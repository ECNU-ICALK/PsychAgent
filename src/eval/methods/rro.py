from __future__ import annotations

from typing import Any, Dict, List, Set

import json
from jinja2 import Template
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..core.base import EvaluationMethod
from ..utils import load_prompt


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
        n = int(s)
        if not (1 <= n <= 24):
            raise ValueError("item must be between 1 and 24")
        return s


class Items(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    items: List[Item] = Field(min_length=24, max_length=24)

    @model_validator(mode="after")
    def _validate_order(self) -> "Items":
        expected = [str(i) for i in range(1, 25)]
        actual = [it.item for it in self.items]
        if actual != expected:
            raise ValueError("items must be in the exact required order: '1'..'24'")
        return self

class RRO(EvaluationMethod):
    REVERSE_SCORED_ITEMS: Set[int] = {2, 7, 16, 17, 18, 19, 24}

    FACTOR_DEFINITIONS: Dict[str, List[int]] = {
        "Client Realism": [1, 8, 9, 10, 12, 20, 17, 16, 22],
        "Client Genuineness": [4, 11, 18, 24],
        "counselor Realism": [2, 6, 15, 21, 23, 19],
        "counselor Genuineness": [3, 5, 7, 13, 14],
    }

    @staticmethod
    def _to_0_10(score_1_5: int) -> float:
        return (float(score_1_5) - 1.0) * 2.5

    def _factor_avg(self, item_numbers: List[int], scores_0_10: Dict[int, float]) -> float:
        values: list[float] = []
        for item_num in item_numbers:
            if item_num not in scores_0_10:
                continue
            v = float(scores_0_10[item_num])
            if item_num in self.REVERSE_SCORED_ITEMS:
                v = 10.0 - v
            values.append(v)
        return sum(values) / len(values) if values else 0.0

    async def evaluate(self, gpt_api, dialogue: Any, profile: dict = None) -> Dict[str, float]:
        prompt_template = load_prompt("RRO", "RRO", "cn")
        prompt = Template(prompt_template).render(intake_form=profile, diag=dialogue)

        messages = [{"role": "user", "content": prompt}]
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                criteria_output = await self.chat_api(gpt_api, messages=messages)
                validated = Items.model_validate(json.loads(criteria_output))
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt >= 2:
                    raise
                messages = messages + [
                    {
                        "role": "user",
                        "content": "上一次输出未通过格式校验。请严格只输出一个JSON对象，且只包含键 items；items 长度必须为 24，每项仅包含 item(“1”-“24”) 与 score(1-5整数)。",
                    }
                ]
        else:  # pragma: no cover
            raise RuntimeError(f"Failed to get valid RRO output: {last_err}")

        scores_0_10: dict[int, float] = {}
        for it in validated.items:
            item_num = int(it.item)
            scores_0_10[item_num] = self._to_0_10(it.score)

        client_realism = self._factor_avg(self.FACTOR_DEFINITIONS["Client Realism"], scores_0_10)
        client_genuineness = self._factor_avg(self.FACTOR_DEFINITIONS["Client Genuineness"], scores_0_10)
        counselor_realism = self._factor_avg(self.FACTOR_DEFINITIONS["counselor Realism"], scores_0_10)
        counselor_genuineness = self._factor_avg(self.FACTOR_DEFINITIONS["counselor Genuineness"], scores_0_10)

        return {
            "client": (client_realism + client_genuineness) / 2.0,
            "counselor": (counselor_realism + counselor_genuineness) / 2.0,
        }

    def get_name(self) -> str:
        return "RRO"
