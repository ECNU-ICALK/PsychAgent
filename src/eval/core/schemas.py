"""Typed configs and data structures for evaluation orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = [
    "ConfigValidationError",
    "EvalRuntimeConfig",
    "MethodExecution",
    "SessionRunResult",
    "EvaluationSummary",
]

ALLOWED_INPUT_FORMATS = {"auto", "eval_case", "sample"}


class ConfigValidationError(ValueError):
    """Raised when eval runtime config is invalid."""


def _ensure_positive_int(name: str, value: int) -> int:
    if value <= 0:
        raise ConfigValidationError(f"{name} must be > 0, got {value}")
    return value


def _ensure_non_negative_int(name: str, value: int) -> int:
    if value < 0:
        raise ConfigValidationError(f"{name} must be >= 0, got {value}")
    return value

@dataclass(frozen=True)
class EvalRuntimeConfig:
    data_root: Path
    output_root: Path
    input_format: str = "auto"
    api_key: Optional[str] = None
    api_base_url: Optional[str] = None
    api_model: str = "gemini-3-flash-preview"
    language: str = "cn"
    method_concurrency: int = 8
    file_concurrency: int = 8
    api_concurrency: int = 64
    api_rps: Optional[int] = None
    api_rps_period: float = 1.0
    resume: bool = True
    overwrite: bool = False
    case_limit: Optional[int] = None
    modalities: Optional[List[str]] = None
    method_names: Optional[List[str]] = None
    selected_files: Optional[List[str]] = None
    supported_modalities: Optional[List[str]] = None
    method_by_modality: Optional[Dict[str, List[str]]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvalRuntimeConfig":
        return cls(
            data_root=Path(data["data_root"]) if "data_root" in data else Path("data"),
            output_root=Path(data["output_root"]) if "output_root" in data else Path("eval_outputs"),
            input_format=str(data.get("input_format", "auto")),
            api_key=data.get("api_key"),
            api_base_url=data.get("api_base_url"),
            api_model=str(data.get("api_model", "gemini-3-flash-preview")),
            language=str(data.get("language", "cn")),
            method_concurrency=_ensure_positive_int("method_concurrency", int(data.get("method_concurrency", 8))),
            file_concurrency=_ensure_positive_int("file_concurrency", int(data.get("file_concurrency", 8))),
            api_concurrency=_ensure_positive_int("api_concurrency", int(data.get("api_concurrency", 64))),
            api_rps=data.get("api_rps"),
            api_rps_period=float(data.get("api_rps_period", 1.0)),
            resume=bool(data.get("resume", True)),
            overwrite=bool(data.get("overwrite", False)),
            case_limit=data.get("case_limit"),
            modalities=_normalize_str_list(data.get("modalities")),
            method_names=_normalize_str_list(data.get("method_names")),
            selected_files=_normalize_str_list(data.get("selected_files")),
            supported_modalities=_normalize_str_list(data.get("supported_modalities")),
            method_by_modality=_normalize_method_map(data.get("method_by_modality")),
        ).validated()

    def validated(self) -> "EvalRuntimeConfig":
        _ensure_positive_int("method_concurrency", self.method_concurrency)
        _ensure_positive_int("file_concurrency", self.file_concurrency)
        _ensure_positive_int("api_concurrency", self.api_concurrency)
        if self.api_rps is not None:
            _ensure_positive_int("api_rps", int(self.api_rps))
        if self.api_rps_period <= 0:
            raise ConfigValidationError("api_rps_period must be > 0")
        if self.case_limit is not None:
            _ensure_positive_int("case_limit", int(self.case_limit))
        if self.resume and self.overwrite:
            raise ConfigValidationError("resume and overwrite cannot both be true")
        if not self.output_root:
            raise ConfigValidationError("output_root must be non-empty")
        if self.method_concurrency <= 0:
            raise ConfigValidationError("method_concurrency must be > 0")
        if self.file_concurrency <= 0:
            raise ConfigValidationError("file_concurrency must be > 0")
        if not self.api_model.strip():
            raise ConfigValidationError("api_model must be non-empty")
        if self.input_format not in ALLOWED_INPUT_FORMATS:
            allowed = ", ".join(sorted(ALLOWED_INPUT_FORMATS))
            raise ConfigValidationError(f"input_format must be one of {{{allowed}}}, got {self.input_format!r}")
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_root": str(self.data_root),
            "output_root": str(self.output_root),
            "input_format": self.input_format,
            "api_key": self.api_key,
            "api_base_url": self.api_base_url,
            "api_model": self.api_model,
            "language": self.language,
            "method_concurrency": self.method_concurrency,
            "file_concurrency": self.file_concurrency,
            "api_concurrency": self.api_concurrency,
            "api_rps": self.api_rps,
            "api_rps_period": self.api_rps_period,
            "resume": self.resume,
            "overwrite": self.overwrite,
            "case_limit": self.case_limit,
            "modalities": list(self.modalities or []),
            "method_names": list(self.method_names or []),
            "selected_files": list(self.selected_files or []),
            "supported_modalities": list(self.supported_modalities or []),
            "method_by_modality": dict(self.method_by_modality or {}),
        }


@dataclass
class MethodExecution:
    method_name: str
    status: str
    scores: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None
    traceback: Optional[str] = None
    raw_model_outputs: List[str] = field(default_factory=list)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    thread_name: Optional[str] = None
    model_name: Optional[str] = None


@dataclass
class SessionRunResult:
    case_name: str
    case_number: str
    case_path: str
    session_number: int
    session_file: str
    status: str
    evaluation_results: Dict[str, Dict[str, Any]]
    method_status: Dict[str, str]
    method_errors: Dict[str, Dict[str, Any]]
    missing_methods: List[str]
    scale_results_dir: str | None
    completed_at: Optional[str] = None
    model_name: Optional[str] = None
    thread_id: Optional[str] = None


@dataclass
class EvaluationSummary:
    total_files: int = 0
    completed: int = 0
    failed: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)


def _normalize_str_list(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if not isinstance(value, list):
        raise ConfigValidationError(f"expected list or comma-separated string, got {type(value)!r}")
    normalized: List[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                normalized.append(text)
        else:
            normalized.append(str(item))
    return normalized


def _normalize_method_map(value: Any) -> Optional[Dict[str, List[str]]]:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConfigValidationError(f"method_by_modality must be a mapping, got {type(value)!r}")
    normalized: Dict[str, List[str]] = {}
    for key, methods in value.items():
        normalized[str(key)] = _normalize_str_list(methods) or []
    return normalized
