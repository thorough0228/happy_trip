import uvicorn
from app.models.schemas import TripRequest, TripPlan

if __name__ == "__main__":
    # 在 Windows 上使用 reload 需要特殊处理
    uvicorn.run("app.api.main:app", host="0.0.0.0", port=7000, reload=True)
    req = TripRequest(
        destination="杭州",
        start_date="2026-10-01",
        travel_days=3,
        party={"adults": 2, "children": 0, "elders": 0},
        budget_constraint={"amount": 3000, "level": "standard"},
        transportation="train",
        accommodation="hotel",
        preferences=["喜欢西湖"],
        negative_constraints=["不吃辣"]
    )
    print(req.model_dump())  # 应该输出一个 dict