"""Reward scoring logic for RFT session-level rollout selection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    try:
        from src.eval.reward import RewardEvaluationResult
    except ModuleNotFoundError:  # pragma: no cover - supports PYTHONPATH=src execution style
        from eval.reward import RewardEvaluationResult


DEFAULT_REWARD_STD_MEAN: Dict[str, Dict[str, Dict[str, float]]] = {
    "counselor": {
        "RRO": {"mean": 7.637, "std": 1.073},
        "HTAIS": {"mean": 6.404, "std": 1.07},
        "WAI": {"mean": 7.257, "std": 1.461},
        "CUSTOM_DIM": {"mean": 7.363, "std": 0.957},
        "CTRS": {"mean": 9.19, "std": 0.89},
        "EFT_TFS": {"mean": 3.144, "std": 1.948},
        "TES": {"mean": 7.362, "std": 1.346},
        "MITI": {"mean": 5.881, "std": 1.112},
        "PSC": {"mean": 7.269, "std": 1.119},
    },
    "client": {
        "RRO": {"mean": 0.211, "std": 1.262},
        "PANAS": {"mean": 0.442, "std": 0.94},
        "SCL_90": {"mean": -0.14, "std": 0.892},
        "SRS": {"mean": 0.225, "std": 1.507},
        "BDI_II": {"mean": -0.446, "std": 1.39},
        "SFBT": {"mean": 0.158, "std": 1.568},
        "CCT": {"mean": 0.136, "std": 1.016},
        "STAI": {"mean": 0.279, "std": 1.741},
        "IPO": {"mean": -0.085, "std": 2.464},
    },
}

NEGATIVE_DELTA_CLIENT_METRICS = {"SCL_90", "BDI_II", "IPO"}


@dataclass(frozen=True)
class RewardSignal:
    side: str
    metric: str
    raw_value: float
    standardized: float
    previous_value: float | None = None
    delta: float | None = None
    skipped_reason: str | None = None


@dataclass(frozen=True)
class RewardComputation:
    final_score: float
    reward_snapshot: Dict[str, Dict[str, float]]
    signals: List[RewardSignal] = field(default_factory=list)
    skipped: List[RewardSignal] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_score": self.final_score,
            "reward_snapshot": {
                "counselor": dict(self.reward_snapshot.get("counselor", {})),
                "client": dict(self.reward_snapshot.get("client", {})),
            },
            "signals": [_signal_to_dict(item) for item in self.signals],
            "skipped": [_signal_to_dict(item) for item in self.skipped],
        }


def compute_rollout_reward(
    *,
    evaluation: "RewardEvaluationResult",
    previous_reward_snapshot: Dict[str, Dict[str, float]] | None,
    reward_std_mean: Dict[str, Dict[str, Dict[str, float]]] | None = None,
) -> RewardComputation:
    stats = reward_std_mean or DEFAULT_REWARD_STD_MEAN
    prev = previous_reward_snapshot or {"counselor": {}, "client": {}}
    prev_client = _normalize_reward_snapshot(prev.get("client", {}))

    curr_counselor = _normalize_reward_snapshot(evaluation.counselor)
    curr_client = _normalize_reward_snapshot(evaluation.client)

    reward_snapshot = {
        "counselor": dict(curr_counselor),
        "client": dict(curr_client),
    }

    signals: List[RewardSignal] = []
    skipped: List[RewardSignal] = []
    z_values: List[float] = []

    for metric, value in curr_counselor.items():
        metric_stats = stats.get("counselor", {}).get(metric)
        if not metric_stats:
            skipped.append(
                RewardSignal(
                    side="counselor",
                    metric=metric,
                    raw_value=value,
                    standardized=0.0,
                    skipped_reason="missing_std_stats",
                )
            )
            continue

        z_score = _clip((value - metric_stats["mean"]) / metric_stats["std"])
        z_values.append(z_score)
        signals.append(
            RewardSignal(
                side="counselor",
                metric=metric,
                raw_value=value,
                standardized=z_score,
            )
        )

    for metric, value in curr_client.items():
        metric_stats = stats.get("client", {}).get(metric)
        previous_value = prev_client.get(metric)
        if previous_value is None:
            skipped.append(
                RewardSignal(
                    side="client",
                    metric=metric,
                    raw_value=value,
                    standardized=0.0,
                    skipped_reason="missing_previous_reward",
                )
            )
            continue
        if not metric_stats:
            skipped.append(
                RewardSignal(
                    side="client",
                    metric=metric,
                    raw_value=value,
                    previous_value=previous_value,
                    delta=value - previous_value,
                    standardized=0.0,
                    skipped_reason="missing_std_stats",
                )
            )
            continue

        delta = value - previous_value
        z_score = _clip((delta - metric_stats["mean"]) / metric_stats["std"])
        if metric in NEGATIVE_DELTA_CLIENT_METRICS:
            z_score = -z_score
        z_values.append(z_score)
        signals.append(
            RewardSignal(
                side="client",
                metric=metric,
                raw_value=value,
                previous_value=previous_value,
                delta=delta,
                standardized=z_score,
            )
        )

    final_score = sum(z_values) / len(z_values) if z_values else 0.0
    return RewardComputation(
        final_score=final_score,
        reward_snapshot=reward_snapshot,
        signals=signals,
        skipped=skipped,
    )


def _normalize_reward_snapshot(raw_scores: Dict[str, Any]) -> Dict[str, float]:
    normalized: Dict[str, float] = {}
    for name, value in raw_scores.items():
        if not isinstance(value, (int, float)):
            continue
        key = canonical_metric_name(name)
        normalized[key] = float(value)
    return normalized


def canonical_metric_name(name: str) -> str:
    return str(name).strip().upper().replace("-", "_")


def _clip(value: float, lower: float = -3.0, upper: float = 3.0) -> float:
    if value < lower:
        return lower
    if value > upper:
        return upper
    return value


def _signal_to_dict(signal: RewardSignal) -> Dict[str, Any]:
    return {
        "side": signal.side,
        "metric": signal.metric,
        "raw_value": signal.raw_value,
        "previous_value": signal.previous_value,
        "delta": signal.delta,
        "standardized": signal.standardized,
        "skipped_reason": signal.skipped_reason,
    }
