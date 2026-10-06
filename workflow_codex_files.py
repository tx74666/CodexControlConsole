"""Bounded Console-owned filesystem tools; no shell or code execution.

The controller verifies thread/turn/call ownership and cancellation before call.
Only full UTF-8 replacement is exposed. A durable call intent prevents replay;
an unknown result never authorizes another write. Optimistic file SHA checks do
not claim an atomic compare-and-swap against unrelated external file writers.
"""
from contextlib import contextmanager
import ctypes
from dataclasses import dataclass, field
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import threading

MAX_TEXT_BYTES = 1024 * 1024
MAX_LIST_ENTRIES = 256
MAX_LIST_BYTES = 16 * 1024 * 1024
MAX_PATH_DEPTH = 8
PROTECTED_DIRECTORIES = frozenset({".git", ".codex", ".ssh", ".aws", ".azure", "work",
    "workflow-private", "chatgpt-subscription", "attachments", "jobs", "siwc-probe"})
PROTECTED_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".dpapi")
PROTECTED_NAMES = frozenset({"auth.json", "credentials", "credentials.json", "token.json", "tokens.json",
    "registration.json", "identity-hint.json", ".netrc", ".npmrc", ".pypirc", ".git-credentials"})
CALL_ID = re.compile(r"[A-Za-z0-9_-]{1,190}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
DEVICE = re.compile(r"(?:CON|CONIN\$|CONOUT\$|PRN|AUX|NUL|CLOCK\$|COM[1-9¹²³]|LPT[1-9¹²³])\Z", re.I)


def fail(code):
    raise RuntimeError("codex_files_" + code)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def hashed(value):
    return hashlib.sha256(value).hexdigest()


def plain(path, directory=False, missing=False):
    try:
        info = path.lstat()
    except FileNotFoundError:
        if missing:
            return None
        fail("not_found")
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        fail("unsafe_path")
    if directory and not stat.S_ISDIR(info.st_mode):
        fail("not_directory")
    if not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
        fail("unsafe_file")
    if path.resolve() != path.absolute():
        fail("unsafe_path")
    return info


@contextmanager
def anchored(directory):
    """On Windows prevent ancestor rename/reparse swaps during an operation."""
    handles = []
    close = None
    try:
        if os.name == "nt":
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            create, close = kernel.CreateFileW, kernel.CloseHandle
            create.argtypes = (ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                               ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p)
            create.restype = ctypes.c_void_p
            close.argtypes = (ctypes.c_void_p,)
            get_info = kernel.GetFileInformationByHandleEx
            get_info.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32)
            class Attributes(ctypes.Structure):
                _fields_ = [("attributes", ctypes.c_uint32), ("tag", ctypes.c_uint32)]
        for parent in reversed((directory, *directory.parents)):
            plain(parent, directory=True)
            if os.name == "nt":
                # GENERIC_READ, share READ|WRITE (not DELETE), OPEN_EXISTING.
                # Attribute-only handles do not block directory rename on Windows.
                # BACKUP_SEMANTICS|OPEN_REPARSE_POINT. No directory is created here.
                handle = create(str(parent), 0x80000000, 3, None, 3, 0x02200000, None)
                if handle in (None, ctypes.c_void_p(-1).value):
                    fail("unsafe_path")
                handles.append(handle); attributes = Attributes()
                if (not get_info(handle, 9, ctypes.byref(attributes), ctypes.sizeof(attributes))
                        or attributes.attributes & 0x400 or not attributes.attributes & 0x10):
                    fail("unsafe_path")
        yield
        plain(directory, directory=True)
    finally:
        if close:
            for handle in reversed(handles):
                close(handle)


def bounded_text(path):
    info = plain(path)
    if info.st_size > MAX_TEXT_BYTES:
        fail("text_too_large")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        actual = os.fstat(stream.fileno())
        if not stat.S_ISREG(actual.st_mode) or actual.st_nlink != 1 or (actual.st_dev, actual.st_ino) != (info.st_dev, info.st_ino):
            fail("unsafe_file")
        raw = stream.read(MAX_TEXT_BYTES + 1)
    if len(raw) > MAX_TEXT_BYTES:
        fail("text_too_large")
    text = raw.decode("utf-8", errors="strict")
    if "\0" in text:
        fail("invalid_utf8_text")
    return raw, text


@dataclass(frozen=True)
class CodexFiles:
    allowed_root: Path
    markers_dir: Path
    protected_directories: tuple = ()
    protected_patterns: tuple = ()
    _lock: object = field(default_factory=threading.Lock, init=False, repr=False, compare=False)

    def __post_init__(self):
        try:
            root, markers = Path(self.allowed_root), Path(self.markers_dir)
            if not root.is_absolute() or not markers.is_absolute() or markers.is_relative_to(root):
                fail("invalid_scope")
            with anchored(root), anchored(markers):
                pass
            if (type(self.protected_directories) not in (tuple, list, frozenset)
                    or type(self.protected_patterns) not in (tuple, list, frozenset)
                    or any(type(name) is not str or not name for name in (*self.protected_directories, *self.protected_patterns))):
                fail("invalid_scope")
        except (OSError, TypeError, ValueError):
            fail("invalid_scope")
        object.__setattr__(self, "allowed_root", root.absolute())
        object.__setattr__(self, "markers_dir", markers.absolute())
        object.__setattr__(self, "protected_directories", PROTECTED_DIRECTORIES | frozenset(name.casefold() for name in self.protected_directories))
        object.__setattr__(self, "protected_patterns", tuple(pattern.casefold() for pattern in self.protected_patterns))

    def protected(self, part):
        name = part.casefold()
        return (name in self.protected_directories or name in PROTECTED_NAMES or name == ".env"
                or name.startswith(".env.") or name.endswith(PROTECTED_SUFFIXES))

    def relative(self, value, root_allowed=False):
        if type(value) is not str or len(value) > 512 or (not value and not root_allowed):
            fail("invalid_relative_path")
        parts = value.split("/") if value else []
        if len(parts) > MAX_PATH_DEPTH:
            fail("path_too_deep")
        for part in parts:
            if (part in {"", ".", ".."} or part.endswith((".", " "))
                    or any(ord(c) < 32 or c in '\\:<>"|?*' for c in part)
                    or DEVICE.fullmatch(part.split(".", 1)[0])):
                fail("invalid_relative_path")
            if self.protected(part):
                fail("protected_path")
        normalized = "/".join(parts).casefold()
        if any(fnmatch.fnmatchcase(normalized, pattern) or (pattern.startswith("**/") and fnmatch.fnmatchcase(normalized, pattern[3:]))
               for pattern in self.protected_patterns):
            fail("protected_path")
        return self.allowed_root.joinpath(*parts)

    def save(self, path, value):
        with path.open("xb") as stream:
            stream.write(encoded(value)); stream.flush(); os.fsync(stream.fileno())

    @staticmethod
    def _check_cancelled(cancelled):
        if cancelled is not None:
            try:
                state = cancelled()
            except Exception:
                fail("operation_unverified")
            if state is not False:
                fail("cancelled")

    def call(self, tool_name, arguments, call_id, *, cancelled=None):
        """Execute one already-bound call; True/unknown cancellation blocks IO."""
        try:
            if cancelled is not None and not callable(cancelled):
                fail("invalid_arguments")
            return self._call(tool_name, arguments, call_id, cancelled)
        except RuntimeError as error:
            if re.fullmatch(r"codex_files_[a-z0-9_]+", str(error)):
                raise
            fail("operation_unverified")
        except UnicodeError:
            fail("invalid_utf8_text")
        except (OSError, ValueError, TypeError):
            fail("operation_unverified")

    def _call(self, tool_name, arguments, call_id, cancelled):
        self._check_cancelled(cancelled)
        if type(call_id) is not str or not CALL_ID.fullmatch(call_id):
            fail("invalid_call_id")
        schemas = {"list_files": {"path", "depth"}, "read_text": {"path"},
                   "write_text": {"path", "expectedSha256", "content"}}
        if type(tool_name) is not str or tool_name not in schemas or type(arguments) is not dict or set(arguments) != schemas[tool_name]:
            fail("invalid_arguments")
        args = dict(arguments); path = self.relative(args["path"], tool_name == "list_files")
        if tool_name == "list_files" and (type(args["depth"]) is not int or not 1 <= args["depth"] <= 3):
            fail("invalid_arguments")
        if tool_name == "write_text":
            if (args["expectedSha256"] is not None and (type(args["expectedSha256"]) is not str or not SHA.fullmatch(args["expectedSha256"]))) or type(args["content"]) is not str:
                fail("invalid_arguments")
            try:
                content = args["content"].encode("utf-8", errors="strict")
            except UnicodeError:
                fail("invalid_utf8_text")
            if len(content) > MAX_TEXT_BYTES or "\0" in args["content"]:
                fail("text_too_large" if len(content) > MAX_TEXT_BYTES else "invalid_utf8_text")
        marker = self.markers_dir / hashed(call_id.encode("ascii"))
        with self._lock, anchored(self.allowed_root), anchored(self.markers_dir):
            intent, receipt = marker.with_suffix(".intent.json"), marker.with_suffix(".receipt.json")
            if intent.exists() or intent.is_symlink() or receipt.exists() or receipt.is_symlink():
                fail("duplicate_call")
            try:
                self.save(intent, {"callId": call_id, "tool": tool_name, "argumentsSha256": hashed(encoded(args)),
                    "scopeSha256": hashed(str(self.allowed_root).encode("utf-8")), "automaticRetry": False})
            except FileExistsError:
                fail("duplicate_call")
            try:
                self._check_cancelled(cancelled)
                if tool_name == "list_files":
                    result = self._list_files(path, args["depth"], cancelled)
                else:
                    with anchored(path.parent):
                        if tool_name == "read_text":
                            raw, text = bounded_text(path)
                            result = {"path": args["path"], "text": text, "bytes": len(raw), "sha256": hashed(raw)}
                        else:
                            result = self._write_text(path, args["path"], args["expectedSha256"], content, cancelled)
                self.save(receipt, {"callId": call_id, "tool": tool_name, "status": "completed", "resultSha256": hashed(encoded(result)),
                    **({key: result[key] for key in ("beforeSha256", "afterSha256", "bytes")} if tool_name == "write_text" else {})})
                return result
            except RuntimeError:
                raise
            except UnicodeError:
                fail("invalid_utf8_text")
            except (OSError, ValueError):
                fail("operation_unverified")

    def _list_files(self, directory, depth, cancelled):
        files, entries, total = [], 0, 0
        def visit(parent, remaining):
            nonlocal entries, total
            self._check_cancelled(cancelled)
            with anchored(parent), os.scandir(parent) as iterator:
                children = []
                for child in iterator:
                    entries += 1
                    if entries > MAX_LIST_ENTRIES:
                        fail("list_limit")
                    children.append(child)
                for child in sorted(children, key=lambda item: item.name):
                    if self.protected(child.name):
                        continue
                    path = self.relative((parent / child.name).relative_to(self.allowed_root).as_posix())
                    info = path.lstat()
                    if stat.S_ISDIR(info.st_mode):
                        plain(path, directory=True)
                        if remaining > 1:
                            visit(path, remaining - 1)
                    else:
                        info = plain(path); total += info.st_size
                        if total > MAX_LIST_BYTES:
                            fail("list_limit")
                        files.append({"path": path.relative_to(self.allowed_root).as_posix(), "bytes": info.st_size})
        visit(directory, depth)
        return {"files": files, "truncated": False}

    def _write_text(self, path, relative, expected, content, cancelled):
        info = plain(path, missing=True)
        before = hashed(bounded_text(path)[0]) if info is not None else None
        if before != expected:
            fail("sha_conflict")
        temporary, own_inode = None, None
        try:
            descriptor, name = tempfile.mkstemp(prefix=".console-codex-", suffix=".tmp", dir=path.parent)
            temporary = Path(name)
            with os.fdopen(descriptor, "wb") as stream:
                own_inode = os.fstat(stream.fileno()).st_ino
                stream.write(content); stream.flush(); os.fsync(stream.fileno())
            # Repeat the actual read/hash immediately before replacing. This
            # detects stale edits, without claiming general external-writer CAS.
            plain(path.parent, directory=True)
            current = hashed(bounded_text(path)[0]) if plain(path, missing=True) is not None else None
            if current != expected:
                fail("sha_conflict")
            if (expected is None and path.exists()) or (expected is not None and not path.exists()):
                fail("sha_conflict")
            self._check_cancelled(cancelled)
            if expected is None:
                # Atomic no-clobber creation: another newly created file is
                # preserved even if it appears after the final absence check.
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    fail("sha_conflict")
                temporary.unlink()
            else:
                os.replace(temporary, path)
            raw, _ = bounded_text(path)
            if raw != content:
                fail("write_unverified")
            return {"path": relative, "beforeSha256": before, "afterSha256": hashed(raw), "bytes": len(raw),
                    "atomicReplacement": True, "optimisticRaceEliminated": False}
        finally:
            if temporary is not None and temporary.exists():
                info = temporary.lstat()
                if stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_ino == own_inode:
                    temporary.unlink()
