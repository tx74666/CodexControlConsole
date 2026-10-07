"""Resource preview and real HTTP boundaries, using disposable libraries only."""
from contextlib import contextmanager, ExitStack
import http.client
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from document_library import DocumentLibraryService
import phone_companion as phone
import resource_http
import resource_library as resources
import resource_preview as preview

PROJECT = Path(__file__).resolve().parents[1]
PUBLIC_ADDRESS = '93.184.216.34'


class Response(io.BytesIO):
    def __init__(self, body=b'', status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = {'Content-Type': 'text/html; charset=utf-8', **(headers or {})}

    def getheader(self, name, default=None):
        return self.headers.get(name, default)


@contextmanager
def mock_pinned_connection(responses, addresses=None):
    """Exercise production HTML parsing; only the socket transport is replaced."""
    connections, pending = [], list(responses)
    real_dns = socket.getaddrinfo

    class Connection:
        def __init__(self, hostname, address):
            self.hostname, self.address, self.requests = hostname, address, []
            self.closed = False
            connections.append(self)

        def request(self, method, path, headers):
            self.requests.append((method, path, headers))

        def getresponse(self):
            if not pending:
                raise AssertionError('Unexpected extra HTTP request, possibly fetching media')
            return pending.pop(0)

        def close(self):
            self.closed = True

    def dns(hostname, port, *args, **kwargs):
        if hostname == '127.0.0.1' and port != 443:
            return real_dns(hostname, port, *args, **kwargs)
        values = addresses(hostname) if callable(addresses) else (addresses or [PUBLIC_ADDRESS])
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (value, port)) for value in values]

    with patch.object(preview, '_PinnedHTTPS', Connection), patch.object(preview.socket, 'getaddrinfo', side_effect=dns):
        yield connections


def dns_response(kind=1, addresses=(PUBLIC_ADDRESS,), **changes):
    document = {'Status': 0, 'TC': False, 'Question': [{'name': 'example.com.', 'type': kind}],
                'Answer': [{'name': 'example.com.', 'type': kind, 'data': address} for address in addresses]}
    document.update(changes)
    return Response(json.dumps(document).encode(), headers={'Content-Type': 'application/dns-json'})


class PreviewChecks(unittest.TestCase):
    def test_private_urls_and_mixed_private_dns_never_connect(self):
        urls = ('http://example.com/a', 'https://127.0.0.1/a', 'https://10.1.2.3/a',
                'https://[::1]/a', 'https://localhost/a', 'https://host.local/a',
                'https://user:password@example.com/a', 'https://example.com:8443/a')
        with mock_pinned_connection([]) as connections:
            for url in urls:
                with self.subTest(url=url), self.assertRaises(preview.ResourcePreviewError):
                    preview.fetch_metadata(url)
            self.assertEqual(connections, [])
        for addresses in (['127.0.0.1'], [PUBLIC_ADDRESS, '192.168.1.2']):
            with mock_pinned_connection([], addresses) as connections:
                with self.assertRaises(preview.ResourcePreviewError):
                    preview.fetch_metadata('https://example.com/a')
                self.assertEqual(connections, [])

    def test_metadata_relative_image_and_entities_without_media_fetch(self):
        html = b'''<title>Fallback title</title><meta property="og:title" content="Artist &amp; Model">
        <meta name="description" content=" A  useful model "><meta property="og:image" content="/cover.jpg">
        <meta property="og:title" content="later duplicate"><img src="/unexpected.jpg">'''
        with mock_pinned_connection([Response(html)]) as connections:
            result = preview.fetch_metadata('https://example.com/model?q=chair#preview')
            self.assertEqual(result['name'], 'Artist & Model')
            self.assertEqual(result['description'], 'A useful model')
            self.assertEqual(result['url'], 'https://example.com/model?q=chair')
            self.assertEqual(result['previewUrl'], 'https://example.com/cover.jpg')
            self.assertEqual(len(connections), 1)
            self.assertEqual(connections[0].address, PUBLIC_ADDRESS)
            self.assertEqual([(method, path) for method, path, _ in connections[0].requests], [('GET', '/model?q=chair')])
            self.assertTrue(connections[0].closed)

    def test_private_redirect_url_or_dns_is_rejected_before_second_connection(self):
        for location, dns in (('https://127.0.0.1/private', None),
                              ('https://internal.example/private', lambda host: ['10.0.0.8'] if host == 'internal.example' else [PUBLIC_ADDRESS])):
            with self.subTest(location=location), mock_pinned_connection([Response(status=302, headers={'Location': location})], dns) as connections:
                with self.assertRaises(preview.ResourcePreviewError):
                    preview.fetch_metadata('https://example.com/model')
                self.assertEqual(len(connections), 1)
                self.assertTrue(connections[0].closed)

    def test_private_image_is_omitted_but_valid_page_remains_readable(self):
        html = b'<title>Model</title><meta property="og:image" content="https://images.example/cover.jpg">'
        with mock_pinned_connection([Response(html)], lambda host: ['192.168.1.8'] if host == 'images.example' else [PUBLIC_ADDRESS]) as connections:
            result = preview.fetch_metadata('https://example.com/model')
            self.assertEqual(result['name'], 'Model')
            self.assertEqual(result['previewUrl'], '')
            self.assertTrue(result['warning'])
            self.assertEqual(len(connections), 1)

    def test_oversize_http_403_and_media_response_are_not_success(self):
        fixtures = (Response(b'x' * 33), Response(status=403),
                    Response(b'image', headers={'Content-Type': 'image/png'}))
        with patch.object(preview, 'MAX_HTML_BYTES', 32):
            for response in fixtures:
                with self.subTest(status=response.status, headers=response.headers), mock_pinned_connection([response]) as connections:
                    with self.assertRaises(preview.ResourcePreviewError):
                        preview.fetch_metadata('https://example.com/model')
                    self.assertEqual(len(connections), 1)
                    self.assertTrue(connections[0].closed)

    def test_vpn_fake_dns_uses_fixed_doh_and_pins_only_public_website_address(self):
        responses = [dns_response(), dns_response(28, ('2606:4700:4700::1111',)),
                     Response(b'<title>Public model</title>')]
        with mock_pinned_connection(responses, ['198.18.0.66', '198.19.255.254']) as connections:
            result = preview.fetch_metadata('https://example.com/model')
        self.assertEqual(result['name'], 'Public model')
        self.assertEqual([(c.hostname, c.address) for c in connections],
                         [('cloudflare-dns.com', '1.1.1.1'), ('cloudflare-dns.com', '1.1.1.1'), ('example.com', PUBLIC_ADDRESS)])
        self.assertEqual(connections[0].requests[0][1], '/dns-query?name=example.com&type=1')
        self.assertEqual(connections[1].requests[0][1], '/dns-query?name=example.com&type=28')
        self.assertTrue(all(c.closed for c in connections))

    def test_non_fake_private_mixed_and_multicast_dns_never_use_doh(self):
        for addresses in (['198.18.0.66', PUBLIC_ADDRESS], ['198.18.0.66', '10.0.0.8'],
                          ['127.0.0.1'], ['224.0.0.1'], ['ff02::1']):
            with self.subTest(addresses=addresses), mock_pinned_connection([], addresses) as connections:
                with self.assertRaises(preview.ResourcePreviewError):
                    preview.fetch_metadata('https://example.com/a')
                self.assertEqual(connections, [])
        with self.assertRaises(preview.ResourcePreviewError):
            preview.public_url('https://224.0.0.1/a')

    def test_doh_private_multicast_and_malformed_address_records_are_rejected(self):
        for address in ('127.0.0.1', '10.0.0.1', '198.18.0.1', '224.0.0.1', 'invalid'):
            with self.subTest(address=address), mock_pinned_connection([dns_response(addresses=(PUBLIC_ADDRESS, address))], ['198.18.0.66']) as connections:
                with self.assertRaises(preview.ResourcePreviewError):
                    preview.fetch_metadata('https://example.com/a')
                self.assertEqual([(c.hostname, c.address) for c in connections], [('cloudflare-dns.com', '1.1.1.1')])
        for address in ('::1', 'fe80::1', 'fec0::1', 'ff02::1', '::ffff:224.0.0.1', PUBLIC_ADDRESS):
            with self.subTest(aaaa=address), mock_pinned_connection([dns_response(), dns_response(28, (address,))], ['198.18.0.66']) as connections:
                with self.assertRaises(preview.ResourcePreviewError):
                    preview.fetch_metadata('https://example.com/a')
                self.assertEqual([c.hostname for c in connections], ['cloudflare-dns.com', 'cloudflare-dns.com'])

    def test_doh_bad_status_query_json_size_or_redirect_never_connects_to_website(self):
        responses = [dns_response(Status=3), dns_response(Status=False), dns_response(TC=True),
                     dns_response(Question=[{'name': 'attacker.example.', 'type': 1}]),
                     dns_response(Question=[{'name': 'example.com.', 'type': 28}]),
                     dns_response(Answer=[{'type': True, 'data': PUBLIC_ADDRESS}]),
                     dns_response(Answer={}), Response(b'{broken', headers={'Content-Type': 'application/dns-json'}),
                     Response(b'x' * (preview.MAX_DNS_BYTES + 1), headers={'Content-Type': 'application/dns-json'}),
                     Response(status=302, headers={'Location': 'https://127.0.0.1/private'}),
                     Response(status=403), Response(b'<html>Not DNS</html>')]
        for index, response in enumerate(responses):
            with self.subTest(response=index), mock_pinned_connection([response], ['198.18.0.66']) as connections:
                with self.assertRaises(preview.ResourcePreviewError):
                    preview.fetch_metadata('https://example.com/a')
                self.assertEqual([(c.hostname, c.address) for c in connections], [('cloudflare-dns.com', '1.1.1.1')])
                self.assertTrue(connections[0].closed)
        with mock_pinned_connection([dns_response(addresses=()), dns_response(28, ())], ['198.18.0.66']) as connections:
            with self.assertRaises(preview.ResourcePreviewError):
                preview.fetch_metadata('https://example.com/a')
            self.assertEqual([c.hostname for c in connections], ['cloudflare-dns.com', 'cloudflare-dns.com'])

    def test_pinned_transport_retains_tls_hostname_and_eight_second_timeout(self):
        with patch.object(preview.socket, 'create_connection') as connect, patch.object(preview.ssl, 'create_default_context') as context:
            connection = preview._PinnedHTTPS(preview.DOH_HOST, preview.DOH_ADDRESS)
            connection.connect()
            connect.assert_called_once_with(('1.1.1.1', 443), 8)
            context.assert_called_once_with()
            context.return_value.wrap_socket.assert_called_once_with(connect.return_value, server_hostname='cloudflare-dns.com')
            connection.close()


class LibraryFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='console-resource-http-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / '中文 资料库'
        self.root.mkdir()
        self.documents = DocumentLibraryService(self.base / 'documents.json')
        self.documents.select(str(self.root))
        self.service = resources.ResourceLibraryService(self.documents)

    def payload(self, **fields):
        return {'expectedRoot': str(self.root), 'expectedRevision': 0,
                'name': 'Fixture Model', 'url': 'https://example.com/model', 'status': 'saved', **fields}

    def request(self, method, path, payload=None, headers=None):
        client = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        merged = {'Content-Type': 'application/json', **(headers or {})}
        if hasattr(self, 'cookie'):
            merged.update({'Cookie': self.cookie} if self.cookie else {})
            if method == 'POST':
                merged = {'Origin': self.origin, 'X-Codex-Phone': '1', **merged}
        try:
            client.request(method, path, body=json.dumps(payload).encode('utf-8') if payload is not None else None, headers=merged)
            response = client.getresponse()
            raw, response_headers = response.read(), dict(response.getheaders())
            try:
                result = json.loads(raw)
            except (ValueError, UnicodeError):
                result = raw
            return response.status, result, response_headers
        finally:
            client.close()


class ResourceDispatchChecks(LibraryFixture):
    def test_preview_rechecks_root_and_authorization_after_network(self):
        other = self.base / 'other'
        other.mkdir()
        def switch_root(url):
            self.documents.select(str(other))
            return {'name': 'Must not return stale preview'}
        with patch.object(resource_http, 'fetch_metadata', side_effect=switch_root):
            with self.assertRaises(resources.ResourceLibraryConflict):
                resource_http.resource_post(self.service, 'preview', {'expectedRoot': str(self.root), 'url': 'https://example.com/a'})
        self.assertEqual(list(other.iterdir()), [])
        self.documents.select(str(self.root))
        allowed = [True]
        def authorize():
            if not allowed[0]:
                raise PermissionError('Revoked during preview')
        def revoke(url):
            allowed[0] = False
            return {'name': 'Must not return unauthorized preview'}
        with patch.object(resource_http, 'fetch_metadata', side_effect=revoke):
            with self.assertRaises(PermissionError):
                resource_http.resource_post(self.service, 'preview', {'expectedRoot': str(self.root), 'url': 'https://example.com/a'}, authorize=authorize)
        self.assertEqual(list(self.root.iterdir()), [])


class DesktopResourceChecks(LibraryFixture):
    @classmethod
    def setUpClass(cls):
        cls.bootstrap = tempfile.TemporaryDirectory(prefix='console-resource-bootstrap-')
        base = Path(cls.bootstrap.name)
        with patch.dict(os.environ, {
                'CODEX_CONTROL_DATA_DIR': str(base / 'server-data'),
                'LOCALAPPDATA': str(base / 'local-app-data'),
                'CODEX_CONTROL_PUBLISHER_STATE_FILE': str(base / 'publisher.json'),
                'CODEX_CONTROL_TEMP_DIR': str(base / 'server-temp')}):
            import world_console
        cls.world = world_console

    @classmethod
    def tearDownClass(cls):
        cls.bootstrap.cleanup()

    def setUp(self):
        super().setUp()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(self.world, 'RESOURCE_LIBRARY', self.service))
        self.server = self.world.ConsoleHTTPServer(('127.0.0.1', 0), self.world.ConsoleHandler)
        self.port = self.server.server_address[1]
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.worker.join(5)
        self.server.server_close()

    def test_first_get_and_static_shell_have_no_network_or_library_writes(self):
        with patch.object(resources, '_fetch_json', side_effect=AssertionError('unexpected search')), patch.object(resource_http, 'fetch_metadata', side_effect=AssertionError('unexpected preview')):
            code, state, _ = self.request('GET', '/api/resources/state')
            self.assertEqual(code, 200, state)
            self.assertEqual((state['revision'], state['items']), (0, []))
            code, shell, _ = self.request('GET', '/resources.html')
            self.assertEqual(code, 200)
            self.assertIn(b'resources.js', shell)
            self.assertNotIn(str(self.root).encode(), shell)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_host_origin_csrf_and_local_boundary_reject_before_mutation(self):
        for headers in ({'Host': 'attacker.example'}, {'Origin': 'https://attacker.example'}, {'Sec-Fetch-Site': 'cross-site'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request('GET', '/api/resources/state', headers=headers)[0], 403)
                self.assertEqual(self.request('POST', '/api/resources/save', self.payload(), headers)[0], 403)
        with patch.object(self.world, '_client_address_is_loopback', return_value=False):
            self.assertEqual(self.request('GET', '/api/resources/state')[0], 403)
            self.assertEqual(self.request('POST', '/api/resources/save', self.payload())[0], 403)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_save_stale_revision_and_switched_library_are_409(self):
        code, saved, _ = self.request('POST', '/api/resources/save', self.payload())
        self.assertEqual(code, 200, saved)
        store = self.root / resources.STORE_RELATIVE
        original = store.read_bytes()
        code, conflict, _ = self.request('POST', '/api/resources/save', self.payload(name='Stale edit'))
        self.assertEqual((code, conflict['code']), (409, 'revision_conflict'))
        other = self.base / 'other'
        other.mkdir()
        self.documents.select(str(other))
        self.assertEqual(self.request('GET', '/api/resources/state?' + urlencode({'expectedRoot': str(self.root)}))[0], 409)
        self.assertEqual(self.request('POST', '/api/resources/save', self.payload(expectedRevision=saved['revision']))[0], 409)
        self.assertEqual(store.read_bytes(), original)
        self.assertEqual(list(other.iterdir()), [])

    def test_preview_failure_and_invalid_routes_do_not_claim_success(self):
        with mock_pinned_connection([Response(status=403)]):
            code, result, _ = self.request('POST', '/api/resources/preview', {'expectedRoot': str(self.root), 'url': 'https://example.com/a'})
            self.assertEqual(code, 502, result)
            self.assertIn('403', result['error'])
            self.assertNotIn('name', result)
        for method, path, body in (('GET', '/api/resources/state?q=a&q=b', None),
                                   ('POST', '/api/resources/save?unexpected=1', self.payload()),
                                   ('POST', '/api/resources/unknown', {})):
            self.assertEqual(self.request(method, path, body)[0], 400)
        self.assertEqual(list(self.root.iterdir()), [])


class PhoneResourceChecks(LibraryFixture):
    def setUp(self):
        super().setUp()
        self.assets = self.base / 'assets'
        self.assets.mkdir()
        for name in ('resources.html', 'resources.js', 'resources.css'):
            (self.assets / name).write_bytes((PROJECT / name).read_bytes())
        self.companion = phone.PhoneCompanionService(self.documents, lambda: {}, self.assets, '1.0.test',
            device_getter=lambda: {}, resource_service=self.service,
            interface_getter=lambda: [{'address': '127.0.0.1', 'name': 'Disposable test listener'}])
        original_policy = phone.is_lan_address
        self.policy = patch.object(phone, 'is_lan_address', lambda address: address == '127.0.0.1' or original_policy(address))
        self.policy.start()
        self.addCleanup(self.policy.stop)
        with socket.socket() as holder:
            holder.bind(('127.0.0.1', 0))
            self.port = holder.getsockname()[1]
        self.companion.start('127.0.0.1', self.port)
        self.addCleanup(self.companion.stop)
        self.origin, self.cookie = f'http://127.0.0.1:{self.port}', ''

    def pair(self):
        code = self.companion.state(False)['pairingCode']
        status, result, headers = self.request('POST', '/api/phone/pair', {'code': code})
        self.assertEqual(status, 200, result)
        self.cookie = headers['Set-Cookie'].split(';', 1)[0]

    def test_unpaired_has_static_shell_but_no_private_resource_access(self):
        with patch.object(resources, '_fetch_json', side_effect=AssertionError('unexpected search')):
            status, shell, _ = self.request('GET', '/resources.html')
            self.assertEqual(status, 200)
            self.assertIn(b'resources.js', shell)
            self.assertNotIn(str(self.root).encode(), shell)
            for method, action, body in (('GET', 'state', None), ('POST', 'save', self.payload()),
                                          ('POST', 'search', {'q': 'chair', 'expectedRoot': str(self.root)})):
                self.assertEqual(self.request(method, '/api/phone/resources/' + action, body)[0], 401)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_paired_cookie_reads_saves_and_revocation_refuses_both(self):
        self.pair()
        self.assertEqual(self.request('GET', '/api/phone/resources/state')[0], 200)
        code, saved, _ = self.request('POST', '/api/phone/resources/save', self.payload())
        self.assertEqual(code, 200, saved)
        self.assertEqual(self.request('POST', '/api/phone/resources/save', self.payload())[0], 409)
        self.assertEqual(self.request('GET', '/api/phone/resources/state')[1]['items'][0]['name'], 'Fixture Model')
        before = (self.root / resources.STORE_RELATIVE).read_bytes()
        self.companion.logout(self.cookie.split('=', 1)[1])
        self.assertEqual(self.request('GET', '/api/phone/resources/state')[0], 401)
        self.assertEqual(self.request('POST', '/api/phone/resources/save', self.payload(expectedRevision=saved['revision']))[0], 401)
        self.assertEqual((self.root / resources.STORE_RELATIVE).read_bytes(), before)

    def test_paired_cross_site_or_missing_phone_header_rejected_without_write(self):
        self.pair()
        self.assertEqual(self.request('GET', '/api/phone/resources/state', headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)
        for headers in ({'Origin': 'https://attacker.example'}, {'X-Codex-Phone': '0'}):
            self.assertEqual(self.request('POST', '/api/phone/resources/save', self.payload(), headers)[0], 403)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_revocation_during_preview_network_cannot_return_success(self):
        self.pair()
        def revoke(url):
            self.companion.logout(self.cookie.split('=', 1)[1])
            return {'name': 'Unauthorized result'}
        with patch.object(resource_http, 'fetch_metadata', side_effect=revoke):
            code, result, _ = self.request('POST', '/api/phone/resources/preview', {'expectedRoot': str(self.root), 'url': 'https://example.com/a'})
        self.assertEqual(code, 401, result)
        self.assertNotIn('name', result)
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
