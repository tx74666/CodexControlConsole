#!/usr/bin/env node
// Fake localStorage only: no browser profiles, real tasks, or network access.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const storageKeys = Object.fromEntries(["workspaceTodos", "workspaceTodoDraft", "workspacePlanCache", "workspacePlanRevision", "workspaceTodoBackup"].map(key => [key, `fixture.${key}`]));
const plan = revision => ({ version: 1, revision, groups: [1, 2, 3, 4].map(index => ({ id: `focus-${index}`, title: `Focus ${index}`, summary: `Goal ${index}`, items: [{ id: `item-${index}`, text: `Step ${index}`, done: false }] })) });
const copy = value => JSON.parse(JSON.stringify(value));
function extract(name) {
  const start = source.indexOf(`function ${name}(`); assert.ok(start >= 0, name);
  const end = source.slice(start + 1).search(/\n(?:async )?function /);
  return source.slice(start, end < 0 ? undefined : start + 1 + end);
}
function boot(incoming = null, stored = new Map(), fail = () => false, serverError = "") {
  const writes = [];
  const context = {
    storageKeys, window: { CODEX_WORKSPACE_PLAN: incoming, CODEX_WORKSPACE_PLAN_ERROR: serverError },
    activeWorkspacePlan: null, workspaceTodoPersonalMode: false, workspaceTodoNoticeKey: "",
    defaultWorkspaceTodoGroups: [1, 2, 3, 4, 5, 6].map(index => ({ id: `generic-${index}`, title: `Generic ${index}`, items: [{ id: `generic-item-${index}`, text: `Generic step ${index}`, done: false }] })),
    localStorage: { getItem: key => stored.get(key) ?? null, setItem(key, value) { if (fail(key, "set", value)) throw new Error("Storage unavailable"); writes.push({ key, value }); stored.set(key, value); }, removeItem(key) { if (fail(key, "remove")) throw new Error("Storage unavailable"); writes.push({ key, remove: true }); stored.delete(key); } },
    els: { workspaceTodoInput: { value: "" }, workspaceTodoCategory: { value: "focus-1" } }, renderWorkspaceTodos() {},
    createWorkspaceTodoId: () => "new-item",
  };
  const names = ["normalizeConsoleWorkspaceView", "normalizeWorkspacePlan", "cloneWorkspacePlanGroups", "restoreWorkspaceStorage", "mergeWorkspacePlanGroups", "applyWorkspacePlan", "normalizePersonalWorkspaceTodos", "cloneDefaultWorkspaceTodos", "normalizeWorkspaceTodoItem", "normalizeWorkspaceTodoGroups", "loadWorkspaceTodos", "resetWorkspaceTodoGroups", "saveWorkspaceTodos", "pruneEmptyWorkspaceTodoGroups", "addWorkspaceTodo", "toggleWorkspaceTodo", "deleteWorkspaceTodo", "saveWorkspaceTodoDraft", "restoreWorkspaceTodoDraft"];
  runInNewContext(names.map(extract).join("\n"), context);
  context.workspaceTodoGroups = context.loadWorkspaceTodos();
  return { context, stored, writes };
}
const saved = (h, key) => h.stored.get(storageKeys[key]);
let passed = 0;
function test(name, action) { action(); console.log(`PASS ${name}`); passed += 1; }

test("Work is the default, explicit tool and document links remain, and tasks share Work", () => {
  const h = boot();
  for (const value of [null, undefined, "", "wrong", "work"]) assert.equal(h.context.normalizeConsoleWorkspaceView(value), "work");
  assert.equal(h.context.normalizeConsoleWorkspaceView("common"), "common");
  assert.equal(h.context.normalizeConsoleWorkspaceView("document"), "document"); assert.equal(h.context.normalizeConsoleWorkspaceView("collaboration"), "collaboration");
  assert.ok(html.indexOf('id="consoleWorkTab"') < html.indexOf('id="consoleDocumentTab"'));
  assert.ok(html.indexOf('class="candidate-strip workspace-todos"') < html.indexOf('class="panel desktop-layout-panel'));
  assert.doesNotMatch(html.match(/<section id="consoleWorkView"[^>]*>/)[0], /\bhidden\b/);
  assert.match(html, /id="consoleCommonView"[^>]+hidden/);
  assert.ok(html.indexOf('id="consoleWorkView"') < html.indexOf('class="candidate-strip workspace-todos"'));
  assert.ok(html.indexOf('class="candidate-strip workspace-todos"') < html.indexOf('id="consoleTransferView"'));
  assert.match(html, /id="consoleDocumentView"[^>]+hidden/);
  for (const name of ["index.html", "workspace.html", "music.html"]) {
    const entry = readFileSync(new URL(`../${name}`, import.meta.url), "utf8");
    assert.ok(entry.indexOf('src="/api/workspace-plan.js"') >= 0 && entry.indexOf('src="/api/workspace-plan.js"') < entry.indexOf('src="app.js?'));
  }
});

test("new revision backs up exact old list and draft before replacing and committing", () => {
  const raw = '[ {"id":"old", "title":"Old custom", "items":[{"id":"a","text":"Keep in backup","done":true}]} ]';
  const draft = '{"text":"Old unfinished task","category":"old"}';
  const h = boot(plan("r1"), new Map([[storageKeys.workspaceTodos, raw], [storageKeys.workspaceTodoDraft, draft]]));
  assert.deepEqual(copy(h.context.workspaceTodoGroups).map(group => group.id), ["focus-1", "focus-2", "focus-3", "focus-4"]);
  assert.equal(h.context.workspaceTodoGroups[0].summary, "Goal 1");
  const backup = JSON.parse(saved(h, "workspaceTodoBackup")); assert.equal(backup.revisions[0].todos, raw); assert.equal(backup.revisions[0].draft, draft);
  assert.equal(saved(h, "workspaceTodoDraft"), undefined); assert.equal(saved(h, "workspacePlanRevision"), "r1");
  const keys = h.writes.map(write => write.key); assert.ok(keys.indexOf(storageKeys.workspaceTodoBackup) < keys.indexOf(storageKeys.workspaceTodos)); assert.ok(keys.indexOf(storageKeys.workspaceTodos) < keys.indexOf(storageKeys.workspacePlanRevision));
});

test("same revision, upgrades and offline cache preserve edits and all four empty categories", () => {
  const h = boot(plan("r1")); const c = h.context;
  c.toggleWorkspaceTodo("focus-1", "item-1", true); c.deleteWorkspaceTodo("focus-2", "item-2");
  c.els.workspaceTodoInput.value = "User added detail"; c.els.workspaceTodoCategory.value = "focus-3"; c.addWorkspaceTodo();
  c.els.workspaceTodoInput.value = "New plan draft"; c.saveWorkspaceTodoDraft();
  const after = saved(h, "workspaceTodos"), backup = saved(h, "workspaceTodoBackup");
  for (const incoming of [plan("r1"), null, undefined, { broken: true }]) {
    const next = boot(incoming, h.stored); assert.equal(saved(next, "workspaceTodos"), after); assert.equal(saved(next, "workspaceTodoBackup"), backup); assert.equal(next.context.workspaceTodoGroups.length, 4);
    assert.equal(next.context.workspaceTodoGroups[0].items[0].done, true); assert.equal(next.context.workspaceTodoGroups[1].items.length, 0); assert.equal(next.context.workspaceTodoGroups[2].items.at(-1).text, "User added detail");
    next.context.restoreWorkspaceTodoDraft(); assert.equal(next.context.els.workspaceTodoInput.value, "New plan draft");
    assert.equal(next.writes.length, 0, "relaunch must not rewrite a migrated plan");
  }
  for (const group of c.workspaceTodoGroups) group.items = [];
  assert.equal(c.pruneEmptyWorkspaceTodoGroups(), false); c.saveWorkspaceTodos(); assert.equal(boot(null, h.stored).context.workspaceTodoGroups.length, 4);
});

test("reset restores the local four-category plan and a new revision gets one fresh backup", () => {
  const h = boot(plan("r1")); h.context.deleteWorkspaceTodo("focus-1", "item-1"); h.context.resetWorkspaceTodoGroups(); assert.equal(h.context.workspaceTodoGroups[0].items.length, 1); assert.equal(h.context.workspaceTodoGroups.length, 4);
  const before = saved(h, "workspaceTodos"), nextPlan = plan("r2"); nextPlan.groups[0].items = [];
  const next = boot(nextPlan, h.stored); assert.equal(next.context.workspaceTodoGroups[0].items.length, 0); const backups = JSON.parse(saved(next, "workspaceTodoBackup")).revisions;
  assert.equal(backups.length, 2); assert.equal(backups[1].todos, before); boot(nextPlan, h.stored); assert.equal(JSON.parse(saved(next, "workspaceTodoBackup")).revisions.length, 2);
});

test("invalid plans cannot overwrite stored tasks or introduce an applied revision", () => {
  for (const mutate of [value => { value.version = 2; }, value => { value.groups.pop(); }, value => { value.groups[1].id = value.groups[0].id; }, value => { value.groups[0].items[0].done = "false"; }, value => { value.groups[0].items.push({ ...value.groups[0].items[0] }); }, value => { value.groups[0].summary = null; }]) {
    const bad = plan("bad"); mutate(bad); const raw = JSON.stringify([{ id: "custom", title: "User data", items: [{ id: "x", text: "Untouched", done: true }] }]);
    const h = boot(bad, new Map([[storageKeys.workspaceTodos, raw]])); assert.equal(saved(h, "workspaceTodos"), raw); assert.equal(saved(h, "workspacePlanRevision"), undefined); assert.equal(h.writes.length, 0);
  }
});

test("storage failures do not commit a revision or replace the original list", () => {
  for (const failedKey of ["workspaceTodoBackup", "workspaceTodos", "workspacePlanCache", "workspaceTodoDraft", "workspacePlanRevision"]) {
    const initial = boot(); initial.context.saveWorkspaceTodos(); const raw = saved(initial, "workspaceTodos");
    const h = boot(plan("r1"), initial.stored, key => key === storageKeys[failedKey]);
    assert.equal(saved(h, "workspaceTodos"), raw, failedKey); assert.equal(saved(h, "workspacePlanRevision"), undefined); assert.equal(h.context.activeWorkspacePlan, null); assert.equal(h.context.workspaceTodoNoticeKey, "workspacePlanLoadFailed");
  }
});

test("backend null plus malformed JSON or permission errors retains cached tasks and warns", () => {
  for (const reason of ["Invalid JSON in workspace-plan.json", "Permission denied reading workspace-plan.json"]) {
    const initial = boot(plan("r1")); initial.context.deleteWorkspaceTodo("focus-1", "item-1");
    const raw = saved(initial, "workspaceTodos"), cache = saved(initial, "workspacePlanCache");
    const h = boot(null, initial.stored, () => false, reason);
    assert.equal(h.context.workspaceTodoNoticeKey, "workspacePlanLoadFailed"); assert.equal(h.context.activeWorkspacePlan.revision, "r1");
    assert.equal(h.context.workspaceTodoGroups.length, 4); assert.equal(h.context.workspaceTodoGroups[0].items.length, 0);
    assert.equal(saved(h, "workspaceTodos"), raw); assert.equal(saved(h, "workspacePlanCache"), cache); assert.equal(h.writes.length, 0);
  }
  const generic = boot(); generic.context.saveWorkspaceTodos(); const raw = saved(generic, "workspaceTodos");
  const h = boot(null, generic.stored, () => false, "Permission denied");
  assert.equal(saved(h, "workspaceTodos"), raw); assert.equal(h.context.workspaceTodoNoticeKey, "workspacePlanLoadFailed"); assert.equal(h.writes.length, 0);
});

test("item identifiers are unique across all four groups", () => {
  const bad = plan("duplicate"); bad.groups[1].items[0].id = bad.groups[0].items[0].id;
  const h = boot(bad); assert.equal(h.context.activeWorkspacePlan, null); assert.equal(saved(h, "workspacePlanRevision"), undefined); assert.equal(h.writes.length, 0);
});

test("failed updates preserve an already migrated plan and its cache", () => {
  const initial = boot(plan("r1")); initial.context.deleteWorkspaceTodo("focus-1", "item-1"); const raw = saved(initial, "workspaceTodos");
  const h = boot(plan("r2"), initial.stored, (key, operation, value) => key === storageKeys.workspacePlanRevision && operation === "set" && value === "r2");
  assert.equal(saved(h, "workspacePlanRevision"), "r1"); assert.equal(saved(h, "workspaceTodos"), raw); assert.equal(h.context.activeWorkspacePlan.revision, "r1"); assert.equal(h.context.workspaceTodoGroups[0].items.length, 0);
});

test("retrying an uncommitted revision backs up the latest edits and draft", () => {
  const initial = boot(plan("r1"));
  const failed = boot(plan("r2"), initial.stored, (key, operation, value) => key === storageKeys.workspacePlanRevision && operation === "set" && value === "r2");
  assert.equal(saved(failed, "workspacePlanRevision"), "r1");
  const editing = boot(plan("r1"), failed.stored);
  editing.context.deleteWorkspaceTodo("focus-1", "item-1");
  editing.context.toggleWorkspaceTodo("focus-2", "item-2", true);
  editing.context.els.workspaceTodoInput.value = "Draft written after the failed upgrade"; editing.context.saveWorkspaceTodoDraft();
  const latestRaw = saved(editing, "workspaceTodos"), latestDraft = saved(editing, "workspaceTodoDraft");
  const retried = boot(plan("r2"), editing.stored);
  assert.equal(saved(retried, "workspacePlanRevision"), "r2");
  const backups = JSON.parse(saved(retried, "workspaceTodoBackup")).revisions;
  assert.equal(backups.length, 2); assert.equal(backups.find(item => item.revision === "r2").todos, latestRaw); assert.equal(backups.find(item => item.revision === "r2").draft, latestDraft);
  assert.deepEqual(JSON.parse(saved(retried, "workspaceTodoDraft")), { text: "Draft written after the failed upgrade", category: "focus-1", planRevision: "r2" });
  assert.equal(retried.context.workspaceTodoGroups[0].items.length, 0);
  assert.equal(retried.context.workspaceTodoGroups[1].items[0].done, true);
});

test("offline missing cache preserves saved groups and cannot reset into six generic groups", () => {
  const h = boot(plan("r1")); h.context.deleteWorkspaceTodo("focus-1", "item-1"); h.stored.delete(storageKeys.workspacePlanCache);
  const next = boot(null, h.stored); assert.equal(next.context.workspaceTodoGroups.length, 4); assert.equal(next.context.workspaceTodoGroups[0].items.length, 0); const raw = saved(next, "workspaceTodos"); next.context.resetWorkspaceTodoGroups(); assert.equal(saved(next, "workspaceTodos"), raw);
});

test("generic installations keep generic defaults and failed task writes revert local changes", () => {
  assert.equal(boot().context.workspaceTodoGroups.length, 6);
  const initial = boot(plan("r1")); const h = boot(null, initial.stored, key => key === storageKeys.workspaceTodos); const c = h.context;
  c.toggleWorkspaceTodo("focus-1", "item-1", true); assert.equal(c.workspaceTodoGroups[0].items[0].done, false);
  c.deleteWorkspaceTodo("focus-1", "item-1"); assert.equal(c.workspaceTodoGroups[0].items.length, 1);
  c.els.workspaceTodoInput.value = "Unsaved new task"; c.addWorkspaceTodo(); assert.equal(c.workspaceTodoGroups[0].items.length, 1); assert.equal(c.els.workspaceTodoInput.value, "Unsaved new task");
});

test("a failed initial draft removal rolls back instead of committing a partial plan", () => {
  const draft = '{"text":"Old task","category":"focus-1"}';
  const h = boot(plan("r1"), new Map([[storageKeys.workspaceTodoDraft, draft]]), (key, operation) => key === storageKeys.workspaceTodoDraft && operation === "remove");
  assert.equal(saved(h, "workspacePlanRevision"), undefined);
  assert.equal(saved(h, "workspaceTodos"), undefined);
  assert.equal(saved(h, "workspaceTodoDraft"), draft);
  assert.equal(h.context.workspaceTodoNoticeKey, "workspacePlanLoadFailed");
});

test("character-only revisions preserve deleted completed tasks and unrelated progress, custom tasks and order", () => {
  const old = plan("r1");
  old.groups[1].items = [
    { id: "character-tuning", text: "Completed tuning", done: true },
    { id: "character-forearm", text: "Completed correction", done: true },
    { id: "character-play", text: "Check Play", done: false },
    { id: "character-animation", text: "Check animation", done: false },
    { id: "character-retired", text: "Overlapping work", done: false }
  ];
  const h = boot(old), c = h.context;
  c.deleteWorkspaceTodo("focus-2", "character-tuning"); c.deleteWorkspaceTodo("focus-2", "character-forearm");
  c.toggleWorkspaceTodo("focus-2", "character-play", true);
  c.toggleWorkspaceTodo("focus-1", "item-1", true); c.deleteWorkspaceTodo("focus-3", "item-3");
  c.workspaceTodoGroups[0].items.unshift({ id: "custom-gallery", text: "My gallery detail", textKey: "", done: true });
  c.workspaceTodoGroups[1].items.unshift({ id: "custom-character", text: "My character detail", textKey: "", done: false });
  c.workspaceTodoGroups.reverse(); c.saveWorkspaceTodos();
  c.els.workspaceTodoCategory.value = "focus-2"; c.els.workspaceTodoInput.value = "Unfinished character detail"; c.saveWorkspaceTodoDraft();
  const before = copy(c.workspaceTodoGroups), incoming = copy(old); incoming.revision = "r2";
  incoming.groups[1].summary = "Actions first, three workstreams next";
  incoming.groups[1].items = incoming.groups[1].items.filter(item => item.id !== "character-retired");
  incoming.groups[1].items.find(item => item.id === "character-play").text = "Check the full interaction pipeline";
  incoming.groups[1].items.push({ id: "character-actions", text: "Unlock jump and double jump", done: false });
  const next = boot(incoming, h.stored), groups = copy(next.context.workspaceTodoGroups);
  assert.deepEqual(groups.map(group => group.id), before.map(group => group.id));
  for (const group of before.filter(group => group.id !== "focus-2")) assert.deepEqual(groups.find(item => item.id === group.id), group);
  const character = groups.find(group => group.id === "focus-2");
  assert.deepEqual(character.items.map(item => item.id), ["custom-character", "character-play", "character-animation", "character-actions"]);
  assert.equal(character.items[1].done, true); assert.equal(character.items[1].text, "Check the full interaction pipeline");
  assert.equal(character.summary, "Actions first, three workstreams next");
  next.context.restoreWorkspaceTodoDraft(); assert.equal(next.context.els.workspaceTodoInput.value, "Unfinished character detail");
  assert.equal(JSON.parse(saved(next, "workspaceTodoDraft")).planRevision, "r2");
  const raw = saved(next, "workspaceTodos"), again = boot(incoming, next.stored);
  assert.equal(saved(again, "workspaceTodos"), raw); assert.deepEqual(copy(again.context.workspaceTodoGroups), groups); assert.equal(again.writes.length, 0);
  assert.equal(JSON.parse(saved(again, "workspaceTodoBackup")).revisions.length, 2);
});

test("changed text does not resurrect a deleted seeded task or reset checked flags", () => {
  const initial = boot(plan("r1")); initial.context.deleteWorkspaceTodo("focus-1", "item-1");
  initial.context.toggleWorkspaceTodo("focus-2", "item-2", true);
  const incoming = plan("r2"); incoming.groups[0].items[0].text = "Reworded deleted task";
  incoming.groups[1].items[0].text = "Reworded checked task";
  const next = boot(incoming, initial.stored);
  assert.equal(next.context.workspaceTodoGroups[0].items.length, 0);
  assert.equal(next.context.workspaceTodoGroups[1].items[0].done, true);
  assert.equal(next.context.workspaceTodoGroups[1].items[0].text, "Reworded checked task");
});

test("missing or damaged migration inputs never replace saved tasks or commit a revision", () => {
  for (const damage of [
    h => h.stored.delete(storageKeys.workspacePlanCache),
    h => h.stored.set(storageKeys.workspacePlanCache, "{bad"),
    h => h.stored.set(storageKeys.workspacePlanCache, JSON.stringify(plan("different"))),
    h => h.stored.delete(storageKeys.workspaceTodos),
    h => h.stored.set(storageKeys.workspaceTodos, "{bad"),
    h => h.stored.set(storageKeys.workspaceTodos, "[]"),
    h => { const groups = JSON.parse(saved(h, "workspaceTodos")); groups[0].items[0].done = "false"; h.stored.set(storageKeys.workspaceTodos, JSON.stringify(groups)); },
    h => { const groups = JSON.parse(saved(h, "workspaceTodos")); groups[0].items.push({ ...groups[0].items[0] }); h.stored.set(storageKeys.workspaceTodos, JSON.stringify(groups)); }
  ]) {
    const initial = boot(plan("r1")); damage(initial); const before = new Map(initial.stored);
    const next = boot(plan("r2"), initial.stored);
    assert.deepEqual([...next.stored], [...before]); assert.equal(next.writes.length, 0);
    assert.equal(saved(next, "workspacePlanRevision"), "r1");
  }
});

test("category replacement, cross-category moves and new-ID collisions fail safely", () => {
  for (const change of [
    incoming => { incoming.groups[0].id = "replacement"; },
    incoming => { incoming.groups[1].items.push(incoming.groups[0].items.pop()); },
    incoming => { incoming.groups[0].items.push({ id: "custom-task", text: "Conflicting seed", done: false }); }
  ]) {
    const initial = boot(plan("r1"));
    initial.context.workspaceTodoGroups[0].items.push({ id: "custom-task", text: "Keep custom", done: true }); initial.context.saveWorkspaceTodos();
    const before = new Map(initial.stored), incoming = plan("r2"); change(incoming);
    const next = boot(incoming, initial.stored); assert.deepEqual([...next.stored], [...before]); assert.equal(next.writes.length, 0);
  }
});

test("every failed merge write rolls back current list, cached seed, revision and draft", () => {
  for (const failedKey of ["workspaceTodoBackup", "workspaceTodos", "workspacePlanCache", "workspaceTodoDraft", "workspacePlanRevision"]) {
    const initial = boot(plan("r1")); initial.context.toggleWorkspaceTodo("focus-1", "item-1", true);
    initial.context.deleteWorkspaceTodo("focus-2", "item-2");
    initial.context.els.workspaceTodoInput.value = "Keep this draft"; initial.context.saveWorkspaceTodoDraft();
    const before = new Map(initial.stored), incoming = plan("r2"); incoming.groups[1].items.push({ id: "new-action", text: "New action", done: false });
    const next = boot(incoming, initial.stored, (key, operation) => key === storageKeys[failedKey] && operation === "set");
    for (const key of ["workspaceTodos", "workspacePlanCache", "workspacePlanRevision", "workspaceTodoDraft"]) assert.equal(saved(next, key), before.get(storageKeys[key]), `${failedKey}: ${key}`);
    assert.equal(next.context.workspaceTodoGroups[0].items[0].done, true); assert.equal(next.context.workspaceTodoGroups[1].items.length, 0);
    assert.equal(next.context.workspaceTodoNoticeKey, "workspacePlanLoadFailed");
  }
});

console.log(`Workspace plan UI: ${passed} isolated checks passed.`);
