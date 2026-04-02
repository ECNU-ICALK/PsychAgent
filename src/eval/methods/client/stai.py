from typing import Any, Dict
import re


from ...core.base import EvaluationMethod
from ...utils import load_prompt
from jinja2 import Template
import json

from typing import List
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator # 👈 确保导入 ConfigDict

STAIItemName = Literal[
    "1. 阻抗 (反向:开放度)",
    "2. 同意 (认可度)",
    "3. 恰当请求 (求助意愿)",
    "4. 叙述 (反向:当下聚焦)",
    "5. 认知探索 (深度)",
    "6. 情感探索 (深度)",
    "7. 领悟 (觉察度)",
    "8. 治疗改变 (行动力)",
]


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    item: STAIItemName
    score: int = Field(ge=0, le=4)
    evidence_pos: List[str] = Field(max_length=2)
    evidence_neg: List[str] = Field(max_length=2)
    thought: str = Field(max_length=24, pattern=r"^[^\n\r]{0,24}$")


class Items(BaseModel):  # 用对象包一层
    model_config = ConfigDict(extra="forbid", strict=True)

    items: List[Item] = Field(min_length=8, max_length=8)

    @model_validator(mode="after")
    def _validate_order(self) -> "Items":
        expected: list[str] = [
            "1. 阻抗 (反向:开放度)",
            "2. 同意 (认可度)",
            "3. 恰当请求 (求助意愿)",
            "4. 叙述 (反向:当下聚焦)",
            "5. 认知探索 (深度)",
            "6. 情感探索 (深度)",
            "7. 领悟 (觉察度)",
            "8. 治疗改变 (行动力)",
        ]
        actual = [it.item for it in self.items]
        if actual != expected:
            raise ValueError("STAI items must be in the exact required order")
        return self

class STAI(EvaluationMethod):

    async def evaluate(self, gpt_api, dialogue: Any, profile: dict = None) -> dict[str, float]:
        """评估对话质量"""
        scores: list[Item] = []
        
        prompt = load_prompt("stai", "STAI","cn")
        
        template = Template(prompt)
        prompt = template.render(intake_form=profile, diag=dialogue)
        # print(f"STAI - {STAI} prompt: {prompt}")
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
                        "content": "上一次输出未通过格式校验。请严格按输出格式只输出 JSON：仅包含键 items；items 长度为 8；每项包含 item/evidence_pos/evidence_neg/thought/score。",
                    }
                ]
        else:  # pragma: no cover
            raise RuntimeError(f"Failed to get valid STAI output: {last_err}")
        

        # outputs = dict(zip(criteria_list, scores))
        
        mean_score = 0
        
        for item in scores:
            mean_score += float(item.score) * 10.0 / 4.0  # 0-4 -> 0-10

        mean_score /= len(scores)
        # mean_score = sum(scores) / len(scores) if scores else 0
        
        # outputs["sum"] = sum(scores)
        return {"client": mean_score}
    
    def get_name(self) -> str:
        return "STAI"
