(() => {
  "use strict";
  const make = (tag, text = "", className = "") => { const node = document.createElement(tag); node.textContent = text; node.className = className; return node; };
  const button = (text, action, className = "") => { const node = make("button", text, `conversations-button ${className}`.trim()); node.type = "button"; node.addEventListener("click", action); return node; };
  const uuid = () => globalThis.crypto?.randomUUID?.() || "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, char => { const value = Math.floor(Math.random() * 16); return (char === "x" ? value : value & 3 | 8).toString(16); });
  const validId = id => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(String(id || ""));
  const normalizePath = path => String(path || "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
  const stamp = value => { const time = Date.parse(value); return Number.isFinite(time) ? time : null; };
  const fetched = value => { const time = stamp(value); if (time === null) return "尚未抓取"; const age = Math.max(0, Date.now() - time); return `抓取于 ${new Date(time).toLocaleString()} · 缓存状态${age > 300000 ? "，已过期，请更新" : "，非实时"}`; };
  function statusOf(thread) {
    const raw = thread?.status, type = typeof raw === "string" ? raw : typeof raw?.type === "string" ? raw.type : "", normalized = type.toLowerCase().replace(/[_ -]/g, "");
    const flags = Array.isArray(raw?.activeFlags) ? raw.activeFlags.map(value => String(value).toLowerCase().replace(/[_ -]/g, "")) : [];
    const attention = thread?.needsAttention === true || ["needsattention", "waitingforinput", "waitingforapproval"].includes(normalized) || flags.some(flag => ["needsattention", "waitingforinput", "waitingforapproval", "waitingonapproval", "waitingonuserinput"].includes(flag));
    const active = ["active", "running", "inprogress", "busy"].includes(normalized);
    const name = attention ? "需要处理" : active ? "进行中" : normalized === "notloaded" ? "尚未加载" : ["idle", "completed", "ready"].includes(normalized) ? "空闲" : type ? type : "状态未提供";
    return { name, active, attention, type };
  }
  const freshAt = value => { const time = stamp(value); return time !== null && Date.now() - time <= 300000; };
  const phaseName = phase => typeof phase === "string" && phase ? `${({ final: "最终回答", final_answer: "最终回答", commentary: "进度" })[phase] || "来源阶段"}（phase：${phase}）` : "";
  function openLink(thread) {
    if (thread?.kind === "codex" && thread.hostId === "local" && validId(thread.id)) return `codex://threads/${thread.id}`;
    if (thread?.kind === "chatgpt" && typeof thread.openUrl === "string" && /^https:\/\/(?:chatgpt\.com|chat\.openai\.com)\/c\/[0-9a-f-]{36}(?:[?#].*)?$/i.test(thread.openUrl)) return thread.openUrl;
    return "";
  }
  function create(root, options = {}) {
    if (!root) return null;
    const phone = Boolean(options.phone), base = phone ? "/api/phone/workflow" : "/api/workflow";
    const state = { active: false, private: false, generation: 0, catalogSequence: 0, detailSequence: 0, timer: 0, statusTimer: 0, catalog: null, selectedId: "", snapshot: null, detailError: "", expanded: new Map(), messagesOpen: new Map(), autoRequested: new Set(), pending: new Map(), posts: new Set() };
    const controllers = new Map();
    const header = make("header", "", "conversations-header"), title = make("div"); title.append(make("h2", "会话"), make("p", "查看已抓取的真实对话；选定会话后，继续整理任务。", "conversations-muted"));
    const refreshList = button("刷新列表", () => void reload()); header.append(title, refreshList);
    const notice = make("p", "", "conversations-notice"); notice.setAttribute("role", "status"); notice.setAttribute("aria-live", "polite");
    const catalogMeta = make("p", "尚未抓取", "conversations-meta");
    const main = make("div", "", "conversations-main"), sidebar = make("aside", "", "conversations-sidebar"), list = make("div", "", "conversations-list"); sidebar.append(list);
    const detail = make("section", "", "conversations-detail"), back = button("‹ 返回会话列表", () => { state.selectedId = ""; state.snapshot = null; state.detailSequence++; abort("detail"); renderDetail(); renderList(); }), detailTitle = make("h3"), sourceMeta = make("p", "", "conversations-meta"), detailMeta = make("p", "", "conversations-meta"), coverage = make("p", "", "conversations-coverage"), requestState = make("div", "", "conversations-requests");
    const actions = make("div", "", "conversations-actions"), update = button("更新对话", () => void queueRead("refresh")), older = button("更多历史", () => void queueRead("older")), choose = button("使用这个会话", () => { const thread = currentThread(); if (thread && !state.private) options.onTarget?.({ ...thread }); }, "conversations-primary"), original = make("a", "打开原会话", "conversations-button"), unavailableLink = make("span", "目前未提供可打开的原会话入口", "conversations-muted"); original.rel = "noopener noreferrer"; actions.append(update, older, choose, original, unavailableLink);
    const messages = make("div", "", "conversations-messages"); detail.append(back, detailTitle, sourceMeta, detailMeta, coverage, actions, requestState, make("p", "以下为 App Tools 实际可读文字；快取可能不包含完整原会话或工具输出。", "conversations-muted"), messages);
    const empty = make("div", "请选择一个会话，查看电脑保存的对话快取。", "conversations-empty"); main.append(sidebar, empty, detail); root.replaceChildren(header, notice, catalogMeta, main); root.classList.add("conversations-panel"); root.dataset.phone = String(phone);
    function say(text, error = false) { notice.textContent = text; notice.dataset.error = String(error); }
    function currentThread() { return state.catalog?.threads?.find(thread => thread.id === state.selectedId) || (state.snapshot?.thread?.id === state.selectedId ? state.snapshot.thread : null); }
    function abort(scope) { for (const [controller, kind] of controllers) if (!scope || kind === scope) { controller.abort(); controllers.delete(controller); } }
    function stopTimer() { if (state.timer) window.clearTimeout(state.timer); if (state.statusTimer) window.clearTimeout(state.statusTimer); state.timer = 0; state.statusTimer = 0; }
    function schedule() {
      stopTimer(); if (!state.active || document.hidden || state.private) return;
      state.timer = window.setTimeout(() => { state.timer = 0; void reload(); }, 30000);
      if (freshAt(state.catalog?.fetchedAt) && state.catalog?.threads?.some(thread => statusOf(thread).active)) state.statusTimer = window.setTimeout(() => { state.statusTimer = 0; if (state.active && !document.hidden && !state.private) { renderList(); renderDetail(); } }, Math.max(1, stamp(state.catalog.fetchedAt) + 300001 - Date.now()));
    }
    function guard(generation) { return generation === state.generation && state.active && !document.hidden && !state.private; }
    function clearPrivate() {
      state.generation++; state.catalogSequence++; state.detailSequence++; state.private = true; state.active = false; stopTimer(); abort(); state.catalog = null; state.snapshot = null; state.selectedId = ""; state.pending.clear(); state.posts.clear(); state.messagesOpen.clear(); state.autoRequested.clear(); state.expanded.clear(); renderList(); renderDetail(); catalogMeta.textContent = "尚未抓取"; say(phone ? "连接授权已失效，请回到手机入口重新连接电脑。" : "会话访问未获授权，请重新连接。", true);
    }
    async function call(path, payload, scope) {
      const controller = new AbortController(), generation = state.generation; let timedOut = false; controllers.set(controller, scope); const deadline = window.setTimeout(() => { timedOut = true; controller.abort(); }, 15000);
      try {
        const result = await fetch(`${base}/${path}`, { method: payload ? "POST" : "GET", headers: { Accept: "application/json", ...(phone ? { "X-Codex-Phone": "1" } : {}), ...(payload ? { "Content-Type": "application/json" } : {}) }, body: payload ? JSON.stringify(payload) : undefined, credentials: "same-origin", mode: "same-origin", referrerPolicy: "same-origin", redirect: "error", cache: "no-store", signal: controller.signal });
        if (!guard(generation) || controller.signal.aborted) throw Object.assign(Error("已取消"), { cancelled: true });
        if (result.status === 401) { clearPrivate(); options.onAuth?.(); throw Object.assign(Error("连接授权已失效"), { cancelled: true }); }
        const data = await result.json(); if (!guard(generation) || controller.signal.aborted) throw Object.assign(Error("已取消"), { cancelled: true });
        if (!result.ok) throw Object.assign(Error(data.error || `请求失败 (${result.status})`), { status: result.status });
        options.onConnectionState?.(true); return data;
      } catch (error) {
        if (timedOut && guard(generation)) { options.onConnectionState?.(false); throw Error("读取连接超时"); }
        if (error.name === "AbortError" || !guard(generation) || controller.signal.aborted) throw Object.assign(Error("已取消"), { cancelled: true });
        if (!error.status && !error.cancelled) options.onConnectionState?.(false); throw error;
      } finally { window.clearTimeout(deadline); controllers.delete(controller); }
    }
    function assignedProject(thread, projects) {
      const exact = projects.find(project => project.id === thread.projectId); if (exact) return exact.id;
      const cwd = normalizePath(thread.cwd); if (!cwd) return "";
      let match = null; for (const project of projects) { const path = normalizePath(project.path); if (path && (cwd === path || cwd.startsWith(`${path}/`)) && (!match || path.length > match.length)) match = { id: project.id, length: path.length }; } return match?.id || "";
    }
    function observedStatus(thread) { const status = statusOf(thread), fresh = freshAt(state.catalog?.fetchedAt); return { ...status, active: status.active && fresh, name: status.active && !fresh ? "上次进行中，待更新" : status.name }; }
    function threadButton(thread) {
      const node = button("", () => void selectThread(thread.id), "conversations-thread"), heading = make("span", "", "conversations-thread-heading"), status = observedStatus(thread), text = make("span", thread.title || "（尚无标题）", "conversations-thread-title"); node.dataset.threadId = thread.id; node.dataset.selected = String(state.selectedId === thread.id); node.setAttribute("aria-pressed", String(state.selectedId === thread.id));
      heading.append(text); if (thread.unread === true) heading.append(make("span", "未读", "conversations-unread"));
      const metadata = make("span", "", "conversations-thread-meta"), indicator = make("span", "", status.active ? "conversations-spinner" : "conversations-status-dot"); indicator.setAttribute("aria-hidden", "true"); metadata.append(indicator, make("span", status.name), make("span", thread.kind === "chatgpt" ? "ChatGPT" : thread.kind === "codex" ? "Codex" : "来源未提供")); node.dataset.active = String(status.active); node.dataset.attention = String(status.attention); node.append(heading, metadata); return node;
    }
    function group(name, key, items, info = "", defaultOpen = false) {
      const node = make("details", "", "conversations-group"), summary = make("summary"), label = make("span", name); summary.append(label, make("span", String(items.length), "conversations-count")); node.append(summary); node.open = state.expanded.has(key) ? state.expanded.get(key) : defaultOpen; node.dataset.group = key;
      node.addEventListener("toggle", () => state.expanded.set(key, node.open)); if (info) node.append(make("p", info, "conversations-path")); const children = make("div", "", "conversations-group-threads"); for (const thread of items) children.append(threadButton(thread)); if (!items.length) children.append(make("p", "暂无已抓取会话", "conversations-muted")); node.append(children); return node;
    }
    function renderList() {
      list.replaceChildren(); const catalog = state.catalog; if (!catalog || state.private) { list.append(make("p", state.private ? "请重新连接电脑" : "等待会话列表", "conversations-muted")); return; }
      const threads = Array.isArray(catalog.threads) ? catalog.threads : [], projects = Array.isArray(catalog.projects) ? catalog.projects : []; catalogMeta.textContent = `${fetched(catalog.fetchedAt)}${catalog.partial ? " · 列表尚未完整取得" : ""}`; catalogMeta.dataset.stale = String(stamp(catalog.fetchedAt) === null || Date.now() - stamp(catalog.fetchedAt) > 300000);
      const projectGroups = make("details", "", "conversations-projects"); projectGroups.open = state.expanded.has("projects") ? state.expanded.get("projects") : true; projectGroups.dataset.group = "projects"; projectGroups.addEventListener("toggle", () => state.expanded.set("projects", projectGroups.open)); projectGroups.append(make("summary", "Projects · 项目"));
      for (const project of projects) projectGroups.append(group(project.label || "（尚无项目标题）", `project:${project.id}`, threads.filter(thread => assignedProject(thread, projects) === project.id), project.path || "", true));
      const unassigned = threads.filter(thread => !assignedProject(thread, projects)); if (!projects.length) projectGroups.append(make("p", "暂无项目快照", "conversations-muted"));
      list.append(projectGroups, group("Recents · 最近", "recents", unassigned, "没有项目归属的会话，保持来源快照的最近顺序。", true));
    }
    function renderRequests() {
      requestState.replaceChildren(); const requests = Array.isArray(state.snapshot?.requests) ? state.snapshot.requests : state.catalog?.requests || [];
      const matching = requests.filter(request => request.threadId === state.selectedId), current = matching.slice().sort((left, right) => Number(right.status === "pending") - Number(left.status === "pending") || (stamp(right.updatedAt || right.createdAt) || 0) - (stamp(left.updatedAt || left.createdAt) || 0)).slice(0, 4); let pending = matching.some(request => request.status === "pending");
      for (const request of current) { if (request.status === "pending") pending = true; const row = make("p", `${request.mode === "older" ? "更多历史" : "更新对话"}：${({ pending: "等待读取", completed: "读取完成", failed: "读取失败" })[request.status] || request.status || "状态未提供"}${request.error ? ` · ${request.error}` : ""}`, "conversations-request"); row.dataset.requestStatus = request.status || ""; requestState.append(row); }
      if (pending) requestState.append(make("p", "只在读取对话，没有向任何会话发送消息。读取完成后，此页会自动显示快取。", "conversations-muted"));
      return pending;
    }
    function renderDetail() {
      const thread = currentThread(), selected = Boolean(state.selectedId && thread && !state.private); root.dataset.detail = String(selected); detail.hidden = !selected; empty.hidden = selected; if (!selected) { messages.replaceChildren(); detailTitle.textContent = ""; sourceMeta.textContent = ""; detailMeta.textContent = ""; coverage.textContent = ""; requestState.replaceChildren(); original.removeAttribute?.("href"); return; }
      detailTitle.textContent = thread.title || "（尚无标题）"; const status = observedStatus(thread); sourceMeta.textContent = `${thread.kind === "chatgpt" ? "ChatGPT" : thread.kind === "codex" ? "Codex" : "来源未提供"} · ${status.name}${thread.hostId ? ` · 主机：${thread.hostId}` : ""}${thread.cwd ? ` · 工作目录：${thread.cwd}` : ""}`;
      const snapshot = state.snapshot, values = Array.isArray(snapshot?.messages) ? snapshot.messages : []; detailMeta.textContent = fetched(snapshot?.fetchedAt); const counts = snapshot?.coverage || {}, count = Number.isFinite(counts.messageCount) ? counts.messageCount : values.length, pages = Number.isFinite(counts.pageCount) ? counts.pageCount : 0; coverage.textContent = `已读取 ${count} 条消息 · ${pages} 页${snapshot?.partial ? " · 部分快取，未取得完整对话" : ""}${snapshot?.hasMore ? " · 仍有历史尚未获取" : ""}${counts.description ? ` · ${counts.description}` : ""}`;
      const inFlight = renderRequests(), posting = state.posts.has(state.selectedId); update.disabled = posting || inFlight; older.disabled = posting || inFlight || !snapshot?.hasMore || !snapshot?.olderCursor; choose.disabled = !["codex", "chatgpt"].includes(thread.kind) || !validId(thread.id);
      const href = openLink(thread); original.hidden = !href; unavailableLink.hidden = Boolean(href); if (href) original.href = href; else original.removeAttribute?.("href");
      messages.replaceChildren(); if (!snapshot) { messages.append(make("p", state.detailError ? `快取未能读取：${state.detailError}。可点更新对话提出读取请求。` : "正在读取电脑上的对话快取……", "conversations-muted")); return; }
      if (!values.length) messages.append(make("p", "尚无已抓取消息。读取请求只取回对话，不发送聊天消息。", "conversations-muted"));
      values.forEach((message, index) => {
        if (!["user", "assistant"].includes(message.role) || typeof message.text !== "string") return;
        const item = make("details", "", "conversations-message"), summary = make("summary"), key = `${state.selectedId}:${message.id || message.sourceMessageId || `${message.turnId || "turn"}:${index}`}`; item.dataset.role = message.role; item.dataset.messageId = message.id || ""; item.open = state.messagesOpen.has(key) ? state.messagesOpen.get(key) : true; item.addEventListener("toggle", () => state.messagesOpen.set(key, item.open));
        summary.append(make("strong", message.role === "user" ? "你" : "助手"), make("span", [message.status, phaseName(message.phase), message.createdAt].filter(value => typeof value === "string" && value).join(" · "), "conversations-muted")); item.append(summary, make("p", message.text, "conversations-message-text")); if (message.turnId || message.sourceMessageId) item.append(make("p", [message.turnId ? `轮次：${message.turnId}` : "", message.sourceMessageId ? `来源消息：${message.sourceMessageId}` : ""].filter(Boolean).join(" · "), "conversations-muted")); if (message.truncated) item.append(make("p", "这条消息已截断；目前显示的是部分文字。", "conversations-truncated")); messages.append(item);
      });
    }
    async function readThread(id) {
      const sequence = ++state.detailSequence, generation = state.generation; abort("detail"); state.detailError = "";
      try {
        const snapshot = await call(`conversations/thread?id=${encodeURIComponent(id)}`, undefined, "detail"); if (!guard(generation) || sequence !== state.detailSequence || state.selectedId !== id) return;
        state.snapshot = snapshot; renderDetail();
        if (!snapshot.messages?.length && !snapshot.fetchedAt && !state.autoRequested.has(id)) { state.autoRequested.add(id); if (!(snapshot.requests || []).some(request => request.threadId === id && request.status === "pending")) void queueRead("refresh"); }
      } catch (error) { if (!error.cancelled && guard(generation) && sequence === state.detailSequence && state.selectedId === id) { state.detailError = error.message; say(`未能读取对话快取：${error.message}`, true); renderDetail(); } }
    }
    async function selectThread(id) {
      if (!state.active || state.private || !state.catalog?.threads?.some(thread => thread.id === id)) return; state.selectedId = id; state.snapshot = null; state.detailError = ""; say("显示电脑已抓取的对话；更新仅提出读取请求。"); renderList(); renderDetail(); await readThread(id); schedule();
    }
    async function queueRead(mode) {
      const id = state.selectedId; if (!state.active || document.hidden || state.private || !validId(id) || state.posts.has(id)) return;
      if (mode === "older" && (!state.snapshot?.hasMore || !state.snapshot?.olderCursor)) { say("目前没有可读取的更早历史。", true); return; }
      const requests = state.snapshot?.requests || state.catalog?.requests || []; if (requests.some(request => request.threadId === id && request.status === "pending")) { say("对话读取已排队，请等待快取更新。"); return; }
      const key = `${id}:${mode}`, pending = state.pending.get(key) || { requestId: uuid(), threadId: id, mode }; state.pending.set(key, pending); state.posts.add(id); const generation = state.generation; renderDetail();
      try {
        const result = await call("conversations/request", pending, "request"); if (!guard(generation)) return; if (!result.fetchRequest?.id || result.fetchRequest.threadId !== id || result.fetchRequest.mode !== mode) throw Error("读取请求未返回对应确认记录"); state.pending.delete(key); if (state.selectedId === id) { const source = state.snapshot || state.catalog; if (source) source.requests = [...(source.requests || []).filter(request => request.id !== result.fetchRequest.id), result.fetchRequest]; renderDetail(); say("已排入只读对话请求，尚未取得新内容；不会发送聊天消息。"); }
      } catch (error) { if (error.cancelled) return; if (error.status >= 400 && error.status < 500) state.pending.delete(key); if (guard(generation) && state.selectedId === id) say(error.status ? `读取请求未接受：${error.message}` : `读取请求尚未确认：${error.message} 可重试同一请求。`, true); }
      finally { if (generation === state.generation) { state.posts.delete(id); if (state.selectedId === id) renderDetail(); schedule(); } }
    }
    async function reload() {
      if (!state.active || document.hidden || state.private) return; const sequence = ++state.catalogSequence, generation = state.generation; abort("catalog"); refreshList.disabled = true;
      try {
        const catalog = await call("conversations", undefined, "catalog"); if (!guard(generation) || sequence !== state.catalogSequence) return; state.catalog = catalog; renderList(); if (state.selectedId && !catalog.threads?.some(thread => thread.id === state.selectedId)) { state.selectedId = ""; state.snapshot = null; state.detailSequence++; abort("detail"); } renderDetail(); if (state.selectedId) await readThread(state.selectedId);
      } catch (error) { if (!error.cancelled && guard(generation) && sequence === state.catalogSequence) { renderList(); renderDetail(); say(`列表更新失败：${error.message} 当前显示此前取得的快取。`, true); } }
      finally { if (generation === state.generation && sequence === state.catalogSequence) { refreshList.disabled = false; schedule(); } }
    }
    function setActive(value) { const next = Boolean(value); if (next === state.active) return; state.active = next; state.generation++; state.catalogSequence++; state.detailSequence++; stopTimer(); abort(); state.posts.clear(); refreshList.disabled = false; if (state.active) { state.private = false; void reload(); } }
    document.addEventListener("visibilitychange", () => { if (document.hidden) { state.generation++; state.catalogSequence++; state.detailSequence++; stopTimer(); abort(); state.posts.clear(); refreshList.disabled = false; } else if (state.active && !state.private) void reload(); });
    renderList(); renderDetail();
    return { setActive, refresh: reload, clear: clearPrivate, canReload: () => state.posts.size === 0, selectThread };
  }
  window.CodexConversationsPanel = { create };
})();
