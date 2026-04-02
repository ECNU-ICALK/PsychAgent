"""RFT runner that reuses sample simulation and eval reward methods."""

from __future__ import annotations

import asyncio
import copy
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List

try:
    from src.sample.core.contracts import CaseResumeDecision, CaseRunResult
    from src.sample.core.schemas import ClientCase
    from src.sample.models import MODALITY_MODELS
    from src.sample.runner import MaxRetriesExceededError, PsychAgentRunner
    from src.sample.skill_manager import STAGE_MAP
    from src.sample.utils import format_transcript
except ModuleNotFoundError:  # pragma: no cover - supports PYTHONPATH=src execution style
    from sample.core.contracts import CaseResumeDecision, CaseRunResult
    from sample.core.schemas import ClientCase
    from sample.models import MODALITY_MODELS
    from sample.runner import MaxRetriesExceededError, PsychAgentRunner
    from sample.skill_manager import STAGE_MAP
    from sample.utils import format_transcript

from .core.schemas import RFTRuntimeConfig
from .reward import canonical_metric_name, compute_rollout_reward

if TYPE_CHECKING:
    try:
        from src.eval.reward import RewardEvaluator
    except ModuleNotFoundError:  # pragma: no cover - supports PYTHONPATH=src execution style
        from eval.reward import RewardEvaluator


@dataclass
class RFTPsychAgentRunner(PsychAgentRunner):
    """Best-of-n rollout runner with reward-driven session selection."""

    rft_runtime_config: RFTRuntimeConfig = field(default_factory=RFTRuntimeConfig)
    _reward_evaluator: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.rft_runtime_config = self.rft_runtime_config.validated()
        self._reward_evaluator = None

    async def close(self) -> None:
        if self._reward_evaluator is not None:
            await self._reward_evaluator.close()

    async def _run_case(self, case: ClientCase, decision: CaseResumeDecision) -> CaseRunResult:
        state = self._init_case_state(case, decision)

        termination_reached = False
        finished_reason = "in_progress"

        for session_index in range(state["next_session_index"], self.baseline_config.max_sessions + 1):
            if self._is_termination(state["stage"]):
                termination_reached = True
                finished_reason = "termination"
                break

            session_record, next_state = await self._run_single_session_rft(
                case=case,
                session_index=session_index,
                history_list=state["history_list"],
                obtain_client_info=state["obtain_client_info"],
                session_focus=state["session_focus"],
                stage=state["stage"],
                homework_assigned=state["homework_assigned"],
                previous_reward_snapshot=state["pre_rewards"],
            )
            self._save_session_record(case, session_index, session_record)

            state.update(next_state)
            state["next_session_index"] = session_index + 1

            if self._is_termination(state["stage"]):
                termination_reached = True
                finished_reason = "termination"

            self._save_case_meta(
                case=case,
                num_sessions=session_index,
                finished=termination_reached,
                finished_reason=finished_reason if termination_reached else "in_progress",
                next_session_index=state["next_session_index"],
                current_stage=state["stage"],
            )

            if termination_reached:
                break

        num_sessions = state["next_session_index"] - 1
        if termination_reached:
            finished = True
            reason = "termination"
        elif num_sessions >= self.baseline_config.max_sessions:
            finished = False
            reason = "max_sessions_reached"
        else:
            finished = False
            reason = "failed_retries"

        self._save_case_meta(
            case=case,
            num_sessions=num_sessions,
            finished=finished,
            finished_reason=reason,
            next_session_index=num_sessions + 1,
            current_stage=state["stage"],
        )

        return CaseRunResult(finished=finished, finished_reason=reason, num_sessions=num_sessions)

    def _init_case_state(self, case: ClientCase, decision: CaseResumeDecision) -> Dict[str, Any]:
        state = super()._init_case_state(case, decision)
        state["pre_rewards"] = {"counselor": {}, "client": {}}
        if decision.action == "resume" and decision.existing_records:
            state["pre_rewards"] = _extract_reward_snapshot(decision.existing_records[-1])
        return state

    async def _run_single_session_rft(
        self,
        *,
        case: ClientCase,
        session_index: int,
        history_list: List[Dict[str, Any]],
        obtain_client_info: Dict[str, Any],
        session_focus: List[str],
        stage: str,
        homework_assigned: List[str],
        previous_reward_snapshot: Dict[str, Dict[str, float]],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        modality_lower = case.modality.lower()
        models = MODALITY_MODELS.get(modality_lower)
        if not models:
            raise RuntimeError(f"unsupported modality for psychagent_rft: {case.modality}")

        summary_model = models["summary"]
        profile_model = models["profile"]
        prompt_mgr = self._get_prompt_manager(modality_lower)

        session_goals = {"stage_title": "stage", "objective": session_focus}
        stage_idx = STAGE_MAP.get(stage, 1)

        candidate_skills = await self._build_candidate_skills(
            modality_lower,
            session_goals,
            stage_idx,
            case.case_id,
        )

        rollout_results = await self._run_rollout_dialogues(
            case=case,
            session_index=session_index,
            history_list=history_list,
            obtain_client_info=obtain_client_info,
            session_focus=session_focus,
            stage=stage,
            homework_assigned=homework_assigned,
            prompt_mgr=prompt_mgr,
            candidate_skills=candidate_skills,
        )
        if not rollout_results:
            raise MaxRetriesExceededError(f"no rollout generated for case={case.case_id} session={session_index}")

        rollout_candidates: List[Dict[str, Any]] = []
        for rollout in rollout_results:
            evaluator = self._ensure_reward_evaluator()
            evaluation_result = await evaluator.evaluate_dialogue(
                modality=modality_lower,
                dialogue=rollout["transcript"],
                profile=obtain_client_info,
            )
            reward_result = compute_rollout_reward(
                evaluation=evaluation_result,
                previous_reward_snapshot=previous_reward_snapshot,
            )
            rollout_candidates.append(
                {
                    "rollout_index": rollout["rollout_index"],
                    "dialogue": rollout,
                    "reward_result": reward_result,
                    "evaluation_result": evaluation_result,
                    "score": reward_result.final_score,
                }
            )

        best_candidate = max(rollout_candidates, key=lambda item: item["score"])
        best_dialogue = best_candidate["dialogue"]
        best_reward_result = best_candidate["reward_result"]
        best_score = best_candidate["score"]

        summary_txt = format_transcript(best_dialogue["transcript"], for_profile=False)
        summary_prompt = prompt_mgr.render(
            "summary_user",
            session_stage=stage,
            client_info=obtain_client_info,
            session_focus=session_focus,
            history=history_list,
            current_session_dialogue=summary_txt,
        )
        summary_dict = await self._build_summary(
            summary_model,
            prompt_mgr.prompts["summary_system"],
            summary_prompt,
            case.case_id,
        )

        profile_txt = format_transcript(best_dialogue["transcript"], for_profile=True)
        profile_prompt = prompt_mgr.render(
            "profile_user",
            current_session_dialogue=profile_txt,
            client_info=obtain_client_info,
        )
        updated_profile = await self._build_profile(
            profile_model,
            prompt_mgr.prompts["profile_system"],
            profile_prompt,
            case.case_id,
        )

        summary_dict["session_stage"] = stage
        next_plan = summary_dict.get("next_session_plan", {})
        next_stage = str(next_plan.get("next_session_stage", "Termination"))
        next_focus = next_plan.get("next_session_focus", [])
        if not isinstance(next_focus, list):
            next_focus = []
        next_homework = summary_dict.get("homework", [])
        if not isinstance(next_homework, list):
            next_homework = []

        next_history = list(history_list)
        next_history.append(summary_dict)

        keep_rollout_transcript = bool(self.rft_runtime_config.keep_all_rollout_transcripts)
        rollout_debug: List[Dict[str, Any]] = []
        for item in sorted(rollout_candidates, key=lambda x: x["rollout_index"]):
            reward_info = item["reward_result"]
            eval_info = item["evaluation_result"]
            payload = {
                "rollout_index": item["rollout_index"],
                "reward_score": item["score"],
                "reward_result": reward_info.to_dict(),
                "method_status": dict(eval_info.method_status),
                "method_errors": dict(eval_info.method_errors),
                "missing_methods": list(eval_info.missing_methods),
            }
            if keep_rollout_transcript:
                payload["transcript"] = item["dialogue"]["transcript"]
                payload["each_turn_system"] = item["dialogue"]["each_turn_system"]
            rollout_debug.append(payload)

        record = {
            "stage": stage,
            "focus": session_focus,
            "profile_snapshot": dict(obtain_client_info),
            "transcript": best_dialogue["transcript"],
            "summary": summary_dict,
            "updated_profile": updated_profile,
            "each_turn_system": best_dialogue["each_turn_system"],
            "evaluation_score": best_score,
            "rollout_data": {
                "rollout_n": self.rft_runtime_config.rollout_n,
                "winner_rollout_index": best_candidate["rollout_index"],
                "rollout_rewards": best_reward_result.reward_snapshot,
                "rollout_candidates": rollout_debug,
            },
        }

        next_state = {
            "history_list": next_history,
            "obtain_client_info": updated_profile if updated_profile else obtain_client_info,
            "session_focus": next_focus,
            "stage": next_stage,
            "homework_assigned": next_homework,
            "pre_rewards": best_reward_result.reward_snapshot,
        }
        return record, next_state

    async def _run_rollout_dialogues(
        self,
        *,
        case: ClientCase,
        session_index: int,
        history_list: List[Dict[str, Any]],
        obtain_client_info: Dict[str, Any],
        session_focus: List[str],
        stage: str,
        homework_assigned: List[str],
        prompt_mgr: Any,
        candidate_skills: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        rollout_n = max(1, int(self.rft_runtime_config.rollout_n))
        semaphore = asyncio.Semaphore(max(1, int(self.rft_runtime_config.rollout_concurrency)))

        async def _run_one(rollout_index: int) -> Dict[str, Any]:
            async with semaphore:
                dialogue = await self._run_dialogue_rollout(
                    case=case,
                    session_index=session_index,
                    history_list=history_list,
                    obtain_client_info=obtain_client_info,
                    session_focus=session_focus,
                    stage=stage,
                    homework_assigned=homework_assigned,
                    prompt_mgr=prompt_mgr,
                    candidate_skills=copy.deepcopy(candidate_skills),
                )
                dialogue["rollout_index"] = rollout_index
                return dialogue

        tasks = [asyncio.create_task(_run_one(i + 1)) for i in range(rollout_n)]
        results: List[Dict[str, Any]] = []
        for task in asyncio.as_completed(tasks):
            results.append(await task)
        results.sort(key=lambda item: int(item.get("rollout_index", 0)))
        return results

    def _resolve_reward_api_key(self) -> str | None:
        if self.rft_runtime_config.reward_api_key:
            return self.rft_runtime_config.reward_api_key
        if self.runtime_config.client_api_key_env:
            candidate = os.environ.get(self.runtime_config.client_api_key_env)
            if candidate:
                return candidate
        if self.baseline_config.api_key_env:
            candidate = os.environ.get(self.baseline_config.api_key_env)
            if candidate:
                return candidate
        return os.environ.get("CHAT_API_KEY")

    def _ensure_reward_evaluator(self) -> Any:
        if self._reward_evaluator is not None:
            return self._reward_evaluator

        reward_evaluator_cls = _load_reward_evaluator_class()
        self._reward_evaluator = reward_evaluator_cls(
            api_key=self._resolve_reward_api_key(),
            api_base_url=(
                self.rft_runtime_config.reward_api_base_url
                or self.runtime_config.client_base_url
                or self.baseline_config.base_url
                or None
            ),
            api_model=(
                self.rft_runtime_config.reward_api_model
                or self.runtime_config.client_model
                or self.baseline_config.model
            ),
            api_concurrency=self.rft_runtime_config.reward_api_concurrency,
            api_rps=self.rft_runtime_config.reward_api_rps,
            api_rps_period=self.rft_runtime_config.reward_api_rps_period,
            method_concurrency=self.rft_runtime_config.reward_method_concurrency,
            method_by_modality=self.rft_runtime_config.method_by_modality,
        )
        return self._reward_evaluator


def _extract_reward_snapshot(record: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    rollout_data = record.get("rollout_data")
    if not isinstance(rollout_data, dict):
        return {"counselor": {}, "client": {}}

    raw = rollout_data.get("rollout_rewards")
    if not isinstance(raw, dict):
        return {"counselor": {}, "client": {}}

    counselor_raw = raw.get("counselor", {})
    client_raw = raw.get("client", {})
    return {
        "counselor": _normalize_numeric_scores(counselor_raw),
        "client": _normalize_numeric_scores(client_raw),
    }


def _normalize_numeric_scores(raw: Any) -> Dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    normalized: Dict[str, float] = {}
    for key, value in raw.items():
        if isinstance(value, (int, float)):
            normalized[canonical_metric_name(str(key))] = float(value)
    return normalized


def _load_reward_evaluator_class() -> Any:
    try:
        from src.eval.reward import RewardEvaluator
    except ModuleNotFoundError:  # pragma: no cover - supports PYTHONPATH=src execution style
        from eval.reward import RewardEvaluator
    return RewardEvaluator
