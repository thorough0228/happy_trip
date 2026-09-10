"""
Happy Trip 评测主入口。

参考业内主流评测框架设计:
- 输入冻结:fixture 一次性构造好 POI 候选池 + 天气,直接喂给 plan_trip 跳过外部 API
- 硬规则评分(code_graders G1-G8)+ 可选 LLM 评委
- 每个 case 跑 k 次,聚合 pass@k / pass^k
- 输出 Markdown 报告 + 落盘 transcript

运行:
    cd happy_trip
    conda activate happy_trip
    python -m evaluation.run_eval                          # 全部, k=1, 无 LLM 评委
    python -m evaluation.run_eval --k 5                    # 全部, k=5
    python -m evaluation.run_eval --only nanjing-3d-history # 单用例
    python -m evaluation.run_eval --judge                  # 开 LLM 评委
    python -m evaluation.run_eval --out eval_report.md     # 输出 Markdown
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

# 把 backend 加进 sys.path
_BACKEND_PATH = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(_BACKEND_PATH))

from pydantic import ValidationError

from app.agents.planner import plan_trip
from app.core import redis_client
from app.models.schemas import TripPlan, TripRequest
from app.planner.context import PlannerContext
from evaluation.graders.code_graders import ALL_GRADERS, grade_all


# ---- 路径 ----
FIXTURES_PATH = Path(__file__).parent / "fixtures" / "cases.json"
TRANSCRIPTS_DIR = Path(__file__).parent / "transcripts"
REPORT_JSON_DIR = Path(__file__).parent / "report_json"
REPORT_MD_DIR = Path(__file__).parent / "report_md"


def _make_report_paths(timestamp: str):
    """根据时间戳生成报告路径(具体到秒):report_json/eval_report_20260910_152939.json + report_md/eval_report_20260910_152939.md"""
    return (
        REPORT_JSON_DIR / f"eval_report_{timestamp}.json",
        REPORT_MD_DIR / f"eval_report_{timestamp}.md",
    )


# ---- Fixture 加载 ----
def load_fixtures() -> list[dict]:
    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


def build_ctx_from_fixture(fix: dict) -> tuple[TripRequest, PlannerContext]:
    """
    用 fixture 构造 PlannerContext,跳过真实的高德 API 调用。

    POI 用 fixture.pool 直接构造,visit_duration 从 pool 注入;
    weather 用 fixture.weather 注入。
    """
    from app.models.poi import POI
    from app.planner.context import PlannerContext, ClusterGroup, DayAssignment
    from app.planner.clustering import cluster_pois

    req = TripRequest(**fix["request"])

    # 构造 POI 列表
    attractions = [
        POI(
            id=f"poi_{i}",
            name=p["name"],
            address=p["address"],
            location=tuple(p["location"]) if p.get("location") else None,
            type=p.get("type", ""),
            cost=float(p.get("cost", 0)),
            opening_hours=p.get("opening_hours"),
            visit_duration=p.get("visit_duration"),
        )
        for i, p in enumerate(fix["pool"])
    ]

    # 简易聚类(每条 fixture 内 POI 数小,直接用 cluster_pois)
    clusters = cluster_pois(attractions, eps_km=2.0)

    # Day Allocation(等分):不足的补全,多的合并到前面的 day
    days_alloc: list[list[list]] = [[c] for c in clusters][: req.travel_days]
    if not days_alloc:
        days_alloc = [[attractions[: req.travel_days]]]  # fallback
    elif len(days_alloc) < req.travel_days:
        # 把多余的 cluster 平摊到现有 day
        flat = []
        for c in clusters[req.travel_days:]:
            flat.extend(c)
        for i, p in enumerate(flat):
            days_alloc[i % len(days_alloc)].append([p])

    day_assignments = [
        DayAssignment(
            day=i,
            clusters=[ClusterGroup(cluster_id=f"c{i}", pois=[p for grp in day_clusters for p in grp])],
        )
        for i, day_clusters in enumerate(days_alloc)
    ]

    # 构造天气
    from app.models.schemas import WeatherDay
    weather = [
        WeatherDay(
            day=datetime.fromisoformat(w["day"]).date(),
            weather=w.get("weather", "晴"),
            temp_max=w.get("temp_max", 25),
            temp_min=w.get("temp_min", 15),
        )
        for w in fix["weather"]
    ]

    ctx = PlannerContext(
        request=req,
        destination=req.destination,
        dates=[w.day for w in weather],
        attractions=attractions,
        weather=weather,
        day_assignments=day_assignments,
        daily_available_minutes=480,
    )
    return req, ctx


# ---- 单次跑 ----
async def run_one_trial(req: TripRequest, ctx: PlannerContext, fix: dict) -> dict:
    """跑一次 plan_trip,返回 grader 结果 + plan + 耗时。"""
    metrics: dict = {
        "grader_results": {},
        "all_pass": False,
        "latency_sec": 0.0,
        "error": "",
    }
    t0 = time.time()
    try:
        plan = await plan_trip(req, _ctx=ctx)
        metrics["latency_sec"] = round(time.time() - t0, 2)
        # 跑全部硬规则
        for name, fn in ALL_GRADERS:
            ok, detail = fn(plan, ctx, req)
            metrics["grader_results"][name] = {"pass": ok, "detail": detail}
        metrics["all_pass"] = all(r["pass"] for r in metrics["grader_results"].values())
        metrics["plan"] = plan.model_dump()
    except (json.JSONDecodeError, ValidationError) as e:
        metrics["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    except Exception as e:
        metrics["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return metrics


# ---- 聚合 ----
def aggregate_trial_results(trials: list[dict]) -> dict:
    """多次 trial 的聚合指标。"""
    n = len(trials)
    if n == 0:
        return {"pass_rate": 0.0, "pass_at_k": 0.0, "pass_pow_k": 0.0, "latency_mean": 0.0, "errors": 0}
    pass_count = sum(1 for t in trials if t.get("all_pass"))
    error_count = sum(1 for t in trials if t.get("error"))
    latencies = [t["latency_sec"] for t in trials if t["latency_sec"] > 0]

    # 单个 grader 通过率
    grader_pass: dict = {}
    for t in trials:
        for name, r in t.get("grader_results", {}).items():
            grader_pass.setdefault(name, []).append(r["pass"])
    grader_rates = {n: f"{sum(p)}/{len(p)}" for n, p in grader_pass.items()}

    return {
        "pass_rate": round(pass_count / n, 2),
        "pass_at_k": 1.0 if pass_count >= 1 else 0.0,
        "pass_pow_k": 1.0 if pass_count == n else 0.0,
        "latency_mean": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "errors": error_count,
        "grader_rates": grader_rates,
    }


# ---- 落盘 transcript ----
def save_transcript(fix_id: str, plan: TripPlan | None, results: list[dict]) -> None:
    TRANSCRIPTS_DIR.mkdir(exist_ok=True)
    path = TRANSCRIPTS_DIR / f"{fix_id}.json"
    path.write_text(
        json.dumps(
            {
                "id": fix_id,
                "plan": plan.model_dump() if plan else None,
                "trials": [
                    {k: v for k, v in t.items() if k != "plan"}
                    for t in results
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ---- Markdown 报告 ----
def render_markdown_report(per_case: list[dict]) -> str:
    lines = ["# Happy Trip 评测报告", ""]
    lines.append(f"_生成时间:{datetime.now().isoformat(timespec='seconds')}_")
    lines.append("")

    # 按 tier 分节
    tiers: dict[str, list[dict]] = {}
    for c in per_case:
        tiers.setdefault(c["tier"], []).append(c)

    for tier in ["regression", "capability"]:
        if tier not in tiers:
            continue
        lines.append(f"## {tier}")
        lines.append("")
        lines.append("| 用例 | k | pass率 | pass@k | pass^k | 耗时均值 | 错误数 | 评委均分 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for c in tiers[tier]:
            j = c.get("judge_avg")
            j_str = f"{j:.2f}" if j is not None else "—"
            lines.append(
                f"| {c['label']} | {c['k']} | "
                f"{int(c['agg']['pass_rate'] * c['k'])}/{c['k']} | "
                f"{'✓' if c['agg']['pass_at_k'] else '✗'} | "
                f"{'✓' if c['agg']['pass_pow_k'] else '✗'} | "
                f"{c['agg']['latency_mean']}s | {c['agg']['errors']} | {j_str} |"
            )
        lines.append("")

    # 汇总
    total = len(per_case)
    pass_at_k_count = sum(1 for c in per_case if c["agg"]["pass_at_k"] > 0)
    pass_pow_k_count = sum(1 for c in per_case if c["agg"]["pass_pow_k"] > 0)
    avg_latency = (
        statistics.mean(c["agg"]["latency_mean"] for c in per_case if c["agg"]["latency_mean"] > 0)
        if any(c["agg"]["latency_mean"] > 0 for c in per_case)
        else 0
    )

    lines.append("## 汇总")
    lines.append("")
    lines.append(f"- 样本数:**{total}**")
    lines.append(f"- pass@k 比例:**{pass_at_k_count}/{total} = {pass_at_k_count/total:.1%}**")
    lines.append(f"- pass^k 比例(全稳定):**{pass_pow_k_count}/{total} = {pass_pow_k_count/total:.1%}**")
    lines.append(f"- 平均耗时:**{avg_latency:.2f}s**")
    judge_avgs = [c["judge_avg"] for c in per_case if c.get("judge_avg") is not None]
    if judge_avgs:
        lines.append(f"- LLM 评委均分均值:**{statistics.mean(judge_avgs):.2f}/5**")
    return "\n".join(lines)


# ---- CLI ----
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Happy Trip 评测")
    p.add_argument("--k", type=int, default=1, help="每个用例跑 k 次")
    p.add_argument("--only", type=str, default=None, help="只跑指定用例 id(可模糊匹配)")
    p.add_argument("--judge", action="store_true", help="启用 LLM 评委")
    p.add_argument("--out", type=str, default=None, help="输出 Markdown 报告路径")
    return p.parse_args()


async def main_async():
    args = parse_args()
    # 每次跑评测生成带时间戳的文件名(具体到秒)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_report_json_path, default_report_md_path = _make_report_paths(timestamp)
    # 确保报告目录存在(首次运行自动创建)
    default_report_json_path.parent.mkdir(parents=True, exist_ok=True)
    default_report_md_path.parent.mkdir(parents=True, exist_ok=True)
    cases = load_fixtures()
    if args.only:
        cases = [c for c in cases if args.only.lower() in c["id"].lower()]
        if not cases:
            print(f"未找到匹配的 case: {args.only}")
            return

    print(f"加载 {len(cases)} 条评测样本(k={args.k}, LLM 评委={args.judge})\n")

    from evaluation.graders.llm_judge import judge_with_llm, judge_avg

    INTERVAL_SEC = 1.0  # 用 fixture 跑不需要调真实高德,可以更快
    per_case = []

    for i, fix in enumerate(cases, 1):
        req, ctx = build_ctx_from_fixture(fix)
        trials = []
        for k in range(args.k):
            print(f"[{i}/{len(cases)}] {fix['label']} (trial {k+1}/{args.k}) ...", end=" ", flush=True)
            t = await run_one_trial(req, ctx, fix)
            trials.append(t)
            status = "[OK]" if t.get("all_pass") else "[FAIL]"
            err = f" {t['error'][:60]}" if t.get("error") else ""
            print(f"{status} {t['latency_sec']}s{err}")

        # LLM 评委(只对最后一次 trial 的 plan 评)
        judge = None
        if args.judge and trials and trials[-1].get("plan"):
            last_plan = TripPlan(**trials[-1]["plan"])
            judge = judge_with_llm(req, last_plan)

        agg = aggregate_trial_results(trials)
        per_case.append(
            {
                "id": fix["id"],
                "label": fix["label"],
                "tier": fix.get("tier", "regression"),
                "k": args.k,
                "agg": agg,
                "judge": judge,
                "judge_avg": judge_avg(judge),
                "trials": trials,
            }
        )

        # 落盘 transcript
        if trials and trials[-1].get("plan"):
            save_transcript(fix["id"], TripPlan(**trials[-1]["plan"]), trials)

        if i < len(cases):
            await asyncio.sleep(INTERVAL_SEC)

    # JSON 报告(带时间戳的文件名,如 eval_report_20260910_152939.json)
    default_report_json_path.write_text(
        json.dumps({"summary": _summary(per_case), "per_case": per_case}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n详细 JSON 报告: {default_report_json_path}")

    # Markdown 报告(同样带时间戳)
    md = render_markdown_report(per_case)
    if args.out:
        # 用户指定路径,确保父目录存在
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_path = default_report_md_path
    out_path.write_text(md, encoding="utf-8")
    print(f"Markdown 报告: {out_path}")
    print("\n" + md)


def _summary(per_case: list[dict]) -> dict:
    total = len(per_case)
    pass_at_k = sum(1 for c in per_case if c["agg"]["pass_at_k"])
    pass_pow_k = sum(1 for c in per_case if c["agg"]["pass_pow_k"])
    return {
        "total": total,
        "pass_at_k": f"{pass_at_k}/{total}",
        "pass_pow_k": f"{pass_pow_k}/{total}",
        "pass_at_k_rate": round(pass_at_k / total, 2) if total else 0,
    }


def main():
    async def _run():
        await redis_client.init_redis()
        try:
            await main_async()
        finally:
            await redis_client.close_redis()
    asyncio.run(_run())


if __name__ == "__main__":
    main()