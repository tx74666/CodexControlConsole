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
  copy.zh.run = copy.zh.heading = "推送到 GitHub";
  copy.en.run = copy.en.heading = "Push to GitHub";
  copy.zh.working = "正在推送到 GitHub…"; copy.en.working = "Pushing to GitHub…";
  copy.zh.repoNoChanges = "无改动"; copy.en.repoNoChanges = "No changes";
  Object.assign(copy.zh, { expand: "展开仓库", collapse: "收起仓库", configAll: "配置全部", connection: "路径与远端", versionPlan: "版本计划", nextPatch: "使用下一个补丁版本", cancelPlan: "取消计划", noVersion: "未配置版本", versionPending: "版本待读取", versionFailed: "版本读取失败", noVersionChange: "不改版本", repoReady: "就绪", repoDone: "已完成", repoAttention: "需查看", repoWorking: "进行中", component: "组件", planned: "已计划", versionUnsupported: "此版本暂不能自动递增" });
  Object.assign(copy.en, { expand: "Show repositories", collapse: "Hide repositories", configAll: "Configure all", connection: "Folder and remote", versionPlan: "Version plan", nextPatch: "Use next patch", cancelPlan: "Cancel plan", noVersion: "No version configured", versionPending: "Version not read yet", versionFailed: "Could not read versions", noVersionChange: "Keep version", repoReady: "Ready", repoDone: "Completed", repoAttention: "Needs attention", repoWorking: "In progress", component: "Component", planned: "Planned", versionUnsupported: "Automatic version bump is unavailable" });
  Object.assign(copy.zh, { versionSummary: "Summary · 版本摘要", changeUnknown: "变化未核对", localChanges: "有待提交改动", outgoing: "有提交待推送", localAndOutgoing: "改动与提交待推送", actualVersionChange: "已修改版本", keepCurrent: "本次保留当前版本", planUnverified: "计划待核对", planTarget: "计划目标", gitCommitVersion: "提交版本", gitCommitHint: "来自提交记录，不修改版本文件", candidateVersion: "可选下一版", pushOnly: "仅推送已有提交，保留原说明", planKept: "计划保留，本次不改版本", syncRecheck: "同步后再核对提交与版本计划", planApplyUnknown: "版本计划执行待核对" });
  Object.assign(copy.en, { versionSummary: "Summary · Versions", changeUnknown: "Changes not checked", localChanges: "Changes to commit", outgoing: "Commits to push", localAndOutgoing: "Changes and commits to push", actualVersionChange: "Version changed", keepCurrent: "Keep the current version", planUnverified: "Plan needs checking", planTarget: "Planned target", gitCommitVersion: "Commit version", gitCommitHint: "Read from commit history; no version file is changed", candidateVersion: "Optional next version", pushOnly: "Push existing commits with their original messages", planKept: "Keep the plan; no version change this time", syncRecheck: "Recheck commits and version plans after file sync", planApplyUnknown: "Version plan execution is not confirmed" });
  copy.zh.autoBump = "有改动自动升下一版"; copy.en.autoBump = "Automatically bump versions with changes";
  copy.zh.automaticVersion = "自动升版，提交时复核"; copy.en.automaticVersion = "Automatic version bump; rechecked when committing";
  copy.zh.configConflict = "另一处已修改配置；此处草稿保留，请重新核对"; copy.en.configConflict = "Configuration changed elsewhere; this draft is kept for review";
  copy.zh.reloadConfig = "重新读取配置（放弃此配置草稿）"; copy.en.reloadConfig = "Reload configuration (discard this configuration draft)";
  copy.zh.syncChanges = "有工作文件待同步"; copy.en.syncChanges = "Saved work files to sync";
  copy.zh.authorityMissing = "无版本 · 备用标题"; copy.en.authorityMissing = "No version · fallback title";
  copy.zh.syncHint = "来源为绝对文件路径，目标为仓库内相对路径；仅执行提交时同步。";
  copy.en.syncHint = "Use an absolute source file and a repository-relative target; synced only when running.";
  copy.zh.resumeOriginal = "继续原请求"; copy.en.resumeOriginal = "Continue original request";
  copy.zh.noIdentity = "请求身份未能保存，尚未发送"; copy.en.noIdentity = "Request ID could not be saved; nothing sent";
  copy.zh.editing = "配置草稿，离开字段后自动保存"; copy.en.editing = "Configuration draft; saves when leaving the field";
  copy.zh.bindingHints = "初次绑定提示"; copy.en.bindingHints = "Initial binding notes";
  copy.zh.bindingHintSnapshot = "此清单是初次发现时的快照，不代表当前仍有异常。"; copy.en.bindingHintSnapshot = "This is the initial discovery snapshot; it does not describe current issues.";
  copy.zh.omittedLink = "链接已省略"; copy.en.omittedLink = "Link omitted";
  copy.zh.scope = "适用范围（每行一项）"; copy.en.scope = "Scope (one pattern per line)";
  Object.assign(copy.zh, { displayVersion: "查看插件版本", changedPlugins: "本次有改动", otherPlugins: "其他插件", uploadNumber: "上传 #{n}", uploadUnknown: "上传 #?", uploadHint: "Console 已确认的上传序号；插件版本在下方单独列出。", uploadPending: "上传计数待核对", pluginDetails: "插件版本", processed: "已处理 {n}/{total}", succeeded: "成功 {n}", skipped: "跳过 {n}", attention: "需处理 {n}", review: "待核对 {n}", progressWaiting: "等待进度回执…", progressLabel: "仓库处理进度", phaseQueued: "等待处理", phaseCheck: "检查仓库", phaseSync: "同步工作文件", phaseRemote: "核对远端", phaseVersion: "准备版本", phaseCommit: "提交改动", phasePush: "上传", phaseVerify: "核验上传结果", phaseOther: "正在处理", uploaded: "已上传", deferred: "已暂缓", failed: "失败", verifyRequired: "待核对", detailsAction: "查看此仓库的处理详情" });
  Object.assign(copy.en, { displayVersion: "View plugin versions", changedPlugins: "Changed plugins", otherPlugins: "Other plugins", uploadNumber: "Push #{n}", uploadUnknown: "Push #?", uploadHint: "Uploads confirmed by Console; independent plugin versions are listed below.", uploadPending: "Upload count needs verification", pluginDetails: "Plugin versions", processed: "Processed {n}/{total}", succeeded: "Succeeded {n}", skipped: "Skipped {n}", attention: "Needs attention {n}", review: "Unconfirmed {n}", progressWaiting: "Waiting for a progress receipt…", progressLabel: "Repository progress", phaseQueued: "Queued", phaseCheck: "Checking repository", phaseSync: "Syncing work files", phaseRemote: "Checking remote", phaseVersion: "Preparing versions", phaseCommit: "Committing", phasePush: "Uploading", phaseVerify: "Verifying upload", phaseOther: "Processing", uploaded: "Uploaded", deferred: "Deferred", failed: "Failed", verifyRequired: "Unconfirmed", detailsAction: "View this repository's operation details" });
  Object.assign(copy.zh, { historicalReceipt: "历史回执", historicalHint: "此回执未匹配当前仓库目标，保留原结果；不会按新配置重试。", originalTarget: "原上传目标" });
  Object.assign(copy.en, { historicalReceipt: "Historical receipt", historicalHint: "This receipt does not match the current repository target. Its original result is kept; retrying against the new configuration is unavailable.", originalTarget: "Original upload target" });
  Object.assign(copy.zh, { diagnosis: "原因与下一步", diagnosisRead: "当前读取", diagnosisOperation: "本次执行", diagnosisHistory: "历史执行", diagnosisNext: "下一步", locateSetting: "查看对应设置", recheckRepository: "重新核对此仓库", readingLocal: "读取版本与本地差异…", readingHint: "正在读取本机状态，最多等待 60 秒；不会同步、提交或推送。", updatingLocal: "更新核对中…", readTimeout: "读取已超时", readInvalid: "仓库状态回执不完整", readConnection: "暂时无法读取仓库状态", readNext: "稍后重新核对。原工作、配置与操作回执已保留。", notRead: "此仓库状态尚未核对", notReadNext: "点击重新核对，只读取本机仓库状态。", publishingRead: "上传处理中，结束后可重新核对版本。", waitOperation: "等待原操作完成；不要重复提交。", knownBefore: "显示上次读取结果，当前尚未重新核对。", checkedAt: "上次核对", inspectOriginal: "查看下方原回执。只在确认原目标后继续原请求。", configDraftRead: "配置草稿尚未保存；保留草稿，保存后再核对。" });
  Object.assign(copy.en, { diagnosis: "Reason and next step", diagnosisRead: "Current check", diagnosisOperation: "Operation receipt", diagnosisHistory: "Historical receipt", diagnosisNext: "Next step", locateSetting: "View the relevant setting", recheckRepository: "Recheck this repository", readingLocal: "Reading versions and local changes…", readingHint: "Reading local state, with a 60-second deadline. No sync, commit or push is performed.", updatingLocal: "Rechecking…", readTimeout: "Read timed out", readInvalid: "Repository receipt is incomplete", readConnection: "Repository state could not be read", readNext: "Recheck later. Your work, configuration and operation receipts are retained.", notRead: "This repository has not been checked", notReadNext: "Recheck to read local repository state only.", publishingRead: "Publishing is active; versions can be rechecked when it finishes.", waitOperation: "Wait for the original operation; do not submit it again.", knownBefore: "Showing the last reading; the current state is not yet rechecked.", checkedAt: "Last checked", inspectOriginal: "Inspect the original receipt below. Continue only after confirming its original target.", configDraftRead: "Configuration has an unsaved draft. Keep it and recheck after saving." });
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
    settings.naming = { preset: "version", fallbackTitle: "更新进度 {datetime}", subtitle: "", notes: "", includeSummary: true, autoBump: true, ...(plain(settings.naming) ? settings.naming : {}) };
    for (const repo of settings.repositories) {
      repo.syncFiles = Array.isArray(repo.syncFiles) ? repo.syncFiles : [];
      repo.versionSources = Array.isArray(repo.versionSources) ? repo.versionSources : [];
      repo.versionPlans = Array.isArray(repo.versionPlans) ? repo.versionPlans : [];
      repo.exclude = Array.isArray(repo.exclude) ? repo.exclude : [];
    }
    return settings;
  }
  function mount({ host } = {}) {
    const workspacePanel = host?.closest('[data-module-panel="workspace"]');
    if (!workspacePanel) return null;
    if (mounted.has(host)) return mounted.get(host);
    const state = { settings: null, settingsSha: "", configConflict: false, warnings: [], allowed: false, serverBusy: false, operation: null, pendingId: storedId(), postBusy: false, readBusy: false, saveBusy: false, previewBusy: false, dirty: false, edit: 0, error: "", notice: "loading", pollTimer: 0, pollDelay: 1200, destroyed: false, invalid: new Set(), localized: [], returnFocus: null };
    const text = key => copy[language()][key] || key;
    state.pendingRequest = storedRequest(); state.notFound = false;
    state.expanded = false; state.configRepoId = null; state.versionBusy = false; state.versionFailed = false; state.versionEpoch = 0; state.catalog = new Map(); state.savedSources = new Map(); state.operatedRepoIds = new Set();
    state.uploadSummaries = new Map(); state.multiBindings = new Set();
    state.versionReads = new Map(); state.statusReadError = null;
    const controls = [], resultRetries = [], syncDrafts = new Map(), inputPending = new Set();
    const compactRefs = new Map(), configCards = new Map(), configSections = new Map(), planBoxes = new Map();
    const managed = item => { item.setAttribute("data-console-management", ""); return item; };
    const bar = managed(node("div", "repository-publish-bar"));
    const runButton = managed(node("button", "ghost-button repository-publish-primary")); runButton.type = "button";
    const toggleButton = managed(node("button", "ghost-button repository-publish-toggle", "⌄")); toggleButton.type = "button";
    const configButton = managed(node("button", "ghost-button repository-publish-config")); configButton.type = "button";
    const shortStatus = node("span", "repository-publish-status"); shortStatus.setAttribute("role", "status"); shortStatus.setAttribute("aria-live", "polite");
    const progress = node("div", "repository-publish-progress"), progressFill = node("span", "repository-publish-progress-fill"); progress.hidden = true;
    progress.setAttribute("role", "progressbar"); progress.append(progressFill); bar.append(runButton, toggleButton, shortStatus, progress);
    const expanded = managed(node("div", "repository-publish-expanded")), expandedToolbar = node("div", "repository-publish-expanded-toolbar"), compactRows = node("div", "repository-publish-compact-rows");
    expanded.id = "consoleRepositoryPublish-repositories-" + (uniqueId() || "list"); expanded.hidden = true; expandedToolbar.append(configButton); expanded.append(expandedToolbar, compactRows);
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
    const diagnosisBox = node("div", "repository-publish-diagnosis"), diagnosisHeading = node("strong"), diagnosisSummary = node("p", "repository-publish-diagnosis-summary"), diagnosisNext = node("p", "repository-publish-diagnosis-next"), diagnosisMeta = node("p", "repository-publish-diagnosis-meta"), diagnosisActions = node("div", "repository-publish-diagnosis-actions"), diagnosisLocate = managed(node("button", "ghost-button repository-publish-diagnosis-locate")), diagnosisRecheck = managed(node("button", "ghost-button repository-publish-diagnosis-recheck"));
    diagnosisLocate.type = diagnosisRecheck.type = "button"; diagnosisBox.hidden = true; diagnosisSummary.id = "repository-publish-reason-" + (uniqueId() || "current"); diagnosisActions.append(diagnosisLocate, diagnosisRecheck); diagnosisBox.append(diagnosisHeading, diagnosisSummary, diagnosisNext, diagnosisMeta, diagnosisActions);
    detail.append(detailSummary, detailStatus, refreshButton, previewButton, resumeButton, previewHint, previewResult, results);
    form.append(diagnosisBox, repositories, addButton, namingDetails, warningDetails, detail); dialog.append(header, form); host.append(bar, expanded, dialog);
    const blocked = () => state.postBusy || state.previewBusy || state.serverBusy || Boolean(state.pendingId) || activeStatuses.has(state.operation?.status);
    const enabled = () => (state.settings?.repositories || []).filter(repo => repo.enabled === true);
    function localize(item, key, property = "textContent") { state.localized.push({ item, key, property }); item[property] = text(key); }
    const successfulRepoStatuses = new Set(["success", "pushed"]), skippedRepoStatuses = new Set(["noop", "no_changes", "disabled"]);
    const reviewRepoStatuses = new Set(["verification_required", "unknown", "index_pending"]), failedRepoStatuses = new Set(["deferred", "push_failed", "commit_failed", "conflict", "interrupted", "failed"]);
    function phaseText(phase) { return text(({ queued: "phaseQueued", check: "phaseCheck", sync: "phaseSync", remote: "phaseRemote", version: "phaseVersion", commit: "phaseCommit", push: "phasePush", verify: "phaseVerify" })[phase] || "phaseOther"); }
    function operationProgress() {
      const items = state.operation?.results;
      if (!Array.isArray(items)) return null;
      const unique = new Map();
      for (const item of items) if (plain(item) && typeof item.repoId === "string" && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$/.test(item.repoId) && !unique.has(item.repoId)) unique.set(item.repoId, item);
      const rows = Array.from(unique.values()); if (!rows.length) return null;
      const succeeded = rows.filter(item => successfulRepoStatuses.has(item.status)).length, skipped = rows.filter(item => skippedRepoStatuses.has(item.status)).length;
      const review = rows.filter(item => reviewRepoStatuses.has(item.status)).length, attention = rows.filter(item => failedRepoStatuses.has(item.status)).length;
      const counterPending = rows.filter(item => successfulRepoStatuses.has(item.status) && item.uploadSummary?.state === "pending").length;
      const current = rows.find(item => item.status === "working") || rows.find(item => item.status === "queued");
      return { total: rows.length, completed: succeeded + skipped + review + attention, succeeded, skipped, review, attention, counterPending, current };
    }
    function operationText(info) {
      const parts = [text("processed").replace("{n}", String(info.completed)).replace("{total}", String(info.total))];
      if (activeStatuses.has(state.operation?.status) && info.current) {
        const repo = state.settings?.repositories.find(item => item.id === info.current.repoId);
        parts.push(clean(repo ? repoName(repo) : info.current.name || info.current.repoId, 60), phaseText(info.current.phase));
        if (info.attention) parts.push(text("attention").replace("{n}", String(info.attention)));
        if (info.review) parts.push(text("review").replace("{n}", String(info.review)));
      } else {
        parts.push(text("succeeded").replace("{n}", String(info.succeeded)));
        if (info.skipped) parts.push(text("skipped").replace("{n}", String(info.skipped)));
        if (info.attention) parts.push(text("attention").replace("{n}", String(info.attention)));
        if (info.review) parts.push(text("review").replace("{n}", String(info.review)));
        if (info.counterPending) parts.push(text("uploadPending") + " " + String(info.counterPending));
        if (info.completed !== info.total) parts.push(text("progressWaiting"));
      }
      return parts.join(" · ");
    }
    function statusText() {
      if (state.configConflict) return text("configConflict");
      if (state.error) { const info = operationProgress(); return info ? operationText(info) + " · " + text(state.error) : text(state.error); }
      if (state.previewBusy) return text("previewing");
      if (inputPending.size) return text(state.invalid.size ? "invalidConfig" : "editing");
      if (state.saveBusy || state.dirty) return text(state.invalid.size ? "invalidConfig" : "saving");
      if (state.pendingId && !activeStatuses.has(state.operation?.status)) return text("unknown");
      const info = operationProgress(); if (info) return operationText(info) + (state.notice === "pendingUnavailable" ? " · " + text("pendingUnavailable") : "");
      if (blocked()) return text("progressWaiting");
      if (state.notice) return text(state.notice);
      const n = enabled().length; return n ? text("ready").replace("{n}", String(n)) : text("empty");
    }
    function render() {
      bar.hidden = state.allowed !== true; if (!state.allowed && dialog.open) dialog.close();
      expanded.hidden = !state.allowed || !state.expanded;
      runButton.textContent = text("run"); configButton.textContent = text("configAll"); heading.textContent = state.configRepoId ? repoName(state.settings?.repositories.find(repo => repo.id === state.configRepoId)) + " · " + text("config") : text("configAll"); closeButton.textContent = text("close");
      toggleButton.textContent = state.expanded ? "⌃" : "⌄"; toggleButton.disabled = !state.allowed; toggleButton.setAttribute("aria-label", text(state.expanded ? "collapse" : "expand")); toggleButton.setAttribute("aria-expanded", String(state.expanded)); toggleButton.setAttribute("aria-controls", expanded.id);
      configButton.setAttribute("aria-controls", dialog.id); configButton.setAttribute("aria-expanded", String(dialog.open));
      shortStatus.textContent = statusText(); detailStatus.textContent = statusText(); shortStatus.dataset.state = state.error ? "error" : blocked() ? "working" : "ready";
      const info = operationProgress(); progress.hidden = !state.allowed || !info;
      if (info) { progress.setAttribute("aria-label", text("progressLabel")); progress.setAttribute("aria-valuemin", "0"); progress.setAttribute("aria-valuemax", String(info.total)); progress.setAttribute("aria-valuenow", String(info.completed)); progress.setAttribute("aria-valuetext", statusText()); progress.dataset.completed = String(info.completed); progress.dataset.total = String(info.total); progress.dataset.active = String(activeStatuses.has(state.operation?.status)); progress.dataset.outcome = info.attention || info.review || info.completed < info.total && !activeStatuses.has(state.operation?.status) ? "attention" : "success"; progressFill.style.width = String(Math.round(100 * info.completed / info.total)) + "%"; }
      runButton.disabled = !state.allowed || !state.settings || !enabled().length || blocked() || state.readBusy || state.saveBusy || state.dirty || state.invalid.size > 0;
      configButton.disabled = !state.allowed; addButton.disabled = blocked() || state.saveBusy || inputPending.size > 0; refreshButton.disabled = state.readBusy || state.postBusy || state.saveBusy;
      previewButton.disabled = blocked() || state.previewBusy || state.saveBusy || state.dirty || !enabled().length;
      resumeButton.textContent = text("resumeOriginal"); resumeButton.hidden = !(state.notFound && state.pendingRequest?.requestId === state.pendingId);
      resumeButton.disabled = state.postBusy || state.serverBusy || state.readBusy || state.saveBusy || state.previewBusy || state.dirty || !state.allowed;
      for (const input of controls) input.disabled = blocked();
      for (const retry of resultRetries) retry.disabled = blocked() || state.readBusy || state.saveBusy || state.dirty;
      for (const label of state.localized) label.item[label.property] = text(label.key);
      refreshButton.textContent = text(state.configConflict ? "reloadConfig" : "refresh");
      if (dialog.open) renderWarnings();
      renderCompactRows(); renderConfigVisibility(); renderVersionPlans(); renderDiagnosis();
    }
    function repoName(repo) {
      const url = clean(repo?.repositoryUrl).split(/[?#]/)[0].replace(/\/+$/, ""), match = url.match(/^(?:https:\/\/github\.com\/|git@github\.com:)[^/]+\/([^/]+)$/i);
      if (match) { try { return clean(decodeURIComponent(match[1].replace(/\.git$/i, "")), 160); } catch { return clean(match[1].replace(/\.git$/i, ""), 160); } }
      return clean(repo?.name, 160) || clean(repo?.path).split(/[\\/]/).filter(Boolean).pop() || text("repo");
    }
    function componentLabel(component, count) { return count > 1 ? (clean(component.name, 80) || clean(component.path, 120) || text("component")) + " " : ""; }
    function sourceIdentity(repo, naming = state.settings?.naming) { return JSON.stringify([repo.path, repo.repositoryUrl, repo.remote, repo.branch, repo.versionSources, repo.syncFiles, repo.exclude, repo.versionPlans, naming?.autoBump]); }
    function sourceIdentities(settings) { return new Map(settings.repositories.map(repo => [repo.id, sourceIdentity(repo, settings.naming)])); }
    function catalogFor(repo) { const catalog = state.catalog.get(repo.id); return catalog?.sourceIdentity === sourceIdentity(repo) ? catalog : null; }
    const diagnosticCategories = new Set(["connection", "sync", "activity", "repository", "versions", "naming", "verification", "authentication", "permissions", "rules", "lfs", "network", "remote", "unknown"]);
    const diagnosticTargets = new Map([
      ...[["repo_missing", "path"], ["repo_root", "path"], ["branch_mismatch", "branch"], ["remote_config", "remote"], ["remote_ownership", "repositoryUrl"], ["duplicate_repository", "path"]].map(([code, field]) => [code, ["connection", new Set([field])]]),
      ...["sync_config", "sync_missing", "sync_writing", "sync_changed"].map(code => [code, ["sync", new Set(["sync"])]]),
      ...["version_authority", "version_plan_stale", "version_plan_blocked"].map(code => [code, ["versions", new Set(["versionPath"])]]),
      ["version_fallback", ["naming", new Set(["fallbackTitle"])]]
    ]);
    function safeDiagnosticText(value, length = 1200) { return clean(value, length).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, ""); }
    function normalizedDiagnostic(value) {
      if (!plain(value) || !/^[a-z][a-z0-9_]{0,79}$/.test(value.code || "") || !["info", "warning", "error"].includes(value.severity) || !safeDiagnosticText(value.summary)) return null;
      const category = diagnosticCategories.has(value.category) ? value.category : "unknown", allowed = diagnosticTargets.get(value.code);
      let target = null;
      if (allowed && category === allowed[0] && plain(value.target) && value.target.section === allowed[0] && allowed[1].has(value.target.field)
        && (value.target.sourceId === undefined && allowed[0] !== "versions" || typeof value.target.sourceId === "string" && /^[A-Za-z0-9_-]{1,120}$/.test(value.target.sourceId))) {
        target = { section: allowed[0], field: value.target.field, ...(value.target.sourceId ? { sourceId: value.target.sourceId } : {}) };
      }
      return { code: value.code, category, severity: value.severity, summary: safeDiagnosticText(value.summary), nextStep: safeDiagnosticText(value.nextStep), target };
    }
    function readFor(repo) { const value = state.versionReads.get(repo.id); return value?.sourceIdentity === sourceIdentity(repo) ? value : null; }
    function readErrorDiagnostic(error) {
      return error?.diagnostic || { code: error?.kind === "timeout" ? "read_timeout" : error?.kind === "invalid_response" ? "read_invalid" : "read_unavailable", category: "network", severity: "warning", summary: error?.safeMessage || text(error?.kind === "timeout" ? "readTimeout" : error?.kind === "invalid_response" ? "readInvalid" : "readConnection"), nextStep: text("readNext"), target: null };
    }
    function diagnosisFor(repo) {
      const catalog = catalogFor(repo), reading = readFor(repo), original = state.operation?.results.find(item => item.repoId === repo.id), result = uploadBindingMatches(original?.uploadSummary, repo) ? original : null;
      const wrap = (diagnostic, origin, metadata = "") => {
        const target = diagnostic.target, component = target?.section === "versions" && catalog?.components.find(item => item.sourceId === target.sourceId);
        const located = target?.section !== "versions" || component && repo.versionSources.some(source => source.path === component.path && source.kind === component.kind && source.key === component.key);
        return { ...diagnostic, target: located ? target : null, origin, metadata, repoId: repo.id, sourceIdentity: sourceIdentity(repo) };
      };
      if (reading?.busy) return wrap({ summary: text(catalog ? "updatingLocal" : "readingLocal"), nextStep: text("readingHint"), severity: "info", target: null }, "diagnosisRead", catalog ? text("knownBefore") : "");
      if (reading?.error) return wrap(readErrorDiagnostic(reading.error), "diagnosisRead", catalog ? text("knownBefore") : "");
      if (state.statusReadError?.sources.get(repo.id) === sourceIdentity(repo)) return wrap(readErrorDiagnostic(state.statusReadError.error), "diagnosisRead");
      if (result && activeStatuses.has(result.status)) return wrap(normalizedDiagnostic(result.diagnostic) || { summary: [phaseText(result.phase), safeDiagnosticText(result.message)].filter(Boolean).join(" · "), nextStep: text("waitOperation"), severity: "info", target: null }, "diagnosisOperation");
      const currentDiagnostic = normalizedDiagnostic(catalog?.diagnostic);
      if (currentDiagnostic && currentDiagnostic.severity !== "info") return wrap(currentDiagnostic, "diagnosisRead");
      if (result && (failedRepoStatuses.has(result.status) || reviewRepoStatuses.has(result.status) || result.uploadSummary?.state === "pending")) return wrap(normalizedDiagnostic(result.diagnostic) || { summary: safeDiagnosticText(result.message) || text(result.uploadSummary?.state === "pending" ? "uploadPending" : "repoAttention"), nextStep: text("inspectOriginal"), severity: "warning", target: null }, "diagnosisOperation");
      if (currentDiagnostic) return wrap(currentDiagnostic, "diagnosisRead");
      if (catalog) return wrap({ summary: safeDiagnosticText(catalog.message) || safeDiagnosticText(catalog.syncState === "unknown" ? catalog.syncReason : "") || safeDiagnosticText(catalog.components?.find(item => !item.currentVersion && item.reason)?.reason) || safeDiagnosticText(catalog.changesReason) || changeHint(catalog), nextStep: text("notReadNext"), severity: "info", target: null }, "diagnosisRead", reading?.checkedAt ? text("checkedAt") + " · " + reading.checkedAt : "");
      if (original && !result) return wrap({ summary: text("historicalHint"), nextStep: text("inspectOriginal"), severity: "info", target: null }, "diagnosisHistory");
      return wrap({ summary: text(blocked() ? "publishingRead" : "notRead"), nextStep: text(state.dirty ? "configDraftRead" : blocked() ? "waitOperation" : "notReadNext"), severity: "info", target: null }, "diagnosisRead");
    }
    function renderDiagnosis() {
      const repo = state.settings?.repositories.find(item => item.id === state.configRepoId);
      diagnosisBox.hidden = !dialog.open || !repo; if (!repo || !dialog.open) return;
      const value = diagnosisFor(repo); state.diagnosisPresentation = value;
      diagnosisHeading.textContent = text("diagnosis"); diagnosisSummary.textContent = value.summary; diagnosisNext.textContent = value.nextStep ? text("diagnosisNext") + " · " + value.nextStep : "";
      diagnosisNext.hidden = !value.nextStep; diagnosisMeta.textContent = [text(value.origin), value.metadata].filter(Boolean).join(" · "); diagnosisBox.dataset.severity = value.severity;
      diagnosisLocate.textContent = text("locateSetting"); diagnosisLocate.hidden = !value.target; diagnosisLocate.disabled = !state.allowed;
      diagnosisRecheck.textContent = text("recheckRepository"); diagnosisRecheck.disabled = blocked() || state.versionBusy || state.readBusy || state.saveBusy || state.dirty || state.invalid.size > 0;
    }
    function childrenOf(parent) { return parent ? [parent, ...Array.from(parent.children || []).flatMap(childrenOf)] : []; }
    function focusDiagnosticTarget(value = state.diagnosisPresentation) {
      const repo = state.settings?.repositories.find(item => item.id === value?.repoId), target = value?.target;
      if (!repo || !target || state.destroyed || !state.allowed || !dialog.open || state.configRepoId !== repo.id || value.sourceIdentity !== sourceIdentity(repo)) return;
      const sections = configSections.get(repo.id); let container, fieldName = target.field;
      if (target.section === "connection") { container = sections?.connection; if (container) container.open = true; }
      else if (target.section === "sync") { container = sections?.rules; if (container) container.open = true; }
      else if (target.section === "versions") {
        if (sections?.rules) sections.rules.open = true; container = sections?.versions;
        if (target.sourceId) {
          const component = catalogFor(repo)?.components.find(item => item.sourceId === target.sourceId);
          const row = component && childrenOf(container).find(item => item.dataset?.sourcePath === component.path && item.dataset?.sourceKind === component.kind && item.dataset?.sourceKey === component.key);
          if (!row) { sections?.rules?.children[0]?.focus(); return; } container = row;
        }
      } else if (target.section === "naming") { state.diagnosticNaming = true; namingDetails.hidden = false; namingDetails.open = true; container = namingFields; fieldName = target.field === "fallbackTitle" ? "fallback" : target.field; }
      if (!container) return;
      const field = childrenOf(container).find(item => item.dataset?.field === fieldName);
      const focus = field && !field.disabled ? field : container.children[0];
      if (focus) { if (field) field.setAttribute("aria-describedby", diagnosisSummary.id); focus.scrollIntoView?.({ block: "center" }); focus.focus(); }
    }
    diagnosisLocate.addEventListener("click", () => focusDiagnosticTarget());
    diagnosisRecheck.addEventListener("click", () => { if (!diagnosisRecheck.disabled && state.configRepoId) void readVersions(state.configRepoId); });
    function repoChangeState(catalog) {
      if (!catalog || typeof catalog.hasChanges !== "boolean") return "unknown";
      const expected = catalog.hasChanges ? "changed" : "unchanged";
      return catalog.changeState === expected ? expected : "unknown";
    }
    function changeHint(catalog) {
      const status = repoChangeState(catalog);
      if (status === "unknown") return text("changeUnknown");
      if (status === "unchanged") return text("repoNoChanges");
      if (Number.isSafeInteger(catalog.outgoingCommits) && catalog.outgoingCommits > 0) return text(catalog.worktreeChanged === true || catalog.syncChanged === true ? "localAndOutgoing" : "outgoing");
      if (catalog.syncChanged === true && catalog.worktreeChanged === false) return text("syncChanges");
      return text("localChanges");
    }
    function componentTransition(component, catalog) {
      const transition = component?.transition;
      if (!plain(transition) || !["planned", "working", "auto"].includes(transition.kind)
        || !clean(component.currentVersion, 80) || !clean(transition.fromVersion, 80)
        || !clean(transition.toVersion, 80) || transition.fromVersion === transition.toVersion) return null;
      if (transition.kind === "planned" && (component.planState !== "valid"
        || transition.fromVersion !== component.currentVersion || transition.toVersion !== component.plannedVersion)) return null;
      if (transition.kind === "working" && (component.versionChanged !== true
        || transition.fromVersion !== component.headVersion || transition.toVersion !== component.currentVersion)) return null;
      if (transition.kind === "auto" && (state.settings?.naming?.autoBump !== true
        || repoChangeState(catalog) !== "changed" || catalog.worktreeChanged !== true
        || component.worktreeChanged !== true || component.canBump !== true || component.autoPlan?.state !== "eligible"
        || component.autoPlan.fromVersion !== component.currentVersion || transition.fromVersion !== component.currentVersion
        || transition.toVersion !== component.autoPlan.targetVersion)) return null;
      return transition;
    }
    function componentVersionText(component, count, catalog) {
      const transition = componentTransition(component, catalog);
      return componentLabel(component, count) + (transition
        ? clean(transition.fromVersion, 80) + " → " + clean(transition.toVersion, 80)
        : clean(component.currentVersion, 80) || text("versionFailed"));
    }
    function displayIdentity(repo) { return JSON.stringify([repo.id, repo.path, repo.repositoryUrl, repo.remote, repo.branch]); }
    function componentChanged(component) { return component.worktreeChanged === true || component.versionChanged === true; }
    function uploadBindingMatches(summary, repo) {
      const binding = summary?.binding;
      return plain(summary) && summary.source === "console_confirmed_deliveries" && ["recorded", "pending", "unknown"].includes(summary.state)
        && plain(binding) && binding.repoId === repo.id && ["path", "repositoryUrl", "remote", "branch"].every(key => typeof binding[key] === "string" && binding[key] === repo[key]);
    }
    function uploadSummary(repo, catalog) {
      const result = state.operation?.results.find(item => item.repoId === repo.id);
      for (const value of [result?.uploadSummary, state.uploadSummaries.get(repo.id), catalog?.uploadSummary]) if (uploadBindingMatches(value, repo)) return value;
      return null;
    }
    function uploadNumber(summary) {
      return summary?.state === "recorded" && Number.isSafeInteger(summary.count) && summary.count >= 0
        && (summary.count === 0 || /^[0-9a-f]{40,64}$/.test(summary.commitSha || "") && typeof summary.verifiedAt === "string" && Number.isFinite(Date.parse(summary.verifiedAt)))
        ? text("uploadNumber").replace("{n}", String(summary.count)) : text("uploadUnknown");
    }
    function hasMultipleVersions(repo, catalog) { return (catalog?.components || []).length > 1 || (repo.versionSources || []).length > 1 || state.multiBindings.has(displayIdentity(repo)); }
    function componentChangeState(component, catalog) {
      if (componentChanged(component)) return "changed";
      return component.worktreeChanged === false || repoChangeState(catalog) === "unchanged" ? "unchanged" : "unknown";
    }
    function versionSummary(repo) {
      const catalog = catalogFor(repo), components = catalog?.components || [];
      if (hasMultipleVersions(repo, catalog)) return uploadNumber(uploadSummary(repo, catalog));
      if (!components.length && catalog?.versionState === "missing") return text("authorityMissing");
      if (!components.length) return text(state.versionBusy ? "loading" : state.versionFailed || catalog?.message ? "versionFailed" : catalog ? "noVersion" : "versionPending");
      return componentVersionText(components[0], components.length, catalog);
    }
    function renderVersionPicker(refs, repo, catalog) {
      const components = catalog?.components || [], multiple = hasMultipleVersions(repo, catalog);
      if (workspacePanel.hidden || !state.expanded || !state.allowed || readFor(repo)?.busy) refs.picker.open = false;
      refs.picker.hidden = !multiple;
      if (!multiple) { refs.picker.open = false; if (refs.version.parentElement !== refs.cell) refs.cell.append(refs.version); return; }
      if (refs.version.parentElement !== refs.summary) refs.summary.append(refs.version, refs.arrow);
      refs.summary.setAttribute("aria-label", [refs.version.textContent, text("displayVersion")].join(" · "));
      const uploaded = uploadSummary(repo, catalog);
      const reading = readFor(repo), signature = JSON.stringify([language(), displayIdentity(repo), components, state.settings.naming.autoBump, uploaded, Boolean(reading?.busy), Boolean(reading?.error)]);
      if (signature === refs.menuSignature) return;
      refs.menuSignature = signature; refs.picker.open = false; refs.menu.replaceChildren();
      refs.menu.append(node("h4", "repository-publish-version-group", text("pluginDetails")));
      if (catalog && (reading?.busy || reading?.error)) refs.menu.append(node("p", "repository-publish-version-note", text("knownBefore")));
      if (!components.length) refs.menu.append(node("p", "repository-publish-version-note", text(state.versionBusy ? "loading" : "versionPending")));
      const changed = components.filter(componentChanged), others = components.filter(item => !componentChanged(item));
      for (const [key, items] of [["changedPlugins", changed], ["otherPlugins", others]]) {
        if (!items.length) continue;
        refs.menu.append(node("hr", "repository-publish-version-divider"), node("h4", "repository-publish-version-group", text(key)));
        for (const component of items) {
          const option = node("div", "repository-publish-version-option", componentVersionText(component, components.length, catalog));
          option.dataset.sourceId = clean(component.sourceId, 120); option.dataset.changeState = componentChangeState(component, catalog);
          option.title = clean(component.path, 200); refs.menu.append(option);
        }
      }
      refs.menu.append(node("p", "repository-publish-version-note", text("uploadHint")));
      if (uploaded?.state !== "recorded") refs.menu.append(node("p", "repository-publish-version-note", clean(uploaded?.reason, 240) || text("uploadPending")));
    }
    function renderCompactRows() {
      const repos = state.settings?.repositories || [];
      for (const [id, refs] of compactRefs) if (!repos.some(repo => repo.id === id)) { refs.row.remove(); compactRefs.delete(id); }
      for (const repo of repos) {
        let refs = compactRefs.get(repo.id);
        if (!refs) {
          const row = node("div", "repository-publish-compact-row"), name = node("strong", "repository-publish-compact-name"), version = node("span", "repository-publish-compact-version"), status = managed(node("button", "repository-publish-compact-status")), configure = managed(node("button", "ghost-button repository-publish-row-config")); configure.type = status.type = "button";
          const cell = node("div", "repository-publish-version-cell"), picker = managed(node("details", "repository-publish-version-picker")), summary = node("summary", "repository-publish-version-trigger"), arrow = node("span", "repository-publish-version-arrow", "⌄"), menu = node("div", "repository-publish-version-menu");
          arrow.setAttribute("aria-hidden", "true"); picker.append(summary, menu); cell.append(version, picker);
          row.dataset.repoId = repo.id; row.append(name, cell, status, configure); compactRows.append(row); refs = { row, name, version, status, configure, cell, picker, summary, arrow, menu, menuSignature: "" }; compactRefs.set(repo.id, refs);
          picker.addEventListener("toggle", () => { if (picker.open) for (const other of compactRefs.values()) if (other !== refs) other.picker.open = false; });
          picker.addEventListener("keydown", event => { if (event.key === "Escape" && picker.open) { event.preventDefault(); picker.open = false; summary.focus(); } });
          configure.addEventListener("click", () => open(repo.id));
          status.addEventListener("click", () => { if (!state.destroyed && state.allowed) { open(repo.id, { diagnose: true }); detail.open = Boolean(state.operation?.results.some(item => item.repoId === repo.id)); renderResults(); dialog.scrollTop = 0; } });
        }
        const originalResult = state.operation?.results.find(item => item.repoId === repo.id);
        const result = uploadBindingMatches(originalResult?.uploadSummary, repo) ? originalResult : null;
        const catalog = catalogFor(repo), reading = readFor(repo), changeState = reading?.busy || reading?.error ? "unknown" : repoChangeState(catalog), diagnostic = normalizedDiagnostic(catalog?.diagnostic);
        refs.name.textContent = repoName(repo); refs.version.textContent = versionSummary(repo); refs.version.dataset.changeState = changeState;
        refs.version.title = [refs.version.textContent, hasMultipleVersions(repo, catalog) ? text("uploadHint") : changeHint(catalog), clean(catalog?.message, 300), clean(catalog?.changesReason, 300), clean(catalog?.remoteReference, 160)].filter(Boolean).join(" · ");
        renderVersionPicker(refs, repo, catalog);
        refs.status.textContent = repo.enabled !== true ? text("disabledRepo") : originalResult && !result ? text("historicalReceipt") : result && activeStatuses.has(result.status) ? phaseText(result.phase)
          : result && successfulRepoStatuses.has(result.status) ? text("uploaded") + (result.uploadSummary?.state === "pending" ? " · " + text("uploadPending") : "")
            : result && skippedRepoStatuses.has(result.status) ? text("repoNoChanges")
              : result && reviewRepoStatuses.has(result.status) ? text("verifyRequired")
                : result && failedRepoStatuses.has(result.status) ? text(result.status === "deferred" ? "deferred" : "failed")
                  : reading?.busy ? text(catalog ? "updatingLocal" : "readingLocal") : reading?.error ? readErrorDiagnostic(reading.error).summary
                    : diagnostic && diagnostic.severity !== "info" ? text("repoAttention") : catalog ? changeHint(catalog) : text(blocked() ? "publishingRead" : "notRead");
        refs.status.dataset.changeState = changeState;
        refs.status.dataset.status = originalResult && !result ? "historical" : clean(result?.status, 60); refs.status.disabled = !state.allowed;
        refs.status.title = [text("diagnosis"), diagnosisFor(repo).summary, reading?.busy && catalog ? text("knownBefore") : ""].filter(Boolean).join(" · "); refs.configure.textContent = text("config"); refs.configure.disabled = !state.allowed;
      }
    }
    function renderConfigVisibility() {
      for (const [id, card] of configCards) { card.children[0].textContent = repoName(state.settings?.repositories.find(repo => repo.id === id)); card.hidden = Boolean(state.configRepoId && id !== state.configRepoId); if (state.configRepoId === id) card.open = true; }
      addButton.hidden = Boolean(state.configRepoId); namingDetails.hidden = Boolean(state.configRepoId && !state.diagnosticNaming);
      if (state.configRepoId) warningDetails.hidden = true;
    }
    async function readVersions(repoId = null) {
      if (state.destroyed || !state.allowed || !state.settings || state.versionBusy || workspacePanel.hidden || blocked()) return;
      if (state.dirty || state.saveBusy) { state.needsVersionsRead = true; return; }
      const selected = state.settings.repositories.filter(repo => !repoId || repo.id === repoId); if (!selected.length) return;
      const sources = sourceIdentities(state.settings), epoch = state.versionEpoch, reads = new Map(selected.map(repo => [repo.id, { sourceIdentity: sources.get(repo.id), busy: true, error: null, checkedAt: readFor(repo)?.checkedAt || "" }]));
      for (const [id, reading] of reads) state.versionReads.set(id, reading);
      state.versionBusy = true; state.versionFailed = false; state.needsVersionsRead = false; render();
      try {
        const value = await request("/versions" + (repoId ? "?repoId=" + encodeURIComponent(repoId) : "")); if (state.destroyed) return;
        if (state.versionEpoch !== epoch) { state.needsVersionsRead = true; return; }
        if (!Array.isArray(value.repositories)) { const error = new Error("invalid_versions_receipt"); error.kind = "invalid_response"; throw error; }
        for (const selectedRepo of selected) {
          const repo = state.settings.repositories.find(repo => repo.id === selectedRepo.id), items = value.repositories.filter(item => plain(item) && item.repoId === selectedRepo.id);
          if (repo && sources.get(repo.id) === sourceIdentity(repo) && items.length === 1 && Array.isArray(items[0].components)) {
            const item = items[0];
            const components = Array.isArray(item.components) ? clone(item.components.filter(plain)) : [];
            if (components.length > 1) state.multiBindings.add(displayIdentity(repo));
            else if (components.length === 1 || item.versionState === "missing") state.multiBindings.delete(displayIdentity(repo));
            state.catalog.set(repo.id, { ...clone(item), sourceIdentity: sources.get(repo.id), components });
            reads.get(repo.id).checkedAt = new Date().toISOString();
          } else if (repo && sources.get(repo.id) === sourceIdentity(repo)) {
            const error = new Error("invalid_repository_receipt"); error.kind = "invalid_response"; reads.get(repo.id).error = error; state.versionFailed = true;
          }
        }
      } catch (error) { if (epoch === state.versionEpoch) { state.versionFailed = true; for (const reading of reads.values()) reading.error = error; } else state.needsVersionsRead = true; }
      finally { for (const reading of reads.values()) reading.busy = false; state.versionBusy = false; render(); readCompletedSettings(); }
    }
    function renderVersionPlans() {
      for (const repo of state.settings?.repositories || []) {
        const box = planBoxes.get(repo.id); if (!box) continue;
        box.replaceChildren(); const heading = node("h4", "repository-publish-plan-heading", text("versionSummary")); box.append(heading);
        const catalog = catalogFor(repo), components = catalog?.components || [], seen = new Set();
        for (const component of components) {
          const plan = repo.versionPlans.find(item => item.sourceId === component.sourceId), row = node("div", "repository-publish-plan-row"), label = node("span"), action = managed(node("button", "ghost-button repository-publish-plan-action")); action.type = "button"; seen.add(component.sourceId);
          const transition = componentTransition(component, catalog), hint = node("span", "repository-publish-plan-reason");
          label.textContent = componentVersionText(component, components.length, catalog);
          label.title = [clean(component.path, 200), clean(component.key, 120), clean(component.versionCommitSha, 40), clean(component.sourceHeadSha, 40)].filter(Boolean).join(" · ");
          hint.textContent = transition ? text(transition.kind === "planned" ? "planned" : transition.kind === "auto" ? "automaticVersion" : "actualVersionChange")
            : plan ? text("planUnverified") + " · " + text("planTarget") + " " + clean(plan.targetVersion, 80) : text("keepCurrent");
          if (!plan && !transition && component.canBump === true && clean(component.currentVersion, 80) && clean(component.nextVersion, 80)) hint.textContent += " · " + text("candidateVersion") + " " + clean(component.nextVersion, 80);
          if (component.kind === "git_commit") hint.textContent += " · " + text("gitCommitHint");
          action.textContent = text(plan ? "cancelPlan" : "nextPatch"); action.disabled = blocked() || state.saveBusy || inputPending.size > 0 || state.versionBusy || !plan && (component.canBump !== true || typeof component.sourceId !== "string" || !component.sourceId || typeof component.currentVersion !== "string" || !component.currentVersion || typeof component.nextVersion !== "string" || !component.nextVersion || !/^[a-f0-9]{64}$/.test(component.planProof) || !/^[a-f0-9]{64}$/.test(component.expectedSha256) || !Number.isSafeInteger(component.expectedBytes) || component.expectedBytes < 0);
          action.addEventListener("click", () => { if (action.disabled || blocked() || state.saveBusy || inputPending.size) return; repo.versionPlans = repo.versionPlans.filter(item => item.sourceId !== component.sourceId); if (!plan) repo.versionPlans.push({ sourceId: component.sourceId, currentVersion: component.currentVersion, targetVersion: component.nextVersion, expectedSha256: component.expectedSha256, expectedBytes: component.expectedBytes, planProof: component.planProof }); changed(); });
          row.append(label, action, hint); if (component.canBump !== true) row.append(node("span", "repository-publish-plan-reason", clean(component.reason, 300) || text("versionUnsupported"))); box.append(row);
        }
        for (const plan of repo.versionPlans) if (!seen.has(plan.sourceId)) {
          const row = node("div", "repository-publish-plan-row"), cancel = managed(node("button", "ghost-button", text("cancelPlan"))); cancel.type = "button"; cancel.disabled = blocked() || state.saveBusy || inputPending.size > 0;
          row.append(node("span", "", text("planUnverified") + " · " + text("planTarget") + " " + clean(plan.targetVersion, 80)), cancel); box.append(row);
          cancel.addEventListener("click", () => { if (cancel.disabled || blocked() || state.saveBusy || inputPending.size) return; repo.versionPlans = repo.versionPlans.filter(item => item !== plan); changed(); });
        }
        if (!components.length && !repo.versionPlans.length) { const hint = node("p", "repository-publish-hint", versionSummary(repo)); hint.title = clean(catalog?.message, 300); box.append(hint); }
      }
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
      const timeoutMs = body === undefined ? path.split("?")[0] === "/versions" ? 60000 : 10000 : 20000;
      const timer = window.setTimeout(() => controller.abort(), timeoutMs);
      let response;
      try {
        response = await window.fetch(BASE + path, { method: body === undefined ? "GET" : "POST", credentials: "same-origin", mode: "same-origin", cache: "no-store", redirect: "error", referrerPolicy: "same-origin", headers: { Accept: "application/json", ...(body === undefined ? {} : { "Content-Type": "application/json" }) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: controller.signal });
        const value = await response.json();
        if (!response.ok || !plain(value) && !(value === null && body === undefined && path.startsWith("/operation?"))) {
          const error = new Error(path === "/config" && (response.status === 409 || value?.code === "settings_changed") ? "configConflict" : "request_failed");
          error.kind = response.ok ? "invalid_response" : "http"; error.httpStatus = response.status;
          error.safeMessage = safeDiagnosticText(value?.error); error.code = clean(value?.code, 80); error.diagnostic = normalizedDiagnostic(value?.diagnostic);
          throw error;
        }
        return value;
      } catch (error) {
        if (!error.kind) error.kind = controller.signal.aborted ? "timeout" : response ? "invalid_response" : "network";
        throw error;
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
      const closingPending = state.pendingId === value.requestId || activeStatuses.has(state.operation?.status);
      state.operation = { ...clone(value), results: clone(items) }; state.error = ""; state.notice = ""; state.notFound = false;
      if (activeStatuses.has(value.status)) { state.pendingId = value.requestId; persistId(state.pendingId); schedulePoll(); }
      else { state.pendingId = ""; state.pendingRequest = null; persistId("", value.requestId); stopPoll(); state.serverBusy = false; state.notice = ["success", "complete"].includes(value.status) ? "complete" : "interrupted"; if (closingPending) { state.needsSettingsRead = true; for (const id of state.operatedRepoIds) state.catalog.delete(id); state.versionEpoch++; state.needsVersionsRead = true; state.operatedRepoIds.clear(); } }
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
      finally { state.readBusy = false; render(); schedulePoll(); readCompletedSettings(); }
    }
    async function readStatus(reloadDraft = false) {
      if (state.destroyed || state.readBusy || state.postBusy || state.saveBusy) return;
      const edit = state.edit, sourcesAtRead = state.settings ? sourceIdentities(state.settings) : new Map();
      state.readBusy = true; render();
      try {
        const value = await request(); if (state.destroyed) return;
        state.statusReadError = null;
        state.allowed = value.allowed === true; state.serverBusy = value.busy === true;
        state.warnings = Array.isArray(value.warnings) ? value.warnings.slice(0, 100) : [];
        if ((!state.dirty || reloadDraft) && state.edit === edit) {
          if (!plain(value.settings) || !/^[a-f0-9]{64}$/.test(value.settingsSha)) { const error = new Error("settings_receipt_missing"); error.kind = "invalid_response"; throw error; }
          const saved = normalized(value.settings), sources = sourceIdentities(saved);
          if (state.settings && Array.from(sources).some(([id, identity]) => state.savedSources.get(id) !== identity)) { state.versionEpoch++; state.catalog.clear(); state.needsVersionsRead = true; previewResult.replaceChildren(); }
          state.settings = saved; state.settingsSha = value.settingsSha; state.savedSources = sources;
          state.uploadSummaries = new Map((Array.isArray(value.uploadSummaries) ? value.uploadSummaries : []).filter(item => plain(item) && typeof item.repoId === "string").map(item => [item.repoId, clone(item)]));
          state.dirty = false; state.configConflict = false; inputPending.clear();
          if (state.pendingRequest) for (const repo of state.settings.repositories) if (state.pendingRequest.repoIds.includes(repo.id)) state.operatedRepoIds.add(repo.id);
          syncDrafts.clear(); state.invalid.clear(); if (dialog.open) renderConfig();
        }
        const accepted = value.operation && acceptOperation(value.operation);
        if (!accepted && !state.dirty) { state.error = ""; state.notice = ""; }
        if (state.pendingId) schedulePoll();
      } catch (error) { state.error = "readFailed"; state.statusReadError = { error, sources: sourcesAtRead }; }
      finally { state.readBusy = false; render(); readCompletedSettings(); }
    }
    function readCompletedSettings() {
      if (state.destroyed || state.readBusy || state.postBusy || state.saveBusy) return;
      if (state.needsSettingsRead) { state.needsSettingsRead = false; void readStatus(); return; }
      if (state.needsVersionsRead && !state.versionBusy && !state.dirty) { state.needsVersionsRead = false; if (state.expanded || dialog.open) void readVersions(); }
    }
    function changed() {
      state.dirty = true; state.edit++; state.error = state.configConflict ? "configConflict" : ""; state.notice = ""; render(); void save();
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
      if (!state.dirty || state.saveBusy || state.destroyed || blocked() || inputPending.size || state.configConflict) return;
      if (!/^[a-f0-9]{64}$/.test(state.settingsSha)) { state.error = "readFailed"; render(); return; }
      if (state.invalid.size) { state.error = "invalidConfig"; render(); return; }
      if (checkDuplicates()) { state.error = "duplicate"; render(); return; }
      const edit = state.edit, payload = clone(state.settings); state.saveBusy = true; render();
      let succeeded = false;
      try {
        const value = await request("/config", { settings: payload, expectedSettingsSha: state.settingsSha }); if (state.destroyed) return;
        if (!plain(value.settings) || !/^[a-f0-9]{64}$/.test(value.settingsSha)) throw new Error("settings_receipt_missing");
        succeeded = true;
        const saved = normalized(value.settings), sources = sourceIdentities(saved);
        if (Array.from(sources).some(([id, identity]) => state.savedSources.get(id) !== identity)) { state.versionEpoch++; state.needsVersionsRead = true; previewResult.replaceChildren(); }
        state.savedSources = sources; state.settingsSha = value.settingsSha;
        if (state.edit === edit) { state.settings = saved; state.dirty = false; state.error = ""; state.notice = "saved"; syncDrafts.clear(); if (dialog.open) renderConfig(); }
      } catch (error) { if (error?.message === "configConflict") state.configConflict = true; state.error = state.configConflict ? "configConflict" : "saveFailed"; }
      finally { state.saveBusy = false; render(); if (succeeded && state.edit !== edit) void save(); else readCompletedSettings(); }
    }
    async function run(repoIds) {
      if (!state.allowed || !state.settings || blocked() || state.readBusy || state.saveBusy || state.dirty || state.invalid.size || !enabled().length) return;
      const requestId = uniqueId(), original = { requestId, repoIds: repoIds || enabled().map(repo => repo.id), createdAt: Date.now() };
      if (!requestId || !persistRequest(original)) { state.error = "noIdentity"; render(); return; }
      state.pendingRequest = original; await sendOriginal(original);
    }
    async function sendOriginal(original) {
      const requestId = original.requestId;
      state.operatedRepoIds = new Set(original.repoIds);
      stopPoll(); state.pendingId = requestId; state.notFound = false; state.operation = null; state.postBusy = true; state.error = ""; state.notice = "working"; renderResults(); render();
      try { const value = await request("/run", { requestId, repoIds: original.repoIds }); if (!acceptOperation(value.operation || value)) state.notice = "unknown"; }
      catch { state.notice = "unknown"; }
      finally { state.postBusy = false; render(); schedulePoll(); readCompletedSettings(); }
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
      input.addEventListener("input", () => { if (blocked() || state.destroyed) return; if (options.required) validate(); change(options.checkbox ? input.checked : input.value, input); inputPending.add(input); state.dirty = true; state.edit++; state.error = state.configConflict ? "configConflict" : ""; state.notice = ""; render(); });
      input.addEventListener("change", () => { if (blocked() || state.destroyed) return; inputPending.delete(input); if (options.required) validate(); change(options.checkbox ? input.checked : input.value, input); changed(); }); return input;
    }
    function renderConfig() {
      const previousOpen = new Map(Array.from(configCards, ([id, card]) => [id, { card: card.open, connection: configSections.get(id)?.connection.open, rules: configSections.get(id)?.rules.open }]));
      controls.length = 0; state.localized.length = 0; state.invalid.clear(); inputPending.clear(); configCards.clear(); configSections.clear(); planBoxes.clear(); repositories.replaceChildren(); namingFields.replaceChildren();
      localize(addButton, "add"); localize(namingSummary, "naming"); localize(detailSummary, "details"); localize(refreshButton, "refresh"); localize(previewButton, "preview"); localize(previewHint, "previewHint");
      for (const repo of state.settings?.repositories || []) {
        const card = node("details", "repository-publish-repo"), grid = node("div", "repository-publish-grid"), title = node("summary", "repository-publish-repo-title"); title.textContent = repoName(repo); card.dataset.repoId = repo.id;
        card.open = previousOpen.get(repo.id)?.card === true;
        card.append(title, grid); repositories.append(card); configCards.set(repo.id, card);
        field(grid, "enabled", repo.enabled, value => { repo.enabled = value; }, { checkbox: true });
        const planBox = node("div", "repository-publish-plan-box"); card.append(planBox); planBoxes.set(repo.id, planBox);
        const connection = node("details", "repository-publish-section repository-publish-connection"), connectionSummary = node("summary"), connectionGrid = node("div", "repository-publish-grid"); localize(connectionSummary, "connection"); connection.append(connectionSummary, connectionGrid); card.append(connection);
        connection.open = previousOpen.get(repo.id)?.connection === true;
        for (const key of ["path", "repositoryUrl", "remote", "branch"]) field(connectionGrid, key, repo[key], value => { repo[key] = value.trim(); }, key === "branch" ? { placeholder: "currentBranch" } : {});
        const rules = node("details", "repository-publish-section"), summary = node("summary"), ruleFields = node("div", "repository-publish-grid"); localize(summary, "rules"); rules.append(summary, ruleFields); card.append(rules);
        rules.open = previousOpen.get(repo.id)?.rules === true; configSections.set(repo.id, { connection, rules });
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
        configSections.get(repo.id).versions = versionBox;
        function versions() {
          for (let i = controls.length - 1; i >= 0; i--) if (versionBox.contains(controls[i])) controls.splice(i, 1);
          for (const invalid of state.invalid) if (versionBox.contains(invalid)) state.invalid.delete(invalid);
          for (const pending of inputPending) if (versionBox.contains(pending)) inputPending.delete(pending);
          state.localized = state.localized.filter(label => !versionBox.contains(label.item));
          versionBox.replaceChildren();
          for (const source of repo.versionSources) {
            const row = node("div", "repository-publish-version-row"); row.dataset.sourcePath = source.path; row.dataset.sourceKind = source.kind; row.dataset.sourceKey = source.key; versionBox.append(row);
            const formats = ["json", "xml", "unity", "unity_yaml", "python_ast", "text", "git_commit"];
            if (typeof source.kind === "string" && source.kind && !formats.includes(source.kind)) formats.push(source.kind);
            const inputs = new Map(), originHint = node("p", "repository-publish-hint repository-publish-version-origin");
            function sourceKindChanged() {
              const commit = source.kind === "git_commit";
              for (const [key, fixed] of [["path", "HEAD"], ["key", "subject"]]) {
                const input = inputs.get(key); if (!input) continue;
                input.readOnly = commit;
                if (commit) { source[key] = fixed; input.value = fixed; input.setCustomValidity(""); state.invalid.delete(input); inputPending.delete(input); }
              }
              originHint.hidden = !commit; originHint.textContent = text("gitCommitHint");
            }
            for (const [label, key] of [["versionPath", "path"], ["kind", "kind"], ["key", "key"], ["name", "name"], ["scope", "scope"]]) {
              const value = key === "scope" && Array.isArray(source.scope) ? source.scope.join("\n") : source[key];
              const input = field(row, label, value, next => {
                if (source.kind === "git_commit" && ["path", "key"].includes(key)) { sourceKindChanged(); return; }
                if (key === "scope") {
                  const scopes = next.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
                  source.scope = Array.isArray(source.scope) || scopes.length > 1 ? scopes : scopes[0] || "";
                } else source[key] = next.trim();
                if (key === "kind") sourceKindChanged();
              }, key === "kind" ? { options: formats.map(kind => kind === "git_commit" ? { value: kind, key: "gitCommitVersion" } : kind) } : key === "scope" ? { multiline: true } : key === "path" ? { required: true } : {});
              inputs.set(key, input);
            }
            row.append(originHint); localize(originHint, "gitCommitHint"); sourceKindChanged();
            const remove = managed(node("button", "ghost-button")); remove.type = "button"; localize(remove, "remove"); controls.push(remove); row.append(remove);
            remove.addEventListener("click", () => { if (blocked()) return; repo.versionSources.splice(repo.versionSources.indexOf(source), 1); versions(); changed(); });
          }
        }
        versions(); versionButton.addEventListener("click", () => { if (blocked()) return; repo.versionSources.push({ path: "", kind: "json", key: "version", name: "", scope: "" }); versions(); changed(); });
      }
      if (state.settings) {
        const naming = state.settings.naming;
        field(namingFields, "preset", naming.preset, value => { naming.preset = value; }, { options: [{ value: "version", key: "version" }, { value: "module_version", key: "module_version" }] });
        field(namingFields, "autoBump", naming.autoBump, value => { naming.autoBump = value; }, { checkbox: true });
        for (const [label, key] of [["fallback", "fallbackTitle"], ["subtitle", "subtitle"], ["notes", "notes"]]) field(namingFields, label, naming[key], value => { naming[key] = value; }, { multiline: key === "notes" });
        field(namingFields, "includeSummary", naming.includeSummary, value => { naming.includeSummary = value; }, { checkbox: true });
      }
      renderResults(); render();
    }
    function renderResults() {
      results.replaceChildren(); resultRetries.length = 0;
      const list = (state.operation?.results || []).filter(result => !state.configRepoId || result.repoId === state.configRepoId);
      if (!list.length) { const item = node("p", "repository-publish-hint"); localize(item, "noResults"); results.append(item); return; }
      for (const result of list) {
        const card = node("article", "repository-publish-result"), title = node("strong"), summary = node("p"), expanded = node("details"), expandedTitle = node("summary"), content = node("pre");
        const repo = state.settings?.repositories.find(item => item.id === result.repoId);
        const currentTarget = Boolean(repo && uploadBindingMatches(result.uploadSummary, repo));
        card.dataset.target = currentTarget ? "current" : "historical";
        title.textContent = clean(result.name || result.repoId, 200); summary.textContent = [clean(result.status, 60), clean(result.phase, 60), clean(result.message, 500)].filter(Boolean).join(" · "); localize(expandedTitle, "details");
        if (!currentTarget) card.append(node("p", "repository-publish-hint", text("historicalReceipt") + " · " + text("historicalHint")));
        const binding = result.uploadSummary?.binding;
        if (plain(binding)) {
          const destination = ["path", "repositoryUrl", "remote", "branch"].map(key => clean(binding[key], 500)).filter(Boolean).join(" · ");
          if (destination) card.append(node("p", "repository-publish-hint", text("originalTarget") + " · " + destination));
        }
        const logs = (Array.isArray(result.logs) ? result.logs : []).slice(-100).map(item => [clean(item.at, 80), clean(item.phase, 80), clean(item.message, 500)].filter(Boolean).join(" · ")).join("\n");
        content.textContent = [clean(result.title), clean(result.body, 16000), clean(result.commitSha, 80), logs].filter(Boolean).join("\n\n"); expanded.append(expandedTitle, content); card.append(title, summary, expanded); results.append(card);
        if (currentTarget && (["push_failed", "commit_failed", "conflict", "interrupted", "failed", "unknown", "index_pending", "deferred", "verification_required"].includes(result.status) || successfulRepoStatuses.has(result.status) && result.uploadSummary?.state === "pending" || state.operation?.status === "verification_required" && activeStatuses.has(result.status)) && typeof result.repoId === "string") {
          const retry = managed(node("button", "ghost-button")); retry.type = "button"; localize(retry, "retry"); card.append(retry); resultRetries.push(retry); retry.addEventListener("click", () => void run([result.repoId]));
        }
      }
    }
    async function preview(repoId) {
      if (blocked() || state.previewBusy || state.saveBusy || state.dirty || !enabled().length) return;
      const sources = sourceIdentities(state.settings), epoch = state.versionEpoch, selected = state.configRepoId;
      state.previewBusy = true; state.notice = "previewing"; previewResult.replaceChildren(); render();
      try {
        const value = await request("/preview", repoId ? { repoId } : {});
        if (state.destroyed || epoch !== state.versionEpoch || selected !== state.configRepoId) return;
        for (const result of Array.isArray(value.previews) ? value.previews : Array.isArray(value.results) ? value.results : Array.isArray(value.repositories) ? value.repositories : []) {
          const repo = state.settings.repositories.find(item => item.id === result?.repoId);
          if (!repo || sources.get(repo.id) !== sourceIdentity(repo) || selected && repo.id !== selected) continue;
          const versions = (Array.isArray(result.versions) ? result.versions : []).map(item => [clean(item.name), clean(item.version)].filter(Boolean).join(" · ")).filter(Boolean).join("\n");
          const card = node("article", "repository-publish-result"), title = node("strong"), summary = node("div", "repository-publish-preview-summary"), content = node("pre");
          title.textContent = clean(result.name || result.repoId || result.id, 200);
          const components = Array.isArray(result.components) ? result.components.filter(plain) : [];
          if (components.length) {
            summary.append(node("h4", "repository-publish-plan-heading", text("versionSummary")));
            for (const component of components) {
              const proposed = componentTransition(component, result), applies = result.planWillApply === true && result.action === "commit";
              const pendingTransition = ["planned", "auto"].includes(proposed?.kind);
              const shown = pendingTransition && !applies ? { ...component, transition: null } : component;
              const transition = componentTransition(shown, result), row = node("p", "repository-publish-preview-version", componentVersionText(shown, components.length, result));
              const hint = pendingTransition && !applies ? result.action === "sync_pending" ? "syncRecheck" : result.planWillApply === false ? "planKept" : "planApplyUnknown"
                : transition ? transition.kind === "planned" ? "planned" : transition.kind === "auto" ? "automaticVersion" : "actualVersionChange" : "keepCurrent";
              row.dataset.transition = transition?.kind || "none";
              row.append(node("span", "repository-publish-preview-version-hint", " · " + text(hint)));
              summary.append(row);
            }
          } else if (result.versionState === "missing") {
            summary.append(node("h4", "repository-publish-plan-heading", text("versionSummary")), node("p", "repository-publish-preview-version", text("authorityMissing")));
          }
          if (result.action === "push_only" || result.action === "sync_pending") summary.append(node("p", "repository-publish-preview-version-hint", text(result.action === "push_only" ? "pushOnly" : "syncRecheck")));
          content.textContent = [components.length ? "" : versions || clean(result.version), clean(result.title), clean(result.body, 16000), clean(result.message, 500)].filter(Boolean).join("\n\n"); card.append(title, summary, content); previewResult.append(card);
        }
        state.notice = ""; state.error = "";
      } catch { state.error = "previewFailed"; }
      finally { state.previewBusy = false; render(); if (state.dirty) void save(); }
    }
    function open(repoId = null, options = {}) {
      if (!state.allowed || state.destroyed) return;
      const selected = typeof repoId === "string" && state.settings?.repositories.some(repo => repo.id === repoId) ? repoId : null;
      if (selected !== state.configRepoId) previewResult.replaceChildren();
      state.diagnosticNaming = false;
      state.configRepoId = selected;
      state.returnFocus = document.activeElement; if (state.settings && !dialog.open && !state.dirty) renderConfig();
      if (!dialog.open) dialog.showModal(); renderResults(); render();
      if (options.diagnose !== true) { void readVersions(); if (state.pendingId) void poll(); else void readStatus(); }
    }
    runButton.addEventListener("click", () => void run()); configButton.addEventListener("click", () => open()); closeButton.addEventListener("click", () => dialog.close());
    toggleButton.addEventListener("click", () => { if (!state.allowed || state.destroyed) return; state.expanded = !state.expanded; render(); if (state.expanded) void readVersions(); });
    dialog.addEventListener("close", () => { render(); state.returnFocus?.focus(); });
    addButton.addEventListener("click", () => {
      if (!state.settings || blocked() || state.saveBusy || inputPending.size) return;
      const id = uniqueId(); if (!id) { state.error = "noIdentity"; render(); return; }
      state.settings.repositories.push({ id, path: "", repositoryUrl: "", remote: "origin", branch: "", enabled: false, syncFiles: [], versionSources: [], versionPlans: [], exclude: [] }); renderConfig(); configCards.get(id).open = true; changed();
    });
    refreshButton.addEventListener("click", () => { if (state.configConflict) void readStatus(true); else if (state.dirty) void save(); else { void readVersions(); if (state.pendingId) void poll(); else void readStatus(); } }); previewButton.addEventListener("click", () => void preview(state.configRepoId));
    resumeButton.addEventListener("click", () => void resumeOriginal());
    let observer = null;
    if (typeof MutationObserver === "function") { observer = new MutationObserver(() => { render(); }); observer.observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] }); }
    let visibilityObserver = null, wasHidden = workspacePanel.hidden, recheckBusy = false;
    function canRecheckVisible() {
      return !state.destroyed && !workspacePanel.hidden && (state.expanded || dialog.open) && state.allowed && state.settings
        && !blocked() && !state.dirty && !state.invalid.size && !inputPending.size && !state.saveBusy && !state.readBusy && !state.versionBusy;
    }
    async function recheckVisible() {
      if (recheckBusy || !canRecheckVisible()) return;
      recheckBusy = true; state.versionEpoch++; render();
      try {
        await readStatus();
        if (canRecheckVisible() && !state.error) await readVersions();
      } finally { recheckBusy = false; }
    }
    if (typeof MutationObserver === "function") {
      visibilityObserver = new MutationObserver(() => {
        const hidden = workspacePanel.hidden; if (hidden === wasHidden) return; wasHidden = hidden;
        if (hidden) { state.versionEpoch++; for (const refs of compactRefs.values()) refs.picker.open = false; } else void recheckVisible();
      });
      visibilityObserver.observe(workspacePanel, { attributes: true, attributeFilter: ["hidden"] });
    }
    function suspend() { stopPoll(); }
    function resume() { if (workspacePanel.hidden || state.destroyed) return; if (state.pendingId) schedulePoll(); else void recheckVisible(); }
    window.addEventListener("pagehide", suspend); window.addEventListener("pageshow", resume); window.addEventListener("focus", recheckVisible);
    function dismissVersionPickers(event) { for (const refs of compactRefs.values()) if (!refs.picker.contains(event.target)) refs.picker.open = false; }
    document.addEventListener("click", dismissVersionPickers);
    const api = { open, refresh: readStatus, hasDraft: () => state.dirty || state.invalid.size > 0, canReload: () => !state.dirty && !state.saveBusy && !state.postBusy && !state.previewBusy, destroy() { state.destroyed = true; stopPoll(); observer?.disconnect(); visibilityObserver?.disconnect(); window.removeEventListener("pagehide", suspend); window.removeEventListener("pageshow", resume); window.removeEventListener("focus", recheckVisible); document.removeEventListener("click", dismissVersionPickers); bar.remove(); expanded.remove(); dialog.remove(); mounted.delete(host); instances.delete(api); } };
    mounted.set(host, api); instances.add(api); render(); void readStatus(); return api;
  }
  window.ConsoleRepositoryPublish = { mount, hasDraft: () => Array.from(instances).some(item => item.hasDraft()), canReload: () => Array.from(instances).every(item => item.canReload()) };
  const mountDefault = () => { const host = document.getElementById("consoleRepositoryPublishHost"); if (host) mount({ host }); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mountDefault, { once: true });
  else mountDefault();
})();
