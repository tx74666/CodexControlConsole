(() => {
  "use strict";
  const launchUrl = new URL(window.location.href), launchFragment = new URLSearchParams(launchUrl.hash.slice(1));
  let launchPairing = null;
  if (launchFragment.has("qrToken") || launchFragment.has("pair")) {
    launchUrl.hash = "";
    history.replaceState?.(history.state, "", launchUrl.href);
    const fields = [...launchFragment];
    if (fields.length === 1 && fields[0][0] === "qrToken" && /^[A-Za-z0-9_-]{32,128}$/.test(fields[0][1])) launchPairing = { qrToken: fields[0][1] };
    else if (fields.length === 1 && fields[0][0] === "pair" && /^\d{6}$/.test(fields[0][1])) launchPairing = { code: fields[0][1] };
    else launchPairing = { invalid: true };
  }

  const el = id => document.getElementById(id);
  const MUSIC_TIERS = [{ value: "first", number: "1", suffix: "st" }, { value: "second", number: "2", suffix: "nd" }, { value: "third", number: "3", suffix: "rd" }];
  const state = { paired: false, generation: 0, busy: false, tab: "work", inbox: "inbox", dashboard: null, reader: null, readerSequence: 0, mutationBusy: false, font: 18, headings: new Map(), music: { tracks: [], selected: null, loaded: false, loading: false, sequence: 0, playSequence: 0, lyricsSequence: 0, tier: "", visible: 60, repeat: "all", lyrics: [], synced: false, activeLine: -1 } };
  const UI_SCRIPTS = ["mobile.js", "workflow-panel.js", "incubator-panel.js", "conversations-panel.js"];
  const UPDATE_KEY = "codexPhone.connectedUiUpdate.v1";
  const uiUpdate = { loaded: loadedUiVersion(), actual: "", checking: false, preparing: false, reloading: false, timer: 0, trusted: false, reason: "" };
  const versionNotice = document.createElement("p"); versionNotice.className = "notice"; versionNotice.hidden = true; versionNotice.setAttribute("role", "status"); el("main").prepend(versionNotice);
  const livePlan = { snapshot: null, timer: null, busy: false, controller: null };
  const transferPanel = window.CodexTransferPanel?.create(el("phoneTransferPanel"), {
    phone: true,
    onConnectionState: connected => updateConnectionState(connected),
    onAuth: () => showPair("配对已过期或已断开，请输入电脑显示的新配对码。")
  }) || null;
  let incubatorPanel = null;
  const workflowPanel = window.CodexWorkflowPanel?.create(el("phoneWorkflowPanel"), {
    phone: true,
    onConnectionState: connected => updateConnectionState(connected),
    onAuth: () => showPair("配对已过期或已断开，请输入电脑显示的新配对码。"),
    onTaskChange: () => void incubatorPanel?.refresh?.()
  }) || null;
  incubatorPanel = window.CodexIncubatorPanel?.create(el("phoneIncubatorPanel"), {
    phone: true,
    onConnectionState: connected => updateConnectionState(connected),
    onAuth: () => showPair("配对已过期，请重新连接电脑。"),
    onTaskOpen: task => workflowPanel?.openTask?.(task) || false,
    getTaskContext: () => workflowPanel?.getTaskContext?.() || null,
    onTaskMount: host => host.append(el("phoneWorkflowPanel")),
    onTaskLeave: () => { if (workflowPanel?.clearTask?.() === false) return false; const host = el("phoneWorkflowDetails"), panel = el("phoneWorkflowPanel"); if (host && panel) host.append(panel); return true; },
    onTaskStateChange: syncWorkPanelActivity
  }) || null;
  const initialWorkView = new URL(window.location.href).searchParams.get("workView");
  let workView = ["ideas", "conversations", "workflow"].includes(initialWorkView) ? initialWorkView : "ideas";
  const conversationsPanel = window.CodexConversationsPanel?.create(el("phoneConversationsPanel"), {
    phone: true, onConnectionState: connected => updateConnectionState(connected),
    onAuth: () => showPair("配对已过期，请重新连接电脑。"),
    onTarget: async thread => { selectWorkView("ideas"); await incubatorPanel?.useTarget(thread); }
  }) || null;
  function selectWorkView(value) {
    const next = ["ideas", "conversations", "workflow"].includes(value) ? value : "ideas";
    if (next === "workflow" && incubatorPanel?.closeTask?.() === false) return false;
    workView = next;
    document.body.dataset.workView = workView;
    if (el("phoneWorkIdeas")) el("phoneWorkIdeas").hidden = workView !== "ideas";
    if (el("phoneConversationsPanel")) el("phoneConversationsPanel").hidden = workView !== "conversations";
    const workflow = el("phoneWorkflowDetails"); if (workflow) { workflow.hidden = workView !== "workflow"; if (workView === "workflow") workflow.open = true; }
    if (el("phoneWorkNotice")) el("phoneWorkNotice").textContent = ({ ideas: "Console 工作区 · 每条任务的底稿、Chat、Work 和 Output 都在这里。保存不等于执行；点确认发布或确认 Work 才会交给电脑。", conversations: "查看电脑抓取的真实对话快取；更新和更多历史只读取内容，不发送消息。", workflow: "看图、评价和派工由电脑 Console 处理；已接收任务可在手机离开后继续。" })[workView];
    for (const button of document.querySelectorAll("#workPanel [data-work-view]")) button.setAttribute("aria-pressed", String(button.dataset.workView === workView));
    syncWorkPanelActivity();
    return true;
  }
  function syncWorkPanelActivity() {
    const active = state.tab === "work" && state.paired && !document.hidden;
    incubatorPanel?.setActive(active && workView === "ideas");
    conversationsPanel?.setActive(active && workView === "conversations");
    workflowPanel?.setActive(active && (workView === "ideas" && Boolean(incubatorPanel?.hasOpenTask?.()) || workView === "workflow" && Boolean(el("phoneWorkflowDetails")?.open)));
  }
  for (const button of document.querySelectorAll("#workPanel [data-work-view]")) button.addEventListener("click", () => selectWorkView(button.dataset.workView));
  el("phoneWorkflowDetails")?.addEventListener("toggle", syncWorkPanelActivity);
  const initialTab = new URL(window.location.href).searchParams.get("tab") || new URL(window.location.href).searchParams.get("view");
  if (["work", "transfer"].includes(initialTab)) state.tab = initialTab;
  selectWorkView(workView);
  const node = (tag, text = "", className = "") => {
    const result = document.createElement(tag);
    if (text) result.textContent = String(text);
    if (className) result.className = className;
    return result;
  };
  function notice(id, message = "", error = false) { el(id).textContent = message; el(id).dataset.error = String(error); }
  function renderVersion(version) {
    if (typeof version !== "string" || !/^\d+\.\d+\.\d+$/.test(version)) { uiUpdate.actual = ""; el("versionLabel").textContent = "电脑版 · 版本暂不可读"; return; }
    uiUpdate.actual = version;
    el("versionLabel").textContent = version === uiUpdate.loaded ? `v${version} · 已更新` : `电脑版 v${version} · 界面 ${uiUpdate.loaded ? `v${uiUpdate.loaded}` : "版本未核验"}`;
    el("versionLabel").setAttribute("aria-label", version === uiUpdate.loaded ? `电脑版与当前界面均为 v${version}` : el("versionLabel").textContent);
    if (version === uiUpdate.loaded) {
      versionNotice.hidden = true; uiUpdate.reason = "";
      try { sessionStorage.removeItem(UPDATE_KEY); } catch { /* No reload is needed. */ }
    } else versionWarning("正在核对新版界面；草稿和附件会保留。");
  }
  function scriptVersion(value) { try { const url = new URL(value, window.location.href); return url.origin === new URL(window.location.href).origin ? url.searchParams.get("v")?.match(/(?:^|[^0-9.])(\d+\.\d+\.\d+)(?=$|[^0-9.])/)?.[1] || "" : ""; } catch { return ""; } }
  function loadedUiVersion() {
    const scripts = Array.from(document.querySelectorAll("script[src]")), versions = UI_SCRIPTS.map(name => {
      const matches = scripts.filter(item => { try { return new URL(item.src, window.location.href).pathname === "/" + name; } catch { return false; } });
      return matches.length === 1 ? scriptVersion(matches[0].src) : "";
    });
    return versions.every(value => value && value === versions[0]) ? versions[0] : "";
  }
  function versionWarning(reason) { uiUpdate.reason = reason; versionNotice.hidden = false; versionNotice.textContent = `电脑已是 v${uiUpdate.actual}，${uiUpdate.loaded ? `当前界面为 v${uiUpdate.loaded}` : "当前界面版本未核验"}。${reason}`; }
  function newerUiVersion(actual, loaded) {
    const left = actual.split(".").map(Number), right = loaded.split(".").map(Number);
    if (left.length !== 3 || right.length !== 3 || ![...left, ...right].every(Number.isSafeInteger)) return false;
    for (let index = 0; index < 3; index++) if (left[index] !== right[index]) return left[index] > right[index];
    return false;
  }
  function reloadIsIdle() {
    const editing = document.activeElement, media = Array.from(document.querySelectorAll("audio,video"));
    return state.paired && !document.hidden && !state.busy && !state.mutationBusy && !state.reader && !state.music.loading && el("musicAudio").paused &&
      !media.some(item => item.paused === false) && !document.querySelectorAll("iframe").length &&
      !Array.from(document.querySelectorAll(".workflow-lightbox")).some(item => !item.hidden) &&
      !(editing && (editing.isContentEditable || ["TEXTAREA", "INPUT"].includes(editing.tagName))) &&
      (!transferPanel || typeof transferPanel.hasDraft === "function" && !transferPanel.hasDraft()) &&
      (!incubatorPanel || typeof incubatorPanel.canReload === "function" && incubatorPanel.canReload() && !incubatorPanel.hasDraft?.()) &&
      (!conversationsPanel || typeof conversationsPanel.canReload === "function" && conversationsPanel.canReload());
  }
  function scheduleVersionCheck() {
    window.clearTimeout(uiUpdate.timer); uiUpdate.timer = 0;
    if (!document.hidden && !uiUpdate.reloading && (state.paired || uiUpdate.trusted)) uiUpdate.timer = window.setTimeout(() => void checkConnectedVersion(), 15000);
  }
  async function verifiedNewShell(version) {
    if (navigator.serviceWorker?.controller) throw new Error("旧页面缓存仍在接管此工作区，暂缓重开；不会删除其他 App 缓存。");
    const address = new URL("/mobile.html", window.location.href); address.searchParams.set("consoleUiRefresh", version);
    const controller = new AbortController(), timeout = window.setTimeout(() => controller.abort(), 10000);
    let text;
    try {
      const response = await fetch(address.href, { method: "GET", credentials: "same-origin", mode: "same-origin", cache: "no-store", redirect: "error", signal: controller.signal });
      if (!response.ok) throw new Error("新版页面暂时不能读取，恢复连接后会继续检查。");
      text = await response.text();
    } finally { window.clearTimeout(timeout); }
    if (text.length > 1024 * 1024) throw new Error("新版页面尚未核验，暂缓重开。");
    const parsed = new DOMParser().parseFromString(text, "text/html"), scripts = Array.from(parsed.querySelectorAll("script[src]"));
    for (const name of UI_SCRIPTS) {
      const matches = scripts.filter(item => { try { const url = new URL(item.getAttribute("src"), address); return url.origin === address.origin && url.pathname === "/" + name; } catch { return false; } });
      if (matches.length !== 1 || scriptVersion(new URL(matches[0].getAttribute("src"), address).href) !== version) throw new Error("新版页面与工作组件尚未一致，等待发布完成后再自动更新。");
    }
    return address;
  }
  async function maybeReloadConnectedUi() {
    const target = uiUpdate.actual;
    if (!target || target === uiUpdate.loaded || uiUpdate.reloading || uiUpdate.preparing) return;
    if (!uiUpdate.loaded) { versionWarning("加载时的组件版本无法核验，暂缓自动重开以保护草稿。"); return; }
    if (!newerUiVersion(target, uiUpdate.loaded)) { versionWarning("电脑版本较旧或尚未核验，等待电脑更新；不会自动退回旧界面。"); return; }
    if (!reloadIsIdle()) { versionWarning("等待编辑、录音、上传、操作或音乐播放结束后自动更新。"); return; }
    uiUpdate.preparing = true;
    try {
      const attempt = JSON.parse(sessionStorage.getItem(UPDATE_KEY) || "null");
      if (attempt?.target === target) throw new Error("已经重开过一次，但组件仍未更新；继续核对，避免反复闪动。");
      const address = await verifiedNewShell(target);
      if (uiUpdate.reloading || target !== uiUpdate.actual || !reloadIsIdle()) return;
      if (JSON.parse(sessionStorage.getItem(UPDATE_KEY) || "null")?.target === target) throw new Error("新版已进入重开流程，暂不重复重开。");
      if (!workflowPanel || typeof workflowPanel.prepareReload !== "function" || !await workflowPanel.prepareReload()) throw new Error("工作草稿或原附件尚未核验保存，保持当前页；保存完成后继续检查。");
      if (uiUpdate.reloading || target !== uiUpdate.actual || !reloadIsIdle() || !workflowPanel.canReload?.() || navigator.serviceWorker?.controller) return;
      if (JSON.parse(sessionStorage.getItem(UPDATE_KEY) || "null")?.target === target) throw new Error("新版已进入重开流程，暂不重复重开。");
      address.searchParams.set("tab", state.tab); address.searchParams.set("workView", workView);
      const receipt = JSON.stringify({ target, loaded: uiUpdate.loaded, tab: state.tab, workView });
      sessionStorage.setItem(UPDATE_KEY, receipt);
      if (uiUpdate.reloading || target !== uiUpdate.actual || sessionStorage.getItem(UPDATE_KEY) !== receipt || !workflowPanel.canReload() || !reloadIsIdle()) throw new Error("重开状态尚未可靠保存，保持当前页面。");
      uiUpdate.reloading = true; window.clearTimeout(uiUpdate.timer);
      window.location.replace(address.href);
    } catch (error) { versionWarning(error.message || "新版核验尚未完成，保持当前页并稍后重试。"); }
    finally { uiUpdate.preparing = false; }
  }
  async function checkConnectedVersion() {
    if (uiUpdate.checking || uiUpdate.reloading || document.hidden || state.busy || !(state.paired || uiUpdate.trusted)) { scheduleVersionCheck(); return; }
    uiUpdate.checking = true;
    try {
      if (!state.paired) await bootstrap();
      else { const status = await api("status"); if (!status.paired) showPair("配对已过期，请重新连接电脑。"); else renderVersion(status.version); }
      if (state.paired) await maybeReloadConnectedUi();
    } catch (error) { if (!error.auth && !error.cancelled) { updateConnectionState(false); if (uiUpdate.actual && uiUpdate.actual !== uiUpdate.loaded) versionWarning("暂时连接不到电脑；草稿保留，恢复后自动继续核对。"); } }
    finally { uiUpdate.checking = false; scheduleVersionCheck(); }
  }
  function updateConnectionState(connected) {
    if (!state.paired) return;
    el("connectionLabel").textContent = connected ? "已连接" : "连接中断";
    el("connectionLabel").dataset.connected = String(Boolean(connected));
  }
  function date(value) {
    if (!value) return "尚未记录";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? "时间未知" : parsed.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
  }
  function bytes(value) {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "—";
    return value >= 1024 ** 3 ? `${(value / 1024 ** 3).toFixed(1)} GiB` : `${Math.round(value / 1024 ** 2)} MiB`;
  }
  function pathValue(value, base = "", decode = false) {
    if (typeof value !== "string") return null;
    let path = value;
    if (decode) { try { path = decodeURIComponent(path); } catch { return null; } }
    if (!path || /^[\\/]/.test(path) || /[\u0000-\u001f\u007f:?]/.test(path)) return null;
    const parts = base ? base.split("/").slice(0, -1) : [];
    for (const part of path.replaceAll("\\", "/").split("/")) {
      if (!part || part === ".") continue;
      if (part === "..") { if (!parts.length) return null; parts.pop(); }
      else parts.push(part);
    }
    return parts.length ? parts.join("/") : null;
  }
  function samePath(left, right) { return Boolean(pathValue(left) && pathValue(right) && pathValue(left).toLowerCase() === pathValue(right).toLowerCase()); }
  function entries() { return Array.isArray(state.dashboard?.documents?.inbox?.entries) ? state.dashboard.documents.inbox.entries : []; }
  function entryStatus(item) { return ["inbox", "later", "archive"].includes(item?.status) ? item.status : item?.read ? "archive" : "inbox"; }

  async function api(endpoint, payload) {
    const generation = state.generation;
    const controller = new AbortController();
    if (endpoint === "plan") livePlan.controller = controller;
    const timer = window.setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(`/api/phone/${endpoint}`, {
        method: payload === undefined ? "GET" : "POST", credentials: "same-origin", mode: "same-origin", referrerPolicy: "same-origin", cache: "no-store", redirect: "error", signal: controller.signal,
        headers: { Accept: "application/json", "X-Codex-Phone": "1", ...(payload === undefined ? {} : { "Content-Type": "application/json" }) },
        ...(payload === undefined ? {} : { body: JSON.stringify(payload) })
      });
      if (generation !== state.generation) throw Object.assign(new Error("已取消旧的请求。"), { cancelled: true });
      if (response.status === 401) {
        showPair(endpoint === "pair" ? "配对码无效或已过期，请输入电脑显示的新配对码。" : "配对已过期或已被电脑断开，请重新输入配对码。");
        throw Object.assign(new Error("需要重新配对。"), { auth: true });
      }
      let result;
      try { result = await response.json(); } catch { throw new Error("电脑返回的数据暂时无法读取，请刷新重试。"); }
      if (generation !== state.generation) throw Object.assign(new Error("已取消旧的请求。"), { cancelled: true });
      if (!response.ok) throw new Error(result.error || `请求失败（${response.status}）。`);
      return result;
    } catch (error) {
      if (generation !== state.generation && !error.auth) throw Object.assign(new Error("已取消旧的请求。"), { cancelled: true });
      if (error.name === "AbortError" || error instanceof TypeError) {
        throw Object.assign(new Error(error.name === "AbortError" ? "连接超时，请检查同一 Wi-Fi 下的电脑连接。" : "连接已中断，请检查电脑与 Wi-Fi。"), { offline: true });
      }
      throw error;
    } finally { window.clearTimeout(timer); if (livePlan.controller === controller) livePlan.controller = null; }
  }

  function clearPrivate() {
    transferPanel?.clear();
    workflowPanel?.clear();
    incubatorPanel?.clear();
    conversationsPanel?.clear();
    document.body.dataset.phoneTab = "unpaired";
    window.clearTimeout(livePlan.timer); livePlan.timer = null; livePlan.busy = false; livePlan.controller?.abort(); livePlan.controller = null;
    state.generation += 1; state.paired = false; state.dashboard = null;
    clearMusic();
    closeReader(false);
    for (const id of ["taskGroups", "memoryCard", "hardwareCard", "inboxList", "guideList", "referenceList", "recordList"]) el(id).replaceChildren();
    el("appScreen").hidden = true; el("bottomNav").hidden = true;
    el("connectionLabel").dataset.connected = "false";
    el("connectionLabel").textContent = "未连接";
    el("updatedLabel").textContent = "";
    notice("appNotice");
  }
  function showPair(message = "") {
    uiUpdate.trusted = false; window.clearTimeout(uiUpdate.timer); uiUpdate.timer = 0;
    livePlan.snapshot = null; try { localStorage.removeItem("codexPhone.planSnapshot.v1"); } catch { /* Pairing remains available without storage. */ }
    el("offlineTaskGroups").replaceChildren(); el("offlinePlanNotice").textContent = ""; el("savePlanSnapshot").disabled = true;
    clearPrivate(); el("pairScreen").hidden = false; el("offlineScreen").hidden = true;
    el("pairCode").value = ""; notice("pairNotice", message, Boolean(message));
  }
  function showOffline(error) {
    if (!livePlan.snapshot) { try { livePlan.snapshot = validateLivePlan(JSON.parse(localStorage.getItem("codexPhone.planSnapshot.v1") || "null")); } catch { /* No valid saved task snapshot. */ } }
    clearPrivate(); el("pairScreen").hidden = true; el("offlineScreen").hidden = false;
    el("connectionLabel").textContent = "连接中断"; notice("offlineNotice", error.message, true);
    if (livePlan.snapshot) renderPlan({ plan: livePlan.snapshot.plan, label: `上次同步 · ${date(livePlan.snapshot.updatedAt)}。当前无法连接电脑。` }, "offlineTaskGroups", "offlinePlanNotice");
  }
  function failure(error, id = "appNotice") {
    if (error.auth || error.cancelled) return;
    if (error.offline) { showOffline(error); return; }
    notice(id, error.message || "暂时无法完成，请重试。", true);
  }
  function setBusy(value) {
    state.busy = value;
    el("refreshButton").disabled = value || state.mutationBusy;
    el("offlineRetry").disabled = value;
    el("pairSubmit").disabled = value;
    el("pairRemember").disabled = value;
    el("logoutButton").disabled = value || state.mutationBusy;
  }
  async function bootstrap() {
    if (state.busy) return;
    setBusy(true);
    try {
      const status = await api("status");
      if (status.version) renderVersion(status.version);
      if (status.paired && (!launchPairing || status.remembered)) {
        if (launchPairing) state.tab = initialTab === "transfer" ? "transfer" : "work";
        launchPairing = null;
        await refreshDashboard(); void pollLivePlan(); return;
      }
      if (launchPairing) {
        const pairing = launchPairing; launchPairing = null;
        if (pairing.invalid) { showPair("二维码无效，请重新扫描电脑 Console 的连接二维码，或使用配对码。"); return; }
        notice("pairNotice", "正在连接并记住这台手机…");
        await api("pair", { ...pairing, remember: Boolean(el("pairRemember").checked), deviceName: phoneDeviceName() });
        state.tab = initialTab === "transfer" ? "transfer" : "work";
        await refreshDashboard(); void pollLivePlan(); return;
      }
      if (!status.paired) { showPair(); return; }
      await refreshDashboard();
      void pollLivePlan();
    } catch (error) { failure(error, el("pairScreen").hidden ? "appNotice" : "pairNotice"); }
    finally { setBusy(false); scheduleVersionCheck(); }
  }
  function phoneDeviceName() { return /iPad/i.test(navigator.userAgent || "") ? "iPad" : /iPhone/i.test(navigator.userAgent || "") ? "iPhone" : "手机"; }
  async function refreshDashboard() {
    const generation = state.generation;
    const data = await api("dashboard");
    if (generation !== state.generation) return;
    if (!data || typeof data !== "object" || !data.documents || !data.device) throw new Error("电脑返回的页面数据不完整，请重试。");
    closeReader(false);
    state.dashboard = data; state.paired = true; uiUpdate.trusted = true;
    renderVersion(data.version);
    el("pairScreen").hidden = true; el("offlineScreen").hidden = true; el("appScreen").hidden = false; el("bottomNav").hidden = false;
    el("connectionLabel").textContent = "已连接"; el("connectionLabel").dataset.connected = "true";
    el("updatedLabel").textContent = `页面读取于 ${date(new Date().toISOString())}`;
    renderPlan(livePlan.snapshot ? { plan: livePlan.snapshot.plan, label: `电脑 → 手机 · 上次同步 ${date(livePlan.snapshot.updatedAt)}。修改请在电脑完成。` } : data.plan); renderDevice(data.device); renderDocuments(); selectTab(state.tab); notice("appNotice");
  }
  async function refresh() {
    if (state.busy || state.mutationBusy) return;
    setBusy(true); notice("appNotice", "正在读取电脑…");
    try { await refreshDashboard(); if (state.tab === "music") await loadMusic(true); } catch (error) { failure(error); }
    finally { setBusy(false); }
  }
  function selectTab(value) {
    if (value === "tasks") value = "work";
    if (value === "device") value = "documents";
    if (!["work", "transfer", "music", "documents"].includes(value)) return;
    state.tab = value;
    document.body.dataset.phoneTab = value;
    for (const tab of ["work", "transfer", "music", "documents"]) el(`${tab}Panel`).hidden = tab !== value;
    el("tasksPanel").hidden = value !== "work";
    el("devicePanel").hidden = value !== "documents";
    transferPanel?.setActive(value === "transfer" && state.paired);
    syncWorkPanelActivity();
    for (const button of document.querySelectorAll("[data-tab]")) button.setAttribute("aria-pressed", String(button.dataset.tab === value));
    if (value === "music" && state.paired && !state.music.loaded) void loadMusic();
  }
  function musicTime(value) {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "0:00";
    const seconds = Math.floor(value); return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  }
  function musicTrackList(payload) {
    if (!Array.isArray(payload?.tracks) || payload.tracks.length > 10000 || payload.playback !== "phone") throw new Error("曲库响应无效，请重新读取电脑曲库。");
    const tracks = [], seen = new Set();
    for (const item of payload.tracks) {
      const path = pathValue(item?.path);
      if (!path || path !== item.path || seen.has(path)) continue;
      seen.add(path);
      tracks.push({ path, name: String(item.name || path.split("/").at(-1)).slice(0, 500), type: String(item.type || "").slice(0, 12), size: item.size, tier: musicTier(item),
        folder: path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "", lyrics: Boolean(item.lyrics), lyricsLanguage: String(item.lyricsLanguage || ""),
        lyricsLanguages: (Array.isArray(item.lyricsLanguages) ? item.lyricsLanguages : []).filter(option => typeof option.code === "string" && /^[A-Za-z][A-Za-z0-9-]{0,23}$/.test(option.code)).map(option => ({ code: option.code, label: option.code === "zh" ? "中文" : String(option.label || option.code).slice(0, 40) })) });
    }
    return tracks;
  }
  function filteredMusic() {
    return MUSIC_TIERS.flatMap(tier => state.music.tracks.filter(track => musicTier(track) === tier.value && (!state.music.tier || tier.value === state.music.tier)));
  }
  function musicTier(track) { return track.tier === "first" || track.tier === "second" ? track.tier : "third"; }
  function renderMusicTierLabel(container, tier) {
    const item = MUSIC_TIERS.find(item => item.value === tier);
    container.replaceChildren();
    if (item) { container.textContent = item.number; container.append(node("sup", item.suffix)); }
    else container.textContent = "全部";
  }
  function renderMusicTierTabs() {
    for (const button of document.querySelectorAll("button[data-music-tier]")) {
      renderMusicTierLabel(button, button.dataset.musicTier); button.setAttribute("aria-pressed", String(state.music.tier === button.dataset.musicTier));
    }
  }
  function renderMusicTracks() {
    const tracks = filteredMusic(), container = el("musicTracks"); container.replaceChildren(); renderMusicTierTabs(); let previousTier = "", groupTracks;
    tracks.slice(0, state.music.visible).forEach((track, index) => {
      const tier = musicTier(track);
      if (tier !== previousTier) { const section = node("section", "", `music-tier-section music-tier-${tier}`), heading = node("h3", "", "music-group-heading"); section.dataset.musicTier = tier; renderMusicTierLabel(heading, tier); groupTracks = node("div", "", "music-group-tracks"); section.append(heading, groupTracks); container.append(section); previousTier = tier; }
      const button = node("button", "", "music-track"); button.type = "button";
      button.setAttribute("aria-pressed", String(track.path === state.music.selected?.path));
      button.append(node("span", track.path === state.music.selected?.path ? "♫" : String(index + 1), "music-track-number"));
      const label = node("span", "", "music-track-label"); label.append(node("span", track.name, "music-track-name"));
      button.append(label);
      // Audio starts within this tap's call stack; no network await precedes play().
      button.addEventListener("click", () => selectMusicTrack(track.path)); groupTracks.append(button);
    });
    if (!tracks.length) container.append(node("p", state.music.loaded ? "这个分类还没有音乐。" : "点「音乐」读取电脑曲库。", "empty-state"));
    el("musicMore").hidden = tracks.length <= state.music.visible;
  }
  async function loadMusic(force = false) {
    const music = state.music;
    if (!state.paired || music.loading || (music.loaded && !force)) return;
    const sequence = ++music.sequence; music.loading = true; el("musicRefresh").disabled = true; notice("musicNotice", "正在读取电脑曲库…");
    try {
      const data = await api("music"); if (sequence !== music.sequence || !state.paired) return;
      const tracks = musicTrackList(data); music.tracks = tracks; music.loaded = true; music.truncated = Boolean(data.truncated);
      if (music.selected) {
        const current = tracks.find(track => track.path === music.selected.path);
        if (!current) stopMusicPlayback(); else { music.selected = current; el("musicTrackTitle").textContent = current.name; }
      }
      renderMusicTracks(); updateMusicControls(); notice("musicNotice", data.error || (music.truncated ? "电脑仅返回了部分曲目。" : ""));
    } catch (error) { if (sequence === music.sequence) failure(error, "musicNotice"); }
    finally { if (sequence === music.sequence) { music.loading = false; el("musicRefresh").disabled = false; } }
  }
  function clearMusicLyrics() {
    state.music.lyricsSequence += 1; state.music.lyrics = []; state.music.synced = false; state.music.activeLine = -1;
    el("musicLyrics").replaceChildren(); el("musicLyricLanguages").replaceChildren(); el("musicLyricLanguages").hidden = true; el("musicLyricsSection").hidden = true; el("musicLyricsNotice").textContent = "";
  }
  function stopMusicPlayback() {
    state.music.playSequence += 1; state.music.selected = null;
    const audio = el("musicAudio"); audio.pause(); audio.removeAttribute("src"); audio.load(); clearMusicLyrics();
    el("musicTrackTitle").textContent = "选择一首音乐"; el("musicTrackMeta").textContent = "声音从 iPhone 播放";
    el("musicSeek").value = "0"; el("musicElapsed").textContent = "0:00"; el("musicDuration").textContent = "0:00";
    try { if (navigator.mediaSession) { navigator.mediaSession.metadata = null; navigator.mediaSession.playbackState = "none"; } } catch { /* Optional system media controls. */ }
    updateMusicControls();
  }
  function clearMusic() {
    stopMusicPlayback();
    state.music.sequence += 1; state.music.tracks = []; state.music.loaded = false; state.music.loading = false; state.music.tier = ""; state.music.visible = 60; state.music.truncated = false;
    renderMusicTierTabs(); el("musicTracks").replaceChildren(); el("musicMore").hidden = true; el("musicRefresh").disabled = false; notice("musicNotice");
  }
  function updateMusicControls() {
    const audio = el("musicAudio"), selected = state.paired && Boolean(state.music.selected);
    el("musicPlay").disabled = !selected; el("musicPrevious").disabled = !selected || state.music.tracks.length < 2; el("musicNext").disabled = !selected || state.music.tracks.length < 2;
    el("musicPlay").textContent = audio.paused ? "播放" : "暂停";
    el("musicRepeat").textContent = state.music.repeat === "one" ? "单曲循环" : state.music.repeat === "off" ? "播完停止" : "列表循环";
    el("musicRepeat").setAttribute("aria-label", `切换循环模式，当前${el("musicRepeat").textContent}`);
    updateMusicPosition();
    try { if (navigator.mediaSession) navigator.mediaSession.playbackState = selected ? audio.paused ? "paused" : "playing" : "none"; } catch { /* Optional system media controls. */ }
  }
  function playMusic() {
    if (!state.paired || !state.music.selected) return;
    const sequence = state.music.playSequence, audio = el("musicAudio");
    notice("musicNotice");
    try {
      const promise = audio.play();
      if (promise && typeof promise.catch === "function") promise.catch(error => {
        if (sequence !== state.music.playSequence || !state.paired) return;
        if (error.name === "AbortError") return;
        notice("musicNotice", error.name === "NotAllowedError" ? "Safari 需要你再点一次「播放」才能开始。" : "暂时无法播放，请重试或选择其他曲目。", true); updateMusicControls();
      });
      updateMusicControls();
    } catch { notice("musicNotice", "暂时无法播放，请重试或选择其他曲目。", true); updateMusicControls(); }
  }
  function selectMusicTrack(path) {
    if (!state.paired) return;
    const track = state.music.tracks.find(item => item.path === path); if (!track) return;
    const music = state.music, audio = el("musicAudio"); music.playSequence += 1;
    audio.pause(); clearMusicLyrics(); music.selected = track;
    el("musicTrackTitle").textContent = track.name; el("musicTrackMeta").textContent = `${track.type.toUpperCase()} · 声音从 iPhone 播放`;
    audio.src = `/api/phone/music/audio?path=${encodeURIComponent(track.path)}`; audio.load();
    try {
      if (navigator.mediaSession && typeof MediaMetadata !== "undefined") navigator.mediaSession.metadata = new MediaMetadata({ title: track.name, album: track.folder.split("/").at(-1) || "Codex Console" });
    } catch { /* Optional system media controls. */ }
    playMusic(); renderMusicTracks();
    if (track.lyrics) { el("musicLyricsSection").hidden = false; renderMusicLyricLanguages(track); void loadMusicLyrics(track.path, track.lyricsLanguage); }
  }
  function advanceMusic(direction = 1, ended = false) {
    const music = state.music; if (!state.paired || !music.selected || !music.tracks.length) return;
    if (ended && music.repeat === "one") { el("musicAudio").currentTime = 0; playMusic(); return; }
    if (ended && music.repeat === "off") { updateMusicControls(); return; }
    let queue = filteredMusic(); if (!queue.some(track => track.path === music.selected.path)) queue = music.tracks;
    const index = queue.findIndex(track => track.path === music.selected.path);
    selectMusicTrack(queue[(index + direction + queue.length) % queue.length].path);
  }
  function updateMusicPosition() {
    const audio = el("musicAudio"), duration = audio.duration, time = audio.currentTime;
    const valid = Boolean(state.music.selected) && Number.isFinite(duration) && duration > 0;
    el("musicSeek").disabled = !valid;
    el("musicSeek").value = valid ? String(Math.min(1000, Math.max(0, Math.round(time / duration * 1000)))) : "0";
    el("musicSeek").setAttribute("aria-valuetext", `${musicTime(time)} / ${musicTime(duration)}`);
    el("musicElapsed").textContent = musicTime(time); el("musicDuration").textContent = musicTime(duration);
    syncMusicLyrics(time);
  }
  function parseMusicLyrics(content, format = "lrc") {
    const value = String(content).replace(/\r\n?/g, "\n"), lines = value.split("\n");
    if (lines.length > 6000) return { synced: false, lines: [{ time: 0, text: value }], notice: "歌词较长，按纯文本显示。" };
    const timed = [], plain = []; let offset = 0;
    for (const raw of lines) {
      const line = raw.trim(); if (!line) continue;
      const offsetTag = /^\[offset:([+-]?\d+)\]$/i.exec(line); if (offsetTag) { offset = Number(offsetTag[1]) / 1000; continue; }
      if (format === "lrc" && /^\[(?:ar|al|ti|by|length|re|ve|lang|language):/i.test(line)) continue;
      const tags = format === "lrc" ? [...line.matchAll(/\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]/g)] : [];
      const text = tags.length ? line.replace(/\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\]/g, "").trim() : line;
      if (tags.length) for (const tag of tags) { const seconds = Number(tag[2]); if (seconds < 60) timed.push({ time: Number(tag[1]) * 60 + seconds + Number((tag[3] || "0").padEnd(3, "0")) / 1000, text }); }
      else plain.push({ time: 0, text });
    }
    if (timed.length) return { synced: true, lines: timed.map(line => ({ ...line, time: Math.max(0, line.time + offset) })).sort((left, right) => left.time - right.time), notice: "点歌词可跳到对应位置。" };
    return { synced: false, lines: plain, notice: plain.length ? "本地文本歌词，未提供时间轴。" : "这份歌词没有可显示的正文。" };
  }
  function renderMusicLyricLanguages(track, language = track.lyricsLanguage) {
    const container = el("musicLyricLanguages"); container.replaceChildren(); container.hidden = track.lyricsLanguages.length < 2;
    for (const option of track.lyricsLanguages) {
      const button = node("button", option.label); button.type = "button"; button.setAttribute("aria-pressed", String(option.code === language));
      button.addEventListener("click", () => { renderMusicLyricLanguages(track, option.code); void loadMusicLyrics(track.path, option.code); }); container.append(button);
    }
  }
  async function loadMusicLyrics(path, language = "") {
    const sequence = ++state.music.lyricsSequence; state.music.lyrics = []; state.music.synced = false; state.music.activeLine = -1; el("musicLyrics").replaceChildren(); el("musicLyricsNotice").textContent = "正在读取本地歌词…";
    try {
      const data = await api(`music/lyrics?path=${encodeURIComponent(path)}${language ? `&language=${encodeURIComponent(language)}` : ""}`);
      if (sequence !== state.music.lyricsSequence || state.music.selected?.path !== path || !state.paired) return;
      if (!samePath(data.path, path) || typeof data.content !== "string" || data.content.length > 262144) throw new Error("歌词响应无效，请重试。");
      const parsed = parseMusicLyrics(data.content, data.format); state.music.lyrics = parsed.lines; state.music.synced = parsed.synced; el("musicLyricsNotice").textContent = parsed.notice;
      parsed.lines.forEach(line => {
        const paragraph = node("p", line.text || "♪"); paragraph.dataset.timed = String(parsed.synced);
        if (parsed.synced) { paragraph.tabIndex = 0; paragraph.setAttribute("role", "button"); paragraph.setAttribute("aria-label", `${musicTime(line.time)} ${line.text || "间奏"}`); const seek = () => { if (state.paired && state.music.selected?.path === path && Number.isFinite(el("musicAudio").duration)) { el("musicAudio").currentTime = Math.min(el("musicAudio").duration, line.time); updateMusicPosition(); } }; paragraph.addEventListener("click", seek); paragraph.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); seek(); } }); }
        el("musicLyrics").append(paragraph);
      });
      renderMusicLyricLanguages(state.music.selected, data.language || language); syncMusicLyrics(el("musicAudio").currentTime);
    } catch (error) { if (sequence === state.music.lyricsSequence) failure(error, "musicLyricsNotice"); }
  }
  function syncMusicLyrics(time) {
    if (!state.music.synced || !Number.isFinite(time)) return;
    let index = -1; for (let offset = 0; offset < state.music.lyrics.length; offset += 1) { if (state.music.lyrics[offset].time > time) break; index = offset; }
    if (index === state.music.activeLine) return; state.music.activeLine = index;
    const activeTime = index >= 0 ? state.music.lyrics[index].time : -1, container = el("musicLyrics");
    for (let offset = 0; offset < container.children.length; offset += 1) container.children[offset].dataset.active = String(index >= 0 && Math.abs(state.music.lyrics[offset].time - activeTime) < 0.002);
    const active = container.children[index]; if (active && el("musicLyricsSection").open) container.scrollTop = Math.max(0, active.offsetTop - container.offsetTop - container.clientHeight / 2 + active.clientHeight / 2);
  }
  async function musicAudioError() {
    if (!state.paired || !state.music.selected || !el("musicAudio").error || el("musicAudio").error.code === 1) return;
    const sequence = state.music.playSequence; el("musicAudio").pause(); updateMusicControls(); notice("musicNotice", "音乐暂时无法播放，请检查连接，或换一首 Safari 支持的音乐。", true);
    try { const result = await api("status"); if (sequence !== state.music.playSequence) return; if (!result.paired) showPair("配对已过期，请重新连接电脑再播放。"); }
    catch (error) { if (sequence === state.music.playSequence) failure(error, "musicNotice"); }
  }
  function bindMusicMediaSession() {
    if (!navigator.mediaSession) return;
    const handlers = { play: () => playMusic(), pause: () => { el("musicAudio").pause(); updateMusicControls(); }, previoustrack: () => advanceMusic(-1), nexttrack: () => advanceMusic(1), seekto: details => { if (state.music.selected && Number.isFinite(details.seekTime)) { el("musicAudio").currentTime = Math.max(0, Math.min(el("musicAudio").duration || 0, details.seekTime)); updateMusicPosition(); } } };
    for (const [action, handler] of Object.entries(handlers)) { try { navigator.mediaSession.setActionHandler(action, handler); } catch { /* Safari support differs by version and context. */ } }
  }
  function validateLivePlan(value) {
    const text = (value, limit) => typeof value === "string" && value.length <= limit;
    const id = value => text(value, 160) && /^[A-Za-z0-9][A-Za-z0-9._:-]*$/.test(value);
    if (!value || value.format !== "codex-console-plan-snapshot" || value.schemaVersion !== 1 || !/^[a-f0-9]{64}$/.test(value.hash || "") || !id(value.computerId) || !text(value.updatedAt, 60) || Number.isNaN(Date.parse(value.updatedAt))) throw new Error("电脑任务快照无效。");
    const plan = value.plan, groupIds = new Set(), taskIds = new Set(); let count = 0;
    if (!plan || plan.version !== 1 || !id(plan.revision) || !Array.isArray(plan.groups) || plan.groups.length < 1 || plan.groups.length > 12) throw new Error("电脑计划分组无效。");
    for (const group of plan.groups) { if (!group || !id(group.id) || groupIds.has(group.id) || !text(group.title, 120) || !group.title.trim() || !text(group.summary || "", 240) || !Array.isArray(group.items) || group.items.length > 100) throw new Error("电脑计划分组无效。"); groupIds.add(group.id); count += group.items.length; if (count > 300) throw new Error("电脑计划清单过长。"); for (const item of group.items) { if (!item || !id(item.id) || taskIds.has(item.id) || !text(item.text, 500) || !item.text.trim() || typeof item.done !== "boolean") throw new Error("电脑计划项无效。"); taskIds.add(item.id); } }
    return { format: value.format, schemaVersion: 1, hash: value.hash, updatedAt: value.updatedAt, computerId: value.computerId, plan: structuredClone(plan) };
  }
  async function pollLivePlan() {
    if (!state.paired || document.hidden || livePlan.busy) return;
    const generation = state.generation; livePlan.busy = true;
    try {
      const value = await api("plan"); if (generation !== state.generation) return;
      updateConnectionState(true);
      const snapshot = validateLivePlan(value);
      if (!livePlan.snapshot || snapshot.hash !== livePlan.snapshot.hash || snapshot.computerId !== livePlan.snapshot.computerId) { livePlan.snapshot = snapshot; try { localStorage.setItem("codexPhone.planSnapshot.v1", JSON.stringify(snapshot)); } catch { /* The current plan remains readable in memory. */ } renderPlan({ plan: snapshot.plan, label: `电脑 → 手机 · 已同步 ${date(snapshot.updatedAt)}。修改请在电脑完成。` }); }
      el("planNotice").textContent = `电脑 → 手机 · 已同步 ${date(snapshot.updatedAt)}。修改请在电脑完成。`;
      el("savePlanSnapshot").disabled = false; notice("appNotice");
    } catch (error) {
      if (generation !== state.generation || error.auth || error.cancelled) return;
      if (error.offline) updateConnectionState(false);
      el("planNotice").textContent = livePlan.snapshot
        ? `上次同步 · ${date(livePlan.snapshot.updatedAt)}。${error.offline ? "暂时连不上电脑" : "电脑任务暂时无法更新"}，计划已保留。`
        : error.offline ? "电脑任务暂时不可读取，正在等待重连。" : "电脑任务暂时不可读取，请在电脑检查计划；其他功能仍可使用。";
    }
    finally { if (generation === state.generation) { livePlan.busy = false; window.clearTimeout(livePlan.timer); if (state.paired && !document.hidden) livePlan.timer = window.setTimeout(() => { livePlan.timer = null; void pollLivePlan(); }, 5000); } }
  }
  function savePlanSnapshot() {
    if (!livePlan.snapshot) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(livePlan.snapshot, null, 2)], { type: "application/json" })), anchor = node("a"); anchor.href = url; anchor.download = `Codex-Console-计划快照-${new Date().toISOString().slice(0, 10)}.json`; document.body.append(anchor); anchor.click(); anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
  function renderPlan(payload, targetId = "taskGroups", noticeId = "planNotice") {
    const plan = payload?.plan || (Array.isArray(payload?.groups) ? payload : null);
    const container = el(targetId), opened = new Map(Array.from(container.children).map(card => [card.dataset.group, card.open])); container.replaceChildren();
    const groups = Array.isArray(plan?.groups) && plan.groups.length <= 12 ? plan.groups : [];
    el(noticeId).textContent = payload?.actualDone === false ? "计划初始清单：实际进度暂未同步。请在电脑打开并保存任务。" : payload?.label || "电脑保存的计划。连接后自动更新，修改请在电脑完成。";
    if (!groups.length) { container.append(node("p", payload?.error || "电脑还没有保存四项计划，请先在电脑上整理。", "empty-state")); return; }
    groups.forEach((group, index) => {
      const card = node("details", "", "card task-card");
      card.dataset.group = group.id; card.open = Boolean(opened.get(group.id));
      const heading = node("summary"); heading.append(node("span", `0${index + 1}`, "task-number"), node("span", group.title)); card.append(heading);
      if (group.summary) card.append(node("p", group.summary, "muted"));
      const list = node("ul", "", "task-items");
      for (const item of Array.isArray(group.items) ? group.items : []) {
        const li = node("li"); const marker = node("span", item.done ? "✓" : "·", `task-status${item.done ? " done" : ""}`); marker.setAttribute("aria-label", item.done ? "计划文件中记录为已完成" : "计划项");
        li.append(marker, node("span", item.text)); list.append(li);
      }
      card.append(list); container.append(card);
    });
  }
  function renderDevice(device) {
    const memory = device?.currentMemory || {};
    const card = el("memoryCard"); card.replaceChildren(node("p", "当前记忆体", "eyebrow"));
    if (memory.status === "available" && typeof memory.usedPercent === "number" && Number.isFinite(memory.usedPercent) && memory.usedPercent >= 0 && memory.usedPercent <= 100) {
      const value = node("p", String(memory.usedPercent), "memory-value"); value.append(node("span", "% 已用")); card.append(value);
      const track = node("div", "", "memory-track"); const fill = node("div", "", "memory-fill"); fill.style.width = `${memory.usedPercent}%`; fill.dataset.high = String(memory.usedPercent >= 95); track.append(fill); card.append(track);
      const line = node("p", "", "memory-line"); line.append(node("span", `可用 ${bytes(memory.availableBytes)}`), node("span", `总计 ${bytes(memory.totalBytes)}`)); card.append(line);
      if (memory.usedPercent >= 98) card.append(node("p", "记忆体接近满载，先避免同时新增重型工作。", "small"));
    } else card.append(node("p", "当前记忆体暂时无法读取。", "muted"));
    card.append(node("p", `读取时间：${date(memory.readAt)}`, "muted small"));
    const hardware = el("hardwareCard"); hardware.replaceChildren(node("h3", "设备信息"), node("p", `保存的硬件采样 · ${date(device?.sampledAt)}`, "muted small"));
    if (!device?.sampledAt) { hardware.append(node("p", "尚无保存的硬件资料，请在电脑的 Document 中采样。", "muted small")); return; }
    const list = node("dl", "", "hardware-list");
    for (const [label, value] of [["电脑", device.model], ["处理器", device.cpuModel], ["显卡", (device.gpuModels || []).join(" / ")], ["已安装记忆体", bytes(device.installedMemoryBytes)]]) {
      if (value) list.append(node("dt", label), node("dd", value));
    }
    hardware.append(list);
  }
  function documentButton(item, meta = "", reference = null) {
    const button = node("button", "", "card document-card"); button.type = "button";
    button.append(node("span", item.title || item.name || item.path, "card-label"));
    if (item.summary) button.append(node("span", item.summary, "card-summary"));
    if (meta) button.append(node("span", meta, "card-meta"));
    button.addEventListener("click", () => void openDocument(item.path, { entryId: item.id || "", reference }));
    return button;
  }
  function renderDocuments() {
    const data = state.dashboard?.documents || {};
    renderInbox();
    const guide = el("guideList"); guide.replaceChildren();
    for (const item of Array.isArray(data.guide?.items) ? data.guide.items : []) {
      if (!pathValue(item.path)) continue;
      const wrapper = node("div"); wrapper.append(documentButton(item));
      if (Array.isArray(item.highlights) && item.highlights.length) { const list = node("ul", "", "guide-highlights"); for (const highlight of item.highlights.slice(0, 8)) list.append(node("li", highlight)); wrapper.append(list); }
      guide.append(wrapper);
    }
    if (!guide.children.length) guide.append(node("p", data.guide?.error || data.error || "电脑还没有登记阅读重点。", "empty-state"));
    const references = el("referenceList"); references.replaceChildren();
    for (const reference of Array.isArray(data.references?.items) ? data.references.items : []) {
      const variants = Array.isArray(reference.variants) ? reference.variants.filter(item => pathValue(item.path)) : [];
      const selected = variants.find(item => item.language === reference.defaultLanguage && item.available) || variants.find(item => item.available) || variants[0];
      if (!selected) continue;
      const card = node("div", "", "card"); card.append(node("h3", selected.title), node("p", selected.summary || "双语参考文档", "muted small"));
      const buttons = node("div", "", "reference-variants");
      for (const variant of variants) { const button = node("button", variant.label || variant.language); button.type = "button"; button.disabled = !variant.available; button.addEventListener("click", () => void openDocument(variant.path, { reference })); buttons.append(button); }
      card.append(buttons); references.append(card);
    }
    if (!references.children.length) references.append(node("p", data.references?.error || data.error || "暂无登记的参考资料。", "empty-state"));
    const records = el("recordList"); records.replaceChildren();
    for (const record of Array.isArray(data.records?.items) ? data.records.items : []) {
      if (pathValue(record.path)) records.append(documentButton(record, "AI 原始记录"));
    }
    if (!records.children.length) records.append(node("p", "完整 AI 原始记录保存在电脑上；请在电脑的 Document → 资料 → AI 记录中查看。手机目前开放阅读重点、参考资料和阅读清单。", "muted small"));
  }
  function renderInbox() {
    const list = entries();
    for (const [status, id] of [["inbox", "inboxCount"], ["later", "laterCount"], ["archive", "archiveCount"]]) el(id).textContent = String(list.filter(item => entryStatus(item) === status).length);
    for (const button of document.querySelectorAll("[data-inbox]")) button.setAttribute("aria-pressed", String(button.dataset.inbox === state.inbox));
    const container = el("inboxList"); container.replaceChildren();
    for (const item of list.filter(item => entryStatus(item) === state.inbox)) {
      if (pathValue(item.path)) container.append(documentButton(item, [item.source, date(item.createdAt)].filter(Boolean).join(" · ")));
    }
    if (!container.children.length) container.append(node("p", state.dashboard?.documents?.inbox?.error || state.dashboard?.documents?.error || (state.inbox === "archive" ? "还没有归档的阅读记录。" : state.inbox === "later" ? "稍后阅读的内容会放在这里。" : "没有待阅读的内容，先做重要的事。"), "empty-state"));
  }

  function closeReader(pop = false) {
    state.readerSequence += 1; state.reader = null; state.headings.clear();
    el("readerScreen").hidden = true; el("readerActions").hidden = true; el("readerContent").replaceChildren(); el("readerHeadings").replaceChildren(); el("readerLanguages").replaceChildren(); el("readerContents").hidden = true;
    el("readerTitle").textContent = ""; el("readerMeta").textContent = ""; notice("readerNotice");
    document.body.dataset.reading = "false"; el("main").inert = false; el("bottomNav").inert = false; el("appHeader").inert = false;
    if (pop && history.state?.phoneReader) history.back();
  }
  async function openDocument(value, { entryId = "", reference = null, fragment = "", push = true } = {}) {
    if (!state.paired) return;
    const path = pathValue(value);
    if (!path) { notice("appNotice", "文档路径无效，请从清单重新打开。", true); return; }
    const sequence = ++state.readerSequence;
    const old = state.reader;
    const entry = entries().find(item => samePath(item.path, path) && (!entryId || item.id === entryId)) || null;
    state.reader = { path, entryId: reference ? "" : entry?.id || "", reference, loaded: false };
    state.headings.clear();
    if (push && !old) history.pushState({ phoneReader: true }, "", window.location.href);
    el("readerScreen").hidden = false; document.body.dataset.reading = "true";
    el("main").inert = true; el("bottomNav").inert = true; el("appHeader").inert = true;
    el("readerScreen").scrollTop = 0; el("readerScreen").focus(); el("readerTitle").textContent = "正在打开…"; el("readerMeta").textContent = "";
    el("readerContent").replaceChildren(); el("readerHeadings").replaceChildren(); el("readerContents").hidden = true; notice("readerNotice", "正在读取电脑上的文档…"); updateReaderControls();
    try {
      const file = await api(`document?path=${encodeURIComponent(path)}`);
      if (sequence !== state.readerSequence) return;
      if (!samePath(file.path, path) || typeof file.content !== "string" || file.content.length > 2 * 1024 * 1024) throw new Error("返回的文档与请求不符或超过阅读限制。");
      el("readerTitle").textContent = /^#\s+(.+)$/m.exec(file.content)?.[1] || file.name || path.split("/").at(-1);
      el("readerMeta").textContent = `电脑文档 · 修改于 ${date(file.modifiedAt)}`;
      el("readerContent").lang = reference?.variants?.find(item => samePath(item.path, path))?.language || "zh-CN";
      if (file.format === "markdown" || /\.md$/i.test(path)) renderMarkdown(file.content, el("readerContent"));
      else el("readerContent").append(node("pre", file.content));
      state.reader.loaded = true; notice("readerNotice"); renderContents(); updateReaderControls();
      if (fragment) scrollFragment(fragment);
    } catch (error) {
      if (sequence !== state.readerSequence) return;
      if (!error.auth && !error.offline && !error.cancelled) el("readerTitle").textContent = "暂时无法打开文档";
      failure(error, "readerNotice");
    } finally { if (sequence === state.readerSequence) updateReaderControls(); }
  }
  function updateReaderControls() {
    const reader = state.reader;
    const entry = reader?.entryId ? entries().find(item => item.id === reader.entryId && samePath(item.path, reader.path)) : null;
    el("readerActions").hidden = !entry || !reader?.loaded;
    el("readerLater").textContent = entryStatus(entry) === "later" ? "移回待阅读" : "稍后阅读";
    el("readerRead").textContent = entryStatus(entry) === "archive" ? "移回待阅读" : "已读，归档";
    el("readerLater").disabled = state.mutationBusy || !reader?.loaded;
    el("readerRead").disabled = state.mutationBusy || !reader?.loaded;
    const languages = el("readerLanguages"); languages.replaceChildren(); languages.hidden = !reader?.reference;
    for (const variant of reader?.reference?.variants || []) {
      const button = node("button", variant.label || variant.language); button.type = "button"; button.disabled = !variant.available || state.mutationBusy;
      button.setAttribute("aria-pressed", String(samePath(variant.path, reader.path)));
      button.addEventListener("click", () => void openDocument(variant.path, { reference: reader.reference, push: false })); languages.append(button);
    }
    el("fontSmaller").disabled = state.font <= 14; el("fontLarger").disabled = state.font >= 26;
  }
  async function moveReader(kind) {
    const reader = state.reader;
    const entry = entries().find(item => item.id === reader?.entryId && samePath(item.path, reader?.path));
    if (!reader?.loaded || !entry || state.mutationBusy || state.busy) return;
    const status = kind === "read" ? entryStatus(entry) === "archive" ? "inbox" : "archive" : entryStatus(entry) === "later" ? "inbox" : "later";
    const sequence = state.readerSequence;
    state.mutationBusy = true; updateReaderControls(); setBusy(state.busy); notice("readerNotice", "正在保存阅读状态…");
    try {
      const result = await api("inbox/move", { id: entry.id, status });
      if (!Array.isArray(result.entries)) throw new Error("阅读状态响应无效，请刷新确认。");
      if (!state.dashboard) return;
      state.dashboard.documents.inbox = result; renderInbox();
      if (sequence === state.readerSequence) notice("readerNotice", status === "archive" ? "已归档，电脑上的阅读清单也已更新。" : status === "later" ? "已放到 Later，电脑上的阅读清单也已更新。" : "已移回待阅读。电脑上的阅读清单也已更新。");
    } catch (error) { failure(error, sequence === state.readerSequence ? "readerNotice" : "appNotice"); }
    finally { state.mutationBusy = false; updateReaderControls(); setBusy(state.busy); }
  }
  function slug(value) { return String(value).trim().toLowerCase().replace(/[^\p{L}\p{N}\s_-]/gu, "").replace(/\s+/g, "-") || "section"; }
  function scrollFragment(value) {
    let fragment = String(value).replace(/^#/, "");
    try { fragment = decodeURIComponent(fragment); } catch { return; }
    const heading = state.headings.get(fragment) || state.headings.get(slug(fragment));
    if (heading) heading.scrollIntoView({ block: "start" });
  }
  function renderContents() {
    const container = el("readerHeadings"); container.replaceChildren();
    for (const [key, heading] of state.headings) {
      if (!/^H[23]$/.test(heading.tagName)) continue;
      const anchor = node("a", heading.textContent); anchor.href = `#${heading.id}`; anchor.dataset.level = heading.tagName.slice(1);
      anchor.addEventListener("click", event => { event.preventDefault(); scrollFragment(key); }); container.append(anchor);
    }
    el("readerContents").hidden = !container.children.length;
  }
  function appendInline(parent, source, depth = 0) {
    const value = String(source);
    if (depth > 5) { parent.append(document.createTextNode(value)); return; }
    const tokens = /(`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|_[^_\n]+_|!?\[[^\]\n]*\]\((?:<[^>\n]+>|[^)\n]+)\))/g;
    let offset = 0;
    for (const match of value.matchAll(tokens)) {
      parent.append(document.createTextNode(value.slice(offset, match.index)));
      const token = match[0];
      if (token.startsWith("`")) parent.append(node("code", token.slice(1, -1)));
      else if (token.startsWith("**") || token.startsWith("__")) { const strong = node("strong"); appendInline(strong, token.slice(2, -2), depth + 1); parent.append(strong); }
      else if (token.startsWith("*") || token.startsWith("_")) { const em = node("em"); appendInline(em, token.slice(1, -1), depth + 1); parent.append(em); }
      else {
        const split = token.indexOf("]("); const image = token.startsWith("!"); const label = token.slice(image ? 2 : 1, split);
        let target = token.slice(split + 2, -1).trim(); target = target.startsWith("<") && target.endsWith(">") ? target.slice(1, -1) : target.replace(/\s+["'][^"']*["']$/, "");
        if (image) parent.append(document.createTextNode(`图片：${label}`)); else appendLink(parent, label, target, depth + 1);
      }
      offset = match.index + token.length;
    }
    parent.append(document.createTextNode(value.slice(offset)));
  }
  function appendLink(parent, label, target, depth = 0) {
    if (/[\u0000-\u001f\u007f]/.test(target)) { parent.append(document.createTextNode(label)); return; }
    if (/^https?:\/\//i.test(target)) {
      try {
        const url = new URL(target); if (!["http:", "https:"].includes(url.protocol)) throw new Error("unsupported");
        const anchor = node("a"); anchor.href = url.href; anchor.target = "_blank"; anchor.rel = "noopener noreferrer"; appendInline(anchor, label, depth); parent.append(anchor); return;
      } catch { parent.append(document.createTextNode(label)); return; }
    }
    const index = target.indexOf("#"); const part = index < 0 ? target : target.slice(0, index); const fragment = index < 0 ? "" : target.slice(index + 1);
    const relative = part ? pathValue(part, state.reader?.path || "", true) : state.reader?.path;
    if (!relative || (part && !/\.md$/i.test(relative))) { parent.append(document.createTextNode(label)); return; }
    const anchor = node("a"); anchor.href = fragment && !part ? `#${fragment}` : "/mobile.html"; appendInline(anchor, label, depth);
    anchor.addEventListener("click", event => { event.preventDefault(); if (samePath(relative, state.reader?.path)) scrollFragment(fragment); else void openDocument(relative, { fragment, push: false }); }); parent.append(anchor);
  }
  function renderMarkdown(source, container, quoteDepth = 0) {
    container.replaceChildren();
    const value = String(source).replace(/\r\n?/g, "\n"); const lines = value.split("\n");
    const plain = content => { const pre = node("pre"); pre.append(node("code", content)); return pre; };
    if (value.length > 512000 || lines.length > 6000 || lines.some(line => line.length > 12000)) { container.append(node("p", "较长文件按纯文本显示，正文完整保留。", "muted small"), plain(value)); return; }
    const tableRule = line => /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line || "");
    const cells = line => {
      const content = line.trim().replace(/^\||\|$/g, ""); const values = []; let cell = "";
      // Avoid regex lookbehind so this reader also parses on older iPhone Safari.
      for (let offset = 0; offset < content.length; offset += 1) {
        if (content[offset] === "\\" && content[offset + 1] === "|") { cell += "|"; offset += 1; }
        else if (content[offset] === "|") { values.push(cell.trim()); cell = ""; }
        else cell += content[offset];
      }
      values.push(cell.trim()); return values;
    };
    const listMatch = line => /^(\s*)([-*+]|\d+[.)])\s+(.+)/.exec(line || "");
    const indentOf = match => match[1].replaceAll("\t", "    ").length;
    const blockStart = (line, index) => !line.trim() || /^\s{0,3}(?:#{1,6}\s|`{3,}|~{3,}|>\s?|(?:[-*_]\s*){3,}$)/.test(line) || listMatch(line) || (line.includes("|") && tableRule(lines[index + 1]));
    const readList = (start, depth = 0) => {
      const first = listMatch(lines[start]); const indent = indentOf(first); const ordered = /^\d/.test(first[2]); const list = node(ordered ? "ol" : "ul");
      if (ordered) list.start = Number.parseInt(first[2], 10) || 1;
      let index = start, lastItem = null;
      while (index < lines.length) {
        const match = listMatch(lines[index]); if (!match || indentOf(match) < indent) break;
        if (indentOf(match) > indent) { if (!lastItem || depth >= 8) break; const nested = readList(index, depth + 1); lastItem.append(nested.list); index = nested.index; continue; }
        if (/^\d/.test(match[2]) !== ordered) break;
        lastItem = node("li"); appendInline(lastItem, match[3]); list.append(lastItem); index += 1;
        while (index < lines.length && lines[index].trim() && !listMatch(lines[index]) && /^\s+/.test(lines[index]) && lines[index].match(/^\s*/)[0].length > indent) { const continuation = node("p"); appendInline(continuation, lines[index++].trim()); lastItem.append(continuation); }
      }
      return { list, index };
    };
    let index = 0;
    while (index < lines.length) {
      const line = lines[index]; if (!line.trim()) { index += 1; continue; }
      const fence = /^\s{0,3}(`{3,}|~{3,})/.exec(line);
      if (fence) { const close = new RegExp(`^\\s{0,3}${fence[1][0]}{${fence[1].length},}\\s*$`); const codeLines = []; index += 1; while (index < lines.length && !close.test(lines[index])) codeLines.push(lines[index++]); if (index < lines.length) index += 1; container.append(plain(codeLines.join("\n"))); continue; }
      const heading = /^(#{1,6})\s+(.+?)(?:\s+#+)?\s*$/.exec(line);
      if (heading) {
        const item = node(`h${heading[1].length}`); appendInline(item, heading[2]); const base = slug(item.textContent); let key = base, count = 1; while (state.headings.has(key)) key = `${base}-${count++}`;
        item.id = `phone-heading-${key}`; state.headings.set(key, item); if (!(quoteDepth === 0 && index === 0 && heading[1].length === 1 && item.textContent.trim() === el("readerTitle").textContent.trim())) container.append(item); else state.headings.set(key, el("readerTitle")); index += 1; continue;
      }
      if (/^\s{0,3}(?:[-*_]\s*){3,}$/.test(line)) { container.append(node("hr")); index += 1; continue; }
      if (/^\s{0,3}>/.test(line) && quoteDepth < 4) { const quotes = []; while (index < lines.length && /^\s{0,3}>/.test(lines[index])) quotes.push(lines[index++].replace(/^\s{0,3}>\s?/, "")); const quote = node("blockquote"); renderMarkdown(quotes.join("\n"), quote, quoteDepth + 1); container.append(quote); continue; }
      if (line.includes("|") && tableRule(lines[index + 1]) && cells(line).length <= 40) {
        const wrap = node("div", "", "reader-table-scroll"); wrap.tabIndex = 0; wrap.setAttribute("aria-label", "表格，可横向滚动"); const table = node("table"), head = node("thead"), row = node("tr");
        for (const cell of cells(line)) { const th = node("th"); th.scope = "col"; appendInline(th, cell); row.append(th); } head.append(row); table.append(head); index += 2;
        const body = node("tbody"); while (index < lines.length && lines[index].trim() && lines[index].includes("|") && cells(lines[index]).length <= 40) { const tr = node("tr"); for (const cell of cells(lines[index++])) { const td = node("td"); appendInline(td, cell); tr.append(td); } body.append(tr); } table.append(body); wrap.append(table); container.append(wrap); continue;
      }
      if (listMatch(line)) { const result = readList(index); container.append(result.list); index = result.index; continue; }
      const paragraph = node("p"); const parts = [line]; index += 1; while (index < lines.length && !blockStart(lines[index], index)) parts.push(lines[index++]);
      parts.forEach((part, offset) => { if (offset) paragraph.append(/ {2}$/.test(parts[offset - 1]) ? node("br") : document.createTextNode(" ")); appendInline(paragraph, part.trim()); }); container.append(paragraph);
    }
  }
  function setFont(value) {
    state.font = Math.min(26, Math.max(14, value)); document.documentElement.style.setProperty("--reader-size", `${state.font}px`);
    // Reading preferences and the last read-only task snapshot use browser storage. Documents and pairing tokens do not.
    try { localStorage.setItem("codexPhone.readerFont.v1", String(state.font)); } catch { /* Reading works without storage. */ }
    updateReaderControls();
  }

  el("pairForm").addEventListener("submit", async event => {
    event.preventDefault(); if (state.busy) return;
    const code = el("pairCode").value.trim(); if (!/^\d{6}$/.test(code)) { notice("pairNotice", "请输入电脑显示的 6 位配对码。", true); return; }
    setBusy(true); notice("pairNotice", "正在连接电脑…");
    try { await api("pair", { code, remember: Boolean(el("pairRemember").checked), deviceName: phoneDeviceName() }); el("pairCode").value = ""; await refreshDashboard(); void pollLivePlan(); }
    catch (error) { el("pairCode").value = ""; failure(error, "pairNotice"); }
    finally { setBusy(false); }
  });
  el("refreshButton").addEventListener("click", () => void refresh());
  el("savePlanSnapshot").addEventListener("click", savePlanSnapshot);
  el("musicRefresh").addEventListener("click", () => void loadMusic(true));
  el("musicPlay").addEventListener("click", () => { if (el("musicAudio").paused) playMusic(); else { el("musicAudio").pause(); updateMusicControls(); } });
  el("musicPrevious").addEventListener("click", () => advanceMusic(-1));
  el("musicNext").addEventListener("click", () => advanceMusic(1));
  el("musicRepeat").addEventListener("click", () => { state.music.repeat = state.music.repeat === "all" ? "one" : state.music.repeat === "one" ? "off" : "all"; updateMusicControls(); });
  for (const button of document.querySelectorAll("button[data-music-tier]")) button.addEventListener("click", () => { state.music.tier = button.dataset.musicTier; state.music.visible = 60; renderMusicTracks(); });
  el("musicMore").addEventListener("click", () => { state.music.visible += 60; renderMusicTracks(); });
  el("musicSeek").addEventListener("input", () => { const audio = el("musicAudio"); if (state.music.selected && Number.isFinite(audio.duration) && audio.duration > 0) { audio.currentTime = audio.duration * Math.min(1000, Math.max(0, Number(el("musicSeek").value) || 0)) / 1000; updateMusicPosition(); } });
  for (const event of ["play", "pause", "loadedmetadata", "durationchange"]) el("musicAudio").addEventListener(event, updateMusicControls);
  el("musicAudio").addEventListener("timeupdate", updateMusicPosition);
  el("musicAudio").addEventListener("ended", () => advanceMusic(1, true));
  el("musicAudio").addEventListener("error", () => void musicAudioError());
  el("offlineRetry").addEventListener("click", () => void bootstrap());
  el("logoutButton").addEventListener("click", async () => {
    if (state.busy || state.mutationBusy) return;
    setBusy(true);
    try { await api("logout", {}); showPair("已断开这台手机。"); }
    catch (error) { failure(error); }
    finally { setBusy(false); }
  });
  for (const button of document.querySelectorAll("[data-tab]")) button.addEventListener("click", () => selectTab(button.dataset.tab));
  for (const button of document.querySelectorAll("[data-inbox]")) button.addEventListener("click", () => { state.inbox = button.dataset.inbox; renderInbox(); });
  el("readerBack").addEventListener("click", () => closeReader(true));
  el("readerLater").addEventListener("click", () => void moveReader("later"));
  el("readerRead").addEventListener("click", () => void moveReader("read"));
  el("fontSmaller").addEventListener("click", () => setFont(state.font - 2));
  el("fontLarger").addEventListener("click", () => setFont(state.font + 2));
  window.addEventListener("popstate", () => closeReader(false));
  window.addEventListener("offline", () => { if (state.paired) showOffline(new Error("Wi-Fi 连接已中断。")); });
  window.addEventListener("online", () => { if (state.paired) void pollLivePlan(); if (state.paired || uiUpdate.trusted) void checkConnectedVersion(); });
  document.addEventListener("visibilitychange", async () => {
    window.clearTimeout(uiUpdate.timer); uiUpdate.timer = 0;
    window.clearTimeout(livePlan.timer); livePlan.timer = null;
    if (document.hidden && livePlan.controller) { state.generation += 1; livePlan.controller.abort(); livePlan.controller = null; livePlan.busy = false; }
    syncWorkPanelActivity();
    if (document.hidden || state.busy) return;
    if (!state.paired) { if (uiUpdate.trusted) await checkConnectedVersion(); return; }
    try { const result = await api("status"); if (!result.paired) showPair("配对已过期，请重新连接电脑。"); else renderVersion(result.version); }
    catch (error) { failure(error); }
    syncWorkPanelActivity();
    if (state.paired) { void pollLivePlan(); await maybeReloadConnectedUi(); } scheduleVersionCheck();
  });
  try { const font = Number(localStorage.getItem("codexPhone.readerFont.v1")); if (font >= 14 && font <= 26) state.font = font; } catch { /* Presentation defaults work without storage. */ }
  document.documentElement.style.setProperty("--reader-size", `${state.font}px`);
  bindMusicMediaSession();
  void bootstrap();
})();
