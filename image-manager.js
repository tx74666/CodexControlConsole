"use strict";
(() => {
  const byId = id => document.getElementById(id);
  const endpoint = "/api/images/";
  const embedded = typeof window !== "undefined" && window.parent !== window
    && new URLSearchParams(window.location.search).get("embed") === "steamwork";
  let reviewExpanded = !embedded;
  const actions = new Set(["replace", "keep", "add"]);
  const statusLabels = { new: "新图片", duplicate: "重复图片", conflict: "替换候选", ambiguous: "多个匹配，请比较" };
  const errors = {
    root_changed: "图库位置已变化，请重新打开页面读取。当前选择已保留。",
    revision_conflict: "图片在比较后发生了变化，请重新检查后选择。",
    plan_stale: "图片在比较后发生了变化，请重新检查后选择。",
    plan_not_found: "这份比较记录已不可用，请重新检查图片。",
    notion_unavailable: "Notion 同步连接尚未就绪。页面地址可先保存，本地图与设备同步仍可使用。",
    device_not_configured: "请先在「图库与同步位置」填写设备文件夹。"
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
  function pageId(value) {
    const match = str(value).match(/[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}/i);
    return match ? match[0].replace(/-/g, "").toLowerCase() : "";
  }
  const configuredPageId = () => pageId(state?.notionPage) || pageId(state?.notion?.pageId);
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
    const placeholder = node("option", "", "选择标准用途"); placeholder.value = ""; select.append(placeholder);
    for (const type of standardTypes()) {
      const option = node("option", "", type.label && type.label !== type.code ? `${str(type.label)} · ${type.code}` : type.code);
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
  const canAutomaticallyAdd = candidate => candidate.status === "new" && !candidate.previousCandidateId && (!standardNaming() || validStandardType(str(candidate.incoming?.standardType)) && candidate.incoming?.namingNeedsReview === false);
  const safeImagePath = value => typeof value === "string" && Boolean(value) && !/^[\\/]|^[a-z]:|[\x00-\x1f]/i.test(value) && !value.split(/[\\/]/).some(part => !part || part === "." || part === "..");
  function updateMetadataName() {
    const enabled = standardNaming();
    byId("metadataGroupTitle").hidden = enabled;
    byId("metadataGroupTitle").required = !enabled;
    byId("metadataStandardType").hidden = !enabled;
    byId("metadataStandardType").required = enabled;
    byId("metadataPurposeLabel").textContent = enabled ? "标准用途" : "用途 / 标题";
    byId("metadataStandardName").hidden = !enabled;
    byId("metadataStandardName").textContent = enabled ? standardName(metadataTarget, metadataPurpose()) ? `采用后：${standardName(metadataTarget, metadataPurpose())}` : "先选择标准用途；名称中的尺寸保持图片的真实尺寸。" : "";
    byId("metadataNamingHint").textContent = enabled ? metadataTarget?.indexed ? "标准用途变更会按预览名称整理文件名；图片内容、方案与派生关系保持。" : "先保存标准用途，确认入库时采用标准文件名。" : "整理用途、方案与来源关系，保留原文件名和图片内容。";
  }
  function rememberMetadataJob(job) {
    metadataJob = job;
    try { sessionStorage.setItem(metadataJobKey(job), JSON.stringify(job)); } catch (_) { /* Keep the saved result in memory. */ }
    if (job.planId) try { sessionStorage.setItem(metadataPlanKey(job.planId), JSON.stringify(job)); } catch (_) { /* Optional storage. */ }
    if (metadataTarget && metadataTarget.path === job.path && metadataTarget.sha256 === job.sha256) {
      byId("metadataStatus").textContent = job.message;
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
    if (!assertCurrent(token, expectedRoot) || !metadataScopeMatches(job, value)) throw new Error("图库、同步位置或原图已改变，已停止本次同步；保存内容与原请求已保留，请重新核对。");
  }
  function configurationDirty() {
    return Boolean(state) && (byId("libraryRoot").value.trim() !== root
      || byId("deviceRoot").value.trim() !== str(state.deviceRoot)
      || byId("notionPage").value.trim() !== str(state.notionPage));
  }
  function requireSavedLocations() {
    if (!configurationDirty()) return true;
    byId("locations").open = true;
    byId("configStatus").textContent = "位置有未保存的修改，请先保存位置。";
    if (byId("metadataDialog").open) byId("metadataStatus").textContent = "位置有未保存的修改，请关闭此框并先保存位置，再同步。";
    if (byId("namingDialog").open) byId("namingStatus").textContent = "位置有未保存的修改，请关闭此框并先保存位置，再整理名称。";
    notice("位置有未保存的修改，请先保存位置，再同步。", true);
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
    byId("metadataSave").textContent = dirty ? "保存并同步" : ownPending ? "继续核对" : retryable ? metadataJob.planId ? "查看待确认同步" : "同步已保存修改" : "保存并同步";
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
    const selectionMatches = (!pending?.uiSource || pending.uiSource === source)
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
    byId("reviewToggle").textContent = reviewExpanded ? "收起" : "查看 / 确认";
  }
  function initializeEmbeddedImage() {
    if (!embedded) return;
    document.documentElement.dataset.embed = "steamwork";
    byId("collectionTitle").textContent = "图库";
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
      if (["dark", "light"].includes(value.theme)) document.documentElement.dataset.theme = value.theme;
      if (["en", "zh-CN"].includes(value.language)) document.documentElement.dataset.hostLanguage = value.language;
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
    byId("operationStatus").textContent = message;
    byId("operationStatus").dataset.error = String(error);
    byId("operationStatus").dataset.tone = success ? "success" : "normal";
  }
  function dimensions(item) {
    const width = Number(item?.width), height = Number(item?.height);
    return Number.isInteger(width) && width > 0 && Number.isInteger(height) && height > 0 ? `${width} × ${height}` : "尺寸待读取";
  }
  function title(item) {
    if (standardNaming() && validStandardType(str(item?.standardType))) return str(item.standardType);
    return str(item?.displayTitle || item?.title || item?.name || item?.path?.split(/[\\/]/).at(-1)) || "未命名图片";
  }
  const originalName = item => str(item?.name || item?.path?.split(/[\\/]/).at(-1));
  const groupTitle = item => str(item?.groupTitle) || title(item);
  const variantTitle = item => str(item?.variantLabel) || "未标注方案";
  const imageKey = item => `${str(item?.space) || "root"}:${str(item?.path)}:${str(item?.sha256)}`;
  const purposeKey = item => str(item?.groupId) || groupTitle(item).normalize("NFC").toLocaleLowerCase();
  function variantNavigation({ key, count, index, label, container, select }) {
    if (count < 2) return null;
    const navigation = node("div", "variant-navigation");
    navigation.setAttribute("role", "group");
    navigation.setAttribute("aria-label", `${label}的方案浏览`);
    const move = (next, action) => {
      if (busy || pendingOperation) return;
      select((next + count) % count);
      [...byId(container).querySelectorAll("button")].find(button => button.dataset.navigatorKey === key && button.dataset.variantNavigate === action)?.focus({ preventScroll: true });
    };
    for (const [action, text, offset] of [["previous", "‹", -1], ["next", "›", 1]]) {
      const button = node("button", "variant-arrow", text);
      button.type = "button";
      button.dataset.navigatorKey = key;
      button.dataset.variantNavigate = action;
      button.disabled = busy || Boolean(pendingOperation);
      button.setAttribute("aria-label", `${label}，${offset < 0 ? "上一个" : "下一个"}方案，当前 ${index + 1} / ${count}`);
      button.addEventListener("click", () => move(index + offset, action));
      if (action === "next") {
        const position = node("span", "variant-position", `${index + 1} / ${count}`);
        position.setAttribute("role", "status");
        position.setAttribute("aria-live", "polite");
        position.setAttribute("aria-label", `${label}，第 ${index + 1} 个，共 ${count} 个方案`);
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
    for (const id of ["scanImages", "syncImages", "imageFiles", "pasteImages", "imagePasteCommand"]) byId(id).disabled = busy || !root || Boolean(pendingOperation);
    if (busy || pendingOperation || !root) closePasteMenu();
    byId("dropZone").setAttribute("aria-disabled", String(busy || !root || Boolean(pendingOperation)));
    byId("dropZone").tabIndex = busy || !root || pendingOperation ? -1 : 0;
    byId("imageGrid").setAttribute("aria-busy", String(busy));
    byId("operationStatus").dataset.busy = String(busy);
    byId("checkOperation").hidden = !pendingOperation || busy;
    byId("checkOperation").disabled = busy;
    if (pendingOperation) byId("syncImages").disabled = true;
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
    byId("reviewApply").textContent = unresolved ? `还有 ${unresolved} 项待选择` : untyped ? `还有 ${untyped} 项待明确用途` : selected.length ? `确认所选 ${selected.length} 项` : "先选择处理方式";
    byId("decisionSummary").textContent = selected.length ? `已选择 ${selected.length} 项${unresolved ? `，还有 ${unresolved} 项待选择` : ""}${untyped ? `；${untyped} 项请先在方案信息中选择标准用途` : ""}` : "重复和替换候选需要你选择处理方式。";
    if (reviewNeedsScan && plan) {
      byId("reviewApply").disabled = true;
      byId("reviewApply").textContent = "重新检查图片后确认";
      byId("decisionSummary").textContent = "名称已变化，请重新检查图片；原选择已保留。";
    }
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
    try { value = await response.json(); } catch (_) { throw new Error("暂时无法读取图片服务，当前图片与选择已保留。"); }
    if (!response.ok || value?.ok === false) {
      const code = str(value?.code || value?.error);
      const error = new Error(errors[code] || str(value?.message) || str(value?.error) || `这次操作未完成（${response.status}），当前选择已保留。`);
      error.code = code;
      error.httpStatus = response.status;
      throw error;
    }
    return value;
  }
  function assertCurrent(token, expectedRoot) {
    return token === generation && (!expectedRoot || expectedRoot === root);
  }
  async function run(message, task) {
    if (busy) return;
    busy = true;
    const token = ++generation;
    const expectedRoot = root;
    notice(message);
    updateControls();
    try { await task(token, expectedRoot); }
    catch (error) {
      if (assertCurrent(token, expectedRoot)) {
        if (pendingOperation?.metadataJob) {
          rememberMetadataJob({ ...pendingOperation.metadataJob, status: "unknown", message: `已保存到本地；同步未完成。${error.message || "请继续核对原请求。"}` });
          notice(metadataJob.message, true);
        } else notice(error.message || "这次操作未完成，当前选择已保留。", true);
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
    if (root && nextRoot && nextRoot !== root) throw new Error(errors.root_changed);
    if (nextRoot) root = nextRoot;
    state = { ...(state || {}), ...value };
    byId("rootSummary").textContent = root || "尚未选择图库";
    byId("rootSummary").dataset.connected = String(Boolean(root));
    byId("deviceSummary").textContent = str(state.deviceRoot) || "使用本地图库";
    byId("deviceSummary").dataset.connected = String(Boolean(state.deviceRoot || root));
    const connected = state.notionAvailable === true || state.notion?.canAttempt === true || state.notion?.available === true;
    const verified = state.notion?.verified === true || state.notionAvailable === true;
    byId("notionSummary").textContent = verified ? "已连接" : connected ? "可同步 · 首次将核验连接" : state.notionPage ? "已保存目标 · 连接待就绪" : "未配置 · 连接待就绪";
    byId("notionSummary").dataset.connected = String(verified);
    byId("notionConfigNote").textContent = verified ? "已核验连接，可在下方选择同步方向。" : connected ? "可选择同步；首次操作会核验页面与附件访问。" : "目前可保存页面地址；Notion 同步连接尚未就绪。";
    for (const select of [byId("syncSource"), byId("syncTarget")]) {
      const option = select.querySelector('option[value="notion"]');
      option.disabled = !connected;
      option.textContent = connected ? "Notion" : "Notion · 连接待就绪";
      if (select.value === "notion" && !connected) select.value = select.id === "syncSource" ? "local" : "console";
    }
    byId("inboxCount").textContent = `inbox ${Number.isInteger(state.inboxCount) ? state.inboxCount : 0}`;
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
    byId("lastSync").textContent = date && !Number.isNaN(date.getTime()) ? `上次同步 ${date.toLocaleString("zh-CN", { hour12: false })}` : "尚无同步记录";
    renderCollection();
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
    if (value.root && value.root !== root) throw new Error(errors.root_changed);
    const previousId = planId(plan);
    plan = value;
    reviewNeedsScan = false;
    if (previousId !== planId(plan)) decisions = new Map();
    const currentIds = new Set(plan.candidates.map(candidate => str(candidate.id)));
    decisions = new Map([...decisions].filter(([id]) => currentIds.has(id)));
    for (const candidate of plan.candidates) {
      const id = str(candidate.id);
      if (!decisions.has(id) && candidate.status === "new" && !candidate.previousCandidateId) decisions.set(id, "add");
    }
    restoreDecisions();
    rememberDecisions();
    renderPlan();
  }
  function createThumbnail(item, label) {
    const button = node("button", "thumbnail-button");
    button.type = "button";
    button.setAttribute("aria-label", `放大查看${label || title(item)}，${dimensions(item)}`);
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
    return button;
  }
  function metadataButton(item) {
    if (item?.space === "device") return node("p", "image-path", "设备副本 · 在本地图库编辑方案信息");
    const button = node("button", "metadata-button", "方案信息");
    button.type = "button";
    button.dataset.metadataPath = str(item?.path);
    button.disabled = busy || Boolean(pendingOperation) || !item?.path || !item?.sha256;
    button.setAttribute("aria-label", standardNaming() ? `编辑${title(item)}的标准用途和方案信息` : `编辑${title(item)}的方案信息，保留原文件名`);
    button.addEventListener("click", () => openMetadata(item, button));
    return button;
  }
  function imageDetails(item, path = true) {
    const content = node("div", "image-details");
    content.append(node("p", "image-title", title(item)), node("span", "image-dimensions", dimensions(item)));
    if (path && item.path) content.append(node("p", "image-path", `原文件：${str(item.path)}`));
    if (item.variantLabel) content.append(node("p", "image-path", `${variantTitle(item)}${item.derivedFromId ? " · 派生尺寸" : item.pendingDerivedFromId ? " · 派生来源待同步 / 待关联" : ""}`));
    if (item.sha256) {
      const details = node("details", "hash-details");
      details.append(node("summary", "", "文件指纹"), node("code", "", str(item.sha256)));
      content.append(details);
    }
    content.append(metadataButton(item));
    return content;
  }
  function comparisonSide(item, label) {
    const side = node("div", "comparison-side");
    side.append(node("p", "side-label", label));
    if (item) side.append(createThumbnail(item, label), imageDetails(item));
    else side.append(node("div", "empty-comparison", "还没有对应图片"));
    return side;
  }
  function candidateReason(candidate) {
    if (candidate.reason) return str(candidate.reason);
    if (candidate.matchReason === "bytes") return "文件指纹相同，内容完全一致。可以保留已有图片，避免重复收录。";
    if (candidate.matchReason === "pixels") return "像素内容相同，可能使用不同格式。请比较后选择保留或替换。";
    if (candidate.status === "duplicate") return candidate.incoming?.sha256 && candidate.incoming.sha256 === candidate.existing?.sha256 ? "文件内容完全相同。可以保留已有图片，避免重复收录。" : "检测到相同图像内容，可能使用了不同格式；请比较后选择。";
    if (candidate.status === "ambiguous") return "存在多个匹配，请核对标题、尺寸和图片内容，再选择处理方式。";
    if (candidate.status === "conflict") return "同标题与尺寸已有图片，内容不同。可以用新图替换，也可以保留为另一方案。";
    return "新图片，确认后加入图库。";
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
    byId("reviewCount").textContent = `${candidates.length} 项待确认`;
    if (embedded) byId("reviewTitle").textContent = state?.inboxCount ? "Inbox" : "图片确认";
    setReviewExpanded(reviewExpanded);
    const next = readContinuation(planId(plan));
    byId("reviewNote").textContent = next ? `确认这些图片后，将自动继续同步到${next.target === "notion" ? " Notion" : "设备文件夹"}${next.next ? "及额外设备文件夹" : ""}。重复与替换候选由你选择。` : "每张图片分别选择；确认会处理全部候选。同用途、同尺寸可左右切换，冲突卡保留新旧对照。";
    byId("planWarnings").hidden = warnings.length === 0;
    byId("planWarnings").textContent = warnings.length ? `以下 ${warnings.length} 项未处理：\n${warnings.slice(0, 6).map(value => typeof value === "string" ? value : `${str(value.path || value.file)} ${str(value.error || value.message)}`).join("\n")}${warnings.length > 6 ? "\n其余记录保留在本次检查中。" : ""}` : "";
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
      heading.append(node("h3", "", title(incoming || existing)), node("span", "match-tag", statusLabels[candidate.status] || "请比较图片"));
      const currentPurpose = groupTitle(incoming || existing);
      const samePurpose = (Array.isArray(state?.items) ? state.items : []).filter(item => incoming?.groupId && item.groupId ? incoming.groupId === item.groupId : groupTitle(item).normalize("NFC").toLocaleLowerCase() === currentPurpose.normalize("NFC").toLocaleLowerCase());
      const purposeSchemes = new Set(samePurpose.map(schemeKey)).size;
      const purpose = node("p", "candidate-purpose", `用途：${currentPurpose}${purposeSchemes ? ` · 已有 ${purposeSchemes} 个方案` : ""}`);
      const comparison = node("div", compact ? "compact-preview" : "comparison");
      if (compact) {
        comparison.append(createThumbnail(incoming), node("span", "image-dimensions", dimensions(incoming)));
        if (incoming?.variantLabel) comparison.append(node("p", "compact-variant-label", `${variantTitle(incoming)}${incoming.derivedFromId ? " · 派生尺寸" : incoming.pendingDerivedFromId ? " · 派生来源待同步 / 待关联" : ""}`));
        comparison.append(metadataButton(incoming));
      }
      else comparison.append(comparisonSide(incoming, "新图片 / 同步来源"));
      if (!compact && !existing && matches.length) {
        const side = node("div", "comparison-side");
        side.append(node("p", "side-label", `已有图片 / ${matches.length} 张匹配`));
        for (const match of matches) {
          const matchView = node("div", "match-preview");
          matchView.append(createThumbnail(match, "已有图片"), imageDetails(match));
          side.append(matchView);
        }
        comparison.append(side);
      } else if (!compact) comparison.append(comparisonSide(existing, "已有图片 / 同步目标"));
      const choices = node("fieldset", "decision-choices");
      choices.append(node("legend", "visually-hidden", `${title(incoming || existing)}的处理方式`));
      const identical = ["bytes", "pixels"].includes(candidate.matchReason) || candidate.status === "duplicate";
      const addLabel = identical ? "另存副本" : "保留为另一方案";
      const options = existing ? [["replace", "用新图替换"], ["keep", "保留已有"], ["add", addLabel]] : matches.length ? [["keep", "保留现状"], ["add", addLabel]] : [["add", "加入图库"], ["keep", "暂不加入"]];
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
      if (standardNaming()) card.append(node("p", "candidate-standard-name", incoming?.standardName && !needsStandardPurpose(candidate) ? `${incoming.standardType ? "采用后" : `建议用途 ${str(incoming.suggestedStandardType)} · 确认采用后`}：${str(incoming.standardName)}` : "采用前请在「方案信息」中选择标准用途。"));
      const navigation = variantNavigation({ key: selectionKey, count: groupCandidates.length, index: groupCandidates.indexOf(candidate),
        label: `${currentPurpose}，${dimensions(incoming)}`, container: "candidateList", select: index => {
          candidateSelections.set(selectionKey, str(groupCandidates[index].id));
          renderPlan();
        } });
      if (navigation) card.append(navigation);
      if (!compact) card.append(node("p", "candidate-reason", candidateReason(candidate)));
      card.append(choices);
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
    const filtered = [...groups.values()].filter(group => !query || group.items.some(item => `${group.title} ${title(item)} ${str(item.title)} ${variantTitle(item)} ${dimensions(item)} ${str(item.path)}`.toLocaleLowerCase().includes(query)));
    byId("libraryCount").textContent = `${items.length} 张`;
    byId("collectionNote").textContent = query ? `找到 ${filtered.length} 组，组内所有尺寸和方案均可查看。` : `${groups.size} 组 · ${items.length} 张图片。按用途与标题分组，选择尺寸和方案查看原图。`;
    byId("imageGrid").replaceChildren();
    for (const group of filtered) byId("imageGrid").append(renderGroup(group));
    byId("emptyState").hidden = filtered.length !== 0;
    byId("emptyState").querySelector("h3").textContent = query ? "没有匹配的图片" : "你的图片，从这里开始";
    byId("emptyState").querySelector("p").textContent = query ? "换一个标题或尺寸试试。" : "保存图库位置，放入图片，再点「检查图片」。";
  }
  function renderGroup(group) {
    const key = `${root}:${group.id}`;
    const sizes = [...new Set(group.items.map(dimensions))];
    const selection = groupSelections.get(key) || { size: sizes[0], image: imageKey(group.items[0]) };
    if (!sizes.includes(selection.size)) selection.size = sizes[0];
    const variants = group.items.filter(item => dimensions(item) === selection.size);
    const selected = variants.find(item => imageKey(item) === selection.image) || variants[0];
    selection.image = imageKey(selected);
    groupSelections.set(key, selection);
    const card = node("article", "asset-group-card");
    card.dataset.groupId = group.id;
    card.dataset.currentPath = str(selected.path);
    const header = node("div", "asset-group-header");
    const schemeCount = new Set(group.items.map(schemeKey)).size;
    header.append(node("h3", "", group.title), node("span", "asset-group-stats", `${schemeCount} 方案 · ${sizes.length} 尺寸`));
    const sizeField = node("label", "asset-size-field");
    const select = node("select");
    select.dataset.variantSize = "true";
    select.disabled = busy || Boolean(pendingOperation);
    select.setAttribute("aria-label", `${group.title}的尺寸`);
    for (const size of sizes) {
      const option = node("option", "", `${size} · ${group.items.filter(item => dimensions(item) === size).length} 张`);
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
    sizeField.append(node("span", "", "尺寸"), select);
    const preview = node("div", "asset-group-preview");
    preview.append(createThumbnail(selected), node("p", "asset-variant-summary", `${variantTitle(selected)} · ${dimensions(selected)}`));
    if (selected.derivedFromId) preview.append(node("span", "derivative-badge", "派生尺寸 · 已关联来源"));
    else if (selected.pendingDerivedFromId) preview.append(node("span", "derivative-badge", "派生来源待同步 / 待关联"));
    if (selected.hasTransparency === true) preview.append(node("span", "transparency-badge", "含透明区域"));
    const navigation = variantNavigation({ key, count: variants.length, index: variants.indexOf(selected),
      label: `${group.title}，${selection.size}`, container: "imageGrid", select: index => {
        selection.image = imageKey(variants[index]);
        renderCollection();
      } });
    if (navigation) preview.append(navigation);
    const footer = node("div", "asset-group-footer");
    footer.append(node("p", "image-path", `原文件：${str(selected.path)}`), metadataButton(selected));
    card.append(header, sizeField, preview, footer);
    return card;
  }
  function publishPreviewState(open) {
    if (embedded) window.parent.postMessage({ channel: "console-image-embed-v1", type: "preview", open }, window.location.origin);
  }
  function showPreview(item, trigger) {
    previewFocus = trigger;
    const image = node("img");
    image.alt = title(item);
    image.src = previewUrl(item);
    byId("previewTitle").textContent = title(item);
    byId("previewMeta").textContent = `${dimensions(item)}${item.path ? ` · ${str(item.path)}` : ""}`;
    byId("previewImageWrap").replaceChildren(image);
    byId("previewDialog").showModal();
    publishPreviewState(true);
  }
  function openMetadata(item, trigger) {
    if (busy || pendingOperation || byId("namingDialog").open || !item?.path || !item?.sha256 || item.space === "device") return;
    metadataTarget = { ...item, expectedRoot: root, expectedPageId: configuredPageId(), expectedDeviceRoot: str(state?.deviceRoot),
      indexed: (state?.items || []).some(current => current.path === item.path && current.sha256 === item.sha256 && current.space !== "device") };
    metadataFocus = trigger;
    byId("metadataOriginal").textContent = `原文件：${str(item.path)} · ${dimensions(item)}`;
    byId("metadataGroupTitle").value = groupTitle(item);
    fillStandardTypes(byId("metadataStandardType"), str(item.standardType || item.suggestedStandardType));
    byId("metadataVariantLabel").value = str(item.variantLabel);
    const sources = byId("metadataDerivedFrom");
    sources.replaceChildren();
    const none = node("option", "", "原始素材 / 未关联来源");
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
      const existing = node("option", "", "已关联的来源（当前图库未显示）");
      existing.value = str(item.derivedFromId);
      sources.append(existing);
    }
    if (!item.derivedFromId && item.pendingDerivedFromId) {
      const pending = node("option", "", "派生来源待同步 / 待关联（保留现有记录）");
      pending.value = "__pending_source__";
      sources.append(pending);
    }
    sources.value = !item.derivedFromId && item.pendingDerivedFromId ? "__pending_source__" : str(item.derivedFromId);
    metadataBaseline = standardNaming() ? JSON.stringify([str(item.standardType), byId("metadataVariantLabel").value.trim(), sources.value]) : metadataValues();
    updateMetadataName();
    metadataJob = null;
    try {
      const saved = JSON.parse(sessionStorage.getItem(metadataJobKey(metadataTarget)) || "null");
      if (saved?.root === root && saved.path === item.path && saved.sha256 === item.sha256) metadataJob = saved;
    } catch (_) { /* Optional saved sync status. */ }
    byId("metadataStatus").textContent = metadataDirty() ? "标准用途建议尚未保存，确认后才会采用。" : metadataJob?.message || "尚无未保存的修改。";
    byId("metadataStatus").dataset.error = "false";
    byId("metadataDialog").showModal();
    updateMetadataControls();
    byId("metadataGroupTitle").focus();
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
    await run(dirty ? "正在保存方案信息…" : "正在同步已保存修改…", async (token, expectedRoot) => {
      byId("metadataStatus").textContent = dirty ? "正在保存…" : "正在同步已保存修改…";
      byId("metadataStatus").dataset.error = "false";
      try {
        requireMetadataScope(snapshot, token, expectedRoot);
        if (dirty) {
          const value = await call("metadata", { payload });
          const item = metadata(value.item);
          const renamed = metadata(value.renamed);
          let savedPath = snapshot.path;
          if (renamed && Object.keys(renamed).length) {
            if (!snapshot.indexed || renamed.from !== snapshot.path || renamed.to !== item?.path || renamed.sha256 !== snapshot.sha256 || !safeImagePath(renamed.to)) throw new Error("改名回执与本次原图不一致，已停止同步，填写内容已保留。");
            savedPath = renamed.to;
          }
          if (item && (item.path !== savedPath || item.sha256 !== snapshot.sha256)) throw new Error("保存回执对应的原图已改变，已停止同步，填写内容已保留。");
          const savedSnapshot = { ...snapshot, path: savedPath };
          requireMetadataScope(savedSnapshot, token, expectedRoot, value.state || state);
          if (!acceptResponse(value, token, expectedRoot)) return;
          if (snapshot.indexed && savedPath !== snapshot.path) invalidateReviewAfterNaming(value.state);
          if (item) { updatePlanMetadata(item, snapshot); metadataTarget = { ...metadataTarget, ...item }; }
          if (savedPath !== snapshot.path) {
            try { sessionStorage.removeItem(metadataJobKey(snapshot)); } catch (_) { /* Optional saved-sync status. */ }
            byId("metadataOriginal").textContent = `当前文件：${savedPath} · ${dimensions(item)}`;
          }
          updateMetadataName();
          metadataBaseline = metadataValues();
          const targets = [...(configuredPageId() ? ["notion"] : []), ...(state?.deviceRoot ? ["device"] : [])];
          rememberMetadataJob({ ...savedSnapshot, annotationFingerprint: annotationFingerprint(value.item || metadataTarget), targets, completed: [], status: !snapshot.indexed ? "inbox" : targets.length ? "saved" : "local",
            message: !snapshot.indexed ? "已保存到 Inbox，确认入库后再同步；尚未发布这张图片。" : targets.length ? "已保存到本地，待同步。" : "已保存到本地；尚未配置外部同步位置。" });
        }
      } catch (error) {
        byId("metadataStatus").textContent = error.message || "保存未完成，填写内容已保留。";
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
        rememberMetadataJob({ ...job, status: "completed", planId: "", message: "已保存，并同步到全部已配置位置。" });
        notice(metadataJob.message, false, true);
        return;
      }
      if (target === "notion" && state?.notionAvailable !== true && state?.notion?.canAttempt !== true && state?.notion?.available !== true) throw new Error("Notion 连接尚未就绪，可在连接恢复后同步已保存修改。");
      byId("syncSource").value = "console";
      byId("syncTarget").value = job.targets.length > 1 ? "all" : target;
      rememberMetadataJob({ ...job, status: "syncing", planId: "", message: `已保存到本地，正在同步${target === "notion" ? "到 Notion" : "到设备文件夹"}…` });
      await dispatchSync("console", target, token, expectedRoot, null, metadataJob);
    } catch (error) {
      const current = metadataJob || job;
      const uncertain = Boolean(pendingOperation?.metadataJob);
      rememberMetadataJob({ ...current, status: error.code === "metadata_scope_changed" ? "stale" : uncertain ? "unknown" : "failed", message: `已保存到本地；${current.completed.length ? "部分位置已同步，" : ""}同步未完成。${error.message || "请重试。"}${uncertain ? "请继续核对原请求。" : ""}` });
      notice(metadataJob.message, true);
    }
  }
  async function completeMetadataTarget(job, target, token, expectedRoot) {
    requireMetadataScope(job, token, expectedRoot);
    rememberMetadataJob({ ...job, completed: [...new Set([...job.completed, target])], status: "saved", planId: "", message: "已保存到本地，正在完成后续同步…" });
    await syncMetadataTargets(metadataJob, token, expectedRoot);
  }
  async function acceptMetadataDeviceResult(value, job, token, expectedRoot) {
    requireMetadataScope(job, token, expectedRoot, value.state || state);
    const syncPlan = extractPlan(value);
    if (!syncPlan || syncPlan.root !== job.root || syncPlan.deviceRoot !== job.deviceRoot || syncPlan.direction !== "to-device") {
      const error = new Error("设备同步计划的图库、目标位置或方向与本次保存不一致，已停止应用，请重新核对位置。");
      error.code = "metadata_scope_changed";
      throw error;
    }
    if (value.state) acceptState(value.state);
    const count = syncPlan?.candidates?.length || 0;
    if (count) {
      acceptPlan(syncPlan);
      rememberMetadataJob({ ...job, status: "review", planId: planId(syncPlan), message: "已保存到本地；设备同步有待确认的图片，请查看后确认。" });
      if (!syncPlan.errors?.length && syncPlan.candidates.every(canAutomaticallyAdd)) {
        await commitBatch({ planId: planId(syncPlan), expectedRoot, decisions: syncPlan.candidates.map(candidate => ({ id: str(candidate.id), action: "add" })) }, token, expectedRoot);
        return;
      }
      setReviewExpanded(true);
      notice(metadataJob.message);
      return;
    }
    if (value.metadataSync?.status !== "completed" || Number(value.metadataSync?.unresolved) > 0 || syncPlan?.errors?.length) throw new Error(str(value.message) || "设备方案信息尚未完整同步，请重新核对。");
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
      select.setAttribute("aria-label", `${originalName(item)}的标准用途`);
      fillStandardTypes(select, namingDrafts.get(key));
      const target = node("p", "naming-target", candidate ? `→ ${str(candidate.targetPath || candidate.target)}` : standardName(item, select.value) ? `→ ${standardName(item, select.value)}` : "请选择标准用途");
      if (candidate?.error) { target.textContent = str(candidate.error); target.dataset.error = "true"; }
      select.addEventListener("change", () => {
        if (busy || pendingOperation) return;
        namingDrafts.set(key, select.value); rememberNamingDraft(); namingPlan = null; namingScope = null;
        byId("namingStatus").textContent = "用途选择尚未应用，请先预览标准名称。";
        renderNamingList(); updateNamingControls();
      });
      row.append(createThumbnail(item), content, select, target); list.append(row);
    }
    if (focusKey) [...list.querySelectorAll("select")].find(select => select.dataset.namingKey === focusKey)?.focus({ preventScroll: true });
  }
  function openNaming(event) {
    if (busy || pendingOperation || !root || byId("metadataDialog").open || byId("previewDialog").open || !standardTypes().length) return;
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
    byId("namingStatus").textContent = namingPlan ? "已恢复名称预览，确认后才会整理文件。" : "先明确标准用途，再预览旧名称与新名称。";
    byId("namingStatus").dataset.error = "false";
    renderNamingList(); updateNamingControls(); byId("namingDialog").showModal();
    (byId("namingList").querySelector("select") || byId("namingClose")).focus();
  }
  async function previewNaming() {
    if (busy || pendingOperation || !requireSavedLocations()) return;
    const entries = namingChoices();
    if (!entries.length || entries.some(entry => !validStandardType(entry.assetType))) return;
    const snapshot = namingSnapshot();
    await run("正在预览标准名称…", async (token, expectedRoot) => {
      try {
        const value = await call("naming-plan", { payload: { expectedRoot, entries } });
        if (!assertCurrent(token, expectedRoot) || !namingScopeMatches(snapshot, value.state || state)) throw new Error("图库、同步位置或原图已改变，名称预览已停止，请重新读取。");
        if (value.kind !== "naming" || !planId(value) || !Array.isArray(value.candidates)
            || value.candidates.length !== entries.length || !entries.every(entry => value.candidates.filter(candidate => candidate.fromPath === entry.path && candidate.sha256 === entry.sha256 && candidate.assetType === entry.assetType).length === 1)
            || value.canApply === true && value.candidates.some(candidate => !["rename", "unchanged"].includes(candidate.status) || !safeImagePath(candidate.targetPath))) throw new Error("名称预览与本次图片不一致，尚未应用更改。");
        if (value.state) acceptState(value.state);
        namingPlan = value; namingScope = snapshot; rememberNamingDraft(); renderNamingList();
        const message = value.canApply === true ? "请核对旧名称 → 新名称，确认后才会整理文件。" : "部分名称存在冲突，尚未应用；请检查下方记录并重新预览。";
        byId("namingStatus").textContent = message; byId("namingStatus").dataset.error = String(value.canApply !== true);
        notice(message, value.canApply !== true);
      } catch (error) { byId("namingStatus").textContent = error.message; byId("namingStatus").dataset.error = "true"; throw error; }
    });
  }
  function validateNamingReceipt(value, snapshot, expectedId, expectedCandidates = null) {
    if (planId(value) !== expectedId || !Array.isArray(value.results) || !namingScopeMatches(snapshot, value.state, true)) throw new Error("名称整理回执与本次图库或计划不一致，请保留原计划并核对。");
    const results = value.results;
    for (const result of results) {
      const source = snapshot.items.find(item => item.path === result.from && item.sha256 === result.sha256);
      const target = value.state.items?.find(item => item.path === result.to && item.sha256 === result.sha256);
      const expected = expectedCandidates?.find(candidate => candidate.fromPath === result.from && candidate.targetPath === result.to && candidate.sha256 === result.sha256);
      if (!source || !target || !safeImagePath(result.to)
          || source.variantId && source.variantId !== target.variantId || source.derivedFromId && source.derivedFromId !== target.derivedFromId
          || expectedCandidates && (!expected || target.standardType !== expected.assetType || target.standardName !== expected.standardName)) throw new Error("改名结果与预览的原图不一致，未采用这份迟到回执。");
    }
    if (expectedCandidates?.some(candidate => candidate.status === "rename" && !results.some(result => result.from === candidate.fromPath && result.to === candidate.targetPath && result.sha256 === candidate.sha256))) throw new Error("部分改名结果尚未核对完成，请保留原计划并继续核对。");
  }
  async function applyNaming() {
    if (busy || pendingOperation || namingPlan?.canApply !== true || namingPlan.errors?.length) return;
    if (!requireSavedLocations()) return;
    if (namingChoices().some(entry => !validStandardType(entry.assetType)) || !namingScopeMatches(namingScope) || !namingChoicesMatch()) return;
    const preview = namingPlan, snapshot = namingScope;
    await run("正在整理已确认的文件名…", async (token, expectedRoot) => {
      try {
        const value = await call("naming-apply", { payload: { expectedRoot, planId: planId(preview) } });
        if (!assertCurrent(token, expectedRoot)) return;
        validateNamingReceipt(value, snapshot, planId(preview), preview.candidates);
        invalidateReviewAfterNaming(value.state); acceptState(value.state); namingPlan = null; namingScope = null;
        namingDrafts = new Map((state.items || []).map(item => [imageKey(item), str(item.standardType)])); rememberNamingDraft(); renderNamingList();
        const message = `标准名称已确认，已整理 ${Number(value.renamed) || 0} 张图片。图片内容与已有方案保留。`;
        byId("namingStatus").textContent = message; byId("namingStatus").dataset.error = "false"; notice(message, false, true);
      } catch (error) { byId("namingStatus").textContent = error.message; byId("namingStatus").dataset.error = "true"; throw error; }
    });
  }
  async function restoreNaming() {
    const id = planId(state?.lastNaming);
    if (busy || pendingOperation || !id) return;
    if (!requireSavedLocations()) return;
    const snapshot = namingSnapshot();
    await run("正在撤回上次名称整理…", async (token, expectedRoot) => {
      try {
        const value = await call("naming-restore", { payload: { expectedRoot, planId: id } });
        if (!assertCurrent(token, expectedRoot)) return;
        validateNamingReceipt(value, snapshot, id);
        if (value.restored !== true) throw new Error("撤回结果尚未确认，请保留记录并核对。");
        invalidateReviewAfterNaming(value.state); acceptState(value.state); namingPlan = null; namingScope = null;
        namingDrafts = new Map((state.items || []).map(item => [imageKey(item), str(item.standardType)])); rememberNamingDraft(); renderNamingList();
        byId("namingStatus").textContent = "已撤回上次名称整理。"; byId("namingStatus").dataset.error = "false"; notice("已撤回上次名称整理。", false, true);
      } catch (error) { byId("namingStatus").textContent = error.message; byId("namingStatus").dataset.error = "true"; throw error; }
    });
  }
  async function loadState() {
    await run("正在读取图库…", async (token, expectedRoot) => {
      const value = await call("state");
      if (!assertCurrent(token, expectedRoot)) return;
      acceptState(value.state || value, { refill: true });
      const savedPlan = extractPlan(value) || extractPlan(value.state);
      if (savedPlan) acceptPlan(savedPlan);
      notice(savedPlan?.candidates?.length ? "已恢复上次的图片比较，可以继续选择。" : root ? "就绪。放入图片后，点「检查图片」查看新增和重复候选。" : "先保存本地图库位置。", false);
      const active = value.operation || value.state?.operation || state?.notion?.operation;
      let saved;
      try { saved = JSON.parse(localStorage.getItem(operationKey()) || "null"); } catch (_) { /* The server can also restore its operation. */ }
      if (saved?.requestId || (active?.requestId && (pendingStatuses.has(active.status) || active.status === "unknown" || canRecheckOperation(active)))) {
        pendingOperation = saved?.requestId ? saved : { requestId: active.requestId, autoApply: true };
        if (pendingOperation.metadataJob) metadataJob = pendingOperation.metadataJob;
        const restoreSource = pendingOperation.uiSource || active?.source;
        const restoreTarget = pendingOperation.uiTarget || active?.target;
        if (["local", "console", "notion"].includes(restoreSource)) byId("syncSource").value = restoreSource;
        if (["console", "device", "notion", "all"].includes(restoreTarget)) byId("syncTarget").value = restoreTarget;
        await pollOperation(active?.requestId === pendingOperation.requestId ? active : { requestId: pendingOperation.requestId, status: "pending" }, token, root);
      }
    });
  }
  async function saveConfig(event) {
    event.preventDefault();
    const nextRoot = byId("libraryRoot").value.trim();
    if (!nextRoot) return;
    const payload = { root: nextRoot, deviceRoot: byId("deviceRoot").value.trim(), notionPage: byId("notionPage").value.trim(), expectedRoot: root };
    await run("正在保存图库位置…", async (token, expectedRoot) => {
      const value = await call("config", { payload });
      if (!assertCurrent(token, expectedRoot)) return;
      const nextState = value.state || value;
      const actualRoot = str(nextState.root);
      if (!actualRoot) throw new Error("保存结果没有返回图库位置，请重新读取确认。");
      if (actualRoot !== root) { root = ""; state = null; plan = null; reviewNeedsScan = false; pendingOperation = null; lastApplied = null; decisions = new Map(); renderPlan(); }
      acceptState(nextState, { refill: true });
      const savedPlan = extractPlan(value) || extractPlan(nextState);
      if (savedPlan) acceptPlan(savedPlan);
      byId("configStatus").textContent = "位置已保存";
      byId("locations").open = false;
      notice("位置已保存，可以放入图片或选择同步方向。", false, true);
    });
  }
  async function scanImages() {
    await run("正在检查图库与 inbox…", async (token, expectedRoot) => {
      const value = await call("scan", { payload: { expectedRoot } });
      if (!acceptResponse(value, token, expectedRoot)) return;
      const count = plan?.candidates?.length || 0;
      notice(count ? `检查完成，${count} 项图片待确认。` : "检查完成，没有待处理的图片。", false, true);
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
    await run(`正在把 ${files.length} 张图片放进 inbox…`, (token, expectedRoot) => stageUpload(files, token, expectedRoot));
    byId("imageFiles").value = "";
  }
  function validateUploadSize(files) {
    if (files.length > 50) throw new Error("每批最多加入 50 张图片，请分批放入 Inbox。");
    const configuredLimit = Number(state?.limits?.maxFileBytes);
    const byteLimit = Math.min(64 * 1024 * 1024, Number.isFinite(configuredLimit) && configuredLimit > 0 ? configuredLimit : Infinity);
    if (files.some(file => file.size > byteLimit)) throw new Error(`有图片超过单张 ${Math.floor(byteLimit / 1024 / 1024)} MiB 限制，请分开检查后再加入。`);
    if (files.reduce((total, file) => total + (Number(file.size) || 0), 0) > 96 * 1024 * 1024) throw new Error("本次图片超过 96 MiB，请分批加入 Inbox。");
  }
  async function stageUpload(files, token, expectedRoot) {
    if (!assertCurrent(token, expectedRoot)) return;
    validateUploadSize(files);
    const form = new FormData();
    form.append("expectedRoot", expectedRoot);
    for (const file of files) form.append("files", file, file.name);
    const value = await call("upload", { form });
    if (!acceptResponse(value, token, expectedRoot)) return;
    notice("图片已放进 inbox。比较新旧图片并确认处理方式后，再应用更改。", false, true);
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
    if (busy || pendingOperation || !root || byId("metadataDialog").open || byId("previewDialog").open || byId("namingDialog").open
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
    const menu = byId("imagePasteMenu");
    menu.style.setProperty("--image-paste-x", `${Number.isFinite(event.clientX) ? event.clientX : 8}px`);
    menu.style.setProperty("--image-paste-y", `${Number.isFinite(event.clientY) ? event.clientY : 8}px`);
    menu.hidden = false;
    byId("dropZone").setAttribute("aria-expanded", "true");
    byId("imagePasteCommand").focus({ preventScroll: true });
  }
  function clipboardFiles(blobs) {
    const stamp = new Date().toISOString().replace(/[^0-9]/g, "").slice(0, 17);
    const images = blobs.filter(blob => str(blob?.type).toLowerCase().startsWith("image/"));
    if (!images.length) throw new Error("剪贴板里没有可用图片。请先复制图片，或把图片拖到这里。");
    if (images.some(blob => !clipboardImageTypes.has(str(blob.type).toLowerCase()))) throw new Error("这种剪贴板图片格式暂不支持，请使用 PNG、JPEG、WebP、GIF、BMP、TIFF 或 ICO。");
    if (images.some(blob => !Number.isFinite(blob.size) || blob.size <= 0)) throw new Error("剪贴板图片为空，尚未加入 Inbox。请重新复制图片或拖入文件。");
    validateUploadSize(images);
    return images.map((blob, index) => {
      const type = str(blob.type).toLowerCase();
      return new File([blob], `Clipboard-${stamp}-${index + 1}.${clipboardImageTypes.get(type)}`, { type });
    });
  }
  async function readClipboardImages() {
    if (typeof navigator === "undefined" || typeof navigator.clipboard?.read !== "function") throw new Error("此处暂时不能直接读取剪贴板。请聚焦图片区域后按 Ctrl+V，或拖入图片。");
    let items;
    try { items = await navigator.clipboard.read(); }
    catch (_) { throw new Error("未能读取剪贴板图片。请允许浏览器粘贴，或聚焦图片区域后按 Ctrl+V、拖入图片。"); }
    const blobs = [];
    for (const item of items || []) {
      const type = [...(item.types || [])].find(type => clipboardImageTypes.has(str(type).toLowerCase()));
      if (!type) {
        if ((item.types || []).some(type => str(type).toLowerCase().startsWith("image/"))) throw new Error("这种剪贴板图片格式暂不支持，请复制 PNG 或 JPEG 图片。");
        continue;
      }
      let blob;
      try { blob = await item.getType(type); }
      catch (_) { throw new Error("未能读取剪贴板图片。请聚焦图片区域后按 Ctrl+V，或拖入图片。"); }
      if (str(blob?.type).toLowerCase() !== str(type).toLowerCase()) throw new Error("剪贴板图片格式未能确认，请重新复制或拖入文件。");
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
    await run("正在读取剪贴板图片…", async (token, expectedRoot) => {
      const files = providedFiles ? clipboardFiles(providedFiles) : await readClipboardImages();
      const current = (value, server = false) => assertCurrent(token, expectedRoot) && !pendingOperation && root === snapshot.root
        && str(value?.root) === snapshot.root && str(value?.deviceRoot) === snapshot.deviceRoot
        && (pageId(value?.notionPage) || pageId(value?.notion?.pageId)) === snapshot.pageId
        && (!server || planId(extractPlan(value)) === snapshot.planId) && planId(plan) === snapshot.planId
        && (!server || ![value?.operation, value?.notion?.operation].some(operation => pendingStatuses.has(operation?.status) || operation?.status === "unknown" || canRecheckOperation(operation)))
        && [byId("libraryRoot").value, byId("deviceRoot").value, byId("notionPage").value].every((field, index) => field === snapshot.fields[index]);
      if (!current(state)) throw new Error("图库或同步位置已改变，已取消粘贴；请重新确认位置后再粘贴。");
      const latest = await call("state");
      if (!current(latest.state || latest, true)) throw new Error("图库、同步位置或待确认状态已改变，已取消粘贴，请重新读取后再试。");
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
    if (!requireSavedLocations()) return;
    const source = byId("syncSource").value, target = byId("syncTarget").value;
    if ((source === "notion" || target === "notion" || target === "all") && state?.notionAvailable !== true && state?.notion?.canAttempt !== true && state?.notion?.available !== true) { notice(errors.notion_unavailable, true); return; }
    await run("正在检查同步内容…", async (token, expectedRoot) => {
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
  async function dispatchSync(source, target, token, expectedRoot, after = null, savedMetadata = null) {
    if (!assertCurrent(token, expectedRoot)) return;
    if (savedMetadata) requireMetadataScope(savedMetadata, token, expectedRoot);
    const requestId = savedMetadata?.deviceRequestId && target === "device" ? savedMetadata.deviceRequestId : crypto.randomUUID();
    if (savedMetadata && target === "device") {
      savedMetadata = { ...savedMetadata, deviceRequestId: requestId };
      rememberMetadataJob(savedMetadata);
    }
    const isNotion = source === "notion" || target === "notion";
    if (isNotion) {
      pendingOperation = { requestId, autoApply: !savedMetadata, after, ...(savedMetadata ? { metadataJob: savedMetadata } : {}), root: expectedRoot, source, target,
        pageId: configuredPageId(), uiSource: byId("syncSource").value, uiTarget: byId("syncTarget").value };
      try { localStorage.setItem(operationKey(), JSON.stringify(pendingOperation)); } catch (_) { /* The server persists its own operation. */ }
      notice(source === "notion" ? "正在从 Notion 同步图片…" : "正在同步到 Notion…");
    } else notice("正在检查设备文件夹的同步内容…");
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
      if (target !== "device") throw new Error("Notion 未返回可核对的同步回执，已保留本地修改。");
      await acceptMetadataDeviceResult(value, savedMetadata, token, expectedRoot);
      return;
    }
    await finishSync(value, token, expectedRoot, true, after);
  }
  async function continueSync(instruction, token, expectedRoot) {
    if (instruction.target === "device" && instruction.deviceRoot !== undefined && instruction.deviceRoot !== str(state?.deviceRoot)) throw new Error("额外设备文件夹已改变，已暂停后续同步，请重新选择目标。");
    if (instruction.target === "notion" && instruction.notionPage !== undefined && instruction.notionPage !== str(state?.notionPage)) throw new Error("Notion 目标页面已改变，已暂停后续同步，请重新选择目标。");
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
      notice(`正在同步 ${count} 张新图片…`);
      await commitBatch({ planId: planId(syncPlan), expectedRoot, decisions: syncPlan.candidates.map(candidate => ({ id: str(candidate.id), action: "add" })) }, token, expectedRoot);
      return;
    }
    if (!count && errorCount) { notice(`有 ${errorCount} 项图片未能读取，后续同步已暂停，请先检查下方记录。`, true); return; }
    if (!count && after && validInstruction(after)) {
      if (syncPlan) clearContinuation(planId(syncPlan));
      await continueSync(after, token, expectedRoot);
      return;
    }
    notice(count ? `已准备 ${count} 项同步内容，确认下方选择后${after ? "自动继续同步" : "执行"}。` : str(value.message) || "同步检查完成，没有待处理的差异。", false, true);
    if (count) { setReviewExpanded(true); byId("reviewSection").scrollIntoView({ behavior: "smooth", block: "start" }); }
  }
  function operationMessage(operation) {
    const stages = { queued: "等待开始", starting: "准备同步", connecting: "连接 Notion", verifying: "核验页面与附件", listing: "读取图片清单", scanning: "检查图片", downloading: "下载原图", uploading: "上传原图", reading: "读取 Notion 页面", fetching: "读取 Notion 页面", planning: "准备图片比较", applying: "保存图片", verifying_download: "核对下载原图", verify: "核验图片", completed: "同步完成" };
    const stage = stages[operation.stage || operation.phase] || (pendingStatuses.has(operation.status) ? "正在同步，请稍候" : "正在核对同步结果");
    return `${stage}…`;
  }
  async function pollOperation(initial, token, expectedRoot) {
    const requestId = str(initial?.requestId || pendingOperation?.requestId);
    if (!requestId) throw new Error("同步未返回可核对的记录，请保留页面并重新读取状态。");
    if (pendingOperation?.requestId && pendingOperation.requestId !== requestId) throw new Error("返回的同步记录与本次请求不同，请继续核对原请求。");
    pendingOperation = { ...pendingOperation, requestId, autoApply: pendingOperation?.autoApply !== false,
      after: validInstruction(pendingOperation?.after) ? pendingOperation.after : null,
      root: pendingOperation?.root || initial.root, source: pendingOperation?.source || initial.source,
      target: pendingOperation?.target || initial.target, pageId: pendingOperation?.pageId || pageId(initial.pageId),
      uiSource: pendingOperation?.uiSource || byId("syncSource").value, uiTarget: pendingOperation?.uiTarget || byId("syncTarget").value };
    try { localStorage.setItem(operationKey(), JSON.stringify(pendingOperation)); } catch (_) { /* Optional storage. */ }
    let operation = initial;
    while (assertCurrent(token, expectedRoot)) {
      if (operation.root && operation.root !== expectedRoot) throw new Error("同步回执对应另一个图库，原请求已保留，请继续核对。");
      const savedMetadata = pendingOperation.metadataJob;
      if (savedMetadata) {
        requireMetadataScope(savedMetadata, token, expectedRoot);
        if (operation.root !== expectedRoot || operation.source !== "console" || operation.target !== "notion"
            || pageId(operation.pageId) !== savedMetadata.pageId) throw new Error("同步回执的图库、页面或方向已改变，已保留本地修改与原请求。");
      }
      if (completeStatuses.has(operation.status)) {
        const autoApply = pendingOperation.autoApply;
        const after = pendingOperation.after;
        const latest = await call("state");
        if (!assertCurrent(token, expectedRoot)) return;
        const nextState = latest.state || latest;
        if (savedMetadata) {
          requireMetadataScope(savedMetadata, token, expectedRoot, nextState);
          if (operation.status !== "completed" || Array.isArray(operation.remainingTargets) && operation.remainingTargets.length) throw new Error("Notion 尚未完整确认同步结果，请继续核对原请求。");
          acceptState(nextState);
          clearOperation();
          await completeMetadataTarget(savedMetadata, "notion", token, expectedRoot);
          return;
        }
        const savedPlan = extractPlan(latest) || extractPlan(nextState);
        const resultPlan = extractPlan(operation.result);
        if (operation.planId && planId(resultPlan || savedPlan) !== operation.planId) throw new Error("同步的图片比较记录尚未对应，原请求已保留，请继续核对。");
        const syncPlan = resultPlan || (operation.planId ? savedPlan : null);
        if (operation.status === "needs_review" && !syncPlan) throw new Error("同步尚未返回匹配的图片比较记录，请继续核对。");
        clearOperation();
        if (syncPlan) { plan = null; decisions = new Map(); renderPlan(); }
        const value = { ...(operation.result || {}), state: nextState, ...(syncPlan ? { plan: syncPlan } : {}), message: str(operation.message || operation.result?.message) };
        await finishSync(value, token, expectedRoot, autoApply && Boolean(operation.planId && planId(syncPlan) === operation.planId), after);
        return;
      }
      if (operation.status && !pendingStatuses.has(operation.status)) {
        if (["failed", "error", "cancelled", "canceled"].includes(operation.status) && !canRecheckOperation(operation)) clearOperation();
        throw new Error(str(operation.error?.message || operation.error || operation.message) || "同步尚未完成，原请求已保留，请继续核对。");
      }
      notice(operationMessage(operation));
      await new Promise(resolve => setTimeout(resolve, 1000));
      if (!assertCurrent(token, expectedRoot)) return;
      const value = await call("operation", { params: { requestId } });
      operation = value.operation || value;
      if (operation.requestId && operation.requestId !== requestId) throw new Error("同步回执不匹配，原请求已保留，请继续核对。");
    }
  }
  async function resumeOperation() {
    if (!pendingOperation) return;
    const savedMetadata = pendingOperation.metadataJob;
    await run("正在核对上次同步…", async (token, expectedRoot) => {
      try {
        if (savedMetadata) requireMetadataScope(savedMetadata, token, expectedRoot);
        const value = await call("operation", { params: { requestId: pendingOperation.requestId } });
        const operation = value.operation || value;
        if (canRecheckOperation(operation)) {
          const latest = await call("state");
          if (!assertCurrent(token, expectedRoot)) return;
          if (savedMetadata) requireMetadataScope(savedMetadata, token, expectedRoot, latest.state || latest);
          acceptState(latest.state || latest);
          if (!recoveryScopeMatches(operation, expectedRoot)) throw new Error("原同步的图库、页面或方向已改变，已保留原请求，不会向其他位置恢复。");
          const recovered = await call("sync", { payload: { expectedRoot, requestId: operation.requestId, source: operation.source, target: operation.target } });
          if (!assertCurrent(token, expectedRoot)) return;
          const recoveredOperation = recovered.operation || recovered;
          if (!recoveryScopeMatches(recoveredOperation, expectedRoot)) throw new Error("恢复回执与原同步范围不一致，原请求已保留，请继续核对。");
          await pollOperation(recoveredOperation, token, expectedRoot);
          return;
        }
        await pollOperation(operation, token, expectedRoot);
      } catch (error) {
        if (savedMetadata) {
          rememberMetadataJob({ ...(metadataJob || savedMetadata), status: pendingOperation ? "unknown" : "failed", message: `已保存到本地；同步未完成。${error.message || "请继续核对原请求。"}` });
          throw new Error(metadataJob.message);
        }
        throw error;
      }
    });
  }
  function reviewApply() {
    if (busy || !plan) return;
    if (reviewNeedsScan) { notice("名称已变化，请重新检查图片；原选择已保留。", true); return; }
    const selected = plan.candidates.filter(candidate => actions.has(decisions.get(str(candidate.id)))).map(candidate => ({ id: str(candidate.id), action: decisions.get(str(candidate.id)) }));
    if (!selected.length || selected.length !== plan.candidates.length) return;
    if (plan.candidates.some(candidate => decisions.get(str(candidate.id)) !== "keep" && needsStandardPurpose(candidate))) { notice("采用前请先在方案信息中明确标准用途。", true); return; }
    void applyBatch({ planId: planId(plan), expectedRoot: root, decisions: selected });
  }
  async function applyBatch(payload) {
    if (!payload || payload.expectedRoot !== root || payload.planId !== planId(plan)) { notice("图库或比较记录已变化，请重新确认。", true); return; }
    await run("正在应用已确认的图片操作…", async (token, expectedRoot) => {
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
    notice(str(value.message) || "已应用所选操作。", false, true);
    if (savedMetadata?.planId === payload.planId && savedMetadata.root === expectedRoot) {
      try { sessionStorage.removeItem(metadataPlanKey(payload.planId)); } catch (_) { /* Optional storage. */ }
      if (value.metadataSync?.status === "completed" && !Number(value.metadataSync?.unresolved)) await completeMetadataTarget(savedMetadata, "device", token, expectedRoot);
      else {
        rememberMetadataJob({ ...savedMetadata, status: "failed", planId: "", message: "已保存到本地；设备图片操作已确认，但方案信息尚未完整同步，请重新核对。" });
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
    await run("正在撤回上次本地图片操作…", async (token, expectedRoot) => {
      const value = await call("restore", { payload });
      if (!assertCurrent(token, expectedRoot)) return;
      lastApplied = null;
      plan = null;
      decisions = new Map();
      renderPlan();
      if (value.state) acceptState(value.state);
      notice("已撤回上次本地图片操作。Notion 上已保存的附件保持原状。", false, true);
    });
  }

  byId("configForm").addEventListener("submit", saveConfig);
  byId("scanImages").addEventListener("click", scanImages);
  byId("syncImages").addEventListener("click", syncImages);
  byId("checkOperation").addEventListener("click", resumeOperation);
  byId("restoreImages").addEventListener("click", restoreImages);
  byId("metadataForm").addEventListener("submit", saveMetadata);
  byId("metadataSaveOnly").addEventListener("click", event => saveMetadata(event, false));
  for (const id of ["metadataGroupTitle", "metadataStandardType", "metadataVariantLabel", "metadataDerivedFrom"]) {
    byId(id).addEventListener(["metadataDerivedFrom", "metadataStandardType"].includes(id) ? "change" : "input", () => {
      updateMetadataName();
      byId("metadataStatus").textContent = metadataDirty() ? "未保存。保存并同步会从 Console 推送本次修改。" : metadataJob?.message || "尚无未保存的修改。";
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
    byId("previewImageWrap").replaceChildren();
    publishPreviewState(false);
    previewFocus?.focus({ preventScroll: true });
  });
  const dropZone = byId("dropZone");
    const openPicker = () => { if (!busy && !pendingOperation && root) byId("imageFiles").click(); };
  dropZone.addEventListener("click", openPicker);
  dropZone.addEventListener("contextmenu", showPasteMenu);
  byId("pasteImages").addEventListener("click", pasteImageFiles);
  byId("imagePasteCommand").addEventListener("click", pasteImageFiles);
  document.addEventListener("paste", receiveImagePaste);
  document.addEventListener("pointerdown", event => { if (!byId("imagePasteMenu").contains(event.target)) closePasteMenu(); });
  document.addEventListener("keydown", event => {
    if (!byId("imagePasteMenu").hidden && ["Escape", "Tab"].includes(event.key)) {
      if (event.key === "Escape") event.preventDefault();
      closePasteMenu(event.key === "Escape");
    }
  });
  if (typeof window !== "undefined") {
    window.addEventListener("blur", () => closePasteMenu());
    window.addEventListener("resize", () => closePasteMenu());
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
