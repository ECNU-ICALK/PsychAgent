from typing import Any, Dict, List

import json
from jinja2 import Template
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ...core.base import EvaluationMethod
from ...utils import load_prompt


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
        if not (1 <= n <= 26):
            raise ValueError("item must be between 1 and 26")
        return s


class Items(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    items: List[Item] = Field(min_length=26, max_length=26)

    @model_validator(mode="after")
    def _validate_order(self) -> "Items":
        expected = [str(i) for i in range(1, 27)]
        actual = [it.item for it in self.items]
        if actual != expected:
            raise ValueError("items must be in the exact required order: '1'..'26'")
        return self


class HTAIS(EvaluationMethod):
    async def evaluate(self, gpt_api, dialogue: Any, profile: dict = None) -> Dict[str, Any]:
        prompt_template = load_prompt("HTAIS", "HTAIS", "cn")
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
                        "content": "上一次输出未通过格式校验。请严格只输出一个JSON对象，且只包含键 items；items 长度必须为 26；每项仅包含 item(“1”-“26”) 与 score(1-5整数)。",
                    }
                ]
        else:  # pragma: no cover
            raise RuntimeError(f"Failed to get valid HTAIS output: {last_err}")

        mean_score = 0.0
        for it in validated.items:
            mean_score += (float(it.score) - 1.0) * 2.5  # 1-5 -> 0-10
        mean_score /= len(validated.items)
        return {"counselor": mean_score}

    def get_name(self) -> str:
        return "HTAIS"
