// view/group-trips-marks.js — 弹层第四页「详细行程」(3.10.0) 3/3: 标记与
// 落定 —— 加/移不直接写库, 点行只是标记 (本地预览翻转, 成员端点跟着标
// 记现算), 页底「取消/确认」才动真格: 取消整批撤销; 确认一批提交, 连续
// 性服务端守 (加 = 区间外延整段吸收, 移 = 只从两端收窄), 返回的分组条目
// 就地翻已加载行 (拉动加载的页不丢)。行渲染与窗口加载在 group-trips
// -stream (先加载), 状态在两边共享 (经典脚本全局)。
/* global $, postJSON, toast, gtrGid, gtrStream: writable, gtrGroup: writable,
          gtrLoad, gtrRefreshRows */
/* exported gtrEff, gtrEnds, gtrClearMarks */
"use strict";

let gtrMarks = null;    // 标记集 (id → 目标态; null = 没有标记, 确认条收起)

/* 行的落点态: 标记盖过原态 (点行即预览), 没标记 = 服务端原样 */
function gtrEff(it) {
  return gtrMarks && gtrMarks.has(it.id) ? gtrMarks.get(it.id) : it.in_group;
}

/* 成员端点 (移标记钮只给这两行): 原组 ids 按标记现算 —— 标记加的段外
   延端点, 标记移的收回来; 未加载的吸收段夹在中间, 不影响首尾 */
function gtrEnds() {
  const ids = new Set(gtrGroup ? gtrGroup.ids : []);
  if (gtrMarks) for (const [id, on] of gtrMarks) on ? ids.add(id) : ids.delete(id);
  return ids.size ? [Math.min(...ids), Math.max(...ids)] : [];
}

/* 标记条: 有标记才亮 (浮在页底), 文案报段数 */
function gtrBarSync() {
  const n = gtrMarks ? gtrMarks.size : 0;
  $("#gtr-bar").hidden = !n;
  if (n) $("#gtr-bar-lb").textContent = `已标记 ${n} 段`;
}

function gtrClearMarks() {
  gtrMarks = null;
  gtrBarSync();
}

/* 点行 = 打/撤标记 (不写库; 整行都是点击目标 —— 全 app 的列表行都点整
   行, 只有钮可点用户报「item 点不了」): 组外行点 = 标记加入; 组内行点 =
   标记移出, 但只许端点 (中间移会断连续, 与服务端口径同一句人话); 再点
   已标记的行 = 撤销该行标记。底部按钮与点行同一判定 (closest 到行即
   中, 按钮只是当前动作的可视提示) */
$("#gtr-list").addEventListener("click", e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;
  const row = t.closest(".gtr-row");
  if (!row) return;
  const it = gtrStream.find(x => x.id === +row.dataset.id);
  if (!it) return;
  const want = !gtrEff(it);   // 点行 = 翻转当前落点态
  if (!want && it.in_group && !gtrEnds().includes(it.id)) {
    toast("只能移出最前或最后的行程");   // 组内中段: 移了会断连续
    return;
  }
  if (!gtrMarks) gtrMarks = new Map();
  if (it.in_group === want) gtrMarks.delete(it.id);   // 落回原态 = 撤标记
  else gtrMarks.set(it.id, want);
  if (!gtrMarks.size) gtrMarks = null;
  gtrBarSync();
  gtrRefreshRows();
});

/* 确认: 标记的加/移整批一次提交 (服务端原子落库); 成功后分组条目换新,
   已加载行按新成员表就地翻 (吸收的未加载段下次拉动自会对状态来)。服务
   端拒了 (口径话 toast) 就整页重拉对齐真身 —— 标记作废 */
$("#gtr-ok").addEventListener("click", async () => {
  if (!gtrMarks || !gtrMarks.size || !gtrGid) return;
  const adds = [], removes = [];
  for (const [id, on] of gtrMarks) (on ? adds : removes).push(id);
  try {
    const upd = await postJSON(
      `/tesla/trips/api/groups/${gtrGid}/changes`, { adds, removes });
    gtrGroup = upd.group;
    const inNew = new Set(upd.group.ids);
    for (const x of gtrStream) x.in_group = inNew.has(x.id);
    gtrClearMarks();
    gtrRefreshRows();
    toast("已保存分组修改");
  } catch (err) {
    toast(err.message || "保存失败");
    gtrLoad();   // 对齐服务端真身 (整页重拉, 标记已随重拉复位)
  }
});

/* 取消: 整批撤销, 行回服务端原样 (已加载的页不丢) */
$("#gtr-cancel").addEventListener("click", () => {
  gtrClearMarks();
  gtrRefreshRows();
});
