"""Programmatic reward evaluation API reused by ``rft`` and other modules."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .core import GPT5ChatClient
from .core.base import EvaluationMethod
from .methods import METHOD_REGISTRY


DEFAULT_REWARD_METHOD_BY_MODALITY: Dict[str, List[str]] = {
    "bt": ["PANAS", "RRO", "SRS", "Custom_Dim", "HTAIS", "WAI", "MITI", "STAI"],
    "cbt": ["PANAS", "RRO", "SRS", "Custom_Dim", "HTAIS", "WAI", "CTRS", "BDI_II"],
    "pmt": ["PANAS", "RRO", "SRS", "Custom_Dim", "HTAIS", "WAI", "EFT_TFS", "SFBT"],
    "het": ["PANAS", "RRO", "SRS", "Custom_Dim", "HTAIS", "WAI", "TES", "CCT"],
    "pdt": ["PANAS", "RRO", "SRS", "Custom_Dim", "HTAIS", "WAI", "PSC", "IPO"],
}


@dataclass(frozen=True)
class RewardEvaluationResult:
    counselor: Dict[str, float]
    client: Dict[str, float]
    method_status: Dict[str, str]
    method_errors: Dict[str, str]
    missing_methods: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "counselor": dict(self.counselor),
            "client": dict(self.client),
            "method_status": dict(self.method_status),
            "method_errors": dict(self.method_errors),
            "missing_methods": list(self.missing_methods),
        }


class RewardEvaluator:
    """Run eval methods directly and expose reward-ready counselor/client scores."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        api_model: str = "gemini-3-flash-preview",
        api_concurrency: int = 64,
        api_rps: Optional[int] = None,
        api_rps_period: float = 1.0,
        method_concurrency: int = 8,
        method_by_modality: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        self._client = GPT5ChatClient(
            api_key=api_key,
            base_url=api_base_url,
            model=api_model,
            max_concurrency=api_concurrency,
            rps=api_rps,
            rps_period=api_rps_period,
        )
        self._method_concurrency = max(1, int(method_concurrency))
        self._method_by_modality = {
            str(key).strip().lower(): list(value)
            for key, value in (method_by_modality or DEFAULT_REWARD_METHOD_BY_MODALITY).items()
        }
        self._method_registry = _build_method_by_effective_name()

    async def close(self) -> None:
        await self._client.aclose()

    async def evaluate_dialogue(
        self,
        *,
        modality: str,
        dialogue: Any,
        profile: Optional[Dict[str, Any]] = None,
        method_names: Optional[Sequence[str]] = None,
    ) -> RewardEvaluationResult:
        method_list = self._resolve_method_names(modality, method_names)
        if not method_list:
            return RewardEvaluationResult(
                counselor={},
                client={},
                method_status={},
                method_errors={},
                missing_methods=[],
            )

        formatted_dialogue = _format_dialogue(dialogue)
        safe_profile = profile if isinstance(profile, dict) else {}

        semaphore = asyncio.Semaphore(self._method_concurrency)
        tasks: List[asyncio.Task[tuple[str, str, Dict[str, float], Optional[str]]]] = []

        async def _run_one(name: str, method: EvaluationMethod) -> tuple[str, str, Dict[str, float], Optional[str]]:
            async with semaphore:
                try:
                    scores = await method.evaluate(self._client, formatted_dialogue, safe_profile)
                    if not isinstance(scores, dict):
                        raise TypeError(f"{name}.evaluate() returned non-dict: {type(scores)!r}")
                    normalized_scores: Dict[str, float] = {}
                    for key, value in scores.items():
                        if isinstance(value, (int, float)):
                            normalized_scores[str(key)] = float(value)
                    return name, "completed", normalized_scores, None
                except Exception as exc:  # noqa: BLE001
                    return name, "failed", {}, str(exc)

        for method_name in method_list:
            cls = self._method_registry.get(method_name)
            if cls is None:
                tasks.append(asyncio.create_task(_missing_method_task(method_name)))
                continue
            tasks.append(asyncio.create_task(_run_one(method_name, cls())))

        counselor_scores: Dict[str, float] = {}
        client_scores: Dict[str, float] = {}
        method_status: Dict[str, str] = {}
        method_errors: Dict[str, str] = {}
        missing_methods: List[str] = []

        for task in asyncio.as_completed(tasks):
            method_name, status, scores, error = await task
            method_status[method_name] = status
            if status != "completed":
                if error:
                    method_errors[method_name] = error
                missing_methods.append(method_name)
                continue

            for dim_name, value in scores.items():
                dim_key = dim_name.strip().lower()
                if dim_key == "counselor":
                    counselor_scores[method_name] = value
                elif dim_key == "client":
                    client_scores[method_name] = value

        return RewardEvaluationResult(
            counselor=counselor_scores,
            client=client_scores,
            method_status=method_status,
            method_errors=method_errors,
            missing_methods=missing_methods,
        )

    def _resolve_method_names(
        self,
        modality: str,
        method_names: Optional[Sequence[str]],
    ) -> List[str]:
        if method_names:
            return _dedupe([str(name) for name in method_names if str(name).strip()])
        key = str(modality).strip().lower()
        return _dedupe(self._method_by_modality.get(key, []))


async def _missing_method_task(method_name: str) -> tuple[str, str, Dict[str, float], Optional[str]]:
    await asyncio.sleep(0)
    return method_name, "failed", {}, "method_not_found"


def _build_method_by_effective_name() -> Dict[str, Any]:
    by_name: Dict[str, Any] = {}
    for key, cls in METHOD_REGISTRY.items():
        key_text = str(key)
        by_name[key_text] = cls
        by_name.setdefault(key_text.lower(), cls)
        by_name.setdefault(key_text.upper(), cls)
        by_name[cls.__name__] = cls
        by_name.setdefault(cls.__name__.lower(), cls)
        by_name.setdefault(cls.__name__.upper(), cls)
        try:
            effective_name = cls().get_name()
            by_name.setdefault(effective_name, cls)
            by_name.setdefault(str(effective_name).lower(), cls)
            by_name.setdefault(str(effective_name).upper(), cls)
        except Exception:
            continue
    return by_name


def _dedupe(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _format_dialogue(dialogue: Any) -> str:
    if isinstance(dialogue, str):
        return dialogue.replace("</end>", "").strip()
    if not isinstance(dialogue, list):
        return str(dialogue)

    lines: List[str] = []
    for turn in dialogue:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role", "")).strip().lower()
        if role == "system":
            continue
        content = turn.get("text")
        if content is None:
            content = turn.get("content")
        if content is None:
            continue
        text = str(content).replace("</end>", "").strip()
        if not text:
            continue
        if role in {"assistant", "counselor", "therapist"}:
            lines.append(f"counselor: {text}")
        elif role in {"user", "client", "human"}:
            lines.append(f"client: {text}")
    return "\n".join(lines).strip()
