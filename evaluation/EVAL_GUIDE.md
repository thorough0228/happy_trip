# Happy Trip 评测体系使用手册

## 快速开始

```bash
cd happy_trip
conda activate agents

# 跑全部 30 个 case,k=1,无 LLM 评委(~5-10 分钟)
python -m evaluation.run_eval

# 跑全部,k=5 评估稳定性(~25-50 分钟)
python -m evaluation.run_eval --k 5

# 跑单个用例
python -m evaluation.run_eval --only nanjing-3d-history --k 3

# 启用 LLM 评委(每条用例 1 次额外的 LLM 调用)
python -m evaluation.run_eval --judge --only hangzhou-3d-couple-budget

# 指定输出路径(注意:每次跑默认也会按时间戳生成 eval_report_YYYYMMDD_HHMMSS.{json,md})
python -m evaluation.run_eval --k 5 --out my_report.md
```

## 架构

参考业内主流评测框架设计:

```
evaluation/
├── run_eval.py              # CLI 入口 + 聚合 + 报告渲染
├── EVAL_GUIDE.md            # 本文件
├── fixtures/
│   └── cases.json           # 30 条冻结用例(14 regression + 16 capability)
├── graders/
│   ├── code_graders.py      # G1-G8 硬规则(纯 Python,零 LLM 成本)
│   └── llm_judge.py         # 5 维 LLM 评分(可选,--judge 启用)
└── transcripts/             # 运行后自动落盘,记录每次 trial 的产物
    └── <case_id>.json
```

报告输出文件命名:`eval_report_<YYYYMMDD_HHMMSS>.{json,md}`(每次跑独立,便于对比与回溯)。

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

- **regression** — 基准用例,**14 条**,预期 ≈100% 通过,用于防退步
- **capability** — 挑战用例,**16 条**(小池、雨天、严寒、边界、多 cluster 等),用于提升目标

### 当前用例覆盖(30 条)

#### regression (14 条 — 主流城市 + 常规场景)

| ID | | 天数 | | 城市/场景 |
|---|---|---|---|---|
| `hangzhou-3d-couple-budget` | | 3 | | 杭州/西湖文化 |
| `nanjing-3d-history` | | 3 | | 南京/历史 |
| `beijing-5d-friends-culture` | | 5 | | 北京/文化古迹 |
| `xian-3d-history-tighter` | | 3 | | 西安/历史 |
| `chengdu-3d-leisure-family` | | 3 | | 成都/休闲 |
| `xiamen-3d-coastal` | | 3 | | 厦门/海岛 |
| `qingdao-3d-coastal` | | 3 | | 青岛/海滨 |
| `suzhou-2d-short` | | 2 | | 苏州/园林 |
| `shanghai-3d-modern` | | 3 | | 上海/都市 |
| `kunn-ming-3d-flowers` | | 3 | | 昆明/春城 |
| `wuhan-3d-history` | | 3 | | 武汉/文化 |
| `tianjin-2d-short` | | 2 | | 天津/历史 |
| `qingdao-2d-short` | | 2 | | 青岛/海滨短途 |
| `xiamen-3d-multi-clusters` | | 3 | | 厦门/多 cluster |

#### capability (16 条 — 挑战 / 边界 / 极端)

| ID | | 天数 | | 场景类别 | 挑战点 |
|---|---|---|---|---|---|
| `lijiang-3d-small-pool` | | 3 | | 小池子 | POI < 6 |
| `sanya-4d-beach-capability` | | 4 | | 海岛 | | 多 cluster 沙滩 |
| `harbin-3d-winter-capability` | | 3 | | 严寒 | | 雪 + 低温 |
| `dali-3d-small-pool-capability` | | 3 | | 小池子 | POI = 4 |
| `guiyang-3d-small-pool-capability` | | 3 | | 小池子 | POI = 4 |
| `beijing-3d-rainy-capability` | | 3 | | 雨天 | | 全雨 3 天 |
| `chongqing-3d-mountain-capability` | | 3 | | 高温 | | 40°C |
| `beijing-1d-ultrashort` | | 1 | | **边界:超短** | | 1 天行程 |
| `shanghai-5d-ultralong` | | 5 | | **边界:超长** | | 5 天行程 |
| `nanjing-3d-empty-prefs` | | 3 | | **边界:无偏好** | | preferences=[] |
| `xian-3d-full-constraints` | | 3 | | **边界:全避雷** | | negative_constraints 满载 |
| `xian-3d-multi-clusters-conflict` | | 3 | | **多样性:多 cluster 冲突** | | 8 POI / 多 cluster |
| `qingdao-3d-no-opening-hours` | | 3 | | **极端:无营业时间** | | opening_hours 全 null |
| `nanjing-3d-all-weather-unknown` | | 3 | | **极端:天气全 unknown** | | 超预报范围 |
| `beijing-shanghai-cross-city` | | 3 | | **多样性:跨城跳跃** | | 北京/上海 POI 混在一起 |
| `xiamen-3d-multi-clusters` (在 regression) | | 3 | | 多 cluster | | 7 POI 跨岛 |

#### 场景维度总览

- **目的地**:南京/北京/上海/杭州/西安/成都/厦门/青岛/苏州/丽江/三亚/昆明/大理/武汉/贵阳/天津/重庆/共 17 城
- **天数**:1 / 2 / 3 / 4 / 5
- **天气**:晴 / 多云 / 小雨 / 大雨 / 雪 / unknown
- **挑战类别**:小候选池、雨天、严寒、高温、超短/超长、空偏好、全避雷、多 cluster、跨城、无营业时间、天气未知

## 报告输出

报告按时间戳命名 + **分目录** 存放,每次跑独立一份:

```
evaluation/
├── report_json/
│   └── eval_report_20260910_152939.json      # 完整 per-case 数据
├── report_md/
│   └── eval_report_20260910_152939.md        # 表格化汇总(按 tier 分节)
└── transcripts/
    └── <id>.json                             # 每个用例最后一次 trial 的 plan
```

- `report_json/eval_report_<YYYYMMDD_HHMMSS>.json` — 完整 per-case 数据(JSON 格式,机器可读)
- `report_md/eval_report_<YYYYMMDD_HHMMSS>.md` — 表格化汇总(按 tier 分节,人类可读)
- `transcripts/<id>.json` — 每个用例最后一次 trial 的 plan

历史报告**不被 .gitignore 排除**(目录已被 ignore 忽略,不入库;本地保留便于对比历史数据)。

如果用 `--out` 指定输出路径,会保留原文件名,但目录若不存在会自动创建。例如:
```bash
python -m evaluation.run_eval --out /tmp/my_report.md   # 输出到 /tmp/my_report.md
```

## 添加新用例

在 `fixtures/cases.json` 的 `cases` 数组中追加:

```json
{
  "id": "新用例-id",
  "tier": "regression 或 capability",
  "label": "可读标签",
  "request": { "destination": "...", "travel_days": 3, "preferences": [...], "negative_constraints": [...] },
  "pool": [{ "name": "...", "location": [...], "visit_duration": 60, "opening_hours": "..." }, ...],
  "weather": [{ "day": "YYYY-MM-DD", "weather": "晴", "temp_max": 25, "temp_min": 15 }]
}
```

POI 的 `visit_duration` **必须填**,否则 G2 一定失败。

新增用例时,**先确定 tier**:
- 期望 ≈100% 通过 → `regression`(防退步)
- 故意设计失败/边界 → `capability`(提升目标)

## 故障排查

- **G1 失败**:检查 `pool` 是否漏了该景点,或 LLM 幻觉
- **G2 失败**:pool 里 POI 的 visit_duration 写错,或 LLM 自编
- **G3 失败**:pool 太多大时长景点,缩短某些 visit_duration
- **G6 失败**:pool 只放1 个 POI,dist_from_prev_km 全 None
- **G7 失败**:检查 `_enrich_weather` 是否在 `_enrich_locations` 之后调用

## 已知限制

- **小池子通过率低**:丽江、大理、贵阳等城市 fixture 的 pool <5 个 POI,G3/G5 通过率下降
- **超短行程**:1 天行程易触发 G3(时间预算)— 480min 限额对短行程宽松,但 pool 过大时 LLM 倾向塞满景点
- **超长行程**:5 天行程易触发 G3 反向(POI 总时长不够填满 days × 480min,LLM 可能凑数)
- **跨城 POI**:北京/上海 POI 混在一起时,LLM 倾向按城市 group 分配,可能违反聚类约束
- **无营业时间**:POI 全无 opening_hours 时,Time Check 跳过但 G7 不受影响
- **天气全 unknown**:超3 天预报范围,plan.days.weather 为 null,G7 必失败(已知边界)
- **LLM 思考模式**:M3 开启 thinking 时 G3/G8 更易失败,关闭后改善
- **fixture 数据手工标注**:天气与 visit_duration 依赖人工构造,误差累积