#!/usr/bin/env node
// Run the actual resource UI against in-memory DOM/API fixtures, without a browser or network.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const html = readFileSync(new URL("../resources.html", import.meta.url), "utf8");
const source = readFileSync(new URL("../resources.js", import.meta.url), "utf8");
const flush = async () => { for (let i = 0; i < 6; i++) await new Promise(resolve => setImmediate(resolve)); };
const item = { id: "fixture-vfx", name: "测试 VFX", url: "https://example.com/vfx", previewUrl: "https://example.com/vfx.png", kind: "vfx", description: "来源展示图", license: "待核对", price: "免费", status: "candidate", provenance: [], notes: "" };
const state = (changes = {}) => ({ root: "D:\\资源库", revision: 17, items: [item], providers: [{ id: "sketchfab", name: "Sketchfab", kinds: ["model"], note: "搜索模型" }], ...changes });

function attributes(tag) {
  const values = new Map();
  for (const match of tag.matchAll(/([\w-]+)(?:="([^"]*)")?/g)) values.set(match[1], match[2] ?? "");
  return values;
}
class Element {
  constructor(tag = "div", attrs = new Map()) {
    this.tagName = tag.toUpperCase(); this.attributes = attrs; this.children = []; this.listeners = new Map();
    this.dataset = {}; this._text = ""; this.disabled = false; this.hidden = attrs.has("hidden"); this.value = attrs.get("value") || "";
    this.classList = { add() {}, remove() {} }; this.isConnected = true;
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  set innerHTML(_) { throw new Error("Resource/API values must never become HTML"); }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  removeAttribute(name) { this.attributes.delete(name); }
  append(...children) { for (const child of children) { child.parent = this; this.children.push(child); } }
  replaceChildren(...children) { this._text = ""; this.children = []; this.append(...children); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this); }
  querySelectorAll(selector) {
    assert.equal(selector, "[data-save]", "Extend this small fixture only for actual UI needs");
    const matches = [];
    const visit = element => { for (const child of element.children) { if (Object.hasOwn(child.dataset, "save")) matches.push(child); visit(child); } };
    visit(this); return matches;
  }
  addEventListener(name, callback) { const callbacks = this.listeners.get(name) || []; callbacks.push(callback); this.listeners.set(name, callbacks); }
  dispatch(name, event = {}) { if (name === "click" && this.disabled) return; for (const callback of this.listeners.get(name) || []) callback({ target: this, preventDefault() {}, ...event }); }
  focus() {}
}
function harness({ phone = false, stored = null } = {}) {
  const nodes = new Map(), calls = [], replies = new Map([["GET state", state()]]), storage = new Map();
  for (const match of html.matchAll(/<([a-z][a-z0-9]*)\b[^>]*\bid="([^"]+)"[^>]*>/gi)) nodes.set(match[2], new Element(match[1], attributes(match[0])));
  // Read real select defaults rather than duplicating the script's filter values.
  for (const match of html.matchAll(/<select\b[^>]*\bid="([^"]+)"[^>]*>([\s\S]*?)<\/select>/gi)) {
    const options = [...match[2].matchAll(/<option\b[^>]*>/gi)].map(value => attributes(value[0]));
    nodes.get(match[1]).value = (options.find(value => value.has("selected")) || options[0]).get("value") || "";
  }
  if (stored) storage.set(phone ? "console-resources-phone-view" : "console-resources-view", JSON.stringify(stored));
  const control = id => { assert.ok(nodes.has(id), `Missing actual HTML control: ${id}`); return nodes.get(id); };
  runInNewContext(source, {
    URL, URLSearchParams, console,
    document: { getElementById: control, createElement: tag => new Element(tag), body: new Element("body") },
    location: { search: phone ? "?phone=1" : "" },
    window: { scrollY: 0, addEventListener() {}, scrollTo() {} },
    sessionStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) },
    async fetch(url, options) {
      const parsed = new URL(url, "http://127.0.0.1:43123/resources.html");
      assert.equal(parsed.origin, "http://127.0.0.1:43123");
      assert.match(parsed.pathname, phone ? /^\/api\/phone\/resources\// : /^\/api\/resources\//);
      assert.equal(options.credentials, "same-origin"); assert.equal(options.mode, "same-origin"); assert.equal(options.cache, "no-store"); assert.equal(options.redirect, "error");
      if (phone) assert.equal(options.headers["X-Codex-Phone"], "1");
      const action = parsed.pathname.split("/").at(-1), method = options.method;
      calls.push({ action, method, params: parsed.searchParams, options: structuredClone(options), body: options.body ? JSON.parse(options.body) : null });
      if (method === "POST") assert.equal(options.headers["Content-Type"], "application/json");
      const key = `${method} ${action}`; assert.ok(replies.has(key), `Unexpected operation: ${key}`);
      const configured = replies.get(key), reply = await (typeof configured === "function" ? configured() : configured);
      return { ok: reply.httpError !== true, async json() { return structuredClone(reply); } };
    }
  }, { filename: "resources.js" });
  return { calls, control, respond: (key, value) => replies.set(key, value) };
}

let passed = 0;
async function test(name, body) { await body(); passed++; console.log(`PASS ${name}`); }

await test("opening the real page maps all filters to the state API's empty strings and never searches", async () => {
  const h = harness(); await flush();
  assert.deepEqual(h.calls.map(call => [call.method, call.action]), [["GET", "state"]]);
  assert.equal(h.calls[0].params.get("kind"), ""); assert.equal(h.calls[0].params.get("status"), "");
  assert.equal(h.calls[0].params.has("expectedRoot"), false);
  assert.equal(h.control("kind").value, "all"); assert.equal(h.control("status").value, "all");
  assert.equal(h.control("resourceGrid").children.length, 1); assert.equal(h.control("resultCount").textContent, "1 项");
  assert.equal(h.control("operationStatus").dataset.error, "false");
});

await test("restored all filters remain UI defaults and long old queries are capped to the backend limit", async () => {
  const h = harness({ stored: { q: "树".repeat(150), kind: "all", status: "all" } }); await flush();
  assert.equal(h.calls[0].params.get("q"), "树".repeat(120));
  assert.equal(h.calls[0].params.get("kind"), ""); assert.equal(h.calls[0].params.get("status"), "");
  assert.equal(h.control("query").attributes.get("maxlength"), "120");
});

await test("a backend Chinese error is shown as text and does not replace existing cards or query", async () => {
  const h = harness(); await flush(); const previousCard = h.control("resourceGrid").children[0];
  const message = "来源暂时无法读取 <span>原记录保留</span>";
  h.respond("GET state", { httpError: true, error: message }); h.control("query").value = "斩击";
  h.control("searchForm").dispatch("submit"); await flush();
  assert.equal(h.control("operationStatus").textContent, message); assert.equal(h.control("operationStatus").dataset.error, "true");
  assert.equal(h.control("resourceGrid").children[0], previousCard); assert.equal(h.control("query").value, "斩击");
  assert.equal(h.calls[1].params.get("expectedRoot"), "D:\\资源库");
});

await test("choosing a candidate posts its actual root and revision once, then reads the saved receipt", async () => {
  const h = harness(); await flush(); const saved = { ...item, status: "saved" };
  h.respond("POST save", { ...state({ revision: 18, items: [saved] }), item: saved }); h.respond("GET state", state({ revision: 18, items: [saved] }));
  const save = h.control("resourceGrid").querySelectorAll("[data-save]").find(button => button.dataset.save === "saved");
  save.dispatch("click"); save.dispatch("click"); await flush();
  const posts = h.calls.filter(call => call.method === "POST"); assert.equal(posts.length, 1);
  assert.equal(posts[0].action, "save");
  assert.deepEqual(posts[0].body, { expectedRoot: "D:\\资源库", expectedRevision: 17, id: "fixture-vfx", status: "saved" });
  assert.deepEqual(h.calls.map(call => [call.method, call.action]), [["GET", "state"], ["POST", "save"], ["GET", "state"]], h.control("operationStatus").textContent);
  assert.match(h.control("operationStatus").textContent, /已收藏/);
  assert.equal(h.control("resourceGrid").querySelectorAll("[data-save]").find(button => button.dataset.save === "saved").disabled, true);
});

await test("revision rejection requires a fresh read and never retries or claims a saved selection", async () => {
  const h = harness(); await flush();
  h.respond("POST save", { httpError: true, code: "revision_conflict", error: "资源已更新" });
  h.control("resourceGrid").querySelectorAll("[data-save]").find(button => button.dataset.save === "planned").dispatch("click"); await flush();
  assert.match(h.control("operationStatus").textContent, /查已收集.*最新记录/);
  assert.equal(h.calls.length, 2); assert.equal(h.control("operationStatus").dataset.error, "true");
  assert.equal(h.control("resourceGrid").querySelectorAll("[data-save]").find(button => button.dataset.save === "planned").dataset.active, "false");
});

await test("phone mode stays on the phone API with its required same-origin header and return location", async () => {
  const h = harness({ phone: true }); await flush();
  assert.equal(h.calls[0].options.headers["X-Codex-Phone"], "1");
  assert.equal(h.control("backLink").href, "/mobile.html?tab=documents"); assert.equal(h.calls.length, 1);
});

console.log(`${passed} resource UI checks passed.`);
