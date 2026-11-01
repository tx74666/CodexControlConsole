"use strict";
(() => {
  const byId = id => document.getElementById(id);
  // Keep bilingual UI phrases separate from image names and editable metadata.
  const phrases = new Map();
  const text = (zh, en) => {
    const pair = [String(zh), String(en)];
    phrases.set(pair[0], pair); phrases.set(pair[1], pair);
    return window.ImageManagerI18n?.text(...pair) ?? pair[0];
  };
  const localized = (value, language) => phrases.get(String(value))?.[language === "en" ? 1 : 0] ?? String(value || "");
  const currentText = value => value === undefined ? "" : phrases.has(String(value)) ? text(...phrases.get(String(value))) : value;
  function setText(element, value) {
    const pair = phrases.get(String(value)) || [String(value ?? ""), String(value ?? "")];
    if (window.ImageManagerI18n?.setText) window.ImageManagerI18n.setText(element, ...pair);
    else element.textContent = value;
  }
  function serviceMessage(value, zh, en, code = "") {
    const message = typeof value === "string" ? value : "";
    if (phrases.has(message)) { const pair = phrases.get(message); return text(...pair); }
    const safeCode = /^[a-z0-9][a-z0-9_-]{0,79}$/i.test(code) ? code : "";
    return text(message || zh, message && !/[\u3400-\u9fff]/.test(message) ? message : `${en}${safeCode ? ` (${safeCode})` : ""}`);
  }
  const endpoint = "/api/images/";
  const embedded = typeof window !== "undefined" && window.parent !== window
    && new URLSearchParams(window.location.search).get("embed") === "steamwork";
  let reviewExpanded = !embedded;
  const actions = new Set(["replace", "keep", "add"]);
  const statusLabels = { new: text("新图片", "New image"), duplicate: text("重复图片", "Duplicate image"), conflict: text("替换候选", "Replacement candidate"), ambiguous: text("多个匹配，请比较", "Multiple matches: compare first") };
  const errors = {
    root_changed: text("图库位置已变化，请重新打开页面读取。当前选择已保留。", "The library location changed. Reopen this page to reload it. Your choices are retained."),
    revision_conflict: text("图片在比较后发生了变化，请重新检查后选择。", "Images changed after comparison. Check images again before choosing."),
    plan_stale: text("图片在比较后发生了变化，请重新检查后选择。", "Images changed after comparison. Check images again before choosing."),
    plan_not_found: text("这份比较记录已不可用，请重新检查图片。", "This comparison is no longer available. Check images again."),
    notion_unavailable: text("Notion 同步连接尚未就绪。页面地址可先保存，本地图与设备同步仍可使用。", "Notion is not ready. You can save its page address and continue using local and device sync."),
    device_not_configured: text("请先在「图库与同步位置」填写设备文件夹。", "Enter a device folder under Library and sync locations first.")
  };
  let state = null;
  let root = "";
  let busy = false;
  let generation = 0;
  let plan = null;
  let reviewNeedsScan = false;
  let decisions = new Map();
  let previewFocus = null;
  let pendingOperation = null;
  let lastApplied = null;
  let metadataTarget = null;
  let metadataFocus = null;
  let metadataBaseline = "";
  let metadataJob = null;
  let namingPlan = null;
  let namingScope = null;
  let namingDrafts = new Map();
  let namingFocus = null;
  let previewItem = null;
  let deletionTarget = null;
  let deletionRequest = null;
  const groupSelections = new Map();
  const candidateSelections = new Map();
  const handledPasteEvents = new WeakSet();
  const clipboardImageTypes = new Map([
    ["image/png", "png"], ["image/jpeg", "jpg"], ["image/webp", "webp"], ["image/gif", "gif"],
    ["image/bmp", "bmp"], ["image/x-ms-bmp", "bmp"], ["image/tiff", "tiff"],
    ["image/x-icon", "ico"], ["image/vnd.microsoft.icon", "ico"]
  ]);
  const continuations = new Map();
  const pendingStatuses = new Set(["pending", "queued", "running", "in_progress", "starting"]);
  const completeStatuses = new Set(["completed", "succeeded", "success", "done", "needs_review"]);
  const str = value => typeof value === "string" ? value : typeof value === "number" ? String(value) : "";
  const node = (tag, className, value) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (value !== undefined) element.textContent = value;
    return element;
  };
  const metadata = value => value && typeof value === "object" && !Array.isArray(value) ? value : null;
  const planId = value => str(value?.planId || value?.id);
  const decisionKey = () => `console-image-decisions:${root}:${planId(plan)}`;
  const operationKey = () => `console-image-operation:${root}`;
  const deletionKey = () => `console-image-deletion:${root}`;
  const deletionUncertain = () => ["pending", "unknown", "recovery_required"].includes(deletionRequest?.status);
  function pageId(value) {
    const match = str(value).match(/[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}/i);
    return match ? match[0].replace(/-/g, "").toLowerCase() : "";
  }
  const configuredPageId = () => pageId(state?.notionPage) || pageId(state?.notion?.pageId);
  const notionReady = () => state?.notion?.sourceOnly !== true && (state?.notionAvailable === true || state?.notion?.canAttempt === true || state?.notion?.available === true);
  const notionScopeMatches = value => value?.root === root && Boolean(configuredPageId()) && pageId(value.pageId) === configuredPageId();
  function notionSyncStatus() {
    if (!root || !configuredPageId() || !notionReady()) return "unavailable";
    if (pendingOperation && notionScopeMatches(pendingOperation)) return ["unknown", "failed", "error", "needs_review"].includes(pendingOperation.uiStatus) ? "failed" : "syncing";
    const operation = state?.notion?.operation || state?.operation;
    if (notionScopeMatches(operation)) {
      if (["unknown", "failed", "error", "needs_review"].includes(operation.status)) return "failed";
      if (pendingStatuses.has(operation.status)) return "syncing";
    }
    const summary = state?.notionSync || state?.notion?.syncStatus;
    if (!notionScopeMatches(summary)) return "unverified";
    if (["syncing", "failed"].includes(summary.status)) return summary.status;
    const local = str(summary.localFingerprint).toLowerCase(), synced = str(summary.syncedFingerprint).toLowerCase();
    if (summary.status === "synced" && /^[a-f0-9]{64}$/.test(local) && local === synced) return "synced";
    return summary.status === "pending" ? "pending" : "unverified";
  }
  function updateNotionStatus() {
    const status = notionSyncStatus();
    const labels = {
      unavailable: !configuredPageId() ? text("Notion 未配置", "Notion not configured") : text("Notion 连接未就绪", "Notion connection not ready"),
      unverified: text("Notion 待同步 · 未核验", "Notion pending · not verified"),
      pending: text("Notion 待同步", "Notion pending sync"),
      syncing: text("Notion 同步中", "Syncing to Notion"),
      failed: text("Notion 同步失败 / 待核对", "Notion failed / needs checking"),
      synced: text("本地内容已同步到 Notion", "Local content verified in Notion")
    };
    const badge = byId("notionSyncState");
    if (badge) { badge.dataset.status = status; setText(badge, labels[status]); }
    setText(byId("notionSummary"), labels[status]);
    byId("notionSummary").dataset.connected = String(status === "synced");
    const hint = !root ? text("先保存当前图片文件夹。", "Save the current image folder first.")
      : !configuredPageId() ? text("在「图库与同步位置」保存 Notion 页面后，再同步。更新本地仍可使用。", "Save a Notion page under Library and sync locations before syncing. Update local is still available.")
      : !notionReady() ? text("Notion 连接尚未就绪；可先更新本地，连接就绪后再同步。", "Notion is not ready. Update local first, then sync when the connection is available.")
      : status === "synced" ? text("当前本地已采用内容已核验同步到 Notion；Inbox 仍需确认，Notion 历史附件保留。", "The adopted local content was verified in Notion. Inbox images still need confirmation; historical Notion attachments are retained.")
      : status === "failed" ? text("同步未完整完成，请核对原请求；本地图片与未采用的 Inbox 保留。", "Sync has not fully completed. Check the original request; local images and unadopted Inbox images are retained.")
      : status === "syncing" ? text("正在同步已采用图片，请等待原请求结果。", "Syncing adopted images. Wait for the original request result.")
      : text("把当前文件夹已采用图片同步到 Notion；Inbox 不会自动入库，也不会自动删除云端附件。", "Sync adopted images from the current folder to Notion. Inbox images are not added automatically, and cloud attachments are not deleted automatically.");
    setText(byId("notionSyncHint"), hint);
    byId("syncImages").disabled ||= !root || !configuredPageId() || !notionReady();
  }
  function advancedSyncAllowed() {
    const source = byId("syncSource").value, target = byId("syncTarget").value;
    return source === "notion" ? ["console", "device", "all"].includes(target) : ["console", "local"].includes(source) && ["notion", "device", "all"].includes(target);
  }
  function advancedSyncIssue() {
    if (!advancedSyncAllowed()) return text("请选择不同的来源与目标；当前文件夹无需同步给自己。", "Choose different source and destination locations. The current folder does not need to sync to itself.");
    const source = byId("syncSource").value, target = byId("syncTarget").value;
    if (target === "device" && !state?.deviceRoot) return text("先在「图库与同步位置」保存额外设备文件夹。", "Save an additional device folder under Library and sync locations first.");
    if ((source === "notion" || ["notion", "all"].includes(target)) && (!configuredPageId() || !notionReady())) return text("先配置可用的 Notion 目标页面。", "Configure an available Notion destination page first.");
    return "";
  }
  const standardTypes = () => (Array.isArray(state?.standardTypes) ? state.standardTypes : []).filter(type => type && typeof type.code === "string" && type.code.length <= 140);
  const standardNaming = () => state?.standardNaming === true;
  const validStandardType = code => standardTypes().some(type => type.code === code);
  const metadataPurpose = () => standardNaming() ? byId("metadataStandardType").value : byId("metadataGroupTitle").value.trim();
  const metadataValues = () => JSON.stringify([metadataPurpose(), byId("metadataVariantLabel").value.trim(), byId("metadataDerivedFrom").value]);
  const metadataDirty = () => Boolean(metadataTarget) && metadataValues() !== metadataBaseline;
  const metadataJobKey = item => `console-image-metadata-sync:${item.root || item.expectedRoot}:${item.path}:${item.sha256}`;
  const metadataPlanKey = id => `console-image-metadata-plan:${root}:${id}`;
  const annotationFingerprint = item => JSON.stringify([groupTitle(item), str(item.variantLabel), str(item.derivedFromId), str(item.pendingDerivedFromId)]);
  function standardName(item, code = str(item?.standardType)) {
    if (!validStandardType(code)) return "";
    const extension = str(item?.canonicalName || item?.standardName).match(/\.[a-z0-9]+$/i)?.[0];
    return extension && Number.isInteger(item?.width) && item.width > 0 && Number.isInteger(item?.height) && item.height > 0 ? `${code}_${item.width}x${item.height}${extension.toLowerCase()}` : "";
  }
  function fillStandardTypes(select, value) {
    select.replaceChildren();
    const placeholder = node("option", "", text("选择标准用途", "Choose a standard purpose")); placeholder.value = ""; select.append(placeholder);
    for (const type of standardTypes()) {
      const option = node("option", "", type.label && type.label !== type.code ? text(`${str(type.label)} · ${type.code}`, type.code) : type.code);
      option.value = type.code; select.append(option);
    }
    select.value = validStandardType(value) ? value : "";
  }
  function needsStandardPurpose(candidate) {
    const incoming = metadata(candidate.incoming) || metadata(candidate.source);
    const confirmed = validStandardType(str(incoming?.standardType)) && incoming?.namingNeedsReview !== true;
    const inboxSuggestion = incoming?.space !== "device" && /^inbox[\\/]/i.test(str(incoming?.path)) && validStandardType(str(incoming?.suggestedStandardType));
    return standardNaming() && !confirmed && !inboxSuggestion;
  }
  function defaultReplacement(candidate) {
    if (candidate.previousCandidateId || candidate.status === "new" || candidate.status === "ambiguous"
        || !Array.isArray(candidate.actions) || !candidate.actions.includes("replace") || Number(candidate.matchCount) > 1) return false;
    const incoming = metadata(candidate.incoming) || metadata(candidate.source);
    const existing = metadata(candidate.existing) || metadata(candidate.target);
    if (!incoming || !existing || !safeImagePath(existing.path) || !/^[a-f0-9]{64}$/i.test(str(existing.sha256))
        || !Number.isInteger(incoming.width) || incoming.width <= 0 || !Number.isInteger(incoming.height) || incoming.height <= 0
        || incoming.width !== existing.width || incoming.height !== existing.height) return false;
    const purpose = item => str(item.groupId || item.standardType || item.groupTitle || item.title).normalize("NFC").trim().toLocaleLowerCase();
    if (!purpose(incoming) || purpose(incoming) !== purpose(existing)) return false;
    return !(candidate.matches || []).some(match => metadata(match) && imageKey(match) !== imageKey(existing));
  }
  const canAutomaticallyAdd = candidate => candidate.status === "new" && !candidate.previousCandidateId && (!standardNaming() || validStandardType(str(candidate.incoming?.standardType)) && candidate.incoming?.namingNeedsReview === false);
  const safeImagePath = value => typeof value === "string" && Boolean(value) && !/^[\\/]|^[a-z]:|[\x00-\x1f]/i.test(value) && !value.split(/[\\/]/).some(part => !part || part === "." || part === "..");
  function updateMetadataName() {
    const enabled = standardNaming();
    byId("metadataGroupTitle").hidden = enabled;
    byId("metadataGroupTitle").required = !enabled;
    byId("metadataStandardType").hidden = !enabled;
    byId("metadataStandardType").required = enabled;
    setText(byId("metadataPurposeLabel"), enabled ? text("标准用途", "Standard purpose") : text("用途 / 标题", "Purpose / title"));
    byId("metadataStandardName").hidden = !enabled;
    setText(byId("metadataStandardName"), enabled ? standardName(metadataTarget, metadataPurpose()) ? text(`采用后：${standardName(metadataTarget, metadataPurpose())}`, `After confirmation: ${standardName(metadataTarget, metadataPurpose())}`) : text("先选择标准用途；名称中的尺寸保持图片的真实尺寸。", "Choose a standard purpose. The filename will use the image's actual dimensions.") : "");
    setText(byId("metadataNamingHint"), enabled ? metadataTarget?.indexed ? text("标准用途变更会按预览名称整理文件名；图片内容、方案与派生关系保持。", "Changing the standard purpose renames the file as previewed. Image content, variants and source relationships are retained.") : text("先保存标准用途，确认入库时采用标准文件名。", "Save the standard purpose first. The standard filename is used when you confirm adding the image.") : text("整理用途、方案与来源关系，保留原文件名和图片内容。", "Edit purpose, variant and source relationships while retaining the original filename and image content."));
  }
  function rememberMetadataJob(job) {
    const pair = phrases.get(job.message) || (job.messageZh && job.messageEn ? [job.messageZh, job.messageEn] : null);
    if (pair) job = { ...job, messageZh: pair[0], messageEn: pair[1], message: text(...pair) };
    metadataJob = job;
    try { sessionStorage.setItem(metadataJobKey(job), JSON.stringify(job)); } catch (_) { /* Keep the saved result in memory. */ }
    if (job.planId) try { sessionStorage.setItem(metadataPlanKey(job.planId), JSON.stringify(job)); } catch (_) { /* Optional storage. */ }
    if (metadataTarget && metadataTarget.path === job.path && metadataTarget.sha256 === job.sha256) {
      setText(byId("metadataStatus"), job.message);
      byId("metadataStatus").dataset.error = String(["failed", "unknown", "stale"].includes(job.status));
    }
  }
  function metadataScopeMatches(job, value = state) {
    if (!job || job.root !== root || str(value?.root) !== job.root
        || (pageId(value?.notionPage) || pageId(value?.notion?.pageId)) !== job.pageId
        || str(value?.deviceRoot) !== job.deviceRoot) return false;
    const items = Array.isArray(value?.items) ? value.items : [];
    if (job.indexed) return items.some(item => item.path === job.path && item.sha256 === job.sha256 && item.space !== "device"
      && (!job.annotationFingerprint || annotationFingerprint(item) === job.annotationFingerprint));
    const candidates = (extractPlan(value) || plan)?.candidates || [];
    return candidates.some(candidate => candidate.incoming?.path === job.path && candidate.incoming.sha256 === job.sha256);
  }
  function requireMetadataScope(job, token, expectedRoot, value = state) {
    if (!assertCurrent(token, expectedRoot) || !metadataScopeMatches(job, value)) throw new Error(text("图库、同步位置或原图已改变，已停止本次同步；保存内容与原请求已保留，请重新核对。", "The library, sync locations or original image changed. Sync stopped; saved changes and the original request are retained. Check again."));
  }
  function configurationDirty() {
    return Boolean(state) && (byId("libraryRoot").value.trim() !== root
      || byId("deviceRoot").value.trim() !== str(state.deviceRoot)
      || byId("notionPage").value.trim() !== str(state.notionPage));
  }
  function requireSavedLocations() {
    if (!configurationDirty()) return true;
    byId("locations").open = true;
    setText(byId("configStatus"), text("位置有未保存的修改，请先保存位置。", "Locations have unsaved changes. Save the locations first."));
    if (byId("metadataDialog").open) setText(byId("metadataStatus"), text("位置有未保存的修改，请关闭此框并先保存位置，再同步。", "Locations have unsaved changes. Close this dialog and save the locations before syncing."));
    if (byId("namingDialog").open) setText(byId("namingStatus"), text("位置有未保存的修改，请关闭此框并先保存位置，再整理名称。", "Locations have unsaved changes. Close this dialog and save the locations before organizing names."));
    notice(text("位置有未保存的修改，请先保存位置，再同步。", "Locations have unsaved changes. Save the locations before syncing."), true);
    return false;
  }
  function updateMetadataControls() {
    const dirty = metadataDirty();
    const ownPending = Boolean(pendingOperation?.metadataJob && metadataTarget
      && pendingOperation.metadataJob.path === metadataTarget.path && pendingOperation.metadataJob.sha256 === metadataTarget.sha256);
    const retryable = metadataJob && metadataTarget && metadataJob.path === metadataTarget.path && metadataJob.sha256 === metadataTarget.sha256
      && !["completed", "local", "inbox", "stale"].includes(metadataJob.status);
    byId("metadataSaveOnly").disabled = busy || Boolean(pendingOperation) || !dirty;
    byId("metadataSave").disabled = busy || Boolean(pendingOperation) && !ownPending || !dirty && !retryable;
    if (standardNaming() && !validStandardType(metadataPurpose())) { byId("metadataSave").disabled = true; byId("metadataSaveOnly").disabled = true; }
    setText(byId("metadataSave"), dirty ? text("保存并同步", "Save and sync") : ownPending ? text("继续核对", "Continue checking") : retryable ? metadataJob.planId ? text("查看待确认同步", "Review pending sync") : text("同步已保存修改", "Sync saved changes") : text("保存并同步", "Save and sync"));
  }
  function canRecheckOperation(operation) {
    return operation?.status === "unknown" && operation.code === "catalog_attached_unverified"
      || operation?.recheckable === true && operation.recheckKind === "verified_completion"
        && (operation.status === "failed" && operation.code === "notion_sync_failed"
            || operation.status === "unknown" && operation.code === "verified_completion_unrecorded");
  }
  function recoveryScopeMatches(operation, expectedRoot) {
    const pending = pendingOperation;
    const source = byId("syncSource").value, target = byId("syncTarget").value;
    const actualSource = source === "local" && ["notion", "all"].includes(target) ? "console" : source;
    const actualTarget = target === "all" ? source === "notion" ? "console" : "notion" : target;
    const selectionMatches = pending?.uiMode === "notion" ? operation.source === "console" && operation.target === "notion" : (!pending?.uiSource || pending.uiSource === source)
      && (!pending?.uiTarget || pending.uiTarget === target)
      && ((source === operation.source && target === operation.target)
          || (actualSource === operation.source && actualTarget === operation.target));
    return pending && operation.requestId === pending.requestId
      && operation.root === expectedRoot && operation.root === root && operation.root === pending.root
      && operation.source === pending.source && operation.target === pending.target && selectionMatches
      && Boolean(pageId(operation.pageId)) && pageId(operation.pageId) === pending.pageId
      && pageId(operation.pageId) === configuredPageId();
  }
  const continuationKey = id => `console-image-continuation:${root}:${id}`;
  function setReviewExpanded(expanded) {
    reviewExpanded = Boolean(expanded);
    byId("reviewSection").dataset.expanded = String(reviewExpanded);
    byId("reviewToggle").setAttribute("aria-expanded", String(reviewExpanded));
    setText(byId("reviewToggle"), reviewExpanded ? text("收起", "Collapse") : text("查看 / 确认", "Review / confirm"));
  }
  function changeLanguage(language) {
    if (!["en", "zh-CN"].includes(language)) return;
    document.documentElement.dataset.hostLanguage = language;
    const i18n = window.ImageManagerI18n;
    if (!i18n || i18n.getLanguage() === language) return;
    const focused = document.activeElement;
    const focusId = focused?.id;
    const focusPath = focused?.dataset?.previewPath;
    const focusSize = focused?.dataset?.variantSize && focused?.closest?.("[data-group-id]")?.dataset.groupId;
    i18n.setLanguage(language);
    if (metadataJob?.messageZh && metadataJob.messageEn) metadataJob.message = text(metadataJob.messageZh, metadataJob.messageEn);
    if (state) acceptState(state);
    renderPlan();
    if (byId("namingDialog").open) renderNamingList();
    if (metadataTarget) {
      const selectedType = byId("metadataStandardType").value;
      fillStandardTypes(byId("metadataStandardType"), selectedType);
      const selectedSource = byId("metadataDerivedFrom").value;
      fillDerivedSources(metadataTarget);
      byId("metadataDerivedFrom").value = selectedSource;
      updateMetadataName();
    }
    if (previewItem && byId("previewDialog").open) {
      byId("previewTitle").textContent = title(previewItem);
      setText(byId("previewMeta"), `${dimensions(previewItem)}${previewItem.path ? ` · ${str(previewItem.path)}` : ""}`);
      const image = byId("previewImageWrap").querySelector("img");
      if (image) image.alt = title(previewItem);
      previewFocus = [...byId("imageGrid").querySelectorAll("button"), ...byId("candidateList").querySelectorAll("button")].find(button => button.dataset.previewPath === previewItem.path) || previewFocus;
    }
    updateControls();
    if (focusId) byId(focusId)?.focus({ preventScroll: true });
    else if (focusPath) [...document.querySelectorAll("button")].find(button => button.dataset.previewPath === focusPath)?.focus({ preventScroll: true });
    else if (focusSize) [...byId("imageGrid").querySelectorAll("article")].find(card => card.dataset.groupId === focusSize)?.querySelector("select")?.focus({ preventScroll: true });
  }
  function initializeEmbeddedImage() {
    if (!embedded) return;
    document.documentElement.dataset.embed = "steamwork";
    setText(byId("collectionTitle"), text("图库", "Library"));
    byId("reviewToggle").hidden = false;
    const shell = document.querySelector(".image-shell");
    if (!shell) return;
    let pending = false, previousHeight = 0;
    const report = () => {
      if (pending) return;
      pending = true;
      window.requestAnimationFrame(() => {
        pending = false;
        const height = Math.ceil(shell.getBoundingClientRect().height);
        if (height < 1 || height === previousHeight) return;
        previousHeight = height;
        window.parent.postMessage({ channel: "console-image-embed-v1", type: "size", height }, window.location.origin);
      });
    };
    window.addEventListener("message", event => {
      const value = event.data;
      if (event.source !== window.parent || event.origin !== window.location.origin || !value
          || typeof value !== "object" || Array.isArray(value) || value.channel !== "console-image-embed-v1") return;
      if (value.type === "dismiss-preview") {
        if (byId("previewDialog").open) byId("previewDialog").close();
        else publishPreviewState(false);
        return;
      }
      if (value.type !== "context") return;
      closePasteMenu();
      closeImageContextMenu();
      if (["dark", "light"].includes(value.theme)) document.documentElement.dataset.theme = value.theme;
      if (["en", "zh-CN"].includes(value.language)) changeLanguage(value.language);
      if (Number.isFinite(value.visibleTop) && value.visibleTop >= 0 && value.visibleTop <= 2000000)
        document.documentElement.style.setProperty("--image-embed-visible-top", `${value.visibleTop}px`);
      if (Number.isFinite(value.visibleHeight) && value.visibleHeight >= 100 && value.visibleHeight <= 10000)
        document.documentElement.style.setProperty("--image-embed-visible-height", `${value.visibleHeight}px`);
      report();
    });
    if (typeof ResizeObserver !== "undefined") new ResizeObserver(report).observe(shell);
    if (typeof MutationObserver !== "undefined") new MutationObserver(report).observe(shell, { childList: true, subtree: true, attributes: true });
    window.addEventListener("resize", report);
    window.parent.postMessage({ channel: "console-image-embed-v1", type: "ready" }, window.location.origin);
    report();
  }
  function validInstruction(value, depth = 0) {
    return value && typeof value === "object" && depth < 3 && value.source === "console" && ["notion", "device"].includes(value.target) && (!value.next || validInstruction(value.next, depth + 1));
  }
  function rememberContinuation(id, instruction) {
    const value = { root, planId: id, instruction };
    continuations.set(continuationKey(id), value);
    try { sessionStorage.setItem(continuationKey(id), JSON.stringify(value)); } catch (_) { /* Keep the continuation in memory when storage is unavailable. */ }
  }
  function readContinuation(id) {
    try {
      const value = continuations.get(continuationKey(id)) || JSON.parse(sessionStorage.getItem(continuationKey(id)) || "null");
      return value?.root === root && value?.planId === id && validInstruction(value.instruction) ? value.instruction : null;
    } catch (_) { return null; }
  }
  function clearContinuation(id) {
    continuations.delete(continuationKey(id));
    try { sessionStorage.removeItem(continuationKey(id)); } catch (_) { /* Optional storage. */ }
  }

  try {
    const theme = localStorage.getItem("codexControl.theme.v1");
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  } catch (_) { /* Theme storage is optional. */ }

  function notice(message, error = false, success = false) {
    setText(byId("operationStatus"), currentText(message));
    byId("operationStatus").dataset.error = String(error);
    byId("operationStatus").dataset.tone = success ? "success" : "normal";
    updateNotionStatus();
  }
  function dimensions(item) {
    const width = Number(item?.width), height = Number(item?.height);
    return Number.isInteger(width) && width > 0 && Number.isInteger(height) && height > 0 ? `${width} × ${height}` : text("尺寸待读取", "Dimensions not read yet");
  }
  function title(item) {
    if (standardNaming() && validStandardType(str(item?.standardType))) return str(item.standardType);
    return str(item?.displayTitle || item?.title || item?.name || item?.path?.split(/[\\/]/).at(-1)) || text("未命名图片", "Untitled image");
  }
  const originalName = item => str(item?.name || item?.path?.split(/[\\/]/).at(-1));
  const groupTitle = item => str(item?.groupTitle) || title(item);
  const variantTitle = item => {
    const value = str(item?.variantLabel);
    const generated = item?.variantExplicit === false && value.match(/^方案\s*([1-9]\d*)$/);
    return generated ? text(value, `Variant ${generated[1]}`) : value || text("未标注方案", "Unlabeled variant");
  };
  const imageKey = item => `${str(item?.space) || "root"}:${str(item?.path)}:${str(item?.sha256)}`;
  const purposeKey = item => str(item?.groupId) || groupTitle(item).normalize("NFC").toLocaleLowerCase();
  function variantNavigation({ key, count, index, label, container, select }) {
    if (count < 2) return null;
    const navigation = node("div", "variant-navigation");
    navigation.setAttribute("role", "group");
    navigation.setAttribute("aria-label", text(`${label}的方案浏览`, `Browse variants of ${label}`));
    const move = (next, action) => {
      if (busy || pendingOperation) return;
      select((next + count) % count);
      [...byId(container).querySelectorAll("button")].find(button => button.dataset.navigatorKey === key && button.dataset.variantNavigate === action)?.focus({ preventScroll: true });
    };
    for (const [action, glyph, offset] of [["previous", "‹", -1], ["next", "›", 1]]) {
      const button = node("button", "variant-arrow", glyph);
      button.type = "button";
      button.dataset.navigatorKey = key;
      button.dataset.variantNavigate = action;
      button.disabled = busy || Boolean(pendingOperation);
      button.setAttribute("aria-label", text(`${label}，${offset < 0 ? "上一个" : "下一个"}方案，当前 ${index + 1} / ${count}`, `${label}, ${offset < 0 ? "previous" : "next"} variant, current ${index + 1} of ${count}`));
      button.addEventListener("click", () => move(index + offset, action));
      if (action === "next") {
        const position = node("span", "variant-position", `${index + 1} / ${count}`);
        position.setAttribute("role", "status");
        position.setAttribute("aria-live", "polite");
        position.setAttribute("aria-label", text(`${label}，第 ${index + 1} 个，共 ${count} 个方案`, `${label}, variant ${index + 1} of ${count}`));
        navigation.append(position);
      }
      navigation.append(button);
    }
    navigation.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key) || event.altKey || event.ctrlKey || event.metaKey
          || !event.target?.dataset?.variantNavigate) return;
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? count - 1 : index + (event.key === "ArrowLeft" ? -1 : 1);
      move(next, event.target.dataset.variantNavigate);
    });
    return navigation;
  }
  function schemeKey(item) {
    const items = Array.isArray(state?.items) ? state.items : [];
    const seen = new Set();
    let current = item;
    while (current?.derivedFromId && !seen.has(current.derivedFromId)) {
      seen.add(current.derivedFromId);
      const parent = items.find(value => str(value.assetId || value.sha256) === current.derivedFromId || value.id === current.derivedFromId);
      if (!parent) break;
      current = parent;
    }
    return str(current?.variantId || current?.assetId || current?.sha256 || current?.path);
  }
  function previewUrl(item) {
    const path = str(item?.previewPath || item?.path);
    if (!path || !root) return "";
    const query = new URLSearchParams({ path, expectedRoot: root });
    if (item?.space === "device") query.set("space", "device");
    return `${endpoint}preview?${query}`;
  }
  function updateControls() {
    for (const id of ["libraryRoot", "deviceRoot", "notionPage", "saveConfig", "syncSource", "syncTarget"]) byId(id).disabled = busy;
    for (const id of ["scanImages", "syncImages", "advancedSyncImages", "imageFiles", "pasteImages", "imagePasteCommand"]) byId(id).disabled = busy || !root || Boolean(pendingOperation);
    for (const id of ["syncSource", "syncTarget"]) byId(id).disabled = busy || Boolean(pendingOperation);
    const advancedIssue = advancedSyncIssue();
    byId("advancedSyncImages").disabled ||= Boolean(advancedIssue);
    setText(byId("advancedSyncHint"), advancedIssue || text("用于设备同步或从 Notion 回读；上方主按钮始终同步到 Notion。", "For device sync or reading images back from Notion. The main button always syncs to Notion."));
    if (busy || pendingOperation || !root) closePasteMenu();
    byId("dropZone").setAttribute("aria-disabled", String(busy || !root || Boolean(pendingOperation)));
    byId("dropZone").tabIndex = busy || !root || pendingOperation ? -1 : 0;
    byId("imageGrid").setAttribute("aria-busy", String(busy));
    byId("operationStatus").dataset.busy = String(busy);
    byId("checkOperation").hidden = !pendingOperation || busy;
    byId("checkOperation").disabled = busy;
    if (pendingOperation) byId("syncImages").disabled = true;
    if (deletionUncertain()) {
      for (const id of ["libraryRoot", "deviceRoot", "notionPage", "saveConfig", "scanImages", "syncImages", "advancedSyncImages", "imageFiles", "pasteImages", "imagePasteCommand", "restoreImages", "reviewApply", "syncSource", "syncTarget"]) byId(id).disabled = true;
      byId("dropZone").setAttribute("aria-disabled", "true");
      byId("dropZone").tabIndex = -1;
      closePasteMenu();
    }
    if (busy || pendingOperation || deletionUncertain()) closeImageContextMenu();
    const undoDelete = byId("undoDelete");
    if (undoDelete) {
      undoDelete.hidden = !deletionUncertain() && state?.lastDeletion?.canRestore !== true;
      undoDelete.disabled = busy || Boolean(pendingOperation);
      setText(undoDelete, deletionUncertain() ? text("核对删除结果", "Check delete result") : text("撤回删除", "Undo delete"));
    }
    byId("restoreImages").hidden = !lastApplied || lastApplied.root !== root;
    byId("restoreImages").disabled = busy || Boolean(pendingOperation);
    for (const id of ["metadataGroupTitle", "metadataStandardType", "metadataVariantLabel", "metadataDerivedFrom"]) byId(id).disabled = busy || Boolean(pendingOperation);
    byId("metadataGroupTitle").disabled ||= standardNaming();
    byId("metadataClose").disabled = busy;
    updateMetadataControls();
    updateNamingControls();
    for (const button of document.querySelectorAll?.("button") || []) if (button.dataset.metadataPath) button.disabled = busy || Boolean(pendingOperation);
    for (const container of [byId("imageGrid"), byId("candidateList")]) {
      for (const button of container.querySelectorAll("button")) if (button.dataset.variantNavigate) button.disabled = busy || Boolean(pendingOperation);
      for (const select of container.querySelectorAll("select")) if (select.dataset.variantSize) select.disabled = busy || Boolean(pendingOperation);
    }
    for (const fieldset of byId("candidateList").querySelectorAll("fieldset")) fieldset.disabled = busy;
    const selected = plan?.candidates?.filter(candidate => actions.has(decisions.get(str(candidate.id)))) || [];
    const unresolved = (plan?.candidates?.length || 0) - selected.length;
    const untyped = selected.filter(candidate => decisions.get(str(candidate.id)) !== "keep" && needsStandardPurpose(candidate)).length;
    byId("reviewApply").disabled = busy || Boolean(pendingOperation) || selected.length === 0 || unresolved !== 0 || untyped !== 0;
    setText(byId("reviewApply"), unresolved ? text(`还有 ${unresolved} 项待选择`, `${unresolved} actions still to choose`) : untyped ? text(`还有 ${untyped} 项待明确用途`, `${untyped} purposes still to choose`) : selected.length ? text(`确认所选 ${selected.length} 项`, `Confirm ${selected.length} selected actions`) : text("先选择处理方式", "Choose an action first"));
    setText(byId("decisionSummary"), selected.length ? text(`已选择 ${selected.length} 项${unresolved ? `，还有 ${unresolved} 项待选择` : ""}${untyped ? `；${untyped} 项请先在方案信息中选择标准用途` : ""}`, `${selected.length} actions selected${unresolved ? `; ${unresolved} still to choose` : ""}${untyped ? `; choose standard purposes for ${untyped} images in Variant details first` : ""}`) : text("重复和替换候选需要你选择处理方式。", "Choose how to handle duplicate and replacement candidates."));
    if (reviewNeedsScan && plan) {
      byId("reviewApply").disabled = true;
      setText(byId("reviewApply"), text("重新检查图片后确认", "Check images again before confirming"));
      setText(byId("decisionSummary"), text("名称已变化，请重新检查图片；原选择已保留。", "Names changed. Check images again; your previous choices are retained."));
    }
    if (deletionUncertain()) {
      byId("reviewApply").disabled = true;
      byId("restoreImages").disabled = true;
      byId("metadataSave").disabled = true;
      byId("metadataSaveOnly").disabled = true;
      byId("organizeNames").disabled = true;
      byId("namingPreview").disabled = true;
      byId("namingApply").disabled = true;
      byId("namingRestore").disabled = true;
    }
    updateNotionStatus();
  }
  async function call(action, { payload, form, params } = {}) {
    const headers = {};
    if (payload !== undefined) headers["Content-Type"] = "application/json";
    const response = await fetch(`${endpoint}${action}${params ? `?${new URLSearchParams(params)}` : ""}`, {
      method: payload !== undefined || form ? "POST" : "GET", headers,
      credentials: "same-origin", mode: "same-origin", cache: "no-store", redirect: "error",
      ...(form ? { body: form } : payload !== undefined ? { body: JSON.stringify(payload) } : {})
    });
    let value;
    try { value = await response.json(); } catch (_) { throw new Error(text("暂时无法读取图片服务，当前图片与选择已保留。", "The image service could not be read. Your images and choices are retained.")); }
    if (!response.ok || value?.ok === false) {
      const code = str(value?.code || value?.error);
      const error = new Error(currentText(errors[code]) || serviceMessage(str(value?.message) || str(value?.error), `这次操作未完成（${response.status}），当前选择已保留。`, `The operation did not finish (${response.status}). Your choices are retained.`, code));
      error.code = code;
      error.httpStatus = response.status;
      throw error;
    }
    return value;
  }
  function assertCurrent(token, expectedRoot) {
    return token === generation && (!expectedRoot || expectedRoot === root);
  }
  async function run(message, task, { deletion = false } = {}) {
    if (busy || deletionUncertain() && !deletion) return;
    busy = true;
    const token = ++generation;
    const expectedRoot = root;
    notice(message);
    updateControls();
    try { await task(token, expectedRoot); }
    catch (error) {
      if (assertCurrent(token, expectedRoot)) {
        if (pendingOperation) pendingOperation.uiStatus = "unknown";
        if (pendingOperation?.metadataJob) {
          rememberMetadataJob({ ...pendingOperation.metadataJob, status: "unknown", message: text(`已保存到本地；同步未完成。${localized(error.message, "zh-CN") || "请继续核对原请求。"}`, `Saved locally; sync did not finish. ${localized(error.message, "en") || "Continue checking the original request."}`) });
          notice(metadataJob.message, true);
        } else notice(error.message || text("这次操作未完成，当前选择已保留。", "The operation did not finish. Your choices are retained."), true);
      }
    }
    finally { if (token === generation) { busy = false; updateControls(); } }
  }
  function rememberDecisions() {
    if (!planId(plan)) return;
    try { sessionStorage.setItem(decisionKey(), JSON.stringify([...decisions])); } catch (_) { /* The server retains the plan. */ }
  }
  function restoreDecisions() {
    const allowed = new Set(plan.candidates.map(candidate => str(candidate.id)));
    try {
      const saved = JSON.parse(sessionStorage.getItem(decisionKey()) || "null");
      if (Array.isArray(saved)) for (const entry of saved) {
        if (Array.isArray(entry) && allowed.has(entry[0]) && actions.has(entry[1])) decisions.set(entry[0], entry[1]);
      }
    } catch (_) { /* Invalid or unavailable optional storage does not change the plan. */ }
  }
  function extractPlan(value) {
    const candidate = value?.plan || value?.pendingPlan || (Array.isArray(value?.candidates) ? value : null);
    return candidate && planId(candidate) && Array.isArray(candidate.candidates) ? candidate : null;
  }
  function acceptState(value, { refill = false } = {}) {
    if (!value || typeof value !== "object") return;
    const nextRoot = str(value.root);
    if (root && nextRoot && nextRoot !== root) throw new Error(currentText(errors.root_changed));
    if (nextRoot) root = nextRoot;
    const changedWithoutProof = state && Array.isArray(value.items) && JSON.stringify(state.items) !== JSON.stringify(value.items)
      && !Object.prototype.hasOwnProperty.call(value, "notionSync") && !value.notion?.syncStatus;
    state = { ...(state || {}), ...value };
    if (changedWithoutProof) { state.notionSync = null; state.notion = { ...(state.notion || {}), syncStatus: null }; }
    setText(byId("rootSummary"), root || text("尚未选择图库", "No library selected"));
    byId("rootSummary").dataset.connected = String(Boolean(root));
    setText(byId("deviceSummary"), str(state.deviceRoot) || text("使用本地图库", "Use the local library"));
    byId("deviceSummary").dataset.connected = String(Boolean(state.deviceRoot || root));
    const connected = state.notionAvailable === true || state.notion?.canAttempt === true || state.notion?.available === true;
    const verified = state.notion?.verified === true || state.notionAvailable === true;
    setText(byId("notionConfigNote"), verified ? text("连接已核验；是否已同步，以当前图片与核验快照是否一致为准。", "Connection verified. Sync status depends on whether the current images match the verified snapshot.") : connected ? text("首次同步会核验页面与附件访问。", "The first sync checks page and attachment access.") : text("目前可保存页面地址；Notion 同步连接尚未就绪。", "You can save the page address. The Notion sync connection is not ready yet."));
    for (const select of [byId("syncSource"), byId("syncTarget")]) {
      const option = select.querySelector('option[value="notion"]');
      option.disabled = !connected;
      setText(option, connected ? "Notion" : text("Notion · 连接待就绪", "Notion · connection not ready"));
      if (select.value === "notion" && !connected) select.value = "console";
    }
    const deviceOption = byId("syncTarget").querySelector('option[value="device"]');
    if (deviceOption) deviceOption.disabled = !state.deviceRoot;
    setText(byId("inboxCount"), `inbox ${Number.isInteger(state.inboxCount) ? state.inboxCount : 0}`);
    if (refill) {
      byId("libraryRoot").value = root;
      byId("deviceRoot").value = str(state.deviceRoot);
      byId("notionPage").value = str(state.notionPage);
    }
    if (!root) byId("locations").open = true;
    const last = state.lastSync;
    const time = str(typeof last === "object" ? last?.completedAt || last?.at || last?.time || last?.appliedAt : last);
    const completionTimes = [time];
    for (const operation of [state.operation, state.notion?.operation]) {
      if (operation?.status === "completed" && (operation.remainingTargets === undefined
          || Array.isArray(operation.remainingTargets) && operation.remainingTargets.length === 0)) completionTimes.push(str(operation.finishedAt));
    }
    const dates = completionTimes.filter(Boolean).map(value => new Date(value)).filter(value => !Number.isNaN(value.getTime()));
    const date = dates.length ? new Date(Math.max(...dates.map(value => value.getTime()))) : null;
    setText(byId("lastSync"), date && !Number.isNaN(date.getTime()) ? text(`上次同步 ${date.toLocaleString("zh-CN", { hour12: false })}`, `Last sync ${date.toLocaleString("en", { hour12: false })}`) : text("尚无同步记录", "No sync recorded yet"));
    renderCollection();
    updateNotionStatus();
  }
  function acceptResponse(value, token, expectedRoot) {
    if (!assertCurrent(token, expectedRoot)) return false;
    if (value.state) acceptState(value.state);
    else if (typeof value.root === "string") acceptState(value);
    const incomingPlan = extractPlan(value) || extractPlan(value.state);
    if (incomingPlan) acceptPlan(incomingPlan);
    return true;
  }
  function acceptPlan(value) {
    if (value.root && value.root !== root) throw new Error(currentText(errors.root_changed));
    const previousId = planId(plan);
    plan = value;
    reviewNeedsScan = false;
    if (previousId !== planId(plan)) decisions = new Map();
    const currentIds = new Set(plan.candidates.map(candidate => str(candidate.id)));
    decisions = new Map([...decisions].filter(([id]) => currentIds.has(id)));
    for (const candidate of plan.candidates) {
      const id = str(candidate.id);
      if (!decisions.has(id) && candidate.status === "new" && !candidate.previousCandidateId) decisions.set(id, "add");
      else if (!decisions.has(id) && defaultReplacement(candidate)) decisions.set(id, "replace");
    }
    restoreDecisions();
    rememberDecisions();
    renderPlan();
  }
  function createThumbnail(item, label) {
    const button = node("button", "thumbnail-button");
    button.type = "button";
    button.dataset.previewPath = str(item?.path);
    button.setAttribute("aria-label", text(`放大查看${label || title(item)}，${dimensions(item)}`, `Preview ${label || title(item)}, ${dimensions(item)}`));
    const url = previewUrl(item);
    if (!url) { button.classList.add("image-unavailable"); button.disabled = true; return button; }
    const image = node("img");
    image.alt = title(item);
    image.loading = "lazy";
    image.decoding = "async";
    image.addEventListener("error", () => { button.classList.add("image-unavailable"); button.disabled = true; });
    image.src = url;
    button.append(image);
    button.addEventListener("click", () => showPreview(item, button));
    button.addEventListener("contextmenu", event => { event.stopPropagation(); showImageContextMenu(event, item); });
    return button;
  }
  function metadataButton(item) {
    if (item?.space === "device") return node("p", "image-path", text("设备副本 · 在本地图库编辑方案信息", "Device copy · edit variant details in the local library"));
    const needsPurpose = standardNaming() && /^inbox[\\/]/i.test(str(item?.path))
      && !validStandardType(str(item?.standardType)) && !validStandardType(str(item?.suggestedStandardType));
    const button = node("button", "metadata-button", needsPurpose ? text("选择用途", "Choose purpose") : text("方案信息", "Variant details"));
    button.type = "button";
    button.dataset.metadataPath = str(item?.path);
    button.disabled = busy || Boolean(pendingOperation) || !item?.path || !item?.sha256;
    button.setAttribute("aria-label", needsPurpose ? text(`选择${title(item)}的标准用途`, `Choose a standard purpose for ${title(item)}`) : standardNaming() ? text(`编辑${title(item)}的标准用途和方案信息`, `Edit standard purpose and variant details for ${title(item)}`) : text(`编辑${title(item)}的方案信息，保留原文件名`, `Edit variant details for ${title(item)}, retaining the original filename`));
    button.addEventListener("click", () => openMetadata(item, button));
    return button;
  }
  function imageDetails(item, path = true) {
    const content = node("div", "image-details");
    content.append(node("p", "image-title", title(item)), node("span", "image-dimensions", dimensions(item)));
    if (path && item.path) content.append(node("p", "image-path", text(`原文件：${str(item.path)}`, `Original file: ${str(item.path)}`)));
    if (item.variantLabel) content.append(node("p", "image-path", `${variantTitle(item)}${item.derivedFromId ? text(" · 派生尺寸", " · Derived size") : item.pendingDerivedFromId ? text(" · 派生来源待同步 / 待关联", " · Source awaiting sync / linking") : ""}`));
    if (item.sha256) {
      const details = node("details", "hash-details");
      details.append(node("summary", "", text("文件指纹", "File fingerprint")), node("code", "", str(item.sha256)));
      content.append(details);
    }
    content.append(metadataButton(item));
    return content;
  }
  function comparisonSide(item, label) {
    const side = node("div", "comparison-side");
    side.append(node("p", "side-label", label));
    if (item) side.append(createThumbnail(item, label), imageDetails(item));
    else side.append(node("div", "empty-comparison", text("还没有对应图片", "No matching image yet")));
    return side;
  }
  function candidateReason(candidate) {
    if (candidate.matchReason === "bytes") return text("文件指纹相同，内容完全一致。可以保留已有图片，避免重复收录。", "The file fingerprints match exactly. Keep the existing image to avoid adding a duplicate.");
    if (candidate.matchReason === "pixels") return text("像素内容相同，可能使用不同格式。请比较后选择保留或替换。", "The pixels match, possibly in different formats. Compare before choosing keep or replace.");
    if (candidate.status === "duplicate") return candidate.incoming?.sha256 && candidate.incoming.sha256 === candidate.existing?.sha256 ? text("文件内容完全相同。可以保留已有图片，避免重复收录。", "The files are identical. Keep the existing image to avoid adding a duplicate.") : text("检测到相同图像内容，可能使用了不同格式；请比较后选择。", "Matching image content was found, possibly in a different format. Compare before choosing.");
    if (candidate.status === "ambiguous") return text("存在多个匹配，请核对标题、尺寸和图片内容，再选择处理方式。", "Several matches were found. Check their titles, dimensions and content before choosing an action.");
    if (candidate.status === "conflict") return text("同标题与尺寸已有图片，内容不同。可以用新图替换，也可以保留为另一方案。", "An image with the same purpose and dimensions already exists, with different content. Replace it or keep another variant.");
    return text("新图片，确认后加入图库。", "New image. It will be added after confirmation.");
  }
  function warningDetails(warnings, language) {
    const lines = warnings.slice(0, 6).map(value => {
      if (typeof value === "string") return localized(serviceMessage(value, "图片未能处理。", "Image could not be processed."), language);
      return `${str(value.path || value.file)} ${localized(serviceMessage(value.error || value.message, "图片未能处理。", "Image could not be processed.", str(value.code)), language)}`;
    });
    if (warnings.length > 6) lines.push(language === "en" ? "More records are retained in this check." : "其余记录保留在本次检查中。");
    return lines.join("\n");
  }
  function candidateGroups(candidates) {
    const groups = new Map();
    for (const candidate of candidates) {
      const item = metadata(candidate.incoming) || metadata(candidate.source);
      const compact = candidate.status === "new" && !metadata(candidate.existing) && !metadata(candidate.target)
        && (!Array.isArray(candidate.matches) || candidate.matches.length === 0);
      const sized = Number.isInteger(item?.width) && item.width > 0 && Number.isInteger(item?.height) && item.height > 0;
      const key = compact && sized ? JSON.stringify([purposeKey(item), item.width, item.height, str(item.space) || "root"]) : `candidate:${str(candidate.id)}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(candidate);
    }
    return groups;
  }
  function renderPlan() {
    const list = byId("candidateList");
    const focus = document.activeElement?.dataset?.candidateId ? { id: document.activeElement.dataset.candidateId, action: document.activeElement.value } : null;
    list.replaceChildren();
    const candidates = plan?.candidates || [];
    const warnings = Array.isArray(plan?.errors) ? plan.errors : [];
    byId("reviewSection").hidden = candidates.length === 0 && warnings.length === 0;
    setText(byId("reviewCount"), text(`${candidates.length} 项待确认`, `${candidates.length} to review`));
    if (embedded) setText(byId("reviewTitle"), state?.inboxCount ? "Inbox" : text("图片确认", "Image review"));
    setReviewExpanded(reviewExpanded);
    const next = readContinuation(planId(plan));
    setText(byId("reviewNote"), next ? text(`确认这些图片后，将自动继续同步到${next.target === "notion" ? " Notion" : "设备文件夹"}${next.next ? "及额外设备文件夹" : ""}。替换仍需确认。`, `After confirmation, sync continues to ${next.target === "notion" ? "Notion" : "the device folder"}${next.next ? " and the additional device folder" : ""}. Replacements still require confirmation.`) : text("每张图片分别选择；确认会处理全部候选。同用途、同尺寸可左右切换，冲突卡保留新旧对照。", "Choose an action for each image; confirmation processes all candidates. Browse images with the same purpose and size using the arrows. Conflicts keep the before/after comparison."));
    byId("planWarnings").hidden = warnings.length === 0;
    setText(byId("planWarnings"), warnings.length ? text(`以下 ${warnings.length} 项未处理：\n${warningDetails(warnings, "zh-CN")}`, `${warnings.length} items could not be processed:\n${warningDetails(warnings, "en")}`) : "");
    for (const [group, groupCandidates] of candidateGroups(candidates)) {
      const selectionKey = `${root}:${planId(plan)}:${group}`;
      const candidate = groupCandidates.find(value => str(value.id) === candidateSelections.get(selectionKey)) || groupCandidates[0];
      candidateSelections.set(selectionKey, str(candidate.id));
      const id = str(candidate.id);
      const incoming = metadata(candidate.incoming) || metadata(candidate.source);
      const existing = metadata(candidate.existing) || metadata(candidate.target);
      const matches = Array.isArray(candidate.matches) ? candidate.matches.filter(metadata) : [];
      const compact = candidate.status === "new" && !existing && matches.length === 0;
      const card = node("article", compact ? "candidate-card compact-new" : "candidate-card");
      card.dataset.status = str(candidate.status);
      card.dataset.candidateId = id;
      const heading = node("div", "candidate-heading");
      heading.append(node("h3", "", title(incoming || existing)), node("span", "match-tag", currentText(statusLabels[candidate.status]) || text("请比较图片", "Compare images")));
      const currentPurpose = groupTitle(incoming || existing);
      const samePurpose = (Array.isArray(state?.items) ? state.items : []).filter(item => incoming?.groupId && item.groupId ? incoming.groupId === item.groupId : groupTitle(item).normalize("NFC").toLocaleLowerCase() === currentPurpose.normalize("NFC").toLocaleLowerCase());
      const purposeSchemes = new Set(samePurpose.map(schemeKey)).size;
      const purpose = node("p", "candidate-purpose", text(`用途：${currentPurpose}${purposeSchemes ? ` · 已有 ${purposeSchemes} 个方案` : ""}`, `Purpose: ${currentPurpose}${purposeSchemes ? ` · ${purposeSchemes} existing variants` : ""}`));
      const comparison = node("div", compact ? "compact-preview" : "comparison");
      if (compact) {
        comparison.append(createThumbnail(incoming), node("span", "image-dimensions", dimensions(incoming)));
        if (incoming?.variantLabel) comparison.append(node("p", "compact-variant-label", `${variantTitle(incoming)}${incoming.derivedFromId ? text(" · 派生尺寸", " · Derived size") : incoming.pendingDerivedFromId ? text(" · 派生来源待同步 / 待关联", " · Source awaiting sync / linking") : ""}`));
        comparison.append(metadataButton(incoming));
      }
      else comparison.append(comparisonSide(incoming, text("新图片 / 同步来源", "Incoming image / sync source")));
      if (!compact && !existing && matches.length) {
        const side = node("div", "comparison-side");
        side.append(node("p", "side-label", text(`已有图片 / ${matches.length} 张匹配`, `Existing images / ${matches.length} matches shown`)));
        for (const match of matches) {
          const matchView = node("div", "match-preview");
          matchView.append(createThumbnail(match, text("已有图片", "Existing image")), imageDetails(match));
          side.append(matchView);
        }
        comparison.append(side);
      } else if (!compact) comparison.append(comparisonSide(existing, text("已有图片 / 同步目标", "Existing image / sync destination")));
      const choices = node("fieldset", "decision-choices");
      choices.append(node("legend", "visually-hidden", text(`${title(incoming || existing)}的处理方式`, `Action for ${title(incoming || existing)}`)));
      const identical = ["bytes", "pixels"].includes(candidate.matchReason) || candidate.status === "duplicate";
      const addLabel = identical ? text("另存副本", "Save a copy") : text("保留为另一方案", "Keep as another variant");
      const options = existing ? [["replace", text("用新图替换", "Replace with new image")], ["keep", text("保留已有", "Keep existing")], ["add", addLabel]] : matches.length ? [["keep", text("保留现状", "Keep current")], ["add", addLabel]] : [["add", text("加入图库", "Add to library")], ["keep", text("暂不加入", "Do not add")]];
      for (const [action, label] of options) {
        if (Array.isArray(candidate.actions) && !candidate.actions.includes(action)) continue;
        const choice = node("label", "decision-choice");
        const input = node("input");
        input.type = "radio";
        input.name = `image-decision-${id}`;
        input.value = action;
        input.dataset.candidateId = id;
        input.checked = decisions.get(id) === action;
        input.addEventListener("change", () => { decisions.set(id, action); rememberDecisions(); updateControls(); });
        choice.append(input, node("span", "", label));
        choices.append(choice);
      }
      card.append(heading, purpose, comparison);
      if (standardNaming()) card.append(node("p", "candidate-standard-name", incoming?.standardName && !needsStandardPurpose(candidate) ? text(`${incoming.standardType ? "采用后" : `建议用途 ${str(incoming.suggestedStandardType)} · 确认采用后`}：${str(incoming.standardName)}`, `${incoming.standardType ? "After confirmation" : `Suggested purpose ${str(incoming.suggestedStandardType)} · after confirmation`}: ${str(incoming.standardName)}`) : text("下一步：点击「选择用途」，再确认加入或替换。", "Next: click Choose purpose, then confirm adding or replacing.")));
      const navigation = variantNavigation({ key: selectionKey, count: groupCandidates.length, index: groupCandidates.indexOf(candidate),
        label: `${currentPurpose}，${dimensions(incoming)}`, container: "candidateList", select: index => {
          candidateSelections.set(selectionKey, str(groupCandidates[index].id));
          renderPlan();
        } });
      if (navigation) card.append(navigation);
      if (!compact) card.append(node("p", "candidate-reason", candidateReason(candidate)));
      card.append(choices);
      card.addEventListener("contextmenu", event => showImageContextMenu(event, incoming));
      list.append(card);
    }
    if (focus) [...list.querySelectorAll("input")].find(input => input.dataset.candidateId === focus.id && input.value === focus.action)?.focus({ preventScroll: true });
    updateControls();
  }
  function renderCollection() {
    const items = Array.isArray(state?.items) ? state.items : [];
    const query = byId("imageSearch").value.trim().toLocaleLowerCase();
    const groups = new Map();
    for (const item of items) {
      if (!metadata(item)) continue;
      const id = purposeKey(item);
      if (!groups.has(id)) groups.set(id, { id, title: groupTitle(item), items: [] });
      groups.get(id).items.push(item);
    }
    const filtered = [...groups.values()].filter(group => !query || group.items.some(item => `${group.title} ${title(item)} ${str(item.title)} ${str(item.variantLabel)} ${variantTitle(item)} ${dimensions(item)} ${str(item.path)}`.toLocaleLowerCase().includes(query)));
    setText(byId("libraryCount"), text(`${items.length} 张`, `${items.length} images`));
    setText(byId("collectionNote"), query ? text(`找到 ${filtered.length} 组，组内所有尺寸和方案均可查看。`, `${filtered.length} groups found. All sizes and variants are available within each group.`) : text(`${groups.size} 组 · ${items.length} 张图片。按用途与标题分组，选择尺寸和方案查看原图。`, `${groups.size} groups · ${items.length} images. Grouped by purpose and title; choose a size and variant to view the original.`));
    byId("imageGrid").replaceChildren();
    for (const group of filtered) byId("imageGrid").append(renderGroup(group));
    byId("emptyState").hidden = filtered.length !== 0;
    setText(byId("emptyState").querySelector("h3"), query ? text("没有匹配的图片", "No matching images") : text("你的图片，从这里开始", "Your images start here"));
    setText(byId("emptyState").querySelector("p"), query ? text("换一个标题或尺寸试试。", "Try another title or size.") : text("保存图库位置，放入图片，再点「更新本地」。", "Save a library location, add images, then select Update local."));
  }
  function renderGroup(group) {
    const key = `${root}:${group.id}`;
    const sizes = [...new Set(group.items.map(dimensions))];
    const selection = groupSelections.get(key) || { size: sizes[0], image: imageKey(group.items[0]) };
    if (!sizes.includes(selection.size)) selection.size = dimensions(group.items.find(item => imageKey(item) === selection.image) || group.items[0]);
    const variants = group.items.filter(item => dimensions(item) === selection.size);
    const selected = variants.find(item => imageKey(item) === selection.image) || variants[0];
    selection.image = imageKey(selected);
    groupSelections.set(key, selection);
    const card = node("article", "asset-group-card");
    card.dataset.groupId = group.id;
    card.dataset.currentPath = str(selected.path);
    const header = node("div", "asset-group-header");
    const schemeCount = new Set(group.items.map(schemeKey)).size;
    header.append(node("h3", "", group.title), node("span", "asset-group-stats", text(`${schemeCount} 方案 · ${sizes.length} 尺寸`, `${schemeCount} variants · ${sizes.length} sizes`)));
    const sizeField = node("label", "asset-size-field");
    const select = node("select");
    select.dataset.variantSize = "true";
    select.disabled = busy || Boolean(pendingOperation);
    select.setAttribute("aria-label", text(`${group.title}的尺寸`, `Size for ${group.title}`));
    for (const size of sizes) {
      const option = node("option", "", text(`${size} · ${group.items.filter(item => dimensions(item) === size).length} 张`, `${size} · ${group.items.filter(item => dimensions(item) === size).length} images`));
      option.value = size;
      select.append(option);
    }
    select.value = selection.size;
    select.addEventListener("change", () => {
      if (busy || pendingOperation) return;
      selection.size = select.value;
      const previousVariant = schemeKey(selected);
      const sameVariant = group.items.find(item => dimensions(item) === select.value && previousVariant && schemeKey(item) === previousVariant);
      selection.image = sameVariant ? imageKey(sameVariant) : "";
      renderCollection();
      [...byId("imageGrid").querySelectorAll("article")].find(element => element.dataset.groupId === group.id)?.querySelector("select")?.focus({ preventScroll: true });
    });
    sizeField.append(node("span", "", text("尺寸", "Size")), select);
    const preview = node("div", "asset-group-preview");
    preview.append(createThumbnail(selected), node("p", "asset-variant-summary", `${variantTitle(selected)} · ${dimensions(selected)}`));
    if (selected.derivedFromId) preview.append(node("span", "derivative-badge", text("派生尺寸 · 已关联来源", "Derived size · source linked")));
    else if (selected.pendingDerivedFromId) preview.append(node("span", "derivative-badge", text("派生来源待同步 / 待关联", "Source awaiting sync / linking")));
    if (selected.hasTransparency === true) preview.append(node("span", "transparency-badge", text("含透明区域", "Contains transparency")));
    const navigation = variantNavigation({ key, count: variants.length, index: variants.indexOf(selected),
      label: `${group.title}，${selection.size}`, container: "imageGrid", select: index => {
        selection.image = imageKey(variants[index]);
        renderCollection();
      } });
    if (navigation) preview.append(navigation);
    const footer = node("div", "asset-group-footer");
    footer.append(node("p", "image-path", text(`原文件：${str(selected.path)}`, `Original file: ${str(selected.path)}`)), metadataButton(selected));
    card.append(header, sizeField, preview, footer);
    card.addEventListener("contextmenu", event => showImageContextMenu(event, selected));
    return card;
  }
  function publishPreviewState(open) {
    if (embedded) window.parent.postMessage({ channel: "console-image-embed-v1", type: "preview", open }, window.location.origin);
  }
  function showPreview(item, trigger) {
    previewFocus = trigger;
    previewItem = item;
    const image = node("img");
    image.alt = title(item);
    image.src = previewUrl(item);
    byId("previewTitle").textContent = title(item);
    setText(byId("previewMeta"), `${dimensions(item)}${item.path ? ` · ${str(item.path)}` : ""}`);
    byId("previewImageWrap").replaceChildren(image);
    byId("previewDialog").showModal();
    publishPreviewState(true);
  }
  function openMetadata(item, trigger) {
    if (busy || pendingOperation || deletionUncertain() || byId("namingDialog").open || !item?.path || !item?.sha256 || item.space === "device") return;
    metadataTarget = { ...item, expectedRoot: root, expectedPageId: configuredPageId(), expectedDeviceRoot: str(state?.deviceRoot),
      indexed: (state?.items || []).some(current => current.path === item.path && current.sha256 === item.sha256 && current.space !== "device") };
    metadataFocus = trigger;
    setText(byId("metadataOriginal"), text(`原文件：${str(item.path)} · ${dimensions(item)}`, `Original file: ${str(item.path)} · ${dimensions(item)}`));
    byId("metadataGroupTitle").value = groupTitle(item);
    fillStandardTypes(byId("metadataStandardType"), str(item.standardType || item.suggestedStandardType));
    byId("metadataVariantLabel").value = str(item.variantLabel);
    fillDerivedSources(item);
    const sources = byId("metadataDerivedFrom");
    metadataBaseline = standardNaming() ? JSON.stringify([str(item.standardType), byId("metadataVariantLabel").value.trim(), sources.value]) : metadataValues();
    updateMetadataName();
    metadataJob = null;
    try {
      const saved = JSON.parse(sessionStorage.getItem(metadataJobKey(metadataTarget)) || "null");
      if (saved?.root === root && saved.path === item.path && saved.sha256 === item.sha256) {
        metadataJob = saved;
        metadataJob.message = saved.messageZh && saved.messageEn ? text(saved.messageZh, saved.messageEn)
          : serviceMessage(saved.message, "已保留本地修改，请核对同步结果。", "Local changes are retained. Check the sync result.");
      }
    } catch (_) { /* Optional saved sync status. */ }
    setText(byId("metadataStatus"), metadataDirty() ? text("标准用途建议尚未保存，确认后才会采用。", "The suggested purpose is not saved yet. It is used only after confirmation.") : metadataJob?.message || text("尚无未保存的修改。", "No unsaved changes."));
    byId("metadataStatus").dataset.error = "false";
    byId("metadataDialog").showModal();
    updateMetadataControls();
    (standardNaming() ? byId("metadataStandardType") : byId("metadataGroupTitle")).focus();
  }
  function fillDerivedSources(item) {
    const sources = byId("metadataDerivedFrom");
    sources.replaceChildren();
    const none = node("option", "", text("原始素材 / 未关联来源", "Original asset / no linked source"));
    none.value = "";
    sources.append(none);
    const ids = new Set();
    for (const source of Array.isArray(state?.items) ? state.items : []) {
      const id = str(source.assetId || source.sha256 || source.id);
      if (!id || id === str(item.assetId || item.sha256) || ids.has(id)) continue;
      ids.add(id);
      const option = node("option", "", `${groupTitle(source)} · ${variantTitle(source)} · ${dimensions(source)} · ${originalName(source)}`);
      option.value = id;
      sources.append(option);
    }
    if (item.derivedFromId && !ids.has(item.derivedFromId)) {
      const existing = node("option", "", text("已关联的来源（当前图库未显示）", "Linked source (not shown in the current library)"));
      existing.value = str(item.derivedFromId);
      sources.append(existing);
    }
    if (!item.derivedFromId && item.pendingDerivedFromId) {
      const pending = node("option", "", text("派生来源待同步 / 待关联（保留现有记录）", "Source awaiting sync / linking (retain existing record)"));
      pending.value = "__pending_source__";
      sources.append(pending);
    }
    sources.value = !item.derivedFromId && item.pendingDerivedFromId ? "__pending_source__" : str(item.derivedFromId);
  }
  function updatePlanMetadata(item, previous = item) {
    if (!plan || !item) return;
    const patch = current => current && current.path === previous.path && current.sha256 === item.sha256 && (current.space || "root") === (item.space || "root") ? { ...current, ...item } : current;
    for (const candidate of plan.candidates) {
      candidate.incoming = patch(candidate.incoming);
      candidate.existing = patch(candidate.existing);
      if (Array.isArray(candidate.matches)) candidate.matches = candidate.matches.map(patch);
    }
    renderPlan();
  }
  function invalidateReviewAfterNaming(value) {
    if (plan && value && Object.prototype.hasOwnProperty.call(value, "plan") && value.plan === null) reviewNeedsScan = true;
  }
  async function saveMetadata(event, synchronize = true) {
    event.preventDefault();
    if (!metadataTarget || metadataTarget.expectedRoot !== root || busy) return;
    if (pendingOperation) {
      if (synchronize && pendingOperation.metadataJob && pendingOperation.metadataJob.path === metadataTarget.path && pendingOperation.metadataJob.sha256 === metadataTarget.sha256) await resumeOperation();
      return;
    }
    if (synchronize && !requireSavedLocations()) return;
    const dirty = metadataDirty();
    if (!dirty && (!synchronize || !metadataJob || ["completed", "local", "inbox", "stale"].includes(metadataJob.status))) return;
    if (!dirty && metadataJob.planId && planId(plan) === metadataJob.planId) {
      byId("metadataDialog").close();
      setReviewExpanded(true);
      byId("reviewSection").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    const snapshot = { root, path: metadataTarget.path, sha256: metadataTarget.sha256, pageId: metadataTarget.expectedPageId,
      deviceRoot: metadataTarget.expectedDeviceRoot, indexed: metadataTarget.indexed };
    const payload = { expectedRoot: root, path: metadataTarget.path, sha256: metadataTarget.sha256, space: "root", groupTitle: metadataPurpose(), variantLabel: byId("metadataVariantLabel").value.trim() };
    if (byId("metadataDerivedFrom").value !== "__pending_source__") payload.derivedFromId = byId("metadataDerivedFrom").value;
    if (!payload.groupTitle || !payload.variantLabel) return;
    if (standardNaming() && !validStandardType(payload.groupTitle)) return;
    await run(dirty ? text("正在保存方案信息…", "Saving variant details…") : text("正在同步已保存修改…", "Syncing saved changes…"), async (token, expectedRoot) => {
      setText(byId("metadataStatus"), dirty ? text("正在保存…", "Saving…") : text("正在同步已保存修改…", "Syncing saved changes…"));
      byId("metadataStatus").dataset.error = "false";
      try {
        requireMetadataScope(snapshot, token, expectedRoot);
        if (dirty) {
          const value = await call("metadata", { payload });
          const item = metadata(value.item);
          const renamed = metadata(value.renamed);
          let savedPath = snapshot.path;
          if (renamed && Object.keys(renamed).length) {
            if (!snapshot.indexed || renamed.from !== snapshot.path || renamed.to !== item?.path || renamed.sha256 !== snapshot.sha256 || !safeImagePath(renamed.to)) throw new Error(text("改名回执与本次原图不一致，已停止同步，填写内容已保留。", "The rename receipt does not match this original. Sync stopped; your entries are retained."));
            savedPath = renamed.to;
          }
          if (item && (item.path !== savedPath || item.sha256 !== snapshot.sha256)) throw new Error(text("保存回执对应的原图已改变，已停止同步，填写内容已保留。", "The original in the save receipt changed. Sync stopped; your entries are retained."));
          const savedSnapshot = { ...snapshot, path: savedPath };
          requireMetadataScope(savedSnapshot, token, expectedRoot, value.state || state);
          if (!acceptResponse(value, token, expectedRoot)) return;
          if (snapshot.indexed && savedPath !== snapshot.path) invalidateReviewAfterNaming(value.state);
          if (item) { updatePlanMetadata(item, snapshot); metadataTarget = { ...metadataTarget, ...item }; }
          if (savedPath !== snapshot.path) {
            try { sessionStorage.removeItem(metadataJobKey(snapshot)); } catch (_) { /* Optional saved-sync status. */ }
            setText(byId("metadataOriginal"), text(`当前文件：${savedPath} · ${dimensions(item)}`, `Current file: ${savedPath} · ${dimensions(item)}`));
          }
          updateMetadataName();
          metadataBaseline = metadataValues();
          const targets = configuredPageId() ? ["notion"] : [];
          rememberMetadataJob({ ...savedSnapshot, uiMode: "notion", annotationFingerprint: annotationFingerprint(value.item || metadataTarget), targets, completed: [], status: !snapshot.indexed ? "inbox" : targets.length ? "saved" : "local",
            message: !snapshot.indexed ? text("已保存到 Inbox，确认入库后再同步；尚未发布这张图片。", "Saved to Inbox. Confirm adding it to the library before syncing; this image has not been published.") : targets.length ? text("已更新本地，Notion 待同步。", "Local folder updated; Notion pending sync.") : text("已更新本地；尚未配置 Notion 目标。", "Local folder updated. No Notion destination is configured.") });
        }
      } catch (error) {
        setText(byId("metadataStatus"), error.message || text("保存未完成，填写内容已保留。", "Saving did not finish. Your entries are retained."));
        byId("metadataStatus").dataset.error = "true";
        throw error;
      }
      if (!synchronize || ["local", "inbox"].includes(metadataJob.status)) { notice(metadataJob.message, false, true); return; }
      await syncMetadataTargets(metadataJob, token, expectedRoot);
    });
  }
  async function syncMetadataTargets(job, token, expectedRoot) {
    try {
      requireMetadataScope(job, token, expectedRoot);
      const target = job.targets.find(value => !job.completed.includes(value));
      if (!target) {
        rememberMetadataJob({ ...job, status: "completed", planId: "", message: job.uiMode === "notion" ? text("已更新本地，并完成同步到 Notion。", "Local folder updated and sync to Notion completed.") : text("已保存，并同步到全部已配置位置。", "Saved and synced to all configured destinations.") });
        notice(metadataJob.message, false, true);
        return;
      }
      if (target === "notion" && state?.notionAvailable !== true && state?.notion?.canAttempt !== true && state?.notion?.available !== true) throw new Error(text("Notion 连接尚未就绪，可在连接恢复后同步已保存修改。", "Notion is not ready. Sync the saved changes when the connection is available."));
      if (job.uiMode !== "notion") {
        byId("syncSource").value = "console";
        byId("syncTarget").value = job.targets.length > 1 ? "all" : target;
      }
      rememberMetadataJob({ ...job, status: "syncing", planId: "", message: text(`已保存到本地，正在同步${target === "notion" ? "到 Notion" : "到设备文件夹"}…`, `Saved locally; syncing to ${target === "notion" ? "Notion" : "the device folder"}…`) });
      await dispatchSync("console", target, token, expectedRoot, null, metadataJob, job.uiMode === "notion" ? "notion" : "legacy");
    } catch (error) {
      const current = metadataJob || job;
      const uncertain = Boolean(pendingOperation?.metadataJob);
      rememberMetadataJob({ ...current, status: error.code === "metadata_scope_changed" ? "stale" : uncertain ? "unknown" : "failed", message: text(`已保存到本地；${current.completed.length ? "部分位置已同步，" : ""}同步未完成。${localized(error.message, "zh-CN") || "请重试。"}${uncertain ? "请继续核对原请求。" : ""}`, `Saved locally; ${current.completed.length ? "some destinations synced; " : ""}sync did not finish. ${localized(error.message, "en") || "Please try again."}${uncertain ? " Continue checking the original request." : ""}`) });
      notice(metadataJob.message, true);
    }
  }
  async function completeMetadataTarget(job, target, token, expectedRoot) {
    requireMetadataScope(job, token, expectedRoot);
    rememberMetadataJob({ ...job, completed: [...new Set([...job.completed, target])], status: "saved", planId: "", message: text("已保存到本地，正在完成后续同步…", "Saved locally; completing the remaining sync…") });
    await syncMetadataTargets(metadataJob, token, expectedRoot);
  }
  async function acceptMetadataDeviceResult(value, job, token, expectedRoot) {
    requireMetadataScope(job, token, expectedRoot, value.state || state);
    const syncPlan = extractPlan(value);
    if (!syncPlan || syncPlan.root !== job.root || syncPlan.deviceRoot !== job.deviceRoot || syncPlan.direction !== "to-device") {
      const error = new Error(text("设备同步计划的图库、目标位置或方向与本次保存不一致，已停止应用，请重新核对位置。", "The device plan's library, destination or direction does not match this save. Applying stopped; check the locations again."));
      error.code = "metadata_scope_changed";
      throw error;
    }
    if (value.state) acceptState(value.state);
    const count = syncPlan?.candidates?.length || 0;
    if (count) {
      acceptPlan(syncPlan);
      rememberMetadataJob({ ...job, status: "review", planId: planId(syncPlan), message: text("已保存到本地；设备同步有待确认的图片，请查看后确认。", "Saved locally. Device sync has images to review and confirm.") });
      if (!syncPlan.errors?.length && syncPlan.candidates.every(canAutomaticallyAdd)) {
        await commitBatch({ planId: planId(syncPlan), expectedRoot, decisions: syncPlan.candidates.map(candidate => ({ id: str(candidate.id), action: "add" })) }, token, expectedRoot);
        return;
      }
      setReviewExpanded(true);
      notice(metadataJob.message);
      return;
    }
    if (value.metadataSync?.status !== "completed" || Number(value.metadataSync?.unresolved) > 0 || syncPlan?.errors?.length) throw new Error(serviceMessage(value.message, "设备方案信息尚未完整同步，请重新核对。", "Device variant details have not fully synced. Check again."));
    await completeMetadataTarget(job, "device", token, expectedRoot);
  }
  const namingDraftKey = () => `console-image-naming-draft:${root}`;
  const libraryIdentity = value => JSON.stringify((Array.isArray(value?.items) ? value.items : []).map(item => [imageKey(item), annotationFingerprint(item)]).sort((left, right) => left[0].localeCompare(right[0])));
  function namingSnapshot() {
    return { root, deviceRoot: str(state?.deviceRoot), pageId: configuredPageId(), standardNaming: standardNaming(), identity: libraryIdentity(state), items: (state?.items || []).map(item => ({ ...item })),
      fields: [byId("libraryRoot").value, byId("deviceRoot").value, byId("notionPage").value] };
  }
  function namingScopeMatches(scope, value = state, after = false) {
    return scope && root === scope.root && value?.root === scope.root && str(value.deviceRoot) === scope.deviceRoot
      && (pageId(value.notionPage) || pageId(value.notion?.pageId)) === scope.pageId
      && [byId("libraryRoot").value, byId("deviceRoot").value, byId("notionPage").value].every((field, index) => field === scope.fields[index])
      && (after || (value.standardNaming === true) === scope.standardNaming && libraryIdentity(value) === scope.identity);
  }
  function namingChoices() {
    return (state?.items || []).map(item => ({ path: item.path, sha256: item.sha256, assetType: namingDrafts.get(imageKey(item)) || "" }));
  }
  function namingChoicesMatch() {
    const choices = namingChoices();
    return namingPlan?.candidates?.length === choices.length && namingPlan.candidates.every(candidate => choices.some(choice => choice.path === candidate.fromPath && choice.sha256 === candidate.sha256 && choice.assetType === candidate.assetType));
  }
  function updateNamingControls() {
    const available = standardTypes().length > 0;
    byId("organizeNames").hidden = !available;
    byId("organizeNames").disabled = busy || Boolean(pendingOperation) || !state?.items?.length;
    for (const select of byId("namingList").querySelectorAll("select")) select.disabled = busy || Boolean(pendingOperation);
    byId("namingClose").disabled = busy;
    const entries = namingChoices();
    byId("namingPreview").disabled = busy || Boolean(pendingOperation) || !entries.length || entries.some(entry => !validStandardType(entry.assetType));
    byId("namingApply").disabled = busy || Boolean(pendingOperation) || namingPlan?.canApply !== true || Boolean(namingPlan?.errors?.length)
      || entries.some(entry => !validStandardType(entry.assetType)) || !namingScopeMatches(namingScope) || !namingChoicesMatch();
    byId("namingRestore").hidden = !planId(state?.lastNaming) || state.lastNaming?.restored === true || state.lastNaming?.status === "restored";
    byId("namingRestore").disabled = busy || Boolean(pendingOperation);
  }
  function rememberNamingDraft() {
    try { sessionStorage.setItem(namingDraftKey(), JSON.stringify([...namingDrafts])); } catch (_) { /* Keep draft choices in memory. */ }
  }
  function renderNamingList() {
    const list = byId("namingList");
    const focusKey = document.activeElement?.dataset?.namingKey;
    list.replaceChildren();
    for (const item of state?.items || []) {
      const key = imageKey(item);
      const candidate = namingPlan?.candidates?.find(candidate => candidate.fromPath === item.path && candidate.sha256 === item.sha256);
      const row = node("div", "naming-row"); row.dataset.namingPath = str(item.path);
      const content = node("div", "naming-row-content");
      content.append(node("p", "naming-original", str(item.path)), node("span", "image-dimensions", `${dimensions(item)} · ${variantTitle(item)}`));
      const select = node("select"); select.dataset.namingKey = key;
      select.setAttribute("aria-label", text(`${originalName(item)}的标准用途`, `Standard purpose for ${originalName(item)}`));
      fillStandardTypes(select, namingDrafts.get(key));
      const target = node("p", "naming-target", candidate ? `→ ${str(candidate.targetPath || candidate.target)}` : standardName(item, select.value) ? `→ ${standardName(item, select.value)}` : text("请选择标准用途", "Choose a standard purpose"));
      if (candidate?.error) { setText(target, serviceMessage(candidate.error, "此名称尚未就绪，请重新预览。", "This filename is not ready. Preview again.")); target.dataset.error = "true"; }
      select.addEventListener("change", () => {
        if (busy || pendingOperation) return;
        namingDrafts.set(key, select.value); rememberNamingDraft(); namingPlan = null; namingScope = null;
        setText(byId("namingStatus"), text("用途选择尚未应用，请先预览标准名称。", "Purpose choices have not been applied. Preview the standard names first."));
        renderNamingList(); updateNamingControls();
      });
      row.append(createThumbnail(item), content, select, target); list.append(row);
    }
    if (focusKey) [...list.querySelectorAll("select")].find(select => select.dataset.namingKey === focusKey)?.focus({ preventScroll: true });
  }
  function openNaming(event) {
    if (busy || pendingOperation || deletionUncertain() || !root || byId("metadataDialog").open || byId("previewDialog").open || !standardTypes().length) return;
    if (!requireSavedLocations()) return;
    namingFocus = event?.target;
    let saved;
    try { saved = JSON.parse(sessionStorage.getItem(namingDraftKey()) || "null"); } catch (_) { /* Optional draft storage. */ }
    namingDrafts = new Map(Array.isArray(saved) ? saved.filter(entry => Array.isArray(entry) && entry.length === 2 && validStandardType(entry[1])) : []);
    const savedKeys = new Set(namingDrafts.keys());
    for (const item of state?.items || []) if (!namingDrafts.has(imageKey(item))) namingDrafts.set(imageKey(item), validStandardType(str(item.standardType || item.suggestedStandardType)) ? item.standardType || item.suggestedStandardType : "");
    const restored = state?.namingPlan;
    namingPlan = restored?.kind === "naming" && restored.status === "review" && Array.isArray(restored.candidates) ? restored : null;
    if (namingPlan) for (const candidate of namingPlan.candidates) {
      const item = (state.items || []).find(item => item.path === candidate.fromPath && item.sha256 === candidate.sha256);
      if (item && !savedKeys.has(imageKey(item))) namingDrafts.set(imageKey(item), candidate.assetType);
    }
    namingScope = namingPlan ? namingSnapshot() : null;
    if (namingPlan && !namingChoicesMatch()) { namingPlan = null; namingScope = null; }
    setText(byId("namingStatus"), namingPlan ? text("已恢复名称预览，确认后才会整理文件。", "Name preview restored. Files change only after confirmation.") : text("先明确标准用途，再预览旧名称与新名称。", "Choose standard purposes, then preview the old and new names."));
    byId("namingStatus").dataset.error = "false";
    renderNamingList(); updateNamingControls(); byId("namingDialog").showModal();
    (byId("namingList").querySelector("select") || byId("namingClose")).focus();
  }
  async function previewNaming() {
    if (busy || pendingOperation || !requireSavedLocations()) return;
    const entries = namingChoices();
    if (!entries.length || entries.some(entry => !validStandardType(entry.assetType))) return;
    const snapshot = namingSnapshot();
    await run(text("正在预览标准名称…", "Preparing standard name preview…"), async (token, expectedRoot) => {
      try {
        const value = await call("naming-plan", { payload: { expectedRoot, entries } });
        if (!assertCurrent(token, expectedRoot) || !namingScopeMatches(snapshot, value.state || state)) throw new Error(text("图库、同步位置或原图已改变，名称预览已停止，请重新读取。", "The library, sync locations or original changed. Name preview stopped; reload the current state."));
        if (value.kind !== "naming" || !planId(value) || !Array.isArray(value.candidates)
            || value.candidates.length !== entries.length || !entries.every(entry => value.candidates.filter(candidate => candidate.fromPath === entry.path && candidate.sha256 === entry.sha256 && candidate.assetType === entry.assetType).length === 1)
            || value.canApply === true && value.candidates.some(candidate => !["rename", "unchanged"].includes(candidate.status) || !safeImagePath(candidate.targetPath))) throw new Error(text("名称预览与本次图片不一致，尚未应用更改。", "The name preview does not match these images. No changes were applied."));
        if (value.state) acceptState(value.state);
        namingPlan = value; namingScope = snapshot; rememberNamingDraft(); renderNamingList();
        const message = value.canApply === true ? text("请核对旧名称 → 新名称，确认后才会整理文件。", "Check old name → new name. Files change only after confirmation.") : text("部分名称存在冲突，尚未应用；请检查下方记录并重新预览。", "Some names conflict. Nothing was applied; check the details below and preview again.");
        setText(byId("namingStatus"), message); byId("namingStatus").dataset.error = String(value.canApply !== true);
        notice(message, value.canApply !== true);
      } catch (error) { setText(byId("namingStatus"), error.message); byId("namingStatus").dataset.error = "true"; throw error; }
    });
  }
  function validateNamingReceipt(value, snapshot, expectedId, expectedCandidates = null) {
    if (planId(value) !== expectedId || !Array.isArray(value.results) || !namingScopeMatches(snapshot, value.state, true)) throw new Error(text("名称整理回执与本次图库或计划不一致，请保留原计划并核对。", "The naming receipt does not match this library or plan. Retain the plan and check again."));
    const results = value.results;
    for (const result of results) {
      const source = snapshot.items.find(item => item.path === result.from && item.sha256 === result.sha256);
      const target = value.state.items?.find(item => item.path === result.to && item.sha256 === result.sha256);
      const expected = expectedCandidates?.find(candidate => candidate.fromPath === result.from && candidate.targetPath === result.to && candidate.sha256 === result.sha256);
      if (!source || !target || !safeImagePath(result.to)
          || source.variantId && source.variantId !== target.variantId || source.derivedFromId && source.derivedFromId !== target.derivedFromId
          || expectedCandidates && (!expected || target.standardType !== expected.assetType || target.standardName !== expected.standardName)) throw new Error(text("改名结果与预览的原图不一致，未采用这份迟到回执。", "The rename result does not match the previewed original. This stale receipt was not accepted."));
    }
    if (expectedCandidates?.some(candidate => candidate.status === "rename" && !results.some(result => result.from === candidate.fromPath && result.to === candidate.targetPath && result.sha256 === candidate.sha256))) throw new Error(text("部分改名结果尚未核对完成，请保留原计划并继续核对。", "Some rename results are not verified yet. Retain the plan and continue checking."));
  }
  async function applyNaming() {
    if (busy || pendingOperation || namingPlan?.canApply !== true || namingPlan.errors?.length) return;
    if (!requireSavedLocations()) return;
    if (namingChoices().some(entry => !validStandardType(entry.assetType)) || !namingScopeMatches(namingScope) || !namingChoicesMatch()) return;
    const preview = namingPlan, snapshot = namingScope;
    await run(text("正在整理已确认的文件名…", "Applying confirmed filenames…"), async (token, expectedRoot) => {
      try {
        const value = await call("naming-apply", { payload: { expectedRoot, planId: planId(preview) } });
        if (!assertCurrent(token, expectedRoot)) return;
        validateNamingReceipt(value, snapshot, planId(preview), preview.candidates);
        invalidateReviewAfterNaming(value.state); acceptState(value.state); namingPlan = null; namingScope = null;
        namingDrafts = new Map((state.items || []).map(item => [imageKey(item), str(item.standardType)])); rememberNamingDraft(); renderNamingList();
        const message = text(`标准名称已确认，已整理 ${Number(value.renamed) || 0} 张图片。图片内容与已有方案保留。`, `Standard names confirmed: ${Number(value.renamed) || 0} images renamed. Image content and variants are retained.`);
        setText(byId("namingStatus"), message); byId("namingStatus").dataset.error = "false"; notice(message, false, true);
      } catch (error) { setText(byId("namingStatus"), error.message); byId("namingStatus").dataset.error = "true"; throw error; }
    });
  }
  async function restoreNaming() {
    const id = planId(state?.lastNaming);
    if (busy || pendingOperation || !id) return;
    if (!requireSavedLocations()) return;
    const snapshot = namingSnapshot();
    await run(text("正在撤回上次名称整理…", "Undoing the last name change…"), async (token, expectedRoot) => {
      try {
        const value = await call("naming-restore", { payload: { expectedRoot, planId: id } });
        if (!assertCurrent(token, expectedRoot)) return;
        validateNamingReceipt(value, snapshot, id);
        if (value.restored !== true) throw new Error(text("撤回结果尚未确认，请保留记录并核对。", "The undo result is not confirmed. Retain the record and check again."));
        invalidateReviewAfterNaming(value.state); acceptState(value.state); namingPlan = null; namingScope = null;
        namingDrafts = new Map((state.items || []).map(item => [imageKey(item), str(item.standardType)])); rememberNamingDraft(); renderNamingList();
        setText(byId("namingStatus"), text("已撤回上次名称整理。", "The last name change was undone.")); byId("namingStatus").dataset.error = "false"; notice(text("已撤回上次名称整理。", "The last name change was undone."), false, true);
      } catch (error) { setText(byId("namingStatus"), error.message); byId("namingStatus").dataset.error = "true"; throw error; }
    });
  }
  async function loadState() {
    await run(text("正在读取图库…", "Loading the library…"), async (token, expectedRoot) => {
      const value = await call("state");
      if (!assertCurrent(token, expectedRoot)) return;
      acceptState(value.state || value, { refill: true });
      try {
        const saved = JSON.parse(sessionStorage.getItem(deletionKey()) || "null");
        if (saved?.root === root && /^[a-f0-9]{32}$/i.test(str(saved.requestId))) deletionRequest = saved;
      } catch (_) { /* Optional recovery state. No deletion is repeated on load. */ }
      if (deletionUncertain()) {
        notice(text("上次删除结果尚未确认，请先核对原请求；不会重复删除。", "The previous delete result is not confirmed. Check the original request first; delete will not be repeated."), true);
        return;
      }
      const savedPlan = extractPlan(value) || extractPlan(value.state);
      if (savedPlan) acceptPlan(savedPlan);
      notice(savedPlan?.candidates?.length ? text("已恢复上次的图片比较，可以继续选择。", "The previous comparison was restored. You can continue choosing.") : root ? text("就绪。放入图片后，点「更新本地」核对新增和替换候选。", "Ready. Add images, then select Update local to review new and replacement candidates.") : text("先保存本地图库位置。", "Save a local library location first."), false);
      const active = value.operation || value.state?.operation || state?.notion?.operation;
      let saved;
      try { saved = JSON.parse(localStorage.getItem(operationKey()) || "null"); } catch (_) { /* The server can also restore its operation. */ }
      if (saved?.requestId || (active?.requestId && (pendingStatuses.has(active.status) || active.status === "unknown" || canRecheckOperation(active)))) {
        pendingOperation = saved?.requestId ? saved : { requestId: active.requestId, autoApply: true };
        if (pendingOperation.metadataJob) metadataJob = pendingOperation.metadataJob;
        const restoreSource = pendingOperation.uiSource || active?.source;
        const restoreTarget = pendingOperation.uiTarget || active?.target;
        if (pendingOperation.uiMode !== "notion") {
          if (["local", "console", "notion"].includes(restoreSource)) byId("syncSource").value = restoreSource;
          if (["console", "device", "notion", "all"].includes(restoreTarget)) byId("syncTarget").value = restoreTarget;
        }
        await pollOperation(active?.requestId === pendingOperation.requestId ? active : { requestId: pendingOperation.requestId, status: "pending" }, token, root);
      }
    });
  }
  async function saveConfig(event) {
    event.preventDefault();
    const nextRoot = byId("libraryRoot").value.trim();
    if (!nextRoot) return;
    const payload = { root: nextRoot, deviceRoot: byId("deviceRoot").value.trim(), notionPage: byId("notionPage").value.trim(), expectedRoot: root };
    await run(text("正在保存图库位置…", "Saving library locations…"), async (token, expectedRoot) => {
      const value = await call("config", { payload });
      if (!assertCurrent(token, expectedRoot)) return;
      const nextState = value.state || value;
      const actualRoot = str(nextState.root);
      if (!actualRoot) throw new Error(text("保存结果没有返回图库位置，请重新读取确认。", "The save result did not return a library location. Reload to check it."));
      if (actualRoot !== root) { root = ""; state = null; plan = null; reviewNeedsScan = false; pendingOperation = null; lastApplied = null; decisions = new Map(); renderPlan(); }
      acceptState(nextState, { refill: true });
      const savedPlan = extractPlan(value) || extractPlan(nextState);
      if (savedPlan) acceptPlan(savedPlan);
      setText(byId("configStatus"), text("位置已保存", "Locations saved"));
      byId("locations").open = false;
      notice(text("位置已保存，可以放入图片或选择同步方向。", "Locations saved. Add images or choose a sync direction."), false, true);
    });
  }
  async function scanImages() {
    await run(text("正在检查图库与 inbox…", "Checking the library and Inbox…"), async (token, expectedRoot) => {
      const value = await call("scan", { payload: { expectedRoot } });
      if (!acceptResponse(value, token, expectedRoot)) return;
      const count = plan?.candidates?.length || 0;
      notice(count ? text(`检查完成，${count} 项图片待确认。`, `Check complete. ${count} images to review.`) : text("检查完成，没有待处理的图片。", "Check complete. No images need attention."), false, true);
      if (count) { setReviewExpanded(true); byId("reviewSection").scrollIntoView({ behavior: "smooth", block: "start" }); }
    });
  }
  async function uploadFiles(fileList) {
    const files = [...(fileList || [])];
    if (busy || pendingOperation || !root || !files.length) return;
    try { validateUploadSize(files); }
    catch (error) {
      notice(error.message, true);
      byId("imageFiles").value = "";
      return;
    }
    await run(text(`正在把 ${files.length} 张图片放进 inbox…`, `Adding ${files.length} images to Inbox…`), (token, expectedRoot) => stageUpload(files, token, expectedRoot));
    byId("imageFiles").value = "";
  }
  function validateUploadSize(files) {
    if (files.length > 50) throw new Error(text("每批最多加入 50 张图片，请分批放入 Inbox。", "Add up to 50 images per batch to Inbox."));
    const configuredLimit = Number(state?.limits?.maxFileBytes);
    const byteLimit = Math.min(64 * 1024 * 1024, Number.isFinite(configuredLimit) && configuredLimit > 0 ? configuredLimit : Infinity);
    if (files.some(file => file.size > byteLimit)) throw new Error(text(`有图片超过单张 ${Math.floor(byteLimit / 1024 / 1024)} MiB 限制，请分开检查后再加入。`, `An image exceeds the ${Math.floor(byteLimit / 1024 / 1024)} MiB per-file limit. Check it separately before adding.`));
    if (files.reduce((total, file) => total + (Number(file.size) || 0), 0) > 96 * 1024 * 1024) throw new Error(text("本次图片超过 96 MiB，请分批加入 Inbox。", "This batch exceeds 96 MiB. Add it to Inbox in smaller batches."));
  }
  async function stageUpload(files, token, expectedRoot) {
    if (!assertCurrent(token, expectedRoot)) return;
    validateUploadSize(files);
    const form = new FormData();
    form.append("expectedRoot", expectedRoot);
    for (const file of files) form.append("files", file, file.name);
    const value = await call("upload", { form });
    if (!acceptResponse(value, token, expectedRoot)) return;
    notice(text("图片已放进 inbox。比较新旧图片并确认处理方式后，再应用更改。", "Images added to Inbox. Compare them and confirm how to handle them before applying changes."), false, true);
    if (plan?.candidates?.length) { setReviewExpanded(true); byId("reviewSection").scrollIntoView({ behavior: "smooth", block: "start" }); }
  }
  function textPasteTarget(target) {
    if (target?.isContentEditable) return true;
    for (let current = target; current; current = current.parentElement) {
      if (["INPUT", "TEXTAREA", "SELECT"].includes(str(current.tagName).toUpperCase())) return true;
      const editable = current.getAttribute?.("contenteditable");
      if (editable === "" || editable === "true" || editable === "plaintext-only") return true;
    }
    return false;
  }
  function imagePasteScope(event) {
    const target = event?.target && event.target !== document && event.target !== document.body ? event.target : document.activeElement;
    if (typeof document.hasFocus === "function" && !document.hasFocus()) return false;
    if (busy || pendingOperation || deletionUncertain() || !root || byId("metadataDialog").open || byId("previewDialog").open || byId("namingDialog").open
        || textPasteTarget(target)) return false;
    const shell = document.querySelector(".image-shell");
    const focusedBody = target === document.body && typeof document.hasFocus === "function" && document.hasFocus();
    return Boolean(shell && (shell.contains(target) || focusedBody));
  }
  function closePasteMenu(restoreFocus = false) {
    const menu = byId("imagePasteMenu");
    if (!menu || menu.hidden) return;
    menu.hidden = true;
    byId("dropZone").setAttribute("aria-expanded", "false");
    if (restoreFocus) byId("dropZone").focus({ preventScroll: true });
  }
  function showPasteMenu(event) {
    if (!imagePasteScope(event)) return;
    event.preventDefault();
    closeImageContextMenu();
    const menu = byId("imagePasteMenu");
    menu.style.setProperty("--image-paste-x", `${Number.isFinite(event.clientX) ? event.clientX : 8}px`);
    menu.style.setProperty("--image-paste-y", `${Number.isFinite(event.clientY) ? event.clientY : 8}px`);
    menu.hidden = false;
    byId("dropZone").setAttribute("aria-expanded", "true");
    byId("imagePasteCommand").focus({ preventScroll: true });
  }
  function closeImageContextMenu(restoreFocus = false) {
    const menu = byId("imageContextMenu");
    if (!menu || menu.hidden) return;
    menu.hidden = true;
    byId("imageDeleteCommand").hidden = true;
    const target = deletionTarget;
    deletionTarget = null;
    if (restoreFocus) target?.focus?.focus?.({ preventScroll: true });
  }
  function deletionScope(value, snapshot, includePlan = true) {
    return value?.root === snapshot.root && root === snapshot.root && str(value.deviceRoot) === snapshot.deviceRoot
      && (pageId(value.notionPage) || pageId(value.notion?.pageId)) === snapshot.pageId
      && [byId("libraryRoot").value, byId("deviceRoot").value, byId("notionPage").value].every((field, index) => field === snapshot.fields[index])
      && (!includePlan || planId(extractPlan(value)) === snapshot.planId && planId(plan) === snapshot.planId);
  }
  function deletionImage(value, snapshot) {
    const items = Array.isArray(value?.items) ? value.items : [];
    if (snapshot.indexed) return items.find(item => item.path === snapshot.path && item.sha256 === snapshot.sha256 && item.space !== "device");
    return extractPlan(value)?.candidates?.find(candidate => (!snapshot.candidateId || candidate.id === snapshot.candidateId)
      && candidate.incoming?.path === snapshot.path && candidate.incoming.sha256 === snapshot.sha256 && candidate.incoming.space !== "device")?.incoming;
  }
  function showImageContextMenu(event, item) {
    if (busy || pendingOperation || deletionUncertain() || !root || !item || item.space === "device" || !safeImagePath(item.path)
        || !/^[a-f0-9]{64}$/i.test(str(item.sha256)) || textPasteTarget(event.target)
        || byId("metadataDialog").open || byId("namingDialog").open || byId("previewDialog").open) return;
    const indexed = (state?.items || []).some(current => imageKey(current) === imageKey(item));
    const candidate = plan?.candidates?.find(candidate => imageKey(candidate.incoming) === imageKey(item));
    if (!indexed && (!candidate || reviewNeedsScan)) return;
    event.preventDefault();
    closePasteMenu(); closeImageContextMenu();
    deletionTarget = { root, deviceRoot: str(state?.deviceRoot), pageId: configuredPageId(), planId: planId(plan), generation,
      path: item.path, sha256: item.sha256, indexed, candidateId: candidate?.id, fingerprint: annotationFingerprint(item), focus: event.target,
      fields: [byId("libraryRoot").value, byId("deviceRoot").value, byId("notionPage").value] };
    const menu = byId("imageContextMenu");
    if (!menu) { deletionTarget = null; return; }
    menu.style.setProperty("--image-paste-x", `${Number.isFinite(event.clientX) ? event.clientX : 8}px`);
    menu.style.setProperty("--image-paste-y", `${Number.isFinite(event.clientY) ? event.clientY : 8}px`);
    menu.hidden = false;
    byId("imageDeleteCommand").hidden = false;
    byId("imageDeleteCommand").disabled = false;
    byId("imageDeleteCommand").focus({ preventScroll: true });
  }
  function rememberDeletion(value) {
    deletionRequest = value;
    try {
      const { focus, ...saved } = value;
      sessionStorage.setItem(deletionKey(), JSON.stringify(saved));
    } catch (_) { /* Keep the original request in memory if storage is unavailable. */ }
  }
  function acceptDeletion(value, snapshot, token, expectedRoot) {
    if (!assertCurrent(token, expectedRoot) || !value.state || !deletionScope(value.state, snapshot, false)
        || value.requestId !== snapshot.requestId || value.path !== snapshot.path || value.sha256 !== snapshot.sha256
        || value.deleted !== true && value.restored !== true) throw new Error(text("删除回执尚未匹配，原请求已保留，请继续核对。", "The delete receipt does not match yet. The original request is retained; continue checking."));
    const selected = new Map(decisions);
    invalidateReviewAfterNaming(value.state);
    acceptResponse(value, token, expectedRoot);
    if (extractPlan(value.state)) {
      for (const candidate of plan?.candidates || []) if (!candidate.previousCandidateId && selected.has(str(candidate.id))) decisions.set(str(candidate.id), selected.get(str(candidate.id)));
      rememberDecisions(); renderPlan();
    }
    rememberDeletion({ ...snapshot, status: value.restored ? "restored" : "completed" });
    notice(value.restored ? text("已撤回删除，图片已恢复。", "Delete undone. The image was restored.") : text("图片已在本地删除，可以撤回。Notion 附件保持原状。", "Image deleted locally. You can undo it. Notion attachments are unchanged."), false, true);
  }
  async function deleteImage() {
    const snapshot = deletionTarget;
    if (!snapshot || busy || pendingOperation || deletionUncertain() || snapshot.generation !== generation
        || byId("metadataDialog").open || byId("namingDialog").open || byId("previewDialog").open) return;
    closeImageContextMenu();
    if (!requireSavedLocations()) return;
    await run(text("正在删除这张图片…", "Deleting this image…"), async (token, expectedRoot) => {
      const latest = await call("state");
      const value = latest.state || latest;
      const current = deletionImage(value, snapshot);
      if (!assertCurrent(token, expectedRoot) || !deletionScope(value, snapshot) || !current || annotationFingerprint(current) !== snapshot.fingerprint
          || [value.operation, value.notion?.operation].some(operation => pendingStatuses.has(operation?.status) || operation?.status === "unknown" || canRecheckOperation(operation))) throw new Error(text("图库、图片或待处理状态已改变，尚未删除，请重新查看。", "The library, image or pending state changed. Nothing was deleted; review it again."));
      const request = { ...snapshot, requestId: crypto.randomUUID().replace(/-/g, ""), status: "pending" };
      rememberDeletion(request);
      try {
        const result = await call("delete", { payload: { expectedRoot, path: request.path, sha256: request.sha256, requestId: request.requestId } });
        acceptDeletion(result, request, token, expectedRoot);
      } catch (error) {
        rememberDeletion({ ...request, status: "unknown" });
        throw new Error(text(`删除结果尚未确认，未重复删除。${localized(error.message, "zh-CN")}请核对原请求。`, `The delete result is not confirmed. It was not repeated. ${localized(error.message, "en")} Check the original request.`));
      }
    }, { deletion: true });
  }
  async function undoOrCheckDeletion() {
    if (busy || pendingOperation || !root || byId("metadataDialog").open || byId("namingDialog").open || byId("previewDialog").open || !requireSavedLocations()) return;
    const checking = deletionUncertain();
    const record = checking ? deletionRequest : state?.lastDeletion;
    if (!record?.requestId || !checking && record.canRestore !== true) return;
    const snapshot = checking ? record : { ...record, root, deviceRoot: str(state?.deviceRoot), pageId: configuredPageId(),
      fields: [byId("libraryRoot").value, byId("deviceRoot").value, byId("notionPage").value] };
    await run(checking ? text("正在核对原删除请求…", "Checking the original delete request…") : text("正在撤回删除…", "Undoing delete…"), async (token, expectedRoot) => {
      if (!checking) {
        const latest = await call("state");
        const fresh = latest.state || latest;
        if (!assertCurrent(token, expectedRoot) || !deletionScope(fresh, snapshot, false)
            || fresh.lastDeletion?.requestId !== record.requestId || fresh.lastDeletion?.canRestore !== true) throw new Error(text("删除记录或图库已变化，尚未撤回，请重新核对。", "The delete record or library changed. Nothing was restored; check again."));
      }
      rememberDeletion({ ...snapshot, status: "pending" });
      try {
        const result = checking ? await call("delete-operation", { params: { expectedRoot, requestId: snapshot.requestId } })
          : await call("delete-restore", { payload: { expectedRoot, requestId: snapshot.requestId } });
        if (checking && !["completed", "restored"].includes(result.status)) throw new Error(serviceMessage(result.message, "删除结果仍需核对，未再次执行删除。", "The delete result still needs checking. Delete was not repeated.", str(result.status)));
        acceptDeletion(result, snapshot, token, expectedRoot);
      } catch (error) {
        rememberDeletion({ ...snapshot, status: "unknown" });
        throw error;
      }
    }, { deletion: true });
  }
  function clipboardFiles(blobs) {
    const stamp = new Date().toISOString().replace(/[^0-9]/g, "").slice(0, 17);
    const images = blobs.filter(blob => str(blob?.type).toLowerCase().startsWith("image/"));
    if (!images.length) throw new Error(text("剪贴板里没有可用图片。请先复制图片，或把图片拖到这里。", "No usable image was found on the clipboard. Copy an image first, or drag one here."));
    if (images.some(blob => !clipboardImageTypes.has(str(blob.type).toLowerCase()))) throw new Error(text("这种剪贴板图片格式暂不支持，请使用 PNG、JPEG、WebP、GIF、BMP、TIFF 或 ICO。", "This clipboard image format is not supported. Use PNG, JPEG, WebP, GIF, BMP, TIFF or ICO."));
    if (images.some(blob => !Number.isFinite(blob.size) || blob.size <= 0)) throw new Error(text("剪贴板图片为空，尚未加入 Inbox。请重新复制图片或拖入文件。", "The clipboard image is empty and was not added to Inbox. Copy it again or drag in a file."));
    validateUploadSize(images);
    return images.map((blob, index) => {
      const type = str(blob.type).toLowerCase();
      return new File([blob], `Clipboard-${stamp}-${index + 1}.${clipboardImageTypes.get(type)}`, { type });
    });
  }
  async function readClipboardImages() {
    if (typeof navigator === "undefined" || typeof navigator.clipboard?.read !== "function") throw new Error(text("此处暂时不能直接读取剪贴板。请聚焦图片区域后按 Ctrl+V，或拖入图片。", "Direct clipboard access is unavailable here. Focus the image area and press Ctrl+V, or drag in an image."));
    let items;
    try { items = await navigator.clipboard.read(); }
    catch (_) { throw new Error(text("未能读取剪贴板图片。请允许浏览器粘贴，或聚焦图片区域后按 Ctrl+V、拖入图片。", "The clipboard image could not be read. Allow browser paste, or focus the image area and press Ctrl+V or drag in an image.")); }
    const blobs = [];
    for (const item of items || []) {
      const type = [...(item.types || [])].find(type => clipboardImageTypes.has(str(type).toLowerCase()));
      if (!type) {
        if ((item.types || []).some(type => str(type).toLowerCase().startsWith("image/"))) throw new Error(text("这种剪贴板图片格式暂不支持，请复制 PNG 或 JPEG 图片。", "This clipboard image format is not supported. Copy a PNG or JPEG image."));
        continue;
      }
      let blob;
      try { blob = await item.getType(type); }
      catch (_) { throw new Error(text("未能读取剪贴板图片。请聚焦图片区域后按 Ctrl+V，或拖入图片。", "The clipboard image could not be read. Focus the image area and press Ctrl+V, or drag in an image.")); }
      if (str(blob?.type).toLowerCase() !== str(type).toLowerCase()) throw new Error(text("剪贴板图片格式未能确认，请重新复制或拖入文件。", "The clipboard image format could not be verified. Copy it again or drag in a file."));
      blobs.push(blob);
    }
    return clipboardFiles(blobs);
  }
  async function pasteImageFiles(event, providedFiles = null) {
    if (!imagePasteScope(event) || handledPasteEvents.has(event)) return;
    if (!requireSavedLocations()) return;
    handledPasteEvents.add(event);
    closePasteMenu(true);
    const snapshot = { root, deviceRoot: str(state?.deviceRoot), pageId: configuredPageId(), planId: planId(plan),
      fields: [byId("libraryRoot").value, byId("deviceRoot").value, byId("notionPage").value] };
    await run(text("正在读取剪贴板图片…", "Reading clipboard images…"), async (token, expectedRoot) => {
      const files = providedFiles ? clipboardFiles(providedFiles) : await readClipboardImages();
      const current = (value, server = false) => assertCurrent(token, expectedRoot) && !pendingOperation && root === snapshot.root
        && str(value?.root) === snapshot.root && str(value?.deviceRoot) === snapshot.deviceRoot
        && (pageId(value?.notionPage) || pageId(value?.notion?.pageId)) === snapshot.pageId
        && (!server || planId(extractPlan(value)) === snapshot.planId) && planId(plan) === snapshot.planId
        && (!server || ![value?.operation, value?.notion?.operation].some(operation => pendingStatuses.has(operation?.status) || operation?.status === "unknown" || canRecheckOperation(operation)))
        && [byId("libraryRoot").value, byId("deviceRoot").value, byId("notionPage").value].every((field, index) => field === snapshot.fields[index]);
      if (!current(state)) throw new Error(text("图库或同步位置已改变，已取消粘贴；请重新确认位置后再粘贴。", "The library or sync locations changed. Paste was cancelled; check the locations before pasting again."));
      const latest = await call("state");
      if (!current(latest.state || latest, true)) throw new Error(text("图库、同步位置或待确认状态已改变，已取消粘贴，请重新读取后再试。", "The library, sync locations or review state changed. Paste was cancelled; reload the state before trying again."));
      await stageUpload(files, token, expectedRoot);
    });
  }
  async function receiveImagePaste(event) {
    if (!imagePasteScope(event) || handledPasteEvents.has(event)) return;
    const clipboard = event.clipboardData;
    if (!clipboard) return;
    let files = [...(clipboard.files || [])].filter(file => str(file?.type).toLowerCase().startsWith("image/"));
    if (!files.length) files = [...(clipboard.items || [])].filter(item => item.kind === "file" && str(item.type).toLowerCase().startsWith("image/")).map(item => item.getAsFile()).filter(Boolean);
    if (!files.length) return;
    event.preventDefault();
    await pasteImageFiles(event, files);
  }
  async function syncImages() {
    if (busy || pendingOperation || deletionUncertain() || !root || !requireSavedLocations()) return;
    if (!configuredPageId() || !notionReady()) {
      updateNotionStatus();
      notice(!configuredPageId() ? text("请先保存 Notion 目标页面，再同步到 Notion。", "Save a Notion destination page before syncing to Notion.") : currentText(errors.notion_unavailable), true);
      return;
    }
    await run(text("正在同步当前文件夹到 Notion…", "Syncing the current folder to Notion…"), async (token, expectedRoot) => {
      await dispatchSync("console", "notion", token, expectedRoot, null, null, "notion");
    });
  }
  async function advancedSyncImages() {
    if (busy || pendingOperation || deletionUncertain() || !root || !advancedSyncAllowed()) return;
    const issue = advancedSyncIssue();
    if (issue) { notice(issue, true); return; }
    if (!requireSavedLocations()) return;
    const source = byId("syncSource").value, target = byId("syncTarget").value;
    if ((source === "notion" || target === "notion" || target === "all") && state?.notionAvailable !== true && state?.notion?.canAttempt !== true && state?.notion?.available !== true) { notice(errors.notion_unavailable, true); return; }
    await run(text("正在检查同步内容…", "Checking sync content…"), async (token, expectedRoot) => {
      const afterDevice = target === "all" && state?.deviceRoot ? { source: "console", target: "device", deviceRoot: str(state.deviceRoot) } : null;
      if (source === "local" && ["notion", "all"].includes(target)) {
        const value = await call("scan", { payload: { expectedRoot } });
        await finishSync(value, token, expectedRoot, true, { source: "console", target: "notion", notionPage: str(state?.notionPage), next: afterDevice });
        return;
      }
      const actualTarget = target === "all" ? source === "notion" ? "console" : "notion" : target;
      await dispatchSync(source, actualTarget, token, expectedRoot, afterDevice);
    });
  }
  async function dispatchSync(source, target, token, expectedRoot, after = null, savedMetadata = null, uiMode = "legacy") {
    if (!assertCurrent(token, expectedRoot)) return;
    if (savedMetadata) requireMetadataScope(savedMetadata, token, expectedRoot);
    const requestId = savedMetadata?.deviceRequestId && target === "device" ? savedMetadata.deviceRequestId : crypto.randomUUID();
    if (savedMetadata && target === "device") {
      savedMetadata = { ...savedMetadata, deviceRequestId: requestId };
      rememberMetadataJob(savedMetadata);
    }
    const isNotion = source === "notion" || target === "notion";
    if (isNotion) {
      pendingOperation = { requestId, autoApply: uiMode !== "notion" && !savedMetadata, after, ...(savedMetadata ? { metadataJob: savedMetadata } : {}), root: expectedRoot, source, target, uiMode, uiStatus: "running",
        pageId: configuredPageId(), uiSource: uiMode === "notion" ? "console" : byId("syncSource").value, uiTarget: uiMode === "notion" ? "notion" : byId("syncTarget").value };
      try { localStorage.setItem(operationKey(), JSON.stringify(pendingOperation)); } catch (_) { /* The server persists its own operation. */ }
      notice(source === "notion" ? text("正在从 Notion 同步图片…", "Syncing images from Notion…") : text("正在同步到 Notion…", "Syncing to Notion…"));
    } else notice(text("正在检查设备文件夹的同步内容…", "Checking device folder sync content…"));
    let value;
    try { value = await call("sync", { payload: { source, target, expectedRoot, requestId } }); }
    catch (error) { if (isNotion && [400, 422].includes(error.httpStatus)) clearOperation(); throw error; }
    if (!assertCurrent(token, expectedRoot)) return;
    if (savedMetadata) requireMetadataScope(savedMetadata, token, expectedRoot, value.state || state);
    if (value.operation) {
      if (value.state) acceptState(value.state);
      await pollOperation(value.operation, token, expectedRoot);
      return;
    }
    if (isNotion) clearOperation();
    if (savedMetadata) {
      if (target !== "device") throw new Error(text("Notion 未返回可核对的同步回执，已保留本地修改。", "Notion did not return a verifiable sync receipt. Local changes are retained."));
      await acceptMetadataDeviceResult(value, savedMetadata, token, expectedRoot);
      return;
    }
    await finishSync(value, token, expectedRoot, uiMode !== "notion", after);
  }
  async function continueSync(instruction, token, expectedRoot) {
    if (instruction.target === "device" && instruction.deviceRoot !== undefined && instruction.deviceRoot !== str(state?.deviceRoot)) throw new Error(text("额外设备文件夹已改变，已暂停后续同步，请重新选择目标。", "The additional device folder changed. Further sync paused; choose the destination again."));
    if (instruction.target === "notion" && instruction.notionPage !== undefined && instruction.notionPage !== str(state?.notionPage)) throw new Error(text("Notion 目标页面已改变，已暂停后续同步，请重新选择目标。", "The Notion destination page changed. Further sync paused; choose the destination again."));
    await dispatchSync(instruction.source, instruction.target, token, expectedRoot, instruction.next || null);
  }
  function clearOperation() {
    try { localStorage.removeItem(operationKey()); } catch (_) { /* Optional storage. */ }
    pendingOperation = null;
  }
  async function finishSync(value, token, expectedRoot, autoApply, after = null) {
    if (!assertCurrent(token, expectedRoot)) return;
    if (value.state) acceptState(value.state);
    else if (typeof value.root === "string") acceptState(value);
    const syncPlan = extractPlan(value);
    if (syncPlan && after && validInstruction(after)) rememberContinuation(planId(syncPlan), after);
    if (syncPlan) acceptPlan(syncPlan);
    const count = syncPlan?.candidates?.length || 0;
    const errorCount = Array.isArray(syncPlan?.errors) ? syncPlan.errors.length : 0;
    if (autoApply && count && !errorCount && syncPlan.candidates.every(canAutomaticallyAdd)) {
      notice(text(`正在同步 ${count} 张新图片…`, `Syncing ${count} new images…`));
      await commitBatch({ planId: planId(syncPlan), expectedRoot, decisions: syncPlan.candidates.map(candidate => ({ id: str(candidate.id), action: "add" })) }, token, expectedRoot);
      return;
    }
    if (!count && errorCount) { notice(text(`有 ${errorCount} 项图片未能读取，后续同步已暂停，请先检查下方记录。`, `${errorCount} images could not be read. Further sync paused; check the records below.`), true); return; }
    if (!count && after && validInstruction(after)) {
      if (syncPlan) clearContinuation(planId(syncPlan));
      await continueSync(after, token, expectedRoot);
      return;
    }
    notice(count ? text(`已准备 ${count} 项同步内容，确认下方选择后${after ? "自动继续同步" : "执行"}。`, `${count} sync items are ready. Confirm the choices below to ${after ? "continue syncing automatically" : "apply them"}.`) : serviceMessage(value.message, "同步检查完成，没有待处理的差异。", "Sync check complete. There are no differences to process."), false, true);
    if (count) { setReviewExpanded(true); byId("reviewSection").scrollIntoView({ behavior: "smooth", block: "start" }); }
  }
  function operationMessage(operation) {
    const stages = { queued: text("等待开始", "Waiting to start"), starting: text("准备同步", "Preparing sync"), connecting: text("连接 Notion", "Connecting to Notion"), verifying: text("核验页面与附件", "Verifying page and attachments"), listing: text("读取图片清单", "Reading image list"), scanning: text("检查图片", "Checking images"), downloading: text("下载原图", "Downloading originals"), uploading: text("上传原图", "Uploading originals"), reading: text("读取 Notion 页面", "Reading the Notion page"), fetching: text("读取 Notion 页面", "Reading the Notion page"), planning: text("准备图片比较", "Preparing comparison"), applying: text("保存图片", "Saving images"), verifying_download: text("核对下载原图", "Verifying downloaded originals"), verify: text("核验图片", "Verifying images"), completed: text("同步完成", "Sync complete") };
    const stage = stages[operation.stage || operation.phase] || (pendingStatuses.has(operation.status) ? text("正在同步，请稍候", "Syncing, please wait") : text("正在核对同步结果", "Checking sync results"));
    return text(`${localized(stage, "zh-CN")}…`, `${localized(stage, "en")}…`);
  }
  async function pollOperation(initial, token, expectedRoot) {
    const requestId = str(initial?.requestId || pendingOperation?.requestId);
    if (!requestId) throw new Error(text("同步未返回可核对的记录，请保留页面并重新读取状态。", "Sync did not return a verifiable record. Keep this page and reload the state."));
    if (pendingOperation?.requestId && pendingOperation.requestId !== requestId) throw new Error(text("返回的同步记录与本次请求不同，请继续核对原请求。", "The returned sync record does not match this request. Continue checking the original request."));
    pendingOperation = { ...pendingOperation, requestId, autoApply: pendingOperation?.uiMode !== "notion" && pendingOperation?.autoApply !== false,
      after: validInstruction(pendingOperation?.after) ? pendingOperation.after : null,
      root: pendingOperation?.root || initial.root, source: pendingOperation?.source || initial.source,
      target: pendingOperation?.target || initial.target, pageId: pendingOperation?.pageId || pageId(initial.pageId),
      uiSource: pendingOperation?.uiSource || byId("syncSource").value, uiTarget: pendingOperation?.uiTarget || byId("syncTarget").value };
    try { localStorage.setItem(operationKey(), JSON.stringify(pendingOperation)); } catch (_) { /* Optional storage. */ }
    let operation = initial;
    while (assertCurrent(token, expectedRoot)) {
      if (operation.root && operation.root !== expectedRoot) throw new Error(text("同步回执对应另一个图库，原请求已保留，请继续核对。", "The sync receipt belongs to another library. The original request is retained; continue checking."));
      pendingOperation.uiStatus = operation.status;
      if (notionScopeMatches(operation)) state = { ...state, operation, notion: { ...(state?.notion || {}), operation } };
      const savedMetadata = pendingOperation.metadataJob;
      if (savedMetadata) {
        requireMetadataScope(savedMetadata, token, expectedRoot);
        if (operation.root !== expectedRoot || operation.source !== "console" || operation.target !== "notion"
            || pageId(operation.pageId) !== savedMetadata.pageId) throw new Error(text("同步回执的图库、页面或方向已改变，已保留本地修改与原请求。", "The receipt's library, page or direction changed. Local changes and the original request are retained."));
      }
      if (completeStatuses.has(operation.status)) {
        const autoApply = pendingOperation.autoApply;
        const after = pendingOperation.after;
        const latest = await call("state");
        if (!assertCurrent(token, expectedRoot)) return;
        const nextState = latest.state || latest;
        if (savedMetadata) {
          requireMetadataScope(savedMetadata, token, expectedRoot, nextState);
          if (operation.status !== "completed" || Array.isArray(operation.remainingTargets) && operation.remainingTargets.length) throw new Error(text("Notion 尚未完整确认同步结果，请继续核对原请求。", "Notion has not fully confirmed the sync result. Continue checking the original request."));
          acceptState(nextState);
          clearOperation();
          await completeMetadataTarget(savedMetadata, "notion", token, expectedRoot);
          return;
        }
        const savedPlan = extractPlan(latest) || extractPlan(nextState);
        const resultPlan = extractPlan(operation.result);
        if (operation.planId && planId(resultPlan || savedPlan) !== operation.planId) throw new Error(text("同步的图片比较记录尚未对应，原请求已保留，请继续核对。", "The sync comparison does not match yet. The original request is retained; continue checking."));
        const syncPlan = resultPlan || (operation.planId ? savedPlan : null);
        if (operation.status === "needs_review" && !syncPlan) throw new Error(text("同步尚未返回匹配的图片比较记录，请继续核对。", "Sync has not returned a matching comparison yet. Continue checking."));
        clearOperation();
        if (syncPlan) { plan = null; decisions = new Map(); renderPlan(); }
        const value = { ...(operation.result || {}), state: nextState, ...(syncPlan ? { plan: syncPlan } : {}), message: str(operation.message || operation.result?.message) };
        await finishSync(value, token, expectedRoot, autoApply && Boolean(operation.planId && planId(syncPlan) === operation.planId), after);
        return;
      }
      if (operation.status && !pendingStatuses.has(operation.status)) {
        if (["failed", "error", "cancelled", "canceled"].includes(operation.status) && !canRecheckOperation(operation)) clearOperation();
        throw new Error(serviceMessage(str(operation.error?.message || operation.error || operation.message), "同步尚未完成，原请求已保留，请继续核对。", "Sync has not finished. The original request is retained; continue checking.", str(operation.code)));
      }
      notice(operationMessage(operation));
      await new Promise(resolve => setTimeout(resolve, 1000));
      if (!assertCurrent(token, expectedRoot)) return;
      const value = await call("operation", { params: { requestId } });
      operation = value.operation || value;
      if (operation.requestId && operation.requestId !== requestId) throw new Error(text("同步回执不匹配，原请求已保留，请继续核对。", "The sync receipt does not match. The original request is retained; continue checking."));
    }
  }
  async function resumeOperation() {
    if (!pendingOperation) return;
    const savedMetadata = pendingOperation.metadataJob;
    await run(text("正在核对上次同步…", "Checking the previous sync…"), async (token, expectedRoot) => {
      try {
        if (savedMetadata) requireMetadataScope(savedMetadata, token, expectedRoot);
        const value = await call("operation", { params: { requestId: pendingOperation.requestId } });
        const operation = value.operation || value;
        if (canRecheckOperation(operation)) {
          const latest = await call("state");
          if (!assertCurrent(token, expectedRoot)) return;
          if (savedMetadata) requireMetadataScope(savedMetadata, token, expectedRoot, latest.state || latest);
          acceptState(latest.state || latest);
          if (!recoveryScopeMatches(operation, expectedRoot)) throw new Error(text("原同步的图库、页面或方向已改变，已保留原请求，不会向其他位置恢复。", "The original sync's library, page or direction changed. Its request is retained and will not resume to another location."));
          const recovered = await call("sync", { payload: { expectedRoot, requestId: operation.requestId, source: operation.source, target: operation.target } });
          if (!assertCurrent(token, expectedRoot)) return;
          const recoveredOperation = recovered.operation || recovered;
          if (!recoveryScopeMatches(recoveredOperation, expectedRoot)) throw new Error(text("恢复回执与原同步范围不一致，原请求已保留，请继续核对。", "The recovery receipt does not match the original sync scope. The original request is retained; continue checking."));
          await pollOperation(recoveredOperation, token, expectedRoot);
          return;
        }
        await pollOperation(operation, token, expectedRoot);
      } catch (error) {
        if (savedMetadata) {
          rememberMetadataJob({ ...(metadataJob || savedMetadata), status: pendingOperation ? "unknown" : "failed", message: text(`已保存到本地；同步未完成。${localized(error.message, "zh-CN") || "请继续核对原请求。"}`, `Saved locally; sync did not finish. ${localized(error.message, "en") || "Continue checking the original request."}`) });
          throw new Error(metadataJob.message);
        }
        throw error;
      }
    });
  }
  function reviewApply() {
    if (busy || !plan) return;
    if (reviewNeedsScan) { notice(text("名称已变化，请重新检查图片；原选择已保留。", "Names changed. Check images again; your previous choices are retained."), true); return; }
    const selected = plan.candidates.filter(candidate => actions.has(decisions.get(str(candidate.id)))).map(candidate => ({ id: str(candidate.id), action: decisions.get(str(candidate.id)) }));
    if (!selected.length || selected.length !== plan.candidates.length) return;
    if (plan.candidates.some(candidate => decisions.get(str(candidate.id)) !== "keep" && needsStandardPurpose(candidate))) { notice(text("采用前请先在方案信息中明确标准用途。", "Choose a standard purpose in Variant details before adding or replacing."), true); return; }
    void applyBatch({ planId: planId(plan), expectedRoot: root, decisions: selected });
  }
  async function applyBatch(payload) {
    if (!payload || payload.expectedRoot !== root || payload.planId !== planId(plan)) { notice(text("图库或比较记录已变化，请重新确认。", "The library or comparison changed. Check it again before confirming."), true); return; }
    await run(text("正在应用已确认的图片操作…", "Applying confirmed image actions…"), async (token, expectedRoot) => {
      await commitBatch(payload, token, expectedRoot);
    });
  }
  async function commitBatch(payload, token, expectedRoot) {
    let savedMetadata = metadataJob?.planId === payload.planId ? metadataJob : null;
    if (!savedMetadata) try { savedMetadata = JSON.parse(sessionStorage.getItem(metadataPlanKey(payload.planId)) || "null"); } catch (_) { /* Optional storage. */ }
    if (savedMetadata) requireMetadataScope(savedMetadata, token, expectedRoot);
    const value = await call("apply", { payload });
    if (!assertCurrent(token, expectedRoot)) return;
    if (savedMetadata) requireMetadataScope(savedMetadata, token, expectedRoot, value.state || state);
    const after = readContinuation(payload.planId);
    if (str(value.planId)) lastApplied = { root: expectedRoot, planId: str(value.planId) };
    try { sessionStorage.removeItem(decisionKey()); } catch (_) { /* Optional storage. */ }
    plan = null;
    decisions = new Map();
    renderPlan();
    acceptResponse(value, token, expectedRoot);
    if (!value.state) {
      const updated = await call("state");
      if (assertCurrent(token, expectedRoot)) {
        acceptState(updated.state || updated);
        const remaining = extractPlan(updated) || extractPlan(updated.state);
        if (remaining) acceptPlan(remaining);
      }
    }
    notice(serviceMessage(value.message, "已应用所选操作。", "Selected actions applied."), false, true);
    if (savedMetadata?.planId === payload.planId && savedMetadata.root === expectedRoot) {
      try { sessionStorage.removeItem(metadataPlanKey(payload.planId)); } catch (_) { /* Optional storage. */ }
      if (value.metadataSync?.status === "completed" && !Number(value.metadataSync?.unresolved)) await completeMetadataTarget(savedMetadata, "device", token, expectedRoot);
      else {
        rememberMetadataJob({ ...savedMetadata, status: "failed", planId: "", message: text("已保存到本地；设备图片操作已确认，但方案信息尚未完整同步，请重新核对。", "Saved locally. Device image actions were confirmed, but variant details have not fully synced. Check again.") });
        notice(metadataJob.message, true);
      }
    }
    if (after && assertCurrent(token, expectedRoot)) {
      clearContinuation(payload.planId);
      await continueSync(after, token, expectedRoot);
    }
  }
  async function restoreImages() {
    if (!lastApplied || lastApplied.root !== root || pendingOperation) return;
    const payload = { expectedRoot: root, planId: lastApplied.planId };
    await run(text("正在撤回上次本地图片操作…", "Undoing the last local image action…"), async (token, expectedRoot) => {
      const value = await call("restore", { payload });
      if (!assertCurrent(token, expectedRoot)) return;
      lastApplied = null;
      plan = null;
      decisions = new Map();
      renderPlan();
      if (value.state) acceptState(value.state);
      notice(text("已撤回上次本地图片操作。Notion 上已保存的附件保持原状。", "The last local image action was undone. Attachments already saved in Notion are unchanged."), false, true);
    });
  }

  byId("configForm").addEventListener("submit", saveConfig);
  byId("scanImages").addEventListener("click", scanImages);
  byId("syncImages").addEventListener("click", syncImages);
  byId("advancedSyncImages").addEventListener("click", advancedSyncImages);
  for (const id of ["syncSource", "syncTarget"]) byId(id).addEventListener("change", updateControls);
  byId("checkOperation").addEventListener("click", resumeOperation);
  byId("restoreImages").addEventListener("click", restoreImages);
  byId("imageDeleteCommand")?.addEventListener("click", deleteImage);
  byId("undoDelete")?.addEventListener("click", undoOrCheckDeletion);
  byId("metadataForm").addEventListener("submit", saveMetadata);
  byId("metadataSaveOnly").addEventListener("click", event => saveMetadata(event, false));
  for (const id of ["metadataGroupTitle", "metadataStandardType", "metadataVariantLabel", "metadataDerivedFrom"]) {
    byId(id).addEventListener(["metadataDerivedFrom", "metadataStandardType"].includes(id) ? "change" : "input", () => {
      updateMetadataName();
      setText(byId("metadataStatus"), metadataDirty() ? text("未保存。保存并同步会从 Console 推送本次修改。", "Unsaved changes. Save and sync pushes these changes from Console.") : metadataJob?.message || text("尚无未保存的修改。", "No unsaved changes."));
      byId("metadataStatus").dataset.error = "false";
      updateMetadataControls();
    });
  }
  byId("metadataClose").addEventListener("click", () => { if (!busy) byId("metadataDialog").close(); });
  byId("metadataDialog").addEventListener("cancel", event => { if (busy) event.preventDefault(); });
  byId("metadataDialog").addEventListener("close", () => {
    const path = metadataTarget?.path;
    metadataTarget = null;
    setTimeout(() => {
      const current = [...byId("imageGrid").querySelectorAll("button"), ...byId("candidateList").querySelectorAll("button")].find(button => button.dataset.metadataPath === path);
      (current || metadataFocus)?.focus({ preventScroll: true });
    }, 0);
  });
  byId("organizeNames").addEventListener("click", openNaming);
  byId("namingPreview").addEventListener("click", previewNaming);
  byId("namingApply").addEventListener("click", applyNaming);
  byId("namingRestore").addEventListener("click", restoreNaming);
  byId("namingClose").addEventListener("click", () => { if (!busy) byId("namingDialog").close(); });
  byId("namingDialog").addEventListener("cancel", event => { if (busy) event.preventDefault(); });
  byId("namingDialog").addEventListener("close", () => { namingFocus?.focus({ preventScroll: true }); });
  byId("imageSearch").addEventListener("input", renderCollection);
  byId("imageFiles").addEventListener("change", event => uploadFiles(event.target.files));
  byId("reviewApply").addEventListener("click", reviewApply);
  byId("reviewToggle").addEventListener("click", () => setReviewExpanded(!reviewExpanded));
  byId("closePreview").addEventListener("click", () => byId("previewDialog").close());
  const previewDialog = byId("previewDialog");
  let previewBackdropPressed = false;
  const outsidePreview = event => {
    const bounds = previewDialog.getBoundingClientRect();
    return previewDialog.open && event.target === previewDialog
      && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom);
  };
  previewDialog.addEventListener("pointerdown", event => { previewBackdropPressed = event.button === 0 && outsidePreview(event); });
  previewDialog.addEventListener("pointercancel", () => { previewBackdropPressed = false; });
  previewDialog.addEventListener("click", event => {
    const pressedOutside = previewBackdropPressed;
    previewBackdropPressed = false;
    if (pressedOutside && outsidePreview(event)) previewDialog.close();
  });
  previewDialog.addEventListener("close", () => {
    previewBackdropPressed = false;
    previewItem = null;
    byId("previewImageWrap").replaceChildren();
    publishPreviewState(false);
    previewFocus?.focus({ preventScroll: true });
  });
  const dropZone = byId("dropZone");
    const openPicker = () => { if (!busy && !pendingOperation && !deletionUncertain() && root) byId("imageFiles").click(); };
  dropZone.addEventListener("click", openPicker);
  dropZone.addEventListener("contextmenu", showPasteMenu);
  byId("pasteImages").addEventListener("click", pasteImageFiles);
  byId("imagePasteCommand").addEventListener("click", pasteImageFiles);
  document.addEventListener("paste", receiveImagePaste);
  document.addEventListener("pointerdown", event => { if (!byId("imagePasteMenu").contains(event.target)) closePasteMenu(); });
  document.addEventListener("pointerdown", event => { if (!byId("imageContextMenu")?.contains(event.target)) closeImageContextMenu(); });
  document.addEventListener("keydown", event => {
    if (!byId("imagePasteMenu").hidden && ["Escape", "Tab"].includes(event.key)) {
      if (event.key === "Escape") event.preventDefault();
      closePasteMenu(event.key === "Escape");
    }
    if (byId("imageContextMenu") && !byId("imageContextMenu").hidden && ["Escape", "Tab"].includes(event.key)) {
      if (event.key === "Escape") event.preventDefault();
      closeImageContextMenu(event.key === "Escape");
    }
  });
  if (typeof window !== "undefined") {
    window.addEventListener("blur", () => closePasteMenu());
    window.addEventListener("resize", () => closePasteMenu());
    window.addEventListener("blur", () => closeImageContextMenu());
    window.addEventListener("resize", () => closeImageContextMenu());
  }
  dropZone.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openPicker(); } });
  dropZone.addEventListener("dragover", event => { event.preventDefault(); if (!busy && root) dropZone.classList.add("drag-over"); });
  dropZone.addEventListener("dragleave", event => { if (!dropZone.contains(event.relatedTarget)) dropZone.classList.remove("drag-over"); });
  dropZone.addEventListener("drop", event => { event.preventDefault(); dropZone.classList.remove("drag-over"); void uploadFiles(event.dataTransfer?.files); });
  document.addEventListener("dragover", event => { if ([...(event.dataTransfer?.types || [])].includes("Files")) event.preventDefault(); });
  document.addEventListener("drop", event => { if ([...(event.dataTransfer?.types || [])].includes("Files")) event.preventDefault(); });
  initializeEmbeddedImage();
  updateControls();
  void loadState();
})();
