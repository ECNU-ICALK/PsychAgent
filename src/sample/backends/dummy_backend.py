"""Dummy backend for dry-run and tests."""

from __future__ import annotations

import asyncio
from typing import List

from .base import Message


class DummyBackend:
    """Deterministic text backend that can emit an end token."""

    def __init__(self, *, default_end_after_turn: int = 2) -> None:
        self._default_end_after_turn = default_end_after_turn

    async def chat_text(self, messages: List[Message], **kwargs: object) -> str:
        await asyncio.sleep(0)
        end_after_turn = int(kwargs.get("dummy_end_after_turn", self._default_end_after_turn))
        end_token = str(kwargs.get("end_token", "</end>"))
        output_language = str(kwargs.get("output_language", "中文"))
        is_chinese = ("中" in output_language) or output_language.lower().startswith("zh")
        if messages:
            system_text = str(messages[0].get("content", ""))
            if "来访者模拟器" in system_text or "client simulator" in system_text.lower():
                if is_chinese:
                    return "我最近还是会因为收容所那件事很焦虑，也挺自责的。你这样问让我愿意继续说下去。"
                return (
                    "I still get anxious and self-critical about what happened at the shelter. "
                    "Your question helps me keep talking."
                )
            if "共享会话总结器" in system_text or "shared summarizer" in system_text.lower():
                if is_chinese:
                    return (
                        '{'
                        '"summary":"本次会谈围绕来访者当前困扰展开，咨询师给出了下一步建议。",'
                        '"homework":["本周记录一次触发情绪的情境，并写下当时的想法与感受。"],'
                        '"static_traits":{}'
                        '}'
                    )
                return (
                    '{'
                    '"summary":"The session focused on current distress and a practical next step.",'
                    '"homework":["Track one trigger this week and note thoughts and feelings."],'
                    '"static_traits":{}'
                    '}'
                )

        counselor_turn = sum(1 for m in messages if m.get("role") == "assistant") + 1
        last_user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user = msg.get("content", "")
                break

        # Opening generation path: avoid echoing meta task instructions.
        if counselor_turn == 1 and ("开场白" in last_user or "session opening" in last_user.lower()):
            if is_chinese:
                return "欢迎你来。开始前我想先听听，你这段时间最困扰你的是什么？我们也可以一起定一个今天想聚焦的小目标。"
            return (
                "Welcome. Before we start, I'd like to hear what has felt most difficult lately, "
                "and we can set one small focus for today."
            )

        if counselor_turn >= end_after_turn:
            if is_chinese:
                return f"我听到你这段时间确实有在努力，我们今天先收在这里。{end_token}"
            return f"I hear your progress. Let's pause here for today. {end_token}"

        clipped = last_user.replace("\n", " ")[:140]
        if is_chinese:
            return f"谢谢你愿意说这些。我听到你刚才提到“{clipped}”。我们可以先一起想一个这周可执行的小步骤。"
        return f"Thanks for sharing. I heard: '{clipped}'. Let's explore one concrete coping step for this week."
