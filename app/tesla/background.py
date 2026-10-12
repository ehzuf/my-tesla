"""TeslaMate 后台线程 (预热 ×2 + 高德 worker ×2) 的开动时机。

数据源没配 (真首启) 时这些线程没有可用的引擎 —— 起了也是对着占位主机
空转 (teslamate_engine.UNSET_HOST), 这里挂起等配置, 向导第二步存好真地址
再开动 (免重启)。开动之后的引擎热换 (设置页保存 rebuild) 由线程自己跟
手: worker 每轮现取 session_factory(), 预热败了隔 60s 重试 —— NAS 实测
教训: 启动时捕获的工厂对象 (docker 定位地址 + 空密码) rebuild 后换不掉,
worker 对着旧地址空转到天荒地老, 而 API (每请求现取) 全通。单仓与
My Home 组合部署共用同一份 (2026-10-09 起两仓 lifespan 都只调
launch_when_configured)。
"""
import threading
import time
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from .. import database
from . import place_worker, roads_worker, settings_store
from . import speed_hist_cache, tracks_cache

WARM_RETRY_S = 60     # 预热失败重试间隔 (引擎还没配对时)


def _warm_with_retry(warm: Callable[[sessionmaker[Session]], bool]) -> None:
    """预热包装: warm 返回 False (后端连不上) 就歇 60s 再来, 成一把即止。

    引擎还没配对 (docker 定位出占位地址 / 密码没存) 时启动那一把必败,
    老实现失败静默后线程就没了 —— 向导存好真地址也没人再预热, 首访
    统计页得现场积分全程; 重试到配置对了为止, 冷启积分回到后台跑。
    """
    while not warm(database.session_factory()):
        time.sleep(WARM_RETRY_S)


def _start_all() -> None:
    """线程全量开动: 预热带重试, worker 每轮现取引擎工厂 (热换即跟手)。"""
    # 后台预热轨迹缓存 (全量下采样 ~15s, 不阻塞启动; 失败 60s 一把重试)
    threading.Thread(target=_warm_with_retry, args=(tracks_cache.warm,),
                     daemon=True).start()
    # 速度直方图预热 (行车采样积分, 冷启全量 ~60s; 有盘缓存时秒级)
    threading.Thread(target=_warm_with_retry, args=(speed_hist_cache.warm,),
                     daemon=True).start()
    # 足迹「走过之路」拟合 worker (高德纠偏回填, 没配 Web 服务 key 就空转;
    # worker 自身先睡 90s 让两条预热先跑; own 工厂注入, TeslaMate 工厂
    # worker 每轮自取)
    threading.Thread(target=roads_worker.start,
                     args=(database.own_session_factory(),), daemon=True).start()
    # 常去地点命名 worker (高德逆地理回填, 同一把 Web 服务 key; 先睡 150s
    # 与 roads 错峰)
    threading.Thread(target=place_worker.start,
                     args=(database.own_session_factory(),), daemon=True).start()


def launch_when_configured() -> None:
    """数据源已配 (设置行/env/docker 任一) 立即开动; 真首启未配则 5s 一查
    自有库, 配好即开。"""
    def teslamate_ready() -> bool:
        with database.own_session_factory()() as own:  # pylint: disable=not-callable
            return "teslamate" not in settings_store.wizard_missing(own)

    if teslamate_ready():
        _start_all()
        return

    def wait_then_start() -> None:
        while not teslamate_ready():
            time.sleep(5)
        _start_all()

    threading.Thread(target=wait_then_start, daemon=True).start()
