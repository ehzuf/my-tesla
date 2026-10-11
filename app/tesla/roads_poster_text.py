"""足迹海报的文字层: 字体逐级回落 (PingFang → NotoSansSC → DejaVu, 全没有
就跳过文字绝不做错) + 头行 (标题/总里程/日期跨度) + 脚行 (热力图例/比例尺/
落款)。色阶色 (color_of) 与画幅几何 (Layout) 是共享词表, 位置与字色由本层
自定。"""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path

from PIL import ImageDraw, ImageFont

from .roads_poster_draw import Layout
from .roads_poster_grid import PosterStats, color_of

INK_1 = (0xF2, 0xF5, 0xFA)        # 主文字 (标题/数字/比例尺)
INK_2 = (0x9A, 0xA4, 0xB5)        # 次文字 (跨度/图例/落款)

_FONT_BOLD = (Path("~/.fonts/pingfang/PingFangSC-Semibold.otf"),)
_FONT_BODY = (Path("~/.fonts/pingfang/PingFangSC-Regular.otf"),
              Path("~/.local/share/fonts/NotoSansSC.ttf"))
_FONT_ANY = _FONT_BODY + _FONT_BOLD + (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),)
_font_cache: dict[tuple[int, bool], ImageFont.FreeTypeFont | None] = {}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | None:
    """逐级回落找字体 (标题优先 Semibold); 全没有 → None (文字让路)。"""
    key = (size, bold)
    if key not in _font_cache:
        found = None
        for path in (_FONT_BOLD if bold else _FONT_BODY) + _FONT_ANY:
            p = path.expanduser()
            if p.is_file():
                try:
                    found = ImageFont.truetype(str(p), size)
                    break
                except OSError:
                    continue
        _font_cache[key] = found
    return _font_cache[key]


def text_head(draw: ImageDraw.ImageDraw, stats: PosterStats, lay: Layout,
              size: int) -> None:
    """头行: 标题 + 总里程 + 日期跨度/时长/行程数 (压暗渐变之上)。"""
    f_title = _font(max(20, size // 26), bold=True)
    f_big = _font(max(16, size // 46), bold=True)
    f_body = _font(max(12, size // 95))
    ty = lay.pad * 0.9
    if f_title:
        draw.text((lay.pad, ty), "足迹地图", font=f_title, fill=INK_1)
        ty += f_title.size + lay.pad * 0.35
    if f_big:
        draw.text((lay.pad, ty), f"总里程 {stats.distance_km:,.0f} km",
                  font=f_big, fill=INK_1)
        ty += f_big.size + lay.pad * 0.18
    if f_body:
        span = ""
        if stats.first and stats.last:
            span = f"{stats.first:%Y.%m.%d} – {stats.last:%Y.%m.%d} · "
        draw.text((lay.pad, ty), span + f"{stats.duration_min / 60:,.0f} 小时 · "
                  f"{stats.drives:,} 程", font=f_body, fill=INK_2)


def text_footer(draw: ImageDraw.ImageDraw, lay: Layout, size: int) -> None:
    """脚行: 热力图例 (偶尔→频繁, 屏上同词同色) + 比例尺 + 生成落款。"""
    f_small = _font(max(10, size // 120))
    by = lay.h - lay.pad
    lg_w, lg_h = round(lay.w * 0.30), max(3, size // 400)
    lg_y = by - lg_h - round(lay.pad * 0.8)
    for i in range(lg_w):
        draw.line([(lay.pad + i, lg_y), (lay.pad + i, lg_y + lg_h)],
                  fill=color_of(i / max(1, lg_w - 1)))
    if f_small:
        cap_y = lg_y - f_small.size - round(lay.pad * 0.15)
        draw.text((lay.pad, cap_y), "偶尔", font=f_small, fill=INK_2)
        draw.text((lay.pad + lg_w, cap_y), "频繁", font=f_small, fill=INK_2,
                  anchor="ra")
        draw.text((lay.w // 2, by - f_small.size),
                  f"My Tesla · 生成于 {date.today():%Y-%m-%d}",
                  font=f_small, fill=INK_2, anchor="ma")
    # 比例尺: 中心纬度的地面分辨率取整刻度 (横距在 Mercator 上无畸变)
    lat_c = math.degrees(2 * math.atan(math.exp(lay.ym)) - math.pi / 2)
    m_per_px = 111_320.0 * math.cos(math.radians(lat_c)) / lay.scale
    for km in (500, 200, 100, 50, 20, 10, 5, 2, 1):
        if km * 1000 / m_per_px > lay.w * 0.22:
            continue
        bar_px = round(km * 1000 / m_per_px)
        bx = lay.w - lay.pad - bar_px
        draw.line([(bx, lg_y), (bx + bar_px, lg_y)], fill=INK_1,
                  width=max(2, size // 1600))
        tick = size // 300
        for xx in (bx, bx + bar_px):
            draw.line([(xx, lg_y - tick), (xx, lg_y + tick)], fill=INK_1,
                      width=max(2, size // 2400))
        if f_small:
            draw.text((bx + bar_px // 2, lg_y - f_small.size - tick),
                      f"{km} km", font=f_small, fill=INK_2, anchor="ma")
        break
