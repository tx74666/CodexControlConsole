"use strict";
(() => {
  const byId = id => document.getElementById(id);
  const phone = new URLSearchParams(location.search).get("phone") === "1";
  const endpoint = phone ? "/api/phone/resources" : "/api/resources";
  const storageKey = phone ? "console-resources-phone-view" : "console-resources-view";
  const kindLabels = { model: "模型", vfx: "VFX 特效", texture: "材质 / 贴图", hdri: "HDRI", other: "其他资源" };
  const statusLabels = { saved: "已收藏", planned: "准备使用", candidate: "候选" };
  const errorLabels = {
    revision_conflict: "资源库刚刚有了新变动，请先「查已收集」读取最新记录，再确认保存。",
    resource_root_changed: "资源库位置已经变化，请重新打开此页面。当前卡片和填写内容已保留。",
    resource_revision_conflict: "资源库刚刚有了新变动，请先「查已收集」读取最新记录，再确认保存。",
    resources_root_changed: "资源库位置已经变化，请重新打开此页面。当前卡片和填写内容已保留。",
    resources_revision_conflict: "资源库刚刚有了新变动，请先「查已收集」读取最新记录，再确认保存。",
    invalid_url: "请使用不含账号或密码的 HTTPS 网址。",
    unsupported_provider: "这个来源尚未接通，请选择列表中的来源。",
    unsupported_kind: "这个来源不支持当前分类，请换一个分类。",
    search_unavailable: "这次联网搜索未完成，已有卡片已保留。可以稍后再试。"
  };
  let root = null;
  let revision = null;
  let generation = 0;
  let busy = false;
  let composing = false;
  let providers = [];
  let currentItems = [];
  let lastSearch = null;
  let preparedUrl = "";
  let imageReturnFocus = null;

  byId("backLink").href = phone ? "/mobile.html?tab=documents" : "/?consoleView=document";

  function stringValue(value, fallback = "") {
    return typeof value === "string" ? value : typeof value === "number" ? String(value) : fallback;
  }
  function safeUrl(value) {
    if (typeof value !== "string" || !value.trim()) return "";
    try {
      const url = new URL(value.trim());
      return url.protocol === "https:" && !url.username && !url.password ? url.href : "";
    } catch (_) { return ""; }
  }
  function node(tag, className, value) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (value !== undefined) element.textContent = value;
    return element;
  }
  function notice(message, error = false, target = "operationStatus", success = false) {
    const element = byId(target);
    element.textContent = message;
    element.dataset.error = String(error);
    element.dataset.tone = success ? "success" : "normal";
  }
  function getFilters() {
    return { q: byId("query").value.trim(), kind: byId("kind").value, status: byId("status").value };
  }
  function persistView() {
    try { sessionStorage.setItem(storageKey, JSON.stringify({ ...getFilters(), provider: byId("provider").value, scroll: window.scrollY })); } catch (_) { /* Session storage is optional. */ }
  }
  function restoreView() {
    try {
      const value = JSON.parse(sessionStorage.getItem(storageKey) || "null");
      if (!value || typeof value !== "object") return 0;
      byId("query").value = stringValue(value.q).slice(0, 120);
      if (value.kind === "all" || Object.hasOwn(kindLabels, value.kind)) byId("kind").value = value.kind;
      if (value.status === "all" || Object.hasOwn(statusLabels, value.status)) byId("status").value = value.status;
      if (["sketchfab", "polyhaven"].includes(value.provider)) byId("provider").value = value.provider;
      return Number.isFinite(value.scroll) && value.scroll > 0 ? value.scroll : 0;
    } catch (_) { return 0; }
  }
  function updateControls() {
    for (const id of ["query", "kind", "status", "provider", "localSearch", "previewButton", "addSave", "addUrl", "addName", "addKind", "addImage", "addDescription", "addNotes"]) byId(id).disabled = busy;
    byId("onlineSearch").disabled = busy || root === null;
    byId("refreshSearch").disabled = busy || root === null;
    byId("addSave").disabled = busy || root === null;
    for (const button of byId("resourceGrid").querySelectorAll("[data-save]")) button.disabled = busy || root === null || button.dataset.active === "true" || button.dataset.hasIdentity !== "true";
    byId("resourceGrid").setAttribute("aria-busy", String(busy));
  }
  async function call(action, payload, params) {
    const headers = {};
    if (phone) headers["X-Codex-Phone"] = "1";
    if (payload !== undefined) headers["Content-Type"] = "application/json";
    const response = await fetch(`${endpoint}/${action}${params ? `?${params}` : ""}`, {
      method: payload !== undefined ? "POST" : "GET",
      headers, credentials: "same-origin", mode: "same-origin", cache: "no-store", redirect: "error",
      ...(payload !== undefined ? { body: JSON.stringify(payload) } : {})
    });
    let value;
    try { value = await response.json(); } catch (_) { throw new Error("本机暂未返回可读取的资源资料，当前卡片已保留。"); }
    if (!response.ok) {
      const code = stringValue(value.code || value.error);
      const serverMessage = stringValue(value.message) || stringValue(value.error);
      const error = new Error(Object.hasOwn(errorLabels, code) ? errorLabels[code] : serverMessage || "这次操作未完成，已有卡片和填写内容已保留。");
      error.code = code;
      throw error;
    }
    return value;
  }
  function acceptIdentity(value) {
    if (typeof value.root !== "string" || !value.root) throw new Error("资源库来源尚未核实，当前卡片已保留。");
    if (root !== null && root !== value.root) throw new Error(errorLabels.resource_root_changed);
    root = value.root;
    if (value.revision !== undefined) revision = value.revision;
    if (Array.isArray(value.providers)) providers = value.providers;
    updateProviderNote();
  }
  function updateProviderNote() {
    const selected = providers.find(provider => provider.id === byId("provider").value);
    byId("providerNote").textContent = selected && stringValue(selected.note) ? selected.note : byId("provider").value === "polyhaven" ? "搜索模型、材质 / 贴图或 HDRI；其他网站可用下方「添加网址」。" : "搜索 Sketchfab 模型；其他网站可用下方「添加网址」。";
  }
  async function readState(token) {
    const filters = getFilters();
    const params = new URLSearchParams({ ...filters, kind: filters.kind === "all" ? "" : filters.kind, status: filters.status === "all" ? "" : filters.status });
    if (root !== null) params.set("expectedRoot", root);
    const value = await call("state", undefined, params.toString());
    if (token !== generation) return null;
    acceptIdentity(value);
    if (!Array.isArray(value.items)) throw new Error("资源列表未完整返回，当前卡片已保留。");
    renderItems(value.items, "library");
    return value;
  }
  async function loadCollected(initial = false) {
    if (busy) return;
    const token = ++generation;
    busy = true; updateControls(); persistView();
    notice(initial ? "正在读取已收集的资源…" : "正在查找已收集的资源…");
    try {
      const value = await readState(token);
      if (value) {
        lastSearch = null; byId("refreshSearch").hidden = true;
        notice(`已读取 ${value.items.length} 项。重复的资源会沿用同一条记录。`);
      }
    } catch (error) { if (token === generation) notice(error.message, true); }
    finally { if (token === generation) { busy = false; updateControls(); } }
  }
  function sourceLabel(providerId) {
    const selected = providers.find(provider => provider.id === providerId);
    return stringValue(selected?.name, providerId === "polyhaven" ? "Poly Haven" : "Sketchfab");
  }
  function onlineKind() {
    const selected = providers.find(provider => provider.id === byId("provider").value);
    const supported = selected && Array.isArray(selected.kinds) ? selected.kinds : byId("provider").value === "polyhaven" ? ["model", "texture", "hdri"] : ["model"];
    const kind = byId("kind").value === "all" ? (byId("provider").value === "polyhaven" ? "hdri" : "model") : byId("kind").value;
    if (!supported.includes(kind)) throw new Error(`${sourceLabel(byId("provider").value)} 暂不支持「${kindLabels[kind] || "当前分类"}」，请选择该来源支持的分类。`);
    return kind;
  }
  async function searchOnline(refresh = false) {
    if (busy || root === null) return;
    const q = byId("query").value.trim();
    if (!q) { notice("先输入想找的资源，再选择来源联网搜索。", true); byId("query").focus(); return; }
    let kind;
    try { kind = onlineKind(); } catch (error) { notice(error.message, true); return; }
    const provider = byId("provider").value;
    const token = ++generation;
    busy = true; updateControls(); persistView();
    notice(`正在${refresh ? "重新" : ""}搜索 ${sourceLabel(provider)} 的${kindLabels[kind]}…`);
    try {
      const value = await call("search", { expectedRoot: root, q, provider, kind, refresh });
      if (token !== generation) return;
      acceptIdentity(value);
      if (!Array.isArray(value.items)) throw new Error("搜索结果未完整返回，当前卡片已保留。");
      lastSearch = { q, provider, kind, searchQuery: stringValue(value.searchQuery, q), cached: value.cached === true };
      renderItems(value.items, "search");
      byId("refreshSearch").hidden = !lastSearch.cached;
      notice(value.cached === true ? `已复用这次搜索的 ${value.items.length} 项记录；需要新的结果时点击「重新搜索」。` : `已从 ${sourceLabel(provider)} 找到 ${value.items.length} 项，查看图片后再选择。`);
    } catch (error) { if (token === generation) notice(error.message, true); }
    finally { if (token === generation) { busy = false; updateControls(); } }
  }
  function makeImage(url, name, className, onFailure, lazy = true) {
    const image = node("img", className);
    image.alt = name;
    image.referrerPolicy = "no-referrer";
    image.decoding = "async";
    if (lazy) image.loading = "lazy";
    image.addEventListener("error", () => { image.remove(); if (onFailure) onFailure(); }, { once: true });
    image.src = url;
    return image;
  }
  function placeholder(message = "暂无可用预览，查看来源页面") {
    return node("span", "preview-placeholder", message);
  }
  function provenanceText(value) {
    if (typeof value === "string") return value;
    if (!Array.isArray(value)) return "";
    return value.map(item => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object") return [stringValue(item.source || item.name || item.provider || item.type), stringValue(item.date || item.at || item.searchTime), item.query ? `搜索：${stringValue(item.query)}` : "", stringValue(item.note || item.description)].filter(Boolean).join(" · ");
      return "";
    }).filter(Boolean).join("\n");
  }
  function renderCard(item) {
    const name = stringValue(item.name, "未命名资源");
    const sourceUrl = safeUrl(item.url);
    const previewUrl = safeUrl(item.previewUrl);
    const kind = Object.hasOwn(kindLabels, item.kind) ? item.kind : "other";
    const status = Object.hasOwn(statusLabels, item.status) ? item.status : "candidate";
    const card = node("article", "resource-card");
    const preview = node("button", "card-preview"); preview.type = "button";
    preview.setAttribute("aria-label", previewUrl ? `查看 ${name} 的图片预览` : `${name} 暂无可用图片预览`);
    if (previewUrl) {
      preview.append(makeImage(previewUrl, `${name} · 来源展示图`, "", () => {
        preview.replaceChildren(placeholder("图片暂不可用，查看来源页面"));
        preview.disabled = true;
      }));
      preview.append(node("span", "preview-affordance", "查看原图"));
      preview.addEventListener("click", () => openImage(item, preview));
    } else { preview.append(placeholder()); preview.disabled = true; }
    preview.append(node("span", "card-kind", kindLabels[kind]));
    card.append(preview);
    const content = node("div", "card-content");
    content.append(node("h3", "card-title", name));
    const meta = node("div", "card-meta");
    const statusTag = node("span", "meta-tag status-tag", statusLabels[status]); statusTag.dataset.status = status;
    meta.append(statusTag, node("span", "meta-tag", stringValue(item.price, "费用待核对")), node("span", "meta-tag", stringValue(item.license, "许可待核对")));
    content.append(meta, node("p", "card-description", stringValue(item.description, "查看来源页面，核对资源内容和适用条件。")));
    const provenance = provenanceText(item.provenance);
    const notes = stringValue(item.notes);
    if (provenance || notes) {
      const details = node("details", "card-extra");
      details.append(node("summary", "", "来源与备注"));
      if (provenance) details.append(node("p", "", `来源：${provenance}`));
      if (notes) details.append(node("p", "", `备注：${notes}`));
      content.append(details);
    }
    const links = node("div", "card-links");
    if (sourceUrl) {
      const link = node("a", "source-link", "来源页面 ↗"); link.href = sourceUrl; link.target = "_blank"; link.rel = "noopener noreferrer";
      link.addEventListener("click", persistView); links.append(link);
    } else links.append(node("span", "source-unavailable", "来源网址待核对"));
    content.append(links);
    const actions = node("div", "card-actions");
    for (const [nextStatus, label] of [["saved", status === "saved" ? "✓ 已收藏" : "收藏"], ["planned", status === "planned" ? "✓ 准备使用" : "准备使用"]]) {
      const button = node("button", "secondary-button", label); button.type = "button";
      button.dataset.save = nextStatus; button.dataset.active = String(status === nextStatus); button.dataset.hasIdentity = String(Boolean(stringValue(item.id)));
      button.disabled = busy || status === nextStatus || !stringValue(item.id);
      button.title = nextStatus === "planned" ? "记录你的选择，尚未导入或修改项目" : "保存到资源库，保留来源";
      button.addEventListener("click", () => saveExisting(item, nextStatus)); actions.append(button);
    }
    content.append(actions); card.append(content);
    return card;
  }
  function renderItems(items, mode) {
    currentItems = items.filter(item => item && typeof item === "object");
    byId("resourceGrid").replaceChildren(...currentItems.map(renderCard));
    byId("emptyState").hidden = currentItems.length > 0;
    byId("resultCount").textContent = `${currentItems.length} 项`;
    byId("resultsTitle").textContent = mode === "search" ? "这次找到的资源" : "已收集的资源";
    if (mode === "search" && lastSearch) {
      byId("resultNote").textContent = `${sourceLabel(lastSearch.provider)} · ${kindLabels[lastSearch.kind]} · 实际搜索词：${lastSearch.searchQuery}${lastSearch.cached ? " · 已复用搜索记录" : ""}。收藏或准备使用前，请查看来源许可。`;
      byId("emptyTitle").textContent = "这个来源暂未找到匹配的资源";
      byId("emptyText").textContent = "换个关键词、分类或来源再搜索；其他网站的网址也可以添加。";
    } else {
      byId("resultNote").textContent = "收藏和准备使用都会保留在这里，准备使用只是选择，尚未导入项目。";
      byId("emptyTitle").textContent = "这里还没有匹配的资源";
      byId("emptyText").textContent = "换一个关键词或分类，也可以选好来源后「联网找」。";
    }
    updateControls();
  }
  async function saveExisting(item, status) {
    if (busy || root === null) return;
    const token = ++generation;
    busy = true; updateControls();
    notice(`正在保存「${stringValue(item.name, "这项资源")}」的选择…`);
    let saved = false;
    try {
      const value = await call("save", { expectedRoot: root, expectedRevision: revision, id: item.id, status });
      if (token !== generation) return;
      acceptIdentity(value); saved = true;
      // Once save succeeds, reflect its receipt even if the following read fails.
      renderItems(currentItems.map(current => current.id === item.id ? { ...current, ...(value.item || {}), status } : current), lastSearch ? "search" : "library");
      await readState(token);
      if (token === generation) {
        lastSearch = null; byId("refreshSearch").hidden = true;
        notice(status === "planned" ? "已记录为准备使用；尚未导入项目。" : "已收藏，今后可以复用这条记录。", false, "operationStatus", true);
      }
    } catch (error) { if (token === generation) notice(saved ? `选择已保存，但列表刷新未完成。${error.message}` : error.message, true); }
    finally { if (token === generation) { busy = false; updateControls(); } }
  }
  function openImage(item, origin) {
    const url = safeUrl(item.previewUrl);
    if (!url) return;
    const dialog = byId("imageDialog");
    byId("imageTitle").textContent = stringValue(item.name, "图片预览");
    byId("dialogImageWrap").replaceChildren(makeImage(url, stringValue(item.name, "资源展示图"), "", () => byId("dialogImageWrap").append(placeholder("原图暂不可用，请查看来源页面")), false));
    const sourceUrl = safeUrl(item.url);
    byId("dialogSource").hidden = !sourceUrl;
    if (sourceUrl) byId("dialogSource").href = sourceUrl; else byId("dialogSource").removeAttribute("href");
    imageReturnFocus = origin;
    dialog.showModal(); document.body.classList.add("dialog-open");
  }
  function updateManualPreview() {
    const url = safeUrl(byId("addImage").value);
    const wrap = byId("addPreview");
    wrap.replaceChildren(); wrap.hidden = !url;
    if (url) wrap.append(makeImage(url, byId("addName").value || "网页预览图片", "", () => wrap.append(placeholder("图片暂不可用"))));
  }
  async function previewWebsite() {
    if (busy) return;
    const url = safeUrl(byId("addUrl").value);
    if (!url) { notice("请填写不含账号或密码的 HTTPS 资源网址。", true, "addFeedback"); return; }
    const token = ++generation;
    busy = true; updateControls();
    const isNewUrl = preparedUrl !== url;
    preparedUrl = url;
    if (isNewUrl) {
      byId("addName").value = new URL(url).hostname;
      byId("addImage").value = ""; byId("addDescription").value = ""; byId("addNotes").value = "";
    }
    byId("addForm").hidden = false; updateManualPreview();
    notice("正在读取这个网页的名称与预览图片…", false, "addFeedback");
    try {
      const value = await call("preview", { url, ...(root !== null ? { expectedRoot: root } : {}) });
      if (token !== generation) return;
      // The submitted URL remains the saved identity; redirected preview URLs are not substituted silently.
      if (stringValue(value.name)) byId("addName").value = stringValue(value.name).slice(0, 240);
      byId("addImage").value = safeUrl(value.previewUrl);
      byId("addDescription").value = stringValue(value.description).slice(0, 3000);
      updateManualPreview();
      notice(stringValue(value.warning) || (safeUrl(value.previewUrl) ? "已读取网页资料。请核对名称和图片，再决定收藏。" : "已读取网页资料，未找到可用图片。可手动填写图片网址，也可以只收藏来源。"), false, "addFeedback");
    } catch (error) {
      if (token === generation) notice(`网页预览未完成。${error.message} 仍可手动填写名称，再收藏原网址。`, true, "addFeedback");
    } finally { if (token === generation) { busy = false; updateControls(); } }
  }
  async function saveManual() {
    if (busy || root === null) return;
    const url = safeUrl(byId("addUrl").value);
    const name = byId("addName").value.trim();
    const previewValue = byId("addImage").value.trim();
    const previewUrl = safeUrl(previewValue);
    if (!url || !name || (previewValue && !previewUrl)) { notice("请核对名称和 HTTPS 网址；图片网址可以留空。", true, "addFeedback"); return; }
    if (url !== preparedUrl) { notice("网址已经变更，请先读取新网址的预览，或核对新网址后重新填写。", true, "addFeedback"); return; }
    const token = ++generation;
    busy = true; updateControls();
    notice("正在收藏这个资源…", false, "addFeedback");
    let saved = false;
    try {
      const value = await call("save", {
        expectedRoot: root, expectedRevision: revision, name, url, previewUrl,
        kind: byId("addKind").value, description: byId("addDescription").value.trim(),
        license: "待核对", price: "待核对", status: "saved", notes: byId("addNotes").value.trim(), provenance: "用户添加的网页"
      });
      if (token !== generation) return;
      acceptIdentity(value); saved = true;
      await readState(token);
      if (token === generation) {
        lastSearch = null; byId("refreshSearch").hidden = true;
        notice("已收藏到资源库，来源与填写内容均已保存。", false, "addFeedback", true);
        notice("已更新资源库。当前筛选条件可能隐藏刚收藏的资源。", false, "operationStatus", true);
      }
    } catch (error) { if (token === generation) notice(saved ? `资源已收藏，但列表刷新未完成。${error.message}` : error.message, true, "addFeedback"); }
    finally { if (token === generation) { busy = false; updateControls(); } }
  }

  byId("searchForm").addEventListener("submit", event => { event.preventDefault(); if (!composing) void loadCollected(); });
  byId("query").addEventListener("compositionstart", () => { composing = true; });
  byId("query").addEventListener("compositionend", () => { composing = false; });
  byId("query").addEventListener("keydown", event => { if (event.key === "Enter" && (event.isComposing || composing || event.keyCode === 229)) event.preventDefault(); });
  for (const id of ["kind", "status"]) byId(id).addEventListener("change", () => { persistView(); void loadCollected(); });
  byId("provider").addEventListener("change", () => { updateProviderNote(); byId("refreshSearch").hidden = true; persistView(); });
  byId("query").addEventListener("input", () => { byId("refreshSearch").hidden = true; persistView(); });
  byId("onlineSearch").addEventListener("click", () => void searchOnline());
  byId("refreshSearch").addEventListener("click", () => void searchOnline(true));
  byId("previewForm").addEventListener("submit", event => { event.preventDefault(); void previewWebsite(); });
  byId("addForm").addEventListener("submit", event => { event.preventDefault(); void saveManual(); });
  byId("addImage").addEventListener("change", updateManualPreview);
  byId("closeImage").addEventListener("click", () => byId("imageDialog").close());
  byId("imageDialog").addEventListener("click", event => { if (event.target === byId("imageDialog")) { const rect = byId("imageDialog").getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) byId("imageDialog").close(); } });
  byId("imageDialog").addEventListener("close", () => { document.body.classList.remove("dialog-open"); byId("dialogImageWrap").replaceChildren(); if (imageReturnFocus?.isConnected) imageReturnFocus.focus(); imageReturnFocus = null; });
  window.addEventListener("pagehide", persistView);
  const restoreScroll = restoreView();
  updateProviderNote(); updateControls();
  void loadCollected(true).then(() => { if (restoreScroll) window.scrollTo({ top: restoreScroll, behavior: "instant" }); });
})();
