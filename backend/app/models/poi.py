"""景点/酒店/餐厅等地点的领域模型。

不直接用高德的 dict,而是定义自己的 Pydantic 模型,这样:
1. 字段名稳定,不受高德 API 升级影响
2. 可以加自有字段(如 cost、is_attraction)
3. 有类型校验和文档作用
"""
from pydantic import BaseModel, field_validator


class POI(BaseModel):
    """通用 POI(景点/酒店/餐厅)。"""

    id: str                              # 高德 POI ID
    name: str                            # POI 名称
    address: str                         # 详细地址
    location: tuple[float, float]        # (经度, 纬度)
    type: str                            # 分类描述,如 "风景名胜;旅游景点"
    city: str | None = None              # 所属城市(L5 PlannerContext 会补)
    cost: float = 0.0                    # 票价/价格(L6 才用,先默认 0)

    @field_validator("location", mode="before")
    @classmethod
    def parse_location(cls, v):
        """高德 location 是 'lng,lat' 字符串,这里解析成 tuple[float, float]"""
        if isinstance(v, str):
            parts = v.split(",")
            return (float(parts[0]), float(parts[1]))
        return v