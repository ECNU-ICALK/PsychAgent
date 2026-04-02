"""JSON artifact storage for sessions and courses."""

from __future__ import annotations

import json
import shutil
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from src.shared.file_utils import write_json
except ModuleNotFoundError:  # pragma: no cover - supports PYTHONPATH=src execution style
    from shared.file_utils import write_json

from ..core.schemas import CourseArtifact, SessionArtifact


class ResultStore:
    """Persist and load case-level artifacts."""

    def __init__(self, save_root: str | Path, baseline_name: str) -> None:
        self._save_root = Path(save_root)
        self._baseline_name = baseline_name

    @property
    def save_root(self) -> Path:
        return self._save_root

    @property
    def baseline_name(self) -> str:
        return self._baseline_name

    def case_dir(self, modality: str, case_id: str) -> Path:
        return self._save_root / self._baseline_name / modality / case_id

    def session_path(self, modality: str, case_id: str, session_index: int) -> Path:
        return self.case_dir(modality, case_id) / f"session_{session_index}.json"

    def course_path(self, modality: str, case_id: str) -> Path:
        return self.case_dir(modality, case_id) / "course.json"

    def prepare_case_dir(self, modality: str, case_id: str, *, overwrite: bool) -> Path:
        path = self.case_dir(modality, case_id)
        if overwrite and path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    # Payload-level APIs used by the active sample/rft runner flow.
    def save_session_payload(
        self,
        modality: str,
        case_id: str,
        session_index: int,
        payload: Dict[str, Any],
    ) -> Path:
        return write_json(self.session_path(modality, case_id, session_index), payload)

    def load_session_payload(self, modality: str, case_id: str, session_index: int) -> Optional[Dict[str, Any]]:
        path = self.session_path(modality, case_id, session_index)
        if not path.exists():
            return None
        return self._load_dict(path)

    def load_session_payload_from_path(self, path: Path) -> Dict[str, Any]:
        return self._load_dict(path)

    def save_course_payload(self, modality: str, case_id: str, payload: Dict[str, Any]) -> Path:
        return write_json(self.course_path(modality, case_id), payload)

    def load_course_payload(self, modality: str, case_id: str) -> Dict[str, Any]:
        path = self.course_path(modality, case_id)
        if not path.exists():
            return {}
        raw = self._load_dict(path)
        return raw if isinstance(raw, dict) else {}

    def discover_session_paths(self, modality: str, case_id: str) -> List[Path]:
        case_dir = self.case_dir(modality, case_id)
        paths: List[Path] = []
        for path in case_dir.glob("session_*.json"):
            stem = path.stem
            try:
                int(stem.split("_")[-1])
            except Exception:
                continue
            paths.append(path)
        return sorted(paths, key=lambda p: int(p.stem.split("_")[-1]))

    @staticmethod
    def _load_dict(path: Path) -> Dict[str, Any]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise RuntimeError(f"invalid json payload (expect object): {path}")
        return raw

    def save_session(self, artifact: SessionArtifact) -> Path:
        """Legacy compatibility API. Prefer ``save_session_payload``."""
        warnings.warn(
            "ResultStore.save_session() is legacy; prefer save_session_payload().",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.save_session_payload(
            artifact.modality,
            artifact.case_id,
            artifact.session_index,
            artifact.to_dict(),
        )

    def load_session(self, modality: str, case_id: str, session_index: int) -> Optional[SessionArtifact]:
        """Legacy compatibility API. Prefer ``load_session_payload``."""
        warnings.warn(
            "ResultStore.load_session() is legacy; prefer load_session_payload().",
            DeprecationWarning,
            stacklevel=2,
        )
        payload = self.load_session_payload(modality, case_id, session_index)
        if payload is None:
            return None
        return SessionArtifact.from_dict(payload)

    def save_course(self, artifact: CourseArtifact) -> Path:
        """Legacy compatibility API. Prefer ``save_course_payload``."""
        warnings.warn(
            "ResultStore.save_course() is legacy; prefer save_course_payload().",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.save_course_payload(artifact.modality, artifact.case_id, artifact.to_dict())

    def load_course(self, modality: str, case_id: str) -> Optional[CourseArtifact]:
        """Legacy compatibility API. Prefer ``load_course_payload``."""
        warnings.warn(
            "ResultStore.load_course() is legacy; prefer load_course_payload().",
            DeprecationWarning,
            stacklevel=2,
        )
        payload = self.load_course_payload(modality, case_id)
        if not payload:
            return None
        return CourseArtifact.from_dict(payload)
