<div align="center">

# 🧳 Happy Trip Planner

### 真实数据驱动的旅行规划助手 — 让 LLM 只做编排,事实交给外部 API

Happy Trip 把景点、价格、天气从外部 API 召回并打包成 PlannerContext,
LLM 只能在事实范围内编排,凭据程序控制、硬规则校验、可量化评测,杜绝凭空编造。
(系统只规划景点 + 酒店区域建议,不规划具体酒店和餐饮)

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white)](https://vuejs.org/)
[![Redis](https://img.shields.io/badge/Redis-5%2B-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![Amap](https://img.shields.io/badge/POI-高德地图-1677FF)](https://lbs.amap.com/)
[![Eval: 8 hard rules](https://img.shields.io/badge/Eval-8%20hard%20rules-brightgreen)](evaluation/run_eval.py)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-blue)](LICENSE)

[项目结构](#项目结构) · [系统架构](#系统架构) · [设计亮点](#设计亮点) · [快速开始](#快速开始) · [评测体系](#评测体系) · [工程边界](#工程边界)

</div>

---

## ✨ 为什么是 Happy Trip

大多数 LLM 旅行助手是"凭印象编造行程"的赌博 — 景点可能不存在,价格随便估,酒店名是幻觉。Happy Trip 把一次旅行拆成可追溯、可校验、可评测的过程:

- 🧠 **PlannerContext 协议** — 外部事实(高德 POI / 天气 / 票价)由程序收集并打包,LLM 只在事实范围内编排,事实不会被"创作"
- 🛡️ **双轨防御** — prompt 软约束 + 8 项硬规则校验 + 反思重试循环,既靠 LLM 自觉也靠程序强制
- 🎫 **票价可信** — 景点票价由代码从静态票价表查询(免费则 0),LLM 不允许自报数字,杜绝价格幻觉;无预算约束,LLM 只按行程体验编排
- 🌧️ **天气感知行程** — Intent 阶段拉高德实时天气,雨天引导 LLM 优先安排室内景点
- ⚡ **异步任务 + SSE 推送** — `POST /api/trip/plan` 立即返回 task_id,前端订阅 SSE 拿实时进度和最终结果,不再 30~90 秒干等
- 🗄️ **Redis 后端(可选)** — 高德 POI/天气缓存 + 任务状态走 Redis;未配置或不可用时静默降级,主流程不受影响
- 🧪 **可量化质量** — 20 条冻结样本、8 项硬规则评分,`pass / pass@k / pass^k` 三档指标,跑多次取平均,质量可追溯

所有景点数据均来自**高德真实 POI**;所有价格来自**静态票价表**;LLM 输出的每一项都能在 PlannerContext 里找到出处。

---

<a id="系统架构"></a>

## 🏗️ 系统架构

```
用户请求 (Home.vue 表单) ─┬─→ POST /api/trip/plan ─→ 立即返回 {task_id}
                          │         │                          │
                          │         │                (Redis ht:task:{id} 600s TTL)
                          │         │                          │
                          │         ▼                          ▼
                          │  BackgroundTasks 启动       GET /api/trip/stream/{task_id}
                          │         │                          │
                          │         ▼                          ▼
                          │  build_context (planner)         │
                          │   ├─ search_attractions           │
                          │   ├─ 票价填充(pricing.py)        │
                          │   ├─ 天气快照(weather.py)         │
                          │   ├─ DBSCAN 聚类 + Day 分配      │
                          │   └─ 打包 PlannerContext          │
                          │         │                          │
                          │         ▼                          ▼
                          │  LLM 编排 (chat, 单次输出) ←─ progress 事件 (stage + 0-100)
                          │         │                          │
                          │         ▼                          │
                          │  validate_plan + time_check        │
                          │   ├─ G1 候选池封闭                │
                          │   ├─ G2 时长一致                  │
                          │   ├─ G3 时长预算                  │
                          │   └─ G5 多样性(地理 + 名称)        │
                          │         │                          │
                          │         ▼                          │
                          │  失败 → Reviewer (软警告追加 notes)│
                          │         │                          │
                          │         ▼                          ▼
                          │  _enrich_locations + _enrich_weather
                          │   └─ 防 LLM 编坐标/补全天气字段    │
                          │         │                          │
                          │         ▼                          ▼
                          │  progress.complete_task ──→  SSE done 事件(完整 TripPlan)
                          │                                            │
                          ▼                                            ▼
                  POST /api/auth/{register,login} ──→ user_id ──→ 创建 trip 历史
                                                                            │
                                                                            ▼
                                                              前端 Result.vue 渲染行程
                                                              HomeMap / DayMap.vue 高德地图
                                                              HistorySidebar.vue 历史侧栏
```

| 层        | 技术 |
| -------- | --- |
| 后端框架     | FastAPI 0.115+ + Uvicorn + asyncio |
| Agent 编排 | 自建 Plan-and-Execute + 轻量 Reflexion(不依赖 LangGraph) |
| LLM      | OpenAI 兼容 SDK(`AsyncOpenAI`),支持 minimax M3 / OpenAI / 智谱 等 |
| 外部数据    | 高德地图 V3 API(POI / 天气,带 1h Redis 缓存) |
| 状态/缓存   | redis.asyncio,key 前缀 `ht:cache:` / `ht:task:` |
| 异步推送    | sse-starlette `EventSourceResponse` |
| 用户认证    | PyJWT + PBKDF2 密码哈希 + SQLite |
| 前端      | Vue 3 + TypeScript + Vite + Ant Design Vue |
| 前端地图    | 高德 Web JS API(动态加载) |
| 评估脚本    | Python(规则评测,8 项硬指标 G1-G8) |

---

<a id="设计亮点"></a>

## 🔑 设计亮点

**1. PlannerContext 协议 — 候选池封闭世界约束**
所有景点必须来自高德 API 搜索结果,LLM 不得凭空生成名字。`build_context()` 做景点召回 + 价格填充 + DBSCAN 地理聚类 + Day 分配 + 日期展开 + 天气快照,打包成 `PlannerContext`(含 `attractions/weather/day_assignments`)。LLM 只能在 ctx 范围内编排,严格遵守 Cluster → Day 分配建议。`validate_plan` 强制检查每一项 `name` 是否在 ctx 的 `attractions` 集合里。

**2. 双轨防御 — 软约束 + 硬规则 + Reviewer 软提示**
- **prompt 软约束**:`build_prompt` 的 system 部分枚举 6 条硬性指令(候选约束、价格约束、多样性等),引导 LLM 自觉
- **确定性检查**:`validate_plan` 跑候选约束、景点多样性(同名 + 地理近邻+名称相关双重去重);plan_trip 内嵌 Time Check;评测覆盖天数匹配、路径优化、时间数据等
- **Reviewer 软提示(替代反思重试)**:业务校验不通过**不再让 LLM 重生成**,而是由 `agents/reviewer.py` 单独调一次 LLM,基于错误列表生成 2-4 条中文警告追加到 `TripPlan.notes`。这样省 token(避免 1 次失败触发 2-3 次 LLM 重生成),且保留可观测性(用户能看到具体哪里不准确)
- **Pydantic schema 失败仍重试**:JSON 损坏 / 字段缺失是致命错,保留 1 次重试

**2b. 景区重复双重判定(地理 + 名称)**
高德 POI 经常把同一景区拆成多个子点(玄武湖 / 玄武湖情侣园 / 玄武门),只比完整同名会漏判。规则:
- 两景点 haversine < 1km **且** 名称有 ≥ 2 字共同子串 → 报"疑似同一景区",让 LLM 二选一
- 双条件都满足才触发,避免故宫/天安门这类"想都玩"的真近邻被误伤

**3. Plan-and-Execute + 轻量 Reflexion — 不依赖 Agent 框架**
没用 LangGraph / ReAct / AutoGPT。旅行规划工具调用固定(POI / 天气 / 票价),程序决定调什么,LLM 决定怎么编排。一次外部数据收集 + LLM 一次输出完整 JSON + Reviewer 软提示,代码量小、行为可控、省 token。

**4. 票价透明 — 价格不让 LLM 编**
LLM 经常幻觉价格。Happy Trip 强制:
- 景点价格:静态票价表 `attraction_price.json`(按城市 × 景点索引,免费则 0)
LLM 只能引用候选 POI 的 `cost` 字段,不允许自报数字。系统不设总预算约束,也不做预算账本——只保证每处票价真实可溯。

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

**8. JSON 提取的分层算法(兼容 reasoning / 非 reasoning 模型)**
`extract_json` 按成本从低到高逐层尝试:① 整体直接是 JSON 对象(非 reasoning 模型最常见,一次 `loads` 命中)→ ② Markdown 代码围栏 ` ```json ` 提取(模型常把 JSON 包在围栏里还夹解释性文字,取解析成功且最长的围栏)→ ③ 栈式配对扫描兜底:reasoning 模型(如 M3)的响应混杂大量 thinking 块,里面可能有伪 JSON(Python 字面量、JSON 片段),遍历所有 `{` 起点栈式配对找匹配的 `}`,用 `json.loads` 验证,返回最长合法候选 — 不会被伪 JSON 误导。三层都失败时原样返回,由 Pydantic 解析兜底。

**9. 坐标回填防 LLM 幻觉**
LLM 输出 `TripPlan` 时**不**输出经纬度(怕它编),后端 `_enrich_locations` 用 name 映射回填 PlannerContext 里 POI 的真实坐标,专门给前端 `DayMap` 用。

**10. 路径优化(简化版)**
完整路径 = `A1 → A2 → ... → AN`,无起终点约束。算法暴力枚举全排列(N ≤ 7)或 2-opt 多起点(N > 7),选 haversine 总路径最短。
**无 hotel 起终点约束,无 meal 节点** — 系统不规划餐饮和具体酒店,纯景点路径优化。
复杂度 N ≤ 7 暴力枚举(N! ≤ 5040),N > 7 用 2-opt 多起点(1 原始 + 20 随机起点),保证 `best ≤ original`。
前端 `DayMap` 默认画直线连线(蓝色),异步调 `GET /api/trip/route/walking` 拿真实路网 polyline 替换为绿色实线。高德响应按坐标对 Redis 缓存 24h,同一对景点二次访问直接命中。
`Result.vue` 简化渲染:每天一个卡片,顶部显示 hotel_area_hint(LLM 建议的酒店区域),下方是按路径最优排序的景点列表。

**11. 地理聚类 + Day 分配(DBSCAN + 时间感知)**
候选 POI(20 个)在进入 LLM 前先做 **DBSCAN 聚类**(haversine 距离,eps 2km,纯 Python 无 sklearn 依赖),cluster 数由空间分布自然决定(≠ 游玩天数)。超大 cluster(>8 POI 或游玩时长 > 1.5 天容量)按贪心空间链拆分,保持空间连续。
`Cluster → Day 分配` 沿地理相邻的 chain 按**累计游玩时长**切段,每段 ≤ 每日可用时间(默认 480 分钟/8 小时,集中配置 `DEFAULT_DAILY_AVAILABLE_MIN`)。每天输出在 prompt 里标注:POI 数 / 游玩时长 / 交通缓冲 / 是否超时。
候选池总时长通常 > 总容量 — 这是"可选池"而非"必去清单",LLM 在时间约束内剪枝,validator 兜底。

**12. 景点游玩时长 visit_duration(V2)**
每个 POI 带预计游玩分钟数,来源:**名称/类型启发式**(博物馆 150min、古镇 180min、山 240min…)集中配置于 `visit_duration.py`,兜底 90min。不用 LLM 自估。
LLM 输出必须**照抄候选的 visit_duration**;后端 validator 校验:① 每天 Σvisit_duration + 交通缓冲(景点数-1 × 15min)≤ 每日可用时间,超时打回重生成;② LLM 填的时长与候选不一致则报错。

**13. Time Check Agent(开放时间验证)**
独立 Agent 验证 plan 中每个景点的开放时间是否与行程日期冲突(闭馆日、营业时段、节假日)。CoT 推理 → 输出 conflicts → 嵌入主循环共用重试 budget(reviewer 不管时间)。POI.opening_hours 字段从高德 V3 `business.opening_hours` 解析,缺失则跳过(降级不报错)。职责分离避免 reviewer 与 Time Check 双重干预震荡。

**14. 用户系统与行程历史(JWT + SQLite)**
注册/登录走 `POST /api/auth/{register,login}`,密码 PBKDF2 哈希存储(`salt:hex`,20 万轮),JWT 用 HS256 签发(`sub` 为 user_id)。受保护接口通过 `require_user_id_from_request(request: Request)` 从 `Authorization: Bearer` 头解析 user_id,缺失/无效直接 401。路由守卫(`router/index.ts`)确保未登录用户跳 `/login`,已登录用户访问 `/login` 重定向首页。行程完成后后台任务自动调 `create_trip()` 把 trip + plan_json 写入 SQLite `users.db`,`HistorySidebar` 提供历史行程抽屉列表(目的地-天数命名,如"北京-3天"),点击详情跳转 `Result.vue`,支持删除。

**15. 每日天气图标**
`PlannerContext.weather` 在 `_enrich_weather()` 阶段按日期映射到 `plan.days[].weather/temp_max/temp_min`,前端 `Result.vue` 每天卡片右上角渲染 emoji 天气 chip(晴 ☀️ / 多云 ⛅ / 雨 🌧️ / 雪 ❄️ 等)+ 温度区间,鼠标悬停显示完整描述。查不到或超出预报范围(>3 天)时该字段为 null,不显示 chip。

**16. 目的地下拉 + 静态坐标库**
主页目的地改为下拉选择(`a-select`,支持中文字符串搜索),200+ 城市覆盖直辖市/华东/华南/华中/西南/西北/华北。右侧地图默认聚焦南京;用户切换城市时先用 `AMap.Geocoder` 异步定位,**失败/超时时降级**到内置静态坐标库 `CITY_COORDS`(200+ 经纬度对),保证地图切换立即响应,不阻塞交互。

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
conda create -n agents python=3.11 -y    # 推荐用 conda 环境
conda activate agents
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

填表(目的地 / 日期 / 人数 / 偏好)→ 提交 → 立即跳转 Result 页 → 进度条动起来 → 完成后渲染行程卡片 + 高德地图标记。

---

## 📁 项目结构

```
happy_trip/
├── backend/                              # 后端(FastAPI 异步应用)
│   ├── app/
│   │   ├── core/                         # 基础设施层
│   │   │   ├── auth.py                   # JWT(HS256)+ PBKDF2 密码哈希 + get_current_user_id 依赖
│   │   │   ├── database.py               # SQLite(users + trips 表)+ 初始化与 CRUD
│   │   │   └── redis_client.py           # Redis 单例(可选)+ lifespan 启动期 ping(失败降级)
│   │   ├── agents/
│   │   │   ├── planner.py                # Plan-and-Execute 主循环(retry + enrich_locations/enrich_weather)
│   │   │   ├── reviewer.py               # 业务校验失败时生成中文警告追加到 plan.notes
│   │   │   └── time_check.py             # 开放时间冲突校验
│   │   ├── api/
│   │   │   ├── main.py                   # FastAPI app + lifespan(init_db + init_redis)
│   │   │   └── routes/
│   │   │       ├── auth.py               # POST /api/auth/{register,login}
│   │   │       ├── history.py            # GET/DELETE /api/history/(JWT 受保护)
│   │   │       └── trip.py               # POST /api/trip/plan + GET /api/trip/stream/{id}
│   │   ├── models/
│   │   │   ├── schemas.py                # TripRequest / TripPlan / Day / WeatherDay / Party
│   │   │   └── poi.py                    # POI 领域模型 + location 解析
│   │   ├── planner/                      # 核心业务逻辑
│   │   │   ├── context.py                # PlannerContext 编译(async)
│   │   │   ├── clustering.py             # DBSCAN 聚类(纯 Python,无 sklearn 依赖)
│   │   │   ├── day_allocation.py         # cluster → day 贪心分配(时间感知)
│   │   │   ├── pois.py                   # 景点召回(async)
│   │   │   ├── weather.py                # 天气快照(async)
│   │   │   ├── dates.py                  # 日期展开
│   │   │   ├── geo.py                    # haversine 球面距离工具
│   │   │   ├── optimize.py               # 单天路径优化(纯景点 haversine 最短路径)
│   │   │   ├── pricing.py                # 静态票价表(酒店/餐饮估价已停用)
│   │   │   ├── visit_duration.py         # visit_duration 启发式估算
│   │   │   └── validation.py             # 硬规则校验(候选/多样性)
│   │   └── services/
│   │       ├── amap.py                   # 高德 V3 HTTP(async + QPS 限流 + 失败短缓存)
│   │       ├── llm.py                    # AsyncOpenAI + JSON 提取(thinking 模式可控)
│   │       ├── cache.py                  # Redis 通用缓存(`ht:cache:` 前缀,不可用时透传)
│   │       └── progress.py               # Redis 任务状态(`ht:task:` 前缀,600s TTL,不可用时降级内存)
│   ├── run.py                            # uvicorn 启动入口(load_dotenv + lifespan=on)
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                              # 真实配置(.gitignore)
├── evaluation/                           # 评测框架(独立目录)
│   ├── EVAL_GUIDE.md                     # 使用手册
│   ├── fixtures/
│   │   └── cases.json                    # 20 条冻结用例(13 regression + 7 capability)
│   ├── graders/
│   │   ├── code_graders.py               # G1-G8 硬规则评分(确定性,零 LLM 成本)
│   │   └── llm_judge.py                  # 5 维 LLM 评分(--judge 启用)
│   ├── run_eval.py                       # 评测主入口(CLI + 报告渲染)
│   ├── transcripts/                      # 每次 trial 的 plan 落盘(.gitignore)
│   ├── eval_report.json                  # JSON 报告(.gitignore)
│   └── eval_report.md                    # Markdown 报告(.gitignore)
├── frontend/                             # 前端(Vue 3 + TypeScript)
│   ├── src/
│   │   ├── views/
│   │   │   ├── Home.vue                  # 旅行需求表单 + 目的地预览地图
│   │   │   ├── Result.vue                # 行程结果(每日卡片 + 天气图标 + 地图)
│   │   │   └── Login.vue                 # 登录/注册页(受路由守卫保护)
│   │   ├── components/
│   │   │   ├── HomeMap.vue               # 主页地图(AMap Geocoder + 200+ 城市静态坐标降级)
│   │   │   ├── DayMap.vue                # 单日地图(高德 JS API 动态加载 + walking route)
│   │   │   ├── HistorySidebar.vue       # 历史行程侧拉抽屉
│   │   │   └── DestinationInput.vue      # 目的地下拉(200+ 城市,可搜索)
│   │   ├── stores/
│   │   │   └── user.ts                   # 用户状态(token/profile)
│   │   ├── services/
│   │   │   ├── api.ts                    # axios + JWT 拦截器 + SSE 客户端 + history/photo API
│   │   │   └── amapLoader.ts             # 高德 JS SDK 动态加载(Geocoder/Marker plugin 按需)
│   │   ├── types/
│   │   │   └── index.ts                  # TS 类型镜像 Pydantic
│   │   ├── router/
│   │   │   └── index.ts                  # 路由守卫(未登录跳 /login)
│   │   └── stores/user.ts                # 用户状态管理
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
冻结 fixture (cases.json, 20 条)        plan_trip(req, _ctx=ctx)
 ├─ request: 用户需求                    │
 ├─ pool: POI 候选池(手工构造)           │  ← 完全跳过高德 API
 ├─ weather: 天气预报(手工构造)           │
 └─ expectations: 期望阈值(可选)         │
                       │                  │
                       └─────── ctx ─────┘
                            │
                       最终 TripPlan
                            │
                ┌───────────┴────────────┐
                ▼                        ▼
     8 项硬规则 (G1-G8)            可选 LLM 评委 (5 维 1-5)
     code_graders.py              llm_judge.py
     (确定性,零 LLM 成本)         (--judge 启用)
                │                        │
                └─────── pass@k ─────────┘
```

设计要点(参考业内主流评测框架):

- **输入冻结**:20 条 fixture 全部手工构造 POI 池和天气,直接喂给 `plan_trip(req, _ctx=ctx)`,**完全跳过**真实高德 API 调用,跑一次评测零外部成本,几秒出结果
- **mini-graph 复用**: `_ctx` 短路 `build_context`,主流程(planner → 校验 → time_check → reviewer)与线上完全一致
- **硬规则 + 可选 LLM 评委双轨**:确定性代码打分是默认,可加 `--judge` 启用 5 维 LLM 评分(只看最终 plan)
- **tier 分层**:`regression`(13 条,期望 ≈100%,防退步)+ `capability`(7 条,小池/雨天/严寒等,提升目标)
- **可复现**:同 fixture + 同模型 + 同 temperature,随机性收敛于 LLM 自身,可对比多次结果

### 核心指标

**8 项硬规则 (G1-G8)** — 业内通用评测粒度:

| 代号 | 检查内容 | 失败含义 |
|---|---|---|
| **G1 候选池封闭** | 所有景点必须在 fixture 的 pool 里 | planner 幻觉 |
| **G2 时长一致** | LLM 填的 visit_duration == 候选值 | LLM 自编时长 |
| **G3 时长预算** | 每天游玩 + 交通 ≤ 480min | 时间超载 |
| **G4 结构合法** | days == travel_days;每天 ≥1 景点 | 不完整规划 |
| **G5 多样性** | 同一天无重复/近邻+名称冲突 | 同景区重复 |
| **G6 路径优化** | 至少一条 dist_from_prev_km > 0 | 后端未跑优化 |
| **G7 天气落地** | plan.days.weather 字段已填充 | _enrich_weather 未生效 |
| **G8 LLM 响应** | plan.title 与 days 均非空 | LLM 未输出 |

`all_pass` = G1-G8 全过。**`pass@k`** = k 次中 ≥1 次通过(能力下界),**`pass^k`** = k 次全过(稳定性)。

**5 维 LLM 评分 (--judge 启用)**:preference_fit / habit_fit / route_reasonableness / weather_adaptation / notes_quality。

### 快速运行

```bash
conda activate agents
cd happy_trip

# 全部 20 条,k=1,无 LLM 评委(2-5 分钟,因走 LLM;fixture 冻结已跳过 API)
python -m evaluation.run_eval

# 全部 k=5 稳定性
python -m evaluation.run_eval --k 5

# 单用例 + 启用 LLM 评委
python -m evaluation.run_eval --only nanjing-3d-history --judge

# 输出 Markdown 报告
python -m evaluation.run_eval --k 5 --out eval_report.md

# 详细使用见 evaluation/EVAL_GUIDE.md
```

报告输出:
- `evaluation/eval_report.json` — 完整 per-case 数据
- `evaluation/eval_report.md` — 表格化汇总(按 tier 分节)
- `evaluation/transcripts/<id>.json` — 每个用例最后一次 trial 的 plan

### 已知限制

- **小池子挑战通过率低**:丽江、大理、贵阳等 fixture 的 pool <5 个 POI,G3(时长预算)与 G5(多样性)通过率下降
- **LLM thinking 关闭对 M3 部分生效**:响应时间从 30s 降到 ~18s,但完全关闭依赖 minimax 服务端支持
- **Redis 不可用时降级为内存版 task dict**:后端重启后 task 丢失,SSE 流拿到 `failed: task expired` 后前端跳回首页;重启前已完成的任务不受影响
- **fixture 手工构造**:天气与 visit_duration 依赖人工标注,误差累积;新增用例必须保证 `pool[i].visit_duration` 必填否则 G2 必失败

### 后续优化方向

- [ ] Redis 持久化任务跟踪(当前 Redis 不可用时内存版 task 重启丢失)
- [ ] OTA 酒店实时价格接入(Amadeus / Expedia)
- [ ] 路线时间真实计算(高德路线 API)
- [ ] DPO 后训练对齐偏好
- [ ] 景点开放时间 / 闭馆日增强

---

<a id="工程边界"></a>

## 🧭 工程边界

### 能力边界(In / Out of Scope)

| 能力 | 状态 | 说明 |
|---|---|---|
| 景点规划(POI 召回 + 聚类 + 按天分配) | ✅ In | 核心能力,经 20 条评测用例验证 |
| 路径优化(Haversine 暴力枚举 / 2-opt) | ✅ In | N ≤ 7 全排列,N > 7 多起点 2-opt |
| 天气感知行程 | ✅ In | 注入 `plan.days[].weather/temp_max/temp_min` |
| 用户注册 / 登录(JWT + PBKDF2) | ✅ In | 路由守卫强制未登录跳 `/login` |
| 行程历史(per-user) | ✅ In | SQLite `trips` 表,绑定 `user_id` |
| 景点票价 | ✅ In | 静态票价表 `pricing.py`,LLM 不允许自报 |
| 地图渲染与步行路线 | ✅ In | AMap JS SDK + 高德 `direction/walking` |
| 酒店预订 / OTA 对接 | ❌ Out | 系统只给 `hotel_area_hint`,不接 OTA |
| 餐厅推荐 | ❌ Out | 旧版有,已剥离,系统只规划景点 |
| 交通票务(火车票/机票) | ❌ Out | 不参与规划,无 transportation 字段 |
| 预算约束 | ❌ Out | `TripRequest` 无 budget 字段,LLM 不限制总价 |
| 实时门票价格 | ❌ Out | 用静态表替代,避免实时 OTA 接入 |
| 支付 / 下单 | ❌ Out | 行程不产生交易,只生成建议 |
| 多模态输入(图片识别) | ❌ Out | 仅文字需求 |
| 多语言支持 | ❌ Out | 仅中文 LLM prompt + 中文 UI |

### 模块依赖边界

| 层 | 目录 | 依赖 | 不允许依赖 |
|---|---|---|---|
| API | `backend/app/api/` | Agent, Core | — |
| Agent | `backend/app/agents/` | Planner, Services, Core | API |
| Planner | `backend/app/planner/` | Services, Models, Core | Agent, API |
| Services | `backend/app/services/` | Models, Core | Agent, Planner, API |
| Core | `backend/app/core/` | 仅 stdlib + 第三方 | 任何业务层 |
| 前端 Views | `frontend/src/views/` | Components, Stores, Services, Types | — |
| 前端 Components | `frontend/src/components/` | Services, Types, Vue | Views, Stores |
| 前端 Stores | `frontend/src/stores/` | localStorage, Services | Views, Components |

### 数据边界(持久化范围)

| 存储 | 内容 | 字段/Key | TTL |
|---|---|---|---|
| SQLite `users.db` | 用户 | id, username, password_hash, created_at | 永久 |
| SQLite `users.db` | 行程历史 | id, user_id, title, destination, date_range, plan_json, created_at | 永久 |
| Redis(可选) | 高德 POI/天气 | `ht:cache:*` | 1h |
| Redis(可选) | SSE 任务状态 | `ht:task:*` | 600s |
| localStorage | 用户 token + 资料 | `happy_trip_token`, `happy_trip_user` | 永久(直到手动 logout) |
| sessionStorage | 当前行程结果 | `trip_plan` | 单次会话 |

**❌ 不存储**:POI 候选池(每次实时拉)、票价表(代码常量)、LLM 对话历史(每次重新生成)、任务 progress 终态(TTL 过期即清)。

### 外部依赖边界

| 依赖 | 必需 | 降级策略 |
|---|---|---|
| 高德 API(POI / 天气 / 路线) | ✅ | 静态坐标库 200+ 城市 + 失败短缓存(60s) |
| LLM(M3 / OpenAI 兼容) | ✅ | 无降级,直接报错 |
| Redis | ❌ | 自动降级内存版 task dict(单进程有效) |
| AMap JS SDK | ✅(前端) | 显示「🗺️ 地图加载失败」提示 |
| Unsplash 图片 | ❌ | 已移除,改为无图渲染 |

### 代码层硬约束

| 约束 | 实现位置 | 防什么 |
|---|---|---|
| LLM 不输出经纬度 | `_enrich_locations` 回填 | 防坐标幻觉 |
| LLM 不输出票价 | `pricing.py` 静态表查询 | 防价格幻觉 |
| LLM 不编景点 | `validation.py` G1 候选池封闭 | 防景点幻觉 |
| LLM 不自编时长 | `validation.py` G2 时长一致 | 防时长幻觉 |
| 每天时长上限 480min | `validation.py` G3 | 防时间超载 |
| 同一天不重复 | `validation.py` G5 多样性 | 防同景区重复 |
| 高德 QPS 防护 | `amap.py` 令牌桶(0.35s/req) | 防 CUQPS_HAS_EXCEEDED_THE_LIMIT |
| 输入长度 / 范围 | Pydantic `Field(ge=)` / `min_length=` | 防异常入参 |

### 边界如何变更

边界变更必须**同步**修改以下文件:
- 新增 `TripRequest` 字段 → 前端 `types/index.ts` + 主页 `Home.vue` + 评测 `fixtures/cases.json`
- 新增外部依赖 → 更新 `requirements.txt` + `.env.example`
- 新增持久化数据 → `database.py` 新建表 + `init_db()` 加 DDL
- 新增业务能力 → 在 In Scope 表格追加,Out of Scope 同步检查

## 🙏 致谢

- [Hello-Agents](https://github.com/datawhalechina/Hello-Agents) — Agent 设计参考
- [高德开放平台](https://lbs.amap.com/) — POI / 天气 / 地图数据
- [minimaxi](https://api.minimaxi.com/) — LLM 服务
- [sse-starlette](https://github.com/sysid/sse-starlette) — FastAPI SSE 支持

## 📄 License

[CC BY-NC-SA 4.0](LICENSE)