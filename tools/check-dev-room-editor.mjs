import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const require = createRequire(import.meta.url);
const editor = require('../dev-room-editor.js');
const source = readFileSync(new URL('../dev-room-editor.js', import.meta.url), 'utf8');
const identity = '{"id":"project-introduction","guid":"cf983df9a9ce17a45a8cc3e108eae281"}';
function fixture({ newline = '\n', title = 'Project Nexus 项目介绍 😀', summary = '概要\r\n第二行  \t\n',
  sections = [{ title: '第一章', body: '第一行\r\n自然 # 标题\n## 正文里的标题\n末尾空白  \t\n\n' },
    { title: '第二章', body: '英文 English 与 中文 🚀\r\n\r\n' }] } = {}) {
  let result = `<!-- rr-dev-room:v1 ${identity} -->${newline}# ${title}${newline}${newline}`;
  result += `<!-- rr-dev-room:summary -->${newline}${summary}${newline}<!-- rr-dev-room:summary-end -->${newline}${newline}`;
  sections.forEach((section, index) => {
    result += `<!-- rr-dev-room:section ${index} -->${newline}## ${section.title}${newline}${section.body}${newline}<!-- rr-dev-room:section-end ${index} -->${newline}${newline}`;
  });
  return result;
}
let checks = 0;
function check(name, action) { action(); checks++; console.log(`PASS ${name}`); }
const markdown = fixture();

check('CommonJS and browser global expose the same pure API', () => {
  assert.deepEqual(Object.keys(editor).sort(), ['catalog', 'parse', 'present', 'serialize']);
  const browser = {}; runInNewContext(source, browser);
  assert.equal(typeof browser.CodexDevRoomEditor.parse, 'function');
  assert.equal(typeof browser.CodexDevRoomEditor.present, 'function');
  assert.equal(typeof browser.CodexDevRoomEditor.catalog, 'function');
  assert.equal(browser.CodexDevRoomEditor.serialize(markdown, browser.CodexDevRoomEditor.parse(markdown)), markdown);
});
check('Unicode, mixed content newlines and trailing whitespace round-trip exactly', () => {
  const model = editor.parse(markdown);
  assert.equal(model.title, 'Project Nexus 项目介绍 😀');
  assert.equal(model.summary, '概要\r\n第二行  \t\n');
  assert.equal(model.sections[0].body, '第一行\r\n自然 # 标题\n## 正文里的标题\n末尾空白  \t\n\n');
  assert.equal(editor.serialize(markdown, model), markdown);
});
check('CRLF structural markers and plain CR inside text are retained', () => {
  const original = fixture({ newline: '\r\n', summary: '摘要\r独立回车  ', sections: [{ title: '章节', body: '正文\r\n\r尾白\t  \r\n' }] });
  const model = editor.parse(original);
  assert.equal(model.source.newline, '\r\n');
  assert.equal(model.sections[0].body, '正文\r\n\r尾白\t  \r\n');
  assert.equal(editor.serialize(original, model), original);
});
check('title editing changes only editable text', () => {
  const model = editor.parse(markdown); model.title = '新标题 🎮';
  assert.equal(editor.serialize(markdown, model), markdown.replace('# Project Nexus 项目介绍 😀\n', '# 新标题 🎮\n'));
});
check('summary and individual section editing preserve all other fields', () => {
  const model = editor.parse(markdown); model.summary += '新增摘要'; model.sections[1].body = '新正文\r\n  \t\n';
  const changed = editor.parse(editor.serialize(markdown, model));
  assert.equal(changed.summary, model.summary);
  assert.deepEqual(changed.sections[0], editor.parse(markdown).sections[0]);
  assert.equal(changed.sections[1].body, model.sections[1].body);
});
check('incomplete empty fields remain recoverable drafts', () => {
  const model = editor.parse(markdown); model.title = ''; model.summary = '';
  model.sections.forEach(section => { section.title = ''; section.body = ''; });
  const blank = editor.serialize(markdown, model), restored = editor.parse(blank);
  assert.deepEqual(restored, model);
  assert.equal(editor.serialize(blank, restored), blank);
});
check('section count and stable index order cannot change', () => {
  let model = editor.parse(markdown); model.sections.pop(); assert.throws(() => editor.serialize(markdown, model), /count/);
  model = editor.parse(markdown); model.sections.push({ index: 2, title: '新节', body: '' }); assert.throws(() => editor.serialize(markdown, model), /count/);
  model = editor.parse(markdown); model.sections.reverse(); assert.throws(() => editor.serialize(markdown, model), /order/);
  model = editor.parse(markdown); model.sections[0].index = '0'; assert.throws(() => editor.serialize(markdown, model), /order/);
  model = editor.parse(markdown); delete model.sections[0]; assert.throws(() => editor.serialize(markdown, model), /fields/);
});
check('source id, GUID, newline and unsupported asset fields cannot be edited', () => {
  for (const key of ['id', 'guid', 'newline']) {
    const model = editor.parse(markdown); model.source = { ...model.source, [key]: 'different' };
    assert.throws(() => editor.serialize(markdown, model), /source identity/);
  }
  const model = editor.parse(markdown); model.sections[0].imageGuid = 'different';
  assert.throws(() => editor.serialize(markdown, model), /fields/);
  const textOnly = editor.parse(markdown); delete textOnly.source;
  assert.equal(editor.serialize(markdown, textOnly), markdown);
});
check('reserved marker injection is rejected in every editable field', () => {
  for (const change of [model => { model.title = '<!-- rr-dev-room:v1 forged -->'; },
    model => { model.summary += '<!-- rr-dev-room:summary-end -->'; },
    model => { model.sections[0].title = '<!-- rr-dev-room:section 2 -->'; },
    model => { model.sections[0].body += '<!-- rr-dev-room:section-end 0 -->'; }]) {
    const model = editor.parse(markdown); change(model);
    assert.throws(() => editor.serialize(markdown, model), /reserved/);
  }
});
check('natural headings and ordinary HTML comments stay inside their section', () => {
  const model = editor.parse(markdown); model.sections[0].body = '# natural heading\n## another\n<!-- ordinary comment -->\n';
  const restored = editor.parse(editor.serialize(markdown, model));
  assert.equal(restored.sections.length, 2); assert.equal(restored.sections[0].body, model.sections[0].body);
});
check('invalid markers, swapped indices and unrecognized trailing content are rejected', () => {
  for (const invalid of [markdown.replace('rr-dev-room:v1', 'rr-dev-room:v2'), markdown.replace('summary-end -->', 'summary-end BAD -->'),
    markdown.replace('section 0 -->', 'section 1 -->'), markdown.replace('section-end 0 -->', 'section-end 1 -->'),
    markdown + 'extra', markdown.replace(identity, '{"id":"../escape","guid":"bad"}'),
    markdown.replace('## 第一章\n', '## 第一章\t\n')]) assert.throws(() => editor.parse(invalid));
});
check('heading newlines, invalid Unicode, controls and size limits reject safely', () => {
  for (const invalid of ['two\nlines', 'two\rline', 'tab\ttitle', '\ud800', '\udc00', '\0', 'x'.repeat(201)]) {
    const model = editor.parse(markdown); model.title = invalid; assert.throws(() => editor.serialize(markdown, model));
  }
  let model = editor.parse(markdown); model.summary = 'x'.repeat(65537); assert.throws(() => editor.serialize(markdown, model), /size/);
  model = editor.parse(markdown); model.sections[0].body = 'x'.repeat(512 * 1024 + 1); assert.throws(() => editor.serialize(markdown, model), /size/);
  assert.throws(() => editor.parse('x'.repeat(2 * 1024 * 1024 + 1)), /size/);
});
check('original source header formatting remains byte-for-byte unchanged', () => {
  const original = markdown.replace(identity, '{ "guid": "cf983df9a9ce17a45a8cc3e108eae281", "id": "project-introduction" }');
  const model = editor.parse(original); model.title = '新标题';
  assert.equal(editor.serialize(original, model).split('\n')[0], original.split('\n')[0]);
});
check('escaped final newlines in source identities cannot evade full matching', () => {
  for (const invalid of [{ id: 'project-introduction\n', guid: 'cf983df9a9ce17a45a8cc3e108eae281' },
    { id: 'project-introduction', guid: 'cf983df9a9ce17a45a8cc3e108eae281\n' }]) {
    assert.throws(() => editor.parse(markdown.replace(identity, JSON.stringify(invalid))), /identity/);
  }
});
check('canonical presentation hides machine markers while retaining human title, summary and section prose', () => {
  const view = editor.present(markdown);
  assert.equal(view.canonical, true);
  assert.equal(view.title, 'Project Nexus 项目介绍 😀');
  assert.equal(view.source.id, 'project-introduction');
  assert.equal(view.source.guid, 'cf983df9a9ce17a45a8cc3e108eae281');
  assert.equal(view.technical.length, 0);
  assert.ok(view.body.startsWith('# Project Nexus 项目介绍 😀\n'));
  assert.ok(view.body.includes('## 第一章\n'));
  assert.ok(view.body.includes('正文里的标题'));
  assert.ok(!view.body.includes('rr-dev-room'));
  assert.ok(!view.body.includes(view.source.guid));
  assert.equal(editor.serialize(markdown, editor.parse(markdown)), markdown);
});
check('only explicit References, Sources and Agent details move to technical sections; Risks remain human prose', () => {
  const original = fixture({ sections: [
    { title: 'Risks', body: 'Risks and dependencies remain visible.\nAssets/does-not-make-it-technical.asset' },
    { title: 'References', body: 'Assets/Scripts/Building.cs\nhttps://example.org/design' },
    { title: 'Sources', body: 'Reference research and provenance.' },
    { title: 'Agent 资料', body: 'GUID 与接口说明。' },
    { title: 'References and risks', body: 'This title is not an exact technical title.' },
    { title: 'C#', body: 'Literal heading punctuation remains human.' },
    { title: '风险', body: '风险正文保持显示。' },
  ] });
  const view = editor.present(original);
  assert.deepEqual(view.technical.map(({ index, title }) => ({ index, title })), [
    { index: 1, title: 'References' }, { index: 2, title: 'Sources' }, { index: 3, title: 'Agent 资料' },
  ]);
  assert.ok(view.technical[0].body.includes('Assets/Scripts/Building.cs'));
  assert.ok(view.technical[0].body.includes('https://example.org/design'));
  assert.ok(view.body.includes('Risks and dependencies remain visible.'));
  assert.ok(view.body.includes('Assets/does-not-make-it-technical.asset'));
  assert.ok(view.body.includes('References and risks'));
  assert.ok(view.body.includes('风险正文保持显示。'));
  assert.ok(view.body.includes('## C#'));
  assert.equal(editor.serialize(original, editor.parse(original)), original);
});
check('explicit Reference labels move only their own block, never the surrounding human section', () => {
  const original = fixture({ sections: [{ title: 'Current status',
    body: 'Current build works.\n\nReference: Assets/Scripts/First.cs\nAssets/Scripts/Second.cs\n\nRisks: preserve this prose.\nNext human paragraph.' }] });
  const view = editor.present(original);
  assert.equal(view.technical.length, 1);
  assert.equal(view.technical[0].index, null);
  assert.equal(view.technical[0].title, 'Reference');
  assert.equal(view.technical[0].body, 'Assets/Scripts/First.cs\nAssets/Scripts/Second.cs');
  assert.ok(view.body.includes('Current build works.'));
  assert.ok(view.body.includes('Risks: preserve this prose.'));
  assert.ok(view.body.includes('Next human paragraph.'));
  assert.ok(!view.body.includes('First.cs'));
});
check('nested human headings end technical scope and cannot hide Risks under Sources', () => {
  const original = fixture({ sections: [{ title: 'Sources',
    body: 'Assets/Reference.cs\n### Risks\nThis human risk remains visible.\n## Consequences\nRead this too.' }] });
  const view = editor.present(original);
  assert.deepEqual(view.technical, [{ index: null, title: 'Sources', body: 'Assets/Reference.cs' }]);
  assert.ok(view.body.includes('### Risks\nThis human risk remains visible.'));
  assert.ok(view.body.includes('## Consequences\nRead this too.'));
  const fallback = editor.present('# Document\n## Sources\npath\n### Risks\nVisible\n## References#\nAlso visible');
  assert.ok(fallback.body.includes('### Risks\nVisible'));
  assert.ok(fallback.body.includes('## References#\nAlso visible'));
});
check('broken markers retain readable prose without leaking IDs, GUIDs or claiming canonical identity', () => {
  for (const broken of [markdown.replace('section-end 0 -->', 'section-end 7 -->'),
    markdown.replace('summary-end -->', 'summary-end'),
    markdown.replace(identity, '{"id":"../forged","guid":"cf983df9a9ce17a45a8cc3e108eae281"}'),
    markdown.replace('rr-dev-room:v1', 'rr-dev-room:v2')]) {
    const view = editor.present(broken);
    assert.equal(view.canonical, false);
    assert.equal(view.source, null);
    assert.ok(view.body.includes('第一行'));
    assert.ok(view.body.includes('第二章'));
    assert.ok(!view.body.includes('rr-dev-room'));
    assert.ok(!view.body.includes('cf983df9a9ce17a45a8cc3e108eae281'));
    assert.throws(() => editor.parse(broken));
  }
  const incomplete = '# Guide\n<!-- rr-dev-room:v1 {\n"id": "bad",\n"guid": "cf983df9a9ce17a45a8cc3e108eae281"\n} -->\nReadable human prose';
  const view = editor.present(incomplete);
  assert.ok(view.body.includes('Readable human prose'));
  assert.ok(!view.body.includes('cf983df9a9ce17a45a8cc3e108eae281'));
});
check('ordinary complete comments hide in reading while fenced and inline literal examples remain exact text', () => {
  const original = '# Guide\nBefore <!-- private comment --> after\n<!-- multiline\nprivate -->\n' +
    '`<!-- ordinary code comment -->`\n``<!-- two-backtick code -->``\n\\<!-- escaped literal -->\n' +
    '```html\n<!-- rr-dev-room:v1 literal-GUID -->\n<!-- ordinary comment -->\nReferences: a code example\n```\nHuman ending';
  const view = editor.present(original);
  assert.equal(view.technical.length, 0);
  assert.ok(view.body.includes('Before  after'));
  assert.ok(!view.body.includes('private comment'));
  assert.ok(!view.body.includes('multiline'));
  assert.ok(view.body.includes('`<!-- ordinary code comment -->`'));
  assert.ok(view.body.includes('``<!-- two-backtick code -->``'));
  assert.ok(view.body.includes('\\<!-- escaped literal -->'));
  assert.ok(view.body.includes('<!-- rr-dev-room:v1 literal-GUID -->'));
  assert.ok(view.body.includes('References: a code example'));
  assert.ok(view.body.includes('Human ending'));
});
check('longer and tilde fences protect nested fake headings, comments and catalog links', () => {
  const nested = '# Guide\n````md\n```\n## References\n<!-- rr-dev-room:v1 code example -->\n```\nStill outer code\n````\n' +
    '~~~\n## Sources\n~~~ not a closing fence\nReference: still code\n~~~\nRisk prose';
  const view = editor.present(nested);
  assert.equal(view.technical.length, 0);
  assert.ok(view.body.includes('<!-- rr-dev-room:v1 code example -->'));
  assert.ok(view.body.includes('Reference: still code'));
  assert.ok(view.body.includes('Risk prose'));
  assert.deepEqual(editor.catalog(nested), []);
});
check('unclosed fences and indented literal metadata are preserved rather than erased', () => {
  const original = '# Guide\n    <!-- rr-dev-room:v1 literal -->\n\tReferences: literal\n```\n## References\n<!-- rr-dev-room:literal -->';
  const view = editor.present(original);
  assert.equal(view.technical.length, 0);
  assert.ok(view.body.includes('    <!-- rr-dev-room:v1 literal -->'));
  assert.ok(view.body.includes('## References\n<!-- rr-dev-room:literal -->'));
});
check('URLs, code and XSS-looking strings stay inert string data without HTML or link construction', () => {
  const content = '<script>globalThis.xss = true</script>\n<img src=x onerror=alert(1)>\n' +
    '[unsafe](javascript:alert(1))\n[web](https://example.org/?a=1&b=2)\n' +
    '`const html = "<img onerror=alert(1)>"`\n## Risks\nKeep the warning';
  const view = editor.present(content);
  assert.equal(view.body, content);
  assert.equal(view.source, null);
  assert.equal(typeof view.body, 'string');
  assert.ok(!source.includes('innerHTML'));
  assert.ok(!source.includes('document.createElement'));
  assert.ok(!source.includes('fetch('));
});
check('catalog preserves original group names, document order and escaped labels without new classification', () => {
  const first = '00112233-4455-6677-8899-aabbccddeeff', second = '11223344-5566-7788-99aa-bbccddeeff00';
  const content = '# Dev Room\n## Project Overview\nDescription\n- [First\\] document](' + first + '.md)\n' +
    '## C#\n- [Second](' + second + '.md)\n- [Duplicate](' + first + '.md)';
  assert.deepEqual(editor.catalog(content), [{ id: first, group: 'Project Overview' }, { id: second, group: 'C#' }]);
  assert.deepEqual(editor.catalog(content, [second]), [{ id: second, group: 'C#' }]);
});
check('catalog excludes unknown syntax, malicious paths, images, code examples and links to unavailable documents', () => {
  const id = '00112233-4455-6677-8899-aabbccddeeff';
  const content = '# Dev Room\n- [Ungrouped](' + id + '.md)\n## Technical\n' +
    '- [Unknown](not-a-document.md)\n- [Path](../' + id + '.md)\n- [Web](https://example.org/' + id + '.md)\n' +
    '- [Query](' + id + '.md?x=1)\n- [Script](javascript:alert(1))\n![](image.md)\n' +
    '`- [Inline](' + id + '.md)`\n```\n- [Fenced](' + id + '.md)\n```\n' +
    '    - [Indented](' + id + '.md)\n<!-- - [Comment](' + id + '.md) -->\n- [Real](' + id + '.md)';
  assert.deepEqual(editor.catalog(content), [{ id, group: 'Technical' }]);
  assert.deepEqual(editor.catalog(content, []), []);
  assert.throws(() => editor.catalog(content, 'invalid'), /identities/);
});
check('presentation and catalog remain bounded and reject invalid text without mutating originals', () => {
  for (const value of [null, {}, '\ud800', '\0', 'x'.repeat(2 * 1024 * 1024 + 1)]) {
    assert.throws(() => editor.present(value));
    assert.throws(() => editor.catalog(value));
  }
  const original = fixture({ sections: [{ title: 'References', body: 'Assets/Source.cs' }, { title: 'Risks', body: 'Human prose' }] });
  const copy = original;
  editor.present(original); editor.catalog(original);
  assert.equal(original, copy);
  assert.equal(editor.serialize(original, editor.parse(original)), original);
});
console.log(`PASS ${checks} Dev Room editor checks`);
