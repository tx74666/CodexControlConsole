// Exercise real save/sync functions without a browser, installed data, or network.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const saveSource = source.slice(source.indexOf("function persistMusicStateNow()"), source.indexOf("function flushMusicStateBeforeUnload()"));
const syncSource = source.slice(source.indexOf("function stopRandomRealmMusicOrderPoll()"), source.indexOf("function setRandomRealmReleaseStatus("));
const settle = async () => { for (let n = 0; n < 8; n++) await new Promise(resolve => setImmediate(resolve)); };
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const response = (value, status = 200) => ({ ok: status >= 200 && status < 300, status, async json() { return value; } });

function harness() {
  const calls = [], timers = new Map();
  let timerId = 0, hook = null, current = { order: ["A", "B"] }, foreground = true;
  const runtime = {
    hasMusic: true,
    els: { syncRandomRealmMusicOrder: { disabled: false }, randomRealmMusicOrderStatus: { textContent: "" } },
    window: {
      setTimeout(fn, delay) { const id = ++timerId; timers.set(id, { fn, delay }); return id; },
      clearTimeout(id) { timers.delete(id); }
    },
    text: (key, detail) => detail ? `${key}:${detail}` : key,
    saveMusicStateLocal() {},
    musicStatePayload: () => structuredClone(current),
    isModuleForeground: () => foreground,
    async fetch(url, options = {}) {
      const call = { url, ...options, payload: options.body ? JSON.parse(options.body) : null };
      calls.push(call);
      const custom = hook?.(call);
      if (custom !== undefined) return await custom;
      if (url === "/api/music/state") return response({ ok: true });
      return response({ ok: true, requestId: "request-1", status: "pending" });
    },
    async postJson(url, payload) {
      const result = await runtime.fetch(url, { method: "POST", body: JSON.stringify(payload) });
      if (!result.ok) throw new Error(`HTTP ${result.status}`);
      return result.json();
    }
  };
  runInNewContext(`
    let musicStatePersistTimer = null;
    let musicStatePersistQueue = Promise.resolve(true);
    let musicStateHasQueuedSave = false;
    let randomRealmMusicOrderRequestId = "";
    let randomRealmMusicOrderStatus = "idle";
    let randomRealmMusicOrderPollTimer = null;
    let randomRealmMusicOrderBusy = false;
    let randomRealmMusicOrderStatusInFlight = false;
    let randomRealmMusicOrderGeneration = 0;
    ${saveSource}
    ${syncSource}
    globalThis.api = { persistMusicStateNow, persistMusicStateSoon, syncRandomRealmMusicOrder,
      loadRandomRealmMusicOrderStatus, scheduleRandomRealmMusicOrderPoll, stopRandomRealmMusicOrderPoll,
      status: () => randomRealmMusicOrderStatus };
  `, runtime);
  return { ...runtime.api, calls, timers, runtime,
    hook(value) { hook = value; }, state(value) { current = value; }, foreground(value) { foreground = value; },
    syncPosts: () => calls.filter(call => call.method === "POST" && call.url === "/api/randomrealm/music-order-sync") };
}

const randomRealmPanel = html.slice(html.indexOf('data-module-panel="randomrealm"'), html.indexOf('data-module-panel="music"'));
assert.equal([...html.matchAll(/id="syncRandomRealmMusicOrder"/g)].length, 1);
assert.match(randomRealmPanel, /id="syncRandomRealmMusicOrder" class="ghost-button"/);
assert.match(randomRealmPanel, /id="randomRealmMusicOrderStatus"[^>]*aria-live="polite"/);

{
  const h = harness(), first = deferred();
  h.hook(call => call.url === "/api/music/state" && h.calls.length === 1 ? first.promise : undefined);
  const a = h.persistMusicStateNow();
  h.state({ order: ["B", "A"] });
  const b = h.persistMusicStateNow();
  await settle();
  assert.equal(h.calls.length, 1, "later snapshot overlapped an earlier save");
  first.resolve(response({ ok: false, staleClient: true }));
  assert.equal(await a, false);
  assert.equal(await b, true, "later snapshot was lost after the earlier rejection");
  assert.deepEqual(h.calls.map(call => call.payload.order), [["A", "B"], ["B", "A"]]);
}
{
  const h = harness(), first = deferred(), second = deferred();
  let saves = 0;
  h.hook(call => {
    if (call.url === "/api/music/state") return ++saves === 1 ? first.promise : second.promise;
  });
  h.persistMusicStateSoon();
  assert.ok([...h.timers.values()].some(timer => timer.delay === 80));
  const syncing = h.syncRandomRealmMusicOrder();
  await settle();
  assert.equal(h.syncPosts().length, 0, "sync ran before the pending sort save");
  h.state({ order: ["B", "A"] });
  const later = h.persistMusicStateNow();
  first.resolve(response({ ok: false }));
  await settle();
  assert.equal(h.syncPosts().length, 0, "sync skipped a newer in-flight snapshot");
  second.resolve(response({ ok: true }));
  assert.equal(await later, true);
  await syncing;
  assert.equal(h.syncPosts().length, 1);
  assert.deepEqual(h.calls.filter(call => call.url === "/api/music/state").at(-1).payload.order, ["B", "A"]);
  assert.equal(h.status(), "pending", "queued write falsely became Applied");
  assert.ok([...h.timers.values()].some(timer => timer.delay === 2000));
  h.foreground(false);
  h.scheduleRandomRealmMusicOrderPoll();
  assert.equal(h.timers.size, 0, "hidden module kept polling");
}
{
  const h = harness();
  h.hook(call => call.url === "/api/music/state" ? response({ ok: false, staleClient: true }) : undefined);
  h.persistMusicStateSoon();
  await h.syncRandomRealmMusicOrder();
  assert.equal(h.syncPosts().length, 0, "failed save still sent a game request");
  assert.match(h.runtime.els.randomRealmMusicOrderStatus.textContent, /SaveFailed/);
  assert.equal(h.runtime.els.syncRandomRealmMusicOrder.disabled, false);
  h.hook(null);
  await h.syncRandomRealmMusicOrder();
  assert.equal(h.syncPosts().length, 1, "manual retry did not retry the current save");
}
{
  const h = harness(), oldStatus = deferred();
  h.hook(call => call.method !== "POST" ? oldStatus.promise : undefined);
  const old = h.loadRandomRealmMusicOrderStatus();
  await h.syncRandomRealmMusicOrder();
  oldStatus.resolve(response({ requestId: "old-request", status: "applied" }));
  await old;
  assert.equal(h.status(), "pending", "late earlier poll overwrote this request's status");
  assert.equal(h.calls.filter(call => call.url === "/api/music/state").length, 0,
    "RandomRealm-only session overwrote current disk music state");
}
console.log("PASS music order UI: serial snapshots, real save barrier, retry, matching status generation, bounded foreground polling");
