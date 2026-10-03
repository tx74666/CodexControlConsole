/* Camera adapter. Decoder: jsQR 1.4.0, Apache-2.0; see vendor/jsQR.LICENSE. */
(() => {
  "use strict";
  function create({ video, canvas, onResult, onNotice }) {
    let stream = null, timer = 0, watchdog = 0, generation = 0, active = false, detector = null;
    try { if (typeof BarcodeDetector === "function") detector = new BarcodeDetector({ formats: ["qr_code"] }); } catch { /* Local jsQR supports Safari. */ }
    function stop() {
      generation += 1; active = false; window.clearTimeout(timer); window.clearTimeout(watchdog); timer = watchdog = 0;
      if (stream) for (const track of stream.getTracks()) track.stop();
      stream = null; video.pause?.(); video.srcObject = null;
    }
    async function decode(source, width, height) {
      if (!width || !height) return "";
      const scale = Math.min(1, 960 / Math.max(width, height));
      canvas.width = Math.max(1, Math.round(width * scale)); canvas.height = Math.max(1, Math.round(height * scale));
      const context = canvas.getContext("2d", { willReadFrequently: true }); context.drawImage(source, 0, 0, canvas.width, canvas.height);
      if (detector) { try { const results = await detector.detect(canvas); if (results[0]?.rawValue) return results[0].rawValue; } catch { detector = null; } }
      if (typeof window.jsQR !== "function") throw new Error("扫码组件还未加载，请更新 App 后重试。");
      const image = context.getImageData(0, 0, canvas.width, canvas.height);
      return window.jsQR(image.data, image.width, image.height, { inversionAttempts: "dontInvert" })?.data || "";
    }
    async function accept(value) {
      stop();
      try { await onResult(value); } catch (error) { onNotice(error.message || "不是 Console 的连接二维码，请重新扫码。", true); }
    }
    async function scan(ticket) {
      if (!active || document.hidden || ticket !== generation) return;
      try {
        if (video.readyState >= 2) {
          const value = await decode(video, video.videoWidth, video.videoHeight); if (ticket !== generation) return;
          if (value) { await accept(value); return; }
        }
      } catch (error) { if (ticket === generation) { stop(); onNotice(error.message || "扫码失败，请重试。", true); } return; }
      if (active && ticket === generation) timer = window.setTimeout(() => void scan(ticket), 350);
    }
    async function start() {
      stop(); const ticket = generation; active = true;
      if (!navigator.mediaDevices?.getUserMedia) { active = false; onNotice("此浏览器无法开启扫码。可选二维码照片，或用 iPhone 相机扫码。", true); return; }
      onNotice("请允许使用摄像头，将电脑上的连接二维码放在取景框内。");
      try {
        const incoming = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } } });
        if (!active || document.hidden || ticket !== generation) { for (const track of incoming.getTracks()) track.stop(); return; }
        stream = incoming; video.srcObject = stream; video.muted = true; video.playsInline = true;
        watchdog = window.setTimeout(() => { if (ticket === generation && video.readyState < 2) { stop(); onNotice("摄像头没有传回画面，请重新扫码或选择二维码照片。", true); } }, 10000);
        await video.play();
        if (ticket !== generation) return;
        onNotice("正在识别电脑的连接二维码…"); void scan(ticket);
      } catch (error) { if (ticket === generation) { stop(); onNotice(error.name === "NotAllowedError" ? "摄像头权限未开启。可选二维码照片，或在 Safari 设置中允许摄像头。" : "摄像头暂时无法使用，请选择二维码照片或重试。", true); } }
    }
    async function readFile(file) {
      stop(); const ticket = generation;
      if (!file || !/^image\//.test(file.type) || file.size > 16 * 1024 ** 2) { onNotice("请选择小于 16 MB 的二维码图片。", true); return; }
      const image = document.createElement("img"), url = URL.createObjectURL(file); let timeout = 0;
      onNotice("正在识别二维码图片…");
      try {
        await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = () => reject(new Error("二维码图片无法读取。")); timeout = window.setTimeout(() => reject(new Error("二维码图片读取超时。")), 10000); image.src = url; });
        if (ticket !== generation) return;
        if (image.naturalWidth * image.naturalHeight > 32 * 1024 ** 2) throw new Error("图片尺寸过大，请选择二维码截图。");
        const value = await decode(image, image.naturalWidth, image.naturalHeight); if (ticket !== generation) return;
        if (!value) throw new Error("未找到二维码，请选择电脑连接二维码的清晰截图。");
        await accept(value);
      } catch (error) { if (ticket === generation) onNotice(error.message, true); }
      finally { window.clearTimeout(timeout); URL.revokeObjectURL(url); image.onload = image.onerror = null; image.removeAttribute("src"); }
    }
    document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); }); window.addEventListener("pagehide", stop);
    return { start, stop, readFile };
  }
  window.CodexPhoneQrScanner = { create };
})();
