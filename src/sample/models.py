from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict


class NextSessionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    next_session_stage: str
    next_session_focus: List[str]


class SessionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_summary_abstract: str
    next_session_plan: NextSessionPlan
    homework: List[str]


class GoalAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective_recap: str
    completion_status: str
    evidence_and_analysis: str


class BaseClientStateAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    affective_state: str
    behavioral_patterns: str
    therapeutic_alliance: str
    unresolved_points_or_tensions: str


class BTClientStateAnalysis(BaseClientStateAnalysis):
    model_config = ConfigDict(extra="forbid")
    target_behavior: str


class BTSessionSummary(SessionSummary):
    model_config = ConfigDict(extra="forbid")
    goal_assessment: GoalAssessment
    client_state_analysis: BTClientStateAnalysis


class CBTClientStateAnalysis(BaseClientStateAnalysis):
    model_config = ConfigDict(extra="forbid")
    cognitive_patterns: str


class CBTSessionSummary(SessionSummary):
    model_config = ConfigDict(extra="forbid")
    goal_assessment: GoalAssessment
    client_state_analysis: CBTClientStateAnalysis


class HETClientStateAnalysis(BaseClientStateAnalysis):
    model_config = ConfigDict(extra="forbid")
    existentialism_topic: str


class HETSessionSummary(SessionSummary):
    model_config = ConfigDict(extra="forbid")
    goal_assessment: GoalAssessment
    client_state_analysis: HETClientStateAnalysis


class PDTClientStateAnalysis(BaseClientStateAnalysis):
    model_config = ConfigDict(extra="forbid")
    subconscious_manifestation: str


class PDTSessionSummary(SessionSummary):
    model_config = ConfigDict(extra="forbid")
    goal_assessment: GoalAssessment
    client_state_analysis: PDTClientStateAnalysis


class PMTClientStateAnalysis(BaseClientStateAnalysis):
    model_config = ConfigDict(extra="forbid")
    personal_agency: str


class PMTSessionSummary(SessionSummary):
    model_config = ConfigDict(extra="forbid")
    goal_assessment: GoalAssessment
    client_state_analysis: PMTClientStateAnalysis


class StaticTraits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = ""
    age: str = ""
    gender: str = ""
    occupation: str = ""
    educational_background: str = ""
    marital_status: str = ""
    family_status: str = ""
    social_status: str = ""
    medical_history: str = ""


class UpdatedProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    static_traits: StaticTraits
    main_problem: str
    topic: str
    core_demands: str
    growth_experiences: List[str]


class TargetBehaviorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    behavior: str
    antecedent: List[str]
    core_reason: str
    function: str
    consequence: str


class BTProfile(UpdatedProfile):
    model_config = ConfigDict(extra="forbid")
    target_behavior: List[TargetBehaviorItem]


class SpecialSituationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: str
    conditional_assumptions: str
    compensatory_strategies: str
    automatic_thoughts: str
    cognitive_pattern: str
    progress: str
    analysis: List[str]


class CBTProfile(UpdatedProfile):
    model_config = ConfigDict(extra="forbid")
    core_beliefs: List[str]
    special_situations: List[SpecialSituationItem]


class ExistentialismTopicItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme: str
    manifestations: List[str]
    outcomes: List[str]


class ContactModelItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str
    definition: str
    manifestations: List[str]


class HETProfile(UpdatedProfile):
    model_config = ConfigDict(extra="forbid")
    existentialism_topic: List[ExistentialismTopicItem]
    contact_model: List[ContactModelItem]


class CoreConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wish: str
    fear: str
    defense_goal: List[str]


class ObjectRelationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    self_representation: str
    object_representation: str
    linking_affect: str


class BehavioralResponsePatternItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trigger_condition: str
    interpretation: str
    defense_mechanism: str
    response_instruction: str


class PDTProfile(UpdatedProfile):
    model_config = ConfigDict(extra="forbid")
    core_conflict: CoreConflict
    object_relations: List[ObjectRelationItem]
    behavioral_response_patterns: List[BehavioralResponsePatternItem]


class ExceptionEventItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_problem: str
    unique_outcome: str
    reason: str


class ForceField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    positive_force: List[str]
    negative_force: List[str]


class PMTProfile(UpdatedProfile):
    model_config = ConfigDict(extra="forbid")
    exception_events: List[ExceptionEventItem]
    force_field: ForceField


MODALITY_MODELS = {
    "bt": {"summary": BTSessionSummary, "profile": BTProfile},
    "cbt": {"summary": CBTSessionSummary, "profile": CBTProfile},
    "het": {"summary": HETSessionSummary, "profile": HETProfile},
    "pdt": {"summary": PDTSessionSummary, "profile": PDTProfile},
    "pmt": {"summary": PMTSessionSummary, "profile": PMTProfile},
}
