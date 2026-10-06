"""Explicit ChatGPT-plan connections and a commit-event-only discussion worker.

This owns a separate Windows-protected OAuth store.  It never imports probe
credentials, scans an outbox, sends a test, or falls back to API-key billing.
The service owns durable claims, send intents, and origin-bound result writes.
"""
from __future__ import annotations

import base64
import ctypes
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import re
import secrets
import ssl
import stat
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from workflow_service import WorkflowError


ISSUER = "https://auth.openai.com"
AUTHORIZE = ISSUER + "/api/accounts/authorize"
TOKEN = ISSUER + "/api/accounts/oauth/token"
JWKS = ISSUER + "/.well-known/jwks.json"
DISCOVERY = ISSUER + "/.well-known/openid-configuration"
RESOURCE = "https://api.openai.com/v1"
MODELS = RESOURCE + "/models"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
DIRECT_SCOPES = {"resource.invoke", "chatgpt.tokens.use.direct"}
PROVIDER = "chatgpt_subscription"
PROTECTED_HEADER = b"CONSOLE-SUBSCRIPTION-DPAPI-v1\n"
HINT_HEADER = b"CONSOLE-SUBSCRIPTION-ID-HINT-v1\n"
BINDING_KEYS = {"provider", "connectionId", "catalogRevision", "modelSlug"}
SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
MAX_IMAGE = 8 * 1024 * 1024
MAX_IMAGES = 24 * 1024 * 1024
IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
# Stable across all instances. Keep the mutex range far beyond bounded backup
# read requests (including BufferedReader readahead); the file itself stays 1 B.
WINDOWS_LOCK_OFFSET = 2**31 - 1


def _error(code, message="订阅通道尚未准备好；内容保留，未自动重发。", status=409):
    return WorkflowError(message, status, code)


def _code(error, fallback="subscription_operation_failed"):
    value = getattr(error, "code", None)
    return value if isinstance(value, str) and CODE.fullmatch(value) else fallback


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _atomic(path, data):
    fd, temporary = tempfile.mkstemp(prefix=".subscription-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _reject_reparse(path):
    """Check lexical ancestors before following or creating any descendant."""
    absolute = path.absolute()
    for node in (absolute, *absolute.parents):
        try:
            information = node.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(information.st_mode)
                or getattr(information, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise _error("subscription_store_path_invalid")


def _canonical_store_directory(path):
    absolute = path.absolute()
    _reject_reparse(absolute)
    absolute.mkdir(parents=True, exist_ok=True)
    canonical = absolute.resolve(strict=True)
    _reject_reparse(canonical)
    # GetFinalPathNameByHandle expands legitimate Windows 8.3 names. File
    # identity, after rejecting every reparse ancestor, validates that alias.
    if not absolute.samefile(canonical) or (os.name != "nt" and canonical != absolute):
        raise _error("subscription_store_path_invalid")
    return canonical


def _protect(data, decrypt=False):
    if os.name != "nt":
        raise _error("subscription_protection_unavailable", "订阅登录需要 Windows 当前用户的凭据保护。")

    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    raw = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(raw, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    if decrypt:
        function = crypt32.CryptUnprotectData
        function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                             ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(Blob)]
        arguments = (ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        function = crypt32.CryptProtectData
        function.argtypes = [ctypes.POINTER(Blob), ctypes.c_wchar_p, ctypes.c_void_p,
                             ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(Blob)]
        arguments = (ctypes.byref(source), "Codex Console subscription", None, None, None, 1, ctypes.byref(target))
    function.restype = ctypes.c_int
    if not function(*arguments):
        raise _error("subscription_protection_failed", "Windows 无法读取或保护此订阅连接自己的凭据。")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel32.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        return None


def _revocation_url(value):
    if not isinstance(value, str) or len(value) > 512:
        return False
    parsed = urllib.parse.urlsplit(value)
    return (parsed.scheme == "https" and parsed.netloc == "auth.openai.com"
            and parsed.path.startswith("/") and not parsed.query and not parsed.fragment)


def _remote_json(url, *, form=None, bearer=None, revoke=False):
    allowed = {TOKEN, JWKS, DISCOVERY, MODELS}
    if url not in allowed and not (revoke and _revocation_url(url)):
        raise _error("subscription_endpoint_invalid")
    if bearer is not None and url != MODELS:
        raise _error("subscription_endpoint_invalid")
    if form is not None and url != TOKEN and not (revoke and _revocation_url(url)):
        raise _error("subscription_endpoint_invalid")
    headers, body = {"Accept": "application/json"}, None
    if form is not None:
        body = urllib.parse.urlencode(form).encode("ascii")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if bearer is not None:
        if not _token_valid(bearer):
            raise _error("subscription_token_invalid")
        headers["Authorization"] = "Bearer " + bearer
    request = urllib.request.Request(url, data=body, headers=headers, method="POST" if form is not None else "GET")
    context = ssl.create_default_context()
    context.keylog_filename = None
    opener = urllib.request.build_opener(_NoRedirect(), urllib.request.HTTPSHandler(context=context))
    try:
        with opener.open(request, timeout=25) as response:
            if response.status != 200 or response.geturl() != url:
                raise _error("subscription_http_unexpected")
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise _error("subscription_response_too_large")
        if revoke and not raw:
            return {}
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise _error("subscription_response_invalid")
        return document
    except urllib.error.HTTPError as error:
        safe = "subscription_http_" + str(error.code)
        try:
            raw = error.read(65537)
            document = json.loads(raw) if len(raw) <= 65536 else {}
            value = document.get("error") if isinstance(document, dict) else None
            value = value.get("code") if isinstance(value, dict) else value
            secret_values = [bearer] + [(form or {}).get(key) for key in ("code", "code_verifier", "refresh_token", "token")]
            if (isinstance(value, str) and CODE.fullmatch(value)
                    and not any(secret and secret in value for secret in secret_values)):
                safe = value
        except (OSError, ValueError, TypeError):
            pass
        finally:
            error.close()
        failure = _error(safe)
        failure.remote_status = error.code
        raise failure from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise _error("subscription_transport_unknown") from None


def _token_valid(value):
    return isinstance(value, str) and 1 <= len(value) <= 65536 and all(33 <= ord(c) < 127 for c in value)


def _client_valid(value):
    return _token_valid(value) and len(value) <= 512 and value != "dynamic_agent_client"


def _callback_query(target, hosts, expected_host):
    if not isinstance(target, str) or len(target) > 16384 or hosts != [expected_host]:
        raise _error("subscription_callback_invalid")
    parsed = urllib.parse.urlsplit(target)
    if parsed.scheme or parsed.netloc or parsed.fragment or parsed.path != "/auth/callback":
        raise _error("subscription_callback_invalid")
    try:
        return urllib.parse.parse_qs(parsed.query, keep_blank_values=True, max_num_fields=8)
    except ValueError:
        raise _error("subscription_callback_invalid") from None


def _verify_identity(encoded, client_id, nonce, request_json=_remote_json):
    try:
        import jwt
    except ImportError:
        raise _error("subscription_auth_dependency_missing", "订阅登录的签名验证组件尚未安装。") from None
    try:
        header = jwt.get_unverified_header(encoded)
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            raise ValueError()
        document = request_json(JWKS)
        keys = document.get("keys")
        if not isinstance(keys, list) or len(keys) > 100:
            raise ValueError()
        matches = [key for key in keys if isinstance(key, dict) and key.get("kid") == header["kid"]
                   and key.get("kty") == "RSA" and key.get("use", "sig") == "sig"
                   and key.get("alg", "RS256") == "RS256"]
        if len(matches) != 1:
            raise ValueError()
        signing_key = jwt.PyJWK.from_dict(matches[0], algorithm="RS256")
        claims = jwt.decode(encoded, signing_key.key, algorithms=["RS256"], audience=client_id,
                            issuer=ISSUER, options={"require": ["iss", "aud", "sub", "exp", "nonce"]})
        if (not isinstance(claims.get("sub"), str) or not 1 <= len(claims["sub"]) <= 1024
                or not isinstance(claims.get("nonce"), str)
                or (isinstance(claims.get("aud"), list) and len(claims["aud"]) > 1 and claims.get("azp") != client_id)
                or (claims.get("azp") is not None and claims["azp"] != client_id)
                or not secrets.compare_digest(claims["nonce"].encode("utf-8"), nonce.encode("utf-8"))):
            raise ValueError()
        return claims
    except Exception:
        raise _error("subscription_identity_invalid", "登录的官方签名、身份、有效期或本次 nonce 无法核实。") from None


def build_input(prepared):
    """Consume only the service's origin-verified frozen text and image copies."""
    frozen, text = prepared.get("frozen"), prepared.get("text")
    if (not isinstance(frozen, dict) or not isinstance(text, str) or len(text) > 65000
            or frozen.get("text") != text or not isinstance(frozen.get("history"), list)):
        raise _error("subscription_frozen_input_invalid")
    history = frozen["history"]
    if (len(history) > 100 or any(not isinstance(row, dict) or not isinstance(row.get("role"), str)
            or not isinstance(row.get("content"), str) for row in history)
            or sum(len(row["content"]) for row in history) > 65000):
        raise _error("subscription_frozen_input_invalid")
    frozen_images, copies = frozen.get("images"), prepared.get("imageBytes", [])
    if not isinstance(frozen_images, list) or not isinstance(copies, list) or len(copies) != len(frozen_images) or len(copies) > 4:
        raise _error("subscription_images_source_mismatch")
    parts, descriptors, total = [], [], 0
    for original, copied in zip(frozen_images, copies):
        if not isinstance(original, dict) or not isinstance(copied, (tuple, list)) or len(copied) != 2:
            raise _error("subscription_images_source_mismatch")
        descriptor, data = copied
        if (not isinstance(descriptor, dict) or not isinstance(data, bytes) or descriptor.get("mimeType") not in IMAGE_MIMES
                or not 0 < len(data) <= MAX_IMAGE or descriptor.get("size") != len(data)
                or descriptor.get("id") != original.get("id") or descriptor.get("mimeType") != original.get("mimeType")
                or original.get("size") != len(data) or descriptor.get("sha256") != original.get("sha256")
                or hashlib.sha256(data).hexdigest() != original.get("sha256")):
            raise _error("subscription_image_changed")
        total += len(data)
        if total > MAX_IMAGES:
            raise _error("subscription_images_too_large")
        descriptors.append({key: descriptor[key] for key in ("id", "mimeType", "size", "sha256")})
        parts.append({"type": "input_image", "image_url": "data:" + descriptor["mimeType"] + ";base64," + base64.b64encode(data).decode("ascii")})
    if not text.strip() and not parts:
        raise _error("subscription_empty_input")
    context = {"submissionTime": frozen.get("submissionTime"), "question": text,
               "history": history, "selectedImages": descriptors}
    for field in ("recordTitle", "projectName", "mobileIdeaContext"):
        if field in frozen:
            context[field] = frozen[field]
    message = ("以下是 Console 已确认的一轮讨论。请根据本轮文字、随请求提供的所选图片和冻结上下文回答。"
               "提交时间是 Console 保存的确认时间，不是你接收或完成回答的时间。\n" + _json(context).decode("utf-8"))
    return [{"role": "user", "content": [{"type": "input_text", "text": message}, *parts]}]


class WorkflowSubscription:
    def __init__(self, service, directory=None, *, request_json=None, protect=None,
                 verify_identity=None, run_response=None, clock=None):
        self.service = service
        self.directory = Path(directory) if directory is not None else service.data_dir / "chatgpt-subscription"
        self._request = request_json or _remote_json
        self._protect = protect or _protect
        self._verify = verify_identity or (lambda encoded, client, nonce: _verify_identity(encoded, client, nonce, self._request))
        self._runner = run_response
        self._clock = clock or time.time
        self._lock = threading.RLock()
        self._lifecycle_lock = threading.Lock()
        self._queue_lock = threading.Lock()
        self._queue = queue.Queue(maxsize=64)
        self._seen, self._released = set(), set()
        self._stopping = threading.Event()
        self._worker = None
        self._callback_server = self._callback_thread = None
        self._pending = None
        self._auth_busy = self._processing = False
        self._active = False
        self._connection = None
        self._id_hint = None
        self._models, self._catalog_revision = [], None
        self._status, self._last_error = "disconnected", None
        self._registry_path = self.directory / "registration.json"
        self._credential_path = self.directory / "connection.dpapi"
        self._hint_path = self.directory / "identity-hint.dpapi"
        self._registry = None
        self._store_available = False
        self._initialized = False
        self._process_file = None

    def _initialize(self):
        """Only actual app start or an explicit local auth action opens this store."""
        with self._lock:
            if self._initialized or self._stopping.is_set():
                return
            self._initialized = True
            try:
                self.directory = _canonical_store_directory(self.directory)
                self._registry_path = self.directory / "registration.json"
                self._credential_path = self.directory / "connection.dpapi"
                self._hint_path = self.directory / "identity-hint.dpapi"
                for name in ("registration.json", "connection.dpapi", "identity-hint.dpapi", "connection.lock"):
                    path = self.directory / name
                    _reject_reparse(path)
                    if path.resolve().parent != self.directory:
                        raise _error("subscription_store_path_invalid")
                self._process_file = open(self.directory / "connection.lock", "a+b")
                if os.name == "nt":
                    import msvcrt
                    self._process_file.seek(WINDOWS_LOCK_OFFSET)
                    msvcrt.locking(self._process_file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._process_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Initialize only after acquiring ownership, so concurrent first
                # starts cannot both append a marker or enlarge the file.
                self._process_file.seek(0, os.SEEK_END)
                length = self._process_file.tell()
                if not length:
                    self._process_file.write(b"0")
                    self._process_file.flush()
                elif length != 1:
                    raise _error("subscription_lock_file_invalid")
                self._load()
                self._store_available = True
            except Exception as error:
                if self._process_file is not None:
                    self._process_file.close()
                self._connection, self._active = None, False
                self._status, self._last_error = "store_unavailable", _code(error, "subscription_store_unavailable")

    def _load(self):
        if self._registry_path.exists():
            if self._registry_path.stat().st_size > 8192:
                raise _error("subscription_registration_invalid")
            try:
                self._registry = json.loads(self._registry_path.read_bytes())
                registry = self._registry
                if (registry.get("format") != 1 or registry.get("provider") != PROVIDER
                        or not isinstance(registry.get("hostId"), str) or not registry["hostId"].startswith("urn:uuid:")
                        or not re.fullmatch(r"[a-f0-9]{32}", registry.get("connectionId", ""))):
                    raise ValueError()
                uuid.UUID(registry["hostId"][9:])
                if registry.get("clientId") is not None and not _client_valid(registry["clientId"]):
                    raise ValueError()
                if registry.get("identitySha256") is not None and not re.fullmatch(r"[a-f0-9]{64}", registry["identitySha256"]):
                    raise ValueError()
                if type(registry.get("enabled", False)) is not bool:
                    raise ValueError()
            except (ValueError, TypeError, AttributeError):
                raise _error("subscription_registration_invalid") from None
        else:
            if self._credential_path.exists() or self._hint_path.exists():
                raise _error("subscription_registration_missing")
            self._registry = {"format": 1, "provider": PROVIDER, "hostId": "urn:uuid:" + str(uuid.uuid4()),
                              "connectionId": uuid.uuid4().hex, "clientId": None, "identitySha256": None, "enabled": False}
            _atomic(self._registry_path, _json(self._registry))
        if self._credential_path.exists():
            if self._credential_path.stat().st_size > 262144:
                raise _error("subscription_credentials_invalid")
            raw = self._credential_path.read_bytes()
            if not raw.startswith(PROTECTED_HEADER):
                raise _error("subscription_credentials_invalid")
            try:
                connection = json.loads(self._protect(raw[len(PROTECTED_HEADER):], decrypt=True))
                self._check_connection(connection)
            except (ValueError, TypeError, AttributeError):
                raise _error("subscription_credentials_invalid") from None
            self._connection, self._active = connection, self._registry.get("enabled", False)
            self._id_hint = connection.get("idToken")
            self._status = ("reauth_required" if connection.get("refreshBlocked") else "catalog_required") if self._active else "disconnected"
        if self._hint_path.exists():
            if self._hint_path.stat().st_size > 131072:
                raise _error("subscription_identity_hint_invalid")
            raw = self._hint_path.read_bytes()
            if not raw.startswith(HINT_HEADER):
                raise _error("subscription_identity_hint_invalid")
            try:
                hint = json.loads(self._protect(raw[len(HINT_HEADER):], decrypt=True))
                if (not isinstance(hint, dict) or set(hint) != {"connectionId", "clientId", "identitySha256", "idToken"}
                        or any(hint.get(key) != self._registry[key] for key in ("connectionId", "clientId", "identitySha256"))
                        or not _token_valid(hint.get("idToken"))):
                    raise ValueError()
                self._id_hint = hint["idToken"]
            except (ValueError, TypeError, AttributeError):
                raise _error("subscription_identity_hint_invalid") from None

    def _check_connection(self, connection):
        registry = self._registry
        if (not isinstance(connection, dict) or connection.get("connectionId") != registry["connectionId"]
                or connection.get("clientId") != registry["clientId"] or connection.get("issuer") != ISSUER
                or not isinstance(connection.get("subject"), str) or not 1 <= len(connection["subject"]) <= 1024
                or hashlib.sha256(_json([ISSUER, connection["subject"]])).hexdigest() != registry["identitySha256"]
                or not _token_valid(connection.get("accessToken")) or not isinstance(connection.get("scope"), str)
                or type(connection.get("expiresAt")) not in (int, float) or not 0 < connection["expiresAt"] < 1e12
                or (connection.get("refreshToken") is not None and not _token_valid(connection["refreshToken"]))
                or (connection.get("idToken") is not None and not _token_valid(connection["idToken"]))
                or type(connection.get("refreshBlocked", False)) is not bool):
            raise _error("subscription_credentials_invalid")

    def _save_connection(self, connection):
        self._check_connection(connection)
        protected = self._protect(_json(connection))
        _atomic(self._credential_path, PROTECTED_HEADER + protected)
        self._connection = connection

    def get_status(self):
        with self._lock:
            granted = self._connection and DIRECT_SCOPES.issubset(set(self._connection["scope"].split()))
            connected = bool(not self._stopping.is_set() and self._active and granted and not self._connection.get("refreshBlocked")
                             and (self._connection["expiresAt"] > self._clock() or self._connection.get("refreshToken"))
                             and self._catalog_revision and self._models)
            pending_active = not self._stopping.is_set() and self._pending and time.monotonic() < self._pending["deadline"]
            status = "signin_expired" if self._status == "signing_in" and self._pending and not pending_active else self._status
            if self._stopping.is_set():
                status = "closed"
            return {"connected": connected, "connectionId": self._registry["connectionId"] if self._active and self._registry else None,
                    "catalogRevision": self._catalog_revision, "models": [dict(row) for row in self._models],
                    "status": status, "busy": bool(self._auth_busy or pending_active or self._processing),
                    "error": self._last_error}

    public_status = get_status

    def validate_selection(self, modelSlug, catalogRevision, connectionId):
        with self._lock:
            status = self.get_status()
            if not status["connected"]:
                raise _error("subscription_not_connected", "订阅通道尚未完成独立登录和模型读取；草稿保留。")
            if (connectionId != status["connectionId"] or catalogRevision != self._catalog_revision
                    or not isinstance(catalogRevision, str)):
                raise _error("subscription_selection_stale", "订阅连接或模型目录已改变，请重新选择后确认发送。")
            if not isinstance(modelSlug, str) or not any(row["slug"] == modelSlug for row in self._models):
                raise _error("subscription_model_unavailable", "本账号实际模型目录中没有所选模型；未降档发送。")
            return {"provider": PROVIDER, "connectionId": connectionId,
                    "catalogRevision": catalogRevision, "modelSlug": modelSlug}

    def _check_binding(self, binding):
        if not isinstance(binding, dict) or set(binding) != BINDING_KEYS or binding.get("provider") != PROVIDER:
            raise _error("subscription_binding_invalid")
        if self.validate_selection(binding["modelSlug"], binding["catalogRevision"], binding["connectionId"]) != binding:
            raise _error("subscription_selection_stale")

    def _open_callback(self):
        if self._callback_server is not None:
            return
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                success = False
                expected_host = "127.0.0.1:" + str(self.server.server_port)
                try:
                    query = _callback_query(self.path, self.headers.get_all("Host", []), expected_host)
                    owner.handle_callback(query)
                    success = True
                except Exception:
                    # No callback URL, code, token, identity, or exception repr in HTML/logs.
                    pass
                message = "订阅登录已处理。请返回 Console 查看连接与实际模型。" if success else "登录未完成。请返回 Console 查看状态，原讨论和草稿保留。"
                raw = ("<!doctype html><meta charset=utf-8><title>Codex Console</title><p>" + message + "</p>").encode("utf-8")
                self.send_response(200 if success else 400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(raw)

        self._callback_server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._callback_server.daemon_threads = True
        self._callback_thread = threading.Thread(target=self._callback_server.serve_forever,
                                                 name="console-subscription-oauth", daemon=True)
        self._callback_thread.start()

    def begin_signin(self):
        self._initialize()
        with self._lock:
            if not self._store_available:
                raise _error(self._last_error or "subscription_store_unavailable")
            if self._auth_busy or self._processing or (self._pending and time.monotonic() < self._pending["deadline"]):
                raise _error("subscription_busy")
            if self._stopping.is_set():
                raise _error("subscription_closed")
            try:
                self._open_callback()
            except OSError:
                raise _error("subscription_callback_unavailable", "无法打开本机登录回调；尚未请求官方授权。") from None
            state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
            callback = "http://127.0.0.1:" + str(self._callback_server.server_port) + "/auth/callback"
            self._pending = {"state": state, "nonce": nonce, "verifier": verifier,
                             "redirectUri": callback, "deadline": time.monotonic() + 300}
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
            query = {"client_id": self._registry["clientId"] or "dynamic_agent_client",
                     "ext_agent_host_id": self._registry["hostId"], "response_type": "code", "redirect_uri": callback,
                     "scope": SCOPES, "resource": RESOURCE, "state": state, "nonce": nonce,
                     "code_challenge": challenge, "code_challenge_method": "S256"}
            if self._registry["clientId"] is None:
                query["agent_name_hint"] = "Codex Console"
            elif self._id_hint:
                query["id_token_hint"] = self._id_hint
            self._status, self._last_error = "signing_in", None
            return {"authorizationUrl": AUTHORIZE + "?" + urllib.parse.urlencode(query),
                    "pendingExpiresAt": datetime.fromtimestamp(self._clock() + 300, timezone.utc).isoformat(),
                    **self.get_status()}

    def handle_callback(self, query):
        with self._lock:
            if self._stopping.is_set():
                raise _error("subscription_closed")
            pending = self._pending
            values = query.get("state", []) if isinstance(query, dict) else []
            if (not pending or not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], str)
                    or not secrets.compare_digest(values[0].encode("utf-8"), pending["state"].encode("utf-8"))):
                raise _error("subscription_callback_state_invalid")
            self._pending = None
            try:
                allowed = {"state", "code", "client_id", "scope", "error", "error_description", "iss", "session_state"}
                if (time.monotonic() >= pending["deadline"] or len(query) > 8 or set(query) - allowed
                        or any(not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], str)
                               or len(value[0]) > 8192 for value in query.values())):
                    raise _error("subscription_callback_invalid")
                # The optional callback scope is untrusted presentation data.
                # Granted capabilities come only from the validated token response.
                if "error" in query:
                    raise _error("subscription_login_not_approved")
                if "iss" in query and query["iss"][0] != ISSUER:
                    raise _error("subscription_callback_issuer_invalid")
                code = query.get("code", [""])[0]
                if not _token_valid(code) or len(code) > 8192:
                    raise _error("subscription_callback_code_invalid")
                returned = query.get("client_id", [None])[0]
                client = self._registry["clientId"]
                if client is None:
                    if not _client_valid(returned):
                        raise _error("subscription_client_invalid")
                    self._registry["clientId"] = client = returned
                    _atomic(self._registry_path, _json(self._registry))
                elif returned is not None and returned != client:
                    raise _error("subscription_client_changed")
                self._auth_busy = True
                tokens = self._request(TOKEN, form={"grant_type": "authorization_code", "client_id": client,
                    "code": code, "code_verifier": pending["verifier"], "redirect_uri": pending["redirectUri"], "resource": RESOURCE})
                expires = tokens.get("expires_in")
                if (str(tokens.get("token_type", "")).lower() != "bearer" or not _token_valid(tokens.get("access_token"))
                        or not isinstance(tokens.get("id_token"), str) or not isinstance(tokens.get("scope"), str)
                        or type(expires) is not int or not 0 < expires <= 31 * 86400
                        or (tokens.get("refresh_token") is not None and not _token_valid(tokens["refresh_token"]))):
                    raise _error("subscription_token_response_invalid")
                identity = self._verify(tokens["id_token"], client, pending["nonce"])
                if identity.get("iss") != ISSUER or not isinstance(identity.get("sub"), str):
                    raise _error("subscription_identity_invalid")
                identity_sha = hashlib.sha256(_json([ISSUER, identity["sub"]])).hexdigest()
                previous = self._registry["identitySha256"]
                if previous is not None and previous != identity_sha:
                    raise _error("subscription_account_changed", "该注册属于原账号；不能用另一账号覆盖连接或既有请求。")
                self._registry["identitySha256"] = identity_sha
                _atomic(self._registry_path, _json(self._registry))
                connection = {"connectionId": self._registry["connectionId"], "clientId": client,
                              "issuer": ISSUER, "subject": identity["sub"], "accessToken": tokens["access_token"],
                              "refreshToken": tokens.get("refresh_token"), "idToken": tokens["id_token"], "scope": tokens["scope"],
                              "expiresAt": self._clock() + expires, "refreshBlocked": False}
                self._save_connection(connection)
                hint = {key: self._registry[key] for key in ("connectionId", "clientId", "identitySha256")}
                hint["idToken"] = tokens["id_token"]
                _atomic(self._hint_path, HINT_HEADER + self._protect(_json(hint)))
                self._id_hint = tokens["id_token"]
                self._registry["enabled"] = True
                _atomic(self._registry_path, _json(self._registry))
                self._active = True
                self._models, self._catalog_revision = [], None
                self._last_error = None
                self._refresh_catalog_locked()
            except Exception as error:
                self._last_error, self._status = _code(error), "login_failed"
                raise _error(self._last_error) from None
            finally:
                self._auth_busy = False
                self._release_if_closed()

    def _token_locked(self, binding=None):
        if self._stopping.is_set():
            raise _error("subscription_closed")
        if not self._store_available:
            raise _error(self._last_error or "subscription_store_unavailable")
        if binding is not None:
            self._check_binding(binding)
        connection = self._connection
        if not self._active or not connection or not DIRECT_SCOPES.issubset(set(connection["scope"].split())):
            raise _error("subscription_not_connected")
        if connection.get("refreshBlocked"):
            raise _error("subscription_reauth_required")
        if connection["expiresAt"] > self._clock() + 60:
            return connection["accessToken"]
        if not connection.get("refreshToken"):
            self._status = "reauth_required"
            raise _error("subscription_reauth_required")
        blocked = {**connection, "refreshBlocked": True}
        try:
            # Rotation reservation must survive a crash after the remote POST,
            # including a crash before the new credential can be saved.
            self._save_connection(blocked)
        except Exception:
            self._connection = blocked
            self._status, self._last_error = "reauth_required", "subscription_refresh_reservation_failed"
            raise _error(self._last_error) from None
        try:
            tokens = self._request(TOKEN, form={"grant_type": "refresh_token", "client_id": connection["clientId"],
                "refresh_token": connection["refreshToken"], "resource": RESOURCE})
            expires, scope = tokens.get("expires_in"), tokens.get("scope", connection["scope"])
            if (str(tokens.get("token_type", "")).lower() != "bearer" or not _token_valid(tokens.get("access_token"))
                    or type(expires) is not int or not 0 < expires <= 31 * 86400 or not isinstance(scope, str)
                    or not DIRECT_SCOPES.issubset(set(scope.split()))
                    or (tokens.get("refresh_token") is not None and not _token_valid(tokens["refresh_token"]))):
                raise _error("subscription_refresh_response_invalid")
            renewed = {**connection, "accessToken": tokens["access_token"],
                       "refreshToken": tokens.get("refresh_token", connection["refreshToken"]),
                       "scope": scope, "expiresAt": self._clock() + expires, "refreshBlocked": False}
            self._save_connection(renewed)
            self._last_error = None
            return renewed["accessToken"]
        except Exception as error:
            if getattr(error, "remote_status", None) in {429, 500, 502, 503, 504} and _code(error) != "invalid_grant":
                # A definite temporary HTTP refusal preserves the still-saved credential.
                # Only a later explicit catalog refresh/new confirmation can try again.
                try:
                    self._save_connection(connection)
                except Exception:
                    self._connection = blocked
                    self._status, self._last_error = "reauth_required", "subscription_refresh_restore_failed"
                else:
                    self._status, self._last_error = "refresh_failed", _code(error)
                raise _error(self._last_error) from None
            # An ambiguous rotation is never retried with the old refresh token.
            self._connection = blocked
            self._status, self._last_error = "reauth_required", _code(error, "subscription_refresh_unknown")
            raise _error(self._last_error) from None

    def credential_token(self, binding):
        # Released before ANY service/SQLite callback. No credential->DB lock edge.
        with self._lock:
            return self._token_locked(binding)

    def _refresh_catalog_locked(self):
        token = self._token_locked()
        document = self._request(MODELS, bearer=token)
        rows = document.get("models")
        if not isinstance(rows, list) or len(rows) > 1000:
            raise _error("subscription_catalog_invalid")
        models, slugs = [], set()
        for row in rows:
            if not isinstance(row, dict):
                raise _error("subscription_catalog_invalid")
            if row.get("visibility") != "list":
                continue
            slug, display = row.get("slug"), row.get("display_name")
            if (not isinstance(slug, str) or not SLUG.fullmatch(slug) or slug in slugs
                    or not isinstance(display, str) or not display.strip() or len(display) > 256
                    or any(ord(character) < 32 for character in display)):
                raise _error("subscription_catalog_invalid")
            models.append({"slug": slug, "displayName": display})
            slugs.add(slug)
        revision = hashlib.sha256(_json({"connectionId": self._registry["connectionId"], "models": models})).hexdigest()
        self._models, self._catalog_revision = models, revision
        self._status, self._last_error = "connected" if models else "no_models", None

    def refresh_catalog(self):
        self._initialize()
        with self._lock:
            if self._auth_busy or (self._pending and time.monotonic() < self._pending["deadline"]) or self._processing:
                raise _error("subscription_busy")
            self._auth_busy = True
            try:
                self._refresh_catalog_locked()
            except Exception as error:
                self._models, self._catalog_revision = [], None
                self._last_error = _code(error)
                if self._status != "reauth_required":
                    self._status = "catalog_failed"
                raise _error(self._last_error) from None
            finally:
                self._auth_busy = False
                self._release_if_closed()
            return self.get_status()

    def disconnect(self):
        self._initialize()
        with self._lock:
            if not self._store_available:
                raise _error(self._last_error or "subscription_store_unavailable")
            connection = self._connection
            self._active = False
            self._pending = None
            self._models, self._catalog_revision = [], None
            self._status, self._last_error = "disconnected", None
            self._connection = None
            try:
                self._registry["enabled"] = False
                _atomic(self._registry_path, _json(self._registry))
                if self._credential_path.exists():
                    self._credential_path.unlink()
            except OSError:
                self._status, self._last_error = "disconnected_cleanup_failed", "subscription_disconnect_persistence_failed"
                raise _error(self._last_error, "当前连接已停用，但本机退出状态未完整保存；请核对后再登录。") from None
            if connection and connection.get("refreshToken"):
                try:
                    document = self._request(DISCOVERY)
                    endpoint = document.get("revocation_endpoint")
                    if document.get("issuer") != ISSUER or not _revocation_url(endpoint):
                        raise _error("subscription_revocation_endpoint_invalid")
                    self._request(endpoint, form={"token": connection["refreshToken"],
                        "token_type_hint": "refresh_token", "client_id": connection["clientId"]}, revoke=True)
                except Exception:
                    self._last_error = "subscription_remote_revocation_unconfirmed"
                    self._status = "disconnected_revocation_unconfirmed"
            # Registration/account binding is retained. Original jobs/results are untouched.
            return self.get_status()

    def start(self):
        self._initialize()
        with self._lifecycle_lock:
            with self._queue_lock:
                running = self._worker is not None and self._worker.is_alive()
                if self._stopping.is_set():
                    raise _error("subscription_closed")
            if running or not self._store_available:
                return self.get_status()
            self.service.register_dispatch_notifier(self)
            with self._queue_lock:
                self._worker = threading.Thread(target=self._work, name="console-subscription-events", daemon=True)
                self._worker.start()
        return self.get_status()

    def notify_committed(self, dispatch_ids):
        with self._queue_lock:
            if self._stopping.is_set():
                return
            for identifier in dispatch_ids:
                if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier) or identifier in self._seen:
                    continue
                if self._queue.full():
                    # Accepted DB rows remain pending/reviewable; never infer or replay them.
                    continue
                self._seen.add(identifier)
                self._queue.put_nowait(identifier)

    def notify_released(self, dispatch_ids):
        with self._queue_lock:
            self._released.update(identifier for identifier in dispatch_ids if isinstance(identifier, str)
                                  and re.fullmatch(r"[a-f0-9]{32}", identifier))

    def _cancelled(self, identifier):
        with self._queue_lock:
            return self._stopping.is_set() or identifier in self._released

    def _work(self):
        try:
            while not self._stopping.is_set():
                identifier = self._queue.get()
                if identifier is None:
                    break
                if not self._cancelled(identifier):
                    self._process(identifier)
        finally:
            self._release_if_closed()

    def _process(self, identifier):
        prepared, intent, wire_started = None, False, False
        with self._lock:
            self._processing = True
        try:
            prepared = self.service.subscription_claim(identifier, None)
            if prepared is None:  # An old/browser/native dispatch is intentionally ignored.
                return
            binding = prepared.get("subscription")
            self._check_binding(binding)
            if self._cancelled(identifier):
                raise _error("subscription_cancelled_before_send")
            inputs = build_input(prepared)
            token = self.credential_token(binding)
            if self._cancelled(identifier):
                raise _error("subscription_cancelled_before_send")
            intent = True  # Even an ambiguous intent-write acknowledgement forbids resending.
            recorded = self.service.subscription_send_intent(identifier, prepared["claimToken"], binding)
            if not isinstance(recorded, dict) or recorded.get("sendIntentRecorded") is not True:
                raise _error("subscription_send_intent_unconfirmed")
            self._check_binding(binding)
            if self._cancelled(identifier):
                raise _error("subscription_cancelled_before_send")
            runner = self._runner
            if runner is None:
                from workflow_subscription_stream import run_response
                runner = run_response
            wire_started = True
            receipt = runner(token, binding["modelSlug"], inputs)
            if not isinstance(receipt, dict):
                raise _error("subscription_receipt_invalid")
            success = (receipt.get("ok") is True and receipt.get("responseCompleted") is True
                       and receipt.get("terminalEventObserved") is True and receipt.get("terminalStatus") == "completed"
                       and receipt.get("completionEvidence") == "response.completed"
                       and receipt.get("providerErrorObserved") is False and receipt.get("actualModel") == binding["modelSlug"]
                       and isinstance(receipt.get("output"), str) and bool(receipt["output"].strip())
                       and len(receipt["output"]) <= 128 * 1024)
            if success:
                self.service.subscription_complete(identifier, prepared["claimToken"], receipt)
            else:
                if receipt.get("ok") is True:
                    receipt = {**receipt, "ok": False, "status": "unknown", "code": "subscription_result_mismatch", "retryAllowed": False}
                self.service.subscription_fail(identifier, prepared["claimToken"], receipt)
        except Exception as error:
            # Failure of the one call or its final DB write is never a reason to send again.
            receipt = {"ok": False, "status": "unknown" if intent else "failed", "code": _code(error),
                       "retryAllowed": False, "requestSent": wire_started}
            try:
                self.service.subscription_fail(identifier, prepared.get("claimToken") if isinstance(prepared, dict) else None, receipt)
            except Exception:
                pass  # Durable claim/intent remains for explicit review on restart.
        finally:
            with self._lock:
                self._processing = False

    def _release_if_closed(self):
        if not self._stopping.is_set() or not self._lock.acquire(blocking=False):
            return
        try:
            worker = self._worker
            if (not self._auth_busy and not self._processing
                    and (worker is None or not worker.is_alive() or worker is threading.current_thread())
                    and self._process_file is not None and not self._process_file.closed):
                self._process_file.close()
        finally:
            self._lock.release()

    def close(self):
        with self._lifecycle_lock:
            self._stopping.set()
            self.service.unregister_dispatch_notifier(self)
        with self._queue_lock:
            if not self._queue.full():
                self._queue.put_nowait(None)
        if self._callback_server is not None:
            self._callback_server.shutdown()
            self._callback_server.server_close()
        worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=2)
        self._release_if_closed()

    stop = close


SubscriptionBroker = WorkflowSubscription
