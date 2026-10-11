(() => {
  "use strict";
  const BASE = "/api/console/repository-publish";
  const KEY = "console.repositoryPublish.pending.v1";
  const mounted = new WeakMap();
  const instances = new Set();
  const activeStatuses = new Set(["queued", "working"]);
  const terminalStatuses = new Set(["success", "attention", "verification_required", "complete", "interrupted"]);
  const copy = {
    zh: { run: "提交并推送", config: "配置", close: "关闭", heading: "提交并推送", ready: "已启用 {n} 个仓库", loading: "正在读取…", saving: "正在保存配置…", saved: "配置已保存", saveFailed: "配置未保存，草稿保留", readFailed: "状态读取失败", unknown: "结果待核对，正在追踪原请求", working: "正在提交并推送…", interrupted: "操作中断，请查看详情", complete: "本次操作已完成", unavailable: "此处不可用", empty: "先配置一个仓库", add: "添加仓库", enabled: "启用", path: "本机仓库目录", repositoryUrl: "仓库网址", remote: "远端名称", branch: "分支", currentBranch: "当前分支（读取后保存）", rules: "同步文件与版本规则", sync: "同步文件（每行 来源 -> 目标）", syncHint: "相对本机仓库目录；仅执行提交时同步。", versions: "版本来源", addVersion: "添加版本来源", versionPath: "文件", kind: "格式", key: "字段 / 匹配式", name: "模块名称", scope: "适用范围", remove: "移除", excludes: "排除路径（每行一项）", naming: "提交命名", preset: "命名方式", version: "版本", module_version: "模块 + 版本", fallback: "无版本时的标题", subtitle: "副标题（可选）", notes: "备注（可选）", includeSummary: "包含改动摘要", preview: "预览标题与改动", previewing: "正在预览…", previewFailed: "预览失败，请查看状态", previewHint: "预览不执行文件同步。", details: "状态与详情", refresh: "重新读取", retry: "继续此仓库", noResults: "尚无操作回执", invalidSync: "同步规则需填写：来源 -> 目标", invalidConfig: "请检查未完成的配置", duplicate: "此仓库目录重复，请修改或禁用其中一项", serial: "配置尚未保存，请稍后再提交", noIdentity: "无法创建安全的请求身份", pendingUnavailable: "原请求回执尚未确认", disabledRepo: "未启用", previewTitle: "预览", repo: "仓库", defaultFallback: "更新进度 {datetime}" },
    en: { run: "Commit & push", config: "Configure", close: "Close", heading: "Commit & push", ready: "{n} repositories enabled", loading: "Reading…", saving: "Saving configuration…", saved: "Configuration saved", saveFailed: "Not saved; draft kept", readFailed: "Could not read status", unknown: "Checking the original request", working: "Committing and pushing…", interrupted: "Interrupted; see details", complete: "Operation completed", unavailable: "Unavailable here", empty: "Configure a repository first", add: "Add repository", enabled: "Enabled", path: "Local repository folder", repositoryUrl: "Repository URL", remote: "Remote name", branch: "Branch", currentBranch: "Current branch (read and save)", rules: "Sync files and version rules", sync: "Sync files (one source -> target per line)", syncHint: "Relative to the repository; synced only when running.", versions: "Version sources", addVersion: "Add version source", versionPath: "File", kind: "Format", key: "Key / pattern", name: "Module name", scope: "Scope", remove: "Remove", excludes: "Excluded paths (one per line)", naming: "Commit naming", preset: "Naming", version: "Version", module_version: "Module + version", fallback: "Title when no version is found", subtitle: "Subtitle (optional)", notes: "Notes (optional)", includeSummary: "Include change summary", preview: "Preview title and changes", previewing: "Previewing…", previewFailed: "Preview failed; see status", previewHint: "Preview does not sync files.", details: "Status and details", refresh: "Refresh", retry: "Continue this repository", noResults: "No operation receipt yet", invalidSync: "Use source -> target for each sync rule", invalidConfig: "Check the unfinished configuration", duplicate: "Duplicate repository folder; change or disable one", serial: "Wait for configuration to finish saving", noIdentity: "Could not create a secure request ID", pendingUnavailable: "Original request receipt remains unconfirmed", disabledRepo: "Disabled", previewTitle: "Preview", repo: "Repository", defaultFallback: "更新进度 {datetime}" }
  };
  copy.en.run = copy.en.heading = "Submit & push";
  copy.zh.syncHint = "来源为绝对文件路径，目标为仓库内相对路径；仅执行提交时同步。";
  copy.en.syncHint = "Use an absolute source file and a repository-relative target; synced only when running.";
  copy.zh.resumeOriginal = "继续原请求"; copy.en.resumeOriginal = "Continue original request";
  copy.zh.noIdentity = "请求身份未能保存，尚未发送"; copy.en.noIdentity = "Request ID could not be saved; nothing sent";
  copy.zh.editing = "配置草稿，离开字段后自动保存"; copy.en.editing = "Configuration draft; saves when leaving the field";
  copy.zh.bindingHints = "初次绑定提示"; copy.en.bindingHints = "Initial binding notes";
  copy.zh.bindingHintSnapshot = "此清单是初次发现时的快照，不代表当前仍有异常。"; copy.en.bindingHintSnapshot = "This is the initial discovery snapshot; it does not describe current issues.";
  copy.zh.omittedLink = "链接已省略"; copy.en.omittedLink = "Link omitted";
  copy.zh.scope = "适用范围（每行一项）"; copy.en.scope = "Scope (one pattern per line)";
  const clone = value => JSON.parse(JSON.stringify(value));
  const plain = value => value && typeof value === "object" && !Array.isArray(value);
  const clean = (value, length = 2000) => typeof value === "string" ? value.slice(0, length) : "";
  const idOK = value => typeof value === "string" && /^[A-Za-z0-9_-]{8,100}$/.test(value);
  const language = () => document.documentElement.lang.toLowerCase().startsWith("zh") ? "zh" : "en";
  function node(tag, className = "", text = "") { const item = document.createElement(tag); item.className = className; item.textContent = text; return item; }
  function uniqueId() {
    if (typeof window.crypto?.randomUUID === "function") return window.crypto.randomUUID();
    if (typeof window.crypto?.getRandomValues === "function") { const bytes = new Uint8Array(16); window.crypto.getRandomValues(bytes); return Array.from(bytes, b => b.toString(16).padStart(2, "0")).join(""); }
    return "";
  }
  function storedId() {
    const request = storedRequest(); if (request) return request.requestId;
    for (const name of ["localStorage", "sessionStorage"]) {
      try { const value = window[name]?.getItem(KEY); if (idOK(value)) return value; } catch { /* Storage may be disabled. */ }
    }
    return "";
  }
  function storedRequest() {
    const candidates = [];
    for (const name of ["localStorage", "sessionStorage"]) {
      try {
        const storage = window[name], parsed = JSON.parse(storage?.getItem(KEY + ".payload") || "null");
        if (plain(parsed) && idOK(parsed.requestId) && storage.getItem(KEY) === parsed.requestId && Array.isArray(parsed.repoIds) && parsed.repoIds.length && parsed.repoIds.every(id => typeof id === "string" && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$/.test(id)) && Number.isFinite(parsed.createdAt)) candidates.push(parsed);
      } catch { /* Missing or unavailable storage is not a receipt. */ }
    }
    candidates.sort((a, b) => b.createdAt - a.createdAt); return candidates[0] || null;
  }
  function persistRequest(request) {
    const encoded = JSON.stringify(request); let saved = false;
    for (const name of ["localStorage", "sessionStorage"]) {
      try { const storage = window[name]; storage.setItem(KEY + ".payload", encoded); storage.setItem(KEY, request.requestId); if (storage.getItem(KEY) === request.requestId && storage.getItem(KEY + ".payload") === encoded) saved = true; } catch { /* The other storage may remain usable. */ }
    }
    return saved;
  }
  function persistId(value, expectedId) {
    let saved = false;
    for (const name of ["localStorage", "sessionStorage"]) {
      try { const storage = window[name], existing = storage?.getItem(KEY); if (value) { if (!existing || existing === value) storage?.setItem(KEY, value); } else if (!expectedId || existing === expectedId) { storage?.removeItem(KEY); storage?.removeItem(KEY + ".payload"); } if (storage) saved = true; } catch { /* Try the other storage. */ }
    }
    return saved;
  }
  function normalized(value) {
    const settings = plain(value) ? clone(value) : {};
    settings.repositories = Array.isArray(settings.repositories) ? settings.repositories : [];
    settings.naming = { preset: "version", fallbackTitle: "更新进度 {datetime}", subtitle: "", notes: "", includeSummary: true, ...(plain(settings.naming) ? settings.naming : {}) };
    for (const repo of settings.repositories) {
      repo.syncFiles = Array.isArray(repo.syncFiles) ? repo.syncFiles : [];
      repo.versionSources = Array.isArray(repo.versionSources) ? repo.versionSources : [];
      repo.exclude = Array.isArray(repo.exclude) ? repo.exclude : [];
    }
    return settings;
  }
  function mount({ host } = {}) {
    if (!host || !host.closest('[data-module-panel="workspace"]')) return null;
    if (mounted.has(host)) return mounted.get(host);
    const state = { settings: null, warnings: [], allowed: false, serverBusy: false, operation: null, pendingId: storedId(), postBusy: false, readBusy: false, saveBusy: false, previewBusy: false, dirty: false, edit: 0, error: "", notice: "loading", pollTimer: 0, pollDelay: 1200, destroyed: false, invalid: new Set(), localized: [], returnFocus: null };
    const text = key => copy[language()][key] || key;
    state.pendingRequest = storedRequest(); state.notFound = false;
    const controls = [], resultRetries = [], syncDrafts = new Map(), inputPending = new Set();
    const managed = item => { item.setAttribute("data-console-management", ""); return item; };
    const bar = managed(node("div", "repository-publish-bar"));
    const runButton = managed(node("button", "ghost-button repository-publish-primary")); runButton.type = "button";
    const configButton = managed(node("button", "ghost-button repository-publish-config")); configButton.type = "button";
    const shortStatus = node("span", "repository-publish-status"); shortStatus.setAttribute("role", "status"); shortStatus.setAttribute("aria-live", "polite");
    bar.append(runButton, configButton, shortStatus);
    const dialog = managed(node("dialog", "repository-publish-dialog")); dialog.id = "consoleRepositoryPublish-" + (uniqueId() || "config");
    const header = node("header", "repository-publish-header"), heading = node("h2"), closeButton = managed(node("button", "ghost-button")); closeButton.type = "button";
    header.append(heading, closeButton);
    const form = node("div", "repository-publish-form"), repositories = node("div", "repository-publish-repositories");
    const addButton = managed(node("button", "ghost-button")); addButton.type = "button";
    const namingDetails = node("details", "repository-publish-section"), namingSummary = node("summary"), namingFields = node("div", "repository-publish-grid"); namingDetails.append(namingSummary, namingFields);
    const warningDetails = node("details", "repository-publish-section repository-publish-warnings"), warningSummary = node("summary"), warningHint = node("p", "repository-publish-hint"), warningRows = node("div", "repository-publish-warning-list"); warningDetails.hidden = true; warningDetails.append(warningSummary, warningHint, warningRows);
    const detail = node("details", "repository-publish-section"), detailSummary = node("summary"), detailStatus = node("p", "repository-publish-detail-status"), results = node("div", "repository-publish-results");
    const refreshButton = managed(node("button", "ghost-button")), previewButton = managed(node("button", "ghost-button")); refreshButton.type = previewButton.type = "button";
    const resumeButton = managed(node("button", "ghost-button")); resumeButton.type = "button"; resumeButton.hidden = true;
    const previewHint = node("p", "repository-publish-hint"), previewResult = node("div", "repository-publish-preview");
    detail.append(detailSummary, detailStatus, refreshButton, previewButton, resumeButton, previewHint, previewResult, results);
    form.append(repositories, addButton, namingDetails, warningDetails, detail); dialog.append(header, form); host.append(bar, dialog);
    const blocked = () => state.postBusy || state.previewBusy || state.serverBusy || Boolean(state.pendingId) || activeStatuses.has(state.operation?.status);
    const enabled = () => (state.settings?.repositories || []).filter(repo => repo.enabled === true);
    function localize(item, key, property = "textContent") { state.localized.push({ item, key, property }); item[property] = text(key); }
    function statusText() {
      if (state.error) return text(state.error);
      if (state.previewBusy) return text("previewing");
      if (inputPending.size) return text(state.invalid.size ? "invalidConfig" : "editing");
      if (state.saveBusy || state.dirty) return text(state.invalid.size ? "invalidConfig" : "saving");
      if (state.pendingId && !activeStatuses.has(state.operation?.status)) return text("unknown");
      if (blocked()) return text("working");
      if (state.notice) return text(state.notice);
      const n = enabled().length; return n ? text("ready").replace("{n}", String(n)) : text("empty");
    }
    function render() {
      bar.hidden = state.allowed !== true; if (!state.allowed && dialog.open) dialog.close();
      runButton.textContent = text("run"); configButton.textContent = text("config"); heading.textContent = text("heading"); closeButton.textContent = text("close");
      configButton.setAttribute("aria-controls", dialog.id); configButton.setAttribute("aria-expanded", String(dialog.open));
      shortStatus.textContent = statusText(); detailStatus.textContent = statusText(); shortStatus.dataset.state = state.error ? "error" : blocked() ? "working" : "ready";
      runButton.disabled = !state.allowed || !state.settings || !enabled().length || blocked() || state.readBusy || state.saveBusy || state.dirty || state.invalid.size > 0;
      configButton.disabled = !state.allowed; addButton.disabled = blocked() || state.saveBusy; refreshButton.disabled = state.readBusy || state.postBusy || state.saveBusy;
      previewButton.disabled = blocked() || state.previewBusy || state.saveBusy || state.dirty || !enabled().length;
      resumeButton.textContent = text("resumeOriginal"); resumeButton.hidden = !(state.notFound && state.pendingRequest?.requestId === state.pendingId);
      resumeButton.disabled = state.postBusy || state.serverBusy || state.readBusy || state.saveBusy || state.previewBusy || state.dirty || !state.allowed;
      for (const input of controls) input.disabled = blocked();
      for (const retry of resultRetries) retry.disabled = blocked() || state.readBusy || state.saveBusy || state.dirty;
      for (const label of state.localized) label.item[label.property] = text(label.key);
      if (dialog.open) renderWarnings();
    }
    function renderWarnings() {
      warningSummary.textContent = text("bindingHints"); warningHint.textContent = text("bindingHintSnapshot"); warningRows.replaceChildren();
      const safe = (value, length) => clean(value, length).replace(/\b(?:[a-z][a-z0-9+.-]*:\/\/|git@)[^\s<>"']+/gi, "[" + text("omittedLink") + "]");
      for (const warning of state.warnings) {
        const label = typeof warning === "string" ? safe(warning, 1200) : plain(warning) ? [safe(warning.code, 120), safe(warning.path, 1000), safe(warning.source, 300)].filter(Boolean).join(" · ") : "";
        if (label) warningRows.append(node("p", "repository-publish-warning-row", label));
      }
      warningDetails.hidden = warningRows.children.length === 0;
    }
    async function request(path = "", body) {
      const controller = new AbortController();
      const timer = window.setTimeout(() => controller.abort(), body === undefined ? 10000 : 20000);
      try {
        const response = await window.fetch(BASE + path, { method: body === undefined ? "GET" : "POST", credentials: "same-origin", mode: "same-origin", cache: "no-store", redirect: "error", referrerPolicy: "same-origin", headers: { Accept: "application/json", ...(body === undefined ? {} : { "Content-Type": "application/json" }) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: controller.signal });
        const value = await response.json();
        if (!response.ok || !plain(value) && !(value === null && body === undefined && path.startsWith("/operation?"))) throw new Error("request_failed");
        return value;
      } finally { window.clearTimeout(timer); }
    }
    function stopPoll() { if (state.pollTimer) window.clearTimeout(state.pollTimer); state.pollTimer = 0; }
    function schedulePoll() {
      stopPoll(); if (!state.pendingId || state.destroyed || !state.allowed) return;
      state.pollTimer = window.setTimeout(() => { state.pollTimer = 0; void poll(); }, state.pollDelay);
    }
    function acceptOperation(value) {
      if (state.destroyed) return false;
      const items = plain(value) && (Array.isArray(value.repositories) ? value.repositories : value.results);
      if (!plain(value) || !idOK(value.requestId) || !activeStatuses.has(value.status) && !terminalStatuses.has(value.status) || !Array.isArray(items)) return false;
      if (state.pendingId && value.requestId !== state.pendingId) return false;
      if (state.operation?.requestId === value.requestId && terminalStatuses.has(state.operation.status) && activeStatuses.has(value.status)) return false;
      state.operation = { ...clone(value), results: clone(items) }; state.error = ""; state.notice = ""; state.notFound = false;
      if (activeStatuses.has(value.status)) { state.pendingId = value.requestId; persistId(state.pendingId); schedulePoll(); }
      else { state.pendingId = ""; state.pendingRequest = null; persistId("", value.requestId); stopPoll(); state.serverBusy = false; state.notice = ["success", "complete"].includes(value.status) ? "complete" : "interrupted"; }
      renderResults(); return true;
    }
    async function poll() {
      if (!state.pendingId || state.destroyed || state.readBusy || state.postBusy) { schedulePoll(); return; }
      const expected = state.pendingId; state.readBusy = true; render();
      try {
        const value = await request("/operation?requestId=" + encodeURIComponent(expected));
        if (state.destroyed || state.pendingId !== expected) return;
        if (value === null || value.status === "not_found" && value.requestId === expected) {
          state.notFound = true; state.notice = "pendingUnavailable"; state.pollDelay = 10000;
          const snapshot = await request();
          if (!state.destroyed && state.pendingId === expected) {
            state.allowed = snapshot.allowed === true; state.serverBusy = snapshot.busy === true;
            if (snapshot.operation?.requestId === expected) acceptOperation(snapshot.operation);
          }
        }
        else if (!acceptOperation(value.operation || value)) { state.notice = "pendingUnavailable"; state.pollDelay = Math.min(10000, state.pollDelay * 2); }
        else state.pollDelay = 1200;
      } catch { state.notice = "pendingUnavailable"; state.pollDelay = Math.min(10000, state.pollDelay * 2); }
      finally { state.readBusy = false; render(); schedulePoll(); }
    }
    async function readStatus() {
      if (state.destroyed || state.readBusy || state.postBusy || state.saveBusy) return;
      state.readBusy = true; render();
      try {
        const value = await request(); if (state.destroyed) return;
        state.allowed = value.allowed === true; state.serverBusy = value.busy === true;
        state.warnings = Array.isArray(value.warnings) ? value.warnings.slice(0, 100) : [];
        if (!state.dirty && plain(value.settings)) { state.settings = normalized(value.settings); syncDrafts.clear(); state.invalid.clear(); if (dialog.open) renderConfig(); }
        const accepted = value.operation && acceptOperation(value.operation);
        if (!accepted) { state.error = ""; state.notice = ""; }
        if (state.pendingId) schedulePoll();
      } catch { state.error = "readFailed"; }
      finally { state.readBusy = false; render(); }
    }
    function changed() {
      state.dirty = true; state.edit++; state.error = ""; state.notice = ""; render(); void save();
    }
    function checkDuplicates() {
      const paths = new Set();
      for (const repo of enabled()) {
        const path = clean(repo.path).trim().replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
        if (path && paths.has(path)) return true; if (path) paths.add(path);
      }
      return false;
    }
    async function save() {
      if (!state.dirty || state.saveBusy || state.destroyed || blocked() || inputPending.size) return;
      if (state.invalid.size) { state.error = "invalidConfig"; render(); return; }
      if (checkDuplicates()) { state.error = "duplicate"; render(); return; }
      const edit = state.edit, payload = clone(state.settings); state.saveBusy = true; render();
      let succeeded = false;
      try {
        const value = await request("/config", { settings: payload }); if (state.destroyed) return;
        succeeded = true;
        if (state.edit === edit) { state.settings = normalized(value.settings || payload); state.dirty = false; state.error = ""; state.notice = "saved"; syncDrafts.clear(); if (dialog.open) renderConfig(); }
      } catch { state.error = "saveFailed"; }
      finally { state.saveBusy = false; render(); if (succeeded && state.edit !== edit) void save(); }
    }
    async function run(repoIds) {
      if (!state.allowed || !state.settings || blocked() || state.readBusy || state.saveBusy || state.dirty || state.invalid.size || !enabled().length) return;
      const requestId = uniqueId(), original = { requestId, repoIds: repoIds || enabled().map(repo => repo.id), createdAt: Date.now() };
      if (!requestId || !persistRequest(original)) { state.error = "noIdentity"; render(); return; }
      state.pendingRequest = original; await sendOriginal(original);
    }
    async function sendOriginal(original) {
      const requestId = original.requestId;
      stopPoll(); state.pendingId = requestId; state.notFound = false; state.operation = null; state.postBusy = true; state.error = ""; state.notice = "working"; renderResults(); render();
      try { const value = await request("/run", { requestId, repoIds: original.repoIds }); if (!acceptOperation(value.operation || value)) state.notice = "unknown"; }
      catch { state.notice = "unknown"; }
      finally { state.postBusy = false; render(); schedulePoll(); }
    }
    async function resumeOriginal() {
      if (!state.allowed || !state.notFound || !state.pendingRequest || state.pendingRequest.requestId !== state.pendingId || state.postBusy || state.readBusy || state.serverBusy || state.saveBusy || state.previewBusy || state.dirty) return;
      await sendOriginal(state.pendingRequest);
    }
    function field(parent, key, value, change, options = {}) {
      const label = node("label", "repository-publish-field"), caption = node("span"), input = node(options.multiline ? "textarea" : options.options ? "select" : "input");
      localize(caption, key);
      if (options.options) for (const choice of options.options) { const option = node("option"); option.value = typeof choice === "string" ? choice : choice.value; if (typeof choice === "string") option.textContent = choice; else localize(option, choice.key); input.append(option); }
      else {
        if (input.tagName === "INPUT") input.type = options.checkbox ? "checkbox" : "text";
        input.maxLength = options.maxLength || (options.multiline ? 16000 : 2048);
        if (options.multiline) input.rows = 3;
      }
      if (options.checkbox) input.checked = value === true; else input.value = clean(String(value ?? ""), 16000);
      if (options.placeholder) localize(input, options.placeholder, "placeholder");
      function validate() { if (options.required && !input.value.trim()) { input.setCustomValidity(text("invalidConfig")); state.invalid.add(input); } else { input.setCustomValidity(""); state.invalid.delete(input); } }
      if (options.required) { input.required = true; validate(); }
      input.dataset.field = key; label.append(caption, input); parent.append(label); controls.push(input);
      input.addEventListener("input", () => { if (blocked() || state.destroyed) return; if (options.required) validate(); change(options.checkbox ? input.checked : input.value, input); inputPending.add(input); state.dirty = true; state.edit++; state.error = ""; state.notice = ""; render(); });
      input.addEventListener("change", () => { if (blocked() || state.destroyed) return; inputPending.delete(input); if (options.required) validate(); change(options.checkbox ? input.checked : input.value, input); changed(); }); return input;
    }
    function renderConfig() {
      controls.length = 0; state.localized.length = 0; state.invalid.clear(); inputPending.clear(); repositories.replaceChildren(); namingFields.replaceChildren();
      localize(addButton, "add"); localize(namingSummary, "naming"); localize(detailSummary, "details"); localize(refreshButton, "refresh"); localize(previewButton, "preview"); localize(previewHint, "previewHint");
      for (const repo of state.settings?.repositories || []) {
        const card = node("section", "repository-publish-repo"), grid = node("div", "repository-publish-grid"), title = node("h3", "repository-publish-repo-title"); title.textContent = clean(repo.path).split(/[\\/]/).filter(Boolean).pop() || text("repo"); card.dataset.repoId = repo.id;
        card.append(title, grid); repositories.append(card);
        field(grid, "enabled", repo.enabled, value => { repo.enabled = value; }, { checkbox: true });
        for (const key of ["path", "repositoryUrl", "remote", "branch"]) field(grid, key, repo[key], value => { repo[key] = value.trim(); }, key === "branch" ? { placeholder: "currentBranch" } : {});
        const rules = node("details", "repository-publish-section"), summary = node("summary"), ruleFields = node("div", "repository-publish-grid"); localize(summary, "rules"); rules.append(summary, ruleFields); card.append(rules);
        const syncValue = syncDrafts.has(repo.id) ? syncDrafts.get(repo.id) : repo.syncFiles.map(item => clean(item.source) + " -> " + clean(item.target)).join("\n");
        const syncInput = field(ruleFields, "sync", syncValue, (value, input) => {
          syncDrafts.set(repo.id, value);
          const parsed = [], lines = value.split(/\r?\n/).map(line => line.trim()).filter(Boolean); let invalid = false;
          for (const line of lines) { const pair = line.split(/\s+->\s+/); if (pair.length !== 2 || !pair[0].trim() || !pair[1].trim()) { invalid = true; break; } parsed.push({ source: pair[0].trim(), target: pair[1].trim() }); }
          input.setCustomValidity(invalid ? text("invalidSync") : ""); if (invalid) state.invalid.add(input); else { state.invalid.delete(input); repo.syncFiles = parsed; }
        }, { multiline: true });
        if (syncValue.split(/\r?\n/).filter(line => line.trim()).some(line => line.trim().split(/\s+->\s+/).length !== 2)) { state.invalid.add(syncInput); syncInput.setCustomValidity(text("invalidSync")); }
        const hint = node("p", "repository-publish-hint"); localize(hint, "syncHint"); ruleFields.append(hint);
        field(ruleFields, "excludes", repo.exclude.join("\n"), value => { repo.exclude = value.split(/\r?\n/).map(line => line.trim()).filter(Boolean); }, { multiline: true });
        const versionBox = node("div", "repository-publish-version-list"), versionHeading = node("h4"), versionButton = managed(node("button", "ghost-button")); versionButton.type = "button"; localize(versionHeading, "versions"); localize(versionButton, "addVersion"); controls.push(versionButton); rules.append(versionHeading, versionBox, versionButton);
        function versions() {
          for (let i = controls.length - 1; i >= 0; i--) if (versionBox.contains(controls[i])) controls.splice(i, 1);
          for (const invalid of state.invalid) if (versionBox.contains(invalid)) state.invalid.delete(invalid);
          for (const pending of inputPending) if (versionBox.contains(pending)) inputPending.delete(pending);
          state.localized = state.localized.filter(label => !versionBox.contains(label.item));
          versionBox.replaceChildren();
          for (const source of repo.versionSources) {
            const row = node("div", "repository-publish-version-row"); versionBox.append(row);
            const formats = ["json", "xml", "unity", "unity_yaml", "python_ast", "text"];
            if (typeof source.kind === "string" && source.kind && !formats.includes(source.kind)) formats.push(source.kind);
            for (const [label, key] of [["versionPath", "path"], ["kind", "kind"], ["key", "key"], ["name", "name"], ["scope", "scope"]]) {
              const value = key === "scope" && Array.isArray(source.scope) ? source.scope.join("\n") : source[key];
              field(row, label, value, next => {
                if (key === "scope") {
                  const scopes = next.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
                  source.scope = Array.isArray(source.scope) || scopes.length > 1 ? scopes : scopes[0] || "";
                } else source[key] = next.trim();
              }, key === "kind" ? { options: formats } : key === "scope" ? { multiline: true } : key === "path" ? { required: true } : {});
            }
            const remove = managed(node("button", "ghost-button")); remove.type = "button"; localize(remove, "remove"); controls.push(remove); row.append(remove);
            remove.addEventListener("click", () => { if (blocked()) return; repo.versionSources.splice(repo.versionSources.indexOf(source), 1); versions(); changed(); });
          }
        }
        versions(); versionButton.addEventListener("click", () => { if (blocked()) return; repo.versionSources.push({ path: "", kind: "json", key: "version", name: "", scope: "" }); versions(); changed(); });
      }
      if (state.settings) {
        const naming = state.settings.naming;
        field(namingFields, "preset", naming.preset, value => { naming.preset = value; }, { options: [{ value: "version", key: "version" }, { value: "module_version", key: "module_version" }] });
        for (const [label, key] of [["fallback", "fallbackTitle"], ["subtitle", "subtitle"], ["notes", "notes"]]) field(namingFields, label, naming[key], value => { naming[key] = value; }, { multiline: key === "notes" });
        field(namingFields, "includeSummary", naming.includeSummary, value => { naming.includeSummary = value; }, { checkbox: true });
      }
      renderResults(); render();
    }
    function renderResults() {
      results.replaceChildren(); resultRetries.length = 0;
      const list = state.operation?.results || [];
      if (!list.length) { const item = node("p", "repository-publish-hint"); localize(item, "noResults"); results.append(item); return; }
      for (const result of list) {
        const card = node("article", "repository-publish-result"), title = node("strong"), summary = node("p"), expanded = node("details"), expandedTitle = node("summary"), content = node("pre");
        title.textContent = clean(result.name || result.repoId, 200); summary.textContent = [clean(result.status, 60), clean(result.phase, 60), clean(result.message, 500)].filter(Boolean).join(" · "); localize(expandedTitle, "details");
        const logs = (Array.isArray(result.logs) ? result.logs : []).slice(-100).map(item => [clean(item.at, 80), clean(item.phase, 80), clean(item.message, 500)].filter(Boolean).join(" · ")).join("\n");
        content.textContent = [clean(result.title), clean(result.body, 16000), clean(result.commitSha, 80), logs].filter(Boolean).join("\n\n"); expanded.append(expandedTitle, content); card.append(title, summary, expanded); results.append(card);
        if ((["push_failed", "commit_failed", "conflict", "interrupted", "failed", "unknown", "index_pending", "deferred", "verification_required"].includes(result.status) || state.operation?.status === "verification_required" && activeStatuses.has(result.status)) && typeof result.repoId === "string") {
          const retry = managed(node("button", "ghost-button")); retry.type = "button"; localize(retry, "retry"); card.append(retry); resultRetries.push(retry); retry.addEventListener("click", () => void run([result.repoId]));
        }
      }
    }
    async function preview(repoId) {
      if (blocked() || state.previewBusy || state.saveBusy || state.dirty || !enabled().length) return;
      state.previewBusy = true; state.notice = "previewing"; render();
      try {
        const value = await request("/preview", repoId ? { repoId } : {}); previewResult.replaceChildren();
        for (const result of Array.isArray(value.previews) ? value.previews : Array.isArray(value.results) ? value.results : Array.isArray(value.repositories) ? value.repositories : []) {
          const versions = (Array.isArray(result.versions) ? result.versions : []).map(item => [clean(item.name), clean(item.version)].filter(Boolean).join(" · ")).filter(Boolean).join("\n");
          const card = node("article", "repository-publish-result"), title = node("strong"), content = node("pre"); title.textContent = clean(result.name || result.repoId || result.id, 200); content.textContent = [versions || clean(result.version), clean(result.title), clean(result.body, 16000), clean(result.message, 500)].filter(Boolean).join("\n\n"); card.append(title, content); previewResult.append(card);
        }
        state.notice = ""; state.error = "";
      } catch { state.error = "previewFailed"; }
      finally { state.previewBusy = false; render(); if (state.dirty) void save(); }
    }
    function open() {
      if (!state.allowed || state.destroyed) return;
      state.returnFocus = document.activeElement; if (state.settings && !dialog.open && !state.dirty) renderConfig();
      dialog.showModal(); render(); if (state.pendingId) void poll(); else void readStatus();
    }
    runButton.addEventListener("click", () => void run()); configButton.addEventListener("click", open); closeButton.addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => { render(); state.returnFocus?.focus(); });
    addButton.addEventListener("click", () => {
      if (!state.settings || blocked() || state.saveBusy) return;
      const id = uniqueId(); if (!id) { state.error = "noIdentity"; render(); return; }
      state.settings.repositories.push({ id, path: "", repositoryUrl: "", remote: "origin", branch: "", enabled: false, syncFiles: [], versionSources: [], exclude: [] }); renderConfig(); changed();
    });
    refreshButton.addEventListener("click", () => { if (state.dirty) void save(); else if (state.pendingId) void poll(); else void readStatus(); }); previewButton.addEventListener("click", () => void preview());
    resumeButton.addEventListener("click", () => void resumeOriginal());
    let observer = null;
    if (typeof MutationObserver === "function") { observer = new MutationObserver(() => { render(); }); observer.observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] }); }
    function suspend() { stopPoll(); }
    function resume() { if (state.pendingId) schedulePoll(); else void readStatus(); }
    window.addEventListener("pagehide", suspend); window.addEventListener("pageshow", resume);
    const api = { open, refresh: readStatus, hasDraft: () => state.dirty || state.invalid.size > 0, canReload: () => !state.dirty && !state.saveBusy && !state.postBusy && !state.previewBusy, destroy() { state.destroyed = true; stopPoll(); observer?.disconnect(); window.removeEventListener("pagehide", suspend); window.removeEventListener("pageshow", resume); bar.remove(); dialog.remove(); mounted.delete(host); instances.delete(api); } };
    mounted.set(host, api); instances.add(api); render(); void readStatus(); return api;
  }
  window.ConsoleRepositoryPublish = { mount, hasDraft: () => Array.from(instances).some(item => item.hasDraft()), canReload: () => Array.from(instances).every(item => item.canReload()) };
  const mountDefault = () => { const host = document.getElementById("consoleRepositoryPublishHost"); if (host) mount({ host }); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mountDefault, { once: true });
  else mountDefault();
})();
