"""Resume inspection for partial case artifacts."""

from __future__ import annotations

from typing import Any, Dict

from ..core.contracts import CaseResumeDecision
from .store import ResultStore


class ResumeStateError(RuntimeError):
    """Raised when on-disk artifacts are inconsistent."""


# Backward-compatible alias.
ResumeDecision = CaseResumeDecision


def inspect_case_resume(
    store: ResultStore,
    *,
    modality: str,
    case_id: str,
    max_sessions: int,
    resume_enabled: bool,
    overwrite: bool,
) -> CaseResumeDecision:
    """Inspect on-disk artifacts and decide start/resume/skip.

    This implementation intentionally follows the active runner behavior to keep
    runtime semantics stable while centralizing resume logic into io/resume.
    """
    if overwrite:
        return CaseResumeDecision(action="start", next_session_index=1, reason="overwrite_enabled")

    course_meta = store.load_course_payload(modality, case_id)
    if course_meta.get("finished") is True:
        return CaseResumeDecision(
            action="skip",
            next_session_index=max_sessions + 1,
            reason="already_completed",
        )

    session_paths = store.discover_session_paths(modality, case_id)
    if not session_paths:
        return CaseResumeDecision(action="start", next_session_index=1, reason="new_case")

    if not resume_enabled:
        raise ResumeStateError(
            f"partial outputs exist for case={case_id}, but resume mode is disabled"
        )

    existing_records = [store.load_session_payload_from_path(path) for path in session_paths]
    last_stage = _extract_next_stage(existing_records[-1])
    if _is_termination(last_stage):
        return CaseResumeDecision(
            action="skip",
            next_session_index=len(existing_records) + 1,
            reason="already_completed",
        )

    return CaseResumeDecision(
        action="resume",
        next_session_index=len(existing_records) + 1,
        existing_records=existing_records,
        reason=f"resume_from_session_{len(existing_records) + 1}",
    )


def _extract_next_stage(record: Dict[str, Any]) -> str:
    summary = record.get("summary", {})
    if not isinstance(summary, dict):
        return ""
    next_plan = summary.get("next_session_plan", {})
    if not isinstance(next_plan, dict):
        return ""
    return str(next_plan.get("next_session_stage", "")).strip()


def _is_termination(stage: str) -> bool:
    return stage.strip().lower() == "termination"
