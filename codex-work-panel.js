(() => {
  "use strict";
  const make = (tag, text = "", cls = "") => { const node = document.createElement(tag); node.textContent = text; node.className = cls; return node; };
  const uuid = () => crypto.randomUUID();
  const button = (text, action) => { const node = make("button", text, "workflow-button"); node.type = "button"; node.addEventListener("click", action); return node; };
  const field = (text, control) => { const node = make("label", "", "workflow-field"); node.append(make("span", text), control); return node; };
  const select = () => make("select");
  function changedFileText(file) {
    if (!file || typeof file.path !== "string" || !file.path || /[\\:\u0000-\u001f\u007f]/.test(file.path) || file.path.split("/").some(part => !part || part === "." || part === "..")) return "";
    const digest = value => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
    const valid = file.change === "added" ? file.beforeSha256 === null && digest(file.afterSha256) : file.change === "removed" ? digest(file.beforeSha256) && file.afterSha256 === null : file.change === "modified" && digest(file.beforeSha256) && digest(file.afterSha256) && file.beforeSha256 !== file.afterSha256;
    return valid ? `${({ added: "新增", modified: "修改", removed: "删除" })[file.change]}：${file.path}` : "";
  }
  function optionsFor(control, items, selected = control.value, preserveMissing = false) { control.replaceChildren(); for (const item of items) { const option = make("option", item.name || item.id); option.value = item.id; option.disabled = item.disabled === true; control.append(option); } const available = items.some(item => item.id === selected && !item.disabled); if (preserveMissing && selected && !available) { const option = make("option", `原模型暂不可选：${selected}`); option.value = selected; option.disabled = true; control.append(option); } control.value = available || preserveMissing && selected ? selected : items.find(item => !item.disabled)?.id || ""; }
  function create(root, options = {}) {
    if (!root) return null;
    const phone = options.phone === true, base = options.endpoint || (phone ? "/api/phone/workflow" : "/api/workflow"), key = `console.codexWork.v1:${base}`;
    let saved = {}; try { saved = JSON.parse(localStorage.getItem(key) || "{}"); } catch { /* Keep the saved draft untouched. */ }
    const state = { active: false, busy: false, generation: 0, source: null, recordId: typeof saved.recordId === "string" ? saved.recordId : "", config: null, review: null, pending: saved.pending || null, setupUnknown: saved.setupUnknown === true, runs: [], timer: 0, setupTimer: 0, composing: false, storageFailed: false };
    const notice = make("p", "", "workflow-notice"), heading = make("h2", "Work Agents"), back = button("返回对话", () => options.onBack?.()), load = button("载入当前讨论", () => void loadSource()), refresh = button("查看进度", () => void refreshAll());
    notice.setAttribute("role", "status"); notice.setAttribute("aria-live", "polite");
    const header = make("div", "", "workflow-header"); header.append(heading, back, load, refresh);
    const sourceText = make("textarea"); sourceText.readOnly = true; sourceText.rows = 4; sourceText.setAttribute("aria-label", "本轮 Work 底稿");
    const workspace = select(), model = select(), profile = select(); profile.setAttribute("aria-label", "Work 档位");
    optionsFor(profile, [{ id: "fast", name: "极速 · low" }, { id: "high", name: "高 · high" }, { id: "pro", name: "Pro · 待核实", disabled: true }], saved.profile || "high");
    if (saved.profile === "pro") profile.value = "pro";
    const scope = make("p", "", "workflow-muted"), sourceImages = make("div", "", "workflow-thumbnails"), prepare = button("核对本轮 Work", () => void prepareWork());
    const setupText = make("p", "", "workflow-muted"), setupButton = button("配置 Console Work 沙箱（Windows 授权）", () => void setupWork());
    const setupBox = make("section", "", "codex-work-setup"); setupBox.append(setupText); if (!phone) setupBox.append(setupButton);
    const form = make("section", "", "codex-work-source"); form.append(field("本轮文字（在对话输入框编辑）", sourceText), sourceImages, field("电脑工作区", workspace), scope, field("已授权模型", model), field("档位", profile), prepare);
    const review = make("section", "", "workflow-review"), reviewText = make("pre", "", "codex-work-review-text"), confirm = button("确认创建 Agent", () => void submitWork()), dismiss = button("返回核对", () => { if (!state.pending && !state.busy) { state.review = null; render(); } });
    review.append(make("h3", "确认这一轮 Work"), reviewText, confirm, dismiss); review.hidden = true;
    const runs = make("section", "", "codex-work-runs"), permissions = make("details", "", "workflow-collapse"); permissions.append(make("summary", "工作区设置"));
    const workspaceId = make("input"), workspaceName = make("input"), workspaceRoot = make("input"), allowedRoot = make("input");
    workspaceId.value = "console"; workspaceName.value = "Codex Console";
    if (!phone) permissions.append(field("工作区 ID", workspaceId), field("名称", workspaceName), field("项目完整目录", workspaceRoot), field("允许修改的完整目录", allowedRoot), button("保存工作区授权", () => void configureWorkspace()));
    else permissions.append(make("p", "工作区访问范围由电脑端明确保存。"));
    root.classList.add("workflow-panel", "codex-work-panel"); root.replaceChildren(header, notice, setupBox, form, review, runs, permissions);
    function say(text, error = false) { notice.textContent = text; notice.dataset.error = String(error); }
    function currentPhoneScope() {
      const value = options.getScope?.();
      if (!value || value.recordId !== state.recordId || !/^[a-f0-9]{32}$/.test(value.recordId) || !/^[a-f0-9]{32}$/.test(value.sessionId || "") || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(value.clientId || "")) return null;
      const scope = { recordId: value.recordId, clientId: value.clientId, sessionId: value.sessionId };
      return !state.source || sameScope(scope, state.source) ? scope : null;
    }
    function sameScope(left, right) { return Boolean(left && right && left.recordId === right.recordId && left.clientId === right.clientId && left.sessionId === right.sessionId); }
    function jobPhoneScope(job) { const value = job.mobileDialogue; return value ? { recordId: value.recordId, clientId: value.clientId, sessionId: value.id } : null; }
    function matchesPhoneJob(job, scope) { return job.mobileDialogue === null || sameScope(scope, jobPhoneScope(job)); }
    function retirePhoneView() { state.generation++; state.runs = []; state.source = state.review = null; sourceText.value = ""; sourceImages.replaceChildren(); say("当前讨论身份已变化，请重新载入当前讨论；原请求与对话草稿保留。", true); render(); }
    function persist() { try { localStorage.setItem(key, JSON.stringify({ recordId: state.recordId, profile: profile.value, workspaceId: workspace.value, model: model.value, pending: state.pending, setupUnknown: state.setupUnknown })); state.storageFailed = false; return true; } catch { state.storageFailed = true; say("本机请求编号尚未保存；保持当前页，未创建 Agent。", true); return false; } }
    async function call(action, body, query = "") {
      const response = await fetch(`${base}/${action}${query ? "?" + query : ""}`, { method: body ? "POST" : "GET", credentials: "same-origin", mode: "same-origin", redirect: "error", cache: "no-store", headers: { ...(phone ? { "X-Codex-Phone": "1" } : {}), ...(body ? { "Content-Type": "application/json" } : {}) }, body: body ? JSON.stringify(body) : undefined });
      const data = await response.json(); if (!response.ok || data.error) { if ([401, 403].includes(response.status)) options.onAuth?.(); const error = new Error(data.error || "Work 状态暂不可用，原记录保留。"); error.code = data.code; throw error; } return data;
    }
    function render() {
      const validSource = state.source?.recordId === state.recordId && state.source.text === sourceText.value;
      const modelAvailable = state.config?.subscription?.models?.some(item => item.slug === model.value), ready = state.config?.setup?.ready === true && state.config?.setup?.busy !== true;
      prepare.disabled = state.busy || state.pending || !validSource || !workspace.value || !modelAvailable || !["fast", "high"].includes(profile.value) || !state.config?.subscription?.connected || !ready || state.composing;
      workspace.disabled = model.disabled = profile.disabled = state.busy || Boolean(state.pending);
      load.disabled = state.busy || Boolean(state.pending); confirm.disabled = state.busy || !state.review || Boolean(state.pending) || !ready || !modelAvailable || !state.config?.subscription?.connected; dismiss.disabled = state.busy || Boolean(state.pending);
      review.hidden = !state.review && !state.pending;
      if (state.pending) { reviewText.textContent = "创建请求已提交或送达待核对。原请求编号已保留，不能再点一次自动重跑。请查看进度。"; confirm.disabled = true; }
      const binding = state.config?.workspaces?.find(item => item.id === workspace.value);
      scope.textContent = binding ? `修改范围：${binding.allowedRoot}。本轮可修改工作区文件；运行项目程序尚未接通。` : "请先在电脑设置工作区。";
      const setup = state.config?.setup;
      setupText.textContent = setup?.ready === true ? "Console Work 沙箱已配置；每轮仍会核对实际工作区权限。" : setup?.busy === true ? "正在等待 Windows 沙箱配置结果；权限窗口需你本人确认。" : setup?.status === "unknown" || state.setupUnknown ? "上次沙箱配置送达或结果待核对，请查看进度；不能重复配置。" : setup?.status === "failed" ? "上次沙箱配置未完成，结果已保留；请先核对电脑权限窗口与配置错误。" : "首次 Work 需要在电脑配置 Console 专用沙箱，并由你确认 Windows 权限。";
      setupButton.disabled = state.busy || !binding || setup?.ready === true || setup?.busy === true || setup?.attempted === true || setup?.status === "unknown" || state.setupUnknown;
      runs.replaceChildren();
      for (const [index, job] of state.runs.entries()) {
        const work = job.codexWork || {}, card = make("article", "", "codex-work-agent"), title = make("h3", work.name || `Agent ${index + 1}`), phase = job.status === "interrupted" ? work.cancellationVerified === true && work.terminalEventObserved === true ? "已取消" : "中断结果待核对" : ({ starting: "准备中", running: "执行中", cancelling: "等待电脑取消回执", completed: "已完成", failed: "未完成", needs_review: "结果待核对" })[job.status] || job.status, description = make("p", `${phase} · ${work.actualModel || work.requestedModel || "模型待核对"}`);
        card.append(title, description, make("p", work.allowedRoot || job.workspace?.allowedRoot || "", "workflow-muted"));
        if (work.actualEffort) card.append(make("p", `实际档位：${work.actualEffort} · ${work.terminalEventObserved ? "已收到终态回执" : "尚在进行"}`, "workflow-muted"));
        if (job.error) card.append(make("p", job.error, "workflow-notice"));
        const progress = make("pre", Array.isArray(work.progress) ? work.progress.filter(item => item && typeof item.text === "string").map(item => item.text).join("\n") : "", "codex-work-progress"); card.append(progress);
        const result = job.result || {}; if (result.text) { card.append(make("h4", "Output"), make("pre", result.text, "codex-work-progress")); if (result.reportOnly || work.reportOnly) card.append(make("p", "本轮只有报告，尚未核实文件修改。", "workflow-muted")); }
        if (job.status === "completed" && work.terminalEventObserved === true && work.executionVerified === true && result.executionVerified === true && Array.isArray(result.changedFiles) && result.changedFiles.length) {
          const files = result.changedFiles.map(changedFileText).filter(Boolean);
          if (files.length) { const list = make("ul"); for (const text of files) list.append(make("li", text)); card.append(make("h4", "已核实文件（相对修改范围）"), list); }
          if (files.length !== result.changedFiles.length) card.append(make("p", "部分文件变更信息尚待核对。", "workflow-muted"));
        }
        if (["starting", "running", "cancelling", "needs_review"].includes(job.status) && work.threadId && work.turnId && !work.terminalEventObserved) {
          const cancel = button(work.cancellationVerified ? "已取消" : job.status === "cancelling" ? "等待取消回执" : "取消这个 Agent", () => void cancelWork(job)); cancel.disabled = state.busy || job.status === "cancelling"; card.append(cancel);
        }
        runs.append(card);
      }
      if (!state.runs.length) runs.append(make("p", "这条记录还没有 Work Agent。", "workflow-muted"));
    }
    async function readConfig() {
      const generation = state.generation, data = await call("codex-work/config"); if (generation !== state.generation) return null; state.config = data;
      if (state.setupUnknown && (data.setup?.busy === true || data.setup?.ready === true || data.setup?.attempted === true)) { state.setupUnknown = false; persist(); }
      optionsFor(workspace, (data.workspaces || []).map(item => ({ ...item, disabled: item.available === false })), workspace.value || saved.workspaceId);
      optionsFor(model, (data.subscription?.models || []).map(item => ({ id: item.slug, name: item.displayName || item.name || item.slug })), model.value || saved.model, true);
      if (state.review && (state.review.source?.subscription?.connectionId !== data.subscription?.connectionId || state.review.source?.subscription?.catalogRevision !== data.subscription?.catalogRevision || !data.subscription?.models?.some(item => item.slug === model.value))) state.review = null;
      render(); if (!data.subscription?.connected) say(({ catalog_loading: "正在恢复已授权的模型列表，请稍候再查看。", catalog_required: "模型列表尚未恢复，请在电脑查看订阅连接。", catalog_failed: "模型列表读取失败，请在电脑重新读取模型。" })[data.subscription?.status] || "请先在电脑连接 ChatGPT 订阅。", true); else if (model.value && !data.subscription.models?.some(item => item.slug === model.value)) say("原模型暂不可选，请明确选择当前已授权模型；不会自动改用其它模型。", true);
      window.clearTimeout(state.setupTimer); if (state.active && data.setup?.busy === true) state.setupTimer = window.setTimeout(() => { if (state.active) void readConfig().catch(error => say(error.message, true)); }, 2000);
      return data;
    }
    async function setupWork() {
      if (phone || setupButton.disabled) return;
      const binding = state.config?.workspaces?.find(item => item.id === workspace.value); if (!binding) return;
      state.setupUnknown = true; if (!persist()) { render(); return; }
      state.busy = true; render();
      try { const data = await call("codex-work/setup", { workspaceId: binding.id, workspaceAuthorizationSha256: binding.authorizationSha256, confirmed: true }); await readConfig(); say(data.accepted === false ? data.message || "原沙箱配置记录已保留，请查看实际状态。" : "沙箱配置请求已提交。请在 Windows 权限窗口中亲自确认，再查看此页状态。"); }
      catch (error) { say(error.message + " 配置送达待核对，请查看进度；不会自动重新配置。", true); } finally { state.busy = false; render(); }
    }
    async function refreshAll() { try { await readConfig(); await readRuns(); } catch (error) { say(error.message, true); } }
    async function loadSource() {
      if (state.busy || state.pending) return false;
      const source = options.getSource?.();
      if (!source?.recordId || typeof source.text !== "string" || !Array.isArray(source.attachmentIds)) { say("当前讨论还在保存或图片尚未上传。请返回对话点「只保存」，再载入本轮。", true); return false; }
      state.generation++; state.source = { ...source, attachmentIds: [...source.attachmentIds] }; state.recordId = source.recordId; sourceText.value = source.text; state.review = null; persist(); sourceImages.replaceChildren();
      sourceImages.append(make("p", source.attachmentIds.length ? `本轮选择 ${source.attachmentIds.length} 张图片；核对页展示冻结内容。` : "本轮没有选图。", "workflow-muted"));
      say("已载入当前底稿，尚未创建 Agent。"); render(); await readRuns(); return true;
    }
    async function prepareWork() {
      if (prepare.disabled) return; state.busy = true; render(); const generation = state.generation;
      try {
        const fresh = options.getSource?.(); if (!fresh || JSON.stringify(fresh) !== JSON.stringify(state.source)) throw new Error("当前底稿已变化，请重新载入后核对。");
        const binding = state.config.workspaces.find(item => item.id === workspace.value), account = state.config.subscription;
        const payload = { requestId: uuid(), ...state.source, workspaceId: binding.id, workspaceAuthorizationSha256: binding.authorizationSha256, requestedProfile: profile.value,
          subscription: { provider: "chatgpt_subscription", connectionId: account.connectionId, catalogRevision: account.catalogRevision, modelSlug: model.value } };
        const data = await call("codex-work/review", payload); if (generation !== state.generation) return;
        if (JSON.stringify(options.getSource?.()) !== JSON.stringify(state.source)) throw new Error("等待核对时底稿已变化，请重新载入；未创建 Agent。");
        const value = data.review || data;
        const frozen = value.source, selectedBinding = payload.subscription, frozenDialogue = frozen?.mobileDialogue;
        if (value.recordId !== state.recordId || typeof value.reviewId !== "string" || !/^[a-f0-9]{64}$/.test(value.sourceSha256 || "") || frozen?.text !== state.source.text || frozen?.workspace?.id !== binding.id || frozen?.workspace?.authorizationSha256 !== binding.authorizationSha256 || frozen?.requestedProfile !== profile.value || JSON.stringify(frozen?.attachmentIds) !== JSON.stringify(state.source.attachmentIds) || frozen?.expectedRevision !== state.source.expectedRevision || !Object.keys(selectedBinding).every(key => frozen?.subscription?.[key] === selectedBinding[key]) || phone && (frozenDialogue?.clientId !== state.source.clientId || frozenDialogue.id !== state.source.sessionId || frozenDialogue.recordId !== state.source.recordId || frozenDialogue.revision !== state.source.expectedRevision) || !phone && frozenDialogue != null) throw new Error("核对页的来源不一致，未创建 Agent。");
        state.review = value; reviewText.textContent = `${value.source.text}\n\n工作区：${value.source.workspace.name}\n修改范围：${value.source.workspace.allowedRoot}\n模型：${value.source.subscription.modelSlug}\n档位：${({ fast: "极速 · low", high: "高 · high", pro: "Pro" })[value.source.requestedProfile]}\n选图：${(value.source.images || []).map(item => item.name || item.id).join("、") || "无"}\n来源版本：${state.source.expectedRevision}`;
        say("请核对原文字、选图、范围和模型；确认后才实际修改电脑文件。");
      } catch (error) { if (generation === state.generation) say(error.message, true); } finally { state.busy = false; render(); }
    }
    async function submitWork() {
      if (confirm.disabled || !state.review) return;
      if (JSON.stringify(options.getSource?.()) !== JSON.stringify(state.source)) { state.review = null; say("当前底稿已变化，请重新载入并核对；未创建 Agent。", true); render(); return; }
      const payload = { requestId: uuid(), reviewId: state.review.reviewId || state.review.id, sourceSha256: state.review.sourceSha256, confirmed: true };
      const generation = state.generation, recordId = state.recordId;
      state.pending = payload; if (!persist()) { state.pending = null; render(); return; }
      state.busy = true; render();
      try { const data = await call("codex-work/submit", payload); if (generation !== state.generation || recordId !== state.recordId) return; const job = data.job; if (!job || job.recordId !== state.recordId || job.codexWork?.sourceSha256 !== payload.sourceSha256) throw new Error("送达来源需要核对；请求编号保留，不会重发。"); state.pending = null; state.review = null; persist(); say("Agent 已创建；正在等待电脑实际进度。"); }
      catch (error) { if (generation === state.generation && recordId === state.recordId) say(error.message + " 原请求编号保留，不会自动重跑。", true); }
      finally { state.busy = false; render(); await readRuns(); }
    }
    async function cancelWork(job) {
      if (state.busy) return; const work = job.codexWork || {};
      const scope = phone ? currentPhoneScope() : null;
      if (phone && (!scope || job.recordId !== scope.recordId || !matchesPhoneJob(job, scope))) { retirePhoneView(); return; }
      const generation = state.generation, recordId = state.recordId;
      state.busy = true; render();
      try { const data = await call("codex-work/cancel", { requestId: uuid(), jobId: job.id, threadId: work.threadId, turnId: work.turnId, sourceSha256: work.sourceSha256, ...(phone ? { clientId: scope.clientId, sessionId: scope.sessionId } : {}) }), actual = data.job?.codexWork;
        if (data.job?.id !== job.id || data.job.recordId !== job.recordId || actual?.sourceSha256 !== work.sourceSha256 || actual.threadId !== work.threadId || actual.turnId !== work.turnId) throw new Error("取消回执目标不一致，请查看这个 Agent 的实际状态。");
        if (phone && !matchesPhoneJob(data.job, scope)) throw new Error("取消回执讨论身份不一致，请查看这个 Agent 的实际状态。");
        if (phone && !sameScope(scope, data.scope)) throw new Error("取消回执讨论身份不一致，请查看这个 Agent 的实际状态。");
        if (generation !== state.generation || recordId !== state.recordId) return;
        if (phone && !sameScope(scope, currentPhoneScope())) { retirePhoneView(); return; }
        say(actual.cancellationVerified === true && actual.terminalEventObserved === true ? "这个 Agent 已收到电脑取消回执。" : "取消请求已接收，等待这个 Agent 的电脑终态回执。"); }
      catch (error) { if (generation === state.generation && recordId === state.recordId) say(error.message, true); } finally { state.busy = false; await readRuns(); }
    }
    async function readRuns() {
      window.clearTimeout(state.timer); if (!state.recordId || !state.active) { render(); return; }
      const scope = phone ? currentPhoneScope() : null;
      if (phone && !scope) { retirePhoneView(); return; }
      const generation = state.generation, recordId = state.recordId;
      try {
        const data = await call("codex-work/runs", null, `recordId=${encodeURIComponent(recordId)}${phone ? `&clientId=${encodeURIComponent(scope.clientId)}&sessionId=${encodeURIComponent(scope.sessionId)}` : ""}`);
        if (!state.active || generation !== state.generation || recordId !== state.recordId) return;
        if (phone && !sameScope(scope, currentPhoneScope())) { retirePhoneView(); return; }
        if (phone && !sameScope(scope, data.scope)) { state.runs = []; render(); throw new Error("进度回执讨论身份不一致，请重新载入当前讨论。"); }
        state.runs = (data.jobs || data.runs || []).filter(job => job.recordId === recordId && job.executionEngine === "codex_agent" && (!phone || matchesPhoneJob(job, scope)));
        if (state.pending && state.runs.some(job => job.requestId === state.pending.requestId && job.codexWork?.sourceSha256 === state.pending.sourceSha256)) { state.pending = null; state.review = null; persist(); say("原创建请求已核对，Agent 记录已保留。"); }
        render();
        // Read progress only for visible, already accepted activity. No model,
        // historical queue adoption or background dispatch occurs in this GET.
        if (state.runs.some(job => ["starting", "running", "cancelling"].includes(job.status))) state.timer = window.setTimeout(() => void readRuns(), 2000);
      } catch (error) { if (generation === state.generation) say(error.message, true); }
    }
    async function configureWorkspace() {
      if (state.busy || phone || state.composing) return; state.busy = true; render();
      try { const current = state.config?.workspaces || [], value = { id: workspaceId.value.trim(), name: workspaceName.value.trim(), workspaceRoot: workspaceRoot.value.trim(), allowedRoot: allowedRoot.value.trim() };
        await call("codex-work/workspaces", { requestId: uuid(), workspaces: [...current.filter(item => item.id !== value.id).map(({ id, name, workspaceRoot, allowedRoot }) => ({ id, name, workspaceRoot, allowedRoot })), value] }); await readConfig(); say("工作区授权已保存；尚未执行任务。"); }
      catch (error) { say(error.message, true); } finally { state.busy = false; render(); }
    }
    for (const control of [workspace, model, profile]) control.addEventListener("change", () => { state.review = null; persist(); render(); });
    for (const control of [workspaceId, workspaceName, workspaceRoot, allowedRoot]) { control.addEventListener("compositionstart", () => { state.composing = true; render(); }); control.addEventListener("compositionend", () => { state.composing = false; render(); }); }
    render();
    return { async setActive(value) { const changed = state.active !== Boolean(value); state.active = Boolean(value); if (!changed && state.active) return; window.clearTimeout(state.timer); window.clearTimeout(state.setupTimer); if (state.active && changed) { try { await readConfig(); if (!state.recordId) await loadSource(); else await readRuns(); } catch (error) { say(error.message, true); } } }, loadSource, refresh: refreshAll,
      canReload() { return !state.busy && !state.composing && !state.storageFailed && !state.pending && state.config?.setup?.busy !== true; }, async prepareReload() { return this.canReload() && persist(); }, hasDraft() { return Boolean(state.review || state.pending); }, clear() { state.generation++; state.active = false; window.clearTimeout(state.timer); window.clearTimeout(state.setupTimer); state.source = state.review = null; state.runs = []; sourceText.value = ""; render(); } };
  }
  window.CodexWorkPanel = Object.freeze({ create });
})();
