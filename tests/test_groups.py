"""行程分组视图测试: 壳内骨架 + 分组视图交互片段 (CRUD 走 trips 的
api/groups, 已在 test_trips 覆盖; 这里只管视图挂载)。3.0 单壳后旧页的
顶栏/页签菜单没了 —— 骨架断言只留视图自身标记 (生命周期/手势断言在
test_shell_views)。"""

from tests.tesla_static_files import served_page

SHELL = "/tesla"


def test_groups_page_served(auth):
    """分组视图: 列表骨架 (转圈/列表/空态/错误重试) + 计数徽标 (toast 在壳层)。"""
    html = served_page(auth, SHELL)
    for frag in ['data-view="groups"', 'id="gp-count-badge"', 'id="gp-spin"',
                 'id="gp-list"', 'id="gp-empty"', 'id="gp-errbox"',
                 'id="gp-retry"', 'id="toast"',
                 '<script src="/tesla/static/js/view/groups-page.js?v=8"></script>',
                 '在行程列表长按多选行程后点「存为分组」']:
        assert frag in html, f"分组视图缺少 {frag}"
    # 弹层块已升壳级 (2026-09-22): 分组页打开的合并弹层宿主是分组视图,
    # 行程视图藏起时这层照常显 —— 背后不再闪「行程轨迹」(用户实报)
    assert 'id="backdrop"' in html and 'id="sheet"' in html
    assert html.index('id="sheet"') > html.index('<aside id="drawer"')   # 壳级: 在抽屉之后


def test_groups_page_interactions(auth):
    """分组视图脚本: 打开 = 壳级合并弹层直接开 (弹层带分组名当标题,
    sheetFrom 记来源, 关弹层原地刷新分组列表; 不跳行程视图), 改名行内
    编辑, 删除二次确认, 卡片化样式对齐行程列表 (card-t 同一套)。行内
    重渲染会脱链事件目标 —— 委托先判 isConnected (与行程页同一坑)。"""
    js = auth.get("/tesla/static/js/view/groups-page.js?v=8").text
    for frag in ['"/tesla/trips/api/groups"', "function rowHTML(",
                 "async function gpLoad()",
                 'sheetFrom = "groups"',
                 # 3.10.0 起每次进都重拉 (明细页会改分组, 回来要新数据);
                 # 转圈只在没数据时亮 (gpBooted 门控), 静默换血不闪白屏
                 'show() { gpLoad(); }', "gpBooted",
                 "if (!gpBooted || groups.length === 0) $(\"#gp-spin\").hidden = false;",
                 # 整个分组条目随键传给 openMerged (带汇总, 弹层数字带一开
                 # 就显数, 2026-09-23 用户点名「加载完地图才显示」)
                 "openMerged(item.dataset.ids, null, group)",
                 'classList.add("arm")', "确认删除",
                 'method: "DELETE"', 'method: "PATCH"',
                 'gp-list").addEventListener("click"',
                 'gp-list").addEventListener("keydown"',
                 "!t.isConnected", 'status === 401',
                 'class="gp-input"', 'maxlength="30"',
                 'class="gp-item card-t"', 'class="gp-acts"']:
        assert frag in js, f"groups-page.js 缺少 {frag}"
    # 不再跳行程视图 (背后停在分组列表); 离开视图与行程 hide 同一套收尾
    assert 'navigate("trips")' not in js
    assert "bumpOpenSeq();" in js and "stopRecExport(true)" in js
    # 改名/删除按钮有结果才动列表; Enter 提交 / Esc 放弃
    assert 'e.target.classList.contains("gp-input")' in js
    assert 'e.key === "Enter"' in js and 'e.key === "Escape"' in js


def test_groups_card_span_not_clipped(auth):
    """跨度没显示全 (2026-09-25 用户两轮实报): 分组卡统计格沿用行程卡的
    .ct-cells 对半分 (flex:1), 那是给短数值设计的; 跨度是日期串在半格里
    必触发 .val 的省略号截尾。三重修复都要在:
    1) 里程格收成按内容宽, 跨度格吃剩下整段 (只钉 .gp-list 下, 行程卡
       三格照旧均分);
    2) 字号真收一档: 旧 .gp-span (0,1,0) 永远输给后加载 trips-cards 的
       .ct-cell .val (0,2,0), 从未生效 —— 跨度一直按 17px 渲染, 这就是
       第一轮修复后用户仍报显示不全的根因; .gp-list .val.gp-span 抬到
       (0,3,0) 才压得过;
    3) nowrap/省略号改 normal: 服务端日期已是紧凑斜杠 (2026/09/09,
       斜杠是干净断行点), 真装不下按 / 换行保底显示全。"""
    css = auth.get("/tesla/static/css/tesla-groups.css").text
    assert ".gp-list .ct-cell:first-child { flex: none; }" in css
    assert ".gp-list .val.gp-span { font-size: 15px; white-space: normal; }" in css
    assert ".gp-span { font-size: 15px; }" not in css   # 死规则 (0,1,0) 不回潮
    trips_css = auth.get("/tesla/static/css/tesla-trips-cards.css").text
    assert ".ct-cell { flex: 1; min-width: 0;" in trips_css   # 行程卡均分不动
    assert ".ct-cell .val {" in trips_css   # 特异性对手 (0,2,0): 跨度规则必须更高
    html = served_page(auth, SHELL)
    assert "css/tesla-groups.css?v=9" in html   # v9: sec-head 顶距 0 (v8 落后一版)


# ---------------------------------------------------------------- 分组明细 (3.10.0)

def test_group_trips_view_skeleton(auth):
    """分组明细视图骨架 (3.10.0): 分组点开后的二级页 —— 组内外行程一列
    (返回钮/两端加载提示行/转圈/错误重试), 不进抽屉菜单 (零历史路由, ‹ 回
    分组列表); 合并弹层头部挂「详细行程」入口 (右键钮包 .sh-head-btns,
    头部两栏网格塞不下第三颗裸按钮)。"""
    html = served_page(auth, SHELL)
    for frag in ['data-view="group-trips"', 'id="gtr-back"', 'id="gtr-name"',
                 'id="gtr-count"', 'id="gtr-top"', 'id="gtr-list"',
                 'id="gtr-tail"', 'id="gtr-spin"', 'id="gtr-errbox"',
                 'id="gtr-retry"', 'aria-label="返回分组列表"',
                 'id="sh-group-btn"', ">详细行程</button>", 'class="sh-head-btns"',
                 'css/tesla-group-trips.css?v=1',
                 '<script src="/tesla/static/js/view/group-trips-page.js?v=1"></script>',
                 '<script src="/tesla/static/js/view/group-trips-stream.js?v=1"></script>']:
        assert frag in html, f"分组明细视图缺少 {frag}"
    # 二级页不进抽屉菜单 (入口只有弹层按钮)
    drawer_js = auth.get("/tesla/static/js/tesla-drawer.js").text
    assert '"group-trips"' not in drawer_js


def test_group_trips_view_interactions(auth):
    """分组明细视图脚本 (3.10.0): 弹层「详细行程」带 gid 跳明细页 (载荷只
    有分组页打开才有 gid —— 多选合并/深链没有, 按钮整颗藏); 默认窗口 =
    组内全部时间正序; 顶部下拉加载更前 (prepend 后 scrollTop 回补不跳位,
    ptr 提示字进页换「松开加载更早」), 尾部触底 IO 加载更后 (链式续载);
    就地加入/移出只翻已加载行 (changed 集合 + 端点重判), 不整页重拉。"""
    page_js = auth.get("/tesla/static/js/view/group-trips-page.js?v=1").text
    for frag in ['function openGroupTrips(gid)', 'navigate("group-trips")',
                 'if (!gtrGid) { navigate("groups"); return; }',   # 恢复停留没上下文: 弹回分组列表
                 'if (curKey != null) closeTrip();',
                 '$("#sh-group-btn").addEventListener("click"',
                 "松开加载更早", "松开刷新",        # ptr 共享提示字进/离页换还原
                 'onRefresh: () => gtrLoadBefore()',   # 流文件后加载: 箭头延迟解析
                 'registerView("group-trips"']:
        assert frag in page_js, f"group-trips-page.js 缺少 {frag}"
    stream_js = auth.get("/tesla/static/js/view/group-trips-stream.js?v=1").text
    for frag in ["const GTR_PAGE = 24",
                 "before=${gtrStream[0].id}&limit=${GTR_PAGE}",
                 "after=${gtrStream[gtrStream.length - 1].id}&limit=${GTR_PAGE}",
                 "sc.scrollTop += sc.scrollHeight - h0;",   # prepend 视口钉原首行
                 "d.items.concat(gtrStream)", "gtrStream.concat(d.items)",
                 "has_more_before", "has_more_after",
                 "new IntersectionObserver", 'rootMargin: PRELOAD_PX + "px"',
                 'class="gtr-add"', 'class="gtr-rm"', ">加入分组</button>",
                 ">移出分组</button>", "已加入分组", "已移出分组",
                 "function gtrRefreshRows()", "el.replaceWith(gtrRow(it))",
                 "${gtrGid}/${add ? \"add\" : \"remove\"}", "upd.changed",
                 "gtrMarquee()"]:
        assert frag in stream_js, f"group-trips-stream.js 缺少 {frag}"
    # gid 载荷链: openMerged 只在分组页打开时带 gid, 弹层头部按钮按它亮/藏
    merged_js = auth.get("/tesla/static/js/view/trips-sheet-page.js?v=9").text
    assert "gid: info && info.id != null ? info.id : null" in merged_js
    drv_js = auth.get("/tesla/static/js/view/trips-sheet-driver.js?v=14").text
    assert '$("#sh-group-btn").hidden = it.gid == null;' in drv_js
    assert '$("#sh-group-btn").hidden = it && it.gid == null;' in drv_js
