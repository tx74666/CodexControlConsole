"use strict";
(() => {
  const byId = id => document.getElementById(id);
  let busy = false, connected = false, hasConnection = false;
  const statusLabels = {
    disconnected: "尚未连接，请在电脑完成正式授权。", signing_in: "等待 OpenAI 返回本机授权回调；模型连接尚未确认。",
    signin_expired: "本次登录链接已过期，请再次点击「连接 ChatGPT」。本机回调和模型连接尚未完成。",
    connected: "订阅已连接；手机可明确选择这条通道和真实模型。", catalog_required: "授权已保存，请点击「重新读取模型」恢复本次连接。",
    no_models: "本账号尚未返回可选模型。", catalog_failed: "模型目录暂未读取成功，请核对连接后重试读取。",
    reauth_required: "连接需要重新登录；消息与草稿保留。", login_failed: "登录尚未完成，请核对账号与官方授权页面。",
    store_unavailable: "本机连接文件暂不可读取，请保留当前数据并查看电脑端状态。"
  };
  const errorLabels = {
    subscription_busy: "正在等待授权或处理已确认的请求。请继续完成现有授权，或点击「查看连接」核对状态。",
    subscription_callback_invalid: "本机未能核对授权回调，这次登录未完成。请重新连接；记录与草稿保留。",
    subscription_callback_state_invalid: "授权回调与本次登录不匹配。请从当前连接页重新开始；记录与草稿保留。",
    subscription_callback_unavailable: "无法打开本机授权回调，尚未发起官方授权。请核对本机连接后再试。",
    subscription_auth_dependency_missing: "本机签名验证组件尚未准备好，登录未完成。请先更新 Console。",
    subscription_identity_invalid: "授权回调的签名、身份或有效期未通过核对，登录未完成。请重新连接。",
    subscription_store_unavailable: "本机连接文件暂不可读取。请保留当前数据并核对电脑端状态。",
    subscription_closed: "本机订阅连接已经停止。请重新打开 Console 后查看连接。",
    subscription_remote_revocation_unconfirmed: "本机连接已停止；官方撤销尚未核实，请在官方使用设置中查看该应用。",
    authorization_url_invalid: "授权地址无法核对，已停止。请点击「查看连接」核对本机状态。"
  };
  const knownLabel = (labels, key) => typeof key === "string" && Object.prototype.hasOwnProperty.call(labels, key) ? labels[key] : "";
  const genericError = "这次连接操作尚未完成。请点击「查看连接」核对本机状态；记录与草稿保留。";
  function clearAuthorizationLink() {
    byId("authorizationLink").hidden = true; byId("authorizationLink").removeAttribute("href");
  }
  async function call(action, post = false) {
    const response = await fetch(`/api/workflow/subscription/${action}`, {
      method: post ? "POST" : "GET", credentials: "same-origin", mode: "same-origin", redirect: "error", cache: "no-store",
      ...(post ? { headers: { "Content-Type": "application/json" }, body: "{}" } : {})
    });
    const value = await response.json();
    if (!response.ok) {
      const error = new Error(genericError);
      error.responseRejected = true;
      error.failureCode = typeof value.code === "string" ? value.code : null;
      throw error;
    }
    return value;
  }
  function render(value) {
    connected = value.connected === true;
    hasConnection = Boolean(value.connectionId);
    const label = knownLabel(statusLabels, value.status) || (connected ? "订阅已连接，手机可明确选择这条通道。" : "连接状态尚未核实，请点击「查看连接」。");
    const failure = value.error ? knownLabel(errorLabels, value.error) || genericError : "";
    byId("connectionStatus").textContent = failure ? `${label} ${failure}` : label;
    byId("connectionStatus").dataset.error = String(Boolean(value.error));
    byId("modelList").replaceChildren(...(value.models || []).map(model => {
      const li = document.createElement("li"); li.textContent = `${model.displayName || model.slug} · ${model.slug}`; return li;
    }));
    if (value.status !== "signing_in") clearAuthorizationLink();
    update();
  }
  function update() {
    for (const id of ["signin", "status", "models", "disconnect"]) byId(id).disabled = busy || (["models", "disconnect"].includes(id) && !hasConnection);
  }
  async function operate(action, post = false) {
    if (busy) return;
    const previousAuthorization = action === "signin" && !byId("authorizationLink").hidden ? byId("authorizationLink").href : "";
    busy = true; update();
    if (action === "signin") clearAuthorizationLink();
    byId("operationStatus").textContent = post ? "正在处理这次明确操作…" : "正在读取本机状态…";
    byId("operationStatus").dataset.error = "false";
    try {
      const value = await call(action, post);
      if (action === "signin") {
        // The previous link is restored only for an explicit busy rejection below.
        clearAuthorizationLink();
        let url;
        try { url = new URL(value.authorizationUrl); } catch (_) { /* Handled with a fixed safe notice below. */ }
        if (!url || url.origin !== "https://auth.openai.com" || url.pathname !== "/api/accounts/authorize" || url.username || url.password || url.hash) {
          const error = new Error(genericError); error.localNotice = true; error.failureCode = "authorization_url_invalid"; throw error;
        }
        render(value);
        byId("authorizationLink").href = url.href; byId("authorizationLink").hidden = false;
        byId("operationStatus").textContent = "点击下面的官方授权链接。等待本机回调页面明确说明登录完成，再回到本页点击「查看连接」，确认模型连接。打开链接不代表接通，也不会发送聊天。";
      } else {
        render(value); byId("operationStatus").textContent = action === "disconnect" ? "连接已停止；原记录与草稿保留。" : "已读取；查看状态不会发送消息。";
      }
    } catch (error) {
      const failureCode = error?.responseRejected === true || error?.localNotice === true ? error.failureCode : null;
      if (action === "signin") {
        clearAuthorizationLink();
        if (previousAuthorization && error?.responseRejected === true && error.failureCode === "subscription_busy") {
          byId("authorizationLink").href = previousAuthorization; byId("authorizationLink").hidden = false;
        }
      }
      byId("operationStatus").textContent = knownLabel(errorLabels, failureCode) || genericError;
      byId("operationStatus").dataset.error = "true";
    } finally { busy = false; update(); }
  }
  byId("signin").addEventListener("click", () => void operate("signin", true));
  byId("status").addEventListener("click", () => void operate("status"));
  byId("models").addEventListener("click", () => void operate("models", true));
  byId("disconnect").addEventListener("click", () => void operate("disconnect", true));
  void operate("status");
})();
