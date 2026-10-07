import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, statSync } from 'node:fs';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const editor = require('../dev-room-editor.js');
const bundlePath = new URL('../dev-room-translations.json', import.meta.url);
const maxBundleBytes = 2 * 1024 * 1024;
const maxBodyBytes = 512 * 1024;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const sha256 = /^[0-9a-f]{64}$/;

// This small manifest describes the imported document identities and existing
// catalog order. The regression never opens a user's library or Unity project.
const manifest = [
  ['5a2f7164-82b3-5f01-91bb-b72b2202e0ef', 'project-current-build', 'efe3e17261f9ae741bd4648121b7376a', 5],
  ['05107322-018a-57df-ac6e-0b51d4e097d8', 'project-vision-direction', 'c8fa1f6f4522b054da9f76f8978042c4', 5],
  ['9cc6013f-8125-5572-b053-940aab1c4512', 'project-introduction', 'cf983df9a9ce17a45a8cc3e108eae281', 3],
  ['7730018c-9934-588b-b167-ea5d5a334d23', 'project-devs-realm-introduction', '83931ff95de2bcc469e03d9ecb20b54f', 3],
  ['ca5722d6-fb8b-5b04-bfb7-871dce492ce1', 'gameplay-adventure', '9586db3ea00ffd346ae2b384f0e08aa3', 5],
  ['e0b1ef39-c71b-50f9-b9b4-50885af0bc74', 'gameplay-combat-ai', '1484b0cf4e83e264e971ba21ef83c20f', 5],
  ['f19c6044-2d41-598f-bf99-0b0460c67c88', 'gameplay-mini-games', 'ce527c9744f4e6f46a67e53f254c7a34', 5],
  ['400d6ffa-dc2c-5fab-b263-1575dd9ccf79', 'systems-building', '83b60b176680be243bd367698a34a60a', 5],
  ['210e611a-6140-5179-b657-c73326123ede', 'systems-multiplayer', '1f82c204173b1304987501f78944cf48', 5],
  ['a1449a49-ad79-5c70-abcb-bc50f9ce6428', 'systems-ui-ux', '4c866fcf7aec3264bab86571bc65c144', 5],
  ['46fd3ac4-ed17-5b3f-8fec-6ccfcc99dff9', 'systems-building-introduction', '708783b64723e0c4e9c43769097f7920', 3],
  ['352c027b-1baa-5528-bb22-e41816d1ae19', 'content-art-direction', '4b48479a36f4c714898cec889f6ac45e', 5],
  ['21db724d-5152-532f-882b-bd930125fb28', 'content-audio', '0f3ac82d370a9974b8e2de38ca2ad4d1', 5],
  ['874770de-3215-5d72-8029-67f18ce45126', 'technical-architecture', '3225b8bb3abc4b7489502bcb4b2c6601', 5],
  ['4cd87dfd-0918-51d3-9150-75eee2b6662a', 'technical-tools', '117f8341130869f479f6cbfa675dc9c0', 5],
  ['98f13021-cd45-5c0b-a205-6a38fb523397', 'technical-asset-pipeline', 'c6f6a8eed9ae87043ad7254fe81c7d18', 5],
];
const originallyChinese = new Set(manifest.filter(item => item[3] === 3).map(item => item[0]));
const expectedTitles = {
  zh: ['当前版本', '愿景与方向', '项目概览', '开发者空间', '冒险模式', '战斗与敌人智能', '小游戏',
    '建造系统', '多人联机', '界面与交互体验', '建造系统', '美术方向', '音频', '架构', '工具', '资产制作流程'],
  en: ['Current Build', 'Vision & Direction', 'Project Overview', "Dev's Realm", 'Adventure', 'Combat & AI', 'Mini-games',
    'Building', 'Multiplayer', 'UI / UX', 'Building System', 'Art Direction', 'Audio', 'Architecture', 'Tools', 'Asset Pipeline'],
};
const expectedGroups = {
  zh: ['项目概览', '游戏玩法', '系统', '内容', '技术'],
  en: ['Project Overview', 'Gameplay', 'Systems', 'Content', 'Technical'],
};
const forbiddenEnglishHeadings = new Set([
  'Overview', 'Current State', 'Target', 'Risks', 'References', 'Project Overview', 'Gameplay', 'Systems', 'Content', 'Technical',
]);
const cjk = /[\u3400-\u9fff]/u;
const allowedChineseProseIdentifiers = new Set(['Random', 'Realm', 'Project', 'Nexus', 'Unity', 'Blender', 'API', 'GUID', 'C']);

function exactKeys(value, keys) {
  assert(value && typeof value === 'object' && !Array.isArray(value), 'schema object required');
  assert.deepEqual(Object.keys(value).sort(), [...keys].sort(), 'unexpected or missing schema key');
}
function boundedText(value, maximum, heading = false) {
  assert.equal(typeof value, 'string', 'text must be a string');
  assert(value.length > 0, 'text must not be empty');
  assert(Buffer.byteLength(value, 'utf8') <= maximum, 'text exceeds byte bound');
  assert(!/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/u.test(value), 'text contains control character');
  assert(!/[\ud800-\udfff]/u.test(value), 'text contains unpaired surrogate');
  if (heading) assert([...value].length <= 200 && !/[\r\n\t]/u.test(value), 'invalid title');
}
function validateSchema(value) {
  exactKeys(value, ['version', 'documents']);
  assert.equal(value.version, 1, 'unsupported schema version');
  assert(Array.isArray(value.documents) && value.documents.length <= 128, 'document count exceeds bound');
  const seen = new Set();
  for (const doc of value.documents) {
    exactKeys(doc, ['id', 'sourceTitle', 'sourceBodySha256', 'variants']);
    assert(typeof doc.id === 'string' && (doc.id === 'overview' || uuid.test(doc.id)), 'invalid document id');
    assert(!seen.has(doc.id), 'duplicate document id'); seen.add(doc.id);
    boundedText(doc.sourceTitle, 1024, true);
    assert(typeof doc.sourceBodySha256 === 'string' && sha256.test(doc.sourceBodySha256), 'invalid source SHA256');
    exactKeys(doc.variants, ['zh', 'en']);
    for (const language of ['zh', 'en']) {
      exactKeys(doc.variants[language], ['title', 'body']);
      boundedText(doc.variants[language].title, 1024, true);
      boundedText(doc.variants[language].body, maxBodyBytes);
    }
  }
  assert(Buffer.byteLength(JSON.stringify(value), 'utf8') <= maxBundleBytes, 'bundle exceeds byte bound');
}
function records(value) { return new Map(value.documents.map(doc => [doc.id, doc])); }
function canonicalModels(value) {
  const byId = records(value), models = new Map();
  for (const [id, sourceId, guid, sectionCount] of manifest) {
    const doc = byId.get(id); assert(doc, 'known document missing');
    const pair = {};
    for (const language of ['zh', 'en']) {
      const variant = doc.variants[language], model = editor.parse(variant.body);
      assert.equal(model.title, variant.title, 'reader and editable title disagree');
      assert.equal(model.source.id, sourceId, 'source identity changed');
      assert.equal(model.source.guid, guid, 'source GUID changed');
      assert.equal(model.sections.length, sectionCount, 'section omitted or added');
      assert.deepEqual(model.sections.map(section => section.index), Array.from({ length: sectionCount }, (_, index) => index));
      assert(model.summary.trim().length > 10, 'summary omitted');
      assert(model.sections.every(section => section.title.trim() && section.body.trim().length > 10), 'section text omitted');
      assert.equal(editor.serialize(variant.body, model), variant.body, 'canonical text cannot round-trip exactly');
      pair[language] = model;
    }
    assert.deepEqual(pair.zh.source, pair.en.source, 'languages disagree about source identity');
    const markers = body => body.match(/<!-- rr-dev-room:[^\r\n]+/gu);
    assert.deepEqual(markers(doc.variants.zh.body), markers(doc.variants.en.body), 'source or ordered markers differ');
    assert.equal(editor.serialize(doc.variants.zh.body, pair.en), doc.variants.en.body, 'language switch changes canonical scaffold');
    models.set(id, pair);
  }
  return models;
}
function chineseProse(value) {
  // Only actual inline code and link destinations are exempt; all prose and
  // headings remain checked. Product names and established API acronyms stay literal.
  const prose = value.replace(/`+[^`\n]+`+/gu, '').replace(/\[([^\]\n]+)\]\([^\n)]*\)/gu, '$1');
  const words = prose.match(/[A-Za-z][A-Za-z0-9_.'-]*/gu) || [];
  for (const word of words) assert(allowedChineseProseIdentifiers.has(word), `untranslated Chinese prose word: ${word}`);
}
function assertHumanLanguages(value) {
  for (const doc of value.documents) {
    for (const language of ['zh', 'en']) {
      const variant = doc.variants[language], view = editor.present(variant.body);
      assert.equal(view.title, doc.id === 'overview' ? (language === 'zh' ? '开发文档室' : 'Dev Room') : variant.title);
      if (language === 'en') {
        assert(!cjk.test(variant.title + '\n' + view.body), 'English human prose contains Chinese');
      } else {
        assert(cjk.test(variant.title), 'Chinese title missing');
        chineseProse(view.body);
        for (const heading of view.body.matchAll(/^#{1,6}\s+([^\n]+)$/gmu)) {
          assert(!forbiddenEnglishHeadings.has(heading[1]), 'English section heading remains in Chinese');
        }
      }
      assert(!view.body.includes('rr-dev-room:'), 'reader leaks canonical metadata');
    }
  }
}
function overviewLinks(body) {
  return [...body.matchAll(/^- \[([^\]\n]+)\]\(([0-9a-f-]{36})\.md\)$/gmu)].map(match => ({ label: match[1], id: match[2] }));
}

let checks = 0;
function check(name, action) { action(); checks++; console.log(`PASS ${name}`); }
assert(statSync(bundlePath).size <= maxBundleBytes, 'translation bundle exceeds read bound');
const raw = readFileSync(bundlePath);
assert(raw.length <= maxBundleBytes, 'translation bundle exceeds read bound');
const bundle = JSON.parse(raw.toString('utf8'));

check('bounded catalog schema has exactly 17 identities and 34 complete variants', () => {
  validateSchema(bundle);
  assert.equal(bundle.documents.length, 17);
  assert.deepEqual([...records(bundle).keys()].sort(), ['overview', ...manifest.map(item => item[0])].sort());
  assert.equal(bundle.documents.reduce((sum, doc) => sum + Object.keys(doc.variants).length, 0), 34);
});
let models;
check('both languages retain all 74 sections, source identities, GUIDs and ordered markers', () => {
  models = canonicalModels(bundle);
  for (const language of ['zh', 'en']) {
    assert.equal([...models.values()].reduce((sum, pair) => sum + pair[language].sections.length, 0), 74);
  }
});
check('13 existing English sources remain byte exact against their stored source SHA256', () => {
  for (const doc of bundle.documents) {
    if (doc.id === 'overview' || originallyChinese.has(doc.id)) continue;
    assert.equal(createHash('sha256').update(doc.variants.en.body, 'utf8').digest('hex'), doc.sourceBodySha256);
  }
});
check('all 13 reference sections are preserved and collapsed in both languages without leaking paths', () => {
  const byId = records(bundle);
  for (const [id, , , count] of manifest) {
    if (count !== 5) continue;
    const pair = models.get(id);
    assert.equal(pair.zh.sections[4].title, '参考资料');
    assert.equal(pair.en.sections[4].title, 'References');
    assert.equal(pair.zh.sections[4].body, pair.en.sections[4].body);
    for (const language of ['zh', 'en']) {
      const view = editor.present(byId.get(id).variants[language].body);
      assert.equal(view.technical.length, 1);
      assert.equal(view.technical[0].index, 4);
      assert.equal(view.technical[0].title, pair[language].sections[4].title);
      assert.equal(view.technical[0].body.trim(), pair[language].sections[4].body.trim());
      for (const path of pair[language].sections[4].body.trim().split('\n')) {
        assert(!view.body.includes(path), 'technical reference path leaked into reader');
      }
      assert(view.body.includes(pair[language].sections[3].body), 'Risks prose was hidden with references');
    }
  }
});
check('English human prose has no Chinese and Chinese human prose has no untranslated ordinary English', () => {
  assertHumanLanguages(bundle);
});
check('overview keeps all 16 original link targets and order with complete language-specific labels and five groups', () => {
  const byId = records(bundle), overview = byId.get('overview');
  assert.equal(overview.variants.zh.title, '总案');
  assert.equal(overview.variants.en.title, 'Overview');
  for (const language of ['zh', 'en']) {
    const body = overview.variants[language].body, links = overviewLinks(body);
    assert.equal(links.length, 16);
    assert.deepEqual(links.map(item => item.id), manifest.map(item => item[0]));
    assert.deepEqual(links.map(item => item.label), expectedTitles[language]);
    for (const link of links) assert.equal(link.label, byId.get(link.id).variants[language].title);
    const groups = editor.catalog(body, manifest.map(item => item[0]));
    assert.deepEqual(groups.map(item => item.id), links.map(item => item.id));
    assert.deepEqual([...new Set(groups.map(item => item.group))], expectedGroups[language]);
    const headings = [...body.matchAll(/^## ([^\n]+)\n\n([^\n]+)$/gmu)];
    assert.equal(headings.length, 5);
    assert(headings.every(match => match[2].trim().length > 10), 'group description omitted');
    assert(!/\]\((?:https?:|javascript:|file:|\.\.)/iu.test(body), 'unexpected external or traversal catalog link');
  }
});
check('duplicate ids, missing languages, unknown keys, invalid hashes and unsafe ids are rejected', () => {
  const mutations = [
    copy => { copy.documents[1].id = copy.documents[0].id; },
    copy => { delete copy.documents[0].variants.en; },
    copy => { copy.documents[0].variants.fr = copy.documents[0].variants.en; },
    copy => { copy.documents[0].variants.zh.extra = 'unexpected'; },
    copy => { copy.documents[0].sourceBodySha256 = 'A'.repeat(64); },
    copy => { copy.documents[0].sourceBodySha256 = '0'.repeat(63); },
    copy => { copy.documents[0].id = '../outside'; },
    copy => { copy.version = 2; },
  ];
  for (const mutate of mutations) {
    const copy = structuredClone(bundle); mutate(copy); assert.throws(() => validateSchema(copy));
  }
});
check('oversized text, oversized catalogs, invalid controls and surrogate corruption are rejected', () => {
  const mutations = [
    copy => { copy.documents[0].variants.zh.title = '字'.repeat(201); },
    copy => { copy.documents[0].variants.zh.title = '两行\n标题'; },
    copy => { copy.documents[0].variants.zh.body = 'x'.repeat(maxBodyBytes + 1); },
    copy => { copy.documents[0].variants.zh.body = '正文\u0000'; },
    copy => { copy.documents[0].variants.zh.body = '正文\ud800'; },
    copy => { copy.documents = Array.from({ length: 129 }, () => copy.documents[0]); },
    copy => {
      for (const doc of copy.documents.slice(0, 3)) {
        doc.variants.zh.body = 'x'.repeat(400 * 1024);
        doc.variants.en.body = 'x'.repeat(400 * 1024);
      }
    },
  ];
  for (const mutate of mutations) {
    const copy = structuredClone(bundle); mutate(copy); assert.throws(() => validateSchema(copy));
  }
});
check('a valid-looking changed source GUID cannot pass the shared-source contract', () => {
  const copy = structuredClone(bundle), doc = copy.documents.find(item => item.id === manifest[0][0]);
  doc.variants.zh.body = doc.variants.zh.body.replace(manifest[0][2], '0'.repeat(32));
  validateSchema(copy);
  assert.throws(() => canonicalModels(copy), /GUID/);
});
check('ordinary English or Chinese accidentally pasted into the opposite prose is detected', () => {
  for (const [language, addition] of [['zh', 'Overview'], ['en', '混入中文']]) {
    const copy = structuredClone(bundle), doc = copy.documents.find(item => item.id === manifest[0][0]);
    const model = editor.parse(doc.variants[language].body); model.summary += '\n' + addition;
    doc.variants[language].body = editor.serialize(doc.variants[language].body, model);
    assert.throws(() => assertHumanLanguages(copy));
  }
});
check('both locales render without mutating the bundle or canonical text', () => {
  const snapshot = JSON.stringify(bundle);
  for (const doc of bundle.documents) for (const language of ['zh', 'en']) editor.present(doc.variants[language].body);
  assert.equal(JSON.stringify(bundle), snapshot);
  assert.deepEqual(readFileSync(bundlePath), raw);
});
console.log(`${checks} Dev Room translation checks passed.`);
