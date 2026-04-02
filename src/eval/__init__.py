"""PsychAgent evaluation module."""

__all__ = ["EvalRuntimeConfig", "EvaluationOrchestrator", "RewardEvaluator", "RewardEvaluationResult"]


def __getattr__(name: str):
    if name == "EvalRuntimeConfig":
        from .core.schemas import EvalRuntimeConfig

        return EvalRuntimeConfig
    if name == "EvaluationOrchestrator":
        from .manager.evaluation_orchestrator import EvaluationOrchestrator

        return EvaluationOrchestrator
    if name in {"RewardEvaluator", "RewardEvaluationResult"}:
        from .reward import RewardEvaluationResult, RewardEvaluator

        if name == "RewardEvaluator":
            return RewardEvaluator
        return RewardEvaluationResult
    raise AttributeError(f"module 'eval' has no attribute {name!r}")
