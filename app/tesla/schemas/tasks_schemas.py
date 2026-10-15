"""后台任务页 schema (设置组「后台任务」): 长回填任务的进度与重启。"""
from pydantic import BaseModel


class TaskInfo(BaseModel):
    """一项后台任务的面板状态: done/total 与 worker 待办严格同口径
    (当前算法/策略版本有行的才算), 跨进程读库即真 (双 uvicorn 不掺
    内存状态)。restart_hint 是重启前的确认文案 (带真实总量, 前端
    confirm 原样示出)。"""

    id: str
    name: str
    desc: str
    state: str         # running / done / blocked
    state_label: str   # 人话状态 (进行中 / 已完成 / 等待配置…)
    done: int
    total: int
    restart_hint: str
