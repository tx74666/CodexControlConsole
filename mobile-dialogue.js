(() => {
  "use strict";
  const make = (tag, text = "", className = "") => { const node = document.createElement(tag); node.textContent = text; node.className = className; return node; };
  const uuid = () => globalThis.crypto?.randomUUID?.() || "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, value => { const n = Math.floor(Math.random() * 16); return (value === "x" ? n : (n & 3) | 8).toString(16); });
  const button = (text, action, className = "") => { const node = make("button", text, className); node.type = "button"; node.addEventListener("click", action); return node; };
  const field = (tag, label, className = "") => { const node = make(tag, "", className); node.setAttribute("aria-label", label); return node; };
  const tiers = [{ id: "fast", label: "极速" }, { id: "high", label: "高" }, { id: "pro", label: "Pro" }];
  const profileReasoning = { fast: { mode: "standard", effort: "low" }, high: { mode: "standard", effort: "high" }, pro: { mode: "pro", effort: "high" } };
  const when = value => { const date = new Date(value || ""); return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" }); };
  const savedTime = value => {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return "时间未记录";
    const date = new Date(value); if (Number.isNaN(date.getTime())) return "时间未记录";
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).formatToParts(date).map(item => [item.type, item.value]));
    return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}（UTC+08:00）`;
  };
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
    const pointDrafts = Object.fromEntries(Object.entries(saved.pointDrafts || {}).filter(([id, value]) => value && value.ideaId === id && typeof value.pointId === "string" && Number.isSafeInteger(value.sourceRevision) && value.sourceRevision > 0 && ["sourceText", "text"].every(key => typeof value[key] === "string") && ["sourceKind", "kind"].every(key => ["suggestion", "decision"].includes(value[key]))));
    const state = { active: false, generation: 0, reading: false, busy: false, clientId: typeof saved.clientId === "string" ? saved.clientId : uuid(), session: null, detail: null, execution: null, tier: tiers.some(item => item.id === saved.tier) ? saved.tier : "high", chatTransport: saved.chatTransport === "chatgpt_subscription" ? "chatgpt_subscription" : "browser_chat", subscription: subscriptionChoice(saved.subscription), subscriptionStatus: null, subscriptionReading: false, drafts: saved.drafts && typeof saved.drafts === "object" ? saved.drafts : {}, editDrafts: saved.editDrafts && typeof saved.editDrafts === "object" ? saved.editDrafts : {}, pending: saved.pending || null, management: null, manageDirty: false, view: "chat", ideas: [], projects: [], idea: null, ideaDetail: null, search: saved.search || "", project: saved.project || "", archived: false, listScroll: Number(saved.listScroll) || 0, chatScroll: 0, messageIds: new Set(), storageFailed: false, composing: false, dirty: false, editorDirty: false, newResults: false, requestSequence: 0 };
    const controllers = new Set();
    let eligibleAttachments = [], cancelPendingButton = null;
    state.pointDrafts = pointDrafts;
    let pointEditor = null;
    const editComposing = { body: false, execution: false };
    let draftSync = null, draftTimer = 0, ideaSequence = 0, managementSequence = 0, files = [], fileOwner = null, fileError = false, fileReading = null, fileWriting = 0, uploadRequest = null, packUrl = "", packIdeaId = "", packRevision = 0;
    let resultStream = null, resultEpoch = 0, resultKey = "", resultCursor = "", resultPending = null, resultDraining = false, resultStopped = false, resultTransition = false, pageClosed = false;
    const blobs = options.blobStore || options.assetStore || fileStore(), filesKey = `${storageKey}:files:${state.clientId}`, filePreviews = [], imageRemovalButtons = [];
    const top = make("header", "", "dialogue-top"), topLeft = make("div", "", "dialogue-top-left"), topActions = make("div", "", "dialogue-top-actions"), title = make("h2", "对话", "dialogue-title");
    const back = button("‹ 返回", () => void goBack(), "dialogue-back"), ideasButton = button("想法", () => void showIdeas());
    const more = make("details", "", "dialogue-more"), summary = make("summary", "更多"), menu = make("div", "", "dialogue-menu"), menuMeta = make("p", "", "dialogue-menu-meta");
    const clearMenuAction = button("清空当前讨论", () => { more.open = false; void clearDiscussion(); }); menu.append(clearMenuAction);
    for (const item of [{ label: "刷新当前页面", action: () => void refresh() }, { label: "Work · 执行进度", action: () => openModule("workflow") }, { label: "Transfer · 互传", action: () => openModule("transfer") }, { label: "音乐", action: () => openModule("music") }, { label: "资料", action: () => openModule("documents") }, { label: offline ? "连接电脑继续" : "Projects / Recents", action: () => offline ? options.onConnect?.() : openModule("conversations") }, { label: "原工作区与导入", action: () => openModule("legacy") }]) menu.append(button(item.label, () => { more.open = false; item.action(); }));
    const chatTransport = field("select", "讨论通道", "dialogue-channel"), connectionNote = make("p", "", "dialogue-source-note");
    for (const choice of [{ id: "browser_chat", name: "浏览器普通 Chat" }, { id: "chatgpt_subscription", name: "ChatGPT 订阅" }]) { const item = make("option", choice.name); item.value = choice.id; chatTransport.append(item); }
    chatTransport.value = state.chatTransport;
    const checkConnection = button("查看订阅连接", () => void readSubscriptionStatus(true));
    menu.append(make("hr"), make("label", "讨论通道"), chatTransport, checkConnection, connectionNote, menuMeta); more.append(summary, menu); topLeft.append(back, title); topActions.append(ideasButton, more); top.append(topLeft, topActions);
    if (offline) menu.insertBefore(button("资料与更新", () => openModule("settings")), menuMeta);
    const packInput = field("input", "导入手机想法包"); packInput.type = "file"; packInput.accept = ".console-idea,application/json"; packInput.hidden = true;
    if (!offline && options.onImportPack) { menu.insertBefore(button("导入手机想法包", () => packInput.click()), menuMeta); menu.append(packInput); }
    const notice = make("p", "", "dialogue-notice"); notice.setAttribute("role", "status"); notice.setAttribute("aria-live", "polite");
    const content = make("main", "", "dialogue-content"), context = make("div", "", "dialogue-context"), contextText = make("span"), contextOpen = button("查看想法", () => void openIdea(state.session?.ideaId)); context.append(contextText, contextOpen);
    const welcome = make("div", "", "dialogue-welcome"); welcome.append(make("div", "✧", "dialogue-welcome-mark"), make("h2", "脑子里的想法，\n从这里开始。"), make("p", "直接问一句，或先记下来。\n还没想清楚，也可以慢慢聊。"));
    const suggestions = make("div", "", "dialogue-suggestions"); suggestions.append(button("先记一个念头", () => { composerInput.placeholder = "记下这个念头，以后接着想…"; composerInput.focus(); }), button("找以前的想法", () => void showIdeas())); welcome.append(suggestions);
    const messages = make("div", "", "dialogue-messages"), pending = make("div", "", "dialogue-pending"), pendingText = make("span"); pending.setAttribute("role", "status"); pending.setAttribute("aria-live", "polite"); pending.append(pendingText);
    const listView = make("section", "", "dialogue-list-view"), listTools = make("div", "", "dialogue-list-tools"), search = field("input", "搜索想法"), project = field("select", "按项目筛选"), ideaList = make("div", "", "dialogue-ideas-list"), listFooter = make("div", "", "dialogue-list-footer"), archiveToggle = button("查看归档", () => { state.archived = !state.archived; void loadIdeas(); });
    search.type = "search"; search.placeholder = "搜索想法"; search.value = state.search; listTools.append(search, project); listFooter.append(archiveToggle); listView.append(listTools, ideaList, listFooter);
    const detailView = make("section", "", "dialogue-detail-view"), detailHeading = make("div", "", "dialogue-detail-heading"), ideaTitle = field("input", "想法标题", "dialogue-detail-title"), detailMeta = make("p", "", "dialogue-detail-meta"), ideaBody = field("textarea", "想法内容", "dialogue-detail-body"); ideaTitle.maxLength = 240; ideaBody.rows = 5; detailHeading.append(ideaTitle, detailMeta);
    const detailActions = make("div", "", "dialogue-detail-actions"), saveEdit = button("保存修改", () => void updateIdea(), "dialogue-primary"), discussIdea = button("继续讨论", () => void openIdeaDiscussion(), "dialogue-primary"), executionDraft = button("执行稿", () => showExecutionDraft()), ideaMore = make("details", "", "dialogue-more"), ideaMenu = make("div", "", "dialogue-menu"), ideaMenuSummary = make("summary", "更多");
    for (const item of [{ label: "移动到项目", kind: "move" }, { label: "拆分选中内容", kind: "split" }, { label: "合并另一条想法", kind: "merge" }]) ideaMenu.append(button(item.label, () => void openManagement(item.kind)));
    const retryManagement = button("重试上次整理", () => void openManagement("retry")); retryManagement.hidden = true; ideaMenu.append(retryManagement);
    const archiveIdea = button("归档想法", () => void archiveCurrent()), copyIdea = button("复制内容", () => void copyText(`${ideaTitle.value}\n\n${ideaBody.value}`)), carryIdea = button("带到电脑", () => void handoffIdea(), "dialogue-primary"), packLink = make("a", "保存想法包"); packLink.hidden = true; ideaMenu.append(copyIdea, archiveIdea); if (offline && options.onHandoff) ideaMenu.append(button("核对上次交接", () => void handoffIdea(null, true))); if (offline && options.onExportPack) ideaMenu.append(button("导出完整想法包", () => void exportPack()), packLink); ideaMore.append(ideaMenuSummary, ideaMenu); detailActions.append(saveEdit, discussIdea, executionDraft); if (offline && options.onHandoff) detailActions.append(carryIdea); detailActions.append(ideaMore);
    const managementView = make("section", "", "dialogue-management"), managementTitle = make("h3"), managementSource = make("p", "", "dialogue-source-note"), managementFields = make("div", "", "dialogue-management-fields"), managementPreview = make("div", "", "dialogue-management-preview"), managementActions = make("div", "", "dialogue-detail-actions"), managementSubmit = button("保存", () => void submitManagement(), "dialogue-primary"), managementCancel = button("取消", () => closeManagement()); managementView.hidden = true; managementActions.append(managementSubmit, managementCancel); managementView.append(managementTitle, managementSource, managementFields, managementPreview, managementActions);
    const bodyDraftReview = make("section", "", "dialogue-detail-section"), executionDraftReview = make("section", "", "dialogue-detail-section"); bodyDraftReview.hidden = executionDraftReview.hidden = true;
    const detailAttachments = make("div", "", "dialogue-attachment-grid"), points = make("section", "", "dialogue-detail-section"), pointsTitle = make("h3", "长期要点"), pointsList = make("div"); points.append(pointsTitle, pointsList); detailView.append(detailHeading, ideaBody, bodyDraftReview, detailAttachments, detailActions, managementView, points);
    const executionView = make("section", "", "dialogue-execution-view"), executionText = field("textarea", "执行稿", "dialogue-keypoint-editor"), saveExecution = button("保存执行稿", () => void updateIdea({ executionDraft: executionText.value }), "dialogue-primary"), handover = button("交给 Codex", () => void handToCodex(), "dialogue-primary"), executionActions = make("div", "", "dialogue-detail-actions"); executionText.rows = 12; executionActions.append(saveExecution, handover); executionView.append(make("h3", "准备好以后再执行"), make("p", "整理本轮想改什么、预期结果与范围。下一步集中核对 Codex 工作区后再确认执行。", "dialogue-source-note"), executionText, executionDraftReview, executionActions);
    content.append(context, welcome, messages, pending, listView, detailView, executionView);
    const newResult = button("有新回复 ↓", () => { state.newResults = false; newResult.hidden = true; window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" }); }, "dialogue-new-result");
    const composer = make("form", "", "dialogue-composer"), shell = make("div", "", "dialogue-composer-shell"), composerInput = field("textarea", "提问或保存想法"), composeActions = make("div", "", "dialogue-compose-actions"), composeLeft = make("div", "", "dialogue-compose-left"), composeRight = make("div", "", "dialogue-compose-right"), tier = field("select", "回答档位", "dialogue-tier");
    composerInput.placeholder = "想问什么，或先记下来…"; composerInput.rows = 1; composerInput.maxLength = 20000;
    for (const choice of tiers) { const option = make("option", choice.label); option.value = choice.id; tier.append(option); } tier.value = state.tier;
    const saveOnly = button("只保存", () => void saveIdea()), send = button("发送 ↑", () => void sendMessage(), "dialogue-send"), attach = button("＋", () => imageInput.click()), imageInput = field("input", "选择图片文件"), pendingImages = make("div", "", "dialogue-attachment-grid"); attach.setAttribute("aria-label", "添加图片"); imageInput.type = "file"; imageInput.accept = "image/jpeg,image/png,image/webp,image/gif,image/heic,image/heif"; imageInput.multiple = true; imageInput.hidden = true;
    const status = make("div", "", "dialogue-status"), draftStatus = make("p"), capabilityStatus = make("p"); status.setAttribute("role", "status"); status.append(draftStatus, capabilityStatus); composeLeft.append(attach, tier); composeRight.append(saveOnly, send); composeActions.append(composeLeft, composeRight); shell.append(pendingImages, composerInput, composeActions, imageInput); composer.append(shell, status); root.classList.add("mobile-dialogue"); root.replaceChildren(top, notice, content, newResult, composer);
    const savedImagePicker = make("details", "", "dialogue-saved-image-picker"), savedImageChoices = make("div", "", "dialogue-attachment-grid"); savedImagePicker.append(make("summary", "已保存图片"), make("p", "选择本次引用的图片；未选择的图片不会发送。", "dialogue-source-note"), savedImageChoices); savedImagePicker.hidden = true; shell.insertBefore(savedImagePicker, composerInput);
    const modelRow = make("div", "", "dialogue-model-row"), modelLabel = make("label", "模型"), subscriptionModel = field("select", "ChatGPT 订阅实际模型", "dialogue-model"), modelFeedback = make("p", "", "dialogue-model-feedback"), modelCheck = button("查看模型状态", () => void readSubscriptionStatus(true), "dialogue-model-check"); modelFeedback.setAttribute("role", "status"); modelFeedback.setAttribute("aria-live", "polite"); modelRow.append(modelLabel, subscriptionModel, modelFeedback, modelCheck); shell.insertBefore(modelRow, composeActions);
    document.addEventListener("pointerdown", event => { if (!state.active) return; for (const popup of [more, ideaMore, savedImagePicker]) if (popup.open && !popup.contains(event.target)) popup.open = false; }, { capture: true });
    const storageFailureNotice = "这台手机暂时无法保存草稿，请保留页面并复制内容。";
    const acceptedSendNotices = ["请求已接收，等待原聊天的实际回答。", "请求已保存；普通 Chat 自动转发尚未接通。", "请求已接收，等待本轮真实回答；接收不等于完成。"];
    function persist() {
      const recovering = state.storageFailed;
      try { localStorage.setItem(storageKey, JSON.stringify({ clientId: state.clientId, tier: state.tier, chatTransport: state.chatTransport, subscription: state.subscription, drafts: state.drafts, editDrafts: state.editDrafts, pointDrafts: state.pointDrafts, pending: state.pending, search: state.search, project: state.project, listScroll: state.listScroll })); state.storageFailed = false; if (recovering && notice.textContent === storageFailureNotice) say(); renderDraftStatus(); return true; }
      catch { state.storageFailed = true; renderDraftStatus(); say(storageFailureNotice, true); return false; }
    }
    function say(text = "", error = false) { notice.textContent = text; notice.dataset.error = String(error); }
    function autosize(input, limit = 170) { input.style.height = "auto"; input.style.height = `${Math.min(limit, Math.max(48, input.scrollHeight || 48))}px`; input.style.overflowY = input.scrollHeight > limit ? "auto" : "hidden"; }
    function draftKey() { return state.session?.id || "unopened"; }
    function renderDraftStatus() {
      draftStatus.textContent = state.storageFailed ? !offline && state.session && !state.dirty ? "草稿已同步电脑；本机保存失败" : "草稿尚未保存在此手机" : offline ? state.session || state.dirty ? "草稿已保存在此手机" : "只保存留在此手机" : state.dirty ? "草稿已保存在此手机" : state.session ? "草稿已同步电脑" : "";
    }
    function saveLocalDraft(userEdited = false) {
      const local = state.drafts[draftKey()];
      // Capturing a blank page before its session loads is not an edit or a clear.
      if (!state.session && !userEdited && !composerInput.value && local?.userEdited !== true) return !state.storageFailed;
      state.drafts[draftKey()] = { text: composerInput.value, tier: state.tier, chatTransport: state.chatTransport, subscription: state.subscription, updatedAt: new Date().toISOString(), unsynced: true, ...(!state.session ? { waitingForSession: true, ...(userEdited || local?.userEdited === true ? { userEdited: true } : {}) } : {}) }; state.dirty = true; const stored = persist(); autosize(composerInput); updateControls(); return stored;
    }
    function restoreDraft() { const local = state.drafts[draftKey()], localDirty = Boolean(local?.unsynced && (state.session || local.userEdited === true || local.text)); composerInput.value = localDirty ? local.text || "" : state.session?.draft?.text ?? local?.text ?? ""; state.dirty = localDirty; autosize(composerInput); renderDraftStatus(); }
    function subscriptionChoice(value) {
      const keys = ["provider", "connectionId", "catalogRevision", "modelSlug"];
      const explicit = value && Object.keys(value).sort().join(",") === [...keys, "requestedProfile", "reasoning"].sort().join(",");
      if (!value || !explicit && Object.keys(value).sort().join(",") !== keys.slice().sort().join(",") || value.provider !== "chatgpt_subscription" || keys.slice(1).some(key => typeof value[key] !== "string" || !value[key] || value[key].length > 200 || /[\u0000-\u001f]/.test(value[key]))) return null;
      const selected = Object.fromEntries(keys.map(key => [key, value[key]]));
      if (explicit) { if (!reasoningMatches(value.reasoning, value.requestedProfile)) return null; selected.requestedProfile = value.requestedProfile; selected.reasoning = { ...profileReasoning[value.requestedProfile] }; }
      return selected;
    }
    function reasoningMatches(value, profile) { const expected = Object.hasOwn(profileReasoning, profile) && profileReasoning[profile]; return Boolean(expected && value && Object.keys(value).sort().join(",") === "effort,mode" && value.mode === expected.mode && value.effort === expected.effort); }
    function sameSubscription(left, right) { const a = subscriptionChoice(left), b = subscriptionChoice(right); return Boolean(a && b && JSON.stringify(a) === JSON.stringify(b)); }
    function reasoningLabel(profile) { const value = profileReasoning[profile]; return `${value.mode === "pro" ? "Pro 模式" : "标准模式"} · ${value.effort}`; }
    function safeSubscriptionStatus(value) {
      if (!value || typeof value.connected !== "boolean" || typeof value.busy !== "boolean" || !Array.isArray(value.models) || value.models.length > 1000 || value.models.some(item => !item || typeof item.slug !== "string" || !item.slug || item.slug.length > 200 || /[\u0000-\u001f]/.test(item.slug) || typeof item.displayName !== "string" || !item.displayName || item.displayName.length > 300) || new Set(value.models.map(item => item.slug)).size !== value.models.length || value.connected && [value.connectionId, value.catalogRevision].some(item => typeof item !== "string" || !item || item.length > 200 || /[\u0000-\u001f]/.test(item))) return { connected: false, busy: false, models: [], status: "invalid", error: "订阅连接状态尚未核实，请在电脑检查连接。" };
      const mappings = {};
      for (const { id } of tiers) { const item = value.profileMappings && Object.hasOwn(value.profileMappings, id) && value.profileMappings[id]; if (item && Object.keys(item).sort().join(",") === "actualProfileVerified,available,modelSlugs,reasoning" && reasoningMatches(item.reasoning, id) && item.actualProfileVerified === false && typeof item.available === "boolean" && Array.isArray(item.modelSlugs) && item.modelSlugs.length <= value.models.length && new Set(item.modelSlugs).size === item.modelSlugs.length && item.modelSlugs.every(slug => value.models.some(model => model.slug === slug))) mappings[id] = { reasoning: { ...profileReasoning[id] }, modelSlugs: [...item.modelSlugs], available: item.available, actualProfileVerified: false }; }
      return { connected: value.connected, busy: value.busy, connectionId: value.connectionId, catalogRevision: value.catalogRevision, models: value.models.map(item => ({ slug: item.slug, displayName: item.displayName })), profileMappings: mappings, status: typeof value.status === "string" ? value.status : "unknown", error: typeof value.error === "string" ? value.error.slice(0, 1000) : "" };
    }
    function subscriptionProfileIssue() {
      const catalog = state.subscriptionStatus, selected = state.subscription, label = tiers.find(item => item.id === state.tier).label;
      if (!catalog?.connected) return subscriptionCatalogMessage();
      if (!selected) return "请选择实际模型后发送。";
      if (selected.connectionId !== catalog.connectionId || selected.catalogRevision !== catalog.catalogRevision || !catalog.models.some(item => item.slug === selected.modelSlug)) return "模型目录或连接已变化，请重新选择实际模型；不会降档发送。";
      const mapping = catalog.profileMappings?.[state.tier];
      if (!mapping?.available || !mapping.modelSlugs.includes(selected.modelSlug)) return `当前模型尚不支持「${label}」请求；请选择受支持的模型，原档位保留。`;
      if (!selected.requestedProfile) return "原模型选择尚未绑定档位，请明确重选档位或模型后发送。";
      if (selected.requestedProfile !== state.tier || !reasoningMatches(selected.reasoning, state.tier)) return "模型与当前档位尚未绑定，请明确重选档位或模型；不会降档发送。";
      return "";
    }
    function subscriptionCatalogMessage() {
      const catalog = state.subscriptionStatus;
      if (offline) return "请先连接电脑，原文字、选图与档位保留。";
      if (state.subscriptionReading) return "正在读取电脑保存的模型状态，请稍候；不会发送消息。";
      if (!catalog) return "模型状态尚未读取，请查看模型状态；原草稿保留。";
      if (catalog.status === "catalog_loading") return "电脑正在恢复模型目录，完成后请查看模型状态；不会自动发送。";
      if (catalog.status === "catalog_required") return "电脑连接已恢复，模型目录尚未准备好；请在电脑查看订阅连接并读取模型目录，再查看模型状态。";
      if (catalog.status === "catalog_failed") return "电脑读取模型目录未完成，请在电脑查看连接原因，再查看模型状态；原选择与草稿保留。";
      if (["reauth_required", "expired"].includes(catalog.status)) return "订阅登录需要在电脑重新核对；原模型、档位和草稿保留。";
      if (catalog.status === "signing_in") return "正在等待电脑完成登录回调，模型暂不可选。";
      if (catalog.connected && !catalog.models.length) return "模型目录尚未准备好，请在电脑读取模型目录后查看模型状态。";
      return "订阅连接或模型目录暂不可用，请在电脑查看连接；原草稿保留。";
    }
    function chooseSubscriptionModel(modelSlug) {
      const catalog = state.subscriptionStatus; if (!catalog?.connected || !catalog.models.some(item => item.slug === modelSlug)) return null;
      const selected = { provider: "chatgpt_subscription", connectionId: catalog.connectionId, catalogRevision: catalog.catalogRevision, modelSlug }, mapping = catalog.profileMappings?.[state.tier];
      return mapping?.available && mapping.modelSlugs.includes(modelSlug) ? { ...selected, requestedProfile: state.tier, reasoning: { ...mapping.reasoning } } : selected;
    }
    function subscriptionReady() {
      const status = state.subscriptionStatus, selected = state.subscription;
      return !offline && status?.connected === true && !status.busy && !state.subscriptionReading && selected && !subscriptionProfileIssue();
    }
    function renderSubscription() {
      const selected = state.chatTransport === "chatgpt_subscription", catalog = state.subscriptionStatus;
      chatTransport.value = state.chatTransport; tier.hidden = false; modelRow.hidden = !selected;
      subscriptionModel.replaceChildren();
      const empty = make("option", state.subscriptionReading ? "正在读取模型状态…" : catalog?.connected ? "请选择实际模型" : catalog?.status === "catalog_required" ? "模型目录尚未准备好" : "模型暂不可选，请查看下方状态"); empty.value = ""; subscriptionModel.append(empty);
      const valid = state.subscription && catalog?.connected && state.subscription.connectionId === catalog.connectionId && state.subscription.catalogRevision === catalog.catalogRevision && catalog.models.some(item => item.slug === state.subscription.modelSlug);
      if (state.subscription && !valid) { const previous = make("option", `${state.subscription.modelSlug}（旧选择，请重新选择）`); previous.value = `stale:${state.subscription.modelSlug}`; previous.disabled = true; subscriptionModel.append(previous); }
      for (const model of catalog?.models || []) { const choice = make("option", `${model.displayName} · ${model.slug}`); choice.value = model.slug; subscriptionModel.append(choice); }
      subscriptionModel.value = valid ? state.subscription.modelSlug : state.subscription ? `stale:${state.subscription.modelSlug}` : "";
      modelFeedback.textContent = !catalog?.connected || state.subscriptionReading ? subscriptionCatalogMessage() : subscriptionProfileIssue() || "当前选择已保存，点发送才会提交本轮消息。";
      modelFeedback.dataset.error = String(Boolean(!state.subscriptionReading && (catalog && !catalog.connected || state.subscription && !valid)));
      modelCheck.hidden = Boolean(catalog?.connected && valid && !state.subscriptionReading); modelCheck.disabled = state.busy || state.subscriptionReading;
      connectionNote.textContent = offline ? "连接电脑后才能使用订阅。" : state.subscriptionReading ? "正在读取电脑保存的连接状态；不会发送消息。" : catalog?.connected ? `${subscriptionProfileIssue() || "模型与档位请求已选择，实际以本轮完成回执为准。"} 发送使用账户共享额度；费用和 credits 由官方设置控制。` : catalog?.error || "请先在电脑 Console 连接 ChatGPT 订阅；手机不保存连接凭据。";
      checkConnection.disabled = state.busy || state.subscriptionReading;
    }
    async function readSubscriptionStatus(visible = false) {
      if (offline || state.subscriptionReading) { if (offline && visible) say("请先连接电脑；草稿和图片保留。"); return; }
      const generation = state.generation; state.subscriptionReading = true; renderSubscription(); updateControls();
      try { const value = await call("subscription/status"); if (generation !== state.generation) return; state.subscriptionStatus = safeSubscriptionStatus(value); if (visible) say(state.subscriptionStatus.connected ? "订阅连接状态已读取，尚未发送。" : "模型状态已读取，当前尚未就绪；请查看模型下方说明。"); }
      catch (error) { if (generation === state.generation && !error.cancelled) { state.subscriptionStatus = { connected: false, busy: false, models: [], status: "unavailable", error: error.message || "订阅连接暂不可用，原草稿保留。" }; if (visible || state.chatTransport === "chatgpt_subscription") fail(error); } }
      finally { if (generation === state.generation) { state.subscriptionReading = false; renderSubscription(); renderCapability(); updateControls(); } }
    }
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
    function applyDialogue(data, expectedSession = "", readCancellation = false) {
      if (!data || data.session?.isCurrent === false || expectedSession && state.session?.id && expectedSession !== state.session.id || data.session?.id === state.session?.id && data.session?.revision < state.session?.revision) return false;
      const cancellationRecovered = readCancellation && recoverCancellationReceipt(data);
      const previousSession = state.session?.id;
      state.session = data.session || null; state.detail = data.detail || null; state.execution = data.execution || null;
      eligibleAttachments = Array.isArray(data.eligibleAttachments) ? data.eligibleAttachments : [];
      if (!previousSession && state.session?.id && state.drafts.unopened) {
        const original = state.drafts.unopened, knownSessions = Object.keys(state.drafts).filter(id => id !== "unopened");
        if ((original.userEdited === true || original.text) && (original.waitingForSession === true || !knownSessions.length)) state.drafts[state.session.id] = { ...original, waitingForSession: false };
        delete state.drafts.unopened;
        persist();
      }
      if (state.session?.id && previousSession !== state.session.id) void restoreSessionFiles(state.session.id);
      const selectedTier = data.preferences?.requestedProfile || data.session?.requestedProfile; if (!saved.tier && !state.dirty && tiers.some(item => item.id === selectedTier)) state.tier = selectedTier;
      if (!saved.chatTransport && !state.dirty && !state.pending) { state.chatTransport = data.preferences?.chatTransport === "chatgpt_subscription" ? "chatgpt_subscription" : "browser_chat"; state.subscription = subscriptionChoice(data.preferences?.subscription); }
      const key = currentResultKey();
      if (key !== resultKey) { closeResultStream(); resultKey = key; resultCursor = ""; resultPending = null; resultStopped = false; }
      if (/^[a-f0-9]{64}$/.test(data.resultCursor || "")) { if (!resultCursor || !resultStream && !resultPending) resultCursor = data.resultCursor; if (resultPending?.cursor === data.resultCursor) resultPending = null; }
      tier.value = state.tier; renderConversation(); renderCapability(); renderFiles(); updateControls(); syncResultStream(); if (cancellationRecovered) say("这条未发送请求已结束，原内容与当前草稿保留。"); return true;
    }
    function currentResultKey() { return state.session ? `${state.clientId}:${state.session.id}:${state.session.recordId}` : ""; }
    function canReadResults() { return !offline && !adapter && state.active && state.view === "chat" && !pageClosed && !document.hidden && navigator.onLine !== false && !resultTransition && /^[a-f0-9]{32}$/.test(state.session?.id || "") && /^[a-f0-9]{32}$/.test(state.session?.recordId || ""); }
    function closeResultStream() { resultEpoch++; const stream = resultStream; resultStream = null; stream?.controller.abort(); void stream?.reader?.cancel().catch(() => {}); }
    function currentResultStream(stream) { return resultStream === stream && stream.epoch === resultEpoch && stream.generation === state.generation && stream.key === currentResultKey() && canReadResults(); }
    function receiveResultFrame(stream, frame) {
      if (!currentResultStream(stream)) return;
      const lines = frame.split("\n"), events = lines.filter(line => line.startsWith("event:")), dataLines = lines.filter(line => line.startsWith("data:"));
      if (events.length !== 1 || !dataLines.length) return;
      const event = events[0].slice(6).trim(); if (!["dialogue.ready", "dialogue.result", "dialogue.closed"].includes(event)) return;
      let data; try { data = JSON.parse(dataLines.map(line => line.slice(5).replace(/^ /, "")).join("\n")); } catch { return; }
      if (!data || Object.keys(data).sort().join(",") !== "clientId,cursor,jobId,recordId,sessionId,status" || data.clientId !== stream.clientId || data.sessionId !== stream.sessionId || data.recordId !== stream.recordId || !/^[a-f0-9]{64}$/.test(data.cursor || "") || data.jobId !== null && !/^[a-f0-9]{32}$/.test(data.jobId || "") || typeof data.status !== "string" || !data.status || data.status.length > 80) return;
      if (event === "dialogue.closed") { resultStopped = true; closeResultStream(); return; }
      if (event === "dialogue.ready") { resultCursor = data.cursor; void drainResults(); return; }
      if (data.cursor === resultCursor) return;
      resultCursor = data.cursor; resultPending = { key: stream.key, generation: stream.generation, cursor: data.cursor }; void drainResults();
    }
    function syncResultStream() {
      if (!canReadResults()) { closeResultStream(); return; }
      if (resultStream || resultStopped || typeof fetch !== "function" || typeof TextDecoder !== "function") return;
      let url; try { url = new URL(`${base}/mobile/dialogue/events`, location.origin); if (url.origin !== location.origin) return; } catch { return; }
      url.search = new URLSearchParams({ clientId: state.clientId, sessionId: state.session.id, cursor: resultCursor }).toString();
      const stream = { epoch: ++resultEpoch, generation: state.generation, key: currentResultKey(), clientId: state.clientId, sessionId: state.session.id, recordId: state.session.recordId, controller: new AbortController(), reader: null }; resultStream = stream;
      void (async () => {
        try {
          const response = await fetch(url.href, { method: "GET", credentials: "same-origin", mode: "same-origin", cache: "no-store", redirect: "error", signal: stream.controller.signal, headers: { Accept: "text/event-stream", ...(phone ? { "X-Codex-Phone": "1" } : {}) } });
          if (!currentResultStream(stream)) { await response.body?.cancel(); return; }
          if (response.status === 401) { options.onAuth?.(); throw new Error("请重新连接电脑。"); }
          if (!response.ok || !/^text\/event-stream(?:;|$)/i.test(response.headers.get("Content-Type") || "") || !response.body?.getReader) throw new Error("回答通知连接暂不可用，请重新连接电脑后查看。");
          stream.reader = response.body.getReader(); const decoder = new TextDecoder(); let buffered = "";
          while (currentResultStream(stream)) {
            const chunk = await stream.reader.read(); if (!currentResultStream(stream)) return;
            if (chunk.done) { options.onConnectionState?.(false); if (!state.storageFailed) say("回答通知连接已断开；重新连接电脑后可继续查看。", true); break; }
            buffered += decoder.decode(chunk.value, { stream: true }); buffered = buffered.replace(/\r\n/g, "\n");
            if (buffered.length > 65536) throw new Error("回答通知格式暂时无法读取，请重新连接电脑后查看。");
            let boundary; while ((boundary = buffered.indexOf("\n\n")) !== -1) { const frame = buffered.slice(0, boundary); buffered = buffered.slice(boundary + 2); receiveResultFrame(stream, frame); if (!currentResultStream(stream)) return; }
          }
        } catch (error) { if (currentResultStream(stream) && error.name !== "AbortError") { options.onConnectionState?.(false); if (!state.storageFailed) fail(error); } }
        finally { if (resultStream === stream) { resultStopped = true; closeResultStream(); } }
      })();
    }
    async function drainResults() {
      if (!resultPending || resultDraining || !canReadResults() || state.busy || state.reading || state.composing || editComposing.body || editComposing.execution) return;
      const pending = resultPending; if (pending.key !== currentResultKey() || pending.generation !== state.generation) { resultPending = null; return; }
      resultDraining = true;
      try { if (await refresh(false) && resultPending === pending) resultPending = null; }
      finally { resultDraining = false; if (resultPending && resultPending !== pending) void drainResults(); }
    }
    function verifiedSubscriptionSelection(job) {
      const result = job?.result, selected = subscriptionChoice(result?.subscription);
      return job?.recordId === state.session?.recordId && job.status === "succeeded" && job.appDispatch?.status === "completed" && result?.source === "chatgpt_subscription" && result.terminalEventObserved === true && result.terminalStatus === "completed" && result.completionEvidence === "response.completed" && result.providerErrorObserved === false && selected?.requestedProfile && result.actualProfileVerified === true && result.requestedProfile === selected.requestedProfile && result.actualProfile === selected.requestedProfile && result.requestedModel === selected.modelSlug && result.actualModel === selected.modelSlug && result.dispatchId === job.appDispatch.id && typeof result.responseId === "string" && /^resp_[A-Za-z0-9_-]{1,190}$/.test(result.responseId) && reasoningMatches(result.requestedReasoning, selected.requestedProfile) && reasoningMatches(result.actualReasoning, selected.requestedProfile) && sameSubscription(job.subscription, selected) && (state.detail?.messages || []).some(message => message.id === result.messageId && message.role === "assistant" && message.text === result.text && result.text?.trim()) ? selected : null;
    }
    function renderCapability() {
      renderSubscription();
      if (state.chatTransport === "chatgpt_subscription") {
        const issue = subscriptionProfileIssue(), actual = state.execution?.actualReceipt, verified = actual?.verified === true && actual.status === "completed" && actual.source === "chatgpt_subscription" && actual.actualProfile === state.tier && actual.actualModel === state.subscription?.modelSlug && reasoningMatches(actual.actualReasoning, state.tier) && (state.detail?.jobs || []).some(job => sameSubscription(verifiedSubscriptionSelection(job), state.subscription));
        const label = tiers.find(item => item.id === state.tier).label;
        capabilityStatus.textContent = offline ? "电脑未连接" : issue ? issue : verified ? `最近回执已核实 ${label} · ${state.subscription.modelSlug}` : `请求 ${label} · 已选 ${state.subscription.modelSlug}`;
        capabilityStatus.title = `${reasoningLabel(state.tier)}。${verified ? "这个模型与档位组合已有同一讨论的真实完成回执；新消息仍需明确发送。" : "实际模式以本轮真实完成回执为准；映射准备、保存和选择档位不会发送。"}`;
        menuMeta.textContent = `${options.getVersion?.() || "Codex Console"}\nChatGPT 订阅只发送本轮明确确认的文字和选图，回答回到同一讨论。Work 仍需另行核对工作区。`;
        return;
      }
      const actual = state.execution?.actualReceipt?.actualProfile, verified = state.execution?.actualReceipt?.verified === true && tiers.some(item => item.id === actual);
      const observed = state.execution?.profileObservation, observation = observed && Object.keys(observed).sort().join(",") === "actualProfileObserved,capabilitiesVerified,dispatchId,jobId,messageId,observedAt,requestedProfile,source" && observed.requestedProfile === "fast" && observed.actualProfileObserved === "Instant" && observed.source === "browser_dom_ui_label" && observed.capabilitiesVerified === false && [observed.dispatchId, observed.jobId, observed.messageId].every(id => typeof id === "string" && /^[a-f0-9]{32}$/.test(id)) && typeof observed.observedAt === "string" && /^\d{4}-\d{2}-\d{2}T/.test(observed.observedAt) && !Number.isNaN(Date.parse(observed.observedAt)) ? "上一轮页面显示 Instant；实际模型／推理未核实" : "";
      capabilityStatus.textContent = offline ? "电脑未连接" : verified ? `实际 ${tiers.find(item => item.id === actual).label}` : "档位待核实";
      capabilityStatus.title = [state.execution?.message || "当前 App 通道的档位还未验证，不会把请求档位当作实际能力。", observation].filter(Boolean).join("\n");
      menuMeta.textContent = offline ? "内容保存在此手机；连接电脑后才可发给 ChatGPT。" : `${options.getVersion?.() || "Codex Console"}\n${state.execution?.message || "普通 Chat 自动转发尚未接通，排队不代表已送达。"}${observation ? `\n${observation}` : ""}`;
    }
    function renderConversation() {
      if (state.view !== "chat") { for (const node of [context, welcome, messages, pending]) node.hidden = true; return; }
      const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 150;
      const values = Array.isArray(state.detail?.messages) ? state.detail.messages : [];
      const fresh = values.some(item => item.role === "assistant" && !state.messageIds.has(item.id));
      state.messageIds = new Set(values.map(item => item.id)); messages.replaceChildren();
      for (const message of values.filter(item => ["user", "assistant"].includes(item.role))) {
        const row = make("article", "", "dialogue-message"); row.dataset.role = message.role;
        const meta = make("div", "", "dialogue-message-meta"), time = make("time", savedTime(message.createdAt), "dialogue-message-time");
        time.title = "记录保存时间 · Asia/Shanghai（UTC+08:00）";
        if (time.textContent !== "时间未记录") time.setAttribute("datetime", message.createdAt);
        meta.append(make("p", message.role === "assistant" ? "ChatGPT" : "你", "dialogue-message-label"), time);
        row.append(meta, make("p", message.text || "", "dialogue-message-text"));
        const roundImages = make("div", "", "dialogue-attachment-grid");
        for (const id of message.attachmentIds || []) {
          const attachment = (state.detail?.attachments || []).find(item => item.id === id);
          if (!attachment || !/^image\//.test(attachment.mimeType || "")) continue;
          try {
            const source = new URL(attachment.previewUrl || attachment.url, window.location.href);
            if (source.origin !== location.origin) continue;
            const image = make("img"); image.src = source.href; image.alt = attachment.name || "本轮已确认图片"; roundImages.append(image);
          } catch { /* Missing/foreign URLs do not become model-visible images. */ }
        }
        if (roundImages.children.length) row.append(roundImages);
        const receipt = (state.detail?.jobs || []).find(job => job.recordId === state.session?.recordId && job.status === "succeeded" && job.result?.messageId === message.id && job.result.text === message.text && job.result.source === "chatgpt_subscription" && job.result.terminalEventObserved === true && job.result.terminalStatus === "completed" && job.result.completionEvidence === "response.completed" && typeof job.result.actualModel === "string" && job.result.actualModel.length <= 200 && message.text?.trim());
        if (message.role === "assistant" && receipt) { const verified = verifiedSubscriptionSelection(receipt), profile = verified ? ` · 实际 ${tiers.find(item => item.id === verified.requestedProfile).label}` : "", note = make("p", `实际模型：${receipt.result.actualModel} · 回答已保存${profile}`, "dialogue-message-note"); if (verified) note.title = reasoningLabel(verified.requestedProfile); row.append(note); if (acceptedSendNotices.includes(notice.textContent)) say(); }
        if (message.role === "assistant") { const actions = make("div", "", "dialogue-message-actions"); actions.append(button(state.session?.ideaId ? "补充到此想法" : "存为想法", () => void rememberAnswer(message.id)), button("复制", () => void copyText(message.text || ""))); row.append(actions); }
        if (message.truncated) row.append(make("p", "此回答来源已截断，全文请到原 Chat 查看。", "dialogue-message-note")); messages.append(row);
      }
      const jobs = Array.isArray(state.detail?.jobs) ? state.detail.jobs : [], inFlight = jobs.filter(item => ["queued", "running", "pending", "claimed", "waiting", "needs_review"].includes(item.status) || ["pending", "claimed", "waiting", "needs_review"].includes(item.appDispatch?.status)).at(-1), failure = latestDialogueFailure();
      pending.replaceChildren(pendingText); pending.hidden = !inFlight && !failure; pending.dataset.status = inFlight ? inFlight.appDispatch?.status || inFlight.status : failure ? "failed" : ""; cancelPendingButton = null;
      if (inFlight) {
        const dispatchStatus = inFlight.appDispatch?.status || inFlight.status;
        const running = ["running", "waiting"].includes(dispatchStatus);
        if (running) pending.prepend(make("span", "", "dialogue-spinner"));
        const target = cancellablePending();
        const unsent = target?.jobId === inFlight.id;
        const subscription = inFlight.chatTransport === "chatgpt_subscription" && inFlight.subscription?.provider === "chatgpt_subscription";
        const stages = { accepted: "请求已接收，尚未发送。", started: "正在核对已确认的模型和选图，尚未发送。", generating: "正在等待本轮实际回答…", unknown: "发送或完成情况需要核对，原请求保留，未重复发送。" };
        pendingText.textContent = subscription ? stages[inFlight.subscriptionPhase] || "请求已接收，发送状态尚未核实。" : dispatchStatus === "needs_review" ? "送达情况需要核对，未重复发送。" : running ? "正在等原聊天回答…" : unsent ? "尚未发送，等待转发处理" : dispatchStatus === "pending" ? "等待转发处理，发送状态尚未核实。" : "请求已保存，等待处理。";
        if (subscription && inFlight.status === "waiting" && dispatchStatus === "needs_review" && currentDialogueJob(inFlight) && subscriptionChoice(inFlight.subscription) && inFlight.result?.source === "chatgpt_subscription" && inFlight.result.status === "unknown") {
          const reasons = { completed_reasoning_unverified: "回答的实际档位未返回，尚不能核实所选档位。", completed_reasoning_mismatch: "回答返回的实际档位与本次选择不一致。", subscription_profile_unverified: "回答的实际档位尚未准确核实。", subscription_result_mismatch: "本轮回答的模型或完成证据尚未准确核实。", stream_ended_without_completed: "回答连接已结束，但没有取得准确的完成回执。", completed_text_mismatch: "收到的回答文字与完成回执尚未一致。", invalid_stream: "回答回执格式未通过核对。", transport_error: "回答连接中断，送达或完成情况尚未核实。" };
          const code = inFlight.result.code, reason = Object.hasOwn(reasons, code) ? reasons[code] : "本轮发送或完成证据尚未核实，请在电脑查看原请求。";
          pendingText.textContent = `本轮需要核对：${reason}\n原消息与当前草稿保留，未自动重发。`;
          const text = inFlight.result.partialText;
          if (inFlight.result.partialTextComplete === false && typeof text === "string" && text.trim() && text.length <= 128 * 1024) { const review = make("section", "", "dialogue-review-answer"); review.append(make("p", "已收到文字 · 待核对", "dialogue-review-label"), make("p", text, "dialogue-review-text"), make("p", "这段文字尚未作为已完成回答保存；实际档位与完成状态以核对结果为准。", "dialogue-source-note")); pending.append(review); }
          if (acceptedSendNotices.includes(notice.textContent)) say();
        }
        if (unsent) { cancelPendingButton = button("结束这条未发送请求", () => void cancelUnsentRequest(target)); pending.append(cancelPendingButton); }
      } else if (failure) {
        const error = typeof failure.error === "string" && failure.error ? failure.error : typeof failure.appDispatch.error === "string" && failure.appDispatch.error ? failure.appDispatch.error : "未取得实际回答，请核对电脑上的原请求。";
        const reason = error.replace(/^[a-z][a-z0-9_]*:\s*(?=\S)/, "");
        pendingText.textContent = `这轮未完成：${reason}\n原消息与当前草稿保留，未自动重发。`;
        if (acceptedSendNotices.includes(notice.textContent)) say();
      }
      context.hidden = !state.session?.ideaId; contextText.textContent = state.session?.ideaId ? `围绕「${state.detail?.sourceTask?.title || state.idea?.title || "这条想法"}」继续聊` : "";
      welcome.hidden = Boolean(values.length || state.session?.ideaId); messages.hidden = !values.length;
      if (fresh && state.view === "chat") { if (atBottom) requestAnimationFrame(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "auto" })); else { state.newResults = true; newResult.hidden = false; } }
    }
    function latestDialogueFailure() {
      const session = state.session;
      if (!session || session.isCurrent !== true || session.clientId !== state.clientId || state.detail?.record?.id !== session.recordId) return null;
      const latest = (Array.isArray(state.detail.jobs) ? state.detail.jobs : []).filter(currentDialogueJob).at(-1);
      return latest?.status === "failed" && latest.appDispatch?.status === "failed"
        && typeof latest.id === "string" && latest.id && typeof latest.appDispatch.id === "string" && latest.appDispatch.id ? latest : null;
    }
    function currentDialogueJob(job) { const session = state.session; return Boolean(session?.isCurrent === true && session.clientId === state.clientId && state.detail?.record?.id === session.recordId && job?.recordId === session.recordId && job.kind === "discuss" && job.purpose === "discussion" && job.mobileDialogue?.id === session.id && job.mobileDialogue.clientId === state.clientId && job.mobileDialogue.recordId === session.recordId && typeof job.id === "string" && job.id && typeof job.appDispatch?.id === "string" && job.appDispatch.id); }
    function renderView() {
      root.dataset.view = state.view; back.hidden = state.view === "chat"; ideasButton.hidden = state.view !== "chat"; clearMenuAction.hidden = state.view !== "chat";
      title.textContent = ({ chat: "对话", ideas: state.archived ? "归档想法" : "想法", detail: "想法", execution: "执行稿" })[state.view];
      listView.hidden = state.view !== "ideas"; detailView.hidden = state.view !== "detail"; executionView.hidden = state.view !== "execution"; composer.hidden = state.view !== "chat";
      for (const node of [context, welcome, messages, pending]) if (state.view !== "chat") node.hidden = true;
      if (state.view === "chat") renderConversation(); newResult.hidden = state.view !== "chat" || !state.newResults; renderEditReviews(); updateControls(); syncResultStream(); options.onViewChange?.(state.view);
    }
    function currentFiles() { return !fileOwner || fileOwner === state.session?.id ? files : []; }
    function updateControls() { const empty = !composerInput.value.trim(), hasImages = currentFiles().length > 0 || (state.session?.draft?.attachmentIds || []).length > 0; send.disabled = state.busy || empty && !hasImages || state.composing || state.chatTransport === "chatgpt_subscription" && !subscriptionReady(); saveOnly.disabled = state.busy || empty && !currentFiles().length && !(state.session?.draft?.attachmentIds || []).length || state.composing; attach.disabled = state.busy || Boolean(state.pending) || Boolean(uploadRequest); tier.disabled = state.busy || state.chatTransport === "chatgpt_subscription" && Boolean(state.pending); chatTransport.disabled = state.busy || Boolean(state.pending) || offline; subscriptionModel.disabled = state.busy || Boolean(state.pending) || state.subscriptionReading || !state.subscriptionStatus?.connected; if (cancelPendingButton) cancelPendingButton.disabled = state.busy || state.composing || Boolean(state.pending && state.pending.action !== "mobile/dialogue/cancel-pending"); saveEdit.hidden = !state.editorDirty; saveEdit.disabled = state.busy || editComposing.body || state.editorDirty && !editSourceMatches("body"); handover.disabled = state.busy || editComposing.execution || !executionText.value.trim() || !editSourceMatches("execution"); saveExecution.disabled = handover.disabled; discussIdea.disabled = state.busy || state.editorDirty; executionDraft.disabled = state.busy || state.editorDirty; carryIdea.disabled = state.busy || state.editorDirty; managementSubmit.disabled = state.busy || !state.management?.ready; managementCancel.disabled = state.busy; retryManagement.hidden = !state.pending?.management; retryManagement.disabled = state.busy; if (pointEditor) { pointEditor.save.disabled = state.busy || pointEditor.composing || !pointSourceMatches(pointEditor.draft) || !pointTextForSave(pointEditor.input.value); pointEditor.cancel.disabled = state.busy; if (pointEditor.rebase) pointEditor.rebase.disabled = state.busy; } const imageLocked = state.busy || Boolean(state.pending) || Boolean(uploadRequest); for (const remove of imageRemovalButtons) remove.disabled = imageLocked; for (const label of savedImageChoices.children) for (const node of label.children) if (node.type === "checkbox") node.disabled = imageLocked; void drainResults(); }
    async function writeFiles(value) { fileWriting++; try { await blobs.put(value); } catch (error) { fileError = true; throw error; } finally { fileWriting--; } }
    async function saveFiles() { try { await writeFiles({ id: filesKey, files, fileOwner, uploadRequest }); fileError = false; } catch (error) { fileError = true; fail(error); throw error; } }
    async function restoreSessionFiles(id) {
      if (!id || fileOwner === id) return;
      try { if (fileOwner && files.length) await writeFiles({ id: `${filesKey}:${fileOwner}`, files, uploadRequest, fileOwner }); const value = await blobs.get(`${filesKey}:${id}`); if (state.session?.id !== id || !value?.files) return; files = value.files; fileOwner = id; uploadRequest = value.uploadRequest || null; await saveFiles(); renderFiles(); }
      catch (error) { fileError = true; fail(error); }
    }
    function renderFiles() {
      for (const source of filePreviews) URL.revokeObjectURL?.(source); filePreviews.length = imageRemovalButtons.length = 0; pendingImages.replaceChildren();
      const renderedSessionId = state.session?.id;
      const addImage = (source, name, action) => { const card = make("div", "", "dialogue-draft-image"), remove = button("", action, "dialogue-image-remove"), glyph = make("span", "×"); glyph.setAttribute("aria-hidden", "true"); remove.append(glyph); remove.setAttribute("aria-label", `移除本次图片 ${name}`); remove.title = "只取消本次选图，保留原图"; imageRemovalButtons.push(remove); if (source) { const image = make("img"); image.src = source; image.alt = name; card.append(image); } else card.append(make("span", name)); card.append(remove); pendingImages.append(card); };
      for (const file of currentFiles()) { const source = URL.createObjectURL?.(file); if (source) filePreviews.push(source); addImage(source, file.name || "待保存图片", () => void removeLocalImage(file, renderedSessionId)); }
      const selected = new Set(state.session?.draft?.attachmentIds || []); for (const item of state.detail?.attachments || []) { if (!selected.has(item.id) || !/^image\//.test(item.mimeType || "")) continue; addImage(item.previewUrl || item.url, item.name || "已上传图片", () => void selectSavedImage(item.id, false, renderedSessionId)); }
      const allowed = new Set([...(state.session?.eligibleAttachmentIds || []), ...(state.session?.uploadedAttachmentIds || [])]); savedImageChoices.replaceChildren();
      for (const item of eligibleAttachments) { if (!allowed.has(item.id) || !/^image\//.test(item.mimeType || "")) continue; const label = make("label", "", "dialogue-saved-image-choice"), choice = field("input", `本次引用 ${item.name || "已保存图片"}`); choice.type = "checkbox"; choice.checked = selected.has(item.id); label.dataset.selected = String(choice.checked); choice.disabled = state.busy || Boolean(state.pending) || Boolean(uploadRequest); choice.addEventListener("change", () => void selectSavedImage(item.id, choice.checked, renderedSessionId)); label.append(choice, make("span", item.name || "已保存图片")); const source = item.previewUrl || item.url; if (source) { const image = make("img"); image.src = source; image.alt = item.name || "已保存图片"; label.append(image); } savedImageChoices.append(label); }
      savedImagePicker.hidden = !savedImageChoices.children.length;
      pendingImages.hidden = !pendingImages.children.length; updateControls();
    }
    async function removeLocalImage(file, renderedSessionId) {
      const generation = state.generation, ownsImage = () => generation === state.generation && state.session?.id === renderedSessionId && currentFiles().includes(file);
      if (state.busy || state.pending || uploadRequest || !renderedSessionId || !ownsImage()) return;
      let removed = false; state.busy = true; updateControls();
      try {
        if (draftSync) await draftSync;
        if (!ownsImage() || state.pending || uploadRequest) return;
        const remaining = [...files]; remaining.splice(remaining.indexOf(file), 1);
        const row = { files: remaining, fileOwner: renderedSessionId, uploadRequest: null };
        await writeFiles({ id: `${filesKey}:${renderedSessionId}`, ...row }); await writeFiles({ id: filesKey, ...row });
        if (!ownsImage()) return;
        files = remaining; fileOwner = renderedSessionId; fileError = false; removed = true; saveLocalDraft(); say("已移除本次图片，文字与其他图片保留；尚未发送。");
      } catch (error) { if (ownsImage()) fail(error); }
      finally { if (generation === state.generation) { state.busy = false; renderFiles(); if (removed && state.session?.id === renderedSessionId) void syncDraft(); } }
    }
    async function selectSavedImage(id, selected, renderedSessionId) {
      if (state.busy || state.pending || uploadRequest || !state.session || state.session.id !== renderedSessionId) { renderFiles(); return; }
      const sessionId = state.session.id; state.busy = true; updateControls();
      try { if (draftSync) await draftSync; if (state.session?.id !== sessionId || !eligibleAttachments.some(item => item.id === id)) throw new Error("图片来源已变化，请重新读取当前想法。"); const ids = new Set(state.session.draft?.attachmentIds || []); if (selected) ids.add(id); else ids.delete(id); const selectedImages = [...(state.detail?.attachments || []), ...eligibleAttachments].filter((item, index, values) => ids.has(item.id) && values.findIndex(other => other.id === item.id) === index); if (ids.size + currentFiles().length > 4 || selectedImages.reduce((sum, item) => sum + (item.size || 0), 0) + currentFiles().reduce((sum, item) => sum + item.size, 0) > 24 * 1024 * 1024) throw new Error("本次最多引用 4 张图片，合计不超过 24 MB。"); saveLocalDraft(); const payload = submission(); payload.attachmentIds = [...ids]; const data = await call("mobile/dialogue/draft", payload); if (state.session?.id !== sessionId || !applyDialogue(data, sessionId)) return; say("本次选图已保存，尚未发送。"); } catch (error) { fail(error); } finally { state.busy = false; renderFiles(); }
    }
    async function uploadFiles(intent) {
      if (!intent.files.length) return [];
      if (fileReading) await fileReading; if (fileError) await saveFiles();
      await ensureSession();
      if (!fileOwner) { fileOwner = state.session.id; await saveFiles(); }
      if (!uploadRequest) { uploadRequest = { requestId: uuid(), recordId: state.session.recordId, route: "mobile/dialogue/upload", scope: { clientId: state.clientId, sessionId: state.session.id, expectedRevision: state.session.revision } }; await saveFiles(); }
      if (uploadRequest.recordId !== state.session.recordId) throw new Error("待上传图片属于原讨论，请先返回原讨论保存，不会附到其它想法。");
      if (uploadRequest.route !== "mobile/dialogue/upload" || uploadRequest.scope?.clientId !== state.clientId || uploadRequest.scope?.sessionId !== state.session.id) throw new Error("旧图片上传结果尚需核对；原图片和请求仍保留，未作为新上传重复发送。");
      let uploaded;
      if (options.uploadAttachments) uploaded = await options.uploadAttachments(intent.files, state.session, uploadRequest);
      else { if (offline) throw new Error("图片仍保存在此手机；连接电脑后才能同步图片。"); const form = new FormData(); form.append("requestId", uploadRequest.requestId); form.append("recordId", uploadRequest.recordId); form.append("text", JSON.stringify(uploadRequest.scope)); for (const file of intent.files) form.append("files", file, file.name || "image.png"); uploaded = await call(uploadRequest.route, form); }
      const attachmentIds = uploaded.uploadedAttachmentIds || uploaded.attachmentIds || (uploaded.attachments || []).map(item => item.id);
      if (!attachmentIds.length) throw new Error("尚未取得图片保存凭据，原图片草稿仍保留。");
      if (uploaded.session && !applyDialogue(uploaded, uploadRequest.scope.sessionId)) throw new Error("讨论已切换；原图片上传凭据保留，未附到新讨论。");
      const payload = submission(intent); payload.attachmentIds = [...new Set([...payload.attachmentIds, ...attachmentIds])]; if (payload.attachmentIds.length > 4) throw new Error("本次图片超过 4 张，请先取消一张已选图片；原文件和上传凭据仍保留。"); const data = await call("mobile/dialogue/draft", payload); applyDialogue(data, state.session.id); files = files.filter(file => !intent.files.includes(file)); if (!files.length) fileOwner = null; uploadRequest = null; await saveFiles(); renderFiles(); return attachmentIds;
    }
    async function ensureSession() {
      if (state.session) return state.session;
      const data = await call("mobile/dialogue/open", { requestId: uuid(), clientId: state.clientId }); applyDialogue(data); restoreDraft(); return state.session;
    }
    function composeIntent() { return { sessionId: state.session?.id || "", text: composerInput.value, attachmentIds: [...(state.session?.draft?.attachmentIds || [])], requestedProfile: state.tier, chatTransport: state.chatTransport, subscription: subscriptionChoice(state.subscription), files: [...currentFiles()] }; }
    function submission(intent = composeIntent(), uploadedIds = []) { if (intent.sessionId && intent.sessionId !== state.session?.id) throw new Error("讨论已切换，原输入保留，未发送到其它讨论。"); return { requestId: uuid(), clientId: state.clientId, sessionId: state.session.id, expectedRevision: state.session.revision, text: intent.text, attachmentIds: [...new Set([...intent.attachmentIds, ...uploadedIds])], requestedProfile: intent.requestedProfile, ...(!offline ? { chatTransport: intent.chatTransport, ...(intent.chatTransport === "chatgpt_subscription" ? { subscription: intent.subscription } : {}) } : {}) }; }
    function durablePayload(action, candidate, identity) {
      if (state.pending) { if (state.pending.action !== action || identity.some(key => JSON.stringify(state.pending.payload[key]) !== JSON.stringify(candidate[key]))) throw new Error("上一项操作结果尚未核对。先刷新核对，原请求不会重复创建。"); return state.pending.payload; }
      state.pending = { action, payload: candidate }; if (!persist()) { state.pending = null; throw new Error("操作凭据无法保存在手机，请保留或复制原内容。"); } return candidate;
    }
    function writeRejected(error) { return error.status >= 400 && error.status < 500 && error.status !== 409 || error.status === 409 && ["revision_conflict", "dialogue_changed", "task_source_mismatch", "dispatch_in_progress", "subscription_not_connected", "subscription_selection_stale", "subscription_model_unavailable", "subscription_profile_unavailable", "subscription_profile_mismatch", "subscription_reasoning_mismatch", "subscription_binding_invalid"].includes(error.data?.code || error.code); }
    function recoverCancellationReceipt(data) {
      const operation = state.pending, payload = operation?.payload;
      if (operation?.action !== "mobile/dialogue/cancel-pending" || !payload
          || Object.keys(payload).sort().join(",") !== "clientId,dispatchId,expectedRevision,recordId,requestId,sessionId"
          || payload.clientId !== state.clientId || data.session?.id !== payload.sessionId || data.session?.recordId !== payload.recordId
          || data.detail?.record?.id !== payload.recordId || !Array.isArray(data.cancellationReceipts) || !Array.isArray(data.detail?.jobs)) return false;
      const receipt = data.cancellationReceipts.slice(0, 20).find(item => item && typeof item === "object"
        && Object.keys(item).sort().join(",") === "clientId,dispatchId,expectedRevision,jobId,reason,recordId,requestId,sessionId,status,unsent"
        && Object.keys(payload).every(key => item[key] === payload[key])
        && item.status === "failed" && item.reason === "cancelled_before_send" && item.unsent === true
        && data.detail.jobs.filter(job => job?.id === item.jobId && job.recordId === payload.recordId
          && job.status === "failed" && job.appDispatch?.id === payload.dispatchId && job.appDispatch.status === "failed").length === 1);
      if (!receipt) return false;
      state.pending = null; persist(); return true;
    }
    function cancellablePending() {
      const session = state.session, job = Array.isArray(state.detail?.jobs) ? state.detail.jobs.at(-1) : null, dispatch = job?.appDispatch;
      if (offline || state.view !== "chat" || !session?.id || !session.recordId || state.detail?.record?.id !== session.recordId
          || job?.recordId !== session.recordId || job.status !== "waiting" || !job.id || !dispatch?.id
          || dispatch.status !== "pending" || dispatch.canCancelPending !== true || ![null, ""].includes(dispatch.targetThreadId)
          || !job.result || typeof job.result !== "object" || Array.isArray(job.result) || Object.keys(job.result).length) return null;
      return { sessionId: session.id, recordId: session.recordId, dispatchId: dispatch.id, jobId: job.id };
    }
    async function cancelUnsentRequest(target) {
      if (state.busy || state.composing) return;
      const matches = () => { const current = cancellablePending(); return current && ["sessionId", "recordId", "dispatchId", "jobId"].every(key => current[key] === target[key]); };
      if (!matches()) { say("请求状态已变化，请刷新当前讨论后核对。", true); return; }
      state.busy = true; saveLocalDraft(); updateControls();
      try {
        if (draftSync) await draftSync;
        if (!matches()) throw new Error("请求状态已变化，尚未结束；请核对当前讨论。");
        const candidate = { requestId: uuid(), clientId: state.clientId, sessionId: target.sessionId, recordId: target.recordId,
          expectedRevision: state.session.revision, dispatchId: target.dispatchId };
        const payload = durablePayload("mobile/dialogue/cancel-pending", candidate, ["clientId", "sessionId", "recordId", "dispatchId"]);
        const data = await call("mobile/dialogue/cancel-pending", payload), receipt = data?.cancellation;
        if (!receipt || Object.keys(receipt).sort().join(",") !== "clientId,dispatchId,expectedRevision,jobId,reason,recordId,sessionId,status,unsent"
            || receipt.clientId !== payload.clientId || receipt.expectedRevision !== payload.expectedRevision
            || receipt.sessionId !== payload.sessionId || receipt.recordId !== payload.recordId || receipt.dispatchId !== payload.dispatchId
            || receipt.jobId !== target.jobId || receipt.status !== "failed" || receipt.reason !== "cancelled_before_send" || receipt.unsent !== true
            || data.session?.id !== payload.sessionId || data.session?.recordId !== payload.recordId || !applyDialogue(data, payload.sessionId))
          throw new Error("结束结果尚未核实，原请求编号与草稿保留；请刷新核对。");
        state.pending = null; persist(); say("这条未发送请求已结束，原内容与当前草稿保留。");
      } catch (error) {
        if (error.status >= 400 && error.status < 500 && state.pending?.action === "mobile/dialogue/cancel-pending") { state.pending = null; persist(); }
        const unknownRequestId = state.pending?.action === "mobile/dialogue/cancel-pending" ? state.pending.payload.requestId : "";
        if (!error.cancelled && state.session?.id === target.sessionId && state.session?.recordId === target.recordId) await refresh(false);
        if (unknownRequestId && !state.pending) return;
        fail(error);
      } finally { state.busy = false; updateControls(); }
    }
    async function syncDraft() {
      if (draftSync || !state.active || state.busy || !state.dirty || state.storageFailed || offline) return;
      const intent = composeIntent(), text = intent.text;
      draftSync = (async () => {
        try { await ensureSession(); const id = state.session.id, data = await call("mobile/dialogue/draft", submission(intent)); if (applyDialogue(data, id) && composerInput.value === text) { state.drafts[id] = { text, tier: intent.requestedProfile, unsynced: false }; state.dirty = false; persist(); } }
        catch (error) { fail(error); }
      })();
      try { await draftSync; } finally { draftSync = null; }
    }
    async function sendMessage() {
      if (state.busy || state.composing || !composerInput.value.trim() && !currentFiles().length && !(state.session?.draft?.attachmentIds || []).length) return;
      if (offline) { if (!saveLocalDraft()) return; say("请连接电脑后发送；这段草稿已保存在此手机。"); options.onConnect?.(); return; }
      if (state.chatTransport === "chatgpt_subscription" && !subscriptionReady()) { say(subscriptionProfileIssue() || "请先核对订阅连接与当前请求；原文字和图片保留。", true); return; }
      const intent = composeIntent(), text = intent.text; state.busy = true; updateControls(); say("");
      try { if (draftSync) await draftSync; await ensureSession(); const uploadedIds = !state.pending ? await uploadFiles(intent) : []; const payload = durablePayload("mobile/dialogue/send", submission(intent, uploadedIds), ["sessionId", "text", "attachmentIds", "requestedProfile", "chatTransport", "subscription"]);
        const data = await call("mobile/dialogue/send", payload); state.pending = null;
        if (applyDialogue(data, payload.sessionId) && composerInput.value === text) { composerInput.value = ""; state.drafts[payload.sessionId] = { text: "", tier: state.tier, unsynced: false }; state.dirty = false; autosize(composerInput); }
        const result = data.job?.result, savedAnswer = payload.chatTransport === "chatgpt_subscription" && data.job?.status === "succeeded" && result?.source === "chatgpt_subscription" && result.terminalEventObserved === true && result.terminalStatus === "completed" && result.completionEvidence === "response.completed" && result.text?.trim() && data.detail?.messages?.some(message => message.role === "assistant" && message.id === result.messageId && message.text === result.text);
        persist(); if (!latestDialogueFailure()) say(savedAnswer ? "本轮回答已保存。" : payload.chatTransport === "chatgpt_subscription" ? acceptedSendNotices[2] : acceptedSendNotices[data.execution?.relayStatus === "connected" ? 0 : 1]);
      } catch (error) { if (writeRejected(error)) { state.pending = null; persist(); if (intent.chatTransport === "chatgpt_subscription" && ["subscription_not_connected", "subscription_selection_stale", "subscription_model_unavailable", "subscription_profile_unavailable", "subscription_profile_mismatch", "subscription_reasoning_mismatch", "subscription_binding_invalid"].includes(error.data?.code || error.code)) await readSubscriptionStatus(); } fail(error); }
      finally { state.busy = false; updateControls(); }
    }
    async function saveIdea() {
      if (state.busy || state.composing || !composerInput.value.trim() && !currentFiles().length && !(state.session?.draft?.attachmentIds || []).length) return;
      const intent = composeIntent(), text = intent.text; state.busy = true; updateControls();
      try { if (draftSync) await draftSync; await ensureSession(); const uploadedIds = !state.pending ? await uploadFiles(intent) : []; const payload = durablePayload("mobile/dialogue/save", submission(intent, uploadedIds), ["sessionId", "text", "requestedProfile"]), data = await call("mobile/dialogue/save", payload); state.pending = null; applyDialogue(data, payload.sessionId);
        if (composerInput.value === text) { composerInput.value = ""; state.drafts[payload.sessionId] = { text: "", tier: state.tier, unsynced: false }; state.dirty = false; autosize(composerInput); } persist(); say(offline ? "想法已保存在此手机。" : "想法已保存到电脑，随时可以接着聊。"); if (data.idea) state.idea = data.idea;
      } catch (error) { if (writeRejected(error)) { state.pending = null; persist(); } fail(error); } finally { state.busy = false; updateControls(); }
    }
    async function clearDiscussion() {
      if (state.busy) return;
      if (state.pending) { say("上一条操作是否送达还需要核对，暂不切换讨论；原草稿与请求编号保留。", true); return; }
      more.open = false; if (state.view !== "chat") return;
      state.busy = true; resultTransition = true; closeResultStream(); updateControls(); saveLocalDraft();
      try { if (draftSync) await draftSync; await ensureSession(); if (currentFiles().length) { fileOwner = state.session.id; await saveFiles(); } const data = await call("mobile/dialogue/clear", { requestId: uuid(), clientId: state.clientId, sessionId: state.session.id, expectedRevision: state.session.revision }); applyDialogue(data); state.messageIds.clear(); composerInput.value = ""; state.drafts[state.session.id] = { text: "", tier: state.tier, unsynced: false }; delete state.drafts.unopened; state.dirty = false; state.newResults = false; persist(); autosize(composerInput); renderView(); say("当前讨论已重新开始，保存的想法仍然保留。"); }
      catch (error) { fail(error); } finally { resultTransition = false; state.busy = false; updateControls(); syncResultStream(); }
    }
    async function rememberAnswer(sourceMessageId) {
      if (state.busy || !state.session) return; state.busy = true; updateControls();
      try { if (draftSync) await draftSync; const candidate = { requestId: uuid(), clientId: state.clientId, sessionId: state.session.id, expectedRevision: state.session.revision, sourceMessageId, ...(state.session.ideaId ? { ideaId: state.session.ideaId, expectedIdeaRevision: state.session.ideaRevision } : {}) }, payload = durablePayload("mobile/dialogue/remember", candidate, ["sessionId", "sourceMessageId", "ideaId"]); const data = await call("mobile/dialogue/remember", payload); state.pending = null; persist(); applyDialogue(data, payload.sessionId); say(data.keyPointAdded === false && data.keyPointOmittedReason === "point_limit" ? "完整回答与来源已保存；长期要点已满，未新增要点。" : payload.ideaId ? "已补充到此想法，原回答来源已保留。" : "已存为想法，原回答来源已保留。"); }
      catch (error) { if (writeRejected(error)) { state.pending = null; persist(); } fail(error); } finally { state.busy = false; updateControls(); }
    }
    async function refresh(recoverEvents = true) {
      if (!state.active || state.reading || state.composing && state.view === "chat" || pointEditor?.composing && state.view === "detail" || editComposing.body || editComposing.execution) return false; if (recoverEvents && !resultStream) resultStopped = false; capturePointEditor(); state.reading = true; const sequence = ++state.requestSequence, sessionId = state.session?.id || "";
      try { if (state.view === "ideas") await loadIdeas(); else if (["detail", "execution"].includes(state.view) && state.idea) await openIdea(state.idea.id, true); else { const data = await call(`mobile/dialogue?clientId=${encodeURIComponent(state.clientId)}`); if (sequence !== state.requestSequence) return false; if (sessionId && data.session?.id !== sessionId && state.dirty) return false; const applied = applyDialogue(data, sessionId, true); if (applied && (!state.dirty || !sessionId) && !state.composing) restoreDraft(); if (applied && state.chatTransport === "chatgpt_subscription") await readSubscriptionStatus(); return applied; } }
      catch (error) { fail(error); } finally { state.reading = false; updateControls(); syncResultStream(); }
    }
    async function showIdeas() { if (state.busy) return; closeManagement(); if (state.view === "chat") { state.chatScroll = window.scrollY; saveLocalDraft(); void syncDraft(); } state.view = "ideas"; say(""); renderView(); await loadIdeas(); requestAnimationFrame(() => window.scrollTo({ top: state.listScroll, behavior: "auto" })); }
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
      if (!refreshing) { closeManagement(); state.listScroll = window.scrollY; persist(); state.view = "detail"; say(""); renderView(); }
      try { const data = await call(`mobile/idea?id=${encodeURIComponent(id)}`); if (sequence !== ideaSequence || state.view === "chat" || state.view === "ideas" || refreshing && (pointEditor?.composing || editComposing.body || editComposing.execution)) return; if (data.idea?.id !== id) throw new Error("这条想法的身份暂时无法核对。"); state.idea = data.idea; state.ideaDetail = data.detail || null; const local = state.editDrafts[id]; if (local && typeof local.executionDraft === "string" && local.executionDirty === undefined) { local.executionDirty = local.executionDraft !== (data.idea.executionDraft || ""); if (!local.executionDirty) local.executionSource = editSource("execution", data.idea); persist(); } if (!state.editorDirty || !refreshing) { ideaTitle.value = local?.dirty ? local.title : data.idea?.title || ""; ideaBody.value = local?.dirty ? local.body : data.idea?.body || ""; state.editorDirty = Boolean(local?.dirty); } if (state.view === "execution" && !local?.executionDirty) executionText.value = data.idea.executionDraft || ""; renderIdea(); if (!refreshing) window.scrollTo({ top: 0, behavior: "auto" }); }
      catch (error) { fail(error); }
    }
    function renderIdea() {
      const idea = state.idea; if (!idea) return; capturePointEditor(); pointEditor = null; detailMeta.textContent = `${when(idea.updatedAt)} · ${state.projects.find(item => item.id === idea.projectId)?.name || "未归类"}${idea.archived ? " · 已归档" : ""}`; archiveIdea.textContent = idea.archived ? "取消归档" : "归档想法"; autosize(ideaBody, 12000); pointsList.replaceChildren();
      if (packUrl && (packIdeaId !== idea.id || packRevision !== idea.revision)) clearPack();
      const keyPoints = Array.isArray(idea.keyPoints) ? idea.keyPoints : [], draft = state.pointDrafts[idea.id]; points.hidden = !keyPoints.length && !draft;
      for (const point of keyPoints) { const row = make("div", "", "dialogue-point"), actions = make("div", "", "dialogue-point-actions"), pointText = make("p", point.text || ""); actions.append(make("span", point.kind === "decision" ? "你确认的决定" : "待确认的建议"), button(point.kind === "decision" ? "改为建议" : "确认为决定", () => void changePointKind(idea.id, point.id, point.kind === "decision" ? "suggestion" : "decision")), button("编辑", () => editPoint(idea.id, point, row)), button("删除", () => void updateIdea({ keyPoints: keyPoints.filter(item => item.id !== point.id).map(pointInput) }, idea.id))); row.append(pointText, actions); pointsList.append(row); if (draft?.pointId === point.id) renderPointDraft(row, draft); }
      if (draft && !keyPoints.some(point => point.id === draft.pointId)) { const row = make("div", "", "dialogue-point"); pointsList.append(row); renderPointDraft(row, draft); }
      detailAttachments.replaceChildren(); for (const attachment of state.ideaDetail?.attachments || []) { const source = attachment.url || attachment.href; if (!source || !/^image\//.test(attachment.mimeType || attachment.mime || "")) continue; try { const url = new URL(source, window.location.href); if (url.origin !== location.origin) continue; const image = make("img"); image.src = url.href; image.alt = attachment.name || "想法图片"; detailAttachments.append(image); } catch { /* An invalid attachment address is not rendered. */ } } renderEditReviews(); updateControls();
    }
    function pointInput(item) { return { id: item.id, text: item.text, kind: item.kind }; }
    function closeManagement() { if (state.busy) return; managementSequence++; state.management = null; state.manageDirty = false; managementView.hidden = true; managementFields.replaceChildren(); managementPreview.textContent = ""; updateControls(); }
    function managementCurrent(value) { return state.management === value && state.view === "detail" && state.idea?.id === value.viewIdeaId; }
    function managementField(label, node) { const wrapper = make("label", label); wrapper.append(node); managementFields.append(wrapper); return node; }
    function shortTitle(text) { return Array.from(String(text || "").trim()).slice(0, 80).join(""); }
    function codepointOffset(text, offset) {
      if (!Number.isInteger(offset) || offset < 0 || offset > text.length) throw new Error("请在已保存正文中重新选择内容。");
      if (offset > 0 && offset < text.length && /[\uD800-\uDBFF]/.test(text[offset - 1]) && /[\uDC00-\uDFFF]/.test(text[offset])) throw new Error("选区切到了一个完整字符中间，请重新选择。");
      return Array.from(text.slice(0, offset)).length;
    }
    function readSplitSelection(value, editor) {
      if (!managementCurrent(value) || value.retry) return;
      try {
        const start = codepointOffset(value.source.body, editor.selectionStart), end = codepointOffset(value.source.body, editor.selectionEnd);
        if (end <= start) throw new Error("先在已保存正文中选中要拆出的内容。");
        value.start = start; value.end = end; value.ready = Boolean(value.title.trim()); state.manageDirty = true;
        managementPreview.textContent = Array.from(value.source.body).slice(start, end).join(""); say(""); updateControls();
      } catch (error) { value.ready = false; managementPreview.textContent = ""; updateControls(); fail(error); }
    }
    async function openManagement(kind) {
      if (state.busy || state.view !== "detail" || !state.idea) return;
      const pendingOperation = state.pending?.management;
      if (kind !== "retry" && state.pending) { say(pendingOperation ? "上次整理结果还待核对，请先点「重试上次整理」；原请求编号保留。" : "上一条操作结果还待核对，请先完成原操作。", true); return; }
      if (kind !== "retry" && state.editorDirty) { say("先保存当前修改，再整理已保存的想法。", true); return; }
      if (kind === "retry" && !pendingOperation) return;
      closeManagement(); ideaMore.open = false;
      const source = { id: state.idea.id, revision: state.idea.revision, title: state.idea.title || "未命名想法", body: String(state.idea.body || ""), executionDraft: String(state.idea.executionDraft || ""), projectId: state.idea.projectId || "" }, value = { kind, source, viewIdeaId: state.idea.id, ready: false, selectionSequence: 0 }, sequence = ++managementSequence;
      if (kind === "retry") { value.kind = pendingOperation.kind; value.retry = true; value.source = pendingOperation.source; value.second = pendingOperation.second || null; value.payload = state.pending.payload; value.ready = true; }
      state.management = value; managementView.hidden = false; managementFields.replaceChildren(); managementPreview.textContent = "";
      managementTitle.textContent = value.retry ? "重试上次整理" : ({ move: "移动到项目", split: "拆分选中内容", merge: "合并另一条想法" })[kind];
      managementSource.textContent = `来源：${value.source.title} · v${value.source.revision}${value.second ? `；${value.second.title} · v${value.second.revision}` : ""}`;
      managementSubmit.textContent = value.retry ? "重试原请求" : kind === "move" ? "保存归类" : kind === "split" ? "保存为独立想法" : "保存合并想法"; updateControls();
      if (value.retry) { managementPreview.textContent = pendingOperation.preview || "原整理请求已保留。重试使用相同编号与内容，不建立另一份请求。"; return; }
      if (kind === "split") {
        const selectedStart = ideaBody.selectionStart, selectedEnd = ideaBody.selectionEnd, editor = managementField("选中已保存正文", field("textarea", "选择拆分正文")), newTitle = managementField("新想法标题", field("input", "拆分想法标题")); editor.value = source.body; editor.readOnly = true; editor.rows = 6; newTitle.maxLength = 80; newTitle.value = value.title = shortTitle(`${source.title} · 拆分`);
        newTitle.addEventListener("input", () => { if (!managementCurrent(value)) return; value.title = newTitle.value; value.ready = value.end > value.start && Boolean(value.title.trim()); state.manageDirty = true; updateControls(); });
        for (const event of ["select", "mouseup", "touchend", "keyup"]) editor.addEventListener(event, () => { if (editor.selectionEnd > editor.selectionStart) readSplitSelection(value, editor); });
        managementFields.append(button("使用选中内容", () => readSplitSelection(value, editor)), make("p", "新想法只保存选中的正文；原正文、要点、执行稿和图片保留在原想法，不复制原图。", "dialogue-source-note"));
        if (Number.isInteger(selectedStart) && selectedEnd > selectedStart) { editor.selectionStart = selectedStart; editor.selectionEnd = selectedEnd; readSplitSelection(value, editor); }
        managementView.scrollIntoView?.({ block: "nearest", behavior: "smooth" }); return;
      }
      try {
        const data = await call("mobile/ideas?search=&projectId=&archived=0"); if (sequence !== managementSequence || !managementCurrent(value)) return; state.projects = Array.isArray(data.projects) ? data.projects : [];
        if (kind === "move") {
          const select = managementField("目标项目", field("select", "移动到项目")), projects = Array.isArray(data.projects) ? data.projects.filter(item => typeof item.id === "string" && item.id && item.id !== "unclassified") : [];
          const choices = [{ id: "", name: "请选择项目" }, { id: "unclassified", name: "未归类" }, ...projects];
          for (const item of choices) { const option = make("option", item.name || item.label || item.id); option.value = item.id; select.append(option); }
          select.value = source.projectId && projects.some(item => item.id === source.projectId) ? source.projectId : source.projectId ? "" : "unclassified"; value.projectId = select.value; value.allowedProjects = choices.slice(1).map(item => item.id); value.ready = Boolean(select.value);
          select.addEventListener("change", () => { if (!managementCurrent(value)) return; value.projectId = select.value; value.ready = value.allowedProjects.includes(select.value); state.manageDirty = true; updateControls(); });
          managementPreview.textContent = "只调整这条想法的归类，正文与来源保留。";
          if (offline && !projects.length) managementFields.append(make("p", "此手机没有已保存的项目目录；可先留在未归类，带到电脑后选择电脑项目。", "dialogue-source-note"));
        } else if (kind === "merge") {
          const archived = await call("mobile/ideas?search=&projectId=&archived=1"); if (sequence !== managementSequence || !managementCurrent(value)) return;
          const candidates = [...(data.ideas || []), ...(archived.ideas || [])].filter((item, index, values) => item.id !== source.id && values.findIndex(other => other.id === item.id) === index), select = managementField("另一条已保存想法", field("select", "选择合并想法")), newTitle = managementField("合并后的标题", field("input", "合并想法标题")); const placeholder = make("option", "请选择想法"); placeholder.value = ""; select.append(placeholder);
          for (const idea of candidates) { const option = make("option", `${idea.title || "未命名想法"}${idea.archived ? " · 已归档" : ""}`); option.value = idea.id; select.append(option); } select.value = ""; newTitle.maxLength = 80; newTitle.value = value.title = shortTitle(`${source.title} · 合并`);
          select.addEventListener("change", () => void selectMergeIdea(value, select.value, candidates)); newTitle.addEventListener("input", () => { if (!managementCurrent(value)) return; value.title = newTitle.value; value.ready = Boolean(value.second && value.title.trim()); state.manageDirty = true; updateControls(); });
          managementFields.append(make("p", "生成第三份想法，两份原稿都保留。正文与执行稿按所选顺序合并，要点保留建议／决定身份；原图保留在各自原想法，不复制。", "dialogue-source-note")); if (!candidates.length) managementPreview.textContent = "还没有另一条已保存想法。";
        }
        updateControls(); managementView.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
      } catch (error) { if (managementCurrent(value)) fail(error); }
    }
    async function selectMergeIdea(value, id, candidates) {
      if (!managementCurrent(value)) return; const sequence = ++value.selectionSequence; value.second = null; value.ready = false; managementPreview.textContent = ""; updateControls(); if (!candidates.some(item => item.id === id)) return;
      try { const data = await call(`mobile/idea?id=${encodeURIComponent(id)}`); if (!managementCurrent(value) || sequence !== value.selectionSequence) return; if (!data.idea || data.idea.id !== id || !Number.isInteger(data.idea.revision)) throw new Error("这条想法的来源与版本暂时无法核对。");
        value.second = { id, revision: data.idea.revision, title: data.idea.title || "未命名想法", body: String(data.idea.body || ""), executionDraft: String(data.idea.executionDraft || "") }; state.manageDirty = true; value.ready = Boolean(value.title.trim());
        managementSource.textContent = `来源：${value.source.title} · v${value.source.revision}；${value.second.title} · v${value.second.revision}`; const body = [value.source.body, value.second.body].filter(Boolean).join("\n\n"), execution = [value.source.executionDraft, value.second.executionDraft].filter(Boolean).join("\n\n"); managementPreview.textContent = `正文\n${body}${execution ? `\n\n执行稿\n${execution}` : ""}`; updateControls();
      } catch (error) { if (managementCurrent(value) && sequence === value.selectionSequence) fail(error); }
    }
    async function submitManagement() {
      const value = state.management; if (state.busy || !value?.ready || !managementCurrent(value)) return;
      if (state.pending && !value.retry) { say("上次整理结果还待核对，请先点「重试上次整理」。", true); return; }
      if (!value.retry && (state.editorDirty || state.idea.revision !== value.source.revision)) { say("原想法版本已改变，请保存或刷新后重新选择内容。", true); return; }
      let action, payload;
      try {
        if (value.retry) { action = state.pending.action; payload = state.pending.payload; }
        else {
          if (value.kind === "move") { if (!value.allowedProjects.includes(value.projectId)) throw new Error("请选择已有项目或未归类。"); action = "mobile/idea/update"; payload = { requestId: uuid(), id: value.source.id, expectedRevision: value.source.revision, projectId: value.projectId === "unclassified" ? null : value.projectId }; }
          else if (value.kind === "split") { action = "mobile/idea/split"; payload = { requestId: uuid(), id: value.source.id, expectedRevision: value.source.revision, start: value.start, end: value.end, title: value.title.trim() }; }
          else { if (!value.second || value.second.id === value.source.id) throw new Error("请选择另一条已保存想法。"); action = "mobile/idea/merge"; payload = { requestId: uuid(), firstId: value.source.id, firstRevision: value.source.revision, secondId: value.second.id, secondRevision: value.second.revision, title: value.title.trim() }; }
          payload = durablePayload(action, payload, value.kind === "merge" ? ["firstId", "secondId"] : ["id"]); state.pending.management = { kind: value.kind, source: value.source, second: value.second || null, preview: managementPreview.textContent }; if (!persist()) throw new Error("整理请求暂时无法保存在此手机，请保留页面。");
        }
        state.busy = true; updateControls(); const data = await call(action, payload), result = data?.idea;
        if (!result?.id || !Number.isInteger(result.revision) || result.revision < 1 || value.kind === "move" && result.id !== value.source.id || value.kind !== "move" && [value.source.id, value.second?.id].includes(result.id)) throw new Error("整理结果的来源与版本暂时无法核对，原请求编号已保留。");
        state.pending = null; persist(); state.busy = false; closeManagement(); await openIdea(result.id); say(value.kind === "move" ? "归类已保存，内容与来源保留。" : value.kind === "split" ? "已保存为独立想法，原想法保留。" : "已保存合并想法，两份原稿保留。");
      } catch (error) { if (writeRejected(error) && ![401, 403].includes(error.status)) { state.pending = null; persist(); } else if (state.pending?.management) say("这次整理的结果还待核对；在更多里点「重试上次整理」，会保留同一请求编号。", true); if (!state.pending?.management) fail(error); }
      finally { state.busy = false; updateControls(); }
    }
    async function changePointKind(ideaId, pointId, kind) {
      if (state.busy || state.view !== "detail" || state.idea?.id !== ideaId) return false;
      const keyPoints = Array.isArray(state.idea.keyPoints) ? state.idea.keyPoints : [], point = keyPoints.find(item => item.id === pointId);
      if (!point || point.kind === kind) return false;
      return updateIdea({ keyPoints: keyPoints.map(item => pointInput(item.id === pointId ? { ...item, kind } : item)) }, ideaId);
    }
    function pointSourceMatches(draft) { const point = state.idea?.id === draft.ideaId && state.idea.keyPoints?.find(item => item.id === draft.pointId); return Boolean(point && state.idea.revision === draft.sourceRevision && point.text === draft.sourceText && point.kind === draft.sourceKind); }
    // Python str.strip used by the saved-point API includes U+001C–001F, and keeps BOM.
    function pointTextForSave(text) { return text.replace(/^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/gu, ""); }
    function pointEditorCurrent(binding) { return pointEditor === binding && state.view === "detail" && state.idea?.id === binding.draft.ideaId && state.pointDrafts[binding.draft.ideaId] === binding.draft; }
    function capturePointEditor(binding = pointEditor) { if (!binding || !pointEditorCurrent(binding)) return; binding.draft.text = binding.input.value; binding.draft.kind = binding.kind.value; persist(); }
    function editPoint(ideaId, point, row) {
      if (state.busy || state.view !== "detail" || state.idea?.id !== ideaId) return; const actual = state.idea.keyPoints?.find(item => item.id === point.id); if (!actual) return;
      const existing = state.pointDrafts[ideaId]; if (existing && existing.pointId !== point.id) { say("先保存或取消当前要点草稿，再编辑另一条。", true); return; }
      const draft = existing || { ideaId, pointId: actual.id, sourceRevision: state.idea.revision, sourceText: actual.text, sourceKind: actual.kind, text: actual.text, kind: actual.kind }; state.pointDrafts[ideaId] = draft; persist(); renderIdea();
    }
    function renderPointDraft(row, draft) {
      const input = field("textarea", "编辑长期要点", "dialogue-keypoint-editor"), kind = field("select", "要点类型"), actions = make("div", "", "dialogue-detail-actions"), source = make("p", "", "dialogue-source-note"), point = state.idea.keyPoints?.find(item => item.id === draft.pointId), matches = pointSourceMatches(draft);
      for (const item of [{ id: "suggestion", label: "建议" }, { id: "decision", label: "已确认决定" }]) { const option = make("option", item.label); option.value = item.id; kind.append(option); } input.value = draft.text; kind.value = draft.kind;
      const binding = { draft, input, kind, composing: false, save: button("保存要点", () => void savePointDraft(binding), "dialogue-primary"), cancel: button("取消要点编辑", () => { if (!pointEditorCurrent(binding) || state.busy) return; capturePointEditor(binding); const cleared = clearPointDraft(draft); renderIdea(); if (cleared) say(""); }), rebase: null };
      source.textContent = !point ? "这个要点已删除，草稿仍保留供复制，不能写回原要点。" : matches ? "要点草稿保存在此设备，点保存后才修改想法。" : `想法已更新，草稿来自第 ${draft.sourceRevision} 版。请核对当前要点后再继续编辑。`;
      actions.append(binding.save, binding.cancel); if (!matches) actions.append(button("复制要点草稿", () => { if (pointEditorCurrent(binding)) { capturePointEditor(binding); void copyText(draft.text); } }));
      row.replaceChildren(source); if (point && !matches) { const current = make("details", "", "dialogue-more"); current.append(make("summary", `当前第 ${state.idea.revision} 版 · ${point.kind === "decision" ? "已确认决定" : "建议"}`), make("p", point.text)); binding.rebase = button("基于当前版本继续编辑", () => { if (!pointEditorCurrent(binding) || state.busy) return; capturePointEditor(binding); const actual = state.idea.keyPoints?.find(item => item.id === draft.pointId); if (!actual) return; Object.assign(draft, { sourceRevision: state.idea.revision, sourceText: actual.text, sourceKind: actual.kind }); persist(); renderIdea(); say("已改用当前来源；草稿尚未保存到想法。"); }); row.append(current); actions.append(binding.rebase); }
      row.append(input, kind, actions); pointEditor = binding; input.addEventListener("input", () => { capturePointEditor(binding); updateControls(); }); kind.addEventListener("change", () => capturePointEditor(binding)); input.addEventListener("compositionstart", () => { if (pointEditorCurrent(binding)) { binding.composing = true; updateControls(); } }); input.addEventListener("compositionend", () => { if (pointEditorCurrent(binding)) { binding.composing = false; capturePointEditor(binding); updateControls(); } }); autosize(input, 12000); updateControls();
    }
    async function savePointDraft(binding) {
      if (!pointEditorCurrent(binding) || state.busy || binding.composing) return; capturePointEditor(binding); const draft = binding.draft;
      if (!pointSourceMatches(draft)) { renderIdea(); return; } const frozen = { ...draft }, submittedText = pointTextForSave(frozen.text); if (!submittedText || Array.from(submittedText).length > 20000) { say("要点须有内容，并且不超过 20000 字。", true); return; }
      const keyPoints = state.idea.keyPoints.map(item => pointInput(item.id === draft.pointId ? { ...item, text: submittedText, kind: frozen.kind } : item));
      if (!await updateIdea({ keyPoints }, draft.ideaId)) return; const actual = state.idea?.id === frozen.ideaId && state.idea.keyPoints?.find(item => item.id === frozen.pointId);
      if (state.pointDrafts[frozen.ideaId] === draft && draft.text === frozen.text && draft.kind === frozen.kind && actual?.text === submittedText && actual?.kind === frozen.kind && state.idea.revision > frozen.sourceRevision) { const cleared = clearPointDraft(draft); renderIdea(); say(cleared ? "要点已保存。" : "要点已保存，但本机草稿清理失败；原输入仍保留。", !cleared); }
    }
    function clearPointDraft(draft) { delete state.pointDrafts[draft.ideaId]; pointEditor = null; if (persist()) return true; state.pointDrafts[draft.ideaId] = draft; return false; }
    // Exact field snapshots are local fingerprints; they do not authorize a newer source revision.
    function editSource(kind, idea = state.idea) {
      if (!idea) return null;
      const fields = kind === "body" ? [String(idea.title || ""), String(idea.body || "")] : [String(idea.executionDraft || "")];
      return { ideaId: idea.id, revision: idea.revision, fields, fingerprint: JSON.stringify(fields) };
    }
    function sameEditSource(source, kind, idea = state.idea) { const actual = editSource(kind, idea); return Boolean(source && actual && source.ideaId === actual.ideaId && source.revision === actual.revision && source.fingerprint === actual.fingerprint && JSON.stringify(source.fields) === actual.fingerprint); }
    function editDirty(kind, draft = state.idea && state.editDrafts[state.idea.id]) { return Boolean(kind === "body" ? draft?.dirty : draft?.executionDirty); }
    function editSourceMatches(kind) { const draft = state.idea && state.editDrafts[state.idea.id]; return !editDirty(kind, draft) || sameEditSource(draft[kind === "body" ? "bodySource" : "executionSource"], kind); }
    function renderEditReviews() {
      for (const [kind, section] of [["body", bodyDraftReview], ["execution", executionDraftReview]]) {
        const draft = state.idea && state.editDrafts[state.idea.id], sourceKey = kind === "body" ? "bodySource" : "executionSource", source = draft?.[sourceKey];
        section.hidden = !editDirty(kind, draft) || editSourceMatches(kind); section.replaceChildren(); if (section.hidden || !state.idea) continue;
        const ideaId = state.idea.id, currentSource = editSource(kind), generation = state.generation, current = make("details", "", "dialogue-more"), actions = make("div", "", "dialogue-detail-actions"), label = kind === "body" ? "正文" : "执行稿";
        section.append(make("p", source?.revision ? `想法已更新，这份${label}草稿来自第 ${source.revision} 版。核对当前版本后再保存；原输入保留。` : `这份${label}草稿的来源版本未记录。核对当前版本后再保存；原输入保留。`, "dialogue-source-note"));
        const original = field("textarea", kind === "body" ? "当前已保存正文" : "当前已保存执行稿", "dialogue-keypoint-editor"); original.readOnly = true; original.value = kind === "body" ? String(state.idea.body || "") : String(state.idea.executionDraft || ""); original.rows = 4;
        current.append(make("summary", `当前第 ${state.idea.revision} 版 · ${label}`)); if (kind === "body") current.append(make("p", state.idea.title || "")); current.append(original);
        const rebase = button(kind === "body" ? "基于当前正文继续编辑" : "基于当前执行稿继续编辑", () => {
          if (state.busy || editComposing[kind] || generation !== state.generation || state.idea?.id !== ideaId || !sameEditSource(currentSource, kind)) return;
          const latest = state.editDrafts[ideaId]; if (!editDirty(kind, latest)) return; const previous = latest[sourceKey]; latest[sourceKey] = currentSource;
          if (!persist()) latest[sourceKey] = previous; else say("已核对当前来源，草稿仍保存在此设备，尚未提交。"); renderEditReviews(); updateControls();
        }); rebase.disabled = state.busy || editComposing[kind]; actions.append(rebase); section.append(current, actions);
      }
    }
    function persistExecution() {
      if (!state.idea) return;
      const id = state.idea.id, previous = state.editDrafts[id] || {};
      state.editDrafts[id] = { ...previous, executionDraft: executionText.value, executionDirty: true, executionSource: previous.executionDirty ? previous.executionSource : editSource("execution") };
      persist(); autosize(executionText, 12000); renderEditReviews(); updateControls();
    }
    function advanceOwnEditSources(id, before, actual) {
      const draft = state.editDrafts[id]; if (!draft) return;
      for (const kind of ["body", "execution"]) { const key = kind === "body" ? "bodySource" : "executionSource"; if (sameEditSource(draft[key], kind, before)) draft[key] = editSource(kind, actual); }
    }
    async function updateIdea(extra = null, expectedIdeaId = null) {
      if (state.busy || !state.idea || expectedIdeaId && state.idea.id !== expectedIdeaId) return false; if (state.pending?.management) { say("上次整理结果还待核对，请先点「重试上次整理」。", true); return false; }
      const kind = !extra ? "body" : extra.executionDraft !== undefined ? "execution" : null;
      if (kind && (editComposing[kind] || !editSourceMatches(kind))) { renderEditReviews(); updateControls(); say("来源版本需要先核对，原草稿保留，尚未保存。", true); return false; }
      const before = { ...state.idea }, id = before.id, frozen = kind === "body" ? { title: ideaTitle.value, body: ideaBody.value } : kind === "execution" ? { executionDraft: extra.executionDraft } : null;
      if (kind === "body") persistEditor(); else if (kind === "execution" && executionText.value === frozen.executionDraft) persistExecution();
      if (kind && !persist()) return false;
      const payload = { requestId: uuid(), id, expectedRevision: before.revision, ...(extra || { title: pointTextForSave(frozen.title), body: frozen.body }) };
      state.busy = true; updateControls();
      try {
        const data = await call("mobile/idea/update", payload), actual = data?.idea;
        if (state.idea?.id !== id || !actual || actual.id !== id || actual.revision !== before.revision + 1 || state.idea.revision > actual.revision || kind === "body" && (actual.title !== payload.title || actual.body !== payload.body) || kind === "execution" && actual.executionDraft !== payload.executionDraft) throw new Error("这次保存的来源或内容暂时无法核对，原草稿仍保留。");
        state.idea = actual; advanceOwnEditSources(id, before, actual);
        const draft = state.editDrafts[id] || {}, unchanged = kind === "body" ? ideaTitle.value === frozen.title && ideaBody.value === frozen.body : kind === "execution" ? executionText.value === frozen.executionDraft : true;
        if (kind === "body" && unchanged) { ideaTitle.value = actual.title; ideaBody.value = actual.body; Object.assign(draft, { title: actual.title, body: actual.body, dirty: false, bodySource: editSource("body") }); }
        else if (kind === "execution" && unchanged) Object.assign(draft, { executionDraft: actual.executionDraft, executionDirty: false, executionSource: editSource("execution") });
        state.editDrafts[id] = draft; state.editorDirty = Boolean(draft.dirty);
        const stored = persist(); if (!stored && kind) { if (kind === "body") { if (unchanged) { ideaTitle.value = frozen.title; ideaBody.value = frozen.body; draft.title = frozen.title; draft.body = frozen.body; } draft.dirty = true; state.editorDirty = true; } else draft.executionDirty = true; }
        renderIdea(); say(!stored ? "内容已保存，但本机草稿状态尚未保存；原输入保留，请保持页面。" : !unchanged ? "本次内容已保存；等待时的新输入仍是本机草稿。" : kind === "execution" ? "执行稿已保存，尚未交给 Codex。" : "修改已保存。", !stored); return true;
      }
      catch (error) { fail(error); return false; } finally { state.busy = false; updateControls(); }
    }
    async function archiveCurrent() {
      if (state.busy || !state.idea || state.editorDirty) { if (state.editorDirty) say("先保存当前修改，再归档。"); return; } if (state.pending?.management) { say("上次整理结果还待核对，请先点「重试上次整理」。", true); return; } state.busy = true; updateControls();
      try { const data = await call("mobile/idea/archive", { requestId: uuid(), id: state.idea.id, expectedRevision: state.idea.revision, archived: !state.idea.archived }); state.idea = data.idea || state.idea; ideaMore.open = false; renderIdea(); say(state.idea.archived ? "已归档，内容和附件仍然保留。" : "已恢复到想法列表。"); }
      catch (error) { fail(error); } finally { state.busy = false; updateControls(); }
    }
    async function openIdeaDiscussion() {
      if (state.busy || !state.idea || state.editorDirty) return; state.busy = true; updateControls();
      if (state.pending) { state.busy = false; updateControls(); say("上一条操作是否送达还需要核对，暂不切换讨论；原草稿与请求编号保留。", true); return; }
      resultTransition = true; closeResultStream();
      try { if (draftSync) await draftSync; saveLocalDraft(); const data = await call("mobile/dialogue/open", { requestId: uuid(), clientId: state.clientId, ideaId: state.idea.id, expectedIdeaRevision: state.idea.revision }); state.messageIds.clear(); applyDialogue(data); state.view = "chat"; restoreDraft(); renderView(); say(""); window.scrollTo({ top: 0, behavior: "auto" }); }
      catch (error) { fail(error); } finally { resultTransition = false; state.busy = false; updateControls(); syncResultStream(); }
    }
    function showExecutionDraft() { if (!state.idea || state.editorDirty) return; closeManagement(); state.view = "execution"; const draft = state.editDrafts[state.idea.id]; executionText.value = draft?.executionDirty ? draft.executionDraft : state.idea.executionDraft || state.idea.body || ""; if (!draft?.executionDirty && executionText.value !== (state.idea.executionDraft || "")) persistExecution(); renderView(); autosize(executionText, 12000); window.scrollTo({ top: 0, behavior: "auto" }); }
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
      if (!state.idea || state.busy || editComposing.execution || !editSourceMatches("execution") || !executionText.value.trim()) return;
      const frozen = { id: state.idea.id, text: executionText.value, generation: state.generation };
      if (offline) {
        let reservation; try { reservation = options.onHandoffReserve?.(); if (!reservation) throw new Error("先连接电脑；执行稿仍保存在此手机。"); } catch (error) { fail(error); return; }
        if (frozen.text !== (state.idea.executionDraft || "") && !await updateIdea({ executionDraft: frozen.text }, frozen.id)) { reservation.popup?.close?.(); return; }
        if (frozen.generation !== state.generation || state.idea?.id !== frozen.id || state.idea.executionDraft !== frozen.text) { reservation.popup?.close?.(); return; }
        await handoffIdea(reservation); return;
      }
      if (frozen.text !== (state.idea.executionDraft || "")) { if (!await updateIdea({ executionDraft: frozen.text }, frozen.id)) return; }
      if (frozen.generation !== state.generation || state.idea?.id !== frozen.id || state.idea.executionDraft !== frozen.text) return;
      const result = await options.onExecution?.({ ...state.idea, ideaId: frozen.id, executionDraft: frozen.text }); if (result === false) say("工作区暂时无法打开，执行稿已保留。", true);
    }
    async function goBack() { if (state.busy) return; closeManagement(); if (state.view === "execution") { state.view = "detail"; renderView(); return; } if (state.view === "detail") { if (state.editorDirty) persistEditor(); state.view = "ideas"; renderView(); await loadIdeas(); requestAnimationFrame(() => window.scrollTo({ top: state.listScroll, behavior: "auto" })); } else { state.listScroll = window.scrollY; persist(); state.view = "chat"; renderView(); requestAnimationFrame(() => window.scrollTo({ top: state.chatScroll, behavior: "auto" })); } }
    function persistEditor() { if (!state.idea) return; const previous = state.editDrafts[state.idea.id] || {}; state.editDrafts[state.idea.id] = { ...previous, title: ideaTitle.value, body: ideaBody.value, dirty: true, bodySource: previous.dirty ? previous.bodySource : editSource("body") }; state.editorDirty = true; persist(); autosize(ideaBody, 12000); renderEditReviews(); updateControls(); }
    function openModule(module) { saveLocalDraft(); void syncDraft(); options.onModule?.(module); }
    function getWorkSource() {
      const session = state.session;
      if (state.view !== "chat" || !session || session.isCurrent !== true || session.clientId !== state.clientId || state.detail?.record?.id !== session.recordId || !Number.isSafeInteger(session.revision) || session.revision < 1 || state.busy || state.reading || state.composing || state.pending || draftSync || fileReading || fileWriting || fileError || state.storageFailed || uploadRequest || currentFiles().length) return null;
      const attachmentIds = session.draft?.attachmentIds || [];
      if (!Array.isArray(attachmentIds) || attachmentIds.length > 4 || new Set(attachmentIds).size !== attachmentIds.length || attachmentIds.some(id => typeof id !== "string" || !id || !(state.detail?.attachments || []).some(item => item.id === id && /^image\//.test(item.mimeType || "")))) return null;
      return { recordId: session.recordId, clientId: state.clientId, sessionId: session.id, expectedRevision: session.revision, text: composerInput.value, attachmentIds: [...attachmentIds] };
    }
    function getWorkScope() {
      const session = state.session;
      if (!session || session.isCurrent !== true || session.clientId !== state.clientId || state.detail?.record?.id !== session.recordId || typeof session.id !== "string" || typeof session.recordId !== "string") return null;
      // Reading/cancelling an accepted Agent needs identity, not an unsent draft.
      return { clientId: state.clientId, sessionId: session.id, recordId: session.recordId };
    }
    async function copyText(text) { try { if (!navigator.clipboard?.writeText) throw new Error("请长按内容选择并复制。"); await navigator.clipboard.writeText(text); say("已复制。"); } catch (error) { fail(error); } }
    composer.addEventListener("submit", event => event.preventDefault());
    packInput.addEventListener("change", async () => { const file = packInput.files?.[0]; packInput.value = ""; if (!file || state.busy || !options.onImportPack) return; state.busy = true; updateControls(); try { const receipt = await options.onImportPack(file); if (!receipt?.imported?.ideaId) throw new Error("导入回执无法核对，原资料保留。"); state.busy = false; await openIdea(receipt.imported.ideaId); say("这条手机想法已导入，手机原副本保留；尚未发送或执行。"); } catch (error) { fail(error); } finally { state.busy = false; updateControls(); } });
    imageInput.addEventListener("change", async () => {
      if (uploadRequest) { say("上次图片上传的内容与编号已冻结；原文件保留，先完成原图片请求。", true); imageInput.value = ""; return; }
      const chosen = Array.from(imageInput.files || []); imageInput.value = ""; if (state.busy || !chosen.length) return;
      const selectedIds = new Set(state.session?.draft?.attachmentIds || []), selectedSize = [...(state.detail?.attachments || []), ...eligibleAttachments].filter((item, index, values) => selectedIds.has(item.id) && values.findIndex(other => other.id === item.id) === index).reduce((sum, item) => sum + (item.size || 0), 0);
      if (chosen.some(item => !/^image\//.test(item.type) || item.size > 8 * 1024 * 1024) || selectedIds.size + currentFiles().length + chosen.length > 4 || selectedSize + [...currentFiles(), ...chosen].reduce((sum, item) => sum + item.size, 0) > 24 * 1024 * 1024) { say("一次最多保留 4 张图片，每张不超过 8 MB，总共不超过 24 MB。", true); return; }
      state.busy = true; updateControls();
      try { if (draftSync) await draftSync; if (fileReading) await fileReading; await ensureSession(); if (fileOwner && fileOwner !== state.session?.id && files.length) { await writeFiles({ id: `${filesKey}:${fileOwner}`, files, uploadRequest, fileOwner }); files = []; uploadRequest = null; } fileOwner = state.session.id; files.push(...chosen); renderFiles(); await saveFiles(); say("图片草稿已保存在此手机；只保存不会发送。"); }
      catch (error) { fileError = true; fail(error); } finally { state.busy = false; updateControls(); }
    });
    composerInput.addEventListener("input", () => { saveLocalDraft(true); window.clearTimeout(draftTimer); draftTimer = window.setTimeout(() => void syncDraft(), 800); }); composerInput.addEventListener("compositionstart", () => { state.composing = true; updateControls(); }); composerInput.addEventListener("compositionend", () => { state.composing = false; saveLocalDraft(true); });
    composerInput.addEventListener("keydown", event => { if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !event.isComposing && !state.composing) { event.preventDefault(); void sendMessage(); } });
    tier.addEventListener("change", () => { if (state.busy || state.chatTransport === "chatgpt_subscription" && state.pending || !tiers.some(item => item.id === tier.value)) { tier.value = state.tier; return; } state.tier = tier.value; saved.tier = state.tier; if (state.chatTransport === "chatgpt_subscription" && state.subscription) state.subscription = chooseSubscriptionModel(state.subscription.modelSlug) || state.subscription; persist(); saveLocalDraft(); renderCapability(); updateControls(); void syncDraft(); });
    chatTransport.addEventListener("change", () => { if (state.busy || state.pending || offline || !["browser_chat", "chatgpt_subscription"].includes(chatTransport.value)) { chatTransport.value = state.chatTransport; return; } state.chatTransport = chatTransport.value; saved.chatTransport = state.chatTransport; persist(); saveLocalDraft(); renderCapability(); updateControls(); void syncDraft(); if (state.chatTransport === "chatgpt_subscription") void readSubscriptionStatus(); });
    subscriptionModel.addEventListener("change", () => { if (state.busy || state.pending || state.subscriptionReading || !state.subscriptionStatus?.connected || !state.subscriptionStatus.models.some(item => item.slug === subscriptionModel.value)) { renderSubscription(); return; } state.subscription = chooseSubscriptionModel(subscriptionModel.value); saved.chatTransport = state.chatTransport; persist(); saveLocalDraft(); renderCapability(); updateControls(); void syncDraft(); });
    ideaTitle.addEventListener("input", persistEditor); ideaBody.addEventListener("input", persistEditor); executionText.addEventListener("input", persistExecution);
    for (const [input, kind] of [[ideaTitle, "body"], [ideaBody, "body"], [executionText, "execution"]]) { input.addEventListener("compositionstart", () => { editComposing[kind] = true; updateControls(); }); input.addEventListener("compositionend", () => { editComposing[kind] = false; kind === "body" ? persistEditor() : persistExecution(); }); }
    search.addEventListener("input", () => { state.search = search.value; state.listScroll = 0; persist(); void loadIdeas(); }); project.addEventListener("change", () => { state.project = project.value; state.listScroll = 0; persist(); void loadIdeas(); });
    window.addEventListener("pagehide", () => { pageClosed = true; closeResultStream(); capturePointEditor(); saveLocalDraft(); if (state.editorDirty) persistEditor(); if (state.view === "execution" && state.idea && executionText.value !== (state.idea.executionDraft || "")) persistExecution(); });
    window.addEventListener("pageshow", () => { pageClosed = false; if (state.active) void refresh(); });
    const viewport = () => { const value = window.visualViewport?.height || window.innerHeight; root.style.setProperty("--dialogue-viewport", `${value}px`); }; window.visualViewport?.addEventListener("resize", viewport); window.addEventListener("resize", viewport); viewport();
    document.addEventListener("visibilitychange", () => { capturePointEditor(); if (!document.hidden && state.active) void refresh(); else if (document.hidden) { closeResultStream(); saveLocalDraft(); } });
    window.addEventListener("offline", () => closeResultStream());
    window.addEventListener("online", () => { if (state.active) void refresh(); });
    window.addEventListener("codex:dialogue-result", event => { if (state.active && event.detail?.clientId === state.clientId && event.detail?.sessionId === state.session?.id && event.detail?.recordId === state.session?.recordId) void refresh(); });
    persist(); restoreDraft(); renderCapability(); renderView();
    fileReading = blobs.get(filesKey).then(value => { if (value?.files) { files = value.files; fileOwner = value.fileOwner || null; uploadRequest = value.uploadRequest || null; renderFiles(); } }).catch(() => { /* No claim of file recovery is made without a readable store. */ }).finally(() => { fileReading = null; });
    return { setActive(value) { const changed = state.active !== Boolean(value); state.active = Boolean(value); if (state.active && changed) { root.hidden = false; void refresh(); } else if (!state.active) { closeResultStream(); capturePointEditor(); saveLocalDraft(); more.open = false; } }, refresh, getWorkSource, getWorkScope, hasDraft() { return state.busy || fileReading || fileWriting || fileError || currentFiles().length > 0 || state.dirty && Boolean(composerInput.value.trim()) || state.editorDirty || Object.values(state.editDrafts).some(draft => draft?.dirty || draft?.executionDirty) || Object.keys(state.pointDrafts).length > 0 || state.manageDirty || Boolean(state.pending); }, canReload() { return !state.busy && !state.manageDirty && !draftSync && !fileReading && !fileWriting && !fileError && !state.storageFailed && !state.composing && !pointEditor?.composing && !editComposing.body && !editComposing.execution; }, async prepareReload() { capturePointEditor(); saveLocalDraft(); if (state.editorDirty) persistEditor(); if (state.view === "execution" && state.idea && executionText.value !== (state.idea.executionDraft || "")) persistExecution(); return !state.storageFailed && !state.busy && !state.manageDirty && !draftSync && !fileReading && !fileWriting && !fileError && !state.composing && !pointEditor?.composing && !editComposing.body && !editComposing.execution; }, clear() { closeResultStream(); resultKey = resultCursor = ""; resultPending = null; capturePointEditor(); pointEditor = null; state.generation += 1; state.subscriptionReading = false; editComposing.body = editComposing.execution = false; window.clearTimeout(draftTimer); controllers.forEach(item => item.abort()); controllers.clear(); state.active = false; state.session = state.detail = state.idea = state.ideaDetail = state.management = null; state.manageDirty = false; managementSequence++; managementView.hidden = true; state.ideas = []; state.messageIds.clear(); messages.replaceChildren(); ideaList.replaceChildren(); detailAttachments.replaceChildren(); root.hidden = true; }, openIdea, showIdeas };
  }
  window.CodexMobileDialogue = Object.freeze({ create });
})();
