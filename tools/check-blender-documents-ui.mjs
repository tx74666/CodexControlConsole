#!/usr/bin/env node
// Isolated document-entry regressions; no user library, inbox, or browser writes.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
function extract(name) {
  const start = source.search(new RegExp(`(?:async )?function ${name}\\(`));
  assert.ok(start >= 0, `Missing ${name}`);
  const end = source.slice(start + 1).search(/\n(?:async )?function /);
  return source.slice(start, end < 0 ? undefined : start + 1 + end);
}
const defer = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const fixture = () => [{ id: "custom-nodes-reference", module: "blender", defaultLanguage: "zh-CN", variants: [
  { language: "zh-CN", title: "自定义节点参考", summary: "中文说明", available: true },
  { language: "en", title: "Custom Nodes reference", summary: "English summary <script>literal</script>", available: true }
] }];
function harness() {
  const calls = [], nodes = new Map(), opened = [], stored = new Map();
  let gate = null, responseRoot = null, items = fixture(), state = { root: "D:/资料 & reading", exists: true }, module = "blender";
  class Element {
    constructor(tag = "div") {
      this.tagName = tag.toUpperCase(); this.children = []; this.listeners = {}; this.dataset = {}; this.attributes = {}; this._text = ""; this.hidden = false;
      this.classList = { toggle() {}, remove() {} }; this.style = { setProperty() {} };
    }
    replaceChildren(...items) { this.children = items; this._text = ""; }
    append(...items) { this.children.push(...items); }
    appendChild(item) { this.children.push(item); return item; }
    set textContent(value) { this.replaceChildren(); this._text = String(value); }
    get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    removeAttribute(key) { delete this.attributes[key]; if (key === "href") delete this.href; }
    addEventListener(key, value) { this.listeners[key] = value; }
  }
  const tabs = ["character", "builder", "document"].map(value => { const node = new Element("button"); node.dataset.blenderViewTarget = value; return node; });
  const views = ["character", "builder", "document"].map(value => { const node = new Element(); node.dataset.blenderView = value; return node; });
  const document = {
    getElementById(id) { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); },
    createElement: tag => new Element(tag),
    querySelector() { return null; },
    querySelectorAll(selector) { return selector === "[data-blender-view-target]" ? tabs : selector === "[data-blender-view]" ? views : []; }
  };
  const runtime = {
    URL, URLSearchParams, document, language: "en", runtimeActivityReady: true, activeBlenderView: "document", documentReadingWindow: null,
    blenderDocuments: { root: "", items: [], loaded: false, busy: false, sequence: 0, error: "", unavailable: "", fallbackUrl: "" },
    documentLibrary: { root: "" }, isModuleForeground: expected => module === expected,
    documentText: (zh, en) => runtime.language === "zh" ? zh : en,
    window: { location: { href: "http://127.0.0.1:12345/blender.html" }, addEventListener() {}, clearTimeout() {}, cancelAnimationFrame() {},
      open(url, name) { const popup = { closed: false, location: { href: url }, focus() {} }; opened.push({ url, name }); return popup; } },
    blenderViewTransitionSequence: 0, blenderViewTransitionTimer: 0, blenderViewTransitionFrame: 0, blenderViewTransitionAnimations: [],
    localStorage: { setItem(key, value) { stored.set(key, value); } }, storageKeys: { blenderView: "view" }, els: {},
    referenceViewProjectPath: () => "", hasRandomRealmArtTools: () => false, referenceViewLoadedProject: "",
    async documentRequest(endpoint, payload) {
      assert.equal(payload, undefined, "reference discovery must be read-only"); calls.push(endpoint);
      if (endpoint === "state") return { ...state };
      assert.ok(endpoint.startsWith("references?module=blender&expectedRoot="));
      const result = { root: responseRoot || state.root, items };
      const wait = gate; gate = null; if (wait) await wait.promise;
      return result;
    }
  };
  const names = ["sameDocumentInboxRoot", "blenderDocumentNode", "blenderDocumentReaderUrl", "normalizeBlenderDocumentReferences", "renderBlenderDocuments", "loadBlenderDocuments", "bindBlenderDocuments", "normalizeBlenderWorkspaceView", "setBlenderWorkspaceView", "openDocumentReaderUrl"];
  const api = runInNewContext(`${names.map(extract).join("\n")}\n({${names.join(",")}})`, runtime);
  return { api, runtime, calls, opened, tabs, views, stored,
    node: name => document.getElementById(`blenderDocuments${name}`),
    setState(value) { state = value; }, setItems(value) { items = value; }, setModule(value) { module = value; }, setResponseRoot(value) { responseRoot = value; },
    gateReferences() { gate = defer(); return gate; }
  };
}
let count = 0;
async function test(name, fn) { await fn(); console.log(`PASS ${name}`); count++; }

await test("Document is additive, keyboard-enabled, persisted, and lazy", async () => {
  assert.deepEqual([...html.matchAll(/data-blender-view-target="([^"]+)"/g)].map(match => match[1]), ["character", "builder", "document"]);
  assert.match(html, /id="blenderDocumentView"[^>]*role="tabpanel"[^>]*hidden/);
  const h = harness(); h.runtime.activeBlenderView = "character"; await h.api.loadBlenderDocuments(); assert.equal(h.calls.length, 0);
  h.runtime.activeBlenderView = "document"; h.setModule("workspace"); await h.api.loadBlenderDocuments(); assert.equal(h.calls.length, 0);
  h.runtime.runtimeActivityReady = false; h.setModule("blender"); h.api.setBlenderWorkspaceView("document", { animate: false });
  assert.equal(h.stored.get("view"), "document"); assert.deepEqual(h.tabs.map(tab => tab.tabIndex), [-1, -1, 0]);
  assert.deepEqual(h.views.map(view => view.hidden), [true, true, false]); assert.equal(h.calls.length, 0);
  assert.equal(h.api.normalizeBlenderWorkspaceView("builder"), "builder"); assert.equal(h.api.normalizeBlenderWorkspaceView("character"), "character");
  assert.equal(h.api.normalizeBlenderWorkspaceView("unknown"), "character");
  const keyboard = source.slice(source.indexOf('for (const button of document.querySelectorAll("[data-blender-view-target]"))'));
  assert.ok(keyboard.includes('"ArrowRight"') && keyboard.includes('"ArrowLeft"') && keyboard.includes('buttons.length'));
});

await test("missing root, unavailable folder, and empty manifest remain concise", async () => {
  const h = harness(); h.setState({ root: "", exists: false }); await h.api.loadBlenderDocuments();
  assert.deepEqual(h.calls, ["state"]); assert.match(h.node("Status").textContent, /Select a library/); assert.equal(h.node("Entries").children.length, 0);
  h.setState({ root: "D:/unavailable", exists: false }); await h.api.loadBlenderDocuments({ force: true }); assert.match(h.node("Status").textContent, /unavailable/);
  h.setState({ root: "D:/empty", exists: true }); h.setItems([]); await h.api.loadBlenderDocuments({ force: true }); assert.match(h.node("Status").textContent, /no Blender reference/);
});

await test("one bilingual card opens encoded reference links and reuses reader", async () => {
  const h = harness(); await h.api.loadBlenderDocuments();
  assert.equal(h.node("Entries").children.length, 1); const card = h.node("Entries").children[0];
  assert.equal(card.children[0].textContent, "Custom Nodes reference"); assert.equal(card.children[1].children.length, 0);
  const links = card.children[2].children; assert.deepEqual(links.map(link => link.textContent), ["中文", "English"]);
  const url = new URL(links[0].href); assert.equal(url.searchParams.get("reference"), "custom-nodes-reference"); assert.equal(url.searchParams.get("lang"), "zh-CN"); assert.equal(url.searchParams.get("root"), "D:/资料 & reading"); assert.equal(url.searchParams.has("id"), false);
  let prevented = 0; const click = { preventDefault() { prevented++; } };
  links[0].listeners.click(click); links[0].listeners.click(click); assert.equal(h.opened.length, 1); assert.equal(prevented, 2);
  assert.equal(h.opened[0].name, "codex-console-document-reader"); assert.ok(!h.calls.some(call => /inbox|read\?/.test(call)));
  h.runtime.language = "zh"; h.api.renderBlenderDocuments(); assert.equal(h.node("Entries").children[0].children[0].textContent, "自定义节点参考");
});

await test("missing translations are visibly unavailable and popup refusal has real-link fallback", async () => {
  const h = harness(); const items = fixture(); items[0].variants[0].available = false; h.setItems(items); await h.api.loadBlenderDocuments();
  const links = h.node("Entries").children[0].children[2].children; assert.equal(links[0].tagName, "SPAN"); assert.match(links[0].textContent, /unavailable/); assert.equal(links[1].tagName, "A");
  h.runtime.window.open = () => null; links[1].listeners.click({ preventDefault() {} }); assert.equal(h.node("Fallback").hidden, false); assert.equal(h.node("Fallback").href, links[1].href);
  assert.match(html, /id="blenderDocumentsFallback"[^>]*target="_blank"[^>]*rel="noopener"/);
  h.runtime.language = "zh"; h.setItems([{ ...items[0], variants: [items[0].variants[1]] }]); await h.api.loadBlenderDocuments({ force: true });
  assert.equal(h.node("Entries").children[0].children[0].textContent, "Custom Nodes reference");
});

await test("root mismatch and late responses never expose stale reading links", async () => {
  const h = harness(); await h.api.loadBlenderDocuments(); h.setResponseRoot("D:/different");
  assert.equal(await h.api.loadBlenderDocuments({ force: true }), false); assert.equal(h.node("Entries").children.length, 0); assert.match(h.node("Status").textContent, /library changed/);
  h.setResponseRoot(null); const gate = h.gateReferences(); const pending = h.api.loadBlenderDocuments({ force: true });
  await Promise.resolve(); h.runtime.documentLibrary.root = "D:/new-root"; gate.resolve(); assert.equal(await pending, false); assert.equal(h.runtime.blenderDocuments.loaded, false); assert.equal(h.node("Entries").children.length, 0);
  h.setState({ root: "D:/new-root", exists: true }); await h.api.loadBlenderDocuments({ force: true }); assert.equal(h.node("Entries").children.length, 1);
  const old = h.node("Entries").children[0].children[2].children[0]; h.runtime.documentLibrary.root = "D:/third-root"; old.listeners.click({ preventDefault() {} });
  assert.equal(h.opened.length, 0, "a known root change must refresh instead of opening the stale card");
});

await test("duplicate records and non-Blender records cannot become extra cards", async () => {
  const h = harness(); const items = fixture(); h.setItems([...items, ...items, { ...items[0], id: "other-module", module: "unity" }, { id: "bad", module: "blender", variants: null }]);
  await h.api.loadBlenderDocuments(); assert.equal(h.node("Entries").children.length, 1);
  assert.equal(h.api.blenderDocumentReaderUrl("ref", "invalid", "D:/docs"), null);
  assert.equal(h.api.blenderDocumentReaderUrl("ref", "en", ""), null);
});

console.log(`Blender document entry: ${count} isolated checks passed.`);
