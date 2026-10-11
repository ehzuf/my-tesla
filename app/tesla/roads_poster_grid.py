"""足迹海报的坐标与计数纯逻辑: js/roads-grid.js + js/gcj02.js 的逐行移植
(同一把尺 —— 海报的热力计数/切段/四锚点色阶/火星坐标与页面完全一致, 改
要两边一起改)。无 Pillow/DB 依赖, 可单测对拍 JS 语义; 海报的数据形状
(RoadShape/PosterStats/PosterError) 也住这 —— 渲染与路由共用同一份词表。"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

CELL = 0.0002                     # 格边长 (度) ≈ 20m
GRID = 5000                       # 1/CELL
STEPS = 12                        # 色阶档数
COLORS = ((0x3D, 0x6F, 0xA8), (0x21, 0xA1, 0x79),
          (0xD9, 0xA5, 0x21), (0xE5, 0x48, 0x4D))   # 暗蓝→青→金→红


class PosterError(ValueError):
    """海报渲染的业务性失败 (没有可画的路等), 路由转 400。"""


@dataclass(frozen=True)
class RoadShape:
    """一程的渲染输入: pts 平铺 WGS-84 [lng,lat,...] + gaps 推断层区间。"""

    pts: list[float]
    gaps: list[list[int]]


@dataclass(frozen=True)
class PosterStats:
    """海报头行数字 (与汇总端点同字段的口径, id 集由调用方筛好)。"""

    drives: int
    distance_km: float
    duration_min: int
    first: datetime | None
    last: datetime | None


def cell_key(lng: float, lat: float) -> int:
    """经纬度 → 格键 (roads-grid.cellKey 同式, 格与格单调可比无碰撞)。"""
    return math.floor(lng * GRID) * 1_000_000 + math.floor(lat * GRID)


def cells_for_flat(pts: Sequence[float]) -> list[int]:
    """扁平 pts → 格键序列 (有序连续去重; DDA 按 CELL/2 步进 —— 相邻点
    200m+ 也不跳格; 折返隔几格再进该格就再计, roads-grid 同语义)。"""
    out: list[int] = []
    n = len(pts)
    if n < 2:
        return out
    if n == 2:
        return [cell_key(pts[0], pts[1])]
    last: int | None = None

    def push(k: int) -> None:
        nonlocal last
        if k != last:
            out.append(k)
            last = k

    for i in range(2, n, 2):
        x0, y0, x1, y1 = pts[i - 2], pts[i - 1], pts[i], pts[i + 1]
        dx, dy = x1 - x0, y1 - y0
        steps = max(1, math.ceil(max(abs(dx), abs(dy)) / (CELL / 2)))
        for s in range(steps):
            push(cell_key(x0 + dx * s / steps, y0 + dy * s / steps))
    push(cell_key(pts[n - 2], pts[n - 1]))
    return out


def row_spans(n: int, gaps: Sequence[Sequence[int]]) -> list[tuple[int, int]]:
    """推断层之外的已证实段: 扁平半开区间 [f0, f1) (证实段与推断段共享
    边界顶点, 两线接上不断; n = 点数)。"""
    out: list[tuple[int, int]] = []
    if n < 1:
        return out
    if not gaps:
        return [(0, n * 2)]
    v0 = 0
    for rg in gaps:
        a, b = max(0, math.floor(rg[0])), min(n - 1, math.floor(rg[1]))
        if b < a:
            continue
        if a > v0:
            out.append((v0 * 2, (a + 1) * 2))
        v0 = max(v0, b)
    if v0 < n - 1:
        out.append((v0 * 2, n * 2))
    return out


def t_of(count: int, max_count: int) -> float:
    """次数 → 0..1: 对数刻度 (1 次=0 端, max 次=1 端; 全 1 次单色保护)。"""
    if max_count <= 1:
        return 0.0
    return min(1.0, math.log(max(1, count)) / math.log(max_count))


def step_of(count: int, max_count: int) -> int:
    """次数 → 色阶档 0..STEPS-1 (切段/上色共用)。"""
    return min(STEPS - 1, round(t_of(count, max_count) * (STEPS - 1)))


def color_of(t: float) -> tuple[int, int, int]:
    """0..1 → 锚点色间逐通道线性插值 (colorOf 同式)。"""
    u = min(1.0, max(0.0, t)) * (len(COLORS) - 1)
    i = min(len(COLORS) - 2, math.floor(u))
    f = u - i
    c0, c1 = COLORS[i], COLORS[i + 1]
    return (round(c0[0] + (c1[0] - c0[0]) * f),
            round(c0[1] + (c1[1] - c0[1]) * f),
            round(c0[2] + (c1[2] - c0[2]) * f))


def step_color(step: int) -> tuple[int, int, int]:
    """色阶档 → 色 (折线与图例渐变条同源)。"""
    return color_of(step / (STEPS - 1))


def runs_by_step(pts: Sequence[float], counts: dict[int, int],
                 max_count: int) -> list[tuple[int, int, int]]:
    """路径按格次数切段: (色阶档, f0, f1) 扁平闭区间; 换档处与前段共享
    顶点不断线, <3 点碎段并前段 (runsByStep 同式)。"""
    n = len(pts) // 2
    if not n:
        return []
    runs: list[tuple[int, int, int]] = []
    cur, i0 = -1, 0
    for i in range(n):
        k = cell_key(pts[i * 2], pts[i * 2 + 1])
        b = step_of(counts.get(k, 0), max_count)
        if b != cur:
            if cur >= 0:
                runs.append((cur, i0, (i - 1) * 2))
            cur, i0 = b, (i - 1) * 2 if i > 0 else 0
    runs.append((cur, i0, (n - 1) * 2))
    if len(runs) < 2:
        return runs
    merged = [runs[0]]
    for r in runs[1:]:
        prev = merged[-1]
        if r[2] - r[1] < 4 or prev[0] == r[0]:
            merged[-1] = (prev[0], prev[1], r[2])
        else:
            merged.append(r)
    return merged


def _gcj_delta(lng: float, lat: float) -> tuple[float, float]:
    """国测局偏移量 (gcj02.js 的 delta 同式, 公开近似式精度 ~1-2m)。"""
    pi, a, ee = math.pi, 6378245.0, 0.00669342162296594323
    x, y = lng - 105.0, lat - 35.0
    d_lat = (-100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y
             + 0.2 * math.sqrt(abs(x))
             + (20.0 * math.sin(6.0 * x * pi) + 20.0 * math.sin(2.0 * x * pi)) * 2.0 / 3.0
             + (20.0 * math.sin(y * pi) + 40.0 * math.sin(y / 3.0 * pi)) * 2.0 / 3.0
             + (160.0 * math.sin(y / 12.0 * pi) + 320.0 * math.sin(y * pi / 30.0)) * 2.0 / 3.0)
    d_lng = (300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y
             + 0.1 * math.sqrt(abs(x))
             + (20.0 * math.sin(6.0 * x * pi) + 20.0 * math.sin(2.0 * x * pi)) * 2.0 / 3.0
             + (20.0 * math.sin(x * pi) + 40.0 * math.sin(x / 3.0 * pi)) * 2.0 / 3.0
             + (150.0 * math.sin(x / 12.0 * pi) + 300.0 * math.sin(x / 30.0 * pi)) * 2.0 / 3.0)
    rad = lat / 180.0 * pi
    magic = 1 - ee * math.sin(rad) ** 2
    sqrt_magic = math.sqrt(magic)
    return ((d_lng * 180.0) / (a / sqrt_magic * math.cos(rad) * pi),
            (d_lat * 180.0) / (a * (1 - ee) / (magic * sqrt_magic) * pi))


def out_of_china(lng: float, lat: float) -> bool:
    """中国域外无偏移 (gcj02.js 同判)。"""
    return not (73.66 < lng < 135.05 and 3.86 < lat < 53.55)


def wgs_to_gcj(lng: float, lat: float) -> tuple[float, float]:
    """WGS-84 → GCJ-02 (火星坐标, 高德显示域; 境外原样返回)。"""
    if out_of_china(lng, lat):
        return lng, lat
    d_lng, d_lat = _gcj_delta(lng, lat)
    return lng + d_lng, lat + d_lat


def mercator(lng: float, lat: float) -> tuple[float, float]:
    """Web Mercator (高德同投影): 海报路形与屏上一致。"""
    rad = math.radians(lat)
    return math.radians(lng), math.log(math.tan(math.pi / 4 + rad / 2))
