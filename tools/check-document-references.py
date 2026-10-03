"""Isolated catalog checks: no user data, running Console, or Blender is touched."""
import copy
from email.message import Message
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from document_library import (
    DocumentLibraryService, INBOX_FILE, MAX_REFERENCE_BYTES,
    MAX_REFERENCE_ITEMS, MAX_TEXT_BYTES, REFERENCES_FILE,
)


def catalog():
    return {'version': 1, 'items': [{
        'id': 'custom-nodes', 'module': 'blender', 'defaultLanguage': 'zh-CN',
        'variants': [
            {'language': 'zh-CN', 'label': '中文', 'title': '自定义节点参考',
             'summary': '按来源查阅节点。', 'path': 'blender/reference.zh-CN.md'},
            {'language': 'en', 'label': 'English', 'title': 'Custom Nodes reference',
             'summary': 'Browse nodes by source.', 'path': 'blender/reference.en.md'},
        ],
    }]}


class ReferenceChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='console-reference-check-')
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / '中文 library'
        (self.root / 'blender').mkdir(parents=True)
        self.zh = self.root / 'blender/reference.zh-CN.md'
        self.en = self.root / 'blender/reference.en.md'
        self.zh.write_text('# 自定义节点\n\n## Higgsas\n\n## Node Tools V2\n', encoding='utf-8-sig')
        self.en.write_text('# Custom Nodes\n\n## Higgsas\n\n## Node Tools V2\n', encoding='utf-8')
        self.config = self.base / 'documents.json'
        self.config.write_text(json.dumps({'root': str(self.root), 'keep': 'existing choice'}), encoding='utf-8')
        # An opaque existing reading-state payload must remain byte-for-byte intact.
        (self.root / INBOX_FILE).write_text('{"version":1,"entries":[],"preserve":"reading state"}', encoding='utf-8')
        self.manifest = self.root / REFERENCES_FILE
        self.service = DocumentLibraryService(self.config)

    def tearDown(self):
        self.temporary.cleanup()

    def write_catalog(self, value=None):
        self.manifest.write_text(json.dumps(catalog() if value is None else value, ensure_ascii=False, indent=2), encoding='utf-8-sig')

    def snapshot(self):
        return {str(path.relative_to(self.base)): (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
                for path in self.base.rglob('*') if path.is_file() and not path.is_symlink()}

    def test_absent_catalog_is_empty_without_inference_or_writes(self):
        before = self.snapshot()
        self.assertEqual(self.service.references(expectedRoot=str(self.root)), {'root': str(self.root), 'items': []})
        self.assertEqual(self.service.references(module='blender')['items'], [])
        self.assertEqual(self.snapshot(), before)

    def test_one_document_two_languages_filter_and_read_only_files(self):
        self.write_catalog()
        before = self.snapshot()
        result = self.service.references(module='blender', expectedRoot=str(self.root))
        self.assertEqual(result['root'], str(self.root))
        self.assertEqual(len(result['items']), 1)
        reference = result['items'][0]
        self.assertEqual(reference['id'], 'custom-nodes')
        self.assertEqual(reference['defaultLanguage'], 'zh-CN')
        self.assertEqual([variant['language'] for variant in reference['variants']], ['zh-CN', 'en'])
        for variant in reference['variants']:
            self.assertTrue(variant['available'])
            self.assertEqual(variant['error'], '')
            document = self.service.read(variant['path'], expectedRoot=result['root'])
            self.assertIn('Node Tools V2', document['content'])
            self.assertNotIn('content', variant)
        self.assertEqual(self.service.references(module='unity')['items'], [])
        self.assertEqual(self.service.references()['items'], result['items'])
        self.assertEqual(self.snapshot(), before)

    def test_missing_language_keeps_other_language_readable(self):
        self.write_catalog()
        self.zh.unlink()
        before = self.snapshot()
        reference = self.service.references()['items'][0]
        self.assertEqual(reference['defaultLanguage'], 'zh-CN')
        self.assertFalse(reference['variants'][0]['available'])
        self.assertTrue(reference['variants'][0]['error'])
        self.assertTrue(reference['variants'][1]['available'])
        self.assertIn('# Custom Nodes', self.service.read(reference['variants'][1]['path'])['content'])
        self.assertEqual(self.snapshot(), before)

    def test_malformed_json_encoding_and_manifest_size_are_rejected_without_repair(self):
        for raw in [b'{broken', b'\xff', b'[]', b'{}', b' ' * (MAX_REFERENCE_BYTES + 1)]:
            with self.subTest(raw=raw[:12]):
                self.manifest.write_bytes(raw)
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    self.service.references()
                self.assertEqual(self.snapshot(), before)
        self.write_catalog()
        manifest_bytes = self.manifest.read_bytes()
        original_open = Path.open
        def deny_manifest(path, *args, **kwargs):
            if path == self.manifest:
                raise PermissionError('fixture denied')
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', deny_manifest), self.assertRaisesRegex(ValueError, 'fixture denied'):
            self.service.references()
        self.assertEqual(self.manifest.read_bytes(), manifest_bytes)

    def test_schema_limits_duplicate_ids_languages_and_paths(self):
        mutations = [
            lambda value: value.update(version=True),
            lambda value: value.update(version=2),
            lambda value: value.update(items={}),
            lambda value: value.update(items=[{}] * (MAX_REFERENCE_ITEMS + 1)),
            lambda value: value['items'].append(copy.deepcopy(value['items'][0])),
            lambda value: value['items'].append('wrong item type'),
            lambda value: value['items'][0].update(id='../outside'),
            lambda value: value['items'][0].update(module=12),
            lambda value: value['items'][0].update(module='Blender'),
            lambda value: value['items'][0].update(variants={}),
            lambda value: value['items'][0].update(variants=[]),
            lambda value: value['items'][0].update(variants=[{}] * 9),
            lambda value: value['items'][0]['variants'].append('wrong variant type'),
            lambda value: value['items'][0].update(defaultLanguage='fr'),
            lambda value: value['items'][0].pop('defaultLanguage'),
            lambda value: value['items'][0]['variants'][1].update(language='zh-cn'),
            lambda value: value['items'][0]['variants'][1].update(language='english'),
            lambda value: value['items'][0]['variants'][1].update(language=1),
            lambda value: value['items'][0]['variants'][1].update(path='blender/reference.zh-CN.md'),
            lambda value: value['items'][0]['variants'][1].update(path='blender/./reference.zh-CN.md'),
            lambda value: value['items'][0]['variants'][1].update(path='blender/reference.py'),
            lambda value: value['items'][0]['variants'][1].update(path=0),
            lambda value: value['items'][0]['variants'][1].update(label=''),
            lambda value: value['items'][0]['variants'][1].update(label='x' * 41),
            lambda value: value['items'][0]['variants'][1].update(title=None),
            lambda value: value['items'][0]['variants'][1].update(title='x' * 161),
            lambda value: value['items'][0]['variants'][1].update(summary='x' * 601),
            lambda value: value['items'][0]['variants'][1].update(summary='line\nbreak'),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                value = catalog()
                mutate(value)
                self.write_catalog(value)
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    self.service.references()
                self.assertEqual(self.snapshot(), before)

    def test_unreadable_or_oversized_utf8_variant_is_unavailable_and_bounded(self):
        self.write_catalog()
        for content, error in [(b'\xff\x00', 'UTF-8'), (b'x' * (MAX_TEXT_BYTES + 1), '2 MiB')]:
            with self.subTest(error=error):
                self.zh.write_bytes(content)
                before = self.snapshot()
                variants = self.service.references()['items'][0]['variants']
                self.assertFalse(variants[0]['available'])
                self.assertIn(error, variants[0]['error'])
                self.assertTrue(variants[1]['available'])
                self.assertEqual(self.snapshot(), before)
        self.zh.write_bytes(b'x' * MAX_TEXT_BYTES)
        self.assertTrue(self.service.references()['items'][0]['variants'][0]['available'])
        original_open = Path.open
        bounded_reads = []
        class BoundedFile(io.BytesIO):
            def read(inner, size=-1):
                self.assertGreater(size, 0, 'Catalog/document reads must have a byte limit')
                bounded_reads.append(size)
                return super().read(size)
        raw = self.manifest.read_bytes()
        def tracked_open(path, *args, **kwargs):
            if path == self.manifest:
                return BoundedFile(raw)
            if path == self.zh:
                return BoundedFile(b'# Reference')
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', tracked_open):
            self.service.references()
        self.assertEqual(bounded_reads, [MAX_REFERENCE_BYTES + 1, MAX_TEXT_BYTES + 1])

    def test_root_guard_and_unsafe_paths_reject_before_outside_read(self):
        self.write_catalog()
        for expected in ['', 'relative/path', str(self.base), 1]:
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                self.service.references(expectedRoot=expected)
        for module in ['', 'BLENDER', '../blender', 'x' * 41]:
            with self.subTest(module=module), self.assertRaises(ValueError):
                self.service.references(module=module)
        secret = self.base / 'outside.md'
        secret.write_text('OUTSIDE-SECRET-MUST-NOT-BE-RETURNED', encoding='utf-8')
        for path in ['../outside.md', str(secret), 'C:outside.md', 'blender/file.md:stream']:
            value = catalog()
            value['items'][0]['variants'][0]['path'] = path
            self.write_catalog(value)
            before = self.snapshot()
            with self.subTest(path=path), patch.object(self.service, '_read_document') as read:
                with self.assertRaises(ValueError) as raised:
                    self.service.references()
                self.assertNotIn('OUTSIDE-SECRET', str(raised.exception))
                read.assert_not_called()
            self.assertEqual(self.snapshot(), before)

    def test_external_document_and_manifest_symlinks_are_rejected(self):
        outside = self.base / 'outside.md'
        outside.write_text('OUTSIDE-SECRET', encoding='utf-8')
        linked = self.root / 'blender/linked.md'
        try:
            linked.symlink_to(outside)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f'Test symlink creation unavailable: {error}')
        value = catalog()
        value['items'][0]['variants'][0]['path'] = 'blender/linked.md'
        self.write_catalog(value)
        with patch.object(self.service, '_read_document') as read, self.assertRaises(ValueError) as raised:
            self.service.references()
        read.assert_not_called()
        self.assertNotIn('OUTSIDE-SECRET', str(raised.exception))
        self.manifest.unlink()
        self.manifest.symlink_to(outside)
        with self.assertRaises(ValueError) as raised:
            self.service.references()
        self.assertNotIn('OUTSIDE-SECRET', str(raised.exception))
        self.assertEqual(outside.read_text(encoding='utf-8'), 'OUTSIDE-SECRET')

    def test_guarded_route_dispatch_passes_parameters_without_real_http(self):
        self.write_catalog()
        data = self.base / 'app-data'
        data.mkdir()
        (data / '.cache-migrated-v0.3').write_text('isolated', encoding='utf-8')
        environment = {
            'CODEX_CONTROL_DATA_DIR': str(data), 'CODEX_CONTROL_EDITION': 'public',
            'CODEX_CONTROL_DESKTOP_LAYOUT_DATA_DIR': str(data / 'desktop'),
            'CODEX_CONTROL_DESKTOP_LAYOUT_CURRENT': str(data / 'desktop/current.json'),
            'CODEX_CONTROL_DESKTOP_LAYOUT_STARTUP_FILE': str(data / 'Startup/Disabled.vbs'),
            'CODEX_CONTROL_TEMP_DIR': str(data / 'temp'),
            'CODEX_CONTROL_MUSIC_DIR': str(data / 'music'),
            'CODEX_CONTROL_WALLPAPERS_DIR': str(data / 'wallpapers'),
            'CODEX_CONTROL_PUBLISHER_STATE_FILE': str(data / 'publisher-state.json'),
        }
        # Run this check as its own process, as check-quality does. Do not reuse a
        # pre-imported Console module that may have initialized against user data.
        self.assertNotIn('world_console', sys.modules)
        with patch.dict(os.environ, environment):
            console = importlib.import_module('world_console')
        self.assertEqual(console.USER_DATA_DIR, data.resolve())
        self.assertEqual(console.DESKTOP_LAYOUT.data_dir, data / 'desktop')
        class Handler:
            require_local_request = console.ConsoleHandler.require_local_request
            require_trusted_post_context = console.ConsoleHandler.require_trusted_post_context
            connection = object()
            def _private_phone_path(inner): return False  # This fixture dispatches API routes only.
            def __init__(inner, host='127.0.0.1:8898', origin=None, client='127.0.0.1', fetch_site=None):
                inner.path = '/api/documents/references?' + urlencode({'module': 'blender', 'expectedRoot': str(self.root)})
                inner.headers = Message()
                inner.headers['Host'] = host
                if origin:
                    inner.headers['Origin'] = origin
                if fetch_site:
                    inner.headers['Sec-Fetch-Site'] = fetch_site
                inner.client_address = (client, 12345)
                inner.response = None
            def send_json(inner, payload, status=200):
                inner.response = (status, payload)
        before = self.snapshot()
        with patch.object(console, 'DOCUMENT_LIBRARY', self.service):
            for kwargs in [{'client': '192.0.2.9'}, {'host': 'attacker.example'},
                           {'origin': 'https://attacker.example'}, {'fetch_site': 'cross-site'}]:
                with self.subTest(kwargs=kwargs), patch.object(self.service, 'references') as read:
                    handler = Handler(**kwargs)
                    console.ConsoleHandler.do_GET(handler)
                    self.assertEqual(handler.response[0], 403)
                    read.assert_not_called()
            handler = Handler(origin='http://127.0.0.1:8898')
            with patch.object(self.service, 'references', wraps=self.service.references) as read:
                console.ConsoleHandler.do_GET(handler)
                read.assert_called_once_with(module='blender', expectedRoot=str(self.root))
            self.assertEqual(handler.response[0], 200)
            self.assertEqual(handler.response[1]['items'][0]['id'], 'custom-nodes')
            for query in [{'module': 'blender', 'expectedRoot': str(self.base)}, {'module': ''}]:
                handler = Handler()
                handler.path = '/api/documents/references?' + urlencode(query)
                console.ConsoleHandler.do_GET(handler)
                self.assertEqual(handler.response[0], 400)
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
