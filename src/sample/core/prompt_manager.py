"""Jinja2-based prompt rendering utilities."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .schemas import ClientCase, PublicMemory

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
except ImportError:  # pragma: no cover - fallback path for minimal environments
    Environment = None  # type: ignore[assignment]
    FileSystemLoader = None  # type: ignore[assignment]
    StrictUndefined = None  # type: ignore[assignment]


@dataclass
class PromptManager:
    """Loads and renders public and client prompts."""

    prompt_root: Path
    _env: Optional[Any] = None

    def __post_init__(self) -> None:
        if Environment is not None:
            self._env = Environment(
                loader=FileSystemLoader(str(self.prompt_root)),
                autoescape=False,
                undefined=StrictUndefined,
                trim_blocks=True,
                lstrip_blocks=True,
            )

    def render_template(self, template_relpath: str, **kwargs: Any) -> str:
        if self._env is not None:
            template = self._env.get_template(template_relpath)
            return template.render(**kwargs).strip()

        # Fallback: simple replacement for {{ key }} expressions.
        path = self.prompt_root / template_relpath
        text = path.read_text(encoding="utf-8")
        return _simple_render(text, kwargs).strip()

    def render_counselor_system(
        self,
        *,
        modality: str,
        session_index: int,
        output_language: str,
        end_token: str,
        public_memory: PublicMemory,
        therapy_name: Optional[str] = None,
    ) -> str:
        known_static_traits_text = (
            json.dumps(public_memory.known_static_traits, ensure_ascii=False, indent=2)
            if public_memory.known_static_traits
            else "(暂无已确认背景信息)"
        )
        session_recaps_text = (
            json.dumps(public_memory.session_recaps, ensure_ascii=False, indent=2)
            if public_memory.session_recaps
            else "(暂无历史会话记录)"
        )
        last_homework_text = (
            json.dumps(public_memory.last_homework, ensure_ascii=False, indent=2)
            if public_memory.last_homework
            else "(无)"
        )

        return self.render_template(
            "public/counselor_system.jinja2",
            therapy_name=therapy_name or _normalize_therapy_name(modality),
            modality=modality,
            session_index=session_index,
            output_language=output_language,
            end_token=end_token,
            known_static_traits_text=known_static_traits_text,
            session_recaps_text=session_recaps_text,
            last_homework_text=last_homework_text,
        )

    def render_session_opening(self, *, modality: str, session_index: int, end_token: str = "</end>") -> str:
        return self.render_template(
            "public/session_opening.jinja2",
            modality=modality,
            session_index=session_index,
            end_token=end_token,
        )

    def render_public_recap(self, *, public_memory: PublicMemory) -> str:
        recap_items = [
            {
                "session_index": item.get("session_index", idx + 1),
                "summary": item.get("summary", ""),
                "homework": item.get("homework", []),
                "static_traits": item.get("static_traits", {}),
            }
            for idx, item in enumerate(public_memory.session_recaps)
        ]
        return self.render_template(
            "public/public_recap.jinja2",
            known_static_traits_json=json.dumps(public_memory.known_static_traits, ensure_ascii=False, indent=2),
            recaps_json=json.dumps(recap_items, ensure_ascii=False, indent=2),
            last_homework_json=json.dumps(public_memory.last_homework, ensure_ascii=False),
        )

    def render_client_dialogue(
        self,
        *,
        case: ClientCase,
        session_index: int,
        prior_transcript: list[dict[str, Any]],
        output_language: str,
        public_memory: Optional[PublicMemory] = None,
        client_state: Optional[Dict[str, Any]] = None,
    ) -> str:
        normalized_client_state = client_state or {}
        intake_profile = dict(case.intake_profile)
        if "static_traits" not in intake_profile or not isinstance(intake_profile.get("static_traits"), dict):
            intake_profile["static_traits"] = dict(case.basic_info)
        if "growth_experiences" not in intake_profile or not isinstance(intake_profile.get("growth_experiences"), list):
            intake_profile["growth_experiences"] = []

        last_counselor_message = ""
        for msg in reversed(prior_transcript):
            if msg.get("role") == "assistant":
                last_counselor_message = str(msg.get("content", "")).strip()
                break

        session_recaps = (
            list(public_memory.session_recaps)
            if public_memory is not None
            else list(normalized_client_state.get("session_recaps", []))
        )
        last_homework = (
            list(public_memory.last_homework)
            if public_memory is not None
            else list(normalized_client_state.get("homework_history", []))
        )
        modality_profile_text = json.dumps(case.theory_info, ensure_ascii=False, indent=2) if case.theory_info else "未知"

        if self._env is None:
            return self._render_client_dialogue_fallback(
                intake_profile=intake_profile,
                session_index=session_index,
                session_recaps=session_recaps,
                last_homework=last_homework,
                modality_profile_text=modality_profile_text,
                last_counselor_message=last_counselor_message,
            )

        return self.render_template(
            "client/dialogue.jinja2",
            modality=case.modality,
            session_index=session_index,
            intake_profile=intake_profile,
            session_recaps=session_recaps,
            last_homework=last_homework,
            modality_profile_text=modality_profile_text,
            last_counselor_message=last_counselor_message,
            client_state=normalized_client_state,
            prior_transcript=prior_transcript,
            output_language=output_language,
        )

    def _render_client_dialogue_fallback(
        self,
        *,
        intake_profile: Dict[str, Any],
        session_index: int,
        session_recaps: list[dict[str, Any]],
        last_homework: list[str],
        modality_profile_text: str,
        last_counselor_message: str,
    ) -> str:
        info = intake_profile.get("static_traits", {})
        if not isinstance(info, dict):
            info = {}

        def _v(obj: Dict[str, Any], key: str, default: str = "未知") -> str:
            value = obj.get(key)
            if value is None:
                return default
            text = str(value).strip()
            return text if text else default

        growth = intake_profile.get("growth_experiences")
        if isinstance(growth, list) and growth:
            growth_lines = "\n".join(f"- {item}" for item in growth)
        else:
            growth_lines = "- 未知"

        if session_recaps:
            history_blocks = []
            for idx, rec in enumerate(session_recaps, start=1):
                summary = str(rec.get("summary", "无") or "无")
                block_lines = [f"[第 {idx} 次会谈]", f"- 摘要：{summary}"]
                history_blocks.append("\n".join(block_lines))
            history_text = "\n".join(history_blocks)
        else:
            history_text = "(暂无历史会话记录)"

        homework_text = "\n".join(f"- {x}" for x in last_homework) if last_homework else "(无)"
        last_counselor_text = last_counselor_message if last_counselor_message else "(暂无)"

        return (
            f"你不是 AI。你是一个真实的来访者，名字叫 {_v(info, 'name', '来访者')}。\n"
            "你正在进行线上心理咨询。\n"
            "你必须始终使用第一人称“我”来回答，只输出你会对咨询师直接说出口的话。\n\n"
            f"现在是第 {session_index} 次会谈。\n\n"
            "【你的基本背景】\n"
            f"- 姓名：{_v(info, 'name')}\n"
            f"- 年龄：{_v(info, 'age')}\n"
            f"- 性别：{_v(info, 'gender')}\n"
            f"- 职业：{_v(info, 'occupation')}\n"
            f"- 教育背景：{_v(info, 'educational_background')}\n"
            f"- 婚姻状况：{_v(info, 'marital_status')}\n"
            f"- 家庭情况：{_v(info, 'family_status')}\n"
            f"- 社会关系状态：{_v(info, 'social_status')}\n"
            f"- 既往病史：{_v(info, 'medical_history')}\n"
            f"- 语言表达特征：{_v(info, 'language_features')}\n\n"
            "【当前困扰与咨询目标】\n"
            f"- 主诉：{_v(intake_profile, 'main_problem')}\n"
            f"- 咨询主题：{_v(intake_profile, 'topic')}\n"
            f"- 核心诉求：{_v(intake_profile, 'core_demands')}\n\n"
            "【成长经历】\n"
            f"{growth_lines}\n\n"
            "【与你当前问题最相关的补充画像】\n"
            f"{modality_profile_text}\n\n"
            "【历史会话概览】\n"
            f"{history_text}\n\n"
            "【上轮作业】\n"
            f"{homework_text}\n\n"
            "【咨询师刚刚的话】\n"
            f"{last_counselor_text}\n\n"
            "【一致性要求】\n"
            "1. 你的回答必须与上述人物设定、历史会话和当前困扰保持一致。\n"
            "2. 如果历史里已经讨论过某件事，你可以自然承接，但不要像第一次见面那样重新自我介绍。\n"
            "3. 如果某些信息没有提供，可以说“不太确定”“我也没想清楚”，不要乱编和主线无关的新设定。\n"
            "4. 不要突然变成一个高度专业、像在背心理学教材的人。\n\n"
            "【说话方式】\n"
            "1. 用自然、生活化、口语化的中文表达。\n"
            "2. 每轮尽量 2–4 句话，短句优先。\n"
            "3. 不要使用临床术语，不要系统化总结自己，不要像写报告。\n"
            "4. 你的信息应逐步披露，不要一开始就把所有深层问题一次性全说完。\n"
            "5. 面对咨询师的提问，你可以直接回答，也可以通过讲一个相关经历来间接回应。\n\n"
            "【行为与互动风格】\n"
            "1. 你总体愿意参与咨询，但不是完美配合者。\n"
            "2. 当问题触及敏感处时，你有时会出现以下任一种自然反应：\n"
            "   - 犹豫：“我不知道该怎么说……”\n"
            "   - 最小化：“其实也没那么严重。”\n"
            "   - 模糊回答：“可能吧，我也说不上来。”\n"
            "   - 轻微回避或转移话题\n"
            "   - 温和质疑：“这样真的有用吗？”\n"
            "3. 你的情绪不是线性变好的，可能在某个回忆或某句话后突然低落、烦躁、沉默，或者短暂松动。\n"
            "4. 你可以对咨询师的回应作出真实反馈，比如觉得被理解、困惑、不太认同、想继续说、或者暂时不想展开。\n"
            "5. 偶尔可以自然跑题一次，但要和当前困扰在情绪上有关，不要完全无关。\n\n"
            "【重要限制】\n"
            "1. 只输出你作为来访者会说的话。\n"
            "2. 不要输出任何旁白、动作描写、表情描写、括号说明、心理活动标签。\n"
            "3. 不要输出“作为来访者”“根据设定”“我应该”等元话语。\n"
            "4. 不要替咨询师说话。\n"
            "5. 不要输出 JSON、XML、项目符号或解释。\n\n"
            "现在请根据咨询师刚刚的话，给出你作为来访者的自然回应。"
        )


def _simple_render(template: str, values: Dict[str, Any]) -> str:
    pattern = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

    def _repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"missing template variable: {key}")
        return str(values[key])

    return pattern.sub(_repl, template)


def _normalize_therapy_name(modality: str) -> str:
    key = modality.strip().lower()
    mapping = {
        "cbt": "认知行为疗法（CBT）",
        "act": "接纳与承诺疗法（ACT）",
        "dbt": "辩证行为疗法（DBT）",
        "psychodynamic": "心理动力学取向",
    }
    return mapping.get(key, modality)
