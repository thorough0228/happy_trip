# Happy Trip 评测体系使用手册

## 快速开始

```bash
cd happy_trip
conda activate happy_trip

# 跑全部 20 个 case,k=1,无 LLM 评委(~2-5 分钟)
python -m evaluation.run_eval

# 跑全部,k=5 评估稳定性
python -m evaluation.run_eval --k 5

# 跑单个用例
python -m evaluation.run_eval --only nanjing-3d-history --k 3

# 启用 LLM 评委(每条用例 1 次额外的 LLM 调用)
python -m evaluation.run_eval --judge --only hangzhou-3d-couple-budget

# 输出 Markdown 报告
python -m evaluation.run_eval --k 5 --out eval_report.md
```

## 架构

参考业内主流评测框架设计：

```
evaluation/
├── run_eval.py              # CLI 入口 + 聚合 + 报告渲染
├── EVAL_GUIDE.md            # 本文件
├── fixtures/
│   └── cases.json           # 20 条冻结用例(13 regression + 7 capability)
├── graders/
│   ├── code_graders.py      # G1-G8 硬规则(纯 Python,零 LLM 成本)
│   └── llm_judge.py         # 5 维 LLM 评分(可选,--judge 启用)
└── transcripts/             # 运行后自动落盘,记录每次 trial的产物
    └── <case_id>.json
```

## 硬规则指标(G1-G8)

| 代号 | 检查内容 | 失败含义 |
|---|---|---|
| **G1 候选池封闭** | 所有景点必须在 fixture 的 pool 里 | planner 幻觉,硬失败 |
| **G2 时长一致** | LLM 填的 visit_duration == 候选值 | LLM 自编时长 |
| **G3 时长预算** | 每天游玩 + 交通 ≤ 每日可用时间(480min) | 时间超载 |
| **G4 结构合法** | days == travel_days;每天 ≥1 景点 | 不完整规划 |
| **G5 多样性** | 同一天无重复/近邻+名称冲突 | 同景区重复 |
| **G6 路径优化** | 至少一条 dist_from_prev_km > 0 | 后端未跑优化 |
| **G7 天气落地** | plan.days.weather 字段已填充 | _enrich_weather 未生效 |
| **G8 LLM 响应** | plan.title 与 days 均非空 | LLM 未输出 |

**全过** = `all_pass = all(G1..G8)`。

## LLM 评委指标(--judge 启用)

只对最后一次 trial 的 plan 评分,5 维 1-5 分:

- `preference_fit` — 景点贴合用户偏好
- `habit_fit` — 节奏合理
- `route_reasonableness` — 动线顺畅
- `weather_adaptation` — 考虑天气
- `notes_quality` — 实用贴士质量

输出 `judge_avg` = 5 维均分。

## Fixture 设计

每条 fixture 冻结 plan_trip 的所有输入,跳过真实的高德 API:

```json
{
  "id": "nanjing-3d-history",
  "tier": "regression",        // 见下
  "label": "南京3天历史文化",
  "request": {
    "destination": "南京",
    "start_date": "2026-09-10",
    "travel_days": 3,
    "preferences": ["历史文化"],
    "negative_constraints": []
  },
  "pool": [                    // 模拟 build_context 的 POI 候选
    {"name": "总统府", "address": "...", "location": [118.797, 32.040],
     "type": "风景名胜", "cost": 35, "visit_duration": 120, "opening_hours": "08:30-18:00"}
  ],
  "weather": [                 // 模拟高德 weatherInfo
    {"day": "2026-09-10", "weather": "晴", "temp_max": 32, "temp_min": 22}
  ]
}
```

### tier 区别

- **regression** — 基准用例,13 条,预期 ≈100% 通过,用于防退步
- **capability** — 挑战用例,7 条(小池、雨天、严寒等),用于提升目标

### 当前用例覆盖

- **目的地**:南京/北京/上海/杭州/西安/成都/厦门/青岛/苏州/丽江/三亚/昆明/大理/武汉/贵阳/天津/重庆
- **天数**:2 / 3 / 4 / 5
- **天气**:晴 / 多云 / 小雨 / 大雨 / 雪
- **挑战场景**:小候选池(<5 个 POI)、雨天、雨+室内为主、严寒、低温 vs 高温

## 报告输出

- `eval_report.json` — 完整 per-case 数据
- `eval_report.md` — 表格化汇总
- `transcripts/<id>.json` — 每个用例最后一次 trial 的 plan

## 添加新用例

在 `fixtures/cases.json` 的 `cases` 数组中追加:

```json
{
  "id": "新用例-id",
  "tier": "regression 或 capability",
  "label": "可读标签",
  "request": { "destination": "...", ... },
  "pool": [{ "name": "...", "location": [...], "visit_duration": 60, "opening_hours": "..." }, ...],
  "weather": [{ "day": "YYYY-MM-DD", "weather": "晴", "temp_max": 25, "temp_min": 15 }]
}
```

POI 的 `visit_duration` **必须填**,否则 G2 一定失败。

## 故障排查

- **G1 失败**:检查 `pool` 是否漏了该景点,或 LLM 幻觉
- **G2 失败**:pool 里 POI 的 visit_duration 写错,或 LLM 自编
- **G3 失败**:pool 太多大时长景点,缩短某些 visit_duration
- **G6 失败**:pool 只放1 个 POI,dist_from_prev_km 全 None
- **G7 失败**:检查 `_enrich_weather` 是否在 `_enrich_locations` 之后调用

## 已知限制

- **小池子通过率低**:丽江、大理等城市 fixture 的 pool <5 个 POI,LLM 容易凑不够 days × min_per_day
- **LLM 思考模式**:M3 开启 thinking 时 G3/G8 更易失败,关闭后改善
- **fixture 数据手工标注**:天气和 POI 的 visit_duration 依赖人工构造,误差累积