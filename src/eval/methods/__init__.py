"""Evaluation methods exposed for the `eval` module orchestrator."""

from __future__ import annotations

from .counselor.ctrs import CTRS
from .counselor.htais import HTAIS
from .client.panas import PANAS
from .client.ipo import IPO
from .client.phq_9 import PHQ_9
from .counselor.eft_tfs import EFT_TFS
from .counselor.miti import MITI
from .client.scl_90 import SCL_90
from .client.srs import SRS
from .client.bdi_ii import BDI_II
from .counselor.custom_dim import Custom_Dim
from .counselor.psc import PSC
from .counselor.tes import TES
from .client.cct import CCT
from .client.stai import STAI
from .client.sfbt import SFBT
from .counselor.wai import WAI
from .counselor.dialogue_grounding import Dialogue_Grounding
from .counselor.dialogue_planning import Dialogue_Planning
from .counselor.dialogue_redundancy import Dialogue_Redundancy
from .counselor.plan_consistency import (
    PersonaConsistency,
    OverallGoalConsistency,
    ProcessDetailConsistency,
    TreatmentOutcomeConsistency,
)
from .counselor.human_eval import Professionalism, Authenticity, Coherence, Depth
from .counselor.human_vs_llm import HUMAN_VS_LLM
from .rro import RRO


METHOD_REGISTRY = {
    "CTRS": CTRS,
    "HTAIS": HTAIS,
    "PANAS": PANAS,
    "IPO": IPO,
    "PHQ_9": PHQ_9,
    "EFT_TFS": EFT_TFS,
    "MITI": MITI,
    "SCL_90": SCL_90,
    "SRS": SRS,
    "BDI_II": BDI_II,
    "Custom_Dim": Custom_Dim,
    "PSC": PSC,
    "TES": TES,
    "CCT": CCT,
    "STAI": STAI,
    "SFBT": SFBT,
    "WAI": WAI,
    "Dialogue_Grounding": Dialogue_Grounding,
    "Dialogue_Planning": Dialogue_Planning,
    "Dialogue_Redundancy": Dialogue_Redundancy,
    "PersonaConsistency": PersonaConsistency,
    "OverallGoalConsistency": OverallGoalConsistency,
    "ProcessDetailConsistency": ProcessDetailConsistency,
    "TreatmentOutcomeConsistency": TreatmentOutcomeConsistency,
    "Professionalism": Professionalism,
    "Authenticity": Authenticity,
    "Coherence": Coherence,
    "Depth": Depth,
    "HUMAN_VS_LLM": HUMAN_VS_LLM,
    "RRO": RRO,
}

__all__ = tuple(METHOD_REGISTRY.keys())
