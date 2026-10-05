/* Reads only the worker-authorized, newly created tab; never page instructions. */
(function (root) {
  "use strict";
  const R = root.ConsoleChatRelay, CONTENT_PREFIX = "consoleChatRelayAttempt:";
  function createController(env) {
    let state = null, serial = Promise.resolve();
    const queue = fn => { const next = serial.then(fn); serial = next.catch(() => {}); return next; };
    const selectors = () => state.prepare.domContract.selectors;
    function visible(node) {
      return !!node && node.isConnected !== false && node.hidden !== true && typeof node.getClientRects === "function" && node.getClientRects().length > 0;
    }
    function all(selector, scope = env.document) {
      try { return [...scope.querySelectorAll(selector)].filter(visible); }
      catch { R.reject("dom_contract_changed", "已核对的 DOM 选择器不能匹配当前页面。"); }
    }
    function one(selector, scope = env.document) {
      const nodes = all(selector, scope);
      if (nodes.length !== 1) R.reject("dom_contract_changed", "缺少唯一已核对的可见页面控件。");
      return nodes[0];
    }
    function profile() {
      const node = one(selectors().profile), raw = String(node.textContent || "").trim();
      const effort = node.getAttribute("data-selected-reasoning-effort");
      if (!["Instant", "Thinking effortInstant"].includes(raw) || effort !== "none")
        R.reject("profile_changed", "未观察到实际 Instant/none 控件；不切换未知控件或降档。");
      return { label: "Instant", dom: { text: raw, reasoningEffort: effort } };
    }
    function composerText(node) { return String(node.innerText ?? node.textContent ?? ""); }
    function completion() { return all(selectors().completion).some(node => String(node.textContent || "").trim() === "Response complete"); }
    function stopPresent() { return all(selectors().stop).length > 0; }
    function messageNodes() {
      const entries = new Map();
      for (const node of all(selectors().messages)) {
        const unit = node.getAttribute("data-chatgpt-search-unit-key"), match = /^fallback-turn-(\d+):(\d+):(user|assistant)$/.exec(unit || "");
        if (!match) R.reject("dom_message_unverified", "实际 DOM 单位格式未经本版本核对。");
        const id = R.messageIds(node.getAttribute("data-chatgpt-search-message-ids"));
        const bodyNodes = all(match[3] === "user" ? selectors().userText : selectors().assistantText, node);
        if (bodyNodes.length !== 1) R.reject("dom_message_unverified", "缺少唯一原文子节点，不能抓取反应、标题或工具输出。");
        const body = bodyNodes[0];
        const text = match[3] === "user" ? String(body.textContent || "") : String(body.innerText ?? body.textContent ?? "");
        const value = { id, unit, role: match[3], text }, key = id + "\n" + unit;
        if (entries.has(key) && entries.get(key).text !== text) R.reject("dom_source_ambiguous", "重复 DOM 节点的实际原文不一致。");
        entries.set(key, value);
      }
      return [...entries.values()];
    }
    function inspectFresh(expectedComposer = "") {
      if (!R.rootUrl(env.location.href)) R.reject("not_fresh_chat", "页面不是扩展自己的空白普通新 Chat。");
      const choice = one(selectors().chatMode);
      if (choice.getAttribute("aria-pressed") !== "true") R.reject("not_ordinary_chat", "未核对到已选普通 Chat 模式。");
      one(selectors().login);
      const composer = one(selectors().composer);
      if (composer.getAttribute("role") !== "textbox" || composer.getAttribute("contenteditable") !== "true"
          || composerText(composer) !== expectedComposer) R.reject("composer_changed", "输入框不空或已有用户草稿，不覆盖。");
      if (messageNodes().length || completion() || stopPresent()) R.reject("not_fresh_chat", "页面已有消息、生成或结束标记，不使用旧聊天。");
      return { composer, profile: profile() };
    }
    function disconnectObserver() {
      if (state?.observer) state.observer.disconnect();
      if (state?.acceptDeadline) env.clearTimeout(state.acceptDeadline);
      if (state?.completionDeadline) env.clearTimeout(state.completionDeadline);
    }
    async function emit(value) {
      const response = await env.chrome.runtime.sendMessage(value);
      if (response?.received !== true) R.reject("native_result_not_received", "本机扩展未确认接收准确页面证据。");
    }
    async function fail(code, message) {
      if (!state || state.phase === "needs_review" || state.phase === "captured") return;
      state.phase = "needs_review"; disconnectObserver();
      try { await emit(R.envelope("uncertain", state.prepare, { code, message })); } catch { /* The durable intent remains; never click again. */ }
    }
    async function observeCommitted() {
      if (!state || state.phase !== "waiting") return;
      if (!R.conversationUrl(env.location.href)) return;
      const observedProfile = profile(), messages = messageNodes(), users = messages.filter(node => node.role === "user"), answers = messages.filter(node => node.role === "assistant");
      if (users.length > 1) R.reject("other_user_input", "专用页面出现额外用户输入，回答归属需核对。");
      if (users.length !== 1 || users[0].text !== state.prepare.prompt) return;
      const user = users[0], seenAt = new Date(env.now()).toISOString();
      if (state.accepted && (state.accepted.sourceUserMessageId !== user.id || state.accepted.sourceUnitKey !== user.unit
          || state.accepted.conversationUrl !== env.location.href)) R.reject("source_changed", "实际输入来源已变化，不能改绑回答。");
      const profileEvidence = { requestedProfile: state.prepare.requestedProfile, observedBefore: state.observedBefore, observedAfter: observedProfile.label };
      if (!state.accepted) {
        const accepted = R.envelope("accepted", state.prepare, { evidence: { source: "browser_dom", conversationUrl: env.location.href,
          sourceUserMessageId: user.id, sourceUnitKey: user.unit, promptText: user.text, observedAt: seenAt, profile: profileEvidence } });
        R.validateAccepted(accepted, state.prepare);
        state.accepted = accepted.evidence;
        env.clearTimeout(state.acceptDeadline);
        await emit(accepted);
      }
      if (!completion() || stopPresent()) return;
      if (answers.length !== 1) R.reject("final_source_ambiguous", "结束后没有唯一主回答，不能把工具或多个成果拼作答案。");
      const answer = answers[0];
      const captured = R.envelope("capture", state.prepare, { evidence: { source: "browser_dom", conversationUrl: env.location.href,
        sourceUserMessageId: user.id, assistantMessageId: answer.id, sourceUnitKey: user.unit, assistantUnitKey: answer.unit,
        promptText: user.text, answerText: answer.text, completion: { text: "Response complete", observedAfterCommit: true, stopPresent: false },
        profile: profileEvidence, observedAt: seenAt } });
      R.validateCapture(captured, state.prepare);
      await emit(captured); state.phase = "captured"; disconnectObserver();
    }
    function observeEvent() {
      queue(observeCommitted).catch(error => queue(() => fail(error.code || "capture_unknown", String(error?.message || "实际回答归属需核对。"))));
    }
    async function prepare(value) {
      R.validatePrepare(value);
      if (state) R.reject("page_already_prepared", "页面已有准备记录，不能重复准备或重发。");
      if (await R.sha256(value.prompt) !== value.promptSha256) R.reject("prompt_hash_mismatch", "完整冻结问题 SHA 不符。");
      const key = CONTENT_PREFIX + value.dispatchId;
      if ((await env.chrome.storage.local.get(key))?.[key]) R.reject("dispatch_already_attempted", "该请求已有页面提交意图，只能核对。");
      state = { prepare: structuredClone(value), phase: "preparing", key, observedBefore: null, accepted: null };
      const fresh = inspectFresh(); state.observedBefore = fresh.profile.label; state.phase = "prepared";
      return R.envelope("prepared", value, { observation: { url: env.location.href, chatMode: true, loginVerified: true, emptyComposer: true,
        observedProfile: fresh.profile.label, completionInitiallyPresent: false, surface: "chrome",
        observationSha256: value.domContract.observationSha256, profileDom: fresh.profile.dom } });
    }
    async function commit(value) {
      R.validateCommit(value);
      if (!state || state.phase !== "prepared" || !R.sameIdentity(value, state.prepare)) R.reject("commit_not_prepared", "没有本次唯一已准备的页面，不点 Send。");
      inspectFresh();
      if ((await env.chrome.storage.local.get(state.key))?.[state.key]) R.reject("dispatch_already_attempted", "该请求已有提交记录，不重复点击。");
      state.phase = "send_intent";
      await env.chrome.storage.local.set({ [state.key]: { dispatchId: value.dispatchId, attemptId: value.attemptId,
        promptSha256: state.prepare.promptSha256, phase: "send_intent", at: new Date(env.now()).toISOString() } });
      // Reobserve after async persistence: a user's late draft or tier change must win.
      const fresh = inspectFresh(), composer = fresh.composer;
      composer.focus(); composer.textContent = state.prepare.prompt;
      composer.dispatchEvent(new env.InputEvent("input", { bubbles: true, inputType: "insertText", data: state.prepare.prompt }));
      if (composerText(composer) !== state.prepare.prompt) R.reject("composer_not_matching", "页面输入没有完整冻结文字，不能发送。");
      inspectFresh(state.prepare.prompt);
      const send = one(selectors().send);
      if (send.disabled || send.getAttribute("aria-disabled") === "true" || send.getAttribute("type") !== "submit")
        R.reject("send_not_available", "未观察到唯一可用的真实 Send 控件。");
      state.observer = new env.MutationObserver(observeEvent);
      state.observer.observe(env.document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true });
      state.phase = "waiting";
      state.acceptDeadline = env.setTimeout(() => queue(() => fail("send_not_verified", "提交后十秒内没有确切同问题 URL/来源证据，保留核对，不重发。")), 10000);
      state.completionDeadline = env.setTimeout(() => queue(() => fail("completion_not_verified", "有界等待内未取得唯一结束回答；保留核对，不重发。")), 120000);
      // Exactly one click. A throwing click is an unknown outcome, never a retry.
      send.click();
      observeEvent();
      return { committed: true };
    }
    async function receive(value) {
      try {
        if (value?.type === "relay.content.prepare") { R.exact(value, ["type", "prepare"]); return await prepare(value.prepare); }
        if (value?.type === "relay.content.commit") { R.exact(value, ["type", "commit"]); return await commit(value.commit); }
        R.reject("unknown_page_control", "网页正文和未知消息不能授权输入或发送。");
      } catch (error) {
        if (state && ["send_intent", "waiting"].includes(state.phase)) await fail(error.code || "send_unknown", String(error?.message || "提交结果不明，不能重发。"));
        throw error;
      }
    }
    return { receive: value => queue(() => receive(value)), observe: () => queue(observeCommitted), idle: () => serial,
      phase: () => state?.phase || "idle", stop: () => { disconnectObserver(); if (state) state.phase = "needs_review"; } };
  }
  root.ConsoleChatRelayContent = Object.freeze({ createController, CONTENT_PREFIX });
  if (root.chrome?.runtime?.onMessage && root.document && root.location && root.MutationObserver) {
    const controller = createController({ chrome: root.chrome, document: root.document, location: root.location,
      MutationObserver: root.MutationObserver, InputEvent: root.InputEvent, now: () => Date.now(), setTimeout: root.setTimeout, clearTimeout: root.clearTimeout });
    root.chrome.runtime.onMessage.addListener((value, sender, reply) => {
      if (sender?.id !== R.EXTENSION_ID || !["relay.content.prepare", "relay.content.commit"].includes(value?.type)) return false;
      controller.receive(value).then(reply, error => reply({ committed: false, code: error?.code || "page_control_rejected" }));
      return true;
    });
    root.addEventListener("pagehide", () => controller.stop(), { once: true });
  }
})(globalThis);
