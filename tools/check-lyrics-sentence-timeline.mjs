// Run the shipped controller, using isolated storage and asynchronous save receipts.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { fileURLToPath } from "node:url";
const path = process.argv[2] || fileURLToPath(new URL("../lyrics-sentence-timeline.js", import.meta.url));
const runtime = { window: {} }; runInNewContext(readFileSync(path, "utf8"), runtime);
const factory = runtime.window.ConsoleLyricsTimelineFactory;
const copy = value => JSON.parse(JSON.stringify(value));
let checks = 0;
async function check(name, callback) { await callback(); console.log(`PASS ${name}`); checks += 1; }
function context(key = "a") {
  return { key, signature: "unchanged original lyric rows", path: `${key}.mp3`, lyricsLanguage: "en", rows: [0, 1, 2], duration: 20,
    points: [[0, "start", 1, "lrc"], [0, "end", 4, "next"], [1, "start", 4, "lrc"], [1, "end", 7, "acoustic"],
      [2, "start", 9, "acoustic"], [2, "end", 12, "manual"]].map(([lineIndex, role, time, source]) => ({ lineIndex, role, time, source,
        lineText: `Original sentence ${lineIndex}`, expectedTime: source === "manual" ? time : null })) };
}
function setup(storage = new Map()) {
  const calls = [], events = []; let pending = null, conflict = false, failWrite = false;
  const controller = factory.createController({ storage: {
    getItem: key => storage.get(key), setItem(key, value) { if (failWrite) throw Error("quota"); storage.set(key, value); },
    removeItem(key) { if (failWrite) throw Error("quota"); storage.delete(key); }
  }, labels: () => ({ saveFailed: "failed", storage: "storage" }), format: String,
  conflicted: () => conflict, preview: () => events.push("preview"), save(target, points) {
    calls.push(copy({ target, points })); return new Promise((resolve, reject) => { pending = { resolve, reject }; });
  } });
  controller.setContext(context());
  return { controller, storage, calls, events, reply: value => pending.resolve(value), fail: () => pending.reject(Error("offline")),
    conflict(value) { conflict = value; }, failWrite(value) { failWrite = value; } };
}
await check("existing LRC and acoustic points are displayed without any manual API save or conversion", () => {
  const h = setup(); h.controller.show();
  assert.equal(h.controller.points().length, 6); assert.equal(h.calls.length, 0);
  assert.equal(h.storage.size, 0); assert.equal(h.controller.hasDraft(), false); assert.equal(h.controller.state().span, 10);
});
await check("drag previews a linked boundary and only changed points enter the dedicated Save batch", async () => {
  const h = setup(); assert.equal(h.controller.move("0:end", 4.5), true);
  assert.equal(h.controller.activeAt(4.2), 0); assert.equal(h.controller.activeAt(4.5), 1);
  assert.equal(h.calls.length, 0); assert.equal(h.controller.canReload(), false);
  const saved = h.controller.save(); assert.equal(h.calls.length, 1);
  assert.deepEqual(h.calls[0].points.map(p => [p.lineIndex, p.role, p.time, p.before]), [[0, "end", 4.5, null], [1, "start", 4.5, null]]);
  h.reply({ ok: true }); assert.equal(await saved, true); assert.equal(h.controller.hasDraft(), false);
});
await check("an acoustic rest is preserved when its separate end is adjusted", () => {
  const h = setup(); h.controller.move("1:end", 7.2);
  assert.equal(h.controller.points().find(p => p.lineIndex === 2 && p.role === "start").time, 9);
  assert.equal(Object.keys(h.controller.state().draft.changes).length, 1);
  assert.equal(h.controller.activeAt(8), -1); assert.equal(h.controller.activeAt(9), 2);
});
await check("crossing, reversal, negative and past-track moves retain the original draft", () => {
  const h = setup(); h.controller.move("1:end", 7.2); const original = copy(h.controller.state().draft);
  for (const time of [-1, 4, 9.1, 21, NaN]) assert.equal(h.controller.move("1:end", time), false);
  assert.deepEqual(copy(h.controller.state().draft), original);
});
await check("Undo and Cancel revert only the active song draft and perform no API write", () => {
  const h = setup(); h.controller.move("0:end", 4.5); h.controller.move("1:end", 7.2);
  assert.equal(h.controller.undo(), true); assert.equal(h.controller.points().find(p => p.lineIndex === 1 && p.role === "end").time, 7);
  h.controller.setContext(context("b")); h.controller.move("2:end", 13);
  h.controller.cancel(); assert.equal(h.controller.hasDraft(), true);
  h.controller.setContext(context()); assert.equal(h.controller.points().find(p => p.lineIndex === 0 && p.role === "end").time, 4.5);
  h.controller.cancel(); assert.equal(h.controller.hasDraft(), false); assert.equal(h.calls.length, 0);
});
await check("draft survives reload with exact original CAS even if a later marks read changes the manual baseline", async () => {
  const h = setup(); h.controller.move("2:end", 13);
  const restored = setup(h.storage), updated = context(); updated.points[5].expectedTime = 12.7; updated.points[5].time = 12.7;
  restored.controller.setContext(updated); assert.equal(restored.controller.points()[5].time, 13);
  const saved = restored.controller.save(); assert.equal(restored.calls[0].points[0].before, 12);
  restored.reply({ ok: false, error: "CAS conflict" }); assert.equal(await saved, false);
  assert.equal(restored.controller.state().draft.changes["2:end"].before, 12); assert.equal(restored.controller.hasDraft(), true);
});
await check("a failed save retains exact captured times and a double-click cannot create another request", async () => {
  const h = setup(); h.controller.move("2:end", 13.111); const first = h.controller.save();
  assert.equal(await h.controller.save(), false); h.fail(); assert.equal(await first, false);
  assert.equal(h.controller.hasDraft(), true); const retry = h.controller.save();
  assert.deepEqual(h.calls[1].points, h.calls[0].points); h.reply({ ok: true }); assert.equal(await retry, true);
});
await check("a late old-song receipt clears only its saved draft and preserves another song draft", async () => {
  const h = setup(); h.controller.setContext(context("b")); h.controller.move("2:end", 13);
  h.controller.setContext(context()); h.controller.move("2:end", 14); const saved = h.controller.save();
  h.controller.setContext(context("b")); h.reply({ ok: true }); assert.equal(await saved, true);
  assert.equal(h.controller.state().key, "b"); assert.equal(h.controller.points()[5].time, 13); assert.equal(h.controller.hasDraft(), true);
});
await check("pending Insert collision blocks drag and Save without deleting or flushing the draft", async () => {
  const h = setup(); h.controller.move("2:end", 13); h.conflict(true);
  assert.equal(h.controller.move("2:end", 14), false); assert.equal(await h.controller.save(), false);
  assert.equal(h.calls.length, 0); assert.equal(h.controller.points()[5].time, 13);
  assert.equal(h.controller.conflicts([{ lineIndex: 2, role: "end" }]), true);
  assert.equal(h.controller.conflicts([{ lineIndex: 0, role: "end" }]), false);
});
await check("edited lyric identity cannot reuse an old draft, and the preserved draft blocks automatic reload", () => {
  const h = setup(); h.controller.move("2:end", 13); const changed = context(); changed.signature = "different original lyric rows";
  h.controller.setContext(changed); assert.equal(h.controller.activeAt(12.5), undefined);
  assert.equal(h.controller.move("2:end", 14), false); assert.equal(h.controller.state().error, "sourceChanged");
  assert.equal(h.controller.hasDraft(), true); assert.equal(h.controller.canReload(), false);
  assert.equal(h.controller.cancel(), true); assert.equal(h.controller.hasDraft(), false);
});
await check("local storage failure does not apply an unprotected edit or erase protected edits", () => {
  const h = setup(); h.failWrite(true); assert.equal(h.controller.move("2:end", 13), false);
  assert.equal(h.controller.points()[5].time, 12); assert.equal(h.events.length, 0);
  h.failWrite(false); h.controller.move("2:end", 13); h.failWrite(true);
  assert.equal(h.controller.cancel(), false); assert.equal(h.controller.points()[5].time, 13);
});
await check("an unrelated pre-existing bad caption does not block a valid repair elsewhere", () => {
  const h = setup(), baseline = context(); baseline.points[1].time = .5;
  h.controller.setContext(baseline); assert.equal(h.controller.move("2:end", 13), true);
  assert.equal(h.controller.move("0:end", .7), true, "progressively improving an existing reversed caption is allowed");
  assert.equal(h.controller.move("0:end", .6), false, "worsening that invalid interval is rejected");
});
await check("a confirmed Save followed by local draft cleanup failure retries cleanup without another API request", async () => {
  const h = setup(); h.controller.move("2:end", 13); const first = h.controller.save(); h.failWrite(true); h.reply({ ok: true });
  assert.equal(await first, false); assert.equal(h.controller.hasDraft(), true);
  assert.equal(h.controller.move("2:end", 14), false); assert.equal(h.controller.undo(), false); assert.equal(h.controller.cancel(), false);
  h.failWrite(false); assert.equal(await h.controller.save(), true); assert.equal(h.calls.length, 1); assert.equal(h.controller.hasDraft(), false);
});
await check("reloaded already-saved drafts require only local cleanup before another edit can use new CAS", async () => {
  const h = setup(); h.controller.move("2:end", 13); const restored = setup(h.storage), baseline = context();
  baseline.points[5].time = 13; baseline.points[5].expectedTime = 13; baseline.points[5].manualNote = "manual sentence timeline";
  restored.controller.setContext(baseline); assert.equal(restored.controller.state().error, "cleanup");
  assert.equal(restored.controller.move("2:end", 14), false); assert.equal(await restored.controller.save(), true);
  assert.equal(restored.calls.length, 0); assert.equal(restored.controller.move("2:end", 14), true);
  assert.equal(restored.controller.state().draft.changes["2:end"].before, 13);
});
await check("dragging a middle boundary leaves untouched caption rests and the original long intro rest blank", () => {
  const h = setup(), baseline = context();
  baseline.points = [[0, "start", 1, "lrc"], [0, "end", 4, "next"], [1, "start", 4, "lrc"], [1, "end", 7, "next"],
    [2, "start", 7, "lrc"], [2, "end", 10, "rest"]].map(([lineIndex, role, time, source]) => ({ lineIndex, role, time, source,
      lineText: `Original sentence ${lineIndex}`, expectedTime: null, playbackTime: role === "end" && source === "rest" ? 9.98 : time }));
  h.controller.setContext(baseline); h.controller.move("1:end", 7.5);
  assert.equal(h.controller.activeAt(8), 2); assert.equal(h.controller.activeAt(11), -1);
  baseline.duration = 50; baseline.points[1] = { ...baseline.points[1], time: 8.76, source: "rest", playbackTime: 8.74 };
  baseline.points[2].time = 30.06; baseline.points[2].playbackTime = 30.04;
  baseline.points[3].time = 35; baseline.points[3].playbackTime = 35;
  baseline.points[4].time = 35; baseline.points[4].playbackTime = 34.98;
  baseline.points[5].time = 40; baseline.points[5].playbackTime = 39.98;
  baseline.signature = "Japanese intro then long rest"; h.controller.cancel(); h.controller.setContext(baseline); h.controller.move("1:end", 35.5);
  assert.equal(h.controller.activeAt(20), -1);
});
await check("a local draft retains untouched rows' original display lead and does not create inferred vocal rests", () => {
  const h = setup(), baseline = context(); baseline.points[0].playbackTime = .98;
  h.controller.setContext(baseline); h.controller.move("2:end", 13);
  assert.equal(h.controller.activeAt(.99), 0); assert.equal(h.controller.activeAt(4), 1);
});
await check("returning a dragged point to its original value removes that change without manufacturing manual LRC points", () => {
  const h = setup(); h.controller.move("0:end", 4.5); h.controller.move("0:end", 4);
  assert.equal(h.controller.hasDraft(), false); assert.equal(h.controller.activeAt(3), undefined); assert.equal(h.calls.length, 0);
});
function domHarness() {
  const document = { activeElement: null };
  const node = tag => {
    const listeners = new Map();
    const element = { tagName: tag.toUpperCase(), className: "", dataset: {}, style: {}, children: [], ownerDocument: document,
      attributes: {}, hidden: false, disabled: false, value: "", setAttribute(key, value) { this.attributes[key] = String(value); },
      appendChild(child) { this.children.push(child); child.parentNode = this; return child; }, replaceChildren(...children) { this.children = children; },
      addEventListener(type, callback) { if (!listeners.has(type)) listeners.set(type, []); listeners.get(type).push(callback); },
      dispatch(type, event = {}) { for (const callback of listeners.get(type) || []) callback({ preventDefault() {}, ...event }); },
      descendants() { return this.children.flatMap(child => [child, ...child.descendants()]); },
      querySelector(selector) {
        return this.descendants().find(child => selector.startsWith(".") ? child.className.split(/\s+/).includes(selector.slice(1))
          : selector.startsWith("[data-timeline-point=") ? child.dataset.timelinePoint === selector.match(/="([^"]+)"/)?.[1] : false) || null;
      }, focus() { document.activeElement = this; }, getBoundingClientRect: () => ({ left: 0, width: 1000 }),
      setPointerCapture(id) { this.captured = id; }, releasePointerCapture(id) { if (this.captured === id) this.captured = null; }
    }; return element;
  };
  document.createElement = node; const root = node("div"), storage = new Map(); let time = 1;
  const labels = { save: "Save", undo: "Undo", cancel: "Cancel", previous: "Previous", nextWindow: "Next", all: "All", zoom: "Zoom", follow: "Follow",
    legend: "Legend", timeline: "Timeline", start: "Start", end: "End", dragHint: "Drag", unsaved: "Unsaved" };
  const controller = factory.createController({ root, storage: { getItem: key => storage.get(key),
    setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) }, labels: () => labels,
    format: time => time.toFixed(2), time: () => time, preview() {}, save: async () => ({ ok: true }) });
  controller.setContext(context()); controller.show();
  return { controller, root, time(value) { time = value; } };
}
await check("actual pointer handlers keep one Undo step for an entire drag, preserve invalid moves, and retain host pointer capture", () => {
  const h = domHarness(), dot = h.root.querySelector('[data-timeline-point="0:end"]');
  dot.dispatch("pointerdown", { pointerId: 6, button: 0, clientX: 400 }); assert.equal(h.root.captured, 6);
  h.root.dispatch("pointermove", { pointerId: 6, clientX: 420 }); h.root.dispatch("pointermove", { pointerId: 6, clientX: 440 });
  h.root.dispatch("pointermove", { pointerId: 6, clientX: 810 }); assert.equal(h.controller.points()[1].time, 4.4);
  assert.equal(h.controller.state().draft.history.length, 1);
  h.root.dispatch("pointerup", { pointerId: 6 }); assert.equal(h.root.captured, null);
  h.controller.undo(); assert.equal(h.controller.points()[1].time, 4); assert.equal(h.controller.hasDraft(), false);
});
await check("actual keyboard handlers fine-tune at 10ms and 100ms while restoring the selected point focus", () => {
  const h = domHarness(), dot = h.root.querySelector('[data-timeline-point="2:end"]');
  // Navigate to the next ten-second window so the point is available.
  const next = h.root.descendants().find(node => node.tagName === "BUTTON" && node.title === "Next"); next.dispatch("click");
  const current = h.root.querySelector('[data-timeline-point="2:end"]'); current.focus();
  current.dispatch("keydown", { key: "ArrowRight" });
  assert.equal(h.controller.points()[5].time, 12.01); assert.equal(h.root.ownerDocument.activeElement.dataset.timelinePoint, "2:end");
  h.root.querySelector('[data-timeline-point="2:end"]').dispatch("keydown", { key: "ArrowLeft", shiftKey: true });
  assert.equal(h.controller.points()[5].time, 11.91); assert.equal(dot, null, "initial ten-second view does not show the twelve-second point");
});
await check("actual window controls support full-song/5-second zoom and audio follow at the final duration without recursion", () => {
  const h = domHarness(), select = h.root.descendants().find(node => node.tagName === "SELECT");
  select.value = "all"; select.dispatch("change"); assert.equal(h.controller.state().span, 20);
  const second = h.root.descendants().find(node => node.tagName === "SELECT"); second.value = "5"; second.dispatch("change");
  assert.equal(h.controller.state().span, 5);
  h.time(21); h.root.descendants().find(node => node.tagName === "BUTTON" && node.title === "Follow").dispatch("click");
  assert.equal(h.controller.state().start, 15); h.controller.clock(21); assert.equal(h.controller.state().start, 15);
});
console.log(JSON.stringify({ passed: true, checks, source: path, scope: "Actual shipped timeline controller; isolated storage and save receipts; no user data or singing validation" }));
