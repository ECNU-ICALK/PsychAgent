from __future__ import annotations

from typing import Any, Dict, List

import json
from jinja2 import Template
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ...core.base import EvaluationMethod
from ...utils import load_prompt


PlanConsistencyItemName = Literal[
    "PersonaConsistency",
    "OverallGoalConsistency",
    "ProcessDetailConsistency",
    "TreatmentOutcomeConsistency",
]


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    item: PlanConsistencyItemName
    score: int = Field(ge=0, le=10)


class Items(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    items: List[Item] = Field(min_length=1, max_length=1)


class _PlanConsistencyBase(EvaluationMethod):
    PROMPT_NAME: str

    async def evaluate(self, gpt_api, dialogue: Any, profile: dict = None) -> Dict[str, float]:
        plan_obj = None
        if isinstance(profile, dict):
            if "global_plan" in profile:
                plan_obj = profile.get("global_plan")
            elif "plan" in profile:
                plan_obj = profile.get("plan")

        try:
            plan_text = json.dumps(plan_obj or {}, ensure_ascii=False, indent=2)
        except Exception:
            plan_text = str(plan_obj)

        prompt_template = load_prompt("plan_consistency", self.PROMPT_NAME, "cn")
        prompt = Template(prompt_template).render(diag=dialogue, plan=plan_text)
        messages = [{"role": "user", "content": prompt}]
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                out = await self.chat_api(gpt_api, messages=messages)
                validated = Items.model_validate(json.loads(out))
                if not validated.items or validated.items[0].item != self.PROMPT_NAME:
                    raise ValueError("Invalid or mismatched item name")
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt >= 2:
                    raise
                messages = messages + [
                    {
                        "role": "user",
                        "content": f"上一次输出未通过格式校验。请严格只输出一个JSON对象，且只包含键 items；items 长度必须为 1；元素仅包含 item(必须为 {self.PROMPT_NAME}) 与 score(0-10整数)。",
                    }
                ]
        else:  # pragma: no cover
            raise RuntimeError(f"Failed to get valid {self.PROMPT_NAME} output: {last_err}")

        if not validated.items:
            return {"counselor": 0.0}

        score_0_10 = float(validated.items[0].score)
        return {"counselor": score_0_10}

    def get_name(self) -> str:
        return self.PROMPT_NAME


class PersonaConsistency(_PlanConsistencyBase):
    PROMPT_NAME = "PersonaConsistency"


class OverallGoalConsistency(_PlanConsistencyBase):
    PROMPT_NAME = "OverallGoalConsistency"


class ProcessDetailConsistency(_PlanConsistencyBase):
    PROMPT_NAME = "ProcessDetailConsistency"


class TreatmentOutcomeConsistency(_PlanConsistencyBase):
    PROMPT_NAME = "TreatmentOutcomeConsistency"
