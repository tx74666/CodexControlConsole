"use strict";
(() => {
  const byId = id => document.getElementById(id);
  let busy = false, connected = false, hasConnection = false;
  const statusLabels = {
    disconnected: "尚未连接，请在电脑完成正式授权。", signing_in: "等待你在 OpenAI 页面完成登录与授权。",
    connected: "订阅已连接；手机可明确选择这条通道和真实模型。", catalog_required: "授权已保存，请点击「重新读取模型」恢复本次连接。",
    no_models: "本账号尚未返回可选模型。", catalog_failed: "模型目录暂未读取成功，请核对连接后重试读取。",
    reauth_required: "连接需要重新登录；消息与草稿保留。", login_failed: "登录尚未完成，请核对账号与官方授权页面。",
    store_unavailable: "本机连接文件暂不可读取，请保留当前数据并查看电脑端状态。"
  };
  async function call(action, post = false) {
    const response = await fetch(`/api/workflow/subscription/${action}`, {
      method: post ? "POST" : "GET", credentials: "same-origin", mode: "same-origin", redirect: "error", cache: "no-store",
      ...(post ? { headers: { "Content-Type": "application/json" }, body: "{}" } : {})
    });
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || "连接操作未完成，请保留当前页面。 ");
    return value;
  }
  function render(value) {
    connected = value.connected === true;
    hasConnection = Boolean(value.connectionId);
    byId("connectionStatus").textContent = statusLabels[value.status] || value.status || (connected ? "订阅已连接，手机可明确选择这条通道。" : "尚未连接，请在电脑完成正式授权。");
    if (value.error === "subscription_remote_revocation_unconfirmed") byId("connectionStatus").textContent = "本机连接已停止；官方撤销尚未核实，请在官方使用设置中查看该应用。";
    byId("connectionStatus").dataset.error = String(Boolean(value.error));
    byId("modelList").replaceChildren(...(value.models || []).map(model => {
      const li = document.createElement("li"); li.textContent = `${model.displayName || model.slug} · ${model.slug}`; return li;
    }));
    update();
  }
  function update() {
    for (const id of ["signin", "status", "models", "disconnect"]) byId(id).disabled = busy || (["models", "disconnect"].includes(id) && !hasConnection);
  }
  async function operate(action, post = false) {
    if (busy) return;
    busy = true; update();
    if (action === "signin") { byId("authorizationLink").hidden = true; byId("authorizationLink").removeAttribute("href"); }
    byId("operationStatus").textContent = post ? "正在处理这次明确操作…" : "正在读取本机状态…";
    byId("operationStatus").dataset.error = "false";
    try {
      const value = await call(action, post);
      if (action === "signin") {
        const url = new URL(value.authorizationUrl);
        if (url.origin !== "https://auth.openai.com" || url.pathname !== "/api/accounts/authorize" || url.username || url.password || url.hash) throw new Error("授权地址无法核对，已停止。 ");
        byId("authorizationLink").href = url.href; byId("authorizationLink").hidden = false;
        byId("operationStatus").textContent = "点击下面的官方授权链接。登录完成后回到本页，点击「查看连接」。这一步不会发送聊天。";
      } else {
        render(value); byId("operationStatus").textContent = action === "disconnect" ? "连接已停止；原记录与草稿保留。" : "已读取；查看状态不会发送消息。";
        if (connected || action === "disconnect") { byId("authorizationLink").hidden = true; byId("authorizationLink").removeAttribute("href"); }
      }
    } catch (error) {
      byId("operationStatus").textContent = error.message || "连接操作未完成，请查看本机状态。";
      byId("operationStatus").dataset.error = "true";
    } finally { busy = false; update(); }
  }
  byId("signin").addEventListener("click", () => void operate("signin", true));
  byId("status").addEventListener("click", () => void operate("status"));
  byId("models").addEventListener("click", () => void operate("models", true));
  byId("disconnect").addEventListener("click", () => void operate("disconnect", true));
  void operate("status");
})();
