#!/usr/bin/env node
// Deterministic VM/DOM fixtures. No live HTTP, Git, browser, source repository or user-data access.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { createHash, randomUUID } from "node:crypto";
const source = readFileSync(new URL("../console-repository-publish.js", import.meta.url), "utf8");
const css = readFileSync(new URL("../console-repository-publish.css", import.meta.url), "utf8");
const index = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const BASE = "/api/console/repository-publish";
const KEY = "console.repositoryPublish.pending.v1";
const DISPLAY_KEY = "console.repositoryPublish.versionDisplay.v1";
const settle = async () => { for (let i = 0; i < 15; i++) await new Promise(resolve => setImmediate(resolve)); };
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
const response = value => ({ ok: true, status: 200, json: async () => structuredClone(value) });
const settingsSha = value => createHash("sha256").update(JSON.stringify(value)).digest("hex");
const configReceipt = value => ({ settings: value, settingsSha: settingsSha(value) });
const repository = (extra = {}) => ({ id: "repository-001", path: "D:/Projects/Music", repositoryUrl: "https://github.com/example/Music", remote: "origin", branch: "feature/music", enabled: true, syncFiles: [], versionSources: [], exclude: [], ...extra });
const settings = repos => ({ repositories: repos || [repository()], naming: { preset: "version", fallbackTitle: "更新进度 {datetime}", subtitle: "", notes: "", includeSummary: true, autoBump: true } });
const operation = (requestId, status = "working", repositories = []) => ({ requestId, status, repositories, message: "fixture" });
const component = (extra = {}) => ({ sourceId: "stable-component-001", path: "package.json", kind: "json", key: "version", name: "Music", scope: [], currentVersion: "2.3.4", nextVersion: "2.3.5", headVersion: "2.3.4", versionChanged: false, worktreeChanged: false, planState: "none", plannedVersion: "", transition: null, canBump: true, reason: "", expectedSha256: "a".repeat(64), expectedBytes: 100, planProof: "b".repeat(64), ...extra });
const automaticComponent = (extra = {}) => {
  const item = component({ worktreeChanged: true, ...extra });
  return { ...item, autoPlan: extra.autoPlan || { state: "eligible", fromVersion: item.currentVersion, targetVersion: item.nextVersion, reason: "Actual scoped fixture file changed" },
    transition: extra.transition === undefined ? { kind: "auto", fromVersion: item.currentVersion, toVersion: item.nextVersion } : extra.transition };
};
const planFor = item => ({ sourceId: item.sourceId, currentVersion: item.currentVersion, targetVersion: item.nextVersion, expectedSha256: item.expectedSha256, expectedBytes: item.expectedBytes, planProof: item.planProof });
function harness(options = {}) {
  const timers = new Map(), calls = [], observers = [], listeners = new Map(), windowListeners = new Map(), storage = options.storage || new Map();
  let document, hook = options.hook, timerId = 0;
  class Element {
    constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.parentElement = null; this.listeners = new Map(); this.attributes = {}; this.dataset = {}; this.hidden = false; this.disabled = false; this.open = false; this.checked = false; this.value = ""; this.textContent = ""; this.className = ""; }
    append(...items) { for (const item of items) { item.remove(); item.parentElement = this; this.children.push(item); } }
    replaceChildren(...items) { for (const old of this.children) old.parentElement = null; this.children = []; this.append(...items); }
    remove() { if (this.parentElement) { const parent = this.parentElement; parent.children.splice(parent.children.indexOf(this), 1); this.parentElement = null; } }
    contains(item) { return item === this || this.children.some(child => child.contains(item)); }
    closest(selector) { for (let item = this; item; item = item.parentElement) if (selector === '[data-module-panel="workspace"]' && item.attributes["data-module-panel"] === "workspace") return item; return null; }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    getAttribute(key) { return this.attributes[key] ?? null; }
    setCustomValidity(value) { this.validationMessage = value; }
    addEventListener(type, handler) { if (!this.listeners.has(type)) this.listeners.set(type, []); this.listeners.get(type).push(handler); }
    dispatch(type, extra = {}) { if (this.disabled && ["click", "change"].includes(type)) return; const event = { target: this, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...extra }; for (const handler of this.listeners.get(type) || []) handler(event); return event; }
    click() { const event = this.dispatch("click"); if (event && !event.defaultPrevented && this.tagName === "SUMMARY" && this.parentElement?.tagName === "DETAILS") { this.parentElement.open = !this.parentElement.open; this.parentElement.dispatch("toggle"); } }
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
  document = { documentElement: root, readyState: options.loading ? "loading" : "complete", activeElement: null, createElement: tag => tag.toLowerCase() === "textarea" ? new TextAreaElement(tag) : tag.toLowerCase() === "select" ? new SelectElement(tag) : new Element(tag), getElementById: id => all().find(item => item.id === id), addEventListener(type, handler) { if (!listeners.has(type)) listeners.set(type, []); listeners.get(type).push(handler); }, removeEventListener(type, handler) { listeners.set(type, (listeners.get(type) || []).filter(item => item !== handler)); } };
  document.emit = (type, event) => { for (const handler of listeners.get(type) || []) handler(event); };
  const stored = options.storageUnavailable ? { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }, removeItem() { throw new Error("blocked"); } } : { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) };
  const snapshot = { allowed: true, busy: false, settings: settings(), operation: null, ...(options.snapshot || {}) };
  if (!("settingsSha" in snapshot)) snapshot.settingsSha = settingsSha(snapshot.settings);
  const catalog = options.catalog || { repositories: snapshot.settings.repositories.map(repo => ({ repoId: repo.id, name: "Music", components: [] })) };
  function versionReply() {
    return { repositories: catalog.repositories.map(item => {
      const repo = snapshot.settings.repositories.find(value => value.id === item.repoId);
      return { hasChanges: false, changeState: "unchanged", worktreeChanged: false, outgoingCommits: 0, ...structuredClone(item),
        components: (item.components || []).map(original => {
          const current = structuredClone(original), plan = repo?.versionPlans?.find(value => value.sourceId === current.sourceId);
          if (!plan || current.planState === "stale") return current;
          if (current.planState === "valid" && current.transition) return current;
          const valid = ["currentVersion", "expectedSha256", "expectedBytes", "planProof"].every(key => plan[key] === current[key]) && plan.targetVersion === current.nextVersion;
          return { ...current, planState: valid ? "valid" : "stale", plannedVersion: valid ? plan.targetVersion : "",
            transition: valid ? { kind: "planned", fromVersion: current.currentVersion, toVersion: plan.targetVersion } : current.transition };
        }) };
    }) };
  }
  const window = { crypto: { randomUUID }, localStorage: stored, sessionStorage: stored, setTimeout(fn, delay) { const id = ++timerId; timers.set(id, { fn, delay }); return id; }, clearTimeout(id) { timers.delete(id); }, addEventListener(type, handler) { if (!windowListeners.has(type)) windowListeners.set(type, new Set()); windowListeners.get(type).add(handler); }, removeEventListener(type, handler) { windowListeners.get(type)?.delete(handler); }, async fetch(url, init) {
    const call = { url, method: init.method, body: init.body ? JSON.parse(init.body) : null, options: init }; calls.push(call);
    if (hook) { const value = await hook(call); if (value !== undefined) return value; }
    if (url === BASE && init.method === "GET") return response(snapshot);
    if (url === BASE + "/versions" && init.method === "GET") return response(versionReply());
    if (url === BASE + "/config") {
      assert.equal(call.body.expectedSettingsSha, snapshot.settingsSha, "Configuration writes must compare the acknowledged service settings");
      snapshot.settings = structuredClone(call.body.settings); snapshot.settingsSha = settingsSha(snapshot.settings);
      return response(configReceipt(snapshot.settings));
    }
    if (url === BASE + "/preview") return response({ previews: [{ repoId: "repository-001", title: "Music v2.3", body: "2 files", versions: [{ name: "Music", version: "2.3" }] }] });
    if (url === BASE + "/run") { snapshot.operation = operation(call.body.requestId, "queued"); return response(snapshot.operation); }
    if (url.startsWith(BASE + "/operation?")) return response(snapshot.operation || null);
    throw new Error("Unexpected fixture request: " + url);
  } };
  class MutationObserver { constructor(callback) { this.callback = callback; observers.push(this); } observe(target) { this.target = target; } disconnect() { this.disconnected = true; } }
  runInNewContext(source, { window, document, MutationObserver, WeakMap, Map, Set, Uint8Array, AbortController, console });
  const byClass = (name, parent = root) => all(parent).find(item => item.className.split(" ").includes(name));
  const fields = name => all().filter(item => item.dataset.field === name);
  const button = label => all().find(item => item.tagName === "BUTTON" && item.textContent === label);
  const visible = item => { for (let parent = item; parent; parent = parent.parentElement) if (parent.hidden || parent !== item && parent.tagName === "DETAILS" && !parent.open && !parent.children[0]?.contains(item)) return false; return true; };
  return { window, document, snapshot, catalog, host, panel, all, calls, storage, timers, byClass, fields, button, visible, hook(value) { hook = value; }, get api() { return window.ConsoleRepositoryPublish.mount({ host }); }, posts(path) { return calls.filter(call => call.method === "POST" && (!path || call.url === BASE + path)); }, async ready() { if (options.loading) for (const listener of listeners.get("DOMContentLoaded") || []) listener(); await settle(); }, async open(repoId) { window.ConsoleRepositoryPublish.mount({ host }).open(repoId); await settle(); }, async expand() { byClass("repository-publish-toggle").click(); await settle(); }, async change(name, value, index = 0) { const input = fields(name)[index]; assert.ok(input, name); if (input.type === "checkbox") input.checked = value; else input.value = value; input.dispatch("change"); await settle(); }, locale(value) { root.lang = value; for (const observer of observers) if (observer.target === root && !observer.disconnected) observer.callback([]); }, async emitWindow(type) { for (const listener of windowListeners.get(type) || []) listener(); await settle(); }, async setPanelHidden(value) { panel.hidden = value; for (const observer of observers) if (observer.target === panel && !observer.disconnected) observer.callback([]); await settle(); }, async poll() { const entry = [...timers.entries()].find(([, item]) => item.delay >= 1200 && item.delay <= 10000); assert.ok(entry, "expected original-request polling timer"); timers.delete(entry[0]); entry[1].fn(); await settle(); } };
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
await test("ordinary GET retains its ten-second deadline and clears the exact timer after completion", async () => {
  const pending = deferred(); const h = harness({ hook(call) { if (call.url === BASE) return pending.promise; } });
  await h.ready(); assert.equal(h.calls.length, 1);
  const [[timerId, timer]] = h.timers; assert.equal(h.timers.size, 1); assert.equal(timer.delay, 10000);
  assert.equal(h.calls[0].options.signal.aborted, false);
  pending.resolve(response(h.snapshot)); await settle();
  assert.equal(h.timers.has(timerId), false); assert.equal(h.timers.size, 0); assert.equal(h.posts().length, 0);
});
await test("slow version catalog has a separate sixty-second deadline without a leftover generic abort", async () => {
  const pending = deferred(); const h = harness({ hook(call) { if (call.url === BASE + "/versions") return pending.promise; } });
  await h.ready(); await h.expand();
  const versions = h.calls.filter(call => call.url === BASE + "/versions"); assert.equal(versions.length, 1);
  const [[timerId, timer]] = h.timers; assert.equal(h.timers.size, 1); assert.equal(timer.delay, 60000);
  assert.equal([...h.timers.values()].some(item => item.delay === 10000), false, "the catalog must have no generic ten-second timer");
  assert.equal(versions[0].options.signal.aborted, false);
  pending.resolve(response({ repositories: [{ repoId: "repository-001", hasChanges: false, changeState: "unchanged", components: [component()] }] }));
  await settle(); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4");
  assert.equal(h.timers.has(timerId), false); assert.equal(h.timers.size, 0); assert.equal(h.posts().length, 0);
});
await test("version deadline still aborts at sixty seconds without mutation or automatic resend", async () => {
  const h = harness({ hook(call) { if (call.url === BASE + "/versions") return new Promise((resolve, reject) =>
    call.options.signal.addEventListener("abort", () => reject(new Error("synthetic catalog deadline")), { once: true })); } });
  await h.ready(); await h.expand();
  const [[timerId, timer]] = h.timers; assert.equal(timer.delay, 60000); timer.fn(); await settle();
  const versions = h.calls.filter(call => call.url === BASE + "/versions"); assert.equal(versions.length, 1);
  assert.equal(versions[0].options.signal.aborted, true); assert.equal(h.timers.has(timerId), false);
  assert.match(h.byClass("repository-publish-compact-version").textContent, /读取失败/); assert.equal(h.posts().length, 0);
});
await test("configuration POST keeps its twenty-second deadline and clears the timer after acknowledgement", async () => {
  const pending = deferred(); const h = harness({ hook(call) { if (call.url === BASE + "/config") return pending.promise; } });
  await h.ready(); await h.open(); await h.change("notes", "preserve POST deadline");
  const [[timerId, timer]] = h.timers; assert.equal(h.timers.size, 1); assert.equal(timer.delay, 20000);
  h.snapshot.settings = h.posts("/config")[0].body.settings; h.snapshot.settingsSha = settingsSha(h.snapshot.settings);
  pending.resolve(response(configReceipt(h.snapshot.settings))); await settle();
  assert.equal(h.timers.has(timerId), false); assert.equal(h.timers.size, 0); assert.equal(h.posts("/config").length, 1); assert.equal(h.posts("/run").length, 0);
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
  const h = harness(); await h.ready(); await h.open(); await h.change("notes", "optional release note"); assert.equal(h.posts("/config").length, 1); const payload = h.posts("/config")[0].body; assert.deepEqual(Object.keys(payload), ["settings", "expectedSettingsSha"]); assert.match(payload.expectedSettingsSha, /^[a-f0-9]{64}$/); assert.equal(payload.settings.naming.notes, "optional release note"); assert.equal(payload.settings.repositories[0].branch, "feature/music"); assert.equal(h.posts("/run").length, 0);
});
await test("autosaves serialize and preserve a newer edit over an older response", async () => {
  const pending = deferred(); let writes = 0; const h = harness({ hook(call) { if (call.url === BASE + "/config" && ++writes === 1) return pending.promise; } }); await h.ready(); await h.open(); await h.change("subtitle", "one"); await h.change("notes", "two"); assert.equal(h.posts("/config").length, 1); assert.equal(h.byClass("repository-publish-primary").disabled, true); h.snapshot.settings = h.posts("/config")[0].body.settings; h.snapshot.settingsSha = settingsSha(h.snapshot.settings); pending.resolve(response(configReceipt(h.snapshot.settings))); await settle(); assert.equal(h.posts("/config").length, 2); assert.equal(h.posts("/config")[1].body.settings.naming.subtitle, "one"); assert.equal(h.posts("/config")[1].body.settings.naming.notes, "two");
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
  const latest = randomUUID(), stale = randomUUID(), h = harness({ snapshot: { operation: operation(latest, "attention", [{ repoId: "repository-001", name: "Latest receipt", status: "deferred", message: "Latest result" }]) }, hook(call) { if (call.url === BASE + "/config") return response({ ...configReceipt(call.body.settings), operation: operation(stale, "queued", [{ repoId: "repository-001", name: "Stale receipt" }]) }); } }); await h.ready(); await h.open(); await h.change("notes", "note"); const labels = h.all().map(item => item.textContent).join(" "); assert.match(labels, /Latest receipt/); assert.doesNotMatch(labels, /Stale receipt/); assert.equal(h.storage.has(KEY), false);
});
await test("unfinished version-source row remains a draft until its file is entered", async () => {
  const h = harness(); await h.ready(); await h.open(); h.button("添加版本来源").click(); await settle(); assert.equal(h.posts("/config").length, 0); assert.equal(h.api.hasDraft(), true); await h.change("versionPath", "app-manifest.json"); assert.equal(h.posts("/config").length, 1); assert.equal(h.posts("/config")[0].body.settings.repositories[0].versionSources[0].path, "app-manifest.json"); assert.equal(h.api.hasDraft(), false);
});
await test("missing receipt refreshes aggregate busy state so a finished other operation cannot latch recovery", async () => {
  const requestId = randomUUID(), original = { requestId, repoIds: ["repository-001"], createdAt: 1 }, storage = new Map([[KEY, requestId], [KEY + ".payload", JSON.stringify(original)]]);
  const h = harness({ storage, snapshot: { busy: true } }); await h.ready(); await h.poll(); assert.equal(h.button("继续原请求").disabled, true); h.snapshot.busy = false; await h.poll(); assert.equal(h.button("继续原请求").disabled, false); assert.equal(h.posts().length, 0);
});
await test("typing before change guards reload and late autosave cannot discard or submit it", async () => {
  const delayed = deferred(); let writes = 0; const h = harness({ hook(call) { if (call.url === BASE + "/config" && ++writes === 1) return delayed.promise; } }); await h.ready(); await h.open(); await h.change("subtitle", "first edit"); const input = h.fields("notes")[0]; input.value = "still typing"; input.dispatch("input"); await settle(); assert.equal(h.api.hasDraft(), true); assert.equal(h.api.canReload(), false); h.snapshot.settings = h.posts("/config")[0].body.settings; h.snapshot.settingsSha = settingsSha(h.snapshot.settings); delayed.resolve(response(configReceipt(h.snapshot.settings))); await settle(); assert.equal(h.posts("/config").length, 1); assert.equal(h.fields("notes")[0], input); assert.equal(input.value, "still typing"); input.dispatch("change"); await settle(); assert.equal(h.posts("/config").length, 2); assert.equal(h.posts("/config")[1].body.settings.naming.notes, "still typing"); assert.equal(h.api.hasDraft(), false);
});
await test("real host precedes Console subnav and remains inside the workspace module", async () => {
  const host = index.indexOf('id="consoleRepositoryPublishHost"'), subnav = index.indexOf('class="console-subnav"'), panel = index.lastIndexOf('data-module-panel="workspace"', host);
  assert.ok(host >= 0 && panel >= 0 && panel < host && host < subnav); assert.equal((index.match(/id="consoleRepositoryPublishHost"/g) || []).length, 1);
});
await test("arrow shows five dynamic GitHub names and current versions without forms or mutations", async () => {
  const names = ["RandomRealm2", "Builder6", "CodexControlConsole", "MyWeb", "MyGitHub"], repos = names.map((name, i) => repository({ id: `repository-${i + 1}`, path: `D:/Unrelated/Folder${i}`, name: `Wrong path title ${i}`, repositoryUrl: i === 4 ? "git@github.com:owner/MyGitHub.git" : `https://github.com/owner/${name}.git`, versionSources: [{ path: "package.json", kind: "json", key: "version" }] }));
  const h = harness({ snapshot: { settings: settings(repos) }, catalog: { repositories: repos.map((repo, i) => ({ repoId: repo.id, components: [component({ currentVersion: `1.0.${i}`, nextVersion: `1.0.${i + 1}` })] })) } }); await h.ready();
  assert.equal(h.byClass("repository-publish-primary").textContent, "推送到 GitHub"); assert.equal(h.byClass("repository-publish-expanded").hidden, true); assert.equal(h.calls.length, 1); assert.equal(h.fields("path").length, 0);
  await h.expand(); const rows = h.byClass("repository-publish-compact-rows").children; assert.equal(rows.length, 5); assert.deepEqual(rows.map(row => row.children[0].textContent), names); assert.deepEqual(rows.map(row => h.byClass("repository-publish-compact-version", row).textContent), names.map((_, i) => `1.0.${i}`));
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
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "Unity 0.1 → 0.1.1");
  assert.deepEqual(h.all(h.byClass("repository-publish-version-menu")).filter(item => item.dataset.sourceId).map(item => item.textContent), ["Unity 0.1 → 0.1.1", "Blender (1, 2, 3) → (1, 2, 4)", "Other 2.3.4"]);
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
  assert.equal(h.byClass("repository-publish-plan-action"), undefined); assert.equal(h.byClass("repository-publish-compact-version").textContent, "正在读取…"); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown"); assert.equal(h.calls.filter(call => call.url.endsWith("/versions")).length, 2);
  delayed.resolve(response(old)); await settle(); assert.equal(h.calls.filter(call => call.url.endsWith("/versions")).length, 3); assert.equal(h.byClass("repository-publish-compact-version").textContent, "4.0.0"); h.byClass("repository-publish-plan-action").click(); await settle(); assert.equal(h.posts("/config").at(-1).body.settings.repositories[0].versionPlans[0].sourceId, "new-source"); assert.equal(h.posts("/run").length, 0);
});
await test("backend noop is no changes and solid dialog and theme-aware primary colors remain explicit", async () => {
  const h = harness({ snapshot: { operation: operation(randomUUID(), "success", [{ repoId: "repository-001", status: "noop" }]) } }); await h.ready(); await h.expand(); assert.equal(h.byClass("repository-publish-compact-status").textContent, "无改动"); h.locale("en"); assert.equal(h.byClass("repository-publish-compact-status").textContent, "No changes");
  assert.match(css, /\.repository-publish-dialog\s*\{[^}]*background:\s*var\(--solid-popover-bg,/); assert.match(css, /\.repository-publish-bar \.repository-publish-primary\s*\{[^}]*color:\s*var\(--bg,[^}]*background:\s*var\(--status-success,/); assert.equal(h.posts().length, 0);
});
await test("compact version colors follow real worktree or outgoing state, never a version plan", async () => {
  const first = component(), repos = [repository({ versionPlans: [planFor(first)] }), repository({ id: "repository-002", path: "D:/Second" }), repository({ id: "repository-003", path: "D:/Third" }), repository({ id: "repository-004", path: "D:/Fourth" })];
  const rows = [
    { repoId: repos[0].id, hasChanges: false, changeState: "unchanged", components: [first] },
    { repoId: repos[1].id, hasChanges: true, changeState: "changed", worktreeChanged: true, outgoingCommits: 0, components: [component()] },
    { repoId: repos[2].id, hasChanges: true, changeState: "changed", worktreeChanged: false, outgoingCommits: 2, components: [component()] },
    { repoId: repos[3].id, hasChanges: null, changeState: "unknown", changesReason: "No trustworthy tracking ref", components: [component()] }
  ];
  const h = harness({ snapshot: { settings: settings(repos) }, catalog: { repositories: rows } }); await h.ready(); await h.expand();
  const visible = h.byClass("repository-publish-compact-rows").children;
  assert.deepEqual(visible.map(row => h.byClass("repository-publish-compact-version", row).dataset.changeState), ["unchanged", "changed", "changed", "unknown"]);
  assert.match(h.byClass("repository-publish-compact-version", visible[0]).textContent, /2\.3\.4 → 2\.3\.5/);
  assert.equal(h.byClass("repository-publish-compact-version", visible[1]).textContent, "2.3.4"); assert.equal(h.byClass("repository-publish-compact-version", visible[2]).textContent, "2.3.4");
  assert.equal(visible[2].children[2].textContent, "有提交待推送"); assert.equal(visible[3].children[2].textContent, "变化未核对");
  assert.match(h.byClass("repository-publish-compact-version", visible[3]).title, /No trustworthy tracking ref/); assert.equal(h.posts().length, 0);
  const colors = [...css.matchAll(/--repository-publish-change:\s*#([0-9a-f]{6})/gi)].map(match => match[1]);
  assert.equal(colors.length, 2);
  for (const color of colors) { const channels = color.match(/../g).map(value => Number.parseInt(value, 16)); assert.ok(channels[1] > channels[0] && channels[1] > channels[2], "Both actual theme change colors must be green, not the desktop dark blue --green alias"); }
  assert.match(css, /\.repository-publish-compact-version\s*\{[^}]*color:\s*var\(--text,/);
  assert.match(css, /compact-version\[data-change-state="changed"\][^}]*var\(--repository-publish-change,/);
  assert.match(css, /data-change-state="unknown"[^}]*var\(--status-warning,/);
});
await test("unknown or contradictory change receipts cannot appear as clean white", async () => {
  for (const row of [{}, { hasChanges: false, changeState: "changed" }, { hasChanges: true, changeState: "unchanged" }, { hasChanges: null, changeState: "unchanged" }]) {
    const h = harness({ catalog: { repositories: [{ repoId: "repository-001", components: [component()], ...row, hasChanges: row.hasChanges, changeState: row.changeState }] } });
    await h.ready(); await h.expand(); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown"); assert.equal(h.byClass("repository-publish-compact-status").textContent, "变化未核对");
  }
});
await test("Summary uses real HEAD-to-working changes and keeps unselected next versions outside the transition", async () => {
  const changed = component({ currentVersion: "1.6.44", headVersion: "1.6.43", nextVersion: "1.6.45", versionChanged: true,
    transition: { kind: "working", fromVersion: "1.6.43", toVersion: "1.6.44" } });
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", components: [changed] }] } });
  await h.ready(); await h.expand(); assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.6.43 → 1.6.44"); await h.open();
  assert.equal(h.byClass("repository-publish-plan-row").children[0].textContent, "1.6.43 → 1.6.44"); assert.match(h.byClass("repository-publish-plan-row").children[2].textContent, /已修改版本/); assert.equal(h.posts().length, 0);
  const unchanged = harness({ catalog: { repositories: [{ repoId: "repository-001", components: [component()] }] } }); await unchanged.ready(); await unchanged.open();
  assert.equal(unchanged.byClass("repository-publish-plan-row").children[0].textContent, "2.3.4"); assert.match(unchanged.byClass("repository-publish-plan-row").children[2].textContent, /本次保留当前版本.*可选下一版 2\.3\.5/); assert.equal(unchanged.posts().length, 0);
});
await test("missing or stale actual version reads never reuse the plan's old current number", async () => {
  const planned = component(), repo = repository({ versionPlans: [planFor(planned)] });
  const failed = harness({ snapshot: { settings: settings([repo]) }, hook(call) { if (call.url === BASE + "/versions") throw new Error("read unavailable"); } });
  await failed.ready(); await failed.open(); assert.match(failed.byClass("repository-publish-compact-version").textContent, /读取失败/); assert.doesNotMatch(failed.byClass("repository-publish-compact-version").textContent, /2\.3\.4/);
  assert.equal(failed.byClass("repository-publish-compact-version").dataset.changeState, "unknown"); assert.match(failed.byClass("repository-publish-plan-row").children[0].textContent, /计划待核对.*计划目标 2\.3\.5/);
  const stale = harness({ snapshot: { settings: settings([repo]) }, catalog: { repositories: [{ repoId: repo.id, components: [component({ currentVersion: "4.0.7", nextVersion: "4.0.8", planState: "stale", plannedVersion: "", transition: null })] }] } });
  await stale.ready(); await stale.open(); assert.equal(stale.byClass("repository-publish-compact-version").textContent, "4.0.7"); assert.equal(stale.byClass("repository-publish-plan-row").children[0].textContent, "4.0.7"); assert.match(stale.byClass("repository-publish-plan-row").children[2].textContent, /计划待核对/); assert.equal(stale.posts().length, 0);
});
await test("99 rollover and independent module formats are displayed only from backend targets", async () => {
  const components = [component({ currentVersion: "1.6.99", nextVersion: "1.7.0", name: "Console" }),
    component({ sourceId: "second-source", currentVersion: "(1, 99, 99)", nextVersion: "(2, 0, 0)", name: "Plugin" })];
  const h = harness({ snapshot: { settings: settings([repository({ versionPlans: components.map(planFor) })]) }, catalog: { repositories: [{ repoId: "repository-001", components }] } });
  await h.ready(); await h.open(); assert.equal(h.byClass("repository-publish-compact-version").textContent, "Console 1.6.99 → 1.7.0");
  assert.deepEqual(h.all(h.byClass("repository-publish-version-menu")).filter(item => item.dataset.sourceId).map(item => item.textContent), ["Console 1.6.99 → 1.7.0", "Plugin (1, 99, 99) → (2, 0, 0)"]);
  assert.equal(h.posts().length, 0); h.byClass("repository-publish-primary").click(); await settle(); assert.equal(h.posts("/run").length, 1);
  assert.deepEqual(Object.keys(h.posts("/run")[0].body).sort(), ["repoIds", "requestId"]); assert.equal(h.posts("/config").length, 0);
});
await test("a completed unplanned push rereads actual dirty state once without a repeated run", async () => {
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", components: [component()] }] } });
  await h.ready(); await h.expand(); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "changed");
  h.byClass("repository-publish-primary").click(); await settle(); const id = h.posts("/run")[0].body.requestId;
  h.catalog.repositories[0].hasChanges = false; h.catalog.repositories[0].changeState = "unchanged"; h.snapshot.operation = operation(id, "success", [{ repoId: "repository-001", status: "success" }]);
  await h.poll(); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unchanged"); assert.equal(h.calls.filter(call => call.url.endsWith("/versions")).length, 2); assert.equal(h.posts("/run").length, 1); assert.equal(h.posts("/config").length, 0);
});
await test("git commit version source exposes fixed HEAD and subject, never an arbitrary command", async () => {
  const source = { path: "ProjectSettings/ProjectSettings.asset", kind: "unity", key: "bundleVersion", name: "Game", scope: "" };
  const h = harness({ snapshot: { settings: settings([repository({ versionSources: [source] })]) } }); await h.ready(); await h.open();
  await h.change("kind", "git_commit"); const saved = h.posts("/config").at(-1).body.settings.repositories[0].versionSources[0];
  assert.equal(saved.path, "HEAD"); assert.equal(saved.key, "subject"); assert.equal(saved.kind, "git_commit"); assert.equal(h.posts("/run").length, 0);
  assert.equal(h.fields("versionPath")[0].readOnly, true); assert.equal(h.fields("key")[0].readOnly, true); assert.match(h.byClass("repository-publish-version-origin").textContent, /来自提交记录，不修改版本文件/);
  await h.change("key", "arbitrary regex or command"); assert.equal(h.posts("/config").at(-1).body.settings.repositories[0].versionSources[0].key, "subject");
  h.locale("en"); assert.match(h.byClass("repository-publish-version-origin").textContent, /commit history; no version file/);
});
await test("git-only plan Summary uses the authoritative commit version and has no Unity replacement", async () => {
  const committed = component({ path: "HEAD", kind: "git_commit", key: "subject", currentVersion: "1.6.43", nextVersion: "1.6.44", headVersion: "1.6.43", sourceHeadSha: "c".repeat(40), versionCommitSha: "d".repeat(40) });
  const h = harness({ snapshot: { settings: settings([repository({ versionSources: [{ path: "HEAD", kind: "git_commit", key: "subject", name: "Game", scope: "" }], versionPlans: [planFor(committed)] })]) }, catalog: { repositories: [{ repoId: "repository-001", components: [committed] }] } });
  await h.ready(); await h.open(); assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.6.43 → 1.6.44"); assert.match(h.byClass("repository-publish-plan-row").children[2].textContent, /已计划.*不修改版本文件/);
  assert.doesNotMatch(h.byClass("repository-publish-plan-row").children[0].textContent, /0\.1\.0/); assert.equal(h.posts().length, 0);
});
await test("preview Summary only shows targets actually selected for this commit, retaining push-only plans", async () => {
  const item = component({ path: "HEAD", kind: "git_commit", key: "subject", currentVersion: "1.6.43", nextVersion: "1.6.44", planState: "valid", plannedVersion: "1.6.44", transition: { kind: "planned", fromVersion: "1.6.43", toVersion: "1.6.44" } });
  for (const [action, planWillApply, expected, hint] of [["commit", true, "1.6.43 → 1.6.44", "已计划"], ["push_only", false, "1.6.43", "计划保留"], ["noop", false, "1.6.43", "计划保留"], ["sync_pending", null, "1.6.43", "同步后再核对"], ["unknown", null, "1.6.43", "执行待核对"]]) {
    const h = harness({ snapshot: { settings: settings([repository({ versionPlans: [planFor(item)] })]) }, catalog: { repositories: [{ repoId: "repository-001", components: [item] }] }, hook(call) {
      if (call.url === BASE + "/preview") return response({ previews: [{ repoId: "repository-001", action, planWillApply, title: action === "push_only" ? "Original committed title" : "Prepared commit title", body: "Saved file changes only", components: [item] }] });
    } });
    await h.ready(); await h.open(); h.button("预览标题与改动").click(); await settle();
    const row = h.byClass("repository-publish-preview-version"); assert.equal(row.textContent, expected); assert.match(row.children[0].textContent, new RegExp(hint));
    if (action === "push_only") assert.match(h.byClass("repository-publish-preview").children[0].children[2].textContent, /Original committed title/);
    assert.equal(h.posts("/run").length, 0); assert.equal(h.posts("/config").length, 0);
  }
});
await test("an old preview cannot fill a newly selected repository's Summary", async () => {
  const delayed = deferred(), repos = [repository(), repository({ id: "repository-002", path: "D:/Second" })];
  const h = harness({ snapshot: { settings: settings(repos) }, hook(call) { if (call.url === BASE + "/preview") return delayed.promise; } });
  await h.ready(); await h.open("repository-001"); h.button("预览标题与改动").click(); await settle(); await h.open("repository-002");
  delayed.resolve(response({ previews: [{ repoId: "repository-001", title: "Old unrelated Summary", components: [component()] }] })); await settle();
  assert.equal(h.byClass("repository-publish-preview").children.length, 0); assert.doesNotMatch(h.all().map(item => item.textContent).join(" "), /Old unrelated Summary/); assert.equal(h.posts("/run").length, 0);
});
await test("branch and exclusion changes reject a late dirty-state catalog", async () => {
  for (const [field, value] of [["branch", "feature/new"], ["excludes", "private/**"], ["autoBump", false]]) {
    const delayed = deferred(); let reads = 0;
    const old = { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", components: [component({ currentVersion: "1.0.5", nextVersion: "1.0.6" })] }] };
    const fresh = { repositories: [{ repoId: "repository-001", hasChanges: false, changeState: "unchanged", components: [component({ currentVersion: "2.0.7", nextVersion: "2.0.8" })] }] };
    const h = harness({ hook(call) { if (call.url === BASE + "/versions") return ++reads === 1 ? response(old) : reads === 2 ? delayed.promise : response(fresh); } });
    await h.ready(); await h.expand(); await h.open(); await h.change(field, value);
    assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown");
    delayed.resolve(response(old)); await settle(); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.0.7"); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unchanged"); assert.equal(h.posts("/run").length, 0);
  }
});
await test("a planned transition flag alone cannot show a mismatched current or target", async () => {
  for (const patch of [{ fromVersion: "9.9.9" }, { toVersion: "9.9.9" }]) {
    const item = component({ planState: "valid", plannedVersion: "2.3.5", transition: { kind: "planned", fromVersion: "2.3.4", toVersion: "2.3.5", ...patch } });
    const h = harness({ snapshot: { settings: settings([repository({ versionPlans: [planFor(item)] })]) }, catalog: { repositories: [{ repoId: "repository-001", components: [item] }] } });
    await h.ready(); await h.open(); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.equal(h.byClass("repository-publish-plan-row").children[0].textContent, "2.3.4"); assert.match(h.byClass("repository-publish-plan-row").children[2].textContent, /计划待核对/); assert.equal(h.posts().length, 0);
  }
});
await test("an authoritative source error does not erase a real pending-change signal", async () => {
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: true, outgoingCommits: 0, message: "Version source is missing", components: [] }] } });
  await h.ready(); await h.expand(); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "changed"); assert.match(h.byClass("repository-publish-compact-version").textContent, /版本读取失败/); assert.match(h.byClass("repository-publish-compact-version").title, /Version source is missing/); assert.equal(h.posts().length, 0);
});
await test("automatic bump defaults on and the saved checkbox can turn it off without running", async () => {
  const initial = settings(); delete initial.naming.autoBump;
  const auto = automaticComponent(), h = harness({ snapshot: { settings: initial }, catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: true, outgoingCommits: 0, components: [auto] }] } });
  await h.ready(); await h.open(); assert.equal(h.fields("autoBump")[0].checked, true); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4 → 2.3.5");
  await h.change("autoBump", false); assert.equal(h.posts("/config").at(-1).body.settings.naming.autoBump, false); assert.equal(h.fields("autoBump")[0].checked, false);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "changed"); assert.equal(h.posts("/run").length, 0);
});
await test("actual automatic candidates show a checked current-to-target Summary without creating a client plan", async () => {
  const auto = automaticComponent({ currentVersion: "1.6.99", nextVersion: "1.7.0" });
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: true, outgoingCommits: 0, components: [auto] }] }, hook(call) {
    if (call.url === BASE + "/preview") return response({ previews: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: true, action: "commit", planWillApply: true, title: "1.6.99 → 1.7.0", components: [auto] }] });
  } });
  await h.ready(); await h.open(); assert.equal(h.byClass("repository-publish-plan-row").children[0].textContent, "1.6.99 → 1.7.0"); assert.match(h.byClass("repository-publish-plan-row").children[2].textContent, /自动升版，提交时复核/);
  h.button("预览标题与改动").click(); await settle(); const row = h.byClass("repository-publish-preview-version"); assert.equal(row.textContent, "1.6.99 → 1.7.0"); assert.equal(row.dataset.transition, "auto"); assert.match(row.children[0].textContent, /自动升版/);
  assert.equal(h.posts("/config").length, 0); assert.equal(h.posts("/run").length, 0); assert.deepEqual(h.snapshot.settings.repositories[0].versionPlans || [], []);
});
await test("manual or initial versions and push-only commits never receive an extra automatic bump", async () => {
  const manual = component({ currentVersion: "2.3.5", nextVersion: "2.3.6", headVersion: "2.3.4", versionChanged: true, worktreeChanged: true, autoPlan: { state: "manual_version", fromVersion: "", targetVersion: "", reason: "Version already changed" }, transition: { kind: "working", fromVersion: "2.3.4", toVersion: "2.3.5" } });
  for (const [item, worktree, outgoing, expected] of [[manual, true, 0, "2.3.4 → 2.3.5"], [component({ autoPlan: { state: "initial_version", fromVersion: "", targetVersion: "", reason: "First version" } }), true, 0, "2.3.4"], [component({ autoPlan: { state: "none", fromVersion: "", targetVersion: "", reason: "Only existing commits" } }), false, 2, "2.3.4"]]) {
    const action = worktree ? "commit" : "push_only", h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: worktree, outgoingCommits: outgoing, components: [item] }] }, hook(call) {
      if (call.url === BASE + "/preview") return response({ previews: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: worktree, outgoingCommits: outgoing, action, planWillApply: false, title: "Original progress", components: [item] }] });
    } });
    await h.ready(); await h.open(); assert.equal(h.byClass("repository-publish-compact-version").textContent, expected); h.button("预览标题与改动").click(); await settle(); assert.equal(h.byClass("repository-publish-preview-version").textContent, expected); assert.equal(h.posts("/config").length, 0); assert.equal(h.posts("/run").length, 0);
  }
});
await test("automatic eligibility alone cannot replace real scoped changes or matching authority values", async () => {
  for (const patch of [{ worktreeChanged: false }, { autoPlan: { state: "eligible", fromVersion: "9.9.9", targetVersion: "2.3.5" } }, { autoPlan: { state: "eligible", fromVersion: "2.3.4", targetVersion: "9.9.9" } }, { canBump: false }]) {
    const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: true, components: [automaticComponent(patch)] }] } }); await h.ready(); await h.open(); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.equal(h.posts().length, 0);
  }
  for (const [hasChanges, changeState] of [[false, "unchanged"], [null, "unknown"]]) {
    const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges, changeState, worktreeChanged: false, components: [automaticComponent()] }] } }); await h.ready(); await h.open(); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.equal(h.posts().length, 0);
  }
});
await test("saved work sync differences stay green without claiming an applied version transition", async () => {
  const item = component({ autoPlan: { state: "sync_pending", fromVersion: "2.3.4", targetVersion: "", reason: "Saved sync must finish first" } });
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: false, outgoingCommits: 0, syncChanged: true, syncState: "changed", components: [item] }] }, hook(call) {
    if (call.url === BASE + "/preview") return response({ previews: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: false, syncChanged: true, action: "sync_pending", planWillApply: null, title: "Saved work awaiting sync", components: [item] }] });
  } });
  await h.ready(); await h.open(); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "changed"); assert.equal(h.byClass("repository-publish-compact-status").textContent, "有工作文件待同步"); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4");
  h.button("预览标题与改动").click(); await settle(); assert.equal(h.byClass("repository-publish-preview-version").textContent, "2.3.4"); assert.equal(h.posts("/config").length, 0); assert.equal(h.posts("/run").length, 0);
});
await test("confirmed missing authority shows fallback naming while failed authority remains an error", async () => {
  for (const [versionState, expected] of [["missing", "无版本 · 备用标题"], ["unknown", "版本读取失败"]]) {
    const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", versionState, message: "No readable authoritative version", components: [] }] }, hook(call) {
      if (call.url === BASE + "/preview") return response({ previews: [{ repoId: "repository-001", versionState, title: "更新进度 2026-10-12 23:00", body: "Modified Build.blend", components: [] }] });
    } });
    await h.ready(); await h.open(); assert.equal(h.byClass("repository-publish-compact-version").textContent, expected); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "changed");
    h.button("预览标题与改动").click(); await settle(); if (versionState === "missing") assert.equal(h.byClass("repository-publish-preview-version").textContent, expected);
    assert.equal(h.posts("/config").length, 0); assert.equal(h.posts("/run").length, 0);
  }
});
await test("configuration CAS conflict keeps drafts and requires explicit reread instead of overwriting", async () => {
  const h = harness(); await h.ready(); await h.open(); const before = h.snapshot.settingsSha;
  h.snapshot.settings.naming.notes = "Saved in another window"; h.snapshot.settingsSha = settingsSha(h.snapshot.settings);
  h.hook(call => {
    if (call.url === BASE + "/config" && call.body.expectedSettingsSha !== h.snapshot.settingsSha) return { ok: false, status: 409, json: async () => ({ code: "settings_changed" }) };
  });
  await h.change("notes", "This window's protected draft"); assert.equal(h.posts("/config")[0].body.expectedSettingsSha, before);
  assert.equal(h.fields("notes")[0].value, "This window's protected draft"); assert.equal(h.api.hasDraft(), true); assert.match(h.byClass("repository-publish-status").textContent, /另一处.*草稿保留/);
  await h.change("subtitle", "More local draft"); assert.equal(h.posts("/config").length, 1, "Do not retry against a newer baseline automatically");
  await h.api.refresh(); await settle(); assert.equal(h.fields("notes")[0].value, "This window's protected draft"); assert.equal(h.posts("/config").length, 1);
  h.button("重新读取配置（放弃此配置草稿）").click(); await settle(); assert.equal(h.api.hasDraft(), false); assert.equal(h.fields("notes")[0].value, "Saved in another window");
  const reviewedSha = h.snapshot.settingsSha; await h.change("notes", "New reviewed configuration"); assert.equal(h.posts("/config").length, 2); assert.equal(h.posts("/config")[1].body.expectedSettingsSha, reviewedSha);
  assert.equal(h.posts("/run").length, 0);
});
await test("missing settings proof cannot save and ambiguous acknowledgments preserve the draft", async () => {
  const missing = harness({ snapshot: { settingsSha: undefined } }); await missing.ready(); assert.equal(missing.byClass("repository-publish-primary").disabled, true); assert.match(missing.byClass("repository-publish-status").textContent, /读取失败/); assert.equal(missing.posts().length, 0);
  const h = harness({ hook(call) { if (call.url === BASE + "/config") return response({ settings: call.body.settings }); } });
  await h.ready(); await h.open(); await h.change("notes", "Receipt remains unconfirmed"); assert.equal(h.api.hasDraft(), true); assert.equal(h.fields("notes")[0].value, "Receipt remains unconfirmed"); assert.match(h.byClass("repository-publish-status").textContent, /未保存/); assert.equal(h.posts("/config").length, 1); assert.equal(h.posts("/run").length, 0);
});
await test("returning focus or pageshow rereads an expanded Console after external saved changes without polling or writes", async () => {
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", components: [component()] }] } });
  await h.ready(); await h.expand(); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unchanged");
  h.catalog.repositories[0] = { repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: true, outgoingCommits: 0, components: [automaticComponent()] };
  const initial = h.calls.length; await h.emitWindow("focus"); assert.equal(h.calls.length, initial + 2); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "changed"); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4 → 2.3.5");
  h.catalog.repositories[0] = { repoId: "repository-001", components: [component()] }; await h.emitWindow("pageshow"); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unchanged"); assert.equal(h.posts().length, 0); assert.equal(h.timers.size, 0, "No recurring monitor is started");
});
await test("hidden or collapsed Console never refreshes on return, while becoming visible refreshes and cleanup removes hooks", async () => {
  const h = harness(); await h.ready(); let reads = h.calls.length;
  await h.emitWindow("focus"); await h.emitWindow("pageshow"); assert.equal(h.calls.length, reads, "Collapsed stays idle");
  await h.expand(); await h.setPanelHidden(true); reads = h.calls.length;
  await h.emitWindow("focus"); await h.emitWindow("pageshow"); assert.equal(h.calls.length, reads, "Other modules trigger no new requests");
  h.catalog.repositories[0].hasChanges = true; h.catalog.repositories[0].changeState = "changed"; h.catalog.repositories[0].worktreeChanged = true;
  await h.setPanelHidden(false); assert.equal(h.calls.length, reads + 2); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "changed");
  const api = h.api; api.destroy(); reads = h.calls.length; await h.emitWindow("focus"); await h.emitWindow("pageshow"); await h.setPanelHidden(true); await h.setPanelHidden(false); assert.equal(h.calls.length, reads); assert.equal(h.posts().length, 0);
});
await test("return refresh preserves dirty drafts, serial autosave and active publishing guards", async () => {
  const draft = harness(); await draft.ready(); await draft.open(); const input = draft.fields("notes")[0]; input.value = "Protected typing"; input.dispatch("input"); let before = draft.calls.length;
  await draft.emitWindow("focus"); await draft.emitWindow("pageshow"); await draft.setPanelHidden(true); await draft.setPanelHidden(false); assert.equal(draft.calls.length, before); assert.equal(input.value, "Protected typing"); assert.equal(draft.api.hasDraft(), true); assert.equal(draft.posts().length, 0);
  const pending = deferred(), saving = harness({ hook(call) { if (call.url === BASE + "/config") return pending.promise; } }); await saving.ready(); await saving.open(); await saving.change("notes", "Serial save"); before = saving.calls.length;
  await saving.emitWindow("focus"); await saving.emitWindow("pageshow"); assert.equal(saving.calls.length, before); pending.reject(new Error("Fixture save remains unsaved")); await settle();
  const active = harness(); await active.ready(); await active.expand(); active.byClass("repository-publish-primary").click(); await settle(); before = active.calls.length;
  await active.emitWindow("focus"); await active.emitWindow("pageshow"); await active.setPanelHidden(true); await active.setPanelHidden(false); assert.equal(active.calls.length, before); assert.equal(active.posts("/run").length, 1);
});
await test("a late return catalog cannot repaint a hidden Console or supersede its fresh visible recheck", async () => {
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", components: [component()] }] } }); await h.ready(); await h.expand();
  const pending = deferred(); h.hook(call => call.url === BASE + "/versions" ? pending.promise : undefined); await h.emitWindow("focus"); await h.setPanelHidden(true); const before = h.calls.length;
  pending.resolve(response({ repositories: [{ repoId: "repository-001", hasChanges: false, changeState: "unchanged", components: [component({ currentVersion: "9.9.9" })] }] })); await settle(); assert.equal(h.calls.length, before); assert.notEqual(h.byClass("repository-publish-compact-version").textContent, "9.9.9");
  h.hook(null); h.catalog.repositories[0] = { repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: true, components: [component({ currentVersion: "3.0.1" })] };
  await h.setPanelHidden(false); assert.equal(h.byClass("repository-publish-compact-version").textContent, "3.0.1"); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "changed"); assert.equal(h.posts().length, 0);
});
const menuComponents = () => [component({ sourceId: "idle-plugin", name: "Node library", currentVersion: "0.3.1", nextVersion: "0.3.2" }),
  automaticComponent({ sourceId: "changed-plugin", name: "Character Designer", currentVersion: "0.77.25", nextVersion: "0.77.38" }),
  component({ sourceId: "other-plugin", name: "RR Helper", currentVersion: "0.2.60", nextVersion: "0.2.61" })];
const menuCatalog = (repoId = "repository-001", components = menuComponents()) => ({ repoId, hasChanges: true, changeState: "changed", worktreeChanged: true, outgoingCommits: 0, components });
const rowFor = (h, id = "repository-001") => h.byClass("repository-publish-compact-rows").children.find(row => row.dataset.repoId === id);
const menuOptions = (h, row = rowFor(h)) => h.all(h.byClass("repository-publish-version-menu", row)).filter(item => item.dataset.sourceId);
await test("multiple versions remain compact and expose fact-based changed and other groups on demand", async () => {
  const h = harness({ catalog: { repositories: [menuCatalog()] } }); await h.ready(); await h.expand();
  const picker = h.byClass("repository-publish-version-picker"), trigger = h.byClass("repository-publish-version-trigger");
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "Character Designer 0.77.25 → 0.77.38");
  assert.equal(h.byClass("repository-publish-version-count").textContent, "3 个插件"); assert.equal(picker.open, false);
  assert.equal(h.visible(menuOptions(h)[0]), false); assert.equal(h.fields("path").length, 0);
  trigger.click(); assert.equal(picker.open, true); assert.equal(h.visible(menuOptions(h)[0]), true);
  const menu = h.byClass("repository-publish-version-menu"), groups = h.all(menu).filter(item => item.tagName === "H4").map(item => item.textContent);
  assert.deepEqual(groups, ["本次有改动", "其他插件"]); assert.equal(h.all(menu).filter(item => item.tagName === "HR").length, 2);
  assert.deepEqual(menuOptions(h).map(item => [item.dataset.sourceId, item.dataset.changeState]), [["changed-plugin", "changed"], ["idle-plugin", "unchanged"], ["other-plugin", "unchanged"]]);
  assert.match(trigger.getAttribute("aria-label"), /选择显示的插件版本.*Character Designer.*3 个插件/);
  assert.equal(h.posts().length, 0); assert.equal(h.api.hasDraft(), false);
});
await test("choosing a plugin changes display and focus only while real repository changes remain visible", async () => {
  const h = harness({ catalog: { repositories: [menuCatalog()] } }); await h.ready(); await h.expand();
  const reads = h.calls.length, settingsBefore = structuredClone(h.snapshot.settings), trigger = h.byClass("repository-publish-version-trigger"); trigger.click();
  menuOptions(h).find(item => item.dataset.sourceId === "idle-plugin").click(); await settle();
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "Node library 0.3.1");
  assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unchanged");
  assert.equal(h.byClass("repository-publish-compact-status").dataset.changeState, "changed"); assert.equal(h.byClass("repository-publish-compact-status").textContent, "有待提交改动");
  assert.equal(h.byClass("repository-publish-version-picker").open, false); assert.equal(h.document.activeElement, trigger);
  assert.equal(menuOptions(h).find(item => item.dataset.sourceId === "idle-plugin").getAttribute("aria-pressed"), "true");
  assert.equal(h.calls.length, reads); assert.equal(h.posts().length, 0); assert.deepEqual(h.snapshot.settings, settingsBefore);
  assert.equal(h.api.hasDraft(), false); assert.equal(h.api.canReload(), true); assert.equal(h.byClass("repository-publish-primary").disabled, false);
  assert.ok(Object.values(JSON.parse(h.storage.get(DISPLAY_KEY))).includes("idle-plugin"));
  h.button("自动显示有改动的插件").click(); await settle(); assert.equal(h.byClass("repository-publish-compact-version").textContent, "Character Designer 0.77.25 → 0.77.38");
  assert.equal(Object.values(JSON.parse(h.storage.get(DISPLAY_KEY))).includes("idle-plugin"), false); assert.equal(h.posts().length, 0);
});
await test("reload preserves the chosen source while using its freshly read version and one-time plan consumption", async () => {
  const storage = new Map(), first = harness({ storage, catalog: { repositories: [menuCatalog()] } }); await first.ready(); await first.expand();
  menuOptions(first).find(item => item.dataset.sourceId === "idle-plugin").click(); first.api.destroy();
  const components = menuComponents(); components[0] = component({ ...components[0], currentVersion: "0.3.2", nextVersion: "0.3.3", worktreeChanged: true });
  const h = harness({ storage, snapshot: { settings: settings([repository({ versionPlans: [planFor(components[1])] })]) }, catalog: { repositories: [menuCatalog("repository-001", components)] } });
  await h.ready(); await h.expand(); assert.equal(h.byClass("repository-publish-compact-version").textContent, "Node library 0.3.2");
  h.snapshot.settings.repositories[0].versionPlans = []; h.snapshot.settingsSha = settingsSha(h.snapshot.settings); await h.emitWindow("focus");
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "Node library 0.3.2"); assert.equal(h.posts().length, 0);
  assert.equal(h.api.hasDraft(), false); assert.equal(h.api.canReload(), true);
});
await test("display choices stay isolated by repository and actual branch binding", async () => {
  const repos = [repository(), repository({ id: "repository-002", path: "D:/Other", repositoryUrl: "https://github.com/example/Other", branch: "feature/other" })];
  const h = harness({ snapshot: { settings: settings(repos) }, catalog: { repositories: repos.map(repo => menuCatalog(repo.id)) } }); await h.ready(); await h.expand();
  menuOptions(h, rowFor(h, repos[0].id)).find(item => item.dataset.sourceId === "idle-plugin").click();
  assert.equal(h.byClass("repository-publish-compact-version", rowFor(h, repos[0].id)).textContent, "Node library 0.3.1");
  assert.equal(h.byClass("repository-publish-compact-version", rowFor(h, repos[1].id)).textContent, "Character Designer 0.77.25 → 0.77.38");
  menuOptions(h, rowFor(h, repos[1].id)).find(item => item.dataset.sourceId === "other-plugin").click();
  const values = Object.values(JSON.parse(h.storage.get(DISPLAY_KEY))); assert.deepEqual(values.sort(), ["idle-plugin", "other-plugin"]); assert.equal(h.posts().length, 0);
  await h.open(repos[0].id); await h.change("branch", "feature/new-bound-branch");
  assert.equal(h.byClass("repository-publish-compact-version", rowFor(h, repos[0].id)).textContent, "Character Designer 0.77.25 → 0.77.38");
  assert.equal(h.byClass("repository-publish-compact-version", rowFor(h, repos[1].id)).textContent, "RR Helper 0.2.60"); assert.equal(h.posts("/config").length, 1); assert.equal(h.posts("/run").length, 0);
});
await test("a removed source safely falls back without stale versions or phantom choices", async () => {
  const h = harness({ catalog: { repositories: [menuCatalog()] } }); await h.ready(); await h.expand();
  menuOptions(h).find(item => item.dataset.sourceId === "idle-plugin").click();
  h.catalog.repositories[0].components = menuComponents().filter(item => item.sourceId !== "idle-plugin"); await h.emitWindow("focus");
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "Character Designer 0.77.25 → 0.77.38"); assert.equal(h.byClass("repository-publish-version-count").textContent, "2 个插件");
  assert.equal(menuOptions(h).some(item => item.dataset.sourceId === "idle-plugin"), false); assert.equal(h.button("自动显示有改动的插件").getAttribute("aria-pressed"), "true");
  h.catalog.repositories[0].components = [component({ sourceId: "new-only", currentVersion: "4.0.7", nextVersion: "4.0.8" })]; await h.emitWindow("focus");
  assert.equal(h.byClass("repository-publish-version-picker").hidden, true); assert.equal(h.byClass("repository-publish-compact-version").textContent, "4.0.7"); assert.equal(h.visible(h.byClass("repository-publish-compact-version")), true);
  h.catalog.repositories[0].components = menuComponents(); await h.emitWindow("focus"); assert.equal(h.byClass("repository-publish-version-picker").hidden, false);
  assert.equal(h.all().filter(item => item.className.split(" ").includes("repository-publish-compact-version")).length, 1, "The native append contract moves rather than duplicates the version span"); assert.equal(h.posts().length, 0);
});
await test("unavailable display storage does not dirty configuration or disable normal controls", async () => {
  const h = harness({ storageUnavailable: true, catalog: { repositories: [menuCatalog()] } }); await h.ready(); await h.expand();
  const reads = h.calls.length; menuOptions(h).find(item => item.dataset.sourceId === "idle-plugin").click();
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "Node library 0.3.1"); assert.equal(h.byClass("repository-publish-primary").disabled, false);
  assert.equal(h.api.hasDraft(), false); assert.equal(h.api.canReload(), true); assert.equal(h.calls.length, reads); assert.equal(h.posts().length, 0);
  await h.emitWindow("focus"); assert.equal(h.byClass("repository-publish-compact-version").textContent, "Node library 0.3.1");
});
await test("locale changes update menu labels and count without changing the saved display choice", async () => {
  const h = harness({ catalog: { repositories: [menuCatalog()] } }); await h.ready(); await h.expand(); menuOptions(h).find(item => item.dataset.sourceId === "idle-plugin").click();
  const preference = h.storage.get(DISPLAY_KEY), reads = h.calls.length; h.byClass("repository-publish-version-trigger").click(); h.locale("en");
  assert.equal(h.byClass("repository-publish-version-count").textContent, "3 plugins"); assert.equal(h.byClass("repository-publish-version-picker").open, false);
  assert.deepEqual(h.all(h.byClass("repository-publish-version-menu")).filter(item => item.tagName === "H4").map(item => item.textContent), ["Changed plugins", "Other plugins"]);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "Node library 0.3.1"); assert.equal(h.storage.get(DISPLAY_KEY), preference); assert.equal(h.calls.length, reads); assert.equal(h.posts().length, 0);
});
await test("unknown component state remains marked unknown and is never described as an unchanged plugin", async () => {
  const unknown = component({ sourceId: "unknown-plugin", name: "Unknown", worktreeChanged: null, versionChanged: null }), other = component({ sourceId: "known-plugin", name: "Other", worktreeChanged: null, versionChanged: null });
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: null, changeState: "unknown", worktreeChanged: null, components: [unknown, other] }] } }); await h.ready(); await h.expand();
  assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown"); assert.equal(h.byClass("repository-publish-compact-status").textContent, "变化未核对");
  assert.deepEqual(menuOptions(h).map(item => item.dataset.changeState), ["unknown", "unknown"]);
  const labels = h.all(h.byClass("repository-publish-version-menu")).map(item => item.textContent).join(" "); assert.doesNotMatch(labels, /无改动|无变化|本次有改动/); assert.match(labels, /其他插件/); assert.equal(h.posts().length, 0);
});
await test("version menus close on Escape and outside click, retain focus, and opening another closes the first", async () => {
  const repos = [repository(), repository({ id: "repository-002", path: "D:/Other" })], h = harness({ snapshot: { settings: settings(repos) }, catalog: { repositories: repos.map(repo => menuCatalog(repo.id)) } }); await h.ready(); await h.expand();
  const first = h.byClass("repository-publish-version-picker", rowFor(h, repos[0].id)), second = h.byClass("repository-publish-version-picker", rowFor(h, repos[1].id));
  const trigger = h.byClass("repository-publish-version-trigger", rowFor(h, repos[0].id)); trigger.click(); assert.equal(first.open, true);
  const escaped = first.dispatch("keydown", { key: "Escape" }); assert.equal(escaped.defaultPrevented, true); assert.equal(first.open, false); assert.equal(h.document.activeElement, trigger);
  trigger.click(); h.document.emit("click", { target: h.byClass("repository-publish-version-menu", rowFor(h, repos[0].id)) }); assert.equal(first.open, true, "Inside clicks retain the current menu");
  h.document.emit("click", { target: h.host }); assert.equal(first.open, false);
  trigger.click(); h.byClass("repository-publish-version-trigger", rowFor(h, repos[1].id)).click(); assert.equal(first.open, false); assert.equal(second.open, true);
  h.api.destroy(); second.open = true; h.document.emit("click", { target: h.host }); assert.equal(second.open, true, "Destroy removes this component's document click hook"); assert.equal(h.posts().length, 0);
});
await test("refresh and hiding or collapsing Console close an old version menu without losing a valid choice", async () => {
  const h = harness({ catalog: { repositories: [menuCatalog()] } }); await h.ready(); await h.expand(); menuOptions(h).find(item => item.dataset.sourceId === "idle-plugin").click();
  const picker = h.byClass("repository-publish-version-picker"), trigger = h.byClass("repository-publish-version-trigger"), pending = deferred(); trigger.click();
  h.hook(call => call.url === BASE + "/versions" ? pending.promise : undefined); await h.emitWindow("focus"); assert.equal(picker.open, false); assert.equal(h.byClass("repository-publish-compact-version").textContent, "正在读取…");
  pending.resolve(response({ repositories: [menuCatalog()] })); await settle(); h.hook(null); assert.equal(h.byClass("repository-publish-compact-version").textContent, "Node library 0.3.1");
  trigger.click(); await h.setPanelHidden(true); assert.equal(picker.open, false); await h.setPanelHidden(false);
  trigger.click(); await h.expand(); assert.equal(picker.open, false); await h.expand(); assert.equal(picker.open, false);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "Node library 0.3.1"); assert.equal(h.posts().length, 0); assert.equal(h.api.hasDraft(), false);
});
await test("a stale menu event cannot choose a source while its catalog is refreshing or after that source disappears", async () => {
  const h = harness({ catalog: { repositories: [menuCatalog()] } }); await h.ready(); await h.expand();
  const staleOption = menuOptions(h).find(item => item.dataset.sourceId === "idle-plugin"), pending = deferred();
  h.hook(call => call.url === BASE + "/versions" ? pending.promise : undefined); await h.emitWindow("focus");
  staleOption.click(); assert.equal(h.storage.has(DISPLAY_KEY), false); assert.equal(h.byClass("repository-publish-compact-version").textContent, "正在读取…");
  const fresh = [automaticComponent({ sourceId: "replacement-changed", name: "Replacement", currentVersion: "4.0.7", nextVersion: "4.0.8" }), component({ sourceId: "replacement-idle", name: "Other" })];
  pending.resolve(response({ repositories: [menuCatalog("repository-001", fresh)] })); await settle();
  staleOption.click(); assert.equal(h.storage.has(DISPLAY_KEY), false); assert.equal(h.byClass("repository-publish-compact-version").textContent, "Replacement 4.0.7 → 4.0.8");
  assert.equal(h.posts().length, 0); assert.equal(h.api.hasDraft(), false);
});
console.log(`PASS ${count} isolated repository-publish UI fixtures`);
