// Runs real playback functions in a pure VM; no browser, audio decode, or installed data writes.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";

const appPath = process.argv[2] || fileURLToPath(new URL("../app.js", import.meta.url));
const source = readFileSync(appPath, "utf8");
const helpers = source.slice(source.indexOf("function isCompactLyricCharacter("), source.indexOf("function renderLyricsWords("));
const playback = source.slice(source.indexOf("const lyricsLineSwitchLeadSeconds"), source.indexOf("function lyricsColorMix("));
const boundaryReference = source.slice(source.indexOf("function lyricsBoundaryReferenceTime("), source.indexOf("function escapeHtml("));
const progress = source.slice(source.indexOf("function updateLyricsProgress("), source.indexOf("function musicLyricsCachePath("));
assert.ok(helpers.startsWith("function isCompactLyricCharacter("), "Missing real tokenization functions");
assert.ok(playback.startsWith("const lyricsLineSwitchLeadSeconds"), "Missing real playback functions");
let count = 0;
const check = (name, fn) => { fn(); count += 1; console.log(`PASS ${name}`); };
const near = (actual, expected, message) => assert.ok(Math.abs(actual - expected) < 1e-9, `${message}: ${actual} != ${expected}`);

function node(words) {
  const properties = new Map(), classes = new Set();
  return {
    properties, classes,
    style: { setProperty: (key, value) => properties.set(key, value), removeProperty: key => properties.delete(key) },
    classList: {
      add: (...names) => names.forEach(name => classes.add(name)),
      remove: (...names) => names.forEach(name => classes.delete(name)),
      toggle(name, enabled) { if (enabled) classes.add(name); else classes.delete(name); }
    },
    querySelectorAll: () => words || []
  };
}

const aligned = (index, start, end, text = "Alpha Beta") => ({
  index, text, time: start - 0.5, analysisTime: start, duration: end - start,
  alignment: { start, end, source: "synthetic-acoustic-test", quality: "acoustic_aligned" },
  wordSpans: [
    { word: "Alpha", start: 0, fillEnd: 0.8, end: 0.8 },
    { word: "Beta", start: 1.2, fillEnd: 2, end: 2 }
  ]
});

function harness(lines = [aligned(0, 1.5, 3.5), aligned(1, 5, 7)], marks = []) {
  const wordNodes = lines.map(line => line.text === "甲乙丙" ? [node(), node(), node()] : [node(), node()]);
  const lineNodes = wordNodes.map(words => node(words));
  const runtime = {
    musicLyricsLines: lines.map(line => ({ time: line.time, text: line.text, rest: Boolean(line.rest) })),
    musicLyricsAnalysis: { path: "fixture.mp3", lines, manualMarks: marks },
    musicLyricsTrackPath: "fixture.mp3", selectedTrackPath: "fixture.mp3", musicLyricsSynced: true, musicLyricsActiveIndex: 0,
    hasMusic: true, heldLyricsActiveIndex: -1, heldLyricsActiveUntil: 0,
    performance: { now: () => 10 },
    clamp: (value, min, max) => Math.min(max, Math.max(min, value)),
    audioDuration: () => 10,
    updateLyricsTimingWavePlayhead() {}, updateLyricsLineTone() {},
    syncLyricsLineVisualStates() { lineNodes.forEach(item => runtime.api.resetLyricsWordProgress(item, 0)); },
    els: { nowPlayingLyricsList: {
      querySelector: () => lineNodes[runtime.musicLyricsActiveIndex] || null,
      querySelectorAll: () => lineNodes.filter((_, index) => index !== runtime.musicLyricsActiveIndex)
    } }
  };
  runInNewContext(`${helpers}\n${playback}\n${boundaryReference}\n${progress}\nglobalThis.api = {
    lyricsTrustedAlignment, lyricsLineDisplayStartTime, lyricsLineWordStartTime, lyricsLineEndTime,
    activeLyricsIndexAt, lyricsWordPlaybackState, lyricsMappedWordSpans, updateActiveLyricsWordProgress, lyricsBoundaryReferenceTime,
    updateLyricsProgress, resetLyricsWordProgress
  };`, runtime);
  return { ...runtime.api, runtime, wordNodes, lineNodes,
    paint(time, active = runtime.api.activeLyricsIndexAt(time)) {
      runtime.musicLyricsActiveIndex = active;
      runtime.api.updateActiveLyricsWordProgress(time);
    }
  };
}

check("verified onset uses full absolute acoustic time", () => {
  const h = harness();
  near(h.lyricsLineDisplayStartTime(0), 1.5, "display onset");
  near(h.lyricsLineWordStartTime(0), 1.5, "relative-span origin");
  assert.equal(h.activeLyricsIndexAt(1.499), -1);
  assert.equal(h.activeLyricsIndexAt(1.5), 0);
});
check("untrusted or malformed alignment does not certify the heuristic", () => {
  for (const change of [{ quality: "needs_review" }, { source: "" }, { start: null }, { end: 1 }, { end: Infinity }]) {
    const line = aligned(0, 1.5, 3.5);
    Object.assign(line.alignment, change);
    assert.equal(harness([line]).lyricsTrustedAlignment(0), null);
  }
  const line = aligned(0, 1.5, 3.5);
  line.alignment.quality = "needs_review";
  near(harness([line]).lyricsLineDisplayStartTime(0), 1.025, "ordinary heuristic display rule retained");
});
check("future words stay empty and a sung word advances fractionally", () => {
  const h = harness();
  near(h.lyricsWordPlaybackState(0, 0, 2, 1.9).fill, 0.5, "first word midpoint");
  near(h.lyricsWordPlaybackState(0, 1, 2, 1.9).fill, 0, "second word is unstarted");
});
check("actual inter-word silence does not advance the next word", () => {
  const h = harness();
  const first = h.lyricsWordPlaybackState(0, 0, 2, 2.5);
  const second = h.lyricsWordPlaybackState(0, 1, 2, 2.5);
  assert.equal(first.fill, 1);
  assert.equal(first.current, false);
  assert.equal(second.fill, 0);
  assert.equal(second.current, false);
});
check("verified end leaves silence and never selects the next sentence early", () => {
  const h = harness();
  assert.equal(h.activeLyricsIndexAt(3.499), 0);
  assert.equal(h.activeLyricsIndexAt(3.5), -1);
  assert.equal(h.activeLyricsIndexAt(4.999), -1);
  assert.equal(h.activeLyricsIndexAt(5), 1);
});
check("manual end can shorten an automatically overlong final word", () => {
  const h = harness(undefined, [{ lineIndex: 0, boundaryIndex: 2, kind: "boundary", role: "end", time: 3 }]);
  near(h.lyricsLineEndTime(0), 3, "explicit shortened end");
  near(h.lyricsWordPlaybackState(0, 1, 2, 2.85).fill, 0.5, "last word uses shortened end");
  assert.equal(h.activeLyricsIndexAt(3), -1);
});
check("explicit word start/end override the automatic interval", () => {
  const h = harness(undefined, [
    { lineIndex: 0, boundaryIndex: 1, kind: "boundary", role: "start", time: 2.9 },
    { lineIndex: 0, boundaryIndex: 2, kind: "boundary", role: "end", time: 3.2 }
  ]);
  near(h.lyricsWordPlaybackState(0, 1, 2, 2.85).fill, 0, "manual delayed onset");
  near(h.lyricsWordPlaybackState(0, 1, 2, 3.05).fill, 0.5, "manual interval midpoint");
});
check("v88 span times keep their full analysisTime origin", () => {
  const line = aligned(0, 1.18, 3.18);
  delete line.alignment;
  line.time = 1;
  const h = harness([line]);
  near(h.lyricsLineWordStartTime(0), 1.18, "full origin instead of compressed 34 percent delay");
  near(h.lyricsWordPlaybackState(0, 0, 2, 1.16).fill, 0, "not yet singing");
});
check("v88 explicit fill-point plateau remains stationary", () => {
  const line = aligned(0, 1.5, 3.5);
  delete line.alignment;
  line.wordSpans[0] = { word: "Alpha", start: 0, fillEnd: 1, end: 1, profile: "gated-cumulative",
    fillPoints: [{ time: 0, fill: 0 }, { time: 0.2, fill: 0.4, hold: true }, { time: 0.6, fill: 0.4, hold: true }, { time: 1, fill: 1 }] };
  const h = harness([line]);
  near(h.lyricsWordPlaybackState(0, 0, 2, 1.8).fill, 0.4, "early plateau");
  near(h.lyricsWordPlaybackState(0, 0, 2, 2).fill, 0.4, "late plateau");
});
check("repeated sentences keep separate occurrence intervals", () => {
  const h = harness();
  assert.equal(h.activeLyricsIndexAt(5.4), 1);
  near(h.lyricsWordPlaybackState(1, 0, 2, 5.4).fill, 0.5, "second occurrence");
  assert.equal(h.lyricsWordPlaybackState(0, 0, 2, 5.4).fill, 1);
});
check("real renderer paints partial progress and restores it after backwards seek", () => {
  const h = harness();
  h.paint(1.9);
  near(Number(h.wordNodes[0][0].properties.get("--word-fill")), 0.5, "rendered first word partial");
  assert.equal(h.wordNodes[0][1].properties.get("--word-fill"), "0");
  h.paint(3.4);
  assert.equal(h.wordNodes[0][0].classes.has("word-sung"), true);
  h.paint(1.9);
  near(Number(h.wordNodes[0][0].properties.get("--word-fill")), 0.5, "backwards seek restores fill");
  assert.equal(h.wordNodes[0][0].classes.has("word-sung"), false);
  assert.equal(h.wordNodes[0][1].properties.get("--word-fill"), "0");
  assert.equal(h.wordNodes[0][0].properties.get("--word-transition"), "0ms");
});
check("CJK translation token mismatch stays at line level without fabricated words", () => {
  const line = aligned(0, 1.5, 3.5, "甲乙丙");
  line.wordSpans = [{ word: "甲乙丙", start: 0, fillEnd: 2, end: 2 }];
  const h = harness([line]);
  assert.equal(h.lyricsMappedWordSpans(0, 3), null);
  const state = h.lyricsWordPlaybackState(0, 1, 3, 2);
  assert.equal(state.lineOnly, true);
  assert.equal(state.fill, 1);
  assert.equal(state.current, false);
  assert.equal(h.lyricsWordPlaybackState(0, 1, 3, 1.49).fill, 0);
  assert.equal(h.lyricsWordPlaybackState(0, 1, 3, 3.5).fill, 0);
});
check("sidecar source-token labels keep fractional word playback", () => {
  const line = aligned(0, 1.5, 3.5, "Hello, world");
  // The loader returns exact source labels after accepting casefold-equivalent input.
  line.wordSpans[0].word = "Hello,";
  line.wordSpans[1].word = "world";
  const h = harness([line]);
  assert.notEqual(h.lyricsMappedWordSpans(0, 2), null);
  h.paint(1.9);
  near(Number(h.wordNodes[0][0].properties.get("--word-fill")), 0.5, "canonical first word remains partial");
  assert.equal(h.wordNodes[0][1].properties.get("--word-fill"), "0");
  assert.equal(h.lyricsWordPlaybackState(0, 1, 2, 1.9).lineOnly, false);
});
check("same-count wrong-word analysis is not applied to a different lyric", () => {
  const line = aligned(0, 1.5, 3.5);
  line.wordSpans[1].word = "Different";
  assert.equal(harness([line]).lyricsMappedWordSpans(0, 2), null);
});
check("a click hold cannot keep a verified or manual-ended sentence singing", () => {
  for (const manual of [false, true]) {
    const line = aligned(0, 1.5, 3.5);
    if (manual) delete line.alignment;
    const h = harness([line, aligned(1, 5, 7)], manual ? [{ lineIndex: 0, boundaryIndex: 2, role: "end", time: 3.5 }] : []);
    h.runtime.heldLyricsActiveIndex = 0;
    h.runtime.heldLyricsActiveUntil = 1000;
    h.paint(3.4);
    h.updateLyricsProgress(3.6);
    assert.equal(h.runtime.musicLyricsActiveIndex, -1);
    assert.equal(h.runtime.heldLyricsActiveIndex, -1);
    assert.equal(h.wordNodes[0][0].properties.get("--word-fill"), "0");
  }
});
check("real progress update restores the earlier occurrence after seeking backwards", () => {
  const h = harness();
  h.updateLyricsProgress(5.4);
  assert.equal(h.runtime.musicLyricsActiveIndex, 1);
  h.updateLyricsProgress(1.9);
  assert.equal(h.runtime.musicLyricsActiveIndex, 0);
  near(Number(h.wordNodes[0][0].properties.get("--word-fill")), 0.5, "earlier occurrence partial fill");
  assert.equal(h.wordNodes[1][0].properties.get("--word-fill"), "0");
});

check("caption rest cannot interrupt a live acoustic interval", () => {
  const first = aligned(0, 1.5, 4.5);
  const rest = { index: 1, text: "", rest: true, time: 3.5, analysisTime: 3.5, duration: 0.4, wordSpans: [] };
  const h = harness([first, rest, aligned(2, 5, 7)]);
  assert.equal(h.activeLyricsIndexAt(3.8), 0);
  assert.equal(h.activeLyricsIndexAt(4.5), 1);
  assert.equal(h.activeLyricsIndexAt(5), 2);
  assert.equal(h.activeLyricsIndexAt(7), -1);
  // Preserve normal caption-rest behavior for ordinary v88 data.
  delete first.alignment;
  assert.equal(harness([first, rest, aligned(2, 5, 7)]).activeLyricsIndexAt(3.8), 1);
});
check("a new acoustic onset takes over even before the previous acoustic end", () => {
  const first = aligned(0, 1.5, 6);
  const rest = { index: 1, text: "", rest: true, time: 3.5, analysisTime: 3.5, duration: 0.4, wordSpans: [] };
  const h = harness([first, rest, aligned(2, 5, 7)]);
  assert.equal(h.activeLyricsIndexAt(4.9), 0);
  assert.equal(h.activeLyricsIndexAt(5), 2);
});
check("an acoustic first-word mark does not shift unmarked words", () => {
  const marks = [{ lineIndex: 0, boundaryIndex: 0, kind: "boundary", role: "start", time: 1.7 }];
  const h = harness(undefined, marks);
  near(h.lyricsLineWordStartTime(0), 1.5, "unchanged acoustic origin");
  near(h.lyricsLineDisplayStartTime(0), 1.7, "manual first-word display onset");
  near(h.lyricsWordPlaybackState(0, 0, 2, 2).fill, 0.5, "only first-word start moved");
  near(h.lyricsWordPlaybackState(0, 1, 2, 2.8).fill, 0.125, "second word remains at acoustic2.7");
  const ordinary = aligned(0, 1.5, 3.5);
  delete ordinary.alignment;
  const v88 = harness([ordinary], marks);
  near(v88.lyricsLineWordStartTime(0), 1.7, "ordinary v88 manual line origin retained");
  near(v88.lyricsWordPlaybackState(0, 1, 2, 2.8).fill, 0, "ordinary v88 shift retained");
});
check("acoustic calibration references retain a real end/start gap", () => {
  const line = aligned(0, 1.5, 3.5);
  line.wordTimes = [0, 1.2, 2];
  const h = harness([line]);
  near(h.lyricsBoundaryReferenceTime(0, 1, "end"), 2.3, "Alpha ends before silence");
  near(h.lyricsBoundaryReferenceTime(0, 1, "start"), 2.7, "Beta starts after silence");
  near(h.lyricsBoundaryReferenceTime(0, 2, "end"), 3.5, "last word end");
  const marked = harness([line], [{lineIndex:0, boundaryIndex:1, role:"end", time:2.2}]);
  near(marked.lyricsBoundaryReferenceTime(0, 1, "end"), 2.2, "exact manual endpoint retained");
  near(marked.lyricsBoundaryReferenceTime(0, 1, "start"), 2.7, "other role remains acoustic");
  delete line.alignment;
  near(harness([line]).lyricsBoundaryReferenceTime(0, 1, "end"), 2.7, "ordinary v88 reference retained");
});

console.log(JSON.stringify({ passed: true, checks: count, source: appPath, scope: "Pure playback/renderer regressions only; no real acoustic or listening validation" }));
