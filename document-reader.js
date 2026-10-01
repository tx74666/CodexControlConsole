(() => {
  "use strict";

  const UI_VERSION = "1.0.16";
  const preferenceKeys = { font: "codexControl.readerFontSize.v1", theme: "codexControl.readerTheme.v1" };
  const saved = key => { try { return localStorage.getItem(key); } catch { return null; } };
  const save = (key, value) => { try { localStorage.setItem(key, String(value)); } catch { /* Reading remains available without browser storage. */ } };
  const english = saved("codexControl.language.v1") === "en";
  const text = (zh, en) => english ? en : zh;
  const node = id => document.getElementById(`reader${id}`);
  const state = { root: "", path: "", requestedId: "", referenceId: "", reference: null, language: "", entry: null, entries: [], loadedDocument: null, valid: false, busy: false, sequence: 0, headings: new Map() };
  let fontSize = Math.max(14, Math.min(26, Number(saved(preferenceKeys.font)) || 18));
  let theme = saved(preferenceKeys.theme) === "light" ? "light" : "dark";
  let upgradePending = false;
  let upgradeReloading = false;
  let messageChannel = null;
  let readStatusRefreshPending = false;

  // Deliberately memory-only: a child window must never inherit its opener's
  // window-session identity through copied per-tab storage.
  const readerSessionId = globalThis.crypto?.randomUUID?.()
    || `reader-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
  let sessionClosed = true;
  let heartbeatTimer = 0;

  function normalizeRoot(value) {
    const root = String(value || "").trim().replaceAll("\\", "/").replace(/\/+$/, "");
    return /^[a-z]:/i.test(root) || root.startsWith("//") ? root.toLowerCase() : root;
  }

  function libraryPath(value, baseFile = "", decode = false) {
    let path = String(value || "");
    if (decode) { try { path = decodeURIComponent(path); } catch { return null; } }
    if (!path || /[\u0000-\u001f\u007f:?]/.test(path) || /^[\\/]/.test(path)) return null;
    const parts = baseFile ? baseFile.split("/").slice(0, -1) : [];
    for (const part of path.replaceAll("\\", "/").split("/")) {
      if (!part || part === ".") continue;
      if (part === "..") { if (!parts.length) return null; parts.pop(); }
      else parts.push(part);
    }
    return parts.length ? parts.join("/") : null;
  }

  function samePath(left, right) {
    const a = libraryPath(left), b = libraryPath(right);
    if (!a || !b) return false;
    const root = String(state.root).replaceAll("\\", "/");
    return /^[a-z]:\//i.test(root) || root.startsWith("//") ? a.toLowerCase() === b.toLowerCase() : a === b;
  }

  function rootChangedError() {
    const error = new Error(text("资料库已切换，请从主窗口重新打开这份文档。", "The library has changed. Reopen this document from the main window."));
    error.rootChanged = true;
    return error;
  }

  function assertRoot(payload, expected) {
    if (!expected || normalizeRoot(payload?.root) !== normalizeRoot(expected)) throw rootChangedError();
  }

  async function request(endpoint, { query = {}, payload, root = state.root } = {}) {
    const url = new URL(`/api/documents/${endpoint}`, window.location.origin);
    for (const [key, value] of Object.entries(query)) url.searchParams.set(key, value);
    if (endpoint !== "state" && payload === undefined) url.searchParams.set("expectedRoot", root);
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(url.href, {
        method: payload === undefined ? "GET" : "POST", cache: "no-store", mode: "same-origin",
        credentials: "same-origin", redirect: "error", signal: controller.signal,
        headers: payload === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
        ...(payload === undefined ? {} : { body: JSON.stringify({ ...payload, expectedRoot: root }) })
      });
      const result = await response.json();
      if (!response.ok || (result.error && endpoint !== "state")) {
        if (/資料庫已切換|资料库已切换/.test(String(result.error || ""))) throw rootChangedError();
        throw new Error(result.error || `${text("读取失败", "Request failed")} (${response.status})`);
      }
      return result;
    } catch (error) {
      if (error.name === "AbortError") throw new Error(text("读取超时，请稍后刷新。", "The request timed out. Refresh to retry."));
      throw error;
    } finally { window.clearTimeout(timer); }
  }

  async function verifyRoot(root) {
    if (!root) throw new Error(text("缺少资料库位置，请从主窗口打开文档。", "No library location was supplied. Open the document from the main window."));
    const result = await request("state", { root });
    assertRoot(result, root);
    if (!result.exists) throw new Error(text("资料库目录暂时不可用，请检查磁盘或从主窗口重新选择。", "The library folder is unavailable. Check the disk or choose it again in the main window."));
  }

  function notice(message = "", error = false) {
    node("Status").textContent = message;
    node("Status").dataset.error = String(error);
  }

  function updateControls() {
    const referenceMode = Boolean(state.referenceId);
    node("ReadControl").hidden = referenceMode;
    node("Later").hidden = referenceMode;
    node("Languages").hidden = !referenceMode;
    for (const [language, suffix] of [["zh-CN", "Chinese"], ["en", "English"]]) {
      const button = node(suffix);
      const variant = state.reference?.variants.find(item => item.language === language);
      // Keep the other available language usable during a load. The sequence
      // guard prevents an earlier response from replacing a newer choice.
      button.disabled = !variant?.available;
      button.setAttribute("aria-pressed", String(state.language === language));
      button.title = variant?.available ? variant.label : text("此语言暂不可用", "This language is unavailable");
    }
    const disabled = state.busy || !state.valid || !hasLoadedBody() || !state.entry;
    const later = entryStatus(state.entry) === "later";
    node("Read").checked = Boolean(state.entry && entryStatus(state.entry) === "archive");
    node("Read").disabled = disabled;
    node("ReadControl").title = state.entry
      ? text("勾选已读并归档；取消勾选移回待阅读。", "Check to mark read and move to Archive; uncheck to return to To read.")
      : text("这份文件没有对应的阅读记录，或记录已从列表清除。", "This file has no matching reading record, or its record was cleared from the lists.");
    const laterLabel = later ? text("移回待阅读", "Return to To read") : text("稍后阅读", "Read later");
    node("Later").disabled = disabled;
    node("Later").setAttribute("aria-pressed", String(later));
    node("Later").setAttribute("aria-label", laterLabel);
    node("Later").title = state.entry ? laterLabel : node("ReadControl").title;
    node("Refresh").disabled = state.busy;
    node("Content").setAttribute("aria-busy", String(state.busy));
  }

  function entryStatus(entry) {
    return ["inbox", "later", "archive"].includes(entry?.status) ? entry.status : entry?.read ? "archive" : "inbox";
  }

  function hasLoadedBody() {
    return Boolean(state.loadedDocument && samePath(state.loadedDocument.path, state.path)
      && normalizeRoot(state.loadedDocument.root) === normalizeRoot(state.root));
  }

  function findEntry(entries, path, id = "") {
    if (id) return entries.find(item => item.id === id && samePath(item.path, path)) || null;
    return entries.find(item => samePath(item.path, path)) || null;
  }

  function setMetadata(file = null) {
    const variant = state.reference?.variants.find(item => item.language === state.language);
    const title = variant?.title || state.entry?.title || state.fileTitle || state.path.split("/").at(-1) || text("文档", "Document");
    node("Title").textContent = title;
    document.title = `${text("阅读", "Reading")} · ${title}`;
    const date = state.entry?.createdAt || state.entry?.registeredAt || file?.modifiedAt || state.modifiedAt;
    const source = state.entry?.source;
    node("Meta").textContent = [
      variant ? variant.label : "",
      source ? `${text("来源", "Source")}：${source}` : "",
      date ? `${state.entry ? text("日期", "Date") : text("修改于", "Modified")}：${date}` : ""
    ].filter(Boolean).join(" · ");
  }

  function slug(value) {
    return String(value).trim().toLowerCase().replace(/[`*_~]/g, "").replace(/\s+/g, "-").replace(/[^\p{L}\p{N}_-]/gu, "") || "section";
  }

  function readerUrl(path, id = "", fragment = "") {
    const variant = state.reference?.variants.find(item => samePath(item.path, path));
    if (state.referenceId && variant) return referenceUrl(variant.language, fragment);
    const url = new URL("/reader.html", window.location.origin);
    url.searchParams.set("path", path);
    url.searchParams.set("root", state.root);
    if (id) url.searchParams.set("id", id);
    if (fragment) url.hash = fragment;
    return url;
  }

  function referenceUrl(language, fragment = "") {
    const url = new URL("/reader.html", window.location.origin);
    url.searchParams.set("reference", state.referenceId);
    url.searchParams.set("lang", language);
    url.searchParams.set("root", state.root);
    if (fragment) url.hash = fragment;
    return url;
  }

  function selectReference(payload, id) {
    if (!Array.isArray(payload.items) || payload.items.length > 100) throw new Error(text("参考文档目录无效。", "The reference catalog is invalid."));
    const matches = payload.items.filter(item => item?.id === id);
    if (matches.length !== 1) throw new Error(text("这份参考文档已移除或尚未登记，请从主窗口重新打开。", "This reference was removed or is not registered. Reopen it from the main window."));
    const reference = matches[0];
    if (!Array.isArray(reference.variants) || reference.variants.length < 1 || reference.variants.length > 2) throw new Error(text("参考文档的语言信息无效。", "The reference language information is invalid."));
    const languages = new Set();
    for (const variant of reference.variants) {
      if (!variant || !["zh-CN", "en"].includes(variant.language) || languages.has(variant.language)
          || typeof variant.available !== "boolean" || typeof variant.title !== "string" || variant.title.length > 200
          || typeof variant.label !== "string" || variant.label.length > 80
          || typeof variant.path !== "string" || !libraryPath(variant.path) || !/\.md$/i.test(variant.path)) {
        throw new Error(text("参考文档的语言信息无效。", "The reference language information is invalid."));
      }
      languages.add(variant.language);
    }
    return reference;
  }

  function switchLanguage(language) {
    if (!state.referenceId || !state.reference?.variants.some(item => item.language === language && item.available)
        || (language === state.language && state.valid)) return;
    history.pushState({}, "", referenceUrl(language));
    void loadDocument({ resetScroll: true });
  }

  function followFragment(fragment, resetScroll = false) {
    let value = String(fragment || "").replace(/^#/, "");
    try { value = decodeURIComponent(value); } catch { value = ""; }
    const heading = state.headings.get(value) || state.headings.get(slug(value));
    if (heading) heading.scrollIntoView({ block: "start" });
    else if (resetScroll) window.scrollTo({ top: 0, left: 0 });
  }

  function appendInline(parent, source, depth = 0) {
    const value = String(source);
    if (depth > 5) { parent.appendChild(document.createTextNode(value)); return; }
    const tokens = /(`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|_[^_\n]+_|!?\[[^\]\n]*\]\((?:<[^>\n]+>|[^)\n]+)\))/g;
    let offset = 0;
    for (const match of value.matchAll(tokens)) {
      parent.appendChild(document.createTextNode(value.slice(offset, match.index)));
      const token = match[0];
      if (token.startsWith("`")) {
        const code = document.createElement("code"); code.textContent = token.slice(1, -1); parent.appendChild(code);
      } else if (token.startsWith("**") || token.startsWith("__")) {
        const strong = document.createElement("strong"); appendInline(strong, token.slice(2, -2), depth + 1); parent.appendChild(strong);
      } else if (token.startsWith("*") || token.startsWith("_")) {
        const em = document.createElement("em"); appendInline(em, token.slice(1, -1), depth + 1); parent.appendChild(em);
      } else {
        const split = token.indexOf("](");
        const image = token.startsWith("!");
        const label = token.slice(image ? 2 : 1, split);
        let target = token.slice(split + 2, -1).trim();
        target = target.startsWith("<") && target.endsWith(">") ? target.slice(1, -1) : target.replace(/\s+["'][^"']*["']$/, "");
        if (image) parent.appendChild(document.createTextNode(`${text("图片", "Image")}：${label}`));
        else appendLink(parent, label, target, depth);
      }
      offset = match.index + token.length;
    }
    parent.appendChild(document.createTextNode(value.slice(offset)));
  }

  function appendLink(parent, label, target, depth) {
    if (/[\u0000-\u001f\u007f]/.test(target)) { parent.appendChild(document.createTextNode(label)); return; }
    if (/^https?:\/\//i.test(target)) {
      try {
        const url = new URL(target);
        if (!["http:", "https:"].includes(url.protocol)) throw new Error("unsupported");
        const anchor = document.createElement("a"); anchor.href = url.href; anchor.target = "_blank"; anchor.rel = "noopener noreferrer";
        appendInline(anchor, label, depth + 1); parent.appendChild(anchor); return;
      } catch { parent.appendChild(document.createTextNode(label)); return; }
    }
    const separator = target.indexOf("#");
    const pathPart = separator < 0 ? target : target.slice(0, separator);
    const fragment = separator < 0 ? "" : target.slice(separator + 1);
    const relative = pathPart ? libraryPath(pathPart, state.path, true) : state.path;
    if (!relative || (pathPart && !/\.md$/i.test(relative))) { parent.appendChild(document.createTextNode(label)); return; }
    const entry = findEntry(state.entries, relative);
    const url = readerUrl(relative, entry?.id || "", fragment);
    const anchor = document.createElement("a"); anchor.href = url.href;
    appendInline(anchor, label, depth + 1);
    anchor.addEventListener("click", event => {
      if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      if (state.busy) return;
      history.pushState({}, "", url);
      if (samePath(relative, state.path)) followFragment(fragment, !fragment);
      else void loadDocument({ resetScroll: true });
    });
    parent.appendChild(anchor);
  }

  function renderMarkdown(source, container, quoteDepth = 0) {
    container.replaceChildren();
    const value = String(source).replace(/\r\n?/g, "\n");
    const lines = value.split("\n");
    const plain = content => { const pre = document.createElement("pre"); const code = document.createElement("code"); code.textContent = content; pre.appendChild(code); return pre; };
    if (value.length > 512000 || lines.length > 6000 || lines.some(line => line.length > 12000)) {
      const note = document.createElement("p"); note.className = "reader-plain-note";
      note.textContent = text("较长文件按纯文本显示，正文完整保留。", "This large file is displayed as plain text; all content is preserved.");
      container.append(note, plain(value)); return;
    }
    const tableRule = line => /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line || "");
    const cells = line => line.trim().replace(/^\||\|$/g, "").split(/(?<!\\)\|/).map(cell => cell.trim().replace(/\\\|/g, "|"));
    const listMatch = line => /^(\s*)([-*+]|\d+[.)])\s+(.+)/.exec(line || "");
    const indentOf = match => match[1].replaceAll("\t", "    ").length;
    const blockStart = (line, index) => !line.trim() || /^\s{0,3}(?:#{1,6}\s|`{3,}|~{3,}|>\s?|(?:[-*_]\s*){3,}$)/.test(line)
      || listMatch(line) || (line.includes("|") && tableRule(lines[index + 1]));
    const readList = (start, depth = 0) => {
      const first = listMatch(lines[start]); const indent = indentOf(first); const ordered = /^\d/.test(first[2]);
      const list = document.createElement(ordered ? "ol" : "ul");
      if (ordered) list.start = Number.parseInt(first[2], 10) || 1;
      let index = start, lastItem = null;
      while (index < lines.length) {
        const match = listMatch(lines[index]);
        if (!match || indentOf(match) < indent) break;
        if (indentOf(match) > indent) {
          if (!lastItem || depth >= 8) break;
          const nested = readList(index, depth + 1); lastItem.appendChild(nested.list); index = nested.index; continue;
        }
        if (/^\d/.test(match[2]) !== ordered) break;
        lastItem = document.createElement("li"); appendInline(lastItem, match[3]); list.appendChild(lastItem); index += 1;
        while (index < lines.length && lines[index].trim() && !listMatch(lines[index])
            && /^\s+/.test(lines[index]) && lines[index].match(/^\s*/)[0].length > indent) {
          const continuation = document.createElement("p"); appendInline(continuation, lines[index].trim()); lastItem.appendChild(continuation); index += 1;
        }
      }
      return { list, index };
    };
    let index = 0;
    while (index < lines.length) {
      const line = lines[index];
      if (!line.trim()) { index += 1; continue; }
      const fence = /^\s{0,3}(`{3,}|~{3,})/.exec(line);
      if (fence) {
        const close = new RegExp(`^\\s{0,3}${fence[1][0]}{${fence[1].length},}\\s*$`);
        const codeLines = []; index += 1;
        while (index < lines.length && !close.test(lines[index])) codeLines.push(lines[index++]);
        if (index < lines.length) index += 1;
        container.appendChild(plain(codeLines.join("\n"))); continue;
      }
      const heading = /^(#{1,6})\s+(.+?)(?:\s+#+)?\s*$/.exec(line);
      if (heading) {
        const element = document.createElement(`h${heading[1].length}`); appendInline(element, heading[2]);
        const base = slug(element.textContent); let key = base; let count = 1;
        while (state.headings.has(key)) key = `${base}-${count++}`;
        if (!quoteDepth && index === 0 && heading[1].length === 1 && element.textContent.trim() === node("Title").textContent.trim()) {
          state.headings.set(key, node("Title")); index += 1; continue;
        }
        element.id = `reader-heading-${key}`; state.headings.set(key, element);
        container.appendChild(element); index += 1; continue;
      }
      if (/^\s{0,3}(?:[-*_]\s*){3,}$/.test(line)) { container.appendChild(document.createElement("hr")); index += 1; continue; }
      if (/^\s{0,3}>/.test(line) && quoteDepth < 4) {
        const quoteLines = [];
        while (index < lines.length && /^\s{0,3}>/.test(lines[index])) quoteLines.push(lines[index++].replace(/^\s{0,3}>\s?/, ""));
        const quote = document.createElement("blockquote"); renderMarkdown(quoteLines.join("\n"), quote, quoteDepth + 1); container.appendChild(quote); continue;
      }
      if (line.includes("|") && tableRule(lines[index + 1]) && cells(line).length <= 40) {
        const wrap = document.createElement("div"); wrap.className = "reader-table-scroll"; wrap.tabIndex = 0;
        wrap.setAttribute("aria-label", text("表格，可横向滚动", "Table; scroll horizontally"));
        const table = document.createElement("table"); const head = document.createElement("thead"); const row = document.createElement("tr");
        for (const cell of cells(line)) { const th = document.createElement("th"); th.scope = "col"; appendInline(th, cell); row.appendChild(th); }
        head.appendChild(row); table.appendChild(head); index += 2;
        const body = document.createElement("tbody");
        while (index < lines.length && lines[index].trim() && lines[index].includes("|") && cells(lines[index]).length <= 40) {
          const tr = document.createElement("tr");
          for (const cell of cells(lines[index++])) { const td = document.createElement("td"); appendInline(td, cell); tr.appendChild(td); }
          body.appendChild(tr);
        }
        table.appendChild(body); wrap.appendChild(table); container.appendChild(wrap); continue;
      }
      if (listMatch(line)) { const list = readList(index); container.appendChild(list.list); index = list.index; continue; }
      const paragraph = document.createElement("p"); const paragraphLines = [line]; index += 1;
      while (index < lines.length && !blockStart(lines[index], index)) paragraphLines.push(lines[index++]);
      paragraphLines.forEach((part, partIndex) => {
        if (partIndex) paragraph.appendChild(/ {2}$/.test(paragraphLines[partIndex - 1]) ? document.createElement("br") : document.createTextNode(" "));
        appendInline(paragraph, part.trim());
      });
      container.appendChild(paragraph);
    }
  }

  function fail(error, clearBody = false) {
    state.valid = false;
    if (clearBody || error.rootChanged) { state.loadedDocument = null; node("Content").replaceChildren(); }
    notice(error.message || String(error), true);
    updateControls();
  }

  async function loadDocument({ resetScroll = false } = {}) {
    const sequence = ++state.sequence;
    const oldScroll = window.scrollY;
    const query = new URLSearchParams(window.location.search);
    const root = query.get("root") || "";
    let path = libraryPath(query.get("path"));
    const referenceId = query.get("reference") || "";
    if (state.referenceId !== referenceId || normalizeRoot(state.root) !== normalizeRoot(root)) state.reference = null;
    state.root = root; state.path = path || ""; state.referenceId = referenceId;
    state.language = ["zh-CN", "en"].includes(query.get("lang")) ? query.get("lang") : "";
    state.requestedId = referenceId ? "" : query.get("id") || "";
    state.entries = [];
    state.entry = null; state.fileTitle = ""; state.modifiedAt = ""; state.loadedDocument = null; state.valid = false; state.busy = true;
    setMetadata(); updateControls(); notice(text("正在读取本地文档…", "Loading the local document…"));
    node("Content").replaceChildren();
    try {
      if (referenceId ? !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/.test(referenceId) : !path) throw new Error(text("文档路径或编号无效，请从资料库内重新打开。", "The document path or reference ID is invalid. Reopen it from the library."));
      await verifyRoot(root);
      if (sequence !== state.sequence) return;
      let file;
      if (referenceId) {
        const catalog = await request("references", { root });
        if (sequence !== state.sequence) return;
        assertRoot(catalog, root);
        state.reference = null;
        state.reference = selectReference(catalog, referenceId);
        const explicitLanguage = ["zh-CN", "en"].includes(query.get("lang")) ? query.get("lang") : "";
        const preferred = [english ? "en" : "zh-CN", state.reference.defaultLanguage];
        const variant = explicitLanguage
          ? state.reference.variants.find(item => item.language === explicitLanguage)
          : preferred.map(language => state.reference.variants.find(item => item.language === language && item.available)).find(Boolean)
            || state.reference.variants.find(item => item.available) || state.reference.variants[0];
        state.language = explicitLanguage || variant?.language || "";
        state.path = path = variant ? libraryPath(variant.path) : "";
        setMetadata(); updateControls();
        if (!variant?.available) throw new Error(text("所选语言的文档暂不可用，可切换到另一种语言。", "The selected language is unavailable. You can choose the other language."));
        history.replaceState(history.state, "", referenceUrl(state.language, window.location.hash));
        file = await request("read", { query: { path }, root });
      } else {
        const [documentFile, inbox] = await Promise.all([
          request("read", { query: { path }, root }), request("inbox", { root })
        ]);
        if (sequence !== state.sequence) return;
        assertRoot(inbox, root);
        file = documentFile;
        state.entries = Array.isArray(inbox.entries) ? inbox.entries : [];
        state.entry = findEntry(state.entries, path, state.requestedId);
        if (state.entry && !state.requestedId) state.requestedId = state.entry.id;
      }
      if (sequence !== state.sequence) return;
      assertRoot(file, root);
      if (!samePath(file.path, path) || typeof file.content !== "string") throw new Error(text("文件响应与请求不符。", "The file response did not match this document."));
      if (file.content.length > 2 * 1024 * 1024) throw new Error(text("文档超过阅读大小限制。", "The document exceeds the reading size limit."));
      const firstHeading = /^#\s+(.+)$/m.exec(file.content)?.[1];
      state.fileTitle = firstHeading || file.name || path.split("/").at(-1);
      state.modifiedAt = file.modifiedAt || ""; state.valid = true; state.headings.clear();
      setMetadata(file);
      node("Content").lang = state.language || (english ? "en" : "zh-CN");
      if (file.format === "markdown" || /\.md$/i.test(path)) renderMarkdown(file.content, node("Content"));
      else { const pre = document.createElement("pre"); pre.textContent = file.content; node("Content").appendChild(pre); }
      state.loadedDocument = { root, path };
      notice(state.requestedId && !state.entry
        ? text("此文件与待阅读记录不匹配，已停用已读勾选。", "This document does not match its inbox entry; read marking is disabled.") : "");
      const restore = history.state?.readerRestoreScroll;
      if (restore && samePath(restore.path, path) && normalizeRoot(restore.root) === normalizeRoot(root)) {
        history.replaceState({ ...history.state, readerRestoreScroll: null }, "", window.location.href);
        window.scrollTo({ top: Math.max(0, Number(restore.y) || 0), left: 0 });
      } else if (window.location.hash) followFragment(window.location.hash, resetScroll);
      else window.scrollTo({ top: resetScroll ? 0 : oldScroll, left: 0 });
    } catch (error) { if (sequence === state.sequence) fail(error, true); }
    finally { if (sequence === state.sequence) { state.busy = false; updateControls(); drainReadStatusRefresh(); maybeReloadForUpgrade(); } }
  }

  function requestReadStatusRefresh() {
    readStatusRefreshPending = true;
    drainReadStatusRefresh();
  }

  function drainReadStatusRefresh() {
    if (!readStatusRefreshPending || state.busy || !state.path || !state.root || document.hidden || sessionClosed || upgradeReloading) return;
    readStatusRefreshPending = false;
    void refreshReadStatus();
  }

  async function refreshReadStatus() {
    if (state.busy || !state.path || !state.root || document.hidden) return;
    const sequence = state.sequence, root = state.root;
    state.busy = true; updateControls();
    try {
      await verifyRoot(root);
      if (sequence !== state.sequence) return;
      if (state.referenceId) {
        state.valid = hasLoadedBody();
        if (!state.valid) notice(text("正文尚未加载，请按“刷新”重新打开。", "The document content is not loaded. Refresh to reopen it."), true);
        return;
      }
      const inbox = await request("inbox", { root });
      if (sequence !== state.sequence) return;
      assertRoot(inbox, root);
      state.entries = Array.isArray(inbox.entries) ? inbox.entries : [];
      state.entry = findEntry(state.entries, state.path, state.requestedId);
      state.valid = hasLoadedBody(); setMetadata();
      notice(state.valid ? "" : text("正文尚未加载，请按“刷新”重新打开文档后再标记已读。", "The document content is not loaded. Refresh the document before marking it read."));
    } catch (error) { if (sequence === state.sequence) fail(error); }
    finally { if (sequence === state.sequence) { state.busy = false; updateControls(); drainReadStatusRefresh(); maybeReloadForUpgrade(); } }
  }

  async function updateInboxEntry(endpoint, payload, message) {
    if (state.referenceId || state.busy || !state.valid || !hasLoadedBody() || !state.entry) { updateControls(); return; }
    const sequence = state.sequence, root = state.root, id = state.entry.id, path = state.path;
    state.busy = true; updateControls();
    try {
      await verifyRoot(root);
      const inbox = await request("inbox", { root });
      assertRoot(inbox, root);
      if (sequence !== state.sequence) return;
      state.entries = Array.isArray(inbox.entries) ? inbox.entries : [];
      state.entry = findEntry(state.entries, path, id);
      if (!state.entry) throw new Error(text("阅读记录已改变或已清除，正文仍可继续阅读。", "The reading record changed or was cleared. You can still read this document."));
      const result = await request(endpoint, { payload: { id, ...payload }, root });
      if (sequence !== state.sequence) return;
      assertRoot(result, root);
      state.entries = Array.isArray(result.entries) ? result.entries : [];
      state.entry = findEntry(state.entries, path, id);
      if (!state.entry) throw new Error(text("无法确认保存后的阅读状态，请刷新。", "The saved read status could not be confirmed. Refresh to check."));
      notice(message);
      messageChannel?.postMessage({ type: "read-changed", root, id });
    } catch (error) { if (sequence === state.sequence) fail(error); }
    finally { if (sequence === state.sequence) { state.busy = false; updateControls(); drainReadStatusRefresh(); maybeReloadForUpgrade(); } }
  }

  async function markRead(read) {
    await updateInboxEntry("inbox/read", { read: Boolean(read) }, read
      ? text("已读，已移至归档。", "Marked read and moved to Archive.")
      : text("已移回待阅读。", "Returned to To read."));
  }

  async function toggleLater() {
    const status = entryStatus(state.entry) === "later" ? "inbox" : "later";
    await updateInboxEntry("inbox/move", { status }, status === "later"
      ? text("已加入稍后阅读。", "Saved for later.")
      : text("已移回待阅读。", "Returned to To read."));
  }

  function applyPreferences() {
    document.documentElement.dataset.readerTheme = theme;
    document.documentElement.style.setProperty("--reader-font-size", `${fontSize}px`);
    node("FontSize").textContent = String(fontSize);
    node("FontSmaller").disabled = fontSize <= 14; node("FontLarger").disabled = fontSize >= 26;
    node("Theme").textContent = theme === "dark" ? text("浅色阅读", "Light theme") : text("深色阅读", "Dark theme");
    node("Theme").setAttribute("aria-pressed", String(theme === "light"));
  }

  function maybeReloadForUpgrade() {
    if (!upgradePending || upgradeReloading || state.busy || sessionClosed) return;
    upgradeReloading = true;
    try { history.replaceState({ ...(history.state || {}), readerRestoreScroll: { root: state.root, path: state.path, y: window.scrollY } }, "", window.location.href); } catch { /* Reload still works without history state. */ }
    window.location.reload();
  }

  function checkVersion(version) {
    if (typeof version !== "string" || !/^\d+\.\d+\.\d+$/.test(version)) return;
    const current = UI_VERSION.split(".").map(Number), next = version.split(".").map(Number);
    const changed = next.findIndex((part, index) => part !== current[index]);
    if (changed >= 0 && next[changed] > current[changed]) { upgradePending = true; maybeReloadForUpgrade(); }
  }

  function sendSession(action, beacon = false) {
    const body = JSON.stringify({ action, sessionId: readerSessionId });
    if (beacon && navigator.sendBeacon) {
      try { if (navigator.sendBeacon("/api/console/window-session", new Blob([body], { type: "application/json" }))) return; } catch { /* Keepalive fetch below is the fallback. */ }
    }
    fetch("/api/console/window-session", {
      method: "POST", headers: { "Content-Type": "application/json" }, body,
      mode: "same-origin", credentials: "same-origin", redirect: "error", keepalive: beacon
    }).then(response => response.ok ? response.json() : null)
      .then(result => { if (action !== "close" && !sessionClosed) checkVersion(result?.version); }).catch(() => {});
  }

  function startSession() {
    if (!sessionClosed) return;
    sessionClosed = false; sendSession("open");
    heartbeatTimer = window.setInterval(() => { if (!sessionClosed) sendSession("heartbeat"); }, 30000);
  }

  function closeSession() {
    if (sessionClosed) return;
    sessionClosed = true; window.clearInterval(heartbeatTimer); heartbeatTimer = 0; sendSession("close", true);
  }

  document.documentElement.lang = english ? "en" : "zh-CN";
  node("Label").textContent = text("阅读", "Reading");
  node("Toolbar").setAttribute("aria-label", text("阅读设置", "Reading settings"));
  node("FontControls").setAttribute("aria-label", text("字号", "Font size"));
  node("Languages").setAttribute("aria-label", text("文档语言", "Document language"));
  node("FontSmaller").setAttribute("aria-label", text("缩小字号", "Decrease font size"));
  node("FontLarger").setAttribute("aria-label", text("放大字号", "Increase font size"));
  node("ReadLabel").textContent = text("已读", "Read");
  node("Refresh").textContent = text("刷新", "Refresh");
  node("FontSmaller").addEventListener("click", () => { fontSize = Math.max(14, fontSize - 1); save(preferenceKeys.font, fontSize); applyPreferences(); });
  node("FontLarger").addEventListener("click", () => { fontSize = Math.min(26, fontSize + 1); save(preferenceKeys.font, fontSize); applyPreferences(); });
  node("Theme").addEventListener("click", () => { theme = theme === "dark" ? "light" : "dark"; save(preferenceKeys.theme, theme); applyPreferences(); });
  node("Refresh").addEventListener("click", () => void loadDocument());
  node("Chinese").addEventListener("click", () => switchLanguage("zh-CN"));
  node("English").addEventListener("click", () => switchLanguage("en"));
  node("Read").addEventListener("change", event => void markRead(event.target.checked));
  node("Later").addEventListener("click", () => void toggleLater());
  window.addEventListener("popstate", () => void loadDocument({ resetScroll: true }));
  window.addEventListener("pagehide", closeSession);
  window.addEventListener("pageshow", () => { if (sessionClosed) startSession(); });
  window.addEventListener("focus", () => { if (!sessionClosed) sendSession("heartbeat"); requestReadStatusRefresh(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { if (!sessionClosed) sendSession("heartbeat"); requestReadStatusRefresh(); } });
  try {
    if (typeof BroadcastChannel === "function") {
      messageChannel = new BroadcastChannel("codexControl.documentInbox.v1");
      messageChannel.onmessage = event => {
        if (event.data?.type === "read-changed" && normalizeRoot(event.data.root) === normalizeRoot(state.root)) requestReadStatusRefresh();
      };
    }
  } catch { /* Focus refresh also reconciles the persisted read state. */ }
  applyPreferences(); startSession(); void loadDocument();
})();
