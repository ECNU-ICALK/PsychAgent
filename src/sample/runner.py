from __future__ import annotations

import asyncio
import copy
import logging
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .backends.base import BackendSettings, ModelBackend
from .backends.dummy_backend import DummyBackend
from .backends.openai_api import OpenAIAPIBackend
from .client.simulator import ClientSimulator
from .core.contracts import CaseResumeDecision, CaseRunResult
from .core.prompt_manager import PromptManager
from .core.schemas import BaselineConfig, ClientCase, PublicMemory, RunResult, RuntimeConfig
from .io.resume import inspect_case_resume
from .io.store import ResultStore
from .models import MODALITY_MODELS
from .prompt_manager import PsychAgentPromptManager
from .skill_manager import STAGE_MAP, SkillManager
from .utils import extract_tag_content, format_transcript, safe_json_loads, strip_end_token


DEFAULT_SESSION_FOCUS = [
    "建立初始关系与咨询框架：开场寒暄与关系建立，确认称呼，说明首会重点与会谈结构，澄清频率与时长，说明保密原则及其限度。",
    "收集稳定背景信息：了解基本人口学信息、成长与家庭背景、居住与通学/工作情况、兴趣与优势等，以形成初步整体印象。",
    "了解当前主要困扰与近期变化：围绕触发情境、核心困扰、主要情绪体验及显著行为/功能变化（学习、睡眠、人际等）进行探索。",
    "澄清来访动机与期待：了解促成就诊的关键事件与动机，共同梳理表层问题清单，提出并协商最优先的改变方向及短—中期目标。",
    "进行基础身心与功能评估：从情绪、睡眠、饮食、精力、学习/工作、人际功能等方面做初步评估，必要时了解身体健康状况与用药情况。",
    "识别潜在风险与可用资源：评估自/他伤风险、人际冲突与危险物品接触等，盘点家庭、同伴与校园资源，必要时共拟初步安全与支持计划。",
    "会谈总结与协作性反馈：共同回顾本次重点与收获，邀请来访者反馈体验与补充重要内容，确认联系与界限，并初步商定后续会谈安排。",
]


class MaxRetriesExceededError(Exception):
    """Raised when retry budget for one case/session is exhausted."""


# Backward-compatible aliases for existing imports.
# Downstream modules should import public contracts from sample.core.contracts.
_CaseResumeDecision = CaseResumeDecision
_CaseRunResult = CaseRunResult


@dataclass
class PsychAgentRunner:
    baseline_config: BaselineConfig
    runtime_config: RuntimeConfig
    prompt_root: Path
    logger: Optional[logging.Logger] = None

    def __post_init__(self) -> None:
        self._logger = self.logger or logging.getLogger(self.__class__.__name__)
        random.seed(self.runtime_config.random_seed)

        self._store = ResultStore(self.runtime_config.save_dir, self.baseline_config.name)
        self._core_prompt_manager = PromptManager(prompt_root=self.prompt_root)
        self._psych_prompt_root = self.prompt_root / "psychagent"

        self._counselor_backend = self._make_backend(self.baseline_config)
        self._client_backend = self._make_client_backend(self.runtime_config)

        self._client_simulator = ClientSimulator(
            prompt_manager=self._core_prompt_manager,
            output_language=self.runtime_config.output_language,
            backend=self._client_backend,
            temperature=self.runtime_config.client_temperature,
            max_tokens=self.runtime_config.client_max_tokens,
            timeout_sec=self.runtime_config.client_timeout_sec,
            max_retries=self.runtime_config.client_max_retries,
            retry_sleep_sec=self.runtime_config.client_retry_sleep_sec,
        )

        self._skill_manager = SkillManager(
            backend=self._counselor_backend,
            runtime_config=self.runtime_config,
            logger=self._logger.getChild("skill"),
        )
        self._prompt_managers: Dict[str, PsychAgentPromptManager] = {}

    async def run_cases(self, cases: List[ClientCase]) -> RunResult:
        await self._skill_manager.load_library()

        result = RunResult(total_cases=len(cases))
        lock = asyncio.Lock()
        sem = asyncio.Semaphore(self.runtime_config.concurrency)

        async def _run_one(case: ClientCase) -> None:
            async with sem:
                case_prefix = f"[case={case.case_id} modality={case.modality}]"
                self._logger.info("%s psychagent start", case_prefix)
                try:
                    self._store.prepare_case_dir(
                        case.modality,
                        case.case_id,
                        overwrite=self.runtime_config.overwrite,
                    )
                    decision = self._inspect_case_resume(case)
                    if decision.action == "skip":
                        async with lock:
                            result.skipped_completed += 1
                        self._logger.info("%s skipped (%s)", case_prefix, decision.reason)
                        return

                    course = await self._run_case(case, decision)
                    if course.finished:
                        async with lock:
                            result.succeeded += 1
                        self._logger.info("%s psychagent succeeded", case_prefix)
                    else:
                        async with lock:
                            if course.finished_reason == "failed_retries":
                                result.failed_due_to_retries += 1
                            else:
                                result.partially_completed += 1
                        self._logger.warning(
                            "%s psychagent partial finished_reason=%s sessions=%s",
                            case_prefix,
                            course.finished_reason,
                            course.num_sessions,
                        )
                except MaxRetriesExceededError as exc:
                    async with lock:
                        result.failed_due_to_retries += 1
                    self._logger.error("%s retries exhausted: %s", case_prefix, exc)
                except Exception as exc:  # pragma: no cover - defensive
                    async with lock:
                        result.crashed += 1
                    self._logger.exception("%s psychagent crashed: %r", case_prefix, exc)

        await asyncio.gather(*[_run_one(case) for case in cases])
        return result

    async def _run_case(self, case: ClientCase, decision: _CaseResumeDecision) -> _CaseRunResult:
        state = self._init_case_state(case, decision)

        termination_reached = False
        finished_reason = "in_progress"

        for session_index in range(state["next_session_index"], self.baseline_config.max_sessions + 1):
            if self._is_termination(state["stage"]):
                termination_reached = True
                finished_reason = "termination"
                break

            session_record, next_state = await self._run_single_session(
                case=case,
                session_index=session_index,
                history_list=state["history_list"],
                obtain_client_info=state["obtain_client_info"],
                session_focus=state["session_focus"],
                stage=state["stage"],
                homework_assigned=state["homework_assigned"],
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

        return _CaseRunResult(finished=finished, finished_reason=reason, num_sessions=num_sessions)

    async def _run_single_session(
        self,
        *,
        case: ClientCase,
        session_index: int,
        history_list: List[Dict[str, Any]],
        obtain_client_info: Dict[str, Any],
        session_focus: List[str],
        stage: str,
        homework_assigned: List[str],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        modality_lower = case.modality.lower()
        models = MODALITY_MODELS.get(modality_lower)
        if not models:
            raise RuntimeError(f"unsupported modality for psychagent: {case.modality}")

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

        dialogue_rollout = await self._run_dialogue_rollout(
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
        transcript = dialogue_rollout["transcript"]
        each_turn_system = dialogue_rollout["each_turn_system"]

        summary_txt = format_transcript(transcript, for_profile=False)
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

        profile_txt = format_transcript(transcript, for_profile=True)
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

        record = {
            "stage": stage,
            "focus": session_focus,
            "profile_snapshot": dict(obtain_client_info),
            "transcript": transcript,
            "summary": summary_dict,
            "updated_profile": updated_profile,
            "each_turn_system": each_turn_system,
        }

        next_state = {
            "history_list": next_history,
            "obtain_client_info": updated_profile if updated_profile else obtain_client_info,
            "session_focus": next_focus,
            "stage": next_stage,
            "homework_assigned": next_homework,
        }
        return record, next_state

    async def _run_dialogue_rollout(
        self,
        *,
        case: ClientCase,
        session_index: int,
        history_list: List[Dict[str, Any]],
        obtain_client_info: Dict[str, Any],
        session_focus: List[str],
        stage: str,
        homework_assigned: List[str],
        prompt_mgr: PsychAgentPromptManager,
        candidate_skills: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        modality_lower = case.modality.lower()
        session_goals = {"stage_title": "stage", "objective": session_focus}

        transcript: List[Dict[str, Any]] = []
        counselor_messages: List[Dict[str, str]] = []
        each_turn_system: List[str] = []

        def render_counselor_system(skills: Optional[List[Dict[str, Any]]] = None) -> str:
            return prompt_mgr.render(
                "counselor_system",
                client_info=obtain_client_info,
                history=history_list,
                session_stage=stage,
                session_focus=session_focus,
                homework_assigned_from_last_session=homework_assigned,
                suggested_skills=skills or [],
            )

        counselor_messages.append({"role": "system", "content": render_counselor_system()})
        transcript.append({"role": "system", "content": counselor_messages[0]["content"]})

        opening_instr = f"这是第{session_index}次会话"
        transcript.append({"role": "user", "content": opening_instr})
        counselor_messages.append({"role": "user", "content": opening_instr})

        skill_suggestion, _ = await self._retrieve_skill(
            modality=modality_lower,
            transcript=transcript,
            session_goals=session_goals,
            stage=stage,
            candidate_skills=candidate_skills,
            case_id=case.case_id,
        )
        counselor_messages[0]["content"] = render_counselor_system(skill_suggestion)
        each_turn_system.append(counselor_messages[0]["content"])

        c_open_pure, c_open_raw = await self._chat_with_retry(
            self._counselor_backend,
            counselor_messages,
            f"[case={case.case_id}] opening",
        )
        c_open_clean, _ = strip_end_token(c_open_pure, self.baseline_config.end_token)
        raw_open_clean, opening_end = strip_end_token(c_open_raw, self.baseline_config.end_token)

        transcript.append({"role": "assistant", "content": raw_open_clean})
        counselor_messages.append({"role": "assistant", "content": c_open_clean})

        client_transcript: List[Dict[str, Any]] = []
        if c_open_clean:
            client_transcript.append({"role": "assistant", "content": c_open_clean})

        public_memory = self._build_public_memory(history_list, obtain_client_info, homework_assigned)

        c_turns = 1
        if not opening_end:
            while c_turns < self.runtime_config.psychagent_max_turns:
                client_resp = await self._client_simulator.generate_client_utterance(
                    case=case,
                    session_index=session_index,
                    prior_transcript=client_transcript,
                    public_memory=public_memory,
                )
                transcript.append({"role": "user", "content": client_resp})
                counselor_messages.append({"role": "user", "content": client_resp})
                client_transcript.append({"role": "user", "content": client_resp})

                skill_suggestion, _ = await self._retrieve_skill(
                    modality=modality_lower,
                    transcript=transcript,
                    session_goals=session_goals,
                    stage=stage,
                    candidate_skills=candidate_skills,
                    case_id=case.case_id,
                )
                counselor_messages[0]["content"] = render_counselor_system(skill_suggestion)
                each_turn_system.append(counselor_messages[0]["content"])

                c_resp_pure, c_resp_raw = await self._chat_with_retry(
                    self._counselor_backend,
                    counselor_messages,
                    f"[case={case.case_id}] counselor turn={c_turns}",
                )
                c_resp_clean, is_end = strip_end_token(c_resp_pure, self.baseline_config.end_token)
                raw_resp_clean, _ = strip_end_token(c_resp_raw, self.baseline_config.end_token)

                transcript.append({"role": "assistant", "content": raw_resp_clean})
                counselor_messages.append({"role": "assistant", "content": c_resp_clean})
                client_transcript.append({"role": "assistant", "content": c_resp_clean})

                c_turns += 1
                if is_end:
                    break

        return {
            "transcript": transcript,
            "each_turn_system": each_turn_system,
        }

    async def _build_summary(
        self,
        summary_model: Any,
        system_prompt: str,
        user_prompt: str,
        case_id: str,
    ) -> Dict[str, Any]:
        summary_dict: Optional[Dict[str, Any]] = None
        for attempt in range(1, self.runtime_config.psychagent_max_retries + 1):
            try:
                raw = await self._chat_once(
                    self._counselor_backend,
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                temp = safe_json_loads(raw)
                summary_model.model_validate(temp)
                summary_dict = temp
                break
            except Exception as exc:
                self._logger.warning(
                    "[case=%s] summary retry %s/%s error=%s",
                    case_id,
                    attempt,
                    self.runtime_config.psychagent_max_retries,
                    exc,
                )
                await asyncio.sleep(self.runtime_config.psychagent_retry_sleep_sec)

        if summary_dict is None:
            raise MaxRetriesExceededError(f"summary generation failed for case={case_id}")

        return summary_dict

    async def _build_profile(
        self,
        profile_model: Any,
        system_prompt: str,
        user_prompt: str,
        case_id: str,
    ) -> Dict[str, Any]:
        updated_profile: Optional[Dict[str, Any]] = None
        for attempt in range(1, self.runtime_config.psychagent_max_retries + 1):
            try:
                raw = await self._chat_once(
                    self._counselor_backend,
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                temp = safe_json_loads(raw)
                if "static_traits" in temp and isinstance(temp["static_traits"], dict):
                    temp["static_traits"].pop("language_features", None)
                temp.pop("user_id", None)
                profile_model.model_validate(temp)
                updated_profile = temp
                break
            except Exception as exc:
                self._logger.warning(
                    "[case=%s] profile retry %s/%s error=%s",
                    case_id,
                    attempt,
                    self.runtime_config.psychagent_max_retries,
                    exc,
                )
                await asyncio.sleep(self.runtime_config.psychagent_retry_sleep_sec)

        if updated_profile is None:
            raise MaxRetriesExceededError(f"profile generation failed for case={case_id}")

        return updated_profile

    async def _build_candidate_skills(
        self,
        modality: str,
        session_goals: Dict[str, Any],
        stage_idx: int,
        case_id: str,
    ) -> List[Dict[str, Any]]:
        for attempt in range(1, self.runtime_config.psychagent_max_retries + 1):
            try:
                meta_skills, _, _, _ = await self._skill_manager.corse_filter(
                    sect=modality,
                    session_goals=session_goals,
                    stage=stage_idx,
                )
                candidate_skills: List[Dict[str, Any]] = []
                for item in meta_skills:
                    candidate_skills.extend(item.get("micro_skills", []))
                return candidate_skills
            except Exception as exc:
                self._logger.warning(
                    "[case=%s] coarse filter retry %s/%s error=%s",
                    case_id,
                    attempt,
                    self.runtime_config.psychagent_max_retries,
                    exc,
                )
                await asyncio.sleep(self.runtime_config.psychagent_retry_sleep_sec)

        raise MaxRetriesExceededError(f"coarse filter failed for case={case_id}")

    async def _retrieve_skill(
        self,
        *,
        modality: str,
        transcript: List[Dict[str, Any]],
        session_goals: Dict[str, Any],
        stage: str,
        candidate_skills: List[Dict[str, Any]],
        case_id: str,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        last_msg = transcript[-1].get("content", "") if transcript else ""

        diag_hist: List[Dict[str, str]] = []
        for msg in transcript[:-1]:
            role = msg.get("role")
            if role == "assistant":
                mapped_role = "Counselor"
            elif role == "user":
                mapped_role = "Client"
            else:
                continue
            diag_hist.append({"role": mapped_role, "text": str(msg.get("content", ""))})

        for attempt in range(1, self.runtime_config.psychagent_max_retries + 1):
            try:
                return await self._skill_manager.retrive(
                    modality,
                    str(last_msg),
                    stage,
                    session_goals,
                    diag_hist,
                    candidate_skills=candidate_skills,
                )
            except Exception as exc:
                self._logger.warning(
                    "[case=%s] skill retrieve retry %s/%s error=%s",
                    case_id,
                    attempt,
                    self.runtime_config.psychagent_max_retries,
                    exc,
                )
                await asyncio.sleep(self.runtime_config.psychagent_retry_sleep_sec)

        return [], {}

    async def _chat_with_retry(
        self,
        backend: ModelBackend,
        messages: List[Dict[str, str]],
        log_prefix: str,
    ) -> tuple[str, str]:
        last_exc: Exception | None = None
        saw_empty_response = False
        for _ in range(self.runtime_config.psychagent_max_retries):
            try:
                raw = await self._chat_once(backend, messages)
                pure = extract_tag_content(raw, tag="response") or raw
                pure = pure.strip()
                if pure:
                    return pure, raw
                saw_empty_response = True
            except Exception as exc:
                last_exc = exc
                self._logger.warning("%s api error: %s", log_prefix, exc)
            await asyncio.sleep(0.5)

        if last_exc is not None:
            raise MaxRetriesExceededError(
                f"{log_prefix} failed after {self.runtime_config.psychagent_max_retries} retries: {last_exc}"
            ) from last_exc
        if saw_empty_response:
            raise MaxRetriesExceededError(
                f"{log_prefix} failed after {self.runtime_config.psychagent_max_retries} retries: empty response"
            )
        raise MaxRetriesExceededError(
            f"{log_prefix} failed after {self.runtime_config.psychagent_max_retries} retries"
        )

    async def _chat_once(self, backend: ModelBackend, messages: List[Dict[str, str]]) -> str:
        return await backend.chat_text(
            messages=messages,
            model=self.baseline_config.model,
            temperature=self.baseline_config.temperature,
            max_tokens=self.baseline_config.max_tokens,
            timeout_sec=self.baseline_config.timeout_sec,
            max_retries=self.baseline_config.max_retries,
            retry_sleep_sec=self.baseline_config.retry_sleep_sec,
            end_token=self.baseline_config.end_token,
            output_language=self.runtime_config.output_language,
        )

    def _inspect_case_resume(self, case: ClientCase) -> _CaseResumeDecision:
        return inspect_case_resume(
            self._store,
            modality=case.modality,
            case_id=case.case_id,
            max_sessions=self.baseline_config.max_sessions,
            resume_enabled=self.runtime_config.resume,
            overwrite=self.runtime_config.overwrite,
        )

    def _init_case_state(self, case: ClientCase, decision: _CaseResumeDecision) -> Dict[str, Any]:
        if decision.action == "start":
            return {
                "history_list": [],
                "obtain_client_info": {},
                "session_focus": copy.deepcopy(DEFAULT_SESSION_FOCUS),
                "stage": "问题概念化与目标设定",
                "homework_assigned": [],
                "next_session_index": 1,
            }

        if decision.action != "resume":
            return {
                "history_list": [],
                "obtain_client_info": dict(case.intake_profile),
                "session_focus": copy.deepcopy(DEFAULT_SESSION_FOCUS),
                "stage": "Termination",
                "homework_assigned": [],
                "next_session_index": self.baseline_config.max_sessions + 1,
            }

        existing = decision.existing_records
        history_list: List[Dict[str, Any]] = []
        for rec in existing:
            summary = rec.get("summary", {})
            if isinstance(summary, dict):
                summary = dict(summary)
                if "session_stage" not in summary:
                    summary["session_stage"] = rec.get("stage", "")
                history_list.append(summary)

        last = existing[-1]
        last_summary = last.get("summary", {}) if isinstance(last.get("summary"), dict) else {}
        next_plan = last_summary.get("next_session_plan", {}) if isinstance(last_summary.get("next_session_plan"), dict) else {}

        next_stage = str(next_plan.get("next_session_stage", "问题概念化与目标设定"))
        next_focus = next_plan.get("next_session_focus", copy.deepcopy(DEFAULT_SESSION_FOCUS))
        if not isinstance(next_focus, list):
            next_focus = copy.deepcopy(DEFAULT_SESSION_FOCUS)

        homework = last_summary.get("homework", [])
        if not isinstance(homework, list):
            homework = []

        updated_profile = last.get("updated_profile", {})
        if not isinstance(updated_profile, dict):
            updated_profile = {}

        return {
            "history_list": history_list,
            "obtain_client_info": updated_profile,
            "session_focus": next_focus,
            "stage": next_stage,
            "homework_assigned": homework,
            "next_session_index": decision.next_session_index,
        }

    def _build_public_memory(
        self,
        history_list: List[Dict[str, Any]],
        obtain_client_info: Dict[str, Any],
        homework_assigned: List[str],
    ) -> PublicMemory:
        recaps: List[Dict[str, Any]] = []
        for idx, item in enumerate(history_list, start=1):
            if not isinstance(item, dict):
                continue
            recaps.append(
                {
                    "session_index": idx,
                    "summary": item.get("session_summary_abstract", ""),
                    "homework": item.get("homework", []),
                    "static_traits": (obtain_client_info or {}).get("static_traits", {}),
                }
            )

        known_static_traits = {}
        if isinstance(obtain_client_info, dict):
            static_traits = obtain_client_info.get("static_traits", {})
            if isinstance(static_traits, dict):
                known_static_traits = static_traits

        return PublicMemory(
            known_static_traits=known_static_traits,
            session_recaps=recaps,
            last_homework=list(homework_assigned),
        )

    def _get_prompt_manager(self, modality: str) -> PsychAgentPromptManager:
        if modality not in self._prompt_managers:
            self._prompt_managers[modality] = PsychAgentPromptManager(
                self._psych_prompt_root,
                modality,
                counselor_system_filename=self.runtime_config.psychagent_counselor_system_filename,
            )
        return self._prompt_managers[modality]

    def _save_session_record(self, case: ClientCase, session_index: int, record: Dict[str, Any]) -> None:
        self._store.save_session_payload(
            case.modality,
            case.case_id,
            session_index,
            record,
        )

    def _save_case_meta(
        self,
        *,
        case: ClientCase,
        num_sessions: int,
        finished: bool,
        finished_reason: str,
        next_session_index: int,
        current_stage: str,
    ) -> None:
        payload = {
            "case_id": case.case_id,
            "baseline_name": self.baseline_config.name,
            "modality": case.modality,
            "finished": finished,
            "finished_reason": finished_reason,
            "num_sessions": num_sessions,
            "next_session_index": next_session_index,
            "current_stage": current_stage,
        }
        self._store.save_course_payload(case.modality, case.case_id, payload)

    @staticmethod
    def _is_termination(stage: str) -> bool:
        return stage.strip().lower() == "termination"

    def _make_backend(self, baseline: BaselineConfig) -> ModelBackend:
        api_key = os.environ.get(baseline.api_key_env, "") if baseline.api_key_env else ""
        settings = BackendSettings(
            model=baseline.model,
            temperature=baseline.temperature,
            max_tokens=baseline.max_tokens,
            timeout_sec=baseline.timeout_sec,
            max_retries=baseline.max_retries,
            retry_sleep_sec=baseline.retry_sleep_sec,
            base_url=baseline.base_url,
            api_key=api_key or None,
        )

        if baseline.backend == "dummy":
            return DummyBackend()
        if baseline.backend == "openai_api":
            return OpenAIAPIBackend(settings=settings, logger=self._logger.getChild("psychagent_counselor"))
        raise ValueError(f"unsupported backend: {baseline.backend}")

    def _make_client_backend(self, runtime: RuntimeConfig) -> Optional[ModelBackend]:
        if runtime.client_backend == "none":
            return None

        api_key = os.environ.get(runtime.client_api_key_env, "") if runtime.client_api_key_env else ""
        settings = BackendSettings(
            model=runtime.client_model,
            temperature=runtime.client_temperature,
            max_tokens=runtime.client_max_tokens,
            timeout_sec=runtime.client_timeout_sec,
            max_retries=runtime.client_max_retries,
            retry_sleep_sec=runtime.client_retry_sleep_sec,
            base_url=runtime.client_base_url,
            api_key=api_key or None,
        )

        if runtime.client_backend == "dummy":
            return DummyBackend()
        if runtime.client_backend == "openai_api":
            return OpenAIAPIBackend(settings=settings, logger=self._logger.getChild("psychagent_client"))
        raise ValueError(f"unsupported client backend: {runtime.client_backend}")
