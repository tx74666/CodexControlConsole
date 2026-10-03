"""Private remembered phone credentials and explicitly approved LAN settings."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
import uuid

REMEMBER_TTL = 90 * 24 * 60 * 60
MAX_DEVICES = 8
TOKEN_PATTERN = re.compile(r"([a-f0-9]{32})\.([A-Za-z0-9_-]{43})\Z")


class DeviceStoreError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def root_hash(root):
    normalized = os.path.normcase(str(Path(root).expanduser().resolve())) if root else ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


class PhoneDeviceStore:
    def __init__(self, directory, *, clock=None):
        self.directory = Path(directory).resolve()
        self._clock = clock or time.time
        self._lock = threading.RLock()

    @contextmanager
    def _database(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / "phone-devices.sqlite3"
        if target.is_symlink() or getattr(target, "is_junction", lambda: False)() or target.resolve() != target:
            raise DeviceStoreError("手机信任记录目录无效，请在电脑上检查。", 403)
        connection = sqlite3.connect(target, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY, secret_hash TEXT NOT NULL,
                    root_hash TEXT NOT NULL, network_hash TEXT NOT NULL, name TEXT NOT NULL,
                    created_at REAL NOT NULL, last_seen_at REAL NOT NULL, expires_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _public(row):
        return {"id": row["id"], "name": row["name"], "createdAt": _timestamp(row["created_at"]),
                "lastSeenAt": _timestamp(row["last_seen_at"]), "expiresAt": _timestamp(row["expires_at"])}

    def register(self, root, network_hash, name):
        if not isinstance(network_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", network_hash):
            raise DeviceStoreError("当前网络标识暂不可用，请取消记住设备后临时连接。", 503)
        if not isinstance(name, str) or len(name) > 80 or any(ord(c) < 32 for c in name):
            raise DeviceStoreError("设备名称无效。")
        name = name.strip() or "我的手机"
        now = self._clock()
        with self._lock, self._database() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM devices WHERE expires_at<=?", (now,))
            if db.execute("SELECT COUNT(*) FROM devices").fetchone()[0] >= MAX_DEVICES:
                db.rollback()
                raise DeviceStoreError("已记住 8 台设备，请先在电脑删除不用的设备。", 429)
            identifier, secret = uuid.uuid4().hex, secrets.token_urlsafe(32)
            token = identifier + "." + secret
            db.execute("INSERT INTO devices VALUES (?,?,?,?,?,?,?,?)", (identifier,
                hashlib.sha256(token.encode("ascii")).hexdigest(), root_hash(root), network_hash,
                name, now, now, now + REMEMBER_TTL))
            db.commit()
            row = db.execute("SELECT * FROM devices WHERE id=?", (identifier,)).fetchone()
            return token, self._public(row)

    def authenticate(self, token, root, network_hash):
        matched = TOKEN_PATTERN.fullmatch(token) if isinstance(token, str) else None
        if not matched:
            raise DeviceStoreError("设备凭据无效，请重新扫码连接。", 401)
        now = self._clock()
        with self._lock, self._database() as db:
            row = db.execute("SELECT * FROM devices WHERE id=?", (matched[1],)).fetchone()
            if (row is None or not secrets.compare_digest(row["secret_hash"], hashlib.sha256(token.encode("ascii")).hexdigest())
                    or row["expires_at"] <= now):
                raise DeviceStoreError("设备已过期或被移除，请重新扫码连接。", 401)
            if not secrets.compare_digest(row["root_hash"], root_hash(root)):
                db.execute("DELETE FROM devices WHERE id=?", (row["id"],))
                db.commit()
                raise DeviceStoreError("电脑资料库已切换，请重新扫码连接。", 401)
            if not network_hash or not secrets.compare_digest(row["network_hash"], network_hash):
                raise DeviceStoreError("当前网络与记住设备时不同，请在电脑重新开启并扫码。", 401)
            if now - row["last_seen_at"] >= 60:
                db.execute("UPDATE devices SET last_seen_at=? WHERE id=?", (now, row["id"]))
                db.commit()
            return self._public(row)

    def active(self, identifier, root, network_hash):
        with self._lock, self._database() as db:
            row = db.execute("SELECT * FROM devices WHERE id=?", (identifier,)).fetchone()
            return bool(row is not None and row["expires_at"] > self._clock() and network_hash
                        and secrets.compare_digest(row["root_hash"], root_hash(root))
                        and secrets.compare_digest(row["network_hash"], network_hash))

    def list(self):
        with self._lock, self._database() as db:
            return [self._public(row) for row in db.execute("SELECT * FROM devices WHERE expires_at>? ORDER BY created_at", (self._clock(),))]

    def revoke(self, identifier=None, *, token=None, all_devices=False):
        if token is not None:
            matched = TOKEN_PATTERN.fullmatch(token) if isinstance(token, str) else None
            if not matched:
                return
            with self._lock, self._database() as db:
                digest = hashlib.sha256(token.encode("ascii")).hexdigest()
                db.execute("DELETE FROM devices WHERE id=? AND secret_hash=?", (matched[1], digest))
                db.commit()
            return
        if not all_devices and (not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier)):
            raise DeviceStoreError("设备标识无效。")
        with self._lock, self._database() as db:
            db.execute("DELETE FROM devices" if all_devices else "DELETE FROM devices WHERE id=?", () if all_devices else (identifier,))
            db.commit()

    def settings(self):
        with self._lock, self._database() as db:
            row = db.execute("SELECT value FROM settings WHERE key='network'").fetchone()
            try:
                value = json.loads(row["value"]) if row else {}
            except (ValueError, TypeError):
                value = {}
            if (not isinstance(value, dict) or value.get("enabled") is not True
                    or not isinstance(value.get("fingerprint"), str)
                    or not re.fullmatch(r"[a-f0-9]{64}", value.get("fingerprint", ""))
                    or type(value.get("port")) is not int or not 1024 <= value["port"] <= 65535):
                return {"enabled": False}
            return {"enabled": True, "fingerprint": value["fingerprint"], "port": value["port"]}

    def save_settings(self, value):
        if value.get("enabled") is True:
            if (not re.fullmatch(r"[a-f0-9]{64}", value.get("fingerprint", ""))
                    or type(value.get("port")) is not int or not 1024 <= value["port"] <= 65535):
                raise DeviceStoreError("手机自动连接设置无效。")
            value = {"enabled": True, "fingerprint": value["fingerprint"], "port": value["port"]}
        else:
            value = {"enabled": False}
        with self._lock, self._database() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES ('network',?)", (json.dumps(value),))
            db.commit()
