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
  const nodes = new Map(), calls = [], answers = [], saved = new Map(), timers = new Map(); let nextTimer = 1;
  const get = id => { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); };
  const audio = get("musicAudio"); audio.paused = true; audio.currentTime = 0; audio.duration = NaN; audio.src = ""; audio.playCalls = 0; audio.pauseCalls = 0; audio.loadCalls = 0; const mediaEvents = [];
  audio.pause = () => { audio.paused = true; audio.pauseCalls++; mediaEvents.push("pause"); };
  audio.load = () => { audio.loadCalls++; audio.duration = NaN; audio.currentTime = 0; mediaEvents.push("load"); };
  audio.play = () => { audio.playCalls++; mediaEvents.push("play"); if (audio.playError) return Promise.reject(audio.playError); audio.paused = false; return Promise.resolve(); };
  const tabs = ["tasks", "music", "device", "documents"].map(tab => { const button = new Element("button"); button.dataset.tab = tab; return button; });
  const listTabs = ["inbox", "later", "archive"].map(tab => { const button = new Element("button"); button.dataset.inbox = tab; return button; });
  const musicTabs = ["", "first", "second", "third"].map(tier => { const button = new Element("button"); button.dataset.musicTier = tier; return button; });
  const documentEvents = new Map(), windowEvents = new Map();
  const document = { body: new Element("body"), documentElement: new Element("html"), hidden: false, getElementById: get, createElement: tag => new Element(tag), createTextNode: value => { const text = new Element("#text"); text.textContent = value; return text; }, querySelectorAll: selector => selector === "[data-tab]" ? tabs : selector === "[data-inbox]" ? listTabs : selector === "[data-music-tier]" ? musicTabs : [], addEventListener(name, callback) { documentEvents.set(name, callback); } };
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
  const runtime = { URL, URLSearchParams, AbortController, TypeError, Request, document, history, navigator: { serviceWorker: { controller: {}, ready: Promise.resolve({}), register: async () => ({ waiting: null, addEventListener() {}, async update() {} }), addEventListener() {} } }, PhoneStore, Blob, structuredClone, localStorage: { getItem: key => saved.get(key) || null, setItem: (key, value) => saved.set(key, value) }, window: { setTimeout(fn, delay) { const id = nextTimer++; timers.set(id, { fn, delay }); return id; }, clearTimeout(id) { timers.delete(id); }, location: { href: "http://192.0.2.1:8899/CodexControlConsole/phone/index.html" }, addEventListener(name, callback) { windowEvents.set(name, callback); } }, async fetch(url, options) { mediaEvents.push(`fetch:${url}`); calls.push({ url, options }); const response = answers.shift(); assert.ok(response, `Unexpected fetch ${url}`); return typeof response === "function" ? response() : await response; } };
  const names = "state,taskSync,validatePlanSnapshot,applyPlanSnapshot,syncAddress,supportsTaskSync,updateSyncFallback,connectTaskSync,pollTaskSync,disconnectTaskSync,restoreTaskSync,validateImport,mergeLibrary,reviewImport,commitImport,backupLibrary,mutateLibrary,saveMusicTrack,downloadMusic,importMusicFiles,addLocalLyric,checkUpdate,api,bootstrap,refreshDashboard,renderPlan,renderDevice,renderDocuments,renderInbox,openDocument,moveReader,closeReader,pathValue,appendLink,renderMarkdown,setFont,selectTab,loadMusic,musicTrackList,selectMusicTrack,playMusic,advanceMusic,parseMusicLyrics,syncMusicLyrics,stopMusicPlayback,clearMusic,musicAudioError,loadMusicLyrics,renderMusicTracks";
  assert.ok(source.includes("  void bootstrap();\n})();"), "test export insertion must match only bootstrap footer");
  runInNewContext(source.replace("  void bootstrap();\n})();", `  globalThis.PHONE_TEST = {${names}};\n})();`), runtime);
  const api = runtime.PHONE_TEST;
  return { api, stores, PhoneStore, runtime, get, document, calls, answers, saved, history, tabs, listTabs, musicTabs, audio, mediaEvents, timers, documentEvents, windowEvents, respond(body, status = 200) { answers.push(result(body, status)); }, ready() { api.state.ready = true; api.state.library = api.validateImport(importFixture()); api.state.dashboard = api.state.library.dashboard; stores.get("records").set("library", structuredClone(api.state.library)); get("pairScreen").hidden = true; get("appScreen").hidden = false; api.renderDocuments(); }, all(root, tag) { const found = []; const visit = item => { if (item.tagName === tag.toUpperCase()) found.push(item); for (const child of item.children) visit(child); }; visit(root); return found; } };
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
let count = 0;
async function test(name, run) { await run(); console.log(`PASS ${name}`); count += 1; }
await test("relative project installation has four tabs and no PC connection requirement", () => {
  assert.equal(manifest.start_url, "./index.html"); assert.equal(manifest.scope, "./");
  assert.deepEqual([...html.matchAll(/data-tab="([^"]+)"/g)].map(match => match[1]), ["tasks", "music", "device", "documents"]);
  assert.doesNotMatch(html, /pairCode|pairForm|offlineScreen|logoutButton/); assert.doesNotMatch(source, /clearPrivate|showOffline|showPair/);
  for (const match of source.matchAll(/\/api\/phone\/([^"']+)/g)) assert.ok(match[1].startsWith("plan-sync/"), "optional PC access must be limited to plan sync");
  for (const match of html.matchAll(/(?:src|href)="([^"]+)"/g)) assert.ok(!match[1].startsWith("/"), "project assets must remain relative");
  const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1])); for (const match of source.matchAll(/\bel\("([^"]+)"\)/g)) assert.ok(ids.has(match[1]), `Missing element ${match[1]}`);
  assert.match(html, /id="musicDownloadAll"[^>]*class="primary">全部下载（83 MiB）/); assert.match(html, /音乐和歌词一起保存/);
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
await test("the original 16 songs retain their 1ST, 2ND and 3RD counts and desktop order", async () => {
  const defaults = JSON.parse(readFileSync(new URL("../release-defaults.json", import.meta.url), "utf8")).music;
  const h = harness(); h.ready(); h.api.state.catalog = defaults.order.map(name => ({ name: name.replace(/\.mp3$/, ""), path: `builtin/${name}`, source: `music/${name}`, type: "mp3", size: 9, tier: defaults.tiers[name] }));
  const before = JSON.stringify(h.api.state.catalog); await h.api.loadMusic();
  assert.deepEqual(h.musicTabs.map(button => button.textContent), ["全部 16", "1ST 3", "2ND 6", "3RD 7"]);
  assert.deepEqual(musicRows(h).slice(0, 3).map(button => h.all(button, "span").find(item => item.className === "music-track-name").textContent), ["Outrun", "Redline", "Liquid Roller"]);
  assert.equal(JSON.stringify(h.api.state.catalog), before); assert.equal(h.get("musicFolder").hidden, true); assert.equal(h.calls.length, 0);
});
await test("tier headings keep stable order and default only the phone display to 3RD", async () => {
  const h = harness(); h.ready(); h.api.state.catalog = groupedPlaylist(); const before = JSON.stringify(h.api.state.catalog); await h.api.loadMusic();
  assert.deepEqual(h.musicTabs.map(button => button.textContent), ["全部 6", "1ST 2", "2ND 2", "3RD 2"]);
  assert.deepEqual(h.all(h.get("musicTracks"), "h3").map(heading => heading.textContent), ["1ST2 首", "2ND2 首", "3RD2 首"]);
  assert.deepEqual(musicRows(h).map(button => h.all(button, "span").find(item => item.className === "music-track-name").textContent), ["First B", "First A", "Second B", "Second A", "Third default", "Third explicit"]);
  assert.equal(h.all(h.get("musicTracks"), "button").length, 6, "song rows must not add individual download buttons");
  assert.equal(JSON.stringify(h.api.state.catalog), before); assert.equal(h.api.state.catalog[0].tier, undefined);
});
await test("tier filtering combines with search and source without changing global counts", async () => {
  const h = harness(); h.ready(); h.api.state.catalog = groupedPlaylist(); h.stores.get("music").set("local/one", { id: "local/one", name: "Second local B", tier: "second", type: "mp3" }); await h.api.loadMusic();
  assert.equal(h.get("musicFolder").hidden, false); assert.deepEqual(h.get("musicFolder").children.map(option => option.textContent), ["全部来源", "原曲库", "本地音乐"]);
  h.musicTabs[2].listeners.get("click")(); h.get("musicSearch").value = " b "; h.get("musicSearch").listeners.get("input")();
  assert.equal(musicRows(h).length, 2); assert.match(h.get("musicTracks").textContent, /Second B/); assert.match(h.get("musicTracks").textContent, /Second local B/);
  h.get("musicFolder").value = "builtin"; h.get("musicFolder").listeners.get("change")(); assert.equal(musicRows(h).length, 1); assert.doesNotMatch(h.get("musicTracks").textContent, /First B|Second A|Second local B/);
  assert.deepEqual(h.musicTabs.map(button => button.textContent), ["全部 7", "1ST 2", "2ND 3", "3RD 2"]); assert.equal(h.musicTabs[2].attributes["aria-pressed"], "true"); assert.match(h.get("musicListMeta").textContent, /7 首音乐.*显示 1 首/);
  h.get("musicSearch").value = "missing"; h.get("musicSearch").listeners.get("input")(); assert.equal(musicRows(h).length, 0); assert.match(h.get("musicTracks").textContent, /没有匹配/);
});
await test("one all-download click saves every missing tier and its lyrics despite active filters", async () => {
  const h = harness(); h.ready(); h.api.state.catalog = [...groupedPlaylist(), ...publicPlaylist()]; const alreadySaved = h.api.state.catalog[1]; h.stores.get("media").set(alreadySaved.path, { id: alreadySaved.path, blob: new Blob(["prior"]) }); await h.api.loadMusic();
  h.musicTabs[1].listeners.get("click")(); h.get("musicSearch").value = "B"; h.get("musicSearch").listeners.get("input")(); assert.equal(musicRows(h).length, 1);
  for (const track of h.api.state.catalog.filter(item => item.path !== alreadySaved.path)) { h.answers.push({ ok: true, blob: async () => new Blob(["audio"], { type: "audio/mpeg" }) }); for (const language of track.lyricsLanguages || []) h.answers.push({ ok: true, text: async () => `[00:01]${language.code}` }); }
  await h.get("musicDownloadAll").listeners.get("click")();
  assert.deepEqual([...h.stores.get("media").keys()].sort(), h.api.state.catalog.map(track => track.path).sort()); assert.equal(h.stores.get("music").get("builtin/one.mp3").offlineLyrics.length, 2);
  const audioRequests = h.calls.filter(call => call.url.endsWith(".mp3")); assert.equal(audioRequests.length, 6); assert.ok(audioRequests.every(call => !call.url.endsWith(alreadySaved.source))); assert.equal(h.answers.length, 0);
  assert.equal(h.api.state.music.tier, "first"); assert.equal(h.api.state.music.search, "B"); assert.equal(h.get("musicDownloadAll").textContent, "全部已下载"); assert.equal(h.get("musicDownloadAll").disabled, true); assert.equal(h.audio.playCalls, 0);
});
await test("stopping all-download preserves completed songs and resumes only missing songs", async () => {
  const h = harness(); h.ready(); h.api.state.catalog = groupedPlaylist().slice(0, 2); await h.api.loadMusic(); const blocked = defer(), urls = [];
  h.runtime.fetch = async (url, options) => { urls.push(url); if (url.endsWith("group-1.mp3")) { blocked.resolve(); return new Promise((_, reject) => options.signal.addEventListener("abort", () => reject(Object.assign(new Error("stopped"), { name: "AbortError" })))); } return { ok: true, blob: async () => new Blob(["audio"]) }; };
  const downloading = h.get("musicDownloadAll").listeners.get("click")(); await blocked.promise; assert.equal(h.get("musicDownloadAll").disabled, true); assert.equal(h.get("musicDownloadStop").hidden, false);
  h.get("musicDownloadStop").listeners.get("click")(); await downloading;
  assert.deepEqual([...h.stores.get("media").keys()], ["builtin/group-0.mp3"]); assert.equal(h.get("musicDownloadAll").disabled, false); assert.equal(h.get("musicDownloadStop").hidden, true); assert.match(h.get("musicDownloadAll").textContent, /继续下载.*1 首/); assert.match(h.get("musicNotice").textContent, /已停止下载.*1 首仍然保留/);
  const resumed = []; h.runtime.fetch = async url => { resumed.push(url); return { ok: true, blob: async () => new Blob(["audio"]) }; }; await h.get("musicDownloadAll").listeners.get("click")();
  assert.equal(resumed.length, 1); assert.ok(resumed[0].endsWith("group-1.mp3")); assert.equal(h.stores.get("media").size, 2); assert.equal(h.get("musicDownloadAll").textContent, "全部已下载");
});
await test("explicit save includes local translated lyrics and uses only relative public sources", async () => {
  const h = harness(); h.ready(); h.api.state.catalog = publicPlaylist(); await h.api.loadMusic(); h.answers.push({ ok: true, blob: async () => new Blob(["audio"], { type: "audio/mpeg" }) }, { ok: true, text: async () => "[00:01]中文" }, { ok: true, text: async () => "[00:01]English" }); await h.api.downloadMusic(["builtin/one.mp3"]);
  assert.equal(h.api.state.saved.has("builtin/one.mp3"), true); assert.equal(h.stores.get("music").get("builtin/one.mp3").offlineLyrics.length, 2); assert.ok(h.calls.every(call => call.url.startsWith("http://192.0.2.1:8899/CodexControlConsole/phone/music/")));
  assert.equal(h.get("musicDownloadAll").textContent, "全部已下载"); assert.match(h.get("musicNotice").textContent, /全部已下载/);
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
const snapshot = (hash = "a", computerId = "fixture-pc") => ({ format: "codex-console-plan-snapshot", schemaVersion: 1, hash: hash.repeat(64), updatedAt: "2026-10-01T12:00:00Z", computerId, plan: plan().plan });
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
  const h = harness(); h.ready(); h.get("syncAddress").value = "http://192.168.1.10:8899/"; h.get("syncCode").value = "123456"; const before = JSON.stringify(h.api.state.library); await h.api.connectTaskSync();
  assert.equal(h.calls.length, 0); assert.equal(h.get("syncFallback").href, "http://192.168.1.10:8899/mobile.html"); assert.match(h.get("syncNotice").textContent, /不支持/); assert.equal(JSON.stringify(h.api.state.library), before); assert.equal(h.get("syncCode").value, "");
  for (const unsafe of ["https://example.com/", "http://example.com/", "http://127.0.0.1:8899/", "http://192.168.1.10:8899/other", "http://user:secret@192.168.1.10:8899/", "http://192.168.1.10:8899/?token=x"]) assert.throws(() => h.api.syncAddress(unsafe));
});
await test("supported pairing stores tokens locally and fetches only scoped read-only task APIs", async () => {
  const h = harness(); h.ready(); enableSync(h); h.respond({ token: "x".repeat(43), computerId: "fixture-pc", expiresIn: 28800 }); h.respond(snapshot()); await h.api.connectTaskSync();
  assert.deepEqual(h.calls.map(call => call.url), ["http://192.168.1.10:8899/api/phone/plan-sync/pair", "http://192.168.1.10:8899/api/phone/plan-sync/plan"]);
  for (const { options } of h.calls) { assert.equal(options.targetAddressSpace, "local"); assert.equal(options.credentials, "omit"); assert.equal(options.mode, "cors"); assert.equal(options.cache, "no-store"); assert.equal(options.redirect, "error"); assert.equal(options.headers["X-Codex-Phone"], "1"); }
  assert.equal(h.calls[1].options.headers.Authorization, "Bearer " + "x".repeat(43)); assert.deepEqual(JSON.parse(h.calls[0].options.body), { code: "123456" }); assert.equal(h.stores.get("settings").get("taskSync").token, "x".repeat(43)); assert.equal(h.api.taskSync.connected, true); assert.ok([...h.timers.values()].some(timer => timer.delay === 5000));
});
await test("a late old PC response cannot replace a newly selected source", async () => {
  const h = harness(); h.ready(); h.api.taskSync.config = savedSync(); const pending = defer(); h.answers.push(pending.promise); const poll = h.api.pollTaskSync(); await h.api.disconnectTaskSync(false); const next = snapshot("c", "next-pc"); await h.api.applyPlanSnapshot(next); pending.resolve(result(snapshot())); await poll;
  assert.equal(h.api.state.library.planSync.computerId, "next-pc"); assert.equal(h.api.taskSync.connected, false); assert.equal(h.api.taskSync.timer, null);
});
await test("disconnect during a pending task write restores the prior phone cache before another source can write", async () => {
  const h = harness(); h.ready(); const before = JSON.stringify(h.stores.get("records").get("library")), pending = defer(), originalPut = h.PhoneStore.put.bind(h.PhoneStore);
  h.PhoneStore.put = async (name, value) => { await originalPut(name, value); if (name === "records" && value.planSync?.hash === "a".repeat(64)) await pending.promise; };
  const update = h.api.applyPlanSnapshot(snapshot(), h.api.taskSync.generation); await new Promise(resolve => setTimeout(resolve, 0)); await h.api.disconnectTaskSync(false); pending.resolve(); assert.equal(await update, false); assert.equal(JSON.stringify(h.stores.get("records").get("library")), before); assert.equal(JSON.stringify(h.api.state.library), before);
  await h.api.applyPlanSnapshot(snapshot("b", "new-pc")); assert.equal(h.stores.get("records").get("library").planSync.computerId, "new-pc");
});
await test("offline and expired sync retain all data and expiry stops polling without losing cached tasks", async () => {
  const h = harness(); h.ready(); await h.api.applyPlanSnapshot(snapshot()); h.api.taskSync.config = savedSync(); const before = JSON.stringify(h.api.state.library); h.answers.push(Promise.reject(new TypeError("offline"))); await h.api.pollTaskSync(); assert.equal(JSON.stringify(h.api.state.library), before); assert.match(h.get("syncNotice").textContent, /已保留/);
  h.api.taskSync.config.expiresAt = Date.now() - 1; await h.api.pollTaskSync(); assert.equal(h.api.taskSync.config.token, undefined); assert.equal(h.api.taskSync.timer, null); assert.match(h.get("syncNotice").textContent, /过期/); assert.equal(JSON.stringify(h.api.state.library), before);
});
await test("background suspends polling and returning foreground refreshes immediately", async () => {
  const h = harness(); h.ready(); h.api.taskSync.config = savedSync(); h.document.hidden = true; await h.api.pollTaskSync(); assert.equal(h.calls.length, 0); h.documentEvents.get("visibilitychange")(); assert.equal(h.api.taskSync.timer, null);
  h.respond(snapshot()); h.document.hidden = false; h.documentEvents.get("visibilitychange")(); await new Promise(resolve => setTimeout(resolve, 0)); assert.equal(h.calls.length, 1); assert.equal(h.api.taskSync.connected, true);
});
console.log(`PASS offline phone UI ${count} checks`);
