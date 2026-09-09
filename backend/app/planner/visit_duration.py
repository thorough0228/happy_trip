"""
POI 预计游玩时长(visit_duration,单位:分钟)。

V2 新增字段。高德 V3 接口没有标准化 visit_duration 字段,
LLM 自己编也不准。所以这里用**名称/类型启发式 + 配置化默认值**集中估算。

启发式优先级(从上到下):
1. POI.type 关键词(博物馆/陵墓/公园...)
2. POI.name 关键词(遗址/博物馆/寺...)
3. 兜底:DEFAULT_VISIT_DURATION

集中配置,不要散落到业务代码里。
"""
import re


# 兜底默认值(分钟) — 集中配置
DEFAULT_VISIT_DURATION = 90


# 类型关键词 → 时长(分钟)映射。
# 优先匹配更具体的类别;数字基于常见旅行经验。
_TYPE_DURATIONS: list[tuple[re.Pattern, int]] = [
    (re.compile(r"博物馆|纪念馆|博物院"), 150),
    (re.compile(r"美术馆|科技馆|水族馆"), 120),
    (re.compile(r"陵墓|陵园|墓园|塔|陵"), 90),
    (re.compile(r"古镇|古城|老街|步行街"), 180),
    (re.compile(r"公园|植物园|动物园"), 150),
    (re.compile(r"山|峰|岭|风景区|国家森林公园"), 240),
    (re.compile(r"湖|湿地|河"), 90),
    (re.compile(r"寺|庙|教堂|清真寺|道观"), 60),
    (re.compile(r"广场|购物中心|商业街|夜市"), 90),
    (re.compile(r"故居|遗址|旧址|纪念馆"), 60),
    (re.compile(r"塔|楼|阁|城墙"), 45),
    (re.compile(r"酒吧|夜店"), 120),
]


_NAME_HINTS: list[tuple[re.Pattern, int]] = [
    (re.compile(r"博物馆|纪念馆|博物院"), 150),
    (re.compile(r"美术馆|科技馆|水族馆"), 120),
    (re.compile(r"古镇|老街|步行街"), 180),
    (re.compile(r"遗址|旧址|故居"), 60),
    (re.compile(r"寺$|庙$|教堂$|塔$"), 45),
    (re.compile(r"山$|峰$"), 240),
    (re.compile(r"公园$"), 90),
    (re.compile(r"广场$|步行街$"), 60),
]


def estimate_visit_duration(poi_type: str | None, poi_name: str | None) -> int:
    """
    估算 POI 预计游玩时长(分钟)。

    优先用 name 关键词(更具体),其次 type,最后兜底。
    任何失败都返回 DEFAULT_VISIT_DURATION,从不抛错。
    """
    name = poi_name or ""
    for pat, mins in _NAME_HINTS:
        if pat.search(name):
            return mins

    type_ = poi_type or ""
    for pat, mins in _TYPE_DURATIONS:
        if pat.search(type_):
            return mins

    return DEFAULT_VISIT_DURATION