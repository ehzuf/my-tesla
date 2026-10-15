// view/settings-tasks.js — 后台任务页 (2026-10-15 用户点名「设置菜单里加
// 一个任务页面…每一项任务都展示一个进度条…重启某个任务就会重新刷新数据
// 库」): 长回填任务 (足迹道路拟合 / 常去地点命名) 各一张卡。任务名单与
// 文案单一来源在服务端任务注册表 (routers/tasks.py), 这边只负责铺卡与
// 轮询: 进度条 = done/total (与 worker 待办同口径, 读库即真), 重启 =
// 清该任务全部成果行从头回填 (烧高德配额, confirm 按服务端 restart_hint
// 把关)。页面在视野内 5s 一轮询, 离开即停 (registerView 的 hide 收表)。
/* global $, getJSON, sendJSON, toast, bindGestures, registerView */
"use strict";

let taskRows = [];    // 最近一次面板数据 (重启 confirm 文案 / 铺卡复用)
let taskTimer = 0;    // 轮询句柄 (视图藏起即清)
let taskBusy = false; // 重启飞行锁 (防连点双清)

function taskPct(t) {
  return t.total ? Math.min(100, Math.round(t.done * 100 / t.total)) : 100;
}

function taskCard(t) {
  // 卡片按 id 只建一次, 之后轮询原位更新 (进度条的 width 过渡才有的看)
  let card = $(`#task-${t.id}`);
  if (!card) {
    card = document.createElement("section");
    card.className = "card";
    card.id = `task-${t.id}`;
    card.innerHTML = "<h2></h2><p class='task-desc'></p>" +
      "<div class='task-bar'><div class='task-fill'></div></div>" +
      "<div class='task-meta'><span class='task-state'></span>" +
      "<span class='task-count'></span>" +
      `<button type='button' class='task-restart' data-task='${t.id}'>重启</button></div>`;
    $("#task-list").appendChild(card);
  }
  return card;
}

function renderTask(t) {
  const card = taskCard(t);
  card.querySelector("h2").textContent = t.name;
  card.querySelector(".task-desc").textContent = t.desc;
  card.querySelector(".task-fill").style.width = `${taskPct(t)}%`;
  const state = card.querySelector(".task-state");
  state.textContent = t.state_label;
  state.dataset.state = t.state;
  card.querySelector(".task-count").textContent = `${t.done} / ${t.total}`;
}

function renderTasks(tasks) {
  taskRows = tasks;
  tasks.forEach(renderTask);
}

async function loadTasks() {
  try {
    renderTasks(await getJSON("/tesla/api/tasks"));
  } catch (err) {
    toast(`任务状态加载失败: ${err.message}`);
  }
}

// 重启 (冒泡层): confirm 文案用服务端 restart_hint (带真实总量); 飞行中
// 全部重启钮锁住, 回包 (新面板状态) 原位重铺
$("#task-list").addEventListener("click", async e => {
  const btn = e.target instanceof Element ? e.target.closest(".task-restart") : null;
  if (!btn || taskBusy) return;
  const t = taskRows.find(x => x.id === btn.dataset.task);
  if (!t) return;
  if (!confirm(`${t.restart_hint}。确定执行?`)) return;
  taskBusy = true;
  document.querySelectorAll("#task-list .task-restart")
    .forEach(b => { b.disabled = true; });
  try {
    renderTasks(await sendJSON(`/tesla/api/tasks/${t.id}/restart`,
                               { method: "POST" }));
    toast("已重启, 从头回填");
  } catch (err) {
    toast(`重启失败: ${err.message}`);
  } finally {
    taskBusy = false;
    document.querySelectorAll("#task-list .task-restart")
      .forEach(b => { b.disabled = false; });
  }
});

function startTaskPolling() {
  stopTaskPolling();
  taskTimer = setInterval(loadTasks, 5000);
}

function stopTaskPolling() {
  if (taskTimer) { clearInterval(taskTimer); taskTimer = 0; }
}

bindGestures($("#task-scroll"), { drawer: true, ptr: true, onRefresh: loadTasks });
registerView("settings-tasks", {
  title: "后台任务",
  el: $("#view-settings-tasks"),
  show: () => { loadTasks(); startTaskPolling(); },
  hide: stopTaskPolling,   // 离开页面停轮询 (回来 show 再起)
  refresh: loadTasks,
});
