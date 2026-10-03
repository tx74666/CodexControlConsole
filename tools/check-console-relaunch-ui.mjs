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
  desktopTransferPanel: { hasDraft() { return false; } },
  desktopWorkflowPanel: { hasDraft() { return false; } },
  desktopIncubatorPanel: { hasDraft() { return false; } },
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
context.refreshForNewConsoleVersion('99.0.0');
context.refreshForNewConsoleVersion('99.0.0');
assert.equal(reloads, 1, 'newer server must reload once');
assert.equal(JSON.parse(stored.get('draft')).text, 'new draft');
context.els.workspaceTodoInput.value = '';
context.saveWorkspaceTodoDraft();
assert(!stored.has('draft'), 'submitting/clearing draft must prevent its resurrection');
stored.set('draft', '{invalid');
context.restoreWorkspaceTodoDraft();
assert.equal(context.els.workspaceTodoInput.value, '');
console.log('PASS Console relaunch UI version and to-do draft preservation');
