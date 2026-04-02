from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

try:
    from jinja2 import Template
except ImportError:  # pragma: no cover
    Template = None  # type: ignore[assignment]


class PsychAgentPromptManager:
    def __init__(
        self,
        prompt_root: Path,
        modality: str,
        counselor_system_filename: str = "system.jinja2",
    ):
        self.prompt_root = Path(prompt_root)
        self.modality = modality
        self.counselor_system_filename = counselor_system_filename
        self.prompts: Dict[str, Any] = {}
        self._load_and_compile_prompts()

    def _load_and_compile_prompts(self) -> None:
        base = self.prompt_root / self.modality
        self.prompts["counselor_system"] = self._load_tmpl(
            base / "counsel" / self.counselor_system_filename
        )
        self.prompts["summary_system"] = self._load_text(base / "summary" / "system.jinja2")
        self.prompts["summary_user"] = self._load_tmpl(base / "summary" / "user.jinja2")
        self.prompts["profile_system"] = self._load_text(base / "profile" / "system.jinja2")
        self.prompts["profile_user"] = self._load_tmpl(base / "profile" / "user.jinja2")

    def _load_text(self, path: Path) -> str:
        if not path.exists():
            raise FileNotFoundError(f"prompt file not found: {path}")
        return path.read_text(encoding="utf-8")

    def _load_tmpl(self, path: Path) -> Any:
        text = self._load_text(path)
        if Template is None:
            return text
        return Template(text)

    def render(self, key: str, **kwargs: Any) -> str:
        tmpl = self.prompts.get(key)
        if tmpl is None:
            return ""
        if Template is not None and isinstance(tmpl, Template):
            return tmpl.render(**kwargs)
        # Jinja2 fallback: keep simple placeholder substitution unavailable.
        return str(tmpl)
