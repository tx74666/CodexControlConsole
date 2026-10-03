#!/usr/bin/env node
// User flows against isolated responses: no real transfers, clipboard writes or opened files.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { File } from "node:buffer";
const script = readFileSync(new URL("../transfer-panel.js", import.meta.url), "utf8");
const response = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, async json() { return body; } });
const defer = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const settle = () => new Promise(resolve => setImmediate(resolve));
const photo = (name = "photo.png", count = 8) => new File([new Uint8Array(count)], name, { type: "image/png" });
function message(id = "one", phone = true, text = "手机文字") {
  const base = phone ? "/api/phone/transfer" : "/api/transfer";
  return { id, requestId: "uuid", sender: "phone", createdAt: "2026-10-03T12:00:00+08:00", text, attachments: [{ id: "asset-1", name: "<script>photo.png", mimeType: "image/png", size: 8, previewable: true, url: `${base}/attachment?id=asset-1`, previewUrl: `${base}/attachment?id=asset-1&preview=1`, path: "D:\\library\\photo.png" }] };
}
function harness(phone = true) {
  class Element {
    constructor(tag = "div") { this.tagName = tag.toUpperCase(); this.children = []; this.listeners = new Map(); this.dataset = {}; this.hidden = false; this.value = ""; this._text = ""; this.attributes = {}; this.classList = { add() {} }; }
    append(...elements) { this.children.push(...elements); }
    replaceChildren(...elements) { this.children = elements; this._text = ""; }
    set textContent(value) { this.replaceChildren(); this._text = String(value); }
    get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
    get childElementCount() { return this.children.length; }
    set innerHTML(_) { throw new Error("No untrusted HTML allowed."); }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    addEventListener(name, handler) { this.listeners.set(name, handler); }
    click() { this.clicked = true; return this.listeners.get("click")?.({}); }
    focus() { this.focused = true; }
    select() { this.selected = true; }
    setSelectionRange() { this.selected = true; }
    remove() { this.removed = true; }
  }
  const calls = [], answers = [], timers = new Map(), events = new Map(), previews = [], revoked = []; let nextTimer = 1, authCount = 0;
  const root = new Element(), body = new Element("body");
  const document = { body, hidden: false, createElement: tag => new Element(tag), addEventListener(name, handler) { events.set(name, handler); }, execCommand: () => true };
  class BrowserURL extends URL { static createObjectURL(file) { const value = `blob:${previews.length}`; previews.push({ file, value }); return value; } static revokeObjectURL(value) { revoked.push(value); } }
  const runtime = { document, navigator: {}, URL: BrowserURL, URLSearchParams, AbortController, TypeError, FormData, window: { isSecureContext: false, location: { href: "http://192.168.0.2:8899/?tab=transfer" }, setTimeout(fn, delay) { const id = nextTimer++; timers.set(id, { fn, delay }); return id; }, clearTimeout(id) { timers.delete(id); } }, async fetch(url, options) { calls.push({ url, options }); const answer = answers.shift(); assert.ok(answer, `Unexpected request ${url}`); return await answer; } };
  runInNewContext(script, runtime);
  const panel = runtime.window.CodexTransferPanel.create(root, { phone, onAuth() { authCount++; panel.clear(); } });
  const all = (tag, start = root) => {
    const nodes = []; function visit(element) { if (element.tagName === tag.toUpperCase()) nodes.push(element); for (const child of element.children) visit(child); } visit(start); return nodes;
  };
  const button = text => all("button").find(item => item.textContent === text);
  const form = all("form")[0], text = all("textarea")[0], photos = all("input")[0];
  function select(...files) { photos.files = files; photos.listeners.get("change")({}); }
  async function send() { return form.listeners.get("submit")({ preventDefault() {} }); }
  function type(value) { text.value = value; text.listeners.get("input")({}); }
  return { root, body, panel, runtime, document, calls, answers, timers, events, all, button, form, text, photos, select, send, type, previews, revoked, authCount: () => authCount, respond(value, status) { answers.push(response(value, status)); } };
}
let count = 0;
async function test(name, run) { await run(); console.log(`PASS ${name}`); count++; }
await test("desktop and LAN mobile expose transfer plus existing sections", () => {
  const desktop = readFileSync(new URL("../index.html", import.meta.url), "utf8"), mobile = readFileSync(new URL("../mobile.html", import.meta.url), "utf8");
  assert.match(desktop, /data-console-view-target="transfer"/); assert.match(desktop, /id="desktopTransferPanel"/);
  assert.deepEqual([...mobile.matchAll(/data-tab="([^"]+)"/g)].map(value => value[1]), ["transfer", "tasks", "music", "device", "documents"]);
  for (const source of [desktop, mobile]) { assert.match(source, /transfer-panel\.js/); assert.match(source, /transfer-panel\.css/); }
  assert.doesNotMatch(script, /\.innerHTML|document\.cookie|localStorage|serviceWorker/);
});
await test("pairing QR changes with LAN address, reveals no pairing code and falls back to address", () => {
  const h = harness(), nodes = new Map();
  function get(id) { if (!nodes.has(id)) { const element = h.document.createElement("div"); element.removeAttribute = name => { delete element.attributes[name]; delete element[name]; }; nodes.set(id, element); } return nodes.get(id); }
  const qr = get("phoneCompanionQr"); let source = "", assignments = 0;
  Object.defineProperty(qr, "src", { configurable: true, get() { return source; }, set(value) { source = value; assignments++; } });
  const pairing = readFileSync(new URL("../phone-pairing.js", import.meta.url), "utf8");
  assert.ok(/\}\)\(\);\s*$/.test(pairing));
  const context = { ...h.runtime, document: { ...h.document, getElementById: get } };
  runInNewContext(pairing.replace(/\}\)\(\);\s*$/, "globalThis.PAIRING_TEST = {render}; })();"), context);
  const state = { enabled: true, availableInterfaces: [{ address: "192.168.0.2", name: "Wi-Fi" }], host: "192.168.0.2", url: "http://192.168.0.2:8899/", connectionUrl: "http://codex-0123456789abcdef.local:8899/", qrGeneration: "non-secret-generation", qrUrl: "http://codex-0123456789abcdef.local:8899/?tab=transfer#qrToken=secret-qrcode", discovery: { available: true }, rememberedDevices: [{ id: "device-one", name: "iPhone" }], pairingCode: "123456", pairingExpiresAt: "2099-10-03T12:00:00Z", pairedCount: 0 };
  context.PAIRING_TEST.render(state); assert.equal(qr.hidden, false); assert.match(source, /^\/api\/phone-companion\/qr\.png\?version=/); assert.doesNotMatch(source, /123456/);
  assert.match(source, /version=non-secret-generation/); assert.doesNotMatch(source, /qrToken|secret-qrcode/);
  assert.match(get("phoneCompanionUrl").href, /codex-0123456789abcdef.local.*tab=transfer/); const initial = assignments; context.PAIRING_TEST.render(state); assert.equal(assignments, initial);
  qr.listeners.get("error")({}); assert.equal(qr.hidden, true); assert.match(get("phoneCompanionUrl").textContent, /codex-0123456789abcdef.local/);
  get("phoneCompanionQrIp").listeners.get("click")({}); assert.match(source, /address=ip/); assert.match(get("phoneCompanionUrl").href, /192\.168\.0\.2/);
  context.PAIRING_TEST.render({ ...state, enabled: false }); assert.equal(qr.hidden, true); assert.equal(qr.dataset.url, undefined);
});
await test("no automatic requests until a paired transfer page becomes active", async () => {
  const h = harness(); assert.equal(h.calls.length, 0); assert.equal(h.button("发送").disabled, true);
  h.respond({ messages: [], revision: "r1", hasMore: false }); h.panel.setActive(true); await settle();
  assert.equal(h.calls.length, 1); assert.match(h.calls[0].url, /^\/api\/phone\/transfer\/messages\?/);
  assert.equal(h.calls[0].options.credentials, "same-origin"); assert.equal(h.calls[0].options.referrerPolicy, "same-origin"); assert.equal(h.calls[0].options.redirect, "error"); assert.equal(h.calls[0].options.headers["X-Codex-Phone"], "1");
  assert.ok([...h.timers.values()].some(timer => timer.delay === 4000));
  h.panel.setActive(false); assert.equal(h.timers.size, 0);
});
await test("photos and text upload together, preserving original file and immediate history", async () => {
  const h = harness(); const file = photo(); h.select(file); h.type("  图片说明\n第二行  ");
  assert.equal(h.previews.length, 1); assert.equal(h.button("上传并发送").disabled, false);
  h.respond({ message: message() }); await h.send();
  const call = h.calls[0]; assert.equal(call.url, "/api/phone/transfer/messages"); assert.equal(call.options.method, "POST"); assert.equal(call.options.referrerPolicy, "same-origin");
  assert.equal(call.options.body.get("text"), "  图片说明\n第二行  "); assert.equal(call.options.body.getAll("files").length, 1); assert.equal(call.options.body.get("files").name, "photo.png");
  assert.match(call.options.body.get("requestId"), /^[0-9a-f-]{36}$/); assert.equal(call.options.headers["Content-Type"], undefined);
  assert.equal(h.text.value, ""); assert.deepEqual(h.revoked, ["blob:0"]); assert.match(h.root.textContent, /已传到电脑/);
  assert.equal(h.all("img").length, 1); assert.equal(h.all("script").length, 0); assert.match(h.root.textContent, /<script>photo.png/);
  assert.ok(h.all("a").some(link => link.download === "<script>photo.png")); assert.equal(h.button("打开文件"), undefined); assert.equal(h.button("复制本地路径"), undefined);
});
await test("failed upload keeps draft and retry UUID, duplicate submit blocked", async () => {
  const h = harness(); h.select(photo()); h.type("请接收"); const pending = defer(); h.answers.push(pending.promise);
  const first = h.send(); assert.equal(h.calls.length, 1); assert.equal(h.text.disabled, true); assert.equal(h.button("正在上传…").disabled, true);
  await h.send(); assert.equal(h.calls.length, 1);
  pending.resolve(response({ error: "Wi-Fi 中断" }, 503)); await first;
  assert.equal(h.text.value, "请接收"); assert.equal(h.all("img").length, 1); assert.deepEqual(h.revoked, []); assert.equal(h.text.disabled, false);
  const firstId = h.calls[0].options.body.get("requestId"); h.respond({ message: message(), duplicate: true }); await h.send();
  assert.equal(h.calls[1].options.body.get("requestId"), firstId); assert.equal(h.calls[1].options.body.getAll("files").length, 1); assert.equal(h.all("article").length, 1);
});
await test("editing a failed draft produces a new submission ID", async () => {
  const h = harness(); h.type("第一版"); h.respond({ error: "失败" }, 500); await h.send();
  h.type("第二版"); h.respond({ message: message() }); await h.send();
  assert.notEqual(h.calls[0].options.body.get("requestId"), h.calls[1].options.body.get("requestId"));
});
await test("client refuses excess count and size and retains selected files", async () => {
  const h = harness(); h.select(photo("one.png")); h.select(photo("two.png"), photo("three.png"), photo("four.png"), photo("five.png"));
  assert.equal(h.previews.length, 1); assert.match(h.root.textContent, /最多 4 张图片/);
  const oversized = photo("large.png", 12 * 1024 ** 2 + 1); h.select(oversized); assert.equal(h.previews.length, 1); assert.match(h.root.textContent, /超过/);
  h.type("a".repeat(20001)); await h.send(); assert.equal(h.calls.length, 0); assert.match(h.root.textContent, /文字最多/);
  h.button("移除").click(); assert.deepEqual(h.revoked, ["blob:0"]);
});
await test("image-only selection reserves request overhead and accepts HEIC originals", async () => {
  const h = harness(); h.select(new File(["abc"], "document.txt", { type: "text/plain" })); assert.equal(h.previews.length, 0); assert.match(h.root.textContent, /不是支持的图片格式/);
  h.select(photo("first.png", 12 * 1024 ** 2), photo("second.png", 12 * 1024 ** 2)); assert.equal(h.previews.length, 0); assert.match(h.root.textContent, /合计不能超过/);
  h.select(new File(["heic-data"], "iPhone.HEIC", { type: "image/heic" })); assert.equal(h.previews.length, 0); assert.ok(h.button("上传并发送"));
  h.respond({ error: "未完成" }, 503); await h.send(); assert.equal(h.calls[0].options.body.get("files").name, "iPhone.HEIC");
});
await test("unchanged revision polls without rebuilding history and stops while background", async () => {
  const h = harness(); h.respond({ messages: [message()], revision: "r1", hasMore: false }); h.panel.setActive(true); await settle();
  const article = h.all("article")[0], timer = [...h.timers.values()].find(item => item.delay === 4000);
  h.respond({ unchanged: true, revision: "r1" }); timer.fn(); await settle();
  assert.match(h.calls[1].url, /revision=r1/); assert.equal(h.all("article")[0], article);
  h.document.hidden = true; h.events.get("visibilitychange")(); assert.equal(h.timers.size, 0);
  h.document.hidden = false; h.respond({ unchanged: true, revision: "r1" }); h.events.get("visibilitychange")(); await settle(); assert.equal(h.calls.length, 3);
});
await test("earlier records are appended once using before cursor", async () => {
  const h = harness(); h.respond({ messages: [message("new")], revision: "r1", hasMore: true }); h.panel.setActive(true); await settle();
  h.respond({ messages: [message("old")], revision: "r1", hasMore: false }); h.button("较早记录").click(); await settle();
  assert.match(h.calls[1].url, /before=new/); assert.equal(h.all("article").length, 2); assert.equal(h.button("较早记录").hidden, true);
});
await test("rejects remote attachment links and keeps text literal", async () => {
  const h = harness(); const item = message("one", true, "<img src=x onerror=evil> [click](javascript:evil)"); item.attachments[0].url = "https://evil.test/api/phone/transfer/attachment?id=secret";
  h.respond({ messages: [item], revision: "r1" }); h.panel.setActive(true); await settle();
  assert.equal(h.all("a").length, 0); assert.equal(h.all("img").length, 0); assert.match(h.root.textContent, /<img src=x onerror=evil>/);
});
await test("HTTP iPhone copies without clipboard API and manual fallback stays selected", async () => {
  const h = harness(); h.respond({ messages: [message()], revision: "r1" }); h.panel.setActive(true); await settle();
  h.button("复制文字").click(); await settle(); assert.match(h.root.textContent, /已复制/); assert.equal(h.body.children[0].selected, true); assert.equal(h.body.children[0].removed, true);
  h.document.execCommand = () => false; h.button("复制文字").click(); await settle();
  assert.match(h.root.textContent, /长按复制/); assert.equal(h.body.children[1].value, "手机文字"); assert.equal(h.body.children[1].removed, undefined);
  h.all("button", h.body).find(item => item.textContent === "完成复制").click(); assert.equal(h.body.children[1].removed, true);
});
await test("desktop offers file opening using attachment ID and local path copy", async () => {
  const h = harness(false); h.respond({ messages: [message("one", false)], revision: "r1" }); h.panel.setActive(true); await settle();
  assert.equal(h.calls[0].options.headers["X-Codex-Phone"], undefined); assert.ok(h.button("打开文件")); assert.ok(h.button("复制本地路径"));
  h.respond({ opened: true }); h.button("打开文件夹").click(); await settle();
  assert.equal(h.calls[1].url, "/api/transfer/open"); assert.deepEqual(JSON.parse(h.calls[1].options.body), { id: "asset-1", folder: true });
});
await test("pair revocation removes private records but preserves unsent draft", async () => {
  const h = harness(); h.respond({ messages: [message()], revision: "r1" }); h.panel.setActive(true); await settle(); h.type("尚未发送");
  h.respond({ error: "需要配对" }, 401); await h.panel.refresh();
  assert.equal(h.authCount(), 1); assert.equal(h.all("article").length, 0); assert.equal(h.text.value, "尚未发送"); assert.equal(h.timers.size, 0);
});
await test("private clear revokes pending previews while retaining selected originals for retry", async () => {
  const h = harness(); h.select(photo()); h.type("草稿"); h.respond({ error: "Wi-Fi 中断" }, 503); await h.send();
  const firstId = h.calls[0].options.body.get("requestId"); h.panel.clear(); assert.deepEqual(h.revoked, ["blob:0"]); assert.equal(h.all("img").length, 0); assert.equal(h.text.value, "草稿");
  h.respond({ message: message() }); await h.send(); assert.equal(h.calls[1].options.body.get("requestId"), firstId); assert.equal(h.calls[1].options.body.get("files").name, "photo.png");
});
await test("a recovered history poll clears only its connection error", async () => {
  const h = harness(); h.respond({ error: "暂时离线" }, 503); h.panel.setActive(true); await settle(); assert.match(h.root.textContent, /暂时离线/);
  h.respond({ messages: [], revision: "r1" }); await h.panel.refresh(); assert.match(h.root.textContent, /已重新连接电脑/);
});
await test("a stale poll cannot overwrite a successfully uploaded message", async () => {
  const h = harness(); const old = defer(); h.answers.push(old.promise); h.panel.setActive(true); h.type("新内容"); h.respond({ message: message("new") }); await h.send();
  old.resolve(response({ messages: [], revision: "old" })); await settle();
  assert.equal(h.all("article").length, 1); assert.match(h.root.textContent, /手机文字/);
});
await test("a late unauthorized response from a revoked connection cannot clear a new connection", async () => {
  const h = harness(); const old = defer(); h.answers.push(old.promise); h.panel.setActive(true); h.panel.clear();
  old.resolve(response({ error: "旧配对已失效" }, 401)); await settle(); assert.equal(h.authCount(), 0);
  h.respond({ messages: [message("new")], revision: "r2" }); h.panel.setActive(true); await settle(); assert.equal(h.all("article").length, 1);
});
console.log(`Transfer UI checks passed (${count} cases).`);
