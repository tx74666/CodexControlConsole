(() => {
  "use strict";
  const stages = [{ id: "vague", name: "模糊" }, { id: "thinking", name: "考虑中" }, { id: "ready", name: "待发布" }, { id: "queued", name: "排队" }, { id: "published", name: "已发布" }];
  const priorities = [{ id: "high", name: "高" }, { id: "normal", name: "普通" }, { id: "low", name: "低" }];
  const targets = [{ id: "none", name: "尚未指定" }, { id: "codex", name: "Codex" }, { id: "chatgpt", name: "ChatGPT" }];
  const make = (tag, text = "", className = "") => { const element = document.createElement(tag); element.textContent = text; element.className = className; return element; };
  const uuid = () => globalThis.crypto?.randomUUID?.() || "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, character => { const value = Math.floor(Math.random() * 16); return (character === "x" ? value : (value & 3) | 8).toString(16); });
  const field = (text, control) => { const label = make("label", "", "incubator-field"); label.append(make("span", text), control); return label; };
  const input = () => make("input");
  const button = (text, action, className = "") => { const element = make("button", text, `incubator-button ${className}`.trim()); element.type = "button"; element.addEventListener("click", action); return element; };
  const select = choices => { const element = make("select"); fillOptions(element, choices); return element; };
  function fillOptions(element, choices, selected = element.value) { element.replaceChildren(); for (const choice of choices) { const option = make("option", choice.name); option.value = choice.id; element.append(option); } element.value = choices.some(choice => choice.id === selected) ? selected : choices[0]?.id || ""; }
  const fields = ["title", "body", "stage", "priority", "parentId", "targetKind", "targetThreadId", "targetName"];
  const content = idea => Object.fromEntries(fields.map(key => [key, key === "parentId" ? idea?.parentId || null : idea?.[key] ?? ({ stage: "vague", priority: "normal", targetKind: "none" }[key] ?? "")]));
  const fingerprint = idea => JSON.stringify(content(idea));
  const localId = id => String(id).startsWith("local-");
  function create(root, options = {}) {
    if (!root) return null;
    const phone = Boolean(options.phone), offline = Boolean(options.offline), adapter = typeof options.endpoint === "function" ? options.endpoint : null, base = typeof options.endpoint === "string" ? options.endpoint : phone ? "/api/phone/workflow" : "/api/workflow", key = options.storageKey || `codexIncubator.v1:${base}`;
    let saved;
    try { saved = JSON.parse(localStorage.getItem(key) || "{}"); } catch { saved = {}; }
    if (!saved || typeof saved !== "object") saved = {};
    const state = { active: false, private: false, generation: 0, reading: false, busy: false, timer: 0, storageFailed: false, ideas: Array.isArray(saved.ideas) ? saved.ideas : [], drafts: saved.drafts && typeof saved.drafts === "object" ? saved.drafts : {}, pending: saved.pending && typeof saved.pending === "object" ? saved.pending : {}, publishPending: saved.publishPending && typeof saved.publishPending === "object" ? saved.publishPending : {}, pausePending: saved.pausePending || {}, publishReview: saved.publishReview || null, targets: [], dispatches: [], refinements: [], selectedId: saved.selectedId || "", mode: saved.mode === "tree" ? "tree" : "list", conflict: null, revision: "", readingSequence: 0, taskOpening: false, openTaskId: "", taskRevision: 0 };
    const controllers = new Set();
    const header = make("header", "", "incubator-header"), heading = make("div"); heading.append(make("h2", "任务工作区"), make("p", offline ? "想法保存在此手机，与电脑工作区不自动共享。" : "文字与图片作为底稿，在同一任务里讨论、工作，再看结果继续修改。", "incubator-muted"));
    const fresh = button("＋ 新建想法", () => newIdea(), "incubator-primary"), refresh = button(offline ? "读取已保存想法" : "同步", () => void reload()), importIdea = button("导入想法 JSON", () => { migration.hidden = false; importText.focus(); }); header.append(heading, fresh, refresh, importIdea);
    const notice = make("p", "", "incubator-notice"); notice.setAttribute("role", "status"); notice.setAttribute("aria-live", "polite");
    const main = make("div", "", "incubator-main"), sidebar = make("aside", "", "incubator-sidebar"), tools = make("div", "", "incubator-view-tools"), mode = select([{ id: "list", name: "列表" }, { id: "tree", name: "树状思维导图" }]); mode.setAttribute("aria-label", "想法视图"); mode.value = state.mode;
    tools.append(field("查看", mode)); const list = make("div", "", "incubator-list"); sidebar.append(tools, list);
    const editor = make("section", "", "incubator-editor"), empty = make("div", "", "incubator-empty"); empty.append(make("h3", "每个还没想清楚的念头，都可以从这里开始。"), button("新建一个想法", () => newIdea(), "incubator-primary"));
    const title = input(), body = make("textarea"), stage = select(stages), priority = select(priorities), targetKind = select(targets), targetName = input(), targetThreadId = input(), parent = select([{ id: "", name: "独立想法" }]);
    title.maxLength = 160; title.placeholder = "一句话记下想法"; body.maxLength = 20000; body.rows = phone ? 4 : 5; body.placeholder = "想解决什么？想到什么就先写下来，后面再补细节。"; targetName.maxLength = 120; targetName.placeholder = "例如：Codex Console"; targetThreadId.maxLength = 160; targetThreadId.placeholder = "可选：准确的聊天 ID";
    const metadata = make("div", "", "incubator-metadata"); metadata.append(field("阶段", stage), field("优先级", priority), field("归属想法", parent));
    targetThreadId.maxLength = 128;
    const routing = make("details", "", "incubator-routing"), knownTarget = select([{ id: "", name: "选择现有聊天（可稍后指定）" }]), advancedTarget = make("details", "", "incubator-advanced"); advancedTarget.append(make("summary", "高级：手动指定聊天 ID"), field("聊天 ID", targetThreadId)); routing.append(make("summary", "目标聊天"), field("平台", targetKind), field("已有聊天", knownTarget), field("具体聊天名", targetName), advancedTarget, make("p", "用于整理和生成任务稿；保存不会发送给任何聊天。", "incubator-muted"));
    const publication = make("label", "", "incubator-publication"), publishedCheck = input(); publishedCheck.type = "checkbox"; publication.append(publishedCheck, make("span", "我已手动把任务发送到目标聊天"));
    const saveState = make("p", "", "incubator-save-state"), actions = make("div", "", "incubator-actions"), save = button(offline ? "保存到此手机" : "保存想法", () => void saveIdea(), "incubator-primary"), prepare = button("生成发布任务稿", () => prepareDraft()), refine = button("反复完善任务稿", () => preparePublication("refine")), publish = button("发布到目标聊天", () => preparePublication()), exportIdea = button("带到另一工作区", () => exportCurrent()); actions.append(save);
    const planning = make("details", "", "incubator-planning"), planningActions = make("div", "", "incubator-actions"); planning.append(make("summary", "排序、完善与发布"), metadata, routing, publication, planningActions); planningActions.append(prepare); if (!offline) planningActions.append(refine, publish); planningActions.append(exportIdea);
    const taskWorkspace = make("section", "", "incubator-task-workspace"), taskIntro = make("div", "", "incubator-task-intro"), taskStatus = make("p", "", "incubator-muted"), taskHost = make("div", "", "incubator-task-host"), taskOpen = button("打开任务工作区", () => void openTaskWorkspace(true)); taskIntro.append(make("h3", "Chat · Work · Output"), taskStatus, taskOpen); taskWorkspace.append(taskIntro, taskHost); taskWorkspace.hidden = offline || typeof options.onTaskOpen !== "function"; taskHost.hidden = true;
    const conflict = make("section", "", "incubator-conflict"), conflictText = make("p"); conflict.append(make("strong", "电脑与手机的编辑版本发生冲突"), conflictText, button("保留我的编辑，基于最新版本再保存", () => void resolveConflict()), button("载入服务器内容（替换当前编辑）", () => useServerVersion()));
    editor.append(field("标题", title), field("想法与任务内容", body), saveState, actions, conflict, taskWorkspace, planning);
    const preview = make("section", "", "incubator-preview"), taskText = make("textarea"), copy = button("复制完整任务稿", () => void copyDraft()), mark = button("我已手动发送，标记已发布", () => void markPublished()); taskText.readOnly = true; taskText.rows = 12; taskText.setAttribute("aria-label", "完整发布任务稿");
    preview.append(make("h3", "发布任务稿"), make("p", "尚未发送。可使用确认发布；需要手动发送时，复制到指定聊天。", "incubator-muted"), taskText, copy, mark, button("收起任务稿", () => { preview.hidden = true; })); planning.append(preview);
    const publishReview = make("section", "", "incubator-publish-review"), publishSnapshot = make("textarea"), publishKind = select(targets.filter(item => item.id !== "none")), publishMode = select([{ id: "new", name: "新建本机 Codex 聊天" }, { id: "existing", name: "已有聊天" }]), publishTarget = select([{ id: "", name: "请选择目标聊天" }]), publishThread = input(), publishName = input(), advancedPublish = make("details", "", "incubator-advanced"); publishSnapshot.readOnly = true; publishSnapshot.rows = 8; publishSnapshot.setAttribute("aria-label", "确认发布的已保存内容"); publishThread.maxLength = 128; publishName.maxLength = 120; advancedPublish.append(make("summary", "高级：目标列表没有所需聊天"), field("发布聊天 ID", publishThread), field("发布聊天名", publishName));
    const confirmPublish = button("确认发布此任务", () => void publishIdea(), "incubator-primary"), cancelPublish = button("取消发布", () => { state.publishReview = null; persist(); update(); });
    const publishHeading = make("h3", "确认发送到目标聊天"), publishExplanation = make("p", "", "incubator-muted"), roundLimit = select([{id:"1",name:"1 轮"},{id:"3",name:"3 轮"},{id:"5",name:"5 轮"},{id:"10",name:"10 轮"}]), roundField = field("完善轮次", roundLimit); roundLimit.value = "3";
    publishReview.append(publishHeading, publishExplanation, publishSnapshot, roundField, field("发布平台", publishKind), field("发布方式", publishMode), field("发布到已有聊天", publishTarget), advancedPublish, confirmPublish, cancelPublish);
    const dispatches = make("div", "", "incubator-dispatches"); if (!offline) planning.append(publishReview, dispatches);
    const migration = make("section", "", "incubator-migration"), exportText = make("textarea"), importText = make("textarea"), importFile = input(); exportText.readOnly = true; exportText.rows = 6; exportText.setAttribute("aria-label", "此想法的导出 JSON"); importText.rows = 6; importText.placeholder = "粘贴从另一工作区导出的想法 JSON"; importFile.type = "file"; importFile.accept = ".json,application/json"; importFile.hidden = true;
    migration.append(make("h3", "跨工作区带入想法"), make("p", "一次仅带一条想法，不携带聊天列表、发布记录或电脑配置。父关系会重置；导入不会发布。", "incubator-muted"), exportText, button("复制想法 JSON", () => void copyText(exportText, "JSON 已复制，可在另一工作区导入。")), button("下载想法 JSON", () => downloadExport()), importText, button("从 JSON 文件选择", () => importFile.click()), importFile, button("导入为新草稿", () => void importCurrent()), button("收起导入导出", () => { migration.hidden = true; }));
    main.append(sidebar, empty, editor); root.replaceChildren(header, notice, migration, main); root.classList.add("incubator-panel"); root.dataset.phone = String(phone);
    const controls = { title, body, stage, priority, targetKind, targetName, targetThreadId };
    function say(message, error = false) { notice.textContent = message; notice.dataset.error = String(error); }
    function persist() {
      if (state.private) return false;
      try { localStorage.setItem(key, JSON.stringify({ ideas: state.ideas, drafts: state.drafts, pending: state.pending, publishPending: state.publishPending, pausePending: state.pausePending, publishReview: state.publishReview, importText: importText.value, selectedId: state.selectedId, mode: state.mode })); state.storageFailed = false; return true; }
      catch { state.storageFailed = true; say("浏览器未能保存本地草稿，请保持此页打开并手动复制内容。", true); return false; }
    }
    function current() { return state.drafts[state.selectedId]; }
    function serverIdea(id) { return state.ideas.find(idea => idea.id === id); }
    function changed(draft = current()) { return Boolean(draft && (!draft.base || fingerprint(draft) !== fingerprint(draft.base))); }
    function remember() {
      const draft = current(); if (!draft || state.private) return;
      for (const name of Object.keys(controls)) draft[name] = controls[name].value;
      draft.parentId = parent.value || null; persist(); renderList(); update();
    }
    function loadEditor() {
      const draft = current(); if (!draft) { update(); return; }
      for (const name of Object.keys(controls)) controls[name].value = draft[name] ?? "";
      publishedCheck.checked = draft.base?.stage === "published"; fillParents(); fillTargets(); preview.hidden = true; update();
    }
    function hasOpenTask() { return !state.private && Boolean(state.openTaskId && state.openTaskId === state.selectedId); }
    function closeTask() {
      if (state.taskOpening) { say("任务工作区正在读取，请稍后再切换。", true); return false; }
      if (!offline && typeof options.onTaskLeave === "function" && options.onTaskLeave() === false) { say("请先结束当前录音或等待草稿、附件保存，再切换任务。", true); return false; }
      state.openTaskId = ""; state.taskRevision = 0; taskHost.hidden = true; options.onTaskStateChange?.(); update(); return true;
    }
    async function openTaskWorkspace(saveFirst = false) {
      if (offline || state.private || !state.active || state.busy || state.taskOpening || !current() || typeof options.onTaskOpen !== "function") return false;
      remember();
      if (saveFirst && (changed() || state.pending[state.selectedId]) && !await saveIdea()) return false;
      const draft = current(), snapshot = serverIdea(draft?.id) || draft?.base;
      if (!snapshot || localId(draft.id)) { if (saveFirst) say("先保存这条任务，工作区会继续使用同一条任务。", true); return false; }
      if (!saveFirst && !snapshot.workflowRecordId && !hasOpenTask()) return false;
      const activeContext = hasOpenTask() && options.getTaskContext?.();
      if (activeContext?.ideaId === draft.id && activeContext.recordId === snapshot.workflowRecordId && Number(activeContext.revision) === Number(snapshot.revision) && activeContext.title === snapshot.title && (activeContext.body || "") === (snapshot.body || "")) { state.taskRevision = Number(activeContext.revision); update(); return true; }
      const id = state.selectedId, generation = state.generation;
      state.taskOpening = true; update();
      try {
        const accepted = await options.onTaskOpen({ ideaId: id, recordId: snapshot.workflowRecordId || undefined, revision: Number(snapshot.revision), title: snapshot.title, body: snapshot.body });
        if (generation !== state.generation || id !== state.selectedId || state.private || !state.active) return false;
        if (!accepted) { say("请先结束录音或等待草稿、附件保存，再打开这条任务。", true); return false; }
        const context = options.getTaskContext?.();
        if (!context || context.ideaId !== id || !context.recordId || Number(context.revision) !== Number(snapshot.revision) || snapshot.workflowRecordId && context.recordId !== snapshot.workflowRecordId) throw Error("任务与工作记录关联没有核验通过，请同步后重试。");
        snapshot.workflowRecordId = context.recordId;
        if (draft.base?.id === id) draft.base.workflowRecordId = context.recordId;
        state.openTaskId = id; state.taskRevision = Number(context.revision); options.onTaskMount?.(taskHost); taskHost.hidden = false; persist(); options.onTaskStateChange?.();
        say("已打开这条任务。Chat 只讨论；Work 需单独确认，结果会回到这里。"); return true;
      } catch (error) { if (generation === state.generation && !state.private && state.active) say(error.message || "任务工作区暂时无法打开，原任务和草稿仍保留。", true); return false; }
      finally { state.taskOpening = false; update(); }
    }
    function isDescendant(candidateId, ancestorId) {
      const seen = new Set(); let next = candidateId;
      while (next && !seen.has(next)) { if (next === ancestorId) return true; seen.add(next); next = state.drafts[next]?.parentId || serverIdea(next)?.parentId; } return false;
    }
    function fillParents() {
      const choices = [{ id: "", name: "独立想法" }, ...state.ideas.filter(idea => idea.id !== state.selectedId && !isDescendant(idea.id, state.selectedId)).map(idea => ({ id: idea.id, name: idea.title }))];
      const chosen = current()?.parentId || ""; fillOptions(parent, choices, chosen);
    }
    function fillTargets() {
      const choices = state.targets.filter(item => targetKind.value === "none" || item.kind === targetKind.value).map(item => ({ id: item.id, name: `${item.kind === "chatgpt" ? "ChatGPT" : "Codex"} · ${item.name || item.title || item.id}` }));
      fillOptions(knownTarget, [{ id: "", name: choices.length ? "请选择现有聊天" : "暂无聊天快照，可稍后指定" }, ...choices], targetThreadId.value); knownTarget.disabled = offline || !choices.length;
      if (state.publishReview) fillPublicationTargets();
    }
    function fillPublicationTargets() {
      const review = state.publishReview; if (!review) return;
      fillOptions(publishMode, review.kind === "chatgpt" ? [{ id: "existing", name: "已有 ChatGPT 聊天" }] : [{ id: "new", name: "新建本机 Codex 聊天" }, { id: "existing", name: "已有 Codex 聊天" }], review.mode); review.mode = publishMode.value;
      fillOptions(publishTarget, [{ id: "", name: "请选择目标聊天" }, ...state.targets.filter(item => item.kind === review.kind).map(item => ({ id: item.id, name: item.name || item.title || item.id }))], review.threadId);
      publishTarget.parentElement.hidden = advancedPublish.hidden = review.mode !== "existing";
    }
    function promptFor(idea) { return idea.publishPrompt || `以下是我从任务孵化器主动发布的想法，请根据内容继续讨论或推进。\n\n标题：${idea.title}\n优先级：${priorities.find(item => item.id === idea.priority)?.name || "普通"}\n成熟度：${({ vague: "模糊", thinking: "思考中", ready: "已成熟", queued: "已排队", published: "已发布" })[idea.stage] || "模糊"}\n\n${idea.body || "（尚无正文，请先协助明确这个想法。）"}`; }
    function refinementPrompt(idea, limit) {
      return `这是任务孵化器的第 1/${limit} 轮提示词完善。\n本次只授权分析、澄清、检查遗漏并重写下面的完整任务稿；禁止执行任务、运行命令、修改项目、发送消息或建立其他聊天。\n保留用户意图与限制，避免加入未经授权的操作。请指出关键缺口，再给出可直接保存的完整新版正文。\n完整稿须且仅须放在一个 <refined_prompt>完整新版正文</refined_prompt> 块中，不在块内使用该标签；不要只给差异或声称已经执行。\n\n标题：${idea.title}\n\n原稿：\n${idea.body || "（请先帮助明确此想法，不能自行执行。）"}`;
    }
    function restorePublication() {
      const review = state.publishReview; if (!review) return;
      publishSnapshot.value = review.prompt || ""; publishKind.value = review.kind; publishThread.value = review.threadId || ""; publishName.value = review.name || ""; fillPublicationTargets();
    }
    function preparePublication(purpose = "execute") {
      if (offline || state.busy || state.private || !state.active || !current()) return; remember();
      const draft = current(); if (changed(draft) || state.pending[draft.id] || !draft.base) { say("请先保存当前想法，再确认发布。", true); return; }
      if (!state.publishPending[draft.id] && state.dispatches.some(item => item.ideaId === draft.id && ["pending", "claimed", "waiting", "needs_review"].includes(item.status))) { say("这条想法已有发布在处理中，请查看实际状态，不要重复发布。", true); return; }
      const pending = state.publishPending[draft.id], snapshot = draft.base;
      state.publishReview = pending ? { ...pending.review } : { id: draft.id, expectedRevision: snapshot.revision, prompt: purpose === "refine" ? refinementPrompt(snapshot, 3) : promptFor(snapshot), snapshot: content(snapshot), purpose: purpose === "refine" ? "refine" : "execute", roundLimit: 3, kind: snapshot.targetKind === "chatgpt" ? "chatgpt" : "codex", mode: snapshot.targetThreadId ? "existing" : snapshot.targetKind === "chatgpt" ? "existing" : "new", threadId: snapshot.targetThreadId || "", name: snapshot.targetName || snapshot.title };
      planning.open = true; restorePublication(); persist(); update(); publishReview.scrollIntoView?.({ block: "nearest", behavior: "smooth" }); say("请核对已保存的任务内容与目标聊天。点确认后才进入发布队列。");
    }
    function publicationError() {
      const review = state.publishReview; if (!review) return "请先打开发布确认。";
      if (!["codex", "chatgpt"].includes(review.kind) || !["new", "existing"].includes(review.mode) || review.kind === "chatgpt" && review.mode !== "existing") return "ChatGPT 必须选择已有聊天。";
      if (review.mode === "existing" && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(review.threadId || "")) return "请选择已有聊天，或在高级选项输入准确的聊天 ID。";
      if (review.name?.length > 120) return "聊天名称超过长度限制。";
      return "";
    }
    async function publishIdea() {
      if (offline || state.busy || state.private || !state.active || !state.publishReview || state.publishReview.id !== state.selectedId) return;
      const id = state.selectedId; let pending = state.publishPending[id];
      if (!pending) {
        const error = publicationError(); if (error) { say(error, true); return; }
        const review = state.publishReview; pending = { review: { ...review }, payload: { requestId: uuid(), id, expectedRevision: Number(review.expectedRevision), targetKind: review.kind, targetMode: review.mode, targetThreadId: review.mode === "new" ? null : review.threadId, targetName: review.name || "", ...(review.purpose === "refine" ? { purpose: "refine", roundLimit: Number(review.roundLimit || 3) } : {}) } }; state.publishPending[id] = pending;
        if (!persist()) { delete state.publishPending[id]; return; }
      }
      state.busy = true; state.readingSequence++; update();
      try {
        const result = await call("incubator/publish", pending.payload); if (!result.dispatch?.id || !result.idea?.id) throw Error("发布没有返回确认结果，请用原请求重试。");
        const draft = state.drafts[id], dirty = changed(draft); state.ideas = [result.idea, ...state.ideas.filter(item => item.id !== result.idea.id)]; state.drafts[id] = { ...(dirty ? content(draft) : content(result.idea)), id, base: result.idea };
        state.dispatches = [result.dispatch, ...state.dispatches.filter(item => item.id !== result.dispatch.id)]; if (result.refinement) state.refinements = [result.refinement, ...state.refinements.filter(item => item.id !== result.refinement.id)]; delete state.publishPending[id]; state.publishReview = null; state.readingSequence++; persist(); loadEditor(); renderList(); say(pending.review.purpose === "refine" ? "已进入任务稿完善队列。只分析与改稿，结束后仍需你决定正式派工。" : "已进入发布队列，尚未确认目标聊天收到。请查看下方实际状态。");
      } catch (error) {
        if (error.cancelled) return;
        if (error.status >= 400 && error.status < 500) { delete state.publishPending[id]; if (error.status === 409) state.publishReview = null; persist(); say(`发布未接受：${error.message} 当前草稿仍保留，请同步后核对。`, true); }
        else say(`发布尚未确认：${error.message} 原请求已保留，请重试，不会重复创建发布。`, true);
      } finally { state.busy = false; update(); schedule(); }
    }
    function renderDispatches() {
      dispatches.replaceChildren(); if (offline) return;
      const refinementNames = {active:"正在完善任务稿",paused:"已暂停后续完善",needs_review:"任务稿完善需要核对",completed:"任务稿完善已结束，等待你决定派工"};
      for (const session of state.refinements.filter(item => item.ideaId === state.selectedId)) {
        const card = make("article", "", "incubator-refinement"); card.dataset.state = session.state;
        card.append(make("strong", refinementNames[session.state] || session.state), make("p", `第 ${session.round} / ${session.roundLimit} 轮 · 只分析和改稿`));
        if (session.state === "active" || state.pausePending[session.id]) card.append(button(state.pausePending[session.id] ? "重试原暂停请求" : "暂停后续完善", () => void pauseRefinement(session.id)));
        if (session.state === "paused") card.append(make("p", "已经发出的这一轮仍会回收；不会再自动发下一轮。", "incubator-muted"));
        if (session.error) card.append(make("p", session.error, "incubator-muted")); dispatches.append(card);
      }
      const names = { pending: "排队，目标聊天尚未确认收到", claimed: "正在送达目标聊天", waiting: "目标聊天已收到，等待处理结果", completed: "任务结果已回收", failed: "发布失败", needs_review: "送达情况需要核查" };
      for (const item of state.dispatches.filter(item => item.ideaId === state.selectedId)) {
        const card = make("article", "", "incubator-dispatch"); card.dataset.dispatchId = item.id; card.dataset.status = item.status; card.append(make("strong", item.purpose === "refine" && item.status === "completed" ? "本轮任务稿完善结果已回收" : names[item.status] || item.status), make("p", `${item.purpose === "refine" ? `任务稿完善 · 第 ${item.round} / ${item.roundLimit} 轮 · ` : "正式派工 · "}${item.targetKind === "chatgpt" ? "ChatGPT" : "Codex"} · ${item.targetName || (item.targetMode === "new" ? "新本机聊天" : item.targetThreadId || "目标聊天")}`));
        if (item.result?.text) card.append(make("p", item.result.text)); if (item.error) card.append(make("p", item.error, "incubator-muted")); if (item.targetThreadId) card.append(make("code", item.targetThreadId)); dispatches.append(card);
      }
    }
    async function pauseRefinement(id) {
      if (state.busy || state.private || !state.active) return;
      const payload = state.pausePending[id] || {requestId:uuid(), id}; state.pausePending[id] = payload; if (!persist()) return;
      state.busy = true; update();
      try { const result = await call("incubator/refinement/pause", payload); state.refinements = [result.refinement, ...state.refinements.filter(item => item.id !== id)]; delete state.pausePending[id]; persist(); say("已停止后续轮次；已发出的这一轮仍会回收，不会继续自动完善。"); }
      catch (error) { if (!error.cancelled) { if (error.status >= 400 && error.status < 500) delete state.pausePending[id]; persist(); say(`暂停尚未确认：${error.message}`, true); } }
      finally { state.busy = false; update(); schedule(); }
    }
    function exportCurrent() {
      if (state.busy || state.private || !current()) return; remember(); exportText.value = JSON.stringify({ format: "codex-incubator-idea", version: 1, idea: content(current()) }, null, 2); migration.hidden = false; exportText.focus(); say("只导出这一条想法；未包含目标列表、配置或发布记录。");
    }
    function downloadExport() {
      if (!exportText.value || state.private || !state.active) return;
      if (!globalThis.Blob || !globalThis.URL?.createObjectURL) { say("此浏览器不能下载文件，请复制上方 JSON。", true); return; }
      const url = URL.createObjectURL(new Blob([exportText.value], { type: "application/json" })), anchor = make("a"); anchor.href = url; anchor.download = "codex-incubator-idea.json"; root.append(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
    }
    async function importCurrent() {
      if (state.busy || state.private || !state.active || state.taskOpening) return;
      try {
        if (!importText.value || importText.value.length > 100000) throw Error("请粘贴单条想法 JSON，文件不超过 200 KB。");
        const data = JSON.parse(importText.value); if (data.format !== "codex-incubator-idea" || data.version !== 1 || !data.idea || typeof data.idea !== "object" || Array.isArray(data.idea) || Object.keys(data).some(name => !["format", "version", "idea"].includes(name)) || Object.keys(data.idea).some(name => !fields.includes(name))) throw Error("请选择从孵化器导出的单条想法 JSON。");
        const value = content(data.idea); if (fields.some(name => name !== "parentId" && typeof value[name] !== "string") || !value.title.trim() || value.title.length > 160 || value.body.length > 20000 || value.targetName.length > 120 || value.targetThreadId.length > 128 || !stages.some(item => item.id === value.stage) || !priorities.some(item => item.id === value.priority) || !targets.some(item => item.id === value.targetKind)) throw Error("想法 JSON 的字段或长度无效。");
        if (!closeTask()) return; value.parentId = null; if (value.stage === "published") value.stage = "ready"; remember(); const id = `local-${uuid()}`; state.drafts[id] = { id, ...value, base: null }; state.selectedId = id; state.conflict = null; importText.value = ""; migration.hidden = true; persist(); loadEditor(); renderList(); say("已导入为新草稿，请点保存。父关系已重置，原已发布状态改为待发布；没有发布到任何聊天。");
      } catch (error) { say(`导入失败：${error.message} 原有想法与草稿保持不变。`, true); }
    }
    function newIdea() {
      if (state.private || state.busy || !closeTask()) return;
      remember(); const id = `local-${uuid()}`; state.drafts[id] = { id, ...content(), base: null }; state.selectedId = id; state.conflict = null; const stored = persist(); loadEditor(); renderList(); title.focus(); if (stored) say(offline ? "新想法草稿先保留在此页，点击“保存到此手机”。不会发布。" : "新想法先保存在本地。点击“保存想法”同步到电脑，不会发布。");
    }
    function choose(id) {
      if (state.private || state.busy || state.taskOpening) return false;
      if (id !== state.selectedId && !closeTask()) return false;
      remember(); const idea = serverIdea(id); if (!state.drafts[id] && idea) state.drafts[id] = { ...content(idea), id, base: idea };
      if (!state.drafts[id]) return false; state.selectedId = id; state.conflict = null; persist(); loadEditor(); renderList(); say("编辑草稿会保留在本地；保存不会发布。"); void openTaskWorkspace(); return true;
    }
    function allIdeas() {
      const map = new Map(state.ideas.map(idea => [idea.id, idea]));
      for (const draft of Object.values(state.drafts)) if (draft && draft.id) map.set(draft.id, draft); return [...map.values()];
    }
    function renderList() {
      list.replaceChildren(); list.dataset.view = state.mode;
      const ideas = allIdeas(); if (!ideas.length) { list.append(make("p", "还没有想法，点上方“新建想法”。", "incubator-muted")); return; }
      const weight = { high: 0, normal: 1, low: 2 }; ideas.sort((a, b) => (weight[a.priority] ?? 1) - (weight[b.priority] ?? 1) || String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")));
      const visited = new Set();
      const renderIdea = (idea, depth, container = list) => {
        if (visited.has(idea.id)) return; visited.add(idea.id);
        const card = button("", () => choose(idea.id), "incubator-idea"); card.dataset.ideaId = idea.id; card.dataset.selected = String(idea.id === state.selectedId); card.style.setProperty("--incubator-depth", String(Math.min(depth, 12))); card.setAttribute("aria-pressed", String(idea.id === state.selectedId));
        const draft = state.drafts[idea.id]; card.append(make("strong", idea.title || "未命名想法"), make("span", `${stages.find(item => item.id === idea.stage)?.name || "模糊"} · ${priorities.find(item => item.id === idea.priority)?.name || "普通"}${draft && changed(draft) ? " · 本地草稿" : ""}`));
        if (state.mode === "tree") {
          const branch = make("div", "", "incubator-tree-node"), children = ideas.filter(item => item.parentId === idea.id); branch.dataset.ideaId = idea.id; branch.append(card); container.append(branch);
          if (children.length) { const lines = make("div", "", "incubator-tree-children"); branch.append(lines); for (const child of children) renderIdea(child, depth + 1, lines); }
        } else container.append(card);
      };
      if (state.mode === "tree") { for (const idea of ideas.filter(item => !item.parentId || !ideas.some(parent => parent.id === item.parentId))) renderIdea(idea, 0); for (const idea of ideas) renderIdea(idea, 0); }
      else for (const idea of ideas) renderIdea(idea, 0);
    }
    function validation() {
      if (!title.value.trim()) return "请先写一个标题。";
      if (title.value.trim().length > 160 || body.value.length > 20000 || targetName.value.length > 120 || targetThreadId.value.length > 128) return "标题、内容或目标聊天超过长度限制。";
      if (!stages.some(item => item.id === stage.value) || !priorities.some(item => item.id === priority.value) || !targets.some(item => item.id === targetKind.value)) return "请选择有效的阶段、优先级和平台。";
      if (stage.value === "published" && current()?.base?.stage !== "published" && !publishedCheck.checked) return "仅在你已手动发送后，才能标记“已发布”。";
      return "";
    }
    function update() {
      const draft = current(), available = state.active && !state.private, working = state.busy || state.taskOpening; empty.hidden = Boolean(draft); editor.hidden = !draft; conflict.hidden = !state.conflict;
      fresh.disabled = working || !available; importIdea.disabled = working || !available; refresh.disabled = state.reading || working || !available; save.disabled = !available || working || !draft || !state.pending[draft.id] && Boolean(validation()); prepare.disabled = !available || working || !draft || !title.value.trim(); exportIdea.disabled = !available || working || !draft; publish.disabled = !available || working || !draft || changed(draft) || Boolean(state.pending[draft.id]) || !state.publishPending[state.selectedId] && state.dispatches.some(item => item.ideaId === state.selectedId && ["pending", "claimed", "waiting", "needs_review"].includes(item.status)); publish.setAttribute("title", "先保存当前想法，再确认发布到目标聊天；处理中不重复发布");
      taskOpen.disabled = !available || working || !draft || Boolean(validation()); taskOpen.textContent = state.taskOpening ? "正在打开任务…" : hasOpenTask() ? changed(draft) || state.taskRevision !== Number(draft?.base?.revision) ? "保存并更新任务底稿" : "任务工作区已打开" : changed(draft) ? "保存并打开任务工作区" : "打开任务工作区"; taskOpen.hidden = hasOpenTask() && !changed(draft) && state.taskRevision === Number(draft?.base?.revision);
      taskHost.hidden = !hasOpenTask(); taskStatus.textContent = hasOpenTask() ? changed(draft) ? "底稿修改尚未保存。先保存并更新，讨论和工作再使用新版本。" : state.taskRevision !== Number(draft?.base?.revision) ? "底稿的新版本已保存，工作区尚未载入。请更新任务底稿后再继续讨论或工作。" : "Chat 讨论 · Work 在电脑 Workspace 工作 · Output 回到本任务" : "在这里添加图片、讨论并工作，不需要打开另一个任务或手机 ChatGPT。";
      for (const control of [...Object.values(controls), parent, publishedCheck]) control.disabled = state.taskOpening;
      refine.disabled = publish.disabled; publication.hidden = stage.value !== "published" || draft?.base?.stage === "published";
      saveState.textContent = draft ? state.storageFailed ? "草稿目前只在此页，本地保存失败，请复制备份。" : state.pending[draft.id] ? "保存未确认送达；草稿和原请求已保留，可安全重试。" : changed(draft) ? offline ? "此页草稿已保留，点击保存到此手机。" : "本地草稿已保留，尚未同步到电脑。" : offline ? "已保存到此手机。与电脑工作区不自动共享。" : "已保存到电脑。保存不等于发布。" : "";
      save.textContent = draft && state.pending[draft.id] ? "重试原保存请求" : offline ? "保存到此手机" : "保存想法";
      copy.disabled = !available || state.busy; mark.disabled = !available || state.busy || Boolean(draft && state.pending[draft.id]);
      const refining = state.publishReview?.purpose === "refine"; roundField.hidden = !refining; roundLimit.disabled = state.busy || Boolean(state.publishPending[state.selectedId]); roundLimit.value = String(state.publishReview?.roundLimit || 3);
      publishHeading.textContent = refining ? "确认完善任务稿" : "确认正式派工"; publishExplanation.textContent = refining ? `只授权 ${state.publishReview.roundLimit || 3} 轮分析与重写。每轮结果会改进任务稿；不会执行任务，也不会自动正式派工。` : "只有点确认才正式进入派工队列。目标聊天收到后会显示实际状态；排队不等于完成。";
      publishReview.hidden = offline || !state.publishReview || state.publishReview.id !== state.selectedId; confirmPublish.disabled = !available || state.busy || !state.publishReview || !state.publishPending[state.selectedId] && Boolean(publicationError()); confirmPublish.textContent = state.publishPending[state.selectedId] ? "重试原发布请求" : refining ? `确认完善 ${state.publishReview.roundLimit || 3} 轮` : "确认发布此任务"; cancelPublish.disabled = state.busy; renderDispatches();
    }
    async function call(path, payload) {
      const controller = new AbortController(), generation = state.generation; controllers.add(controller);
      try {
        if (adapter) { const data = await adapter(path, payload); if (generation !== state.generation || !state.active || state.private) throw Object.assign(new Error("请求已取消。"), { cancelled: true }); if (!offline) options.onConnectionState?.(true); return data; }
        const result = await fetch(`${base}/${path}`, { method: payload ? "POST" : "GET", credentials: "same-origin", mode: "same-origin", referrerPolicy: "same-origin", redirect: "error", headers: { Accept: "application/json", ...(payload ? { "Content-Type": "application/json" } : {}), ...(phone ? { "X-Codex-Phone": "1" } : {}) }, body: payload ? JSON.stringify(payload) : undefined, signal: controller.signal, cache: "no-store" });
        const data = await result.json().catch(() => ({}));
        if (generation !== state.generation || !state.active || state.private) throw Object.assign(new Error("请求已取消。"), { cancelled: true });
        options.onConnectionState?.(true);
        if (result.status === 401) { clear(); options.onAuth?.(); throw Object.assign(new Error("请重新连接电脑。"), { cancelled: true }); }
        if (!result.ok) throw Object.assign(new Error(data.error || "电脑暂时无法保存想法。"), { status: result.status, data });
        return data;
      } catch (error) { if (error.name === "AbortError") error.cancelled = true; if (!error.cancelled && error.status === 401) { clear(); options.onAuth?.(); error.cancelled = true; } if (!error.cancelled && !error.status && !offline) options.onConnectionState?.(false); throw error; }
      finally { controllers.delete(controller); }
    }
    function schedule() { window.clearTimeout(state.timer); state.timer = 0; if (!offline && state.active && !state.private && !document.hidden) state.timer = window.setTimeout(() => void reload(), 30000); }
    async function reload() {
      if (!state.active || state.private || state.reading || document.hidden) return;
      state.reading = true; const sequence = ++state.readingSequence; update();
      try {
        const data = await call("incubator"); if (sequence !== state.readingSequence) return;
        if (!data.unchanged) state.ideas = Array.isArray(data.ideas) ? data.ideas : []; state.revision = data.revision || ""; if (!offline) { state.targets = Array.isArray(data.targets) ? data.targets : state.targets; state.dispatches = Array.isArray(data.dispatches) ? data.dispatches : state.dispatches; state.refinements = Array.isArray(data.refinements) ? data.refinements : state.refinements; }
        for (const idea of state.ideas) { const draft = state.drafts[idea.id]; if (draft && !changed(draft) && !state.pending[idea.id] && !state.busy) state.drafts[idea.id] = { ...content(idea), id: idea.id, base: idea }; }
        if (!current() && state.ideas.length) { state.selectedId = state.ideas[0].id; state.drafts[state.selectedId] = { ...content(state.ideas[0]), id: state.selectedId, base: state.ideas[0] }; loadEditor(); }
        else if (current() && !changed() && !state.busy) loadEditor(); else fillParents();
        fillTargets(); persist(); renderList();
      } catch (error) { if (!error.cancelled) say(offline ? "暂时无法读取此手机保存的想法，编辑草稿仍在此页。" : error.status ? `同步失败：${error.message} 编辑草稿仍保留。` : "暂时连接不到电脑，本地草稿仍保留。恢复连接后点保存即可同步。", true); }
      finally { state.reading = false; update(); schedule(); void openTaskWorkspace(); }
    }
    function mergeAccepted(result, pending) {
      const idea = result.idea; if (!idea?.id) throw new Error("服务器没有返回保存结果，请使用原请求重试。"); state.readingSequence++;
      const original = state.drafts[pending.localId]; state.ideas = [idea, ...state.ideas.filter(item => item.id !== idea.id)];
      if (original) { const newer = fingerprint(original) !== fingerprint(pending.payload); state.drafts[idea.id] = { ...(newer ? content(original) : content(idea)), id: idea.id, base: idea }; if (pending.localId !== idea.id) delete state.drafts[pending.localId]; }
      delete state.pending[pending.localId]; if (state.selectedId === pending.localId) { state.selectedId = idea.id; loadEditor(); } state.conflict = null; persist(); renderList();
      say(offline ? "已保存到此手机。想法尚未发送给聊天，与电脑工作区不自动共享。" : "已保存到电脑。想法尚未发送给聊天。");
    }
    async function saveIdea() {
      if (state.busy || state.taskOpening || state.private || !state.active || !current()) return false; remember();
      const id = state.selectedId; let pending = state.pending[id];
      if (!pending) {
        const error = validation(); if (error) { say(error, true); return false; }
        const draft = current(), payload = { requestId: uuid(), ...content(draft), title: draft.title.trim() };
        if (!localId(id)) Object.assign(payload, { id, expectedRevision: Number(draft.base?.revision || 0) });
        pending = { localId: id, path: localId(id) ? "incubator/create" : "incubator/update", payload }; state.pending[id] = pending;
        if (!persist()) { delete state.pending[id]; return false; }
      }
      state.busy = true; state.readingSequence++; update();
      try { mergeAccepted(await call(pending.path, pending.payload), pending); return true; }
      catch (error) {
        if (error.cancelled) return false;
        if (error.status === 409 && error.data?.code === "revision_conflict") {
          delete state.pending[id]; state.conflict = { id, current: error.data.idea || error.data.current || error.data.currentIdea || null }; persist();
          conflictText.textContent = "你的编辑草稿没有被覆盖。先同步服务器最新版本，再选择保留自己的编辑或载入服务器内容。"; say("保存发生版本冲突，当前草稿已保留。", true);
          try { const data = await call("incubator"); state.ideas = Array.isArray(data.ideas) ? data.ideas : state.ideas; state.conflict.current = serverIdea(id) || state.conflict.current; renderList(); } catch (readError) { if (!readError.cancelled) say("版本冲突；暂时无法获取最新版本。请同步后再处理，草稿仍保留。", true); }
        } else if (error.status >= 400 && error.status < 500) { delete state.pending[id]; persist(); say(`保存未接受：${error.message} 草稿已保留，修改后可重新保存。`, true); }
        else say(`${error.message} 草稿和原保存请求已保留，可重试。`, true);
        return false;
      } finally { state.busy = false; update(); schedule(); if (hasOpenTask()) void openTaskWorkspace(); }
    }
    async function resolveConflict() {
      if (state.busy || !state.conflict || state.conflict.id !== state.selectedId) return;
      const latest = serverIdea(state.selectedId) || state.conflict.current;
      if (!latest) { say("请先同步，取得服务器的最新版本。", true); return; }
      remember(); current().base = latest; state.conflict = null; persist(); update(); await saveIdea();
    }
    function useServerVersion() {
      if (state.busy || !state.conflict || state.conflict.id !== state.selectedId) return;
      const latest = serverIdea(state.selectedId) || state.conflict.current; if (!latest) { say("请先同步，取得服务器的最新版本。", true); return; }
      state.drafts[state.selectedId] = { ...content(latest), id: latest.id, base: latest }; state.conflict = null; persist(); loadEditor(); renderList(); say("已按你的选择载入服务器内容。");
    }
    function taskDraft() {
      const idea = current(); if (!idea) return "";
      const ancestors = [], seen = new Set([idea.id]); let id = idea.parentId;
      while (id && !seen.has(id)) { seen.add(id); const parentIdea = state.drafts[id] || serverIdea(id); if (!parentIdea) break; ancestors.unshift(parentIdea.title); id = parentIdea.parentId; }
      return [`任务：${idea.title.trim()}`, `目标：${targets.find(item => item.id === idea.targetKind)?.name || "尚未指定"}${idea.targetName ? ` / ${idea.targetName}` : ""}${idea.targetThreadId ? `（聊天 ID：${idea.targetThreadId}）` : ""}`, `优先级：${priorities.find(item => item.id === idea.priority)?.name || "普通"}`, ancestors.length ? `上层想法：${ancestors.join(" → ")}` : "", "", "任务内容：", idea.body || "（请补充任务内容）", "", "请先理解以上目标和约束；需要澄清的地方先提问。新建和保存这条想法不构成对外发布或执行授权。"].filter((line, index, array) => line || index > 0 && array[index - 1]).join("\n");
    }
    function prepareDraft() { if (state.busy || state.taskOpening || state.private || !current() || !title.value.trim()) return; remember(); taskText.value = taskDraft(); planning.open = true; preview.hidden = false; preview.scrollIntoView?.({ block: "nearest", behavior: "smooth" }); say("任务稿已生成，尚未发送。可确认发布，或复制后手动发送。"); }
    async function copyDraft() {
      if (state.private || !state.active || !taskText.value) return;
      try { if (window.isSecureContext && navigator.clipboard?.writeText) { await navigator.clipboard.writeText(taskText.value); say("已复制。请在目标聊天粘贴并手动发送。"); return; } } catch { /* Use selected text when clipboard access is refused. */ }
      taskText.focus(); taskText.select(); taskText.setSelectionRange?.(0, taskText.value.length);
      let copied = false; try { copied = Boolean(document.execCommand?.("copy")); } catch { /* Selected task text remains available. */ }
      say(copied ? "已复制。请在目标聊天粘贴并手动发送。" : "任务稿已选中，请长按或按 Ctrl+C 复制，再到目标聊天发送。");
    }
    async function copyText(control, success) {
      if (state.private || !state.active || !control.value) return;
      try { if (window.isSecureContext && navigator.clipboard?.writeText) { await navigator.clipboard.writeText(control.value); if (!state.private) say(success); return; } } catch { /* Keep selected JSON available for manual copy. */ }
      if (state.private) return; control.focus(); control.select(); control.setSelectionRange?.(0, control.value.length); let copied = false; try { copied = Boolean(document.execCommand?.("copy")); } catch { /* Manual fallback. */ } say(copied ? success : "JSON 已选中，请长按或按 Ctrl+C 复制。");
    }
    async function markPublished() { if (state.busy || state.private || !current() || state.pending[state.selectedId]) return; stage.value = "published"; publishedCheck.checked = true; remember(); await saveIdea(); }
    function clear() {
      state.private = true; state.active = false; state.generation++; state.readingSequence++; window.clearTimeout(state.timer); state.timer = 0; for (const controller of controllers) controller.abort();
      state.ideas = []; state.drafts = {}; state.pending = {}; state.publishPending = {}; state.pausePending = {}; state.publishReview = null; state.targets = []; state.dispatches = []; state.refinements = []; state.selectedId = ""; state.conflict = null; state.busy = false; state.reading = false; state.openTaskId = ""; state.taskRevision = 0;
      for (const control of Object.values(controls)) control.value = ""; taskText.value = ""; publishSnapshot.value = ""; exportText.value = ""; importText.value = ""; publishedCheck.checked = false; preview.hidden = true; migration.hidden = true; notice.textContent = ""; try { localStorage.removeItem(key); } catch { /* Private UI is already cleared. */ } renderList(); update();
    }
    for (const control of Object.values(controls)) { control.addEventListener("input", remember); control.addEventListener("change", remember); }
    parent.addEventListener("change", remember); publishedCheck.addEventListener("change", update);
    targetKind.addEventListener("change", () => { remember(); fillTargets(); });
    knownTarget.addEventListener("change", () => { const chosen = state.targets.find(item => item.id === knownTarget.value); if (!chosen) return; targetKind.value = chosen.kind; targetName.value = chosen.name || chosen.title || ""; targetThreadId.value = chosen.id; remember(); fillTargets(); });
    const rememberPublication = () => { const review = state.publishReview; if (!review || state.busy) return; review.kind = publishKind.value; review.mode = publishMode.value; review.threadId = publishThread.value; review.name = publishName.value; fillPublicationTargets(); persist(); update(); };
    roundLimit.addEventListener("change", () => { if (!state.publishReview || state.busy || state.publishPending[state.selectedId]) return; state.publishReview.roundLimit = Number(roundLimit.value); state.publishReview.prompt = refinementPrompt(state.publishReview.snapshot, state.publishReview.roundLimit); publishSnapshot.value = state.publishReview.prompt; persist(); update(); });
    publishKind.addEventListener("change", () => { if (!state.publishReview || state.busy) return; state.publishReview.kind = publishKind.value; state.publishReview.threadId = ""; state.publishReview.name = ""; publishThread.value = ""; publishName.value = ""; fillPublicationTargets(); persist(); update(); });
    publishMode.addEventListener("change", rememberPublication); publishThread.addEventListener("input", rememberPublication); publishName.addEventListener("input", rememberPublication);
    publishTarget.addEventListener("change", () => { const chosen = state.targets.find(item => item.id === publishTarget.value && item.kind === publishKind.value); publishThread.value = chosen?.id || ""; publishName.value = chosen?.name || chosen?.title || ""; rememberPublication(); });
    importText.value = typeof saved.importText === "string" ? saved.importText : ""; importText.addEventListener("input", persist);
    importFile.addEventListener("change", async () => { const file = importFile.files?.[0], generation = state.generation; importFile.value = ""; if (!file || state.private || !state.active) return; if (!file.size || file.size > 200 * 1024 || !/\.json$/i.test(file.name)) { say("请选择不超过 200 KB 的想法 JSON 文件。", true); return; } try { const text = await file.text(); if (generation !== state.generation || state.private || !state.active) return; importText.value = text; persist(); say("文件已读取，请核对后点“导入为新草稿”。"); } catch { if (generation === state.generation && !state.private) say("无法读取 JSON 文件，请复制内容后粘贴。", true); } });
    mode.addEventListener("change", () => { state.mode = mode.value === "tree" ? "tree" : "list"; persist(); renderList(); });
    document.addEventListener("visibilitychange", () => { if (document.hidden) { window.clearTimeout(state.timer); state.timer = 0; } else if (state.active && !state.private) void reload(); });
    preview.hidden = true; migration.hidden = true; loadEditor(); renderList(); restorePublication(); update();
    return {
      setActive(value) { const next = Boolean(value), changedActive = state.active !== next; state.active = next; if (next && changedActive) { state.private = false; loadEditor(); void reload(); } else if (!next) { remember(); state.generation++; state.readingSequence++; window.clearTimeout(state.timer); state.timer = 0; for (const controller of controllers) controller.abort(); } update(); },
      refresh: reload, clear, hasDraft() { return Boolean(state.busy || state.taskOpening || importText.value.trim() || state.publishReview || Object.keys(state.pending).length || Object.keys(state.publishPending).length || Object.keys(state.pausePending).length || Object.values(state.drafts).some(draft => changed(draft) && Boolean(draft.title?.trim() || draft.body?.trim()))); }, canReload() { return !state.busy && !state.taskOpening && !state.storageFailed; }, selectIdea: choose, openTask: openTaskWorkspace, closeTask, hasOpenTask,
      async useTarget(thread) {
        if (!state.active || state.private || state.busy || !thread || !["codex","chatgpt"].includes(thread.kind)) return false;
        const draft = current(); if (!draft) { say("先选择一条已经准备好的任务，再选择目标会话。", true); return false; }
        remember(); const hadEdits = changed(draft);
        state.targets = [thread, ...state.targets.filter(item => item.id !== thread.id)]; targetKind.value = thread.kind; targetThreadId.value = thread.id; targetName.value = thread.title || thread.name || ""; remember(); fillTargets();
        if (!hadEdits && draft.base && !await saveIdea()) return false;
        if (state.private || !state.active) return false;
        say(hadEdits || !draft.base ? "目标会话已选好，当前草稿保留。先保存，再选择完善任务稿或正式发布。" : "已关联选中的会话。可完善现成任务稿，或核对后正式发布；尚未发送。"); return true;
      }
    };
  }
  window.CodexIncubatorPanel = { create };
})();
