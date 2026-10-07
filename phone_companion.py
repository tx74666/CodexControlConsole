"""Explicitly enabled, limited same-Wi-Fi companion for Codex Console.

This server is separate from the desktop control server. It never forwards
requests, selects a library, or exposes an arbitrary file. Paired phones can
submit work only through the computer's explicitly configured project permissions.
PIN sessions are temporary; explicitly remembered phones use hashed local credentials.
"""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import nullcontext
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import ipaddress
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import stat
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from workspace_plan import MAX_PLAN_BYTES, normalize_actual_plan
from transfer_store import TransferError, read_transfer_request, send_transfer_attachment
from phone_device_store import DeviceStoreError, REMEMBER_TTL, TOKEN_PATTERN
from phone_discovery import discover_lan_interfaces
from workflow_service import WorkflowError
from workflow_models import WorkflowModelError
from workflow_http import workflow_get, workflow_post, workflow_import_idea, workflow_upload_dialogue, send_workflow_events
from resource_library import ResourceLibraryError, ResourceLibraryConflict
from resource_preview import ResourcePreviewError
from resource_http import resource_get, resource_post


PAIR_TTL = 300
SESSION_TTL = 8 * 60 * 60
MAX_BODY = 4096
MAX_ASSET = 2 * 1024 * 1024
MAX_MUSIC_TRACKS = 2000
MAX_LYRICS_BYTES = 256 * 1024
MUSIC_CACHE_TTL = 15
AUDIO_CHUNK_BYTES = 64 * 1024
AUDIO_TYPES = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4",
               ".aac": "audio/aac", ".flac": "audio/flac", ".ogg": "audio/ogg", ".opus": "audio/ogg"}
COOKIE_NAME = "codex_phone_session"
REMEMBER_COOKIE_NAME = "codex_phone_device"
PLAN_SYNC_PREFIX = "/api/phone/plan-sync/"
PLAN_SYNC_ORIGIN = "https://tx74666.github.io"
NETWORK_WARNING = "只在你信任的同一 Wi-Fi 内使用。当前连接未加密；电脑关闭、休眠或关闭手机入口后不能访问。"
ASSETS = {
    "/": "mobile.html", "/mobile.html": "mobile.html",
    "/resources.html": "resources.html", "/resources.js": "resources.js", "/resources.css": "resources.css",
    "/mobile.css": "mobile.css", "/mobile.js": "mobile.js",
    "/mobile-dialogue.js": "mobile-dialogue.js", "/mobile-dialogue.css": "mobile-dialogue.css",
    "/mobile-handoff.js": "mobile-handoff.js",
    "/transfer-panel.js": "transfer-panel.js", "/transfer-panel.css": "transfer-panel.css",
    "/workflow-panel.js": "workflow-panel.js", "/workflow-panel.css": "workflow-panel.css",
    "/codex-work-panel.js": "codex-work-panel.js", "/codex-work-panel.css": "codex-work-panel.css",
    "/incubator-panel.js": "incubator-panel.js", "/incubator-panel.css": "incubator-panel.css",
    "/conversations-panel.js": "conversations-panel.js", "/conversations-panel.css": "conversations-panel.css",
    "/mobile.webmanifest": "mobile.webmanifest",
    "/phone/phone-icon-180.png": "phone/phone-icon-180.png",
    "/phone/phone-icon-192.png": "phone/phone-icon-192.png",
    "/phone/phone-icon-512.png": "phone/phone-icon-512.png",
    "/codex-resource-icon-32.png": "codex-resource-icon-32.png",
    "/codex-resource-icon-128.png": "codex-resource-icon-128.png",
    "/codex-resource-icon-256.png": "codex-resource-icon-256.png",
}
_LAN_NETWORKS = tuple(ipaddress.ip_network(value) for value in
                      ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def is_lan_address(value):
    try:
        address = ipaddress.ip_address(value)
        return isinstance(address, ipaddress.IPv4Address) and any(address in item for item in _LAN_NETWORKS)
    except (ValueError, TypeError):
        return False


class PhoneRequestError(ValueError):
    def __init__(self, message, status=400, headers=None):
        super().__init__(message)
        self.status = status
        self.headers = headers or {}


class _PhoneServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, companion):
        self.companion = companion
        self._slots = threading.BoundedSemaphore(8)
        # Long-lived result subscriptions leave four normal request slots free.
        self._workflow_event_slots = threading.BoundedSemaphore(4)
        super().__init__(address, _PhoneHandler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(5)
        return connection, address

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class _PhoneHandler(BaseHTTPRequestHandler):
    server_version = "CodexPhone"
    sys_version = ""
    protocol_version = "HTTP/1.0"

    def log_message(self, format, *args):
        # Do not retain pairing attempts, cookies or personal document paths.
        return

    def _send(self, payload, status=200, content_type="application/json; charset=utf-8", cookie=None, headers=None):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        # Same-origin POSTs need their real Origin for the CSRF check. Browsers
        # serialize it as null under no-referrer with fetch mode same-origin.
        # Cross-origin links still receive no Referer with this policy.
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            for value in cookie if isinstance(cookie, (list, tuple)) else [cookie]:
                self.send_header("Set-Cookie", value)
        if getattr(self, "_plan_sync_cors", False):
            self.send_header("Access-Control-Allow-Origin", PLAN_SYNC_ORIGIN)
            self.send_header("Vary", "Origin")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _context(self, post=False):
        companion = self.server.companion
        if not is_lan_address(self.client_address[0]):
            raise PhoneRequestError("只允许同一局域网设备访问。", 403)
        hosts = self.headers.get_all("Host", [])
        if len(hosts) != 1 or hosts[0] not in companion.authorities:
            raise PhoneRequestError("访问地址不匹配，请使用电脑显示的手机地址。", 403)
        navigation = (not post and self.command in {"GET", "HEAD"}
                      and urlsplit(self.path).path in {"/", "/mobile.html"}
                      and self.headers.get_all("Sec-Fetch-Mode", []) == ["navigate"]
                      and self.headers.get_all("Sec-Fetch-Dest", []) == ["document"])
        if not navigation and any(value.strip().casefold() == "cross-site"
               for header in self.headers.get_all("Sec-Fetch-Site", []) for value in header.split(",")):
            raise PhoneRequestError("不允许跨网站请求。", 403)
        origins = self.headers.get_all("Origin", [])
        if origins and (len(origins) != 1 or origins[0] != "http://" + hosts[0]):
            raise PhoneRequestError("请求来源不匹配。", 403)
        if post and (len(origins) != 1 or origins[0] != "http://" + hosts[0]
                     or self.headers.get_all("X-Codex-Phone", []) != ["1"]):
            raise PhoneRequestError("请从手机入口提交操作。", 403)
        if not companion.enabled:
            raise PhoneRequestError("电脑上的手机入口已关闭。", 503)
        return companion

    def _plan_sync_context(self, preflight=False):
        """A narrow, independently authenticated exception for the phone PWA."""
        companion = self.server.companion
        if not is_lan_address(self.client_address[0]):
            raise PhoneRequestError("只允许同一局域网设备访问。", 403)
        hosts = self.headers.get_all("Host", [])
        if len(hosts) != 1 or hosts[0] not in companion.authorities:
            raise PhoneRequestError("访问地址不匹配，请使用电脑显示的同步地址。", 403)
        if self.headers.get_all("Origin", []) != [PLAN_SYNC_ORIGIN]:
            raise PhoneRequestError("只允许已发布的手机版请求计划同步。", 403)
        if not preflight and self.headers.get_all("X-Codex-Phone", []) != ["1"]:
            raise PhoneRequestError("请从手机版提交计划同步请求。", 403)
        self._plan_sync_cors = True
        if not companion.enabled:
            raise PhoneRequestError("电脑上的手机入口已关闭。", 503)
        return companion

    def _bearer(self):
        values = self.headers.get_all("Authorization", [])
        if len(values) != 1 or not re.fullmatch(r"Bearer [A-Za-z0-9_-]{40,80}", values[0]):
            raise PhoneRequestError("请先使用电脑显示的配对码连接。", 401)
        return values[0][7:]

    def do_OPTIONS(self):
        self._plan_sync_cors = False
        try:
            parsed = urlsplit(self.path)
            if parsed.query or parsed.path not in {PLAN_SYNC_PREFIX + name for name in ("pair", "plan", "logout")}:
                raise PhoneRequestError("手机入口没有此功能。", 404)
            self._plan_sync_context(preflight=True)
            methods = self.headers.get_all("Access-Control-Request-Method", [])
            expected = "GET" if parsed.path.endswith("/plan") else "POST"
            if methods != [expected]:
                raise PhoneRequestError("计划同步请求方式无效。", 403)
            requested = self.headers.get_all("Access-Control-Request-Headers", [])
            if len(requested) != 1 or len(requested[0]) > 512:
                raise PhoneRequestError("计划同步请求头无效。", 403)
            names = {value.strip().lower() for value in requested[0].split(",")}
            if "x-codex-phone" not in names or names - {"x-codex-phone", "content-type", "authorization"}:
                raise PhoneRequestError("计划同步请求头无效。", 403)
            private_network = self.headers.get_all("Access-Control-Request-Private-Network", [])
            if private_network and private_network != ["true"]:
                raise PhoneRequestError("计划同步网络请求无效。", 403)
            self._send(b"", 204, headers={
                "Access-Control-Allow-Methods": "GET, POST",
                "Access-Control-Allow-Headers": "X-Codex-Phone, Content-Type, Authorization",
                "Access-Control-Allow-Private-Network": "true",
                "Access-Control-Max-Age": "300",
            })
        except PhoneRequestError as error:
            self._send({"error": str(error)}, error.status)

    def _body(self, maximum=MAX_BODY):
        if self.headers.get("Transfer-Encoding"):
            raise PhoneRequestError("不支持此请求格式。")
        lengths = self.headers.get_all("Content-Length", [])
        try:
            if len(lengths) != 1:
                raise ValueError()
            size = int(lengths[0])
        except ValueError:
            raise PhoneRequestError("请求长度无效。")
        if not 0 <= size <= maximum:
            raise PhoneRequestError("请求内容过大。", 413)
        if self.headers.get_content_type() != "application/json":
            raise PhoneRequestError("请使用 JSON 请求。", 415)
        try:
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError()
            body = json.loads(raw.decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError()
            return body
        except (ValueError, UnicodeError):
            raise PhoneRequestError("请求内容无效。")

    def _token(self):
        raw = self.headers.get("Cookie", "")
        if len(raw) > 2048:
            return ""
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
            if REMEMBER_COOKIE_NAME in cookie:
                return "device:" + cookie[REMEMBER_COOKIE_NAME].value
            return cookie[COOKIE_NAME].value if COOKIE_NAME in cookie else ""
        except Exception:
            return ""

    def do_GET(self):
        self._plan_sync_cors = False
        try:
            parsed = urlsplit(self.path)
            if parsed.path.startswith(PLAN_SYNC_PREFIX):
                companion = self._plan_sync_context()
                if self.command != "GET" or parsed.query:
                    raise PhoneRequestError("计划同步请求地址或方式无效。", 400)
                token = self._bearer()
                session = companion.session(token, self.client_address[0], scope="plan-sync")
                if parsed.path != PLAN_SYNC_PREFIX + "plan":
                    raise PhoneRequestError("手机入口没有此功能。", 404)
                snapshot = companion.plan_snapshot(session)
                companion.session(token, self.client_address[0], scope="plan-sync")
                self._send(snapshot)
                return
            companion = self._context()
            if parsed.path in ASSETS:
                content, content_type = companion.asset(parsed.path)
                self._send(content, content_type=content_type)
                return
            if parsed.path == "/api/phone/status":
                token = self._token()
                if not companion.is_paired(token, self.client_address[0]):
                    self._send({"paired": False})
                else:
                    session = companion.session(token, self.client_address[0])
                    result = {"paired": True, "version": companion.version}
                    if session.get("remembered"):
                        result.update({"remembered": True,
                                       "connectionUrl": companion.connection_url})
                    self._send(result)
                return
            session = companion.session(self._token(), self.client_address[0])
            if parsed.path.startswith("/api/phone/resources/"):
                if companion.resource_service is None:
                    raise PhoneRequestError("电脑端资源库尚未更新。", 503)
                result = resource_get(companion.resource_service, parsed.path.removeprefix("/api/phone/resources/"), parsed.query)
                companion.session(self._token(), self.client_address[0])
                self._send(result)
                return
            if parsed.path.startswith("/api/phone/workflow/"):
                if companion.workflow_service is None:
                    raise PhoneRequestError("电脑端工作组件尚未更新。", 503)
                token, peer = self._token(), self.client_address[0]
                authorize = lambda: companion.session(token, peer)
                action = parsed.path.removeprefix("/api/phone/workflow/")
                if action == "mobile/dialogue/events":
                    send_workflow_events(self, companion.workflow_service, parsed.query, authorize=authorize)
                elif action == "attachment":
                    with companion.workflow_service.read_attachment(parsed.query, authorize=authorize) as item:
                        send_transfer_attachment(self, item, authorize=authorize)
                else:
                    result = workflow_get(companion.workflow_service, action, parsed.query, prefix="/api/phone/workflow", authorize=authorize)
                    authorize()
                    self._send(result)
            elif parsed.path.startswith("/api/phone/transfer/"):
                if companion.transfer_store is None:
                    raise PhoneRequestError("电脑端互传组件尚未更新。", 503)
                token, peer = self._token(), self.client_address[0]
                authorize = lambda: companion.session(token, peer)
                if parsed.path == "/api/phone/transfer/messages":
                    result = companion.transfer_store.list(parsed.query, prefix="/api/phone/transfer")
                    authorize()
                    self._send(result)
                elif parsed.path == "/api/phone/transfer/attachment":
                    with companion.transfer_store.read_attachment(parsed.query, authorize=authorize) as item:
                        send_transfer_attachment(self, item, authorize=authorize)
                else:
                    raise PhoneRequestError("手机入口没有此功能。", 404)
            elif parsed.path == "/api/phone/dashboard":
                self._send(companion.dashboard(session))
            elif parsed.path == "/api/phone/plan":
                if parsed.query:
                    raise PhoneRequestError("请求地址无效。")
                snapshot = companion.plan_snapshot(session)
                companion.session(self._token(), self.client_address[0])
                self._send(snapshot)
            elif parsed.path == "/api/phone/document":
                query = parse_qs(parsed.query, keep_blank_values=True)
                if set(query) != {"path"} or len(query["path"]) != 1:
                    raise PhoneRequestError("文件路径无效。")
                self._send(companion.document(session, query["path"][0]))
            elif parsed.path == "/api/phone/music":
                if parsed.query:
                    raise PhoneRequestError("请求地址无效。")
                self._send(companion.music_playlist(session, refresh=True))
            elif parsed.path in ("/api/phone/music/audio", "/api/phone/music/lyrics"):
                query = parse_qs(parsed.query, keep_blank_values=True)
                allowed = {"path"} if parsed.path.endswith("/audio") else {"path", "language"}
                if ("path" not in query or set(query) - allowed
                        or any(len(values) != 1 for values in query.values())):
                    raise PhoneRequestError("音乐路径无效。")
                if parsed.path.endswith("/audio"):
                    self._send_audio(companion, session, query["path"][0])
                else:
                    self._send(companion.music_lyrics(session, query["path"][0], query.get("language", [""])[0]))
            else:
                raise PhoneRequestError("手机入口没有此功能。", 404)
        except PhoneRequestError as error:
            self._send({"error": str(error)}, error.status, headers=error.headers)
        except (TransferError, DeviceStoreError, WorkflowError, WorkflowModelError) as error:
            self._send({"error": str(error), "code": getattr(error, "code", "invalid_request")}, error.status)
        except (ValueError, OSError, RuntimeError, sqlite3.Error):
            self._send({"error": "暂时无法读取，请回到电脑检查资料库。"}, 400)

    def do_HEAD(self):
        # Safari probes media with HEAD and short Range GETs. Use precisely the
        # same authentication and path checks, suppressing the response body.
        self.do_GET()

    def _send_audio(self, companion, session, path):
        target = companion.music_file(session, path)
        with target.open("rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise PhoneRequestError("音乐文件不可播放。", 404)
            size = info.st_size
            ranges = self.headers.get_all("Range", [])
            start, end, status = audio_range(ranges, size)
            token, peer = self._token(), self.client_address[0]
            # Recheck after the local file was opened, before sending headers.
            companion.session(token, peer)
            self.send_response(status)
            self.send_header("Content-Type", AUDIO_TYPES[target.suffix.lower()])
            self.send_header("Content-Length", str(max(0, end - start + 1)))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if self.command == "HEAD":
                return
            remaining = end - start + 1
            try:
                source.seek(start)
                while remaining > 0 and companion.is_paired(token, peer):
                    chunk = source.read(min(AUDIO_CHUNK_BYTES, remaining))
                    if not chunk:
                        return
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            except (OSError, BrokenPipeError, ConnectionResetError):
                # A stopped/revoked session terminates the stream; never append
                # an error body to an audio response or leave a background job.
                return

    def do_POST(self):
        self._plan_sync_cors = False
        try:
            parsed = urlsplit(self.path)
            if parsed.path.startswith(PLAN_SYNC_PREFIX):
                companion = self._plan_sync_context()
                if parsed.query:
                    raise PhoneRequestError("计划同步请求地址无效。")
                if parsed.path == PLAN_SYNC_PREFIX + "pair":
                    body = self._body()
                    if set(body) != {"code"}:
                        raise PhoneRequestError("请输入电脑显示的配对码。")
                    token = companion.pair(body["code"], self.client_address[0], scope="plan-sync")
                    self._send({"paired": True, "token": token, "expiresIn": SESSION_TTL,
                                "computerId": companion.computer_id, "version": companion.version})
                    return
                token = self._bearer()
                companion.session(token, self.client_address[0], scope="plan-sync")
                if parsed.path != PLAN_SYNC_PREFIX + "logout":
                    raise PhoneRequestError("手机入口没有此功能。", 404)
                if self._body():
                    raise PhoneRequestError("请求内容无效。")
                companion.logout(token)
                self._send({"paired": False})
                return
            companion = self._context(post=True)
            if parsed.query:
                raise PhoneRequestError("请求地址无效。")
            if parsed.path.startswith("/api/phone/resources/"):
                token, peer = self._token(), self.client_address[0]
                authorize = lambda: companion.session(token, peer)
                authorize()
                if companion.resource_service is None:
                    raise PhoneRequestError("电脑端资源库尚未更新。", 503)
                result = resource_post(companion.resource_service,
                    parsed.path.removeprefix("/api/phone/resources/"), self._body(maximum=128 * 1024), authorize=authorize)
                authorize()
                self._send(result)
                return
            if parsed.path.startswith("/api/phone/workflow/"):
                token, peer = self._token(), self.client_address[0]
                authorize = lambda: companion.session(token, peer)
                authorize()
                if companion.workflow_service is None:
                    raise PhoneRequestError("电脑端工作组件尚未更新。", 503)
                action = parsed.path.removeprefix("/api/phone/workflow/")
                if action == "upload":
                    with read_transfer_request(self.headers, self.rfile, allowed_fields={"requestId", "recordId"}) as (fields, files):
                        authorize()
                        result = companion.workflow_service.upload(fields, files, prefix="/api/phone/workflow", authorize=authorize)
                elif action == "mobile/dialogue/upload":
                    with read_transfer_request(self.headers, self.rfile, allowed_fields={"requestId", "recordId", "text"}) as (fields, files):
                        authorize()
                        result = workflow_upload_dialogue(companion.workflow_service, fields, files, prefix="/api/phone/workflow", authorize=authorize)
                elif action == "mobile/idea/import":
                    with read_transfer_request(self.headers, self.rfile, allowed_fields={"requestId", "text"}) as (fields, files):
                        authorize()
                        result = workflow_import_idea(companion.workflow_service, fields, files, prefix="/api/phone/workflow", authorize=authorize)
                elif action in {"create", "message", "submit", "discuss", "transcribe", "retry", "task-record", "app-work", "app-work/end",
                                "codex-work/review", "codex-work/submit", "codex-work/cancel", "codex-work/setup", "codex-work/workspaces",
                                "incubator/create", "incubator/update", "incubator/publish", "incubator/refinement/pause", "conversations/request",
                                "mobile/dialogue/open", "mobile/dialogue/draft", "mobile/dialogue/clear", "mobile/dialogue/send",
                                "mobile/dialogue/cancel-pending",
                                "mobile/dialogue/save", "mobile/dialogue/remember", "mobile/idea/update", "mobile/idea/archive", "mobile/idea/split", "mobile/idea/merge", "mobile/idea/import-status"}:
                    # This read-only lookup wraps the exact frozen manifest in
                    # JSON, whose escaping can double its bounded 80 KB text.
                    maximum = 192 * 1024 if action == "mobile/idea/import-status" else 128 * 1024
                    body = self._body(maximum=maximum)
                    authorize()
                    result = workflow_post(companion.workflow_service, action, body, prefix="/api/phone/workflow", authorize=authorize)
                else:
                    raise PhoneRequestError("手机入口没有此功能。", 404)
                authorize()
                self._send(result)
                return
            if parsed.path == "/api/phone/transfer/messages":
                token, peer = self._token(), self.client_address[0]
                companion.session(token, peer)
                if companion.transfer_store is None:
                    raise PhoneRequestError("电脑端互传组件尚未更新。", 503)
                with read_transfer_request(self.headers, self.rfile) as (fields, files):
                    self._send(companion.transfer_store.send(fields, files, "phone",
                        prefix="/api/phone/transfer", authorize=lambda: companion.session(token, peer)))
                return
            body = self._body()
            if parsed.path == "/api/phone/pair":
                if (set(body) - {"code", "qrToken", "remember", "deviceName"}
                        or ("code" in body) == ("qrToken" in body)):
                    raise PhoneRequestError("请输入电脑显示的配对码。")
                token, remembered = companion.pair_phone(body, self.client_address[0])
                cookies = []
                if remembered:
                    cookies.append(companion.remember_cookie(remembered["token"]))
                else:
                    cookies.append(companion.remember_cookie("", max_age=0))
                cookies.append(companion.cookie(token))
                self._send({"paired": True, "remembered": bool(remembered),
                            "expiresIn": REMEMBER_TTL if remembered else SESSION_TTL,
                            "deviceId": remembered["device"]["id"] if remembered else None,
                            "connectionUrl": companion.connection_url, "version": companion.version}, cookie=cookies)
                return
            token = self._token()
            session = companion.session(token, self.client_address[0])
            if parsed.path in {"/api/phone/transfer/star", "/api/phone/transfer/delete", "/api/phone/transfer/clear"}:
                if companion.transfer_store is None:
                    raise PhoneRequestError("电脑端互传组件尚未更新。", 503)
                peer = self.client_address[0]
                self._send(companion.transfer_store.mutate(parsed.path.rsplit("/", 1)[-1], body,
                    prefix="/api/phone/transfer", authorize=lambda: companion.session(token, peer)))
            elif parsed.path == "/api/phone/inbox/move":
                if set(body) != {"id", "status"}:
                    raise PhoneRequestError("阅读状态无效。")
                self._send(companion.move_report(session, body["id"], body["status"]))
            elif parsed.path == "/api/phone/logout":
                if body:
                    raise PhoneRequestError("请求内容无效。")
                companion.logout(token)
                self._send({"paired": False}, cookie=[companion.remember_cookie("", max_age=0), companion.cookie("", max_age=0)])
            else:
                raise PhoneRequestError("手机入口没有此功能。", 404)
        except PhoneRequestError as error:
            self._send({"error": str(error)}, error.status)
        except ResourceLibraryConflict as error:
            self._send({"error": str(error), "code": "revision_conflict"}, 409)
        except (ResourceLibraryError, ResourcePreviewError) as error:
            self._send({"error": str(error)}, getattr(error, "status", 400))
        except (TransferError, DeviceStoreError, WorkflowError, WorkflowModelError) as error:
            self._send({"error": str(error), "code": getattr(error, "code", "invalid_request"),
                **({"queueAccepted": False} if getattr(error, "queueAccepted", None) is False else {})}, error.status)
        except (ValueError, OSError, RuntimeError, sqlite3.Error):
            self._send({"error": "操作未完成，请刷新后重试。"}, 400)


class PhoneCompanionService:
    def __init__(self, document_library, plan_getter, app_dir, version, device_getter=None,
                 *, clock=None, interface_getter=None, music_getter=None,
                 music_file_getter=None, music_lyrics_getter=None, computer_id=None, transfer_store=None,
                 device_store=None, announcer=None, monitor_interval=60, workflow_service=None, resource_service=None):
        self.documents = document_library
        self.plan_getter = plan_getter
        self.device_getter = device_getter or document_library.overview
        self.app_dir = Path(app_dir).resolve()
        self.version = str(version)
        if computer_id is not None and (not isinstance(computer_id, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{16,120}", computer_id)):
            raise ValueError("手机计划来源标识无效。")
        self.computer_id = computer_id or secrets.token_urlsafe(24)
        self._clock = clock or time.monotonic
        self._interface_getter = interface_getter or discover_lan_interfaces
        self._lock = threading.RLock()
        self._server = None
        self._thread = None
        self._host = ""
        self._port = None
        self._code = ""
        self._code_expires = 0
        self._code_failures = 0
        self._attempts = {}
        self._sessions = {}
        self._interface_lock = threading.Lock()
        self._interface_cache = None
        self._interface_checked_at = 0
        self.music_getter = music_getter
        self.music_file_getter = music_file_getter
        self.music_lyrics_getter = music_lyrics_getter
        self.transfer_store = transfer_store
        self.workflow_service = workflow_service
        self.resource_service = resource_service
        self.device_store = device_store
        self.announcer = announcer
        self._network_fingerprint = ""
        self._auto_settings = {"enabled": False}
        self._restore_status = "disabled"
        self._monitor_interval = max(30, monitor_interval)
        self._monitor_stop = threading.Event()
        self._monitor_thread = None
        self._lifecycle_lock = threading.RLock()
        self._qr_token = ""
        self._qr_generation = ""
        self._shutdown_requested = False
        self._music_lock = threading.RLock()
        self._music_cache = None
        self._music_checked_at = 0

    @property
    def enabled(self):
        with self._lock:
            return self._server is not None

    @property
    def authority(self):
        with self._lock:
            return f"{self._host}:{self._port}" if self._server is not None else ""

    @property
    def hostname(self):
        return "codex-" + hashlib.sha256(self.computer_id.encode("utf-8")).hexdigest()[:12] + ".local"

    @property
    def authorities(self):
        with self._lock:
            return {self.authority, f"{self.hostname}:{self._port}"} if self._server is not None else set()

    def _discovery_state(self):
        value = self.announcer.state() if self.announcer is not None else {
            "available": False, "status": "unavailable", "error": "本地发现暂不可用，请使用电脑显示的地址。"}
        return {**value, "hostname": self.hostname}

    @property
    def connection_url(self):
        with self._lock:
            if self._server is None:
                return ""
            authority = f"{self.hostname}:{self._port}" if self._discovery_state().get("available") else self.authority
            return "http://" + authority + "/"

    def _prune(self):
        now = self._clock()
        self._sessions = {key: value for key, value in self._sessions.items() if value["expires"] > now}
        self._attempts = {key: [stamp for stamp in stamps if stamp > now - 60]
                          for key, stamps in self._attempts.items() if any(stamp > now - 60 for stamp in stamps)}
        if self._code and self._code_expires <= now:
            self._code = ""
            self._qr_token = ""

    def state(self, include_interfaces=True):
        with self._lock:
            self._prune()
            try:
                devices = self.device_store.list() if self.device_store else []
                device_error = ""
            except (DeviceStoreError, OSError, sqlite3.Error):
                devices, device_error = [], "设备信任记录暂不可用，请稍后重试。"
            remaining = max(0, self._code_expires - self._clock()) if self._code else 0
            result = {"enabled": self._server is not None, "host": self._host, "port": self._port,
                      "url": "http://" + self.authority + "/" if self._server is not None else "",
                      "pairingCode": self._code,
                      "pairingExpiresAt": datetime.fromtimestamp(time.time() + remaining, timezone.utc).isoformat() if remaining else None,
                      "pairingExpiresIn": int(remaining), "pairedCount": len(self._sessions),
                      "networkWarning": NETWORK_WARNING, "transport": "http-lan"}
            result.update({"connectionUrl": self.connection_url, "stableUrl": self.connection_url,
                           "qrToken": self._qr_token, "qrGeneration": self._qr_generation,
                           "qrExpiresIn": int(remaining) if self._qr_token else 0,
                           "qrUrl": self.connection_url + "?tab=transfer#qrToken=" + self._qr_token if self._qr_token else "",
                           "ipQrUrl": result["url"] + "?tab=transfer#qrToken=" + self._qr_token if self._qr_token else "",
                           "discovery": self._discovery_state(),
                           "autoRestore": {"enabled": self._auto_settings.get("enabled") is True,
                                           "networkAvailable": bool(self._network_fingerprint), "status": self._restore_status,
                                           "error": "当前网络标识暂不可用；当前入口可临时使用，下次需手动开启。" if self._server is not None and not self._network_fingerprint else ""},
                           "rememberedDevices": devices, "deviceTrustError": device_error})
        if include_interfaces:
            result["availableInterfaces"] = self._available_interfaces()
        return result

    def _available_interfaces(self, force=False):
        # The Windows adapter inventory is relatively slow. Status polling must
        # not repeatedly scan it; an explicit start always revalidates the bind.
        with self._interface_lock:
            if force or self._interface_cache is None or self._clock() - self._interface_checked_at >= 60:
                self._interface_cache = self._interface_getter()
                self._interface_checked_at = self._clock()
            return [dict(item) for item in self._interface_cache if isinstance(item, dict)]

    def start(self, host=None, port=8899):
        with self._lifecycle_lock:
            self._shutdown_requested = False
            return self._start(host, port)

    def _start(self, host=None, port=8899, *, persist=True):
        interfaces = self._available_interfaces(force=True)
        addresses = [item.get("address") for item in interfaces if isinstance(item, dict) and is_lan_address(item.get("address", ""))]
        host = host or (addresses[0] if addresses else "")
        if host not in addresses or not is_lan_address(host):
            raise ValueError("没有可用的 Wi-Fi / Ethernet 地址，请先将电脑接入同一 Wi-Fi。")
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError("手机入口端口无效。")
        selected = next((item for item in interfaces if item.get("address") == host), {})
        fingerprint = selected.get("fingerprint", "")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
            fingerprint = ""
        if not persist and fingerprint != self._auto_settings.get("fingerprint"):
            raise ValueError("当前物理网络与已设置的网络不同。")
        with self._lock:
            if self._server is not None:
                if self._host != host:
                    raise ValueError("请先关闭手机入口，再切换网络地址。")
                return self.state(include_interfaces=False)
            try:
                server = _PhoneServer((host, port), self)
            except OSError as error:
                raise ValueError("无法开启手机入口，地址已变化或端口正被使用。") from error
            self._server, self._host, self._port = server, host, server.server_address[1]
            self._network_fingerprint = fingerprint
            self._sessions.clear()
            self._attempts.clear()
            self._new_code()
            self._thread = threading.Thread(target=server.serve_forever, name="console-phone-companion", daemon=True)
            self._thread.start()
        try:
            if self.announcer is not None:
                self.announcer.start(self.hostname, host, self._port, self.version)
            if persist and self.device_store:
                self._auto_settings = {"enabled": True, "fingerprint": self._network_fingerprint, "port": self._port} if self._network_fingerprint else {"enabled": False}
                self.device_store.save_settings(self._auto_settings)
        except (ValueError, OSError, RuntimeError, sqlite3.Error):
            self._close_listener()
            raise
        self._restore_status = "connected" if self._auto_settings.get("enabled") else "manual"
        if self._auto_settings.get("enabled"):
            self._ensure_monitor()
        return self.state(include_interfaces=False)

    def _new_code(self):
        self._code = f"{secrets.randbelow(1000000):06d}"
        self._code_expires = self._clock() + PAIR_TTL
        self._code_failures = 0
        self._qr_token = secrets.token_urlsafe(32)
        self._qr_generation = secrets.token_hex(16)

    def renew_pairing(self):
        with self._lock:
            if self._server is None:
                raise ValueError("请先开启手机入口。")
            self._new_code()
        return self.state(include_interfaces=False)

    def stop(self):
        with self._lifecycle_lock:
            self._monitor_stop.set()
            self._auto_settings = {"enabled": False}
            if self.device_store:
                self.device_store.save_settings(self._auto_settings)
            self._restore_status = "disabled"
            return self._close_listener()

    def _close_listener(self):
        with self._lock:
            server, thread = self._server, self._thread
            self._server = self._thread = None
            self._host, self._port = "", None
            self._code = ""
            self._qr_token = ""
            self._network_fingerprint = ""
            self._sessions.clear()
            self._attempts.clear()
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3)
        if self.announcer is not None:
            self.announcer.stop()
        return self.state(include_interfaces=False)

    def shutdown(self):
        """Process exit preserves only the explicit same-network start setting."""
        self._monitor_stop.set()
        with self._lifecycle_lock:
            self._shutdown_requested = True
            self._monitor_stop.set()
            result = self._close_listener()
        thread = self._monitor_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
        return result

    def _ensure_monitor(self):
        if self._monitor_thread is not None and self._monitor_thread.is_alive() and not self._monitor_stop.is_set():
            return
        self._monitor_stop = threading.Event()
        event = self._monitor_stop
        def watch():
            while not event.wait(self._monitor_interval):
                try:
                    self.check_network()
                except (ValueError, OSError, RuntimeError, sqlite3.Error):
                    self._restore_status = "unavailable"
        self._monitor_thread = threading.Thread(target=watch, name="console-phone-network", daemon=True)
        self._monitor_thread.start()

    def restore(self):
        if not self.device_store:
            return self.state(False)
        with self._lifecycle_lock:
            if self._shutdown_requested:
                return self.state(False)
            self._auto_settings = self.device_store.settings()
            if self._auto_settings.get("enabled"):
                self._ensure_monitor()
                self.check_network()
        return self.state(False)

    def check_network(self):
        """One slow physical-interface read per minute, never a subnet scan."""
        with self._lifecycle_lock:
            if self._shutdown_requested or not self._auto_settings.get("enabled") or self._monitor_stop.is_set():
                return
            interfaces = self._available_interfaces(force=True)
            selected = next((item for item in interfaces if item.get("fingerprint") == self._auto_settings.get("fingerprint")
                             and is_lan_address(item.get("address", ""))), None)
            if selected is None:
                self._close_listener()
                self._restore_status = "waiting-for-approved-network"
                return
            if self.enabled and self._host == selected["address"]:
                return
            self._close_listener()
            try:
                self._start(selected["address"], self._auto_settings["port"], persist=False)
                self._restore_status = "connected"
            except (ValueError, OSError, RuntimeError):
                self._restore_status = "unavailable"

    def forget_devices(self, body):
        if not self.device_store or not isinstance(body, dict) or (set(body) != {"id"} and body != {"all": True}):
            raise PhoneRequestError("设备移除请求无效。")
        with self._lock:
            self.device_store.revoke(body.get("id"), all_devices=body.get("all") is True)
            self._sessions = {key: item for key, item in self._sessions.items() if not item.get("deviceId")
                              or (not body.get("all") and item["deviceId"] != body.get("id"))}
        return self.state(False)

    def pair(self, code, peer, *, scope="phone", qr_token=None, remembered=None):
        if scope not in ("phone", "plan-sync"):
            raise PhoneRequestError("配对权限无效。", 403)
        with self._lock:
            self._prune()
            if self._server is None or not is_lan_address(peer):
                raise PhoneRequestError("手机入口已关闭或网络不匹配。", 403)
            if len(self._attempts) >= 128 and peer not in self._attempts:
                raise PhoneRequestError("配对尝试过多，请稍后重试。", 429)
            attempts = self._attempts.setdefault(peer, [])
            if len(attempts) >= 5 or sum(len(items) for items in self._attempts.values()) >= 20:
                raise PhoneRequestError("配对尝试过多，请稍后重试。", 429)
            attempts.append(self._clock())
            valid = (isinstance(code, str) and len(code) == 6 and code.isascii() and code.isdigit()
                     and self._code and secrets.compare_digest(code, self._code)) if qr_token is None else (
                         scope == "phone" and isinstance(qr_token, str) and re.fullmatch(r"[A-Za-z0-9_-]{43}", qr_token)
                         and self._qr_token and secrets.compare_digest(qr_token, self._qr_token))
            if not valid:
                self._code_failures += 1
                if self._code_failures >= 8:
                    self._code = ""
                    self._qr_token = ""
                raise PhoneRequestError("配对码错误或已失效，请在电脑上获取新配对码。", 401)
            if len(self._sessions) >= 8:
                raise PhoneRequestError("已配对设备过多，请在电脑上关闭后重新开启手机入口。", 429)
            root = self.documents.state().get("root", "")
            if remembered is not None:
                if scope != "phone" or not self.device_store:
                    raise PhoneRequestError("电脑端暂不能记住设备，请使用临时配对。", 503)
                credential, device = self.device_store.register(root, self._network_fingerprint, remembered["name"])
                remembered.update({"token": credential, "device": device})
            token = secrets.token_urlsafe(32)
            self._sessions[token] = {"expires": self._clock() + SESSION_TTL, "peer": peer,
                                     "root": root, "scope": scope}
            if remembered is not None:
                self._sessions[token].update({"deviceId": device["id"], "remembered": True})
            self._code = ""  # One successful pairing consumes the code.
            self._qr_token = ""
            return token

    def pair_phone(self, body, peer):
        remember = body.get("remember", False)
        name = body.get("deviceName", "我的手机")
        if type(remember) is not bool or not isinstance(name, str) or len(name) > 80 or any(ord(c) < 32 for c in name):
            raise PhoneRequestError("设备名称或记住设置无效。")
        remembered = {"name": name} if remember else None
        token = self.pair(body.get("code"), peer, qr_token=body.get("qrToken"), remembered=remembered)
        return token, remembered

    @staticmethod
    def cookie(token, max_age=SESSION_TTL):
        return f"{COOKIE_NAME}={token}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict"

    @staticmethod
    def remember_cookie(token, max_age=REMEMBER_TTL):
        return f"{REMEMBER_COOKIE_NAME}={token}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict"

    def session(self, token, peer, *, scope="phone"):
        with self._lock:
            if isinstance(token, str) and token.startswith("device:"):
                if scope != "phone" or self._server is None or not is_lan_address(peer) or not self.device_store:
                    raise PhoneRequestError("请先扫码连接电脑。", 401)
                root = self.documents.state().get("root", "")
                try:
                    device = self.device_store.authenticate(token[7:], root, self._network_fingerprint)
                except DeviceStoreError as error:
                    raise PhoneRequestError(str(error), error.status) from error
                return {"root": root, "scope": "phone", "peer": peer, "remembered": True, "deviceId": device["id"]}
            self._prune()
            session = self._sessions.get(token)
            if (self._server is None or not session or session["peer"] != peer
                    or session.get("scope", "phone") != scope):
                raise PhoneRequestError("请先使用电脑显示的配对码连接。", 401)
            if session["root"] != self.documents.state().get("root", ""):
                self._sessions.pop(token, None)
                if session.get("deviceId") and self.device_store:
                    self.device_store.revoke(session["deviceId"])
                raise PhoneRequestError("电脑资料库已切换，请重新配对。", 401)
            if session.get("deviceId") and (not self.device_store or not self.device_store.active(
                    session["deviceId"], session["root"], self._network_fingerprint)):
                self._sessions.pop(token, None)
                raise PhoneRequestError("设备已被移除，请重新扫码连接。", 401)
            return dict(session)

    def is_paired(self, token, peer):
        try:
            self.session(token, peer)
            return True
        except PhoneRequestError:
            return False

    def logout(self, token):
        with self._lock:
            session = self._sessions.pop(token, None)
            if self.device_store:
                if isinstance(token, str) and token.startswith("device:"):
                    self.device_store.revoke(token=token[7:])
                    matched = TOKEN_PATTERN.fullmatch(token[7:])
                    if matched:
                        self._sessions = {key: item for key, item in self._sessions.items() if item.get("deviceId") != matched[1]}
                elif session and session.get("deviceId"):
                    self.device_store.revoke(session["deviceId"])

    def asset(self, path):
        name = ASSETS.get(path)
        if not name:
            raise PhoneRequestError("手机入口没有此文件。", 404)
        requested = self.app_dir / name
        target = requested.resolve()
        if target != requested or self.app_dir not in target.parents or not target.is_file():
            raise PhoneRequestError("手机入口文件缺失，请更新电脑端。", 404)
        with target.open("rb") as source:
            content = source.read(MAX_ASSET + 1)
        if len(content) > MAX_ASSET:
            raise PhoneRequestError("手机入口文件过大。", 413)
        content_type = "application/manifest+json" if name.endswith(".webmanifest") else mimetypes.guess_type(name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or name.endswith(".js"):
            content_type += "; charset=utf-8"
        return content, content_type

    @staticmethod
    def _public(value):
        return {key: item for key, item in value.items() if key != "root"}

    def _catalog(self, root):
        empty = {"guide": {"items": []}, "inbox": {"entries": [], "inboxCount": 0, "laterCount": 0,
                 "archiveCount": 0, "unreadCount": 0, "totalCount": 0}, "references": {"items": []}}
        if not root:
            empty["error"] = "请先在电脑的 Document 选择资料库，再重新配对。"
            return empty
        with self.documents._document_scope(expectedRoot=root):
            for name, getter in (("guide", self.documents.guide), ("inbox", self.documents.inbox),
                                 ("references", self.documents.references)):
                try:
                    empty[name] = self._public(getter(expectedRoot=root))
                except (ValueError, OSError, RuntimeError):
                    empty[name]["error"] = "这部分资料暂不可用，请在电脑上检查。"
        return empty

    @staticmethod
    def _paths(catalog):
        paths = {item["path"] for item in catalog["guide"].get("items", [])}
        paths.update(item["path"] for item in catalog["inbox"].get("entries", []))
        paths.update(variant["path"] for item in catalog["references"].get("items", [])
                     for variant in item.get("variants", []) if variant.get("available"))
        return paths

    def dashboard(self, session):
        scope = self.documents._document_scope(expectedRoot=session["root"]) if session["root"] else nullcontext()
        with scope:
            return self._dashboard_scoped(session)

    def _dashboard_scoped(self, session):
        plan = self.plan_getter()
        if not isinstance(plan, dict):
            plan = {"plan": None, "error": "电脑计划清单暂不可用。"}
        # Only saved actual state includes desktop edits and completion flags.
        # A seed remains an initial list until the desktop saves that state.
        actual_done = plan.get("actualDone") is True
        plan = {"plan": plan.get("plan"), "error": plan.get("error", ""),
                "actualDone": actual_done,
                "label": "电脑已保存的计划与进度" if actual_done else "计划初始清单（实际进度暂未同步，请在电脑保存后同步）"}
        try:
            raw = self.device_getter()
            device = {key: raw.get(key) for key in ("currentMemory", "model", "cpuModel", "gpuModels",
                      "installedMemoryBytes", "sampledAt", "status")}
        except (ValueError, OSError, RuntimeError):
            device = {"currentMemory": {"status": "unavailable"}, "status": "unavailable"}
        return {"version": self.version, "device": device, "plan": plan,
                "documents": self._catalog(session["root"])}

    def plan_snapshot(self, session):
        """Read only saved actual tasks after validating the paired document root."""
        if session["root"] != self.documents.state().get("root", ""):
            raise PhoneRequestError("电脑资料库已切换，请重新配对。", 401)
        scope = self.documents._document_scope(expectedRoot=session["root"]) if session["root"] else nullcontext()
        with scope:
            try:
                payload = self.plan_getter()
                if not isinstance(payload, dict) or payload.get("error") or payload.get("plan") is None:
                    raise ValueError("No current saved plan")
                if payload.get("actualDone") is False:
                    raise PhoneRequestError("请先在电脑打开计划，让实际清单完成保存。手机原有的计划会保留。", 503)
                plan = normalize_actual_plan(payload["plan"])
                # This digest describes exactly the task content sent to phones;
                # source filenames, timestamps and extra fields never enter it.
                canonical = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                if len(canonical) > MAX_PLAN_BYTES:
                    raise ValueError("Current plan exceeds its size limit")
                digest = hashlib.sha256(canonical).hexdigest()
                updated_at = payload.get("updatedAt")
                if not isinstance(updated_at, str) or len(updated_at) > 80:
                    updated_at = datetime.now(timezone.utc).isoformat()
                else:
                    datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                if session["root"] != self.documents.state().get("root", ""):
                    raise PhoneRequestError("电脑资料库已切换，请重新配对。", 401)
                return {"format": "codex-console-plan-snapshot", "schemaVersion": 1,
                        "plan": plan, "hash": digest, "updatedAt": updated_at,
                        "computerId": self.computer_id}
            except PhoneRequestError:
                raise
            except (OSError, ValueError, TypeError, RuntimeError):
                raise PhoneRequestError("电脑计划暂不可用，手机已保存的计划会保留。请在电脑上保存最新计划后重试。", 503)

    def document(self, session, path):
        if not isinstance(path, str) or len(path) > 1024 or path not in self._paths(self._catalog(session["root"])):
            raise PhoneRequestError("只能阅读电脑已登记的重点、报告与参考资料。", 403)
        return self._public(self.documents.read(path, expectedRoot=session["root"]))

    def move_report(self, session, identifier, status):
        if not isinstance(identifier, str) or status not in ("inbox", "later", "archive"):
            raise PhoneRequestError("阅读状态无效。")
        catalog = self._catalog(session["root"])
        if not any(item["id"] == identifier for item in catalog["inbox"].get("entries", [])):
            raise PhoneRequestError("此报告未登记或已被清空，请刷新。", 403)
        return self._public(self.documents.move_report(identifier, status, expectedRoot=session["root"]))

    def _music_catalog(self, refresh=False):
        with self._music_lock:
            if not refresh and self._music_cache is not None and self._clock() - self._music_checked_at < MUSIC_CACHE_TTL:
                return self._music_cache
            raw = self.music_getter() if self.music_getter is not None else []
            tracks = raw.get("tracks", []) if isinstance(raw, dict) else raw
            if not isinstance(tracks, list):
                raise PhoneRequestError("电脑音乐清单暂不可用。", 404)
            normalized, seen = [], set()
            for item in tracks[:MAX_MUSIC_TRACKS]:
                if not isinstance(item, dict):
                    continue
                path = item.get("path")
                if not safe_music_relative(path) or path in seen:
                    continue
                seen.add(path)
                name = item.get("name")
                name = name.strip()[:240] if isinstance(name, str) and name.strip() else Path(path).stem
                languages = []
                options = item.get("lyricsLanguages")
                for option in (options if isinstance(options, list) else [])[:8]:
                    if (isinstance(option, dict) and isinstance(option.get("code"), str)
                            and re.fullmatch(r"[a-z]{2}(?:-[a-z]{2,8})?", option["code"])):
                        languages.append({"code": option["code"], "label": str(option.get("label") or option["code"])[:80]})
                language = item.get("lyricsLanguage", "")
                language = language if isinstance(language, str) and re.fullmatch(r"[a-z]{2}(?:-[a-z]{2,8})?", language) else ""
                normalized.append({"name": name, "path": path, "type": Path(path).suffix.lower()[1:],
                    "tier": item.get("tier") if item.get("tier") in ("first", "second", "third") else "third",
                    "size": item.get("size") if type(item.get("size")) is int and item["size"] >= 0 else 0,
                    "modified": item.get("modified", "")[:120] if isinstance(item.get("modified", ""), str) else "",
                    "lyrics": item.get("lyrics") is True, "lyricsLanguage": language, "lyricsLanguages": languages,
                    "url": "/api/phone/music/audio?" + urlencode({"path": path})})
            self._music_cache = {"tracks": normalized, "truncated": len(tracks) > MAX_MUSIC_TRACKS,
                "playback": "phone", "error": "" if self.music_getter is not None else "电脑端暂未提供音乐清单。"}
            self._music_checked_at = self._clock()
            return self._music_cache

    def music_playlist(self, session, refresh=False):
        return self._music_catalog(refresh=refresh)

    def _registered_music(self, path):
        if not safe_music_relative(path) or not any(item["path"] == path for item in self._music_catalog()["tracks"]):
            raise PhoneRequestError("只能播放电脑音乐清单中已有的歌曲。", 403)

    def music_file(self, session, path):
        self._registered_music(path)
        if self.music_file_getter is None:
            raise PhoneRequestError("电脑端暂未提供音乐播放。", 404)
        try:
            target = Path(self.music_file_getter(path)).resolve()
        except (ValueError, TypeError, OSError, RuntimeError) as error:
            raise PhoneRequestError("音乐文件已移动或无法播放，请刷新清单。", 404) from error
        if target.suffix.lower() not in AUDIO_TYPES or not target.is_file():
            raise PhoneRequestError("音乐文件已移动或无法播放，请刷新清单。", 404)
        return target

    def music_lyrics(self, session, path, language=""):
        self._registered_music(path)
        if not isinstance(language, str) or (language and not re.fullmatch(r"[a-z]{2}(?:-[a-z]{2,8})?", language)):
            raise PhoneRequestError("歌词语言无效。")
        if self.music_lyrics_getter is None:
            raise PhoneRequestError("这首歌没有本地歌词。", 404)
        try:
            target = Path(self.music_lyrics_getter(path, language)).resolve()
        except (ValueError, TypeError, OSError, RuntimeError) as error:
            raise PhoneRequestError("这首歌没有本地歌词。", 404) from error
        if target.suffix.lower() not in (".lrc", ".txt") or not target.is_file():
            raise PhoneRequestError("这首歌没有本地歌词。", 404)
        with target.open("rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise PhoneRequestError("歌词文件不可读取。", 404)
            content = source.read(MAX_LYRICS_BYTES + 1)
        if len(content) > MAX_LYRICS_BYTES:
            raise PhoneRequestError("歌词文件过大，请在电脑端查看。", 413)
        try:
            text = content.decode("utf-8-sig")
        except UnicodeError as error:
            raise PhoneRequestError("本地歌词不是 UTF-8 文字。", 400) from error
        return {"path": path, "content": text, "format": "lrc" if target.suffix.lower() == ".lrc" else "text", "language": language}


def safe_music_relative(value):
    return (isinstance(value, str) and 0 < len(value) <= 1024 and not value.startswith("/")
            and not any(char in value for char in ("\\", ":", "\x00"))
            and not any(ord(char) < 32 for char in value)
            and not any(part in ("", ".", "..") for part in value.split("/"))
            and Path(value).suffix.lower() in AUDIO_TYPES)


def audio_range(ranges, size):
    """Return a single byte interval, including Safari's bytes=0-1 probe."""
    if not ranges:
        return 0, size - 1, 200
    invalid = PhoneRequestError("请求的音频范围无效。", 416, {"Content-Range": f"bytes */{size}", "Accept-Ranges": "bytes"})
    if len(ranges) != 1 or len(ranges[0]) > 128:
        raise invalid
    match = re.fullmatch(r"bytes=(\d{0,20})-(\d{0,20})", ranges[0].strip(), flags=re.IGNORECASE)
    if not match or not any(match.groups()) or size <= 0:
        raise invalid
    first, last = match.groups()
    if not first:
        suffix = int(last)
        if suffix <= 0:
            raise invalid
        return max(0, size - suffix), size - 1, 206
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or end < start:
        raise invalid
    return start, end, 206
