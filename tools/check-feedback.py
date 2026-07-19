import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from feedback_service import FeedbackService, FeedbackServiceError  # noqa: E402


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class RelayHandler(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *args):
        return

    def send_payload(self, payload, status=200, content_type="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.requests.append(("GET", self.path, self.headers.get("Authorization", ""), None))
        if self.path == "/v1/config":
            self.send_payload({
                "siteKey": "test-site-key",
                "dailyLimit": 10,
                "maxImageBytes": 5242880,
                "maxImages": 4,
                "maxTotalImageBytes": 12582912,
            })
            return
        if self.path.startswith("/v1/admin/reports?"):
            self.send_payload({
                "reports": [{
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "category": "bug",
                    "description": "Example report for the inbox.",
                    "status": "new",
                    "hasImage": True,
                    "imageCount": 2,
                }],
                "newCount": 1,
            })
            return
        if "/images/" in self.path or self.path.endswith("/image"):
            self.send_payload(b"\x89PNG\r\n\x1a\n", content_type="image/png")
            return
        self.send_payload({"error": "not found"}, status=404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        self.requests.append(("POST", self.path, self.headers.get("Authorization", ""), payload))
        if self.path == "/v1/reports":
            if "burst limit" in str(payload.get("description") or "").lower():
                self.send_payload({
                    "error": "Too many reports. Please wait a minute.",
                    "code": "burst_limit",
                    "retryAfter": 60,
                    "limitReached": False,
                }, status=429)
                return
            if "daily limit" in str(payload.get("description") or "").lower():
                self.send_payload({
                    "error": "This device has reached its daily report limit.",
                    "code": "daily_limit",
                    "retryAfter": 3600,
                    "limitReached": True,
                }, status=429)
                return
            self.send_payload({"ok": True, "id": "report-id", "remaining": 9, "dailyLimit": 10}, status=201)
            return
        self.send_payload({"error": "not found"}, status=404)

    def do_PATCH(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        self.requests.append(("PATCH", self.path, self.headers.get("Authorization", ""), payload))
        self.send_payload({"ok": True, "status": payload.get("status")})


def main():
    RelayHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), RelayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}"

    try:
        with tempfile.TemporaryDirectory(prefix="codex-feedback-") as temporary:
            root = Path(temporary)
            service = FeedbackService(
                root / "app",
                root / "data",
                {"version": "0.5.0", "feedbackEndpoint": endpoint},
                {"installationId": "123e4567-e89b-12d3-a456-426614174000"},
                lambda: "developer",
            )
            config = service.config(force=True)
            require(config["configured"] and config["available"], "relay configuration was not detected")
            require(config["dailyLimit"] == 10 and config["siteKey"] == "test-site-key", "public limits were not loaded")
            require(config["maxImages"] == 4 and config["maxTotalImageBytes"] == 12582912, "multi-image limits were not loaded")
            require("token" not in config, "admin token leaked through the public configuration")

            png = b"\x89PNG\r\n\x1a\n" + b"sample"
            submitted = service.submit({
                "category": "layout",
                "description": "The tabs overlap after the first launch.",
                "locale": "en",
                "module": "workspace",
                "turnstileToken": "verified-test-token",
                "screenshots": [
                    {
                        "data": base64.b64encode(png).decode("ascii"),
                        "type": "image/png",
                        "name": "layout.png",
                    },
                    {
                        "data": base64.b64encode(png).decode("ascii"),
                        "type": "image/png",
                        "name": "layout-detail.png",
                    },
                ],
            })
            require(submitted["remaining"] == 9, "submission response was not returned")
            forwarded = next(item[3] for item in RelayHandler.requests if item[1] == "/v1/reports")
            require(forwarded["installationId"].startswith("123e4567"), "installation ID was not forwarded")
            require(forwarded["screenshot"]["type"] == "image/png", "validated screenshot was not forwarded")
            require(len(forwarded["screenshots"]) == 2, "multiple screenshots were not forwarded")

            for description, expected_code, expected_limit in (
                ("Burst limit test should remain temporary.", "burst_limit", False),
                ("Daily limit test should lock until reset.", "daily_limit", True),
            ):
                try:
                    service.submit({"category": "bug", "description": description})
                except FeedbackServiceError as error:
                    require(error.status == 429, "rate-limit status was not preserved")
                    require(error.code == expected_code, "rate-limit type was not preserved")
                    require(error.limit_reached is expected_limit, "daily and burst limits were confused")
                    require(error.retry_after > 0, "rate-limit reset time was not preserved")
                    require(error.payload().get("limitReached", False) is expected_limit, "public limit payload is wrong")
                else:
                    raise AssertionError("rate-limited feedback was accepted")

            try:
                service.submit({
                    "category": "bug",
                    "description": "This image claims to be JPEG but is PNG.",
                    "screenshot": {
                        "data": base64.b64encode(png).decode("ascii"),
                        "type": "image/jpeg",
                    },
                })
            except FeedbackServiceError as error:
                require("does not match" in str(error), "mismatched image error is unclear")
            else:
                raise AssertionError("mismatched screenshot type was accepted")

            token = "a-secure-admin-token-with-32-characters"
            configured = service.save_admin_config({"endpoint": endpoint, "token": token})
            require(configured["adminEnabled"], "local inbox token was not saved")
            require(token not in json.dumps(configured), "admin token leaked from save response")
            require(token not in service.admin_file.read_text(encoding="utf-8"), "admin token was stored in plaintext")
            inbox = service.inbox()
            require(inbox["newCount"] == 1, "inbox was not loaded")
            admin_request = next(item for item in RelayHandler.requests if item[1].startswith("/v1/admin/reports?"))
            require(admin_request[2] == f"Bearer {token}", "admin request did not use the local token")
            image, content_type = service.report_image("123e4567-e89b-12d3-a456-426614174000", 1)
            require(content_type == "image/png" and image.startswith(b"\x89PNG"), "private image proxy failed")
            require(service.update_status("123e4567-e89b-12d3-a456-426614174000", "resolved")["status"] == "resolved", "status update failed")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    print("PASS Codex Console feedback service")


if __name__ == "__main__":
    main()
