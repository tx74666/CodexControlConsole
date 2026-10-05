"""Disposable OAuth/event worker fixtures. No provider requests or inference."""
import base64
import copy
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import workflow_subscription as api
from workflow_service import WorkflowError


def protect_fixture(data, decrypt=False):
    if decrypt:
        if not data.startswith(b"FIXTURE:"):
            raise ValueError("bad fixture")
        return base64.b64decode(data[8:], validate=True)
    return b"FIXTURE:" + base64.b64encode(data)


class Remote:
    def __init__(self):
        self.calls = []
        self.tokens = {"token_type": "Bearer", "access_token": "fixture-access-A",
                       "refresh_token": "fixture-refresh-A", "id_token": "fixture-id-token-A",
                       "scope": api.SCOPES, "expires_in": 3600}
        self.catalog = {"models": [{"slug": "gpt-6-astra", "display_name": "Astra", "visibility": "list"},
                                    {"slug": "private-model", "display_name": "Private", "visibility": "hidden"}]}
        self.refresh = None
        self.on_token = None
        self.discovery = {"issuer": api.ISSUER, "revocation_endpoint": api.ISSUER + "/oauth/revoke"}

    def __call__(self, url, **kwargs):
        self.calls.append((url, copy.deepcopy(kwargs)))
        if url == api.TOKEN:
            if self.on_token:
                self.on_token(kwargs)
            if kwargs["form"]["grant_type"] == "refresh_token" and self.refresh:
                return self.refresh()
            return copy.deepcopy(self.tokens)
        if url == api.MODELS:
            return copy.deepcopy(self.catalog)
        if url == api.DISCOVERY:
            return copy.deepcopy(self.discovery)
        if kwargs.get("revoke"):
            return {}
        raise AssertionError("Unexpected fixture endpoint")


def completed(model):
    return {"ok": True, "status": "completed", "code": None, "responseCompleted": True,
            "terminalEventObserved": True, "terminalStatus": "completed",
            "completionEvidence": "response.completed", "completionSource": "completed_stream_deltas",
            "providerErrorObserved": False, "requestedModel": model, "actualModel": model,
            "responseId": "resp_fixture", "output": "这是一条隔离回答。", "retryAllowed": False}


class Service:
    def __init__(self, directory):
        self.data_dir = directory
        self.notifiers = set()
        self.claims, self.intents, self.successes, self.failures = [], [], [], []
        self.prepared = {}
        self.sealed = set()
        self.done = threading.Event()
        self.subscription = None

    def register_dispatch_notifier(self, notifier):
        self.notifiers.add(notifier)

    def unregister_dispatch_notifier(self, notifier):
        self.notifiers.discard(notifier)

    def subscription_claim(self, identifier, binding):
        self.claims.append(identifier)
        if identifier not in self.prepared or identifier in self.sealed:
            return None
        row = self.prepared[identifier]
        expected = row["subscription"]
        self.subscription.validate_selection(expected["modelSlug"], expected["catalogRevision"], expected["connectionId"])
        self.sealed.add(identifier)
        return row

    def subscription_send_intent(self, identifier, token, binding):
        if identifier in self.intents:
            raise WorkflowError("Fixture refuses duplicate intent", 409, "subscription_send_reserved")
        self.intents.append(identifier)
        return {"sendIntentRecorded": True, "confirmedAt": "2026-10-06T01:00:00Z"}

    def subscription_complete(self, identifier, token, receipt):
        self.successes.append((identifier, token, receipt))
        self.done.set()

    def subscription_fail(self, identifier, token, receipt):
        self.failures.append((identifier, token, receipt))
        self.done.set()

    def list_pending(self):
        raise AssertionError("Startup must not scan or replay pending rows")


class SubscriptionChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="console-subscription-check-")
        self.directory = Path(self.temp.name)
        self.service = Service(self.directory)
        self.remote = Remote()
        self.runner_calls = []
        self.identity = {"iss": api.ISSUER, "sub": "fixture-account-A"}
        self.now = 1_800_000_000.0
        self.broker = self.make_broker()

    def make_broker(self):
        broker = api.SubscriptionBroker(self.service, request_json=self.remote, protect=protect_fixture,
            verify_identity=lambda *_: dict(self.identity), run_response=self.run_provider, clock=lambda: self.now)
        # Callback mechanics are pure fixtures; no socket or real OAuth is opened.
        broker._open_callback = lambda: setattr(broker, "_callback_server", SimpleNamespace(
            server_port=31234, shutdown=lambda: None, server_close=lambda: None))
        self.service.subscription = broker
        return broker

    def run_provider(self, token, model, inputs):
        self.runner_calls.append((token, model, inputs))
        return completed(model)

    def tearDown(self):
        self.broker.close()
        self.temp.cleanup()

    def login(self):
        result = self.broker.begin_signin()
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(result["authorizationUrl"]).query)
        self.broker.handle_callback({"state": query["state"], "code": ["fixture-code"], "client_id": ["issued-fixture-client"]})
        return query

    def binding(self):
        status = self.broker.get_status()
        return self.broker.validate_selection("gpt-6-astra", status["catalogRevision"], status["connectionId"])

    def prepare(self, identifier="a" * 32, text="原始问题", images=None):
        images = images or []
        frozen = {"text": text, "history": [{"role": "assistant", "content": "仅本记录历史", "createdAt": "2026-10-05T00:00:00Z"}],
            "images": [row[0] for row in images], "submissionTime": {"confirmedAt": "2026-10-06T01:00:00Z", "timeZone": "Asia/Shanghai"},
            "recordTitle": "同一来源", "actionPlanning": {"secretOutsideScope": "must-not-send"}}
        row = {"dispatch": {"id": identifier}, "frozen": frozen, "text": text, "claimToken": "c" * 32,
               "subscription": self.binding(), "imageBytes": images}
        self.service.prepared[identifier] = row
        return row

    def test_constructor_get_status_and_start_do_not_authenticate_or_scan(self):
        self.assertFalse(self.broker.get_status()["connected"])
        self.assertFalse(self.broker.directory.exists())
        self.assertIsNone(self.broker._process_file)
        self.broker.start()
        self.assertIn(self.broker, self.service.notifiers)
        self.assertEqual(self.remote.calls, [])
        self.assertEqual(self.service.claims, [])
        self.assertEqual(self.runner_calls, [])

    def test_concurrent_start_registers_one_serial_worker(self):
        registrations, errors = [], []
        original = self.service.register_dispatch_notifier
        def register(notifier):
            registrations.append(notifier)
            time.sleep(0.02)
            original(notifier)
        self.service.register_dispatch_notifier = register
        ready = threading.Barrier(2)
        def start():
            try:
                ready.wait(2)
                self.broker.start()
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=start) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
        self.assertEqual(errors, [])
        self.assertEqual(registrations, [self.broker])

    def test_separate_namespace_leaves_probe_credentials_untouched(self):
        probe = self.directory / "siwc-probe" / "state"
        probe.mkdir(parents=True)
        other = probe / "credentials.dpapi"
        other.write_bytes(b"unrelated-private-sentinel")
        self.login()
        self.assertEqual(other.read_bytes(), b"unrelated-private-sentinel")
        protected = self.broker._credential_path.read_bytes()
        self.assertNotIn(b"fixture-access-A", protected)
        self.assertNotIn(b"fixture-refresh-A", protected)
        self.assertNotIn("fixture-account-A", json.dumps(self.broker.get_status()))

    def test_invalid_directory_degrades_without_breaking_console(self):
        bad = self.directory / "not-a-directory"
        bad.write_bytes(b"preserve")
        other = api.SubscriptionBroker(self.service, bad, request_json=self.remote, protect=protect_fixture)
        try:
            other.start()
            self.assertFalse(other.get_status()["connected"])
            self.assertEqual(other.get_status()["status"], "store_unavailable")
            with self.assertRaises(WorkflowError):
                other.begin_signin()
            self.assertEqual(bad.read_bytes(), b"preserve")
        finally:
            other.close()

    @unittest.skipUnless(os.name == "nt", "Native Windows 8.3 path identity")
    def test_windows_short_alias_canonicalizes_same_directory_without_reparse(self):
        long_parent = self.directory / "Console subscription long directory name"
        long_parent.mkdir()
        long_parent = long_parent.resolve()
        function = ctypes.WinDLL("kernel32", use_last_error=True).GetShortPathNameW
        function.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong]
        function.restype = ctypes.c_ulong
        length = function(str(long_parent), None, 0)
        self.assertGreater(length, 0)
        buffer = ctypes.create_unicode_buffer(length)
        self.assertGreater(function(str(long_parent), buffer, length), 0)
        short = Path(buffer.value)
        if short.absolute() == long_parent:
            self.skipTest("This NTFS temp path has no distinct on-disk 8.3 alias")
        self.assertTrue(short.samefile(long_parent))
        other = api.SubscriptionBroker(self.service, short / "auth", request_json=self.remote, protect=protect_fixture)
        try:
            other.start()
            self.assertTrue(other._store_available, other.get_status()["error"])
            self.assertEqual(other.directory, long_parent / "auth")
            self.assertEqual(other._registry_path.parent, long_parent / "auth")
            self.assertEqual(self.remote.calls, [])
        finally:
            other.close()

    @unittest.skipUnless(os.name == "nt", "Native Windows junction ancestors")
    def test_windows_ancestor_junction_rejected_before_creating_store(self):
        target, junction = self.directory / "real-target", self.directory / "junction-ancestor"
        target.mkdir()
        result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(target)],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(junction.is_junction())
        other = api.SubscriptionBroker(self.service, junction / "must-not-create", request_json=self.remote, protect=protect_fixture)
        try:
            other.start()
            self.assertFalse(other._store_available)
            self.assertEqual(other.get_status()["error"], "subscription_store_path_invalid")
            self.assertFalse((target / "must-not-create").exists())
            self.assertEqual(self.remote.calls, [])
        finally:
            other.close()
            junction.rmdir()  # Removes this isolated junction only; never recurse into its target.

    def test_every_store_file_reparse_attribute_rejected_before_open(self):
        original = Path.lstat
        for index, name in enumerate(("registration.json", "connection.dpapi", "identity-hint.dpapi", "connection.lock")):
            directory = self.directory / ("reparse-case-" + str(index))
            directory.mkdir()
            # The provider canonicalizes legitimate Windows short-name aliases.
            # Mark the actual same file, even when CI's TEMP uses RUNNER~1.
            file = (directory / name).resolve()
            file.write_bytes(b"owned-fixture-sentinel")
            def information(path, *args, file=file, **kwargs):
                value = original(path, *args, **kwargs)
                if path == file:
                    return SimpleNamespace(st_mode=value.st_mode, st_file_attributes=0x400)
                return value
            other = api.SubscriptionBroker(self.service, directory, request_json=self.remote, protect=protect_fixture)
            try:
                with patch.object(Path, "lstat", information):
                    other.start()
                self.assertFalse(other._store_available)
                self.assertEqual(other.get_status()["error"], "subscription_store_path_invalid")
                self.assertEqual(file.read_bytes(), b"owned-fixture-sentinel")
            finally:
                other.close()
        self.assertEqual(self.remote.calls, [])

    @unittest.skipUnless(os.name == "nt", "Native Windows mandatory file range lock")
    def test_windows_eof_mutex_blocks_second_broker_but_backup_reads_and_hashes(self):
        self.broker.start()
        file = self.broker.directory / "connection.lock"
        with file.open("rb") as independent:
            self.assertEqual(independent.read(16), b"0")
        self.assertEqual(file.read_bytes(), b"0")
        self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), hashlib.sha256(b"0").hexdigest())
        digest = hashlib.sha256()
        with file.open("rb") as independent:
            for block in iter(lambda: independent.read(128 * 1024), b""):
                digest.update(block)
        self.assertEqual(digest.hexdigest(), hashlib.sha256(b"0").hexdigest())
        self.assertEqual(file.stat().st_size, 1)
        second = api.SubscriptionBroker(self.service, self.broker.directory, request_json=self.remote, protect=protect_fixture)
        try:
            second.start()
            self.assertFalse(second._store_available)
            self.assertEqual(second.get_status()["status"], "store_unavailable")
            self.assertEqual(file.read_bytes(), b"0")
            self.assertEqual(self.remote.calls, [])
        finally:
            second.close()
        self.broker.close()
        third = api.SubscriptionBroker(self.service, self.broker.directory, request_json=self.remote, protect=protect_fixture)
        try:
            third.start()
            self.assertTrue(third._store_available)
            self.assertEqual(file.read_bytes(), b"0")
        finally:
            third.close()

    def test_pkce_scope_resource_and_issued_client_saved_before_exchange(self):
        self.remote.on_token = lambda _: self.assertEqual(
            json.loads(self.broker._registry_path.read_bytes())["clientId"], "issued-fixture-client")
        query = self.login()
        self.assertEqual(query["client_id"], ["dynamic_agent_client"])
        self.assertEqual(query["resource"], [api.RESOURCE])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertIn("chatgpt.tokens.use.direct", query["scope"][0].split())
        token_form = next(kwargs["form"] for url, kwargs in self.remote.calls if url == api.TOKEN)
        digest = hashlib.sha256(token_form["code_verifier"].encode("ascii")).digest()
        self.assertEqual(query["code_challenge"], [base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")])
        self.assertEqual(token_form["client_id"], "issued-fixture-client")
        self.assertEqual(token_form["redirect_uri"], query["redirect_uri"][0])

    def test_wrong_state_no_exchange_and_duplicate_correct_callback_consumed(self):
        result = self.broker.begin_signin()
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(result["authorizationUrl"]).query)
        with self.assertRaises(WorkflowError):
            self.broker.handle_callback({"state": ["wrong"], "code": ["fixture-code"]})
        self.assertEqual(self.remote.calls, [])
        valid = {"state": query["state"], "code": ["fixture-code"], "client_id": ["issued-fixture-client"]}
        self.broker.handle_callback(valid)
        count = len(self.remote.calls)
        with self.assertRaises(WorkflowError):
            self.broker.handle_callback(valid)
        self.assertEqual(len(self.remote.calls), count)

    def test_duplicate_callback_field_cannot_exchange_and_consumes_matching_state(self):
        result = self.broker.begin_signin()
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(result["authorizationUrl"]).query)
        with self.assertRaises(WorkflowError):
            self.broker.handle_callback({"state": query["state"], "code": ["a", "b"], "client_id": ["issued-fixture-client"]})
        self.assertIsNone(self.broker._pending)
        self.assertEqual(self.remote.calls, [])

    def test_login_denied_preserves_registration_and_no_tokens_requested(self):
        result = self.broker.begin_signin()
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(result["authorizationUrl"]).query)
        before = self.broker._registry_path.read_bytes()
        with self.assertRaises(WorkflowError):
            self.broker.handle_callback({"state": query["state"], "error": ["access_denied"], "error_description": ["sensitive"]})
        self.assertEqual(self.remote.calls, [])
        self.assertEqual(before, self.broker._registry_path.read_bytes())
        self.assertNotIn("sensitive", json.dumps(self.broker.get_status()))

    def test_returning_login_uses_issued_client_host_and_signed_hint(self):
        first = self.login()
        self.broker.disconnect()
        result = self.broker.begin_signin()
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(result["authorizationUrl"]).query)
        self.assertEqual(query["client_id"], ["issued-fixture-client"])
        self.assertEqual(query["ext_agent_host_id"], first["ext_agent_host_id"])
        self.assertEqual(query["id_token_hint"], ["fixture-id-token-A"])
        self.assertNotIn("agent_name_hint", query)
        self.assertNotIn("fixture-id-token-A", json.dumps(self.broker.get_status()))

    def test_returning_other_account_cannot_replace_connection(self):
        self.login()
        original = self.broker._credential_path.read_bytes()
        self.identity["sub"] = "fixture-account-B"
        result = self.broker.begin_signin()
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(result["authorizationUrl"]).query)
        with self.assertRaises(WorkflowError) as failure:
            self.broker.handle_callback({"state": query["state"], "code": ["fixture-code"]})
        self.assertEqual(failure.exception.code, "subscription_account_changed")
        self.assertEqual(original, self.broker._credential_path.read_bytes())

    def test_direct_scope_missing_does_not_fetch_models_or_enable_inference(self):
        self.remote.tokens["scope"] = "openid profile email offline_access"
        with self.assertRaises(WorkflowError):
            self.login()
        self.assertFalse(self.broker.get_status()["connected"])
        self.assertFalse(any(url == api.MODELS for url, _ in self.remote.calls))
        self.assertEqual(self.runner_calls, [])

    def test_catalog_visibility_exact_model_and_revision_gate(self):
        self.login()
        binding = self.binding()
        self.assertEqual(set(binding), api.BINDING_KEYS)
        self.assertEqual(self.broker.get_status()["models"], [{"slug": "gpt-6-astra", "displayName": "Astra"}])
        for model, revision, connection in (("private-model", binding["catalogRevision"], binding["connectionId"]),
                (binding["modelSlug"], "0" * 64, binding["connectionId"]),
                (binding["modelSlug"], binding["catalogRevision"], "another-connection")):
            with self.assertRaises(WorkflowError):
                self.broker.validate_selection(model, revision, connection)
        self.remote.catalog["models"][0]["display_name"] = "New actual name"
        self.broker.refresh_catalog()
        with self.assertRaises(WorkflowError):
            self.broker._check_binding(binding)

    def test_cached_get_and_validate_do_not_fetch_or_refresh(self):
        self.login()
        binding = self.binding()
        count = len(self.remote.calls)
        self.broker._connection["expiresAt"] = self.now - 1
        for _ in range(3):
            self.broker.get_status()
            self.broker._check_binding(binding)
        self.assertEqual(len(self.remote.calls), count)

    def test_expired_pending_is_not_forever_busy_or_model_refresh_block(self):
        self.login()
        self.broker.begin_signin()
        self.broker._pending["deadline"] = time.monotonic() - 1
        pending = copy.deepcopy(self.broker._pending)
        self.assertFalse(self.broker.get_status()["busy"])
        self.assertEqual(self.broker.get_status()["status"], "signin_expired")
        self.assertEqual(self.broker._pending, pending)
        self.broker.refresh_catalog()
        self.assertTrue(self.broker.get_status()["connected"])

    def test_serial_refresh_rotates_once_and_uses_issued_client_resource_omits_scope(self):
        self.login()
        binding = self.binding()
        self.broker._connection["expiresAt"] = self.now + 1
        def refresh():
            time.sleep(0.02)
            return {**self.remote.tokens, "access_token": "fixture-access-B", "refresh_token": "fixture-refresh-B"}
        self.remote.refresh = refresh
        outputs, errors = [], []
        def request():
            try:
                outputs.append(self.broker.credential_token(binding))
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=request) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
        self.assertEqual(errors, [])
        self.assertEqual(outputs, ["fixture-access-B", "fixture-access-B"])
        forms = [kwargs["form"] for url, kwargs in self.remote.calls if url == api.TOKEN and kwargs["form"]["grant_type"] == "refresh_token"]
        self.assertEqual(len(forms), 1)
        self.assertEqual(forms[0], {"grant_type": "refresh_token", "client_id": "issued-fixture-client",
            "refresh_token": "fixture-refresh-A", "resource": api.RESOURCE})
        stored = json.loads(protect_fixture(self.broker._credential_path.read_bytes()[len(api.PROTECTED_HEADER):], decrypt=True))
        self.assertEqual(stored["refreshToken"], "fixture-refresh-B")

    def test_unknown_refresh_is_durable_block_and_never_reuses_old_token(self):
        self.login()
        binding = self.binding()
        self.broker._connection["expiresAt"] = self.now - 1
        def lost():
            raise WorkflowError("must never leak fixture-refresh-A", 409, "subscription_transport_unknown")
        self.remote.refresh = lost
        with self.assertRaises(WorkflowError):
            self.broker.credential_token(binding)
        count = len(self.remote.calls)
        with self.assertRaises(WorkflowError):
            self.broker.credential_token(binding)
        self.assertEqual(len(self.remote.calls), count)
        stored = json.loads(protect_fixture(self.broker._credential_path.read_bytes()[len(api.PROTECTED_HEADER):], decrypt=True))
        self.assertTrue(stored["refreshBlocked"])
        self.assertEqual(stored["refreshToken"], "fixture-refresh-A")
        self.assertNotIn("fixture-refresh-A", json.dumps(self.broker.get_status()))

    def stored_connection(self):
        return json.loads(protect_fixture(self.broker._credential_path.read_bytes()[len(api.PROTECTED_HEADER):], decrypt=True))

    def test_refresh_reservation_save_failure_makes_no_token_request(self):
        self.login()
        binding = self.binding()
        self.broker._connection["expiresAt"] = self.now - 1
        before_file, before_calls = self.broker._credential_path.read_bytes(), len(self.remote.calls)
        def cannot_reserve(_):
            raise OSError("fixture disk full")
        self.broker._save_connection = cannot_reserve
        with self.assertRaises(WorkflowError) as failure:
            self.broker.credential_token(binding)
        self.assertEqual(failure.exception.code, "subscription_refresh_reservation_failed")
        self.assertEqual(len(self.remote.calls), before_calls)
        self.assertEqual(self.broker._credential_path.read_bytes(), before_file)
        self.assertTrue(self.broker._connection["refreshBlocked"])

    def test_rotated_token_save_failure_leaves_durable_block_on_restart(self):
        self.login()
        binding = self.binding()
        self.broker._connection["expiresAt"] = self.now - 1
        original = self.broker._save_connection
        def saving(connection):
            if connection["accessToken"] == "fixture-access-B":
                raise OSError("fixture disk full after rotation")
            return original(connection)
        self.broker._save_connection = saving
        def rotated():
            self.assertTrue(self.stored_connection()["refreshBlocked"])
            return {**self.remote.tokens, "access_token": "fixture-access-B", "refresh_token": "fixture-refresh-B"}
        self.remote.refresh = rotated
        with self.assertRaises(WorkflowError):
            self.broker.credential_token(binding)
        self.assertTrue(self.stored_connection()["refreshBlocked"])
        before_calls = len(self.remote.calls)
        self.broker.close()
        self.broker = self.make_broker()
        self.broker.start()
        self.assertEqual(self.broker.get_status()["status"], "reauth_required")
        with self.assertRaises(WorkflowError):
            self.broker.refresh_catalog()
        self.assertEqual(len(self.remote.calls), before_calls)

    def test_crash_inside_refresh_has_prior_durable_reservation(self):
        self.login()
        binding = self.binding()
        self.broker._connection["expiresAt"] = self.now - 1
        def interrupted():
            self.assertTrue(self.stored_connection()["refreshBlocked"])
            raise SystemExit("simulated process crash, no real termination")
        self.remote.refresh = interrupted
        with self.assertRaises(SystemExit):
            self.broker.credential_token(binding)
        self.assertTrue(self.stored_connection()["refreshBlocked"])
        before_calls = len(self.remote.calls)
        self.broker.close()
        self.broker = self.make_broker()
        self.broker.start()
        self.assertFalse(self.broker.get_status()["connected"])
        with self.assertRaises(WorkflowError):
            self.broker.refresh_catalog()
        self.assertEqual(len(self.remote.calls), before_calls)

    def test_definite_refresh_refusal_restore_failure_keeps_durable_block(self):
        self.login()
        binding = self.binding()
        self.broker._connection["expiresAt"] = self.now - 1
        original = self.broker._save_connection
        def saving(connection):
            if not connection["refreshBlocked"]:
                raise OSError("fixture restore failure")
            return original(connection)
        self.broker._save_connection = saving
        def unavailable():
            error = WorkflowError("fixture HTTP refusal", 409, "temporarily_unavailable")
            error.remote_status = 503
            raise error
        self.remote.refresh = unavailable
        with self.assertRaises(WorkflowError) as failure:
            self.broker.credential_token(binding)
        self.assertEqual(failure.exception.code, "subscription_refresh_restore_failed")
        self.assertTrue(self.stored_connection()["refreshBlocked"])
        before_calls = len(self.remote.calls)
        with self.assertRaises(WorkflowError):
            self.broker.credential_token(binding)
        self.assertEqual(len(self.remote.calls), before_calls)

    def test_definite_temporary_refresh_refusal_keeps_credentials_without_auto_retry(self):
        self.login()
        binding = self.binding()
        self.broker._connection["expiresAt"] = self.now - 1
        def unavailable():
            error = WorkflowError("temporary", 409, "temporarily_unavailable")
            error.remote_status = 503
            raise error
        self.remote.refresh = unavailable
        with self.assertRaises(WorkflowError):
            self.broker.credential_token(binding)
        count = len(self.remote.calls)
        self.assertFalse(self.broker._connection["refreshBlocked"])
        self.broker.get_status()
        self.assertEqual(len(self.remote.calls), count)
        self.remote.refresh = lambda: {**self.remote.tokens, "access_token": "fixture-access-B"}
        self.broker.refresh_catalog()
        self.assertEqual(self.broker._connection["accessToken"], "fixture-access-B")

    def test_restart_preserves_registration_hints_but_no_network_or_queue_replay(self):
        self.login()
        original = dict(self.broker._registry)
        self.broker.close()
        count = len(self.remote.calls)
        self.broker = self.make_broker()
        self.assertIsNone(self.broker._registry)
        self.assertEqual(self.broker.get_status()["status"], "disconnected")
        self.broker.start()
        self.assertEqual(self.broker._registry, original)
        self.assertEqual(self.broker.get_status()["status"], "catalog_required")
        self.assertEqual(len(self.remote.calls), count)
        self.assertEqual(self.service.claims, [])
        self.broker.refresh_catalog()
        self.assertTrue(self.broker.get_status()["connected"])

    def test_disconnect_revoke_bound_endpoint_keeps_mapping_and_inflight_rows(self):
        self.login()
        registry = dict(self.broker._registry)
        self.prepare()
        result = self.broker.disconnect()
        self.assertFalse(result["connected"])
        self.assertFalse(self.broker._credential_path.exists())
        self.assertTrue(self.broker._hint_path.exists())
        self.assertEqual(self.broker._registry["hostId"], registry["hostId"])
        self.assertEqual(self.broker._registry["clientId"], registry["clientId"])
        self.assertEqual(self.service.failures, [])
        url, kwargs = self.remote.calls[-1]
        self.assertEqual(url, api.ISSUER + "/oauth/revoke")
        self.assertEqual(kwargs["form"], {"token": "fixture-refresh-A", "token_type_hint": "refresh_token", "client_id": "issued-fixture-client"})

    def test_bad_revocation_endpoint_is_not_forwarded_and_status_truthful(self):
        self.login()
        self.remote.discovery["revocation_endpoint"] = "https://other.invalid/revoke"
        result = self.broker.disconnect()
        self.assertEqual(result["status"], "disconnected_revocation_unconfirmed")
        self.assertEqual(result["error"], "subscription_remote_revocation_unconfirmed")
        self.assertFalse(any(url.startswith("https://other.invalid") for url, _ in self.remote.calls))

    def test_selected_text_context_original_timestamp_and_actual_image_bytes_only(self):
        self.login()
        data = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j2ioAAAAASUVORK5CYII=")
        image = {"id": "b" * 32, "mimeType": "image/png", "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                 "path": "C:/private/original.png"}
        prepared = self.prepare(text="原始问题，保持原样", images=[(image, data)])
        inputs = api.build_input(prepared)
        text = inputs[0]["content"][0]["text"]
        self.assertIn("原始问题，保持原样", text)
        self.assertIn("2026-10-06T01:00:00Z", text)
        self.assertIn("2026-10-05T00:00:00Z", text)
        self.assertNotIn("C:/private/original.png", json.dumps(inputs))
        self.assertNotIn("must-not-send", json.dumps(inputs))
        self.assertEqual(inputs[0]["content"][1]["image_url"], "data:image/png;base64," + base64.b64encode(data).decode("ascii"))

    def test_pure_image_send_and_changed_bytes_fail_without_intent(self):
        self.login()
        data = b"selected-image-copy"
        image = {"id": "b" * 32, "mimeType": "image/png", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        row = self.prepare(text="", images=[(image, data)])
        self.assertEqual(len(api.build_input(row)[0]["content"]), 2)
        row["imageBytes"] = [(image, b"wrong-copy")]
        self.broker._process("a" * 32)
        self.assertEqual(self.service.intents, [])
        self.assertEqual(self.runner_calls, [])
        self.assertEqual(self.service.failures[-1][2]["status"], "failed")

    def test_commit_notification_deduplicates_and_only_one_real_runner_call(self):
        self.login()
        self.prepare()
        self.broker.start()
        self.broker.notify_committed(["a" * 32, "a" * 32])
        self.assertTrue(self.service.done.wait(2))
        self.assertEqual(self.service.intents, ["a" * 32])
        self.assertEqual(len(self.runner_calls), 1)
        self.assertEqual(len(self.service.successes), 1)
        self.assertEqual(self.service.successes[0][0], "a" * 32)

    def test_browser_or_old_dispatch_never_reaches_runner(self):
        self.login()
        self.broker._process("d" * 32)
        self.assertEqual(self.service.intents, [])
        self.assertEqual(self.runner_calls, [])

    def test_intent_ack_unknown_is_not_reported_known_unsent_or_retried(self):
        self.login()
        self.prepare()
        def lost(identifier, *_):
            self.service.intents.append(identifier)
            raise OSError("fixture acknowledgement lost")
        self.service.subscription_send_intent = lost
        self.broker._process("a" * 32)
        self.assertEqual(self.runner_calls, [])
        receipt = self.service.failures[-1][2]
        self.assertEqual(receipt["status"], "unknown")
        self.assertFalse(receipt["requestSent"])
        self.broker._process("a" * 32)
        self.assertEqual(self.service.intents, ["a" * 32])

    def test_lost_inference_response_has_one_post_and_retains_unknown(self):
        self.login()
        self.prepare()
        def lost(*args):
            self.runner_calls.append(args)
            raise TimeoutError("fixture token text should not escape")
        self.broker._runner = lost
        self.broker._process("a" * 32)
        self.broker._process("a" * 32)
        self.assertEqual(len(self.runner_calls), 1)
        receipt = self.service.failures[-1][2]
        self.assertEqual(receipt["status"], "unknown")
        self.assertTrue(receipt["requestSent"])
        self.assertFalse(receipt["retryAllowed"])

    def test_provider_partial_failure_is_not_completed_message(self):
        self.login()
        self.prepare()
        self.broker._runner = lambda *_: {"ok": False, "status": "failed", "code": "completed_output_empty",
            "output": "partial", "terminalEventObserved": False, "providerErrorObserved": True}
        self.broker._process("a" * 32)
        self.assertEqual(self.service.successes, [])
        self.assertEqual(self.service.failures[-1][2]["output"], "partial")

    def test_missing_terminal_or_different_model_never_marks_success(self):
        self.login()
        for index, change in enumerate(({"terminalEventObserved": False}, {"actualModel": "other-model"}, {"output": ""})):
            identifier = (str(index + 1) * 32)
            self.prepare(identifier)
            self.broker._runner = lambda _, model, inputs, change=change: {**completed(model), **change}
            self.broker._process(identifier)
        self.assertEqual(self.service.successes, [])
        self.assertEqual(len(self.service.failures), 3)

    def test_complete_130000_character_answer_is_not_downgraded(self):
        self.login()
        self.prepare()
        self.broker._runner = lambda _, model, inputs: {**completed(model), "output": "答" * 130000}
        self.broker._process("a" * 32)
        self.assertEqual(len(self.service.successes), 1)
        self.assertEqual(len(self.service.successes[0][2]["output"]), 130000)
        self.assertEqual(self.service.failures, [])

    def test_release_during_token_preparation_prevents_intent_and_post(self):
        self.login()
        self.prepare()
        original = self.broker.credential_token
        def released(binding):
            self.broker.notify_released(["a" * 32])
            return original(binding)
        self.broker.credential_token = released
        self.broker._process("a" * 32)
        self.assertEqual(self.runner_calls, [])
        self.assertEqual(self.service.intents, [])

    def test_service_callbacks_never_hold_credential_lock(self):
        self.login()
        self.prepare()
        for method in ("subscription_claim", "subscription_send_intent", "subscription_complete"):
            original = getattr(self.service, method)
            def guard(*args, original=original):
                self.assertFalse(self.broker._lock._is_owned())
                return original(*args)
            setattr(self.service, method, guard)
        self.broker._process("a" * 32)
        self.assertEqual(len(self.service.successes), 1)

    def test_disconnect_after_intent_prevents_http_and_preserves_ledger(self):
        self.login()
        self.prepare()
        original = self.service.subscription_send_intent
        def disconnected(*args):
            receipt = original(*args)
            self.broker.disconnect()
            return receipt
        self.service.subscription_send_intent = disconnected
        self.broker._process("a" * 32)
        self.assertEqual(self.service.intents, ["a" * 32])
        self.assertEqual(self.runner_calls, [])
        self.assertEqual(self.service.failures[-1][2]["status"], "unknown")
        self.assertFalse(self.service.failures[-1][2]["requestSent"])


class EndpointAndIdentityChecks(unittest.TestCase):
    def test_callback_exact_loopback_host_path_limits_and_duplicate_values(self):
        self.assertEqual(api._callback_query("/auth/callback?state=one&code=two", ["127.0.0.1:31234"], "127.0.0.1:31234")["state"], ["one"])
        for path, hosts in (("/auth/callback?state=one", ["localhost:31234"]),
                ("/auth/callback?state=one", ["127.0.0.1:31234", "127.0.0.1:31234"]),
                ("http://other.invalid/auth/callback", ["127.0.0.1:31234"]),
                ("/not-callback", ["127.0.0.1:31234"]),
                ("/auth/callback?" + "x" * 17000, ["127.0.0.1:31234"])):
            with self.assertRaises(WorkflowError):
                api._callback_query(path, hosts, "127.0.0.1:31234")

    def test_http_error_keeps_safe_code_without_token_body_header_or_redirect(self):
        secret = "fixture-access-secret"
        for returned, expected in ((secret, "subscription_http_401"), ("invalid_grant", "invalid_grant")):
            error = urllib.error.HTTPError(api.MODELS, 401, "contains " + secret, {"secret": secret},
                io.BytesIO(json.dumps({"error": {"code": returned, "message": secret}}).encode()))
            opener = SimpleNamespace(open=lambda *_args, **_kwargs: (_ for _ in ()).throw(error))
            with patch.object(api.urllib.request, "build_opener", return_value=opener):
                with self.assertRaises(WorkflowError) as failure:
                    api._remote_json(api.MODELS, bearer=secret)
            self.assertEqual(failure.exception.code, expected)
            self.assertNotIn(secret, str(failure.exception))
        for url in ("http://auth.openai.com/api/accounts/oauth/token", "https://other.invalid/token"):
            with self.assertRaises(WorkflowError):
                api._remote_json(url, form={"code": secret})
        self.assertIsNone(api._NoRedirect().redirect_request(None, None, 302, "ignored", {}, "https://other.invalid"))

    def test_real_signed_jwt_checks_issuer_audience_expiry_nonce_and_unique_jwks(self):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
        key.update(kid="fixture-kid", use="sig", alg="RS256")
        base = {"iss": api.ISSUER, "aud": "issued-fixture-client", "sub": "account-A",
                "exp": int(time.time()) + 300, "nonce": "fixture-nonce"}
        def encode(fields):
            return jwt.encode(fields, private, algorithm="RS256", headers={"kid": "fixture-kid"})
        def keys(url, **_):
            self.assertEqual(url, api.JWKS)
            return {"keys": [key]}
        self.assertEqual(api._verify_identity(encode(base), "issued-fixture-client", "fixture-nonce", keys)["sub"], "account-A")
        for change in ({"iss": "https://other.invalid"}, {"aud": "other-client"}, {"exp": int(time.time()) - 300},
                {"nonce": "different"}, {"aud": ["issued-fixture-client", "other-client"], "azp": "other-client"}):
            with self.assertRaises(WorkflowError):
                api._verify_identity(encode({**base, **change}), "issued-fixture-client", "fixture-nonce", keys)
        with self.assertRaises(WorkflowError):
            api._verify_identity(encode(base), "issued-fixture-client", "fixture-nonce", lambda *_: {"keys": [key, key]})
        hs = jwt.encode(base, "x" * 64, algorithm="HS256", headers={"kid": "fixture-kid"})
        with self.assertRaises(WorkflowError):
            api._verify_identity(hs, "issued-fixture-client", "fixture-nonce", keys)


if __name__ == "__main__":
    unittest.main()
