"""Backend protocol and common backend errors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol


Message = Dict[str, str]


class ModelBackend(Protocol):
    """OpenAI-style text chat backend."""

    async def chat_text(self, messages: List[Message], **kwargs: object) -> str:
        """Generate plain text output from chat messages."""


@dataclass
class BackendSettings:
    model: str
    temperature: float
    max_tokens: int
    timeout_sec: int
    max_retries: int
    retry_sleep_sec: float
    base_url: str = ""
    api_key: Optional[str] = None
    verify_ssl: bool = True


class EmptyResponseError(RuntimeError):
    """Raised when model output is empty and should be retried."""


class BackendHTTPError(RuntimeError):
    """Raised for backend HTTP/API failures."""
