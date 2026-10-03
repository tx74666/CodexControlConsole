"""Isolated local-image and private-export checks; no user files or app windows."""
import base64
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from document_library import (DocumentLibraryService, MAX_IMAGE_BYTES,
                              document_image_path, markdown_image_paths)
import phone_offline

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG1UAAAAASUVORK5CYII=')


class ImageChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='console-document-images-')
        self.base = Path(self.temp.name)
        self.root = self.base / 'library'
        (self.root / 'reports').mkdir(parents=True)
        (self.root / 'images').mkdir()
        (self.root / 'images/电梯.png').write_bytes(PNG)
        (self.root / 'reports/gallery.md').write_text('# Gallery\n\n![电梯](../images/%E7%94%B5%E6%A2%AF.png)\n', encoding='utf-8')
        (self.root / '.document-guide.json').write_text(json.dumps({'version': 1, 'items': [
            {'path': 'reports/gallery.md', 'title': 'Gallery', 'summary': '', 'highlights': []}]}), encoding='utf-8')
        self.service = DocumentLibraryService(self.base / 'documents.json')
        self.service.select(str(self.root))

    def tearDown(self):
        self.temp.cleanup()

    def export(self):
        return phone_offline.build_phone_export(self.service, lambda: {'plan': None}, lambda: {}, '1.0.22')

    def test_normalize_relative_encoded_paths_and_reject_unsafe_targets(self):
        self.assertEqual(document_image_path('../images/%E7%94%B5%E6%A2%AF.png', 'reports/gallery.md'), 'images/电梯.png')
        self.assertEqual(document_image_path(r'..\images\电梯.png', 'reports/gallery.md'), 'images/电梯.png')
        for target in ('../../outside.png', '/outside.png', '//host/x.png', 'C:\\x.png',
                       'https://host/x.png', 'data:image/png,x', '%2foutside.png',
                       '../images/x.png?x=1', '../images/x.png#x', '%00x.png', '%ZZx.png', 'x.svg'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                document_image_path(target, 'reports/gallery.md')

    def test_images_read_only_bounded_signature_and_selected_root(self):
        original = self.service.settings_file.read_bytes()
        image = self.service.image('images/电梯.png', expectedRoot=self.root)
        self.assertEqual(image['content'], PNG)
        self.assertEqual(image['mimeType'], 'image/png')
        self.assertEqual(self.service.settings_file.read_bytes(), original)
        for relative, expected in (('../outside.png', self.root), ('images/电梯.png', None),
                                   ('images/电梯.png', self.base), ('images/电梯.png?x=1', self.root)):
            with self.subTest(relative=relative, root=expected), self.assertRaises(ValueError):
                self.service.image(relative, expectedRoot=expected)
        (self.root / 'images/fake.png').write_bytes(b'<script>not a picture</script>')
        with self.assertRaisesRegex(ValueError, '副檔名'):
            self.service.image('images/fake.png', expectedRoot=self.root)
        (self.root / 'images/large.png').write_bytes(PNG + b'x' * MAX_IMAGE_BYTES)
        with self.assertRaisesRegex(ValueError, '1 MiB'):
            self.service.image('images/large.png', expectedRoot=self.root)

    def test_each_supported_signature_and_no_svg(self):
        for name, content, mime in [('one.jpg', b'\xff\xd8\xffx', 'image/jpeg'),
                                    ('one.gif', b'GIF89ax', 'image/gif'),
                                    ('one.webp', b'RIFF\x04\x00\x00\x00WEBP', 'image/webp')]:
            (self.root / 'images' / name).write_bytes(content)
            self.assertEqual(self.service.image('images/' + name, expectedRoot=self.root)['mimeType'], mime)
        (self.root / 'images/x.svg').write_text('<svg/>', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.service.image('images/x.svg', expectedRoot=self.root)

    def test_symlink_cannot_read_outside_library(self):
        outside = self.base / 'outside.png'
        outside.write_bytes(PNG)
        link = self.root / 'images/link.png'
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f'Symlink creation unavailable: {exc}')
        with self.assertRaises(ValueError):
            self.service.image('images/link.png', expectedRoot=self.root)

    def test_export_includes_only_referenced_assets_and_preserves_source(self):
        (self.root / 'images/private-unused.png').write_bytes(PNG)
        document = self.root / 'reports/gallery.md'
        document.write_text(document.read_text(encoding='utf-8') + '\n![Again](../images/电梯.png)\n', encoding='utf-8')
        before = {item: item.read_bytes() for item in self.root.rglob('*') if item.is_file()}
        payload = self.export()
        self.assertEqual(payload['schemaVersion'], 1)
        self.assertEqual(len(payload['assets']), 1)
        asset = payload['assets'][0]
        self.assertEqual(asset['path'], 'images/电梯.png')
        self.assertEqual(asset['mimeType'], 'image/png')
        self.assertEqual(base64.b64decode(asset['data']), PNG)
        self.assertNotIn(str(self.root), json.dumps(payload))
        self.assertEqual(before, {item: item.read_bytes() for item in self.root.rglob('*') if item.is_file()})
        document.write_text('# No images\n', encoding='utf-8')
        self.assertNotIn('assets', self.export())

    def test_code_examples_and_remote_images_never_export_or_fetch(self):
        source = '`![code](missing.png)`\n```md\n![fence](missing.png)\n```\n![remote](https://host/x.png)\n![photo](../images/电梯.png)\n'
        self.assertEqual(list(markdown_image_paths(source, 'reports/gallery.md')), ['images/电梯.png'])

    def test_missing_images_size_and_packet_limits_fail_without_partial_export(self):
        document = self.root / 'reports/gallery.md'
        document.write_text('![Missing](../images/missing.png)\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '不能匯出'):
            self.export()
        document.write_text('![Photo](../images/电梯.png)\n', encoding='utf-8')
        baseline = phone_offline._json_bytes(self.export())
        with patch.object(phone_offline, 'MAX_EXPORT_BYTES', len(baseline) - 1):
            with self.assertRaisesRegex(ValueError, '8 MiB'):
                self.export()
        self.assertEqual((self.root / 'images/电梯.png').read_bytes(), PNG)

    def test_http_image_bytes_headers_and_host_origin_root_boundaries(self):
        with patch.dict(os.environ, {'CODEX_CONTROL_DATA_DIR': str(self.base / 'server-data'),
                                    'CODEX_CONTROL_PUBLISHER_STATE_FILE': str(self.base / 'publisher.json'),
                                    'CODEX_CONTROL_TEMP_DIR': str(self.base / 'server-temp')}):
            import world_console
        with patch.object(world_console, 'DOCUMENT_LIBRARY', self.service):
            server = world_console.ConsoleHTTPServer(('127.0.0.1', 0), world_console.ConsoleHandler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            def get(query, headers=None):
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                try:
                    client.request('GET', '/api/documents/image?' + urlencode(query), headers=headers or {})
                    response = client.getresponse()
                    return response.status, dict(response.headers), response.read()
                finally:
                    client.close()
            try:
                query = {'path': 'images/电梯.png', 'expectedRoot': str(self.root)}
                code, headers, body = get(query)
                self.assertEqual(code, 200)
                self.assertEqual(body, PNG)
                self.assertEqual(headers['Content-Type'], 'image/png')
                self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
                self.assertEqual(headers['Cache-Control'], 'no-store')
                self.assertEqual(get(query, {'Host': 'attacker.example'})[0], 403)
                self.assertEqual(get(query, {'Origin': 'https://attacker.example'})[0], 403)
                self.assertEqual(get(query, {'Sec-Fetch-Site': 'cross-site'})[0], 403)
                self.assertEqual(get({'path': 'images/电梯.png'})[0], 400)
                self.assertEqual(get({**query, 'expectedRoot': str(self.base)})[0], 400)
                self.assertEqual(get({**query, 'path': '../outside.png'})[0], 400)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(5)


if __name__ == '__main__':
    unittest.main()
