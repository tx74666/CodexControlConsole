#!/usr/bin/env node
// In-memory UI actions only: no application, credentials, workspace, or model calls.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { randomUUID } from "node:crypto";
const sourceCode = readFileSync(new URL("../codex-work-panel.js", import.meta.url), "utf8");
const flush = async () => { for (let n = 0; n < 10; n++) await new Promise(resolve => setImmediate(resolve)); };
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
class Element {
  constructor(tag = "div") { this.tagName = tag.toUpperCase(); this.children = []; this.listeners = new Map(); this.attributes = {}; this.dataset = {}; this.style = {}; this.value = ""; this._text = ""; this.hidden = false; this.className = ""; this.classList = { add: (...names) => { this.className = [...new Set([...this.className.split(" "), ...names])].filter(Boolean).join(" "); } }; }
  append(...values) { this.children.push(...values); }
  replaceChildren(...values) { this.children = values; this._text = ""; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  set innerHTML(_) { throw new Error("Untrusted provider and source content must stay text"); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(event, fn) { const handlers = this.listeners.get(event) || []; handlers.push(fn); this.listeners.set(event, handlers); }
  fire(event, detail = {}) { for (const fn of this.listeners.get(event) || []) fn({ target: this, preventDefault() {}, ...detail }); }
  click() { if (!this.disabled) this.fire("click"); }
  contains(other) { return this === other || this.children.some(child => child.contains(other)); }
}
const identity = { recordId: "1".repeat(32), clientId: "10101010-1010-4010-8010-101010101010", sessionId: "2".repeat(32), expectedRevision: 11, text: "  本轮修改底稿\n保留原换行 <script>不能执行</script>  ", attachmentIds: ["3".repeat(32)] };
const scopeFor = value => ({ recordId: value.recordId, clientId: value.clientId, sessionId: value.sessionId });
const configFixture = () => ({ setup: { ready: true, busy: false, status: "ready" }, workspaces: [{ id: "fixture-project", name: "隔离示例项目", workspaceRoot: "D:/fixture/project", allowedRoot: "D:/fixture/project/allowed", authorizationSha256: "a".repeat(64), available: true }], subscription: { connected: true, connectionId: "b".repeat(32), catalogRevision: "c".repeat(64), status: "ready", models: [{ slug: "fixture-model", name: "隔离模型" }] } });
const jobFixture = (recordId = identity.recordId) => ({ id: "5".repeat(32), recordId, kind: "work", requestId: "fixture-request", executionEngine: "codex_agent", status: "running", attempt: 1, error: "", instruction: identity.text, result: {}, workspace: { ...configFixture().workspaces[0] }, mobileDialogue: { id: identity.sessionId, clientId: identity.clientId, recordId, revision: identity.expectedRevision }, codexWork: { name: "Agent 1", runId: "5".repeat(32), threadId: "thread-fixture", turnId: "turn-fixture", sourceSha256: "d".repeat(64), requestedModel: "fixture-model", actualModel: "fixture-model", requestedProfile: "high", requestedEffort: "high", actualEffort: "high", allowedRoot: "D:/fixture/project/allowed", terminalEventObserved: false, terminalStatus: null, cancellationVerified: false, executionVerified: false, reportOnly: false, progress: [{ kind: "item/agentMessage/delta", itemId: "agent-item", text: "只在内存中的进度" }], plan: [] } });
function harness({ storage = new Map(), source = structuredClone(identity), config = configFixture(), options = {} } = {}) {
  const root = new Element(), calls = [], timers = new Map(), backs = []; let currentSource = source, currentScope = { recordId: source?.recordId || identity.recordId, clientId: source?.clientId || identity.clientId, sessionId: source?.sessionId || identity.sessionId }, currentConfig = config, jobs = [], hook = null, lastReview = null, storageFailure = false;
  const reviewFor = body => ({ reviewId: "4".repeat(32), recordId: body.recordId, sourceSha256: "d".repeat(64), reviewSha256: "e".repeat(64), beforeFileCount: 2, duplicate: false, revision: 17, source: { recordId: body.recordId, text: body.text, attachmentIds: [...body.attachmentIds], expectedRevision: body.expectedRevision, context: { history: [], sourceTask: null, ideaContext: null }, images: body.attachmentIds.map(id => ({ id, name: "本轮原图.png", mimeType: "image/png", size: 8, sha256: "f".repeat(64), url: "/fixture/original.png" })), workspace: { ...currentConfig.workspaces[0] }, subscription: { ...body.subscription }, requestedProfile: body.requestedProfile, mobileDialogue: options.phone === false ? null : { id: body.sessionId, clientId: body.clientId, recordId: body.recordId, ideaId: null, ideaRevision: null, revision: body.expectedRevision } } });
  const reply = (data, status = 200) => ({ ok: status >= 200 && status < 300, status, async json() { return structuredClone(data); } });
  const runtime = { console, crypto: { randomUUID }, URL, structuredClone, document: { createElement: tag => new Element(tag) }, localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => { if (storageFailure) throw new Error("fixture storage unavailable"); storage.set(key, value); } }, window: { setTimeout(fn, ms) { const id = randomUUID(); timers.set(id, { fn, ms }); return id; }, clearTimeout(id) { timers.delete(id); } }, async fetch(url, request) {
    const parsed = new URL(url, "http://fixture.test"), action = parsed.pathname.replace(/^\/api\/(?:phone\/)?workflow\//, ""), body = request.body ? JSON.parse(request.body) : null;
    assert.match(parsed.pathname, /^\/api\/(?:phone\/)?workflow\/codex-work\//, "Only the actual local Work route is available to this fixture.");
    calls.push({ action, body: body && structuredClone(body), query: parsed.searchParams, request: { ...request } });
    // Mirror the real paired-phone POST gate, rather than letting a stub bypass it.
    if (parsed.pathname.startsWith("/api/phone/") && request.method === "POST" && request.headers?.["X-Codex-Phone"] !== "1") return reply({ error: "请从手机入口提交操作。", code: "fixture_phone_origin_gate" }, 403);
    if (hook) { const value = await hook(action, body, request); if (value !== undefined) return value; }
    if (action === "codex-work/config") return reply(currentConfig);
    if (action === "codex-work/runs") return reply({ recordId: parsed.searchParams.get("recordId"), runs: jobs, revision: 18, ...(parsed.pathname.startsWith("/api/phone/") ? { scope: { recordId: parsed.searchParams.get("recordId"), clientId: parsed.searchParams.get("clientId"), sessionId: parsed.searchParams.get("sessionId") } } : {}) });
    if (action === "codex-work/review") { lastReview = reviewFor(body); return reply(lastReview); }
    if (action === "codex-work/submit") { const job = jobFixture(lastReview.recordId); job.requestId = body.requestId; job.status = "starting"; jobs = [job]; return reply({ recordId: job.recordId, job, duplicate: false, revision: 19 }); }
    if (action === "codex-work/cancel") { jobs = jobs.map(job => job.id === body.jobId ? { ...job, status: "cancelling" } : job); return reply({ recordId: currentSource.recordId, job: jobs.find(job => job.id === body.jobId), duplicate: false, revision: 20, ...(parsed.pathname.startsWith("/api/phone/") ? { scope: { recordId: currentSource.recordId, clientId: body.clientId, sessionId: body.sessionId } } : {}) }); }
    throw new Error(`Unexpected fixture route ${action}`);
  } };
  runInNewContext(sourceCode, runtime);
  const panel = runtime.window.CodexWorkPanel.create(root, { phone: true, getSource: () => currentSource && structuredClone(currentSource), getScope: () => currentScope && structuredClone(currentScope), onBack: () => backs.push(true), ...options });
  const all = (node = root) => [node, ...node.children.flatMap(child => all(child))], byText = text => all().find(node => node.tagName === "BUTTON" && node.textContent === text), byClass = cls => all().find(node => node.className.split(" ").includes(cls)), byLabel = label => all().find(node => node.attributes["aria-label"] === label), fieldControl = label => all().find(node => node.tagName === "LABEL" && node.children[0]?.textContent === label)?.children[1];
  return { root, panel, calls, storage, timers, backs, byText, byClass, byLabel, fieldControl, reply, reviewFor, setSource(value) { currentSource = value && structuredClone(value); if (value) currentScope = { recordId: value.recordId, clientId: value.clientId, sessionId: value.sessionId }; }, setScope(value) { currentScope = value && structuredClone(value); }, setConfig(value) { currentConfig = structuredClone(value); }, setJobs(value) { jobs = structuredClone(value); }, hook(value) { hook = value; }, failStorage(value = true) { storageFailure = value; } };
}
let count = 0;
async function test(name, fn) { await fn(); count++; console.log(`PASS ${name}`); }
const posts = h => h.calls.filter(call => call.request.method === "POST");
const savedPending = h => JSON.parse([...h.storage.values()][0] || "{}").pending;
async function reviewCurrent(h) { await h.panel.setActive(true); h.byText("核对本轮 Work").click(); await flush(); }

await test("opening and reading Work stays GET-only and binds the cached original discussion", async () => {
  const h = harness(); assert.equal(h.calls.length, 0); await h.panel.setActive(true); assert.equal(posts(h).length, 0); assert.deepEqual(h.calls.map(call => call.action), ["codex-work/config", "codex-work/runs"]); assert.deepEqual(Object.fromEntries(h.calls[1].query), scopeFor(identity)); assert.equal(h.byLabel("本轮 Work 底稿").value, identity.text);
  h.byText("查看进度").click(); await flush(); assert.equal(posts(h).length, 0); assert.equal(h.timers.size, 0); h.byText("返回对话").click(); assert.equal(h.backs.length, 1); assert.equal(posts(h).length, 0); for (const call of h.calls) { assert.equal(call.request.credentials, "same-origin"); assert.equal(call.request.mode, "same-origin"); assert.equal(call.request.redirect, "error"); }
});
await test("desktop sandbox setup requires one explicit click and preserves exact workspace authorization", async () => {
  const initial = configFixture(); initial.setup = { ready: false, busy: false, status: "not_started" };
  const h = harness({ config: initial, options: { phone: false } }); await h.panel.setActive(true);
  const control = h.byText("配置 Console Work 沙箱（Windows 授权）"); assert.ok(control); assert.equal(control.disabled, false); assert.equal(posts(h).length, 0);
  const wait = deferred(); h.hook(action => action === "codex-work/setup" ? wait.promise : undefined);
  control.click(); control.click(); await flush(); const sent = posts(h); assert.equal(sent.length, 1); assert.equal(sent[0].action, "codex-work/setup"); assert.deepEqual(sent[0].body, { workspaceId: "fixture-project", workspaceAuthorizationSha256: "a".repeat(64), confirmed: true });
  assert.equal(sent[0].request.headers["X-Codex-Phone"], undefined); assert.equal(control.disabled, true);
  const busy = configFixture(); busy.setup = { ready: false, busy: true, status: "running" }; h.setConfig(busy); wait.resolve(h.reply({ setup: busy.setup })); await flush();
  assert.match(h.byClass("codex-work-setup").textContent, /等待 Windows.*本人确认/); assert.equal(control.disabled, true); assert.equal(h.panel.canReload(), false); assert.equal(posts(h).length, 1);
  const timer = [...h.timers.values()].find(item => item.ms === 2000); assert.ok(timer); timer.fn(); await flush(); assert.equal(posts(h).length, 1);
  const ready = configFixture(); ready.setup = { ready: true, busy: false, status: "ready" }; h.setConfig(ready); h.byText("查看进度").click(); await flush();
  assert.match(h.byClass("codex-work-setup").textContent, /沙箱已配置/); assert.equal(control.disabled, true); assert.equal(posts(h).length, 1); await h.panel.setActive(false); assert.equal(h.timers.size, 0);
});
await test("phone sandbox status never exposes or automatically starts the Windows permission action", async () => {
  const config = configFixture(); config.setup = { ready: false, busy: true, status: "running" }; const h = harness({ config }); await h.panel.setActive(true);
  assert.equal(h.byText("配置 Console Work 沙箱（Windows 授权）"), undefined); assert.match(h.byClass("codex-work-setup").textContent, /权限窗口需你本人确认/); assert.equal(posts(h).length, 0);
  const timer = [...h.timers.values()].find(item => item.ms === 2000); assert.ok(timer); timer.fn(); await flush(); assert.equal(posts(h).length, 0); assert.equal(h.calls.some(call => call.action === "codex-work/setup"), false);
  await h.panel.setActive(false); assert.equal(h.timers.size, 0);
});
await test("unknown sandbox setup remains blocked through refresh and reopening without replay", async () => {
  const config = configFixture(); config.setup = { ready: false, busy: false, status: "unknown" }; const h = harness({ config, options: { phone: false } }); await h.panel.setActive(true);
  assert.equal(h.byText("配置 Console Work 沙箱（Windows 授权）").disabled, true); assert.match(h.byClass("codex-work-setup").textContent, /待核对.*不能重复配置/);
  h.byText("配置 Console Work 沙箱（Windows 授权）").click(); h.byText("查看进度").click(); await flush(); assert.equal(posts(h).length, 0);
  const resumed = harness({ config, storage: h.storage, options: { phone: false } }); await resumed.panel.setActive(true); assert.equal(resumed.byText("配置 Console Work 沙箱（Windows 授权）").disabled, true); assert.equal(posts(resumed).length, 0);
});
await test("sandbox setup accepted with a lost response is fenced until cache status is checked", async () => {
  const config = configFixture(); config.setup = { ready: false, busy: false, status: "not_started" }; const h = harness({ config, options: { phone: false } }); await h.panel.setActive(true);
  const unknown = configFixture(); unknown.setup = { ready: false, busy: false, status: "unknown" };
  h.hook(action => { if (action !== "codex-work/setup") return undefined; h.setConfig(unknown); throw new TypeError("fixture accepted setup but response lost"); });
  h.byText("配置 Console Work 沙箱（Windows 授权）").click(); await flush(); assert.equal(posts(h).length, 1);
  assert.equal(h.byText("配置 Console Work 沙箱（Windows 授权）").disabled, true); h.byText("配置 Console Work 沙箱（Windows 授权）").click(); assert.equal(posts(h).length, 1);
  h.byText("查看进度").click(); await flush(); assert.equal(h.byText("配置 Console Work 沙箱（Windows 授权）").disabled, true); assert.match(h.byClass("codex-work-setup").textContent, /待核对/); assert.equal(posts(h).length, 1);
});
await test("missing or unsaved source blocks review without posting or silently omitting images", async () => {
  const h = harness({ source: null }); await h.panel.setActive(true); assert.equal(h.byText("核对本轮 Work").disabled, true); assert.match(h.byClass("workflow-notice").textContent, /保存|上传/); h.byText("核对本轮 Work").click(); assert.equal(posts(h).length, 0);
  h.setSource(identity); h.byText("载入当前讨论").click(); await flush(); assert.equal(h.byText("核对本轮 Work").disabled, false); assert.match(h.byClass("workflow-thumbnails").textContent, /1 张图片/); assert.equal(posts(h).length, 0);
});
await test("review freezes exact source images workspace authorization model and requested profile without creating Agent", async () => {
  const h = harness(); await reviewCurrent(h); const sent = posts(h); assert.equal(sent.length, 1); assert.equal(sent[0].action, "codex-work/review"); const body = sent[0].body;
  for (const key of Object.keys(identity)) assert.deepEqual(body[key], identity[key]); assert.equal(body.workspaceId, "fixture-project"); assert.equal(body.workspaceAuthorizationSha256, "a".repeat(64)); assert.equal(body.requestedProfile, "high"); assert.deepEqual(body.subscription, { provider: "chatgpt_subscription", connectionId: "b".repeat(32), catalogRevision: "c".repeat(64), modelSlug: "fixture-model" });
  assert.equal(h.byClass("workflow-review").hidden, false); assert.match(h.byClass("codex-work-review-text").textContent, /本轮修改底稿|fixture-project|隔离示例项目/); assert.equal(h.calls.some(call => call.action === "codex-work/submit"), false);
});
await test("unsupported Pro stays visibly unavailable while explicit Fast reviews only the supported request", async () => {
  const h = harness(); await h.panel.setActive(true); const tier = h.byLabel("Work 档位"); assert.equal(tier.children.find(option => option.value === "pro").disabled, true); assert.match(tier.children.find(option => option.value === "pro").textContent, /暂不支持/); tier.value = "fast"; tier.fire("change"); assert.equal(posts(h).length, 0); h.byText("核对本轮 Work").click(); await flush(); assert.equal(posts(h)[0].body.requestedProfile, "fast"); assert.equal(h.calls.some(call => call.action === "codex-work/submit"), false);
});
await test("reopening a saved unsupported Pro never silently changes to Fast or submits", async () => {
  const storage = new Map([["console.codexWork.v1:/api/phone/workflow", JSON.stringify({ profile: "pro" })]]), h = harness({ storage });
  await h.panel.setActive(true); const tier = h.byLabel("Work 档位"); assert.equal(tier.value, "pro"); assert.equal(tier.children.find(option => option.value === "pro").disabled, true); assert.equal(h.byText("核对本轮 Work").disabled, true);
  h.byText("核对本轮 Work").click(); assert.equal(posts(h).length, 0); tier.value = "high"; tier.fire("change"); assert.equal(posts(h).length, 0); assert.equal(h.byText("核对本轮 Work").disabled, false); h.byText("核对本轮 Work").click(); await flush(); assert.equal(posts(h)[0].body.requestedProfile, "high"); assert.equal(h.calls.some(call => call.action === "codex-work/submit"), false);
});
await test("foreign or malformed review frames cannot become a confirmable Agent proposal", async () => {
  for (const change of [frame => { frame.recordId = "f".repeat(32); }, frame => { frame.sourceSha256 = "invalid"; }, frame => { frame.source.text = "foreign draft"; }, frame => { frame.source.workspace.id = "other-workspace"; }, frame => { frame.source.subscription.modelSlug = "other-model"; }, frame => { frame.source.requestedProfile = "pro"; }, frame => { frame.source.attachmentIds = ["8".repeat(32)]; }, frame => { frame.source.expectedRevision += 1; }, frame => { frame.source.mobileDialogue.clientId = "90909090-9090-4090-8090-909090909090"; }, frame => { frame.source.mobileDialogue.id = "8".repeat(32); }, frame => { frame.source.mobileDialogue.recordId = "8".repeat(32); }, frame => { frame.source.mobileDialogue.revision += 1; }, frame => { frame.source.mobileDialogue = null; }, frame => { frame.source.expectedRevision = String(frame.source.expectedRevision); }, frame => { frame.source.workspace.authorizationSha256 = "8".repeat(64); }, frame => { frame.source.subscription.connectionId = "8".repeat(32); }, frame => { frame.source.subscription.catalogRevision = "8".repeat(64); }, frame => { frame.source.subscription.provider = "other_provider"; }]) {
    const h = harness(); await h.panel.setActive(true); h.hook((action, body) => { if (action !== "codex-work/review") return undefined; const frame = h.reviewFor(body); change(frame); return h.reply(frame); }); h.byText("核对本轮 Work").click(); await flush(); assert.equal(h.byText("确认创建 Agent").disabled, true); assert.equal(h.byClass("workflow-review").hidden, true); assert.match(h.byClass("workflow-notice").textContent, /来源不一致|核对/); assert.equal(h.calls.some(call => call.action === "codex-work/submit"), false);
  }
});
await test("changed cached discussion is rejected before review and explicit reload binds the new identity", async () => {
  const h = harness(); await h.panel.setActive(true); const next = { ...identity, recordId: "6".repeat(32), sessionId: "7".repeat(32), expectedRevision: 21, text: "B 独立底稿", attachmentIds: [] }; h.setSource(next); h.byText("核对本轮 Work").click(); await flush(); assert.equal(posts(h).length, 0); assert.match(h.byClass("workflow-notice").textContent, /变化|重新载入/);
  h.byText("载入当前讨论").click(); await flush(); h.byText("核对本轮 Work").click(); await flush(); assert.equal(posts(h)[0].body.recordId, next.recordId); assert.equal(posts(h)[0].body.sessionId, next.sessionId); assert.equal(posts(h)[0].body.text, next.text);
});
await test("a review arriving after the current source changes cannot authorize the old discussion", async () => {
  const h = harness(); await h.panel.setActive(true); const wait = deferred(); let original;
  h.hook((action, body) => { if (action !== "codex-work/review") return undefined; original = body; return wait.promise; }); h.byText("核对本轮 Work").click(); await flush(); assert.ok(original);
  const next = { ...identity, recordId: "6".repeat(32), sessionId: "7".repeat(32), expectedRevision: 21, text: "B：审核期间新讨论", attachmentIds: [] }; h.setSource(next); wait.resolve(h.reply(h.reviewFor(original))); await flush(); assert.equal(h.byText("确认创建 Agent").disabled, true); assert.equal(h.calls.some(call => call.action === "codex-work/submit"), false);
  h.hook(null); h.byText("载入当前讨论").click(); await flush(); assert.equal(h.byLabel("本轮 Work 底稿").value, next.text); assert.equal(h.byClass("workflow-review").hidden, true);
});
await test("a late progress read for A cannot overwrite the newly loaded B record", async () => {
  const h = harness(); await h.panel.setActive(true); const wait = deferred(), oldReadEntered = deferred(); let first = true; h.hook(action => { if (action === "codex-work/runs" && first) { first = false; assert.equal(h.calls.at(-1).query.get("recordId"), identity.recordId); oldReadEntered.resolve(); return wait.promise; } });
  const oldRead = h.panel.refresh(); await oldReadEntered.promise;
  const next = { ...identity, recordId: "6".repeat(32), sessionId: "7".repeat(32), expectedRevision: 21, text: "B：独立的当前底稿", attachmentIds: [] }, b = jobFixture(next.recordId); b.mobileDialogue.id = next.sessionId; b.codexWork.name = "Agent B"; b.codexWork.progress[0].text = "只属于 B 的进度"; h.setSource(next); h.setJobs([b]); await h.panel.loadSource();
  const a = jobFixture(); a.codexWork.name = "Agent A"; a.codexWork.progress[0].text = "不应进入 B 的旧进度"; wait.resolve(h.reply({ recordId: identity.recordId, scope: scopeFor(identity), runs: [a], revision: 22 })); await oldRead; assert.equal(h.byLabel("本轮 Work 底稿").value, next.text); assert.match(h.byClass("codex-work-runs").textContent, /Agent B|只属于 B/); assert.doesNotMatch(h.byClass("codex-work-runs").textContent, /Agent A|不应进入 B/); assert.equal(posts(h).length, 0);
  await h.panel.setActive(false); assert.equal(h.timers.size, 0);
});
await test("only the explicit confirm creates one Agent and repeated taps cannot duplicate the same request", async () => {
  const h = harness(); await reviewCurrent(h); const wait = deferred(); h.hook((action, body) => action === "codex-work/submit" ? wait.promise : undefined); h.byText("确认创建 Agent").click(); h.byText("确认创建 Agent").click(); assert.equal(posts(h).filter(call => call.action === "codex-work/submit").length, 1); assert.equal(h.byText("确认创建 Agent").disabled, true); const payload = posts(h).at(-1).body; assert.equal(payload.confirmed, true); assert.equal(payload.reviewId, "4".repeat(32)); assert.equal(payload.sourceSha256, "d".repeat(64)); assert.equal(savedPending(h).requestId, payload.requestId);
  const job = jobFixture(); job.status = "starting"; job.requestId = payload.requestId; h.setJobs([job]); wait.resolve(h.reply({ recordId: identity.recordId, job, duplicate: false, revision: 19 })); await flush(); assert.equal(posts(h).filter(call => call.action === "codex-work/submit").length, 1); assert.equal(savedPending(h), null); assert.match(h.byClass("codex-work-runs").textContent, /Agent 1|准备中/);
});
await test("failed durable reservation sends no Agent request and leaves the review available", async () => {
  const h = harness(); await reviewCurrent(h); h.failStorage(); h.byText("确认创建 Agent").click(); await flush(); assert.equal(h.calls.some(call => call.action === "codex-work/submit"), false); assert.match(h.byClass("workflow-notice").textContent, /编号尚未保存|未创建/); assert.equal(h.panel.canReload(), false); assert.equal(h.byClass("workflow-review").hidden, false);
});
await test("unknown create outcome retains its nonce through refresh and reload without automatic replay", async () => {
  const h = harness(); await reviewCurrent(h); h.hook(action => { if (action === "codex-work/submit") throw new TypeError("fixture accepted response was lost"); }); h.byText("确认创建 Agent").click(); await flush(); const pending = structuredClone(savedPending(h)); assert.ok(pending?.requestId); assert.equal(h.byText("确认创建 Agent").disabled, true); h.byText("查看进度").click(); await flush(); assert.deepEqual(savedPending(h), pending); assert.equal(h.calls.filter(call => call.action === "codex-work/submit").length, 1);
  const resumed = harness({ storage: h.storage }); await resumed.panel.setActive(true); assert.equal(posts(resumed).length, 0); assert.deepEqual(savedPending(resumed), pending); assert.equal(resumed.panel.canReload(), false); const job = jobFixture(); job.requestId = pending.requestId; resumed.setJobs([job]); await resumed.panel.refresh(); assert.equal(savedPending(resumed), null); assert.equal(posts(resumed).length, 0);
});
await test("foreign submit acknowledgement stays uncertain and cannot show successful creation", async () => {
  const h = harness(); await reviewCurrent(h); h.hook(action => action === "codex-work/submit" ? h.reply({ recordId: "f".repeat(32), job: jobFixture("f".repeat(32)) }) : undefined); h.byText("确认创建 Agent").click(); await flush(); assert.ok(savedPending(h)); assert.match(h.byClass("workflow-notice").textContent, /核对|保留/); assert.doesNotMatch(h.byClass("workflow-notice").textContent, /Agent 已创建/); assert.equal(h.calls.filter(call => call.action === "codex-work/submit").length, 1);
});
await test("progress uses only this record and displays report-only output without inventing file modifications", async () => {
  const h = harness(); const report = jobFixture(); report.status = "completed"; report.codexWork.terminalEventObserved = true; report.result = { text: "<img onerror=fixture>报告原文", reportOnly: true }; h.setJobs([report, jobFixture("f".repeat(32)), { ...jobFixture(), executionEngine: "other_engine" }]); await h.panel.setActive(true); assert.equal(h.byClass("codex-work-runs").children.length, 1); assert.match(h.byClass("codex-work-runs").textContent, /报告原文.*本轮只有报告/); assert.doesNotMatch(h.byClass("codex-work-runs").textContent, /已核实文件/); assert.equal(posts(h).length, 0);
});
await test("running progress renders the actual public codexWork entries as safe text without claiming Output", async () => {
  const h = harness(), job = jobFixture(); job.log = "wrong legacy field"; job.progress = "wrong top-level field"; job.codexWork.progress = [{ kind: "item/agentMessage/delta", itemId: "agent-item", text: "正在阅读源码\n保留换行" }, { kind: "item/commandExecution/outputDelta", itemId: "command-item", text: "<img onerror=fixture>真实命令进度" }, { kind: "item/fileChange/outputDelta", itemId: "file-item", text: "准备修改 source.txt" }]; h.setJobs([job]); await h.panel.setActive(true);
  assert.equal(h.byClass("codex-work-progress").textContent, "正在阅读源码\n保留换行\n<img onerror=fixture>真实命令进度\n准备修改 source.txt"); assert.match(h.byClass("codex-work-runs").textContent, /执行中/); assert.doesNotMatch(h.byClass("codex-work-runs").textContent, /wrong legacy|wrong top-level|Output|已完成|已核实文件|\[object Object\]/); assert.equal(posts(h).length, 0); await h.panel.setActive(false);
});
await test("completed public file evidence renders concrete added modified removed paths instead of object coercion", async () => {
  const h = harness(), job = jobFixture(); job.status = "completed"; Object.assign(job.codexWork, { terminalEventObserved: true, terminalStatus: "completed", executionVerified: true }); job.result = { source: "codex_agent", runId: job.id, sourceSha256: job.codexWork.sourceSha256, status: "completed", terminalEventObserved: true, terminalStatus: "completed", text: "真实完成报告", executionVerified: true, reportOnly: false, changedFiles: [{ path: "src/new.txt", change: "added", beforeSha256: null, afterSha256: "a".repeat(64) }, { path: "source.txt", change: "modified", beforeSha256: "b".repeat(64), afterSha256: "c".repeat(64) }, { path: "old.txt", change: "removed", beforeSha256: "d".repeat(64), afterSha256: null }] }; h.setJobs([job]); await h.panel.setActive(true);
  const text = h.byClass("codex-work-runs").textContent; assert.match(text, /已完成.*Output.*真实完成报告.*已核实文件/); assert.match(text, /新增：src\/new\.txt.*修改：source\.txt.*删除：old\.txt/); assert.doesNotMatch(text, /\[object Object\]|本轮只有报告/); assert.equal(posts(h).length, 0);
  job.result.changedFiles.push({ path: "../outside.txt", change: "added", beforeSha256: null, afterSha256: "e".repeat(64) }, { path: "bad-proof.txt", change: "modified", beforeSha256: "invalid", afterSha256: "f".repeat(64) }); h.setJobs([job]); await h.panel.refresh(); assert.match(h.byClass("codex-work-runs").textContent, /部分文件变更信息尚待核对/); assert.doesNotMatch(h.byClass("codex-work-runs").textContent, /outside\.txt|bad-proof\.txt/);
  job.codexWork.executionVerified = false; h.setJobs([job]); await h.panel.refresh(); assert.doesNotMatch(h.byClass("codex-work-runs").textContent, /已核实文件/);
});
await test("phone can view and cancel a desktop-origin Agent only with exact current API scope", async () => {
  const h = harness(), job = jobFixture(); job.mobileDialogue = null; h.setJobs([job]); await h.panel.setActive(true); assert.match(h.byClass("codex-work-runs").textContent, /Agent 1|执行中/); h.byText("取消这个 Agent").click(); await flush(); const sent = posts(h)[0]; assert.equal(sent.action, "codex-work/cancel"); assert.deepEqual(Object.keys(sent.body).sort(), ["requestId", "jobId", "threadId", "turnId", "sourceSha256", "clientId", "sessionId"].sort()); assert.equal(sent.body.clientId, identity.clientId); assert.equal(sent.body.sessionId, identity.sessionId); assert.match(h.byClass("codex-work-runs").textContent, /等待电脑取消回执/); assert.doesNotMatch(h.byClass("codex-work-runs").textContent, /已取消/); await h.panel.setActive(false);
});
await test("desktop runs and cancellation retain record-only reads and the original five-field request", async () => {
  const h = harness({ options: { phone: false, getScope: undefined } }), job = jobFixture(); job.mobileDialogue = null; h.setJobs([job]); await h.panel.setActive(true); assert.deepEqual(Object.fromEntries(h.calls.find(call => call.action === "codex-work/runs").query), { recordId: identity.recordId }); h.byText("取消这个 Agent").click(); await flush(); assert.deepEqual(Object.keys(posts(h)[0].body).sort(), ["requestId", "jobId", "threadId", "turnId", "sourceSha256"].sort()); assert.equal(posts(h)[0].request.headers["X-Codex-Phone"], undefined); await h.panel.setActive(false);
});
await test("phone identity changes or missing fresh scope cannot reuse old progress or cancellation authority", async () => {
  for (const scope of [null, { ...scopeFor(identity), recordId: "6".repeat(32) }, { ...scopeFor(identity), sessionId: "7".repeat(32) }, { ...scopeFor(identity), clientId: "90909090-9090-4090-8090-909090909090" }]) {
    const h = harness(), job = jobFixture(); h.setJobs([job]); await h.panel.setActive(true); h.setScope(scope); h.byText("取消这个 Agent").click(); await flush(); assert.equal(posts(h).length, 0); assert.doesNotMatch(h.byClass("codex-work-runs").textContent, /Agent 1|只在内存/); assert.equal(h.byLabel("本轮 Work 底稿").value, ""); assert.match(h.byClass("workflow-notice").textContent, /重新载入当前讨论.*草稿保留/); assert.equal(h.byText("核对本轮 Work").disabled, true); await h.panel.setActive(false);
  }
  const h = harness({ options: { getScope: undefined } }); await h.panel.setActive(true); assert.equal(h.calls.some(call => call.action === "codex-work/runs"), false); assert.equal(posts(h).length, 0);
});
await test("foreign API scope or old phone job identity cannot become current progress", async () => {
  const h = harness(), job = jobFixture(); h.setJobs([job]); await h.panel.setActive(true); h.hook(action => action === "codex-work/runs" ? h.reply({ recordId: identity.recordId, scope: { ...scopeFor(identity), sessionId: "7".repeat(32) }, runs: [job] }) : undefined); await h.panel.refresh(); assert.doesNotMatch(h.byClass("codex-work-runs").textContent, /Agent 1/); assert.match(h.byClass("workflow-notice").textContent, /进度回执讨论身份不一致/); h.hook(null);
  const old = jobFixture(); old.mobileDialogue.id = "7".repeat(32); const missing = jobFixture(); delete missing.mobileDialogue; h.setJobs([old, missing]); await h.panel.refresh(); assert.doesNotMatch(h.byClass("codex-work-runs").textContent, /Agent 1/); assert.equal(posts(h).length, 0); await h.panel.setActive(false);
});
await test("cancel requests preserve the exact running Agent and acknowledgement alone does not mean cancelled", async () => {
  const h = harness(); const job = jobFixture(); h.setJobs([job]); await h.panel.setActive(true); h.byText("取消这个 Agent").click(); await flush(); const sent = posts(h); assert.equal(sent.length, 1); assert.equal(sent[0].action, "codex-work/cancel"); for (const [key, value] of Object.entries({ jobId: job.id, threadId: job.codexWork.threadId, turnId: job.codexWork.turnId, sourceSha256: job.codexWork.sourceSha256 })) assert.equal(sent[0].body[key], value); assert.match(h.byClass("codex-work-runs").textContent, /等待电脑取消回执/); assert.doesNotMatch(h.byClass("codex-work-runs").textContent, /已取消/); h.byText("查看进度").click(); await flush(); assert.equal(posts(h).length, 1);
  const stopped = { ...job, status: "interrupted", codexWork: { ...job.codexWork, terminalEventObserved: true, cancellationVerified: true } }; h.setJobs([stopped]); await h.panel.refresh(); assert.match(h.byClass("codex-work-runs").textContent, /已取消/);
});
await test("cancel acknowledgement for another turn is rejected and interrupted without proof stays unverified", async () => {
  const h = harness(); const job = jobFixture(); h.setJobs([job]); await h.panel.setActive(true); h.hook(action => action === "codex-work/cancel" ? h.reply({ recordId: job.recordId, job: { ...job, codexWork: { ...job.codexWork, turnId: "wrong-turn", cancellationVerified: true, terminalEventObserved: true } } }) : undefined); h.byText("取消这个 Agent").click(); await flush(); assert.match(h.byClass("workflow-notice").textContent, /目标不一致|核对/); assert.doesNotMatch(h.root.textContent, /已取消|已收到电脑取消回执/); assert.equal(posts(h).length, 1);
  const stopped = { ...job, status: "interrupted" }; h.setJobs([stopped]); await h.panel.refresh(); assert.match(h.byClass("codex-work-runs").textContent, /中断结果待核对/); assert.doesNotMatch(h.byClass("codex-work-runs").textContent, /已取消/); assert.equal(posts(h).length, 1);
});
await test("phone Work requires actual sandbox readiness before review or confirmation and never requests Windows permissions", async () => {
  const config = configFixture(); config.setup = { ready: false, busy: false, status: "not_started" }; const h = harness({ config }); await h.panel.setActive(true);
  assert.equal(h.byText("核对本轮 Work").disabled, true); h.byText("核对本轮 Work").click(); await flush(); assert.equal(posts(h).length, 0); assert.match(h.byClass("codex-work-setup").textContent, /首次 Work.*电脑.*Windows 权限/);
  const ready = configFixture(); h.setConfig(ready); await h.panel.refresh(); assert.equal(h.byText("核对本轮 Work").disabled, false); h.byText("核对本轮 Work").click(); await flush(); assert.equal(posts(h).length, 1); assert.equal(h.byText("确认创建 Agent").disabled, false);
  ready.setup = { ready: false, busy: true, status: "running" }; h.setConfig(ready); await h.panel.refresh(); assert.equal(h.byText("确认创建 Agent").disabled, true); h.byText("确认创建 Agent").click(); await flush(); assert.equal(posts(h).length, 1); assert.equal(h.byText("配置 Console Work 沙箱（Windows 授权）"), undefined);
});
await test("unavailable saved Work model remains visible until explicitly changed and survives catalog restoration without fallback", async () => {
  const storage = new Map(), warm = harness({ storage }); await warm.panel.setActive(true); const changed = configFixture(); changed.subscription.models = [{ slug: "new-authorized-model", displayName: "当前真实模型名称" }];
  const h = harness({ storage, config: changed }); await h.panel.setActive(true); const model = h.fieldControl("已授权模型"); assert.equal(model.value, "fixture-model"); assert.ok(model.children.find(item => item.value === "fixture-model" && item.disabled)); assert.match(h.byClass("workflow-notice").textContent, /原模型暂不可选.*不会自动/); assert.equal(h.byText("核对本轮 Work").disabled, true); assert.equal(posts(h).length, 0);
  h.byText("载入当前讨论").click(); await flush(); assert.equal(h.byText("核对本轮 Work").disabled, true); assert.equal(model.children.find(item => item.value === "new-authorized-model").textContent, "当前真实模型名称"); model.value = "new-authorized-model"; model.fire("change"); assert.equal(h.byText("核对本轮 Work").disabled, false);
  const empty = configFixture(); empty.subscription = { ...empty.subscription, connected: false, status: "catalog_loading", models: [] }; h.setConfig(empty); await h.panel.refresh(); assert.equal(model.value, "new-authorized-model"); assert.equal(h.byText("核对本轮 Work").disabled, true); assert.equal(posts(h).length, 0);
  const restored = configFixture(); restored.subscription.models.push(changed.subscription.models[0]); h.setConfig(restored); await h.panel.refresh(); assert.equal(model.value, "new-authorized-model"); assert.equal(h.byText("核对本轮 Work").disabled, false); assert.equal(posts(h).length, 0);
  h.byText("核对本轮 Work").click(); await flush(); assert.equal(posts(h)[0].body.subscription.modelSlug, "new-authorized-model");
});
await test("a new account catalog retires an old Work review rather than confirming its stale model binding", async () => {
  const h = harness(); await reviewCurrent(h); assert.equal(h.byText("确认创建 Agent").disabled, false); const refreshed = configFixture(); refreshed.subscription.catalogRevision = "7".repeat(64); h.setConfig(refreshed); await h.panel.refresh(); assert.equal(h.byText("确认创建 Agent").disabled, true); assert.equal(h.byClass("workflow-review").hidden, true); h.byText("确认创建 Agent").click(); await flush(); assert.equal(posts(h).length, 1); assert.equal(posts(h)[0].action, "codex-work/review");
});
console.log(`${count} Codex Work UI behavior checks passed; no real app, workspace, or model accessed.`);
