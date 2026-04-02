"""Shared file/path utilities used across sample and eval modules."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def project_root() -> Path:
    """Return repository root for PsychAgent_v0402 (same level as src/)."""
    return Path(__file__).resolve().parents[2]


def resolve_path(*parts: str | Path) -> Path:
    """Resolve path relative to repository root when needed."""
    if not parts:
        return project_root()

    first = Path(parts[0])
    if first.is_absolute():
        return Path(*parts)
    return project_root() / Path(*parts)


def safe_filename(stem: str) -> str:
    """Normalize arbitrary text into a safe filesystem stem."""
    text = str(stem).strip().replace("/", "_").replace("\\", "_")
    text = _SAFE_FILENAME_RE.sub("_", text)
    return text.strip("._-") or "untitled"


def load_json_if_exists(path: str | Path) -> Optional[Dict[str, Any]]:
    """Load JSON if file exists, return None on read/parsing failure."""
    file_path = Path(path)
    if not file_path.exists():
        return None
    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data


def write_json_atomic(path: str | Path, data: Dict[str, Any]) -> Path:
    """Write JSON with atomic replace under a lock-friendly temporary file."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(dir=str(file_path.parent), prefix=f".{file_path.name}.", suffix=".tmp")
    temp_file = Path(temp_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(temp_file), str(file_path))
    finally:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass
    return file_path


def write_json(path: str | Path, data: Dict[str, Any]) -> Path:
    """Simple non-atomic JSON write helper."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return file_path
