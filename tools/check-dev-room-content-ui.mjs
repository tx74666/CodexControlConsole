// Exercise real media/sync behavior with isolated DOM/storage/network fixtures.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { createRequire } from "node:module";
import { randomUUID } from "node:crypto";
const require = createRequire(import.meta.url), editor = require("../dev-room-editor.js");
const app = fs.readFileSync(new URL("../app.js", import.meta.url), "utf8");
const source = app.slice(app.indexOf("// Dev Room keeps confirmed documents"));
const markdownSource = app.slice(app.indexOf("function renderDocumentMarkdown("), app.indexOf("function resetDocumentResources()"));
const id = "e0b1ef39-c71b-50f9-b9b4-50885af0bc74", root = "D:/fixture/library";
const original = '<!-- rr-dev-room:v1 {"id":"gameplay-combat-ai","guid":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"} -->\n# Combat & AI\n\n<!-- rr-dev-room:summary -->\nCombat rules.\n<!-- rr-dev-room:summary-end -->\n\n<!-- rr-dev-room:section 0 -->\n## Overview\nAim and hit.\n<!-- rr-dev-room:section-end 0 -->\n\n<!-- rr-dev-room:section 1 -->\n## References\nAssets/Scripts/Gameplay/AI\n<!-- rr-dev-room:section-end 1 -->\n\n';
const media = { section: 0, imageCaption: "Original image", sha256: "", stagingName: "", resourcePath: "fixture/image", guid: "d".repeat(32), fileID: 2800000, type: 3, assetPath: "Assets/fixture/image.png" };
const model = editor.parse(original); model.sections[0].media = media;
model.title = "战斗与人工智能"; model.summary = "战斗的共同规则。";
model.sections[0].title = "概述"; model.sections[0].body = "瞄准并命中。"; model.sections[1].title = "参考资料";
const chinese = editor.serialize(original, model);
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const response = (value, status = 200) => ({ ok: status < 400, status, async json() { return structuredClone(value); } });
const settle = async () => { for (let n = 0; n < 12; n++) await new Promise(resolve => setImmediate(resolve)); };
function harness(options = {}) {
  let document, hook = null, failStorage = false, failRead = false;
  const observers = [], storage = new Map(options.storage || []), calls = [], nodes = new Map();
  class Element {
    constructor(tag = "div") { this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.attributes = {}; this.listeners = new Map(); this.hidden = false; this.disabled = false; this.open = false; this.value = ""; this.className = ""; this._text = ""; this.scrollTop = 0; }
    append(...items) { for (const item of items) { item.parentElement = this; this.children.push(item); } }
    appendChild(item) { this.append(item); return item; }
    replaceChildren(...items) { for (const item of this.children) item.parentElement = null; this.children = []; this._text = ""; this.append(...items); }
    set textContent(value) { this.replaceChildren(); this._text = String(value); }
    get textContent() { return this._text + this.children.map(item => item.textContent).join(""); }
    set innerHTML(value) { throw Error("HTML assignment is not allowed: " + value); }
    get childElementCount() { return this.children.length; }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    addEventListener(key, callback) { if (!this.listeners.has(key)) this.listeners.set(key, []); this.listeners.get(key).push(callback); }
    fire(key) { for (const callback of this.listeners.get(key) || []) callback({ target: this }); }
    click() { if (!this.disabled) { this.focus(); this.fire("click"); } }
    focus() { document.activeElement = this; }
    select() {}
    closest() { return module; }
    matches(selector) {
      if (selector.includes(">")) { const [parent, self] = selector.split(">").map(item => item.trim()); return this.matches(self) && this.parentElement?.matches(parent); }
      if (selector.startsWith(".")) return this.className.split(/\s+/).includes(selector.slice(1));
      if (selector === "[data-dev-room-field-label]") return Boolean(this.dataset.devRoomFieldLabel);
      if (selector === "[data-dev-room-text]") return Boolean(this.dataset.devRoomText);
      if (selector === '[aria-current="true"]') return this.attributes["aria-current"] === "true";
      return this.tagName.toLowerCase() === selector;
    }
    querySelectorAll(selector) {
      const choices = selector.split(",").map(item => item.trim()), result = [];
      const visit = node => { for (const child of node.children) { if (choices.some(choice => child.matches(choice))) result.push(child); visit(child); } };
      visit(this); return result;
    }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    getBoundingClientRect() { return { top: 10, bottom: 400 }; }
  }
  const module = new Element(), panel = new Element(), sidebar = new Element(), section = new Element(), label = new Element();
  panel.id = "devRoomPanel"; nodes.set(panel.id, panel); module.append(panel); panel.append(label, sidebar, section);
  label.className = "section-label"; sidebar.className = "dev-room-sidebar"; section.className = "dev-room-document";
  for (const name of ["Heading", "List", "Title", "SavedAt", "Read", "Editor", "TitleInput", "BodyInput", "BodyLabel", "Fields", "Agent", "AgentContent", "Edit", "Save", "Copy", "New", "Reload", "Status", "ViewImages", "ViewText", "ViewNote", "Sync", "SyncHeading", "StructureNote", "SyncPull", "SyncPush", "SyncReceipt", "SyncStatus", "SyncPreview", "SyncPreviewTitle", "SyncChanges", "SyncApply", "SyncDismiss"]) {
    const node = new Element(name.endsWith("Input") ? name === "BodyInput" ? "textarea" : "input" : ["Edit", "Save", "Copy", "New", "Reload"].includes(name) ? "button" : "div");
    node.id = "devRoom" + name; nodes.set(node.id, node);
    (name === "List" ? sidebar : section).append(node);
  }
  nodes.get("devRoomAgent").append(new Element("summary"));
  const ui = name => nodes.get("devRoom" + name);
  ui("Agent").append(ui("AgentContent"));
  document = { documentElement: { lang: options.language || "zh-CN" }, activeElement: panel, createElement: tag => new Element(tag), createTextNode: text => { const node = new Element("#text"); node.textContent = text; return node; }, getElementById: name => nodes.get(name) || panel.querySelectorAll("input, textarea").find(item => item.id === name) };
  const englishModel = editor.parse(original); englishModel.sections[0].media = media;
  const texts = { zh: { title: "战斗与人工智能", body: chinese }, en: { title: "Combat & AI", body: editor.serialize(original, englishModel) } };
  let revision = "a".repeat(64);
  function state(language, selected = "overview") {
    const overview = { id: "overview", title: language === "zh" ? "总案" : "Overview", body: language === "zh" ? "## 玩法\n- [战斗与人工智能](" + id + ".md)\n" : "## Gameplay\n- [Combat & AI](" + id + ".md)\n", revision, updatedAt: "", language, sourceBody: "", translationMissing: false };
    const image = editor.parse(texts[language].body).sections[0].media || media;
    const combat = { id, ...texts[language], revision, language, sourceBody: original, updatedAt: "", translationMissing: Boolean(options.missing), mediaSlots: [{ section: 0, index: 0, caption: image.imageCaption, image, hasImage: true, editable: true }] };
    if (options.missing) { combat.title = language === "zh" ? "待翻译文档" : "Translation needed"; combat.body = ""; }
    return { root, documents: [overview, combat].map(item => ({ id: item.id, title: item.title, language, updatedAt: "" })), document: selected === id ? combat : selected === "overview" ? overview : null };
  }
  const runtime = {
    document, URLSearchParams, crypto: { randomUUID }, MutationObserver: class { constructor(callback) { this.callback = callback; observers.push(this); } observe(target) { this.target = target; } },
    window: { CodexDevRoomEditor: editor, addEventListener() {} },
    FileReader: class { readAsDataURL(file) { this.result = "data:" + file.type + ";base64,aW1hZ2U="; this.onload(); } },
    localStorage: { getItem(key) { if (failRead) throw Error("Fixture storage read failed"); return storage.get(key) || null; }, setItem(key, value) { if (failStorage) throw Error("Fixture storage full"); storage.set(key, value); }, removeItem(key) { if (failStorage) throw Error("Fixture storage full"); storage.delete(key); } },
    renderDocumentMarkdown: options.realMarkdown ? vm.runInNewContext("(" + markdownSource + ")", { document }) : (markdown, element) => { element.textContent = markdown; },
    async fetch(url, init = {}) {
      const call = { url, ...init, payload: init.body ? JSON.parse(init.body) : null }; calls.push(call);
      const hooked = hook?.(call); if (hooked !== undefined) return await hooked;
      if (url === "/api/documents/state") return response({ root });
      if (url.startsWith("/api/dev-room/sync/status?")) { const query = new URLSearchParams(url.split("?")[1]); return response({ root, language: query.get("language"), bindings: [{ documentId: id, lastUnityRevision: "c".repeat(64) }], pending: [] }); }
      if (url.startsWith("/api/dev-room/sync/preview?")) { const query = new URLSearchParams(url.split("?")[1]); return response({ root, language: query.get("language"), canImport: true, planSha256: "f".repeat(64), indexRevision: "a".repeat(64), changes: [{ action: "update", title: "Combat" }] }); }
      if (url === "/api/dev-room/sync/push") return response({ root, language: call.payload.language, documentId: id, requestId: call.payload.requestId, status: "pending" });
      if (url === "/api/dev-room/sync/import") return response({ root, language: call.payload.language, requestId: call.payload.requestId, status: "applied" });
      if (url.startsWith("/api/dev-room/sync/receipt?")) { const query = new URLSearchParams(url.split("?")[1]); return response({ root, language: query.get("language"), requestId: query.get("requestId"), status: "unknown" }); }
      if (url === "/api/dev-room/media/upload") return response({ root, id, language: call.payload.language, expectedRevision: call.payload.expectedRevision, section: 0, sha256: "e".repeat(64), stagingName: "e".repeat(64) + ".png", image: { ...media, sha256: "e".repeat(64), stagingName: "e".repeat(64) + ".png" } });
      if (url.startsWith("/api/dev-room/state?")) { const query = new URLSearchParams(url.split("?")[1]); return response(state(query.get("language"), query.get("id"))); }
      if (url === "/api/dev-room/save") {
        const sent = call.payload; texts[sent.language] = { title: sent.title, body: sent.body }; revision = "b".repeat(64);
        return response(state(sent.language, sent.id));
      }
      throw Error("Unexpected endpoint " + url);
    }
  };
  if (options.legacy) storage.set("codex-console-dev-room-drafts-v1:" + root, JSON.stringify(options.legacy));
  vm.runInNewContext(source, runtime);
  const change = language => { document.documentElement.lang = language; for (const observer of observers) if (observer.target === document.documentElement) observer.callback(); };
  const open = async () => { await settle(); ui("List").querySelectorAll("button").find(item => item.textContent === (document.documentElement.lang.startsWith("zh") ? "战斗与人工智能" : "Combat & AI") || item.textContent === "待翻译文档").click(); await settle(); };
  const input = (name, value) => { ui(name).value = value; ui(name).fire("input"); };
  return { ui, calls, storage, state, texts, change, open, input, document, panel, hook(value) { hook = value; }, failRead(value) { failRead = value; }, failStorage(value) { failStorage = value; }, draft(language) { return JSON.parse(storage.get("codex-console-dev-room-drafts-v2:" + root + ":" + language) || "{}"); }, intent(language = "zh") { return JSON.parse(storage.get("codex-console-dev-room-sync-request-v2:" + root + ":" + language) || "null"); } };
}
let count = 0;
async function test(name, run) { await run(); count++; console.log("PASS " + name); }
const editField = (h, name, value) => { const node = h.document.getElementById("devRoom" + name); node.value = value; node.fire("input"); return node; };
const upload = async h => { const node = h.document.getElementById("devRoomImageFile0"); node.files = [{ name: "replacement.png", type: "image/png", size: 32 }]; node.fire("change"); await settle(); };
await test("media content round-trips without exposing its token in the text field", async () => {
  const parsed = editor.parse(chinese); assert.deepEqual(parsed.sections[0].media, media); assert.doesNotMatch(parsed.sections[0].body, /codex-dev-room-media/);
  parsed.sections[0].media.imageCaption = "第一张图片\n第二行"; const serialized = editor.serialize(chinese, parsed);
  assert.equal(editor.parse(serialized).sections[0].media.imageCaption, "第一张图片\n第二行"); assert.deepEqual(editor.parse(serialized).source, editor.parse(original).source);
  parsed.sections[0].media.section = 1; assert.throws(() => editor.serialize(chinese, parsed)); parsed.sections[0].media.section = 0;
  parsed.sections[0].media.imageCaption = "--> broken"; assert.throws(() => editor.serialize(chinese, parsed));
});
await test("text-only browsing preserves pixels, captions, body and all writes", async () => {
  const h = harness(); await h.open(); const before = h.ui("BodyInput").value, count = h.calls.filter(call => call.method === "POST").length;
  assert.ok(h.ui("Read").querySelector("img")); assert.match(h.ui("Read").textContent, /Original image/);
  h.ui("ViewText").click(); assert.equal(h.panel.dataset.devRoomView, "text"); assert.equal(h.ui("ViewText").attributes["aria-pressed"], "true");
  assert.equal(h.ui("BodyInput").value, before); assert.match(h.ui("Read").textContent, /Original image/); assert.ok(h.ui("Read").querySelector("img"));
  assert.equal(h.calls.filter(call => call.method === "POST").length, count); assert.equal(h.storage.get("codex-console-dev-room-view-v1"), "text");
  h.change("en"); await settle(); assert.equal(h.panel.dataset.devRoomView, "text"); h.ui("ViewImages").click(); assert.equal(h.panel.dataset.devRoomView, "images");
});
await test("fixed imported sections expose an image slot and hide structural additions", async () => {
  const h = harness(); await h.open(); assert.equal(h.ui("New").hidden, true); h.ui("Edit").click();
  assert.ok(h.document.getElementById("devRoomImageFile0")); assert.equal(h.document.getElementById("devRoomImageFile1"), undefined);
  assert.doesNotMatch(h.document.getElementById("devRoomSectionBody0").value, /codex-dev-room-media|sha256/);
  assert.equal(h.ui("Fields").querySelectorAll(".dev-room-section-edit").length, 2);
  h.ui("List").querySelectorAll("button").find(item => item.textContent === "总案").click(); await settle(); assert.equal(h.ui("New").hidden, false);
});
await test("real replacement upload creates a recoverable draft before any game sync", async () => {
  const h = harness(); await h.open(); h.ui("Edit").click(); editField(h, "ImageCaption0", "替换图片说明"); await upload(h);
  const sent = h.calls.find(call => call.url === "/api/dev-room/media/upload").payload;
  assert.deepEqual(Object.keys(sent).sort(), ["expectedRoot", "id", "language", "expectedRevision", "section", "filename", "mimeType", "base64"].sort());
  assert.equal(sent.language, "zh"); assert.equal(sent.section, 0); assert.equal(sent.expectedRoot, root); assert.equal(sent.id, id);
  const draft = editor.parse(h.draft("zh")[id].body); assert.equal(draft.sections[0].media.sha256, "e".repeat(64)); assert.equal(draft.sections[0].media.imageCaption, "替换图片说明");
  assert.equal(draft.sections.length, 2); assert.match(h.ui("Fields").querySelector("img").src, /^data:image\/png;base64,/);
  assert.equal(h.calls.filter(call => call.url === "/api/dev-room/sync/push").length, 0); assert.equal(h.ui("SyncPush").disabled, true);
  h.ui("Save").click(); await settle();
  const saved = h.calls.find(call => call.url === "/api/dev-room/save").payload;
  assert.equal(editor.parse(saved.body).sections[0].media.imageCaption, "替换图片说明");
  assert.equal(editor.parse(h.texts.zh.body).sections[0].media.imageCaption, "替换图片说明");
});
await test("a delayed image receipt from another language cannot overwrite the selected draft", async () => {
  const h = harness(); await h.open(); h.ui("Edit").click(); const gate = deferred();
  h.hook(call => call.url === "/api/dev-room/media/upload" ? gate.promise : undefined);
  const node = h.document.getElementById("devRoomImageFile0"); node.files = [{ name: "late.png", type: "image/png", size: 32 }]; node.fire("change"); await settle();
  const sent = h.calls.find(call => call.url === "/api/dev-room/media/upload").payload; h.change("en"); await settle(); h.ui("Edit").click(); h.input("TitleInput", "Keep English draft");
  gate.resolve(response({ root, id, language: "zh", expectedRevision: sent.expectedRevision, section: 0, sha256: "e".repeat(64), image: { ...media, sha256: "e".repeat(64), stagingName: "e".repeat(64) + ".png" } })); await settle();
  assert.equal(h.ui("TitleInput").value, "Keep English draft"); assert.equal(h.draft("en")[id].title, "Keep English draft"); assert.equal(editor.parse(h.draft("en")[id].body).sections[0].media.sha256, "");
});
await test("game requests freeze one UUID and unknown receipts cannot submit a second time", async () => {
  const h = harness(); await h.open(); h.ui("SyncPush").click(); await settle(); const intent = h.intent();
  assert.ok(intent?.requestId); assert.equal(intent.documentId, id); assert.equal(intent.language, "zh"); assert.match(h.ui("SyncStatus").textContent, /等待游戏确认/); assert.doesNotMatch(h.ui("SyncStatus").textContent, /同步完成/);
  h.ui("SyncPush").click(); h.ui("SyncReceipt").click(); await settle(); assert.equal(h.intent().requestId, intent.requestId); assert.equal(h.calls.filter(call => call.url === "/api/dev-room/sync/push").length, 1);
  h.ui("Reload").click(); await settle(); assert.equal(h.ui("SyncPush").disabled, true); assert.equal(h.ui("SyncReceipt").hidden, false);
  h.hook(call => call.url.startsWith("/api/dev-room/sync/receipt?") ? response({ root, language: "zh", requestId: intent.requestId, documentId: id, status: "applied" }) : undefined);
  h.ui("SyncReceipt").click(); await settle(); assert.equal(h.intent(), null); assert.match(h.ui("SyncStatus").textContent, /游戏已确认写入/);
});
await test("unaccepted conflicts release their UUID while a wrong receipt retains it", async () => {
  const h = harness(); await h.open(); h.hook(call => call.url === "/api/dev-room/sync/push" ? response({ error: "Changed", accepted: false }, 409) : undefined);
  h.ui("SyncPush").click(); await settle(); assert.equal(h.intent(), null); assert.equal(h.ui("SyncPush").disabled, false);
  h.hook(null); h.ui("SyncPush").click(); await settle(); const intent = h.intent();
  h.hook(call => call.url.startsWith("/api/dev-room/sync/receipt?") ? response({ root, language: "zh", requestId: randomUUID(), status: "applied" }) : undefined);
  h.ui("SyncReceipt").click(); await settle(); assert.equal(h.intent().requestId, intent.requestId); assert.equal(h.ui("SyncPush").disabled, true);
});
await test("import preview is language-bound and only explicit confirmation writes content", async () => {
  const h = harness(); await h.open(); h.ui("SyncPull").click(); await settle(); assert.equal(h.ui("SyncPreview").hidden, false);
  assert.equal(h.calls.filter(call => call.url === "/api/dev-room/sync/import").length, 0); h.ui("SyncApply").click(); await settle();
  const sent = h.calls.find(call => call.url === "/api/dev-room/sync/import").payload; assert.equal(sent.language, "zh"); assert.equal(sent.expectedRoot, root); assert.ok(sent.requestId); assert.equal(h.intent(), null);
  h.hook(call => call.url.startsWith("/api/dev-room/sync/preview?") ? response({ root, language: "en", canImport: true, planSha256: "f".repeat(64), indexRevision: "a".repeat(64), changes: [] }) : undefined);
  h.ui("SyncPull").click(); await settle(); assert.equal(h.ui("SyncPreview").hidden, true); assert.equal(h.ui("SyncApply").disabled, true);
});
await test("saved image bytes load only through a guarded same-origin endpoint", async () => {
  const h = harness(); await h.open(); const pixels = h.ui("Read").querySelector("img"), url = new URL(pixels.src, "http://console.fixture");
  assert.equal(url.pathname, "/api/dev-room/media"); assert.equal(url.searchParams.get("expectedRoot"), root); assert.equal(url.searchParams.get("id"), id);
  assert.equal(url.searchParams.get("language"), "zh"); assert.equal(url.searchParams.get("section"), "0"); assert.equal(url.searchParams.get("revision"), "a".repeat(64));
  const css = fs.readFileSync(new URL("../styles.css", import.meta.url), "utf8"); assert.match(css, /\[data-dev-room-view="text"\] \.dev-room-media img\s*\{\s*display: none/);
  assert.ok(h.calls.every(call => call.url.startsWith("/api/"))); assert.doesNotMatch(h.ui("Read").textContent, /codex-dev-room-media|assetPath|sha256/);
});
await test("late sync completion cannot replace another language's draft or status", async () => {
  const h = harness(); await h.open(); const gate = deferred();
  h.hook(call => call.url === "/api/dev-room/sync/push" ? gate.promise : undefined);
  h.ui("SyncPush").click(); await settle(); const intent = h.intent();
  h.change("en"); await settle(); h.ui("Edit").click(); h.input("TitleInput", "English remains current");
  gate.resolve(response({ root, language: "zh", documentId: id, requestId: intent.requestId, status: "unchanged" })); await settle();
  assert.equal(h.ui("TitleInput").value, "English remains current"); assert.equal(h.draft("en")[id].title, "English remains current");
  assert.doesNotMatch(h.ui("SyncStatus").textContent, /Both versions match/); assert.equal(h.intent("zh"), null);
});
await test("damaged sync storage cannot enable a duplicate submission", async () => {
  const h = harness(); await h.open(); h.storage.set("codex-console-dev-room-sync-request-v2:" + root + ":zh", "{ damaged receipt bank");
  h.ui("Reload").click(); await settle(); assert.equal(h.ui("SyncPush").disabled, true); assert.match(h.ui("SyncStatus").textContent, /同步记录暂时无法读取/);
  h.ui("SyncPush").click(); assert.equal(h.calls.filter(call => call.url === "/api/dev-room/sync/push").length, 0);
});
await test("a conflict text copy keeps the original image draft and never inherits its game identity", async () => {
  const h = harness(); await h.open(); h.ui("Edit").click(); editField(h, "ImageCaption0", "保留这张替换图"); await upload(h);
  const originalDraft = h.draft("zh")[id];
  h.hook(call => {
    if (call.url !== "/api/dev-room/save") return undefined;
    const sent = call.payload;
    if (sent.id === id) return response({ error: "Changed" }, 409);
    const local = { id: sent.id, language: sent.language, title: sent.title, body: sent.body, revision: "b".repeat(64), updatedAt: "", translationMissing: false };
    return response({ root, document: local, documents: [...h.state(sent.language).documents, local] });
  });
  h.ui("Save").click(); await settle(); assert.equal(h.ui("Copy").textContent, "保存文字副本"); assert.match(h.ui("Status").textContent, /图片和替换图片的草稿保留在原文档/);
  h.ui("Copy").click(); await settle(); const copied = h.calls.filter(call => call.url === "/api/dev-room/save").at(-1).payload;
  assert.notEqual(copied.id, id); assert.doesNotMatch(copied.body, /rr-dev-room:|codex-dev-room-media|stagingName|assetPath/); assert.match(copied.body, /保留这张替换图/);
  const kept = h.draft("zh")[id]; for (const field of ["id", "title", "body", "expectedRevision", "language"]) assert.equal(kept[field], originalDraft[field]);
  assert.equal(editor.parse(kept.body).sections[0].media.sha256, "e".repeat(64)); assert.equal(h.ui("SyncPush").disabled, true);
});
await test("a missing English overview retains seventeen bound documents in game order", async () => {
  const docs = Array.from({ length: 17 }, (_, n) => ({ id: randomUUID(), title: `Game document ${n}`, language: "en", updatedAt: new Date(2030, 0, 17 - n).toISOString() }));
  const bindings = docs.map((doc, n) => ({ documentId: doc.id, unityDocumentId: `document-${String(n).padStart(2, "0")}`, category: Math.floor(n / 4), categoryOrder: n === 0 ? -1 : Math.floor(n / 4), categoryTitle: n === 0 ? "设备私有展示" : "Systems", order: n % 4, scope: n === 0 ? "displayContent" : "globalLibrary", lastUnityRevision: "c".repeat(64) }));
  const local = [ { id: randomUUID(), title: "Local latest", language: "en" }, { id: randomUUID(), title: "Local earlier", language: "en" } ];
  const expected = bindings.slice().sort((a, b) => a.categoryOrder - b.categoryOrder || a.order - b.order || a.unityDocumentId.localeCompare(b.unityDocumentId)).map(binding => docs.find(doc => doc.id === binding.documentId).title);
  const h = harness({ language: "en" });
  h.hook(call => {
    if (call.url.startsWith("/api/dev-room/sync/status?")) return response({ root, language: "en", bindings: bindings.slice().reverse(), pending: [] });
    if (!call.url.startsWith("/api/dev-room/state?")) return undefined;
    const query = new URLSearchParams(call.url.split("?")[1]);
    const overview = { id: "overview", title: "Overview", language: "en", body: "", sourceBody: "# Dev Room\n\nNew game index", translationMissing: true, revision: "a".repeat(64), updatedAt: "" };
    return response({ root, documents: [overview, ...local, ...docs.slice().reverse()], document: query.get("id") === "overview" ? overview : docs.find(doc => doc.id === query.get("id")) });
  });
  await settle(); h.ui("Reload").click(); await settle();
  const titles = h.ui("List").querySelectorAll("button").map(node => node.textContent);
  assert.deepEqual(titles, ["Overview · Translation needed", ...expected, ...local.map(doc => doc.title)]); assert.match(h.ui("List").textContent, /Device displays/); assert.doesNotMatch(h.ui("List").textContent, /设备私有展示/);
});
await test("a replacement draft requests guarded pixels after losing its memory preview without another upload", async () => {
  const originalWindow = harness(); await originalWindow.open(); originalWindow.ui("Edit").click(); editField(originalWindow, "ImageCaption0", "恢复图片和说明"); await upload(originalWindow);
  const recovered = harness({ storage: [...originalWindow.storage] }); await settle();
  recovered.ui("List").querySelectorAll("button").find(node => node.textContent.startsWith("战斗与人工智能")).click(); await settle();
  const pixels = recovered.ui("Fields").querySelector("img"), url = new URL(pixels.src, "http://console.fixture");
  assert.equal(url.pathname, "/api/dev-room/media/draft"); assert.equal(url.searchParams.get("expectedRoot"), root); assert.equal(url.searchParams.get("id"), id);
  assert.equal(url.searchParams.get("language"), "zh"); assert.equal(url.searchParams.get("section"), "0"); assert.equal(url.searchParams.get("revision"), "a".repeat(64));
  assert.equal(url.searchParams.get("stagingName"), "e".repeat(64) + ".png"); assert.equal(recovered.ui("Editor").hidden, false);
  assert.match(recovered.ui("Fields").textContent, /恢复图片和说明/); assert.equal(recovered.calls.filter(call => call.method === "POST").length, 0);
  recovered.ui("ViewText").click(); assert.equal(recovered.ui("Fields").querySelector("img"), pixels); assert.equal(recovered.panel.dataset.devRoomView, "text");
  const kept = recovered.draft("zh")[id].body; recovered.change("en"); await settle(); pixels.fire("error");
  assert.equal(recovered.ui("TitleInput").value, "Combat & AI"); assert.equal(recovered.draft("zh")[id].body, kept); assert.deepEqual(recovered.draft("en"), {});
  const activeUrl = new URL(recovered.ui("Read").querySelector("img").src, "http://console.fixture"); assert.equal(activeUrl.pathname, "/api/dev-room/media"); assert.equal(activeUrl.searchParams.get("language"), "en");
});
await test("draft media never inherits another library's token or follows a mismatched object name", async () => {
  const originalWindow = harness(); await originalWindow.open(); originalWindow.ui("Edit").click(); await upload(originalWindow);
  const recovered = harness({ storage: [...originalWindow.storage] }), otherRoot = "D:/fixture/other-library";
  recovered.hook(call => {
    if (call.url === "/api/documents/state") return response({ root: otherRoot });
    if (!call.url.startsWith("/api/dev-room/state?")) return undefined;
    const query = new URLSearchParams(call.url.split("?")[1]), result = recovered.state(query.get("language"), query.get("id")); result.root = otherRoot; return response(result);
  });
  await settle(); recovered.ui("Reload").click(); await settle(); recovered.ui("List").querySelectorAll("button").find(node => node.textContent === "战斗与人工智能").click(); await settle();
  assert.equal(recovered.ui("Editor").hidden, true); const pixels = new URL(recovered.ui("Read").querySelector("img").src, "http://console.fixture");
  assert.equal(pixels.pathname, "/api/dev-room/media"); assert.equal(pixels.searchParams.get("expectedRoot"), otherRoot); assert.equal(pixels.searchParams.has("stagingName"), false);
  const old = originalWindow.draft("zh")[id], parsed = editor.parse(old.body); parsed.sections[0].media.sha256 = "f".repeat(64);
  const bank = new Map([["codex-console-dev-room-drafts-v2:" + root + ":zh", JSON.stringify({ [id]: { ...old, body: editor.serialize(old.body, parsed) } })]]);
  const mismatch = harness({ storage: [...bank] }); await settle(); mismatch.ui("List").querySelectorAll("button").find(node => node.textContent.startsWith("战斗与人工智能")).click(); await settle();
  assert.equal(mismatch.ui("Fields").querySelector("img"), null); assert.equal(mismatch.calls.filter(call => call.method === "POST").length, 0); assert.ok(mismatch.calls.every(call => call.url.startsWith("/api/")));
});
await test("managed navigation localizes known groups and same-language summary links without rewriting source prose", async () => {
  const h = harness({ language: "en", realMarkdown: true }), building = randomUUID();
  const originalBody = "# Dev Room\n\n## 设备私有展示\n- [建造系统](" + building + ".md)\n\n## 项目概览\n- [战斗与人工智能](" + id + ".md)\n\n## 未定义分类\n保留未知原文。\n";
  const state = managed => call => {
    if (!call.url.startsWith("/api/dev-room/state?")) return undefined;
    const query = new URLSearchParams(call.url.split("?")[1]), result = h.state(query.get("language"), query.get("id"));
    result.documents.push({ id: building, title: "Building System", language: "en", updatedAt: "" });
    if (result.document?.id === "overview") Object.assign(result.document, { title: "Overview", body: originalBody, sourceBody: originalBody, generatedNavigation: managed });
    return response(result);
  };
  h.hook(state(true)); await settle(); h.ui("Reload").click(); await settle();
  assert.equal(h.ui("Edit").disabled, true); assert.equal(h.ui("Save").disabled, true); assert.match(h.ui("Edit").title, /Generated from the game/);
  assert.equal(h.ui("BodyInput").value, originalBody); assert.match(h.ui("Read").textContent, /Device displays|Project Overview/); assert.doesNotMatch(h.ui("Read").textContent, /设备私有展示|项目概览|建造系统|战斗与人工智能/);
  assert.deepEqual(h.ui("Read").querySelectorAll("button").map(node => node.textContent), ["Building System", "Combat & AI"]); assert.match(h.ui("Read").textContent, /未定义分类|保留未知原文/);
  h.ui("Edit").click(); assert.equal(h.ui("Editor").hidden, true); assert.equal(h.calls.filter(call => call.method === "POST").length, 0);
  h.hook(state(false)); h.ui("Reload").click(); await settle(); assert.equal(h.ui("Edit").disabled, false); assert.equal(h.ui("BodyInput").value, originalBody);
  assert.match(h.ui("Read").textContent, /设备私有展示|项目概览|建造系统|战斗与人工智能/);
});
await test("game-bound missing translations do not expose a structural new-document action", async () => {
  const h = harness({ missing: true }); await h.open(); assert.equal(h.ui("BodyInput").value, ""); assert.equal(h.ui("New").hidden, true); assert.equal(h.ui("Edit").disabled, false);
});
await test("drafts block import before any UUID or write and saving invalidates the old preview", async () => {
  const h = harness(); await h.open(); h.ui("Edit").click(); h.input("TitleInput", "待保存草稿"); h.ui("SyncPull").click(); await settle();
  assert.equal(h.ui("SyncApply").disabled, true); assert.match(h.ui("SyncStatus").textContent, /请先保存当前语言的草稿/);
  h.ui("SyncApply").fire("click"); await settle(); assert.equal(h.intent(), null); assert.equal(h.calls.filter(call => call.url === "/api/dev-room/sync/import").length, 0);
  h.ui("Save").click(); await settle(); assert.equal(h.ui("SyncPreview").hidden, true); assert.equal(h.ui("SyncApply").disabled, true); assert.match(h.ui("SyncStatus").textContent, /重新核对.*预览/);
  h.ui("SyncPull").click(); await settle(); assert.equal(h.ui("SyncApply").disabled, false); h.ui("SyncApply").click(); await settle(); assert.equal(h.calls.filter(call => call.url === "/api/dev-room/sync/import").length, 1);
});
await test("sync errors show actionable bridge and draft reasons while accepted requests remain frozen", async () => {
  for (const [code, accepted, pattern] of [["bridge_unavailable", false, /同步窗口未开启或已过期/], ["bridge_changed", true, /同步窗口已改变.*原请求待核对/], ["unsaved_draft", false, /请先保存当前语言的草稿/], ["unsupported_image_identity", false, /原图身份暂时无法核对/]]) {
    const h = harness(); await h.open(); h.hook(call => call.url === "/api/dev-room/sync/push" ? response({ error: "Rejected", code, accepted }, 409) : undefined);
    h.ui("SyncPush").click(); await settle(); assert.match(h.ui("SyncStatus").textContent, pattern); assert.doesNotMatch(h.ui("SyncStatus").textContent, /文档、来源或资料库已改变/); assert.equal(Boolean(h.intent()), accepted);
  }
});
await test("an applied receipt flags saved edits made after submission as local and unsynced", async () => {
  const h = harness(); await h.open(); h.ui("SyncPush").click(); await settle(); const intent = h.intent();
  h.ui("Edit").click(); h.input("TitleInput", "提交后已保存的新标题"); h.ui("Save").click(); await settle(); assert.equal(h.draft("zh")[id], undefined);
  const savedBody = h.texts.zh.body;
  h.hook(call => call.url.startsWith("/api/dev-room/sync/receipt?") ? response({ root, language: "zh", requestId: intent.requestId, documentId: id, status: "applied", localChangedSincePush: true }) : undefined);
  h.ui("SyncReceipt").click(); await settle();
  assert.match(h.ui("SyncStatus").textContent, /本次提交版本已写回；后来的本地修改尚未同步/); assert.doesNotMatch(h.ui("SyncStatus").textContent, /同步完成/);
  assert.equal(h.ui("TitleInput").value, "提交后已保存的新标题"); assert.equal(h.ui("BodyInput").value, savedBody); assert.equal(h.intent(), null);
  assert.equal(h.calls.filter(call => call.url === "/api/dev-room/sync/push").length, 1);
});
await test("an applied receipt keeps later unsaved text and image drafts without claiming they were synced", async () => {
  const h = harness(); await h.open(); h.ui("SyncPush").click(); await settle(); const intent = h.intent();
  h.ui("Edit").click(); h.input("TitleInput", "提交后未保存的新标题"); editField(h, "ImageCaption0", "后来的图片说明"); await upload(h); const draft = h.draft("zh")[id];
  h.hook(call => call.url.startsWith("/api/dev-room/sync/receipt?") ? response({ root, language: "zh", requestId: intent.requestId, documentId: id, status: "applied", localChangedSincePush: false }) : undefined);
  h.ui("SyncReceipt").click(); await settle();
  assert.match(h.ui("SyncStatus").textContent, /本次提交版本已写回；后来的本地修改尚未同步/); assert.equal(h.ui("Editor").hidden, false); assert.equal(h.ui("TitleInput").value, "提交后未保存的新标题");
  const kept = h.draft("zh")[id]; assert.equal(kept.body, draft.body); assert.equal(kept.expectedRevision, draft.expectedRevision);
  assert.equal(editor.parse(kept.body).sections[0].media.sha256, "e".repeat(64)); assert.equal(editor.parse(kept.body).sections[0].media.imageCaption, "后来的图片说明");
  assert.equal(h.calls.filter(call => call.url === "/api/dev-room/save").length, 0); assert.equal(h.calls.filter(call => call.url === "/api/dev-room/sync/push").length, 1); assert.equal(h.ui("SyncPush").disabled, true);
});
await test("stale translations are marked for review even when another status claims synced", async () => {
  for (const documentFlag of [false, true]) {
    const h = harness({ language: "en" });
    h.hook(call => {
      if (call.url.startsWith("/api/dev-room/sync/status?")) return response({ root, language: "en", bindings: [{ documentId: id, lastUnityRevision: "c".repeat(64), status: documentFlag ? "synced" : "translation_stale", translationStale: !documentFlag }], pending: [] });
      if (!documentFlag || !call.url.startsWith("/api/dev-room/state?")) return undefined;
      const query = new URLSearchParams(call.url.split("?")[1]), result = h.state(query.get("language"), query.get("id")); if (result.document?.id === id) result.document.translationStale = true;
      return response(result);
    });
    await settle(); h.ui("List").querySelectorAll("button").find(node => node.textContent.startsWith("Combat & AI")).click(); await settle();
    assert.match(h.ui("List").textContent, /Translation needs review/); assert.equal(h.ui("SyncStatus").textContent, "Translation needs review"); assert.doesNotMatch(h.ui("SyncStatus").textContent, /synced|confirmed|Both versions match/i);
  }
});
await test("missing empty translations show their label and cannot push through either the button or handler", async () => {
  const h = harness({ missing: true });
  h.hook(call => call.url.startsWith("/api/dev-room/sync/status?") ? response({ root, language: "zh", bindings: [{ documentId: id, lastUnityRevision: "c".repeat(64), status: "translation_missing", translationMissing: true }], pending: [] }) : undefined);
  await settle(); h.ui("List").querySelectorAll("button").find(node => node.textContent.startsWith("待翻译文档")).click(); await settle();
  assert.match(h.ui("List").textContent, /待翻译/); assert.equal(h.ui("SyncStatus").textContent, "待翻译"); assert.equal(h.ui("SyncPush").disabled, true); assert.equal(h.ui("BodyInput").value, "");
  h.ui("SyncPush").fire("click"); await settle(); assert.equal(h.intent(), null); assert.equal(h.calls.filter(call => call.url === "/api/dev-room/sync/push").length, 0);
});
console.log(count + " Dev Room content-controller checks passed.");
