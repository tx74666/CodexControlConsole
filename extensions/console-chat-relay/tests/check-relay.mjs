#!/usr/bin/env node
// Pure, isolated fixtures: no browser process, live Chat, production DB or network.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import { webcrypto } from "node:crypto";
const directory = new URL("../", import.meta.url);
const context = vm.createContext({ crypto: webcrypto, TextEncoder, URL, Date, Uint8Array, Set, Error, structuredClone,
  setTimeout, clearTimeout, importScripts() {} });
vm.runInContext(await readFile(new URL("lib/protocol.js", directory), "utf8"), context);
vm.runInContext(await readFile(new URL("service-worker.js", directory), "utf8"), context);
vm.runInContext(await readFile(new URL("content-script.js", directory), "utf8"), context);
const relay = context.ConsoleChatRelay;
let tests = 0;
async function test(name, run) { await run(); tests++; console.log(`PASS ${name}`); }
function rejected(fn, code) { assert.throws(fn, error => error?.code === code); }
const dispatchId = "1234567890abcdef1234567890abcdef", attemptId = "12a45678-1234-4567-89ab-1234567890ab";
const sourceId = "eee3bb2e-c6cd-491d-a123-5481d49f8703", answerId = "8f848f8c-2eea-449a-b2c2-29ed433c8e78";
// These selectors exist only in the fixture. They are not a verified ChatGPT DOM contract.
const domContract = { version: 1, verified: true, surface: "chrome", source: "cua", capturedAt: "2026-10-05T12:00:00.000Z",
  observationSha256: "a".repeat(64), selectors: { composer: "#composer", profile: "#profile", messages: ".message",
    userText: ".user-body", assistantText: ".answer-body", completion: "#complete", send: "#send", stop: "#stop",
    login: "#signed-in", chatMode: "#ordinary-chat" }, profiles: { fast: { label: "Instant" } } };
const prompt = "你好。\n保留 😀 和原换行。\n[Codex Console 发布编号：" + dispatchId + "]";
const prepare = relay.envelope("prepare", { dispatchId, attemptId }, { prompt, promptSha256: await relay.sha256(prompt), requestedProfile: "fast",
  target: { kind: "chatgpt", mode: "new" }, domContract });
function clone(value) { return JSON.parse(JSON.stringify(value)); }
const capture = relay.envelope("capture", prepare, { evidence: { source: "browser_dom", conversationUrl: "https://chatgpt.com/c/92a45678-1234-4567-89ab-1234567890ab",
  sourceUserMessageId: sourceId, assistantMessageId: answerId, sourceUnitKey: "fallback-turn-0:0:user", assistantUnitKey: "fallback-turn-0:1:assistant",
  promptText: prompt, answerText: "你好！", completion: { text: "Response complete", observedAfterCommit: true, stopPresent: false },
  profile: { requestedProfile: "fast", observedBefore: "Instant", observedAfter: "Instant" }, observedAt: "2026-10-05T12:00:00.000Z" } });
await test("UTC observation accepts JS/Python ISO and rejects invalid calendar/non-UTC dates", () => {
  for (const value of ["2026-10-05T12:00:00.000Z", "2026-10-05T12:00:00.123456+00:00", "2026-10-05T12:00:00Z"])
    assert.equal(relay.isoTime(value), true);
  for (const value of ["2026-02-30T12:00:00.000Z", "2026-10-05T12:00:00+08:00", "2026-10-05 12:00:00Z", "tomorrow"])
    assert.equal(relay.isoTime(value), false);
});
await test("explicit ordinary Chat prepare validates; actual SHA includes Unicode and newlines", async () => {
  assert.equal(relay.validatePrepare(prepare), prepare);
  assert.equal(await relay.sha256(prompt), prepare.promptSha256);
  assert.notEqual(await relay.sha256(prompt.replace("\n", " ")), prepare.promptSha256);
});
await test("missing/wrong/duplicate publication marker rejects frozen prompt", () => {
  for (const wrong of [prompt.replace(dispatchId, "f".repeat(32)), "你好", prompt + "\n[Codex Console 发布编号：" + dispatchId + "]"]) {
    rejected(() => relay.validatePrepare({ ...prepare, prompt: wrong }), "invalid_publication_marker");
  }
});
await test("Work/Codex/existing target cannot replace ordinary new Chat", () => {
  for (const target of [{ kind: "codex", mode: "new" }, { kind: "chatgpt", mode: "existing" }, { kind: "work", mode: "new" }])
    rejected(() => relay.validatePrepare({ ...prepare, target }), "wrong_target");
});
await test("claimToken/private path/model API cannot be smuggled into page payload", () => {
  for (const field of ["claimToken", "privatePath", "apiKey", "model", "targetThreadId"])
    rejected(() => relay.validatePrepare({ ...prepare, [field]: "hidden" }), "invalid_schema");
});
await test("high/Pro remain unverified and cannot downgrade to Instant", () => {
  for (const requestedProfile of ["high", "pro"]) rejected(() => relay.validatePrepare({ ...prepare, requestedProfile }), "profile_unverified");
});
await test("unverified profile mapping/DOM completion source refuses preparation", () => {
  const wrong = clone(prepare); wrong.domContract.profiles.fast.label = "Pro";
  rejected(() => relay.validatePrepare(wrong), "profile_unverified");
  wrong.domContract = clone(domContract); wrong.domContract.verified = false;
  rejected(() => relay.validatePrepare(wrong), "dom_contract_unverified");
  wrong.domContract = clone(domContract); wrong.domContract.surface = "iab";
  rejected(() => relay.validatePrepare(wrong), "dom_contract_unverified");
  delete wrong.domContract.selectors.send;
  rejected(() => relay.validatePrepare(wrong), "dom_contract_unverified");
});
await test("commitSend cannot supply a new prompt or target", () => {
  const commit = relay.envelope("commitSend", prepare);
  assert.equal(relay.validateCommit(commit), commit);
  rejected(() => relay.validateCommit({ ...commit, prompt: "different" }), "invalid_schema");
});
await test("prepared requires actual empty fresh root/Chat/login/Instant/no previous completion", () => {
  const observation = { url: "https://chatgpt.com/", chatMode: true, loginVerified: true, emptyComposer: true, observedProfile: "Instant", completionInitiallyPresent: false,
    surface: "chrome", observationSha256: "a".repeat(64), profileDom: { text: "Thinking effortInstant", reasoningEffort: "none" } };
  assert.ok(relay.validatePrepared(relay.envelope("prepared", prepare, { observation })));
  for (const patch of [{ url: capture.evidence.conversationUrl }, { url: "https://chatgpt.com/?prompt=secret" }, { chatMode: false }, { loginVerified: false },
    { emptyComposer: false }, { observedProfile: "Pro" }, { completionInitiallyPresent: true }])
    rejected(() => relay.validatePrepared(relay.envelope("prepared", prepare, { observation: { ...observation, ...patch } })), "prepare_observation_mismatch");
});
await test("actual DOM evidence uses source keys; no fabricated server turn ID", () => {
  assert.equal(relay.validateCapture(capture, prepare), capture);
  const wrong = clone(capture); wrong.evidence.turnId = "fabricated";
  rejected(() => relay.validateCapture(wrong, prepare), "invalid_schema");
});
await test("assistant DOM ordinal must follow its exact source user unit", () => {
  const wrong = clone(capture);
  wrong.evidence.sourceUnitKey = "fallback-turn-0:2:user";
  wrong.evidence.assistantUnitKey = "fallback-turn-0:1:assistant";
  rejected(() => relay.validateCapture(wrong, prepare), "capture_source_mismatch");
});
await test("late answer cannot attach to another dispatch/attempt", () => {
  const wrong = clone(capture); wrong.attemptId = "a2a45678-1234-4567-89ab-1234567890ab";
  rejected(() => relay.validateCapture(wrong, prepare), "capture_identity_mismatch");
});
await test("full prompt is compared exactly, including whitespace and emoji", () => {
  for (const promptText of [prompt + " ", prompt.replace("\n", " "), prompt.replace("😀", ""), "你好"])
    rejected(() => relay.validateCapture({ ...capture, evidence: { ...capture.evidence, promptText } }, prepare), "capture_prompt_mismatch");
});
await test("same ID or wrong role DOM keys cannot represent two actual messages", () => {
  const evidence = capture.evidence;
  for (const patch of [{ assistantMessageId: sourceId }, { sourceUserMessageId: "invented" }, { sourceUnitKey: "fallback:assistant" }])
    rejected(() => relay.validateCapture({ ...capture, evidence: { ...evidence, ...patch } }, prepare), "capture_source_mismatch");
});
await test("old completion/Stop still present/inexact completion reject main answer", () => {
  for (const patch of [{ observedAfterCommit: false }, { stopPresent: true }, { text: "Response started" }])
    rejected(() => relay.validateCapture({ ...capture, evidence: { ...capture.evidence, completion: { ...capture.evidence.completion, ...patch } } }, prepare), "capture_not_complete");
});
await test("actual profile changes after commit cannot masquerade as requested tier", () => {
  for (const patch of [{ observedBefore: "Pro" }, { observedAfter: "Thinking" }, { requestedProfile: "high" }])
    rejected(() => relay.validateCapture({ ...capture, evidence: { ...capture.evidence, profile: { ...capture.evidence.profile, ...patch } } }, prepare), "profile_changed");
});
await test("overlong answer is retained in browser for review, never claimed as a full capture", () => {
  rejected(() => relay.validateCapture({ ...capture, evidence: { ...capture.evidence, answerText: "字".repeat(20001) } }, prepare), "invalid_text");
});
await test("only observed exact ChatGPT conversation URL accepted, no private query data", () => {
  for (const url of ["https://chatgpt.com/", "https://evil.test/c/92a45678-1234-4567-89ab-1234567890ab", capture.evidence.conversationUrl + "?key=hidden"])
    rejected(() => relay.validateCapture({ ...capture, evidence: { ...capture.evidence, conversationUrl: url } }, prepare), "capture_source_mismatch");
});
await test("message attribute duplicate same UUID permitted; multiple actual sources rejected", () => {
  assert.equal(relay.messageIds(JSON.stringify([sourceId, sourceId])), sourceId);
  assert.equal(relay.messageIds(sourceId), sourceId);
  rejected(() => relay.messageIds(JSON.stringify([sourceId, answerId])), "capture_source_mismatch");
  rejected(() => relay.messageIds("fabricated"), "capture_source_mismatch");
});
await test("manifest permissions are confined to ChatGPT, own storage and native messaging", async () => {
  const manifest = JSON.parse(await readFile(new URL("manifest.json", directory), "utf8"));
  assert.deepEqual(manifest.permissions, ["nativeMessaging", "storage"]);
  assert.deepEqual(manifest.host_permissions, ["https://chatgpt.com/*"]);
  assert.equal(manifest.content_scripts[0].all_frames, false);
  assert.ok(!("externally_connectable" in manifest));
  const { createHash } = await import("node:crypto");
  const id = createHash("sha256").update(Buffer.from(manifest.key, "base64")).digest().subarray(0, 16).toString("hex")
    .replace(/[0-9a-f]/g, digit => String.fromCharCode(97 + parseInt(digit, 16)));
  assert.equal(id, relay.EXTENSION_ID);
});
class Event {
  listeners = new Set();
  addListener = listener => this.listeners.add(listener);
  removeListener = listener => this.listeners.delete(listener);
  emit = (...args) => { for (const listener of this.listeners) listener(...args); };
}
function storageFixture(initial = {}) {
  const data = clone(initial), writes = [];
  let failNext = false;
  return { data, writes, fail() { failNext = true; }, local: {
    async get(key) { return { [key]: data[key] === undefined ? undefined : clone(data[key]) }; },
    async set(value) { if (failNext) { failNext = false; throw new Error("fixture persistence rejected"); }
      Object.assign(data, clone(value)); writes.push(clone(value)); }
  } };
}
function preparedFor(value) {
  return relay.envelope("prepared", value, { observation: { url: "https://chatgpt.com/", chatMode: true, loginVerified: true,
    emptyComposer: true, observedProfile: "Instant", completionInitiallyPresent: false, surface: "chrome",
    observationSha256: value.domContract.observationSha256, profileDom: { text: "Thinking effortInstant", reasoningEffort: "none" } } });
}
function workerFixture(initial = {}) {
  const storage = storageFixture(initial), ports = [], tabs = [], calls = [], updates = new Event();
  let sendFailure = false, prepareFailure = false;
  const api = { storage, runtime: { id: relay.EXTENSION_ID,
    connectNative(host) {
      assert.equal(host, relay.HOST_NAME);
      const port = { onMessage: new Event(), onDisconnect: new Event(), sent: [],
        postMessage(value) { this.sent.push(clone(value)); }, disconnect() { this.onDisconnect.emit(); } };
      ports.push(port); return port;
    } }, tabs: { onUpdated: updates,
      async create(value) { tabs.push(clone(value)); return { id: 40 + tabs.length, status: "complete" }; },
      async get(id) { return { id, status: "complete" }; },
      async sendMessage(id, value) { calls.push({ id, value: clone(value) });
        if (value.type === "relay.content.prepare") {
          if (prepareFailure) { prepareFailure = false; throw new relay.RelayError("login_required", "隔离页面未登录，本次未发送。"); }
          return preparedFor(value.prepare);
        }
        if (sendFailure) throw new Error("fixture click outcome unknown");
        return { committed: true };
      } } };
  const controller = context.ConsoleChatRelayWorker.createController(api);
  const status = clientReady => ({ protocol: relay.PROTOCOL, type: "status", hostName: relay.HOST_NAME, enabled: true,
    approved: true, configured: true, message: "fixture-only approved endpoint", clientReady });
  return { api, storage, ports, tabs, calls, controller, status,
    failSend() { sendFailure = true; },
    failPrepare() { prepareFailure = true; },
    async enable() { await controller.popup("status"); ports.at(-1).onMessage.emit(status(false));
      await controller.popup("enable"); ports.at(-1).onMessage.emit(status(true)); }
  };
}
await test("default-disabled worker performs no native connect or queue read", async () => {
  const fixture = workerFixture(); await fixture.controller.start();
  assert.equal(fixture.ports.length, 0); assert.equal(fixture.tabs.length, 0);
  assert.equal(fixture.controller.view().enabled, false);
});
await test("hello/status inspect does not ready; enable requires approved/configured actual endpoint", async () => {
  const f = workerFixture(); await f.controller.popup("status");
  assert.deepEqual(f.ports[0].sent.map(message => message.type), ["hello"]);
  await assert.rejects(f.controller.popup("enable"), error => error.code === "approval_required");
  assert.equal(f.tabs.length, 0);
  f.ports[0].onMessage.emit(f.status(false)); await f.controller.popup("enable");
  assert.equal(f.ports[0].sent.at(-1).type, "ready");
  assert.equal(f.ports[0].sent.at(-1).clientReady, true);
});
await test("worker owns one exact fresh tab and persists intent before a unique Send", async () => {
  const f = workerFixture(); await f.enable(); await f.controller.native(prepare);
  assert.deepEqual(f.tabs, [{ url: "https://chatgpt.com/", active: true }]);
  assert.equal(f.controller.state().active.phase, "prepared");
  await f.controller.native(relay.envelope("commitSend", prepare));
  assert.equal(f.calls.filter(call => call.value.type === "relay.content.commit").length, 1);
  assert.ok(f.storage.writes.some(write => write.consoleChatRelayV1?.active?.phase === "send_intent"));
  await f.controller.native(relay.envelope("commitSend", prepare));
  assert.equal(f.calls.filter(call => call.value.type === "relay.content.commit").length, 1);
  assert.equal(f.controller.state().active.phase, "needs_review");
});
await test("known unsent preparation failure durably retains tombstone and releases only its active request", async () => {
  const f = workerFixture(); await f.enable(); f.failPrepare();
  const port = f.ports[0], postMessage = port.postMessage.bind(port);
  port.postMessage = value => {
    if (value.type === "blocked") {
      assert.equal(f.storage.data.consoleChatRelayV1.attempts[dispatchId].phase, "failed");
      assert.equal(f.storage.data.consoleChatRelayV1.active, null);
    }
    postMessage(value);
  };
  await f.controller.native(prepare);
  assert.equal(port.sent.at(-1).type, "blocked");
  assert.equal(port.sent.at(-1).code, "login_required");
  assert.equal(f.controller.state().active, null);
  assert.equal(f.controller.state().attempts[dispatchId].attemptId, attemptId);
  assert.equal(f.controller.state().attempts[dispatchId].promptSha256, prepare.promptSha256);
  assert.equal(f.calls.filter(call => call.value.type === "relay.content.commit").length, 0);
  await f.controller.native(prepare);
  assert.equal(f.tabs.length, 1);
  assert.equal(f.controller.state().attempts[dispatchId].phase, "failed");
  const next = { ...prepare, dispatchId: "a".repeat(32), attemptId: "a2a45678-1234-4567-89ab-1234567890ab",
    prompt: prompt.replace(dispatchId, "a".repeat(32)) };
  next.promptSha256 = await relay.sha256(next.prompt);
  await f.controller.native(next);
  assert.equal(f.tabs.length, 2); assert.equal(f.controller.state().active.phase, "prepared");
  assert.equal(f.controller.state().attempts[dispatchId].phase, "failed");
  const restart = workerFixture(f.storage.data); await restart.controller.start();
  restart.ports[0].onMessage.emit(restart.status(true));
  await restart.controller.native(prepare);
  assert.equal(restart.tabs.length, 0); assert.equal(restart.calls.length, 0);
  assert.equal(restart.controller.state().attempts[dispatchId].phase, "failed");
});
await test("known blocked validation while prepared releases only exact matching unsent identity", async () => {
  const f = workerFixture(); await f.enable(); await f.controller.native(prepare);
  const invalid = clone(prepare); invalid.domContract.verified = false;
  await f.controller.native(invalid);
  assert.equal(f.controller.state().active, null);
  assert.equal(f.storage.data.consoleChatRelayV1.attempts[dispatchId].phase, "failed");
  assert.equal(f.calls.filter(call => call.value.type === "relay.content.commit").length, 0);
});
await test("blocked unrelated request after intent cannot release or fail the waiting request", async () => {
  const f = workerFixture(); await f.enable(); await f.controller.native(prepare);
  await f.controller.native(relay.envelope("commitSend", prepare));
  const next = { ...prepare, dispatchId: "a".repeat(32), attemptId: "a2a45678-1234-4567-89ab-1234567890ab",
    prompt: prompt.replace(dispatchId, "a".repeat(32)) };
  next.promptSha256 = await relay.sha256(next.prompt);
  await f.controller.native(next);
  assert.equal(f.ports[0].sent.at(-1).type, "blocked");
  assert.equal(f.controller.state().active.prepare.dispatchId, dispatchId);
  assert.equal(f.controller.state().active.phase, "waiting");
  assert.equal(f.controller.state().attempts[dispatchId].phase, "waiting");
  assert.equal(f.tabs.length, 1);
  assert.equal(f.calls.filter(call => call.value.type === "relay.content.commit").length, 1);
});
await test("unknown click/reconnect/duplicate attempt never creates another tab or repeats Send", async () => {
  const f = workerFixture(); await f.enable(); await f.controller.native(prepare); f.failSend();
  await f.controller.native(relay.envelope("commitSend", prepare));
  await f.controller.native({ ...prepare, attemptId: "a2a45678-1234-4567-89ab-1234567890ab" });
  assert.equal(f.tabs.length, 1); assert.equal(f.calls.filter(call => call.value.type === "relay.content.commit").length, 1);
  assert.equal(f.controller.state().active.phase, "needs_review");
  assert.equal(f.storage.data.consoleChatRelayV1.attempts[dispatchId].phase, "needs_review");
  const restart = workerFixture(f.storage.data); await restart.controller.start();
  restart.ports[0].onMessage.emit(restart.status(true));
  await restart.controller.native(prepare);
  assert.equal(restart.tabs.length, 0); assert.equal(restart.calls.length, 0);
});
await test("failed durable intent write prevents all Send controls", async () => {
  const f = workerFixture(); await f.enable(); await f.controller.native(prepare); f.storage.fail();
  await assert.rejects(f.controller.native(relay.envelope("commitSend", prepare)), /persistence rejected/);
  assert.equal(f.calls.filter(call => call.value.type === "relay.content.commit").length, 0);
});
await test("actual page evidence must come from owned tab/top frame/current URL", async () => {
  const f = workerFixture(); await f.enable(); await f.controller.native(prepare); await f.controller.native(relay.envelope("commitSend", prepare));
  const sender = { id: relay.EXTENSION_ID, tab: { id: 41 }, frameId: 0, url: capture.evidence.conversationUrl };
  for (const patch of [{ id: "another-extension" }, { tab: { id: 99 } }, { frameId: 1 }, { url: "https://evil.test/" }])
    await assert.rejects(f.controller.page(capture, { ...sender, ...patch }), error => error.code === "wrong_page_source");
  assert.equal(f.controller.state().active.phase, "waiting");
  assert.equal(f.ports[0].sent.filter(value => value.type === "capture").length, 0);
});
await test("capture awaits exact stored receipt; UI label never becomes verified backend capability", async () => {
  const f = workerFixture(); await f.enable(); await f.controller.native(prepare); await f.controller.native(relay.envelope("commitSend", prepare));
  const sender = { id: relay.EXTENSION_ID, tab: { id: 41 }, frameId: 0, url: capture.evidence.conversationUrl };
  const accepted = relay.envelope("accepted", prepare, { evidence: Object.fromEntries(["source", "conversationUrl", "sourceUserMessageId", "sourceUnitKey", "promptText", "observedAt", "profile"].map(key => [key, capture.evidence[key]])) });
  await f.controller.page(accepted, sender); await f.controller.page(capture, sender);
  assert.equal(f.controller.state().active.phase, "capture_forwarded");
  const stored = relay.envelope("stored", prepare, { sourceKind: "browser_dom", actualProfileObserved: "Instant",
    executionCapabilities: { verified: false, source: "browser_dom_ui_label" } });
  await assert.rejects(f.controller.native({ ...stored, executionCapabilities: { verified: true, source: "browser_dom_ui_label" } }), error => error.code === "invalid_capability_receipt");
  await f.controller.native(stored); assert.equal(f.controller.state().active.phase, "stored");
  assert.equal(f.controller.state().active.prepare.prompt, undefined);
  await f.controller.native(stored); assert.equal(f.controller.state().active.phase, "stored");
  await f.controller.native(prepare); assert.equal(f.controller.state().active.phase, "stored");
  assert.equal(f.tabs.length, 1);
  const next = { ...prepare, dispatchId: "a".repeat(32), attemptId: "a2a45678-1234-4567-89ab-1234567890ab",
    prompt: prompt.replace(dispatchId, "a".repeat(32)) };
  next.promptSha256 = await relay.sha256(next.prompt);
  await f.controller.native(next); assert.equal(f.tabs.length, 2); assert.equal(f.controller.state().active.phase, "prepared");
  const saved = clone(f.storage.data); saved.consoleChatRelayV1.active = { prepare: { protocol: relay.PROTOCOL, dispatchId, attemptId }, phase: "stored", observedProfile: "Instant" };
  const restart = workerFixture(saved); await restart.controller.start(); assert.equal(restart.controller.state().active.phase, "stored");
});
class Node {
  constructor(text = "", attributes = {}) { this.textContent = text; this.attributes = attributes; this.isConnected = true; this.children = new Map(); }
  get innerText() { return this.textContent; }
  getAttribute(key) { return this.attributes[key] ?? null; }
  getClientRects() { return [{}]; }
  querySelectorAll(selector) { return this.children.get(selector) || []; }
  focus() {}
  dispatchEvent() { return true; }
}
function contentFixture({ promptText = prompt, completed = false, stop = false, extraUser = false, clickThrows = false, draft = "" } = {}) {
  const storage = storageFixture(), messages = [], emitted = [], timers = new Map(), location = { href: "https://chatgpt.com/" };
  const composer = new Node(draft, { role: "textbox", contenteditable: "true" });
  const model = new Node("Thinking effortInstant", { "data-selected-reasoning-effort": "none" });
  const chat = new Node("Chat", { "aria-pressed": "true" }), login = new Node("Signed in"), complete = new Node("Response complete"), stopNode = new Node("Stop");
  const items = new Map([["#composer", [composer]], ["#profile", [model]], ["#ordinary-chat", [chat]], ["#signed-in", [login]], [".message", messages], ["#complete", []], ["#stop", []]]);
  function message(id, unit, text, role) {
    const node = new Node(text + (role === "user" ? "👍" : "ChatGPT said:"), { "data-chatgpt-search-message-ids": JSON.stringify([id, id]), "data-chatgpt-search-unit-key": unit });
    node.children.set(role === "user" ? ".user-body" : ".answer-body", [new Node(text)]); return node;
  }
  let clicks = 0, mutation, nextTimer = 1;
  const send = new Node("Send", { type: "submit" });
  send.click = () => {
    assert.equal(storage.data[context.ConsoleChatRelayContent.CONTENT_PREFIX + dispatchId]?.phase, "send_intent");
    clicks++; location.href = capture.evidence.conversationUrl;
    messages.push(message(sourceId, "fallback-turn-0:0:user", promptText, "user"));
    if (extraUser) messages.push(message("a2a45678-1234-4567-89ab-1234567890ab", "fallback-turn-1:0:user", "other", "user"));
    messages.push(message(answerId, "fallback-turn-0:1:assistant", "真实隔离答案", "assistant"));
    if (completed) items.set("#complete", [complete]); if (stop) items.set("#stop", [stopNode]);
    if (clickThrows) throw new Error("fixture click result unknown");
  };
  items.set("#send", [send]);
  class Observer { constructor(callback) { mutation = callback; } observe() {} disconnect() { mutation = null; } }
  const env = { chrome: { storage, runtime: { async sendMessage(value) { emitted.push(clone(value)); return { received: true }; } } },
    document: { documentElement: {}, querySelectorAll(selector) { return items.get(selector) || []; } }, location, MutationObserver: Observer,
    InputEvent: class { constructor(type, detail) { this.type = type; this.detail = detail; } }, now: () => Date.parse("2026-10-05T12:00:00.000Z"),
    setTimeout(fn, timeout) { const id = nextTimer++; timers.set(id, { fn, timeout }); return id; }, clearTimeout(id) { timers.delete(id); } };
  return { env, items, storage, emitted, composer, model, messages, timers, controller: context.ConsoleChatRelayContent.createController(env),
    clicks: () => clicks, async mutation() { mutation?.(); await this.controller.idle(); await this.controller.idle(); } };
}
await test("content prepare is readonly and cannot overwrite any existing user draft", async () => {
  const f = contentFixture({ draft: "未发送草稿" });
  await assert.rejects(f.controller.receive({ type: "relay.content.prepare", prepare }), error => error.code === "composer_changed");
  assert.equal(f.composer.textContent, "未发送草稿"); assert.equal(f.clicks(), 0); assert.equal(f.storage.writes.length, 0);
});
await test("pure fixture owns empty Chat, commits once, excludes reactions/title and captures actual source units", async () => {
  const f = contentFixture({ completed: true });
  relay.validatePrepared(await f.controller.receive({ type: "relay.content.prepare", prepare }));
  assert.equal(f.clicks(), 0); assert.equal(f.composer.textContent, "");
  assert.equal((await f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) })).committed, true);
  await f.controller.idle();
  const accepted = f.emitted.find(value => value.type === "accepted"), actual = f.emitted.find(value => value.type === "capture");
  assert.ok(accepted); assert.ok(actual); relay.validateCapture(actual, prepare);
  assert.equal(actual.evidence.promptText, prompt); assert.equal(actual.evidence.answerText, "真实隔离答案");
  await assert.rejects(f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) }), error => error.code === "commit_not_prepared");
  assert.equal(f.clicks(), 1);
});
await test("late user draft or model change after prepared prevents physical Send", async () => {
  for (const change of [f => { f.composer.textContent = "late draft"; }, f => { f.model.textContent = "Pro"; }]) {
    const f = contentFixture(); await f.controller.receive({ type: "relay.content.prepare", prepare }); change(f);
    await assert.rejects(f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) }));
    assert.equal(f.clicks(), 0);
  }
});
await test("content persistent intent failure or throwing Send never permits retry", async () => {
  const rejectedStore = contentFixture(); await rejectedStore.controller.receive({ type: "relay.content.prepare", prepare }); rejectedStore.storage.fail();
  await assert.rejects(rejectedStore.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) }));
  assert.equal(rejectedStore.clicks(), 0);
  const f = contentFixture({ clickThrows: true }); await f.controller.receive({ type: "relay.content.prepare", prepare });
  await assert.rejects(f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) }));
  await assert.rejects(f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) }));
  assert.equal(f.clicks(), 1); assert.equal(f.controller.phase(), "needs_review");
});
await test("Stop prevents premature final; DOM completion event then returns one answer", async () => {
  const f = contentFixture({ completed: true, stop: true }); await f.controller.receive({ type: "relay.content.prepare", prepare });
  await f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) }); await f.controller.idle();
  assert.equal(f.emitted.filter(value => value.type === "capture").length, 0);
  f.items.set("#stop", []); await f.mutation();
  assert.equal(f.emitted.filter(value => value.type === "capture").length, 1);
  await f.mutation(); assert.equal(f.emitted.filter(value => value.type === "capture").length, 1);
});
await test("other user input stops attribution rather than attaching an unrelated final", async () => {
  const f = contentFixture({ completed: true, extraUser: true }); await f.controller.receive({ type: "relay.content.prepare", prepare });
  await f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) });
  await f.controller.idle(); await f.controller.idle();
  assert.equal(f.emitted.filter(value => value.type === "capture").length, 0); assert.equal(f.controller.phase(), "needs_review");
});
await test("commit without a genuine prepared authority cannot type or Send", async () => {
  const f = contentFixture();
  await assert.rejects(f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) }), error => error.code === "commit_not_prepared");
  assert.equal(f.composer.textContent, ""); assert.equal(f.clicks(), 0);
});
console.log(`PASS ${tests} isolated relay checks; no real Chat/browser or production state accessed.`);
