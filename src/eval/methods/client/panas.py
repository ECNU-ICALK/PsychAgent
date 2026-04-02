from typing import Any, Dict
import re


from ...core.base import EvaluationMethod
from ...utils import load_prompt
from jinja2 import Template
import json

from typing import List
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator # 👈 确保导入 ConfigDict

PANASItemName = Literal[
    "Interested",
    "Excited",
    "Strong",
    "Enthusiastic",
    "Proud",
    "Alert",
    "Inspired",
    "Determined",
    "Attentive",
    "Active",
    "Distressed",
    "Upset",
    "Guilty",
    "Scared",
    "Hostile",
    "Irritable",
    "Ashamed",
    "Nervous",
    "Jittery",
    "Afraid",
]

_PANAS_ORDER: list[str] = [
    "Interested",
    "Excited",
    "Strong",
    "Enthusiastic",
    "Proud",
    "Alert",
    "Inspired",
    "Determined",
    "Attentive",
    "Active",
    "Distressed",
    "Upset",
    "Guilty",
    "Scared",
    "Hostile",
    "Irritable",
    "Ashamed",
    "Nervous",
    "Jittery",
    "Afraid",
]


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    item: PANASItemName
    score: int = Field(ge=1, le=5)


class Items(BaseModel):  # 用对象包一层
    model_config = ConfigDict(extra="forbid", strict=True)

    items: List[Item] = Field(min_length=20, max_length=20)

    @model_validator(mode="after")
    def _validate_order(self) -> "Items":
        names = [it.item for it in self.items]
        if names != _PANAS_ORDER:
            raise ValueError("PANAS items must be in the exact required order")
        return self

class PANAS(EvaluationMethod):

    def _parse_panas_response(self, data: list) -> float:
        """解析PANAS量表的响应"""
        # 首先，将列表转换为一个查找字典，方便快速获取分数
        # key是 'Interested', 'Excited' 等, value 是 2, 1 等
        def _norm(s: str) -> str:
            return re.sub(r"\s+", "", str(s or "")).lower()

        data_lookup = {_norm(entry.get("item")): entry.get("score") for entry in data if isinstance(entry, dict)}
        
        scores = {}
        
        # 您的原始情感列表（作为处理的基准）
        emotions = ['Interested', 'Excited', 'Strong', 'Enthusiastic', 'Proud', 'Alert', 'Inspired', 'Determined', 'Attentive', 'Active','Distressed', 'Upset', 'Guilty', 'Scared', 'Hostile', 'Irritable', 'Ashamed', 'Nervous', 'Jittery', 'Afraid']

        for emotion in emotions:
            # 从查找字典中获取原始分数
            original_score = data_lookup.get(_norm(emotion))
            
            if original_score is not None:
                # 关键：应用您完全相同的分数计算逻辑
                # (原始分数-1) * 2.5
                scores[f'panas_{emotion.lower()}'] = (original_score - 1) * 2.5


        # --- 从这里开始，下面的所有逻辑都与您的原始函数完全相同 ---
        
        # 计算正面情绪和负面情绪总分
        # (列表字段保持不变)
        
        
        positive_emotions = ['interested', 'excited', 'strong', 'enthusiastic', 'proud', 'alert', 'inspired', 'determined', 'attentive', 'active'] 
        negative_emotions = ['distressed', 'upset', 'guilty', 'scared', 'hostile', 'irritable', 'ashamed', 'nervous', 'jittery','afraid']
        
        positive_total = sum(scores.get(f'panas_{emotion}', 0) for emotion in positive_emotions)
        negative_total = sum(scores.get(f'panas_{emotion}', 0) for emotion in negative_emotions)
        
        final_scores = {}
        
        num_positive = len(positive_emotions)
        num_negative = len(negative_emotions)

        final_scores['positive'] = positive_total / num_positive if num_positive > 0 else 0
        final_scores['negative'] = negative_total / num_negative if num_negative > 0 else 0
        
        # (分数计算方式保持不变)
        final_score = (final_scores['positive'] - final_scores['negative'] + 10) / 2  # 转换为0-10分制
        
        return final_score

    async def evaluate(self, gpt_api, dialogue: Any, profile: dict = None) -> dict[str, float]:
        """评估对话质量"""
        prompt = load_prompt("panas", "panas","cn")
        
        template = Template(prompt)
        prompt = template.render(intake_form=profile, diag=dialogue)

        # print(f"panas - panas prompt: {prompt}")

        messages=[{"role": "user", "content": prompt}]

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
                        "content": "上一次输出未通过格式校验。请严格只输出一个JSON对象，且只包含键 items；items 长度必须为 20；每项仅包含 item(固定情绪名) 与 score(1-5整数)，顺序必须与要求一致。",
                    }
                ]
        else:  # pragma: no cover
            raise RuntimeError(f"Failed to get valid PANAS output: {last_err}")

        # 3. 将您的数据（列表）转换为函数所需的字符串格式
        # 构建一个像 "Interested: 2\nExcited: 1\n..." 这样的字符串
        # score = {'items': [
        #     {'item': 'Interested', 'score': 2}, {'item': 'Excited', 'score': 1}, {'item': 'Strong', 'score': 3}, {'item': 'Enthusiastic', 'score': 2}, {'item': 'Proud', 'score': 3}, {'item': 'Alert', 'score': 2}, {'item': 'Inspired', 'score': 2}, {'item': 'Determined', 'score': 3}, {'item': 'Attentive', 'score': 3}, {'item': 'Active', 'score': 2}, 
        # {'item': 'Distressed', 'score': 4}, 
        # {'item': 'Upset', 'score': 4}, 
        # {'item': 'Guilty', 'score': 4}, 
        # {'item': 'Scared', 'score': 3}, 
        # {'item': 'Hostile', 'score': 2}, 
        # {'item': 'Irritable', 'score': 3}, 
        # {'item': 'Ashamed', 'score': 4}, 
        # {'item': 'Nervous', 'score': 4}, 
        # {'item': 'Jittery', 'score': 3}, 
        # {'item': 'Afraid', 'score': 4}]}
        final_score = self._parse_panas_response([it.model_dump() for it in validated.items])
        return {"client": final_score}


    def get_name(self) -> str:
        return "PANAS"
