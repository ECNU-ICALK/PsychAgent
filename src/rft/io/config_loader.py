"""Config loading for RFT runtime."""

from __future__ import annotations

from pathlib import Path

from ..core.schemas import RFTRuntimeConfig

try:
    from src.shared.config_utils import load_yaml_mapping
except ModuleNotFoundError:  # pragma: no cover - supports PYTHONPATH=src execution style
    from shared.config_utils import load_yaml_mapping


def load_rft_config(path: str | Path) -> RFTRuntimeConfig:
    payload = load_yaml_mapping(path)
    maybe_rft = payload.get("rft")
    if isinstance(maybe_rft, dict):
        payload = maybe_rft
    return RFTRuntimeConfig.from_dict(payload)
