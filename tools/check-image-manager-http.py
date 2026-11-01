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
