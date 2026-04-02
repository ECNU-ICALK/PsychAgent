from typing import Any, Dict, ClassVar
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
    score: int = Field(ge=1, le=5)

    @field_validator("item")
    @classmethod
    def _validate_item(cls, v: str) -> str:
        s = str(v).strip()
        if not s.isdigit():
            raise ValueError("item must be a digit string")
        return s


class _ItemsBase(BaseModel):  # 用对象包一层
    model_config = ConfigDict(extra="forbid", strict=True)

    items: List[Item]

    EXPECTED_LEN: ClassVar[int]

    @model_validator(mode="after")
    def _validate_len_and_order(self) -> "_ItemsBase":
        expected = [str(i) for i in range(1, int(self.EXPECTED_LEN) + 1)]
        actual = [it.item for it in self.items]
        if actual != expected:
            raise ValueError(f"items must be in the exact required order: '1'..'{self.EXPECTED_LEN}'")
        return self


class Items14(_ItemsBase):
    EXPECTED_LEN: ClassVar[int] = 14
    items: List[Item] = Field(min_length=14, max_length=14)


class Items15(_ItemsBase):
    EXPECTED_LEN: ClassVar[int] = 15
    items: List[Item] = Field(min_length=15, max_length=15)


class Items21(_ItemsBase):
    EXPECTED_LEN: ClassVar[int] = 21
    items: List[Item] = Field(min_length=21, max_length=21)


_ITEMS_MODEL_BY_CRITERIA: dict[str, type[_ItemsBase]] = {
    "Ethics": Items15,
    "Interaction": Items14,
    "Intervention": Items15,
    "Perception": Items21,
}

class Custom_Dim(EvaluationMethod):

    async def evaluate(self, gpt_api, dialogue: Any, profile: dict = None) -> dict[str, float]:
        """评估对话质量"""
        criteria_list = ["Ethics", "Interaction", "Intervention", "Perception"]
        scores: list[Item] = []
        
        async def run_one(criteria: str) -> list[Item]:
            prompt = load_prompt("custom_dim", criteria, "cn")
            template = Template(prompt)
            prompt = template.render(intake_form=profile, diag=dialogue)
            messages = [{"role": "user", "content": prompt}]
            items_model = _ITEMS_MODEL_BY_CRITERIA.get(criteria)
            if items_model is None:
                raise ValueError(f"Unknown Custom_Dim criteria: {criteria}")

            expected_len = int(items_model.EXPECTED_LEN)
            last_err: Exception | None = None
            for attempt in range(3):
                try:
                    criteria_output = await self.chat_api(gpt_api, messages=messages)
                    validated = items_model.model_validate(json.loads(criteria_output))
                    return list(validated.items)
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    if attempt >= 2:
                        raise
                    messages = messages + [
                        {
                            "role": "user",
                            "content": f"上一次输出未通过格式校验。请严格只输出一个JSON对象，且只包含键 items；items 长度必须为 {expected_len}；items 必须按顺序包含编号 '1'..'{expected_len}'；每项仅包含 item(编号字符串) 与 score(1-5整数)。",
                        }
                    ]
            raise RuntimeError(f"Failed to get valid Custom_Dim output: {last_err}")

        items_lists = await asyncio.gather(*(run_one(c) for c in criteria_list))
        for items in items_lists:
            scores.extend(items)
        

        # outputs = dict(zip(criteria_list, scores))
        
        mean_score = 0
        
        for item in scores:
            mean_score += (float(item.score) - 1.0) * 2.5  # 1-5 -> 0-10

        mean_score /= len(scores)
        # mean_score = sum(scores) / len(scores) if scores else 0
        
        # outputs["sum"] = sum(scores)
        return {"counselor": mean_score}
    
    def get_name(self) -> str:
        return "Custom_Dim"
