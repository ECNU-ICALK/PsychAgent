from typing import Any, Dict
import re


from ...core.base import EvaluationMethod
from ...utils import load_prompt
from jinja2 import Template
import json

from typing import List
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator # 👈 确保导入 ConfigDict

SRSItemName = Literal[
    "关系维度 (Relationship)",
    "目标与话题维度 (Goals and Topics)",
    "方法与风格维度 (Approach or Method)",
    "整体评价 (Overall)",
]


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    item: SRSItemName
    score: int = Field(ge=0, le=4)
    evidence_pos: List[str] = Field(max_length=2)
    evidence_neg: List[str] = Field(max_length=2)
    thought: str = Field(max_length=24, pattern=r"^[^\n\r]{0,24}$")


class Items(BaseModel):  # 用对象包一层
    model_config = ConfigDict(extra="forbid", strict=True)

    items: List[Item] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def _validate_order(self) -> "Items":
        expected: list[str] = [
            "关系维度 (Relationship)",
            "目标与话题维度 (Goals and Topics)",
            "方法与风格维度 (Approach or Method)",
            "整体评价 (Overall)",
        ]
        actual = [it.item for it in self.items]
        if actual != expected:
            raise ValueError("SRS items must be in the exact required order")
        return self


class SRS(EvaluationMethod):

    async def evaluate(self, gpt_api, dialogue: Any, profile: dict = None) -> dict[str, float]:
        """评估对话质量"""
        scores: list[Item] = []
        
        prompt = load_prompt("srs", "srs","cn")
        
        template = Template(prompt)
        prompt = template.render(intake_form=profile, diag=dialogue)
        # print(f"SRS - {SRS} prompt: {prompt}")
        messages=[{"role": "user", "content": prompt}]

        last_err: Exception | None = None
        for attempt in range(3):
            try:
                criteria_output = await self.chat_api(gpt_api, messages=messages)
                validated = Items.model_validate(json.loads(criteria_output))
                scores.extend(validated.items)
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt >= 2:
                    raise
                messages = messages + [
                    {
                        "role": "user",
                        "content": "上一次输出未通过格式校验。请严格按输出格式只输出 JSON：仅包含键 items；items 长度为 4；每项包含 item/evidence_pos/evidence_neg/thought/score。",
                    }
                ]
        else:  # pragma: no cover
            raise RuntimeError(f"Failed to get valid SRS output: {last_err}")
        

        # outputs = dict(zip(criteria_list, scores))
        
        mean_score = 0
        
        for item in scores:
            mean_score += float(item.score) * 10.0 / 4.0  # 0-4 -> 0-10

        mean_score /= len(scores)
        # mean_score = sum(scores) / len(scores) if scores else 0
        
        # outputs["sum"] = sum(scores)
        return {"client": mean_score}
    
    def get_name(self) -> str:
        return "SRS"
