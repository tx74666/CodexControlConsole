"""Private, persistent same-LAN text/image inbox; never executes uploaded content."""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from email.parser import HeaderParser
from email.utils import collapse_rfc2231_value
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import threading
from urllib.parse import parse_qs, urlencode
import uuid
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_TEXT_CHARS = 20_000
MAX_FILES = 4
MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_REQUEST_BYTES = 24 * 1024 * 1024
MAX_PIXELS = 40_000_000
LIMITS = {"maxTextChars": MAX_TEXT_CHARS, "maxFiles": MAX_FILES,
          "maxFileBytes": MAX_FILE_BYTES, "maxRequestBytes": MAX_REQUEST_BYTES}
UPLOAD_SLOTS = threading.BoundedSemaphore(2)
DECODE_LOCK = threading.Lock()
ID_PATTERN = re.compile(r"[a-f0-9]{32}\Z")
IMAGE_FORMATS = {"JPEG": (".jpg", "image/jpeg", {".jpg", ".jpeg"}),
                 "PNG": (".png", "image/png", {".png"}),
                 "GIF": (".gif", "image/gif", {".gif"}),
                 "WEBP": (".webp", "image/webp", {".webp"})}


class TransferError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _identifier(value):
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise TransferError("互传项目无效。", 404)
    return value


def _safe_child(parent, name):
    parent = Path(parent).resolve()
    target = parent / name
    if (target.is_symlink() or getattr(target, "is_junction", lambda: False)()
            or target.resolve() != target or target.resolve().parent != parent):
        raise TransferError("互传目录指向了其他位置，请在电脑上检查资料库。", 403)
    return target


def _filename(value):
    if not isinstance(value, str):
        raise TransferError("图片文件名无效。")
    # Filenames are display metadata; uploaded paths never control disk paths.
    value = value.replace("\\", "/").rsplit("/", 1)[-1]
    value = re.sub(r"[\x00-\x1f\x7f]", "", value).strip()[:160]
    if not value or value in {".", ".."}:
        raise TransferError("图片文件名无效。")
    return value


class IncomingFile:
    def __init__(self, spool, offset, size, name, mime_type):
        self.spool, self.offset, self.size = spool, offset, size
        self.name, self.mime_type = name, mime_type

    def copy_to(self, path):
        digest = hashlib.sha256()
        with Path(self.spool).open("rb") as source, path.open("xb") as dest:
            source.seek(self.offset)
            remaining = self.size
            while remaining:
                block = source.read(min(64 * 1024, remaining))
                if not block:
                    raise TransferError("图片上传中断，请重新上传。")
                dest.write(block)
                digest.update(block)
                remaining -= len(block)
            dest.flush()
            os.fsync(dest.fileno())
        return digest.hexdigest()


@contextmanager
def read_transfer_request(headers, stream, *, allowed_fields=None):
    """Bounded multipart spool, strict fields, no decoded/base64 image copies."""
    field_names = frozenset({"text", "requestId"} if allowed_fields is None else allowed_fields)
    if not field_names or "requestId" not in field_names or not field_names <= {"text", "requestId", "recordId"}:
        raise ValueError("Unsupported multipart fields")
    if not UPLOAD_SLOTS.acquire(blocking=False):
        raise TransferError("正在接收其他图片，请稍后重试。", 429)
    spool = None
    try:
        if headers.get_all("Transfer-Encoding", []):
            raise TransferError("请使用有明确长度的上传请求。")
        lengths = headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,10}", lengths[0]):
            raise TransferError("上传请求长度无效。")
        size = int(lengths[0])
        if not 0 < size <= MAX_REQUEST_BYTES:
            raise TransferError("每次上传总大小不能超过 24 MB。", 413)
        types = headers.get_all("Content-Type", [])
        if len(types) != 1 or len(types[0]) > 256:
            raise TransferError("上传请求格式无效。", 415)
        matched = re.fullmatch(r'multipart/form-data;\s*boundary=(?:"([A-Za-z0-9\x27()+_,./:=?-]{1,70})"|([A-Za-z0-9\x27()+_,./:=?-]{1,70}))', types[0], re.I)
        if not matched:
            raise TransferError("请使用图片上传表单。", 415)
        boundary = (matched[1] or matched[2]).encode("ascii")
        descriptor, spool_name = tempfile.mkstemp(prefix="codex-transfer-", suffix=".tmp")
        spool = Path(spool_name)
        with os.fdopen(descriptor, "wb") as dest:
            remaining = size
            while remaining:
                block = stream.read(min(64 * 1024, remaining))
                if not block:
                    raise TransferError("上传中断，内容未发送，请重新上传。")
                dest.write(block)
                remaining -= len(block)
        fields, files = {}, []
        with spool.open("rb") as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as body:
            opening = b"--" + boundary + b"\r\n"
            marker = b"\r\n--" + boundary
            if body[:len(opening)] != opening:
                raise TransferError("上传表单不完整。")
            position = len(opening)
            parts = 0
            while True:
                parts += 1
                if parts > MAX_FILES + len(field_names):
                    raise TransferError("一次最多上传 4 张图片。", 413)
                header_end = body.find(b"\r\n\r\n", position, min(len(body), position + 4096))
                if header_end < 0:
                    raise TransferError("上传表单标题无效。")
                raw_header = body[position:header_end]
                if b"\r\n " in raw_header or b"\r\n\t" in raw_header:
                    raise TransferError("上传表单标题无效。")
                try:
                    # Browser multipart filenames are UTF-8 HTTP header bytes,
                    # not MIME's default ASCII. BytesHeaderParser's compat32
                    # get_filename replaces non-ASCII bytes irreversibly.
                    decoded_header = raw_header.decode("utf-8", errors="strict")
                except UnicodeError:
                    raise TransferError("图片文件名编码无效，请重新选择图片。")
                part = HeaderParser().parsestr(decoded_header + "\r\n\r\n")
                if (part.defects or part.get_all("Content-Disposition", []) == []
                        or len(part.get_all("Content-Disposition", [])) != 1
                        or len(part.get_all("Content-Type", [])) > 1
                        or part.get("Content-Transfer-Encoding")):
                    raise TransferError("上传表单标题无效。")
                if part.get_content_disposition() != "form-data":
                    raise TransferError("上传表单内容无效。")
                params = part.get_params(header="Content-Disposition", unquote=True)[1:]
                if len({key for key, _ in params}) != len(params) or any(key not in {"name", "filename"} for key, _ in params):
                    raise TransferError("上传表单参数无效。")
                disposition = dict(params)
                name = disposition.get("name")
                filename = disposition.get("filename")
                if isinstance(filename, tuple):
                    charset, language, encoded = filename
                    if str(charset or "").lower() not in {"utf-8", "us-ascii", "ascii"}:
                        raise TransferError("图片文件名编码无效。")
                    try:
                        filename = collapse_rfc2231_value(filename, errors="strict")
                    except (UnicodeError, LookupError):
                        raise TransferError("图片文件名编码无效。")
                content_start = header_end + 4
                end = body.find(marker, content_start)
                while end >= 0 and body[end + len(marker):end + len(marker) + 2] not in (b"\r\n", b"--"):
                    end = body.find(marker, end + 1)
                if end < 0:
                    raise TransferError("上传表单不完整。")
                length = end - content_start
                if name == "files" and filename is not None:
                    if len(files) >= MAX_FILES or not 0 < length <= MAX_FILE_BYTES:
                        raise TransferError("一次最多 4 张图片，每张不能超过 12 MB。", 413)
                    files.append(IncomingFile(spool, content_start, length, _filename(filename), part.get_content_type()))
                elif name in field_names and filename is None:
                    if name in fields or length > MAX_TEXT_CHARS * 4:
                        raise TransferError("上传文字过长或包含重复内容。", 413)
                    try:
                        fields[name] = body[content_start:end].decode("utf-8")
                    except UnicodeError:
                        raise TransferError("上传文字编码无效。")
                else:
                    raise TransferError("上传表单包含不支持的内容。")
                tail = end + len(marker)
                if body[tail:tail + 2] == b"--":
                    if body[tail + 2:] not in (b"", b"\r\n"):
                        raise TransferError("上传表单结尾无效。")
                    break
                position = tail + 2
        if "requestId" not in fields:
            raise TransferError("上传标识缺失，请刷新后重试。")
        yield fields, files
    finally:
        if spool:
            spool.unlink(missing_ok=True)
        UPLOAD_SLOTS.release()


def _heic(path):
    """Check complete ISO-BMFF structure; preserve HEIC without decoding it."""
    size = path.stat().st_size
    brands, seen, offset = set(), set(), 0
    with path.open("rb") as source:
        while offset < size:
            source.seek(offset)
            header = source.read(16)
            if len(header) < 8:
                raise TransferError("HEIC 图片内容不完整。", 415)
            length = int.from_bytes(header[:4], "big")
            kind, header_size = header[4:8], 8
            if length == 1:
                if len(header) < 16:
                    raise TransferError("HEIC 图片内容不完整。", 415)
                length, header_size = int.from_bytes(header[8:16], "big"), 16
            elif length == 0:
                length = size - offset
            if length < header_size or offset + length > size:
                raise TransferError("HEIC 图片内容不完整。", 415)
            seen.add(kind)
            if offset == 0 and kind != b"ftyp":
                raise TransferError("HEIC 图片格式无效。", 415)
            if kind == b"ftyp":
                if length > 1024 or length < header_size + 8 or (length - header_size) % 4:
                    raise TransferError("HEIC 图片格式无效。", 415)
                source.seek(offset + header_size)
                payload = source.read(length - header_size)
                brands.update([payload[:4], *[payload[n:n + 4] for n in range(8, len(payload), 4)]])
            offset += length
    if not brands.intersection({b"heic", b"heix", b"hevc", b"hevx"}) or not {b"meta", b"mdat"}.issubset(seen):
        raise TransferError("HEIC 图片格式无效。", 415)
    return ".heic", "image/heic", False


def _image(path, name, thumbnail):
    suffix = Path(name).suffix.lower()
    if suffix in {".heic", ".heif"}:
        return _heic(path)
    try:
        with DECODE_LOCK, warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                detected = IMAGE_FORMATS.get(image.format)
                if not detected or suffix not in detected[2]:
                    raise TransferError("请上传内容与文件名相符的 JPEG、PNG、GIF、WebP 或 HEIC 图片。", 415)
                width, height = image.size
                if width < 1 or height < 1 or width * height > MAX_PIXELS:
                    raise TransferError("图片分辨率过大，请缩小后上传。", 413)
                image.verify()
            with Image.open(path) as image:
                image.draft("RGB", (800, 800))
                image.load()  # Reject truncated or merely signature-matching files.
                image = ImageOps.exif_transpose(image)
                image.thumbnail((800, 800))
                if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                    rgba = image.convert("RGBA")
                    rendered = Image.new("RGB", rgba.size, "white")
                    rendered.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    rendered = image.convert("RGB")
                rendered.save(thumbnail, "JPEG", quality=82)
                with thumbnail.open("rb+") as source:
                    os.fsync(source.fileno())
            return detected[0], detected[1], True
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombWarning, Image.DecompressionBombError) as error:
        raise TransferError("图片无法完整解码，内容未发送，请重新选择图片。", 415) from error


class TransferStore:
    def __init__(self, root_getter, fallback_dir, *, public_root=None):
        self.root_getter = root_getter
        self.fallback_dir = Path(fallback_dir)
        self.public_root = Path(public_root).resolve() if public_root is not None else None
        self._lock = threading.RLock()
        self._readers = {}

    def _location(self):
        selected = self.root_getter()
        if selected:
            root = Path(selected).expanduser().resolve()
            if not root.is_dir():
                raise TransferError("资料库无法访问，互传内容未保存，请在电脑上检查。", 503)
            folder = _safe_child(root, "互传")
            label = "资料库 · 互传"
        else:
            folder, label = self.fallback_dir.resolve(), "本机 · 互传"
        if self.public_root is not None:
            try:
                folder.resolve().relative_to(self.public_root)
            except ValueError:
                pass
            else:
                raise TransferError("互传资料库不能放在应用程序的网页目录内，请在 Document 选择独立资料库。", 403)
        folder.mkdir(parents=True, exist_ok=True)
        private = _safe_child(folder, ".console-transfer")
        private.mkdir(exist_ok=True)
        return folder, private, label

    @contextmanager
    def _database(self, location=None):
        folder, private, label = location if location is not None else self._location()
        if location is not None and (folder.resolve() != folder or not folder.is_dir()
                or private != _safe_child(folder, ".console-transfer") or not private.is_dir()):
            raise TransferError("互传目录已变化，请重新读取记录。", 403)
        database = _safe_child(private, "history.sqlite3")
        connection = sqlite3.connect(database, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, request_id TEXT NOT NULL,
                    sender TEXT NOT NULL, created_at TEXT NOT NULL, text TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, starred INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(sender, request_id));
                CREATE TABLE IF NOT EXISTS attachments (id TEXT PRIMARY KEY, message_id TEXT NOT NULL,
                    name TEXT NOT NULL, filename TEXT NOT NULL, mime_type TEXT NOT NULL,
                    size INTEGER NOT NULL, preview INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS attachment_messages ON attachments(message_id);
                CREATE TABLE IF NOT EXISTS history_state (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL);
                INSERT OR IGNORE INTO history_state VALUES (1, 0);
                CREATE TABLE IF NOT EXISTS deleted_requests (sender TEXT NOT NULL, request_id TEXT NOT NULL,
                    PRIMARY KEY(sender, request_id));
                CREATE TABLE IF NOT EXISTS attachment_cleanup (id TEXT PRIMARY KEY, filename TEXT NOT NULL,
                    preview INTEGER NOT NULL);
            """)
            # Upgrade existing private histories without rebuilding their records.
            connection.execute("BEGIN IMMEDIATE")
            if "starred" not in {row["name"] for row in connection.execute("PRAGMA table_info(messages)")}:
                connection.execute("ALTER TABLE messages ADD COLUMN starred INTEGER NOT NULL DEFAULT 0")
            connection.commit()
            self._cleanup_attachments(connection, folder, private)
            yield connection, folder, private, label
        finally:
            connection.close()

    @staticmethod
    def _public(db, row, prefix, folder=None):
        attachments = []
        for item in db.execute("SELECT * FROM attachments WHERE message_id=? ORDER BY rowid", (row["id"],)):
            url = prefix + "/attachment?" + urlencode({"id": item["id"]})
            attachment = {"id": item["id"], "name": item["name"], "mimeType": item["mime_type"],
                                "size": item["size"], "previewable": bool(item["preview"]), "url": url,
                                "previewUrl": url + "&preview=1" if item["preview"] else None}
            if prefix == "/api/transfer" and folder is not None:
                attachment["path"] = str(_safe_child(folder, item["filename"]))
            attachments.append(attachment)
        return {"id": row["id"], "requestId": row["request_id"], "sender": row["sender"],
                "createdAt": row["created_at"], "text": row["text"], "starred": bool(row["starred"]),
                "attachments": attachments}

    @staticmethod
    def _change_revision(db):
        db.execute("UPDATE history_state SET revision=revision+1 WHERE id=1")

    def _cleanup_attachments(self, db, folder, private):
        """Retry only registered owned files; live downloads keep their handles."""
        for row in db.execute("SELECT * FROM attachment_cleanup").fetchall():
            try:
                identifier = _identifier(row["id"])
                if not re.fullmatch(re.escape(identifier) + r"\.(?:jpg|png|gif|webp|heic)", row["filename"]):
                    continue
                paths = [_safe_child(folder, row["filename"])]
                if row["preview"]:
                    paths.append(_safe_child(private, identifier + ".preview.jpg"))
                if any(self._readers.get(str(path), 0) for path in paths):
                    continue
                for path in paths:
                    path.unlink(missing_ok=True)
            except (OSError, TransferError):
                # A busy file or redirected path is left for a later safe retry.
                continue
            db.execute("DELETE FROM attachment_cleanup WHERE id=?", (identifier,))
        db.commit()

    def list(self, query="", prefix="/api/transfer", location=None):
        params = parse_qs(query, keep_blank_values=True)
        if (len(query) > 512 or set(params) - {"limit", "before", "revision"}
                or any(len(v) != 1 for v in params.values())
                or len(params.get("revision", [""])[0]) > 64):
            raise TransferError("互传列表请求无效。")
        try:
            limit_value = params.get("limit", ["50"])[0]
            if not re.fullmatch(r"[0-9]{1,2}", limit_value):
                raise ValueError()
            limit = int(limit_value)
            if not 1 <= limit <= 50:
                raise ValueError()
        except ValueError:
            raise TransferError("互传列表数量无效。")
        before = params.get("before", [""])[0]
        if before:
            _identifier(before)
        with self._lock, self._database(location) as (db, folder, private, label):
            sequence = db.execute("SELECT revision FROM history_state WHERE id=1").fetchone()["revision"]
            revision = hashlib.sha256(str(private).encode()).hexdigest()[:12] + ":" + str(sequence)
            result = {"revision": revision, "limits": LIMITS, "storageLabel": label}
            if not before and params.get("revision", [""])[0] == revision:
                return {**result, "unchanged": True}
            position = None
            if before:
                row = db.execute("SELECT rowid FROM messages WHERE id=?", (before,)).fetchone()
                if row is None:
                    raise TransferError("该互传记录不存在，请刷新。", 404)
                position = row["rowid"]
            rows = db.execute("SELECT * FROM messages WHERE (? IS NULL OR rowid<?) ORDER BY rowid DESC LIMIT ?",
                              (position, position, limit + 1)).fetchall()
            return {**result, "messages": [self._public(db, row, prefix, folder) for row in rows[:limit]],
                    "hasMore": len(rows) > limit}

    def send(self, fields, files, sender, prefix="/api/transfer", authorize=None):
        if sender not in {"phone", "desktop"} or set(fields) - {"requestId", "text"}:
            raise TransferError("互传请求无效。")
        try:
            request_id = str(uuid.UUID(fields.get("requestId", "")))
        except (ValueError, TypeError, AttributeError):
            raise TransferError("上传标识无效，请刷新后重试。")
        text = fields.get("text", "")
        if not isinstance(text, str) or len(text) > MAX_TEXT_CHARS or "\0" in text:
            raise TransferError("文字不能超过 20000 字，请缩短后发送。", 413)
        if not text.strip() and not files:
            raise TransferError("请填写文字或选择图片后发送。")
        if len(files) > MAX_FILES or any(not 0 < file.size <= MAX_FILE_BYTES for file in files):
            raise TransferError("一次最多 4 张图片，每张不能超过 12 MB。", 413)
        if sum(file.size for file in files) + len(text.encode("utf-8")) > MAX_REQUEST_BYTES:
            raise TransferError("每次上传总大小不能超过 24 MB。", 413)
        if authorize:
            authorize()
        committed, staged = False, []
        with self._lock, self._database() as (db, folder, private, _):
            if shutil.disk_usage(folder).free < sum(file.size for file in files) + 8 * 1024 * 1024:
                raise TransferError("电脑磁盘空间不足，内容未发送。", 507)
            stage = _safe_child(private, uuid.uuid4().hex + ".pending")
            stage.mkdir()
            try:
                fingerprints = [text]
                metadata = []
                for file in files:
                    name = _filename(file.name)
                    identifier = uuid.uuid4().hex
                    incoming = _safe_child(stage, identifier + ".upload")
                    digest = file.copy_to(incoming)
                    thumb = _safe_child(stage, identifier + ".preview.jpg")
                    extension, mime_type, preview = _image(incoming, name, thumb)
                    allowed_types = {mime_type, "application/octet-stream"}
                    if mime_type == "image/heic":
                        allowed_types.add("image/heif")
                    if mime_type == "image/jpeg":
                        allowed_types.add("image/jpg")
                    if file.mime_type not in allowed_types:
                        raise TransferError("图片类型与文件内容不一致。", 415)
                    filename = identifier + extension
                    metadata.append((identifier, name, filename, mime_type, file.size, preview, incoming, thumb))
                    fingerprints.append([name, digest])
                fingerprint = hashlib.sha256(json.dumps(fingerprints, ensure_ascii=False).encode("utf-8")).hexdigest()
                existing = db.execute("SELECT * FROM messages WHERE sender=? AND request_id=?", (sender, request_id)).fetchone()
                if existing:
                    if existing["fingerprint"] != fingerprint:
                        raise TransferError("这次上传标识已用于其他内容，请重新发送。", 409)
                    if authorize:
                        authorize()
                    return {"message": self._public(db, existing, prefix, folder), "duplicate": True}
                if db.execute("SELECT 1 FROM deleted_requests WHERE sender=? AND request_id=?", (sender, request_id)).fetchone():
                    raise TransferError("这次发送记录已删除，请重新发送。", 409)
                if authorize:
                    authorize()  # Expired/stopped/revoked pairing never writes a message.
                identifier = uuid.uuid4().hex
                db.execute("BEGIN IMMEDIATE")
                db.execute("INSERT INTO messages (id,request_id,sender,created_at,text,fingerprint) VALUES (?,?,?,?,?,?)", (identifier, request_id, sender,
                           datetime.now(timezone.utc).isoformat(), text, fingerprint))
                for aid, name, filename, mime_type, size, preview, incoming, thumb in metadata:
                    original = _safe_child(folder, filename)
                    os.replace(incoming, original)
                    staged.append(original)
                    if preview:
                        preview_path = _safe_child(private, aid + ".preview.jpg")
                        os.replace(thumb, preview_path)
                        staged.append(preview_path)
                    db.execute("INSERT INTO attachments VALUES (?,?,?,?,?,?,?)", (aid, identifier, name, filename, mime_type, size, int(preview)))
                if authorize:
                    authorize()
                self._change_revision(db)
                db.commit()
                committed = True
                row = db.execute("SELECT * FROM messages WHERE id=?", (identifier,)).fetchone()
                return {"message": self._public(db, row, prefix, folder), "duplicate": False}
            finally:
                if not committed:
                    db.rollback()
                    for path in staged:
                        path.unlink(missing_ok=True)
                # Only files generated for this request are removed, no recursion.
                for path in stage.iterdir():
                    path.unlink()
                stage.rmdir()

    def mutate(self, action, body, prefix="/api/transfer", authorize=None):
        """Strict shared-history operations; normal clear preserves every star."""
        if not isinstance(body, dict):
            raise TransferError("互传操作内容无效。")
        if action == "star":
            if set(body) != {"id", "starred"} or type(body["starred"]) is not bool:
                raise TransferError("标星操作无效。")
            identifier = _identifier(body["id"])
        elif action == "delete":
            if set(body) != {"id"}:
                raise TransferError("删除操作无效。")
            identifier = _identifier(body["id"])
        elif action == "clear":
            if set(body) != {"mode"} or not isinstance(body["mode"], str) or body["mode"] not in {"unstarred", "all"}:
                raise TransferError("请明确选择清空未标星或全部清空。")
        else:
            raise TransferError("互传操作不存在。", 404)
        if authorize:
            authorize()
        with self._lock, self._database() as (db, folder, private, label):
            db.execute("BEGIN IMMEDIATE")
            removed = 0
            try:
                if authorize:
                    authorize()
                if action in {"star", "delete"}:
                    row = db.execute("SELECT * FROM messages WHERE id=?", (identifier,)).fetchone()
                    if row is None:
                        raise TransferError("该互传记录不存在，请刷新。", 404)
                if action == "star":
                    changed = bool(row["starred"]) != body["starred"]
                    if changed:
                        db.execute("UPDATE messages SET starred=? WHERE id=?", (int(body["starred"]), identifier))
                else:
                    where, arguments = ("id=?", (identifier,)) if action == "delete" else (
                        ("starred=0", ()) if body["mode"] == "unstarred" else ("1=1", ()))
                    removed = db.execute("SELECT COUNT(*) FROM messages WHERE " + where, arguments).fetchone()[0]
                    changed = removed > 0
                    db.execute("INSERT OR IGNORE INTO attachment_cleanup SELECT id,filename,preview FROM attachments "
                               "WHERE message_id IN (SELECT id FROM messages WHERE " + where + ")", arguments)
                    db.execute("DELETE FROM attachments WHERE message_id IN (SELECT id FROM messages WHERE " + where + ")", arguments)
                    db.execute("INSERT OR IGNORE INTO deleted_requests SELECT sender,request_id FROM messages WHERE " + where, arguments)
                    db.execute("DELETE FROM messages WHERE " + where, arguments)
                if authorize:
                    authorize()
                if changed:
                    self._change_revision(db)
                db.commit()
            except BaseException:
                db.rollback()
                raise
            self._cleanup_attachments(db, folder, private)
            preserved = db.execute("SELECT COUNT(*) FROM messages WHERE starred=1").fetchone()[0]
            result = {**self.list(prefix=prefix, location=(folder, private, label)),
                      "removedCount": removed, "preservedStarredCount": preserved}
            if authorize:
                authorize()
            return result

    def attachment(self, query, location=None):
        params = parse_qs(query, keep_blank_values=True)
        if (set(params) - {"id", "preview", "download"} or "id" not in params
                or any(len(v) != 1 for v in params.values())
                or any(params.get(key, ["0"])[0] not in {"0", "1"} for key in ("preview", "download"))):
            raise TransferError("图片请求无效。")
        identifier = _identifier(params["id"][0])
        with self._lock, self._database(location) as (db, folder, private, _):
            row = db.execute("SELECT * FROM attachments WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise TransferError("图片不存在。", 404)
            preview = params.get("preview", ["0"])[0] == "1"
            if preview and not row["preview"]:
                raise TransferError("HEIC 原图已保存，请下载后打开。", 415)
            target = _safe_child(private if preview else folder,
                                 identifier + ".preview.jpg" if preview else row["filename"])
            if not target.is_file() or not 0 < target.stat().st_size <= MAX_FILE_BYTES:
                raise TransferError("图片无法读取，请在电脑上检查。", 404)
            return {"path": target, "mimeType": "image/jpeg" if preview else row["mime_type"],
                    "name": identifier + ".jpg" if preview else row["name"],
                    "download": params.get("download", ["0"])[0] == "1"}

    @contextmanager
    def read_attachment(self, query, authorize=None):
        """Open under the same lock as deletion, then stream without blocking writes."""
        with self._lock:
            if authorize:
                authorize()
            location = self._location()
            item = self.attachment(query, location=location)
            source = item["path"].open("rb")
            key = str(item["path"])
            self._readers[key] = self._readers.get(key, 0) + 1
        try:
            yield {**item, "source": source}
        finally:
            source.close()
            with self._lock:
                remaining = self._readers[key] - 1
                if remaining:
                    self._readers[key] = remaining
                else:
                    self._readers.pop(key, None)
                try:
                    with self._database(location):
                        pass
                except (OSError, sqlite3.Error, TransferError):
                    pass  # Persisted cleanup retries at the next history access.

    def open_attachment(self, body):
        if not isinstance(body, dict) or set(body) - {"id", "folder"} or not isinstance(body.get("folder", False), bool):
            raise TransferError("打开互传文件请求无效。")
        with self._lock:
            item = self.attachment(urlencode({"id": _identifier(body.get("id"))}))
            if os.name != "nt":
                raise TransferError("当前系统无法打开本机文件，请下载后使用。", 503)
            target = item["path"].parent if body.get("folder") else item["path"]
            os.startfile(str(target))
        return {"opened": True}


def send_transfer_attachment(handler, item, *, authorize=None):
    """Stream only a registered, contained attachment, including authenticated HEAD."""
    with (nullcontext(item["source"]) if "source" in item else item["path"].open("rb")) as source:
        if authorize:
            authorize()
        size = os.fstat(source.fileno()).st_size
        if not 0 < size <= MAX_FILE_BYTES:
            raise TransferError("图片无法读取。", 404)
        handler.send_response(200)
        handler.send_header("Content-Type", item["mimeType"])
        handler.send_header("Content-Length", str(size))
        handler.send_header("Cache-Control", "private, no-store")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("Referrer-Policy", "no-referrer")
        handler.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
        from urllib.parse import quote
        handler.send_header("Content-Disposition", ("attachment" if item["download"] else "inline") +
                            "; filename*=UTF-8''" + quote(item["name"], safe=""))
        handler.end_headers()
        if handler.command == "HEAD":
            return
        try:
            remaining = size
            while remaining:
                if authorize:
                    authorize()
                block = source.read(min(64 * 1024, remaining))
                if not block:
                    break
                handler.wfile.write(block)
                remaining -= len(block)
        except (OSError, ValueError, BrokenPipeError, ConnectionResetError):
            return
