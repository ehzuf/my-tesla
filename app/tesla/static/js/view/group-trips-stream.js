// view/group-trips-stream.js — 分组明细页 (3.10.0) 2/2: 流 —— 行渲染
// (组内外同列, 组外降透明 + 加入钮; 组内徽标, 两端行才有移出钮), 默认
// 窗口 = 组内全部 (id 升序 = 落库序 = 出发序, 时间正序), 两端拉动加载组外
// 候选 (顶部下拉 prepend 视口钉原首行, 尾部触底 IO + 首屏不满链式续载),
// 就地加/移 (连续性服务端守: 加 = 区间外延整段吸收, 移 = 只收头尾;
// 返回的 changed 只翻已加载行的状态, 拉动加载的页不丢, 不整页重拉)。
/* global $, esc, num, toast, fmtCardDate, fmtDur, getJSON, postJSON,
          gtrGid, PRELOAD_PX */
/* exported gtrLoad, gtrLoadBefore */
"use strict";

const GTR_PAGE = 24;    // 两端拉动一次拉多少条组外候选

let gtrStream = [];     // 已加载行程 (id 升序), 与 #gtr-list 子元素一一对应
let gtrGroup = null;    // 当前分组条目 (页头段数 + 成员端点判定用)
let gtrMoreB = false, gtrMoreA = false;   // 两端还有没有组外候选 (服务端口径)
let gtrBusy = false;    // 一次只跑一个加载 (下拉/触底/重试并发防抖)

/* 起终点短地名: trips-list-page 的 shortPlace 是顶层裸名 (经典脚本 =
   全局), 撞名各自覆盖, 这里改名复制保口径 (市 · 最小行政级, 地名不混
   入; 解析不出链退回整串) */
function gtrShortPlace(region, full) {
  const seg = (region || "").split(" · ").filter(Boolean);
  const pp = seg.length >= 3 ? seg.slice(-2) : seg.slice(-1);
  return pp.length ? pp.join(" · ") : full;
}

/* 组成员的两端 id (移出钮只给这两行; ids 服务端保证升序全展开) */
function gtrEnds() {
  const ids = gtrGroup ? gtrGroup.ids : [];
  return ids.length ? [ids[0], ids[ids.length - 1]] : [];
}

function gtrRow(it) {
  const el = document.createElement("article");
  el.className = "card-t gtr-row" + (it.in_group ? " in" : "");
  el.dataset.id = it.id;
  const [lo, hi] = gtrEnds();
  const fromP = gtrShortPlace(it.from_region, it.from);
  const toP = gtrShortPlace(it.to_region, it.to);
  /* 按钮: 组外 → 加入 (点谁区间就外延到谁); 组内两端 → 移出 (中间行没有,
     挖洞会断开连续); 组内中间 → 无按钮 */
  const acts = !it.in_group
    ? '<div class="gtr-acts"><button type="button" class="gtr-add">加入分组</button></div>'
    : (it.id === lo || it.id === hi)
      ? '<div class="gtr-acts"><button type="button" class="gtr-rm">移出分组</button></div>'
      : "";
  el.innerHTML = `
    <div class="ct-top">
      <span class="ct-date">${esc(fmtCardDate(it.start))}</span>
      ${it.in_group ? '<span class="gtr-badge">组内</span>' : ""}
    </div>
    <div class="ct-cells">
      <div class="ct-cell"><div class="lb">里程</div>
        <div class="val">${it.km != null ? num(it.km) + "<small>km</small>" : "—"}</div></div>
      <div class="ct-cell"><div class="lb">时长</div><div class="val">${fmtDur(it.min)}</div></div>
      ${it.kwh != null ? `<div class="ct-cell"><div class="lb">总电耗</div>
        <div class="val">${num(it.kwh)}<small>kWh</small></div></div>` : ""}
    </div>
    <div class="ct-addr mq-line"><span class="mq-run"><i class="dot f"></i>${esc(fromP)}<span class="arr">→</span><i class="dot t"></i>${esc(toP)}</span></div>
    ${acts}`;
  return el;
}

/* 起终点行超宽滚动: trips-list-page 同款, 量宽限本视图 (藏着量不出宽,
   跳过不挂; 转屏后重量防抖) */
function gtrMarquee() {
  for (const line of $("#gtr-list").querySelectorAll(".mq-line")) {
    const run = line.querySelector(".mq-run");
    run.classList.remove("marquee");
    if (!line.clientWidth) continue;
    const over = run.scrollWidth - line.clientWidth;
    if (over <= 2) continue;
    run.style.setProperty("--mq-dx", `${-over}px`);
    run.style.setProperty("--mq-dur", `${Math.max(8, over / 18)}s`);
    run.classList.add("marquee");
  }
}
addEventListener("resize", () => setTimeout(gtrMarquee, 200));

function gtrRender() {
  $("#gtr-name").textContent = gtrGroup ? gtrGroup.name : "分组行程";
  $("#gtr-count").textContent = gtrGroup ? `${gtrGroup.n} 段` : "";
  $("#gtr-list").innerHTML = "";
  for (const it of gtrStream) $("#gtr-list").appendChild(gtrRow(it));
  $("#gtr-top").hidden = !gtrMoreB;    // 两端提示行: 还有候选才亮, 拉空即收
  $("#gtr-top").textContent = "下拉加载更早的行程";
  $("#gtr-tail").hidden = !gtrMoreA;
  $("#gtr-tail").textContent = "上拉加载更后的行程";
  gtrMarquee();
}

/* 默认窗口: 组内全部 (进页/重试/换车都走这), 复位两端候选旗标 */
async function gtrLoad() {
  if (gtrBusy || !gtrGid) return;
  gtrBusy = true;
  gtrStream = []; gtrGroup = null;
  $("#gtr-errbox").hidden = true;
  $("#gtr-spin").hidden = false;
  try {
    const d = await getJSON(`/tesla/trips/api/groups/${gtrGid}/trips`);
    gtrGroup = d.group;
    gtrStream = d.items;
    gtrMoreB = d.has_more_before;
    gtrMoreA = d.has_more_after;
    gtrRender();
  } catch {
    $("#gtr-errbox").hidden = false;
  }
  $("#gtr-spin").hidden = true;
  gtrBusy = false;
}

/* 顶部下拉: 加载更前的组外候选, 头前插入后按增量回补 scrollTop ——
   视口钉在原首行不跳 (prepend 掉高度差就会闪滚) */
async function gtrLoadBefore() {
  if (gtrBusy || !gtrMoreB || !gtrStream.length) return;
  gtrBusy = true;
  const sc = $("#gtr-scroll");
  const h0 = sc.scrollHeight;
  try {
    const d = await getJSON(
      `/tesla/trips/api/groups/${gtrGid}/trips?before=${gtrStream[0].id}&limit=${GTR_PAGE}`);
    gtrStream = d.items.concat(gtrStream);   // 服务端给 id 升序, 直接头前接
    gtrMoreB = d.has_more_before;
    gtrRender();
    sc.scrollTop += sc.scrollHeight - h0;
  } catch {
    toast("加载失败");
  }
  gtrBusy = false;
}

/* 尾部触底: 加载更后的组外候选; 首屏没填满 (哨兵还在预载区里 IO 不再
   触发) 链式续载直到哨兵滚出预载区 (充电/行程列表同款) */
async function gtrLoadAfter() {
  if (gtrBusy || !gtrMoreA || !gtrStream.length) return;
  gtrBusy = true;
  let ok = false;
  try {
    const d = await getJSON(
      `/tesla/trips/api/groups/${gtrGid}/trips?after=${gtrStream[gtrStream.length - 1].id}&limit=${GTR_PAGE}`);
    gtrStream = gtrStream.concat(d.items);
    gtrMoreA = d.has_more_after;
    gtrRender();
    ok = true;
  } catch {
    toast("加载失败");
  }
  gtrBusy = false;
  if (ok && gtrMoreA &&
      $("#gtr-tail").getBoundingClientRect().top < innerHeight + PRELOAD_PX)
    gtrLoadAfter();
}

/* 哨兵常驻: 视图藏起 (display:none) 不相交, 不会偷跑 */
new IntersectionObserver(es => {
  if (es[0].isIntersecting) gtrLoadAfter();
}, { rootMargin: PRELOAD_PX + "px" }).observe($("#gtr-tail"));

/* 就地翻状态: 只重画与目标态不符的行 (组内外类 / 按钮有无), 其余已加载
   行原样保留 —— 分页拉的页不丢, 不整页重拉 */
function gtrRefreshRows() {
  const [lo, hi] = gtrEnds();
  for (const el of [...$("#gtr-list").children]) {
    const it = gtrStream.find(x => x.id === +el.dataset.id);
    if (!it) continue;
    const wantBtn = !it.in_group ? "add" : (it.id === lo || it.id === hi) ? "rm" : "";
    if (el.classList.contains("in") !== it.in_group ||
        wantBtn === "add" !== !!el.querySelector(".gtr-add") ||
        wantBtn === "rm" !== !!el.querySelector(".gtr-rm"))
      el.replaceWith(gtrRow(it));
  }
  gtrMarquee();
}

/* 加入/移出: 点钮即写库 (按钮拦截在先, 行本身不可点); 返回的 changed 在
   已加载行上翻状态 (加 = 新吸收的全部段, 吸收的未加载段下次拉动自会带
   对状态来), 页头段数跟新; 失败原样 toast 服务端的口径话 */
$("#gtr-list").addEventListener("click", async e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;
  const row = t.closest(".gtr-row");
  if (!row) return;
  const it = gtrStream.find(x => x.id === +row.dataset.id);
  if (!it) return;
  const add = t.closest(".gtr-add");
  if (!add && !t.closest(".gtr-rm")) return;
  try {
    const upd = await postJSON(
      `/tesla/trips/api/groups/${gtrGid}/${add ? "add" : "remove"}`, { id: it.id });
    gtrGroup = upd.group;
    const changed = new Set(upd.changed);
    for (const x of gtrStream) if (changed.has(x.id)) x.in_group = !!add;
    gtrRefreshRows();
    toast(add ? "已加入分组" : "已移出分组");
  } catch (err) { toast(err.message || "操作失败"); }
});
