import base64
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


MAX_DESCRIPTION_LENGTH = 4000
MIN_DESCRIPTION_LENGTH = 10
MAX_IMAGE_BYTES = 5 * 1024 * 1024
DEFAULT_DAILY_LIMIT = 10
ALLOWED_CATEGORIES = ("bug", "layout", "music", "update", "other")
ALLOWED_IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp")


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _protect_secret(value):
    raw = str(value or "").encode("utf-8")
    if not raw:
        return ""
    if sys.platform != "win32":
        return "portable:" + base64.b64encode(raw).decode("ascii")
    source_buffer = ctypes.create_string_buffer(raw)
    source = _DataBlob(len(raw), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
    protected = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    if not crypt32.CryptProtectData(
        ctypes.byref(source),
        ctypes.c_wchar_p("Codex Console feedback inbox"),
        None,
        None,
        None,
        0x01,
        ctypes.byref(protected),
    ):
        raise OSError(ctypes.get_last_error(), "Could not protect the feedback admin token.")
    try:
        encrypted = ctypes.string_at(protected.pbData, protected.cbData)
    finally:
        kernel32.LocalFree(protected.pbData)
    return "dpapi:" + base64.b64encode(encrypted).decode("ascii")


def _unprotect_secret(value):
    protected_value = str(value or "").strip()
    if not protected_value:
        return ""
    if protected_value.startswith("portable:"):
        try:
            return base64.b64decode(protected_value[9:], validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return ""
    if not protected_value.startswith("dpapi:") or sys.platform != "win32":
        return ""
    try:
        encrypted = base64.b64decode(protected_value[6:], validate=True)
    except ValueError:
        return ""
    source_buffer = ctypes.create_string_buffer(encrypted)
    source = _DataBlob(len(encrypted), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
    clear = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    if not crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        0x01,
        ctypes.byref(clear),
    ):
        return ""
    try:
        return ctypes.string_at(clear.pbData, clear.cbData).decode("utf-8")
    except UnicodeDecodeError:
        return ""
    finally:
        kernel32.LocalFree(clear.pbData)


class FeedbackServiceError(RuntimeError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = int(status or 400)


def _atomic_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _read_json(path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _clean_endpoint(value, allow_local=False):
    endpoint = str(value or "").strip().rstrip("/")
    if not endpoint:
        return ""
    parsed = urllib.parse.urlparse(endpoint)
    local_hosts = {"127.0.0.1", "localhost", "::1"}
    allowed_scheme = parsed.scheme == "https" or (
        allow_local and parsed.scheme == "http" and parsed.hostname in local_hosts
    )
    if not allowed_scheme or not parsed.netloc or parsed.username or parsed.password:
        raise FeedbackServiceError("Feedback endpoint must use HTTPS.")
    return endpoint


def _image_type(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return ""


def _clean_image_name(value, content_type):
    name = Path(str(value or "screenshot").replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" ._")[:96]
    extension = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[content_type]
    if not name:
        return "screenshot" + extension
    if Path(name).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        name += extension
    return name


class FeedbackService:
    def __init__(self, app_dir, user_data_dir, manifest, installation_state, edition_provider):
        self.app_dir = Path(app_dir)
        self.user_data_dir = Path(user_data_dir)
        self.manifest = dict(manifest or {})
        self.installation_state = dict(installation_state or {})
        self.edition_provider = edition_provider
        self.admin_file = self.user_data_dir / "feedback-admin.json"
        self._remote_config = {}
        self._remote_config_at = None

    def _is_developer(self):
        return str(self.edition_provider() or "").strip().lower() == "developer"

    def _admin_state(self):
        return _read_json(self.admin_file)

    def _endpoint(self):
        admin = self._admin_state()
        value = (
            os.environ.get("CODEX_FEEDBACK_ENDPOINT", "").strip()
            or str(admin.get("endpoint") or "").strip()
            or str(self.manifest.get("feedbackEndpoint") or "").strip()
        )
        return _clean_endpoint(value, allow_local=self._is_developer()) if value else ""

    def _admin_token(self):
        admin = self._admin_state()
        return (
            os.environ.get("CODEX_FEEDBACK_ADMIN_TOKEN", "").strip()
            or _unprotect_secret(admin.get("tokenProtected"))
            or str(admin.get("token") or "").strip()
        )

    def _site_key(self):
        return (
            os.environ.get("CODEX_FEEDBACK_TURNSTILE_SITE_KEY", "").strip()
            or str(self.manifest.get("feedbackTurnstileSiteKey") or "").strip()
            or str(self._remote_config.get("siteKey") or "").strip()
        )

    def _request(self, method, path, payload=None, admin=False, timeout=20):
        endpoint = self._endpoint()
        if not endpoint:
            raise FeedbackServiceError("Feedback service is not configured.", status=503)
        headers = {
            "Accept": "application/json",
            "User-Agent": f"CodexControlConsole/{self.manifest.get('version') or 'dev'}",
        }
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        if admin:
            token = self._admin_token()
            if not token:
                raise FeedbackServiceError("Feedback inbox is not connected on this device.", status=403)
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(endpoint + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
                content_type = response.headers.get_content_type()
                if content_type == "application/json":
                    return json.loads(body.decode("utf-8")) if body else {}
                return {
                    "body": body,
                    "contentType": response.headers.get("Content-Type", "application/octet-stream"),
                }
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8"))
                message = str(detail.get("error") or detail.get("message") or "Feedback request failed.")
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                message = "Feedback request failed."
            raise FeedbackServiceError(message, status=error.code) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise FeedbackServiceError("Feedback service is temporarily unavailable.", status=503) from error

    def _load_remote_config(self, force=False):
        now = datetime.now(timezone.utc)
        if not force and self._remote_config_at and (now - self._remote_config_at).total_seconds() < 300:
            return self._remote_config
        if not self._endpoint():
            self._remote_config = {}
            self._remote_config_at = now
            return self._remote_config
        try:
            payload = self._request("GET", "/v1/config", timeout=8)
            self._remote_config = payload if isinstance(payload, dict) else {}
        except FeedbackServiceError:
            self._remote_config = {}
        self._remote_config_at = now
        return self._remote_config

    def config(self, force=False):
        self._load_remote_config(force=force)
        endpoint = self._endpoint()
        return {
            "configured": bool(endpoint),
            "available": bool(endpoint and self._remote_config),
            "siteKey": self._site_key(),
            "categories": list(ALLOWED_CATEGORIES),
            "dailyLimit": int(self._remote_config.get("dailyLimit") or DEFAULT_DAILY_LIMIT),
            "maxImageBytes": int(self._remote_config.get("maxImageBytes") or MAX_IMAGE_BYTES),
            "maxDescriptionLength": MAX_DESCRIPTION_LENGTH,
            "adminEnabled": bool(endpoint and self._admin_token()),
            "adminSetupAvailable": self._is_developer(),
            "endpoint": endpoint if self._is_developer() else "",
        }

    def save_admin_config(self, payload):
        if not self._is_developer():
            raise FeedbackServiceError("Feedback inbox settings are available in the developer edition only.", status=403)
        payload = payload if isinstance(payload, dict) else {}
        endpoint = _clean_endpoint(payload.get("endpoint"), allow_local=True)
        current_token = self._admin_token()
        token = str(payload.get("token") or "").strip() or current_token
        if token and len(token) < 24:
            raise FeedbackServiceError("Admin token must contain at least 24 characters.")
        _atomic_write_json(self.admin_file, {
            "endpoint": endpoint,
            "tokenProtected": _protect_secret(token),
            "updated": datetime.now(timezone.utc).isoformat(),
        })
        self._remote_config_at = None
        return self.config(force=True)

    def _normalize_screenshot(self, payload):
        screenshot = payload.get("screenshot")
        if not screenshot:
            return None
        if not isinstance(screenshot, dict):
            raise FeedbackServiceError("Screenshot data is invalid.")
        encoded = str(screenshot.get("data") or "").strip()
        if encoded.startswith("data:"):
            if "," not in encoded:
                raise FeedbackServiceError("Screenshot data is invalid.")
            encoded = encoded.split(",", 1)[1]
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as error:
            raise FeedbackServiceError("Screenshot data is invalid.") from error
        if not data:
            return None
        if len(data) > MAX_IMAGE_BYTES:
            raise FeedbackServiceError("Screenshot must be 5 MB or smaller.", status=413)
        detected_type = _image_type(data)
        if detected_type not in ALLOWED_IMAGE_TYPES:
            raise FeedbackServiceError("Screenshot must be PNG, JPEG, or WebP.")
        claimed_type = str(screenshot.get("type") or "").strip().lower()
        if claimed_type and claimed_type != detected_type:
            raise FeedbackServiceError("Screenshot file type does not match its contents.")
        return {
            "data": base64.b64encode(data).decode("ascii"),
            "type": detected_type,
            "name": _clean_image_name(screenshot.get("name"), detected_type),
        }

    def submit(self, payload):
        payload = payload if isinstance(payload, dict) else {}
        category = str(payload.get("category") or "bug").strip().lower()
        if category not in ALLOWED_CATEGORIES:
            raise FeedbackServiceError("Feedback category is invalid.")
        description = str(payload.get("description") or "").strip()
        if len(description) < MIN_DESCRIPTION_LENGTH:
            raise FeedbackServiceError("Please describe the problem in at least 10 characters.")
        if len(description) > MAX_DESCRIPTION_LENGTH:
            raise FeedbackServiceError("Feedback description is too long.")
        screenshot = self._normalize_screenshot(payload)
        forwarded = {
            "category": category,
            "description": description,
            "installationId": str(self.installation_state.get("installationId") or ""),
            "appVersion": str(self.manifest.get("version") or "dev"),
            "osVersion": platform.platform()[:180],
            "locale": str(payload.get("locale") or "")[:24],
            "module": str(payload.get("module") or "")[:48],
            "turnstileToken": str(payload.get("turnstileToken") or "")[:4096],
        }
        if screenshot:
            forwarded["screenshot"] = screenshot
        return self._request("POST", "/v1/reports", forwarded, timeout=35)

    def inbox(self, status="new", limit=50):
        status = str(status or "new").strip().lower()
        if status not in {"new", "resolved", "all"}:
            status = "new"
        try:
            limit = max(1, min(100, int(limit)))
        except (TypeError, ValueError):
            limit = 50
        query = urllib.parse.urlencode({"status": status, "limit": limit})
        return self._request("GET", f"/v1/admin/reports?{query}", admin=True)

    def report_image(self, report_id):
        report_id = str(report_id or "").strip()
        if not re.fullmatch(r"[0-9a-fA-F-]{16,64}", report_id):
            raise FeedbackServiceError("Report ID is invalid.")
        result = self._request("GET", f"/v1/admin/reports/{urllib.parse.quote(report_id)}/image", admin=True)
        body = result.get("body") if isinstance(result, dict) else None
        if not isinstance(body, bytes):
            raise FeedbackServiceError("Screenshot was not found.", status=404)
        return body, str(result.get("contentType") or "application/octet-stream")

    def update_status(self, report_id, status):
        report_id = str(report_id or "").strip()
        status = str(status or "").strip().lower()
        if not re.fullmatch(r"[0-9a-fA-F-]{16,64}", report_id):
            raise FeedbackServiceError("Report ID is invalid.")
        if status not in {"new", "resolved"}:
            raise FeedbackServiceError("Report status is invalid.")
        return self._request(
            "PATCH",
            f"/v1/admin/reports/{urllib.parse.quote(report_id)}",
            {"status": status},
            admin=True,
        )
