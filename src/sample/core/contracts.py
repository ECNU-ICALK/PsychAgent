"""Public runner contracts shared by sample and downstream modules (e.g. rft)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal


@dataclass
class CaseResumeDecision:
    """Resume decision produced before running one case."""

    action: Literal["start", "resume", "skip"]
    next_session_index: int
    existing_records: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""


@dataclass
class CaseRunResult:
    """Case-level run result returned by one runner invocation."""

    finished: bool
    finished_reason: str
    num_sessions: int

