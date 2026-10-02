"""Small isolated checks; never uses the user's selected directory or sampler."""
import json
import ctypes
import http.client
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import document_library
from document_library import (DocumentLibraryService, MAX_TEXT_BYTES, INBOX_FILE, GUIDE_FILE, MAX_GUIDE_BYTES,
                              MAX_GUIDE_ITEMS, DEVICE_DETAILS_FILE, MAX_DEVICE_DETAILS_BYTES, MAX_GPU_QUERY_BYTES,
                              current_memory, current_gpu, current_storage)


class DocumentChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='console-documents-')
        self.base = Path(self.temp.name)
        self.root = self.base / '中文 資料 folder'
        self.root.mkdir()
        (self.root / 'README.md').write_text('# 電腦\n\n[報告](reports/狀態.md)\n', encoding='utf-8')
        (self.root / 'reports').mkdir()
        (self.root / 'reports' / '狀態.md').write_text('| 指標 | 值 |\n| --- | --- |\n| 可用 | 未知 |', encoding='utf-8')
        self.config = self.base / 'settings' / 'documents.json'
        self.service = DocumentLibraryService(self.config)
        self.status_patch = patch('document_library.device_library.status', return_value={'status': 'idle'})
        self.status_patch.start()
        self.gpu_patch = patch('document_library.current_gpu', return_value={
            'status': 'unavailable', 'readAt': '2026-10-03T00:00:00+08:00', 'source': 'nvidia-smi',
            'reason': 'isolated test driver unavailable', 'adapters': []})
        self.storage_patch = patch('document_library.current_storage', return_value={
            'status': 'unavailable', 'readAt': '2026-10-03T00:00:00+08:00', 'totalBytes': None,
            'usedBytes': None, 'freeBytes': None, 'source': 'isolated fixture', 'reason': 'fixture unavailable'})
        self.gpu_patch.start()
        self.storage_patch.start()

    def tearDown(self):
        self.status_patch.stop()
        self.gpu_patch.stop()
        self.storage_patch.stop()
        self.temp.cleanup()

    def test_reopen_and_invalid_root_preserve_choice(self):
        self.service.select(str(self.root))
        reopened = DocumentLibraryService(self.config)
        self.assertEqual(reopened.state()['root'], str(self.root.resolve()))
        with self.assertRaises(ValueError):
            reopened.select(str(self.base / 'missing'))
        self.assertTrue(reopened.state()['exists'])
        moved = self.root.with_name('已移動')
        self.root.rename(moved)
        self.assertFalse(reopened.state()['exists'])
        self.assertIn('重新選擇', reopened.state()['error'])
        reopened.select(str(moved))
        self.assertTrue(reopened.state()['exists'])

    def test_folder_picker_cancel_keeps_choice(self):
        self.service.select(str(self.root))
        with patch.object(self.service, '_choose_folder', return_value=None):
            self.assertTrue(self.service.select()['cancelled'])
        self.assertEqual(self.service.state()['root'], str(self.root.resolve()))

    def test_browse_refresh_and_bounded_read(self):
        self.service.select(str(self.root))
        self.assertEqual(self.service.list()['path'], '')
        self.assertEqual(self.service.read('README.md')['format'], 'markdown')
        self.assertEqual(self.service.read('reports/狀態.md')['name'], '狀態.md')
        (self.root / 'new.json').write_text('{}', encoding='utf-8')
        self.assertIn('new.json', [item['path'] for item in self.service.list()['entries']])
        (self.root / 'large.txt').write_bytes(b'x' * (MAX_TEXT_BYTES + 1))
        with self.assertRaisesRegex(ValueError, '2 MiB'):
            self.service.read('large.txt')
        (self.root / 'binary.txt').write_bytes(b'\xff\x00')
        with self.assertRaisesRegex(ValueError, 'UTF-8'):
            self.service.read('binary.txt')

    def test_no_parent_absolute_or_executable_access(self):
        self.service.select(str(self.root))
        for path in ['../outside.md', str(self.base / 'outside.md'), 'C:outside.md']:
            with self.assertRaises(ValueError):
                self.service.read(path)
        (self.root / 'run.exe').write_bytes(b'MZ')
        with self.assertRaises(ValueError):
            self.service.read('run.exe')
        self.assertNotIn('run.exe', [item['name'] for item in self.service.list()['entries']])

    def write_guide(self, root=None, **changes):
        root = root or self.root
        item = {'path': 'reports/狀態.md', 'title': '設備重點', 'summary': '供人閱讀的摘要。',
                'highlights': ['這是保存的歷史資料。', '即時記憶體請看首頁。']}
        item.update(changes)
        manifest = root / GUIDE_FILE
        manifest.write_text(json.dumps({'version': 1, 'items': [item]}, ensure_ascii=False), encoding='utf-8')
        return manifest

    def test_guide_missing_manifest_is_empty_and_valid_manifest_is_read_only(self):
        self.service.select(str(self.root))
        settings = self.config.read_bytes()
        readme = (self.root / 'README.md').read_bytes()
        self.assertEqual(self.service.guide(expectedRoot=self.root), {'root': str(self.root.resolve()), 'items': []})
        self.assertFalse((self.root / GUIDE_FILE).exists())
        manifest = self.write_guide()
        original = manifest.read_bytes()
        report = (self.root / 'reports' / '狀態.md').read_bytes()
        result = self.service.guide(expectedRoot=self.root)
        self.assertEqual(result['root'], str(self.root.resolve()))
        self.assertEqual(result['items'][0], {'path': 'reports/狀態.md', 'title': '設備重點',
                                             'summary': '供人閱讀的摘要。',
                                             'highlights': ['這是保存的歷史資料。', '即時記憶體請看首頁。']})
        self.assertNotIn('content', result['items'][0])
        self.assertEqual(manifest.read_bytes(), original)
        self.assertEqual(self.config.read_bytes(), settings)
        self.assertEqual((self.root / 'README.md').read_bytes(), readme)
        self.assertEqual((self.root / 'reports' / '狀態.md').read_bytes(), report)
        self.assertFalse((self.root / INBOX_FILE).exists())

    def test_guide_rejects_bad_manifest_and_field_limits_without_rewriting(self):
        self.service.select(str(self.root))
        manifest = self.root / GUIDE_FILE
        invalid = [b'{broken', b'\xff', b'[]', b'{"version":true,"items":[]}', b'{"version":2,"items":[]}',
                   b'{"version":1,"items":{}}', b'{"version":1,"items":[null]}',
                   b' ' * (MAX_GUIDE_BYTES + 1),
                   json.dumps({'version': 1, 'items': [{}] * (MAX_GUIDE_ITEMS + 1)}).encode('utf-8')]
        for raw in invalid:
            manifest.write_bytes(raw)
            with self.subTest(raw=raw[:80]), self.assertRaisesRegex(ValueError, '重點導覽設定.*原檔案未更動'):
                self.service.guide()
            self.assertEqual(manifest.read_bytes(), raw)
        for changes in [{'title': ''}, {'title': 'x' * 161}, {'summary': 'x' * 601}, {'summary': []},
                        {'path': 'x' * 1025}, {'highlights': 'text'}, {'highlights': ['x'] * 9},
                        {'highlights': ['x' * 241]}, {'highlights': [None]}, {'highlights': ['line\nbreak']}]:
            self.write_guide(**changes)
            original = manifest.read_bytes()
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, '原檔案未更動'):
                self.service.guide()
            self.assertEqual(manifest.read_bytes(), original)

    def test_guide_requires_real_readable_files_and_keeps_path_boundary(self):
        self.service.select(str(self.root))
        outside = self.base / 'outside.md'
        outside.write_text('# Outside', encoding='utf-8')
        (self.root / 'reports' / 'binary.md').write_bytes(b'\xff')
        (self.root / 'reports' / 'large.md').write_bytes(b'x' * (MAX_TEXT_BYTES + 1))
        (self.root / 'run.exe').write_bytes(b'MZ')
        for path in ['../outside.md', str(outside), 'C:outside.md', 'reports/../README.md',
                     'missing.md', 'reports', 'run.exe', 'reports/binary.md', 'reports/large.md']:
            manifest = self.write_guide(path=path)
            original = manifest.read_bytes()
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, '原檔案未更動'):
                self.service.guide()
            self.assertEqual(manifest.read_bytes(), original)
        self.assertEqual(outside.read_text(encoding='utf-8'), '# Outside')

    def test_guide_wraps_manifest_and_item_path_resolution_loops(self):
        self.service.select(str(self.root))
        manifest = self.write_guide()
        original = manifest.read_bytes()
        for method in ('_path', '_read_document'):
            with self.subTest(method=method), \
                    patch.object(self.service, method, side_effect=RuntimeError('Symlink loop')):
                with self.assertRaisesRegex(ValueError, '重點導覽設定.*原檔案未更動.*Symlink loop'):
                    self.service.guide(expectedRoot=self.root)
            self.assertEqual(manifest.read_bytes(), original)

    def test_guide_expected_root_and_external_root_change_stay_scoped(self):
        self.service.select(str(self.root))
        first_manifest = self.write_guide()
        first_bytes = first_manifest.read_bytes()
        second = self.base / 'guide library B'
        (second / 'reports').mkdir(parents=True)
        (second / 'reports' / '狀態.md').write_text('# B report', encoding='utf-8')
        second_manifest = self.write_guide(second, title='B guide')
        second_bytes = second_manifest.read_bytes()
        self.service.select(str(second))
        with self.assertRaisesRegex(ValueError, '資料庫已切換'):
            self.service.guide(expectedRoot=self.root)
        self.assertEqual(self.service.guide(expectedRoot=second)['items'][0]['title'], 'B guide')
        self.assertEqual(self.service.guide()['root'], str(second.resolve()))
        external = DocumentLibraryService(self.config)
        self.service.select(str(self.root))
        original_read = self.service._read_document

        def change_settings_before_read(relative):
            external.select(str(second))
            return original_read(relative)

        with patch.object(self.service, '_read_document', side_effect=change_settings_before_read):
            result = self.service.guide(expectedRoot=self.root)
        self.assertEqual(result['root'], str(self.root.resolve()))
        self.assertEqual(result['items'][0]['title'], '設備重點')
        self.assertEqual(self.service.guide(expectedRoot=second)['items'][0]['title'], 'B guide')
        self.assertEqual(first_manifest.read_bytes(), first_bytes)
        self.assertEqual(second_manifest.read_bytes(), second_bytes)

    def register(self, identifier='cosha-unity-v1', path='reports/狀態.md', **changes):
        values = {'id': identifier, 'path': path, 'title': 'Cosha 操作報告',
                  'summary': '可閱讀的完整報告摘要。', 'source': 'X', 'createdAt': '2026-09-28T12:30:00+08:00'}
        values.update(changes)
        return self.service.register_report(**values)

    def prepare_second_library(self):
        self.service.select(str(self.root))
        self.register()
        second = self.base / '另一個資料庫'
        (second / 'reports').mkdir(parents=True)
        (second / 'reports' / '狀態.md').write_text('# Database B has different report content', encoding='utf-8')
        self.service.select(str(second))
        self.register(title='Database B same id')
        return second

    def test_reader_expected_root_rejects_stale_read_inbox_and_mark_without_writes(self):
        second = self.prepare_second_library()
        first_registry = (self.root / INBOX_FILE).read_bytes()
        second_registry = (second / INBOX_FILE).read_bytes()
        operations = [lambda: self.service.read('reports/狀態.md', expectedRoot=str(self.root)),
                      lambda: self.service.inbox(expectedRoot=str(self.root)),
                      lambda: self.service.mark_report_read('cosha-unity-v1', True, expectedRoot=str(self.root))]
        for operation in operations:
            with self.assertRaisesRegex(ValueError, '資料庫已切換'):
                operation()
        self.assertEqual((self.root / INBOX_FILE).read_bytes(), first_registry)
        self.assertEqual((second / INBOX_FILE).read_bytes(), second_registry)
        self.assertEqual(self.service.state()['root'], str(second.resolve()))
        self.assertIn('Database B', self.service.read('reports/狀態.md', expectedRoot=second)['content'])
        self.assertEqual(self.service.inbox(expectedRoot=second)['unreadCount'], 1)
        self.assertEqual(self.service.mark_report_read('cosha-unity-v1', True, expectedRoot=second)['unreadCount'], 0)
        self.assertEqual((self.root / INBOX_FILE).read_bytes(), first_registry)
        # Existing callers without expectedRoot keep following the selected root.
        self.assertIn('Database B', self.service.read('reports/狀態.md')['content'])
        self.assertEqual(self.service.inbox()['unreadCount'], 0)
        self.assertEqual(self.service.mark_report_read('cosha-unity-v1', False)['unreadCount'], 1)
        for expected in ['', [], 'relative-folder']:
            with self.subTest(expected=expected), self.assertRaisesRegex(ValueError, '路徑無效'):
                self.service.inbox(expectedRoot=expected)

    def test_reader_scope_pins_root_across_external_settings_change(self):
        second = self.prepare_second_library()
        external = DocumentLibraryService(self.config)
        self.service.select(str(self.root))
        second_registry = (second / INBOX_FILE).read_bytes()
        original_save = self.service._save_inbox

        def switch_before_save(entries):
            # Another service/process updates the shared settings after this request
            # validated A. The in-flight operation must not write A's entries to B.
            external.select(str(second))
            original_save(entries)

        with patch.object(self.service, '_save_inbox', side_effect=switch_before_save):
            result = self.service.mark_report_read('cosha-unity-v1', True, expectedRoot=str(self.root))
        self.assertEqual(result['root'], str(self.root.resolve()))
        self.assertTrue(json.loads((self.root / INBOX_FILE).read_text(encoding='utf-8'))['entries'][0]['read'])
        self.assertEqual((second / INBOX_FILE).read_bytes(), second_registry)
        self.assertEqual(self.service.state()['root'], str(second.resolve()))
        with self.assertRaisesRegex(ValueError, '資料庫已切換'):
            self.service.inbox(expectedRoot=str(self.root))
        self.service.select(str(self.root))
        original_read = self.service._read_document

        def switch_before_read(relative):
            external.select(str(second))
            return original_read(relative)

        with patch.object(self.service, '_read_document', side_effect=switch_before_read):
            document = self.service.read('reports/狀態.md', expectedRoot=str(self.root))
        self.assertEqual(document['root'], str(self.root.resolve()))
        self.assertNotIn('Database B', document['content'])
        self.assertIn('Database B', self.service.read('reports/狀態.md')['content'])

    def test_inbox_read_is_explicit_persistent_and_duplicate_is_idempotent(self):
        self.service.select(str(self.root))
        original_report = (self.root / 'reports' / '狀態.md').read_bytes()
        original_config = self.config.read_bytes()
        self.assertEqual(self.service.inbox()['entries'], [])
        registered = self.register()
        self.assertTrue(registered['created'])
        self.assertEqual(registered['unreadCount'], 1)
        self.assertFalse(registered['item']['read'])
        self.service.read('reports/狀態.md')
        self.assertEqual(self.service.inbox()['unreadCount'], 1)
        marked = self.service.mark_report_read('cosha-unity-v1', True)
        self.assertEqual(marked['unreadCount'], 0)
        read_at = marked['item']['readAt']
        self.assertTrue(read_at)
        reopened = DocumentLibraryService(self.config)
        self.assertEqual(reopened.inbox()['entries'][0]['readAt'], read_at)
        duplicate = self.register(title='Duplicate title must not replace original', path='reports/absent.md')
        self.assertFalse(duplicate['created'])
        self.assertEqual(duplicate['totalCount'], 1)
        self.assertEqual(duplicate['item'], marked['item'])
        self.assertEqual(self.service.mark_report_read('cosha-unity-v1', True)['item']['readAt'], read_at)
        unread = self.service.mark_report_read('cosha-unity-v1', False)
        self.assertEqual(unread['unreadCount'], 1)
        self.assertIsNone(unread['item']['readAt'])
        self.assertEqual((self.root / 'reports' / '狀態.md').read_bytes(), original_report)
        self.assertEqual(self.config.read_bytes(), original_config)

    def test_archive_migrates_legacy_read_flags_in_memory_without_get_writes(self):
        self.service.select(str(self.root))
        self.register(identifier='legacy-unread')
        self.register(identifier='legacy-read')
        self.service.mark_report_read('legacy-read', True)
        registry = self.root / INBOX_FILE
        data = json.loads(registry.read_text(encoding='utf-8'))
        for entry in data['entries']:
            entry.pop('status')
        registry.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        original = registry.read_bytes()
        result = self.service.inbox(expectedRoot=self.root)
        self.assertEqual({entry['id']: entry['status'] for entry in result['entries']},
                         {'legacy-unread': 'inbox', 'legacy-read': 'archive'})
        self.assertEqual((result['inboxCount'], result['laterCount'], result['archiveCount']), (1, 0, 1))
        self.assertEqual(registry.read_bytes(), original)
        self.assertFalse(self.register(identifier='legacy-read')['created'])
        self.assertEqual(registry.read_bytes(), original)
        self.service.move_report('legacy-unread', 'later', expectedRoot=self.root)
        result = DocumentLibraryService(self.config).inbox()
        self.assertEqual((result['inboxCount'], result['laterCount'], result['archiveCount'], result['unreadCount']), (0, 1, 1, 1))
        self.assertTrue(all('status' in entry for entry in json.loads(registry.read_text(encoding='utf-8'))['entries']))

    def test_archive_clear_and_batch_undo_preserve_files_and_stable_ids(self):
        self.service.select(str(self.root))
        original_report = (self.root / 'reports' / '狀態.md').read_bytes()
        original_config = self.config.read_bytes()
        for identifier in ['archive-a', 'archive-b', 'later-c', 'inbox-d']:
            self.register(identifier=identifier)
        for identifier in ['archive-a', 'archive-b']:
            self.service.mark_report_read(identifier, True)
        self.service.move_report('later-c', 'later')
        before = self.service.inbox()
        self.assertEqual((before['inboxCount'], before['laterCount'], before['archiveCount'], before['unreadCount']), (1, 1, 2, 2))
        read_times = {entry['id']: entry['readAt'] for entry in before['entries']}
        first = self.service.clear_archive(expectedRoot=self.root)
        self.assertEqual(first['clearedCount'], 2)
        self.assertEqual((first['inboxCount'], first['laterCount'], first['archiveCount'], first['totalCount']), (1, 1, 0, 2))
        self.assertRegex(first['undoToken'], r'^[0-9a-f]{32}$')
        cleared_bytes = (self.root / INBOX_FILE).read_bytes()
        duplicate = self.register(identifier='archive-a')
        self.assertFalse(duplicate['created'])
        self.assertEqual(duplicate['item']['status'], 'cleared')
        self.assertEqual(duplicate['totalCount'], 2)
        for action in [lambda: self.service.mark_report_read('archive-a', False),
                       lambda: self.service.mark_report_read('archive-a', True),
                       lambda: self.service.move_report('archive-a', 'inbox'),
                       lambda: self.service.move_report('archive-a', 'archive')]:
            with self.assertRaisesRegex(ValueError, '復原'):
                action()
        self.assertEqual((self.root / INBOX_FILE).read_bytes(), cleared_bytes)
        empty = self.service.clear_archive()
        self.assertEqual(empty['clearedCount'], 0)
        self.assertNotEqual(empty['undoToken'], first['undoToken'])
        self.assertEqual((self.root / INBOX_FILE).read_bytes(), cleared_bytes)
        self.assertTrue(self.service.read('reports/狀態.md')['content'])
        self.service.mark_report_read('inbox-d', True)
        second = self.service.clear_archive()
        self.assertEqual(second['clearedCount'], 1)
        self.assertNotEqual(second['undoToken'], first['undoToken'])
        reopened = DocumentLibraryService(self.config)
        restored = reopened.restore_archive(first['undoToken'], expectedRoot=self.root)
        self.assertEqual(restored['restoredCount'], 2)
        self.assertEqual(restored['archiveCount'], 2)
        self.assertNotIn('inbox-d', [entry['id'] for entry in restored['entries']])
        for entry in restored['entries']:
            if entry['status'] == 'archive':
                self.assertTrue(entry['read'])
                self.assertEqual(entry['readAt'], read_times[entry['id']])
                self.assertNotIn('clearBatch', entry)
                self.assertNotIn('clearedAt', entry)
        self.assertEqual(reopened.restore_archive(first['undoToken'])['restoredCount'], 0)
        reopened.move_report('archive-a', 'later')
        self.assertEqual(reopened.restore_archive(second['undoToken'])['restoredCount'], 1)
        third = reopened.clear_archive()
        self.assertEqual(third['clearedCount'], 2)
        self.assertEqual(reopened.restore_archive(first['undoToken'])['restoredCount'], 0)
        self.assertEqual(reopened.restore_archive(third['undoToken'])['restoredCount'], 2)
        final = reopened.inbox()
        self.assertEqual((final['inboxCount'], final['laterCount'], final['archiveCount'], final['unreadCount']), (0, 2, 2, 2))
        self.assertEqual(len({entry['id'] for entry in final['entries']}), 4)
        self.assertEqual((self.root / 'reports' / '狀態.md').read_bytes(), original_report)
        self.assertEqual(self.config.read_bytes(), original_config)

    def test_archive_mutations_validate_status_keep_failed_writes_and_share_lock(self):
        self.service.select(str(self.root))
        self.register()
        registry = self.root / INBOX_FILE
        original = registry.read_bytes()
        for status in ['cleared', 'read', None, [], True]:
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.service.move_report('cosha-unity-v1', status)
        for token in ['', None, [], '../file', '0' * 31]:
            with self.subTest(token=token), self.assertRaises(ValueError):
                self.service.restore_archive(token)
        self.assertEqual(registry.read_bytes(), original)
        self.service.mark_report_read('cosha-unity-v1', True)
        archived = registry.read_bytes()
        with patch('document_library.os.replace', side_effect=OSError('test disk failure')):
            with self.assertRaises(OSError):
                self.service.clear_archive()
        self.assertEqual(registry.read_bytes(), archived)
        cleared = self.service.clear_archive()
        cleared_bytes = registry.read_bytes()
        with patch('document_library.os.replace', side_effect=OSError('test disk failure')):
            with self.assertRaises(OSError):
                self.service.restore_archive(cleared['undoToken'])
        self.assertEqual(registry.read_bytes(), cleared_bytes)
        other = DocumentLibraryService(self.config)
        with self.service._inbox_write_lock():
            for operation in [lambda: other.move_report('cosha-unity-v1', 'later'),
                              lambda: other.clear_archive(), lambda: other.restore_archive(cleared['undoToken'])]:
                with self.assertRaisesRegex(ValueError, '另一個 Console'):
                    operation()
        self.assertEqual(registry.read_bytes(), cleared_bytes)
        self.assertFalse(list(self.root.glob(INBOX_FILE + '.*.tmp')))

    def test_archive_root_guard_and_pinning_prevent_cross_library_changes(self):
        second = self.prepare_second_library()
        self.service.mark_report_read('cosha-unity-v1', True)
        first_bytes = (self.root / INBOX_FILE).read_bytes()
        second_bytes = (second / INBOX_FILE).read_bytes()
        for operation in [lambda: self.service.move_report('cosha-unity-v1', 'later', expectedRoot=self.root),
                          lambda: self.service.clear_archive(expectedRoot=self.root),
                          lambda: self.service.restore_archive('0' * 32, expectedRoot=self.root)]:
            with self.assertRaisesRegex(ValueError, '資料庫已切換'):
                operation()
        self.assertEqual((self.root / INBOX_FILE).read_bytes(), first_bytes)
        self.assertEqual((second / INBOX_FILE).read_bytes(), second_bytes)
        original_save = self.service._save_inbox
        external = DocumentLibraryService(self.config)

        def switch_before_save(entries):
            external.select(str(self.root))
            original_save(entries)

        with patch.object(self.service, '_save_inbox', side_effect=switch_before_save):
            cleared = self.service.clear_archive(expectedRoot=second)
        self.assertEqual(cleared['root'], str(second.resolve()))
        self.assertEqual(cleared['clearedCount'], 1)
        self.assertEqual((self.root / INBOX_FILE).read_bytes(), first_bytes)
        with self.assertRaisesRegex(ValueError, '資料庫已切換'):
            self.service.restore_archive(cleared['undoToken'], expectedRoot=second)
        self.service.select(str(second))
        self.assertEqual(self.service.restore_archive(cleared['undoToken'], expectedRoot=second)['restoredCount'], 1)

    def test_archive_rejects_inconsistent_persisted_states_without_rewriting(self):
        self.service.select(str(self.root))
        self.register()
        registry = self.root / INBOX_FILE
        original = json.loads(registry.read_text(encoding='utf-8'))
        for changes in [{'status': 'invalid'}, {'status': []}, {'status': 'archive'},
                        {'status': 'cleared', 'read': True, 'readAt': '2026-09-28'},
                        {'clearBatch': '0' * 32, 'clearedAt': '2026-09-28'}]:
            data = {**original, 'entries': [{**original['entries'][0], **changes}]}
            registry.write_text(json.dumps(data), encoding='utf-8')
            original_bytes = registry.read_bytes()
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, '原檔案已保留'):
                self.service.clear_archive()
            self.assertEqual(registry.read_bytes(), original_bytes)

    def test_inbox_validates_paths_and_explicit_read_values(self):
        self.service.select(str(self.root))
        for path in ['../outside.md', str(self.root / 'reports' / '狀態.md'), 'README.md',
                     'reports/../README.md', 'reports/not-found.md', 'reports/run.ps1', 'C:outside.md']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.register(path=path)
        (self.root / 'reports' / 'empty.md').write_text('  \n', encoding='utf-8')
        (self.root / 'reports' / 'binary.md').write_bytes(b'\xff')
        for path in ['reports/empty.md', 'reports/binary.md']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.register(path=path)
        for changes in [{'id': '../invalid'}, {'title': ''}, {'createdAt': 'yesterday'},
                        {'createdAt': '2026-09-28T12:00:00'}, {'summary': '<script>\nline break'}, {'source': []}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.register(**changes)
        self.assertEqual(self.service.inbox()['totalCount'], 0)
        self.register()
        for read in [None, 'false', 0, 1, [], {}]:
            with self.subTest(read=read), self.assertRaises(ValueError):
                self.service.mark_report_read('cosha-unity-v1', read)
        with self.assertRaises(ValueError):
            self.service.mark_report_read('unknown-id', True)
        self.assertEqual(self.service.inbox()['unreadCount'], 1)

    def test_inbox_corruption_and_failed_replace_preserve_previous_bytes(self):
        self.service.select(str(self.root))
        self.register()
        registry = self.root / INBOX_FILE
        original = registry.read_bytes()
        with patch('document_library.os.replace', side_effect=OSError('test disk failure')):
            with self.assertRaises(OSError):
                self.service.mark_report_read('cosha-unity-v1', True)
        self.assertEqual(registry.read_bytes(), original)
        self.assertFalse(list(self.root.glob(INBOX_FILE + '.*.tmp')))
        registry.write_bytes(b'{broken')
        with self.assertRaisesRegex(ValueError, '原檔案已保留'):
            self.register(identifier='different-id')
        self.assertEqual(registry.read_bytes(), b'{broken')

    def test_inbox_multi_instance_lock_and_root_isolation(self):
        self.service.select(str(self.root))
        self.register()
        another = DocumentLibraryService(self.config)
        with self.service._inbox_write_lock():
            with self.assertRaisesRegex(ValueError, '另一個 Console'):
                another.mark_report_read('cosha-unity-v1', True)
        self.assertEqual(another.mark_report_read('cosha-unity-v1', True)['unreadCount'], 0)
        self.register(identifier='cosha-blender-v1')
        history = another.inbox()
        self.assertEqual(history['totalCount'], 2)
        self.assertEqual(history['unreadCount'], 1)
        second_root = self.base / 'second-root'
        second_root.mkdir()
        self.service.select(str(second_root))
        self.assertEqual(self.service.inbox()['totalCount'], 0)
        self.service.select(str(self.root))
        self.assertEqual(self.service.inbox()['totalCount'], 2)

    def test_inbox_rejects_report_and_registry_links_outside_root(self):
        self.service.select(str(self.root))
        outside = self.base / 'outside.md'
        outside.write_text('# Outside', encoding='utf-8')
        report_link = self.root / 'reports' / 'link.md'
        try:
            report_link.symlink_to(outside)
        except OSError:
            self.skipTest('Creating symbolic links is unavailable on this Windows account.')
        with self.assertRaises(ValueError):
            self.register(path='reports/link.md')
        registry = self.root / INBOX_FILE
        registry.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.service.inbox()
        self.assertEqual(outside.read_text(encoding='utf-8'), '# Outside')

    def test_overview_includes_one_current_memory_read_without_history(self):
        self.service.select(str(self.root))
        values = {'availableBytes': 250 * 1024 * 1024, 'totalBytes': 16 * 1024 ** 3, 'usedPercent': 98}
        with patch('document_library._windows_memory_values', return_value=values) as reader:
            overview = self.service.overview()
        reader.assert_called_once_with()
        self.assertIsNone(overview['sampledAt'])
        self.assertEqual(overview['currentMemory']['status'], 'available')
        self.assertEqual(overview['currentMemory']['availableBytes'], values['availableBytes'])
        self.assertEqual(overview['currentMemory']['usedBytes'], values['totalBytes'] - values['availableBytes'])
        self.assertEqual(overview['currentMemory']['source'], 'GlobalMemoryStatusEx')
        self.assertRegex(overview['currentMemory']['readAt'], r'[+-]\d\d:\d\d$')
        with patch('document_library._windows_memory_values', side_effect=OSError('test unavailable')):
            unknown = current_memory()
        self.assertEqual(unknown['status'], 'unavailable')
        self.assertIsNone(unknown['availableBytes'])
        self.assertIsNone(unknown['totalBytes'])
        self.assertIsNone(unknown['usedBytes'])
        self.assertIn('test unavailable', unknown['reason'])
        (self.root / 'snapshots').mkdir()
        history = {'id': 'old', 'status': 'completed', 'sampledAt': '2026-09-27T01:00:00+08:00',
                   'system': {'visiblePhysicalBytes': 16 * 1024 ** 3, 'availablePhysicalBytes': 2 * 1024 ** 3}}
        (self.root / 'snapshots' / 'old.json').write_text(json.dumps(history), encoding='utf-8')
        with patch('document_library._windows_memory_values', return_value=values) as reader, \
                patch('document_library.device_library.list_snapshots', return_value=[{'id': 'old'}]):
            overview = self.service.overview()
        reader.assert_called_once_with()
        self.assertEqual(overview['sampledAt'], history['sampledAt'])
        self.assertEqual(overview['availableBytes'], 2 * 1024 ** 3)
        self.assertEqual(overview['currentMemory']['availableBytes'], 250 * 1024 * 1024)

    def write_device_fixture(self, *, root=None, model='Fixture laptop', details=None, hardware=None):
        root = root or self.root
        (root / 'snapshots').mkdir(exist_ok=True)
        snapshot = {'schemaVersion': 1, 'id': 'overview-fixture', 'status': 'completed', 'sampledAt': '2026-09-27T01:00:00+08:00',
                    'system': {'visiblePhysicalBytes': 16 * 1024 ** 3, 'availablePhysicalBytes': 2 * 1024 ** 3,
                               'installedPhysicalBytes': 16 * 1024 ** 3},
                    'hardware': {'model': model, **(hardware or {})},
                    'gpu': {'dedicatedUsedBytes': 999999999, 'maxEngineUtilizationPercent': 99}}
        (root / 'snapshots' / 'overview-fixture.json').write_text(json.dumps(snapshot), encoding='utf-8')
        if details is not None:
            (root / DEVICE_DETAILS_FILE).write_text(json.dumps(details), encoding='utf-8')
        return snapshot

    def details_fixture(self, model='Fixture laptop'):
        # Synthetic values, never the user's private recollection or device record.
        return {'schemaVersion': 1, 'model': model, 'purchase': {'amount': 1234.5, 'currency': 'CNY',
                'approximate': True, 'source': 'user-recollection', 'year': 2019, 'yearApproximate': True}, 'color': None}

    def test_overview_returns_hardware_whitelists_and_never_saved_gpu_usage_as_current(self):
        self.service.select(str(self.root))
        hardware = {'sampledAt': '2026-09-27T00:00:00+08:00',
                    'cpus': [{'name': 'Fixture CPU', 'cores': 8, 'logicalProcessors': 16, 'serial': 'do-not-return'}],
                    'memoryModules': [{'capacityBytes': 8 * 1024 ** 3, 'speedMHz': 3200, 'configuredSpeedMHz': 2933,
                                       'serial': 'do-not-return'}, None],
                    'gpus': [{'name': 'Fixture GPU', 'driverVersion': '1.2.3', 'dedicatedCapacityBytes': None,
                              'capacityReason': 'capacity unknown', 'AdapterRAM': 2147483648}]}
        snapshot = self.write_device_fixture(hardware=hardware)
        with patch('document_library._windows_memory_values', return_value={'totalBytes': 1000, 'availableBytes': 0, 'usedPercent': 100}), \
                patch('document_library.current_gpu', return_value={'readAt': 'now', 'status': 'unavailable', 'source': 'nvidia-smi',
                       'reason': 'unknown', 'adapters': []}) as gpu:
            result = self.service.overview()
        gpu.assert_called_once_with()
        self.assertEqual(result['currentMemory']['usedBytes'], 1000)
        self.assertEqual(result['currentMemory']['availableBytes'], 0)
        self.assertEqual(result['cpus'], [{'name': 'Fixture CPU', 'cores': 8, 'logicalProcessors': 16}])
        self.assertEqual(result['memoryModules'], [{key: hardware['memoryModules'][0][key] for key in ('capacityBytes', 'speedMHz', 'configuredSpeedMHz')}])
        self.assertNotIn('AdapterRAM', result['gpus'][0])
        self.assertIsNone(result['gpus'][0]['dedicatedCapacityBytes'])
        self.assertEqual(result['hardwareSampledAt'], hardware['sampledAt'])
        self.assertEqual(result['sampledAt'], snapshot['sampledAt'])
        self.assertEqual(result['currentGpu'], [])
        self.assertEqual(result['currentGpuRead']['status'], 'unavailable')

    def test_memory_unknown_and_invalid_values_are_never_zero(self):
        for values in ({'totalBytes': 0, 'availableBytes': 0}, {'totalBytes': 100, 'availableBytes': 101},
                       {'totalBytes': True, 'availableBytes': 0}, {'totalBytes': 100, 'availableBytes': -1}):
            with self.subTest(values=values), patch('document_library._windows_memory_values', return_value=values):
                result = current_memory()
                self.assertEqual(result['status'], 'unavailable')
                self.assertIsNone(result['usedBytes'])

    def test_gpu_multi_adapter_same_name_csv_quoted_name_and_real_zero(self):
        text = '0, "Fixture, GPU", 00000000:01:00.0, 6144, 0, 5995, N/A, N/A\n1, "Fixture, GPU", 00000000:02:00.0, 8192, 2000, 6000, 25, 42\n'
        with patch('document_library._nvidia_smi_path', return_value=Path('fixed-driver.exe')), \
                patch('document_library._gpu_query_output', return_value=text) as query:
            result = current_gpu()
        query.assert_called_once_with(Path('fixed-driver.exe'))
        self.assertEqual(result['status'], 'available')
        first, second = result['adapters']
        self.assertEqual(first['totalBytes'], 6 * 1024 ** 3)
        self.assertEqual(first['usedBytes'], 0)
        self.assertEqual(first['freeBytes'], 5995 * 1048576)
        self.assertIsNone(first['utilizationPercent'])
        self.assertIsNone(first['temperatureC'])
        self.assertNotEqual(first['adapterId'], second['adapterId'])
        self.assertEqual(second['utilizationPercent'], 25)
        self.assertEqual(second['temperatureC'], 42)

    def test_gpu_na_illegal_counters_do_not_poison_valid_capacity_or_other_optional_values(self):
        for text in ('0, Fixture GPU, N/A, 6144, N/A, 0, 100, 0',
                     '0, Fixture GPU, N/A, 6144, 6145, -1, 101, 300'):
            with self.subTest(text=text), patch('document_library._nvidia_smi_path', return_value=Path('fixed-driver.exe')), \
                    patch('document_library._gpu_query_output', return_value=text):
                result = current_gpu()
            self.assertEqual(result['status'], 'partial')
            adapter = result['adapters'][0]
            self.assertEqual(adapter['totalBytes'], 6 * 1024 ** 3)
            self.assertIsNone(adapter['usedBytes'])
        self.assertIsNone(adapter['freeBytes'])
        self.assertIsNone(adapter['utilizationPercent'])
        self.assertIsNone(adapter['temperatureC'])

    def test_gpu_missing_driver_failed_or_malformed_output_remains_unavailable(self):
        with patch('document_library._nvidia_smi_path', return_value=None), patch('document_library._gpu_query_output') as query:
            self.assertEqual(current_gpu()['adapters'], [])
        query.assert_not_called()
        for output in ('', 'not,a,gpu', '0,GPU,0000:01:00.0,1,0,0,0,0\n1,GPU,0000:01:00.0,1,0,0,0,0'):
            with self.subTest(output=output), patch('document_library._nvidia_smi_path', return_value=Path('fixed-driver.exe')), \
                    patch('document_library._gpu_query_output', return_value=output):
                result = current_gpu()
                self.assertEqual(result['status'], 'unavailable')
                self.assertEqual(result['adapters'], [])

    def test_gpu_query_is_hidden_once_bounded_and_cleans_its_own_timeout_child(self):
        calls, children = [], []
        def spawn(args, **kwargs):
            calls.append((args, kwargs))
            class Child:
                returncode = None
                killed = False
                def wait(self, timeout):
                    if not self.killed:
                        raise subprocess.TimeoutExpired(args, timeout)
                    self.returncode = -1
                    return -1
                def poll(self):
                    return self.returncode
                def kill(self):
                    self.killed = True
            child = Child()
            children.append(child)
            return child
        with patch('document_library._nvidia_smi_path', return_value=Path('fixed-driver.exe')), \
                patch('document_library.subprocess.Popen', side_effect=spawn):
            result = current_gpu()
        self.assertEqual(len(calls), 1)
        self.assertTrue(children[0].killed)
        self.assertFalse(calls[0][1]['shell'])
        self.assertEqual(calls[0][1]['stdin'], subprocess.DEVNULL)
        self.assertEqual(result['status'], 'unavailable')
        self.assertIn('2 秒', result['reason'])

    def test_gpu_query_limits_output_and_rejects_failed_exit(self):
        def spawn(output, returncode):
            def fake(args, **kwargs):
                kwargs['stdout'].write(output)
                class Child:
                    def wait(self, timeout):
                        self.returncode = returncode
                    def poll(self):
                        return self.returncode
                return Child()
            return fake
        for output, code in ((b'x' * (MAX_GPU_QUERY_BYTES + 1), 0), (b'', 1)):
            with self.subTest(code=code), patch('document_library._nvidia_smi_path', return_value=Path('fixed-driver.exe')), \
                    patch('document_library.subprocess.Popen', side_effect=spawn(output, code)):
                self.assertEqual(current_gpu()['status'], 'unavailable')

    def test_gpu_does_not_resolve_a_driver_from_path_or_the_selected_library(self):
        with patch('document_library.Path.is_file', return_value=True), patch('document_library.Path.is_symlink', return_value=False), \
                patch.dict('document_library.os.environ', {'SystemRoot': r'C:\Windows', 'ProgramFiles': r'C:\Program Files',
                                                        'PATH': str(self.root)}):
            self.assertEqual(document_library._nvidia_smi_path(), Path(r'C:\Windows\System32\nvidia-smi.exe'))

    def test_device_details_are_model_bound_bounded_whitelisted_and_read_only(self):
        self.service.select(str(self.root))
        details = self.details_fixture(' fixture LAPTOP ')
        details['privateExtra'] = 'never-return'
        details['purchase']['receiptPath'] = 'never-return'
        self.write_device_fixture(details=details)
        path = self.root / DEVICE_DETAILS_FILE
        before, settings = path.read_bytes(), self.config.read_bytes()
        result = self.service.overview()['deviceDetails']
        self.assertEqual(result['status'], 'available')
        self.assertEqual(result['purchase']['amount'], 1234.5)
        self.assertTrue(result['purchase']['approximate'])
        self.assertTrue(result['purchase']['yearApproximate'])
        self.assertIsNone(result['color'])
        self.assertNotIn('receiptPath', result['purchase'])
        self.assertNotIn('privateExtra', result)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.config.read_bytes(), settings)
        details['model'] = 'Other laptop'
        path.write_text(json.dumps(details), encoding='utf-8')
        result = self.service.overview()['deviceDetails']
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['purchase'])

    def test_bad_device_details_and_absent_model_preserve_overview(self):
        self.service.select(str(self.root))
        self.write_device_fixture()
        path = self.root / DEVICE_DETAILS_FILE
        invalid = [b'\xff', b'{', b'[' * 1100 + b']' * 1100, b'x' * (MAX_DEVICE_DETAILS_BYTES + 1)]
        for update in ({'schemaVersion': True}, {'purchase': {**self.details_fixture()['purchase'], 'amount': float('nan')}},
                       {'purchase': {**self.details_fixture()['purchase'], 'amount': 0}},
                       {'purchase': {**self.details_fixture()['purchase'], 'amount': -0.0}},
                       {'purchase': {**self.details_fixture()['purchase'], 'amount': True}},
                       {'purchase': {**self.details_fixture()['purchase'], 'year': True}}, {'color': '../' * 30}):
            details = self.details_fixture()
            details.update(update)
            invalid.append(json.dumps(details).encode('utf-8'))
        for raw in invalid:
            with self.subTest(length=len(raw)):
                path.write_bytes(raw)
                result = self.service.overview()
                self.assertEqual(result['model'], 'Fixture laptop')
                self.assertEqual(result['deviceDetails']['status'], 'unavailable')
                self.assertIsNone(result['deviceDetails']['purchase'])
        self.write_device_fixture(model=None, details=self.details_fixture())
        self.assertIsNone(self.service.overview()['deviceDetails']['purchase'])

    def test_device_details_link_and_directory_are_not_read(self):
        self.service.select(str(self.root))
        self.write_device_fixture()
        path, outside = self.root / DEVICE_DETAILS_FILE, self.base / 'outside-device.json'
        outside.write_text(json.dumps(self.details_fixture()), encoding='utf-8')
        try:
            path.symlink_to(outside)
        except OSError:
            self.skipTest('symlink creation unavailable')
        before = outside.read_bytes()
        self.assertEqual(self.service.overview()['deviceDetails']['status'], 'unavailable')
        self.assertEqual(outside.read_bytes(), before)
        path.unlink()
        path.mkdir()
        self.assertEqual(self.service.overview()['deviceDetails']['status'], 'unavailable')

    def test_device_details_exact_size_limit_is_accepted(self):
        self.service.select(str(self.root))
        self.write_device_fixture(details=self.details_fixture())
        path = self.root / DEVICE_DETAILS_FILE
        raw = path.read_bytes()
        path.write_bytes(raw + b' ' * (MAX_DEVICE_DETAILS_BYTES - len(raw)))
        self.assertEqual(self.service.overview()['deviceDetails']['status'], 'available')
        path.write_bytes(path.read_bytes() + b' ')
        self.assertEqual(self.service.overview()['deviceDetails']['status'], 'unavailable')

    def test_overview_pins_hardware_and_private_details_while_external_settings_change(self):
        self.service.select(str(self.root))
        self.write_device_fixture(details=self.details_fixture())
        other = self.base / 'other-library'
        other.mkdir()
        details = self.details_fixture('Other laptop')
        details['purchase']['amount'] = 999
        self.write_device_fixture(root=other, model='Other laptop', details=details)
        def switch_settings():
            self.config.write_text(json.dumps({'root': str(other)}), encoding='utf-8')
            return {'readAt': 'now', 'status': 'unavailable', 'source': 'fixture', 'reason': 'fixture', 'adapters': []}
        with patch('document_library.current_gpu', side_effect=switch_settings) as gpu, \
                patch('document_library._windows_memory_values', return_value={'totalBytes': 1000, 'availableBytes': 100, 'usedPercent': 90}) as memory:
            result = self.service.overview()
        gpu.assert_called_once_with()
        memory.assert_called_once_with()
        self.assertEqual(result['root'], str(self.root.resolve()))
        self.assertEqual(result['model'], 'Fixture laptop')
        self.assertEqual(result['deviceDetails']['purchase']['amount'], 1234.5)
        self.assertEqual(self.service.state()['root'], str(other))

    def test_storage_aggregate_is_anonymous_deduplicated_and_unknown_is_not_zero(self):
        records = [{'identity': 'volume-a', 'totalBytes': 1000, 'freeBytes': 0},
                   {'identity': 'VOLUME-A', 'totalBytes': 1000, 'freeBytes': 0},
                   {'identity': 'volume-b', 'totalBytes': 2000, 'freeBytes': 500}]
        with patch('document_library._windows_storage_volumes', return_value=records) as reader:
            result = current_storage()
        reader.assert_called_once_with()
        self.assertEqual((result['totalBytes'], result['usedBytes'], result['freeBytes']), (3000, 2500, 500))
        self.assertEqual(result['status'], 'available')
        self.assertNotIn('volume-a', json.dumps(result))
        with patch('document_library._windows_storage_volumes', return_value=[records[0], {'error': True}]):
            self.assertEqual(current_storage()['status'], 'partial')
        with patch('document_library._windows_storage_volumes', return_value=[{'identity': 'bad', 'totalBytes': 100, 'freeBytes': 101}]):
            result = current_storage()
            self.assertEqual(result['status'], 'unavailable')
            self.assertIsNone(result['totalBytes'])
        too_large = [{'identity': str(i), 'totalBytes': 2 ** 53 - 1, 'freeBytes': 0} for i in range(2)]
        with patch('document_library._windows_storage_volumes', return_value=too_large):
            result = current_storage()
            self.assertEqual(result['status'], 'unavailable')
            self.assertIsNone(result['totalBytes'])

    def test_native_storage_filters_usb_network_and_unknown_backing_and_closes_handles(self):
        class NativeFunction:
            def __init__(self, callback):
                self.callback = callback
            def __call__(self, *args):
                return self.callback(*args)

        # C and E are aliases of one local volume; D is an external fixed USB
        # SSD. F is Spaces with unknown backing, G network, H a failed local
        # volume read, I a disappeared root, J an invalid handle, K failed IOCTL.
        identities = {'C': 'local', 'D': 'usb', 'E': 'LOCAL', 'F': 'spaces',
                      'H': 'failed', 'J': 'bad-handle', 'K': 'bad-query'}
        buses = {'local': 17, 'usb': 7, 'spaces': 16, 'failed': 11, 'bad-query': 17}
        handles, closed, free_reads, opens = {}, [], [], []
        def set_u64(pointer, value):
            ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint64)).contents.value = value
        def volume_name(mount, output, length):
            output.value = '\\\\?\\Volume{' + identities[mount[0]] + '}\\'
            return 1
        def create_file(path, access, share, security, disposition, flags, template):
            self.assertEqual((access, share, disposition), (0, 3, 3))
            self.assertFalse(path.endswith('\\'))
            identity = path.split('{')[1].split('}')[0].lower()
            opens.append(identity)
            if identity == 'bad-handle':
                return ctypes.c_void_p(-1).value
            handle = len(handles) + 1
            handles[handle] = identity
            return handle
        def ioctl(handle, code, query, query_size, output, output_size, returned, overlapped):
            self.assertEqual((code, query_size, output_size), (0x2D1400, 12, 4096))
            self.assertEqual(ctypes.string_at(query, 8), b'\0' * 8)
            identity = handles[handle]
            if identity == 'bad-query':
                return 0
            raw = bytearray(40)
            raw[:4], raw[4:8], raw[28:32] = (40).to_bytes(4, 'little'), (40).to_bytes(4, 'little'), buses[identity].to_bytes(4, 'little')
            ctypes.memmove(output, bytes(raw), len(raw))
            ctypes.cast(returned, ctypes.POINTER(ctypes.c_uint32)).contents.value = len(raw)
            return 1
        def free_space(mount, available, total, volume_free):
            free_reads.append(mount)
            if mount[0] == 'H':
                return 0
            set_u64(available, 100)
            set_u64(total, 1000)
            set_u64(volume_free, 200)
            return 1
        class Kernel:
            GetLogicalDrives = NativeFunction(lambda: sum(1 << (ord(letter) - 65) for letter in 'CDEFGHIJK'))
            GetDriveTypeW = NativeFunction(lambda mount: 4 if mount[0] == 'G' else 1 if mount[0] == 'I' else 3)
            GetVolumeNameForVolumeMountPointW = NativeFunction(volume_name)
            CreateFileW = NativeFunction(create_file)
            DeviceIoControl = NativeFunction(ioctl)
            GetDiskFreeSpaceExW = NativeFunction(free_space)
            CloseHandle = NativeFunction(lambda handle: closed.append(handle) or 1)
        with patch('document_library.ctypes.WinDLL', return_value=Kernel()):
            records = document_library._windows_storage_volumes()
        self.assertEqual(opens.count('local'), 1)
        self.assertEqual(free_reads, ['C:\\', 'H:\\'])
        self.assertCountEqual(closed, handles)
        with patch('document_library._windows_storage_volumes', return_value=records):
            result = current_storage()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual((result['totalBytes'], result['usedBytes'], result['freeBytes']), (1000, 900, 100))
        self.assertNotIn('Volume{', json.dumps(result))
        self.assertNotIn('C:', json.dumps(result))

    def test_async_duplicate_and_failure_keep_documents(self):
        self.service.select(str(self.root))
        started = threading.Event()
        finish = threading.Event()

        def fake_collect(*args, **kwargs):
            started.set()
            finish.wait(5)
            raise RuntimeError('test sampler unavailable')

        with patch('document_library.device_library.collect', side_effect=fake_collect):
            self.assertEqual(self.service.collect('固定場景')['status'], 'running')
            self.assertTrue(started.wait(2))
            self.assertEqual(self.service.sample_status()['status'], 'running')
            with self.assertRaises(ValueError):
                self.service.collect('duplicate')
            with self.assertRaises(ValueError):
                self.service.select(str(self.root))
            finish.set()
            self.service._worker.join(5)
        self.assertEqual(self.service.sample_status()['status'], 'failed')
        self.assertIn('電腦', self.service.read('README.md')['content'])

    def test_http_read_host_origin_and_path_boundaries(self):
        import world_console
        self.service.select(str(self.root))
        with patch.object(world_console, 'DOCUMENT_LIBRARY', self.service):
            server = world_console.ConsoleHTTPServer(('127.0.0.1', 0), world_console.ConsoleHandler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            port = server.server_address[1]

            def get(path, headers=None):
                client = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                try:
                    client.request('GET', path, headers=headers or {})
                    response = client.getresponse()
                    return response.status, json.loads(response.read())
                finally:
                    client.close()

            def post(path, payload, headers=None):
                client = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                try:
                    client.request('POST', path, body=json.dumps(payload),
                                   headers={'Content-Type': 'application/json', **(headers or {})})
                    response = client.getresponse()
                    return response.status, json.loads(response.read())
                finally:
                    client.close()

            try:
                code, body = get('/api/documents/read?path=README.md')
                self.assertEqual(code, 200)
                self.assertIn('電腦', body['content'])
                self.assertEqual(get('/api/documents/state', {'Host': 'attacker.example'})[0], 403)
                self.assertEqual(get('/api/documents/state', {'Sec-Fetch-Site': 'cross-site'})[0], 403)
                self.assertEqual(get('/api/documents/state', {'Origin': 'https://attacker.example'})[0], 403)
                self.assertEqual(get('/api/documents/read?path=../outside.md')[0], 400)
                report = {'id': 'cosha-http-v1', 'title': 'HTTP 登記報告', 'summary': '只在暫存資料庫驗證。',
                          'source': 'test', 'createdAt': '2026-09-28', 'path': 'reports/狀態.md'}
                self.assertEqual(get('/api/documents/inbox', {'Host': 'attacker.example'})[0], 403)
                self.assertEqual(get('/api/documents/inbox', {'Origin': 'https://attacker.example'})[0], 403)
                self.assertEqual(post('/api/documents/inbox/register', report, {'Host': 'attacker.example'})[0], 403)
                self.assertEqual(post('/api/documents/inbox/register', report, {'Origin': 'https://attacker.example'})[0], 403)
                self.assertEqual(post('/api/documents/inbox/register', report, {'Sec-Fetch-Site': 'cross-site'})[0], 403)
                code, body = post('/api/documents/inbox/register', report)
                self.assertEqual(code, 200)
                self.assertTrue(body['created'])
                self.assertEqual(get('/api/documents/inbox')[1]['unreadCount'], 1)
                self.assertEqual(get('/api/documents/read?path=' + quote(report['path']))[0], 200)
                self.assertEqual(get('/api/documents/inbox')[1]['unreadCount'], 1)
                self.assertEqual(post('/api/documents/inbox/read', {'id': report['id'], 'read': True},
                                      {'Origin': 'https://attacker.example'})[0], 403)
                self.assertEqual(post('/api/documents/inbox/read', {'id': report['id'], 'read': 'false'})[0], 400)
                code, body = post('/api/documents/inbox/read', {'id': report['id'], 'read': True})
                self.assertEqual(code, 200)
                self.assertEqual(body['unreadCount'], 0)
                self.assertEqual(body['totalCount'], 1)
                self.assertTrue(body['entries'][0]['read'])
                reopened = DocumentLibraryService(self.config)
                self.assertEqual(reopened.inbox()['entries'], body['entries'])
                code, duplicate = post('/api/documents/inbox/register', report)
                self.assertEqual(code, 200)
                self.assertFalse(duplicate['created'])
                self.assertEqual(duplicate['unreadCount'], 0)
                self.assertEqual(duplicate['totalCount'], 1)
                # A stale reader must neither read B's same path nor change B's same id.
                second = self.base / 'HTTP library B'
                (second / 'reports').mkdir(parents=True)
                (second / 'reports' / '狀態.md').write_text('# HTTP database B report', encoding='utf-8')
                self.service.select(str(second))
                self.service.register_report(**{**report, 'title': 'HTTP B same id'})
                first_bytes = (self.root / INBOX_FILE).read_bytes()
                second_bytes = (second / INBOX_FILE).read_bytes()
                old_root = quote(str(self.root))
                code, error = get('/api/documents/read?path=' + quote(report['path']) + '&expectedRoot=' + old_root)
                self.assertEqual(code, 400)
                self.assertIn('資料庫已切換', error['error'])
                self.assertEqual(get('/api/documents/inbox?expectedRoot=' + old_root)[0], 400)
                self.assertEqual(post('/api/documents/inbox/read',
                                      {'id': report['id'], 'read': True, 'expectedRoot': str(self.root)})[0], 400)
                self.assertEqual(get('/api/documents/inbox?expectedRoot=')[0], 400)
                self.assertEqual((self.root / INBOX_FILE).read_bytes(), first_bytes)
                self.assertEqual((second / INBOX_FILE).read_bytes(), second_bytes)
                matching_root = quote(str(second))
                code, document = get('/api/documents/read?path=' + quote(report['path']) + '&expectedRoot=' + matching_root)
                self.assertEqual(code, 200)
                self.assertIn('HTTP database B', document['content'])
                self.assertEqual(get('/api/documents/inbox?expectedRoot=' + matching_root)[1]['unreadCount'], 1)
                code, marked = post('/api/documents/inbox/read',
                                    {'id': report['id'], 'read': True, 'expectedRoot': str(second)})
                self.assertEqual(code, 200)
                self.assertEqual(marked['unreadCount'], 0)
                self.assertEqual((self.root / INBOX_FILE).read_bytes(), first_bytes)
                archived_bytes = (second / INBOX_FILE).read_bytes()
                archive_operations = [('/api/documents/inbox/move', {'id': report['id'], 'status': 'later'}),
                                      ('/api/documents/inbox/archive/clear', {}),
                                      ('/api/documents/inbox/archive/restore', {'undoToken': '0' * 32})]
                for endpoint, payload in archive_operations:
                    self.assertEqual(post(endpoint, {**payload, 'expectedRoot': str(self.root)})[0], 400)
                    self.assertEqual(post(endpoint, {**payload, 'expectedRoot': str(second)},
                                          {'Origin': 'https://attacker.example'})[0], 403)
                self.assertEqual((second / INBOX_FILE).read_bytes(), archived_bytes)
                self.assertEqual((self.root / INBOX_FILE).read_bytes(), first_bytes)
                code, later = post('/api/documents/inbox/move',
                                   {'id': report['id'], 'status': 'later', 'expectedRoot': str(second)})
                self.assertEqual(code, 200)
                self.assertEqual(later['item']['status'], 'later')
                self.assertFalse(later['item']['read'])
                self.assertEqual((later['inboxCount'], later['laterCount'], later['archiveCount'], later['unreadCount']), (0, 1, 0, 1))
                code, archived = post('/api/documents/inbox/read',
                                      {'id': report['id'], 'read': True, 'expectedRoot': str(second)})
                self.assertEqual(code, 200)
                self.assertEqual(archived['item']['status'], 'archive')
                report_bytes = (second / 'reports' / '狀態.md').read_bytes()
                code, cleared = post('/api/documents/inbox/archive/clear', {'expectedRoot': str(second)})
                self.assertEqual(code, 200)
                self.assertEqual(cleared['clearedCount'], 1)
                self.assertEqual(cleared['entries'], [])
                self.assertEqual(cleared['archiveCount'], 0)
                self.assertEqual(get('/api/documents/read?path=' + quote(report['path']) + '&expectedRoot=' + matching_root)[0], 200)
                self.assertEqual(post('/api/documents/inbox/register', report)[1]['totalCount'], 0)
                self.assertEqual(post('/api/documents/inbox/read',
                                      {'id': report['id'], 'read': False, 'expectedRoot': str(second)})[0], 400)
                self.assertEqual(post('/api/documents/inbox/move',
                                      {'id': report['id'], 'status': 'inbox', 'expectedRoot': str(second)})[0], 400)
                code, restored = post('/api/documents/inbox/archive/restore',
                                      {'undoToken': cleared['undoToken'], 'expectedRoot': str(second)})
                self.assertEqual(code, 200)
                self.assertEqual(restored['restoredCount'], 1)
                self.assertEqual(restored['entries'][0]['status'], 'archive')
                self.assertEqual(post('/api/documents/inbox/archive/restore',
                                      {'undoToken': cleared['undoToken'], 'expectedRoot': str(second)})[1]['restoredCount'], 0)
                self.assertEqual((second / 'reports' / '狀態.md').read_bytes(), report_bytes)
                self.assertEqual((self.root / INBOX_FILE).read_bytes(), first_bytes)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(5)


if __name__ == '__main__':
    unittest.main()
