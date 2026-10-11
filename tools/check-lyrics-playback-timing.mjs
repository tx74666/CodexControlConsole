// Real Console functions in a small DOM VM; no browser, audio decode, or data writes.
// May replace tools/check-lyrics-playback-timing.mjs without changing its positional app.js argument.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";

const appPath = process.argv[2] || fileURLToPath(new URL("../app.js", import.meta.url));
const cssPath = process.argv[3] || join(dirname(appPath), "styles.css");
const source = readFileSync(appPath, "utf8"), css = readFileSync(cssPath, "utf8");
const between = (start, end) => {
  const a = source.indexOf(start), b = source.indexOf(end, a + start.length);
  assert.ok(a >= 0 && b > a, `Missing actual source range: ${start}`);
  return source.slice(a, b);
};
const functionSource = name => {
  const start = source.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `Missing actual function ${name}`);
  const tail = source.slice(start), next = /\n(?:async )?function \w+\(/.exec(tail.slice(1));
  return next ? tail.slice(0, next.index + 1) : tail;
};
const helpers = between("function isCompactLyricCharacter(", "function renderLyricsWords(");
const playback = between("const lyricsLineSwitchLeadSeconds", "function lyricsColorMix(");
const visuals = between("function lyricsColorMix(", "function lyricsAnimationShouldRun(");
const names = ["renderLyricsWords", "lyricsBoundaryReferenceTime", "updateLyricsProgress", "lyricsAnimationShouldRun",
  "applyAudioCurrentTime", "seekToLyricsLine", "currentAudioSeekRatio", "updateTrackProgress"];
const actualFunctions = `${helpers}\n${playback}\n${visuals}\n${names.map(functionSource).join("\n")}`;
const playbackClasses = ["word-sung", "word-current", "word-hold", "word-wave-current", "word-phrase-rest",
  "word-strong", "word-valley-break", "word-group-break"];
const playbackProperties = ["--word-fill", "--word-strength", "--word-current-brightness", "--word-current-saturation",
  "--word-valley", "--word-motion", "--word-break-strength", "--word-phrase-rest", "--word-valley-shadow", "--word-transition"];
let count = 0;
const check = (name, fn) => { fn(); count += 1; console.log(`PASS ${name}`); };
const near = (a, b, message) => assert.ok(Math.abs(a - b) < 1e-9, `${message}: ${a} != ${b}`);

function element(tag = "div") {
  const properties = new Map(), classes = new Set(), children = [], mutations = [];
  let ownText = "";
  const item = {
    tag, properties, classes, children, mutations, dataset: {}, hidden: false,
    style: {
      setProperty(key, value) { properties.set(key, String(value)); mutations.push(["set", key, String(value)]); },
      removeProperty(key) { properties.delete(key); mutations.push(["remove", key]); }
    },
    classList: {
      add(...names) { names.forEach(name => { classes.add(name); mutations.push(["add", name]); }); },
      remove(...names) { names.forEach(name => { classes.delete(name); mutations.push(["removeClass", name]); }); },
      toggle(name, enabled) { if (enabled) this.add(name); else this.remove(name); }
    },
    appendChild(child) { children.push(child); return child; },
    querySelectorAll(selector) {
      const all = children.flatMap(child => [child, ...(child.querySelectorAll?.(selector) || [])]);
      if (selector === ".music-lyrics-line") return all.filter(child => child.classes.has("music-lyrics-line"));
      if (selector === ".lyric-word") return all.filter(child => child.classes.has("lyric-word"));
      throw new Error(`Unhandled DOM query ${selector}`);
    },
    querySelector(selector) {
      const match = selector.match(/^\[data-lyrics-index="(\d+)"\]$/);
      assert.ok(match, `Unhandled DOM selector ${selector}`);
      return children.find(child => child.dataset.lyricsIndex === match[1]) || null;
    },
    scrollIntoView() {}
  };
  Object.defineProperties(item, {
    className: { get: () => [...classes].join(" "), set(value) { classes.clear(); String(value).split(/\s+/).filter(Boolean).forEach(c => classes.add(c)); } },
    textContent: { get: () => ownText + children.map(child => child.textContent).join(""), set(value) { ownText = String(value); children.length = 0; } }
  });
  return item;
}

const aligned = (index, start, end, text = "Alpha Beta") => ({
  index, text, time: start - 0.5, analysisTime: start, duration: end - start,
  alignment: { start, end, source: "synthetic-acoustic-test", quality: "acoustic_aligned" },
  wordSpans: [{ word: "Alpha", start: 0, fillEnd: 0.8, end: 0.8 }, { word: "Beta", start: 1.2, fillEnd: 2, end: 2 }]
});

function harness(lines = [aligned(0, 1.5, 3.5), aligned(1, 5, 7)], marks = []) {
  const list = element(), panel = element(), seekEvents = [];
  const runtime = {
    musicLyricsLines: lines.map(line => ({ time: line.time, text: line.text, rest: Boolean(line.rest) })),
    musicLyricsAnalysis: { path: "fixture.mp3", lines, manualMarks: marks },
    musicLyricsTrackPath: "fixture.mp3", selectedTrackPath: "fixture.mp3", musicLyricsSynced: true, musicLyricsActiveIndex: -1,
    hasMusic: true, heldLyricsActiveIndex: -1, heldLyricsActiveUntil: 0, pendingSeekRatio: null, userSeeking: false,
    sessionMusicLyricMarks: new Map(), pendingMusicLyricMarks: new Map(), smoothValueAnimations: new Map(),
    performance: { now: () => 10 }, clamp: (v, min, max) => Math.min(max, Math.max(min, v)), audioDuration: () => 10,
    document: { createElement: element, createTextNode(value) { const node = element("text"); node.textContent = value; return node; } },
    window: { location: { href: "http://fixture/" } }, URL,
    selectedTrack: () => ({ path: "fixture.mp3", url: "fixture.mp3" }),
    setSelectedTrackPath(path) { runtime.selectedTrackPath = path; },
    recordTrackSeekChange: (...args) => seekEvents.push(args), formatDuration: String,
    isModuleForeground: () => true, syncLyricsTimingSelection() {}, syncLyricsAnimationLoop() {},
    updateLyricsTimingWavePlayhead() {}, trackSeekRatio: () => 0,
    els: { nowPlayingLyricsList: list, nowPlayingLyricsPanel: panel,
      audioPlayer: { currentTime: 0, paused: false, ended: false, src: "http://fixture/fixture.mp3", load() { throw new Error("Unexpected source reload"); } },
      trackSeek: { value: "0" }, trackCurrentTime: { textContent: "" }, trackDuration: { textContent: "" } }
  };
  runInNewContext(`${actualFunctions}\nglobalThis.api = { ${names.join(", ")},
    lyricsTrustedAlignment, lyricsLineDisplayStartTime, lyricsLineWordStartTime, lyricsLineEndTime, activeLyricsIndexAt,
    lyricsMappedWordSpans, clearLyricsWordPlaybackStyles, syncLyricsLineVisualStates, updateLyricsLineTone };`, runtime);
  const lineNodes = lines.map((line, index) => {
    const node = element("button"); node.className = "music-lyrics-line"; node.dataset.lyricsIndex = String(index);
    if (!line.rest) runtime.api.renderLyricsWords(node, line.text);
    list.appendChild(node); return node;
  });
  const wordNodes = lineNodes.map(node => node.querySelectorAll(".lyric-word"));
  return { ...runtime.api, runtime, lineNodes, wordNodes, seekEvents,
    paint(time) { runtime.els.audioPlayer.currentTime = time; runtime.api.updateLyricsProgress(time); },
    assertLine(active) {
      assert.equal(runtime.musicLyricsActiveIndex, active);
      lineNodes.forEach((line, index) => {
        assert.equal(line.classes.has("active"), index === active, `active class line ${index}`);
        assert.equal(line.properties.get("--line-color"), index === active ? "var(--lyrics-active-text)" : "var(--lyrics-upcoming-dim)");
        assert.equal(line.properties.get("--line-opacity"), index === active ? "1.000" : "0.540");
        wordNodes[index].forEach(word => {
          assert.ok(![...word.properties.keys()].some(key => key.startsWith("--word-")), "no word playback property");
          playbackClasses.forEach(name => assert.ok(!word.classes.has(name), `no playback ${name}`));
          assert.ok(!word.mutations.some(([kind, key]) => kind === "set" && key.startsWith("--word-")), "no word fill written at any point");
          assert.ok(!word.mutations.some(([kind, key]) => kind === "add" && playbackClasses.includes(key)), "no word playback class added at any point");
        });
      });
    }
  };
}

check("active words inherit one sentence tone; CSS has no word playback gradient or effects", () => {
  assert.ok(!/\b(?:updateActiveLyricsWordProgress|resetLyricsWordProgress)\s*\(/.test(source), "removed updater/reset must have no remaining declaration or call");
  assert.ok(!/--word-(?:fill|progress)|\.word-(?:current|sung|wave-current|hold|phrase-rest|strong|valley-break|group-break)\b/.test(css));
  for (const selector of [".now-playing-lyrics-panel .lyric-word", ".now-playing-lyrics-panel .music-lyrics-line.active .lyric-word"]) {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const block = css.match(new RegExp(`${escaped}\\s*\\{([^}]+)\\}`))?.[1]?.replace(/\/\*[\s\S]*?\*\//g, "");
    assert.ok(block, `Missing inheritance rule ${selector}`);
    for (const [property, value] of [["color", "inherit"], ["background-image", "none"], ["filter", "none"], ["text-shadow", "inherit"]]) {
      assert.ok(new RegExp(`(?:^|;)\\s*${property}\\s*:\\s*${value}\\s*;`).test(block), `${selector}: ${property} ${value}`);
    }
  }
});
check("real render preserves English punctuation, whitespace, CJK and editing indices without fill", () => {
  for (const text of ["Hello,  world!", "甲乙丙", "日本語の歌詞", "Alpha\tBeta", "café l’amour"]) {
    const h = harness([aligned(0, 1.5, 3.5, text)]);
    assert.equal(h.lineNodes[0].textContent, text);
    h.wordNodes[0].forEach((word, index) => assert.equal(word.dataset.wordIndex, String(index)));
    assert.equal(h.lineNodes[0].dataset.wordCount, String(h.wordNodes[0].length));
    h.paint(1.5); h.assertLine(0);
  }
});
check("all words light at the onset, stay equal through the phrase, and dim together at its end", () => {
  const h = harness(), before = JSON.stringify(h.runtime.musicLyricsAnalysis);
  for (const [time, active] of [[1.499, -1], [1.5, 0], [1.9, 0], [2.5, 0], [3.499, 0], [3.5, -1], [4.999, -1], [5, 1], [7, -1]]) {
    h.paint(time); h.assertLine(active);
  }
  assert.equal(JSON.stringify(h.runtime.musicLyricsAnalysis), before, "text/times/spans/marks unchanged");
});
check("pause and real backwards sentence seek preserve simultaneous highlight", () => {
  const h = harness(); h.paint(5.4); h.assertLine(1);
  h.runtime.els.audioPlayer.paused = true;
  assert.equal(h.lyricsAnimationShouldRun(), false);
  h.paint(5.4); h.assertLine(1);
  h.seekToLyricsLine(0); h.assertLine(0);
  near(h.runtime.els.audioPlayer.currentTime, 1.5, "real seek uses sentence onset");
  assert.equal(h.runtime.els.audioPlayer.paused, true, "seek preserves pause");
  assert.equal(h.seekEvents.length, 1);
  h.paint(3.5); h.assertLine(-1);
});
check("legacy playback styles are cleared while editing and marker word classes remain", () => {
  const h = harness(), line = h.lineNodes[0], word = h.wordNodes[0][0];
  playbackProperties.forEach(key => word.style.setProperty(key, ".5"));
  playbackClasses.forEach(name => word.classList.add(name));
  word.classList.add("lyrics-timing-selected", "session-lyric-boundary-start-before");
  h.clearLyricsWordPlaybackStyles(line);
  playbackProperties.forEach(key => assert.ok(!word.properties.has(key)));
  playbackClasses.forEach(name => assert.ok(!word.classes.has(name)));
  assert.ok(word.classes.has("lyrics-timing-selected"));
  assert.ok(word.classes.has("session-lyric-boundary-start-before"));
});
check("untrusted or malformed alignment keeps the existing ordinary onset rule", () => {
  for (const change of [{ quality: "needs_review" }, { source: "" }, { start: null }, { end: 1 }, { end: Infinity }]) {
    const line = aligned(0, 1.5, 3.5); Object.assign(line.alignment, change);
    assert.equal(harness([line]).lyricsTrustedAlignment(0), null);
  }
  const line = aligned(0, 1.5, 3.5); line.alignment.quality = "needs_review";
  near(harness([line]).lyricsLineDisplayStartTime(0), 1.025, "ordinary heuristic retained");
});
check("manual first/end sentence marks retain exact times and analysis origin", () => {
  const marks = [{ lineIndex: 0, boundaryIndex: 0, role: "start", time: 1.7 }, { lineIndex: 0, boundaryIndex: 2, role: "end", time: 3 }];
  const h = harness(undefined, marks), before = JSON.stringify(h.runtime.musicLyricsAnalysis);
  near(h.lyricsLineWordStartTime(0), 1.5, "acoustic internal origin retained");
  near(h.lyricsLineDisplayStartTime(0), 1.7, "manual sentence onset");
  near(h.lyricsLineEndTime(0), 3, "manual sentence end");
  for (const [time, active] of [[1.69, -1], [1.7, 0], [2.9, 0], [3, -1]]) { h.paint(time); h.assertLine(active); }
  assert.equal(JSON.stringify(h.runtime.musicLyricsAnalysis), before);
  const ordinary = aligned(0, 1.5, 3.5); delete ordinary.alignment;
  near(harness([ordinary], marks).lyricsLineWordStartTime(0), 1.7, "ordinary v88 manual origin retained");
});
check("a click hold cannot retain an acoustic or manual-ended sentence after its end", () => {
  for (const manual of [false, true]) {
    const line = aligned(0, 1.5, 3.5); if (manual) delete line.alignment;
    const h = harness([line, aligned(1, 5, 7)], manual ? [{ lineIndex: 0, boundaryIndex: 2, role: "end", time: 3.5 }] : []);
    h.runtime.heldLyricsActiveIndex = 0; h.runtime.heldLyricsActiveUntil = 1000;
    h.paint(3.4); h.assertLine(0); h.paint(3.6); h.assertLine(-1);
    assert.equal(h.runtime.heldLyricsActiveIndex, -1);
  }
});
check("caption rest cannot interrupt a live acoustic phrase; next onset can take over", () => {
  const first = aligned(0, 1.5, 4.5), rest = { index: 1, text: "", rest: true, time: 3.5, analysisTime: 3.5, duration: .4, wordSpans: [] };
  const h = harness([first, rest, aligned(2, 5, 7)]);
  for (const [time, active] of [[3.8, 0], [4.5, 1], [5, 2], [7, -1]]) { h.paint(time); h.assertLine(active); }
  delete first.alignment;
  assert.equal(harness([first, rest, aligned(2, 5, 7)]).activeLyricsIndexAt(3.8), 1, "ordinary caption-rest rule retained");
  first.alignment = { start: 1.5, end: 6, source: "synthetic-acoustic-test", quality: "acoustic_aligned" };
  assert.equal(harness([first, rest, aligned(2, 5, 7)]).activeLyricsIndexAt(5), 2);
});
check("track mismatch and unsynced lyrics cannot leave an active sentence", () => {
  const h = harness(); h.paint(2); h.assertLine(0);
  h.runtime.selectedTrackPath = "different.mp3"; h.paint(2); h.assertLine(-1);
  h.runtime.selectedTrackPath = "fixture.mp3"; h.runtime.musicLyricsSynced = false; h.paint(2);
  assert.equal(h.runtime.musicLyricsActiveIndex, -1);
  assert.ok(h.lineNodes.every(line => !line.classes.has("active")));
});
check("CJK translation and same-count mismatched source tokens still highlight only at sentence level", () => {
  for (const text of ["甲乙丙", "Hello, world"]) {
    const line = aligned(0, 1.5, 3.5, text), h = harness([line]);
    assert.equal(h.lyricsMappedWordSpans(0, h.wordNodes[0].length), null);
    for (const time of [1.5, 2.5, 3.49]) { h.paint(time); h.assertLine(0); }
    assert.equal(h.lineNodes[0].textContent, text);
  }
});
check("calibration retains the acoustic end/start gap and exact manual endpoint roles", () => {
  const line = aligned(0, 1.5, 3.5); line.wordTimes = [0, 1.2, 2];
  const h = harness([line]);
  near(h.lyricsBoundaryReferenceTime(0, 1, "end"), 2.3, "previous word end");
  near(h.lyricsBoundaryReferenceTime(0, 1, "start"), 2.7, "following word start");
  near(h.lyricsBoundaryReferenceTime(0, 2, "end"), 3.5, "sentence end");
  const marked = harness([line], [{ lineIndex: 0, boundaryIndex: 1, role: "end", time: 2.2 }]);
  near(marked.lyricsBoundaryReferenceTime(0, 1, "end"), 2.2, "manual endpoint retained");
  near(marked.lyricsBoundaryReferenceTime(0, 1, "start"), 2.7, "unmarked start unchanged");
  delete line.alignment;
  near(harness([line]).lyricsBoundaryReferenceTime(0, 1, "end"), 2.7, "ordinary v88 reference retained");
});

console.log(JSON.stringify({ passed: true, checks: count, source: appPath, stylesheet: cssPath,
  scope: "Actual sentence-selection/render/seek functions plus CSS source guards; no browser pixels or listening validation" }));
