"""Disposable loopback-only gateway for the real-browser Origin regression check."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from document_library import DocumentLibraryService
import phone_companion as phone
from phone_device_store import PhoneDeviceStore
from transfer_store import TransferStore


class ProbeHandler(phone._PhoneHandler):
    def send_header(self, keyword, value):
        if keyword.lower() == "referrer-policy" and self.server.legacy_headers:
            value = "no-referrer"
        return super().send_header(keyword, value)

    def _context(self, post=False):
        self.server.observed.append({"method": self.command, "path": self.path.split("?", 1)[0],
                                     "origin": self.headers.get("Origin"),
                                     "fetchSite": self.headers.get("Sec-Fetch-Site")})
        return super()._context(post=post)

    def do_GET(self):
        prefix = "/__origin_browser/"
        if self.path.startswith(prefix):
            policy = self.path[len(prefix):]
            if policy not in {"no-referrer", "same-origin", "strict-origin"}:
                self.send_error(404)
                return
            data = b"<!doctype html><title>Disposable Origin probe</title>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            # Deliberately bypass the legacy override for this controlled page.
            super().send_header("Referrer-Policy", policy)
            self.end_headers()
            self.wfile.write(data)
            return
        return super().do_GET()


def main():
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="codex-phone-origin-browser-") as temporary:
        base = Path(temporary)
        library = base / "library"
        library.mkdir()
        documents = DocumentLibraryService(base / "documents.json")
        documents.select(str(library))
        plan = {"plan": {"version": 1, "revision": "browser-origin-fixture", "groups": [
            {"id": f"fixture-{index}", "title": f"Fixture {index}", "summary": "", "items": []}
            for index in range(4)]}, "error": ""}
        clock = [100.0]
        service = phone.PhoneCompanionService(documents, lambda: plan, repo, "browser-fixture",
            device_getter=lambda: {"model": "Disposable fixture"},
            clock=lambda: clock[0],
            interface_getter=lambda: [{"address": "127.0.0.1", "name": "Loopback fixture",
                                       "fingerprint": "a" * 64}],
            transfer_store=TransferStore(lambda: str(library), base / "transfer"),
            device_store=PhoneDeviceStore(base / "devices"))
        original_policy = phone.is_lan_address
        with patch.object(phone, "is_lan_address", lambda value: value == "127.0.0.1" or original_policy(value)):
            with socket.socket() as holder:
                holder.bind(("127.0.0.1", 0))
                port = holder.getsockname()[1]
            service.start("127.0.0.1", port)
            server = service._server
            server.RequestHandlerClass = ProbeHandler
            server.legacy_headers = False
            server.observed = []
            image = io.BytesIO()
            Image.new("RGB", (2, 2), "#7858d8").save(image, "PNG")

            def reply(value):
                print(json.dumps(value), flush=True)

            reply({"origin": f"http://127.0.0.1:{port}",
                   "png": base64.b64encode(image.getvalue()).decode("ascii")})
            try:
                for line in sys.stdin:
                    command = json.loads(line)
                    if command["command"] == "renew":
                        # Separate successful invitations are separate simulated minutes;
                        # retain production rate limiting without waiting in the browser check.
                        clock[0] += 61
                        service.renew_pairing()
                        state = service.state(False)
                        reply({"code": state["pairingCode"], "qrToken": state["qrToken"]})
                    elif command["command"] == "observed":
                        observed, server.observed = server.observed, []
                        reply({"requests": observed})
                    elif command["command"] == "legacy-headers":
                        server.legacy_headers = command["enabled"]
                        reply({"ok": True})
                    elif command["command"] == "stop":
                        reply({"ok": True})
                        break
                    else:
                        raise ValueError("Unknown fixture command")
            finally:
                service.stop()


if __name__ == "__main__":
    main()
