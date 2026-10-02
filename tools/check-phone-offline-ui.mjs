#!/usr/bin/env node
// Exercise the phone UI against isolated in-memory responses; no real plan or inbox writes.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
const swSource = readFileSync(new URL("../phone/sw.js", import.meta.url), "utf8");
const storeSource = readFileSync(new URL("../phone/store.js", import.meta.url), "utf8");

const source = readFileSync(new URL("../phone/app.js", import.meta.url), "utf8").replace(/\r\n?/g, "\n");
const html = readFileSync(new URL("../phone/index.html", import.meta.url), "utf8");
const css = readFileSync(new URL("../phone/styles.css", import.meta.url), "utf8");
const manifest = JSON.parse(readFileSync(new URL("../phone/manifest.webmanifest", import.meta.url), "utf8"));
const defer = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
const result = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, async json() { return body; } });
const plan = () => ({ plan: { version: 1, revision: "fixture-1", groups: Array.from({ length: 4 }, (_, index) => ({ id: `group-${index}`, title: ["示例计划一", "示例计划二", "示例计划三", "示例计划四"][index], summary: `摘要 ${index}`, items: [{ id: `task-${index}`, text: "<script>保留为文字</script>", done: index === 1 }] })) }, label: "计划清单（电脑浏览器中的勾选进度暂未同步）", error: "" });
const inbox = () => ({ entries: [
  { id: "to-read", path: "reports/one.md", title: "待阅读文件", summary: "一份报告", status: "inbox", createdAt: "2026-10-01T10:00:00+08:00" },
  { id: "later", path: "reports/later.md", title: "Later 文件", status: "later" },
  { id: "archived", path: "reports/archive.md", title: "归档文件", status: "archive", read: true }
] });
const dashboard = () => ({ version: "1.0.14", plan: plan(), device: { currentMemory: { status: "available", usedPercent: 91, availableBytes: 1024 ** 3, totalBytes: 16 * 1024 ** 3, readAt: "2026-10-01T11:00:00+08:00" }, model: "Dell fixture", cpuModel: "CPU", gpuModels: ["GPU"], sampledAt: "2026-09-27T11:00:00+08:00", installedMemoryBytes: 16 * 1024 ** 3 }, documents: { inbox: inbox(), guide: { items: [{ title: "阅读重点", path: "human.md", highlights: ["重点"] }] }, references: { items: [{ id: "nodes", defaultLanguage: "zh-CN", variants: [{ language: "zh-CN", label: "中文", title: "节点参考", path: "nodes.zh.md", available: true }, { language: "en", label: "English", title: "Nodes", path: "nodes.en.md", available: true }] }] } } });
const playlist = () => ({ playback: "phone", tracks: [{ name: "<script>One</script>", path: "local/one.mp3", type: "mp3", size: 100 }, { name: "Two", path: "album/two.m4a", type: "m4a", size: 200 }, { name: "三首", path: "album/three.mp3", type: "mp3", lyrics: true, lyricsLanguage: "zh", lyricsLanguages: [{ code: "zh", label: "Chinese" }, { code: "en", label: "English" }] }], truncated: false });
function harness({ syncEnabled = false } = {}) {
  class Element {
    constructor(tag = "div") { this.tagName = tag.toUpperCase(); this.children = []; this.listeners = new Map(); this.dataset = {}; this.attributes = {}; this._text = ""; this.hidden = false; this.value = ""; this.style = { setProperty(key, value) { this[key] = value; } }; }
    append(...items) { this.children.push(...items); }
    appendChild(item) { this.append(item); return item; }
    replaceChildren(...items) { this.children = items; this._text = ""; }
    set textContent(value) { this.replaceChildren(); this._text = String(value); }
    get textContent() { return this._text + this.children.map(item => item.textContent).join(""); }
    set innerHTML(_) { throw new Error("Raw HTML must never be used."); }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    removeAttribute(key) { delete this.attributes[key]; if (key === "src") this.src = ""; }
    addEventListener(key, fn) { this.listeners.set(key, fn); }
    focus() { this.focused = true; }
    scrollIntoView() { this.scrolled = true; }
    click() { this.clicked = true; }
    remove() { this.removed = true; }
  }
  const nodes = new Map(), calls = [], answers = [], saved = new Map(), timers = new Map(); let nextTimer = 1;
  const get = id => { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); };
  const audio = get("musicAudio"); audio.paused = true; audio.currentTime = 0; audio.duration = NaN; audio.src = ""; audio.playCalls = 0; audio.pauseCalls = 0; audio.loadCalls = 0; const mediaEvents = [];
  audio.pause = () => { audio.paused = true; audio.pauseCalls++; mediaEvents.push("pause"); };
  audio.load = () => { audio.loadCalls++; audio.duration = NaN; audio.currentTime = 0; mediaEvents.push("load"); };
  audio.play = () => { audio.playCalls++; mediaEvents.push("play"); if (audio.playError) return Promise.reject(audio.playError); audio.paused = false; return Promise.resolve(); };
  const tabs = ["tasks", "music", "device", "documents"].map(tab => { const button = new Element("button"); button.dataset.tab = tab; return button; });
  const listTabs = ["inbox", "later", "archive"].map(tab => { const button = new Element("button"); button.dataset.inbox = tab; return button; });
  const musicTabs = ["", "first", "second", "third"].map(tier => { const button = new Element("button"); button.dataset.musicTier = tier; return button; });
  const documentEvents = new Map(), windowEvents = new Map(), workerEvents = new Map(), registrationEvents = new Map(), registrations = [], reloads = [];
  const addEvent = (events, name, callback) => { const previous = events.get(name); events.set(name, (...args) => { previous?.(...args); return callback(...args); }); };
  const document = { body: new Element("body"), documentElement: new Element("html"), hidden: false, getElementById: get, createElement: tag => new Element(tag), createTextNode: value => { const text = new Element("#text"); text.textContent = value; return text; }, querySelectorAll: selector => selector === "[data-tab]" ? tabs : selector === "[data-inbox]" ? listTabs : selector === "button[data-music-tier]" ? musicTabs : [], addEventListener(name, callback) { addEvent(documentEvents, name, callback); } };
  const history = { state: null, pushState(value) { this.state = value; }, back() { this.state = null; } };
  const stores = new Map(["records", "music", "media", "settings"].map(name => [name, new Map()]));
  const PhoneStore = {
    failWrites: false,
    async get(name, id) { return structuredClone(stores.get(name).get(id)); },
    async all(name) { return [...stores.get(name).values()].map(value => structuredClone(value)); },
    async keys(name) { return [...stores.get(name).keys()]; },
    async remove(name, id) { if (this.failWrites) throw new Error("quota"); stores.get(name).delete(id); },
    async put(name, value) { if (this.failWrites) throw Object.assign(new Error("quota"), { name: "QuotaExceededError" }); stores.get(name).set(value.id, structuredClone(value)); },
    async putTrack(metadata, media) { if (this.failWrites) throw Object.assign(new Error("quota"), { name: "QuotaExceededError" }); stores.get("music").set(metadata.id, structuredClone(metadata)); stores.get("media").set(media.id, structuredClone(media)); },
    async replaceLibrary(value) { if (this.failWrites) throw new Error("quota"); const old = stores.get("records").get("library"); if (old) stores.get("records").set("previousImport", structuredClone({ ...old, id: "previousImport" })); stores.get("records").set("library", structuredClone(value)); }
  };
  const registration = { waiting: null, installing: null, updateCalls: 0, addEventListener(name, callback) { registrationEvents.set(name, callback); }, async update() { this.updateCalls++; if (this.updateError) throw this.updateError; if (this.onUpdate) await this.onUpdate(); } };
  const runtime = { URL, URLSearchParams, AbortController, TypeError, Request, document, history, navigator: { onLine: true, serviceWorker: { controller: {}, ready: Promise.resolve(registration), register: async (...args) => { registrations.push(args); return registration; }, addEventListener(name, callback) { workerEvents.set(name, callback); } } }, PhoneStore, Blob, structuredClone, localStorage: { getItem: key => saved.get(key) || null, setItem: (key, value) => saved.set(key, value) }, window: { setTimeout(fn, delay) { const id = nextTimer++; timers.set(id, { fn, delay }); return id; }, clearTimeout(id) { timers.delete(id); }, location: { href: "http://192.0.2.1:8899/CodexControlConsole/phone/index.html", reload() { reloads.push(true); } }, addEventListener(name, callback) { addEvent(windowEvents, name, callback); } }, async fetch(url, options) { mediaEvents.push(`fetch:${url}`); calls.push({ url, options }); const response = answers.shift(); assert.ok(response, `Unexpected fetch ${url}`); return typeof response === "function" ? response() : await response; } };
  const names = "state,taskSync,validatePlanSnapshot,applyPlanSnapshot,syncAddress,supportsTaskSync,updateSyncFallback,connectTaskSync,pollTaskSync,disconnectTaskSync,restoreTaskSync,validateImport,mergeLibrary,reviewImport,commitImport,backupLibrary,mutateLibrary,saveMusicTrack,downloadMusic,importMusicFiles,addLocalLyric,checkUpdate,setupWorker,maybeReloadUpdate,api,bootstrap,refresh,refreshDashboard,renderPlan,renderDevice,renderDocuments,renderInbox,openDocument,moveReader,closeReader,pathValue,appendLink,renderMarkdown,setFont,selectTab,loadMusic,musicTrackList,selectMusicTrack,playMusic,advanceMusic,parseMusicLyrics,syncMusicLyrics,stopMusicPlayback,clearMusic,musicAudioError,loadMusicLyrics,renderMusicTracks";
  assert.ok(source.includes("  void bootstrap();\n})();"), "test export insertion must match only bootstrap footer");
  // Exercise deferred sync explicitly in isolated tests; production stays offline by default.
  const testSource = syncEnabled ? source.replace("const TASK_SYNC_ENABLED = false;", "const TASK_SYNC_ENABLED = true;") : source;
  if (syncEnabled) assert.notEqual(testSource, source, "deferred sync tests must enable the source flag in memory");
  runInNewContext(testSource.replace("  void bootstrap();\n})();", `  globalThis.PHONE_TEST = {${names}};\n})();`), runtime);
  const api = runtime.PHONE_TEST;
  return { api, stores, PhoneStore, runtime, get, document, calls, answers, saved, history, tabs, listTabs, musicTabs, audio, mediaEvents, timers, documentEvents, windowEvents, workerEvents, registrationEvents, registration, registrations, reloads, respond(body, status = 200) { answers.push(result(body, status)); }, ready() { api.state.ready = true; api.state.library = api.validateImport(importFixture()); api.state.dashboard = api.state.library.dashboard; stores.get("records").set("library", structuredClone(api.state.library)); get("pairScreen").hidden = true; get("appScreen").hidden = false; api.renderDocuments(); }, all(root, tag) { const found = []; const visit = item => { if (item.tagName === tag.toUpperCase()) found.push(item); for (const child of item.children) visit(child); }; visit(root); return found; } };
}

function importFixture() {
  const data = { format: "codex-console-phone-data", schemaVersion: 1, exportedAt: "2026-10-01T10:00:00+08:00", dashboard: dashboard(), files: [] };
  for (const path of ["human.md", "reports/one.md", "reports/later.md", "reports/archive.md", "nodes.zh.md", "nodes.en.md"]) data.files.push({ path, name: path.split("/").at(-1), content: "# " + path + "\n\n**重点**与 <script>literal</script>", format: "markdown", modifiedAt: "2026-10-01T09:00:00+08:00" });
  return data;
}
const publicPlaylist = () => [{ path: "builtin/one.mp3", name: "Public one", type: "mp3", size: 9, source: "music/one.mp3", lyrics: true, lyricsLanguage: "zh", lyricsLanguages: [{ code: "zh", label: "Chinese", source: "music/one.zh.lrc" }, { code: "en", label: "English", source: "music/one.en.lrc" }] }];
const groupedPlaylist = () => [
  { name: "Third default", tier: undefined }, { name: "First B", tier: "first" }, { name: "Second B", tier: "second" }, { name: "First A", tier: "first" }, { name: "Second A", tier: "second" }, { name: "Third explicit", tier: "third" }
].map((track, index) => ({ ...track, path: `builtin/group-${index}.mp3`, type: "mp3", size: 9, source: `music/group-${index}.mp3` }));
const musicRows = h => h.all(h.get("musicTracks"), "button").filter(button => button.className === "music-track");
const snapshot = (hash = "a", computerId = "fixture-pc") => ({ format: "codex-console-plan-snapshot", schemaVersion: 1, hash: hash.repeat(64), updatedAt: "2026-10-01T12:00:00Z", computerId, plan: plan().plan });
const settle = () => new Promise(resolve => setTimeout(resolve, 0));
function workerHarness({ active = true, clients = [], installError = null } = {}) {
  const listeners = new Map(), deleted = [], claimed = [], skipped = [], precached = [], timers = new Map(); let nextTimer = 1;
  class Channel {
    constructor() {
      this.port1 = { onmessage: null, close() {} };
      this.port2 = { postMessage: data => this.port1.onmessage?.({ data }), close() {} };
    }
  }
  const self = { registration: { scope: "https://example.test/project/phone/", active: active ? {} : null }, clients: { async claim() { claimed.push(true); }, async matchAll() { return clients; } }, addEventListener: (name, fn) => listeners.set(name, fn), async skipWaiting() { skipped.push(true); } };
  const context = { self, URL, Headers, Request, Response, Blob, MessageChannel: Channel, importScripts() {}, PhoneStore: {}, setTimeout(fn, delay) { const id = nextTimer++; timers.set(id, { fn, delay }); return id; }, clearTimeout(id) { timers.delete(id); }, caches: { async open() { return { async addAll(requests) { precached.push(...requests); if (installError) throw installError; } }; }, async keys() { return ["codex-console-phone-shell-%2Fproject%2Fphone%2F-old-old", "unrelated-cache", "codex-console-phone-shell-%2Fother%2F-old-old"]; }, async delete(key) { deleted.push(key); } } };
  runInNewContext(swSource, context);
  return { listeners, deleted, claimed, skipped, precached, timers, async run(name) { let done; listeners.get(name)({ waitUntil(promise) { done = promise; } }); return done; } };
}
let count = 0;
async function test(name, run) { await run(); console.log(`PASS ${name}`); count += 1; }
await test("relative project installation has four tabs and no PC connection requirement", () => {
  assert.equal(manifest.start_url, "./index.html"); assert.equal(manifest.scope, "./");
  assert.deepEqual([...html.matchAll(/data-tab="([^"]+)"/g)].map(match => match[1]), ["tasks", "music", "device", "documents"]);
  assert.doesNotMatch(html, /pairCode|pairForm|offlineScreen|logoutButton/); assert.doesNotMatch(source, /clearPrivate|showOffline|showPair/);
  for (const match of source.matchAll(/\/api\/phone\/([^"']+)/g)) assert.ok(match[1].startsWith("plan-sync/"), "optional PC access must be limited to plan sync");
  for (const match of html.matchAll(/(?:src|href)="([^"]+)"/g)) assert.ok(!match[1].startsWith("/"), "project assets must remain relative");
  const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1])); for (const match of source.matchAll(/\bel\("([^"]+)"\)/g)) assert.ok(ids.has(match[1]), `Missing element ${match[1]}`);
  assert.deepEqual([...html.matchAll(/data-music-tier="([^"]*)"/g)].map(match => match[1]), ["", "first", "second", "third"]);
});
await test("JSON import validates registered content and rejects unsafe or incomplete packages", () => {
  const h = harness(); assert.equal(h.api.validateImport(importFixture()).files.length, 6);
  for (const mutate of [data => { data.schemaVersion = 99; }, data => { data.files[0].path = "../../secret.md"; }, data => { data.files[0].path = "unregistered.md"; }, data => { data.files.pop(); }, data => { data.dashboard.documents.inbox.entries[0].status = "cleared"; }, data => { data.dashboard.plan.plan.groups.pop(); }, data => { data.files[0].content = "x".repeat(2 * 1024 * 1024 + 1); }]) { const data = importFixture(); mutate(data); assert.throws(() => h.api.validateImport(data)); }
});
await test("import review writes nothing until the user confirms", async () => {
  const h = harness(); h.ready(); const before = JSON.stringify(h.stores.get("records").get("library")); await h.api.reviewImport({ size: 100, text: async () => JSON.stringify(importFixture()) });
  assert.equal(h.get("importReview").hidden, false); assert.equal(JSON.stringify(h.stores.get("records").get("library")), before); assert.match(h.get("importCounts").textContent, /4 项主要计划/);
});
await test("new imports preserve local task checks and reading states with a recoverable prior import", async () => {
  const h = harness(); h.ready(); h.api.state.library.taskDone = { "task-0": true }; h.api.state.library.reading = { "to-read": "later" }; h.api.state.pendingImport = h.api.validateImport(importFixture()); await h.api.commitImport();
  assert.equal(h.api.state.library.taskDone["task-0"], true); assert.equal(h.api.state.library.dashboard.documents.inbox.entries[0].status, "later"); assert.ok(h.stores.get("records").get("previousImport")); assert.match(h.get("settingsNotice").textContent, /已保留/);
});
await test("failed import preserves the previous phone library", async () => {
  const h = harness(); h.ready(); const before = JSON.stringify(h.api.state.library); h.PhoneStore.failWrites = true; h.api.state.pendingImport = h.api.validateImport(importFixture()); await h.api.commitImport(); assert.equal(JSON.stringify(h.api.state.library), before); assert.equal(h.get("settingsNotice").dataset.error, "true");
});
await test("import confirmation cannot race an in-progress restore or another import", async () => {
  const h = harness(); h.ready(); const before = JSON.stringify(h.api.state.library); h.api.state.pendingImport = h.api.validateImport(importFixture()); h.api.state.busy = true; await h.api.commitImport(); assert.equal(JSON.stringify(h.api.state.library), before); assert.equal(h.stores.get("records").has("previousImport"), false);
});
await test("rapid task changes and reading changes serialize without losing each other", async () => {
  const h = harness(); h.ready(); h.api.renderPlan(h.api.state.library.dashboard.plan); const checks = h.all(h.get("taskGroups"), "input"); checks[0].checked = true; checks[2].checked = true;
  await Promise.all([checks[0].listeners.get("change")(), checks[2].listeners.get("change")(), h.api.api("inbox/move", { id: "to-read", status: "archive" })]);
  const saved = h.stores.get("records").get("library"); assert.equal(saved.taskDone["task-0"], true); assert.equal(saved.taskDone["task-2"], true); assert.equal(saved.reading["to-read"], "archive"); assert.equal(h.calls.length, 0);
});
await test("document reading and safe Markdown run from local records without HTTP", async () => {
  const h = harness(); h.ready(); await h.api.openDocument("reports/one.md", { entryId: "to-read" }); assert.equal(h.calls.length, 0); assert.match(h.get("readerContent").textContent, /重点/); assert.equal(h.all(h.get("readerContent"), "script").length, 0);
  await h.api.moveReader("later"); assert.equal(h.stores.get("records").get("library").reading["to-read"], "later"); assert.equal(h.calls.length, 0);
});
await test("device memory is explicitly historical and never presented as current", () => {
  const h = harness(); h.ready(); h.api.renderDevice(h.api.state.dashboard.device); assert.match(h.get("memoryCard").textContent, /上次保存/); assert.match(html, /不是电脑当前状态/); assert.doesNotMatch(h.get("memoryCard").textContent, /当前记忆体/);
});
await test("public songs are listed without automatically downloading audio", async () => {
  const h = harness(); h.ready(); h.api.state.catalog = publicPlaylist(); await h.api.loadMusic(); assert.equal(h.calls.length, 0); assert.equal(h.audio.playCalls, 0); assert.equal(h.api.state.saved.size, 0);
  assert.equal(h.get("musicPlayer").hidden, true, "an empty player must not push the category list below the first screen");
  h.api.selectMusicTrack("builtin/one.mp3"); assert.equal(h.audio.playCalls, 0); assert.match(h.get("musicNotice").textContent, /还没有下载/);
});
await test("the original songs retain their tiers and desktop order", async () => {
  const defaults = JSON.parse(readFileSync(new URL("../release-defaults.json", import.meta.url), "utf8")).music;
  const h = harness(); h.ready(); h.api.state.catalog = defaults.order.map(name => ({ name: name.replace(/\.mp3$/, ""), path: `builtin/${name}`, source: `music/${name}`, type: "mp3", size: 9, tier: defaults.tiers[name] }));
  const before = JSON.stringify(h.api.state.catalog); await h.api.loadMusic();
  assert.deepEqual(h.get("musicTracks").children.filter(section => section.tagName === "SECTION").map(section => [section.dataset.musicTier, h.all(section, "button").filter(button => button.className === "music-track").length]), [["first", 3], ["second", 6], ["third", 7]]);
  assert.deepEqual(musicRows(h).slice(0, 3).map(button => h.all(button, "span").find(item => item.className === "music-track-name").textContent), ["Outrun", "Redline", "Liquid Roller"]);
  assert.equal(JSON.stringify(h.api.state.catalog), before); assert.equal(h.calls.length, 0);
});
await test("tier groups keep stable order and default only the phone display to third", async () => {
  const h = harness(); h.ready(); h.api.state.catalog = groupedPlaylist(); const before = JSON.stringify(h.api.state.catalog); await h.api.loadMusic();
  assert.deepEqual(musicRows(h).map(button => h.all(button, "span").find(item => item.className === "music-track-name").textContent), ["First B", "First A", "Second B", "Second A", "Third default", "Third explicit"]);
  assert.equal(h.all(h.get("musicTracks"), "button").length, 6, "song rows must not add individual download buttons");
  assert.equal(JSON.stringify(h.api.state.catalog), before); assert.equal(h.api.state.catalog[0].tier, undefined);
});
await test("tier filtering includes local songs without changing catalog order", async () => {
  const h = harness(); h.ready(); h.api.state.catalog = groupedPlaylist(); h.stores.get("music").set("local/one", { id: "local/one", name: "Second local B", tier: "second", type: "mp3" }); await h.api.loadMusic();
  const before = JSON.stringify(h.api.state.catalog);
  h.musicTabs[2].listeners.get("click")();
  assert.deepEqual(musicRows(h).map(button => h.all(button, "span").find(item => item.className === "music-track-name").textContent), ["Second B", "Second A", "Second local B"]);
  assert.doesNotMatch(h.get("musicTracks").textContent, /First B|Third default/); assert.equal(h.musicTabs[2].attributes["aria-pressed"], "true");
  h.musicTabs[0].listeners.get("click")(); assert.equal(musicRows(h).length, 7); assert.equal(JSON.stringify(h.api.state.catalog), before);
});
await test("one all-download click saves every missing tier and its lyrics despite active filters", async () => {
  const h = harness(); h.ready(); h.api.state.catalog = [...groupedPlaylist(), ...publicPlaylist()]; const alreadySaved = h.api.state.catalog[1]; h.stores.get("media").set(alreadySaved.path, { id: alreadySaved.path, blob: new Blob(["prior"]) }); await h.api.loadMusic();
  h.musicTabs[1].listeners.get("click")(); assert.equal(musicRows(h).length, 2);
  for (const track of h.api.state.catalog.filter(item => item.path !== alreadySaved.path)) { h.answers.push({ ok: true, blob: async () => new Blob(["audio"], { type: "audio/mpeg" }) }); for (const language of track.lyricsLanguages || []) h.answers.push({ ok: true, text: async () => `[00:01]${language.code}` }); }
  await h.get("musicDownloadAll").listeners.get("click")();
  assert.deepEqual([...h.stores.get("media").keys()].sort(), h.api.state.catalog.map(track => track.path).sort()); assert.equal(h.stores.get("music").get("builtin/one.mp3").offlineLyrics.length, 2);
  const audioRequests = h.calls.filter(call => call.url.endsWith(".mp3")); assert.equal(audioRequests.length, 6); assert.ok(audioRequests.every(call => !call.url.endsWith(alreadySaved.source))); assert.equal(h.answers.length, 0);
  assert.equal(h.api.state.music.tier, "first"); assert.equal(h.get("musicDownloadAll").hidden, true); assert.equal(h.audio.playCalls, 0);
});
await test("stopping all-download preserves completed songs and resumes only missing songs", async () => {
  const h = harness(); h.ready(); h.api.state.catalog = groupedPlaylist().slice(0, 2); await h.api.loadMusic(); const blocked = defer(), urls = [];
  h.runtime.fetch = async (url, options) => { urls.push(url); if (url.endsWith("group-1.mp3")) { blocked.resolve(); return new Promise((_, reject) => options.signal.addEventListener("abort", () => reject(Object.assign(new Error("stopped"), { name: "AbortError" })))); } return { ok: true, blob: async () => new Blob(["audio"]) }; };
  const downloading = h.get("musicDownloadAll").listeners.get("click")(); await blocked.promise; assert.equal(h.get("musicDownloadAll").disabled, true); assert.equal(h.get("musicDownloadStop").hidden, false);
  h.get("musicDownloadStop").listeners.get("click")(); await downloading;
  assert.deepEqual([...h.stores.get("media").keys()], ["builtin/group-0.mp3"]); assert.equal(h.get("musicDownloadAll").disabled, false); assert.equal(h.get("musicDownloadAll").hidden, false); assert.equal(h.get("musicDownloadStop").hidden, true);
  const resumed = []; h.runtime.fetch = async url => { resumed.push(url); return { ok: true, blob: async () => new Blob(["audio"]) }; }; await h.get("musicDownloadAll").listeners.get("click")();
  assert.equal(resumed.length, 1); assert.ok(resumed[0].endsWith("group-1.mp3")); assert.equal(h.stores.get("media").size, 2); assert.equal(h.get("musicDownloadAll").hidden, true);
});
await test("explicit save includes local translated lyrics and uses only relative public sources", async () => {
  const h = harness(); h.ready(); h.api.state.catalog = publicPlaylist(); await h.api.loadMusic(); h.answers.push({ ok: true, blob: async () => new Blob(["audio"], { type: "audio/mpeg" }) }, { ok: true, text: async () => "[00:01]中文" }, { ok: true, text: async () => "[00:01]English" }); await h.api.downloadMusic(["builtin/one.mp3"]);
  assert.equal(h.api.state.saved.has("builtin/one.mp3"), true); assert.equal(h.stores.get("music").get("builtin/one.mp3").offlineLyrics.length, 2); assert.ok(h.calls.every(call => call.url.startsWith("http://192.0.2.1:8899/CodexControlConsole/phone/music/")));
  assert.equal(h.get("musicDownloadAll").hidden, true);
});
await test("saved music starts synchronously through the local SW route, never PC or network audio", async () => {
  const h = harness(); h.ready(); h.api.state.catalog = publicPlaylist(); h.stores.get("media").set("builtin/one.mp3", { id: "builtin/one.mp3", blob: new Blob(["audio"]) }); h.stores.get("music").set("builtin/one.mp3", { id: "builtin/one.mp3", offlineLyrics: [], lyrics: false }); await h.api.loadMusic();
  h.api.selectMusicTrack("builtin/one.mp3"); assert.equal(h.audio.playCalls, 1); assert.equal(h.audio.src, "http://192.0.2.1:8899/CodexControlConsole/phone/audio/builtin%2Fone.mp3"); assert.equal(h.calls.length, 0);
  assert.equal(h.get("musicPlayer").hidden, false);
  h.api.selectTab("tasks"); assert.equal(h.audio.paused, false); assert.equal(h.api.state.music.selected.path, "builtin/one.mp3");
});
await test("local audio and matching translated lyrics import without any upload", async () => {
  const h = harness(); h.ready(); const audio = new Blob(["local audio"], { type: "audio/wav" }); Object.defineProperty(audio, "name", { value: "song.wav" }); const lyric = new Blob(["[00:01]English"], { type: "text/plain" }); Object.defineProperty(lyric, "name", { value: "song.en.lrc" }); await h.api.importMusicFiles([audio, lyric]);
  assert.equal(h.stores.get("media").size, 1); const track = [...h.stores.get("music").values()][0]; assert.equal(track.offlineLyrics[0].code, "en"); assert.equal(h.calls.length, 0);
});
await test("quota failure never reports an unsaved audio blob as offline-ready", async () => {
  const h = harness(); h.ready(); h.PhoneStore.failWrites = true; const audio = new Blob(["audio"]); Object.defineProperty(audio, "name", { value: "song.wav" }); await h.api.importMusicFiles([audio]); assert.equal(h.stores.get("media").size, 0); assert.equal(h.api.state.saved.size, 0);
});
await test("failed update checks preserve imported data and active music", async () => {
  const h = harness(); h.ready(); const before = JSON.stringify(h.api.state.library); h.audio.paused = false; h.answers.push(Promise.reject(new TypeError("offline"))); await h.api.checkUpdate(); assert.equal(h.audio.paused, false); assert.equal(JSON.stringify(h.api.state.library), before); assert.match(h.get("updateNotice").textContent, /继续使用/);
});
await test("online startup checks for a fresh shell and reloads once after the old controller changes", async () => {
  const h = harness(); h.ready(); const before = JSON.stringify(h.api.state.library), applied = [];
  h.stores.get("media").set("saved-song", { id: "saved-song", blob: new Blob(["original audio"]) });
  h.registration.waiting = { postMessage(message) { applied.push(message); } };
  h.respond({ tracks: [] }); h.respond({ version: "99.0.0", buildId: "a".repeat(16) }); await h.api.bootstrap(); await settle();
  assert.ok(h.calls.some(call => call.url === "./version.json" && call.options.cache === "no-store")); assert.ok(h.registration.updateCalls > 0);
  assert.equal(h.registrations[0][1].updateViaCache, "none"); assert.ok(applied.some(message => message.type === "APPLY_UPDATE"));
  h.runtime.navigator.serviceWorker.controller = {}; h.workerEvents.get("controllerchange")(); await settle();
  h.workerEvents.get("controllerchange")(); await settle(); assert.equal(h.reloads.length, 1);
  assert.equal(JSON.stringify(h.api.state.library), before); assert.equal(await h.stores.get("media").get("saved-song").blob.text(), "original audio");
});
await test("the first offline controller installation does not unnecessarily reload the app", async () => {
  const h = harness(); h.ready(); h.runtime.navigator.serviceWorker.controller = null;
  h.respond({ version: "__CONSOLE_PHONE_VERSION__", buildId: "__CONSOLE_PHONE_BUILD__" }); await h.api.setupWorker(); await settle();
  h.runtime.navigator.serviceWorker.controller = {}; h.workerEvents.get("controllerchange")(); await settle();
  assert.equal(h.reloads.length, 0); assert.equal(h.audio.pauseCalls, 0);
});
await test("updated playing pages acknowledge migration immediately and defer their own reload until paused", async () => {
  const h = harness(); h.ready(); h.api.state.catalog = publicPlaylist();
  h.stores.get("media").set("builtin/one.mp3", { id: "builtin/one.mp3", blob: new Blob(["saved music"]) });
  h.stores.get("music").set("builtin/one.mp3", { id: "builtin/one.mp3", offlineLyrics: [], lyrics: false });
  await h.api.loadMusic(); h.api.selectMusicTrack("builtin/one.mp3"); const before = JSON.stringify(h.api.state.library), pauses = h.audio.pauseCalls;
  h.respond({ version: "__CONSOLE_PHONE_VERSION__", buildId: "__CONSOLE_PHONE_BUILD__" }); await h.api.setupWorker(); await settle();
  h.runtime.navigator.serviceWorker.controller = {}; h.workerEvents.get("controllerchange")(); const acknowledgements = [];
  h.workerEvents.get("message")({ source: h.runtime.navigator.serviceWorker.controller, data: { type: "CONSOLE_SHELL_UPDATED", version: "99.0.0", buildId: "a".repeat(16) }, ports: [{ postMessage(value) { acknowledgements.push(value); } }] });
  assert.equal(acknowledgements[0]?.handled, true); await settle(); assert.equal(h.reloads.length, 0); assert.equal(h.audio.paused, false); assert.equal(h.audio.pauseCalls, pauses);
  h.audio.paused = true; h.audio.listeners.get("pause")?.(); await settle(); assert.equal(h.reloads.length, 1);
  assert.equal(JSON.stringify(h.api.state.library), before); assert.equal(await h.stores.get("media").get("builtin/one.mp3").blob.text(), "saved music");
});
await test("automatic update waits for an in-progress library save before reloading", async () => {
  const h = harness(); h.ready(); const pending = defer(), originalPut = h.PhoneStore.put.bind(h.PhoneStore);
  h.PhoneStore.put = async (name, value) => { if (name === "records") await pending.promise; await originalPut(name, value); };
  const saved = h.api.mutateLibrary(library => { library.reading = { "to-read": "later" }; }); h.api.state.updatePending = true;
  const reload = h.api.maybeReloadUpdate(); await settle(); assert.equal(h.reloads.length, 0); pending.resolve(); await saved; await reload;
  assert.equal(h.stores.get("records").get("library").reading["to-read"], "later"); assert.equal(h.reloads.length, 1);
});
await test("automatic update also waits for a second library save queued during the first save", async () => {
  const h = harness(); h.ready(); const firstGate = defer(), secondGate = defer(), originalPut = h.PhoneStore.put.bind(h.PhoneStore); let writes = 0;
  h.PhoneStore.put = async (name, value) => { if (name === "records") await (++writes === 1 ? firstGate.promise : secondGate.promise); await originalPut(name, value); };
  const first = h.api.mutateLibrary(library => { library.reading = { "to-read": "later" }; }); await settle();
  h.api.state.updatePending = true; const reload = h.api.maybeReloadUpdate();
  const second = h.api.mutateLibrary(library => { library.taskDone = { "task-0": true }; });
  firstGate.resolve(); await first; await settle(); assert.equal(writes, 2); assert.equal(h.reloads.length, 0);
  assert.equal(h.stores.get("records").get("library").reading["to-read"], "later"); assert.equal(h.stores.get("records").get("library").taskDone["task-0"], undefined);
  secondGate.resolve(); await second; await reload; const saved = h.stores.get("records").get("library");
  assert.equal(saved.reading["to-read"], "later"); assert.equal(saved.taskDone["task-0"], true); assert.equal(h.reloads.length, 1);
});
await test("slow import reads defer shell reload through review and recover after cancel confirm or failure", async () => {
  for (const action of ["cancel", "confirm", "fail"]) {
    const h = harness(); h.ready(); const pending = defer(), before = JSON.stringify(h.stores.get("records").get("library"));
    const review = h.api.reviewImport({ size: 100, text: () => pending.promise }); h.api.state.updatePending = true;
    await h.api.maybeReloadUpdate(); await settle(); assert.equal(h.reloads.length, 0, `reload while ${action} import is still reading`);
    if (action === "fail") {
      pending.reject(new Error("file read failed")); await assert.rejects(review, /file read failed/); await settle();
      assert.equal(h.reloads.length, 1); assert.equal(JSON.stringify(h.stores.get("records").get("library")), before); continue;
    }
    pending.resolve(JSON.stringify(snapshot("b"))); await review; await settle();
    assert.equal(h.get("importReview").hidden, false); assert.equal(h.reloads.length, 0); assert.equal(JSON.stringify(h.stores.get("records").get("library")), before);
    if (action === "cancel") h.get("importCancel").listeners.get("click")(); else await h.api.commitImport();
    await settle(); assert.equal(h.reloads.length, 1);
    if (action === "cancel") assert.equal(JSON.stringify(h.stores.get("records").get("library")), before);
    else assert.equal(h.stores.get("records").get("library").planSync.hash, "b".repeat(64));
  }
});
await test("offline automatic startup keeps saved plans documents and music without interrupting playback", async () => {
  const h = harness(); h.ready(); await h.api.applyPlanSnapshot(snapshot()); h.audio.paused = false;
  h.stores.get("media").set("saved-song", { id: "saved-song", blob: new Blob(["offline music"]) }); const before = JSON.stringify(h.stores.get("records").get("library"));
  h.answers.push(() => { throw new TypeError("offline catalog"); }, () => { throw new TypeError("offline update"); }); await h.api.bootstrap(); await settle();
  assert.equal(h.reloads.length, 0); assert.equal(h.audio.paused, false); assert.equal(h.audio.pauseCalls, 0); assert.equal(JSON.stringify(h.api.state.library), before);
  assert.equal(h.api.state.library.planSync.readonly, true); assert.equal(h.api.state.library.files.length, 6); assert.equal(await h.stores.get("media").get("saved-song").blob.text(), "offline music");
});
await test("shell cache is build-specific and activation never removes user data", async () => {
  assert.match(swSource, /VERSION \+ "-" \+ BUILD/); assert.match(swSource, /encodeURIComponent\(new URL\(self.registration.scope\).pathname\)/); assert.doesNotMatch(swSource, /deleteDatabase|\.clear\(/); assert.match(storeSource, /db.transaction\(\["music", "media"\], "readwrite"\)/);
  const h = workerHarness(); await h.run("activate"); assert.deepEqual(h.deleted, ["codex-console-phone-shell-%2Fproject%2Fphone%2F-old-old"]); assert.equal(h.claimed.length, 1);
});
await test("a complete fresh shell activates automatically while failed precaching keeps the old worker", async () => {
  const complete = workerHarness(); await complete.run("install"); assert.equal(complete.skipped.length, 1); assert.ok(complete.precached.length > 0);
  assert.ok(complete.precached.every(request => request.cache === "reload"), "new shell installation must fetch fresh responses rather than old HTTP cache entries");
  const incomplete = workerHarness({ installError: new TypeError("offline midway") }); await assert.rejects(incomplete.run("install"), /offline midway/); assert.equal(incomplete.skipped.length, 0);
});
await test("legacy pages without a handler navigate once without blocking worker activation", async () => {
  const messages = [], navigated = [], unrelated = [];
  const legacy = { type: "window", url: "https://example.test/project/phone/index.html", postMessage(message) { messages.push(message); }, navigate(url) { navigated.push(url); return new Promise(() => {}); } };
  const other = { type: "window", url: "https://example.test/other/index.html", postMessage() { unrelated.push("message"); }, navigate() { unrelated.push("navigate"); } };
  const h = workerHarness({ clients: [legacy, other] }), activated = h.run("activate"); await settle();
  for (const timer of [...h.timers.values()]) timer.fn();
  let deadline; try { await Promise.race([activated, new Promise((_, reject) => { deadline = setTimeout(() => reject(new Error("activation waited for client navigation")), 500); })]); } finally { clearTimeout(deadline); }
  assert.deepEqual(navigated, [legacy.url]); assert.equal(messages.length, 1); assert.equal(messages[0].type, "CONSOLE_SHELL_UPDATED"); assert.deepEqual(unrelated, []);
});
await test("an acknowledged updated page is never forced to navigate by the migration bridge", async () => {
  const messages = [], navigated = [];
  const current = { type: "window", url: "https://example.test/project/phone/", postMessage(message, ports) { messages.push(message); ports[0].postMessage({ handled: true }); }, navigate(url) { navigated.push(url); } };
  const h = workerHarness({ clients: [current] }); await h.run("activate"); assert.equal(messages.length, 1); assert.deepEqual(navigated, []);
});
await test("local SW audio returns full HEAD and all Safari single byte ranges", async () => {
  const context = { self: { registration: { scope: "https://example.test/project/phone/", active: {} }, addEventListener() {} }, URL, Headers, Response, Blob, importScripts() {}, PhoneStore: { async get(_, id) { return id === "test" ? { blob: new Blob(["0123456789"], { type: "audio/wav" }) } : null; } } };
  runInNewContext(swSource + "\nglobalThis.SW_TEST = {localAudio,rangeParts};", context); const api = context.SW_TEST;
  for (const [range, expected, status] of [[null, "0123456789", 200], ["bytes=0-1", "01", 206], ["bytes=7-", "789", 206], ["bytes=-2", "89", 206], ["bytes=9-99", "9", 206]]) { const response = await api.localAudio(new Request("https://example.test/project/phone/audio/test", { headers: range ? { Range: range } : {} }), "test"); assert.equal(response.status, status); assert.equal(await response.text(), expected); }
  const head = await api.localAudio(new Request("https://example.test/project/phone/audio/test", { method: "HEAD" }), "test"); assert.equal(head.headers.get("Content-Length"), "10"); assert.equal(await head.text(), "");
  const bad = await api.localAudio(new Request("https://example.test/project/phone/audio/test", { headers: { Range: "bytes=99-" } }), "test"); assert.equal(bad.status, 416); assert.equal(bad.headers.get("Content-Range"), "bytes */10"); assert.equal((await api.localAudio(new Request("https://example.test/project/phone/audio/missing"), "missing")).status, 404);
});
const enableSync = h => { h.runtime.Request = class { constructor(_, options) { this.targetAddressSpace = options.targetAddressSpace; } }; h.get("syncAddress").value = "http://192.168.1.10:8899/"; h.get("syncCode").value = "123456"; };
const savedSync = () => ({ address: "http://192.168.1.10:8899", token: "x".repeat(43), computerId: "fixture-pc", expiresAt: Date.now() + 3600000 });
await test("task snapshots validate bounded groups and never accept malformed private records", () => {
  const h = harness(); assert.equal(h.api.validatePlanSnapshot(snapshot()).plan.groups.length, 4);
  const six = snapshot(); six.plan.groups.push({ id: "extra-1", title: "示例五", items: [] }, { id: "extra-2", title: "示例六", items: [] }); assert.equal(h.api.validatePlanSnapshot(six).plan.groups.length, 6);
  for (const mutate of [s => { s.schemaVersion = 2; }, s => { s.hash = "invalid"; }, s => { s.computerId = "../../secret"; }, s => { s.updatedAt = "invalid"; }, s => { s.plan.groups[1].id = s.plan.groups[0].id; }, s => { s.plan.groups[1].items[0].id = s.plan.groups[0].items[0].id; }, s => { s.plan.groups[0].items[0].done = "yes"; }, s => { s.plan.groups[0].items[0].text = "x".repeat(501); }]) { const s = snapshot(); mutate(s); assert.throws(() => h.api.validatePlanSnapshot(s)); }
});
await test("computer snapshots override checks while preserving phone documents music reading and a local check backup", async () => {
  const h = harness(); h.ready(); h.api.state.library.taskDone = { "task-0": true }; h.api.state.library.reading = { "to-read": "later" }; h.stores.get("media").set("music", { id: "music", blob: new Blob(["saved"]) }); h.stores.get("music").set("music", { id: "music", name: "Saved" });
  h.api.renderPlan(h.api.state.library.dashboard.plan); h.get("taskGroups").children[0].open = true; const files = JSON.stringify(h.api.state.library.files), device = JSON.stringify(h.api.state.library.dashboard.device);
  await h.api.applyPlanSnapshot(snapshot()); const checks = h.all(h.get("taskGroups"), "input"); assert.equal(checks[0].checked, false); assert.ok(checks.every(input => input.disabled)); assert.equal(h.get("taskGroups").children[0].open, true);
  assert.equal(JSON.stringify(h.api.state.library.files), files); assert.equal(JSON.stringify(h.api.state.library.dashboard.device), device); assert.equal(h.api.state.library.reading["to-read"], "later"); assert.equal(h.api.state.library.localTaskBackup.taskDone["task-0"], true); assert.equal(h.stores.get("media").size, 1); assert.equal(h.stores.get("music").size, 1);
  const updated = snapshot("b"); updated.plan.groups[0].items[0].done = true; updated.plan.groups[0].items.push({ id: "new-task", text: "新细项", done: false }); await h.api.applyPlanSnapshot(updated); assert.equal(h.all(h.get("taskGroups"), "input")[0].checked, true); assert.match(h.get("taskGroups").textContent, /新细项/); assert.equal(h.api.state.library.localTaskBackup.taskDone["task-0"], true);
  assert.equal(await h.api.applyPlanSnapshot(updated), false); assert.equal(h.calls.length, 0);
});
await test("snapshot import review writes nothing and confirmation changes only tasks", async () => {
  const h = harness(); h.ready(); const before = JSON.stringify(h.api.state.library), docs = JSON.stringify(h.api.state.library.dashboard.documents);
  await h.api.reviewImport({ size: 100, text: async () => JSON.stringify(snapshot()) }); assert.equal(JSON.stringify(h.api.state.library), before); assert.equal(h.api.state.pendingImport, null); assert.match(h.get("importReviewHelp").textContent, /只更新任务/);
  await h.api.commitImport(); assert.equal(JSON.stringify(h.api.state.library.dashboard.documents), docs); assert.equal(h.api.state.library.planSync.hash, "a".repeat(64)); assert.equal(h.get("importReview").hidden, true);
});
await test("phone backups restore synced public groups as readonly without exporting connection credentials", async () => {
  const h = harness(); h.ready(); h.api.state.library.taskDone = { "task-0": true }; const six = snapshot(); six.plan.groups.push({ id: "extra-1", title: "五", items: [] }, { id: "extra-2", title: "六", items: [] }); await h.api.applyPlanSnapshot(six); h.stores.get("settings").set("taskSync", { id: "taskSync", ...savedSync() });
  let blob; h.runtime.URL = class extends URL { static createObjectURL(value) { blob = value; return "blob:fixture"; } static revokeObjectURL() {} }; await h.api.backupLibrary(); const raw = await blob.text(), backup = JSON.parse(raw); assert.equal(backup.format, "codex-console-phone-backup"); assert.equal(backup.phoneState.planSnapshot.computerId, "fixture-pc"); assert.equal(backup.phoneState.localTaskBackup.taskDone["task-0"], true); assert.doesNotMatch(raw, /192\.168\.1\.10|xxxxxxxxxxxxxxxx|"token"|"expiresAt"/);
  const restored = h.api.validateImport(backup); assert.equal(restored.dashboard.plan.plan.groups.length, 6); assert.equal(restored.planSync.readonly, true); h.api.state.library = restored; h.api.renderPlan(restored.dashboard.plan); assert.ok(h.all(h.get("taskGroups"), "input").every(input => input.disabled));
  const ordinary = structuredClone(backup); ordinary.format = "codex-console-phone-data"; assert.throws(() => h.api.validateImport(ordinary), /四项/);
  const mismatched = structuredClone(backup); mismatched.dashboard.plan.plan.groups[0].items[0].done = true; assert.throws(() => h.api.validateImport(mismatched), /不一致/);
  const malformed = structuredClone(backup); malformed.phoneState.planSnapshot.hash = "bad"; assert.throws(() => h.api.validateImport(malformed));
});
await test("Safari without LNA gets a safe top-level real-time link without any PC fetch", async () => {
  const h = harness({ syncEnabled: true }); h.ready(); h.get("syncAddress").value = "http://192.168.1.10:8899/"; h.get("syncCode").value = "123456"; const before = JSON.stringify(h.api.state.library); await h.api.connectTaskSync();
  assert.equal(h.calls.length, 0); assert.equal(h.get("syncFallback").href, "http://192.168.1.10:8899/mobile.html"); assert.match(h.get("syncNotice").textContent, /不支持/); assert.equal(JSON.stringify(h.api.state.library), before); assert.equal(h.get("syncCode").value, "");
  for (const unsafe of ["https://example.com/", "http://example.com/", "http://127.0.0.1:8899/", "http://192.168.1.10:8899/other", "http://user:secret@192.168.1.10:8899/", "http://192.168.1.10:8899/?token=x"]) assert.throws(() => h.api.syncAddress(unsafe));
});
await test("supported pairing stores tokens locally and fetches only scoped read-only task APIs", async () => {
  const h = harness({ syncEnabled: true }); h.ready(); enableSync(h); h.respond({ token: "x".repeat(43), computerId: "fixture-pc", expiresIn: 28800 }); h.respond(snapshot()); await h.api.connectTaskSync();
  assert.deepEqual(h.calls.map(call => call.url), ["http://192.168.1.10:8899/api/phone/plan-sync/pair", "http://192.168.1.10:8899/api/phone/plan-sync/plan"]);
  for (const { options } of h.calls) { assert.equal(options.targetAddressSpace, "local"); assert.equal(options.credentials, "omit"); assert.equal(options.mode, "cors"); assert.equal(options.cache, "no-store"); assert.equal(options.redirect, "error"); assert.equal(options.headers["X-Codex-Phone"], "1"); }
  assert.equal(h.calls[1].options.headers.Authorization, "Bearer " + "x".repeat(43)); assert.deepEqual(JSON.parse(h.calls[0].options.body), { code: "123456" }); assert.equal(h.stores.get("settings").get("taskSync").token, "x".repeat(43)); assert.equal(h.api.taskSync.connected, true); assert.ok([...h.timers.values()].some(timer => timer.delay === 5000));
});
await test("a late old PC response cannot replace a newly selected source", async () => {
  const h = harness({ syncEnabled: true }); h.ready(); h.api.taskSync.config = savedSync(); const pending = defer(); h.answers.push(pending.promise); const poll = h.api.pollTaskSync(); await h.api.disconnectTaskSync(false); const next = snapshot("c", "next-pc"); await h.api.applyPlanSnapshot(next); pending.resolve(result(snapshot())); await poll;
  assert.equal(h.api.state.library.planSync.computerId, "next-pc"); assert.equal(h.api.taskSync.connected, false); assert.equal(h.api.taskSync.timer, null);
});
await test("disconnect during a pending task write restores the prior phone cache before another source can write", async () => {
  const h = harness({ syncEnabled: true }); h.ready(); const before = JSON.stringify(h.stores.get("records").get("library")), pending = defer(), originalPut = h.PhoneStore.put.bind(h.PhoneStore);
  h.PhoneStore.put = async (name, value) => { await originalPut(name, value); if (name === "records" && value.planSync?.hash === "a".repeat(64)) await pending.promise; };
  const update = h.api.applyPlanSnapshot(snapshot(), h.api.taskSync.generation); await new Promise(resolve => setTimeout(resolve, 0)); await h.api.disconnectTaskSync(false); pending.resolve(); assert.equal(await update, false); assert.equal(JSON.stringify(h.stores.get("records").get("library")), before); assert.equal(JSON.stringify(h.api.state.library), before);
  await h.api.applyPlanSnapshot(snapshot("b", "new-pc")); assert.equal(h.stores.get("records").get("library").planSync.computerId, "new-pc");
});
await test("offline and expired sync retain all data and expiry stops polling without losing cached tasks", async () => {
  const h = harness({ syncEnabled: true }); h.ready(); await h.api.applyPlanSnapshot(snapshot()); h.api.taskSync.config = savedSync(); const before = JSON.stringify(h.api.state.library); h.answers.push(Promise.reject(new TypeError("offline"))); await h.api.pollTaskSync(); assert.equal(JSON.stringify(h.api.state.library), before); assert.match(h.get("syncNotice").textContent, /已保留/);
  h.api.taskSync.config.expiresAt = Date.now() - 1; await h.api.pollTaskSync(); assert.equal(h.api.taskSync.config.token, undefined); assert.equal(h.api.taskSync.timer, null); assert.match(h.get("syncNotice").textContent, /过期/); assert.equal(JSON.stringify(h.api.state.library), before);
});
await test("background suspends polling and returning foreground refreshes immediately", async () => {
  const h = harness({ syncEnabled: true }); h.ready(); h.api.taskSync.config = savedSync(); h.document.hidden = true; await h.api.pollTaskSync(); assert.equal(h.calls.length, 0); h.documentEvents.get("visibilitychange")(); assert.equal(h.api.taskSync.timer, null);
  h.respond({ version: "__CONSOLE_PHONE_VERSION__", buildId: "__CONSOLE_PHONE_BUILD__" }); h.respond(snapshot()); h.document.hidden = false; h.documentEvents.get("visibilitychange")(); await new Promise(resolve => setTimeout(resolve, 0)); assert.equal(h.calls.filter(call => call.url.includes("/api/phone/")).length, 1); assert.equal(h.api.taskSync.connected, true);
});
await test("default offline boot refresh and foreground events ignore old PC tokens without losing saved content", async () => {
  const h = harness(); h.ready(); enableSync(h); await h.api.applyPlanSnapshot(snapshot());
  h.stores.get("media").set("saved-song", { id: "saved-song", blob: new Blob(["original audio"]) });
  h.stores.get("music").set("saved-song", { id: "saved-song", name: "Saved song", offlineLyrics: [{ code: "en", content: "[00:01]Saved lyrics" }] });
  const oldConnection = { id: "taskSync", ...savedSync() }; h.stores.get("settings").set("taskSync", structuredClone(oldConnection));
  const before = JSON.stringify(h.stores.get("records").get("library")); h.respond({ tracks: [] }); h.respond({ version: "__CONSOLE_PHONE_VERSION__", buildId: "__CONSOLE_PHONE_BUILD__" });
  await h.api.bootstrap(); await new Promise(resolve => setTimeout(resolve, 0));
  // A stale in-memory config must remain harmless too, including direct dormant entry calls.
  h.api.taskSync.config = savedSync(); await h.api.refresh(); await h.api.restoreTaskSync(); await h.api.connectTaskSync(); await h.api.pollTaskSync();
  h.windowEvents.get("online")?.(); h.document.hidden = true; h.documentEvents.get("visibilitychange")?.();
  h.document.hidden = false; h.documentEvents.get("visibilitychange")?.(); await new Promise(resolve => setTimeout(resolve, 0));
  assert.ok(h.calls.some(call => call.url === "./version.json")); assert.ok(h.calls.every(call => ["./music-catalog.json", "./version.json"].includes(call.url)), "offline viewing may check the public app version but must not contact a PC"); assert.equal(h.api.taskSync.timer, null);
  assert.equal(JSON.stringify(h.stores.get("records").get("library")), before); assert.equal(JSON.stringify(h.api.state.library), before);
  assert.deepEqual(h.stores.get("settings").get("taskSync"), oldConnection); assert.equal(await h.stores.get("media").get("saved-song").blob.text(), "original audio");
  assert.equal(h.stores.get("music").get("saved-song").offlineLyrics[0].content, "[00:01]Saved lyrics"); assert.equal(h.api.state.library.planSync.readonly, true);
  assert.ok(h.all(h.get("taskGroups"), "input").every(input => input.disabled)); assert.equal(h.api.state.library.files.length, 6);
});
console.log(`PASS offline phone UI ${count} checks`);
