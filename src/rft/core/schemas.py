"""Typed runtime configuration for the RFT module."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


class RFTConfigValidationError(ValueError):
    """Raised when RFT runtime config is invalid."""


def _ensure_positive_int(name: str, value: int) -> int:
    if value <= 0:
        raise RFTConfigValidationError(f"{name} must be > 0, got {value}")
    return value


@dataclass(frozen=True)
class RFTRuntimeConfig:
    rollout_n: int = 8
    rollout_concurrency: int = 8
    reward_method_concurrency: int = 8
    reward_api_concurrency: int = 64
    reward_api_rps: Optional[int] = None
    reward_api_rps_period: float = 1.0
    reward_api_key: Optional[str] = None
    reward_api_base_url: Optional[str] = None
    reward_api_model: Optional[str] = None
    keep_all_rollout_transcripts: bool = True
    method_by_modality: Optional[Dict[str, List[str]]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RFTRuntimeConfig":
        cfg = cls(
            rollout_n=int(data.get("rollout_n", 8)),
            rollout_concurrency=int(data.get("rollout_concurrency", 8)),
            reward_method_concurrency=int(data.get("reward_method_concurrency", 8)),
            reward_api_concurrency=int(data.get("reward_api_concurrency", 64)),
            reward_api_rps=int(data["reward_api_rps"]) if data.get("reward_api_rps") is not None else None,
            reward_api_rps_period=float(data.get("reward_api_rps_period", 1.0)),
            reward_api_key=data.get("reward_api_key"),
            reward_api_base_url=data.get("reward_api_base_url"),
            reward_api_model=data.get("reward_api_model"),
            keep_all_rollout_transcripts=bool(data.get("keep_all_rollout_transcripts", True)),
            method_by_modality=_normalize_method_map(data.get("method_by_modality")),
        )
        return cfg.validated()

    def validated(self) -> "RFTRuntimeConfig":
        _ensure_positive_int("rollout_n", self.rollout_n)
        _ensure_positive_int("rollout_concurrency", self.rollout_concurrency)
        _ensure_positive_int("reward_method_concurrency", self.reward_method_concurrency)
        _ensure_positive_int("reward_api_concurrency", self.reward_api_concurrency)
        if self.reward_api_rps is not None:
            _ensure_positive_int("reward_api_rps", self.reward_api_rps)
        if self.reward_api_rps_period <= 0:
            raise RFTConfigValidationError("reward_api_rps_period must be > 0")
        return self

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _normalize_method_map(value: Any) -> Optional[Dict[str, List[str]]]:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise RFTConfigValidationError(f"method_by_modality must be a mapping, got {type(value)!r}")
    normalized: Dict[str, List[str]] = {}
    for key, methods in value.items():
        if methods is None:
            normalized[str(key).strip().lower()] = []
            continue
        if isinstance(methods, str):
            normalized[str(key).strip().lower()] = [item.strip() for item in methods.split(",") if item.strip()]
            continue
        if not isinstance(methods, list):
            raise RFTConfigValidationError(
                f"method_by_modality[{key!r}] must be list or comma-separated string, got {type(methods)!r}"
            )
        normalized[str(key).strip().lower()] = [str(item).strip() for item in methods if str(item).strip()]
    return normalized
