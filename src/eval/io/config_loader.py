"""Config loading for eval runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ..core.schemas import EvalRuntimeConfig

try:
    from src.shared.config_utils import load_yaml_mapping
    from src.shared.file_utils import project_root
except ModuleNotFoundError:  # pragma: no cover - supports PYTHONPATH=src execution style
    from shared.config_utils import load_yaml_mapping
    from shared.file_utils import project_root


def load_eval_config(path: str | Path) -> EvalRuntimeConfig:
    """Load eval runtime config from YAML."""
    config_path = Path(path).expanduser().resolve()
    payload = load_yaml_mapping(config_path)

    # Support wrapping under `eval:` to keep room for multi-task configs.
    raw_config: Dict[str, Any]
    maybe_eval = payload.get("eval")
    if isinstance(maybe_eval, dict):
        raw_config = dict(maybe_eval)
    else:
        raw_config = dict(payload)

    _resolve_path_fields(raw_config)
    return EvalRuntimeConfig.from_dict(raw_config)


def _resolve_path_fields(raw: Dict[str, Any]) -> None:
    root = project_root()
    for key in ("data_root", "output_root"):
        value = raw.get(key)
        if value is None:
            continue
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            path = (root / path).resolve()
        raw[key] = str(path)
