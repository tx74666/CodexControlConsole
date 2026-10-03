#!/usr/bin/env node
// Exercise the phone UI against isolated in-memory responses; no real plan or inbox writes.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const normalizeScript = value => value.replace(/\r\n?/g, "\n");
const source = normalizeScript(readFileSync(new URL("../mobile.js", import.meta.url), "utf8"));
const html = readFileSync(new URL("../mobile.html", import.meta.url), "utf8");
const css = readFileSync(new URL("../mobile.css", import.meta.url), "utf8");
const manifest = JSON.parse(readFileSync(new URL("../mobile.webmanifest", import.meta.url), "utf8"));
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
function harness(script = source, initialUrl = "http://192.0.2.1:8899/mobile.html") {
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
  get("pairRemember").checked = true;
  const audio = get("musicAudio"); audio.paused = true; audio.currentTime = 0; audio.duration = NaN; audio.src = ""; audio.playCalls = 0; audio.pauseCalls = 0; audio.loadCalls = 0; const mediaEvents = [];
  audio.pause = () => { audio.paused = true; audio.pauseCalls++; mediaEvents.push("pause"); };
  audio.load = () => { audio.loadCalls++; audio.duration = NaN; audio.currentTime = 0; mediaEvents.push("load"); };
  audio.play = () => { audio.playCalls++; mediaEvents.push("play"); if (audio.playError) return Promise.reject(audio.playError); audio.paused = false; return Promise.resolve(); };
  const tabs = ["transfer", "tasks", "music", "device", "documents"].map(tab => { const button = new Element("button"); button.dataset.tab = tab; return button; });
  const listTabs = ["inbox", "later", "archive"].map(tab => { const button = new Element("button"); button.dataset.inbox = tab; return button; });
  const documentEvents = new Map(), windowEvents = new Map();
  const document = { body: new Element("body"), documentElement: new Element("html"), hidden: false, getElementById: get, createElement: tag => new Element(tag), createTextNode: value => { const text = new Element("#text"); text.textContent = value; return text; }, querySelectorAll: selector => selector === "[data-tab]" ? tabs : selector === "[data-inbox]" ? listTabs : [], addEventListener(name, callback) { documentEvents.set(name, callback); } };
  const replacedUrls = [];
  const history = { state: null, replaceState(value, unused, url) { this.state = value; replacedUrls.push(url); runtime.window.location.href = url; }, pushState(value) { this.state = value; }, back() { this.state = null; } };
  const runtime = { URL, URLSearchParams, AbortController, TypeError, Blob, structuredClone, document, history, navigator: {}, localStorage: { getItem: key => saved.get(key) || null, setItem: (key, value) => saved.set(key, value), removeItem: key => saved.delete(key) }, window: { setTimeout(fn, delay) { const id = nextTimer++; timers.set(id, { fn, delay }); return id; }, clearTimeout(id) { timers.delete(id); }, location: { href: initialUrl }, addEventListener(name, callback) { windowEvents.set(name, callback); } }, async fetch(url, options) { mediaEvents.push(`fetch:${url}`); calls.push({ url, options }); const response = answers.shift(); assert.ok(response, `Unexpected fetch ${url}`); return typeof response === "function" ? response() : await response; } };
  const names = "state,livePlan,validateLivePlan,pollLivePlan,savePlanSnapshot,api,bootstrap,refreshDashboard,renderPlan,renderDevice,renderDocuments,renderInbox,openDocument,moveReader,closeReader,showPair,showOffline,pathValue,appendLink,renderMarkdown,setFont,selectTab,loadMusic,musicTrackList,selectMusicTrack,playMusic,advanceMusic,parseMusicLyrics,syncMusicLyrics,stopMusicPlayback,clearMusic,musicAudioError,loadMusicLyrics,renderMusicTracks";
  const normalized = normalizeScript(script), footer = "  void bootstrap();\n})();";
  assert.equal(normalized.split(footer).length, 2, "test export insertion must match only bootstrap footer");
  runInNewContext(normalized.replace(footer, `  globalThis.PHONE_TEST = {${names}};\n})();`), runtime);
  const api = runtime.PHONE_TEST;
  return { api, runtime, get, document, calls, answers, saved, history, replacedUrls, tabs, listTabs, audio, mediaEvents, timers, documentEvents, windowEvents, respond(body, status = 200) { answers.push(result(body, status)); }, ready() { api.state.paired = true; api.state.dashboard = dashboard(); get("pairScreen").hidden = true; get("appScreen").hidden = false; api.renderDocuments(); }, all(root, tag) { const found = []; const visit = item => { if (item.tagName === tag.toUpperCase()) found.push(item); for (const child of item.children) visit(child); }; visit(root); return found; } };
}
let count = 0;
async function test(name, run) { await run(); console.log(`PASS ${name}`); count += 1; }

await test("iPhone install entry, safe areas, touch sizes and five real tabs", () => {
  assert.equal(manifest.start_url, "/mobile.html"); assert.equal(manifest.scope, "/"); assert.equal(manifest.display, "standalone");
  assert.match(html, /apple-mobile-web-app-capable/); assert.match(html, /apple-touch-icon[^>]+256/); assert.match(html, /viewport-fit=cover/);
  assert.deepEqual([...html.matchAll(/data-tab="([^"]+)"/g)].map(match => match[1]), ["transfer", "tasks", "music", "device", "documents"]);
  assert.match(css, /env\(safe-area-inset-bottom\)/); assert.match(css, /min-height:44px/); assert.match(css, /font-size:24px/); assert.match(css, /reader-table-scroll\{overflow-x:auto/);
  assert.doesNotMatch(source, /serviceWorker|\.innerHTML|document\.cookie/); assert.doesNotMatch(html, /onclick=|<script[^>]*>\s*[^<\s]/);
  const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]));
  for (const match of source.matchAll(/\bel\("([^"]+)"\)/g)) assert.ok(ids.has(match[1]), `Missing phone element ${match[1]}`);
});
await test("LF and Windows CRLF sources inject one test footer without starting the application", async () => {
  for (const script of [source, source.replace(/\n/g, "\r\n")]) {
    const h = harness(script);
    assert.equal(h.calls.length, 0, "test loading must not start real bootstrap requests");
    h.respond({ paired: false }); await h.api.bootstrap();
    assert.equal(h.calls.length, 1); assert.equal(h.calls[0].url, "/api/phone/status");
    assert.equal(h.get("appScreen").hidden, true); assert.equal(h.api.state.paired, false);
  }
  const footer = "  void bootstrap();\n})();";
  assert.throws(() => harness(source.replace(footer, "})();")), /must match only bootstrap footer/);
  assert.throws(() => harness(source + "\n" + footer), /must match only bootstrap footer/);
});
await test("unpaired bootstrap never requests or displays private content", async () => {
  const h = harness(); h.ready(); h.respond({ paired: false }); await h.api.bootstrap();
  assert.equal(h.calls.length, 1); assert.equal(h.calls[0].url, "/api/phone/status"); assert.equal(h.get("appScreen").hidden, true); assert.equal(h.get("pairScreen").hidden, false); assert.equal(h.api.state.dashboard, null); assert.equal(h.get("inboxList").textContent, "");
});
await test("authenticated requests use no-store, same-origin cookies, CSRF header and no redirect", async () => {
  const h = harness(); h.respond({ paired: true }); await h.api.api("status"); h.respond({ paired: true }); await h.api.api("pair", { code: "123456" });
  for (const call of h.calls) { assert.equal(call.options.cache, "no-store"); assert.equal(call.options.credentials, "same-origin"); assert.equal(call.options.mode, "same-origin"); assert.equal(call.options.redirect, "error"); assert.equal(call.options.headers["X-Codex-Phone"], "1"); }
  assert.equal(h.calls[1].options.method, "POST"); assert.equal(h.calls[1].options.headers["Content-Type"], "application/json"); assert.deepEqual(JSON.parse(h.calls[1].options.body), { code: "123456" }); assert.equal(h.saved.size, 0);
});
await test("four readonly plan groups preserve literal content and explain saved status", () => {
  const h = harness(); h.api.renderPlan(plan());
  assert.equal(h.get("taskGroups").children.length, 4); assert.equal(h.all(h.get("taskGroups"), "input").length, 0); assert.equal(h.all(h.get("taskGroups"), "script").length, 0);
  assert.match(h.get("taskGroups").textContent, /<script>保留为文字<\/script>/); assert.match(h.get("planNotice").textContent, /暂未同步/);
  h.api.renderPlan({ plan: { groups: [] }, error: "计划文件无效" }); assert.match(h.get("taskGroups").textContent, /计划文件无效/);
});
await test("memory comes only from currentMemory and saved hardware has its own date", () => {
  const h = harness(); const device = dashboard().device; h.api.renderDevice(device);
  assert.match(h.get("memoryCard").textContent, /91% 已用/); assert.match(h.get("memoryCard").textContent, /可用 1.0 GiB/); assert.match(h.get("hardwareCard").textContent, /保存的硬件采样/);
  h.api.renderDevice({ ...device, currentMemory: { status: "unavailable" }, availableBytes: 14 * 1024 ** 3 });
  assert.match(h.get("memoryCard").textContent, /暂时无法读取/); assert.doesNotMatch(h.get("memoryCard").textContent, /14.0 GiB|91/);
});
await test("To read Later Archive remain separate and opening never marks read", async () => {
  const h = harness(); h.ready(); assert.match(h.get("inboxList").textContent, /待阅读文件/); assert.doesNotMatch(h.get("inboxList").textContent, /Later 文件|归档文件/);
  assert.equal(h.get("inboxCount").textContent, "1"); assert.equal(h.get("laterCount").textContent, "1"); assert.equal(h.get("archiveCount").textContent, "1");
  h.respond({ path: "reports/one.md", name: "one.md", format: "markdown", content: "# 重点\n\n正文" }); await h.api.openDocument("reports/one.md", { entryId: "to-read" });
  assert.equal(h.calls.length, 1); assert.equal(h.calls[0].options.method, "GET"); assert.equal(h.get("readerActions").hidden, false); assert.equal(h.document.body.dataset.reading, "true"); assert.equal(h.get("main").inert, true);
});
await test("explicit Read and Later save only inbox status and update local lists", async () => {
  const h = harness(); h.ready(); h.respond({ path: "reports/one.md", content: "正文", format: "markdown" }); await h.api.openDocument("reports/one.md", { entryId: "to-read" });
  const archive = inbox(); archive.entries[0].status = "archive"; h.respond(archive); await h.api.moveReader("read");
  assert.deepEqual(JSON.parse(h.calls[1].options.body), { id: "to-read", status: "archive" }); assert.equal(h.get("archiveCount").textContent, "2"); assert.match(h.get("readerNotice").textContent, /电脑上的阅读清单也已更新/);
  const later = inbox(); later.entries[0].status = "later"; h.respond(later); await h.api.moveReader("later"); assert.deepEqual(JSON.parse(h.calls[2].options.body), { id: "to-read", status: "later" }); assert.equal(h.get("laterCount").textContent, "2");
});
await test("paired reference languages are readonly with no inbox controls", async () => {
  const h = harness(); h.ready(); const reference = h.api.state.dashboard.documents.references.items[0];
  h.respond({ path: "nodes.zh.md", content: "# 中文\n\n正文", format: "markdown" }); await h.api.openDocument("nodes.zh.md", { reference });
  assert.equal(h.get("readerActions").hidden, true); assert.equal(h.get("readerLanguages").children.length, 2);
  h.respond({ path: "nodes.en.md", content: "# English\n\nText", format: "markdown" }); await h.get("readerLanguages").children[1].listeners.get("click")();
  // Button listener deliberately launches the async reader without returning it.
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(h.get("readerContent").lang, "en"); assert.equal(h.get("readerActions").hidden, true); assert.equal(h.calls.filter(call => call.options.method === "POST").length, 0);
});
await test("Markdown remains inert and unsafe links never become navigation", () => {
  const h = harness(); h.api.state.reader = { path: "reports/one.md" }; const target = h.get("readerContent");
  h.api.renderMarkdown('<script>alert(1)</script>\n\n[bad](javascript:alert) [file](file:///secret) ![pixel](https://example.com/pixel.png) [outside](../../../secret.md) [okay](https://example.com/docs)', target);
  assert.equal(h.all(target, "script").length, 0); assert.equal(h.all(target, "img").length, 0); const links = h.all(target, "a"); assert.equal(links.length, 1); assert.equal(links[0].href, "https://example.com/docs"); assert.equal(links[0].rel, "noopener noreferrer"); assert.match(target.textContent, /<script>/);
  assert.equal(h.api.pathValue("C:\\secret.md"), null); assert.equal(h.api.pathValue("%2fsecret.md", "", true), null); assert.equal(h.api.pathValue("../../secret.md", "reports/one.md"), null);
});
await test("reader supports heading navigation, nested lists and scrollable four-column tables", () => {
  const h = harness(); const target = h.get("readerContent"); h.api.renderMarkdown("## 标题\n\n- 项一\n  - 子项\n\n| A | B | C | D |\n| --- | --- | --- | --- |\n| 一 | 二 | 三 | 四 |", target);
  assert.equal(h.all(target, "h2").length, 1); assert.equal(h.all(target, "ul").length, 2); assert.equal(h.all(target, "table").length, 1); assert.equal(h.all(target, "th").length, 4);
  const wrap = target.children.find(child => child.className === "reader-table-scroll"); assert.ok(wrap); assert.equal(wrap.attributes["aria-label"], "表格，可横向滚动");
  h.api.renderMarkdown("| A\\|B | C |\n| --- | --- |\n| 一 | 二 |", target); assert.equal(h.all(target, "th").length, 2); assert.equal(h.all(target, "th")[0].textContent, "A|B");
  const long = "a".repeat(513000); h.api.renderMarkdown(long, target); assert.equal(h.all(target, "pre").length, 1); assert.match(target.textContent, /纯文本显示/); assert.ok(target.textContent.includes(long));
});
await test("a late reader response cannot replace a newer document", async () => {
  const h = harness(); h.ready(); const slow = defer(); h.answers.push(slow.promise); const first = h.api.openDocument("reports/one.md");
  h.respond({ path: "reports/later.md", content: "# New document", format: "markdown" }); await h.api.openDocument("reports/later.md");
  slow.resolve(result({ path: "reports/one.md", content: "# Old document", format: "markdown" })); await first;
  assert.equal(h.get("readerTitle").textContent, "New document"); assert.equal(h.api.state.reader.path, "reports/later.md");
});
await test("401 clears documents plans reader and credential input immediately", async () => {
  const h = harness(); h.ready(); h.get("taskGroups").textContent = "PRIVATE PLAN"; h.get("readerContent").textContent = "PRIVATE DOCUMENT"; h.get("pairCode").value = "123456"; h.respond({ error: "expired" }, 401);
  await assert.rejects(h.api.api("dashboard"), error => error.auth);
  assert.equal(h.api.state.dashboard, null); assert.equal(h.get("taskGroups").textContent, ""); assert.equal(h.get("readerContent").textContent, ""); assert.equal(h.get("pairCode").value, ""); assert.equal(h.get("readerScreen").hidden, true); assert.equal(h.get("pairScreen").hidden, false);
});
await test("logout invalidation also rejects a pending stale dashboard response", async () => {
  const h = harness(); h.ready(); const pending = defer(); h.answers.push(pending.promise); const request = h.api.refreshDashboard();
  h.api.showPair("已断开"); pending.resolve(result(dashboard())); await assert.rejects(request, error => error.cancelled);
  assert.equal(h.api.state.dashboard, null); assert.equal(h.get("appScreen").hidden, true); assert.equal(h.get("pairScreen").hidden, false);
});
await test("the actual logout control sends a request and clears sensitive UI", async () => {
  const h = harness(); h.ready(); h.get("readerContent").textContent = "PRIVATE"; h.respond({ paired: false }); await h.get("logoutButton").listeners.get("click")();
  assert.equal(h.calls[0].url, "/api/phone/logout"); assert.equal(h.calls[0].options.method, "POST"); assert.equal(h.get("readerContent").textContent, ""); assert.equal(h.get("appScreen").hidden, true); assert.equal(h.get("pairScreen").hidden, false);
});
await test("an old connection failure cannot overwrite the current pairing screen", async () => {
  const h = harness(); h.ready(); const pending = defer(); h.answers.push(pending.promise); const request = h.api.api("dashboard"); h.api.showPair("已断开"); pending.reject(new TypeError("old connection error"));
  await assert.rejects(request, error => error.cancelled); assert.equal(h.get("pairScreen").hidden, false); assert.equal(h.get("offlineScreen").hidden, true);
});
await test("offline clears private data and saves only font preference", () => {
  const h = harness(); h.ready(); h.get("readerContent").textContent = "PRIVATE"; h.api.setFont(24); h.api.showOffline(new Error("Wi-Fi 断开"));
  assert.equal(h.api.state.dashboard, null); assert.equal(h.get("readerContent").textContent, ""); assert.equal(h.get("offlineScreen").hidden, false); assert.equal(h.get("appScreen").hidden, true); assert.deepEqual([...h.saved], [["codexPhone.readerFont.v1", "24"]]);
});
await test("music loads lazily without autoplay and existing tabs remain available", async () => {
  const h = harness(); h.ready(); h.api.selectTab("tasks"); h.api.selectTab("device"); h.api.selectTab("documents"); assert.equal(h.calls.length, 0);
  h.respond(playlist()); h.api.selectTab("music"); await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(h.calls.length, 1); assert.equal(h.calls[0].url, "/api/phone/music"); assert.equal(h.audio.playCalls, 0); assert.equal(h.audio.src, ""); assert.equal(h.get("musicTracks").children.length, 3);
  assert.equal(h.all(h.get("musicTracks"), "script").length, 0); assert.match(h.get("musicTracks").textContent, /<script>One<\/script>/);
  h.api.selectTab("tasks"); assert.equal(h.get("tasksPanel").hidden, false); assert.equal(h.get("musicPanel").hidden, true); h.api.selectTab("device"); assert.equal(h.get("devicePanel").hidden, false);
  assert.match(html, /<audio id="musicAudio" preload="none" playsinline>/);
});
await test("tapping a registered track plays directly before any lyric request", async () => {
  const h = harness(); h.ready(); h.respond(playlist()); await h.api.loadMusic(); h.mediaEvents.length = 0;
  h.respond({ path: "album/three.mp3", content: "[00:01]歌词", format: "lrc", language: "zh" }); h.get("musicTracks").children[2].listeners.get("click")();
  assert.equal(h.audio.playCalls, 1); assert.equal(h.audio.src, "/api/phone/music/audio?path=album%2Fthree.mp3"); assert.ok(h.mediaEvents.indexOf("play") < h.mediaEvents.findIndex(event => event.startsWith("fetch:")));
  await new Promise(resolve => setTimeout(resolve, 0)); assert.match(h.get("musicLyrics").textContent, /歌词/); assert.equal(h.get("musicPlay").textContent, "暂停");
  const playCount = h.audio.playCalls; h.api.selectMusicTrack("https://evil.invalid/audio"); assert.equal(h.audio.playCalls, playCount);
});
await test("play failures stay visible with an explicit tap-to-play retry", async () => {
  const h = harness(); h.ready(); h.respond(playlist()); await h.api.loadMusic(); h.audio.playError = { name: "NotAllowedError" }; h.api.selectMusicTrack("local/one.mp3");
  await new Promise(resolve => setTimeout(resolve, 0)); assert.match(h.get("musicNotice").textContent, /再点一次/); assert.equal(h.get("musicPlay").textContent, "播放");
  h.audio.playError = null; h.get("musicPlay").listeners.get("click")(); assert.equal(h.audio.paused, false); assert.equal(h.audio.playCalls, 2);
});
await test("seek previous next and repeat modes control only the phone media element", async () => {
  const h = harness(); h.ready(); const data = playlist(); data.tracks[2].lyrics = false; h.respond(data); await h.api.loadMusic(); h.api.selectMusicTrack("local/one.mp3");
  h.audio.duration = 200; h.get("musicSeek").value = "250"; h.get("musicSeek").listeners.get("input")(); assert.equal(h.audio.currentTime, 50); assert.equal(h.get("musicElapsed").textContent, "0:50");
  h.get("musicNext").listeners.get("click")(); assert.equal(h.api.state.music.selected.path, "album/two.m4a"); h.get("musicPrevious").listeners.get("click")(); assert.equal(h.api.state.music.selected.path, "local/one.mp3");
  h.get("musicRepeat").listeners.get("click")(); assert.equal(h.api.state.music.repeat, "one"); const count = h.audio.playCalls; h.audio.listeners.get("ended")(); assert.equal(h.api.state.music.selected.path, "local/one.mp3"); assert.equal(h.audio.playCalls, count + 1);
  h.get("musicRepeat").listeners.get("click")(); assert.equal(h.api.state.music.repeat, "off"); assert.equal(h.get("musicRepeat").textContent, "播完停止"); h.api.selectMusicTrack("album/three.mp3"); const last = h.audio.playCalls; h.audio.listeners.get("ended")(); assert.equal(h.audio.playCalls, last);
  assert.equal(h.calls.filter(call => call.options.method === "POST").length, 0);
});
await test("music refresh preserves a surviving selection and never autoplays", async () => {
  const h = harness(); h.ready(); h.respond(playlist()); await h.api.loadMusic(); h.api.selectMusicTrack("local/one.mp3"); h.audio.pause(); const count = h.audio.playCalls;
  h.respond(playlist()); await h.api.loadMusic(true); assert.equal(h.api.state.music.selected.path, "local/one.mp3"); assert.equal(h.audio.playCalls, count); assert.equal(h.audio.paused, true);
  h.respond({ playback: "phone", tracks: [] }); await h.api.loadMusic(true); assert.equal(h.api.state.music.selected, null); assert.equal(h.audio.src, ""); assert.equal(h.audio.paused, true);
});
await test("LRC timestamps offsets repeated lines and text lyrics are parsed without raw HTML", () => {
  const h = harness(); const parsed = h.api.parseMusicLyrics("[offset:-500]\n[ar:艺术家]\n[00:01.25][00:03.500]一句\n[00:03.500]A translation\n[00:99]invalid", "lrc");
  assert.equal(parsed.synced, true); assert.deepEqual(JSON.parse(JSON.stringify(parsed.lines)), [{ time: .75, text: "一句" }, { time: 3, text: "一句" }, { time: 3, text: "A translation" }]);
  const plain = h.api.parseMusicLyrics("<script>literal</script>\n第二句", "text"); assert.equal(plain.synced, false); assert.equal(plain.lines[0].text, "<script>literal</script>");
});
await test("local lyric languages replace content and highlight the current timed line", async () => {
  const h = harness(); h.ready(); h.respond(playlist()); await h.api.loadMusic(); h.respond({ path: "album/three.mp3", content: "[00:01]一句\n[00:03]下一句", format: "lrc", language: "zh" }); h.api.selectMusicTrack("album/three.mp3"); await new Promise(resolve => setTimeout(resolve, 0));
  h.api.syncMusicLyrics(2); assert.equal(h.get("musicLyrics").children[0].dataset.active, "true"); assert.equal(h.get("musicLyrics").children[1].dataset.active, "false");
  assert.equal(h.get("musicLyricLanguages").children[0].textContent, "中文");
  h.respond({ path: "album/three.mp3", content: "[00:01]<script>English stays text</script>", format: "lrc", language: "en" }); h.get("musicLyricLanguages").children[1].listeners.get("click")(); await new Promise(resolve => setTimeout(resolve, 0));
  assert.match(h.calls.at(-1).url, /language=en$/); assert.match(h.get("musicLyrics").textContent, /English stays text/); assert.equal(h.all(h.get("musicLyrics"), "script").length, 0);
});
await test("a late lyric response cannot replace a newer selected track", async () => {
  const h = harness(); h.ready(); h.respond(playlist()); await h.api.loadMusic(); const pending = defer(); h.answers.push(pending.promise); h.api.selectMusicTrack("album/three.mp3"); h.api.selectMusicTrack("local/one.mp3");
  pending.resolve(result({ path: "album/three.mp3", content: "PRIVATE OLD LYRICS", format: "text" })); await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(h.api.state.music.selected.path, "local/one.mp3"); assert.equal(h.get("musicLyrics").textContent, ""); assert.equal(h.get("musicLyricsSection").hidden, true);
});
await test("401 logout and offline stop audio detach the source and clear track metadata", async () => {
  for (const type of ["auth", "logout", "offline"]) {
    const h = harness(); h.ready(); h.respond(playlist()); await h.api.loadMusic(); h.api.selectMusicTrack("local/one.mp3"); assert.equal(h.audio.paused, false);
    if (type === "auth") { h.respond({ error: "expired" }, 401); await assert.rejects(h.api.api("dashboard"), error => error.auth); }
    else if (type === "logout") { h.respond({ paired: false }); await h.get("logoutButton").listeners.get("click")(); }
    else h.api.showOffline(new Error("Wi-Fi lost"));
    assert.equal(h.audio.paused, true); assert.equal(h.audio.src, ""); assert.ok(h.audio.loadCalls >= 2); assert.equal(h.api.state.music.selected, null); assert.equal(h.get("musicTracks").textContent, ""); assert.equal(h.get("musicLyrics").textContent, "");
  }
});
await test("search folder filters and paging operate locally on the registered list", async () => {
  const h = harness(); h.ready(); const data = playlist(); data.tracks.push(...Array.from({ length: 70 }, (_, index) => ({ name: `Extra ${index}`, path: `extras/${index}.mp3`, type: "mp3" }))); h.respond(data); await h.api.loadMusic();
  assert.equal(h.get("musicTracks").children.length, 60); assert.equal(h.get("musicMore").hidden, false); h.get("musicMore").listeners.get("click")(); assert.equal(h.get("musicTracks").children.length, 73);
  h.get("musicSearch").value = "Two"; h.get("musicSearch").listeners.get("input")(); assert.equal(h.get("musicTracks").children.length, 1); assert.match(h.get("musicTracks").textContent, /Two/);
  h.get("musicSearch").value = ""; h.get("musicSearch").listeners.get("input")(); h.get("musicFolder").value = "album"; h.get("musicFolder").listeners.get("change")(); assert.equal(h.get("musicTracks").children.length, 2); assert.equal(h.calls.length, 1);
});
await test("untrusted catalog URLs cannot direct playback outside the phone endpoint", () => {
  const h = harness(); const data = playlist(); data.tracks.push({ name: "unsafe", path: "../../secret.mp3", url: "https://evil.invalid/audio" }); data.tracks[0].url = "https://evil.invalid/audio";
  const tracks = h.api.musicTrackList(data); assert.equal(tracks.length, 3); h.ready(); h.api.state.music.tracks = tracks; h.api.selectMusicTrack("local/one.mp3"); assert.match(h.audio.src, /^\/api\/phone\/music\/audio\?path=/); assert.doesNotMatch(h.audio.src, /evil/);
});
const snapshot = (hash = "a") => ({ format: "codex-console-plan-snapshot", schemaVersion: 1, hash: hash.repeat(64), updatedAt: "2026-10-01T12:00:00Z", computerId: "fixture-pc", plan: plan().plan });
await test("QR fragment is removed before any request and automatically pairs remembered phone", async () => {
  const token = "q".repeat(43), h = harness(source, "http://codex-0123456789abcdef.local:8899/?tab=transfer#qrToken=" + token);
  assert.equal(h.calls.length, 0); assert.equal(h.replacedUrls.length, 1); assert.doesNotMatch(h.runtime.window.location.href, /qrToken|#/);
  h.respond({ paired: false }); h.respond({ paired: true, remembered: true }); h.respond(dashboard()); h.respond(snapshot()); await h.api.bootstrap(); await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(h.calls[1].url, "/api/phone/pair"); assert.deepEqual(JSON.parse(h.calls[1].options.body), { qrToken: token, remember: true, deviceName: "手机" });
  assert.equal(h.api.state.tab, "transfer"); assert.equal(h.get("pairScreen").hidden, true); assert.equal(h.get("transferPanel").hidden, false);
  assert.doesNotMatch(JSON.stringify([...h.saved]), /qrToken|qqqq/);
});
await test("invalid QR clears fragment and leaves PIN fallback without sending token", async () => {
  const h = harness(source, "http://192.168.1.2:8899/?tab=transfer#qrToken=short&token=extra");
  assert.equal(h.replacedUrls.length, 1); h.respond({ paired: false }); await h.api.bootstrap(); assert.equal(h.calls.length, 1); assert.equal(h.get("pairScreen").hidden, false); assert.match(h.get("pairNotice").textContent, /二维码无效/);
});
await test("already remembered device opens QR without consuming another device invitation", async () => {
  const h = harness(source, "http://codex-0123456789abcdef.local:8899/?tab=transfer#qrToken=" + "q".repeat(43));
  h.respond({ paired: true, remembered: true }); h.respond(dashboard()); h.respond(snapshot()); await h.api.bootstrap(); await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(h.calls.some(call => call.url === "/api/phone/pair"), false); assert.equal(h.api.state.tab, "transfer"); assert.equal(h.get("appScreen").hidden, false);
});
await test("PIN fallback carries user visible remember choice and device label", async () => {
  const h = harness(); h.get("pairRemember").checked = false; h.get("pairCode").value = "123456"; h.respond({ paired: true }); h.respond(dashboard()); h.respond(snapshot());
  await h.get("pairForm").listeners.get("submit")({ preventDefault() {} }); await new Promise(resolve => setTimeout(resolve, 0));
  assert.deepEqual(JSON.parse(h.calls[0].options.body), { code: "123456", remember: false, deviceName: "手机" });
});
await test("LAN task polling reads only actual tasks and keeps expanded groups on updates", async () => {
  const h = harness(); h.ready(); h.api.renderPlan(plan()); h.get("taskGroups").children[0].open = true; h.respond(snapshot()); await h.api.pollLivePlan();
  assert.equal(h.calls[0].url, "/api/phone/plan"); assert.equal(h.calls[0].options.method, "GET"); assert.equal(h.get("taskGroups").children[0].open, true); assert.match(h.get("planNotice").textContent, /已同步/); assert.ok(h.saved.has("codexPhone.planSnapshot.v1")); assert.equal(h.get("savePlanSnapshot").disabled, false);
  const updated = snapshot("b"); updated.plan.groups[0].items[0].done = true; updated.plan.groups[0].items.push({ id: "new", text: "电脑新增", done: false }); h.respond(updated); await h.api.pollLivePlan(); assert.match(h.get("taskGroups").textContent, /电脑新增/); assert.equal(h.get("taskGroups").children[0].open, true); assert.equal(h.all(h.get("taskGroups"), "input").length, 0); assert.equal(h.all(h.get("taskGroups"), "span").find(span => span.className === "task-status done").textContent, "✓");
  assert.ok([...h.timers.values()].some(timer => timer.delay === 5000)); assert.equal(h.calls.filter(call => /dashboard|document|music/.test(call.url)).length, 0);
});
await test("actual public task boards may have six groups while initial seeds never claim synchronized progress", () => {
  const h = harness(), payload = plan(); payload.actualDone = true; payload.label = "电脑已保存的计划与进度"; payload.plan.groups.push({ id: "extra-1", title: "五", items: [] }, { id: "extra-2", title: "六", items: [] }); h.api.renderPlan(payload); assert.equal(h.get("taskGroups").children.length, 6);
  payload.actualDone = false; h.api.renderPlan(payload); assert.match(h.get("planNotice").textContent, /实际进度暂未同步/); assert.doesNotMatch(h.get("planNotice").textContent, /已保存的计划与进度/);
});
await test("network interruption keeps last tasks with an explicit cached time while clearing private documents", async () => {
  const h = harness(); h.ready(); h.respond(snapshot()); await h.api.pollLivePlan(); h.get("readerContent").textContent = "PRIVATE DOCUMENT"; h.api.showOffline(new Error("Wi-Fi lost"));
  assert.equal(h.get("readerContent").textContent, ""); assert.equal(h.get("appScreen").hidden, true); assert.match(h.get("offlinePlanNotice").textContent, /上次同步/); assert.equal(h.get("offlineTaskGroups").children.length, 4); assert.equal(h.api.livePlan.timer, null);
  const another = harness(); another.saved.set("codexPhone.planSnapshot.v1", h.saved.get("codexPhone.planSnapshot.v1")); another.api.showOffline(new Error("offline")); assert.equal(another.get("offlineTaskGroups").children.length, 4); assert.equal(another.calls.length, 0);
});
await test("expired pairing removes cached tasks and a late response cannot repopulate them", async () => {
  const h = harness(); h.ready(); h.respond(snapshot()); await h.api.pollLivePlan(); const pending = defer(); h.answers.push(pending.promise); const poll = h.api.pollLivePlan(); h.api.showPair("expired"); pending.resolve(result(snapshot("b"))); await poll;
  assert.equal(h.api.livePlan.snapshot, null); assert.equal(h.saved.has("codexPhone.planSnapshot.v1"), false); assert.equal(h.get("taskGroups").textContent, ""); assert.equal(h.get("offlineTaskGroups").textContent, ""); assert.equal(h.api.livePlan.timer, null);
});
await test("background polling pauses and foreground resumes with status then a task-only update", async () => {
  const h = harness(); h.ready(); h.document.hidden = true; await h.api.pollLivePlan(); assert.equal(h.calls.length, 0); h.documentEvents.get("visibilitychange")(); assert.equal(h.api.livePlan.timer, null);
  h.respond({ paired: true }); h.respond(snapshot()); h.document.hidden = false; await h.documentEvents.get("visibilitychange")(); await new Promise(resolve => setTimeout(resolve, 0)); assert.deepEqual(h.calls.map(call => call.url), ["/api/phone/status", "/api/phone/plan"]);
});
await test("saved task JSON contains no session token or documents and malformed caches are ignored", async () => {
  const h = harness(); h.ready(); h.respond(snapshot()); await h.api.pollLivePlan(); let blob; h.runtime.URL = { createObjectURL(value) { blob = value; return "blob:fixture"; }, revokeObjectURL() {} }; h.api.savePlanSnapshot(); const data = JSON.parse(await blob.text()); assert.equal(data.format, "codex-console-plan-snapshot"); assert.equal(data.computerId, "fixture-pc"); assert.equal(data.plan.groups.length, 4); assert.equal(data.documents, undefined); assert.equal(data.token, undefined);
  const bad = harness(); bad.saved.set("codexPhone.planSnapshot.v1", JSON.stringify({ ...snapshot(), hash: "bad" })); bad.api.showOffline(new Error("offline")); assert.equal(bad.get("offlineTaskGroups").children.length, 0);
  const six = snapshot(); six.plan.groups.push({ id: "extra-1", title: "五", items: [] }, { id: "extra-2", title: "六", items: [] }); assert.equal(h.api.validateLivePlan(six).plan.groups.length, 6);
});
await test("connection failure is visible and an unchanged recovered plan clears the stale warning", async () => {
  const h = harness(); h.ready(); h.respond(snapshot()); await h.api.pollLivePlan();
  h.answers.push(Promise.reject(new TypeError("unavailable"))); await h.api.pollLivePlan();
  assert.equal(h.get("connectionLabel").textContent, "连接中断"); assert.equal(h.get("connectionLabel").dataset.connected, "false");
  assert.match(h.get("planNotice").textContent, /计划已保留/);
  h.respond(snapshot()); await h.api.pollLivePlan();
  assert.equal(h.get("connectionLabel").textContent, "已连接"); assert.equal(h.get("connectionLabel").dataset.connected, "true");
  assert.match(h.get("planNotice").textContent, /已同步/); assert.doesNotMatch(h.get("planNotice").textContent, /暂时连不上/);
});
await test("invalid task data never marks working transfer disconnected", async () => {
  const h = harness(); h.ready(); h.api.selectTab("transfer"); h.respond({}); await h.api.pollLivePlan();
  assert.equal(h.get("connectionLabel").textContent, "已连接"); assert.equal(h.get("connectionLabel").dataset.connected, "true");
  assert.match(h.get("planNotice").textContent, /其他功能仍可使用/); assert.equal(h.api.state.paired, true); assert.equal(h.get("transferPanel").hidden, false);
});
console.log(`PASS phone UI ${count} checks`);
