// view/group-trips-marks.js — 弹层第四页「详细行程」(3.10.0) 3/3: 多选与
// 落定 —— 进入即多选态 (钩 = 分组成员, 组内行默认全钩): 点行打/撤钩不
// 写库, 页底常驻「取消/确定」—— 取消整批回服务端原样, 确定一次提交,
// 连续性服务端守 (加 = 区间外延整段吸收, 移 = 只从两端收窄), 拒了就整
// 页重拉对齐真身。行渲染与钩集在 group-trips-stream (先加载), 状态两边
// 共享 (经典脚本全局)。
/* global $, postJSON, toast, gtrGid, gtrGroup: writable, gtrStream,
          gtrSel, gtrResetSel, gtrLoad, gtrRefreshRows */
"use strict";

/* 原组里还保留钩的端点 (服务端真身口径): 组内行撤钩只许从这两端收 */
function gtrKeptEnds(orig) {
  const kept = [...gtrSel].filter(id => orig.has(id));
  return kept.length ? [Math.min(...kept), Math.max(...kept)] : [];
}

/* 点行 = 打/撤钩 (不写库; 整行都是点击目标 —— 全 app 的列表行都点整行):
   组外行打钩自由 (区间外延, 中间的服务端整段吸收); 组内行撤钩只许从
   两端收 —— 挖中间会断连续, 与服务端口径同一句人话; 撤了的再点回来
   也自由 */
$("#gtr-list").addEventListener("click", e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;
  const row = t.closest(".gtr-row");
  if (!row) return;
  const it = gtrStream.find(x => x.id === +row.dataset.id);
  if (!it) return;
  if (gtrSel.has(it.id)) {
    const orig = new Set(gtrGroup ? gtrGroup.ids : []);
    const [lo, hi] = gtrKeptEnds(orig);   // 撤这钩之前先看保留侧端点
    if (orig.has(it.id) && lo < it.id && it.id < hi) {
      toast("只能移出最前或最后的行程");   // 组内中段: 撤了会断连续
      return;
    }
    gtrSel.delete(it.id);
  } else {
    gtrSel.add(it.id);
  }
  gtrRefreshRows();
});

/* 确定: 钩集一次提交 (adds = 新钩进的组外, removes = 撤钩的原组内;
   服务端原子落库并归一全展开); 成功后分组条目换新, 已加载行按新成员
   表就地翻, 钩集复位对齐真身 (吸收的未加载段下次拉动自会对状态来)。
   没改动点了就是 no-op。服务端拒了 (口径话 toast) 就整页重拉对齐真身 */
$("#gtr-ok").addEventListener("click", async () => {
  if (!gtrGroup || !gtrGid) return;
  const orig = new Set(gtrGroup.ids);
  const adds = [...gtrSel].filter(id => !orig.has(id));
  const removes = [...orig].filter(id => !gtrSel.has(id));
  if (!adds.length && !removes.length) return;
  try {
    const upd = await postJSON(
      `/tesla/trips/api/groups/${gtrGid}/changes`, { adds, removes });
    gtrGroup = upd.group;
    const inNew = new Set(upd.group.ids);
    for (const x of gtrStream) x.in_group = inNew.has(x.id);
    gtrResetSel();
    gtrRefreshRows();
    toast("已保存分组修改");
  } catch (err) {
    toast(err.message || "保存失败");
    gtrLoad();   // 对齐服务端真身 (整页重拉, 钩集随重拉复位)
  }
});

/* 取消: 整批撤销, 钩集与行回服务端原样 (已加载的页不丢) */
$("#gtr-cancel").addEventListener("click", () => {
  gtrResetSel();
  gtrRefreshRows();
});
