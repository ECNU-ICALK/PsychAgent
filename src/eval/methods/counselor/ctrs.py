from typing import Any, Dict
import re
import asyncio


from ...core.base import EvaluationMethod
from ...utils import load_prompt
from jinja2 import Template

from typing import List
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field # 👈 确保导入 ConfigDict
import json

CtrsItemName = Literal[
    "understanding",
    "interpersonal_effectiveness",
    "collaboration",
    "guided_discovery",
    "focus",
    "strategy",
]


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    item: CtrsItemName
    score: int = Field(ge=0, le=6)
    evidence_pos: List[str] = Field(max_length=2)
    evidence_neg: List[str] = Field(max_length=2)
    thought: str = Field(max_length=24, pattern=r"^[^\n\r]{0,24}$")


class Items(BaseModel):  # 用对象包一层
    model_config = ConfigDict(extra="forbid", strict=True)

    items: List[Item] = Field(min_length=1, max_length=1)

class CTRS(EvaluationMethod):
    async def evaluate(self, gpt_api, dialogue: Any, profile: dict = None) -> Dict[str, float]:
        criteria_list = ["understanding", "interpersonal_effectiveness", "collaboration", "guided_discovery", "focus",
                         "strategy"]
        scores: list[Item] = []

        async def run_one(criteria: str) -> list[Item]:
            prompt = load_prompt("ctrs", criteria, "cn")
            template = Template(prompt)
            prompt = template.render(diag=dialogue)
            messages = [{"role": "user", "content": prompt}]
            last_err: Exception | None = None
            for attempt in range(3):
                try:
                    criteria_output = await self.chat_api(gpt_api, messages=messages)
                    validated = Items.model_validate(json.loads(criteria_output))
                    if validated.items[0].item != criteria:
                        raise ValueError("Mismatched item key for CTRS criterion")
                    return list(validated.items)
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    if attempt >= 2:
                        raise
                    messages = messages + [
                        {
                            "role": "user",
                            "content": "上一次输出未通过格式校验。请严格按输出格式只输出 JSON：仅包含键 items；items 长度为 1；每项包含 item/evidence_pos/evidence_neg/thought/score。",
                        }
                    ]
            raise RuntimeError(f"Failed to get valid CTRS output: {last_err}")

        items_lists = await asyncio.gather(*(run_one(c) for c in criteria_list))
        for items in items_lists:
            scores.extend(items)

        mean_score = 0
        
        if scores :
            for item in scores:
                mean_score += float(item.score) / 6.0 * 10.0  # 0-6 -> 0-10
                # print(f"item score: {item['score']}")
                # print(f"mean_score: {mean_score}")
            mean_score /= len(scores)
        else:
            mean_score = 0

        return {"counselor": mean_score}
    
    
    def get_name(self) -> str:
        return "CTRS"
