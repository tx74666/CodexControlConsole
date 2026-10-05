/* Popup actions are local extension controls, never page-authored instructions. */
"use strict";
const el = id => document.getElementById(id);
let pending = false;
let statusPort = null, latestValue = null, statusUpdates = 0;
function show(value) {
  latestValue = value;
  const enabled = value?.enabled === true, ready = value?.clientReady === true;
  el("status-label").textContent = enabled ? (ready ? "已接通" : "已启用，等待本机确认") : "已停用";
  let message = value?.message || "未取得实际本机回执。";
  if (["approved_browser_contract", "approved_browser_relay"].includes(message))
    message = !enabled ? "本机已允许接通，请点击「启用转发」。" : ready ? "已取得本机就绪回执，可以处理你确认发送的新消息。" : "正在等待本机就绪回执。";
  el("status-detail").textContent = String(message);
  el("status-dot").dataset.state = enabled && ready ? "ready" : "";
  el("profile").textContent = value?.actualProfile ? String(value.actualProfile) : "尚未核验";
  el("attempt").textContent = value?.attemptId ? String(value.attemptId) : "无";
  el("enable").disabled = pending || value?.approved !== true || value?.configured !== true || enabled;
  el("disable").disabled = pending || !enabled;
  el("approval").textContent = value?.approved === true
    ? "已取得本机明确授权；真实 Chat 往返与档位以每条请求的实际回执为准。"
    : "准备包没有获得生产启用批准，也没有完成真实 Chat 往返验收。";
}
function watchStatus() {
  if (statusPort) return;
  try {
    const port = chrome.runtime.connect({ name: "relay.status" });
    statusPort = port;
    port.onMessage.addListener(message => {
      if (statusPort !== port || message?.type !== "relay.status") return;
      statusUpdates++; show(message.value);
    });
    port.onDisconnect.addListener(() => {
      if (statusPort !== port) return;
      void chrome.runtime.lastError;
      statusPort = null; statusUpdates++;
      show({ ...latestValue, connected: false, clientReady: false, approved: false, configured: false,
        message: "扩展状态连接中断；点击「查看连接」重新核对。" });
    });
  } catch {
    statusPort = null;
  }
}
async function act(action) {
  if (pending) return;
  pending = true;
  watchStatus();
  const beforeUpdates = statusUpdates;
  for (const id of ["refresh", "enable", "disable"]) el(id).disabled = true;
  el("error").hidden = true;
  let result;
  try { result = await chrome.runtime.sendMessage({ type: "relay.popup", action }); }
  catch (error) { el("error").textContent = "未取得扩展状态：" + String(error?.message || error); el("error").hidden = false; }
  finally {
    pending = false;
    if (statusUpdates !== beforeUpdates && latestValue) show(latestValue);
    else if (result) show(result);
    else if (latestValue) show(latestValue);
    el("refresh").disabled = false;
  }
}
for (const [id, action] of [["refresh", "status"], ["enable", "enable"], ["disable", "disable"]]) {
  el(id).addEventListener("click", () => act(action));
}
const version = chrome.runtime.getManifest().version;
if (el("extension-version")) el("extension-version").textContent = "扩展版本 " + version;
act("status");
