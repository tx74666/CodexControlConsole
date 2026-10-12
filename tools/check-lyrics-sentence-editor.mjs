// Actual Console sentence functions in an isolated DOM VM. No real audio, APIs, or user data.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";

const appPath = process.argv[2] || fileURLToPath(new URL("../app.js", import.meta.url));
const app = readFileSync(appPath, "utf8");
const css = readFileSync(join(dirname(appPath), "styles.css"), "utf8");
const copy = value => JSON.parse(JSON.stringify(value));
function functionSource(name) {
  const start = app.search(new RegExp(`(?:async )?function ${name}\\(`));
  assert.ok(start >= 0, `Missing actual Console function ${name}`);
  const tail = app.slice(start), next = /\n(?:async )?function \w+\(/.exec(tail.slice(1));
  return next ? tail.slice(0, next.index + 1) : tail;
}
function element(tag = "div") {
  const classes = new Set(), attributes = new Map(), properties = new Map();
  const listeners = new Map(); let ownText = "", html = "";
  const node = { tagName: tag.toUpperCase(), dataset: {}, classes, attributes, properties,
    children: [], hidden: false, disabled: false, value: "", innerHTML: "", textContent: "",
    classList: { add(...names) { names.forEach(n => classes.add(n)); }, remove(...names) { names.forEach(n => classes.delete(n)); },
      contains(name) { return classes.has(name); }, toggle(name, force) { const on = force ?? !classes.has(name); if (on) classes.add(name); else classes.delete(name); return on; } },
    style: { setProperty(k, v) { properties.set(k, String(v)); }, removeProperty(k) { properties.delete(k); } },
    setAttribute(k, v) { attributes.set(k, String(v)); }, getAttribute(k) { return attributes.get(k) ?? null; },
    removeAttribute(k) { attributes.delete(k); }, appendChild(child) { child.parentNode = node; node.children.push(child); return child; },
    prepend(child) { child.parentNode = node; node.children.unshift(child); }, insertBefore(child, before) { child.parentNode = node; const i = node.children.indexOf(before); node.children.splice(i < 0 ? node.children.length : i, 0, child); return child; },
    remove() { if (node.parentNode) node.parentNode.children = node.parentNode.children.filter(item => item !== node); },
    contains(child) { return node === child || node.children.some(item => item.contains?.(child)); },
    replaceChildren(...items) { node.children = []; items.forEach(item => node.appendChild(item)); },
    addEventListener(type, callback) { if (!listeners.has(type)) listeners.set(type, []); listeners.get(type).push(callback); },
    dispatch(type, event) { for (const callback of listeners.get(type) || []) callback(event); },
    focus() {}, scrollIntoView() {},
    querySelector(selector) { return node.querySelectorAll(selector)[0] || null; },
    querySelectorAll(selector) {
      const descendants = node.children.flatMap(child => [child, ...(child.querySelectorAll?.("*") || [])]);
      if (selector === "*") return descendants;
      if (selector === ".music-lyrics-line") return descendants.filter(child => child.classes.has("music-lyrics-line"));
      const index = selector.match(/^\[data-lyrics-index="(\d+)"\]$/)?.[1];
      if (index != null) return descendants.filter(child => child.dataset.lyricsIndex === index);
      if (selector.startsWith(".")) return descendants.filter(child => child.classes.has(selector.slice(1)));
      return [];
    }, closest() { return null; } };
  Object.defineProperty(node, "className", { get() { return [...classes].join(" "); }, set(value) { classes.clear(); String(value).split(/\s+/).filter(Boolean).forEach(c => classes.add(c)); } });
  Object.defineProperty(node, "textContent", { get() { return ownText + node.children.map(child => child.textContent).join(""); }, set(value) { ownText = String(value); node.children = []; } });
  Object.defineProperty(node, "innerHTML", { get() { return html; }, set(value) { html = String(value); node.children = []; ownText = ""; } });
  return node;
}
const tick = () => new Promise(resolve => setImmediate(resolve));
let checks = 0;
async function check(name, callback) { await callback(); checks += 1; console.log(`PASS ${name}`); }
const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-9, `${actual} != ${expected}`);

// Resolve custom-property dependencies from the actual desktop theme roots.
// This catches invalid-at-computed-value declarations without pretending the DOM VM renders CSS.
function desktopThemeProperties(source, theme) {
  const properties = new Map();
  const clean = source.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const rule of clean.matchAll(/:root(?:\[data-theme=(["'])(light|dark)\1\])?\s*\{([^{}]*)\}/g)) {
    if (rule[2] && rule[2] !== theme) continue;
    for (const declaration of rule[3].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
      properties.set(declaration[1], declaration[2].trim());
    }
  }
  assert.ok(properties.size, `Missing actual desktop ${theme} root variables`);
  return properties;
}
function resolveCssVariables(value, properties, stack = new Set()) {
  let result = "", offset = 0;
  for (let start = value.indexOf("var("); start >= 0; start = value.indexOf("var(", offset)) {
    result += value.slice(offset, start);
    let depth = 1, end = start + 4, comma = -1;
    for (; end < value.length && depth; end += 1) {
      const char = value[end];
      if (char === "(") depth += 1;
      else if (char === ")") depth -= 1;
      else if (char === "," && depth === 1 && comma < 0) comma = end;
    }
    if (depth) return null;
    const name = value.slice(start + 4, comma < 0 ? end - 1 : comma).trim();
    if (!/^--[\w-]+$/.test(name) || stack.has(name)) return null;
    const nextStack = new Set(stack); nextStack.add(name);
    let replacement = properties.has(name) ? resolveCssVariables(properties.get(name), properties, nextStack) : null;
    if (replacement == null && comma >= 0) replacement = resolveCssVariables(value.slice(comma + 1, end - 1).trim(), properties, stack);
    if (replacement == null || !replacement.trim()) return null;
    result += replacement; offset = end;
  }
  return result + value.slice(offset);
}

await check("sentence CSS variables resolve against actual light and dark desktop roots or usable fallbacks", () => {
  const start = css.indexOf(".lyrics-sentence-toolbar {");
  const end = css.indexOf(".now-playing-lyrics-panel .music-lyrics-line {", start);
  assert.ok(start >= 0 && end > start, "Missing actual sentence style block");
  const declarations = [...css.slice(start, end).matchAll(/\{([^{}]*)\}/g)]
    .flatMap(rule => [...rule[1].matchAll(/(?:^|;)\s*([\w-]+)\s*:\s*([^;]*)(?=;|$)/g)])
    .filter(match => match[2].includes("var("));
  assert.ok(declarations.length >= 6, "Sentence declarations must be checked, not an empty selector range");
  for (const theme of ["light", "dark"]) {
    const properties = desktopThemeProperties(css, theme);
    for (const [, property, value] of declarations) {
      assert.notEqual(resolveCssVariables(value, properties), null, `${theme} sentence ${property} has an unresolved CSS variable: ${value}`);
    }
    // Negative controls reproduce the original invisible cursor and reject an unusable fallback.
    assert.equal(resolveCssVariables("var(--undefined-sentence-accent)", properties), null);
    assert.equal(resolveCssVariables("var(--undefined-sentence-accent, var(--also-undefined))", properties), null);
    assert.equal(resolveCssVariables("var(--undefined-sentence-accent, rgba(12, 34, 56, .8))", properties), "rgba(12, 34, 56, .8)");
    assert.equal(resolveCssVariables("var(--undefined-sentence-accent, var(--text))", properties), properties.get("--text"));
  }
});

// Deliberately wrong old times and a caption rest: calibration must follow audio and line order.
const fixtureLines = () => [{ text: "First, unchanged sentence.", time: 70 }, { text: "", time: 71, rest: true },
  { text: "Second sentence?", time: 72 }, { text: "第三句！", time: 73 }];
const sentenceNames = [...app.matchAll(/(?:async )?function (\w*[Ss]entence\w*)\(/g)].map(match => match[1]);
const actualNames = [...new Set([...sentenceNames, "lyricsLineText", "lyricsAnalysisLine", "manualLyricMarksForLine",
  "musicLyricMarkRole", "musicLyricMarkStorageKey", "musicLyricMarkComparable", "sortMusicLyricMarks",
  "mergePendingMusicLyricMarksIntoAnalysis", "stagePendingMusicLyricMark", "sessionLyricMarksForLine",
  "flushPendingMusicLyricMarks", "musicLyricsCachePath", "musicLyricsRequestKey", "audioIsTrack",
  "musicLyricsCacheType", "getMusicLyricsCacheEntry", "setMusicLyricsCacheEntry", "fetchParsedLyricsForTrack",
  "fetchLyricsAnalysisForTrack", "ensureLyricsAnalysisWarm", "loadLyricsAnalysisForTrack",
  "formatLyricsEditorTime", "parseLyricsEditorTime", "lyricsTrustedAlignment", "lyricsLineDisplayStartTime",
  "activeLyricsIndexAt", "lyricsLineEndTime", "applyAudioCurrentTime", "seekToLyricsLine", "lyricsAnimationShouldRun",
  "syncManualLyricMarkClasses", "clearLyricsWordPlaybackStyles", "setLyricsLineTone", "clearLyricsLineTone",
  "updateLyricsLineTone", "setLyricsLineVisualState", "syncLyricsLineVisualStates", "updateLyricsProgress",
  "renderLyricsPanel", "applyLyricsAnalysisToActiveTrack"])];
const actualFunctions = `const sentenceLyricsPendingStorageKey = "codexControl.sentenceLyricPending.v1";
  ${actualNames.map(functionSource).join("\n")}`;

function harness({ lines = fixtureLines(), marks = [], synced = true, language = "en" } = {}) {
  const nodes = new Map(), requests = [], reads = [], cachedWrites = [], messages = [];
  const storage = new Map();
  let persisted = copy(marks);
  const get = id => { if (!nodes.has(id)) { const node = element(); node.id = id; node.isConnected = true; nodes.set(id, node); } return nodes.get(id); };
  const list = get("nowPlayingLyricsList");
  lines.forEach((line, index) => { const node = element("button"); node.className = "music-lyrics-line";
    node.dataset.lyricsIndex = String(index); node.textContent = line.text; list.appendChild(node); });
  const selected = { path: "fixture.mp3", url: "fixture.mp3", lyricsUrl: `/fixture.${language}.lrc`, lyricsLanguage: language };
  let stamp = 0;
  const runtime = {
    console, URL, URLSearchParams, Blob, Date, Map, Set, Promise,
    hasMusic: true, selectedTrackPath: selected.path, musicLyricsTrackPath: selected.path,
    musicLyricsLines: copy(lines), musicLyricsSynced: synced, musicLyricsLoadToken: 3, musicLyricsStatus: "",
    musicLyricsActiveIndex: -1, heldLyricsActiveIndex: -1, heldLyricsActiveUntil: 0,
    musicLyricsAnalysis: { ok: true, path: selected.path, lyricsLanguage: language,
      lines: lines.map((line, index) => ({ index, text: line.text, time: line.time, analysisTime: line.time,
        wordTimes: [0, .2], wordSpans: [{ word: line.text, start: 0, end: .2 }] })), manualMarks: copy(marks) },
    sessionMusicLyricMarks: new Map(), pendingMusicLyricMarks: new Map(), musicLyricMarksFlushPromise: null,
    musicLyricsCache: new Map(), musicLyricsTextPromises: new Map(), musicLyricsAnalysisPromises: new Map(),
    sentenceLyricsCalibration: null, sentenceLyricsOperation: null, sentenceLyricsBusy: false, sentenceLyricsSaveError: "",
    sentenceLyricsMarksLoadedToken: -1, sentenceLyricsMarksLoadedSource: "",
    smoothValueAnimations: new Map(), pendingSeekRatio: null, userSeeking: false, musicLyricsAnimationFrame: 0,
    activeLyricsTimingTarget: null, lyricsTimingWaveDrag: null, suppressLyricsLineClickUntil: 0,
    clamp: (v, min, max) => Math.min(max, Math.max(min, v)), audioDuration: () => 100,
    performance: { now: () => 10 }, navigator: {},
    document: { body: element("body"), documentElement: element("html"), hidden: false,
      createElement: element, createTextNode(value) { const node = element("text"); node.textContent = value; return node; },
      getElementById: get, activeElement: null },
    window: { location: { href: "http://fixture/" }, setTimeout() { return ++stamp; }, clearTimeout() {},
      requestAnimationFrame() { return ++stamp; }, cancelAnimationFrame() {} },
    localStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, String(value)), removeItem: key => storage.delete(key) },
    selectedTrack: () => selected, musicTrackWithPreferredLyrics: item => item,
    normalizeMusicTrackPathValue: value => String(value || ""), normalizeLyricsLanguageCode: value => String(value || "").toLowerCase(),
    isModuleForeground: () => true,
    text: (key, ...values) => [key, ...values].join(":"),
    escapeHtml: value => String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"),
    setLyricsMarkStatus(message) { messages.push(message); },
    formatDuration: String, formatLyricsEditorTime: value => String(value), parseLyricsEditorTime: value => Number(value),
    closeLyricsTimingEditor() { get("lyricsTimingEditor").hidden = true; },
    detachLyricsTimingEditorFromList() {}, applyLyricsPanelHeight() {}, musicLyricsLookupPath: "",
    stopLyricsAnimationLoop() {}, syncLyricsAnimationLoop() {}, syncLyricsTimingSelection() {},
    syncLyricsLineVisualStates() {}, updateLyricsLineTone() {}, updateLyricsProgress() {}, updateTrackProgress() {},
    updateLyricsTimingWavePlayhead() {}, renderLyricsPanel() {}, scheduleSelectedLyricsPreload() {},
    setMusicLyricsCacheEntry(item, patch) { cachedWrites.push({ item: copy(item), patch: copy(patch) }); },
    lyricsLineAnalysisStartTime: index => Number(runtime.musicLyricsLines[index]?.time),
    manualLyricLineStartTime: () => NaN, manualLyricLineEndTime: () => NaN,
    lyricsLineWordStartTime: index => Number(runtime.musicLyricsLines[index]?.time),
    recordTrackSeekChange() {}, currentAudioSeekRatio: () => 0, trackSeekRatio: () => 0,
    postJson(url, payload) { return new Promise((resolve, reject) => requests.push({ url, payload: copy(payload), resolve, reject })); },
    fetch(url, options) { return new Promise((resolve, reject) => reads.push({ url, options: copy(options), resolve, reject })); },
    els: {}
  };
  for (const id of ["nowPlayingLyricsList", "nowPlayingLyricsPanel", "nowPlayingLyricsStatus", "lyricsTimingEditor",
    "lyricsSentenceControls", "lyricsSentenceToggle", "lyricsSentenceRail", "lyricsSentenceRetry", "lyricsSentenceStatus",
    "lyricsSentenceTarget", "lyricsSentenceMark", "lyricsSentenceRole", "lyricsSentenceTime", "lyricsSentenceApply",
    "lyricsSentenceRemove", "lyricsSentenceCursor", "lyricsSentenceClock", "trackSeek", "trackCurrentTime", "trackDuration", "trackVolume"]) runtime.els[id] = get(id);
  const ticks = element("span"); ticks.className = "lyrics-sentence-ticks"; runtime.els.lyricsSentenceRail.appendChild(ticks);
  runtime.els.lyricsTimingEditor.hidden = true;
  runtime.els.audioPlayer = { currentTime: 0, paused: false, ended: false, src: "http://fixture/fixture.mp3", load() { throw new Error("Unexpected source reload"); } };
  runInNewContext(`${actualFunctions}\nglobalThis.api = { ${actualNames.join(", ")} };`, runtime);
  const cacheSetter = runtime.api.setMusicLyricsCacheEntry;
  runtime.setMusicLyricsCacheEntry = (item, patch) => { cachedWrites.push({ item: copy(item), patch: copy(patch) }); return cacheSetter(item, patch); };
  const ready = () => { runtime.sentenceLyricsMarksLoadedToken = runtime.musicLyricsLoadToken; runtime.sentenceLyricsMarksLoadedSource = runtime.api.sentenceLyricsSource(); };
  ready();
  return { runtime, api: runtime.api, requests, reads, messages, cachedWrites, nodes, selected, storage,
    ready,
    body: runtime.document.body, time(value) { runtime.els.audioPlayer.currentTime = value; },
    key(patch = {}) { let prevented = false; return { key: "Insert", code: "Insert", target: runtime.document.body,
      repeat: false, isComposing: false, defaultPrevented: false, altKey: false, ctrlKey: false, metaKey: false, shiftKey: false,
      preventDefault() { prevented = true; }, get prevented() { return prevented; }, ...patch }; },
    replySuccess(request = requests.at(-1)) {
      for (const mark of request.payload.marks || []) {
        const same = old => old.kind === mark.kind && old.lineIndex === mark.lineIndex && old.role === mark.role
          && String(old.lyricsLanguage || "") === String(mark.lyricsLanguage || "");
        persisted = persisted.filter(old => !same(old));
        if (mark.action !== "remove") persisted.push({ ...mark });
      }
      request.resolve({ ok: true, marksByPath: { [request.payload.marks[0].path]: copy(persisted) } });
    },
    replyRead(marks, request = reads.at(-1), extra = {}) {
      request.resolve({ ok: true, status: 200, json: async () => ({ ok: true, path: selected.path, lyricsLanguage: selected.lyricsLanguage, marks: copy(marks), ...extra }) });
    }
  };
}

async function markAndAcknowledge(h, time) {
  h.time(time); assert.equal(h.api.markSentenceLyricsNow(), true); await tick();
  const request = h.requests.at(-1); assert.ok(request, "actual mark must request persistence");
  h.replySuccess(request); await tick(); await tick(); return request;
}
async function onsetAndAcknowledge(h, time) {
  h.runtime.sentenceLyricsCalibration.role = "start";
  h.runtime.els.lyricsSentenceTime.value = String(time);
  assert.equal(h.api.editSentenceLyricsPoint(), true);
  const request = h.requests.at(-1); h.replySuccess(request); await tick(); await tick();
  h.runtime.sentenceLyricsCalibration.role = "end";
  return request;
}
const sentenceMark = (index, role, time, language = "en", lineText = fixtureLines()[index]?.text) => ({
  kind: "sentence", path: "fixture.mp3", lineIndex: index, role, time, lyricsLanguage: language, lineText
});

await check("arming selects a sentence cursor independently of incorrect LRC and without rewriting text", () => {
  const h = harness(), original = copy(h.runtime.musicLyricsLines);
  h.time(73); h.api.setSentenceLyricsCalibration(true);
  assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 0);
  assert.equal(h.runtime.sentenceLyricsCalibration.role, "end");
  assert.deepEqual(copy(h.runtime.musicLyricsLines), original);
  assert.equal(h.requests.length, 0);
});
await check("first Insert closes the sentence with implicit zero onset and immediately advances past rest rows", async () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true);
  const request = await markAndAcknowledge(h, 4.567);
  assert.deepEqual(request.payload.marks.map(mark => [mark.lineIndex, mark.role, mark.time]), [[0, "start", 0], [0, "end", 4.567], [2, "start", 4.567]]);
  assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 2);
  assert.equal(h.runtime.sentenceLyricsCalibration.role, "end");
  assert.equal(h.api.activeLyricsIndexAt(0), 0);
  assert.equal(h.api.activeLyricsIndexAt(4.566), 0);
  assert.equal(h.api.activeLyricsIndexAt(4.567), 2);
  assert.equal(h.api.activeLyricsIndexAt(72), 2, "uncalibrated old LRC cannot prematurely take over");
});
await check("final end closes the last sentence and disarms the cursor", async () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true);
  for (const time of [4, 8]) await markAndAcknowledge(h, time);
  const request = await markAndAcknowledge(h, 12);
  assert.deepEqual(request.payload.marks.map(mark => [mark.lineIndex, mark.role]), [[3, "end"]]);
  assert.equal(h.runtime.sentenceLyricsCalibration, null);
  assert.equal(h.api.activeLyricsIndexAt(11.999), 3);
  assert.equal(h.api.activeLyricsIndexAt(12), -1);
});
await check("existing first onset is preserved while Insert closes the first sentence without another onset tap", async () => {
  const h = harness({ marks: [sentenceMark(0, "start", 2)] }); h.api.setSentenceLyricsCalibration(true);
  const request = await markAndAcknowledge(h, 4);
  assert.deepEqual(request.payload.marks.map(mark => [mark.lineIndex, mark.role, mark.time]), [[0, "end", 4], [2, "start", 4]]);
  near(h.api.sentenceLyricPointTime(0, "start"), 2);
  assert.equal(h.api.activeLyricsIndexAt(1.99), -1);
});
await check("consecutive sentence ends advance immediately and drain serially behind a slow acknowledgement", async () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true); h.api.renderLyricsPanel();
  h.time(4); assert.equal(h.api.markSentenceLyricsNow(), true);
  assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 2);
  assert.equal(h.runtime.musicLyricsActiveIndex, 2);
  assert.ok(h.runtime.els.nowPlayingLyricsList.querySelector('[data-lyrics-index="2"]').classes.has("active"));
  h.time(8); assert.equal(h.api.markSentenceLyricsNow(), true);
  assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 3);
  h.time(12); assert.equal(h.api.markSentenceLyricsNow(), true);
  assert.equal(h.runtime.sentenceLyricsCalibration, null);
  assert.equal(h.requests.length, 1, "only one request is in flight");
  assert.equal(h.runtime.pendingMusicLyricMarks.size, 6);
  h.replySuccess(h.requests[0]); await tick(); await tick();
  assert.equal(h.requests.length, 2);
  assert.deepEqual(h.requests[1].payload.marks.map(mark => [mark.lineIndex, mark.role, mark.time]),
    [[2, "end", 8], [3, "start", 8], [3, "end", 12]]);
  assert.equal(h.runtime.sentenceLyricsCalibration, null, "late receipt does not reopen a completed cursor");
  h.replySuccess(h.requests[1]); await tick(); await tick();
  assert.equal(h.runtime.pendingMusicLyricMarks.size, 0); assert.equal(h.runtime.sentenceLyricsOperation, null);
  assert.equal(h.storage.size, 0); assert.equal(h.api.activeLyricsIndexAt(8), 3); assert.equal(h.api.activeLyricsIndexAt(12), -1);
});
await check("queued sentence save failure retries its original times without undoing immediate cursor advancement", async () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true);
  h.time(4); h.api.markSentenceLyricsNow(); h.time(8); h.api.markSentenceLyricsNow();
  h.replySuccess(h.requests[0]); await tick(); await tick();
  const failed = h.requests[1]; failed.reject(new Error("queued synthetic disk failure")); await tick(); await tick();
  assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 3);
  assert.equal(h.runtime.pendingMusicLyricMarks.size, 2); assert.match(h.runtime.sentenceLyricsSaveError, /queued synthetic disk failure/);
  h.time(90); assert.equal(h.api.markSentenceLyricsNow(), false, "failed pending work must be retried, not retimed");
  const retry = h.api.saveSentenceLyricsOperation(h.runtime.sentenceLyricsOperation);
  assert.deepEqual(h.requests.at(-1).payload, failed.payload);
  h.replySuccess(); assert.equal(await retry, true);
  assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 3);
  near(h.api.sentenceLyricPointTime(2, "end"), 8); assert.equal(h.runtime.pendingMusicLyricMarks.size, 0);
});
await check("a local journal failure keeps the cursor until the same end point can be journaled and retried", async () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true);
  const store = h.runtime.localStorage.setItem;
  h.runtime.localStorage.setItem = () => { throw new Error("synthetic full local storage"); };
  h.time(4); assert.equal(h.api.markSentenceLyricsNow(), false);
  assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 0); assert.equal(h.requests.length, 0);
  assert.equal(h.runtime.pendingMusicLyricMarks.size, 3); assert.match(h.runtime.sentenceLyricsSaveError, /JournalFailed/);
  h.runtime.localStorage.setItem = store; h.time(90);
  const retry = h.api.saveSentenceLyricsOperation(h.runtime.sentenceLyricsOperation);
  assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 2);
  assert.ok(h.runtime.els.nowPlayingLyricsList.querySelector('[data-lyrics-index="2"]').classes.has("sentence-calibration-target"), "Retry paints its advanced target before network acknowledgement");
  assert.deepEqual(h.requests[0].payload.marks.map(mark => [mark.lineIndex, mark.role, mark.time]),
    [[0, "start", 0], [0, "end", 4], [2, "start", 4]]);
  h.replySuccess(); assert.equal(await retry, true);
  assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 2);
});
await check("middle sentence marking derives only a known preceding end and never guesses an unmarked gap", async () => {
  const h = harness({ marks: [sentenceMark(0, "start", 0), sentenceMark(0, "end", 4)] });
  h.api.setSentenceLyricsCalibration(true, 2);
  const request = await markAndAcknowledge(h, 8);
  assert.deepEqual(request.payload.marks.map(mark => [mark.lineIndex, mark.role, mark.time]), [[2, "start", 4], [2, "end", 8], [3, "start", 8]]);
  const gap = harness(); gap.api.setSentenceLyricsCalibration(true, 2); gap.time(8);
  assert.equal(gap.api.markSentenceLyricsNow(), false); assert.equal(gap.requests.length, 0);
});
await check("Insert remains an end-only action when Start is selected for precise correction", async () => {
  const h = harness({ marks: [sentenceMark(0, "start", 2)] }); h.api.setSentenceLyricsCalibration(true);
  h.runtime.sentenceLyricsCalibration.role = "start";
  const request = await markAndAcknowledge(h, 4);
  assert.deepEqual(request.payload.marks.map(mark => [mark.lineIndex, mark.role, mark.time]), [[0, "end", 4], [2, "start", 4]]);
  near(h.api.sentenceLyricPointTime(0, "start"), 2); assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 2);
});
await check("a journal failure during an in-flight save holds the newer cursor and resumes once protected", async () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true); h.time(4); h.api.markSentenceLyricsNow();
  const store = h.runtime.localStorage.setItem;
  h.runtime.localStorage.setItem = () => { throw new Error("synthetic later journal failure"); };
  h.time(8); assert.equal(h.api.markSentenceLyricsNow(), false);
  assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 2);
  h.replySuccess(h.requests[0]); await tick(); await tick();
  assert.equal(h.requests.length, 1); assert.equal(h.runtime.sentenceLyricsBusy, false);
  assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 2);
  h.runtime.localStorage.setItem = store;
  const retry = h.api.saveSentenceLyricsOperation(h.runtime.sentenceLyricsOperation);
  assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 3);
  assert.deepEqual(h.requests.at(-1).payload.marks.map(mark => [mark.lineIndex, mark.role, mark.time]), [[2, "end", 8], [3, "start", 8]]);
  h.replySuccess(); assert.equal(await retry, true); assert.equal(h.runtime.sentenceLyricsSaveError, "");
});
await check("old sentence word boundaries and word spans survive sentence saves", async () => {
  const legacy = { kind: "boundary", path: "fixture.mp3", lineIndex: 0, boundaryIndex: 1, role: "end", time: 80, note: "preserve" };
  const h = harness({ marks: [legacy] }), original = copy(h.runtime.musicLyricsAnalysis.lines);
  h.api.setSentenceLyricsCalibration(true); await onsetAndAcknowledge(h, 1);
  assert.deepEqual(copy(h.runtime.musicLyricsAnalysis.lines), original);
  assert.deepEqual(copy(h.runtime.musicLyricsAnalysis.manualMarks.find(mark => mark.kind === "boundary")), legacy);
  assert.equal(h.api.activeLyricsIndexAt(2), 0, "legacy words cannot choose the calibration cursor");
});
await check("plaintext lyrics with no LRC timestamps support manual sentence playback and paused seek", async () => {
  const lines = fixtureLines().map(line => ({ ...line, time: null }));
  const h = harness({ lines, synced: false }); h.api.setSentenceLyricsCalibration(true);
  await onsetAndAcknowledge(h, 1); await markAndAcknowledge(h, 4);
  h.runtime.els.audioPlayer.paused = true;
  h.api.seekToLyricsLine(0); near(h.runtime.els.audioPlayer.currentTime, 1);
  assert.equal(h.runtime.els.audioPlayer.paused, true);
  h.runtime.els.audioPlayer.paused = false;
  assert.equal(h.api.lyricsAnimationShouldRun(), true);
  h.api.updateLyricsProgress(4); assert.equal(h.runtime.musicLyricsActiveIndex, 2);
});
await check("Insert ignores repeats, IME, modifiers, editable targets, and inactive calibration", () => {
  const h = harness(); assert.equal(h.api.handleSentenceLyricsMarkKeydown(h.key()), false);
  h.api.setSentenceLyricsCalibration(true);
  const cases = [{ repeat: true }, { isComposing: true }, { keyCode: 229 }, { defaultPrevented: true },
    { altKey: true }, { ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { key: "End" },
    { target: { isContentEditable: true } }, { target: { closest: () => ({}) } }];
  for (const patch of cases) { const event = h.key(patch); assert.equal(h.api.handleSentenceLyricsMarkKeydown(event), false); assert.equal(event.prevented, false); }
  h.runtime.document.hidden = true; assert.equal(h.api.handleSentenceLyricsMarkKeydown(h.key()), false);
  h.runtime.document.hidden = false; h.runtime.isModuleForeground = () => false;
  assert.equal(h.api.handleSentenceLyricsMarkKeydown(h.key()), false);
  assert.equal(h.requests.length, 0);
});
await check("a held key or repeated click cannot submit the same operation twice", async () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true); h.time(1);
  const first = h.key(); assert.equal(h.api.handleSentenceLyricsMarkKeydown(first), true); assert.equal(first.prevented, true);
  assert.equal(h.api.markSentenceLyricsNow(), false); assert.equal(h.api.handleSentenceLyricsMarkKeydown(h.key({ repeat: true })), false);
  assert.equal(h.requests.length, 1);
  assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 2, "cursor advances before acknowledgement");
  assert.equal(h.api.activeLyricsIndexAt(1), 2, "whole next line uses the staged sentence timeline immediately");
  h.replySuccess(); await tick(); await tick();
  assert.equal(h.runtime.sentenceLyricsCalibration.role, "end");
});
await check("pause and backward seek keep the independent cursor; an end before onset is rejected", async () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true); await onsetAndAcknowledge(h, 1);
  const target = h.runtime.sentenceLyricsCalibration; h.runtime.els.audioPlayer.paused = true;
  h.api.seekToLyricsLine(2); assert.equal(h.runtime.sentenceLyricsCalibration, target);
  h.time(.5); assert.equal(h.api.markSentenceLyricsNow(), false); assert.equal(h.requests.length, 1);
  assert.match(h.runtime.sentenceLyricsSaveError, /OrderInvalid/);
  await markAndAcknowledge(h, 4); assert.equal(h.runtime.els.audioPlayer.paused, true);
  assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 2);
});
await check("saved endpoint correction updates its paired boundary with compare-and-set and no cursor advance", async () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true);
  await onsetAndAcknowledge(h, 1); await markAndAcknowledge(h, 4);
  h.api.setSentenceLyricsCalibration(true, 2); h.runtime.sentenceLyricsCalibration.role = "start";
  h.runtime.els.lyricsSentenceTime.value = "0:03.500";
  assert.equal(h.api.editSentenceLyricsPoint(), true);
  const request = h.requests.at(-1);
  assert.deepEqual(request.payload.marks.map(mark => [mark.lineIndex, mark.role, mark.time, mark.expectedTime]),
    [[2, "start", 3.5, 4], [0, "end", 3.5, 4]]);
  h.replySuccess(); await tick(); await tick();
  assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 2); assert.equal(h.runtime.sentenceLyricsCalibration.role, "start");
  assert.equal(h.api.activeLyricsIndexAt(3.499), 0); assert.equal(h.api.activeLyricsIndexAt(3.5), 2);
});
await check("point removal deletes only the linked sentence endpoints while preserving words and text", async () => {
  const legacy = { kind: "boundary", path: "fixture.mp3", lineIndex: 0, boundaryIndex: 1, role: "end", time: 80 };
  const h = harness({ marks: [legacy] }); h.api.setSentenceLyricsCalibration(true);
  await onsetAndAcknowledge(h, 1); await markAndAcknowledge(h, 4);
  const textBefore = copy(h.runtime.musicLyricsLines), spansBefore = copy(h.runtime.musicLyricsAnalysis.lines);
  h.api.setSentenceLyricsCalibration(true, 0); h.runtime.sentenceLyricsCalibration.role = "end";
  assert.equal(h.api.removeSentenceLyricsPoint(), true); const request = h.requests.at(-1);
  assert.deepEqual(request.payload.marks.map(mark => [mark.lineIndex, mark.role, mark.action, mark.expectedTime]),
    [[0, "end", "remove", 4], [2, "start", "remove", 4]]);
  h.replySuccess(); await tick(); await tick();
  assert.ok(Number.isNaN(h.api.sentenceLyricPointTime(0, "end"))); assert.ok(Number.isNaN(h.api.sentenceLyricPointTime(2, "start")));
  near(h.api.sentenceLyricPointTime(0, "start"), 1);
  assert.deepEqual(copy(h.runtime.musicLyricsLines), textBefore); assert.deepEqual(copy(h.runtime.musicLyricsAnalysis.lines), spansBefore);
  assert.deepEqual(copy(h.runtime.musicLyricsAnalysis.manualMarks.find(mark => mark.kind === "boundary")), legacy);
});
await check("failed persistence retains the exact point and advanced cursor, and Retry acknowledges the original audio time", async () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true); h.time(1.234);
  assert.equal(h.api.markSentenceLyricsNow(), true); const first = h.requests.at(-1);
  first.reject(new Error("synthetic disk failure")); await tick(); await tick();
  assert.equal(h.runtime.sentenceLyricsCalibration.role, "end");
  assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 2);
  assert.equal(h.runtime.pendingMusicLyricMarks.size, 3); assert.equal(h.runtime.sentenceLyricsBusy, false);
  assert.match(h.runtime.sentenceLyricsSaveError, /synthetic disk failure/);
  assert.equal(h.runtime.els.lyricsSentenceRetry.hidden, false);
  assert.equal(h.api.markSentenceLyricsNow(), false, "do not replace the failed point with a later clock value");
  h.time(9); const retry = h.api.saveSentenceLyricsOperation(h.runtime.sentenceLyricsOperation);
  assert.deepEqual(h.requests.at(-1).payload, first.payload);
  h.replySuccess(); assert.equal(await retry, true);
  assert.equal(h.runtime.sentenceLyricsCalibration.role, "end");
  near(h.api.sentenceLyricPointTime(0, "end"), 1.234);
  assert.equal(h.runtime.pendingMusicLyricMarks.size, 0); assert.equal(h.storage.size, 0);
});
await check("pending journal survives reload and beacon queueing is never reported as persistence", async () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true); h.time(1);
  assert.equal(h.api.markSentenceLyricsNow(), true);
  h.requests.at(-1).reject(new Error("offline")); await tick(); await tick();
  const journal = h.storage.get("codexControl.sentenceLyricPending.v1"); assert.ok(journal);
  const restored = harness(); restored.storage.set("codexControl.sentenceLyricPending.v1", journal);
  restored.api.restorePendingSentenceLyricsMarks(); assert.equal(restored.runtime.pendingMusicLyricMarks.size, 3);
  near(restored.api.sentenceLyricPointTime(0, "start"), 0);
  restored.runtime.navigator.sendBeacon = () => true;
  const result = await restored.api.flushPendingMusicLyricMarks({ beacon: true });
  assert.equal(result.ok, false); assert.equal(result.pending, true);
  assert.equal(restored.runtime.pendingMusicLyricMarks.size, 3);
  assert.ok(restored.storage.has("codexControl.sentenceLyricPending.v1"));
});
await check("stale song acknowledgement cannot advance a new cursor or replace its analysis", async () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true); h.time(1); h.api.markSentenceLyricsNow();
  const request = h.requests.at(-1);
  h.selected.path = "other.mp3"; h.runtime.selectedTrackPath = "other.mp3"; h.runtime.musicLyricsTrackPath = "other.mp3";
  h.runtime.musicLyricsLoadToken += 1; h.runtime.musicLyricsAnalysis = { ok: true, path: "other.mp3", lines: [], manualMarks: [] };
  const before = copy(h.runtime.musicLyricsAnalysis); h.ready(); h.api.setSentenceLyricsCalibration(true);
  h.replySuccess(request); await tick(); await tick();
  assert.deepEqual(copy(h.runtime.musicLyricsAnalysis), before);
  assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 0); assert.equal(h.runtime.sentenceLyricsCalibration.role, "end");
  assert.equal(h.cachedWrites.length, 0);
});
await check("stale language acknowledgement cannot overwrite the active translation or its calibration", async () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true); h.time(1); h.api.markSentenceLyricsNow();
  const request = h.requests.at(-1);
  h.selected.lyricsLanguage = "zh"; h.selected.lyricsUrl = "/fixture.zh.lrc"; h.runtime.musicLyricsLoadToken += 1;
  h.runtime.musicLyricsAnalysis = { ok: true, path: "fixture.mp3", lyricsLanguage: "zh", lines: [], manualMarks: [] };
  const before = copy(h.runtime.musicLyricsAnalysis); h.ready(); h.api.setSentenceLyricsCalibration(true);
  h.replySuccess(request); await tick(); await tick();
  assert.deepEqual(copy(h.runtime.musicLyricsAnalysis), before);
  assert.equal(h.runtime.sentenceLyricsCalibration.role, "end"); assert.equal(h.cachedWrites.length, 0);
  assert.ok(Number.isNaN(h.api.sentenceLyricPointTime(0, "start")));
});
await check("sentence identity rejects another translation and edited line text at the same ordinal", () => {
  const h = harness({ marks: [sentenceMark(0, "start", 1, "zh"), sentenceMark(2, "start", 4, "en", "Different sentence")] });
  assert.ok(Number.isNaN(h.api.sentenceLyricPointTime(0, "start"))); assert.ok(Number.isNaN(h.api.sentenceLyricPointTime(2, "start")));
  assert.equal(h.api.hasSentenceLyricTimeline(), false);
  const old = { ...h.selected, lyricsLanguage: "zh", lyricsUrl: "/fixture.zh.lrc" };
  assert.equal(h.api.applyLyricsAnalysisToActiveTrack(old, { ok: true, path: "fixture.mp3", manualMarks: [] }), false);
});
await check("real lyric rendering uses one text span per sentence and time markers, never a word graph", () => {
  const h = harness({ marks: [sentenceMark(0, "start", 1), sentenceMark(0, "end", 4), sentenceMark(2, "start", 4)] });
  h.api.renderLyricsPanel();
  const rows = h.runtime.els.nowPlayingLyricsList.querySelectorAll(".music-lyrics-line");
  assert.equal(rows.length, fixtureLines().length);
  for (let index = 0; index < rows.length; index += 1) {
    assert.equal(rows[index].querySelector(".lyric-sentence-text").textContent, fixtureLines()[index].text);
    assert.equal(rows[index].querySelectorAll(".lyric-word").length, 0);
    assert.equal(rows[index].querySelectorAll(".lyrics-wave-editor").length, 0);
  }
  assert.equal(rows[0].querySelectorAll(".lyric-sentence-point").length, 2);
  h.api.updateLyricsProgress(2);
  assert.ok(rows[0].classes.has("active")); assert.equal(rows[0].properties.get("--line-opacity"), "1.000");
  assert.equal(rows[2].properties.get("--line-opacity"), "0.540");
  assert.equal(h.runtime.els.lyricsTimingEditor.hidden, true);
  assert.ok(!/--word-(?:fill|progress)|\.word-(?:current|sung|wave-current)\b/.test(css));
});
await check("time cursor and red point locations derive only from audio seconds", () => {
  const h = harness({ marks: [sentenceMark(0, "start", 10), sentenceMark(0, "end", 25)] });
  h.api.setSentenceLyricsCalibration(true); h.api.updateSentenceLyricsCursor(30);
  assert.equal(h.runtime.els.lyricsSentenceCursor.style.left, "30%");
  assert.equal(h.runtime.els.lyricsSentenceClock.textContent, "0:30.000");
  const ticks = h.runtime.els.lyricsSentenceRail.querySelectorAll(".lyrics-sentence-tick");
  assert.deepEqual(ticks.map(tick => tick.style.left), ["10%", "25%"]);
});
await check("fresh cheap marks read enables plaintext calibration and reuses saved sentence timings without analysis", async () => {
  const h = harness({ lines: fixtureLines().map(line => ({ ...line, time: null })), synced: false });
  h.runtime.sentenceLyricsMarksLoadedToken = -1; h.runtime.musicLyricsAnalysis = null;
  h.api.setSentenceLyricsCalibration(true); assert.equal(h.runtime.sentenceLyricsCalibration, null);
  h.api.renderSentenceLyricsControls(); assert.equal(h.runtime.els.lyricsSentenceToggle.disabled, true);
  const loading = h.api.loadSentenceLyricsMarksForTrack(h.selected, h.runtime.musicLyricsLoadToken);
  assert.equal(h.reads.length, 1); assert.match(h.reads[0].url, /^\/api\/music\/lyrics\/marks\?/);
  assert.match(h.reads[0].url, /language=en/); assert.equal(h.reads[0].options.cache, "no-store");
  h.replyRead([sentenceMark(0, "start", 1), sentenceMark(0, "end", 4), sentenceMark(2, "start", 4)]);
  await loading;
  assert.equal(h.api.sentenceLyricsMarksReady(), true); assert.equal(h.api.activeLyricsIndexAt(4), 2);
  h.api.setSentenceLyricsCalibration(true); assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 2);
  assert.equal(h.reads.length, 1, "no audio/analysis API requested");
});
await check("late marks GET for a different language cannot enable or replace the active translation", async () => {
  const h = harness(), old = { ...h.selected };
  h.runtime.sentenceLyricsMarksLoadedToken = -1;
  const loading = h.api.loadSentenceLyricsMarksForTrack(old, h.runtime.musicLyricsLoadToken);
  h.selected.lyricsLanguage = "zh"; h.selected.lyricsUrl = "/fixture.zh.lrc"; h.runtime.musicLyricsLoadToken += 1;
  const before = copy(h.runtime.musicLyricsAnalysis);
  h.replyRead([sentenceMark(0, "start", 1)], h.reads[0]); await loading;
  assert.deepEqual(copy(h.runtime.musicLyricsAnalysis), before);
  assert.equal(h.api.sentenceLyricsMarksReady(), false); assert.equal(h.cachedWrites.length, 0);
});
await check("same-song reload rejects old marks GET and old save acknowledgement by load token", async () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true); h.time(1); h.api.markSentenceLyricsNow();
  const save = h.requests.at(-1), loading = h.api.loadSentenceLyricsMarksForTrack(h.selected, h.runtime.musicLyricsLoadToken);
  h.runtime.musicLyricsLoadToken += 1;
  h.runtime.musicLyricsAnalysis = { ok: true, path: "fixture.mp3", lyricsLanguage: "en", lines: [], manualMarks: [] };
  const before = copy(h.runtime.musicLyricsAnalysis); h.ready(); h.api.setSentenceLyricsCalibration(true);
  const roleBefore = h.runtime.sentenceLyricsCalibration.role;
  h.replyRead([sentenceMark(0, "start", 8)]); await loading;
  h.replySuccess(save); await tick(); await tick();
  assert.deepEqual(copy(h.runtime.musicLyricsAnalysis), before); assert.equal(h.cachedWrites.length, 0);
  assert.equal(h.runtime.sentenceLyricsCalibration.role, roleBefore);
});
await check("failed marks read leaves calibration disabled and reports the failure", async () => {
  const h = harness(); h.runtime.sentenceLyricsMarksLoadedToken = -1;
  const loading = h.api.loadSentenceLyricsMarksForTrack(h.selected, h.runtime.musicLyricsLoadToken);
  h.reads.at(-1).reject(new Error("synthetic read failure")); await loading;
  h.api.setSentenceLyricsCalibration(true); assert.equal(h.runtime.sentenceLyricsCalibration, null);
  assert.equal(h.api.sentenceLyricsMarksReady(), false); assert.match(h.runtime.sentenceLyricsSaveError, /synthetic read failure/);
});
await check("a late error for the old song does not put a failure banner on the new song", async () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true); h.time(1); h.api.markSentenceLyricsNow();
  const save = h.requests.at(-1);
  h.selected.path = "other.mp3"; h.runtime.selectedTrackPath = "other.mp3"; h.runtime.musicLyricsTrackPath = "other.mp3";
  h.runtime.musicLyricsLoadToken += 1; h.runtime.musicLyricsStatus = "new-song-status"; h.ready(); h.api.setSentenceLyricsCalibration(true);
  save.reject(new Error("old song failure")); await tick(); await tick();
  assert.equal(h.runtime.musicLyricsStatus, "new-song-status");
  assert.equal(h.runtime.sentenceLyricsSaveError, "", "old save must not put its error in the new sentence controls");
});
await check("invalid acknowledgement cannot discard pending points or move the already advanced calibration cursor", async () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true); h.time(1); h.api.markSentenceLyricsNow();
  h.requests.at(-1).resolve({ ok: false, error: "synthetic rejected receipt" }); await tick(); await tick();
  assert.equal(h.runtime.sentenceLyricsCalibration.role, "end"); assert.equal(h.runtime.pendingMusicLyricMarks.size, 3);
  assert.ok(h.storage.has("codexControl.sentenceLyricPending.v1")); assert.ok(h.runtime.sentenceLyricsOperation);
});
await check("successful-looking receipts without the exact sentence point remain pending and retryable", async () => {
  const wrong = patch => ({ ...sentenceMark(0, "start", 1), note: "manual sentence boundary", ...patch });
  for (const result of [{ ok: true }, { ok: true, marksByPath: {} }, { ok: true, marksByPath: { "fixture.mp3": [] } },
    ...[{ time: 9 }, { role: "end" }, { lyricsLanguage: "zh" }, { lineText: "Wrong sentence" }, { note: "Other note" }]
      .map(patch => ({ ok: true, marksByPath: { "fixture.mp3": [wrong(patch)] } }))]) {
    const h = harness(); h.api.setSentenceLyricsCalibration(true); h.time(1); h.api.markSentenceLyricsNow();
    h.requests.at(-1).resolve(result); await tick(); await tick();
    assert.equal(h.runtime.sentenceLyricsCalibration.role, "end"); assert.equal(h.runtime.pendingMusicLyricMarks.size, 3);
    assert.ok(h.storage.has("codexControl.sentenceLyricPending.v1")); assert.ok(h.runtime.sentenceLyricsOperation);
  }
});
await check("a removal receipt still containing either paired point cannot clear the removal journal", async () => {
  const marks = [sentenceMark(0, "start", 1), sentenceMark(0, "end", 4), sentenceMark(2, "start", 4)];
  const h = harness({ marks }); h.api.setSentenceLyricsCalibration(true, 0); h.runtime.sentenceLyricsCalibration.role = "end";
  h.api.removeSentenceLyricsPoint(); h.requests.at(-1).resolve({ ok: true, marksByPath: { "fixture.mp3": marks } });
  await tick(); await tick();
  assert.equal(h.runtime.pendingMusicLyricMarks.size, 2); assert.ok(h.storage.has("codexControl.sentenceLyricPending.v1"));
  assert.ok(h.runtime.sentenceLyricsOperation); assert.equal(h.runtime.sentenceLyricsCalibration.lineIndex, 0);
});
await check("invalid clocks and unlinked correction gaps cannot create or move sentence points", () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true);
  for (const time of [-1, NaN, Infinity, 101]) { h.time(time); assert.equal(h.api.markSentenceLyricsNow(), false); }
  assert.equal(h.requests.length, 0);
  const gap = harness({ marks: [sentenceMark(0, "start", 1), sentenceMark(0, "end", 4), sentenceMark(2, "start", 5)] });
  gap.api.setSentenceLyricsCalibration(true, 0); gap.runtime.sentenceLyricsCalibration.role = "end";
  gap.runtime.els.lyricsSentenceTime.value = "0:04.500";
  assert.equal(gap.api.editSentenceLyricsPoint(), false); assert.equal(gap.requests.length, 0);
  near(gap.api.sentenceLyricPointTime(0, "end"), 4); near(gap.api.sentenceLyricPointTime(2, "start"), 5);
});
await check("cheap marks placeholder cannot suppress a later actual acoustic analysis request", async () => {
  const h = harness();
  h.runtime.musicLyricsCache.set(h.selected.path, { path: h.selected.path, lyricsUrl: h.selected.lyricsUrl,
    lyricsType: "lrc", lines: fixtureLines(), synced: true, analysis: { ok: true, path: h.selected.path,
      lines: [], sentenceMarksOnly: true, manualMarks: [sentenceMark(0, "start", 1)] } });
  const loading = h.api.ensureLyricsAnalysisWarm(h.selected);
  await tick(); assert.equal(h.reads.length, 1); assert.match(h.reads[0].url, /^\/api\/music\/lyrics\/analysis\?/);
  const acoustic = { ok: true, path: h.selected.path, method: "synthetic-acoustic", lyricsLanguage: "en",
    lines: [{ index: 0, text: fixtureLines()[0].text, alignment: { source: "synthetic", quality: "acoustic_aligned", start: 1, end: 4 } }],
    manualMarks: [sentenceMark(0, "start", 1)] };
  h.reads[0].resolve({ ok: true, json: async () => copy(acoustic) }); await loading;
  assert.equal(h.runtime.musicLyricsCache.get(h.selected.path).analysis.method, "synthetic-acoustic");
  assert.equal(h.runtime.musicLyricsCache.get(h.selected.path).analysis.sentenceMarksOnly, undefined);
});
await check("cheap marks overlay preserves already available acoustic timing and word detail", async () => {
  const h = harness(), before = copy(h.runtime.musicLyricsAnalysis.lines);
  const loading = h.api.loadSentenceLyricsMarksForTrack(h.selected, h.runtime.musicLyricsLoadToken);
  h.replyRead([sentenceMark(0, "start", 1)]); await loading;
  assert.deepEqual(copy(h.runtime.musicLyricsAnalysis.lines), before);
  assert.deepEqual(copy(h.runtime.musicLyricsCache.get(h.selected.path).analysis.lines), before);
  assert.equal(h.runtime.musicLyricsAnalysis.sentenceMarksOnly, undefined);
});
await check("failed acoustic load does not wipe independently loaded manual sentence points", async () => {
  const h = harness(); h.runtime.musicLyricsAnalysis = { ok: true, path: h.selected.path, lines: [],
    sentenceMarksOnly: true, manualMarks: [sentenceMark(0, "start", 1)] };
  const before = copy(h.runtime.musicLyricsAnalysis);
  const loading = h.api.loadLyricsAnalysisForTrack(h.selected, h.runtime.musicLyricsLoadToken);
  h.reads.at(-1).resolve({ ok: false, status: 503 }); await loading;
  assert.deepEqual(copy(h.runtime.musicLyricsAnalysis), before); assert.equal(h.api.activeLyricsIndexAt(2), 0);
});
await check("closing calibration keeps the saved whole-sentence playback and removes only the editing target", () => {
  const h = harness({ marks: [sentenceMark(0, "start", 1), sentenceMark(0, "end", 4), sentenceMark(2, "start", 4)] });
  h.api.setSentenceLyricsCalibration(true); h.api.renderLyricsPanel(); h.api.setSentenceLyricsCalibration(false);
  assert.equal(h.runtime.sentenceLyricsCalibration, null); assert.equal(h.runtime.els.lyricsSentenceControls.hidden, true);
  h.api.updateLyricsProgress(2); assert.equal(h.runtime.musicLyricsActiveIndex, 0);
  const rows = h.runtime.els.nowPlayingLyricsList.querySelectorAll(".music-lyrics-line");
  assert.ok(rows[0].classes.has("active")); assert.ok(rows.every(row => !row.classes.has("sentence-calibration-target")));
  assert.equal(rows[0].querySelector(".lyric-sentence-text").textContent, fixtureLines()[0].text);
  assert.equal(rows[0].querySelectorAll(".lyric-word").length, 0);
});
await check("late acoustic response accepts fresh word detail without replacing acknowledged sentence corrections or browser cache", async () => {
  const h = harness(); h.api.setSentenceLyricsCalibration(true);
  await onsetAndAcknowledge(h, 1); await markAndAcknowledge(h, 4);
  h.api.setSentenceLyricsCalibration(true, 0); h.runtime.sentenceLyricsCalibration.role = "start";
  h.runtime.els.lyricsSentenceTime.value = "0:01.500"; assert.equal(h.api.editSentenceLyricsPoint(), true);
  h.replySuccess(); await tick(); await tick();
  const late = { ok: true, path: "fixture.mp3", lyricsLanguage: "en", method: "synthetic-late-acoustic",
    lines: [{ index: 0, text: fixtureLines()[0].text, wordTimes: [0, .75, 1.5],
      wordSpans: [{ word: "First", start: 0, end: .75 }], alignment: { source: "synthetic", quality: "acoustic_aligned", start: 1, end: 4 } }],
    manualMarks: [sentenceMark(0, "start", 1), sentenceMark(0, "end", 4), sentenceMark(2, "start", 4),
      { kind: "boundary", lineIndex: 0, boundaryIndex: 1, role: "end", time: 2.25 }] };
  assert.equal(h.api.applyLyricsAnalysisToActiveTrack(h.selected, late), true);
  near(h.api.sentenceLyricPointTime(0, "start"), 1.5);
  assert.deepEqual(copy(h.runtime.musicLyricsAnalysis.lines), late.lines, "new acoustic word detail accepted");
  const cached = h.runtime.musicLyricsCache.get(h.selected.path).analysis;
  assert.equal(cached.manualMarks.find(mark => mark.kind === "sentence" && mark.lineIndex === 0 && mark.role === "start").time, 1.5);
  assert.deepEqual(copy(cached.lines), late.lines);
  assert.equal(cached.manualMarks.find(mark => mark.kind === "boundary").time, 2.25);
  const foreign = { ...h.selected, lyricsLanguage: "zh", lyricsUrl: "/fixture.zh.lrc" };
  const before = copy(h.runtime.musicLyricsAnalysis);
  assert.equal(h.api.applyLyricsAnalysisToActiveTrack(foreign, late), false);
  assert.deepEqual(copy(h.runtime.musicLyricsAnalysis), before);
});
await check("late acoustic response cannot revive acknowledged removed sentence points in active analysis or browser cache", async () => {
  const marks = [sentenceMark(0, "start", 1), sentenceMark(0, "end", 4), sentenceMark(2, "start", 4)];
  const h = harness({ marks }); h.api.setSentenceLyricsCalibration(true, 0); h.runtime.sentenceLyricsCalibration.role = "end";
  assert.equal(h.api.removeSentenceLyricsPoint(), true); h.replySuccess(); await tick(); await tick();
  assert.ok(Number.isNaN(h.api.sentenceLyricPointTime(0, "end")));
  assert.ok(Number.isNaN(h.api.sentenceLyricPointTime(2, "start")));
  const late = { ok: true, path: "fixture.mp3", lyricsLanguage: "en", method: "synthetic-late-acoustic",
    lines: [{ index: 0, text: fixtureLines()[0].text, wordTimes: [0, .75], wordSpans: [{ word: "First", start: 0, end: .75 }] }],
    manualMarks: [...marks, { kind: "boundary", lineIndex: 0, boundaryIndex: 1, role: "end", time: 2.25 }] };
  assert.equal(h.api.applyLyricsAnalysisToActiveTrack(h.selected, late), true);
  assert.ok(Number.isNaN(h.api.sentenceLyricPointTime(0, "end"))); assert.ok(Number.isNaN(h.api.sentenceLyricPointTime(2, "start")));
  near(h.api.sentenceLyricPointTime(0, "start"), 1);
  const cached = h.runtime.musicLyricsCache.get(h.selected.path).analysis;
  assert.deepEqual(copy(cached.manualMarks.filter(mark => mark.kind === "sentence")), [marks[0]]);
  assert.deepEqual(copy(cached.lines), late.lines); assert.equal(cached.manualMarks.find(mark => mark.kind === "boundary").time, 2.25);
});

console.log(JSON.stringify({ passed: true, checks, source: appPath,
  scope: "Actual sentence functions in synthetic DOM/audio-clock fixtures; no listening validation or user data writes" }));
