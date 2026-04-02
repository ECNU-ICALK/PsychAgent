"""Core evaluation abstractions shared by all eval methods."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import json
import os


class EvaluationMethod(ABC):
    """Base class for all eval methods.

    The default `chat_api` compatibility layer keeps legacy method code unchanged.
    """

    @staticmethod
    def _supports_json_schema(gpt_api: Any) -> bool:
        force_json_object = os.getenv("CHAT_FORCE_JSON_OBJECT", "").strip().lower() in {"1", "true", "yes"}
        if force_json_object:
            return False

        model_name = str(getattr(gpt_api, "model", "") or "").lower()
        if "deepseek" in model_name:
            return False
        return True

    def _normalize_response_format(self, gpt_api: Any, response_format: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not response_format or not isinstance(response_format, dict):
            return response_format
        if response_format.get("type") == "json_schema" and not self._supports_json_schema(gpt_api):
            return {"type": "json_object"}
        return response_format

    @staticmethod
    def _extract_json_object(text: str) -> str:
        candidate = text.strip()
        left = candidate.find("{")
        right = candidate.rfind("}")
        if left != -1 and right != -1 and left < right:
            return candidate[left : right + 1].strip()
        return candidate

    async def chat_api(
        self,
        gpt_api,
        messages: List[Dict[str, Any]],
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """统一的模型调用入口：兼容不同后端的 JSON 限制并做一次 JSON 兜底修复。"""
        normalized_format = self._normalize_response_format(gpt_api, response_format)

        call_kwargs: Dict[str, Any] = {"response_format": normalized_format}
        if normalized_format is not None:
            call_kwargs["temperature"] = 0

        last_error: Optional[Exception] = None
        for attempt in range(2):
            result = await gpt_api.chat_text(messages=messages, **call_kwargs)
            candidate = self._extract_json_object(result)
            try:
                parsed = json.loads(candidate)
                if not isinstance(parsed, dict):
                    raise ValueError("Top-level JSON must be an object")
                return candidate
            except Exception as exc:
                last_error = exc

            messages = [
                {
                    "role": "system",
                    "content": "你是一个严格的 JSON 修复器。只返回合法 JSON 对象文本。",
                },
                {
                    "role": "user",
                    "content": candidate,
                },
            ]
            call_kwargs["response_format"] = {"type": "json_object"}
            call_kwargs["temperature"] = 0

        raise RuntimeError(f"Model output is not valid JSON after retry: {last_error}") from last_error

    @abstractmethod
    async def evaluate(self, gpt_api, dialogue: Any, profile: dict | None = None) -> Dict[str, float]:
        raise NotImplementedError

    def get_name(self) -> str:
        return self.__class__.__name__
