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
  copy.zh.run = "全部上传"; copy.zh.heading = "提交并上传"; copy.zh.pushOne = "上传"; copy.zh.commitPushHint = "提交并上传已保存的改动";
  copy.en.run = "Push All"; copy.en.heading = "Commit & Push"; copy.en.pushOne = "Push"; copy.en.commitPushHint = "Commit and push saved changes";
  copy.zh.checkAll = "检查全部"; copy.en.checkAll = "Check All";
  copy.zh.working = "正在提交并上传…"; copy.en.working = "Committing and pushing…";
  copy.zh.repoNoChanges = "无改动"; copy.en.repoNoChanges = "No changes";
  Object.assign(copy.zh, { expand: "展开仓库", collapse: "收起仓库", configAll: "配置全部", connection: "路径与远端", versionPlan: "版本计划", nextPatch: "使用下一个补丁版本", cancelPlan: "取消计划", noVersion: "未配置版本", versionPending: "版本待读取", versionFailed: "版本读取失败", noVersionChange: "不改版本", repoReady: "就绪", repoDone: "已完成", repoAttention: "需查看", repoWorking: "进行中", component: "组件", planned: "已计划", versionUnsupported: "此版本暂不能自动递增" });
  Object.assign(copy.en, { expand: "Show repositories", collapse: "Hide repositories", configAll: "Configure All", connection: "Folder and remote", versionPlan: "Version plan", nextPatch: "Use next patch", cancelPlan: "Cancel plan", noVersion: "No version configured", versionPending: "Version not read yet", versionFailed: "Could not read versions", noVersionChange: "Keep version", repoReady: "Ready", repoDone: "Completed", repoAttention: "Needs attention", repoWorking: "In progress", component: "Component", planned: "Planned", versionUnsupported: "Automatic version bump is unavailable" });
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
  Object.assign(copy.zh, { displayVersion: "查看插件版本", changedPlugins: "本次有改动", otherPlugins: "其他插件", uploadHint: "仓库主版本；各插件版本在下方单独列出。", uploadPending: "上传记录待核对", initialRepositoryVersion: "首次提交时初始化此主版本；尚未保存。", nothingToUpload: "已核对的仓库均无改动，无需提交或推送。", pluginDetails: "插件版本", processed: "已处理 {n}/{total}", succeeded: "成功 {n}", skipped: "跳过 {n}", attention: "需处理 {n}", review: "待核对 {n}", progressWaiting: "等待进度回执…", progressLabel: "仓库处理进度", phaseQueued: "等待处理", phaseCheck: "检查仓库", phaseSync: "同步工作文件", phaseRemote: "核对远端", phaseVersion: "准备版本", phaseCommit: "提交改动", phasePush: "上传", phaseVerify: "核验上传结果", phaseOther: "正在处理", uploaded: "已上传", deferred: "已暂缓", failed: "失败", verifyRequired: "待核对", detailsAction: "查看此仓库的处理详情" });
  Object.assign(copy.en, { displayVersion: "View plugin versions", changedPlugins: "Changed plugins", otherPlugins: "Other plugins", uploadHint: "Repository version; independent plugin versions are listed below.", uploadPending: "Upload record needs verification", initialRepositoryVersion: "This repository version will be initialized on its first commit; it has not been saved.", nothingToUpload: "All checked repositories have no changes; no commit or push is needed.", pluginDetails: "Plugin versions", processed: "Processed {n}/{total}", succeeded: "Succeeded {n}", skipped: "Skipped {n}", attention: "Needs attention {n}", review: "Unconfirmed {n}", progressWaiting: "Waiting for a progress receipt…", progressLabel: "Repository progress", phaseQueued: "Queued", phaseCheck: "Checking repository", phaseSync: "Syncing work files", phaseRemote: "Checking remote", phaseVersion: "Preparing versions", phaseCommit: "Committing", phasePush: "Uploading", phaseVerify: "Verifying upload", phaseOther: "Processing", uploaded: "Uploaded", deferred: "Deferred", failed: "Failed", verifyRequired: "Unconfirmed", detailsAction: "View this repository's operation details" });
  Object.assign(copy.zh, { historicalReceipt: "历史回执", historicalHint: "此回执未匹配当前仓库目标，保留原结果；不会按新配置重试。", originalTarget: "原上传目标" });
  Object.assign(copy.en, { historicalReceipt: "Historical receipt", historicalHint: "This receipt does not match the current repository target. Its original result is kept; retrying against the new configuration is unavailable.", originalTarget: "Original upload target" });
  Object.assign(copy.zh, { diagnosis: "原因与下一步", diagnosisRead: "当前读取", diagnosisOperation: "本次执行", diagnosisHistory: "历史执行", diagnosisNext: "下一步", locateSetting: "查看对应设置", recheckRepository: "重新核对此仓库", readingLocal: "读取版本与本地差异…", readingHint: "正在读取本机状态，最多等待 60 秒；不会同步、提交或推送。", updatingLocal: "更新核对中…", readTimeout: "读取已超时", readInvalid: "仓库状态回执不完整", readConnection: "暂时无法读取仓库状态", readNext: "稍后重新核对。原工作、配置与操作回执已保留。", notRead: "此仓库状态尚未核对", notReadNext: "点击重新核对，只读取本机仓库状态。", publishingRead: "上传处理中，结束后可重新核对版本。", waitOperation: "等待原操作完成；不要重复提交。", knownBefore: "显示上次读取结果，当前尚未重新核对。", checkedAt: "上次核对", inspectOriginal: "查看下方原回执。只在确认原目标后继续原请求。", configDraftRead: "配置草稿尚未保存；保留草稿，保存后再核对。" });
  Object.assign(copy.en, { diagnosis: "Reason and next step", diagnosisRead: "Current check", diagnosisOperation: "Operation receipt", diagnosisHistory: "Historical receipt", diagnosisNext: "Next step", locateSetting: "View the relevant setting", recheckRepository: "Recheck this repository", readingLocal: "Reading versions and local changes…", readingHint: "Reading local state, with a 60-second deadline. No sync, commit or push is performed.", updatingLocal: "Rechecking…", readTimeout: "Read timed out", readInvalid: "Repository receipt is incomplete", readConnection: "Repository state could not be read", readNext: "Recheck later. Your work, configuration and operation receipts are retained.", notRead: "This repository has not been checked", notReadNext: "Recheck to read local repository state only.", publishingRead: "Publishing is active; versions can be rechecked when it finishes.", waitOperation: "Wait for the original operation; do not submit it again.", knownBefore: "Showing the last reading; the current state is not yet rechecked.", checkedAt: "Last checked", inspectOriginal: "Inspect the original receipt below. Continue only after confirming its original target.", configDraftRead: "Configuration has an unsaved draft. Keep it and recheck after saving." });
  Object.assign(copy.zh, { refreshing: "正在核对", lastKnown: "上次状态", refreshFailed: "核对失败", gitObjects: "Git 对象", lfsObjects: "LFS 对象", lfsFile: "LFS 文件 {n}/{total}", phasePercent: "当前传输阶段", elapsed: "已用时 {time}", checkingReceipt: "回执待核对", repoProgress: "{name} · {phase}" });
  Object.assign(copy.en, { refreshing: "Refreshing", lastKnown: "Last known", refreshFailed: "Refresh failed", gitObjects: "Git objects", lfsObjects: "LFS objects", lfsFile: "LFS file {n}/{total}", phasePercent: "Current transfer phase", elapsed: "Elapsed {time}", checkingReceipt: "Receipt needs verification", repoProgress: "{name} · {phase}" });
  copy.zh.lastUpload = "上次上传"; copy.en.lastUpload = "Last upload";
  copy.zh.lastOperation = "上次操作"; copy.en.lastOperation = "Last operation";
  copy.zh.largeHistory = "旧提交含大文件，需转换历史"; copy.en.largeHistory = "Old commits contain large files; convert history to LFS";
  Object.assign(copy.zh, { uploadPaused: "暂停上传 · 查看原因", waitingCodex: "等待 Codex 完成", activityScope: "聊天范围待核对", activityCheck: "Codex 活动待核对", stagedSelection: "已有暂存选择", historyOperation: "Git 操作未完成", gitLocked: "检测到Git锁文件", mergeConflict: "先处理合并冲突", workChanged: "改动还在变化", folderCheck: "核对仓库目录", branchCheck: "核对目标分支", remoteCheck: "核对远端", syncMissing: "先保存工作文件", syncWriting: "等待文件保存完成", syncCheck: "核对文件同步", versionCheck: "核对版本来源", versionPlanCheck: "核对版本计划", authCheck: "Git 登录待处理", permissionCheck: "仓库权限待处理", rulesCheck: "上传规则未满足", lfsCheck: "LFS 上传待处理", networkCheck: "网络状态待核对", remoteHistory: "先整合远端历史", gitCheck: "Git 运行待核对", whyPaused: "为什么暂停上传", blockingWork: "相关 Codex 工作", notConfigIssue: "这是工作状态检查，无需修改仓库配置。", activityUnknown: "活动信息尚未确认；查看原原因，不会猜测聊天归属。" });
  Object.assign(copy.en, { uploadPaused: "Upload paused · See why", waitingCodex: "Waiting for Codex", activityScope: "Check the chat's scope", activityCheck: "Check Codex activity", stagedSelection: "Review staged changes", historyOperation: "Finish the Git operation", gitLocked: "Git lock file found", mergeConflict: "Resolve merge conflicts", workChanged: "Files are still changing", folderCheck: "Check the repository folder", branchCheck: "Check the target branch", remoteCheck: "Check the remote", syncMissing: "Save the work file first", syncWriting: "Waiting for the file to finish saving", syncCheck: "Check file sync", versionCheck: "Check the version source", versionPlanCheck: "Check the version plan", authCheck: "Git sign-in needs fixing", permissionCheck: "Check repository permissions", rulesCheck: "Upload rules need review", lfsCheck: "Check the LFS upload", networkCheck: "Check the network", remoteHistory: "Integrate remote changes first", gitCheck: "Check Git", whyPaused: "Why the upload is paused", blockingWork: "Related Codex work", notConfigIssue: "This is a work-state check. No repository setting needs changing.", activityUnknown: "Activity is not confirmed. See the original reason; no chat ownership is assumed." });
  Object.assign(copy.zh, { currentActivity: "当前 Codex 活动", checkingActivity: "正在核对当前聊天活动…", lastAttempt: "上次上传尝试", activityCleared: "聊天活动已解除；重试后继续核对仓库。", activityRetry: "重试以继续仓库检查", activityFailed: "当前活动未能核对，上次尝试的原因仍保留。", activityOnly: "本次只核对聊天活动，不代表 Git、文件或远端已就绪。" });
  Object.assign(copy.en, { currentActivity: "Current Codex activity", checkingActivity: "Checking current chat activity…", lastAttempt: "Last upload attempt", activityCleared: "Chat activity cleared; retry continues repository checks.", activityRetry: "Retry repository checks", activityFailed: "Current activity could not be checked. The last attempt's reason is retained.", activityOnly: "This checks chat activity only. Git, files and the remote still need checking." });
  Object.assign(copy.zh, { publishingOptions: "上传行为与命名", allowActiveWork: "Codex 工作时也上传已保存内容", allowActiveHint: "默认开启。聊天活动仅作提醒；文件仍在保存、暂存选择和 Git 冲突等问题仍会暂停。", activeAllowed: "有聊天在工作，允许上传已保存内容。", activityAllowedRetry: "可继续上传已保存内容", currentUnknown: "当前状态尚未核对；上次上传记录保留在下方。", previousPause: "上次暂停 · 查看当前状态", previousAttemptHint: "这是上次操作记录，不代表当前仍然受阻。", gitExit: "退出码 {n}", gitFailureKind: "错误类型", tlsFailed: "TLS连接失败" });
  Object.assign(copy.en, { publishingOptions: "Upload behavior and naming", allowActiveWork: "Upload saved work while Codex is working", allowActiveHint: "On by default. Chat activity is a notice; files still being saved, staged selections and Git conflicts can still pause an upload.", activeAllowed: "A chat is working; saved work may be uploaded.", activityAllowedRetry: "Continue with saved work", currentUnknown: "The current state has not been checked. The last upload record is kept below.", previousPause: "Previous pause · Check current state", previousAttemptHint: "This is the previous operation record; it does not establish a current blocker.", gitExit: "Exit code {n}", gitFailureKind: "Error kind", tlsFailed: "TLS connection failed" });
  copy.zh.previousPause = "可重试上传已保存内容"; copy.en.previousPause = "Retry upload of saved work";
  copy.zh.policyRetryHint = "已允许上传已保存内容；上次因聊天活动暂停。"; copy.en.policyRetryHint = "Saved-work uploads are enabled; the previous attempt paused for chat activity.";
  Object.assign(copy.zh, { commitAge: "提交 {age}", commitTime: "本机 HEAD 提交时间", commitUnknown: "尚无可核对的提交时间", commitClock: "提交时间晚于本机时间，请核对时钟。" });
  Object.assign(copy.en, { commitAge: "Commit {age}", commitTime: "Local HEAD commit time", commitUnknown: "No verified commit time is available", commitClock: "The commit time is ahead of this computer's clock; check the timestamp." });
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
        if (plain(parsed) && idOK(parsed.requestId) && storage.getItem(KEY) === parsed.requestId && Array.isArray(parsed.repoIds) && parsed.repoIds.length && parsed.repoIds.every(id => typeof id === "string" && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$/.test(id)) && Number.isFinite(parsed.createdAt)
          && (parsed.intent === undefined || parsed.intent === "commit_and_push")) candidates.push(parsed);
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
    settings.naming = { preset: "version", fallbackTitle: "更新进度 {datetime}", subtitle: "", notes: "", includeSummary: true, autoBump: true, allowActiveWork: true, ...(plain(settings.naming) ? settings.naming : {}) };
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
    state.expanded = false; state.configRepoId = null; state.versionBusy = false; state.versionEpoch = 0; state.catalog = new Map(); state.savedSources = new Map(); state.operatedRepoIds = new Set();
    state.uploadSummaries = new Map(); state.multiBindings = new Set();
    state.versionReads = new Map(); state.statusReadError = null;
    state.cacheIdentity = ""; state.serverVersionSources = new Map(); state.snapshotMode = false; state.versionRefresh = null; state.versionPollTimer = 0;
    state.commitAgeTimer = 0; state.ageSuspended = false; state.activityCheck = null;
    const controls = [], resultRetries = [], syncDrafts = new Map(), inputPending = new Set();
    const compactRefs = new Map(), configCards = new Map(), configSections = new Map(), planBoxes = new Map();
    const managed = item => { item.setAttribute("data-console-management", ""); return item; };
    const bar = managed(node("div", "repository-publish-bar"));
    const runButton = managed(node("button", "ghost-button repository-publish-primary")); runButton.type = "button";
    const checkButton = managed(node("button", "ghost-button repository-publish-check")); checkButton.type = "button";
    const checkRefresh = node("span", "repository-publish-refresh-indicator repository-publish-check-spinner"); checkRefresh.hidden = true; checkRefresh.setAttribute("aria-hidden", "true");
    const toggleButton = managed(node("button", "ghost-button repository-publish-toggle")); toggleButton.type = "button";
    const configButton = managed(node("button", "ghost-button repository-publish-config")); configButton.type = "button";
    const shortStatus = node("span", "repository-publish-status"); shortStatus.setAttribute("role", "status"); shortStatus.setAttribute("aria-live", "polite");
    bar.append(runButton, checkButton, checkRefresh, configButton, toggleButton, shortStatus);
    const expanded = managed(node("div", "repository-publish-expanded")), compactRows = node("div", "repository-publish-compact-rows");
    expanded.id = "consoleRepositoryPublish-repositories-" + (uniqueId() || "list"); expanded.hidden = true; expanded.append(compactRows);
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
    const diagnosisBox = node("div", "repository-publish-diagnosis"), diagnosisHeading = node("strong", "repository-publish-diagnosis-heading"), diagnosisSummary = node("p", "repository-publish-diagnosis-summary"), diagnosisNext = node("p", "repository-publish-diagnosis-next"), diagnosisMeta = node("p", "repository-publish-diagnosis-meta"), diagnosisBlockers = node("div", "repository-publish-diagnosis-blockers"), diagnosisActivity = node("div", "repository-publish-current-activity"), diagnosisActions = node("div", "repository-publish-diagnosis-actions"), diagnosisLocate = managed(node("button", "ghost-button repository-publish-diagnosis-locate")), diagnosisRecheck = managed(node("button", "ghost-button repository-publish-diagnosis-recheck"));
    const diagnosisPlain = node("div", "repository-publish-diagnosis-current"), diagnosisBody = node("div", "repository-publish-diagnosis-body"), diagnosisHistory = node("details", "repository-publish-last-attempt"), diagnosisHistoryTitle = node("summary"), diagnosisHistoryHint = node("p", "repository-publish-hint");
    const diagnosisGitMeta = node("p", "repository-publish-git-metadata"), diagnosisProgress = node("p", "repository-publish-operation-metric"); diagnosisGitMeta.hidden = diagnosisProgress.hidden = true;
    diagnosisHistory.append(diagnosisHistoryTitle, diagnosisHistoryHint); diagnosisBody.append(diagnosisHeading, diagnosisSummary, diagnosisGitMeta, diagnosisProgress, diagnosisBlockers, diagnosisNext, diagnosisMeta); diagnosisPlain.append(diagnosisBody);
    diagnosisLocate.type = diagnosisRecheck.type = "button"; diagnosisBox.hidden = true; diagnosisBlockers.hidden = diagnosisActivity.hidden = diagnosisHistory.hidden = true; diagnosisSummary.id = "repository-publish-reason-" + (uniqueId() || "current"); diagnosisActions.append(diagnosisLocate, diagnosisRecheck); diagnosisBox.append(diagnosisActivity, diagnosisPlain, diagnosisActions, diagnosisHistory);
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
      if (terminalStatuses.has(state.operation?.status) && !state.pendingId && !state.postBusy) parts.unshift(text("lastOperation"));
      return parts.join(" · ");
    }
    function statusText() {
      if (state.configConflict) return text("configConflict");
      if (state.error) { const info = operationProgress(); return info ? operationText(info) + " · " + text(state.error) : text(state.error); }
      if (state.previewBusy) return text("previewing");
      if (inputPending.size) return text(state.invalid.size ? "invalidConfig" : "editing");
      if (state.saveBusy || state.dirty) return text(state.invalid.size ? "invalidConfig" : "saving");
      if (state.pendingId && !activeStatuses.has(state.operation?.status)) return text("unknown");
      if (state.notice === "nothingToUpload") return text("nothingToUpload");
      const info = operationProgress(); if (info) return operationText(info) + (state.notice === "pendingUnavailable" ? " · " + text("pendingUnavailable") : "");
      if (blocked()) return text("progressWaiting");
      if (state.notice) return text(state.notice);
      const n = enabled().length; return n ? text("ready").replace("{n}", String(n)) : text("empty");
    }
    function render() {
      if (state.activityCheck && !activityCheckMatches(state.activityCheck)) cancelActivityCheck();
      bar.hidden = state.allowed !== true; if (!state.allowed && dialog.open) dialog.close();
      expanded.hidden = !state.allowed || !state.expanded;
      runButton.textContent = text("run"); runButton.title = text("commitPushHint"); runButton.setAttribute("aria-label", text("run") + " · " + text("commitPushHint")); configButton.textContent = text("configAll"); heading.textContent = state.configRepoId ? repoName(state.settings?.repositories.find(repo => repo.id === state.configRepoId)) + " · " + text("config") : text("configAll"); closeButton.textContent = text("close");
      checkButton.textContent = text("checkAll"); checkButton.setAttribute("aria-busy", String(state.versionBusy)); runButton.setAttribute("aria-busy", String(state.versionBusy));
      const toggleLabel = text(state.expanded ? "collapse" : "expand"); toggleButton.disabled = !state.allowed; toggleButton.setAttribute("aria-label", toggleLabel); toggleButton.title = toggleLabel; toggleButton.setAttribute("aria-expanded", String(state.expanded)); toggleButton.setAttribute("aria-controls", expanded.id);
      configButton.setAttribute("aria-controls", dialog.id); configButton.setAttribute("aria-expanded", String(dialog.open));
      shortStatus.textContent = statusText(); detailStatus.textContent = statusText(); shortStatus.dataset.state = state.error ? "error" : blocked() ? "working" : "ready";
      runButton.disabled = !state.allowed || !state.settings || !enabled().length || blocked() || state.versionBusy || state.readBusy || state.saveBusy || state.dirty || state.invalid.size > 0;
      checkButton.disabled = runButton.disabled;
      configButton.disabled = !state.allowed; addButton.disabled = blocked() || state.versionBusy || state.saveBusy || inputPending.size > 0; refreshButton.disabled = state.versionBusy || state.readBusy || state.postBusy || state.saveBusy;
      previewButton.disabled = blocked() || state.versionBusy || state.previewBusy || state.saveBusy || state.dirty || !enabled().length;
      resumeButton.textContent = text("resumeOriginal"); resumeButton.hidden = !(state.notFound && state.pendingRequest?.requestId === state.pendingId);
      resumeButton.disabled = state.postBusy || state.serverBusy || state.readBusy || state.saveBusy || state.previewBusy || state.dirty || !state.allowed;
      for (const input of controls) input.disabled = blocked() || state.versionBusy;
      for (const retry of resultRetries) retry.disabled = blocked() || state.versionBusy || state.readBusy || state.saveBusy || state.dirty;
      for (const label of state.localized) label.item[label.property] = text(label.key);
      refreshButton.textContent = text(state.configConflict ? "reloadConfig" : "refresh");
      if (dialog.open) renderWarnings();
      renderConfigVisibility();
      if (!state.versionBusy) { renderCompactRows(); renderVersionPlans(); }
      else {
        for (const refs of compactRefs.values()) refs.push.disabled = true;
        for (const box of planBoxes.values()) for (const button of childrenOf(box)) if (button.tagName === "BUTTON") button.disabled = true;
        diagnosisRecheck.disabled = true;
      }
      renderCheckActivity();
      renderDiagnosis();
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
    function displayCatalogFor(repo) {
      const catalog = catalogFor(repo), reading = readFor(repo);
      return catalog && !currentCatalog(catalog, reading) ? { ...catalog, displayOnly: true } : catalog;
    }
    function acceptVersionSnapshots(value, sources = sourceIdentities(state.settings), initial = false, target = state, passive = false) {
      if (!plain(value) || !/^[a-f0-9]{64}$/.test(value.cacheIdentity || "") || !Array.isArray(value.versionSources) || !Array.isArray(value.versionSnapshots) || !plain(value.versionReadStates)) return false;
      const receivedSources = value.versionSources.filter(item => plain(item) && typeof item.repoId === "string" && typeof item.sourceIdentity === "string" && item.sourceIdentity.length <= 200).map(item => [item.repoId, item.sourceIdentity]);
      if (initial) {
        if (target.cacheIdentity && target.cacheIdentity !== value.cacheIdentity) { target.catalog.clear(); target.versionReads.clear(); target.multiBindings.clear(); }
        target.cacheIdentity = value.cacheIdentity; target.snapshotMode = true;
        target.serverVersionSources = new Map([...(target.ids ? target.serverVersionSources : []), ...receivedSources]);
      } else if (target.cacheIdentity !== value.cacheIdentity) return false;
      else if (target.ids) for (const [id, identity] of receivedSources) if (target.ids.includes(id) && !target.serverVersionSources.has(id)) target.serverVersionSources.set(id, identity);
      for (const repo of target.settings.repositories) {
        if (target.ids && !target.ids.includes(repo.id)) continue;
        if (sources.get(repo.id) !== sourceIdentity(repo, target.settings.naming)) continue;
        const expected = target.serverVersionSources.get(repo.id), receivedSource = value.versionSources.find(item => item?.repoId === repo.id);
        if (!expected || receivedSource?.sourceIdentity !== expected) continue;
        const values = value.versionSnapshots.filter(item => plain(item) && item.repoId === repo.id && item.sourceIdentity === expected && Array.isArray(item.components));
        const read = value.versionReadStates[repo.id], previous = target.catalog.get(repo.id), previousRead = target.versionReads.get(repo.id);
        // Saved ready/queued snapshots cannot erase a failed explicit check for this source.
        if (passive && previousRead?.sourceIdentity === sources.get(repo.id) && previousRead.manualError && previousRead.error) continue;
        // A passive status read cannot grant fresh authority or replace a newer explicit check.
        if (passive && previous?.sourceIdentity === sources.get(repo.id) && currentCatalog(previous, previousRead)
          && plain(read) && Date.parse(read.checkedAt) <= Date.parse(previousRead.checkedAt)) continue;
        if (values.length === 1) {
          const item = values[0], components = clone(item.components.filter(plain));
          target.catalog.set(repo.id, { ...clone(item), sourceIdentity: sources.get(repo.id), components, displayOnly: passive || item.displayOnly === true, cached: passive || item.displayOnly === true });
          if (components.length > 1) target.multiBindings.add(displayIdentity(repo)); else if (components.length === 1 || item.versionState === "missing") target.multiBindings.delete(displayIdentity(repo));
        }
        if (plain(read) && read.sourceIdentity === expected) {
          const error = read.state === "error" ? Object.assign(new Error("snapshot_read_failed"), { safeMessage: safeDiagnosticText(read.message), kind: read.errorKind === "timeout" ? "timeout" : "network", diagnostic: normalizedDiagnostic(read.diagnostic) }) : null;
          target.versionReads.set(repo.id, { sourceIdentity: sources.get(repo.id), busy: !passive && ["queued", "reading"].includes(read.state), error, manualError: !passive && Boolean(error), checkedAt: clean(read.checkedAt, 100), startedAt: clean(read.startedAt, 100) });
        }
      }
      return true;
    }
    const diagnosticCategories = new Set(["connection", "sync", "activity", "repository", "versions", "naming", "verification", "authentication", "permissions", "rules", "lfs", "network", "remote", "unknown"]);
    const activityCodes = new Set(["activity_active", "activity_scope_unknown", "activity_unconfirmed"]);
    const activityPolicies = new Set(["allow_saved_snapshot", "strict"]);
    const gitOperations = new Set(["ls-remote", "fetch", "push", "commit", "status", "config", "rev-parse", "symbolic-ref", "add", "read-tree", "update-index", "write-tree", "diff", "diff-tree", "diff-index", "merge-base", "rev-list", "log", "ls-files", "ls-tree", "cat-file", "show", "show-ref", "update-ref", "check-ref-format", "stripspace"]);
    const gitErrors = new Set(["unknown", "unsupported_option", "timeout", "resolve_host", "connect_failed", "connection_reset", "tls_failed", "server_unavailable", "transport_failed"]);
    const diagnosticLabels = new Map([
      ...[["activity_active", "waitingCodex"], ["activity_scope_unknown", "activityScope"], ["activity_unconfirmed", "activityCheck"]].map(([code, key]) => [code, ["activity", key]]),
      ...[["repo_missing", "folderCheck"], ["repo_root", "folderCheck"], ["branch_mismatch", "branchCheck"], ["remote_config", "remoteCheck"], ["remote_ownership", "remoteCheck"], ["duplicate_repository", "folderCheck"]].map(([code, key]) => [code, ["connection", key]]),
      ...[["sync_config", "syncCheck"], ["sync_missing", "syncMissing"], ["sync_writing", "syncWriting"], ["sync_changed", "syncCheck"]].map(([code, key]) => [code, ["sync", key]]),
      ...[["git_history_operation", "historyOperation"], ["git_lock", "gitLocked"], ["staged_selection", "stagedSelection"], ["merge_conflict", "mergeConflict"], ["worktree_changed", "workChanged"], ["git_missing", "gitCheck"], ["git_unavailable", "gitCheck"]].map(([code, key]) => [code, ["repository", key]]),
      ["version_authority", ["versions", "versionCheck"]], ["version_plan_stale", ["versions", "versionPlanCheck"]], ["version_plan_blocked", ["versions", "versionPlanCheck"]],
      ["git_authentication", ["authentication", "authCheck"]], ["git_permissions", ["permissions", "permissionCheck"]], ["git_rules", ["rules", "rulesCheck"]], ["git_lfs", ["lfs", "lfsCheck"]], ["git_large_history", ["lfs", "largeHistory"]], ["git_timeout", ["network", "networkCheck"]], ["remote_ahead", ["remote", "remoteHistory"]], ["remote_changed", ["remote", "remoteCheck"]],
      ["git_failed", ["repository", "gitCheck"]], ["git_remote_failed", ["remote", "remoteCheck"]], ["git_network", ["network", "networkCheck"]], ["git_unsupported", ["repository", "gitCheck"]],
      ...["destination_changed", "receipt_unverified", "operation_interrupted"].map(code => [code, ["verification", "verifyRequired"]])
    ]);
    const diagnosticTargets = new Map([
      ...[["repo_missing", "path"], ["repo_root", "path"], ["branch_mismatch", "branch"], ["remote_config", "remote"], ["remote_ownership", "repositoryUrl"], ["duplicate_repository", "path"]].map(([code, field]) => [code, ["connection", new Set([field])]]),
      ...["sync_config", "sync_missing", "sync_writing", "sync_changed"].map(code => [code, ["sync", new Set(["sync"])]]),
      ...["version_authority", "version_plan_stale", "version_plan_blocked"].map(code => [code, ["versions", new Set(["versionPath"])]]),
      ["version_fallback", ["naming", new Set(["fallbackTitle"])]]
    ]);
    function safeDiagnosticText(value, length = 1200) { return clean(value, length).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, ""); }
    function normalizedBlockers(value) {
      if (!Array.isArray(value)) return [];
      const localPath = value => typeof value === "string" && /^(?:[A-Za-z]:[\\/]|\/(?!\/))/.test(value) ? safeDiagnosticText(value, 1000) : "";
      return value.slice(0, 20).filter(plain).map(item => {
        const title = safeDiagnosticText(item.title, 160).trim(), agentPath = typeof item.agentPath === "string" && /^\/[A-Za-z0-9_./-]{1,199}$/.test(item.agentPath) ? item.agentPath : "", threadId = idOK(item.threadId) ? item.threadId : "";
        return { title, agentPath, threadId, cwd: localPath(item.cwd), roots: Array.isArray(item.roots) ? item.roots.slice(0, 12).map(localPath).filter(Boolean) : [],
          state: /^[A-Za-z][A-Za-z0-9_-]{0,39}$/.test(item.state || "") ? item.state : "", mode: /^[A-Za-z][A-Za-z0-9_-]{0,39}$/.test(item.mode || "") ? item.mode : "", reason: safeDiagnosticText(item.reason, 600) };
      }).filter(item => item.title || item.agentPath || item.threadId);
    }
    function normalizedDiagnostic(value) {
      if (!plain(value) || !/^[a-z][a-z0-9_]{0,79}$/.test(value.code || "") || !["info", "warning", "error"].includes(value.severity) || !safeDiagnosticText(value.summary)) return null;
      const category = diagnosticCategories.has(value.category) ? value.category : "unknown", allowed = diagnosticTargets.get(value.code);
      let target = null;
      if (allowed && category === allowed[0] && plain(value.target) && value.target.section === allowed[0] && allowed[1].has(value.target.field)
        && (value.target.sourceId === undefined && allowed[0] !== "versions" || typeof value.target.sourceId === "string" && /^[A-Za-z0-9_-]{1,120}$/.test(value.target.sourceId))) {
        target = { section: allowed[0], field: value.target.field, ...(value.target.sourceId ? { sourceId: value.target.sourceId } : {}) };
      }
      const activity = category === "activity" && activityCodes.has(value.code);
      const operationKind = gitOperations.has(value.operationKind) ? value.operationKind : "", errorKind = gitErrors.has(value.errorKind) ? value.errorKind : "";
      const exitCode = Number.isSafeInteger(value.exitCode) && value.exitCode >= -2147483648 && value.exitCode <= 4294967295 ? value.exitCode : null;
      return { code: value.code, category, severity: value.severity, summary: safeDiagnosticText(value.summary), nextStep: safeDiagnosticText(value.nextStep), target: activity ? null : target, blockers: activity ? normalizedBlockers(value.blockers) : [], operationKind, errorKind, exitCode };
    }
    function diagnosticStatus(value, fallback = "uploadPaused") {
      if (value?.errorKind === "tls_failed") return [text("tlsFailed"), ["ls-remote", "fetch"].includes(value.operationKind) ? text("phaseRemote") : value.operationKind === "push" ? text("phasePush") : ""].filter(Boolean).join(" · ");
      const label = value && diagnosticLabels.get(value.code);
      return text(label && label[0] === value.category ? label[1] : fallback);
    }
    function compactReason(value) {
      const actors = (value?.blockers || []).map(item => item.title || item.agentPath || item.threadId).filter(Boolean).join(", ");
      return [actors, safeDiagnosticText(value?.summary).replace(/\s+/g, " ")].filter(Boolean).join(" · ");
    }
    function stoppedResult(repo) {
      const result = state.operation?.results.find(item => item.repoId === repo.id);
      return uploadBindingMatches(result?.uploadSummary, repo) && (failedRepoStatuses.has(result.status) || reviewRepoStatuses.has(result.status)) ? result : null;
    }
    function activityCheckMatches(check) {
      const repo = state.settings?.repositories.find(item => item.id === check?.repoId);
      return Boolean(repo && !state.destroyed && state.allowed && !state.dirty && dialog.open && !workspacePanel.hidden && state.configRepoId === repo.id && check.epoch === state.versionEpoch && check.edit === state.edit && check.settingsSha === state.settingsSha && check.cacheIdentity === state.cacheIdentity && check.localIdentity === sourceIdentity(repo) && check.serverIdentity === state.serverVersionSources.get(repo.id));
    }
    function cancelActivityCheck() {
      const check = state.activityCheck; state.activityCheck = null; check?.controller.abort(); diagnosisActivity.hidden = true; diagnosisActivity.replaceChildren();
    }
    function currentActivityFor(repo) {
      const check = state.activityCheck;
      return check?.repoId === repo.id && activityCheckMatches(check) ? check : null;
    }
    function activityReceipt(value) {
      if (!plain(value) || typeof value.activityClear !== "boolean") return null;
      const diagnostic = value?.diagnostic === null ? null : normalizedDiagnostic(value?.diagnostic);
      const isActivity = item => item?.category === "activity" && activityCodes.has(item.code);
      const hasPolicy = ["publicationAllowed", "activityPolicy", "activityNotice"].some(key => Object.prototype.hasOwnProperty.call(value || {}, key));
      if (!hasPolicy) {
        if (value.activityClear ? value.diagnostic !== null : !isActivity(diagnostic)) return null;
        return { activityClear: value.activityClear, publicationAllowed: value.activityClear, activityPolicy: "strict", activityNotice: null, diagnostic };
      }
      const notice = value.activityNotice === null ? null : normalizedDiagnostic(value.activityNotice);
      if (!activityPolicies.has(value.activityPolicy) || typeof value.publicationAllowed !== "boolean" || value.diagnostic !== null && !diagnostic || value.activityNotice !== null && !isActivity(notice)) return null;
      if (value.activityClear) {
        if (!value.publicationAllowed || value.diagnostic !== null || value.activityNotice !== null) return null;
      } else if (value.publicationAllowed) {
        if (value.activityPolicy !== "allow_saved_snapshot" || value.diagnostic !== null || !isActivity(notice)) return null;
      } else if (!isActivity(diagnostic) && !(diagnostic?.category === "repository" && diagnostic.code === "git_lock")) return null;
      return { activityClear: value.activityClear, publicationAllowed: value.publicationAllowed, activityPolicy: value.activityPolicy, activityNotice: notice, diagnostic };
    }
    function currentActivityText(current) {
      return current?.publicationAllowed && !current.activityClear ? text("activeAllowed") : current?.activityClear ? text("activityCleared") : compactReason(current?.diagnostic);
    }
    async function readCurrentActivity(repoId, explicit = false) {
      const repo = state.settings?.repositories.find(item => item.id === repoId), serverIdentity = state.serverVersionSources.get(repoId);
      if (!repo || !dialog.open || state.configRepoId !== repoId || state.destroyed || !state.allowed || workspacePanel.hidden || state.dirty || state.saveBusy || !/^[a-f0-9]{64}$/.test(serverIdentity || "") || !explicit && !stoppedResult(repo)) return;
      if (currentActivityFor(repo)?.busy) return;
      cancelActivityCheck();
      const check = { repoId, serverIdentity, localIdentity: sourceIdentity(repo), settingsSha: state.settingsSha, cacheIdentity: state.cacheIdentity, edit: state.edit, epoch: state.versionEpoch, controller: new AbortController(), busy: true, value: null, error: false };
      state.activityCheck = check; render();
      try {
        const value = await request("/activity?repoId=" + encodeURIComponent(repoId), undefined, check.controller.signal);
        if (state.activityCheck !== check || !activityCheckMatches(check)) return;
        const receipt = activityReceipt(value);
        if (value?.repoId !== repoId || value.sourceIdentity !== serverIdentity || typeof value.activityClear !== "boolean" || typeof value.checkedAt !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value.checkedAt) || !Number.isFinite(Date.parse(value.checkedAt)) || !receipt) throw new Error("invalid_activity_receipt");
        check.value = { ...receipt, checkedAt: safeDiagnosticText(value.checkedAt, 100) };
      } catch { if (state.activityCheck === check && activityCheckMatches(check)) check.error = true; }
      finally { if (state.activityCheck === check) { check.busy = false; render(); } }
    }
    function appendActivityBlockers(parent, blockers) {
      for (const blocker of blockers) {
        const item = node("div", "repository-publish-diagnosis-work"), title = node("strong", "", blocker.title || blocker.agentPath || blocker.threadId);
        item.append(title);
        const paths = [...new Set([blocker.cwd, ...blocker.roots].filter(Boolean))];
        for (const path of paths) item.append(node("p", "repository-publish-diagnosis-work-path", path));
        const metadata = [blocker.agentPath, blocker.threadId, blocker.state, blocker.mode].filter(Boolean).join(" · ");
        if (metadata) item.append(node("p", "repository-publish-diagnosis-meta", metadata));
        if (blocker.reason) item.append(node("p", "repository-publish-diagnosis-work-reason", blocker.reason));
        parent.append(item);
      }
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
      // A refreshing display snapshot must not hide the reason an actual upload stopped.
      if (result && (failedRepoStatuses.has(result.status) || reviewRepoStatuses.has(result.status) || result.uploadSummary?.state === "pending")) return wrap(normalizedDiagnostic(result.diagnostic) || { summary: safeDiagnosticText(result.message) || text(result.uploadSummary?.state === "pending" ? "uploadPending" : "uploadPaused"), nextStep: text("inspectOriginal"), severity: "warning", target: null }, "diagnosisOperation");
      if (reading?.busy) return wrap({ summary: text(catalog ? "updatingLocal" : "readingLocal"), nextStep: text("readingHint"), severity: "info", target: null }, "diagnosisRead", catalog ? text("knownBefore") : "");
      if (reading?.error) return wrap(readErrorDiagnostic(reading.error), "diagnosisRead", catalog ? text("knownBefore") : "");
      if (state.statusReadError?.sources.get(repo.id) === sourceIdentity(repo)) return wrap(readErrorDiagnostic(state.statusReadError.error), "diagnosisRead");
      if (result && activeStatuses.has(result.status)) return wrap(normalizedDiagnostic(result.diagnostic) || { summary: [phaseText(result.phase), safeDiagnosticText(result.message)].filter(Boolean).join(" · "), nextStep: text("waitOperation"), severity: "info", target: null }, "diagnosisOperation");
      const currentDiagnostic = normalizedDiagnostic(catalog?.diagnostic);
      if (currentDiagnostic && currentDiagnostic.severity !== "info") return wrap(currentDiagnostic, "diagnosisRead");
      if (currentDiagnostic) return wrap(currentDiagnostic, "diagnosisRead");
      if (catalog) return wrap({ summary: safeDiagnosticText(catalog.message) || safeDiagnosticText(catalog.syncState === "unknown" ? catalog.syncReason : "") || safeDiagnosticText(catalog.components?.find(item => !item.currentVersion && item.reason)?.reason) || safeDiagnosticText(catalog.changesReason) || changeHint(catalog), nextStep: text("notReadNext"), severity: "info", target: null }, "diagnosisRead", reading?.checkedAt ? text("checkedAt") + " · " + reading.checkedAt : "");
      if (original && !result) return wrap({ summary: text("historicalHint"), nextStep: text("inspectOriginal"), severity: "info", target: null }, "diagnosisHistory");
      return wrap({ summary: text(blocked() ? "publishingRead" : "notRead"), nextStep: text(state.dirty ? "configDraftRead" : blocked() ? "waitOperation" : "notReadNext"), severity: "info", target: null }, "diagnosisRead");
    }
    function renderDiagnosis() {
      const repo = state.settings?.repositories.find(item => item.id === state.configRepoId);
      diagnosisBox.hidden = !dialog.open || !repo; if (!repo || !dialog.open) return;
      const value = diagnosisFor(repo); state.diagnosisPresentation = value;
      const previous = stoppedResult(repo), currentActivity = currentActivityFor(repo); diagnosisActivity.replaceChildren(); diagnosisActivity.hidden = !currentActivity && !previous;
      if (currentActivity || previous) {
        diagnosisActivity.append(node("strong", "", text("currentActivity")));
        const current = currentActivity?.value, currentDiagnostic = current?.diagnostic || current?.activityNotice;
        diagnosisActivity.dataset.state = currentActivity?.busy ? "checking" : currentActivity?.error || !current ? "unknown" : current.publicationAllowed ? "allowed" : "blocked";
        diagnosisActivity.append(node("p", "repository-publish-current-activity-summary", currentActivity?.busy ? text("checkingActivity") : currentActivity?.error ? text("activityFailed") : current ? currentActivityText(current) : text("currentUnknown")));
        if (currentDiagnostic) {
          appendActivityBlockers(diagnosisActivity, currentDiagnostic.blockers);
          if (currentDiagnostic.nextStep && !current.publicationAllowed) diagnosisActivity.append(node("p", "repository-publish-diagnosis-next", text("diagnosisNext") + " · " + currentDiagnostic.nextStep));
        }
        if (current) diagnosisActivity.append(node("p", "repository-publish-diagnosis-meta", text("checkedAt") + " · " + current.checkedAt), node("p", "repository-publish-diagnosis-meta", text("activityOnly")));
      }
      const historyKey = previous ? JSON.stringify([repo.id, state.operation?.requestId, previous.status, previous.message]) : "";
      if (state.diagnosisHistoryKey !== historyKey) diagnosisHistory.open = false;
      state.diagnosisHistoryKey = historyKey; diagnosisHistory.hidden = !previous; diagnosisPlain.hidden = Boolean(previous);
      (previous ? diagnosisHistory : diagnosisPlain).append(diagnosisBody);
      diagnosisHistoryTitle.textContent = text("lastAttempt") + (previous?.phase ? " · " + phaseText(previous.phase) : ""); diagnosisHistoryHint.textContent = text("previousAttemptHint");
      diagnosisHeading.textContent = text(previous ? "lastAttempt" : value.origin === "diagnosisOperation" && value.severity !== "info" ? "whyPaused" : "diagnosis"); diagnosisSummary.textContent = value.summary; diagnosisNext.textContent = value.nextStep ? text("diagnosisNext") + " · " + value.nextStep : "";
      diagnosisGitMeta.textContent = [value.operationKind ? "Git " + value.operationKind : "", Number.isSafeInteger(value.exitCode) ? text("gitExit").replace("{n}", String(value.exitCode)) : "", value.errorKind ? text("gitFailureKind") + " · " + value.errorKind : ""].filter(Boolean).join(" · "); diagnosisGitMeta.hidden = !diagnosisGitMeta.textContent;
      const operationResult = state.operation?.results.find(item => item.repoId === repo.id);
      const progress = uploadBindingMatches(operationResult?.uploadSummary, repo) ? repositoryProgressInfo(operationResult) : null;
      diagnosisProgress.textContent = progress ? [progress.phase, progress.metrics, progress.measured ? text("phasePercent") : ""].filter(Boolean).join(" · ") : "";
      diagnosisProgress.hidden = !diagnosisProgress.textContent;
      diagnosisBlockers.replaceChildren();
      const activity = value.category === "activity" && activityCodes.has(value.code), blockers = value.blockers || [];
      diagnosisBlockers.hidden = !activity;
      if (activity) {
        diagnosisBlockers.append(node("p", "repository-publish-diagnosis-work-hint", text("notConfigIssue")));
        if (blockers.length) {
          diagnosisBlockers.append(node("strong", "repository-publish-diagnosis-work-heading", text("blockingWork")));
          appendActivityBlockers(diagnosisBlockers, blockers);
        } else diagnosisBlockers.append(node("p", "repository-publish-diagnosis-work-hint", text("activityUnknown")));
      }
      diagnosisNext.hidden = !value.nextStep; diagnosisMeta.textContent = [text(value.origin), value.metadata].filter(Boolean).join(" · "); diagnosisBox.dataset.severity = value.severity;
      diagnosisLocate.textContent = text("locateSetting"); diagnosisLocate.hidden = !value.target; diagnosisLocate.disabled = !state.allowed;
      diagnosisRecheck.textContent = text("checkAll"); diagnosisRecheck.disabled = blocked() || state.versionBusy || state.readBusy || state.saveBusy || state.dirty || state.invalid.size > 0 || currentActivity?.busy === true;
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
    diagnosisRecheck.addEventListener("click", () => { if (!diagnosisRecheck.disabled) void readVersions(); });
    function repoChangeState(catalog) {
      if (!catalog || typeof catalog.hasChanges !== "boolean") return "unknown";
      const expected = catalog.hasChanges ? "changed" : "unchanged";
      if (expected === "unchanged" && (catalog.pendingRecovery !== false || catalog.worktreeChanged !== false
        || catalog.outgoingCommits !== 0 || catalog.syncChanged !== false || catalog.syncState === "unknown"
        || !/^(?:[a-f0-9]{40}|[a-f0-9]{64})$/.test(catalog.headSha || "") || catalog.headSha !== catalog.outgoingBaselineSha)) return "unknown";
      return catalog.changeState === expected ? expected : "unknown";
    }
    function currentCatalog(catalog, reading) {
      const checked = Date.parse(reading?.checkedAt || catalog?.checkedAt || "");
      return Boolean(catalog && reading && !reading.busy && !reading.error && catalog.readState !== "error"
        && catalog.displayOnly !== true && catalog.cached !== true && catalog.stale !== true
        && Number.isFinite(checked) && Date.now() >= checked && Date.now() - checked <= 60000);
    }
    function confirmedClean(repo) {
      const catalog = catalogFor(repo);
      return currentCatalog(catalog, readFor(repo)) && repoChangeState(catalog) === "unchanged"
        && catalog.worktreeChanged === false && catalog.outgoingCommits === 0 && catalog.syncChanged === false
        && (!repo.syncFiles.length || catalog.syncState === "unchanged")
        && !["warning", "error"].includes(catalog.diagnostic?.severity);
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
      if (catalog?.displayOnly === true || catalog?.cached === true
        || !plain(transition) || !["planned", "working", "auto"].includes(transition.kind)
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
        ? clean(transition.toVersion, 80)
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
    function repositorySemver(value, historical = false) {
      const match = typeof value === "string" && value.length <= 100 && value.match(/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/);
      return Boolean(match && !match[4]?.split(".").some(part => /^\d+$/.test(part) && part.length > 1 && part[0] === "0")
        && (historical || match[1] !== "0" && !(match[1] === "1" && match[2] === "0" && match[3] === "0" && match[4])));
    }
    function repositoryVersionText(catalog) {
      const version = catalog?.repositoryVersion;
      if (!plain(version)) return null;
      if (!["current", "initial"].includes(version.state) || !repositorySemver(version.currentVersion)) return text("versionFailed");
      const transition = version.transition;
      if (version.state === "initial" && catalog.displayOnly !== true && catalog.cached !== true && plain(transition)
        && transition.kind === "initial" && repositorySemver(transition.fromVersion, true)
        && transition.toVersion === version.currentVersion && transition.fromVersion !== transition.toVersion) {
        return version.currentVersion;
      }
      if (version.state === "current" && catalog.displayOnly !== true && catalog.cached !== true && plain(transition)
        && ["working", "planned", "auto"].includes(transition.kind)
        && repositorySemver(transition.fromVersion) && repositorySemver(transition.toVersion)
        && transition.fromVersion !== transition.toVersion
        && (transition.kind === "working" ? transition.toVersion === version.currentVersion : transition.fromVersion === version.currentVersion)) {
        return transition.toVersion;
      }
      return version.currentVersion;
    }
    function hasMultipleVersions(repo, catalog) { return (catalog?.components || []).length > 1 || (repo.versionSources || []).length > 1 || state.multiBindings.has(displayIdentity(repo)); }
    function componentChangeState(component, catalog) {
      if (componentChanged(component)) return "changed";
      return component.worktreeChanged === false || repoChangeState(catalog) === "unchanged" ? "unchanged" : "unknown";
    }
    function versionSummary(repo) {
      const catalog = displayCatalogFor(repo), components = catalog?.components || [];
      const repositoryVersion = repositoryVersionText(catalog);
      if (repositoryVersion !== null) return repositoryVersion;
      const unread = readFor(repo)?.error || catalog?.readState === "error" || catalog?.versionState === "unknown"
        || catalog?.message && catalog.versionState !== "missing";
      if (hasMultipleVersions(repo, catalog) || !components.length) return text(unread ? "versionFailed" : "versionPending");
      return repositorySemver(components[0].currentVersion) ? componentVersionText(components[0], components.length, catalog) : text(unread ? "versionFailed" : "versionPending");
    }
    function renderVersionPicker(refs, repo, catalog) {
      const components = catalog?.components || [], multiple = hasMultipleVersions(repo, catalog);
      if (workspacePanel.hidden || !state.expanded || !state.allowed || readFor(repo)?.busy) refs.picker.open = false;
      refs.picker.hidden = !multiple;
      if (!multiple) { refs.picker.open = false; return; }
      refs.summary.setAttribute("aria-label", [text("displayVersion"), repoName(repo)].join(" · ")); refs.summary.title = text("displayVersion");
      const uploaded = uploadSummary(repo, catalog);
      const reading = readFor(repo), signature = JSON.stringify([language(), displayIdentity(repo), components, state.settings.naming.autoBump, uploaded, Boolean(reading?.busy), Boolean(reading?.error), Boolean(catalog?.displayOnly), Boolean(catalog?.cached)]);
      if (signature === refs.menuSignature) return;
      refs.menuSignature = signature; refs.picker.open = false; refs.menu.replaceChildren();
      refs.menu.append(node("h4", "repository-publish-version-group", text("pluginDetails")));
      if (catalog && (reading?.busy || reading?.error)) refs.menu.append(node("p", "repository-publish-version-note", text("knownBefore")));
      if (!components.length) refs.menu.append(node("p", "repository-publish-version-note", text("versionPending")));
      const changed = components.filter(componentChanged), others = components.filter(item => !componentChanged(item));
      for (const [key, items] of [["changedPlugins", changed], ["otherPlugins", others]]) {
        if (!items.length) continue;
        refs.menu.append(node("hr", "repository-publish-version-divider"), node("h4", "repository-publish-version-group", text(key)));
        for (const component of items) {
          const option = node("div", "repository-publish-version-option", componentVersionText(component, components.length, catalog));
          option.dataset.sourceId = clean(component.sourceId, 120); option.dataset.changeState = catalog?.displayOnly === true || catalog?.cached === true ? "unknown" : componentChangeState(component, catalog);
          option.title = clean(component.path, 200); refs.menu.append(option);
        }
      }
      refs.menu.append(node("p", "repository-publish-version-note", text("uploadHint")));
      if (uploaded?.state !== "recorded") refs.menu.append(node("p", "repository-publish-version-note", clean(uploaded?.reason, 240) || text("uploadPending")));
    }
    function durationText(seconds) {
      const n = Math.floor(seconds); return n < 60 ? n + "s" : Math.floor(n / 60) + "m " + n % 60 + "s";
    }
    function lastCommitFor(repo) {
      const value = catalogFor(repo)?.lastCommit;
      if (!plain(value) || !/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(value.sha || "") || typeof value.committedAt !== "string"
        || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value.committedAt)) return null;
      const [year, month, day] = value.committedAt.slice(0, 10).split("-").map(Number), calendarYear = year < 100 ? year + 400 : year;
      if (month < 1 || month > 12 || day < 1 || day > new Date(Date.UTC(calendarYear, month, 0)).getUTCDate()) return null;
      const timestamp = Date.parse(value.committedAt); return Number.isFinite(timestamp) ? { ...value, timestamp } : null;
    }
    function stopCommitAgeTimer() { if (state.commitAgeTimer) window.clearTimeout(state.commitAgeTimer); state.commitAgeTimer = 0; }
    function renderCommitAges() {
      if (state.versionBusy) { stopCommitAgeTimer(); return; }
      let hasCommit = false;
      for (const repo of state.settings?.repositories || []) {
        const refs = compactRefs.get(repo.id); if (!refs) continue;
        const commit = lastCommitFor(repo), catalog = catalogFor(repo), reading = readFor(repo);
        let age = "—", hint = text("commitUnknown");
        if (commit) {
          hasCommit = true; const seconds = Math.floor((Date.now() - commit.timestamp) / 1000);
          age = seconds < 0 ? "?" : seconds < 60 ? seconds + "s" : seconds < 3600 ? Math.floor(seconds / 60) + "m" : seconds < 86400 ? Math.floor(seconds / 3600) + "h" : Math.floor(seconds / 86400) + "d";
          hint = [text("commitTime"), commit.committedAt, commit.sha, seconds < 0 ? text("commitClock") : "", catalog?.displayOnly === true || reading?.busy || reading?.error ? text("knownBefore") : ""].filter(Boolean).join(" · ");
        }
        refs.commitAge.textContent = text("commitAge").replace("{age}", age); refs.commitAge.title = hint;
        refs.commitAge.dataset.state = !commit ? "unknown" : commit.timestamp > Date.now() ? "future" : "known";
        refs.commitAge.dataset.freshness = catalog?.displayOnly === true || reading?.busy || reading?.error ? "last-known" : "current";
      }
      if (!hasCommit || state.destroyed || state.ageSuspended || workspacePanel.hidden || document.hidden === true || !state.allowed || !state.expanded) { stopCommitAgeTimer(); return; }
      if (!state.commitAgeTimer) state.commitAgeTimer = window.setTimeout(() => { state.commitAgeTimer = 0; renderCommitAges(); }, 1000);
    }
    function repositoryProgressComplete(result) {
      const value = result?.progress;
      return successfulRepoStatuses.has(result?.status) && value?.state === "complete" && value.scope === "repository" && value.source === "receipt" && value.percent === 100;
    }
    function currentRepositoryStatus(catalog, reading, diagnostic) {
      if (reading?.busy) return text(catalog ? "updatingLocal" : "readingLocal");
      if (reading?.error) return text("refreshFailed") + (catalog ? " · " + text("lastKnown") : "");
      if (catalog && !currentCatalog(catalog, reading)) return text("lastKnown");
      if (diagnostic && diagnostic.severity !== "info") return diagnosticStatus(diagnostic, "repoAttention");
      return catalog ? changeHint(catalog) : text(blocked() ? "publishingRead" : "notRead");
    }
    function repositoryProgressInfo(result) {
      if (!result) return null;
      const value = plain(result.progress) ? result.progress : null;
      const phase = phaseText(result.phase), current = Number(value?.current), total = Number(value?.total);
      // Only actual transfer measurements are percentages; details keep the original receipt scope.
      const measured = result.status === "working" && result.phase === "push" && value?.phase === "push" && value.state === "measured"
        && ["phase", "file"].includes(value.scope) && ["objects", "bytes"].includes(value.unit) && ["git", "git-lfs"].includes(value.source)
        && typeof value.current === "number" && typeof value.total === "number" && Number.isFinite(current) && Number.isFinite(total) && total > 0 && current >= 0 && current <= total;
      const active = result.status === "working";
      const awaitingReceipt = active && (!activeStatuses.has(state.operation?.status) || state.notice === "pendingUnavailable");
      const percent = awaitingReceipt ? null : measured ? Math.floor(100 * current / total) : repositoryProgressComplete(result) ? 100 : null;
      const step = measured ? value.source === "git" ? text("gitObjects") : value.scope === "file" && Number.isSafeInteger(value.fileIndex) && value.fileIndex > 0 && Number.isSafeInteger(value.fileTotal) && value.fileTotal >= value.fileIndex
        ? text("lfsFile").replace("{n}", String(value.fileIndex)).replace("{total}", value.estimatedFileTotal === true ? "~" + value.fileTotal : String(value.fileTotal)) : text("lfsObjects") : "";
      let seconds = Number(value?.elapsedSeconds);
      if (typeof value?.elapsedSeconds !== "number" || !Number.isFinite(seconds) || seconds < 0) seconds = typeof value?.startedAt === "string" && Number.isFinite(Date.parse(value.startedAt)) ? (Date.now() - Date.parse(value.startedAt)) / 1000 : null;
      const elapsed = seconds !== null && seconds >= 0 && seconds <= 7 * 86400 && active ? durationText(seconds) : "";
      return { phase, measured, metrics: [awaitingReceipt ? text("checkingReceipt") : percent !== null ? percent + "%" : "", step, elapsed].filter(Boolean).join(" · ") };
    }
    function renderRepositoryActivity(refs, repo, result, reading, catalog) {
      const live = result?.status === "working" && activeStatuses.has(state.operation?.status) && state.notice !== "pendingUnavailable";
      const refreshing = !result && reading?.busy;
      const busy = repo.enabled === true && !skippedRepoStatuses.has(result?.status) && (live || refreshing);
      refs.activity.hidden = refs.refresh.hidden = !busy;
      refs.refresh.title = refreshing ? text("refreshing") : phaseText(result?.phase);
      refs.refresh.setAttribute("aria-label", refs.refresh.title); refs.status.setAttribute("aria-busy", String(busy));
      refs.cell.dataset.freshness = reading?.busy || reading?.error || catalog?.cached === true ? "last-known" : "current";
    }
    function renderCompactRows() {
      const repos = state.settings?.repositories || [];
      for (const [id, refs] of compactRefs) if (!repos.some(repo => repo.id === id)) { refs.row.remove(); compactRefs.delete(id); }
      for (const repo of repos) {
        let refs = compactRefs.get(repo.id);
        if (!refs) {
          const row = node("div", "repository-publish-compact-row"), name = managed(node("button", "repository-publish-compact-name")), nameCell = node("div", "repository-publish-name-cell"), commitAge = node("span", "repository-publish-commit-age"), version = managed(node("button", "repository-publish-compact-version")), status = managed(node("button", "repository-publish-compact-status")), push = managed(node("button", "ghost-button repository-publish-row-push")); name.type = version.type = push.type = status.type = "button";
          const cell = node("div", "repository-publish-version-cell"), picker = managed(node("details", "repository-publish-version-picker")), summary = node("summary", "repository-publish-version-trigger"), arrow = node("span", "repository-publish-version-arrow", "⌄"), menu = node("div", "repository-publish-version-menu"), freshness = node("span", "repository-publish-version-freshness");
          const refresh = node("span", "repository-publish-refresh-indicator repository-publish-row-spinner"), statusCell = node("div", "repository-publish-status-cell"), statusLine = node("div", "repository-publish-status-line"), reason = node("span", "repository-publish-row-reason"), history = node("span", "repository-publish-row-history"), activity = node("span", "repository-publish-row-activity");
          const versionRefresh = node("span", "repository-publish-refresh-indicator repository-publish-version-spinner"); versionRefresh.hidden = true; versionRefresh.setAttribute("aria-hidden", "true");
          refresh.hidden = freshness.hidden = history.hidden = true; arrow.setAttribute("aria-hidden", "true"); summary.append(arrow); picker.append(summary, menu); cell.append(version, versionRefresh, picker, freshness);
          reason.id = "repository-publish-row-reason-" + (uniqueId() || repo.id); reason.hidden = true;
          activity.append(refresh); statusLine.append(status, activity); statusCell.append(statusLine, reason, history);
          nameCell.append(name, commitAge); row.dataset.repoId = repo.id; row.append(nameCell, cell, statusCell, push); compactRows.append(row); refs = { row, name, commitAge, version, versionRefresh, status, reason, history, push, cell, picker, summary, arrow, menu, refresh, freshness, activity, menuSignature: "" }; compactRefs.set(repo.id, refs);
          picker.addEventListener("toggle", () => { if (picker.open) for (const other of compactRefs.values()) if (other !== refs) other.picker.open = false; });
          picker.addEventListener("keydown", event => { if (event.key === "Escape" && picker.open) { event.preventDefault(); picker.open = false; summary.focus(); } });
          name.addEventListener("click", () => open(repo.id));
          version.addEventListener("click", () => { if (!version.disabled) void readVersions(repo.id); });
          push.addEventListener("click", () => void run([repo.id]));
          status.addEventListener("click", () => { if (!state.destroyed && state.allowed) { open(repo.id, { diagnose: true }); detail.open = false; renderResults(); dialog.scrollTop = 0; } });
        }
        const originalResult = state.operation?.results.find(item => item.repoId === repo.id);
        const result = uploadBindingMatches(originalResult?.uploadSummary, repo) ? originalResult : null;
        const catalog = catalogFor(repo), reading = readFor(repo), changeState = repoChangeState(catalog), diagnostic = normalizedDiagnostic(catalog?.diagnostic);
        const checkedActivity = currentActivityFor(repo)?.value;
        const activityIsNewer = !currentCatalog(catalog, reading) || Date.parse(checkedActivity?.checkedAt || "") > Date.parse(reading?.checkedAt || catalog?.checkedAt || "");
        const currentBlocker = !reading?.busy && activityIsNewer && normalizedDiagnostic(checkedActivity?.publicationAllowed === false ? checkedActivity.diagnostic : null);
        // A completed attempt is history; only an unresolved receipt remains an active warning.
        const unresolvedReceipt = result && (reviewRepoStatuses.has(result.status) || result.uploadSummary?.state === "pending")
          && !(currentCatalog(catalog, reading) && catalog.pendingRecovery === false);
        const lastCompletion = result && !activeStatuses.has(state.operation?.status) && !state.pendingId && !state.postBusy
          && !activeStatuses.has(result.status) && !unresolvedReceipt;
        const lastKnown = Boolean(catalog && !currentCatalog(catalog, reading));
        const displayChangeState = lastKnown || changeState === "unchanged" && !confirmedClean(repo) ? "unknown" : changeState;
        refs.name.textContent = repoName(repo); refs.name.disabled = !state.allowed; refs.name.title = text("config"); refs.name.setAttribute("aria-label", text("config") + " · " + repoName(repo)); refs.name.setAttribute("aria-haspopup", "dialog"); refs.name.setAttribute("aria-controls", dialog.id); refs.name.setAttribute("aria-expanded", String(dialog.open && state.configRepoId === repo.id)); refs.version.textContent = versionSummary(repo); refs.version.dataset.changeState = displayChangeState;
        refs.freshness.hidden = !lastKnown; refs.freshness.textContent = lastKnown ? text(reading?.error ? "refreshFailed" : "lastKnown") : "";
        refs.version.setAttribute("aria-label", [text("recheckRepository"), repoName(repo), refs.version.textContent].join(" · "));
        refs.version.title = [text("recheckRepository"), refs.version.textContent, lastKnown ? text("knownBefore") : "", catalog?.repositoryVersion?.state === "initial" ? text("initialRepositoryVersion") : "", hasMultipleVersions(repo, catalog) ? text("uploadHint") : changeHint(catalog), clean(catalog?.message, 300), clean(catalog?.changesReason, 300), clean(catalog?.remoteReference, 160)].filter(Boolean).join(" · ");
        renderVersionPicker(refs, repo, displayCatalogFor(repo));
        refs.status.textContent = repo.enabled !== true ? text("disabledRepo") : originalResult && !result ? text("historicalReceipt") : result && activeStatuses.has(result.status) ? phaseText(result.phase)
          : lastCompletion ? currentBlocker ? diagnosticStatus(currentBlocker, "repoAttention") : currentRepositoryStatus(catalog, reading, diagnostic)
            : result && successfulRepoStatuses.has(result.status) ? text("uploaded") + (result.uploadSummary?.state === "pending" ? " · " + text("uploadPending") : "")
            : result && skippedRepoStatuses.has(result.status) ? text("repoNoChanges")
              : result && reviewRepoStatuses.has(result.status) ? text("verifyRequired")
                : result && failedRepoStatuses.has(result.status) ? diagnosticStatus(normalizedDiagnostic(result.diagnostic), result.status === "deferred" ? "uploadPaused" : "failed")
                  : reading?.busy ? catalog ? changeHint(catalog) : text("readingLocal") : reading?.error ? catalog ? changeHint(catalog) + " · " + text("refreshFailed") : readErrorDiagnostic(reading.error).summary
                    : diagnostic && diagnostic.severity !== "info" ? diagnosticStatus(diagnostic, "repoAttention") : catalog ? changeHint(catalog) : text(blocked() ? "publishingRead" : "notRead");
        const diagnosis = lastCompletion ? reading?.error ? readErrorDiagnostic(reading.error)
          : currentBlocker || currentCatalog(catalog, reading) && diagnostic || { summary: "", nextStep: "", severity: "info" } : diagnosisFor(repo);
        const awaitingReceipt = activeStatuses.has(result?.status) && (!activeStatuses.has(state.operation?.status) || state.notice === "pendingUnavailable");
        const readWarning = !activeStatuses.has(result?.status) && !reading?.busy && (reading?.error || currentBlocker || currentCatalog(catalog, reading) && diagnostic && diagnostic.severity !== "info");
        const hasReason = repo.enabled === true && !(originalResult && !result) && (awaitingReceipt || !lastCompletion && result && (failedRepoStatuses.has(result.status) || reviewRepoStatuses.has(result.status) || result.uploadSummary?.state === "pending") || readWarning);
        const attemptDiagnostic = normalizedDiagnostic(result?.diagnostic);
        // Current chat activity cannot erase an independently diagnosed Git, sync or remote blocker.
        const activity = !lastCompletion && hasReason && result?.status === "deferred" && attemptDiagnostic?.category === "activity" && activityCodes.has(attemptDiagnostic.code) ? checkedActivity : null;
        if (hasReason && activity) refs.status.textContent = activity.publicationAllowed ? text(activity.activityClear ? "activityRetry" : "activityAllowedRetry") : diagnosticStatus(activity.diagnostic);
        const resultNotice = result?.activityPolicy === "allow_saved_snapshot" ? normalizedDiagnostic(result.activityNotice) : null;
        const savedWorkNotice = activeStatuses.has(result?.status) && resultNotice?.category === "activity" && activityCodes.has(resultNotice.code);
        const policyRetry = !lastCompletion && hasReason && !activity && result?.status === "deferred" && attemptDiagnostic?.category === "activity" && activityCodes.has(attemptDiagnostic.code) && state.settings.naming.allowActiveWork === true;
        if (policyRetry) refs.status.textContent = text("previousPause");
        if (awaitingReceipt) refs.status.textContent = text("checkingReceipt");
        else if (!lastCompletion && result && failedRepoStatuses.has(result.status) && !activeStatuses.has(state.operation?.status) && !policyRetry && !activity) refs.status.textContent = text("lastAttempt") + " · " + refs.status.textContent;
        refs.reason.textContent = awaitingReceipt ? text("checkingReceipt") + " · " + text("knownBefore") : hasReason ? activity ? currentActivityText(activity) : policyRetry ? text("policyRetryHint") : compactReason(diagnosis) : savedWorkNotice ? text("activeAllowed") : ""; refs.reason.hidden = !refs.reason.textContent; refs.reason.title = refs.reason.textContent;
        if (refs.reason.hidden) refs.status.removeAttribute("aria-describedby"); else refs.status.setAttribute("aria-describedby", refs.reason.id);
        refs.status.dataset.changeState = displayChangeState;
        refs.status.dataset.attention = String(Boolean(hasReason && refs.reason.textContent && !policyRetry && !activity?.publicationAllowed));
        refs.status.dataset.status = policyRetry || activity?.publicationAllowed ? "snapshot_available" : originalResult && !result ? "historical" : lastCompletion ? "current" : clean(result?.status, 60); refs.status.disabled = !state.allowed;
        refs.history.hidden = !(repo.enabled === true && lastCompletion && successfulRepoStatuses.has(result.status));
        refs.history.textContent = refs.history.hidden ? "" : [text("lastUpload"), repositoryProgressComplete(result) ? "100%" : "", result.uploadSummary?.state === "pending" ? text("uploadPending") : ""].filter(Boolean).join(" · ");
        refs.history.title = refs.history.textContent;
        refs.status.title = [text("diagnosis"), activity ? currentActivityText(activity) : policyRetry ? text("policyRetryHint") : compactReason(diagnosis), activity ? activity.publicationAllowed ? "" : activity.diagnostic?.nextStep : policyRetry ? "" : diagnosis.nextStep, reading?.busy && catalog ? text("knownBefore") : ""].filter(Boolean).join(" · "); refs.push.textContent = text("pushOne"); refs.push.title = text("commitPushHint"); refs.push.setAttribute("aria-label", text("pushOne") + " · " + repoName(repo) + " · " + text("commitPushHint")); refs.push.disabled = runButton.disabled || repo.enabled !== true;
        renderRepositoryActivity(refs, repo, lastCompletion ? null : result, reading, catalog);
      }
      renderCommitAges();
    }
    function renderConfigVisibility() {
      for (const [id, card] of configCards) { card.children[0].textContent = repoName(state.settings?.repositories.find(repo => repo.id === id)); card.hidden = Boolean(state.configRepoId && id !== state.configRepoId); if (state.configRepoId === id) card.open = true; }
      addButton.hidden = Boolean(state.configRepoId); namingDetails.hidden = Boolean(state.configRepoId && !state.diagnosticNaming);
      if (state.configRepoId) warningDetails.hidden = true;
    }
    function renderCheckActivity() {
      const selected = state.versionRefresh?.repoId;
      checkRefresh.hidden = !state.versionBusy || Boolean(selected);
      for (const repo of state.settings?.repositories || []) {
        const refs = compactRefs.get(repo.id); if (!refs) continue;
        const busy = state.versionBusy && selected === repo.id;
        refs.versionRefresh.hidden = !busy; refs.version.setAttribute("aria-busy", String(busy));
        refs.version.disabled = runButton.disabled || repo.enabled !== true;
      }
    }
    async function readVersions(repoId = "") {
      if (state.destroyed || !state.allowed || !state.settings || state.versionBusy || state.readBusy || workspacePanel.hidden || blocked()
        || state.dirty || state.saveBusy || state.invalid.size || inputPending.size || !enabled().length) return;
      const ids = enabled().filter(repo => !repoId || repo.id === repoId).map(repo => repo.id); if (!ids.length) return;
      const refresh = { epoch: state.versionEpoch, settingsSha: state.settingsSha, sources: sourceIdentities(state.settings), ids, repoId, deadline: Date.now() + 60000,
        controller: new AbortController(), settings: clone(state.settings), cacheIdentity: state.cacheIdentity, serverVersionSources: new Map(state.serverVersionSources),
        snapshotMode: state.snapshotMode, catalog: new Map(state.catalog), versionReads: new Map(state.versionReads), multiBindings: new Set(state.multiBindings) };
      state.versionRefresh = refresh; state.versionBusy = true; state.needsVersionsRead = false;
      stopCommitAgeTimer(); render(); await readVersionSnapshotStep(refresh, true);
    }
    function stopVersionRefresh() {
      if (state.versionPollTimer) window.clearTimeout(state.versionPollTimer); state.versionPollTimer = 0;
      state.versionRefresh?.controller.abort();
      state.versionRefresh = null; state.versionBusy = false;
    }
    function versionRefreshMatches(refresh) {
      return state.versionRefresh === refresh && !state.destroyed && !workspacePanel.hidden && !document.hidden && !state.ageSuspended
        && state.versionEpoch === refresh.epoch && state.settingsSha === refresh.settingsSha && !blocked()
        && state.settings?.repositories.length === refresh.sources.size && state.settings.repositories.every(repo => refresh.sources.get(repo.id) === sourceIdentity(repo));
    }
    async function readVersionSnapshotStep(refresh, start = false) {
      if (state.versionRefresh !== refresh) return;
      if (!versionRefreshMatches(refresh)) { stopVersionRefresh(); if (!state.destroyed) render(); return; }
      try {
        const value = await request("/versions?snapshot=1" + (start ? "&refresh=1" : "") + (refresh.repoId ? "&repoId=" + encodeURIComponent(refresh.repoId) : ""), undefined, refresh.controller.signal);
        if (state.versionRefresh !== refresh || state.destroyed) return;
        if (!versionRefreshMatches(refresh)) { stopVersionRefresh(); render(); return; }
        if (!acceptVersionSnapshots(value, refresh.sources, !refresh.cacheIdentity, refresh)) { const error = new Error("invalid_versions_snapshot"); error.kind = "invalid_response"; throw error; }
        if (value.complete === true) {
          for (const id of refresh.ids) {
            const read = value.versionReadStates[id], expected = refresh.serverVersionSources.get(id);
            const items = value.versionSnapshots.filter(item => item?.repoId === id && item.sourceIdentity === expected && Array.isArray(item.components));
            if (!expected || !plain(read) || read.sourceIdentity !== expected || !["ready", "error"].includes(read.state)
              || read.state === "ready" && (items.length !== 1 || !Number.isFinite(Date.parse(read.checkedAt)))) {
              const error = new Error("invalid_repository_receipt"); error.kind = "invalid_response"; throw error;
            }
          }
          state.cacheIdentity = refresh.cacheIdentity; state.serverVersionSources = refresh.serverVersionSources; state.snapshotMode = true;
          state.catalog = refresh.catalog; state.versionReads = refresh.versionReads; state.multiBindings = refresh.multiBindings;
          stopVersionRefresh(); render(); readCompletedSettings(); return;
        }
        if (Date.now() >= refresh.deadline) { const error = new Error("snapshot_deadline"); error.kind = "timeout"; throw error; }
        state.versionPollTimer = window.setTimeout(() => { state.versionPollTimer = 0; void readVersionSnapshotStep(refresh); }, 1200);
      } catch (error) {
        if (state.versionRefresh !== refresh || state.destroyed) return;
        stopVersionRefresh();
        for (const id of refresh.ids) {
          const repo = state.settings.repositories.find(item => item.id === id);
          if (repo && refresh.sources.get(id) === sourceIdentity(repo)) state.versionReads.set(id, { ...readFor(repo), sourceIdentity: sourceIdentity(repo), busy: false, error, manualError: true });
        }
        render(); readCompletedSettings();
      }
    }
    function renderVersionPlans() {
      for (const repo of state.settings?.repositories || []) {
        const box = planBoxes.get(repo.id); if (!box) continue;
        box.replaceChildren(); const heading = node("h4", "repository-publish-plan-heading", text("versionSummary")); box.append(heading);
        const catalog = displayCatalogFor(repo), components = catalog?.components || [], seen = new Set();
        for (const component of components) {
          const plan = repo.versionPlans.find(item => item.sourceId === component.sourceId), row = node("div", "repository-publish-plan-row"), label = node("span"), action = managed(node("button", "ghost-button repository-publish-plan-action")); action.type = "button"; seen.add(component.sourceId);
          const transition = componentTransition(component, catalog), hint = node("span", "repository-publish-plan-reason");
          label.textContent = componentVersionText(component, components.length, catalog);
          label.title = [clean(component.path, 200), clean(component.key, 120), clean(component.versionCommitSha, 40), clean(component.sourceHeadSha, 40)].filter(Boolean).join(" · ");
          hint.textContent = transition ? text(transition.kind === "planned" ? "planned" : transition.kind === "auto" ? "automaticVersion" : "actualVersionChange")
            : plan ? text("planUnverified") + " · " + text("planTarget") + " " + clean(plan.targetVersion, 80) : text("keepCurrent");
          if (!plan && !transition && component.canBump === true && clean(component.currentVersion, 80) && clean(component.nextVersion, 80)) hint.textContent += " · " + text("candidateVersion") + " " + clean(component.nextVersion, 80);
          if (component.kind === "git_commit") hint.textContent += " · " + text("gitCommitHint");
          action.textContent = text(plan ? "cancelPlan" : "nextPatch"); action.disabled = blocked() || state.saveBusy || inputPending.size > 0 || state.versionBusy || !plan && (catalog?.displayOnly === true || component.canBump !== true || typeof component.sourceId !== "string" || !component.sourceId || typeof component.currentVersion !== "string" || !component.currentVersion || typeof component.nextVersion !== "string" || !component.nextVersion || !/^[a-f0-9]{64}$/.test(component.planProof) || !/^[a-f0-9]{64}$/.test(component.expectedSha256) || !Number.isSafeInteger(component.expectedBytes) || component.expectedBytes < 0);
          action.addEventListener("click", () => { if (action.disabled || blocked() || state.versionBusy || state.saveBusy || inputPending.size) return; repo.versionPlans = repo.versionPlans.filter(item => item.sourceId !== component.sourceId); if (!plan) repo.versionPlans.push({ sourceId: component.sourceId, currentVersion: component.currentVersion, targetVersion: component.nextVersion, expectedSha256: component.expectedSha256, expectedBytes: component.expectedBytes, planProof: component.planProof }); changed(); });
          row.append(label, action, hint); if (component.canBump !== true) row.append(node("span", "repository-publish-plan-reason", clean(component.reason, 300) || text("versionUnsupported"))); box.append(row);
        }
        for (const plan of repo.versionPlans) if (!seen.has(plan.sourceId)) {
          const row = node("div", "repository-publish-plan-row"), cancel = managed(node("button", "ghost-button", text("cancelPlan"))); cancel.type = "button"; cancel.disabled = blocked() || state.versionBusy || state.saveBusy || inputPending.size > 0;
          row.append(node("span", "", text("planUnverified") + " · " + text("planTarget") + " " + clean(plan.targetVersion, 80)), cancel); box.append(row);
          cancel.addEventListener("click", () => { if (cancel.disabled || blocked() || state.versionBusy || state.saveBusy || inputPending.size) return; repo.versionPlans = repo.versionPlans.filter(item => item !== plan); changed(); });
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
    async function request(path = "", body, externalSignal) {
      const controller = new AbortController();
      const timeoutMs = body === undefined ? path.split("?")[0] === "/activity" ? 30000 : path.split("?")[0] === "/versions" && !path.includes("snapshot=1") ? 60000 : 10000 : 20000;
      const timer = window.setTimeout(() => controller.abort(), timeoutMs);
      const abort = () => { controller.abort(); window.clearTimeout(timer); }; externalSignal?.addEventListener("abort", abort, { once: true });
      if (externalSignal?.aborted) abort();
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
      } finally { window.clearTimeout(timer); externalSignal?.removeEventListener("abort", abort); }
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
      if (state.destroyed || state.versionBusy || state.readBusy || state.postBusy || state.saveBusy) return;
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
          acceptVersionSnapshots(value, sources, true, state, true);
        }
        const accepted = value.operation && acceptOperation(value.operation);
        if (!accepted && !state.dirty) { state.error = ""; state.notice = ""; }
        if (state.pendingId) schedulePoll();
      } catch (error) { state.error = "readFailed"; state.statusReadError = { error, sources: sourcesAtRead }; }
      finally { state.readBusy = false; render(); readCompletedSettings(); }
    }
    function readCompletedSettings() {
      if (state.destroyed || state.versionBusy || state.readBusy || state.postBusy || state.saveBusy) return;
      if (state.needsSettingsRead) { state.needsSettingsRead = false; void readStatus(); return; }
      state.needsVersionsRead = false;
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
      if (!state.dirty || state.saveBusy || state.destroyed || blocked() || state.versionBusy || inputPending.size || state.configConflict) return;
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
        if (Array.from(sources).some(([id, identity]) => state.savedSources.get(id) !== identity)) { state.versionEpoch++; state.needsVersionsRead = true; if (state.snapshotMode) { stopVersionRefresh(); state.needsSettingsRead = true; } previewResult.replaceChildren(); }
        state.savedSources = sources; state.settingsSha = value.settingsSha;
        if (state.edit === edit) { state.settings = saved; state.dirty = false; state.error = ""; state.notice = "saved"; syncDrafts.clear(); if (dialog.open) renderConfig(); }
      } catch (error) { if (error?.message === "configConflict") state.configConflict = true; state.error = state.configConflict ? "configConflict" : "saveFailed"; }
      finally { state.saveBusy = false; render(); if (succeeded && state.edit !== edit) void save(); else readCompletedSettings(); }
    }
    async function run(repoIds) {
      if (!state.allowed || !state.settings || blocked() || state.versionBusy || state.readBusy || state.saveBusy || state.dirty || state.invalid.size || !enabled().length) return;
      const selected = (repoIds || enabled().map(repo => repo.id)).filter(id => {
        const repo = state.settings.repositories.find(item => item.id === id); return !repo || !confirmedClean(repo);
      });
      const rank = id => {
        const repo = state.settings.repositories.find(item => item.id === id), catalog = repo && catalogFor(repo);
        return repo && currentCatalog(catalog, readFor(repo)) && repoChangeState(catalog) === "changed" ? 0 : 1;
      };
      selected.sort((left, right) => rank(left) - rank(right));
      if (!selected.length) { state.error = ""; state.notice = "nothingToUpload"; render(); return; }
      const requestId = uniqueId(), original = { requestId, repoIds: selected, createdAt: Date.now(), intent: "commit_and_push" };
      if (!requestId || !persistRequest(original)) { state.error = "noIdentity"; render(); return; }
      state.pendingRequest = original; await sendOriginal(original);
    }
    async function sendOriginal(original) {
      const requestId = original.requestId;
      state.operatedRepoIds = new Set(original.repoIds);
      if (state.snapshotMode) { stopVersionRefresh(); state.versionEpoch++; }
      stopPoll(); state.pendingId = requestId; state.notFound = false; state.operation = null; state.postBusy = true; state.error = ""; state.notice = "working"; renderResults(); render();
      try {
        const payload = { requestId, repoIds: original.repoIds };
        if (original.intent === "commit_and_push") payload.intent = original.intent;
        const value = await request("/run", payload); if (!acceptOperation(value.operation || value)) state.notice = "unknown";
      }
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
      localize(addButton, "add"); localize(namingSummary, "publishingOptions"); localize(detailSummary, "details"); localize(refreshButton, "refresh"); localize(previewButton, "preview"); localize(previewHint, "previewHint");
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
        field(namingFields, "allowActiveWork", naming.allowActiveWork, value => { naming.allowActiveWork = value; }, { checkbox: true });
        const activeHint = node("p", "repository-publish-hint repository-publish-policy-hint"); localize(activeHint, "allowActiveHint"); namingFields.append(activeHint);
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
        const resultDiagnostic = normalizedDiagnostic(result.diagnostic), statusLabel = failedRepoStatuses.has(result.status) ? diagnosticStatus(resultDiagnostic, result.status === "deferred" ? "uploadPaused" : "failed") : successfulRepoStatuses.has(result.status) ? text("uploaded") : skippedRepoStatuses.has(result.status) ? text("repoNoChanges") : reviewRepoStatuses.has(result.status) ? text("verifyRequired") : activeStatuses.has(result.status) ? phaseText(result.phase) : clean(result.status, 60);
        title.textContent = clean(result.name || result.repoId, 200); summary.textContent = [statusLabel, compactReason(resultDiagnostic) || safeDiagnosticText(result.message, 500)].filter(Boolean).join(" · "); localize(expandedTitle, "details");
        if (!currentTarget) card.append(node("p", "repository-publish-hint", text("historicalReceipt") + " · " + text("historicalHint")));
        const binding = result.uploadSummary?.binding;
        if (plain(binding)) {
          const destination = ["path", "repositoryUrl", "remote", "branch"].map(key => clean(binding[key], 500)).filter(Boolean).join(" · ");
          if (destination) card.append(node("p", "repository-publish-hint", text("originalTarget") + " · " + destination));
        }
        const logs = (Array.isArray(result.logs) ? result.logs : []).slice(-100).map(item => [clean(item.at, 80), clean(item.phase, 80), clean(item.message, 500)].filter(Boolean).join(" · ")).join("\n");
        const progress = currentTarget ? repositoryProgressInfo(result) : null;
        content.textContent = [progress ? [progress.phase, progress.metrics, progress.measured ? text("phasePercent") : ""].filter(Boolean).join(" · ") : "", clean(result.title), clean(result.body, 16000), clean(result.commitSha, 80), logs].filter(Boolean).join("\n\n"); expanded.append(expandedTitle, content); card.append(title, summary, expanded); results.append(card);
        if (currentTarget && (["push_failed", "commit_failed", "conflict", "interrupted", "failed", "unknown", "index_pending", "deferred", "verification_required"].includes(result.status) || successfulRepoStatuses.has(result.status) && result.uploadSummary?.state === "pending" || state.operation?.status === "verification_required" && activeStatuses.has(result.status)) && typeof result.repoId === "string") {
          const retry = managed(node("button", "ghost-button")); retry.type = "button"; localize(retry, "retry"); card.append(retry); resultRetries.push(retry); retry.addEventListener("click", () => void run([result.repoId]));
        }
      }
    }
    async function preview(repoId) {
      if (blocked() || state.versionBusy || state.previewBusy || state.saveBusy || state.dirty || !enabled().length) return;
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
      if (selected !== state.configRepoId) { previewResult.replaceChildren(); cancelActivityCheck(); }
      state.diagnosticNaming = false;
      state.configRepoId = selected;
      state.returnFocus = document.activeElement; if (state.settings && !dialog.open && !state.dirty) renderConfig();
      if (!dialog.open) dialog.showModal(); renderResults(); render();
      if (state.pendingId) void poll(); else void readStatus();
    }
    runButton.addEventListener("click", () => void run()); configButton.addEventListener("click", () => open()); closeButton.addEventListener("click", () => dialog.close());
    checkButton.addEventListener("click", () => { if (!checkButton.disabled) void readVersions(); });
    toggleButton.addEventListener("click", () => { if (!state.allowed || state.destroyed) return; state.expanded = !state.expanded; render(); if (state.expanded) { if (state.pendingId) void poll(); else void readStatus(); } });
    dialog.addEventListener("close", () => { cancelActivityCheck(); render(); state.returnFocus?.focus(); });
    addButton.addEventListener("click", () => {
      if (!state.settings || blocked() || state.saveBusy || inputPending.size) return;
      const id = uniqueId(); if (!id) { state.error = "noIdentity"; render(); return; }
      state.settings.repositories.push({ id, path: "", repositoryUrl: "", remote: "origin", branch: "", enabled: false, syncFiles: [], versionSources: [], versionPlans: [], exclude: [] }); renderConfig(); configCards.get(id).open = true; changed();
    });
    refreshButton.addEventListener("click", () => { if (state.configConflict) void readStatus(true); else if (state.dirty) void save(); else if (state.pendingId) void poll(); else void readStatus(); }); previewButton.addEventListener("click", () => void preview(state.configRepoId));
    resumeButton.addEventListener("click", () => void resumeOriginal());
    let observer = null;
    if (typeof MutationObserver === "function") { observer = new MutationObserver(() => { if (dialog.open) renderResults(); render(); }); observer.observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] }); }
    let visibilityObserver = null, wasHidden = workspacePanel.hidden, recheckBusy = false;
    function canRecheckVisible() {
      return !state.destroyed && !workspacePanel.hidden && (state.expanded || dialog.open) && state.allowed && state.settings
        && !blocked() && !state.dirty && !state.invalid.size && !inputPending.size && !state.saveBusy && !state.readBusy && !state.versionBusy;
    }
    async function recheckVisible() {
      if (recheckBusy || !canRecheckVisible()) return;
      recheckBusy = true;
      try { await readStatus(); } finally { recheckBusy = false; }
    }
    if (typeof MutationObserver === "function") {
      visibilityObserver = new MutationObserver(() => {
        const hidden = workspacePanel.hidden; if (hidden === wasHidden) return; wasHidden = hidden;
        if (hidden) { state.versionEpoch++; cancelActivityCheck(); stopCommitAgeTimer(); stopVersionRefresh(); for (const refs of compactRefs.values()) refs.picker.open = false; render(); } else { renderCommitAges(); void recheckVisible(); }
      });
      visibilityObserver.observe(workspacePanel, { attributes: true, attributeFilter: ["hidden"] });
    }
    function suspend() { state.ageSuspended = true; cancelActivityCheck(); stopPoll(); stopVersionRefresh(); stopCommitAgeTimer(); if (!state.destroyed) render(); }
    function resume() { state.ageSuspended = false; if (workspacePanel.hidden || state.destroyed) return; renderCommitAges(); if (state.pendingId) schedulePoll(); else void recheckVisible(); }
    function ageVisibility() { if (document.hidden === true) { stopCommitAgeTimer(); stopVersionRefresh(); render(); } else renderCommitAges(); }
    window.addEventListener("pagehide", suspend); window.addEventListener("pageshow", resume); window.addEventListener("focus", recheckVisible);
    function dismissVersionPickers(event) { for (const refs of compactRefs.values()) if (!refs.picker.contains(event.target)) refs.picker.open = false; }
    document.addEventListener("click", dismissVersionPickers);
    document.addEventListener("visibilitychange", ageVisibility);
    const api = { open, refresh: readStatus, hasDraft: () => state.dirty || state.invalid.size > 0, canReload: () => !state.dirty && !state.saveBusy && !state.postBusy && !state.previewBusy && !state.versionBusy, destroy() { state.destroyed = true; cancelActivityCheck(); stopPoll(); stopVersionRefresh(); stopCommitAgeTimer(); observer?.disconnect(); visibilityObserver?.disconnect(); window.removeEventListener("pagehide", suspend); window.removeEventListener("pageshow", resume); window.removeEventListener("focus", recheckVisible); document.removeEventListener("click", dismissVersionPickers); document.removeEventListener("visibilitychange", ageVisibility); bar.remove(); expanded.remove(); dialog.remove(); mounted.delete(host); instances.delete(api); } };
    mounted.set(host, api); instances.add(api); render(); void readStatus(); return api;
  }
  window.ConsoleRepositoryPublish = { mount, hasDraft: () => Array.from(instances).some(item => item.hasDraft()), canReload: () => Array.from(instances).every(item => item.canReload()) };
  const mountDefault = () => { const host = document.getElementById("consoleRepositoryPublishHost"); if (host) mount({ host }); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mountDefault, { once: true });
  else mountDefault();
})();
