#!/usr/bin/env node

// Isolated fake DOM/API checks. No browser, server, production file, or inbox
// is opened or changed. Only the reader source and its HTML entry are read.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = readFileSync(join(projectRoot, "document-reader.js"), "utf8");
const html = readFileSync(join(projectRoot, "reader.html"), "utf8");
let nextSessionId = 1;

class Element {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.listeners = {};
    this.dataset = {};
    this.style = { setProperty() {} };
    this.attributes = {};
    this._text = "";
  }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { children.forEach(child => this.appendChild(child)); }
  replaceChildren(...children) { this._text = ""; this.children = children; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  scrollIntoView() { this.scrolled = true; }
}

const descendants = element => [element, ...element.children.flatMap(descendants)];
const writes = reader => reader.calls.filter(call => call.url === "/api/documents/inbox/read");
const moves = reader => reader.calls.filter(call => call.url === "/api/documents/inbox/move");
const sessionCalls = (reader, action) => reader.calls.filter(call => call.payload?.action === action);

async function settle() {
  // Every request is an immediate fake promise, so drain microtasks and beacon
  // Blob reads without a wall-clock wait or any network access.
  for (let index = 0; index < 14; index += 1) await new Promise(setImmediate);
}

async function createReader({ path = "reports/first.md", id = "first", currentRoot = "D:/library", reference = "", language = "", uiLanguage = "zh-CN", englishAvailable = true } = {}) {
  const elements = new Map(), windowEvents = {}, documentEvents = {}, calls = [], preferences = new Map(), channels = [];
  let nextMutationWait = null;
  let nextReadWait = null;
  preferences.set("codexControl.language.v1", uiLanguage);
  const entries = [
    { id: "first", path: "reports/first.md", title: "First report", source: "Fixture", createdAt: "2026-09-28", read: false },
    { id: "second", path: "reports/second.md", title: "Second report", source: "Fixture", createdAt: "2026-09-28", read: false }
  ];
  const files = {
    "reports/first.md": [
      "# First report", "",
      "[Second](second.md) [unsafe](javascript:alert(1)) [data](data:text/plain,hi) [network](//evil.example/x.md) [escape](../../outside.md) [External](https://example.com/)",
      "", "<script>evil()</script>", "", "> A quote", "",
      "| A | B |", "| --- | --- |", "| safe | table |", "",
      "- Parent", "  - Child", "", "```js", "const value = 1;", "```"
    ].join("\n"),
    "reports/second.md": "# Second report\n\nSecond body.",
    "reports/hash#name.md": "# Hash report\n\nFull body.",
    "blender/reference.zh-CN.md": "# 自定义节点参考\n\n中文正文。\n\n[目录](#节点列表) [English](reference.en.md)\n\n## 节点列表\n\n内容。",
    "blender/reference.en.md": "# Custom nodes reference\n\nEnglish body."
  };
  const references = [{ id: "custom-nodes-reference", module: "blender", defaultLanguage: "zh-CN", variants: [
    { language: "zh-CN", label: "中文", title: "自定义节点参考", summary: "中文用途", path: "blender/reference.zh-CN.md", available: true, error: "" },
    { language: "en", label: "English", title: "Custom nodes reference", summary: "English uses", path: "blender/reference.en.md", available: englishAvailable, error: englishAvailable ? "" : "missing" }
  ] }];
  // This URL exists only in the VM. fetch below never leaves this process.
  let locationUrl = new URL("http://127.0.0.1:55319/reader.html");
  locationUrl.searchParams.set("path", path);
  locationUrl.searchParams.set("root", "D:/library");
  if (id) locationUrl.searchParams.set("id", id);
  if (reference) locationUrl.searchParams.set("reference", reference);
  if (language) locationUrl.searchParams.set("lang", language);
  const location = {
    get origin() { return locationUrl.origin; }, get href() { return locationUrl.href; },
    get search() { return locationUrl.search; }, get hash() { return locationUrl.hash; },
    reload() { calls.push({ reload: true }); }
  };
  const history = {
    state: null,
    pushState(state, _title, url) { this.state = state; locationUrl = new URL(url, locationUrl); },
    replaceState(state, _title, url) { this.state = state; locationUrl = new URL(url, locationUrl); }
  };
  const document = {
    hidden: false, title: "", documentElement: new Element("html"),
    getElementById(id) { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); },
    createElement: tag => new Element(tag),
    createTextNode(value) { const element = new Element("#text"); element.textContent = value; return element; },
    addEventListener(name, callback) { documentEvents[name] = callback; }
  };
  const runtime = {
    document, history, location, URL, URLSearchParams, AbortController, Blob,
    crypto: { randomUUID: () => `reader-fixture-session-${nextSessionId++}` },
    BroadcastChannel: class {
      constructor(name) { this.name = name; this.messages = []; channels.push(this); }
      postMessage(message) { this.messages.push(structuredClone(message)); }
      receive(message) { this.onmessage?.({ data: message }); }
    },
    localStorage: { getItem: key => preferences.get(key) || null, setItem: (key, value) => preferences.set(key, value) },
    navigator: {
      sendBeacon(url, blob) {
        blob.text().then(value => calls.push({ url, method: "BEACON", payload: JSON.parse(value) }));
        return true;
      }
    },
    setTimeout, clearTimeout, setInterval: () => 1, clearInterval() {}, scrollY: 250,
    scrollTo(value) { runtime.scrollY = value.top; },
    addEventListener(name, callback) { windowEvents[name] = callback; },
    async fetch(url, options = {}) {
      const requestUrl = new URL(url, locationUrl);
      const payload = options.body ? JSON.parse(options.body) : undefined;
      calls.push({ url: requestUrl.pathname, query: requestUrl.searchParams, method: options.method || "GET", payload });
      assert.equal(requestUrl.origin, locationUrl.origin, "reader made a cross-origin API request");
      const reply = (value, status = 200) => ({ ok: status === 200, status, json: async () => value });
      const mutationReply = value => {
        const response = reply(value), wait = nextMutationWait;
        nextMutationWait = null;
        return wait ? wait.then(() => response) : response;
      };
      if (requestUrl.pathname === "/api/console/window-session") return reply({ version: "1.0.10" });
      if (requestUrl.pathname === "/api/documents/state") return reply({ root: currentRoot, exists: true });
      assert.equal(payload?.expectedRoot || requestUrl.searchParams.get("expectedRoot"), "D:/library", "expectedRoot guard missing");
      if (currentRoot !== "D:/library") return reply({ error: "資料庫已切換" }, 400);
      const inbox = () => ({ root: currentRoot, entries: structuredClone(entries.filter(entry => entry.status !== "cleared")) });
      if (requestUrl.pathname === "/api/documents/references") return reply({ root: currentRoot, items: structuredClone(references) });
      if (requestUrl.pathname === "/api/documents/inbox") return reply(inbox());
      if (requestUrl.pathname === "/api/documents/read") {
        const requested = requestUrl.searchParams.get("path");
        const response = files[requested]
          ? reply({ root: currentRoot, path: requested, name: requested.split("/").at(-1), format: "markdown", content: files[requested] })
          : reply({ error: "missing" }, 404);
        const wait = nextReadWait;
        nextReadWait = null;
        return wait ? wait.then(() => response) : response;
      }
      if (requestUrl.pathname === "/api/documents/inbox/read") {
        const entry = entries.find(item => item.id === payload.id && item.status !== "cleared");
        assert(entry, "reader tried to mark an unknown id");
        entry.read = payload.read;
        entry.status = payload.read ? "archive" : "inbox";
        return mutationReply(inbox());
      }
      if (requestUrl.pathname === "/api/documents/inbox/move") {
        const entry = entries.find(item => item.id === payload.id && item.status !== "cleared");
        assert(entry, "reader tried to move an unknown or cleared id");
        assert(["later", "inbox"].includes(payload.status), "reader sent an unsupported destination");
        entry.status = payload.status; entry.read = false;
        return mutationReply(inbox());
      }
      throw new Error(`Unexpected reader API: ${requestUrl.pathname}`);
    }
  };
  runtime.window = runtime;
  runInNewContext(source, runtime, { filename: "document-reader.js" });
  await settle();
  return {
    elements, calls, preferences, entries, files, references, windowEvents, runtime, channels,
    setRoot(value) { currentRoot = value; },
    holdNextMutation() { let release; nextMutationWait = new Promise(resolveWait => { release = resolveWait; }); return () => release(); },
    holdNextRead() { let release; nextReadWait = new Promise(resolveWait => { release = resolveWait; }); return () => release(); }
  };
}

function boundaryChecks() {
  const start = source.indexOf("  function normalizeRoot(");
  const end = source.indexOf("  function rootChangedError(", start);
  const bodyStart = source.indexOf("  function hasLoadedBody(");
  const bodyEnd = source.indexOf("\n  function ", bodyStart + 1);
  assert(start >= 0 && end > start && bodyStart >= 0 && bodyEnd > bodyStart, "reader path helpers could not be isolated");
  const context = { state: { root: "D:/library", path: "reports/A.md", loadedDocument: null } };
  runInNewContext(source.slice(start, end) + source.slice(bodyStart, bodyEnd), context);
  assert.equal(context.libraryPath("reports/hash#name.md"), "reports/hash#name.md");
  assert.equal(context.libraryPath("hash%23name.md", "reports/A.md", true), "reports/hash#name.md");
  assert.equal(context.libraryPath("//evil.example/x.md", "reports/A.md"), null);
  assert.equal(context.libraryPath("../../outside.md", "reports/A.md"), null);
  assert.equal(context.samePath("reports/A.md", "reports/a.md"), true, "Windows path comparison lost its case normalization");
  context.state.root = "/tmp/library";
  assert.equal(context.samePath("reports/A.md", "reports/a.md"), false, "non-Windows paths must distinguish filename case");
  assert.equal(context.hasLoadedBody(), false);
  context.state.loadedDocument = { root: "/tmp/library", path: "reports/A.md" };
  assert.equal(context.hasLoadedBody(), true);
  context.state.path = "reports/a.md";
  assert.equal(context.hasLoadedBody(), false, "a different document reused the loaded-body authorization");
  context.state.path = "reports/A.md"; context.state.root = "/tmp/other";
  assert.equal(context.hasLoadedBody(), false, "a different root reused the loaded-body authorization");
}

async function main() {
  assert(!/\b(?:innerHTML|outerHTML|insertAdjacentHTML)\b|\beval\s*\(/.test(source), "reader introduced an unsafe rendering sink");
  assert(!/\bsessionStorage\b/.test(source), "reader identity must not use copied per-tab storage");
  assert(!/src=["'][^"']*\bapp\.js/.test(html), "reader must not load the main Console app");
  const version = source.match(/const UI_VERSION = "([^"]+)"/)?.[1];
  assert(version && html.includes(`document-reader.js?v=reader-${version}`) && html.includes(`document-reader.css?v=reader-${version}`), "reader asset and UI versions differ");
  assert(/id="readerLater"[^>]*aria-pressed="false"/.test(html), "Later bookmark must start accessible and unselected");
  boundaryChecks();

  const reader = await createReader();
  assert.match(reader.runtime.document.title, /^阅读 · /);
  assert.equal(writes(reader).length, 0, "opening a document changed its read state");
  reader.runtime.scrollTo({ top: 500 });
  assert.equal(writes(reader).length, 0, "scrolling changed read state");
  const content = reader.elements.get("readerContent");
  const nodes = descendants(content);
  assert(nodes.some(element => element.tagName === "TABLE"));
  assert(nodes.some(element => element.tagName === "BLOCKQUOTE"));
  assert(nodes.some(element => element.tagName === "PRE"));
  assert(!nodes.some(element => ["SCRIPT", "IMG", "IFRAME"].includes(element.tagName)), "Markdown created active HTML");
  assert(content.textContent.includes("<script>evil()</script>"), "raw HTML text was lost rather than shown safely");
  const links = nodes.filter(element => element.tagName === "A");
  assert.equal(links.length, 2, "unsafe or escaping Markdown targets became links");
  assert.equal(links.find(element => element.href.startsWith("https:")).rel, "noopener noreferrer");

  links.find(element => element.href.includes("second.md")).listeners.click({ button: 0, preventDefault() {} });
  await settle();
  assert.match(reader.runtime.location.search, /id=second/);
  assert.equal(writes(reader).length, 0, "following a report link changed read state");
  const checkbox = reader.elements.get("readerRead");
  checkbox.checked = true; checkbox.listeners.change({ target: checkbox });
  await settle();
  assert.equal(writes(reader).length, 1);
  assert.equal(writes(reader)[0].payload.id, "second", "following a link retained the old inbox id");
  assert.equal(reader.entries[0].read, false);
  assert.equal(reader.entries[1].read, true);
  assert.equal(reader.entries[1].status, "archive", "Read did not move the report to Archive");

  reader.setRoot("D:/another"); reader.windowEvents.focus(); await settle();
  assert.equal(checkbox.disabled, true);
  assert.equal(reader.elements.get("readerLater").disabled, true);
  assert.equal(content.children.length, 0);
  assert.match(reader.elements.get("readerStatus").textContent, /资料库已切换/);
  checkbox.checked = true; checkbox.listeners.change({ target: checkbox }); await settle();
  assert.equal(writes(reader).length, 1, "root mismatch allowed a read-state write");
  reader.setRoot("D:/library"); reader.windowEvents.focus(); await settle();
  assert.equal(checkbox.disabled, true, "inbox refresh re-enabled marking without loading the cleared body");
  assert.equal(reader.elements.get("readerLater").disabled, true, "inbox refresh re-enabled Later without the document body");
  assert.equal(content.children.length, 0);
  assert.match(reader.elements.get("readerStatus").textContent, /正文尚未加载/);
  reader.elements.get("readerRefresh").listeners.click(); await settle();
  assert.equal(checkbox.disabled, false);
  assert.equal(checkbox.checked, true, "explicit refresh did not restore persisted read state");
  assert(content.textContent.includes("Second body."));

  const firstSession = sessionCalls(reader, "open")[0].payload.sessionId;
  reader.windowEvents.pagehide(); await settle();
  assert.equal(sessionCalls(reader, "close")[0].payload.sessionId, firstSession);
  reader.windowEvents.pageshow(); await settle();
  assert.equal(sessionCalls(reader, "open").length, 2);
  assert.equal(sessionCalls(reader, "open")[1].payload.sessionId, firstSession);

  const hashReader = await createReader({ path: "reports/hash#name.md", id: "" });
  assert(hashReader.elements.get("readerContent").textContent.includes("Full body."));
  assert.notEqual(sessionCalls(hashReader, "open")[0].payload.sessionId, firstSession, "independent reader windows reused one session id");
  const mismatch = await createReader({ currentRoot: "D:/wrong" });
  assert.equal(mismatch.calls.some(call => call.url === "/api/documents/read"), false, "wrong root was read before validation");
  assert.equal(mismatch.elements.get("readerRead").disabled, true);
  assert.equal(mismatch.elements.get("readerLater").disabled, true);

  await archiveAndLaterChecks();
  await delayedMutationChecks();
  await referenceChecks();

  console.log("PASS standalone reader: safe Markdown/links; explicit Archive/Later actions; queued cross-window reconciliation; cleared-record protection; id/path/root binding; cleared-body recovery; case/hash paths; independent session lifecycle (fake DOM/API only)");
}

async function referenceChecks() {
  const reference = "custom-nodes-reference";
  const inboxCalls = reader => reader.calls.filter(call => call.url.startsWith("/api/documents/inbox"));
  const click = async (reader, suffix) => { reader.elements.get(`reader${suffix}`).listeners.click(); await settle(); };
  const content = reader => reader.elements.get("readerContent").textContent;
  const reader = await createReader({ reference });
  const longestId = "r".repeat(160);
  const longest = await createReader({ reference });
  longest.references[0].id = longestId;
  const longestUrl = new URL(longest.runtime.location.href);
  longestUrl.searchParams.set("reference", longestId);
  longest.runtime.history.pushState({}, "", longestUrl); longest.windowEvents.popstate(); await settle();
  assert(content(longest).includes("中文正文"), "valid 160-character reference ID was rejected");
  assert.equal(new URL(longest.runtime.location.href).searchParams.get("reference"), longestId);
  assert(content(reader).includes("中文正文"));
  assert.equal(reader.elements.get("readerReadControl").hidden, true);
  assert.equal(reader.elements.get("readerLater").hidden, true);
  assert.equal(reader.elements.get("readerLanguages").hidden, false);
  assert.equal(reader.elements.get("readerChinese").attributes["aria-pressed"], "true");
  assert.equal(reader.elements.get("readerContent").lang, "zh-CN");
  assert.equal(inboxCalls(reader).length, 0, "reference consulted or mutated report inbox");
  const zhUrl = reader.runtime.location.href;
  const query = new URL(zhUrl).searchParams;
  assert.equal(query.get("reference"), reference);
  assert.equal(query.get("lang"), "zh-CN");
  assert.equal(query.get("root"), "D:/library");
  assert.equal(query.has("path"), false);
  assert.equal(query.has("id"), false, "reference retained a report identity");
  const anchor = descendants(reader.elements.get("readerContent")).find(element => element.tagName === "A" && element.href.includes("#"));
  assert.equal(new URL(anchor.href).searchParams.get("reference"), reference, "heading link lost reference identity");
  anchor.listeners.click({ button: 0, preventDefault() {} }); await settle();
  assert(descendants(reader.elements.get("readerContent")).some(element => element.scrolled), "reference heading anchor stopped working");

  await click(reader, "FontLarger"); await click(reader, "Theme");
  await click(reader, "English");
  assert(content(reader).includes("English body."));
  assert.equal(reader.elements.get("readerContent").lang, "en");
  assert.equal(new URL(reader.runtime.location.href).searchParams.get("lang"), "en");
  assert.equal(reader.elements.get("readerFontSize").textContent, "19");
  assert.equal(reader.runtime.document.documentElement.dataset.readerTheme, "light");
  reader.runtime.history.pushState({}, "", zhUrl); reader.windowEvents.popstate(); await settle();
  assert(content(reader).includes("中文正文"), "history did not restore the language variant");
  assert.equal(reader.elements.get("readerFontSize").textContent, "19");

  const release = reader.holdNextRead();
  await click(reader, "English");
  assert.equal(reader.elements.get("readerChinese").disabled, false, "language choice was blocked by a pending read");
  await click(reader, "Chinese");
  assert(content(reader).includes("中文正文"));
  release(); await settle();
  assert(content(reader).includes("中文正文"), "late English response replaced the newer Chinese selection");
  assert.equal(reader.elements.get("readerEnglish").attributes["aria-pressed"], "false");

  // Even a report that happens to point at this file does not turn a durable
  // reference into an inbox item, including programmatically fired controls.
  reader.entries.push({ id: "same-file", path: "blender/reference.zh-CN.md", read: false });
  reader.elements.get("readerRead").listeners.change({ target: { checked: true } });
  await click(reader, "Later");
  reader.windowEvents.focus(); reader.channels[0].receive({ type: "read-changed", root: "D:/library" }); await settle();
  assert.equal(inboxCalls(reader).length, 0, "reference actions touched an inbox entry");

  reader.setRoot("D:/changed"); reader.windowEvents.focus(); await settle();
  assert.equal(content(reader), "");
  assert.match(reader.elements.get("readerStatus").textContent, /资料库已切换/);
  const readCount = reader.calls.filter(call => call.url === "/api/documents/read").length;
  await click(reader, "English");
  assert.equal(reader.calls.filter(call => call.url === "/api/documents/read").length, readCount, "reference read a different selected root");
  assert.equal(inboxCalls(reader).length, 0);

  const unavailable = await createReader({ reference, language: "en", englishAvailable: false });
  assert.match(unavailable.elements.get("readerStatus").textContent, /所选语言.*不可用/);
  assert.equal(content(unavailable), "", "explicit unavailable language silently showed another language");
  assert.equal(unavailable.elements.get("readerEnglish").disabled, true);
  assert.equal(unavailable.elements.get("readerChinese").disabled, false);
  await click(unavailable, "Chinese");
  assert(content(unavailable).includes("中文正文"));
  const preferred = await createReader({ reference, language: "invalid", uiLanguage: "en" });
  assert(content(preferred).includes("English body."), "invalid language did not fall back to the UI preference");
  const fallback = await createReader({ reference, uiLanguage: "en", englishAvailable: false });
  assert(content(fallback).includes("中文正文"), "missing UI language did not fall back to an available variant");

  const missing = await createReader({ reference });
  delete missing.files["blender/reference.en.md"];
  await click(missing, "English");
  assert.equal(content(missing), "");
  assert.match(missing.elements.get("readerStatus").textContent, /missing/);
  await click(missing, "Chinese");
  assert(content(missing).includes("中文正文"), "missing content prevented recovery to the other language");
  missing.references.splice(0);
  await click(missing, "Refresh");
  assert.equal(content(missing), "");
  assert.match(missing.elements.get("readerStatus").textContent, /已移除/);
  assert.equal(missing.elements.get("readerChinese").disabled, true);
  assert.equal(missing.elements.get("readerEnglish").disabled, true);
  assert.equal(inboxCalls(missing).length, 0);

  const invalid = await createReader({ reference });
  invalid.references[0].variants[0].path = "../../outside.md";
  const before = invalid.calls.filter(call => call.url === "/api/documents/read").length;
  await click(invalid, "Refresh");
  assert.equal(content(invalid), "");
  assert.equal(invalid.calls.filter(call => call.url === "/api/documents/read").length, before, "unsafe catalog path reached the read API");
  const oversized = await createReader({ reference });
  oversized.files["blender/reference.zh-CN.md"] = "x".repeat(2 * 1024 * 1024 + 1);
  await click(oversized, "Refresh");
  assert.equal(content(oversized), "");
  assert.match(oversized.elements.get("readerStatus").textContent, /大小限制/);
  console.log("PASS paired references: language selection/fallback, history, safe heading links, late-response isolation, missing variants/files/catalog, root changes, bounded content and zero inbox access");
}

async function delayedMutationChecks() {
  const reader = await createReader();
  const inboxReads = () => reader.calls.filter(call => call.url === "/api/documents/inbox").length;
  const release = reader.holdNextMutation();
  reader.elements.get("readerLater").listeners.click(); await settle();
  assert.equal(reader.entries[0].status, "later");
  assert.equal(reader.elements.get("readerLater").disabled, true);
  const before = inboxReads();
  // The server applies a main-window action after the reader's mutation, but
  // the earlier reader response has not arrived yet.
  reader.entries[0].status = "archive"; reader.entries[0].read = true;
  reader.channels[0].receive({ type: "read-changed", root: "D:/library" });
  reader.channels[0].receive({ type: "read-changed", root: "D:/library" });
  await settle();
  assert.equal(inboxReads(), before, "busy notifications should queue rather than start overlapping refreshes");
  release(); await settle();
  assert.equal(inboxReads(), before + 1, "queued notifications were lost or not coalesced");
  assert.equal(reader.elements.get("readerRead").checked, true, "a delayed POST response overwrote a newer external Archive state");
  assert.equal(reader.elements.get("readerLater").attributes["aria-pressed"], "false");
  assert.equal(reader.elements.get("readerLater").disabled, false);
  await settle();
  assert.equal(inboxReads(), before + 1, "refresh reconciliation entered a loop");

  const navigated = await createReader();
  const releaseOld = navigated.holdNextMutation();
  navigated.elements.get("readerLater").listeners.click(); await settle();
  navigated.channels[0].receive({ type: "read-changed", root: "D:/library" });
  const destination = new URL(navigated.runtime.location.href);
  destination.searchParams.set("path", "reports/second.md"); destination.searchParams.set("id", "second");
  navigated.runtime.history.pushState({}, "", destination);
  navigated.windowEvents.popstate(); await settle();
  releaseOld(); await settle();
  assert(navigated.elements.get("readerContent").textContent.includes("Second body."));
  assert.equal(navigated.elements.get("readerRead").checked, false);
  assert.equal(navigated.elements.get("readerLater").attributes["aria-pressed"], "false", "old mutation state crossed the document navigation sequence");
  assert.equal(navigated.elements.get("readerLater").disabled, false);
}

async function archiveAndLaterChecks() {
  const reader = await createReader();
  const later = reader.elements.get("readerLater"), read = reader.elements.get("readerRead");
  const content = reader.elements.get("readerContent").textContent;
  const clickLater = async () => { later.listeners.click(); await settle(); };
  const checkRead = async value => { read.checked = value; read.listeners.change({ target: read }); await settle(); };
  const channel = reader.channels[0];
  assert.equal(channel.name, "codexControl.documentInbox.v1");
  assert.equal(later.disabled, false);
  assert.equal(later.attributes["aria-pressed"], "false", "legacy unread record was incorrectly saved for later");
  assert.match(reader.elements.get("readerReadControl").title, /归档/);
  await clickLater();
  assert.equal(moves(reader).length, 1);
  assert.equal(moves(reader)[0].payload.id, "first");
  assert.equal(moves(reader)[0].payload.status, "later");
  assert.equal(later.attributes["aria-pressed"], "true");
  assert.match(later.attributes["aria-label"], /移回待阅读/);
  assert.equal(read.checked, false);
  await clickLater();
  assert.equal(moves(reader)[1].payload.status, "inbox");
  assert.equal(later.attributes["aria-pressed"], "false");
  await checkRead(true);
  assert.equal(reader.entries[0].status, "archive");
  assert.equal(read.checked, true);
  await clickLater();
  assert.equal(reader.entries[0].status, "later", "Archive could not be moved to Later");
  assert.equal(reader.entries[0].read, false, "moving Archive to Later retained read=true");
  assert.equal(read.checked, false);
  await checkRead(true);
  assert.equal(reader.entries[0].status, "archive", "marking Later read did not archive it");
  assert.equal(later.attributes["aria-pressed"], "false");
  await checkRead(false);
  assert.equal(reader.entries[0].status, "inbox");
  assert.equal(channel.messages.length, 6, "state changes were not broadcast to the main window");
  assert(channel.messages.every(message => message.type === "read-changed" && message.root === "D:/library" && message.id === "first"));

  // Legacy read=true without status remains Archive; a matching broadcast
  // reconciles external changes without reading or replacing the document.
  delete reader.entries[0].status; reader.entries[0].read = true;
  channel.receive({ type: "read-changed", root: "D:/library" }); await settle();
  assert.equal(read.checked, true, "legacy read state was not interpreted as Archive");
  assert.equal(later.attributes["aria-pressed"], "false");
  reader.entries[0].status = "cleared";
  channel.receive({ type: "read-changed", root: "D:/library" }); await settle();
  assert.equal(read.disabled, true, "cleared report could still be marked read");
  assert.equal(later.disabled, true, "cleared report could still be moved to Later");
  assert.equal(reader.elements.get("readerContent").textContent, content, "clearing the record discarded the open document");
  const writeCount = writes(reader).length, moveCount = moves(reader).length;
  await clickLater(); await checkRead(true);
  assert.equal(writes(reader).length, writeCount);
  assert.equal(moves(reader).length, moveCount, "a cleared record was resurrected");
  reader.elements.get("readerRefresh").listeners.click(); await settle();
  assert.equal(read.disabled, true); assert.equal(later.disabled, true);
  assert.equal(reader.elements.get("readerContent").textContent, content);

  // No notification is required for safety: both actions revalidate the
  // current record before writing, including its path and selected root.
  const stale = await createReader();
  const staleContent = stale.elements.get("readerContent").textContent;
  stale.entries[0].status = "cleared";
  stale.elements.get("readerLater").listeners.click(); await settle();
  assert.equal(moves(stale).length, 0, "stale Later action recreated a cleared report");
  assert.equal(stale.elements.get("readerRead").disabled, true);
  assert.equal(stale.elements.get("readerLater").disabled, true);
  assert.equal(stale.elements.get("readerContent").textContent, staleContent);
  const changedPath = await createReader();
  changedPath.entries[0].path = "reports/second.md";
  changedPath.elements.get("readerLater").listeners.click(); await settle();
  assert.equal(moves(changedPath).length, 0, "Later wrote a record now bound to a different file");
  const changedRoot = await createReader();
  changedRoot.setRoot("D:/another");
  changedRoot.elements.get("readerLater").listeners.click(); await settle();
  assert.equal(moves(changedRoot).length, 0, "Later wrote after the selected library changed");

  const noId = await createReader({ id: "" });
  noId.entries[0].status = "cleared";
  noId.entries.push({ ...noId.entries[0], id: "replacement", status: "inbox", read: false });
  noId.windowEvents.focus(); await settle();
  assert.equal(noId.elements.get("readerLater").disabled, true, "clearing an inferred id rebound the reader to a different record");
}

main().catch(error => { console.error(`FAIL ${error.stack || error}`); process.exitCode = 1; });
