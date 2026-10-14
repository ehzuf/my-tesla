"""地名高德化 (2026-10-14) API 级回归: 行程起终点/充电列表/统计口径的省市区
与地名一律高德缓存优先, 没刷到的逐址回退 TeslaMate (英文 OSM 链是用户实报
的坏形态); 直辖市 (高德 city=[]) 区县提市层、展示链补省名重一层; v1 老行
(只有名没区划) 名照用、区划回退 —— 平滑升级的混合口径。worker/单元级在
test_place_names, 自有库加列迁移在 test_defensive_paths。"""
from datetime import datetime

from app.tesla import repository
from app.tesla.models import Address
from app.tesla.repository.place_names import place_name_row, save_place_name
from tests.seed_factories import seed_charging, seed_drive

TRIPS = "/tesla/trips/api/sessions"


def _seed(db, owndb):
    """地址 1=深圳 (高德 v2 万象天地), 2=东莞 (无缓存行 → 全兜底),
    3=北京英文链 (高德 v2 九宫, 直辖市 city 空), 4=英文链 (v1 老行只有名)。
    行程 1: 1→3, 2: 1→2, 3: 3→2, 4: 4→2 (按出发升序); 充电 1/2/3 分别
    停在地址 1/3/4。"""
    db.add(Address(id=1, name="华为立体车库", city="深圳市",
                   display_name="广东省深圳市龙岗区坂田街道",
                   latitude=22.61, longitude=114.06))
    db.add(Address(id=2, name="长安镇", city="东莞市",
                   display_name="广东省东莞市长安镇",
                   latitude=22.75, longitude=113.75))
    db.add(Address(id=3, name="Jiugong Parking", city=None,
                   display_name="Jiugong, Daxing District, Beijing, China",
                   latitude=39.79, longitude=116.34))
    db.add(Address(id=4, name="Old Mill Road", city=None,
                   display_name="Old Mill Road, Fangshan, China",
                   latitude=22.62, longitude=114.07))
    seed_drive(db, id=1, distance=10.0, start_address_id=1, end_address_id=3)
    seed_drive(db, id=2, distance=10.0, start_address_id=1, end_address_id=2,
               start_date=datetime(2026, 9, 11, 2, 0),
               end_date=datetime(2026, 9, 11, 3, 0))
    seed_drive(db, id=3, distance=10.0, start_address_id=3, end_address_id=2,
               start_date=datetime(2026, 9, 12, 2, 0),
               end_date=datetime(2026, 9, 12, 3, 0))
    seed_drive(db, id=4, distance=10.0, start_address_id=4, end_address_id=2,
               start_date=datetime(2026, 9, 13, 2, 0),
               end_date=datetime(2026, 9, 13, 3, 0))
    seed_charging(db, id=1, address_id=1)
    seed_charging(db, id=2, address_id=3,
                  start_date=datetime(2026, 9, 8, 15, 50),
                  end_date=datetime(2026, 9, 8, 17, 2))
    seed_charging(db, id=3, address_id=4,
                  start_date=datetime(2026, 9, 9, 15, 50),
                  end_date=datetime(2026, 9, 9, 17, 2))
    save_place_name(owndb, place_name_row(
        1, "ok", 2, "万象天地", province="广东省", city="深圳市",
        district="龙岗区"))
    save_place_name(owndb, place_name_row(
        3, "ok", 2, "九宫", province="北京市", district="大兴区"))
    save_place_name(owndb, place_name_row(4, "ok", 1, "坂田老站"))


def _plain(nodes):
    """RegionNode 列表 → 可比较的递归元组 (名字排序, 摆脱同计数次序抖动)。"""
    return sorted((n["name"], n["count"], _plain(n["children"]))
                  for n in nodes)


def test_trips_amap_first_over_english_chain(auth, db, owndb):
    """行程列表: 地名/省市区链/整链高德优先, 英文 OSM 链只剩兜底份;
    直辖市展示链补省名重一层 (北京市 · 北京市 · 大兴区), v1 老行名照用
    区划回退。"""
    _seed(db, owndb)
    items = {i["id"]: i for i in auth.get(TRIPS).json()["items"]}
    a = items[1]
    assert (a["from"], a["from_region"], a["from_loc"]) == (
        "广东省深圳市龙岗区万象天地", "广东省 · 深圳市 · 龙岗区", "万象天地")
    assert (a["to"], a["to_region"], a["to_loc"]) == (
        "北京市大兴区九宫", "北京市 · 北京市 · 大兴区", "九宫")   # 直辖市
    v1 = items[4]
    assert v1["from_loc"] == "坂田老站"      # v1 老行: 名还在用
    assert v1["from_region"] is None         # 区划空 → 英文链解析不出省
    assert v1["to"] == "广东省东莞市长安镇"   # 无缓存行 → TeslaMate 兜底


def test_trips_region_filter_and_tree_amap(auth, db, owndb):
    """地区过滤/树走高德区划: 英文链地址也按 北京市/大兴区 命中 (旧口径
    匹配不上); 树混建 —— 高德三级与兜底解析并账, 直辖市区县提市层。"""
    _seed(db, owndb)

    def ids(**params):
        return [i["id"] for i in auth.get(TRIPS, params=params).json()["items"]]

    assert ids(from_loc="北京市") == [3]
    assert ids(from_loc="北京市/大兴区") == [3]
    assert ids(from_loc="广东省/深圳市") == [2, 1]     # 最新在前
    assert ids(to_loc="北京市") == [1]
    assert ids(from_loc="Fangshan") == []              # 英文不是区划
    tree = auth.get("/tesla/trips/api/regions").json()
    assert _plain(tree["start"]) == [
        ("北京市", 1, [("大兴区", 1, [])]),
        ("广东省", 2, [("深圳市", 2, [("龙岗区", 2, [])])]),
    ]
    assert _plain(tree["end"]) == [
        ("北京市", 1, [("大兴区", 1, [])]),
        ("广东省", 3, [("东莞市", 3, [("长安镇", 3, [])])]),
    ]


def test_charging_sessions_amap_fields(auth, db, owndb):
    """充电列表: location/city/region/address 高德优先; 直辖市 city 并省层;
    搜索框能搜到只在高德缓存里的名, region 过滤命中英文链地址。"""
    _seed(db, owndb)
    items = {i["id"]: i for i in
             auth.get("/tesla/charging/api/sessions").json()["items"]}
    assert (items[1]["location"], items[1]["city"],
            items[1]["region"], items[1]["address"]) == (
        "万象天地", "深圳市", "广东省 · 深圳市 · 龙岗区",
        "广东省深圳市龙岗区万象天地")
    assert (items[2]["location"], items[2]["city"],
            items[2]["region"], items[2]["address"]) == (
        "九宫", "北京市", "北京市 · 北京市 · 大兴区", "北京市大兴区九宫")
    v1 = items[3]
    assert v1["location"] == "坂田老站" and v1["city"] is None \
        and v1["region"] is None
    got = auth.get("/tesla/charging/api/sessions",
                   params={"q": "九宫"}).json()      # TeslaMate 字段全英文
    assert [i["id"] for i in got["items"]] == [2]
    got = auth.get("/tesla/charging/api/sessions",
                   params={"region": "北京市"}).json()
    assert [i["id"] for i in got["items"]] == [2]


def test_charging_dims_districts_map_amap(auth, db, owndb):
    """统计口径同源: 城市图按高德市 (直辖市并省层, v1 老行无区划不进城),
    城市下钻到高德区县, 充电地图点名/城市高德优先。"""
    _seed(db, owndb)
    dims = auth.get("/tesla/charging/api/dimensions").json()
    assert sorted((c["city"], c["sessions"]) for c in dims["by_city"]) == [
        ("北京市", 1), ("深圳市", 1)]
    drill = auth.get("/tesla/charging/api/districts",
                     params={"city": "北京市"}).json()
    assert [(d["district"], d["sessions"]) for d in drill] == [("大兴区", 1)]
    pts = {p["id"]: p for p in
           auth.get("/tesla/charging/api/map-locations").json()}
    assert (pts[3]["name"], pts[3]["city"]) == ("九宫", "北京市")
    assert (pts[1]["name"], pts[1]["city"]) == ("万象天地", "深圳市")
    assert (pts[4]["name"], pts[4]["city"]) == ("坂田老站", None)


def test_merged_track_header_amap(db, owndb):
    """回放合并轨迹头部起终点同口径高德优先 (没刷到的回退清洗链)。"""
    _seed(db, owndb)
    plan = repository.merged_track_plan(db, owndb, [1])
    assert plan.header.from_ == "广东省深圳市龙岗区万象天地"
    assert plan.header.to == "北京市大兴区九宫"
