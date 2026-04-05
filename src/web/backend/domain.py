from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel


class StageInfo(BaseModel):
    key: str
    label: str
    desc: str
    range: List[int]
    color: Optional[str] = None


class SchoolInfo(BaseModel):
    id: str
    name: str
    color: str
    desc: str
    style: str


STAGES: Dict[str, Dict[str, object]] = {
    "assessment": {
        "label": "问题概念化与目标设定",
        "range": [1, 2],
        "desc": "聚焦问题定义、信息收集、关系建立与可执行目标设定",
        "color": "text-blue-600 bg-blue-50",
    },
    "intervention": {
        "label": "核心认知与行为干预",
        "range": [3, 8],
        "desc": "围绕关键认知与行为模式进行结构化干预与练习",
        "color": "text-purple-600 bg-purple-50",
    },
    "consolidation": {
        "label": "巩固与复发预防",
        "range": [9, 10],
        "desc": "整合收获、迁移应用与复发预防，准备有序结束",
        "color": "text-green-600 bg-green-50",
    },
}


SCHOOLS: List[SchoolInfo] = [
    SchoolInfo(
        id="behavioral",
        name="行为疗法 (BT)",
        color="bg-amber-500",
        desc="通过强化、脱敏和模仿来改变特定行为模式，强调可观察、可练习、可追踪的改变。",
        style="直接、实用、训练导向",
    ),
    SchoolInfo(
        id="cbt",
        name="认知行为疗法 (CBT)",
        color="bg-blue-500",
        desc="关注想法、情绪和行为之间的关系，识别并修正带来痛苦的自动化思维。",
        style="理性、结构化、以问题解决为导向",
    ),
    SchoolInfo(
        id="humanistic",
        name="人本-存在主义疗法 (HET)",
        color="bg-rose-500",
        desc="强调真实关系、接纳与意义探索，帮助来访者理解当下体验并作出自主选择。",
        style="温暖、接纳、以人为本",
    ),
    SchoolInfo(
        id="psychodynamic",
        name="心理动力学疗法 (PDT)",
        color="bg-indigo-600",
        desc="探索潜意识冲突与早年经验对当前关系和情绪模式的影响，提升自我理解。",
        style="深度探索、关注内在冲突与关系模式",
    ),
    SchoolInfo(
        id="postmodern",
        name="后现代主义疗法 (PMT)",
        color="bg-teal-500",
        desc="通过外化问题、重构叙事与发现例外时刻，帮助来访者重写更有力量的生命故事。",
        style="合作、赋能、强调多元视角",
    ),
]

SCHOOL_TO_PSYCHAGENT_SECT: Dict[str, str] = {
    "behavioral": "bt",
    "cbt": "cbt",
    "humanistic": "het",
    "psychodynamic": "pdt",
    "postmodern": "pmt",
}

STAGE_KEY_TO_SKILL_STAGE: Dict[str, int] = {
    "assessment": 1,
    "intervention": 2,
    "consolidation": 3,
}

SUMMARY_STAGE_TO_STAGE_KEY: Dict[str, str] = {
    "assessment": "assessment",
    "intervention": "intervention",
    "consolidation": "consolidation",
    "问题概念化与目标设定": "assessment",
    "核心认知与行为干预": "intervention",
    "巩固与复发预防": "consolidation",
    # Backward-compatible aliases from older UI copy.
    "评估性会谈": "assessment",
    "咨询性会谈": "intervention",
    "巩固性会谈": "consolidation",
}


def stage_from_key(key: str) -> StageInfo:
    value = STAGES[key]
    return StageInfo(
        key=key,
        label=value["label"],
        desc=value["desc"],
        range=value["range"],
        color=value.get("color"),
    )


def get_stage_by_visit_no(visit_no: int) -> StageInfo:
    for key, value in STAGES.items():
        start, end = value["range"]
        if start <= visit_no <= end:
            return stage_from_key(key)
    last_key = list(STAGES.keys())[-1]
    return stage_from_key(last_key)


def pick_school(school_id: str) -> SchoolInfo:
    for school in SCHOOLS:
        if school.id == school_id:
            return school
    raise HTTPException(status_code=404, detail="School not found")


def school_to_psychagent_sect(school_id: str) -> str:
    sect = SCHOOL_TO_PSYCHAGENT_SECT.get(school_id)
    if not sect:
        raise HTTPException(status_code=404, detail="Unsupported school for PsychAgent prompts")
    return sect


def stage_key_to_skill_stage(stage_key: str) -> int:
    return STAGE_KEY_TO_SKILL_STAGE.get(stage_key, 1)


def summary_stage_to_stage_key(raw_stage: str) -> Optional[str]:
    text = str(raw_stage or "").strip()
    if not text:
        return None
    return SUMMARY_STAGE_TO_STAGE_KEY.get(text)
