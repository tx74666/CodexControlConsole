#!/usr/bin/env node
// Executes actual desktop Work navigation with isolated component adapters; no APIs or user data.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
const source = readFileSync(new URL("../app.js", import.meta.url), "utf8").replace(/\r\n?/g, "\n");
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
function extract(name) {
  const start = source.indexOf(`function ${name}(`); assert.ok(start >= 0, `Missing actual function ${name}`); const next = source.slice(start + 1).search(/\n(?:async )?function /); return source.slice(start, next < 0 ? undefined : start + 1 + next);
}
function harness(search = "", { remembered = "music", archived = [] } = {}) {
  const nodes = new Map(), panels = {}, stores = new Map(), created = [];
  const get = id => { if (!nodes.has(id)) nodes.set(id, { id, hidden: false, open: false, attributes: {}, listeners: new Map(), setAttribute(key, value) { this.attributes[key] = String(value); }, addEventListener(name, action) { this.listeners.set(name, action); } }); return nodes.get(id); };
  const tabs = ["ideas", "conversations", "workflow"].map(value => ({ dataset: { workView: value }, attributes: {}, listeners: new Map(), setAttribute(key, value) { this.attributes[key] = String(value); }, addEventListener(name, action) { this.listeners.set(name, action); } }));
  const context = { URLSearchParams, runtimeActivityReady: true, activeConsoleView: "work", activeModuleId: "workspace", document: { hidden: false, getElementById: get, querySelectorAll: selector => selector === "#consoleWorkView [data-work-view]" ? tabs : [] }, localStorage: { getItem: key => stores.get(key) || null, setItem: (key, value) => stores.set(key, value) }, window: { location: { search } }, desktopTransferPanel: null, desktopWorkflowPanel: null, desktopIncubatorPanel: null, desktopConversationsPanel: null, ensureEditionModuleLayout() {}, currentPageName: () => "index.html", allArchivedModuleIds: () => archived, deletedModuleIds: () => [], lastModuleId: () => remembered, moduleIdFromPage: () => "workspace", visibleModuleOrder: () => ["music", "workspace"] };
  context.isModuleForeground = name => !context.document.hidden && context.activeModuleId === name;
  for (const [name, globalName] of [["workflow", "CodexWorkflowPanel"], ["incubator", "CodexIncubatorPanel"], ["conversations", "CodexConversationsPanel"], ["transfer", "CodexTransferPanel"]]) context.window[globalName] = { create(root, options = {}) { created.push({ name, id: root.id }); const panel = { root, options, active: false, activity: [], targets: [], setActive(value) { this.active = Boolean(value); this.activity.push(this.active); }, async useTarget(value) { this.targets.push(value); return true; } }; panels[name] = panel; return panel; } };
  const requested = source.match(/^const requestedConsoleView = .+;$/m)?.[0], view = source.match(/^let activeWorkView = .+;$/m)?.[0]; assert.ok(requested && view, "Use actual URL initialization");
  runInNewContext(`${requested}\n${view}\n${extract("normalizeConsoleWorkView")}\n${extract("setConsoleWorkView")}\n${extract("syncConsoleTransferActivity")}\n${extract("bindConsoleTransfer")}\n${extract("initialModuleId")}`, context); context.bindConsoleTransfer();
  return { context, nodes, panels, created, get, tabs, stores, click(view) { tabs.find(tab => tab.dataset.workView === view).listeners.get("click")(); } };
}
let passed = 0;
async function test(name, action) { await action(); passed++; console.log(`PASS ${name}`); }
await test("desktop Work has one explicit picture dispatch entry and reuses one panel", () => {
  assert.deepEqual([...html.matchAll(/data-work-view="([^"]+)"/g)].map(match => match[1]), ["ideas", "conversations", "workflow"]); assert.match(html, /data-work-view="workflow"[^>]*>看图与派工/); assert.match(html, /id="desktopWorkflowDetails"[^>]*hidden/); assert.equal([...html.matchAll(/id="desktopWorkflowPanel"/g)].length, 1); assert.match(html, /<summary>执行清单<\/summary>/);
  const h = harness(); assert.deepEqual(h.created.filter(item => item.name === "workflow").map(item => item.id), ["desktopWorkflowPanel"]); assert.equal(h.panels.incubator.active, true); assert.equal(h.panels.workflow.active, false); assert.equal(h.get("desktopWorkflowDetails").hidden, true);
});
await test("selecting picture dispatch opens its real container and isolates activity", () => {
  const h = harness(); h.click("workflow"); assert.equal(h.get("desktopWorkflowDetails").hidden, false); assert.equal(h.get("desktopWorkflowDetails").open, true); assert.equal(h.get("desktopWorkIdeas").hidden, true); assert.equal(h.get("desktopConversationsPanel").hidden, true); assert.equal(h.panels.workflow.active, true); assert.equal(h.panels.incubator.active, false); assert.equal(h.panels.conversations.active, false); assert.equal(h.tabs.find(tab => tab.dataset.workView === "workflow").attributes["aria-pressed"], "true");
});
await test("switching ideas or conversations stops the picture dispatch panel", () => {
  const h = harness(); h.click("workflow"); h.click("conversations"); assert.equal(h.get("desktopWorkflowDetails").hidden, true); assert.equal(h.panels.workflow.active, false); assert.equal(h.panels.conversations.active, true); h.get("desktopWorkflowDetails").listeners.get("toggle")(); assert.equal(h.panels.workflow.active, false); h.click("ideas"); assert.equal(h.panels.incubator.active, true); assert.equal(h.panels.conversations.active, false); assert.equal(h.panels.workflow.active, false);
});
await test("closed workflow details never activate until opened in its selected view", () => {
  const h = harness(); h.click("workflow"); h.get("desktopWorkflowDetails").open = false; h.get("desktopWorkflowDetails").listeners.get("toggle")(); assert.equal(h.panels.workflow.active, false); h.get("desktopWorkflowDetails").open = true; h.get("desktopWorkflowDetails").listeners.get("toggle")(); assert.equal(h.panels.workflow.active, true);
});
await test("other Console views and modules cannot retain workflow foreground activity", () => {
  const h = harness(); h.click("workflow"); h.context.activeConsoleView = "transfer"; h.context.syncConsoleTransferActivity(); assert.equal(h.panels.workflow.active, false); assert.equal(h.panels.transfer.active, true); h.context.activeConsoleView = "work"; h.context.activeModuleId = "music"; h.context.syncConsoleTransferActivity(); assert.equal(h.panels.workflow.active, false); assert.equal(h.panels.transfer.active, false); h.context.activeModuleId = "workspace"; h.context.syncConsoleTransferActivity(); assert.equal(h.panels.workflow.active, true);
});
await test("hidden document or pending runtime readiness cannot activate workflow", () => {
  const h = harness(); h.click("workflow"); h.context.document.hidden = true; h.context.syncConsoleTransferActivity(); assert.equal(h.panels.workflow.active, false); h.context.document.hidden = false; h.context.runtimeActivityReady = false; h.context.syncConsoleTransferActivity(); assert.equal(h.panels.workflow.active, false); h.context.runtimeActivityReady = true; h.context.syncConsoleTransferActivity(); assert.equal(h.panels.workflow.active, true);
});
await test("explicit workflow URL opens Work even if the last module was music", () => {
  const h = harness("?consoleView=work&workView=workflow"); assert.equal(h.context.initialModuleId(), "workspace"); assert.equal(h.get("desktopWorkflowDetails").open, true); assert.equal(h.get("desktopWorkflowDetails").hidden, false); assert.equal(h.panels.workflow.active, true); assert.equal(h.stores.size, 0);
});
await test("ordinary navigation keeps prior module preferences and unknown views are safe", () => {
  const h = harness("?consoleView=work&workView=invalid"); assert.equal(h.context.initialModuleId(), "music"); assert.equal(h.panels.incubator.active, true); assert.equal(h.panels.workflow.active, false); assert.equal(h.get("desktopWorkflowDetails").hidden, true); const archived = harness("?consoleView=work&workView=workflow", { archived: ["workspace"] }); assert.equal(archived.context.initialModuleId(), "music");
});
await test("target selection returns to ideas and binds metadata without sending a message", async () => {
  const h = harness(); h.click("conversations"); const target = { id: "original-thread", kind: "codex", title: "原标题" }; await h.panels.conversations.options.onTarget(target); assert.equal(h.panels.incubator.active, true); assert.equal(h.panels.conversations.active, false); assert.equal(h.panels.workflow.active, false); assert.deepEqual(h.panels.incubator.targets, [target]); assert.equal(h.get("desktopWorkIdeas").hidden, false); assert.equal(h.stores.size, 0);
});
console.log(`${passed} desktop Work navigation checks passed`);
