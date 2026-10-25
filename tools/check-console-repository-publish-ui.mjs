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
const settings = repos => ({ repositories: repos || [repository()], naming: { preset: "version", fallbackTitle: "更新进度 {datetime}", subtitle: "", notes: "", includeSummary: true, autoBump: true, allowActiveWork: true } });
const operation = (requestId, status = "working", repositories = []) => ({ requestId, status, repositories, message: "fixture" });
const component = (extra = {}) => ({ sourceId: "stable-component-001", path: "package.json", kind: "json", key: "version", name: "Music", scope: [], currentVersion: "2.3.4", nextVersion: "2.3.5", headVersion: "2.3.4", versionChanged: false, worktreeChanged: false, planState: "none", plannedVersion: "", transition: null, canBump: true, reason: "", expectedSha256: "a".repeat(64), expectedBytes: 100, planProof: "b".repeat(64), ...extra });
const automaticComponent = (extra = {}) => {
  const item = component({ worktreeChanged: true, ...extra });
  return { ...item, autoPlan: extra.autoPlan || { state: "eligible", fromVersion: item.currentVersion, targetVersion: item.nextVersion, reason: "Actual scoped fixture file changed" },
    transition: extra.transition === undefined ? { kind: "auto", fromVersion: item.currentVersion, toVersion: item.nextVersion } : extra.transition };
};
const planFor = item => ({ sourceId: item.sourceId, currentVersion: item.currentVersion, targetVersion: item.nextVersion, expectedSha256: item.expectedSha256, expectedBytes: item.expectedBytes, planProof: item.planProof });
const uploadSummary = (repo = repository(), extra = {}) => ({ state: "recorded", count: 3, commitSha: "a".repeat(40), verifiedAt: "2026-10-14T00:00:00Z", source: "console_confirmed_deliveries", startedAt: "2026-10-14T00:00:00Z", reason: "", binding: { repoId: repo.id, path: repo.path, repositoryUrl: repo.repositoryUrl, remote: repo.remote, branch: repo.branch }, ...extra });
function harness(options = {}) {
  const paintEvents = [], timers = new Map(), calls = [], observers = [], listeners = new Map(), windowListeners = new Map(), storage = options.storage || new Map();
  let document, hook = options.hook, timerId = 0;
  class Element {
    constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.parentElement = null; this.listeners = new Map(); this.attributes = {}; this.dataset = {}; this.style = {}; this.hidden = false; this.disabled = false; this.open = false; this.checked = false; this.value = ""; this.textContent = ""; this.className = ""; this.scrollTop = 0; this.scrollIntoViewCount = 0; this.focusCount = 0; }
    get textContent() { return this._textContent ?? ""; }
    set textContent(value) { const old = this._textContent; this._textContent = value; if (old !== value) paintEvents.push({ element: this, value }); }
    append(...items) { for (const item of items) { item.remove(); item.parentElement = this; this.children.push(item); } }
    replaceChildren(...items) { for (const old of this.children) old.parentElement = null; this.children = []; this.append(...items); }
    remove() { if (this.parentElement) { const parent = this.parentElement; parent.children.splice(parent.children.indexOf(this), 1); this.parentElement = null; } }
    contains(item) { return item === this || this.children.some(child => child.contains(item)); }
    closest(selector) { for (let item = this; item; item = item.parentElement) if (selector === '[data-module-panel="workspace"]' && item.attributes["data-module-panel"] === "workspace") return item; return null; }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    removeAttribute(key) { delete this.attributes[key]; }
    getAttribute(key) { return this.attributes[key] ?? null; }
    setCustomValidity(value) { this.validationMessage = value; }
    addEventListener(type, handler) { if (!this.listeners.has(type)) this.listeners.set(type, []); this.listeners.get(type).push(handler); }
    dispatch(type, extra = {}) { if (this.disabled && ["click", "change"].includes(type)) return; const event = { target: this, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...extra }; for (const handler of this.listeners.get(type) || []) handler(event); return event; }
    click() { const event = this.dispatch("click"); if (event && !event.defaultPrevented && this.tagName === "SUMMARY" && this.parentElement?.tagName === "DETAILS") { this.parentElement.open = !this.parentElement.open; this.parentElement.dispatch("toggle"); } }
    showModal() { this.open = true; }
    close() { this.open = false; this.dispatch("close"); }
    focus() { this.focusCount++; document.activeElement = this; }
    scrollIntoView(options) { this.scrollIntoViewCount++; this.lastScrollIntoView = options; }
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
  const catalog = options.catalog || { repositories: snapshot.settings.repositories.map(repo => ({ repoId: repo.id, name: "Music", components: [], hasChanges: null, changeState: "unknown", pendingRecovery: null })) };
  function versionReply() {
    return { repositories: catalog.repositories.map(item => {
      const repo = snapshot.settings.repositories.find(value => value.id === item.repoId);
      return { hasChanges: false, changeState: "unchanged", worktreeChanged: false, outgoingCommits: 0, headSha: "c".repeat(40), outgoingBaselineSha: "c".repeat(40), syncChanged: false, syncState: "none", pendingRecovery: false, readState: "ready", ...structuredClone(item),
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
  // Protocol-only fixtures: the initial status has no newly read catalog. Only
  // an explicit Check All request obtains the version rows prepared above.
  const serverSource = repo => "fixture-saved-source-" + settingsSha([repo, snapshot.settings.naming.autoBump]);
  function versionEnvelope(value = versionReply()) {
    const checkedAt = new Date(options.clock?.now ?? Date.now()).toISOString();
    const sources = snapshot.settings.repositories.map(repo => ({ repoId: repo.id, sourceIdentity: serverSource(repo) }));
    const rows = (value.repositories || []).map(item => ({ ...structuredClone(item),
      sourceIdentity: sources.find(source => source.repoId === item.repoId)?.sourceIdentity,
      checkedAt, displayOnly: item.displayOnly === true || item.cached === true }));
    return { cacheIdentity: "c".repeat(64), versionSources: sources, versionSnapshots: rows,
      versionReadStates: Object.fromEntries(sources.map(source => [source.repoId, { sourceIdentity: source.sourceIdentity,
        state: rows.some(item => item.repoId === source.repoId && item.readState !== "error") ? "ready" : "error", checkedAt, startedAt: checkedAt, message: "" }])),
      complete: true, refreshingIds: [], repositories: rows };
  }
  function statusReply() {
    if (Object.prototype.hasOwnProperty.call(snapshot, "cacheIdentity")) return snapshot;
    const value = versionEnvelope({ repositories: [] });
    for (const reading of Object.values(value.versionReadStates)) reading.state = "idle";
    return { ...snapshot, ...value };
  }
  const window = { crypto: { randomUUID }, localStorage: stored, sessionStorage: stored, setTimeout(fn, delay) { const id = ++timerId; timers.set(id, { fn, delay }); return id; }, clearTimeout(id) { timers.delete(id); }, addEventListener(type, handler) { if (!windowListeners.has(type)) windowListeners.set(type, new Set()); windowListeners.get(type).add(handler); }, removeEventListener(type, handler) { windowListeners.get(type)?.delete(handler); }, async fetch(url, init) {
    const call = { url, method: init.method, body: init.body ? JSON.parse(init.body) : null, options: init }; calls.push(call);
    if (hook) { const value = await hook(call); if (value !== undefined) return value; }
    if (url === BASE && init.method === "GET") return response(statusReply());
    if (url.startsWith(BASE + "/versions?snapshot=1") && init.method === "GET") return response(versionEnvelope());
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
  const FixtureDate = options.clock ? class extends Date { constructor(...args) { super(...(args.length ? args : [options.clock.now])); } static now() { return options.clock.now; } } : Date;
  runInNewContext(source, { window, document, MutationObserver, WeakMap, Map, Set, Uint8Array, AbortController, Date: FixtureDate, console });
  const byClass = (name, parent = root) => all(parent).find(item => item.className.split(" ").includes(name));
  const fields = name => all().filter(item => item.dataset.field === name);
  const button = label => all().find(item => item.tagName === "BUTTON" && item.textContent === label);
  const visible = item => { for (let parent = item; parent; parent = parent.parentElement) if (parent.hidden || parent !== item && parent.tagName === "DETAILS" && !parent.open && !parent.children[0]?.contains(item)) return false; return true; };
  return { window, document, snapshot, catalog, host, panel, all, calls, storage, timers, paintEvents, byClass, fields, button, visible, versionEnvelope, hook(value) { hook = value; }, get api() { return window.ConsoleRepositoryPublish.mount({ host }); }, posts(path) { return calls.filter(call => call.method === "POST" && (!path || call.url === BASE + path)); }, async ready() { if (options.loading) for (const listener of listeners.get("DOMContentLoaded") || []) listener(); await settle(); }, async open(repoId) { window.ConsoleRepositoryPublish.mount({ host }).open(repoId); await settle(); }, async expand() { byClass("repository-publish-toggle").click(); await settle(); }, async change(name, value, index = 0) { const input = fields(name)[index]; assert.ok(input, name); if (input.type === "checkbox") input.checked = value; else input.value = value; input.dispatch("change"); await settle(); }, locale(value) { root.lang = value; for (const observer of observers) if (observer.target === root && !observer.disconnected) observer.callback([]); }, async emitWindow(type) { for (const listener of windowListeners.get(type) || []) listener(); await settle(); }, async setPanelHidden(value) { panel.hidden = value; for (const observer of observers) if (observer.target === panel && !observer.disconnected) observer.callback([]); await settle(); }, async poll() { const entry = [...timers.entries()].find(([, item]) => item.delay >= 1200 && item.delay <= 10000); assert.ok(entry, "expected original-request polling timer"); timers.delete(entry[0]); entry[1].fn(); await settle(); } };
}
const versionCalls = h => h.calls.filter(call => call.url.startsWith(BASE + "/versions?"));
const activityCalls = h => h.calls.filter(call => call.url.startsWith(BASE + "/activity?"));
async function checkAll(h) { const check = h.byClass("repository-publish-check"); assert.ok(check, "explicit Check All control"); check.click(); await settle(); }
async function expandAndCheck(h) { await h.expand(); await checkAll(h); }
async function openAndCheck(h, repoId) { await h.open(repoId); await checkAll(h); }
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
await test("a manual snapshot request keeps its bounded transport deadline without a leftover abort", async () => {
  const pending = deferred(), h = harness({ hook(call) { if (call.url.startsWith(BASE + "/versions?")) return pending.promise; } });
  await h.ready(); await h.expand(); assert.equal(versionCalls(h).length, 0); await checkAll(h);
  const versions = versionCalls(h); assert.equal(versions.length, 1); assert.equal(versions[0].url, BASE + "/versions?snapshot=1&refresh=1");
  const aborts = [...h.timers].filter(([, timer]) => timer.delay === 10000); assert.equal(aborts.length, 1);
  assert.equal(versions[0].options.signal.aborted, false); assert.equal(h.byClass("repository-publish-check").disabled, true); assert.equal(h.byClass("repository-publish-primary").disabled, true);
  pending.resolve(response(h.versionEnvelope({ repositories: [{ repoId: "repository-001", hasChanges: false, changeState: "unchanged", components: [component()] }] })));
  await settle(); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4");
  assert.equal(h.timers.has(aborts[0][0]), false); assert.equal(h.posts().length, 0); assert.equal(h.byClass("repository-publish-check").disabled, false);
});
await test("a manual snapshot transport timeout aborts once without mutation or automatic resend", async () => {
  const h = harness({ hook(call) { if (call.url.startsWith(BASE + "/versions?")) return new Promise((resolve, reject) =>
    call.options.signal.addEventListener("abort", () => reject(new Error("synthetic snapshot timeout")), { once: true })); } });
  await h.ready(); await expandAndCheck(h);
  const [timerId, timer] = [...h.timers].find(([, item]) => item.delay === 10000); timer.fn(); await settle();
  assert.equal(versionCalls(h).length, 1); assert.equal(versionCalls(h)[0].options.signal.aborted, true); assert.equal(h.timers.has(timerId), false);
  assert.equal(h.byClass("repository-publish-primary").disabled, false); assert.equal(h.byClass("repository-publish-check").disabled, false);
  assert.equal(h.posts().length, 0); assert.equal([...h.timers.values()].some(timer => timer.delay === 1200), false);
});
await test("configuration POST keeps its twenty-second deadline and clears the timer after acknowledgement", async () => {
  const pending = deferred(); const h = harness({ hook(call) { if (call.url === BASE + "/config") return pending.promise; } });
  await h.ready(); await h.open(); await h.change("notes", "preserve POST deadline");
  const [[timerId, timer]] = h.timers; assert.equal(h.timers.size, 1); assert.equal(timer.delay, 20000);
  h.snapshot.settings = h.posts("/config")[0].body.settings; h.snapshot.settingsSha = settingsSha(h.snapshot.settings);
  pending.resolve(response(configReceipt(h.snapshot.settings))); await settle();
  assert.equal(h.timers.has(timerId), false); assert.equal(h.timers.size, 0); assert.equal(h.posts("/config").length, 1); assert.equal(h.posts("/run").length, 0);
});
await test("closed toolbar keeps Push All and Configure All visible without a resident form", async () => {
  const h = harness(); await h.ready(); const bar = h.byClass("repository-publish-bar"); assert.equal(bar.children.filter(item => !item.hidden).length, 5); assert.equal(h.byClass("repository-publish-dialog").open, false); assert.equal(h.fields("path").length, 0); assert.equal(h.byClass("repository-publish-primary").disabled, false); assert.match(css, /\.repository-publish-bar\[hidden\]/);
  assert.ok(bar.children.slice(0, 2).every(item => item.getAttribute("data-console-management") === ""));
});
await test("initial binding warnings stay collapsed in config with safe supported text and snapshot wording", async () => {
  const hostile = '<img src=x onerror="evil()">', h = harness({ snapshot: { warnings: [
    "legacy_initial_note", { code: "configured_repository_path_missing", path: "D:/Projects/MyWeb", source: "environment" },
    { code: hostile, path: "D:/Projects/Other", source: "https://secret-token@example.invalid/private" },
    { repositoryUrl: "https://another-secret@example.invalid/private", unsupported: hostile }, null, 17
  ], warningsSource: "initial_discovery" } });
  await h.ready(); const bar = h.byClass("repository-publish-bar"), notes = h.byClass("repository-publish-warnings");
  assert.equal(bar.children.filter(item => !item.hidden).length, 5); assert.equal(h.byClass("repository-publish-dialog").open, false);
  assert.equal(h.fields("path").length, 0); assert.equal(notes.children[2].children.length, 0); assert.equal(notes.hidden, true);
  await h.open(); assert.equal(notes.open, false); assert.equal(notes.hidden, false); assert.equal(notes.children[0].textContent, "初次绑定提示");
  assert.equal(notes.children[2].children.length, 3); const labels = h.all(notes).map(item => item.textContent).join(" ");
  assert.match(labels, /legacy_initial_note/); assert.match(labels, /configured_repository_path_missing.*D:\/Projects\/MyWeb.*environment/);
  assert.ok(labels.includes(hostile)); assert.match(labels, /初次发现时的快照.*不代表当前仍有异常/);
  assert.doesNotMatch(labels, /secret-token|another-secret|example\.invalid/); assert.equal(h.all(notes).some(item => item.tagName === "IMG" || item.tagName === "A"), false);
  h.locale("en"); assert.equal(notes.children[0].textContent, "Initial binding notes"); assert.match(notes.children[1].textContent, /initial discovery snapshot.*does not describe current issues/);
  h.button("Close").click(); assert.equal(h.byClass("repository-publish-dialog").open, false); assert.equal(bar.children.filter(item => !item.hidden).length, 5); assert.equal(h.posts().length, 0);
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
  const pending = deferred(); const h = harness({ hook(call) { if (call.url === BASE + "/run") return pending.promise; } }); await h.ready(); const run = h.byClass("repository-publish-primary"); run.click(); run.click(); await settle(); assert.equal(h.posts("/run").length, 1); assert.equal(h.storage.get(KEY), h.posts("/run")[0].body.requestId); assert.deepEqual(h.posts("/run")[0].body.repoIds, ["repository-001"]); assert.equal(h.posts("/run")[0].body.intent, "commit_and_push"); assert.equal(JSON.parse(h.storage.get(KEY + ".payload")).intent, "commit_and_push"); pending.resolve(response(operation(h.storage.get(KEY)))); await settle(); assert.equal(h.posts("/run").length, 1);
});
await test("uncertain network and reload read original identity without a second POST", async () => {
  const storage = new Map(); const first = harness({ storage, hook(call) { if (call.url === BASE + "/run") throw new Error("unknown delivery"); } }); await first.ready(); first.byClass("repository-publish-primary").click(); await settle(); const id = storage.get(KEY); await first.poll(); assert.ok(first.calls.some(call => call.url.endsWith("requestId=" + id))); assert.equal(first.posts("/run").length, 1);
  const reload = harness({ storage }); await reload.ready(); assert.equal(reload.byClass("repository-publish-primary").disabled, true); await reload.poll(); assert.ok(reload.calls.some(call => call.url.endsWith("requestId=" + id))); assert.equal(reload.posts().length, 0); assert.equal(storage.get(KEY), id);
});
await test("different receipt cannot release unresolved original request", async () => {
  const id = randomUUID(); const storage = new Map([[KEY, id]]); const h = harness({ storage, snapshot: { operation: operation(randomUUID(), "complete") } }); await h.ready(); await h.poll(); assert.equal(h.storage.get(KEY), id); assert.equal(h.byClass("repository-publish-primary").disabled, true); assert.equal(h.posts().length, 0);
});
await test("terminal receipt exposes per-repo continuation using one new filtered run", async () => {
  const id = randomUUID(); const h = harness({ storage: new Map([[KEY, id]]), snapshot: { operation: operation(id, "complete", [{ repoId: "repository-001", name: "Music", status: "push_failed", phase: "pushing", message: "original commit retained", commitSha: "a".repeat(40), title: "v2", body: "fixture", uploadSummary: uploadSummary() }]) } }); await h.ready(); assert.equal(h.storage.has(KEY), false); await h.open(); const retry = h.button("继续此仓库"); assert.ok(retry); retry.click(); await settle(); assert.deepEqual(h.posts("/run")[0].body.repoIds, ["repository-001"]); assert.notEqual(h.posts("/run")[0].body.requestId, id);
});
await test("preview renders actual title/body without sync or commit request", async () => {
  const h = harness(); await h.ready(); await h.open(); h.button("预览标题与改动").click(); await settle(); assert.equal(h.posts("/preview").length, 1); assert.equal(h.posts("/run").length, 0); assert.equal(h.posts("/config").length, 0); const text = h.all().map(item => item.textContent).join(" "); assert.match(text, /Music v2.3/); assert.match(text, /2 files/);
});
await test("language follows app lang mutation without changing drafts or sending", async () => {
  const h = harness(); await h.ready(); await h.open(); const before = h.calls.length; h.locale("en"); assert.equal(h.byClass("repository-publish-primary").textContent, "Push All"); assert.equal(h.fields("branch")[0].placeholder, "Current branch (read and save)"); assert.equal(h.fields("branch")[0].value, "feature/music"); assert.equal(h.calls.length, before); assert.ok(h.button("Configure All"));
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
  h.snapshot.operation = operation(id, "attention", [{ repoId: "repository-001", name: "Music", status: "deferred", phase: "checking", message: "busy workspace", logs: [{ at: "fixture-time", phase: "checking", message: "original files retained" }], uploadSummary: uploadSummary() }]); await h.poll(); assert.equal(h.storage.has(KEY), false); await h.open(); assert.ok(h.button("继续此仓库")); assert.ok(h.all().some(item => item.textContent.includes("original files retained")));
});
await test("interrupted queued repository receives a continuation from verification_required", async () => {
  const id = randomUUID(), h = harness({ snapshot: { operation: operation(id, "verification_required", [{ repoId: "repository-001", status: "queued", name: "Music", uploadSummary: uploadSummary() }]) } }); await h.ready(); await h.open(); assert.ok(h.button("继续此仓库")); assert.equal(h.byClass("repository-publish-primary").disabled, false);
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
await test("reloading an explicit commit-and-push request retains its original intent and same identity", async () => {
  const requestId = randomUUID(), original = { requestId, repoIds: ["repository-001"], createdAt: 1, intent: "commit_and_push" }, storage = new Map([[KEY, requestId], [KEY + ".payload", JSON.stringify(original)]]);
  const h = harness({ storage }); await h.ready(); assert.equal(h.posts().length, 0); await h.poll();
  assert.equal(h.button("继续原请求").hidden, false); h.button("继续原请求").click(); await settle();
  assert.deepEqual(h.posts("/run")[0].body, { requestId, repoIds: original.repoIds, intent: "commit_and_push" });
  assert.equal(h.posts("/run").length, 1); assert.equal(JSON.parse(h.storage.get(KEY + ".payload")).intent, "commit_and_push"); h.api.destroy();
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
  assert.equal(h.byClass("repository-publish-primary").textContent, "全部上传"); assert.equal(h.byClass("repository-publish-expanded").hidden, true); assert.equal(h.calls.length, 1); assert.equal(h.fields("path").length, 0);
  await expandAndCheck(h); const rows = h.byClass("repository-publish-compact-rows").children; assert.equal(rows.length, 5); assert.deepEqual(rows.map(row => h.byClass("repository-publish-compact-name", row).textContent), names); assert.deepEqual(rows.map(row => h.byClass("repository-publish-compact-version", row).textContent), names.map((_, i) => `1.0.${i}`));
  assert.equal(h.byClass("repository-publish-toggle").getAttribute("aria-expanded"), "true"); assert.ok(h.button("配置全部")); assert.equal(h.fields("path").length, 0); assert.equal(h.posts().length, 0); assert.equal(h.calls.filter(call => call.url.startsWith(BASE + "/versions?")).length, 1);
  await h.expand(); assert.equal(h.byClass("repository-publish-expanded").hidden, true); assert.equal(h.calls.filter(call => call.url.startsWith(BASE + "/versions?")).length, 1); h.locale("en"); assert.equal(h.byClass("repository-publish-primary").textContent, "Push All"); assert.equal(h.posts().length, 0);
});
await test("single-repository configure hides other repos and keeps paths and rules collapsed", async () => {
  const repos = [repository(), repository({ id: "repository-002", repositoryUrl: "https://github.com/example/Second.git", path: "D:/Other" })], h = harness({ snapshot: { settings: settings(repos) } }); await h.ready(); await expandAndCheck(h); const name = h.byClass("repository-publish-compact-name", h.byClass("repository-publish-compact-rows").children[1]);
  assert.equal(name.tagName, "BUTTON"); assert.equal(name.type, "button"); assert.match(name.getAttribute("aria-label"), /配置.*Second/); assert.equal(name.getAttribute("aria-haspopup"), "dialog");
  name.focus(); assert.equal(h.document.activeElement, name); name.click(); await settle();
  const cards = h.byClass("repository-publish-repositories").children; assert.equal(cards[0].hidden, true); assert.equal(cards[1].hidden, false); assert.equal(cards[1].open, true); assert.match(h.byClass("repository-publish-header").children[0].textContent, /^Second/);
  assert.equal(h.fields("enabled").filter(h.visible).length, 1); assert.equal(h.fields("path").filter(h.visible).length, 0); assert.equal(h.fields("notes").filter(h.visible).length, 0); assert.equal(h.fields("sync").filter(h.visible).length, 0); assert.equal(h.posts().length, 0);
  h.button("预览标题与改动").click(); await settle(); assert.deepEqual(h.posts("/preview")[0].body, { repoId: "repository-002" }); assert.equal(h.posts("/run").length, 0);
  h.button("关闭").click(); assert.equal(h.document.activeElement, name); h.button("配置全部").click(); await settle(); assert.ok(h.byClass("repository-publish-repositories").children.every(card => !card.hidden));
});
await test("a row Push submits only its repository with one commit-and-push intent and keeps batch guards", async () => {
  const repos = [repository(), repository({ id: "repository-002", repositoryUrl: "https://github.com/example/Second.git", path: "D:/Other" })];
  const h = harness({ lang: "en", snapshot: { settings: settings(repos) } }); await h.ready(); await expandAndCheck(h);
  const rows = h.byClass("repository-publish-compact-rows").children, push = h.byClass("repository-publish-row-push", rows[1]);
  assert.equal(push.textContent, "Push"); assert.equal(push.disabled, false); push.click(); push.click(); await settle();
  const posted = h.posts("/run"); assert.equal(posted.length, 1); assert.deepEqual(posted[0].body.repoIds, [repos[1].id]); assert.equal(posted[0].body.intent, "commit_and_push");
  assert.deepEqual(JSON.parse(h.storage.get(KEY + ".payload")).repoIds, [repos[1].id]); assert.equal(h.byClass("repository-publish-dialog").open, false);
  assert.equal(h.byClass("repository-publish-primary").disabled, true); assert.ok(rows.every(row => h.byClass("repository-publish-row-push", row).disabled));
  h.byClass("repository-publish-row-push", rows[0]).click(); h.byClass("repository-publish-primary").click(); await settle(); assert.equal(h.posts("/run").length, 1); assert.equal(h.posts("/config").length, 0);
});
await test("all configuration starts as a compact name list and retains expanded details after autosave", async () => {
  const h = harness({ snapshot: { settings: settings([repository(), repository({ id: "repository-002", path: "D:/Other", repositoryUrl: "https://github.com/example/Second" })]) } }); await h.ready(); await h.open();
  const cards = h.byClass("repository-publish-repositories").children; assert.ok(cards.every(card => card.tagName === "DETAILS" && !card.open)); assert.equal(h.fields("path").filter(h.visible).length, 0); assert.deepEqual(cards.map(card => card.children[0].textContent), ["Music", "Second"]);
  cards[0].open = true; const connection = h.all(cards[0]).find(item => item.className.split(" ").includes("repository-publish-connection")); connection.open = true; await h.change("branch", "feature/real-branch");
  assert.equal(h.byClass("repository-publish-repositories").children[0].open, true); assert.equal(h.byClass("repository-publish-connection").open, true); assert.equal(h.posts("/config")[0].body.settings.repositories[0].branch, "feature/real-branch"); assert.equal(h.posts("/run").length, 0);
});
await test("patch plans preserve each component format and proof and only save configuration", async () => {
  const components = [component({ name: "Unity", currentVersion: "0.1", nextVersion: "0.1.1" }), component({ sourceId: "stable-second", name: "Blender", currentVersion: "(1, 2, 3)", nextVersion: "(1, 2, 4)", planProof: "c".repeat(64) }), component({ sourceId: "manual", name: "Other", canBump: false, nextVersion: "", reason: "Custom format is read-only" })];
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", components }] } }); await h.ready(); await openAndCheck(h, "repository-001"); let actions = h.all().filter(item => item.className.split(" ").includes("repository-publish-plan-action")); assert.equal(actions.length, 3); assert.equal(actions[2].disabled, true); assert.ok(h.all().some(item => item.textContent === "Custom format is read-only"));
  actions[0].click(); await settle(); await checkAll(h); actions = h.all().filter(item => item.className.split(" ").includes("repository-publish-plan-action")); actions[1].click(); await settle(); await checkAll(h);
  const plans = h.posts("/config").at(-1).body.settings.repositories[0].versionPlans; assert.deepEqual(plans, components.slice(0, 2).map(item => ({ sourceId: item.sourceId, currentVersion: item.currentVersion, targetVersion: item.nextVersion, expectedSha256: item.expectedSha256, expectedBytes: item.expectedBytes, planProof: item.planProof }))); assert.equal(h.posts("/run").length, 0);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "版本待读取");
  assert.deepEqual(h.all(h.byClass("repository-publish-version-menu")).filter(item => item.dataset.sourceId).map(item => item.textContent), ["Unity 0.1.1", "Blender (1, 2, 4)", "Other 2.3.4"]);
  h.button("取消计划").click(); await settle(); assert.equal(h.posts("/config").at(-1).body.settings.repositories[0].versionPlans.length, 1); assert.equal(h.posts("/run").length, 0);
});
await test("version lookup failure or missing proof cannot invent a plan or block unchanged-version push", async () => {
  const h = harness({ hook(call) { if (call.url.startsWith(BASE + "/versions?")) throw new Error("read unavailable"); } }); await h.ready(); await expandAndCheck(h); assert.equal(h.posts().length, 0); assert.equal(h.byClass("repository-publish-primary").disabled, false); assert.match(h.byClass("repository-publish-compact-version").textContent, /读取失败/);
  const bad = harness({ catalog: { repositories: [{ repoId: "repository-001", components: [component({ planProof: "" })] }] } }); await bad.ready(); await openAndCheck(bad); assert.equal(bad.byClass("repository-publish-plan-action").disabled, true); assert.equal(bad.posts().length, 0);
});
await test("switching repository configuration preserves invalid raw sync drafts and never posts a run", async () => {
  const h = harness({ snapshot: { settings: settings([repository(), repository({ id: "repository-002", path: "D:/Other" })]) } }); await h.ready(); await h.open("repository-001"); await h.change("sync", "raw unpaired ->"); const raw = h.fields("sync")[0]; await h.open("repository-002"); assert.equal(h.fields("sync")[0], raw); assert.equal(raw.value, "raw unpaired ->"); assert.equal(h.api.hasDraft(), true); assert.equal(h.posts().length, 0); assert.equal(h.byClass("repository-publish-primary").disabled, true);
});
await test("late status read cannot overwrite a configuration that finished saving after that read began", async () => {
  const delayed = deferred(); let reads = 0; const h = harness({ hook(call) { if (call.url === BASE && call.method === "GET" && ++reads === 2) return delayed.promise; } }); await h.ready(); const stale = structuredClone(h.snapshot); h.api.open(); await settle(); await h.change("notes", "newer completed save"); assert.equal(h.posts("/config").length, 1); delayed.resolve(response(stale)); await settle(); assert.equal(h.fields("notes")[0].value, "newer completed save"); assert.equal(h.api.hasDraft(), false);
});
await test("completed operation refreshes cleared one-time plans without polling version files or repeating POST", async () => {
  const comp = component(), plan = { sourceId: comp.sourceId, currentVersion: comp.currentVersion, targetVersion: comp.nextVersion, expectedSha256: comp.expectedSha256, expectedBytes: comp.expectedBytes, planProof: comp.planProof }, h = harness({ snapshot: { settings: settings([repository({ versionPlans: [plan] })]) } }); await h.ready(); h.byClass("repository-publish-primary").click(); await settle(); const id = h.posts("/run")[0].body.requestId;
  h.snapshot.settings.repositories[0].versionPlans = []; h.snapshot.operation = operation(id, "success", [{ repoId: "repository-001", status: "success" }]); await h.poll(); assert.equal(h.posts("/run").length, 1); assert.equal(h.calls.filter(call => call.url.startsWith(BASE + "/versions?")).length, 0); await h.open(); assert.equal(h.posts().filter(call => call.url.endsWith("/config")).length, 0); assert.equal(h.all().some(item => item.textContent === "取消计划"), false);
});
await test("visible planned operation reads the actual completed version once and does not infer its target", async () => {
  const comp = component(), plan = { sourceId: comp.sourceId, currentVersion: comp.currentVersion, targetVersion: comp.nextVersion, expectedSha256: comp.expectedSha256, expectedBytes: comp.expectedBytes, planProof: comp.planProof }, h = harness({ snapshot: { settings: settings([repository({ versionPlans: [plan] })]) }, catalog: { repositories: [{ repoId: "repository-001", components: [comp], hasChanges: true, changeState: "changed", worktreeChanged: true }] } }); await h.ready(); await expandAndCheck(h); assert.match(h.byClass("repository-publish-compact-version").textContent, /2.3.5/);
  h.byClass("repository-publish-primary").click(); await settle(); const id = h.posts("/run")[0].body.requestId; h.snapshot.settings.repositories[0].versionPlans = []; h.snapshot.operation = operation(id, "success", [{ repoId: "repository-001", status: "success" }]); h.catalog.repositories[0].components[0].currentVersion = "2.3.5"; await h.poll(); assert.equal(versionCalls(h).length, 1); await checkAll(h);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.5"); assert.equal(h.calls.filter(call => call.url.startsWith(BASE + "/versions?")).length, 2); assert.equal(h.posts("/run").length, 1); assert.equal(h.posts("/config").length, 0);
  const failed = harness({ snapshot: { settings: settings([repository({ versionPlans: [plan] })]) }, catalog: { repositories: [{ repoId: "repository-001", components: [component()], hasChanges: true, changeState: "changed", worktreeChanged: true }] } }); await failed.ready(); await expandAndCheck(failed); failed.byClass("repository-publish-primary").click(); await settle(); const failedId = failed.posts("/run")[0].body.requestId; failed.snapshot.settings.repositories[0].versionPlans = []; failed.snapshot.operation = operation(failedId, "attention", [{ repoId: "repository-001", status: "commit_failed" }]); await failed.poll(); await checkAll(failed); assert.equal(failed.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.equal(failed.posts("/run").length, 1);
});
await test("saved source changes invalidate old catalog and a late lookup cannot expose the old component", async () => {
  const delayed = deferred(), old = { repositories: [{ repoId: "repository-001", components: [component()] }] }, fresh = { repositories: [{ repoId: "repository-001", components: [component({ sourceId: "new-source", path: "new-package.json", currentVersion: "4.0.0", nextVersion: "4.0.1" })] }] };
  const h = harness({ snapshot: { settings: settings([repository({ versionSources: [{ path: "package.json", kind: "json", key: "version", name: "Module", scope: "" }] })]) }, catalog: old });
  await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); await h.open("repository-001");
  const oldReply = h.versionEnvelope(old); h.hook(call => call.url.startsWith(BASE + "/versions?") ? delayed.promise : undefined); await checkAll(h);
  h.snapshot.settings.repositories[0].versionSources[0].path = "new-package.json"; h.snapshot.settingsSha = settingsSha(h.snapshot.settings); const reads = versionCalls(h).length; delayed.resolve(response(h.versionEnvelope(fresh))); await settle(); await h.api.refresh(); await settle();
  assert.equal(versionCalls(h).length, reads); assert.equal(h.byClass("repository-publish-plan-action"), undefined); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown");
  h.hook(call => call.url.startsWith(BASE + "/versions?") ? response(h.versionEnvelope(fresh)) : undefined); await checkAll(h);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "4.0.0"); h.byClass("repository-publish-plan-action").click(); await settle(); assert.equal(h.posts("/config").at(-1).body.settings.repositories[0].versionPlans[0].sourceId, "new-source"); assert.equal(h.posts("/run").length, 0);
});
await test("backend noop is no changes and solid dialog and theme-aware primary colors remain explicit", async () => {
  const h = harness({ snapshot: { operation: operation(randomUUID(), "success", [{ repoId: "repository-001", status: "noop", uploadSummary: uploadSummary() }]) }, catalog: { repositories: [{ repoId: "repository-001", components: [], hasChanges: false, changeState: "unchanged" }] } }); await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-status").textContent, "无改动"); h.locale("en"); assert.equal(h.byClass("repository-publish-compact-status").textContent, "No changes");
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
  const h = harness({ snapshot: { settings: settings(repos) }, catalog: { repositories: rows } }); await h.ready(); await expandAndCheck(h);
  const visible = h.byClass("repository-publish-compact-rows").children;
  assert.deepEqual(visible.map(row => h.byClass("repository-publish-compact-version", row).dataset.changeState), ["unchanged", "changed", "changed", "unknown"]);
  assert.match(h.byClass("repository-publish-compact-version", visible[0]).textContent, /2\.3\.5/);
  assert.equal(h.byClass("repository-publish-compact-version", visible[1]).textContent, "2.3.4"); assert.equal(h.byClass("repository-publish-compact-version", visible[2]).textContent, "2.3.4");
  assert.equal(h.byClass("repository-publish-compact-status", visible[2]).textContent, "有提交待推送"); assert.equal(h.byClass("repository-publish-compact-status", visible[3]).textContent, "变化未核对");
  assert.match(h.byClass("repository-publish-compact-version", visible[3]).title, /No trustworthy tracking ref/); assert.equal(h.posts().length, 0);
  const colors = [...css.matchAll(/--repository-publish-change:\s*#([0-9a-f]{6})/gi)].map(match => match[1]);
  assert.equal(colors.length, 2);
  for (const color of colors) { const channels = color.match(/../g).map(value => Number.parseInt(value, 16)); assert.ok(channels[1] > channels[0] && channels[1] > channels[2], "Both actual theme change colors must be green, not the desktop dark blue --green alias"); }
  assert.match(css, /\.repository-publish-compact-version\s*\{[^}]*color:\s*var\(--text,/);
  assert.match(css, /compact-version\[data-change-state="changed"\][^}]*var\(--repository-publish-change,/);
  assert.match(css, /\.repository-publish-compact-status\s*\{[^}]*color:\s*var\(--text,/);
  assert.doesNotMatch(css, /data-change-state="unknown"[^}]*var\(--status-warning,/);
  assert.match(css, /data-attention="true"[^}]*var\(--status-warning,/);
  assert.ok(visible.every(row => h.byClass("repository-publish-compact-status", row).dataset.attention === "false"));
});
await test("unknown or contradictory receipts remain unverified without claiming clean or warning", async () => {
  for (const row of [{}, { hasChanges: false, changeState: "changed" }, { hasChanges: true, changeState: "unchanged" }, { hasChanges: null, changeState: "unchanged" }]) {
    const h = harness({ catalog: { repositories: [{ repoId: "repository-001", components: [component()], ...row, hasChanges: row.hasChanges, changeState: row.changeState }] } });
    await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown"); assert.equal(h.byClass("repository-publish-compact-status").textContent, "变化未核对");
  }
});
await test("Summary uses real HEAD-to-working changes and keeps unselected next versions outside the transition", async () => {
  const changed = component({ currentVersion: "1.6.44", headVersion: "1.6.43", nextVersion: "1.6.45", versionChanged: true,
    transition: { kind: "working", fromVersion: "1.6.43", toVersion: "1.6.44" } });
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", components: [changed] }] } });
  await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.6.44"); await openAndCheck(h);
  assert.equal(h.byClass("repository-publish-plan-row").children[0].textContent, "1.6.44"); assert.match(h.byClass("repository-publish-plan-row").children[2].textContent, /已修改版本/); assert.equal(h.posts().length, 0);
  const unchanged = harness({ catalog: { repositories: [{ repoId: "repository-001", components: [component()] }] } }); await unchanged.ready(); await openAndCheck(unchanged);
  assert.equal(unchanged.byClass("repository-publish-plan-row").children[0].textContent, "2.3.4"); assert.match(unchanged.byClass("repository-publish-plan-row").children[2].textContent, /本次保留当前版本.*可选下一版 2\.3\.5/); assert.equal(unchanged.posts().length, 0);
});
await test("missing or stale actual version reads never reuse the plan's old current number", async () => {
  const planned = component(), repo = repository({ versionPlans: [planFor(planned)] });
  const failed = harness({ snapshot: { settings: settings([repo]) }, hook(call) { if (call.url.startsWith(BASE + "/versions?")) throw new Error("read unavailable"); } });
  await failed.ready(); await openAndCheck(failed); assert.match(failed.byClass("repository-publish-compact-version").textContent, /读取失败/); assert.doesNotMatch(failed.byClass("repository-publish-compact-version").textContent, /2\.3\.4/);
  assert.equal(failed.byClass("repository-publish-compact-version").dataset.changeState, "unknown"); assert.match(failed.byClass("repository-publish-plan-row").children[0].textContent, /计划待核对.*计划目标 2\.3\.5/);
  const stale = harness({ snapshot: { settings: settings([repo]) }, catalog: { repositories: [{ repoId: repo.id, components: [component({ currentVersion: "4.0.7", nextVersion: "4.0.8", planState: "stale", plannedVersion: "", transition: null })] }] } });
  await stale.ready(); await openAndCheck(stale); assert.equal(stale.byClass("repository-publish-compact-version").textContent, "4.0.7"); assert.equal(stale.byClass("repository-publish-plan-row").children[0].textContent, "4.0.7"); assert.match(stale.byClass("repository-publish-plan-row").children[2].textContent, /计划待核对/); assert.equal(stale.posts().length, 0);
});
await test("99 rollover and independent module formats are displayed only from backend targets", async () => {
  const components = [component({ currentVersion: "1.6.99", nextVersion: "1.7.0", name: "Console" }),
    component({ sourceId: "second-source", currentVersion: "(1, 99, 99)", nextVersion: "(2, 0, 0)", name: "Plugin" })];
  const h = harness({ snapshot: { settings: settings([repository({ versionPlans: components.map(planFor) })]) }, catalog: { repositories: [{ repoId: "repository-001", components, hasChanges: true, changeState: "changed", worktreeChanged: true }] } });
  await h.ready(); await openAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, "版本待读取");
  assert.deepEqual(h.all(h.byClass("repository-publish-version-menu")).filter(item => item.dataset.sourceId).map(item => item.textContent), ["Console 1.7.0", "Plugin (2, 0, 0)"]);
  assert.equal(h.posts().length, 0); h.byClass("repository-publish-primary").click(); await settle(); assert.equal(h.posts("/run").length, 1);
  assert.deepEqual(Object.keys(h.posts("/run")[0].body).sort(), ["intent", "repoIds", "requestId"]); assert.equal(h.posts("/run")[0].body.intent, "commit_and_push"); assert.equal(h.posts("/config").length, 0);
});
await test("a completed unplanned push rereads actual dirty state once without a repeated run", async () => {
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", components: [component()] }] } });
  await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "changed");
  h.byClass("repository-publish-primary").click(); await settle(); const id = h.posts("/run")[0].body.requestId;
  h.catalog.repositories[0].hasChanges = false; h.catalog.repositories[0].changeState = "unchanged"; h.snapshot.operation = operation(id, "success", [{ repoId: "repository-001", status: "success" }]);
  await h.poll(); assert.equal(versionCalls(h).length, 1); await checkAll(h); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unchanged"); assert.equal(h.calls.filter(call => call.url.startsWith(BASE + "/versions?")).length, 2); assert.equal(h.posts("/run").length, 1); assert.equal(h.posts("/config").length, 0);
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
  await h.ready(); await openAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.6.44"); assert.match(h.byClass("repository-publish-plan-row").children[2].textContent, /已计划.*不修改版本文件/);
  assert.doesNotMatch(h.byClass("repository-publish-plan-row").children[0].textContent, /0\.1\.0/); assert.equal(h.posts().length, 0);
});
await test("preview Summary only shows targets actually selected for this commit, retaining push-only plans", async () => {
  const item = component({ path: "HEAD", kind: "git_commit", key: "subject", currentVersion: "1.6.43", nextVersion: "1.6.44", planState: "valid", plannedVersion: "1.6.44", transition: { kind: "planned", fromVersion: "1.6.43", toVersion: "1.6.44" } });
  for (const [action, planWillApply, expected, hint] of [["commit", true, "1.6.44", "已计划"], ["push_only", false, "1.6.43", "计划保留"], ["noop", false, "1.6.43", "计划保留"], ["sync_pending", null, "1.6.43", "同步后再核对"], ["unknown", null, "1.6.43", "执行待核对"]]) {
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
    const old = { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", components: [component({ currentVersion: "1.0.5", nextVersion: "1.0.6" })] }] };
    const fresh = { repositories: [{ repoId: "repository-001", hasChanges: false, changeState: "unchanged", worktreeChanged: false, outgoingCommits: 0, headSha: "c".repeat(40), outgoingBaselineSha: "c".repeat(40), syncChanged: false, syncState: "none", pendingRecovery: false, components: [component({ currentVersion: "2.0.7", nextVersion: "2.0.8" })] }] };
    const h = harness({ catalog: old }); await h.ready(); await expandAndCheck(h); await h.open();
    const delayed = deferred(); h.hook(call => call.url.startsWith(BASE + "/versions?") ? delayed.promise : undefined); await checkAll(h);
    if (field === "autoBump") h.snapshot.settings.naming.autoBump = value; else h.snapshot.settings.repositories[0][field === "excludes" ? "exclude" : field] = field === "excludes" ? [value] : value;
    h.snapshot.settingsSha = settingsSha(h.snapshot.settings);
    delayed.resolve(response(h.versionEnvelope(fresh))); await settle(); await h.api.refresh(); await settle();
    assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown"); assert.equal(versionCalls(h).length, 2);
    h.hook(call => call.url.startsWith(BASE + "/versions?") ? response(h.versionEnvelope(fresh)) : undefined); await checkAll(h);
    assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.0.7"); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unchanged"); assert.equal(h.posts().length, 0);
  }
});
await test("a planned transition flag alone cannot show a mismatched current or target", async () => {
  for (const patch of [{ fromVersion: "9.9.9" }, { toVersion: "9.9.9" }]) {
    const item = component({ planState: "valid", plannedVersion: "2.3.5", transition: { kind: "planned", fromVersion: "2.3.4", toVersion: "2.3.5", ...patch } });
    const h = harness({ snapshot: { settings: settings([repository({ versionPlans: [planFor(item)] })]) }, catalog: { repositories: [{ repoId: "repository-001", components: [item] }] } });
    await h.ready(); await openAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.equal(h.byClass("repository-publish-plan-row").children[0].textContent, "2.3.4"); assert.match(h.byClass("repository-publish-plan-row").children[2].textContent, /计划待核对/); assert.equal(h.posts().length, 0);
  }
});
await test("an authoritative source error does not erase a real pending-change signal", async () => {
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: true, outgoingCommits: 0, message: "Version source is missing", components: [] }] } });
  await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "changed"); assert.match(h.byClass("repository-publish-compact-version").textContent, /版本读取失败/); assert.match(h.byClass("repository-publish-compact-version").title, /Version source is missing/); assert.equal(h.posts().length, 0);
});
await test("automatic bump defaults on and the saved checkbox can turn it off without running", async () => {
  const initial = settings(); delete initial.naming.autoBump;
  const auto = automaticComponent(), h = harness({ snapshot: { settings: initial }, catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: true, outgoingCommits: 0, components: [auto] }] } });
  await h.ready(); await openAndCheck(h); assert.equal(h.fields("autoBump")[0].checked, true); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.5");
  await h.change("autoBump", false); await checkAll(h); assert.equal(h.posts("/config").at(-1).body.settings.naming.autoBump, false); assert.equal(h.fields("autoBump")[0].checked, false);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "changed"); assert.equal(h.posts("/run").length, 0);
});
await test("actual automatic candidates show only the checked target version without creating a client plan", async () => {
  const auto = automaticComponent({ currentVersion: "1.6.99", nextVersion: "1.7.0" });
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: true, outgoingCommits: 0, components: [auto] }] }, hook(call) {
    if (call.url === BASE + "/preview") return response({ previews: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: true, action: "commit", planWillApply: true, title: "1.7.0", components: [auto] }] });
  } });
  await h.ready(); await openAndCheck(h); assert.equal(h.byClass("repository-publish-plan-row").children[0].textContent, "1.7.0"); assert.match(h.byClass("repository-publish-plan-row").children[2].textContent, /自动升版，提交时复核/);
  h.button("预览标题与改动").click(); await settle(); const row = h.byClass("repository-publish-preview-version"); assert.equal(row.textContent, "1.7.0"); assert.equal(row.dataset.transition, "auto"); assert.match(row.children[0].textContent, /自动升版/);
  assert.equal(h.posts("/config").length, 0); assert.equal(h.posts("/run").length, 0); assert.deepEqual(h.snapshot.settings.repositories[0].versionPlans || [], []);
});
await test("1.6.50 is the sole displayed new version while 1.6.49 remains the saved source", async () => {
  const auto = automaticComponent({ currentVersion: "1.6.49", headVersion: "1.6.49", nextVersion: "1.6.50" });
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: true, outgoingCommits: 0, components: [auto],
    repositoryVersion: { state: "current", currentVersion: "1.6.49", nextVersion: "1.6.50", transition: auto.transition } }] }, hook(call) {
    if (call.url === BASE + "/preview") return response({ previews: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: true, action: "commit", planWillApply: true, title: "1.6.50", components: [auto] }] });
  } });
  await h.ready(); await openAndCheck(h);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.6.50");
  assert.equal(h.byClass("repository-publish-plan-row").children[0].textContent, "1.6.50");
  assert.match(h.byClass("repository-publish-plan-row").children[2].textContent, /提交时复核/);
  h.button("预览标题与改动").click(); await settle(); assert.equal(h.byClass("repository-publish-preview-version").textContent, "1.6.50");
  assert.equal(h.catalog.repositories[0].components[0].currentVersion, "1.6.49");
  assert.equal(h.catalog.repositories[0].repositoryVersion.currentVersion, "1.6.49");
  assert.equal(h.posts("/run").length, 0); assert.equal(h.posts("/config").length, 0);
  h.locale("en"); assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.6.50");
});
await test("manual or initial versions and push-only commits never receive an extra automatic bump", async () => {
  const manual = component({ currentVersion: "2.3.5", nextVersion: "2.3.6", headVersion: "2.3.4", versionChanged: true, worktreeChanged: true, autoPlan: { state: "manual_version", fromVersion: "", targetVersion: "", reason: "Version already changed" }, transition: { kind: "working", fromVersion: "2.3.4", toVersion: "2.3.5" } });
  for (const [item, worktree, outgoing, expected] of [[manual, true, 0, "2.3.5"], [component({ autoPlan: { state: "initial_version", fromVersion: "", targetVersion: "", reason: "First version" } }), true, 0, "2.3.4"], [component({ autoPlan: { state: "none", fromVersion: "", targetVersion: "", reason: "Only existing commits" } }), false, 2, "2.3.4"]]) {
    const action = worktree ? "commit" : "push_only", h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: worktree, outgoingCommits: outgoing, components: [item] }] }, hook(call) {
      if (call.url === BASE + "/preview") return response({ previews: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: worktree, outgoingCommits: outgoing, action, planWillApply: false, title: "Original progress", components: [item] }] });
    } });
    await h.ready(); await openAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, expected); h.button("预览标题与改动").click(); await settle(); assert.equal(h.byClass("repository-publish-preview-version").textContent, expected); assert.equal(h.posts("/config").length, 0); assert.equal(h.posts("/run").length, 0);
  }
});
await test("automatic eligibility alone cannot replace real scoped changes or matching authority values", async () => {
  for (const patch of [{ worktreeChanged: false }, { autoPlan: { state: "eligible", fromVersion: "9.9.9", targetVersion: "2.3.5" } }, { autoPlan: { state: "eligible", fromVersion: "2.3.4", targetVersion: "9.9.9" } }, { canBump: false }]) {
    const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: true, components: [automaticComponent(patch)] }] } }); await h.ready(); await openAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.equal(h.posts().length, 0);
  }
  for (const [hasChanges, changeState] of [[false, "unchanged"], [null, "unknown"]]) {
    const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges, changeState, worktreeChanged: false, components: [automaticComponent()] }] } }); await h.ready(); await openAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.equal(h.posts().length, 0);
  }
});
await test("saved work sync differences stay green without claiming an applied version transition", async () => {
  const item = component({ autoPlan: { state: "sync_pending", fromVersion: "2.3.4", targetVersion: "", reason: "Saved sync must finish first" } });
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: false, outgoingCommits: 0, syncChanged: true, syncState: "changed", components: [item] }] }, hook(call) {
    if (call.url === BASE + "/preview") return response({ previews: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: false, syncChanged: true, action: "sync_pending", planWillApply: null, title: "Saved work awaiting sync", components: [item] }] });
  } });
  await h.ready(); await openAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "changed"); assert.equal(h.byClass("repository-publish-compact-status").textContent, "有工作文件待同步"); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4");
  h.button("预览标题与改动").click(); await settle(); assert.equal(h.byClass("repository-publish-preview-version").textContent, "2.3.4"); assert.equal(h.posts("/config").length, 0); assert.equal(h.posts("/run").length, 0);
});
await test("missing authority keeps the main version unread while failed authority remains an error", async () => {
  for (const [versionState, expected] of [["missing", "版本待读取"], ["unknown", "版本读取失败"]]) {
    const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: true, changeState: "changed", versionState, message: "No readable authoritative version", components: [] }] }, hook(call) {
      if (call.url === BASE + "/preview") return response({ previews: [{ repoId: "repository-001", versionState, title: "更新进度 2026-10-12 23:00", body: "Modified Build.blend", components: [] }] });
    } });
    await h.ready(); await openAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, expected); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "changed");
    h.button("预览标题与改动").click(); await settle(); if (versionState === "missing") assert.equal(h.byClass("repository-publish-preview-version").textContent, "无版本 · 备用标题");
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
await test("returning focus or pageshow reads only passive status until the user checks saved changes", async () => {
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", components: [component()] }] } });
  await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4");
  h.catalog.repositories[0] = { repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: true, outgoingCommits: 0, components: [automaticComponent()] };
  const checks = versionCalls(h).length; await h.emitWindow("focus"); await h.emitWindow("pageshow");
  assert.equal(versionCalls(h).length, checks); assert.equal(activityCalls(h).length, 0); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4");
  await checkAll(h); assert.equal(versionCalls(h).length, checks + 1); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.5"); assert.equal(h.posts().length, 0);
});
await test("hidden collapsed and newly visible Console never start local checks and cleanup removes hooks", async () => {
  const h = harness(); await h.ready(); await h.emitWindow("focus"); await h.emitWindow("pageshow"); await h.expand();
  await h.setPanelHidden(true); await h.emitWindow("focus"); await h.emitWindow("pageshow"); await h.setPanelHidden(false);
  assert.equal(versionCalls(h).length, 0); assert.equal(activityCalls(h).length, 0); assert.equal(h.posts().length, 0);
  const api = h.api; api.destroy(); const reads = h.calls.length; await h.emitWindow("focus"); await h.emitWindow("pageshow"); await h.setPanelHidden(true); await h.setPanelHidden(false);
  assert.equal(h.calls.length, reads); assert.equal(h.posts().length, 0);
});
await test("return refresh preserves dirty drafts, serial autosave and active publishing guards", async () => {
  const draft = harness(); await draft.ready(); await draft.open(); const input = draft.fields("notes")[0]; input.value = "Protected typing"; input.dispatch("input"); let before = draft.calls.length;
  await draft.emitWindow("focus"); await draft.emitWindow("pageshow"); await draft.setPanelHidden(true); await draft.setPanelHidden(false); assert.equal(draft.calls.length, before); assert.equal(input.value, "Protected typing"); assert.equal(draft.api.hasDraft(), true); assert.equal(draft.posts().length, 0);
  const pending = deferred(), saving = harness({ hook(call) { if (call.url === BASE + "/config") return pending.promise; } }); await saving.ready(); await saving.open(); await saving.change("notes", "Serial save"); before = saving.calls.length;
  await saving.emitWindow("focus"); await saving.emitWindow("pageshow"); assert.equal(saving.calls.length, before); pending.reject(new Error("Fixture save remains unsaved")); await settle();
  const active = harness(); await active.ready(); await expandAndCheck(active); active.byClass("repository-publish-primary").click(); await settle(); before = active.calls.length;
  await active.emitWindow("focus"); await active.emitWindow("pageshow"); await active.setPanelHidden(true); await active.setPanelHidden(false); assert.equal(active.calls.length, before); assert.equal(active.posts("/run").length, 1);
});
await test("a late cancelled manual catalog cannot repaint a hidden Console or replace the next explicit check", async () => {
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", components: [component()] }] } }); await h.ready(); await expandAndCheck(h);
  const pending = deferred(); h.hook(call => call.url.startsWith(BASE + "/versions?") ? pending.promise : undefined); await checkAll(h); await h.setPanelHidden(true); const before = versionCalls(h).length;
  pending.resolve(response(h.versionEnvelope({ repositories: [{ repoId: "repository-001", hasChanges: false, changeState: "unchanged", components: [component({ currentVersion: "9.9.9" })] }] }))); await settle();
  assert.equal(versionCalls(h).length, before); assert.notEqual(h.byClass("repository-publish-compact-version").textContent, "9.9.9");
  h.hook(null); h.catalog.repositories[0] = { repoId: "repository-001", hasChanges: true, changeState: "changed", worktreeChanged: true, components: [component({ currentVersion: "3.0.1" })] };
  await h.setPanelHidden(false); assert.equal(versionCalls(h).length, before); await checkAll(h);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "3.0.1"); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "changed"); assert.equal(h.posts().length, 0);
});
const menuComponents = () => [component({ sourceId: "idle-plugin", name: "Node library", currentVersion: "0.3.1", nextVersion: "0.3.2" }),
  automaticComponent({ sourceId: "changed-plugin", name: "Character Designer", currentVersion: "0.77.25", nextVersion: "0.77.38" }),
  component({ sourceId: "other-plugin", name: "RR Helper", currentVersion: "0.2.60", nextVersion: "0.2.61" })];
const menuCatalog = (repo = repository(), components = menuComponents(), summary = uploadSummary(repo), currentVersion = "1.2.3") => ({ repoId: repo.id, hasChanges: true, changeState: "changed", worktreeChanged: true, outgoingCommits: 0, components, uploadSummary: summary, repositoryVersion: { state: "current", currentVersion, transition: null } });
const rowFor = (h, id = "repository-001") => h.byClass("repository-publish-compact-rows").children.find(row => row.dataset.repoId === id);
const menuOptions = (h, row = rowFor(h)) => h.all(h.byClass("repository-publish-version-menu", row)).filter(item => item.dataset.sourceId);
await test("multi-plugin rows show one repository semantic version and fact-based plugin details on demand", async () => {
  const h = harness({ catalog: { repositories: [menuCatalog()] } }); await h.ready(); await expandAndCheck(h);
  const picker = h.byClass("repository-publish-version-picker"), trigger = h.byClass("repository-publish-version-trigger");
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.2.3"); assert.equal(picker.open, false);
  assert.equal(h.visible(menuOptions(h)[0]), false);
  trigger.click(); assert.equal(picker.open, true); assert.equal(h.visible(menuOptions(h)[0]), true);
  const menu = h.byClass("repository-publish-version-menu"), groups = h.all(menu).filter(item => item.tagName === "H4").map(item => item.textContent);
  assert.deepEqual(groups, ["插件版本", "本次有改动", "其他插件"]); assert.ok(h.all(menu).filter(item => item.tagName === "HR").length >= 1);
  assert.deepEqual(menuOptions(h).map(item => [item.dataset.sourceId, item.dataset.changeState, item.textContent]), [["changed-plugin", "changed", "Character Designer 0.77.38"], ["idle-plugin", "unchanged", "Node library 0.3.1"], ["other-plugin", "unchanged", "RR Helper 0.2.60"]]);
  assert.equal(h.fields("path").length, 0); assert.equal(h.posts().length, 0); assert.equal(h.api.hasDraft(), false);
});
await test("plugin details are read-only and old display preferences never replace the repository version with a chosen plugin", async () => {
  const repo = repository(), legacy = JSON.stringify({ [JSON.stringify([repo.id, repo.path, repo.repositoryUrl, repo.remote, repo.branch])]: "idle-plugin" }), storage = new Map([[DISPLAY_KEY, legacy]]);
  const h = harness({ storage, catalog: { repositories: [menuCatalog(repo)] } }); await h.ready(); await expandAndCheck(h);
  const reads = h.calls.length, settingsBefore = structuredClone(h.snapshot.settings); h.byClass("repository-publish-version-trigger").click();
  for (const item of menuOptions(h)) { assert.notEqual(item.tagName, "BUTTON"); item.click(); }
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.2.3"); assert.equal(h.storage.get(DISPLAY_KEY), legacy);
  assert.equal(h.calls.length, reads); assert.equal(h.posts().length, 0); assert.deepEqual(h.snapshot.settings, settingsBefore); assert.equal(h.api.hasDraft(), false); assert.equal(h.api.canReload(), true);
  assert.equal(h.byClass("repository-publish-primary").disabled, false); assert.equal(h.button("自动显示有改动的插件"), undefined);
});
await test("reload and plan consumption preserve the repository version independently of plugin versions and upload counts", async () => {
  const storage = new Map(), first = harness({ storage, catalog: { repositories: [menuCatalog()] } }); await first.ready(); await expandAndCheck(first); first.api.destroy();
  const repo = repository(), components = menuComponents(); components[0] = component({ ...components[0], currentVersion: "8.5.17", nextVersion: "8.5.18", worktreeChanged: true });
  const summary = uploadSummary(repo, { count: 4, commitSha: "b".repeat(40), verifiedAt: "2026-10-14T01:00:00Z" });
  const h = harness({ storage, snapshot: { settings: settings([{ ...repo, versionPlans: [planFor(components[1])] }]) }, catalog: { repositories: [menuCatalog(repo, components, summary)] } });
  await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.2.3");
  h.snapshot.settings.repositories[0].versionPlans = []; h.snapshot.settingsSha = settingsSha(h.snapshot.settings); await h.emitWindow("focus"); await checkAll(h);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.2.3"); assert.equal(h.posts().length, 0); assert.equal(h.api.hasDraft(), false);
  assert.ok(menuOptions(h).some(item => item.textContent === "Node library 8.5.17"));
});
await test("repository versions remain isolated by repository and reject a previous branch destination", async () => {
  const repos = [repository(), repository({ id: "repository-002", path: "D:/Other", repositoryUrl: "https://github.com/example/Other", branch: "feature/other" })];
  const h = harness({ snapshot: { settings: settings(repos) }, catalog: { repositories: repos.map((repo, i) => menuCatalog(repo, menuComponents(), uploadSummary(repo, { count: i + 3 }), i ? "1.5.0" : "1.2.3")) } }); await h.ready(); await expandAndCheck(h);
  assert.equal(h.byClass("repository-publish-compact-version", rowFor(h, repos[0].id)).textContent, "1.2.3"); assert.equal(h.byClass("repository-publish-compact-version", rowFor(h, repos[1].id)).textContent, "1.5.0");
  h.catalog.repositories[0].repositoryVersion.currentVersion = "1.8.0";
  await openAndCheck(h, repos[0].id); await h.change("branch", "feature/new-bound-branch"); await checkAll(h);
  assert.equal(h.byClass("repository-publish-compact-version", rowFor(h, repos[0].id)).textContent, "1.8.0"); assert.equal(h.byClass("repository-publish-compact-version", rowFor(h, repos[1].id)).textContent, "1.5.0");
  assert.equal(h.posts("/config").length, 1); assert.equal(h.posts("/run").length, 0);
});
await test("removed plugin sources refresh the details without changing the independent repository version", async () => {
  const h = harness({ catalog: { repositories: [menuCatalog()] } }); await h.ready(); await expandAndCheck(h);
  h.catalog.repositories[0].components = menuComponents().filter(item => item.sourceId !== "idle-plugin"); await h.emitWindow("focus"); await checkAll(h);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.2.3"); assert.equal(menuOptions(h).length, 2); assert.equal(menuOptions(h).some(item => item.dataset.sourceId === "idle-plugin"), false);
  h.catalog.repositories[0].components = menuComponents(); await h.emitWindow("focus"); await checkAll(h);
  assert.equal(h.all().filter(item => item.className.split(" ").includes("repository-publish-compact-version")).length, 1); assert.equal(h.posts().length, 0);
});
await test("unavailable browser storage never blocks repository-version and plugin detail rendering", async () => {
  const h = harness({ storageUnavailable: true, catalog: { repositories: [menuCatalog()] } }); await h.ready(); await expandAndCheck(h);
  const reads = h.calls.length; h.byClass("repository-publish-version-trigger").click(); for (const item of menuOptions(h)) item.click();
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.2.3"); assert.equal(h.byClass("repository-publish-primary").disabled, false);
  assert.equal(h.api.hasDraft(), false); assert.equal(h.api.canReload(), true); assert.equal(h.calls.length, reads); assert.equal(h.posts().length, 0);
});
await test("locale changes preserve the repository semantic version and translate detail labels without changing plans", async () => {
  const h = harness({ catalog: { repositories: [menuCatalog()] } }); await h.ready(); await expandAndCheck(h);
  const settingsBefore = structuredClone(h.snapshot.settings), reads = h.calls.length; h.byClass("repository-publish-version-trigger").click(); h.locale("en");
  assert.equal(h.byClass("repository-publish-version-picker").open, false);
  assert.deepEqual(h.all(h.byClass("repository-publish-version-menu")).filter(item => item.tagName === "H4").map(item => item.textContent), ["Plugin versions", "Changed plugins", "Other plugins"]);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.2.3"); assert.deepEqual(h.snapshot.settings, settingsBefore); assert.equal(h.calls.length, reads); assert.equal(h.posts().length, 0);
});
await test("unknown plugin changes and missing repository authority are not presented as unchanged or a fabricated version", async () => {
  const unknown = component({ sourceId: "unknown-plugin", name: "Unknown", worktreeChanged: null, versionChanged: null }), other = component({ sourceId: "known-plugin", name: "Other", worktreeChanged: null, versionChanged: null });
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: null, changeState: "unknown", worktreeChanged: null, components: [unknown, other], uploadSummary: uploadSummary(repository(), { state: "unknown", count: null, reason: "Historical uploads cannot be verified" }) }] } }); await h.ready(); await expandAndCheck(h);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "版本待读取"); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown"); assert.equal(h.byClass("repository-publish-compact-status").textContent, "变化未核对");
  assert.deepEqual(menuOptions(h).map(item => item.dataset.changeState), ["unknown", "unknown"]); const labels = h.all(h.byClass("repository-publish-version-menu")).map(item => item.textContent).join(" "); assert.doesNotMatch(labels, /无改动|无变化|本次有改动/); assert.equal(h.posts().length, 0);
});
await test("read-only upload detail menus close on Escape and outside click and opening another closes the first", async () => {
  const repos = [repository(), repository({ id: "repository-002", path: "D:/Other" })], h = harness({ snapshot: { settings: settings(repos) }, catalog: { repositories: repos.map(repo => menuCatalog(repo)) } }); await h.ready(); await expandAndCheck(h);
  const first = h.byClass("repository-publish-version-picker", rowFor(h, repos[0].id)), second = h.byClass("repository-publish-version-picker", rowFor(h, repos[1].id)), trigger = h.byClass("repository-publish-version-trigger", rowFor(h, repos[0].id)); trigger.click();
  const escaped = first.dispatch("keydown", { key: "Escape" }); assert.equal(escaped.defaultPrevented, true); assert.equal(first.open, false); assert.equal(h.document.activeElement, trigger);
  trigger.click(); h.document.emit("click", { target: h.byClass("repository-publish-version-menu", rowFor(h, repos[0].id)) }); assert.equal(first.open, true); h.document.emit("click", { target: h.host }); assert.equal(first.open, false);
  trigger.click(); h.byClass("repository-publish-version-trigger", rowFor(h, repos[1].id)).click(); assert.equal(first.open, false); assert.equal(second.open, true);
  h.api.destroy(); second.open = true; h.document.emit("click", { target: h.host }); assert.equal(second.open, true); assert.equal(h.posts().length, 0);
});
await test("silent checking preserves old detail state while hiding or collapsing Console closes menus", async () => {
  const repo = repository({ versionSources: [{ path: "plugins/Designer/__init__.py", kind: "bl_info", key: "version", name: "Designer" }, { path: "plugins/Nodes/__init__.py", kind: "bl_info", key: "version", name: "Nodes" }] }), summary = uploadSummary(repo), h = harness({ snapshot: { settings: settings([repo]), uploadSummaries: [{ repoId: repo.id, ...summary }] }, catalog: { repositories: [menuCatalog(repo)] } }); await h.ready(); await expandAndCheck(h);
  const picker = h.byClass("repository-publish-version-picker"), trigger = h.byClass("repository-publish-version-trigger"), pending = deferred(); trigger.click();
  h.hook(call => call.url.startsWith(BASE + "/versions?") ? pending.promise : undefined); await h.emitWindow("focus"); await checkAll(h); assert.equal(picker.open, true); assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.2.3");
  pending.resolve(response(h.versionEnvelope({ repositories: [menuCatalog(repo)] }))); await settle(); h.hook(null); trigger.click(); await h.setPanelHidden(true); assert.equal(picker.open, false); await h.setPanelHidden(false);
  trigger.click(); await h.expand(); assert.equal(picker.open, false); await h.expand(); assert.equal(picker.open, false);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.2.3"); assert.equal(h.posts().length, 0); assert.equal(h.api.hasDraft(), false);
});
await test("missing or malformed upload summaries never replace an authoritative repository semantic version", async () => {
  const repo = repository();
  for (const summary of [undefined, null, {}, uploadSummary(repo, { count: -1 }), uploadSummary(repo, { count: 1.5 }), uploadSummary(repo, { count: "7" }), uploadSummary(repo, { state: "success" }), uploadSummary(repo, { source: "git_history" }), uploadSummary(repo, { state: "pending", count: null }), uploadSummary(repo, { binding: null }), uploadSummary(repo, { commitSha: "invalid" }), uploadSummary(repo, { verifiedAt: "not a date" }), uploadSummary(repo, { binding: { ...uploadSummary(repo).binding, remote: "different-origin" } })]) {
    const h = harness({ catalog: { repositories: [menuCatalog(repo, menuComponents(), summary)] } }); if (summary === undefined) delete h.catalog.repositories[0].uploadSummary; await h.ready(); await expandAndCheck(h);
    assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.2.3"); assert.equal(h.posts().length, 0); assert.equal(h.api.hasDraft(), false);
  }
  const zero = harness({ catalog: { repositories: [menuCatalog(repo, menuComponents(), uploadSummary(repo, { count: 0, commitSha: "", verifiedAt: "", startedAt: "" }))] } }); await zero.ready(); await expandAndCheck(zero); assert.equal(zero.byClass("repository-publish-compact-version").textContent, "1.2.3");
});
const progressText = h => h.byClass("repository-publish-status").textContent;
const assertProgress = (h, finished, total) => { const text = progressText(h); assert.match(text, new RegExp(`\\b${finished}\\s*[/／]\\s*${total}\\b`)); assert.doesNotMatch(text, /\d+(?:\.\d+)?\s*%/); assert.equal(h.byClass("repository-publish-progress"), undefined, "there must be no aggregate progress bar in the toolbar"); return text; };
const progressRepos = () => Array.from({ length: 5 }, (_, i) => repository({ id: `progress-repo-${i + 1}`, path: `D:/Progress/Repo${i + 1}`, repositoryUrl: `https://github.com/example/Progress${i + 1}` }));
const progressItem = (repo, status = "queued", phase = "queued") => ({ repoId: repo.id, name: `Repository ${repo.id.slice(-1)}`, status, phase, message: "Fixture actual phase", uploadSummary: uploadSummary(repo) });
await test("mixed real queue progress counts finished repositories without pretending to know transfer percent", async () => {
  const repos = progressRepos(), id = randomUUID(), rows = [progressItem(repos[0], "success", "complete"), progressItem(repos[1], "working", "push"), ...repos.slice(2).map(repo => progressItem(repo))];
  const h = harness({ storage: new Map([[KEY, id]]), snapshot: { settings: settings(repos), operation: { ...operation(id, "working", rows), percent: 100, progress: { percent: 100 } } } }); await h.ready();
  const text = assertProgress(h, 1, 5); assert.match(text, /Progress2/); assert.match(text, /推送|上传/); assert.equal(h.storage.get(KEY), id); assert.equal(h.byClass("repository-publish-primary").disabled, true); assert.equal(h.posts().length, 0);
});
await test("each actual working phase is visible while the denominator stays bound to the original operation", async () => {
  const repos = progressRepos(), id = randomUUID();
  for (const [phase, expected] of [["check", /检查|核对/], ["sync", /同步/], ["remote", /远端/], ["version", /版本|升版/], ["commit", /提交/], ["push", /推送|上传/], ["verify", /核对|验证|核验/]]) {
    const h = harness({ storage: new Map([[KEY, id]]), snapshot: { settings: settings(repos), operation: operation(id, "working", [progressItem(repos[0], "working", phase), ...repos.slice(1).map(repo => progressItem(repo))]) } }); await h.ready();
    assert.match(assertProgress(h, 0, 5), expected); assert.equal(h.posts().length, 0); h.api.destroy();
  }
});
await test("completed mixed batch distinguishes successful uploads, skips, failures and pending verification", async () => {
  const repos = progressRepos(), id = randomUUID(), statuses = ["success", "noop", "push_failed", "verification_required", "deferred"];
  const h = harness({ snapshot: { settings: settings(repos), operation: operation(id, "attention", repos.map((repo, i) => progressItem(repo, statuses[i], statuses[i] === "verification_required" ? "verify" : "complete"))) } }); await h.ready();
  const text = assertProgress(h, 5, 5); assert.match(text, /成功\s*1|已上传\s*1|已推送\s*1/); assert.match(text, /跳过\s*1/); assert.match(text, /待核对\s*1/); assert.match(text, /需处理\s*2|失败\s*2/); assert.equal(h.posts().length, 0); assert.equal(h.byClass("repository-publish-primary").disabled, false);
});
await test("all-noop completion never reports successful uploads or advances any upload counter", async () => {
  const repos = progressRepos(), id = randomUUID(), h = harness({ snapshot: { settings: settings(repos), operation: operation(id, "success", repos.map(repo => progressItem(repo, "noop", "complete"))) }, catalog: { repositories: [menuCatalog(repos[0])] } }); await h.ready(); await expandAndCheck(h);
  const text = assertProgress(h, 5, 5); assert.match(text, /跳过\s*5/); assert.doesNotMatch(text, /成功\s*[1-9]|已上传\s*[1-9]|已推送\s*[1-9]/); assert.equal(h.byClass("repository-publish-compact-version", rowFor(h, repos[0].id)).textContent, "1.2.3"); assert.equal(h.posts().length, 0);
});
await test("poll disconnection retains the pending operation and last known progress without resending", async () => {
  const repos = progressRepos(), id = randomUUID(), original = operation(id, "working", [progressItem(repos[0], "success", "complete"), progressItem(repos[1], "working", "push"), ...repos.slice(2).map(repo => progressItem(repo))]);
  const h = harness({ storage: new Map([[KEY, id]]), snapshot: { settings: settings(repos), operation: original }, hook(call) { if (call.url.startsWith(BASE + "/operation?")) throw new Error("Fixture offline"); } }); await h.ready(); await h.poll();
  const text = assertProgress(h, 1, 5); assert.match(text, /核对|确认|读取|连接|追踪/); assert.equal(h.storage.get(KEY), id); assert.equal(h.byClass("repository-publish-primary").disabled, true); assert.equal(h.posts().length, 0);
  h.hook(null); h.snapshot.operation = operation(id, "attention", repos.map((repo, i) => progressItem(repo, i < 2 ? "success" : "deferred", "complete"))); await h.poll(); assertProgress(h, 5, 5); assert.equal(h.storage.has(KEY), false); assert.equal(h.posts().length, 0);
});
await test("working multi-plugin rows keep their repository version and show real phase without reverting to plugin text", async () => {
  const repo = repository(), summary = uploadSummary(repo), h = harness({ snapshot: { uploadSummaries: [{ repoId: repo.id, ...summary }] }, catalog: { repositories: [menuCatalog(repo)] } }); await h.ready(); await expandAndCheck(h);
  h.byClass("repository-publish-primary").click(); await settle(); const id = h.posts("/run")[0].body.requestId;
  h.snapshot.operation = operation(id, "working", [progressItem(repo, "working", "push")]); await h.poll();
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.2.3"); assert.doesNotMatch(h.byClass("repository-publish-compact-version").textContent, /Node library|Character|RR Helper/); assert.match(h.byClass("repository-publish-compact-status").textContent, /推送|上传/); assertProgress(h, 0, 1); assert.equal(h.posts("/run").length, 1);
  const completed = uploadSummary(repo, { count: 4, commitSha: "b".repeat(40), verifiedAt: "2026-10-14T01:00:00Z" }); h.snapshot.uploadSummaries = [{ repoId: repo.id, ...completed }]; h.catalog.repositories[0].uploadSummary = completed;
  h.snapshot.operation = operation(id, "success", [{ ...progressItem(repo, "success", "complete"), uploadSummary: completed }]); await h.poll(); await checkAll(h);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.2.3"); assertProgress(h, 1, 1); assert.equal(h.posts("/run").length, 1); assert.equal(h.posts("/config").length, 0);
});
await test("a stale operation binding cannot replace the newly configured repository version", async () => {
  const repo = repository(), current = { ...repo, branch: "feature/rebound" }, id = randomUUID(), stale = uploadSummary(repo, { count: 91 });
  const h = harness({ snapshot: { settings: settings([current]), operation: operation(id, "attention", [{ ...progressItem(repo, "push_failed", "push"), uploadSummary: stale }]), uploadSummaries: [{ repoId: repo.id, ...stale }] }, catalog: { repositories: [menuCatalog(current, menuComponents(), { ...stale })] } }); await h.ready(); await expandAndCheck(h);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.2.3"); assert.equal(h.posts().length, 0);
});
await test("a terminal batch with an unrecognized row status never pretends all repositories finished", async () => {
  const repos = progressRepos(), id = randomUUID(), statuses = ["success", "noop", "deferred", "verification_required", "unrecognized_old_status"];
  const h = harness({ snapshot: { settings: settings(repos), operation: { ...operation(id, "success", repos.map((repo, i) => progressItem(repo, statuses[i], "complete"))), progress: { percent: 100, completed: 5, total: 5 } } } }); await h.ready();
  const text = assertProgress(h, 4, 5); assert.match(text, /等待.*回执/); assert.equal(h.byClass("repository-publish-progress-fill"), undefined); assert.equal(h.posts().length, 0);
});
await test("clicking an individual repository status opens only its operation details without publishing or changing plans", async () => {
  const repos = progressRepos(), id = randomUUID(), h = harness({ snapshot: { settings: settings(repos), operation: operation(id, "attention", repos.map((repo, i) => progressItem(repo, i === 1 ? "push_failed" : "noop", "complete"))) } }); await h.ready(); await expandAndCheck(h);
  const settingsBefore = structuredClone(h.snapshot.settings), button = h.byClass("repository-publish-compact-status", rowFor(h, repos[1].id)); assert.equal(button.tagName, "BUTTON"); assert.equal(button.type, "button"); button.click(); await settle();
  assert.equal(h.byClass("repository-publish-dialog").open, true); const results = h.byClass("repository-publish-results"), detail = h.all().find(item => item.tagName === "DETAILS" && item.children.includes(results)); assert.equal(detail.open, false); assert.equal(results.children.length, 1); assert.match(results.children[0].children[0].textContent, /2/);
  assert.equal(h.posts().length, 0); assert.deepEqual(h.snapshot.settings, settingsBefore); assert.equal(h.api.hasDraft(), false); assert.equal(h.byClass("repository-publish-primary").disabled, false);
});
await test("a confirmed upload with pending counter persistence remains successful and retries only after the user asks", async () => {
  const repo = repository({ versionSources: [{ path: "plugins/Designer/__init__.py", kind: "bl_info", key: "version" }, { path: "plugins/Nodes/__init__.py", kind: "bl_info", key: "version" }] }), id = randomUUID();
  const pending = uploadSummary(repo, { state: "pending", count: null, reason: "Upload confirmed; counter persistence needs recovery" });
  const h = harness({ snapshot: { settings: settings([repo]), uploadSummaries: [{ repoId: repo.id, ...pending }], operation: operation(id, "success", [{ ...progressItem(repo, "success", "complete"), uploadSummary: pending }]) }, catalog: { repositories: [menuCatalog(repo, menuComponents(), pending)] } }); await h.ready(); await expandAndCheck(h);
  const text = assertProgress(h, 1, 1); assert.match(text, /成功\s*1/); assert.match(text, /上传记录待核对\s*1/); assert.doesNotMatch(text, /需处理|失败|(?<!记录)待核对\s*1/);
  assert.equal(h.byClass("repository-publish-progress"), undefined); assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.2.3");
  const status = h.byClass("repository-publish-compact-status"); assert.equal(status.textContent, "有待提交改动"); assert.match(h.byClass("repository-publish-row-history").textContent, /上次上传.*记录待核对/); assert.doesNotMatch(status.textContent, /失败/); assert.equal(h.posts().length, 0);
  status.click(); await settle(); const retry = h.button("继续此仓库"); assert.ok(retry); assert.equal(retry.disabled, false); assert.equal(h.posts().length, 0); assert.equal(h.api.hasDraft(), false);
  retry.click(); retry.click(); await settle(); assert.equal(h.posts("/run").length, 1); assert.deepEqual(h.posts("/run")[0].body.repoIds, [repo.id]); assert.notEqual(h.posts("/run")[0].body.requestId, id); assert.equal(h.posts("/config").length, 0);
});
await test("an explicit status refresh disconnection keeps known repository progress and pending identity", async () => {
  const repos = progressRepos(), id = randomUUID(), rows = [progressItem(repos[0], "success", "complete"), progressItem(repos[1], "push_failed", "push"), progressItem(repos[2], "working", "push"), progressItem(repos[3], "verification_required", "verify"), progressItem(repos[4])];
  const h = harness({ storage: new Map([[KEY, id]]), snapshot: { settings: settings(repos), operation: operation(id, "working", rows) } }); await h.ready();
  assert.match(assertProgress(h, 3, 5), /需处理\s*1.*待核对\s*1/); h.hook(call => { if (call.url === BASE && call.method === "GET") throw new Error("Fixture status refresh offline"); }); await h.api.refresh(); await settle();
  const text = assertProgress(h, 3, 5); assert.match(text, /状态读取失败/); assert.match(text, /Progress3/); assert.equal(h.storage.get(KEY), id); assert.equal(h.byClass("repository-publish-primary").disabled, true); assert.equal(h.posts().length, 0);
});
await test("changing branch or path never labels the new target Uploaded from a previous successful receipt", async () => {
  for (const [field, target] of [["branch", "feature/new-target"], ["path", "D:/New/Checkout"]]) {
    const repo = repository(), id = randomUUID(), h = harness({ snapshot: { settings: settings([repo]), operation: operation(id, "success", [progressItem(repo, "success", "complete")]) }, catalog: { repositories: [{ repoId: repo.id, components: [], hasChanges: false, changeState: "unchanged" }] } }); await h.ready(); await expandAndCheck(h);
    assert.equal(h.byClass("repository-publish-compact-status").textContent, "无改动"); assert.equal(h.byClass("repository-publish-row-history").textContent, "上次上传"); await h.open(repo.id); await h.change(field, target); h.button("关闭").click();
    const status = h.byClass("repository-publish-compact-status"); assert.match(status.textContent, /历史回执/); assert.doesNotMatch(status.textContent, /已上传/); status.click(); await settle();
    assert.equal(h.byClass("repository-publish-dialog").open, true); const detailText = h.all(h.byClass("repository-publish-results")).map(item => item.textContent).join(" "); assert.match(detailText, /历史回执|历史目标|原.*目标/); assert.ok(detailText.includes(repo.path)); assert.ok(detailText.includes(repo.branch));
    assert.equal(h.button("继续此仓库"), undefined); assert.equal(h.posts("/run").length, 0); assert.equal(h.posts("/config").length, 1); assert.equal(h.api.hasDraft(), false); assertProgress(h, 1, 1);
  }
});
await test("old failed or unbound receipts have no cross-target retry while a bound past failure retains its explicit retry", async () => {
  const previous = repository(), current = { ...previous, branch: "feature/rebound" };
  for (const result of [progressItem(previous, "push_failed", "push"), { repoId: previous.id, name: "Unbound legacy receipt", status: "push_failed", phase: "push", message: "Original target not recorded" }]) {
    const h = harness({ snapshot: { settings: settings([current]), operation: operation(randomUUID(), "attention", [result]) } }); await h.ready(); await expandAndCheck(h);
    const status = h.byClass("repository-publish-compact-status"); assert.match(status.textContent, /历史回执/); status.click(); await settle(); assert.equal(h.button("继续此仓库"), undefined); assert.equal(h.posts().length, 0);
  }
  const h = harness({ snapshot: { settings: settings([current]), operation: operation(randomUUID(), "attention", [progressItem(current, "push_failed", "push")]) } }); await h.ready(); await expandAndCheck(h);
  const status = h.byClass("repository-publish-compact-status"); assert.equal(status.dataset.attention, "false"); assert.doesNotMatch(status.textContent, /无改动|失败|历史回执/); status.click(); await settle(); const retry = h.button("继续此仓库"); assert.ok(retry); assert.equal(h.posts().length, 0); retry.click(); await settle(); assert.equal(h.posts("/run").length, 1); assert.deepEqual(h.posts("/run")[0].body.repoIds, [current.id]); assert.equal(h.posts("/config").length, 0);
});
const diagnostic = (extra = {}) => ({ code: "branch_mismatch", category: "connection", severity: "warning", summary: "Checked branch differs from configured branch.", nextStep: "Review the branch setting; preserve your work.", target: { section: "connection", field: "branch" }, ...extra });
await test("status opens the reason at the dialog top and only explicit Locate focuses the named setting", async () => {
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", hasChanges: null, changeState: "unknown", components: [], diagnostic: diagnostic(), message: "Checked branch differs from configured branch." }] } }); await h.ready(); await expandAndCheck(h);
  h.byClass("repository-publish-dialog").scrollTop = 460;
  const calls = h.calls.length, button = h.byClass("repository-publish-compact-status"); assert.equal(button.disabled, false); button.click(); await settle();
  assert.equal(h.byClass("repository-publish-dialog").open, true); assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, "Checked branch differs from configured branch."); assert.match(h.byClass("repository-publish-diagnosis-next").textContent, /Review the branch/);
  assert.equal(h.byClass("repository-publish-dialog").scrollTop, 0); assert.equal(h.byClass("repository-publish-diagnosis").hidden, false); assert.equal(h.byClass("repository-publish-connection").open, false); assert.notEqual(h.document.activeElement, h.fields("branch")[0]); assert.equal(h.fields("branch")[0].scrollIntoViewCount, 0);
  h.byClass("repository-publish-diagnosis-locate").click();
  assert.equal(h.byClass("repository-publish-connection").open, true); assert.equal(h.document.activeElement, h.fields("branch")[0]); assert.equal(h.fields("branch")[0].value, "feature/music"); assert.ok(h.fields("branch")[0].getAttribute("aria-describedby"));
  assert.equal(h.fields("branch")[0].scrollIntoViewCount, 1);
  assert.equal(h.calls.length, calls + 1); assert.ok(h.calls.slice(calls).every(call => call.method === "GET" && call.url === BASE)); assert.equal(activityCalls(h).length, 0); assert.equal(h.posts().length, 0); assert.equal(h.api.hasDraft(), false);
});
await test("explicit sync diagnostics open the mapping while preserving saved paths and raw drafts", async () => {
  const repo = repository({ syncFiles: [{ source: "D:/Saved/Builder6.blend", target: "Build.blend" }] }), value = diagnostic({ code: "sync_missing", category: "sync", severity: "error", summary: "The configured saved work file is missing.", nextStep: "Save it in Blender or correct its source path.", target: { section: "sync", field: "sync" } });
  const h = harness({ snapshot: { settings: settings([repo]) }, catalog: { repositories: [{ repoId: repo.id, components: [], syncState: "unknown", syncReason: value.summary, diagnostic: value }] } }); await h.ready(); await expandAndCheck(h); h.byClass("repository-publish-compact-status").click(); await settle();
  assert.notEqual(h.document.activeElement, h.fields("sync")[0]); h.byClass("repository-publish-diagnosis-locate").click();
  assert.equal(h.document.activeElement, h.fields("sync")[0]); assert.equal(h.fields("sync")[0].value, "D:/Saved/Builder6.blend -> Build.blend"); assert.equal(h.posts().length, 0);
  await h.change("sync", "unfinished ->"); const raw = h.fields("sync")[0], posts = h.posts().length; h.byClass("repository-publish-compact-status").click(); await settle();
  assert.equal(h.fields("sync")[0], raw); assert.equal(raw.value, "unfinished ->"); assert.equal(h.api.hasDraft(), true); assert.equal(h.posts().length, posts); assert.equal(h.posts("/run").length, 0);
});
await test("the trusted component source ID selects its own version field instead of the first plugin", async () => {
  const sources = [{ path: "first.json", kind: "json", key: "version", name: "First" }, { path: "second.json", kind: "json", key: "version", name: "Second" }], repo = repository({ versionSources: sources });
  const components = sources.map((source, i) => component({ ...source, sourceId: `version-authority-${i + 1}` })), value = diagnostic({ code: "version_authority", category: "versions", summary: "The second authority needs review.", target: { section: "versions", field: "versionPath", sourceId: components[1].sourceId } });
  const h = harness({ snapshot: { settings: settings([repo]) }, catalog: { repositories: [{ repoId: repo.id, components, diagnostic: value }] } }); await h.ready(); await expandAndCheck(h); h.byClass("repository-publish-compact-status").click(); await settle();
  assert.notEqual(h.document.activeElement, h.fields("versionPath")[1]); h.byClass("repository-publish-diagnosis-locate").click();
  assert.equal(h.document.activeElement, h.fields("versionPath")[1]); assert.equal(h.fields("versionPath")[0].value, "first.json"); assert.equal(h.fields("versionPath")[1].value, "second.json"); assert.equal(h.posts().length, 0);
});
await test("fallback naming is informative and opens the existing global title without a failure or write", async () => {
  const value = diagnostic({ code: "version_fallback", category: "naming", severity: "info", summary: "No independent version source; the saved progress title is used.", nextStep: "Keep the saved title or review naming.", target: { section: "naming", field: "fallbackTitle" } });
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", components: [], hasChanges: false, changeState: "unchanged", versionState: "missing", diagnostic: value }] } }); await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-status").textContent, "无改动"); h.byClass("repository-publish-compact-status").click(); await settle();
  assert.notEqual(h.document.activeElement, h.fields("fallback")[0]); h.byClass("repository-publish-diagnosis-locate").click();
  assert.equal(h.document.activeElement, h.fields("fallback")[0]); assert.equal(h.fields("fallback")[0].value, "更新进度 {datetime}"); assert.equal(h.posts().length, 0); assert.equal(h.api.hasDraft(), false);
});
await test("unknown messages and benign nonempty reasons never generate a configuration fix or failure", async () => {
  for (const item of [{ message: "A binary file changed; no feature diagnosis is known." }, { changesReason: "Read from a saved local tracking reference." }, { syncState: "unchanged", syncReason: "The saved source and snapshot match." }]) {
    const h = harness({ catalog: { repositories: [{ repoId: "repository-001", components: [component()], hasChanges: false, changeState: "unchanged", ...item }] } }); await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-status").textContent, "无改动"); h.byClass("repository-publish-compact-status").click(); await settle();
    assert.equal(h.byClass("repository-publish-diagnosis-locate").hidden, true); assert.equal(h.byClass("repository-publish-diagnosis").dataset.severity, "info"); assert.equal(h.posts().length, 0);
  }
});
await test("malicious or unsupported diagnostic targets remain inert text and cannot choose arbitrary controls", async () => {
  for (const value of [diagnostic({ target: { section: "__proto__", field: "path" } }), diagnostic({ target: { section: "connection", field: "notes" } }), diagnostic({ code: "manual_check", category: "unknown" }), diagnostic({ code: "version_authority", category: "versions", target: { section: "versions", field: "versionPath" } }), diagnostic({ code: "branch_mismatch", target: { section: "connection", field: "path" } })]) {
    value.summary = '<img src=x onerror="evil()">'; const h = harness({ catalog: { repositories: [{ repoId: "repository-001", components: [], diagnostic: value }] } }); await h.ready(); await expandAndCheck(h); h.byClass("repository-publish-compact-status").click(); await settle();
    assert.equal(h.byClass("repository-publish-diagnosis-locate").hidden, true); assert.ok(h.byClass("repository-publish-diagnosis-summary").textContent.includes("<img")); assert.equal(h.all().some(item => item.tagName === "IMG"), false); assert.equal(h.document.activeElement, null); assert.equal(h.posts().length, 0);
  }
});
await test("diagnosis recheck uses one full Check All transaction with no per-row spinner", async () => {
  const pending = deferred(), repos = [repository(), repository({ id: "repository-002", path: "D:/Other" })], h = harness({ snapshot: { settings: settings(repos) }, catalog: { repositories: repos.map(repo => ({ repoId: repo.id, components: [component()] })) } });
  await h.ready(); await expandAndCheck(h); h.byClass("repository-publish-compact-status").click(); await settle();
  h.hook(call => call.url.startsWith(BASE + "/versions?") ? pending.promise : undefined); const calls = h.calls.length, before = h.byClass("repository-publish-compact-status").textContent; h.byClass("repository-publish-diagnosis-recheck").click(); await settle();
  assert.equal(h.calls.length, calls + 1); assert.equal(h.calls.at(-1).method, "GET"); assert.equal(h.calls.at(-1).url, BASE + "/versions?snapshot=1&refresh=1"); assert.equal([...h.timers.values()].filter(timer => timer.delay === 10000).length, 1);
  assert.equal(h.byClass("repository-publish-compact-status").textContent, before); assert.equal(h.byClass("repository-publish-row-spinner").hidden, true); assert.equal(h.byClass("repository-publish-primary").disabled, true);
  pending.resolve(response(h.versionEnvelope({ repositories: [{ repoId: repos[0].id, components: [component({ currentVersion: "2.3.5" })], hasChanges: true, changeState: "changed", worktreeChanged: true }, { repoId: repos[1].id, components: [component()] }] }))); await settle();
  assert.equal(h.byClass("repository-publish-compact-version", rowFor(h, repos[0].id)).textContent, "2.3.5"); assert.equal(h.byClass("repository-publish-compact-version", rowFor(h, repos[1].id)).textContent, "2.3.4"); assert.equal(h.posts().length, 0); assert.equal(h.timers.size, 0);
});
await test("status details remain clickable during a silent manual request and timeout restores the main controls", async () => {
  const h = harness({ hook(call) { if (call.url.startsWith(BASE + "/versions?")) return new Promise((resolve, reject) => call.options.signal.addEventListener("abort", () => reject(new Error("Fixture timeout")), { once: true })); } }); await h.ready(); await expandAndCheck(h);
  const status = h.byClass("repository-publish-compact-status"); assert.equal(status.disabled, false); status.click(); await settle(); assert.equal(h.byClass("repository-publish-dialog").open, true); assert.equal(h.byClass("repository-publish-row-activity").hidden, true);
  const [timerId, timer] = [...h.timers].find(([, item]) => item.delay === 10000); timer.fn(); await settle();
  assert.equal(h.timers.has(timerId), false); assert.equal(h.byClass("repository-publish-check").disabled, false); assert.equal(h.byClass("repository-publish-primary").disabled, false); assert.equal(h.byClass("repository-publish-row-activity").hidden, true); assert.equal(h.posts().length, 0); assert.equal(versionCalls(h).length, 1);
});
await test("a failed refresh retains last known versions and the safe HTTP reason instead of relabeling it authentication", async () => {
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", components: [component()] }] } }); await h.ready(); await expandAndCheck(h);
  h.hook(call => call.url.startsWith(BASE + "/versions?") ? { ok: false, status: 503, json: async () => ({ error: "Local repository service unavailable; retain original receipts.", code: "service_unavailable" }) } : undefined); await h.emitWindow("focus"); await checkAll(h);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); h.byClass("repository-publish-compact-status").click(); await settle(); assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, "Local repository service unavailable; retain original receipts."); assert.match(h.byClass("repository-publish-diagnosis-meta").textContent, /上次读取/); assert.equal(h.byClass("repository-publish-diagnosis-locate").hidden, true); assert.equal(h.posts().length, 0);
});
await test("late cancelled check diagnostics cannot focus or replace a newly saved branch", async () => {
  const pending = deferred(), h = harness({ catalog: { repositories: [{ repoId: "repository-001", components: [component()] }] } }); await h.ready(); await expandAndCheck(h); await h.open("repository-001");
  const oldReply = h.versionEnvelope({ repositories: [{ repoId: "repository-001", components: [], diagnostic: diagnostic({ code: "repo_missing", severity: "error", summary: "Stale old checkout is missing", target: { section: "connection", field: "path" } }) }] });
  h.hook(call => call.url.startsWith(BASE + "/versions?") ? pending.promise : undefined); await checkAll(h); await h.setPanelHidden(true); await h.setPanelHidden(false);
  await h.change("branch", "feature/reviewed-new-target"); const before = h.document.activeElement; pending.resolve(response(oldReply)); await settle();
  assert.doesNotMatch(h.byClass("repository-publish-diagnosis-summary").textContent, /Stale old checkout/); assert.equal(h.document.activeElement, before); assert.equal(h.fields("branch")[0].value, "feature/reviewed-new-target"); assert.equal(h.posts("/run").length, 0);
});
await test("diagnosis viewing and locating preserve an unsaved configuration and never autosave it", async () => {
  const h = harness({ catalog: { repositories: [{ repoId: "repository-001", components: [], diagnostic: diagnostic() }] }, hook(call) { if (call.url === BASE + "/config") throw new Error("Fixture save failed"); } }); await h.ready(); await expandAndCheck(h); h.byClass("repository-publish-compact-status").click(); await h.change("notes", "Protected unsaved notes");
  const field = h.fields("notes")[0], writes = h.posts().length; h.byClass("repository-publish-compact-status").click(); h.byClass("repository-publish-diagnosis-locate").click(); await settle(); assert.equal(h.fields("notes")[0], field); assert.equal(field.value, "Protected unsaved notes"); assert.equal(h.api.hasDraft(), true); assert.equal(h.posts().length, writes); assert.equal(h.byClass("repository-publish-diagnosis-recheck").disabled, true); assert.equal(h.posts("/run").length, 0);
});
await test("a historical diagnosis does not focus new-target settings or offer a cross-target retry", async () => {
  const previous = repository(), current = { ...previous, branch: "feature/new-target" }, result = { ...progressItem(previous, "push_failed", "push"), diagnostic: diagnostic() }, h = harness({ snapshot: { settings: settings([current]), operation: operation(randomUUID(), "attention", [result]) } }); await h.ready(); await expandAndCheck(h); h.byClass("repository-publish-compact-status").click(); await settle();
  assert.match(h.byClass("repository-publish-compact-status").textContent, /历史回执/); assert.equal(h.byClass("repository-publish-diagnosis-locate").hidden, true); assert.equal(h.button("继续此仓库"), undefined); assert.equal(h.posts().length, 0); assert.notEqual(h.document.activeElement, h.fields("branch")[0]);
});
await test("an asynchronous recheck updates the reason without stealing focus, scrolling or reopening a setting", async () => {
  const pending = deferred(), value = diagnostic({ code: "remote_config", summary: "The configured remote needs review.", target: { section: "connection", field: "remote" } }), h = harness({ catalog: { repositories: [{ repoId: "repository-001", components: [component()], diagnostic: value }] } });
  await h.ready(); await expandAndCheck(h); h.byClass("repository-publish-compact-status").click(); await settle(); h.byClass("repository-publish-diagnosis-locate").click();
  const remote = h.fields("remote")[0], notes = h.fields("notes")[0], dialog = h.byClass("repository-publish-dialog"); assert.equal(h.document.activeElement, remote); assert.equal(remote.scrollIntoViewCount, 1);
  h.hook(call => call.url.startsWith(BASE + "/versions?") ? pending.promise : undefined); h.byClass("repository-publish-diagnosis-recheck").click(); await settle(); notes.focus(); notes.value = "Protected typing during recheck"; notes.dispatch("input"); dialog.scrollTop = 240; h.byClass("repository-publish-connection").open = false;
  const focused = notes.focusCount, remoteFocus = remote.focusCount, remoteScroll = remote.scrollIntoViewCount;
  pending.resolve(response(h.versionEnvelope({ repositories: [{ repoId: "repository-001", components: [component()], diagnostic: diagnostic({ code: "repo_missing", severity: "error", summary: "The new local check needs a path review.", target: { section: "connection", field: "path" } }) }] }))); await settle();
  assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, "The new local check needs a path review."); assert.equal(h.document.activeElement, notes); assert.equal(notes.focusCount, focused); assert.equal(remote.focusCount, remoteFocus); assert.equal(remote.scrollIntoViewCount, remoteScroll); assert.equal(h.fields("path")[0].scrollIntoViewCount, 0); assert.equal(h.byClass("repository-publish-connection").open, false); assert.equal(dialog.scrollTop, 240); assert.equal(notes.value, "Protected typing during recheck"); assert.equal(h.api.hasDraft(), true); assert.equal(h.posts().length, 0);
});
const cachedEnvelope = (repo, item, readState = "reading", extra = {}) => {
  const sourceIdentity = "fixture-saved-source-" + settingsSha(repo);
  const checkedAt = readState === "ready" ? new Date().toISOString() : "2026-10-14T01:00:00Z";
  return { cacheIdentity: "c".repeat(64), versionSources: [{ repoId: repo.id, sourceIdentity }],
    versionSnapshots: item ? [{ repoId: repo.id, hasChanges: true, changeState: "changed", worktreeChanged: true, outgoingCommits: 0, headSha: "c".repeat(40), outgoingBaselineSha: "c".repeat(40), syncChanged: false, syncState: "none", pendingRecovery: false, components: [component()], ...item, sourceIdentity, checkedAt, displayOnly: readState !== "ready" }] : [],
    versionReadStates: { [repo.id]: { sourceIdentity, state: readState, startedAt: "2026-10-14T01:01:00Z", checkedAt, message: readState === "error" ? "Local reader unavailable" : "" } }, complete: ["ready", "error", "idle"].includes(readState), refreshingIds: ["queued", "reading"].includes(readState) ? [repo.id] : [], repositories: [], ...extra };
};
const completedUpload = repo => ({ ...progressItem(repo, "success", "complete"), progress: { phase: "complete", state: "complete", scope: "repository", source: "receipt", percent: 100 } });
await test("fresh changes remain primary after a successful old upload without inventing an applied version", async () => {
  const repo = repository(), current = automaticComponent({ currentVersion: "1.6.45", nextVersion: "1.6.46", headVersion: "1.6.45" });
  const h = harness({ lang: "en", snapshot: { operation: operation(randomUUID(), "success", [completedUpload(repo)]) }, catalog: { repositories: [{ repoId: repo.id, hasChanges: true, changeState: "changed", worktreeChanged: true, components: [current] }] } });
  await h.ready(); await expandAndCheck(h);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.6.46");
  assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "changed");
  assert.equal(h.byClass("repository-publish-compact-status").textContent, "Changes to commit");
  assert.equal(h.byClass("repository-publish-row-history").textContent, "Last upload · 100%");
  assert.equal(h.byClass("repository-publish-row-activity").hidden, true); assert.equal(h.posts().length, 0);
  h.byClass("repository-publish-primary").click(); await settle(); assert.equal(h.posts("/run").length, 1); assert.equal(h.posts("/run")[0].body.intent, "commit_and_push"); h.api.destroy();
});
await test("old success cannot hide a pending or failed read and only a fresh catalog advances the displayed version", async () => {
  const repo = repository(), pending = deferred(), old = automaticComponent({ currentVersion: "1.6.45", nextVersion: "1.6.46", headVersion: "1.6.45" }), envelope = cachedEnvelope(repo, { components: [old] });
  const h = harness({ lang: "en", snapshot: { ...envelope, operation: operation(randomUUID(), "success", [completedUpload(repo)]) }, hook(call) { if (call.url.includes("/versions?snapshot=1")) return pending.promise; } });
  await h.ready(); await expandAndCheck(h);
  const version = h.byClass("repository-publish-compact-version"), status = h.byClass("repository-publish-compact-status"), history = h.byClass("repository-publish-row-history"), freshness = h.byClass("repository-publish-version-freshness");
  assert.equal(version.textContent, "1.6.45"); assert.equal(version.dataset.changeState, "unknown"); assert.equal(status.textContent, "Last known"); assert.equal(freshness.textContent, "Last known"); assert.equal(status.dataset.attention, "false"); assert.equal(h.byClass("repository-publish-row-activity").hidden, true);
  assert.equal(history.textContent, "Last upload · 100%"); assert.equal(h.posts().length, 0);
  pending.reject(new Error("fixture version reader unavailable")); await settle();
  assert.equal(version.textContent, "1.6.45"); assert.equal(status.textContent, "Refresh failed · Last known"); assert.equal(freshness.textContent, "Refresh failed"); assert.equal(history.hidden, false); assert.equal(status.dataset.attention, "true"); assert.equal(h.byClass("repository-publish-row-reason").hidden, false); assert.equal(h.byClass("repository-publish-row-activity").hidden, true);
  assert.equal(h.posts().length, 0);
  h.hook(call => call.url.includes("/versions?snapshot=1") ? response(cachedEnvelope(repo, { hasChanges: false, changeState: "unchanged", worktreeChanged: false, components: [component({ currentVersion: "1.6.46", nextVersion: "1.6.47", headVersion: "1.6.46" })] }, "ready")) : undefined);
  await h.emitWindow("focus"); await checkAll(h); assert.equal(version.textContent, "1.6.46"); assert.equal(version.dataset.changeState, "unchanged"); assert.equal(status.textContent, "No changes"); assert.equal(freshness.hidden, true);
  assert.equal(history.textContent, "Last upload · 100%"); assert.equal(h.calls.filter(call => call.url.includes("refresh=1")).length, 2); assert.equal(h.posts().length, 0); h.api.destroy();
});
await test("display-only snapshots keep their known number but never a current green auto transition or upload rail", async () => {
  for (const readState of ["idle", "ready"]) {
    const repo = repository(), item = automaticComponent(), envelope = cachedEnvelope(repo, { components: [item] }, readState); envelope.versionSnapshots[0].displayOnly = true;
    const h = harness({ lang: "en", snapshot: { ...envelope, operation: operation(randomUUID(), "success", [completedUpload(repo)]) }, hook(call) { if (call.url.includes("/versions?snapshot=1")) return response(envelope); } });
    await h.ready(); await h.expand(); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown");
    assert.equal(h.byClass("repository-publish-compact-status").textContent, "Last known"); assert.equal(h.byClass("repository-publish-compact-status").dataset.attention, "false"); assert.equal(h.byClass("repository-publish-row-history").textContent, "Last upload · 100%");
    assert.equal(h.byClass("repository-publish-version-freshness").hidden, false); assert.equal(h.posts().length, 0); h.api.destroy();
  }
});
await test("completed uploads retain normal live batch progress until the original batch finishes", async () => {
  const first = repository(), second = repository({ id: "repository-002", path: "D:/Other", repositoryUrl: "https://github.com/example/Other" }), id = randomUUID();
  const measured = { phase: "push", state: "measured", scope: "phase", source: "git", unit: "objects", current: 37, total: 100 };
  const h = harness({ lang: "en", snapshot: { ...cachedEnvelope(first, { components: [automaticComponent()] }, "ready"), settings: settings([first, second]), operation: operation(id, "working", [completedUpload(first), { ...progressItem(second, "working", "push"), progress: measured }]) } });
  await h.ready(); await expandAndCheck(h);
  const one = rowFor(h, first.id), two = rowFor(h, second.id);
  assert.equal(h.byClass("repository-publish-compact-status", one).textContent, "Uploaded"); assert.equal(h.byClass("repository-publish-row-activity", one).hidden, true); assert.equal(h.byClass("repository-publish-row-history", one).hidden, true);
  assert.equal(h.byClass("repository-publish-compact-status", two).textContent, "Uploading"); assert.equal(h.byClass("repository-publish-row-activity", two).hidden, false); assert.equal(h.posts().length, 0); h.api.destroy();
});
await test("an old skipped receipt cannot mask newly saved changes", async () => {
  const repo = repository(), h = harness({ lang: "en", snapshot: { operation: operation(randomUUID(), "success", [progressItem(repo, "noop", "complete")]) }, catalog: { repositories: [{ repoId: repo.id, hasChanges: true, changeState: "changed", worktreeChanged: true, components: [automaticComponent()] }] } });
  await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-status").textContent, "Changes to commit"); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "changed");
  assert.equal(h.byClass("repository-publish-row-history").hidden, true); assert.equal(h.posts().length, 0); h.api.destroy();
});
await test("initial snapshots and an explicitly started slow check keep rows silent without a loading symbol", async () => {
  const repo = repository(), pending = deferred(), cached = cachedEnvelope(repo, {}), h = harness({ snapshot: cached,
    hook(call) { if (call.url.includes("/versions?snapshot=1")) return pending.promise; } });
  await h.ready(); assert.equal(h.calls.length, 1); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4");
  assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown"); assert.equal(h.byClass("repository-publish-version-freshness").textContent, "上次状态"); assert.equal(h.byClass("repository-publish-row-spinner").hidden, true);
  await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-status").textContent, "有待提交改动"); assert.doesNotMatch(h.byClass("repository-publish-compact-version").textContent, /Pending|Reading|待读取/);
  await h.emitWindow("focus"); assert.equal(h.calls.filter(call => call.url.includes("/versions?snapshot=1")).length, 1); assert.equal(h.posts().length, 0);
  pending.resolve(response(cachedEnvelope(repo, { components: [component({ currentVersion: "2.3.5" })] }, "ready"))); await settle();
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.5"); assert.equal(h.byClass("repository-publish-row-spinner").hidden, true); assert.equal(h.timers.size, 0);
});
await test("first use shows an explicit unread version instead of a component name or fabricated repository version", async () => {
  const repo = repository({ versionSources: [{ path: "package.json", kind: "json", key: "version", name: "Music component" }] }), envelope = cachedEnvelope(repo, null), h = harness({ snapshot: { settings: settings([repo]), ...envelope }, hook(call) { if (call.url.includes("/versions?snapshot=1")) return new Promise(() => {}); } });
  await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, "版本待读取"); assert.equal(h.byClass("repository-publish-row-spinner").hidden, true); assert.equal(h.posts().length, 0); h.api.destroy();
});
await test("a failed snapshot refresh preserves the last-known values, disables stale version writes and stops polling", async () => {
  const repo = repository(), cached = cachedEnvelope(repo, {}, "idle"), h = harness({ snapshot: cached, hook(call) { if (call.url.includes("/versions?snapshot=1")) return { ok: false, status: 503, json: async () => ({ error: "Current local read unavailable" }) }; } });
  await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.equal(h.byClass("repository-publish-row-spinner").hidden, true); assert.match(h.byClass("repository-publish-compact-status").textContent, /有待提交改动.*核对失败/);
  await openAndCheck(h, repo.id); assert.equal(h.byClass("repository-publish-plan-action").disabled, true); assert.equal(h.timers.size, 0); assert.equal(h.posts().length, 0);
});
await test("snapshot polling has one refresh request, retains rows, and clears its timer after completion or destroy", async () => {
  const repo = repository(), cached = cachedEnvelope(repo, {}), h = harness({ snapshot: cached, hook(call) { if (call.url.includes("/versions?snapshot=1")) return response(cached); } });
  await h.ready(); await expandAndCheck(h); assert.equal(h.calls.filter(call => call.url.includes("refresh=1")).length, 1); assert.equal(h.timers.size, 1);
  await h.emitWindow("focus"); await h.emitWindow("pageshow"); assert.equal(h.calls.filter(call => call.url.includes("refresh=1")).length, 1); assert.equal(h.timers.size, 1);
  h.hook(call => call.url.includes("/versions?snapshot=1") ? response(cachedEnvelope(repo, {}, "ready")) : undefined); await h.poll(); assert.equal(h.timers.size, 0); assert.equal(h.calls.filter(call => call.url.includes("refresh=1")).length, 1);
  assert.equal(h.byClass("repository-publish-row-spinner").hidden, true); assert.equal(h.posts().length, 0); h.api.destroy(); assert.equal(h.timers.size, 0);
});
await test("changed destination and installation identity invalidate cached versions and late snapshots cannot restore them", async () => {
  const repo = repository(), pending = deferred(), envelope = cachedEnvelope(repo, {}, "idle"), h = harness({ snapshot: envelope, hook(call) { if (call.url.includes("/versions?snapshot=1")) return pending.promise; } });
  await h.ready(); await expandAndCheck(h); h.snapshot.settings.repositories[0].branch = "feature/new-target"; h.snapshot.settingsSha = settingsSha(h.snapshot.settings);
  Object.assign(h.snapshot, cachedEnvelope(h.snapshot.settings.repositories[0], null, "idle", { cacheIdentity: "d".repeat(64) }));
  await h.setPanelHidden(true); await h.api.refresh(); await settle(); assert.notEqual(h.byClass("repository-publish-compact-version").textContent, "2.3.4");
  pending.resolve(response(envelope)); await settle(); assert.notEqual(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.equal(h.posts().length, 0); h.api.destroy();
});
await test("snapshot refresh stops after its overall deadline and hiding Console removes only its read timer", async () => {
  const repo = repository(), cached = cachedEnvelope(repo, {}), clock = { now: Date.now() }, h = harness({ clock, snapshot: cached, hook(call) { if (call.url.includes("/versions?snapshot=1")) return response(cached); } });
  await h.ready(); await expandAndCheck(h); assert.equal(h.timers.size, 1); clock.now += 61000; await h.poll();
  assert.equal(h.timers.size, 0); assert.equal(h.byClass("repository-publish-row-spinner").hidden, true); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.match(h.byClass("repository-publish-compact-status").textContent, /核对失败/);
  await h.emitWindow("focus"); assert.equal(h.timers.size, 0); await checkAll(h); assert.equal(h.timers.size, 1); await h.setPanelHidden(true); assert.equal(h.timers.size, 0); assert.equal(h.posts().length, 0);
});
await test("a snapshot from another source identity cannot replace a valid previous catalog", async () => {
  const repo = repository(), cached = cachedEnvelope(repo, {}, "idle"), invalid = cachedEnvelope(repo, { components: [component({ currentVersion: "91.2.3" })] }, "ready");
  invalid.versionSnapshots[0].sourceIdentity = "different-checkout";
  const h = harness({ snapshot: cached, hook(call) { if (call.url.includes("/versions?snapshot=1")) return response(invalid); } });
  await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.equal(h.posts().length, 0);
});
await test("snapshot read failures preserve known versions and retain their safe repository-path Locate target", async () => {
  const repo = repository(), envelope = cachedEnvelope(repo, {}, "error"), reason = diagnostic({ code: "repo_missing", severity: "error", summary: "The saved local repository folder is missing.", nextStep: "Review this repository folder; existing work is retained.", target: { section: "connection", field: "path" } });
  envelope.versionReadStates[repo.id].diagnostic = reason;
  const h = harness({ snapshot: envelope, hook(call) { if (call.url.includes("/versions?snapshot=1")) return response(envelope); } });
  await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); h.byClass("repository-publish-compact-status").click(); await settle();
  assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, reason.summary); assert.equal(h.byClass("repository-publish-diagnosis").dataset.severity, "error"); assert.equal(h.byClass("repository-publish-diagnosis-locate").hidden, false); assert.notEqual(h.document.activeElement, h.fields("path")[0]);
  h.byClass("repository-publish-diagnosis-locate").click(); assert.equal(h.document.activeElement, h.fields("path")[0]); assert.equal(h.fields("path")[0].value, repo.path); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.equal(h.posts().length, 0);
});
await test("a failed snapshot version-authority read locates its validated source without discarding the old version", async () => {
  const value = component(), repo = repository({ versionSources: [{ path: value.path, kind: value.kind, key: value.key, name: value.name, scope: [] }] }), envelope = cachedEnvelope(repo, { components: [value] }, "error"), reason = diagnostic({ code: "version_authority", category: "versions", severity: "warning", summary: "This component version authority needs review.", nextStep: "Review the component source file.", target: { section: "versions", field: "versionPath", sourceId: value.sourceId } });
  envelope.versionReadStates[repo.id].diagnostic = reason;
  const h = harness({ snapshot: { settings: settings([repo]), ...envelope }, hook(call) { if (call.url.includes("/versions?snapshot=1")) return response(envelope); } });
  await h.ready(); await expandAndCheck(h); h.byClass("repository-publish-compact-status").click(); await settle(); assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, reason.summary); assert.equal(h.byClass("repository-publish-diagnosis-locate").hidden, false); assert.notEqual(h.document.activeElement, h.fields("versionPath")[0]);
  h.byClass("repository-publish-diagnosis-locate").click(); assert.equal(h.document.activeElement, h.fields("versionPath")[0]); assert.equal(h.fields("versionPath")[0].value, value.path); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.equal(h.posts().length, 0);
});
await test("snapshot read failures without a valid diagnosis keep the safe message and do not invent a Locate action", async () => {
  for (const malformed of [undefined, { code: "arbitrary", severity: "error", summary: "Unverified target", target: { section: "connection", field: "path" } }]) {
    const repo = repository(), envelope = cachedEnvelope(repo, {}, "error"); envelope.versionReadStates[repo.id].message = "Local source read could not finish; retain previous values."; envelope.versionReadStates[repo.id].diagnostic = malformed;
    const h = harness({ snapshot: envelope, hook(call) { if (call.url.includes("/versions?snapshot=1")) return response(envelope); } }); await h.ready(); await expandAndCheck(h); h.byClass("repository-publish-compact-status").click(); await settle();
    assert.equal(h.byClass("repository-publish-diagnosis-locate").hidden, true); assert.match(h.byClass("repository-publish-diagnosis-summary").textContent, malformed ? /Unverified target/ : /Local source read could not finish/); assert.equal(h.byClass("repository-publish-compact-version").textContent, "2.3.4"); assert.equal(h.posts().length, 0);
  }
});
await test("active rows use one compact spinner while real measurements remain scoped to operation details", async () => {
  const repos = progressRepos(), measured = { phase: "push", state: "measured", scope: "phase", unit: "objects", current: 37, total: 100, percent: 37, source: "git", step: "writing_objects", elapsedSeconds: 23 }, rows = [
    { ...progressItem(repos[0], "working", "push"), progress: measured },
    { ...progressItem(repos[1], "queued", "queued"), progress: { state: "queued", percent: 90 } },
    { ...progressItem(repos[2], "working", "check"), progress: { ...measured, phase: "check", elapsedSeconds: 4 } },
    { ...progressItem(repos[3], "working", "push"), progress: { ...measured, scope: "file", unit: "bytes", current: 75, total: 100, source: "git-lfs", fileIndex: 2, fileTotal: 3, estimatedFileTotal: true } },
    { ...progressItem(repos[4], "success", "complete"), progress: { phase: "complete", state: "complete", scope: "repository", source: "receipt", percent: 100 } }
  ], h = harness({ snapshot: { settings: settings(repos), operation: operation(randomUUID(), "working", rows) } }); await h.ready(); await expandAndCheck(h);
  for (let i = 0; i < repos.length; i++) {
    const row = rowFor(h, repos[i].id), status = h.byClass("repository-publish-compact-status", row);
    assert.equal(h.all(row).filter(item => item.className.split(" ").includes("repository-publish-row-spinner")).length, 1);
    assert.equal(h.byClass("repository-publish-row-activity", row).hidden, i === 1 || i === 4); assert.equal(status.dataset.attention, "false");
    assert.equal(h.byClass("repository-publish-row-progress", row), undefined); assert.equal(h.byClass("repository-publish-row-metric", row), undefined);
    assert.doesNotMatch(h.all(row).map(item => item.textContent).join(" "), /23s|4s|37%|75%/);
  }
  const metrics = [];
  for (const repo of repos) { await h.open(repo.id); metrics.push(h.byClass("repository-publish-operation-metric").textContent); }
  assert.match(metrics[0], /37%.*Git.*23s.*当前传输阶段/); assert.doesNotMatch(metrics[1], /%/); assert.match(metrics[2], /4s/); assert.doesNotMatch(metrics[2], /%/);
  assert.match(metrics[3], /75%.*LFS.*2\/\~3/); assert.match(metrics[4], /100%/);
  assert.equal(h.byClass("repository-publish-progress"), undefined); assert.equal(h.posts().length, 0);
});
await test("unknown results, historical receipts and failed transfer never show a fabricated 100 percent", async () => {
  const repo = repository();
  for (const [status, progress] of [["verification_required", { state: "complete", scope: "repository", source: "receipt", percent: 100 }], ["push_failed", { phase: "push", state: "measured", scope: "phase", source: "git", unit: "objects", current: 100, total: 100, percent: 100 }], ["success", { state: "complete", scope: "repository", source: "historical_receipt", percent: null }]]) {
    const h = harness({ snapshot: { operation: operation(randomUUID(), "attention", [{ ...progressItem(repo, status, "verify"), progress }]) } }); await h.ready(); await expandAndCheck(h); await h.open(repo.id);
    assert.doesNotMatch(h.byClass("repository-publish-operation-metric").textContent, /100%/); assert.equal(h.byClass("repository-publish-row-activity").hidden, true);
    assert.equal(h.byClass("repository-publish-compact-status").dataset.attention, String(status === "verification_required")); assert.equal(h.posts().length, 0);
  }
});
await test("switching an operation removes old detail measurements and a failed poll stops claiming live transfer", async () => {
  const repo = repository(), id = randomUUID(), measured = { phase: "push", state: "measured", scope: "phase", source: "git", unit: "objects", current: 50, total: 100, elapsedSeconds: 9 }, h = harness({ snapshot: { operation: operation(id, "working", [{ ...progressItem(repo, "working", "push"), progress: measured }]) } });
  await h.ready(); await expandAndCheck(h); await h.open(repo.id); assert.match(h.byClass("repository-publish-operation-metric").textContent, /50%/); assert.equal(h.byClass("repository-publish-row-activity").hidden, false);
  h.hook(call => { if (call.url.includes("/operation?")) throw new Error("Fixture disconnected"); }); await h.poll();
  assert.doesNotMatch(h.byClass("repository-publish-operation-metric").textContent, /50%/); assert.match(h.byClass("repository-publish-operation-metric").textContent, /待核对/);
  assert.equal(h.byClass("repository-publish-row-activity").hidden, true); assert.equal(h.byClass("repository-publish-compact-status").dataset.attention, "true");
  h.hook(null); h.snapshot.operation = operation(id, "attention", [progressItem(repo, "push_failed", "push")]); await h.poll();
  h.byClass("repository-publish-primary").click(); await settle(); assert.equal(h.posts("/run").length, 1); assert.doesNotMatch(h.byClass("repository-publish-operation-metric").textContent, /50%/);
});
await test("each repository displays the age of its HEAD commit instead of the upload receipt or operation start", async () => {
  const clock = { now: Date.parse("2026-10-15T03:00:00Z") }, repos = progressRepos(), seconds = [30, 12 * 60, 3 * 3600, 2 * 86400, 60], rows = repos.map((repo, i) => ({ repoId: repo.id, components: [component()], lastCommit: { sha: String(i + 1).repeat(40), committedAt: new Date(clock.now - seconds[i] * 1000).toISOString() } }));
  const h = harness({ clock, snapshot: { settings: settings(repos), operation: { ...operation(randomUUID(), "success", repos.map(repo => progressItem(repo, "success", "complete"))), createdAt: new Date(clock.now).toISOString() } }, catalog: { repositories: rows } }); await h.ready(); await expandAndCheck(h);
  assert.deepEqual(repos.map(repo => h.byClass("repository-publish-commit-age", rowFor(h, repo.id)).textContent), ["提交 30s", "提交 12m", "提交 3h", "提交 2d", "提交 1m"]);
  for (let i = 0; i < repos.length; i++) { const age = h.byClass("repository-publish-commit-age", rowFor(h, repos[i].id)); assert.ok(age.title.includes(rows[i].lastCommit.committedAt)); assert.ok(age.title.includes(rows[i].lastCommit.sha)); assert.match(age.title, /HEAD/); }
  const requests = h.calls.length, [[id, timer]] = [...h.timers].filter(([, entry]) => entry.delay === 1000); assert.equal([...h.timers].filter(([, entry]) => entry.delay === 1000).length, 1); clock.now += 1000; h.timers.delete(id); timer.fn(); await settle();
  assert.equal(h.byClass("repository-publish-commit-age", rowFor(h, repos[0].id)).textContent, "提交 31s"); assert.equal(h.calls.length, requests); assert.equal(h.posts().length, 0); h.api.destroy(); assert.equal(h.timers.size, 0);
});
await test("commit age retains the bound last-known commit through refresh failure and replaces it only with a fresh HEAD", async () => {
  const clock = { now: Date.parse("2026-10-15T03:00:00Z") }, repo = repository(), old = { sha: "a".repeat(40), committedAt: new Date(clock.now - 720000).toISOString() }, envelope = cachedEnvelope(repo, { lastCommit: old }, "idle");
  const h = harness({ clock, snapshot: envelope, hook(call) { if (call.url.includes("/versions?snapshot=1")) return { ok: false, status: 503, json: async () => ({ error: "Fixture reader unavailable" }) }; } });
  await h.ready(); await expandAndCheck(h); const age = h.byClass("repository-publish-commit-age"); assert.equal(age.textContent, "提交 12m"); assert.equal(age.dataset.freshness, "last-known"); assert.match(age.title, /上次读取/);
  const fresh = { sha: "b".repeat(40), committedAt: new Date(clock.now - 30000).toISOString() }; h.hook(call => call.url.includes("/versions?snapshot=1") ? response(cachedEnvelope(repo, { lastCommit: fresh }, "ready")) : undefined); await h.emitWindow("focus"); await checkAll(h);
  assert.equal(age.textContent, "提交 30s"); assert.equal(age.dataset.freshness, "current"); assert.ok(age.title.includes(fresh.sha)); assert.equal(h.posts().length, 0); h.api.destroy(); assert.equal(h.timers.size, 0);
});
await test("missing or malformed commit times remain a dash and a future timestamp is never presented as ordinary zero seconds", async () => {
  const clock = { now: Date.parse("2026-10-15T03:00:00Z") };
  for (const lastCommit of [null, undefined, {}, { sha: "not-a-commit", committedAt: "2026-10-15T02:59:00Z" }, { sha: "a".repeat(41), committedAt: "2026-10-15T02:59:00Z" }, { sha: "a".repeat(40), committedAt: "not-a-time" }, { sha: "a".repeat(40), committedAt: "2026-02-30T02:59:00Z" }, { sha: "a".repeat(40), committedAt: "2026-10-15T02:59:00" }]) {
    const h = harness({ clock, catalog: { repositories: [{ repoId: "repository-001", components: [], lastCommit }] } }); await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-commit-age").textContent, "提交 —"); assert.equal(h.byClass("repository-publish-commit-age").dataset.state, "unknown"); assert.equal([...h.timers.values()].filter(timer => timer.delay === 1000).length, 0); assert.equal(h.posts().length, 0); h.api.destroy();
  }
  const h = harness({ clock, catalog: { repositories: [{ repoId: "repository-001", components: [], lastCommit: { sha: "a".repeat(40), committedAt: new Date(clock.now + 1000).toISOString() } }] } }); await h.ready(); await expandAndCheck(h); const age = h.byClass("repository-publish-commit-age"); assert.equal(age.textContent, "提交 ?"); assert.equal(age.dataset.state, "future"); assert.match(age.title, /核对时钟/); h.locale("en"); assert.equal(age.textContent, "Commit ?"); assert.match(age.title, /clock/); assert.equal(h.posts().length, 0); h.api.destroy();
});
await test("the commit-age display timer stops on collapse, hidden Console, page suspension, hidden document and destruction", async () => {
  const clock = { now: Date.parse("2026-10-15T03:00:00Z") }, h = harness({ clock, catalog: { repositories: [{ repoId: "repository-001", components: [], lastCommit: { sha: "a".repeat(40), committedAt: "2026-10-15T02:59:30Z" } }] } });
  const ageTimers = () => [...h.timers.values()].filter(timer => timer.delay === 1000).length;
  await h.ready(); assert.equal(ageTimers(), 0); await expandAndCheck(h); assert.equal(ageTimers(), 1); await expandAndCheck(h); assert.equal(ageTimers(), 0); await expandAndCheck(h); assert.equal(ageTimers(), 1);
  await h.setPanelHidden(true); assert.equal(ageTimers(), 0); await h.setPanelHidden(false); assert.equal(ageTimers(), 1);
  await h.emitWindow("pagehide"); assert.equal(ageTimers(), 0); await h.emitWindow("pageshow"); assert.equal(ageTimers(), 1);
  h.document.hidden = true; h.document.emit("visibilitychange"); assert.equal(ageTimers(), 0); h.document.hidden = false; h.document.emit("visibilitychange"); assert.equal(ageTimers(), 1);
  h.api.destroy(); assert.equal(ageTimers(), 0); h.document.emit("visibilitychange"); assert.equal(ageTimers(), 0); assert.equal(h.posts().length, 0);
});
await test("a changed repository destination cannot reuse the last-known commit of the old target", async () => {
  const clock = { now: Date.parse("2026-10-15T03:00:00Z") }, repo = repository(), envelope = cachedEnvelope(repo, { lastCommit: { sha: "a".repeat(40), committedAt: "2026-10-15T02:59:30Z" } }, "idle"), h = harness({ clock, snapshot: envelope, hook(call) { if (call.url.includes("/versions?snapshot=1")) return response(envelope); } });
  await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-commit-age").textContent, "提交 30s");
  h.snapshot.settings.repositories[0].branch = "feature/new-commit-target"; h.snapshot.settingsSha = settingsSha(h.snapshot.settings); Object.assign(h.snapshot, cachedEnvelope(h.snapshot.settings.repositories[0], null, "idle")); await h.api.refresh(); await settle();
  assert.equal(h.byClass("repository-publish-commit-age").textContent, "提交 —"); assert.equal(h.byClass("repository-publish-commit-age").dataset.state, "unknown"); assert.equal(h.posts().length, 0); h.api.destroy();
});
const activityBlocker = (extra = {}) => ({ threadId: "01a12305-aada-7273-b72c-54a41aad77e4", title: "Character", agentPath: "/root/dress_check", cwd: "D:/Unity Projects/RandomRealm2", state: "inProgress", mode: "work", roots: ["D:/Unity Projects/RandomRealm2"], reason: "This chat is editing the repository.", ...extra });
const blockedReceipt = (repo, value, extra = {}) => ({ ...progressItem(repo, "deferred", "check"), message: value?.summary || "Original work retained", diagnostic: value, ...extra });
const assertPastAttemptIsNotCurrent = h => {
  const status = h.byClass("repository-publish-compact-status");
  assert.equal(status.dataset.attention, "false"); assert.equal(h.byClass("repository-publish-row-reason").hidden, true);
  assert.doesNotMatch(status.textContent, /Last upload attempt|上次上传尝试|TLS connection failed|TLS连接失败|Uploaded|已上传/);
  if (h.byClass("repository-publish-compact-version").dataset.changeState === "unknown") assert.doesNotMatch(status.textContent, /No changes|无改动/);
};
const activityDiagnostic = (extra = {}) => diagnostic({ code: "activity_active", category: "activity", summary: "Codex is still editing this repository.", nextStep: "Wait for Character to finish, then retry this repository.", target: null, blockers: [activityBlocker()], ...extra });
await test("past activity blockers remain in details without becoming the current row status", async () => {
  const repo = repository(), h = harness({ lang: "en", snapshot: { operation: operation(randomUUID(), "attention", [blockedReceipt(repo, activityDiagnostic())]) } }); await h.ready(); await expandAndCheck(h);
  const row = rowFor(h, repo.id), status = h.byClass("repository-publish-compact-status", row), reason = h.byClass("repository-publish-row-reason", row);
  assertPastAttemptIsNotCurrent(h); assert.equal(status.dataset.status, "current"); assert.equal(status.getAttribute("aria-describedby"), null); assert.doesNotMatch(status.title, /Wait for Character to finish/);
  const calls = h.calls.length; status.click(); await settle(); assert.equal(h.calls.length, calls + 1); assert.ok(h.calls.slice(calls).every(call => call.method === "GET" && call.url === BASE)); assert.equal(h.byClass("repository-publish-diagnosis-heading").textContent, "Last upload attempt");
  assert.equal(h.byClass("repository-publish-last-attempt").open, false); assert.equal(h.visible(h.byClass("repository-publish-diagnosis-summary")), false); assert.match(h.byClass("repository-publish-current-activity-summary").textContent, /current state has not been checked/);
  const details = h.byClass("repository-publish-diagnosis-blockers"), content = h.all(details).map(item => item.textContent).join(" "); assert.equal(details.hidden, false); assert.match(content, /Character/); assert.match(content, /D:\/Unity Projects\/RandomRealm2/); assert.match(content, /\/root\/dress_check/); assert.match(content, /01a12305-aada-7273-b72c-54a41aad77e4/); assert.match(content, /No repository setting needs changing/);
  assert.equal(h.byClass("repository-publish-diagnosis-locate").hidden, true); assert.ok(h.button("Continue this repository")); assert.equal(h.posts().length, 0);
  h.locale("zh-CN"); assertPastAttemptIsNotCurrent(h); assert.match(h.all(h.byClass("repository-publish-results")).map(item => item.textContent).join(" "), /等待 Codex 完成/); assert.ok(h.button("继续此仓库")); assert.equal(h.posts().length, 0);
});
await test("scope-unknown and legacy unconfirmed activity have different labels and never assume missing actors", async () => {
  for (const [code, expected] of [["activity_scope_unknown", "Check the chat's scope"], ["activity_unconfirmed", "Check Codex activity"]]) {
    const repo = repository(), value = activityDiagnostic({ code, summary: "A projectless working chat has not declared its repository scope.", nextStep: "Confirm its working scope before retrying.", blockers: code === "activity_scope_unknown" ? [activityBlocker({ title: "X", cwd: "D:/Blender/Projects/Character/X", roots: ["D:/Blender/Projects/Character/X"] })] : undefined }), h = harness({ lang: "en", snapshot: { operation: operation(randomUUID(), "attention", [blockedReceipt(repo, value)]) } });
    await h.ready(); await expandAndCheck(h); assertPastAttemptIsNotCurrent(h); h.byClass("repository-publish-compact-status").click(); await settle();
    assert.match(h.byClass("repository-publish-diagnosis-summary").textContent, /projectless working chat/); assert.equal(h.byClass("repository-publish-diagnosis-locate").hidden, true);
    const content = h.all(h.byClass("repository-publish-diagnosis-blockers")).map(item => item.textContent).join(" ");
    if (code === "activity_scope_unknown") assert.match(content, /X.*D:\/Blender\/Projects\/Character\/X/); else { assert.match(content, /Activity is not confirmed/); assert.doesNotMatch(content, /Character|\/root\/dress_check/); }
    assert.equal(h.posts().length, 0);
  }
});
await test("legacy deferred reasons remain inspectable without claiming a current blocker", async () => {
  const repo = repository(), h = harness({ lang: "en", snapshot: { operation: operation(randomUUID(), "attention", [blockedReceipt(repo, null, { message: "Original safety check could not establish the workspace boundary." })]) } }); await h.ready(); await expandAndCheck(h);
  assertPastAttemptIsNotCurrent(h); h.byClass("repository-publish-compact-status").click(); await settle();
  assert.match(h.byClass("repository-publish-diagnosis-summary").textContent, /could not establish the workspace boundary/); assert.equal(h.byClass("repository-publish-diagnosis-blockers").hidden, true); assert.equal(h.byClass("repository-publish-diagnosis-locate").hidden, true); assert.doesNotMatch(h.all(h.byClass("repository-publish-diagnosis")).map(item => item.textContent).join(" "), /Character|X\.blend/); assert.equal(h.posts().length, 0);
});
await test("current Git and sync diagnostics provide actionable localized labels with preserved reasons", async () => {
  for (const [code, category, label, zh] of [["staged_selection", "repository", "Review staged changes", "已有暂存选择"], ["git_lock", "repository", "Git lock file found", "检测到Git锁文件"], ["remote_ahead", "remote", "Integrate remote changes first", "先整合远端历史"], ["sync_missing", "sync", "Save the work file first", "先保存工作文件"], ["git_lfs", "lfs", "Check the LFS upload", "LFS 上传待处理"], ["git_large_history", "lfs", "Old commits contain large files; convert history to LFS", "旧提交含大文件，需转换历史"]]) {
    const repo = repository(), value = diagnostic({ code, category, summary: "A verified guard stopped this repository; original work is retained.", target: null }), h = harness({ lang: "en", snapshot: { operation: operation(randomUUID(), "attention", [blockedReceipt(repo, value)]) }, catalog: { repositories: [{ repoId: repo.id, components: [], diagnostic: value }] } }); await h.ready(); await expandAndCheck(h);
    assert.equal(h.byClass("repository-publish-compact-status").textContent, label); assert.match(h.byClass("repository-publish-row-reason").textContent, /verified guard/); h.locale("zh-CN"); assert.equal(h.byClass("repository-publish-compact-status").textContent, zh); assert.equal(h.posts().length, 0);
  }
});
await test("a refreshing catalog stays neutral while the original stopped reason remains in details", async () => {
  const repo = repository(), pending = deferred(), h = harness({ lang: "en", snapshot: { operation: operation(randomUUID(), "attention", [blockedReceipt(repo, activityDiagnostic())]) }, catalog: { repositories: [{ repoId: repo.id, components: [], diagnostic: diagnostic() }] }, hook(call) { if (call.url.startsWith(BASE + "/versions?")) return pending.promise; } });
  await h.ready(); await expandAndCheck(h); assertPastAttemptIsNotCurrent(h); assert.equal(h.byClass("repository-publish-row-activity").hidden, true); h.byClass("repository-publish-compact-status").click(); await settle();
  assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, "Codex is still editing this repository."); assert.match(h.byClass("repository-publish-diagnosis-next").textContent, /Wait for Character to finish/); assert.equal(h.byClass("repository-publish-diagnosis-locate").hidden, true);
  pending.resolve(response(h.versionEnvelope({ repositories: [{ repoId: repo.id, components: [], diagnostic: diagnostic() }] }))); await settle(); assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, "Codex is still editing this repository."); assert.equal(h.posts().length, 0);
});
await test("hostile or malformed blocker metadata remains inert text and cannot choose settings or external actions", async () => {
  const repo = repository(), hostile = '<img src=x onerror="evil()">', value = activityDiagnostic({ target: { section: "connection", field: "path" }, blockers: [null, 17, activityBlocker({ title: hostile, threadId: hostile, agentPath: hostile, cwd: "https://secret-token@example.invalid/private", state: hostile, mode: hostile, roots: ["https://secret-token@example.invalid/private", null, "D:/Blender/Projects/X"], reason: hostile }), { cwd: "D:/Unknown", reason: "No actor identity was supplied" }] }), h = harness({ lang: "en", snapshot: { operation: operation(randomUUID(), "attention", [blockedReceipt(repo, value)]) } });
  await h.ready(); await expandAndCheck(h); assert.doesNotMatch(h.byClass("repository-publish-row-reason").textContent, /<img/); h.byClass("repository-publish-compact-status").click(); await settle();
  const details = h.byClass("repository-publish-diagnosis-blockers"), content = h.all(details).map(item => item.textContent).join(" "); assert.ok(content.includes(hostile)); assert.match(content, /D:\/Blender\/Projects\/X/); assert.doesNotMatch(content, /secret-token|example\.invalid|No actor identity was supplied/); assert.equal(h.all(details).some(item => ["IMG", "A", "BUTTON"].includes(item.tagName)), false); assert.equal(h.byClass("repository-publish-diagnosis-locate").hidden, true); assert.equal(h.posts().length, 0);
});
await test("unknown codes remain truthful generic pauses and normal or historical rows have no new blocker note", async () => {
  const repo = repository(), value = activityDiagnostic({ code: "unknown_future_guard" }), h = harness({ lang: "en", snapshot: { operation: operation(randomUUID(), "attention", [blockedReceipt(repo, value)]) } }); await h.ready(); await expandAndCheck(h);
  assertPastAttemptIsNotCurrent(h); h.byClass("repository-publish-compact-status").click(); await settle(); assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, value.summary); assert.equal(h.byClass("repository-publish-diagnosis-blockers").hidden, true); assert.equal(h.posts().length, 0);
  for (const operationValue of [null, operation(randomUUID(), "complete", [progressItem(repo, "success", "complete")]), operation(randomUUID(), "attention", [blockedReceipt({ ...repo, branch: "feature/old-target" }, activityDiagnostic())])]) {
    const normal = harness({ snapshot: { operation: operationValue }, catalog: { repositories: [{ repoId: repo.id, components: [], hasChanges: false, changeState: "unchanged" }] } }); await normal.ready(); await expandAndCheck(normal); assert.equal(normal.byClass("repository-publish-row-reason").hidden, true); assert.equal(normal.byClass("repository-publish-compact-status").getAttribute("aria-describedby"), null); assert.equal(normal.posts().length, 0);
  }
  assert.match(css, /\.repository-publish-row-reason\[hidden\]/); assert.match(css, /text-overflow:\s*ellipsis/);
});
const activityEnvelope = (repo, extra = {}) => {
  const value = cachedEnvelope(repo, {}, "idle", extra), sourceIdentity = settingsSha(repo); value.versionSources[0].sourceIdentity = sourceIdentity; value.versionSnapshots[0].sourceIdentity = sourceIdentity; value.versionReadStates[repo.id].sourceIdentity = sourceIdentity; return value;
};
const liveActivityReply = (repo, value = activityDiagnostic(), extra = {}) => ({ repoId: repo.id, sourceIdentity: settingsSha(repo), activityClear: value === null, diagnostic: value, checkedAt: "2026-10-15T03:14:00Z", ...extra });
await test("opening a stopped diagnosis reads no actors and preserves the exact original attempt", async () => {
  const repo = repository(), old = activityDiagnostic({ code: "activity_unconfirmed", summary: "The previous attempt could not confirm the active scope.", blockers: [] }), envelope = activityEnvelope(repo), current = activityDiagnostic({ blockers: [activityBlocker({ title: "Unrequested actor" })] });
  const h = harness({ lang: "en", snapshot: { ...envelope, operation: operation(randomUUID(), "attention", [blockedReceipt(repo, old)]) }, hook(call) { if (call.url.startsWith(BASE + "/activity?")) return response(liveActivityReply(repo, current)); } });
  await h.ready(); await h.expand(); h.byClass("repository-publish-compact-status").click(); await settle();
  assert.equal(activityCalls(h).length, 0); assert.equal(versionCalls(h).length, 0); assert.equal(h.posts().length, 0);
  assert.equal(h.byClass("repository-publish-current-activity").dataset.state, "unknown"); assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, old.summary);
  assert.doesNotMatch(h.all().map(item => item.textContent).join(" "), /Unrequested actor/); assert.equal(h.snapshot.operation.repositories[0].diagnostic.summary, old.summary); assert.equal(h.snapshot.operation.repositories[0].diagnostic.blockers.length, 0);
});
await test("an unrequested clear-activity reply cannot claim ready uploaded or clear an original failure", async () => {
  const repo = repository(), envelope = activityEnvelope(repo), original = activityDiagnostic(), h = harness({ lang: "en", snapshot: { ...envelope, operation: operation(randomUUID(), "attention", [blockedReceipt(repo, original)]) }, hook(call) { if (call.url.startsWith(BASE + "/activity?")) return response(liveActivityReply(repo, null)); } });
  await h.ready(); await h.expand(); h.byClass("repository-publish-compact-status").click(); await settle(); assertPastAttemptIsNotCurrent(h);
  assert.equal(activityCalls(h).length, 0); assert.equal(h.byClass("repository-publish-current-activity").dataset.state, "unknown"); assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, original.summary);
  assert.doesNotMatch(h.byClass("repository-publish-compact-status").textContent, /Uploaded|Ready|activity cleared/); assert.ok(h.button("Continue this repository")); assert.equal(h.posts().length, 0);
  h.locale("zh-CN"); assertPastAttemptIsNotCurrent(h); assert.equal(h.posts().length, 0);
});
await test("explicit diagnosis Check All refreshes the catalog once without scanning actors or changing the receipt", async () => {
  const repo = repository(), envelope = activityEnvelope(repo), fresh = activityEnvelope(repo, cachedEnvelope(repo, { components: [component()] }, "ready")), h = harness({ lang: "en", snapshot: { ...envelope, operation: operation(randomUUID(), "attention", [blockedReceipt(repo, activityDiagnostic())]) }, hook(call) { if (call.url.startsWith(BASE + "/versions?")) return response(fresh); } });
  await h.ready(); await h.expand(); h.byClass("repository-publish-compact-status").click(); await settle(); assert.equal(versionCalls(h).length, 0);
  const original = structuredClone(h.snapshot.operation); h.byClass("repository-publish-diagnosis-recheck").click(); await settle();
  assert.equal(versionCalls(h).length, 1); assert.equal(versionCalls(h)[0].url, BASE + "/versions?snapshot=1&refresh=1"); assert.equal(activityCalls(h).length, 0); assert.deepEqual(h.snapshot.operation, original); assert.equal(h.posts().length, 0);
});
await test("a manual local catalog preserves staged-selection and file-sync blockers without a chat scan", async () => {
  for (const [code, category, label] of [["staged_selection", "repository", "Review staged changes"], ["sync_missing", "sync", "Save the work file first"]]) {
    const repo = repository(), value = diagnostic({ code, category, summary: "This specific non-chat blocker still needs resolving.", target: null }), envelope = activityEnvelope(repo), fresh = activityEnvelope(repo, cachedEnvelope(repo, { diagnostic: value }, "ready")), h = harness({ lang: "en", snapshot: { ...envelope, operation: operation(randomUUID(), "attention", [blockedReceipt(repo, value)]) }, hook(call) { if (call.url.startsWith(BASE + "/versions?")) return response(fresh); } });
    await h.ready(); await expandAndCheck(h); h.byClass("repository-publish-compact-status").click(); await settle();
    assert.equal(h.byClass("repository-publish-compact-status").textContent, label); assert.equal(h.byClass("repository-publish-row-reason").textContent, value.summary); assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, value.summary); assert.equal(activityCalls(h).length, 0); assert.equal(h.posts().length, 0);
  }
});
await test("malformed or differently bound activity data is never requested or accepted by passive opening", async () => {
  for (const bad of [{ repoId: "repository-other" }, { sourceIdentity: "f".repeat(64) }, { activityClear: true }, { diagnostic: null }, { checkedAt: "tomorrow" }, { diagnostic: diagnostic({ code: "remote_ahead", category: "remote" }) }]) {
    const repo = repository(), envelope = activityEnvelope(repo), h = harness({ lang: "en", snapshot: { ...envelope, operation: operation(randomUUID(), "attention", [blockedReceipt(repo, activityDiagnostic())]) }, hook(call) { if (call.url.startsWith(BASE + "/activity?")) return response(liveActivityReply(repo, activityDiagnostic({ blockers: [activityBlocker({ title: "Untrusted new actor" })] }), bad)); } });
    await h.ready(); await h.expand(); h.byClass("repository-publish-compact-status").click(); await settle();
    assert.equal(activityCalls(h).length, 0); assert.equal(versionCalls(h).length, 0); assertPastAttemptIsNotCurrent(h); assert.doesNotMatch(h.all().map(item => item.textContent).join(" "), /Untrusted new actor/); assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, "Codex is still editing this repository."); assert.equal(h.posts().length, 0);
  }
});
await test("opening old activity details never starts an activity deadline or an actor request", async () => {
  const repo = repository(), pending = deferred(), envelope = activityEnvelope(repo), h = harness({ lang: "en", snapshot: { ...envelope, operation: operation(randomUUID(), "attention", [blockedReceipt(repo, activityDiagnostic())]) }, hook(call) { if (call.url.startsWith(BASE + "/activity?")) return pending.promise; } });
  await h.ready(); await h.expand(); h.byClass("repository-publish-compact-status").click(); await settle();
  assert.equal([...h.timers.values()].filter(item => item.delay === 30000).length, 0); assert.equal(activityCalls(h).length, 0); assertPastAttemptIsNotCurrent(h);
  assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, "Codex is still editing this repository."); assert.equal(h.byClass("repository-publish-current-activity").dataset.state, "unknown"); assert.equal(h.posts().length, 0);
});
await test("manual catalog failure restores Check All and keeps the original attempt without automatic retry", async () => {
  const repo = repository(), envelope = activityEnvelope(repo), h = harness({ lang: "en", snapshot: { ...envelope, operation: operation(randomUUID(), "attention", [blockedReceipt(repo, activityDiagnostic())]) }, hook(call) { if (call.url.startsWith(BASE + "/versions?")) throw new Error("Fixture local read failed"); } });
  await h.ready(); await h.expand(); h.byClass("repository-publish-compact-status").click(); await settle(); h.byClass("repository-publish-diagnosis-recheck").click(); await settle();
  assert.equal(versionCalls(h).length, 1); assert.equal(activityCalls(h).length, 0); assert.equal(h.byClass("repository-publish-check").disabled, false); assert.equal(h.byClass("repository-publish-primary").disabled, false);
  assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, "Codex is still editing this repository."); assert.equal(h.posts().length, 0); assert.equal([...h.timers.values()].filter(item => item.delay === 1200).length, 0);
});
await test("closing switching hiding or destroying passive details never creates activity work or late actors", async () => {
  for (const action of ["close", "switch", "hide", "destroy"]) {
    const repo = repository(), other = repository({ id: "repository-002", path: "D:/Other", repositoryUrl: "https://github.com/example/Other" }), pending = deferred(), envelope = activityEnvelope(repo), h = harness({ lang: "en", snapshot: { ...envelope, settings: settings([repo, other]), operation: operation(randomUUID(), "attention", [blockedReceipt(repo, activityDiagnostic())]) }, hook(call) { if (call.url.startsWith(BASE + "/activity?")) return pending.promise; } });
    await h.ready(); await h.expand(); h.byClass("repository-publish-compact-status", rowFor(h, repo.id)).click(); await settle();
    if (action === "close") h.button("Close").click(); else if (action === "switch") await h.open(other.id); else if (action === "hide") await h.setPanelHidden(true); else h.api.destroy();
    assert.equal(activityCalls(h).length, 0); pending.resolve(response(liveActivityReply(repo, activityDiagnostic({ blockers: [activityBlocker({ title: "Late actor" })] })))); await settle();
    assert.doesNotMatch(h.all().map(item => item.textContent).join(" "), /Late actor/); assert.equal(h.posts().length, 0); if (action === "destroy") assert.equal(h.host.children.length, 0);
  }
});
await test("an unsaved branch draft stays protected without starting activity or local checks", async () => {
  const repo = repository(), envelope = activityEnvelope(repo), h = harness({ lang: "en", snapshot: { ...envelope, operation: operation(randomUUID(), "attention", [blockedReceipt(repo, activityDiagnostic())]) } });
  await h.ready(); await h.expand(); h.byClass("repository-publish-compact-status").click(); await settle(); const input = h.fields("branch")[0]; input.value = "feature/new-draft"; input.dispatch("input"); await settle();
  await h.emitWindow("focus"); await h.emitWindow("pageshow"); await checkAll(h);
  assert.equal(input.value, "feature/new-draft"); assert.equal(h.api.hasDraft(), true); assert.equal(activityCalls(h).length, 0); assert.equal(versionCalls(h).length, 0); assert.equal(h.posts().length, 0); assert.equal(h.byClass("repository-publish-primary").disabled, true);
});
await test("a changed installation passively invalidates cached actor permission without starting another check", async () => {
  const repo = repository(), envelope = activityEnvelope(repo), h = harness({ lang: "en", snapshot: { ...envelope, operation: operation(randomUUID(), "attention", [blockedReceipt(repo, activityDiagnostic())]) } });
  await h.ready(); await h.expand(); h.byClass("repository-publish-compact-status").click(); await settle(); h.snapshot.cacheIdentity = "d".repeat(64); await h.api.refresh(); await settle();
  assert.equal(activityCalls(h).length, 0); assert.equal(versionCalls(h).length, 0); assert.notEqual(h.byClass("repository-publish-compact-status").textContent, "No changes"); assert.equal(h.posts().length, 0);
});
await test("repeated diagnosis checks share one manual catalog transaction while all details avoid chat scans", async () => {
  const repo = repository(), pending = deferred(), envelope = activityEnvelope(repo), fresh = activityEnvelope(repo, cachedEnvelope(repo, {}, "ready")), h = harness({ snapshot: { ...envelope, operation: operation(randomUUID(), "attention", [blockedReceipt(repo, activityDiagnostic())]) }, hook(call) { if (call.url.startsWith(BASE + "/versions?")) return pending.promise; } });
  await h.ready(); await h.expand(); const status = h.byClass("repository-publish-compact-status"); status.click(); status.click(); await settle(); assert.equal(activityCalls(h).length, 0); assert.equal(versionCalls(h).length, 0);
  h.byClass("repository-publish-diagnosis-recheck").click(); h.byClass("repository-publish-diagnosis-recheck").click(); await settle(); assert.equal(versionCalls(h).length, 1); assert.equal(h.byClass("repository-publish-primary").disabled, true);
  pending.resolve(response(fresh)); await settle(); assert.equal(activityCalls(h).length, 0); assert.equal(h.posts().length, 0);
});
await test("saved-work publication defaults on and its compact global setting saves without confirmation or upload", async () => {
  const initial = settings(); delete initial.naming.allowActiveWork;
  const h = harness({ lang: "en", snapshot: { settings: initial } }); await h.ready(); assert.equal(h.fields("allowActiveWork").length, 0); await h.open();
  const input = h.fields("allowActiveWork")[0]; assert.equal(input.checked, true); assert.equal(h.visible(input), false);
  const section = h.all().find(item => item.tagName === "DETAILS" && item.contains(input)); assert.equal(section.children[0].textContent, "Upload behavior and naming"); section.children[0].click();
  assert.equal(h.visible(input), true); assert.match(h.byClass("repository-publish-policy-hint").textContent, /On by default.*staged selections and Git conflicts/);
  await h.change("allowActiveWork", false); assert.equal(h.posts("/config").length, 1); assert.equal(h.posts("/config")[0].body.settings.naming.allowActiveWork, false); assert.equal(h.posts("/run").length, 0);
  h.button("Close").click(); await h.open(); assert.equal(h.fields("allowActiveWork")[0].checked, false); assert.equal(h.posts("/run").length, 0); h.locale("zh-CN"); assert.match(h.byClass("repository-publish-policy-hint").textContent, /默认开启/);
});
const policyActivityReply = (repo, extra = {}) => liveActivityReply(repo, null, { activityClear: false, publicationAllowed: true, activityPolicy: "allow_saved_snapshot", activityNotice: activityDiagnostic(), ...extra });
await test("passive saved-work history never invents a fresh clear or upload permission", async () => {
  const repo = repository(), original = activityDiagnostic(), envelope = activityEnvelope(repo), result = blockedReceipt(repo, original, { activityPolicy: "allow_saved_snapshot", activityNotice: original });
  const h = harness({ lang: "en", snapshot: { ...envelope, operation: operation(randomUUID(), "attention", [result]) }, hook(call) { if (call.url.startsWith(BASE + "/activity?")) return response(policyActivityReply(repo)); } });
  await h.ready(); await h.expand(); h.byClass("repository-publish-compact-status").click(); await settle(); await h.emitWindow("focus"); await h.emitWindow("pageshow");
  assert.equal(h.snapshot.settings.naming.allowActiveWork, true); assert.deepEqual(h.snapshot.operation.repositories[0], result); assert.equal(h.byClass("repository-publish-current-activity").dataset.state, "unknown");
  assert.equal(activityCalls(h).length, 0); assert.equal(versionCalls(h).length, 0); assert.doesNotMatch(h.byClass("repository-publish-compact-status").textContent, /Uploaded|Ready|cleared/); assertPastAttemptIsNotCurrent(h); assert.equal(h.posts().length, 0);
});
await test("strict or unconfirmed actor history remains retained without a fresh permission claim", async () => {
  for (const strict of [true, false]) {
    const repo = repository(), original = activityDiagnostic(strict ? {} : { code: "activity_unconfirmed", blockers: undefined }), configured = settings([repo]); configured.naming.allowActiveWork = !strict;
    const envelope = activityEnvelope(repo), result = blockedReceipt(repo, original), h = harness({ lang: "en", snapshot: { ...envelope, settings: configured, operation: operation(randomUUID(), "attention", [result]) }, hook(call) { if (call.url.startsWith(BASE + "/activity?")) return response(policyActivityReply(repo)); } });
    await h.ready(); await h.expand(); h.byClass("repository-publish-compact-status").click(); await settle();
    assert.equal(h.snapshot.settings.naming.allowActiveWork, !strict); assert.equal(h.snapshot.operation.repositories[0].diagnostic.code, strict ? "activity_active" : "activity_unconfirmed"); assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, original.summary);
    assert.equal(h.byClass("repository-publish-current-activity").dataset.state, "unknown"); assertPastAttemptIsNotCurrent(h); assert.equal(activityCalls(h).length, 0); assert.equal(h.posts().length, 0);
  }
});
await test("manual catalog Git locks remain a hard current blocker under the saved-work policy", async () => {
  const repo = repository(), envelope = activityEnvelope(repo), lock = diagnostic({ code: "git_lock", category: "repository", summary: "An actual Git lock file is present; ownership remains unconfirmed.", nextStep: "Preserve it while its origin is checked.", target: null }), fresh = activityEnvelope(repo, cachedEnvelope(repo, { diagnostic: lock }, "ready")), h = harness({ lang: "en", snapshot: { ...envelope, operation: operation(randomUUID(), "attention", [blockedReceipt(repo, activityDiagnostic())]) }, hook(call) { if (call.url.startsWith(BASE + "/versions?")) return response(fresh); } });
  await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-status").dataset.attention, "true"); assert.equal(h.byClass("repository-publish-compact-status").textContent, "Git lock file found"); assert.equal(h.byClass("repository-publish-row-reason").textContent, lock.summary); assert.equal(activityCalls(h).length, 0); assert.equal(h.posts().length, 0);
});
await test("unrequested contradictory saved-work receipts cannot grant permission", async () => {
  for (const extra of [{ activityClear: false, publicationAllowed: true, activityPolicy: "strict" }, { activityClear: true, diagnostic: activityDiagnostic() }, { publicationAllowed: true, activityNotice: null }, { activityPolicy: "invented_policy" }]) {
    const repo = repository(), original = activityDiagnostic(), envelope = activityEnvelope(repo), untrusted = policyActivityReply(repo, { ...extra, activityNotice: activityDiagnostic({ summary: "Unrequested permission must never be adopted." }) });
    const h = harness({ lang: "en", snapshot: { ...envelope, operation: operation(randomUUID(), "attention", [blockedReceipt(repo, original)]) }, hook(call) { if (call.url.startsWith(BASE + "/activity?")) return response(untrusted); } });
    await h.ready(); await h.expand(); h.byClass("repository-publish-compact-status").click(); await settle();
    assert.equal(activityCalls(h).length, 0); assert.equal(h.byClass("repository-publish-current-activity").dataset.state, "unknown"); assert.doesNotMatch(h.all().map(item => item.textContent).join(" "), /Unrequested permission/); assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, original.summary); assert.equal(h.posts().length, 0);
  }
});
await test("a local catalog success does not claim chat clearance Git readiness or remote delivery", async () => {
  const repo = repository(), original = activityDiagnostic(), envelope = activityEnvelope(repo), fresh = activityEnvelope(repo, cachedEnvelope(repo, { hasChanges: false, changeState: "unchanged", worktreeChanged: false, outgoingCommits: 0, headSha: "c".repeat(40), outgoingBaselineSha: "c".repeat(40), syncChanged: false, syncState: "none", pendingRecovery: true }, "ready"));
  const h = harness({ lang: "en", snapshot: { ...envelope, operation: operation(randomUUID(), "verification_required", [blockedReceipt(repo, original, { status: "verification_required", phase: "verify" })]) }, hook(call) { if (call.url.startsWith(BASE + "/versions?")) return response(fresh); } });
  await h.ready(); await expandAndCheck(h); h.byClass("repository-publish-compact-status").click(); await settle();
  assert.equal(h.byClass("repository-publish-current-activity").dataset.state, "unknown"); assert.notEqual(h.byClass("repository-publish-compact-status").textContent, "No changes"); assert.doesNotMatch(h.byClass("repository-publish-compact-status").textContent, /Uploaded|Ready|cleared/);
  assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, original.summary); assert.equal(h.snapshot.operation.repositories[0].status, "verification_required"); assert.equal(activityCalls(h).length, 0); assert.equal(h.posts().length, 0);
});
await test("an active upload can show the actual saved-work notice without replacing its measured phase or result", async () => {
  const repo = repository(), item = { ...progressItem(repo, "working", "push"), activityPolicy: "allow_saved_snapshot", activityNotice: activityDiagnostic() }, h = harness({ lang: "en", snapshot: { operation: operation(randomUUID(), "working", [item]) } }); await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-status").textContent, "Uploading"); assert.equal(h.byClass("repository-publish-row-reason").textContent, "A chat is working; saved work may be uploaded."); assert.equal(h.posts().length, 0);
});
await test("Git failure details show only verified operation, exit code and error-kind metadata on demand", async () => {
  for (const exitCode of [128, -1073741510, 4294967295]) {
    const repo = repository(), reason = diagnostic({ code: "git_network", category: "network", summary: "Fetching the remote failed because its host could not be resolved.", operationKind: "fetch", exitCode, errorKind: "resolve_host", stderr: "secret-token@host" }), h = harness({ lang: "en", snapshot: { operation: operation(randomUUID(), "attention", [blockedReceipt(repo, reason, { phase: "remote" })]) } }); await h.ready(); await expandAndCheck(h); assertPastAttemptIsNotCurrent(h); h.byClass("repository-publish-compact-status").click(); await settle();
    const details = h.byClass("repository-publish-git-metadata"); assert.equal(h.visible(details), false); h.byClass("repository-publish-last-attempt").children[0].click(); assert.equal(h.visible(details), true); assert.equal(details.textContent, `Git fetch · Exit code ${exitCode} · Error kind · resolve_host`); assert.doesNotMatch(h.all().map(item => item.textContent).join(" "), /secret-token|Git hook/); h.locale("zh-CN"); assert.match(details.textContent, /Git fetch.*退出码/); assert.equal(h.posts().length, 0);
  }
  for (const lang of ["en", "zh-CN"]) {
    const repo = repository(), reason = diagnostic({ code: "git_network", category: "network", summary: "TLS verification failed while checking the remote.", operationKind: "ls-remote", exitCode: 128, errorKind: "tls_failed", stderr: "secret-token@host" });
    const h = harness({ lang, snapshot: { operation: operation(randomUUID(), "attention", [blockedReceipt(repo, reason, { phase: "version" })]) } }); await h.ready(); await expandAndCheck(h);
    const status = h.byClass("repository-publish-compact-status"); assertPastAttemptIsNotCurrent(h); status.click(); await settle(); assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, reason.summary);
    assert.equal(status.dataset.attention, "false"); assert.equal(h.byClass("repository-publish-row-reason").hidden, true); assert.match(h.byClass("repository-publish-git-metadata").textContent, /Git ls-remote.*128.*tls_failed/);
    assert.equal(h.byClass("repository-publish-row-activity").hidden, true); assert.doesNotMatch(h.all().map(item => item.textContent).join(" "), /secret-token/); assert.equal(h.posts().length, 0);
  }
});
await test("unknown, hostile or ill-typed Git metadata is omitted without fabricating a hook diagnosis", async () => {
  for (const extra of [{ operationKind: "exec https://secret-token@example.invalid", errorKind: "<img src=x>", exitCode: true }, { operationKind: "unknown-command", errorKind: "invented", exitCode: "128" }, { exitCode: 4294967296 }, { exitCode: -2147483649 }, { exitCode: 1.5 }]) {
    const repo = repository(), reason = diagnostic({ code: "git_failed", category: "repository", summary: "The Git operation failed; the original work is retained.", ...extra }), h = harness({ lang: "en", snapshot: { operation: operation(randomUUID(), "attention", [blockedReceipt(repo, reason)]) } }); await h.ready(); await expandAndCheck(h); h.byClass("repository-publish-compact-status").click(); await settle(); assert.equal(h.byClass("repository-publish-git-metadata").hidden, true); assert.doesNotMatch(h.all().map(item => item.textContent).join(" "), /secret-token|unknown-command|invented|<img|Git hook/); assert.equal(h.posts().length, 0);
  }
});
await test("passive local status cannot erase the retained historical Git failure details", async () => {
  const repo = repository(), envelope = activityEnvelope(repo), reason = diagnostic({ code: "legacy_git_error", category: "unknown", summary: "The original Git operation failed before uploading; the subtype was not retained.", target: null });
  const h = harness({ lang: "en", snapshot: { ...envelope, operation: operation(randomUUID(), "attention", [blockedReceipt(repo, reason)]) }, hook(call) { if (call.url.startsWith(BASE + "/activity?")) return response(policyActivityReply(repo)); } });
  await h.ready(); await h.expand(); h.byClass("repository-publish-compact-status").click(); await settle(); await h.emitWindow("focus");
  assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, reason.summary); assert.equal(h.byClass("repository-publish-git-metadata").hidden, true); assert.equal(h.byClass("repository-publish-current-activity").dataset.state, "unknown");
  assertPastAttemptIsNotCurrent(h); assert.equal(activityCalls(h).length, 0); assert.equal(versionCalls(h).length, 0); assert.equal(h.posts().length, 0);
});
const freshCleanCatalog = (repo, extra = {}) => ({ repoId: repo.id, components: [component()], repositoryVersion: { state: "current", currentVersion: "2.3.4", transition: null },
  hasChanges: false, changeState: "unchanged", worktreeChanged: false, outgoingCommits: 0, headSha: "c".repeat(40), outgoingBaselineSha: "c".repeat(40), syncChanged: false, syncState: "none", pendingRecovery: false, readState: "ready", ...extra });
await test("a new batch omits freshly confirmed clean rows and preserves stable green-before-unknown order", async () => {
  const repos = [repository(), repository({ id: "unknown-repo", path: "D:/Unknown" }), repository({ id: "green-second", path: "D:/Green2" }), repository({ id: "green-first", path: "D:/Green1" })];
  const catalogs = [freshCleanCatalog(repos[0]), freshCleanCatalog(repos[1], { hasChanges: null, changeState: "unknown", worktreeChanged: null, pendingRecovery: null }),
    ...repos.slice(2).map(repo => freshCleanCatalog(repo, { hasChanges: true, changeState: "changed", worktreeChanged: true }))];
  const h = harness({ snapshot: { settings: settings(repos) }, catalog: { repositories: catalogs }, hook(call) {
    if (call.url === BASE + "/run") return response(operation(call.body.requestId, "queued", call.body.repoIds.map(id => progressItem(repos.find(repo => repo.id === id)))));
  } });
  await h.ready(); await expandAndCheck(h); h.byClass("repository-publish-primary").click(); await settle();
  const posted = h.posts("/run"); assert.equal(posted.length, 1); assert.deepEqual(posted[0].body.repoIds, ["green-second", "green-first", "unknown-repo"]);
  assert.deepEqual(JSON.parse(h.storage.get(KEY + ".payload")).repoIds, posted[0].body.repoIds); assert.equal(posted[0].body.intent, "commit_and_push");
  assert.equal(h.byClass("repository-publish-row-activity", rowFor(h, repos[0].id)).hidden, true); assertProgress(h, 0, 3);
});
await test("all freshly clean repositories perform no POST or identity allocation and preserve their existing rows", async () => {
  const repos = [repository(), repository({ id: "second-clean", path: "D:/Second" })], h = harness({ snapshot: { settings: settings(repos), operation: operation(randomUUID(), "success", repos.map(repo => progressItem(repo, "noop", "complete"))) }, catalog: { repositories: repos.map(repo => freshCleanCatalog(repo)) } });
  await h.ready(); await expandAndCheck(h); const before = structuredClone(h.snapshot.settings); h.byClass("repository-publish-primary").click(); await settle();
  assert.equal(h.posts().length, 0); assert.equal(h.storage.has(KEY), false); assert.equal(h.storage.has(KEY + ".payload"), false);
  assert.match(progressText(h), /均无改动.*无需提交或推送/); assert.deepEqual(h.snapshot.settings, before);
  for (const repo of repos) { const row = rowFor(h, repo.id); assert.equal(h.byClass("repository-publish-compact-version", row).dataset.changeState, "unchanged"); assert.equal(h.byClass("repository-publish-row-activity", row).hidden, true); h.byClass("repository-publish-row-push", row).click(); }
  await settle(); assert.equal(h.posts("/run").length, 0); assert.equal(h.storage.has(KEY), false);
});
await test("unknown recovery, outgoing state, sync comparison, or stale display never narrows a new request", async () => {
  for (const extra of [{ pendingRecovery: null }, { pendingRecovery: undefined }, { pendingRecovery: true }, { worktreeChanged: null }, { outgoingCommits: null }, { outgoingCommits: 1 },
    { syncChanged: null }, { syncState: "unknown" }, { displayOnly: true }, { cached: true }, { stale: true }, { readState: "error" }]) {
    const repo = repository(), h = harness({ catalog: { repositories: [freshCleanCatalog(repo, extra)] } }); await h.ready(); await expandAndCheck(h);
    assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown", JSON.stringify(extra));
    h.byClass("repository-publish-primary").click(); await settle(); assert.deepEqual(h.posts("/run")[0].body.repoIds, [repo.id]);
  }
});
await test("sync-file repositories are omitted only after a current successful external comparison", async () => {
  const repo = repository({ syncFiles: [{ source: "D:/Saved/work.txt", target: "work.txt" }] });
  for (const syncState of ["none", "unknown", undefined]) {
    const h = harness({ snapshot: { settings: settings([repo]) }, catalog: { repositories: [freshCleanCatalog(repo, { syncState })] } }); await h.ready(); await expandAndCheck(h);
    assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown"); h.byClass("repository-publish-primary").click(); await settle(); assert.equal(h.posts("/run").length, 1);
  }
  const clean = harness({ snapshot: { settings: settings([repo]) }, catalog: { repositories: [freshCleanCatalog(repo, { syncState: "unchanged" })] } }); await clean.ready(); await expandAndCheck(clean);
  clean.byClass("repository-publish-primary").click(); await settle(); assert.equal(clean.posts().length, 0);
});
await test("a formerly clean catalog past the freshness bound is visibly unknown and remains selected", async () => {
  const clock = { now: Date.parse("2026-10-16T02:30:00Z") }, repo = repository(), h = harness({ clock, catalog: { repositories: [freshCleanCatalog(repo)] } });
  await h.ready(); await expandAndCheck(h); clock.now += 60001; h.locale("en");
  assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown"); assert.match(h.byClass("repository-publish-version-freshness").textContent, /Last known/i);
  h.byClass("repository-publish-primary").click(); await settle(); assert.equal(h.posts("/run").length, 1);
});
await test("a behind or unverifiable local baseline cannot become a white row or disappear from a new request", async () => {
  for (const extra of [{ outgoingBaselineSha: "d".repeat(40) }, { outgoingBaselineSha: "" }, { outgoingBaselineSha: null }, { headSha: "invalid", outgoingBaselineSha: "invalid" }, { headSha: null, outgoingBaselineSha: null }]) {
    const repo = repository(), h = harness({ catalog: { repositories: [freshCleanCatalog(repo, extra)] } }); await h.ready(); await expandAndCheck(h);
    assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown"); assert.equal(h.byClass("repository-publish-compact-status").textContent, "变化未核对");
    h.byClass("repository-publish-primary").click(); await settle(); assert.deepEqual(h.posts("/run")[0].body.repoIds, [repo.id]);
  }
});
await test("an old pending request retains its exact original clean-inclusive scope and order", async () => {
  const repos = [repository(), repository({ id: "green-repo", path: "D:/Green" })], id = randomUUID(), original = { requestId: id, repoIds: repos.map(repo => repo.id), createdAt: Date.now(), intent: "commit_and_push" };
  const storage = new Map([[KEY, id], [KEY + ".payload", JSON.stringify(original)]]), h = harness({ storage, snapshot: { settings: settings(repos) }, catalog: { repositories: [freshCleanCatalog(repos[0]), freshCleanCatalog(repos[1], { hasChanges: true, changeState: "changed", worktreeChanged: true })] }, hook(call) {
    if (call.url.startsWith(BASE + "/operation?")) return response(null);
  } });
  await h.ready(); await h.poll(); await h.open(); const resume = h.button("继续原请求"); assert.ok(resume); assert.equal(resume.hidden, false); resume.click(); await settle();
  assert.deepEqual(h.posts("/run")[0].body, { requestId: id, repoIds: original.repoIds, intent: "commit_and_push" });
});
await test("server-confirmed noops have no phase or progress track during another repository upload", async () => {
  const repos = [repository(), repository({ id: "uploading-repo", path: "D:/Uploading" })], rows = [progressItem(repos[0], "noop", "complete"), progressItem(repos[1], "working", "push")];
  const h = harness({ snapshot: { settings: settings(repos), operation: operation(randomUUID(), "working", rows) }, catalog: { repositories: [freshCleanCatalog(repos[0]), freshCleanCatalog(repos[1], { hasChanges: true, changeState: "changed", worktreeChanged: true })] } });
  await h.ready(); await expandAndCheck(h); const skipped = rowFor(h, repos[0].id); assert.equal(h.byClass("repository-publish-row-activity", skipped).hidden, true); assert.equal(h.byClass("repository-publish-row-spinner", skipped).hidden, true);
  assert.equal(h.byClass("repository-publish-row-activity", rowFor(h, repos[1].id)).hidden, false); assertProgress(h, 1, 2);
  h.snapshot.operation = operation(h.snapshot.operation.requestId, "success", [rows[0], progressItem(repos[1], "success", "complete")]); await h.poll(); assert.match(assertProgress(h, 2, 2), /成功\s*1.*跳过\s*1/);
});
await test("repository semantic authority replaces every upload count while keeping plugin versions independent", async () => {
  for (const count of [0, 5, null]) {
    const repo = repository(), item = menuCatalog(repo, menuComponents(), uploadSummary(repo, { count }), "1.0.0"), h = harness({ catalog: { repositories: [item] } });
    await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.0.0"); h.locale("en"); assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.0.0");
    assert.ok(menuOptions(h).some(option => option.textContent.includes("0.77.38"))); assert.doesNotMatch(h.all().map(node => node.textContent).join(" "), /Push\s*#|上传\s*#/); assert.equal(h.posts().length, 0);
  }
});
await test("an initial repository floor is visibly an unsaved preview and never rewrites independent plugins", async () => {
  const item = menuCatalog(); item.repositoryVersion = { state: "initial", currentVersion: "1.0.0", transition: null };
  const h = harness({ catalog: { repositories: [item] } }); await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.0.0"); assert.match(h.byClass("repository-publish-compact-version").title, /首次提交.*尚未保存/);
  assert.deepEqual(menuOptions(h).map(option => option.textContent), ["Character Designer 0.77.38", "Node library 0.3.1", "RR Helper 0.2.60"]); assert.equal(h.posts().length, 0);
});
await test("invalid repository authority never falls back to a plugin or upload sequence", async () => {
  for (const repositoryVersion of [{ state: "unknown", currentVersion: "1.2.3" }, { state: "current", currentVersion: "0.4.0" }, { state: "current", currentVersion: "5" }, { state: "current", currentVersion: "01.2.3" }, { state: "current", currentVersion: "1.0.0-alpha" }, { state: "current", currentVersion: "1.2.3-01" }]) {
    const item = menuCatalog(); item.repositoryVersion = repositoryVersion; const h = harness({ catalog: { repositories: [item] } }); await h.ready(); await expandAndCheck(h);
    assert.equal(h.byClass("repository-publish-compact-version").textContent, "版本读取失败"); assert.equal(h.posts().length, 0);
  }
});
await test("a real below-floor source shows an unsaved green initialization transition without claiming the file changed", async () => {
  const repo = repository(), item = freshCleanCatalog(repo, { hasChanges: true, changeState: "changed", components: [component({ currentVersion: "0.4.0", headVersion: "0.4.0", worktreeChanged: false, versionChanged: false })],
    repositoryVersion: { state: "initial", currentVersion: "1.0.0", nextVersion: "1.0.0", transition: { kind: "initial", fromVersion: "0.4.0", toVersion: "1.0.0" } } });
  const h = harness({ catalog: { repositories: [item] } }); await h.ready(); await expandAndCheck(h);
  assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.0.0"); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "changed");
  assert.match(h.byClass("repository-publish-compact-version").title, /尚未保存/); assert.equal(h.catalog.repositories[0].components[0].currentVersion, "0.4.0"); assert.equal(h.posts().length, 0);
  h.catalog.repositories[0].displayOnly = true; await h.emitWindow("focus"); await checkAll(h); assert.equal(h.byClass("repository-publish-compact-version").textContent, "1.0.0"); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown"); assert.equal(h.posts().length, 0);
});
await test("a failed refresh cannot omit a repository that was previously confirmed clean", async () => {
  const repo = repository(), h = harness({ catalog: { repositories: [freshCleanCatalog(repo)] } }); await h.ready(); await expandAndCheck(h);
  h.hook(call => { if (call.url.startsWith(BASE + "/versions?")) throw new Error("isolated refresh failed"); }); await h.emitWindow("focus"); await checkAll(h);
  assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown"); h.byClass("repository-publish-primary").click(); await settle(); assert.deepEqual(h.posts("/run")[0].body.repoIds, [repo.id]);
});
await test("Push All and each row Push explicitly retain commit-and-push semantics in both languages", async () => {
  const h = harness(); await h.ready(); assert.equal(h.byClass("repository-publish-primary").textContent, "全部上传"); h.locale("en"); assert.equal(h.byClass("repository-publish-primary").textContent, "Push All");
  assert.match(h.byClass("repository-publish-primary").getAttribute("aria-label"), /Push All.*Commit and push saved changes/); assert.equal(h.byClass("repository-publish-config").textContent, "Configure All");
  await expandAndCheck(h); const one = h.byClass("repository-publish-row-push"); assert.equal(one.textContent, "Push"); assert.match(one.getAttribute("aria-label"), /Push.*Music.*Commit and push/);
  h.locale("zh-CN"); assert.equal(one.textContent, "上传"); assert.match(one.title, /提交并上传/);
  assert.match(css, /compact-name:focus-visible/);
  assert.match(css, /@media \(max-width: 620px\)[^\n]*\.repository-publish-row-push \{[^}]*grid-column: 2;[^}]*grid-row: 1;[^}]*justify-self: end/);
  assert.doesNotMatch(css, /\.repository-publish-row-config\b/);
  assert.equal(h.button("Push only"), undefined); assert.equal(h.button("仅推送"), undefined); assert.equal(h.posts().length, 0);
});
await test("legacy missing snapshots never paint a fallback title or an invented repository version before fresh reads", async () => {
  for (const components of [[], [component({ currentVersion: "not-a-version" })]]) {
    const repo = repository(), envelope = cachedEnvelope(repo, { components, versionState: "missing", repositoryVersion: undefined, message: "Legacy fallback title retained only as historical information" }, "idle");
    const h = harness({ snapshot: { settings: settings([repo]), ...envelope }, hook(call) { if (call.url.includes("/versions?snapshot=1")) return new Promise(() => {}); } });
    await h.ready(); await expandAndCheck(h); const version = h.byClass("repository-publish-compact-version");
    assert.equal(version.textContent, "版本待读取"); assert.equal(version.dataset.changeState, "unknown"); assert.doesNotMatch(version.textContent, /备用标题|无版本|1\.0\.0|Push\s*#|上传\s*#/);
    assert.equal(h.posts().length, 0); h.api.destroy();
  }
});
await test("an empty or invalid legacy version becomes a read failure after a failed snapshot refresh", async () => {
  for (const components of [[], [component({ currentVersion: "0.4.0" })]]) {
    const repo = repository(), old = cachedEnvelope(repo, { components, versionState: "missing", repositoryVersion: undefined }, "idle"), failed = cachedEnvelope(repo, { components, versionState: "missing", repositoryVersion: undefined }, "error");
    const h = harness({ snapshot: { settings: settings([repo]), ...old }, hook(call) { if (call.url.includes("/versions?snapshot=1")) return response(failed); } });
    await h.ready(); await expandAndCheck(h); const version = h.byClass("repository-publish-compact-version");
    assert.equal(version.textContent, "版本读取失败"); assert.equal(version.dataset.changeState, "unknown"); assert.match(h.byClass("repository-publish-version-freshness").textContent, /核对失败/);
    assert.equal(h.posts().length, 0); h.api.destroy();
  }
});
await test("a terminal TLS attempt stays in details while fresh local changes or clean state lead the row", async () => {
  for (const changed of [true, false]) {
    const repo = repository(), reason = diagnostic({ code: "git_network", category: "network", target: null, summary: "The last remote check failed TLS verification.", operationKind: "ls-remote", exitCode: 128, errorKind: "tls_failed" });
    const h = harness({ lang: "en", snapshot: { operation: operation(randomUUID(), "attention", [blockedReceipt(repo, reason, { phase: "version" })]) },
      catalog: { repositories: [freshCleanCatalog(repo, { hasChanges: changed, changeState: changed ? "changed" : "unchanged", worktreeChanged: changed, diagnostic: null })] } });
    await h.ready(); await expandAndCheck(h); const status = h.byClass("repository-publish-compact-status"), version = h.byClass("repository-publish-compact-version");
    assert.equal(status.textContent, changed ? "Changes to commit" : "No changes"); assert.equal(version.dataset.changeState, changed ? "changed" : "unchanged");
    assertPastAttemptIsNotCurrent(h); assert.doesNotMatch(status.textContent, /TLS|remote|verified|successful/i); assert.match(h.byClass("repository-publish-status").textContent, /^Last operation · Processed 1\/1/);
    status.click(); await settle(); assert.equal(h.byClass("repository-publish-last-attempt").open, false); assert.equal(h.visible(h.byClass("repository-publish-diagnosis-summary")), false);
    h.byClass("repository-publish-last-attempt").children[0].click(); assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, reason.summary);
    assert.equal(h.byClass("repository-publish-git-metadata").textContent, "Git ls-remote · Exit code 128 · Error kind · tls_failed");
    h.locale("zh-CN"); assert.match(h.byClass("repository-publish-status").textContent, /^上次操作/); assert.equal(h.posts().length, 0); h.api.destroy();
  }
  const repo = repository(), envelope = activityEnvelope(repo, cachedEnvelope(repo, freshCleanCatalog(repo), "ready"));
  const oldLock = diagnostic({ code: "git_lock", category: "repository", target: null, summary: "A prior activity read observed an old lock." });
  const h = harness({ lang: "en", snapshot: { ...envelope, operation: operation(randomUUID(), "attention", [blockedReceipt(repo, activityDiagnostic())]) }, hook(call) {
    if (call.url.includes("/versions?snapshot=1")) return response(envelope);
    if (call.url.startsWith(BASE + "/activity?")) return response(policyActivityReply(repo, { publicationAllowed: false, diagnostic: oldLock, activityNotice: null }));
  } });
  await h.ready(); await expandAndCheck(h); h.byClass("repository-publish-compact-status").click(); await settle();
  assert.equal(h.byClass("repository-publish-current-activity").dataset.state, "unknown"); assert.equal(h.byClass("repository-publish-compact-status").textContent, "No changes");
  assertPastAttemptIsNotCurrent(h); assert.equal(h.posts().length, 0); h.api.destroy();
});
await test("a terminal failure cannot color a current read but a newly observed Git lock is an amber blocker", async () => {
  const repo = repository(), pending = deferred(), old = cachedEnvelope(repo, { components: [component()] }, "idle"), reason = diagnostic({ code: "git_network", category: "network", target: null, operationKind: "ls-remote", exitCode: 128, errorKind: "tls_failed", summary: "Previous TLS failure." });
  const h = harness({ lang: "en", snapshot: { ...old, operation: operation(randomUUID(), "attention", [blockedReceipt(repo, reason)]) }, hook(call) { if (call.url.includes("/versions?snapshot=1")) return pending.promise; } });
  await h.ready(); await expandAndCheck(h); const status = h.byClass("repository-publish-compact-status"), activity = h.byClass("repository-publish-row-activity");
  assertPastAttemptIsNotCurrent(h); assert.equal(status.textContent, "Last known"); assert.equal(activity.hidden, true); assert.equal(h.all(activity).filter(n => n.className.split(" ").includes("repository-publish-row-spinner")).length, 1); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown");
  const lock = diagnostic({ code: "git_lock", category: "repository", target: null, summary: "The current local index lock still exists.", nextStep: "Wait for its owner; do not delete it." });
  pending.resolve(response(cachedEnvelope(repo, { diagnostic: lock }, "ready"))); await settle();
  assert.equal(status.textContent, "Git lock file found"); assert.equal(status.dataset.attention, "true"); assert.equal(h.byClass("repository-publish-row-reason").textContent, lock.summary); assert.equal(activity.hidden, true); assert.doesNotMatch(status.textContent, /TLS|Last upload/);
  status.click(); await settle(); assert.equal(h.byClass("repository-publish-diagnosis-summary").textContent, reason.summary); assert.equal(h.posts().length, 0); h.api.destroy();
});
await test("unresolved receipts never become confirmed clean from an unknown or cached read", async () => {
  for (const extra of [{ pendingRecovery: true }, { pendingRecovery: null }, { displayOnly: true }, { stale: true }]) {
    const repo = repository(), result = blockedReceipt(repo, null, { status: "verification_required", phase: "verify", message: "The original delivery remains unconfirmed." });
    const h = harness({ lang: "en", snapshot: { operation: operation(randomUUID(), "verification_required", [result]) }, catalog: { repositories: [freshCleanCatalog(repo, extra)] } });
    await h.ready(); await expandAndCheck(h); assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown"); assert.notEqual(h.byClass("repository-publish-compact-status").textContent, "No changes"); assert.equal(h.byClass("repository-publish-compact-status").dataset.attention, "true");
    h.byClass("repository-publish-primary").click(); await settle(); assert.deepEqual(h.posts("/run")[0].body.repoIds, [repo.id]); assert.equal(h.posts("/run")[0].body.intent, "commit_and_push"); h.api.destroy();
  }
});

await test("opening expanding focusing and pageshow remain passive with no Git catalog activity preview or writes", async () => {
  const repo = repository(), cached = cachedEnvelope(repo, freshCleanCatalog(repo), "ready"), h = harness({ lang: "en", snapshot: cached });
  await h.ready(); await h.expand(); await h.open(repo.id); await h.emitWindow("focus"); await h.emitWindow("pageshow");
  await h.setPanelHidden(true); await h.setPanelHidden(false); h.button("Close").click(); await h.open();
  assert.equal(versionCalls(h).length, 0); assert.equal(activityCalls(h).length, 0); assert.equal(h.posts().length, 0); assert.ok(h.calls.every(call => call.method === "GET" && call.url === BASE));
  assert.equal(h.byClass("repository-publish-compact-version").dataset.changeState, "unknown"); assert.equal(h.byClass("repository-publish-row-activity").hidden, true);
  assert.equal(h.byClass("repository-publish-check").disabled, false); assert.equal(h.byClass("repository-publish-primary").disabled, false); h.api.destroy();
});
await test("Check All stages partial rows and paints the whole final catalog once with both main buttons disabled", async () => {
  const repos = [repository(), repository({ id: "repository-002", path: "D:/Other", repositoryUrl: "https://github.com/example/Other" })];
  const h = harness({ lang: "en", snapshot: { settings: settings(repos) }, catalog: { repositories: repos.map(repo => menuCatalog(repo, [component({ currentVersion: "1.0.0" })], uploadSummary(repo), "1.0.0")) } });
  await h.ready(); await expandAndCheck(h);
  const versions = repos.map(repo => h.byClass("repository-publish-compact-version", rowFor(h, repo.id))), labels = [h.byClass("repository-publish-check").textContent, h.byClass("repository-publish-primary").textContent];
  const fresh = { repositories: repos.map((repo, index) => menuCatalog(repo, [component({ currentVersion: (index + 2) + ".0.0" })], uploadSummary(repo), (index + 2) + ".0.0")) };
  const partial = h.versionEnvelope(fresh); partial.complete = false; partial.refreshingIds = [repos[1].id]; partial.versionReadStates[repos[1].id].state = "reading";
  const final = deferred(); h.hook(call => call.url.startsWith(BASE + "/versions?") ? call.url.includes("refresh=1") ? response(partial) : final.promise : undefined);
  const firstPaint = h.paintEvents.length, before = versionCalls(h).length; await checkAll(h);
  const check = h.byClass("repository-publish-check"), push = h.byClass("repository-publish-primary");
  assert.equal(check.disabled, true); assert.equal(push.disabled, true); assert.equal(check.getAttribute("aria-busy"), "true"); assert.equal(push.getAttribute("aria-busy"), "true");
  assert.deepEqual([check.textContent, push.textContent], labels); assert.deepEqual(versions.map(item => item.textContent), ["1.0.0", "1.0.0"]);
  assert.ok(h.all().filter(item => item.className.split(" ").includes("repository-publish-row-activity")).every(item => item.hidden)); assert.equal(h.paintEvents.slice(firstPaint).filter(event => versions.includes(event.element)).length, 0);
  check.click(); push.click(); await settle(); assert.equal(versionCalls(h).length, before + 1); assert.equal(h.posts("/run").length, 0);
  await h.poll(); assert.equal(push.disabled, true); assert.deepEqual(versions.map(item => item.textContent), ["1.0.0", "1.0.0"]);
  final.resolve(response(h.versionEnvelope(fresh))); await settle();
  assert.deepEqual(versions.map(item => item.textContent), ["2.0.0", "3.0.0"]); assert.equal(check.disabled, false); assert.equal(push.disabled, false);
  assert.equal(h.paintEvents.slice(firstPaint).filter(event => versions.includes(event.element)).length, 2); assert.equal(versionCalls(h).slice(before).filter(call => call.url.includes("refresh=1")).length, 1); assert.equal(activityCalls(h).length, 0); assert.equal(h.posts().length, 0); h.api.destroy();
});
await test("busy Check All disables current and stale version plan actions and prevents configuration writes", async () => {
  const current = component(), stale = { sourceId: "old-source", currentVersion: "8.0.0", targetVersion: "8.0.1", expectedSha256: "a".repeat(64), expectedBytes: 100, planProof: "b".repeat(64) };
  const repo = repository({ versionPlans: [stale] }), h = harness({ lang: "en", snapshot: { settings: settings([repo]) }, catalog: { repositories: [{ repoId: repo.id, hasChanges: true, changeState: "changed", worktreeChanged: true, components: [current] }] } });
  await h.ready(); await openAndCheck(h, repo.id); const box = h.byClass("repository-publish-plan-box"), buttons = h.all(box).filter(item => item.tagName === "BUTTON"); assert.ok(buttons.length >= 2); assert.ok(buttons.every(item => !item.disabled));
  const pending = deferred(); h.hook(call => call.url.startsWith(BASE + "/versions?") ? pending.promise : undefined); const original = structuredClone(h.snapshot.settings); await checkAll(h);
  assert.ok(buttons.every(item => item.disabled)); for (const button of buttons) button.click(); await settle(); assert.equal(h.posts("/config").length, 0); assert.deepEqual(h.snapshot.settings, original);
  pending.resolve(response(h.versionEnvelope())); await settle(); assert.equal(h.byClass("repository-publish-primary").disabled, false); assert.equal(h.posts().length, 0); h.api.destroy();
});
await test("a failed manual Check All retains old rows and only another explicit click retries it", async () => {
  const repo = repository(), h = harness({ lang: "en", catalog: { repositories: [menuCatalog(repo)] } }); await h.ready(); await expandAndCheck(h);
  const version = h.byClass("repository-publish-compact-version"), old = version.textContent; h.hook(call => { if (call.url.startsWith(BASE + "/versions?")) throw new Error("fixture local reader offline"); });
  const before = versionCalls(h).length; await checkAll(h); assert.equal(version.textContent, old); assert.equal(h.byClass("repository-publish-primary").disabled, false); assert.equal(h.byClass("repository-publish-check").disabled, false); assert.equal(versionCalls(h).length, before + 1); assert.equal(h.posts().length, 0);
  await h.emitWindow("focus"); await h.emitWindow("pageshow"); assert.equal(versionCalls(h).length, before + 1);
  h.hook(null); await checkAll(h); assert.equal(versionCalls(h).length, before + 2); assert.equal(h.byClass("repository-publish-check").disabled, false); h.api.destroy();
});
await test("Push All can start without Check All and passive clean snapshots cannot hide newly saved work", async () => {
  const repos = [repository(), repository({ id: "repository-002", path: "D:/Other", repositoryUrl: "https://github.com/example/Other" })], cold = cachedEnvelope(repos[0], freshCleanCatalog(repos[0]), "ready");
  const h = harness({ lang: "en", snapshot: { ...cold, settings: settings(repos) } }); await h.ready(); h.byClass("repository-publish-primary").click(); await settle();
  assert.equal(h.posts("/run").length, 1); assert.deepEqual(h.posts("/run")[0].body.repoIds, repos.map(repo => repo.id)); assert.equal(h.posts("/run")[0].body.intent, "commit_and_push");
  assert.equal(versionCalls(h).length, 0); assert.equal(activityCalls(h).length, 0); assert.equal(h.posts("/preview").length, 0); assert.equal(h.posts("/config").length, 0); assert.equal(JSON.parse(h.storage.get(KEY + ".payload")).requestId, h.posts("/run")[0].body.requestId); h.api.destroy();
});
await test("the bounded manual check deadline preserves rows and never starts another refresh transaction", async () => {
  const clock = { now: Date.now() }, repo = repository(), h = harness({ lang: "en", clock, catalog: { repositories: [menuCatalog(repo)] } }); await h.ready(); await expandAndCheck(h);
  const old = h.byClass("repository-publish-compact-version").textContent, pending = h.versionEnvelope(); pending.complete = false; pending.refreshingIds = [repo.id]; pending.versionReadStates[repo.id].state = "reading";
  h.hook(call => call.url.startsWith(BASE + "/versions?") ? response(pending) : undefined); const before = versionCalls(h).length; await checkAll(h); clock.now += 60001; await h.poll();
  assert.equal(h.byClass("repository-publish-compact-version").textContent, old); assert.equal(h.byClass("repository-publish-check").disabled, false); assert.equal(h.byClass("repository-publish-primary").disabled, false);
  assert.equal(versionCalls(h).slice(before).filter(call => call.url.includes("refresh=1")).length, 1); assert.equal(h.posts().length, 0); assert.equal([...h.timers.values()].some(timer => timer.delay === 1200), false); h.api.destroy();
});
await test("an original pending request still polls without Check All and preserves its exact stored scope", async () => {
  const repos = [repository(), repository({ id: "repository-002", path: "D:/Other" })], id = randomUUID(), original = { requestId: id, repoIds: [repos[1].id, repos[0].id], createdAt: Date.now(), intent: "commit_and_push" }, storage = new Map([[KEY,id],[KEY+".payload",JSON.stringify(original)]]);
  const h = harness({ storage, snapshot: { settings: settings(repos), operation: operation(id, "working", []) } }); await h.ready(); await h.expand(); await h.emitWindow("pageshow"); await h.poll();
  assert.ok(h.calls.some(call => call.url === BASE + "/operation?requestId=" + id)); assert.equal(versionCalls(h).length, 0); assert.equal(activityCalls(h).length, 0); assert.equal(h.posts().length, 0); assert.deepEqual(JSON.parse(storage.get(KEY + ".payload")), original); h.api.destroy();
});

const singleEnvelope = (h, id, catalog) => {
  const envelope = h.versionEnvelope(catalog);
  return { ...envelope, versionSources: envelope.versionSources.filter(item => item.repoId === id),
    versionSnapshots: envelope.versionSnapshots.filter(item => item.repoId === id),
    versionReadStates: { [id]: envelope.versionReadStates[id] },
    repositories: envelope.repositories.filter(item => item.repoId === id) };
};
await test("Check All shows its circle synchronously before a response and clears it on completion", async () => {
  const pending = deferred(), h = harness({ lang: "en", hook(call) { if (call.url.startsWith(BASE + "/versions?")) return pending.promise; } });
  await h.ready(); await h.expand(); const check = h.byClass("repository-publish-check"), circle = h.byClass("repository-publish-check-spinner");
  assert.equal(circle.hidden, true); check.click();
  assert.equal(circle.hidden, false); assert.equal(check.disabled, true); assert.equal(check.getAttribute("aria-busy"), "true");
  assert.ok(h.all().filter(item => item.className.split(" ").includes("repository-publish-version-spinner")).every(item => item.hidden));
  pending.resolve(response(h.versionEnvelope())); await settle();
  assert.equal(circle.hidden, true); assert.equal(check.disabled, false); assert.equal(check.getAttribute("aria-busy"), "false"); assert.equal(h.posts().length, 0); h.api.destroy();
});
await test("version click checks exactly one repository and only its version circle starts immediately", async () => {
  const repos = [repository(), repository({ id: "repository-002", path: "D:/Other" })], pending = deferred();
  const h = harness({ lang: "en", snapshot: { settings: settings(repos) }, hook(call) { if (call.url.startsWith(BASE + "/versions?")) return pending.promise; } });
  await h.ready(); await h.expand(); const row = rowFor(h, repos[1].id), version = h.byClass("repository-publish-compact-version", row);
  assert.equal(version.tagName, "BUTTON"); assert.match(version.getAttribute("aria-label"), /check/i); version.click();
  assert.equal(h.byClass("repository-publish-version-spinner", row).hidden, false);
  assert.equal(h.byClass("repository-publish-version-spinner", rowFor(h, repos[0].id)).hidden, true);
  assert.equal(h.byClass("repository-publish-check-spinner").hidden, true); assert.equal(version.getAttribute("aria-busy"), "true");
  await settle(); assert.equal(versionCalls(h).length, 1); assert.equal(versionCalls(h)[0].url, BASE + "/versions?snapshot=1&refresh=1&repoId=" + repos[1].id);
  pending.resolve(response(singleEnvelope(h, repos[1].id, { repositories: [menuCatalog(repos[1])] }))); await settle();
  assert.equal(version.textContent, "1.2.3"); assert.equal(version.disabled, false); assert.equal(version.getAttribute("aria-busy"), "false");
  assert.equal(h.byClass("repository-publish-version-spinner", row).hidden, true); assert.equal(h.posts().length, 0); assert.equal(activityCalls(h).length, 0); h.api.destroy();
});
await test("a partial single-repository snapshot polls its original scope without refreshing other rows", async () => {
  const repos = [repository(), repository({ id: "repository-002", path: "D:/Other" })], h = harness({ snapshot: { settings: settings(repos) }, catalog: { repositories: repos.map(repo => menuCatalog(repo)) } });
  await h.ready(); await expandAndCheck(h); const other = h.byClass("repository-publish-compact-version", rowFor(h, repos[0].id)), before = other.textContent;
  const partial = singleEnvelope(h, repos[1].id, { repositories: [menuCatalog(repos[1], [], uploadSummary(repos[1]), "2.0.0")] }); partial.complete = false; partial.refreshingIds = [repos[1].id]; partial.versionReadStates[repos[1].id].state = "reading";
  const final = deferred(); h.hook(call => call.url.startsWith(BASE + "/versions?") ? call.url.includes("refresh=1") ? response(partial) : final.promise : undefined);
  h.byClass("repository-publish-compact-version", rowFor(h, repos[1].id)).click(); await settle(); assert.equal(other.textContent, before); await h.poll();
  assert.equal(versionCalls(h).at(-1).url, BASE + "/versions?snapshot=1&repoId=" + repos[1].id);
  final.resolve(response({ ...partial, complete: true, refreshingIds: [], versionReadStates: { [repos[1].id]: { ...partial.versionReadStates[repos[1].id], state: "ready" } } })); await settle();
  assert.equal(other.textContent, before); assert.equal(other.dataset.changeState, "changed"); assert.equal(h.byClass("repository-publish-compact-version", rowFor(h, repos[1].id)).textContent, "2.0.0"); assert.equal(h.posts().length, 0); h.api.destroy();
});
await test("single-repository errors stop its circle and leave other ready repositories and errors untouched", async () => {
  const repos = [repository(), repository({ id: "repository-002", path: "D:/Other" })], h = harness({ lang: "en", snapshot: { settings: settings(repos) }, catalog: { repositories: repos.map(repo => menuCatalog(repo)) } });
  await h.ready(); await expandAndCheck(h); const rows = repos.map(repo => rowFor(h, repo.id)), otherStatus = h.byClass("repository-publish-compact-status", rows[0]).textContent;
  h.hook(call => call.url.startsWith(BASE + "/versions?") ? { ok: false, status: 503, json: async () => ({ error: "Fixture read unavailable" }) } : undefined);
  h.byClass("repository-publish-compact-version", rows[1]).click(); await settle();
  assert.equal(h.byClass("repository-publish-version-spinner", rows[1]).hidden, true); assert.equal(h.byClass("repository-publish-compact-version", rows[1]).disabled, false);
  assert.equal(h.byClass("repository-publish-compact-status", rows[0]).textContent, otherStatus); assert.equal(h.byClass("repository-publish-compact-status", rows[0]).dataset.attention, "false");
  assert.equal(h.byClass("repository-publish-compact-status", rows[1]).dataset.attention, "true"); const before = versionCalls(h).length;
  await h.emitWindow("focus"); await h.emitWindow("pageshow"); assert.equal(versionCalls(h).length, before); assert.equal(h.posts().length, 0); h.api.destroy();
});
await test("hiding Console aborts a single version check and a late reply cannot repaint it", async () => {
  const repo = repository(), pending = deferred(), h = harness({ catalog: { repositories: [menuCatalog(repo)] } }); await h.ready(); await expandAndCheck(h);
  const version = h.byClass("repository-publish-compact-version"), old = version.textContent; h.hook(call => call.url.startsWith(BASE + "/versions?") ? pending.promise : undefined);
  version.click(); await settle(); const request = versionCalls(h).at(-1); await h.setPanelHidden(true);
  assert.equal(request.options.signal.aborted, true); assert.equal(h.byClass("repository-publish-version-spinner").hidden, true);
  pending.resolve(response(singleEnvelope(h, repo.id, { repositories: [menuCatalog(repo, [], uploadSummary(repo), "9.0.0")] }))); await settle(); await h.setPanelHidden(false);
  assert.equal(version.textContent, old); assert.equal(version.disabled, false); assert.equal(h.byClass("repository-publish-check-spinner").hidden, true); assert.equal(h.posts().length, 0); h.api.destroy();
});
await test("plugin disclosure is separate from the version check button and remains read-only", async () => {
  const repo = repository(), h = harness({ lang: "en", catalog: { repositories: [menuCatalog(repo)] } }); await h.ready(); await expandAndCheck(h);
  const version = h.byClass("repository-publish-compact-version"), trigger = h.byClass("repository-publish-version-trigger"), picker = h.byClass("repository-publish-version-picker"), before = h.calls.length;
  assert.equal(trigger.contains(version), false); assert.equal(version.contains(trigger), false); assert.match(trigger.getAttribute("aria-label"), /plugin/i);
  trigger.click(); assert.equal(picker.open, true); assert.equal(h.calls.length, before); assert.equal(h.posts().length, 0); assert.equal(h.visible(version), true); h.api.destroy();
});
await test("failed Check All stops its circle and direct Push still works without another check", async () => {
  const h = harness({ lang: "en", hook(call) { if (call.url.startsWith(BASE + "/versions?")) throw new Error("Fixture offline"); } }); await h.ready(); await h.expand();
  const check = h.byClass("repository-publish-check"); check.click(); assert.equal(h.byClass("repository-publish-check-spinner").hidden, false); await settle();
  assert.equal(h.byClass("repository-publish-check-spinner").hidden, true); assert.equal(check.disabled, false);
  h.byClass("repository-publish-row-push").click(); await settle(); assert.equal(h.posts("/run").length, 1); assert.deepEqual(h.posts("/run")[0].body.repoIds, [repository().id]); assert.equal(h.posts("/run")[0].body.intent, "commit_and_push"); h.api.destroy();
});
await test("a failed first single check cannot label an untouched repository as failed", async () => {
  const repos = [repository(), repository({ id: "repository-002", path: "D:/Other" })], h = harness({ lang: "en", snapshot: { settings: settings(repos) }, hook(call) { if (call.url.startsWith(BASE + "/versions?")) throw new Error("Fixture offline"); } });
  await h.ready(); await h.expand(); const untouched = rowFor(h, repos[1].id), version = h.byClass("repository-publish-compact-version", untouched), status = h.byClass("repository-publish-compact-status", untouched), before = [version.textContent, status.textContent, status.dataset.attention];
  h.byClass("repository-publish-compact-version", rowFor(h, repos[0].id)).click(); await settle();
  assert.deepEqual([version.textContent, status.textContent, status.dataset.attention], before); assert.equal(h.byClass("repository-publish-version-spinner", untouched).hidden, true); assert.equal(h.posts().length, 0); h.api.destroy();
});
await test("a partial saved source map accepts a later explicit Check All without losing existing bindings", async () => {
  const repos = [repository(), repository({ id: "repository-002", path: "D:/Other" })], catalog = { repositories: repos.map(repo => menuCatalog(repo)) }, h = harness({ lang: "en", snapshot: { settings: settings(repos) }, catalog });
  const initial = singleEnvelope(h, repos[0].id, catalog); Object.assign(h.snapshot, initial);
  await h.ready(); await h.expand(); h.hook(call => call.url.startsWith(BASE + "/versions?") ? response(call.url.includes("repoId=") ? singleEnvelope(h, repos[0].id, catalog) : h.versionEnvelope(catalog)) : undefined);
  h.byClass("repository-publish-compact-version", rowFor(h, repos[0].id)).click(); await settle(); await checkAll(h);
  assert.deepEqual(repos.map(repo => h.byClass("repository-publish-compact-version", rowFor(h, repo.id)).textContent), ["1.2.3", "1.2.3"]);
  assert.ok(repos.every(repo => h.byClass("repository-publish-compact-version", rowFor(h, repo.id)).dataset.changeState === "changed")); assert.equal(h.posts().length, 0); h.api.destroy();
});

console.log(`PASS ${count} isolated repository-publish UI fixtures`);
