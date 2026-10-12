// Actual app snapshot/save functions, isolated from the user's music and server.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { fileURLToPath } from "node:url";
const appPath = process.argv[2] || fileURLToPath(new URL("../app.js", import.meta.url));
const source = readFileSync(appPath, "utf8"), copy = value => JSON.parse(JSON.stringify(value));
function actualFunction(name) {
  const start = source.search(new RegExp(`(?:async )?function ${name}\\(`)); assert.ok(start >= 0, name);
  const tail = source.slice(start), next = /\n(?:async )?function \w+\(/.exec(tail.slice(1));
  return next ? tail.slice(0, next.index + 1) : tail;
}
const names = ["lyricsTimelineLabels", "lyricsTimelineContext", "lyricsTimelineConflicted", "saveLyricsTimelineDraft",
  "musicLyricMarkRole", "musicLyricMarkStorageKey", "activeSentenceLyricsIndexAt", "hasSentenceLyricTimeline"];
let checks = 0;
async function check(name, callback) { await callback(); console.log(`PASS ${name}`); checks += 1; }
function harness() {
  const requests = [], caches = []; let acknowledge;
  const runtime = { language: "en", musicLyricsTrackPath: "fixture.mp3", selectedTrackPath: "fixture.mp3", musicLyricsLoadToken: 7,
    musicLyricsLines: [{ text: "First original", time: 1 }, { text: "", time: 4, rest: true }, { text: "Second original", time: 5 },
      { text: "Third original", time: 9 }], musicLyricsAnalysis: { ok: true, path: "fixture.mp3", duration: 20,
        lines: [{ wordTimes: [1, 2] }], manualMarks: [{ kind: "boundary", lineIndex: 2, time: 6, boundaryIndex: 0 }] },
    pendingMusicLyricMarks: new Map(), sessionMusicLyricMarks: new Map(), sentenceLyricsBusy: false, musicLyricMarksFlushPromise: null,
    sentenceLyricsMarksReady: () => true, sentenceLyricsRowIndices: () => [0, 2, 3],
    sentenceLyricMark: (index, role) => index === 3 && role === "end" ? { time: 12 } : null,
    lyricsTrustedAlignment: index => index === 2 ? { start: 5.5, end: 7.5 } : null,
    manualLyricLineStartTime: () => NaN, manualLyricLineEndTime: () => NaN,
    audioDuration: () => 20, lyricsLineEndTime: () => 13, lyricsLineText: index => runtime.musicLyricsLines[index].text,
    lyricsLineDisplayStartTime: index => runtime.sentenceLyricMark(index, "start")?.time ?? (runtime.musicLyricsLines[index].time - .02),
    sentenceLyricPointTime: (index, role) => runtime.sentenceLyricMark(index, role)?.time ?? NaN,
    sentenceLyricsLanguage: () => "en", sentenceLyricsSource: () => "exact-lyrics-source", normalizeLyricsLanguageCode: value => value || "",
    selectedTrack: () => ({ path: "fixture.mp3", lyricsLanguage: "en" }), musicTrackWithPreferredLyrics: value => value,
    mergePendingMusicLyricMarksIntoAnalysis: value => value,
    setMusicLyricsCacheEntry: (item, value) => caches.push(copy({ item, value })), Date, URLSearchParams,
    fetch: async () => ({ ok: true, json: async () => ({ ok: true, marks: [] }) }),
    postJson(url, payload) { requests.push(copy({ url, payload })); return new Promise(resolve => { acknowledge = resolve; }); }
  };
  runInNewContext(names.map(actualFunction).join("\n"), runtime);
  return { runtime, requests, caches, reply(value) { acknowledge(value); } };
}
const changes = [{ lineIndex: 3, role: "end", lineText: "Third original", time: 12.25, before: 12 }];
function receipt(requests) {
  return { ok: true, marksByPath: { "fixture.mp3": [
    { kind: "boundary", lineIndex: 2, time: 6, boundaryIndex: 0 }, ...requests[0].payload.marks
  ] } };
}
await check("snapshot uses original lyric rows with manual/acoustic precedence and labels inferred rest endpoints honestly", () => {
  const h = harness(), before = copy(h.runtime.musicLyricsLines), snapshot = h.runtime.lyricsTimelineContext();
  assert.deepEqual(copy(snapshot.rows), [0, 2, 3]); assert.equal(snapshot.points.find(p => p.lineIndex === 0 && p.role === "start").source, "lrc");
  assert.deepEqual(copy(snapshot.points.find(p => p.lineIndex === 0 && p.role === "end")), {
    lineIndex: 0, role: "end", time: 4, source: "rest", lineText: "First original", playbackTime: 3.98,
    confirmedEnd: false, manualNote: "", expectedTime: null, locked: false
  });
  assert.equal(snapshot.points.find(p => p.lineIndex === 2 && p.role === "end").time, 7.5);
  assert.equal(snapshot.points.find(p => p.lineIndex === 3 && p.role === "end").source, "manual");
  assert.equal(h.requests.length, 0); assert.deepEqual(copy(h.runtime.musicLyricsLines), before);
});
await check("plain text null timestamps never become a pile of invented zero-time LRC points", () => {
  const h = harness(); h.runtime.musicLyricsLines.forEach(line => { line.time = null; });
  h.runtime.sentenceLyricMark = () => null; h.runtime.lyricsTrustedAlignment = () => null;
  const snapshot = h.runtime.lyricsTimelineContext(); assert.equal(snapshot.points.filter(p => p.role === "start").length, 0);
});
await check("a saved correction of one middle sentence does not suppress subsequent untouched LRC rows", () => {
  const h = harness(); h.runtime.sentenceLyricMark = (index, role) => index === 2
    ? { time: role === "start" ? 5.7 : 7.7 } : null;
  assert.equal(h.runtime.activeSentenceLyricsIndexAt(6), 2); assert.equal(h.runtime.activeSentenceLyricsIndexAt(8), -1);
  assert.equal(h.runtime.activeSentenceLyricsIndexAt(9.1), undefined, "normal LRC row takes over through the existing player fallback");
});
await check("null-timestamp plaintext rows do not take over an existing manual sentence timeline", () => {
  const h = harness(); h.runtime.musicLyricsLines.forEach(line => { line.time = null; }); h.runtime.lyricsTrustedAlignment = () => null;
  h.runtime.sentenceLyricMark = (index, role) => index === 0 ? { time: role === "start" ? 0 : 3 } : null;
  assert.equal(h.runtime.activeSentenceLyricsIndexAt(1), 0); assert.equal(h.runtime.activeSentenceLyricsIndexAt(3), -1);
});
await check("partial manual next-start corrections yield to a later original caption rest, including the outro", () => {
  const h = harness(); h.runtime.musicLyricsLines = [{ text: "First", time: 1 }, { text: "Second", time: 4 }, { text: "Third", time: 7 }, { text: "", time: 10, rest: true }];
  h.runtime.sentenceLyricsRowIndices = () => [0, 1, 2]; h.runtime.lyricsTrustedAlignment = () => null;
  h.runtime.sentenceLyricMark = (index, role) => index === 1 && role === "end" || index === 2 && role === "start" ? { time: 7.5 } : null;
  assert.equal(h.runtime.activeSentenceLyricsIndexAt(8), 2); assert.equal(h.runtime.activeSentenceLyricsIndexAt(11), undefined);
});
await check("a caption rest does not interrupt a still-live existing acoustic/manual interval", () => {
  const h = harness(); h.runtime.musicLyricsLines = [{ text: "First", time: 1 }, { text: "", time: 4, rest: true }];
  h.runtime.sentenceLyricsRowIndices = () => [0]; h.runtime.sentenceLyricMark = (index, role) => index === 0 && role === "start" ? { time: 1 } : null;
  h.runtime.lyricsTrustedAlignment = () => ({ start: 1, end: 6 });
  assert.equal(h.runtime.activeSentenceLyricsIndexAt(5), 0); assert.equal(h.runtime.activeSentenceLyricsIndexAt(7), undefined);
});
await check("metadata-zero tracks still display existing LRC points using analysis duration", () => {
  const h = harness(); h.runtime.audioDuration = () => 0;
  assert.equal(h.runtime.lyricsTimelineContext().duration, 20);
  h.runtime.musicLyricsAnalysis.duration = 0; h.runtime.sentenceLyricMark = () => null;
  const snapshot = h.runtime.lyricsTimelineContext(); assert.equal(snapshot.points.find(p => p.lineIndex === 3 && p.role === "end").source, "estimate");
  assert.equal(snapshot.duration, 13);
});
await check("Save sends only changed sentence points with original CAS and never stages or flushes pending word or other-song marks", async () => {
  const h = harness(); h.runtime.pendingMusicLyricMarks.set("private-other", { kind: "sentence", path: "other.mp3", time: 99 });
  h.runtime.pendingMusicLyricMarks.set("private-word", { kind: "boundary", path: "fixture.mp3", time: 6 });
  const beforePending = copy([...h.runtime.pendingMusicLyricMarks]), beforeLines = copy(h.runtime.musicLyricsAnalysis.lines);
  const target = h.runtime.lyricsTimelineContext(), saved = h.runtime.saveLyricsTimelineDraft(target, changes);
  assert.equal(h.requests[0].payload.marks.length, 1); assert.equal(h.requests[0].payload.marks[0].expectedTime, 12);
  assert.equal(h.requests[0].payload.marks[0].kind, "sentence"); h.reply(receipt(h.requests));
  assert.equal((await saved).ok, true); assert.deepEqual(copy([...h.runtime.pendingMusicLyricMarks]), beforePending);
  assert.deepEqual(copy(h.runtime.musicLyricsAnalysis.lines), beforeLines); assert.equal(h.caches.length, 1);
});
await check("late save acknowledgement for another song cannot replace active analysis or cache", async () => {
  const h = harness(), target = h.runtime.lyricsTimelineContext(), saved = h.runtime.saveLyricsTimelineDraft(target, changes);
  h.runtime.musicLyricsTrackPath = "new.mp3"; h.runtime.selectedTrackPath = "new.mp3";
  h.runtime.musicLyricsAnalysis = { ok: true, path: "new.mp3", manualMarks: [{ time: 3 }], lines: [{ wordTimes: [2] }] };
  const before = copy(h.runtime.musicLyricsAnalysis); h.reply(receipt(h.requests)); assert.equal((await saved).ok, true);
  assert.deepEqual(copy(h.runtime.musicLyricsAnalysis), before); assert.equal(h.caches.length, 0);
});
await check("same-song reload or language change rejects old acknowledgement without losing saved server receipt", async () => {
  for (const change of [h => { h.runtime.musicLyricsLoadToken += 1; }, h => { h.runtime.sentenceLyricsLanguage = () => "zh"; }]) {
    const h = harness(), target = h.runtime.lyricsTimelineContext(), before = copy(h.runtime.musicLyricsAnalysis);
    const saved = h.runtime.saveLyricsTimelineDraft(target, changes); change(h); h.reply(receipt(h.requests));
    assert.equal((await saved).ok, true); assert.deepEqual(copy(h.runtime.musicLyricsAnalysis), before); assert.equal(h.caches.length, 0);
  }
});
await check("successful-looking receipts lacking the changed point or returning another timestamp do not clear the draft", async () => {
  for (const mode of ["missing", "wrong-time", "wrong-text", "wrong-note"]) {
    const h = harness(), saved = h.runtime.saveLyricsTimelineDraft(h.runtime.lyricsTimelineContext(), changes), result = receipt(h.requests);
    const point = result.marksByPath["fixture.mp3"][1];
    if (mode === "missing") result.marksByPath["fixture.mp3"].pop();
    if (mode === "wrong-time") point.time += .01;
    if (mode === "wrong-text") point.lineText = "changed text";
    if (mode === "wrong-note") point.note = "not our change";
    h.reply(result); assert.equal((await saved).ok, false); assert.equal(h.caches.length, 0);
  }
});
await check("Save waits for an existing Insert acknowledgement before issuing its separate captured batch", async () => {
  const h = harness(); let release; h.runtime.musicLyricMarksFlushPromise = new Promise(resolve => { release = resolve; });
  const saved = h.runtime.saveLyricsTimelineDraft(h.runtime.lyricsTimelineContext(), changes);
  assert.equal(h.requests.length, 0); release({ ok: true }); await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.requests.length, 1); h.reply(receipt(h.requests)); assert.equal((await saved).ok, true);
});
await check("lost POST receipt is resolved by a read-only exact point verification, without a second batch", async () => {
  const h = harness(); let reads = 0;
  h.runtime.postJson = async (url, payload) => { h.requests.push(copy({ url, payload })); throw Error("timeout"); };
  h.runtime.fetch = async () => { reads += 1; return { ok: true, json: async () => ({ ok: true, marks: receipt(h.requests).marksByPath["fixture.mp3"] }) }; };
  const saved = await h.runtime.saveLyricsTimelineDraft(h.runtime.lyricsTimelineContext(), changes);
  assert.equal(saved.ok, true); assert.equal(saved.verified, true); assert.equal(h.requests.length, 1); assert.equal(reads, 1);
});
await check("application reload guard includes the timeline draft and current save/drag activity", () => {
  const fn = actualFunction("refreshForNewConsoleVersion");
  assert.ok(fn.includes("window.ConsoleLyricsTimeline?.hasDraft()")); assert.ok(fn.includes("!window.ConsoleLyricsTimeline.canReload()"));
});
console.log(JSON.stringify({ passed: true, checks, source: appPath, scope: "Actual app snapshot, dedicated CAS batch and late-receipt guards; no API or user data writes" }));
