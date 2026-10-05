/* Popup actions are local extension controls, never page-authored instructions. */
"use strict";
const el = id => document.getElementById(id);
let pending = false;
function show(value) {
  const enabled = value?.enabled === true, ready = value?.connected === true;
  el("status-label").textContent = enabled ? (ready ? "已连接" : "已启用，尚未连接") : "已停用";
  el("status-detail").textContent = String(value?.message || "未取得实际本机回执。");
  el("status-dot").dataset.state = enabled && ready ? "ready" : "";
  el("profile").textContent = value?.actualProfile ? String(value.actualProfile) : "尚未核验";
  el("attempt").textContent = value?.attemptId ? String(value.attemptId) : "无";
  el("enable").disabled = pending || value?.approved !== true || value?.configured !== true || enabled;
  el("disable").disabled = pending || !enabled;
  el("approval").textContent = value?.approved === true
    ? "已取得本机明确授权；真实 Chat 往返与档位以每条请求的实际回执为准。"
    : "准备包没有获得生产启用批准，也没有完成真实 Chat 往返验收。";
}
async function act(action) {
  if (pending) return;
  pending = true;
  for (const id of ["refresh", "enable", "disable"]) el(id).disabled = true;
  el("error").hidden = true;
  let result;
  try { result = await chrome.runtime.sendMessage({ type: "relay.popup", action }); }
  catch (error) { el("error").textContent = "未取得扩展状态：" + String(error?.message || error); el("error").hidden = false; }
  finally { pending = false; if (result) show(result); el("refresh").disabled = false; }
}
for (const [id, action] of [["refresh", "status"], ["enable", "enable"], ["disable", "disable"]]) {
  el(id).addEventListener("click", () => act(action));
}
act("status");
