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
// Validation only reads metadata; avoid allocating megabytes for size boundaries.
const sizedPhoto = (name, bytes) => ({ name, size: bytes, type: "image/png" });
const clipboardEntry = file => ({ kind: "file", type: file.type, getAsFile: () => file });
function message(id = "one", phone = true, text = "手机文字") {
  const base = phone ? "/api/phone/transfer" : "/api/transfer";
  return { id, requestId: "uuid", sender: "phone", createdAt: "2026-10-03T12:00:00+08:00", text, starred: false, attachments: [{ id: "asset-1", name: "<script>photo.png", mimeType: "image/png", size: 8, previewable: true, url: `${base}/attachment?id=asset-1`, previewUrl: `${base}/attachment?id=asset-1&preview=1`, path: "D:\\library\\photo.png" }] };
}
const historyPage = (messages, revision = "r1", hasMore = false) => ({ messages, revision, hasMore });
const cardFor = (h, id) => h.all("article").find(card => card.dataset.messageId === id);
const starFor = (h, id) => h.all("button", cardFor(h, id)).find(button => button.className === "transfer-button transfer-star");
function harness(phone = true) {
  class Element {
    constructor(tag = "div") { this.tagName = tag.toUpperCase(); this.children = []; this.listeners = new Map(); this.dataset = {}; this.hidden = false; this.value = ""; this._text = ""; this.attributes = {}; this.classList = { add() {} }; }
    append(...elements) { this.children.push(...elements); for (const element of elements) element.parentElement = this; }
    replaceChildren(...elements) { for (const child of this.children) child.parentElement = null; this.children = []; this.append(...elements); this._text = ""; }
    set textContent(value) { this.replaceChildren(); this._text = String(value); }
    get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
    get childElementCount() { return this.children.length; }
    set innerHTML(_) { throw new Error("No untrusted HTML allowed."); }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    addEventListener(name, handler) { this.listeners.set(name, handler); }
    dispatch(name, fields = {}) {
      const event = { target: this, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...fields };
      for (let element = this; element; element = element.parentElement) { event.currentTarget = element; element.listeners.get(name)?.(event); }
      return event;
    }
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
  const runtime = { document, navigator: {}, URL: BrowserURL, URLSearchParams, AbortController, TypeError, FormData, File, window: { isSecureContext: false, location: { href: "http://192.168.0.2:8899/?tab=transfer" }, setTimeout(fn, delay) { const id = nextTimer++; timers.set(id, { fn, delay }); return id; }, clearTimeout(id) { timers.delete(id); } }, async fetch(url, options) { calls.push({ url, options }); const answer = answers.shift(); assert.ok(answer, `Unexpected request ${url}`); return await answer; } };
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
  function paste(clipboardData, target = form) { return target.dispatch("paste", { clipboardData }); }
  return { root, body, panel, runtime, document, calls, answers, timers, events, all, button, form, text, photos, select, send, type, paste, previews, revoked, authCount: () => authCount, respond(value, status) { answers.push(response(value, status)); } };
}
let count = 0;
async function test(name, run) { await run(); console.log(`PASS ${name}`); count++; }
await test("desktop and LAN mobile expose transfer plus existing sections", () => {
  const desktop = readFileSync(new URL("../index.html", import.meta.url), "utf8"), mobile = readFileSync(new URL("../mobile.html", import.meta.url), "utf8");
  assert.match(desktop, /data-console-view-target="transfer"/); assert.match(desktop, /id="desktopTransferPanel"/);
  assert.deepEqual([...mobile.matchAll(/data-tab="([^"]+)"/g)].map(value => value[1]), ["work", "transfer", "music", "documents"]);
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
  const oversized = sizedPhoto("large.png", 12 * 1024 ** 2 + 1); h.select(oversized); assert.equal(h.previews.length, 1); assert.match(h.root.textContent, /超过/);
  h.type("a".repeat(20001)); await h.send(); assert.equal(h.calls.length, 0); assert.match(h.root.textContent, /文字最多/);
  h.button("移除").click(); assert.deepEqual(h.revoked, ["blob:0"]);
});
await test("image-only selection reserves request overhead and accepts HEIC originals", async () => {
  const h = harness(); h.select(new File(["abc"], "document.txt", { type: "text/plain" })); assert.equal(h.previews.length, 0); assert.match(h.root.textContent, /不是支持的图片格式/);
  h.select(sizedPhoto("first.png", 12 * 1024 ** 2), sizedPhoto("second.png", 12 * 1024 ** 2)); assert.equal(h.previews.length, 0); assert.match(h.root.textContent, /合计不能超过/);
  h.select(new File(["heic-data"], "iPhone.HEIC", { type: "image/heic" })); assert.equal(h.previews.length, 0); assert.ok(h.button("上传并发送"));
  h.respond({ error: "未完成" }, 503); await h.send(); assert.equal(h.calls[0].options.body.get("files").name, "iPhone.HEIC");
});
await test("image paste bubbles once, prefers items and normalizes a screenshot name without sending", async () => {
  const h = harness(false), screenshot = photo("clipboard-image"); h.type("保留原有说明");
  const event = h.paste({ items: [{ kind: "string", type: "text/html" }, clipboardEntry(screenshot)], files: [screenshot] }, h.text);
  assert.equal(event.defaultPrevented, true); assert.equal(h.previews.length, 1); assert.equal(h.all("img").length, 1); assert.equal(h.calls.length, 0);
  const staged = h.previews[0].file; assert.ok(staged instanceof File); assert.match(staged.name, /^pasted-image-\d+-1\.png$/); assert.equal(staged.type, "image/png");
  assert.deepEqual(new Uint8Array(await staged.arrayBuffer()), new Uint8Array(await screenshot.arrayBuffer()));
  assert.equal(h.text.value, "保留原有说明"); assert.equal(h.button("上传并发送").disabled, false);
  h.respond({ message: message("pasted", false) }); await h.send();
  assert.equal(h.calls.length, 1); assert.equal(h.calls[0].options.body.getAll("files").length, 1); assert.equal(h.calls[0].options.body.get("files").name, staged.name);
});
await test("file fallback and repeated pastes append to selected originals until explicit send", async () => {
  const h = harness(false), original = photo("selected.png"), pasted = photo("pasted.png"); h.select(original); h.type("已有草稿");
  assert.equal(h.paste({ items: [], files: [pasted] }).defaultPrevented, true);
  h.paste({ files: [pasted] }, h.button("选择图片"));
  assert.equal(h.previews.length, 3); assert.equal(h.previews[0].file, original); assert.equal(h.previews[1].file, pasted); assert.equal(h.previews[2].file, pasted);
  assert.equal(h.text.value, "已有草稿"); assert.equal(h.calls.length, 0); assert.deepEqual(h.revoked, []);
  h.respond({ message: message("repeated", false) }); await h.send();
  assert.deepEqual(h.calls[0].options.body.getAll("files").map(file => file.name), ["selected.png", "pasted.png", "pasted.png"]);
  assert.equal(h.calls[0].options.body.get("text"), "已有草稿");
});
await test("four pasted images are accepted and a fifth or invalid batch preserves the draft", () => {
  const h = harness(false); h.type("不要丢失"); h.paste({ files: [1, 2, 3, 4].map(index => photo(`${index}.png`)) });
  assert.equal(h.previews.length, 4); assert.equal(h.all("img").length, 4);
  h.paste({ files: [photo("fifth.png")] }); assert.equal(h.previews.length, 4); assert.match(h.root.textContent, /最多 4 张图片/);
  h.button("移除").click(); assert.deepEqual(h.revoked, ["blob:0"]);
  h.paste({ files: [photo("replacement.png"), new File([], "empty.png", { type: "image/png" })] });
  assert.equal(h.previews.length, 4); assert.equal(h.all("img").length, 3); assert.match(h.root.textContent, /最多 4 张图片/);
  h.paste({ files: [new File([], "empty.png", { type: "image/png" })] }); assert.equal(h.all("img").length, 3); assert.match(h.root.textContent, /空文件/);
  h.paste({ files: [new File(["bmp"], "unsupported.bmp", { type: "image/bmp" })] }); assert.equal(h.all("img").length, 3); assert.match(h.root.textContent, /不是支持的图片格式/);
  assert.equal(h.text.value, "不要丢失"); assert.equal(h.calls.length, 0); assert.deepEqual(h.revoked, ["blob:0"]);
});
await test("paste accepts precise single and aggregate byte limits without large allocations", () => {
  const maxFile = 12 * 1024 ** 2, total = 24 * 1024 ** 2 - 128 * 1024;
  const single = harness(false); single.paste({ files: [sizedPhoto("exact.png", maxFile)] }); assert.equal(single.previews.length, 1);
  single.paste({ files: [sizedPhoto("over.png", maxFile + 1)] }); assert.equal(single.previews.length, 1); assert.match(single.root.textContent, /超过/);
  const combined = harness(false); combined.paste({ files: [sizedPhoto("first.png", maxFile), sizedPhoto("second.png", total - maxFile)] }); assert.equal(combined.previews.length, 2);
  combined.paste({ files: [sizedPhoto("one-byte.png", 1)] }); assert.equal(combined.previews.length, 2); assert.match(combined.root.textContent, /合计不能超过/);
  const over = harness(false); over.select(photo("keep.png")); over.paste({ files: [sizedPhoto("first.png", maxFile), sizedPhoto("second.png", total - maxFile)] });
  assert.equal(over.previews.length, 1); assert.match(over.root.textContent, /合计不能超过/); assert.deepEqual(over.revoked, []);
  for (const h of [single, combined, over]) assert.equal(h.calls.length, 0);
});
await test("text-only and missing clipboard payloads keep native paste while mixed image data keeps the draft", () => {
  const h = harness(false); h.type("已有文字");
  assert.equal(h.paste({ items: [{ kind: "string", type: "text/plain" }], files: [] }, h.text).defaultPrevented, false);
  assert.equal(h.paste(undefined, h.text).defaultPrevented, false);
  assert.equal(h.paste({ items: [clipboardEntry(new File(["text"], "notes.txt", { type: "text/plain" }))], files: [] }, h.text).defaultPrevented, false);
  assert.equal(h.paste({ items: [{ kind: "string", type: "text/plain" }, clipboardEntry(photo())], files: [] }, h.text).defaultPrevented, true);
  assert.equal(h.text.value, "已有文字"); assert.equal(h.previews.length, 1); assert.equal(h.calls.length, 0);
});
await test("desktop paste button falls back to Ctrl+V when API or secure context is unavailable", () => {
  for (const secure of [false, true]) {
    const h = harness(false); let reads = 0; h.runtime.window.isSecureContext = secure;
    if (!secure) h.runtime.navigator.clipboard = { read() { reads++; throw new Error("Should not read on insecure context"); } };
    h.button("粘贴图片").click(); assert.equal(reads, 0); assert.equal(h.text.focused, true); assert.match(h.root.textContent, /Ctrl\+V/); assert.equal(h.calls.length, 0);
  }
  assert.equal(harness(true).button("粘贴图片"), undefined);
});
await test("clipboard read blocks duplicate paste and submit, prefers one image flavor and stages only", async () => {
  const h = harness(false), pending = defer(); let reads = 0; const requested = [];
  h.runtime.window.isSecureContext = true; h.runtime.navigator.clipboard = { read() { reads++; return pending.promise; } }; h.type("读取时保留");
  const pasteButton = h.button("粘贴图片"); pasteButton.click(); assert.equal(reads, 1); assert.equal(pasteButton.disabled, true); assert.equal(h.button("发送").disabled, true);
  pasteButton.click(); await h.send(); h.paste({ files: [photo("while-reading.png")] }); assert.equal(reads, 1); assert.equal(h.previews.length, 0); assert.equal(h.calls.length, 0);
  pending.resolve([{ types: ["text/html", "image/jpeg", "image/png"], async getType(type) { requested.push(type); return new Blob(["screenshot"], { type }); } }]); await settle();
  assert.deepEqual(requested, ["image/png"]); assert.equal(h.previews.length, 1); assert.match(h.previews[0].file.name, /\.png$/); assert.equal(h.button("粘贴图片").disabled, false);
  assert.equal(h.button("上传并发送").disabled, false); assert.equal(h.text.value, "读取时保留"); assert.equal(h.calls.length, 0);
});
await test("empty or denied clipboard reads preserve selected originals and enable retry", async () => {
  for (const denied of [false, true]) {
    const h = harness(false); h.select(photo("keep.png")); h.type("keep text"); h.runtime.window.isSecureContext = true;
    h.runtime.navigator.clipboard = { async read() { if (denied) throw new Error("Permission denied"); return [{ types: ["text/plain"], getType() { throw new Error("No image type should be read"); } }]; } };
    h.button("粘贴图片").click(); await settle();
    assert.equal(h.previews.length, 1); assert.equal(h.all("img").length, 1); assert.equal(h.text.value, "keep text"); assert.equal(h.button("粘贴图片").disabled, false); assert.equal(h.button("上传并发送").disabled, false);
    assert.match(h.root.textContent, denied ? /无法读取剪贴板.*Ctrl\+V/ : /剪贴板里没有图片/); if (denied) assert.equal(h.text.focused, true);
    assert.equal(h.calls.length, 0); assert.deepEqual(h.revoked, []);
  }
});
await test("a revoked generation discards late clipboard image results", async () => {
  const h = harness(false), pending = defer(); h.select(photo("keep.png")); h.type("未发送"); h.runtime.window.isSecureContext = true;
  h.runtime.navigator.clipboard = { read: () => pending.promise }; h.button("粘贴图片").click(); h.panel.clear();
  pending.resolve([{ types: ["image/png"], async getType() { return new Blob(["late"], { type: "image/png" }); } }]); await settle();
  assert.equal(h.previews.length, 1); assert.equal(h.all("img").length, 0); assert.deepEqual(h.revoked, ["blob:0"]); assert.equal(h.text.value, "未发送");
  assert.equal(h.button("粘贴图片").disabled, false); assert.equal(h.calls.length, 0); assert.doesNotMatch(h.root.textContent, /已粘贴/);
});
await test("paste events and clipboard button do not change an in-flight upload", async () => {
  const h = harness(false), pending = defer(); let reads = 0; h.select(photo("upload.png")); h.type("正在发的说明");
  h.runtime.window.isSecureContext = true; h.runtime.navigator.clipboard = { async read() { reads++; return []; } }; h.answers.push(pending.promise); const sending = h.send();
  h.paste({ files: [photo("late.png")] }, h.text); h.button("粘贴图片").click();
  assert.equal(reads, 0); assert.equal(h.previews.length, 1); assert.equal(h.calls.length, 1); assert.equal(h.calls[0].options.body.getAll("files").length, 1);
  pending.resolve(response({ error: "retry" }, 503)); await sending; assert.equal(h.text.value, "正在发的说明"); assert.equal(h.all("img").length, 1);
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
await test("desktop and phone star actions use authenticated JSON and synchronize revisions", async () => {
  for (const phone of [false, true]) {
    const h = harness(phone), original = message("star-me", phone); h.respond(historyPage([original])); h.panel.setActive(true); await settle();
    assert.equal(starFor(h, "star-me").textContent, "☆"); assert.equal(starFor(h, "star-me").attributes["aria-pressed"], "false");
    h.respond(historyPage([{ ...original, starred: true }], "starred-revision")); starFor(h, "star-me").click(); await settle();
    const call = h.calls[1]; assert.equal(call.url, `${phone ? "/api/phone" : "/api"}/transfer/star`); assert.equal(call.options.method, "POST"); assert.equal(call.options.headers["Content-Type"], "application/json");
    assert.equal(call.options.credentials, "same-origin"); assert.equal(call.options.redirect, "error"); assert.equal(call.options.headers["X-Codex-Phone"], phone ? "1" : undefined);
    assert.deepEqual(JSON.parse(call.options.body), { id: "star-me", starred: true }); assert.equal(starFor(h, "star-me").textContent, "★"); assert.equal(starFor(h, "star-me").attributes["aria-pressed"], "true");
    const timer = [...h.timers.values()].find(timer => timer.delay === 4000); h.respond(historyPage([original], "another-device-unstarred")); timer.fn(); await settle();
    assert.match(h.calls[2].url, /revision=starred-revision/); assert.equal(starFor(h, "star-me").textContent, "☆"); assert.equal(h.calls.filter(call => call.options.method === "POST").length, 1);
    h.respond(historyPage([{ ...original, starred: true }], "r4")); await h.panel.refresh(); h.respond(historyPage([original], "r5")); starFor(h, "star-me").click(); await settle();
    assert.deepEqual(JSON.parse(h.calls.at(-1).options.body), { id: "star-me", starred: false });
  }
});
await test("single delete is explicitly confirmed and only targets its message while preserving drafts", async () => {
  const h = harness(false), keep = { ...message("keep", false), starred: true }; h.respond(historyPage([message("delete-me", false), keep])); h.panel.setActive(true); await settle(); h.select(photo("draft.png")); h.type("待发送草稿");
  h.all("button", cardFor(h, "delete-me")).find(button => button.textContent === "删除").click(); assert.equal(h.calls.length, 1); assert.match(cardFor(h, "delete-me").textContent, /删除这条记录及其互传附件/);
  h.button("取消").click(); assert.equal(h.calls.length, 1); assert.equal(h.button("确认删除"), undefined);
  h.all("button", cardFor(h, "delete-me")).find(button => button.textContent === "删除").click(); h.respond(historyPage([keep], "deleted")); h.button("确认删除").click(); await settle();
  assert.equal(h.calls[1].url, "/api/transfer/delete"); assert.deepEqual(JSON.parse(h.calls[1].options.body), { id: "delete-me" }); assert.equal(cardFor(h, "delete-me"), undefined); assert.ok(cardFor(h, "keep"));
  assert.equal(h.text.value, "待发送草稿"); assert.equal(h.previews.length, 1); assert.deepEqual(h.revoked, []); assert.equal(h.button("上传并发送").disabled, false);
});
await test("default clear applies to all pages and preserves starred records beyond the loaded page", async () => {
  const h = harness(), newer = message("new"), starred = { ...message("visible-star"), starred: true }, oldStar = { ...message("older-star"), starred: true };
  h.respond(historyPage([newer, starred], "before-clear", true)); h.panel.setActive(true); await settle(); h.select(photo("pending.png")); h.type("未发送");
  h.button("清空记录").click(); assert.match(h.root.textContent, /尚未展开的较早记录/); assert.equal(h.calls.length, 1);
  h.respond({ ...historyPage([starred, oldStar], "after-clear"), removedCount: 78, preservedStarredCount: 2 }); h.button("确认清空未标星").click(); await settle();
  assert.deepEqual(JSON.parse(h.calls[1].options.body), { mode: "unstarred" }); assert.equal(h.calls[1].url, "/api/phone/transfer/clear");
  assert.equal(cardFor(h, "new"), undefined); assert.ok(cardFor(h, "older-star")); assert.equal(h.all("article").length, 2); assert.equal(h.button("较早记录").hidden, true);
  assert.match(h.root.textContent, /78 条未标星记录，保留 2 条星标记录/); assert.equal(h.text.value, "未发送"); assert.deepEqual(h.revoked, []); assert.equal(h.previews.length, 1);
  const timer = [...h.timers.values()].find(timer => timer.delay === 4000); h.respond({ unchanged: true, revision: "after-clear" }); timer.fn(); await settle(); assert.match(h.calls[2].url, /revision=after-clear/);
});
await test("clear-all requires choosing the destructive mode and its separate confirmation", async () => {
  const h = harness(false); h.respond(historyPage([{ ...message("starred", false), starred: true }], "r1", true)); h.panel.setActive(true); await settle();
  h.button("清空记录").click(); assert.ok(h.button("确认清空未标星")); h.button("全部清空").click(); assert.equal(h.calls.length, 1); assert.match(h.root.textContent, /包括星标和较早记录.*无法撤销/);
  assert.equal(h.button("确认清空未标星"), undefined); h.button("保留星标").click(); assert.ok(h.button("确认清空未标星")); assert.equal(h.calls.length, 1);
  h.button("全部清空").click(); h.respond({ ...historyPage([], "empty"), removedCount: 80, preservedStarredCount: 0 }); h.button("确认全部清空").click(); await settle();
  assert.equal(h.calls[1].url, "/api/transfer/clear"); assert.deepEqual(JSON.parse(h.calls[1].options.body), { mode: "all" }); assert.equal(h.all("article").length, 0); assert.equal(h.button("清空记录").disabled, true);
});
await test("history mutations block duplicate actions and accidental draft upload", async () => {
  const h = harness(false), original = message("busy", false), pending = defer(); h.respond(historyPage([original])); h.panel.setActive(true); await settle(); h.select(photo("pending.png")); h.type("不能自动发送");
  const star = starFor(h, "busy"); h.answers.push(pending.promise); star.click(); star.click(); await h.send(); await h.panel.refresh(); h.button("清空记录").click();
  assert.equal(h.calls.length, 2); assert.equal(h.button("上传并发送").disabled, true); assert.equal(h.button("清空记录").disabled, true); assert.equal(starFor(h, "busy").disabled, true); assert.equal(h.button("确认清空未标星"), undefined);
  pending.resolve(response(historyPage([{ ...original, starred: true }], "done"))); await settle(); assert.equal(h.text.value, "不能自动发送"); assert.deepEqual(h.revoked, []); assert.equal(h.button("上传并发送").disabled, false);
  assert.equal(h.calls.filter(call => /\/messages$/.test(call.url) && call.options.method === "POST").length, 0);
});
await test("failed history cleanup retains records, selected files and an upload retry UUID", async () => {
  const h = harness(false); h.respond(historyPage([message("keep", false)])); h.panel.setActive(true); await settle(); h.select(photo("retry.png")); h.type("retry draft"); h.respond({ error: "upload failed" }, 503); await h.send();
  const retryId = h.calls[1].options.body.get("requestId"); h.button("清空记录").click(); h.respond({ error: "cleanup failed" }, 503); h.button("确认清空未标星").click(); await settle();
  assert.ok(cardFor(h, "keep")); assert.match(h.root.textContent, /cleanup failed/); assert.equal(h.text.value, "retry draft"); assert.deepEqual(h.revoked, []);
  h.respond({ message: message("sent", false) }); await h.send(); assert.equal(h.calls[3].options.body.get("requestId"), retryId); assert.equal(h.calls[3].options.body.get("files").name, "retry.png");
});
await test("a stale history poll cannot restore deleted records after cleanup", async () => {
  const h = harness(), original = message("old"), pending = defer(); h.respond(historyPage([original])); h.panel.setActive(true); await settle();
  h.answers.push(pending.promise); const polling = h.panel.refresh(); h.button("清空记录").click(); h.respond(historyPage([], "cleared")); h.button("确认清空未标星").click(); await settle();
  pending.resolve(response(historyPage([original], "old-poll"))); await polling; assert.equal(h.all("article").length, 0); assert.equal(h.authCount(), 0);
});
await test("unauthorized and late history mutations respect private clear without losing original draft files", async () => {
  const h = harness(), original = message("private"); h.respond(historyPage([original])); h.panel.setActive(true); await settle(); h.select(photo("keep.png")); h.type("仍可重试");
  h.respond({ error: "pairing expired" }, 401); starFor(h, "private").click(); await settle(); assert.equal(h.authCount(), 1); assert.equal(h.all("article").length, 0); assert.equal(h.text.value, "仍可重试");
  h.respond({ message: message("sent") }); await h.send(); assert.equal(h.calls[2].options.body.get("files").name, "keep.png");
  const other = harness(false), pending = defer(); other.respond(historyPage([message("old", false)])); other.panel.setActive(true); await settle(); other.answers.push(pending.promise); starFor(other, "old").click(); other.panel.clear();
  pending.resolve(response(historyPage([{ ...message("old", false), starred: true }], "late"))); await settle(); assert.equal(other.all("article").length, 0); assert.equal(other.authCount(), 0);
});
await test("hasDraft protects text, selected originals and in-flight operations during application updates", async () => {
  const h = harness(false); assert.equal(h.panel.hasDraft(), false); h.type("   "); assert.equal(h.panel.hasDraft(), false); h.type("unsent"); assert.equal(h.panel.hasDraft(), true); h.type("");
  h.select(photo()); assert.equal(h.panel.hasDraft(), true); h.panel.clear(); assert.equal(h.panel.hasDraft(), true); h.button("移除").click(); assert.equal(h.panel.hasDraft(), false);
  const clipboard = defer(); h.runtime.window.isSecureContext = true; h.runtime.navigator.clipboard = { read: () => clipboard.promise }; h.button("粘贴图片").click(); assert.equal(h.panel.hasDraft(), true); clipboard.resolve([]); await settle(); assert.equal(h.panel.hasDraft(), false);
  h.respond(historyPage([message("star", false)])); h.panel.setActive(true); await settle(); const mutation = defer(); h.answers.push(mutation.promise); starFor(h, "star").click(); assert.equal(h.panel.hasDraft(), true);
  mutation.resolve(response(historyPage([{ ...message("star", false), starred: true }], "updated"))); await settle(); assert.equal(h.panel.hasDraft(), false);
  h.type("send"); const upload = defer(); h.answers.push(upload.promise); const sending = h.send(); assert.equal(h.panel.hasDraft(), true); upload.resolve(response({ message: message("sent", false) })); await sending; assert.equal(h.panel.hasDraft(), false);
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
