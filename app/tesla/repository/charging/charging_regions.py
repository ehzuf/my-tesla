"""充电地点: 省市区逐级匹配筛选 + 地点计数树 (级联下拉数据源)。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Address, ChargingProcess
from ..place_names import PlaceInfo, place_info_map
from ..region_tree import _acc_triple_tree, resolve_region
from ...schemas import RegionNode


def _match_region(address: Address | None, path: str,
                  info: PlaceInfo | None = None) -> bool:
    """充电地点筛选: 地址剥出的省市区对 "/" 路径做逐级匹配 (高德区划优先,
    没刷到回退 display_name 解析)。

    段数即精确到哪一级 (1=省 2=市 3=区县), 没给的层不陪绑;
    无地址 / 解析不出省 = 不命中。与地点树、行程页 region_address_ids 同一口径。
    """
    segs = [seg for seg in (t.strip() for t in path.split("/")) if seg]
    if not segs or address is None:
        return False
    region = resolve_region(info, address.display_name)
    return region[:len(segs)] == tuple(segs)


def charging_region_tree(session: Session, own: Session,
                         car_id: int | None = None) -> list[RegionNode]:
    """充电地点省→市→区县计数树 (按充电次数降序), 地点级联下拉数据源。

    与行程页同款树 (三级高德优先, 没刷到的逐址回退 TeslaMate 链解析);
    解析不出省的地址不进树, 但仍参与列表展示; car_id 选定时只数那台车
    充过的地点。
    """
    stmt = (select(Address.id, Address.display_name)
            .join(ChargingProcess, ChargingProcess.address_id == Address.id))
    if car_id is not None:
        stmt = stmt.where(ChargingProcess.car_id == car_id)
    rows = session.execute(stmt).all()
    amap = place_info_map(own, [aid for aid, _ in rows])
    return _acc_triple_tree(resolve_region(amap.get(aid), name)
                            for aid, name in rows)
