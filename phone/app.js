(() => {
  "use strict";
  const VERSION = "__CONSOLE_PHONE_VERSION__";
  const BUILD = "__CONSOLE_PHONE_BUILD__";
  const TASK_SYNC_ENABLED = false;
  let libraryMutationQueue = Promise.resolve();
  const readerImageUrls = new Map();
  const IMAGE_MIME_TYPES = { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif", webp: "image/webp" };

  const el = id => document.getElementById(id);
  const state = { ready: true, generation: 0, busy: false, tab: "work", inbox: "inbox", dashboard: null, reader: null, readerSequence: 0, mutationBusy: false, font: 18, headings: new Map(), library: null, catalog: [], saved: new Set(), pendingImport: null, registration: null, applyingUpdate: false, downloadController: null, music: { tracks: [], selected: null, loaded: false, loading: false, sequence: 0, playSequence: 0, lyricsSequence: 0, tier: "", visible: 60, repeat: "all", lyrics: [], synced: false, activeLine: -1 } };
  const MUSIC_TIERS = [{ value: "first", number: "1", suffix: "st" }, { value: "second", number: "2", suffix: "nd" }, { value: "third", number: "3", suffix: "rd" }];
  const taskSync = { generation: 0, controller: null, timer: null, config: null, busy: false, connected: false };
  let rememberedTransferAddress = "";
  let phoneIncubator = null;
  let incubatorSaving = 0;
  const transferScanner = window.CodexPhoneQrScanner?.create({ video: el("transferQrVideo"), canvas: el("transferQrCanvas"), onResult: acceptTransferQr, onNotice: (message, error) => notice("transferQrNotice", message, error) }) || null;
  const node = (tag, text = "", className = "") => {
    const result = document.createElement(tag);
    if (text) result.textContent = String(text);
    if (className) result.className = className;
    return result;
  };
  function notice(id, message = "", error = false) { el(id).textContent = message; el(id).dataset.error = String(error); }
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
  function imagePath(value, base = "") {
    if (typeof value !== "string") return null;
    let decoded; try { decoded = decodeURIComponent(value); } catch { return null; }
    if (/[#?]/.test(decoded)) return null;
    const relative = pathValue(decoded, base);
    return relative && IMAGE_MIME_TYPES[relative.split(".").at(-1).toLowerCase()] ? relative : null;
  }
  function imageBytes(asset) {
    const data = asset?.data, mimeType = asset?.mimeType;
    if (!asset || typeof asset.path !== "string" || asset.path.includes("#") || pathValue(asset.path) !== asset.path || mimeType !== IMAGE_MIME_TYPES[asset.path.split(".").at(-1).toLowerCase()] || typeof data !== "string" || !data || data.length > 4 * Math.ceil(1024 * 1024 / 3) || data.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(data)) throw new Error("资料图片的路径、格式或大小无效。");
    let decoded; try { decoded = atob(data); } catch { throw new Error("资料图片编码无效。"); }
    if (!decoded.length || decoded.length > 1024 * 1024) throw new Error("每张资料图片不能超过 1 MiB。");
    const value = Uint8Array.from(decoded, char => char.charCodeAt(0)), header = String.fromCharCode(...value.slice(0, 12));
    const valid = mimeType === "image/png" ? value.length >= 33 && header.startsWith("\x89PNG\r\n\x1a\n") && String.fromCharCode(...value.slice(12, 16)) === "IHDR" : mimeType === "image/jpeg" ? value.length >= 4 && value[0] === 255 && value[1] === 216 && value[2] === 255 : mimeType === "image/gif" ? value.length >= 13 && /^(GIF87a|GIF89a)/.test(header) : mimeType === "image/webp" && value.length >= 20 && header.startsWith("RIFF") && header.slice(8) === "WEBP";
    if (!valid) throw new Error("资料图片内容与声明的格式不一致。");
    return value;
  }
  async function validateImageDecoding(library) {
    for (const asset of library.assets || []) {
      const image = node("img"), url = URL.createObjectURL(new Blob([imageBytes(asset)], { type: asset.mimeType }));
      let timer;
      try {
        await new Promise((resolve, reject) => {
          const invalid = () => reject(new Error("资料图片损坏或无法在手机显示，请重新导出截图。"));
          image.onload = () => image.naturalWidth > 0 && image.naturalHeight > 0 && image.naturalWidth <= 16384 && image.naturalHeight <= 16384 && image.naturalWidth * image.naturalHeight <= 32 * 1024 * 1024 ? resolve() : invalid();
          image.onerror = invalid; timer = window.setTimeout(invalid, 10000); image.src = url;
        });
      } finally { window.clearTimeout(timer); image.onload = null; image.onerror = null; image.removeAttribute("src"); URL.revokeObjectURL(url); }
    }
  }
  function releaseReaderImages() { for (const url of readerImageUrls.values()) URL.revokeObjectURL(url); readerImageUrls.clear(); }
  function entries() { return Array.isArray(state.dashboard?.documents?.inbox?.entries) ? state.dashboard.documents.inbox.entries : []; }
  function entryStatus(item) { return ["inbox", "later", "archive"].includes(item?.status) ? item.status : item?.read ? "archive" : "inbox"; }

  async function api(endpoint, payload) {
    if (endpoint === "status") return { ready: true };
    if (endpoint === "dashboard") return state.library?.dashboard || { version: VERSION, plan: { plan: null }, device: {}, documents: { guide: { items: [] }, inbox: { entries: [] }, references: { items: [] } } };
    if (endpoint.startsWith("document?")) {
      const path = new URLSearchParams(endpoint.split("?")[1]).get("path");
      const file = state.library?.files.find(item => item.path === path);
      if (!file) throw new Error("这份文档尚未导入手机，请先更新资料包。");
      return file;
    }
    if (endpoint === "inbox/move") {
      const item = entries().find(entry => entry.id === payload.id);
      if (!item || !["inbox", "later", "archive"].includes(payload.status)) throw new Error("找不到这份阅读记录。");
      const next = await mutateLibrary(next => { next.reading = { ...(next.reading || {}), [item.id]: payload.status }; const entry = next.dashboard.documents.inbox.entries.find(entry => entry.id === payload.id); entry.status = payload.status; entry.read = payload.status === "archive"; }); return next.dashboard.documents.inbox;
    }
    if (endpoint === "music") {
      const local = await PhoneStore.all("music"); state.saved = new Set(await PhoneStore.keys("media"));
      const overrides = new Map(local.map(item => [item.id, item]));
      return { playback: "phone", tracks: [...state.catalog.map(item => ({ ...item, ...(overrides.get(item.path) || {}) })), ...local.filter(item => !state.catalog.some(track => track.path === item.id)).map(item => ({ ...item, path: item.id }))] };
    }
    if (endpoint.startsWith("music/lyrics?")) {
      const query = new URLSearchParams(endpoint.split("?")[1]), path = query.get("path"), language = query.get("language");
      const record = await PhoneStore.get("music", path), lyrics = record?.offlineLyrics || [];
      const selected = lyrics.find(item => item.code === language) || (!language ? lyrics.find(item => item.code === record.lyricsLanguage) || lyrics[0] : null);
      if (!selected) throw new Error("手机还没有保存这个语言的歌词，可以添加本地歌词。");
      return { path, content: selected.content, format: selected.format, language: selected.code };
    }
    throw new Error("离线版没有这个操作。");
  }
  const IDEA_FIELDS = ["title", "body", "stage", "priority", "parentId", "targetKind", "targetThreadId", "targetName"];
  const IDEA_UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
  function incubatorError(message, status = 400, code = "invalid_idea", idea = null) {
    return Object.assign(new Error(message), { status, data: { error: message, code, ...(idea ? { idea } : {}) } });
  }
  function cleanPhoneIdea(value, ideas, identifier) {
    const text = (name, fallback, limit) => { const raw = Object.hasOwn(value, name) ? value[name] : fallback; if (typeof raw !== "string" || raw.length > limit || /\u0000/.test(raw)) throw incubatorError("想法内容的格式或长度无效。"); return raw; };
    const result = { title: text("title", "新想法", 160).trim(), body: text("body", "", 20000), stage: Object.hasOwn(value, "stage") ? value.stage : "vague", priority: Object.hasOwn(value, "priority") ? value.priority : "normal", parentId: value.parentId === "" || value.parentId === undefined ? null : value.parentId, targetKind: Object.hasOwn(value, "targetKind") ? value.targetKind : "none", targetThreadId: text("targetThreadId", "", 128).trim(), targetName: text("targetName", "", 120).trim() };
    if (!result.title || !["vague", "thinking", "ready", "queued", "published"].includes(result.stage) || !["high", "normal", "low"].includes(result.priority) || !["none", "codex", "chatgpt"].includes(result.targetKind)) throw incubatorError("请填写标题并选择有效的阶段、优先级和平台。");
    const seen = new Set(); let parent = result.parentId;
    while (parent !== null) {
      if (typeof parent !== "string" || parent === identifier || seen.has(parent)) throw incubatorError("父想法不能形成循环。", 409, "idea_cycle");
      seen.add(parent); const found = ideas.find(idea => idea.id === parent);
      if (!found) throw incubatorError("找不到归属想法。", 404, "idea_not_found"); parent = found.parentId;
    }
    if (result.targetKind === "none") result.targetThreadId = result.targetName = "";
    else if (result.targetThreadId) {
      if (result.targetKind === "codex" && !IDEA_UUID.test(result.targetThreadId) || result.targetKind === "chatgpt" && !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(result.targetThreadId)) throw incubatorError("目标聊天标识无效。");
      if (result.targetKind === "codex") result.targetThreadId = result.targetThreadId.toLowerCase();
    }
    return result;
  }
  async function incubatorApi(path, payload) {
    if (path === "incubator" && payload === undefined) {
      const saved = await PhoneStore.get("records", "incubator");
      return { ideas: saved?.ideas || [], revision: String(saved?.revision || 0) };
    }
    if (!["incubator/create", "incubator/update"].includes(path) || !payload || typeof payload !== "object" || Array.isArray(payload)) throw incubatorError("此手机工作区只保存想法；不会发送到聊天。");
    const update = path === "incubator/update", allowed = new Set([...IDEA_FIELDS, "requestId", ...(update ? ["id", "expectedRevision"] : [])]);
    if (Object.keys(payload).some(name => !allowed.has(name)) || !IDEA_UUID.test(payload.requestId || "")) throw incubatorError("保存请求无效。");
    if (update && (typeof payload.id !== "string" || !Number.isSafeInteger(payload.expectedRevision) || payload.expectedRevision < 1 || !IDEA_FIELDS.some(name => Object.hasOwn(payload, name)))) throw incubatorError("修改想法须提供当前版本与内容。");
    const signature = JSON.stringify(Object.fromEntries(Object.keys(payload).sort().map(name => [name, payload[name]]))), receiptId = path + ":" + payload.requestId;
    let duplicate = false, ideaId;
    incubatorSaving++;
    try {
      const stored = await PhoneStore.mutateRecord("records", "incubator", previous => {
        const next = structuredClone(previous || { id: "incubator", ideas: [], receipts: {}, revision: 0 }), old = next.receipts[receiptId];
        if (old) {
          if (old.signature !== signature) throw incubatorError("同一保存请求不能换成不同内容。", 409, "request_conflict");
          duplicate = true; ideaId = old.ideaId; return next;
        }
        if (Object.keys(next.receipts).length >= 4096 || !update && next.ideas.length >= 1000) throw incubatorError("此手机保存的想法较多，请先导出备份，当前内容仍保留。", 409, "local_limit");
        const existing = update ? next.ideas.find(idea => idea.id === payload.id) : null;
        if (update && !existing) throw incubatorError("找不到此手机里的想法。", 404, "idea_not_found");
        if (existing && existing.revision !== payload.expectedRevision) throw incubatorError("想法已在另一页修改；当前草稿保留，请刷新后合并。", 409, "revision_conflict", existing);
        ideaId = existing?.id || (globalThis.crypto?.randomUUID?.() || "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, character => { const value = Math.floor(Math.random() * 16); return (character === "x" ? value : (value & 3) | 8).toString(16); })).replaceAll("-", "");
        const now = new Date().toISOString(), idea = { ...cleanPhoneIdea({ ...existing, ...payload }, next.ideas, ideaId), id: ideaId, revision: (existing?.revision || 0) + 1, createdAt: existing?.createdAt || now, updatedAt: now };
        next.ideas = [idea, ...next.ideas.filter(item => item.id !== ideaId)]; next.revision++;
        next.receipts[receiptId] = { signature, ideaId }; return next;
      });
      return { idea: stored.ideas.find(idea => idea.id === ideaId), revision: String(stored.revision), duplicate };
    } finally { incubatorSaving--; window.setTimeout(() => void maybeReloadUpdate(), 0); }
  }
  function ensurePhoneIncubator() {
    if (!phoneIncubator) phoneIncubator = window.CodexIncubatorPanel?.create(el("phoneIncubator"), { phone: true, offline: true, storageKey: "codexIncubator.phone.v1", endpoint: incubatorApi }) || null;
    return phoneIncubator;
  }
  async function openComputerWork() {
    if (rememberedTransferAddress) { await openTransferConnection(true, "work"); return; }
    selectTab("transfer"); notice("transferNotice", "先扫描电脑 Console 的连接二维码，或填写电脑显示的手机地址；配对后打开电脑工作区。");
  }
  function mutateLibrary(change) {
    const pending = libraryMutationQueue.then(async () => { if (!state.library) throw new Error("请先导入资料。"); const next = structuredClone(state.library); change(next); await PhoneStore.put("records", next); state.library = next; state.dashboard = next.dashboard; return next; });
    libraryMutationQueue = pending.catch(() => {}); return pending;
  }



  function failure(error, id = "appNotice") {
    if (error.cancelled) return;
    notice(id, error.name === "QuotaExceededError" ? "手机储存空间不足，已保存的资料仍保留。请先备份并腾出空间。" : error.message || "暂时无法完成，请重试。", true);
  }
  function setBusy(value) {
    state.busy = value; el("refreshButton").disabled = value || state.mutationBusy;
    if (!value) void maybeReloadUpdate();
  }
  async function bootstrap() {
    setBusy(true);
    try {
      state.library = await PhoneStore.get("records", "library") || null;
      try { const response = await fetch("./music-catalog.json"); if (response.ok) { const payload = await response.json(); state.catalog = Array.isArray(payload.tracks) ? payload.tracks : []; } } catch { /* Imported data works even if the first public catalog download is incomplete. */ }
      await refreshDashboard(); await updateStorageNotice(); await restoreTransferConnection();
      el("restoreButton").hidden = !await PhoneStore.get("records", "previousImport");
      if (TASK_SYNC_ENABLED) await restoreTaskSync();
    } catch (error) { failure(error); }
    finally { setBusy(false); }
    void setupWorker();
  }
  async function refreshDashboard() {
    const data = await api("dashboard"); state.dashboard = data; state.ready = true;
    el("appScreen").hidden = false; el("bottomNav").hidden = false;
    el("connectionLabel").textContent = navigator.serviceWorker?.controller ? "本机离线" : "离线准备中"; el("connectionLabel").dataset.connected = "true";
    el("updatedLabel").textContent = `本版 v${VERSION}`;
    renderPlan(data.plan); renderDevice(data.device); renderDocuments(); selectTab(state.tab); notice("appNotice");
  }
  async function refresh() {
    if (state.busy || state.mutationBusy) return; setBusy(true);
    try { await libraryMutationQueue; state.library = await PhoneStore.get("records", "library") || null; await refreshDashboard(); if (TASK_SYNC_ENABLED && taskSync.config?.token) await pollTaskSync(); if (state.tab === "music") await loadMusic(true); }
    catch (error) { failure(error); } finally { setBusy(false); }
  }
  function selectTab(value) {
    value = ({ tasks: "work", device: "materials", documents: "materials" })[value] || value;
    if (value !== "transfer") transferScanner?.stop();
    if (!["work", "music", "materials", "transfer"].includes(value)) return;
    state.tab = value;
    el("appToolbar").hidden = value === "music";
    el("taskSyncSection").hidden = !TASK_SYNC_ENABLED;
    for (const tab of ["work", "music", "materials", "transfer"]) el(`${tab}Panel`).hidden = tab !== value;
    for (const button of document.querySelectorAll("[data-tab]")) button.setAttribute("aria-pressed", String(button.dataset.tab === value));
    if (value === "music" && state.ready && !state.music.loaded) void loadMusic();
    ensurePhoneIncubator()?.setActive(value === "work");
  }
  function validateImport(data) {
    const text = (value, limit, label) => { if (typeof value !== "string" || value.length > limit) throw new Error(`${label}格式或大小不正确。`); return value; };
    const path = value => { const result = pathValue(value); if (!result || result !== value) throw new Error("资料包含有无效的文档路径。"); return result; };
    const id = value => { if (typeof value !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/.test(value)) throw new Error("资料编号无效。"); return value; };
    const phoneBackup = data?.format === "codex-console-phone-backup";
    const documentsOnly = data?.format === "codex-console-phone-data" && data.importScope === "documents";
    if (!data || !["codex-console-phone-data", "codex-console-phone-backup"].includes(data.format) || data.schemaVersion !== 1 || !data.dashboard || !Array.isArray(data.files) || data.files.length > 200) throw new Error("请选择 Console 导出的资料 JSON，或手机资料备份。");
    if (data.importScope !== undefined && !documentsOnly) throw new Error("资料包的导入范围无效。");
    text(data.exportedAt, 60, "导出时间"); if (Number.isNaN(new Date(data.exportedAt).getTime())) throw new Error("导出时间无效。");
    const dashboard = structuredClone(data.dashboard), plan = documentsOnly ? null : dashboard.plan?.plan, taskIds = new Set();
    const synced = phoneBackup && data.phoneState?.planSnapshot ? validatePlanSnapshot(data.phoneState.planSnapshot) : null;
    if (synced && JSON.stringify(validatePlanSnapshot({ ...synced, plan }).plan) !== JSON.stringify(synced.plan)) throw new Error("备份的电脑任务与来源快照不一致。");
    if (plan) {
      if (!Array.isArray(plan.groups) || (synced ? plan.groups.length < 1 || plan.groups.length > 12 : plan.groups.length !== 4)) throw new Error("资料包应包含四项主要计划。");
      let total = 0; const groupIds = new Set();
      for (const group of plan.groups) {
        if (!group || groupIds.has(id(group.id)) || !Array.isArray(group.items) || group.items.length > 100) throw new Error("计划分组无效。"); groupIds.add(group.id); text(group.title, 120, "计划标题"); text(group.summary || "", 240, "计划摘要");
        total += group.items.length; if (total > 300) throw new Error("计划清单过长。");
        for (const item of group.items) { if (!item || taskIds.has(id(item.id)) || typeof item.done !== "boolean") throw new Error("计划项编号或状态无效。"); taskIds.add(item.id); text(item.text, 500, "计划项"); }
      }
    }
    const documents = dashboard.documents; if (!documents || !Array.isArray(documents.guide?.items) || !Array.isArray(documents.inbox?.entries) || !Array.isArray(documents.references?.items)) throw new Error("资料包的文档索引无效。");
    if (documents.guide.items.length > 50 || documents.inbox.entries.length > 5000 || documents.references.items.length > 100) throw new Error("文档索引过长。");
    const registered = new Set(), reportIds = new Set(), requiredFiles = new Set();
    for (const item of documents.guide.items) { registered.add(path(item.path)); text(item.title, 160, "文档标题"); text(item.summary || "", 600, "文档摘要"); if (!Array.isArray(item.highlights) || item.highlights.length > 8) throw new Error("文档重点无效。"); item.highlights.forEach(value => text(value, 240, "重点")); }
    for (const item of documents.guide.items) requiredFiles.add(item.path);
    for (const item of documents.inbox.entries) { if (reportIds.has(id(item.id))) throw new Error("阅读编号重复。"); reportIds.add(item.id); registered.add(path(item.path)); requiredFiles.add(item.path); text(item.title, 240, "报告标题"); text(item.summary || "", 2000, "报告摘要"); if (item.status !== undefined ? !["inbox", "later", "archive"].includes(item.status) : typeof item.read !== "boolean") throw new Error("阅读状态无效。"); }
    for (const item of documents.references.items) {
      id(item.id); if (!Array.isArray(item.variants) || item.variants.length < 1 || item.variants.length > 2) throw new Error("参考资料语言无效。");
      for (const variant of item.variants) { registered.add(path(variant.path)); if (variant.available !== false) requiredFiles.add(variant.path); text(variant.title, 160, "参考标题"); text(variant.summary || "", 600, "参考摘要"); text(variant.label, 40, "语言标签"); if (!["zh-CN", "en"].includes(variant.language)) throw new Error("参考语言无效。"); }
    }
    const files = [], filePaths = new Set(); let characters = 0;
    for (const file of data.files) {
      const relative = path(file.path); if (!registered.has(relative) || filePaths.has(relative)) throw new Error("资料包包含未登记或重复的文档。"); filePaths.add(relative); text(file.content, 2 * 1024 * 1024, "文档正文"); characters += file.content.length; if (characters > 16 * 1024 * 1024) throw new Error("资料包正文超过手机导入限制，请减少文档数量。");
      files.push({ path: relative, name: text(file.name || relative.split("/").at(-1), 255, "文件名"), content: file.content, format: file.format === "markdown" ? "markdown" : "text", modifiedAt: text(file.modifiedAt || "", 60, "文件时间") });
    }
    for (const path of requiredFiles) if (!filePaths.has(path)) throw new Error("资料包缺少已登记的文档正文，请重新从电脑导出。");
    const assets = [], assetPaths = new Set(); let assetBytes = 0;
    if (data.assets !== undefined && (!Array.isArray(data.assets) || data.assets.length > 200)) throw new Error("资料图片清单无效或过长。");
    for (const asset of data.assets || []) {
      const value = imageBytes(asset), key = asset.path.toLowerCase();
      if (assetPaths.has(key)) throw new Error("资料包包含重复的图片。");
      assetPaths.add(key); assetBytes += value.length; if (assetBytes > 8 * 1024 * 1024) throw new Error("资料图片总大小不能超过 8 MiB，请减少截图。");
      assets.push({ path: asset.path, mimeType: asset.mimeType, data: asset.data });
    }
    const device = dashboard.device || {}, memory = device.currentMemory || {};
    dashboard.device = { model: String(device.model || "").slice(0, 200), cpuModel: String(device.cpuModel || "").slice(0, 500), gpuModels: (Array.isArray(device.gpuModels) ? device.gpuModels : []).slice(0, 8).map(value => String(value).slice(0, 200)), installedMemoryBytes: Number.isFinite(device.installedMemoryBytes) ? device.installedMemoryBytes : null, sampledAt: String(device.sampledAt || "").slice(0, 60), currentMemory: { status: memory.status === "available" ? "available" : "unavailable", readAt: String(memory.readAt || "").slice(0, 60), usedPercent: memory.usedPercent, totalBytes: memory.totalBytes, availableBytes: memory.availableBytes } };
    dashboard.plan = { plan: synced?.plan || plan || null }; delete documents.records;
    const library = { id: "library", exportedAt: data.exportedAt, importedAt: new Date().toISOString(), dashboard, files, assets, reading: data.phoneState?.reading || {}, taskDone: data.phoneState?.taskDone || {} };
    if (documentsOnly) { library.importScope = "documents"; library.dashboard.device = {}; library.taskDone = {}; }
    if (synced) library.planSync = { computerId: synced.computerId, hash: synced.hash, updatedAt: synced.updatedAt, syncedAt: new Date().toISOString(), readonly: true };
    if (phoneBackup && data.phoneState?.localTaskBackup) library.localTaskBackup = validateLocalTaskBackup(data.phoneState.localTaskBackup);
    return library;
  }
  function mergeLibrary(next, previous) {
    if (next.importScope === "documents") {
      const merged = structuredClone(previous || emptyLibrary()), previousDocuments = merged.dashboard.documents, incomingDocuments = next.dashboard.documents;
      const pathKey = item => item.path.toLowerCase();
      const combine = (existing = [], incoming = [], key) => { const replacements = new Map(incoming.map(item => [key(item), item])), oldKeys = new Set(existing.map(key)); return [...existing.map(item => replacements.get(key(item)) || item), ...incoming.filter(item => !oldKeys.has(key(item)))]; };
      const oldEntries = new Map(previousDocuments.inbox.entries.map(item => [item.id, item]));
      merged.dashboard.documents = {
        guide: { ...previousDocuments.guide, ...incomingDocuments.guide, items: combine(previousDocuments.guide.items, incomingDocuments.guide.items, pathKey) },
        inbox: { ...previousDocuments.inbox, ...incomingDocuments.inbox, entries: combine(previousDocuments.inbox.entries, incomingDocuments.inbox.entries, item => item.id) },
        references: { ...previousDocuments.references, ...incomingDocuments.references, items: combine(previousDocuments.references.items, incomingDocuments.references.items, item => item.id) }
      };
      merged.reading = { ...(merged.reading || {}) };
      for (const entry of merged.dashboard.documents.inbox.entries) {
        const old = oldEntries.get(entry.id), status = merged.reading?.[entry.id] || (old ? entryStatus(old) : next.reading?.[entry.id] || entryStatus(entry));
        entry.status = status; entry.read = status === "archive"; merged.reading[entry.id] = status;
      }
      merged.files = combine(merged.files, next.files, pathKey); merged.assets = combine(merged.assets, next.assets, pathKey);
      const documents = merged.dashboard.documents;
      if (merged.files.length > 200 || merged.assets.length > 200 || documents.guide.items.length > 50 || documents.inbox.entries.length > 5000 || documents.references.items.length > 100) throw new Error("合并后的资料数量超过手机限制，原资料保留。请先备份并减少旧资料。");
      const pictureBytes = merged.assets.reduce((total, asset) => total + asset.data.length * 3 / 4 - (asset.data.endsWith("==") ? 2 : asset.data.endsWith("=") ? 1 : 0), 0);
      if (pictureBytes > 8 * 1024 * 1024 || merged.files.reduce((total, file) => total + file.content.length, 0) > 16 * 1024 * 1024) throw new Error("合并后的资料超过手机保存限制，原资料保留。请先备份并减少旧资料。");
      merged.exportedAt = next.exportedAt; merged.importedAt = next.importedAt; delete merged.importScope; return merged;
    }
    const reading = {}, taskDone = {};
    for (const entry of next.dashboard.documents.inbox.entries) { const status = previous?.reading?.[entry.id] || next.reading?.[entry.id]; if (["inbox", "later", "archive"].includes(status)) { reading[entry.id] = status; entry.status = status; entry.read = status === "archive"; } }
    for (const group of next.dashboard.plan?.plan?.groups || []) for (const item of group.items) { const old = previous?.taskDone?.[item.id], restored = next.taskDone?.[item.id]; if (typeof old === "boolean") taskDone[item.id] = old; else if (typeof restored === "boolean") taskDone[item.id] = restored; }
    return { ...next, reading, taskDone };
  }
  function validatePlanSnapshot(value) {
    const bounded = (value, limit) => typeof value === "string" && value.length <= limit;
    const identifier = value => bounded(value, 160) && /^[A-Za-z0-9][A-Za-z0-9._:-]*$/.test(value);
    if (!value || value.format !== "codex-console-plan-snapshot" || value.schemaVersion !== 1 || !/^[a-f0-9]{64}$/.test(value.hash || "") || !identifier(value.computerId) || !bounded(value.updatedAt, 60) || Number.isNaN(Date.parse(value.updatedAt))) throw new Error("电脑计划快照无效。");
    const plan = value.plan, groups = new Set(), tasks = new Set(); let count = 0;
    if (!plan || plan.version !== 1 || !identifier(plan.revision) || !Array.isArray(plan.groups) || plan.groups.length < 1 || plan.groups.length > 12) throw new Error("电脑计划分组无效。");
    for (const group of plan.groups) {
      if (!group || !identifier(group.id) || groups.has(group.id) || !bounded(group.title, 120) || !group.title.trim() || !bounded(group.summary || "", 240) || !Array.isArray(group.items) || group.items.length > 100) throw new Error("电脑计划分组无效。"); groups.add(group.id);
      count += group.items.length; if (count > 300) throw new Error("电脑计划清单过长。");
      for (const item of group.items) { if (!item || !identifier(item.id) || tasks.has(item.id) || !bounded(item.text, 500) || !item.text.trim() || typeof item.done !== "boolean") throw new Error("电脑计划项无效。"); tasks.add(item.id); }
    }
    return { format: value.format, schemaVersion: 1, hash: value.hash, updatedAt: value.updatedAt, computerId: value.computerId, plan: { version: 1, revision: plan.revision, groups: plan.groups.map(group => ({ id: group.id, title: group.title, summary: group.summary || "", items: group.items.map(item => ({ id: item.id, text: item.text, done: item.done })) })) } };
  }
  function validateLocalTaskBackup(value) {
    if (!value || typeof value.backedUpAt !== "string" || value.backedUpAt.length > 60 || Number.isNaN(Date.parse(value.backedUpAt)) || !value.taskDone || typeof value.taskDone !== "object" || Array.isArray(value.taskDone) || Object.keys(value.taskDone).length > 300) throw new Error("原手机勾选备份无效。");
    const taskDone = {};
    for (const [id, done] of Object.entries(value.taskDone)) { if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/.test(id) || typeof done !== "boolean") throw new Error("原手机勾选备份无效。"); taskDone[id] = done; }
    const plan = value.plan?.plan ? validatePlanSnapshot({ format: "codex-console-plan-snapshot", schemaVersion: 1, hash: "0".repeat(64), updatedAt: value.backedUpAt, computerId: "local-backup", plan: value.plan.plan }).plan : null;
    return { plan: { plan }, taskDone, backedUpAt: value.backedUpAt };
  }
  function emptyLibrary() {
    return { id: "library", exportedAt: new Date().toISOString(), importedAt: new Date().toISOString(), dashboard: { version: VERSION, plan: { plan: null }, device: {}, documents: { guide: { items: [] }, inbox: { entries: [] }, references: { items: [] } } }, files: [], reading: {}, taskDone: {} };
  }
  function applyPlanSnapshot(value, generation = null) {
    const snapshot = validatePlanSnapshot(value);
    const pending = libraryMutationQueue.then(async () => {
      if (generation !== null && generation !== taskSync.generation) return false;
      if (state.library?.planSync?.hash === snapshot.hash && state.library.planSync.computerId === snapshot.computerId) return false;
      const previous = state.library ? structuredClone(state.library) : null, next = structuredClone(previous || emptyLibrary());
      if (!next.localTaskBackup) next.localTaskBackup = { plan: structuredClone(next.dashboard.plan), taskDone: structuredClone(next.taskDone || {}), backedUpAt: new Date().toISOString() };
      next.dashboard.plan = { plan: snapshot.plan };
      next.planSync = { hash: snapshot.hash, updatedAt: snapshot.updatedAt, computerId: snapshot.computerId, syncedAt: new Date().toISOString(), readonly: true };
      await PhoneStore.put("records", next);
      if (generation !== null && generation !== taskSync.generation) { if (previous) await PhoneStore.put("records", previous); else await PhoneStore.remove("records", "library"); return false; }
      state.library = next; state.dashboard = next.dashboard; renderPlan(next.dashboard.plan); return true;
    });
    libraryMutationQueue = pending.catch(() => {}); return pending;
  }
  function syncAddress(value) {
    let url; try { url = new URL(String(value).trim()); } catch { throw new Error("请输入电脑显示的完整手机地址。"); }
    const parts = url.hostname.split(".").map(Number), privateAddress = parts.length === 4 && parts.every(part => Number.isInteger(part) && part >= 0 && part <= 255) && (parts[0] === 10 || parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31 || parts[0] === 192 && parts[1] === 168);
    if (url.protocol !== "http:" || !privateAddress || url.username || url.password || url.search || url.hash || !["/", "/mobile.html"].includes(url.pathname)) throw new Error("请使用电脑显示的同 Wi-Fi 手机地址，不要使用公网、localhost 或其他网页地址。");
    return url.origin;
  }
  function parseTransferAddress(value, allowPairing = false) {
    let url; try { url = new URL(String(value).trim()); } catch { throw new Error("请输入电脑显示的完整手机地址。"); }
    const parts = url.hostname.split(".").map(Number);
    const privateAddress = parts.length === 4 && parts.every(part => Number.isInteger(part) && part >= 0 && part <= 255) && (parts[0] === 10 || parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31 || parts[0] === 192 && parts[1] === 168);
    const consoleName = /^codex-[a-z0-9]{8,64}\.local$/.test(url.hostname);
    const validQuery = !url.search || url.search === "?tab=transfer";
    let pairing = "";
    if (url.hash && allowPairing) {
      const params = new URLSearchParams(url.hash.slice(1)), entries = [...params];
      if (entries.length === 1 && entries[0][0] === "qrToken" && /^[A-Za-z0-9_-]{32,128}$/.test(entries[0][1])) pairing = `#qrToken=${entries[0][1]}`;
      else if (entries.length === 1 && entries[0][0] === "pair" && /^\d{6}$/.test(entries[0][1])) pairing = `#pair=${entries[0][1]}`;
      else throw new Error("二维码连接信息无效，请扫描电脑 Console 显示的新二维码。");
    }
    if (url.protocol !== "http:" || !(privateAddress || consoleName) || url.username || url.password || !validQuery || (url.hash && !allowPairing) || !["/", "/mobile.html"].includes(url.pathname)) throw new Error("请使用电脑 Console 的同 Wi-Fi 连接二维码或地址。");
    return { address: url.origin + "/?tab=transfer", pairing };
  }
  function transferAddress(value) { return parseTransferAddress(value).address; }
  function renderTransferConnection(address) {
    rememberedTransferAddress = address; el("transferAddress").value = address;
    el("transferRemembered").hidden = !address; el("transferForget").hidden = !address;
    el("transferComputerName").textContent = address ? `已保存电脑入口 · ${new URL(address).hostname}` : "";
    el("computerWorkOpen").textContent = address ? "打开电脑工作区" : "连接电脑工作区";
    el("transferScan").textContent = address ? "扫描新的电脑二维码" : "扫码连接电脑";
  }
  async function restoreTransferConnection() {
    try {
      const saved = await PhoneStore.get("settings", "transferConnection");
      if (saved?.address) renderTransferConnection(transferAddress(saved.address));
    } catch { /* A remembered address is optional; private offline data stays independent. */ }
  }
  async function saveTransferConnection(address) {
    try { await PhoneStore.put("settings", { id: "transferConnection", address }); } catch { /* Opening works even when preferences cannot be saved. */ }
    renderTransferConnection(address);
  }
  async function openTransferConnection(useRemembered = false, view = "transfer") {
    try {
      const address = transferAddress(useRemembered ? rememberedTransferAddress : el("transferAddress").value);
      transferScanner?.stop(); await saveTransferConnection(address);
      const target = new URL(address);
      if (view === "work") target.searchParams.set("tab", "work");
      window.location.href = target.href;
    } catch (error) { failure(error, "transferNotice"); }
  }
  async function acceptTransferQr(value) {
    const parsed = parseTransferAddress(value, true);
    transferScanner?.stop(); await saveTransferConnection(parsed.address);
    if (el("transferQrDialog").open) el("transferQrDialog").close();
    window.location.href = parsed.address + parsed.pairing;
  }
  function scanTransferConnection() {
    if (!transferScanner) { notice("transferNotice", "扫码组件尚未加载，请检查程序更新；也可以从备用入口选择二维码照片或填写地址。", true); return; }
    if (!el("transferQrDialog").open) el("transferQrDialog").showModal();
    void transferScanner.start();
  }
  async function forgetTransferConnection() {
    try {
      await PhoneStore.remove("settings", "transferConnection"); renderTransferConnection("");
      notice("transferNotice", "电脑入口已清除。要撤销手机配对，可在电脑的连接设置中忘记设备。");
    } catch (error) { failure(error, "transferNotice"); }
  }
  function supportsTaskSync(address) {
    if (!TASK_SYNC_ENABLED) return false;
    try { return typeof Request === "function" && new Request(address + "/api/phone/plan-sync/plan", { targetAddressSpace: "local" }).targetAddressSpace === "local"; } catch { return false; }
  }
  function updateSyncFallback() {
    if (!TASK_SYNC_ENABLED) return;
    try { el("syncFallback").href = syncAddress(el("syncAddress").value) + "/mobile.html"; el("syncFallback").hidden = false; }
    catch { el("syncFallback").hidden = true; el("syncFallback").removeAttribute("href"); }
  }
  function renderSyncState(message = "", error = false) {
    if (!TASK_SYNC_ENABLED) return;
    const active = Boolean(taskSync.config?.token);
    el("syncDisconnect").hidden = !active; el("syncConnect").disabled = taskSync.busy;
    el("syncSummary").textContent = taskSync.connected ? "已连接 · 自动更新" : active ? "保留上次同步" : "电脑 → 手机";
    el("syncFallbackHelp").hidden = taskSync.connected;
    if (message) notice("syncNotice", message, error);
  }
  function stopSyncRequests() {
    taskSync.generation += 1; taskSync.controller?.abort(); taskSync.controller = null; window.clearTimeout(taskSync.timer); taskSync.timer = null; taskSync.busy = false; taskSync.connected = false;
  }
  async function syncRequest(config, endpoint, payload, generation) {
    if (!TASK_SYNC_ENABLED) throw Object.assign(new Error("任务同步暂未启用。"), { cancelled: true });
    const controller = new AbortController(); taskSync.controller = controller;
    const timeout = window.setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(config.address + "/api/phone/plan-sync/" + endpoint, { method: payload === undefined ? "GET" : "POST", mode: "cors", credentials: "omit", redirect: "error", cache: "no-store", targetAddressSpace: "local", signal: controller.signal, headers: { Accept: "application/json", "X-Codex-Phone": "1", ...(config.token ? { Authorization: "Bearer " + config.token } : {}), ...(payload === undefined ? {} : { "Content-Type": "application/json" }) }, ...(payload === undefined ? {} : { body: JSON.stringify(payload) }) });
      if (generation !== taskSync.generation) throw Object.assign(new Error("已取消旧电脑的请求。"), { cancelled: true });
      if (response.status === 401) throw Object.assign(new Error("配对已过期，请输入电脑的新配对码。"), { auth: true });
      const body = await response.json(); if (!response.ok) throw new Error(body.error || "电脑暂时没有可读取的任务。"); return body;
    } finally { window.clearTimeout(timeout); if (taskSync.controller === controller) taskSync.controller = null; }
  }
  function scheduleTaskSync(generation) {
    window.clearTimeout(taskSync.timer); taskSync.timer = null;
    if (!TASK_SYNC_ENABLED) return;
    if (generation === taskSync.generation && taskSync.config?.token && !document.hidden) taskSync.timer = window.setTimeout(() => { taskSync.timer = null; void pollTaskSync(); }, 5000);
  }
  async function pollTaskSync() {
    if (!TASK_SYNC_ENABLED || taskSync.busy || document.hidden || !taskSync.config?.token) return;
    const generation = taskSync.generation, config = { ...taskSync.config }; taskSync.busy = true;
    try {
      if (config.expiresAt <= Date.now()) throw Object.assign(new Error("配对已过期，请输入电脑的新配对码。"), { auth: true });
      const snapshot = validatePlanSnapshot(await syncRequest(config, "plan", undefined, generation));
      if (generation !== taskSync.generation) return;
      if (snapshot.computerId !== config.computerId) throw Object.assign(new Error("电脑来源已改变，请重新配对。"), { auth: true });
      await applyPlanSnapshot(snapshot, generation); if (generation !== taskSync.generation) return;
      taskSync.connected = true; renderSyncState(`已同步 · ${date(snapshot.updatedAt)}。电脑修改后，会在这里自动更新。`); renderPlan(state.library?.dashboard.plan);
    } catch (error) {
      if (generation !== taskSync.generation || error.cancelled) return;
      taskSync.connected = false;
      if (error.auth) { taskSync.config = { address: config.address }; await PhoneStore.put("settings", { id: "taskSync", ...taskSync.config }); }
      renderSyncState(error.auth ? error.message : error.name === "QuotaExceededError" ? "手机储存空间不足，原来的计划和音乐保留。请先腾出空间。" : "暂时连不上电脑，最后一次计划已保留。可重试或打开实时计划。", true); renderPlan(state.library?.dashboard.plan);
    } finally { if (generation === taskSync.generation) { taskSync.busy = false; renderSyncState(); scheduleTaskSync(generation); } }
  }
  async function connectTaskSync() {
    if (!TASK_SYNC_ENABLED) return;
    let address; try { address = syncAddress(el("syncAddress").value); } catch (error) { failure(error, "syncNotice"); return; }
    updateSyncFallback(); const code = el("syncCode").value.trim();
    if (!/^\d{6}$/.test(code)) { notice("syncNotice", "请输入电脑显示的 6 位配对码。", true); return; }
    stopSyncRequests(); const generation = taskSync.generation; taskSync.config = { address }; taskSync.busy = true; renderSyncState("正在连接电脑…");
    try {
      await PhoneStore.put("settings", { id: "taskSync", address });
      if (!supportsTaskSync(address)) { renderSyncState("这个浏览器暂不支持 App 内直接同步，请点「打开实时计划」。原 App 的离线计划和音乐仍保留。", true); return; }
      const paired = await syncRequest({ address }, "pair", { code }, generation);
      if (generation !== taskSync.generation) return;
      if (typeof paired.token !== "string" || !/^[A-Za-z0-9_-]{32,160}$/.test(paired.token) || !Number.isFinite(paired.expiresIn) || paired.expiresIn <= 0 || paired.expiresIn > 28800 || typeof paired.computerId !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/.test(paired.computerId)) throw new Error("电脑的配对响应无效。");
      taskSync.config = { address, token: paired.token, expiresAt: Date.now() + paired.expiresIn * 1000, computerId: paired.computerId };
      await PhoneStore.put("settings", { id: "taskSync", ...taskSync.config });
    } catch (error) { if (generation === taskSync.generation) renderSyncState(error.auth ? error.message : "连接未完成；原来的资料仍保留。可点「打开实时计划」使用。", true); }
    finally { el("syncCode").value = ""; if (generation === taskSync.generation) { taskSync.busy = false; renderSyncState(); } }
    if (generation === taskSync.generation && taskSync.config?.token) await pollTaskSync();
  }
  async function disconnectTaskSync(logout = true) {
    if (!TASK_SYNC_ENABLED) { stopSyncRequests(); return; }
    const config = taskSync.config; stopSyncRequests(); taskSync.config = config?.address ? { address: config.address } : null;
    await PhoneStore.remove("settings", "taskSync"); renderSyncState("自动同步已断开，最后一次计划仍保留。"); renderPlan(state.library?.dashboard.plan);
    if (logout && config?.token) { try { await syncRequest(config, "logout", {}, taskSync.generation); } catch { /* Local revocation succeeds even if the PC cannot be reached. */ } }
  }
  async function restoreTaskSync() {
    if (!TASK_SYNC_ENABLED) return;
    const saved = await PhoneStore.get("settings", "taskSync"); if (!saved?.address) return;
    try { saved.address = syncAddress(saved.address); } catch { return; }
    el("syncAddress").value = saved.address; updateSyncFallback(); taskSync.config = saved;
    if (typeof saved.token !== "string" || !/^[A-Za-z0-9_-]{32,160}$/.test(saved.token) || !Number.isFinite(saved.expiresAt) || typeof saved.computerId !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/.test(saved.computerId) || !supportsTaskSync(saved.address)) { taskSync.config = { address: saved.address }; renderSyncState("可点「打开实时计划」连接电脑。离线 App 保留已有计划。", true); return; }
    void pollTaskSync();
  }
  async function reviewImport(file) {
    state.reviewingImport = (state.reviewingImport || 0) + 1;
    const sequence = state.importReviewSequence = (state.importReviewSequence || 0) + 1;
    try {
      state.pendingImport = null; state.pendingSnapshot = null; el("importReview").hidden = true;
      if (!file || file.size > 24 * 1024 * 1024) throw new Error("资料包超过 24 MiB，请在电脑减少要导出的文档。");
      const data = JSON.parse(await file.text());
      if (sequence !== state.importReviewSequence) return;
      if (data?.format === "codex-console-plan-snapshot") { const snapshot = validatePlanSnapshot(data); state.pendingSnapshot = snapshot; el("importCounts").textContent = `${snapshot.plan.groups.length} 项主要计划 · ${snapshot.plan.groups.reduce((total, group) => total + group.items.length, 0)} 个细项。电脑保存于 ${date(snapshot.updatedAt)}。`; el("importReviewHelp").textContent = "只更新任务，以电脑记录为准。文档、阅读状态和音乐保留；原手机勾选保存为备份。"; el("importReview").hidden = false; return; }
      const library = validateImport(data); await validateImageDecoding(library); if (sequence !== state.importReviewSequence) return;
      state.pendingImport = library; const documentsOnly = library.importScope === "documents";
      el("importReviewHelp").textContent = documentsOnly ? "合并图文资料，保留手机现有任务、其他文档、阅读状态和音乐。不会上传到 GitHub。" : "更新资料并保留这台手机的任务勾选与阅读状态。不会上传到 GitHub。";
      const groups = library.dashboard.plan?.plan?.groups || []; el("importCounts").textContent = `${documentsOnly ? "" : `${groups.length} 项主要计划 · ${groups.reduce((total, group) => total + group.items.length, 0)} 个细项 · `}${library.files.length} 份文档${library.assets.length ? ` · ${library.assets.length} 张图片` : ""}。导出于 ${date(library.exportedAt)}。`;
      el("importReview").hidden = false; notice("settingsNotice");
    } finally { state.reviewingImport -= 1; void maybeReloadUpdate(); }
  }
  async function commitImport() {
    if (state.busy || !state.pendingImport && !state.pendingSnapshot) return; el("importConfirm").disabled = true; setBusy(true);
    if (state.pendingSnapshot) { try { await disconnectTaskSync(false); await applyPlanSnapshot(state.pendingSnapshot); state.pendingSnapshot = null; el("importReview").hidden = true; notice("settingsNotice", "电脑任务快照已保存；文档、阅读状态和音乐保留。"); } catch (error) { failure(error, "settingsNotice"); } finally { el("importConfirm").disabled = false; setBusy(false); } return; }
    try {
      const incoming = state.pendingImport; if (incoming.importScope !== "documents") await disconnectTaskSync(false);
      const pending = libraryMutationQueue.then(async () => { const next = mergeLibrary(incoming, state.library); await PhoneStore.replaceLibrary(next); state.library = next; return next; });
      libraryMutationQueue = pending.catch(() => {}); await pending;
      state.pendingImport = null; closeReader(false); await refreshDashboard(); el("importReview").hidden = true; el("restoreButton").hidden = false; notice("settingsNotice", "资料已保存到手机；本机勾选和阅读状态已保留。"); await updateStorageNotice();
    }
    catch (error) { failure(error, "settingsNotice"); } finally { el("importConfirm").disabled = false; setBusy(false); }
  }
  async function backupLibrary() {
    await libraryMutationQueue;
    if (!state.library) { notice("settingsNotice", "还没有导入资料。", true); return; }
    const phoneState = { reading: state.library.reading, taskDone: state.library.planSync ? {} : state.library.taskDone };
    if (state.library.planSync) phoneState.planSnapshot = validatePlanSnapshot({ format: "codex-console-plan-snapshot", schemaVersion: 1, ...state.library.planSync, plan: state.library.dashboard.plan.plan });
    if (state.library.localTaskBackup) phoneState.localTaskBackup = validateLocalTaskBackup(state.library.localTaskBackup);
    const payload = { format: "codex-console-phone-backup", schemaVersion: 1, exportedAt: new Date().toISOString(), dashboard: state.library.dashboard, files: state.library.files, ...(state.library.assets?.length ? { assets: state.library.assets } : {}), phoneState };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" })), anchor = node("a"); anchor.href = url; anchor.download = `Codex-Console-手机资料-${new Date().toISOString().slice(0, 10)}.json`; document.body.append(anchor); anchor.click(); anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 60000); notice("settingsNotice", "资料备份已准备，音频仍保留在手机和原文件中。");
  }
  async function updateStorageNotice() {
    try { if (navigator.storage?.estimate) { const value = await navigator.storage.estimate(); el("storageNotice").textContent = `本机资料使用约 ${bytes(value.usage)}${value.quota ? `，可用配额约 ${bytes(Math.max(0, value.quota - value.usage))}` : ""}。`; } }
    catch { el("storageNotice").textContent = "资料保存在这台手机，可随时导出备份。"; }
  }
  async function requestPersistence() { try { if (navigator.storage?.persist) await navigator.storage.persist(); } catch { /* Storage availability is checked on every write. */ } }
  function updateIsIdle() {
    return !state.busy && !state.mutationBusy && !incubatorSaving && (phoneIncubator?.canReload?.() ?? true) && !state.mediaSaving && !state.reviewingImport && !state.downloadController && !state.pendingImport && !state.pendingSnapshot && el("musicAudio").paused;
  }
  async function maybeReloadUpdate() {
    if (!state.updatePending || state.reloadingUpdate) return;
    el("applyUpdate").hidden = false;
    if (!updateIsIdle()) { notice("updateNotice", "新版已准备，播放或保存结束后会自动更新。"); return; }
    state.reloadingUpdate = true;
    let pending;
    do { pending = libraryMutationQueue; await pending; } while (pending !== libraryMutationQueue);
    if (!updateIsIdle()) { state.reloadingUpdate = false; return; }
    window.location.reload();
  }
  function prepareWaitingUpdate() {
    if (!state.registration?.waiting) return;
    el("applyUpdate").hidden = false;
    state.registration.waiting.postMessage({ type: "APPLY_UPDATE" });
  }
  async function setupWorker() {
    if (!navigator.serviceWorker) { notice("updateNotice", "这个浏览器暂时不支持离线程序，请使用新版 iPhone Safari。", true); return; }
    try {
      if (!state.workerEventsBound) {
        state.workerEventsBound = true;
        let previousController = navigator.serviceWorker.controller;
        navigator.serviceWorker.addEventListener("controllerchange", () => {
          const controller = navigator.serviceWorker.controller;
          if (previousController && controller !== previousController) state.updatePending = true;
          previousController = controller;
          updateMusicControls(); void maybeReloadUpdate();
        });
        navigator.serviceWorker.addEventListener("message", event => {
          if (event.data?.type !== "CONSOLE_SHELL_UPDATED") return;
          event.ports?.[0]?.postMessage({ handled: true });
          if (event.data.buildId !== BUILD) { state.updatePending = true; void maybeReloadUpdate(); }
        });
      }
      state.registration = await navigator.serviceWorker.register("./sw.js", { scope: "./", updateViaCache: "none" });
      const watch = () => prepareWaitingUpdate();
      watch(); state.registration.addEventListener("updatefound", () => state.registration.installing?.addEventListener("statechange", watch));
      await navigator.serviceWorker.ready; updateMusicControls();
      el("connectionLabel").textContent = "本机离线";
      if (!state.updatePending) notice("updateNotice", "离线程序已保存，联网打开时会自动检查更新。");
      await checkUpdate({ automatic: true });
    } catch { notice("updateNotice", "离线程序尚未完整保存。首次使用请联网后重开一次。", true); }
  }
  async function checkUpdate({ automatic = false } = {}) {
    if (state.updatePromise) return state.updatePromise;
    if (automatic && (navigator.onLine === false || document.hidden || Date.now() - (state.lastUpdateCheck || 0) < 30000)) return;
    state.lastUpdateCheck = Date.now();
    state.updatePromise = (async () => {
      el("checkUpdate").disabled = true;
      if (!automatic) notice("updateNotice", "正在检查程序更新…");
      const controller = new AbortController(), timeout = window.setTimeout(() => controller.abort(), 8000);
      try {
        const response = await fetch("./version.json", { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error(); const data = await response.json();
        if (typeof data.version !== "string" || typeof data.buildId !== "string") throw new Error();
        await state.registration?.update();
        if (!state.updatePending) notice("updateNotice", data.version === VERSION && data.buildId === BUILD ? `当前已是 v${VERSION}。` : `正在更新到 v${data.version}，资料和音乐保留。`);
        prepareWaitingUpdate(); await maybeReloadUpdate();
      } catch { notice("updateNotice", "当前无法检查更新；已保存的资料和音乐可以继续使用。"); }
      finally { window.clearTimeout(timeout); el("checkUpdate").disabled = false; state.updatePromise = null; }
    })();
    return state.updatePromise;
  }
  function musicMime(type) { return ({ mp3: "audio/mpeg", m4a: "audio/mp4", aac: "audio/aac", wav: "audio/wav", flac: "audio/flac", ogg: "audio/ogg", opus: "audio/ogg" })[type] || "application/octet-stream"; }
  function publicSource(value) { const path = pathValue(value); if (!path || path !== value || !path.startsWith("music/")) throw new Error("音乐来源无效。"); return new URL(path.split("/").map(encodeURIComponent).join("/"), window.location.href).href; }
  async function saveMusicTrack(track, signal) {
    if (state.saved.has(track.path)) return;
    if (!track.source) throw new Error("请重新选择这份音乐原文件。");
    const response = await fetch(publicSource(track.source), { signal }); if (!response.ok) throw new Error("音乐暂时无法下载，请稍后重试。");
    const body = await response.blob(); if (!body.size || body.size > 256 * 1024 * 1024) throw new Error("单首音乐为空或超过 256 MiB。");
    const metadata = { ...track, id: track.path, offlineLyrics: [] }, options = track.lyricsLanguages?.length ? track.lyricsLanguages : track.lyricsSource ? [{ code: track.lyricsLanguage || "original", label: "原文", source: track.lyricsSource }] : [];
    for (const option of options) {
      if (!option.source) continue;
      try { const result = await fetch(publicSource(option.source), { signal }); if (result.ok) { const content = await result.text(); if (content.length <= 262144) metadata.offlineLyrics.push({ code: option.code, content, format: /\.lrc$/i.test(option.source) ? "lrc" : "text" }); } }
      catch (error) { if (error.name === "AbortError") throw error; /* Audio remains useful when a local lyric sidecar is unavailable. */ }
    }
    metadata.lyrics = metadata.offlineLyrics.length > 0; metadata.lyricsLanguage = track.lyricsLanguage || metadata.offlineLyrics[0]?.code || "";
    metadata.lyricsLanguages = options.filter(option => metadata.offlineLyrics.some(item => item.code === option.code)).map(option => ({ code: option.code, label: option.code === "zh" ? "中文" : option.label }));
    await PhoneStore.putTrack(metadata, { id: track.path, blob: new Blob([body], { type: musicMime(track.type) }) }); state.saved.add(track.path);
  }
  async function downloadMusic(paths = state.music.tracks.filter(track => track.source && !state.saved.has(track.path)).map(track => track.path)) {
    if (state.downloadController) return; const controller = new AbortController(); state.downloadController = controller;
    el("musicDownloadStop").hidden = false; el("musicDownloadAll").disabled = true; renderMusicTracks(); await requestPersistence();
    try {
      const tracks = paths.map(path => state.music.tracks.find(track => track.path === path)).filter(track => track && !state.saved.has(track.path));
      for (const track of tracks) { notice("musicNotice", `正在下载：${track.name}`); await saveMusicTrack(track, controller.signal); renderMusicTracks(); }
      await loadMusic(true); await updateStorageNotice(); notice("musicNotice");
    } catch (error) { if (error.name === "AbortError") notice("musicNotice", "已停止下载，已保存的音乐仍保留。"); else failure(error, "musicNotice"); }
    finally { state.downloadController = null; el("musicDownloadStop").hidden = true; el("musicDownloadAll").disabled = false; renderMusicTracks(); void maybeReloadUpdate(); }
  }
  function lyricFileInfo(file) {
    const stem = file.name.replace(/\.(lrc|txt)$/i, ""), match = /^(.*)\.(zh|en|fr|ja|ko|de|es|it)$/i.exec(stem);
    return { base: (match?.[1] || stem).toLocaleLowerCase(), code: match?.[2]?.toLowerCase() || "original", format: /\.lrc$/i.test(file.name) ? "lrc" : "text" };
  }
  async function importMusicFiles(files) {
    if (state.downloadController) { notice("musicNotice", "请等保存完成或点停止，再添加音乐。"); return; }
    state.mediaSaving = (state.mediaSaving || 0) + 1;
    await requestPersistence(); const batch = new Map(), audioFiles = files.filter(file => /\.(mp3|m4a|aac|wav|flac|ogg|opus)$/i.test(file.name)), lyricFiles = files.filter(file => /\.(lrc|txt)$/i.test(file.name)); let unassigned = 0;
    try {
      for (const file of audioFiles) {
        if (!file.size || file.size > 256 * 1024 * 1024) throw new Error("单首音乐为空或超过 256 MiB，请选择较小的文件。");
        const id = `local/${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`}`, type = file.name.split(".").at(-1).toLowerCase(), name = file.name.replace(/\.[^.]+$/, ""), metadata = { id, path: id, name, type, size: file.size, lyrics: false, lyricsLanguages: [], offlineLyrics: [] };
        await PhoneStore.putTrack(metadata, { id, blob: new Blob([file], { type: musicMime(type) }) }); state.saved.add(id);
        const key = name.toLocaleLowerCase(); batch.set(key, batch.has(key) ? null : metadata); notice("musicNotice", `正在添加：${name}`);
      }
      for (const file of lyricFiles) {
        const info = lyricFileInfo(file), track = batch.get(info.base) || (!audioFiles.length && state.music.selected ? await PhoneStore.get("music", state.music.selected.path) : null);
        if (!track) { unassigned += 1; continue; }
        await addLocalLyric(track, file, info);
      }
      await loadMusic(true); await updateStorageNotice(); notice("musicNotice", unassigned ? "部分歌词未找到对应音乐，请选中歌曲后添加本地歌词。" : "");
      if (state.music.selected?.lyrics) { renderMusicLyricLanguages(state.music.selected); el("musicLyricsSection").hidden = false; void loadMusicLyrics(state.music.selected.path, state.music.selected.lyricsLanguage); }
    } catch (error) { await loadMusic(true); failure(error, "musicNotice"); }
    finally { state.mediaSaving -= 1; void maybeReloadUpdate(); }
  }
  async function addLocalLyric(track, file, info = lyricFileInfo(file)) {
    state.mediaSaving = (state.mediaSaving || 0) + 1;
    try {
      if (file.size > 262144) throw new Error("歌词超过 256 KiB。"); const content = await file.text();
      track.offlineLyrics = [...(track.offlineLyrics || []).filter(item => item.code !== info.code), { code: info.code, content, format: info.format }]; track.lyrics = true; track.lyricsLanguage ||= info.code;
      track.lyricsLanguages = track.offlineLyrics.map(item => ({ code: item.code, label: ({ original: "原文", zh: "中文", en: "English", fr: "Français", ja: "日本語", ko: "한국어" })[item.code] || item.code })); await PhoneStore.put("music", track);
    } finally { state.mediaSaving -= 1; void maybeReloadUpdate(); }
  }
  function musicTime(value) {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "0:00";
    const seconds = Math.floor(value); return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  }
  function musicTrackList(payload) {
    if (!Array.isArray(payload?.tracks) || payload.tracks.length > 10000 || payload.playback !== "phone") throw new Error("音乐列表无效，请重新读取本机曲库。");
    const tracks = [], seen = new Set();
    for (const item of payload.tracks) {
      const path = pathValue(item?.path);
      if (!path || path !== item.path || seen.has(path)) continue;
      seen.add(path);
      tracks.push({ ...item, path, name: String(item.name || path.split("/").at(-1)).slice(0, 500), type: String(item.type || "").slice(0, 12), size: item.size,
        folder: path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "", lyrics: Boolean(item.lyrics), lyricsLanguage: String(item.lyricsLanguage || ""),
        lyricsLanguages: (Array.isArray(item.lyricsLanguages) ? item.lyricsLanguages : []).filter(option => typeof option.code === "string" && /^[A-Za-z][A-Za-z0-9-]{0,23}$/.test(option.code)).map(option => ({ ...option, code: option.code, label: option.code === "zh" ? "中文" : String(option.label || option.code).slice(0, 40) })) });
    }
    return tracks;
  }
  function filteredMusic() {
    return MUSIC_TIERS.flatMap(tier => state.music.tracks.filter(track => musicTier(track) === tier.value && (!state.music.tier || musicTier(track) === state.music.tier)));
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
      const row = node("div", "", "music-track-row"), button = node("button", "", "music-track"); button.type = "button"; button.setAttribute("aria-pressed", String(track.path === state.music.selected?.path));
      button.append(node("span", track.path === state.music.selected?.path ? "♫" : String(index + 1), "music-track-number")); const label = node("span", "", "music-track-label"); label.append(node("span", track.name, "music-track-name")); button.append(label); button.addEventListener("click", () => selectMusicTrack(track.path)); row.append(button); groupTracks.append(row);
    });
    if (!tracks.length) container.append(node("p", state.music.loaded ? "这个分类还没有音乐。" : "正在读取手机曲库…", "empty-state"));
    el("musicMore").hidden = tracks.length <= state.music.visible;
    const pending = state.music.tracks.filter(track => track.source && !state.saved.has(track.path)), downloadable = state.music.tracks.filter(track => track.source), download = el("musicDownloadAll");
    download.hidden = !pending.length && !state.downloadController; download.textContent = state.downloadController ? "正在下载…" : pending.length < downloadable.length ? "继续下载" : "全部下载"; download.disabled = Boolean(state.downloadController);
    el("musicDownloadActions").hidden = download.hidden && el("musicDownloadStop").hidden;
  }
  async function loadMusic(force = false) {
    const music = state.music;
    if (!state.ready || music.loading || (music.loaded && !force)) return;
    const sequence = ++music.sequence; music.loading = true; notice("musicNotice", "正在读取本机曲库…");
    try {
      const data = await api("music"); if (sequence !== music.sequence || !state.ready) return;
      const tracks = musicTrackList(data); music.tracks = tracks; music.loaded = true; music.truncated = Boolean(data.truncated);
      if (music.selected) {
        const current = tracks.find(track => track.path === music.selected.path);
        if (!current) stopMusicPlayback(); else { music.selected = current; el("musicTrackTitle").textContent = current.name; }
      }
      renderMusicTracks(); updateMusicControls(); notice("musicNotice", data.error || "");
    } catch (error) { if (sequence === music.sequence) failure(error, "musicNotice"); }
    finally { if (sequence === music.sequence) music.loading = false; }
  }
  function clearMusicLyrics() {
    state.music.lyricsSequence += 1; state.music.lyrics = []; state.music.synced = false; state.music.activeLine = -1;
    el("musicLyrics").replaceChildren(); el("musicLyricLanguages").replaceChildren(); el("musicLyricLanguages").hidden = true; el("musicLyricsSection").hidden = true; el("musicLyricsNotice").textContent = "";
  }
  function stopMusicPlayback() {
    state.music.playSequence += 1; state.music.selected = null;
    const audio = el("musicAudio"); audio.pause(); audio.removeAttribute("src"); audio.load(); clearMusicLyrics();
    el("musicTrackTitle").textContent = "选择一首音乐";
    el("musicAddLyrics").hidden = true; el("musicSeek").value = "0"; el("musicElapsed").textContent = "0:00"; el("musicDuration").textContent = "0:00";
    try { if (navigator.mediaSession) { navigator.mediaSession.metadata = null; navigator.mediaSession.playbackState = "none"; } } catch { /* Optional system media controls. */ }
    updateMusicControls();
  }
  function clearMusic() {
    stopMusicPlayback();
    state.music.sequence += 1; state.music.tracks = []; state.music.loaded = false; state.music.loading = false; state.music.tier = ""; state.music.visible = 60; state.music.truncated = false; renderMusicTracks(); notice("musicNotice");
  }
  function updateMusicControls() {
    const audio = el("musicAudio"), selected = state.ready && Boolean(state.music.selected);
    el("musicPlayer").hidden = !selected;
    el("musicPlay").disabled = !selected; el("musicPrevious").disabled = !selected || state.music.tracks.length < 2; el("musicNext").disabled = !selected || state.music.tracks.length < 2;
    el("musicPlay").textContent = audio.paused ? "播放" : "暂停";
    el("musicRepeat").textContent = state.music.repeat === "one" ? "单曲循环" : state.music.repeat === "off" ? "播完停止" : "列表循环";
    el("musicRepeat").setAttribute("aria-label", `切换循环模式，当前${el("musicRepeat").textContent}`);
    updateMusicPosition();
    try { if (navigator.mediaSession) navigator.mediaSession.playbackState = selected ? audio.paused ? "paused" : "playing" : "none"; } catch { /* Optional system media controls. */ }
  }
  function playMusic() {
    if (!state.ready || !state.music.selected) return;
    const sequence = state.music.playSequence, audio = el("musicAudio");
    notice("musicNotice");
    try {
      const promise = audio.play();
      if (promise && typeof promise.catch === "function") promise.catch(error => {
        if (sequence !== state.music.playSequence || !state.ready) return;
        if (error.name === "AbortError") return;
        notice("musicNotice", error.name === "NotAllowedError" ? "Safari 需要你再点一次「播放」才能开始。" : "暂时无法播放，请重试或选择其他曲目。", true); updateMusicControls();
      });
      updateMusicControls();
    } catch { notice("musicNotice", "暂时无法播放，请重试或选择其他曲目。", true); updateMusicControls(); }
  }
  function selectMusicTrack(path) {
    const track = state.music.tracks.find(item => item.path === path); if (!track) return;
    if (!state.saved.has(path)) { notice("musicNotice", "这首音乐还没有下载，请先下载曲库。", true); return; }
    if (!navigator.serviceWorker?.controller) { notice("musicNotice", "离线程序正在准备，请稍后点播放；首次使用请联网重开一次。", true); return; }
    const music = state.music, audio = el("musicAudio"); music.playSequence += 1; audio.pause(); clearMusicLyrics(); music.selected = track;
    el("musicTrackTitle").textContent = track.name;
    audio.src = new URL(`audio/${encodeURIComponent(track.path)}`, window.location.href).href; audio.load();
    try { if (navigator.mediaSession && typeof MediaMetadata !== "undefined") navigator.mediaSession.metadata = new MediaMetadata({ title: track.name, album: "Codex Console" }); } catch { /* Optional native controls. */ }
    playMusic(); renderMusicTracks(); el("musicAddLyrics").hidden = false;
    if (track.lyrics) { el("musicLyricsSection").hidden = false; renderMusicLyricLanguages(track); void loadMusicLyrics(track.path, track.lyricsLanguage); }
  }
  function advanceMusic(direction = 1, ended = false) {
    const music = state.music; if (!music.selected || !music.tracks.length) return;
    if (ended && music.repeat === "one") { el("musicAudio").currentTime = 0; playMusic(); return; }
    let queue = filteredMusic().filter(track => state.saved.has(track.path)); if (!queue.some(track => track.path === music.selected.path)) queue = music.tracks.filter(track => state.saved.has(track.path));
    const index = queue.findIndex(track => track.path === music.selected.path);
    if (ended && music.repeat === "off" && index === queue.length - 1) { updateMusicControls(); return; }
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
      if (sequence !== state.music.lyricsSequence || state.music.selected?.path !== path || !state.ready) return;
      if (!samePath(data.path, path) || typeof data.content !== "string" || data.content.length > 262144) throw new Error("歌词响应无效，请重试。");
      const parsed = parseMusicLyrics(data.content, data.format); state.music.lyrics = parsed.lines; state.music.synced = parsed.synced; el("musicLyricsNotice").textContent = parsed.notice;
      parsed.lines.forEach(line => {
        const paragraph = node("p", line.text || "♪"); paragraph.dataset.timed = String(parsed.synced);
        if (parsed.synced) { paragraph.tabIndex = 0; paragraph.setAttribute("role", "button"); paragraph.setAttribute("aria-label", `${musicTime(line.time)} ${line.text || "间奏"}`); const seek = () => { if (state.ready && state.music.selected?.path === path && Number.isFinite(el("musicAudio").duration)) { el("musicAudio").currentTime = Math.min(el("musicAudio").duration, line.time); updateMusicPosition(); } }; paragraph.addEventListener("click", seek); paragraph.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); seek(); } }); }
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
    if (!state.music.selected || !el("musicAudio").error || el("musicAudio").error.code === 1) return;
    el("musicAudio").pause(); updateMusicControls(); notice("musicNotice", "这份音乐暂时不能播放，请重试或选择 Safari 支持的音乐格式。", true);
  }
  function bindMusicMediaSession() {
    if (!navigator.mediaSession) return;
    const handlers = { play: () => playMusic(), pause: () => { el("musicAudio").pause(); updateMusicControls(); }, previoustrack: () => advanceMusic(-1), nexttrack: () => advanceMusic(1), seekto: details => { if (state.music.selected && Number.isFinite(details.seekTime)) { el("musicAudio").currentTime = Math.max(0, Math.min(el("musicAudio").duration || 0, details.seekTime)); updateMusicPosition(); } } };
    for (const [action, handler] of Object.entries(handlers)) { try { navigator.mediaSession.setActionHandler(action, handler); } catch { /* Safari support differs by version and context. */ } }
  }
  function renderPlan(payload) {
    const plan = payload?.plan, container = el("taskGroups"), opened = new Map(Array.from(container.children).map(card => [card.dataset.group, card.open])); container.replaceChildren();
    const sync = state.library?.planSync;
    el("planMode").hidden = el("planNotice").hidden = !plan?.groups?.length;
    el("planMode").textContent = sync ? "已保存 · 只读" : "本机保存";
    el("planNotice").textContent = sync ? `保存于 ${date(sync.updatedAt)}，可离线查看。` : "勾选进度保存在这台手机。";
    if (!plan?.groups?.length) { container.append(node("p", "还没有保存的计划。", "empty-state")); return; }
    plan.groups.forEach((group, index) => {
      const card = node("details", "", "card task-card"), heading = node("summary"); card.dataset.group = group.id; card.open = Boolean(opened.get(group.id)); heading.append(node("span", `0${index + 1}`, "task-number"), node("span", group.title)); card.append(heading);
      if (group.summary) card.append(node("p", group.summary, "muted")); const list = node("ul", "", "task-items");
      for (const item of group.items) {
        const li = node("li"), label = node("label"), checkbox = node("input", "", "task-checkbox"); checkbox.type = "checkbox"; checkbox.disabled = Boolean(sync); checkbox.checked = !sync && typeof state.library?.taskDone?.[item.id] === "boolean" ? state.library.taskDone[item.id] : item.done;
        checkbox.addEventListener("change", async () => { if (sync) { checkbox.checked = item.done; return; } const done = checkbox.checked; if (state.busy) { checkbox.checked = !done; return; } checkbox.disabled = true; try { await mutateLibrary(next => { next.taskDone = { ...(next.taskDone || {}), [item.id]: done }; }); } catch (error) { checkbox.checked = typeof state.library?.taskDone?.[item.id] === "boolean" ? state.library.taskDone[item.id] : item.done; failure(error); } finally { checkbox.disabled = false; } });
        label.append(checkbox, node("span", item.text, "task-item-text")); li.append(label); list.append(li);
      }
      card.append(list); container.append(card);
    });
  }
  function renderDevice(device) {
    const memory = device?.currentMemory || {};
    const card = el("memoryCard"); card.replaceChildren(node("p", "上次保存的记忆体", "eyebrow"));
    if (memory.status === "available" && typeof memory.usedPercent === "number" && Number.isFinite(memory.usedPercent) && memory.usedPercent >= 0 && memory.usedPercent <= 100) {
      const value = node("p", String(memory.usedPercent), "memory-value"); value.append(node("span", "% 已用")); card.append(value);
      const track = node("div", "", "memory-track"); const fill = node("div", "", "memory-fill"); fill.style.width = `${memory.usedPercent}%`; fill.dataset.high = String(memory.usedPercent >= 95); track.append(fill); card.append(track);
      const line = node("p", "", "memory-line"); line.append(node("span", `可用 ${bytes(memory.availableBytes)}`), node("span", `总计 ${bytes(memory.totalBytes)}`)); card.append(line);
      if (memory.usedPercent >= 98) card.append(node("p", "这次保存的记忆体接近满载；离线版不读取电脑当前占用。", "small"));
    } else card.append(node("p", "上次保存的记忆体暂时无法读取。", "muted"));
    card.append(node("p", `电脑采样时间：${date(memory.readAt)}`, "muted small"));
    const hardware = el("hardwareCard"); hardware.replaceChildren(node("h3", "设备信息"), node("p", `保存的硬件采样 · ${date(device?.sampledAt)}`, "muted small"));
    if (!device?.sampledAt) { hardware.append(node("p", "还没有保存的设备资料。", "muted small")); return; }
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
    if (!guide.children.length) guide.append(node("p", data.guide?.error || data.error || "还没有保存的阅读重点。", "empty-state"));
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
    if (!records.children.length) records.append(node("p", "AI 原始记录保存在电脑资料库中。", "muted small"));
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
    releaseReaderImages();
    el("readerScreen").hidden = true; el("readerActions").hidden = true; el("readerContent").replaceChildren(); el("readerHeadings").replaceChildren(); el("readerLanguages").replaceChildren(); el("readerContents").hidden = true;
    el("readerTitle").textContent = ""; el("readerMeta").textContent = ""; notice("readerNotice");
    document.body.dataset.reading = "false"; el("main").inert = false; el("bottomNav").inert = false; el("appHeader").inert = false;
    if (pop && history.state?.phoneReader) history.back();
  }
  async function openDocument(value, { entryId = "", reference = null, fragment = "", push = true } = {}) {
    if (!state.ready) return;
    const path = pathValue(value);
    if (!path) { notice("appNotice", "文档路径无效，请从清单重新打开。", true); return; }
    const sequence = ++state.readerSequence;
    releaseReaderImages();
    const old = state.reader;
    const entry = entries().find(item => samePath(item.path, path) && (!entryId || item.id === entryId)) || null;
    state.reader = { path, entryId: reference ? "" : entry?.id || "", reference, loaded: false };
    state.headings.clear();
    if (push && !old) history.pushState({ phoneReader: true }, "", window.location.href);
    el("readerScreen").hidden = false; document.body.dataset.reading = "true";
    el("main").inert = true; el("bottomNav").inert = true; el("appHeader").inert = true;
    el("readerScreen").scrollTop = 0; el("readerScreen").focus(); el("readerTitle").textContent = "正在打开…"; el("readerMeta").textContent = "";
    el("readerContent").replaceChildren(); el("readerHeadings").replaceChildren(); el("readerContents").hidden = true; notice("readerNotice", "正在打开本机文档…"); updateReaderControls();
    try {
      const file = await api(`document?path=${encodeURIComponent(path)}`);
      if (sequence !== state.readerSequence) return;
      if (!samePath(file.path, path) || typeof file.content !== "string" || file.content.length > 2 * 1024 * 1024) throw new Error("返回的文档与请求不符或超过阅读限制。");
      el("readerTitle").textContent = /^#\s+(.+)$/m.exec(file.content)?.[1] || file.name || path.split("/").at(-1);
      el("readerMeta").textContent = `本机文档 · 修改于 ${date(file.modifiedAt)}`;
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
      if (sequence === state.readerSequence) notice("readerNotice", status === "archive" ? "已归档，已保存在这台手机。" : status === "later" ? "已放到 Later，已保存在这台手机。" : "已移回待阅读。已保存在这台手机。");
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
        if (image) appendImage(parent, label, target); else appendLink(parent, label, target, depth + 1);
      }
      offset = match.index + token.length;
    }
    parent.append(document.createTextNode(value.slice(offset)));
  }
  function appendImage(parent, label, target) {
    const relative = imagePath(target, state.reader?.path || ""), asset = relative && state.library?.assets?.find(item => item.path.toLowerCase() === relative.toLowerCase());
    const fallback = () => node("span", `图片：${label || "截图"}（未包含在资料包中）`, "reader-image-unavailable");
    if (!asset) { parent.append(fallback()); return; }
    const key = asset.path.toLowerCase(); let url = readerImageUrls.get(key);
    try { if (!url) { url = URL.createObjectURL(new Blob([imageBytes(asset)], { type: asset.mimeType })); readerImageUrls.set(key, url); } }
    catch { parent.append(fallback()); return; }
    const group = node("span", "", "reader-image"), anchor = node("a"), image = node("img");
    anchor.href = url; anchor.target = "_blank"; anchor.rel = "noopener noreferrer"; anchor.setAttribute("aria-label", `${label || "截图"}，打开原图`);
    image.alt = label || "截图"; image.loading = "lazy"; image.decoding = "async"; image.src = url;
    image.addEventListener("error", () => { group.replaceChildren(node("span", `图片：${label || "截图"}（暂时无法显示）`, "reader-image-unavailable")); });
    anchor.append(image); group.append(anchor); if (label) group.append(node("span", label, "reader-image-caption")); parent.append(group);
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
    const anchor = node("a"); anchor.href = fragment && !part ? `#${fragment}` : "./index.html"; appendInline(anchor, label, depth);
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
    // Reading preferences use small browser storage; private documents and music use IndexedDB.
    try { localStorage.setItem("codexPhone.offlineReaderFont.v1", String(state.font)); } catch { /* Reading works without storage. */ }
    updateReaderControls();
  }

  el("refreshButton").addEventListener("click", () => void refresh());
  el("computerWorkOpen").addEventListener("click", () => void openComputerWork());
  el("importButton").addEventListener("click", () => el("dataFile").click());
  el("dataFile").addEventListener("change", async () => { try { await reviewImport(el("dataFile").files[0]); } catch (error) { failure(error, "settingsNotice"); } finally { el("dataFile").value = ""; } });
  el("importConfirm").addEventListener("click", () => void commitImport());
  el("importCancel").addEventListener("click", () => { state.pendingImport = null; state.pendingSnapshot = null; el("importReview").hidden = true; void maybeReloadUpdate(); });
  if (TASK_SYNC_ENABLED) {
    el("syncForm").addEventListener("submit", event => { event.preventDefault(); void connectTaskSync(); });
    el("syncAddress").addEventListener("input", updateSyncFallback);
    el("syncDisconnect").addEventListener("click", () => { void disconnectTaskSync().catch(error => failure(error, "syncNotice")); });
  }
  el("backupButton").addEventListener("click", () => void backupLibrary());
  el("transferConnectForm").addEventListener("submit", event => { event.preventDefault(); void openTransferConnection(); });
  el("transferWorkOpen").addEventListener("click", () => void openTransferConnection(false, "work"));
  el("transferRememberedOpen").addEventListener("click", () => void openTransferConnection(true));
  el("workRememberedOpen").addEventListener("click", () => void openTransferConnection(true, "work"));
  el("transferScan").addEventListener("click", scanTransferConnection);
  el("transferQrRetry").addEventListener("click", scanTransferConnection);
  el("transferQrClose").addEventListener("click", () => el("transferQrDialog").close());
  el("transferQrDialog").addEventListener("close", () => transferScanner?.stop());
  for (const id of ["transferQrPhoto", "transferQrPhotoInDialog"]) el(id).addEventListener("click", () => { transferScanner?.stop(); el("transferQrFile").click(); });
  el("transferQrFile").addEventListener("change", () => { const file = el("transferQrFile").files?.[0]; el("transferQrFile").value = ""; if (!file || !transferScanner) return; if (!el("transferQrDialog").open) el("transferQrDialog").showModal(); void transferScanner.readFile(file); });
  el("transferForget").addEventListener("click", () => void forgetTransferConnection());
  el("restoreButton").addEventListener("click", async () => { if (state.busy) return; setBusy(true); try { await disconnectTaskSync(false); await libraryMutationQueue; const previous = await PhoneStore.get("records", "previousImport"); if (!previous) return; const next = mergeLibrary({ ...previous, id: "library", importedAt: new Date().toISOString() }, state.library); await PhoneStore.replaceLibrary(next); state.library = next; closeReader(false); await refreshDashboard(); notice("settingsNotice", "已恢复上次导入的资料，本机进度仍然保留。"); } catch (error) { failure(error, "settingsNotice"); } finally { setBusy(false); } });
  el("checkUpdate").addEventListener("click", () => void checkUpdate());
  el("applyUpdate").addEventListener("click", () => { if (!state.registration?.waiting && !state.updatePending) return; state.applyingUpdate = true; el("musicAudio").pause(); prepareWaitingUpdate(); void maybeReloadUpdate(); });
  el("musicImportButton").addEventListener("click", () => el("musicFiles").click());
  el("musicFiles").addEventListener("change", async () => { await importMusicFiles([...el("musicFiles").files]); el("musicFiles").value = ""; });
  el("musicDownloadAll").addEventListener("click", () => downloadMusic());
  el("musicDownloadStop").addEventListener("click", () => state.downloadController?.abort());
  el("musicAddLyrics").addEventListener("click", () => el("musicLyricFile").click());
  el("musicLyricFile").addEventListener("change", async () => { const file = el("musicLyricFile").files[0]; if (!file || !state.music.selected) return; try { const track = await PhoneStore.get("music", state.music.selected.path); if (!track) throw new Error("请先保存这首音乐。"); await addLocalLyric(track, file); await loadMusic(true); el("musicLyricsSection").hidden = false; renderMusicLyricLanguages(state.music.selected); await loadMusicLyrics(track.id, track.lyricsLanguage); } catch (error) { failure(error, "musicNotice"); } finally { el("musicLyricFile").value = ""; } });
  el("musicPlay").addEventListener("click", () => { if (el("musicAudio").paused) playMusic(); else { el("musicAudio").pause(); updateMusicControls(); } });
  el("musicPrevious").addEventListener("click", () => advanceMusic(-1));
  el("musicNext").addEventListener("click", () => advanceMusic(1));
  el("musicRepeat").addEventListener("click", () => { state.music.repeat = state.music.repeat === "all" ? "one" : state.music.repeat === "one" ? "off" : "all"; updateMusicControls(); });
  for (const button of document.querySelectorAll("button[data-music-tier]")) button.addEventListener("click", () => { state.music.tier = button.dataset.musicTier; state.music.visible = 60; renderMusicTracks(); });
  el("musicMore").addEventListener("click", () => { state.music.visible += 60; renderMusicTracks(); });
  el("musicSeek").addEventListener("input", () => { const audio = el("musicAudio"); if (state.music.selected && Number.isFinite(audio.duration) && audio.duration > 0) { audio.currentTime = audio.duration * Math.min(1000, Math.max(0, Number(el("musicSeek").value) || 0)) / 1000; updateMusicPosition(); } });
  for (const event of ["play", "pause", "loadedmetadata", "durationchange"]) el("musicAudio").addEventListener(event, () => { updateMusicControls(); if (event === "pause") void maybeReloadUpdate(); });
  el("musicAudio").addEventListener("timeupdate", updateMusicPosition);
  el("musicAudio").addEventListener("ended", () => advanceMusic(1, true));
  el("musicAudio").addEventListener("error", () => void musicAudioError());
  for (const button of document.querySelectorAll("[data-tab]")) button.addEventListener("click", () => selectTab(button.dataset.tab));
  for (const button of document.querySelectorAll("[data-inbox]")) button.addEventListener("click", () => { state.inbox = button.dataset.inbox; renderInbox(); });
  el("readerBack").addEventListener("click", () => closeReader(true));
  el("readerLater").addEventListener("click", () => void moveReader("later"));
  el("readerRead").addEventListener("click", () => void moveReader("read"));
  el("fontSmaller").addEventListener("click", () => setFont(state.font - 2));
  el("fontLarger").addEventListener("click", () => setFont(state.font + 2));
  window.addEventListener("popstate", () => closeReader(false));
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { void maybeReloadUpdate(); void checkUpdate({ automatic: true }); } });
  window.addEventListener("online", () => void checkUpdate({ automatic: true }));
  if (TASK_SYNC_ENABLED) {
    document.addEventListener("visibilitychange", () => { if (document.hidden) { stopSyncRequests(); renderSyncState(); } else void pollTaskSync(); });
    window.addEventListener("online", () => void pollTaskSync());
  }
  try { const font = Number(localStorage.getItem("codexPhone.offlineReaderFont.v1")); if (font >= 14 && font <= 26) state.font = font; } catch { /* Presentation defaults work without storage. */ }
  document.documentElement.style.setProperty("--reader-size", `${state.font}px`);
  bindMusicMediaSession();
  void bootstrap();
})();
