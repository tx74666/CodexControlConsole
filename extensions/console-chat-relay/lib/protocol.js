/* Pure validation. No browser, filesystem, account or native-host access. */
(function (root) {
  "use strict";
  const PROTOCOL = "console_chat_relay/v1";
  const MAX_PROMPT = 120000, MAX_ANSWER = 20000;
  const IMAGE_CHUNK_BYTES = 128 * 1024, MAX_IMAGE_BYTES = 8 * 1024 * 1024, MAX_IMAGE_TOTAL = 24 * 1024 * 1024;
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  const DISPATCH = /^[0-9a-f]{32}$/, SHA = /^[0-9a-f]{64}$/;
  const PROFILE = new Set(["fast", "high", "pro"]);
  const DOM_UNIT = /^fallback-turn-(\d+):(\d+):(user|assistant)$/;
  const HOST_NAME = "com.tx74666.codex_console_chat_relay", EXTENSION_ID = "ggjlmdfnbknlicnibfngaenlakeabkfk";
  const DOM_KEYS = ["version", "verified", "surface", "capturedAt", "source", "observationSha256", "selectors", "profiles"];
  const SELECTOR_KEYS = ["composer", "profile", "messages", "userText", "assistantText", "completion", "send", "stop", "login", "chatMode"];
  class RelayError extends Error {
    constructor(code, message) { super(message); this.name = "RelayError"; this.code = code; }
  }
  function reject(code, message) { throw new RelayError(code, message); }
  function exact(value, keys, code = "invalid_schema") {
    if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).length !== keys.length
        || Object.keys(value).some(key => !keys.includes(key))) reject(code, "消息字段不符合冻结契约。");
    return value;
  }
  function text(value, limit, code = "invalid_text") {
    if (typeof value !== "string" || [...value].length > limit || value.includes("\0")) reject(code, "文字内容无效或超过上限。");
    return value;
  }
  function nonempty(value, limit, code) {
    const result = text(value, limit, code);
    if (!result.trim()) reject(code || "invalid_text", "实际文字不能为空。");
    return result;
  }
  function common(value, type) {
    if (value.protocol !== PROTOCOL || value.type !== type || !DISPATCH.test(value.dispatchId)
        || !UUID.test(value.attemptId)) reject("invalid_identity", "协议或请求身份无效。");
  }
  function envelope(type, identity, extra = {}) {
    const value = { protocol: PROTOCOL, type, dispatchId: identity.dispatchId, attemptId: identity.attemptId, ...extra };
    common(value, type);
    return value;
  }
  function sameIdentity(value, identity) {
    return value?.protocol === PROTOCOL && value.dispatchId === identity?.dispatchId && value.attemptId === identity?.attemptId;
  }
  function validateDom(value) {
    exact(value, DOM_KEYS, "dom_contract_unverified");
    if (value.version !== 1 || value.verified !== true || !["chrome", "edge"].includes(value.surface) || value.source !== "cua"
        || !SHA.test(value.observationSha256) || !isoTime(value.capturedAt))
      reject("dom_contract_unverified", "尚无经实际 Chrome/Edge CUA 核对的 DOM 合同，IAB 与 fixture 不能替代。");
    exact(value.selectors, SELECTOR_KEYS, "dom_contract_unverified");
    for (const key of SELECTOR_KEYS) {
      // Only Stop can remain explicitly unknown. Missing/empty selectors are
      // never an alternative spelling for an unobserved control.
      if (key === "stop" && value.selectors[key] === null) continue;
      nonempty(value.selectors[key], 1000, "dom_contract_unverified");
    }
    exact(value.profiles, ["fast"], "profile_unverified");
    exact(value.profiles.fast, ["label"], "profile_unverified");
    if (value.profiles.fast.label !== "Instant") reject("profile_unverified", "本准备包只包含实际观察过的 Instant 标签。");
    return value;
  }
  function validatePrepare(value) {
    const keys = ["protocol", "type", "dispatchId", "attemptId", "prompt", "promptSha256", "requestedProfile", "target", "domContract"];
    if (Object.prototype.hasOwnProperty.call(value || {}, "images")) keys.push("images", "attachmentsContract");
    exact(value, keys);
    common(value, "prepare");
    nonempty(value.prompt, MAX_PROMPT);
    if (!SHA.test(value.promptSha256) || !PROFILE.has(value.requestedProfile)) reject("invalid_prompt", "问题哈希或所选档位无效。");
    const marker = `[Codex Console 发布编号：${value.dispatchId}]`;
    if (value.prompt.split("[Codex Console 发布编号：").length !== 2 || !value.prompt.includes(marker))
      reject("invalid_publication_marker", "缺少这次请求唯一的完整发布编号。");
    exact(value.target, ["kind", "mode"]);
    if (value.target.kind !== "chatgpt" || value.target.mode !== "new") reject("wrong_target", "只接受普通 ChatGPT 新 Chat。");
    validateDom(value.domContract);
    if (keys.includes("images")) { validateImages(value.images); validateAttachmentsContract(value.attachmentsContract, value.domContract.surface); }
    if (value.requestedProfile !== "fast") reject("profile_unverified", "高与 Pro 尚无实际档位映射，保留请求并停止，不降档。");
    return value;
  }
  function validateCommit(value) {
    exact(value, ["protocol", "type", "dispatchId", "attemptId"]);
    common(value, "commitSend");
    return value;
  }
  function rootUrl(value) {
    try {
      const url = new URL(value);
      return url.origin === "https://chatgpt.com" && (url.pathname === "/" || url.pathname === "") && !url.search && !url.hash;
    } catch { return false; }
  }
  function conversationUrl(value) {
    try {
      const url = new URL(value);
      return url.origin === "https://chatgpt.com" && /^\/c\/[0-9a-f-]{36}$/.test(url.pathname) && UUID.test(url.pathname.slice(3))
        && !url.search && !url.hash;
    } catch { return false; }
  }
  function validatePrepared(value, prepared = null) {
    exact(value, ["protocol", "type", "dispatchId", "attemptId", "observation"]);
    common(value, "prepared");
    validateFreshObservation(value.observation, prepared);
    return value;
  }
  function validateReadiness(value) {
    exact(value, ["protocol", "type", "dispatchId", "attemptId", "domContract"]);
    common(value, "checkReady");
    validateDom(value.domContract);
    return value;
  }
  function validatePageReady(value, readiness) {
    exact(value, ["protocol", "type", "dispatchId", "attemptId", "observation"]);
    common(value, "pageReady");
    validateReadiness(readiness);
    const observation = exact(value.observation, ["url", "chatMode", "loginVerified", "emptyComposer", "modelControlPresent", "completionInitiallyPresent", "surface", "observationSha256"]);
    if (!rootUrl(observation.url) || observation.chatMode !== true || observation.loginVerified !== true
        || observation.emptyComposer !== true || observation.modelControlPresent !== true || observation.completionInitiallyPresent !== false
        || !["chrome", "edge"].includes(observation.surface) || !SHA.test(observation.observationSha256))
      reject("readiness_observation_mismatch", "只读就绪缺少实际空白普通 Chat、登录或档位控件；不代表已选择 Instant。");
    if (!sameIdentity(value, readiness) || value.observation.surface !== readiness.domContract.surface
        || value.observation.observationSha256 !== readiness.domContract.observationSha256)
      reject("readiness_identity_mismatch", "只读就绪回执不属于本次页面与冻结 DOM 合同。");
    return value;
  }
  function validateFreshObservation(value, prepared = null) {
    const keys = ["url", "chatMode", "loginVerified", "emptyComposer", "observedProfile", "completionInitiallyPresent", "surface", "observationSha256", "profileDom"];
    if (prepared?.images) keys.push("images");
    const observation = exact(value, keys);
    if (prepared?.images) validateImageEvidence(observation.images, prepared.images, "ready");
    if (!rootUrl(observation.url) || observation.chatMode !== true || observation.loginVerified !== true
        || observation.emptyComposer !== true || observation.completionInitiallyPresent !== false || observation.observedProfile !== "Instant"
        || !["chrome", "edge"].includes(observation.surface) || !SHA.test(observation.observationSha256))
      reject("prepare_observation_mismatch", "新 Chat、登录、空输入、结束标记或实际 Instant 观测不符。");
    exact(observation.profileDom, ["text", "reasoningEffort"]);
    if (!["Instant", "Thinking effortInstant", "思考强度Instant", "思考强度即时"].includes(observation.profileDom.text) || observation.profileDom.reasoningEffort !== "none")
      reject("profile_unverified", "缺少实际 Instant 标签与 none effort 属性。");
    return observation;
  }
  function validateFailure(value) {
    exact(value, ["protocol", "type", "dispatchId", "attemptId", "code", "message"]);
    if (!["blocked", "uncertain"].includes(value.type)) reject("invalid_schema", "失败类型无效。");
    common(value, value.type);
    nonempty(value.code, 80);
    nonempty(value.message, 1000);
    return value;
  }
  function validateCapture(value, prepared) {
    exact(value, ["protocol", "type", "dispatchId", "attemptId", "evidence"]);
    common(value, "capture");
    if (!sameIdentity(value, prepared)) reject("capture_identity_mismatch", "回答不属于已冻结请求。");
    const contract = validateDom(prepared.domContract);
    const keys = ["source", "conversationUrl", "sourceUserMessageId", "assistantMessageId", "sourceUnitKey",
      "assistantUnitKey", "promptText", "answerText", "completion", "profile", "observedAt"];
    if (prepared.images) keys.push("images");
    const evidence = exact(value.evidence, keys);
    if (prepared.images) validateImageEvidence(evidence.images, prepared.images, "attached");
    if (evidence.source !== "browser_dom" || !conversationUrl(evidence.conversationUrl)
        || !UUID.test(evidence.sourceUserMessageId) || !UUID.test(evidence.assistantMessageId)
        || evidence.sourceUserMessageId === evidence.assistantMessageId) reject("capture_source_mismatch", "缺少准确的实际页面对话与消息来源。");
    nonempty(evidence.sourceUnitKey, 160);
    nonempty(evidence.assistantUnitKey, 160);
    const userUnit = DOM_UNIT.exec(evidence.sourceUnitKey), assistantUnit = DOM_UNIT.exec(evidence.assistantUnitKey);
    if (!userUnit || !assistantUnit || userUnit[3] !== "user" || assistantUnit[3] !== "assistant"
        || userUnit[1] !== assistantUnit[1] || Number(assistantUnit[2]) <= Number(userUnit[2])) reject("capture_source_mismatch", "DOM 单位归属或回答顺序不符。");
    if (text(evidence.promptText, MAX_PROMPT) !== prepared.prompt) reject("capture_prompt_mismatch", "页面用户输入与完整冻结问题不一致。");
    nonempty(evidence.answerText, MAX_ANSWER);
    exact(evidence.completion, ["text", "observedAfterCommit", "stopPresent"]);
    const expectedStop = contract.selectors.stop === null ? null : false;
    if (!["Response complete", "回答已完成"].includes(evidence.completion.text) || evidence.completion.observedAfterCommit !== true
        || evidence.completion.stopPresent !== expectedStop) reject("capture_not_complete", "没有本次提交后的明确结束证据，或停止控件观测与冻结契约不符。");
    exact(evidence.profile, ["requestedProfile", "observedBefore", "observedAfter"]);
    if (evidence.profile.requestedProfile !== prepared.requestedProfile || evidence.profile.observedBefore !== "Instant"
        || evidence.profile.observedAfter !== "Instant") reject("profile_changed", "实际档位前后不符，不能冒充所选档位。");
    if (!isoTime(evidence.observedAt)) reject("invalid_observation_time", "实际观察时间无效。");
    return value;
  }
  function validateAccepted(value, prepared) {
    exact(value, ["protocol", "type", "dispatchId", "attemptId", "evidence"]);
    common(value, "accepted");
    if (!sameIdentity(value, prepared)) reject("capture_identity_mismatch", "输入不属于已冻结请求。");
    const keys = ["source", "conversationUrl", "sourceUserMessageId", "sourceUnitKey", "promptText", "observedAt", "profile"];
    if (prepared.images) keys.push("images");
    const evidence = exact(value.evidence, keys);
    if (prepared.images) validateImageEvidence(evidence.images, prepared.images, "attached");
    const unit = DOM_UNIT.exec(evidence.sourceUnitKey);
    if (evidence.source !== "browser_dom" || !conversationUrl(evidence.conversationUrl) || !UUID.test(evidence.sourceUserMessageId)
        || !unit || unit[3] !== "user" || evidence.promptText !== prepared.prompt || !isoTime(evidence.observedAt))
      reject("capture_source_mismatch", "缺少确切的同问题实际输入送达证据。");
    exact(evidence.profile, ["requestedProfile", "observedBefore", "observedAfter"]);
    if (evidence.profile.requestedProfile !== prepared.requestedProfile || evidence.profile.observedBefore !== "Instant"
        || evidence.profile.observedAfter !== "Instant") reject("profile_changed", "实际输入档位不符。");
    return value;
  }
  function validateStored(value, prepared) {
    exact(value, ["protocol", "type", "dispatchId", "attemptId", "sourceKind", "actualProfileObserved", "executionCapabilities"]);
    common(value, "stored");
    if (!sameIdentity(value, prepared) || value.sourceKind !== "browser_dom" || value.actualProfileObserved !== "Instant")
      reject("store_identity_mismatch", "本机保存回执不属于当前 DOM 结果。");
    exact(value.executionCapabilities, ["verified", "source"]);
    if (value.executionCapabilities.verified !== false || value.executionCapabilities.source !== "browser_dom_ui_label")
      reject("invalid_capability_receipt", "DOM 标签不能冒充底层推理能力验收。");
    return value;
  }
  function validateRetired(value) {
    exact(value, ["protocol", "type", "dispatchId", "attemptId", "reason"]);
    common(value, "retired");
    if (value.reason !== "original_dispatch_failed") reject("retirement_unverified", "本机未确认原请求已经结束。");
    return value;
  }
  function isoTime(value) {
    // Accept the UTC ISO forms emitted by both JavaScript and Python. Never
    // turn an invalid calendar date or non-UTC offset into an observation.
    return typeof value === "string" && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(value)
      && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 19) === value.slice(0, 19);
  }
  function handshake(type, extra = {}) { return { protocol: PROTOCOL, type, hostName: HOST_NAME, ...extra }; }
  function validateStatus(value) {
    exact(value, ["protocol", "type", "hostName", "enabled", "approved", "configured", "message", "clientReady"]);
    if (value.protocol !== PROTOCOL || value.type !== "status" || value.hostName !== HOST_NAME
        || [value.enabled, value.approved, value.configured, value.clientReady].some(flag => typeof flag !== "boolean"))
      reject("invalid_status", "原生接收端状态契约无效。");
    text(value.message, 1000);
    return value;
  }
  async function sha256(value) {
    return sha256Bytes(new TextEncoder().encode(value));
  }
  async function sha256Bytes(value) {
    const bytes = await root.crypto.subtle.digest("SHA-256", value);
    return [...new Uint8Array(bytes)].map(byte => byte.toString(16).padStart(2, "0")).join("");
  }
  function validateImages(value) {
    if (!Array.isArray(value) || !value.length || value.length > 4) reject("images_invalid", "本次确切图片数量无效。");
    const ids = new Set(); let total = 0;
    for (const image of value) {
      exact(image, ["id", "name", "mimeType", "size", "sha256"], "images_invalid");
      const suffixes = { "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif" };
      const suffix = typeof image.mimeType === "string" && Object.prototype.hasOwnProperty.call(suffixes, image.mimeType) ? suffixes[image.mimeType] : null;
      if (typeof image.id !== "string" || !DISPATCH.test(image.id) || ids.has(image.id) || !suffix || image.name !== `console-${image.id}${suffix}`
          || !Number.isInteger(image.size) || image.size <= 0 || image.size > MAX_IMAGE_BYTES || typeof image.sha256 !== "string" || !SHA.test(image.sha256))
        reject("images_invalid", "图片身份、名称、格式或大小与冻结内容不符。");
      ids.add(image.id); total += image.size;
    }
    if (total > MAX_IMAGE_TOTAL) reject("images_invalid", "本次选图总大小超过上限。");
    return value;
  }
  function validateAttachmentsContract(value, surface) {
    exact(value, ["version", "verified", "surface", "capturedAt", "source", "observationSha256", "selectors"], "images_contract_unverified");
    if (value.version !== 1 || value.verified !== true || value.surface !== surface || !["chrome", "edge"].includes(surface)
        || value.source !== "cua" || !isoTime(value.capturedAt) || !SHA.test(value.observationSha256))
      reject("images_contract_unverified", "没有实际浏览器核对的图片上传与来源契约。");
    exact(value.selectors, ["input", "ready", "pending", "source"], "images_contract_unverified");
    for (const selector of Object.values(value.selectors)) nonempty(selector, 1000, "images_contract_unverified");
    return value;
  }
  function sameImages(left, right) {
    return Array.isArray(left) && Array.isArray(right) && left.length === right.length
      && left.every((image, index) => ["id", "name", "mimeType", "size", "sha256"].every(key => image[key] === right[index]?.[key]));
  }
  function validateImageEvidence(value, images, status) {
    exact(value, ["status", "items"], "images_evidence_mismatch");
    validateImages(value.items);
    if (value.status !== status || !sameImages(value.items, images)) reject("images_evidence_mismatch", "图片上传或实际消息附件与本轮选择不一致。");
    return value;
  }
  function validateImageChunk(value) {
    exact(value, ["protocol", "type", "dispatchId", "attemptId", "image", "index", "count", "data", "chunkSha256"]);
    common(value, "imageChunk"); validateImages([value.image]);
    const count = Math.ceil(value.image.size / IMAGE_CHUNK_BYTES);
    if (!Number.isInteger(value.index) || value.index < 0 || value.index >= count || value.count !== count || !SHA.test(value.chunkSha256)
        || typeof value.data !== "string" || value.data.length > Math.ceil(IMAGE_CHUNK_BYTES / 3) * 4
        || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value.data))
      reject("image_chunk_invalid", "图片分片身份、顺序或大小无效。");
    const expected = Math.min(IMAGE_CHUNK_BYTES, value.image.size - value.index * IMAGE_CHUNK_BYTES);
    let binary;
    try { binary = root.atob(value.data); } catch { reject("image_chunk_invalid", "图片分片编码无效。"); }
    if (binary.length !== expected || root.btoa(binary) !== value.data) reject("image_chunk_invalid", "图片分片字节数量不符。");
    return Uint8Array.from(binary, character => character.charCodeAt(0));
  }
  function messageIds(value) {
    text(value, 1000, "capture_source_mismatch");
    let values;
    try { values = JSON.parse(value); } catch { values = [value]; }
    if (typeof values === "string") values = [values];
    if (!Array.isArray(values) || !values.length || values.some(id => typeof id !== "string" || !UUID.test(id)))
      reject("capture_source_mismatch", "页面消息 ID 属性不是实际 UUID 列表。");
    const unique = [...new Set(values)];
    if (unique.length !== 1) reject("capture_source_mismatch", "页面消息 ID 归属不唯一。");
    return unique[0];
  }
  root.ConsoleChatRelay = Object.freeze({ PROTOCOL, HOST_NAME, EXTENSION_ID, MAX_PROMPT, MAX_ANSWER, IMAGE_CHUNK_BYTES, MAX_IMAGE_BYTES, MAX_IMAGE_TOTAL,
    validateImages, validateAttachmentsContract, validateImageEvidence, sameImages, validateImageChunk, sha256Bytes, RelayError, reject, exact, text, nonempty, common,
    envelope, sameIdentity, validateDom, validatePrepare, validateCommit, validatePrepared, validateReadiness, validatePageReady, validateFailure,
    validateCapture, validateAccepted, validateStored, validateRetired, rootUrl, conversationUrl, sha256, messageIds, isoTime, handshake, validateStatus });
})(globalThis);
