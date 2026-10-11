"""足迹海报的画笔 (Pillow 原语): 画幅几何 / 虚线 / 压暗渐变 / 道路层落墨。
坐标与计数语义在 roads_poster_grid (roads-grid.js 同一把尺), 文字层在
roads_poster_text —— 本模块只管几何怎么画: 2× 超采样画路后 LANCZOS 缩回
抗锯齿 (PIL 画线无原生抗锯齿)。"""
from __future__ import annotations

import math
from collections.abc import Sequence
from typing import NamedTuple

from PIL import Image, ImageDraw

from .roads_poster_grid import (PosterError, RoadShape, row_spans,
                                runs_by_step, step_color, STEPS)

GUESS_COLOR = (0x8E, 0x99, 0xAB)  # 推断层灰 (屏上 strokeColor #8e99ab)
BG = (0x0E, 0x12, 0x19)           # 底色: 深夜蓝黑 (灰阶底图的同族暗面)
SS = 2                            # 超采样倍率 (缩回时抗锯齿)


class Layout(NamedTuple):
    """画幅几何: 像素尺寸 + 数据域中点/比例 (y 轴画时翻, 北上)。"""

    w: int
    h: int
    pad: int
    scale: float
    xm: float
    ym: float


def _dashed(draw: ImageDraw.ImageDraw, pts: Sequence[tuple[float, float]],
            on: float, off: float, width: int,
            color: tuple[int, int, int]) -> None:
    """折线虚线 (PIL 无原生 dash: 沿线按像素长走 on/off 两态切子段,
    dash 跨顶点连续, on 态走完才收笔)。"""
    seg: list[tuple[float, float]] = []
    state, remain = True, on
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        d = math.hypot(x1 - x0, y1 - y0)
        if d < 1e-9:
            continue
        t = 0.0
        while t < d - 1e-9:
            step = min(remain, d - t)
            if state:
                seg.append((x0 + (x1 - x0) * t / d, y0 + (y1 - y0) * t / d))
            t += step
            remain -= step
            if remain <= 1e-9:
                if state and len(seg) >= 2:
                    draw.line(seg, fill=color, width=width, joint="curve")
                state = not state
                remain = on if state else off
                seg = ([] if not state else
                       [(x0 + (x1 - x0) * t / d, y0 + (y1 - y0) * t / d)])
    if state and len(seg) >= 2:
        draw.line(seg, fill=color, width=width, joint="curve")


def scrim(img: Image.Image, w: int, h: int, top_h: int, bottom_h: int,
          max_alpha: int) -> None:
    """上下缘压暗渐变 (文字可读性): 灰度蒙版逐行画坡, 经 alpha 蒙版叠黑
    (int 直填 RGB 会被当打包色 —— 画成纯红, 必须走 mask paste)。"""
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    for y in range(min(top_h, h)):
        d.line([(0, y), (w, y)], fill=max_alpha * (top_h - y) // max(1, top_h))
    for y in range(min(bottom_h, h)):
        d.line([(0, h - 1 - y), (w, h - 1 - y)],
               fill=max_alpha * (bottom_h - y) // max(1, bottom_h))
    img.paste((0, 0, 0), (0, 0), mask)


def _px(lay: Layout, row: Sequence[tuple[float, float]], p0: int,
        p1: int) -> list[tuple[float, float]]:
    """点区间的超采样像素坐标 (y 翻转北上)。"""
    return [(lay.w * SS / 2 + (x - lay.xm) * lay.scale * SS,
             lay.h * SS / 2 - (y - lay.ym) * lay.scale * SS)
            for x, y in row[p0:p1 + 1]]


def layout(proj: Sequence[Sequence[tuple[float, float]]],
           size: int) -> Layout:
    """画幅: 长边 = size, 短边随数据纵横比 (含 6% 呼吸边), 道路满幅居中。"""
    xs = [p[0] for row in proj for p in row]
    ys = [p[1] for row in proj for p in row]
    if not xs:
        raise PosterError("还没有走过的路可画")   # render 已挡空集, 收口防呆
    dx = max(max(xs) - min(xs), 1e-9)
    dy = max(max(ys) - min(ys), 1e-9)
    pad = round(size * 0.035)
    breath = (dx + dy) * 0.06
    aspect = (dx + breath) / (dy + breath)
    if aspect >= 1:
        w, h = size, max(size // 8, round(size / aspect))
    else:
        w, h = max(size // 8, round(size * aspect)), size
    scale = min((w - 2 * pad) / dx, (h - 2 * pad) / dy)
    return Layout(w, h, pad, scale, (max(xs) + min(xs)) / 2,
                  (max(ys) + min(ys)) / 2)


def _run_lines(shapes: Sequence[RoadShape],
               proj: Sequence[Sequence[tuple[float, float]]],
               counts: dict[int, int], max_count: int,
               lay: Layout) -> list[tuple[int, list[tuple[float, float]]]]:
    """证实段按次数档切段 → (档, 像素折线); 段色与屏上分段一致。"""
    runs: list[tuple[int, list[tuple[float, float]]]] = []
    for s, row in zip(shapes, proj):
        for f0, f1 in row_spans(len(s.pts) // 2, s.gaps):
            for b, i0, i1 in runs_by_step(s.pts[f0:f1], counts, max_count):
                runs.append((b, _px(lay, row, (f0 + i0) // 2, (f0 + i1) // 2)))
    return runs


def roads_layer(shapes: Sequence[RoadShape],
                proj: Sequence[Sequence[tuple[float, float]]],
                counts: dict[int, int], max_count: int, lay: Layout,
                size: int) -> Image.Image:
    """道路层: 推断层灰虚线垫底, 证实段按次数档 0→11 排笔 (常走的路压着
    偶走的 —— 与屏上图层序一致); 超采样画完缩回目标尺寸。"""
    img = Image.new("RGB", (lay.w * SS, lay.h * SS), BG)
    draw = ImageDraw.Draw(img)
    base = max(3, round(size / 800))   # 4800px → 6px 笔宽 (300dpi 印 0.5mm 线)
    for s, row in zip(shapes, proj):
        n = len(s.pts) // 2
        for gi in s.gaps:
            a, b = max(0, math.floor(gi[0])), min(n - 1, math.floor(gi[1]))
            if b - a < 1:
                continue
            _dashed(draw, _px(lay, row, a, b), 9 * SS, 7 * SS,
                    max(1, base - 1) * SS, GUESS_COLOR)
    runs = _run_lines(shapes, proj, counts, max_count, lay)
    for bucket in range(STEPS):
        for b, pts in runs:
            if b == bucket and len(pts) >= 2:
                draw.line(pts, fill=step_color(b), width=base * SS,
                          joint="curve")
    return img.resize((lay.w, lay.h), Image.Resampling.LANCZOS)
