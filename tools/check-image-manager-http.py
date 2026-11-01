"""Real local HTTP boundaries using disposable images and server data only."""
from contextlib import ExitStack
import http.client
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from image_manager import ImageManagerService


class ImageHTTPChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bootstrap = tempfile.TemporaryDirectory(prefix='console-image-http-')
        base = Path(cls.bootstrap.name)
        with patch.dict(os.environ, {'CODEX_CONTROL_DATA_DIR': str(base / 'server'),
                'LOCALAPPDATA': str(base / 'local'), 'CODEX_CONTROL_TEMP_DIR': str(base / 'temp'),
                'CODEX_CONTROL_PUBLISHER_STATE_FILE': str(base / 'publisher.json')}):
            import world_console
        cls.world = world_console

    @classmethod
    def tearDownClass(cls):
        cls.bootstrap.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='image-library-http-')
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.root = base / 'Pictures'
        self.root.mkdir()
        self.service = ImageManagerService(base / 'config.json')
        self.service.configure({'root': str(self.root)})
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(self.world, 'IMAGE_MANAGER', self.service))
        self.server = self.world.ConsoleHTTPServer(('127.0.0.1', 0), self.world.ConsoleHandler)
        self.port = self.server.server_address[1]
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.worker.join(5)
        self.server.server_close()

    def request(self, method, path, payload=None, headers=None, *, response_headers=False):
        outgoing = dict(headers or {})
        body = payload
        if isinstance(payload, dict):
            body = json.dumps(payload).encode()
            outgoing.setdefault('Content-Type', 'application/json')
        client = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            client.request(method, path, body, outgoing)
            response = client.getresponse()
            raw = response.read()
            try:
                result = json.loads(raw)
            except (ValueError, UnicodeError):
                result = raw
            if response_headers:
                return response.status, result, {key.lower():value for key,value in response.getheaders()}
            return response.status, result
        finally:
            client.close()

    def test_shell_and_state_do_not_scan_or_modify_user_pictures(self):
        before = list(self.root.iterdir())
        with patch.object(self.service, 'scan', side_effect=AssertionError('implicit scan')):
            status, state = self.request('GET', '/api/images/state')
            self.assertEqual(status, 200, state)
            status, shell = self.request('GET', '/image-manager.html')
            self.assertEqual(status, 200)
            self.assertIn(b'image-manager.js', shell)
        self.assertEqual(list(self.root.iterdir()), before)

    def test_only_explicit_image_embed_can_be_framed_by_its_own_console_origin(self):
        for method in ('GET', 'HEAD'):
            status, _, headers = self.request(method, '/image-manager.html?embed=steamwork', response_headers=True)
            self.assertEqual(status, 200)
            self.assertEqual(headers.get('x-frame-options'), 'SAMEORIGIN')
            self.assertEqual(headers.get('content-security-policy'), "frame-ancestors 'self'")
        for path in ('/image-manager.html', '/image-manager.html?embed=other',
                     '/image-manager.html?embed=steamwork&embed=other',
                     '/image-manager.html?embed=steamwork&embed=',
                     '/index.html?embed=steamwork', '/image-manager.js?embed=steamwork',
                     '/api/images/state?embed=steamwork'):
            with self.subTest(path=path):
                _, _, headers = self.request('GET', path, response_headers=True)
                self.assertEqual(headers.get('x-frame-options'), 'DENY')
                self.assertNotIn('content-security-policy', headers)

    def test_untrusted_host_origin_and_nonlocal_requests_cannot_write(self):
        payload = {'expectedRoot': str(self.root)}
        for headers in ({'Host': 'attacker.example'}, {'Origin': 'https://attacker.example'},
                        {'Sec-Fetch-Site': 'cross-site'}):
            status, _ = self.request('POST', '/api/images/scan', payload, headers)
            self.assertEqual(status, 403)
            status, _ = self.request('GET', '/api/images/state', headers=headers)
            self.assertEqual(status, 403)
        with patch.object(self.world, '_client_address_is_loopback', return_value=False):
            status, _ = self.request('POST', '/api/images/scan', payload)
            self.assertEqual(status, 403)

    def test_naming_actions_are_explicit_post_only_and_strictly_scoped(self):
        from image_manager_http import image_post
        expected = {'expectedRoot':str(self.root), 'entries':[]}
        service = SimpleNamespace(naming_plan=lambda payload:{'received':payload},
            naming_apply=lambda payload:{'received':payload}, naming_restore=lambda payload:{'received':payload})
        for action, payload in [('naming-plan',expected),
                ('naming-apply',{'expectedRoot':str(self.root),'planId':'a'*32}),
                ('naming-restore',{'expectedRoot':str(self.root),'planId':'a'*32})]:
            self.assertEqual(image_post(service,action,payload,notion=SimpleNamespace(busy=False)),{'received':payload})
            with self.assertRaises(ValueError):
                image_post(service,action,dict(payload,unexpected=True))
            with self.assertRaises(ValueError):
                image_post(service,action,{key:value for key,value in payload.items() if key!='expectedRoot'})
            self.assertGreaterEqual(self.request('GET','/api/images/'+action)[0],400)
            self.assertEqual(self.request('POST','/api/images/'+action,payload,{'Origin':'https://attacker.example'})[0],403)
        for action in ['naming-apply','naming-restore']:
            with self.assertRaisesRegex(ValueError,'正在同步'):
                image_post(service,action,{'expectedRoot':str(self.root),'planId':'a'*32},notion=SimpleNamespace(busy=True))
        # Previewing names does not write images or monopolize an in-flight sync.
        self.assertEqual(image_post(service,'naming-plan',expected,notion=SimpleNamespace(busy=True)),{'received':expected})

    def test_naming_preview_apply_and_restore_preserve_original_bytes(self):
        original = self.root/'Old-event-v9.png'
        Image.new('RGB',(800,450),'teal').save(original)
        before = original.read_bytes()
        self.service.scan({'expectedRoot':str(self.root)})
        item = self.service.state()['items'][0]
        status, plan = self.request('POST','/api/images/naming-plan',{
            'expectedRoot':str(self.root), 'entries':[{'path':item['path'],
                'sha256':item['sha256'],'assetType':'EventCover'}]})
        self.assertEqual(status,200,plan)
        self.assertTrue(plan['canApply'])
        self.assertTrue(original.is_file(),'Preview must not rename a picture')
        status, result = self.request('POST','/api/images/naming-apply',{
            'expectedRoot':str(self.root),'planId':plan['planId']})
        self.assertEqual(status,200,result)
        standard = self.root/'EventCover_800x450.png'
        self.assertEqual(standard.read_bytes(),before)
        self.assertFalse(original.exists())
        status, result = self.request('POST','/api/images/naming-restore',{
            'expectedRoot':str(self.root),'planId':plan['planId']})
        self.assertEqual(status,200,result)
        self.assertEqual(original.read_bytes(),before)
        self.assertFalse(standard.exists())

    def test_delete_routes_are_explicit_scoped_and_receipts_are_read_only(self):
        from image_manager_http import image_get, image_post
        service = SimpleNamespace(delete=lambda payload: {'received': payload},
            delete_restore=lambda payload: {'received': payload},
            delete_operation=lambda payload: {'received': payload})
        deletion = {'expectedRoot': str(self.root), 'path': 'inbox/new.png', 'sha256': 'a'*64, 'requestId': 'b'*32}
        restore = {'expectedRoot': str(self.root), 'requestId': deletion['requestId']}
        for action, payload in [('delete', deletion), ('delete-restore', restore)]:
            self.assertEqual(image_post(service, action, payload, SimpleNamespace(busy=False)), {'received': payload})
            for invalid in [dict(payload, space='device'), {key: value for key, value in payload.items() if key != 'requestId'}]:
                with self.assertRaises(ValueError): image_post(service, action, invalid)
            with self.assertRaisesRegex(ValueError, '正在同步'):
                image_post(service, action, payload, SimpleNamespace(busy=True))
            self.assertGreaterEqual(self.request('GET', '/api/images/'+action)[0], 400)
            self.assertEqual(self.request('POST', '/api/images/'+action, payload, {'Origin': 'https://attacker.example'})[0], 403)
        self.assertEqual(image_get(service, 'delete-operation', urlencode(restore)), {'received': restore})
        for query in [urlencode({'requestId': deletion['requestId']}), urlencode(dict(restore, path='new.png')),
                      urlencode(restore)+'&requestId='+deletion['requestId']]:
            with self.assertRaises(ValueError): image_get(service, 'delete-operation', query)
        with self.assertRaises(ValueError): image_post(service, 'delete-operation', restore)
        self.assertEqual(self.request('GET', '/api/images/delete-operation?'+urlencode(restore), headers={'Origin':'https://attacker.example'})[0],403)

    def test_delete_and_undo_over_http_preserve_inbox_and_original_bytes(self):
        original = self.root/'A.png'; inbox = self.root/'inbox'; inbox.mkdir(exist_ok=True)
        Image.new('RGB', (12, 8), 'teal').save(original)
        pending = inbox/'Pending.png'; Image.new('RGB', (12, 8), 'purple').save(pending)
        before, pending_bytes = original.read_bytes(), pending.read_bytes()
        self.service.scan({'expectedRoot': str(self.root)})
        item = next(item for item in self.service.state()['items'] if item['path']=='A.png')
        payload = {'expectedRoot': str(self.root), 'path': item['path'], 'sha256': item['sha256'], 'requestId': 'd'*32}
        status, deleted = self.request('POST', '/api/images/delete', payload)
        self.assertEqual(status, 200, deleted); self.assertTrue(deleted['deleted']); self.assertFalse(original.exists())
        self.assertEqual(pending.read_bytes(), pending_bytes)
        self.assertTrue(deleted['state']['lastDeletion']['canRestore'])
        manifest = self.root/'.image-manager/library.json'; manifest_bytes = manifest.read_bytes()
        query = urlencode({'expectedRoot': str(self.root), 'requestId': payload['requestId']})
        status, receipt = self.request('GET', '/api/images/delete-operation?'+query)
        self.assertEqual(status, 200, receipt); self.assertEqual(receipt['status'], 'completed')
        self.assertEqual(manifest.read_bytes(), manifest_bytes, 'Checking a deletion result must not rewrite metadata')
        status, repeated = self.request('POST', '/api/images/delete', payload)
        self.assertEqual(status, 200, repeated); self.assertTrue(repeated['replayed'])
        status, restored = self.request('POST', '/api/images/delete-restore', {'expectedRoot':str(self.root),'requestId':payload['requestId']})
        self.assertEqual(status, 200, restored); self.assertTrue(restored['restored'])
        self.assertEqual(original.read_bytes(), before); self.assertEqual(pending.read_bytes(), pending_bytes)
        status, receipt = self.request('GET', '/api/images/delete-operation?'+query)
        self.assertEqual(status, 200, receipt); self.assertEqual(receipt['status'], 'restored')

    def test_language_helper_is_a_normal_javascript_resource(self):
        status, source, headers = self.request('GET', '/image-manager-i18n.js', response_headers=True)
        self.assertEqual(status, 200)
        self.assertIn(b'ImageManagerI18n', source)
        self.assertIn('javascript', headers.get('content-type', ''))

    def test_notion_status_reuses_each_local_response_snapshot_without_extra_scan(self):
        from image_manager_http import image_get, image_post
        snapshots = []
        def provider_state(*, local_state):
            snapshots.append(local_state)
            return {'notionSync': {'status': 'pending', 'localFingerprint': local_state['revision']}}
        notion = SimpleNamespace(busy=False, state=provider_state)
        calls = []
        local = {'root': str(self.root), 'revision': 'changed'}
        def read_state():
            calls.append('state')
            return local
        service = SimpleNamespace(state=read_state, configure=lambda payload: local,
            delete_operation=lambda payload: {'status': 'completed', 'state': local})
        state = image_get(service, 'state', '', notion)
        self.assertEqual(calls, ['state'])
        self.assertIs(snapshots[-1], local)
        self.assertEqual(state['notionSync']['localFingerprint'], 'changed')
        self.assertNotIn('notionSync', local, 'Merging the provider must not modify the core snapshot')
        configured = image_post(service, 'config', {'root': str(self.root)}, notion)
        self.assertEqual(configured['notionSync']['status'], 'pending')
        for action, method, fields in [
            ('scan', 'scan', {}), ('apply', 'apply', {'planId': 'a'*32, 'decisions': []}),
            ('restore', 'restore', {'planId': 'a'*32}),
            ('metadata', 'annotate', {'path': 'A.png', 'sha256': 'b'*64}),
            ('naming-plan', 'naming_plan', {'entries': []}),
            ('naming-apply', 'naming_apply', {'planId': 'a'*32}),
            ('naming-restore', 'naming_restore', {'planId': 'a'*32}),
            ('delete', 'delete', {'path': 'A.png', 'sha256': 'b'*64, 'requestId': 'c'*32}),
            ('delete-restore', 'delete_restore', {'requestId': 'c'*32}),
            ('sync', 'scan', {'source': 'console', 'target': 'local'}),
        ]:
            with self.subTest(action=action):
                original = {'state': local, 'ok': True}
                setattr(service, method, lambda payload: original)
                count = len(snapshots)
                response = image_post(service, action, {'expectedRoot': str(self.root), **fields}, notion)
                self.assertEqual(len(snapshots), count+1)
                self.assertIs(snapshots[-1], local)
                self.assertEqual(response['state']['notionSync']['status'], 'pending')
                self.assertNotIn('notionSync', original['state'])
        receipt = image_get(service, 'delete-operation', urlencode({
            'expectedRoot': str(self.root), 'requestId': 'c'*32}), notion)
        self.assertEqual(receipt['state']['notionSync']['status'], 'pending')
        self.assertEqual(calls, ['state'], 'Local mutation receipts already carry the core state')

    def test_busy_notion_push_blocks_local_scan_and_device_writes_but_retains_same_request_route(self):
        from image_manager_http import image_post
        def forbidden(payload):
            self.fail('An in-flight Notion operation must protect its local export snapshot')
        service = SimpleNamespace(scan=forbidden, sync_device=forbidden, state=lambda: {'deviceRoot': 'E:\\Device'})
        notion = SimpleNamespace(busy=True, sync=lambda payload: {'requestId': payload['requestId']})
        with self.assertRaisesRegex(ValueError, '正在同步'):
            image_post(service, 'scan', {'expectedRoot': str(self.root)}, notion)
        for source, target in [('local', 'console'), ('local', 'local'), ('console', 'console'),
                               ('console', 'local'), ('local', 'device'), ('console', 'device'), ('device', 'console')]:
            with self.subTest(source=source, target=target), self.assertRaisesRegex(ValueError, '正在同步'):
                image_post(service, 'sync', {'expectedRoot': str(self.root), 'source': source, 'target': target}, notion)
        original = {'expectedRoot': str(self.root), 'source': 'console', 'target': 'notion', 'requestId': 'same-request'}
        self.assertEqual(image_post(service, 'sync', original, notion), {'requestId': original['requestId']},
                         'The provider must retain authority over checking the same in-flight request')

    def test_upload_review_and_preview_use_bound_root_and_reject_escape(self):
        stream = io.BytesIO()
        Image.new('RGB', (32, 24), 'purple').save(stream, format='PNG')
        original = stream.getvalue()
        boundary = 'console-image-http-fixture'
        raw = (f'--{boundary}\r\nContent-Disposition: form-data; name="expectedRoot"\r\n\r\n'
               f'{self.root}\r\n--{boundary}\r\nContent-Disposition: form-data; name="files"; '
               'filename="Poster.png"\r\nContent-Type: image/png\r\n\r\n').encode() + original + f'\r\n--{boundary}--\r\n'.encode()
        status, plan = self.request('POST', '/api/images/upload', raw,
            {'Content-Type': f'multipart/form-data; boundary={boundary}'})
        self.assertEqual(status, 200, plan)
        self.assertTrue(plan['candidates'])
        entry = plan['candidates'][0]
        self.assertFalse((self.root / 'Poster - 32x24.png').exists())
        incoming = entry['incoming']
        query = urlencode({'expectedRoot': str(self.root), 'path': incoming['path']})
        status, served = self.request('GET', '/api/images/preview?' + query)
        self.assertEqual((status, served), (200, original))
        query = urlencode({'expectedRoot': str(self.root), 'path': '../outside.png'})
        self.assertEqual(self.request('GET', '/api/images/preview?' + query)[0], 400)
        query = urlencode({'expectedRoot': str(self.root / 'different'), 'path': incoming['path']})
        self.assertEqual(self.request('GET', '/api/images/preview?' + query)[0], 409)
        status, result = self.request('POST', '/api/images/apply', {
            'expectedRoot': str(self.root), 'planId': plan.get('planId', plan.get('id')),
            'decisions': [{'id': entry['id'], 'action': 'add'}]})
        self.assertEqual(status, 200, result)
        self.assertEqual((self.root / 'Poster - 32x24.png').read_bytes(), original)

    def test_unknown_actions_and_sync_directions_do_not_run(self):
        status, _ = self.request('POST', '/api/images/sync', {
            'expectedRoot': str(self.root), 'source': 'arbitrary', 'target': 'all'})
        self.assertEqual(status, 400)
        self.assertEqual(self.request('POST', '/api/images/apply?root=evil', {})[0], 400)
        self.assertEqual(self.request('GET', '/api/images/state?root=evil')[0], 400)

    def test_metadata_saves_options_without_changing_original_and_rejects_stale_bytes(self):
        path = self.root / 'Togo.png'
        Image.new('RGBA', (12, 8), (128, 64, 255, 80)).save(path)
        original = path.read_bytes()
        self.service.scan({'expectedRoot': str(self.root)})
        item = self.service.state()['items'][0]
        status, result = self.request('POST', '/api/images/metadata', {
            'expectedRoot': str(self.root), 'path': item['path'], 'sha256': item['sha256'],
            'groupTitle': 'Logo options', 'variantLabel': 'Option B', 'derivedFromId': ''})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['item']['variantLabel'], 'Option B')
        self.assertEqual(result['item']['groupTitle'], 'Logo options')
        self.assertEqual(path.read_bytes(), original)
        Image.new('RGBA', (12, 8), (64, 128, 255, 80)).save(path)
        status, _ = self.request('POST', '/api/images/metadata', {
            'expectedRoot': str(self.root), 'path': item['path'], 'sha256': item['sha256'],
            'groupTitle': 'Changed after preview', 'variantLabel': 'Option C'})
        self.assertEqual(status, 409)

    def test_private_configuration_and_transfer_snapshots_are_never_static_files(self):
        app = Path(self.temporary.name) / 'app'
        private = app / 'cache' / 'image-manager-notion-private'
        private.mkdir(parents=True)
        (private / 'original-fixture.png').write_bytes(b'private original')
        config = app / 'cache' / 'image-manager.json'
        config.write_text('{"root":"private"}', encoding='utf-8')
        with patch.object(self.world, 'APP_DIR', app), patch.object(self.service, 'config_path', config), \
                patch.object(self.world, 'IMAGE_MANAGER_NOTION', SimpleNamespace(directory=private)):
            for path in ('/cache/image-manager.json', '/cache/image-manager-notion-private/',
                         '/cache/image-manager-notion-private/original-fixture.png',
                         '/cache/image-manager-notion-private/%6friginal-fixture.png'):
                for method in ('GET', 'HEAD'):
                    self.assertEqual(self.request(method, path)[0], 404)


if __name__ == '__main__':
    unittest.main()
