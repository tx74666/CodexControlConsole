#!/usr/bin/env node
// Executes the component with isolated DOM/storage/network fixtures; no browser or chat delivery.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
const source = readFileSync(new URL("../incubator-panel.js", import.meta.url), "utf8");
const css = readFileSync(new URL("../incubator-panel.css", import.meta.url), "utf8");
const clone = value => JSON.parse(JSON.stringify(value));
const settle = async () => { for (let index = 0; index < 5; index++) await new Promise(resolve => setImmediate(resolve)); };
const defer = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const response = (body, status = 200) => ({ status, ok: status >= 200 && status < 300, async json() { return clone(body); } });
const idea = (id, patch = {}) => ({ id, title: `想法 ${id}`, body: "保存、整理、随后才发布", stage: "vague", priority: "normal", parentId: null, targetKind: "none", targetName: "", targetThreadId: "", revision: 1, createdAt: "2026-10-04T10:00:00Z", updatedAt: "2026-10-04T10:00:00Z", ...patch });
function harness({ phone = true, ideas = [], server = { ideas, receipts: new Map() }, storage = new Map(), secure = false, failStorage = false, offline = false, taskOptions = {} } = {}) {
  class Element {
    constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.listeners = new Map(); this.dataset = {}; this.attributes = {}; this.hidden = false; this.disabled = false; this.value = ""; this._text = ""; this.checked = false; this.classList = { add() {} }; this.style = { values: {}, setProperty(name, value) { this.values[name] = value; } }; }
    append(...children) { for (const child of children) { if (child.parentElement) child.parentElement.children = child.parentElement.children.filter(value => value !== child); this.children.push(child); child.parentElement = this; } }
    replaceChildren(...children) { this.children.forEach(child => { child.parentElement = null; }); this.children = []; this._text = ""; this.append(...children); }
    set textContent(value) { this.replaceChildren(); this._text = String(value); }
    get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
    set innerHTML(value) { throw Error("Do not insert HTML from saved ideas"); }
    setAttribute(name, value) { this.attributes[name] = String(value); }
    addEventListener(name, action) { this.listeners.set(name, action); }
    fire(name, values = {}) { return this.listeners.get(name)?.({ preventDefault() {}, ...values }); }
    click() { if (!this.disabled) return this.fire("click"); }
    focus() { this.focused = true; }
    select() { this.selected = true; }
    setSelectionRange(start, end) { this.selection = [start, end]; }
    scrollIntoView() { this.scrolled = true; }
    remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(child => child !== this); }
  }
  const root = new Element("div"), calls = [], timers = new Map(), events = new Map(), connection = [], clipboard = [];
  let timerId = 0, failPath = "", pendingResponse = null, auth = 0, panel;
  const document = { hidden: false, createElement: tag => new Element(tag), addEventListener(name, action) { events.set(name, action); }, execCommand: () => false };
  const base = phone ? "/api/phone/workflow" : "/api/workflow";
  const runtime = { document, AbortController, TypeError, localStorage: { getItem: key => storage.get(key) || null, setItem(key, value) { if (failStorage) throw Error("Quota reached"); storage.set(key, value); }, removeItem: key => storage.delete(key) }, navigator: { clipboard: { async writeText(text) { clipboard.push(text); } } }, window: { isSecureContext: secure, setTimeout(action, delay) { const id = ++timerId; timers.set(id, { action, delay }); return id; }, clearTimeout: id => timers.delete(id) }, async fetch(url, options) {
    assert.ok(url.startsWith(base + "/incubator")); const path = url.slice(base.length + 1), payload = options.body ? JSON.parse(options.body) : null; calls.push({ path, payload, options });
    if (pendingResponse?.path === path) { const waiting = pendingResponse; pendingResponse = null; return waiting.promise; }
    const result = backend(path, payload); if (failPath === path) { failPath = ""; throw new TypeError("Lost response"); } return result;
  } };
  function backend(path, payload) {
    if (path === "incubator") return response({ ideas: server.ideas, targets: server.targets || [], dispatches: server.dispatches || [], refinements: server.refinements || [], revision: `r${server.ideas.reduce((sum, item) => sum + item.revision, 0)}` });
    assert.deepEqual(Object.keys(payload).filter(key => !["requestId", "id", "expectedRevision", "title", "body", "stage", "priority", "parentId", "targetKind", "targetThreadId", "targetName", ...(path === "incubator/publish" ? ["targetMode", "purpose", "roundLimit"] : [])].includes(key)), []);
    if (server.receipts.has(payload.requestId)) return response({ ...server.receipts.get(payload.requestId), duplicate: true });
    if (path === "incubator/refinement/pause") {
      const refinement = server.refinements.find(item => item.id === payload.id); assert.ok(refinement); refinement.state = "paused";
      const result = {refinement:clone(refinement), revision:"paused"}; server.receipts.set(payload.requestId, clone(result)); return response(result);
    }
    let saved;
    if (path === "incubator/publish") {
      assert.deepEqual(Object.keys(payload).sort(), ["requestId", "id", "expectedRevision", "targetKind", "targetMode", "targetThreadId", "targetName", ...(payload.purpose === "refine" ? ["purpose","roundLimit"] : [])].sort());
      saved = server.ideas.find(item => item.id === payload.id); assert.ok(saved);
      if (saved.revision !== payload.expectedRevision) return response({ error: "发布版本已变化", code: "revision_conflict" }, 409);
      server.dispatches ||= []; if (server.dispatches.some(item => item.ideaId === saved.id && ["pending", "claimed", "waiting", "needs_review"].includes(item.status))) return response({ error: "已有发布在处理中", code: "dispatch_active" }, 409);
      assert.ok(payload.targetKind === "codex" || payload.targetMode === "existing"); if (payload.targetMode === "existing") assert.match(payload.targetThreadId, /^[a-f\d-]{36}$/i);
      const dispatch = { id: `dispatch-${server.dispatches.length + 1}`, ideaId: saved.id, status: "pending", targetKind: payload.targetKind, targetMode: payload.targetMode, targetThreadId: payload.targetThreadId, targetName: payload.targetName, snapshot: clone(saved), prompt: saved.publishPrompt || saved.body, result: {} }; server.dispatches.push(dispatch); saved.stage = "queued"; saved.revision++;
      let refinement;
      if (payload.purpose === "refine") { server.refinements ||= []; refinement = {id:`refine-${server.refinements.length+1}`,ideaId:saved.id,state:"active",round:1,roundLimit:payload.roundLimit}; server.refinements.push(refinement); Object.assign(dispatch,{purpose:"refine",refinementId:refinement.id,round:1,roundLimit:payload.roundLimit}); }
      const result = { dispatch, idea: clone(saved), ...(refinement ? {refinement:clone(refinement)} : {}), revision: `r${saved.revision}`, duplicate: false }; server.receipts.set(payload.requestId, clone(result)); return response(result);
    }
    if (path === "incubator/create") { saved = idea(`server-${server.ideas.length + 1}`, payload); delete saved.requestId; server.ideas.unshift(saved); }
    else if (path === "incubator/update") {
      const current = server.ideas.find(item => item.id === payload.id); assert.ok(current);
      if (current.revision !== payload.expectedRevision) return response({ error: "想法已由另一端修改", code: "revision_conflict", idea: current }, 409);
      Object.assign(current, payload, { revision: current.revision + 1 }); delete current.expectedRevision; delete current.requestId; saved = current;
    } else throw Error(`Unexpected mutation: ${path}`);
    const result = { idea: clone(saved), revision: `r${saved.revision}`, duplicate: false }; server.receipts.set(payload.requestId, result); return response(result);
  }
  const endpoint = offline ? async (path, payload) => { calls.push({ path, payload: payload ? clone(payload) : null, options: { method: payload ? "POST" : "GET", adapter: true } }); const result = backend(path, payload); const data = await result.json(); if (!result.ok) throw Object.assign(Error(data.error), { status: result.status, data }); return data; } : undefined;
  if (offline) runtime.fetch = () => { throw Error("Offline adapter must not fetch the public site"); };
  runInNewContext(source, runtime); panel = runtime.window.CodexIncubatorPanel.create(root, { phone, offline, endpoint, storageKey: offline ? "codexIncubator.phone.v1" : undefined, onAuth() { auth++; }, onConnectionState: value => connection.push(value), ...taskOptions });
  const all = (tag, start = root) => { const results = []; const visit = element => { if (element.tagName === tag.toUpperCase()) results.push(element); element.children.forEach(visit); }; visit(start); return results; };
  const button = label => all("button").find(element => element.textContent === label), field = label => all("label").find(element => element.children[0]?.textContent === label)?.children[1];
  return { root, panel, runtime, server, storage, calls, timers, events, connection, clipboard, all, button, field, auth: () => auth, async start() { panel.setActive(true); await settle(); }, new() { button("＋ 新建想法").click(); }, type(label, value) { const control = field(label); control.value = value; control.fire("input"); }, change(label, value) { const control = field(label); control.value = value; control.fire("change"); }, fail(path) { failPath = path; }, pending(path, promise) { pendingResponse = { path, promise }; }, async poll() { const timer = [...timers.values()].find(item => item.delay === 30000); assert.ok(timer); timer.action(); await settle(); }, cards() { return all("button").filter(element => element.className === "incubator-button incubator-idea"); } };
}
let count = 0;
async function test(name, action) { await action(); count++; console.log(`PASS ${name}`); }

await test("new ideas are prominent, locally durable and never require a model or post automatically", async () => {
  const h = harness(); await h.start(); h.new(); h.type("标题", "还很模糊的想法"); h.type("想法与任务内容", "暂时只记录，不执行");
  assert.equal(h.calls.filter(call => call.options.method === "POST").length, 0); assert.equal(h.panel.hasDraft(), true); assert.match([...h.storage.values()][0], /还很模糊的想法/); assert.equal(h.button("保存想法").disabled, false); assert.ok(h.button("生成发布任务稿"));
});
await test("normal save uses the final flat contract, creates only an idea and clears saved draft guard", async () => {
  const h = harness(); await h.start(); h.new(); h.type("标题", "Console 手机任务"); h.type("想法与任务内容", "仔细审阅要求"); h.change("阶段", "ready"); h.change("优先级", "high"); h.change("平台", "codex"); h.type("具体聊天名", "Codex Console"); h.type("聊天 ID", "exact-console-chat"); h.button("保存想法").click(); await settle();
  const payload = h.calls.find(call => call.path === "incubator/create").payload; assert.equal(payload.stage, "ready"); assert.equal(payload.priority, "high"); assert.equal(payload.targetKind, "codex"); assert.equal(payload.targetThreadId, "exact-console-chat"); assert.equal(payload.parentId, null); assert.equal(h.server.ideas.length, 1); assert.equal(h.panel.hasDraft(), false); assert.match(h.root.textContent, /保存不等于发布/);
});
await test("every stage stays a persisted planning state; published requires explicit manual-send acknowledgement", async () => {
  const h = harness({ ideas: [idea("one")] }); await h.start(); for (const stage of ["vague", "thinking", "ready", "queued"]) { h.change("阶段", stage); h.button("保存想法").click(); await settle(); }
  h.change("阶段", "published"); assert.equal(h.button("保存想法").disabled, true); const checkbox = h.all("input").find(element => element.type === "checkbox"); checkbox.checked = true; checkbox.fire("change"); h.button("保存想法").click(); await settle(); assert.equal(h.server.ideas[0].stage, "published"); assert.ok(h.calls.filter(call => call.options.method === "POST").every(call => call.path === "incubator/update"));
});
await test("task generation and copy are local only with target, full body, priority and parent context", async () => {
  const h = harness({ secure: true, ideas: [idea("parent", { title: "手机协作入口" }), idea("child", { title: "保留草稿", body: "不清除用户输入\n完成后验证", parentId: "parent", targetKind: "chatgpt", targetName: "设计讨论", targetThreadId: "target-42", priority: "high" })] }); await h.start(); h.panel.selectIdea("child"); h.button("生成发布任务稿").click(); const task = h.all("textarea").find(element => element.attributes["aria-label"] === "完整发布任务稿"); assert.match(task.value, /ChatGPT \/ 设计讨论（聊天 ID：target-42）/); assert.match(task.value, /上层想法：手机协作入口/); assert.match(task.value, /不清除用户输入\n完成后验证/); assert.match(task.value, /优先级：高/); h.button("复制完整任务稿").click(); await settle(); assert.equal(h.clipboard[0], task.value); assert.equal(h.calls.filter(call => call.options.method === "POST").length, 0); assert.match(h.root.textContent, /尚未发送/);
});
await test("insecure LAN copy gives selected text fallback and does not claim a delivered message", async () => {
  const h = harness(); await h.start(); h.new(); h.type("标题", "离线可整理"); h.button("生成发布任务稿").click(); h.button("复制完整任务稿").click(); await settle(); const task = h.all("textarea").find(element => element.attributes["aria-label"] === "完整发布任务稿"); assert.equal(task.selected, true); assert.equal(h.clipboard.length, 0); assert.match(h.root.textContent, /长按或按 Ctrl\+C 复制/); assert.equal(h.calls.filter(call => call.options.method === "POST").length, 0);
});
await test("explicit manual-send button marks published without any chat delivery request", async () => {
  const h = harness(); await h.start(); h.new(); h.type("标题", "已自行发送的任务"); h.button("生成发布任务稿").click(); h.button("我已手动发送，标记已发布").click(); await settle(); assert.equal(h.server.ideas[0].stage, "published"); assert.equal(h.calls.filter(call => call.options.method === "POST").length, 1); assert.equal(h.calls.at(-1).path, "incubator/create");
});
await test("switching ideas, tabs and recreating the component preserve separate local drafts", async () => {
  const server = { ideas: [idea("a"), idea("b")], receipts: new Map() }, storage = new Map(); const h = harness({ server, storage }); await h.start(); h.type("想法与任务内容", "A未保存内容"); h.panel.selectIdea("b"); h.type("想法与任务内容", "B未保存内容"); h.panel.setActive(false); assert.equal(h.timers.size, 0); const reopened = harness({ server, storage }); await reopened.start(); assert.equal(reopened.field("想法与任务内容").value, "B未保存内容"); reopened.panel.selectIdea("a"); assert.equal(reopened.field("想法与任务内容").value, "A未保存内容"); assert.equal(reopened.calls.filter(call => call.options.method === "POST").length, 0);
});
await test("lost save response survives reopening and retries exactly the original request once", async () => {
  const storage = new Map(), server = { ideas: [], receipts: new Map() }, h = harness({ storage, server }); await h.start(); h.new(); h.type("标题", "幂等保存"); h.fail("incubator/create"); h.button("保存想法").click(); await settle(); const original = h.calls.find(call => call.path === "incubator/create").payload; assert.equal(server.ideas.length, 1); assert.ok(h.button("重试原保存请求")); h.panel.setActive(false);
  const reopened = harness({ storage, server }); await reopened.start(); reopened.button("重试原保存请求").click(); await settle(); assert.deepEqual(reopened.calls.find(call => call.path === "incubator/create").payload, original); assert.equal(server.ideas.length, 1); assert.equal(reopened.panel.hasDraft(), false);
});
await test("editing after uncertain save never changes its payload or loses newer unsent text", async () => {
  const h = harness(); await h.start(); h.new(); h.type("标题", "原稿"); h.type("想法与任务内容", "原先内容"); h.fail("incubator/create"); h.button("保存想法").click(); await settle(); const request = h.calls.find(call => call.path === "incubator/create").payload; h.type("想法与任务内容", "响应丢失后继续写的内容"); h.button("重试原保存请求").click(); await settle(); const retry = h.calls.filter(call => call.path === "incubator/create").at(-1); assert.deepEqual(retry.payload, request); assert.equal(h.field("想法与任务内容").value, "响应丢失后继续写的内容"); assert.equal(h.panel.hasDraft(), true); h.button("保存想法").click(); await settle(); const update = h.calls.find(call => call.path === "incubator/update").payload; assert.notEqual(update.requestId, request.requestId); assert.equal(update.expectedRevision, 1); assert.equal(h.server.ideas[0].body, "响应丢失后继续写的内容");
});
await test("optimistic conflict keeps local input and only explicit rebase saves on the latest revision", async () => {
  const h = harness({ ideas: [idea("shared")] }); await h.start(); h.type("想法与任务内容", "手机保留的编辑"); h.server.ideas[0].body = "电脑另一份编辑"; h.server.ideas[0].revision = 2; h.button("保存想法").click(); await settle(); assert.equal(h.field("想法与任务内容").value, "手机保留的编辑"); assert.match(h.root.textContent, /版本发生冲突/); assert.equal(h.server.ideas[0].body, "电脑另一份编辑"); h.button("保留我的编辑，基于最新版本再保存").click(); await settle(); assert.equal(h.server.ideas[0].body, "手机保留的编辑"); assert.equal(h.calls.filter(call => call.path === "incubator/update").at(-1).payload.expectedRevision, 2); assert.equal(h.server.ideas[0].revision, 3);
});
await test("explicit server-version choice replaces only the selected conflicted draft", async () => {
  const h = harness({ ideas: [idea("shared"), idea("other")] }); await h.start(); h.panel.selectIdea("other"); h.type("想法与任务内容", "另一条草稿"); h.panel.selectIdea("shared"); h.type("想法与任务内容", "当前手机编辑"); h.server.ideas[0].body = "服务器新内容"; h.server.ideas[0].revision++; h.button("保存想法").click(); await settle(); h.button("载入服务器内容（替换当前编辑）").click(); assert.equal(h.field("想法与任务内容").value, "服务器新内容"); h.panel.selectIdea("other"); assert.equal(h.field("想法与任务内容").value, "另一条草稿");
});
await test("list and parent tree are navigable and exclude self or descendants from parent choices", async () => {
  const h = harness({ ideas: [idea("root"), idea("child", { parentId: "root" }), idea("leaf", { parentId: "child" }), idea("other")] }); await h.start(); const parentOptions = h.all("option", h.field("归属想法")).map(element => element.value); assert.ok(parentOptions.includes("other")); assert.ok(!parentOptions.includes("root")); assert.ok(!parentOptions.includes("child")); assert.ok(!parentOptions.includes("leaf")); const mode = h.all("select").find(element => element.attributes["aria-label"] === "想法视图"); mode.value = "tree"; mode.fire("change"); const depths = Object.fromEntries(h.cards().map(element => [element.dataset.ideaId, element.style.values["--incubator-depth"]])); assert.equal(depths.root, "0"); assert.equal(depths.child, "1"); assert.equal(depths.leaf, "2"); h.cards().find(element => element.dataset.ideaId === "leaf").click(); assert.equal(h.field("标题").value, "想法 leaf");
});
await test("frontmost low-frequency sync never overwrites dirty draft and stops in hidden or inactive tabs", async () => {
  const h = harness({ ideas: [idea("one")] }); await h.start(); h.type("想法与任务内容", "保留本地输入"); h.server.ideas[0].body = "远端更新"; h.server.ideas[0].revision++; await h.poll(); assert.equal(h.field("想法与任务内容").value, "保留本地输入"); assert.ok([...h.timers.values()].every(timer => timer.delay === 30000)); h.runtime.document.hidden = true; h.events.get("visibilitychange")(); assert.equal(h.timers.size, 0); const count = h.calls.length; await h.panel.refresh(); assert.equal(h.calls.length, count); h.runtime.document.hidden = false; h.events.get("visibilitychange")(); await settle(); assert.equal(h.field("想法与任务内容").value, "保留本地输入"); h.panel.setActive(false); assert.equal(h.timers.size, 0);
});
await test("stale list response cannot overwrite a newly accepted idea save", async () => {
  const h = harness({ ideas: [idea("one")] }); await h.start(); const waiting = defer(); h.pending("incubator", waiting.promise); const refreshing = h.panel.refresh(); h.type("标题", "新标题"); h.button("保存想法").click(); await settle(); waiting.resolve(response({ ideas: [idea("one")], revision: "old" })); await refreshing; assert.equal(h.field("标题").value, "新标题"); assert.ok(h.cards().some(card => card.textContent.includes("新标题"))); assert.equal(h.panel.hasDraft(), false);
});
await test("network failure is truthful and retains local draft and connectivity status", async () => {
  const h = harness({ ideas: [idea("one")] }); await h.start(); h.type("想法与任务内容", "断线也保留"); h.fail("incubator"); await h.panel.refresh(); assert.match(h.root.textContent, /暂时连接不到电脑/); assert.equal(h.connection.at(-1), false); assert.equal(h.field("想法与任务内容").value, "断线也保留"); await h.panel.refresh(); assert.equal(h.connection.at(-1), true);
});
await test("private clear and late responses do not restore old data or emit another mutation", async () => {
  const h = harness(); await h.start(); h.new(); h.type("标题", "隐私内容"); const waiting = defer(); h.pending("incubator/create", waiting.promise); h.button("保存想法").click(); await settle(); h.panel.clear(); waiting.resolve(response({ idea: idea("late", { title: "隐私内容" }) })); await settle(); assert.equal(h.storage.size, 0); assert.equal(h.field("标题").value, ""); assert.doesNotMatch(h.root.textContent, /隐私内容/); assert.equal(h.panel.hasDraft(), false); assert.equal(h.timers.size, 0);
});
await test("401 clears private drafts, disables the panel and calls the existing auth hook", async () => {
  const h = harness(); await h.start(); h.new(); h.type("标题", "配对私有内容"); h.pending("incubator", Promise.resolve(response({ error: "pair again" }, 401))); await h.panel.refresh(); assert.equal(h.auth(), 1); assert.equal(h.storage.size, 0); assert.equal(h.panel.hasDraft(), false); assert.equal(h.button("＋ 新建想法").disabled, true); assert.equal(h.timers.size, 0);
});
await test("length validation rejects malformed drafts before network and storage quota is not labelled durable", async () => {
  const h = harness(); await h.start(); h.new(); for (const [field, value] of [["标题", "x".repeat(161)], ["标题", "有效标题"]]) h.type(field, value); h.type("想法与任务内容", "x".repeat(20001)); assert.equal(h.button("保存想法").disabled, true); h.button("保存想法").click(); assert.equal(h.calls.filter(call => call.options.method === "POST").length, 0); const quota = harness({ failStorage: true }); await quota.start(); quota.new(); quota.type("标题", "本页仍有内容"); assert.match(quota.root.textContent, /本地保存失败|未能保存本地草稿/); assert.equal(quota.panel.hasDraft(), true); quota.button("保存想法").click(); await settle(); assert.equal(quota.calls.filter(call => call.options.method === "POST").length, 0);
});
await test("saved markup remains text, desktop and phone share routes, and CSS fits a narrow viewport", async () => {
  const h = harness({ phone: false, ideas: [idea("safe", { title: "<img src=x onerror=alert(1)>", body: "<script>bad()</script>" })] }); await h.start(); assert.equal(h.field("标题").value, "<img src=x onerror=alert(1)>"); assert.equal(h.cards()[0].children[0].textContent, "<img src=x onerror=alert(1)>"); assert.equal(h.all("script").length, 0); assert.equal(h.root.dataset.phone, "false"); assert.match(css, /@media\(max-width:700px\)/); assert.match(css, /\.incubator-main\{grid-template-columns:1fr/); assert.match(css, /font-size:16px/); assert.match(css, /\[hidden\]\{display:none!important\}/);
});
await test("publish needs a saved snapshot and explicit confirmation; double click enqueues once", async () => {
  const h = harness(); await h.start(); h.new(); h.type("标题", "明确发布"); h.type("想法与任务内容", "执行用户写明的要求"); assert.equal(h.button("发布到目标聊天").disabled, true); h.button("保存想法").click(); await settle(); h.server.ideas[0].publishPrompt = "服务器生成的完整已保存任务稿"; await h.panel.refresh(); h.button("发布到目标聊天").click(); assert.equal(h.calls.filter(call => call.path === "incubator/publish").length, 0); assert.equal(h.all("textarea").find(element => element.attributes["aria-label"] === "确认发布的已保存内容").value, "服务器生成的完整已保存任务稿"); const confirm = h.button("确认发布此任务"); confirm.click(); confirm.click(); await settle(); assert.equal(h.calls.filter(call => call.path === "incubator/publish").length, 1); assert.equal(h.server.dispatches.length, 1); assert.equal(h.server.ideas[0].stage, "queued"); assert.match(h.root.textContent, /目标聊天尚未确认收到/); assert.equal(h.button("发布到目标聊天").disabled, true);
});
await test("real Codex snapshot target selection preserves its exact title and ID", async () => {
  const id = "01a10257-e1b3-7ce2-a0af-cf9df4ec2c09", server = { ideas: [idea("route")], receipts: new Map(), targets: [{ id, kind: "codex", name: "Codex Console" }] }; const h = harness({ server }); await h.start(); h.change("已有聊天", id); assert.equal(h.field("平台").value, "codex"); assert.equal(h.field("具体聊天名").value, "Codex Console"); assert.equal(h.field("聊天 ID").value, id); h.button("保存想法").click(); await settle(); h.button("发布到目标聊天").click(); assert.equal(h.field("发布到已有聊天").value, id); h.button("确认发布此任务").click(); await settle(); const payload = h.calls.find(call => call.path === "incubator/publish").payload; assert.equal(payload.targetMode, "existing"); assert.equal(payload.targetThreadId, id); assert.equal(payload.targetName, "Codex Console"); assert.ok(!("text" in payload));
});
await test("ChatGPT publishing offers existing chats only and does not invent a new Work conversation", async () => {
  const id = "11111111-2222-4333-8444-555555555555", server = { ideas: [idea("chatgpt", { targetKind: "chatgpt" })], receipts: new Map(), targets: [{ id, kind: "chatgpt", name: "想法讨论" }] }; const h = harness({ server }); await h.start(); h.button("发布到目标聊天").click(); assert.deepEqual(h.all("option", h.field("发布方式")).map(element => element.value), ["existing"]); assert.equal(h.button("确认发布此任务").disabled, true); h.change("发布到已有聊天", id); assert.equal(h.button("确认发布此任务").disabled, false); h.button("确认发布此任务").click(); await settle(); const payload = h.calls.find(call => call.path === "incubator/publish").payload; assert.equal(payload.targetKind, "chatgpt"); assert.equal(payload.targetMode, "existing"); assert.equal(payload.targetThreadId, id);
});
await test("opened publication review stays on saved revision while later edits remain local", async () => {
  const h = harness({ ideas: [idea("freeze", { body: "已保存的指令" })] }); await h.start(); h.button("发布到目标聊天").click(); h.type("想法与任务内容", "审核打开后新写的草稿"); h.button("确认发布此任务").click(); await settle(); assert.equal(h.server.dispatches[0].snapshot.body, "已保存的指令"); assert.equal(h.field("想法与任务内容").value, "审核打开后新写的草稿"); assert.equal(h.panel.hasDraft(), true); assert.equal(h.server.ideas[0].body, "已保存的指令");
});
await test("uncertain publish persists and reuses original target and request ID after reopening", async () => {
  const storage = new Map(), server = { ideas: [idea("pending")], receipts: new Map() }, h = harness({ storage, server }); await h.start(); h.button("发布到目标聊天").click(); h.fail("incubator/publish"); h.button("确认发布此任务").click(); await settle(); const original = h.calls.find(call => call.path === "incubator/publish").payload; assert.equal(server.dispatches.length, 1); assert.ok(h.button("重试原发布请求")); h.panel.setActive(false); const reopened = harness({ storage, server }); await reopened.start(); assert.equal(reopened.calls.filter(call => call.path === "incubator/publish").length, 0); reopened.button("重试原发布请求").click(); await settle(); assert.deepEqual(reopened.calls.find(call => call.path === "incubator/publish").payload, original); assert.equal(server.dispatches.length, 1); assert.equal(reopened.panel.hasDraft(), false);
});
await test("dispatch polling distinguishes target receipt and final result without republishing", async () => {
  const h = harness({ ideas: [idea("status")] }); await h.start(); h.button("发布到目标聊天").click(); h.button("确认发布此任务").click(); await settle(); h.server.dispatches[0].status = "waiting"; h.server.dispatches[0].targetName = "实际新建的聊天"; await h.poll(); assert.match(h.root.textContent, /目标聊天已收到，等待处理结果/); h.server.dispatches[0].status = "completed"; h.server.dispatches[0].result = { text: "结果：已处理该想法" }; h.server.ideas[0].stage = "published"; h.server.ideas[0].revision++; await h.poll(); assert.match(h.root.textContent, /任务结果已回收/); assert.match(h.root.textContent, /结果：已处理该想法/); assert.match(h.root.textContent, /实际新建的聊天/); assert.equal(h.calls.filter(call => call.path === "incubator/publish").length, 1); assert.equal(h.field("阶段").value, "published");
});
await test("needs-review remains visibly unresolved and active dispatch blocks another publication", async () => {
  const server = { ideas: [idea("review")], receipts: new Map(), dispatches: [{ id: "uncertain", ideaId: "review", status: "needs_review", targetKind: "codex", targetMode: "new", targetName: "目标聊天", error: "需核对是否已送达" }] }, h = harness({ server }); await h.start(); assert.match(h.root.textContent, /送达情况需要核查/); assert.match(h.root.textContent, /需核对是否已送达/); assert.equal(h.button("发布到目标聊天").disabled, true); assert.equal(h.calls.filter(call => call.options.method === "POST").length, 0);
});
await test("publication revision conflict retains local draft and never silently publishes newer content", async () => {
  const h = harness({ ideas: [idea("stale")] }); await h.start(); h.button("发布到目标聊天").click(); h.server.ideas[0].revision++; h.server.ideas[0].body = "电脑新版内容"; h.type("想法与任务内容", "手机另一个草稿"); h.button("确认发布此任务").click(); await settle(); assert.match(h.root.textContent, /发布未接受/); assert.equal(h.field("想法与任务内容").value, "手机另一个草稿"); assert.equal(h.server.dispatches?.length || 0, 0); assert.equal(h.button("重试原发布请求"), undefined); assert.equal(h.panel.hasDraft(), true);
});
await test("offline adapter saves to this phone, never fetches, publishes, polls or claims PC synchronization", async () => {
  const storage = new Map(), h = harness({ offline: true, storage }); await h.start(); assert.equal(h.button("发布到目标聊天"), undefined); h.new(); h.type("标题", "此手机想法"); h.type("想法与任务内容", "离线可保存"); h.button("保存到此手机").click(); await settle(); assert.match(h.root.textContent, /已保存到此手机/); assert.match(h.root.textContent, /与电脑工作区不自动共享/); assert.ok(h.calls.every(call => call.options.adapter)); assert.equal(h.timers.size, 0); assert.equal(h.connection.length, 0); assert.equal(h.panel.canReload(), true); assert.ok(storage.has("codexIncubator.phone.v1")); h.type("想法与任务内容", "新持久草稿"); assert.equal(h.panel.hasDraft(), true); assert.equal(h.panel.canReload(), true); h.button("生成发布任务稿").click(); h.button("我已手动发送，标记已发布").click(); await settle(); assert.equal(h.server.ideas[0].stage, "published"); assert.ok(h.calls.every(call => !call.path.includes("publish")));
});
await test("single-idea JSON export excludes dispatch/config and import remaps to a new unpublishing draft", async () => {
  const original = harness({ ideas: [idea("parent"), idea("child", { body: "可迁移内容", stage: "published", parentId: "parent" })] }); await original.start(); original.panel.selectIdea("child"); original.button("带到另一工作区").click(); const exported = original.all("textarea").find(element => element.attributes["aria-label"] === "此想法的导出 JSON").value, data = JSON.parse(exported); assert.deepEqual(Object.keys(data).sort(), ["format", "idea", "version"]); assert.ok(!("dispatches" in data.idea)); assert.ok(!("id" in data.idea)); assert.equal(data.idea.parentId, "parent");
  const imported = harness(); await imported.start(); imported.button("导入想法 JSON").click(); const entry = imported.all("textarea").find(element => element.placeholder?.startsWith("粘贴从另一工作区")); entry.value = exported; entry.fire("input"); imported.button("导入为新草稿").click(); await settle(); assert.equal(imported.field("想法与任务内容").value, "可迁移内容"); assert.equal(imported.field("阶段").value, "ready"); assert.equal(imported.field("归属想法").value, ""); assert.equal(imported.calls.filter(call => call.options.method === "POST").length, 0); imported.button("保存想法").click(); await settle(); const payload = imported.calls.find(call => call.path === "incubator/create").payload; assert.equal(payload.parentId, null); assert.equal(payload.stage, "ready"); assert.equal(imported.server.ideas.length, 1); assert.equal(imported.server.dispatches?.length || 0, 0);
});
await test("invalid JSON or unexpected transfer fields never replace existing editor content", async () => {
  const h = harness({ ideas: [idea("keep", { body: "原有内容" })] }); await h.start(); h.button("导入想法 JSON").click(); const entry = h.all("textarea").find(element => element.placeholder?.startsWith("粘贴从另一工作区")); for (const value of ["not json", JSON.stringify({ format: "codex-incubator-idea", version: 1, idea: { title: "攻击", body: "", dispatches: [] } }), "x".repeat(100001)]) { entry.value = value; entry.fire("input"); h.button("导入为新草稿").click(); await settle(); assert.equal(h.field("想法与任务内容").value, "原有内容"); assert.match(h.root.textContent, /导入失败/); } assert.equal(h.calls.filter(call => call.options.method === "POST").length, 0);
});
await test("rejected 400 save can be corrected with a new request and reload waits only for unsafe persistence", async () => {
  const h = harness(); await h.start(); h.new(); h.type("标题", "需更正"); h.pending("incubator/create", Promise.resolve(response({ error: "目标聊天无效" }, 400))); h.button("保存想法").click(); await settle(); const old = h.calls.find(call => call.path === "incubator/create").payload.requestId; assert.match(h.root.textContent, /保存未接受/); assert.equal(h.button("重试原保存请求"), undefined); h.type("标题", "已更正"); const waiting = defer(); h.pending("incubator/create", waiting.promise); h.button("保存想法").click(); assert.equal(h.panel.canReload(), false); waiting.resolve(response({ idea: idea("new", { title: "已更正" }) })); await settle(); assert.notEqual(h.calls.filter(call => call.path === "incubator/create").at(-1).payload.requestId, old); assert.equal(h.panel.canReload(), true); const quota = harness({ failStorage: true }); await quota.start(); quota.new(); quota.type("标题", "不能保证重载恢复"); assert.equal(quota.panel.canReload(), false);
});
await test("tree view renders actual nested branch connectors and keeps narrow-screen titles readable", async () => {
  const h = harness({ ideas: [idea("parent"), idea("child", { parentId: "parent", title: "很长的子任务名称".repeat(12) }), idea("grandchild", { parentId: "child" })] }); await h.start(); const mode = h.all("select").find(element => element.attributes["aria-label"] === "想法视图"); assert.ok(h.all("option", mode).some(element => element.textContent === "树状思维导图")); mode.value = "tree"; mode.fire("change"); const card = h.cards().find(element => element.dataset.ideaId === "grandchild"); assert.equal(card.parentElement.className, "incubator-tree-node"); assert.equal(card.parentElement.parentElement.className, "incubator-tree-children"); assert.equal(card.parentElement.parentElement.parentElement.dataset.ideaId, "child"); assert.match(css, /incubator-tree-children\{[^}]*border-left:2px/); assert.match(css, /incubator-tree-node:before\{[^}]*border-top:2px/); assert.match(css, /overflow-wrap:anywhere/); assert.match(css, /\.incubator-list\[data-view=tree\]\{max-height:230px;overflow:auto/);
});
await test("paired phone GET/save/publish carry the same-origin auth gate while desktop sends no phone header", async () => {
  for (const phone of [true, false]) {
    const h = harness({ phone }); await h.start(); h.new(); h.type("标题", "请求配对验证"); h.button("保存想法").click(); await settle(); h.button("发布到目标聊天").click(); h.button("确认发布此任务").click(); await settle();
    assert.ok(h.calls.some(call => call.path === "incubator" && call.options.method === "GET")); assert.ok(h.calls.some(call => call.path === "incubator/create" && call.options.method === "POST")); assert.ok(h.calls.some(call => call.path === "incubator/publish" && call.options.method === "POST"));
    for (const call of h.calls) { assert.equal(call.options.headers.Accept, "application/json"); assert.equal(call.options.headers["X-Codex-Phone"], phone ? "1" : undefined); assert.equal(call.options.credentials, "same-origin"); assert.equal(call.options.mode, "same-origin"); assert.equal(call.options.referrerPolicy, "same-origin"); assert.equal(call.options.redirect, "error"); if (call.options.method === "POST") assert.equal(call.options.headers["Content-Type"], "application/json"); }
  }
});
await test("prepared saved task uses a selected conversation without typing or sending", async () => {
  const h = harness({ideas:[idea("ready",{title:"现成任务稿",body:"完整的原任务内容",stage:"ready"})]}); await h.start();
  await h.panel.useTarget({id:"01a10257-e1b3-7ce2-a0af-cf9df4ec2c09",kind:"codex",title:"Codex Console"});
  assert.equal(h.field("想法与任务内容").value,"完整的原任务内容"); assert.equal(h.server.ideas[0].targetName,"Codex Console");
  assert.equal(h.server.ideas[0].targetThreadId,"01a10257-e1b3-7ce2-a0af-cf9df4ec2c09"); assert.equal(h.calls.filter(call=>call.path==="incubator/publish").length,0);
  h.button("反复完善任务稿").click(); assert.ok(h.button("确认完善 3 轮")); assert.match(h.root.textContent,/不会自动正式派工/);
});
await test("refinement confirmation explicitly bounds rounds and stays separate from execution", async () => {
  const h = harness({ideas:[idea("saved")]}); await h.start(); h.button("反复完善任务稿").click(); h.change("完善轮次","5");
  const preview=h.all("textarea").find(element=>element.attributes["aria-label"]==="确认发布的已保存内容");
  assert.match(preview.value,/第 1\/5 轮提示词完善/); assert.match(preview.value,/禁止执行任务/); assert.match(preview.value,/<refined_prompt>/);
  assert.ok(h.button("确认完善 5 轮")); assert.equal(h.calls.filter(call=>call.path==="incubator/publish").length,0);
  h.button("确认完善 5 轮").click(); await settle(); const sent=h.calls.find(call=>call.path==="incubator/publish").payload;
  assert.equal(sent.purpose,"refine"); assert.equal(sent.roundLimit,5); assert.match(h.root.textContent,/只分析和改稿/); assert.ok(h.button("暂停后续完善"));
  h.button("暂停后续完善").click(); await settle(); assert.equal(h.server.refinements[0].state,"paused");
  assert.equal(h.calls.filter(call=>call.path==="incubator/publish").length,1); assert.match(h.root.textContent,/不会再自动发下一轮/);
});
await test("selecting a conversation keeps an unsaved task and requires deliberate save", async () => {
  const h=harness({ideas:[idea("saved")]}); await h.start(); h.type("想法与任务内容","尚未保存的修改");
  await h.panel.useTarget({id:"6ac16523-a468-83e8-a16a-877c3ec8f64a",kind:"chatgpt",title:"手机版App建议"});
  assert.equal(h.field("想法与任务内容").value,"尚未保存的修改"); assert.equal(h.calls.filter(call=>call.payload).length,0);
  assert.match(h.root.textContent,/当前草稿保留/);
});
await test("uncertain refinement retry retains purpose and authorized round count", async () => {
  const server={ideas:[idea("saved")],receipts:new Map()},storage=new Map(); let h=harness({server,storage}); await h.start();
  h.button("反复完善任务稿").click(); h.change("完善轮次","1"); h.fail("incubator/publish"); h.button("确认完善 1 轮").click(); await settle();
  const first=h.calls.find(call=>call.path==="incubator/publish").payload; h.panel.setActive(false); h=harness({server,storage}); await h.start();
  h.button("重试原发布请求").click(); await settle(); assert.deepEqual(h.calls.find(call=>call.path==="incubator/publish").payload,first);
  assert.equal(server.refinements.length,1); assert.equal(first.roundLimit,1);
});
await test("associating a prepared task does not hide an uncertain save or revision conflict", async () => {
  for (const conflict of [false,true]) {
    const h=harness({ideas:[idea("prepared")]}); await h.start();
    if (conflict) h.server.ideas[0].revision++; else h.fail("incubator/update");
    const accepted=await h.panel.useTarget({id:"01a10257-e1b3-7ce2-a0af-cf9df4ec2c09",kind:"codex",title:"Codex Console"});
    assert.equal(accepted,false); assert.doesNotMatch(h.root.textContent,/已关联选中的会话/);
    assert.match(h.root.textContent,conflict?/版本冲突/:/原保存请求已保留/);
    assert.equal(h.calls.filter(call=>call.path==="incubator/publish").length,0);
  }
});
function taskBridge() {
  const bridge = { context: null, opens: [], hosts: [], leaveReady: true, openReady: true, waiting: null, override: null };
  bridge.options = {
    async onTaskOpen(task) { bridge.opens.push(clone(task)); if (bridge.waiting) await bridge.waiting; if (!bridge.openReady) return false; bridge.context = { ...task, recordId: task.recordId || `record-${task.ideaId}`, ...bridge.override }; return true; },
    getTaskContext: () => bridge.context,
    onTaskMount: host => bridge.hosts.push(host),
    onTaskLeave() { if (!bridge.leaveReady) return false; bridge.context = null; return true; }
  };
  return bridge;
}
await test("a saved linked task delegates its exact server association and mounts without publishing", async () => {
  const bridge = taskBridge(), h = harness({ ideas: [idea("one", { workflowRecordId: "record-one" })], taskOptions: bridge.options }); await h.start();
  assert.equal(h.panel.hasOpenTask(), true); assert.deepEqual(bridge.opens, [{ ideaId: "one", recordId: "record-one", revision: 1, title: "想法 one", body: "保存、整理、随后才发布" }]); assert.equal(bridge.hosts.length, 1); assert.equal(bridge.hosts[0].hidden, false); assert.equal(h.calls.filter(call => call.payload).length, 0);
  const planning = h.all("details").find(value => value.className === "incubator-planning"); assert.notEqual(planning.open, true); assert.ok(h.button("反复完善任务稿")); assert.ok(h.button("发布到目标聊天")); assert.match(h.root.textContent, /Chat 讨论 · Work 在电脑 Workspace 工作 · Output 回到本任务/);
});
await test("tasks with identical titles select by exact IDs and busy workflow cannot switch the outer task", async () => {
  const bridge = taskBridge(), h = harness({ ideas: [idea("one", { title: "相同标题", workflowRecordId: "record-one" }), idea("two", { title: "相同标题", workflowRecordId: "record-two" })], taskOptions: bridge.options }); await h.start();
  bridge.leaveReady = false; assert.equal(h.panel.selectIdea("two"), false); assert.equal(h.cards().find(value => value.dataset.selected === "true").dataset.ideaId, "one"); assert.equal(bridge.opens.length, 1); assert.equal(h.panel.hasOpenTask(), true);
  bridge.leaveReady = true; assert.equal(h.panel.selectIdea("two"), true); await settle(); assert.equal(bridge.opens.at(-1).ideaId, "two"); assert.equal(bridge.opens.at(-1).recordId, "record-two"); assert.equal(h.cards().find(value => value.dataset.selected === "true").dataset.ideaId, "two"); assert.equal(h.calls.filter(call => call.payload).length, 0);
});
await test("opening a new task first saves its draft and delegates one associated record without a second idea", async () => {
  const bridge = taskBridge(), h = harness({ taskOptions: bridge.options }); await h.start(); h.new(); h.type("标题", "文字与图片底稿"); h.type("想法与任务内容", "先讨论，Work 再确认");
  assert.equal(bridge.opens.length, 0); assert.equal(await h.panel.openTask(true), true); assert.equal(h.server.ideas.length, 1); assert.equal(h.calls.filter(call => call.payload).length, 1); assert.equal(h.calls.find(call => call.payload).path, "incubator/create"); assert.equal(bridge.opens.length, 1); assert.equal(bridge.opens[0].ideaId, h.server.ideas[0].id); assert.equal(bridge.opens[0].body, "先讨论，Work 再确认"); assert.equal(h.panel.hasOpenTask(), true);
  assert.equal(await h.panel.openTask(false), true); assert.equal(bridge.opens.length, 1); assert.equal(h.calls.filter(call => call.path === "incubator/publish").length, 0);
});
await test("an unlinked saved task does not create a record merely from polling or selection", async () => {
  const bridge = taskBridge(), h = harness({ ideas: [idea("one")], taskOptions: bridge.options }); await h.start(); h.panel.selectIdea("one"); await h.poll(); assert.equal(bridge.opens.length, 0); assert.equal(h.panel.hasOpenTask(), false); assert.equal(h.calls.filter(call => call.payload).length, 0);
  assert.equal(await h.panel.openTask(true), true); assert.equal(bridge.opens.length, 1); assert.equal(h.calls.filter(call => call.payload).length, 0);
});
await test("failed or ambiguous task saves preserve the source draft and never open a workspace", async () => {
  const bridge = taskBridge(), h = harness({ taskOptions: bridge.options }); await h.start(); h.new(); h.type("标题", "保留待保存底稿"); h.type("想法与任务内容", "输入不会丢"); h.fail("incubator/create");
  assert.equal(await h.panel.openTask(true), false); assert.equal(bridge.opens.length, 0); assert.equal(h.field("想法与任务内容").value, "输入不会丢"); assert.equal(h.panel.hasDraft(), true); assert.match(h.root.textContent, /原保存请求已保留/);
});
await test("workspace rejection does not mount or claim that a linked record is ready", async () => {
  const bridge = taskBridge(); bridge.openReady = false; const h = harness({ ideas: [idea("one", { workflowRecordId: "record-one" })], taskOptions: bridge.options }); await h.start(); assert.equal(h.panel.hasOpenTask(), false); assert.equal(bridge.hosts.length, 0); assert.equal(h.field("标题").value, "想法 one"); assert.match(h.root.textContent, /结束录音|保存/); assert.equal(h.calls.filter(call => call.payload).length, 0);
});
await test("pending task load blocks new-task and selection changes without losing original source", async () => {
  const bridge = taskBridge(), waiting = defer(); bridge.waiting = waiting.promise; const h = harness({ ideas: [idea("one", { workflowRecordId: "record-one" }), idea("two")], taskOptions: bridge.options }); await h.start();
  assert.equal(h.panel.canReload(), false); assert.equal(h.panel.selectIdea("two"), false); h.new(); assert.equal(h.field("标题").value, "想法 one"); assert.equal(h.button("保存想法").disabled, true); waiting.resolve(); await settle(); assert.equal(h.panel.hasOpenTask(), true); assert.equal(h.panel.canReload(), true); assert.equal(h.server.ideas.length, 2);
});
await test("late task load cannot mount after leaving the foreground or clearing private content", async () => {
  for (const clear of [false, true]) { const bridge = taskBridge(), waiting = defer(); bridge.waiting = waiting.promise; const h = harness({ ideas: [idea("one", { body: "私有底稿", workflowRecordId: "record-one" })], taskOptions: bridge.options }); await h.start(); if (clear) h.panel.clear(); else h.panel.setActive(false); waiting.resolve(); await settle(); assert.equal(h.panel.hasOpenTask(), false); assert.equal(bridge.hosts.length, 0); if (clear) assert.doesNotMatch(h.root.textContent, /私有底稿/); }
});
await test("record or revision mismatch cannot mount a task or overwrite its source draft", async () => {
  for (const override of [{ recordId: "different-record" }, { ideaId: "different-idea" }, { revision: 9 }]) { const bridge = taskBridge(); bridge.override = override; const h = harness({ ideas: [idea("one", { workflowRecordId: "record-one" })], taskOptions: bridge.options }); await h.start(); assert.equal(h.panel.hasOpenTask(), false); assert.equal(bridge.hosts.length, 0); assert.equal(h.field("标题").value, "想法 one"); assert.match(h.root.textContent, /关联没有核验通过/); }
});
await test("saved source updates rebind the same task and same workspace host without publishing", async () => {
  const bridge = taskBridge(), h = harness({ ideas: [idea("one", { workflowRecordId: "record-one" })], taskOptions: bridge.options }); await h.start(); const host = bridge.hosts[0]; h.type("想法与任务内容", "新一轮底稿"); assert.equal(bridge.opens.length, 1); assert.match(h.root.textContent, /底稿修改尚未保存/); h.button("保存想法").click(); await settle();
  assert.equal(bridge.opens.length, 2); assert.equal(bridge.opens[1].recordId, "record-one"); assert.equal(bridge.opens[1].revision, 2); assert.equal(bridge.opens[1].body, "新一轮底稿"); assert.equal(bridge.hosts[1], host); assert.equal(h.server.ideas.length, 1); assert.equal(h.calls.filter(call => call.payload).length, 1); assert.equal(h.calls.find(call => call.payload).path, "incubator/update");
});
await test("offline task editing never invokes computer workflow callbacks or invents shared record links", async () => {
  const bridge = taskBridge(), h = harness({ offline: true, ideas: [idea("one", { workflowRecordId: "record-one" })], taskOptions: bridge.options }); await h.start(); assert.equal(await h.panel.openTask(true), false); assert.equal(bridge.opens.length, 0); assert.equal(h.panel.hasOpenTask(), false); assert.equal(h.all("section").find(value => value.className === "incubator-task-workspace").hidden, true); assert.match(h.root.textContent, /与电脑工作区不自动共享/);
});
await test("a saved newer source remains visibly unbound when workspace is busy and safely retries without resaving", async () => {
  const bridge = taskBridge(), h = harness({ ideas: [idea("one", { workflowRecordId: "record-one" })], taskOptions: bridge.options }); await h.start(); bridge.openReady = false; h.type("想法与任务内容", "新的已保存底稿"); h.button("保存想法").click(); await settle(); assert.equal(h.panel.hasOpenTask(), true); assert.equal(bridge.context.revision, 1); assert.match(h.root.textContent, /新版本已保存，工作区尚未载入/); assert.ok(h.button("保存并更新任务底稿")); const posts = h.calls.filter(call => call.payload).length;
  bridge.openReady = true; assert.equal(await h.panel.openTask(true), true); assert.equal(bridge.context.revision, 2); assert.equal(h.calls.filter(call => call.payload).length, posts); assert.equal(h.server.ideas.length, 1); assert.doesNotMatch(h.root.textContent, /工作区尚未载入/);
});
await test("computer source writeback refreshes the task body without reopening an already matching workspace", async () => {
  const bridge = taskBridge(), h = harness({ ideas: [idea("one", { workflowRecordId: "record-one" })], taskOptions: bridge.options }); await h.start(); Object.assign(h.server.ideas[0], { body: "电脑确认后的新底稿", revision: 2 }); Object.assign(bridge.context, { body: "电脑确认后的新底稿", revision: 2 }); await h.panel.refresh(); await settle();
  assert.equal(h.field("想法与任务内容").value, "电脑确认后的新底稿"); assert.equal(bridge.opens.length, 1); assert.equal(bridge.hosts.length, 1); assert.equal(h.panel.hasOpenTask(), true); assert.equal(h.calls.filter(call => call.payload).length, 0); assert.doesNotMatch(h.root.textContent, /工作区尚未载入/);
});
await test("computer source writeback retains a newer local edit and its original optimistic revision", async () => {
  const bridge = taskBridge(), h = harness({ ideas: [idea("one", { workflowRecordId: "record-one" })], taskOptions: bridge.options }); await h.start(); h.type("想法与任务内容", "我的未保存输入"); Object.assign(h.server.ideas[0], { body: "电脑确认后的新底稿", revision: 2 }); Object.assign(bridge.context, { body: "电脑确认后的新底稿", revision: 2 }); await h.panel.refresh(); await settle();
  assert.equal(h.field("想法与任务内容").value, "我的未保存输入"); assert.equal(bridge.opens.length, 1); assert.equal(h.panel.hasDraft(), true); assert.equal(h.calls.filter(call => call.payload).length, 0); h.button("保存想法").click(); await settle(); assert.equal(h.calls.find(call => call.path === "incubator/update").payload.expectedRevision, 1); assert.equal(h.field("想法与任务内容").value, "我的未保存输入"); assert.match(h.root.textContent, /版本冲突/); assert.equal(h.server.ideas[0].body, "电脑确认后的新底稿");
});
console.log(`PASS ${count} incubator UI checks`);
