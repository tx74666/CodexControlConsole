"""Exercise real phone workflow HTTP against disposable local data only.

No production listener, document library, model credential, or remote AI is used.
The one executed command is a generated fixture script inside TemporaryDirectory.
"""
import base64
import http.client
import io
import json
from pathlib import Path
from http.cookies import SimpleCookie
import socket
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid
import wave
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from document_library import DocumentLibraryService
from phone_device_store import PhoneDeviceStore
import phone_companion as phone
from workflow_models import WorkflowModels
from workflow_service import WorkflowService


PREFIX = "/api/phone/workflow/"


def request_id():
    return str(uuid.uuid4())


def tiny_png():
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0\xff\0\0\0\xff\0")) + chunk(b"IEND", b""))


def tiny_wav():
    output = io.BytesIO()
    with wave.open(output, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(8000)
        recording.writeframes(b"\0\0" * 80)
    return output.getvalue()


def multipart(fields, files):
    boundary = "console-workflow-check-" + uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                      + value + "\r\n").encode("utf-8"))
    for name, mime, data in files:
        parts.extend([(f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\n'
                       f'Content-Type: {mime}\r\n\r\n').encode("utf-8"), data, b"\r\n"])
    parts.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


class WorkflowHttpChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-workflow-http-check-")
        self.base = Path(self.temp.name)
        self.library = self.base / "library"
        self.library.mkdir()
        (self.library / "guide.md").write_text("# Temporary fixture\n", encoding="utf-8")
        self.documents = DocumentLibraryService(self.base / "documents.json")
        self.documents.select(str(self.library))
        self.assets = self.base / "assets"
        self.assets.mkdir()
        (self.assets / "mobile.html").write_text("<!doctype html><title>Isolated check</title>", encoding="utf-8")
        self.project = self.base / "fixture-project"
        self.project.mkdir()
        self.marker = self.project / "executions.txt"
        self.png, self.wav = tiny_png(), tiny_wav()
        self.script = self.project / "make-result.py"
        self.script.write_text(
            "import base64,json,os\nfrom pathlib import Path\n"
            "output=Path(os.environ['CONSOLE_WORKFLOW_OUTPUT_DIR'])\n"
            f"(output/'result.png').write_bytes(base64.b64decode({base64.b64encode(self.png).decode('ascii')!r}))\n"
            f"with Path({str(self.marker)!r}).open('a',encoding='utf-8') as target: target.write('executed\\n')\n"
            "Path(os.environ['CONSOLE_WORKFLOW_RESULT_MANIFEST']).write_text("
            "json.dumps({'text':'Fixture script really executed.','files':['result.png']}),encoding='utf-8')\n"
            "print('isolated-script-result')\n", encoding="utf-8")
        self.models = WorkflowModels(self.base / "private" / "models", image_root=self.base / "private" / "attachments")
        self.workflow = WorkflowService(self.base / "private", models=self.models,
            computer_id="isolated-test-computer", computer_name="Isolated test computer",
            projects=[{"id": "fixture", "name": "Temporary fixture", "root": str(self.project),
                       "capabilities": ["command", "result_import"], "allowGeneratedScripts": False,
                       "commands": [{"id": "make-result", "name": "Make fixture result", "argv": [sys.executable, "-B", str(self.script)], "timeout": 5}]}])
        self.device_store = PhoneDeviceStore(self.base / "devices")
        self.companion = phone.PhoneCompanionService(self.documents,
            lambda: {"plan": {"version": 1, "revision": "fixture", "groups": [
                {"id": "fixture-group", "title": "Isolated fixture", "summary": "", "items": [
                    {"id": "fixture-task", "text": "Verify token scope", "done": False}]}]},
                "actualDone": True, "error": ""},
            self.assets, "1.0.test", computer_id="isolated-test-computer",
            interface_getter=lambda: [{"address": "127.0.0.1", "name": "Disposable test transport", "fingerprint": "a" * 64}],
            workflow_service=self.workflow, device_store=self.device_store)
        # Only this isolated Python process treats loopback as test-local LAN.
        # The existing check-phone-companion.py verifies the original RFC1918 policy.
        policy = phone.is_lan_address
        self.policy_patch = patch.object(phone, "is_lan_address", lambda address: address == "127.0.0.1" or policy(address))
        self.policy_patch.start()
        with socket.socket() as holder:
            holder.bind(("127.0.0.1", 0))
            self.port = holder.getsockname()[1]
        self.host, self.origin = f"127.0.0.1:{self.port}", f"http://127.0.0.1:{self.port}"
        self.cookie = ""
        self.companion.start("127.0.0.1", self.port)
        self.workflow.start()

    def tearDown(self):
        self.companion.stop()
        self.workflow.shutdown()
        self.policy_patch.stop()
        self.temp.cleanup()

    def request(self, path, method="GET", body=None, headers=None, *, raw=None, cookie=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        merged = {"Host": self.host}
        current_cookie = self.cookie if cookie is None else cookie
        if current_cookie:
            merged["Cookie"] = current_cookie
        if method == "POST":
            merged.update({"Origin": self.origin, "X-Codex-Phone": "1", "Content-Type": "application/json"})
        merged.update(headers or {})
        encoded = raw if raw is not None else json.dumps(body or {}).encode("utf-8") if method == "POST" else None
        try:
            connection.request(method, path, body=encoded, headers=merged)
            response = connection.getresponse()
            content = response.read()
            response_headers = response.getheaders()
            try:
                value = json.loads(content.decode("utf-8"))
            except (ValueError, UnicodeError):
                value = content
            return response.status, value, response_headers
        finally:
            connection.close()

    def pair(self, remember=False):
        code = self.companion.state(False)["pairingCode"]
        status, data, headers = self.request("/api/phone/pair", "POST", {"code": code, "remember": remember})
        self.assertEqual(status, 200, data)
        cookies = SimpleCookie()
        for name, value in headers:
            if name.lower() == "set-cookie":
                cookies.load(value)
        self.cookie = "; ".join(f"{name}={item.value}" for name, item in cookies.items() if item.value)
        self.assertTrue(self.cookie)
        return data

    def create(self, text="Review the fixture image."):
        status, data, _ = self.request(PREFIX + "create", "POST", {"requestId": request_id(), "projectId": "fixture", "text": text})
        self.assertEqual(status, 200, data)
        return data

    def upload(self, record_id, files=None, identifier=None, extra_fields=None):
        fields = {"requestId": identifier or request_id(), "recordId": record_id, **(extra_fields or {})}
        raw, content_type = multipart(fields, files or [("截图.png", "image/png", self.png)])
        return self.request(PREFIX + "upload", "POST", raw=raw, headers={"Content-Type": content_type})

    def detail(self, identifier):
        status, data, _ = self.request(PREFIX + "record?id=" + identifier)
        self.assertEqual(status, 200, data)
        return data

    def wait_job(self, record_id, job_id):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            detail = self.detail(record_id)
            job = next(item for item in detail["jobs"] if item["id"] == job_id)
            if job["status"] not in {"queued", "running"}:
                return job, detail
            time.sleep(0.04)
        self.fail("Isolated workflow job did not finish within 8 seconds")

    def test_unpaired_private_routes_and_head_are_unauthorized(self):
        for action in ("config", "records", "record?id=" + "a" * 32, "attachment?id=" + "a" * 32):
            self.assertEqual(self.request(PREFIX + action)[0], 401, action)
        self.assertEqual(self.request(PREFIX + "attachment?id=" + "a" * 32, "HEAD")[0], 401)
        for action in ("create", "message", "submit", "discuss", "transcribe", "retry", "upload", "models", "projects", "background"):
            self.assertEqual(self.request(PREFIX + action, "POST")[0], 401, action)
        self.assertEqual(self.workflow.list()["records"], [])

    def test_paired_create_message_records_and_exact_request_deduplication(self):
        self.pair()
        body = {"requestId": request_id(), "projectId": "fixture", "title": "HTTP fixture", "text": "First exact message"}
        status, first, _ = self.request(PREFIX + "create", "POST", body)
        self.assertEqual(status, 200, first)
        status, second, _ = self.request(PREFIX + "create", "POST", body)
        self.assertEqual(status, 200, second)
        identifier = first["record"]["id"]
        self.assertEqual(second["record"]["id"], identifier)
        self.assertEqual(len(second["messages"]), 1)
        self.assertEqual(self.request(PREFIX + "create", "POST", {**body, "text": "different"})[0], 409)
        message = {"requestId": request_id(), "recordId": identifier, "text": "Second exact message"}
        for _ in range(2):
            self.assertEqual(self.request(PREFIX + "message", "POST", message)[0], 200)
        detail = self.detail(identifier)
        self.assertEqual([item["text"] for item in detail["messages"]], [body["text"], message["text"]])
        status, listing, _ = self.request(PREFIX + "records?limit=10")
        self.assertEqual(status, 200, listing)
        self.assertEqual([item["id"] for item in listing["records"]], [identifier])
        self.assertNotIn(str(self.base), json.dumps(listing))
        self.assertEqual(self.request(PREFIX + "record?id=" + identifier + "&id=" + identifier)[0], 400)
        self.assertEqual(self.request(PREFIX + "records?path=../private")[0], 400)

    def test_multipart_image_audio_registered_attachment_head_get_and_deduplication(self):
        self.pair()
        identifier = self.create()["record"]["id"]
        upload_id = request_id()
        files = [("截图.png", "image/png", self.png), ("recording.wav", "audio/wav", self.wav)]
        status, first, _ = self.upload(identifier, files, upload_id)
        self.assertEqual(status, 200, first)
        status, second, _ = self.upload(identifier, files, upload_id)
        self.assertEqual(status, 200, second)
        self.assertEqual(first["uploadedAttachmentIds"], second["uploadedAttachmentIds"])
        self.assertEqual(len(second["attachments"]), 2)
        self.assertEqual(len(second["messages"]), 2)
        self.assertNotIn(str(self.base), json.dumps(second))
        for attachment in second["attachments"]:
            expected = self.png if attachment["mimeType"] == "image/png" else self.wav
            self.assertTrue(attachment["url"].startswith(PREFIX + "attachment?"))
            status, content, headers = self.request(attachment["url"], "HEAD")
            self.assertEqual((status, content), (200, b""))
            headers = dict(headers)
            self.assertEqual(int(headers["Content-Length"]), len(expected))
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            self.assertIn("no-store", headers["Cache-Control"])
            self.assertIn("sandbox", headers["Content-Security-Policy"])
            self.assertEqual(self.request(attachment["url"])[1], expected)
            if attachment["previewUrl"]:
                preview = self.request(attachment["previewUrl"])
                self.assertEqual(preview[0], 200)
                self.assertTrue(preview[1].startswith(b"\xff\xd8"))
        self.assertEqual(self.request(PREFIX + "attachment?id=" + "a" * 32)[0], 404)
        self.assertEqual(self.request(PREFIX + "attachment?path=../workflow.sqlite3")[0], 400)
        self.assertEqual(self.upload(identifier, extra_fields={"path": "../private"})[0], 400)
        self.assertEqual(self.upload(identifier, [("bad.png", "image/png", b"not an image")])[0], 415)
        self.assertEqual(len(self.detail(identifier)["attachments"]), 2)

    def test_phone_cannot_change_desktop_settings_or_bypass_origin(self):
        self.pair()
        for action in ("models", "projects", "background"):
            self.assertEqual(self.request(PREFIX + action, "POST", {"enabled": True})[0], 404, action)
            self.assertEqual(self.request(PREFIX + action)[0], 404, action)
        for desktop_path in ("/api/workflow/models", "/api/workflow/projects", "/api/workflow/background"):
            self.assertEqual(self.request(desktop_path, "POST")[0], 404)
        status, config, _ = self.request(PREFIX + "config")
        self.assertEqual(status, 200, config)
        self.assertFalse(config["models"]["ready"])
        self.assertFalse(config["backgroundEnabled"])
        self.assertNotIn(str(self.project), json.dumps(config))
        body = {"requestId": request_id(), "projectId": "fixture", "text": "Origin should fail"}
        for headers in ({"Origin": "http://attacker.example"}, {"X-Codex-Phone": ""}, {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.request(PREFIX + "create", "POST", body, headers)[0], 403)
        self.assertEqual(self.workflow.list()["records"], [])

    def test_plan_sync_token_scope_cannot_read_or_submit_workflow(self):
        code = self.companion.state(False)["pairingCode"]
        sync_headers = {"Origin": phone.PLAN_SYNC_ORIGIN, "X-Codex-Phone": "1", "Sec-Fetch-Site": "cross-site"}
        status, data, _ = self.request(phone.PLAN_SYNC_PREFIX + "pair", "POST", {"code": code}, sync_headers)
        self.assertEqual(status, 200, data)
        token = data["token"]
        bearer = {**sync_headers, "Authorization": "Bearer " + token}
        status, snapshot, _ = self.request(phone.PLAN_SYNC_PREFIX + "plan", headers=bearer)
        self.assertEqual(status, 200, snapshot)
        self.assertEqual(snapshot["plan"]["groups"][0]["items"][0]["text"], "Verify token scope")
        token_cookie = phone.COOKIE_NAME + "=" + token
        self.assertEqual(self.request(PREFIX + "records", cookie=token_cookie)[0], 401)
        self.assertEqual(self.request(PREFIX + "create", "POST", cookie=token_cookie)[0], 401)
        self.assertEqual(self.request(PREFIX + "records", headers={"Authorization": "Bearer " + token}, cookie="")[0], 401)
        self.assertEqual(self.request(PREFIX + "records", headers=bearer)[0], 403)
        self.assertEqual(self.request(phone.PLAN_SYNC_PREFIX + "workflow/records", headers=bearer)[0], 404)
        self.assertEqual(self.workflow.list()["records"], [])

    def test_revoked_remembered_device_cannot_read_existing_record_or_attachment(self):
        paired = self.pair(remember=True)
        self.assertTrue(paired["remembered"])
        identifier = self.create()["record"]["id"]
        status, uploaded, _ = self.upload(identifier)
        self.assertEqual(status, 200, uploaded)
        url = uploaded["attachments"][0]["url"]
        self.assertEqual(self.request(url)[0], 200)
        self.companion.forget_devices({"id": paired["deviceId"]})
        for path, method in ((PREFIX + "records", "GET"), (PREFIX + "record?id=" + identifier, "GET"), (url, "GET"), (url, "HEAD"), (PREFIX + "create", "POST")):
            self.assertEqual(self.request(path, method)[0], 401, (path, method))
        self.assertEqual(len(self.workflow.detail(identifier)["attachments"]), 1)

    def test_revocation_during_create_rolls_back_before_durable_commit(self):
        self.pair()
        token = self.cookie.split("=", 1)[1]
        original_message = self.workflow._message
        def revoke_inside_transaction(*args, **kwargs):
            result = original_message(*args, **kwargs)
            self.companion.logout(token)
            return result
        with patch.object(self.workflow, "_message", side_effect=revoke_inside_transaction):
            status, response, _ = self.request(PREFIX + "create", "POST", {"requestId": request_id(), "projectId": "fixture", "text": "Do not commit revoked work"})
        self.assertEqual(status, 401, response)
        self.assertEqual(self.workflow.list()["records"], [])

    def test_missing_ai_jobs_wait_without_fabricated_messages_or_results(self):
        self.pair()
        identifier = self.create()["record"]["id"]
        status, uploaded, _ = self.upload(identifier, [("recording.wav", "audio/wav", self.wav)])
        self.assertEqual(status, 200, uploaded)
        audio_id = uploaded["uploadedAttachmentIds"][0]
        for action, extra in (("discuss", {}), ("transcribe", {"attachmentId": audio_id}), ("submit", {"action": "auto"})):
            body = {"requestId": request_id(), "recordId": identifier, "text": "Synthetic model request must wait", **extra}
            status, queued, _ = self.request(PREFIX + action, "POST", body)
            self.assertEqual(status, 200, queued)
            job, detail = self.wait_job(identifier, queued["job"]["id"])
            self.assertEqual(job["status"], "waiting", job)
            self.assertTrue(job["error"])
            self.assertEqual(job["result"], {})
            self.assertFalse(any(message["role"] in {"assistant", "transcript"} for message in detail["messages"]))
        self.assertFalse(self.marker.exists())

    def test_paired_authorized_command_really_executes_once_and_returns_result_image(self):
        self.pair()
        identifier = self.create()["record"]["id"]
        body = {"requestId": request_id(), "recordId": identifier, "computerId": "isolated-test-computer", "projectId": "fixture",
                "action": "command", "commandId": "make-result", "text": "Run the explicitly authorized fixture script"}
        status, submitted, _ = self.request(PREFIX + "submit", "POST", body)
        self.assertEqual(status, 200, submitted)
        status, duplicate, _ = self.request(PREFIX + "submit", "POST", body)
        self.assertEqual(status, 200, duplicate)
        self.assertEqual(submitted["job"]["id"], duplicate["job"]["id"])
        job, detail = self.wait_job(identifier, submitted["job"]["id"])
        self.assertEqual(job["status"], "succeeded", job)
        self.assertIn("isolated-script-result", job["log"])
        self.assertEqual(job["result"]["text"], "Fixture script really executed.")
        self.assertEqual(self.marker.read_text(encoding="utf-8"), "executed\n")
        self.assertEqual(len(detail["jobs"]), 1)
        self.assertEqual(len(job["resultAttachmentIds"]), 1)
        result = next(item for item in detail["attachments"] if item["id"] == job["resultAttachmentIds"][0])
        self.assertEqual(self.request(result["url"])[1], self.png)
        self.assertEqual(detail["record"]["primaryAttachmentId"], result["id"])
        self.assertTrue(any(item["role"] == "result" and item["attachmentIds"] == [result["id"]] for item in detail["messages"]))
        self.assertEqual(self.request(PREFIX + "submit", "POST", {**body, "text": "Different request content"})[0], 409)
        self.assertFalse(self.models.config()["ready"])

    def test_unapproved_action_command_computer_and_raw_script_cannot_execute(self):
        self.pair()
        identifier = self.create()["record"]["id"]
        baseline = {"recordId": identifier, "action": "command", "commandId": "make-result", "text": "An explicit fixture request"}
        for override, expected in (({"commandId": "not-approved"}, 403), ({"action": "generated_script"}, 403),
                                   ({"computerId": "different-computer"}, 403), ({"projectId": "not-approved"}, 403),
                                   ({"script": "print('not authorized')"}, 400), ({"argv": ["some executable"]}, 400)):
            status, data, _ = self.request(PREFIX + "submit", "POST", {**baseline, **override, "requestId": request_id()})
            self.assertEqual(status, expected, data)
        self.assertEqual(self.detail(identifier)["jobs"], [])
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
