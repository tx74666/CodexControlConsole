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
  async function copyText(text, status, success = "已复制。") {
    try {
      if (navigator.clipboard?.writeText && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        status(success); return;
      }
    } catch { /* LAN HTTP and Safari can refuse clipboard access. */ }
    const input = make("textarea", "", "transfer-copy-field"); input.value = text;
    input.readOnly = true; input.setAttribute("aria-label", "复制内容"); document.body.append(input);
    input.focus(); input.select(); input.setSelectionRange?.(0, text.length);
    let copied = false;
    try { copied = Boolean(document.execCommand?.("copy")); } catch { /* Keep selected text available for manual copy. */ }
    if (copied) { input.remove(); status(success); }
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
    let active = false, timer = 0, reading = false, sending = false, pasting = false, mutating = false, mutationSequence = 0, sendSequence = 0, pendingAction = null, historyControls = [], limits = { ...defaults }, revision = "", messages = [], hasMore = false, pendingId = "", files = [], pendingDropBatch = null, generation = 0, controller = null, uploadController = null, pollError = false;
    const header = make("div", "", "transfer-heading"), title = make("div");
    title.append(make("h2", "手机传话 / 互传"), make("p", phone ? "在下面打字或粘贴文字，点发送，电脑就能收到。" : "这里接收手机发来的文字，也可以互传图片。", "transfer-muted"));
    header.append(title);
    if (options.onConnection) {
      const connect = make("button", "连接手机", "transfer-button"); connect.type = "button";
      connect.addEventListener("click", options.onConnection); header.append(connect);
    }
    const guide = make("section", "", "transfer-chat-guide"); guide.setAttribute("aria-label", "传给 Codex Console 聊天的步骤");
    guide.append(make("strong", "把手机文字传给 Codex Console 聊天"));
    const steps = make("ol");
    for (const step of ["手机：在下方输入文字，点“发送”。", "电脑：在下方收发记录找到“手机 → 电脑”，点“复制文字”。", "Codex：打开“Codex Console”这条聊天，粘贴到输入框，发送。"]) steps.append(make("li", step));
    guide.append(steps, make("p", "目前需要电脑上最后粘贴一次；“已传到电脑”表示电脑收到，尚未发送给聊天。", "transfer-muted transfer-small"));
    const dropHint = phone ? null : make("p", "拖入图片，松手即发送到手机。已输入的文字和已选图片会保留。", "transfer-drop-hint");
    const form = make("form", "", "transfer-composer");
    const label = make("label", phone ? "在这里输入：手机 → 电脑" : "电脑 → 手机（手机来信在下方收发记录）"); label.htmlFor = `${phone ? "phone" : "desktop"}TransferText`;
    const text = make("textarea"); text.id = label.htmlFor; text.rows = 4; text.maxLength = limits.maxTextChars;
    text.placeholder = phone ? "输入或粘贴文字，也可以只上传图片" : "输入或粘贴文字；复制图片后，按 Ctrl+V 粘贴"; text.setAttribute("aria-describedby", `${text.id}Notice`);
    const actions = make("div", "", "transfer-actions");
    const photos = make("input"); photos.type = "file"; photos.accept = "image/*,.heic,.heif"; photos.multiple = true; photos.hidden = true;
    const attachments = make("input"); attachments.type = "file"; attachments.accept = ".jpg,.jpeg,.png,.gif,.webp,.heic,.heif,image/jpeg,image/png,image/gif,image/webp,image/heic,image/heif"; attachments.multiple = true; attachments.hidden = true;
    const photoButton = make("button", "选择图片", "transfer-button"), fileButton = make("button", "从文件选图片", "transfer-button"), submit = make("button", "发送", "transfer-button transfer-primary");
    photoButton.type = fileButton.type = "button"; submit.type = "submit";
    photoButton.addEventListener("click", () => photos.click()); fileButton.addEventListener("click", () => attachments.click());
    const pasteButton = phone ? null : make("button", "粘贴图片", "transfer-button");
    if (pasteButton) { pasteButton.type = "button"; pasteButton.addEventListener("click", () => void pasteImages()); }
    actions.append(photoButton, fileButton); if (pasteButton) actions.append(pasteButton); actions.append(submit);
    const picked = make("div", "", "transfer-picked"), notice = make("p", "", "transfer-notice"); notice.id = `${text.id}Notice`; notice.setAttribute("role", "status"); notice.setAttribute("aria-live", "polite");
    const hint = make("p", "", "transfer-muted transfer-small");
    form.append(label, text, photos, attachments, picked, actions, hint, notice);
    const dropBatch = make("section", "", "transfer-drop-batch"); dropBatch.hidden = true; dropBatch.setAttribute("aria-label", "拖入的图片");
    let renderedDropBatch = null, dropRenderKey = "";
    const historyHead = make("div", "", "transfer-history-heading"), historyMeta = make("p", "收发记录", "transfer-muted"), refresh = make("button", "刷新", "transfer-button"); refresh.type = "button";
    const historyActions = make("div", "", "transfer-actions"), clearHistory = make("button", "清空记录", "transfer-button"), historyConfirm = make("div", "", "transfer-confirm"); clearHistory.type = "button"; historyConfirm.hidden = true;
    historyHead.tabIndex = -1;
    historyActions.append(refresh, clearHistory); historyHead.append(historyMeta, historyActions);
    const history = make("div", "", "transfer-history"), older = make("button", "较早记录", "transfer-button transfer-older"); older.type = "button"; older.hidden = true;
    root.classList.add("transfer-panel"); root.replaceChildren(header, guide, ...(dropHint ? [dropHint] : []), form, dropBatch, historyHead, historyConfirm, history, older);
    function status(message = "", error = false) { notice.textContent = message; notice.dataset.error = String(error); }
    function update() {
      text.disabled = photos.disabled = attachments.disabled = photoButton.disabled = fileButton.disabled = sending;
      if (pasteButton) { pasteButton.disabled = sending || pasting || mutating; pasteButton.textContent = pasting ? "正在粘贴…" : "粘贴图片"; }
      submit.disabled = sending || pasting || mutating || (!text.value.trim() && !files.length);
      submit.textContent = sending ? "正在上传…" : files.length ? "上传并发送" : "发送";
      refresh.disabled = older.disabled = reading || sending || mutating;
      clearHistory.disabled = sending || pasting || mutating || (!messages.length && !hasMore);
      for (const control of historyControls) control.disabled = sending || pasting || mutating;
      hint.textContent = `每次最多 ${limits.maxFiles} 张图片，单张 ${size(limits.maxFileBytes)}，合计 ${size(totalFileLimit())}。原图保存在电脑，两端可下载。`;
      renderDropBatch();
    }
    function renderDropBatch() {
      const batch = pendingDropBatch, key = batch ? JSON.stringify([batch.requestId, batch.state, batch.error, sending, pasting, mutating, active, document.hidden]) : "none";
      if (renderedDropBatch === batch && dropRenderKey === key) return;
      renderedDropBatch = batch; dropRenderKey = key;
      dropBatch.replaceChildren(); dropBatch.hidden = !batch;
      if (!batch) return;
      dropBatch.dataset.state = batch.state;
      dropBatch.append(make("strong", batch.state === "sending" ? "正在发送拖入的图片…" : "拖入的图片"));
      const names = make("ul", "", "transfer-drop-files");
      for (const file of batch.files) names.append(make("li", `${file.name || "未命名文件"} · ${size(file.size)}`));
      dropBatch.append(names);
      if (batch.error) dropBatch.append(make("p", batch.error, "transfer-drop-error"));
      const controls = make("div", "", "transfer-actions"), retry = make("button", "重试发送", "transfer-button"), remove = make("button", "移除这批图片", "transfer-button"); retry.type = remove.type = "button";
      retry.disabled = remove.disabled = sending || pasting || mutating;
      retry.disabled ||= !active || document.hidden;
      retry.addEventListener("click", () => { if (pendingDropBatch === batch) void sendDroppedImages(batch); });
      remove.addEventListener("click", () => {
        if (pendingDropBatch !== batch || sending || pasting || mutating) return;
        pendingDropBatch = null; status("已移除这批拖入的图片，原草稿仍保留。文件本身没有删除。"); update();
      });
      controls.append(retry, remove); dropBatch.append(controls);
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
      const all = [...files.map(item => item.file), ...additions], error = imageBatchError(all);
      if (error) { status(error, true); return; }
      for (const file of additions) files.push({ file, preview: /^image\/(?:jpeg|png|gif|webp)$/.test(file.type) ? URL.createObjectURL(file) : "" });
      pendingId = ""; status(); renderPicked(); update();
      return true;
    }
    function totalFileLimit() { return Math.max(0, limits.maxRequestBytes - 128 * 1024); }
    function imageBatchError(batch) {
      if (!batch.length) return "没有可发送的图片。请把图片文件拖到互传区域。";
      if (batch.length > limits.maxFiles) return `每次最多上传 ${limits.maxFiles} 张图片。请先移除一些图片。`;
      const unsupported = batch.find(file => !/\.(?:jpe?g|png|gif|webp|heic|heif)$/i.test(file.name || ""));
      if (unsupported) return `${unsupported.name} 不是支持的图片格式。请选 JPEG、PNG、GIF、WebP 或 HEIC 图片。`;
      const empty = batch.find(file => !file.size); if (empty) return `${empty.name} 是空文件，请重新选择图片。`;
      const oversized = batch.find(file => file.size > limits.maxFileBytes);
      if (oversized) return `${oversized.name} 超过 ${size(limits.maxFileBytes)}，请选择较小的文件。`;
      if (batch.reduce((sum, file) => sum + file.size, 0) > totalFileLimit()) return `图片合计不能超过 ${size(totalFileLimit())}。`;
      return "";
    }
    function isFileDrag(event) {
      const transfer = event.dataTransfer;
      return Boolean(transfer && (transfer.files?.length || Array.from(transfer.types || []).includes("Files") || Array.from(transfer.items || []).some(item => item.kind === "file")));
    }
    function isUriDrag(event) { return Array.from(event.dataTransfer?.types || []).includes("text/uri-list"); }
    function acceptsDropTarget(event) { return event.target === root || root.contains?.(event.target) || event.composedPath?.().includes(root); }
    function stopFileNavigation(event) { event.preventDefault(); event.stopPropagation?.(); }
    if (!phone) {
      const protectFileDrag = event => {
        if (!active || document.hidden) return;
        const fileDrag = isFileDrag(event);
        if (!fileDrag && !isUriDrag(event)) return;
        stopFileNavigation(event);
        if (!fileDrag) { event.dataTransfer.dropEffect = "none"; root.classList.remove("transfer-drop-active"); return; }
        const available = acceptsDropTarget(event) && !pendingDropBatch && !sending && !pasting && !mutating;
        if (event.dataTransfer) event.dataTransfer.dropEffect = pendingDropBatch ? "none" : "copy";
        if (pendingDropBatch) status("上一批拖入的图片还未确认发送。请先重试或移除上一批，再拖入新图片。", true);
        root.classList.toggle("transfer-drop-active", available);
      };
      document.addEventListener("dragenter", protectFileDrag, true); document.addEventListener("dragover", protectFileDrag, true);
      document.addEventListener("dragleave", event => { if (!event.relatedTarget || !root.contains?.(event.relatedTarget)) root.classList.remove("transfer-drop-active"); }, true);
      document.addEventListener("drop", event => {
        if (!active || document.hidden) return;
        const fileDrag = isFileDrag(event);
        if (!fileDrag && !isUriDrag(event)) return;
        stopFileNavigation(event); root.classList.remove("transfer-drop-active");
        if (!fileDrag) { event.dataTransfer.dropEffect = "none"; status("请从文件夹拖入图片，网页链接不会发送。", true); return; }
        if (pendingDropBatch) { status("上一批拖入的图片还未确认发送。请先重试或移除上一批，再拖入新图片。", true); return; }
        const dropped = Array.from(event.dataTransfer.files || []);
        if (!dropped.length) { status("没有收到图片文件。请从文件夹把图片文件拖到互传区域；链接和文件夹不会发送。", true); return; }
        const error = imageBatchError(dropped);
        const outside = !acceptsDropTarget(event), busy = sending || pasting || mutating;
        const batch = { files: dropped, requestId: error ? "" : requestId(), state: "ready", error: error || (outside ? "请把图片拖到互传区域。此批文件已保留，可点击“重试发送”发送到手机。" : busy ? "正在处理上一项操作。此批图片已保留，请完成后点击“重试发送”。" : "") };
        pendingDropBatch = batch;
        if (batch.error) { batch.state = "failed"; status(batch.error, true); update(); return; }
        update(); void sendDroppedImages(batch);
      }, true);
    }
    async function sendDroppedImages(batch) {
      if (phone || !active || document.hidden || pendingDropBatch !== batch || sending || pasting || mutating) return;
      const error = imageBatchError(batch.files);
      if (error) { batch.state = "failed"; batch.error = error; status(error, true); update(); return; }
      batch.requestId ||= requestId();
      const payload = new FormData(); payload.append("requestId", batch.requestId); payload.append("text", "");
      for (const file of batch.files) payload.append("files", file, file.name);
      const ticket = generation, operation = ++sendSequence;
      batch.state = "sending"; batch.error = ""; sending = true; pollError = false; window.clearTimeout(timer); update(); renderPicked(); status("正在发送拖入的图片，请保持页面打开…");
      try {
        const result = await request("messages", payload, 90000);
        if (ticket !== generation || pendingDropBatch !== batch || operation !== sendSequence) return;
        if (!result.message?.id) throw new Error("未能确认接收结果。这批图片已保留，请点击“重试发送”核对并重试。");
        generation += 1; pendingDropBatch = null;
        if (!messages.some(item => item.id === result.message.id)) messages.unshift(result.message);
        revision = ""; renderHistory(); status("图片已发送，手机打开「互传」即可看到。原草稿仍保留。");
      } catch (error) {
        if (ticket !== generation || pendingDropBatch !== batch || operation !== sendSequence) return;
        batch.state = "unconfirmed"; batch.error = `${error.uploadTimedOut ? "上传超时，接收结果尚未确认。" : error.message || "暂时无法确认发送结果。"} 这批图片已保留，请点击“重试发送”核对接收结果。`; status(batch.error, true);
      } finally {
        if (operation === sendSequence) { sending = false; update(); renderPicked(); schedule(); }
      }
    }
    function cancelPendingUpload() {
      generation += 1; sendSequence += 1; controller?.abort(); uploadController?.abort(); controller = uploadController = null; sending = false;
      if (pendingDropBatch?.state === "sending") { pendingDropBatch.state = "unconfirmed"; pendingDropBatch.error = "发送结果尚未确认。这批图片已保留，返回互传后请点击“重试发送”。"; }
      root.classList.remove("transfer-drop-active"); update(); renderPicked();
    }
    function clipboardImage(file, index) {
      const extensions = { "image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp", "image/heic": "heic", "image/heif": "heif" };
      const extension = extensions[file.type];
      if (!extension || /\.(?:jpe?g|png|gif|webp|heic|heif)$/i.test(file.name || "")) return file;
      return new File([file], `pasted-image-${Date.now()}-${index + 1}.${extension}`, { type: file.type });
    }
    function addClipboardImages(additions) {
      if (selectFiles({ files: additions.map(clipboardImage), value: "" })) status(`已粘贴 ${additions.length} 张图片，点击“上传并发送”发送。`);
    }
    async function pasteImages() {
      if (sending || pasting || mutating) return;
      if (!navigator.clipboard?.read || !window.isSecureContext) {
        text.focus(); status("请在输入框按 Ctrl+V 粘贴图片。"); return;
      }
      const ticket = generation; pasting = true; update();
      try {
        const items = await navigator.clipboard.read(), additions = [];
        for (const item of items) {
          const type = ["image/png", "image/jpeg", "image/webp", "image/gif", "image/heic", "image/heif"].find(value => item.types.includes(value));
          if (type) additions.push(await item.getType(type));
        }
        if (ticket !== generation) return;
        if (!additions.length) { status("剪贴板里没有图片，请先复制图片。", true); return; }
        addClipboardImages(additions);
      } catch {
        if (ticket === generation) { text.focus(); status("无法读取剪贴板，请在输入框按 Ctrl+V 粘贴图片。", true); }
      } finally { pasting = false; update(); }
    }
    photos.addEventListener("change", () => selectFiles(photos)); attachments.addEventListener("change", () => selectFiles(attachments));
    text.addEventListener("input", () => { pendingId = ""; update(); });
    form.addEventListener("paste", event => {
      if (sending || pasting || mutating) return;
      const items = Array.from(event.clipboardData?.items || []).filter(item => item.kind === "file").map(item => item.getAsFile()).filter(Boolean);
      const additions = (items.length ? items : Array.from(event.clipboardData?.files || [])).filter(file => /^image\//.test(file.type) || /\.(?:jpe?g|png|gif|webp|heic|heif)$/i.test(file.name || ""));
      if (additions.length) { event.preventDefault(); addClipboardImages(additions); }
    });
    function assetUrl(value, preview = false) {
      try {
        const url = new URL(value, window.location.href);
        if (url.origin !== new URL(window.location.href).origin || url.pathname !== `${endpoint}/attachment` || !url.searchParams.get("id")) return "";
        if (preview) url.searchParams.set("preview", "1");
        return url.href;
      } catch { return ""; }
    }
    let imagePreview = null, previewTriggers = new Map();
    const previewKey = (message, url, preview) => JSON.stringify([message.id, url, preview]);
    function closePreview(restore = true) {
      const current = imagePreview; if (!current) return;
      imagePreview = null;
      current.image.removeAttribute("src");
      if (current.dialog.open && typeof current.dialog.close === "function") current.dialog.close();
      current.dialog.remove();
      if (!restore || !active) return;
      const target = previewTriggers.get(current.key) || historyHead;
      target.focus({ preventScroll: true });
      for (const position of current.scroll) { position.element.scrollTop = position.top; position.element.scrollLeft = position.left; }
      window.scrollTo?.(current.windowX, current.windowY);
    }
    function openPreview(key, attachment, url, preview) {
      if (!active || !previewTriggers.has(key)) return;
      closePreview(false);
      const dialog = make("dialog", "", "transfer-preview"), toolbar = make("div", "", "transfer-preview-toolbar"), close = make("button", "关闭 · 返回互传", "transfer-button"), download = make("a", "下载原文件", "transfer-button");
      dialog.setAttribute("aria-label", `图片预览：${attachment.name}`); dialog.setAttribute("aria-modal", "true"); dialog.setAttribute("role", "dialog");
      close.type = "button"; download.href = url; download.download = attachment.name;
      toolbar.append(close, download);
      const stage = make("div", "", "transfer-preview-stage"), image = make("img"), info = make("p", "正在载入图片…", "transfer-preview-info");
      image.alt = attachment.name; image.hidden = true; info.setAttribute("role", "status"); info.setAttribute("aria-live", "polite");
      stage.append(image, info); dialog.append(toolbar, make("p", attachment.name, "transfer-preview-name"), stage);
      const scroll = []; for (let element = previewTriggers.get(key); element; element = element.parentElement) scroll.push({ element, top: element.scrollTop, left: element.scrollLeft });
      const current = { key, dialog, image, scroll, windowX: window.scrollX || 0, windowY: window.scrollY || 0 }; imagePreview = current;
      const owned = () => imagePreview === current;
      image.addEventListener("load", () => { if (owned()) { image.hidden = false; info.hidden = true; } });
      image.addEventListener("error", () => { if (owned()) { image.hidden = true; info.hidden = false; info.textContent = "图片暂时无法显示。可以下载原文件，或点上方“关闭 · 返回互传”。"; } });
      close.addEventListener("click", () => { if (owned()) closePreview(); });
      dialog.addEventListener("cancel", event => { event.preventDefault(); if (owned()) closePreview(); });
      dialog.addEventListener("close", () => { if (owned()) closePreview(); });
      dialog.addEventListener("click", event => { if (owned() && (event.target === dialog || event.target === stage)) closePreview(); });
      dialog.addEventListener("keydown", event => {
        if (!owned()) return;
        if (event.key === "Escape") { event.preventDefault(); closePreview(); }
        else if (event.key === "Tab" && dialog.dataset.fallback === "true") {
          if (event.shiftKey && document.activeElement === close) { event.preventDefault(); download.focus(); }
          else if (!event.shiftKey && document.activeElement === download) { event.preventDefault(); close.focus(); }
        }
      });
      root.append(dialog);
      try { if (typeof dialog.showModal !== "function") throw new Error("Dialog unavailable"); dialog.showModal(); }
      catch { dialog.dataset.fallback = "true"; dialog.setAttribute("open", ""); }
      close.focus({ preventScroll: true }); image.src = url;
    }
    function renderHistory() {
      history.replaceChildren(); historyControls = []; previewTriggers = new Map();
      if (pendingAction?.type === "delete" && !messages.some(message => message.id === pendingAction.id)) pendingAction = null;
      renderClearConfirmation();
      if (!messages.length) history.append(make("p", "还没有收发记录。选图片或输入文字，然后点发送。", "transfer-empty"));
      for (const message of messages) {
        const card = make("article", "", "transfer-message"); card.dataset.sender = message.sender; card.dataset.messageId = message.id; card.dataset.starred = String(message.starred === true);
        const heading = make("div", "", "transfer-message-heading");
        const stamp = new Date(message.createdAt);
        heading.append(make("strong", message.sender === "phone" ? "手机 → 电脑" : "电脑 → 手机"), make("time", Number.isNaN(stamp.getTime()) ? "" : stamp.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })));
        const controls = make("div", "", "transfer-message-actions"), star = make("button", message.starred === true ? "★" : "☆", "transfer-button transfer-star"), remove = make("button", "删除", "transfer-button"); star.type = remove.type = "button";
        star.setAttribute("aria-pressed", String(message.starred === true)); star.setAttribute("aria-label", message.starred === true ? "取消标星" : "标星这条记录"); star.title = message.starred === true ? "取消标星" : "标星，清空时保留";
        star.addEventListener("click", () => void mutateHistory("star", { id: message.id, starred: message.starred !== true }));
        remove.addEventListener("click", () => { if (sending || pasting || mutating) return; pendingAction = { type: "delete", id: message.id }; renderHistory(); });
        controls.append(star, remove); historyControls.push(star, remove); heading.append(controls); card.append(heading);
        if (pendingAction?.type === "delete" && pendingAction.id === message.id) card.append(makeConfirmation("删除这条记录及其互传附件？", "确认删除", () => void mutateHistory("delete", { id: message.id })));
        if (message.text) {
          card.append(make("p", message.text, "transfer-message-text"));
          const copy = make("button", "复制文字", "transfer-button"); copy.type = "button"; copy.addEventListener("click", () => void copyText(message.text, status, !phone && message.sender === "phone" ? "已复制。请在 Codex 的“Codex Console”聊天输入框粘贴，再发送。" : "已复制。")); card.append(copy);
        }
        const gallery = make("div", "", "transfer-attachments");
        for (const attachment of message.attachments || []) {
          const url = assetUrl(attachment.url); if (!url) continue;
          const item = make("div", "", "transfer-attachment");
          if (attachment.previewable) {
            const preview = assetUrl(attachment.previewUrl || attachment.url, true);
            if (preview) {
              const link = make(phone ? "button" : "a", "", phone ? "transfer-preview-trigger" : "");
              if (phone) {
                const key = previewKey(message, url, preview); link.type = "button"; link.setAttribute("aria-label", `查看图片：${attachment.name}`); link.setAttribute("aria-haspopup", "dialog"); previewTriggers.set(key, link);
                link.addEventListener("click", () => { if (previewTriggers.get(key) === link) openPreview(key, attachment, url, preview); });
              } else { link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; }
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
                  const response = await fetch("/api/transfer/open", { method: "POST", credentials: "same-origin", mode: "same-origin", referrerPolicy: "same-origin", redirect: "error", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: attachment.id, folder }) });
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
      if (imagePreview && !previewTriggers.has(imagePreview.key)) closePreview();
      historyMeta.textContent = `收发记录 · 最近 ${messages.length} 条`; older.hidden = !hasMore;
      update();
    }
    function makeConfirmation(description, confirmLabel, confirmAction) {
      const box = make("div", "", "transfer-confirm"), actions = make("div", "", "transfer-actions"), confirm = make("button", confirmLabel, "transfer-button transfer-danger"), cancel = make("button", "取消", "transfer-button"); confirm.type = cancel.type = "button";
      confirm.addEventListener("click", confirmAction); cancel.addEventListener("click", () => { if (mutating) return; pendingAction = null; renderHistory(); });
      actions.append(confirm, cancel); box.append(make("p", description), actions); historyControls.push(confirm, cancel); return box;
    }
    function renderClearConfirmation() {
      historyConfirm.replaceChildren(); historyConfirm.hidden = pendingAction?.type !== "clear";
      if (historyConfirm.hidden) return;
      const all = pendingAction.mode === "all", box = makeConfirmation(all ? "删除全部收发记录及其互传附件，包括星标和较早记录。此操作无法撤销。" : "删除所有未标星记录及其互传附件，包括尚未展开的较早记录；保留 ★ 星标记录。", all ? "确认全部清空" : "确认清空未标星", () => void mutateHistory("clear", { mode: all ? "all" : "unstarred" }));
      const mode = make("button", all ? "保留星标" : "全部清空", "transfer-button"); mode.type = "button";
      mode.addEventListener("click", () => { if (sending || pasting || mutating) return; pendingAction = { type: "clear", mode: all ? "unstarred" : "all" }; renderHistory(); });
      box.children[1].append(mode); historyControls.push(mode); historyConfirm.append(box);
    }
    async function mutateHistory(action, payload) {
      if (sending || pasting || mutating) return;
      const operation = ++mutationSequence; generation += 1; const ticket = generation; mutating = true; pendingAction = null; controller?.abort(); controller = null; window.clearTimeout(timer); renderHistory();
      status(action === "star" ? "正在更新星标…" : action === "delete" ? "正在删除记录…" : "正在清空记录…");
      try {
        const result = await request(action, JSON.stringify(payload));
        if (ticket !== generation) return;
        if (!Array.isArray(result.messages)) throw new Error("收发记录无法读取，请刷新确认操作结果。");
        messages = result.messages; revision = result.revision || ""; hasMore = Boolean(result.hasMore); pollError = false;
        if (result.limits) { limits = { ...defaults, ...result.limits }; text.maxLength = limits.maxTextChars; }
        renderHistory();
        if (action === "star") status(payload.starred ? "已标星，清空未标星记录时会保留。" : "已取消标星。");
        else if (action === "delete") status("已删除这条记录及其互传附件。");
        else if (payload.mode === "all") status("已清空全部记录，包括星标。");
        else status(Number.isSafeInteger(result.removedCount) && Number.isSafeInteger(result.preservedStarredCount) ? `已清空 ${result.removedCount} 条未标星记录，保留 ${result.preservedStarredCount} 条星标记录。` : "已清空未标星记录，星标记录已保留。");
      } catch (error) { if (!error.cancelled && ticket === generation) status(error.message || "操作失败，请重试。", true); }
      finally { if (operation === mutationSequence) { mutating = false; update(); schedule(); } }
    }
    async function request(path, body, timeoutMs = 15000) {
      const abort = new AbortController(), timeout = window.setTimeout(() => abort.abort(), timeoutMs);
      const ticket = generation;
      if (!body) controller = abort; else uploadController = abort;
      try {
        const response = await fetch(`${endpoint}/${path}`, { method: body ? "POST" : "GET", credentials: "same-origin", mode: "same-origin", referrerPolicy: "same-origin", cache: "no-store", redirect: "error", signal: abort.signal, headers: { Accept: "application/json", ...(typeof body === "string" ? { "Content-Type": "application/json" } : {}), ...(phone ? { "X-Codex-Phone": "1" } : {}) }, ...(body ? { body } : {}) });
        if (ticket !== generation) throw Object.assign(new Error("旧连接已取消。"), { cancelled: true });
        options.onConnectionState?.(true);
        let result;
        try { result = await response.json(); } catch { throw new Error("电脑返回的内容无法读取，请重试。"); }
        if (ticket !== generation) throw Object.assign(new Error("旧连接已取消。"), { cancelled: true });
        if (!response.ok) {
          if (response.status === 401) { closePreview(false); if (!phone) { active = false; cancelPendingUpload(); } options.onAuth?.(); }
          throw new Error(result.error || `请求失败（${response.status}）。`);
        }
        return result;
      } catch (error) {
        if (ticket !== generation) throw Object.assign(new Error("旧连接已取消。"), { cancelled: true });
        if (error.name === "AbortError") { options.onConnectionState?.(false); throw Object.assign(new Error(typeof body === "string" ? "操作超时，请刷新记录确认结果。" : body ? "上传超时。内容已保留，可重新点发送。" : "连接超时，请检查电脑与 Wi-Fi。"), { uploadTimedOut: Boolean(body && typeof body !== "string") }); }
        if (error instanceof TypeError) { options.onConnectionState?.(false); throw new Error("暂时连不上电脑。内容已保留，请检查 Wi-Fi 后重试。"); }
        throw error;
      } finally { window.clearTimeout(timeout); if (controller === abort) controller = null; if (uploadController === abort) uploadController = null; }
    }
    function schedule() { window.clearTimeout(timer); timer = active && !document.hidden ? window.setTimeout(() => void load(), 4000) : 0; }
    async function load(earlier = false, force = false) {
      if (reading || sending || mutating || (!active && !force) || document.hidden) return;
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
      event.preventDefault(); if (sending || pasting || mutating || (!text.value.trim() && !files.length)) return;
      if (text.value.length > limits.maxTextChars) { status(`文字最多 ${limits.maxTextChars} 字，请缩短后发送。`, true); return; }
      const error = files.length ? imageBatchError(files.map(item => item.file)) : "";
      if (error) { status(error, true); return; }
      pendingId ||= requestId(); const payload = new FormData(); payload.append("requestId", pendingId); payload.append("text", text.value); const ticket = generation, operation = ++sendSequence;
      for (const item of files) payload.append("files", item.file, item.file.name);
      sending = true; pollError = false; window.clearTimeout(timer); update(); renderPicked(); status("正在上传，请保持页面打开…");
      try {
        const result = await request("messages", payload, 90000);
        if (ticket !== generation || operation !== sendSequence) return;
        if (!result.message?.id) throw new Error("未能确认接收结果。内容已保留，可重新点发送。");
        generation += 1;
        if (!messages.some(item => item.id === result.message.id)) messages.unshift(result.message);
        text.value = ""; pendingId = ""; releaseFiles(); renderPicked(); renderHistory(); revision = "";
        status(phone ? "已传到电脑。电脑点“手机传话”查看收发记录，复制后粘贴到 Codex 的“Codex Console”聊天，再发送。" : "已发送，手机打开「互传」即可看到。");
      } catch (error) { if (!error.cancelled && ticket === generation && operation === sendSequence) status(error.message, true); }
      finally { if (operation === sendSequence) { sending = false; update(); renderPicked(); schedule(); } }
    });
    refresh.addEventListener("click", () => void load(false, true)); older.addEventListener("click", () => void load(true));
    clearHistory.addEventListener("click", () => { if (sending || pasting || mutating || (!messages.length && !hasMore)) return; pendingAction = { type: "clear", mode: "unstarred" }; renderHistory(); });
    document.addEventListener("visibilitychange", () => { window.clearTimeout(timer); timer = 0; if (document.hidden && !phone) cancelPendingUpload(); if (!document.hidden && active) void load(); });
    window.addEventListener?.("pagehide", () => { closePreview(false); if (!phone) { active = false; cancelPendingUpload(); } });
    renderHistory(); update();
    return {
      hasDraft() { return Boolean(text.value.trim() || files.length || pendingDropBatch || sending || pasting || mutating || imagePreview); },
      setActive(value) { const changed = active !== Boolean(value); active = Boolean(value); if (!active) { closePreview(false); if (!phone && (changed || sending)) cancelPendingUpload(); } window.clearTimeout(timer); timer = 0; update(); if (active && changed) void load(); },
      refresh() { return load(false, true); },
      clear() { closePreview(false); generation += 1; sendSequence += 1; sending = false; mutationSequence += 1; mutating = false; pendingAction = null; active = false; controller?.abort(); uploadController?.abort(); controller = null; uploadController = null; if (pendingDropBatch?.state === "sending") { pendingDropBatch.state = "unconfirmed"; pendingDropBatch.error = "连接已重置，发送结果尚未确认。这批图片已保留，返回互传后请点击“重试发送”。"; } root.classList.remove("transfer-drop-active"); window.clearTimeout(timer); timer = 0; messages = []; revision = ""; hasMore = false; pollError = false; document.querySelectorAll?.(".transfer-copy-field, .transfer-copy-close").forEach(element => element.remove()); for (const item of files) { if (item.preview) URL.revokeObjectURL(item.preview); item.preview = ""; } renderPicked(); renderHistory(); }
    };
  }
  window.CodexTransferPanel = { create };
})();
