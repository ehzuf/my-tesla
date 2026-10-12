"""行程分组接口模型: 拆自 trip_schemas (那边满 200 行硬上限, 2026-10-12
分组明细第四页批)。建组/改名 (3.2.0) 与改成员一批落定 (3.10.0 —— 前端先
标记后确认); 条目字段 = 行程卡字段 + 在组标记。全部经 schemas/__init__ 门
面对外, 调用方不感知内部分层。"""
from pydantic import BaseModel, Field

from .trip_schemas import TripItem


class TripGroupIn(BaseModel):
    """存分组: 名字 + 行程 id 列表 (至少 2 段; 上限 2026-09-25 用户点名撤掉,
    大分组靠区间写法与逐段流式扛)。"""
    name: str = Field(min_length=1, max_length=30)
    ids: list[int] = Field(min_length=2)


class TripGroupRename(BaseModel):
    """分组改名 (只改名字, 成员不动)。"""
    name: str = Field(min_length=1, max_length=30)


class TripGroupInfo(BaseModel):
    """分组条目: 段数/里程/日期跨度按当前行程数据现算; 起止/时长/最高速/
    电耗汇总与合并播放的流式汇总头同口径 (弹层一开就显数, 不等地图)。"""
    id: int
    name: str
    ids: list[int]
    n: int
    km: float
    span: str
    start: str | None = None      # 首段出发 (本地时间, 与汇总头同格式)
    end: str | None = None
    min: int | None = None        # 各段时长和 (分钟)
    speed_max: int | None = None
    kwh: float | None = None      # 总电耗 (各段续航差×换算系数之和)
    wh_per_km: float | None = None   # 平均电耗 (按总里程)


class GroupChangesIn(BaseModel):
    """分组改成员 (确认提交一批): 要加入 + 要移出的行程 id 列表。前端先
    标记后确认 —— 车里逐行点标记是预览, 落定才整批发过来 (没标记不发)。"""
    adds: list[int] = []
    removes: list[int] = []


class GroupTripRow(TripItem):
    """分组明细页的行程条目: 行程卡字段 + 在组标记 (组外候选行也走这,
    前端降透明画 + 给加入钮)。"""
    in_group: bool


class GroupTripsPage(BaseModel):
    """分组明细窗口: 分组条目 (页头段数/里程) + 行程条目 (id 升序 = 时间
    正序; id 即行程落库序, 与出发序一致, 连续区间本就按 id 定义) + 两端
    还有没有可拉的 (更前/更后的组外行程)。"""
    group: TripGroupInfo
    items: list[GroupTripRow]
    has_more_before: bool
    has_more_after: bool


class GroupMemberUpdate(BaseModel):
    """改成员一批后的返回: 更新后的分组条目 + 全部翻转了状态的行程 id
    (加 = 新吸收进组的全部段 —— 区间外延不止点的那几段; 移 = 被移掉的)。
    前端拿分组条目的 ids 就地在已加载行上翻状态, 不整页重拉 (拉动加载的
    页不丢)。"""
    group: TripGroupInfo
    changed: list[int]
