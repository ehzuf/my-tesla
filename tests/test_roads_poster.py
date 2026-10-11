"""高清海报测试: roads_poster_grid 的 JS 移植钉 (roads-grid.js 同一把尺 ——
改要两边一起改) / GCJ-02 与墨卡托 / 渲染冒烟 / 汇总聚合 / 端点。"""
import io
import math
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main as m
from app.tesla.repository import roads_poster_stats
from app.tesla.repository.map_roads import road_row, save_road
from app.tesla.roads_poster import render
from app.tesla.roads_poster_grid import (PosterError, PosterStats, RoadShape,
                                         cell_key, cells_for_flat, color_of,
                                         mercator, row_spans, runs_by_step,
                                         step_color, step_of, t_of, wgs_to_gcj)
from tests.map_seed_helpers import _two_point_drive

POSTER = "/tesla/map/api/roads/poster"


# ---------------------------------------------------------------- 格与色阶 (JS 对拍钉)
def test_cell_key_and_walk():
    """格键单调无碰撞 (cellKey 同式); DDA 按 CELL/2 步进逐格走 (不跳格),
    连续同格去重。"""
    assert cell_key(114.0, 22.0) == 570_000_110_000
    assert cell_key(114.5, 22.5) == 572_500_112_500
    assert cells_for_flat([114.5, 22.5]) == [572_500_112_500]
    assert cells_for_flat([114.0, 22.0, 114.0001, 22.0001]) == \
        [570_000_110_000]                       # 同格两点: 去重成一键
    walk = cells_for_flat([114.0, 22.0, 114.001, 22.0, 114.002, 22.0])
    assert walk == [570_000_110_000 + i * 1_000_000 for i in range(11)]


def test_row_spans_split():
    """推断段之外按顶点切证实段 (扁平半开, 段间共享边界顶点)。"""
    assert row_spans(5, [[1, 3]]) == [(0, 4), (6, 10)]
    assert row_spans(5, []) == [(0, 10)]
    assert row_spans(1, []) == [(0, 2)]


def test_scale_and_colors():
    """对数刻度 (1 次=0 端, max=1 端, 全 1 次单色保护) + 四锚点插值。"""
    assert (t_of(1, 100), t_of(10, 100), t_of(100, 100)) == (0.0, 0.5, 1.0)
    assert t_of(3, 1) == 0.0                     # 全 1 次: 不除零, 单色
    assert (step_of(1, 100), step_of(100, 100), step_of(5, 50)) == (0, 11, 5)
    assert color_of(0.5) == (125, 163, 77)       # 青→金 正中
    assert step_color(0) == (0x3D, 0x6F, 0xA8)   # 暗蓝 (偶尔)
    assert step_color(11) == (0xE5, 0x48, 0x4D)  # 红 (频繁)


def test_runs_by_step_shared_vertex_and_merge():
    """换档处与前段共享顶点不断线; <2 点的碎段并进前段 (runsByStep 同式)。"""
    counts = {cell_key(114.5, 22.5): 5, cell_key(114.501, 22.5): 5,
              cell_key(114.502, 22.5): 50, cell_key(114.503, 22.5): 50,
              cell_key(114.504, 22.5): 50}
    pts = [c for i in range(5) for c in (114.5 + 0.001 * i, 22.5)]
    assert runs_by_step(pts, counts, 50) == [(5, 0, 2), (11, 2, 8)]
    short = [c for i in range(3) for c in (114.5 + 0.001 * i, 22.5)]
    assert runs_by_step(short, counts, 50) == [(5, 0, 4)]   # 尾段 1 点并前段


# ---------------------------------------------------------------- 坐标换算
def test_gcj02_and_mercator():
    """境外原样返回; 境内偏移百米量级; 墨卡托原点/南北对称。"""
    assert wgs_to_gcj(10.0, 50.0) == (10.0, 50.0)
    lng, lat = wgs_to_gcj(114.05, 22.55)
    dist = math.hypot((lng - 114.05) * 111_320 * math.cos(math.radians(22.55)),
                      (lat - 22.55) * 110_540)
    assert 100 <= dist <= 800                    # 火星偏移的公开量级带
    assert abs(mercator(0.0, 0.0)[0]) < 1e-9 and abs(mercator(0.0, 0.0)[1]) < 1e-9
    assert abs(mercator(0.0, 45.0)[1] + mercator(0.0, -45.0)[1]) < 1e-9


# ---------------------------------------------------------------- 渲染冒烟
_STATS = PosterStats(drives=2, distance_km=3.4, duration_min=66,
                     first=datetime(2026, 1, 2), last=datetime(2026, 3, 4))


def _shape(lng0, lat0, d_lng, d_lat, n, gaps):
    return RoadShape(pts=[c for i in range(n)
                          for c in (lng0 + d_lng * i, lat0 + d_lat * i)],
                     gaps=gaps)


def test_render_smoke_png():
    """L 形两条路 (一条带推断段) → PNG 魔数/长边像素/非底色墨迹都在。"""
    shapes = [_shape(114.50, 22.50, 0.001, 0.0, 10, []),        # 横
              _shape(114.50, 22.50, 0.0, 0.001, 10, [[2, 6]])]  # 竖带推断段
    png = render(shapes, _STATS, 1600)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    img = Image.open(io.BytesIO(png)).convert("RGB")
    assert max(img.size) == 1600 and min(img.size) > 1600 // 2
    ink = sum(1 for y in range(0, img.height, 2)
              for x in range(0, img.width, 2)
              if img.getpixel((x, y)) != (14, 18, 25))
    assert ink > 1000                             # 路与文字都落了墨


def test_render_nothing_raises():
    """空集 / 少于 2 个顶点的集合 → PosterError (路由转 400)。"""
    for shapes in ([], [RoadShape(pts=[], gaps=[])],
                   [RoadShape(pts=[114.5, 22.5], gaps=[])]):
        with pytest.raises(PosterError):
            render(shapes, _STATS, 1600)


# ---------------------------------------------------------------- 汇总与端点
def test_roads_poster_stats_aggregation(db):
    """id 集聚合 (去重/缺 id 忽略): 行程数/里程/时长/起止, 汇总条同口径。"""
    _two_point_drive(db, 5, datetime(2026, 9, 1, 2, 0))
    _two_point_drive(db, 7, datetime(2026, 9, 3, 2, 0))
    st = roads_poster_stats(db, [7, 5, 5, 999])
    assert (st.drives, st.distance_km, st.duration_min) == (2, 24.7, 50)
    assert st.first == datetime(2026, 9, 1, 2, 0)
    assert st.last == datetime(2026, 9, 3, 2, 0)


def test_poster_endpoint(auth, db, owndb):
    """有几何的行程 → 200 PNG (带附件名); 空 ids / 全无几何 → 400。"""
    _two_point_drive(db, 5, datetime(2026, 9, 1, 2, 0))
    save_road(owndb, road_row(5, "ok", 3, [114.5, 22.5, 114.51, 22.5], 2,
                              1.2, ""))
    _two_point_drive(db, 7, datetime(2026, 9, 3, 2, 0))
    save_road(owndb, road_row(7, "failed", 3, [], 0, 0.0, "grab_fail"))

    r = auth.post(POSTER, json={"ids": [5, 7], "size": 1600})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert "filename=\"footprint.png\"" in r.headers["content-disposition"]
    assert "filename*=UTF-8''" in r.headers["content-disposition"]
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert auth.post(POSTER, json={"ids": []}).status_code == 400
    assert auth.post(POSTER, json={"ids": [7]}).status_code == 400
    assert TestClient(m.app).post(POSTER, json={"ids": [5]}).status_code == 401
