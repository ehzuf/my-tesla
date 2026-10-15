"""常去地点的取名策略 (2026-10-02 #171「用 GPS 坐标结合高德, 不要信
teslamate」, 2026-10-15 从 place_worker 拆出 —— worker 只留轮次编排):

regeocode → 展示名: 最近的 POI ≤300m 优先 (送学停校门外也算「到学校」),
其次 ≤100m 的道路名 (停路边), 都没有用 区+街道 兜底。取不出回 ""
(调用方落 skip, 同 v 不再重试)。纯函数无副作用, 测试直喂 Regeocode。
"""
from .roads_amap_wire import AmapSpot, Regeocode

_POI_MAX_M = 300.0        # POI 认定半径: 送学停校门 300m 外也是「到学校」
_ROAD_MAX_M = 100.0       # 没有近 POI 时贴路名 (停路边)


def _nearest(spots: list[AmapSpot]) -> tuple[str, float] | None:
    """列表里距离最近的一条 (pois/roads 不保证按距离排, 自己挑;
    距离缺/坏的条目跳过)。"""
    best: AmapSpot | None = None
    best_d = float("inf")
    for spot in spots:
        if spot.distance is not None and spot.distance < best_d:
            best_d, best = spot.distance, spot
    return (best.name, best_d) if best is not None else None


def pick_place_name(geo: Regeocode) -> str:
    """regeocode → 展示名 (策略见模块头)。取不出回 "" (落 skip, 同 v 不再
    重试)。"""
    poi = _nearest(geo.pois)
    if poi and poi[0] and poi[1] <= _POI_MAX_M:
        return poi[0][:60]
    road = _nearest(geo.roads)
    if road and road[0] and road[1] <= _ROAD_MAX_M:
        return road[0][:60]
    return (geo.address.district + geo.address.township)[:60]
