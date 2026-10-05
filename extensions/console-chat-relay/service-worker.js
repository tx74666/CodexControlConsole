/* Own Chrome extension transport. Default disabled; no model/API/GUI helper. */
importScripts("lib/protocol.js");
(function (root) {
  "use strict";
  const R = root.ConsoleChatRelay, STORAGE_KEY = "consoleChatRelayV1", MAX_TOMBSTONES = 1000;
  function detectBrowserSurface(navigator) {
    const ua = typeof navigator?.userAgent === "string" ? navigator.userAgent : "";
    if (/\b(?:OPR|Opera|Brave|Vivaldi|YaBrowser|SamsungBrowser|UCBrowser|Chromium|Electron|EdgA|EdgiOS|Firefox|FxiOS|HeadlessChrome)\//i.test(ua)) return null;
    const uaSurface = /\bEdg\/\d/.test(ua) ? "edge" : /\bChrome\/\d/.test(ua) ? "chrome" : null;
    const brands = navigator?.userAgentData?.brands;
    if (brands === undefined) return uaSurface;
    if (!Array.isArray(brands) || !brands.length) return null;
    const surfaces = new Set();
    for (const entry of brands) {
      if (typeof entry?.brand !== "string") return null;
      if (entry.brand === "Google Chrome") surfaces.add("chrome");
      else if (entry.brand === "Microsoft Edge") surfaces.add("edge");
      else if (entry.brand !== "Chromium" && entry.brand.replace(/[^a-z]/gi, "").toLowerCase() !== "notabrand") return null;
    }
    if (surfaces.size !== 1) return null;
    const surface = [...surfaces][0];
    return ua && uaSurface !== surface ? null : surface;
  }
  function createController(api, resolveBrowserSurface = () => detectBrowserSurface(root.navigator), timers = { setTimeout, clearTimeout }) {
    let state = { enabled: false, attempts: {}, active: null }, native = null, status = null, nativeReady = false, requestedReady = false;
    let readinessWait = null, preparationGuard = null;
    let lastMessage = "准备包默认停用；尚无生产启用批准或浏览器页面实机验收。", serial = Promise.resolve(), reconnectUsed = false;
    const viewers = new Set();
    const load = api.storage.local.get(STORAGE_KEY).then(result => {
      const saved = result?.[STORAGE_KEY];
      if (!saved) return;
      if (typeof saved.enabled !== "boolean" || !saved.attempts || typeof saved.attempts !== "object" || Array.isArray(saved.attempts))
        R.reject("invalid_local_ledger", "本机扩展账本无效，停止连接。");
      state = saved;
      if (state.active && state.active.phase !== "stored") { state.active.phase = "needs_review"; lastMessage = "上次转发未取得完整保存回执；保留核对，不能重发。"; }
    });
    async function save() { await api.storage.local.set({ [STORAGE_KEY]: structuredClone(state) }); }
    function ownSurface() {
      const surface = resolveBrowserSurface();
      if (!["chrome", "edge"].includes(surface)) R.reject("browser_identity_unverified", "扩展自身浏览器身份未知或互相冲突，停止连接与发送。");
      return surface;
    }
    function queue(fn) {
      const run = serial.then(() => load).then(fn);
      serial = run.catch(() => {});
      return run;
    }
    function send(value) {
      if (!native) R.reject("native_disconnected", "本机接收端连接已断开。");
      native.postMessage(value);
    }
    function cancelOwned(code = "page_ready_cancelled", message = "本次专用页就绪等待已停止，不输入或发送。") {
      const active = state.active;
      if (!active || active.phase === "stored") return;
      // Cancellation is monotonic even while creation/persistence is awaiting
      // and no tab or readiness waiter exists yet. A later ready status cannot
      // turn this same request back into a live preparation.
      if (preparationGuard && R.sameIdentity(preparationGuard.identity, active.prepare)) {
        preparationGuard.cancelled = true; preparationGuard.code = code; preparationGuard.message = message;
      }
      if (!Number.isInteger(active.tabId)) return;
      if (readinessWait && R.sameIdentity(readinessWait.identity, active.prepare)) {
        readinessWait.cancel(code, message); return;
      }
      try {
        const pending = api.tabs.sendMessage(active.tabId, { type: "relay.content.cancel", cancel: R.envelope("cancel", active.prepare) });
        pending?.catch?.(() => {});
      } catch { /* The existing intent remains uncertain; no substitute Send. */ }
    }
    function preemptNative(value) {
      // A terminal receipt must stop an in-progress DOM wait immediately,
      // before serial handling can be delayed behind that same commit.
      const active = state.active;
      if (!active || active.phase === "stored" || !R.sameIdentity(value, active.prepare)) return;
      try {
        if (value?.type === "retired") {
          R.validateRetired(value);
          const prior = state.attempts[value.dispatchId];
          if (!prior || prior.attemptId !== value.attemptId || prior.phase === "stored") return;
        } else if (["blocked", "uncertain"].includes(value?.type)) R.validateFailure(value);
        else return;
        cancelOwned();
      } catch { /* Invalid or foreign receipts cannot cancel an owned page. */ }
    }
    function receiveNative(value) { preemptNative(value); return queue(() => handleNative(value)); }
    async function fail(identity, code, message, uncertain = true, notify = true) {
      const value = R.envelope(uncertain ? "uncertain" : "blocked", identity, { code, message });
      if (state.active && state.active.phase !== "stored" && R.sameIdentity(value, state.active.prepare)) {
        cancelOwned();
        const knownUnsent = uncertain === false && ["preparing", "prepared"].includes(state.active.phase);
        const phase = knownUnsent ? "failed" : "needs_review";
        state.attempts[identity.dispatchId] = { attemptId: identity.attemptId, phase, promptSha256: state.active.prepare.promptSha256 };
        if (knownUnsent) state.active = null;
        else state.active.phase = phase;
        await save();
      }
      lastMessage = message;
      if (native && notify) send(value);
      return value;
    }
    function view() {
      return { enabled: state.enabled, connected: native !== null, approved: status?.approved === true,
        clientReady: nativeReady && native !== null && state.enabled,
        configured: status?.configured === true && status?.enabled === true, actualProfile: state.active?.observedProfile || null,
        attemptId: state.active?.prepare?.attemptId || null, message: lastMessage };
    }
    function publish() { for (const viewer of viewers) { try { viewer(view()); } catch {} } }
    function subscribe(viewer) { viewers.add(viewer); return () => viewers.delete(viewer); }
    function notice(message) { lastMessage = message; publish(); }
    function askReady() {
      if (state.enabled && native && status?.enabled === true && status?.approved === true && status?.configured === true && !requestedReady) {
        requestedReady = true;
        send(R.handshake("ready", { clientReady: true }));
      }
    }
    function connect(inspectOnly = false) {
      ownSurface();
      if (native) { send(R.handshake("status")); return; }
      if (!inspectOnly && !state.enabled) return;
      if (api.runtime.id !== R.EXTENSION_ID) R.reject("wrong_extension", "扩展身份与已批准 allowlist 不一致。");
      const port = api.runtime.connectNative(R.HOST_NAME);
      native = port; nativeReady = false; requestedReady = false;
      port.onMessage.addListener(value => {
        if (native !== port) return;
        if (value?.type === "status") {
          try {
            R.validateStatus(value); status = value;
            if (![value.enabled, value.approved, value.configured, value.clientReady].every(item => item === true)) cancelOwned();
            nativeReady = value.clientReady === true && state.enabled && value.enabled && value.approved && value.configured;
            lastMessage = value.message; askReady();
          } catch { cancelOwned(); lastMessage = "原生状态回执无效，保持未就绪。"; status = null; nativeReady = false; requestedReady = false; }
          publish();
          return;
        }
        receiveNative(value).then(publish, error => notice(String(error?.message || "原生消息未处理。")));
      });
      port.onDisconnect.addListener(() => {
        if (native !== port) return;
        cancelOwned();
        native = null; nativeReady = false; requestedReady = false; status = null;
        // Consume callback-scoped runtime.lastError without exposing private paths.
        void api.runtime.lastError;
        notice("本机接收端未连接。");
        queue(async () => {
          if (state.active && state.active.phase !== "stored") await fail(state.active.prepare, "native_disconnected", "本机连接中断；发送或保存结果待核对，不能重发。");
          lastMessage = "本机接收端未连接。";
          if (state.enabled && !reconnectUsed) { reconnectUsed = true; connect(false); }
          publish();
        }).catch(() => notice("本机连接或账本状态无效，已停止自动连接。"));
      });
      send(R.handshake("hello"));
    }
    function available(value, sender) {
      R.exact(value, ["protocol", "type"]);
      const active = state.active;
      if (value.protocol !== R.PROTOCOL || value.type !== "contentAvailable" || sender?.id !== api.runtime.id
          || sender.frameId !== 0 || !Number.isInteger(sender.tab?.id) || sender.tab.id !== active?.tabId
          || !R.rootUrl(sender.url) || active.phase !== "preparing" || !readinessWait
          || !R.sameIdentity(readinessWait.identity, active.prepare))
        R.reject("wrong_page_source", "只读接收器通知不是本次专用 tab 的主页面。");
      readinessWait.wake();
      return { received: true };
    }
    async function waitReady(tabId, prepare) {
      return new Promise((resolve, reject) => {
        let done = false, probing = false, wakeRequested = false, deadline;
        const readiness = R.envelope("checkReady", prepare, { domContract: structuredClone(prepare.domContract) });
        const finish = (error, response) => {
          if (done) return; done = true;
          if (deadline !== undefined) timers.clearTimeout(deadline);
          api.tabs.onUpdated.removeListener(onUpdated);
          if (readinessWait?.identity === prepare) readinessWait = null;
          if (error) {
            try { api.tabs.sendMessage(tabId, { type: "relay.content.cancel", cancel: R.envelope("cancel", prepare) }, { frameId: 0 })?.catch?.(() => {}); }
            catch { /* A missing receiver cannot authorize a substitute send. */ }
            reject(error);
          } else resolve(response);
        };
        const probe = () => {
          if (done) return;
          if (probing) { wakeRequested = true; return; }
          wakeRequested = false;
          if (!state.enabled || !nativeReady || state.active?.phase !== "preparing" || state.active.tabId !== tabId
              || !R.sameIdentity(state.active.prepare, prepare))
            return finish(new R.RelayError("page_ready_cancelled", "本次只读就绪等待身份或批准已失效，不发送。"));
          probing = true;
          let response;
          try { response = api.tabs.sendMessage(tabId, { type: "relay.content.readiness", readiness }, { frameId: 0 }); }
          catch (error) { probing = false; return finish(error); }
          Promise.resolve(response).then(value => {
            probing = false; if (done) return;
            try {
              if (value?.type === "blocked") {
                R.validateFailure(value);
                if (!R.sameIdentity(value, prepare)) R.reject("readiness_identity_mismatch", "就绪失败回执属于另一请求。");
                throw new R.RelayError(value.code, value.message);
              }
              R.validatePageReady(value, readiness);
              finish(null, value);
            } catch (error) { finish(error); }
          }, error => {
            probing = false; if (done) return;
            // Only an absent receiver permits another readonly probe, and
            // only on a real contentAvailable/complete event, never a timer.
            if (!/Receiving end does not exist/i.test(String(error?.message || ""))) finish(error);
            else if (wakeRequested) probe();
          });
        };
        const onUpdated = (changedId, info) => { if (changedId === tabId && info.status === "complete") probe(); };
        readinessWait = { identity: prepare, tabId, wake: probe, cancel: (code, message) => finish(new R.RelayError(code, message)) };
        api.tabs.onUpdated.addListener(onUpdated);
        deadline = timers.setTimeout(() => finish(new R.RelayError("page_ready_timeout", "六十秒内未取得专用页的实际只读就绪回执，不输入或发送。")), 60000);
        // Listen first, then probe the current owned receiver. Page load/asset
        // completion is only a wake-up event, never evidence of DOM readiness.
        api.tabs.get(tabId).then(tab => {
          if (done) return;
          if (tab?.id !== tabId) return finish(new R.RelayError("wrong_page_source", "未取得本次准确专用 tab。"));
          probe();
        }, finish);
      });
    }
    async function handlePrepare(value) {
      try {
        R.validatePrepare(value);
        if (value.domContract.surface !== ownSurface()) R.reject("browser_surface_mismatch", "冻结 DOM 合同与扩展自身浏览器不符，不创建或发送。");
      }
      catch (error) {
        if (value?.protocol === R.PROTOCOL && /^[0-9a-f]{32}$/.test(value.dispatchId) && typeof value.attemptId === "string")
          return fail(value, error.code || "invalid_prepare", String(error.message || "准备契约不符。"), false);
        throw error;
      }
      if (!state.enabled || !nativeReady) return fail(value, "relay_not_ready", "扩展未获批准或接收端未就绪，不发送。", false);
      if (state.attempts[value.dispatchId]) return fail(value, "dispatch_already_attempted", "该请求已有转发记录；只能核对，不能再次创建或发送。");
      if (state.active && state.active.phase !== "stored") return fail(value, "dispatch_busy", "已有请求在途或需要核对，不能处理下一条。", false);
      if (Object.keys(state.attempts).length >= MAX_TOMBSTONES) return fail(value, "ledger_full", "扩展防重复账本已达上限，保留请求并停止。", false);
      state.active = { prepare: structuredClone(value), phase: "preparing", tabId: null, observedProfile: null, accepted: null };
      state.attempts[value.dispatchId] = { attemptId: value.attemptId, promptSha256: value.promptSha256, phase: "preparing" };
      const guard = preparationGuard = { identity: value, cancelled: false, code: null, message: null };
      const stillPreparing = (phase = "preparing") => {
        if (guard.cancelled || preparationGuard !== guard || !state.enabled || !nativeReady
            || state.active?.phase !== phase || !R.sameIdentity(state.active.prepare, value))
          R.reject(guard.code || "page_ready_cancelled", guard.message || "本次准备已停止，不能恢复输入或发送。");
      };
      try {
        await save(); stillPreparing();
        const actualSha = await R.sha256(value.prompt); stillPreparing();
        if (actualSha !== value.promptSha256) R.reject("prompt_hash_mismatch", "冻结问题与实际 SHA 不匹配，不发送。");
        const tab = await api.tabs.create({ url: "https://chatgpt.com/", active: true });
        stillPreparing();
        if (!Number.isInteger(tab?.id) || tab.id < 0) R.reject("tab_not_created", "未取得扩展自己创建的准确 tab。");
        state.active.tabId = tab.id; await save();
        stillPreparing();
        await waitReady(tab.id, value);
        stillPreparing();
        if (state.active.tabId !== tab.id) R.reject("page_ready_cancelled", "只读就绪后专用页面身份已失效，不发送准备请求。");
        const response = await api.tabs.sendMessage(tab.id, { type: "relay.content.prepare", prepare: value }, { frameId: 0 });
        stillPreparing();
        if (response?.type === "blocked") {
          R.validateFailure(response);
          if (!R.sameIdentity(response, value)) R.reject("prepare_identity_mismatch", "准备失败回执不属于本次专用页面。");
          return fail(value, response.code, response.message, false);
        }
        R.validatePrepared(response);
        if (!R.sameIdentity(response, value) || response.observation.observationSha256 !== value.domContract.observationSha256
            || response.observation.surface !== value.domContract.surface)
          R.reject("prepare_identity_mismatch", "页面准备回执身份、浏览器或 DOM 观察证据不符。");
        state.active.phase = "prepared"; state.active.observedProfile = response.observation.observedProfile;
        state.attempts[value.dispatchId].phase = "prepared"; await save(); stillPreparing("prepared"); send(response);
      } catch (error) { return fail(value, error.code || "prepare_failed", String(error?.message || "页面未准备完成。"), false); }
      finally { if (preparationGuard === guard) preparationGuard = null; }
    }
    async function handleCommit(value) {
      R.validateCommit(value);
      const active = state.active;
      if (!active || !R.sameIdentity(value, active.prepare) || active.phase !== "prepared")
        return fail(value, "commit_not_prepared", "该 commit 未对应唯一已准备页面；不能再次点击 Send。");
      if (!state.enabled || !nativeReady) return fail(value, "relay_not_ready", "提交前连接或权限变化，保留核对。", true);
      // Durable intent precedes the sole content-script click. Restart never resets it.
      active.phase = "send_intent"; state.attempts[value.dispatchId].phase = "send_intent"; await save();
      try {
        const response = await api.tabs.sendMessage(active.tabId, { type: "relay.content.commit", commit: value });
        if (response?.type === "uncertain") {
          R.exact(response, ["protocol", "type", "dispatchId", "attemptId", "code", "message", "clickStarted"]);
          if (typeof response.clickStarted !== "boolean") R.reject("invalid_commit_receipt", "缺少本次实际点击阶段回执。");
          const { clickStarted, ...failure } = response;
          R.validateFailure(failure);
          if (!R.sameIdentity(failure, value)) R.reject("commit_identity_mismatch", "提交失败回执不属于本次专用页面。");
          return fail(value, failure.code, failure.message + (clickStarted ? " 本次已开始点击 Send，送达需核对。" : " 本次尚未点击 Send；原意图保留，不自动重发。"));
        }
        if (response?.committed !== true) R.reject("send_unknown", "页面没有返回准确的一次提交回执。");
        active.phase = "waiting"; state.attempts[value.dispatchId].phase = "waiting"; await save();
      } catch (error) { return fail(value, error.code || "send_unknown", String(error?.message || "Send 结果不明，不能重发。")); }
    }
    async function handleStored(value) {
      const active = state.active;
      if (active?.phase === "stored" && R.sameIdentity(value, active.prepare)) { R.validateStored(value, active.prepare); return { duplicate: true }; }
      if (!active || active.phase !== "capture_forwarded") R.reject("store_not_matching", "尚无对应的已回传实际回答。");
      R.validateStored(value, active.prepare);
      active.phase = "stored"; state.attempts[value.dispatchId].phase = "stored";
      await save(); lastMessage = "本机已确认保存该请求的实际 DOM 回答；底层推理能力仍未核验。";
      // Keep only bounded attribution/tombstone data after acknowledged storage.
      state.active = { prepare: { protocol: R.PROTOCOL, dispatchId: value.dispatchId, attemptId: value.attemptId }, phase: "stored", observedProfile: "Instant" };
      await save();
    }
    async function handleRetired(value) {
      R.validateRetired(value);
      const prior = state.attempts[value.dispatchId];
      if (!prior || prior.attemptId !== value.attemptId) R.reject("retirement_identity_mismatch", "结束回执没有匹配的原防重复记录。");
      if (state.active && !R.sameIdentity(value, state.active.prepare)) R.reject("retirement_identity_mismatch", "结束回执不能释放另一条当前请求。");
      if (prior.phase === "stored") R.reject("retirement_completed", "已保存的回答不能改为失败结束。");
      if (prior.phase === "retired" && !state.active) return { duplicate: true };
      // Retain the original intent/unknown outcome and every tombstone. A
      // terminal local receipt releases ownership, never authorizes another send.
      prior.retirement = value.reason;
      prior.previousPhase = prior.previousPhase || prior.phase;
      prior.phase = "retired";
      cancelOwned();
      state.active = null;
      await save();
      lastMessage = "本机已结束原请求；记录与发送意图保留，不自动重发。";
      return { retired: true };
    }
    async function handleNative(value) {
      if (value?.type === "prepare") return handlePrepare(value);
      if (value?.type === "commitSend") return handleCommit(value);
      if (value?.type === "stored") return handleStored(value);
      if (value?.type === "retired") return handleRetired(value);
      if (["blocked", "uncertain"].includes(value?.type)) {
        R.validateFailure(value);
        if (state.active && R.sameIdentity(value, state.active.prepare)) return fail(value, value.code, value.message, true, false);
      }
      R.reject("unsupported_native_message", "未知原生消息不能构成发送授权。");
    }
    async function handlePage(value, sender) {
      const active = state.active;
      if (!active || sender?.id !== api.runtime.id || sender?.tab?.id !== active.tabId || sender.frameId !== 0
          || !R.sameIdentity(value, active.prepare)) R.reject("wrong_page_source", "页面消息不是这次授权的专用 tab。");
      if (!["send_intent", "waiting", "capture_forwarded"].includes(active.phase)) R.reject("page_not_committed", "页面尚未处于本次已提交阶段。");
      if (value.type === "accepted") {
        R.validateAccepted(value, active.prepare);
        if (sender.url !== value.evidence.conversationUrl) R.reject("wrong_page_source", "实际发送页地址与证据不符。");
        if (active.accepted && JSON.stringify(active.accepted) !== JSON.stringify(value.evidence))
          R.reject("accepted_source_changed", "已经保存的实际用户来源不能改写。");
        active.accepted = structuredClone(value.evidence); await save(); send(value); return { received: true };
      }
      if (value.type === "capture") {
        R.validateCapture(value, active.prepare);
        if (sender.url !== value.evidence.conversationUrl) R.reject("wrong_page_source", "实际回答页地址与证据不符。");
        if (active.accepted && ["conversationUrl", "sourceUserMessageId", "sourceUnitKey", "promptText"].some(key => active.accepted[key] !== value.evidence[key]))
          R.reject("capture_source_changed", "回答来源与实际送达输入不一致。");
        if (active.phase === "capture_forwarded") return { received: true, duplicate: true };
        active.phase = "capture_forwarded"; state.attempts[value.dispatchId].phase = "capture_forwarded";
        await save(); send(value); lastMessage = "实际回答已回传，等待本机保存回执。"; return { received: true };
      }
      if (["blocked", "uncertain"].includes(value.type)) { R.validateFailure(value); await fail(value, value.code, value.message); return { received: true }; }
      R.reject("unsupported_page_message", "页面消息不能改变发送授权。");
    }
    async function popup(action) {
      if (action === "status") { connect(true); publish(); return view(); }
      if (action === "enable") {
        if (!status?.approved || !status?.configured || !status?.enabled) R.reject("approval_required", "尚未取得本机明确批准与真实 Chrome DOM 合同。");
        state.enabled = true; reconnectUsed = false; await save(); askReady(); publish(); return view();
      }
      if (action === "disable") {
        if (state.active && state.active.phase !== "stored") await fail(state.active.prepare, "relay_disabled", "用户停用转发；保留在途核对，不能重发。");
        state.enabled = false; await save(); nativeReady = false;
        const old = native; native = null; status = null; if (old) old.disconnect();
        lastMessage = "已停用；旧请求与防重复账本保留。"; publish(); return view();
      }
      R.reject("invalid_popup_action", "未知扩展控制动作。");
    }
    async function start() { await load; if (state.enabled) connect(false); publish(); }
    return { start, view, native: receiveNative, page: (value, sender) => queue(() => handlePage(value, sender)),
      popup: action => { if (action === "disable") cancelOwned(); return queue(() => popup(action)); },
      abandon: (identity, code, message) => queue(() => fail(identity, code, message)),
      subscribe, notice, cancelOwned, available, idle: () => serial, state: () => structuredClone(state) };
  }
  function ownControlUrl(api) { return `chrome-extension://${api.runtime.id}/popup.html`; }
  function ownControlPage(api, sender) {
    if (api.runtime.id !== R.EXTENSION_ID || sender?.id !== R.EXTENSION_ID || sender.url !== ownControlUrl(api)
        || (sender.frameId !== undefined && sender.frameId !== 0)
        || (sender.origin !== undefined && sender.origin !== `chrome-extension://${R.EXTENSION_ID}`)) return false;
    if (sender.tab === undefined) return true;
    return Number.isInteger(sender.tab?.id) && sender.tab.id >= 0 && sender.frameId === 0
      && (sender.tab.url === undefined || sender.tab.url === ownControlUrl(api));
  }
  function registerRuntime(api, resolveBrowserSurface) {
    const controller = createController(api, resolveBrowserSurface);
    api.runtime.onMessage.addListener((value, sender, reply) => {
      if (value?.type === "contentAvailable") {
        try { reply(controller.available(value, sender)); }
        catch (error) { reply({ received: false, code: error?.code || "page_rejected" }); }
        return false;
      }
      if (value?.type === "relay.popup") {
        if (!ownControlPage(api, sender)) return false;
        if (value.action === "disable") controller.cancelOwned();
        controller.popup(value.action).then(reply, error => reply({ ...controller.view(), message: String(error?.message || "扩展操作未完成。") }));
        return true;
      }
      if (value?.protocol !== R.PROTOCOL) return false;
      controller.page(value, sender).then(reply, error => reply({ received: false, code: error?.code || "page_rejected" }));
      return true;
    });
    api.runtime.onConnect?.addListener(port => {
      if (port.name !== "relay.status" || !ownControlPage(api, port.sender)) { port.disconnect(); return; }
      const update = value => {
        try { port.postMessage({ type: "relay.status", value }); }
        catch { unsubscribe(); }
      };
      const unsubscribe = controller.subscribe(update);
      port.onDisconnect.addListener(unsubscribe);
      update(controller.view());
    });
    api.runtime.onInstalled?.addListener(details => {
      if (!["install", "update"].includes(details?.reason) || api.runtime.id !== R.EXTENSION_ID) return;
      const failed = () => controller.notice("接通页未能自动打开；请从此扩展的详细信息打开「扩展选项」。");
      try {
        const opening = api.tabs.create({ url: ownControlUrl(api), active: true }, () => {
          if (api.runtime.lastError) failed();
        });
        if (opening && typeof opening.catch === "function") opening.catch(failed);
      } catch { failed(); }
    });
    api.tabs.onRemoved.addListener(tabId => {
      const active = controller.state().active;
      if (active?.tabId !== tabId || active.phase === "stored") return;
      controller.cancelOwned("owned_tab_closed", "本次专用聊天页已关闭，不能继续输入或发送。");
      if (active.phase !== "preparing") controller.abandon(active.prepare,
        "owned_tab_closed", "专用聊天页已关闭，发送或结果需核对，不能重发。").catch(() => {});
    });
    controller.start().catch(() => {});
    return controller;
  }
  root.ConsoleChatRelayWorker = Object.freeze({ createController, detectBrowserSurface, ownControlPage, registerRuntime, STORAGE_KEY });
  if (root.chrome?.runtime?.onMessage && root.chrome?.storage?.local && root.chrome?.tabs) registerRuntime(root.chrome);
})(globalThis);
