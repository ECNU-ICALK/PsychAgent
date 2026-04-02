from typing import Any

from ...core.base import EvaluationMethod
from ...utils import load_prompt
from jinja2 import Template
import json

from typing import List
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


DialogueRedundancyItemName = Literal["非重复与非模板化", "推进效率与信息密度"]


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    item: DialogueRedundancyItemName
    score: int = Field(ge=0, le=4)
    evidence_pos: List[str] = Field(max_length=2)
    evidence_neg: List[str] = Field(max_length=2)
    thought: str = Field(max_length=24, pattern=r"^[^\n\r]{0,24}$")


class Items(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    items: List[Item] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def _validate_order(self) -> "Items":
        expected: list[str] = ["非重复与非模板化", "推进效率与信息密度"]
        actual = [it.item for it in self.items]
        if actual != expected:
            raise ValueError("Dialogue_Redundancy items must be in the exact required order")
        return self


class Dialogue_Redundancy(EvaluationMethod):
    async def evaluate(self, gpt_api, dialogue: Any, profile: dict = None) -> dict[str, float]:
        prompt = load_prompt("dialogue_redundancy", "dialogue_redundancy", "cn")
        prompt = Template(prompt).render(diag=dialogue)
        messages = [{"role": "user", "content": prompt}]
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                out = await self.chat_api(gpt_api, messages=messages)
                validated = Items.model_validate(json.loads(out))
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt >= 2:
                    raise
                messages = messages + [
                    {
                        "role": "user",
                        "content": "上一次输出未通过格式校验。请严格按输出格式只输出 JSON：仅包含键 items；items 长度为 2；每项包含 item/evidence_pos/evidence_neg/thought/score。",
                    }
                ]
        else:  # pragma: no cover
            raise RuntimeError(f"Failed to get valid Dialogue_Redundancy output: {last_err}")

        if not validated.items:
            return {"counselor": 0.0}

        mean_score = 0.0
        for it in validated.items:
            mean_score += float(it.score) * 10.0 / 4.0  # 0-4 -> 0-10
        mean_score /= len(validated.items)
        return {"counselor": mean_score}

    def get_name(self) -> str:
        return "Dialogue_Redundancy"
