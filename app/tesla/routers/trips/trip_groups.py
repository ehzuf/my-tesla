"""轨迹分组 API: 查/存/改名/删 (逻辑分组, 存自有库, 行程原数据不动) +
分组明细 (组内行程窗口 + 批量改成员, 3.10.0)。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .... import database
from ... import repository
from ...schemas import (
    GroupChangesIn,
    GroupMemberUpdate,
    GroupTripsPage,
    TripGroupIn,
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


@router.post("/groups/{group_id}/changes")
def group_change_members(group_id: int, body: GroupChangesIn,
                         db: Session = Depends(database.get_db),
                         own: Session = Depends(database.get_own_db)) -> GroupMemberUpdate:
    """分组改成员 (确认提交一批 —— 前端点行只是标记预览, 落定才整批发
    来): 加 = 区间外延到新段、中间已结束行程整段吸收 (连续性靠构造保
    证); 移 = 只从两端收窄 (中间挖洞会断开), 至少保留 2 段。返回更新后
    的分组条目 + 全部翻转了状态的行程 id。"""
    try:
        return repository.apply_group_changes(db, own, group_id,
                                              body.adds, body.removes)
    except repository.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
