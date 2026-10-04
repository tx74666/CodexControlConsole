#!/usr/bin/env node
// Isolated real-component DOM/network checks. No browser, App Tools or chat messages are sent.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
const source = readFileSync(new URL("../conversations-panel.js", import.meta.url), "utf8"), css = readFileSync(new URL("../conversations-panel.css", import.meta.url), "utf8");
const clone = value => JSON.parse(JSON.stringify(value));
const settle = async () => { for (let index = 0; index < 8; index++) await new Promise(resolve => setImmediate(resolve)); };
const defer = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const response = (value, status = 200) => ({ status, ok: status >= 200 && status < 300, async json() { return clone(value); } });
const A = "11111111-1111-4111-8111-111111111111", B = "22222222-2222-4222-8222-222222222222", C = "33333333-3333-4333-8333-333333333333", D = "44444444-4444-4444-8444-444444444444";
const thread = (id = A, patch = {}) => ({ id, title: `原会话 ${id.slice(0, 4)}`, kind: "codex", hostId: "local", status: "idle", unread: false, ...patch });
const catalog = patch => ({ projects: [], threads: [thread()], fetchedAt: new Date().toISOString(), partial: false, revision: "catalog-1", requests: [], ...patch });
const snapshot = (id = A, patch = {}) => ({ thread: thread(id), messages: [{ id: "u1", role: "user", text: "用户的真实文字\n第二行", turnId: "turn-1", status: "completed", createdAt: "2026-10-04T12:00:00Z", truncated: false }, { id: "a1", role: "assistant", text: "助手回复", turnId: "turn-1", phase: "final", status: "completed", truncated: false }], generation: 1, snapshotGeneration: 1, fetchedAt: new Date().toISOString(), partial: true, olderCursor: "older-page-2", hasMore: true, coverage: { messageCount: 2, pageCount: 1, description: "最近一页" }, requests: [], revision: "snapshot-1", ...patch });
function harness({ phone = true, list = catalog(), snapshots = new Map([[A, snapshot()]]) } = {}) {
  class Element {
    constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.listeners = new Map(); this.dataset = {}; this.attributes = {}; this.hidden = false; this.disabled = false; this._text = ""; this.open = false; this.classList = { add: name => { this.className = `${this.className || ""} ${name}`.trim(); } }; }
    append(...children) { for (const child of children) { this.children.push(child); child.parentElement = this; } }
    replaceChildren(...children) { this.children.forEach(child => { child.parentElement = null; }); this.children = []; this._text = ""; this.append(...children); }
    set textContent(value) { this.replaceChildren(); this._text = String(value); }
    get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
    set innerHTML(value) { throw Error("Conversation content must be text, never HTML"); }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    removeAttribute(key) { delete this.attributes[key]; if (key === "href") delete this.href; }
    addEventListener(name, action) { this.listeners.set(name, action); }
    fire(name, values = {}) { return this.listeners.get(name)?.({ preventDefault() {}, ...values }); }
    click() { if (!this.disabled) return this.fire("click"); }
  }
  const root = new Element("div"), calls = [], timers = new Map(), events = new Map(), connections = [], targets = [], receipts = new Map(), waits = new Map();
  let timerId = 0, auth = 0, failPath = "", statusPath = "", statusCode = 200;
  const document = { hidden: false, createElement: tag => new Element(tag), addEventListener: (name, action) => events.set(name, action) }, base = phone ? "/api/phone/workflow" : "/api/workflow";
  const runtime = { document, AbortController, Date, window: { setTimeout(action, delay) { const id = ++timerId; timers.set(id, { action, delay }); return id; }, clearTimeout(id) { timers.delete(id); } }, async fetch(url, options) {
    assert.ok(url.startsWith(`${base}/conversations`), `Only conversations endpoints are allowed: ${url}`); const path = url.slice(base.length + 1), payload = options.body ? JSON.parse(options.body) : null; calls.push({ path, payload, options });
    if (waits.has(path)) { const waiting = waits.get(path); waits.delete(path); return waiting; }
    if (path === statusPath) { statusPath = ""; return response({ error: `fixture HTTP ${statusCode}` }, statusCode); }
    const result = backend(path, payload); if (path === failPath) { failPath = ""; throw new TypeError("Connection lost after response"); } return result;
  } };
  function backend(path, payload) {
    if (path === "conversations") return response(list);
    if (path.startsWith("conversations/thread?id=")) { const id = decodeURIComponent(path.split("=")[1]); return response(snapshots.get(id) || snapshot(id, { messages: [], fetchedAt: null, coverage: { messageCount: 0, pageCount: 0 }, olderCursor: null, hasMore: false })); }
    assert.equal(path, "conversations/request"); assert.deepEqual(Object.keys(payload).sort(), ["mode", "requestId", "threadId"]); assert.match(payload.requestId, /^[a-f0-9-]{36}$/i); assert.ok(["refresh", "older"].includes(payload.mode));
    if (receipts.has(payload.requestId)) return response({ ...receipts.get(payload.requestId), duplicate: true });
    const request = { id: `request-${receipts.size + 1}`, threadId: payload.threadId, mode: payload.mode, generation: 2, cursor: payload.mode === "older" ? snapshots.get(payload.threadId)?.olderCursor : null, status: "pending", error: "", createdAt: new Date().toISOString() }, result = { fetchRequest: request, duplicate: false, revision: "r2" };
    receipts.set(payload.requestId, result); if (snapshots.has(payload.threadId)) snapshots.get(payload.threadId).requests.push(request); list.requests.push(request); return response(result);
  }
  runInNewContext(source, runtime); const panel = runtime.window.CodexConversationsPanel.create(root, { phone, onTarget: target => targets.push(target), onAuth: () => auth++, onConnectionState: value => connections.push(value) });
  const all = (tag, start = root) => { const out = []; const visit = item => { if (item.tagName === tag.toUpperCase()) out.push(item); item.children.forEach(visit); }; visit(start); return out; };
  const find = text => all("button").find(node => node.textContent === text), group = id => all("details").find(node => node.dataset.group === id);
  return { root, panel, runtime, list, snapshots, calls, timers, events, connections, targets, receipts, all, find, group, auth: () => auth, fail: path => { failPath = path; }, status(path, code) { statusPath = path; statusCode = code; }, wait(path, promise) { waits.set(path, promise); }, async start() { panel.setActive(true); await settle(); }, async select(id = A) { panel.selectThread(id); await settle(); }, async poll() { const entry = [...timers.values()].find(timer => timer.delay === 30000); assert.ok(entry, "Active view must schedule a 30s refresh"); entry.action(); await settle(); }, async visibility(hidden) { document.hidden = hidden; events.get("visibilitychange")(); await settle(); } };
}
let passed = 0;
async function test(name, action) { await action(); passed++; console.log(`PASS ${name}`); }
await test("catalog is read only and Projects / Recents retain source order and exact titles", async () => {
  const h = harness({ list: catalog({ projects: [{ id: "project", label: "项目 原 标题", path: "D:\\Repo" }], threads: [thread(B, { title: "后更新的名字", projectId: "project" }), thread(C), thread(A, { title: "前一个名字", projectId: "project" }), thread(D)] }) }); await h.start();
  assert.equal(h.calls.length, 1); assert.equal(h.calls[0].options.method, "GET"); assert.equal(h.group("project:project").children[0].children[0].textContent, "项目 原 标题"); const recent = h.group("recents"); assert.deepEqual(h.all("button", recent).map(item => item.dataset.threadId), [C, D]); assert.deepEqual(h.all("button", h.group("project:project")).map(item => item.dataset.threadId), [B, A]); assert.equal(h.group("project:project").open, true); assert.equal(h.group("projects").open, true); assert.equal(recent.open, true); assert.doesNotMatch(h.group("projects").textContent, /其他会话/);
});
await test("cwd longest root prefix uses path boundaries and exact project takes priority", async () => {
  const h = harness({ list: catalog({ projects: [{ id: "wide", label: "Wide", path: "D:\\Repo" }, { id: "nested", label: "Nested", path: "D:\\Repo\\Child" }], threads: [thread(A, { cwd: "d:/REPO/child/inside" }), thread(B, { cwd: "D:\\Repository\\Other" }), thread(C, { cwd: "D:\\Repo\\Child", projectId: "wide" })] }) }); await h.start();
  assert.deepEqual(h.all("button", h.group("project:nested")).map(item => item.dataset.threadId), [A]); assert.deepEqual(h.all("button", h.group("project:wide")).map(item => item.dataset.threadId), [C]); assert.deepEqual(h.all("button", h.group("recents")).map(item => item.dataset.threadId), [B]);
});
await test("project expansion survives polling without changing labels", async () => {
  const h = harness({ list: catalog({ projects: [{ id: "p", label: "原样", path: "D:\\P" }], threads: [thread(A, { projectId: "p" })] }) }); await h.start(); h.group("project:p").open = true; h.group("project:p").fire("toggle"); await h.poll(); assert.equal(h.group("project:p").open, true);
});
await test("active spinner, idle, unread and approval state are source-derived", async () => {
  const h = harness({ list: catalog({ threads: [thread(A, { status: { type: "active", activeFlags: [] }, unread: true }), thread(B), thread(C, { status: { type: "active", activeFlags: ["waitingOnApproval"] } }), thread(D, { status: undefined })] }) }); await h.start();
  const cards = h.all("button", h.group("recents")); assert.equal(cards[0].dataset.active, "true"); assert.match(cards[0].textContent, /进行中.*Codex/); assert.match(cards[0].textContent, /未读/); assert.match(cards[1].textContent, /空闲/); assert.equal(cards[2].dataset.attention, "true"); assert.match(cards[2].textContent, /需要处理/); assert.match(cards[3].textContent, /状态未提供/); assert.equal(h.all("span", cards[3]).some(node => node.className === "conversations-spinner"), false); assert.doesNotMatch(h.root.textContent, /\d+%/);
});
await test("real notLoaded status is readable and never shown as running", async () => {
  const h = harness({ list: catalog({ threads: [thread(A, { title: "Common", status: { type: "notLoaded" } })] }) }); await h.start(); const card = h.all("button", h.group("recents"))[0]; assert.match(card.textContent, /Common.*尚未加载/); assert.equal(card.dataset.active, "false"); assert.equal(h.all("span", card).some(item => item.className === "conversations-spinner"), false); await h.select(); assert.match(h.root.textContent, /Codex · 尚未加载/); assert.doesNotMatch(h.root.textContent, /notLoaded|进行中/);
});
await test("snapshot time and partial or expired catalog remain explicit", async () => {
  const h = harness({ list: catalog({ fetchedAt: new Date(Date.now() - 600000).toISOString(), partial: true }) }); await h.start(); assert.match(h.root.textContent, /抓取于.*已过期.*列表尚未完整取得/); const meta = h.all("p").find(item => item.dataset.stale); assert.equal(meta.dataset.stale, "true");
});
await test("active spinner stops for expired or undated observations", async () => {
  const h = harness({ list: catalog({ threads: [thread(A, { status: "active" })] }) }); await h.start(); assert.equal(h.all("span").filter(item => item.className === "conversations-spinner").length, 1); h.list.fetchedAt = new Date(Date.now() - 301000).toISOString(); await h.poll(); assert.equal(h.all("span").filter(item => item.className === "conversations-spinner").length, 0); assert.match(h.root.textContent, /上次进行中，待更新/); h.list.fetchedAt = null; await h.poll(); assert.equal(h.all("span").filter(item => item.className === "conversations-spinner").length, 0);
});
await test("failed refresh still expires the cached active spinner", async () => {
  const h = harness({ list: catalog({ threads: [thread(A, { status: "active" })] }) }); await h.start(); const originalNow = Date.now, time = Date.now(); try { Date.now = () => time + 301000; h.fail("conversations"); await h.panel.refresh(); assert.equal(h.all("span").filter(item => item.className === "conversations-spinner").length, 0); assert.match(h.root.textContent, /上次进行中，待更新/); } finally { Date.now = originalNow; }
});
await test("active snapshot expires without waiting for another network reply", async () => {
  const h = harness({ list: catalog({ threads: [thread(A, { status: "active" })] }) }); await h.start(); const expiry = [...h.timers.values()].find(item => item.delay > 30000); assert.ok(expiry); const originalNow = Date.now, time = Date.now(); try { Date.now = () => time + 301000; expiry.action(); assert.equal(h.all("span").filter(item => item.className === "conversations-spinner").length, 0); assert.match(h.root.textContent, /上次进行中，待更新/); } finally { Date.now = originalNow; }
});
await test("titles and message content are plain text, never executable HTML", async () => {
  const h = harness({ list: catalog({ threads: [thread(A, { title: '<img src=x onerror="bad()">' })] }), snapshots: new Map([[A, snapshot(A, { messages: [{ id: "u", role: "user", text: "<script>bad()</script>", truncated: false }] })]]) }); await h.start(); await h.select(); assert.equal(h.all("h3")[0].textContent, '<img src=x onerror="bad()">'); assert.ok(h.all("p").some(node => node.className === "conversations-message-text" && node.textContent === "<script>bad()</script>")); assert.equal(h.all("script").length, 0);
});
await test("selecting cached conversation uses only GET and exposes true coverage", async () => {
  const h = harness(); await h.start(); await h.select(); assert.equal(h.calls.filter(call => call.options.method === "POST").length, 0); assert.match(h.root.textContent, /已读取 2 条消息 · 1 页.*部分快取.*仍有历史尚未获取.*最近一页/); assert.match(h.root.textContent, /用户的真实文字\n第二行/); assert.match(h.root.textContent, /completed.*final/); assert.equal(h.root.dataset.detail, "true");
});
await test("messages can be collapsed individually and state survives refresh", async () => {
  const h = harness(); await h.start(); await h.select(); const rows = h.all("details").filter(node => node.className === "conversations-message"); assert.equal(rows.length, 2); rows[0].open = false; rows[0].fire("toggle"); await h.poll(); const fresh = h.all("details").filter(node => node.className === "conversations-message"); assert.equal(fresh[0].open, false); assert.equal(fresh[1].open, true);
});
await test("truncated messages are never presented as full text", async () => {
  const h = harness({ snapshots: new Map([[A, snapshot(A, { messages: [{ id: "x", role: "assistant", text: "部分回复", phase: "commentary", status: "in_progress", truncated: true }] })]]) }); await h.start(); await h.select(); assert.match(h.root.textContent, /commentary/); assert.match(h.root.textContent, /这条消息已截断.*部分文字/);
});
await test("final_answer maps to final answer while retaining original source and turn", async () => {
  const h = harness({ snapshots: new Map([[A, snapshot(A, { messages: [{ id: "source", sourceMessageId: "call_source_1", turnId: "exact-turn-2", role: "assistant", text: "App Tools可读的原文字", phase: "final_answer", status: "completed", truncated: false }] })]]) }); await h.start(); await h.select(); assert.match(h.root.textContent, /最终回答（phase：final_answer）/); assert.match(h.root.textContent, /轮次：exact-turn-2.*来源消息：call_source_1/); assert.match(h.root.textContent, /App Tools 实际可读文字/); assert.equal(h.calls.filter(call => call.options.method === "POST").length, 0);
});
await test("empty cache automatically queues exactly one read-only refresh", async () => {
  const h = harness({ snapshots: new Map([[A, snapshot(A, { messages: [], fetchedAt: null, coverage: { messageCount: 0, pageCount: 0 }, hasMore: false, olderCursor: null })]]) }); await h.start(); await h.select(); await h.poll(); const posts = h.calls.filter(call => call.options.method === "POST"); assert.equal(posts.length, 1); assert.deepEqual(Object.keys(posts[0].payload).sort(), ["mode", "requestId", "threadId"]); assert.equal(posts[0].payload.mode, "refresh"); assert.match(h.root.textContent, /等待读取/); assert.match(h.root.textContent, /不会发送聊天消息/); assert.equal(h.find("更新对话").disabled, true);
});
await test("existing pending empty read is not queued again", async () => {
  const h = harness({ snapshots: new Map([[A, snapshot(A, { messages: [], fetchedAt: null, requests: [{ id: "pending", threadId: A, status: "pending", mode: "refresh" }] })]]) }); await h.start(); await h.select(); assert.equal(h.calls.filter(call => call.options.method === "POST").length, 0); assert.match(h.root.textContent, /等待读取/);
});
await test("manual update is a queue request and cannot imply delivery or fresh content", async () => {
  const h = harness(); await h.start(); await h.select(); h.find("更新对话").click(); await settle(); assert.equal(h.calls.at(-1).path, "conversations/request"); assert.equal(h.calls.at(-1).payload.mode, "refresh"); assert.match(h.root.textContent, /尚未取得新内容/); assert.match(h.root.textContent, /用户的真实文字/); assert.doesNotMatch(h.root.textContent, /消息已发送/);
});
await test("more history sends no client cursor and only uses available cached cursor", async () => {
  const h = harness(); await h.start(); await h.select(); assert.equal(h.find("更多历史").disabled, false); h.find("更多历史").click(); await settle(); assert.equal(h.calls.at(-1).payload.mode, "older"); assert.deepEqual(Object.keys(h.calls.at(-1).payload).sort(), ["mode", "requestId", "threadId"]);
});
await test("history button cannot request missing or completed history", async () => {
  const h = harness({ snapshots: new Map([[A, snapshot(A, { hasMore: false, olderCursor: null, partial: false })]]) }); await h.start(); await h.select(); assert.equal(h.find("更多历史").disabled, true); h.find("更多历史").click(); await settle(); assert.equal(h.calls.filter(call => call.options.method === "POST").length, 0); assert.doesNotMatch(h.root.textContent, /仍有历史尚未获取/);
});
await test("completed queued read is reflected on low-frequency polling", async () => {
  const h = harness(); await h.start(); await h.select(); h.find("更新对话").click(); await settle(); h.snapshots.get(A).requests[0].status = "completed"; h.snapshots.get(A).messages.push({ id: "new", role: "assistant", text: "新抓取的真实结果", phase: "final", status: "completed", truncated: false }); h.snapshots.get(A).coverage.messageCount = 3; await h.poll(); assert.match(h.root.textContent, /读取完成/); assert.match(h.root.textContent, /新抓取的真实结果/); assert.equal(h.find("更新对话").disabled, false);
});
await test("failed queue is honest and can be retried", async () => {
  const h = harness({ snapshots: new Map([[A, snapshot(A, { requests: [{ id: "failed", threadId: A, mode: "refresh", status: "failed", error: "来源应用离线" }] })]]) }); await h.start(); await h.select(); assert.match(h.root.textContent, /读取失败.*来源应用离线/); assert.equal(h.find("更新对话").disabled, false);
});
await test("failed empty cache GET stops its loading claim and exposes a retry", async () => {
  const h = harness(); await h.start(); h.status(`conversations/thread?id=${A}`, 503); await h.select(); assert.match(h.root.textContent, /快取未能读取/); assert.doesNotMatch(h.root.textContent, /正在读取电脑上的对话快取/); assert.equal(h.find("更新对话").disabled, false);
});
await test("timed out detail read is bounded and cannot keep claiming to load", async () => {
  const h = harness(); await h.start(); const waiting = defer(); h.wait(`conversations/thread?id=${A}`, waiting.promise); h.panel.selectThread(A); await settle(); const timeout = [...h.timers.values()].find(item => item.delay === 15000); assert.ok(timeout); timeout.action(); waiting.resolve(response(snapshot())); await settle(); assert.match(h.root.textContent, /快取未能读取：读取连接超时/); assert.equal(h.connections.at(-1), false); assert.doesNotMatch(h.root.textContent, /正在读取电脑上的对话快取/);
});
await test("pending queue state is not shown as model activity", async () => {
  const h = harness(); await h.start(); await h.select(); h.find("更新对话").click(); await settle(); assert.match(h.root.textContent, /等待读取/); assert.equal(h.all("span").filter(item => item.className === "conversations-spinner").length, 0); assert.doesNotMatch(h.root.textContent, /模型正在|正在思考/);
});
await test("an acknowledgement without a matching fetch record remains unconfirmed", async () => {
  const h = harness(); await h.start(); await h.select(); h.wait("conversations/request", Promise.resolve(response({ duplicate: false }))); h.find("更新对话").click(); await settle(); assert.match(h.root.textContent, /尚未确认.*未返回对应确认记录/); assert.doesNotMatch(h.root.textContent, /已排入只读对话请求/);
});
await test("lost acknowledgement reuses the same requestId rather than creating a second read", async () => {
  const h = harness(); await h.start(); await h.select(); h.fail("conversations/request"); h.find("更新对话").click(); await settle(); assert.match(h.root.textContent, /尚未确认/); h.find("更新对话").click(); await settle(); const posts = h.calls.filter(call => call.options.method === "POST"); assert.equal(posts.length, 2); assert.equal(posts[0].payload.requestId, posts[1].payload.requestId); assert.equal(h.receipts.size, 1);
});
await test("phone routes require the established paired security headers", async () => {
  const h = harness(); await h.start(); await h.select(); h.find("更新对话").click(); await settle(); for (const call of h.calls) { assert.equal(call.options.headers["X-Codex-Phone"], "1"); assert.equal(call.options.headers.Accept, "application/json"); assert.equal(call.options.credentials, "same-origin"); assert.equal(call.options.mode, "same-origin"); assert.equal(call.options.referrerPolicy, "same-origin"); assert.equal(call.options.redirect, "error"); assert.equal(call.options.cache, "no-store"); assert.ok(call.options.signal); }
});
await test("desktop uses desktop route without a phone header", async () => {
  const h = harness({ phone: false }); await h.start(); await h.select(); assert.ok(h.calls.every(call => call.options.headers["X-Codex-Phone"] === undefined));
});
await test("use this conversation passes exact metadata without any request mutation", async () => {
  const original = thread(A, { title: "必须原样", cwd: "D:\\Repo", status: "active" }), h = harness({ list: catalog({ threads: [original] }) }); await h.start(); await h.select(); const count = h.calls.length; h.find("使用这个会话").click(); assert.deepEqual(clone(h.targets[0]), original); assert.equal(h.calls.length, count);
});
await test("original local Codex link is real and foreign hosts are not guessed", async () => {
  const h = harness({ list: catalog({ threads: [thread(A), thread(B, { hostId: "remote-pc" })] }), snapshots: new Map([[A, snapshot()], [B, snapshot(B)]]) }); await h.start(); await h.select(); assert.equal(h.all("a")[0].href, `codex://threads/${A}`); assert.equal(h.all("a")[0].hidden, false); await h.select(B); assert.equal(h.all("a")[0].hidden, true); assert.equal(h.all("a")[0].href, undefined); assert.match(h.root.textContent, /目前未提供可打开的原会话入口/);
});
await test("ChatGPT requires an actual catalog URL and rejects unsafe URLs", async () => {
  const h = harness({ list: catalog({ threads: [thread(A, { kind: "chatgpt", openUrl: `https://chatgpt.com/c/${A}` }), thread(B, { kind: "chatgpt", openUrl: "javascript:alert(1)" }), thread(C, { kind: "chatgpt" })] }) }); await h.start(); await h.select(A); assert.equal(h.all("a")[0].href, `https://chatgpt.com/c/${A}`); await h.select(B); assert.equal(h.all("a")[0].hidden, true); await h.select(C); assert.equal(h.all("a")[0].hidden, true);
});
await test("invalid target IDs or kinds never enable selection or original links", async () => {
  const h = harness({ list: catalog({ threads: [thread("not-an-id", { kind: "other" })] }) }); await h.start(); await h.select("not-an-id"); assert.equal(h.find("使用这个会话").disabled, true); assert.equal(h.all("a")[0].hidden, true);
});
await test("late detail responses cannot overwrite a newly selected conversation", async () => {
  const h = harness({ list: catalog({ threads: [thread(A), thread(B)] }), snapshots: new Map([[A, snapshot()], [B, snapshot(B, { messages: [{ id: "b", role: "user", text: "仅B内容" }] })]]) }); await h.start(); const waiting = defer(); h.wait(`conversations/thread?id=${A}`, waiting.promise); h.panel.selectThread(A); await settle(); await h.select(B); waiting.resolve(response(snapshot(A, { messages: [{ id: "late", role: "user", text: "过期A内容" }] }))); await settle(); assert.match(h.root.textContent, /仅B内容/); assert.doesNotMatch(h.root.textContent, /过期A内容/); assert.equal(h.all("h3")[0].textContent, thread(B).title);
});
await test("late catalogue generation does not replace a newer refresh", async () => {
  const h = harness(); const waiting = defer(); h.wait("conversations", waiting.promise); h.panel.setActive(true); await settle(); h.list.threads = [thread(B, { title: "较新列表" })]; await h.panel.refresh(); waiting.resolve(response(catalog({ threads: [thread(A, { title: "过期列表" })] }))); await settle(); assert.match(h.root.textContent, /较新列表/); assert.doesNotMatch(h.root.textContent, /过期列表/);
});
await test("late read acknowledgement cannot alter another conversation", async () => {
  const h = harness({ list: catalog({ threads: [thread(A), thread(B)] }), snapshots: new Map([[A, snapshot()], [B, snapshot(B)]]) }); await h.start(); await h.select(); const waiting = defer(); h.wait("conversations/request", waiting.promise); h.find("更新对话").click(); await settle(); assert.equal(h.panel.canReload(), false); await h.select(B); waiting.resolve(response({ fetchRequest: { id: "late", threadId: A, mode: "refresh", status: "pending" } })); await settle(); assert.equal(h.all("h3")[0].textContent, thread(B).title); assert.doesNotMatch(h.root.textContent, /已排入只读对话请求/); assert.equal(h.panel.canReload(), true);
});
await test("authorization revocation wipes private cache and aborts late responses", async () => {
  const h = harness(); await h.start(); await h.select(); h.status("conversations", 401); await h.panel.refresh(); assert.equal(h.auth(), 1); assert.doesNotMatch(h.root.textContent, /用户的真实文字|助手回复|原会话 1111/); assert.match(h.root.textContent, /授权已失效/); assert.equal(h.timers.size, 0); assert.equal(h.root.dataset.detail, "false");
});
await test("explicit clear removes all private text without triggering a chat operation", async () => {
  const h = harness(); await h.start(); await h.select(); const count = h.calls.length; h.panel.clear(); assert.equal(h.calls.length, count); assert.doesNotMatch(h.root.textContent, /用户的真实文字|助手回复|原会话 1111/); assert.equal(h.panel.canReload(), true);
});
await test("hidden and inactive panels stop polling and abort reads", async () => {
  const h = harness(); await h.start(); assert.equal(h.timers.size, 1); await h.visibility(true); assert.equal(h.timers.size, 0); const count = h.calls.length; await h.panel.refresh(); assert.equal(h.calls.length, count); await h.visibility(false); assert.equal(h.timers.size, 1); h.panel.setActive(false); assert.equal(h.timers.size, 0); await h.panel.refresh(); assert.equal(h.calls.length, count + 1);
});
await test("same active value preserves polling and an in-flight acknowledgement", async () => {
  const h = harness(); await h.start(); await h.select(); const waiting = defer(); h.wait("conversations/request", waiting.promise); h.find("更新对话").click(); await settle(); const count = h.calls.length, pending = h.calls.at(-1); assert.equal(h.panel.canReload(), false); h.panel.setActive(true); h.panel.setActive(true); await settle(); assert.equal(h.calls.length, count); assert.equal(pending.options.signal.aborted, false); assert.equal(h.panel.canReload(), false); waiting.resolve(response({ fetchRequest: { id: "stable", threadId: A, mode: "refresh", status: "pending" } })); await settle(); assert.match(h.root.textContent, /已排入只读对话请求/); assert.equal(h.panel.canReload(), true); h.panel.setActive(false); const inactiveCount = h.calls.length; h.panel.setActive(false); await settle(); assert.equal(h.calls.length, inactiveCount); assert.equal(h.timers.size, 0);
});
await test("re-pair after a private clear can activate and read again", async () => {
  const h = harness(); await h.start(); await h.select(); h.panel.clear(); assert.doesNotMatch(h.root.textContent, /用户的真实文字/); const count = h.calls.length; h.panel.setActive(true); await settle(); assert.equal(h.calls.length, count + 1); await h.select(); assert.match(h.root.textContent, /用户的真实文字/); assert.equal(h.calls.filter(call => call.options.method === "POST").length, 0);
});
await test("network errors retain honest cached display and report connection loss", async () => {
  const h = harness(); await h.start(); await h.select(); h.fail("conversations"); await h.panel.refresh(); assert.match(h.root.textContent, /此前取得的快取/); assert.match(h.root.textContent, /用户的真实文字/); assert.equal(h.connections.at(-1), false);
});
await test("back navigation keeps the list and does not queue another read", async () => {
  const h = harness(); await h.start(); await h.select(); const count = h.calls.length; h.find("‹ 返回会话列表").click(); assert.equal(h.root.dataset.detail, "false"); assert.equal(h.calls.length, count); assert.equal(h.all("h3")[0].textContent, "");
});
await test("mobile CSS has readable narrow layout, touch controls and safe text wrapping", async () => {
  assert.match(css, /@media\(max-width:700px\)/); assert.match(css, /grid-template-columns:minmax\(0,1fr\)/); assert.match(css, /\[data-detail=true\] \.conversations-sidebar\{display:none\}/); assert.match(css, /min-height:44px/); assert.match(css, /white-space:pre-wrap/); assert.match(css, /overflow-wrap:anywhere/); assert.match(css, /prefers-reduced-motion/); assert.doesNotMatch(source, /innerHTML|localStorage|sessionStorage|send_message|create_thread/);
});
console.log(`${passed} conversations UI checks passed`);
