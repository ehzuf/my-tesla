"""省市区解析与地区树 (充电与行程共用)。

TeslaMate (OSM) 的 display_name 是逗号分隔、从细到粗的地址链:
"POI, 路, 街道/镇, 区县, 市, 省, 邮编, 中国", 但市/区偶尔重复或缺失
("…, 顺德区, 佛山市, 顺德区, 广东省", 省直辖县没有市)。addresses 的
city 列则混着 市/区/街道, 不能当层级用 —— 三级只能从 display_name 解析。

2026-10-14 地名高德化: 三级解析优先走高德缓存 (place_names 的 province/
city/district, worker 拿停车 GPS 问的), TeslaMate 链降为逐址兜底 (那些
库的 OSM 反查可能是英文); 直辖市高德只给省+区 (city=[]), 匹配/建树把
区县提市层, 展示链补一层省名重复。
"""
from functools import lru_cache
import re
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Address
from .place_names import PlaceInfo, place_info_map
from ..schemas import RegionNode


_PROV_SUF = ("省", "自治区", "特别行政区")
_CITY_SUF = ("市", "盟", "地区", "自治州")
_DIST_SUF = ("区", "县", "旗", "镇", "街道", "市")
_LEGACY_RE = re.compile(r"^(?:(.{1,12}?(?:省|自治区))?)\s*(?:(.{1,12}?市)?)"
                        r"\s*(?:(.{1,12}?(?:区|县|镇|街道))?)")


def _suffixed(token: str, suffixes: tuple[str, ...]) -> bool:
    return any(token.endswith(s) for s in suffixes)


def _scan_left(parts: list[str], start: int, suffixes: tuple[str, ...],
               window: int = 2) -> int:
    """从 start 向左 window 格内找第一个以后缀结尾的 token 下标 (找不到 = -1)。"""
    for j in range(start - 1, max(-1, start - 1 - window), -1):
        if _suffixed(parts[j], suffixes):
            return j
    return -1


@lru_cache(maxsize=4096)
def parse_region(display_name: str) -> tuple[str | None, str | None, str | None]:
    """display_name → (省, 市, 区县)。

    兼容两种格式: OSM 逗号链 (向左窗口扫描, 容忍重复/缺失/邮编/中国大陆)
    和旧版连写 "广东省深圳市龙岗区坂田街道"。解析不出省 = 无地区信息。
    """
    if not display_name:
        return (None, None, None)
    if "," not in display_name:
        m = _LEGACY_RE.match(display_name)
        g = m.groups() if m else (None, None, None)
        return (g[0] or None, g[1] or None, g[2] or None)
    parts = [p.strip() for p in display_name.split(",") if p.strip()]
    i = len(parts) - 1
    while i >= 0 and (parts[i] in ("中国", "中国大陆") or parts[i].isdigit()):
        i -= 1
    if i < 0 or not _suffixed(parts[i], _PROV_SUF):
        return (None, None, None)
    prov = parts[i]
    city = dist = None
    cj = _scan_left(parts, i, _CITY_SUF)
    if cj >= 0:
        city = parts[cj]
        dj = _scan_left(parts, cj, _DIST_SUF)
        if dj >= 0:
            dist = parts[dj]
    else:                       # 省直辖县: 没有市级, 区县提升到市层
        dj = _scan_left(parts, i, _DIST_SUF)
        if dj >= 0:
            city = parts[dj]
    return (prov, city, dist)


def region_chain(display_name: str | None) -> str | None:
    """display_name → 省市区链 (大→小, " · " 连); 解析不出省 = None。

    充电列表/详情与行程起终点同一口径 (用户点名信息量对齐 + 从大到小排),
    前端配 fmtPlaceShort 再取最小两段。"""
    if not display_name:
        return None
    prov, city, dist = parse_region(display_name)
    if not prov:
        return None
    return " · ".join(p for p in (prov, city, dist) if p)


def amap_region(info: PlaceInfo | None) -> tuple[str | None, str | None, str | None]:
    """高德缓存行 → (省, 市, 区县) (与 parse_region 同形状): 无行/区划缺省
    (v1 老行/境外) 三连 None; 直辖市 city=[] 区县提市层 (省直辖县口径)。"""
    if info is None or not info.province:
        return (None, None, None)
    city, dist = info.city or None, info.district or None
    if not city and dist:          # 直辖市: 区县提市层 (省直辖县口径)
        city, dist = dist, None
    return (info.province, city, dist)


def resolve_region(info: PlaceInfo | None,
                   display_name: str | None) -> tuple[str | None, str | None, str | None]:
    """(高德缓存行, TeslaMate 地址链) → (省, 市, 区县): 缓存行有省用高德,
    v1 老行/境外/没刷到逐址回退 display_name 解析。"""
    if info is not None:
        triple = amap_region(info)
        if triple[0]:
            return triple
    return parse_region(display_name or "")


def amap_chain(info: PlaceInfo | None) -> str | None:
    """高德缓存行 → 省市区展示链 (" · " 连, 大→小)。直辖市市层缺位补省名
    (北京市 · 北京市 · 大兴区) —— 前端 shortPlace 只在 ≥3 段时取尾两段;
    无行/没省 = None (调用方回退 TeslaMate 链)。"""
    if info is None or not info.province:
        return None
    return " · ".join(p for p in (info.province, info.city or info.province,
                                  info.district) if p)


def amap_full(info: PlaceInfo | None) -> str:
    """高德缓存行 → 整链清洗串 (无分隔, _clean_addr 同形态): 省+市 (直辖市
    补省)+区+地名, 相邻重名去重, 兜底名与区重前缀剪掉; 无行/没省 = ""。"""
    if info is None or not info.province:
        return ""
    name = info.name
    if name and info.district and name.startswith(info.district):
        name = name[len(info.district):]
    kept: list[str] = []
    for part in (info.province, info.city or info.province, info.district, name):
        if part and (not kept or part != kept[-1]):
            kept.append(part)
    return "".join(kept)[:80]


def region_address_ids(session: Session, own: Session, path: str) -> list[int]:
    """省市区路径 → 命中的地址 id 列表 (段数即精确到哪一级; 三级解析高德
    优先, 没刷到的逐址回退 TeslaMate 链; 空/无命中返回 [])。"""
    segs = [s for s in (p.strip() for p in path.split("/")) if s]
    if not segs:
        return []
    rows = session.execute(select(Address.id, Address.display_name)).all()
    amap = place_info_map(own, [aid for aid, _ in rows])
    ids: list[int] = []
    for aid, name in rows:
        prov, city, dist = resolve_region(amap.get(aid), name)
        if (prov == segs[0]
                and (len(segs) < 2 or city == segs[1])
                and (len(segs) < 3 or dist == segs[2])):
            ids.append(aid)
    return ids


class _RegionAcc:
    """建树用的临时累加器: 数 count, children 最后统一排序转 RegionNode。"""

    def __init__(self, name: str) -> None:
        """建一个 0 计数的空节点。"""
        self.name = name
        self.count = 0
        self.children: dict[str, _RegionAcc] = {}

    def child(self, name: str) -> "_RegionAcc":
        """取子节点 (没有就建)。"""
        node = self.children.get(name)
        if node is None:
            node = self.children[name] = _RegionAcc(name)
        return node

    def node(self) -> RegionNode:
        """转出定型的 RegionNode (children 按次数降序)。"""
        return RegionNode(
            name=self.name, count=self.count,
            children=[c.node() for c in
                      sorted(self.children.values(), key=lambda c: -c.count)])


def _acc_triple_tree(
        triples: Iterable[tuple[str | None, str | None, str | None]]
) -> list[RegionNode]:
    """(省, 市, 区县) 三元组序列 → 省→市→区县计数树 (次数降序): 无省的
    不进树, 有市无区的计入省市两级。来源混建 —— 高德缓存行 (amap_region)
    与 TeslaMate 链解析同形状, 后台慢慢刷, 树里两路节点自然并账。"""
    root = _RegionAcc("")
    for prov, city, dist in triples:
        if not prov:
            continue
        prov_acc = root.child(prov)
        prov_acc.count += 1
        if city:
            city_acc = prov_acc.child(city)
            city_acc.count += 1
            if dist:
                dist_acc = city_acc.child(dist)
                dist_acc.count += 1
    return [c.node() for c in
            sorted(root.children.values(), key=lambda c: -c.count)]
