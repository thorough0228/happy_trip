# Happy Trip Planner

> 一个面向真实旅行规划场景的智能旅行助手。所有景点、酒店、餐厅、价格都来自外部 API,**不让 LLM 凭空编造**。

![GitHub](https://img.shields.io/badge/license-CC%20BY--NC--SA%204.0-blue)

## 核心特性

- **真实数据驱动**:景点/酒店/餐厅从高德 API 检索,价格从静态票价表 + 规则估价,天气从高德实时 API
- **PlannerContext 协议**:把外部事实打包给 LLM,LLM 只在事实范围内编排
- **双轨防御**:prompt 软约束 + 12 项硬规则校验 + 重试循环
- **天气感知行程**:LLM 据天气调整景点(雨天改室内景点)
- **预算账本**:酒店估价、票价、规则餐饮,不在 prompt 里让 LLM 算钱
- **前端地图**:每天的景点/酒店/餐饮在地图上标点
- **异步任务 + SSE 推送**:`POST /api/trip/plan` 立即返回 task_id,前端订阅 `/api/trip/stream/{id}` 看实时进度,不再 30~90 秒干等
- **Redis 后端**:高德 POI/天气缓存 + 任务状态全部走 Redis,重启不丢、可水平扩展
- **规则评测**:20 条冻结样本,12 个规则指标,5 分钟跑完一次

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | FastAPI + Pydantic v2 |
| 异步运行时 | asyncio + httpx.AsyncClient + openai.AsyncOpenAI |
| LLM 集成 | OpenAI 兼容 SDK(支持 minimax M3 等) |
| 数据来源 | 高德地图 V3 API(POI / 天气) |
| 状态/缓存 | Redis(`redis.asyncio`)+ sse-starlette |
| 前端框架 | Vue 3 + TypeScript + Vite |
| UI 库 | Ant Design Vue |
| 前端地图 | 高德 Web JS API |
| 评估脚本 | Python(规则评测) |

## 项目结构

```
happy_trip/
├── backend/                    # 后端(FastAPI 应用)
│   ├── app/
│   │   ├── core/               # 基础设施层(L11 新增)
│   │   │   └── redis_client.py # Redis 单例 + 启动期 ping 校验
│   │   ├── agents/             # Planner Agent (prompt + 重试 + feedback)
│   │   ├── api/                # FastAPI 路由(SSE 流端点)
│   │   ├── models/             # Pydantic schema (TripRequest / TripPlan / POI)
│   │   ├── planner/            # 项目核心业务逻辑
│   │   │   ├── context.py      # PlannerContext 编译(async)
│   │   │   ├── pois.py         # 景点召回(async)
│   │   │   ├── hotels.py       # 酒店召回(async)
│   │   │   ├── food.py         # 餐饮召回(多关键词,async)
│   │   │   ├── weather.py      # 天气快照(async)
│   │   │   ├── dates.py        # 日期展开
│   │   │   ├── pricing.py      # 价格规则 + 静态票价表
│   │   │   └── validation.py   # 12 项硬规则校验
│   │   └── services/           # 外部服务封装(高德/llm/缓存/进度)
│   │       ├── amap.py         # 高德 V3 HTTP(async,httpx.AsyncClient)
│   │       ├── llm.py          # LLM 调用(async,AsyncOpenAI)
│   │       ├── cache.py        # Redis 通用缓存,ht:cache: 前缀
│   │       └── progress.py     # Redis 任务状态,ht:task: 前缀,600s TTL
│   ├── run.py                  # 启动入口(uvicorn + lifespan)
│   ├── requirements.txt
│   ├── .env.example            # 配置模板
│   └── .env                    # 真实配置(被 .gitignore 排除)
├── evaluation/                 # 规则评测(独立目录,与 backend 解耦)
│   ├── eval_set.jsonl          # 20 条冻结核样本
│   ├── run_eval.py             # 评测脚本(async 化)
│   └── eval_report.json        # 输出报告(被 .gitignore 排除)
├── frontend/                   # 前端(Vue 3)
│   ├── src/
│   │   ├── views/
│   │   │   ├── Home.vue        # 旅行需求表单(提交后跳 /result?task_id=...)
│   │   │   └── Result.vue      # 行程结果 + 实时进度 + 地图
│   │   ├── components/
│   │   │   └── DayMap.vue      # 单日地图组件
│   │   ├── services/
│   │   │   ├── api.ts          # 后端 API 客户端 + streamTask AsyncGenerator
│   │   │   └── amapLoader.ts   # 高德 JS SDK 动态加载
│   │   ├── types/
│   │   │   └── index.ts        # TypeScript 类型(含 TaskProgress / SSE event)
│   │   └── router/
│   │       └── index.ts
│   ├── package.json
│   ├── vite.config.ts
│   └── .env.example
└── .gitignore
```

## 快速开始

### 前置条件

- Python 3.11+
- Node.js 22+
- Redis 5+(本地或远程,启动期不可用会硬失败退出)
- 高德地图 API Key(申请: https://lbs.amap.com/)
- OpenAI 兼容 LLM API Key(minimax / OpenAI / 智谱 等)

### 1. 启动 Redis

任选一种:

```bash
# 本地 Docker(推荐)
docker run -d --name happy-trip-redis -p 6379:6379 redis:7-alpine

# 或本地已装 Redis
redis-server

# 或远程 Redis(填 URL 到 .env 的 REDIS_URL,见后文)
```

### 2. 启动后端

```bash
cd backend

# 创建 conda 环境(项目已配置)
conda create -n happy_trip python=3.11 -y
conda activate happy_trip

# 安装依赖(包含 redis / sse-starlette / httpx)
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env,填入 LLM_API_KEY、AMAP_API_KEY、REDIS_URL

# 启动服务(端口 7000)
python run.py
```

启动后会看到:`[redis] connected to redis://localhost:6379/0`
如果 Redis 不可用,uvicorn 会报错退出(不允许降级到内存)。

启动后访问:
- API 文档: http://localhost:7000/docs
- 健康检查: http://localhost:7000/health

### 3. 启动前端

```bash
cd frontend

# 安装依赖
npm install

# 配置环境变量
cp .env.example .env
# 编辑 .env,填入 VITE_API_BASE_URL 和 VITE_AMAP_WEB_KEY

# 启动开发服务(端口 5173)
npm run dev
```

访问: http://localhost:5173

## 环境变量

### 后端 `backend/.env`

```bash
# LLM 配置(支持 minimax / OpenAI / 智谱 等 OpenAI 兼容服务)
LLM_API_KEY=your_llm_api_key_here
LLM_BASE_URL=https://api.minimaxi.com/v1
LLM_MODEL_ID=MiniMax-M3

# Thinking 模式:enabled / adaptive / disabled(留空表示不传)
# MiniMax-M3 支持 enabled/disabled,M2.x 系列关不掉
LLM_THINKING=disabled

# 高德地图 API Key
AMAP_API_KEY=your_amap_key_here

# Redis 配置 — 缓存和任务状态的唯一存储
# 本地: redis://localhost:6379/0
# 远程: redis://:password@host:port/db
REDIS_URL=redis://localhost:6379/0
```

### 前端 `frontend/.env`

```bash
# 后端 API 地址
VITE_API_BASE_URL=http://localhost:7000

# 高德 Web 端 JS Key(和后端 Key 不同,需单独申请)
VITE_AMAP_WEB_KEY=your_amap_web_key_here
```

## API 契约

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/trip/plan` | 提交 TripRequest,**立即返回** `{task_id}`,实际规划在 BackgroundTasks 跑 |
| GET  | `/api/trip/stream/{task_id}` | SSE 流,推送 `progress` / `done` / `failed` 事件,终态后关闭流 |
| GET  | `/health` | 健康检查 |

### SSE 事件

| event 名 | data 载荷 | 触发时机 |
|---|---|---|
| `progress` | `{status, stage, progress}` | 阶段性进度(`progress` 0~100,`stage` 中文描述) |
| `done` | TripPlan(完整 JSON) | 任务完成 |
| `failed` | `{error}` | 任务失败 / task 不存在 / task 已过期(>600s) |

> 不用 `error` 作为 event 名,是因为 EventSource 的 `error` 既是自定义事件名又是浏览器原生连接错误事件名,会冲突。客户端应监听 `failed` 区分业务失败和连接中断。

## 评估

20 条冻结核样本覆盖 11 个城市、3 种人数类型、3 种预算档位:

```bash
conda activate happy_trip
cd happy_trip

# 跑评测(5-10 分钟,需要 .env 已配 LLM_API_KEY / AMAP_API_KEY / REDIS_URL)
python -m evaluation.run_eval
```

### 评测指标

| 指标 | 含义 |
|---|---|
| `json_parse_ok` | LLM 输出能解析为合法 JSON |
| `schema_valid` | Pydantic schema 校验通过 |
| `attraction_in_candidates` | 景点名在候选 POI 列表中 |
| `hotel_in_candidates` | 酒店名在候选 POI 列表中 |
| `meal_in_candidates` | 餐厅名在候选 POI 列表中 |
| `meal_grounding_ok` | 早午晚三餐都命中候选,不是占位词 |
| `budget_arithmetic_consistent` | budget.total = 各项加总(±5%) |
| `budget_within_constraint` | 总预算不超用户预算上限 |
| `days_count_match` | days 数组长度 = travel_days |
| `hotel_nights_match` | 酒店晚数合计 = travel_days - 1 |
| `attraction_count_ok` | 每天至少 1 个景点 |
| `hard_pass` | 上面 12 项硬指标全部通过 |

实际 hard_pass 稳态: **45-55%**(受 LLM 随机性影响,跑多次取平均更准)

## 核心架构:PlannerContext 协议

trip_planner 最重要的设计思想:**不让 LLM 凭空编造旅行事实**。

```
用户请求
  ↓
POST /api/trip/plan → 返回 task_id
  ↓
后端 BackgroundTasks 启动,异步执行:
  ├─ 高德 POI 搜索(景点/酒店/餐厅)
  ├─ 高德天气 API
  └─ 静态票价表
  ↓
编译 PlannerContext(把所有事实打包)
  ↓
LLM 接收 PlannerContext,在事实范围内编排
  ↓
硬规则校验
  ├─ 候选约束(景点/酒店/餐厅必须在候选中)
  ├─ 预算一致性
  └─ 多样性(同一餐厅不重复)
  ↓
失败 → 带错误反馈重试(最多 3 次)
  ↓
成功 → 写入 Redis task → SSE 推 done 事件
  ↓
前端 EventSource 收到 done,渲染行程
```

前端全程通过 SSE 流拿到进度(`progress` event,带 stage + progress 0~100)和最终结果(`done` event),无需长轮询。

## 设计模式与技术选型

### Planner Agent 设计模式:**Plan-and-Execute + 轻量 Reflexion**

**没有采用 ReAct、AutoGPT、LangGraph 等 agent 框架**。采用的是更朴素的模式:

| 模式 | 是否使用 | 原因 |
|---|---|---|
| **Plan-and-Execute** | ✅ **使用** | 旅行规划工具调用固定(POI / 天气 / 票价),程序决定调什么,LLM 决定怎么编排 |
| **Reflexion**(反思重试) | ✅ **使用** | validate_plan 失败时,把错误信息反馈给 LLM 让它重生成 |
| ReAct(思考-行动循环) | ❌ 不使用 | LLM 自己决定调工具,但旅行规划流程已知,不需要这种灵活性 |
| AutoGPT / LangGraph | ❌ 不使用 | 过度设计,会增加复杂度和成本 |

**具体含义**(L11 异步版本):

```python
# 用户提交后,后端立即返回 task_id,实际规划在 BackgroundTasks 跑
@router.post("/plan")
async def plan(req: TripRequest, bg: BackgroundTasks):
    task = await progress.create_task()
    bg.add_task(_run_plan, task.task_id, req)
    return {"task_id": task.task_id}

# 一次外部数据收集(程序控制,不是 LLM 控制)
async def _run_plan(task_id, req):
    ctx = await build_context(req)    # 高德 POI + 天气 + 票价表,Redis 缓存
    messages = build_prompt(req, ctx)
    raw = await chat(messages)         # AsyncOpenAI 单次调用
    for attempt in range(MAX_RETRIES + 1):
        plan = TripPlan.model_validate_json(raw)
        errors = validate_plan(plan, ctx)
        if not errors:
            await progress.complete_task(task_id, plan.model_dump())
            return
        messages = _build_retry_messages(req, ctx, errors)
```

### 任务进度协议:Redis STRING + SSE

**为什么不用 LangChain / LlamaIndex 等框架**:

- **更可控**:LLM 调用细节自己写,出问题能直接定位
- **更轻量**:依赖少,部署简单
- **更易学**:不绑定框架,核心代码就是 plain Python
- **够用**:本项目逻辑用框架反而增加抽象成本

如果未来需要更复杂的工具编排(比如让 LLM 自己决定要不要查汇率、要不要查交通),可以引入 LangGraph 局部使用,不重写整体架构。

### 技术栈依赖

| 组件 | 选型 | 备注 |
|---|---|---|
| LLM SDK | `openai.AsyncOpenAI` | 兼容 SDK,不是 LangChain,直接调 API |
| Schema 校验 | Pydantic v2 | TripRequest / TripPlan / POI 全部 Pydantic |
| 后端框架 | FastAPI | 用 `BackgroundTasks` + `lifespan` 跑异步任务 |
| SSE | sse-starlette | `EventSourceResponse` + async generator |
| HTTP 客户端 | httpx.AsyncClient | 高德 API 全异步,共享连接池 |
| 缓存 | Redis (`redis.asyncio`) | `ht:cache:` 前缀,JSON 序列化,1h TTL |
| 任务状态 | Redis STRING | `ht:task:{task_id}`,600s TTL,创建时一次性 SET |
| 前端框架 | Vue 3 + Vite + TypeScript | 不引入 Nuxt/Next 这类 SSR |
| UI 库 | Ant Design Vue | 不混用 Element Plus |
| 地图 SDK | 高德 Web JS API(动态加载) | 不是 Mapbox / Leaflet |
| SSE 客户端 | `EventSource` + AsyncGenerator | 避开 native `error` 事件冲突,自定义 `failed` |

### Redis 硬失败设计

L11 起,SSE 任务状态完全依赖 Redis(`ht:task:{id}`,TTL 600s)。**启动期 `redis.ping()` 失败会让 uvicorn 报错退出**,不允许降级到内存 dict。理由:

- task_id 是 SSE 流客户端订阅的唯一标识,跨进程 / 跨重启必须可恢复
- 内存 dict 让客户端拿到"幽灵 task"(后端重启后查不到,流静默断开)
- 生产环境必须配 Redis,显式报错比"看似能用实际丢状态"更安全

## 已知限制

- **LLM thinking 关闭对 MiniMax-M3 部分生效**:响应时间从 30 秒降到 ~18 秒,但完全关闭依赖 minimax 服务端支持
- **中型城市 POI 候选不足**:丽江、大理 等城市的餐饮 POI 候选池较小,meal_in_candidates 通过率约 70%
- **Redis 单点**:当前部署假设单 Redis 实例,生产环境需要主从 / Sentinel / Cluster 配合

## 后续优化方向

- [x] Redis 持久化缓存(L11 完成)
- [ ] 多 Redis 部署支持(主从 / Sentinel)
- [ ] OTA 酒店实时价格接入(Amadeus / Expedia)
- [ ] 路线时间真实计算(高德路线 API)
- [ ] DPO 后训练对齐偏好
- [ ] 景点开放时间/闭馆日增强

## 致谢

- [Hello-Agents](https://github.com/datawhalechina/Hello-Agents) - Agent 设计参考
- [高德开放平台](https://lbs.amap.com/) - POI / 天气 / 地图数据
- [minimaxi](https://api.minimaxi.com/) - LLM 服务
- [sse-starlette](https://github.com/sysid/sse-starlette) - FastAPI SSE 支持

## 许可证

CC BY-NC-SA 4.0