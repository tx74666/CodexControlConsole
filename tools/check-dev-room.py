"""Isolated Dev Room persistence and HTTP checks; never writes to the user's library."""
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dev_room import DevRoomService, DevRoomConflict, DEV_ROOM_PARTS, MAX_BODY_BYTES
from document_library import DocumentLibraryService


class DevRoomChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='console-dev-room-')
        self.base = Path(self.temp.name)
        self.root = self.base / '中文 资料库'
        self.root.mkdir()
        self.settings = self.base / 'documents.json'
        self.select_root(self.root)
        self.library = DocumentLibraryService(self.settings)
        self.service = DevRoomService(self.library)

    def tearDown(self):
        self.temp.cleanup()

    def select_root(self, path):
        self.settings.write_text(json.dumps({'root': str(path.resolve())}, ensure_ascii=False), encoding='utf-8')

    def payload(self, id='overview', title='总案', body='', revision=''):
        return {'expectedRoot': str(self.root), 'id': id, 'title': title,
                'body': body, 'expectedRevision': revision}

    @property
    def storage(self):
        return self.root.joinpath(*DEV_ROOM_PARTS)

    def create_link(self, link, target):
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != 'nt':
                raise
            result = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(link), str(target)],
                                    capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                self.skipTest('This account cannot create an isolated test link or junction.')

    def test_first_read_is_virtual_and_never_creates_storage(self):
        before = list(self.root.rglob('*'))
        result = self.service.state(str(self.root))
        self.assertEqual(result['documents'], [{'id': 'overview', 'title': '总案', 'updatedAt': ''}])
        self.assertEqual(result['document'], {'id': 'overview', 'title': '总案', 'body': '',
                                             'revision': '', 'updatedAt': ''})
        self.assertEqual(list(self.root.rglob('*')), before)
        self.assertIsNone(self.service.state(str(self.root), str(uuid.uuid4()))['document'])
        self.assertEqual(list(self.root.rglob('*')), before)

    def test_chinese_markdown_exact_save_reopen_and_backup(self):
        title, body = '总案 <!-- 原稿 -->', '# Dev Room\r\n\r\n中文与英文 Nexus。\n无分类\n'
        first = self.service.save(self.payload(title=title, body=body))['document']
        original = (self.storage / 'overview.md').read_bytes()
        self.assertEqual(first['title'], title)
        self.assertEqual(first['body'], body)
        reopened = DevRoomService(DocumentLibraryService(self.settings))
        self.assertEqual(reopened.state(str(self.root))['document'], first)
        document_read = self.library.read('/'.join((*DEV_ROOM_PARTS, 'overview.md')), expectedRoot=str(self.root))
        self.assertIn('中文与英文', document_read['content'])
        second = reopened.save(self.payload(title='新总案', body='新正文', revision=first['revision']))['document']
        backup = self.storage / '.history' / 'overview' / (first['revision'] + '.md')
        self.assertEqual(backup.read_bytes(), original)
        self.assertNotEqual(first['revision'], second['revision'])
        self.assertEqual(second['body'], '新正文')

    def test_new_document_and_stale_revision_cannot_overwrite(self):
        id = str(uuid.uuid4())
        first = self.service.save(self.payload(id=id, title='文档一', body='原稿'))
        self.assertEqual(first['documents'][0]['id'], 'overview')
        self.assertEqual(first['document']['id'], id)
        revision = first['document']['revision']
        self.service.save(self.payload(id=id, title='文档一', body='较新稿', revision=revision))
        with self.assertRaises(DevRoomConflict):
            self.service.save(self.payload(id=id, title='文档一', body='旧页面的稿', revision=revision))
        with self.assertRaises(DevRoomConflict):
            self.service.save(self.payload(id=id, title='误当新稿', body='误覆盖'))
        self.assertEqual(self.service.state(str(self.root), id)['document']['body'], '较新稿')

    def test_external_edit_is_detected_as_revision_conflict(self):
        first = self.service.save(self.payload(body='原稿'))['document']
        path = self.storage / 'overview.md'
        external = path.read_bytes().replace('原稿'.encode(), '外部更新'.encode())
        path.write_bytes(external)
        with self.assertRaises(DevRoomConflict):
            self.service.save(self.payload(body='旧页保存', revision=first['revision']))
        self.assertEqual(path.read_bytes(), external)

    def test_root_switch_and_root_change_during_write_preserve_documents(self):
        first = self.service.save(self.payload(body='A 原稿'))['document']
        second_root = self.base / '另外的资料库'
        second_root.mkdir()
        self.select_root(second_root)
        with self.assertRaises(ValueError):
            self.service.state(str(self.root))
        with self.assertRaises(ValueError):
            self.service.save(self.payload(body='错误覆盖', revision=first['revision']))
        self.assertFalse(second_root.joinpath(*DEV_ROOM_PARTS).exists())
        self.select_root(self.root)
        normal_sync = os.fsync

        def switch_on_flush(fd):
            normal_sync(fd)
            self.select_root(second_root)

        with patch('dev_room.os.fsync', side_effect=switch_on_flush):
            with self.assertRaises(ValueError):
                self.service.save(self.payload(body='保存途中切换', revision=first['revision']))
        self.select_root(self.root)
        self.assertEqual(self.service.state(str(self.root))['document']['body'], 'A 原稿')
        self.assertFalse(second_root.joinpath(*DEV_ROOM_PARTS).exists())
        self.assertEqual(list(self.storage.rglob('*.tmp')), [])

    def test_disk_failure_preserves_original_and_does_not_leave_temporary_files(self):
        # CI may spell TEMP with a Windows 8.3 alias while the service resolves
        # it to a long path. Exercise equivalent alternate spelling everywhere.
        alias_parent = self.base / 'alternate spelling'
        alias_parent.mkdir()
        self.root = alias_parent / '..' / self.root.name
        first = self.service.save(self.payload(body='唯一原稿'))['document']
        document_path = self.storage / 'overview.md'
        resolved_document = document_path.resolve()
        self.assertNotEqual(document_path, resolved_document)
        original = document_path.read_bytes()
        with patch('dev_room.os.replace', side_effect=OSError('fixture disk failure')):
            with self.assertRaises(OSError):
                self.service.save(self.payload(body='新稿', revision=first['revision']))
        self.assertEqual((self.storage / 'overview.md').read_bytes(), original)
        self.assertEqual(list(self.storage.rglob('*.tmp')), [])
        # If the backup succeeds but replacement fails, the backup must be exact.
        real_replace = os.replace
        rejected_targets = []

        def reject_document(source, target):
            if Path(target).resolve() == resolved_document:
                rejected_targets.append(Path(target).resolve())
                raise OSError('fixture final replacement failure')
            real_replace(source, target)

        with patch('dev_room.os.replace', side_effect=reject_document):
            with self.assertRaises(OSError):
                self.service.save(self.payload(body='另一个新稿', revision=first['revision']))
        self.assertEqual(rejected_targets, [resolved_document])
        self.assertEqual((self.storage / 'overview.md').read_bytes(), original)
        self.assertEqual((self.storage / '.history' / 'overview' / (first['revision'] + '.md')).read_bytes(), original)
        self.assertEqual(list(self.storage.rglob('*.tmp')), [])

    def test_rejected_ids_sizes_and_payloads_create_no_document(self):
        for id in ('../outside', '..', 'C:\\outside', 'overview/other', 'a.md', 1):
            with self.subTest(id=id), self.assertRaises(ValueError):
                self.service.save(self.payload(id=id))
        for payload in (self.payload(title=''), self.payload(title='行\n标题'),
                        self.payload(body='中' * (MAX_BODY_BYTES // 3 + 1)),
                        self.payload(revision='invalid'), self.payload(body='\0'),
                        {**self.payload(), 'path': '../outside.md'},
                        {**self.payload(), 'expectedRoot': ''}):
            with self.subTest(payload=list(payload)), self.assertRaises(ValueError):
                self.service.save(payload)
        self.assertFalse(self.storage.exists())

    def test_junction_or_symlink_escape_is_rejected(self):
        outside = self.base / 'outside'
        outside.mkdir()
        link = self.root / 'projects'
        self.create_link(link, outside)
        with self.assertRaises(ValueError):
            self.service.state(str(self.root))
        with self.assertRaises(ValueError):
            self.service.save(self.payload(body='越界写入'))
        self.assertEqual(list(outside.iterdir()), [])

    def test_selected_root_replaced_by_junction_is_rejected(self):
        outside = self.base / 'outside'
        outside.mkdir()
        self.root.rmdir()
        self.create_link(self.root, outside)
        with self.assertRaises(ValueError):
            self.service.state(str(self.root))
        with self.assertRaises(ValueError):
            self.service.save(self.payload(body='错误跟随根链接'))
        self.assertEqual(list(outside.iterdir()), [])

    def test_concurrent_pages_keep_one_winner(self):
        first = self.service.save(self.payload(body='原稿'))['document']
        barrier = threading.Barrier(2)
        results = []

        def save(body):
            barrier.wait(5)
            try:
                self.service.save(self.payload(body=body, revision=first['revision']))
                results.append('saved')
            except DevRoomConflict:
                results.append('conflict')

        workers = [threading.Thread(target=save, args=(body,)) for body in ('页面一', '页面二')]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(5)
            self.assertFalse(worker.is_alive())
        self.assertCountEqual(results, ['saved', 'conflict'])
        self.assertIn(self.service.state(str(self.root))['document']['body'], ('页面一', '页面二'))

    def test_http_contract_permissions_conflict_and_validation(self):
        # Production bootstrap creates service state during import. Keep those
        # side effects in this fixture too, then restore the caller's environment.
        with patch.dict(os.environ, {
                'CODEX_CONTROL_DATA_DIR': str(self.base / 'server-data'),
                'LOCALAPPDATA': str(self.base / 'local-app-data'),
                'CODEX_CONTROL_PUBLISHER_STATE_FILE': str(self.base / 'publisher.json'),
                'CODEX_CONTROL_TEMP_DIR': str(self.base / 'server-temp')}):
            import world_console
        with patch.object(world_console, 'DEV_ROOM', self.service):
            server = world_console.ConsoleHTTPServer(('127.0.0.1', 0), world_console.ConsoleHandler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()

            def request(method, path, payload=None, headers=None):
                client = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=5)
                try:
                    client.request(method, path, body=json.dumps(payload) if payload is not None else None,
                                   headers={'Content-Type': 'application/json', **(headers or {})})
                    response = client.getresponse()
                    return response.status, json.loads(response.read())
                finally:
                    client.close()

            path = '/api/dev-room/state?' + urlencode({'expectedRoot': str(self.root)})
            try:
                self.assertEqual(request('GET', path)[0], 200)
                self.assertFalse(self.storage.exists())
                for headers in ({'Host': 'attacker.example'}, {'Origin': 'https://attacker.example'},
                                {'Sec-Fetch-Site': 'cross-site'}):
                    self.assertEqual(request('GET', path, headers=headers)[0], 403)
                    self.assertEqual(request('POST', '/api/dev-room/save', self.payload(), headers)[0], 403)
                with patch.object(world_console, '_client_address_is_loopback', return_value=False):
                    self.assertEqual(request('GET', path)[0], 403)
                    self.assertEqual(request('POST', '/api/dev-room/save', self.payload())[0], 403)
                self.assertFalse(self.storage.exists())
                self.assertEqual(request('GET', '/api/dev-room/state')[0], 400)
                self.assertEqual(request('GET', path + '&id=../outside')[0], 400)
                self.assertEqual(request('GET', path + '&expectedRoot=duplicate')[0], 400)
                self.assertEqual(request('POST', '/api/dev-room/save', [])[0], 400)
                self.assertEqual(request('POST', '/api/dev-room/save?x=1', self.payload())[0], 400)
                code, first = request('POST', '/api/dev-room/save', self.payload(body='HTTP 原稿'))
                self.assertEqual(code, 200)
                self.assertEqual(first['document']['body'], 'HTTP 原稿')
                code, conflict = request('POST', '/api/dev-room/save', self.payload(body='旧页'))
                self.assertEqual(code, 409)
                self.assertEqual(conflict['code'], 'revision_conflict')
                self.assertEqual(request('GET', path)[1]['document']['body'], 'HTTP 原稿')
                with patch.object(self.service, 'save', side_effect=OSError('fixture disk unavailable')):
                    self.assertEqual(request('POST', '/api/dev-room/save', self.payload())[0], 503)
            finally:
                server.shutdown()
                worker.join(5)
                server.server_close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
