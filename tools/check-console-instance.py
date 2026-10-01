"""Isolated instance handoff checks; never contacts the installed Console port."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
import console_instance as instance


class OwnedServer:
    def __init__(self, *, accepted=True, retire=False, redirect=None):
        self.accepted = accepted
        self.retire = retire
        self.redirect = redirect
        self.requests = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, payload):
                content = json.dumps(payload).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                self.wfile.flush()

            def do_GET(self):
                owner.requests.append(('GET', self.path, None))
                if owner.redirect:
                    self.send_response(302)
                    self.send_header('Location', owner.redirect)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                else:
                    self.respond({'runtime': owner.runtime})

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                owner.requests.append(('POST', self.path, payload))
                accepted = (owner.accepted and self.path == '/api/console/retire'
                            and payload.get('expectedInstanceId') == owner.runtime['instanceId'])
                self.respond({'accepted': accepted})
                if accepted and owner.retire:
                    threading.Thread(target=owner.stop, daemon=True).start()

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.server.server_address[1]
        assert self.port != 8898
        self.runtime = {'version': '1.0.6', 'instanceId': '0123456789abcdef0123456789abcdef', 'handoffProtocol': 1}
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True)
        self._stop_lock = threading.Lock()
        self._stopped = False

    def __enter__(self):
        self.thread.start()
        return self

    def stop(self):
        with self._stop_lock:
            if not self._stopped:
                self.server.shutdown()
                self.server.server_close()
                self.thread.join(2)
                self._stopped = True

    def __exit__(self, *args):
        self.stop()

    def identity(self):
        return {'port': self.port, 'runtime': dict(self.runtime)}


class InstanceChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='console-instance-')
        self.root = Path(self.temp.name) / '資料 folder'
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def config(self, version='1.0.6', **changes):
        runtime = {'dataDirectory': str(self.root), 'installationId': 'installation-test', 'version': version}
        runtime.update(changes)
        return {'runtime': runtime}

    def test_semver_precedence_and_unknown_versions(self):
        versions = ['1.0.0-alpha', '1.0.0-alpha.1', '1.0.0-alpha.beta', '1.0.0-beta',
                    '1.0.0-beta.2', '1.0.0-beta.11', '1.0.0-rc.1', '1.0.0', '1.0.9', '1.0.10', '2.0.0']
        self.assertEqual(sorted(reversed(versions), key=instance.version_tuple), versions)
        self.assertEqual(instance.compare_versions('1.0.0+old', '1.0.0+new'), 0)
        self.assertLess(instance.version_tuple('0.0.0-dev'), instance.version_tuple('0.0.0'))
        for value in [None, 1, 'latest', '1.0', 'v1.0.0', '01.0.0', '1.0.0-01', '1.0.0-', '1.0.0+x..y', ' 1.0.0']:
            with self.subTest(value=value), self.assertRaises(instance.InvalidVersionError):
                instance.version_tuple(value)

    def test_discovery_matches_data_and_installation_selects_highest_version(self):
        payloads = {22000: self.config('1.0.9'),
                    22001: self.config('9.0.0', dataDirectory=str(self.root.parent / 'other')),
                    22002: self.config('9.0.0', installationId='another-installation'),
                    22003: self.config('1.0.10-rc.1'), 22004: self.config('1.0.10'),
                    22005: self.config('latest'), 22006: {'title': 'Codex World'},
                    22007: self.config('1.0.10+second-build')}
        calls = []

        def request(opener, port, route):
            calls.append((port, route))
            if port == 22008:
                raise instance.http.client.BadStatusLine('not HTTP')
            if port not in payloads:
                raise ConnectionRefusedError()
            return payloads[port]

        # Canonicalization also handles an explicit parent segment in the caller path.
        equivalent = self.root / '..' / self.root.name
        with patch.object(instance, '_request_json', side_effect=request), \
                patch.object(instance, '_windows_listener_ports', return_value=None):
            found = instance.find_running_console(22000, equivalent, 'installation-test')
        self.assertEqual(found['port'], 22004)
        self.assertEqual(found['runtime']['version'], '1.0.10')
        self.assertEqual(calls, [(port, '/api/console/config') for port in range(22000, 22030)])

    def test_discovery_ignores_html_unknown_identity_and_malformed_configuration(self):
        values = [ValueError('<title>Codex Console</title>'), {'title': 'Codex World'},
                  self.config('unknown'), self.config(dataDirectory='relative/path'),
                  self.config(installationId=''), {'runtime': []}, {'runtime': None}]

        def request(opener, port, route):
            value = values[(port - 23000) % len(values)]
            if isinstance(value, Exception):
                raise value
            return value

        with patch.object(instance, '_request_json', side_effect=request), \
                patch.object(instance, '_windows_listener_ports', return_value=None):
            self.assertIsNone(instance.find_running_console(23000, self.root, 'installation-test'))
        with self.assertRaises(instance.ConsoleInstanceError):
            instance.find_running_console(23000, self.root, '')

    def test_loopback_requests_disable_environment_proxy_and_refuse_redirects(self):
        proxy_environment = {'HTTP_PROXY': 'http://127.0.0.1:1', 'http_proxy': 'http://127.0.0.1:1',
                             'ALL_PROXY': 'http://127.0.0.1:1', 'NO_PROXY': '', 'no_proxy': ''}
        with OwnedServer() as target, patch.dict(os.environ, proxy_environment):
            payload = instance._request_json(instance._local_opener(), target.port, '/api/console/config')
            self.assertEqual(payload['runtime']['version'], '1.0.6')
            initial_count = len(target.requests)
            with OwnedServer(redirect=f'http://127.0.0.1:{target.port}/redirect-target') as redirect:
                with self.assertRaises(urllib.error.HTTPError):
                    instance._request_json(instance._local_opener(), redirect.port, '/api/console/config')
            self.assertEqual(len(target.requests), initial_count)

    def test_discovery_uses_listener_table_only_as_port_filter(self):
        payloads = {23502: self.config('1.0.9'), 23509: self.config('9.0.0', installationId='other'),
                    23512: self.config('1.0.10')}
        with patch.object(instance, '_windows_listener_ports', return_value=set(payloads)), \
                patch.object(instance, '_request_json', side_effect=lambda opener, port, route: payloads[port]) as request:
            found = instance.find_running_console(23500, self.root, 'installation-test')
        self.assertEqual(found['port'], 23512)
        self.assertEqual([call.args[1] for call in request.call_args_list], [23502, 23509, 23512])

    def test_discovery_finds_different_start_hint_and_preserves_it_on_version_ties(self):
        hint = self.root / instance.ACTIVE_INSTANCE_HINT
        hint.parent.mkdir()
        hint.write_text(json.dumps({'port': 28001, 'version': 'untrusted metadata'}), encoding='utf-8')
        payloads = {28001: self.config('1.0.7'), 29002: self.config('1.0.7')}

        def request(opener, port, route):
            if port not in payloads:
                raise ConnectionRefusedError()
            return payloads[port]

        with patch.object(instance, '_windows_listener_ports', return_value=set(payloads)), \
                patch.object(instance, '_request_json', side_effect=request) as requests:
            found = instance.find_running_console(29000, self.root, 'installation-test')
        self.assertEqual(found['port'], 28001)
        self.assertEqual([call.args[1] for call in requests.call_args_list], [28001, 29002])
        # A genuinely newer API version still outranks the hinted instance.
        payloads[29002] = self.config('1.0.8')
        with patch.object(instance, '_windows_listener_ports', return_value=set(payloads)), \
                patch.object(instance, '_request_json', side_effect=request):
            self.assertEqual(instance.find_running_console(29000, self.root, 'installation-test')['port'], 29002)

    def test_discovery_ignores_bad_stale_and_other_identity_hints(self):
        hint = self.root / instance.ACTIVE_INSTANCE_HINT
        hint.parent.mkdir()
        invalid_values = [b'{broken', b'[]', b' ' * (instance.MAX_HINT_BYTES + 1), b'{"port":true}',
                          b'{"port":0}', b'{"port":65536}', b'{"port":"28001"}']
        for raw in invalid_values:
            hint.write_bytes(raw)
            with self.subTest(raw=raw[:40]), patch.object(instance, '_windows_listener_ports', return_value=None), \
                    patch.object(instance, '_request_json', side_effect=ConnectionRefusedError()) as requests:
                self.assertIsNone(instance.find_running_console(29000, self.root, 'installation-test'))
                self.assertEqual([call.args[1] for call in requests.call_args_list], list(range(29000, 29030)))
        hint.write_text('{"port":28001}', encoding='utf-8')
        for response in (self.config('9.0.0', dataDirectory=str(self.root.parent / 'another-root')),
                         self.config('9.0.0', installationId='another-installation'), ConnectionRefusedError()):
            def request(opener, port, route):
                if port != 28001 or isinstance(response, Exception):
                    raise ConnectionRefusedError()
                return response
            with self.subTest(response=str(response)), patch.object(instance, '_windows_listener_ports', return_value=None), \
                    patch.object(instance, '_request_json', side_effect=request):
                self.assertIsNone(instance.find_running_console(29000, self.root, 'installation-test'))

    def test_real_listener_table_contains_owned_server_when_supported(self):
        if os.name != 'nt':
            self.assertIsNone(instance._windows_listener_ports())
            return
        with OwnedServer() as server:
            listening = instance._windows_listener_ports()
            self.assertIsNotNone(listening)
            self.assertIn(server.port, listening)

    def test_normal_handoff_posts_exact_identity_and_waits_for_original_port(self):
        with OwnedServer(retire=True) as server:
            self.assertTrue(instance.retire_older_instance(server.identity(), '1.0.10', timeout=2))
            self.assertEqual(server.requests, [('POST', '/api/console/retire',
                                                {'expectedInstanceId': server.runtime['instanceId'], 'version': '1.0.10'})])
            self.assertTrue(instance._port_is_closed(server.port, 0.1))

    def test_refused_and_timeout_handoffs_keep_original_server_alive(self):
        for accepted in (False, True):
            with self.subTest(accepted=accepted), OwnedServer(accepted=accepted) as server:
                started = time.monotonic()
                with self.assertRaises(instance.HandoffError):
                    instance.retire_older_instance(server.identity(), '1.0.10', timeout=0.2)
                self.assertLess(time.monotonic() - started, 1)
                self.assertEqual(len(server.requests), 1)
                payload = instance._request_json(instance._local_opener(), server.port, '/api/console/config')
                self.assertEqual(payload['runtime']['instanceId'], server.runtime['instanceId'])

    def test_handoff_rejects_unknown_unsupported_or_non_newer_without_network(self):
        normal = {'port': 24000, 'runtime': {'version': '1.0.6', 'handoffProtocol': 1,
                                           'instanceId': '0123456789abcdef0123456789abcdef'}}
        cases = [('1.0.6', {}), ('1.0.5', {}), ('unknown', {}), ('1.0.7', {'version': 'unknown'}),
                 ('1.0.7', {'handoffProtocol': 0}), ('1.0.7', {'handoffProtocol': True}),
                 ('1.0.7', {'instanceId': 'invalid'}), ('1.0.7', {'instanceId': 'a' * 16 + '\n'})]
        for version, changes in cases:
            item = {'port': normal['port'], 'runtime': {**normal['runtime'], **changes}}
            with self.subTest(version=version, changes=changes), patch.object(instance, '_local_opener') as opener:
                with self.assertRaises(instance.HandoffError):
                    instance.retire_older_instance(item, version)
                opener.assert_not_called()

    def test_handoff_does_not_retire_replacement_with_different_instance_id(self):
        with OwnedServer() as server:
            stale = server.identity()
            stale['runtime']['instanceId'] = 'fedcba9876543210fedcba9876543210'
            with self.assertRaises(instance.HandoffError):
                instance.retire_older_instance(stale, '1.0.7', timeout=0.2)
            self.assertFalse(instance._port_is_closed(server.port, 0.1))

    def test_ambiguous_socket_errors_do_not_confirm_retirement(self):
        with patch.object(instance.socket, 'create_connection', side_effect=TimeoutError()), \
                patch.object(instance, '_windows_listener_ports', return_value=None):
            self.assertFalse(instance._port_is_closed(25000, 0.1))
        with patch.object(instance.socket, 'create_connection', side_effect=TimeoutError()), \
                patch.object(instance, '_windows_listener_ports', return_value={25000}):
            self.assertFalse(instance._port_is_closed(25000, 0.1))
        with patch.object(instance.socket, 'create_connection', side_effect=TimeoutError()), \
                patch.object(instance, '_windows_listener_ports', return_value={25001}):
            self.assertTrue(instance._port_is_closed(25000, 0.1))

    def child(self, source, *args):
        kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        return subprocess.Popen([sys.executable, '-c', source, str(self.root), *args], cwd=str(PROJECT),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kwargs)

    def test_startup_lock_different_ports_contend_and_persistent_file_is_reused(self):
        code = '''import sys
from console_instance import StartupLock, StartupLockTimeout
try:
    with StartupLock(sys.argv[1], 26001, timeout=0.2):
        print('unexpected acquisition')
        raise SystemExit(2)
except StartupLockTimeout:
    print('timed out safely')
'''
        with instance.StartupLock(self.root, 26000):
            inode = (self.root / instance.STARTUP_LOCK_NAME).stat().st_ino
            process = self.child(code)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertIn('timed out safely', stdout)
        with instance.StartupLock(self.root / '..' / self.root.name, 26002, timeout=1):
            self.assertEqual((self.root / instance.STARTUP_LOCK_NAME).stat().st_ino, inode)
        self.assertTrue((self.root / instance.STARTUP_LOCK_NAME).is_file())

    def test_startup_lock_serializes_two_processes_without_deleting_lockfile(self):
        code = '''import json, sys, time
from console_instance import StartupLock
with StartupLock(sys.argv[1], int(sys.argv[2]), timeout=3):
    started = time.monotonic()
    time.sleep(0.1)
    finished = time.monotonic()
print(json.dumps([started, finished]))
'''
        with instance.StartupLock(self.root, 27000):
            processes = [self.child(code, str(port)) for port in (27001, 27002)]
            time.sleep(0.1)
            released = time.monotonic()
        intervals = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            intervals.append(json.loads(stdout))
        intervals.sort()
        self.assertGreaterEqual(intervals[0][0], released)
        self.assertGreaterEqual(intervals[1][0], intervals[0][1])
        self.assertTrue((self.root / instance.STARTUP_LOCK_NAME).exists())


if __name__ == '__main__':
    unittest.main()
