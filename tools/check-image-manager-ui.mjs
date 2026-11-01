import fs from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import crypto from 'node:crypto';
import { Blob, File } from 'node:buffer';
const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source = fs.readFileSync(resolve(projectRoot, 'image-manager.js'), 'utf8');
const html = fs.readFileSync(resolve(projectRoot, 'image-manager.html'), 'utf8');
class Element {
  constructor(tag, doc) { this.tagName = tag; this.doc = doc; this.children = []; this.dataset = {}; this.attributes = {}; this.events = {}; this.value = ''; this.className = ''; this.style = { setProperty: (key, value) => { this.style[key] = value; } }; this._classes = new Set(); this.classList = { add: (...v) => v.forEach(x => this._classes.add(x)), remove: (...v) => v.forEach(x => this._classes.delete(x)) }; }
  append(...children) { for (const child of children) child.parentElement = this; this.children.push(...children); }
  replaceChildren(...children) { for (const child of this.children) child.parentElement = null; this.children = []; this.append(...children); }
  setAttribute(k, v) { this.attributes[k] = v; }
  getAttribute(k) { return this.attributes[k] ?? null; }
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
  async emit(name, extra = {}) {
    if (name === 'change' && this.type === 'radio') for (const input of this.doc.querySelector('.image-shell').querySelectorAll('input')) if (input.name === this.name) input.checked = input === this;
    for (const callback of this.events[name] || []) await callback({ target: this, preventDefault() {}, ...extra });
  }
  click() { return this.emit('click'); }
}
const flush = async () => { for (let i = 0; i < 7; i++) await new Promise(resolve => setImmediate(resolve)); };
const arrow = (card, action) => card.querySelectorAll('button').find(button => button.dataset.variantNavigate === action);
const position = card => card.querySelectorAll('span').find(element => element.className === 'variant-position')?.textContent;
const originalRoot = 'D:\\Fixture Images';
const image = { path: 'sample 64x64.png', title: '<img src=x onerror=alert(1)>', width: 64, height: 64, sha256: 'a'.repeat(64), space: 'root' };
const candidate = { id: 'candidate1', status: 'conflict', incoming: { ...image, path: 'inbox/sample.png' }, existing: { ...image, space: 'device', sha256: 'b'.repeat(64) }, actions: ['replace', 'keep', 'add'] };
const review = { id: 'plan1', planId: 'plan1', candidates: [candidate], errors: [] };
const initialState = { root: originalRoot, deviceRoot: 'E:\\Fixture Export', notionPage: '', items: [image], inboxCount: 1, plan: review };
function makeStorage(existing = new Map()) { return { getItem: key => existing.get(key) || null, setItem: (key, value) => existing.set(key, value), removeItem: key => existing.delete(key), existing }; }
function boot(initial, storage = makeStorage(), embedOptions = null) {
  const elements = {};
  const docEvents = {}, windowEvents = {};
  let documentFocused = true;
  const doc = { getElementById: id => elements[id], createElement: tag => new Element(tag, doc), documentElement: { dataset: {} }, addEventListener: (type, listener) => { (docEvents[type] ||= []).push(listener); }, activeElement: null,
    emit: async (name, event) => { for (const listener of docEvents[name] || []) await listener(event); }, hasFocus: () => documentFocused };
  for (const match of html.matchAll(/<(\w+)([^>]*\bid="([^"]+)"[^>]*)>/g)) { const element = new Element(match[1], doc); element.id = match[3]; element.hidden = /\shidden(?:\s|$)/.test(match[2]); elements[match[3]] = element; }
  const shell = new Element('main', doc);
  shell.getBoundingClientRect = () => ({ height: embedOptions?.height || 600 });
  shell.append(...Object.values(elements));
  elements.imagePasteMenu.append(elements.imagePasteCommand);
  elements.imagePasteMenu.hidden = true;
  doc.body = new Element('body', doc); doc.body.append(shell);
  doc.querySelector = selector => selector === '.image-shell' ? shell : null;
  for (const id of ['syncSource', 'syncTarget']) { const option = new Element('option', doc); option.value = 'notion'; elements[id].append(option); }
  elements.syncSource.value = 'console'; elements.syncTarget.value = 'notion';
  elements.emptyState.append(new Element('h3', doc), new Element('p', doc));
  let current = structuredClone(initial);
  const requests = [];
  const replies = new Map();
  let clipboardRead = async () => { throw new Error('Clipboard fixture has no image'); }, clipboardReads = 0;
  class FormData { constructor() { this.fields = []; } append(...field) { this.fields.push(field); } }
  const context = { document: doc, navigator: { clipboard: { read: () => { clipboardReads++; return clipboardRead(); }, readText() { throw new Error('Text clipboard reads are forbidden'); } } }, Blob, File, sessionStorage: storage, localStorage: storage.localStorage ||= makeStorage(), URLSearchParams, FormData, crypto: crypto, setTimeout: callback => setImmediate(callback), console, fetch: async (url, options) => {
    const action = url.split('/').at(-1).split('?')[0];
    requests.push({ action, url, options, body: typeof options.body === 'string' ? JSON.parse(options.body) : options.body });
    const reply = replies.get(action);
    const result = typeof reply === 'function' ? await reply(requests.at(-1)) : reply || (action === 'state' ? { body: current } : { body: { state: current } });
    return { ok: result.ok !== false, status: result.status || 200, json: async () => structuredClone(result.body) };
  }};
  const embedMessages = [], embedListeners = windowEvents, embedStyles = {};
  context.window = { location: { search: '', origin: 'http://fixture' }, addEventListener: (type, listener) => { (windowEvents[type] ||= []).push(listener); } };
  context.window.parent = context.window;
  let observedResize = () => {};
  if (embedOptions) {
    doc.documentElement.style = { setProperty: (name, value) => { embedStyles[name] = value; } };
    context.window = { parent: { postMessage: (message, origin) => embedMessages.push({ message, origin }) },
      location: { search: '?embed=steamwork', origin: 'http://fixture' },
      addEventListener: (type, listener) => { (windowEvents[type] ||= []).push(listener); },
      requestAnimationFrame: callback => setImmediate(callback) };
    context.ResizeObserver = class { constructor(callback) { observedResize = callback; } observe() {} };
    context.MutationObserver = class { observe() {} };
  }
  vm.runInNewContext(source, context);
  return { elements, requests, replies, storage, doc, embedMessages, embedStyles,
    sendContext: (value, { origin = 'http://fixture', source = context.window?.parent } = {}) => { for (const listener of embedListeners.message || []) listener({ data: value, origin, source }); },
    resizeEmbed: height => { embedOptions.height = height; observedResize(); },
    emitWindow: (name, event = {}) => { for (const listener of windowEvents[name] || []) listener(event); },
    setClipboardRead: value => { clipboardRead = value; }, clipboardReadCount: () => clipboardReads,
    disableClipboardRead: () => { context.navigator.clipboard.read = undefined; },
    setDocumentFocus: value => { documentFocused = value; },
    setState: value => { current = structuredClone(value); } };
}
(async () => {
  assert(html.includes('.ico'));
  for (const match of source.matchAll(/byId\("([^\"]+)"\)/g)) assert(html.includes(`id="${match[1]}"`), `Missing HTML ID ${match[1]}`);
  const app = boot(initialState);
  await flush();
  const { elements: e } = app;
  assert.equal(e.libraryRoot.value, originalRoot);
  assert.equal(e.reviewApply.disabled, false, 'A unique matching replacement defaults to the new image but still waits for confirmation');
  assert(e.candidateList.querySelectorAll('input').find(input => input.value === 'replace').checked);
  assert.equal(app.requests.filter(request => request.action === 'apply').length, 0, 'Default replacement must never apply by itself');
  const keptChoice = boot(initialState); await flush();
  await keptChoice.elements.candidateList.querySelectorAll('input').find(input => input.value === 'keep').emit('change');
  const keptReload = boot(initialState, keptChoice.storage); await flush();
  assert(keptReload.elements.candidateList.querySelectorAll('input').find(input => input.value === 'keep').checked, 'A saved manual choice overrides the replacement default');
  for (const changed of [{ status: 'ambiguous', matches: [candidate.existing, image] },
      { previousCandidateId: 'previous-match' }, { incoming: { ...candidate.incoming, width: 65 } }]) {
    const unresolvedDefault = boot({ ...initialState, plan: { ...review, candidates: [{ ...candidate, ...changed }] } }); await flush();
    assert.equal(unresolvedDefault.elements.reviewApply.disabled, true, 'Ambiguous, rematched and dimension-mismatched candidates still require a choice');
    assert(!unresolvedDefault.elements.candidateList.querySelectorAll('input').some(input => input.checked));
  }
  assert.equal(e.deviceSummary.textContent, initialState.deviceRoot);
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
  await e.transferDeviceImages.click();
  assert.equal(app.requests.at(-1).action, 'apply', 'Conflict-free sync must complete in one click');
  assert.equal(app.requests.at(-1).body.decisions[0].action, 'add');
  assert.equal(e.reviewSection.hidden, true);
  assert.match(e.operationStatus.textContent, /同步完成/);
  app.replies.set('sync', { body: { ...review, id: 'conflict-plan2', planId: 'conflict-plan2' } });
  const countBefore = app.requests.filter(request => request.action === 'apply').length;
  await e.transferDeviceImages.click();
  assert.equal(app.requests.filter(request => request.action === 'apply').length, countBefore, 'Conflict sync must wait for confirmation');
  assert.equal(e.reviewApply.disabled, false, 'The matching replacement is selected while its explicit confirmation remains available');
  app.replies.set('scan', { body: { id: 'errors-plan', candidates: [], errors: [{ path: 'bad.png', error: '无法读取' }], state: initialState } });
  await e.scanImages.click();
  assert.equal(e.reviewSection.hidden, false, 'Skipped images must remain visible');
  assert.match(e.planWarnings.textContent, /bad.png/);
  assert.equal(e.reviewApply.disabled, true);
  const asyncInitial = { ...initialState, plan: addPlan, notionPage: '11111111111111111111111111111111', notion: { canAttempt: true, available: false, verified: false }, notionAvailable: false };
  const asyncApp = boot(asyncInitial); await flush();
  assert.equal(asyncApp.elements.syncSource.querySelector('option[value="notion"]').disabled, false, 'Can-attempt connection must be selectable before verification');
  assert.match(asyncApp.elements.notionSummary.textContent, /未核验/);
  const downloadPlan = { id: 'download-plan', planId: 'download-plan', candidates: [{ ...addPlan.candidates[0], id: 'download-new' }] };
  let requestId;
  asyncApp.replies.set('sync', request => { requestId = request.body.requestId; return { body: { operation: { requestId, status: 'running', phase: 'reading' } } }; });
  asyncApp.replies.set('operation', () => ({ body: { requestId, status: 'needs_review', phase: 'finished', planId: downloadPlan.id } }));
  asyncApp.setState({ ...asyncInitial, plan: downloadPlan });
  asyncApp.replies.set('apply', { body: { state: { ...asyncInitial, plan: null, inboxCount: 0 }, message: '下载已加入图库' } });
  asyncApp.elements.syncSource.value = 'notion'; asyncApp.elements.syncTarget.value = 'console';
  asyncApp.elements.syncDirection.value = 'notion-to-console'; await asyncApp.elements.syncImages.click();
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
  mismatchApp.elements.syncSource.value = 'notion'; mismatchApp.elements.syncTarget.value = 'console';
  mismatchApp.elements.syncDirection.value = 'notion-to-console'; await mismatchApp.elements.syncImages.click();
  assert.equal(mismatchApp.requests.filter(request => request.action === 'apply').length, 0);
  assert.equal(mismatchApp.elements.checkOperation.hidden, true, 'The legacy duplicate resume button stays hidden');
  assert.equal(mismatchApp.elements.syncDirection.disabled, true, 'The unresolved original direction is locked');
  assert.equal(mismatchApp.elements.syncImages.disabled, false, 'The single main button remains available to check the original request');
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
  const chainState = { ...asyncInitial, plan: null, deviceRoot: 'E:\\Fixture Export', notionPage: '11111111111111111111111111111111' };
  const chain = boot(chainState); await flush();
  const importPlan = { ...addPlan, id: 'import-plan', planId: 'import-plan' };
  const devicePlan = { ...addPlan, id: 'device-plan', planId: 'device-plan' };
  chain.replies.set('scan', { body: importPlan });
  chain.replies.set('apply', request => { const next = { ...chainState, plan: null, inboxCount: 0 }; chain.setState(next); return { body: { ok: true, planId: request.body.planId, state: next } }; });
  chain.replies.set('sync', request => request.body.target === 'notion' ? { body: { operation: { requestId: request.body.requestId, status: 'completed', message: 'Notion 已验证' } } } : { body: devicePlan });
  chain.elements.syncSource.value = 'local'; chain.elements.syncTarget.value = 'all';
  await chain.elements.advancedSyncImages.click();
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
  await pause.elements.advancedSyncImages.click();
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
  assert.equal(logoGroup.querySelectorAll('button').filter(element => element.dataset.variantNavigate).length, 2, 'Both arrows browse the real same-size schemes');
  assert.equal(position(logoGroup), '1 / 2');
  await arrow(logoGroup, 'next').click();
  logoGroup = grouped.elements.imageGrid.children.find(element => element.dataset.groupId === 'logo');
  assert.equal(new URL(logoGroup.querySelector('img').src, 'http://fixture').searchParams.get('path'), logoB.path);
  logoGroup.querySelector('select').value = '320 × 180';
  await logoGroup.querySelector('select').emit('change');
  logoGroup = grouped.elements.imageGrid.children.find(element => element.dataset.groupId === 'logo');
  assert(logoGroup.querySelectorAll('span').some(element => element.className === 'derivative-badge'));
  assert.equal(logoGroup.querySelectorAll('button').filter(element => element.dataset.variantNavigate).length, 0, 'A single image at this size needs no navigation arrows');
  logoGroup.querySelector('select').value = '1280 × 720';
  await logoGroup.querySelector('select').emit('change');
  logoGroup = grouped.elements.imageGrid.children.find(element => element.dataset.groupId === 'logo');
  assert.equal(logoGroup.dataset.currentPath, logoA.path, 'Changing size must preserve an explicitly linked scheme where available');
  const togoGroup = grouped.elements.imageGrid.children.find(element => element.dataset.groupId === 'transparent-logo');
  assert.equal(togoGroup.querySelector('h3').textContent, '透明Logo');
  assert(togoGroup.querySelectorAll('p').some(element => element.textContent.includes('Togo.png')), 'Display alias must retain original filename');
  await logoGroup.querySelectorAll('button').find(element => element.dataset.metadataPath === logoA.path).click();
  assert.equal(grouped.elements.metadataDialog.open, true);
  assert.equal(grouped.elements.metadataSave.disabled, true, 'Unchanged metadata must not be saved or pushed again');
  assert.equal(grouped.elements.metadataSaveOnly.disabled, true);
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
  assert.equal(grouped.elements.metadataDialog.open, true, 'Keep the saved/sync outcome visible until the user closes it');
  assert.match(grouped.elements.metadataStatus.textContent, /已更新本地.*尚未配置 Notion/);
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
  const logoC = { ...logoA, id: 'logo-c', path: 'Logo (3).png', name: 'Logo (3).png', assetId: 'c', sha256: 'c', variantId: 'vc', variantLabel: '方案3' };
  const playtestLogo = { ...logoA, id: 'playtest-logo', path: 'Playtest Logo.png', assetId: 'pt', sha256: 'pt', groupId: 'playtest-logo', variantId: 'vpt' };
  const carousel = boot({ ...groupedState, items: [logoA, logoB, logoC, logoSmall, playtestLogo] }); await flush();
  const mainCard = () => carousel.elements.imageGrid.children.find(card => card.dataset.groupId === 'logo');
  const nav = card => card.querySelectorAll('*').find(element => element.className === 'variant-navigation');
  assert.equal(carousel.elements.imageGrid.children.length, 2, 'Existing distinct main/Playtest purpose IDs must not become alternatives of one card');
  assert.equal(position(mainCard()), '1 / 3', 'Only actual same-size originals appear in the option counter');
  assert.equal(mainCard().querySelectorAll('img').length, 1, 'Arrow navigation must not repeat the main image in a thumbnail strip');
  await arrow(mainCard(), 'next').click();
  assert.equal(mainCard().dataset.currentPath, logoB.path);
  assert.equal(position(mainCard()), '2 / 3');
  assert.equal(carousel.doc.activeElement, arrow(mainCard(), 'next'), 'Pointer navigation must restore focus to the same arrow after rendering');
  await arrow(mainCard(), 'next').click(); assert.equal(mainCard().dataset.currentPath, logoC.path);
  await arrow(mainCard(), 'next').click(); assert.equal(mainCard().dataset.currentPath, logoA.path, 'Next wraps from the third real option to the first');
  await arrow(mainCard(), 'previous').click(); assert.equal(mainCard().dataset.currentPath, logoC.path, 'Previous wraps from first to last');
  await nav(mainCard()).emit('keydown', { key: 'Home', target: arrow(mainCard(), 'previous') });
  assert.equal(mainCard().dataset.currentPath, logoA.path);
  await nav(mainCard()).emit('keydown', { key: 'End', target: arrow(mainCard(), 'next') });
  assert.equal(mainCard().dataset.currentPath, logoC.path);
  await nav(mainCard()).emit('keydown', { key: 'ArrowRight', target: arrow(mainCard(), 'next') });
  assert.equal(mainCard().dataset.currentPath, logoA.path);
  await nav(mainCard()).emit('keydown', { key: 'ArrowLeft', target: arrow(mainCard(), 'previous') });
  assert.equal(mainCard().dataset.currentPath, logoC.path);
  await mainCard().querySelectorAll('button').find(button => button.className === 'thumbnail-button').click();
  assert.match(carousel.elements.previewMeta.textContent, /Logo \(3\)\.png/, 'Preview must follow the selected option');
  await carousel.elements.closePreview.click();
  await mainCard().querySelectorAll('button').find(button => button.dataset.metadataPath).click();
  assert.match(carousel.elements.metadataOriginal.textContent, /Logo \(3\)\.png/, 'Option editor must target the selected original');
  assert.equal(carousel.elements.metadataVariantLabel.value, '方案3');
  await carousel.elements.metadataClose.click();
  await nav(mainCard()).emit('keydown', { key: 'Home', target: arrow(mainCard(), 'previous') });
  mainCard().querySelector('select').value = '320 × 180'; await mainCard().querySelector('select').emit('change');
  assert.equal(mainCard().dataset.currentPath, logoSmall.path);
  assert.equal(position(mainCard()), undefined, 'A derivative size is a size choice rather than another same-size option');
  assert(!arrow(mainCard(), 'next'));
  mainCard().querySelector('select').value = '1280 × 720'; await mainCard().querySelector('select').emit('change');
  assert.equal(mainCard().dataset.currentPath, logoA.path, 'Returning from a derivative preserves its explicitly linked original scheme');
  assert.equal(position(mainCard()), '1 / 3');
  assert(!arrow(carousel.elements.imageGrid.children.find(card => card.dataset.groupId === playtestLogo.groupId), 'next'));
  assert.equal(carousel.requests.filter(request => request.options.method === 'POST').length, 0, 'Browsing, previews, size selection and opening an editor must not write or create assets');
  const inboxOptions = [logoA, logoB, logoC].map((item, index) => ({ id: `inbox-option-${index + 1}`, status: 'new', incoming: { ...item, path: `inbox/${item.path}` }, existing: null, actions: ['add','keep'] }));
  const inboxOptionsPlan = { id: 'three-inbox-options', candidates: inboxOptions };
  const inboxCarousel = boot({ ...groupedState, plan: inboxOptionsPlan, inboxCount: 3 }); await flush();
  const inboxCard = () => inboxCarousel.elements.candidateList.children[0];
  const selectedRadio = () => inboxCard().querySelectorAll('input').find(input => input.checked);
  assert.equal(inboxCarousel.elements.candidateList.children.length, 1, 'Same-purpose, same-size new Inbox originals share one browsing card');
  assert.equal(inboxCarousel.elements.reviewCount.textContent, '3 项待确认', 'Review count must be original candidates rather than visible cards');
  assert.match(inboxCarousel.elements.reviewNote.textContent, /每张图片分别选择.*全部候选.*左右切换/);
  assert.equal(inboxCard().dataset.candidateId, inboxOptions[0].id);
  assert.equal(selectedRadio().value, 'add', 'The existing new-candidate add default remains unchanged');
  await inboxCard().querySelectorAll('input').find(input => input.value === 'keep').emit('change');
  await arrow(inboxCard(), 'next').click();
  assert.equal(inboxCard().dataset.candidateId, inboxOptions[1].id);
  assert.equal(selectedRadio().value, 'add', 'Other candidates retain their own default when the first is kept out');
  await arrow(inboxCard(), 'next').click();
  assert.equal(inboxCard().dataset.candidateId, inboxOptions[2].id);
  await inboxCard().querySelectorAll('input').find(input => input.value === 'keep').emit('change');
  await arrow(inboxCard(), 'next').click();
  assert.equal(inboxCard().dataset.candidateId, inboxOptions[0].id);
  assert.equal(selectedRadio().value, 'keep', 'The first candidate decision survives a full cycle');
  await nav(inboxCard()).emit('keydown', { key: 'End', target: arrow(inboxCard(), 'next') });
  assert.equal(inboxCard().dataset.candidateId, inboxOptions[2].id);
  assert.equal(selectedRadio().value, 'keep');
  await nav(inboxCard()).emit('keydown', { key: 'Home', target: selectedRadio() });
  assert.equal(inboxCard().dataset.candidateId, inboxOptions[2].id, 'Navigation key handling must not consume radio/form keys');
  await inboxCard().querySelectorAll('button').find(button => button.dataset.metadataPath).click();
  assert.match(inboxCarousel.elements.metadataOriginal.textContent, /inbox\/Logo \(3\)\.png/);
  await inboxCarousel.elements.metadataClose.click();
  assert.equal(inboxCarousel.requests.filter(request => request.options.method === 'POST').length, 0, 'Inbox browsing and local decision changes are zero-write until explicit confirmation');
  const inboxReload = boot({ ...groupedState, plan: inboxOptionsPlan, inboxCount: 3 }, inboxCarousel.storage); await flush();
  const reloadedCard = () => inboxReload.elements.candidateList.children[0];
  assert.equal(reloadedCard().querySelectorAll('input').find(input => input.value === 'keep').checked, true);
  await arrow(reloadedCard(), 'next').click();
  assert.equal(reloadedCard().querySelectorAll('input').find(input => input.value === 'add').checked, true);
  await arrow(reloadedCard(), 'next').click();
  assert.equal(reloadedCard().querySelectorAll('input').find(input => input.value === 'keep').checked, true);
  inboxCarousel.replies.set('apply', { ok: false, status: 409, body: { error: 'plan_stale' } });
  await inboxCarousel.elements.reviewApply.click(); await flush();
  assert.deepEqual(inboxCarousel.requests.findLast(request => request.action === 'apply').body.decisions, inboxOptions.map((item, index) => ({ id: item.id, action: index === 1 ? 'add' : 'keep' })), 'Confirmation must submit every original candidate, including currently hidden options');
  const exceptions = [
    { ...inboxOptions[0], id: 'other-purpose', incoming: { ...inboxOptions[0].incoming, groupId: playtestLogo.groupId } },
    { ...inboxOptions[0], id: 'other-size', incoming: { ...inboxOptions[0].incoming, width: 320, height: 180 } },
    { ...inboxOptions[0], id: 'other-space', incoming: { ...inboxOptions[0].incoming, space: 'device' } },
    { ...inboxOptions[0], id: 'unknown-size', incoming: { ...inboxOptions[0].incoming, width: null } },
    { ...inboxOptions[0], id: 'string-size', incoming: { ...inboxOptions[0].incoming, width: '1280' } },
    { ...inboxOptions[0], id: 'zero-size', incoming: { ...inboxOptions[0].incoming, height: 0 } },
    { ...inboxOptions[0], id: 'conflict-stays-separate', status: 'conflict', existing: logoB, actions: ['add','keep','replace'] },
    { ...inboxOptions[0], id: 'duplicate-stays-separate', status: 'duplicate', existing: logoB },
    { ...inboxOptions[0], id: 'ambiguous-stays-separate', status: 'ambiguous', matches: [logoA,logoB] },
    { ...inboxOptions[0], id: 'new-match-stays-separate', matches: [logoA] },
    { ...inboxOptions[0], id: 'new-existing-stays-separate', existing: logoA }
  ];
  const isolated = boot({ ...groupedState, plan: { id: 'isolated-new-buckets', candidates: [...inboxOptions, ...exceptions] } }); await flush();
  assert.equal(isolated.elements.candidateList.children.length, exceptions.length + 1, 'Only new candidates with exact purpose, actual positive integer dimensions and space may share a card');
  assert.equal(isolated.elements.reviewApply.disabled, true, 'An unresolved conflict outside the displayed option still blocks confirmation');
  assert(isolated.elements.candidateList.children.filter(card => ['conflict','duplicate','ambiguous'].includes(card.dataset.status)).every(card => !arrow(card, 'next') && card.querySelectorAll('img').length >= 2), 'Conflicts and duplicate/ambiguous comparisons must remain complete individual cards');
  assert.equal(isolated.requests.filter(request => request.options.method === 'POST').length, 0);
  const fallbackPurpose = boot({ ...groupedState, plan: { id: 'fallback-purpose', candidates: inboxOptions.map((candidate, index) => ({ ...candidate, incoming: { ...candidate.incoming, groupId: '', groupTitle: ['Icône','ICÔNE','Ico\u0302ne'][index] } })) } }); await flush();
  assert.equal(fallbackPurpose.elements.candidateList.children.length, 1, 'A missing group ID falls back to the existing normalized purpose/title semantics');
  assert.equal(position(fallbackPurpose.elements.candidateList.children[0]), '1 / 3');
  const explicitPurpose = boot({ ...groupedState, items: [logoA,{ ...logoB, path: 'Playtest/Logo.png' }] }); await flush();
  assert.equal(explicitPurpose.elements.imageGrid.children.length, 1, 'A path name must not override an explicitly shared purpose group');
  assert.equal(position(explicitPurpose.elements.imageGrid.children[0]), '1 / 2');
  const sameHashNew = boot({ ...groupedState, plan: { id: 'independent-new-identities', candidates: [inboxOptions[0], { ...inboxOptions[1], incoming: { ...inboxOptions[1].incoming, sha256: inboxOptions[0].incoming.sha256 } }] } }); await flush();
  assert.equal(position(sameHashNew.elements.candidateList.children[0]), '1 / 2', 'UI grouping does not deduplicate distinct new candidate IDs or alter their defaults');
  await arrow(sameHashNew.elements.candidateList.children[0], 'next').click();
  assert.equal(sameHashNew.elements.candidateList.children[0].dataset.candidateId, inboxOptions[1].id);
  assert.equal(sameHashNew.elements.candidateList.children[0].querySelectorAll('input').find(input => input.value === 'add').checked, true);
  let releaseScan;
  const busyBrowse = boot({ ...groupedState, items: [logoA,logoB,logoC], plan: inboxOptionsPlan }); await flush();
  busyBrowse.replies.set('scan', () => new Promise(resolve => { releaseScan = resolve; }));
  const runningScan = busyBrowse.elements.scanImages.click(); await flush();
  const busyGallery = busyBrowse.elements.imageGrid.children[0], busyInbox = busyBrowse.elements.candidateList.children[0];
  assert.equal(arrow(busyGallery, 'next').disabled, true); assert.equal(arrow(busyInbox, 'next').disabled, true);
  assert.equal(busyGallery.querySelector('select').disabled, true);
  await arrow(busyGallery, 'next').click(); await arrow(busyInbox, 'next').click();
  await nav(busyGallery).emit('keydown', { key: 'End', target: arrow(busyGallery, 'next') });
  assert.equal(busyBrowse.elements.imageGrid.children[0].dataset.currentPath, logoA.path);
  assert.equal(busyBrowse.elements.candidateList.children[0].dataset.candidateId, inboxOptions[0].id);
  releaseScan({ body: { ...inboxOptionsPlan, state: { ...groupedState, items: [logoA,logoB,logoC], plan: inboxOptionsPlan } } });
  await runningScan;
  assert.equal(arrow(busyBrowse.elements.imageGrid.children[0], 'next').disabled, false);
  assert.deepEqual(busyBrowse.requests.filter(request => request.options.method === 'POST').map(request => request.action), ['scan'], 'Busy navigation must not enqueue a write or change the selected original');
  const pendingBrowse = boot({ ...groupedState, notionPage: '11111111111111111111111111111111', items: [logoA,logoB,logoC], plan: inboxOptionsPlan, notion: { canAttempt: true } }); await flush();
  pendingBrowse.replies.set('sync', request => ({ body: { operation: { requestId: request.body.requestId, status: 'unknown', message: '原请求待核对' } } }));
  pendingBrowse.elements.syncSource.value = 'console'; pendingBrowse.elements.syncTarget.value = 'notion';
  pendingBrowse.elements.syncDirection.value = 'notion-to-console'; await pendingBrowse.elements.syncImages.click();
  assert.equal(arrow(pendingBrowse.elements.imageGrid.children[0], 'next').disabled, true);
  assert.equal(arrow(pendingBrowse.elements.candidateList.children[0], 'next').disabled, true);
  await arrow(pendingBrowse.elements.imageGrid.children[0], 'next').click();
  assert.equal(pendingBrowse.elements.imageGrid.children[0].dataset.currentPath, logoA.path);
  assert.deepEqual(pendingBrowse.requests.filter(request => request.options.method === 'POST').map(request => request.action), ['sync'], 'Uncertain pending operation navigation cannot start another request');
  const pageA = '11111111-1111-1111-1111-111111111111', pageB = '22222222-2222-2222-2222-222222222222';
  const editedLogo = { ...logoA, variantLabel: '保存的新方案名' };
  const metadataState = { ...groupedState, notionPage: `https://www.notion.so/${pageA}`, notion: { canAttempt: true, verified: true, pageId: pageA }, plan: addPlan };
  const metadataSavedState = { ...metadataState, items: [editedLogo, logoB, logoSmall, togo] };
  const completedPush = request => ({ requestId: request.body.requestId, root: originalRoot, pageId: pageA, source: 'console', target: 'notion', status: 'completed', remainingTargets: [] });
  const openAndEdit = async (view, item = logoA) => {
    await view.elements.imageGrid.querySelectorAll('button').find(button => button.dataset.metadataPath === item.path).click();
    view.elements.metadataVariantLabel.value = editedLogo.variantLabel;
    await view.elements.metadataVariantLabel.emit('input');
    assert.equal(view.elements.metadataSave.disabled, false);
    assert.match(view.elements.metadataStatus.textContent, /未保存/);
  };
  const saveReply = (view, savedState = metadataSavedState, item = editedLogo) => {
    view.replies.set('metadata', () => { view.setState(savedState); return { body: { ok: true, item, state: savedState } }; });
  };
  const fixedPush = boot(metadataState); await flush();
  await openAndEdit(fixedPush); saveReply(fixedPush);
  fixedPush.elements.syncSource.value = 'notion'; fixedPush.elements.syncTarget.value = 'console';
  fixedPush.elements.syncDirection.value = 'notion-to-console';
  fixedPush.replies.set('sync', request => ({ body: { operation: completedPush(request) } }));
  await fixedPush.elements.metadataForm.emit('submit');
  assert.deepEqual(fixedPush.requests.filter(request => ['metadata','sync','scan','apply'].includes(request.action)).map(request => request.action), ['metadata','sync']);
  assert.equal(fixedPush.requests.find(request => request.action === 'sync').body.source, 'console', 'Saved metadata must be pushed from Console, regardless of the old Notion source selection');
  assert.equal(fixedPush.elements.syncSource.value, 'notion', 'A primary saved-edit push must not rewrite advanced controls');
  assert.equal(fixedPush.elements.syncTarget.value, 'console');
  assert.equal(fixedPush.elements.syncDirection.value, 'notion-to-console', 'Save and sync always pushes, then restores the prior main direction after successful completion');
  assert.match(fixedPush.elements.metadataStatus.textContent, /已(?:保存，并|更新本地，并完成)同步/);
  assert.equal(fixedPush.elements.candidateList.children.length, 1, 'Pushing saved metadata must retain the unrelated Inbox review');
  const fixedCount = fixedPush.requests.length;
  await fixedPush.elements.metadataForm.emit('submit');
  await fixedPush.elements.metadataSaveOnly.click();
  assert.equal(fixedPush.requests.length, fixedCount, 'No changes after verified completion must not save or sync again');
  const onlySave = boot(metadataState); await flush();
  await openAndEdit(onlySave); saveReply(onlySave);
  await onlySave.elements.metadataSaveOnly.click();
  assert.equal(onlySave.requests.filter(request => request.action === 'sync').length, 0);
  assert.match(onlySave.elements.metadataStatus.textContent, /已更新本地，Notion 待同步/);
  assert.equal(onlySave.elements.metadataSave.textContent, '同步已保存修改');
  onlySave.elements.metadataDialog.close(); await flush();
  const pendingSaved = boot(metadataSavedState, onlySave.storage); await flush();
  await pendingSaved.elements.imageGrid.querySelectorAll('button').find(button => button.dataset.metadataPath === logoA.path).click();
  assert.equal(pendingSaved.elements.metadataSave.textContent, '同步已保存修改', 'Saved pending status must survive reopen and reload');
  pendingSaved.replies.set('sync', request => ({ body: { operation: completedPush(request) } }));
  await pendingSaved.elements.metadataForm.emit('submit');
  assert.equal(pendingSaved.requests.filter(request => request.action === 'metadata').length, 0, 'Retry saved edits without another metadata save');
  assert.equal(pendingSaved.requests.filter(request => request.action === 'sync').length, 1);
  const saveRejected = boot(metadataState); await flush(); await openAndEdit(saveRejected);
  saveRejected.replies.set('metadata', { ok: false, status: 409, body: { message: '原图已改变' } });
  await saveRejected.elements.metadataForm.emit('submit');
  assert.equal(saveRejected.requests.filter(request => request.action === 'sync').length, 0);
  assert.equal(saveRejected.elements.metadataVariantLabel.value, editedLogo.variantLabel);
  assert.equal(saveRejected.elements.metadataSave.disabled, false);
  const configDraft = boot(metadataState); await flush();
  configDraft.elements.deviceRoot.value = 'E:\\Unsaved Destination';
  await configDraft.elements.syncImages.click();
  assert.equal(configDraft.requests.filter(request => ['sync','scan'].includes(request.action)).length, 0);
  assert.equal(configDraft.elements.locations.open, true);
  assert.match(configDraft.elements.configStatus.textContent, /先保存位置/);
  await openAndEdit(configDraft);
  await configDraft.elements.metadataForm.emit('submit');
  assert.equal(configDraft.requests.filter(request => request.action === 'metadata').length, 0, 'Save-and-sync must not silently ignore a location draft');
  const inboxSync = boot({ ...metadataState, plan: pendingPlan }); await flush();
  await inboxSync.elements.candidateList.querySelectorAll('button').find(button => button.dataset.metadataPath === pendingSourceItem.path).click();
  inboxSync.elements.metadataVariantLabel.value = 'Inbox 新标注';
  inboxSync.replies.set('metadata', { body: { ok: true, item: { ...pendingSourceItem, variantLabel: 'Inbox 新标注' }, state: { ...metadataState, plan: pendingPlan } } });
  await inboxSync.elements.metadataForm.emit('submit');
  assert.equal(inboxSync.requests.filter(request => ['scan','sync','apply'].includes(request.action)).length, 0, 'Metadata on an unconfirmed Inbox image must never publish or import it');
  assert.match(inboxSync.elements.metadataStatus.textContent, /已保存到 Inbox.*确认入库后再同步/);
  for (const changed of [{ root: 'D:\\Changed Root' }, { notionPage: `https://www.notion.so/${pageB}` }, { deviceRoot: 'E:\\Changed Device' }, { items: [{ ...editedLogo, sha256: 'changed-asset' }] }]) {
    const lateSave = boot(metadataState); await flush(); await openAndEdit(lateSave);
    lateSave.replies.set('metadata', { body: { ok: true, item: editedLogo, state: { ...metadataSavedState, ...changed } } });
    await lateSave.elements.metadataForm.emit('submit');
    assert.equal(lateSave.requests.filter(request => request.action === 'sync').length, 0, 'A save receipt for a changed root/page/device/asset must not start a push');
    assert.equal(lateSave.elements.metadataVariantLabel.value, editedLogo.variantLabel);
    assert.equal(lateSave.elements.metadataDialog.open, true);
  }
  const prepareLegacyMetadataJob = async (view, targets) => {
    await view.elements.metadataSaveOnly.click();
    const key = `console-image-metadata-sync:${originalRoot}:${logoA.path}:${logoA.sha256}`;
    const saved = JSON.parse(view.storage.getItem(key));
    assert(saved, 'The saved edit must exist before restoring its old destination scope');
    const { uiMode, ...legacy } = saved;
    view.storage.setItem(key, JSON.stringify({ ...legacy, targets, completed: [], status: 'saved' }));
    view.elements.metadataDialog.close(); await flush();
    await view.elements.imageGrid.querySelectorAll('button').find(button => button.dataset.metadataPath === logoA.path).click();
  };
  const deviceMetadata = { status: 'completed', applied: 1, unresolved: 0, target: 'device' };
  const deviceState = { ...metadataState, notionPage: '', notion: {}, deviceRoot: 'E:\\Fixture Export' };
  const deviceSavedState = { ...deviceState, items: metadataSavedState.items };
  const devicePlanScope = { root: originalRoot, deviceRoot: deviceState.deviceRoot, direction: 'to-device' };
  const deviceOnly = boot(deviceState); await flush(); await openAndEdit(deviceOnly); saveReply(deviceOnly, deviceSavedState); await prepareLegacyMetadataJob(deviceOnly, ['device']);
  deviceOnly.replies.set('sync', { body: { id: 'device-metadata-only', ...devicePlanScope, candidates: [], metadataSync: deviceMetadata } });
  await deviceOnly.elements.metadataForm.emit('submit');
  assert.equal(deviceOnly.requests.find(request => request.action === 'sync').body.target, 'device');
  assert.equal(deviceOnly.requests.filter(request => request.action === 'apply').length, 0, 'Same-byte metadata synchronization must not rewrite image files');
  assert.match(deviceOnly.elements.metadataStatus.textContent, /已(?:保存，并|更新本地，并完成)同步/);
  const deviceNew = boot(deviceState); await flush(); await openAndEdit(deviceNew); saveReply(deviceNew, deviceSavedState); await prepareLegacyMetadataJob(deviceNew, ['device']);
  deviceNew.replies.set('sync', { body: { ...devicePlan, ...devicePlanScope, metadataSync: { ...deviceMetadata, status: 'needs_review' } } });
  deviceNew.replies.set('apply', { body: { ok: true, planId: devicePlan.id, state: deviceSavedState, metadataSync: deviceMetadata } });
  await deviceNew.elements.metadataForm.emit('submit');
  assert.deepEqual(deviceNew.requests.filter(request => request.action === 'apply').map(request => request.body.planId), [devicePlan.id], 'Only the freshly returned device plan may be auto-applied; never the earlier Inbox plan');
  const deviceConflict = boot(deviceState); await flush(); await openAndEdit(deviceConflict); saveReply(deviceConflict, deviceSavedState); await prepareLegacyMetadataJob(deviceConflict, ['device']);
  const metadataDeviceConflict = { ...review, ...devicePlanScope, id: 'device-review-metadata', planId: 'device-review-metadata' };
  deviceConflict.replies.set('sync', { body: { ...metadataDeviceConflict, metadataSync: { ...deviceMetadata, status: 'needs_review' } } });
  await deviceConflict.elements.metadataForm.emit('submit');
  assert.equal(deviceConflict.requests.filter(request => request.action === 'apply').length, 0);
  assert.match(deviceConflict.elements.metadataStatus.textContent, /设备同步有待确认/);
  deviceConflict.elements.metadataDialog.close(); await flush();
  deviceConflict.replies.set('apply', { body: { ok: true, planId: metadataDeviceConflict.id, state: deviceSavedState, metadataSync: deviceMetadata } });
  await deviceConflict.elements.candidateList.querySelectorAll('input').find(input => input.value === 'replace').emit('change');
  await deviceConflict.elements.reviewApply.click(); await flush();
  assert.match(deviceConflict.elements.operationStatus.textContent, /已(?:保存，并|更新本地，并完成)同步/);
  const bothState = { ...metadataState, deviceRoot: deviceState.deviceRoot };
  const bothSavedState = { ...bothState, items: metadataSavedState.items };
  const partial = boot(bothState); await flush(); await openAndEdit(partial); saveReply(partial, bothSavedState); await prepareLegacyMetadataJob(partial, ['notion','device']);
  partial.replies.set('sync', request => request.body.target === 'notion' ? { body: { operation: completedPush(request) } } : { ok: false, status: 503, body: { message: '设备暂不可用' } });
  await partial.elements.metadataForm.emit('submit');
  assert.match(partial.elements.metadataStatus.textContent, /已(?:保存到|更新)本地.*部分位置已同步.*同步未完成/);
  partial.replies.set('sync', { body: { id: 'device-retry-metadata', ...devicePlanScope, candidates: [], metadataSync: deviceMetadata } });
  await partial.elements.metadataForm.emit('submit');
  assert.deepEqual(partial.requests.filter(request => request.action === 'sync').map(request => request.body.target), ['notion','device','device'], 'Retry a partial result only at the unfinished location');
  assert.equal(partial.requests.filter(request => request.body?.target === 'device')[0].body.requestId, partial.requests.filter(request => request.body?.target === 'device')[1].body.requestId, 'An unfinished device check keeps its request identity on retry');
  assert.equal(partial.requests.filter(request => request.action === 'metadata').length, 1);
  for (const changed of [{ root: 'D:\\Other Actual Root' }, { deviceRoot: 'E:\\Other Actual Export' }, { direction: 'from-device' }, { deviceRoot: undefined }]) {
    const mismatchedDevice = boot(deviceState); await flush(); await openAndEdit(mismatchedDevice); saveReply(mismatchedDevice, deviceSavedState); await prepareLegacyMetadataJob(mismatchedDevice, ['device']);
    mismatchedDevice.replies.set('sync', { body: { ...devicePlan, ...devicePlanScope, ...changed, metadataSync: deviceMetadata } });
    await mismatchedDevice.elements.metadataForm.emit('submit');
    assert.equal(mismatchedDevice.requests.filter(request => request.action === 'apply').length, 0, 'A device plan for changed/missing root, target or direction must never auto-apply');
    assert.match(mismatchedDevice.elements.metadataStatus.textContent, /已(?:保存到|更新)本地.*计划.*不一致/);
    assert.equal(mismatchedDevice.elements.metadataSave.disabled, true, 'A stale device destination requires a fresh scope instead of retrying it');
  }
  const savedUnknown = boot(metadataState); await flush(); await openAndEdit(savedUnknown); saveReply(savedUnknown);
  let savedUnknownRequest;
  const unknownReceipt = request => ({ ...completedPush(request), status: 'unknown', code: 'network_result_unknown' });
  savedUnknown.replies.set('sync', request => { savedUnknownRequest = request; return { body: { operation: unknownReceipt(request) } }; });
  await savedUnknown.elements.metadataForm.emit('submit');
  assert.match(savedUnknown.elements.metadataStatus.textContent, /已(?:保存到|更新)本地.*同步未完成/);
  assert.equal(savedUnknown.elements.metadataSave.textContent, '继续核对');
  savedUnknown.replies.set('operation', { body: unknownReceipt(savedUnknownRequest) });
  await savedUnknown.elements.metadataForm.emit('submit');
  assert.equal(savedUnknown.requests.filter(request => request.action === 'sync').length, 1, 'Ordinary unknown metadata pushes must only GET the existing request');
  const oldMetadataRequestId = savedUnknownRequest.body.requestId;
  const unknownReload = boot({ ...metadataSavedState, operation: unknownReceipt(savedUnknownRequest) }, savedUnknown.storage); await flush();
  assert.equal(unknownReload.requests.filter(request => request.action === 'sync').length, 0, 'Reload must restore saved-edit identity and never POST an unknown request');
  assert.match(unknownReload.elements.operationStatus.textContent, /已(?:保存到|更新)本地.*同步未完成/);
  unknownReload.replies.set('operation', { body: unknownReceipt(savedUnknownRequest) });
  await unknownReload.elements.syncImages.click();
  assert(unknownReload.requests.findLast(request => request.action === 'operation').url.includes(oldMetadataRequestId));
  assert.equal(unknownReload.requests.filter(request => request.action === 'sync').length, 0);
  savedUnknown.replies.set('operation', { body: { ...unknownReceipt(savedUnknownRequest), code: 'catalog_attached_unverified' } });
  savedUnknown.replies.set('sync', request => ({ body: { operation: completedPush(request) } }));
  await savedUnknown.elements.metadataForm.emit('submit');
  assert.deepEqual(savedUnknown.requests.filter(request => request.action === 'sync').map(request => request.body.requestId), [oldMetadataRequestId,oldMetadataRequestId], 'Explicit recoverable verification must reuse the original saved-edit request ID');
  assert.equal(savedUnknown.requests.filter(request => ['scan','apply'].includes(request.action)).length, 0);
  for (const changed of [{ root: 'D:\\Changed Root' }, { notionPage: `https://www.notion.so/${pageB}` }, { deviceRoot: 'E:\\Other Device' }, { items: [{ ...editedLogo, sha256: 'changed-asset' }] }, { items: [{ ...editedLogo, variantLabel: '其他窗口的修改' }, logoB, logoSmall, togo] }]) {
    const latePush = boot(bothState); await flush(); await openAndEdit(latePush); saveReply(latePush, bothSavedState);
    latePush.replies.set('sync', request => { latePush.setState({ ...bothSavedState, ...changed }); return { body: { operation: completedPush(request) } }; });
    await latePush.elements.metadataForm.emit('submit');
    assert.equal(latePush.requests.filter(request => request.action === 'sync').length, 1, 'A changed page/device/asset completion receipt must not continue pushing to another target');
    assert.match(latePush.elements.metadataStatus.textContent, /已(?:保存到|更新)本地.*同步未完成/);
  }
  const syncFingerprint = 'd'.repeat(64);
  const syncSummary = { root: originalRoot, pageId: pageA, status: 'synced', localFingerprint: syncFingerprint, syncedFingerprint: syncFingerprint, lastSyncedAt: '2026-11-01T03:00:00Z' };
  const syncedLocalState = { ...metadataState, plan: review, notionSync: syncSummary };
  for (const [summary, expected] of [
    [syncSummary, 'synced'],
    [{ ...syncSummary, localFingerprint: 'e'.repeat(64), status: 'pending' }, 'pending'],
    [{ ...syncSummary, localFingerprint: 'e'.repeat(64) }, 'unverified'],
    [{ ...syncSummary, localFingerprint: 'bad', syncedFingerprint: 'bad' }, 'unverified'],
    [{ ...syncSummary, root: 'D:\\Different Library' }, 'unverified'],
    [{ ...syncSummary, pageId: pageB }, 'unverified'],
    [{ ...syncSummary, status: 'syncing' }, 'syncing'],
    [{ ...syncSummary, status: 'failed' }, 'failed'],
    [undefined, 'unverified'],
  ]) {
    const statusView = boot({ ...syncedLocalState, notionSync: summary }); await flush();
    assert.equal(statusView.elements.notionSyncState.dataset.status, expected);
    assert(statusView.elements.notionSyncState.textContent.includes('Notion'), 'Status needs visible text as well as color');
    assert.equal(statusView.requests.filter(request => request.options.method === 'POST').length, 0);
  }
  const localUpdate = boot(syncedLocalState); await flush();
  localUpdate.replies.set('scan', { body: { id: 'updated-folder', candidates: [], state: { ...syncedLocalState, notionSync: { ...syncSummary, status: 'pending', localFingerprint: 'f'.repeat(64) } } } });
  await localUpdate.elements.scanImages.click();
  assert.deepEqual(localUpdate.requests.filter(request => request.options.method === 'POST').map(request => request.action), ['scan'], 'Refresh list reviews the Console folder without publishing or adopting');
  assert.equal(localUpdate.elements.notionSyncState.dataset.status, 'pending');
  const primaryPush = boot(syncedLocalState); await flush();
  primaryPush.elements.syncSource.value = 'notion'; primaryPush.elements.syncTarget.value = 'console';
  primaryPush.replies.set('sync', request => ({ body: { operation: completedPush(request) } }));
  await primaryPush.elements.syncImages.click();
  const primaryPosts = primaryPush.requests.filter(request => request.options.method === 'POST');
  assert.deepEqual(primaryPosts.map(request => request.action), ['sync']);
  assert.equal(primaryPosts[0].body.source, 'console'); assert.equal(primaryPosts[0].body.target, 'notion');
  assert.equal(primaryPush.elements.candidateList.children.length, 1, 'The primary push leaves the unadopted Inbox review intact');
  for (const receiptMode of ['direct-plan', 'operation-plan']) {
    const unexpectedPlan = { ...addPlan, id: 'unexpected-push-plan', planId: 'unexpected-push-plan' };
    const unexpected = boot({ ...syncedLocalState, plan: unexpectedPlan }); await flush();
    unexpected.replies.set('sync', request => ({ body: receiptMode === 'direct-plan' ? unexpectedPlan
      : { operation: { ...completedPush(request), status: 'needs_review', planId: unexpectedPlan.id } } }));
    await unexpected.elements.syncImages.click();
    assert.equal(unexpected.requests.filter(request => request.action === 'apply').length, 0, 'A primary push never adopts even an unexpected matching review-plan receipt');
  }
  const oldMainStorage = makeStorage(); oldMainStorage.localStorage = makeStorage();
  const oldMainOperation = { requestId: 'old-main-request', root: originalRoot, pageId: pageA, source: 'console', target: 'notion', status: 'needs_review', planId: addPlan.id };
  oldMainStorage.localStorage.setItem(`console-image-operation:${originalRoot}`, JSON.stringify({ ...oldMainOperation, uiMode: 'notion', autoApply: true }));
  const restoredMain = boot({ ...syncedLocalState, plan: addPlan, operation: oldMainOperation }, oldMainStorage); await flush();
  assert.equal(restoredMain.requests.filter(request => request.options.method === 'POST').length, 0, 'Restoring a main push cannot inherit an older automatic Inbox-adoption flag');
  const unconfiguredPush = boot(deviceState); await flush();
  await unconfiguredPush.elements.syncImages.click();
  assert.equal(unconfiguredPush.elements.notionSyncState.dataset.status, 'unavailable');
  assert.equal(unconfiguredPush.requests.filter(request => request.options.method === 'POST').length, 0, 'No Notion page must never fall back to local/self/device sync');
  await openAndEdit(unconfiguredPush); saveReply(unconfiguredPush, deviceSavedState);
  await unconfiguredPush.elements.metadataForm.emit('submit');
  assert.deepEqual(unconfiguredPush.requests.filter(request => request.options.method === 'POST').map(request => request.action), ['metadata'], 'A new save-and-sync job has only Notion as an external destination');
  assert.match(unconfiguredPush.elements.metadataStatus.textContent, /尚未配置 Notion/);
  const noFreshMarker = boot(syncedLocalState); await flush(); await openAndEdit(noFreshMarker);
  noFreshMarker.replies.set('metadata', { body: { ok: true, item: editedLogo, state: metadataSavedState } });
  await noFreshMarker.elements.metadataSaveOnly.click();
  assert.notEqual(noFreshMarker.elements.notionSyncState.dataset.status, 'synced', 'A successful local change without fresh provider evidence cannot retain an old green marker');
  const mainPending = boot(syncedLocalState); await flush(); let mainRequest;
  mainPending.replies.set('sync', request => { mainRequest = request; return { body: { operation: unknownReceipt(request) } }; });
  await mainPending.elements.syncImages.click();
  assert.equal(mainPending.elements.notionSyncState.dataset.status, 'failed');
  mainPending.elements.syncDirection.value = 'notion-to-console';
  mainPending.replies.set('operation', { body: unknownReceipt(mainRequest) });
  await mainPending.elements.syncImages.click();
  assert.equal(mainPending.requests.filter(request => request.action === 'sync').length, 1, 'An uncertain main push keeps its original request despite advanced-control changes');
  assert(mainPending.requests.findLast(request => request.action === 'operation').url.includes(mainRequest.body.requestId));
  assert.equal(mainPending.elements.syncDirection.value, 'console-to-notion', 'Checking locks the displayed original direction again');
  assert.equal(mainPending.elements.syncDirection.disabled, true);
  assert.equal(mainPending.elements.advancedSync.hidden, true, 'Legacy direction controls have no visible duplicate entry');
  assert.equal(mainPending.elements.deviceTransfer.open, undefined, 'Device transfer is a low-frequency collapsed utility');
  console.log('PASS Console and Notion sync: independent main direction, no self-sync fallback, Inbox excluded from publication, scoped verified fingerprints and text/color states, local-change invalidation, Notion-only new save jobs, and legacy device/multiple-target recovery.');
  const catalogUnknown = { id: 'existing-operation', requestId: 'existing-request-135', root: originalRoot, pageId: pageA, source: 'console', target: 'notion', status: 'unknown', code: 'catalog_attached_unverified', message: '目录已附页，待回读验证' };
  const recoveryState = { ...asyncInitial, plan: null, lastSync: null, notionPage: `https://www.notion.so/${pageA}`, notion: { canAttempt: true, pageId: pageA }, operation: catalogUnknown };
  const recovery = boot(recoveryState); await flush();
  assert.equal(recovery.requests.filter(request => request.action === 'sync').length, 0, 'Loading an unknown catalog request must never POST');
  assert.equal(recovery.elements.checkOperation.hidden, true);
  assert.equal(recovery.elements.syncImages.disabled, false);
  recovery.replies.set('operation', { body: catalogUnknown });
  recovery.replies.set('sync', request => { const completed = { ...catalogUnknown, status: 'completed', finishedAt: '2026-11-01T03:00:00Z', remainingTargets: [] }; recovery.setState({ ...recoveryState, operation: completed }); return { body: { operation: completed } }; });
  const startAt = recovery.requests.length;
  await recovery.elements.syncImages.click();
  assert.equal(recovery.requests[startAt].action, 'operation', 'Resume must first GET the old operation');
  const resumedPosts = recovery.requests.filter(request => request.action === 'sync');
  assert.equal(resumedPosts.length, 1);
  assert.deepEqual(resumedPosts[0].body, { expectedRoot: originalRoot, requestId: catalogUnknown.requestId, source: 'console', target: 'notion' }, 'Catalog verification must reuse the exact original request and scope');
  assert.equal(recovery.requests.filter(request => ['apply','upload'].includes(request.action)).length, 0);
  assert.notEqual(recovery.elements.lastSync.textContent, '尚无同步记录', 'Verified remote-only completion must count as a real sync');
  const ordinary = boot({ ...recoveryState, operation: { ...catalogUnknown, code: 'other_unknown' } }); await flush();
  ordinary.replies.set('operation', { body: { ...catalogUnknown, code: 'other_unknown' } });
  await ordinary.elements.syncImages.click();
  assert.equal(ordinary.requests.filter(request => request.action === 'sync').length, 0, 'Ordinary unknown operations must remain GET-only');
  for (const change of [{ root: 'D:\\Other Fixture' }, { pageId: pageB }, { source: 'notion' }, { target: 'all' }, { requestId: 'other-request' }]) {
    const scoped = boot(recoveryState); await flush();
    scoped.replies.set('operation', { body: { ...catalogUnknown, ...change } });
    await scoped.elements.syncImages.click();
    assert.equal(scoped.requests.filter(request => request.action === 'sync').length, 0, `Changed receipt scope must not resume: ${JSON.stringify(change)}`);
  }
  const changedPage = boot(recoveryState); await flush();
  changedPage.replies.set('operation', { body: catalogUnknown });
  changedPage.setState({ ...recoveryState, notionPage: `https://www.notion.so/${pageB}`, notion: { canAttempt: true, pageId: pageB } });
  await changedPage.elements.syncImages.click();
  assert.equal(changedPage.requests.filter(request => request.action === 'sync').length, 0, 'Changed configured page must reject old catalog resume');
  const changedDirection = boot(recoveryState); await flush();
  changedDirection.replies.set('operation', { body: catalogUnknown });
  changedDirection.elements.syncSource.value = 'local';
  await changedDirection.elements.syncImages.click();
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
    assert.equal(recheck.elements.checkOperation.hidden, true);
    assert.equal(recheck.elements.syncImages.disabled, false, 'The single main button explicitly checks positive public completion evidence');
    recheck.replies.set('operation', { body: verifiedPrior });
    recheck.replies.set('sync', request => { const done = { ...verifiedPrior, status: 'completed', finishedAt: '2026-11-01T04:00:00Z', remainingTargets: [] }; recheck.setState({ ...verifiedState, operation: done }); return { body: { operation: done } }; });
    await recheck.elements.syncImages.click();
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
  const mainMarkup = html.slice(html.indexOf('<div class="action-bar">'), html.indexOf('<p id="operationStatus"'));
  assert(mainMarkup.includes('id="syncDirection"') && mainMarkup.includes('id="syncImages"'));
  assert(!mainMarkup.includes('id="scanImages"') && !mainMarkup.includes('id="syncSource"') && !mainMarkup.includes('id="syncTarget"'), 'The main bar has no local/self/device or duplicate direction controls');
  const directionMarkup = html.match(/<select id="syncDirection"[^>]*>([\s\S]*?)<\/select>/)[1];
  assert.deepEqual([...directionMarkup.matchAll(/value="([^"]+)"/g)].map(match => match[1]), ['console-to-notion','notion-to-console']);
  assert(html.indexOf('id="scanImages"') > html.indexOf('<section class="collection-section"'), 'Refresh list belongs to the Console gallery utility');
  const mainPull = boot({ ...syncedLocalState, plan: null }); await flush();
  mainPull.elements.syncDirection.value = 'notion-to-console';
  const pullReview = { ...review, id: 'main-pull-review', planId: 'main-pull-review', root: originalRoot };
  mainPull.replies.set('sync', request => {
    const operation = { ...completedPush(request), source: 'notion', target: 'console', status: 'needs_review', planId: pullReview.id };
    mainPull.setState({ ...syncedLocalState, plan: pullReview, operation, notion: { ...syncedLocalState.notion, operation } });
    return { body: { operation } };
  });
  await mainPull.elements.syncImages.click();
  assert.equal(mainPull.requests.find(request => request.action === 'sync').body.source, 'notion');
  assert.equal(mainPull.requests.find(request => request.action === 'sync').body.target, 'console');
  assert.equal(mainPull.requests.filter(request => ['scan','apply'].includes(request.action)).length, 0, 'Main Notion readback shows conflicts without overwriting or scanning Console');
  assert.equal(mainPull.elements.notionSyncState.dataset.status, 'pending');
  assert.match(mainPull.elements.notionSyncState.textContent, /Console.*确认/);
  assert(!mainPull.elements.notionSyncState.textContent.includes('已同步到 Notion'), 'Pulling originals must not claim an upload fingerprint is verified');
  const deviceReadback = boot({ ...deviceState, plan: null }); await flush();
  deviceReadback.elements.deviceDirection.value = 'from-device';
  deviceReadback.replies.set('sync', { body: { id: 'device-read-empty', candidates: [], state: deviceState } });
  await deviceReadback.elements.transferDeviceImages.click();
  assert.equal(deviceReadback.requests.find(request => request.action === 'sync').body.source, 'device');
  assert.equal(deviceReadback.requests.find(request => request.action === 'sync').body.target, 'console');
  const missingUnknown = { ...catalogUnknown, id: 'missing-upload', requestId: 'missing-upload-request', code: 'upload_receipt_unresolved', recheckable: true, recheckKind: 'upload_receipt' };
  const missingOffer = { ...missingUnknown, status: 'failed', code: 'recovery_unavailable', recheckable: false, retryable: true, retryOf: missingUnknown.requestId, missingOriginals: [{ sha256: logoA.sha256, filename: logoA.path, blockedReceiptIds: ['old-piece'] }], message: '原图尚未确认附到此页，请独立重试。' };
  const missingState = { ...recoveryState, operation: missingUnknown };
  const missingView = boot(missingState); await flush();
  assert.equal(missingView.elements.syncImages.disabled, false);
  assert.equal(missingView.elements.syncDirection.disabled, true);
  assert.equal(missingView.elements.checkOperation.hidden, true);
  missingView.elements.syncDirection.value = 'notion-to-console';
  missingView.replies.set('operation', { body: missingUnknown });
  missingView.replies.set('sync', request => { assert.equal(request.body.requestId, missingUnknown.requestId); missingView.setState({ ...missingState, operation: missingOffer }); return { body: { operation: missingOffer } }; });
  await missingView.elements.syncImages.click();
  assert.deepEqual(missingView.requests.filter(request => request.options.method === 'POST').map(request => request.body), [{ expectedRoot: originalRoot, requestId: missingUnknown.requestId, source: 'console', target: 'notion' }], 'Check only reuses the original scope and ID; it does not authorize a new upload');
  assert.equal(missingView.elements.syncDirection.value, 'console-to-notion');
  assert.equal(missingView.elements.syncDirection.disabled, false, 'A confirmed missing-original offer does not keep Sync permanently locked');
  assert.match(missingView.elements.syncImages.textContent, /重试/);
  assert.equal(missingView.requests.filter(request => ['apply','upload'].includes(request.action)).length, 0);
  missingView.elements.syncDirection.value = 'notion-to-console';
  await missingView.elements.syncDirection.emit('change');
  missingView.replies.set('sync', request => {
    assert.equal(request.body.retryOf, undefined, 'Changing to Notion readback must never carry the push retry proof');
    const operation = { ...completedPush(request), source: 'notion', target: 'console' };
    missingView.setState({ ...missingState, operation, notion: { ...missingState.notion, operation } }); return { body: { operation } };
  });
  await missingView.elements.syncImages.click();
  missingView.elements.syncDirection.value = 'console-to-notion'; await missingView.elements.syncDirection.emit('change');
  missingView.replies.set('sync', request => {
    assert.notEqual(request.body.requestId, missingUnknown.requestId);
    assert.equal(request.body.retryOf, missingUnknown.requestId);
    const operation = completedPush(request); missingView.setState({ ...missingState, operation, notion: { ...missingState.notion, operation } }); return { body: { operation } };
  });
  await missingView.elements.syncImages.click();
  assert.equal(missingView.requests.filter(request => request.action === 'sync').length, 3, 'Only the later separate user click creates a retry request');
  assert(!missingView.elements.syncImages.textContent.includes('重试'), 'Successful retry retires the old offer');
  const saveWithOffer = boot({ ...metadataState, operation: missingOffer }); await flush(); await openAndEdit(saveWithOffer);
  saveReply(saveWithOffer, metadataSavedState); await saveWithOffer.elements.metadataForm.emit('submit');
  assert.deepEqual(saveWithOffer.requests.filter(request => request.options.method === 'POST').map(request => request.action), ['metadata'], 'Save and sync retains local edits but cannot authorize a missing-original retry offer');
  assert.match(saveWithOffer.elements.metadataStatus.textContent, /主同步/);
  assert.equal(saveWithOffer.elements.syncImages.textContent, '同步', 'Changing adopted metadata retires the old retry evidence');
  assert.match(saveWithOffer.elements.notionSyncHint.textContent, /依据已变化/);
  const rejectedRetry = boot({ ...recoveryState, operation: missingOffer }); await flush();
  rejectedRetry.replies.set('sync', { ok: false, status: 409, body: { code: 'retry_scope_changed', message: '重试依据已改变。' } });
  await rejectedRetry.elements.syncImages.click();
  const rejectedBody = rejectedRetry.requests.find(request => request.action === 'sync').body;
  assert.equal(rejectedBody.retryOf, missingOffer.requestId);
  assert.equal(rejectedRetry.elements.syncImages.textContent, '同步', 'A rejected retry offer must stop reusing the same invalid evidence');
  rejectedRetry.replies.set('sync', request => {
    assert.equal(request.body.retryOf, undefined, 'The next explicit Sync starts current-snapshot checking without the stale retry proof');
    assert.notEqual(request.body.requestId, rejectedBody.requestId);
    return { body: { operation: { ...missingUnknown, requestId: request.body.requestId } } };
  });
  await rejectedRetry.elements.syncImages.click();
  const persistedRejected = JSON.parse(rejectedRetry.storage.localStorage.getItem(`console-image-operation:${originalRoot}`));
  const rejectedReload = boot({ ...recoveryState, operation: { ...missingUnknown, requestId: persistedRejected.requestId } }, rejectedRetry.storage); await flush();
  // The current unknown request remains the only pending request after reload.
  assert.equal(rejectedReload.requests.filter(request => request.options.method === 'POST').length, 0);
  rejectedRetry.storage.localStorage.removeItem(`console-image-operation:${originalRoot}`);
  const staleOfferReload = boot({ ...recoveryState, operation: missingOffer }, rejectedRetry.storage); await flush();
  assert.equal(staleOfferReload.elements.syncImages.textContent, '同步', 'Reload must retain stale evidence rather than offering the same rejected retry again');
  assert.match(staleOfferReload.elements.notionSyncHint.textContent, /依据已变化/);
  for (const change of [{ recheckable: false }, { recheckKind: 'other' }]) {
    const noProbe = boot({ ...recoveryState, operation: { ...missingUnknown, ...change } }); await flush();
    noProbe.replies.set('operation', { body: { ...missingUnknown, ...change } }); await noProbe.elements.syncImages.click();
    assert.equal(noProbe.requests.filter(request => request.options.method === 'POST').length, 0, 'Missing receipt without the exact public read-only flag must remain GET-only');
  }
  console.log('PASS single Sync: exactly Console↔Notion, no local/device main target, gallery-only refresh, frozen same-request Check, conflict review on pull, low-frequency device transfer, explicit-only missing-original retry, no retryOf on pull/save, and stale-offer retirement without automatic work.');
  const namingTypes = [
    { code: 'GameIcon', label: '游戏图标', sizes: [{ width: 256, height: 256 }] },
    { code: 'PlaytestGameIcon', label: 'Playtest 图标', sizes: [{ width: 256, height: 256 }] },
    { code: 'HeaderCapsule', label: '商店横幅', sizes: [{ width: 920, height: 430 }] },
    { code: 'LibraryHeader', label: '库横幅', sizes: [{ width: 920, height: 430 }] },
    { code: 'EventCover', label: '活动封面', sizes: [{ width: 800, height: 450 }] },
    { code: 'Logo', label: 'Logo', sizes: [{ width: 1280, height: 720 }] },
    { code: 'TransparentLogo', label: '透明 Logo', sizes: [{ width: 1280, height: 720 }] }
  ];
  const standardIcon = { ...logoA, path: 'aaa story Final v9.png', width: 256, height: 256, groupTitle: 'GameIcon', groupId: 'game-icon', standardType: 'GameIcon', standardName: 'GameIcon_256x256.png', canonicalName: 'GameIcon_256x256.png', namingNeedsReview: false };
  const standardIconB = { ...standardIcon, id: logoB.id, sha256: logoB.sha256, assetId: logoB.assetId, variantId: logoB.variantId, variantLabel: logoB.variantLabel, path: 'Icon version 2.png' };
  const standardSmall = { ...standardIcon, id: logoSmall.id, sha256: logoSmall.sha256, assetId: logoSmall.assetId, variantId: logoSmall.variantId, path: 'Small Final.png', width: 64, height: 64, standardName: 'GameIcon_64x64.png', canonicalName: 'GameIcon_64x64.png', derivedFromId: standardIcon.sha256 };
  const standardTransparent = { ...togo, groupTitle: 'TransparentLogo', groupId: 'transparent-logo', standardType: 'TransparentLogo', standardName: 'TransparentLogo_1280x720.png', canonicalName: 'TransparentLogo_1280x720.png', namingNeedsReview: false };
  const standardState = { ...groupedState, items: [standardIcon, standardIconB, standardSmall, standardTransparent], standardNaming: true, standardTypes: namingTypes, plan: null, notionPage: '', deviceRoot: '' };
  const namingStartState = { ...standardState, standardNaming: false, plan: review };
  const expectedNames = ['Options/GameIcon/stable-option-a/GameIcon_256x256.png','Options/GameIcon/stable-option-b/GameIcon_256x256.png','GameIcon_64x64.png','TransparentLogo_1280x720.png'];
  const namingPreviewPlan = { id: 'standard-naming-preview', planId: 'standard-naming-preview', kind: 'naming', status: 'review', canApply: true, errors: [], candidates: standardState.items.map((item, index) => ({ id: `name-${index}`, source: item.path, target: expectedNames[index], fromPath: item.path, targetPath: expectedNames[index], assetType: item.standardType, standardName: item.standardName, width: item.width, height: item.height, sha256: item.sha256, variantLabel: item.variantLabel, status: 'rename' })) };
  const renamedItems = standardState.items.map((item, index) => ({ ...item, path: expectedNames[index] }));
  const renamedState = { ...standardState, items: renamedItems, plan: review, namingPlan: null, lastNaming: { planId: namingPreviewPlan.id } };
  const namingResults = namingPreviewPlan.candidates.map(candidate => ({ from: candidate.fromPath, to: candidate.targetPath, sha256: candidate.sha256 }));
  const arrange = boot(namingStartState); await flush();
  const selectedBeforeNaming = arrange.elements.candidateList.querySelectorAll('input').find(input => input.value === 'keep'); await selectedBeforeNaming.emit('change');
  await arrange.elements.organizeNames.click();
  assert.equal(arrange.elements.namingDialog.open, true); assert.equal(arrange.elements.namingList.children.length, 4);
  assert.equal(arrange.elements.namingApply.disabled, true, 'Naming requires a server preview before confirmation');
  assert.equal(arrange.requests.filter(request => request.options.method === 'POST').length, 0, 'Opening name organization does not rename or scan');
  arrange.replies.set('naming-plan', request => {
    assert.equal(request.body.expectedRoot, originalRoot);
    assert.deepEqual(request.body.entries, standardState.items.map(item => ({ path: item.path, sha256: item.sha256, assetType: item.standardType })));
    return { body: { ...namingPreviewPlan, state: { ...namingStartState, namingPlan: namingPreviewPlan } } };
  });
  await arrange.elements.namingPreview.click();
  assert.equal(arrange.elements.namingApply.disabled, false);
  assert(arrange.elements.namingList.children[1].querySelectorAll('p').some(element => element.textContent.includes(expectedNames[1])), 'Same-name alternatives use the backend Options directory without version or collision suffixes');
  assert.equal(arrange.elements.reviewCount.textContent, '1 项待确认');
  arrange.replies.set('naming-apply', { ok: false, status: 409, body: { error: '原图在预览后改变' } });
  await arrange.elements.namingApply.click();
  assert.equal(arrange.elements.namingApply.disabled, false, 'A failed confirmation retains the original preview and selected purposes');
  assert.equal(arrange.elements.namingList.querySelectorAll('select')[0].value, 'GameIcon');
  arrange.replies.set('naming-apply', () => { arrange.setState(renamedState); return { body: { ok: true, planId: namingPreviewPlan.id, renamed: 4, unchanged: 0, results: namingResults, state: renamedState } }; });
  await arrange.elements.namingApply.click();
  assert.equal(arrange.elements.namingRestore.hidden, false); assert.equal(arrange.elements.namingApply.disabled, true);
  assert.equal(arrange.elements.candidateList.querySelectorAll('input').find(input => input.value === 'keep').checked, true, 'Naming a library must not consume or reset the separate Inbox review');
  assert.deepEqual(arrange.requests.filter(request => request.options.method === 'POST').map(request => request.action), ['naming-plan','naming-apply','naming-apply']);
  assert.equal(renamedState.items[2].derivedFromId, standardSmall.derivedFromId);
  assert.equal(renamedState.items[1].variantId, standardIconB.variantId);
  arrange.replies.set('naming-restore', { ok: false, status: 409, body: { error: '文件已有后续修改，不能覆盖' } });
  await arrange.elements.namingRestore.click();
  assert.equal(arrange.elements.namingRestore.hidden, false);
  arrange.replies.set('naming-restore', { body: { ok: true, planId: namingPreviewPlan.id, restored: true, results: namingResults.map(result => ({ from: result.to, to: result.from, sha256: result.sha256 })), state: { ...namingStartState, lastNaming: null } } });
  await arrange.elements.namingRestore.click(); assert.equal(arrange.elements.namingRestore.hidden, true);
  assert.equal(arrange.elements.candidateList.querySelectorAll('input').find(input => input.value === 'keep').checked, true);
  for (const explicitNull of [true, false]) {
    const keepReview = boot(namingStartState); await flush();
    await keepReview.elements.candidateList.querySelectorAll('input').find(input => input.value === 'keep').emit('change');
    await keepReview.elements.organizeNames.click();
    keepReview.replies.set('naming-plan', { body: { ...namingPreviewPlan, state: namingStartState } }); await keepReview.elements.namingPreview.click();
    const afterNames = { ...renamedState }; if (explicitNull) afterNames.plan = null; else delete afterNames.plan;
    keepReview.replies.set('naming-apply', { body: { ok: true, planId: namingPreviewPlan.id, renamed: 4, results: namingResults, state: afterNames } });
    await keepReview.elements.namingApply.click();
    assert.equal(keepReview.elements.candidateList.querySelectorAll('input').find(input => input.value === 'keep').checked, true);
    assert.equal(keepReview.elements.reviewApply.disabled, explicitNull, 'Only an explicitly invalidated Inbox plan becomes stale; an omitted plan field must not invalidate it');
    if (explicitNull) {
      assert.match(keepReview.elements.decisionSummary.textContent, /名称已变化.*原选择已保留/);
      await keepReview.elements.reviewApply.click();
      assert.equal(keepReview.requests.filter(request => request.action === 'apply').length, 0);
      keepReview.replies.set('scan', { body: { ...review, id: 'fresh-after-name-change', state: renamedState } });
      await keepReview.elements.scanImages.click();
      await keepReview.elements.candidateList.querySelectorAll('input').find(input => input.value === 'keep').emit('change');
      assert.equal(keepReview.elements.reviewApply.disabled, false, 'An explicit new comparison clears the naming-stale gate');
    }
  }
  const pendingNaming = boot({ ...namingStartState, namingPlan: namingPreviewPlan }); await flush();
  await pendingNaming.elements.organizeNames.click(); assert.equal(pendingNaming.elements.namingApply.disabled, false, 'Reload can recover a matching persisted name preview without issuing a write');
  assert.equal(pendingNaming.requests.filter(request => request.options.method === 'POST').length, 0);
  const selectedPreview = { ...namingPreviewPlan, candidates: namingPreviewPlan.candidates.map((candidate, index) => index ? candidate : { ...candidate, assetType: 'PlaytestGameIcon', targetPath: 'PlaytestGameIcon_256x256.png', target: 'PlaytestGameIcon_256x256.png', standardName: 'PlaytestGameIcon_256x256.png' }) };
  const recoveredSelection = boot({ ...namingStartState, namingPlan: selectedPreview }); await flush(); await recoveredSelection.elements.organizeNames.click();
  assert.equal(recoveredSelection.elements.namingList.querySelector('select').value, 'PlaytestGameIcon', 'A persisted preview restores its explicit purpose even in a fresh browser session');
  assert.equal(recoveredSelection.elements.namingApply.disabled, false);
  const unknownNamingItem = { ...standardIcon, standardType: '', standardName: '', namingNeedsReview: true };
  const unknownNaming = boot({ ...namingStartState, items: [unknownNamingItem] }); await flush(); await unknownNaming.elements.organizeNames.click();
  assert.equal(unknownNaming.elements.namingPreview.disabled, true, 'Ambiguous purpose must be selected explicitly rather than inferred from dimensions');
  unknownNaming.elements.namingList.querySelector('select').value = 'PlaytestGameIcon'; await unknownNaming.elements.namingList.querySelector('select').emit('change');
  assert.equal(unknownNaming.elements.namingPreview.disabled, false);
  unknownNaming.replies.set('naming-plan', { ok: false, status: 409, body: { error: '预览未完成' } });
  await unknownNaming.elements.namingPreview.click(); assert.equal(unknownNaming.elements.namingList.querySelector('select').value, 'PlaytestGameIcon', 'Preview failures retain the chosen standard type');
  const conflictNaming = boot(namingStartState); await flush(); await conflictNaming.elements.organizeNames.click();
  conflictNaming.replies.set('naming-plan', { body: { ...namingPreviewPlan, canApply: false, errors: ['目标已被占用'], candidates: namingPreviewPlan.candidates.map((candidate, index) => index ? candidate : { ...candidate, status: 'conflict', error: '目标已被占用' }), state: namingStartState } });
  await conflictNaming.elements.namingPreview.click(); await conflictNaming.elements.namingApply.click();
  assert.equal(conflictNaming.elements.namingApply.disabled, true);
  assert.equal(conflictNaming.requests.filter(request => request.action === 'naming-apply').length, 0);
  const namingDraftLocation = boot(namingStartState); await flush(); namingDraftLocation.elements.deviceRoot.value = 'E:\\Unsaved Naming Location';
  await namingDraftLocation.elements.organizeNames.click(); assert.notEqual(namingDraftLocation.elements.namingDialog.open, true);
  assert.equal(namingDraftLocation.requests.filter(request => request.options.method === 'POST').length, 0);
  const busyNaming = boot(namingStartState); await flush(); await busyNaming.elements.organizeNames.click(); let completeNamingPreview;
  busyNaming.replies.set('naming-plan', () => new Promise(resolve => { completeNamingPreview = resolve; }));
  const namingInFlight = busyNaming.elements.namingPreview.click(); await flush();
  assert.equal(busyNaming.elements.imageGrid.attributes['aria-busy'], 'true');
  assert.equal(busyNaming.elements.namingClose.disabled, true); assert(busyNaming.elements.namingList.querySelectorAll('select').every(select => select.disabled));
  await busyNaming.elements.namingApply.click(); await busyNaming.elements.namingClose.click();
  assert.equal(busyNaming.elements.namingDialog.open, true); assert.equal(busyNaming.requests.filter(request => request.action === 'naming-apply').length, 0);
  completeNamingPreview({ body: { ...namingPreviewPlan, state: namingStartState } }); await namingInFlight;
  for (const changed of [{ root: 'D:\\Other Naming Root' }, { notionPage: `https://www.notion.so/${pageB}` }, { deviceRoot: 'E:\\Other Naming Device' }, { items: [{ ...standardIcon, sha256: 'changed' }, ...standardState.items.slice(1)] }]) {
    const lateNaming = boot(namingStartState); await flush(); await lateNaming.elements.organizeNames.click();
    lateNaming.replies.set('naming-plan', { body: { ...namingPreviewPlan, state: { ...namingStartState, ...changed } } });
    await lateNaming.elements.namingPreview.click(); assert.equal(lateNaming.elements.namingApply.disabled, true);
    assert.equal(lateNaming.requests.filter(request => request.action === 'naming-apply').length, 0);
  }
  for (const changed of [{ planId: 'other-naming-plan' }, { results: [{ ...namingResults[0], to: '../outside.png' }, ...namingResults.slice(1)] }, { results: namingResults.slice(1) }, { state: { ...renamedState, root: 'D:\\Other Receipt Root' } }, { state: { ...renamedState, items: renamedItems.map((item, index) => index ? item : { ...item, standardType: 'PlaytestGameIcon' }) } }, { state: { ...renamedState, items: renamedItems.map((item, index) => index ? item : { ...item, variantId: 'lost-original-variant' }) } }, { state: { ...renamedState, items: renamedItems.map((item, index) => index === 2 ? { ...item, derivedFromId: '' } : item) } }]) {
    const badNamingReceipt = boot(namingStartState); await flush(); await badNamingReceipt.elements.organizeNames.click();
    badNamingReceipt.replies.set('naming-plan', { body: { ...namingPreviewPlan, state: namingStartState } }); await badNamingReceipt.elements.namingPreview.click();
    badNamingReceipt.replies.set('naming-apply', { body: { ok: true, planId: namingPreviewPlan.id, renamed: 4, results: namingResults, state: renamedState, ...changed } });
    await badNamingReceipt.elements.namingApply.click();
    assert.equal(badNamingReceipt.elements.namingStatus.dataset.error, 'true');
    assert.equal(badNamingReceipt.elements.imageGrid.children[0].dataset.currentPath, standardIcon.path, 'A mismatched naming receipt cannot replace the current library');
  }
  const unknownInboxItem = { ...standardIcon, path: 'inbox/aaa.png', standardType: '', standardName: '', namingNeedsReview: true };
  const unknownInboxPlan = { id: 'unknown-inbox-type', candidates: [{ ...addPlan.candidates[0], id: 'untyped-inbox', incoming: unknownInboxItem }] };
  const unknownAdoption = boot({ ...standardState, plan: unknownInboxPlan }); await flush();
  assert.equal(unknownAdoption.elements.reviewApply.disabled, true); await unknownAdoption.elements.reviewApply.click();
  assert.equal(unknownAdoption.requests.filter(request => request.action === 'apply').length, 0);
  await unknownAdoption.elements.candidateList.querySelectorAll('input').find(input => input.value === 'keep').emit('change');
  assert.equal(unknownAdoption.elements.reviewApply.disabled, false, 'Keeping an untyped Inbox picture out does not require adopting a purpose');
  const standardSyncState = { ...standardState, deviceRoot: initialState.deviceRoot };
  const unknownAuto = boot(standardSyncState); await flush(); unknownAuto.replies.set('sync', { body: unknownInboxPlan });
  unknownAuto.elements.syncTarget.value = 'device';
  await unknownAuto.elements.transferDeviceImages.click(); assert.equal(unknownAuto.requests.filter(request => request.action === 'apply').length, 0, 'Standard-policy unknown files must never be auto-adopted');
  const knownSuggestion = { ...unknownInboxItem, width: 800, height: 450, standardType: 'EventCover', standardName: 'EventCover_800x450.png', canonicalName: 'EventCover_800x450.png', namingNeedsReview: false };
  const knownSuggestionPlan = { id: 'known-event-cover', candidates: [{ ...addPlan.candidates[0], incoming: knownSuggestion }] };
  const suggestedAuto = boot(standardSyncState); await flush(); suggestedAuto.replies.set('sync', { body: knownSuggestionPlan });
  suggestedAuto.elements.syncTarget.value = 'device';
  suggestedAuto.replies.set('apply', { body: { ok: true, state: standardState } }); await suggestedAuto.elements.transferDeviceImages.click();
  assert.equal(suggestedAuto.requests.filter(request => request.action === 'apply').length, 1, 'An already confirmed canonical type can retain the existing one-click synchronization behavior');
  const suggestionOnly = { ...knownSuggestion, standardType: '', suggestedStandardType: 'EventCover', namingNeedsReview: true };
  const suggestionOnlyPlan = { id: 'suggestion-needs-adoption', candidates: [{ ...addPlan.candidates[0], incoming: suggestionOnly }] };
  const explicitSuggestion = boot(standardSyncState); await flush(); explicitSuggestion.replies.set('sync', { body: suggestionOnlyPlan });
  explicitSuggestion.elements.syncTarget.value = 'device';
  explicitSuggestion.replies.set('apply', { body: { ok: true, state: standardState } }); await explicitSuggestion.elements.transferDeviceImages.click();
  assert.equal(explicitSuggestion.requests.filter(request => request.action === 'apply').length, 0, 'A size-only suggestion must never be automatically adopted by synchronization');
  assert.equal(explicitSuggestion.elements.reviewApply.disabled, false, 'The displayed Inbox-only suggestion can be accepted at the explicit adoption boundary');
  assert(explicitSuggestion.elements.candidateList.querySelectorAll('p').some(element => /建议用途 EventCover.*确认采用后.*EventCover_800x450/.test(element.textContent)));
  await explicitSuggestion.elements.reviewApply.click(); await flush();
  assert.equal(explicitSuggestion.requests.filter(request => request.action === 'apply').length, 1);
  assert.equal(explicitSuggestion.requests.filter(request => request.action === 'metadata').length, 0, 'Accepting a valid displayed Inbox suggestion does not require an extra metadata dialog');
  const indexedSuggestion = boot({ ...standardState, plan: { id: 'root-suggestion-not-adoption', candidates: [{ ...addPlan.candidates[0], incoming: { ...suggestionOnly, path: 'story v9.png' } }] } }); await flush();
  assert.equal(indexedSuggestion.elements.reviewApply.disabled, true, 'An indexed root story image cannot be treated as an approved type based only on its dimensions');
  const explicitMetadataSuggestion = boot({ ...standardState, items: [{ ...suggestionOnly, path: 'story v9.png' }] }); await flush();
  await explicitMetadataSuggestion.elements.imageGrid.querySelectorAll('button').find(button => button.dataset.metadataPath).click();
  assert.equal(explicitMetadataSuggestion.elements.metadataStandardType.value, 'EventCover');
  assert.equal(explicitMetadataSuggestion.elements.metadataSaveOnly.disabled, false, 'A visible suggested type remains an unsaved semantic choice until the user confirms it');
  assert.equal(explicitMetadataSuggestion.requests.filter(request => request.options.method === 'POST').length, 0);
  const rematched = boot({ ...standardState, plan: { id: 'same-plan-rematch', candidates: [{ ...candidate, id: 'changed-match', incoming: unknownInboxItem }, { ...addPlan.candidates[0], id: 'unaffected', incoming: { ...standardTransparent, path: 'inbox/Togo.png' } }] } }); await flush();
  await rematched.elements.candidateList.querySelectorAll('input').find(input => input.dataset.candidateId === 'changed-match' && input.value === 'replace').emit('change');
  await rematched.elements.candidateList.querySelectorAll('input').find(input => input.dataset.candidateId === 'unaffected' && input.value === 'keep').emit('change');
  await rematched.elements.candidateList.querySelectorAll('button').find(button => button.dataset.metadataPath === unknownInboxItem.path).click();
  assert.equal(rematched.elements.metadataGroupTitle.hidden, true); assert.equal(rematched.elements.metadataStandardType.hidden, false);
  rematched.elements.metadataStandardType.value = 'GameIcon'; await rematched.elements.metadataStandardType.emit('change');
  assert.match(rematched.elements.metadataStandardName.textContent, /GameIcon_256x256\.png/);
  const typedInbox = { ...unknownInboxItem, groupTitle: 'GameIcon', standardType: 'GameIcon', standardName: 'GameIcon_256x256.png', canonicalName: 'GameIcon_256x256.png', namingNeedsReview: false };
  const rebuiltPlan = { id: 'same-plan-rematch', candidates: [{ id: 'fresh-match', previousCandidateId: 'changed-match', status: 'new', incoming: typedInbox, actions: ['add','keep'] }, { ...addPlan.candidates[0], id: 'unaffected', incoming: { ...standardTransparent, path: 'inbox/Togo.png' } }] };
  rematched.replies.set('metadata', { body: { ok: true, item: typedInbox, planRebuilt: true, plan: rebuiltPlan, state: { ...standardState, plan: rebuiltPlan } } });
  await rematched.elements.metadataSaveOnly.click();
  assert.equal(rematched.requests.findLast(request => request.action === 'metadata').body.groupTitle, 'GameIcon');
  assert.equal(rematched.elements.candidateList.querySelectorAll('input').filter(input => input.dataset.candidateId === 'fresh-match' && input.checked).length, 0, 'A rematched new candidate cannot inherit replace or receive the new-file add default');
  assert.equal(rematched.elements.candidateList.querySelectorAll('input').find(input => input.dataset.candidateId === 'unaffected' && input.value === 'keep').checked, true);
  assert.equal(rematched.elements.reviewApply.disabled, true); assert.equal(rematched.requests.filter(request => ['apply','sync'].includes(request.action)).length, 0);
  const standardMetadataState = { ...standardState, notionPage: `https://www.notion.so/${pageA}`, notion: { canAttempt: true, pageId: pageA } };
  const renamedMetadataItem = { ...standardIcon, path: 'PlaytestGameIcon_256x256.png', groupTitle: 'PlaytestGameIcon', groupId: 'playtest-game-icon', standardType: 'PlaytestGameIcon', standardName: 'PlaytestGameIcon_256x256.png', canonicalName: 'PlaytestGameIcon_256x256.png' };
  const renamedMetadataState = { ...standardMetadataState, items: [renamedMetadataItem, ...standardState.items.slice(1)] };
  const renameMetadataReceipt = { ok: true, item: renamedMetadataItem, renamed: { from: standardIcon.path, to: renamedMetadataItem.path, sha256: standardIcon.sha256 }, state: renamedMetadataState };
  const editStandardType = async view => {
    await view.elements.imageGrid.querySelectorAll('button').find(button => button.dataset.metadataPath === standardIcon.path).click();
    view.elements.metadataStandardType.value = 'PlaytestGameIcon'; await view.elements.metadataStandardType.emit('change');
  };
  const metadataRename = boot(standardMetadataState); await flush(); await editStandardType(metadataRename);
  metadataRename.replies.set('metadata', () => { metadataRename.setState(renamedMetadataState); return { body: renameMetadataReceipt }; });
  metadataRename.replies.set('sync', request => ({ body: { operation: completedPush(request) } }));
  metadataRename.elements.syncSource.value = 'notion'; metadataRename.elements.syncTarget.value = 'console';
  await metadataRename.elements.metadataForm.emit('submit');
  assert.match(metadataRename.elements.metadataOriginal.textContent, /PlaytestGameIcon_256x256\.png/);
  assert.match(metadataRename.elements.metadataStatus.textContent, /已(?:保存，并|更新本地，并完成)同步/);
  assert.deepEqual(metadataRename.requests.filter(request => request.options.method === 'POST').map(request => request.action), ['metadata','sync'], 'An atomic purpose rename can save then push from the verified new path without applying Inbox work');
  assert.equal(metadataRename.requests.find(request => request.action === 'sync').body.source, 'console');
  assert.equal(metadataRename.elements.imageGrid.children.find(card => card.dataset.groupId === 'playtest-game-icon').dataset.currentPath, renamedMetadataItem.path, 'A canonical main-to-Playtest purpose change is reflected as its own group rather than another main-game option');
  assert.equal(metadataRename.elements.metadataSave.disabled, true, 'Verified rename completion must not leave a phantom dirty edit');
  const localRename = boot(standardMetadataState); await flush(); await editStandardType(localRename);
  localRename.replies.set('metadata', () => { localRename.setState(renamedMetadataState); return { body: renameMetadataReceipt }; });
  await localRename.elements.metadataSaveOnly.click(); await localRename.elements.metadataClose.click();
  const resumeRenamed = boot(renamedMetadataState, localRename.storage); await flush();
  await resumeRenamed.elements.imageGrid.querySelectorAll('button').find(button => button.dataset.metadataPath === renamedMetadataItem.path).click();
  assert.equal(resumeRenamed.elements.metadataSave.textContent, '同步已保存修改', 'A save-only purpose rename persists its pending sync against the verified new path');
  resumeRenamed.replies.set('sync', request => ({ body: { operation: completedPush(request) } })); await resumeRenamed.elements.metadataForm.emit('submit');
  assert.equal(resumeRenamed.requests.filter(request => request.action === 'metadata').length, 0);
  assert.equal(resumeRenamed.requests.filter(request => request.action === 'sync').length, 1);
  const indexedNameReview = boot({ ...standardMetadataState, plan: review }); await flush();
  await indexedNameReview.elements.candidateList.querySelectorAll('input').find(input => input.value === 'keep').emit('change');
  await editStandardType(indexedNameReview);
  indexedNameReview.replies.set('metadata', { body: { ...renameMetadataReceipt, state: { ...renamedMetadataState, plan: null } } });
  await indexedNameReview.elements.metadataSaveOnly.click();
  assert.equal(indexedNameReview.elements.reviewApply.disabled, true);
  assert.equal(indexedNameReview.elements.candidateList.querySelectorAll('input').find(input => input.value === 'keep').checked, true);
  assert.match(indexedNameReview.elements.decisionSummary.textContent, /名称已变化/);
  assert.deepEqual(indexedNameReview.requests.filter(request => request.options.method === 'POST').map(request => request.action), ['metadata'], 'An atomic indexed rename invalidates the old review without an automatic scan or apply');
  const realDimensionItem = { ...standardIcon, width: 333, height: 222, standardName: 'GameIcon_333x222.png', canonicalName: 'GameIcon_333x222.png' };
  const realDimensionView = boot({ ...standardState, items: [realDimensionItem] }); await flush();
  await realDimensionView.elements.imageGrid.querySelectorAll('button').find(button => button.dataset.metadataPath).click();
  assert.match(realDimensionView.elements.metadataStandardName.textContent, /GameIcon_333x222\.png/, 'Recommended Steam sizes must not replace the image\'s actual dimensions');
  assert.equal(realDimensionView.requests.filter(request => request.options.method === 'POST').length, 0);
  for (const changed of [{ renamed: undefined }, { renamed: { from: 'other.png', to: renamedMetadataItem.path, sha256: standardIcon.sha256 } }, { renamed: { from: standardIcon.path, to: renamedMetadataItem.path, sha256: 'other-sha' } }, { state: { ...renamedMetadataState, notionPage: `https://www.notion.so/${pageB}` } }, { state: { ...renamedMetadataState, items: [{ ...renamedMetadataItem, sha256: 'other-sha' }, ...standardState.items.slice(1)] } }]) {
    const badMetadataRename = boot(standardMetadataState); await flush(); await editStandardType(badMetadataRename);
    badMetadataRename.replies.set('metadata', { body: { ...renameMetadataReceipt, ...changed } });
    await badMetadataRename.elements.metadataForm.emit('submit');
    assert.equal(badMetadataRename.requests.filter(request => request.action === 'sync').length, 0, 'Only a matching old→new path/hash receipt may become the saved synchronization source');
    assert.equal(badMetadataRename.elements.metadataStandardType.value, 'PlaytestGameIcon');
    assert.equal(badMetadataRename.elements.metadataStatus.dataset.error, 'true');
  }
  const clipboardState = { ...groupedState, plan: null, inboxCount: 0, notionPage: `https://www.notion.so/${pageA}`, deviceRoot: 'E:\\Clipboard Fixture', limits: { maxFileBytes: 64 * 1024 * 1024 } };
  const pngBytes = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a0X0AAAAASUVORK5CYII=', 'base64');
  const clipboardPng = new Blob([pngBytes], { type: 'image/png' });
  const pngItem = { types: ['text/html','image/png','image/jpeg'], getType: async type => { assert.equal(type, 'image/png', 'Only one supported image representation is read per ClipboardItem'); return clipboardPng; } };
  const clipboardPlan = { id: 'clipboard-inbox-plan', candidates: [{ ...addPlan.candidates[0], id: 'pasted-image', incoming: { ...image, path: 'inbox/Clipboard.png' } }] };
  const postActions = view => view.requests.filter(request => request.options.method === 'POST').map(request => request.action);
  const nativePasteEvent = (target, files = [], items = []) => ({ target, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, clipboardData: { files, items, getData() { throw new Error('Plain text, HTML and URLs must not be read'); } } });
  const uploadedFile = view => view.requests.findLast(request => request.action === 'upload').body.fields.find(field => field[0] === 'files')[1];
  const installPasteUpload = view => view.replies.set('upload', () => { const next = { ...clipboardState, plan: clipboardPlan, inboxCount: 1 }; view.setState(next); return { body: { ...clipboardPlan, state: next } }; });
  const apiPaste = boot(clipboardState); await flush();
  assert.equal(apiPaste.clipboardReadCount(), 0, 'Loading Image must never read the OS clipboard');
  let typeReads = 0;
  apiPaste.setClipboardRead(async () => [{ ...pngItem, getType: async type => { typeReads++; return pngItem.getType(type); } }]);
  installPasteUpload(apiPaste);
  await apiPaste.elements.pasteImages.click();
  assert.equal(apiPaste.clipboardReadCount(), 1); assert.equal(typeReads, 1);
  assert.deepEqual(postActions(apiPaste), ['upload'], 'A paste command only stages an Inbox upload, without scan/apply/sync');
  assert.equal(apiPaste.requests.find(request => request.action === 'upload').body.fields.find(field => field[0] === 'expectedRoot')[1], originalRoot);
  assert.equal(uploadedFile(apiPaste).type, 'image/png');
  assert.match(uploadedFile(apiPaste).name, /^Clipboard-\d+-1\.png$/, 'Clipboard names are generated from the returned MIME rather than untrusted text or filenames');
  assert.deepEqual(Buffer.from(await uploadedFile(apiPaste).arrayBuffer()), pngBytes, 'The returned clipboard Blob is uploaded without canvas conversion');
  assert.equal(apiPaste.elements.reviewSection.hidden, false);
  assert.equal(apiPaste.elements.libraryCount.textContent, `${clipboardState.items.length} 张`, 'Staging a paste must not add it to the indexed library');
  const nativePaste = boot(clipboardState); await flush(); installPasteUpload(nativePaste);
  let asFileReads = 0;
  const copiedFile = new File([clipboardPng], '../untrusted:name.png', { type: 'image/png' });
  const sharedPaste = nativePasteEvent(nativePaste.elements.dropZone, [copiedFile], [{ kind: 'file', type: 'image/png', getAsFile() { asFileReads++; return copiedFile; } }]);
  await nativePaste.doc.emit('paste', sharedPaste);
  assert.equal(sharedPaste.defaultPrevented, true);
  assert.equal(asFileReads, 0, 'The files and items lists of the same paste event must not duplicate its image');
  assert.equal(nativePaste.clipboardReadCount(), 0, 'Native image paste does not invoke Clipboard API permissions');
  assert.deepEqual(postActions(nativePaste), ['upload']);
  assert.match(uploadedFile(nativePaste).name, /^Clipboard-\d+-1\.png$/);
  await nativePaste.doc.emit('paste', sharedPaste);
  assert.deepEqual(postActions(nativePaste), ['upload'], 'Re-dispatching the same handled paste event must not send it again');
  const itemPaste = boot(clipboardState); await flush(); installPasteUpload(itemPaste);
  const itemEvent = nativePasteEvent(itemPaste.elements.dropZone, [], [{ kind: 'file', type: 'image/png', getAsFile: () => copiedFile }, { kind: 'string', type: 'text/html', getAsString() { throw new Error('HTML must not be read'); } }]);
  await itemPaste.doc.emit('paste', itemEvent);
  assert.deepEqual(postActions(itemPaste), ['upload']); assert.equal(itemEvent.defaultPrevented, true);
  const focusedBodyPaste = boot(clipboardState); await flush(); installPasteUpload(focusedBodyPaste);
  focusedBodyPaste.doc.body.focus();
  const bodyImageEvent = nativePasteEvent(focusedBodyPaste.doc.body, [copiedFile]);
  await focusedBodyPaste.doc.emit('paste', bodyImageEvent);
  assert.deepEqual(postActions(focusedBodyPaste), ['upload'], 'Ctrl+V after clicking Image blank space must work when its own document is focused');
  const noFocusPaste = boot(clipboardState); await flush(); noFocusPaste.doc.body.focus(); noFocusPaste.setDocumentFocus(false);
  const noFocusEvent = nativePasteEvent(noFocusPaste.doc.body, [copiedFile]);
  await noFocusPaste.doc.emit('paste', noFocusEvent);
  await noFocusPaste.elements.pasteImages.click();
  assert.equal(noFocusEvent.defaultPrevented, false); assert.deepEqual(postActions(noFocusPaste), []); assert.equal(noFocusPaste.clipboardReadCount(), 0);
  const textPaste = boot(clipboardState); await flush();
  const textEvent = nativePasteEvent(textPaste.elements.dropZone, [], [{ kind: 'string', type: 'text/plain', getAsString() { throw new Error('Text must not be read'); } }]);
  await textPaste.doc.emit('paste', textEvent);
  assert.equal(textEvent.defaultPrevented, false); assert.deepEqual(postActions(textPaste), []);
  const textTargets = [textPaste.elements.libraryRoot, textPaste.elements.imageSearch, textPaste.doc.createElement('textarea'), textPaste.doc.createElement('select')];
  const editable = textPaste.doc.createElement('div'), editableChild = textPaste.doc.createElement('span');
  editable.setAttribute('contenteditable', 'true'); editable.append(editableChild); textTargets.push(editableChild);
  textPaste.doc.querySelector('.image-shell').append(...textTargets.filter(target => !target.parentElement), editable);
  for (const target of textTargets) {
    target.focus(); const fieldEvent = nativePasteEvent(target, [copiedFile]);
    await textPaste.doc.emit('paste', fieldEvent);
    assert.equal(fieldEvent.defaultPrevented, false, 'Inputs, textareas, selects and inherited contenteditable retain their normal paste');
  }
  for (const dialog of ['metadataDialog','previewDialog','namingDialog']) {
    textPaste.elements[dialog].open = true; textPaste.elements.dropZone.focus();
    const modalEvent = nativePasteEvent(textPaste.elements.dropZone, [copiedFile]);
    await textPaste.doc.emit('paste', modalEvent); await textPaste.elements.pasteImages.click();
    assert.equal(modalEvent.defaultPrevented, false); textPaste.elements[dialog].open = false;
  }
  assert.equal(textPaste.clipboardReadCount(), 0); assert.deepEqual(postActions(textPaste), []);
  const menuPaste = boot(clipboardState, makeStorage(), { height: 1200 }); await flush();
  const contextEvent = { target: menuPaste.elements.dropZone, clientX: 990, clientY: 1190, prevented: false, preventDefault() { this.prevented = true; } };
  await menuPaste.elements.dropZone.emit('contextmenu', contextEvent);
  assert.equal(menuPaste.elements.imagePasteMenu.hidden, false); assert.equal(menuPaste.clipboardReadCount(), 0);
  assert.equal(menuPaste.doc.activeElement, menuPaste.elements.imagePasteCommand);
  assert.equal(menuPaste.elements.imagePasteMenu.style['--image-paste-y'], '1190px');
  await menuPaste.doc.emit('keydown', { key: 'Escape', preventDefault() {} });
  assert.equal(menuPaste.elements.imagePasteMenu.hidden, true); assert.equal(menuPaste.doc.activeElement, menuPaste.elements.dropZone);
  await menuPaste.elements.dropZone.emit('contextmenu', contextEvent);
  await menuPaste.doc.emit('pointerdown', { target: menuPaste.elements.imageGrid });
  assert.equal(menuPaste.elements.imagePasteMenu.hidden, true);
  await menuPaste.elements.dropZone.emit('contextmenu', contextEvent); menuPaste.emitWindow('blur');
  assert.equal(menuPaste.elements.imagePasteMenu.hidden, true);
  await menuPaste.elements.dropZone.emit('contextmenu', contextEvent);
  menuPaste.sendContext({ channel: 'console-image-embed-v1', type: 'context', visibleTop: 900, visibleHeight: 280 });
  assert.equal(menuPaste.elements.imagePasteMenu.hidden, true, 'A host visible-window change closes an open paste menu');
  assert.equal(menuPaste.embedStyles['--image-embed-visible-top'], '900px');
  await menuPaste.elements.dropZone.emit('contextmenu', contextEvent);
  menuPaste.setClipboardRead(async () => { assert.equal(menuPaste.doc.hasFocus(), true); assert.equal(menuPaste.doc.activeElement, menuPaste.elements.dropZone, 'Closing the menu keeps focus in the Image document before clipboard.read'); return [pngItem]; });
  installPasteUpload(menuPaste); await menuPaste.elements.imagePasteCommand.click();
  assert.equal(menuPaste.elements.imagePasteMenu.hidden, true); assert.deepEqual(postActions(menuPaste), ['upload']);
  const cssSource = fs.readFileSync(resolve(projectRoot, 'image-manager.css'), 'utf8');
  assert(cssSource.includes('.image-paste-menu { position: fixed;') && cssSource.includes('top: clamp(calc(var(--image-embed-visible-top') && cssSource.includes('var(--image-embed-visible-height, 100vh)'), 'Paste menu must clamp to the host-visible iframe area rather than its full document height');
  for (const [items, message] of [
    [[{ types: ['text/plain','text/html'], getType() { throw new Error('Nonimage data must not be read'); } }], /没有可用图片/],
    [[{ types: ['image/svg+xml'], getType() { throw new Error('Unsupported image must not be read'); } }], /格式暂不支持/],
    [[{ types: ['image/png'], getType: async () => new Blob([], { type: 'image/png' }) }], /图片为空/],
    [[{ types: ['image/png'], getType: async () => ({ type: 'image/png', size: 64 * 1024 * 1024 + 1 }) }], /64 MiB/],
    [[{ types: ['image/png'], getType: async () => ({ type: 'image/png', size: 50 * 1024 * 1024 }) }, { types: ['image/png'], getType: async () => ({ type: 'image/png', size: 50 * 1024 * 1024 }) }], /96 MiB/],
    [Array.from({ length: 51 }, () => pngItem), /最多加入 50 张/],
    [[{ types: ['image/png'], getType: async () => new Blob(['wrong'], { type: 'text/html' }) }], /格式未能确认/]
  ]) {
    const rejectedPaste = boot(clipboardState); await flush(); rejectedPaste.setClipboardRead(async () => items);
    await rejectedPaste.elements.pasteImages.click();
    assert.deepEqual(postActions(rejectedPaste), []); assert.match(rejectedPaste.elements.operationStatus.textContent, message);
    assert.equal(rejectedPaste.elements.pasteImages.disabled, false);
  }
  const deniedPaste = boot(clipboardState); await flush(); deniedPaste.setClipboardRead(async () => { throw new Error('NotAllowedError'); });
  await deniedPaste.elements.pasteImages.click();
  assert.match(deniedPaste.elements.operationStatus.textContent, /Ctrl\+V.*拖入/); assert.deepEqual(postActions(deniedPaste), []);
  installPasteUpload(deniedPaste);
  await deniedPaste.doc.emit('paste', nativePasteEvent(deniedPaste.elements.dropZone, [copiedFile]));
  assert.deepEqual(postActions(deniedPaste), ['upload'], 'Native Ctrl+V remains available after a direct clipboard permission failure');
  const unsupportedClipboard = boot(clipboardState); await flush(); unsupportedClipboard.disableClipboardRead();
  await unsupportedClipboard.elements.pasteImages.click();
  assert.match(unsupportedClipboard.elements.operationStatus.textContent, /Ctrl\+V.*拖入/); assert.equal(unsupportedClipboard.clipboardReadCount(), 0); assert.deepEqual(postActions(unsupportedClipboard), []);
  const pendingPasteEvent = nativePasteEvent(pendingBrowse.elements.dropZone, [copiedFile]);
  await pendingBrowse.doc.emit('paste', pendingPasteEvent); await pendingBrowse.elements.pasteImages.click();
  assert.equal(pendingPasteEvent.defaultPrevented, false); assert.equal(pendingBrowse.clipboardReadCount(), 0);
  assert.deepEqual(postActions(pendingBrowse), ['sync'], 'An existing unknown request keeps paste disabled without reading or uploading');
  const draftLocationPaste = boot(clipboardState); await flush(); draftLocationPaste.elements.deviceRoot.value = 'E:\\Unsaved Paste Target';
  await draftLocationPaste.elements.pasteImages.click();
  assert.equal(draftLocationPaste.clipboardReadCount(), 0); assert.deepEqual(postActions(draftLocationPaste), []); assert.match(draftLocationPaste.elements.operationStatus.textContent, /先保存位置/);
  for (const change of [{ root: 'D:\\Other Paste Root' }, { deviceRoot: 'E:\\Other Device' }, { notionPage: `https://www.notion.so/${pageB}` }, { plan: { id: 'other-review', candidates: [] } }, { operation: { status: 'running', requestId: 'other-request' } }, { operation: { status: 'unknown', requestId: 'unknown-request' } }]) {
    const lateRead = boot(clipboardState); await flush(); let releaseRead;
    lateRead.setClipboardRead(() => new Promise(resolve => { releaseRead = resolve; }));
    const reading = lateRead.elements.pasteImages.click(); await flush();
    assert.equal(lateRead.elements.imageGrid.attributes['aria-busy'], 'true', 'The clipboard permission/read wait must protect automatic reload');
    lateRead.setState({ ...clipboardState, ...change }); releaseRead([pngItem]); await reading;
    assert.deepEqual(postActions(lateRead), [], 'Changed root/device/page/plan or a newly pending operation rejects a delayed clipboard image');
    assert.match(lateRead.elements.operationStatus.textContent, /已改变.*取消粘贴/);
  }
  const localDraftDuringRead = boot(clipboardState); await flush(); let finishLocalRead;
  localDraftDuringRead.setClipboardRead(() => new Promise(resolve => { finishLocalRead = resolve; }));
  const delayedLocalRead = localDraftDuringRead.elements.pasteImages.click(); await flush();
  localDraftDuringRead.elements.libraryRoot.value = 'D:\\Changed Input During Permission'; finishLocalRead([pngItem]); await delayedLocalRead;
  assert.deepEqual(postActions(localDraftDuringRead), []);
  const delayedBlobPaste = boot(clipboardState); await flush(); let finishBlob;
  delayedBlobPaste.setClipboardRead(async () => [{ types: ['image/png'], getType: () => new Promise(resolve => { finishBlob = resolve; }) }]);
  const delayedBlobRead = delayedBlobPaste.elements.pasteImages.click(); await flush();
  delayedBlobPaste.setState({ ...clipboardState, deviceRoot: 'E:\\Changed During Blob Read' }); finishBlob(clipboardPng); await delayedBlobRead;
  assert.deepEqual(postActions(delayedBlobPaste), [], 'A delayed ClipboardItem.getType result receives the same configuration checks as clipboard.read');
  const racePaste = boot(clipboardState); await flush(); installPasteUpload(racePaste); let finishApiRead;
  racePaste.setClipboardRead(() => new Promise(resolve => { finishApiRead = resolve; }));
  const apiRead = racePaste.elements.pasteImages.click(); await flush();
  assert.equal(racePaste.elements.pasteImages.disabled, true);
  const overlappingEvent = nativePasteEvent(racePaste.elements.dropZone, [copiedFile]);
  await racePaste.doc.emit('paste', overlappingEvent); await racePaste.elements.pasteImages.click();
  assert.equal(overlappingEvent.defaultPrevented, false, 'Busy paste handling must not intercept another native event');
  assert.equal(racePaste.clipboardReadCount(), 1); finishApiRead([pngItem]); await apiRead;
  assert.deepEqual(postActions(racePaste), ['upload'], 'Clipboard API and paste-event overlap must not double-stage an image');
  const failedPaste = boot(clipboardState); await flush(); failedPaste.setClipboardRead(async () => [pngItem]);
  failedPaste.replies.set('upload', { ok: false, status: 409, body: { error: 'root_changed' } });
  await failedPaste.elements.pasteImages.click();
  assert.equal(failedPaste.elements.libraryRoot.value, originalRoot); assert.equal(failedPaste.elements.pasteImages.disabled, false);
  assert.deepEqual(postActions(failedPaste), ['upload']);
  const lateUpload = boot(clipboardState); await flush(); lateUpload.setClipboardRead(async () => [pngItem]); let finishUpload;
  lateUpload.replies.set('upload', () => new Promise(resolve => { finishUpload = resolve; }));
  const uploadInFlight = lateUpload.elements.pasteImages.click(); await flush();
  finishUpload({ body: { ...clipboardPlan, state: { ...clipboardState, root: 'D:\\Different Receipt Root', inboxCount: 9, plan: clipboardPlan } } }); await uploadInFlight;
  assert.equal(lateUpload.elements.libraryRoot.value, originalRoot);
  assert.equal(lateUpload.elements.reviewSection.hidden, true, 'A late upload receipt for another root cannot replace the current Inbox');
  assert.equal(lateUpload.elements.inboxCount.textContent, 'inbox 0');
  const indexSource = fs.readFileSync(resolve(projectRoot, 'index.html'), 'utf8');
  const hostSource = fs.readFileSync(resolve(projectRoot, 'app.js'), 'utf8');
  assert(indexSource.includes('id="steamworkImageTitle">Image</h3>'));
  assert(indexSource.includes('data-src="image-manager.html?embed=steamwork"'));
  for (const id of ['imageManagerOpen','steamworkAssetList','steamworkAssetRoot','steamworkAssetSummary','steamworkAssetFileInput']) assert(!indexSource.includes(`id="${id}"`), `Removed checklist/extra entry must stay absent: ${id}`);
  assert(!indexSource.includes('href="image-manager.html"'), 'Primary Image experience must not be an extra standalone link');
  assert(html.includes('href="/steamwork.html"'), 'Standalone compatibility page must return to the actual Image host');
  const eightPlan = { ...addPlan, candidates: Array.from({ length: 8 }, (_, i) => ({ ...addPlan.candidates[0], id: `inbox-${i}`, incoming: { ...image, groupId: `purpose-${i}`, groupTitle: `用途 ${i + 1}`, path: `inbox/new-${i}.png` } })) };
  const embeddedApp = boot({ ...groupedState, plan: eightPlan, inboxCount: 8 }, makeStorage(), { height: 600 }); await flush();
  assert.equal(embeddedApp.doc.documentElement.dataset.embed, 'steamwork');
  assert.equal(embeddedApp.elements.reviewSection.dataset.expanded, 'false', 'Restored Inbox must not push the primary gallery below eight review cards');
  assert.equal(embeddedApp.elements.candidateList.children.length, 8, 'Collapsing reviews must preserve the real plan');
  assert.equal(embeddedApp.elements.imageGrid.children.length, 2);
  assert.equal(embeddedApp.elements.imageGrid.children.find(card => card.dataset.groupId === 'transparent-logo').querySelectorAll('button').filter(button => button.dataset.variantNavigate).length, 0, 'A single option needs neither arrows nor a redundant thumbnail');
  assert.equal(embeddedApp.elements.imageGrid.children.find(card => card.dataset.groupId === 'logo').querySelectorAll('button').filter(button => button.dataset.variantNavigate).length, 2, 'All real alternative options must remain switchable');
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
  const frameFields = { metadataDialog: { open: false }, namingDialog: { open: false }, locations: { open: false }, imageGrid: { getAttribute: () => 'false' } };
  draftFrame = { getAttribute: () => 'image-manager.html?embed=steamwork', contentDocument: { getElementById: id => frameFields[id] } };
  assert.equal(draftContext.steamworkImageHasDraft(), false);
  frameFields.metadataDialog.open = true; assert.equal(draftContext.steamworkImageHasDraft(), true);
  frameFields.metadataDialog.open = false; frameFields.namingDialog.open = true; assert.equal(draftContext.steamworkImageHasDraft(), true);
  frameFields.namingDialog.open = false; frameFields.locations.open = true; assert.equal(draftContext.steamworkImageHasDraft(), true);
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
  console.log('PASS save-and-sync: dirty/no-op gating, save-only/reopen/reload, fixed Console authority, no Inbox import/publish, failed-save draft, unsaved-location guard, root/page/device/asset/annotation late-result refusal, same-request unknown verification, partial-target retry, and device metadata-only/new/review completion.');
  console.log('PASS option arrows: three real originals cycle with pointer and scoped keyboard/focus, no single-image arrows or thumbnail duplication, explicit size/lineage and main/Playtest grouping retained, Inbox choices persist per candidate through browsing/reload/full-plan confirmation, unsafe buckets stay separate, and busy browsing is zero-write.');
  console.log('PASS paste images: explicit-only image ClipboardItem/native files/items, one MIME per item and event/API de-duplication, safe MIME filenames and unchanged returned Blob bytes, Inbox-only upload, body-focus and text/modal boundaries, menu dismissal/iframe-visible clamp, no text/HTML/URL reads, permission fallback, size/empty/format guards, and late root/device/page/plan/pending-operation rejection. No OS clipboard is accessed by fixtures.');
  console.log('PASS standard naming: explicit canonical types and real dimensions, independent library preview/apply/restore with Options alternatives and preserved Inbox choices, failed/late/conflicting receipt protection, unknown adoption gating and unique backend suggestions, rematched candidate-only reselection, verified metadata old→new path migration before Console sync, saved pending rename recovery, busy/modal/reload protection, and legacy compatibility.');
})().catch(error => { console.error(error); process.exitCode = 1; });
