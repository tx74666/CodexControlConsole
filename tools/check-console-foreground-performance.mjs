#!/usr/bin/env node
// Pure fixtures: no browser, service, user data, native bridge, or network.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
function extract(name) {
  const start = source.search(new RegExp(`(?:async )?function ${name}\\(`));
  assert.ok(start >= 0, `Missing ${name}`);
  const end = source.slice(start + 1).search(/\n(?:async )?function /);
  return source.slice(start, end < 0 ? undefined : start + 1 + end);
}
const defer = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const flush = async () => { for (let index = 0; index < 15; index++) await Promise.resolve(); };
function timers() {
  let next = 1;
  const pending = new Map();
  return {
    pending,
    set(callback, delay) { const id = next++; pending.set(id, { callback, delay }); return id; },
    clear(id) { pending.delete(id); },
    async run(id = pending.keys().next().value) { const item = pending.get(id); assert.ok(item, "Missing timer"); pending.delete(id); await item.callback(); }
  };
}
let count = 0;
async function test(name, action) { await action(); console.log(`PASS ${name}`); count++; }

function workspace() {
  const calls = [], idle = timers(), clock = timers(), gates = new Map(), outcomes = new Map();
  const runtime = {
    Promise, Map, runtimeActivityReady: true, module: "workspace", activeConsoleView: "work", hasWorkspace: true,
    els: { desktopLayoutPlan: {}, builtinMediaMusicSync: {}, feedbackForm: {}, githubDownloadsMeta: {} },
    desktopLayoutState: null, desktopLayoutBusy: false, builtinMediaState: null, feedbackConfigLoaded: false,
    feedbackConfigBusy: false, feedbackInboxBusy: false, downloadMapLoaded: false, downloadMapBusy: false,
    blenderGithubShareState: null, blenderGithubBusy: false, hasMaterialWorkspace: true, downloadIntakeEnabled: true,
    loadingConsoleWorkspaceViews: new Map(), workspaceDesktopLayoutIdleCallback: 0, workspaceDesktopLayoutScheduleTimer: 0,
    githubDownloadsInfo: null, githubDownloadsLoaded: false, githubDownloadsLoading: null,
    window: { requestIdleCallback: idle.set, cancelIdleCallback: idle.clear, setTimeout: clock.set, clearTimeout: clock.clear },
    isModuleForeground: id => runtime.module === id && !runtime.hidden,
    syncConsoleTransferActivity() { calls.push("transfer-activity"); },
    hasBlenderGithubShare: () => true, feedbackInboxPollingAllowed: () => false,
    text: key => key, renderGithubDownloads() { calls.push("github-render"); }
  };
  for (const [name, label, loaded] of [
    ["loadDesktopLayout", "layout", "desktopLayoutState"], ["loadBuiltinMedia", "media", "builtinMediaState"],
    ["loadFeedbackConfig", "feedback", "feedbackConfigLoaded"], ["loadDownloadMap", "map", "downloadMapLoaded"],
    ["loadBlenderGithubShare", "share", "blenderGithubShareState"], ["loadMaterialCandidates", "materials"],
    ["loadDocumentLibrary", "documents"], ["loadFeedbackInbox", "inbox"]
  ]) runtime[name] = async () => {
    calls.push(label);
    if (label === "layout") runtime.desktopLayoutBusy = true;
    if (gates.has(label)) await gates.get(label).promise;
    const succeeded = outcomes.get(label) !== false;
    if (succeeded && loaded) runtime[loaded] = true;
    if (label === "layout") runtime.desktopLayoutBusy = false;
    return succeeded;
  };
  runtime.fetch = async () => {
    calls.push("github");
    if (gates.has("github")) await gates.get("github").promise;
    return { ok: outcomes.get("github") !== false, status: 503, json: async () => ({ configured: true, url: "https://example.test/download" }) };
  };
  const names = ["loadModuleData", "cancelWorkspaceDesktopLayoutInitialization", "scheduleWorkspaceDesktopLayoutInitialization", "loadActiveConsoleWorkspaceViewData", "loadGithubDownloadsInfo"];
  const api = runInNewContext(`${names.map(extract).join("\n")}\n({${names.join(",")}})`, runtime);
  return { runtime, api, calls, idle, clock, hold(label) { const gate = defer(); gates.set(label, gate); return gate; }, fail(label, value = true) { outcomes.set(label, !value); }, clear() { calls.length = 0; } };
}

await test("Work and Transfer do not load hidden workspace controls", async () => {
  for (const view of ["work", "transfer"]) {
    const h = workspace(); h.runtime.activeConsoleView = view;
    assert.equal(await h.api.loadModuleData("workspace"), true);
    assert.deepEqual(h.calls, ["transfer-activity"]);
    assert.equal(h.idle.pending.size, 1, "Existing layout history still initializes in idle time");
  }
});
await test("Document loads its own data without awaiting the layout initializer", async () => {
  const h = workspace(); h.runtime.activeConsoleView = "document"; h.hold("layout");
  assert.equal(await h.api.loadModuleData("workspace"), true);
  assert.deepEqual(h.calls, ["documents"]);
});
await test("Existing automatic layout history still starts without opening Common", async () => {
  const h = workspace(); await h.api.loadModuleData("workspace"); h.clear();
  await h.idle.run(); await flush(); assert.deepEqual(h.calls, ["layout"]);
  h.api.scheduleWorkspaceDesktopLayoutInitialization(); assert.equal(h.idle.pending.size, 0);
});
await test("Common cancels pending layout initialization and coalesces concurrent loads", async () => {
  const h = workspace(); await h.api.loadModuleData("workspace"); h.clear();
  const gate = h.hold("media"); h.runtime.activeConsoleView = "common";
  const first = h.api.loadActiveConsoleWorkspaceViewData(), second = h.api.loadActiveConsoleWorkspaceViewData();
  await flush(); assert.deepEqual(h.calls, ["layout", "media", "materials"]); assert.equal(h.idle.pending.size, 0);
  gate.resolve(); assert.equal(await first, true); assert.equal(await second, true);
  assert.equal(h.runtime.loadingConsoleWorkspaceViews.size, 0);
});
await test("Failed Common data remains retryable when the subpage is revisited", async () => {
  const h = workspace(); h.runtime.activeConsoleView = "common"; h.fail("media");
  assert.equal(await h.api.loadActiveConsoleWorkspaceViewData(), false); h.clear(); h.fail("media", false);
  assert.equal(await h.api.loadActiveConsoleWorkspaceViewData(), true);
  assert.deepEqual(h.calls, ["media", "materials"]);
});
await test("Common does not duplicate layout work already started in idle time", async () => {
  const h = workspace(), gate = h.hold("layout");
  h.api.scheduleWorkspaceDesktopLayoutInitialization(); await h.idle.run(); await flush();
  // Mirror the production loader's existing busy guard for this concurrent read.
  const original = h.runtime.loadDesktopLayout;
  h.runtime.loadDesktopLayout = (...args) => h.runtime.desktopLayoutBusy ? Promise.resolve(Boolean(h.runtime.desktopLayoutState)) : original(...args);
  h.runtime.activeConsoleView = "common"; await h.api.loadActiveConsoleWorkspaceViewData();
  assert.equal(h.calls.filter(call => call === "layout").length, 1); gate.resolve(); await flush();
});
await test("Collaboration loads its controls once and shares pending GitHub discovery", async () => {
  const h = workspace(), gate = h.hold("github"); h.runtime.activeConsoleView = "collaboration";
  const first = h.api.loadActiveConsoleWorkspaceViewData(), second = h.api.loadActiveConsoleWorkspaceViewData();
  await flush(); assert.deepEqual(h.calls, ["feedback", "map", "share", "github"]);
  const direct = h.api.loadGithubDownloadsInfo(); await flush(); assert.equal(h.calls.filter(call => call === "github").length, 1);
  gate.resolve(); assert.equal(await first, true); assert.equal(await second, true); assert.equal(await direct, true);
  h.clear(); await h.api.loadActiveConsoleWorkspaceViewData(); assert.deepEqual(h.calls, []);
});
await test("GitHub discovery failure clears the pending guard and allows retry", async () => {
  const h = workspace(); h.fail("github"); assert.equal(await h.api.loadGithubDownloadsInfo(), false);
  assert.equal(h.runtime.githubDownloadsLoaded, false); assert.equal(h.runtime.githubDownloadsLoading, null);
  h.fail("github", false); assert.equal(await h.api.loadGithubDownloadsInfo(), true);
  assert.equal(h.calls.filter(call => call === "github").length, 2);
});
await test("A workspace request queued before switching subpage starts no hidden work", async () => {
  const h = workspace(); h.runtime.activeConsoleView = "common";
  const pending = h.api.loadActiveConsoleWorkspaceViewData(); h.runtime.activeConsoleView = "work";
  assert.equal(await pending, false); assert.deepEqual(h.calls, []);
});
await test("Desktop layout initialization retains the timer fallback and retry", async () => {
  const h = workspace(); delete h.runtime.window.requestIdleCallback; h.fail("layout");
  h.api.scheduleWorkspaceDesktopLayoutInitialization(); h.api.scheduleWorkspaceDesktopLayoutInitialization();
  assert.equal(h.clock.pending.size, 1); await h.clock.run(); await flush();
  h.api.scheduleWorkspaceDesktopLayoutInitialization(); assert.equal(h.clock.pending.size, 1);
});
await test("Global idle update checks and user preferences retain their existing path", async () => {
  const startup = source.slice(source.lastIndexOf("\napplyConsoleEdition(consoleEdition, { activate: false, forceRender: true });"));
  assert.ok(startup.includes("scheduleProductUpdateStatusCheck();"));
  assert.ok(extract("scheduleProductUpdateStatusCheck").includes("window.requestIdleCallback(run, { timeout: 1200 })"));
  assert.ok(extract("scheduleProductUpdateStatusCheck").includes("check: true, quiet: true"));
  assert.ok(extract("saveProductUpdatePreference").includes("autoCheck"));
  assert.ok(!extract("loadModuleData").includes("scheduleProductUpdateStatusCheck({ immediate: true })"));
});

function blender() {
  const clock = timers(), requests = [], changes = [];
  const runtime = {
    AbortController, runtimeActivityReady: true, activeBlenderView: "builder", module: "blender", document: { hidden: false },
    els: { randomRealmBlenderProject: { value: "D:/Builder.blend" }, randomRealmBlenderObject: { value: "Old" } },
    randomRealmLiveSelectionTimer: null, randomRealmLiveSelectionEpoch: 0, randomRealmLiveSelectionRequest: null,
    randomRealmLiveSelectionFailureCount: 0, randomRealmLastLiveObject: "", randomRealmLiveSelectedObjects: [],
    randomRealmObjectPickerOpen: false, randomRealmBlenderObjects: [{ name: "Old" }, { name: "New" }],
    randomRealmArtContext: {}, randomRealmSelectedOldTexture: null, randomRealmSelectedMaterial: "",
    randomRealmLiveSelectionSuccessDelayMs: 1600, randomRealmLiveSelectionFailureDelaysMs: [5000, 10000, 30000],
    window: { setTimeout: clock.set, clearTimeout: clock.clear },
    hasRandomRealmArtTools: () => true, isModuleForeground: id => runtime.module === id && !runtime.document.hidden,
    text: key => key, setRandomRealmArtStatus: message => changes.push(message),
    clearRandomRealmTextureDragFileCache() { changes.push("clear-textures"); },
    setRandomRealmObjectPickerOpen() {}, renderRandomRealmUsedTextures() { changes.push("render-textures"); },
    updateRandomRealmArtContext() { changes.push("persist-selection"); }, async refreshRandomRealmSelectedObjectTextures() { changes.push("refresh-textures"); },
    fetch(url, options) { const gate = defer(), item = { url, options, gate, reads: 0 }; requests.push(item); return gate.promise; }
  };
  const names = ["syncRandomRealmLiveSelection", "stopRandomRealmLiveSelectionPolling", "randomRealmLiveSelectionPollDelay", "randomRealmBuilderIsForeground", "syncRandomRealmLiveSelectionActivity", "startRandomRealmLiveSelectionPolling"];
  const api = runInNewContext(`${names.map(extract).join("\n")}\n({${names.join(",")}})`, runtime);
  return { runtime, api, clock, requests, changes, reply(index = 0, name = "New", extra = {}) {
    const item = requests[index]; item.gate.resolve({ ok: true, json: async () => { item.reads++; return { available: true, matchingProject: true, activeObject: { name }, selectedObjects: [{ name }], ...extra }; } });
  } };
}
await test("Only the foreground Builder starts live selection polling", async () => {
  for (const view of ["document", "character"]) {
    const h = blender(); h.runtime.activeBlenderView = view; h.api.syncRandomRealmLiveSelectionActivity({ immediate: true });
    assert.equal(h.clock.pending.size, 0); assert.equal(await h.api.syncRandomRealmLiveSelection(), false); assert.equal(h.requests.length, 0);
  }
  const h = blender(); h.runtime.document.hidden = true; h.api.syncRandomRealmLiveSelectionActivity(); assert.equal(h.clock.pending.size, 0);
});
await test("Builder resumes immediately and retains adaptive polling", async () => {
  const h = blender(); h.api.syncRandomRealmLiveSelectionActivity({ immediate: true });
  assert.equal([...h.clock.pending.values()][0].delay, 0);
  const running = h.clock.run(); h.reply(); await running;
  assert.equal([...h.clock.pending.values()][0].delay, 1600); assert.equal(h.runtime.els.randomRealmBlenderObject.value, "New");
  assert.deepEqual([h.api.randomRealmLiveSelectionPollDelay(false), h.api.randomRealmLiveSelectionPollDelay(false), h.api.randomRealmLiveSelectionPollDelay(false)], [5000, 10000, 30000]);
});
await test("Simultaneous live selection reads share one request and one JSON body", async () => {
  const h = blender(), first = h.api.syncRandomRealmLiveSelection(), second = h.api.syncRandomRealmLiveSelection({ quiet: false });
  assert.equal(h.requests.length, 1); h.reply(); assert.equal(await first, true); assert.equal(await second, true);
  assert.equal(h.requests[0].reads, 1); assert.equal(h.changes.filter(item => item === "render-textures").length, 1);
  assert.ok(h.changes.includes("refresh-textures"));
});
await test("Leaving Builder cancels pending work and ignores a late selection response", async () => {
  const h = blender(), pending = h.api.syncRandomRealmLiveSelection();
  h.runtime.activeBlenderView = "document"; h.api.syncRandomRealmLiveSelectionActivity();
  assert.equal(h.requests[0].options.signal.aborted, true); h.reply(); assert.equal(await pending, false);
  assert.equal(h.runtime.els.randomRealmBlenderObject.value, "Old"); assert.deepEqual(h.changes, []);
});
await test("Leaving and returning cannot revive an older Builder response", async () => {
  const h = blender(), old = h.api.syncRandomRealmLiveSelection();
  h.runtime.activeBlenderView = "character"; h.api.syncRandomRealmLiveSelectionActivity();
  h.runtime.activeBlenderView = "builder"; const current = h.api.syncRandomRealmLiveSelection();
  h.reply(0); assert.equal(await old, false); assert.equal(h.runtime.els.randomRealmBlenderObject.value, "Old");
  h.reply(1); assert.equal(await current, true); assert.equal(h.runtime.els.randomRealmBlenderObject.value, "New");
});
await test("A project change rejects the previous project's live selection", async () => {
  const h = blender(), pending = h.api.syncRandomRealmLiveSelection();
  h.runtime.els.randomRealmBlenderProject.value = "D:/Other.blend"; h.reply();
  assert.equal(await pending, false); assert.deepEqual(h.changes, []);
});
await test("Returning to an earlier project cannot accept its superseded request", async () => {
  const h = blender(), old = h.api.syncRandomRealmLiveSelection();
  h.runtime.els.randomRealmBlenderProject.value = "D:/Other.blend";
  const other = h.api.syncRandomRealmLiveSelection();
  h.runtime.els.randomRealmBlenderProject.value = "D:/Builder.blend";
  h.reply(0); assert.equal(await old, false);
  h.reply(1); assert.equal(await other, false); assert.deepEqual(h.changes, []);
});
await test("A cancelled polling callback cannot restart the previous view's loop", async () => {
  const h = blender(); h.api.startRandomRealmLiveSelectionPolling({ immediate: true });
  const running = h.clock.run(); h.runtime.activeBlenderView = "document"; h.api.syncRandomRealmLiveSelectionActivity();
  h.reply(); await running; assert.equal(h.clock.pending.size, 0); assert.deepEqual(h.changes, []);
});
await test("A queued callback checks the actual view before reading the bridge", async () => {
  const h = blender(); h.api.startRandomRealmLiveSelectionPolling();
  h.runtime.activeBlenderView = "document"; await h.clock.run(); assert.equal(h.requests.length, 0);
});
await test("A previously queued cancelled callback cannot erase a newer timer", async () => {
  const h = blender(); h.api.startRandomRealmLiveSelectionPolling();
  const stale = [...h.clock.pending.values()][0].callback;
  h.api.startRandomRealmLiveSelectionPolling({ immediate: true });
  const latest = h.runtime.randomRealmLiveSelectionTimer;
  await stale(); assert.equal(h.runtime.randomRealmLiveSelectionTimer, latest); assert.equal(h.requests.length, 0);
});
await test("Subpage and project selection both resynchronize Builder activity", async () => {
  assert.ok(extract("setBlenderWorkspaceView").includes("syncRandomRealmLiveSelectionActivity({ immediate: previousView !== activeBlenderView })"));
  assert.ok(extract("selectRandomRealmBlenderProject").includes("stopRandomRealmLiveSelectionPolling();"));
  assert.ok(extract("selectRandomRealmBlenderProject").includes("syncRandomRealmLiveSelectionActivity({ immediate: true });"));
});
console.log(`${count} foreground performance checks passed`);
