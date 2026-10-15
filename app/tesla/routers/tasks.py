"""后台任务 API (设置组「后台任务」页, 2026-10-15 用户点名「设置菜单里加
一个任务页面…每一项任务都展示一个进度条, 可以重启某个任务重新刷新数据
库」)。

任务 = 长回填 worker (分钟~小时级, 烧高德配额); 两条秒级缓存预热 (轨迹/
速度直方图) 不进此页 —— 无进度可言且自动管理。进度与 worker 待办严格同
口径 (当前算法/策略版本有行的才算), 只读库不掺进程内存 —— 双 uvicorn
(8500/8501) 下两个进程的 worker 经 DB 水位自然分工, 谁的进度都真。

重启 = 清该任务全部成果行 + 撤首回旗 + 清失败计数 + 踢醒 worker, 全量
重算 (配额照烧, 前端按 restart_hint 二次确认把关)。清空后另一进程的
worker 下一轮也看到全量待办 (水位在库里), 无需跨进程通知。
"""
from collections.abc import Callable
from typing import NamedTuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ... import database
from .. import place_worker, repository, roads_worker, settings_store
from ..place_worker import PLACE_NAME_V
from ..roads_fit import ROAD_FIT_V
from ..schemas import TaskInfo

tasksapi = APIRouter(prefix="/tesla/api")

_BLOCKED_KEY = "等待配置 Web 服务 Key"


def _state(own: Session, done: int, total: int) -> tuple[str, str]:
    """状态机: 没配 Web 服务 Key 待配置; 处理完 (含无待办) 完成; 其余进行中。"""
    if not settings_store.amap_web_key_value(own):
        return "blocked", _BLOCKED_KEY
    if done >= total:
        return "done", "已完成"
    return "running", "进行中"


def _roads_task(db: Session, own: Session) -> TaskInfo:
    """足迹道路拟合: 已结束行程逐段纠偏到实际道路 (高德轨迹纠偏 + 断档
    规划补全), 一程一行。"""
    done, total = repository.roads_progress(db, own, ROAD_FIT_V)
    state, label = _state(own, done, total)
    return TaskInfo(
        id="roads", name="足迹道路拟合",
        desc="把已结束行程的轨迹逐段拟合到实际道路 (高德接口, 首次回填约需几十分钟)",
        state=state, state_label=label, done=done, total=total,
        restart_hint=f"将清空 {total} 段行程已拟合的道路, 全部重新调用高德接口重算")


def _places_task(db: Session, own: Session) -> TaskInfo:
    """常去地点命名: 停车点 GPS 坐标问高德逆地理取真实地名, 一址一行。"""
    done, total = repository.places_progress(db, own, PLACE_NAME_V)
    state, label = _state(own, done, total)
    return TaskInfo(
        id="places", name="常去地点命名",
        desc="拿停车点坐标向高德问真实地名 (TeslaMate 的 OSM 名只作兜底)",
        state=state, state_label=label, done=done, total=total,
        restart_hint=f"将清空 {total} 个地点已取回的名称, 全部重新调用高德接口重查")


def _restart_roads(own: Session) -> None:
    """清成果 + 撤首回旗 (蒙版重新盖上) + 清放弃名单 + 踢醒。"""
    repository.wipe_roads(own)
    settings_store.reset_roads_initial_done(own)
    roads_worker.forget_failures()
    roads_worker.nudge()


def _restart_places(own: Session) -> None:
    """清成果 + 清放弃名单 + 踢醒 (没有首回旗 —— 地点名不走蒙版)。"""
    repository.wipe_place_names(own)
    place_worker.forget_failures()
    place_worker.nudge()


class _TaskSpec(NamedTuple):
    """一项任务的组装件: build 出面板状态, restart 清成果从头回填。"""

    build: Callable[[Session, Session], TaskInfo]
    restart: Callable[[Session], None]


# 任务注册表: 页面顺序 = 列表顺序 (roads 先跑, 与 worker 启动错峰一致)
_TASKS = {"roads": _TaskSpec(_roads_task, _restart_roads),
          "places": _TaskSpec(_places_task, _restart_places)}


@tasksapi.get("/tasks")
def list_tasks(db: Session = Depends(database.get_db),
               own: Session = Depends(database.get_own_db)) -> list[TaskInfo]:
    """全部后台任务的面板状态 (页面与 5s 轮询共用)。"""
    return [spec.build(db, own) for spec in _TASKS.values()]


@tasksapi.post("/tasks/{task_id}/restart")
def restart_task(task_id: str,
                 db: Session = Depends(database.get_db),
                 own: Session = Depends(database.get_own_db)) -> list[TaskInfo]:
    """重启一项任务: 成果清空从头回填, 回新面板状态 (进度归零)。"""
    spec = _TASKS.get(task_id)
    if spec is None:
        raise HTTPException(404, "没有这个任务")
    spec.restart(own)
    return [spec.build(db, own) for spec in _TASKS.values()]
