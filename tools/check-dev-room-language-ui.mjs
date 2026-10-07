// Exercise the actual Dev Room controller with isolated DOM/storage/network fixtures.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { createRequire } from "node:module";
import { randomUUID } from "node:crypto";
const require = createRequire(import.meta.url), editor = require("../dev-room-editor.js");
const app = fs.readFileSync(new URL("../app.js", import.meta.url), "utf8");
const source = app.slice(app.indexOf("// Dev Room keeps confirmed documents"));
const id = "e0b1ef39-c71b-50f9-b9b4-50885af0bc74", root = "D:/fixture/library";
const original = '<!-- rr-dev-room:v1 {"id":"gameplay-combat-ai","guid":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"} -->\n# Combat & AI\n\n<!-- rr-dev-room:summary -->\nCombat rules.\n<!-- rr-dev-room:summary-end -->\n\n<!-- rr-dev-room:section 0 -->\n## Overview\nAim and hit.\n<!-- rr-dev-room:section-end 0 -->\n\n<!-- rr-dev-room:section 1 -->\n## References\nAssets/Scripts/Gameplay/AI\n<!-- rr-dev-room:section-end 1 -->\n\n';
const model = editor.parse(original);
model.title = "战斗与人工智能"; model.summary = "战斗的共同规则。";
model.sections[0].title = "概述"; model.sections[0].body = "瞄准并命中。"; model.sections[1].title = "参考资料";
const chinese = editor.serialize(original, model);
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const response = (value, status = 200) => ({ ok: status < 400, status, async json() { return structuredClone(value); } });
const settle = async () => { for (let n = 0; n < 12; n++) await new Promise(resolve => setImmediate(resolve)); };
function harness(options = {}) {
  let document, hook = null, failStorage = false, failRead = false;
  const observers = [], storage = new Map(), calls = [], nodes = new Map();
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
  for (const name of ["Heading", "List", "Title", "SavedAt", "Read", "Editor", "TitleInput", "BodyInput", "BodyLabel", "Fields", "Agent", "AgentContent", "Edit", "Save", "Copy", "New", "Reload", "Status"]) {
    const node = new Element(name.endsWith("Input") ? name === "BodyInput" ? "textarea" : "input" : ["Edit", "Save", "Copy", "New", "Reload"].includes(name) ? "button" : "div");
    node.id = "devRoom" + name; nodes.set(node.id, node);
    (name === "List" ? sidebar : section).append(node);
  }
  nodes.get("devRoomAgent").append(new Element("summary"));
  const ui = name => nodes.get("devRoom" + name);
  ui("Agent").append(ui("AgentContent"));
  document = { documentElement: { lang: options.language || "zh-CN" }, activeElement: panel, createElement: tag => new Element(tag), createTextNode: text => { const node = new Element("#text"); node.textContent = text; return node; }, getElementById: name => nodes.get(name) || panel.querySelectorAll("input, textarea").find(item => item.id === name) };
  const texts = { zh: { title: "战斗与人工智能", body: chinese }, en: { title: "Combat & AI", body: original } };
  let revision = "a".repeat(64);
  function state(language, selected = "overview") {
    const overview = { id: "overview", title: language === "zh" ? "总案" : "Overview", body: language === "zh" ? "## 玩法\n- [战斗与人工智能](" + id + ".md)\n" : "## Gameplay\n- [Combat & AI](" + id + ".md)\n", revision, updatedAt: "", language, sourceBody: "", translationMissing: false };
    const combat = { id, ...texts[language], revision, language, sourceBody: original, updatedAt: "", translationMissing: Boolean(options.missing) };
    if (options.missing) { combat.title = language === "zh" ? "待翻译文档" : "Translation needed"; combat.body = ""; }
    return { root, documents: [overview, combat].map(item => ({ id: item.id, title: item.title, language, updatedAt: "" })), document: selected === id ? combat : selected === "overview" ? overview : null };
  }
  const runtime = {
    document, URLSearchParams, crypto: { randomUUID }, MutationObserver: class { constructor(callback) { this.callback = callback; observers.push(this); } observe(target) { this.target = target; } },
    window: { CodexDevRoomEditor: editor, addEventListener() {} },
    localStorage: { getItem(key) { if (failRead) throw Error("Fixture storage read failed"); return storage.get(key) || null; }, setItem(key, value) { if (failStorage) throw Error("Fixture storage full"); storage.set(key, value); } },
    renderDocumentMarkdown(markdown, element) { element.textContent = markdown; },
    async fetch(url, init = {}) {
      const call = { url, ...init, payload: init.body ? JSON.parse(init.body) : null }; calls.push(call);
      const hooked = hook?.(call); if (hooked !== undefined) return await hooked;
      if (url === "/api/documents/state") return response({ root });
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
  return { ui, calls, storage, state, texts, change, open, input, document, panel, hook(value) { hook = value; }, failRead(value) { failRead = value; }, failStorage(value) { failStorage = value; }, draft(language) { return JSON.parse(storage.get("codex-console-dev-room-drafts-v2:" + root + ":" + language) || "{}"); } };
}
let count = 0;
async function test(name, run) { await run(); count++; console.log("PASS " + name); }
await test("one chosen language is requested for the overview, sidebar and actual document", async () => {
  const h = harness(); await h.open(); assert.equal(h.ui("Title").textContent, "战斗与人工智能"); assert.match(h.ui("Read").textContent, /战斗的共同规则/); assert.doesNotMatch(h.ui("Read").textContent, /Combat|Aim|rr-dev-room|Assets\//);
  assert.ok(h.calls.filter(call => call.url.startsWith("/api/dev-room/state?")).every(call => call.url.includes("language=zh")));
  h.change("en"); await settle(); assert.equal(h.ui("Title").textContent, "Combat & AI"); assert.doesNotMatch(h.ui("Read").textContent, /[\u3400-\u9fff]/); assert.equal(h.ui("Heading").textContent, "Dev Room");
});
await test("rapid language changes reject a delayed body from the previous language", async () => {
  const h = harness(); await h.open(); const gate = deferred();
  h.hook(call => call.url.includes("/api/dev-room/state?") && call.url.includes("language=en") ? gate.promise : undefined);
  h.change("en"); await settle(); assert.equal(h.ui("TitleInput").value, ""); h.change("zh-CN"); await settle();
  gate.resolve(response(h.state("en", id))); await settle(); assert.equal(h.ui("Title").textContent, "战斗与人工智能"); assert.match(h.ui("Read").textContent, /共同规则/);
});
await test("Chinese and English drafts survive switching with their original conflict base", async () => {
  const h = harness(); await h.open(); h.ui("Edit").click(); h.input("TitleInput", "中文草稿"); const zhRevision = h.draft("zh")[id].expectedRevision;
  h.change("en"); await settle(); assert.equal(h.ui("TitleInput").value, "Combat & AI"); h.ui("Edit").click(); h.input("TitleInput", "English draft");
  h.change("zh-CN"); await settle(); assert.equal(h.ui("TitleInput").value, "中文草稿"); assert.equal(h.draft("zh")[id].expectedRevision, zhRevision); assert.equal(h.draft("en")[id].title, "English draft");
});
await test("a confirmed save finishing in the old language cannot overwrite or erase the new draft", async () => {
  const h = harness(); await h.open(); h.ui("Edit").click(); h.input("TitleInput", "中文保存稿"); const gate = deferred();
  h.hook(call => call.url === "/api/dev-room/save" ? gate.promise : undefined);
  h.ui("Save").click(); await settle(); const sent = h.calls.find(call => call.payload?.language === "zh").payload;
  h.change("en"); await settle(); h.ui("Edit").click(); h.input("TitleInput", "Keep English draft");
  const saved = h.state("zh", id); saved.document.title = sent.title; saved.document.body = sent.body; gate.resolve(response(saved)); await settle();
  assert.equal(h.ui("TitleInput").value, "Keep English draft"); assert.equal(h.draft("en")[id].title, "Keep English draft"); assert.equal(h.draft("zh")[id], undefined);
});
await test("missing canonical translations expose an empty target-language edit frame rather than source prose", async () => {
  const h = harness({ missing: true }); await h.open(); assert.match(h.ui("Read").textContent, /没有中文版本/); assert.doesNotMatch(h.ui("Read").textContent, /Aim and hit/);
  h.ui("Edit").click(); const model = editor.parse(h.ui("BodyInput").value);
  assert.deepEqual(model.source, editor.parse(original).source); assert.equal(model.summary, ""); assert.ok(model.sections.every(section => section.body === ""));
  assert.doesNotMatch(model.sections.map(section => section.title).join(" "), /Overview|References/);
});
await test("legacy drafts remain untouched and visible in read-only Agent details", async () => {
  const legacy = { [id]: { id, title: "Legacy English draft", body: "# Old English notes", expectedRevision: "c".repeat(64) } }, h = harness({ legacy });
  await h.open(); assert.equal(h.ui("TitleInput").value, "战斗与人工智能"); assert.match(h.ui("AgentContent").textContent, /Old English notes/); h.change("en"); await settle();
  assert.equal(h.ui("TitleInput").value, "Combat & AI"); assert.deepEqual(JSON.parse(h.storage.get("codex-console-dev-room-drafts-v1:" + root)), legacy);
});
await test("failed draft storage hides the old language and keeps unsaved fields for returning", async () => {
  const h = harness(); await h.open(); h.ui("Edit").click(); h.input("TitleInput", "必须保留"); h.failStorage(true); h.change("en"); await settle();
  assert.equal(h.ui("Editor").hidden, true); assert.doesNotMatch(h.ui("Read").textContent, /[\u3400-\u9fff]/); assert.equal(h.ui("TitleInput").value, "必须保留"); assert.equal(h.ui("Save").disabled, true);
  h.failStorage(false); h.change("zh-CN"); await settle(); assert.equal(h.ui("Editor").hidden, false); assert.equal(h.ui("TitleInput").value, "必须保留");
});
await test("a payload claiming the wrong language cannot fill the selected document", async () => {
  const h = harness(); await h.open(); h.hook(call => call.url.startsWith("/api/dev-room/state?") ? response(h.state("zh", id)) : undefined);
  h.change("en"); await settle(); assert.match(h.ui("Read").textContent, /could not be loaded/); assert.doesNotMatch(h.ui("Read").textContent, /[\u3400-\u9fff]/);
});
await test("a never-saved legacy UUID remains reachable without translating or overwriting its original draft", async () => {
  const pending = randomUUID(), legacy = { [pending]: { id: pending, title: "旧未保存稿", body: "Unpublished original", expectedRevision: "" } }, h = harness({ legacy });
  await settle(); h.ui("List").querySelectorAll("button").find(item => item.textContent === "旧格式草稿").click(); await settle();
  assert.equal(h.ui("Agent").hidden, false); assert.match(h.ui("AgentContent").textContent, /Unpublished original/);
  assert.equal(h.calls.filter(call => call.method === "POST").length, 0); assert.deepEqual(JSON.parse(h.storage.get("codex-console-dev-room-drafts-v1:" + root)), legacy);
});
await test("failed or malformed draft-bank reads cannot replace other document drafts", async () => {
  for (const broken of [false, true]) {
    const h = harness(); await h.open(); h.ui("Edit").click();
    const key = "codex-console-dev-room-drafts-v2:" + root + ":zh", bank = broken ? "{ damaged JSON" : JSON.stringify({ [randomUUID()]: { title: "Other draft", body: "Keep" } });
    h.storage.set(key, bank); if (!broken) h.failRead(true); h.input("TitleInput", "当前未保存"); assert.equal(h.storage.get(key), bank);
    assert.match(h.ui("Status").textContent, /草稿暂时无法保留/);
  }
});
await test("a same-identity save receipt with changed or missing content cannot clear the draft", async () => {
  const h = harness(); await h.open(); h.ui("Edit").click(); h.input("TitleInput", "保留此稿");
  h.hook(call => {
    if (call.url !== "/api/dev-room/save") return undefined;
    const result = h.state("zh", id); result.document.translationMissing = true; result.document.body = "";
    return response(result);
  });
  h.ui("Save").click(); await settle(); assert.equal(h.draft("zh")[id].title, "保留此稿"); assert.match(h.ui("Status").textContent, /当前草稿已保留/); assert.equal(h.ui("Editor").hidden, false);
});
await test("a saved draft left by failed cleanup resumes the current saved revision without rebasing different edits", async () => {
  const h = harness(); await h.open(); h.ui("Edit").click(); h.input("TitleInput", "已保存稿");
  h.hook(call => { if (call.url === "/api/dev-room/save") h.failStorage(true); return undefined; });
  h.ui("Save").click(); await settle(); assert.equal(h.draft("zh")[id].expectedRevision, "a".repeat(64));
  h.failStorage(false); h.hook(null); h.ui("Reload").click(); await settle();
  assert.equal(h.ui("Editor").hidden, true); h.ui("Edit").click(); h.input("TitleInput", "继续修改");
  assert.equal(h.draft("zh")[id].expectedRevision, "b".repeat(64));
  h.ui("Save").click(); await settle(); assert.equal(h.calls.filter(call => call.url === "/api/dev-room/save")[1].payload.expectedRevision, "b".repeat(64));
  const old = { id, language: "zh", title: "不同的旧稿", body: chinese, expectedRevision: "a".repeat(64) };
  h.storage.set("codex-console-dev-room-drafts-v2:" + root + ":zh", JSON.stringify({ [id]: old }));
  h.ui("Reload").click(); await settle(); h.input("TitleInput", "保留旧稿"); assert.equal(h.draft("zh")[id].expectedRevision, "a".repeat(64));
});
console.log(count + " Dev Room language-controller checks passed.");
