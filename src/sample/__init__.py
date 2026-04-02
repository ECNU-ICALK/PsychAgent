"""PsychAgent sample package."""

__all__ = ["PsychAgentRunner"]


def __getattr__(name: str):
    if name == "PsychAgentRunner":
        from .runner import PsychAgentRunner

        return PsychAgentRunner
    raise AttributeError(f"module 'sample' has no attribute {name!r}")
