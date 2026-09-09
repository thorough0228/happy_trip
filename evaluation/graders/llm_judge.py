"""
LLM 评委(可选,5 维 1-5 分)。

参考业内主流 LLM 评委设计:
- 只看最终产物(plan + 备注),不看中间路径
- temperature=0,JSON 结构化输出
- 失败时降级为 None,不影响硬规则评分
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from app.models.schemas import TripPlan, TripRequest


JUDGE_PROMPT = """你是旅游行程质量评审。请根据用户需求和最终行程,按 5 个维度 1-5 分打分(5 最好)。

用户需求:{request}

最终行程:
{plan}

只输出严格 JSON,不要额外文字:
{{
  "preference_fit": <1-5>,     // 景点是否贴合用户偏好
  "habit_fit": <1-5>,          // 节奏是否合理(人数/天数匹配)
  "route_reasonableness": <1-5>, // 动线是否顺(每天内景点集中)
  "weather_adaptation": <1-5>,   // 是否考虑天气
  "notes_quality": <1-5>         // 实用贴士是否有用
}}
"""


def judge_with_llm(req: TripRequest, plan: TripPlan) -> Optional[dict[str, int]]:
    """调 LLM 给最终 plan 评分。失败返回 None(不影响硬规则)。"""
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    model_id = os.getenv("LLM_MODEL_ID", "gpt-3.5-turbo")
    if not api_key:
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url)
        prompt = JUDGE_PROMPT.format(
            request=req.model_dump_json(),
            plan=plan.model_dump_json(indent=1)[:6000],  # 截断防超 token
        )
        resp = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        text = resp.choices[0].message.content or "{}"
        return json.loads(text)
    except Exception as e:
        print(f"[judge] LLM 评委失败(降级为 None): {e}")
        return None


def judge_avg(judge: Optional[dict[str, int]]) -> Optional[float]:
    if not judge:
        return None
    vals = [v for v in judge.values() if isinstance(v, (int, float))]
    return round(sum(vals) / len(vals), 2) if vals else None