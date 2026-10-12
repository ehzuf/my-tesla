// view/group-trips-page.js — 分组明细页 (3.10.0) 1/2: 底座 —— 打开入口
// (合并弹层头部「详细行程」, 分组页打开的弹层才亮), 视图生命周期
// (registerView: 每次进都重拉默认窗口 = 组内全部时间正序 —— 明细页里
// 加/移过行程, 回分组列表再进要新数据; 冷启恢复/深链落进这没分组上下文
// 时同步弹回分组列表, 双跳在同一 JS 任务里完成, 浏览器不画中间帧),
// 手势面 (顶部下拉 = 加载更前的组外行程, 共享的 #ptr-hint 文案临时换),
// 底部触底加载与行渲染/就地加移在流文件 (group-trips-stream.js)。
/* global $, registerView, bindGestures, navigate, closeTrip, curKey,
          gtrLoad, gtrLoadBefore */
/* exported openGroupTrips */
"use strict";

let gtrGid = null;      // 当前明细页的分组 id (弹层载荷带来, 进页前就定)

/* 弹层头部「详细行程」: dataset.gid 由 fillSheetHeader 按载荷写入 (分组页
   打开才有; 多选合并/深链重开没有, 按钮整颗藏着)。点开 = 关弹层跳明细页
   (curKey 兜底防弹层不在时误关)。 */
$("#sh-group-btn").addEventListener("click", () => {
  const gid = +$("#sh-group-btn").dataset.gid;
  if (gid) openGroupTrips(gid);
});

function openGroupTrips(gid) {
  gtrGid = gid;
  if (curKey != null) closeTrip();     // 弹层收掉 (地址栏镜像回裸壳地址)
  navigate("group-trips");
}

/* 返回: 回分组列表 (那边每次 show 都重拉, 段数/里程即时反映这页的改动) */
$("#gtr-back").addEventListener("click", () => navigate("groups"));

$("#gtr-retry").addEventListener("click", () => gtrLoad());

/* 手势: 列表滚动器 —— 右划开抽屉, 在顶下拉 = 加载更前的组外行程 (松手
   才拉, 拉动中的「松开加载更早」提示由 ptr 机制统一浮出)。onRefresh 包
   一层箭头: gtrLoadBefore 在后加载的流文件里 (点击时才解析, 与行程页
   openMerged 同法), 裸引用会在本模块加载期就 ReferenceError */
bindGestures($("#gtr-scroll"), { drawer: true, ptr: true, onRefresh: () => gtrLoadBefore() });

registerView("group-trips", {
  title: "分组行程",
  el: $("#view-group-trips"),
  show() {
    if (!gtrGid) { navigate("groups"); return; }   // 恢复停留落进这: 弹回分组列表
    $("#ptr-hint").textContent = "松开加载更早";    // 全壳共享一只提示, 进页换文案
    gtrLoad();
  },
  hide() { $("#ptr-hint").textContent = "松开刷新"; },
  refresh: () => gtrLoad(),     // 换车: 重拉默认窗口 (组内行程跟车走)
});
