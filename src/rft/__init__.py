"""PsychAgent RFT module."""

__all__ = ["RFTPsychAgentRunner", "RFTRuntimeConfig"]


def __getattr__(name: str):
    if name == "RFTPsychAgentRunner":
        from .runner import RFTPsychAgentRunner

        return RFTPsychAgentRunner
    if name == "RFTRuntimeConfig":
        from .core.schemas import RFTRuntimeConfig

        return RFTRuntimeConfig
    raise AttributeError(f"module 'rft' has no attribute {name!r}")
