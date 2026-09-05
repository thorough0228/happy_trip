"""
规则评测脚本。

读 eval_set.jsonl,对每条样本调 plan_trip,统计规则指标,输出汇总报告。

L11 改造点:
- plan_trip / build_context 改为 async,evaluate_one 改为 async,主循环用 asyncio.run
- 启动期 init_redis()(因为 cache / progress 都要 Redis)

运行:
    cd happy_trip
    python -m evaluation.run_eval
"""
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

# 把 backend 加进 sys.path,这样才能 import app.*
# (evaluation 在 happy_trip/ 根目录下,不归 backend 管)
_BACKEND_PATH = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(_BACKEND_PATH))

from pydantic import ValidationError

from app.agents.planner import plan_trip
from app.core import redis_client
from app.models.schemas import TripPlan, TripRequest
from app.planner.context import build_context
from app.planner.validation import PLACEHOLDER_MEALS, validate_plan

EVAL_SET_PATH = Path(__file__).parent / "eval_set.jsonl"
REPORT_PATH = Path(__file__).parent / "eval_report.json"


def load_eval_set() -> list[dict[str, Any]]:
    cases = []
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    return cases


async def evaluate_one(case: dict[str, Any]) -> dict[str, Any]:
    """对单条样本跑评测,返回指标 dict。"""
    req_dict = case["request"]
    req = TripRequest(**req_dict)
    metrics = {k: False for k in [
        "json_parse_ok",
        "schema_valid",
        "attraction_in_candidates",
        "hotel_in_candidates",
        "meal_in_candidates",
        "meal_grounding_ok",
        "meal_specific_ok",
        "budget_arithmetic_consistent",
        "budget_within_constraint",
        "budget_utilization_ok",
        "days_count_match",
        "hotel_nights_match",
        "attraction_count_ok",
        "hard_pass",
    ]}
    metrics["error"] = ""
    metrics["latency_sec"] = 0.0

    t0 = time.time()
    try:
        ctx = await build_context(req)
        plan = await plan_trip(req)
    except json.JSONDecodeError:
        metrics["error"] = "JSON parse failed"
        return metrics
    except ValidationError as e:
        metrics["error"] = f"Schema validation failed: {e}"
        return metrics
    except Exception as e:
        metrics["error"] = f"{type(e).__name__}: {e}"
        return metrics

    metrics["latency_sec"] = round(time.time() - t0, 2)
    metrics["json_parse_ok"] = True
    metrics["schema_valid"] = True

    # 候选集
    attraction_names = {p.name for p in ctx.attractions}
    hotel_names = {p.name for p in ctx.hotels}
    food_names = {p.name for p in ctx.food}

    # 候选约束
    if all(a.name in attraction_names for a in plan.days[0].attractions):
        for day in plan.days:
            if not all(a.name in attraction_names for a in day.attractions):
                break
        else:
            metrics["attraction_in_candidates"] = True

    if all(
        (day.hotel is None or day.hotel.name in hotel_names)
        for day in plan.days
    ):
        metrics["hotel_in_candidates"] = True

    meal_in_ok = True
    meal_grounding_ok = True
    meal_specific_ok = True
    for day in plan.days:
        for meal_type, meal in day.meals.items():
            if meal is None:
                continue
            if meal.name not in food_names:
                meal_in_ok = False
            if meal_type in ("lunch", "dinner") and meal.name not in food_names:
                meal_grounding_ok = False
            if meal.name.strip() in PLACEHOLDER_MEALS:
                meal_specific_ok = False
    metrics["meal_in_candidates"] = meal_in_ok
    metrics["meal_grounding_ok"] = meal_grounding_ok
    metrics["meal_specific_ok"] = meal_specific_ok

    # 预算一致性
    b = plan.budget
    items_sum = (
        b.total_attractions + b.total_hotels + b.total_meals + b.total_transportation
    )
    if items_sum > 0:
        if abs(b.total - items_sum) / items_sum <= 0.05:
            metrics["budget_arithmetic_consistent"] = True

    # 预算不超
    if b.total <= req.budget_constraint.amount:
        metrics["budget_within_constraint"] = True

    # 天数匹配
    if len(plan.days) == req.travel_days:
        metrics["days_count_match"] = True

    # 酒店晚数(语义修正):sum(days[i].hotel.nights) == travel_days - 1
    # 因为 LLM 可能在每晚都输出 nights=1(同一家酒店连住),而不是每晚输出总晚数
    total_nights = sum(
        (day.hotel.nights if day.hotel else 0) for day in plan.days
    )
    expected_nights = max(1, req.travel_days - 1)
    if total_nights == expected_nights:
        metrics["hotel_nights_match"] = True

    # 每天至少 1 个景点
    if all(len(day.attractions) >= 1 for day in plan.days):
        metrics["attraction_count_ok"] = True

    # 预算利用率(分档下限,与 validation.py 保持一致)
    user_budget = req.budget_constraint.amount
    budget_level = req.budget_constraint.level
    util_min = {"economy": 0.50, "standard": 0.70, "premium": 0.85}.get(budget_level, 0.70)
    if user_budget > 0 and b.total > 0:
        if b.total / user_budget >= util_min:
            metrics["budget_utilization_ok"] = True

    # hard_pass = 所有硬指标都通过
    hard_keys = [
        "json_parse_ok", "schema_valid", "attraction_in_candidates",
        "hotel_in_candidates", "meal_in_candidates", "meal_grounding_ok",
        "meal_specific_ok", "budget_arithmetic_consistent",
        "budget_within_constraint", "budget_utilization_ok", "days_count_match",
        "hotel_nights_match", "attraction_count_ok",
    ]
    metrics["hard_pass"] = all(metrics[k] for k in hard_keys)

    return metrics


async def main_async():
    cases = load_eval_set()
    print(f"加载 {len(cases)} 条评测样本\n")

    # 每个 case 之间 sleep,避免高德 API QPS 限制
    # (每个 case 跑 3 POI + 1 weather,连续跑 20 个 case 容易触发 CUQPS_HAS_EXCEEDED_THE_LIMIT)
    INTERVAL_SEC = 3

    per_case = []
    for i, case in enumerate(cases, 1):
        label = case.get("label", case.get("id", f"case_{i}"))
        print(f"[{i}/{len(cases)}] {label} ...", end=" ", flush=True)
        m = await evaluate_one(case)
        m["id"] = case.get("id", f"case_{i}")
        m["label"] = label
        per_case.append(m)
        status = "✓" if m.get("hard_pass") else "✗"
        err = f" ({m['error']})" if m.get("error") else ""
        print(f"{status}  {m['latency_sec']}s{err}")

        # 下一个 case 之前 sleep(避开高德 QPS)
        if i < len(cases):
            await asyncio.sleep(INTERVAL_SEC)

    # 汇总
    metric_keys = [
        "json_parse_ok", "schema_valid", "attraction_in_candidates",
        "hotel_in_candidates", "meal_in_candidates", "meal_grounding_ok",
        "meal_specific_ok", "budget_arithmetic_consistent",
        "budget_within_constraint", "budget_utilization_ok", "days_count_match",
        "hotel_nights_match", "attraction_count_ok", "hard_pass",
    ]
    summary = {
        "total_cases": len(per_case),
        "metric_pass_rate": {},
        "avg_latency_sec": round(
            statistics.mean(m["latency_sec"] for m in per_case if m["latency_sec"] > 0),
            2,
        ) if any(m["latency_sec"] > 0 for m in per_case) else 0,
    }
    for k in metric_keys:
        passed = sum(1 for m in per_case if m.get(k))
        summary["metric_pass_rate"][k] = f"{passed}/{len(per_case)} ({passed/len(per_case):.1%})"

    print("\n" + "=" * 60)
    print("汇总报告")
    print("=" * 60)
    print(f"样本数: {summary['total_cases']}")
    print(f"平均耗时: {summary['avg_latency_sec']}s\n")
    for k, v in summary["metric_pass_rate"].items():
        print(f"  {k:36s} {v}")

    # 写出报告
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "per_case": per_case}, f, ensure_ascii=False, indent=2)
    print(f"\n详细报告写入: {REPORT_PATH}")


def main():
    """同步包裹:启动期 init_redis(),用 asyncio.run 跑 async 主循环,退出前 close。"""
    async def _run():
        await redis_client.init_redis()
        try:
            await main_async()
        finally:
            await redis_client.close_redis()
    asyncio.run(_run())


if __name__ == "__main__":
    main()