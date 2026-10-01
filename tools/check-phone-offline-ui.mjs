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
function harness() {
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
  const nodes = new Map(), calls = [], answers = [], saved = new Map();
  const get = id => { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); };
  const audio = get("musicAudio"); audio.paused = true; audio.currentTime = 0; audio.duration = NaN; audio.src = ""; audio.playCalls = 0; audio.pauseCalls = 0; audio.loadCalls = 0; const mediaEvents = [];
  audio.pause = () => { audio.paused = true; audio.pauseCalls++; mediaEvents.push("pause"); };
  audio.load = () => { audio.loadCalls++; audio.duration = NaN; audio.currentTime = 0; mediaEvents.push("load"); };
  audio.play = () => { audio.playCalls++; mediaEvents.push("play"); if (audio.playError) return Promise.reject(audio.playError); audio.paused = false; return Promise.resolve(); };
  const tabs = ["tasks", "music", "device", "documents"].map(tab => { const button = new Element("button"); button.dataset.tab = tab; return button; });
  const listTabs = ["inbox", "later", "archive"].map(tab => { const button = new Element("button"); button.dataset.inbox = tab; return button; });
  const document = { body: new Element("body"), documentElement: new Element("html"), hidden: false, getElementById: get, createElement: tag => new Element(tag), createTextNode: value => { const text = new Element("#text"); text.textContent = value; return text; }, querySelectorAll: selector => selector === "[data-tab]" ? tabs : selector === "[data-inbox]" ? listTabs : [], addEventListener() {} };
  const history = { state: null, pushState(value) { this.state = value; }, back() { this.state = null; } };
  const stores = new Map(["records", "music", "media", "settings"].map(name => [name, new Map()]));
  const PhoneStore = {
    failWrites: false,
    async get(name, id) { return structuredClone(stores.get(name).get(id)); },
    async all(name) { return [...stores.get(name).values()].map(value => structuredClone(value)); },
    async keys(name) { return [...stores.get(name).keys()]; },
    async put(name, value) { if (this.failWrites) throw Object.assign(new Error("quota"), { name: "QuotaExceededError" }); stores.get(name).set(value.id, structuredClone(value)); },
    async putTrack(metadata, media) { if (this.failWrites) throw Object.assign(new Error("quota"), { name: "QuotaExceededError" }); stores.get("music").set(metadata.id, structuredClone(metadata)); stores.get("media").set(media.id, structuredClone(media)); },
    async replaceLibrary(value) { if (this.failWrites) throw new Error("quota"); const old = stores.get("records").get("library"); if (old) stores.get("records").set("previousImport", structuredClone({ ...old, id: "previousImport" })); stores.get("records").set("library", structuredClone(value)); }
  };
  const runtime = { URL, URLSearchParams, AbortController, TypeError, document, history, navigator: { serviceWorker: { controller: {}, ready: Promise.resolve({}), register: async () => ({ waiting: null, addEventListener() {}, async update() {} }), addEventListener() {} } }, PhoneStore, Blob, structuredClone, localStorage: { getItem: key => saved.get(key) || null, setItem: (key, value) => saved.set(key, value) }, window: { setTimeout, clearTimeout, location: { href: "http://192.0.2.1:8899/CodexControlConsole/phone/index.html" }, addEventListener() {} }, async fetch(url, options) { mediaEvents.push(`fetch:${url}`); calls.push({ url, options }); const response = answers.shift(); assert.ok(response, `Unexpected fetch ${url}`); return typeof response === "function" ? response() : await response; } };
  const names = "state,validateImport,mergeLibrary,reviewImport,commitImport,mutateLibrary,saveMusicTrack,downloadMusic,importMusicFiles,addLocalLyric,checkUpdate,api,bootstrap,refreshDashboard,renderPlan,renderDevice,renderDocuments,renderInbox,openDocument,moveReader,closeReader,pathValue,appendLink,renderMarkdown,setFont,selectTab,loadMusic,musicTrackList,selectMusicTrack,playMusic,advanceMusic,parseMusicLyrics,syncMusicLyrics,stopMusicPlayback,clearMusic,musicAudioError,loadMusicLyrics,renderMusicTracks";
  assert.ok(source.includes("  void bootstrap();\n})();"), "test export insertion must match only bootstrap footer");
  runInNewContext(source.replace("  void bootstrap();\n})();", `  globalThis.PHONE_TEST = {${names}};\n})();`), runtime);
  const api = runtime.PHONE_TEST;
  return { api, stores, PhoneStore, runtime, get, document, calls, answers, saved, history, tabs, listTabs, audio, mediaEvents, respond(body, status = 200) { answers.push(result(body, status)); }, ready() { api.state.ready = true; api.state.library = api.validateImport(importFixture()); api.state.dashboard = api.state.library.dashboard; stores.get("records").set("library", structuredClone(api.state.library)); get("pairScreen").hidden = true; get("appScreen").hidden = false; api.renderDocuments(); }, all(root, tag) { const found = []; const visit = item => { if (item.tagName === tag.toUpperCase()) found.push(item); for (const child of item.children) visit(child); }; visit(root); return found; } };
}

function importFixture() {
  const data = { format: "codex-console-phone-data", schemaVersion: 1, exportedAt: "2026-10-01T10:00:00+08:00", dashboard: dashboard(), files: [] };
  for (const path of ["human.md", "reports/one.md", "reports/later.md", "reports/archive.md", "nodes.zh.md", "nodes.en.md"]) data.files.push({ path, name: path.split("/").at(-1), content: "# " + path + "\n\n**重点**与 <script>literal</script>", format: "markdown", modifiedAt: "2026-10-01T09:00:00+08:00" });
  return data;
}
const publicPlaylist = () => [{ path: "builtin/one.mp3", name: "Public one", type: "mp3", size: 9, source: "music/one.mp3", lyrics: true, lyricsLanguage: "zh", lyricsLanguages: [{ code: "zh", label: "Chinese", source: "music/one.zh.lrc" }, { code: "en", label: "English", source: "music/one.en.lrc" }] }];
let count = 0;
async function test(name, run) { await run(); console.log(`PASS ${name}`); count += 1; }
await test("relative project installation has four tabs and no PC connection requirement", () => {
  assert.equal(manifest.start_url, "./index.html"); assert.equal(manifest.scope, "./");
  assert.deepEqual([...html.matchAll(/data-tab="([^"]+)"/g)].map(match => match[1]), ["tasks", "music", "device", "documents"]);
  assert.doesNotMatch(html, /pairCode|pairForm|offlineScreen|logoutButton/); assert.doesNotMatch(source, /\/api\/phone|clearPrivate|showOffline|showPair/);
  for (const match of html.matchAll(/(?:src|href)="([^"]+)"/g)) assert.ok(!match[1].startsWith("/"), "project assets must remain relative");
  const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1])); for (const match of source.matchAll(/\bel\("([^"]+)"\)/g)) assert.ok(ids.has(match[1]), `Missing element ${match[1]}`);
  assert.match(html, /下载原曲库（83 MiB）/); assert.match(html, /现有的 16 首音乐已在曲库里/);
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
  h.api.selectMusicTrack("builtin/one.mp3"); assert.equal(h.audio.playCalls, 0); assert.match(h.get("musicNotice").textContent, /还没有下载/);
});
await test("explicit save includes local translated lyrics and uses only relative public sources", async () => {
  const h = harness(); h.ready(); h.api.state.catalog = publicPlaylist(); await h.api.loadMusic(); h.answers.push({ ok: true, blob: async () => new Blob(["audio"], { type: "audio/mpeg" }) }, { ok: true, text: async () => "[00:01]中文" }, { ok: true, text: async () => "[00:01]English" }); await h.api.downloadMusic(["builtin/one.mp3"]);
  assert.equal(h.api.state.saved.has("builtin/one.mp3"), true); assert.equal(h.stores.get("music").get("builtin/one.mp3").offlineLyrics.length, 2); assert.ok(h.calls.every(call => call.url.startsWith("http://192.0.2.1:8899/CodexControlConsole/phone/music/")));
  assert.equal(h.get("musicDownloadAll").textContent, "曲库已下载"); assert.match(h.get("musicNotice").textContent, /曲库已下载/);
});
await test("saved music starts synchronously through the local SW route, never PC or network audio", async () => {
  const h = harness(); h.ready(); h.api.state.catalog = publicPlaylist(); h.stores.get("media").set("builtin/one.mp3", { id: "builtin/one.mp3", blob: new Blob(["audio"]) }); h.stores.get("music").set("builtin/one.mp3", { id: "builtin/one.mp3", offlineLyrics: [], lyrics: false }); await h.api.loadMusic();
  h.api.selectMusicTrack("builtin/one.mp3"); assert.equal(h.audio.playCalls, 1); assert.equal(h.audio.src, "http://192.0.2.1:8899/CodexControlConsole/phone/audio/builtin%2Fone.mp3"); assert.equal(h.calls.length, 0);
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
await test("shell cache is build-specific and activation never removes user data", async () => {
  assert.match(swSource, /VERSION \+ "-" \+ BUILD/); assert.match(swSource, /encodeURIComponent\(new URL\(self.registration.scope\).pathname\)/); assert.doesNotMatch(swSource, /deleteDatabase|\.clear\(/); assert.match(storeSource, /db.transaction\(\["music", "media"\], "readwrite"\)/);
  const listeners = new Map(), deleted = [], claimed = []; const self = { registration: { scope: "https://example.test/project/phone/", active: {} }, clients: { async claim() { claimed.push(true); } }, addEventListener: (name, fn) => listeners.set(name, fn), async skipWaiting() {} };
  const context = { self, URL, Headers, Response, Blob, importScripts() {}, PhoneStore: {}, caches: { async keys() { return ["codex-console-phone-shell-%2Fproject%2Fphone%2F-old-old", "unrelated-cache", "codex-console-phone-shell-%2Fother%2F-old-old"]; }, async delete(key) { deleted.push(key); } } };
  runInNewContext(swSource, context); let done; listeners.get("activate")({ waitUntil(promise) { done = promise; } }); await done; assert.deepEqual(deleted, ["codex-console-phone-shell-%2Fproject%2Fphone%2F-old-old"]); assert.equal(claimed.length, 1);
});
await test("local SW audio returns full HEAD and all Safari single byte ranges", async () => {
  const context = { self: { registration: { scope: "https://example.test/project/phone/", active: {} }, addEventListener() {} }, URL, Headers, Response, Blob, importScripts() {}, PhoneStore: { async get(_, id) { return id === "test" ? { blob: new Blob(["0123456789"], { type: "audio/wav" }) } : null; } } };
  runInNewContext(swSource + "\nglobalThis.SW_TEST = {localAudio,rangeParts};", context); const api = context.SW_TEST;
  for (const [range, expected, status] of [[null, "0123456789", 200], ["bytes=0-1", "01", 206], ["bytes=7-", "789", 206], ["bytes=-2", "89", 206], ["bytes=9-99", "9", 206]]) { const response = await api.localAudio(new Request("https://example.test/project/phone/audio/test", { headers: range ? { Range: range } : {} }), "test"); assert.equal(response.status, status); assert.equal(await response.text(), expected); }
  const head = await api.localAudio(new Request("https://example.test/project/phone/audio/test", { method: "HEAD" }), "test"); assert.equal(head.headers.get("Content-Length"), "10"); assert.equal(await head.text(), "");
  const bad = await api.localAudio(new Request("https://example.test/project/phone/audio/test", { headers: { Range: "bytes=99-" } }), "test"); assert.equal(bad.status, 416); assert.equal(bad.headers.get("Content-Range"), "bytes */10"); assert.equal((await api.localAudio(new Request("https://example.test/project/phone/audio/missing"), "missing")).status, 404);
});
console.log(`PASS offline phone UI ${count} checks`);
