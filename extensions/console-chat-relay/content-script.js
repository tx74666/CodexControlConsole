/* Reads only the worker-authorized, newly created tab; never page instructions. */
(function (root) {
  "use strict";
  const R = root.ConsoleChatRelay, CONTENT_PREFIX = "consoleChatRelayAttempt:";
  function createController(env) {
    let state = null, readiness = null, serial = Promise.resolve();
    const queue = fn => { const next = serial.then(fn); serial = next.catch(() => {}); return next; };
    const selectors = () => (state?.prepare || readiness?.request).domContract.selectors;
    function visible(node) {
      if (!node || node.isConnected === false || typeof node.getClientRects !== "function" || !node.getClientRects().length) return false;
      for (let current = node; current; current = current.parentElement) {
        if (current.hidden === true || current.inert === true || current.getAttribute?.("inert") != null
            || String(current.getAttribute?.("aria-hidden") || "").toLowerCase() === "true") return false;
      }
      return true;
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
      if (!["Instant", "Thinking effortInstant", "思考强度Instant", "思考强度即时"].includes(raw) || effort !== "none"
          || node.getAttribute("aria-expanded") !== "false")
        R.reject("profile_changed", "未观察到实际 Instant/none 控件；不切换未知控件或降档。");
      return { label: "Instant", dom: { text: raw, reasoningEffort: effort } };
    }
    function composerText(node) {
      const raw = String(node.innerText ?? node.textContent ?? "");
      // CUA observed a rendered newline in the otherwise text-empty editor.
      // A real textContent newline/space remains a user draft, without trimming.
      return node.textContent === "" && raw === "\n" ? "" : raw;
    }
    function completion() {
      const markers = all(selectors().completion).map(node => String(node.textContent || "").trim())
        .filter(text => ["Response complete", "回答已完成"].includes(text));
      if (markers.length > 1) R.reject("dom_completion_ambiguous", "没有唯一的本次明确结束标记，保留原页面核对。");
      return markers[0] || "";
    }
    function stopPresent() {
      // null records an unobserved control, never a query for the string "null"
      // or an assertion that a generating Stop control is absent.
      return selectors().stop === null ? null : all(selectors().stop).length > 0;
    }
    function messageNodes(readAnswers = true) {
      const entries = new Map();
      for (const node of all(selectors().messages)) {
        const unit = node.getAttribute("data-chatgpt-search-unit-key"), match = /^fallback-turn-(\d+):(\d+):(user|assistant)$/.exec(unit || "");
        if (!match) R.reject("dom_message_unverified", "实际 DOM 单位格式未经本版本核对。");
        // An assistant wrapper can precede its streaming body. Bind the exact
        // user first; require the unique answer body only after completion.
        if (!readAnswers && match[3] === "assistant") continue;
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
    function inspectFresh(expectedComposer = "", requireInstant = true) {
      if (!R.rootUrl(env.location.href)) R.reject("not_fresh_chat", "页面不是扩展自己的空白普通新 Chat。");
      const choice = one(selectors().chatMode);
      if (choice.getAttribute("aria-pressed") !== "true") R.reject("not_ordinary_chat", "未核对到已选普通 Chat 模式。");
      one(selectors().login);
      const composer = one(selectors().composer);
      if (composer.getAttribute("role") !== "textbox" || composer.getAttribute("contenteditable") !== "true"
          || composerText(composer) !== expectedComposer) R.reject("composer_changed", "输入框不空或已有用户草稿，不覆盖。");
      if (messageNodes().length || completion() || stopPresent() === true) R.reject("not_fresh_chat", "页面已有消息、生成或结束标记，不使用旧聊天。");
      return { composer, profileControl: one(selectors().profile), profile: requireInstant ? profile() : null };
    }
    function freshObservation(contract, fresh) {
      return { url: env.location.href, chatMode: true, loginVerified: true, emptyComposer: true,
        observedProfile: fresh.profile.label, completionInitiallyPresent: false, surface: contract.surface,
        observationSha256: contract.observationSha256, profileDom: fresh.profile.dom };
    }
    function checkReadiness(value) {
      R.validateReadiness(value);
      if (state || readiness) R.reject("page_already_checked", "专用页面已有本次就绪或准备记录，不能重新绑定。");
      const current = readiness = { request: structuredClone(value), phase: "checking", cancel: null };
      return new Promise((resolve, reject) => {
        let done = false, observer, deadline;
        const finish = (error, fresh) => {
          if (done) return;
          done = true; observer?.disconnect();
          if (deadline !== undefined) env.clearTimeout(deadline);
          current.cancel = null; current.phase = error ? "cancelled" : "ready";
          if (error) reject(error);
          else resolve(R.envelope("pageReady", value, { observation: { url: env.location.href, chatMode: true,
            loginVerified: true, emptyComposer: true, modelControlPresent: true, completionInitiallyPresent: false,
            surface: value.domContract.surface, observationSha256: value.domContract.observationSha256 } }));
        };
        const check = () => {
          if (done) return;
          try {
            if (current.phase !== "checking") R.reject("readiness_cancelled", "本次只读就绪等待已停止。");
            if (!R.rootUrl(env.location.href)) R.reject("not_fresh_chat", "页面不是本次专用普通新 Chat。");
            // Missing initial React controls may arrive after document_idle.
            // This probe observes presence only; it never selects or proves a tier.
            let missing = false;
            for (const key of ["chatMode", "login", "composer", "profile"]) {
              const nodes = all(selectors()[key]);
              if (nodes.length > 1) R.reject("dom_contract_changed", "只读就绪检查发现重复的可见控件。");
              if (!nodes.length) missing = true;
            }
            if (missing) return;
            finish(null, inspectFresh("", false));
          } catch (error) { finish(error); }
        };
        current.cancel = () => finish(new R.RelayError("readiness_cancelled", "本次只读就绪等待已停止，不输入或发送。"));
        observer = new env.MutationObserver(check);
        observer.observe(env.document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true });
        deadline = env.setTimeout(() => finish(new R.RelayError("page_ready_timeout", "六十秒内未核对到实际空白 Chat、登录与档位控件，不输入或发送。")), 60000);
        // Subscribe before the first state check. No periodic DOM probes.
        check();
      });
    }
    function disconnectObserver() {
      state?.cancelProfileWait?.();
      state?.cancelSendWait?.();
      if (state?.observer) state.observer.disconnect();
      if (state?.acceptDeadline) env.clearTimeout(state.acceptDeadline);
    }
    // Exact CUA-observed menu states. Pro's initial medium attribute is an
    // observed UI value, never an inferred model or requested Pro mapping.
    const pickerSteps = [
      { text: "Instant，第 1 项，共 5 项。", effort: "none" },
      { text: "Medium，第 2 项，共 5 项。", effort: "medium" },
      { text: "High，第 3 项，共 5 项。", effort: "high" },
      { text: "Extra High，第 4 项，共 5 项。", effort: "max" },
      { text: "Pro，第 5 项，共 5 项。", effort: "medium" }
    ];
    const sliderSelector = '[role="menuitem"][data-reasoning-slider="true"][aria-label="强度"][aria-keyshortcuts="ArrowLeft ArrowRight"]';
    const pickerStatusSelector = '[role="status"][aria-live="polite"]';
    function pickerBinding(button) {
      const menus = all('[role="menu"]');
      if (menus.length > 1) R.reject("profile_picker_unverified", "档位菜单不唯一，不操作未知菜单。");
      if (!menus.length) return null;
      const menu = menus[0], buttonId = button.getAttribute("id"), menuId = menu.getAttribute("id");
      if (!buttonId || !menuId || button.getAttribute("aria-haspopup") !== "menu" || button.getAttribute("aria-expanded") !== "true"
          || menu.getAttribute("aria-labelledby") !== buttonId || button.getAttribute("aria-controls") !== menuId)
        R.reject("profile_picker_unverified", "档位菜单没有准确绑定原控件，不选择。");
      const sliders = all(sliderSelector, menu), statuses = all(pickerStatusSelector, menu);
      if (sliders.length > 1 || statuses.length > 1) R.reject("profile_picker_unverified", "档位滑块或状态不唯一，不选择。");
      if (!sliders.length || !statuses.length) return null;
      return { menu, slider: sliders[0], status: statuses[0] };
    }
    function pickerSnapshot(button) {
      const binding = pickerBinding(button);
      if (!binding) return null;
      const raw = String(binding.status.textContent || "");
      if (!raw) return null;
      const index = pickerSteps.findIndex(step => step.text === raw && step.effort === button.getAttribute("data-selected-reasoning-effort"));
      if (index < 0) R.reject("profile_picker_unverified", "档位状态与实际属性不属于已观察的五项表，不猜测。");
      return { ...binding, index };
    }
    function waitProfile(current, stillPreparing, checkState, action) {
      return new Promise((resolve, reject) => {
        let done = false, observer, deadline;
        const finish = (error, value) => {
          if (done) return;
          done = true; observer?.disconnect();
          if (deadline !== undefined) env.clearTimeout(deadline);
          current.cancelProfileWait = null;
          if (error) reject(error); else resolve(value);
        };
        const check = () => {
          if (done) return;
          try { stillPreparing(); inspectFresh("", false); const value = checkState(); if (value) finish(null, value); }
          catch (error) { finish(error); }
        };
        current.cancelProfileWait = () => finish(new R.RelayError("prepare_cancelled", "本次档位准备已停止，不能恢复选择或发送。"));
        observer = new env.MutationObserver(check);
        observer.observe(env.document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true });
        deadline = env.setTimeout(() => finish(new R.RelayError("profile_selection_timeout", "十秒内未取得准确档位状态，保留原请求，不输入或发送。")), 10000);
        try { stillPreparing(); inspectFresh("", false); action?.(); check(); }
        catch (error) { finish(error); }
      });
    }
    async function selectInstant(current, stillPreparing) {
      const initial = inspectFresh("", false), button = initial.profileControl;
      try { profile(); if (!all('[role="menu"]').length) return; }
      catch (error) { if (error?.code !== "profile_changed") throw error; }
      if (button.tagName !== "BUTTON" || !button.getAttribute("id") || button.getAttribute("aria-haspopup") !== "menu"
          || button.getAttribute("aria-expanded") !== "false" || all('[role="menu"]').length
          || typeof button.click !== "function" || typeof env.KeyboardEvent !== "function")
        R.reject("profile_picker_unverified", "没有已观察的唯一关闭档位按钮，不操作现有或未知菜单。");
      const originalButton = () => {
        stillPreparing();
        if (inspectFresh("", false).profileControl !== button) R.reject("profile_changed", "原档位控件已被替换，停止选择。");
      };
      let snapshot = await waitProfile(current, stillPreparing, () => { originalButton(); return pickerSnapshot(button); }, () => { originalButton(); button.click(); });
      const boundMenu = snapshot.menu, boundSlider = snapshot.slider, boundStatus = snapshot.status;
      const boundIdentity = () => {
        originalButton(); const found = pickerBinding(button);
        if (!found || found.menu !== boundMenu || found.slider !== boundSlider || found.status !== boundStatus)
          R.reject("profile_picker_unverified", "原档位菜单、滑块或状态已改变，停止选择。");
      };
      const boundSnapshot = () => {
        boundIdentity(); const found = pickerSnapshot(button);
        if (!found) R.reject("profile_picker_unverified", "原档位状态暂不可核对，停止选择。");
        return found;
      };
      let steps = 0;
      while (snapshot.index > 0) {
        if (++steps > 4) R.reject("profile_picker_unverified", "档位步骤超出已观察范围，不继续选择。");
        const previous = snapshot.index, next = previous - 1;
        snapshot = await waitProfile(current, stillPreparing, () => {
          const found = boundSnapshot();
          if (found.index === previous) return null;
          if (found.index !== next) R.reject("profile_picker_unverified", "档位没有按已观察的一项左移，不继续选择。");
          return found;
        }, () => {
          if (boundSnapshot().index !== previous) R.reject("profile_changed", "键盘选择前档位已改变，不操作。");
          boundSlider.focus(); originalButton();
          if (boundSnapshot().index !== previous) R.reject("profile_changed", "聚焦后档位已改变，不操作。");
          boundSlider.dispatchEvent(new env.KeyboardEvent("keydown", { key: "ArrowLeft", code: "ArrowLeft", bubbles: true, cancelable: true, repeat: false }));
          // React may update the ordinal asynchronously, but a retired or
          // inactive original slider must never receive the keyup operation.
          boundIdentity();
          boundSlider.dispatchEvent(new env.KeyboardEvent("keyup", { key: "ArrowLeft", code: "ArrowLeft", bubbles: true, cancelable: true, repeat: false }));
        });
      }
      await waitProfile(current, stillPreparing, () => {
        originalButton(); const menus = all('[role="menu"]');
        if (menus.length && (menus.length !== 1 || menus[0] !== boundMenu)) R.reject("profile_picker_unverified", "关闭时出现其它菜单，不恢复选择。");
        if (button.getAttribute("aria-expanded") === "true" || menus.length) return null;
        if (String(button.textContent || "").trim() === "思考强度思考强度") return null;
        return inspectFresh();
      }, () => { if (boundSnapshot().index !== 0) R.reject("profile_changed", "关闭前 Instant 观测已改变，不操作。"); button.click(); });
      stillPreparing(); inspectFresh();
    }
    function waitForSend() {
      return new Promise((resolve, reject) => {
        let done = false, observer, deadline;
        const finish = (error, send) => {
          if (done) return;
          done = true; observer?.disconnect();
          if (deadline !== undefined) env.clearTimeout(deadline);
          state.cancelSendWait = null;
          if (error) reject(error); else resolve(send);
        };
        const check = () => {
          if (done) return;
          try {
            if (state.phase !== "send_intent") R.reject("send_cancelled", "本次输入已停止，不能点击 Send。");
            inspectFresh(state.prepare.prompt);
            const nodes = all(selectors().send);
            if (nodes.length > 1) R.reject("send_not_available", "真实发送控件不唯一，不能发送。");
            if (!nodes.length) return;
            const send = nodes[0];
            if (send.getAttribute("type") !== "submit") R.reject("send_not_available", "发送控件类型已经变化。");
            if (send.disabled || send.getAttribute("aria-disabled") === "true") return;
            finish(null, send);
          } catch (error) { finish(error); }
        };
        state.cancelSendWait = () => finish(new R.RelayError("send_cancelled", "本次输入已停止，发送意图保留，不自动重发。"));
        observer = new env.MutationObserver(check);
        observer.observe(env.document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true });
        deadline = env.setTimeout(() => finish(new R.RelayError("send_not_available", "十秒内未取得实际可用的 Send 控件，保留输入与意图，不自动重发。")), 10000);
        // React may publish the enabled button after the input handler returns.
        // Subscribe first, then inspect; DOM events alone drive this bounded wait.
        check();
      });
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
      const observedProfile = profile(), users = messageNodes(false);
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
      const completionText = completion();
      const observedStop = stopPresent();
      if (!completionText || observedStop === true || state.completionAbsentAtCommit !== true) return;
      const answers = messageNodes().filter(node => node.role === "assistant");
      if (answers.length !== 1) R.reject("final_source_ambiguous", "结束后没有唯一主回答，不能把工具或多个成果拼作答案。");
      const answer = answers[0];
      const captured = R.envelope("capture", state.prepare, { evidence: { source: "browser_dom", conversationUrl: env.location.href,
        sourceUserMessageId: user.id, assistantMessageId: answer.id, sourceUnitKey: user.unit, assistantUnitKey: answer.unit,
        promptText: user.text, answerText: answer.text, completion: { text: completionText,
          observedAfterCommit: state.completionAbsentAtCommit === true, stopPresent: observedStop },
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
      if (readiness && (readiness.phase !== "ready" || !R.sameIdentity(value, readiness.request)
          || JSON.stringify(value.domContract) !== JSON.stringify(readiness.request.domContract)))
        R.reject("readiness_identity_mismatch", "准备请求没有匹配本次已核对的只读就绪记录。");
      const key = CONTENT_PREFIX + value.dispatchId;
      // Claim the in-memory identity before the first async boundary. Cancel
      // can then stop SHA/storage waits without a later assignment reviving it.
      const current = state = { prepare: structuredClone(value), phase: "preparing", key, observedBefore: null, accepted: null, clickStarted: false };
      const stillPreparing = () => {
        if (state !== current || current.phase !== "preparing") R.reject("prepare_cancelled", "本次页面准备已停止，不能恢复输入或发送。");
      };
      const actualSha = await R.sha256(value.prompt); stillPreparing();
      if (actualSha !== value.promptSha256) R.reject("prompt_hash_mismatch", "完整冻结问题 SHA 不符。");
      const prior = await env.chrome.storage.local.get(key); stillPreparing();
      if (prior?.[key]) R.reject("dispatch_already_attempted", "该请求已有页面提交意图，只能核对。");
      await selectInstant(current, stillPreparing); stillPreparing();
      const fresh = inspectFresh(); current.observedBefore = fresh.profile.label; current.phase = "prepared";
      return R.envelope("prepared", value, { observation: freshObservation(value.domContract, fresh) });
    }
    async function commit(value) {
      R.validateCommit(value);
      if (!state || state.phase !== "prepared" || !R.sameIdentity(value, state.prepare)) R.reject("commit_not_prepared", "没有本次唯一已准备的页面，不点 Send。");
      inspectFresh();
      if ((await env.chrome.storage.local.get(state.key))?.[state.key]) R.reject("dispatch_already_attempted", "该请求已有提交记录，不重复点击。");
      if (state.phase !== "prepared") R.reject("send_cancelled", "本次输入已停止，不能恢复提交。");
      state.phase = "send_intent";
      await env.chrome.storage.local.set({ [state.key]: { dispatchId: value.dispatchId, attemptId: value.attemptId,
        promptSha256: state.prepare.promptSha256, phase: "send_intent", at: new Date(env.now()).toISOString() } });
      // Reobserve after async persistence: a user's late draft or tier change must win.
      if (state.phase !== "send_intent") R.reject("send_cancelled", "本次输入已停止，不能输入或点击 Send。");
      const fresh = inspectFresh(), composer = fresh.composer;
      composer.focus(); composer.textContent = state.prepare.prompt;
      composer.dispatchEvent(new env.InputEvent("input", { bubbles: true, inputType: "insertText", data: state.prepare.prompt }));
      if (composerText(composer) !== state.prepare.prompt) R.reject("composer_not_matching", "页面输入没有完整冻结文字，不能发送。");
      inspectFresh(state.prepare.prompt);
      const send = await waitForSend();
      inspectFresh(state.prepare.prompt);
      if (state.phase !== "send_intent" || one(selectors().send) !== send || send.disabled || send.getAttribute("aria-disabled") === "true"
          || send.getAttribute("type") !== "submit") R.reject("send_not_available", "点击前真实发送控件或请求状态已经变化。");
      // inspectFresh just proved no completion marker on this owned blank
      // conversation. The observer is installed before its sole Send click.
      state.completionAbsentAtCommit = true;
      state.observer = new env.MutationObserver(observeEvent);
      state.observer.observe(env.document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true });
      state.phase = "waiting";
      state.acceptDeadline = env.setTimeout(() => queue(() => fail("send_not_verified", "提交后十秒内没有确切同问题 URL/来源证据，保留核对，不重发。")), 10000);
      // Once the exact input is accepted, remain idle on DOM events until its
      // final or an attribution failure. Slow generation is not a send failure.
      // Exactly one click. A throwing click is an unknown outcome, never a retry.
      state.clickStarted = true; send.click();
      observeEvent();
      return { committed: true };
    }
    async function receive(value) {
      try {
        if (value?.type === "relay.content.readiness") { R.exact(value, ["type", "readiness"]); return await checkReadiness(value.readiness); }
        if (value?.type === "relay.content.prepare") { R.exact(value, ["type", "prepare"]); return await prepare(value.prepare); }
        if (value?.type === "relay.content.commit") { R.exact(value, ["type", "commit"]); return await commit(value.commit); }
        R.reject("unknown_page_control", "网页正文和未知消息不能授权输入或发送。");
      } catch (error) {
        // The worker alone reports a failed control reply. Emitting a second
        // asynchronous failure would race it and can deadlock both queues.
        if (state && value?.type === "relay.content.commit") { state.phase = "needs_review"; disconnectObserver(); }
        throw error;
      }
    }
    function cancel(value) {
      R.exact(value, ["protocol", "type", "dispatchId", "attemptId"]); R.common(value, "cancel");
      if (!state && readiness && R.sameIdentity(value, readiness.request)) {
        readiness.cancel?.(); readiness.phase = "cancelled";
        return { cancelled: true };
      }
      if (!state || !R.sameIdentity(value, state.prepare)) R.reject("cancel_identity_mismatch", "停止消息不属于当前专用页面。");
      state.phase = "needs_review"; disconnectObserver();
      return { cancelled: true };
    }
    return { receive: value => queue(() => receive(value)), cancel, clickStarted: () => state?.clickStarted === true,
      observe: () => queue(observeCommitted), idle: () => serial,
      phase: () => state?.phase || "idle", stop: () => { readiness?.cancel?.(); if (readiness) readiness.phase = "cancelled";
        disconnectObserver(); if (state) state.phase = "needs_review"; } };
  }
  root.ConsoleChatRelayContent = Object.freeze({ createController, CONTENT_PREFIX });
  if (root.chrome?.runtime?.onMessage && root.document && root.location && root.MutationObserver) {
    const controller = createController({ chrome: root.chrome, document: root.document, location: root.location,
      MutationObserver: root.MutationObserver, InputEvent: root.InputEvent, KeyboardEvent: root.KeyboardEvent, now: () => Date.now(),
      setTimeout: (...args) => root.setTimeout(...args), clearTimeout: (...args) => root.clearTimeout(...args) });
    root.chrome.runtime.onMessage.addListener((value, sender, reply) => {
      if (sender?.id !== R.EXTENSION_ID || !["relay.content.readiness", "relay.content.prepare", "relay.content.commit", "relay.content.cancel"].includes(value?.type)) return false;
      if (value.type === "relay.content.cancel") {
        try { R.exact(value, ["type", "cancel"]); reply(controller.cancel(value.cancel)); }
        catch (error) { reply({ cancelled: false, code: error?.code || "page_control_rejected" }); }
        return false;
      }
      controller.receive(value).then(reply, error => {
        const identity = value.type === "relay.content.readiness" ? value.readiness : value.type === "relay.content.prepare" ? value.prepare : value.commit;
        try {
          reply(R.envelope(value.type === "relay.content.commit" ? "uncertain" : "blocked", identity,
            { code: error?.code || "page_control_rejected", message: String(error?.message || "页面控制失败，不能重发。"),
              ...(value.type === "relay.content.commit" ? { clickStarted: controller.clickStarted() } : {}) }));
        } catch { reply({ committed: false, code: "page_control_rejected" }); }
      });
      return true;
    });
    // document_idle registers the real receiver independently of slow page
    // assets. This carries neither a prompt nor permission to prepare or send.
    if (R.rootUrl(root.location.href)) {
      try { root.chrome.runtime.sendMessage({ protocol: R.PROTOCOL, type: "contentAvailable" })?.catch?.(() => {}); }
      catch { /* The worker's event-first initial probe covers startup races. */ }
    }
    root.addEventListener("pagehide", () => controller.stop(), { once: true });
  }
})(globalThis);
