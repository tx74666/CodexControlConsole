#!/usr/bin/env node
// Isolated camera lifecycle tests: no actual camera, pairing or network request.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { spawnSync } from "node:child_process";
import { File } from "node:buffer";
const source = readFileSync(new URL("../phone/connection-qr.js", import.meta.url), "utf8");
const settle = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
function harness() {
  const timers = new Map(), events = new Map(), cameraCalls = [], stopped = [], notices = [], results = [], decoded = [], revoked = []; let nextTimer = 1;
  const track = { stop() { stopped.push(true); } }, stream = { getTracks: () => [track] };
  const video = { readyState: 0, videoWidth: 1280, videoHeight: 720, srcObject: null, async play() {}, pause() {} };
  const canvas = { width: 0, height: 0, getContext() { return { drawImage() {}, getImageData() { return { data: new Uint8ClampedArray(canvas.width * canvas.height * 4), width: canvas.width, height: canvas.height }; } }; } };
  const document = { hidden: false, addEventListener(name, handler) { events.set(name, handler); }, createElement() { const image = { naturalWidth: 800, naturalHeight: 600, removeAttribute() {} }; Object.defineProperty(image, "src", { set() { Promise.resolve().then(() => image.onload?.()); } }); return image; } };
  class BrowserURL extends URL { static createObjectURL() { return "blob:qr-photo"; } static revokeObjectURL(value) { revoked.push(value); } }
  const runtime = { document, URL: BrowserURL, navigator: { mediaDevices: { async getUserMedia(options) { cameraCalls.push(options); return await (runtime.cameraPromise || stream); } } }, window: { setTimeout(fn, delay) { const id = nextTimer++; timers.set(id, { fn, delay }); return id; }, clearTimeout(id) { timers.delete(id); }, addEventListener(name, handler) { events.set(name, handler); }, jsQR(data, width, height) { decoded.push({ width, height }); return runtime.qrValue ? { data: runtime.qrValue } : null; } } };
  runInNewContext(source, runtime);
  const scanner = runtime.window.CodexPhoneQrScanner.create({ video, canvas, onNotice(message, error) { notices.push({ message, error }); }, async onResult(value) { results.push(value); if (runtime.resultError) throw runtime.resultError; } });
  return { scanner, runtime, video, canvas, document, cameraCalls, stopped, notices, results, decoded, revoked, timers, events, stream };
}
let count = 0;
async function test(name, run) { await run(); console.log(`PASS ${name}`); count++; }
await test("camera stays off until explicit scan, and stops on close", async () => {
  const h = harness(); assert.equal(h.cameraCalls.length, 0); assert.equal(h.video.srcObject, null);
  await h.scanner.start(); assert.equal(h.cameraCalls.length, 1); assert.equal(h.cameraCalls[0].audio, false); assert.equal(h.video.playsInline, true); assert.equal(h.video.muted, true);
  h.scanner.stop(); assert.equal(h.stopped.length, 1); assert.equal(h.video.srcObject, null); assert.equal(h.timers.size, 0);
});
await test("permission resolving after cancellation cannot reopen camera", async () => {
  const h = harness(), pending = deferred(); h.runtime.cameraPromise = pending.promise; const start = h.scanner.start();
  h.scanner.stop(); pending.resolve(h.stream); await start; assert.equal(h.stopped.length, 1); assert.equal(h.video.srcObject, null); assert.equal(h.timers.size, 0);
});
await test("Safari jsQR fallback decodes bounded frames and stops before navigation", async () => {
  const h = harness(); h.video.readyState = 2; h.runtime.qrValue = "http://codex-0123456789abcdef.local:8899/?tab=transfer#qrToken=" + "q".repeat(43);
  await h.scanner.start(); await settle(); assert.equal(h.results.length, 1); assert.equal(h.stopped.length, 1); assert.equal(h.video.srcObject, null); assert.ok(h.decoded[0].width <= 960); assert.ok(h.decoded[0].height <= 960);
});
await test("background and page navigation stop camera without restarting it", async () => {
  const h = harness(); await h.scanner.start(); h.document.hidden = true; h.events.get("visibilitychange")(); assert.equal(h.stopped.length, 1); assert.equal(h.timers.size, 0);
  h.document.hidden = false; h.events.get("visibilitychange")(); assert.equal(h.cameraCalls.length, 1);
  await h.scanner.start(); h.events.get("pagehide")(); assert.equal(h.stopped.length, 2); assert.equal(h.video.srcObject, null);
});
await test("permission failure and absent API leave photo fallback available", async () => {
  const h = harness(); h.runtime.cameraPromise = Promise.reject(Object.assign(new Error("denied"), { name: "NotAllowedError" })); await h.scanner.start(); assert.match(h.notices.at(-1).message, /权限|二维码照片/); assert.equal(h.video.srcObject, null);
  delete h.runtime.navigator.mediaDevices; await h.scanner.start(); assert.match(h.notices.at(-1).message, /二维码照片/);
});
await test("camera without frames times out and releases tracks", async () => {
  const h = harness(); await h.scanner.start(); const watchdog = [...h.timers.values()].find(timer => timer.delay === 10000); assert.ok(watchdog); watchdog.fn();
  assert.equal(h.stopped.length, 1); assert.match(h.notices.at(-1).message, /没有传回画面/); assert.equal(h.video.srcObject, null);
});
await test("QR image fallback decodes locally, revokes image URL and never opens camera", async () => {
  const h = harness(); h.runtime.qrValue = "http://192.168.1.2:8899/?tab=transfer#qrToken=" + "q".repeat(43);
  await h.scanner.readFile(new File(["fake-photo"], "qr.png", { type: "image/png" })); assert.equal(h.results.length, 1); assert.equal(h.cameraCalls.length, 0); assert.deepEqual(h.revoked, ["blob:qr-photo"]);
});
await test("invalid QR result stays visible and camera remains stopped", async () => {
  const h = harness(); h.video.readyState = 2; h.runtime.qrValue = "https://evil.test/"; h.runtime.resultError = new Error("不是电脑 Console 二维码");
  await h.scanner.start(); await settle(); assert.equal(h.stopped.length, 1); assert.match(h.notices.at(-1).message, /不是电脑 Console/);
});
await test("bundled official jsQR decodes a real Console pairing QR and retains license", () => {
  const decoder = {}, library = readFileSync(new URL("../phone/vendor/jsQR.js", import.meta.url), "utf8"); runInNewContext(library, decoder);
  const result = spawnSync("python", ["-c", "import qrcode,json; text='http://codex-0123456789abcdef.local:8899/?tab=transfer#qrToken='+'q'*43; qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4); qr.add_data(text); qr.make(fit=True); print(json.dumps({'text':text,'rows':[''.join('1' if v else '0' for v in row) for row in qr.get_matrix()]}))"], { encoding: "utf8", windowsHide: true });
  assert.equal(result.status, 0, result.stderr); const fixture = JSON.parse(result.stdout), side = fixture.rows.length * 5, pixels = new Uint8ClampedArray(side * side * 4);
  for (let y = 0; y < side; y++) for (let x = 0; x < side; x++) { const index = (y * side + x) * 4, value = fixture.rows[Math.floor(y / 5)][Math.floor(x / 5)] === "1" ? 0 : 255; pixels[index] = pixels[index + 1] = pixels[index + 2] = value; pixels[index + 3] = 255; }
  assert.equal(decoder.jsQR(pixels, side, side, { inversionAttempts: "dontInvert" }).data, fixture.text);
  const license = readFileSync(new URL("../phone/vendor/jsQR.LICENSE", import.meta.url), "utf8"); assert.match(license, /Apache License/);
});
console.log(`Connection QR UI checks passed (${count} cases).`);
