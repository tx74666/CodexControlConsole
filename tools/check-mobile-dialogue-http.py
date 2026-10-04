#!/usr/bin/env python3
"""Real paired-phone routes against disposable data; no App or model is used.

The desktop dispatch method is compiled from its source without importing the
production bootstrap. All listeners, images, sessions and databases are fixtures.
"""
import ast
import http.client
import io
import json
from email.message import Message
from http.cookies import SimpleCookie
from pathlib import Path
import socket
import sqlite3
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.parse
import uuid
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from document_library import DocumentLibraryService
import phone_companion as phone
from transfer_store import MAX_REQUEST_BYTES, TransferError, read_transfer_request
from workflow_http import workflow_post, workflow_upload_dialogue
from workflow_models import WorkflowModelError
from workflow_service import WorkflowError, WorkflowService

PREFIX = "/api/phone/workflow/"


def request(**values):
    return {"requestId": str(uuid.uuid4()), **values}


def tiny_png():
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0\xff\0\0\0\xff\0")) + chunk(b"IEND", b""))


def multipart(fields, files):
    boundary = "console-mobile-route-" + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                       + value + "\r\n").encode("utf-8"))
    for name, mime, data in files:
        chunks.extend([(f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\n'
                        f'Content-Type: {mime}\r\n\r\n').encode("utf-8"), data, b"\r\n"])
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(chunks), "multipart/form-data; boundary=" + boundary


class MobileDialogueHttpChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="console-mobile-http-")
        self.root = Path(self.temporary.name)
        self.service = WorkflowService(self.root / "private", computer_id="isolated-mobile-http",
            projects=[{"id": "fixture", "name": "Isolated fixture", "root": str(self.root), "capabilities": ["result_import"]}],
            recover_jobs=False)
        self.documents = DocumentLibraryService(self.root / "documents.json")
        self.companion = phone.PhoneCompanionService(self.documents, lambda: {"plan": {"groups": []}},
            self.root, "1.0.fixture", workflow_service=self.service, computer_id="isolated-mobile-http",
            interface_getter=lambda: [{"address": "127.0.0.1", "name": "Fixture loopback"}])
        original = phone.is_lan_address
        self.policy = patch.object(phone, "is_lan_address", lambda value: value == "127.0.0.1" or original(value))
        self.policy.start()
        with socket.socket() as holder:
            holder.bind(("127.0.0.1", 0))
            self.port = holder.getsockname()[1]
        self.companion.start("127.0.0.1", self.port)
        self.host, self.cookie = f"127.0.0.1:{self.port}", ""
        self.origin = "http://" + self.host
        self.client_id = uuid.uuid4().hex
        self.png = tiny_png()

    def tearDown(self):
        self.companion.stop()
        self.service.shutdown()
        self.policy.stop()
        self.temporary.cleanup()

    def call(self, path, body=None, *, raw=None, headers=None, cookie=None):
        values = {"Host": self.host, "Origin": self.origin, "X-Codex-Phone": "1", "Content-Type": "application/json"}
        active_cookie = self.cookie if cookie is None else cookie
        if active_cookie:
            values["Cookie"] = active_cookie
        values.update(headers or {})
        values = {name: value for name, value in values.items() if value is not None}
        payload = raw if raw is not None else json.dumps(body or {}, ensure_ascii=False).encode("utf-8")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=4)
        try:
            connection.request("POST", path, payload, values)
            response = connection.getresponse()
            return response.status, json.loads(response.read()), dict(response.getheaders())
        finally:
            connection.close()

    def pair(self):
        status, data, headers = self.call("/api/phone/pair", {"code": self.companion.state(False)["pairingCode"]})
        self.assertEqual(status, 200, data)
        parsed = SimpleCookie()
        parsed.load(headers["Set-Cookie"])
        self.cookie = "; ".join(f"{name}={entry.value}" for name, entry in parsed.items())

    def open(self):
        status, data, _ = self.call(PREFIX + "mobile/dialogue/open", request(clientId=self.client_id))
        self.assertEqual(status, 200, data)
        return data["session"]

    def fields(self, session, **extra):
        return {"requestId": str(uuid.uuid4()), "recordId": session["recordId"], "text": json.dumps({
            "clientId": self.client_id, "sessionId": session["id"], "expectedRevision": session["revision"]}), **extra}

    def upload(self, fields, files=None, **options):
        payload, content_type = multipart(fields, files if files is not None else [("原图.png", "image/png", self.png)])
        headers = {"Content-Type": content_type, **options.pop("headers", {})}
        return self.call(PREFIX + "mobile/dialogue/upload", raw=payload, headers=headers, **options)

    def counts(self):
        with self.service._db() as db:
            return {name: db.execute("SELECT COUNT(*) FROM " + name).fetchone()[0]
                    for name in ("attachments", "messages", "jobs", "idea_dispatches")}

    def idea(self, text):
        return self.service.incubator_create(request(title=text, body=text, stage="thinking"))["idea"]

    def test_unpaired_and_wrong_origin_header_reject_before_reading_or_writing(self):
        before = self.counts()
        for action in ("mobile/dialogue/upload", "mobile/idea/split", "mobile/idea/merge"):
            self.assertEqual(self.call(PREFIX + action)[0], 401)
        self.pair()
        for action in ("mobile/dialogue/upload", "mobile/idea/split", "mobile/idea/merge"):
            for headers in ({"Origin": None}, {"Origin": "https://other.invalid"}, {"X-Codex-Phone": None}, {"X-Codex-Phone": "0"}, {"Sec-Fetch-Site": "cross-site"}):
                status, _, response_headers = self.call(PREFIX + action, headers=headers)
                self.assertEqual(status, 403, (action, headers))
                self.assertNotIn("Access-Control-Allow-Origin", response_headers)
        self.assertEqual(self.counts(), before)

    def test_upload_is_session_scoped_deduplicated_and_does_not_send(self):
        self.pair()
        session = self.open()
        fields, before = self.fields(session), self.counts()
        status, first, headers = self.upload(fields)
        self.assertEqual(status, 200, first)
        self.assertEqual(first["session"]["id"], session["id"])
        self.assertGreater(first["session"]["revision"], session["revision"])
        self.assertEqual(first["session"]["draft"]["attachmentIds"], [])
        self.assertEqual(len(first["uploadedAttachmentIds"]), 1)
        self.assertTrue(first["detail"]["attachments"][0]["url"].startswith(PREFIX + "attachment?"))
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        status, duplicate, _ = self.upload(fields)
        self.assertEqual(status, 200, duplicate)
        self.assertEqual(duplicate["uploadedAttachmentIds"], first["uploadedAttachmentIds"])
        self.assertEqual(self.counts(), {**before, "attachments": before["attachments"] + 1})

    def test_expired_pairing_is_rechecked_after_multipart_before_any_write(self):
        self.pair()
        session, before = self.open(), self.counts()
        original, checked = self.companion.session, []
        def expires_during_upload(*args, **kwargs):
            checked.append(True)
            if len(checked) >= 2:
                raise phone.PhoneRequestError("Fixture pairing expired during upload", 401)
            return original(*args, **kwargs)
        with patch.object(self.companion, "session", expires_during_upload):
            self.assertEqual(self.upload(self.fields(session))[0], 401)
        self.assertEqual(len(checked), 2)
        self.assertEqual(self.counts(), before)

    def test_upload_stale_revision_cleared_session_and_unknown_fields_do_not_write(self):
        self.pair()
        session = self.open()
        self.assertEqual(self.upload(self.fields(session))[0], 200)
        before = self.counts()
        status, rejected, _ = self.upload(self.fields(session))
        self.assertEqual((status, rejected["code"]), (409, "revision_conflict"))
        current = self.service.mobile_dialogue_get("clientId=" + self.client_id)["session"]
        status, cleared, _ = self.call(PREFIX + "mobile/dialogue/clear", request(clientId=self.client_id,
            sessionId=current["id"], expectedRevision=current["revision"]))
        self.assertEqual(status, 200, cleared)
        status, rejected, _ = self.upload(self.fields(current))
        self.assertEqual((status, rejected["code"]), (409, "dialogue_changed"))
        self.assertEqual(self.upload(self.fields(cleared["session"], unsupported="no"))[0], 400)
        self.assertEqual(self.counts(), before)

    def test_multipart_and_json_keep_existing_request_bounds(self):
        self.pair()
        session = self.open()
        before = self.counts()
        self.assertEqual(self.upload(self.fields(session), headers={"Content-Length": str(MAX_REQUEST_BYTES + 1)})[0], 413)
        self.assertEqual(self.upload(self.fields(session), files=[(f"{i}.png", "image/png", self.png) for i in range(5)])[0], 413)
        self.assertEqual(self.call(PREFIX + "mobile/dialogue/upload", self.fields(session))[0], 415)
        for action in ("mobile/idea/split", "mobile/idea/merge"):
            self.assertEqual(self.call(PREFIX + action, {"oversized": "a" * (128 * 1024)})[0], 413)
            self.assertEqual(self.call(PREFIX + action + "?unexpected=1")[0], 400)
        self.assertEqual(self.counts(), before)

    def test_split_merge_preserve_sources_deduplication_and_reject_stale_versions(self):
        self.pair()
        first, second = self.idea("裙子物理与手动"), self.idea("手机想法")
        before = self.counts()
        split = request(id=first["id"], expectedRevision=first["revision"], start=0, end=2, title="分出的想法")
        status, created, _ = self.call(PREFIX + "mobile/idea/split", split)
        self.assertEqual(status, 200, created)
        self.assertEqual(created["idea"]["body"], first["body"][:2])
        self.assertEqual(self.call(PREFIX + "mobile/idea/split", split)[1]["idea"]["id"], created["idea"]["id"])
        rejected = {**split, "requestId": str(uuid.uuid4()), "expectedRevision": first["revision"] + 1}
        self.assertEqual(self.call(PREFIX + "mobile/idea/split", rejected)[0], 409)
        merge = request(firstId=first["id"], firstRevision=first["revision"], secondId=second["id"],
                        secondRevision=second["revision"], title="合并后的想法")
        status, combined, _ = self.call(PREFIX + "mobile/idea/merge", merge)
        self.assertEqual(status, 200, combined)
        self.assertEqual(combined["idea"]["body"], first["body"] + "\n\n" + second["body"])
        self.assertEqual(self.call(PREFIX + "mobile/idea/merge", merge)[1]["idea"]["id"], combined["idea"]["id"])
        self.assertEqual(self.call(PREFIX + "mobile/idea/merge", {**merge, "requestId": str(uuid.uuid4()), "secondRevision": second["revision"] + 1})[0], 409)
        with self.service._db() as db:
            self.assertEqual(self.service._idea(db, first["id"])["body"], first["body"])
            self.assertEqual(self.service._idea(db, second["id"])["body"], second["body"])
        self.assertEqual(self.counts(), before)

    def test_desktop_source_dispatches_the_same_bounded_multipart_and_json_contracts(self):
        tree = ast.parse((ROOT / "world_console.py").read_text(encoding="utf-8"))
        handler = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "ConsoleHandler")
        method = next(item for item in handler.body if isinstance(item, ast.FunctionDef) and item.name == "_dispatch_POST")
        namespace = {"urllib": urllib, "sqlite3": sqlite3, "WorkflowError": WorkflowError,
            "WorkflowModelError": WorkflowModelError, "TransferError": TransferError, "RequestBodyError": WorkflowError,
            "WORKFLOW_SERVICE": self.service, "read_transfer_request": read_transfer_request,
            "workflow_post": workflow_post, "workflow_upload_dialogue": workflow_upload_dialogue}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "world_console.py", "exec"), namespace)
        class Handler:
            def require_trusted_post_context(self): return True
            def require_local_request(self): return True
            def send_json(self, value, status=200): self.result = (status, value)
            def read_json_body(self, max_bytes):
                assert max_bytes == 128 * 1024
                return self.body
        session = self.service.mobile_dialogue_open(request(clientId=self.client_id))["session"]
        raw, content_type = multipart(self.fields(session), [("original.png", "image/png", self.png)])
        target = Handler()
        target.path, target.rfile, target.headers = "/api/workflow/mobile/dialogue/upload", io.BytesIO(raw), Message()
        target.headers["Content-Type"], target.headers["Content-Length"] = content_type, str(len(raw))
        namespace["_dispatch_POST"](target)
        self.assertEqual(target.result[0], 200, target.result)
        self.assertTrue(target.result[1]["detail"]["attachments"][0]["url"].startswith("/api/workflow/attachment?"))
        for action in ("mobile/idea/split", "mobile/idea/merge"):
            target.path, target.body = "/api/workflow/" + action, {}
            namespace["_dispatch_POST"](target)
            self.assertEqual(target.result[0], 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
