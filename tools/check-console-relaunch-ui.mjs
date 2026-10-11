import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
const manifest = JSON.parse(readFileSync(new URL('../app-manifest.json', import.meta.url), 'utf8'));
function extract(name) {
  const start = source.indexOf(`function ${name}(`);
  assert(start >= 0, `missing ${name}`);
  const after = source.slice(start + 1).search(/\n(?:async )?function /);
  const end = after < 0 ? -1 : start + 1 + after;
  return source.slice(start, end < 0 ? undefined : end);
}
const buildVersion = source.match(/const consoleUiVersion = "([^"]+)";/)?.[1];
assert.equal(buildVersion, manifest.version, 'UI build identity must match the packaged release');
const stored = new Map();
let reloads = 0;
const context = {
  storageKeys: { workspaceTodoDraft: 'draft', workspaceTodos: 'existing-todos' },
  els: { workspaceTodoInput: { value: '' }, workspaceTodoCategory: { value: 'work' } },
  workspaceTodoGroups: [{ id: 'work' }, { id: 'home' }],
  workspaceTodoPersonalMode: false, activeWorkspacePlan: null,
  desktopCodexWorkPanel: null,
  desktopTransferPanel: { hasDraft() { return false; } },
  desktopWorkflowPanel: { hasDraft() { return false; } },
  desktopIncubatorPanel: { hasDraft() { return false; } },
  desktopConversationsPanel: { canReload() { return true; } },
  localStorage: { getItem: key => stored.get(key) ?? null, setItem: (key, value) => stored.set(key, value), removeItem: key => stored.delete(key) },
  window: { location: { reload() { reloads++; } } }
};
runInNewContext(`const consoleUiVersion = ${JSON.stringify(buildVersion)}; let consoleVersionReloadPending = false;
${extract('saveWorkspaceTodoDraft')}
${extract('restoreWorkspaceTodoDraft')}
${extract('refreshForNewConsoleVersion')}`, context);
runInNewContext(extract('hasReachedUpdateVersion'), context);
assert(context.hasReachedUpdateVersion('1.0.8', '1.0.8'));
assert(context.hasReachedUpdateVersion('1.0.10', '1.0.8'));
assert(!context.hasReachedUpdateVersion('1.0.7', '1.0.8'));
assert(!context.hasReachedUpdateVersion('bad', '1.0.8'));
stored.set('existing-todos', '[{"text":"keep existing"}]');
context.els.workspaceTodoInput.value = '  尚未提交的待办  ';
context.els.workspaceTodoCategory.value = 'home';
context.saveWorkspaceTodoDraft();
context.els.workspaceTodoInput.value = '';
context.els.workspaceTodoCategory.value = 'work';
context.restoreWorkspaceTodoDraft();
assert.equal(context.els.workspaceTodoInput.value, '  尚未提交的待办  ');
assert.equal(context.els.workspaceTodoCategory.value, 'home');
assert.equal(stored.get('existing-todos'), '[{"text":"keep existing"}]');
for (const version of [buildVersion, '0.9.9', 'bad', '999.bad']) context.refreshForNewConsoleVersion(version);
assert.equal(reloads, 0, 'same/older/invalid server must not reload a page');
context.els.workspaceTodoInput.value = 'new draft';
context.desktopTransferPanel.hasDraft = () => true;
context.refreshForNewConsoleVersion('99.0.0');
assert.equal(reloads, 0, 'a transfer draft or active upload must block automatic reload');
context.desktopTransferPanel.hasDraft = () => false;
context.desktopWorkflowPanel.hasDraft = () => true;
context.refreshForNewConsoleVersion('99.0.0');
assert.equal(reloads, 0, 'a workflow draft must block automatic reload');
context.desktopWorkflowPanel.hasDraft = () => false;
context.desktopIncubatorPanel.hasDraft = () => true;
context.refreshForNewConsoleVersion('99.0.0');
assert.equal(reloads, 0, 'an unsaved incubator idea must block automatic reload');
context.desktopIncubatorPanel.hasDraft = () => false;
context.desktopConversationsPanel.canReload = () => false;
context.refreshForNewConsoleVersion('99.0.0');
assert.equal(reloads, 0, 'a conversation read request awaiting acknowledgement must block automatic reload');
context.desktopConversationsPanel.canReload = () => true;
context.desktopCodexWorkPanel = { hasDraft() { return true; }, canReload() { return true; } };
context.refreshForNewConsoleVersion('99.0.0');
assert.equal(reloads, 0, 'a saved Work review or unconfirmed Agent request must block automatic reload');
assert.equal(context.els.workspaceTodoInput.value, 'new draft', 'blocked Work reload must preserve the current editor');
context.desktopCodexWorkPanel.hasDraft = () => false;
context.desktopCodexWorkPanel.canReload = () => false;
context.refreshForNewConsoleVersion('99.0.0');
assert.equal(reloads, 0, 'active Work, permission setup, or unsafe Work persistence must block automatic reload');
context.desktopCodexWorkPanel.canReload = () => true;
context.refreshForNewConsoleVersion('99.0.0');
context.refreshForNewConsoleVersion('99.0.0');
assert.equal(reloads, 1, 'an idle reload-safe Work panel permits one newer-server reload');
assert.equal(JSON.parse(stored.get('draft')).text, 'new draft');
context.els.workspaceTodoInput.value = '';
context.saveWorkspaceTodoDraft();
assert(!stored.has('draft'), 'submitting/clearing draft must prevent its resurrection');
stored.set('draft', '{invalid');
context.restoreWorkspaceTodoDraft();
assert.equal(context.els.workspaceTodoInput.value, '');
const initialViewExpression = source.match(/let activeConsoleView = ([^;]+);/)?.[1];
assert(initialViewExpression, 'missing Console initial view selection');
for (const [requested, saved, expected] of [
  [null, 'document', 'document'], [null, 'transfer', 'transfer'],
  [null, 'collaboration', 'collaboration'], [null, null, 'work'],
  ['work', 'document', 'work'], ['document', 'transfer', 'document'],
  ['invalid', 'document', 'work'], [null, 'invalid', 'work']
]) {
  const view = runInNewContext(`${extract('normalizeConsoleWorkspaceView')}\n${initialViewExpression}`, {
    requestedConsoleView: requested,
    storageKeys: { consoleView: 'console-view' },
    localStorage: { getItem(key) { assert.equal(key, 'console-view'); return saved; } }
  });
  assert.equal(view, expected, 'ordinary reopen must remember its Console section and explicit links must win');
}
const moduleHrefs = { wallpaper: 'index.html', music: 'music.html', workspace: 'workspace.html', blender: 'blender.html' };
for (const [page, saved, resume, archived, requestedView, workView, expected] of [
  ['music.html', 'workspace', null, [], null, 'workflow', 'music'],
  ['workspace.html', 'music', null, [], null, 'workflow', 'workspace'],
  ['index.html', 'music', 'wallpaper', [], null, 'workflow', 'wallpaper'],
  ['index.html', 'music', null, [], null, 'workflow', 'music'],
  ['index.html', 'music', 'invalid', [], null, 'workflow', 'music'],
  ['music.html', 'workspace', 'workspace', [], null, 'workflow', 'music'],
  ['index.html', 'music', 'wallpaper', ['wallpaper'], null, 'workflow', 'music'],
  ['index.html', 'music', 'wallpaper', [], 'work', 'agents', 'workspace'],
  ['blender.html', 'music', 'music', [], null, 'workflow', 'blender']
]) {
  const selected = runInNewContext(`${extract('initialModuleId')}\ninitialModuleId()`, {
    requestedConsoleView: requestedView, requestedResumeModule: resume, activeWorkView: workView,
    ensureEditionModuleLayout() {}, currentPageName() { return page; },
    allArchivedModuleIds() { return archived; }, deletedModuleIds() { return []; },
    isModuleId(id) { return Object.hasOwn(moduleHrefs, id); },
    moduleById(id) { return { href: moduleHrefs[id] }; }, lastModuleId() { return saved; },
    moduleIdFromPage(name) { return Object.keys(moduleHrefs).find(id => moduleHrefs[id] === name); },
    visibleModuleOrder() { return Object.keys(moduleHrefs).filter(id => !archived.includes(id)); }
  });
  assert.equal(selected, expected, 'saved launch hint must resolve stale index storage without overriding explicit pages or Work links');
}
const nextUrl = runInNewContext(`${extract('moduleUrl')}\nmoduleUrl('music.html')`, {
  URLSearchParams, consoleEdition: 'public',
  window: { location: { search: '?edition=public&resumeModule=wallpaper&consoleView=document', hash: '' } }
});
assert.equal(nextUrl, 'music.html?edition=public&consoleView=document', 'one-shot launch hint must not leak into later module navigation');
console.log('PASS Console relaunch UI version, remembered module/section, explicit entry, Work reload gates and to-do draft preservation');
