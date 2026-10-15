"""后台任务页 API 测试 (设置组「后台任务」): 列表进度口径 (与 worker 待办
同口径, 旧版本行不算) / 状态机 (没 Key 待配置, 处理完完成) / 重启语义
(清成果 + 撤首回旗 + 清放弃名单, 回包进度归零)。"""
from datetime import datetime

from app.tesla import place_worker, roads_worker
from app.tesla.models import Address, AppSetting, DriveRoad, PlaceName
from app.tesla.repository.map_roads import road_row, save_road
from app.tesla.repository.place_names import place_name_row, save_place_name
from app.tesla.roads_fit import ROAD_FIT_V
from app.tesla.settings_store import (mark_roads_initial_done,
                                      roads_initial_done_value)
from tests.map_seed_helpers import _two_point_drive

TASKS = "/tesla/api/tasks"


def _by_id(rows):
    return {t["id"]: t for t in rows}


def _seed_drive(db, drive_id, day):
    _two_point_drive(db, drive_id, datetime(2026, 9, day, 2, 0))


def _seed_address(db, addr_id, lat, lng):
    db.add(Address(id=addr_id, name=f"点{addr_id}", city="深圳市",
                   display_name="广东省深圳市", latitude=lat, longitude=lng))
    db.commit()


def test_tasks_progress_and_states(auth, db, owndb):
    """进度 = 当前版本有行的 / 全量 (旧 v 行不算, 无坐标地址不进总数);
    配了 Key 的任务 running, 处理完的 done。"""
    _seed_drive(db, 5, 1)
    _seed_drive(db, 6, 2)
    _seed_drive(db, 7, 3)
    save_road(owndb, road_row(5, "ok", ROAD_FIT_V,
                              [114.0, 22.5, 114.01, 22.5], 2, 1.2, ""))
    save_road(owndb, road_row(6, "failed", ROAD_FIT_V, [], 0, 0.0, "grab_fail"))
    save_road(owndb, road_row(7, "ok", 0, [114.0, 22.5], 1, 0.5, ""))  # 旧 v 不算
    _seed_address(db, 1, 22.55, 114.05)
    _seed_address(db, 2, 22.60, 114.10)
    db.add(Address(id=3, name="无坐标", city="东莞市",
                   display_name="广东省东莞市"))   # 没坐标: 不进总数
    db.commit()
    save_place_name(owndb, place_name_row(1, "ok", place_worker.PLACE_NAME_V,
                                          "坂田街道"))
    save_place_name(owndb, place_name_row(2, "ok", 0, "旧版名"))    # 旧 v 不算

    rows = _by_id(auth.get(TASKS).json())
    roads, places = rows["roads"], rows["places"]
    assert (roads["done"], roads["total"]) == (2, 3)
    assert roads["state"] == "running"
    assert (places["done"], places["total"]) == (1, 2)
    assert places["state"] == "running"
    # 处理完的任务转 done
    save_road(owndb, road_row(7, "ok", ROAD_FIT_V, [114.0, 22.5], 1, 0.5, ""))
    save_place_name(owndb, place_name_row(2, "ok",
                                          place_worker.PLACE_NAME_V, "长安镇"))
    rows = _by_id(auth.get(TASKS).json())
    assert rows["roads"]["state"] == "done"
    assert rows["places"]["state"] == "done"


def test_tasks_blocked_without_web_key(auth, owndb):
    """没配 Web 服务 Key: 两个任务都待配置 (页面教人去哪补)。"""
    owndb.get(AppSetting, 1).amap_web_key = ""
    owndb.commit()
    rows = _by_id(auth.get(TASKS).json())
    assert rows["roads"]["state"] == "blocked"
    assert rows["places"]["state"] == "blocked"


def test_restart_roads_wipes_and_recounts(auth, db, owndb):
    """重启拟合: 行清空 / 首回旗撤 / 放弃名单清, 回包进度归零。"""
    _seed_drive(db, 5, 1)
    _seed_drive(db, 6, 2)
    save_road(owndb, road_row(5, "ok", ROAD_FIT_V,
                              [114.0, 22.5, 114.01, 22.5], 2, 1.2, ""))
    save_road(owndb, road_row(6, "failed", ROAD_FIT_V, [], 0, 0.0, "grab_fail"))
    mark_roads_initial_done(owndb)
    roads_worker._State.attempts[99] = 3        # 放弃过的行程

    r = auth.post(f"{TASKS}/roads/restart")
    assert r.status_code == 200
    rows = _by_id(r.json())
    assert (rows["roads"]["done"], rows["roads"]["total"]) == (0, 2)
    assert owndb.query(DriveRoad).count() == 0
    assert roads_initial_done_value(owndb) is False
    assert not roads_worker._State.attempts


def test_restart_places_wipes(auth, db, owndb):
    """重启命名: 行清空回包归零 (没有首回旗 —— 地点名不走蒙版)。"""
    _seed_address(db, 1, 22.55, 114.05)
    _seed_address(db, 2, 22.60, 114.10)
    save_place_name(owndb, place_name_row(1, "ok", place_worker.PLACE_NAME_V,
                                          "坂田街道"))
    place_worker._State.attempts[88] = 3

    r = auth.post(f"{TASKS}/places/restart")
    assert r.status_code == 200
    rows = _by_id(r.json())
    assert (rows["places"]["done"], rows["places"]["total"]) == (0, 2)
    assert owndb.query(PlaceName).count() == 0
    assert not place_worker._State.attempts


def test_restart_unknown_task_404(auth):
    """没有的任务重启 404。"""
    assert auth.post(f"{TASKS}/nope/restart").status_code == 404
