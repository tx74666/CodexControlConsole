"""Isolated bilingual persistence checks; never reads or writes the user's library."""
import hashlib
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
from dev_room import DevRoomService, DevRoomConflict, DEV_ROOM_PARTS, MAX_LOCALE_BYTES
from document_library import DocumentLibraryService


class DevRoomLocaleChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='console-dev-room-locales-')
        self.base = Path(self.temp.name)
        self.root = self.base / '中文 资料库'
        self.root.mkdir()
        self.settings = self.base / 'documents.json'
        self.select(self.root)
        self.catalog = self.base / 'translations.json'
        self.catalog.write_text('{"version":1,"documents":[]}', encoding='utf-8')
        self.library = DocumentLibraryService(self.settings)
        self.service = DevRoomService(self.library, self.catalog)
        self.identifier = str(uuid.uuid4())

    def tearDown(self):
        self.temp.cleanup()

    def select(self, root):
        self.settings.write_text(json.dumps({'root': str(root.resolve())}, ensure_ascii=False), encoding='utf-8')

    @property
    def storage(self):
        return self.root.joinpath(*DEV_ROOM_PARTS)

    def source_path(self, identifier=None):
        return self.storage / ((identifier or self.identifier) + '.md')

    def locale_path(self, identifier=None):
        return self.storage / '.locales' / ((identifier or self.identifier) + '.json')

    def state(self, language='zh', identifier=None):
        return self.service.state(str(self.root), identifier or self.identifier, language=language)['document']

    def payload(self, document=None, language='zh', identifier=None, title='中文文档', body='中文正文\r\n尾白  \t\n'):
        return {'expectedRoot': str(self.root), 'id': identifier or self.identifier, 'title': title,
                'body': body, 'expectedRevision': document['revision'] if document else '', 'language': language}

    def seed(self, catalog=True, canonical=False):
        body = '# Original\r\n\r\nOriginal body  \t\n'
        zh, en = '# 中文标题\r\n中文正文  \t\n', '# English title\r\nEnglish body  \t\n'
        if canonical:
            header = '<!-- rr-dev-room:v1 {"id":"project-introduction","guid":"cf983df9a9ce17a45a8cc3e108eae281"} -->\n'
            scaffold = '\n\n<!-- rr-dev-room:summary -->\n{summary}\n<!-- rr-dev-room:summary-end -->\n\n<!-- rr-dev-room:section 0 -->\n## {section}\n{body}\n<!-- rr-dev-room:section-end 0 -->\n\n'
            body = header + '# Original' + scaffold.format(summary='Original summary', section='Original section', body='Original body')
            zh = header + '# 中文标题' + scaffold.format(summary='中文摘要', section='中文章节', body='中文正文')
            en = header + '# English title' + scaffold.format(summary='English summary', section='English section', body='English body')
        source = self.service.save({'expectedRoot': str(self.root), 'id': self.identifier,
                                   'title': 'Original', 'body': body, 'expectedRevision': ''})['document']
        if catalog:
            self.catalog.write_text(json.dumps({'version': 1, 'documents': [{
                'id': self.identifier, 'sourceTitle': source['title'],
                'sourceBodySha256': hashlib.sha256(body.encode('utf-8')).hexdigest(),
                'variants': {'zh': {'title': '中文标题', 'body': zh}, 'en': {'title': 'English title', 'body': en}}}]}, ensure_ascii=False), encoding='utf-8')
        return source

    def test_language_reads_are_real_exact_variants_and_never_write(self):
        source = self.seed(canonical=True)
        before = {str(path): path.read_bytes() for path in self.storage.rglob('*') if path.is_file()}
        zh, en = self.state(), self.state('en')
        self.assertEqual(zh['title'], '中文标题')
        self.assertEqual(en['title'], 'English title')
        self.assertIn('中文正文', zh['body'])
        self.assertIn('English body', en['body'])
        self.assertEqual(zh['revision'], en['revision'])
        self.assertEqual(zh['sourceRevision'], source['revision'])
        self.assertEqual(zh['sourceBody'], source['body'])
        self.assertFalse(zh['translationMissing'])
        self.assertEqual({str(path): path.read_bytes() for path in self.storage.rglob('*') if path.is_file()}, before)
        self.assertEqual(self.service.state(str(self.root), self.identifier)['document'], source)

    def test_two_languages_edit_independently_and_share_conflict_revision(self):
        self.seed()
        original = self.source_path().read_bytes()
        zh, en = self.state(), self.state('en')
        first = self.service.save(self.payload(zh))['document']
        self.assertEqual(first['body'], '中文正文\r\n尾白  \t\n')
        self.assertEqual(self.state('en')['title'], 'English title')
        with self.assertRaises(DevRoomConflict):
            self.service.save(self.payload(en, language='en', title='English edit', body='English content'))
        sidecar = self.locale_path().read_bytes()
        second = self.service.save(self.payload(self.state('en'), language='en', title='English edit', body='English content\r\n'))['document']
        self.assertEqual(second['body'], 'English content\r\n')
        self.assertEqual(self.state()['body'], first['body'])
        self.assertEqual(self.source_path().read_bytes(), original)
        backup = self.storage / '.history' / self.identifier / 'locales' / (hashlib.sha256(sidecar).hexdigest() + '.json')
        self.assertEqual(backup.read_bytes(), sidecar)

    def test_catalog_is_bound_to_exact_body_and_title_and_revision(self):
        self.seed()
        old = self.state()
        catalog = json.loads(self.catalog.read_text(encoding='utf-8'))
        catalog['documents'][0]['variants']['zh']['title'] = '新内置标题'
        self.catalog.write_text(json.dumps(catalog, ensure_ascii=False), encoding='utf-8')
        with self.assertRaises(DevRoomConflict):
            self.service.save(self.payload(old))
        self.assertEqual(self.state()['title'], '新内置标题')
        catalog['documents'][0]['sourceBodySha256'] = '0' * 64
        self.catalog.write_text(json.dumps(catalog), encoding='utf-8')
        self.assertTrue(self.state()['translationMissing'])
        self.assertEqual(self.state()['body'], '')
        self.assertEqual(self.state('en')['title'], 'Translation needed')

    def test_unknown_legacy_custom_document_never_guesses_source_language(self):
        self.seed(catalog=False)
        self.assertTrue(self.state()['translationMissing'])
        self.assertTrue(self.state('en')['translationMissing'])
        saved = self.service.save(self.payload(self.state('en'), language='en', title='My English version', body='Actual English text'))['document']
        self.assertEqual(saved['body'], 'Actual English text')
        self.assertTrue(self.state()['translationMissing'])
        self.assertEqual(self.state()['body'], '')

    def test_new_document_is_discoverable_and_records_source_language_once(self):
        self.assertIsNone(self.state())
        first = self.service.save(self.payload())['document']
        self.assertIn(self.identifier, [entry['id'] for entry in self.service.state(str(self.root))['documents']])
        original = self.source_path().read_bytes()
        locale = json.loads(self.locale_path().read_text(encoding='utf-8'))
        self.assertEqual(locale['sourceLanguage'], 'zh')
        self.assertFalse(first['translationMissing'])
        self.assertTrue(self.state('en')['translationMissing'])
        self.service.save(self.payload(self.state('en'), language='en', title='English document', body='English body'))
        self.assertEqual(self.source_path().read_bytes(), original)
        self.assertEqual(self.state()['body'], first['body'])

    def test_virtual_overview_language_read_does_not_create_any_files(self):
        before = list(self.root.rglob('*'))
        zh, en = self.state(identifier='overview'), self.state('en', 'overview')
        self.assertEqual((zh['title'], en['title']), ('总案', 'Overview'))
        self.assertEqual(zh['revision'], '')
        self.assertFalse(en['translationMissing'])
        self.assertEqual(list(self.root.rglob('*')), before)
        saved = self.service.save(self.payload(en, language='en', identifier='overview', title='Overview', body='My plan'))['document']
        self.assertEqual(saved['body'], 'My plan')
        self.assertTrue(self.source_path('overview').exists())

    def test_external_source_change_hides_all_stale_versions_and_rejects_old_page(self):
        source = self.seed()
        self.service.save(self.payload(self.state()))
        old = self.state('en')
        self.service.save({'expectedRoot': str(self.root), 'id': self.identifier, 'title': 'Changed source', 'body': 'New original', 'expectedRevision': source['revision']})
        for language in ('zh', 'en'):
            document = self.state(language)
            self.assertTrue(document['translationMissing'])
            self.assertEqual(document['body'], '')
        with self.assertRaises(DevRoomConflict):
            self.service.save(self.payload(old, language='en', title='Old English', body='Old content'))
        self.service.save(self.payload(self.state('en'), language='en', title='New English', body='Updated English'))
        self.assertTrue(self.state()['translationMissing'])

    def test_selected_root_changes_before_and_during_save_preserve_documents(self):
        self.seed()
        document = self.state()
        other = self.base / 'other'; other.mkdir()
        self.select(other)
        with self.assertRaises(ValueError):self.service.save(self.payload(document))
        self.select(self.root)
        real_atomic = self.service._atomic_write
        def switch(root, parts, content, before_replace=None):
            self.select(other)
            return real_atomic(root, parts, content, before_replace=before_replace)
        original = self.source_path().read_bytes()
        with patch.object(self.service, '_atomic_write', side_effect=switch):
            with self.assertRaises(ValueError):self.service.save(self.payload(document))
        self.assertEqual(self.source_path().read_bytes(), original)
        self.assertFalse(self.locale_path().exists())
        self.assertEqual(list(self.storage.rglob('*.tmp')), [])

    def test_orphan_locale_cannot_be_overwritten_as_a_new_document(self):
        self.service.save(self.payload())
        original = self.locale_path().read_bytes()
        self.source_path().unlink()
        self.assertIsNone(self.state())
        with self.assertRaises(DevRoomConflict):self.service.save(self.payload(body='Collision'))
        forged = self.payload(body='Collision')
        forged['expectedRevision'] = self.service._locale_revision(None, original, None)
        with self.assertRaises(DevRoomConflict):self.service.save(forged)
        self.assertEqual(self.locale_path().read_bytes(), original)
        self.assertFalse(self.source_path().exists())

    def test_recorded_source_language_fallback_requires_matching_source_revision(self):
        created = self.service.save(self.payload())['document']
        locale = json.loads(self.locale_path().read_text(encoding='utf-8'))
        locale['variants'] = {}
        self.locale_path().write_text(json.dumps(locale), encoding='utf-8')
        self.assertEqual(self.state()['body'], created['body'])
        self.assertTrue(self.state('en')['translationMissing'])
        source = self.service.state(str(self.root), self.identifier)['document']
        self.service.save({'expectedRoot': str(self.root), 'id': self.identifier, 'title': 'English now', 'body': 'Changed external source', 'expectedRevision': source['revision']})
        self.assertTrue(self.state()['translationMissing'])
        self.assertEqual(self.state()['body'], '')

    def test_sidecar_race_at_atomic_replace_cannot_overwrite_newer_language(self):
        self.seed()
        self.service.save(self.payload(self.state()))
        old = self.state()
        raw = self.locale_path().read_bytes()
        winner = json.loads(raw.decode('utf-8')); winner['variants']['en'] = {'title': 'Winner', 'body': 'Winning concurrent language'}
        winner_raw = json.dumps(winner).encode('utf-8')
        real_atomic = self.service._atomic_write
        def race(root, parts, content, before_replace=None):
            if parts[-1] == self.identifier + '.json':
                def guard():
                    self.locale_path().write_bytes(winner_raw)
                    before_replace()
                return real_atomic(root, parts, content, before_replace=guard)
            return real_atomic(root, parts, content, before_replace=before_replace)
        with patch.object(self.service, '_atomic_write', side_effect=race):
            with self.assertRaises(DevRoomConflict):self.service.save(self.payload(old, body='Losing edit'))
        self.assertEqual(self.locale_path().read_bytes(), winner_raw)
        self.assertEqual(list(self.storage.rglob('*.tmp')), [])

    def test_source_race_at_atomic_replace_is_a_conflict(self):
        self.seed()
        old = self.state()
        real_atomic = self.service._atomic_write
        winning_source = self.source_path().read_bytes() + b'\nExternal change'
        def race(root, parts, content, before_replace=None):
            def guard():
                self.source_path().write_bytes(winning_source)
                before_replace()
            return real_atomic(root, parts, content, before_replace=guard)
        with patch.object(self.service, '_atomic_write', side_effect=race):
            with self.assertRaises(DevRoomConflict):self.service.save(self.payload(old))
        self.assertEqual(self.source_path().read_bytes(), winning_source)
        self.assertFalse(self.locale_path().exists())

    def test_disk_failure_preserves_source_sidecar_and_precise_history(self):
        self.seed()
        self.service.save(self.payload(self.state()))
        original, locale_raw = self.source_path().read_bytes(), self.locale_path().read_bytes()
        old, real_replace = self.state(), os.replace
        def fail(source, target):
            if Path(target).resolve() == self.locale_path().resolve():raise OSError('fixture disk failure')
            return real_replace(source, target)
        with patch('dev_room.os.replace', side_effect=fail):
            with self.assertRaises(OSError):self.service.save(self.payload(old, body='Failed edit'))
        self.assertEqual(self.source_path().read_bytes(), original)
        self.assertEqual(self.locale_path().read_bytes(), locale_raw)
        backups = list((self.storage / '.history' / self.identifier / 'locales').glob('*.json'))
        self.assertTrue(any(path.read_bytes() == locale_raw for path in backups))
        self.assertEqual(list(self.storage.rglob('*.tmp')), [])

    def test_new_document_source_failure_cleans_only_our_new_sidecar(self):
        real_replace = os.replace
        def fail(source, target):
            if Path(target).resolve() == self.source_path().resolve():raise OSError('fixture source disk failure')
            return real_replace(source, target)
        with patch('dev_room.os.replace', side_effect=fail):
            with self.assertRaises(OSError):self.service.save(self.payload())
        self.assertFalse(self.source_path().exists())
        self.assertFalse(self.locale_path().exists())
        self.assertEqual(list(self.storage.rglob('*.tmp')), [])

    def test_invalid_sidecar_fields_duplicates_cross_id_and_size_are_rejected(self):
        self.seed()
        self.service.save(self.payload(self.state()))
        original = self.locale_path().read_bytes()
        valid = json.loads(original)
        bad = [b'{', b'{"version":1,"version":1}', b'\xff', b'x' * (MAX_LOCALE_BYTES + 1)]
        for change in ({'id': str(uuid.uuid4())}, {'version': True}, {'sourceRevision': 'bad'}, {'variants': {'fr': {'title': 'French', 'body': ''}}}, {'variants': {'zh': {'title': 'Title', 'body': '', 'path': '../escape'}}}, {'sourceLanguage': 'fr'}):
            bad.append(json.dumps({**valid, **change}).encode('utf-8'))
        for raw in bad:
            with self.subTest(raw=raw[:30]):
                self.locale_path().write_bytes(raw)
                with self.assertRaises(ValueError):self.state()
                self.assertEqual(self.locale_path().read_bytes(), raw)
        self.locale_path().write_bytes(original)

    def test_bad_catalog_is_not_used_and_old_contract_remains_usable(self):
        source = self.seed()
        for raw in (b'{"version":1,"documents":[],"documents":[]}', b'{"version":true,"documents":[]}', b'{"version":1,"documents":{}}'):
            self.catalog.write_bytes(raw)
            with self.assertRaises(ValueError):self.state()
            self.assertEqual(self.service.state(str(self.root), self.identifier)['document'], source)

    def test_canonical_source_identity_and_sections_cannot_be_changed(self):
        self.seed(canonical=True)
        old = self.state()
        for body in (old['body'].replace('cf983df9a9ce17a45a8cc3e108eae281', '0' * 32), old['body'].replace('section 0', 'section 1'), old['body'] + '<!-- rr-dev-room:injected -->'):
            with self.assertRaises(ValueError):self.service.save(self.payload(old, body=body))
        self.assertFalse(self.locale_path().exists())

    def test_corrupt_other_language_identity_rejects_the_whole_sidecar(self):
        self.seed(canonical=True)
        self.service.save(self.payload(self.state(), body=self.state()['body']))
        locale = json.loads(self.locale_path().read_text(encoding='utf-8'))
        locale['variants']['en'] = {'title': 'English', 'body': self.state('en')['body'].replace('cf983df9a9ce17a45a8cc3e108eae281', '0' * 32)}
        self.locale_path().write_text(json.dumps(locale), encoding='utf-8')
        with self.assertRaises(ValueError):self.state()

    def test_locale_directory_link_is_rejected_without_touching_target(self):
        self.seed()
        outside = self.base / 'outside'; outside.mkdir()
        link = self.storage / '.locales'
        try:link.symlink_to(outside, target_is_directory=True)
        except OSError:
            if os.name != 'nt':raise
            result = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:self.skipTest('Isolated junction unavailable.')
        with self.assertRaises(ValueError):self.state()
        with self.assertRaises(ValueError):self.service.save(self.payload())
        self.assertEqual(list(outside.iterdir()), [])

    def test_locale_directory_swap_after_version_callback_never_touches_outside(self):
        self.seed()
        self.service.save(self.payload(self.state()))
        old = self.state()
        original, locale_raw = self.source_path().read_bytes(), self.locale_path().read_bytes()
        outside = self.base / 'outside-after-guard'; outside.mkdir()
        outside_target = outside / self.locale_path().name
        outside_target.write_bytes(b'outside target must survive')
        directory = self.storage / '.locales'
        retired = self.storage / '.locales-before-swap'
        real_atomic = self.service._atomic_write
        outside_before = None
        def race(root, parts, content, before_replace=None):
            if parts[-1] != self.identifier + '.json':
                return real_atomic(root, parts, content, before_replace=before_replace)
            def guard():
                nonlocal outside_before
                before_replace()
                temporary, = directory.glob('.*.tmp')
                (outside / temporary.name).write_bytes(temporary.read_bytes())
                outside_before = {path.name: path.read_bytes() for path in outside.iterdir()}
                directory.rename(retired)
                try:directory.symlink_to(outside, target_is_directory=True)
                except OSError:
                    if os.name != 'nt':raise
                    result = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(directory), str(outside)], capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
                    if result.returncode:self.skipTest('Isolated late junction unavailable.')
            return real_atomic(root, parts, content, before_replace=guard)
        try:
            with patch.object(self.service, '_atomic_write', side_effect=race):
                with self.assertRaises(ValueError):self.service.save(self.payload(old, body='Losing redirected edit'))
        finally:
            if retired.exists():
                if directory.is_symlink():directory.unlink()
                elif directory.exists():directory.rmdir()  # Remove only our junction, never its target.
                retired.rename(directory)
        self.assertIsNotNone(outside_before)
        self.assertEqual({path.name: path.read_bytes() for path in outside.iterdir()}, outside_before)
        self.assertEqual(self.source_path().read_bytes(), original)
        self.assertEqual(self.locale_path().read_bytes(), locale_raw)

    def test_http_language_contract_and_rejects_unknown_or_duplicate_languages(self):
        self.seed()
        with patch.dict(os.environ, {'CODEX_CONTROL_DATA_DIR': str(self.base / 'server-data'), 'LOCALAPPDATA': str(self.base / 'local-data'), 'CODEX_CONTROL_PUBLISHER_STATE_FILE': str(self.base / 'publisher.json'), 'CODEX_CONTROL_TEMP_DIR': str(self.base / 'server-temp')}):
            import world_console
        with patch.object(world_console, 'DEV_ROOM', self.service):
            server = world_console.ConsoleHTTPServer(('127.0.0.1', 0), world_console.ConsoleHandler)
            worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
            def request(method, path, payload=None, headers=None):
                client = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=5)
                try:
                    client.request(method, path, body=json.dumps(payload) if payload is not None else None, headers={'Content-Type': 'application/json', **(headers or {})})
                    response = client.getresponse(); return response.status, json.loads(response.read())
                finally:client.close()
            query = urlencode({'expectedRoot': str(self.root), 'id': self.identifier})
            try:
                self.assertEqual(request('GET', '/api/dev-room/state?' + query + '&language=zh')[1]['document']['title'], '中文标题')
                for language in ('fr', 'ZH', '', 'en-us'):
                    self.assertEqual(request('GET', '/api/dev-room/state?' + query + '&language=' + language)[0], 400)
                    self.assertEqual(request('POST', '/api/dev-room/save', self.payload(self.state(), language=language))[0], 400)
                self.assertEqual(request('GET', '/api/dev-room/state?' + query + '&language=zh&language=en')[0], 400)
                self.assertEqual(request('GET', '/api/dev-room/state?' + query + '&language=en', headers={'Origin': 'https://attacker.example'})[0], 403)
                stale = self.state('en')
                self.assertEqual(request('POST', '/api/dev-room/save', self.payload(self.state()))[0], 200)
                self.assertEqual(request('POST', '/api/dev-room/save', self.payload(stale, language='en', title='English', body='English'))[0], 409)
                legacy = request('GET', '/api/dev-room/state?' + query)[1]['document']
                self.assertEqual(set(legacy), {'id', 'title', 'body', 'revision', 'updatedAt'})
            finally:server.shutdown(); worker.join(5); server.server_close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
