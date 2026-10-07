#!/usr/bin/env node
// Isolated browser behavior: no repository mutation, remote request or installed data access.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { randomUUID } from "node:crypto";
const source = readFileSync(new URL("../console-developer-update.js", import.meta.url), "utf8");
const BASE = "/api/console/developer-update";
const settle = async () => { for (let n = 0; n < 12; n++) await new Promise(resolve => setImmediate(resolve)); };
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const response = (value, status = 200) => ({ ok: status >= 200 && status < 300, status, async json() { return structuredClone(value); } });
const receipt = (requestId, status = "success", extra = {}) => ({ requestId, status, action: "update", actionId: "", phase: status === "working" ? "summary" : "done", summary: "Improve local Console changes", commitSha: "a".repeat(40), committed: !["noop", "conflict", "commit_failed", "not_found"].includes(status), pushed: status === "success", error: "", canRetryPush: status === "push_failed", updatedAt: "2026-10-07T02:00:00Z", ...extra });
function harness(overrides = {}) {
  let document;
  class Element {
    constructor(tag = "div") { this.tagName = tag.toUpperCase(); this.children = []; this.listeners = new Map(); this.attributes = {}; this.dataset = {}; this.hidden = false; this.disabled = false; this.open = false; this.checked = false; this.value = ""; this.className = ""; this._text = ""; this.isConnected = true; this.classList = { add: value => { this.className += ` ${value}`; } }; }
    append(...items) { for (const item of items) { this.children.push(item); item.parentElement = this; } }
    replaceChildren(...items) { this.children.forEach(child => { child.parentElement = null; }); this.children = []; this._text = ""; this.append(...items); }
    set textContent(value) { this.replaceChildren(); this._text = String(value); }
    get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
    set innerHTML(value) { throw new Error(`Untrusted HTML assignment: ${value}`); }
    setAttribute(name, value) { this.attributes[name] = String(value); }
    removeAttribute(name) { delete this.attributes[name]; delete this[name]; }
    addEventListener(name, handler) { if (!this.listeners.has(name)) this.listeners.set(name, []); this.listeners.get(name).push(handler); }
    fire(name, fields = {}) { const event = { target: this, preventDefault() { this.prevented = true; }, ...fields }; for (const handler of this.listeners.get(name) || []) handler(event); return event; }
    click() { if (!this.disabled) { document.activeElement = this; this.fire("click"); } }
    focus() { document.activeElement = this; }
    showModal() { this.open = true; }
    close() { this.open = false; this.fire("close"); }
    getBoundingClientRect() { return { left: 10, top: 10, right: 310, bottom: 700 }; }
  }
  const top = new Element("button"), settings = new Element("button"), dialog = new Element("dialog"), body = new Element("body"), docEvents = new Map();
  top.id = "consoleDeveloperModeTop"; settings.id = "consoleDeveloperSettingsTop"; dialog.id = "consoleDeveloperDialog";
  const elements = new Map([[top.id, top], [settings.id, settings], [dialog.id, dialog]]);
  document = { body, readyState: "loading", activeElement: top, documentElement: { lang: "zh-CN" }, createElement: tag => new Element(tag), getElementById: id => elements.get(id) || null, addEventListener(name, handler) { docEvents.set(name, handler); } };
  const snapshot = { allowed: true, enabled: true, sourceRoot: "D:/source/Console", sourceVersion: "1.0.78", runtimeVersion: "1.0.77", repoName: "tx74666/CodexControlConsole", repositoryWebUrl: "https://github.com/tx74666/CodexControlConsole", branch: "main", changedCount: 2, changes: [{ path: "one.js", status: " M", kind: "tracked", bytes: 10 }, { path: "new.css", status: "??", kind: "new", bytes: 20 }], head: "b".repeat(40), fingerprint: "preview-fingerprint", canUpdate: true, blockingReason: "", operation: null, ...overrides };
  const calls = [], timers = new Map(); let timerId = 0, hook = null;
  const runtime = { document, URL, AbortController, TypeError, Date, crypto: { randomUUID }, window: { setTimeout(fn, delay) { const id = ++timerId; timers.set(id, { fn, delay }); return id; }, clearTimeout(id) { timers.delete(id); } }, async fetch(url, options) {
    const call = { url, ...options, payload: options.body ? JSON.parse(options.body) : undefined }; calls.push(call);
    const answer = hook?.(call); if (answer !== undefined) return await answer;
    if (url === BASE) return response(snapshot);
    if (url === `${BASE}/config`) { Object.assign(snapshot, call.payload); return response(snapshot); }
    if (url === `${BASE}/run`) { const op = receipt(call.payload.requestId, "success", { action: call.payload.action, actionId: call.payload.actionId || "" }); snapshot.operation = op; snapshot.changedCount = 0; snapshot.changes = []; snapshot.canUpdate = false; snapshot.fingerprint = "after-update"; return response(op); }
    if (url.startsWith(`${BASE}/operation?`)) return response(snapshot.operation || receipt(new URL(url, "http://fixture.test").searchParams.get("requestId"), "not_found", { summary: "", commitSha: "", committed: false }));
    throw new Error(`Unexpected endpoint ${url}`);
  } };
  runInNewContext(source, runtime);
  const panel = runtime.window.ConsoleDeveloperUpdate.mount({ button: top, settingsButton: settings, dialog });
  function all(tag, start = dialog) { const result = []; function visit(node) { if (!tag || node.tagName === tag.toUpperCase()) result.push(node); node.children.forEach(visit); } visit(start); return result; }
  const byText = text => all("button").find(node => node.textContent === text), byClass = name => all().find(node => node.className.split(/\s+/).includes(name));
  return { panel, top, settings, dialog, document, runtime, snapshot, calls, timers, all, byText, byClass, enabled: () => all("input").find(node => node.type === "checkbox"), path: () => all("input").find(node => node.type === "text"), hook(value) { hook = value; }, posts: () => calls.filter(call => call.method === "POST"), runPosts: () => calls.filter(call => call.url === `${BASE}/run`), async poll() { const timer = [...timers.entries()].find(([, timer]) => timer.delay === 1200); assert.ok(timer, "expected one operation polling timer"); timers.delete(timer[0]); timer[1].fn(); await settle(); } };
}
let count = 0;
async function test(name, run) { await run(); count++; console.log(`PASS ${name}`); }
await test("only real server capability reveals the entry and static edition cannot authorize it", async () => {
  const h = harness({ allowed: false }); assert.equal(h.top.hidden, true); await settle(); assert.equal(h.top.hidden, true); assert.equal(h.settings.hidden, true); h.top.fire("click"); await settle(); assert.equal(h.dialog.open, false); assert.equal(h.posts().length, 0); assert.equal(h.calls.length, 1);
  assert.doesNotMatch(source, /edition=|localStorage|document\.cookie|\.innerHTML|\/api\/(?:workflow|phone|product|update)/);
});
await test("opening developer settings only reads status and distinguishes source from running version", async () => {
  const h = harness(); await settle(); assert.equal(h.top.textContent, "Update · v1.0.78"); assert.equal(h.settings.hidden, false); h.settings.click(); await settle();
  assert.equal(h.dialog.open, true); assert.equal(h.posts().length, 0); assert.equal(h.calls.length, 2); assert.match(h.dialog.textContent, /本机源码 · 1.0.78/); assert.match(h.dialog.textContent, /当前运行 · 1.0.77/); assert.match(h.dialog.textContent, /分支 · main/); assert.match(h.dialog.textContent, /one.js/); assert.equal(h.document.activeElement, h.byClass("console-developer-close"));
  for (const call of h.calls) { assert.equal(call.method, "GET"); assert.equal(call.cache, "no-store"); assert.equal(call.credentials, "same-origin"); assert.equal(call.redirect, "error"); }
});
await test("one top click refreshes first and submits once while repeated top/dialog clicks cannot duplicate it", async () => {
  const h = harness(), gate = deferred(); await settle(); h.hook(call => call.url === `${BASE}/run` ? gate.promise : undefined); h.top.click(); h.top.fire("click"); await settle();
  assert.equal(h.runPosts().length, 1); const sent = h.runPosts()[0].payload; assert.match(sent.requestId, /^[0-9a-f-]{36}$/); assert.equal(sent.stateFingerprint, "preview-fingerprint"); assert.equal(sent.action, "update"); assert.equal(sent.actionId, undefined); assert.equal(h.top.disabled, true); assert.equal(h.settings.disabled, true); h.byText("Update").fire("click"); assert.equal(h.runPosts().length, 1);
  const done = receipt(sent.requestId); h.snapshot.operation = done; h.snapshot.changedCount = 0; h.snapshot.canUpdate = false; gate.resolve(response(done)); await settle(); assert.match(h.dialog.textContent, /源码已同步到 GitHub/); assert.match(h.dialog.textContent, /aaaaaaaaaaaa/); assert.equal(h.runPosts().length, 1); assert.equal([...h.timers.values()].some(timer => timer.delay === 1200), false);
});
await test("top action uses the fresh preview rather than stale source fingerprint", async () => {
  const h = harness(); await settle(); h.snapshot.fingerprint = "new-preview"; h.snapshot.changedCount = 3; h.top.click(); await settle(); assert.equal(h.runPosts().length, 1); assert.equal(h.runPosts()[0].payload.stateFingerprint, "new-preview");
});
await test("clean status is a no-op without an empty commit or a run request", async () => {
  const h = harness({ canUpdate: false, changedCount: 0, changes: [] }); await settle(); h.top.click(); await settle(); assert.equal(h.runPosts().length, 0); assert.match(h.byClass("console-developer-status").textContent, /没有待同步/); assert.equal(h.byText("Update").disabled, true);
});
await test("clean working files still show cached outgoing commits and their included file scope", async () => {
  const h = harness({ changedCount: 0, changes: [], outgoingCommitCount: 2, outgoingChanges: [{ path: "already-committed.js", status: "committed", kind: "committed", bytes: 0 }] }); await settle(); h.settings.click(); await settle(); assert.match(h.dialog.textContent, /本机已提交待上传 · 2 条（本机缓存）/); assert.match(h.dialog.textContent, /已提交already-committed.js/); assert.equal(h.posts().length, 0); assert.equal(h.byText("Update").disabled, false);
});
await test("mode toggle and private source binding mutate only after their explicit gestures", async () => {
  const h = harness({ enabled: false, sourceRoot: "" }); await settle(); assert.equal(h.top.textContent, "开发者模式"); h.top.click(); await settle(); assert.equal(h.posts().length, 0); assert.equal(h.byText("Update").hidden, true); assert.equal(h.byClass("console-developer-settings").open, true);
  h.path().value = "D:/private/source"; h.byText("保存文件夹").click(); await settle(); assert.deepEqual(h.posts()[0].payload, { enabled: false, sourceRoot: "D:/private/source" }); h.enabled().checked = true; h.enabled().fire("change"); await settle(); assert.deepEqual(h.posts()[1].payload, { enabled: true }); assert.equal(h.top.textContent, "Update · v1.0.78"); assert.equal(h.byText("Update").hidden, false); assert.equal(h.runPosts().length, 0);
});
await test("failed configuration does not pretend the developer mode was saved", async () => {
  const h = harness({ enabled: false }); await settle(); h.top.click(); await settle(); h.hook(call => call.url.endsWith("/config") ? response({ error: "not saved" }, 409) : undefined); h.enabled().checked = true; h.enabled().fire("change"); await settle(); assert.equal(h.enabled().checked, false); assert.equal(h.top.textContent, "开发者模式"); assert.match(h.byClass("console-developer-status").textContent, /设置未能保存/); assert.equal(h.runPosts().length, 0);
});
await test("late status JSON from an old modal cannot replace the reopened repository view", async () => {
  const h = harness(), gate = deferred(); await settle(); let delayed = true; h.hook(call => call.url === BASE && delayed ? (delayed = false, gate.promise) : undefined); const oldOpen = h.panel.open(); h.panel.close(); h.snapshot.branch = "new-branch"; await h.panel.open(); gate.resolve(response({ ...h.snapshot, branch: "old-branch" })); await oldOpen; await settle(); assert.match(h.dialog.textContent, /new-branch/); assert.doesNotMatch(h.dialog.textContent, /old-branch/); assert.equal(h.posts().length, 0);
});
await test("capability revoked during fresh top GET cannot submit", async () => {
  const h = harness(); await settle(); h.snapshot.allowed = false; h.top.click(); await settle(); assert.equal(h.runPosts().length, 0); assert.equal(h.top.hidden, true); assert.equal(h.settings.hidden, true); assert.equal(h.dialog.open, false);
});
await test("terminal conflict and commit failure retain accurate results and allow a new explicit attempt", async () => {
  for (const status of ["conflict", "commit_failed"]) {
    const h = harness(); await settle(); let attempt = 0; h.hook(call => { if (call.url !== `${BASE}/run`) return; if (++attempt > 1) return; const op = receipt(call.payload.requestId, status, { commitSha: "", error: "The original changes remain" }); h.snapshot.operation = op; return response(op); });
    h.top.click(); await settle(); const first = h.runPosts()[0].payload; assert.match(h.byClass("console-developer-status").textContent, status === "conflict" ? /已变化/ : /提交未完成/); assert.equal(h.byText("Update").disabled, false); h.byText("Update").click(); await settle(); assert.equal(h.runPosts().length, 2); assert.notEqual(h.runPosts()[1].payload.requestId, first.requestId); assert.equal(h.runPosts()[1].payload.action, "update");
  }
});
await test("a lost original run response checks the same request with GET and never resends it", async () => {
  const h = harness(); await settle(); h.hook(call => { if (call.url === `${BASE}/run`) throw new TypeError("response lost"); }); h.top.click(); await settle(); const id = h.runPosts()[0].payload.requestId;
  assert.equal(h.runPosts().length, 1); assert.ok(h.calls.some(call => call.url === `${BASE}/operation?requestId=${id}` && call.method === "GET")); assert.equal(h.byText("Update").disabled, true); h.byText("核对请求结果").click(); await settle(); assert.equal(h.runPosts().length, 1); assert.match(h.dialog.textContent, /不会自动重新发送/); assert.equal([...h.timers.values()].some(timer => timer.delay === 1200), false);
});
await test("a late accepted original run can be recovered without creating a second action", async () => {
  const h = harness(); await settle(); h.hook(call => { if (call.url === `${BASE}/run`) { h.snapshot.operation = receipt(call.payload.requestId, "working"); throw new TypeError("receipt lost"); } }); h.top.click(); await settle(); assert.equal(h.runPosts().length, 1); assert.equal(h.byText("Update").disabled, true); const id = h.runPosts()[0].payload.requestId; h.snapshot.operation = receipt(id); h.snapshot.canUpdate = false; await h.poll(); assert.match(h.dialog.textContent, /源码已同步/); assert.equal(h.runPosts().length, 1); assert.equal([...h.timers.values()].some(timer => timer.delay === 1200), false);
});
await test("push failure keeps the original SHA and requires a separate explicit retry action", async () => {
  const id = randomUUID(), old = receipt(id, "push_failed"), h = harness({ operation: old }); await settle(); h.top.click(); await settle(); assert.equal(h.runPosts().length, 0); assert.match(h.dialog.textContent, /已提交，尚未推送/); assert.match(h.dialog.textContent, /aaaaaaaaaaaa/); assert.equal(h.byText("Update").hidden, true); h.byText("继续上传").click(); await settle(); const body = h.runPosts()[0].payload; assert.equal(body.requestId, id); assert.equal(body.action, "retry"); assert.match(body.actionId, /^[0-9a-f-]{36}$/); assert.equal(h.runPosts().length, 1);
});
await test("unknown push uses an explicit verify action without silently retrying the push", async () => {
  const id = randomUUID(), h = harness({ operation: receipt(id, "unknown") }); await settle(); h.top.click(); await settle(); assert.equal(h.runPosts().length, 0); assert.equal(h.byText("Update").disabled, true); assert.equal([...h.timers.values()].some(timer => timer.delay === 1200), false);
  h.byText("核对推送结果").click(); await settle(); const sent = h.runPosts()[0].payload; assert.equal(sent.requestId, id); assert.equal(sent.action, "verify"); assert.match(sent.actionId, /^[0-9a-f-]{36}$/); assert.equal(h.runPosts().length, 1);
});
await test("lost recovery action does not mistake an older receipt for permission to retry", async () => {
  const id = randomUUID(), h = harness({ operation: receipt(id, "push_failed") }); await settle(); await h.panel.open(); h.hook(call => { if (call.url === `${BASE}/run`) throw new TypeError("retry response lost"); }); h.byText("继续上传").click(); await settle(); const sent = h.runPosts()[0].payload;
  assert.equal(sent.action, "retry"); assert.equal(h.byText("Update").disabled, true); h.byText("核对请求结果").click(); await settle(); assert.equal(h.runPosts().length, 1); assert.equal(h.byText("Update").disabled, true);
  h.snapshot.operation = receipt(id, "success", { action: "retry", actionId: sent.actionId }); h.snapshot.canUpdate = false; h.byText("核对请求结果").click(); await settle(); assert.match(h.dialog.textContent, /源码已同步/); assert.equal(h.runPosts().length, 1);
});
await test("an interrupted unknown request without a confirmed SHA can be explicitly checked without replay", async () => {
  const id = randomUUID(), h = harness({ operation: receipt(id, "unknown", { committed: false, commitSha: "" }) }); await settle(); h.top.click(); await settle(); assert.equal(h.runPosts().length, 0); assert.equal(h.byText("Update").disabled, true); assert.equal(h.byText("核对推送结果").hidden, false);
  h.hook(call => { if (call.url !== `${BASE}/run`) return; const op = receipt(id, "conflict", { committed: false, commitSha: "", action: "verify", actionId: call.payload.actionId }); h.snapshot.operation = op; return response(op); }); h.byText("核对推送结果").click(); await settle(); assert.equal(h.runPosts().length, 1); assert.equal(h.runPosts()[0].payload.requestId, id); assert.equal(h.runPosts()[0].payload.action, "verify"); assert.equal(h.byText("Update").disabled, false); assert.equal([...h.timers.values()].some(timer => timer.delay === 1200), false);
});
await test("closing a working modal stops polling and reopening restores the operation by GET", async () => {
  const id = randomUUID(), h = harness({ operation: receipt(id, "working") }); await settle(); await h.panel.open(); assert.equal([...h.timers.values()].filter(timer => timer.delay === 1200).length, 1); h.panel.close(); assert.equal([...h.timers.values()].some(timer => timer.delay === 1200), false); const before = h.calls.length; await settle(); assert.equal(h.calls.length, before); assert.equal(h.top.disabled, false);
  h.snapshot.operation = receipt(id); h.snapshot.canUpdate = false; h.top.click(); await settle(); assert.equal(h.runPosts().length, 0); assert.match(h.dialog.textContent, /源码已同步/); assert.equal([...h.timers.values()].some(timer => timer.delay === 1200), false);
});
await test("a POST completing after close cannot reopen the modal or poll in the background", async () => {
  const h = harness(), gate = deferred(); await settle(); h.hook(call => call.url === `${BASE}/run` ? gate.promise : undefined); h.top.click(); await settle(); const id = h.runPosts()[0].payload.requestId; h.panel.close(); gate.resolve(response(receipt(id, "working"))); await settle(); assert.equal(h.dialog.open, false); assert.equal([...h.timers.values()].some(timer => timer.delay === 1200), false); assert.equal(h.runPosts().length, 1); assert.equal(h.document.activeElement, h.top); assert.equal(h.top.disabled, false); h.hook(null); h.snapshot.operation = receipt(id); h.snapshot.canUpdate = false; h.top.click(); await settle(); assert.equal(h.runPosts().length, 1); assert.match(h.dialog.textContent, /源码已同步/);
});
await test("a synchronously rejected recovery preserves the confirmed commit and waits for a fresh preview", async () => {
  const id = randomUUID(), h = harness({ operation: receipt(id, "push_failed") }); await settle(); await h.panel.open(); h.hook(call => call.url === `${BASE}/run` ? response({ error: "预览之后源码已变化，请刷新后重新确认。", code: "developer_update_invalid" }, 400) : undefined); h.byText("继续上传").click(); await settle(); assert.match(h.dialog.textContent, /aaaaaaaaaaaa/); assert.match(h.byClass("console-developer-status").textContent, /源码已变化/); assert.equal(h.byText("继续上传").disabled, true); assert.equal(h.byText("Update").hidden, true); assert.equal(h.runPosts().length, 1); h.byText("重新读取").click(); await settle(); assert.equal(h.byText("继续上传").disabled, false); assert.equal(h.runPosts().length, 1);
});
await test("a confirmed commit in conflict must be verified before any new update", async () => {
  for (const status of ["conflict", "commit_failed"]) {
    const id = randomUUID(), h = harness({ operation: receipt(id, status, { committed: true }) }); await settle(); h.top.click(); await settle(); assert.equal(h.runPosts().length, 0); assert.equal(h.byText("Update").disabled, true); assert.equal(h.enabled().disabled, true); h.byText("核对推送结果").click(); await settle(); assert.equal(h.runPosts().length, 1); assert.equal(h.runPosts()[0].payload.action, "verify"); assert.equal(h.runPosts()[0].payload.requestId, id);
  }
});
await test("an already pushed commit with pending local index is described accurately", async () => {
  const h = harness({ operation: receipt(randomUUID(), "push_failed", { pushed: true, indexPending: true, phase: "index_pending" }) }); await settle(); h.top.click(); await settle(); assert.equal(h.runPosts().length, 0); assert.match(h.byClass("console-developer-status").textContent, /源码已推送/); assert.doesNotMatch(h.byClass("console-developer-status").textContent, /尚未推送/); assert.equal(h.byText("完成核对").hidden, false); assert.equal(h.enabled().disabled, true); assert.equal(h.path().disabled, true); assert.equal(h.byText("保存文件夹").disabled, true); h.enabled().fire("change"); h.byText("保存文件夹").fire("click"); await settle(); assert.equal(h.posts().length, 0);
});
await test("all remote text stays literal and only an uncredentialed GitHub repository URL becomes a link", async () => {
  for (const url of ["javascript:alert(1)", "https://secret:token@github.com/owner/repo", "https://github.com.evil.test/owner/repo", "https://github.com/owner/repo?token=secret"]) {
    const h = harness({ repositoryWebUrl: url, repoName: "<img onerror=alert(1)>", changes: [{ path: "<script>alert(1)</script>", status: "<svg>", kind: "new" }], operation: receipt(randomUUID(), "success", { summary: "<img src=x onerror=alert(1)>", error: "<script>literal</script>" }) }); await settle(); await h.panel.open();
    assert.equal(h.all("a")[0].href, undefined); assert.match(h.dialog.textContent, /<script>alert\(1\)<\/script>/); assert.match(h.dialog.textContent, /<img src=x onerror=alert\(1\)>/); assert.equal(h.all("script").length, 0); assert.equal(h.all("img").length, 0);
  }
  const h = harness(); await settle(); await h.panel.open(); assert.equal(h.all("a")[0].href, "https://github.com/tx74666/CodexControlConsole"); assert.equal(h.all("a")[0].rel, "noopener noreferrer");
});
await test("native Escape close restores focus and component mounting is idempotent", async () => {
  const h = harness(); await settle(); const same = h.runtime.window.ConsoleDeveloperUpdate.mount({ button: h.top, settingsButton: h.settings, dialog: h.dialog }); assert.equal(same, h.panel); const before = h.calls.length; h.settings.click(); await settle(); const event = h.dialog.fire("cancel"); assert.equal(event.prevented, true); assert.equal(h.dialog.open, false); assert.equal(h.document.activeElement, h.settings); assert.equal(h.top.attributes["aria-expanded"], "false"); assert.equal(h.calls.length, before + 1);
});
await test("destroyed component ignores late status and leaves no polling timers", async () => {
  const h = harness(), gate = deferred(); await settle(); h.hook(call => call.url === BASE ? gate.promise : undefined); const opening = h.panel.open(); h.panel.destroy(); gate.resolve(response(h.snapshot)); await opening; await settle(); assert.equal(h.top.hidden, true); assert.equal(h.dialog.open, false); assert.equal([...h.timers.values()].some(timer => timer.delay === 1200), false); assert.equal(h.posts().length, 0);
});
console.log(`${count} developer update UI behavior checks passed.`);
