"""Read-only repository discovery and edit-activity guards. No publishing or file sync."""
from __future__ import annotations
import ast
from contextlib import closing
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess

_URL = re.compile(r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
_VERSION = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_ACTIVE = {"pending", "claimed", "queued", "starting", "running", "working", "cancelling", "needs_review", "waiting"}
_TERMINAL = {"completed", "succeeded", "success", "noop", "failed", "interrupted", "cancelled", "closed", "idle"}


def _path(value):
    text = str(value)
    if text.startswith("\\\\?\\UNC\\"):
        text = "\\\\" + text[8:]
    elif text.startswith("\\\\?\\"):
        text = text[4:]
    return Path(text).expanduser().resolve()


def _supplied_path(value):
    text = str(value)
    if text.startswith("\\\\?\\UNC\\"):
        text = "\\\\" + text[8:]
    elif text.startswith("\\\\?\\"):
        text = text[4:]
    return Path(text).expanduser().absolute()


def _overlap(left, right):
    try:
        a, b = _path(left), _path(right)
        return a == b or a.is_relative_to(b) or b.is_relative_to(a)
    except (OSError, ValueError, TypeError):
        return False


def _unredirected(path):
    p = Path(path).absolute()
    for part in (p, *p.parents):
        if os.path.lexists(part):
            s = part.lstat()
            if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
                raise ValueError("redirected_path")
    return p.resolve()


def _url(value):
    match = _URL.fullmatch(str(value).strip())
    if not match:
        raise ValueError("unsupported_or_credential_bearing_remote")
    return "https://github.com/" + match[1] + "/" + match[2]


class ReadOnlyGit:
    """Only metadata commands; never status, filters, hooks, fetch, or lazy fetch."""
    def __call__(self, root, *args):
        allowed = (args in (("rev-parse", "--show-toplevel"), ("rev-parse", "--git-common-dir"),
                            ("symbolic-ref", "--short", "HEAD"))
                   or args in (("remote", "get-url", "--all", "origin"),
                               ("remote", "get-url", "--push", "--all", "origin")))
        if not allowed:
            raise ValueError("non_metadata_git_command")
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
        result = subprocess.run(["git", "-C", str(root), "-c", "core.fsmonitor=false", *args],
                                capture_output=True, text=True, encoding="utf-8", errors="strict", timeout=15,
                                env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise ValueError("git_metadata_unavailable")
        return result.stdout.strip()


def probe_existing_lock(path):
    """Probe the existing one-byte OS lock without creating or writing a lock file."""
    p = Path(path)
    if not p.exists():
        return "absent"
    try:
        _unredirected(p)
        with p.open("rb") as stream:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        return "free"
    except OSError as error:
        return "held" if error.errno in {errno.EACCES, errno.EAGAIN} else "unknown"
    except ValueError:
        return "unknown"


def _lifecycle(event):
    """Read only typed boundaries; never inspect message text."""
    if not isinstance(event, dict):
        return None
    typ, payload = event.get("type"), event.get("payload")
    if not isinstance(payload, dict):
        return None
    kind = payload.get("type")
    if typ == "event_msg":
        if kind in {"task_started", "turn_started"}:
            return "active"
        if kind in {"task_complete", "turn_complete", "turn_aborted", "turn_finished"}:
            return "idle"
        if kind == "agent_message" and payload.get("phase") == "final":
            return "idle"
    if typ == "turn_context":
        return "active"
    if typ == "response_item" and kind == "message":
        if payload.get("role") == "user":
            return "active"
        if payload.get("role") == "assistant" and payload.get("phase") == "final":
            return "idle"
    return None


def rollout_activity(path, max_bytes=4 * 1024 * 1024):
    """Bounded tail. A missing boundary or changing file means unverified, not idle."""
    try:
        p = _unredirected(path)
        first = p.stat()
        budget = min(65536, max_bytes)
        while True:
            offset = max(0, first.st_size - budget)
            with p.open("rb") as stream:
                stream.seek(offset)
                raw = stream.read(budget)
            if offset:
                raw = raw.partition(b"\n")[2]
            state = None
            for line in raw.splitlines():
                try:
                    current = _lifecycle(json.loads(line))
                except (ValueError, UnicodeError):
                    continue
                if current is not None:
                    state = current
            last = p.stat()
            if (first.st_size, first.st_mtime_ns) != (last.st_size, last.st_mtime_ns):
                return {"state": "unknown", "reason": "rollout_changed_during_read"}
            if raw and not raw.endswith(b"\n"):
                return {"state": "unknown", "reason": "rollout_partial_tail"}
            if state is not None:
                return {"state": state, "reason": "typed_rollout_boundary", "bytesRead": len(raw)}
            if not offset or budget >= max_bytes:
                return {"state": "unknown", "reason": "no_boundary_in_bounded_tail", "bytesRead": len(raw)}
            budget = min(max_bytes, budget * 2)
    except (OSError, ValueError):
        return {"state": "unknown", "reason": "rollout_unavailable"}


def desktop_codex_activity(root, state_paths=None):
    """Inspect actual schema and nonarchived matching cwd; omit titles and all text."""
    paths = list(state_paths) if state_paths is not None else list((Path.home() / ".codex").glob("state_*.sqlite"))
    records, warnings = [], []
    if not paths:
        warnings.append({"code": "desktop_codex_state_unavailable"})
    for database in paths:
        try:
            p = _unredirected(database)
            with closing(sqlite3.connect(p.as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
                columns = {row[1] for row in db.execute("PRAGMA table_info(threads)")}
                if not {"id", "cwd", "rollout_path", "archived"} <= columns:
                    warnings.append({"code": "desktop_codex_schema_unverified", "database": str(p)})
                    continue
                order = " ORDER BY updated_at DESC" if "updated_at" in columns else ""
                rows = db.execute("SELECT id,cwd,rollout_path FROM threads WHERE archived=0" + order).fetchall()
            for ident, cwd, rollout in rows:
                if cwd and _overlap(root, cwd):
                    activity = rollout_activity(rollout)
                    records.append({"threadId": ident, "cwd": str(_path(cwd)), **activity})
                    # Actual active evidence is already sufficient to defer publication.
                    if activity["state"] == "active":
                        return {"records": records, "warnings": warnings}
        except (OSError, ValueError, sqlite3.Error):
            warnings.append({"code": "desktop_codex_state_unreadable", "database": str(database)})
    return {"records": records, "warnings": warnings}


def _record_roots(record):
    if not isinstance(record, dict):
        return []
    roots = [record[k] for k in ("path", "root", "cwd", "projectRoot", "workspaceRoot", "allowedRoot", "sourceRoot") if record.get(k)]
    for key in ("workspace", "binding", "payload", "codexWork", "nativeWork", "source", "spec"):
        if isinstance(record.get(key), dict):
            roots.extend(_record_roots(record[key]))
    return roots


class RepositoryBindingDiscovery:
    def __init__(self, *, blender_store=None, blender_catalog=None, developer_settings=None,
                 workflow_snapshot=None, known_roots=(), git_reader=None, desktop_activity=None,
                 state_paths=None, lock_probe=probe_existing_lock, edit_ownership=None):
        self.blender_store = blender_store
        self.blender_catalog = blender_catalog
        self.developer_settings = developer_settings
        self.workflow_snapshot = workflow_snapshot
        self.known_roots = known_roots
        self.git = git_reader or ReadOnlyGit()
        self.desktop_activity = desktop_activity
        self.state_paths = state_paths
        self.lock_probe = lock_probe
        self.edit_ownership = edit_ownership

    @staticmethod
    def _get(callback, default):
        if callback is None:
            return default
        return callback() if callable(callback) else callback

    def discover(self):
        candidates, warnings, missing = [], [], {}
        def add(value, source, expected_url=""):
            if value:
                candidates.append((value, source, expected_url))
            else:
                try:
                    safe_url = _url(expected_url) if expected_url else ""
                except ValueError:
                    safe_url = ""
                warnings.append({"code": "configured_repository_path_missing", "source": source,
                                 "repositoryUrl": safe_url})
                if safe_url:
                    missing.setdefault(safe_url.casefold(), safe_url)
        def obtain(callback, default, source):
            try:
                value = self._get(callback, default)
                if not isinstance(value, type(default)) and not (source == "blender_catalog" and isinstance(value, dict)):
                    raise ValueError("configuration_shape_invalid")
                return value
            except (OSError, ValueError, TypeError):
                warnings.append({"code": "configuration_unreadable", "source": source})
                return default
        store = obtain(self.blender_store, {}, "blender_store")
        catalog = obtain(self.blender_catalog, [], "blender_catalog")
        settings = obtain(self.developer_settings, {}, "developer_settings")
        workflow = obtain(self.workflow_snapshot, {}, "workflow_snapshot")
        if settings.get("sourceRoot"):
            add(settings["sourceRoot"], "developer_settings")
        repository_paths = store.get("repositoryPaths", {})
        for slug, value in repository_paths.items():
            add(value, "blender_repository_binding", "https://github.com/" + slug if not slug.startswith("https://") else slug)
        for project in store.get("projects", {}).values():
            if isinstance(project, dict):
                add(project.get("projectRoot") or project.get("blendFile"), "blender_project", project.get("repositoryUrl", ""))
        for entry in catalog.get("repositories", []) if isinstance(catalog, dict) else catalog:
            if not isinstance(entry, dict):
                continue
            url = entry.get("repositoryUrl") or entry.get("remoteUrl", "")
            local = entry.get("path") or entry.get("directory") or entry.get("projectRoot")
            if not local and url:
                try:
                    slug = _url(url).removeprefix("https://github.com/").casefold()
                    local = next((v for k, v in repository_paths.items() if k.casefold() == slug), None)
                except ValueError:
                    pass
            add(local, "catalog", url)
        for key in ("projects", "bindings", "workspaces"):
            for entry in workflow.get(key, []):
                if isinstance(entry, dict):
                    add(entry.get("workspaceRoot") or entry.get("root") or entry.get("path"), "workflow_" + key,
                        entry.get("repositoryUrl", ""))
        for entry in self.known_roots:
            add(entry.get("path") or entry.get("root"), "environment", entry.get("repositoryUrl", "")) if isinstance(entry, dict) else add(entry, "environment")
        repositories = {}
        for value, source, expected_url in candidates:
            try:
                supplied = _unredirected(_supplied_path(value))
                if not supplied.exists():
                    raise ValueError("configured_repository_path_missing")
                candidate = supplied.parent if supplied.is_file() else supplied
                root = _unredirected(self.git(candidate, "rev-parse", "--show-toplevel"))
                fetch = self.git(root, "remote", "get-url", "--all", "origin").splitlines()
                push = self.git(root, "remote", "get-url", "--push", "--all", "origin").splitlines()
                if len(fetch) != 1 or len(push) != 1 or _url(fetch[0]).casefold() != _url(push[0]).casefold():
                    raise ValueError("ambiguous_origin")
                url = _url(fetch[0])
                if expected_url and _url(expected_url).casefold() != url.casefold():
                    raise ValueError("configured_repository_remote_mismatch")
                branch = self.git(root, "symbolic-ref", "--short", "HEAD")
                if not branch:
                    raise ValueError("detached_or_missing_branch")
                key = os.path.normcase(str(root))
                if key in repositories:
                    continue
                ident = url.rsplit("/", 1)[-1][:50] + "-" + hashlib.sha256(key.encode()).hexdigest()[:12]
                sync, sync_warnings, sync_manifest = self._sync_files(root)
                versions = self._version_sources(root)
                warnings.extend(sync_warnings)
                if not versions:
                    warnings.append({"code": "authoritative_version_source_missing", "path": str(root)})
                repositories[key] = {"id": ident, "path": str(root), "repositoryUrl": url, "remote": "origin",
                                     "branch": branch, "enabled": True, "syncFiles": sync, "versionSources": versions, "exclude": [],
                                     "syncError": "Saved build sync manifest is invalid; repair the explicit saved-file mappings before publication."
                                     if any(w["code"] == "saved_sync_manifest_invalid" for w in sync_warnings) else "",
                                     "syncManifest": sync_manifest}
            except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as error:
                code = str(error) if isinstance(error, ValueError) and re.fullmatch(r"[a-z_]+", str(error)) else "repository_metadata_unavailable"
                warnings.append({"code": code, "source": source, "path": str(value)})
        by_remote = {}
        for item in repositories.values():
            previous = by_remote.setdefault(item["repositoryUrl"].casefold(), item["path"])
            if previous != item["path"]:
                warnings.append({"code": "multiple_local_roots_for_remote", "path": item["path"], "otherPath": previous})
        # A named cloud repository with no checkout remains editable in settings.
        # Its current branch is unknown, so never invent a branch or enable it.
        for key, url in missing.items():
            if key in by_remote:
                continue
            ident = url.rsplit("/", 1)[-1][:50] + "-" + hashlib.sha256(("remote:" + key).encode()).hexdigest()[:12]
            repositories["remote:" + key] = {"id": ident, "path": "", "repositoryUrl": url, "remote": "origin",
                                           "branch": "", "enabled": False, "syncFiles": [], "versionSources": [],
                                           "exclude": [], "syncError": "", "syncManifest": None}
        return {"repositories": list(repositories.values()), "warnings": warnings}

    @staticmethod
    def _sync_files(root):
        manifest = root / "tools/build_sources.json"
        if not manifest.is_file():
            return [], [], None
        try:
            _unredirected(manifest)
            raw = manifest.read_bytes()
            data = json.loads(raw.decode("utf-8-sig"))
            if any(not Path(x["source"]).is_absolute() for x in data["dependencies"]):
                raise ValueError("dependency_source_must_be_absolute")
            # Preserve the existing helper's dependency-first, scene-last publication order.
            mappings = [*[{"source": x["source"], "target": x["destination"]} for x in data["dependencies"]],
                        {"source": data["sourceScene"], "target": data["sceneDestination"]}]
            results, targets, warnings = [], set(), []
            for mapping in mappings:
                source = _unredirected(root / mapping["source"] if not Path(mapping["source"]).is_absolute() else mapping["source"])
                target = Path(mapping["target"])
                if target.is_absolute() or ".." in target.parts or not target.parts or ".git" in {p.casefold() for p in target.parts}:
                    raise ValueError("invalid_saved_sync_target")
                destination = _unredirected(root / target)
                if not destination.is_relative_to(root) or destination == source or str(destination).casefold() in targets:
                    raise ValueError("invalid_saved_sync_target")
                targets.add(str(destination).casefold())
                results.append({"source": str(source), "target": target.as_posix()})
                if not source.is_file():
                    warnings.append({"code": "configured_sync_source_missing", "path": str(source), "target": target.as_posix()})
            if manifest.read_bytes() != raw:
                raise ValueError("saved_sync_manifest_changed")
            return results, warnings, {"path": str(manifest), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        except (OSError, ValueError, KeyError, TypeError):
            return [], [{"code": "saved_sync_manifest_invalid", "path": str(manifest)}], None

    @staticmethod
    def _version_sources(root):
        sources = []
        def add(path, kind, key, name, scope, value):
            if isinstance(value, (tuple, list)) and all(type(x) is int for x in value):
                value = ".".join(map(str, value))
            if isinstance(value, str) and _VERSION.fullmatch(value):
                sources.append({"path": path.relative_to(root).as_posix(), "kind": kind, "key": key, "name": name, "scope": scope})
        for relative, key, name, scope in (("app-manifest.json", "version", "Application", "**"),
                                           ("package.json", "version", "Package", "**"),
                                           ("node_library/manifest.json", "library_version", "Node library", "node_library/**")):
            p = root / relative
            try:
                _unredirected(p)
                if p.is_file():
                    add(p, "json", key, name, scope, json.loads(p.read_text(encoding="utf-8-sig")).get(key))
            except (OSError, ValueError, TypeError):
                pass
        unity = root / "ProjectSettings/ProjectSettings.asset"
        if unity.is_file():
            try:
                match = re.search(r"^\s*bundleVersion:\s*([^\r\n]+)$", _unredirected(unity).read_text(encoding="utf-8-sig"), re.M)
                if match:
                    add(unity, "unity", "bundleVersion", "Unity application", ["Assets/**", "Packages/**", "ProjectSettings/**"], match[1].strip())
            except (OSError, ValueError):
                pass
        for p in sorted((root / "addons").glob("*/__init__.py")):
            try:
                tree = ast.parse(_unredirected(p).read_text(encoding="utf-8-sig"))
                for node in tree.body:
                    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "bl_info" for t in node.targets):
                        info = ast.literal_eval(node.value)
                        add(p, "python_ast", "bl_info.version", info.get("name") or p.parent.name,
                            p.parent.relative_to(root).as_posix() + "/**", info.get("version"))
            except (OSError, ValueError, SyntaxError, TypeError, AttributeError):
                pass
        for p in sorted(root.glob("*/blender_manifest.toml")):
            try:
                import tomllib
                info = tomllib.loads(_unredirected(p).read_text(encoding="utf-8-sig"))
                add(p, "text", "version", info.get("name") or p.parent.name,
                    p.parent.relative_to(root).as_posix() + "/**", info.get("version"))
            except (OSError, ValueError, TypeError):
                pass
        return sources

    def busy_reason(self, root, *, developer_operation=None, owned_developer_lock=False):
        """Reason string or None. Unverified overlapping activity is explicitly deferred."""
        root = _path(root)
        try:
            snapshot = self._get(self.workflow_snapshot, {})  # exactly one callback read
            ownership = self._get(self.edit_ownership, [])
        except (OSError, ValueError, TypeError):
            return "Work/edit ownership state could not be verified."
        records = []
        for key in ("jobs", "nativeDispatches", "threads", "editOwnership"):
            records.extend(snapshot.get(key, []))
        for key in ("nativeApp", "native_app"):
            native = snapshot.get(key, {})
            if isinstance(native, dict):
                records.extend(native.get("threads", []))
        records.extend(ownership)
        if developer_operation:
            records.append(developer_operation)
        for item in records:
            if not isinstance(item, dict) or item.get("archived") is True:
                continue
            paths = _record_roots(item)
            if paths and not any(_overlap(root, p) for p in paths):
                continue
            status = item.get("status") or item.get("state")
            if item.get("active") is True or status in _ACTIVE:
                return "An active or unresolved Work/edit operation overlaps this repository."
            if status not in _TERMINAL and item.get("active") is not False:
                return "Work/edit operation state is unverified; publication deferred."
        try:
            common = Path(self.git(root, "rev-parse", "--git-common-dir"))
            common = common if common.is_absolute() else root / common
            # Trusted server-only thread lease; callers must prove they retain
            # this exact lock. Other Work/Desktop ownership checks still run.
            state = "owned" if owned_developer_lock is True else self.lock_probe(common / "console-developer-update.lock")
            if state in {"held", "unknown"}:
                return "The shared Git developer-update lock is held or could not be verified."
        except (OSError, ValueError, subprocess.SubprocessError):
            return "Shared Git operation state could not be verified."
        try:
            native = self.desktop_activity(root) if callable(self.desktop_activity) else self.desktop_activity
            if native is None:
                native = desktop_codex_activity(root, self.state_paths)
        except (OSError, ValueError, TypeError):
            return "Desktop Codex activity could not be verified; publication deferred."
        for item in native.get("records", []):
            if item.get("archived") is True or not item.get("cwd") or not _overlap(root, item["cwd"]):
                continue
            if item.get("state") == "active":
                return "Desktop Codex has an active turn in this repository or an overlapping parent directory."
            if item.get("state") != "idle":
                return "Desktop Codex lifecycle boundary is unverified; publication deferred."
        if native.get("warnings"):
            return "Desktop Codex state schema or availability is unverified; publication deferred."
        return None
