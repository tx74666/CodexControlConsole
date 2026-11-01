import fs from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import crypto from 'node:crypto';
const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source = fs.readFileSync(resolve(projectRoot, 'image-manager.js'), 'utf8');
const html = fs.readFileSync(resolve(projectRoot, 'image-manager.html'), 'utf8');
class Element {
  constructor(tag, doc) { this.tagName = tag; this.doc = doc; this.children = []; this.dataset = {}; this.attributes = {}; this.events = {}; this.value = ''; this.className = ''; this._classes = new Set(); this.classList = { add: (...v) => v.forEach(x => this._classes.add(x)), remove: (...v) => v.forEach(x => this._classes.delete(x)) }; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(k, v) { this.attributes[k] = v; }
  addEventListener(name, listener) { (this.events[name] ||= []).push(listener); }
  querySelectorAll(selector) {
    const items = this.children.flatMap(child => [child, ...(child.querySelectorAll?.('*') || [])]);
    return selector === '*' ? items : items.filter(child => selector === 'option[value="notion"]' ? child.tagName === 'option' && child.value === 'notion' : child.tagName === selector);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  focus() { this.doc.activeElement = this; }
  showModal() { this.open = true; }
  close() { this.open = false; return this.emit('close'); }
  scrollIntoView() {}
  contains(other) { return this === other || this.querySelectorAll('*').includes(other); }
  async emit(name, extra = {}) { for (const callback of this.events[name] || []) await callback({ target: this, preventDefault() {}, ...extra }); }
  click() { return this.emit('click'); }
}
const flush = async () => { for (let i = 0; i < 7; i++) await new Promise(resolve => setImmediate(resolve)); };
const originalRoot = 'D:\\Fixture Images';
const image = { path: 'sample 64x64.png', title: '<img src=x onerror=alert(1)>', width: 64, height: 64, sha256: 'a'.repeat(64), space: 'root' };
const candidate = { id: 'candidate1', status: 'conflict', incoming: { ...image, path: 'inbox/sample.png' }, existing: { ...image, space: 'device', sha256: 'b'.repeat(64) }, actions: ['replace', 'keep', 'add'] };
const review = { id: 'plan1', planId: 'plan1', candidates: [candidate], errors: [] };
const initialState = { root: originalRoot, deviceRoot: '', notionPage: '', items: [image], inboxCount: 1, plan: review };
function makeStorage(existing = new Map()) { return { getItem: key => existing.get(key) || null, setItem: (key, value) => existing.set(key, value), removeItem: key => existing.delete(key), existing }; }
function boot(initial, storage = makeStorage(), embedOptions = null) {
  const elements = {};
  const doc = { getElementById: id => elements[id], createElement: tag => new Element(tag, doc), documentElement: { dataset: {} }, addEventListener() {}, activeElement: null };
  for (const id of html.matchAll(/id="([^"]+)"/g)) { const element = new Element('div', doc); element.id = id[1]; elements[id[1]] = element; }
  for (const id of ['syncSource', 'syncTarget']) { const option = new Element('option', doc); option.value = 'notion'; elements[id].append(option); }
  elements.syncSource.value = 'local'; elements.syncTarget.value = 'console';
  elements.emptyState.append(new Element('h3', doc), new Element('p', doc));
  let current = structuredClone(initial);
  const requests = [];
  const replies = new Map();
  class FormData { constructor() { this.fields = []; } append(...field) { this.fields.push(field); } }
  const context = { document: doc, sessionStorage: storage, localStorage: makeStorage(), URLSearchParams, FormData, crypto: crypto, setTimeout: callback => setImmediate(callback), console, fetch: async (url, options) => {
    const action = url.split('/').at(-1).split('?')[0];
    requests.push({ action, options, body: typeof options.body === 'string' ? JSON.parse(options.body) : options.body });
    const reply = replies.get(action);
    const result = typeof reply === 'function' ? reply(requests.at(-1)) : reply || (action === 'state' ? { body: current } : { body: { state: current } });
    return { ok: result.ok !== false, status: result.status || 200, json: async () => structuredClone(result.body) };
  }};
  const embedMessages = [], embedListeners = {}, embedStyles = {};
  let observedResize = () => {};
  if (embedOptions) {
    const shell = new Element('main', doc);
    shell.getBoundingClientRect = () => ({ height: embedOptions.height || 600 });
    doc.querySelector = selector => selector === '.image-shell' ? shell : null;
    doc.documentElement.style = { setProperty: (name, value) => { embedStyles[name] = value; } };
    context.window = { parent: { postMessage: (message, origin) => embedMessages.push({ message, origin }) },
      location: { search: '?embed=steamwork', origin: 'http://fixture' },
      addEventListener: (type, listener) => { embedListeners[type] = listener; },
      requestAnimationFrame: callback => setImmediate(callback) };
    context.ResizeObserver = class { constructor(callback) { observedResize = callback; } observe() {} };
    context.MutationObserver = class { observe() {} };
  }
  vm.runInNewContext(source, context);
  return { elements, requests, replies, storage, doc, embedMessages, embedStyles,
    sendContext: (value, { origin = 'http://fixture', source = context.window?.parent } = {}) => embedListeners.message?.({ data: value, origin, source }),
    resizeEmbed: height => { embedOptions.height = height; observedResize(); },
    setState: value => { current = structuredClone(value); } };
}
(async () => {
  assert(html.includes('.ico'));
  for (const match of source.matchAll(/byId\("([^\"]+)"\)/g)) assert(html.includes(`id="${match[1]}"`), `Missing HTML ID ${match[1]}`);
  const app = boot(initialState);
  await flush();
  const { elements: e } = app;
  assert.equal(e.libraryRoot.value, originalRoot);
  assert.equal(e.reviewApply.disabled, true, 'Conflict must have no default choice');
  assert.match(e.deviceSummary.textContent, /本地图库/);
  assert(e.syncSource.querySelector('option[value="notion"]').disabled);
  const previews = e.candidateList.querySelectorAll('img');
  assert(previews.some(value => value.src.includes('space=device')), 'Device previews must bind device space');
  assert.equal(e.imageGrid.querySelector('h3').textContent, image.title, 'Group title must be literal text');
  const replace = e.candidateList.querySelectorAll('input').find(input => input.value === 'replace');
  await replace.emit('change');
  assert.equal(e.reviewApply.disabled, false);
  app.replies.set('apply', { ok: false, status: 409, body: { error: 'plan_stale' } });
  await e.reviewApply.click();
  await flush();
  assert.equal(e.reviewApply.disabled, false, 'Failed apply must retain decisions');
  assert.match(e.operationStatus.textContent, /重新检查/);
  assert.equal(e.candidateList.querySelectorAll('input').length, 3);
  const reloaded = boot(initialState, app.storage); await flush();
  assert(reloaded.elements.candidateList.querySelectorAll('input').find(input => input.value === 'replace').checked, 'Reload must restore choice for same root/plan');
  app.replies.set('upload', { body: { ...review, state: initialState } });
  const applyCount = app.requests.filter(request => request.action === 'apply').length;
  await e.imageFiles.emit('change', { target: { files: [{ name: 'new.ico' }] } });
  const uploaded = app.requests.findLast(request => request.action === 'upload');
  assert(uploaded.body.fields.some(field => field[0] === 'expectedRoot' && field[1] === originalRoot));
  assert(uploaded.body.fields.some(field => field[0] === 'files' && field[2] === 'new.ico'));
  assert.equal(app.requests.filter(request => request.action === 'apply').length, applyCount, 'Upload must not apply automatically');
  const addPlan = { id: 'new-plan', candidates: [{ id: 'new1', status: 'new', incoming: image, existing: null, actions: ['keep', 'add'] }] };
  app.replies.set('sync', { body: addPlan });
  app.replies.set('apply', { body: { state: { ...initialState, plan: null, inboxCount: 0 }, message: '同步完成' } });
  e.syncSource.value = 'console'; e.syncTarget.value = 'device';
  await e.syncImages.click();
  assert.equal(app.requests.at(-1).action, 'apply', 'Conflict-free sync must complete in one click');
  assert.equal(app.requests.at(-1).body.decisions[0].action, 'add');
  assert.equal(e.reviewSection.hidden, true);
  assert.match(e.operationStatus.textContent, /同步完成/);
  app.replies.set('sync', { body: { ...review, id: 'conflict-plan2', planId: 'conflict-plan2' } });
  const countBefore = app.requests.filter(request => request.action === 'apply').length;
  await e.syncImages.click();
  assert.equal(app.requests.filter(request => request.action === 'apply').length, countBefore, 'Conflict sync must wait for confirmation');
  assert.equal(e.reviewApply.disabled, true);
  app.replies.set('scan', { body: { id: 'errors-plan', candidates: [], errors: [{ path: 'bad.png', error: '无法读取' }], state: initialState } });
  await e.scanImages.click();
  assert.equal(e.reviewSection.hidden, false, 'Skipped images must remain visible');
  assert.match(e.planWarnings.textContent, /bad.png/);
  assert.equal(e.reviewApply.disabled, true);
  const asyncInitial = { ...initialState, plan: addPlan, notion: { canAttempt: true, available: false, verified: false }, notionAvailable: false };
  const asyncApp = boot(asyncInitial); await flush();
  assert.equal(asyncApp.elements.syncSource.querySelector('option[value="notion"]').disabled, false, 'Can-attempt connection must be selectable before verification');
  assert.match(asyncApp.elements.notionSummary.textContent, /首次将核验/);
  const downloadPlan = { id: 'download-plan', planId: 'download-plan', candidates: [{ ...addPlan.candidates[0], id: 'download-new' }] };
  let requestId;
  asyncApp.replies.set('sync', request => { requestId = request.body.requestId; return { body: { operation: { requestId, status: 'running', phase: 'reading' } } }; });
  asyncApp.replies.set('operation', () => ({ body: { requestId, status: 'needs_review', phase: 'finished', planId: downloadPlan.id } }));
  asyncApp.setState({ ...asyncInitial, plan: downloadPlan });
  asyncApp.replies.set('apply', { body: { state: { ...asyncInitial, plan: null, inboxCount: 0 }, message: '下载已加入图库' } });
  asyncApp.elements.syncSource.value = 'notion'; asyncApp.elements.syncTarget.value = 'console';
  await asyncApp.elements.syncImages.click();
  assert.equal(asyncApp.requests.filter(request => request.action === 'apply').length, 1);
  assert.equal(asyncApp.requests.find(request => request.action === 'apply').body.planId, 'download-plan', 'Only the operation-matched plan may be auto-applied');
  assert.match(asyncApp.elements.operationStatus.textContent, /下载已加入图库/);
  const noPlanApp = boot(asyncInitial); await flush();
  noPlanApp.replies.set('sync', request => ({ body: { operation: { requestId: request.body.requestId, status: 'completed', message: 'Notion 附件已核对' } } }));
  noPlanApp.elements.syncSource.value = 'console'; noPlanApp.elements.syncTarget.value = 'notion';
  await noPlanApp.elements.syncImages.click();
  assert.equal(noPlanApp.requests.filter(request => request.action === 'apply').length, 0, 'Completed Notion upload must not apply an earlier scan plan');
  assert.match(noPlanApp.elements.operationStatus.textContent, /附件已核对/);
  const mismatchApp = boot(asyncInitial); await flush();
  mismatchApp.replies.set('sync', request => ({ body: { operation: { requestId: request.body.requestId, status: 'needs_review', planId: 'different-plan' } } }));
  mismatchApp.elements.syncSource.value = 'notion';
  await mismatchApp.elements.syncImages.click();
  assert.equal(mismatchApp.requests.filter(request => request.action === 'apply').length, 0);
  assert.equal(mismatchApp.elements.checkOperation.hidden, false, 'Unmatched result must retain a read-only resume action');
  assert.equal(mismatchApp.elements.syncImages.disabled, true, 'Uncertain request must not be posted again');
  assert.match(mismatchApp.elements.operationStatus.textContent, /记录尚未对应/);
  const directApp = boot(asyncInitial); await flush();
  directApp.replies.set('sync', { body: { state: asyncInitial, message: '没有新计划' } });
  await directApp.elements.syncImages.click();
  assert.equal(directApp.requests.filter(request => request.action === 'apply').length, 0, 'A sync response without its own plan must not auto-apply old state.plan');
  assert(asyncApp.elements.candidateList.children.length === 0);
  const compactApp = boot({ ...initialState, plan: addPlan }); await flush();
  assert(compactApp.elements.candidateList.children[0].className.includes('compact-new'));
  assert(!compactApp.elements.candidateList.querySelectorAll('*').some(element => element.className === 'empty-comparison'), 'New-only candidate must not render an empty comparison column');
  assert(!app.elements.candidateList.children.some(element => element.className?.includes('compact-new')), 'Conflicts retain comparison layout');
  const chainState = { ...asyncInitial, plan: null, deviceRoot: 'E:\\Fixture Export', notionPage: 'fixture-page' };
  const chain = boot(chainState); await flush();
  const importPlan = { ...addPlan, id: 'import-plan', planId: 'import-plan' };
  const devicePlan = { ...addPlan, id: 'device-plan', planId: 'device-plan' };
  chain.replies.set('scan', { body: importPlan });
  chain.replies.set('apply', request => { const next = { ...chainState, plan: null, inboxCount: 0 }; chain.setState(next); return { body: { ok: true, planId: request.body.planId, state: next } }; });
  chain.replies.set('sync', request => request.body.target === 'notion' ? { body: { operation: { requestId: request.body.requestId, status: 'completed', message: 'Notion 已验证' } } } : { body: devicePlan });
  chain.elements.syncSource.value = 'local'; chain.elements.syncTarget.value = 'all';
  await chain.elements.syncImages.click();
  assert.deepEqual(chain.requests.filter(request => ['scan','apply','sync'].includes(request.action)).map(request => [request.action, request.body.planId || request.body.target || '']), [['scan',''],['apply','import-plan'],['sync','notion'],['sync','device'],['apply','device-plan']], 'Local-to-all must include inbox before Notion and export only after Notion completes');
  assert.equal(chain.elements.restoreImages.hidden, false, 'Success receipt exposes local undo');
  chain.replies.set('restore', { ok: false, status: 409, body: { error: '图片已再次修改，不能覆盖' } });
  await chain.elements.restoreImages.click();
  assert.equal(chain.elements.restoreImages.hidden, false, 'Rejected undo retains receipt and original state');
  chain.replies.set('restore', { body: { ok: true, restored: true, state: chainState } });
  await chain.elements.restoreImages.click();
  assert.equal(chain.elements.restoreImages.hidden, true);
  assert.equal(chain.requests.findLast(request => request.action === 'restore').body.planId, 'device-plan');
  const pause = boot({ ...chainState, deviceRoot: '' }); await flush();
  const pausedPlan = { ...review, id: 'pause-plan', planId: 'pause-plan' };
  pause.replies.set('scan', { body: pausedPlan });
  pause.elements.syncSource.value = 'local'; pause.elements.syncTarget.value = 'notion';
  await pause.elements.syncImages.click();
  assert.equal(pause.requests.filter(request => request.action === 'sync').length, 0, 'Inbox conflict must pause before any Notion upload');
  assert.match(pause.elements.reviewNote.textContent, /自动继续/);
  const resumed = boot({ ...chainState, deviceRoot: '', plan: pausedPlan }, pause.storage); await flush();
  resumed.replies.set('apply', request => { const next = { ...chainState, deviceRoot: '', plan: null }; resumed.setState(next); return { body: { ok: true, planId: request.body.planId, state: next } }; });
  resumed.replies.set('sync', request => ({ body: { operation: { requestId: request.body.requestId, status: 'completed', message: 'Notion 已验证' } } }));
  await resumed.elements.candidateList.querySelectorAll('input').find(input => input.value === 'replace').emit('change');
  await resumed.elements.reviewApply.click(); await flush();
  assert.equal(resumed.requests.filter(request => request.action === 'sync').length, 1, 'Confirmed conflict must resume its saved Notion destination after reload');
  assert.equal(resumed.requests.find(request => request.action === 'sync').body.target, 'notion');
  const logoA = { ...image, id: 'logo-a', path: 'Logo.png', name: 'Logo.png', title: 'Logo', displayTitle: 'Logo', assetId: 'a', sha256: 'a', groupId: 'logo', groupTitle: 'Logo', variantId: 'va', variantLabel: '方案1', derivedFromId: '', width: 1280, height: 720 };
  const logoB = { ...logoA, id: 'logo-b', path: 'Logo (2).png', name: 'Logo (2).png', assetId: 'b', sha256: 'b', variantId: 'vb', variantLabel: '方案2' };
  const logoSmall = { ...logoA, id: 'logo-small', path: 'Logo 320x180.png', name: 'Logo 320x180.png', assetId: 'as', sha256: 'as', variantId: 'vas', derivedFromId: 'a', width: 320, height: 180 };
  const togo = { ...logoA, id: 'togo', path: 'Togo.png', name: 'Togo.png', title: 'Togo', displayTitle: '透明Logo', assetId: 't', sha256: 't', groupId: 'transparent-logo', groupTitle: '透明Logo', variantId: 'vt', hasTransparency: true };
  const groupedState = { ...initialState, plan: null, items: [logoA, logoB, logoSmall, togo] };
  const grouped = boot(groupedState); await flush();
  assert.equal(grouped.elements.imageGrid.children.length, 2, 'Togo and Logo must remain separate groups');
  let logoGroup = grouped.elements.imageGrid.children.find(element => element.dataset.groupId === 'logo');
  assert.equal(logoGroup.querySelector('h3').textContent, 'Logo');
  assert(logoGroup.querySelectorAll('span').some(element => element.textContent === '2 方案 · 2 尺寸'), 'Only explicit derivative links share a scheme count');
  assert.equal(logoGroup.querySelectorAll('button').filter(element => element.dataset.variantPath).length, 2, 'Both same-size schemes must be accessible');
  await logoGroup.querySelectorAll('button').find(element => element.dataset.variantPath === logoB.path).click();
  logoGroup = grouped.elements.imageGrid.children.find(element => element.dataset.groupId === 'logo');
  assert.equal(new URL(logoGroup.querySelector('img').src, 'http://fixture').searchParams.get('path'), logoB.path);
  logoGroup.querySelector('select').value = '320 × 180';
  await logoGroup.querySelector('select').emit('change');
  logoGroup = grouped.elements.imageGrid.children.find(element => element.dataset.groupId === 'logo');
  assert(logoGroup.querySelectorAll('span').some(element => element.className === 'derivative-badge'));
  assert.equal(logoGroup.querySelectorAll('button').filter(element => element.dataset.variantPath).length, 1);
  logoGroup.querySelector('select').value = '1280 × 720';
  await logoGroup.querySelector('select').emit('change');
  logoGroup = grouped.elements.imageGrid.children.find(element => element.dataset.groupId === 'logo');
  assert(logoGroup.querySelectorAll('button').find(element => element.dataset.variantPath === logoA.path).attributes['aria-pressed'] === 'true', 'Changing size must preserve an explicitly linked scheme where available');
  const togoGroup = grouped.elements.imageGrid.children.find(element => element.dataset.groupId === 'transparent-logo');
  assert.equal(togoGroup.querySelector('h3').textContent, '透明Logo');
  assert(togoGroup.querySelectorAll('p').some(element => element.textContent.includes('Togo.png')), 'Display alias must retain original filename');
  await logoGroup.querySelectorAll('button').find(element => element.dataset.metadataPath === logoA.path).click();
  assert.equal(grouped.elements.metadataDialog.open, true);
  assert.equal(grouped.elements.metadataGroupTitle.value, 'Logo');
  assert(grouped.elements.metadataOriginal.textContent.includes('Logo.png'));
  assert(!grouped.elements.metadataDerivedFrom.children.some(element => element.value === 'a'), 'Source selector must exclude self');
  grouped.elements.metadataGroupTitle.value = '商店Logo'; grouped.elements.metadataVariantLabel.value = '备选构图';
  grouped.replies.set('metadata', { ok: false, status: 409, body: { error: '原图已改变，填写内容已保留' } });
  await grouped.elements.metadataForm.emit('submit');
  assert.equal(grouped.elements.metadataDialog.open, true);
  assert.equal(grouped.elements.metadataVariantLabel.value, '备选构图');
  assert.equal(grouped.elements.metadataGroupTitle.value, '商店Logo');
  assert.equal(grouped.elements.metadataStatus.dataset.error, 'true');
  const updatedLogo = { ...logoA, groupId: 'store-logo', groupTitle: '商店Logo', variantLabel: '备选构图' };
  grouped.replies.set('metadata', { body: { ok: true, item: updatedLogo, state: { ...groupedState, items: [updatedLogo, logoB, logoSmall, togo] } } });
  await grouped.elements.metadataForm.emit('submit');
  assert.equal(grouped.elements.metadataDialog.open, false);
  const metadataRequest = grouped.requests.findLast(request => request.action === 'metadata').body;
  assert.equal(metadataRequest.path, 'Logo.png'); assert.equal(metadataRequest.sha256, 'a');
  assert.equal(metadataRequest.groupTitle, '商店Logo');
  assert.equal(grouped.requests.filter(request => ['apply','upload'].includes(request.action)).length, 0, 'Editing metadata must never generate or rewrite image bytes');
  const variantConflict = boot({ ...initialState, plan: { ...review, candidates: [{ ...candidate, matchReason: 'name-size' }] } }); await flush();
  assert(variantConflict.elements.candidateList.querySelectorAll('span').some(element => element.textContent === '保留为另一方案'));
  const exactDuplicate = boot({ ...initialState, plan: { ...review, candidates: [{ ...candidate, status: 'duplicate', matchReason: 'bytes' }] } }); await flush();
  assert(exactDuplicate.elements.candidateList.querySelectorAll('span').some(element => element.textContent === '另存副本'));
  assert(!exactDuplicate.elements.candidateList.querySelectorAll('span').some(element => element.textContent === '保留为另一方案'));
  const pendingSourceItem = { ...togo, path: 'inbox/Togo.png', pendingDerivedFromId: 'remote-parent', derivedFromId: '' };
  const pendingPlan = { ...addPlan, candidates: [{ ...addPlan.candidates[0], incoming: pendingSourceItem }] };
  const pendingState = { ...initialState, items: [logoA], plan: pendingPlan };
  const pendingSource = boot(pendingState); await flush();
  assert(pendingSource.elements.candidateList.querySelectorAll('p').some(element => element.textContent.includes('派生来源待同步 / 待关联')));
  await pendingSource.elements.candidateList.querySelectorAll('button').find(element => element.dataset.metadataPath === pendingSourceItem.path).click();
  assert.equal(pendingSource.elements.metadataDerivedFrom.value, '__pending_source__');
  pendingSource.elements.metadataVariantLabel.value = '保留来源的方案';
  pendingSource.replies.set('metadata', { body: { ok: true, item: { ...pendingSourceItem, variantLabel: '保留来源的方案' }, state: pendingState } });
  await pendingSource.elements.metadataForm.emit('submit');
  assert.equal(Object.hasOwn(pendingSource.requests.findLast(request => request.action === 'metadata').body, 'derivedFromId'), false, 'Unchanged pending source must not be silently cleared or guessed');
  assert(pendingSource.elements.candidateList.querySelectorAll('p').some(element => element.textContent.includes('保留来源的方案')));
  const pageA = '11111111-1111-1111-1111-111111111111', pageB = '22222222-2222-2222-2222-222222222222';
  const catalogUnknown = { id: 'existing-operation', requestId: 'existing-request-135', root: originalRoot, pageId: pageA, source: 'console', target: 'notion', status: 'unknown', code: 'catalog_attached_unverified', message: '目录已附页，待回读验证' };
  const recoveryState = { ...asyncInitial, plan: null, lastSync: null, notionPage: `https://www.notion.so/${pageA}`, notion: { canAttempt: true, pageId: pageA }, operation: catalogUnknown };
  const recovery = boot(recoveryState); await flush();
  assert.equal(recovery.requests.filter(request => request.action === 'sync').length, 0, 'Loading an unknown catalog request must never POST');
  assert.equal(recovery.elements.checkOperation.hidden, false);
  recovery.replies.set('operation', { body: catalogUnknown });
  recovery.replies.set('sync', request => { const completed = { ...catalogUnknown, status: 'completed', finishedAt: '2026-11-01T03:00:00Z', remainingTargets: [] }; recovery.setState({ ...recoveryState, operation: completed }); return { body: { operation: completed } }; });
  const startAt = recovery.requests.length;
  await recovery.elements.checkOperation.click();
  assert.equal(recovery.requests[startAt].action, 'operation', 'Resume must first GET the old operation');
  const resumedPosts = recovery.requests.filter(request => request.action === 'sync');
  assert.equal(resumedPosts.length, 1);
  assert.deepEqual(resumedPosts[0].body, { expectedRoot: originalRoot, requestId: catalogUnknown.requestId, source: 'console', target: 'notion' }, 'Catalog verification must reuse the exact original request and scope');
  assert.equal(recovery.requests.filter(request => ['apply','upload'].includes(request.action)).length, 0);
  assert.notEqual(recovery.elements.lastSync.textContent, '尚无同步记录', 'Verified remote-only completion must count as a real sync');
  const ordinary = boot({ ...recoveryState, operation: { ...catalogUnknown, code: 'other_unknown' } }); await flush();
  ordinary.replies.set('operation', { body: { ...catalogUnknown, code: 'other_unknown' } });
  await ordinary.elements.checkOperation.click();
  assert.equal(ordinary.requests.filter(request => request.action === 'sync').length, 0, 'Ordinary unknown operations must remain GET-only');
  for (const change of [{ root: 'D:\\Other Fixture' }, { pageId: pageB }, { source: 'notion' }, { target: 'all' }, { requestId: 'other-request' }]) {
    const scoped = boot(recoveryState); await flush();
    scoped.replies.set('operation', { body: { ...catalogUnknown, ...change } });
    await scoped.elements.checkOperation.click();
    assert.equal(scoped.requests.filter(request => request.action === 'sync').length, 0, `Changed receipt scope must not resume: ${JSON.stringify(change)}`);
  }
  const changedPage = boot(recoveryState); await flush();
  changedPage.replies.set('operation', { body: catalogUnknown });
  changedPage.setState({ ...recoveryState, notionPage: `https://www.notion.so/${pageB}`, notion: { canAttempt: true, pageId: pageB } });
  await changedPage.elements.checkOperation.click();
  assert.equal(changedPage.requests.filter(request => request.action === 'sync').length, 0, 'Changed configured page must reject old catalog resume');
  const changedDirection = boot(recoveryState); await flush();
  changedDirection.replies.set('operation', { body: catalogUnknown });
  changedDirection.elements.syncSource.value = 'local';
  await changedDirection.elements.checkOperation.click();
  assert.equal(changedDirection.requests.filter(request => request.action === 'sync').length, 0, 'Even a UI direction change with the same effective target must not silently resume');
  for (const status of ['unknown','running','failed','needs_review']) {
    const timestampApp = boot({ ...initialState, plan: null, lastSync: { at: '2025-01-01T00:00:00Z' }, operation: { status, finishedAt: '2027-01-01T00:00:00Z', remainingTargets: [] } }); await flush();
    assert(timestampApp.elements.lastSync.textContent.includes('2025'), `${status} must not advance the completion timestamp`);
  }
  const unfinishedTarget = boot({ ...initialState, plan: null, lastSync: { at: '2025-01-01T00:00:00Z' }, operation: { status: 'completed', finishedAt: '2027-01-01T00:00:00Z', remainingTargets: ['device'] } }); await flush();
  assert(unfinishedTarget.elements.lastSync.textContent.includes('2025'), 'A remaining target must prevent a full completion timestamp');
  const latestCompleted = boot({ ...initialState, plan: null, lastSync: { at: '2025-01-01T00:00:00Z' }, operation: { status: 'completed', finishedAt: '2026-01-01T00:00:00Z', remainingTargets: [] }, notion: { operation: { status: 'completed', finishedAt: '2027-01-01T00:00:00Z', remainingTargets: [] } } }); await flush();
  assert(latestCompleted.elements.lastSync.textContent.includes('2027'), 'Footer must choose the latest verified local/remote completion');
  for (const [status, code] of [['failed','notion_sync_failed'], ['unknown','verified_completion_unrecorded']]) {
    const verifiedPrior = { ...catalogUnknown, status, code, recheckable: true, recheckKind: 'verified_completion' };
    const verifiedState = { ...recoveryState, operation: verifiedPrior };
    const recheck = boot(verifiedState); await flush();
    assert.equal(recheck.requests.filter(request => request.action === 'sync').length, 0, 'Loading verified effects must remain read-only');
    assert.equal(recheck.elements.checkOperation.hidden, false, 'Only positive public completion evidence permits explicit recheck');
    recheck.replies.set('operation', { body: verifiedPrior });
    recheck.replies.set('sync', request => { const done = { ...verifiedPrior, status: 'completed', finishedAt: '2026-11-01T04:00:00Z', remainingTargets: [] }; recheck.setState({ ...verifiedState, operation: done }); return { body: { operation: done } }; });
    await recheck.elements.checkOperation.click();
    const posts = recheck.requests.filter(request => request.action === 'sync');
    assert.equal(posts.length, 1);
    assert.deepEqual(posts[0].body, { expectedRoot: originalRoot, requestId: verifiedPrior.requestId, source: verifiedPrior.source, target: verifiedPrior.target }, 'Verified completion recheck must preserve the same request and scope');
    assert.equal(recheck.requests.filter(request => ['apply','upload'].includes(request.action)).length, 0);
  }
  for (const change of [{ recheckable: false }, { recheckable: 'true' }, { recheckKind: 'other' }, { code: 'some_other_failure' }]) {
    const generic = { ...catalogUnknown, status: 'failed', code: 'notion_sync_failed', recheckable: true, recheckKind: 'verified_completion', ...change };
    const unproven = boot({ ...recoveryState, operation: generic }); await flush();
    assert.equal(unproven.elements.checkOperation.hidden, true, 'Generic failed receipts must not gain a replay path without exact positive public evidence');
    assert.equal(unproven.requests.filter(request => request.action === 'sync').length, 0);
  }
  const indexSource = fs.readFileSync(resolve(projectRoot, 'index.html'), 'utf8');
  const hostSource = fs.readFileSync(resolve(projectRoot, 'app.js'), 'utf8');
  assert(indexSource.includes('id="steamworkImageTitle">Image</h3>'));
  assert(indexSource.includes('data-src="image-manager.html?embed=steamwork"'));
  for (const id of ['imageManagerOpen','steamworkAssetList','steamworkAssetRoot','steamworkAssetSummary','steamworkAssetFileInput']) assert(!indexSource.includes(`id="${id}"`), `Removed checklist/extra entry must stay absent: ${id}`);
  assert(!indexSource.includes('href="image-manager.html"'), 'Primary Image experience must not be an extra standalone link');
  assert(html.includes('href="/steamwork.html"'), 'Standalone compatibility page must return to the actual Image host');
  const eightPlan = { ...addPlan, candidates: Array.from({ length: 8 }, (_, i) => ({ ...addPlan.candidates[0], id: `inbox-${i}`, incoming: { ...image, path: `inbox/new-${i}.png` } })) };
  const embeddedApp = boot({ ...groupedState, plan: eightPlan, inboxCount: 8 }, makeStorage(), { height: 600 }); await flush();
  assert.equal(embeddedApp.doc.documentElement.dataset.embed, 'steamwork');
  assert.equal(embeddedApp.elements.reviewSection.dataset.expanded, 'false', 'Restored Inbox must not push the primary gallery below eight review cards');
  assert.equal(embeddedApp.elements.candidateList.children.length, 8, 'Collapsing reviews must preserve the real plan');
  assert.equal(embeddedApp.elements.imageGrid.children.length, 2);
  assert.equal(embeddedApp.elements.imageGrid.children.find(card => card.dataset.groupId === 'transparent-logo').querySelectorAll('button').filter(button => button.dataset.variantPath).length, 0, 'A single option must not repeat the full preview as a thumbnail');
  assert.equal(embeddedApp.elements.imageGrid.children.find(card => card.dataset.groupId === 'logo').querySelectorAll('button').filter(button => button.dataset.variantPath).length, 2, 'All real alternative options must remain switchable');
  await embeddedApp.elements.reviewToggle.click();
  assert.equal(embeddedApp.elements.reviewSection.dataset.expanded, 'true');
  await embeddedApp.elements.reviewToggle.click();
  assert.equal(embeddedApp.requests.filter(request => ['apply','sync','scan','upload'].includes(request.action)).length, 0, 'Opening or expanding an Inbox must never alter originals or trigger synchronization');
  embeddedApp.replies.set('scan', { body: eightPlan });
  await embeddedApp.elements.scanImages.click();
  assert.equal(embeddedApp.elements.reviewSection.dataset.expanded, 'true', 'An explicit check must reveal its comparison results');
  assert(embeddedApp.embedMessages.some(value => value.message.type === 'ready' && value.origin === 'http://fixture'));
  assert(embeddedApp.embedMessages.some(value => value.message.type === 'size' && value.message.height === 600));
  embeddedApp.resizeEmbed(240); await flush();
  assert(embeddedApp.embedMessages.some(value => value.message.type === 'size' && value.message.height === 240), 'Embed sizing must shrink as well as grow');
  const trustedContext = { channel: 'console-image-embed-v1', type: 'context', theme: 'light', language: 'en', visibleTop: 120, visibleHeight: 640 };
  embeddedApp.sendContext(trustedContext, { origin: 'https://outside.invalid' });
  embeddedApp.sendContext(trustedContext, { source: {} });
  assert.equal(embeddedApp.doc.documentElement.dataset.theme, undefined);
  embeddedApp.sendContext(trustedContext); await flush();
  assert.equal(embeddedApp.doc.documentElement.dataset.theme, 'light');
  assert.equal(embeddedApp.doc.documentElement.dataset.hostLanguage, 'en');
  assert.equal(embeddedApp.embedStyles['--image-embed-visible-top'], '120px');
  assert.equal(embeddedApp.embedStyles['--image-embed-visible-height'], '640px');
  const hostFrame = { contentWindow: {}, style: { height: '480px' }, dataset: {}, imageReadyTimer: 1 };
  const hostContext = { els: { steamworkImageFrame: hostFrame, steamworkImageStatus: { hidden: false } }, window: { location: { origin: 'http://fixture' }, clearTimeout() {} }, scheduleSteamworkImageContext() {}, syncSteamworkImageFrame() {} };
  const receiverStart = hostSource.indexOf('function receiveSteamworkImageMessage(event) {');
  const receiverEnd = hostSource.indexOf('function openSteamworkImagePanel()', receiverStart);
  vm.runInNewContext(hostSource.slice(receiverStart, receiverEnd), hostContext);
  const sendHeight = (height, override = {}) => hostContext.receiveSteamworkImageMessage({ source: hostFrame.contentWindow, origin: 'http://fixture', data: { channel: 'console-image-embed-v1', type: 'size', height }, ...override });
  sendHeight(900, { origin: 'https://outside.invalid' }); sendHeight(900, { source: {} });
  for (const value of [NaN, -1, Infinity, 2000001, '900']) sendHeight(value);
  assert.equal(hostFrame.style.height, '480px', 'Untrusted frames/origins or invalid heights must not resize the host');
  sendHeight(700); assert.equal(hostFrame.style.height, '702px');
  sendHeight(250); assert.equal(hostFrame.style.height, '252px');
  assert.equal(hostFrame.dataset.ready, 'true');
  const contextStart = hostSource.indexOf('function syncSteamworkImageFrame() {');
  const contextEnd = hostSource.indexOf('function scheduleSteamworkImageContext()', contextStart);
  const sentContexts = [];
  let currentFrameRect = { width: 0, height: 0, top: 0 };
  const contextFrame = { contentWindow: { postMessage: value => sentContexts.push(value) }, getAttribute: () => 'image-manager.html?embed=steamwork', getBoundingClientRect: () => currentFrameRect };
  const viewportContext = { els: { steamworkImageFrame: contextFrame }, document: { documentElement: { dataset: { theme: 'dark' } } }, language: 'en', window: { innerHeight: 900, location: { origin: 'http://fixture' } } };
  vm.runInNewContext(hostSource.slice(contextStart, contextEnd), viewportContext);
  viewportContext.syncSteamworkImageFrame();
  assert.equal(sentContexts.length, 0, 'Hidden module frames must not overwrite a valid dialog viewport with 160px');
  currentFrameRect = { width: 1000, height: 800, top: 150 };
  viewportContext.syncSteamworkImageFrame();
  assert.equal(sentContexts[0].visibleHeight, 750);
  assert(hostSource.includes('if (activeModuleId === "steamwork") scheduleSteamworkImageContext();'), 'Returning to a loaded Steamwork module must refresh its viewport without reloading data');
  const moduleStart = hostSource.indexOf('    case "steamwork":');
  const moduleEnd = hostSource.indexOf('    case "randomrealm":', moduleStart);
  let inlineOpens = 0;
  const moduleContext = { els: { steamworkImageFrame: {} }, openSteamworkImagePanel() { inlineOpens++; }, hasSteamwork: true, loadSteamworkAssets() { throw new Error('Legacy checklist must not be requested by the new Image panel'); } };
  assert.equal(await vm.runInNewContext(`(async () => {${hostSource.slice(moduleStart, moduleEnd).replace('    case "steamwork":','')}})()`, moduleContext), true);
  assert.equal(inlineOpens, 1);
  const draftStart = hostSource.indexOf('function steamworkImageHasDraft() {');
  const draftEnd = hostSource.indexOf('function refreshForNewConsoleVersion(', draftStart);
  let draftFrame = null;
  const draftContext = { document: { getElementById: () => draftFrame } };
  vm.runInNewContext(hostSource.slice(draftStart, draftEnd), draftContext);
  assert.equal(draftContext.steamworkImageHasDraft(), false);
  draftFrame = { getAttribute: () => null };
  assert.equal(draftContext.steamworkImageHasDraft(), false);
  const frameFields = { metadataDialog: { open: false }, locations: { open: false }, imageGrid: { getAttribute: () => 'false' } };
  draftFrame = { getAttribute: () => 'image-manager.html?embed=steamwork', contentDocument: { getElementById: id => frameFields[id] } };
  assert.equal(draftContext.steamworkImageHasDraft(), false);
  frameFields.metadataDialog.open = true; assert.equal(draftContext.steamworkImageHasDraft(), true);
  frameFields.metadataDialog.open = false; frameFields.locations.open = true; assert.equal(draftContext.steamworkImageHasDraft(), true);
  frameFields.locations.open = false; frameFields.imageGrid.getAttribute = () => 'true'; assert.equal(draftContext.steamworkImageHasDraft(), true);
  frameFields.imageGrid.getAttribute = () => 'false'; assert.equal(draftContext.steamworkImageHasDraft(), false);
  draftFrame = { getAttribute: () => 'image-manager.html?embed=steamwork', get contentDocument() { throw new Error('not same origin'); } };
  assert.equal(draftContext.steamworkImageHasDraft(), true);
  assert(hostSource.slice(draftEnd, hostSource.indexOf('function consoleWindowSessionId()', draftEnd)).includes('steamworkImageHasDraft()'), 'Automatic update reload must consult the embedded editor/busy guard');
  console.log('PASS inline Image: original panel replacement, no duplicate entries/checklist fetch, collapsed Inbox, preserved plan, real variants, authenticated resize/theme bridge, grow/shrink and standalone compatibility.');
  console.log('PASS: IDs, literal titles, root/space preview binding, conflict defaults, failed apply preservation, reload decisions, inbox-only upload, one-click new sync, conflict gating, skipped-file visibility.');
  console.log('PASS: First-connection availability, async phase polling, operation/plan binding, no old-plan apply, completed upload receipt, unknown-result resume without reposting.');
  console.log('PASS: Compact new cards, full-width conflict comparison, local inbox-to-Notion-to-device sequence, saved conflict continuation after reload, undo receipt and changed-file rejection.');
  console.log('PASS: Purpose grouping, all existing variants/sizes accessible, explicit derivative lineage, Togo alias without merge/rename, safe metadata editor with failed-save draft, and duplicate versus alternative labels.');
  console.log('PASS: Inbox metadata projection retains choices; missing remote derivative source stays pending and is preserved unless explicitly changed.');
  console.log('PASS: Explicit same-request catalog resume only after GET; ordinary unknown/load stay GET-only; root/page/source/target/request changes refuse; footer uses only completed operations without remaining targets.');
})().catch(error => { console.error(error); process.exitCode = 1; });
