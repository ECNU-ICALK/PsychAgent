"""Utilities shared by eval methods and orchestrator."""

from __future__ import annotations

from pathlib import Path

try:
    from src.shared.file_utils import project_root
except ModuleNotFoundError:  # pragma: no cover - supports PYTHONPATH=src execution style
    from shared.file_utils import project_root


def _prompt_root() -> Path:
    """Return project prompt root for eval methods."""
    return project_root() / "prompts" / "eval"


def load_prompt(method_name: str, prompt_name: str, language: str = "cn") -> str:
    """Load a prompt text from the eval prompt catalog.

    The historical project stored prompt texts by method name. In the current
    framework version the layout is:

    prompts/eval/<method_name>/<prompt_name>.txt
    """

    if not method_name or not prompt_name:
        raise ValueError("method_name and prompt_name are required")

    root = _prompt_root()
    candidate = root / method_name / f"{prompt_name}.txt"
    if not candidate.exists():
        alt = root / method_name / f"{prompt_name}.TXT"
        if alt.exists():
            candidate = alt
        else:
            # Some prompts are intentionally placed directly under prompts/eval.
            direct = root / f"{prompt_name}.txt"
            direct_alt = root / f"{prompt_name}.TXT"
            if direct.exists():
                candidate = direct
            elif direct_alt.exists():
                candidate = direct_alt
            else:
                raise FileNotFoundError(f"prompt not found: {candidate}")

    if language and language.lower() not in {"cn", "zh", "zh-cn"}:
        return candidate.read_text(encoding="utf-8")
    return candidate.read_text(encoding="utf-8")
