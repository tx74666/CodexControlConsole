"""Isolated desktop workflow HTTP, private files and window lifecycle checks.

Imports the actual handler with temporary runtime/media/publisher/desktop paths.
Never starts world_console.main, captures the screen, runs a user project, or
contacts a model. All listeners and durable state belong to this fixture.
"""
import http.client
import importlib
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from console_window_session import ConsoleWindowSessionService
from document_library import DocumentLibraryService
from phone_companion import PhoneCompanionService
from phone_device_store import PhoneDeviceStore
import phone_companion as phone
from workflow_models import WorkflowModels
from workflow_service import WorkflowService


def tiny_png():
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0\x20\x80\xff")) + chunk(b"IEND", b""))


class DesktopWorkflowChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "world_console" in sys.modules:
            raise RuntimeError("Run this isolated test as its own Python process; world_console must not be imported earlier.")
        cls.runtime = tempfile.TemporaryDirectory(prefix="codex-workflow-desktop-import-")
        root = Path(cls.runtime.name)
        data = root / "data"
        data.mkdir()
        # Prevent importing any legacy source cache/user data into this test.
        (data / ".cache-migrated-v0.3").write_text("isolated-check\n", encoding="utf-8")
        stub = root / "disabled-desktop.ps1"
        stub.write_text("throw 'Desktop operations disabled in this fixture.'\n", encoding="utf-8")
        cls.environment = patch.dict(os.environ, {
            "CODEX_CONTROL_DATA_DIR": str(data),
            "CODEX_CONTROL_PUBLISHER_STATE_FILE": str(root / "publisher.json"),
            "CODEX_CONTROL_TEMP_DIR": str(root / "tmp"),
            "CODEX_CONTROL_MUSIC_DIR": str(root / "music"),
            "CODEX_CONTROL_WALLPAPERS_DIR": str(root / "wallpapers"),
            "CODEX_CONTROL_BLENDER_PROJECT_ROOTS": str(root / "empty-projects"),
            "CODEX_CONTROL_DESKTOP_LAYOUT_DATA_DIR": str(root / "desktop-layout"),
            "CODEX_CONTROL_DESKTOP_LAYOUT_CURRENT": str(root / "desktop-layout" / "current.json"),
            "CODEX_CONTROL_DESKTOP_LAYOUT_SCRIPT": str(stub),
            "CODEX_CONTROL_DESKTOP_LAYOUT_STARTUP_FILE": str(root / "Startup" / "disabled.vbs"),
            "LOCALAPPDATA": str(root / "local"), "APPDATA": str(root / "roaming"),
        })
        cls.environment.start()
        cls.desktop = importlib.import_module("world_console")
        cls.imported_workflow = cls.desktop.WORKFLOW_SERVICE
        cls.imported_phone = cls.desktop.PHONE_COMPANION
        cls.imported_windows = cls.desktop.CONSOLE_WINDOW_SESSIONS
        cls.original_capture = cls.imported_workflow.callbacks.get("capture_screen")
        cls.original_memory_guard = cls.imported_workflow.callbacks.get("before_execute")
        if not cls.desktop.USER_DATA_DIR.is_relative_to(root):
            raise AssertionError("Desktop import did not honor the temporary data directory")
        if not cls.desktop.WORKFLOW_DATA_DIR.is_relative_to(root):
            raise AssertionError("Workflow import did not honor the temporary data directory")

    @classmethod
    def tearDownClass(cls):
        cls.imported_workflow.shutdown()
        cls.imported_phone.shutdown()
        cls.imported_windows.stop()
        cls.environment.stop()
        cls.runtime.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-workflow-desktop-http-")
        self.root = Path(self.temp.name)
        self.assets = self.root / "app"
        self.assets.mkdir()
        (self.assets / "index.html").write_text("<!doctype html><title>Isolated desktop</title>", encoding="utf-8")
        self.private = self.assets / "cache" / "workflow-private"
        self.models = WorkflowModels(self.private)
        self.workflow = WorkflowService(self.private, models=self.models,
            callbacks={"capture_screen": self.desktop.capture_workflow_screen,
                       "before_execute": self.desktop.allow_workflow_execution,
                       "work_finished": self.desktop.workflow_job_finished},
            computer_id="isolated-desktop-computer", computer_name="Isolated desktop",
            projects=[{"id": "console", "name": "Console fixture", "root": str(self.assets),
                       "capabilities": ["capture_screen", "result_import"], "allowGeneratedScripts": False}])
        library = self.root / "library"
        library.mkdir()
        self.documents = DocumentLibraryService(self.root / "documents.json")
        self.documents.select(str(library))
        self.device_store = PhoneDeviceStore(self.assets / "cache" / "phone-private")
        self.companion = PhoneCompanionService(self.documents, lambda: {}, self.assets, "1.0.test",
            computer_id="isolated-desktop-computer", device_store=self.device_store, workflow_service=self.workflow,
            interface_getter=lambda: [{"address": "127.0.0.1", "name": "Isolated transport", "fingerprint": "a" * 64}])
        self.windows = ConsoleWindowSessionService(self.desktop.shutdown_if_no_background_work, close_delay_seconds=0.03)
        self.server = self.desktop.ConsoleHTTPServer(("127.0.0.1", 0), self.desktop.ConsoleHandler)
        self.host = f"127.0.0.1:{self.server.server_port}"
        self.origin = "http://" + self.host
        self.globals = patch.multiple(self.desktop, APP_DIR=self.assets,
            WORKFLOW_DATA_DIR=self.private, WORKFLOW_MODELS=self.models, WORKFLOW_SERVICE=self.workflow,
            PHONE_COMPANION=self.companion, PHONE_DEVICE_STORE=self.device_store,
            DOCUMENT_LIBRARY=self.documents, CONSOLE_WINDOW_SESSIONS=self.windows, ACTIVE_SERVER=self.server)
        self.globals.start()
        self.worker = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.02), daemon=True)
        self.worker.start()
        self.workflow.start()

    def tearDown(self):
        self.windows.stop()
        self.companion.shutdown()
        self.workflow.shutdown()
        if self.worker.is_alive():
            self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=3)
        self.globals.stop()
        self.temp.cleanup()

    def request(self, path, method="GET", body=None, headers=None, raw=None):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        merged = {"Host": self.host}
        if method == "POST":
            merged.update({"Origin": self.origin, "Content-Type": "application/json"})
        merged.update(headers or {})
        data = raw if raw is not None else json.dumps(body or {}).encode("utf-8") if method == "POST" else None
        try:
            client.request(method, path, body=data, headers=merged)
            response = client.getresponse()
            content, response_headers = response.read(), dict(response.getheaders())
            try:
                value = json.loads(content.decode("utf-8"))
            except (ValueError, UnicodeError):
                value = content
            return response.status, value, response_headers
        finally:
            client.close()

    def session(self, action, identifier="isolated-window-123", **extra):
        status, result, _ = self.request("/api/console/window-session", "POST", {"action": action, "sessionId": identifier, **extra})
        self.assertEqual(status, 200, result)
        return result

    def wait_window_callback(self):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with self.windows._lock:
                called = self.windows._shutdown_requested
            if called:
                return
            time.sleep(0.01)
        self.fail("Window close callback did not run")

    def test_desktop_config_projects_and_background_are_real_http(self):
        status, config, _ = self.request("/api/workflow/config")
        self.assertEqual(status, 200, config)
        self.assertEqual(config["computer"]["id"], "isolated-desktop-computer")
        self.assertFalse(config["models"]["ready"])
        self.assertFalse(config["backgroundEnabled"])
        self.assertNotIn(str(self.assets), json.dumps(config))
        project_root = self.root / "approved-project"
        project_root.mkdir()
        status, result, _ = self.request("/api/workflow/projects", "POST", {"project": {
            "id": "approved", "name": "Approved fixture", "root": str(project_root),
            "capabilities": ["result_import"], "allowGeneratedScripts": False}})
        self.assertEqual(status, 200, result)
        self.assertTrue(any(item["id"] == "approved" for item in result["projects"]))
        self.assertNotIn(str(project_root), json.dumps(result))
        status, created, _ = self.request("/api/workflow/create", "POST", {"requestId": str(uuid.uuid4()), "projectId": "approved", "text": "Fixture record"})
        self.assertEqual(status, 200, created)
        self.assertEqual(created["record"]["projectId"], "approved")
        status, result, _ = self.request("/api/workflow/background", "POST", {"enabled": True})
        self.assertEqual(status, 200, result)
        self.assertTrue(result["backgroundEnabled"])
        self.assertEqual(self.request("/api/workflow/background", "POST", {"enabled": "true"})[0], 400)

    @unittest.skipUnless(os.name == "nt", "Write-only synthetic DPAPI secret requires Windows")
    def test_model_key_is_write_only_through_http_and_dpapi_at_rest(self):
        secret = "synthetic-desktop-fixture-secret-do-not-use"
        profile = {"id": "fixture", "endpoint": "http://127.0.0.1:1/v1", "protocol": "responses",
                   "model": "fixture-do-not-contact", "transcriptionModel": "fixture-voice", "key": secret}
        status, result, _ = self.request("/api/workflow/models", "POST", profile)
        self.assertEqual(status, 200, result)
        self.assertTrue(result["models"]["ready"])
        self.assertTrue(result["models"]["transcriptionReady"])
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(secret, json.dumps(self.request("/api/workflow/config")[1]))
        self.assertNotIn(secret.encode(), (self.private / "workflow-model-credentials.json").read_bytes())
        self.assertNotIn(secret.encode(), (self.private / "workflow-models.json").read_bytes())
        status, cleared, _ = self.request("/api/workflow/models", "POST", {**profile, "key": "", "clearKey": True})
        self.assertEqual(status, 200, cleared)
        self.assertFalse(cleared["models"]["ready"])
        self.assertFalse(cleared["models"]["providers"][0]["keyConfigured"])
        self.assertEqual(self.request("/api/workflow/models", "POST", {**profile, "endpoint": "http://external.example/v1"})[0], 400)

    def test_workflow_attachment_head_uses_authenticated_api_and_matches_get(self):
        status, created, _ = self.request("/api/workflow/create", "POST", {"requestId": str(uuid.uuid4()), "projectId": "console", "text": "Fixture attachment"})
        self.assertEqual(status, 200, created)
        boundary = "isolated-desktop-upload"
        identifier, png = created["record"]["id"], tiny_png()
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="requestId"\r\n\r\n{uuid.uuid4()}\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="recordId"\r\n\r\n{identifier}\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="fixture.png"\r\n'
                'Content-Type: image/png\r\n\r\n').encode() + png + f"\r\n--{boundary}--\r\n".encode()
        status, uploaded, _ = self.request("/api/workflow/upload", "POST", raw=body, headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
        self.assertEqual(status, 200, uploaded)
        url = uploaded["attachments"][0]["url"]
        status, content, headers = self.request(url, "HEAD")
        self.assertEqual((status, content), (200, b""))
        self.assertEqual(int(headers["Content-Length"]), len(png))
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.request(url)[1], png)

    def test_private_files_directory_case_and_encoded_get_head_are_denied(self):
        fixtures = {"workflow.sqlite3": b"PRIVATE SQLITE", "workflow-model-credentials.json": b"PRIVATE SECRET",
                    "workflow-models.json": b"PRIVATE MODEL", "jobs/job/execution.log": b"PRIVATE LOG",
                    "attachments/private.png": b"PRIVATE ATTACHMENT"}
        for relative, content in fixtures.items():
            target = self.private / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            # Preserve the real SQLite file; a WAL sibling still proves static denial.
            if target.exists():
                target = target.with_name(target.name + "-wal")
            target.write_bytes(content)
        self.device_store.directory.mkdir(parents=True, exist_ok=True)
        (self.device_store.directory / "private-fixture.txt").write_bytes(b"PRIVATE DEVICE")
        for method in ("GET", "HEAD"):
            for path in ("/cache/workflow-private/", "/cache/workflow-private/workflow.sqlite3", "/cache/workflow-private/workflow-model-credentials.json",
                         "/cache/workflow-private/workflow.sqlite3-wal", "/cache/workflow-private/jobs/job/execution.log",
                         "/cache/workflow-private/attachments/private.png", "/%63ache/workflow-private/workflow-model-credentials.json",
                         "/cache/./workflow-private/workflow-model-credentials.json", "/CACHE/WORKFLOW-PRIVATE/workflow-model-credentials.json",
                         "/cache/phone-private/private-fixture.txt"):
                status, response, _ = self.request(path, method)
                self.assertEqual(status, 404, (method, path))
                self.assertNotIn(b"PRIVATE", response if isinstance(response, bytes) else str(response).encode())

    def test_workflow_desktop_peer_host_origin_and_head_guards(self):
        for headers in ({"Host": "attacker.example"}, {"Origin": "http://attacker.example"}, {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.request("/api/workflow/config", headers=headers)[0], 403)
            self.assertEqual(self.request("/api/workflow/background", "POST", {"enabled": True}, headers)[0], 403)
        # A real HTTP connection still exercises the handler; only the peer
        # classification is made non-loopback to cover the desktop-only policy.
        with patch.object(self.desktop, "_client_address_is_loopback", return_value=False):
            self.assertEqual(self.request("/api/workflow/config")[0], 403)
            self.assertEqual(self.request("/api/workflow/config", "HEAD")[0], 403)
            self.assertEqual(self.request("/api/workflow/background", "POST", {"enabled": True})[0], 403)
        self.assertFalse(self.workflow.background_enabled)

    def test_all_windows_closed_background_enabled_keeps_server_and_worker(self):
        self.assertEqual(self.request("/api/workflow/background", "POST", {"enabled": True})[0], 200)
        self.session("open")
        self.assertEqual(self.session("close")["activeSessions"], 0)
        self.wait_window_callback()
        self.assertTrue(self.worker.is_alive())
        self.assertTrue(self.workflow.status()["workerAlive"])
        self.assertEqual(self.request("/api/workflow/config")[0], 200)
        # Opening a new UI remains possible after its earlier close was guarded.
        self.assertEqual(self.session("open", "reopened-window-456")["activeSessions"], 1)

    def test_all_windows_closed_phone_enabled_keeps_server_and_worker(self):
        original = phone.is_lan_address
        with patch.object(phone, "is_lan_address", lambda address: address == "127.0.0.1" or original(address)):
            with socket.socket() as holder:
                holder.bind(("127.0.0.1", 0))
                port = holder.getsockname()[1]
            self.companion.start("127.0.0.1", port)
            self.assertTrue(self.companion.enabled)
            self.assertFalse(self.workflow.background_enabled)
            self.session("open")
            self.session("close")
            self.wait_window_callback()
            self.assertTrue(self.worker.is_alive())
            self.assertTrue(self.workflow.status()["workerAlive"])
            self.assertEqual(self.request("/api/workflow/config")[0], 200)

    def test_all_windows_closed_without_background_phone_or_jobs_stops_owned_server(self):
        self.assertFalse(self.companion.enabled)
        self.assertFalse(self.workflow.background_enabled)
        self.assertFalse(self.workflow.has_pending_jobs())
        self.session("open")
        self.session("close")
        self.worker.join(timeout=2)
        self.assertFalse(self.worker.is_alive())

    def test_closed_window_pending_job_defers_shutdown_then_finished_callback_reclaims_server(self):
        self.assertFalse(self.companion.enabled)
        self.assertFalse(self.workflow.background_enabled)
        (self.assets / "fixture-result.png").write_bytes(tiny_png())
        self.session("open")
        status, record, _ = self.request("/api/workflow/create", "POST", {
            "requestId": str(uuid.uuid4()), "projectId": "console", "text": "Complete accepted work before closing"})
        self.assertEqual(status, 200, record)
        identifier = record["record"]["id"]
        entered, release = threading.Event(), threading.Event()
        original_run = self.workflow._run
        def delayed_run(row):
            entered.set()
            if not release.wait(timeout=4):
                raise AssertionError("Pending-job lifecycle fixture did not release its gate")
            return original_run(row)
        try:
            with patch.object(self.workflow, "_run", side_effect=delayed_run):
                status, submitted, _ = self.request("/api/workflow/submit", "POST", {
                    "requestId": str(uuid.uuid4()), "recordId": identifier, "action": "result_import",
                    "args": {"paths": ["fixture-result.png"]}, "text": "Import the real temporary fixture image"})
                self.assertEqual(status, 200, submitted)
                self.assertTrue(entered.wait(timeout=3))
                self.session("close")
                self.wait_window_callback()
                self.assertTrue(self.workflow.has_pending_jobs())
                self.assertTrue(self.worker.is_alive(), "Accepted pending work must keep the server alive")
                self.assertEqual(self.request("/api/workflow/config")[0], 200)
                release.set()
                self.worker.join(timeout=3)
                self.assertFalse(self.worker.is_alive(), "Finished work must reconsider a deferred idle shutdown")
            job = next(item for item in self.workflow.detail(identifier)["jobs"] if item["id"] == submitted["job"]["id"])
            self.assertEqual(job["status"], "succeeded", job)
            self.assertEqual(len(job["resultAttachmentIds"]), 1)
        finally:
            release.set()

    def test_desktop_revokes_command_while_worker_waits_before_process_start(self):
        marker = self.root / "revoked-command-ran.txt"
        script = self.root / "must-not-run.py"
        script.write_text(
            "import json,os\nfrom pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('executed',encoding='utf-8')\n"
            "Path(os.environ['CODEX_WORKFLOW_RESULT_MANIFEST']).write_text("
            "json.dumps({'text':'Revoked command executed.','files':[]}),encoding='utf-8')\n", encoding="utf-8")
        status, configured, _ = self.request("/api/workflow/projects", "POST", {"project": {
            "id": "console", "name": "Revocation fixture", "root": str(self.assets),
            "capabilities": ["command"], "allowGeneratedScripts": False,
            "commands": [{"id": "fixture-command", "argv": [sys.executable, "-B", str(script)], "timeout": 3}]}})
        self.assertEqual(status, 200, configured)
        status, record, _ = self.request("/api/workflow/create", "POST", {
            "requestId": str(uuid.uuid4()), "projectId": "console", "text": "Fixture for revocation"})
        self.assertEqual(status, 200, record)
        identifier = record["record"]["id"]
        entered, release = threading.Event(), threading.Event()
        def before_process(*args):
            entered.set()
            if not release.wait(timeout=4):
                raise AssertionError("Revocation fixture did not release its gate")
            return True
        self.workflow.callbacks["before_execute"] = before_process
        try:
            status, submitted, _ = self.request("/api/workflow/submit", "POST", {
                "requestId": str(uuid.uuid4()), "recordId": identifier, "action": "command",
                "commandId": "fixture-command", "text": "Only run while the command remains authorized"})
            self.assertEqual(status, 200, submitted)
            self.assertTrue(entered.wait(timeout=3), "Worker did not reach the pre-process gate")
            status, revoked, _ = self.request("/api/workflow/projects", "POST", {"project": {
                "id": "console", "capabilities": [], "commands": [], "allowGeneratedScripts": False}})
            self.assertEqual(status, 200, revoked)
            release.set()
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                status, detail, _ = self.request("/api/workflow/record?id=" + identifier)
                self.assertEqual(status, 200, detail)
                job = next(item for item in detail["jobs"] if item["id"] == submitted["job"]["id"])
                if job["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.02)
            self.assertEqual(job["status"], "failed", job)
            self.assertTrue(job["error"])
            self.assertFalse(marker.exists(), "A revoked command must never start")
            self.assertEqual(job["result"], {})
        finally:
            release.set()

    def test_root_real_capture_callback_and_resource_guard_are_registered_without_capture(self):
        self.assertIs(type(self).original_capture, self.desktop.capture_workflow_screen)
        self.assertIs(type(self).original_memory_guard, self.desktop.allow_workflow_execution)
        self.assertTrue(callable(type(self).original_capture))
        self.assertIs(self.companion.workflow_service, self.workflow)
        self.assertEqual(self.models.image_root, self.workflow.attachments_dir)

    def test_configured_model_key_env_is_not_inherited_or_saved_in_script_logs(self):
        env_name, secret = "CONSOLE_WORKFLOW_TEST_API_KEY", "synthetic-secret-never-save-in-workflow-log"
        script = self.root / "environment-probe.py"
        script.write_text(
            "import json,os\nfrom pathlib import Path\n"
            f"print('model-key-env='+os.environ.get({env_name!r},'NOT_INHERITED'))\n"
            "Path(os.environ['CODEX_WORKFLOW_RESULT_MANIFEST']).write_text("
            "json.dumps({'text':'Isolated environment probe executed.','files':[]}),encoding='utf-8')\n", encoding="utf-8")
        with patch.dict(os.environ, {env_name: secret}):
            status, configured, _ = self.request("/api/workflow/models", "POST", {
                "id": "fixture", "endpoint": "http://127.0.0.1:1/v1", "protocol": "responses",
                "model": "fixture-do-not-contact", "keyEnv": env_name})
            self.assertEqual(status, 200, configured)
            self.assertTrue(configured["models"]["ready"])
            self.assertNotIn(secret, json.dumps(configured))
            status, configured, _ = self.request("/api/workflow/projects", "POST", {"project": {
                "id": "console", "capabilities": ["command"], "commands": [
                    {"id": "env-probe", "argv": [sys.executable, "-B", str(script)], "timeout": 3}]}})
            self.assertEqual(status, 200, configured)
            status, record, _ = self.request("/api/workflow/create", "POST", {
                "requestId": str(uuid.uuid4()), "projectId": "console", "text": "Synthetic environment isolation check"})
            self.assertEqual(status, 200, record)
            identifier = record["record"]["id"]
            status, submitted, _ = self.request("/api/workflow/submit", "POST", {
                "requestId": str(uuid.uuid4()), "recordId": identifier, "action": "command",
                "commandId": "env-probe", "text": "Run only the isolated environment fixture"})
            self.assertEqual(status, 200, submitted)
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                status, detail, _ = self.request("/api/workflow/record?id=" + identifier)
                self.assertEqual(status, 200, detail)
                job = next(item for item in detail["jobs"] if item["id"] == submitted["job"]["id"])
                if job["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.02)
            self.assertEqual(job["status"], "succeeded", job)
            self.assertIn("NOT_INHERITED", job["log"])
            self.assertNotIn(secret, json.dumps(detail), "API key must never return through record logs")
            self.assertNotIn(secret.encode(), (self.private / "workflow.sqlite3").read_bytes(), "API key must never be saved in the job database")
            self.assertNotIn(secret.encode(), (self.workflow.jobs_dir / job["id"] / "execution.log").read_bytes())

    @unittest.skipUnless(os.name == "nt", "Synthetic stored-key redaction requires Windows DPAPI")
    def test_environment_and_log_helpers_preserve_unrelated_values_and_redact_known_dpapi_key(self):
        reference = "CONSOLE_WORKFLOW_TEST_API_KEY"
        env_key, dpapi_key = "synthetic-explicit-env-key", "synthetic-explicit-stored-key"
        with patch.dict(os.environ, {reference: env_key}):
            status, result, _ = self.request("/api/workflow/models", "POST", {
                "id": "fixture", "endpoint": "http://127.0.0.1:1/v1", "model": "fixture-no-call",
                "keyEnv": reference, "key": dpapi_key})
            self.assertEqual(status, 200, result)
            original = {reference: env_key, "cOnSoLe_WoRkFlOw_TeSt_ApI_kEy": env_key,
                        "CODEX_CONTROL_DATA_DIR": str(self.private), "CODEX_CONTROL_PUBLISHER_STATE_FILE": "synthetic-private-path",
                        "UNRELATED_TEST_VALUE": "keep-this-unrelated-value", "PATH": "keep-fixture-path"}
            filtered = self.models.execution_environment(original)
            self.assertNotIn(reference, filtered)
            self.assertNotIn("cOnSoLe_WoRkFlOw_TeSt_ApI_kEy", filtered)
            self.assertNotIn("CODEX_CONTROL_DATA_DIR", filtered)
            self.assertNotIn("CODEX_CONTROL_PUBLISHER_STATE_FILE", filtered)
            self.assertEqual(filtered["UNRELATED_TEST_VALUE"], original["UNRELATED_TEST_VALUE"])
            self.assertEqual(filtered["PATH"], original["PATH"])
            self.assertEqual(original[reference], env_key, "The caller's environment must not be mutated")
            redacted = self.models.redact_execution_log(f"env={env_key}, stored={dpapi_key}, unrelated=keep-this-unrelated-value")
            self.assertNotIn(env_key, redacted)
            self.assertNotIn(dpapi_key, redacted)
            self.assertIn("keep-this-unrelated-value", redacted)
            # A key cleared while its script is running must still be redacted.
            self.models.configure({"id": "fixture", "endpoint": "http://127.0.0.1:1/v1", "model": "fixture-no-call", "clearKey": True})
            self.assertNotIn(dpapi_key, self.models.redact_execution_log(dpapi_key))


if __name__ == "__main__":
    unittest.main(verbosity=2)
