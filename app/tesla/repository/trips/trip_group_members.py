"""分组明细: 组内行程窗口与加/移成员 (分组 = 连续区间)。

区间口径与合并播放一致 (分享链接只记「首-尾」, 服务端按区间展开全部已
结束行程): 加一段 = 区间外延到该行程, 中间的已结束行程整段吸收 —— 连续
性靠构造保证, 不可能挖出洞; 移一段 = 只许收头尾 (中间挖洞会断开)。
窗口按 id 升序 (id 即行程落库序, 与出发序一致), 组内行 in_group=true,
组外候选行也一并给 (前端降透明画 + 加入钮, 拉动加载沿两端翻页)。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from ...models import Address, Drive, TripGroup
from ...schemas import GroupMemberUpdate, GroupTripsPage, GroupTripRow
from ..common import NotFound
from .trip_groups import _group_ids, _group_info
from .trip_listing import _eff_by_car, _trip_item, _trip_rows_stmt
from .trip_tracks import closed_drive_ids_between


def _stored_range(group: TripGroup) -> tuple[int, int]:
    """分组存库 ids 的首尾 (区间定义; 写库方恒存升序全展开, min/max 兜底)。"""
    ids = _group_ids(group)
    return min(ids), max(ids)


def _closed_before(session: Session, edge: int | None) -> bool:
    """edge 之前还有没有已结束行程 (两端「还有更多」旗标; 空 edge = 没有)。"""
    if edge is None:
        return False
    return session.scalar(
        select(Drive.id).where(Drive.end_date.is_not(None), Drive.id < edge)
        .limit(1)) is not None


def _closed_after(session: Session, edge: int | None) -> bool:
    """edge 之后还有没有已结束行程 (同上, 方向反过来)。"""
    if edge is None:
        return False
    return session.scalar(
        select(Drive.id).where(Drive.end_date.is_not(None), Drive.id > edge)
        .limit(1)) is not None


def _cursor_ok(session: Session, drive_id: int) -> None:
    """翻页游标 = 已加载边缘行程的 id, 必须是已结束行程 (防脏参数)。"""
    d = session.get(Drive, drive_id)
    if d is None or d.end_date is None:
        raise NotFound("游标行程不存在或未结束")


def group_trip_window(session: Session, own: Session, group_id: int,
                      before_id: int | None = None,
                      after_id: int | None = None,
                      limit: int = 30) -> GroupTripsPage:
    """分组明细窗口: 默认给组内全部行程 (id 升序, 不截断 —— 组内行就是
    「当前分组的所有轨迹」); before/after = 沿两端翻组外候选 (各给 limit
    条, 贴近的先)。in_group 按当前区间现算, 两端旗标跟着本页边缘走。"""
    group = own.get(TripGroup, group_id)
    if group is None:
        raise NotFound("分组不存在")
    lo, hi = _stored_range(group)
    stmt = _trip_rows_stmt(aliased(Address), aliased(Address))  # 已含已结束过滤
    more = False
    if before_id is not None:
        _cursor_ok(session, before_id)
        rows = list(session.execute(stmt.where(Drive.id < before_id)
                                    .order_by(Drive.id.desc())
                                    .limit(limit + 1)).all())
        more = len(rows) > limit
        rows = list(reversed(rows[:limit]))    # 展示仍按 id 升序 (时间正序)
    elif after_id is not None:
        _cursor_ok(session, after_id)
        rows = list(session.execute(stmt.where(Drive.id > after_id)
                                    .order_by(Drive.id)
                                    .limit(limit + 1)).all())
        more = len(rows) > limit
        rows = rows[:limit]
    else:
        rows = list(session.execute(stmt.where(Drive.id >= lo, Drive.id <= hi)
                                    .order_by(Drive.id)).all())
    eff = set(closed_drive_ids_between(session, lo, hi))
    effs = _eff_by_car(session, {d.car_id for d, _, _ in rows})
    items = [GroupTripRow(**_trip_item(d, s, e, effs.get(d.car_id)).model_dump(),
                          in_group=d.id in eff) for d, s, e in rows]
    edge_lo = items[0].id if items else None
    edge_hi = items[-1].id if items else None
    if before_id is not None:                  # 本方向翻页: limit+1 直接给出旗标
        return GroupTripsPage(group=_group_info(session, group), items=items,
                              has_more_before=more,
                              has_more_after=_closed_after(session, edge_hi))
    if after_id is not None:
        return GroupTripsPage(group=_group_info(session, group), items=items,
                              has_more_before=_closed_before(session, edge_lo),
                              has_more_after=more)
    return GroupTripsPage(group=_group_info(session, group), items=items,
                          has_more_before=_closed_before(session, edge_lo),
                          has_more_after=_closed_after(session, edge_hi))


def add_trip_to_group(session: Session, own: Session,
                      group_id: int, drive_id: int) -> GroupMemberUpdate:
    """分组加一段: 区间外延到该行程, 中间的已结束行程整段吸收 (changed
    列出全部新吸收段, 不止点的那一段)。"""
    group = own.get(TripGroup, group_id)
    if group is None:
        raise NotFound("分组不存在")
    drive = session.get(Drive, drive_id)
    if drive is None or drive.end_date is None:
        raise NotFound("行程不存在或未结束")
    lo, hi = _stored_range(group)
    effective = set(closed_drive_ids_between(session, lo, hi))
    if drive_id in effective:
        raise ValueError("该行程已在分组里")
    new_ids = closed_drive_ids_between(session, min(lo, drive_id), max(hi, drive_id))
    changed = [i for i in new_ids if i not in effective]
    group.ids = ",".join(str(i) for i in new_ids)
    own.commit()
    return GroupMemberUpdate(group=_group_info(session, group), changed=changed)


def remove_trip_from_group(session: Session, own: Session,
                           group_id: int, drive_id: int) -> GroupMemberUpdate:
    """分组移一段: 只许收头尾 (中间挖洞会断开连续); 至少保留 2 段 (与
    建组口径一致)。移后存库 ids 仍是新区间的全展开。"""
    group = own.get(TripGroup, group_id)
    if group is None:
        raise NotFound("分组不存在")
    lo, hi = _stored_range(group)
    effective = closed_drive_ids_between(session, lo, hi)
    if drive_id not in effective:
        raise ValueError("该行程不在分组里")
    if len(effective) <= 2:
        raise ValueError("分组至少要保留 2 段")
    if drive_id not in (effective[0], effective[-1]):
        raise ValueError("只能移出最前或最后的行程")
    group.ids = ",".join(str(i) for i in effective if i != drive_id)
    own.commit()
    return GroupMemberUpdate(group=_group_info(session, group),
                             changed=[drive_id])
