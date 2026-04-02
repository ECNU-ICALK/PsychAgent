from typing import Any, Dict
import re
import asyncio


from ...core.base import EvaluationMethod
from ...utils import load_prompt
from jinja2 import Template
import json

from typing import List
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator # 👈 确保导入 ConfigDict

class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    item: str
    score: int = Field(ge=0, le=2)
    evidence_pos: List[str] = Field(max_length=2)
    evidence_neg: List[str] = Field(max_length=2)
    thought: str = Field(max_length=24, pattern=r"^[^\n\r]{0,24}$")

    @field_validator("item")
    @classmethod
    def _validate_item(cls, v: str) -> str:
        s = str(v).strip()
        if not s.isdigit():
            raise ValueError("item must be a digit string")
        n = int(s)
        if not (1 <= n <= 3):
            raise ValueError("item must be between 1 and 3")
        return s


class Items(BaseModel):  # 用对象包一层
    model_config = ConfigDict(extra="forbid", strict=True)

    items: List[Item] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def _validate_order(self) -> "Items":
        expected = ["1", "2", "3"]
        actual = [it.item for it in self.items]
        if actual != expected:
            raise ValueError("items must be in the exact required order: '1','2','3'")
        return self

class CCT(EvaluationMethod):
    async def evaluate(self, gpt_api, dialogue: Any, profile: dict = None) -> dict[str, float]:
        """评估对话质量"""
        criteria_list = ["current focus", "non critical", "real connection", "self awareness", "self exploration"]
        scores: list[Item] = []

        async def run_one(criteria: str) -> list[Item]:
            prompt = load_prompt("cct", criteria, "cn")
            prompt = Template(prompt).render(intake_form=profile, diag=dialogue)
            messages = [{"role": "user", "content": prompt}]
            last_err: Exception | None = None
            for attempt in range(3):
                try:
                    criteria_output = await self.chat_api(gpt_api, messages=messages)
                    validated = Items.model_validate(json.loads(criteria_output))
                    return list(validated.items)
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    if attempt >= 2:
                        raise
                    messages = messages + [
                        {
                            "role": "user",
                            "content": "上一次输出未通过格式校验。请严格只输出一个JSON对象，且只包含键 items；items 长度必须为 3，每项仅包含 item/evidence_pos/evidence_neg/thought/score。",
                        }
                    ]
            raise RuntimeError(f"Failed to get valid CCT output: {last_err}")

        items_lists = await asyncio.gather(*(run_one(c) for c in criteria_list))
        for items in items_lists:
            scores.extend(items)

        mean_score = 0.0
        if scores:
            for item in scores:
                mean_score += float(item.score) / 2.0 * 10.0  # 0-2 -> 0-10
            mean_score /= len(scores)

        return {"client": mean_score}

    def get_name(self) -> str:
        return "CCT"
