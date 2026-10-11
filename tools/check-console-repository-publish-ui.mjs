#!/usr/bin/env node
// Deterministic VM/DOM fixtures. No live HTTP, Git, browser, source repository or user-data access.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { randomUUID } from "node:crypto";
const source = readFileSync(new URL("../console-repository-publish.js", import.meta.url), "utf8");
const css = readFileSync(new URL("../console-repository-publish.css", import.meta.url), "utf8");
const index = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const BASE = "/api/console/repository-publish";
const KEY = "console.repositoryPublish.pending.v1";
const settle = async () => { for (let i = 0; i < 15; i++) await new Promise(resolve => setImmediate(resolve)); };
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
const response = value => ({ ok: true, status: 200, json: async () => structuredClone(value) });
const repository = (extra = {}) => ({ id: "repository-001", path: "D:/Projects/Music", repositoryUrl: "https://github.com/example/Music", remote: "origin", branch: "feature/music", enabled: true, syncFiles: [], versionSources: [], exclude: [], ...extra });
const settings = repos => ({ repositories: repos || [repository()], naming: { preset: "version", fallbackTitle: "更新进度 {datetime}", subtitle: "", notes: "", includeSummary: true } });
const operation = (requestId, status = "working", repositories = []) => ({ requestId, status, repositories, message: "fixture" });
const component = (extra = {}) => ({ sourceId: "stable-component-001", path: "package.json", kind: "json", key: "version", name: "Music", scope: [], currentVersion: "2.3.4", nextVersion: "2.3.5", canBump: true, reason: "", expectedSha256: "a".repeat(64), expectedBytes: 100, planProof: "b".repeat(64), ...extra });
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
  // Match the native DOM contract: HTMLTextAreaElement.type is getter-only.
  class TextAreaElement extends Element { get type() { return "textarea"; } }
  // A native select does not retain values that have no matching option.
  class SelectElement extends Element {
    get type() { return "select-one"; }
    get value() { return this.children.find(item => item.selected)?.value || ""; }
    set value(value) { let matched = false; for (const option of this.children) { option.selected = !matched && option.value === String(value); if (option.selected) matched = true; } }
    get selectedIndex() { return this.children.findIndex(item => item.selected); }
    append(...items) { super.append(...items); if (!this.children.some(item => item.selected) && this.children.length) this.children[0].selected = true; }
  }
  const root = new Element("html"), panel = new Element("section"), host = new Element("div");
  root.lang = options.lang || "zh-CN"; panel.setAttribute("data-module-panel", options.module || "workspace"); host.id = "consoleRepositoryPublishHost"; root.append(panel); panel.append(host);
  const all = (parent = root) => [parent, ...parent.children.flatMap(item => all(item))];
  document = { documentElement: root, readyState: options.loading ? "loading" : "complete", activeElement: null, createElement: tag => tag.toLowerCase() === "textarea" ? new TextAreaElement(tag) : tag.toLowerCase() === "select" ? new SelectElement(tag) : new Element(tag), getElementById: id => all().find(item => item.id === id), addEventListener(type, handler) { if (!listeners.has(type)) listeners.set(type, []); listeners.get(type).push(handler); } };
  const stored = options.storageUnavailable ? { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }, removeItem() { throw new Error("blocked"); } } : { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) };
  const snapshot = { allowed: true, busy: false, settings: settings(), operation: null, ...(options.snapshot || {}) };
  const catalog = options.catalog || { repositories: snapshot.settings.repositories.map(repo => ({ repoId: repo.id, name: "Music", components: [] })) };
  const window = { crypto: { randomUUID }, localStorage: stored, sessionStorage: stored, setTimeout(fn, delay) { const id = ++timerId; timers.set(id, { fn, delay }); return id; }, clearTimeout(id) { timers.delete(id); }, addEventListener() {}, removeEventListener() {}, async fetch(url, init) {
    const call = { url, method: init.method, body: init.body ? JSON.parse(init.body) : null, options: init }; calls.push(call);
    if (hook) { const value = await hook(call); if (value !== undefined) return value; }
    if (url === BASE && init.method === "GET") return response(snapshot);
    if (url === BASE + "/versions" && init.method === "GET") return response(catalog);
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
  const visible = item => { for (let parent = item; parent; parent = parent.parentElement) if (parent.hidden || parent !== item && parent.tagName === "DETAILS" && !parent.open && !parent.children[0]?.contains(item)) return false; return true; };
  return { window, document, snapshot, catalog, host, panel, all, calls, storage, timers, byClass, fields, button, visible, hook(value) { hook = value; }, get api() { return window.ConsoleRepositoryPublish.mount({ host }); }, posts(path) { return calls.filter(call => call.method === "POST" && (!path || call.url === BASE + path)); }, async ready() { if (options.loading) for (const listener of listeners.get("DOMContentLoaded") || []) listener(); await settle(); }, async open(repoId) { window.ConsoleRepositoryPublish.mount({ host }).open(repoId); await settle(); }, async expand() { byClass("repository-publish-toggle").click(); await settle(); }, async change(name, value, index = 0) { const input = fields(name)[index]; assert.ok(input, name); if (input.type === "checkbox") input.checked = value; else input.value = value; input.dispatch("change"); await settle(); }, locale(value) { root.lang = value; for (const observer of observers) observer.callback([]); }, async poll() { const entry = [...timers.entries()].find(([, item]) => item.delay >= 1200 && item.delay <= 10000); assert.ok(entry, "expected original-request polling timer"); timers.delete(entry[0]); entry[1].fn(); await settle(); } };
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
  const h = harness({ loading: true }); assert.equal(h.host.children.length, 0); await h.ready(); const api = h.api; assert.equal(h.api, api); assert.equal(h.host.children.length, 3); assert.equal(h.calls.length, 1); assert.equal(h.posts().length, 0);
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
await test("native getter-only textarea type opens multiline config and preserves autosaved values", async () => {
  const h = harness({ snapshot: { settings: settings([repository({ syncFiles: [{ source: "D:/Saved/Builder6.blend", target: "Build.blend" }], exclude: ["private/", "cache/"] })]) } });
  await h.ready(); await h.open(); assert.equal(h.byClass("repository-publish-dialog").open, true);
  for (const name of ["sync", "excludes", "notes"]) {
    const input = h.fields(name)[0], descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), "type");
    assert.equal(input.tagName, "TEXTAREA"); assert.equal(input.type, "textarea"); assert.equal(typeof descriptor.get, "function"); assert.equal(descriptor.set, undefined);
    assert.throws(() => { input.type = "text"; }, TypeError); assert.equal(Object.hasOwn(input, "type"), false);
    assert.equal(input.rows, 3); assert.equal(input.maxLength, 16000);
  }
  assert.equal(h.fields("sync")[0].value, "D:/Saved/Builder6.blend -> Build.blend"); assert.equal(h.fields("excludes")[0].value, "private/\ncache/");
  assert.equal(h.fields("enabled")[0].type, "checkbox"); assert.equal(h.fields("path")[0].type, "text");
  await h.change("notes", "Saved scene only\nNo inferred feature changes"); const payload = h.posts("/config")[0].body.settings;
  assert.equal(payload.naming.notes, "Saved scene only\nNo inferred feature changes"); assert.deepEqual(payload.repositories[0].syncFiles, [{ source: "D:/Saved/Builder6.blend", target: "Build.blend" }]); assert.deepEqual(payload.repositories[0].exclude, ["private/", "cache/"]);
  h.button("关闭").click(); await h.open(); assert.equal(h.fields("notes")[0].value, payload.naming.notes); assert.equal(h.posts("/run").length, 0);
});
await test("discovered Unity kind selects a native option and its three scopes round-trip as separate lines", async () => {
  const scopes = ["Assets/**", "Packages/**", "ProjectSettings/**"], version = { path: "ProjectSettings/ProjectSettings.asset", kind: "unity", key: "bundleVersion", name: "Unity application", scope: scopes };
  const h = harness({ snapshot: { settings: settings([repository({ versionSources: [version] })]) } }); await h.ready(); await h.open();
  const kind = h.fields("kind")[0]; assert.equal(kind.tagName, "SELECT"); assert.equal(kind.type, "select-one"); assert.equal(kind.value, "unity"); assert.ok(kind.selectedIndex >= 0);
  assert.throws(() => { kind.type = "text"; }, TypeError); kind.value = "not-a-version-format"; assert.equal(kind.value, ""); assert.equal(kind.selectedIndex, -1); kind.value = "unity";
  assert.equal(h.fields("scope")[0].tagName, "TEXTAREA"); assert.equal(h.fields("scope")[0].value, scopes.join("\n")); assert.equal(h.posts("/config").length, 0);
  await h.change("notes", "Retain discovered version binding"); assert.deepEqual(h.posts("/config").at(-1).body.settings.repositories[0].versionSources[0], version);
  await h.change("scope", "Assets/**\r\nPackages/**\r\nProjectSettings/**"); assert.deepEqual(h.posts("/config").at(-1).body.settings.repositories[0].versionSources[0].scope, scopes);
  await h.change("scope", "Assets/**"); assert.deepEqual(h.posts("/config").at(-1).body.settings.repositories[0].versionSources[0].scope, ["Assets/**"]);
  h.button("关闭").click(); await h.open(); assert.equal(h.fields("kind")[0].value, "unity"); assert.equal(h.fields("scope")[0].value, "Assets/**"); assert.equal(h.posts("/run").length, 0);
});
await test("single string version scope keeps its schema until multiple lines are entered", async () => {
  const version = { path: "package.json", kind: "json", key: "version", name: "Module", scope: "src/**" };
  const h = harness({ snapshot: { settings: settings([repository({ versionSources: [version] })]) } }); await h.ready(); await h.open(); assert.equal(h.fields("scope")[0].value, "src/**");
  await h.change("scope", ""); assert.equal(h.posts("/config").at(-1).body.settings.repositories[0].versionSources[0].scope, "");
  await h.change("scope", "lib/**"); assert.equal(h.posts("/config").at(-1).body.settings.repositories[0].versionSources[0].scope, "lib/**");
  await h.change("scope", "lib/**\nassets/a,b.blend"); assert.deepEqual(h.posts("/config").at(-1).body.settings.repositories[0].versionSources[0].scope, ["lib/**", "assets/a,b.blend"]);
  await h.change("scope", ""); assert.deepEqual(h.posts("/config").at(-1).body.settings.repositories[0].versionSources[0].scope, []); assert.equal(h.posts("/run").length, 0);
});
await test("existing backend format aliases stay selected and are not rewritten by unrelated edits", async () => {
  const aliases = ["app-manifest", "package", "yaml", "bl_info", "csproj"], versions = aliases.map((kind, i) => ({ path: `component${i}/version.txt`, kind, key: "version", name: kind, scope: `component${i}/**` }));
  const h = harness({ snapshot: { settings: settings([repository({ versionSources: versions })]) } }); await h.ready(); await h.open();
  assert.deepEqual(h.fields("kind").map(input => input.value), aliases); assert.ok(h.fields("kind").every(input => input.selectedIndex >= 0));
  await h.change("notes", "Keep existing format aliases"); assert.deepEqual(h.posts("/config").at(-1).body.settings.repositories[0].versionSources, versions); assert.equal(h.posts("/run").length, 0);
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
  const h = harness(); await h.ready(); await h.open(); const before = h.calls.length; h.locale("en"); assert.equal(h.byClass("repository-publish-primary").textContent, "Push to GitHub"); assert.equal(h.fields("branch")[0].placeholder, "Current branch (read and save)"); assert.equal(h.fields("branch")[0].value, "feature/music"); assert.equal(h.calls.length, before); assert.ok(h.button("Configure all"));
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
await test("real host precedes Console subnav and remains inside the workspace module", async () => {
  const host = index.indexOf('id="consoleRepositoryPublishHost"'), subnav = index.indexOf('class="console-subnav"'), panel = index.lastIndexOf('data-module-panel="workspace"', host);
  assert.ok(host >= 0 && panel >= 0 && panel < host && host < subnav); assert.equal((index.match(/id="consoleRepositoryPublishHost"/g) || []).length, 1);
});
await test("arrow shows five dynamic GitHub names and current versions without forms or mutations", async () => {
  const names = ["RandomRealm2", "Builder6", "CodexControlConsole", "MyWeb", "MyGitHub"], repos = names.map((name, i) => repository({ id: `repository-${i + 1}`, path: `D:/Unrelated/Folder${i}`, name: `Wrong path title ${i}`, repositoryUrl: i === 4 ? "git@github.com:owner/MyGitHub.git" : `https://github.com/owner/${name}.git`, versionSources: [{ path: "package.json", kind: "json", key: "version" }] }));
  const h = harness({ snapshot: { settings: settings(repos) }, catalog: { repositories: repos.map((repo, i) => ({ repoId: repo.id, components: [component({ currentVersion: `1.0.${i}`, nextVersion: `1.0.${i + 1}` })] })) } }); await h.ready();
  assert.equal(h.byClass("repository-publish-primary").textContent, "推送到 GitHub"); assert.equal(h.byClass("repository-publish-expanded").hidden, true); assert.equal(h.calls.length, 1); assert.equal(h.fields("path").length, 0);
  await h.expand(); const rows = h.byClass("repository-publish-compact-rows").children; assert.equal(rows.length, 5); assert.deepEqual(rows.map(row => row.children[0].textContent), names); assert.deepEqual(rows.map(row => row.children[1].textContent), names.map((_, i) => `1.0.${i}`));
  assert.equal(h.byClass("repository-publish-toggle").getAttribute("aria-expanded"), "true"); assert.ok(h.button("配置全部")); assert.equal(h.fields("path").length, 0); assert.equal(h.posts().length, 0); assert.equal(h.calls.filter(call => call.url.endsWith("/versions")).length, 1);
  await h.expand(); assert.equal(h.byClass("repository-publish-expanded").hidden, true); assert.equal(h.calls.filter(call => call.url.endsWith("/versions")).length, 1); h.locale("en"); assert.equal(h.byClass("repository-publish-primary").textContent, "Push to GitHub"); assert.equal(h.posts().length, 0);
});
await test("single-repository configure hides other repos and keeps paths and rules collapsed", async () => {
  const repos = [repository(), repository({ id: "repository-002", repositoryUrl: "https://github.com/example/Second.git", path: "D:/Other" })], h = harness({ snapshot: { settings: settings(repos) } }); await h.ready(); await h.expand(); h.byClass("repository-publish-compact-rows").children[1].children[3].click(); await settle();
  const cards = h.byClass("repository-publish-repositories").children; assert.equal(cards[0].hidden, true); assert.equal(cards[1].hidden, false); assert.equal(cards[1].open, true); assert.match(h.byClass("repository-publish-header").children[0].textContent, /^Second/);
  assert.equal(h.fields("enabled").filter(h.visible).length, 1); assert.equal(h.fields("path").filter(h.visible).length, 0); assert.equal(h.fields("notes").filter(h.visible).length, 0); assert.equal(h.fields("sync").filter(h.visible).length, 0); assert.equal(h.posts().length, 0);
  h.button("预览标题与改动").click(); await settle(); assert.deepEqual(h.posts("/preview")[0].body, { repoId: "repository-002" }); assert.equal(h.posts("/run").length, 0);
  h.button("关闭").click(); h.button("配置全部").click(); await settle(); assert.ok(h.byClass("repository-publish-repositories").children.every(card => !card.hidden));
});
await test("all configuration starts as a compact name list and retains expanded details after autosave", async () => {
  const h = harness({ snapshot: { settings: settings([repository(), repository({ id: "repository-002", path: "D:/Other", repositoryUrl: "https://github.com/example/Second" })]) } }); await h.ready(); await h.open();
  const cards = h.byClass("repository-publish-repositories").children; assert.ok(cards.every(card => card.tagName === "DETAILS" && !card.open)); assert.equal(h.fields("path").filter(h.visible).length, 0); assert.deepEqual(cards.map(card => card.children[0].textContent), ["Music", "Second"]);
  cards[0].open = true; const connection = h.all(cards[0]).find(item => item.className.split(" ").includes("repository-publish-connection")); connection.open = true; await h.change("branch", "feature/real-branch");
  assert.equal(h.byClass("repository-publish-repositories").children[0].open, true); assert.equal(h.byClass("repository-publish-connection").open, true); assert.equal(h.posts("/config")[0].body.settings.repositories[0].branch, "feature/real-branch"); assert.equal(h.posts("/run").length, 0);
});
await test("patch plans preserve each component format and proof and only save configuration", async () => {
  const components = [component({ name: "Unity", currentVersion: "0.1", nextVersion: "0.1.1" }), component({ sourceId: "stable-second", name: "Blender", currentVersion: "(1, 2, 3)", nextVersion: "(1, 2, 4)", planProof: "c".repeat(64) }), component({ sourceId: "manual", name: "Other", canBump: false, nextVersion: "", reason: "Custom format is read-only" })];
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", components }] } }); await h.ready(); await h.open("repository-001"); let actions = h.all().filter(item => item.className.split(" ").includes("repository-publish-plan-action")); assert.equal(actions.length, 3); assert.equal(actions[2].disabled, true); assert.ok(h.all().some(item => item.textContent === "Custom format is read-only"));
  actions[0].click(); await settle(); actions = h.all().filter(item => item.className.split(" ").includes("repository-publish-plan-action")); actions[1].click(); await settle();
  const plans = h.posts("/config").at(-1).body.settings.repositories[0].versionPlans; assert.deepEqual(plans, components.slice(0, 2).map(item => ({ sourceId: item.sourceId, currentVersion: item.currentVersion, targetVersion: item.nextVersion, expectedSha256: item.expectedSha256, expectedBytes: item.expectedBytes, planProof: item.planProof }))); assert.equal(h.posts("/run").length, 0);
  assert.match(h.byClass("repository-publish-compact-version").textContent, /Unity 0.1 → 0.1.1.*Blender \(1, 2, 3\) → \(1, 2, 4\)/);
  h.button("取消计划").click(); await settle(); assert.equal(h.posts("/config").at(-1).body.settings.repositories[0].versionPlans.length, 1); assert.equal(h.posts("/run").length, 0);
});
await test("version lookup failure or missing proof cannot invent a plan or block unchanged-version push", async () => {
  const h = harness({ hook(call) { if (call.url === BASE + "/versions") throw new Error("read unavailable"); } }); await h.ready(); await h.expand(); assert.equal(h.posts().length, 0); assert.equal(h.byClass("repository-publish-primary").disabled, false); assert.match(h.byClass("repository-publish-compact-version").textContent, /读取失败/);
  const bad = harness({ catalog: { repositories: [{ repoId: "repository-001", components: [component({ planProof: "" })] }] } }); await bad.ready(); await bad.open(); assert.equal(bad.byClass("repository-publish-plan-action").disabled, true); assert.equal(bad.posts().length, 0);
});
await test("switching repository configuration preserves invalid raw sync drafts and never posts a run", async () => {
  const h = harness({ snapshot: { settings: settings([repository(), repository({ id: "repository-002", path: "D:/Other" })]) } }); await h.ready(); await h.open("repository-001"); await h.change("sync", "raw unpaired ->"); const raw = h.fields("sync")[0]; await h.open("repository-002"); assert.equal(h.fields("sync")[0], raw); assert.equal(raw.value, "raw unpaired ->"); assert.equal(h.api.hasDraft(), true); assert.equal(h.posts().length, 0); assert.equal(h.byClass("repository-publish-primary").disabled, true);
});
await test("late status read cannot overwrite a configuration that finished saving after that read began", async () => {
  const delayed = deferred(); let reads = 0; const h = harness({ hook(call) { if (call.url === BASE && call.method === "GET" && ++reads === 2) return delayed.promise; } }); await h.ready(); const stale = structuredClone(h.snapshot); h.api.open(); await settle(); await h.change("notes", "newer completed save"); assert.equal(h.posts("/config").length, 1); delayed.resolve(response(stale)); await settle(); assert.equal(h.fields("notes")[0].value, "newer completed save"); assert.equal(h.api.hasDraft(), false);
});
await test("completed operation refreshes cleared one-time plans without polling version files or repeating POST", async () => {
  const comp = component(), plan = { sourceId: comp.sourceId, currentVersion: comp.currentVersion, targetVersion: comp.nextVersion, expectedSha256: comp.expectedSha256, expectedBytes: comp.expectedBytes, planProof: comp.planProof }, h = harness({ snapshot: { settings: settings([repository({ versionPlans: [plan] })]) } }); await h.ready(); h.byClass("repository-publish-primary").click(); await settle(); const id = h.posts("/run")[0].body.requestId;
  h.snapshot.settings.repositories[0].versionPlans = []; h.snapshot.operation = operation(id, "success", [{ repoId: "repository-001", status: "success" }]); await h.poll(); assert.equal(h.posts("/run").length, 1); assert.equal(h.calls.filter(call => call.url.endsWith("/versions")).length, 0); await h.open(); assert.equal(h.posts().filter(call => call.url.endsWith("/config")).length, 0); assert.equal(h.all().some(item => item.textContent === "取消计划"), false);
});
await test("visible planned operation reads the actual completed version once and does not infer its target", async () => {
  const comp = component(), plan = { sourceId: comp.sourceId, currentVersion: comp.currentVersion, targetVersion: comp.nextVersion, expectedSha256: comp.expectedSha256, expectedBytes: comp.expectedBytes, planProof: comp.planProof }, h = harness({ snapshot: { settings: settings([repository({ versionPlans: [plan] })]) }, catalog: { repositories: [{ repoId: "repository-001", components: [comp] }] } }); await h.ready(); await h.expand(); assert.match(h.byClass("repository-publish-compact-version").textContent, /2.3.4 → 2.3.5/);
  h.byClass("repository-publish-primary").click(); await settle(); const id = h.posts("/run")[0].body.requestId; h.snapshot.settings.repositories[0].versionPlans = []; h.snapshot.operation = operation(id, "success", [{ repoId: "repository-001", status: "success" }]); h.catalog.repositories[0].components[0].currentVersion = "2.3.5"; await h.poll();
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.5"); assert.equal(h.calls.filter(call => call.url.endsWith("/versions")).length, 2); assert.equal(h.posts("/run").length, 1); assert.equal(h.posts("/config").length, 0);
  const failed = harness({ snapshot: { settings: settings([repository({ versionPlans: [plan] })]) }, catalog: { repositories: [{ repoId: "repository-001", components: [component()] }] } }); await failed.ready(); await failed.expand(); failed.byClass("repository-publish-primary").click(); await settle(); const failedId = failed.posts("/run")[0].body.requestId; failed.snapshot.settings.repositories[0].versionPlans = []; failed.snapshot.operation = operation(failedId, "attention", [{ repoId: "repository-001", status: "commit_failed" }]); await failed.poll(); assert.equal(failed.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.equal(failed.posts("/run").length, 1);
});
await test("saved source changes invalidate old catalog and a late lookup cannot expose the old component", async () => {
  const delayed = deferred(), old = { repositories: [{ repoId: "repository-001", components: [component()] }] }, fresh = { repositories: [{ repoId: "repository-001", components: [component({ sourceId: "new-source", path: "new-package.json", currentVersion: "4.0.0", nextVersion: "4.0.1" })] }] }; let reads = 0;
  const h = harness({ snapshot: { settings: settings([repository({ versionSources: [{ path: "package.json", kind: "json", key: "version", name: "Module", scope: "" }] })]) }, hook(call) { if (call.url === BASE + "/versions") return ++reads === 1 ? response(old) : reads === 2 ? delayed.promise : response(fresh); } }); await h.ready(); await h.expand(); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); h.api.open("repository-001"); await settle(); await h.change("versionPath", "new-package.json");
  assert.equal(h.byClass("repository-publish-plan-action"), undefined); assert.match(h.byClass("repository-publish-compact-version").textContent, /待读取/); delayed.resolve(response(old)); await settle(); assert.equal(h.byClass("repository-publish-compact-version").textContent, "4.0.0"); h.byClass("repository-publish-plan-action").click(); await settle(); assert.equal(h.posts("/config").at(-1).body.settings.repositories[0].versionPlans[0].sourceId, "new-source"); assert.equal(h.posts("/run").length, 0);
});
await test("backend noop is no changes and solid dialog and theme-aware primary colors remain explicit", async () => {
  const h = harness({ snapshot: { operation: operation(randomUUID(), "success", [{ repoId: "repository-001", status: "noop" }]) } }); await h.ready(); await h.expand(); assert.equal(h.byClass("repository-publish-compact-status").textContent, "无改动"); h.locale("en"); assert.equal(h.byClass("repository-publish-compact-status").textContent, "No changes");
  assert.match(css, /\.repository-publish-dialog\s*\{[^}]*background:\s*var\(--solid-popover-bg,/); assert.match(css, /\.repository-publish-bar \.repository-publish-primary\s*\{[^}]*color:\s*var\(--bg,[^}]*background:\s*var\(--status-success,/); assert.equal(h.posts().length, 0);
});
console.log(`PASS ${count} isolated repository-publish UI fixtures`);
