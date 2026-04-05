from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from sample.backends.base import BackendSettings, ModelBackend
from sample.backends.openai_api import OpenAIAPIBackend
from sample.core.schemas import BaselineConfig, RuntimeConfig
from sample.io.config_loader import load_baseline_config, load_runtime_config
from sample.models import MODALITY_MODELS
from sample.prompt_manager import PsychAgentPromptManager
from sample.skill_manager import SkillManager
from sample.utils import extract_tag_content, format_transcript, safe_json_loads, strip_end_token

from .domain import (
    school_to_psychagent_sect,
    stage_from_key,
    stage_key_to_skill_stage,
    summary_stage_to_stage_key,
)
from .models import TherapyCourseRecord, TherapyVisitRecord
from .schemas import VisitMessageOut, VisitPsychContextOut, VisitState

SESSION_FOCUS_DEFAULT: List[str] = [
    "建立初始关系与咨询框架",
    "收集稳定背景信息",
    "了解当前主要困扰与近期变化",
    "澄清来访动机与期待",
    "进行基础身心与功能评估",
    "识别潜在风险与可用资源",
    "会谈总结与协作性反馈",
]


class PsychAgentWebBackend:
    def __init__(
        self,
        *,
        project_root: Path,
        baseline_config_path: str | Path,
        runtime_config_path: str | Path,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._project_root = Path(project_root)
        self._logger = logger or logging.getLogger(self.__class__.__name__)

        self._baseline_config_path = self._resolve_path(baseline_config_path)
        self._runtime_config_path = self._resolve_path(runtime_config_path)

        self._baseline_config = load_baseline_config(self._baseline_config_path)
        self._runtime_config = load_runtime_config(self._runtime_config_path)
        self._backend = self._make_backend(self._baseline_config)

        self._psych_prompt_root = self._project_root / "prompts" / "psychagent"
        self._prompt_managers: Dict[str, PsychAgentPromptManager] = {}
        self._skill_manager = SkillManager(
            backend=self._backend,
            runtime_config=self._runtime_config,
            logger=self._logger.getChild("skill"),
        )
        self._started = False

    @property
    def baseline_config(self) -> BaselineConfig:
        return self._baseline_config

    @property
    def runtime_config(self) -> RuntimeConfig:
        return self._runtime_config

    async def startup(self) -> None:
        if self._started:
            return
        await self._skill_manager.load_library()
        self._started = True
        self._logger.info(
            "PsychAgent web backend ready with baseline=%s runtime=%s",
            self._baseline_config_path,
            self._runtime_config_path,
        )

    async def reply_from_visit(
        self,
        *,
        fallback_messages: List[Dict[str, str]],
        course: TherapyCourseRecord,
        visit: TherapyVisitRecord,
        visit_state: VisitState,
        psych_context: Optional[VisitPsychContextOut],
    ) -> Dict[str, Any]:
        if not self._started:
            await self.startup()
        try:
            sect = school_to_psychagent_sect(course.school_id)
            stage = stage_from_key(visit.stage_key_snapshot)
            stage_idx = stage_key_to_skill_stage(visit.stage_key_snapshot)
            prompt_manager = self._get_prompt_manager(sect)

            session_focus = self._build_session_focus(psych_context)
            history = self._build_prompt_history(psych_context)
            homework = list((psych_context.homework if psych_context else []) or [])
            client_info = self._build_prompt_client_info(course, psych_context)
            session_goals = {
                "stage_title": stage.label,
                "objective": session_focus,
            }

            candidate_skills = await self._build_candidate_skills(sect, session_goals, stage_idx)
            transcript = self._build_transcript(visit_state.messages)
            user_query = self._last_user_query(transcript)
            diag_hist = self._build_diag_history(transcript[:-1])

            suggested_skills: List[Dict[str, Any]] = []
            if user_query:
                suggested_skills, _ = await self._skill_manager.retrive(
                    sect=sect,
                    query=user_query,
                    session_stage=stage_idx,
                    session_goals=session_goals,
                    diag_hist=diag_hist,
                    candidate_skills=candidate_skills,
                )

            system_prompt = prompt_manager.render(
                "counselor_system",
                client_info=client_info,
                history=history,
                session_stage=stage.label,
                session_focus=session_focus,
                homework_assigned_from_last_session=homework,
                suggested_skills=suggested_skills,
            )
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(self._build_chat_history(visit_state.messages))

            raw = await self._chat_once(messages)
            text, should_end = self._normalize_output_with_end(raw)
            if text:
                return {"text": text, "end": should_end}
            raise RuntimeError("empty response from PsychAgent prompt chain")
        except Exception as exc:
            self._logger.warning("PsychAgent prompt chain failed, falling back to baseline prompt: %s", exc)
            raw = await self._chat_once(fallback_messages)
            text, should_end = self._normalize_output_with_end(raw)
            if not text:
                raise RuntimeError("empty response from fallback prompt")
            return {"text": text, "end": should_end}

    async def _chat_once(self, messages: List[Dict[str, str]]) -> str:
        return await self._backend.chat_text(
            messages=messages,
            model=self._baseline_config.model,
            temperature=self._baseline_config.temperature,
            max_tokens=self._baseline_config.max_tokens,
            timeout_sec=self._baseline_config.timeout_sec,
            max_retries=self._baseline_config.max_retries,
            retry_sleep_sec=self._baseline_config.retry_sleep_sec,
            end_token=self._baseline_config.end_token,
            output_language=self._runtime_config.output_language,
        )

    async def build_session_close_artifacts(
        self,
        *,
        course: TherapyCourseRecord,
        visit: TherapyVisitRecord,
        visit_state: VisitState,
        psych_context: Optional[VisitPsychContextOut],
    ) -> Dict[str, Any]:
        if not self._started:
            await self.startup()

        try:
            sect = school_to_psychagent_sect(course.school_id)
            modality_models = MODALITY_MODELS.get(sect)
            if not modality_models:
                raise ValueError(f"unsupported modality for psychagent session close: {sect}")

            stage = stage_from_key(visit.stage_key_snapshot)
            prompt_manager = self._get_prompt_manager(sect)
            session_focus = self._build_session_focus(psych_context)
            history = self._build_prompt_history(psych_context)
            client_info = self._build_prompt_client_info(course, psych_context)
            transcript = self._build_transcript(visit_state.messages)

            summary_prompt = prompt_manager.render(
                "summary_user",
                session_stage=stage.label,
                client_info=client_info,
                session_focus=session_focus,
                history=history,
                current_session_dialogue=format_transcript(transcript, for_profile=False),
            )
            summary_data = await self._chat_structured_json(
                system_prompt=str(prompt_manager.prompts.get("summary_system", "")),
                user_prompt=summary_prompt,
                schema_model=modality_models["summary"],
                task_label="summary",
            )

            profile_prompt = prompt_manager.render(
                "profile_user",
                current_session_dialogue=format_transcript(transcript, for_profile=True),
                client_info=client_info,
            )
            profile_data = await self._chat_structured_json(
                system_prompt=str(prompt_manager.prompts.get("profile_system", "")),
                user_prompt=profile_prompt,
                schema_model=modality_models["profile"],
                task_label="profile",
            )

            next_plan = summary_data.get("next_session_plan")
            next_focus: List[str] = []
            next_stage_raw = ""
            next_stage_key = ""
            should_complete_course = False
            if isinstance(next_plan, dict):
                raw_focus = next_plan.get("next_session_focus")
                if isinstance(raw_focus, list):
                    next_focus = [str(item).strip() for item in raw_focus if str(item).strip()]
                next_stage_raw = str(next_plan.get("next_session_stage") or "").strip()
                should_complete_course = next_stage_raw.lower() == "termination"
                if not should_complete_course:
                    next_stage_key = str(summary_stage_to_stage_key(next_stage_raw) or "").strip()
            if should_complete_course:
                next_stage_label = "Termination"
            else:
                if not next_stage_key:
                    next_stage_key = visit.stage_key_snapshot
                next_stage_label = stage_from_key(next_stage_key).label

            raw_homework = summary_data.get("homework")
            homework: List[str] = []
            if isinstance(raw_homework, list):
                homework = [str(item).strip() for item in raw_homework if str(item).strip()]

            return {
                "summary_text": str(summary_data.get("session_summary_abstract") or "").strip(),
                "next_session_focus": next_focus[:8],
                "next_session_stage_key": next_stage_key,
                "next_session_stage": next_stage_label,
                "next_session_stage_raw": next_stage_raw,
                "should_complete_course": should_complete_course,
                "homework": homework[:12],
                "updated_profile": profile_data,
                "profile_payload": profile_data,
                "summary_payload": summary_data,
                "source": "psychagent_summary_profile_v2",
            }
        except Exception as exc:
            self._logger.warning("PsychAgent session-close postprocess failed: %s", exc)
            return {}

    async def _chat_structured_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_model: Any,
        task_label: str,
    ) -> Dict[str, Any]:
        if not system_prompt.strip():
            raise ValueError(f"empty system prompt for {task_label}")
        if not user_prompt.strip():
            raise ValueError(f"empty user prompt for {task_label}")

        attempts = max(1, int(self._baseline_config.max_retries or 1))
        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                raw = await self._chat_once(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ]
                )
                payload = safe_json_loads(raw)
                if "static_traits" in payload and isinstance(payload["static_traits"], dict):
                    payload["static_traits"].pop("language_features", None)
                payload.pop("user_id", None)
                self._validate_schema_payload(schema_model, payload)
                return payload
            except Exception as exc:
                last_error = exc
                self._logger.warning(
                    "PsychAgent %s parse/validate failed (attempt %s/%s): %s",
                    task_label,
                    attempt,
                    attempts,
                    exc,
                )

        raise RuntimeError(f"structured generation failed for {task_label}: {last_error}")

    @staticmethod
    def _validate_schema_payload(schema_model: Any, payload: Dict[str, Any]) -> None:
        """Validate payload for both pydantic v2 and v1 runtimes."""
        if hasattr(schema_model, "model_validate"):
            schema_model.model_validate(payload)
            return
        if hasattr(schema_model, "parse_obj"):
            schema_model.parse_obj(payload)
            return
        raise TypeError(f"unsupported schema model validator: {schema_model}")

    async def _build_candidate_skills(
        self,
        sect: str,
        session_goals: Dict[str, Any],
        stage_idx: int,
    ) -> List[Dict[str, Any]]:
        meta_skills, _, _, _ = await self._skill_manager.corse_filter(
            sect=sect,
            session_goals=session_goals,
            stage=stage_idx,
        )
        candidate_skills: List[Dict[str, Any]] = []
        for item in meta_skills:
            candidate_skills.extend(item.get("micro_skills", []))
        return candidate_skills

    def _get_prompt_manager(self, sect: str) -> PsychAgentPromptManager:
        if sect not in self._prompt_managers:
            self._prompt_managers[sect] = PsychAgentPromptManager(
                self._psych_prompt_root,
                sect,
                counselor_system_filename=self._runtime_config.psychagent_counselor_system_filename,
            )
        return self._prompt_managers[sect]

    def _make_backend(self, baseline: BaselineConfig) -> ModelBackend:
        if baseline.backend != "openai_api":
            raise ValueError(f"src/web backend requires baseline.backend=openai_api, got {baseline.backend!r}")

        api_key = os.environ.get(baseline.api_key_env, "").strip() if baseline.api_key_env else ""
        if baseline.api_key_env and not api_key:
            raise RuntimeError(f"missing model api key env: {baseline.api_key_env}")

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
        return OpenAIAPIBackend(settings=settings, logger=self._logger.getChild("counselor"))

    def _resolve_path(self, raw_path: str | Path) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        return (self._project_root / path).resolve()

    @staticmethod
    def _normalize_text_list(raw: Any, limit: int = 8) -> List[str]:
        if not isinstance(raw, list):
            return []
        values: List[str] = []
        for item in raw:
            text = str(item).strip()
            if not text or text in values:
                continue
            values.append(text)
            if len(values) >= limit:
                break
        return values

    def _build_session_focus(
        self,
        psych_context: Optional[VisitPsychContextOut],
    ) -> List[str]:
        focus = self._normalize_text_list(
            psych_context.session_focus if psych_context else [],
            limit=8,
        )
        if focus:
            return focus
        return list(SESSION_FOCUS_DEFAULT)

    def _build_prompt_history(
        self,
        psych_context: Optional[VisitPsychContextOut],
    ) -> List[Dict[str, Any]]:
        history_items = list((psych_context.history if psych_context else []) or [])
        prompt_history: List[Dict[str, Any]] = []
        for item in history_items:
            if not isinstance(item, dict):
                continue
            summary_payload = item.get("summary_payload")
            if not isinstance(summary_payload, dict):
                summary_payload = {}

            prompt_item: Dict[str, Any] = {
                "session_stage": str(
                    item.get("session_stage")
                    or item.get("stage_label")
                    or item.get("stage_key")
                    or "未知阶段"
                ),
                "session_summary_abstract": str(
                    item.get("session_summary_abstract")
                    or item.get("summary")
                    or summary_payload.get("session_summary_abstract")
                    or ""
                ).strip()
                or "暂无摘要",
            }

            client_state_analysis = item.get("client_state_analysis")
            if not isinstance(client_state_analysis, dict):
                client_state_analysis = summary_payload.get("client_state_analysis")
            if isinstance(client_state_analysis, dict) and client_state_analysis:
                prompt_item["client_state_analysis"] = client_state_analysis

            goal_assessment = item.get("goal_assessment")
            if not isinstance(goal_assessment, dict):
                goal_assessment = summary_payload.get("goal_assessment")
            if isinstance(goal_assessment, dict) and goal_assessment:
                prompt_item["goal_assessment"] = goal_assessment

            homework = item.get("homework")
            if not isinstance(homework, list):
                homework = summary_payload.get("homework")
            normalized_homework = self._normalize_text_list(homework, limit=12)
            if normalized_homework:
                prompt_item["homework"] = normalized_homework

            prompt_history.append(prompt_item)
        return prompt_history

    def _build_prompt_client_info(
        self,
        course: TherapyCourseRecord,
        psych_context: Optional[VisitPsychContextOut],
    ) -> Dict[str, Any]:
        raw_info = dict((psych_context.client_info if psych_context else {}) or {})
        static_traits = raw_info.get("static_traits") if isinstance(raw_info.get("static_traits"), dict) else {}
        note_lines = self._split_lines(course.intake_note)
        growth_experiences = raw_info.get("growth_experiences")
        if not isinstance(growth_experiences, list):
            growth_experiences = note_lines

        pure_profile: Dict[str, Any] = {
            "static_traits": {
                "name": static_traits.get("name") or "来访者",
                "age": static_traits.get("age") or raw_info.get("age") or "未知",
                "gender": static_traits.get("gender") or raw_info.get("gender") or "未知",
                "occupation": static_traits.get("occupation") or raw_info.get("occupation") or "未知",
                "educational_background": static_traits.get("educational_background") or "未知",
                "marital_status": static_traits.get("marital_status") or "未知",
                "family_status": static_traits.get("family_status")
                or raw_info.get("family_status")
                or (note_lines[0] if note_lines else "未知"),
                "social_status": static_traits.get("social_status") or raw_info.get("social_status") or "未知",
                "medical_history": static_traits.get("medical_history") or raw_info.get("medical_history") or "未知",
            },
            "main_problem": raw_info.get("main_problem") or course.intake_note or course.goal_summary or "待澄清",
            "topic": raw_info.get("topic") or course.title or course.goal_summary or "当前困扰",
            "core_demands": raw_info.get("core_demands") or course.goal_summary or "待澄清",
            "growth_experiences": growth_experiences,
            # Modality-specific profile fields (kept pure: no course/workflow metadata).
            "target_behavior": raw_info.get("target_behavior") if isinstance(raw_info.get("target_behavior"), list) else [],
            "core_beliefs": raw_info.get("core_beliefs") if isinstance(raw_info.get("core_beliefs"), list) else [],
            "special_situations": raw_info.get("special_situations")
            if isinstance(raw_info.get("special_situations"), list)
            else [],
            "existentialism_topic": raw_info.get("existentialism_topic")
            if isinstance(raw_info.get("existentialism_topic"), list)
            else [],
            "contact_model": raw_info.get("contact_model") if isinstance(raw_info.get("contact_model"), list) else [],
            "core_conflict": raw_info.get("core_conflict") if isinstance(raw_info.get("core_conflict"), dict) else {},
            "object_relations": raw_info.get("object_relations")
            if isinstance(raw_info.get("object_relations"), list)
            else [],
            "behavioral_response_patterns": raw_info.get("behavioral_response_patterns")
            if isinstance(raw_info.get("behavioral_response_patterns"), list)
            else [],
            "exception_events": raw_info.get("exception_events")
            if isinstance(raw_info.get("exception_events"), list)
            else [],
            "force_field": raw_info.get("force_field") if isinstance(raw_info.get("force_field"), dict) else {},
        }
        return pure_profile

    @staticmethod
    def _build_transcript(messages: List[VisitMessageOut]) -> List[Dict[str, str]]:
        transcript: List[Dict[str, str]] = []
        for message in messages:
            content = str(message.text or "").strip()
            if not content:
                continue
            transcript.append({"role": message.role, "content": content})
        return transcript

    @staticmethod
    def _build_chat_history(messages: List[VisitMessageOut]) -> List[Dict[str, str]]:
        chat_messages: List[Dict[str, str]] = []
        for message in messages:
            if message.role not in {"assistant", "user"}:
                continue
            content = str(message.text or "").strip()
            if not content:
                continue
            chat_messages.append({"role": message.role, "content": content})
        return chat_messages

    @staticmethod
    def _build_diag_history(transcript: List[Dict[str, str]]) -> List[Dict[str, str]]:
        diag_hist: List[Dict[str, str]] = []
        for item in transcript:
            role = item.get("role")
            if role == "assistant":
                mapped_role = "Counselor"
            elif role == "user":
                mapped_role = "Client"
            else:
                continue
            diag_hist.append({"role": mapped_role, "text": str(item.get("content") or "")})
        return diag_hist

    @staticmethod
    def _last_user_query(transcript: List[Dict[str, str]]) -> str:
        for item in reversed(transcript):
            if item.get("role") == "user":
                return str(item.get("content") or "").strip()
        return ""

    def _normalize_output(self, raw_text: str) -> str:
        text, _ = self._normalize_output_with_end(raw_text)
        return text

    def _normalize_output_with_end(self, raw_text: str) -> tuple[str, bool]:
        text = extract_tag_content(raw_text, tag="response") or raw_text or ""
        text, has_end = strip_end_token(text, self._baseline_config.end_token)
        return text.strip(), has_end

    @staticmethod
    def _split_lines(raw_text: str) -> List[str]:
        values: List[str] = []
        for line in str(raw_text or "").splitlines():
            normalized = line.strip().lstrip("-•").strip()
            if normalized:
                values.append(normalized)
        return values
