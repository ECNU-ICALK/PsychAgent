"""YAML config loading for baseline sampler."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import warnings
from pathlib import Path
from typing import Any, Dict, Tuple

from ..core.schemas import (
    BaselineConfig,
    ConfigValidationError,
    DatasetConfig,
    RuntimeConfig,
    runtime_field_statuses,
)

try:
    from src.shared.config_utils import load_yaml_mapping
except ModuleNotFoundError:  # pragma: no cover - supports PYTHONPATH=src execution style
    from shared.config_utils import load_yaml_mapping


def load_baseline_config(path: str | Path) -> BaselineConfig:
    return BaselineConfig.from_dict(_load_yaml_dict(path))


@dataclass(frozen=True)
class RuntimeConfigAuditReport:
    config_path: str
    strict: bool
    active: Tuple[str, ...]
    deprecated: Tuple[str, ...]
    removed: Tuple[str, ...]
    unknown: Tuple[str, ...]
    unused: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def load_runtime_config(
    path: str | Path,
    *,
    strict: bool = False,
    return_audit: bool = False,
) -> RuntimeConfig | tuple[RuntimeConfig, RuntimeConfigAuditReport]:
    raw = _load_yaml_dict(path)
    report = audit_runtime_config_fields(raw, path=path, strict=strict)
    cfg = RuntimeConfig.from_dict(raw)
    if return_audit:
        return cfg, report
    return cfg


def load_dataset_config(path: str | Path) -> DatasetConfig:
    config_path = Path(path)
    cfg = DatasetConfig.from_dict(_load_yaml_dict(config_path))
    if cfg.root_data_path and not Path(cfg.root_data_path).is_absolute():
        cfg.root_data_path = str((config_path.parent / cfg.root_data_path).resolve())
    return cfg


def _load_yaml_dict(path: str | Path) -> Dict[str, Any]:
    return load_yaml_mapping(path)


def audit_runtime_config_fields(
    raw: Dict[str, Any],
    *,
    path: str | Path,
    strict: bool,
) -> RuntimeConfigAuditReport:
    statuses = runtime_field_statuses()
    configured_keys = sorted(str(key) for key in raw.keys())

    active = []
    deprecated = []
    removed = []
    unknown = []

    for key in configured_keys:
        status = statuses.get(key)
        if status == "active":
            active.append(key)
        elif status == "deprecated":
            deprecated.append(key)
        elif status == "removed":
            removed.append(key)
        else:
            unknown.append(key)

    unused = sorted(set(deprecated) | set(removed))
    config_path = Path(path)
    if deprecated:
        warnings.warn(
            (
                f"Runtime config {config_path} contains deprecated keys: {', '.join(deprecated)}. "
                "These keys are compatibility-only and currently no-op."
            ),
            UserWarning,
            stacklevel=2,
        )
    if removed:
        warnings.warn(
            (
                f"Runtime config {config_path} contains removed keys: {', '.join(removed)}. "
                "These keys are ignored by active runtime schema."
            ),
            UserWarning,
            stacklevel=2,
        )
    if unknown:
        warnings.warn(
            (
                f"Runtime config {config_path} contains unknown keys: {', '.join(unknown)}. "
                "Unknown keys are ignored unless strict mode is enabled."
            ),
            UserWarning,
            stacklevel=2,
        )
    if strict and (unused or unknown):
        detail = []
        if unused:
            detail.append(f"unused={unused}")
        if unknown:
            detail.append(f"unknown={unknown}")
        raise ConfigValidationError(
            f"strict runtime config check failed for {config_path}: " + "; ".join(detail)
        )

    return RuntimeConfigAuditReport(
        config_path=str(config_path),
        strict=bool(strict),
        active=tuple(active),
        deprecated=tuple(deprecated),
        removed=tuple(removed),
        unknown=tuple(unknown),
        unused=tuple(unused),
    )
