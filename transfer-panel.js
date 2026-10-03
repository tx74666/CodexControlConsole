(() => {
  "use strict";
  const defaults = { maxTextChars: 20000, maxFiles: 4, maxFileBytes: 12 * 1024 ** 2, maxRequestBytes: 24 * 1024 ** 2 };
  const make = (tag, text = "", className = "") => {
    const element = document.createElement(tag);
    if (text) element.textContent = String(text);
    if (className) element.className = className;
    return element;
  };
  const size = value => value < 1024 ** 2 ? `${Math.max(1, Math.ceil(value / 1024))} KB` : `${(value / 1024 ** 2).toFixed(1)} MB`;
  function requestId() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, character => {
      const value = Math.floor(Math.random() * 16);
      return (character === "x" ? value : (value & 3) | 8).toString(16);
    });
  }
  async function copyText(text, status) {
    try {
      if (navigator.clipboard?.writeText && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        status("已复制。"); return;
      }
    } catch { /* LAN HTTP and Safari can refuse clipboard access. */ }
    const input = make("textarea", "", "transfer-copy-field"); input.value = text;
    input.readOnly = true; input.setAttribute("aria-label", "复制内容"); document.body.append(input);
    input.focus(); input.select(); input.setSelectionRange?.(0, text.length);
    let copied = false;
    try { copied = Boolean(document.execCommand?.("copy")); } catch { /* Keep selected text available for manual copy. */ }
    if (copied) { input.remove(); status("已复制。"); }
    else {
      input.className = "transfer-copy-field transfer-copy-manual";
      const close = make("button", "完成复制", "transfer-copy-close"); close.type = "button";
      close.addEventListener("click", () => { input.remove(); close.remove(); }); document.body.append(close);
      status("内容已选中，请长按复制，再点“完成复制”。");
    }
  }
  function create(root, options = {}) {
    if (!root) return null;
    const phone = Boolean(options.phone), endpoint = phone ? "/api/phone/transfer" : "/api/transfer";
    let active = false, timer = 0, reading = false, sending = false, limits = { ...defaults }, revision = "", messages = [], hasMore = false, pendingId = "", files = [], generation = 0, controller = null, uploadController = null, pollError = false;
    const header = make("div", "", "transfer-heading"), title = make("div");
    title.append(make("h2", "互传"), make("p", phone ? "选图片，点上传，电脑就能收到。" : "手机和电脑互传图片与文字。", "transfer-muted"));
    header.append(title);
    if (options.onConnection) {
      const connect = make("button", "连接手机", "transfer-button"); connect.type = "button";
      connect.addEventListener("click", options.onConnection); header.append(connect);
    }
    const form = make("form", "", "transfer-composer");
    const label = make("label", phone ? "发给电脑" : "发给手机"); label.htmlFor = `${phone ? "phone" : "desktop"}TransferText`;
    const text = make("textarea"); text.id = label.htmlFor; text.rows = 4; text.maxLength = limits.maxTextChars;
    text.placeholder = "输入或粘贴文字，也可以只上传图片"; text.setAttribute("aria-describedby", `${text.id}Notice`);
    const actions = make("div", "", "transfer-actions");
    const photos = make("input"); photos.type = "file"; photos.accept = "image/*,.heic,.heif"; photos.multiple = true; photos.hidden = true;
    const attachments = make("input"); attachments.type = "file"; attachments.accept = ".jpg,.jpeg,.png,.gif,.webp,.heic,.heif,image/jpeg,image/png,image/gif,image/webp,image/heic,image/heif"; attachments.multiple = true; attachments.hidden = true;
    const photoButton = make("button", "选择图片", "transfer-button"), fileButton = make("button", "从文件选图片", "transfer-button"), submit = make("button", "发送", "transfer-button transfer-primary");
    photoButton.type = fileButton.type = "button"; submit.type = "submit";
    photoButton.addEventListener("click", () => photos.click()); fileButton.addEventListener("click", () => attachments.click());
    actions.append(photoButton, fileButton, submit);
    const picked = make("div", "", "transfer-picked"), notice = make("p", "", "transfer-notice"); notice.id = `${text.id}Notice`; notice.setAttribute("role", "status"); notice.setAttribute("aria-live", "polite");
    const hint = make("p", "", "transfer-muted transfer-small");
    form.append(label, text, photos, attachments, picked, actions, hint, notice);
    const historyHead = make("div", "", "transfer-history-heading"), historyMeta = make("p", "收发记录", "transfer-muted"), refresh = make("button", "刷新", "transfer-button"); refresh.type = "button";
    historyHead.append(historyMeta, refresh);
    const history = make("div", "", "transfer-history"), older = make("button", "较早记录", "transfer-button transfer-older"); older.type = "button"; older.hidden = true;
    root.classList.add("transfer-panel"); root.replaceChildren(header, form, historyHead, history, older);
    function status(message = "", error = false) { notice.textContent = message; notice.dataset.error = String(error); }
    function update() {
      text.disabled = photos.disabled = attachments.disabled = photoButton.disabled = fileButton.disabled = sending;
      submit.disabled = sending || (!text.value.trim() && !files.length);
      submit.textContent = sending ? "正在上传…" : files.length ? "上传并发送" : "发送";
      refresh.disabled = reading; older.disabled = reading;
      hint.textContent = `每次最多 ${limits.maxFiles} 张图片，单张 ${size(limits.maxFileBytes)}，合计 ${size(totalFileLimit())}。原图保存在电脑，两端可下载。`;
    }
    function releaseFiles() { for (const item of files) if (item.preview) URL.revokeObjectURL(item.preview); files = []; }
    function renderPicked() {
      picked.replaceChildren();
      files.forEach((item, index) => {
        const row = make("div", "", "transfer-picked-file");
        if (item.preview) { const image = make("img"); image.src = item.preview; image.alt = item.file.name; row.append(image); }
        row.append(make("span", `${item.file.name} · ${size(item.file.size)}`));
        const remove = make("button", "移除", "transfer-button"); remove.type = "button"; remove.disabled = sending; remove.setAttribute("aria-label", `移除 ${item.file.name}`);
        remove.addEventListener("click", () => { if (sending) return; if (item.preview) URL.revokeObjectURL(item.preview); files.splice(index, 1); pendingId = ""; renderPicked(); update(); }); row.append(remove); picked.append(row);
      });
    }
    function selectFiles(input) {
      if (sending) return;
      const additions = Array.from(input.files || []); input.value = "";
      if (!additions.length) return;
      const all = [...files.map(item => item.file), ...additions];
      if (all.length > limits.maxFiles) { status(`每次最多上传 ${limits.maxFiles} 张图片。请先移除一些图片。`, true); return; }
      const unsupported = additions.find(file => !/\.(?:jpe?g|png|gif|webp|heic|heif)$/i.test(file.name));
      if (unsupported) { status(`${unsupported.name} 不是支持的图片格式。请选 JPEG、PNG、GIF、WebP 或 HEIC 图片。`, true); return; }
      const empty = additions.find(file => !file.size); if (empty) { status(`${empty.name} 是空文件，请重新选择图片。`, true); return; }
      const oversized = additions.find(file => file.size > limits.maxFileBytes);
      if (oversized) { status(`${oversized.name} 超过 ${size(limits.maxFileBytes)}，请选择较小的文件。`, true); return; }
      if (all.reduce((sum, file) => sum + file.size, 0) > totalFileLimit()) { status(`图片合计不能超过 ${size(totalFileLimit())}。`, true); return; }
      for (const file of additions) files.push({ file, preview: /^image\/(?:jpeg|png|gif|webp)$/.test(file.type) ? URL.createObjectURL(file) : "" });
      pendingId = ""; status(); renderPicked(); update();
    }
    function totalFileLimit() { return Math.max(0, limits.maxRequestBytes - 128 * 1024); }
    photos.addEventListener("change", () => selectFiles(photos)); attachments.addEventListener("change", () => selectFiles(attachments));
    text.addEventListener("input", () => { pendingId = ""; update(); });
    text.addEventListener("paste", event => {
      const items = Array.from(event.clipboardData?.files || []);
      if (items.length) { event.preventDefault(); selectFiles({ files: items, value: "" }); }
    });
    function assetUrl(value, preview = false) {
      try {
        const url = new URL(value, window.location.href);
        if (url.origin !== new URL(window.location.href).origin || url.pathname !== `${endpoint}/attachment` || !url.searchParams.get("id")) return "";
        if (preview) url.searchParams.set("preview", "1");
        return url.href;
      } catch { return ""; }
    }
    function renderHistory() {
      history.replaceChildren();
      if (!messages.length) history.append(make("p", "还没有收发记录。选图片或输入文字，然后点发送。", "transfer-empty"));
      for (const message of messages) {
        const card = make("article", "", "transfer-message"); card.dataset.sender = message.sender;
        const heading = make("div", "", "transfer-message-heading");
        const stamp = new Date(message.createdAt);
        heading.append(make("strong", message.sender === "phone" ? "手机 → 电脑" : "电脑 → 手机"), make("time", Number.isNaN(stamp.getTime()) ? "" : stamp.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })));
        card.append(heading);
        if (message.text) {
          card.append(make("p", message.text, "transfer-message-text"));
          const copy = make("button", "复制文字", "transfer-button"); copy.type = "button"; copy.addEventListener("click", () => void copyText(message.text, status)); card.append(copy);
        }
        const gallery = make("div", "", "transfer-attachments");
        for (const attachment of message.attachments || []) {
          const url = assetUrl(attachment.url); if (!url) continue;
          const item = make("div", "", "transfer-attachment");
          if (attachment.previewable) {
            const preview = assetUrl(attachment.previewUrl || attachment.url, true);
            if (preview) {
              const link = make("a"); link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer";
              const image = make("img"); image.src = preview; image.alt = attachment.name; image.loading = "lazy";
              image.addEventListener("error", () => { image.hidden = true; }); link.append(image); item.append(link);
            }
          }
          item.append(make("p", `${attachment.name} · ${size(attachment.size)}`, "transfer-file-name"));
          const download = make("a", "下载原文件", "transfer-button"); download.href = url; download.download = attachment.name; item.append(download);
          if (!phone && attachment.path) {
            const path = make("button", "复制本地路径", "transfer-button"); path.type = "button";
            path.addEventListener("click", () => void copyText(attachment.path, status)); item.append(path);
          }
          if (!phone) {
            for (const folder of [false, true]) {
              const open = make("button", folder ? "打开文件夹" : "打开文件", "transfer-button"); open.type = "button";
              open.addEventListener("click", async () => {
                if (open.disabled) return; open.disabled = true;
                try {
                  const response = await fetch("/api/transfer/open", { method: "POST", credentials: "same-origin", mode: "same-origin", redirect: "error", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: attachment.id, folder }) });
                  const result = await response.json(); if (!response.ok) throw new Error(result.error || "无法打开，请重试。");
                  status(folder ? "已在电脑打开文件夹。" : "已在电脑打开文件。");
                } catch (error) { status(error.message || "无法打开，请重试。", true); }
                finally { open.disabled = false; }
              }); item.append(open);
            }
          }
          if (!attachment.previewable && /image\//.test(attachment.mimeType)) item.append(make("p", "此格式请下载原文件查看。", "transfer-muted transfer-small"));
          gallery.append(item);
        }
        if (gallery.childElementCount) card.append(gallery); history.append(card);
      }
      historyMeta.textContent = `收发记录 · 最近 ${messages.length} 条`; older.hidden = !hasMore;
    }
    async function request(path, body, timeoutMs = 15000) {
      const abort = new AbortController(), timeout = window.setTimeout(() => abort.abort(), timeoutMs);
      const ticket = generation;
      if (!body) controller = abort; else uploadController = abort;
      try {
        const response = await fetch(`${endpoint}/${path}`, { method: body ? "POST" : "GET", credentials: "same-origin", mode: "same-origin", cache: "no-store", redirect: "error", signal: abort.signal, headers: { Accept: "application/json", ...(phone ? { "X-Codex-Phone": "1" } : {}) }, ...(body ? { body } : {}) });
        if (ticket !== generation) throw Object.assign(new Error("旧连接已取消。"), { cancelled: true });
        options.onConnectionState?.(true);
        let result;
        try { result = await response.json(); } catch { throw new Error("电脑返回的内容无法读取，请重试。"); }
        if (ticket !== generation) throw Object.assign(new Error("旧连接已取消。"), { cancelled: true });
        if (!response.ok) {
          if (response.status === 401) options.onAuth?.();
          throw new Error(result.error || `请求失败（${response.status}）。`);
        }
        return result;
      } catch (error) {
        if (ticket !== generation) throw Object.assign(new Error("旧连接已取消。"), { cancelled: true });
        if (error.name === "AbortError") { options.onConnectionState?.(false); throw new Error(body ? "上传超时。内容已保留，可重新点发送。" : "连接超时，请检查电脑与 Wi-Fi。"); }
        if (error instanceof TypeError) { options.onConnectionState?.(false); throw new Error("暂时连不上电脑。内容已保留，请检查 Wi-Fi 后重试。"); }
        throw error;
      } finally { window.clearTimeout(timeout); if (controller === abort) controller = null; if (uploadController === abort) uploadController = null; }
    }
    function schedule() { window.clearTimeout(timer); timer = active && !document.hidden ? window.setTimeout(() => void load(), 4000) : 0; }
    async function load(earlier = false, force = false) {
      if (reading || sending || (!active && !force) || document.hidden) return;
      reading = true; update(); const ticket = generation;
      const query = new URLSearchParams({ limit: "50" });
      if (earlier && messages.length) query.set("before", messages[messages.length - 1].id);
      else if (revision && !force) query.set("revision", revision);
      try {
        const result = await request(`messages?${query}`);
        if (ticket !== generation) return;
        if (pollError) { pollError = false; status("已重新连接电脑。"); }
        if (result.limits) { limits = { ...defaults, ...result.limits }; text.maxLength = limits.maxTextChars; }
        if (!result.unchanged) {
          if (!Array.isArray(result.messages)) throw new Error("收发记录无法读取，请刷新重试。");
          if (earlier) messages.push(...result.messages.filter(item => !messages.some(existing => existing.id === item.id)));
          else messages = result.messages;
          hasMore = Boolean(result.hasMore); revision = result.revision || ""; renderHistory();
        }
      } catch (error) { if (ticket === generation) { pollError = true; status(error.message, true); } }
      finally { reading = false; update(); schedule(); }
    }
    form.addEventListener("submit", async event => {
      event.preventDefault(); if (sending || (!text.value.trim() && !files.length)) return;
      if (text.value.length > limits.maxTextChars) { status(`文字最多 ${limits.maxTextChars} 字，请缩短后发送。`, true); return; }
      if (files.length > limits.maxFiles || files.some(item => item.file.size > limits.maxFileBytes) || files.reduce((sum, item) => sum + item.file.size, 0) > totalFileLimit()) { status("图片超过上传限制，请移除或缩小后重试。", true); return; }
      pendingId ||= requestId(); const payload = new FormData(); payload.append("requestId", pendingId); payload.append("text", text.value); const ticket = generation;
      for (const item of files) payload.append("files", item.file, item.file.name);
      sending = true; pollError = false; window.clearTimeout(timer); update(); renderPicked(); status("正在上传，请保持页面打开…");
      try {
        const result = await request("messages", payload, 90000);
        if (ticket !== generation) return;
        if (!result.message?.id) throw new Error("未能确认接收结果。内容已保留，可重新点发送。");
        generation += 1;
        if (!messages.some(item => item.id === result.message.id)) messages.unshift(result.message);
        text.value = ""; pendingId = ""; releaseFiles(); renderPicked(); renderHistory(); revision = "";
        status(phone ? "已传到电脑，可以在电脑 Console「互传」查看。" : "已发送，手机打开「互传」即可看到。");
      } catch (error) { if (!error.cancelled) status(error.message, true); }
      finally { sending = false; update(); renderPicked(); schedule(); }
    });
    refresh.addEventListener("click", () => void load(false, true)); older.addEventListener("click", () => void load(true));
    document.addEventListener("visibilitychange", () => { window.clearTimeout(timer); timer = 0; if (!document.hidden && active) void load(); });
    renderHistory(); update();
    return {
      setActive(value) { const changed = active !== Boolean(value); active = Boolean(value); window.clearTimeout(timer); timer = 0; if (active && changed) void load(); },
      refresh() { return load(false, true); },
      clear() { generation += 1; active = false; controller?.abort(); uploadController?.abort(); controller = null; uploadController = null; window.clearTimeout(timer); timer = 0; messages = []; revision = ""; hasMore = false; pollError = false; document.querySelectorAll?.(".transfer-copy-field, .transfer-copy-close").forEach(element => element.remove()); for (const item of files) { if (item.preview) URL.revokeObjectURL(item.preview); item.preview = ""; } renderPicked(); renderHistory(); }
    };
  }
  window.CodexTransferPanel = { create };
})();
