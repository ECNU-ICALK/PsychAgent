"""Normalize eval inputs from native eval cases or sample artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


_SESSION_STEM_RE = re.compile(r"^session_(\d+)$")


@dataclass(frozen=True)
class AdaptedEvalCase:
    """Normalized eval case payload used by orchestrator."""

    case_name: str
    payload: Dict[str, Any]


def adapt_eval_case_file(path: Path, *, input_format: str = "auto") -> AdaptedEvalCase:
    raw = _load_case_object(path)
    kind = _detect_case_kind(path, raw)

    fmt = (input_format or "auto").strip().lower()
    if fmt == "eval_case" and kind != "eval_case":
        raise RuntimeError(f"{path}: input_format=eval_case but payload is {kind}")
    if fmt == "sample" and kind == "eval_case":
        raise RuntimeError(f"{path}: input_format=sample but payload is eval_case")

    if kind == "eval_case":
        return AdaptedEvalCase(case_name=path.stem, payload=raw)
    if kind == "sample_course":
        return _adapt_sample_course(path, raw)
    if kind == "sample_session":
        return _adapt_sample_session(path, raw)
    raise RuntimeError(f"{path}: unsupported input payload format")


def _load_case_object(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"failed to load eval case json {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path}: invalid json payload (expect object)")
    return payload


def _detect_case_kind(path: Path, payload: Dict[str, Any]) -> str:
    if isinstance(payload.get("sessions"), list):
        return "eval_case"
    if path.name == "course.json":
        return "sample_course"
    if _SESSION_STEM_RE.match(path.stem) and isinstance(payload.get("transcript"), list):
        return "sample_session"
    if isinstance(payload.get("transcript"), list):
        return "sample_session"
    return "unknown"


def _adapt_sample_course(path: Path, payload: Dict[str, Any]) -> AdaptedEvalCase:
    case_name = path.parent.name
    session_paths = sorted(
        path.parent.glob("session_*.json"),
        key=lambda p: _safe_session_number_from_stem(p.stem, 0),
    )
    sessions: List[Dict[str, Any]] = []
    profile: Dict[str, Any] = {}
    for session_path in session_paths:
        session_raw = _load_case_object(session_path)
        dialogue = _extract_session_dialogue(session_raw.get("transcript"))
        if not dialogue:
            continue
        session_number = _safe_session_number_from_stem(session_path.stem, len(sessions) + 1)
        sessions.append(
            {
                "session_number": session_number,
                "session_dialogue": dialogue,
            }
        )
        profile_candidate = _extract_profile(session_raw)
        if profile_candidate:
            profile = profile_candidate

    if not sessions:
        raise RuntimeError(f"{path}: no usable session_*.json transcript found for sample course payload")

    case_id = str(payload.get("case_id") or case_name)
    client_info = dict(profile)
    client_info.setdefault("client_id", case_id)

    normalized = {
        "theoretical": str(payload.get("modality") or "").strip().lower(),
        "client_info": client_info,
        "sessions": sessions,
    }
    return AdaptedEvalCase(case_name=case_name, payload=normalized)


def _adapt_sample_session(path: Path, payload: Dict[str, Any]) -> AdaptedEvalCase:
    case_name = path.parent.name if path.parent.name else path.stem
    session_number = _safe_session_number_from_stem(path.stem, 1)
    dialogue = _extract_session_dialogue(payload.get("transcript"))
    if not dialogue:
        raise RuntimeError(f"{path}: sample session payload missing usable transcript")

    profile = _extract_profile(payload)
    client_info = dict(profile)
    client_info.setdefault("client_id", case_name)

    normalized = {
        "theoretical": str(payload.get("modality") or "").strip().lower(),
        "client_info": client_info,
        "sessions": [
            {
                "session_number": session_number,
                "session_dialogue": dialogue,
            }
        ],
    }
    return AdaptedEvalCase(case_name=case_name, payload=normalized)


def _extract_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    updated = payload.get("updated_profile")
    if isinstance(updated, dict) and updated:
        return dict(updated)
    snap = payload.get("profile_snapshot")
    if isinstance(snap, dict) and snap:
        return dict(snap)
    return {}


def _extract_session_dialogue(transcript: Any) -> List[Dict[str, str]]:
    if not isinstance(transcript, list):
        return []
    dialogue: List[Dict[str, str]] = []
    for turn in transcript:
        if not isinstance(turn, dict):
            continue
        raw_role = str(turn.get("role", "")).strip().lower()
        role = _normalize_role(raw_role)
        if role is None:
            continue
        content = turn.get("content")
        if content is None:
            content = turn.get("text")
        if content is None:
            continue
        text = str(content).strip()
        if not text:
            continue
        dialogue.append({"role": role, "text": text})
    return dialogue


def _normalize_role(raw_role: str) -> Optional[str]:
    if raw_role in {"assistant", "counselor", "therapist"}:
        return "Counselor"
    if raw_role in {"user", "client", "human"}:
        return "Client"
    return None


def _safe_session_number_from_stem(stem: str, default_value: int) -> int:
    match = _SESSION_STEM_RE.match(stem)
    if match:
        try:
            idx = int(match.group(1))
            if idx > 0:
                return idx
        except Exception:
            pass
    return default_value
