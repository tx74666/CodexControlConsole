/* A single saved idea moves through a paired LAN tab. No Chat or Work sender. */
(() => {
  "use strict";
  const PUBLIC_ORIGIN = "https://tx74666.github.io", PROTOCOL = "codex-console-idea-handoff-v1";
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/, ID = /^[a-f0-9]{32}$/, HASH = /^[a-f0-9]{64}$/;
  const mimeTypes = new Set(["image/png", "image/jpeg", "image/gif", "image/webp"]);
  const fail = message => { throw new Error(message); };
  const exact = (value, fields) => value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).length === fields.length && fields.every(key => Object.prototype.hasOwnProperty.call(value, key));
  const positive = value => Number.isSafeInteger(value) && value > 0;
  const string = (value, limit) => typeof value === "string" && value.length <= limit && !value.includes("\0");
  const digest = async blob => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await blob.arrayBuffer())), byte => byte.toString(16).padStart(2, "0")).join("");
  function newNonce() { if (typeof crypto?.getRandomValues !== "function") fail("浏览器无法生成安全交接凭据，内容仍保留。"); const bytes = crypto.getRandomValues(new Uint8Array(16)); bytes[6] = bytes[6] & 15 | 64; bytes[8] = bytes[8] & 63 | 128; const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join(""); return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`; }
  function decode(text) {
    if (typeof text !== "string" || new TextEncoder().encode(text).length > 80000) fail("单条想法内容无效或超过 80 KB，手机副本仍保留。");
    let value; try { value = JSON.parse(text); } catch { fail("想法包正文无法读取。"); }
    if (!exact(value, ["format", "version", "source", "idea", "images"]) || value.format !== "codex-console-idea" || value.version !== 1 || !exact(value.source, ["clientId", "ideaId", "revision"]) || !UUID.test(value.source.clientId) || !ID.test(value.source.ideaId) || !positive(value.source.revision)) fail("想法包的来源或版本无效。");
    const idea = value.idea;
    if (!exact(idea, ["title", "body", "executionDraft", "archived", "keyPoints"]) || !string(idea.title, 160) || !idea.title.trim() || !string(idea.body, 20000) || !string(idea.executionDraft, 20000) || typeof idea.archived !== "boolean" || !Array.isArray(idea.keyPoints) || idea.keyPoints.length > 100) fail("想法包内容无效。");
    const points = new Set(); for (const point of idea.keyPoints) { if (!exact(point, ["id", "text", "kind"]) || !ID.test(point.id) || points.has(point.id) || !string(point.text, 2000) || !point.text.trim() || !["suggestion", "decision"].includes(point.kind)) fail("长期要点无效。"); points.add(point.id); }
    if (!Array.isArray(value.images) || value.images.length > 4) fail("每条想法最多带四张图片。");
    let total = 0; const images = new Set();
    for (const item of value.images) { if (!exact(item, ["id", "name", "mimeType", "size", "sha256"]) || !ID.test(item.id) || images.has(item.id) || !string(item.name, 160) || !item.name || item.name !== item.name.trim() || [".", ".."].includes(item.name) || /[\\/\u0000-\u001f\u007f]/.test(item.name) || !mimeTypes.has(item.mimeType) || !positive(item.size) || item.size > 8 * 1024 * 1024 || !HASH.test(item.sha256)) fail("图片来源、大小或校验值无效。"); total += item.size; images.add(item.id); }
    if (total > 24 * 1024 * 1024) fail("图片总大小超过 24 MB。");
    return value;
  }
  async function verify(text, files, checkHash = true) {
    const manifest = decode(text);
    if (!Array.isArray(files) || files.length !== manifest.images.length) fail("图片文件尚未完整取得，手机副本仍保留。");
    for (let index = 0; index < files.length; index++) { const file = files[index], item = manifest.images[index]; if (!(file instanceof Blob) || file.size !== item.size || file.type !== item.mimeType || checkHash && await digest(file) !== item.sha256) fail("图片字节与已保存校验值不同，未交给电脑。"); }
    return manifest;
  }
  function verifyReceipt(receipt, exported) {
    const source = decode(exported.text).source, imported = receipt?.imported, idea = receipt?.idea;
    if (receipt?.requestId !== exported.requestId || !imported || !exact(imported.source, ["clientId", "ideaId", "revision"]) || Object.keys(source).some(key => imported.source[key] !== source[key]) || !HASH.test(imported.sourceHash || "") || !ID.test(imported.ideaId || "") || idea?.id !== imported.ideaId || !positive(imported.destinationRevision) || !positive(idea?.revision) || imported.destinationRevision > idea.revision || !ID.test(idea?.workflowRecordId || "") || receipt?.detail?.record?.id !== idea.workflowRecordId) fail("电脑回执与本条想法不一致，结果待核对；手机副本仍保留。");
    return receipt;
  }
  async function importExported(exported) {
    if (!UUID.test(exported?.requestId || "")) fail("交接编号无效。");
    // This HTTP page checks shape and size; the paired server verifies actual hashes.
    const manifest = await verify(exported.text, exported.files, false), form = new FormData(); form.append("requestId", exported.requestId); form.append("text", exported.text); manifest.images.forEach((item, index) => form.append("files", exported.files[index], item.name));
    const controller = new AbortController(), timeout = window.setTimeout(() => controller.abort(), 30000);
    try { const response = await fetch("/api/phone/workflow/mobile/idea/import", { method: "POST", credentials: "same-origin", mode: "same-origin", redirect: "error", cache: "no-store", headers: { Accept: "application/json", "X-Codex-Phone": "1" }, body: form, signal: controller.signal }); const result = await response.json(); if (!response.ok) throw Object.assign(new Error(result.error || `电脑未导入（${response.status}）`), { code: result.code, status: response.status, serverRejected: response.status >= 400 && response.status < 500 }); return verifyReceipt(result, exported); }
    finally { window.clearTimeout(timeout); }
  }
  async function lookupExported(exported) {
    if (!UUID.test(exported?.requestId || "")) fail("交接编号无效。"); decode(exported.text);
    const controller = new AbortController(), timeout = window.setTimeout(() => controller.abort(), 15000);
    try { const response = await fetch("/api/phone/workflow/mobile/idea/import-status", { method: "POST", credentials: "same-origin", mode: "same-origin", redirect: "error", cache: "no-store", headers: { Accept: "application/json", "Content-Type": "application/json", "X-Codex-Phone": "1" }, body: JSON.stringify({ requestId: exported.requestId, text: exported.text }), signal: controller.signal }); const result = await response.json(); if (!response.ok) throw Object.assign(new Error(result.error || `原交接暂时无法核对（${response.status}）`), { code: result.code, status: response.status }); if (result.found === true) return verifyReceipt(result, exported); const source = decode(exported.text).source; if (result.found !== false || result.requestId !== exported.requestId || !HASH.test(result.sourceHash || "") || !exact(result.source, ["clientId", "ideaId", "revision"]) || Object.keys(source).some(key => result.source[key] !== source[key])) fail("原交接查询回执与冻结来源不一致。"); return result; }
    finally { window.clearTimeout(timeout); }
  }
  async function encodePack(exported) {
    if (exported.attemptedAt) fail("这条版本已经尝试交接，请先核对原回执；不能生成另一份重送包。");
    await verify(exported.text, exported.files); if (!UUID.test(exported.requestId || "")) fail("交接编号无效。");
    const images = [];
    for (let index = 0; index < exported.files.length; index++) { const bytes = new Uint8Array(await exported.files[index].arrayBuffer()); let binary = ""; for (let start = 0; start < bytes.length; start += 32768) binary += String.fromCharCode(...bytes.subarray(start, start + 32768)); images.push({ id: decode(exported.text).images[index].id, base64: btoa(binary) }); }
    const blob = new Blob([JSON.stringify({ format: "codex-console-idea-pack", version: 1, requestId: exported.requestId, text: exported.text, images })], { type: "application/json" });
    if (blob.size > 34 * 1024 * 1024) fail("完整想法包超过 34 MB，原内容仍保留。"); return blob;
  }
  async function decodePack(file) {
    if (!(file instanceof Blob) || file.size > 34 * 1024 * 1024 || !file.size) fail("请选择小于 34 MB 的完整手机想法包。");
    let pack; try { pack = JSON.parse(await file.text()); } catch { fail("完整想法包无法读取，原资料保留。"); }
    if (!exact(pack, ["format", "version", "requestId", "text", "images"]) || pack.format !== "codex-console-idea-pack" || pack.version !== 1 || !UUID.test(pack.requestId || "") || !Array.isArray(pack.images)) fail("完整想法包结构无效。");
    const manifest = decode(pack.text); if (pack.images.length !== manifest.images.length) fail("完整想法包图片不齐。");
    const files = pack.images.map((item, index) => { const image = manifest.images[index]; if (!exact(item, ["id", "base64"]) || item.id !== image.id || typeof item.base64 !== "string" || item.base64.length > Math.ceil(image.size / 3) * 4 || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(item.base64)) fail("完整想法包图片编码无效。"); let binary; try { binary = atob(item.base64); } catch { fail("完整想法包图片无法解码。"); } if (binary.length !== image.size) fail("完整想法包图片大小不一致。"); return new Blob([Uint8Array.from(binary, char => char.charCodeAt(0))], { type: image.mimeType }); });
    await verify(pack.text, files, false); return { requestId: pack.requestId, text: pack.text, files };
  }
  function targetAddress(address) {
    let url; try { url = new URL(address); } catch { fail("先扫码记住电脑 Console 的地址，再带到电脑。"); }
    const parts = url.hostname.split(".").map(Number), privateAddress = parts.length === 4 && parts.every(value => Number.isInteger(value) && value >= 0 && value <= 255) && (parts[0] === 10 || parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31 || parts[0] === 192 && parts[1] === 168), named = /^codex-[a-z0-9]{8,64}\.local$/.test(url.hostname);
    if (url.protocol !== "http:" || !(privateAddress || named) || url.username || url.password || url.hash || !["/", "/mobile.html"].includes(url.pathname) || url.search && url.search !== "?tab=transfer") fail("请使用已保存的电脑 Console 同 Wi-Fi 地址。");
    return new URL("/mobile.html?tab=work&workView=dialogue", url.origin);
  }
  function createSender(options) {
    let busy = false;
    function reserve() {
      if (busy) fail("上一条交接还在核对，请稍候。");
      if (window.location.origin !== PUBLIC_ORIGIN) fail("请从正式手机入口交接，当前内容仍在此设备。");
      const target = targetAddress(options.getAddress()), popup = window.open("about:blank", "_blank");
      if (!popup) fail("浏览器没有保留交接标签页；内容仍在手机，可导出完整想法包。");
      return { popup, target, nonce: newNonce() };
    }
    async function send(reservation, ideaId, revision, retryPending = false) {
      if (busy || !reservation?.popup || !UUID.test(reservation.nonce)) fail("无法开始这次交接，手机副本仍保留。");
      busy = true; let listener, timer, exported;
      try {
        exported = retryPending ? await options.buildPendingExport(ideaId) : await options.buildExport(ideaId, revision); await verify(exported.text, exported.files);
        if (!UUID.test(exported.requestId)) fail("交接凭据无效。");
        if (exported.destinationOrigin && exported.destinationOrigin !== reservation.target.origin) fail("这次交接已绑定另一台电脑入口，未向当前电脑传送；原内容和回执保留。");
        const readOnly = retryPending || ["pending", "completed"].includes(exported.status);
        const receipt = await new Promise((resolve, reject) => {
          let sent = false, challenge = "", expired = false;
          listener = async event => {
            if (event.source !== reservation.popup || event.origin !== reservation.target.origin || event.data?.protocol !== PROTOCOL || event.data.nonce !== reservation.nonce) return;
            const message = event.data;
            if (message.type === "ready" && !sent && UUID.test(message.challenge || "")) {
              sent = true; challenge = message.challenge;
              try { if (!readOnly) { if (typeof options.markAttempted !== "function") fail("手机无法持久保存交接尝试，尚未传送。"); await options.markAttempted(exported, reservation.target.origin); } if (expired) return; reservation.popup.postMessage({ protocol: PROTOCOL, type: readOnly ? "status" : "import", nonce: reservation.nonce, challenge, requestId: exported.requestId, text: exported.text, ...(!readOnly ? { files: exported.files } : {}) }, reservation.target.origin); } catch (error) { reject(error); }
            } else if (sent && message.challenge === challenge && message.type === "receipt") {
              try { resolve(verifyReceipt(message.receipt, exported)); } catch (error) { reject(error); }
            } else if (sent && readOnly && message.challenge === challenge && message.type === "not_found" && message.requestId === exported.requestId) reject(new Error("电脑尚未找到原交接回执，原版本仍待核对；本次没有重送内容。"));
            else if (message.type === "error" && (!sent || message.challenge === challenge)) {
              const verifiedRejection = !readOnly && sent && message.serverRejected === true && ([400, 413, 415, 429].includes(message.status) || message.status === 409 && ["import_source_conflict", "import_revision_conflict", "import_conflict"].includes(message.code));
              reject(Object.assign(new Error(message.message || "电脑未能确认导入，手机副本和交接凭据仍保留。"), { verifiedRejection, status: message.status, code: message.code }));
            }
          };
          window.addEventListener("message", listener);
          timer = window.setTimeout(() => { expired = true; reject(new Error("尚未取得电脑的实际回执，手机副本和原交接编号已保留；可再次点带到电脑核对。")); }, Math.min(options.timeoutMs || 60000, 90000));
          reservation.target.searchParams.set("ideaHandoff", reservation.nonce);
          try { reservation.popup.location.href = reservation.target.href; } catch (error) { reject(error); }
        });
        await options.saveReceipt(exported, receipt);
        return receipt;
      } catch (error) { if (error.verifiedRejection && exported && options.saveRejected) await options.saveRejected(exported, { status: error.status, code: error.code, message: error.message }); throw error; }
      finally { busy = false; if (listener) window.removeEventListener("message", listener); if (timer) window.clearTimeout(timer); }
    }
    return { reserve, send, isBusy: () => busy };
  }
  function createReceiver(options) {
    const nonce = new URL(window.location.href).searchParams.get("ideaHandoff"), sourceWindow = window.opener;
    if (!UUID.test(nonce || "") || !sourceWindow || !["http:", "https:"].includes(window.location.protocol)) return null;
    const challenge = newNonce(); let ready = false, accepted = false, active = true, busy = false, timer;
    const reply = value => sourceWindow.postMessage({ protocol: PROTOCOL, nonce, challenge, ...value }, PUBLIC_ORIGIN);
    const listener = async event => {
      if (!active || !ready || accepted || !options.isPaired() || event.source !== sourceWindow || event.origin !== PUBLIC_ORIGIN || event.data?.protocol !== PROTOCOL || !["import", "status"].includes(event.data.type) || event.data.nonce !== nonce || event.data.challenge !== challenge) return;
      accepted = true; busy = true; const message = event.data;
      try {
        if (!UUID.test(message.requestId || "")) fail("交接编号无效。");
        // LAN HTTP may have no SubtleCrypto. Actual bytes and hashes are verified by the paired backend.
        if (message.type === "import") await verify(message.text, message.files, false); else decode(message.text);
        if (!options.isPaired()) fail("配对已断开，未导入想法。");
        const receipt = message.type === "status" ? await lookupExported(message) : await importExported(message);
        if (receipt.found === false) { reply({ type: "not_found", requestId: message.requestId }); options.onNotice?.("尚未找到原交接回执；此次只读核对，没有重送。", true); return; }
        reply({ type: "receipt", receipt });
        options.onNotice?.("已导入这条手机想法；手机原副本保留，尚未执行。");
        await options.onImported?.(receipt);
      } catch (error) { reply({ type: "error", message: error.message || "导入结果待核对，未重复发送。", code: error.code || "unverified", status: error.status, serverRejected: error.serverRejected === true }); options.onNotice?.(error.message || "导入结果待核对。", true); }
      finally { busy = false; active = false; window.removeEventListener("message", listener); window.clearTimeout(timer); }
    };
    window.addEventListener("message", listener);
    timer = window.setTimeout(() => { if (!accepted) { active = false; window.removeEventListener("message", listener); options.onNotice?.("交接标签页已超时；手机内容仍保留，请从手机再次点带到电脑。", true); } }, Math.min(options.timeoutMs || 60000, 90000));
    return { activate() { if (!active || ready || !options.isPaired()) return; ready = true; reply({ type: "ready" }); }, isBusy: () => busy, dispose() { active = false; window.removeEventListener("message", listener); window.clearTimeout(timer); } };
  }
  window.CodexMobileHandoff = { PUBLIC_ORIGIN, decode, verify, verifyReceipt, digest, targetAddress, encodePack, decodePack, importExported, lookupExported, createSender, createReceiver };
})();
