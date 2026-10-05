"""Optional relay entry points without importing the production bootstrap."""
import ast
import json
from pathlib import Path
import sys
import sqlite3
import tempfile
import unittest
import urllib.parse
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow_chat_relay import ChatRelayBroker
from workflow_service import WorkflowService


class BodyError(ValueError):
    status = 400


class FeedbackError(Exception):
    pass


class FakeBroker:
    def __init__(self, ready=False):
        self.started = 0
        self.reads = 0
        self.ready = ready

    def start(self):
        self.started += 1
        return False

    def public_status(self):
        self.reads += 1
        return {"enabled": False, "clientReady": self.ready, "capabilitiesVerified": False}


class Handler:
    def __init__(self, path, body=None, local=True, trusted=True):
        self.path, self.body = path, body
        self.local, self.trusted = local, trusted
        self.result, self.body_reads = None, 0

    def _private_phone_path(self):
        return False

    def require_trusted_post_context(self):
        if not self.trusted:
            self.send_json({"error": "fixture origin rejected"}, status=403)
        return self.trusted

    def require_local_request(self):
        if not self.local:
            self.send_json({"error": "fixture LAN rejected"}, status=403)
        return self.local

    def send_json(self, value, status=200):
        self.result = status, value

    def read_json_body(self, max_bytes=None):
        self.body_reads += 1
        return self.body


class IntegrationChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ast.parse((ROOT / "world_console.py").read_text(encoding="utf-8"))
        handler = next(item for item in source.body if isinstance(item, ast.ClassDef) and item.name == "ConsoleHandler")
        methods = [item for item in handler.body if isinstance(item, ast.FunctionDef)
                   and item.name in {"do_GET", "_dispatch_POST"}]
        cls.namespace = {"urllib": urllib, "uuid": uuid, "RequestBodyError": BodyError,
                         "FeedbackServiceError": FeedbackError,
                         "sqlite3": sqlite3,
                         "MAX_JSON_REQUEST_BYTES": 128 * 1024,
                         "BLENDER_MUTATION_API_PATHS": set()}
        exec(compile(ast.Module(body=methods, type_ignores=[]), "world_console.py", "exec"), cls.namespace)

    def setUp(self):
        self.broker = FakeBroker()
        self.namespace["CHAT_RELAY_BROKER"] = self.broker

    def call(self, handler, post=False):
        self.namespace["_dispatch_POST" if post else "do_GET"](handler)
        return handler.result

    def test_status_is_local_read_only(self):
        rejected = Handler("/api/console/chat-relay/status", local=False)
        self.assertEqual(self.call(rejected)[0], 403)
        self.assertEqual((self.broker.reads, self.broker.started), (0, 0))
        accepted = Handler("/api/console/chat-relay/status")
        self.assertEqual(self.call(accepted)[0], 200)
        self.assertEqual((self.broker.reads, self.broker.started, accepted.body_reads), (1, 0, 0))

    def test_start_requires_same_origin_and_local_gate(self):
        for local, trusted in ((True, False), (False, True)):
            handler = Handler("/api/console/chat-relay/start", {"requestId": str(uuid.uuid4())},
                              local=local, trusted=trusted)
            self.assertEqual(self.call(handler, post=True)[0], 403)
        self.assertEqual(self.broker.started, 0)

    def test_start_cannot_provision_or_accept_alternate_paths(self):
        invalid = [None, [], {}, {"requestId": "invalid"}, {"requestId": 2},
                   {"requestId": str(uuid.uuid4()), "enabled": True},
                   {"requestId": str(uuid.uuid4()), "dataDir": "private"},
                   {"requestId": str(uuid.uuid4()), "domContract": {}},
                   {"requestId": str(uuid.uuid4()).upper()}]
        for body in invalid:
            handler = Handler("/api/console/chat-relay/start", body)
            self.assertEqual(self.call(handler, post=True)[0], 400, body)
        handler = Handler("/api/console/chat-relay/start?enabled=1", {"requestId": str(uuid.uuid4())})
        self.assertEqual(self.call(handler, post=True)[0], 400)
        self.assertEqual(self.broker.started, 0)

    def test_start_uses_only_preexisting_approval_and_reports_disabled(self):
        handler = Handler("/api/console/chat-relay/start", {"requestId": str(uuid.uuid4())})
        status, result = self.call(handler, post=True)
        self.assertEqual(status, 200)
        self.assertFalse(result["enabled"])
        self.assertEqual((self.broker.started, self.broker.reads), (1, 1))

    def test_unavailable_optional_host_reports_failure_without_private_path(self):
        for failure in (OSError("fixture/private/path"), sqlite3.OperationalError("fixture/private/path")):
            with patch.object(self.broker, "start", side_effect=failure), patch.object(self.broker, "close", create=True) as close:
                handler = Handler("/api/console/chat-relay/start", {"requestId": str(uuid.uuid4())})
                status, result = self.call(handler, post=True)
                self.assertEqual((status, result["code"]), (503, "relay_start_unavailable"))
                self.assertNotIn("fixture/private/path", json.dumps(result))
                close.assert_called_once()

    def test_mobile_connection_is_not_a_model_capability_receipt(self):
        with tempfile.TemporaryDirectory(prefix="console-relay-capabilities-") as directory:
            service = WorkflowService(Path(directory) / "private", recover_jobs=False)
            service._chat_relay_broker = FakeBroker(ready=True)
            try:
                before = service.incubator_dispatches()
                for profile in ("fast", "high", "pro"):
                    result = service._mobile_execution(profile)
                    self.assertEqual(result["requestedProfile"], profile)
                    self.assertEqual(result["relayStatus"], "connected")
                    self.assertFalse(result["actualReceipt"]["verified"])
                    self.assertIsNone(result["actualReceipt"]["actualProfile"])
                    self.assertEqual(result["supportedProfiles"], [])
                self.assertEqual(service.incubator_dispatches(), before)
                self.assertEqual(service._chat_relay_broker.started, 0)
            finally:
                service.shutdown()

    def test_disabled_broker_status_and_start_do_not_create_approval(self):
        with tempfile.TemporaryDirectory(prefix="console-relay-disabled-") as directory:
            service = WorkflowService(Path(directory) / "CodexControlConsole" / "workflow-private", recover_jobs=False)
            broker = ChatRelayBroker(service)
            try:
                with service._db() as db:
                    before = list(db.execute("SELECT key,value FROM settings ORDER BY key"))
                with patch.dict("os.environ", {"LOCALAPPDATA": directory}):
                    for _ in range(2):
                        self.assertFalse(broker.start())
                        self.assertFalse(broker.public_status()["enabled"])
                with service._db() as db:
                    self.assertEqual(list(db.execute("SELECT key,value FROM settings ORDER BY key")), before)
                self.assertFalse((service.data_dir / "console-chat-relay-approved.json").exists())
                self.assertEqual(service.incubator_dispatches()["dispatches"], [])
            finally:
                broker.close()
                service.shutdown()


if __name__ == "__main__":
    unittest.main(verbosity=2)
