// Fake DOM checks for local image rendering; no browser or network requests.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

class Element {
  constructor(tag = 'span') { this.tagName = tag.toUpperCase(); this.children = []; this.listeners = {}; this._text = ''; this.classes = new Set(); this.classList = { add: value => this.classes.add(value) }; }
  appendChild(child) { this.children.push(child); return child; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  addEventListener(name, callback) { this.listeners[name] = callback; }
}
function extract(source, name) {
  const start = source.indexOf(`function ${name}(`);
  assert(start >= 0, `Missing function ${name}`);
  const end = source.slice(start + 1).search(/\n\s*(?:async )?function /);
  return source.slice(start, end < 0 ? undefined : start + 1 + end);
}
const descendants = element => [element, ...element.children.flatMap(descendants)];
const document = { createElement: tag => new Element(tag), createTextNode: text => { const element = new Element('#text'); element.textContent = text; return element; } };
const window = { location: { origin: 'http://127.0.0.1:8899' } };
const readerHtml = readFileSync(new URL('../reader.html', import.meta.url), 'utf8');
const policy = readerHtml.match(/http-equiv="Content-Security-Policy" content="([^"]+)"/)?.[1];
assert(policy, 'Reader must retain its content security policy');
assert.equal(policy.split(';').map(item => item.trim()).find(item => item.startsWith('img-src ')), "img-src 'self'", 'Reader policy must allow only local image sources');
for (const standalone of [false, true]) {
  const source = readFileSync(new URL(standalone ? '../document-reader.js' : '../app.js', import.meta.url), 'utf8');
  const context = { document, window, URL, state: { root: 'D:/library', path: 'reports/gallery.md' }, documentLibrary: { root: 'D:/library', file: 'reports/gallery.md' }, text: zh => zh, documentText: zh => zh };
  const names = standalone ? ['libraryPath', 'appendImage', 'appendInline'] : ['documentRelativePath', 'appendDocumentImage', 'appendDocumentInline'];
  runInNewContext(names.map(name => extract(source, name)).join('\n'), context);
  const render = markdown => { const parent = new Element('p'); context[names.at(-1)](parent, markdown); return parent; };
  const valid = render('![电梯](../images/%E7%94%B5%E6%A2%AF.png)');
  const image = descendants(valid).find(element => element.tagName === 'IMG');
  assert(image, 'Library image must produce real img pixels');
  const url = new URL(image.src);
  assert.equal(url.origin, window.location.origin);
  assert.equal(url.pathname, '/api/documents/image');
  assert.equal(url.searchParams.get('path'), 'images/电梯.png');
  assert.equal(url.searchParams.get('expectedRoot'), 'D:/library');
  assert.equal(image.alt, '电梯');
  assert.equal(image.loading, 'lazy');
  assert.equal(image.decoding, 'async');
  const anchor = descendants(valid).find(element => element.tagName === 'A');
  assert.equal(anchor.href, image.src);
  assert.equal(anchor.target, '_blank');
  assert(anchor.rel.includes('noopener'));
  for (const target of ['https://outside.test/private.png', '//outside.test/private.png', 'file:///C:/private.png', 'data:image/png,xx', '/private.png', 'C:\\private.png', '../../private.png', '../images/x.png?key=1', '../images/x.png#part', '%00x.png', '%ZZx.png', 'x.svg']) {
    const rejected = render(`![Unavailable](${target})`);
    assert(!descendants(rejected).some(element => element.tagName === 'IMG'), `Must not fetch ${target}`);
    assert(rejected.textContent.includes('Unavailable'));
  }
  assert(!descendants(render('`![Example](../images/电梯.png)`')).some(element => element.tagName === 'IMG'), 'Code must remain text');
  image.listeners.error();
  assert(valid.textContent.includes('1 MiB'), 'Missing/oversize image must explain failure');
}
console.log('PASS embedded and standalone document images: actual local img, selected root, encoded paths, full-size links, lazy loading, no URL/traversal fetches, code and clear failure');
