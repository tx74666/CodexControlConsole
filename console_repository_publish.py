"""Explicit multi-repository commits and exact-commit pushes.

GET/preview never sync or contact remotes. The HTTP caller must enforce a trusted
local developer request. Journals intentionally survive failures: a new request
first resumes the original commit, with its original destination and message.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import ast
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import weakref
import xml.etree.ElementTree as ET


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
_REQUEST = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,99}\Z")
_SHA = re.compile(r"[0-9a-f]{40,64}\Z")
_PRIVATE_PARTS = {".git", ".venv", "venv", "node_modules", "__pycache__", "cache",
                  "private", "workflow-private", "browserprofiles", "logs", "tmp", "temp"}
_PRIVATE_NAMES = {".env", ".npmrc", ".pypirc", "credentials.json", "secrets.json",
                  "installation.json", "local-store-identity.json", "publisher-state.json"}
_DEFAULT_NAMING = {"preset": "version", "fallbackTitle": "更新进度 {datetime}",
                   "subtitle": "", "notes": "", "includeSummary": True}
_LIVE = {}


class RepositoryPublishError(ValueError):
    """A sanitized, user-facing validation error."""


class _GitFailure(Exception):
    def __init__(self, code, detail="", returncode=None):
        super().__init__(code)
        self.code, self.detail, self.returncode = code, detail, returncode


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json_sha(value):
    return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _now():
    return datetime.now(timezone.utc).isoformat()


def _read(path, default=None):
    try:
        for attempt in range(12):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                break
            except PermissionError:
                if attempt == 11:
                    raise
                time.sleep(.01)
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        raise RepositoryPublishError("发布记录损坏或不可读，请保留记录后核对；不会重新提交。") from exc
    if not isinstance(value, dict):
        raise RepositoryPublishError("发布记录格式错误，请先核对；不会重新提交。")
    return value


def _atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(20):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(.01)
    finally:
        temporary.unlink(missing_ok=True)


def _safe_path(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            st = part.lstat()
            if part.is_symlink() or getattr(st, "st_file_attributes", 0) & 0x400:
                raise RepositoryPublishError("路径含符号链接或重解析点，请使用真实目录。")
    return path.resolve()


def _relative(value):
    text = str(value).replace("\\", "/")
    path = Path(text)
    if not text or path.is_absolute() or ":" in text or "\0" in text or ".." in path.parts or ".git" in {p.lower() for p in path.parts}:
        raise RepositoryPublishError("仓库内文件路径必须是安全的相对路径。")
    return path.as_posix()


def _matches(path, scope):
    if not scope:
        return True
    if isinstance(scope, list):
        return any(_matches(path, item) for item in scope)
    scope = str(scope).replace("\\", "/").strip("/")
    return fnmatch.fnmatchcase(path, scope) if any(c in scope for c in "*?[") else path == scope or path.startswith(scope + "/")


def _excluded(path, patterns):
    pieces = path.replace("\\", "/").lower().split("/")
    return (any(p in _PRIVATE_PARTS for p in pieces) or pieces[-1] in _PRIVATE_NAMES
            or pieces[-1].startswith(".env.") or any(_matches(path, p) for p in patterns))


def _stable(path):
    path = _safe_path(path)
    before = path.stat()
    if not path.is_file():
        raise RepositoryPublishError("文件不是普通已保存文件。")
    digest = hashlib.sha256()
    with _read_lease(path), path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    key = lambda s: (s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_ino)
    if key(before) != key(after):
        raise RepositoryPublishError("文件正在写入，请保存完成后重试。")
    return {"bytes": after.st_size, "sha256": digest.hexdigest()}


@contextmanager
def _read_lease(path):
    """Windows refuses an existing writer; no app or process is terminated.

    Other systems use stable byte/stat proofs and repeated gates. This isn't a
    claim to discover paused writers on systems without Windows share leases.
    """
    if os.name != "nt":
        yield
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x08000000, None)
    if handle == ctypes.c_void_p(-1).value:
        code = ctypes.get_last_error()
        if code in {32, 33}:
            raise RepositoryPublishError("文件仍有写入句柄，请等待保存完成；不会关闭应用。")
        raise OSError(code, "Unable to hold read lease")
    try:
        yield
    finally:
        kernel.CloseHandle(handle)


@contextmanager
def _file_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if not stream.seek(0, os.SEEK_END):
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RepositoryPublishError("另一处正在操作该仓库，请等待完成。") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _process_key(pid):
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
            handle = kernel.OpenProcess(0x1000, False, int(pid))
            if not handle:
                return None if ctypes.get_last_error() == 87 else "unknown"
            try:
                exit_code = wintypes.DWORD()
                if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return "unknown"
                if exit_code.value != 259:
                    return None
                times = [wintypes.FILETIME() for _ in range(4)]
                if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                    return "unknown"
                return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
            finally:
                kernel.CloseHandle(handle)
        return Path(f"/proc/{int(pid)}/stat").read_text().split(") ", 1)[1].split()[19]
    except (OSError, ValueError, IndexError):
        return None


class RepositoryPublishService:
    def __init__(self, state_dir, *, discovery=None, busy_check=None, allowed=True, test_mode=False):
        self.state_dir = _safe_path(state_dir)
        self.allowed = bool(allowed)
        self._test_mode = bool(test_mode)
        self._sandbox = self.state_dir.parent
        if self._test_mode and not self._sandbox.is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise RepositoryPublishError("测试模式只允许临时隔离目录。")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._ops = self.state_dir / "operations"
        self._pending_dir = self.state_dir / "pending"
        self._ops.mkdir(exist_ok=True)
        self._pending_dir.mkdir(exist_ok=True)
        self._settings_path = self.state_dir / "settings.json"
        self._mutex = threading.RLock()
        self._lease = threading.local()
        self._queue = []
        self._worker = None
        self._starting = False
        self._owner = uuid.uuid4().hex
        self._pid_key = _process_key(os.getpid())
        self._busy_check = busy_check
        self._discovery = discovery
        self._warnings = []
        with _file_lock(self.state_dir / "settings.lock"):
            if not self._settings_path.exists():
                found = discovery() if discovery else []
                if isinstance(found, dict):
                    self._warnings = list(found.get("warnings", []))
                    found = found.get("repositories", [])
                settings = self._normalize({"repositories": found or [], "naming": dict(_DEFAULT_NAMING)})
                settings["warnings"] = self._warnings
                _atomic(self._settings_path, settings)

    def _git(self, root, *arguments, data=None, index=None, timeout=35, config=None):
        executable = shutil.which("git")
        if not executable:
            raise _GitFailure("missing_git")
        env = os.environ.copy()
        # Remove environment-based repository redirects, not credentials, SSH,
        # config, hooks, or clean/LFS filters belonging to the user.
        for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_PREFIX"):
            env.pop(key, None)
        env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never", GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1")
        if index is not None:
            env["GIT_INDEX_FILE"] = str(index)
        if config:
            offset = int(env.get("GIT_CONFIG_COUNT", "0"))
            for number, (key, value) in enumerate(config, offset):
                env["GIT_CONFIG_KEY_" + str(number)] = key
                env["GIT_CONFIG_VALUE_" + str(number)] = value
            env["GIT_CONFIG_COUNT"] = str(offset + len(config))
        if self._test_mode:
            env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_SYSTEM=str(self.state_dir / "empty-config"),
                       GIT_CONFIG_GLOBAL=str(self.state_dir / "empty-config"), GIT_ALLOW_PROTOCOL="file")
            if not Path(root).resolve().is_relative_to(self._sandbox):
                raise RepositoryPublishError("测试操作超出隔离目录。")
        try:
            process = subprocess.run([executable, "-C", str(root), *arguments], input=data,
                                     capture_output=True, env=env, timeout=timeout,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except subprocess.TimeoutExpired as exc:
            raise _GitFailure("timeout") from exc
        except OSError as exc:
            raise _GitFailure("git_unavailable") from exc
        if process.returncode:
            text = process.stderr.decode("utf-8", "replace").lower()
            category = ("lfs" if "lfs" in text else "authentication" if any(v in text for v in ("authentication", "could not read username", "terminal prompts disabled", "publickey"))
                        else "permissions" if any(v in text for v in ("permission denied", "403", "access denied"))
                        else "rules" if any(v in text for v in ("protected branch", "repository rule", "gh013", "hook declined", "pre-receive"))
                        else "remote_changed" if any(v in text for v in ("non-fast-forward", "fetch first", "stale info")) else "git_failed")
            raise _GitFailure(category, returncode=process.returncode)
        return process.stdout

    def _text(self, root, *args, **kwargs):
        return self._git(root, *args, **kwargs).decode("utf-8", "replace").strip()

    def _normalize(self, payload):
        if not isinstance(payload, dict) or not isinstance(payload.get("repositories", []), list):
            raise RepositoryPublishError("设置必须包含仓库列表。")
        repositories, identifiers = [], set()
        for raw in payload.get("repositories", []):
            if not isinstance(raw, dict) or not _ID.fullmatch(str(raw.get("id", ""))):
                raise RepositoryPublishError("仓库编号无效。")
            identifier = str(raw["id"])
            if identifier in identifiers:
                raise RepositoryPublishError("仓库编号重复。")
            identifiers.add(identifier)
            location = str(raw.get("path", "")).strip()
            if location and not Path(location).is_absolute():
                raise RepositoryPublishError("仓库目录必须是绝对路径。")
            branch = str(raw.get("branch", "")).strip()
            if not branch and location and Path(location).exists():
                try:
                    branch = self._text(Path(location), "symbolic-ref", "--short", "HEAD")
                except (_GitFailure, RepositoryPublishError):
                    pass
            remote = str(raw.get("remote", "origin")).strip()
            if not _ID.fullmatch(remote) or (branch and (branch.startswith("-") or any(c in branch for c in "\n\r\0: ~^?*[\\") or ".." in branch)):
                raise RepositoryPublishError("远端名称或分支无效。")
            sync = []
            for item in raw.get("syncFiles", []):
                if not isinstance(item, dict) or not Path(str(item.get("source", ""))).is_absolute():
                    raise RepositoryPublishError("同步来源必须是明确的绝对文件路径。")
                sync.append({"source": str(item["source"]), "target": _relative(item.get("target", ""))})
            versions = []
            for item in raw.get("versionSources", []):
                if not isinstance(item, dict):
                    raise RepositoryPublishError("版本来源格式无效。")
                scope = item.get("scope", "")
                if not isinstance(scope, (str, list)) or isinstance(scope, list) and any(not isinstance(v, str) for v in scope):
                    raise RepositoryPublishError("版本范围必须是路径或匹配模式。")
                versions.append({"path": _relative(item.get("path", "")), "kind": str(item.get("kind", "json")),
                                 "key": str(item.get("key", "")), "name": str(item.get("name", "")), "scope": scope})
            exclude = raw.get("exclude", [])
            if not isinstance(exclude, list) or any(not isinstance(v, str) or not v for v in exclude):
                raise RepositoryPublishError("排除范围必须是路径列表。")
            manifest = raw.get("syncManifest")
            if manifest is not None:
                if not isinstance(manifest, dict) or not isinstance(manifest.get("bytes"), int) or manifest["bytes"] < 0 or not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("sha256", ""))):
                    raise RepositoryPublishError("同步清单来源证明格式无效。")
                manifest_path = str(manifest.get("path", ""))
                if not manifest_path:
                    raise RepositoryPublishError("同步清单来源路径缺失。")
                manifest = {"path": manifest_path, "bytes": manifest["bytes"], "sha256": manifest["sha256"]}
            repositories.append({"id": identifier, "path": location, "repositoryUrl": str(raw.get("repositoryUrl", "")).strip(),
                                 "remote": remote, "branch": branch, "enabled": bool(raw.get("enabled", True)),
                                 "syncFiles": sync, "versionSources": versions, "exclude": exclude,
                                 "syncError": str(raw.get("syncError", ""))[:1000], "syncManifest": manifest})
        naming = dict(_DEFAULT_NAMING)
        supplied = payload.get("naming", {})
        if not isinstance(supplied, dict):
            raise RepositoryPublishError("命名设置格式无效。")
        naming.update({k: supplied[k] for k in naming if k in supplied})
        if naming["preset"] not in {"version", "module_version", "progress"}:
            raise RepositoryPublishError("提交命名模式无效。")
        for key in ("fallbackTitle", "subtitle", "notes"):
            naming[key] = str(naming[key])[:16000]
        naming["includeSummary"] = bool(naming["includeSummary"])
        return {"repositories": repositories, "naming": naming}

    def _settings(self):
        return _read(self._settings_path)

    def configure(self, payload):
        if not self.allowed:
            raise RepositoryPublishError("当前入口不允许提交推送。")
        with self._mutex, _file_lock(self.state_dir / "settings.lock"):
            settings = self._normalize(payload)
            previous = self._settings()
            previous_repos = {r["id"]: r for r in previous["repositories"]}
            rediscovered = None
            for repo in settings["repositories"]:
                old = previous_repos.get(repo["id"], {})
                if old.get("syncError") or old.get("syncManifest"):
                    fresh = None
                    if self._discovery:
                        if rediscovered is None:
                            found = self._discovery()
                            rows = found.get("repositories", []) if isinstance(found, dict) else found
                            rediscovered = self._normalize({"repositories": rows or []})["repositories"]
                        fresh = next((r for r in rediscovered if r["path"] == repo["path"] and r["syncFiles"] == repo["syncFiles"] and not r.get("syncError")), None)
                    if fresh:
                        repo.update(syncError="", syncManifest=fresh.get("syncManifest"))
                        continue
                    # A missing field or an empty list cannot silently turn a
                    # failed saved-scene manifest into permission to push it.
                    if not repo["syncFiles"] or repo["syncFiles"] == old.get("syncFiles", []):
                        repo.update(syncError=old.get("syncError", ""), syncManifest=old.get("syncManifest"))
                    else:
                        root = _safe_path(repo["path"])
                        targets = set()
                        for mapping in repo["syncFiles"]:
                            _stable(Path(mapping["source"]))
                            destination = _safe_path(root / mapping["target"])
                            if not destination.is_relative_to(root) or os.path.normcase(str(destination)) in targets or _excluded(mapping["target"], repo["exclude"]):
                                raise RepositoryPublishError("修正同步映射仍不安全，保留同步错误。")
                            targets.add(os.path.normcase(str(destination)))
                        repo.update(syncError="", syncManifest=None)
            settings["warnings"] = previous.get("warnings", [])
            _atomic(self._settings_path, settings)
        return self.status()

    @property
    def busy(self):
        with self._mutex:
            local = bool(self._queue or self._worker and self._worker.is_alive())
        latest = self.operation()
        return local or bool(latest and latest.get("status") in {"working", "queued"})

    def status(self):
        settings = self._settings()
        return {"settings": settings, "warnings": settings.get("warnings", []), "operation": self.operation(),
                "warningsSource": "initial_discovery", "allowed": self.allowed, "busy": self.busy}

    def operation(self, request_id=None):
        if request_id is not None and not _REQUEST.fullmatch(str(request_id)):
            raise RepositoryPublishError("请求编号无效。")
        if request_id is None:
            latest = _read(self.state_dir / "latest.json", {})
            request_id = latest.get("requestId")
        if not request_id:
            return None
        receipt = _read(self._ops / (str(request_id) + ".json"))
        if receipt and receipt.get("status") in {"working", "queued"}:
            owner = receipt.get("owner", {})
            actual_key = _process_key(owner.get("pid", 0))
            owner_ref = _LIVE.get(owner.get("nonce"))
            local_owner = owner_ref() if owner_ref else None
            local_active = bool(local_owner and (local_owner._starting or local_owner._queue or local_owner._worker and local_owner._worker.is_alive()))
            alive = (local_active if owner.get("pid") == os.getpid()
                     else actual_key == "unknown" or bool(actual_key and actual_key == owner.get("processKey")))
            if not alive:
                receipt["status"] = "verification_required"
                receipt["message"] = "上次操作中断，请点击重试；先核对原提交，不会重复提交。"
        return receipt

    def _repo(self, repo):
        if not repo["path"] or not Path(repo["path"]).exists():
            raise RepositoryPublishError("仓库目录不存在，请检查设置。")
        root = _safe_path(repo["path"])
        top = _safe_path(self._text(root, "rev-parse", "--show-toplevel"))
        if os.path.normcase(str(root)) != os.path.normcase(str(top)):
            raise RepositoryPublishError("请选择仓库根目录，不能使用其子目录。")
        gitdir = _safe_path(self._text(root, "rev-parse", "--absolute-git-dir"))
        common_text = self._text(root, "rev-parse", "--git-common-dir")
        common = _safe_path(Path(common_text) if Path(common_text).is_absolute() else root / common_text)
        branch = self._text(root, "symbolic-ref", "--short", "HEAD")
        if not repo["branch"] or branch != repo["branch"]:
            raise RepositoryPublishError("当前分支与设置不符，请自行切换或修正设置。")
        self._git(root, "check-ref-format", "refs/heads/" + branch)
        fetch = self._text(root, "remote", "get-url", "--all", repo["remote"]).splitlines()
        push = self._text(root, "remote", "get-url", "--push", "--all", repo["remote"]).splitlines()
        if len(fetch) != 1 or len(push) != 1:
            raise RepositoryPublishError("远端必须只有一个读取地址和一个推送地址。")
        expected = repo["repositoryUrl"]
        if self._test_mode:
            for url in (*fetch, *push, expected):
                if "://" in url or not Path(url).is_absolute() or not _safe_path(url).is_relative_to(self._sandbox):
                    raise RepositoryPublishError("隔离测试只允许本地 bare 远端。")
                if not (Path(url) / "HEAD").is_file() or not (Path(url) / "objects").is_dir():
                    raise RepositoryPublishError("测试远端不是 bare 仓库。")
            slugs = [os.path.normcase(str(Path(v).resolve())) for v in (*fetch, *push, expected)]
        else:
            slugs = [self._github(v) for v in (*fetch, *push, expected)]
        if not slugs[0] or len(set(slugs)) != 1:
            raise RepositoryPublishError("读取、推送和配置地址必须指向同一个 GitHub 仓库。")
        identity = {"root": str(root), "gitdir": str(gitdir), "common": str(common), "branch": branch,
                    "remote": repo["remote"], "fetchUrl": fetch[0], "pushUrl": push[0], "repository": slugs[0]}
        return root, gitdir, common, identity

    @staticmethod
    def _github(url):
        match = re.fullmatch(r"(?:https://github\.com/|ssh://git@github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?", url)
        return match.group(1).lower() if match else ""

    def _busy_reason(self, root):
        reason = self._busy_check(root) if self._busy_check else None
        if reason:
            raise RepositoryPublishError(str(reason))

    def _sync_contract(self, repo):
        if repo.get("syncError"):
            raise RepositoryPublishError("已保存同步清单无效，请修正并验证同步映射：" + repo["syncError"])
        manifest = repo.get("syncManifest")
        if manifest:
            root = _safe_path(repo["path"])
            source = _safe_path(root / manifest["path"])
            if not source.is_relative_to(root):
                raise RepositoryPublishError("同步清单来源超出仓库。")
            try:
                actual = _stable(source)
            except OSError as exc:
                raise RepositoryPublishError("导入的同步清单已缺失，请重新核对配置。") from exc
            if actual != {"bytes": manifest["bytes"], "sha256": manifest["sha256"]}:
                raise RepositoryPublishError("导入的同步清单已变化，请重新保存并核对同步配置。")

    def owns_developer_lock(self, root):
        """Internal callback hint; true only for this worker thread's held lock."""
        return getattr(self._lease, "root", None) == os.path.normcase(str(Path(root).resolve()))

    @contextmanager
    def _repo_locks(self, context):
        root, _, common = context[:3]
        # Busy probing happens before taking the shared developer lock. Once it
        # is held, the trusted callback may omit re-probing that same lock only.
        self._busy_reason(root)
        with _file_lock(common / "console-repository-publish.lock"), _file_lock(common / "console-developer-update.lock"):
            self._lease.root = os.path.normcase(str(root))
            try:
                yield
            finally:
                self._lease.root = None

    def _blockers(self, root, gitdir, common, *, own_index_lock=False):
        if (gitdir / "index").exists():
            _safe_path(gitdir / "index")
        for base in {gitdir, common}:
            for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply", "sequencer", "BISECT_START"):
                if (base / name).exists():
                    raise RepositoryPublishError("仓库正在合并、变基或处理历史，请先完成该操作。")
            locks = [base / "HEAD.lock", base / "config.lock", base / "packed-refs.lock"]
            locks.extend((base / "refs").rglob("*.lock") if (base / "refs").exists() else [])
            if any(p.exists() for p in locks) or not own_index_lock and (gitdir / "index.lock").exists():
                raise RepositoryPublishError("Git 正在使用锁，请等待；不会移除其他操作的锁。")
        # Existing Console developer-update uses this same lock file. Merely
        # existing isn't busy; taking its advisory lock detects a live owner.
        self._busy_reason(root)

    def _snapshot(self, repo, context, *, own_index_lock=False):
        root, gitdir, common, identity = context
        self._blockers(root, gitdir, common, own_index_lock=own_index_lock)
        head = self._text(root, "rev-parse", "HEAD")
        index_path = gitdir / "index"
        index_sha = _sha(index_path.read_bytes()) if index_path.exists() else None
        config_sha = _sha(self._git(root, "config", "--null", "--list"))
        status = self._git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames")
        records = status.split(b"\0")
        changed = []
        for record in records:
            if not record:
                continue
            xy = record[:2].decode("ascii", "replace")
            if xy != "??" and xy[0] != " ":
                raise RepositoryPublishError("保留已有暂存选择，请先提交或取消该选择。")
            path = record[3:].decode("utf-8", "surrogateescape")
            if _excluded(path, repo["exclude"]):
                continue
            location = _safe_path(root / _relative(path))
            proof = _stable(location) if location.exists() else {"deleted": True}
            changed.append({"path": path, "status": xy, **proof})
        if self._git(root, "ls-files", "--unmerged", "-z"):
            raise RepositoryPublishError("仓库存在未解决冲突，请先处理。")
        if self._text(root, "rev-parse", "HEAD") != head or (_sha(index_path.read_bytes()) if index_path.exists() else None) != index_sha:
            raise RepositoryPublishError("仓库在检查期间发生变化，请稍后重试。")
        result = {"head": head, "indexSha": index_sha, "configSha": config_sha, "identity": identity,
                  "files": sorted(changed, key=lambda item: item["path"])}
        result["fingerprint"] = _json_sha(result)
        return result

    def _versions(self, root, sources, files):
        result = []
        # Two root manifests describe one application. The application manifest
        # is authoritative; package.json is only its fallback.
        if any(s["path"] == "app-manifest.json" for s in sources):
            sources = [s for s in sources if s["path"] != "package.json"]
        if files:
            selected = set()
            for file in files:
                matching = [(i, s) for i, s in enumerate(sources) if _matches(file["path"], s["scope"])]
                def specificity(source):
                    scopes = source["scope"] if isinstance(source["scope"], list) else [source["scope"]]
                    return max((len(re.split(r"[*?\[]", v)[0].strip("/")) for v in scopes if _matches(file["path"], v)), default=0)
                best = max((specificity(s) for _, s in matching), default=-1)
                selected.update(i for i, s in matching if specificity(s) == best)
            sources = [s for i, s in enumerate(sources) if i in selected]
        for source in sources:
            if files and not any(_matches(f["path"], source["scope"]) for f in files):
                continue
            item = {"name": source["name"] or Path(source["path"]).stem, "path": source["path"], "version": "", "scope": source["scope"]}
            try:
                location = _safe_path(root / source["path"])
                stable = _stable(location)
                text = location.read_text(encoding="utf-8-sig")
                kind, key = source["kind"], source["key"]
                if kind in {"json", "app-manifest", "package"}:
                    value = json.loads(text)
                    for part in (key or "version").split("."):
                        value = value[part]
                elif kind in {"unity", "unity_yaml", "text", "yaml"}:
                    pattern = re.escape(key or ("bundleVersion" if kind in {"unity", "unity_yaml"} else "version"))
                    match = re.search(r"(?m)^\s*" + pattern + r"\s*[:=]\s*[\"']?([^\r\n\"']+)", text)
                    if not match:
                        raise ValueError("key missing")
                    value = match.group(1).strip()
                elif kind in {"python_ast", "bl_info"}:
                    tree = ast.parse(text)
                    name = (key or "bl_info.version").split(".")[0]
                    assignments = [n.value for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))
                                   and any(isinstance(t, ast.Name) and t.id == name for t in (n.targets if isinstance(n, ast.Assign) else [n.target]))]
                    if len(assignments) != 1:
                        raise ValueError("ambiguous assignment")
                    value = ast.literal_eval(assignments[0])
                    parts = (key or "bl_info.version").split(".")[1:]
                    if name == "bl_info" and not parts:
                        parts = ["version"]
                    for part in parts:
                        value = value[part]
                elif kind in {"xml", "csproj"}:
                    nodes = [n for n in ET.fromstring(text).iter() if n.tag.split("}")[-1] == (key or "Version")]
                    values = {n.text.strip() for n in nodes if n.text and n.text.strip()}
                    if len(values) != 1:
                        raise ValueError("ambiguous XML version")
                    value = values.pop()
                else:
                    raise ValueError("unsupported kind")
                if isinstance(value, (tuple, list)) and all(isinstance(v, int) for v in value):
                    value = ".".join(map(str, value))
                if not isinstance(value, (str, int, float)) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+\-]{0,79}", str(value)):
                    raise ValueError("invalid version")
                if _stable(location) != stable:
                    raise ValueError("source changed")
                item["version"] = str(value)
            except (OSError, ValueError, KeyError, TypeError, SyntaxError, RepositoryPublishError, ET.ParseError):
                item["message"] = "版本来源缺失、变化或无法唯一读取，使用进度标题。"
            result.append(item)
        return result

    def _message(self, repo, snapshot, naming):
        root = Path(snapshot["identity"]["root"])
        sources = repo["versionSources"]
        if not sources:
            first = next((p for p in ("app-manifest.json", "package.json") if (root / p).is_file()), None)
            sources = [{"path": first, "kind": "json", "key": "version", "name": root.name, "scope": ""}] if first else []
        versions = self._versions(root, sources, snapshot["files"])
        valid = [v for v in versions if v["version"]]
        title = naming["fallbackTitle"].replace("{datetime}", datetime.now().strftime("%Y-%m-%d %H:%M"))
        if naming["preset"] == "version" and len(versions) == 1 and len(valid) == 1:
            title = valid[0]["version"]
        elif naming["preset"] == "module_version" and valid and len(valid) == len(versions):
            title = " / ".join(v["name"] + " " + v["version"] for v in valid)
        title = " ".join(title.replace("\0", "").splitlines()).strip()[:240] or "更新进度"
        paragraphs = [naming[k].strip() for k in ("subtitle", "notes") if naming[k].strip()]
        if versions:
            paragraphs.append("版本来源：\n" + "\n".join("- " + v["name"] + ": " + (v["version"] or "未确认") + " (" + v["path"] + ")" for v in versions))
        if naming["includeSummary"] and snapshot["files"]:
            lines = ["文件变更："]
            for item in snapshot["files"][:300]:
                action = "删除" if item.get("deleted") else "新增" if item["status"] == "??" else "修改"
                lines.append(f"- {action} {item['path']}")
            if len(snapshot["files"]) > 300:
                lines.append(f"- 另有 {len(snapshot['files']) - 300} 个文件")
            paragraphs.append("\n".join(lines))
        return title, "\n\n".join(paragraphs).replace("\0", ""), versions

    def preview(self, repo_id=None):
        settings = self._settings()
        selected = [r for r in settings["repositories"] if repo_id is None or r["id"] == repo_id]
        if repo_id is not None and not selected:
            raise RepositoryPublishError("仓库编号不存在。")
        results = []
        commons = {}
        for repo in selected:
            item = {"repoId": repo["id"], "name": Path(repo["path"]).name or repo["id"], "title": "", "body": "", "versions": [], "files": []}
            try:
                self._sync_contract(repo)
                context = self._repo(repo)
                key = os.path.normcase(str(context[2]))
                if key in commons:
                    raise RepositoryPublishError("重复仓库或共享 Git 目录，请只配置一个入口。")
                commons[key] = repo["id"]
                snapshot = self._snapshot(repo, context)
                item["title"], item["body"], item["versions"] = self._message(repo, snapshot, settings["naming"])
                item.update(files=snapshot["files"], fingerprint=snapshot["fingerprint"], status="ready", message="预览已保存文件；提交时会重新核对。")
                if not repo["enabled"]:
                    item.update(status="disabled", message="该仓库未启用，请先启用再提交。")
            except (RepositoryPublishError, _GitFailure, OSError) as exc:
                item.update(status="deferred", message=self._error(exc))
            results.append(item)
        return {"previews": results}

    def run(self, request_id, repo_ids=None):
        if not self.allowed:
            raise RepositoryPublishError("当前入口不允许提交推送。")
        if not _REQUEST.fullmatch(str(request_id)):
            raise RepositoryPublishError("请求编号须为 8–100 个安全字符。")
        if repo_ids is not None and (not isinstance(repo_ids, list) or not repo_ids or any(not isinstance(v, str) for v in repo_ids)):
            raise RepositoryPublishError("仓库选择必须是编号列表。")
        with self._mutex, _file_lock(self.state_dir / "requests.lock"):
            existing = self.operation(request_id)
            if existing:
                return existing
            if self.busy:
                raise RepositoryPublishError("正在处理，请等待原回执；不会重复排队或混入新修改。")
            settings = self._settings()
            wanted = set(repo_ids) if repo_ids is not None else {r["id"] for r in settings["repositories"] if r["enabled"]}
            if wanted - {r["id"] for r in settings["repositories"]}:
                raise RepositoryPublishError("仓库编号不存在。")
            selected = [r for r in settings["repositories"] if r["id"] in wanted]
            receipt = {"requestId": request_id, "status": "queued", "phase": "queued", "message": "已接收，逐仓库处理。",
                       "createdAt": _now(), "updatedAt": _now(), "owner": {"pid": os.getpid(), "processKey": self._pid_key, "nonce": self._owner},
                       "repositories": [{"repoId": r["id"], "name": Path(r["path"]).name or r["id"], "status": "queued", "phase": "queued",
                                         "message": "等待处理", "commitSha": "", "title": "", "body": "", "logs": []} for r in selected]}
            self._starting = True
            _LIVE[self._owner] = weakref.ref(self)
            try:
                _atomic(self._ops / (request_id + ".json"), receipt)
                _atomic(self.state_dir / "latest.json", {"requestId": request_id})
            except Exception:
                self._starting = False
                _LIVE.pop(self._owner, None)
                raise
            self._queue.append((receipt, selected, settings))
            try:
                if not self._worker or not self._worker.is_alive():
                    self._worker = threading.Thread(target=self._drain, daemon=True, name="repository-publish")
                    self._worker.start()
            except (RuntimeError, OSError):
                if not self._worker or not self._worker.is_alive():
                    self._queue.clear()
                    _LIVE.pop(self._owner, None)
                    receipt.update(status="attention", phase="dispatch_failed", message="后台暂时无法启动，请稍后重试；尚未提交或推送。")
                    for item in receipt["repositories"]:
                        item.update(status="deferred", phase="dispatch_failed", message=receipt["message"])
                    self._save(receipt)
            finally:
                self._starting = False
            return json.loads(json.dumps(receipt))

    def _save(self, receipt):
        receipt["updatedAt"] = _now()
        _atomic(self._ops / (receipt["requestId"] + ".json"), receipt)

    def _phase(self, receipt, item, phase, message):
        item.update(status="working", phase=phase, message=message)
        item["logs"].append({"at": _now(), "phase": phase, "message": message})
        self._save(receipt)

    def _drain(self):
        try:
            self._drain_batches()
        finally:
            _LIVE.pop(self._owner, None)

    def _drain_batches(self):
        while True:
            with self._mutex:
                if not self._queue:
                    return
                receipt, selected, settings = self._queue.pop(0)
            try:
                with _file_lock(self.state_dir / "worker.lock"):
                    receipt.update(status="working", phase="repositories")
                    self._save(receipt)
                    duplicates, contexts = set(), {}
                    for repo in selected:
                        try:
                            context = self._repo(repo)
                            key = os.path.normcase(str(context[2]))
                            if key in contexts:
                                duplicates.update({repo["id"], contexts[key]})
                            contexts[key] = repo["id"]
                        except (RepositoryPublishError, _GitFailure, OSError):
                            pass
                    for repo, item in zip(selected, receipt["repositories"]):
                        try:
                            if not repo["enabled"]:
                                raise RepositoryPublishError("该仓库未启用，请先启用再重试。")
                            if repo["id"] in duplicates:
                                raise RepositoryPublishError("重复仓库或共享 Git 目录，请只启用一个入口。")
                            self._run_repo(repo, settings["naming"], receipt, item)
                        except (RepositoryPublishError, _GitFailure, OSError) as exc:
                            item.update(status="deferred", message=self._error(exc))
                        except Exception:
                            item.update(status="verification_required", message="操作中断，保留核对记录；重试会先检查原提交。")
                        try:
                            pending = _read(self._pending_path(repo["id"]))
                            if pending and pending.get("state") != "delivered":
                                item.update(commitSha=pending.get("commitSha", item["commitSha"]), title=pending["title"], body=pending["body"])
                        except RepositoryPublishError as exc:
                            item.update(status="verification_required", message=str(exc))
                        item["logs"].append({"at": _now(), "phase": item["phase"], "message": item["message"]})
                        self._save(receipt)
                    states = {i["status"] for i in receipt["repositories"]}
                    receipt.update(status="success" if states <= {"success", "noop"} else "attention", phase="complete",
                                   message="所有仓库已完成。" if states <= {"success", "noop"} else "部分仓库需要处理，其他仓库已继续完成。")
                    self._save(receipt)
            except (RepositoryPublishError, OSError) as exc:
                receipt.update(status="attention", phase="deferred", message=self._error(exc))
                for item in receipt["repositories"]:
                    if item["status"] in {"queued", "working"}:
                        item.update(status="deferred", message=receipt["message"])
                self._save(receipt)

    @staticmethod
    def _error(exc):
        if isinstance(exc, RepositoryPublishError):
            return str(exc)
        if isinstance(exc, _GitFailure):
            return {"authentication": "认证失败，请检查已配置的 Git 凭证后重试原提交。", "permissions": "没有推送权限，请检查仓库权限。",
                    "rules": "远端规则或 Git hook 拒绝操作，请处理规则后重试。", "lfs": "Git LFS 处理失败，请检查 LFS 安装、对象或认证。",
                    "remote_changed": "远端发生变化，请自行整合；不会强制推送。", "timeout": "Git 操作超时，保留原提交核对状态。",
                    "missing_git": "未找到 Git。"}.get(exc.code, "Git 操作失败，请检查仓库或 Git hook；已保留文件和原提交。")
        return "文件或发布记录不可用，请保存完成后重试。"

    def _sync(self, repo, context):
        root = context[0]
        self._sync_contract(repo)
        self._busy_reason(root)
        records = []
        preflight = self._sync_preflight(repo, root)
        for mapping, source, target, proof in preflight:
            try:
                if _stable(source) != proof:
                    raise RepositoryPublishError("同步来源正在写入，请保存后重试。")
                target_before = _stable(target) if target.exists() else None
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name("." + target.name + ".console-sync-" + uuid.uuid4().hex)
                try:
                    with _read_lease(source), source.open("rb") as src, temporary.open("xb") as dst:
                        shutil.copyfileobj(src, dst, 1024 * 1024)
                        dst.flush()
                        os.fsync(dst.fileno())
                    if _stable(source) != proof or _stable(temporary) != proof:
                        raise RepositoryPublishError("同步来源在复制期间发生变化。")
                    if (_stable(target) if target.exists() else None) != target_before:
                        raise RepositoryPublishError("同步目标被另一处修改，保留该修改。")
                    self._busy_reason(root)
                    if source != target and target_before != proof:
                        os.replace(temporary, target)
                    records.append({"source": str(source), "target": mapping["target"], **proof, "changed": target_before != proof})
                finally:
                    temporary.unlink(missing_ok=True)
            except FileNotFoundError as exc:
                raise RepositoryPublishError("同步来源缺失，请先保存来源文件；本仓库延期。") from exc
        self._verify_sync(repo, context, records)
        return records

    def _sync_preflight(self, repo, root):
        records, targets = [], set()
        for mapping in repo["syncFiles"]:
            source = _safe_path(mapping["source"])
            target = _safe_path(root / mapping["target"])
            if self._test_mode and not source.is_relative_to(self._sandbox):
                raise RepositoryPublishError("测试同步来源超出隔离目录。")
            key = os.path.normcase(str(target))
            if source == target or key in targets or not target.is_relative_to(root):
                raise RepositoryPublishError("同步目标重复、与来源相同或超出仓库。")
            if _excluded(mapping["target"], repo["exclude"]):
                raise RepositoryPublishError("同步目标属于排除或私人范围。")
            targets.add(key)
            try:
                records.append((mapping, source, target, _stable(source)))
            except FileNotFoundError as exc:
                raise RepositoryPublishError("同步来源缺失，请先保存来源文件；本仓库延期。") from exc
        time.sleep(.02 if records else 0)
        if any(_stable(source) != proof for _, source, _, proof in records):
            raise RepositoryPublishError("同步来源正在写入，请保存后重试。")
        return records

    def _verify_sync(self, repo, context, records):
        self._sync_contract(repo)
        for record in records:
            expected = {"bytes": record["bytes"], "sha256": record["sha256"]}
            try:
                if _stable(Path(record["source"])) != expected or _stable(context[0] / record["target"]) != expected:
                    raise RepositoryPublishError("同步来源或目标在处理期间变化，请保存后重试；不会发布混合快照。")
            except FileNotFoundError as exc:
                raise RepositoryPublishError("同步来源或目标在处理期间缺失，本仓库延期。") from exc

    def _remote(self, repo, root):
        alias, config = self._transport(repo, root)
        output = self._text(root, "ls-remote", "--heads", alias, "refs/heads/" + repo["branch"], timeout=35, config=config)
        self._transport_identity(repo, root)
        if not output:
            return None
        rows = output.splitlines()
        if len(rows) != 1 or len(rows[0].split()) != 2 or rows[0].split()[1] != "refs/heads/" + repo["branch"] or not _SHA.fullmatch(rows[0].split()[0]):
            raise RepositoryPublishError("远端分支回执无效。")
        return rows[0].split()[0]

    def _fetch(self, repo, context, expected):
        if expected is None:
            return None
        root = context[0]
        alias, config = self._transport(repo, root)
        private_ref = "refs/console-publish/" + uuid.uuid4().hex + "/remote"
        self._git(root, "fetch", "--no-tags", "--no-write-fetch-head", "--no-recurse-submodules", alias,
                  "refs/heads/" + repo["branch"] + ":" + private_ref, timeout=65, config=config)
        fetched = self._text(root, "rev-parse", private_ref)
        if fetched != expected or self._remote(repo, root) != expected:
            raise RepositoryPublishError("远端在核对期间发生变化，请稍后重试。")
        return fetched

    def _remote_options(self, repo, root):
        try:
            raw = self._git(root, "config", "--null", "--get-regexp", "^remote\\." + re.escape(repo["remote"]) + "\\.")
        except _GitFailure as exc:
            if exc.returncode != 1:
                raise
            raw = b""
        prefix = "remote." + repo["remote"] + "."
        options = []
        for entry in raw.split(b"\0"):
            if not entry:
                continue
            key, value = entry.decode("utf-8", "surrogateescape").split("\n", 1)
            key = key[len(prefix):]
            if key == "mirror" and value.lower() not in {"false", "no", "off", "0"}:
                raise RepositoryPublishError("远端启用了镜像推送，不适用于单分支提交。")
            if key not in {"url", "pushurl", "fetch", "mirror"}:
                options.append((key, value))
        return options

    def _transport_identity(self, repo, root):
        actual = self._repo(repo)[3]
        transport = getattr(self._lease, "transport", None)
        if transport is None:
            options = self._remote_options(repo, root)
            transport = {"identity": actual, "options": options, "optionsSha": _json_sha(options)}
            self._lease.transport = transport
        elif actual != transport["identity"] or _json_sha(self._remote_options(repo, root)) != transport["optionsSha"]:
            raise RepositoryPublishError("远端目标或传输配置在处理期间变化，保留原提交待核对。")
        return transport

    def _transport(self, repo, root):
        # A mutable origin alias cannot be pinned with -c origin.url: Git appends
        # multi-valued URLs. A fresh alias pins transport without changing user
        # config. Effective remote-specific LFS/proxy/upload options are copied;
        # normal hooks still run, receiving this valid ephemeral remote name.
        transport = self._transport_identity(repo, root)
        alias = "console-publish-" + uuid.uuid4().hex
        try:
            self._git(root, "config", "--get-regexp", "^remote\\." + alias + "\\.")
        except _GitFailure as exc:
            if exc.returncode != 1:
                raise
        else:
            raise RepositoryPublishError("临时远端名称冲突，本仓库延期。")
        identity = transport["identity"]
        config = [("remote." + alias + ".url", identity["fetchUrl"]), ("remote." + alias + ".pushurl", identity["pushUrl"])]
        config.extend(("remote." + alias + "." + key, value) for key, value in transport["options"])
        return alias, config

    def _ancestor(self, root, ancestor, descendant):
        if ancestor == descendant:
            return True
        try:
            self._git(root, "merge-base", "--is-ancestor", ancestor, descendant)
            return True
        except _GitFailure as exc:
            if exc.returncode == 1:
                return False
            raise

    def _outgoing_safe(self, root, remote, head, repo):
        revisions = self._text(root, "rev-list", head, *( ["^" + remote] if remote else [] )).splitlines()
        for revision in revisions:
            paths = self._git(root, "diff-tree", "--root", "-m", "--no-commit-id", "--name-only", "-r", "-z", revision)
            if any(_excluded(p.decode("utf-8", "surrogateescape"), repo["exclude"]) for p in paths.split(b"\0") if p):
                raise RepositoryPublishError("待推送历史包含私人或排除路径，请先自行核对历史。")

    def _pending_path(self, repo_id):
        return self._pending_dir / (repo_id + ".json")

    def _run_repo(self, repo, naming, receipt, item):
        self._phase(receipt, item, "check", "核对仓库、分支和活动任务。")
        self._sync_contract(repo)
        context = self._repo(repo)
        root, gitdir, common, identity = context
        with self._repo_locks(context):
            self._lease.transport = None
            transport = self._transport_identity(repo, root)
            self._busy_reason(root)
            pending_path = self._pending_path(repo["id"])
            pending = _read(pending_path)
            if pending and pending.get("state") not in {"delivered", "cancelled_before_commit"}:
                if pending["identity"] != identity or pending["repositorySettingsSha"] != _json_sha(repo):
                    raise RepositoryPublishError("原提交的仓库或配置已变化，请恢复原配置后重试；不会推送到新目标。")
                if pending.get("transportOptionsSha", transport["optionsSha"]) != transport["optionsSha"]:
                    raise RepositoryPublishError("原提交的 LFS 或传输配置已变化，请恢复后重试。")
                self._phase(receipt, item, "verify", "先核对并继续上次原提交。")
                pending = self._recover_commit(repo, context, pending, pending_path)
                if pending.get("state") != "cancelled_before_commit":
                    item.update(commitSha=pending.get("commitSha", ""), title=pending["title"], body=pending["body"])
                    if not pending.get("commitSha"):
                        raise RepositoryPublishError("上次提交结果尚未确认，请核对保留的记录和 Git 锁。")
                    self._push(repo, context, pending, pending_path, receipt, item)
                    return
            self._blockers(root, gitdir, common)
            # Staged work is checked before any explicit source synchronization.
            self._snapshot(repo, context)
            self._phase(receipt, item, "sync", "核对并同步明确指定的已保存文件。")
            item["syncFiles"] = self._sync(repo, context)
            self._save(receipt)
            snapshot = self._snapshot(repo, context)
            title, body, versions = self._message(repo, snapshot, naming)
            item.update(title=title, body=body, versions=versions)
            self._phase(receipt, item, "remote", "核对远端分支及待推送历史。")
            remote = self._remote(repo, root)
            self._fetch(repo, context, remote)
            self._verify_sync(repo, context, item["syncFiles"])
            if remote and not self._ancestor(root, remote, snapshot["head"]):
                raise RepositoryPublishError("远端领先或分叉，请先自行整合；本仓库延期。")
            self._outgoing_safe(root, remote, snapshot["head"], repo)
            if not snapshot["files"] and remote == snapshot["head"]:
                item.update(status="noop", phase="complete", message="没有需要提交或推送的文件。")
                return
            pending = {"state": "prepared", "requestId": receipt["requestId"], "repoId": repo["id"], "identity": identity,
                       "repositorySettingsSha": _json_sha(repo), "parentSha": snapshot["head"], "snapshot": snapshot,
                       "title": title, "body": body, "createdAt": _now(), "commitSha": "", "indexReconciled": not snapshot["files"]}
            pending["transportOptionsSha"] = transport["optionsSha"]
            pending["syncProofs"] = item["syncFiles"]
            if snapshot["files"]:
                self._phase(receipt, item, "commit", "暂存已核对文件并执行正常 Git 提交及 hooks。")
                self._commit(repo, context, snapshot, pending, pending_path)
            else:
                pending.update(commitSha=snapshot["head"], state="committed")
                pending["title"] = self._text(root, "show", "-s", "--format=%s", snapshot["head"])
                pending["body"] = self._text(root, "show", "-s", "--format=%b", snapshot["head"])
                _atomic(pending_path, pending)
            item.update(commitSha=pending["commitSha"], title=pending["title"], body=pending["body"])
            self._push(repo, context, pending, pending_path, receipt, item)

    def _commit(self, repo, context, snapshot, pending, pending_path):
        root, gitdir, common, identity = context
        self._busy_reason(root)
        self._verify_sync(repo, context, pending.get("syncProofs", []))
        if self._repo(repo)[3] != identity or self._snapshot(repo, context)["fingerprint"] != snapshot["fingerprint"]:
            raise RepositoryPublishError("文件或仓库在提交前变化，请重新预览后重试。")
        lock_path = gitdir / "index.lock"
        marker = ("console-repository-publish:" + uuid.uuid4().hex).encode()
        descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        temp_index = self.state_dir / ("index-" + uuid.uuid4().hex)
        attempted = False
        try:
            os.write(descriptor, marker)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            pending.update(lockMarkerSha=_sha(marker), temporaryIndex=str(temp_index), state="staging")
            _atomic(pending_path, pending)
            self._git(root, "read-tree", snapshot["head"], index=temp_index)
            paths = b"".join(item["path"].encode("utf-8", "surrogateescape") + b"\0" for item in snapshot["files"])
            self._git(root, "--literal-pathspecs", "add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul", data=paths, index=temp_index, timeout=90)
            if self._snapshot(repo, context, own_index_lock=True)["fingerprint"] != snapshot["fingerprint"] or self._repo(repo)[3] != identity:
                raise RepositoryPublishError("文件在暂存期间变化，保留工作文件；本仓库延期。")
            self._busy_reason(root)
            self._verify_sync(repo, context, pending.get("syncProofs", []))
            pending["treeSha"] = self._text(root, "write-tree", index=temp_index)
            if pending["treeSha"] == self._text(root, "rev-parse", snapshot["head"] + "^{tree}"):
                # Clean filters may normalize a worktree edit to the original tree.
                pending.update(state="committed", commitSha=snapshot["head"], indexReconciled=True)
                _atomic(pending_path, pending)
                return
            pending.update(state="commit_attempt", commitAttemptAt=_now())
            pending["messageSha"] = _sha(self._git(root, "stripspace", data=(pending["title"] + "\n\n" + pending["body"] + "\n").encode("utf-8")).strip())
            _atomic(pending_path, pending)
            attempted = True
            try:
                self._git(root, "commit", "-F", "-", data=(pending["title"] + "\n\n" + pending["body"] + "\n").encode("utf-8"), index=temp_index, timeout=90)
            except _GitFailure as exc:
                pending["commitError"] = exc.code
                _atomic(pending_path, pending)
                recovered = self._recover_commit(repo, context, pending, pending_path, allow_no_commit=True)
                if not recovered.get("commitSha"):
                    if exc.code == "timeout":
                        raise RepositoryPublishError("提交超时，保留提交记录和自有锁，需先核对后重试。")
                    # Definite hook rejection with unchanged HEAD is not a commit.
                    if recovered.get("state") == "no_commit":
                        attempted = False
                        pending.update(state="releasing_before_commit", noCommitVerified=True)
                        _atomic(pending_path, pending)
                    raise exc
            head = self._text(root, "rev-parse", "HEAD")
            pending["observedHead"] = head
            _atomic(pending_path, pending)
            self._recognize_commit(root, pending, head)
            pending.update(commitSha=head, state="committed")
            _atomic(pending_path, pending)
            self._reconcile(context, pending, pending_path)
            self._verify_sync(repo, context, pending.get("syncProofs", []))
            after = self._snapshot(repo, context)
            # Normalization by filters is permitted; a hook changing source bytes
            # is retained but postpones pushing the created commit.
            before_files = {f["path"]: {k: v for k, v in f.items() if k != "status"} for f in snapshot["files"]}
            unexpected = {f["path"] for f in after["files"]} - set(before_files)
            if unexpected:
                pending["heldReason"] = "Git hook 或另一处新增了工作变更，原提交已保留；请核对后重试原提交。"
                _atomic(pending_path, pending)
                raise RepositoryPublishError(pending["heldReason"])
            for path, old in before_files.items():
                actual = {"path": path, **(_stable(root / path) if (root / path).exists() else {"deleted": True})}
                if actual != old:
                    pending["heldReason"] = "Git hook 或另一处改变了工作文件，原提交已保留；请核对后重试原提交。"
                    _atomic(pending_path, pending)
                    raise RepositoryPublishError(pending["heldReason"])
            if after["configSha"] != snapshot["configSha"] or after["head"] != head:
                raise RepositoryPublishError("提交期间仓库配置或 HEAD 变化，已保留原提交。")
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if not attempted or pending.get("indexReconciled"):
                releasing = not attempted and pending.get("state") != "committed"
                if releasing:
                    pending["state"] = "releasing_before_commit"
                    _atomic(pending_path, pending)
                if lock_path.exists() and _sha(lock_path.read_bytes()) == _sha(marker):
                    lock_path.unlink()
                temp_index.unlink(missing_ok=True)
                if releasing:
                    pending["state"] = "cancelled_before_commit"
                    _atomic(pending_path, pending)

    def _recognize_commit(self, root, pending, head):
        info = self._text(root, "show", "-s", "--format=%P%n%T", head).splitlines()
        if len(info) != 2 or info[0] != pending["parentSha"] or info[1] != pending.get("treeSha"):
            raise RepositoryPublishError("提交结果与记录不符，请核对 HEAD；不会重新提交或推送。")
        if pending.get("messageSha") and _sha(self._git(root, "stripspace", data=self._git(root, "show", "-s", "--format=%B", head)).strip()) != pending["messageSha"]:
            raise RepositoryPublishError("提交消息与记录不符，请核对 hook 或并发提交；不会重新提交或推送。")

    def _recover_commit(self, repo, context, pending, pending_path, allow_no_commit=False):
        root = context[0]
        if pending.get("commitSha"):
            if not self._ancestor(root, pending["commitSha"], self._text(root, "rev-parse", "HEAD")):
                raise RepositoryPublishError("原提交已不在当前历史中，请人工核对；不会重新提交。")
        else:
            head = self._text(root, "rev-parse", "HEAD")
            if head != pending["parentSha"]:
                self._recognize_commit(root, pending, head)
                pending.update(commitSha=head, state="committed")
                _atomic(pending_path, pending)
            elif allow_no_commit and pending.get("commitError") != "timeout":
                pending["state"] = "no_commit"
                return pending
            elif pending.get("state") in {"staging", "releasing_before_commit"} and (not pending.get("commitAttemptAt") or pending.get("noCommitVerified") is True):
                # This durable phase precedes commit_attempt. No commit was
                # dispatched; only an exact owned marker and unchanged original
                # index may be retired, with the old journal retained externally.
                gitdir = context[1]
                index = gitdir / "index"
                lock = gitdir / "index.lock"
                temporary = _safe_path(pending.get("temporaryIndex", ""))
                if not temporary.is_relative_to(self.state_dir) or Path(str(temporary) + ".lock").exists():
                    raise RepositoryPublishError("上次暂存仍有索引写入，请先核对；不会移除锁。")
                original = _sha(index.read_bytes()) if index.exists() else None
                lock_owned = lock.exists() and _sha(lock.read_bytes()) == pending.get("lockMarkerSha")
                already_releasing = pending.get("state") == "releasing_before_commit"
                if original != pending["snapshot"]["indexSha"] or lock.exists() and not lock_owned or not lock.exists() and not already_releasing:
                    raise RepositoryPublishError("上次暂存后的索引或锁已变化，请先核对。")
                if temporary.exists():
                    _stable(temporary)
                pending.update(state="releasing_before_commit", recoveredAt=_now())
                _atomic(pending_path, pending)
                _atomic(self.state_dir / ("precommit-recovery-" + uuid.uuid4().hex + ".json"), pending)
                lock.unlink(missing_ok=True)
                temporary.unlink(missing_ok=True)
                pending["state"] = "cancelled_before_commit"
                _atomic(pending_path, pending)
                return pending
            else:
                raise RepositoryPublishError("上次提交未确认，保留自有记录和锁；请先核对 Git 操作是否结束。")
        if not pending.get("indexReconciled"):
            self._reconcile(context, pending, pending_path)
        return pending

    def _reconcile(self, context, pending, pending_path):
        root, gitdir = context[:2]
        index = gitdir / "index"
        current = _sha(index.read_bytes()) if index.exists() else None
        temporary = _safe_path(pending["temporaryIndex"])
        if not temporary.is_relative_to(self.state_dir) or not temporary.is_file():
            raise RepositoryPublishError("原提交的索引恢复文件缺失，请先核对。")
        expected = _sha(temporary.read_bytes())
        lock = gitdir / "index.lock"
        if current == expected:
            pending["indexReconciled"] = True
            _atomic(pending_path, pending)
            if lock.exists() and _sha(lock.read_bytes()) == pending.get("lockMarkerSha"):
                lock.unlink()
            temporary.unlink(missing_ok=True)
            return
        if current != pending["snapshot"]["indexSha"]:
            raise RepositoryPublishError("已有新的暂存选择，原提交保留；不会覆盖索引。")
        if not lock.exists() or _sha(lock.read_bytes()) not in {pending.get("lockMarkerSha"), pending.get("reconciledIndexSha")}:
            raise RepositoryPublishError("Git 索引锁不属于此任务，原提交保留；不会移除该锁。")
        pending["reconciledIndexSha"] = expected
        _atomic(pending_path, pending)
        with lock.open("wb") as stream:
            stream.write(temporary.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        if (_sha(index.read_bytes()) if index.exists() else None) != current:
            raise RepositoryPublishError("暂存选择在恢复期间变化，保留原提交与锁。")
        os.replace(lock, index)
        pending["indexReconciled"] = True
        _atomic(pending_path, pending)
        temporary.unlink(missing_ok=True)

    def _push(self, repo, context, pending, pending_path, receipt, item):
        root, gitdir, common, identity = context
        self._blockers(root, gitdir, common)
        # A retry may coexist with newly edited files, but never new staging.
        self._snapshot(repo, context)
        if self._repo(repo)[3] != pending["identity"]:
            raise RepositoryPublishError("原提交目标已变化，请恢复配置后重试。")
        sha = pending["commitSha"]
        item["commitSha"] = sha
        self._phase(receipt, item, "verify", "核对原提交是否已送达。")
        try:
            remote = self._remote(repo, root)
            self._fetch(repo, context, remote)
        except _GitFailure as exc:
            pending.update(state="verification_required", pushError=exc.code)
            _atomic(pending_path, pending)
            item.update(status="verification_required", message=self._error(exc))
            return
        if remote and self._ancestor(root, sha, remote):
            pending.update(state="delivered", verifiedAt=_now(), verifiedRemote=remote)
            _atomic(pending_path, pending)
            item.update(status="success", phase="complete", message="已核对原提交在远端，无需重复推送。")
            return
        if remote and not self._ancestor(root, remote, sha):
            raise RepositoryPublishError("远端领先或分叉，请自行整合；保留原提交。")
        self._outgoing_safe(root, remote, sha, repo)
        self._busy_reason(root)
        if self._repo(repo)[3] != identity or self._text(root, "rev-parse", "HEAD") != pending["snapshot"]["head"] and not self._ancestor(root, sha, self._text(root, "rev-parse", "HEAD")):
            raise RepositoryPublishError("仓库历史或目标变化，请先核对原提交。")
        self._phase(receipt, item, "push", "推送原提交并核对远端回执。")
        pending.update(state="push_attempt", pushAttemptAt=_now(), remoteBeforePush=remote)
        _atomic(pending_path, pending)
        error = None
        try:
            alias, config = self._transport(repo, root)
            self._git(root, "push", "--no-follow-tags", alias, sha + ":refs/heads/" + repo["branch"], timeout=100, config=config)
            self._transport_identity(repo, root)
        except _GitFailure as exc:
            error = exc
        except RepositoryPublishError:
            pending.update(state="verification_required", pushError="destination_changed")
            _atomic(pending_path, pending)
            item.update(status="verification_required", phase="verify", message="传输配置在处理期间变化，原提交和固定目标已保留；请恢复配置后核对。")
            return
        try:
            after = self._remote(repo, root)
            self._fetch(repo, context, after)
            delivered = bool(after and self._ancestor(root, sha, after))
        except (_GitFailure, RepositoryPublishError):
            after, delivered = None, False
        if delivered:
            pending.update(state="delivered", verifiedAt=_now(), verifiedRemote=after)
            item.update(status="success", phase="complete", message="原提交已推送并核对成功。")
        elif error and error.code != "timeout" and after == remote:
            pending.update(state="push_failed", pushError=error.code)
            item.update(status="push_failed", phase="push", message=self._error(error))
        else:
            pending.update(state="verification_required", pushError=error.code if error else "verification")
            item.update(status="verification_required", phase="verify", message="推送结果尚未确认；重试会先核对远端并继续原提交。")
        _atomic(pending_path, pending)
