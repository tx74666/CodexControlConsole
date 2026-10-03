"""Explicitly enabled, limited same-Wi-Fi companion for Codex Console.

This server is separate from the desktop control server. It never forwards
requests, selects a library, executes a program, or exposes an arbitrary file.
Pairings exist only in memory and are revoked when the companion is stopped.
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
import subprocess
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from workspace_plan import MAX_PLAN_BYTES, normalize_actual_plan
from transfer_store import TransferError, read_transfer_request, send_transfer_attachment


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
PLAN_SYNC_PREFIX = "/api/phone/plan-sync/"
PLAN_SYNC_ORIGIN = "https://tx74666.github.io"
NETWORK_WARNING = "只在你信任的同一 Wi-Fi 内使用。当前连接未加密；电脑关闭、休眠或关闭手机入口后不能访问。"
ASSETS = {
    "/": "mobile.html", "/mobile.html": "mobile.html",
    "/mobile.css": "mobile.css", "/mobile.js": "mobile.js",
    "/transfer-panel.js": "transfer-panel.js", "/transfer-panel.css": "transfer-panel.css",
    "/mobile.webmanifest": "mobile.webmanifest",
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


def discover_lan_interfaces():
    """Read physical active adapters once; do not choose a VPN or change routing."""
    if os.name != "nt":
        return []
    script = r"""$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$rows = @()
foreach ($adapter in (Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.HardwareInterface })) {
  $config = Get-NetIPConfiguration -InterfaceIndex $adapter.ifIndex
  if (-not $config.IPv4DefaultGateway) { continue }
  foreach ($address in $config.IPv4Address) {
    $rows += [PSCustomObject]@{ address = $address.IPAddress; name = $adapter.Name }
  }
}
ConvertTo-Json -InputObject @($rows) -Compress
"""
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, encoding="utf-8", timeout=12,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            return []
        rows = json.loads(result.stdout.lstrip("\ufeff"))
        if isinstance(rows, dict):
            rows = [rows]
        return [{"address": item["address"], "name": str(item.get("name") or "Wi-Fi / Ethernet")[:80]}
                for item in rows if isinstance(item, dict) and is_lan_address(item.get("address", ""))]
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []


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
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
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
        if len(hosts) != 1 or hosts[0] != companion.authority:
            raise PhoneRequestError("访问地址不匹配，请使用电脑显示的手机地址。", 403)
        if any(value.strip().casefold() == "cross-site"
               for header in self.headers.get_all("Sec-Fetch-Site", []) for value in header.split(",")):
            raise PhoneRequestError("不允许跨网站请求。", 403)
        origins = self.headers.get_all("Origin", [])
        if origins and (len(origins) != 1 or origins[0] != "http://" + companion.authority):
            raise PhoneRequestError("请求来源不匹配。", 403)
        if post and (len(origins) != 1 or origins[0] != "http://" + companion.authority
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
        if self.headers.get_all("Host", []) != [companion.authority]:
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

    def _body(self):
        if self.headers.get("Transfer-Encoding"):
            raise PhoneRequestError("不支持此请求格式。")
        lengths = self.headers.get_all("Content-Length", [])
        try:
            if len(lengths) != 1:
                raise ValueError()
            size = int(lengths[0])
        except ValueError:
            raise PhoneRequestError("请求长度无效。")
        if not 0 <= size <= MAX_BODY:
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
                self._send({"paired": companion.is_paired(self._token(), self.client_address[0])})
                return
            session = companion.session(self._token(), self.client_address[0])
            if parsed.path.startswith("/api/phone/transfer/"):
                if companion.transfer_store is None:
                    raise PhoneRequestError("电脑端互传组件尚未更新。", 503)
                token, peer = self._token(), self.client_address[0]
                authorize = lambda: companion.session(token, peer)
                if parsed.path == "/api/phone/transfer/messages":
                    result = companion.transfer_store.list(parsed.query, prefix="/api/phone/transfer")
                    authorize()
                    self._send(result)
                elif parsed.path == "/api/phone/transfer/attachment":
                    item = companion.transfer_store.attachment(parsed.query)
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
        except TransferError as error:
            self._send({"error": str(error)}, error.status)
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
                if set(body) != {"code"}:
                    raise PhoneRequestError("请输入电脑显示的配对码。")
                token = companion.pair(body["code"], self.client_address[0])
                self._send({"paired": True, "expiresIn": SESSION_TTL}, cookie=companion.cookie(token))
                return
            token = self._token()
            session = companion.session(token, self.client_address[0])
            if parsed.path == "/api/phone/inbox/move":
                if set(body) != {"id", "status"}:
                    raise PhoneRequestError("阅读状态无效。")
                self._send(companion.move_report(session, body["id"], body["status"]))
            elif parsed.path == "/api/phone/logout":
                if body:
                    raise PhoneRequestError("请求内容无效。")
                companion.logout(token)
                self._send({"paired": False}, cookie=companion.cookie("", max_age=0))
            else:
                raise PhoneRequestError("手机入口没有此功能。", 404)
        except PhoneRequestError as error:
            self._send({"error": str(error)}, error.status)
        except TransferError as error:
            self._send({"error": str(error)}, error.status)
        except (ValueError, OSError, RuntimeError, sqlite3.Error):
            self._send({"error": "操作未完成，请刷新后重试。"}, 400)


class PhoneCompanionService:
    def __init__(self, document_library, plan_getter, app_dir, version, device_getter=None,
                 *, clock=None, interface_getter=None, music_getter=None,
                 music_file_getter=None, music_lyrics_getter=None, computer_id=None, transfer_store=None):
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

    def _prune(self):
        now = self._clock()
        self._sessions = {key: value for key, value in self._sessions.items() if value["expires"] > now}
        self._attempts = {key: [stamp for stamp in stamps if stamp > now - 60]
                          for key, stamps in self._attempts.items() if any(stamp > now - 60 for stamp in stamps)}
        if self._code and self._code_expires <= now:
            self._code = ""

    def state(self, include_interfaces=True):
        with self._lock:
            self._prune()
            remaining = max(0, self._code_expires - self._clock()) if self._code else 0
            result = {"enabled": self._server is not None, "host": self._host, "port": self._port,
                      "url": "http://" + self.authority + "/" if self._server is not None else "",
                      "pairingCode": self._code,
                      "pairingExpiresAt": datetime.fromtimestamp(time.time() + remaining, timezone.utc).isoformat() if remaining else None,
                      "pairingExpiresIn": int(remaining), "pairedCount": len(self._sessions),
                      "networkWarning": NETWORK_WARNING, "transport": "http-lan"}
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
        interfaces = self._available_interfaces(force=True)
        addresses = [item.get("address") for item in interfaces if isinstance(item, dict) and is_lan_address(item.get("address", ""))]
        host = host or (addresses[0] if addresses else "")
        if host not in addresses or not is_lan_address(host):
            raise ValueError("没有可用的 Wi-Fi / Ethernet 地址，请先将电脑接入同一 Wi-Fi。")
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError("手机入口端口无效。")
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
            self._sessions.clear()
            self._attempts.clear()
            self._new_code()
            self._thread = threading.Thread(target=server.serve_forever, name="console-phone-companion", daemon=True)
            self._thread.start()
        return self.state(include_interfaces=False)

    def _new_code(self):
        self._code = f"{secrets.randbelow(1000000):06d}"
        self._code_expires = self._clock() + PAIR_TTL
        self._code_failures = 0

    def renew_pairing(self):
        with self._lock:
            if self._server is None:
                raise ValueError("请先开启手机入口。")
            self._new_code()
        return self.state(include_interfaces=False)

    def stop(self):
        with self._lock:
            server, thread = self._server, self._thread
            self._server = self._thread = None
            self._host, self._port = "", None
            self._code = ""
            self._sessions.clear()
            self._attempts.clear()
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3)
        return self.state(include_interfaces=False)

    def pair(self, code, peer, *, scope="phone"):
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
            if (not isinstance(code, str) or len(code) != 6 or not code.isascii() or not code.isdigit()
                    or not self._code or not secrets.compare_digest(code, self._code)):
                self._code_failures += 1
                if self._code_failures >= 8:
                    self._code = ""
                raise PhoneRequestError("配对码错误或已失效，请在电脑上获取新配对码。", 401)
            if len(self._sessions) >= 8:
                raise PhoneRequestError("已配对设备过多，请在电脑上关闭后重新开启手机入口。", 429)
            root = self.documents.state().get("root", "")
            token = secrets.token_urlsafe(32)
            self._sessions[token] = {"expires": self._clock() + SESSION_TTL, "peer": peer,
                                     "root": root, "scope": scope}
            self._code = ""  # One successful pairing consumes the code.
            return token

    @staticmethod
    def cookie(token, max_age=SESSION_TTL):
        return f"{COOKIE_NAME}={token}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict"

    def session(self, token, peer, *, scope="phone"):
        with self._lock:
            self._prune()
            session = self._sessions.get(token)
            if (self._server is None or not session or session["peer"] != peer
                    or session.get("scope", "phone") != scope):
                raise PhoneRequestError("请先使用电脑显示的配对码连接。", 401)
            if session["root"] != self.documents.state().get("root", ""):
                self._sessions.pop(token, None)
                raise PhoneRequestError("电脑资料库已切换，请重新配对。", 401)
            return dict(session)

    def is_paired(self, token, peer):
        try:
            self.session(token, peer)
            return True
        except PhoneRequestError:
            return False

    def logout(self, token):
        with self._lock:
            self._sessions.pop(token, None)

    def asset(self, path):
        name = ASSETS.get(path)
        if not name:
            raise PhoneRequestError("手机入口没有此文件。", 404)
        target = (self.app_dir / name).resolve()
        if target.parent != self.app_dir or not target.is_file():
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
