"""Exercise the isolated phone gateway against a disposable document library."""
import copy
import http.client
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from document_library import DocumentLibraryService
from workflow_service import WorkflowError
from workflow_http import workflow_post
import phone_companion as phone


class PhoneCompanionChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-phone-check-")
        self.base = Path(self.temp.name)
        self.library = self.base / "library"
        self.library.mkdir()
        (self.library / "reports").mkdir()
        (self.library / "guide.md").write_text("# 阅读重点\nOne important point.\n", encoding="utf-8")
        (self.library / "private-secret.txt").write_text("NOT REGISTERED", encoding="utf-8")
        (self.library / "reports" / "one.md").write_text("# Report\nReadable.\n", encoding="utf-8")
        (self.library / "reference.md").write_text("# Reference\nRegistered.\n", encoding="utf-8")
        (self.library / ".document-guide.json").write_text(json.dumps({"version": 1, "items": [
            {"path": "guide.md", "title": "Guide", "summary": "Short", "highlights": ["Point"]}]}), encoding="utf-8")
        (self.library / ".document-references.json").write_text(json.dumps({"version": 1, "items": [
            {"id": "test-ref", "module": "blender", "defaultLanguage": "en", "variants": [
                {"language": "en", "label": "English", "title": "Reference", "summary": "", "path": "reference.md"}]}]}), encoding="utf-8")
        self.documents = DocumentLibraryService(self.base / "documents.json")
        self.documents.select(str(self.library))
        self.documents.register_report("report-one", "reports/one.md", "One report", "Summary", "Test")
        self.assets = self.base / "assets"
        self.assets.mkdir()
        (self.assets / "mobile.html").write_text("<!doctype html><title>Phone</title>", encoding="utf-8")
        (self.assets / "mobile.js").write_text("'use strict';", encoding="utf-8")
        (self.assets / "world_console.py").write_text("PRIVATE IMPLEMENTATION", encoding="utf-8")
        self.now = [100.0]
        self.music_dir = self.base / "music"
        self.music_dir.mkdir()
        self.audio_bytes = bytes(range(256)) * 600
        (self.music_dir / "song one.mp3").write_bytes(self.audio_bytes)
        (self.music_dir / "not-listed.mp3").write_bytes(b"PRIVATE AUDIO")
        (self.music_dir / "song one.en.lrc").write_text("[00:01.00]Local lyrics only\n", encoding="utf-8", newline="\n")
        self.music_tracks = [{"name": "Song One", "path": "song one.mp3", "size": len(self.audio_bytes),
            "modified": "today", "lyrics": True, "lyricsLanguage": "en", "lyricsLanguages": [
                {"code": "en", "label": "English", "lyricsUrl": "PRIVATE DESKTOP API"}],
            "url": "PRIVATE DESKTOP URL", "directory": "PRIVATE DIRECTORY", "cookies": "PRIVATE COOKIE"}]
        self.music_calls = []
        def music_getter():
            self.music_calls.append(self.now[0])
            return {"tracks": self.music_tracks, "directory": "PRIVATE DIRECTORY", "cookies": "PRIVATE COOKIE"}
        self.plan = {"plan": {"version": 1, "revision": "test-1", "groups": [
            {"id": f"group-{index}", "title": f"Task {index}", "summary": "", "items": []}
            for index in range(4)]}, "error": ""}
        self.service = phone.PhoneCompanionService(self.documents, lambda: copy.deepcopy(self.plan),
            self.assets, "1.0.test", device_getter=lambda: {"root": "PRIVATE ROOT", "applications": ["PRIVATE PROCESS"],
                "currentMemory": {"status": "available", "readAt": "now", "totalBytes": 16000,
                                  "availableBytes": 5000, "usedPercent": 69}, "model": "Test PC", "sampledAt": "yesterday"},
            clock=lambda: self.now[0], interface_getter=lambda: [{"address": "127.0.0.1", "name": "Disposable test transport"}],
            music_getter=music_getter, music_file_getter=lambda path: self.music_dir / path,
            music_lyrics_getter=lambda path, language: self.music_dir / "song one.en.lrc")
        # A test-local listener uses loopback without changing production policy.
        # Exact RFC1918 policy is tested separately using the original function.
        self.original_policy = phone.is_lan_address
        self.policy_patch = patch.object(phone, "is_lan_address", lambda value: value == "127.0.0.1" or self.original_policy(value))
        self.policy_patch.start()
        with socket.socket() as holder:
            holder.bind(("127.0.0.1", 0))
            self.port = holder.getsockname()[1]
        self.service.start("127.0.0.1", self.port)
        self.host = f"127.0.0.1:{self.port}"
        self.origin = "http://" + self.host
        self.cookie = ""

    def tearDown(self):
        self.service.stop()
        self.policy_patch.stop()
        self.temp.cleanup()

    def request(self, path, method="GET", body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        merged = {"Host": self.host}
        if self.cookie:
            merged["Cookie"] = self.cookie
        if method == "POST":
            merged.update({"Origin": self.origin, "X-Codex-Phone": "1", "Content-Type": "application/json"})
        merged.update(headers or {})
        encoded = json.dumps(body or {}).encode("utf-8") if method == "POST" else None
        try:
            connection.request(method, path, body=encoded, headers=merged)
            response = connection.getresponse()
            raw = response.read()
            response_headers = dict(response.getheaders())
            try:
                value = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeError):
                value = raw
            return response.status, value, response_headers
        finally:
            connection.close()

    def pair(self):
        code = self.service.state(False)["pairingCode"]
        status, data, headers = self.request("/api/phone/pair", "POST", {"code": code})
        self.assertEqual(status, 200, data)
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        return code, headers

    def sync_request(self, path, method="GET", body=None, token=None, headers=None):
        merged = {"Origin": phone.PLAN_SYNC_ORIGIN, "X-Codex-Phone": "1", "Sec-Fetch-Site": "cross-site"}
        if token is not None:
            merged["Authorization"] = "Bearer " + token
        merged.update(headers or {})
        return self.request(phone.PLAN_SYNC_PREFIX + path, method, body, merged)

    def sync_pair(self):
        code = self.service.state(False)["pairingCode"]
        status, data, headers = self.sync_request("pair", "POST", {"code": code})
        self.assertEqual(status, 200, data)
        self.assertEqual(data["computerId"], self.service.computer_id)
        self.assertEqual(data["expiresIn"], phone.SESSION_TTL)
        self.assertNotIn("Set-Cookie", headers)
        self.assertEqual(headers["Access-Control-Allow-Origin"], phone.PLAN_SYNC_ORIGIN)
        self.assertNotIn(str(self.library), json.dumps(data))
        return data["token"], code

    def test_rfc1918_policy_and_interface_selection(self):
        for address in ("10.1.2.3", "172.16.0.2", "172.31.255.2", "192.168.1.13"):
            self.assertTrue(self.original_policy(address), address)
        for address in ("127.0.0.1", "0.0.0.0", "169.254.1.2", "172.32.0.2", "8.8.8.8", "::1", "bad"):
            self.assertFalse(self.original_policy(address), address)
        self.service.stop()
        with self.assertRaises(ValueError):
            self.service.start("8.8.8.8", self.port)
        with self.assertRaises(ValueError):
            self.service.start("192.168.99.99", self.port)
        self.assertFalse(self.service.enabled)

    def test_unauthenticated_shell_only_no_private_api_or_source(self):
        self.assertEqual(self.request("/")[0], 200)
        self.assertEqual(self.request("/api/phone/status")[1], {"paired": False})
        for path in ("/api/phone/dashboard", "/api/phone/document?path=guide.md", "/world_console.py", "/api/console/state", "/api/documents/read?path=guide.md"):
            status, data, headers = self.request(path)
            self.assertEqual(status, 401, (path, data))
            self.assertNotIn("NOT REGISTERED", str(data))
        self.assertEqual(self.service.state(False)["pairedCount"], 0)

    def test_task_chat_work_routes_require_the_live_paired_session(self):
        calls = []

        class WorkflowProbe:
            def task_record(self, body, *, prefix, authorize):
                authorize()
                calls.append(("task-record", body, prefix))
                return {"record": {"id": "isolated-task-record"}}

            def app_work(self, body, *, prefix, authorize):
                authorize()
                calls.append(("app-work", body, prefix))
                return {"job": {"id": "isolated-work-job", "status": "queued"}}

            def end_app_work(self, body, *, prefix, authorize):
                authorize()
                calls.append(("app-work/end", body, prefix))
                return {"job": {"id": "isolated-work-job", "status": "failed"}}

        self.service.workflow_service = WorkflowProbe()
        for action in ("task-record", "app-work", "app-work/end"):
            self.assertEqual(self.request("/api/phone/workflow/" + action, "POST", {"requestId": "test-only"})[0], 401)
        self.assertEqual(calls, [])
        self.pair()
        for action in ("task-record", "app-work", "app-work/end"):
            body = {"requestId": "isolated-" + action, "recordId": "isolated-task-record"}
            status, result, _ = self.request("/api/phone/workflow/" + action, "POST", body)
            self.assertEqual(status, 200, result)
            self.assertEqual(calls[-1], (action, body, "/api/phone/workflow"))
        self.assertEqual(len(calls), 3)
        self.now[0] += phone.SESSION_TTL + 1
        self.assertEqual(self.request("/api/phone/workflow/app-work", "POST", {"requestId": "expired"})[0], 401)
        self.assertEqual(len(calls), 3)

    def test_phone_cannot_configure_work_authorization_or_workspace_catalog(self):
        self.service.workflow_service = object()
        self.pair()
        for action in ("app-work/bindings", "app-work/workspaces", "workspaces", "work-bindings"):
            status, result, _ = self.request("/api/phone/workflow/" + action, "POST", {"bindings": []})
            self.assertEqual(status, 404, (action, result))

    def test_explicit_work_rejection_marker_does_not_turn_unknown_failure_into_no_queue(self):
        class WorkflowProbe:
            def app_work(self, body, *, prefix, authorize):
                authorize()
                error = WorkflowError("Work source changed" if body["case"] == "rejected" else "Unavailable", 409)
                if body["case"] == "rejected":
                    error.code, error.queueAccepted = "revision_conflict", False
                raise error

        self.service.workflow_service = WorkflowProbe()
        self.pair()
        status, result, _ = self.request("/api/phone/workflow/app-work", "POST", {"case": "rejected"})
        self.assertEqual(status, 409)
        self.assertEqual(result["code"], "revision_conflict")
        self.assertIs(result["queueAccepted"], False)
        status, result, _ = self.request("/api/phone/workflow/app-work", "POST", {"case": "unknown"})
        self.assertEqual(status, 409)
        self.assertNotIn("queueAccepted", result)

    def test_temporary_pairing_status_keeps_actual_version_without_device_trust(self):
        self.pair()
        status, result, _ = self.request("/api/phone/status")
        self.assertEqual(status, 200)
        self.assertIs(result["paired"], True)
        self.assertEqual(result["version"], self.service.version)
        self.assertNotIn("remembered", result)
        self.assertNotIn("connectionUrl", result)

    def test_new_work_ui_cannot_silently_downgrade_on_an_older_component(self):
        class OlderWorkflow:
            def create(self, body, *, prefix, authorize):
                return {"record": {"id": "legacy-record"}}

        service = OlderWorkflow()
        self.assertEqual(workflow_post(service, "create", {})["record"]["id"], "legacy-record")
        for action in ("task-record", "app-work", "app-work/end"):
            with self.assertRaises(WorkflowError) as outcome:
                workflow_post(service, action, {})
            self.assertEqual(outcome.exception.status, 503)

    def test_only_desktop_route_can_configure_explicit_work_binding(self):
        calls = []
        authorization = lambda: "isolated-local-authority"

        class WorkflowProbe:
            def configure_app_work(self, body, *, authorize):
                calls.append((body, authorize))
                return {"appWork": {"bindings": []}}

        service, body = WorkflowProbe(), {"requestId": "isolated-configure", "bindings": []}
        with self.assertRaises(WorkflowError) as outcome:
            workflow_post(service, "app-work/bindings", body, desktop=False, authorize=authorization)
        self.assertEqual(outcome.exception.status, 404)
        self.assertEqual(calls, [])
        self.assertEqual(workflow_post(service, "app-work/bindings", body, desktop=True, authorize=authorization),
                         {"appWork": {"bindings": []}})
        self.assertEqual(calls, [(body, authorization)])

    def test_phone_icons_use_exact_public_assets_without_opening_phone_directory(self):
        source_root = Path(__file__).resolve().parents[1]
        folder = self.assets / "phone"
        folder.mkdir()
        originals = {}
        for size in (180, 192, 512):
            name = "phone-icon-" + str(size) + ".png"
            originals[name] = (source_root / "phone" / name).read_bytes()
            (folder / name).write_bytes(originals[name])
        (folder / "app.js").write_text("NOT REGISTERED PHONE SOURCE", encoding="utf-8")
        (folder / "private.png").write_bytes(b"NOT REGISTERED PHONE IMAGE")
        self.assertEqual({key: value for key, value in phone.ASSETS.items() if key.startswith("/phone/")},
                         {"/phone/" + name: "phone/" + name for name in originals})
        for name, original in originals.items():
            status, payload, headers = self.request("/phone/" + name + "?v=phone-white-72")
            self.assertEqual(status, 200)
            self.assertEqual(payload, original)
            self.assertEqual(headers["Content-Type"], "image/png")
            status, payload, headers = self.request("/phone/" + name, "HEAD")
            self.assertEqual(status, 200)
            self.assertEqual(payload, b"")
            self.assertEqual(int(headers["Content-Length"]), len(original))
        self.pair()
        for path in ("/phone/", "/phone/app.js", "/phone/private.png", "/phone/../mobile.html", "/phone/%2e%2e/mobile.html"):
            status, payload, _ = self.request(path)
            self.assertEqual(status, 404, path)
            self.assertNotIn("NOT REGISTERED", str(payload))

    def test_host_origin_and_cross_site_guards_apply_before_pairing(self):
        self.assertEqual(self.request("/", headers={"Host": "attacker.test"})[0], 403)
        self.assertEqual(self.request("/", headers={"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.request("/api/phone/status", headers={"Origin": "http://attacker.test"})[0], 403)
        code = self.service.state(False)["pairingCode"]
        self.assertEqual(self.request("/api/phone/pair", "POST", {"code": code}, headers={"Origin": ""})[0], 403)
        self.assertEqual(self.request("/api/phone/pair", "POST", {"code": code}, headers={"Origin": "null"})[0], 403)
        self.assertEqual(self.request("/api/phone/pair", "POST", {"code": code}, headers={"Origin": "http://attacker.test"})[0], 403)
        self.assertEqual(self.request("/api/phone/pair", "POST", {"code": code}, headers={"X-Codex-Phone": ""})[0], 403)
        self.assertEqual(self.service.state(False)["pairingCode"], code)

    def test_pairing_single_use_cookie_expiry_and_peer_binding(self):
        code, headers = self.pair()
        self.assertEqual(headers["Referrer-Policy"], "same-origin")
        cookie = headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertNotIn("Secure", cookie)  # Explicit HTTP LAN transport.
        self.assertEqual(self.request("/api/phone/status")[1], {"paired": True, "version": self.service.version})
        self.assertEqual(self.request("/api/phone/pair", "POST", {"code": code})[0], 401)
        token = self.cookie.split("=", 1)[1]
        self.assertFalse(self.service.is_paired(token, "192.168.1.55"))
        self.now[0] += phone.SESSION_TTL + 1
        self.assertEqual(self.request("/api/phone/status")[1], {"paired": False})
        self.assertEqual(self.request("/api/phone/dashboard")[0], 401)

    def test_expired_code_rate_limit_and_global_failure_lock(self):
        code = self.service.state(False)["pairingCode"]
        self.now[0] += phone.PAIR_TTL + 1
        self.assertEqual(self.request("/api/phone/pair", "POST", {"code": code})[0], 401)
        self.service.renew_pairing()
        for _ in range(4):
            self.assertEqual(self.request("/api/phone/pair", "POST", {"code": "invalid"})[0], 401)
        self.assertEqual(self.request("/api/phone/pair", "POST", {"code": self.service.state(False)["pairingCode"]})[0], 429)
        self.now[0] += 61
        self.service.renew_pairing()
        for index in range(8):
            with self.assertRaises(phone.PhoneRequestError) as outcome:
                self.service.pair("invalid", f"192.168.1.{index+40}")
            self.assertEqual(outcome.exception.status, 401)
        self.assertEqual(self.service.state(False)["pairingCode"], "")

    def test_dashboard_only_curated_device_seed_and_documents(self):
        self.pair()
        status, data, headers = self.request("/api/phone/dashboard")
        self.assertEqual(status, 200, data)
        self.assertEqual(data["device"]["model"], "Test PC")
        self.assertEqual(len(data["plan"]["plan"]["groups"]), 4)
        self.assertIn("暂未同步", data["plan"]["label"])
        self.assertEqual(data["documents"]["guide"]["items"][0]["path"], "guide.md")
        self.assertEqual(data["documents"]["inbox"]["inboxCount"], 1)
        serialized = json.dumps(data)
        self.assertNotIn("PRIVATE ROOT", serialized)
        self.assertNotIn("PRIVATE PROCESS", serialized)
        self.assertNotIn(str(self.library), serialized)
        self.assertNotIn("applications", data["device"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_registered_reads_only_no_traversal_arbitrary_query_or_assets(self):
        self.pair()
        for path in ("guide.md", "reports/one.md", "reference.md"):
            status, data, _ = self.request("/api/phone/document?path=" + path)
            self.assertEqual(status, 200, data)
            self.assertEqual(data["path"], path)
            self.assertNotIn("root", data)
        for path in ("private-secret.txt", "../outside.txt", "..%2foutside.txt", "D:%5csecret.txt", "%2fworld_console.py"):
            self.assertEqual(self.request("/api/phone/document?path=" + path)[0], 403, path)
        self.assertEqual(self.request("/api/phone/document?path=guide.md&path=reference.md")[0], 400)
        self.assertEqual(self.request("/api/phone/document?path=guide.md&expectedRoot=D:%5canything")[0], 400)
        for path in ("/world_console.py", "/../world_console.py", "/api/documents/read", "/api/console/update/install"):
            self.assertEqual(self.request(path)[0], 404, path)

    def test_only_existing_report_read_later_mutations_preserve_files(self):
        self.pair()
        original = (self.library / "reports/one.md").read_bytes()
        for status in ("later", "archive", "inbox"):
            response, data, _ = self.request("/api/phone/inbox/move", "POST", {"id": "report-one", "status": status})
            self.assertEqual(response, 200, data)
            self.assertEqual(data["item"]["status"], status)
            self.assertNotIn("root", data)
        self.assertEqual((self.library / "reports/one.md").read_bytes(), original)
        self.assertEqual(self.request("/api/phone/inbox/move", "POST", {"id": "unknown", "status": "archive"})[0], 403)
        self.assertEqual(self.request("/api/phone/inbox/move", "POST", {"id": "report-one", "status": "cleared"})[0], 400)
        self.assertEqual(self.request("/api/phone/inbox/archive/clear", "POST")[0], 404)
        self.assertEqual(self.request("/api/console/update/install", "POST")[0], 404)

    def test_library_switch_revokes_session_and_expected_root_read_race(self):
        self.pair()
        token = self.cookie.split("=", 1)[1]
        session = self.service.session(token, "127.0.0.1")
        alternate = self.base / "alternate"
        alternate.mkdir()
        (alternate / "guide.md").write_text("PRIVATE NEW ROOT", encoding="utf-8")
        original_read = self.documents.read
        def switching_read(path, expectedRoot=None):
            self.documents.select(str(alternate))
            return original_read(path, expectedRoot=expectedRoot)
        with patch.object(self.documents, "read", side_effect=switching_read):
            with self.assertRaises(ValueError):
                self.service.document(session, "guide.md")
        self.assertEqual(self.request("/api/phone/status")[1], {"paired": False})
        self.assertEqual(self.request("/api/phone/dashboard")[0], 401)

    def test_logout_and_disable_clear_sessions_listener_and_pairing_code(self):
        self.pair()
        self.assertEqual(self.request("/api/phone/logout", "POST")[1], {"paired": False})
        self.assertEqual(self.request("/api/phone/status")[1], {"paired": False})
        self.service.renew_pairing()
        self.pair()
        self.service.stop()
        state = self.service.state(False)
        self.assertFalse(state["enabled"])
        self.assertEqual(state["pairingCode"], "")
        self.assertEqual(state["pairedCount"], 0)
        self.assertEqual(state["url"], "")
        with socket.socket() as connection:
            self.assertNotEqual(connection.connect_ex(("127.0.0.1", self.port)), 0)

    def test_body_size_and_content_type_are_bounded(self):
        code = self.service.state(False)["pairingCode"]
        self.assertEqual(self.request("/api/phone/pair", "POST", {"code": code}, headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("/api/phone/pair", "POST", {"code": "a" * 5000})[0], 413)
        self.assertEqual(self.service.state(False)["pairedCount"], 0)

    def test_interface_inventory_cached_but_start_revalidates(self):
        calls = []
        def interfaces():
            calls.append(self.now[0])
            return [{"address": "127.0.0.1", "name": "Disposable test transport"}]
        self.service._interface_getter = interfaces
        self.service._interface_cache = None
        self.service.state()
        self.service.state()
        self.assertEqual(len(calls), 1)
        self.now[0] += 61
        self.service.state()
        self.assertEqual(len(calls), 2)
        self.service.start("127.0.0.1", self.port)
        self.assertEqual(len(calls), 3)

    def test_dashboard_validates_root_before_any_device_getter(self):
        self.pair()
        session = self.service.session(self.cookie.split("=", 1)[1], "127.0.0.1")
        alternate = self.base / "alternate-device"
        alternate.mkdir()
        self.documents.select(str(alternate))
        with patch.object(self.service, "device_getter") as getter:
            with self.assertRaises(ValueError):
                self.service.dashboard(session)
            getter.assert_not_called()

    def test_same_origin_plan_is_lightweight_current_content_and_metadata_only(self):
        self.assertEqual(self.request("/api/phone/plan")[0], 401)
        self.pair()
        self.plan["updatedAt"] = "2026-10-01T01:02:03+00:00"
        self.plan["sourcePath"] = "PRIVATE LOCAL FILE"
        self.plan["plan"]["groups"][0]["items"] = [{"id": "item-1", "text": "Current task", "done": False}]
        with patch.object(self.service, "device_getter") as device, patch.object(self.service, "_catalog") as catalog, \
             patch.object(self.service, "music_getter") as music:
            status, first, headers = self.request("/api/phone/plan")
            self.assertEqual(status, 200, first)
            for getter in (device, catalog, music):
                getter.assert_not_called()
        self.assertEqual(first["format"], "codex-console-plan-snapshot")
        self.assertEqual(first["schemaVersion"], 1)
        self.assertEqual(first["updatedAt"], self.plan["updatedAt"])
        self.assertRegex(first["hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(first["computerId"], self.service.computer_id)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertNotIn("PRIVATE LOCAL FILE", json.dumps(first))
        self.assertEqual(self.request("/api/phone/plan")[1]["hash"], first["hash"])
        self.plan["plan"]["groups"][0]["items"][0]["done"] = True
        second = self.request("/api/phone/plan")[1]
        self.assertNotEqual(first["hash"], second["hash"])
        self.assertTrue(second["plan"]["groups"][0]["items"][0]["done"])
        self.plan["plan"]["groups"] += [{"id": f"group-{index}", "title": f"Task {index}", "summary": "", "items": []}
                                         for index in (4, 5)]
        self.assertEqual(len(self.request("/api/phone/plan")[1]["plan"]["groups"]), 6)
        self.assertEqual(self.request("/api/phone/plan?root=anything")[0], 400)

    def test_plan_validation_and_root_guard_keep_getters_and_errors_private(self):
        self.pair()
        token = self.cookie.split("=", 1)[1]
        session = self.service.session(token, "127.0.0.1")
        for payload in ({"plan": None, "error": "PRIVATE PATH"}, {"plan": {}, "error": ""}, None):
            with patch.object(self.service, "plan_getter", return_value=payload):
                status, result, _ = self.request("/api/phone/plan")
                self.assertEqual(status, 503)
                self.assertNotIn("plan", result)
                self.assertNotIn("PRIVATE", json.dumps(result))
        with patch.object(self.service, "plan_getter", return_value={**self.plan, "actualDone": False}):
            status, result, _ = self.request("/api/phone/plan")
            self.assertEqual(status, 503)
            self.assertIn("完成保存", result["error"])
            self.assertNotIn("plan", result)
        alternate = self.base / "alternate-plan"
        alternate.mkdir()
        self.documents.select(str(alternate))
        with patch.object(self.service, "plan_getter") as getter:
            self.assertEqual(self.request("/api/phone/plan")[0], 401)
            with self.assertRaises(phone.PhoneRequestError):
                self.service.plan_snapshot(session)
            getter.assert_not_called()

    def test_plan_sync_preflight_only_exact_published_origin_and_routes(self):
        requested = {"Access-Control-Request-Method": "GET",
                     "Access-Control-Request-Headers": "authorization, x-codex-phone",
                     "Access-Control-Request-Private-Network": "true"}
        status, data, headers = self.sync_request("plan", "OPTIONS", headers=requested)
        self.assertEqual(status, 204)
        self.assertEqual(data, b"")
        self.assertEqual(headers["Access-Control-Allow-Origin"], phone.PLAN_SYNC_ORIGIN)
        self.assertEqual(headers["Access-Control-Allow-Private-Network"], "true")
        self.assertNotIn("Access-Control-Allow-Credentials", headers)
        self.assertNotIn("*", headers["Access-Control-Allow-Headers"])
        for origin in ("https://evil.test", "http://tx74666.github.io", "https://tx74666.github.io.evil.test", "null", ""):
            status, _, headers = self.sync_request("plan", "OPTIONS", headers={**requested, "Origin": origin})
            self.assertEqual(status, 403, origin)
            self.assertNotIn("Access-Control-Allow-Origin", headers)
        for method in ("POST", "DELETE", "HEAD"):
            self.assertEqual(self.sync_request("plan", "OPTIONS", headers={**requested, "Access-Control-Request-Method": method})[0], 403)
        for names in ("authorization", "x-codex-phone, cookie", "x-codex-phone, x-other"):
            self.assertEqual(self.sync_request("plan", "OPTIONS", headers={**requested, "Access-Control-Request-Headers": names})[0], 403)
        self.assertEqual(self.sync_request("document", "OPTIONS", headers=requested)[0], 404)
        self.assertEqual(self.request("/api/phone/document", "OPTIONS", headers={"Origin": phone.PLAN_SYNC_ORIGIN, **requested})[0], 404)

    def test_plan_sync_pair_requires_origin_header_code_and_separate_scope(self):
        code = self.service.state(False)["pairingCode"]
        self.assertEqual(self.sync_request("plan")[0], 401)
        for headers in ({"Origin": "https://evil.test"}, {"X-Codex-Phone": ""}, {"Host": "evil.test"}):
            self.assertEqual(self.sync_request("pair", "POST", {"code": code}, headers=headers)[0], 403)
        self.assertEqual(self.service.state(False)["pairingCode"], code)
        self.assertEqual(self.sync_request("pair", "POST", {"code": code, "extra": True})[0], 400)
        token, code = self.sync_pair()
        self.assertEqual(self.sync_request("pair", "POST", {"code": code})[0], 401)
        status, snapshot, headers = self.sync_request("plan", token=token)
        self.assertEqual(status, 200, snapshot)
        self.assertEqual(snapshot["computerId"], self.service.computer_id)
        self.assertEqual(headers["Access-Control-Allow-Origin"], phone.PLAN_SYNC_ORIGIN)
        self.assertFalse(self.service.is_paired(token, "127.0.0.1"))
        with self.assertRaises(phone.PhoneRequestError):
            self.service.session(token, "192.168.1.55", scope="plan-sync")
        # A plan-only bearer cannot become a general mobile cookie, even locally.
        self.cookie = phone.COOKIE_NAME + "=" + token
        for path in ("/api/phone/dashboard", "/api/phone/document?path=guide.md", "/api/phone/music"):
            self.assertEqual(self.request(path)[0], 401, path)
            self.assertEqual(self.request(path, headers={"Origin": phone.PLAN_SYNC_ORIGIN, "X-Codex-Phone": "1", "Authorization": "Bearer " + token})[0], 403, path)
        for path in ("document", "music", "inbox/move", "plan"):
            self.assertEqual(self.sync_request(path, "POST", token=token)[0], 404, path)
        self.service.renew_pairing()
        self.cookie = ""
        self.pair()
        old_token = self.cookie.split("=", 1)[1]
        self.assertEqual(self.sync_request("plan", token=old_token)[0], 401)

    def test_plan_sync_expiry_logout_stop_and_revocation_during_getter(self):
        token, _ = self.sync_pair()
        self.assertEqual(self.sync_request("logout", "POST", {"unexpected": True}, token)[0], 400)
        self.assertEqual(self.sync_request("logout", "POST", {}, token)[1], {"paired": False})
        self.assertEqual(self.sync_request("plan", token=token)[0], 401)
        self.service.renew_pairing()
        token, _ = self.sync_pair()
        original_getter = self.service.plan_getter
        def revoking_getter():
            self.service.logout(token)
            return original_getter()
        with patch.object(self.service, "plan_getter", side_effect=revoking_getter):
            self.assertEqual(self.sync_request("plan", token=token)[0], 401)
        self.service.renew_pairing()
        token, _ = self.sync_pair()
        self.now[0] += phone.SESSION_TTL + 1
        self.assertEqual(self.sync_request("plan", token=token)[0], 401)
        self.service.renew_pairing()
        token, _ = self.sync_pair()
        self.service.stop()
        self.assertFalse(self.service._sessions)
        with self.assertRaises(phone.PhoneRequestError):
            self.service.session(token, "127.0.0.1", scope="plan-sync")

    def test_music_catalog_sanitized_relative_paths_and_cache(self):
        self.pair()
        self.music_tracks += [{"name": "Bad", "path": "../private.mp3"},
                              {"name": "Bad", "path": "D:\\private.mp3"}]
        status, data, headers = self.request("/api/phone/music")
        self.assertEqual(status, 200, data)
        self.assertEqual(len(data["tracks"]), 1)
        self.assertEqual(data["playback"], "phone")
        self.assertEqual(data["tracks"][0]["url"], "/api/phone/music/audio?path=song+one.mp3")
        for private in ("PRIVATE DESKTOP", "PRIVATE DIRECTORY", "PRIVATE COOKIE"):
            self.assertNotIn(private, json.dumps(data))
        count = len(self.music_calls)
        self.assertEqual(self.request("/api/phone/music/audio?path=song+one.mp3", headers={"Range": "bytes=0-1"})[0], 206)
        self.assertEqual(self.request("/api/phone/music/audio?path=song+one.mp3", headers={"Range": "bytes=2-3"})[0], 206)
        self.assertEqual(len(self.music_calls), count)

    def test_music_audio_head_and_safari_ranges_exact_bytes(self):
        self.pair()
        path = "/api/phone/music/audio?path=song+one.mp3"
        status, raw, headers = self.request(path, "HEAD")
        self.assertEqual(status, 200)
        self.assertEqual(raw, b"")
        self.assertEqual(headers["Content-Length"], str(len(self.audio_bytes)))
        self.assertEqual(headers["Content-Type"], "audio/mpeg")
        self.assertEqual(headers["Accept-Ranges"], "bytes")
        self.assertEqual(headers["Cache-Control"], "private, no-store")
        cases = [("bytes=0-1", self.audio_bytes[:2], "bytes 0-1"),
                 ("bytes=128-255", self.audio_bytes[128:256], "bytes 128-255"),
                 ("bytes=-12", self.audio_bytes[-12:], f"bytes {len(self.audio_bytes)-12}-{len(self.audio_bytes)-1}"),
                 (f"bytes={len(self.audio_bytes)-10}-", self.audio_bytes[-10:], f"bytes {len(self.audio_bytes)-10}-{len(self.audio_bytes)-1}")]
        for requested, expected, content_range in cases:
            status, raw, headers = self.request(path, headers={"Range": requested})
            self.assertEqual(status, 206, requested)
            self.assertEqual(raw, expected, requested)
            self.assertEqual(headers["Content-Range"], content_range + "/" + str(len(self.audio_bytes)))
        status, raw, headers = self.request(path)
        self.assertEqual(status, 200)
        self.assertEqual(raw, self.audio_bytes)

    def test_music_invalid_ranges_return_416_not_full_audio(self):
        self.pair()
        path = "/api/phone/music/audio?path=song+one.mp3"
        for requested in ("bytes=10-5", "bytes=-0", "bytes=", "bytes=0-1,2-3", "bytes=99999999-", "items=0-1", "bytes=" + "9" * 200 + "-"):
            status, data, headers = self.request(path, headers={"Range": requested})
            self.assertEqual(status, 416, requested)
            self.assertEqual(headers["Content-Range"], f"bytes */{len(self.audio_bytes)}")
            self.assertNotEqual(data, self.audio_bytes)
        status, data, headers = self.request(path, "HEAD", headers={"Range": "bytes=99999999-"})
        self.assertEqual(status, 416)
        self.assertEqual(data, b"")

    def test_music_auth_and_arbitrary_path_boundary_on_get_head_lyrics(self):
        for method in ("GET", "HEAD"):
            for path in ("/api/phone/music", "/api/phone/music/audio?path=song+one.mp3", "/api/phone/music/lyrics?path=song+one.mp3"):
                self.assertEqual(self.request(path, method)[0], 401, (path, method))
        self.pair()
        for path in ("not-listed.mp3", "..%2fnot-listed.mp3", "D:%5cprivate.mp3", "%2fprivate.mp3"):
            self.assertEqual(self.request("/api/phone/music/audio?path=" + path)[0], 403, path)
            self.assertEqual(self.request("/api/phone/music/audio?path=" + path, "HEAD")[0], 403, path)
            self.assertEqual(self.request("/api/phone/music/lyrics?path=" + path)[0], 403, path)
        self.assertEqual(self.request("/api/phone/music/audio?path=song+one.mp3&path=not-listed.mp3")[0], 400)
        self.assertEqual(self.request("/api/phone/music/audio?path=song+one.mp3", headers={"Origin": "https://evil.test"})[0], 403)
        for endpoint in ("/api/music/delete", "/api/music/import-url", "/api/phone/music/delete"):
            self.assertEqual(self.request(endpoint, "POST")[0], 404)
        self.assertEqual(self.request("/api/phone/logout", "POST")[0], 200)
        self.assertEqual(self.request("/api/phone/music/audio?path=song+one.mp3", "HEAD")[0], 401)

    def test_music_lyrics_local_utf8_size_limit_and_language(self):
        self.pair()
        path = "/api/phone/music/lyrics?path=song+one.mp3&language=en"
        status, data, headers = self.request(path)
        self.assertEqual(status, 200, data)
        self.assertEqual(data["content"], "[00:01.00]Local lyrics only\n")
        self.assertEqual(data["format"], "lrc")
        self.assertEqual(data["language"], "en")
        self.assertNotIn(str(self.music_dir), json.dumps(data))
        self.assertEqual(self.request(path + "%2foutside")[0], 400)
        (self.music_dir / "song one.en.lrc").write_bytes(b"a" * (phone.MAX_LYRICS_BYTES + 1))
        self.assertEqual(self.request(path)[0], 413)
        (self.music_dir / "song one.en.lrc").write_bytes(b"\xff\xfeNOT UTF8")
        self.assertEqual(self.request(path)[0], 400)
        with patch.object(self.service, "music_lyrics_getter", return_value=None):
            status, data, _ = self.request(path)
            self.assertEqual(status, 404)
            self.assertIn("本地歌词", data["error"])
        with patch.object(self.service, "music_file_getter", side_effect=ValueError("PRIVATE PATH")):
            status, data, _ = self.request("/api/phone/music/audio?path=song+one.mp3")
            self.assertEqual(status, 404)
            self.assertNotIn("PRIVATE PATH", data["error"])

    def test_music_audio_stream_stops_after_pair_revocation(self):
        self.pair()
        token = self.cookie.split("=", 1)[1]
        original = self.service.is_paired
        calls = []
        def revoke_after_chunk(candidate, peer):
            calls.append(True)
            if len(calls) > 1:
                self.service.logout(token)
            return original(candidate, peer)
        with patch.object(self.service, "is_paired", side_effect=revoke_after_chunk):
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
            try:
                connection.request("GET", "/api/phone/music/audio?path=song+one.mp3", headers={"Host": self.host, "Cookie": self.cookie})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                with self.assertRaises(http.client.IncompleteRead) as truncated:
                    response.read()
                self.assertEqual(truncated.exception.partial, self.audio_bytes[:phone.AUDIO_CHUNK_BYTES])
            finally:
                connection.close()
        self.assertFalse(self.service.is_paired(token, "127.0.0.1"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
