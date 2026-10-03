"""Disposable integration checks for the authenticated text/image transfer inbox."""
import http.client
import io
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from document_library import DocumentLibraryService
import phone_companion as phone
import transfer_store as transfer


def image_bytes(format="PNG"):
    result = io.BytesIO()
    Image.new("RGB", (30, 18), "blue").save(result, format)
    return result.getvalue()


def multipart(text="", files=(), request_id=None, extra=()):
    boundary = "----ConsoleTransferCheck123456"
    result = bytearray()
    for name, value in [("requestId", request_id or str(uuid.uuid4())), ("text", text), *extra]:
        result.extend((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode("utf-8"))
    for name, data, mime in files:
        result.extend((f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\nContent-Type: {mime}\r\n\r\n').encode("utf-8"))
        result.extend(data)
        result.extend(b"\r\n")
    result.extend(f"--{boundary}--\r\n".encode())
    return bytes(result), "multipart/form-data; boundary=" + boundary


def box(kind, data):
    return struct.pack(">I", len(data) + 8) + kind + data


class TransferChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-transfer-check-")
        self.base = Path(self.temp.name)
        self.library = self.base / "library"
        self.library.mkdir()
        self.documents = DocumentLibraryService(self.base / "documents.json")
        self.documents.select(str(self.library))
        self.store = transfer.TransferStore(lambda: self.documents.state().get("root", ""), self.base / "fallback")
        self.service = phone.PhoneCompanionService(self.documents, lambda: {}, self.base, "test",
            interface_getter=lambda: [{"address": "127.0.0.1", "name": "Test transport"}], transfer_store=self.store)
        original_policy = phone.is_lan_address
        self.policy = patch.object(phone, "is_lan_address", lambda value: value == "127.0.0.1" or original_policy(value))
        self.policy.start()
        with socket.socket() as holder:
            holder.bind(("127.0.0.1", 0))
            self.port = holder.getsockname()[1]
        self.service.start("127.0.0.1", self.port)
        self.cookie = ""

    def tearDown(self):
        self.service.stop()
        self.policy.stop()
        self.temp.cleanup()

    def request(self, path, method="GET", body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        authority = f"127.0.0.1:{self.port}"
        merged = {"Host": authority}
        if self.cookie:
            merged["Cookie"] = self.cookie
        if method == "POST":
            merged.update({"Origin": "http://" + authority, "X-Codex-Phone": "1"})
        merged.update(headers or {})
        try:
            connection.request(method, path, body, merged)
            response = connection.getresponse()
            raw, result_headers = response.read(), dict(response.getheaders())
            try:
                value = json.loads(raw)
            except (ValueError, UnicodeError):
                value = raw
            return response.status, value, result_headers
        finally:
            connection.close()

    def pair(self):
        code = self.service.state(False)["pairingCode"]
        status, result, headers = self.request("/api/phone/pair", "POST", json.dumps({"code": code}), {"Content-Type": "application/json"})
        self.assertEqual(status, 200, result)
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]

    def send(self, text="", files=(), request_id=None, headers=None):
        body, content_type = multipart(text, files, request_id)
        return self.request("/api/phone/transfer/messages", "POST", body, {"Content-Type": content_type, **(headers or {})})

    def direct_send(self, text="", files=(), request_id=None, sender="desktop", authorize=None):
        from email.message import Message
        raw, content_type = multipart(text, files, request_id)
        headers = Message()
        headers["Content-Type"], headers["Content-Length"] = content_type, str(len(raw))
        with transfer.read_transfer_request(headers, io.BytesIO(raw)) as (fields, incoming):
            return self.store.send(fields, incoming, sender, authorize=authorize)

    def test_pair_required_same_origin_csrf_and_scope_boundaries(self):
        self.assertEqual(self.send("private text")[0], 401)
        self.assertEqual(self.request("/api/phone/transfer/messages")[0], 401)
        self.assertEqual(self.request("/api/phone/transfer/attachment?id=" + "a" * 32)[0], 401)
        self.pair()
        for headers in ({"Origin": "https://evil.test"}, {"X-Codex-Phone": ""}, {"Host": "evil.test"}, {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.send("blocked", headers=headers)[0], 403, headers)
        self.assertEqual(self.store.list()["messages"], [])
        self.service.renew_pairing()
        token = self.service.pair(self.service.state(False)["pairingCode"], "127.0.0.1", scope="plan-sync")
        self.cookie = phone.COOKIE_NAME + "=" + token
        self.assertEqual(self.send("plan scope cannot write")[0], 401)
        self.assertEqual(self.request("/api/phone/transfer/messages")[0], 401)
        self.assertEqual(self.request(phone.PLAN_SYNC_PREFIX + "transfer/messages", "GET", headers={
            "Origin": phone.PLAN_SYNC_ORIGIN, "X-Codex-Phone": "1", "Authorization": "Bearer " + token})[0], 404)

    def test_bidirectional_history_original_thumbnail_download_head_and_persistence(self):
        original = image_bytes()
        desktop = self.direct_send("电脑→手机", [("中文照片.png", original, "image/png")])["message"]
        self.assertEqual(desktop["attachments"][0]["name"], "中文照片.png")
        self.assertTrue(Path(desktop["attachments"][0]["path"]).is_file())
        self.assertEqual(Path(desktop["attachments"][0]["path"]).parent.resolve(),
                         (self.library / "互传").resolve())
        self.pair()
        status, data, _ = self.send("手机→电脑 <script>alert(1)</script>", [("验证图片.jpg", image_bytes("JPEG"), "image/jpeg")])
        self.assertEqual(status, 200, data)
        self.assertEqual(data["message"]["attachments"][0]["name"], "验证图片.jpg")
        self.assertEqual(data["message"]["sender"], "phone")
        self.assertNotIn("path", data["message"]["attachments"][0])
        status, listing, _ = self.request("/api/phone/transfer/messages?limit=1")
        self.assertEqual(status, 200)
        self.assertTrue(listing["hasMore"])
        status, second, _ = self.request("/api/phone/transfer/messages?before=" + listing["messages"][0]["id"])
        self.assertEqual(status, 200)
        attachment = second["messages"][0]["attachments"][0]
        self.assertNotIn(str(self.library), json.dumps(second))
        status, raw, headers = self.request(attachment["url"])
        self.assertEqual((status, raw), (200, original))
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        status, raw, headers = self.request(attachment["url"] + "&download=1", "HEAD")
        self.assertEqual((status, raw), (200, b""))
        self.assertTrue(headers["Content-Disposition"].startswith("attachment;"))
        status, preview, headers = self.request(attachment["previewUrl"])
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/jpeg")
        with Image.open(io.BytesIO(preview)) as image:
            self.assertEqual(image.format, "JPEG")
        restarted = transfer.TransferStore(lambda: str(self.library), self.base / "fallback")
        self.assertEqual(len(restarted.list()["messages"]), 2)
        unchanged = restarted.list("revision=" + restarted.list()["revision"])
        self.assertTrue(unchanged["unchanged"])
        self.assertNotIn("messages", unchanged)

    def test_idempotency_retry_conflict_sender_distinction_and_all_or_nothing(self):
        self.pair()
        request_id = str(uuid.uuid4())
        status, initial, _ = self.send("one", [("photo.png", image_bytes(), "image/png")], request_id)
        self.assertEqual(status, 200, initial)
        status, retry, _ = self.send("one", [("photo.png", image_bytes(), "image/png")], request_id)
        self.assertEqual(status, 200, retry)
        self.assertTrue(retry["duplicate"])
        self.assertEqual(initial["message"]["id"], retry["message"]["id"])
        self.assertEqual(self.send("changed", request_id=request_id)[0], 409)
        self.direct_send("desktop request ID separate", request_id=request_id)
        before = list((self.library / "互传").glob("*.png"))
        status, result, _ = self.send("invalid second image", [("valid.png", image_bytes(), "image/png"), ("bad.png", b"<html><script>bad</script>", "image/png")])
        self.assertEqual(status, 415, result)
        self.assertEqual(len(self.store.list()["messages"]), 2)
        self.assertEqual(list((self.library / "互传").glob("*.png")), before)
        self.assertEqual(list((self.library / "互传" / ".console-transfer").glob("*.pending")), [])

    def test_image_content_size_type_truncation_and_resource_caps(self):
        self.pair()
        cases = [("svg.svg", b"<svg></svg>", "image/svg+xml"),
                 ("mismatch.jpg", image_bytes(), "image/jpeg"),
                 ("bad.png", b"\x89PNG\r\n\x1a\nxxxx", "image/png"),
                 ("truncated.jpg", image_bytes("JPEG")[:-40], "image/jpeg"),
                 ("type.png", image_bytes(), "text/html")]
        for item in cases:
            self.assertEqual(self.send("", [item])[0], 415, item[0])
        self.assertEqual(self.send(" " * (transfer.MAX_TEXT_CHARS + 1))[0], 413)
        self.assertEqual(self.send()[0], 400)
        self.assertEqual(self.send("", [("photo.png", image_bytes(), "image/png")] * 5)[0], 413)
        self.assertEqual(self.store.list()["messages"], [])
        with patch.object(transfer, "MAX_PIXELS", 100):
            self.assertEqual(self.send("", [("photo.png", image_bytes(), "image/png")])[0], 413)
        for format, name, mime in [("GIF", "valid.gif", "image/gif"), ("WEBP", "valid.webp", "image/webp")]:
            self.assertEqual(self.send("", [(name, image_bytes(format), mime)])[0], 200)

    def test_heic_original_preserved_without_misleading_preview(self):
        # A tiny BMFF fixture exercises the preservation contract, not HEIC decoding.
        heic = box(b"ftyp", b"heic" + b"\0\0\0\0" + b"mif1heic") + box(b"meta", b"\0" * 4) + box(b"mdat", b"fixture")
        self.pair()
        status, result, _ = self.send("iPhone original", [("iphone.heic", heic, "image/heic")])
        self.assertEqual(status, 200, result)
        attachment = result["message"]["attachments"][0]
        self.assertFalse(attachment["previewable"])
        self.assertIsNone(attachment["previewUrl"])
        self.assertEqual(self.request(attachment["url"])[1], heic)
        self.assertEqual(self.request(attachment["url"] + "&preview=1")[0], 415)
        self.assertEqual(self.send("", [("fake.heic", heic[:-1], "image/heic")])[0], 415)

    def test_query_path_containment_library_switch_and_revocation(self):
        self.pair()
        status, result, _ = self.send("file", [("../../bad.png", image_bytes(), "image/png")])
        self.assertEqual(status, 200, result)
        attachment = result["message"]["attachments"][0]
        self.assertEqual(attachment["name"], "bad.png")
        for suffix in ("id=../outside", "id=" + "a" * 32 + "&id=" + "b" * 32, "path=C%3A%5Cprivate", "id=" + "a" * 32 + "&preview=9"):
            self.assertIn(self.request("/api/phone/transfer/attachment?" + suffix)[0], {400, 404})
        for query in ("limit=0", "limit=51", "limit=1&limit=2", "after=bad", "revision=" + "x" * 600):
            self.assertEqual(self.request("/api/phone/transfer/messages?" + query)[0], 400)
        token = self.cookie.split("=", 1)[1]
        self.service.logout(token)
        self.assertEqual(self.request(attachment["url"])[0], 401)
        self.service.renew_pairing()
        self.pair()
        other = self.base / "other"
        other.mkdir()
        self.documents.select(str(other))
        self.assertEqual(self.request("/api/phone/transfer/messages")[0], 401)
        self.assertEqual(self.store.list()["messages"], [])

    def test_revoke_during_save_leaves_no_message_or_attachments(self):
        calls = []
        def authorize():
            calls.append(True)
            if len(calls) == 3:
                raise phone.PhoneRequestError("revoked", 401)
        with self.assertRaises(phone.PhoneRequestError):
            self.direct_send("must roll back", [("one.png", image_bytes(), "image/png")], authorize=authorize)
        self.assertEqual(self.store.list()["messages"], [])
        self.assertEqual(list((self.library / "互传").glob("*.png")), [])
        self.assertEqual(list((self.library / "互传" / ".console-transfer").glob("*.preview.jpg")), [])

    def test_strict_utf8_and_extended_multipart_filenames(self):
        from urllib.parse import quote
        self.pair()
        raw, content_type = multipart("extended filename", [("placeholder.png", image_bytes(), "image/png")])
        header = b'filename="placeholder.png"'
        extended = ("filename*=UTF-8''" + quote("验证图片.png", safe="")).encode("ascii")
        valid = raw.replace(header, extended)
        status, result, _ = self.request("/api/phone/transfer/messages", "POST", valid, {"Content-Type": content_type})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["message"]["attachments"][0]["name"], "验证图片.png")
        for invalid in (b'filename="\xff.png"', b"filename*=UTF-8''%FF.png", b"filename*=unknown''image.png"):
            status, result, _ = self.request("/api/phone/transfer/messages", "POST", raw.replace(header, invalid), {"Content-Type": content_type})
            self.assertEqual(status, 400, (invalid, result))
        self.assertEqual(len(self.store.list()["messages"]), 1)

    def test_interrupted_duplicate_malformed_multipart_and_upload_slots(self):
        from email.message import Message
        raw, content_type = multipart("hello")
        headers = Message()
        headers["Content-Type"], headers["Content-Length"] = content_type, str(len(raw))
        with self.assertRaises(transfer.TransferError):
            with transfer.read_transfer_request(headers, io.BytesIO(raw[:-20])):
                pass
        duplicate, _ = multipart("hello", extra=[("text", "twice")])
        headers.replace_header("Content-Length", str(len(duplicate)))
        with self.assertRaises(transfer.TransferError):
            with transfer.read_transfer_request(headers, io.BytesIO(duplicate)):
                pass
        transfer.UPLOAD_SLOTS.acquire()
        transfer.UPLOAD_SLOTS.acquire()
        try:
            with self.assertRaises(transfer.TransferError) as error:
                with transfer.read_transfer_request(headers, io.BytesIO(duplicate)):
                    pass
            self.assertEqual(error.exception.status, 429)
        finally:
            transfer.UPLOAD_SLOTS.release()
            transfer.UPLOAD_SLOTS.release()

    def test_desktop_http_list_upload_attachment_head_local_open_and_auth(self):
        with patch.dict(os.environ, {"CODEX_CONTROL_DATA_DIR": str(self.base / "desktop-runtime"),
                "CODEX_CONTROL_PUBLISHER_STATE_FILE": str(self.base / "publisher.json")}):
            import world_console as desktop
        server = desktop.ConsoleHTTPServer(("127.0.0.1", 0), desktop.ConsoleHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        with patch.object(desktop, "TRANSFER_STORE", self.store):
            thread.start()
            port = server.server_address[1]
            authority = f"127.0.0.1:{port}"
            def request(path, method="GET", body=None, headers=None):
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                try:
                    connection.request(method, path, body, {"Host": authority, "Origin": "http://" + authority, **(headers or {})})
                    response = connection.getresponse()
                    raw = response.read()
                    try:
                        value = json.loads(raw)
                    except (ValueError, UnicodeError):
                        value = raw
                    return response.status, value, dict(response.getheaders())
                finally:
                    connection.close()
            try:
                body, content_type = multipart("desktop HTTP", [("验证图片.png", image_bytes(), "image/png")])
                status, result, _ = request("/api/transfer/messages", "POST", body, {"Content-Type": content_type})
                self.assertEqual(status, 200, result)
                attachment = result["message"]["attachments"][0]
                self.assertEqual(attachment["name"], "验证图片.png")
                self.assertEqual(result["message"]["sender"], "desktop")
                self.assertTrue(Path(attachment["path"]).is_file())
                status, history, _ = request("/api/transfer/messages")
                self.assertEqual(status, 200, history)
                self.assertEqual(len(history["messages"]), 1)
                self.assertTrue(request("/api/transfer/messages?revision=" + history["revision"])[1]["unchanged"])
                self.assertEqual(request(attachment["url"])[1], image_bytes())
                status, raw, response_headers = request(attachment["url"], "HEAD")
                self.assertEqual((status, raw), (200, b""))
                self.assertEqual(response_headers["Content-Length"], str(len(image_bytes())))
                self.assertEqual(request(attachment["previewUrl"])[2]["Content-Type"], "image/jpeg")
                with patch.object(desktop.PHONE_COMPANION, "state", return_value={"enabled": True,
                        "url": "http://192.168.1.55:8899", "pairingCode": "987654"}):
                    status, code_image, response_headers = request("/api/phone-companion/qr.png?version=http%3A%2F%2F192.168.1.55%3A8899")
                    self.assertEqual(status, 200)
                    self.assertEqual(response_headers["Content-Type"], "image/png")
                    self.assertEqual(response_headers["Cache-Control"], "no-store")
                    with Image.open(io.BytesIO(code_image)) as image:
                        self.assertEqual(image.format, "PNG")
                    self.assertEqual(request("/api/phone-companion/qr.png?unexpected=yes")[0], 400)
                    self.assertEqual(request("/api/phone-companion/qr.png?version=" + "a" * 181)[0], 400)
                    self.assertEqual(request("/api/phone-companion/qr.png", headers={"Host": "evil.test"})[0], 403)
                    with patch.object(desktop, "_client_address_is_loopback", return_value=False):
                        self.assertEqual(request("/api/phone-companion/qr.png")[0], 403)
                with patch.object(desktop.PHONE_COMPANION, "state", return_value={"enabled": False}):
                    self.assertEqual(request("/api/phone-companion/qr.png")[0], 409)
                with patch.object(transfer.os, "startfile", create=True) as open_file:
                    status, result, _ = request("/api/transfer/open", "POST", json.dumps({"id": attachment["id"]}), {"Content-Type": "application/json"})
                    self.assertEqual(status, 200, result)
                    open_file.assert_called_once_with(attachment["path"])
                with patch.object(transfer.os, "startfile", create=True) as open_file:
                    status, result, _ = request("/api/transfer/open", "POST", json.dumps({"id": attachment["id"], "folder": True}), {"Content-Type": "application/json"})
                    self.assertEqual(status, 200, result)
                    open_file.assert_called_once_with(str(Path(attachment["path"]).parent))
                for headers in ({"Origin": "https://evil.test"}, {"Host": "evil.test"}, {"Sec-Fetch-Site": "cross-site"}):
                    self.assertEqual(request("/api/transfer/messages", "POST", body, {"Content-Type": content_type, **headers})[0], 403)
                    self.assertEqual(request("/api/transfer/messages", headers=headers)[0], 403)
                with patch.object(desktop, "_client_address_is_loopback", return_value=False):
                    self.assertEqual(request("/api/transfer/messages")[0], 403)
                    self.assertEqual(request(attachment["url"])[0], 403)
                    self.assertEqual(request("/api/transfer/messages", "POST", body, {"Content-Type": content_type})[0], 403)
                self.assertEqual(request("/api/transfer/messages", "POST", body, {"Content-Type": content_type})[1]["duplicate"], True)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_reject_public_root_and_junction_or_link_redirects(self):
        forbidden = transfer.TransferStore(lambda: str(self.library), self.base / "fallback", public_root=self.base)
        with self.assertRaises(transfer.TransferError) as error:
            forbidden.list()
        self.assertEqual(error.exception.status, 403)
        target = self.library / "互传"
        if os.name == "nt":
            # Query the actual junction filesystem behavior; no shell deletion.
            import subprocess
            sibling = self.library / "other"
            sibling.mkdir()
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                "New-Item -ItemType Junction -Path '" + str(target).replace("'", "''") +
                "' -Target '" + str(sibling).replace("'", "''") + "' | Out-Null"],
                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                self.skipTest("test junction creation is unavailable")
            try:
                with self.assertRaises(transfer.TransferError):
                    self.store.list()
            finally:
                # os.rmdir removes the junction itself, preserving its target.
                target.rmdir()
            self.assertTrue(sibling.is_dir())
            self.assertFalse((sibling / ".console-transfer").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
