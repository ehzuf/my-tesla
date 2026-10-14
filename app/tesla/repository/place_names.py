"""高德逆地理命名缓存的存取 (2026-10-02 用户点名「用 GPS 坐标结合高德,
不要相信 teslamate」): place_worker 回填写, 常去地点统计读; 2026-10-14
地名高德化起, 行程起终点与充电地点的省市区/城市也读这里。

place_names 一址一行 (键 = TeslaMate address_id): 读侧 IN 查只回 ok 的行
—— 有名字 (v1/v2 同策略取名) 或有省市区 (v2 起) 都算可用; v1 老行区划
空, 区划类消费对那址回退 TeslaMate (后台慢慢刷, 刷好一址换一址)。
境外/失败的地址不落 ok 行, 读侧自然回退 TeslaMate 名 (旧行为)。
all_address_coords 是 TeslaMate 侧的全量坐标清单 (worker 的待办面)。"""
from typing import Iterable, NamedTuple

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from ..models import Address, PlaceName


class PlaceInfo(NamedTuple):
    """读侧形状: 地名 + 省市区区划 (v2 起有; v1 老行只有 name)。"""

    name: str
    province: str
    city: str
    district: str


def place_name_map(own: Session, ids: Iterable[int]) -> dict[int, str]:
    """地址 id → 高德名 (只回 ok 且有名字的; 空 ids 短路回空表 ——
    in_() 吃空列表会查成全表)。"""
    keys = list(ids)
    if not keys:
        return {}
    rows = own.execute(
        select(PlaceName.address_id, PlaceName.name)
        .where(PlaceName.address_id.in_(keys),
               PlaceName.status == "ok", PlaceName.name != "")).all()
    return {r[0]: r[1] for r in rows}


def place_info_map(own: Session, ids: Iterable[int]) -> dict[int, PlaceInfo]:
    """地址 id → 高德地名+区划 (ok 且有名或省市区; 空 ids 短路同上)。

    v1 老行 (只有名) 也回 —— 取名策略没变, 名字照用; 区划空由消费侧
    逐项回退 TeslaMate 解析。"""
    keys = list(ids)
    if not keys:
        return {}
    rows = own.execute(
        select(PlaceName.address_id, PlaceName.name, PlaceName.province,
               PlaceName.city, PlaceName.district)
        .where(PlaceName.address_id.in_(keys),
               PlaceName.status == "ok",
               or_(PlaceName.name != "", PlaceName.province != ""))).all()
    return {r[0]: PlaceInfo(r[1], r[2], r[3], r[4]) for r in rows}


def place_search_ids(own: Session, q: str) -> list[int]:
    """搜索词命中高德名/区划的地址 id (充电地址搜索的补充口径: 地名换成
    高德名后, 拿 TeslaMate 原名搜不到的, 得能在缓存里搜到)。"""
    like = f"%{q.lower()}%"
    return [r[0] for r in own.execute(
        select(PlaceName.address_id).where(or_(
            func.lower(PlaceName.name).like(like),
            func.lower(PlaceName.province).like(like),
            func.lower(PlaceName.city).like(like),
            func.lower(PlaceName.district).like(like)))).all()]


def done_address_ids(own: Session, ver: int) -> set[int]:
    """已处理水位 (ok/skip 都算, 只按 v): 策略版本没到的重查。"""
    return set(own.scalars(
        select(PlaceName.address_id).where(PlaceName.v == ver)))


def save_place_name(own: Session, row: PlaceName) -> None:
    """命名结果落库: 一址一行, 重写 = 先删后插 (save_road 同款)。"""
    own.execute(delete(PlaceName)
                .where(PlaceName.address_id == row.address_id))
    own.add(row)
    own.commit()


def all_address_coords(session: Session) -> list[tuple[int, float, float]]:
    """TeslaMate 全量地址坐标 (worker 待办面): 停车点的 WGS-84 GPS,
    空坐标的地址这里就排除 (读侧回退 TeslaMate 名)。"""
    return [(a.id, float(a.latitude), float(a.longitude))
            for a in session.scalars(select(Address))
            if a.latitude is not None and a.longitude is not None]


def place_name_row(address_id: int, status: str, v: int, name: str = "",
                   province: str = "", city: str = "",
                   district: str = "") -> PlaceName:
    """工厂 (road_row 同款): name 截 60 字 (与改名接口的 max_length 对齐),
    区划截 24 字 (省市区名最长也就十来字)。"""
    return PlaceName(address_id=address_id, name=name[:60],
                     province=province[:24], city=city[:24],
                     district=district[:24], status=status, v=v)
