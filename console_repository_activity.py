"""Current-turn repository scope declarations; never write Codex runtime history.

This is a cooperative ownership protocol, not a heuristic that guesses edits from
messages or commands. Unknown and invalid declarations retain the original guard.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import tempfile
import uuid

MAX_SCAN_BYTES = 4 * 1024 * 1024
MAX_CLAIM_BYTES = 64 * 1024
SCHEMA = 1


class ScopeError(ValueError):
    pass


def safe_path(value):
    text = str(value)
    if text.startswith("\\\\?\\UNC\\"):
        text = "\\\\" + text[8:]
    elif text.startswith("\\\\?\\"):
        text = text[4:]
    p = Path(text).expanduser().absolute()
    for part in (p, *p.parents):
        if os.path.lexists(part):
            s = part.lstat()
            if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
                raise ScopeError("redirected_path")
    return p.resolve()


def _token(value):
    if not isinstance(value, str) or not value or len(value) > 128 or any(ord(c) < 33 for c in value):
        raise ScopeError("invalid_identity")
    return value


def _thread_id(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise ScopeError("invalid_thread_id") from error


def _identity(p, s):
    return {"path": str(p), "device": s.st_dev, "inode": s.st_ino}


def _stamp(s):
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)


def scan_rollout(path, max_bytes=MAX_SCAN_BYTES):
    """Bounded metadata scan. No message text or command arguments leave this API."""
    try:
        p = safe_path(path)
        first = p.stat()
        if not stat.S_ISREG(first.st_mode):
            raise ScopeError("not_regular_rollout")
        budget = min(65536, max_bytes)
        while True:
            offset = max(0, first.st_size - budget)
            with p.open("rb") as stream:
                stream.seek(offset)
                window = stream.read(budget)
                stream.seek(0)
                head = stream.read(min(65536, first.st_size))
            raw, line_offset = window, offset
            if offset:
                prefix, separator, raw = window.partition(b"\n")
                line_offset += len(prefix) + len(separator)
            state, turn_id, starts, malformed = None, None, [], False
            for line in raw.splitlines(keepends=True):
                at = line_offset
                line_offset += len(line)
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeError):
                    malformed = True
                    continue
                if not isinstance(event, dict) or not isinstance(event.get("payload"), dict):
                    continue
                typ, payload = event.get("type"), event["payload"]
                kind = payload.get("type")
                if typ == "event_msg" and kind in {"task_started", "turn_started"}:
                    state, turn_id = "active", payload.get("turn_id")
                    starts.append({"offset": at, "turnId": turn_id})
                elif typ == "turn_context":
                    state = "active"
                    context_id = payload.get("turn_id")
                    turn_id = context_id
                elif typ == "event_msg" and kind in {"task_complete", "turn_complete", "turn_aborted", "turn_finished"}:
                    state = "idle"
                elif typ == "event_msg" and kind == "agent_message" and payload.get("phase") in {"final", "final_answer"}:
                    state = "idle"
                elif typ == "response_item" and kind == "message":
                    if payload.get("role") == "user":
                        # Desktop emits the initial user after task_started /
                        # turn_context. Preserve that typed identity; every new
                        # user boundary still invalidates earlier declarations.
                        state = "active"
                        starts.append({"offset": at, "turnId": turn_id})
                    elif payload.get("role") == "assistant" and payload.get("phase") in {"final", "final_answer"}:
                        state = "idle"
            last = p.stat()
            if _stamp(first) != _stamp(last):
                return {"state": "unknown", "reason": "rollout_changed_during_read"}
            fingerprint = {**_identity(p, first), "size": first.st_size, "mtimeNs": first.st_mtime_ns,
                           "headSha256": hashlib.sha256(head).hexdigest(), "tailOffset": offset,
                           "tailSha256": hashlib.sha256(window).hexdigest()}
            owner_thread = None
            first_line, separator, _ = head.partition(b"\n")
            if separator:
                try:
                    meta = json.loads(first_line)
                    if meta.get("type") == "session_meta" and isinstance(meta.get("payload"), dict):
                        owner_thread = meta["payload"].get("id")
                except (ValueError, UnicodeError, AttributeError):
                    pass
            common = {"identity": _identity(p, first), "fingerprint": fingerprint, "ownerThreadId": owner_thread,
                      "bytesRead": len(raw), "currentTurnId": turn_id, "starts": starts}
            if raw and not raw.endswith(b"\n"):
                return {**common, "state": "unknown", "reason": "rollout_partial_tail"}
            if malformed:
                return {**common, "state": "unknown", "reason": "rollout_malformed_tail"}
            if state is not None and (state == "idle" or turn_id or not offset or budget >= max_bytes):
                return {**common, "state": state, "reason": "typed_rollout_boundary"}
            if not offset or budget >= max_bytes:
                return {**common, "state": "unknown", "reason": "no_boundary_in_bounded_tail"}
            budget = min(max_bytes, budget * 2)
    except FileNotFoundError:
        return {"state": "unknown", "reason": "rollout_unavailable", "unavailableKind": "missing"}
    except (OSError, ValueError, TypeError, RuntimeError):
        return {"state": "unknown", "reason": "rollout_unavailable"}


def _read_json(path, limit=MAX_CLAIM_BYTES):
    p = safe_path(path)
    with p.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ScopeError("metadata_too_large")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ScopeError("metadata_not_object")
    return value, hashlib.sha256(raw).hexdigest()


def _native_receipt_matches(evidence, thread_id, turn_id, status):
    """Verify the preserved native JSON, not only an integration's summary."""
    try:
        raw, digest = _read_json(evidence.get("nativeReceiptPath"), 256 * 1024)
        turns, thread = raw.get("turns"), raw.get("thread")
        if (digest != evidence.get("nativeReceiptSha256") or type(raw.get("schemaVersion")) is not int
                or raw["schemaVersion"] != 1 or not isinstance(thread, dict) or thread.get("id") != thread_id
                or not isinstance(turns, list) or not turns or not isinstance(turns[0], dict)
                or turns[0].get("id") != turn_id or turns[0].get("status") != status):
            return False
        items = turns[0].get("items", [])
        if not isinstance(items, list):
            return False
        for item in items:
            if not isinstance(item, dict):
                return False
            if item.get("type") in {"commandExecution", "command_execution"} and item.get("status") not in {
                    "completed", "failed", "interrupted", "cancelled", "succeeded"}:
                return False
        return True
    except (OSError, ValueError, TypeError):
        return False


def _atomic_json(path, value):
    p = safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    safe_path(p.parent)
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=".scope-", suffix=".tmp", dir=p.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        safe_path(p)
        os.replace(temporary, p)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def exact_git_root(value):
    p = safe_path(value)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
    result = subprocess.run(["git", "-C", str(p), "-c", "core.fsmonitor=false", "rev-parse", "--show-toplevel"],
                            capture_output=True, text=True, encoding="utf-8", errors="strict", timeout=15,
                            env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode or safe_path(result.stdout.strip()) != p:
        raise ScopeError("not_exact_git_root")
    return str(p)


class ScopeStore:
    def __init__(self, directory=None, *, state_paths=None, git_root_reader=exact_git_root):
        self.directory = Path(directory) if directory is not None else Path.home() / ".codex" / "repository-edit-scopes"
        self.state_paths = state_paths
        self.git_root_reader = git_root_reader
        self._snapshot_names = None

    def begin_snapshot(self):
        """Fresh filename inventory avoids thousands of nonexistent-file probes.

        The inventory only removes redundant I/O inside one metadata snapshot.
        Every actual claim still receives full JSON/rollout verification.
        """
        try:
            directory = safe_path(self.directory)
            with os.scandir(directory) as entries:
                self._snapshot_names = {entry.name for entry in entries if entry.name.endswith(".json")}
            return True
        except FileNotFoundError:
            self._snapshot_names = set()
            return True
        except (OSError, ValueError, TypeError):
            self._snapshot_names = None
            return False

    def _known_absent(self, thread_id):
        return self._snapshot_names is not None and _thread_id(thread_id) + ".json" not in self._snapshot_names

    def _file(self, thread_id):
        return safe_path(self.directory / (_thread_id(thread_id) + ".json"))

    def thread_record(self, thread_id):
        ident = _thread_id(thread_id)
        paths = list(self.state_paths) if self.state_paths is not None else list((Path.home() / ".codex").glob("state_*.sqlite"))
        records = []
        for database in paths:
            p = safe_path(database)
            with closing(sqlite3.connect(p.as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
                columns = {r[1] for r in db.execute("PRAGMA table_info(threads)")}
                if not {"id", "cwd", "rollout_path", "archived"} <= columns:
                    raise ScopeError("desktop_codex_schema_unverified")
                row = db.execute("SELECT id,cwd,rollout_path,archived FROM threads WHERE id=?", (ident,)).fetchone()
                if row:
                    records.append(row)
        if len(records) != 1 or records[0][3]:
            raise ScopeError("owner_thread_not_current")
        return {"threadId": ident, "cwd": str(safe_path(records[0][1])), "rolloutPath": str(safe_path(records[0][2]))}

    def declare(self, thread_id, mode, roots=()):
        if mode not in {"read_only", "edit"} or (mode == "read_only" and roots) or (mode == "edit" and not roots):
            raise ScopeError("invalid_scope_mode_or_roots")
        record = self.thread_record(thread_id)
        scan = scan_rollout(record["rolloutPath"])
        if (scan.get("state") != "active" or not scan.get("currentTurnId") or not scan.get("identity", {}).get("inode")
                or scan.get("ownerThreadId") != record["threadId"]):
            raise ScopeError("current_active_turn_unverified")
        turn_id = _token(scan["currentTurnId"])
        edit_roots = sorted(set(self.git_root_reader(root) for root in roots))
        value = {"schemaVersion": SCHEMA, "kind": "scope", "threadId": record["threadId"], "turnId": turn_id,
                 "mode": mode, "editRoots": edit_roots, "cwd": record["cwd"], "anchor": scan["fingerprint"],
                 "declaredAt": datetime.now(timezone.utc).isoformat()}
        # Validation before atomic publication catches a new turn during Git root reads.
        if self.thread_record(thread_id) != record or not self._scope_matches(value, scan_rollout(record["rolloutPath"])):
            raise ScopeError("owner_turn_changed_during_declaration")
        _atomic_json(self._file(thread_id), value)
        self._snapshot_names = None
        return value

    @staticmethod
    def _anchor_matches(anchor, scan):
        try:
            fp = scan["fingerprint"]
            if not isinstance(anchor, dict) or any(type(anchor.get(k)) is not int for k in ("device", "inode", "size", "mtimeNs", "tailOffset")):
                return False
            if any(anchor.get(k) != fp.get(k) for k in ("path", "device", "inode")) or not 0 <= anchor["tailOffset"] <= anchor["size"] <= fp["size"]:
                return False
            length = anchor["size"] - anchor["tailOffset"]
            if length > MAX_SCAN_BYTES:
                return False
            p = safe_path(fp["path"])
            first = p.stat()
            with p.open("rb") as stream:
                stream.seek(anchor["tailOffset"])
                raw = stream.read(length)
                stream.seek(0)
                head = stream.read(min(65536, anchor["size"]))
            return (_stamp(first) == _stamp(p.stat()) and _identity(p, first) == scan["identity"]
                    and first.st_size == fp["size"] and first.st_mtime_ns == fp["mtimeNs"]
                    and hashlib.sha256(raw).hexdigest() == anchor.get("tailSha256")
                    and hashlib.sha256(head).hexdigest() == anchor.get("headSha256"))
        except (OSError, ValueError, KeyError, TypeError):
            return False

    @classmethod
    def _scope_matches(cls, value, scan):
        return (scan.get("state") == "active" and value.get("turnId") == scan.get("currentTurnId")
                and value.get("threadId") == scan.get("ownerThreadId")
                and cls._anchor_matches(value.get("anchor"), scan)
                and not any(s["offset"] >= value["anchor"]["size"] for s in scan.get("starts", [])))

    def resolve(self, thread_id, rollout_path, *, scan=None):
        """Invalid/absent claims never turn active or unknown records into idle."""
        try:
            ident = _thread_id(thread_id)
            if self._known_absent(ident):
                return {"status": "undeclared", "reason": "edit_scope_undeclared"}
            value, _ = _read_json(self._file(ident))
        except FileNotFoundError:
            return {"status": "undeclared", "reason": "edit_scope_undeclared"}
        except (OSError, ValueError, TypeError):
            return {"status": "unverified", "reason": "edit_scope_unreadable"}
        scan = scan if scan is not None else scan_rollout(rollout_path)
        if value.get("schemaVersion") != SCHEMA or value.get("threadId") != ident:
            return {"status": "unverified", "reason": "edit_scope_invalid"}
        if value.get("kind") == "terminal":
            try:
                evidence, digest = _read_json(value.get("evidencePath"), 256 * 1024)
                evidence_valid = (digest == value.get("evidenceSha256") and evidence.get("source") == "codex_app.read_thread"
                                  and evidence.get("threadId") == ident and evidence.get("turnId") == value.get("turnId")
                                  and evidence.get("status") == value.get("verifiedStatus")
                                  and evidence.get("rolloutFingerprint") == value.get("fingerprint")
                                  and _native_receipt_matches(evidence, ident, value.get("turnId"), value.get("verifiedStatus")))
            except (OSError, ValueError, TypeError):
                evidence_valid = False
            if (value.get("verifiedStatus") in {"interrupted", "completed"} and value.get("turnId") == scan.get("currentTurnId")
                    and scan.get("ownerThreadId") == ident
                    and value.get("fingerprint") == scan.get("fingerprint") and scan.get("reason") == "typed_rollout_boundary"
                    and evidence_valid):
                return {"status": "terminal", "reason": "native_terminal_attestation", "turnId": value["turnId"],
                        "verifiedStatus": value["verifiedStatus"]}
            return {"status": "unverified", "reason": "terminal_attestation_stale"}
        mode, roots = value.get("mode"), value.get("editRoots")
        if (value.get("kind") != "scope" or mode not in {"read_only", "edit"} or not isinstance(roots, list)
                or (mode == "read_only" and roots) or (mode == "edit" and not roots)
                or any(not isinstance(r, str) or not Path(r).is_absolute() for r in roots)):
            return {"status": "unverified", "reason": "edit_scope_invalid"}
        try:
            if any(str(safe_path(r)) != r for r in roots) or not isinstance(value.get("turnId"), str):
                return {"status": "unverified", "reason": "edit_scope_invalid"}
        except (OSError, ValueError, TypeError):
            return {"status": "unverified", "reason": "edit_scope_invalid"}
        if not self._scope_matches(value, scan):
            return {"status": "unverified", "reason": "edit_scope_stale_or_turn_unverified", "editRoots": roots}
        return {"status": "verified", "mode": mode, "editRoots": roots, "turnId": value["turnId"],
                "reason": "current_turn_scope_declaration"}

    def candidate_roots(self, thread_id):
        """Only expand candidates. A stale declaration must never grant exemption."""
        try:
            ident = _thread_id(thread_id)
            if self._known_absent(ident):
                return []
            value, _ = _read_json(self._file(ident))
            roots = value.get("editRoots")
            if (value.get("schemaVersion") == SCHEMA and value.get("threadId") == ident
                    and value.get("kind") == "scope" and value.get("mode") == "edit" and isinstance(roots, list)
                    and roots and all(isinstance(r, str) and Path(r).is_absolute() and str(safe_path(r)) == r for r in roots)):
                return roots
        except (OSError, ValueError, TypeError):
            pass
        return []

    def attest_terminal(self, thread_id, *, verified_turn_id, verified_status, evidence_path):
        """Trusted integration: caller must first obtain the native app receipt.

        A receipt is stored independently from runtime history. It cannot survive
        even one appended event, and notLoaded is never a terminal status.
        """
        record = self.thread_record(thread_id)
        ident, turn = record["threadId"], _token(verified_turn_id)
        if verified_status not in {"interrupted", "completed"}:
            raise ScopeError("native_status_not_terminal")
        evidence, digest = _read_json(evidence_path, 256 * 1024)
        if (evidence.get("source") != "codex_app.read_thread" or evidence.get("threadId") != ident
                or evidence.get("turnId") != turn or evidence.get("status") != verified_status
                or not _native_receipt_matches(evidence, ident, turn, verified_status)):
            raise ScopeError("native_terminal_receipt_mismatch")
        scan = scan_rollout(record["rolloutPath"])
        if (scan.get("reason") != "typed_rollout_boundary" or scan.get("currentTurnId") != turn
                or scan.get("ownerThreadId") != ident):
            raise ScopeError("attested_rollout_turn_unverified")
        if evidence.get("rolloutFingerprint") != scan.get("fingerprint"):
            raise ScopeError("rollout_changed_since_native_receipt")
        value = {"schemaVersion": SCHEMA, "kind": "terminal", "threadId": ident, "turnId": turn,
                 "verifiedStatus": verified_status, "fingerprint": scan["fingerprint"],
                 "evidencePath": str(safe_path(evidence_path)), "evidenceSha256": digest,
                 "attestedAt": datetime.now(timezone.utc).isoformat()}
        if self.thread_record(thread_id) != record or scan_rollout(record["rolloutPath"]).get("fingerprint") != scan["fingerprint"]:
            raise ScopeError("rollout_changed_during_attestation")
        _atomic_json(self._file(ident), value)
        self._snapshot_names = None
        return value

    def revoke(self, thread_id):
        p = self._file(thread_id)
        try:
            p.unlink()
        except FileNotFoundError:
            pass
        self._snapshot_names = None

