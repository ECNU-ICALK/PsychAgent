"""Async chat client used by eval methods."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Dict, List, Optional

try:
    from aiolimiter import AsyncLimiter
    from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, RateLimitError
    from tenacity import (
        retry,
        retry_if_exception,
        retry_if_exception_type,
        stop_after_attempt,
        wait_random_exponential,
    )
except ImportError as exc:  # pragma: no cover
    AsyncLimiter = None  # type: ignore[assignment]
    AsyncOpenAI = None  # type: ignore[assignment]
    APIConnectionError = APIStatusError = APITimeoutError = AsyncOpenAI = RateLimitError = None  # type: ignore[assignment]
    retry = retry_if_exception = retry_if_exception_type = stop_after_attempt = wait_random_exponential = None  # type: ignore
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


def _is_retryable_status(exc: Exception) -> bool:
    return isinstance(exc, APIStatusError) and (exc.status_code == 429 or 500 <= exc.status_code < 600)


_RETRY_COND = None
if retry is not None:
    _RETRY_COND = (
        retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError))
        | retry_if_exception(_is_retryable_status)
    )


class EmptyModelResponseError(RuntimeError):
    """Raised when model invocation succeeds but response text is empty."""


class GPT5ChatClient:
    """Small async client wrapper with global concurrency/rate limits + retry policy."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        max_concurrency: int = 64,
        rps: Optional[int] = 60,
        rps_period: float = 1.0,
        default_timeout: float = 300.0,
        model: str = "deepseek-ai/DeepSeek-V3.1-Terminus",
    ) -> None:
        if _IMPORT_ERROR is not None:
            raise RuntimeError("GPT5ChatClient requires dependencies: openai, aiolimiter, tenacity") from _IMPORT_ERROR

        base_url = base_url or os.getenv("CHAT_API_BASE", None)
        api_key = api_key or os.getenv("CHAT_API_KEY", None)
        model = os.getenv("CHAT_MODEL_NAME", None) or model

        if not api_key:
            raise ValueError("api_key must be provided explicitly or via CHAT_API_KEY")
        if not base_url:
            raise ValueError("base_url must be provided explicitly or via CHAT_API_BASE")
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be > 0")
        if rps is not None and rps <= 0:
            raise ValueError("rps must be > 0 or None")
        if rps_period <= 0:
            raise ValueError("rps_period must be > 0")

        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self._sdk = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=default_timeout, max_retries=0)
        self._sem = asyncio.Semaphore(max_concurrency)
        self._limiter = AsyncLimiter(max_rate=rps, time_period=rps_period) if (AsyncLimiter is not None and rps) else None
        self._default_timeout = default_timeout
        self._closed = False

    async def __aenter__(self) -> "GPT5ChatClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # pragma: no cover
        await self.aclose()

    async def aclose(self) -> None:
        if self._closed:
            return

        close_fn = getattr(self._sdk, "aclose", None)
        if callable(close_fn):
            await close_fn()
        else:  # pragma: no cover
            maybe = getattr(self._sdk, "close", None)
            if callable(maybe):
                out = maybe()
                if asyncio.iscoroutine(out):
                    await out
        self._closed = True

    async def _acquire_rate_limit(self) -> None:
        if self._limiter is not None:
            async with self._limiter:
                pass

    @staticmethod
    def _strip_fences(text: str) -> str:
        if not isinstance(text, str):
            return text
        matched = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        return (matched.group(1) if matched else text).strip()

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        *,
        response_format: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        max_retries: int = 6,
        **extra_kwargs: Any,
    ):
        if _RETRY_COND is None:
            raise RuntimeError("tenacity decorator missing; install required dependency")

        @retry(
            retry=_RETRY_COND,
            stop=stop_after_attempt(max_retries),
            wait=wait_random_exponential(min=1, max=60),
            reraise=True,
        )
        async def _do_call():
            if self._closed:
                raise RuntimeError("GPT5ChatClient is closed")
            await self._acquire_rate_limit()
            async with self._sem:
                return await self._sdk.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format=response_format,
                    timeout=timeout or self._default_timeout,
                    **extra_kwargs,
                )

        return await _do_call()

    async def chat_text(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        response = await self.chat_completion(messages=messages, **kwargs)
        if not response.choices or not getattr(response.choices[0], "message", None):
            raise RuntimeError(f"Unexpected OpenAI response shape: {response}")
        content = response.choices[0].message.content or ""
        text = self._strip_fences(content).strip()
        if not text:
            raise EmptyModelResponseError("Model returned empty response text")
        return text
