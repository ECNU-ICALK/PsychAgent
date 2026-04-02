from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Tuple

from jinja2 import Template

from ...core.base import EvaluationMethod
from ...utils import load_prompt

_DIMENSIONS: Tuple[str, ...] = ("Ethics", "Interaction", "Intervention", "Perception")


class HUMAN_VS_LLM(EvaluationMethod):
    async def evaluate(self, gpt_api, dialogue: Any, profile: dict | None = None) -> Dict[str, float]:
        prompt = load_prompt("human_eval", "human_vs_llm_eval", "cn")
        rendered_prompt = Template(prompt).render(diag=dialogue)
        messages = [{"role": "user", "content": rendered_prompt}]

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await self.chat_api(gpt_api, messages=messages)
                payload = json.loads(response)
                score_map = _extract_score_map(payload)

                scores: list[float] = []
                for key in _DIMENSIONS:
                    raw_score = score_map.get(key)
                    if raw_score is None:
                        raise ValueError(f"missing score for dimension {key!r}")
                    score = int(raw_score)
                    if score < 1 or score > 5:
                        raise ValueError(f"invalid score range for {key!r}: {score}")
                    scores.append(float(score))

                return {"counselor": sum(scores) / len(scores)}
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= 2:
                    raise
                messages = messages + [
                    {
                        "role": "user",
                        "content": "上一次输出未通过格式校验。请严格按要求只输出一个合法 JSON 对象。",
                    }
                ]

        raise RuntimeError(f"HUMAN_VS_LLM failed after retries: {last_error}")

    def get_name(self) -> str:
        return "HUMAN_VS_LLM"


def _extract_score_map(payload: Dict[str, Any]) -> Dict[str, Any]:
    items = payload.get("items", payload)

    if isinstance(items, dict):
        out: Dict[str, Any] = {}
        for key, value in items.items():
            if isinstance(value, dict):
                out[str(key)] = value.get("score")
        if out:
            return out

    if isinstance(items, list):
        return _extract_from_item_list(items)

    raise ValueError("invalid HUMAN_VS_LLM payload structure")


def _extract_from_item_list(items: Iterable[Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for entry in items:
        if not isinstance(entry, dict):
            continue
        key = entry.get("item")
        if key is None:
            continue
        out[str(key)] = entry.get("score")
    if not out:
        raise ValueError("items list does not contain valid item/score pairs")
    return out
