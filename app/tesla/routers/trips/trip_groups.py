"""轨迹分组 API: 查/存/改名/删 (逻辑分组, 存自有库, 行程原数据不动) +
分组明细 (组内行程窗口 + 就地加/移, 3.10.0)。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .... import database
from ... import repository
from ...schemas import (
    GroupMemberUpdate,
    GroupTripsPage,
    TripGroupIn,
    TripGroupMemberIn,
    TripGroupRename,
    TripGroupInfo,
)
from ....schemas import OkResponse


router = APIRouter()


@router.get("/groups")
def list_groups(db: Session = Depends(database.get_db),
                own: Session = Depends(database.get_own_db)) -> list[TripGroupInfo]:
    """全部轨迹分组 (逻辑分组, 存自有库, 行程原数据不动)。"""
    return repository.list_trip_groups(db, own)


@router.post("/groups")
def save_group(body: TripGroupIn,
               db: Session = Depends(database.get_db),
               own: Session = Depends(database.get_own_db)) -> TripGroupInfo:
    """多选行程存成命名分组; 段数/里程/日期跨度展示时现算, 不落库。"""
    if len(set(body.ids)) < 2:
        raise HTTPException(400, "ids 去重后需至少 2 个行程")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "名字不能为空")
    try:
        return repository.save_trip_group(db, own, name, body.ids)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.patch("/groups/{group_id}")
def rename_group(group_id: int, body: TripGroupRename,
                 db: Session = Depends(database.get_db),
                 own: Session = Depends(database.get_own_db)) -> TripGroupInfo:
    """分组改名 (成员不动)。"""
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "名字不能为空")
    try:
        return repository.rename_trip_group(db, own, group_id, name)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/groups/{group_id}")
def delete_group(group_id: int,
                 own: Session = Depends(database.get_own_db)) -> OkResponse:
    """删分组 (只删自有库记录)。"""
    try:
        repository.delete_trip_group(own, group_id)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    return OkResponse(ok=True)


@router.get("/groups/{group_id}/trips")
def group_trips_window(group_id: int, before: int | None = None,
                       after: int | None = None, limit: int = 30,
                       db: Session = Depends(database.get_db),
                       own: Session = Depends(database.get_own_db)) -> GroupTripsPage:
    """分组明细窗口: 默认给组内全部行程 (时间正序); before/after = 沿两端
    继续拉组外候选 (游标 = 已加载边缘行程 id, 贴近的先)。"""
    if before is not None and after is not None:
        raise HTTPException(400, "before 与 after 只能指定一个")
    if not 1 <= limit <= 100:
        raise HTTPException(400, "分页参数非法")
    try:
        return repository.group_trip_window(db, own, group_id, before, after, limit)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/groups/{group_id}/add")
def group_add_trip(group_id: int, body: TripGroupMemberIn,
                   db: Session = Depends(database.get_db),
                   own: Session = Depends(database.get_own_db)) -> GroupMemberUpdate:
    """分组加一段: 区间外延到该行程, 中间的已结束行程整段吸收 (连续性靠
    构造保证); 返回更新后的分组条目 + 本次新吸收的行程 id。"""
    try:
        return repository.add_trip_to_group(db, own, group_id, body.id)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/groups/{group_id}/remove")
def group_remove_trip(group_id: int, body: TripGroupMemberIn,
                      db: Session = Depends(database.get_db),
                      own: Session = Depends(database.get_own_db)) -> GroupMemberUpdate:
    """分组移一段: 只许收头尾 (中间挖洞会断开连续), 至少保留 2 段;
    返回更新后的分组条目 + 被移掉的行程 id。"""
    try:
        return repository.remove_trip_from_group(db, own, group_id, body.id)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
