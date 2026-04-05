"""Core typed schemas used by the PsychAgent standalone sample framework."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import os
from typing import Any, Dict, List, Literal, Optional


class ConfigValidationError(ValueError):
    """Raised when runtime/baseline configuration is invalid."""


def _ensure_enum(name: str, value: str, allowed: set[str]) -> str:
    if value not in allowed:
        raise ConfigValidationError(f"{name} must be one of {sorted(allowed)}, got: {value!r}")
    return value


def _ensure_positive_int(name: str, value: int) -> int:
    if value <= 0:
        raise ConfigValidationError(f"{name} must be > 0, got: {value}")
    return value


def _ensure_non_negative_int(name: str, value: int) -> int:
    if value < 0:
        raise ConfigValidationError(f"{name} must be >= 0, got: {value}")
    return value


@dataclass
class BaselineConfig:
    """Configuration for the counselor model in PsychAgent sample flows."""

    name: str
    family: Literal["sota_api", "specific_llm"] = "specific_llm"
    backend: Literal["openai_api", "dummy"] = "dummy"
    model: str = "default"
    base_url: str = ""
    api_key_env: str = ""
    temperature: float = 0.7
    max_tokens: int = 512
    memory_mode: Literal["raw_history", "public_recap", "rag", "membank", "mem0"] = "public_recap"
    max_sessions: int = 6
    max_counselor_turns: int = 15
    end_token: str = "</end>"
    timeout_sec: int = 60
    max_retries: int = 3
    retry_sleep_sec: float = 1.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaselineConfig":
        cfg = cls(
            name=str(data["name"]),
            family=str(data.get("family", "specific_llm")),
            backend=str(data.get("backend", "dummy")),
            model=str(data.get("model", "default")),
            base_url=str(data.get("base_url", "")),
            api_key_env=str(data.get("api_key_env", "")),
            temperature=float(data.get("temperature", 0.7)),
            max_tokens=int(data.get("max_tokens", 512)),
            memory_mode=str(data.get("memory_mode", "public_recap")),
            max_sessions=int(data.get("max_sessions", 6)),
            max_counselor_turns=int(data.get("max_counselor_turns", 15)),
            end_token=str(data.get("end_token", "</end>")),
            timeout_sec=int(data.get("timeout_sec", 60)),
            max_retries=int(data.get("max_retries", 3)),
            retry_sleep_sec=float(data.get("retry_sleep_sec", 1.0)),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        _ensure_enum("family", self.family, {"sota_api", "specific_llm"})
        _ensure_enum("backend", self.backend, {"openai_api", "dummy"})
        _ensure_enum(
            "memory_mode",
            self.memory_mode,
            {"raw_history", "public_recap", "rag", "membank", "mem0"},
        )
        _ensure_positive_int("max_tokens", self.max_tokens)
        _ensure_positive_int("max_sessions", self.max_sessions)
        _ensure_positive_int("max_counselor_turns", self.max_counselor_turns)
        _ensure_positive_int("timeout_sec", self.timeout_sec)
        _ensure_non_negative_int("max_retries", self.max_retries)
        if self.temperature < 0:
            raise ConfigValidationError("temperature must be >= 0")
        if not self.name.strip():
            raise ConfigValidationError("name must be non-empty")
        if not self.model.strip():
            raise ConfigValidationError("model must be non-empty")
        if not self.end_token.strip():
            raise ConfigValidationError("end_token must be non-empty")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RuntimeConfig:
    """Runtime settings for one PsychAgent run."""

    concurrency: int = 1
    save_dir: str = "sample_outputs"
    resume: bool = True
    overwrite: bool = False
    random_seed: int = 7
    transcript_truncation_strategy: str = "none"
    output_language: str = "中文"
    shared_public_recap_mode: str = "deterministic"

    client_backend: Literal["openai_api", "dummy", "none"] = "none"
    client_model: str = "shared-client-simulator"
    client_base_url: str = ""
    client_api_key_env: str = ""
    client_timeout_sec: int = 60
    client_max_retries: int = 3
    client_retry_sleep_sec: float = 1.0
    client_max_tokens: int = 256
    client_temperature: float = 0.7

    max_sessions: Optional[int] = None
    max_counselor_turns: Optional[int] = None
    end_token: Optional[str] = None

    psychagent_max_turns: int = 45
    psychagent_max_retries: int = 16
    psychagent_retry_sleep_sec: float = 1.0
    psychagent_counselor_system_filename: str = "system.jinja2"

    psychagent_skill_base_dir: str = "assets/skills/sect"
    psychagent_skill_select_prompt_dir: str = "prompts/psychagent/skill/select_skill"
    psychagent_skill_rewrite_prompt_dir: str = "prompts/psychagent/skill/rewrite"
    psychagent_skill_sects: str | List[str] = "all"

    psychagent_embedding_base_url: str = "https://api.siliconflow.cn/v1"
    psychagent_embedding_api_key_env: str = "PSYCHAGENT_EMBEDDING_API_KEY"
    psychagent_embedding_model: str = "BAAI/bge-m3"
    psychagent_embedding_batch_size: int = 64
    psychagent_embedding_max_retries: int = 16
    psychagent_embedding_retry_sleep_sec: float = 0.5
    psychagent_embedding_verify_ssl: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeConfig":
        raw = dict(data)
        runtime_defaults = _runtime_defaults_for_psychagent_library()
        psychagent_skill_sects = raw.get("psychagent_skill_sects", "all")
        if isinstance(psychagent_skill_sects, list):
            psychagent_skill_sects = [str(x) for x in psychagent_skill_sects]
        else:
            psychagent_skill_sects = str(psychagent_skill_sects)

        cfg = cls(
            concurrency=int(raw.get("concurrency", 1)),
            save_dir=str(raw.get("save_dir", "sample_outputs")),
            resume=bool(raw.get("resume", True)),
            overwrite=bool(raw.get("overwrite", False)),
            random_seed=int(raw.get("random_seed", 7)),
            transcript_truncation_strategy=str(raw.get("transcript_truncation_strategy", "none")),
            output_language=str(raw.get("output_language", "中文")),
            shared_public_recap_mode=str(raw.get("shared_public_recap_mode", "deterministic")),
            client_backend=str(raw.get("client_backend", "none")),
            client_model=str(raw.get("client_model", "shared-client-simulator")),
            client_base_url=str(raw.get("client_base_url", "")),
            client_api_key_env=str(raw.get("client_api_key_env", "")),
            client_timeout_sec=int(raw.get("client_timeout_sec", 60)),
            client_max_retries=int(raw.get("client_max_retries", 3)),
            client_retry_sleep_sec=float(raw.get("client_retry_sleep_sec", 1.0)),
            client_max_tokens=int(raw.get("client_max_tokens", 256)),
            client_temperature=float(raw.get("client_temperature", 0.7)),
            max_sessions=int(raw["max_sessions"]) if raw.get("max_sessions") is not None else None,
            max_counselor_turns=int(raw["max_counselor_turns"]) if raw.get("max_counselor_turns") is not None else None,
            end_token=str(raw["end_token"]) if raw.get("end_token") is not None else None,
            psychagent_max_turns=int(raw.get("psychagent_max_turns", 45)),
            psychagent_max_retries=int(raw.get("psychagent_max_retries", 16)),
            psychagent_retry_sleep_sec=float(raw.get("psychagent_retry_sleep_sec", 1.0)),
            psychagent_counselor_system_filename=str(raw.get("psychagent_counselor_system_filename", "system.jinja2")),
            psychagent_skill_base_dir=str(
                raw.get(
                    "psychagent_skill_base_dir",
                    runtime_defaults["psychagent_skill_base_dir"],
                )
            ),
            psychagent_skill_select_prompt_dir=str(
                raw.get(
                    "psychagent_skill_select_prompt_dir",
                    runtime_defaults["psychagent_skill_select_prompt_dir"],
                )
            ),
            psychagent_skill_rewrite_prompt_dir=str(
                raw.get(
                    "psychagent_skill_rewrite_prompt_dir",
                    runtime_defaults["psychagent_skill_rewrite_prompt_dir"],
                )
            ),
            psychagent_skill_sects=psychagent_skill_sects,
            psychagent_embedding_base_url=str(raw.get("psychagent_embedding_base_url", "https://api.siliconflow.cn/v1")),
            psychagent_embedding_api_key_env=str(raw.get("psychagent_embedding_api_key_env", "PSYCHAGENT_EMBEDDING_API_KEY")),
            psychagent_embedding_model=str(raw.get("psychagent_embedding_model", "BAAI/bge-m3")),
            psychagent_embedding_batch_size=int(raw.get("psychagent_embedding_batch_size", 64)),
            psychagent_embedding_max_retries=int(raw.get("psychagent_embedding_max_retries", 16)),
            psychagent_embedding_retry_sleep_sec=float(raw.get("psychagent_embedding_retry_sleep_sec", 0.5)),
            psychagent_embedding_verify_ssl=bool(raw.get("psychagent_embedding_verify_ssl", True)),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        _ensure_positive_int("concurrency", self.concurrency)
        if self.resume and self.overwrite:
            raise ConfigValidationError("resume and overwrite cannot both be true")
        if not self.save_dir.strip():
            raise ConfigValidationError("save_dir must be non-empty")
        _ensure_enum("client_backend", self.client_backend, {"openai_api", "dummy", "none"})
        if self.client_backend != "none" and not self.client_model.strip():
            raise ConfigValidationError("client_model must be non-empty when client backend is enabled")
        if self.client_timeout_sec <= 0:
            raise ConfigValidationError("client_timeout_sec must be > 0")
        _ensure_non_negative_int("client_max_retries", self.client_max_retries)
        _ensure_positive_int("client_max_tokens", self.client_max_tokens)
        if self.client_temperature < 0:
            raise ConfigValidationError("client_temperature must be >= 0")
        if self.max_sessions is not None:
            _ensure_positive_int("max_sessions", self.max_sessions)
        if self.max_counselor_turns is not None:
            _ensure_positive_int("max_counselor_turns", self.max_counselor_turns)
        if self.end_token is not None and not str(self.end_token).strip():
            raise ConfigValidationError("end_token if provided must be non-empty")
        _ensure_positive_int("psychagent_max_turns", self.psychagent_max_turns)
        _ensure_positive_int("psychagent_max_retries", self.psychagent_max_retries)
        if self.psychagent_retry_sleep_sec < 0:
            raise ConfigValidationError("psychagent_retry_sleep_sec must be >= 0")
        if not self.psychagent_counselor_system_filename.strip():
            raise ConfigValidationError("psychagent_counselor_system_filename must be non-empty")
        if not str(self.psychagent_skill_base_dir).strip():
            raise ConfigValidationError("psychagent_skill_base_dir must be non-empty")
        if not str(self.psychagent_skill_select_prompt_dir).strip():
            raise ConfigValidationError("psychagent_skill_select_prompt_dir must be non-empty")
        if not str(self.psychagent_skill_rewrite_prompt_dir).strip():
            raise ConfigValidationError("psychagent_skill_rewrite_prompt_dir must be non-empty")
        _ensure_positive_int("psychagent_embedding_batch_size", self.psychagent_embedding_batch_size)
        _ensure_positive_int("psychagent_embedding_max_retries", self.psychagent_embedding_max_retries)
        if self.psychagent_embedding_retry_sleep_sec < 0:
            raise ConfigValidationError("psychagent_embedding_retry_sleep_sec must be >= 0")
        embedding_env = str(self.psychagent_embedding_api_key_env).strip()
        if not embedding_env:
            raise ConfigValidationError("psychagent_embedding_api_key_env must be non-empty")
        if not os.getenv(embedding_env, "").strip():
            raise ConfigValidationError(
                f"missing embedding api key in environment variable: {embedding_env}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


RUNTIME_DEPRECATED_FIELDS = frozenset(
    {
        "transcript_truncation_strategy",
        "shared_public_recap_mode",
    }
)

RUNTIME_REMOVED_FIELDS = frozenset(
    {
        "summarizer_backend",
        "summarizer_model",
        "summarizer_base_url",
        "summarizer_api_key_env",
        "summarizer_timeout_sec",
        "summarizer_max_retries",
        "summarizer_retry_sleep_sec",
        "summarizer_max_tokens",
        "summarizer_temperature",
        "psychagent_load_library",
        "psychagent_enable_coarse_skill_filter",
        "psychagent_enable_turn_skill_retrieval",
        "psychagent_skill_versions",
    }
)


def runtime_field_statuses() -> Dict[str, str]:
    """Return runtime field status map used by config observability checks.

    Status values:
    - ``active``: field is parsed and consumed by active runtime flow.
    - ``deprecated``: field is parsed for compatibility but currently no-op.
    - ``removed``: historical field, no longer consumed by runtime schema.
    """

    statuses: Dict[str, str] = {}
    for name in RuntimeConfig.__dataclass_fields__:
        statuses[name] = "deprecated" if name in RUNTIME_DEPRECATED_FIELDS else "active"
    for name in sorted(RUNTIME_REMOVED_FIELDS):
        statuses[name] = "removed"
    return statuses


def _runtime_defaults_for_psychagent_library() -> Dict[str, str]:
    return {
        "psychagent_skill_base_dir": "assets/skills/sect",
        "psychagent_skill_select_prompt_dir": "prompts/psychagent/skill/select_skill",
        "psychagent_skill_rewrite_prompt_dir": "prompts/psychagent/skill/rewrite",
    }


@dataclass
class DatasetConfig:
    """Configuration for dataset discovery and case selection."""

    root_data_path: str
    supported_modalities: List[str]
    split: str = "sample"
    max_cases: Optional[int] = None
    max_cases_per_modality: Optional[int] = None
    case_selection_strategy: Literal["sequential", "random"] = "sequential"
    filename_sort_policy: Literal["stem_asc", "stem_desc"] = "stem_asc"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DatasetConfig":
        cfg = cls(
            root_data_path=str(data["root_data_path"]),
            supported_modalities=[str(x) for x in data.get("supported_modalities", [])],
            split=str(data.get("split", "sample")),
            max_cases=int(data["max_cases"]) if data.get("max_cases") is not None else None,
            max_cases_per_modality=(
                int(data["max_cases_per_modality"]) if data.get("max_cases_per_modality") is not None else None
            ),
            case_selection_strategy=str(data.get("case_selection_strategy", "sequential")),
            filename_sort_policy=str(data.get("filename_sort_policy", "stem_asc")),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not self.root_data_path.strip():
            raise ConfigValidationError("root_data_path must be non-empty")
        if not self.supported_modalities:
            raise ConfigValidationError("supported_modalities must be non-empty")
        _ensure_enum("case_selection_strategy", self.case_selection_strategy, {"sequential", "random"})
        _ensure_enum("filename_sort_policy", self.filename_sort_policy, {"stem_asc", "stem_desc"})
        if self.max_cases is not None:
            _ensure_positive_int("max_cases", self.max_cases)
        if self.max_cases_per_modality is not None:
            _ensure_positive_int("max_cases_per_modality", self.max_cases_per_modality)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClientCase:
    """Single case loaded from dataset json."""

    case_id: str
    modality: str
    basic_info: Dict[str, Any]
    theory_info: Dict[str, Any]

    @property
    def intake_profile(self) -> Dict[str, Any]:
        merged: Dict[str, Any] = dict(self.basic_info)
        merged.update(self.theory_info)
        return merged

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "modality": self.modality,
            "basic_info": self.basic_info,
            "theory_info": self.theory_info,
            "intake_profile": self.intake_profile,
        }


@dataclass
class PublicMemory:
    """Session-level state that should stay public across turns/sessions."""

    known_static_traits: Dict[str, Any] = field(default_factory=dict)
    session_recaps: List[Dict[str, Any]] = field(default_factory=list)
    last_homework: List[str] = field(default_factory=list)


@dataclass
class SessionArtifact:
    """Legacy compatibility artifact persisted per session.

    Active sample/rft runtime flow uses payload dictionaries via ``io.store``.
    """

    case_id: str
    baseline_name: str
    session_index: int
    modality: str
    transcript: List[Dict[str, Any]]
    public_recap: Dict[str, Any]
    stop_reason: Literal["end_token", "turn_cap", "empty_response_failure", "backend_error"]
    num_counselor_turns: int
    visible_context_summary: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionArtifact":
        return cls(
            case_id=str(data["case_id"]),
            baseline_name=str(data["baseline_name"]),
            session_index=int(data["session_index"]),
            modality=str(data["modality"]),
            transcript=list(data.get("transcript", [])),
            public_recap=dict(data.get("public_recap", {})),
            stop_reason=str(data.get("stop_reason", "backend_error")),
            num_counselor_turns=int(data.get("num_counselor_turns", 0)),
            visible_context_summary=dict(data.get("visible_context_summary", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CourseArtifact:
    """Legacy compatibility artifact persisted for a case's partial or full run.

    Active sample/rft runtime flow uses payload dictionaries via ``io.store``.
    """

    case_id: str
    baseline_name: str
    modality: str
    sessions: List[SessionArtifact] = field(default_factory=list)
    finished: bool = False
    finished_reason: str = ""
    num_sessions: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CourseArtifact":
        sessions = [SessionArtifact.from_dict(x) for x in data.get("sessions", [])]
        return cls(
            case_id=str(data["case_id"]),
            baseline_name=str(data["baseline_name"]),
            modality=str(data["modality"]),
            sessions=sessions,
            finished=bool(data.get("finished", False)),
            finished_reason=str(data.get("finished_reason", "")),
            num_sessions=int(data.get("num_sessions", len(sessions))),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "baseline_name": self.baseline_name,
            "modality": self.modality,
            "sessions": [x.to_dict() for x in self.sessions],
            "finished": self.finished,
            "finished_reason": self.finished_reason,
            "num_sessions": self.num_sessions,
        }


@dataclass
class RunResult:
    """Aggregate run-level statistics."""

    total_cases: int = 0
    succeeded: int = 0
    partially_completed: int = 0
    failed_due_to_retries: int = 0
    crashed: int = 0
    skipped_completed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
