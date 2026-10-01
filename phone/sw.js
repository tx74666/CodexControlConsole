"use strict";
importScripts("./store.js");
const VERSION = "__CONSOLE_PHONE_VERSION__";
const BUILD = "__CONSOLE_PHONE_BUILD__";
const PREFIX = "codex-console-phone-shell-" + encodeURIComponent(new URL(self.registration.scope).pathname) + "-";
const CACHE = PREFIX + VERSION + "-" + BUILD;
const SHELL = ["./", "./index.html", "./styles.css", "./app.js", "./store.js", "./manifest.webmanifest", "./codex-resource-icon-128.png", "./codex-resource-icon-256.png", "./music-catalog.json", "./version.json"];
self.addEventListener("install", event => event.waitUntil((async () => { const cache = await caches.open(CACHE); await cache.addAll(SHELL); if (!self.registration.active) await self.skipWaiting(); })()));
self.addEventListener("activate", event => event.waitUntil((async () => { for (const key of await caches.keys()) if (key.startsWith(PREFIX) && key !== CACHE) await caches.delete(key); await self.clients.claim(); })()));
self.addEventListener("message", event => { if (event.data?.type === "APPLY_UPDATE") void self.skipWaiting(); });
function rangeParts(range, size) {
  if (!range) return null;
  const match = /^bytes=(\d*)-(\d*)$/.exec(range);
  if (!match || (!match[1] && !match[2]) || !size) throw new Error("range");
  let start, end;
  if (!match[1]) { const count = Number(match[2]); if (!Number.isSafeInteger(count) || count < 1) throw new Error("range"); start = Math.max(0, size - count); end = size - 1; }
  else { start = Number(match[1]); end = match[2] ? Number(match[2]) : size - 1; }
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 0 || start >= size || end < start) throw new Error("range");
  return { start, end: Math.min(end, size - 1) };
}
async function localAudio(request, id) {
  if (!["GET", "HEAD"].includes(request.method)) return new Response(null, { status: 405 });
  let media;
  try { media = await PhoneStore.get("media", id); } catch { return new Response(null, { status: 503 }); }
  if (!media?.blob || !Number.isFinite(media.blob.size)) return new Response(null, { status: 404 });
  const blob = media.blob, headers = new Headers({ "Content-Type": blob.type || media.type || "application/octet-stream", "Accept-Ranges": "bytes", "Cache-Control": "no-store" });
  let range;
  try { range = rangeParts(request.headers.get("Range"), blob.size); }
  catch { headers.set("Content-Range", `bytes */${blob.size}`); return new Response(null, { status: 416, headers }); }
  if (range) { const size = range.end - range.start + 1; headers.set("Content-Length", String(size)); headers.set("Content-Range", `bytes ${range.start}-${range.end}/${blob.size}`); return new Response(request.method === "HEAD" ? null : blob.slice(range.start, range.end + 1, blob.type), { status: 206, headers }); }
  headers.set("Content-Length", String(blob.size)); return new Response(request.method === "HEAD" ? null : blob, { headers });
}
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url), scope = new URL(self.registration.scope);
  if (url.origin !== scope.origin || !url.pathname.startsWith(scope.pathname)) return;
  const relative = url.pathname.slice(scope.pathname.length);
  if (relative.startsWith("audio/")) {
    let id; try { id = decodeURIComponent(relative.slice(6)); } catch { event.respondWith(new Response(null, { status: 400 })); return; }
    event.respondWith(localAudio(event.request, id)); return;
  }
  if (event.request.method !== "GET") return;
  if (relative === "version.json" && event.request.cache === "no-store") { event.respondWith(fetch(event.request)); return; }
  event.respondWith((async () => { const cache = await caches.open(CACHE), cached = await cache.match(event.request, { ignoreSearch: true }); if (cached) return cached; if (event.request.mode === "navigate") return await cache.match("./index.html") || new Response("首次使用需要联网保存程序。", { status: 503 }); return fetch(event.request); })());
});
