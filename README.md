<div align="center">

# 🧳 Happy Trip Planner

### 真实数据驱动的旅行规划助手 — 让 LLM 只做编排,事实交给外部 API

Happy Trip 把景点、酒店、餐厅、价格、天气全部从外部 API 召回并打包成 PlannerContext,
LLM 只能在事实范围内编排,凭据程序控制、硬规则校验、可量化评测,杜绝凭空编造。

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white)](https://vuejs.org/)
[![Redis](https://img.shields.io/badge/Redis-5%2B-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![Amap](https://img.shields.io/badge/POI-高德地图-1677FF)](https://lbs.amap.com/)
[![Eval: 12 hard rules](https://img.shields.io/badge/Eval-12%20hard%20rules-brightgreen)](evaluation/run_eval.py)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-blue)](LICENSE)

[项目结构](#项目结构) · [系统架构](#系统架构) · [设计亮点](#设计亮点) · [快速开始](#快速开始) · [评测体系](#评测体系)

</div>

---

## ✨ 为什么是 Happy Trip

大多数 LLM 旅行助手是"凭印象编造行程"的赌博 — 景点可能不存在,价格随便估,酒店名是幻觉。Happy Trip 把一次旅行拆成可追溯、可校验、可评测的过程:

- 🧠 **PlannerContext 协议** — 外部事实(高德 POI / 天气 / 票价)由程序收集并打包,LLM 只在事实范围内编排,事实不会被"创作"
- 🛡️ **双轨防御** — prompt 软约束 + 15 项硬规则校验 + 反思重试循环,既靠 LLM 自觉也靠程序强制
- 💰 **预算账本** — 酒店估价、票价、规则餐饮全部由代码算,LLM 不允许自报数字,杜绝价格幻觉
- 🌧️ **天气感知行程** — Intent 阶段拉高德实时天气,雨天引导 LLM 优先安排室内景点
- ⚡ **异步任务 + SSE 推送** — `POST /api/trip/plan` 立即返回 task_id,前端订阅 SSE 拿实时进度和最终结果,不再 30~90 秒干等
- 🗄️ **Redis 后端(可选)** — 高德 POI/天气缓存 + 任务状态走 Redis;未配置或不可用时静默降级,主流程不受影响
- 🧪 **可量化质量** — 20 条冻结样本、15 项硬规则、45-55% hard_pass 稳态,跑多次取平均,质量可追溯

所有景点与餐厅数据均来自**高德真实 POI**;所有价格来自**静态票价表 + 规则估价**;LLM 输出的每一项都能在 PlannerContext 里找到出处。

---

<a id="系统架构"></a>

## 🏗️ 系统架构

```
用户请求 (Home.vue 表单)
   │
   ▼
POST /api/trip/plan  ──→  立即返回 {task_id}
   │                            │
   │                       (Redis ht:task:{id} 600s TTL)
   │                            │
   ▼                            ▼
BackgroundTasks 启动           GET /api/trip/stream/{task_id}
   │                            (前端 EventSource 订阅)
   ▼                            │
后端收集事实(程序控制)            │
   ├─ 高德 POI 搜索(景点/酒店/餐厅) │
   ├─ 高德天气 API              │
   └─ 静态票价表 / 规则估价       │
   │                            │
   ▼                            ▼
编译 PlannerContext  ──→  progress 事件 (stage + 0-100)
   │
   ▼
LLM 编排(async chat, 单次输出)
   │
   ▼
硬规则校验 (validate_plan)
   ├─ 候选约束:景点/酒店/餐厅必须在候选中
   ├─ 预算一致性:各项加总 = total(±5%)
   └─ 多样性:同一餐厅不重复
   │
   ▼
失败 → 带错误反馈重试(最多 3 次)
   │
   ▼
成功 → progress.complete_task 写入 Redis  ──→  SSE done 事件(完整 TripPlan)
   │                                            │
   ▼                                            ▼
_enrich_locations                          前端 Result.vue 渲染行程
(回填坐标,防止 LLM 编经纬度)                DayMap.vue 高德地图
```

```
| 层        | 技术 |
| -------- | --- |
| 后端框架     | FastAPI 0.115+ + Uvicorn + asyncio |
| Agent 编排 | 自建 Plan-and-Execute + 轻量 Reflexion(不依赖 LangGraph) |
| LLM      | OpenAI 兼容 SDK(`AsyncOpenAI`),支持 minimax M3 / OpenAI / 智谱 等 |
| 外部数据    | 高德地图 V3 API(POI / 天气,带 1h Redis 缓存) |
| 状态/缓存   | redis.asyncio,key 前缀 `ht:cache:` / `ht:task:` |
| 异步推送    | sse-starlette `EventSourceResponse` |
| 前端      | Vue 3 + TypeScript + Vite + Ant Design Vue |
| 前端地图    | 高德 Web JS API(动态加载) |
| 评估脚本    | Python(规则评测,15 项硬指标) |
```

---

<a id="设计亮点"></a>

## 🔑 设计亮点

**1. PlannerContext 协议 — 候选池封闭世界约束**
所有景点 / 酒店 / 餐厅必须来自高德 API 搜索结果,LLM 不得凭空生成名字。`build_context()` 一次召回三类 POI + 价格填充 + 日期展开 + 天气快照,打包成 `PlannerContext`,LLM 只能在 ctx 范围内编排。`validate_plan` 强制检查每一项 `name` 是否在 ctx 的 `attractions` / `hotels` / `food` 集合里,不在则交给 reviewer 软提示。

**2. 双轨防御 — 软约束 + 硬规则 + Reviewer 软提示**
- **prompt 软约束**:`build_prompt` 的 system 部分枚举 9 条硬性指令(候选约束、价格约束、多样性、餐饮 grounding 等),引导 LLM 自觉
- **15 项硬规则**:`validate_plan` 跑候选约束、预算一致性、预算利用率、路径优化、Time Check、天数匹配、餐厅多样性等确定性检查
- **Reviewer 软提示(替代反思重试)**:业务校验不通过**不再让 LLM 重生成**,而是由 `agents/reviewer.py` 单独调一次 LLM,基于错误列表生成 2-4 条中文警告追加到 `TripPlan.notes`。这样省 token(避免 1 次失败触发 2-3 次 LLM 重生成),且保留可观测性(用户能看到具体哪里不准确)
- **Pydantic schema 失败仍重试**:JSON 损坏 / 字段缺失是致命错,保留 1 次重试

**3. Plan-and-Execute + 轻量 Reflexion — 不依赖 Agent 框架**
没用 LangGraph / ReAct / AutoGPT。旅行规划工具调用固定(POI / 天气 / 票价),程序决定调什么,LLM 决定怎么编排。一次外部数据收集 + LLM 一次输出完整 JSON + Reviewer 软提示,代码量小、行为可控、省 token。

**4. 预算账本 — 价格不让 LLM 编**
LLM 经常幻觉价格。Happy Trip 强制:
- 景点价格:静态票价表 `attraction_price.json`(按城市 × 景点索引,区分淡/旺/平季)
- 酒店价格:`base × 城市档位系数 × 住宿类型系数 × 间数 × 晚数` 规则估价
- 餐饮价格:按 `餐次 × 人数` 规则估价
LLM 只能引用候选 POI 的 `cost` 字段,不允许自报数字。`budget_arithmetic_consistent` 规则再校验各项加总 = total(±5%);`budget_utilization_ok` 校验总成本不小于用户预算的 80%(统一阈值),防止 LLM 偷懒出低价行程。

**5. 天气感知行程**
`build_context` 拉取行程日期的天气预报(高德 V3 weatherInfo,extensions=all),写入 `PlannerContext.weather`。LLM 在 prompt 里看到逐日天气,雨雪天会优先选博物馆、展馆等室内景点。超过预报范围(>3 天)时降级为 `unknown`,不中断规划。

**6. 异步任务 + SSE 推送**
`POST /api/trip/plan` 在 `BackgroundTasks` 里跑 `plan_trip`,立即返回 `{task_id}`。前端用 `EventSource` 订阅 `GET /api/trip/stream/{task_id}`,服务端 0.5s 轮询 Redis 推 `progress` 事件(stage + 0~100),终态推 `done`(完整 TripPlan)或 `failed`(错误信息)后关闭流。EventSource 自带断线重连,客户端在终态主动 `source.close()` 终止重连。
**避坑**:自定义事件名用 `progress` / `done` / `failed` 而非 `error`,因为 EventSource 的 `error` 既是自定义事件名也是浏览器原生连接错误事件名,会冲突。

**7. Redis 后端 — 缓存 + 任务状态(可选,优雅降级)**
- `services/cache.py`:高德 POI / 天气结果存 Redis(key `ht:cache:*`),TTL 1h,JSON 序列化。`stats()` 用 `scan_iter` 避免 `KEYS *` 阻塞。
- `services/progress.py`:任务状态存 Redis STRING(JSON,key `ht:task:{task_id}`),`create_task` 时一次性 `SET ... EX 600`,后续 update/complete 不重置 TTL。
- **Redis 不可用时静默降级**:`REDIS_URL` 未配置 / ping 失败时,`cache.py` 所有操作透传(`get` 返回 None,`set` / `clear` no-op),`progress.py` 降级到模块内内存 dict(`_memory_tasks`,带 asyncio.Lock 保护)。整个降级无任何副作用,**不影响主流程稳定性** — 只是重复请求会每次重新查高德,且后端重启后内存版 task 丢失(SSE 流拿到 `failed: task expired` 后前端跳回首页)。
- **为什么不完全 no-op**:SSE 客户端订阅的 task 必须有存储,完全透传会让整个异步任务机制失效。降级到内存 dict 是最小可用方案。

**8. 多关键词餐饮召回**
高德餐饮 POI 在中型城市候选池偏小(丽江、大理 meal_in_candidates 通过率约 70%)。`search_food` 用 4 个默认桶(`餐厅` / `美食` / `本地特色` / `小吃`)分别搜索,合并去重,比单关键词召回多 2-3 倍候选。

**9. JSON 提取的栈式配对算法**
reasoning 模型(如 M3)的响应混杂大量 thinking 块,里面可能有伪 JSON(Python 字面量、JSON 片段)。`extract_json` 遍历所有 `{` 起点,栈式配对找匹配的 `}`,用 `json.loads` 验证,返回最长合法候选 — 不会被伪 JSON 误导。

**10. 坐标回填防 LLM 幻觉**
LLM 输出 `TripPlan` 时**不**输出经纬度(怕它编),后端 `_enrich_locations` 用 name 映射回填 PlannerContext 里 POI 的真实坐标,专门给前端 `DayMap` 用。

**11. 路径优化(FloatTrip 风格)**
单天景点暴力枚举全排列,haversine 计算总路程,选最短排列重写 attractions 顺序,重算每个节点的 `dist_from_prev_km`。保证 `best_km ≤ original_km`(原始排列是候选项之一)。Meals/hotel 保持原位不动(happy_trip 没有 period 时段概念)。复杂度 N!,实际行程 2-5 个景点完全可接受。
前端 `DayMap` 默认画直线连线(蓝色),异步调 `GET /api/trip/route/walking` 拿真实路网 polyline 替换为绿色实线。高德响应按坐标对 Redis 缓存 24h,同一对景点二次访问直接命中。

**12. Time Check Agent(开放时间验证,FloatTrip 风格)**
独立 Agent 验证 plan 中每个景点的开放时间是否与行程日期冲突(闭馆日、营业时段、节假日)。CoT 推理 → 输出 conflicts → 嵌入主循环共用重试 budget(reviewer 不管时间)。POI.opening_hours 字段从高德 V3 `business.opening_hours` 解析,缺失则跳过(降级不报错)。职责分离避免 reviewer 与 Time Check 双重干预震荡。

---

<a id="快速开始"></a>

## 🚀 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/thorough0228/happy_trip.git
cd happy_trip
```

### 2. (可选)启动 Redis

Redis 是**可选依赖** — 启动期 `redis.ping()` 失败时静默降级,主流程照常运行:
- `cache.py` 透传(get 永远返回 None,set / clear / stats no-op),重复请求每次重新查高德
- `progress.py` 降级到模块内内存 dict,SSE 流仍能跑,但后端重启后 task 丢失

如果想用上缓存和跨重启的 task 跟踪,启动 Redis:

```bash
# Docker(推荐)
docker run -d --name happy-trip-redis -p 6379:6379 redis:7-alpine

# 或本地
redis-server
```

不启动也完全可以正常使用 — 启动日志会显示 `[redis] REDIS_URL 未配置,跳过 Redis(降级为内存 / 透传)` 或 `[redis] 连接失败,降级为内存 / 透传`。

### 3. 配置环境变量

```bash
cd backend
cp .env.example .env
```

编辑 `backend/.env`:

```bash
# LLM 配置(支持 minimax / OpenAI / 智谱 等 OpenAI 兼容服务)
LLM_API_KEY=your_llm_api_key
LLM_BASE_URL=https://api.minimaxi.com/v1
LLM_MODEL_ID=MiniMax-M3
LLM_THINKING=disabled  # M3 支持 enabled/disabled,M2.x 系列关不掉

# 高德地图 API Key(必填)
AMAP_API_KEY=your_amap_key

# Redis(可选,留空则降级为内存 / 透传)
# REDIS_URL=redis://localhost:6379/0
```

```bash
cd ../frontend
cp .env.example .env
```

编辑 `frontend/.env`:

```bash
VITE_API_BASE_URL=http://localhost:7000
VITE_AMAP_WEB_KEY=your_amap_web_key   # 与后端 Key 不同,需单独申请
```

### 4. 启动后端

```bash
cd ../backend
conda create -n happy_trip python=3.11 -y    # 项目已配置 conda 环境
conda activate happy_trip
pip install -r requirements.txt
python run.py
```

启动后会看到 `[redis] connected to redis://localhost:6379/0`,然后访问:
- API 文档:http://localhost:7000/docs
- 健康检查:http://localhost:7000/health

### 5. 启动前端

新开终端:

```bash
cd frontend
npm install
npm run dev
```

访问:http://localhost:5173

### 6. 跑一次端到端

填表(目的地 / 日期 / 人数 / 预算 / 偏好)→ 提交 → 立即跳转 Result 页 → 进度条动起来 → 完成后渲染行程卡片 + 高德地图标记。

---

## 📁 项目结构

```
happy_trip/
├── backend/                         # 后端(FastAPI 异步应用)
│   ├── app/
│   │   ├── core/                    # 基础设施层
│   │   │   └── redis_client.py      # Redis 单例(可选)+ lifespan 启动期 ping(失败降级)
│   │   ├── agents/
│   │   │   └── planner.py           # Plan-and-Execute + Reflexion 主循环
│   │   ├── api/
│   │   │   ├── main.py              # FastAPI app + lifespan
│   │   │   └── routes/
│   │   │       └── trip.py          # POST /plan + GET /stream/{id}
│   │   ├── models/
│   │   │   ├── schemas.py           # TripRequest / TripPlan / Day / Budget
│   │   │   └── poi.py               # POI 领域模型 + location 解析
│   │   ├── planner/                 # 核心业务逻辑
│   │   │   ├── context.py           # PlannerContext 编译(async)
│   │   │   ├── pois.py              # 景点召回(async)
│   │   │   ├── hotels.py            # 酒店召回(async)
│   │   │   ├── food.py              # 餐饮召回(多关键词桶,async)
│   │   │   ├── weather.py           # 天气快照(async)
│   │   │   ├── dates.py             # 日期展开
│   │   │   ├── geo.py               # haversine 球面距离工具
│   │   │   ├── optimize.py          # 单天路径优化(暴力枚举 + haversine)
│   │   │   ├── pricing.py           # 票价表 + 酒店/餐饮规则估价
│   │   │   └── validation.py        # 15 项硬规则校验
│   │   └── services/
│   │       ├── amap.py              # 高德 V3 HTTP(async,httpx.AsyncClient)
│   │       ├── llm.py               # AsyncOpenAI + JSON 提取
│   │       ├── cache.py             # Redis 通用缓存(`ht:cache:` 前缀,不可用时透传)
│   │       └── progress.py          # Redis 任务状态(`ht:task:` 前缀,600s TTL,不可用时降级内存)
│   ├── run.py                       # uvicorn 启动入口(lifespan=on)
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                         # 真实配置(.gitignore)
├── evaluation/                      # 规则评测(独立目录)
│   ├── eval_set.jsonl               # 20 条冻结核样本
│   ├── run_eval.py                  # 评测主入口(async)
│   └── eval_report.json             # 报告输出(.gitignore)
├── frontend/                        # 前端(Vue 3)
│   ├── src/
│   │   ├── views/
│   │   │   ├── Home.vue             # 旅行需求表单 → /result?task_id=...
│   │   │   └── Result.vue           # 行程结果 + SSE 实时进度 + 地图
│   │   ├── components/
│   │   │   └── DayMap.vue           # 单日地图(高德 JS API 动态加载)
│   │   ├── services/
│   │   │   ├── api.ts               # axios + planTrip + streamTask(AsyncGenerator)
│   │   │   └── amapLoader.ts        # 高德 JS SDK 加载器
│   │   ├── types/
│   │   │   └── index.ts             # TS 类型镜像 Pydantic
│   │   └── router/
│   │       └── index.ts
│   ├── package.json
│   ├── vite.config.ts
│   └── .env.example
└── .gitignore
```

---

<a id="评测体系"></a>

## 🧪 评测体系

### 评估设计

```
冻结输入(eval_set.jsonl 20 条)    真实 LLM 调用
 目的地/日期/人数/预算/偏好        PlannerContext → plan_trip
        │                              │
        └──── build_context 共享 ──────┘
                       │
                  最终 TripPlan
                       │
            ┌──────────┴──────────┐
            ▼                     ▼
    15 项硬规则(G1-G15)      候选约束 / 预算算术 / 利用率 / 路径优化 / Time Check
    (确定性,零 LLM 成本)      / 餐厅多样性
```

- **输入冻结**:20 条样本覆盖 11 个城市、3 种人数类型、确定可复现
- **纯确定性评分**:15 项硬规则全部由 Python 代码执行,不依赖 LLM 评委,跑一次评测零额外 API 成本
- **业务校验不重试**:`hard_pass` 反映的是 LLM 一次输出的合规度(plan 仍可能带 reviewer 软警告)。多次跑取平均以减少 LLM 随机性影响

### 核心指标

| 指标 | 含义 |
|---|---|
| `json_parse_ok` | LLM 输出能解析为合法 JSON |
| `schema_valid` | Pydantic schema 校验通过 |
| `attraction_in_candidates` | 景点名在候选 POI 列表中 |
| `hotel_in_candidates` | 酒店名在候选 POI 列表中 |
| `meal_in_candidates` | 餐厅名在候选 POI 列表中 |
| `meal_grounding_ok` | 早午晚三餐都命中候选,不是占位词 |
| `budget_arithmetic_consistent` | `budget.total = 各项加总(±5%)` |
| `budget_within_constraint` | 总预算不超用户预算上限 |
| `budget_utilization_ok` | `total / 用户预算 ≥ 80%`(统一阈值),防 LLM 偷懒出低价 |
| `days_count_match` | `days` 数组长度 = `travel_days` |
| `hotel_nights_match` | 酒店晚数合计 = `travel_days - 1` |
| `attraction_count_ok` | 每天至少 1 个景点 |
| `route_optimized_ok` | 至少一条 `dist_from_prev_km > 0`(后端确实跑了路径优化) |
| `time_check_ok` | ctx 中至少一个 POI 有 `opening_hours`(高德返回了营业时间数据,Time Check 有数据可查) |
| `hard_pass` | 上面 15 项硬指标全部通过 |

### 快速运行

```bash
conda activate happy_trip
cd happy_trip

# 跑一次评测(5-10 分钟;case 之间 sleep 3s 避高德 QPS 限流)
python -m evaluation.run_eval

# 报告写入 evaluation/eval_report.json(.gitignore)
```

### 已知限制

- **中型城市 POI 候选不足**:丽江、大理等城市的餐饮 POI 候选池较小,`meal_in_candidates` 通过率约 70%
- **LLM thinking 关闭对 M3 部分生效**:响应时间从 30s 降到 ~18s,但完全关闭依赖 minimax 服务端支持
- **Redis 不可用时降级为内存版 task dict**:后端重启后 task 丢失,SSE 流拿到 `failed: task expired` 后前端跳回首页;重启前已完成的任务不受影响

### 后续优化方向

- [ ] Redis 持久化任务跟踪(当前 Redis 不可用时内存版 task 重启丢失)
- [ ] OTA 酒店实时价格接入(Amadeus / Expedia)
- [ ] 路线时间真实计算(高德路线 API)
- [ ] DPO 后训练对齐偏好
- [ ] 景点开放时间 / 闭馆日增强

---

## 🙏 致谢

- [Hello-Agents](https://github.com/datawhalechina/Hello-Agents) — Agent 设计参考
- [高德开放平台](https://lbs.amap.com/) — POI / 天气 / 地图数据
- [minimaxi](https://api.minimaxi.com/) — LLM 服务
- [sse-starlette](https://github.com/sysid/sse-starlette) — FastAPI SSE 支持

## 📄 License

[CC BY-NC-SA 4.0](LICENSE)