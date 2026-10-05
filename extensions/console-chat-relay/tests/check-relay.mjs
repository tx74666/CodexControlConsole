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
    for (const text of ["Instant", "Thinking effortInstant", "思考强度Instant"]) {
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
function workerFixture(initial = {}, browserSurface = "chrome") {
  const storage = storageFixture(initial), ports = [], tabs = [], calls = [], updates = new Event();
  let sendFailure = false, prepareFailure = false, preparedSurface = null;
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
          const response = preparedFor(value.prepare);
          if (preparedSurface !== null) response.observation.surface = preparedSurface;
          return response;
        }
        if (sendFailure) throw new Error("fixture click outcome unknown");
        return { committed: true };
      } } };
  const controller = context.ConsoleChatRelayWorker.createController(api, () => browserSurface);
  const status = clientReady => ({ protocol: relay.PROTOCOL, type: "status", hostName: relay.HOST_NAME, enabled: true,
    approved: true, configured: true, message: "fixture-only approved endpoint", clientReady });
  return { api, storage, ports, tabs, calls, controller, status,
    failSend() { sendFailure = true; },
    failPrepare() { prepareFailure = true; },
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
  get innerText() { return this.textContent === "" && this.emptyInnerText !== undefined ? this.emptyInnerText : this.textContent; }
  getAttribute(key) { return this.attributes[key] ?? null; }
  getClientRects() { return [{}]; }
  querySelectorAll(selector) { return this.children.get(selector) || []; }
  focus() {}
  dispatchEvent() { return true; }
}
function contentFixture({ promptText = prompt, completed = false, stop = false, extraUser = false, clickThrows = false, draft = "", answerShell = false,
  emptyInnerText, profileText = "Thinking effortInstant", completionText = "Response complete" } = {}) {
  const storage = storageFixture(), messages = [], emitted = [], queries = [], timers = new Map(), location = { href: "https://chatgpt.com/" };
  const composer = new Node(draft, { role: "textbox", contenteditable: "true" });
  composer.emptyInnerText = emptyInnerText;
  const model = new Node(profileText, { "data-selected-reasoning-effort": "none" });
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
  const env = { chrome: { storage, runtime: { async sendMessage(value) { emitted.push(clone(value)); return { received: true }; } } },
    document: { documentElement: {}, querySelectorAll(selector) {
      assert.equal(typeof selector, "string"); assert.ok(selector); queries.push(selector); return items.get(selector) || [];
    } }, location, MutationObserver: Observer,
    InputEvent: class { constructor(type, detail) { this.type = type; this.detail = detail; } }, now: () => Date.parse("2026-10-05T12:00:00.000Z"),
    setTimeout(fn, timeout) { const id = nextTimer++; timers.set(id, { fn, timeout }); return id; }, clearTimeout(id) { timers.delete(id); } };
  return { env, items, storage, emitted, queries, composer, model, messages, timers, controller: context.ConsoleChatRelayContent.createController(env),
    clicks: () => clicks, async mutation() { mutation?.(); await this.controller.idle(); await this.controller.idle(); } };
}
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
await test("bidirectional serial worker/content failure replies before uncertain acknowledgement and never retries", async () => {
  const worker = workerFixture(), content = contentFixture({ clickThrows: true }), notifications = [];
  content.env.chrome.runtime.sendMessage = async value => {
    notifications.push(clone(value));
    const sender = { id: relay.EXTENSION_ID, tab: { id: 41 }, frameId: 0, url: content.env.location.href };
    try { return await worker.controller.page(value, sender); }
    catch (error) { return { received: false, code: error.code || "page_rejected" }; }
  };
  worker.api.tabs.sendMessage = async (id, value) => {
    worker.calls.push({ id, value: clone(value) });
    try { return await content.controller.receive(value); }
    catch (error) { return { committed: false, code: error.code || "page_control_rejected" }; }
  };
  await worker.enable(); await worker.controller.native(prepare);
  let deadline;
  try {
    await Promise.race([worker.controller.native(relay.envelope("commitSend", prepare)),
      new Promise((_, reject) => { deadline = setTimeout(() => reject(new Error("bidirectional commit queue deadlocked")), 500); })]);
  } finally { clearTimeout(deadline); }
  await worker.controller.idle(); await content.controller.idle();
  assert.equal(content.clicks(), 1); assert.equal(content.controller.phase(), "needs_review");
  assert.equal(worker.controller.state().active.phase, "needs_review");
  assert.equal(worker.storage.data.consoleChatRelayV1.attempts[dispatchId].phase, "needs_review");
  assert.equal(content.storage.data[context.ConsoleChatRelayContent.CONTENT_PREFIX + dispatchId].phase, "send_intent");
  assert.ok(notifications.some(value => value.type === "uncertain" && relay.sameIdentity(value, prepare)));
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
console.log(`PASS ${tests} isolated relay checks; no real Chat/browser or production state accessed.`);
