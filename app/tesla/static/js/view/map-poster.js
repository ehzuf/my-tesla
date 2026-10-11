// view/map-poster.js — 足迹地图「高清图」按钮 (2026-10-11 用户点名「下载高清
// 轨迹地图, 地图大小不限, 精度拉满, 要求带文字」): 服务端把屏上同一批
// 「走过的路」整幅画成 PNG —— 拟合顶点全量不抽稀, 不迁就车机浏览器画布/
// 内存上限 (8K 封顶那套是画布的, 海报走服务端想多大画多大)。屏上筛选是
// 什么海报就是什么 (车/驾驶员筛选照带); 生成期间钮置忙态 (全量渲染几秒),
// 落盘文件名带日期, 失败 toast 业务文案。
/* global $, toast, diag, fpVisibleTracks */
"use strict";

// 钮住 #fp-stats 行尾 (汇总出数才露脸 —— 没数就没路可导)
const btn = $("#fp-poster");

btn.addEventListener("click", async () => {
  if (btn.disabled) return;
  const ids = fpVisibleTracks().map((t) => t.id);
  if (!ids.length) { toast("还没有走过的路可导出"); return; }
  btn.disabled = true;
  const label = btn.textContent;
  btn.textContent = "生成中…";
  try {
    const r = await fetch("/tesla/map/api/roads/poster", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    if (r.status === 401) { location.replace("/login"); return; }
    if (!r.ok) {   // 业务错 (还没有走过的路可画等) → detail 文案
      const body = await r.json().catch(() => null);
      throw new Error((body && body.detail) || `${r.status} ${r.statusText}`);
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const d = new Date();
    a.href = url;
    a.download = "足迹地图_" + d.getFullYear() + "-" +
      String(d.getMonth() + 1).padStart(2, "0") + "-" +
      String(d.getDate()).padStart(2, "0") + ".png";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);   // 等下载接管再回收
    toast("已下载");
  } catch (e) {
    diag("poster_fail", { msg: String(e && e.message || e).slice(0, 200) });
    toast(e && e.message || "生成失败");
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
});
