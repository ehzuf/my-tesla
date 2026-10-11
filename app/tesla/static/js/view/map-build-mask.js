// view/map-build-mask.js — 足迹地图首回构造蒙版 (2026-10-11): 刚配好高德
// Key 后, 后台把历史行程逐条拟合到实际道路 (首回上千次调用, 几十分钟),
// 期间足迹地图盖「正在构造数据」模糊蒙版 + 进度条, 轮询 /roads/status
// (done/total 与 worker 待办同口径, 首回清空含放弃收尾后 initial_done 置位)
// 造完自动掀开。只盖首回: 老部署 (早已造好) 首查即终态, 蒙版永不出现;
// 空车库 total=0 也不蒙。蒙版底下地图照常起, 造好的路在模糊后渐进冒出
// (涨了且隔 ≥30s 补一轮同步让新路露脸); 掀盖是终态, 进程内不再轮询,
// 之后增量新行程照旧走水位补。
/* global $, getJSON, diag, fpSync, fpViewOn */
/* exported fpBuildWatch, fpBuildStop, fpBuildPoke */
"use strict";
const FP_BUILD_MS = 3000;        // 轮询间隔 (3s 一跳, 造几十分钟也不刷屏)
const FP_BUILD_SYNC_MS = 30000;  // 蒙版期补同步节流 (底下跟着长路才有的看)

let fpBuildTimer = null;    // 轮询句柄 (视图切走收掉, 回来重建)
let fpBuildBusy = false;    // 单飞: 上一查没回来不发下一查
let fpBuildShown = false;   // 蒙版正盖着 (没盖过就不存在「掀」)
let fpBuildDone = false;    // 终态: 首回已清空, 进程内永不再蒙
let fpBuildLastDone = -1;   // 上次读到的 done (涨了才考虑补同步)
let fpBuildSyncAt = 0;      // 上次补同步时刻 (节流)

function fpBuildApply(st) {
  const finished = st.initial_done || (st.total > 0 && st.done >= st.total);
  if (finished) {              // 掀盖 = 终态: 收轮询; 盖过才补一轮收尾同步
    fpBuildDone = true;
    fpBuildStop();
    if (fpBuildShown) {
      fpBuildShown = false;
      $("#fp-build").hidden = true;
      diag("fp_build_done", {});
      fpSync();                // 造好的最后一批路这轮露脸
    }
    return;
  }
  if (!st.total) return;       // 空车库: 不蒙 (worker 置旗后自然终态)
  fpBuildShown = true;
  $("#fp-build").hidden = false;
  const pct = Math.min(100, Math.round(st.done / st.total * 100));
  $("#fp-build-fill").style.width = pct + "%";
  $("#fp-build-num").textContent =
    st.done + " / " + st.total + " · " + pct + "%";
  if (fpBuildLastDone >= 0 && st.done > fpBuildLastDone
      && Date.now() - fpBuildSyncAt >= FP_BUILD_SYNC_MS) {   // 长出新路到节流点
    fpBuildSyncAt = Date.now();
    fpSync();                  // 骑 map-boot 的同步互斥, 不并发
  }
  fpBuildLastDone = st.done;
}

async function fpBuildPoll() {
  if (fpBuildDone || fpBuildBusy) return;
  fpBuildBusy = true;
  try {
    fpBuildApply(await getJSON("/tesla/map/api/roads/status?_=" + Date.now()));
  } catch { /* 网络闪断/服务重启: 蒙版冻结, 下轮再试 */ }
  finally { fpBuildBusy = false; }
}

function fpBuildWatch() {   // 进视图 (map-filters.show 首句): 立查 + 起轮询
  if (fpBuildDone) return;
  fpBuildPoll();
  if (fpBuildTimer === null) fpBuildTimer = setInterval(fpBuildPoll, FP_BUILD_MS);
}

function fpBuildStop() {    // 切走视图 (map-filters.hide): 收轮询
  if (fpBuildTimer !== null) { clearInterval(fpBuildTimer); fpBuildTimer = null; }
}

function fpBuildPoke() {    // 下拉刷新/换筛选 (map-filters.refresh): 立查
  if (fpViewOn) fpBuildPoll();
}

document.addEventListener("visibilitychange", () => {   // 从后台切回立即查
  if (!document.hidden && fpViewOn) fpBuildPoll();
});
