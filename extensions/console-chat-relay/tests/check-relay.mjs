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
await test("only an explicit null Stop is unknown; other selectors remain mandatory and nonempty", () => {
  const unknown = clone(prepare); unknown.domContract.selectors.stop = null;
  assert.equal(relay.validatePrepare(unknown), unknown);
  for (const key of Object.keys(domContract.selectors).filter(key => key !== "stop")) {
    const wrong = clone(unknown); wrong.domContract.selectors[key] = null;
    rejected(() => relay.validatePrepare(wrong), "dom_contract_unverified");
  }
  for (const stop of ["", " ", false, 0, undefined]) {
    const wrong = clone(prepare); wrong.domContract.selectors.stop = stop;
    rejected(() => relay.validatePrepare(wrong), "dom_contract_unverified");
  }
  const missing = clone(unknown); delete missing.domContract.selectors.stop;
  rejected(() => relay.validatePrepare(missing), "dom_contract_unverified");
});
await test("only CUA Chrome and Edge surfaces can prepare; other surfaces remain unverified", () => {
  for (const surface of ["chrome", "edge"]) {
    const value = clone(prepare); value.domContract.surface = surface;
    assert.equal(relay.validatePrepare(value), value);
  }
  for (const surface of ["iab", "fixture", "firefox", "Chrome", ""]) {
    const value = clone(prepare); value.domContract.surface = surface;
    rejected(() => relay.validatePrepare(value), "dom_contract_unverified");
  }
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
await test("prepared accepts only observed English/Chinese Instant labels with none effort", () => {
  for (const surface of ["chrome", "edge"]) {
    const value = clone(prepare); value.domContract.surface = surface;
    const response = preparedFor(value);
    for (const text of ["Instant", "Thinking effortInstant", "思考强度Instant", "思考强度即时"]) {
      response.observation.profileDom.text = text;
      assert.equal(relay.validatePrepared(response), response);
    }
    for (const text of ["思考强度Pro", "思考强度 Instant", "思考强度Instant extra"]) {
      response.observation.profileDom.text = text;
      rejected(() => relay.validatePrepared(response), "profile_unverified");
    }
    response.observation.profileDom = { text: "思考强度Instant", reasoningEffort: "high" };
    rejected(() => relay.validatePrepared(response), "profile_unverified");
    response.observation.profileDom.reasoningEffort = "none";
    response.observation.surface = "iab";
    rejected(() => relay.validatePrepared(response), "prepare_observation_mismatch");
  }
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
await test("capture Stop evidence must exactly match the frozen known or unknown selector", () => {
  const unknown = clone(prepare); unknown.domContract.selectors.stop = null;
  const value = clone(capture); value.evidence.completion.stopPresent = null;
  assert.equal(relay.validateCapture(value, unknown), value);
  for (const stopPresent of [false, true, 0, "", undefined]) {
    const wrong = clone(value); wrong.evidence.completion.stopPresent = stopPresent;
    rejected(() => relay.validateCapture(wrong, unknown), "capture_not_complete");
  }
  for (const stopPresent of [null, true, 0, "", undefined]) {
    const wrong = clone(capture); wrong.evidence.completion.stopPresent = stopPresent;
    rejected(() => relay.validateCapture(wrong, prepare), "capture_not_complete");
  }
  for (const patch of [{ observedAfterCommit: false }, { text: "回答已完城" }, { text: "Response started" }]) {
    const wrong = clone(value); Object.assign(wrong.evidence.completion, patch);
    rejected(() => relay.validateCapture(wrong, unknown), "capture_not_complete");
  }
  const wrongSource = clone(value); wrongSource.evidence.promptText += " ";
  rejected(() => relay.validateCapture(wrongSource, unknown), "capture_prompt_mismatch");
  const wrongProfile = clone(value); wrongProfile.evidence.profile.observedAfter = "Pro";
  rejected(() => relay.validateCapture(wrongProfile, unknown), "profile_changed");
});
await test("observed Chinese completion validates exactly and typo/localized guesses never count as final", () => {
  const actual = clone(capture); actual.evidence.completion.text = "回答已完成";
  assert.equal(relay.validateCapture(actual, prepare), actual);
  for (const text of ["回答已完", "回答已完成。", "回答完成", "回答已开始"])
    rejected(() => relay.validateCapture({ ...capture, evidence: { ...capture.evidence,
      completion: { ...capture.evidence.completion, text } } }, prepare), "capture_not_complete");
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
    emptyComposer: true, observedProfile: "Instant", completionInitiallyPresent: false, surface: value.domContract.surface,
    observationSha256: value.domContract.observationSha256, profileDom: { text: "Thinking effortInstant", reasoningEffort: "none" } } });
}
function readinessFor(value = prepare) {
  return relay.envelope("checkReady", value, { domContract: clone(value.domContract) });
}
function pageReadyFor(value = prepare) {
  return relay.envelope("pageReady", value, { observation: { url: "https://chatgpt.com/", chatMode: true, loginVerified: true,
    emptyComposer: true, modelControlPresent: true, completionInitiallyPresent: false,
    surface: value.domContract.surface, observationSha256: value.domContract.observationSha256 } });
}
function workerFixture(initial = {}, browserSurface = "chrome", worker = context.ConsoleChatRelayWorker) {
  const storage = storageFixture(initial), ports = [], tabs = [], calls = [], updates = new Event(), timers = new Map();
  let timerId = 0;
  const timing = { setTimeout(fn, timeout) { const id = ++timerId; timers.set(id, { fn, timeout }); return id; }, clearTimeout(id) { timers.delete(id); } };
  let sendFailure = false, prepareFailure = false, preparedSurface = null, prepareReply = null, commitReply = null;
  const api = { storage, runtime: { id: relay.EXTENSION_ID,
    connectNative(host) {
      assert.equal(host, relay.HOST_NAME);
      const port = { onMessage: new Event(), onDisconnect: new Event(), sent: [],
        postMessage(value) { this.sent.push(clone(value)); }, disconnect() { this.onDisconnect.emit(); } };
      ports.push(port); return port;
    } }, tabs: { onUpdated: updates,
      async create(value) { tabs.push(clone(value)); return { id: 40 + tabs.length, status: "complete" }; },
      async get(id) { return { id, status: "complete" }; },
      async sendMessage(id, value, options) { calls.push({ id, value: clone(value), options: options === undefined ? undefined : clone(options) });
        if (value.type === "relay.content.readiness") return pageReadyFor(value.readiness);
        if (value.type === "relay.content.prepare") {
          if (prepareReply) return clone(prepareReply);
          if (prepareFailure) { prepareFailure = false; throw new relay.RelayError("login_required", "隔离页面未登录，本次未发送。"); }
          const response = preparedFor(value.prepare);
          if (preparedSurface !== null) response.observation.surface = preparedSurface;
          return response;
        }
        if (commitReply) return clone(commitReply);
        if (sendFailure) throw new Error("fixture click outcome unknown");
        return { committed: true };
      } } };
  const controller = worker.createController(api, () => browserSurface, timing);
  const status = clientReady => ({ protocol: relay.PROTOCOL, type: "status", hostName: relay.HOST_NAME, enabled: true,
    approved: true, configured: true, message: "fixture-only approved endpoint", clientReady });
  return { api, storage, ports, tabs, calls, updates, timers, timing, controller, status,
    failSend() { sendFailure = true; },
    failPrepare() { prepareFailure = true; },
    setPrepareReply(value) { prepareReply = clone(value); },
    setCommitReply(value) { commitReply = clone(value); },
    setPreparedSurface(surface) { preparedSurface = surface; },
    setOwnSurface(surface) { browserSurface = surface; },
    async enable() { await controller.popup("status"); ports.at(-1).onMessage.emit(status(false));
      await controller.popup("enable"); ports.at(-1).onMessage.emit(status(true)); }
  };
}
function runtimeFixture() {
  const f = workerFixture();
  Object.assign(f.api.runtime, { onMessage: new Event(), onConnect: new Event(), onInstalled: new Event() });
  f.api.tabs.onRemoved = new Event();
  const controller = context.ConsoleChatRelayWorker.registerRuntime(f.api, () => "edge");
  const url = `chrome-extension://${relay.EXTENSION_ID}/popup.html`;
  return { ...f, controller, url, sender: { id: relay.EXTENSION_ID, url, frameId: 0, tab: { id: 73, url } },
    route: [...f.api.runtime.onMessage.listeners][0] };
}
function controlPort(sender, name = "relay.status") {
  return { sender, name, onMessage: new Event(), onDisconnect: new Event(), posted: [], disconnected: false,
    postMessage(value) { this.posted.push(clone(value)); },
    disconnect() { this.disconnected = true; this.onDisconnect.emit(); } };
}
await test("only the fixed own popup or top-level options page can control relay settings", () => {
  const f = runtimeFixture(), accepts = context.ConsoleChatRelayWorker.ownControlPage;
  for (const sender of [{ id: relay.EXTENSION_ID, url: f.url },
    { id: relay.EXTENSION_ID, url: f.url, frameId: 0 }, f.sender,
    { ...f.sender, tab: { id: 73 } }, { ...f.sender, origin: `chrome-extension://${relay.EXTENSION_ID}` }])
    assert.equal(accepts(f.api, sender), true);
  for (const sender of [undefined, { ...f.sender, id: "foreign" }, { ...f.sender, id: undefined },
    { ...f.sender, url: "https://chatgpt.com/" }, { ...f.sender, url: "chrome-extension://foreign/popup.html" },
    { ...f.sender, url: f.url + "?action=enable" }, { ...f.sender, url: f.url + "#enable" },
    { ...f.sender, url: f.url.replace("popup.html", "content-script.js") }, { ...f.sender, frameId: 1 },
    { ...f.sender, frameId: undefined }, { ...f.sender, origin: "https://chatgpt.com" },
    { ...f.sender, tab: null }, { ...f.sender, tab: {} }, { ...f.sender, tab: { id: -1 } },
    { ...f.sender, tab: { id: 73, url: "https://chatgpt.com/" } }])
    assert.equal(accepts(f.api, sender), false);
  assert.equal(accepts({ runtime: { id: "foreign" } }, { id: "foreign", url: "chrome-extension://foreign/popup.html" }), false);
  assert.equal(f.storage.writes.length, 0); assert.equal(f.ports.length, 0);
});
await test("runtime settings route accepts own toolbar/options inspect and rejects foreign enable", async () => {
  const f = runtimeFixture(), replies = [];
  for (const sender of [{ id: relay.EXTENSION_ID, url: f.url }, f.sender]) {
    assert.equal(f.route({ type: "relay.popup", action: "status" }, sender, value => replies.push(clone(value))), true);
    await f.controller.idle();
  }
  assert.equal(replies.length, 2); assert.equal(f.ports.length, 1);
  f.ports[0].onMessage.emit(f.status(false));
  for (const sender of [{ ...f.sender, id: "foreign" }, { ...f.sender, frameId: 2 },
    { ...f.sender, url: "https://chatgpt.com/" }, { ...f.sender, url: f.url + "?enable" }])
    assert.equal(f.route({ type: "relay.popup", action: "enable" }, sender, () => assert.fail("foreign page replied")), false);
  await f.controller.idle();
  assert.equal(f.controller.state().enabled, false); assert.equal(f.storage.writes.length, 0);
  assert.equal(f.ports[0].sent.some(value => value.type === "ready"), false); assert.equal(f.tabs.length, 0);
});
await test("install/update opens one own setup tab per event without native ready, Enable or Chat", async () => {
  const f = runtimeFixture();
  for (const reason of ["install", "update", "browser_update", "chrome_update", "shared_module_update", undefined])
    f.api.runtime.onInstalled.emit({ reason });
  await f.controller.idle();
  assert.deepEqual(f.tabs, [{ url: f.url, active: true }, { url: f.url, active: true }]);
  assert.equal(f.controller.state().enabled, false); assert.equal(f.ports.length, 0);
  assert.equal(f.calls.length, 0); assert.equal(f.storage.writes.length, 0);
});
await test("setup tab callback failure consumes lastError, stays harmless and never retries", async () => {
  const f = runtimeFixture(); let errorReads = 0;
  Object.defineProperty(f.api.runtime, "lastError", { get() { errorReads++; return { message: "fixture private path" }; } });
  f.api.tabs.create = (value, callback) => { f.tabs.push(clone(value)); callback(); };
  f.api.runtime.onInstalled.emit({ reason: "update" });
  await f.controller.idle();
  assert.equal(errorReads, 1); assert.equal(f.tabs.length, 1);
  assert.match(f.controller.view().message, /接通页未能自动打开/);
  assert.equal(f.controller.view().message.includes("fixture private path"), false);
  assert.equal(f.controller.state().enabled, false); assert.equal(f.storage.writes.length, 0); assert.equal(f.ports.length, 0);
});
await test("setup tab thrown/rejected creation never escapes or triggers an automatic retry", async () => {
  for (const create of [() => { throw new Error("fixture create failed"); }, () => Promise.reject(new Error("fixture create failed"))]) {
    const f = runtimeFixture(); let creates = 0;
    f.api.tabs.create = () => { creates++; return create(); };
    f.api.runtime.onInstalled.emit({ reason: "install" });
    await f.controller.idle(); await Promise.resolve();
    assert.equal(creates, 1); assert.match(f.controller.view().message, /接通页未能自动打开/);
    assert.equal(f.controller.state().enabled, false); assert.equal(f.ports.length, 0); assert.equal(f.calls.length, 0);
  }
});
await test("own status port receives actual native readiness events without polling or enable commands", async () => {
  const f = runtimeFixture(), page = controlPort(f.sender);
  f.api.runtime.onConnect.emit(page);
  await f.controller.popup("status");
  f.ports[0].onMessage.emit(f.status(false));
  assert.equal(page.posted.at(-1).value.approved, true);
  assert.equal(page.posted.at(-1).value.enabled, false); assert.equal(page.posted.at(-1).value.clientReady, false);
  page.onMessage.emit({ type: "relay.popup", action: "enable" });
  assert.equal(f.controller.state().enabled, false); assert.equal(f.storage.writes.length, 0);
  await f.controller.popup("enable");
  assert.equal(page.posted.at(-1).value.connected, true); assert.equal(page.posted.at(-1).value.clientReady, false);
  f.ports[0].onMessage.emit(f.status(true));
  assert.equal(page.posted.at(-1).value.clientReady, true);
  f.ports[0].onMessage.emit({ ...f.status(true), unexpected: true });
  assert.equal(page.posted.at(-1).value.clientReady, false); assert.equal(page.posted.at(-1).value.approved, false);
  await assert.rejects(f.controller.popup("enable"), error => error.code === "approval_required");
  const before = page.posted.length; page.disconnect();
  f.ports[0].onMessage.emit(f.status(true));
  assert.equal(page.posted.length, before); assert.equal(f.tabs.length, 0); assert.equal(f.calls.length, 0);
});
await test("foreign/frame/other-url status ports disconnect without observing or changing relay state", async () => {
  const f = runtimeFixture();
  for (const [sender, name] of [[{ ...f.sender, id: "foreign" }, "relay.status"],
    [{ ...f.sender, frameId: 1 }, "relay.status"], [{ ...f.sender, url: "https://chatgpt.com/" }, "relay.status"],
    [f.sender, "relay.enable"]]) {
    const port = controlPort(sender, name); f.api.runtime.onConnect.emit(port);
    assert.equal(port.disconnected, true); assert.equal(port.posted.length, 0);
  }
  await f.controller.idle(); assert.equal(f.storage.writes.length, 0); assert.equal(f.ports.length, 0);
});
await test("setup page shows its manifest version and asynchronous ready ack without stale reply or extra requests", async () => {
  const ids = ["status-label", "status-detail", "status-dot", "profile", "attempt", "enable", "disable", "approval", "refresh", "error", "extension-version"];
  const elements = Object.fromEntries(ids.map(id => [id, { textContent: "", disabled: false, hidden: true, dataset: {}, addEventListener() {} }]));
  const port = controlPort({}), requests = []; let respond;
  const popup = vm.createContext({ chrome: { runtime: { getManifest: () => ({ version: "0.1.1" }),
    connect: options => { assert.equal(options.name, "relay.status"); return port; },
    sendMessage: value => { requests.push(clone(value)); return new Promise(resolve => { respond = resolve; }); } } },
    document: { getElementById: id => elements[id] } });
  const initialAction = vm.runInContext(await readFile(new URL("popup.js", directory), "utf8"), popup);
  assert.equal(typeof initialAction?.then, "function");
  assert.equal(elements["extension-version"].textContent, "扩展版本 0.1.1");
  const push = value => port.onMessage.emit({ type: "relay.status", value });
  push({ enabled: false, connected: true, approved: true, configured: true, clientReady: false, message: "approved_browser_contract" });
  assert.equal(elements.enable.disabled, true);
  respond({ enabled: false, connected: true, approved: false, configured: false, clientReady: false });
  await initialAction;
  assert.equal(elements.enable.disabled, false);
  push({ enabled: true, connected: true, approved: true, configured: true, clientReady: false });
  assert.equal(elements["status-label"].textContent, "已启用，等待本机确认");
  assert.equal(elements["status-dot"].dataset.state, "");
  push({ enabled: true, connected: true, approved: true, configured: true, clientReady: true });
  assert.equal(elements["status-label"].textContent, "已接通"); assert.equal(elements["status-dot"].dataset.state, "ready");
  port.disconnect(); assert.equal(elements["status-dot"].dataset.state, "");
  assert.deepEqual(requests, [{ type: "relay.popup", action: "status" }]);
});
await test("default-disabled worker performs no native connect or queue read", async () => {
  const fixture = workerFixture(); await fixture.controller.start();
  assert.equal(fixture.ports.length, 0); assert.equal(fixture.tabs.length, 0);
  assert.equal(fixture.controller.view().enabled, false);
});
await test("browser identity derives from its own brands/UA and rejects unknown vendors or conflicts", () => {
  const detect = context.ConsoleChatRelayWorker.detectBrowserSurface;
  const chromeUA = "Mozilla/5.0 Chrome/140.0.0.0 Safari/537.36", edgeUA = chromeUA + " Edg/140.0.0.0";
  const brands = brand => [{ brand: "Not A(Brand", version: "8" }, { brand: "Chromium", version: "140" }, { brand, version: "140" }];
  assert.equal(detect({ userAgent: chromeUA, userAgentData: { brands: brands("Google Chrome") } }), "chrome");
  assert.equal(detect({ userAgent: edgeUA, userAgentData: { brands: brands("Microsoft Edge") } }), "edge");
  assert.equal(detect({ userAgent: chromeUA }), "chrome"); assert.equal(detect({ userAgent: edgeUA }), "edge");
  for (const value of [{}, { userAgent: "Firefox/140.0" }, { userAgent: chromeUA + " OPR/120.0" },
    { userAgent: chromeUA, userAgentData: { brands: brands("Brave") } },
    { userAgent: chromeUA, userAgentData: { brands: [{ brand: "Chromium" }] } },
    { userAgent: chromeUA, userAgentData: { brands: brands("Microsoft Edge") } },
    { userAgent: edgeUA, userAgentData: { brands: brands("Google Chrome") } },
    { userAgent: edgeUA, userAgentData: { brands: [{ brand: "Google Chrome" }, { brand: "Microsoft Edge" }] } }])
    assert.equal(detect(value), null);
});
await test("unknown browser identity prevents native hello; mismatched native surface never opens a page", async () => {
  const unknown = workerFixture({}, null);
  await assert.rejects(unknown.controller.popup("status"), error => error.code === "browser_identity_unverified");
  assert.equal(unknown.ports.length, 0);
  for (const surface of ["chrome", "edge"]) {
    const f = workerFixture({}, surface); await f.enable();
    const value = clone(prepare); value.domContract.surface = surface === "edge" ? "chrome" : "edge";
    await f.controller.native(value);
    assert.equal(f.ports[0].sent.at(-1).type, "blocked");
    assert.equal(f.ports[0].sent.at(-1).code, "browser_surface_mismatch");
    assert.equal(f.tabs.length, 0); assert.equal(f.calls.length, 0);
  }
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
await test("readiness has no prompt or send permission and requires the exact frozen identity/observation", () => {
  const request = readinessFor(); relay.validateReadiness(request);
  assert.deepEqual(Object.keys(request).sort(), ["attemptId", "dispatchId", "domContract", "protocol", "type"].sort());
  for (const patch of [{ prompt }, { promptSha256: prepare.promptSha256 }, { requestedProfile: "fast" }, { claimToken: "private" }])
    rejected(() => relay.validateReadiness({ ...request, ...patch }), "invalid_schema");
  const reply = pageReadyFor(request); relay.validatePageReady(reply, request);
  for (const patch of [{ dispatchId: "a".repeat(32) }, { attemptId: "a2a45678-1234-4567-89ab-1234567890ab" }])
    rejected(() => relay.validatePageReady({ ...reply, ...patch }, request), "readiness_identity_mismatch");
  for (const patch of [{ surface: "edge" }, { observationSha256: "b".repeat(64) }])
    rejected(() => relay.validatePageReady({ ...reply, observation: { ...reply.observation, ...patch } }, request), "readiness_identity_mismatch");
});
await test("loading owned tab waits for actual readonly DOM receipt then prepares exactly once without Send", async () => {
  const f = workerFixture(); let release, reached;
  const entered = new Promise(resolve => { reached = resolve; });
  f.api.tabs.get = async id => ({ id, status: "loading" });
  const send = f.api.tabs.sendMessage.bind(f.api.tabs);
  f.api.tabs.sendMessage = (id, value, options) => value.type === "relay.content.readiness"
    ? (f.calls.push({ id, value: clone(value), options: clone(options) }), new Promise(resolve => { release = resolve; reached(); })) : send(id, value, options);
  await f.enable(); const pending = f.controller.native(prepare); await entered;
  assert.equal(f.controller.state().active.phase, "preparing"); assert.equal(f.calls.length, 1);
  assert.deepEqual(f.calls[0].options, { frameId: 0 }); assert.equal("prompt" in f.calls[0].value.readiness, false);
  assert.equal([...f.timers.values()][0].timeout, 60000);
  f.updates.emit(999, { status: "complete" }); f.updates.emit(41, { status: "complete" });
  assert.equal(f.calls.length, 1);
  release(pageReadyFor(prepare)); await pending;
  assert.equal(f.controller.state().active.phase, "prepared"); assert.equal(f.timers.size, 0); assert.equal(f.updates.listeners.size, 0);
  assert.equal(f.calls.filter(call => call.value.type === "relay.content.prepare").length, 1);
  assert.equal(f.calls.filter(call => call.value.type === "relay.content.commit").length, 0);
  assert.equal(f.ports[0].sent.some(value => value.type === "sending"), false);
});
await test("event-first available handshake covers receiver-install race and rejects foreign tab/frame/source", async () => {
  const f = workerFixture(); let rejectAbsent, reached;
  const entered = new Promise(resolve => { reached = resolve; });
  f.api.tabs.get = async id => ({ id, status: "loading" });
  const send = f.api.tabs.sendMessage.bind(f.api.tabs); let probes = 0;
  f.api.tabs.sendMessage = (id, value, options) => {
    if (value.type === "relay.content.readiness" && ++probes === 1) {
      f.calls.push({ id, value: clone(value), options: clone(options) });
      return new Promise((_, reject) => { rejectAbsent = reject; reached(); });
    }
    return send(id, value, options);
  };
  await f.enable(); const pending = f.controller.native(prepare); await entered;
  const notification = { protocol: relay.PROTOCOL, type: "contentAvailable" };
  const sender = { id: relay.EXTENSION_ID, tab: { id: 41 }, frameId: 0, url: "https://chatgpt.com/" };
  for (const patch of [{ id: "foreign" }, { frameId: 1 }, { tab: { id: 99 } }, { url: capture.evidence.conversationUrl }, { url: "https://evil.test/" }])
    rejected(() => f.controller.available(notification, { ...sender, ...patch }), "wrong_page_source");
  rejected(() => f.controller.available({ ...notification, prompt }, sender), "invalid_schema");
  assert.equal(f.controller.available(notification, sender).received, true);
  rejectAbsent(new Error("Could not establish connection. Receiving end does not exist.")); await pending;
  assert.equal(probes, 2); assert.equal(f.calls.filter(call => call.value.type === "relay.content.prepare").length, 1);
  assert.equal(f.calls.filter(call => call.value.type === "relay.content.commit").length, 0);
  assert.equal(f.timers.size, 0); assert.equal(f.updates.listeners.size, 0);
});
await test("readiness timeout/native cancellation cannot resurrect an unsent attempt on a late ready reply", async () => {
  for (const trigger of ["timeout", "not_ready", "retired", "blocked", "disconnect"]) {
    const f = workerFixture(); let release, reached;
    const entered = new Promise(resolve => { reached = resolve; });
    const send = f.api.tabs.sendMessage.bind(f.api.tabs);
    f.api.tabs.sendMessage = (id, value, options) => value.type === "relay.content.readiness"
      ? (f.calls.push({ id, value: clone(value), options: clone(options) }), new Promise(resolve => { release = resolve; reached(); })) : send(id, value, options);
    await f.enable(); const pending = f.controller.native(prepare); await entered;
    let terminal;
    if (trigger === "timeout") [...f.timers.values()][0].fn();
    if (trigger === "not_ready") f.ports[0].onMessage.emit(f.status(false));
    if (trigger === "retired") terminal = f.controller.native(relay.envelope("retired", prepare, { reason: "original_dispatch_failed" }));
    if (trigger === "blocked") terminal = f.controller.native(relay.envelope("blocked", prepare, { code: "original_failed", message: "原请求已停止" })).catch(() => {});
    if (trigger === "disconnect") f.ports[0].disconnect();
    await pending; if (terminal) await terminal; await f.controller.idle();
    assert.equal(f.controller.state().active, null);
    assert.ok(["failed", "retired"].includes(f.controller.state().attempts[dispatchId].phase));
    release(pageReadyFor(prepare)); await new Promise(resolve => setImmediate(resolve));
    f.updates.emit(41, { status: "complete" });
    assert.equal(f.calls.filter(call => call.value.type === "relay.content.prepare").length, 0);
    assert.equal(f.calls.filter(call => call.value.type === "relay.content.commit").length, 0);
    assert.equal(f.ports[0].sent.some(value => value.type === "prepared"), false);
    assert.equal(f.timers.size, 0); assert.equal(f.updates.listeners.size, 0); assert.equal(f.tabs.length, 1);
    await f.controller.native(prepare); assert.equal(f.tabs.length, 1);
  }
});
await test("wrong readiness receipt or inaccurate tab identity fails closed before the original prepare", async () => {
  for (const invalid of ["tab", "identity", "contract", "profile"]) {
    const f = workerFixture();
    if (invalid === "tab") f.api.tabs.get = async () => ({ id: 999, status: "complete" });
    else {
      const send = f.api.tabs.sendMessage.bind(f.api.tabs);
      f.api.tabs.sendMessage = (id, value, options) => {
        if (value.type !== "relay.content.readiness") return send(id, value, options);
        f.calls.push({ id, value: clone(value), options: clone(options) });
        const response = pageReadyFor(prepare);
        if (invalid === "identity") response.attemptId = "a2a45678-1234-4567-89ab-1234567890ab";
        if (invalid === "contract") response.observation.observationSha256 = "c".repeat(64);
        if (invalid === "profile") response.observation.modelControlPresent = false;
        return Promise.resolve(response);
      };
    }
    await f.enable(); await f.controller.native(prepare);
    assert.equal(f.controller.state().active, null); assert.equal(f.controller.state().attempts[dispatchId].phase, "failed");
    assert.equal(f.calls.filter(call => call.value.type === "relay.content.prepare").length, 0);
    assert.equal(f.calls.filter(call => call.value.type === "relay.content.commit").length, 0);
    assert.equal(f.timers.size, 0); assert.equal(f.updates.listeners.size, 0);
  }
});
await test("closing only the owned preparing tab cancels readiness immediately and late pageReady cannot prepare", async () => {
  const f = runtimeFixture(), value = clone(prepare); value.domContract.surface = "edge";
  let release, reached; const send = f.api.tabs.sendMessage.bind(f.api.tabs);
  const entered = new Promise(resolve => { reached = resolve; });
  f.api.tabs.sendMessage = (id, message, options) => message.type === "relay.content.readiness"
    ? (f.calls.push({ id, value: clone(message), options: clone(options) }), new Promise(resolve => { release = resolve; reached(); })) : send(id, message, options);
  await f.controller.popup("status"); f.ports[0].onMessage.emit(f.status(false));
  await f.controller.popup("enable"); f.ports[0].onMessage.emit(f.status(true));
  const pending = f.controller.native(value); await entered;
  f.api.tabs.onRemoved.emit(999); assert.equal(f.controller.state().active.phase, "preparing");
  f.api.tabs.onRemoved.emit(41); await pending; await f.controller.idle();
  assert.equal(f.controller.state().active, null); assert.equal(f.controller.state().attempts[dispatchId].phase, "failed");
  assert.equal(f.ports[0].sent.filter(message => message.type === "blocked").length, 1);
  assert.equal(f.ports[0].sent.at(-1).code, "owned_tab_closed");
  release(pageReadyFor(value)); await new Promise(resolve => setImmediate(resolve));
  assert.equal(f.calls.filter(call => call.value.type === "relay.content.prepare").length, 0);
  assert.equal(f.calls.filter(call => call.value.type === "relay.content.commit").length, 0);
  assert.equal(f.updates.listeners.size, 0);
});
await test("cancel during creation or preparation persistence remains final after readiness recovers", async () => {
  for (const boundary of ["initial_save", "create", "tab_save", "prepared_save"]) {
    for (const trigger of ["status_recovers", "retired"]) {
      const f = workerFixture(); let release, reached, paused = false;
      const entered = new Promise(resolve => { reached = resolve; }), gate = new Promise(resolve => { release = resolve; });
      await f.enable();
      if (boundary === "create") {
        const create = f.api.tabs.create.bind(f.api.tabs);
        f.api.tabs.create = async value => { const tab = await create(value); reached(); await gate; return tab; };
      } else {
        const persist = f.storage.local.set.bind(f.storage.local);
        f.storage.local.set = async value => {
          const active = value.consoleChatRelayV1?.active;
          const matches = boundary === "initial_save" ? active?.phase === "preparing" && active.tabId === null
            : boundary === "tab_save" ? active?.phase === "preparing" && Number.isInteger(active.tabId)
            : active?.phase === "prepared";
          if (!paused && matches) { paused = true; reached(); await gate; }
          return persist(value);
        };
      }
      const pending = f.controller.native(prepare); await entered; let terminal;
      if (trigger === "retired") terminal = f.controller.native(relay.envelope("retired", prepare, { reason: "original_dispatch_failed" }));
      else { f.ports[0].onMessage.emit(f.status(false)); f.ports[0].onMessage.emit(f.status(true)); }
      release(); await pending; if (terminal) await terminal; await f.controller.idle();
      assert.equal(f.controller.state().active, null);
      assert.equal(f.storage.data.consoleChatRelayV1.attempts[dispatchId].phase, trigger === "retired" ? "retired" : "failed");
      assert.equal(f.ports[0].sent.some(value => value.type === "prepared"), false);
      assert.equal(f.calls.filter(call => call.value.type === "relay.content.prepare").length, boundary === "prepared_save" ? 1 : 0);
      assert.equal(f.calls.filter(call => call.value.type === "relay.content.commit").length, 0);
      assert.equal(f.timers.size, 0); assert.equal(f.updates.listeners.size, 0);
      const created = f.tabs.length; await f.controller.native(prepare); assert.equal(f.tabs.length, created);
    }
  }
});
await test("cancel after readonly ready settles but before prepare remains final even if native ready immediately recovers", async () => {
  const f = workerFixture(); await f.enable(); let cancelled = false;
  const clear = f.timing.clearTimeout;
  f.timing.clearTimeout = id => {
    clear(id);
    if (!cancelled) {
      cancelled = true;
      // Deliver the native loss/recovery before the await-ready continuation.
      queueMicrotask(() => { f.ports[0].onMessage.emit(f.status(false)); f.ports[0].onMessage.emit(f.status(true)); });
    }
  };
  await f.controller.native(prepare);
  assert.equal(cancelled, true); assert.equal(f.controller.state().active, null);
  assert.equal(f.storage.data.consoleChatRelayV1.attempts[dispatchId].phase, "failed");
  assert.equal(f.calls.filter(call => call.value.type === "relay.content.readiness").length, 1);
  assert.equal(f.calls.filter(call => call.value.type === "relay.content.prepare").length, 0);
  assert.equal(f.calls.filter(call => call.value.type === "relay.content.commit").length, 0);
  assert.equal(f.ports[0].sent.some(value => value.type === "prepared"), false);
});
await test("matching retirement or readiness loss during worker SHA cannot create a tab after a late valid hash", async () => {
  for (const trigger of ["status_recovers", "retired"]) {
    let reached, release;
    const entered = new Promise(resolve => { reached = resolve; }), gate = new Promise(resolve => { release = resolve; });
    const isolated = vm.createContext({ crypto: { subtle: { async digest(...args) {
      reached(); await gate; return webcrypto.subtle.digest(...args);
    } } }, TextEncoder, URL, Date, Uint8Array, Set, Error, structuredClone, setTimeout, clearTimeout, importScripts() {} });
    vm.runInContext(await readFile(new URL("lib/protocol.js", directory), "utf8"), isolated);
    vm.runInContext(await readFile(new URL("service-worker.js", directory), "utf8"), isolated);
    const f = workerFixture({}, "chrome", isolated.ConsoleChatRelayWorker); await f.enable();
    const pending = f.controller.native(prepare); await entered; let terminal;
    assert.equal(f.controller.state().active.phase, "preparing");
    if (trigger === "retired") terminal = f.controller.native(relay.envelope("retired", prepare, { reason: "original_dispatch_failed" }));
    else { f.ports[0].onMessage.emit(f.status(false)); f.ports[0].onMessage.emit(f.status(true)); }
    release(); await pending; if (terminal) await terminal; await f.controller.idle();
    assert.equal(f.controller.state().active, null);
    assert.equal(f.storage.data.consoleChatRelayV1.attempts[dispatchId].phase, trigger === "retired" ? "retired" : "failed");
    assert.equal(f.tabs.length, 0); assert.equal(f.calls.length, 0);
    assert.equal(f.ports[0].sent.some(value => value.type === "prepared"), false);
  }
});
await test("worker accepts matching Chrome/Edge prepared surfaces and never forwards a different browser", async () => {
  for (const surface of ["chrome", "edge"]) {
    const value = clone(prepare); value.domContract.surface = surface;
    const matching = workerFixture({}, surface); await matching.enable(); await matching.controller.native(value);
    assert.equal(matching.controller.state().active.phase, "prepared");
    assert.equal(matching.ports[0].sent.at(-1).observation.surface, surface);
    const mismatch = workerFixture({}, surface); await mismatch.enable();
    mismatch.setPreparedSurface(surface === "edge" ? "chrome" : "edge");
    await mismatch.controller.native(value);
    assert.equal(mismatch.ports[0].sent.at(-1).type, "blocked");
    assert.equal(mismatch.ports[0].sent.at(-1).code, "prepare_identity_mismatch");
    assert.equal(mismatch.controller.state().active, null);
    assert.equal(mismatch.calls.filter(call => call.value.type === "relay.content.commit").length, 0);
  }
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
await test("typed content preparation failure preserves its actual profile error without schema masking or Send", async () => {
  const f = workerFixture(); await f.enable();
  f.setPrepareReply(relay.envelope("blocked", prepare, { code: "profile_changed", message: "实际为 Pro/medium，尚未点击 Send。" }));
  await f.controller.native(prepare);
  assert.equal(f.ports[0].sent.at(-1).type, "blocked");
  assert.equal(f.ports[0].sent.at(-1).code, "profile_changed");
  assert.equal(f.controller.state().active, null);
  assert.equal(f.controller.state().attempts[dispatchId].phase, "failed");
  assert.equal(f.calls.filter(call => call.value.type === "relay.content.commit").length, 0);
});
await test("typed commit failure records the actual click boundary once and keeps unknown intent without resending", async () => {
  for (const clickStarted of [false, true]) {
    const f = workerFixture(); await f.enable(); await f.controller.native(prepare);
    f.setCommitReply(relay.envelope("uncertain", prepare, { code: "send_not_available", message: "真实发送控件未就绪。", clickStarted }));
    await f.controller.native(relay.envelope("commitSend", prepare));
    const failures = f.ports[0].sent.filter(value => value.type === "uncertain");
    assert.equal(failures.length, 1); relay.validateFailure(failures[0]);
    assert.equal(failures[0].code, "send_not_available");
    assert.equal("clickStarted" in failures[0], false);
    assert.match(failures[0].message, clickStarted ? /已开始点击 Send/ : /尚未点击 Send/);
    assert.equal(f.controller.state().active.phase, "needs_review");
    await f.controller.native(relay.envelope("commitSend", prepare));
    assert.equal(f.calls.filter(call => call.value.type === "relay.content.commit").length, 1);
  }
});
await test("native failed retirement releases only its matching active attempt and retains all original tombstone fields", async () => {
  const f = workerFixture(); await f.enable(); await f.controller.native(prepare); f.failSend();
  await f.controller.native(relay.envelope("commitSend", prepare));
  const before = clone(f.controller.state().attempts[dispatchId]);
  const retired = relay.envelope("retired", prepare, { reason: "original_dispatch_failed" });
  for (const wrong of [{ ...retired, dispatchId: "a".repeat(32) }, { ...retired, attemptId: "a2a45678-1234-4567-89ab-1234567890ab" }, { ...retired, reason: "assumed_unsent" }, { ...retired, sent: false }])
    await assert.rejects(f.controller.native(wrong));
  assert.equal(f.controller.state().active.phase, "needs_review");
  const sender = { id: relay.EXTENSION_ID, tab: { id: 41 }, frameId: 0, url: "https://chatgpt.com/" };
  await assert.rejects(f.controller.page(retired, sender), error => error.code === "page_not_committed");
  await f.controller.native(retired); assert.equal(f.controller.state().active, null);
  const after = f.controller.state().attempts[dispatchId];
  assert.equal(after.attemptId, before.attemptId); assert.equal(after.promptSha256, before.promptSha256);
  assert.equal(after.previousPhase, before.phase); assert.equal(after.retirement, "original_dispatch_failed");
  assert.equal((await f.controller.native(retired)).duplicate, true);
  await f.controller.native(prepare);
  assert.equal(f.tabs.length, 1); assert.equal(f.calls.filter(call => call.value.type === "relay.content.commit").length, 1);
  const restart = workerFixture(f.storage.data); await restart.controller.start();
  restart.ports[0].onMessage.emit(restart.status(true)); await restart.controller.native(prepare);
  assert.equal(restart.tabs.length, 0); assert.equal(restart.calls.length, 0);
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
  assert.equal(restart.tabs.length, 0);
  assert.equal(restart.calls.filter(call => ["relay.content.prepare", "relay.content.commit"].includes(call.value.type)).length, 0);
  assert.equal(restart.calls.filter(call => call.value.type === "relay.content.cancel").length, 1);
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
  get innerText() { return this.textContent === "" && this.emptyInnerText !== undefined ? this.emptyInnerText : this.textContent; }
  getAttribute(key) { return this.attributes[key] ?? null; }
  getClientRects() { return [{}]; }
  querySelectorAll(selector) { return this.children.get(selector) || []; }
  focus() {}
  dispatchEvent() { return true; }
}
function contentFixture({ promptText = prompt, completed = false, stop = false, extraUser = false, clickThrows = false, draft = "", answerShell = false,
  emptyInnerText, profileText = "Thinking effortInstant", completionText = "Response complete" } = {}) {
  const storage = storageFixture(), messages = [], emitted = [], availableNotifications = [], queries = [], timers = new Map(), location = { href: "https://chatgpt.com/" };
  const composer = new Node(draft, { role: "textbox", contenteditable: "true" });
  composer.emptyInnerText = emptyInnerText;
  const model = new Node(profileText, { "data-selected-reasoning-effort": "none", "id": "profile-original", "aria-haspopup": "menu", "aria-expanded": "false" }); model.tagName = "BUTTON";
  const chat = new Node("Chat", { "aria-pressed": "true" }), login = new Node("Signed in"), complete = new Node(completionText), stopNode = new Node("Stop");
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
    const answer = message(answerId, "fallback-turn-0:1:assistant", "真实隔离答案", "assistant");
    if (answerShell) answer.children.delete(".answer-body");
    messages.push(answer);
    if (completed) items.set("#complete", [complete]); if (stop) items.set("#stop", [stopNode]);
    if (clickThrows) throw new Error("fixture click result unknown");
  };
  items.set("#send", [send]);
  class Observer { constructor(callback) { mutation = callback; } observe() {} disconnect() { mutation = null; } }
  const env = { chrome: { storage, runtime: { async sendMessage(value) {
    (value.type === "contentAvailable" ? availableNotifications : emitted).push(clone(value)); return { received: true };
  } } },
    document: { documentElement: {}, querySelectorAll(selector) {
      assert.equal(typeof selector, "string"); assert.ok(selector); queries.push(selector); return items.get(selector) || [];
    } }, location, MutationObserver: Observer,
    InputEvent: class { constructor(type, detail) { this.type = type; this.detail = detail; } },
    KeyboardEvent: class { constructor(type, detail) { this.type = type; Object.assign(this, detail); } }, now: () => Date.parse("2026-10-05T12:00:00.000Z"),
    setTimeout(fn, timeout) { const id = nextTimer++; timers.set(id, { fn, timeout }); return id; }, clearTimeout(id) { timers.delete(id); } };
  return { env, items, storage, emitted, availableNotifications, queries, composer, model, messages, timers, send, controller: context.ConsoleChatRelayContent.createController(env),
    clicks: () => clicks, mutateNow() { mutation?.(); },
    async mutation() { mutation?.(); await this.controller.idle(); await this.controller.idle(); } };
}
async function contentListenerFixture(f, crypto = webcrypto) {
  f.env.chrome.runtime.onMessage = new Event();
  const isolated = vm.createContext({ ...f.env, crypto, TextEncoder, URL, Date, Uint8Array, Set, Error,
    structuredClone, addEventListener() {} });
  vm.runInContext(await readFile(new URL("lib/protocol.js", directory), "utf8"), isolated);
  vm.runInContext(await readFile(new URL("content-script.js", directory), "utf8"), isolated);
  const route = [...f.env.chrome.runtime.onMessage.listeners][0];
  assert.equal(typeof route, "function");
  return { route, call(value) { return new Promise(resolve => { route(value, { id: relay.EXTENSION_ID }, resolve); }); } };
}
await test("content document_idle announces only receiver availability; missing controls resolve on DOM event without preparing or typing", async () => {
  const f = contentFixture({ profileText: "思考强度Instant" }), composer = f.items.get("#composer");
  f.items.set("#composer", []); const listener = await contentListenerFixture(f);
  assert.deepEqual(f.availableNotifications, [{ protocol: relay.PROTOCOL, type: "contentAvailable" }]);
  const request = readinessFor(), pending = listener.call({ type: "relay.content.readiness", readiness: request });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(f.timers.size, 1); assert.equal([...f.timers.values()][0].timeout, 60000);
  assert.equal(f.storage.writes.length, 0); assert.equal(f.composer.textContent, ""); assert.equal(f.clicks(), 0); assert.equal(f.emitted.length, 0);
  f.items.set("#composer", composer); f.mutateNow(); const response = await pending; relay.validatePageReady(response, request);
  assert.equal(response.observation.modelControlPresent, true); assert.equal("observedProfile" in response.observation, false); assert.equal(f.timers.size, 0);
  assert.equal(f.clicks(), 0); assert.equal(f.storage.writes.length, 0); assert.equal(f.emitted.length, 0);
  // Readiness confers no commit authority; the real prepare is still required.
  const rejectedCommit = await listener.call({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) });
  assert.equal(rejectedCommit.code, "commit_not_prepared"); assert.equal(rejectedCommit.clickStarted, false);
  relay.validatePrepared(await listener.call({ type: "relay.content.prepare", prepare }));
  assert.equal(f.clicks(), 0); assert.equal(f.composer.textContent, "");
});
await test("readonly DOM readiness rejects a late draft, prior conversation or duplicate control before prompt delivery", async () => {
  for (const [change, code] of [
    [f => { f.composer.textContent = "用户原草稿"; }, "composer_changed"],
    [f => { f.env.location.href = capture.evidence.conversationUrl; }, "not_fresh_chat"],
    [f => { f.items.set("#profile", [f.model, new Node("Instant")]); }, "dom_contract_changed"]
  ]) {
    const f = contentFixture(); change(f);
    await assert.rejects(f.controller.receive({ type: "relay.content.readiness", readiness: readinessFor() }), error => error.code === code);
    assert.equal(f.clicks(), 0); assert.equal(f.storage.writes.length, 0); assert.equal(f.emitted.length, 0); assert.equal(f.timers.size, 0);
    if (code === "composer_changed") assert.equal(f.composer.textContent, "用户原草稿");
  }
});
await test("content readiness timeout/cancel/pagehide removes observer and cannot restore prepare when controls arrive late", async () => {
  for (const trigger of ["timeout", "cancel", "pagehide"]) {
    const f = contentFixture(), composer = f.items.get("#composer"); f.items.set("#composer", []);
    const pending = f.controller.receive({ type: "relay.content.readiness", readiness: readinessFor() });
    const rejected = assert.rejects(pending, error => error.code === (trigger === "timeout" ? "page_ready_timeout" : "readiness_cancelled"));
    await new Promise(resolve => setImmediate(resolve));
    if (trigger === "timeout") [...f.timers.values()][0].fn();
    if (trigger === "cancel") {
      assert.throws(() => f.controller.cancel(relay.envelope("cancel", { ...prepare, dispatchId: "a".repeat(32) })), error => error.code === "cancel_identity_mismatch");
      f.controller.cancel(relay.envelope("cancel", prepare));
    }
    if (trigger === "pagehide") f.controller.stop();
    await rejected; f.items.set("#composer", composer); f.mutateNow();
    await assert.rejects(f.controller.receive({ type: "relay.content.prepare", prepare }), error => error.code === "readiness_identity_mismatch");
    assert.equal(f.clicks(), 0); assert.equal(f.composer.textContent, ""); assert.equal(f.storage.writes.length, 0); assert.equal(f.timers.size, 0);
  }
});
await test("ready content cannot bind a different prepare identity or altered frozen selector contract", async () => {
  for (const change of [value => { value.attemptId = "a2a45678-1234-4567-89ab-1234567890ab"; },
    value => { value.domContract.selectors.composer = "#other"; }]) {
    const f = contentFixture(); relay.validatePageReady(await f.controller.receive({ type: "relay.content.readiness", readiness: readinessFor() }), readinessFor());
    const wrong = clone(prepare); change(wrong);
    await assert.rejects(f.controller.receive({ type: "relay.content.prepare", prepare: wrong }), error => error.code === "readiness_identity_mismatch");
    assert.equal(f.storage.writes.length, 0); assert.equal(f.composer.textContent, ""); assert.equal(f.clicks(), 0);
  }
});
await test("content cancellation during prepare SHA/storage cannot recreate a prepared identity or authorize Send", async () => {
  for (const boundary of ["sha", "storage"]) {
    const f = contentFixture(); let reached, release;
    const entered = new Promise(resolve => { reached = resolve; }), gate = new Promise(resolve => { release = resolve; });
    const crypto = boundary === "sha" ? { subtle: { async digest(...args) {
      reached(); await gate; return webcrypto.subtle.digest(...args);
    } } } : webcrypto;
    const listener = await contentListenerFixture(f, crypto);
    relay.validatePageReady(await listener.call({ type: "relay.content.readiness", readiness: readinessFor() }), readinessFor());
    if (boundary === "storage") {
      const get = f.storage.local.get.bind(f.storage.local);
      f.storage.local.get = async key => { reached(); await gate; return get(key); };
    }
    const pending = listener.call({ type: "relay.content.prepare", prepare }); await entered;
    const cancel = await listener.call({ type: "relay.content.cancel", cancel: relay.envelope("cancel", prepare) });
    assert.equal(cancel.cancelled, true); release();
    const response = await pending; relay.validateFailure(response);
    assert.equal(response.type, "blocked"); assert.equal(response.code, "prepare_cancelled");
    const commit = await listener.call({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) });
    assert.equal(commit.code, "commit_not_prepared"); assert.equal(commit.clickStarted, false);
    const repeat = await listener.call({ type: "relay.content.prepare", prepare }); assert.equal(repeat.code, "page_already_prepared");
    assert.equal(f.composer.textContent, ""); assert.equal(f.clicks(), 0); assert.equal(f.storage.writes.length, 0); assert.equal(f.emitted.length, 0);
  }
});
await test("input waits for a DOM-enabled Send event and commits exactly once with its durable original intent", async () => {
  const f = contentFixture({ completed: true }); let inputs = 0;
  f.composer.dispatchEvent = () => { inputs++; return true; };
  await f.controller.receive({ type: "relay.content.prepare", prepare }); f.send.disabled = true;
  const pending = f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(f.clicks(), 0); assert.equal(inputs, 1); assert.equal(f.timers.size, 1);
  assert.equal(f.composer.textContent, prompt); assert.equal(f.controller.clickStarted(), false);
  f.send.disabled = false; f.mutateNow(); assert.equal((await pending).committed, true); await f.controller.idle();
  assert.equal(f.clicks(), 1); assert.equal(inputs, 1); assert.equal(f.controller.clickStarted(), true);
  assert.equal(f.emitted.filter(value => value.type === "capture").length, 1);
  await assert.rejects(f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) }));
  assert.equal(f.clicks(), 1);
});
await test("late draft, tier, URL, duplicate or wrong Send during readiness wait prevents the first physical click", async () => {
  for (const [change, code] of [
    [f => { f.composer.textContent = "late user draft"; }, "composer_changed"],
    [f => { f.model.textContent = "Pro"; }, "profile_changed"],
    [f => { f.env.location.href = capture.evidence.conversationUrl; }, "not_fresh_chat"],
    [f => { f.items.set("#send", [f.send, new Node("Other", { type: "submit" })]); }, "send_not_available"],
    [f => { f.send.attributes.type = "button"; }, "send_not_available"]
  ]) {
    const f = contentFixture(); await f.controller.receive({ type: "relay.content.prepare", prepare }); f.send.disabled = true;
    const pending = f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) });
    const rejected = assert.rejects(pending, error => error.code === code);
    await new Promise(resolve => setImmediate(resolve)); change(f); f.mutateNow(); await rejected;
    assert.equal(f.clicks(), 0); assert.equal(f.controller.clickStarted(), false); assert.equal(f.timers.size, 0);
    assert.equal(f.controller.phase(), "needs_review"); assert.equal(f.emitted.length, 0);
    if (code === "composer_changed") assert.equal(f.composer.textContent, "late user draft");
  }
});
await test("bounded readiness timeout or matching cancel retains input and never resumes when Send later becomes ready", async () => {
  for (const cancel of [false, true]) {
    const f = contentFixture(); await f.controller.receive({ type: "relay.content.prepare", prepare }); f.send.disabled = true;
    const pending = f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) });
    const rejected = assert.rejects(pending, error => error.code === (cancel ? "send_cancelled" : "send_not_available"));
    await new Promise(resolve => setImmediate(resolve));
    if (cancel) {
      assert.throws(() => f.controller.cancel(relay.envelope("cancel", { ...prepare, dispatchId: "a".repeat(32) })), error => error.code === "cancel_identity_mismatch");
      f.controller.cancel(relay.envelope("cancel", prepare));
    } else [...f.timers.values()][0].fn();
    await rejected; f.send.disabled = false; f.mutateNow(); await f.controller.idle();
    assert.equal(f.clicks(), 0); assert.equal(f.composer.textContent, prompt); assert.equal(f.timers.size, 0);
    assert.equal(f.storage.data[context.ConsoleChatRelayContent.CONTENT_PREFIX + dispatchId].phase, "send_intent");
  }
});
await test("cancel during asynchronous intent read or write cannot restore sending or type into the page", async () => {
  for (const operation of ["get", "set"]) {
    const f = contentFixture(), listener = await contentListenerFixture(f);
    relay.validatePrepared(await listener.call({ type: "relay.content.prepare", prepare }));
    let release, reached;
    const entered = new Promise(resolve => { reached = resolve; });
    const gate = new Promise(resolve => { release = resolve; });
    const original = f.env.chrome.storage.local[operation].bind(f.env.chrome.storage.local);
    f.env.chrome.storage.local[operation] = async (...args) => { reached(); await gate; return original(...args); };
    const pending = listener.call({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) });
    await entered;
    assert.equal((await listener.call({ type: "relay.content.cancel", cancel: relay.envelope("cancel", prepare) })).cancelled, true);
    release();
    const { clickStarted, ...failure } = await pending;
    relay.validateFailure(failure); assert.equal(failure.code, "send_cancelled"); assert.equal(clickStarted, false);
    assert.equal(f.composer.textContent, ""); assert.equal(f.clicks(), 0); assert.equal(f.emitted.length, 0);
    const retry = await listener.call({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) });
    assert.equal(retry.code, "commit_not_prepared"); assert.equal(retry.clickStarted, false); assert.equal(f.clicks(), 0);
    assert.equal(!!f.storage.data[context.ConsoleChatRelayContent.CONTENT_PREFIX + dispatchId], operation === "set");
  }
});
await test("actual content listener returns typed original failures and exact click boundary without a duplicate async report", async () => {
  const pro = contentFixture({ profileText: "Pro" }), proListener = await contentListenerFixture(pro);
  const blocked = await proListener.call({ type: "relay.content.prepare", prepare }); relay.validateFailure(blocked);
  assert.equal(blocked.type, "blocked"); assert.equal(blocked.code, "profile_picker_unverified");
  assert.equal(pro.clicks(), 0); assert.equal(pro.composer.textContent, ""); assert.equal(pro.emitted.length, 0);
  for (const clickThrows of [false, true]) {
    const f = contentFixture({ clickThrows }), listener = await contentListenerFixture(f);
    relay.validatePrepared(await listener.call({ type: "relay.content.prepare", prepare }));
    if (!clickThrows) f.send.disabled = true;
    const pending = listener.call({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) });
    if (!clickThrows) { await new Promise(resolve => setImmediate(resolve)); [...f.timers.values()][0].fn(); }
    const response = await pending, { clickStarted, ...failure } = response;
    relay.validateFailure(failure); assert.equal(failure.type, "uncertain"); assert.equal(clickStarted, clickThrows);
    assert.equal(f.clicks(), clickThrows ? 1 : 0); assert.equal(f.emitted.length, 0);
  }
});
await test("content prepare is readonly and cannot overwrite any existing user draft", async () => {
  const f = contentFixture({ draft: "未发送草稿" });
  await assert.rejects(f.controller.receive({ type: "relay.content.prepare", prepare }), error => error.code === "composer_changed");
  assert.equal(f.composer.textContent, "未发送草稿"); assert.equal(f.clicks(), 0); assert.equal(f.storage.writes.length, 0);
});
await test("observed Edge empty editor newline is prepared without typing and reports Edge Chinese Instant", async () => {
  const value = clone(prepare); value.domContract.surface = "edge";
  const f = contentFixture({ emptyInnerText: "\n", profileText: "思考强度Instant", completed: true });
  const response = await f.controller.receive({ type: "relay.content.prepare", prepare: value });
  relay.validatePrepared(response);
  assert.equal(response.observation.surface, "edge");
  assert.equal(response.observation.profileDom.text, "思考强度Instant");
  assert.equal(f.composer.textContent, ""); assert.equal(f.composer.innerText, "\n");
  assert.equal(f.storage.writes.length, 0); assert.equal(f.clicks(), 0);
  assert.equal((await f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", value) })).committed, true);
  await f.controller.idle();
  assert.equal(f.composer.textContent, prompt); assert.equal(f.clicks(), 1);
  assert.equal(f.emitted.filter(message => message.type === "capture").length, 1);
});
await test("current observed Edge localized Instant label with none effort prepares and retains its exact DOM text", async () => {
  const f = contentFixture({ profileText: "思考强度即时" });
  const response = await f.controller.receive({ type: "relay.content.prepare", prepare });
  relay.validatePrepared(response); assert.equal(response.observation.profileDom.text, "思考强度即时");
  assert.equal(f.composer.textContent, ""); assert.equal(f.clicks(), 0);
  f.model.attributes["data-selected-reasoning-effort"] = "medium";
  await assert.rejects(f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) }), error => error.code === "profile_changed");
  assert.equal(f.clicks(), 0);
});
await test("real spaces/newlines in textContent stay protected user drafts without trimming", async () => {
  for (const draft of [" ", "\n", "\t\n", " 未发送草稿 \n"]) {
    const f = contentFixture({ draft, profileText: "思考强度Instant" });
    await assert.rejects(f.controller.receive({ type: "relay.content.prepare", prepare }), error => error.code === "composer_changed");
    assert.equal(f.composer.textContent, draft); assert.equal(f.clicks(), 0); assert.equal(f.storage.writes.length, 0);
  }
  const f = contentFixture({ emptyInnerText: " " });
  await assert.rejects(f.controller.receive({ type: "relay.content.prepare", prepare }), error => error.code === "composer_changed");
  assert.equal(f.composer.innerText, " "); assert.equal(f.clicks(), 0);
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
await test("matching native retirement or loss of readiness cancels a blocked Send before the worker queue can advance", async () => {
  for (const trigger of ["retired", "status", "uncertain"]) {
    const worker = workerFixture(), content = contentFixture(), listener = await contentListenerFixture(content);
    content.send.disabled = true;
    worker.api.tabs.sendMessage = async (id, value) => { worker.calls.push({ id, value: clone(value) }); return listener.call(value); };
    await worker.enable(); await worker.controller.native(prepare);
    const committing = worker.controller.native(relay.envelope("commitSend", prepare));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(content.timers.size, 1); assert.equal(content.clicks(), 0);
    let terminal;
    if (trigger === "retired") {
      const retired = relay.envelope("retired", prepare, { reason: "original_dispatch_failed" });
      const invalid = worker.controller.native({ ...retired, attemptId: "a2a45678-1234-4567-89ab-1234567890ab" }).catch(() => {});
      assert.equal(content.timers.size, 1);
      terminal = worker.controller.native(retired);
      await committing; await invalid;
    } else if (trigger === "status") {
      worker.ports[0].onMessage.emit({ ...worker.status(false), approved: false });
    } else {
      terminal = worker.controller.native(relay.envelope("uncertain", prepare, { code: "fixture_stopped", message: "fixture stop" }));
    }
    await committing; if (terminal) await terminal; await worker.controller.idle();
    content.send.disabled = false; content.mutateNow();
    assert.equal(content.clicks(), 0); assert.equal(content.timers.size, 0);
    assert.equal(content.storage.data[context.ConsoleChatRelayContent.CONTENT_PREFIX + dispatchId].phase, "send_intent");
    assert.equal(worker.calls.filter(call => call.value.type === "relay.content.commit").length, 1);
    if (trigger === "retired") assert.equal(worker.controller.state().active, null);
  }
});
await test("bidirectional serial worker/content typed failure reports once and never deadlocks or retries", async () => {
  const worker = workerFixture(), content = contentFixture({ clickThrows: true }), notifications = [];
  const listener = await contentListenerFixture(content);
  content.env.chrome.runtime.sendMessage = async value => {
    notifications.push(clone(value));
    const sender = { id: relay.EXTENSION_ID, tab: { id: 41 }, frameId: 0, url: content.env.location.href };
    try { return await worker.controller.page(value, sender); }
    catch (error) { return { received: false, code: error.code || "page_rejected" }; }
  };
  worker.api.tabs.sendMessage = async (id, value) => {
    worker.calls.push({ id, value: clone(value) });
    return listener.call(value);
  };
  await worker.enable(); await worker.controller.native(prepare);
  let deadline;
  try {
    await Promise.race([worker.controller.native(relay.envelope("commitSend", prepare)),
      new Promise((_, reject) => { deadline = setTimeout(() => reject(new Error("bidirectional commit queue deadlocked")), 500); })]);
  } finally { clearTimeout(deadline); }
  await worker.controller.idle(); await content.controller.idle();
  assert.equal(content.clicks(), 1);
  assert.equal(worker.controller.state().active.phase, "needs_review");
  assert.equal(worker.storage.data.consoleChatRelayV1.attempts[dispatchId].phase, "needs_review");
  assert.equal(content.storage.data[context.ConsoleChatRelayContent.CONTENT_PREFIX + dispatchId].phase, "send_intent");
  assert.equal(notifications.filter(value => value.type === "uncertain").length, 0);
  assert.equal(worker.ports[0].sent.filter(value => value.type === "uncertain").length, 1);
  await worker.controller.native(relay.envelope("commitSend", prepare));
  assert.equal(content.clicks(), 1);
  assert.equal(worker.calls.filter(call => call.value.type === "relay.content.commit").length, 1);
});
await test("Stop prevents premature final; DOM completion event then returns one answer", async () => {
  const f = contentFixture({ completed: true, stop: true }); await f.controller.receive({ type: "relay.content.prepare", prepare });
  await f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) }); await f.controller.idle();
  assert.equal(f.emitted.filter(value => value.type === "capture").length, 0);
  f.items.set("#stop", []); await f.mutation();
  assert.equal(f.emitted.filter(value => value.type === "capture").length, 1);
  await f.mutation(); assert.equal(f.emitted.filter(value => value.type === "capture").length, 1);
});
await test("unknown Stop is never queried or reported absent; only a new explicit completion captures once", async () => {
  const value = clone(prepare); value.domContract.surface = "edge"; value.domContract.selectors.stop = null;
  const f = contentFixture({ profileText: "思考强度Instant", stop: true });
  await f.controller.receive({ type: "relay.content.prepare", prepare: value });
  await f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", value) });
  await f.controller.idle();
  assert.equal(f.emitted.filter(message => message.type === "accepted").length, 1);
  assert.equal(f.emitted.filter(message => message.type === "capture").length, 0);
  assert.equal(f.controller.phase(), "waiting"); assert.equal(f.clicks(), 1);
  await f.mutation();
  assert.equal(f.emitted.filter(message => message.type === "capture").length, 0);
  f.items.set("#stop", []);
  f.items.set("#complete", [new Node("回答已完成")]);
  await f.mutation();
  const response = f.emitted.find(message => message.type === "capture");
  assert.ok(response); relay.validateCapture(response, value);
  assert.equal(response.evidence.completion.text, "回答已完成");
  assert.equal(response.evidence.completion.observedAfterCommit, true);
  assert.equal(response.evidence.completion.stopPresent, null);
  assert.equal(response.evidence.promptText, prompt); assert.equal(response.evidence.sourceUserMessageId, sourceId);
  assert.equal(response.evidence.assistantMessageId, answerId); assert.equal(f.queries.includes("#stop"), false);
  await f.mutation();
  assert.equal(f.emitted.filter(message => message.type === "capture").length, 1); assert.equal(f.clicks(), 1);
});
await test("unknown Stop cannot use a completion already present before its unique Send", async () => {
  const value = clone(prepare); value.domContract.selectors.stop = null;
  const f = contentFixture();
  await f.controller.receive({ type: "relay.content.prepare", prepare: value });
  f.items.set("#complete", [new Node("回答已完成")]);
  await assert.rejects(f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", value) }),
    error => error.code === "not_fresh_chat");
  assert.equal(f.clicks(), 0); assert.equal(f.storage.writes.length, 0);
  assert.equal(f.emitted.filter(message => message.type === "capture").length, 0);
});
await test("unknown Stop still rejects duplicate completion markers or ambiguous final sources", async () => {
  const value = clone(prepare); value.domContract.selectors.stop = null;
  for (const mutate of [
    f => f.items.set("#complete", [new Node("回答已完成"), new Node("回答已完成")]),
    f => { f.items.set("#complete", [new Node("回答已完成")]);
      f.messages[1].children.set(".answer-body", [new Node("answer A"), new Node("answer B")]); },
    f => { f.items.set("#complete", [new Node("回答已完成")]);
      const other = new Node("other", { "data-chatgpt-search-message-ids": JSON.stringify(["a2a45678-1234-4567-89ab-1234567890ab"]),
        "data-chatgpt-search-unit-key": "fallback-turn-1:0:user" });
      other.children.set(".user-body", [new Node("other")]); f.messages.push(other); },
    f => { f.items.set("#complete", [new Node("回答已完成")]); f.model.textContent = "Pro"; }
  ]) {
    const f = contentFixture();
    await f.controller.receive({ type: "relay.content.prepare", prepare: value });
    await f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", value) });
    await f.controller.idle(); mutate(f); await f.mutation(); await f.controller.idle();
    assert.equal(f.emitted.filter(message => message.type === "capture").length, 0);
    assert.equal(f.controller.phase(), "needs_review"); assert.equal(f.clicks(), 1);
  }
});
await test("content preserves actual Chinese completion text and never translates a wrong marker into final evidence", async () => {
  const value = clone(prepare); value.domContract.surface = "edge";
  const actual = contentFixture({ completed: true, profileText: "思考强度Instant", completionText: "回答已完成" });
  await actual.controller.receive({ type: "relay.content.prepare", prepare: value });
  await actual.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", value) });
  await actual.controller.idle();
  const response = actual.emitted.find(message => message.type === "capture");
  assert.ok(response); assert.equal(response.evidence.completion.text, "回答已完成");
  relay.validateCapture(response, value);
  const wrong = contentFixture({ completed: true, completionText: "回答已完成。" });
  await wrong.controller.receive({ type: "relay.content.prepare", prepare });
  await wrong.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) });
  await wrong.controller.idle();
  assert.equal(wrong.emitted.filter(message => message.type === "capture").length, 0);
  assert.equal(wrong.controller.phase(), "waiting"); assert.equal(wrong.clicks(), 1);
});
await test("streaming assistant shell does not abort the accepted input before its body exists", async () => {
  const f = contentFixture({ answerShell: true, stop: true });
  await f.controller.receive({ type: "relay.content.prepare", prepare });
  await f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) });
  await f.controller.idle();
  assert.equal(f.controller.phase(), "waiting");
  assert.equal(f.emitted.filter(value => value.type === "accepted").length, 1);
  assert.equal(f.emitted.filter(value => value.type === "uncertain" || value.type === "capture").length, 0);
  await f.mutation();
  f.messages[1].children.set(".answer-body", [new Node("流式完成的真实隔离答案")]);
  f.items.set("#complete", [new Node("Response complete")]); f.items.set("#stop", []);
  await f.mutation();
  const actual = f.emitted.find(value => value.type === "capture");
  assert.equal(actual.evidence.answerText, "流式完成的真实隔离答案"); relay.validateCapture(actual, prepare);
  assert.equal(f.clicks(), 1); assert.equal(f.controller.phase(), "captured");
});
await test("accepted slow generation stays on mutation events and captures after two minutes without retry", async () => {
  const f = contentFixture({ stop: true });
  await f.controller.receive({ type: "relay.content.prepare", prepare });
  await f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) });
  await f.controller.idle();
  assert.equal(f.timers.size, 0); assert.equal(f.controller.phase(), "waiting");
  f.env.now = () => Date.parse("2026-10-05T12:05:00.000Z");
  await f.mutation(); assert.equal(f.emitted.filter(value => value.type === "uncertain").length, 0);
  f.items.set("#complete", [new Node("Response complete")]); f.items.set("#stop", []);
  await f.mutation();
  const actual = f.emitted.find(value => value.type === "capture");
  assert.equal(actual.evidence.observedAt, "2026-10-05T12:05:00.000Z");
  assert.equal(f.emitted.filter(value => value.type === "capture").length, 1); assert.equal(f.clicks(), 1);
});
await test("final completion still rejects an ambiguous assistant body after streaming", async () => {
  const f = contentFixture({ answerShell: true });
  await f.controller.receive({ type: "relay.content.prepare", prepare });
  await f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) });
  await f.controller.idle();
  f.messages[1].children.set(".answer-body", [new Node("answer A"), new Node("answer B")]);
  f.items.set("#complete", [new Node("Response complete")]); await f.mutation(); await f.controller.idle();
  assert.equal(f.controller.phase(), "needs_review");
  assert.equal(f.emitted.filter(value => value.type === "capture").length, 0); assert.equal(f.clicks(), 1);
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
const pickerRows = [
  ["Instant，第 1 项，共 5 项。", "none"], ["Medium，第 2 项，共 5 项。", "medium"],
  ["High，第 3 项，共 5 项。", "high"], ["Extra High，第 4 项，共 5 项。", "max"], ["Pro，第 5 项，共 5 项。", "medium"]
];
const fixtureSliderSelector = '[role="menuitem"][data-reasoning-slider="true"][aria-label="强度"][aria-keyshortcuts="ArrowLeft ArrowRight"]';
const fixtureStatusSelector = '[role="status"][aria-live="polite"]';
function pickerFixture({ pauseKeys = false, pauseOpen = false, pauseClose = false } = {}) {
  const f = contentFixture({ profileText: "Pro" }); let index = 4, profileClicks = 0;
  const menu = new Node("", { role: "menu", id: "menu-owned", "aria-labelledby": "profile-original" });
  const slider = new Node("", { role: "menuitem", "data-reasoning-slider": "true", "aria-label": "强度", "aria-keyshortcuts": "ArrowLeft ArrowRight" });
  const status = new Node("", { role: "status", "aria-live": "polite" }), keys = [], seen = [];
  const keyWaiters = [], clickWaiters = [];
  const waitForCount = (count, readCount, waiters, label) => {
    if (readCount() >= count) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const waiter = { count, resolve, timer: setTimeout(() => {
        const index = waiters.indexOf(waiter); if (index >= 0) waiters.splice(index, 1);
        reject(new Error(`Fixture did not observe ${count} ${label}.`));
      }, 10000) };
      waiters.push(waiter);
    });
  };
  const publishCount = (count, waiters) => {
    for (const waiter of [...waiters]) if (count >= waiter.count) {
      waiters.splice(waiters.indexOf(waiter), 1); clearTimeout(waiter.timer); waiter.resolve();
    }
  };
  slider.parentElement = menu; status.parentElement = menu;
  menu.children.set(fixtureSliderSelector, [slider]); menu.children.set(fixtureStatusSelector, [status]);
  f.items.set('[role="menu"]', []); f.model.attributes["data-selected-reasoning-effort"] = "medium";
  const show = value => { index = value; status.textContent = pickerRows[value][0]; f.model.attributes["data-selected-reasoning-effort"] = pickerRows[value][1]; seen.push([...pickerRows[value]]); f.mutateNow(); };
  f.model.click = () => {
    profileClicks++; publishCount(profileClicks, clickWaiters);
    if (f.model.attributes["aria-expanded"] === "false") {
      if (pauseOpen) return;
      f.model.attributes["aria-expanded"] = "true"; f.model.attributes["aria-controls"] = "menu-owned";
      f.model.textContent = "思考强度思考强度"; f.items.set('[role="menu"]', [menu]); show(index);
    } else {
      if (pauseClose) return;
      f.model.attributes["aria-expanded"] = "false"; f.model.textContent = "思考强度Instant";
      f.model.attributes["data-selected-reasoning-effort"] = "none"; f.items.set('[role="menu"]', []); f.mutateNow();
    }
  };
  slider.dispatchEvent = event => {
    keys.push({ type: event.type, key: event.key, code: event.code, bubbles: event.bubbles, cancelable: event.cancelable, repeat: event.repeat });
    publishCount(keys.length, keyWaiters);
    if (event.type === "keydown" && !pauseKeys) show(Math.max(0, index - 1));
    return true;
  };
  return { ...f, menu, slider, status, keys, seen, show, index: () => index, profileClicks: () => profileClicks,
    whenKeys: count => waitForCount(count, () => keys.length, keyWaiters, "keyboard events"),
    whenProfileClicks: count => waitForCount(count, () => profileClicks, clickWaiters, "original control clicks") };
}
await test("generic readonly readiness reports control presence without profile claims or selection permission", async () => {
  const f = pickerFixture(), request = readinessFor();
  const result = await f.controller.receive({ type: "relay.content.readiness", readiness: request });
  relay.validatePageReady(result, request);
  assert.deepEqual(Object.keys(result.observation).sort(), ["url", "chatMode", "loginVerified", "emptyComposer", "modelControlPresent", "completionInitiallyPresent", "surface", "observationSha256"].sort());
  assert.equal(f.model.textContent, "Pro"); assert.equal(f.profileClicks(), 0); assert.equal(f.keys.length, 0); assert.equal(f.storage.writes.length, 0);
  rejected(() => relay.validatePrepared({ ...result, type: "prepared" }), "invalid_schema");
  rejected(() => relay.validatePageReady({ ...result, observation: { ...result.observation, observedProfile: "Instant" } }, request), "invalid_schema");
  const commit = relay.envelope("commitSend", prepare);
  await assert.rejects(f.controller.receive({ type: "relay.content.commit", commit }), error => error.code === "commit_not_prepared");
  assert.equal(f.clicks(), 0);
});
await test("full frozen Fast prepare selects only the observed four left steps and closes the original control before proving Instant", async () => {
  const f = pickerFixture();
  const result = await f.controller.receive({ type: "relay.content.prepare", prepare }); relay.validatePrepared(result);
  assert.deepEqual(f.seen, [...pickerRows].reverse()); assert.equal(f.profileClicks(), 2);
  assert.deepEqual(f.keys.map(item => item.type), ["keydown", "keyup", "keydown", "keyup", "keydown", "keyup", "keydown", "keyup"]);
  assert.ok(f.keys.every(item => item.key === "ArrowLeft" && item.code === "ArrowLeft" && item.bubbles && item.cancelable && item.repeat === false));
  assert.equal(result.observation.profileDom.text, "思考强度Instant"); assert.equal(result.observation.profileDom.reasoningEffort, "none");
  assert.equal(f.model.attributes["aria-expanded"], "false"); assert.equal(f.composer.textContent, "");
  assert.equal(f.clicks(), 0); assert.equal(f.storage.writes.length, 0); assert.equal(f.timers.size, 0);
  await f.controller.receive({ type: "relay.content.commit", commit: relay.envelope("commitSend", prepare) });
  assert.equal(f.clicks(), 1); assert.equal(f.composer.textContent, prompt);
  await assert.rejects(f.controller.receive({ type: "relay.content.prepare", prepare }), error => error.code === "page_already_prepared");
  assert.equal(f.profileClicks(), 2); assert.equal(f.keys.length, 8); f.controller.stop();
});
await test("profile selection waits only on actual DOM changes and never proves the open menu placeholder", async () => {
  const f = pickerFixture({ pauseKeys: true }), pending = f.controller.receive({ type: "relay.content.prepare", prepare });
  await f.whenKeys(2); assert.equal(f.keys.length, 2); assert.equal(f.controller.phase(), "preparing");
  for (const index of [3, 2, 1, 0]) {
    f.show(index);
    if (index > 0) { await f.whenKeys((5 - index) * 2); assert.equal(f.controller.phase(), "preparing"); }
  }
  const result = await pending; relay.validatePrepared(result); assert.equal(f.profileClicks(), 2); assert.equal(f.keys.length, 8); assert.equal(f.timers.size, 0);
  const open = pickerFixture({ pauseClose: true }), blocked = open.controller.receive({ type: "relay.content.prepare", prepare });
  const rejection = assert.rejects(blocked, error => error.code === "profile_selection_timeout");
  await open.whenProfileClicks(2); assert.equal(open.index(), 0); assert.equal(open.model.textContent, "思考强度思考强度");
  assert.equal(open.controller.phase(), "preparing"); [...open.timers.values()][0].fn(); await rejection;
  assert.equal(open.clicks(), 0); assert.equal(open.storage.writes.length, 0); assert.equal(open.timers.size, 0);
});
await test("positive client rectangles cannot activate controls in hidden or inert ancestors", async () => {
  for (const flag of ["hidden", "inert", "inertAttribute", "ariaHidden"]) {
    const f = pickerFixture(), ancestor = new Node(); f.model.parentElement = ancestor;
    if (flag === "hidden") ancestor.hidden = true;
    if (flag === "inert") ancestor.inert = true;
    if (flag === "inertAttribute") ancestor.attributes.inert = "";
    if (flag === "ariaHidden") ancestor.attributes["aria-hidden"] = "true";
    assert.equal(f.model.getClientRects().length, 1);
    await assert.rejects(f.controller.receive({ type: "relay.content.prepare", prepare }), error => error.code === "dom_contract_changed");
    assert.equal(f.profileClicks(), 0); assert.equal(f.keys.length, 0); assert.equal(f.clicks(), 0); assert.equal(f.storage.writes.length, 0);
  }
  const f = pickerFixture(), inactiveMenu = new Node("Inactive", { role: "menu" }), ancestor = new Node("", { "aria-hidden": "true" });
  inactiveMenu.parentElement = ancestor;
  const click = f.model.click; f.model.click = () => {
    click(); if (f.model.attributes["aria-expanded"] === "true") f.items.set('[role="menu"]', [f.menu, inactiveMenu]);
  };
  const result = await f.controller.receive({ type: "relay.content.prepare", prepare }); relay.validatePrepared(result);
  assert.equal(f.profileClicks(), 2); assert.equal(f.keys.length, 8); assert.equal(f.clicks(), 0); assert.equal(f.storage.writes.length, 0);
});
await test("keydown replacement or deactivation cannot send keyup to the retired slider", async () => {
  for (const change of [
    f => { f.menu.children.set(fixtureSliderSelector, [new Node("Other")]); },
    f => { f.menu.children.set(fixtureStatusSelector, [new Node("Other")]); },
    f => { f.items.set('[role="menu"]', [new Node("Other", { role: "menu" })]); },
    f => { f.slider.isConnected = false; },
    f => { f.menu.attributes["aria-hidden"] = "true"; }
  ]) {
    const f = pickerFixture({ pauseKeys: true }), dispatch = f.slider.dispatchEvent;
    f.slider.dispatchEvent = event => { const result = dispatch(event); if (event.type === "keydown") change(f); return result; };
    await assert.rejects(f.controller.receive({ type: "relay.content.prepare", prepare }), error => error.code === "profile_picker_unverified");
    assert.deepEqual(f.keys.map(item => item.type), ["keydown"]);
    assert.equal(f.profileClicks(), 1); assert.equal(f.clicks(), 0); assert.equal(f.storage.writes.length, 0); assert.equal(f.timers.size, 0);
  }
});
await test("unbound duplicate or unknown menu status cannot cause the first selection key", async () => {
  for (const change of [
    f => { f.menu.attributes["aria-labelledby"] = "other-button"; },
    f => { f.model.attributes["aria-controls"] = "other-menu"; },
    f => { f.items.set('[role="menu"]', [f.menu, new Node("Other", { role: "menu" })]); },
    f => { f.menu.children.set(fixtureSliderSelector, [f.slider, new Node("Other")]); },
    f => { f.menu.children.set(fixtureStatusSelector, [f.status, new Node("Other")]); },
    f => { f.status.textContent = "Pro，第 5 项，共 6 项。"; },
    f => { f.model.attributes["data-selected-reasoning-effort"] = "max"; }
  ]) {
    const f = pickerFixture(), click = f.model.click; f.model.click = () => { click(); change(f); };
    await assert.rejects(f.controller.receive({ type: "relay.content.prepare", prepare }), error => error.code === "profile_picker_unverified");
    assert.equal(f.keys.length, 0); assert.equal(f.clicks(), 0); assert.equal(f.storage.writes.length, 0); assert.equal(f.timers.size, 0);
  }
});
await test("unknown requests prior intents and wrong frozen hashes cannot acquire picker permission", async () => {
  for (const variant of ["high", "pro", "hash", "intent", "draft", "open"]) {
    const f = pickerFixture(), value = clone(prepare);
    if (["high", "pro"].includes(variant)) value.requestedProfile = variant;
    if (variant === "hash") value.promptSha256 = "f".repeat(64);
    if (variant === "intent") f.storage.data[context.ConsoleChatRelayContent.CONTENT_PREFIX + dispatchId] = { phase: "send_intent" };
    if (variant === "draft") f.composer.textContent = "真实用户草稿\n ";
    if (variant === "open") { f.model.attributes["aria-expanded"] = "true"; f.items.set('[role="menu"]', [f.menu]); }
    await assert.rejects(f.controller.receive({ type: "relay.content.prepare", prepare: value }));
    assert.equal(f.profileClicks(), 0); assert.equal(f.keys.length, 0); assert.equal(f.clicks(), 0); assert.equal(f.storage.writes.length, 0);
    if (variant === "draft") assert.equal(f.composer.textContent, "真实用户草稿\n ");
  }
});
await test("late draft turn URL or skipped ordinal stops profile selection without typing or another key", async () => {
  for (const [change, code] of [
    [f => { f.composer.textContent = "后到用户输入\n "; }, "composer_changed"],
    [f => { f.env.location.href = capture.evidence.conversationUrl; }, "not_fresh_chat"],
    [f => { f.items.set("#complete", [new Node("回答已完成")]); }, "not_fresh_chat"],
    [f => { f.show(2); }, "profile_picker_unverified"],
    [f => { f.items.set("#profile", [new Node("Other")]); }, "profile_changed"]
  ]) {
    const f = pickerFixture({ pauseKeys: true }), pending = f.controller.receive({ type: "relay.content.prepare", prepare });
    const rejection = assert.rejects(pending, error => error.code === code); await f.whenKeys(2);
    assert.equal(f.keys.length, 2); change(f); f.mutateNow(); await rejection;
    assert.equal(f.keys.length, 2); assert.equal(f.clicks(), 0); assert.equal(f.storage.writes.length, 0); assert.equal(f.timers.size, 0);
    if (code === "composer_changed") assert.equal(f.composer.textContent, "后到用户输入\n ");
  }
});
await test("matching cancel timeout or page stop cleans picker waits and late steps cannot revive prepared", async () => {
  for (const trigger of ["cancel", "timeout", "stop"]) {
    const f = pickerFixture({ pauseKeys: true }), pending = f.controller.receive({ type: "relay.content.prepare", prepare });
    const rejection = assert.rejects(pending, error => error.code === (trigger === "timeout" ? "profile_selection_timeout" : "prepare_cancelled"));
    await f.whenKeys(2);
    if (trigger === "timeout") [...f.timers.values()][0].fn();
    else if (trigger === "stop") f.controller.stop();
    else f.controller.cancel(relay.envelope("cancel", prepare));
    await rejection; f.show(3); await new Promise(resolve => setImmediate(resolve));
    assert.notEqual(f.controller.phase(), "prepared"); assert.equal(f.keys.length, 2); assert.equal(f.profileClicks(), 1);
    assert.equal(f.timers.size, 0); assert.equal(f.clicks(), 0); assert.equal(f.composer.textContent, ""); assert.equal(f.storage.writes.length, 0);
  }
});
console.log(`PASS ${tests} isolated relay checks; no real Chat/browser or production state accessed.`);
