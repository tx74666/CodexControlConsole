(() => {
  "use strict";
  const make = (tag, text = "", className = "") => { const node = document.createElement(tag); node.textContent = text; node.className = className; return node; };
  const uuid = () => globalThis.crypto?.randomUUID?.() || "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, value => { const n = Math.floor(Math.random() * 16); return (value === "x" ? n : (n & 3) | 8).toString(16); });
  const button = (text, action, className = "") => { const node = make("button", text, className); node.type = "button"; node.addEventListener("click", action); return node; };
  const field = (tag, label, className = "") => { const node = make(tag, "", className); node.setAttribute("aria-label", label); return node; };
  const tiers = [{ id: "fast", label: "极速" }, { id: "high", label: "高" }, { id: "pro", label: "Pro" }];
  const when = value => { const date = new Date(value || ""); return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" }); };
  function fileStore() {
    if (window.PhoneStore) return { get: id => window.PhoneStore.get("settings", id), put: value => window.PhoneStore.put("settings", value), remove: id => window.PhoneStore.remove("settings", id) };
    let opened;
    const database = () => opened ||= new Promise((resolve, reject) => { if (!globalThis.indexedDB) return reject(new Error("浏览器暂时不能保存图片草稿，请保持页面打开。")); const request = indexedDB.open("codex-workflow-drafts-v1", 1); request.onupgradeneeded = () => request.result.createObjectStore("drafts", { keyPath: "id" }); request.onsuccess = () => resolve(request.result); request.onerror = () => { opened = null; reject(request.error); }; });
    const op = async (mode, action) => { const db = await database(); return new Promise((resolve, reject) => { const tx = db.transaction("drafts", mode), request = action(tx.objectStore("drafts")); let value; request.onsuccess = () => { value = request.result; }; tx.oncomplete = () => resolve(value); tx.onerror = tx.onabort = () => reject(tx.error); }); };
    return { get: id => op("readonly", store => store.get(id)), put: value => op("readwrite", store => store.put(value)), remove: id => op("readwrite", store => store.delete(id)) };
  }
  function create(root, options = {}) {
    if (!root) return null;
    const phone = options.phone !== false, offline = Boolean(options.offline), adapter = typeof options.endpoint === "function" ? options.endpoint : null, base = typeof options.endpoint === "string" ? options.endpoint : phone ? "/api/phone/workflow" : "/api/workflow";
    const storageKey = options.storageKey || `codexMobileDialogue.v1:${offline ? "offline" : base}`;
    let saved;
    try { saved = JSON.parse(localStorage.getItem(storageKey) || "{}"); } catch { saved = {}; }
    if (!saved || typeof saved !== "object") saved = {};
    const state = { active: false, generation: 0, reading: false, busy: false, clientId: typeof saved.clientId === "string" ? saved.clientId : uuid(), session: null, detail: null, execution: null, tier: tiers.some(item => item.id === saved.tier) ? saved.tier : "high", drafts: saved.drafts && typeof saved.drafts === "object" ? saved.drafts : {}, editDrafts: saved.editDrafts && typeof saved.editDrafts === "object" ? saved.editDrafts : {}, pending: saved.pending || null, view: "chat", ideas: [], projects: [], idea: null, ideaDetail: null, search: saved.search || "", project: saved.project || "", archived: false, listScroll: Number(saved.listScroll) || 0, chatScroll: 0, messageIds: new Set(), storageFailed: false, composing: false, dirty: false, editorDirty: false, newResults: false, requestSequence: 0 };
    const controllers = new Set();
    let draftSync = null, draftTimer = 0, ideaSequence = 0, files = [], fileOwner = null, fileError = false, fileReading = null, fileWriting = 0, uploadRequest = null, packUrl = "", packIdeaId = "", packRevision = 0;
    const blobs = options.blobStore || options.assetStore || fileStore(), filesKey = `${storageKey}:files:${state.clientId}`, filePreviews = [];
    const top = make("header", "", "dialogue-top"), topLeft = make("div", "", "dialogue-top-left"), topActions = make("div", "", "dialogue-top-actions"), title = make("h2", "对话", "dialogue-title");
    const back = button("‹ 返回", () => void goBack(), "dialogue-back"), ideasButton = button("想法", () => void showIdeas());
    const more = make("details", "", "dialogue-more"), summary = make("summary", "更多"), menu = make("div", "", "dialogue-menu"), menuMeta = make("p", "", "dialogue-menu-meta");
    const clearMenuAction = button("清空当前讨论", () => { more.open = false; void clearDiscussion(); }); menu.append(clearMenuAction);
    for (const item of [{ label: "刷新当前页面", action: () => void refresh() }, { label: "Transfer · 互传", action: () => openModule("transfer") }, { label: "音乐", action: () => openModule("music") }, { label: "资料", action: () => openModule("documents") }, { label: offline ? "连接电脑继续" : "Projects / Recents", action: () => offline ? options.onConnect?.() : openModule("conversations") }, { label: "原工作区与导入", action: () => openModule("legacy") }]) menu.append(button(item.label, () => { more.open = false; item.action(); }));
    menu.append(make("hr"), menuMeta); more.append(summary, menu); topLeft.append(back, title); topActions.append(ideasButton, more); top.append(topLeft, topActions);
    if (offline) menu.insertBefore(button("资料与更新", () => openModule("settings")), menuMeta);
    const packInput = field("input", "导入手机想法包"); packInput.type = "file"; packInput.accept = ".console-idea,application/json"; packInput.hidden = true;
    if (!offline && options.onImportPack) { menu.insertBefore(button("导入手机想法包", () => packInput.click()), menuMeta); menu.append(packInput); }
    const notice = make("p", "", "dialogue-notice"); notice.setAttribute("role", "status"); notice.setAttribute("aria-live", "polite");
    const content = make("main", "", "dialogue-content"), context = make("div", "", "dialogue-context"), contextText = make("span"), contextOpen = button("查看想法", () => void openIdea(state.session?.ideaId)); context.append(contextText, contextOpen);
    const welcome = make("div", "", "dialogue-welcome"); welcome.append(make("div", "✧", "dialogue-welcome-mark"), make("h2", "脑子里的想法，\n从这里开始。"), make("p", "直接问一句，或先记下来。\n还没想清楚，也可以慢慢聊。"));
    const suggestions = make("div", "", "dialogue-suggestions"); suggestions.append(button("先记一个念头", () => { composerInput.placeholder = "记下这个念头，以后接着想…"; composerInput.focus(); }), button("找以前的想法", () => void showIdeas())); welcome.append(suggestions);
    const messages = make("div", "", "dialogue-messages"), pending = make("div", "", "dialogue-pending"), pendingText = make("span"); pending.append(pendingText);
    const listView = make("section", "", "dialogue-list-view"), listTools = make("div", "", "dialogue-list-tools"), search = field("input", "搜索想法"), project = field("select", "按项目筛选"), ideaList = make("div", "", "dialogue-ideas-list"), listFooter = make("div", "", "dialogue-list-footer"), archiveToggle = button("查看归档", () => { state.archived = !state.archived; void loadIdeas(); });
    search.type = "search"; search.placeholder = "搜索想法"; search.value = state.search; listTools.append(search, project); listFooter.append(archiveToggle); listView.append(listTools, ideaList, listFooter);
    const detailView = make("section", "", "dialogue-detail-view"), detailHeading = make("div", "", "dialogue-detail-heading"), ideaTitle = field("input", "想法标题", "dialogue-detail-title"), detailMeta = make("p", "", "dialogue-detail-meta"), ideaBody = field("textarea", "想法内容", "dialogue-detail-body"); ideaTitle.maxLength = 240; ideaBody.rows = 5; detailHeading.append(ideaTitle, detailMeta);
    const detailActions = make("div", "", "dialogue-detail-actions"), saveEdit = button("保存修改", () => void updateIdea(), "dialogue-primary"), discussIdea = button("继续讨论", () => void openIdeaDiscussion(), "dialogue-primary"), executionDraft = button("执行稿", () => showExecutionDraft()), ideaMore = make("details", "", "dialogue-more"), ideaMenu = make("div", "", "dialogue-menu"), ideaMenuSummary = make("summary", "更多");
    const archiveIdea = button("归档想法", () => void archiveCurrent()), copyIdea = button("复制内容", () => void copyText(`${ideaTitle.value}\n\n${ideaBody.value}`)), carryIdea = button("带到电脑", () => void handoffIdea(), "dialogue-primary"), packLink = make("a", "保存想法包"); packLink.hidden = true; ideaMenu.append(copyIdea, archiveIdea); if (offline && options.onHandoff) ideaMenu.append(button("核对上次交接", () => void handoffIdea(null, true))); if (offline && options.onExportPack) ideaMenu.append(button("导出完整想法包", () => void exportPack()), packLink); ideaMore.append(ideaMenuSummary, ideaMenu); detailActions.append(saveEdit, discussIdea, executionDraft); if (offline && options.onHandoff) detailActions.append(carryIdea); detailActions.append(ideaMore);
    const detailAttachments = make("div", "", "dialogue-attachment-grid"), points = make("section", "", "dialogue-detail-section"), pointsTitle = make("h3", "长期要点"), pointsList = make("div"); points.append(pointsTitle, pointsList); detailView.append(detailHeading, ideaBody, detailAttachments, detailActions, points);
    const executionView = make("section", "", "dialogue-execution-view"), executionText = field("textarea", "执行稿", "dialogue-keypoint-editor"), saveExecution = button("保存执行稿", () => void updateIdea({ executionDraft: executionText.value }), "dialogue-primary"), handover = button("交给 Codex", () => void handToCodex(), "dialogue-primary"), executionActions = make("div", "", "dialogue-detail-actions"); executionText.rows = 12; executionActions.append(saveExecution, handover); executionView.append(make("h3", "准备好以后再执行"), make("p", "整理本轮想改什么、预期结果与范围。下一步集中核对 Codex 工作区后再确认执行。", "dialogue-source-note"), executionText, executionActions);
    content.append(context, welcome, messages, pending, listView, detailView, executionView);
    const newResult = button("有新回复 ↓", () => { state.newResults = false; newResult.hidden = true; window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" }); }, "dialogue-new-result");
    const composer = make("form", "", "dialogue-composer"), shell = make("div", "", "dialogue-composer-shell"), composerInput = field("textarea", "提问或保存想法"), composeActions = make("div", "", "dialogue-compose-actions"), composeLeft = make("div", "", "dialogue-compose-left"), composeRight = make("div", "", "dialogue-compose-right"), tier = field("select", "回答档位", "dialogue-tier");
    composerInput.placeholder = "想问什么，或先记下来…"; composerInput.rows = 1; composerInput.maxLength = 20000;
    for (const choice of tiers) { const option = make("option", choice.label); option.value = choice.id; tier.append(option); } tier.value = state.tier;
    const saveOnly = button("只保存", () => void saveIdea()), send = button("发送 ↑", () => void sendMessage(), "dialogue-send"), attach = button("＋", () => imageInput.click()), imageInput = field("input", "选择图片文件"), pendingImages = make("div", "", "dialogue-attachment-grid"); attach.setAttribute("aria-label", "添加图片"); imageInput.type = "file"; imageInput.accept = "image/jpeg,image/png,image/webp,image/gif,image/heic,image/heif"; imageInput.multiple = true; imageInput.hidden = true;
    const status = make("div", "", "dialogue-status"), draftStatus = make("p"), capabilityStatus = make("p"); status.setAttribute("role", "status"); status.append(draftStatus, capabilityStatus); composeLeft.append(attach, tier); composeRight.append(saveOnly, send); composeActions.append(composeLeft, composeRight); shell.append(pendingImages, composerInput, composeActions, imageInput); composer.append(shell, status); root.classList.add("mobile-dialogue"); root.replaceChildren(top, notice, content, newResult, composer);
    function persist() {
      try { localStorage.setItem(storageKey, JSON.stringify({ clientId: state.clientId, tier: state.tier, drafts: state.drafts, editDrafts: state.editDrafts, pending: state.pending, search: state.search, project: state.project, listScroll: state.listScroll })); state.storageFailed = false; return true; }
      catch { state.storageFailed = true; say("这台手机暂时无法保存草稿，请保留页面并复制内容。", true); return false; }
    }
    function say(text = "", error = false) { notice.textContent = text; notice.dataset.error = String(error); }
    function autosize(input, limit = 170) { input.style.height = "auto"; input.style.height = `${Math.min(limit, Math.max(48, input.scrollHeight || 48))}px`; input.style.overflowY = input.scrollHeight > limit ? "auto" : "hidden"; }
    function draftKey() { return state.session?.id || "unopened"; }
    function saveLocalDraft() { state.drafts[draftKey()] = { text: composerInput.value, tier: state.tier, updatedAt: new Date().toISOString(), unsynced: true, ...(!state.session ? { waitingForSession: true } : {}) }; state.dirty = true; persist(); draftStatus.textContent = offline ? "已保存在此手机" : "草稿已保存在此手机"; autosize(composerInput); updateControls(); }
    function restoreDraft() { const local = state.drafts[draftKey()]; composerInput.value = local?.unsynced ? local.text || "" : state.session?.draft?.text || local?.text || ""; state.dirty = Boolean(local?.unsynced); autosize(composerInput); draftStatus.textContent = state.dirty ? "草稿已保存在此手机" : state.session ? "草稿已同步电脑" : offline ? "只保存留在此手机" : ""; }
    async function call(action, body) {
      const generation = state.generation;
      if (adapter) { const result = await adapter(action, body); if (generation !== state.generation) throw Object.assign(new Error("已切换页面。"), { cancelled: true }); return result; }
      const controller = new AbortController(); controllers.add(controller); const multipart = typeof FormData !== "undefined" && body instanceof FormData, timer = window.setTimeout(() => controller.abort(), multipart ? 90000 : 15000);
      try { const response = await fetch(`${base}/${action}`, { method: body === undefined ? "GET" : "POST", credentials: "same-origin", mode: "same-origin", cache: "no-store", redirect: "error", signal: controller.signal, headers: { Accept: "application/json", ...(phone ? { "X-Codex-Phone": "1" } : {}), ...(body === undefined || multipart ? {} : { "Content-Type": "application/json" }) }, ...(body === undefined ? {} : { body: multipart ? body : JSON.stringify(body) }) });
        if (generation !== state.generation) throw Object.assign(new Error("已切换页面。"), { cancelled: true });
        if (response.status === 401) { options.onAuth?.(); throw Object.assign(new Error("请重新连接电脑。"), { auth: true }); }
        let data; try { data = await response.json(); } catch { throw new Error("电脑返回的内容暂时无法读取。"); }
        if (!response.ok) throw Object.assign(new Error(data.error || `操作未完成（${response.status}）。`), { status: response.status, data });
        options.onConnectionState?.(true); return data;
      } catch (error) { if (error instanceof TypeError || error.name === "AbortError") options.onConnectionState?.(false); throw error; }
      finally { controllers.delete(controller); window.clearTimeout(timer); }
    }
    function fail(error) { if (!error.auth && !error.cancelled) say(error.name === "AbortError" ? "电脑连接超时，草稿仍在此手机。" : error.message || "暂时无法完成，草稿已保留。", true); }
    function applyDialogue(data, expectedSession = "") {
      if (!data || data.session?.isCurrent === false || expectedSession && state.session?.id && expectedSession !== state.session.id || data.session?.id === state.session?.id && data.session?.revision < state.session?.revision) return false;
      const previousSession = state.session?.id;
      state.session = data.session || null; state.detail = data.detail || null; state.execution = data.execution || null;
      if (!previousSession && state.session?.id && state.drafts.unopened) {
        const original = state.drafts.unopened, knownSessions = Object.keys(state.drafts).filter(id => id !== "unopened");
        if (original.waitingForSession === true || !knownSessions.length) state.drafts[state.session.id] = { ...original, waitingForSession: false };
        delete state.drafts.unopened;
        persist();
      }
      if (state.session?.id && previousSession !== state.session.id) void restoreSessionFiles(state.session.id);
      const selectedTier = data.preferences?.requestedProfile || data.session?.requestedProfile; if (!saved.tier && !state.dirty && tiers.some(item => item.id === selectedTier)) state.tier = selectedTier;
      tier.value = state.tier; renderConversation(); renderCapability(); renderFiles(); updateControls(); return true;
    }
    function renderCapability() {
      const actual = state.execution?.actualReceipt?.actualProfile, verified = state.execution?.actualReceipt?.verified === true && tiers.some(item => item.id === actual);
      capabilityStatus.textContent = offline ? "电脑未连接" : verified ? `实际 ${tiers.find(item => item.id === actual).label}` : "档位待核实";
      capabilityStatus.title = state.execution?.message || "当前 App 通道的档位还未验证，不会把请求档位当作实际能力。";
      menuMeta.textContent = offline ? "内容保存在此手机；连接电脑后才可发给 ChatGPT。" : `${options.getVersion?.() || "Codex Console"}\n${state.execution?.message || "普通 Chat 自动转发尚未接通，排队不代表已送达。"}`;
    }
    function renderConversation() {
      if (state.view !== "chat") { for (const node of [context, welcome, messages, pending]) node.hidden = true; return; }
      const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 150;
      const values = Array.isArray(state.detail?.messages) ? state.detail.messages : [];
      const fresh = values.some(item => item.role === "assistant" && !state.messageIds.has(item.id));
      state.messageIds = new Set(values.map(item => item.id)); messages.replaceChildren();
      for (const message of values.filter(item => ["user", "assistant"].includes(item.role))) {
        const row = make("article", "", "dialogue-message"); row.dataset.role = message.role;
        row.append(make("p", message.role === "assistant" ? "ChatGPT" : "你", "dialogue-message-label"), make("p", message.text || "", "dialogue-message-text"));
        if (message.role === "assistant") { const actions = make("div", "", "dialogue-message-actions"); actions.append(button(state.session?.ideaId ? "补充到此想法" : "存为想法", () => void rememberAnswer(message.id)), button("复制", () => void copyText(message.text || ""))); row.append(actions); }
        if (message.truncated) row.append(make("p", "此回答来源已截断，全文请到原 Chat 查看。", "dialogue-message-note")); messages.append(row);
      }
      const jobs = Array.isArray(state.detail?.jobs) ? state.detail.jobs : [], inFlight = jobs.filter(item => ["queued", "running", "pending", "claimed", "waiting", "needs_review"].includes(item.status) || ["pending", "claimed", "waiting", "needs_review"].includes(item.appDispatch?.status)).at(-1);
      pending.replaceChildren(pendingText); pending.hidden = !inFlight;
      if (inFlight) {
        const dispatchStatus = inFlight.appDispatch?.status || inFlight.status;
        const running = ["running", "waiting"].includes(dispatchStatus);
        if (running) pending.prepend(make("span", "", "dialogue-spinner"));
        pendingText.textContent = dispatchStatus === "needs_review" ? "送达情况需要核对，未重复发送。" : running ? "正在等原聊天回答…" : "消息已保存，自动转发尚未接通。";
      }
      context.hidden = !state.session?.ideaId; contextText.textContent = state.session?.ideaId ? `围绕「${state.detail?.sourceTask?.title || state.idea?.title || "这条想法"}」继续聊` : "";
      welcome.hidden = Boolean(values.length || state.session?.ideaId); messages.hidden = !values.length;
      if (fresh && state.view === "chat") { if (atBottom) requestAnimationFrame(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "auto" })); else { state.newResults = true; newResult.hidden = false; } }
    }
    function renderView() {
      root.dataset.view = state.view; back.hidden = state.view === "chat"; ideasButton.hidden = state.view !== "chat"; clearMenuAction.hidden = state.view !== "chat";
      title.textContent = ({ chat: "对话", ideas: state.archived ? "归档想法" : "想法", detail: "想法", execution: "执行稿" })[state.view];
      listView.hidden = state.view !== "ideas"; detailView.hidden = state.view !== "detail"; executionView.hidden = state.view !== "execution"; composer.hidden = state.view !== "chat";
      for (const node of [context, welcome, messages, pending]) if (state.view !== "chat") node.hidden = true;
      if (state.view === "chat") renderConversation(); newResult.hidden = state.view !== "chat" || !state.newResults; updateControls(); options.onViewChange?.(state.view);
    }
    function currentFiles() { return !fileOwner || fileOwner === state.session?.id ? files : []; }
    function updateControls() { const empty = !composerInput.value.trim(); send.disabled = state.busy || empty || state.composing; saveOnly.disabled = state.busy || empty && !currentFiles().length && !(state.session?.draft?.attachmentIds || []).length || state.composing; attach.disabled = state.busy || Boolean(state.pending); tier.disabled = state.busy; saveEdit.hidden = !state.editorDirty; saveEdit.disabled = state.busy; handover.disabled = state.busy || !executionText.value.trim(); saveExecution.disabled = state.busy || !executionText.value.trim(); discussIdea.disabled = state.busy || state.editorDirty; executionDraft.disabled = state.busy || state.editorDirty; carryIdea.disabled = state.busy || state.editorDirty; }
    async function writeFiles(value) { fileWriting++; try { await blobs.put(value); } catch (error) { fileError = true; throw error; } finally { fileWriting--; } }
    async function saveFiles() { try { await writeFiles({ id: filesKey, files, fileOwner, uploadRequest }); fileError = false; } catch (error) { fileError = true; fail(error); throw error; } }
    async function restoreSessionFiles(id) {
      if (!id || fileOwner === id) return;
      try { if (fileOwner && files.length) await writeFiles({ id: `${filesKey}:${fileOwner}`, files, uploadRequest, fileOwner }); const value = await blobs.get(`${filesKey}:${id}`); if (state.session?.id !== id || !value?.files) return; files = value.files; fileOwner = id; uploadRequest = value.uploadRequest || null; await saveFiles(); renderFiles(); }
      catch (error) { fileError = true; fail(error); }
    }
    function renderFiles() {
      for (const source of filePreviews) URL.revokeObjectURL?.(source); filePreviews.length = 0; pendingImages.replaceChildren();
      for (const file of currentFiles()) { const source = URL.createObjectURL?.(file); if (!source) continue; filePreviews.push(source); const image = make("img"); image.src = source; image.alt = file.name || "待保存图片"; pendingImages.append(image); }
      const selected = new Set(state.session?.draft?.attachmentIds || []); for (const item of state.detail?.attachments || []) { if (!selected.has(item.id) || !/^image\//.test(item.mimeType || "")) continue; const source = item.previewUrl || item.url; if (!source) continue; const image = make("img"); image.src = source; image.alt = item.name || "已上传图片"; pendingImages.append(image); }
      pendingImages.hidden = !pendingImages.children.length; updateControls();
    }
    async function uploadFiles() {
      if (fileReading) await fileReading; if (!currentFiles().length) return; if (fileError) await saveFiles();
      await ensureSession();
      if (!fileOwner) { fileOwner = state.session.id; await saveFiles(); }
      if (!uploadRequest) { uploadRequest = { requestId: uuid(), recordId: state.session.recordId }; await saveFiles(); }
      if (uploadRequest.recordId !== state.session.recordId) throw new Error("待上传图片属于原讨论，请先返回原讨论保存，不会附到其它想法。");
      let uploaded;
      if (options.uploadAttachments) uploaded = await options.uploadAttachments(files, state.session, uploadRequest);
      else { if (offline) throw new Error("图片仍保存在此手机；连接电脑后才能同步图片。"); const form = new FormData(); form.append("requestId", uploadRequest.requestId); form.append("recordId", uploadRequest.recordId); for (const file of files) form.append("files", file, file.name || "image.png"); uploaded = await call("upload", form); }
      const attachmentIds = uploaded.uploadedAttachmentIds || uploaded.attachmentIds || (uploaded.attachments || []).map(item => item.id);
      if (!attachmentIds.length) throw new Error("尚未取得图片保存凭据，原图片草稿仍保留。");
      const payload = submission(); payload.attachmentIds = [...new Set([...payload.attachmentIds, ...attachmentIds])].slice(-4); const data = await call("mobile/dialogue/draft", payload); applyDialogue(data, state.session.id); files = []; fileOwner = null; uploadRequest = null; await saveFiles(); renderFiles();
    }
    async function ensureSession() {
      if (state.session) return state.session;
      const data = await call("mobile/dialogue/open", { requestId: uuid(), clientId: state.clientId }); applyDialogue(data); restoreDraft(); return state.session;
    }
    function submission() { return { requestId: uuid(), clientId: state.clientId, sessionId: state.session.id, expectedRevision: state.session.revision, text: composerInput.value, attachmentIds: state.session.draft?.attachmentIds || [], requestedProfile: state.tier }; }
    function durablePayload(action, candidate, identity) {
      if (state.pending) { if (state.pending.action !== action || identity.some(key => JSON.stringify(state.pending.payload[key]) !== JSON.stringify(candidate[key]))) throw new Error("上一项操作结果尚未核对。先刷新核对，原请求不会重复创建。"); return state.pending.payload; }
      state.pending = { action, payload: candidate }; if (!persist()) { state.pending = null; throw new Error("操作凭据无法保存在手机，请保留或复制原内容。"); } return candidate;
    }
    function writeRejected(error) { return error.status >= 400 && error.status < 500 && error.status !== 409 || error.status === 409 && ["revision_conflict", "dialogue_changed", "task_source_mismatch", "dispatch_in_progress"].includes(error.data?.code || error.code); }
    async function syncDraft() {
      if (draftSync || !state.active || state.busy || !state.dirty || state.storageFailed || offline) return;
      const text = composerInput.value;
      draftSync = (async () => {
        try { await ensureSession(); const id = state.session.id, data = await call("mobile/dialogue/draft", submission()); if (applyDialogue(data, id) && composerInput.value === text) { state.drafts[id] = { text, tier: state.tier, unsynced: false }; state.dirty = false; persist(); draftStatus.textContent = "草稿已同步电脑"; } }
        catch (error) { fail(error); }
      })();
      try { await draftSync; } finally { draftSync = null; }
    }
    async function sendMessage() {
      if (state.busy || state.composing || !composerInput.value.trim()) return;
      if (offline) { saveLocalDraft(); say("请连接电脑后发送；这段草稿已保存在此手机。"); options.onConnect?.(); return; }
      state.busy = true; updateControls(); say(""); const text = composerInput.value;
      try { if (draftSync) await draftSync; await ensureSession(); if (!state.pending) await uploadFiles(); const payload = durablePayload("mobile/dialogue/send", submission(), ["sessionId", "text", "requestedProfile"]);
        const data = await call("mobile/dialogue/send", payload); state.pending = null;
        if (applyDialogue(data, payload.sessionId) && composerInput.value === text) { composerInput.value = ""; state.drafts[payload.sessionId] = { text: "", tier: state.tier, unsynced: false }; state.dirty = false; autosize(composerInput); }
        persist(); say(data.execution?.relayStatus === "connected" ? "请求已接收，等待原聊天的实际回答。" : "请求已保存；普通 Chat 自动转发尚未接通。");
      } catch (error) { if (writeRejected(error)) { state.pending = null; persist(); } fail(error); }
      finally { state.busy = false; updateControls(); }
    }
    async function saveIdea() {
      if (state.busy || state.composing || !composerInput.value.trim() && !currentFiles().length && !(state.session?.draft?.attachmentIds || []).length) return;
      state.busy = true; updateControls(); const text = composerInput.value;
      try { if (draftSync) await draftSync; await ensureSession(); if (!state.pending) await uploadFiles(); const payload = durablePayload("mobile/dialogue/save", submission(), ["sessionId", "text", "requestedProfile"]), data = await call("mobile/dialogue/save", payload); state.pending = null; applyDialogue(data, payload.sessionId);
        if (composerInput.value === text) { composerInput.value = ""; state.drafts[payload.sessionId] = { text: "", tier: state.tier, unsynced: false }; state.dirty = false; autosize(composerInput); } persist(); say(offline ? "想法已保存在此手机。" : "想法已保存到电脑，随时可以接着聊。"); if (data.idea) state.idea = data.idea;
      } catch (error) { if (writeRejected(error)) { state.pending = null; persist(); } fail(error); } finally { state.busy = false; updateControls(); }
    }
    async function clearDiscussion() {
      if (state.busy) return;
      if (state.pending) { say("上一条操作是否送达还需要核对，暂不切换讨论；原草稿与请求编号保留。", true); return; }
      more.open = false; if (state.view !== "chat") return;
      state.busy = true; updateControls(); saveLocalDraft();
      try { if (draftSync) await draftSync; await ensureSession(); if (currentFiles().length) { fileOwner = state.session.id; await saveFiles(); } const data = await call("mobile/dialogue/clear", { requestId: uuid(), clientId: state.clientId, sessionId: state.session.id, expectedRevision: state.session.revision }); applyDialogue(data); state.messageIds.clear(); composerInput.value = ""; state.drafts[state.session.id] = { text: "", tier: state.tier, unsynced: false }; delete state.drafts.unopened; state.dirty = false; state.newResults = false; persist(); autosize(composerInput); renderView(); say("当前讨论已重新开始，保存的想法仍然保留。"); }
      catch (error) { fail(error); } finally { state.busy = false; updateControls(); }
    }
    async function rememberAnswer(sourceMessageId) {
      if (state.busy || !state.session) return; state.busy = true; updateControls();
      try { if (draftSync) await draftSync; const candidate = { requestId: uuid(), clientId: state.clientId, sessionId: state.session.id, expectedRevision: state.session.revision, sourceMessageId, ...(state.session.ideaId ? { ideaId: state.session.ideaId, expectedIdeaRevision: state.session.ideaRevision } : {}) }, payload = durablePayload("mobile/dialogue/remember", candidate, ["sessionId", "sourceMessageId", "ideaId"]); const data = await call("mobile/dialogue/remember", payload); state.pending = null; persist(); applyDialogue(data, payload.sessionId); say(payload.ideaId ? "已补充到此想法，原回答来源已保留。" : "已存为想法，原回答来源已保留。"); }
      catch (error) { if (writeRejected(error)) { state.pending = null; persist(); } fail(error); } finally { state.busy = false; updateControls(); }
    }
    async function refresh() {
      if (!state.active || state.reading) return; state.reading = true; const sequence = ++state.requestSequence, sessionId = state.session?.id || "";
      try { if (state.view === "ideas") await loadIdeas(); else if (["detail", "execution"].includes(state.view) && state.idea) await openIdea(state.idea.id, true); else { const data = await call(`mobile/dialogue?clientId=${encodeURIComponent(state.clientId)}`); if (sequence !== state.requestSequence) return; if (sessionId && data.session?.id !== sessionId && state.dirty) return; const localText = composerInput.value; applyDialogue(data, sessionId); if (!state.dirty) restoreDraft(); else composerInput.value = localText; } }
      catch (error) { fail(error); } finally { state.reading = false; updateControls(); }
    }
    async function showIdeas() { if (state.busy) return; if (state.view === "chat") { state.chatScroll = window.scrollY; saveLocalDraft(); void syncDraft(); } state.view = "ideas"; say(""); renderView(); await loadIdeas(); requestAnimationFrame(() => window.scrollTo({ top: state.listScroll, behavior: "auto" })); }
    async function loadIdeas() {
      const currentSearch = state.search, currentProject = state.project, archived = state.archived;
      try { const data = await call(`mobile/ideas?search=${encodeURIComponent(currentSearch)}&projectId=${encodeURIComponent(currentProject)}&archived=${archived ? "1" : "0"}`); if (currentSearch !== state.search || currentProject !== state.project || archived !== state.archived) return;
        state.ideas = Array.isArray(data.ideas) ? data.ideas : []; state.projects = Array.isArray(data.projects) ? data.projects : []; renderIdeas(); }
      catch (error) { fail(error); }
    }
    function renderIdeas() {
      project.replaceChildren(); for (const item of [{ id: "", name: "全部项目" }, { id: "unclassified", name: "未归类" }, ...state.projects]) { const option = make("option", item.name || item.label || item.id); option.value = item.id; project.append(option); } project.value = state.project;
      ideaList.replaceChildren(); archiveToggle.textContent = state.archived ? "返回未归档" : "查看归档"; title.textContent = state.archived ? "归档想法" : "想法";
      if (!state.ideas.length) ideaList.append(make("p", state.search ? "没有找到这条想法，试试别的词。" : state.archived ? "还没有归档的想法。" : "值得留下的念头，点「只保存」就会出现在这里。", "dialogue-empty"));
      for (const idea of state.ideas) { const row = button("", () => void openIdea(idea.id), "dialogue-idea-row"), meta = make("div", "", "dialogue-idea-meta"); row.append(make("h3", idea.title || "未命名想法"), make("p", String(idea.body || "").slice(0, 220), "dialogue-idea-preview")); meta.append(make("span", state.projects.find(item => item.id === idea.projectId)?.name || "未归类"), make("span", when(idea.updatedAt))); if (idea.archived) meta.append(make("span", "已归档", "dialogue-archive-label")); row.append(meta); ideaList.append(row); }
    }
    async function openIdea(id, refreshing = false) {
      if (!id || state.busy) return;
      const sequence = ++ideaSequence;
      if (!refreshing) { state.listScroll = window.scrollY; persist(); state.view = "detail"; say(""); renderView(); }
      try { const data = await call(`mobile/idea?id=${encodeURIComponent(id)}`); if (sequence !== ideaSequence || state.view === "chat" || state.view === "ideas") return; state.idea = data.idea; state.ideaDetail = data.detail || null; const local = state.editDrafts[id]; if (!state.editorDirty || !refreshing) { ideaTitle.value = local?.dirty ? local.title : data.idea?.title || ""; ideaBody.value = local?.dirty ? local.body : data.idea?.body || ""; state.editorDirty = Boolean(local?.dirty); } renderIdea(); if (!refreshing) window.scrollTo({ top: 0, behavior: "auto" }); }
      catch (error) { fail(error); }
    }
    function renderIdea() {
      const idea = state.idea; if (!idea) return; detailMeta.textContent = `${when(idea.updatedAt)} · ${state.projects.find(item => item.id === idea.projectId)?.name || "未归类"}${idea.archived ? " · 已归档" : ""}`; archiveIdea.textContent = idea.archived ? "取消归档" : "归档想法"; autosize(ideaBody, 12000); pointsList.replaceChildren();
      if (packUrl && (packIdeaId !== idea.id || packRevision !== idea.revision)) clearPack();
      const keyPoints = Array.isArray(idea.keyPoints) ? idea.keyPoints : []; points.hidden = !keyPoints.length;
      for (const point of keyPoints) { const row = make("div", "", "dialogue-point"), actions = make("div", "", "dialogue-point-actions"), pointText = make("p", point.text || ""); actions.append(make("span", point.kind === "decision" ? "你确认的决定" : "待确认的建议"), button(point.kind === "decision" ? "改为建议" : "确认为决定", () => void changePointKind(idea.id, point.id, point.kind === "decision" ? "suggestion" : "decision")), button("编辑", () => editPoint(idea.id, point, row)), button("删除", () => void updateIdea({ keyPoints: keyPoints.filter(item => item.id !== point.id).map(pointInput) }, idea.id))); row.append(pointText, actions); pointsList.append(row); }
      detailAttachments.replaceChildren(); for (const attachment of state.ideaDetail?.attachments || []) { const source = attachment.url || attachment.href; if (!source || !/^image\//.test(attachment.mimeType || attachment.mime || "")) continue; try { const url = new URL(source, window.location.href); if (url.origin !== location.origin) continue; const image = make("img"); image.src = url.href; image.alt = attachment.name || "想法图片"; detailAttachments.append(image); } catch { /* An invalid attachment address is not rendered. */ } } updateControls();
    }
    function pointInput(item) { return { id: item.id, text: item.text, kind: item.kind }; }
    async function changePointKind(ideaId, pointId, kind) {
      if (state.busy || state.view !== "detail" || state.idea?.id !== ideaId) return false;
      const keyPoints = Array.isArray(state.idea.keyPoints) ? state.idea.keyPoints : [], point = keyPoints.find(item => item.id === pointId);
      if (!point || point.kind === kind) return false;
      return updateIdea({ keyPoints: keyPoints.map(item => pointInput(item.id === pointId ? { ...item, kind } : item)) }, ideaId);
    }
    function editPoint(ideaId, point, row) { if (state.idea?.id !== ideaId) return; const editor = field("textarea", "编辑长期要点", "dialogue-keypoint-editor"), actions = make("div", "", "dialogue-detail-actions"); editor.value = point.text || ""; actions.append(button("保存要点", () => { if (state.idea?.id === ideaId) void updateIdea({ keyPoints: state.idea.keyPoints.map(item => pointInput(item.id === point.id ? { ...item, text: editor.value } : item)) }, ideaId); }), button("取消", () => renderIdea())); row.replaceChildren(editor, actions); }
    async function updateIdea(extra = null, expectedIdeaId = null) {
      if (state.busy || !state.idea || expectedIdeaId && state.idea.id !== expectedIdeaId) return false; state.busy = true; updateControls(); const id = state.idea.id;
      try { const data = await call("mobile/idea/update", { requestId: uuid(), id, expectedRevision: state.idea.revision, ...(extra || { title: ideaTitle.value, body: ideaBody.value }) }); state.idea = data.idea || state.idea; if (!extra) { state.editorDirty = false; state.editDrafts[id] = { ...(state.editDrafts[id] || {}), title: ideaTitle.value, body: ideaBody.value, dirty: false }; } else if (extra.executionDraft !== undefined) state.editDrafts[id] = { ...(state.editDrafts[id] || {}), executionDraft: extra.executionDraft }; persist(); renderIdea(); say(extra?.executionDraft !== undefined ? "执行稿已保存，尚未交给 Codex。" : "修改已保存。"); return true; }
      catch (error) { fail(error); return false; } finally { state.busy = false; updateControls(); }
    }
    async function archiveCurrent() {
      if (state.busy || !state.idea || state.editorDirty) { if (state.editorDirty) say("先保存当前修改，再归档。"); return; } state.busy = true; updateControls();
      try { const data = await call("mobile/idea/archive", { requestId: uuid(), id: state.idea.id, expectedRevision: state.idea.revision, archived: !state.idea.archived }); state.idea = data.idea || state.idea; ideaMore.open = false; renderIdea(); say(state.idea.archived ? "已归档，内容和附件仍然保留。" : "已恢复到想法列表。"); }
      catch (error) { fail(error); } finally { state.busy = false; updateControls(); }
    }
    async function openIdeaDiscussion() {
      if (state.busy || !state.idea || state.editorDirty) return; state.busy = true; updateControls();
      if (state.pending) { state.busy = false; updateControls(); say("上一条操作是否送达还需要核对，暂不切换讨论；原草稿与请求编号保留。", true); return; }
      try { if (draftSync) await draftSync; saveLocalDraft(); const data = await call("mobile/dialogue/open", { requestId: uuid(), clientId: state.clientId, ideaId: state.idea.id, expectedIdeaRevision: state.idea.revision }); state.messageIds.clear(); applyDialogue(data); state.view = "chat"; restoreDraft(); renderView(); say(""); window.scrollTo({ top: 0, behavior: "auto" }); }
      catch (error) { fail(error); } finally { state.busy = false; updateControls(); }
    }
    function showExecutionDraft() { if (!state.idea || state.editorDirty) return; state.view = "execution"; executionText.value = state.editDrafts[state.idea.id]?.executionDraft ?? (state.idea.executionDraft || state.idea.body || ""); renderView(); autosize(executionText, 12000); window.scrollTo({ top: 0, behavior: "auto" }); }
    function clearPack() { if (packUrl) URL.revokeObjectURL?.(packUrl); packUrl = ""; packIdeaId = ""; packRevision = 0; packLink.hidden = true; packLink.removeAttribute?.("href"); }
    async function exportPack() {
      if (!offline || !state.idea || state.busy || state.editorDirty) { if (state.editorDirty) say("先保存当前修改，再导出完整想法包。"); return; }
      const idea = { id: state.idea.id, revision: state.idea.revision }; state.busy = true; updateControls();
      try { const result = await options.onExportPack(idea); if (!(result?.blob instanceof Blob) || !URL.createObjectURL) throw new Error("完整想法包尚未生成，手机副本保留。"); clearPack(); packUrl = URL.createObjectURL(result.blob); packIdeaId = idea.id; packRevision = idea.revision; packLink.href = packUrl; packLink.download = result.fileName || "想法.console-idea"; packLink.textContent = `保存 v${idea.revision} 完整想法包`; packLink.hidden = false; say("完整想法包已生成；点保存链接后在系统中保存，再到电脑更多里导入。手机原副本保留。"); }
      catch (error) { fail(error); } finally { state.busy = false; updateControls(); }
    }
    async function handoffIdea(reservation = null, retryPending = false) {
      if (!offline || !state.idea || state.busy || state.editorDirty && !retryPending) return false;
      const ideaId = state.idea.id, revision = state.idea.revision;
      try {
        // Reserve inside the original tap, before any IndexedDB or network await.
        reservation ||= options.onHandoffReserve?.(); if (!reservation || !options.onHandoff) throw new Error("交接入口尚未准备好，内容仍在此手机。");
        state.busy = true; updateControls(); say("正在核对已保存版本与图片，手机原副本保留…");
        await options.onHandoff(reservation, { id: ideaId, revision, retryPending }); say(retryPending ? "上次版本已核对，当前修改仍在手机；带到电脑会使用当前已保存版本。" : "电脑已确认导入这条想法；手机原副本保留。到电脑核对工作区后才执行。"); return true;
      } catch (error) { fail(error); return false; } finally { state.busy = false; updateControls(); }
    }
    async function handToCodex() {
      if (!state.idea || state.busy || !executionText.value.trim()) return;
      if (offline) {
        let reservation; try { reservation = options.onHandoffReserve?.(); if (!reservation) throw new Error("先连接电脑；执行稿仍保存在此手机。"); } catch (error) { fail(error); return; }
        if (executionText.value !== (state.idea.executionDraft || "") && !await updateIdea({ executionDraft: executionText.value })) { reservation.popup?.close?.(); return; }
        await handoffIdea(reservation); return;
      }
      if (executionText.value !== (state.idea.executionDraft || "")) { if (!await updateIdea({ executionDraft: executionText.value })) return; }
      const result = await options.onExecution?.({ ...state.idea, ideaId: state.idea.id, executionDraft: executionText.value }); if (result === false) say("工作区暂时无法打开，执行稿已保留。", true);
    }
    async function goBack() { if (state.busy) return; if (state.view === "execution") { state.view = "detail"; renderView(); return; } if (state.view === "detail") { if (state.editorDirty) persistEditor(); state.view = "ideas"; renderView(); await loadIdeas(); requestAnimationFrame(() => window.scrollTo({ top: state.listScroll, behavior: "auto" })); } else { state.listScroll = window.scrollY; persist(); state.view = "chat"; renderView(); requestAnimationFrame(() => window.scrollTo({ top: state.chatScroll, behavior: "auto" })); } }
    function persistEditor() { if (!state.idea) return; state.editDrafts[state.idea.id] = { ...(state.editDrafts[state.idea.id] || {}), title: ideaTitle.value, body: ideaBody.value, dirty: true }; state.editorDirty = true; persist(); autosize(ideaBody, 12000); updateControls(); }
    function openModule(module) { saveLocalDraft(); void syncDraft(); options.onModule?.(module); }
    async function copyText(text) { try { if (!navigator.clipboard?.writeText) throw new Error("请长按内容选择并复制。"); await navigator.clipboard.writeText(text); say("已复制。"); } catch (error) { fail(error); } }
    composer.addEventListener("submit", event => event.preventDefault());
    packInput.addEventListener("change", async () => { const file = packInput.files?.[0]; packInput.value = ""; if (!file || state.busy || !options.onImportPack) return; state.busy = true; updateControls(); try { const receipt = await options.onImportPack(file); if (!receipt?.imported?.ideaId) throw new Error("导入回执无法核对，原资料保留。"); state.busy = false; await openIdea(receipt.imported.ideaId); say("这条手机想法已导入，手机原副本保留；尚未发送或执行。"); } catch (error) { fail(error); } finally { state.busy = false; updateControls(); } });
    imageInput.addEventListener("change", async () => {
      const chosen = Array.from(imageInput.files || []); imageInput.value = ""; if (state.busy || !chosen.length) return;
      if (chosen.some(item => !/^image\//.test(item.type)) || currentFiles().length + chosen.length > 4 || [...currentFiles(), ...chosen].reduce((sum, item) => sum + item.size, 0) > 24 * 1024 * 1024) { say("一次最多保留 4 张图片，总共不超过 24 MB。", true); return; }
      state.busy = true; updateControls();
      try { if (draftSync) await draftSync; if (fileReading) await fileReading; await ensureSession(); if (fileOwner && fileOwner !== state.session?.id && files.length) { await writeFiles({ id: `${filesKey}:${fileOwner}`, files, uploadRequest, fileOwner }); files = []; uploadRequest = null; } fileOwner = state.session.id; files.push(...chosen); renderFiles(); await saveFiles(); say("图片草稿已保存在此手机；只保存不会发送。"); }
      catch (error) { fileError = true; fail(error); } finally { state.busy = false; updateControls(); }
    });
    composerInput.addEventListener("input", () => { saveLocalDraft(); window.clearTimeout(draftTimer); draftTimer = window.setTimeout(() => void syncDraft(), 800); }); composerInput.addEventListener("compositionstart", () => { state.composing = true; updateControls(); }); composerInput.addEventListener("compositionend", () => { state.composing = false; saveLocalDraft(); });
    composerInput.addEventListener("keydown", event => { if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !event.isComposing && !state.composing) { event.preventDefault(); void sendMessage(); } });
    tier.addEventListener("change", () => { state.tier = tier.value; saved.tier = state.tier; saveLocalDraft(); void syncDraft(); });
    ideaTitle.addEventListener("input", persistEditor); ideaBody.addEventListener("input", persistEditor); executionText.addEventListener("input", () => { if (state.idea) { state.editDrafts[state.idea.id] = { ...(state.editDrafts[state.idea.id] || {}), executionDraft: executionText.value }; persist(); } autosize(executionText, 12000); updateControls(); });
    search.addEventListener("input", () => { state.search = search.value; state.listScroll = 0; persist(); void loadIdeas(); }); project.addEventListener("change", () => { state.project = project.value; state.listScroll = 0; persist(); void loadIdeas(); });
    window.addEventListener("pagehide", () => { saveLocalDraft(); if (state.editorDirty) persistEditor(); });
    const viewport = () => { const value = window.visualViewport?.height || window.innerHeight; root.style.setProperty("--dialogue-viewport", `${value}px`); }; window.visualViewport?.addEventListener("resize", viewport); window.addEventListener("resize", viewport); viewport();
    document.addEventListener("visibilitychange", () => { if (!document.hidden && state.active) void refresh(); else if (document.hidden) saveLocalDraft(); });
    window.addEventListener("online", () => { if (state.active) void refresh(); });
    window.addEventListener("codex:dialogue-result", event => { if (state.active && event.detail?.sessionId === state.session?.id) void refresh(); });
    persist(); restoreDraft(); renderCapability(); renderView();
    fileReading = blobs.get(filesKey).then(value => { if (value?.files) { files = value.files; fileOwner = value.fileOwner || null; uploadRequest = value.uploadRequest || null; renderFiles(); } }).catch(() => { /* No claim of file recovery is made without a readable store. */ }).finally(() => { fileReading = null; });
    return { setActive(value) { const changed = state.active !== Boolean(value); state.active = Boolean(value); if (state.active && changed) { root.hidden = false; void refresh(); } else if (!state.active) { saveLocalDraft(); more.open = false; } }, refresh, hasDraft() { return state.busy || fileReading || fileWriting || fileError || currentFiles().length > 0 || state.dirty && Boolean(composerInput.value.trim()) || state.editorDirty || Boolean(state.pending); }, canReload() { return !state.busy && !draftSync && !fileReading && !fileWriting && !fileError && !state.storageFailed && !state.composing; }, async prepareReload() { saveLocalDraft(); if (state.editorDirty) persistEditor(); return !state.storageFailed && !state.busy && !draftSync && !fileReading && !fileWriting && !fileError; }, clear() { state.generation += 1; window.clearTimeout(draftTimer); controllers.forEach(item => item.abort()); controllers.clear(); state.active = false; state.session = state.detail = state.idea = state.ideaDetail = null; state.ideas = []; state.messageIds.clear(); messages.replaceChildren(); ideaList.replaceChildren(); detailAttachments.replaceChildren(); root.hidden = true; }, openIdea, showIdeas };
  }
  window.CodexMobileDialogue = Object.freeze({ create });
})();
