"""OpenAI-style API backend implementations."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

try:
    import httpx
except ImportError:  # pragma: no cover - optional dependency guard
    httpx = None  # type: ignore[assignment]

try:
    from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
except ImportError:  # pragma: no cover - optional dependency guard
    AsyncOpenAI = None  # type: ignore[assignment]

    class _OpenAINotInstalledError(Exception):
        pass

    APIConnectionError = _OpenAINotInstalledError  # type: ignore[assignment]
    APIStatusError = _OpenAINotInstalledError  # type: ignore[assignment]
    APITimeoutError = _OpenAINotInstalledError  # type: ignore[assignment]

from .base import BackendHTTPError, BackendSettings, Message
from ..core.retry import FatalBackendError, RetryPolicy, RetryableError, retry_async

INSECURE_CLIENT_BASE_URL = "https://10.140.158.153:1020/dsv3/all/v1"


class OpenAIStyleBackend:
    """Backend for chat-completions compatible HTTP APIs."""

    def __init__(self, settings: BackendSettings, logger: Optional[logging.Logger] = None) -> None:
        self._settings = settings
        self._logger = logger or logging.getLogger(self.__class__.__name__)
        self.client = self._build_client()

    def _build_client(self) -> Any:
        if AsyncOpenAI is None:
            raise FatalBackendError("openai package is required for openai_api backend")

        base_url = self._settings.base_url
        if not base_url:
            base_url = "https://api.openai.com/v1"

        client_kwargs: Dict[str, Any] = {
            "max_retries": 0,
        }

        # For this internal endpoint we must disable TLS verification.
        if self._is_insecure_tls_endpoint(base_url):
            if httpx is None:
                raise FatalBackendError("httpx is required to set verify=False for the configured endpoint")
            http_client = httpx.AsyncClient(verify=False)
            client_kwargs["http_client"] = http_client
            self._logger.warning("Using verify=False for endpoint: %s", base_url)

        return AsyncOpenAI(
            api_key=self._settings.api_key,
            base_url=base_url,
            **client_kwargs,
        )

    async def chat_text(self, messages: List[Message], **kwargs: object) -> str:
        model = str(kwargs.get("model", self._settings.model))
        temperature = float(kwargs.get("temperature", self._settings.temperature))
        max_tokens = int(kwargs.get("max_tokens", self._settings.max_tokens))
        timeout_sec = int(kwargs.get("timeout_sec", self._settings.timeout_sec))

        retry_policy = RetryPolicy(
            max_retries=int(kwargs.get("max_retries", self._settings.max_retries)),
            base_sleep_sec=float(kwargs.get("retry_sleep_sec", self._settings.retry_sleep_sec)),
        )

        async def _call_once() -> str:
            response = await asyncio.wait_for(
                self._async_post_chat(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout_sec=timeout_sec,
                ),
                timeout=timeout_sec,
            )
            response_json = self._to_response_dict(response)
            text = self._extract_text(response_json).strip()
            if not text:
                raise RetryableError("empty model output")
            return text

        return await retry_async(_call_once, retry_policy, logger=self._logger)

    async def _async_post_chat(
        self,
        *,
        model: str,
        messages: List[Message],
        temperature: float,
        max_tokens: int,
        timeout_sec: int,
    ) -> Any:
        try:
            return await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout_sec,
            )
        except APITimeoutError as exc:
            self._logger.error("backend timeout error: %r", exc)
            raise RetryableError(f"timeout: {exc!r}") from exc
        except APIConnectionError as exc:
            self._logger.error("backend connection error: %r", exc)
            raise RetryableError(f"connection error: {exc!r}") from exc
        except APIStatusError as exc:
            status = int(getattr(exc, "status_code", 0) or 0)
            body = ""
            try:
                resp_obj = getattr(exc, "response", None)
                if resp_obj is not None:
                    body = getattr(resp_obj, "text", "") or ""
            except Exception:
                body = ""
            self._logger.error("backend http error status=%s body=%s", status, body)
            if status in {408, 409, 425, 429, 500, 502, 503, 504}:
                raise RetryableError(f"retryable http status {status}") from exc
            raise FatalBackendError(f"fatal http status {status}: {body}") from exc

    @staticmethod
    def _to_response_dict(response: Any) -> Dict[str, Any]:
        if isinstance(response, dict):
            return response
        model_dump = getattr(response, "model_dump", None)
        if callable(model_dump):
            data = model_dump()
            if isinstance(data, dict):
                return data
        raise BackendHTTPError(f"unexpected response type from backend: {type(response)!r}")

    @staticmethod
    def _is_insecure_tls_endpoint(base_url: str) -> bool:
        return base_url.rstrip("/") == INSECURE_CLIENT_BASE_URL.rstrip("/")

    @staticmethod
    def _extract_text(response_json: Dict[str, Any]) -> str:
        choices = response_json.get("choices")
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message", {})
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                chunks = []
                for item in content:
                    if isinstance(item, dict):
                        text = item.get("text") or item.get("content") or ""
                        if text:
                            chunks.append(str(text))
                    elif isinstance(item, str):
                        chunks.append(item)
                return "".join(chunks)

        # Some OpenAI-compatible servers may return a direct output text field.
        output_text = response_json.get("output_text")
        if isinstance(output_text, str):
            return output_text

        raise BackendHTTPError(f"cannot extract text from backend response keys={list(response_json.keys())}")


class OpenAIAPIBackend(OpenAIStyleBackend):
    """Backend for SOTA API models through OpenAI-compatible chat endpoint."""

    def __init__(self, settings: BackendSettings, logger: Optional[logging.Logger] = None) -> None:
        if not settings.base_url:
            settings = BackendSettings(
                model=settings.model,
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
                timeout_sec=settings.timeout_sec,
                max_retries=settings.max_retries,
                retry_sleep_sec=settings.retry_sleep_sec,
                base_url="https://api.openai.com/v1",
                api_key=settings.api_key,
                verify_ssl=settings.verify_ssl,
            )
        super().__init__(settings=settings, logger=logger)
