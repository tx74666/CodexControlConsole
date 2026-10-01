import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const main = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
function extract(name, async = false) {
  const start = main.indexOf(`${async ? 'async ' : ''}function ${name}(`);
  assert(start >= 0, `Missing ${name}`);
  const after = main.slice(start + 1).search(/\n(?:async )?function /);
  return main.slice(start, after < 0 ? undefined : start + 1 + after);
}
let opened = 0, focused = 0, embedded = 0, fallbackVisible = false;
let popup = null;
const context = {
  URL, URLSearchParams,
  documentLibrary: { root: 'D:\\资料\\阅读', exists: true },
  window: { location: { href: 'http://127.0.0.1:12345/workspace.html?edition=public' }, open(url, name, features) {
    opened++;
    assert.equal(name, 'codex-console-document-reader');
    assert(features.includes('popup'));
    popup = { closed: false, location: { href: url }, focus() { focused++; } };
    return popup;
  } },
  withDocumentAction: async action => { await action(); return true; },
  readDocumentFile: async () => { embedded++; },
  showDocumentResources: (view, options) => { fallbackVisible = view === 'ai' && options.load === false; },
  documentNode: () => ({ focus() {}, scrollIntoView() {} }),
  documentNotice() {}, documentText: zh => zh
};
runInNewContext(`let documentReadingWindow = null;\n${extract('openDocumentReaderUrl')}\n${extract('openDocumentReadingWindow')}\n${extract('openDocumentInboxEntry', true)}`, context);
const report = { id: 'report-1', path: 'reports/正文 & ?#.md' };
await context.openDocumentInboxEntry(report);
assert.equal(opened, 1);
assert.equal(embedded, 0);
assert.equal(new URL(popup.location.href).searchParams.get('path'), report.path);
assert.equal(new URL(popup.location.href).searchParams.get('root'), context.documentLibrary.root);
await context.openDocumentInboxEntry(report);
assert.equal(opened, 1, 'same report must focus the existing reader');
assert.equal(focused, 2);
popup.focus = () => { throw new Error('foreground denied'); };
await context.openDocumentInboxEntry(report);
assert.equal(opened, 1, 'foreground denial must not reopen the existing reader');
await context.openDocumentInboxEntry({ id: 'report-2', path: 'reports/two.md' });
assert.equal(opened, 2, 'another report should navigate the named reading window');
popup.closed = true;
context.window.open = () => null;
await context.openDocumentInboxEntry(report);
assert.equal(embedded, 1, 'blocked popup must retain accessible inline reading');
assert.equal(fallbackVisible, true, 'blocked popup must expose the inline reader in the AI records dialog');
assert(!extract('openDocumentInboxEntry', true).includes('inbox/read'), 'opening must never mark read');
console.log('PASS independent reader opening, reuse, URL encoding and popup fallback');
