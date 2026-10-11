#!/usr/bin/env node
// Deterministic VM/DOM fixtures. No live HTTP, Git, browser, source repository or user-data access.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { randomUUID } from "node:crypto";
const source = readFileSync(new URL("../console-repository-publish.js", import.meta.url), "utf8");
const css = readFileSync(new URL("../console-repository-publish.css", import.meta.url), "utf8");
const BASE = "/api/console/repository-publish";
const KEY = "console.repositoryPublish.pending.v1";
const settle = async () => { for (let i = 0; i < 15; i++) await new Promise(resolve => setImmediate(resolve)); };
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
const response = value => ({ ok: true, status: 200, json: async () => structuredClone(value) });
const repository = (extra = {}) => ({ id: "repository-001", path: "D:/Projects/Music", repositoryUrl: "https://github.com/example/Music", remote: "origin", branch: "feature/music", enabled: true, syncFiles: [], versionSources: [], exclude: [], ...extra });
const settings = repos => ({ repositories: repos || [repository()], naming: { preset: "version", fallbackTitle: "更新进度 {datetime}", subtitle: "", notes: "", includeSummary: true } });
const operation = (requestId, status = "working", repositories = []) => ({ requestId, status, repositories, message: "fixture" });
function harness(options = {}) {
  const timers = new Map(), calls = [], observers = [], listeners = new Map(), storage = options.storage || new Map();
  let document, hook = options.hook, timerId = 0;
  class Element {
    constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.parentElement = null; this.listeners = new Map(); this.attributes = {}; this.dataset = {}; this.hidden = false; this.disabled = false; this.open = false; this.checked = false; this.value = ""; this.textContent = ""; this.className = ""; }
    append(...items) { for (const item of items) { item.parentElement = this; this.children.push(item); } }
    replaceChildren(...items) { for (const old of this.children) old.parentElement = null; this.children = []; this.append(...items); }
    remove() { if (this.parentElement) { const parent = this.parentElement; parent.children.splice(parent.children.indexOf(this), 1); this.parentElement = null; } }
    contains(item) { return item === this || this.children.some(child => child.contains(item)); }
    closest(selector) { for (let item = this; item; item = item.parentElement) if (selector === '[data-module-panel="workspace"]' && item.attributes["data-module-panel"] === "workspace") return item; return null; }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    getAttribute(key) { return this.attributes[key] ?? null; }
    setCustomValidity(value) { this.validationMessage = value; }
    addEventListener(type, handler) { if (!this.listeners.has(type)) this.listeners.set(type, []); this.listeners.get(type).push(handler); }
    dispatch(type) { if (this.disabled && ["click", "change"].includes(type)) return; for (const handler of this.listeners.get(type) || []) handler({ target: this, preventDefault() {} }); }
    click() { this.dispatch("click"); }
    showModal() { this.open = true; }
    close() { this.open = false; this.dispatch("close"); }
    focus() { document.activeElement = this; }
    set innerHTML(_) { throw new Error("Unsafe HTML assignment"); }
  }
  const root = new Element("html"), panel = new Element("section"), host = new Element("div");
  root.lang = options.lang || "zh-CN"; panel.setAttribute("data-module-panel", options.module || "workspace"); host.id = "consoleRepositoryPublishHost"; root.append(panel); panel.append(host);
  const all = (parent = root) => [parent, ...parent.children.flatMap(item => all(item))];
  document = { documentElement: root, readyState: options.loading ? "loading" : "complete", activeElement: null, createElement: tag => new Element(tag), getElementById: id => all().find(item => item.id === id), addEventListener(type, handler) { if (!listeners.has(type)) listeners.set(type, []); listeners.get(type).push(handler); } };
  const stored = options.storageUnavailable ? { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }, removeItem() { throw new Error("blocked"); } } : { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) };
  const snapshot = { allowed: true, busy: false, settings: settings(), operation: null, ...(options.snapshot || {}) };
  const window = { crypto: { randomUUID }, localStorage: stored, sessionStorage: stored, setTimeout(fn, delay) { const id = ++timerId; timers.set(id, { fn, delay }); return id; }, clearTimeout(id) { timers.delete(id); }, addEventListener() {}, removeEventListener() {}, async fetch(url, init) {
    const call = { url, method: init.method, body: init.body ? JSON.parse(init.body) : null, options: init }; calls.push(call);
    if (hook) { const value = await hook(call); if (value !== undefined) return value; }
    if (url === BASE && init.method === "GET") return response(snapshot);
    if (url === BASE + "/config") { snapshot.settings = structuredClone(call.body.settings); return response({ settings: snapshot.settings }); }
    if (url === BASE + "/preview") return response({ previews: [{ repoId: "repository-001", title: "Music v2.3", body: "2 files", versions: [{ name: "Music", version: "2.3" }] }] });
    if (url === BASE + "/run") { snapshot.operation = operation(call.body.requestId, "queued"); return response(snapshot.operation); }
    if (url.startsWith(BASE + "/operation?")) return response(snapshot.operation || null);
    throw new Error("Unexpected fixture request: " + url);
  } };
  class MutationObserver { constructor(callback) { this.callback = callback; observers.push(this); } observe() {} disconnect() {} }
  runInNewContext(source, { window, document, MutationObserver, WeakMap, Map, Set, Uint8Array, AbortController, console });
  const byClass = name => all().find(item => item.className.split(" ").includes(name));
  const fields = name => all().filter(item => item.dataset.field === name);
  const button = label => all().find(item => item.tagName === "BUTTON" && item.textContent === label);
  return { window, document, snapshot, host, panel, all, calls, storage, timers, byClass, fields, button, hook(value) { hook = value; }, get api() { return window.ConsoleRepositoryPublish.mount({ host }); }, posts(path) { return calls.filter(call => call.method === "POST" && (!path || call.url === BASE + path)); }, async ready() { if (options.loading) for (const listener of listeners.get("DOMContentLoaded") || []) listener(); await settle(); }, async open() { button(root.lang.startsWith("zh") ? "配置" : "Configure").click(); await settle(); }, async change(name, value, index = 0) { const input = fields(name)[index]; assert.ok(input, name); if (input.type === "checkbox") input.checked = value; else input.value = value; input.dispatch("change"); await settle(); }, locale(value) { root.lang = value; for (const observer of observers) observer.callback([]); }, async poll() { const entry = [...timers.entries()].find(([, item]) => item.delay >= 1200 && item.delay <= 10000); assert.ok(entry, "expected original-request polling timer"); timers.delete(entry[0]); entry[1].fn(); await settle(); } };
}
let count = 0;
async function test(name, fn) { await fn(); count++; console.log("PASS " + name); }
await test("only Console workspace may mount, with no other-module request", async () => {
  const h = harness({ module: "music" }); await h.ready(); assert.equal(h.api, null); assert.equal(h.host.children.length, 0); assert.equal(h.calls.length, 0);
});
await test("strict allowed gate keeps missing or false authorization hidden", async () => {
  for (const allowed of [false, undefined]) { const h = harness({ snapshot: { allowed } }); await h.ready(); assert.equal(h.byClass("repository-publish-bar").hidden, true); assert.equal(h.byClass("repository-publish-primary").disabled, true); }
});
await test("DOMContentLoaded auto-mount is idempotent and idle performs one read", async () => {
  const h = harness({ loading: true }); assert.equal(h.host.children.length, 0); await h.ready(); const api = h.api; assert.equal(h.api, api); assert.equal(h.host.children.length, 2); assert.equal(h.calls.length, 1); assert.equal(h.posts().length, 0);
});
await test("closed default is three compact controls with no resident form", async () => {
  const h = harness(); await h.ready(); const bar = h.byClass("repository-publish-bar"); assert.equal(bar.children.length, 3); assert.equal(h.byClass("repository-publish-dialog").open, false); assert.equal(h.fields("path").length, 0); assert.equal(h.byClass("repository-publish-primary").disabled, false); assert.match(css, /\.repository-publish-bar\[hidden\]/);
  assert.ok(bar.children.slice(0, 2).every(item => item.getAttribute("data-console-management") === ""));
});
await test("initial binding warnings stay collapsed in config with safe supported text and snapshot wording", async () => {
  const hostile = '<img src=x onerror="evil()">', h = harness({ snapshot: { warnings: [
    "legacy_initial_note", { code: "configured_repository_path_missing", path: "D:/Projects/MyWeb", source: "environment" },
    { code: hostile, path: "D:/Projects/Other", source: "https://secret-token@example.invalid/private" },
    { repositoryUrl: "https://another-secret@example.invalid/private", unsupported: hostile }, null, 17
  ], warningsSource: "initial_discovery" } });
  await h.ready(); const bar = h.byClass("repository-publish-bar"), notes = h.byClass("repository-publish-warnings");
  assert.equal(bar.children.length, 3); assert.equal(h.byClass("repository-publish-dialog").open, false);
  assert.equal(h.fields("path").length, 0); assert.equal(notes.children[2].children.length, 0); assert.equal(notes.hidden, true);
  await h.open(); assert.equal(notes.open, false); assert.equal(notes.hidden, false); assert.equal(notes.children[0].textContent, "初次绑定提示");
  assert.equal(notes.children[2].children.length, 3); const labels = h.all(notes).map(item => item.textContent).join(" ");
  assert.match(labels, /legacy_initial_note/); assert.match(labels, /configured_repository_path_missing.*D:\/Projects\/MyWeb.*environment/);
  assert.ok(labels.includes(hostile)); assert.match(labels, /初次发现时的快照.*不代表当前仍有异常/);
  assert.doesNotMatch(labels, /secret-token|another-secret|example\.invalid/); assert.equal(h.all(notes).some(item => item.tagName === "IMG" || item.tagName === "A"), false);
  h.locale("en"); assert.equal(notes.children[0].textContent, "Initial binding notes"); assert.match(notes.children[1].textContent, /initial discovery snapshot.*does not describe current issues/);
  h.button("Close").click(); assert.equal(h.byClass("repository-publish-dialog").open, false); assert.equal(bar.children.length, 3); assert.equal(h.posts().length, 0);
});
await test("configuration opens on demand and close restores compact state", async () => {
  const h = harness(); await h.ready(); await h.open(); assert.equal(h.fields("path")[0].value, "D:/Projects/Music"); assert.equal(h.fields("branch")[0].value, "feature/music"); h.button("关闭").click(); assert.equal(h.byClass("repository-publish-dialog").open, false); assert.equal(h.byClass("repository-publish-config").getAttribute("aria-expanded"), "false");
});
await test("change autosaves exactly the settings schema without prompting", async () => {
  const h = harness(); await h.ready(); await h.open(); await h.change("notes", "optional release note"); assert.equal(h.posts("/config").length, 1); const payload = h.posts("/config")[0].body; assert.deepEqual(Object.keys(payload), ["settings"]); assert.equal(payload.settings.naming.notes, "optional release note"); assert.equal(payload.settings.repositories[0].branch, "feature/music"); assert.equal(h.posts("/run").length, 0);
});
await test("autosaves serialize and preserve a newer edit over an older response", async () => {
  const pending = deferred(); let writes = 0; const h = harness({ hook(call) { if (call.url === BASE + "/config" && ++writes === 1) return pending.promise; } }); await h.ready(); await h.open(); await h.change("subtitle", "one"); await h.change("notes", "two"); assert.equal(h.posts("/config").length, 1); assert.equal(h.byClass("repository-publish-primary").disabled, true); pending.resolve(response({ settings: h.posts("/config")[0].body.settings })); await settle(); assert.equal(h.posts("/config").length, 2); assert.equal(h.posts("/config")[1].body.settings.naming.subtitle, "one"); assert.equal(h.posts("/config")[1].body.settings.naming.notes, "two");
});
await test("failed save remains visible after close and reopening preserves draft", async () => {
  const h = harness({ hook(call) { if (call.url === BASE + "/config") throw new Error("offline"); } }); await h.ready(); await h.open(); await h.change("notes", "unsaved draft"); h.button("关闭").click(); assert.match(h.byClass("repository-publish-status").textContent, /未保存/); await h.open(); assert.equal(h.fields("notes")[0].value, "unsaved draft"); assert.equal(h.byClass("repository-publish-primary").disabled, true);
});
await test("add starts disabled with empty actual-branch binding and disable autosaves", async () => {
  const h = harness(); await h.ready(); await h.open(); h.button("添加仓库").click(); await settle(); const added = h.posts("/config").at(-1).body.settings.repositories[1]; assert.equal(added.enabled, false); assert.equal(added.branch, ""); assert.equal(h.fields("branch")[1].placeholder, "当前分支（读取后保存）"); await h.change("enabled", false); assert.equal(h.posts("/config").at(-1).body.settings.repositories[0].enabled, false); assert.equal(h.byClass("repository-publish-primary").disabled, true);
});
await test("duplicate enabled paths cannot save or run", async () => {
  const h = harness({ snapshot: { settings: settings([repository(), repository({ id: "repository-002", path: "D:/Projects/Other" })]) } }); await h.ready(); await h.open(); await h.change("path", "d:\\projects\\music\\", 1); assert.equal(h.posts("/config").length, 0); assert.match(h.byClass("repository-publish-status").textContent, /重复/); assert.equal(h.byClass("repository-publish-primary").disabled, true);
});
await test("malformed sync rule retains draft and does not submit old parsed data", async () => {
  const h = harness(); await h.ready(); await h.open(); await h.change("sync", "unpaired rule"); assert.equal(h.posts("/config").length, 0); h.button("关闭").click(); await h.open(); assert.equal(h.fields("sync")[0].value, "unpaired rule"); await h.change("sync", "D:/Sources/source.txt -> target.txt"); assert.deepEqual(h.posts("/config")[0].body.settings.repositories[0].syncFiles, [{ source: "D:/Sources/source.txt", target: "target.txt" }]);
});
await test("double click submits once and persists identity before network", async () => {
  const pending = deferred(); const h = harness({ hook(call) { if (call.url === BASE + "/run") return pending.promise; } }); await h.ready(); const run = h.byClass("repository-publish-primary"); run.click(); run.click(); await settle(); assert.equal(h.posts("/run").length, 1); assert.equal(h.storage.get(KEY), h.posts("/run")[0].body.requestId); assert.deepEqual(h.posts("/run")[0].body.repoIds, ["repository-001"]); pending.resolve(response(operation(h.storage.get(KEY)))); await settle(); assert.equal(h.posts("/run").length, 1);
});
await test("uncertain network and reload read original identity without a second POST", async () => {
  const storage = new Map(); const first = harness({ storage, hook(call) { if (call.url === BASE + "/run") throw new Error("unknown delivery"); } }); await first.ready(); first.byClass("repository-publish-primary").click(); await settle(); const id = storage.get(KEY); await first.poll(); assert.ok(first.calls.some(call => call.url.endsWith("requestId=" + id))); assert.equal(first.posts("/run").length, 1);
  const reload = harness({ storage }); await reload.ready(); assert.equal(reload.byClass("repository-publish-primary").disabled, true); await reload.poll(); assert.ok(reload.calls.some(call => call.url.endsWith("requestId=" + id))); assert.equal(reload.posts().length, 0); assert.equal(storage.get(KEY), id);
});
await test("different receipt cannot release unresolved original request", async () => {
  const id = randomUUID(); const storage = new Map([[KEY, id]]); const h = harness({ storage, snapshot: { operation: operation(randomUUID(), "complete") } }); await h.ready(); await h.poll(); assert.equal(h.storage.get(KEY), id); assert.equal(h.byClass("repository-publish-primary").disabled, true); assert.equal(h.posts().length, 0);
});
await test("terminal receipt exposes per-repo continuation using one new filtered run", async () => {
  const id = randomUUID(); const h = harness({ storage: new Map([[KEY, id]]), snapshot: { operation: operation(id, "complete", [{ repoId: "repository-001", name: "Music", status: "push_failed", phase: "pushing", message: "original commit retained", commitSha: "a".repeat(40), title: "v2", body: "fixture" }]) } }); await h.ready(); assert.equal(h.storage.has(KEY), false); await h.open(); const retry = h.button("继续此仓库"); assert.ok(retry); retry.click(); await settle(); assert.deepEqual(h.posts("/run")[0].body.repoIds, ["repository-001"]); assert.notEqual(h.posts("/run")[0].body.requestId, id);
});
await test("preview renders actual title/body without sync or commit request", async () => {
  const h = harness(); await h.ready(); await h.open(); h.button("预览标题与改动").click(); await settle(); assert.equal(h.posts("/preview").length, 1); assert.equal(h.posts("/run").length, 0); assert.equal(h.posts("/config").length, 0); const text = h.all().map(item => item.textContent).join(" "); assert.match(text, /Music v2.3/); assert.match(text, /2 files/);
});
await test("language follows app lang mutation without changing drafts or sending", async () => {
  const h = harness(); await h.ready(); await h.open(); const before = h.calls.length; h.locale("en"); assert.equal(h.byClass("repository-publish-primary").textContent, "Submit & push"); assert.equal(h.fields("branch")[0].placeholder, "Current branch (read and save)"); assert.equal(h.fields("branch")[0].value, "feature/music"); assert.equal(h.calls.length, before); assert.ok(h.button("Configure"));
});
await test("XSS values remain text, request credentials and redirects stay local", async () => {
  const id = randomUUID(), hostile = '<img src=x onerror="fetch(\"evil\")">'; const h = harness({ snapshot: { operation: operation(id, "complete", [{ repoId: "repository-001", name: hostile, status: "success", title: hostile, body: hostile }]) } }); await h.ready(); await h.open(); assert.ok(h.all().some(item => item.textContent.includes(hostile))); assert.equal(h.all().some(item => item.tagName === "IMG"), false); for (const call of h.calls) { assert.equal(call.options.credentials, "same-origin"); assert.equal(call.options.redirect, "error"); assert.equal(call.options.mode, "same-origin"); } assert.doesNotMatch(source, /\b(?:innerHTML|eval|confirm)\s*[=(]/);
});
await test("reload guard protects unsaved draft while a persisted receipt may resume", async () => {
  const h = harness({ hook(call) { if (call.url === BASE + "/config") throw new Error("save failed"); } }); await h.ready(); assert.equal(h.window.ConsoleRepositoryPublish.hasDraft(), false); assert.equal(h.window.ConsoleRepositoryPublish.canReload(), true); await h.open(); await h.change("notes", "kept locally"); assert.equal(h.api.hasDraft(), true); assert.equal(h.window.ConsoleRepositoryPublish.canReload(), false);
  const pendingId = randomUUID(), pending = harness({ storage: new Map([[KEY, pendingId]]) }); await pending.ready(); assert.equal(pending.window.ConsoleRepositoryPublish.hasDraft(), false); assert.equal(pending.window.ConsoleRepositoryPublish.canReload(), true); assert.equal(pending.posts().length, 0);
});
await test("destroyed component cannot clear a newer pending identity with a late response", async () => {
  const delayed = deferred(); const h = harness({ hook(call) { if (call.url === BASE + "/run") return delayed.promise; } }); await h.ready(); h.byClass("repository-publish-primary").click(); await settle(); const original = h.posts("/run")[0].body.requestId; h.api.destroy(); const newer = randomUUID(); h.storage.set(KEY, newer); delayed.resolve(response(operation(original, "complete"))); await settle(); assert.equal(h.storage.get(KEY), newer); assert.equal(h.host.children.length, 0); assert.equal(h.window.ConsoleRepositoryPublish.canReload(), true);
});
await test("actual queued/attention repositories contract releases and shows deferred retry", async () => {
  const h = harness(); await h.ready(); h.byClass("repository-publish-primary").click(); await settle(); const id = h.posts("/run")[0].body.requestId; assert.equal(h.byClass("repository-publish-primary").disabled, true);
  h.snapshot.operation = operation(id, "attention", [{ repoId: "repository-001", name: "Music", status: "deferred", phase: "checking", message: "busy workspace", logs: [{ at: "fixture-time", phase: "checking", message: "original files retained" }] }]); await h.poll(); assert.equal(h.storage.has(KEY), false); await h.open(); assert.ok(h.button("继续此仓库")); assert.ok(h.all().some(item => item.textContent.includes("original files retained")));
});
await test("interrupted queued repository receives a continuation from verification_required", async () => {
  const id = randomUUID(), h = harness({ snapshot: { operation: operation(id, "verification_required", [{ repoId: "repository-001", status: "queued", name: "Music" }]) } }); await h.ready(); await h.open(); assert.ok(h.button("继续此仓库")); assert.equal(h.byClass("repository-publish-primary").disabled, false);
});
await test("storage failure sends nothing and reports failure before network mutation", async () => {
  const h = harness({ storageUnavailable: true }); await h.ready(); h.byClass("repository-publish-primary").click(); await settle(); assert.equal(h.posts().length, 0); assert.match(h.byClass("repository-publish-status").textContent, /尚未发送/); assert.equal(h.api.canReload(), true);
});
await test("authoritative missing receipt offers only an explicit same-ID original-scope continuation", async () => {
  let attempts = 0; const h = harness({ hook(call) { if (call.url === BASE + "/run" && ++attempts === 1) throw new Error("delivery unknown"); } }); await h.ready(); h.byClass("repository-publish-primary").click(); await settle(); const original = structuredClone(h.posts("/run")[0].body); assert.equal(h.button("继续原请求").hidden, true); await h.poll(); assert.equal(h.button("继续原请求").hidden, false); assert.equal(h.posts("/run").length, 1);
  h.button("继续原请求").click(); await settle(); assert.equal(h.posts("/run").length, 2); assert.deepEqual(h.posts("/run")[1].body, original); assert.equal(JSON.parse(h.storage.get(KEY + ".payload")).repoIds[0], "repository-001");
});
await test("reload restores original scope and unknown GET cannot offer a retry", async () => {
  const requestId = randomUUID(), original = { requestId, repoIds: ["repository-001"], createdAt: 1 }, storage = new Map([[KEY, requestId], [KEY + ".payload", JSON.stringify(original)]]);
  const h = harness({ storage, hook(call) { if (call.url.startsWith(BASE + "/operation?")) throw new Error("network unknown"); } }); await h.ready(); await h.poll(); assert.equal(h.button("继续原请求").hidden, true); assert.equal(h.posts().length, 0);
  h.hook(undefined); await h.poll(); assert.equal(h.button("继续原请求").hidden, false); h.button("继续原请求").click(); await settle(); assert.deepEqual(h.posts("/run")[0].body, { requestId, repoIds: original.repoIds });
});
await test("config response cannot replace current receipt with its stale operation", async () => {
  const latest = randomUUID(), stale = randomUUID(), h = harness({ snapshot: { operation: operation(latest, "attention", [{ repoId: "repository-001", name: "Latest receipt", status: "deferred", message: "Latest result" }]) }, hook(call) { if (call.url === BASE + "/config") return response({ settings: call.body.settings, operation: operation(stale, "queued", [{ repoId: "repository-001", name: "Stale receipt" }]) }); } }); await h.ready(); await h.open(); await h.change("notes", "note"); const labels = h.all().map(item => item.textContent).join(" "); assert.match(labels, /Latest receipt/); assert.doesNotMatch(labels, /Stale receipt/); assert.equal(h.storage.has(KEY), false);
});
await test("unfinished version-source row remains a draft until its file is entered", async () => {
  const h = harness(); await h.ready(); await h.open(); h.button("添加版本来源").click(); await settle(); assert.equal(h.posts("/config").length, 0); assert.equal(h.api.hasDraft(), true); await h.change("versionPath", "app-manifest.json"); assert.equal(h.posts("/config").length, 1); assert.equal(h.posts("/config")[0].body.settings.repositories[0].versionSources[0].path, "app-manifest.json"); assert.equal(h.api.hasDraft(), false);
});
await test("missing receipt refreshes aggregate busy state so a finished other operation cannot latch recovery", async () => {
  const requestId = randomUUID(), original = { requestId, repoIds: ["repository-001"], createdAt: 1 }, storage = new Map([[KEY, requestId], [KEY + ".payload", JSON.stringify(original)]]);
  const h = harness({ storage, snapshot: { busy: true } }); await h.ready(); await h.poll(); assert.equal(h.button("继续原请求").disabled, true); h.snapshot.busy = false; await h.poll(); assert.equal(h.button("继续原请求").disabled, false); assert.equal(h.posts().length, 0);
});
await test("typing before change guards reload and late autosave cannot discard or submit it", async () => {
  const delayed = deferred(); let writes = 0; const h = harness({ hook(call) { if (call.url === BASE + "/config" && ++writes === 1) return delayed.promise; } }); await h.ready(); await h.open(); await h.change("subtitle", "first edit"); const input = h.fields("notes")[0]; input.value = "still typing"; input.dispatch("input"); await settle(); assert.equal(h.api.hasDraft(), true); assert.equal(h.api.canReload(), false); delayed.resolve(response({ settings: h.posts("/config")[0].body.settings })); await settle(); assert.equal(h.posts("/config").length, 1); assert.equal(h.fields("notes")[0], input); assert.equal(input.value, "still typing"); input.dispatch("change"); await settle(); assert.equal(h.posts("/config").length, 2); assert.equal(h.posts("/config")[1].body.settings.naming.notes, "still typing"); assert.equal(h.api.hasDraft(), false);
});
console.log(`PASS ${count} isolated repository-publish UI fixtures`);
