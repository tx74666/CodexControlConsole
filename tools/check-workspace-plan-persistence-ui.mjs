#!/usr/bin/env node
// Isolated plan storage and HTTP fixtures: never opens a real browser profile.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const copy = value => JSON.parse(JSON.stringify(value));
const hash = index => String(index).padStart(64, "0");
const fixture = () => ({ version: 1, revision: "fixture-seed-v1", groups: [0, 1, 2, 3].map(index => ({
  id: `group-${index}`, title: `Plan ${index + 1}`, summary: "", items: Array.from({ length: index === 3 ? 6 : 5 }, (_, item) => ({ id: `item-${index}-${item}`, text: `Step ${index}-${item}`, done: false }))
})) });
const storageKeys = Object.fromEntries(["workspaceTodos", "workspaceTodoDraft", "workspacePlanCache", "workspacePlanRevision", "workspaceTodoBackup", "workspacePlanServerHash", "workspacePlanPending", "workspacePlanCacheOrigin"].map(key => [key, `fixture.${key}`]));
function extract(name) {
  const match = new RegExp(`(?:async )?function ${name}\\(`).exec(source); assert.ok(match, name);
  const start = match.index, end = source.slice(start + 1).search(/\n(?:async )?function /);
  return source.slice(start, end < 0 ? undefined : start + 1 + end);
}
function boot({ local = fixture(), saved = null, pending = null, generic = false, fresh = false } = {}) {
  const stored = new Map([[storageKeys.workspaceTodos, JSON.stringify(local.groups)], [storageKeys.workspaceTodoDraft, '{"text":"Keep this draft","category":"group-0"}']]);
  if (pending) stored.set(storageKeys.workspacePlanPending, JSON.stringify(pending));
  const gets = [], posts = [], timers = [];
  let server = saved ? copy(saved) : { persisted: false, plan: null, hash: null, error: "" };
  let nextHash = 10;
  const c = {
    storageKeys, hasWorkspace: true, workspaceTodoPersonalMode: !generic, activeWorkspacePlan: generic ? null : copy(fixture()), workspaceTodoGroups: copy(local.groups), workspaceTodoNoticeKey: "",
    workspacePlanSync: { ready: false, loading: false, hash: null, blocked: false, dirty: 0, saving: false, timer: 0, legacyCacheChecked: true, hadLocalTasks: !fresh },
    window: { setTimeout(action, delay) { timers.push({ action, delay }); return timers.length; } }, document: { hidden: false },
    localStorage: { getItem: key => stored.get(key) ?? null, setItem: (key, value) => stored.set(key, value), removeItem: key => stored.delete(key) },
    text: key => `Translated ${key}`, renderWorkspaceTodos() {},
    async requestJson(path) { gets.push(path); return copy(server); },
    async postJson(path, payload) {
      posts.push({ path, payload: copy(payload) });
      if (payload.expectedHash !== server.hash) throw Object.assign(new Error("Conflict"), { status: 409 });
      server = { persisted: true, actualDone: true, error: "", plan: copy(payload.plan), seed: generic ? null : fixture(), hash: hash(nextHash++), updatedAt: "2026-10-01T00:00:00Z" };
      return copy(server);
    }
  };
  const names = ["normalizeWorkspacePlan", "normalizeActualWorkspacePlan", "cloneWorkspacePlanGroups", "workspaceTodoGroupTitle", "workspaceTodoItemText", "saveWorkspaceTodos", "workspacePlanSnapshot", "workspacePlanPending", "markWorkspacePlanPending", "scheduleWorkspacePlanRetry", "persistWorkspacePlanSoon", "applySavedWorkspacePlan", "initializeWorkspacePlanPersistence", "persistWorkspacePlanNow", "loadSavedWorkspacePlan", "restoreWorkspaceStorage", "mergeWorkspacePlanGroups", "applyWorkspacePlan", "normalizePersonalWorkspaceTodos", "cloneDefaultWorkspaceTodos", "normalizeWorkspaceTodoItem", "normalizeWorkspaceTodoGroups", "loadWorkspaceTodos"];
  runInNewContext(names.map(extract).join("\n"), c);
  return { c, stored, gets, posts, timers, server: () => server, replaceServer(value) { server = copy(value); } };
}
function saved(plan, value = 1, seed = fixture()) { return { persisted: true, actualDone: true, plan, seed, hash: hash(value), updatedAt: "2026-10-01T00:00:00Z", error: "" }; }
let passed = 0;
async function test(name, action) { await action(); console.log(`PASS ${name}`); passed += 1; }
async function settled(c) { for (let i = 0; i < 12; i += 1) { await Promise.resolve(); if (!c.workspacePlanSync.saving && !c.workspacePlanSync.dirty) return; } }

await test("first migration preserves all 21 current details, completion, additions, and deletions", async () => {
  const local = fixture(); local.groups[0].items[0].done = true; local.groups[1].items.pop(); local.groups[2].items.push({ id: "custom", text: "An existing custom detail", done: true });
  const h = boot({ local }); await h.c.initializeWorkspacePlanPersistence();
  assert.equal(h.posts.length, 1); assert.deepEqual(h.posts[0].payload.plan, local); assert.equal(h.posts[0].payload.expectedHash, null);
  assert.equal(h.server().plan.groups.flatMap(group => group.items).length, 21);
  assert.equal(h.stored.get(storageKeys.workspacePlanPending), undefined);
});
await test("an untouched fresh browser cannot initialize the owner's saved plan before the old desktop profile", async () => {
  const h = boot({ fresh: true }); h.stored.delete(storageKeys.workspaceTodos); h.c.window.CODEX_WORKSPACE_PLAN = fixture(); h.c.workspacePlanSync.legacyCacheChecked = false;
  h.c.workspaceTodoGroups = h.c.loadWorkspaceTodos(); await h.c.initializeWorkspacePlanPersistence();
  assert.equal(h.posts.length, 0); assert.equal(h.server().persisted, false); assert.equal(h.c.workspacePlanSync.ready, true); assert.equal(h.stored.get(storageKeys.workspacePlanCacheOrigin), "seed");
  const reopened = boot({ fresh: true }); for (const [key, value] of h.stored) reopened.stored.set(key, value);
  reopened.c.window.CODEX_WORKSPACE_PLAN = fixture(); reopened.c.workspacePlanSync.legacyCacheChecked = false; reopened.c.workspaceTodoGroups = reopened.c.loadWorkspaceTodos();
  await reopened.c.initializeWorkspacePlanPersistence(); assert.equal(reopened.posts.length, 0); assert.equal(reopened.c.workspacePlanSync.hadLocalTasks, false);
  reopened.c.workspaceTodoGroups[0].items[0].done = true; reopened.c.saveWorkspaceTodos(); await settled(reopened.c);
  assert.equal(reopened.posts.length, 1); assert.equal(reopened.server().plan.groups[0].items[0].done, true); assert.equal(reopened.stored.get(storageKeys.workspacePlanCacheOrigin), "edited");
});
await test("edits made while the initial GET is pending are preserved and saved against the known server hash", async () => {
  const h = boot({ saved: saved(fixture()) }); h.stored.set(storageKeys.workspacePlanServerHash, hash(1));
  let release; h.c.requestJson = () => new Promise(resolve => { release = resolve; });
  const loading = h.c.initializeWorkspacePlanPersistence(); h.c.workspaceTodoGroups[0].items[0].done = true; h.c.saveWorkspaceTodos();
  release(saved(fixture())); await loading;
  assert.equal(h.posts.length, 1); assert.equal(h.posts[0].payload.expectedHash, hash(1)); assert.equal(h.server().plan.groups[0].items[0].done, true);
});
await test("existing server snapshot wins over an old unmodified browser cache and keeps a backup", async () => {
  const plan = fixture(); plan.groups[0].items[0].done = true; plan.groups[1].items = [];
  const h = boot({ saved: saved(plan) }), oldRaw = h.stored.get(storageKeys.workspaceTodos), draft = h.stored.get(storageKeys.workspaceTodoDraft);
  await h.c.initializeWorkspacePlanPersistence();
  assert.equal(h.posts.length, 0); assert.equal(h.c.workspaceTodoGroups[0].items[0].done, true); assert.equal(h.c.workspaceTodoGroups[1].items.length, 0);
  const backup = JSON.parse(h.stored.get(storageKeys.workspaceTodoBackup)); assert.equal(backup.revisions[0].todos, oldRaw); assert.equal(backup.revisions[0].draft, draft);
  assert.equal(h.stored.get(storageKeys.workspaceTodoDraft), draft);
});
await test("public installs without a private seed preserve six groups and resolve visible translated text", async () => {
  const local = fixture(); local.groups.push(...[5, 6].map(index => ({ id: `generic-${index}`, title: "", labelKey: `title-${index}`, items: [{ id: `generic-item-${index}`, text: "", textKey: `task-${index}`, done: true }] })));
  const h = boot({ local, generic: true }); await h.c.initializeWorkspacePlanPersistence();
  assert.equal(h.server().plan.groups.length, 6); assert.equal(h.server().plan.groups[5].title, "Translated title-6"); assert.equal(h.server().plan.groups[5].items[0].text, "Translated task-6");
  assert.equal(h.c.normalizeWorkspacePlan(h.server().plan), null); assert.ok(h.c.normalizeActualWorkspacePlan(h.server().plan));
});
await test("unsaved local progress retries against exactly its last confirmed server hash", async () => {
  const local = fixture(); local.groups[0].items[0].done = true;
  const h = boot({ local, saved: saved(fixture()), pending: { baseHash: hash(1), plan: local } });
  await h.c.initializeWorkspacePlanPersistence(); assert.equal(h.posts.length, 1); assert.equal(h.posts[0].payload.expectedHash, hash(1)); assert.equal(h.server().plan.groups[0].items[0].done, true);
});
await test("a stale pending browser cannot replace newer server edits", async () => {
  const local = fixture(); local.groups[0].items[0].done = true;
  const h = boot({ local, saved: saved(fixture(), 2), pending: { baseHash: hash(1), plan: local } }), oldRaw = h.stored.get(storageKeys.workspaceTodos);
  await h.c.initializeWorkspacePlanPersistence(); assert.equal(h.posts.length, 0); assert.equal(h.c.workspacePlanSync.blocked, true); assert.equal(h.c.workspaceTodoNoticeKey, "workspacePlanSyncConflict");
  assert.equal(h.stored.get(storageKeys.workspaceTodos), oldRaw); assert.ok(h.stored.has(storageKeys.workspacePlanPending));
});
await test("explicit conflict recovery backs up pending local edits before loading the server snapshot", async () => {
  const local = fixture(); local.groups[0].items[0].done = true;
  const h = boot({ local, saved: saved(fixture(), 2), pending: { baseHash: hash(1), plan: local } });
  await h.c.initializeWorkspacePlanPersistence(); const oldRaw = h.stored.get(storageKeys.workspaceTodos), button = { disabled: false };
  await h.c.loadSavedWorkspacePlan(button); assert.equal(h.posts.length, 0); assert.equal(h.c.workspacePlanSync.blocked, false); assert.equal(h.c.workspaceTodoGroups[0].items[0].done, false);
  assert.ok(JSON.parse(h.stored.get(storageKeys.workspaceTodoBackup)).revisions.some(item => item.todos === oldRaw)); assert.equal(h.stored.get(storageKeys.workspacePlanPending), undefined); assert.equal(button.disabled, false);
});
await test("a previously completed request with a lost response clears the pending marker without another write", async () => {
  const local = fixture(); local.groups[0].items[0].done = true;
  const h = boot({ local, saved: saved(local, 2), pending: { baseHash: hash(1), plan: local } });
  await h.c.initializeWorkspacePlanPersistence(); assert.equal(h.posts.length, 0); assert.equal(h.c.workspacePlanSync.blocked, false); assert.equal(h.stored.get(storageKeys.workspacePlanPending), undefined);
});
await test("network save failure preserves local changes and schedules a bounded retry", async () => {
  const h = boot({ saved: saved(fixture()) }); await h.c.initializeWorkspacePlanPersistence();
  h.c.postJson = async () => { throw new TypeError("Offline"); };
  h.c.workspaceTodoGroups[0].items[0].done = true; assert.equal(h.c.saveWorkspaceTodos(), true); await settled(h.c);
  assert.equal(JSON.parse(h.stored.get(storageKeys.workspaceTodos))[0].items[0].done, true); assert.ok(h.stored.has(storageKeys.workspacePlanPending));
  assert.equal(h.c.workspaceTodoNoticeKey, "workspacePlanSyncFailed"); assert.equal(h.timers[0].delay, 5000);
});
await test("rapid edits are serialized and the second write uses the first acknowledged hash", async () => {
  const h = boot({ saved: saved(fixture()) }); await h.c.initializeWorkspacePlanPersistence();
  const originalPost = h.c.postJson; let release; const gate = new Promise(resolve => { release = resolve; }); let inflight = 0, highest = 0;
  h.c.postJson = async (path, payload) => { inflight += 1; highest = Math.max(highest, inflight); if (!h.posts.length) await gate; const result = await originalPost(path, payload); inflight -= 1; return result; };
  h.c.workspaceTodoGroups[0].items[0].done = true; h.c.saveWorkspaceTodos(); await Promise.resolve();
  h.c.workspaceTodoGroups[1].items[0].done = true; h.c.saveWorkspaceTodos(); release(); await settled(h.c);
  assert.equal(highest, 1); assert.equal(h.posts.length, 2); assert.equal(h.posts[1].payload.expectedHash, hash(10));
  assert.equal(h.server().plan.groups[0].items[0].done, true); assert.equal(h.server().plan.groups[1].items[0].done, true); assert.equal(h.stored.get(storageKeys.workspacePlanPending), undefined);
});
await test("reset saves the passed next groups after the caller replaces the in-memory list", async () => {
  const h = boot({ saved: saved(fixture()) }); await h.c.initializeWorkspacePlanPersistence(); const next = copy(h.c.workspaceTodoGroups); next[0].items = [];
  assert.equal(h.c.saveWorkspaceTodos(next), true); h.c.workspaceTodoGroups = next; await settled(h.c); assert.equal(h.server().plan.groups[0].items.length, 0);
});
await test("a broken server snapshot never replaces the browser list with a seed", async () => {
  const h = boot(); h.replaceServer({ persisted: false, plan: null, error: "Broken stored JSON", hash: null }); const before = h.stored.get(storageKeys.workspaceTodos);
  await h.c.initializeWorkspacePlanPersistence(); assert.equal(h.posts.length, 0); assert.equal(h.stored.get(storageKeys.workspaceTodos), before); assert.equal(h.c.workspaceTodoNoticeKey, "workspacePlanSyncFailed");
});
console.log(`Workspace plan persistence UI: ${passed} isolated checks passed.`);
