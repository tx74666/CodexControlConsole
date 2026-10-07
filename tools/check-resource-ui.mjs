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
  removeAttribute(name) { this.attributes.delete(name); if (name === "href") this.href = ""; }
  append(...children) { for (const child of children) { child.parent = this; this.children.push(child); } }
  replaceChildren(...children) { this._text = ""; this.children = []; this.append(...children); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this); }
  querySelectorAll(selector) {
    const attribute = /^\[data-(save|provider)\]$/.exec(selector)?.[1];
    assert.ok(attribute, "Extend this small fixture only for actual UI needs");
    const matches = [];
    const visit = element => { for (const child of element.children) { if (Object.hasOwn(child.dataset, attribute)) matches.push(child); visit(child); } };
    visit(this); return matches;
  }
  addEventListener(name, callback) { const callbacks = this.listeners.get(name) || []; callbacks.push(callback); this.listeners.set(name, callbacks); }
  dispatch(name, event = {}) { if (name === "click" && this.disabled) return; for (const callback of this.listeners.get(name) || []) callback({ target: this, preventDefault() {}, ...event }); }
  focus() {}
  get parentElement() { return this.parent; }
}
function harness({ phone = false, stored = null, initial = state() } = {}) {
  const nodes = new Map(), calls = [], navigations = [], replies = new Map([["GET state", initial]]), storage = new Map();
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
    window: { scrollY: 0, addEventListener() {}, scrollTo() {}, open(...args) { navigations.push(args); throw new Error("Websites must be opened only through human-operated links"); } },
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
  return { calls, navigations, control, storage, respond: (key, value) => replies.set(key, value) };
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

await test("a new server catalog renders arbitrary APIs, migrates the old single choice, and accepts an older single-source receipt", async () => {
  const providers = [{ id: "new-catalog-source", name: "新来源 <span>可预览</span>", mode: "api", kinds: ["model", "texture"], defaultKind: "texture", note: "已接通图片预览" }];
  const h = harness({ initial: state({ providers }), stored: { provider: "new-catalog-source", q: "石头", kind: "all", status: "all" } }); await flush();
  const checkboxes = h.control("apiSourceList").querySelectorAll("[data-provider]").filter(element => element.tagName === "INPUT");
  assert.equal(checkboxes.length, 1); assert.equal(checkboxes[0].value, "new-catalog-source"); assert.equal(checkboxes[0].checked, true);
  assert.match(h.control("apiSourceList").textContent, /新来源 <span>可预览<\/span>/);
  assert.match(h.control("resultNote").textContent, /候选 1.*已收藏 0.*候选尚未收藏/);
  h.respond("POST search", { ...state({ providers, revision: 18 }), searchQuery: "rock", cached: false });
  h.control("onlineSearch").dispatch("click"); await flush();
  const search = h.calls.find(call => call.action === "search");
  assert.deepEqual(search.body.providers, ["new-catalog-source"]); assert.equal(search.body.kind, "all"); assert.equal(search.body.count, 12); assert.equal(search.body.q, "石头");
  assert.match(h.control("resultNote").textContent, /实际搜索词：rock/);
  assert.deepEqual(JSON.parse(h.storage.get("console-resources-view")).selectedProviders, ["new-catalog-source"]);
  assert.match(h.control("providerNote").textContent, /全部类型按各站默认分类检索/);
});

await test("external-only selection prepares encoded human-operated links without POST or changing cards", async () => {
  const providers = [{ id: "external-fixture", name: "itch.io", mode: "external", kinds: ["model", "other"], defaultKind: "model", note: "可把选中的资源网址添加回来。", searchUrlTemplate: "https://itch.io/search?q={query}&facets=c.2" }];
  const h = harness({ initial: state({ providers }), stored: { provider: "external-fixture", q: "stone & 草地" } }); await flush();
  const card = h.control("resourceGrid").children[0];
  h.control("onlineSearch").dispatch("click"); await flush();
  const link = h.control("browseLinks").children[0];
  assert.equal(h.control("browsePanel").hidden, false);
  assert.equal(h.control("browsePanel").open, true);
  assert.equal(link.href, `https://itch.io/search?q=${encodeURIComponent("stone & 草地")}&facets=c.2`);
  assert.equal(link.target, "_blank"); assert.match(link.rel, /noopener/); assert.match(link.rel, /noreferrer/);
  assert.match(h.control("browseNote").textContent, /尚未在 Console 内检索/);
  link.dispatch("click"); await flush();
  assert.equal(h.calls.length, 1); assert.equal(h.control("resourceGrid").children[0], card);
  assert.equal(h.navigations.length, 0);
  h.control("query").value = "新词"; h.control("query").dispatch("input");
  assert.equal(h.control("browsePanel").hidden, true);
  h.control("onlineSearch").dispatch("click"); await flush();
  assert.equal(h.control("browseLinks").children[0].href, `https://itch.io/search?q=${encodeURIComponent("新词")}&facets=c.2`);
  assert.equal(h.calls.length, 1);
});

await test("unapproved external templates cannot become links or fall through to the local search API", async () => {
  for (const searchUrlTemplate of ["https://unknown.example/search?q={query}", "javascript:alert('{query}')", "https://itch.io/search?q={query}&next={query}"]) {
    const providers = [{ id: "external-fixture", name: "外部来源", mode: "external", kinds: ["model"], searchUrlTemplate }];
    const h = harness({ initial: state({ providers }), stored: { q: "tree" } }); await flush();
    h.control("onlineSearch").dispatch("click"); await flush();
    assert.equal(h.control("browseLinks").children.length, 0);
    assert.equal(h.calls.length, 1); assert.equal(h.control("operationStatus").dataset.error, "true");
  }
});

const selectionCatalog = [
  { id: "model-api", name: "模型来源", mode: "api", group: "catalog", core: true, kinds: ["model"], defaultKind: "model" },
  { id: "texture-api", name: "贴图来源", mode: "api", group: "catalog", core: false, kinds: ["texture"], defaultKind: "texture" },
  { id: "itch", name: "itch.io", mode: "external", group: "catalog", core: true, kinds: ["model", "vfx", "other"], searchUrlTemplate: "https://itch.io/search?q={query}&facets=c.2" },
  { id: "fab", name: "Fab", mode: "external", group: "catalog", core: false, kinds: ["model"], searchUrlTemplate: "https://www.fab.com/search?q={query}" },
  { id: "bing", name: "Bing", mode: "external", group: "web", core: true, kinds: ["other"], searchUrlTemplate: "https://www.bing.com/search?q={query}%20game%20assets" }
];
const chosen = h => [...JSON.parse(h.storage.get("console-resources-view")).selectedProviders].sort();

await test("core and wide presets, select all, and checkbox changes are local selections; web discovery stays independent", async () => {
  const h = harness({ initial: state({ providers: selectionCatalog }), stored: { q: "tree" } }); await flush();
  h.control("corePreset").dispatch("click"); assert.deepEqual(chosen(h), ["itch", "model-api"]);
  assert.match(h.control("sourceCounts").textContent, /1 站可直接预览 · 1 站打开浏览/);
  h.control("widePreset").dispatch("click"); assert.deepEqual(chosen(h), ["fab", "itch", "model-api", "texture-api"]);
  h.control("clearSources").dispatch("click"); assert.deepEqual(chosen(h), []); assert.equal(h.control("onlineSearch").disabled, true);
  h.control("selectAllSources").dispatch("click"); assert.deepEqual(chosen(h), ["fab", "itch", "model-api", "texture-api"]);
  const texture = h.control("apiSourceList").querySelectorAll("[data-provider]").find(element => element.tagName === "INPUT" && element.value === "texture-api");
  texture.checked = false; texture.dispatch("change"); assert.deepEqual(chosen(h), ["fab", "itch", "model-api"]);
  assert.equal(h.calls.length, 1); assert.equal(h.control("webDiscoveryLinks").children.length, 1);
});

await test("batch search posts only compatible APIs once, provides external links, and discloses partial source failures", async () => {
  const h = harness({ initial: state({ providers: selectionCatalog }), stored: { q: "tree", selectedProviders: ["model-api", "texture-api", "itch", "fab"], resultLimit: "24" } }); await flush();
  h.respond("POST search", { ...state({ providers: selectionCatalog, revision: 18 }), batch: true, searchQuery: "tree", sources: [
    { provider: "model-api", name: "模型来源", kind: "model", status: "ok", count: 1, skippedCount: 2, warnings: ["两个条目无效"] },
    { provider: "texture-api", name: "贴图来源", kind: "texture", status: "error", error: "来源暂不可用 <script>" }
  ] });
  h.control("onlineSearch").dispatch("click"); h.control("onlineSearch").dispatch("click"); await flush();
  const posts = h.calls.filter(call => call.method === "POST"); assert.equal(posts.length, 1);
  assert.deepEqual(posts[0].body, { expectedRoot: "D:\\资源库", q: "tree", providers: ["model-api", "texture-api"], kind: "all", count: 24, refresh: false });
  assert.equal(h.control("browseLinks").children.length, 2); assert.match(h.control("operationStatus").textContent, /找到 1 项.*1 站未完成.*另有 2 项/);
  assert.equal(h.control("browsePanel").open, false);
  assert.equal(h.navigations.length, 0);
  assert.match(h.control("sourceResultsList").textContent, /来源暂不可用 <script>/); assert.match(h.control("sourceResultsList").textContent, /模型 · 1 项/);
  assert.match(h.control("resultWarnings").textContent, /贴图来源/);
});

await test("unsupported source kinds are never sent, and an all-source failure keeps the existing cards", async () => {
  const h = harness({ initial: state({ providers: selectionCatalog }), stored: { q: "tree", kind: "model", selectedProviders: ["model-api", "texture-api", "itch"] } }); await flush();
  const card = h.control("resourceGrid").children[0];
  h.respond("POST search", { ...state({ providers: selectionCatalog, items: [] }), batch: true, sources: [{ provider: "model-api", name: "模型来源", kind: "model", status: "error", error: "来源未响应" }] });
  h.control("onlineSearch").dispatch("click"); await flush();
  assert.deepEqual(h.calls.find(call => call.action === "search").body.providers, ["model-api"]);
  assert.equal(h.control("resourceGrid").children[0], card); assert.equal(h.control("operationStatus").dataset.error, "true");
  assert.match(h.control("providerNote").textContent, /当前分类不支持 1 站/); assert.match(h.control("sourceResultsList").textContent, /来源未响应/);
});

await test("web discovery links encode terms and never open windows automatically or become batch API selections", async () => {
  const h = harness({ initial: state({ providers: selectionCatalog }), stored: { q: "车 & 草地", selectedProviders: [] } }); await flush();
  const link = h.control("webDiscoveryLinks").children[0];
  assert.equal(link.href, `https://www.bing.com/search?q=${encodeURIComponent("车 & 草地")}%20game%20assets`);
  link.dispatch("click"); await flush(); assert.equal(h.calls.length, 1);
  const reload = harness({ initial: state({ providers: selectionCatalog }), stored: JSON.parse(h.storage.get("console-resources-view")) }); await flush();
  assert.equal(reload.control("onlineSearch").disabled, true); assert.deepEqual(chosen(reload), []);
});

await test("all pinned official browsing destinations in the server registry remain usable through human-operated links", async () => {
  const registry = readFileSync(new URL("../resource_sources.py", import.meta.url), "utf8");
  const destinations = [...registry.matchAll(/["'](searchUrlTemplate|browseUrl)["']\s*:\s*(["'])([^"']+)\2/g)].map((match, index) => ({ id: `registered-${index}`, name: `已核实网站 ${index}`, mode: "external", group: "catalog", core: true, kinds: ["other"], [match[1]]: match[3] }));
  assert.ok(destinations.length >= 5, "Use the checked-in official source registry as the API boundary fixture");
  const h = harness({ initial: state({ providers: destinations }), stored: { q: "树 & 模型" } }); await flush();
  h.control("onlineSearch").dispatch("click"); await flush();
  assert.equal(h.control("browseLinks").children.length, destinations.length, "A registered official link must also pass the UI's independent URL allowlist");
  for (const link of h.control("browseLinks").children) { const url = new URL(link.href); assert.equal(url.protocol, "https:"); assert.equal(url.username, ""); assert.equal(url.password, ""); assert.equal(link.target, "_blank"); }
  assert.equal(h.calls.length, 1); assert.equal(h.navigations.length, 0);
});

await test("browse destinations reject domain lookalikes, credentials, changed paths, and arbitrary servers", async () => {
  for (const browseUrl of ["https://quaternius.com.evil.test/", "https://user:password@quaternius.com/", "https://quaternius.com/extra", "https://unknown.example/"]) {
    const providers = [{ id: "unsafe-browse", name: "未核实目录", mode: "external", group: "catalog", core: true, kinds: ["model"], browseUrl }];
    const h = harness({ initial: state({ providers }), stored: { q: "tree" } }); await flush(); h.control("onlineSearch").dispatch("click"); await flush();
    assert.equal(h.control("browseLinks").children.length, 0); assert.equal(h.calls.length, 1); assert.equal(h.navigations.length, 0);
  }
});

await test("partial results and cached repeats disclose skipped records, while a full error preserves those cards and notices", async () => {
  const h = harness(); await flush(); h.control("query").value = "tree";
  const partial = { ...state({ revision: 18 }), skippedCount: 2, warnings: ["跳过了 <span>无效身份</span>", "提示".repeat(200), "第三条", "第四条不显示"], cached: false };
  h.respond("POST search", partial); h.control("onlineSearch").dispatch("click"); await flush();
  assert.match(h.control("operationStatus").textContent, /找到 1 项.*另有 2 项因资料无效未显示/);
  assert.equal(h.control("resultWarnings").hidden, false); assert.match(h.control("resultWarnings").textContent, /<span>无效身份<\/span>/);
  assert.doesNotMatch(h.control("resultWarnings").textContent, /第四条/); assert.ok(h.control("resultWarnings").textContent.length < 580);
  h.respond("POST search", { ...partial, cached: true }); h.control("onlineSearch").dispatch("click"); await flush();
  assert.match(h.control("operationStatus").textContent, /已复用.*1 项.*另有 2 项因资料无效未显示/);
  const card = h.control("resourceGrid").children[0], warning = h.control("resultWarnings").textContent;
  h.respond("POST search", { httpError: true, error: "这次来源全部资料无效，结果未保存。" }); h.control("refreshSearch").dispatch("click"); await flush();
  assert.equal(h.control("operationStatus").textContent, "这次来源全部资料无效，结果未保存。");
  assert.equal(h.control("resourceGrid").children[0], card); assert.equal(h.control("resultWarnings").textContent, warning);
});

console.log(`${passed} resource UI checks passed.`);
