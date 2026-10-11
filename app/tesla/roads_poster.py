"""足迹地图高清海报渲染入口 (Pillow, 2026-10-11 用户点名「下载高清轨迹
地图, 地图大小不限, 精度拉满, 要求带文字」): 服务端把「走过的路」整幅画
成 PNG —— 不迁就浏览器画布/内存上限 (车机 8K 封顶, 全量折线车机也画不
动), 拟合顶点全量不抽稀 (屏上为性能按缩放抽稀, 海报不吃这套)。

计数/色阶/坐标换算在 roads_poster_grid (roads-grid.js 同一把尺: 1 次暗
蓝 → 青 → 金 → 最多次数红, 对数刻度; 次数只从已证实段来, 推断层画灰虚线
不进计数), 画笔在 roads_poster_draw (超采样/虚线/压暗), 文字在
roads_poster_text, 本文件只做编排。文字: 标题 + 日期跨度 + 总里程/时长/
行程数 + 图例 + 比例尺。"""
from __future__ import annotations

import io
from collections.abc import Sequence

from PIL import ImageDraw

from . import roads_poster_draw as draw
from . import roads_poster_text as text
from .roads_poster_grid import (PosterError, PosterStats, RoadShape,
                                cells_for_flat, mercator, row_spans,
                                wgs_to_gcj)


def _counts(shapes: Sequence[RoadShape]) -> tuple[dict[int, int], int]:
    """全量格计数 (mergeCells 同口径): 每程已证实段的格序列 (连续去重后
    本程内仍可重复进格 —— 折返就该多计) 并进全局, 上限跟最重格走。"""
    counts: dict[int, int] = {}
    max_count = 0
    for s in shapes:
        per: dict[int, int] = {}
        for f0, f1 in row_spans(len(s.pts) // 2, s.gaps):
            for k in cells_for_flat(s.pts[f0:f1]):
                per[k] = per.get(k, 0) + 1
        for k, c in per.items():
            counts[k] = counts.get(k, 0) + c
            if counts[k] > max_count:
                max_count = counts[k]
    return counts, max_count


def _project(shapes: Sequence[RoadShape]) -> list[list[tuple[float, float]]]:
    """WGS-84 → GCJ-02 → Web Mercator (与屏上坐标链一致, 路形对得上)。
    火星偏移在百米内渐变是米级 —— 按 ~100m 桶缓存, 重复走过的同一条路
    命中率高, 省掉大半三角函数。"""
    cache: dict[tuple[int, int], tuple[float, float]] = {}
    proj: list[list[tuple[float, float]]] = []
    for s in shapes:
        row: list[tuple[float, float]] = []
        for i in range(0, len(s.pts), 2):
            lng, lat = s.pts[i], s.pts[i + 1]
            ck = (round(lng * 1000), round(lat * 1000))
            g = cache.get(ck)
            if g is None:
                g = wgs_to_gcj(lng, lat)
                cache[ck] = g
            row.append(mercator(g[0], g[1]))
        proj.append(row)
    return proj


def render(shapes: Sequence[RoadShape], stats: PosterStats,
           size: int = 4800) -> bytes:
    """整幅海报: 计数 → 投影 → 画幅 → 道路层 (超采样) → 压暗 + 文字。"""
    if not any(len(s.pts) >= 4 for s in shapes):
        raise PosterError("还没有走过的路可画")
    counts, max_count = _counts(shapes)
    proj = _project(shapes)
    lay = draw.layout(proj, size)
    img = draw.roads_layer(shapes, proj, counts, max_count, lay, size)
    ink = ImageDraw.Draw(img)
    draw.scrim(img, lay.w, lay.h, round(lay.h * 0.15), round(lay.h * 0.10), 165)
    text.text_head(ink, stats, lay, size)
    text.text_footer(ink, lay, size)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
