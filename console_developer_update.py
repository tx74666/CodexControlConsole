"""Explicit, local developer source commits; independent of release and installation.

The HTTP controller must additionally enforce local, trusted developer requests.
No request can choose a remote, ref, command, or a set of unpreviewed files.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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


REPOSITORY = "tx74666/CodexControlConsole"
WEB_URL = "https://github.com/" + REPOSITORY
BRANCH = "main"
_REQUEST = re.compile(r"[A-Za-z0-9_-]{8,100}\Z")
_SOURCE_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".css", ".html", ".json", ".toml",
                    ".yml", ".yaml", ".ps1", ".sh", ".md", ".txt", ".svg", ".ico"}
_EXCLUDED_PARTS = {".git", ".venv", "venv", "node_modules", "__pycache__", "cache", "work", "localdocs",
                   "private", "workflow-private", "build", "dist", "release", "generated",
                   "browserprofiles", "logs", "tmp", "temp"}
_EXCLUDED_NAMES = {".env", ".npmrc", ".pypirc", ".gitattributes", ".lfsconfig", "installation.json", "local-store-identity.json",
                   "publisher-state.json", "settings.json", "credentials.json", "secrets.json"}
_PENDING = {"working", "unknown", "push_failed"}
_LIVE_OWNERS = set()


class DeveloperUpdateError(ValueError):
    """An already sanitized error safe to return to the local UI."""


class _GitFailure(Exception):
    def __init__(self, code, returncode=None):
        super().__init__(code)
        self.returncode = returncode


class ConsoleDeveloperUpdateService:
    def __init__(self, state_dir, *, repo_path=None, runtime_version="", allowed=True,
                 test_remote=None):
        self.state_dir = Path(state_dir).resolve()
        self.runtime_version = str(runtime_version)
        self.allowed = bool(allowed)
        self._lock = threading.RLock()
        self._running = set()
        self._volatile = {}
        self._receipts = {}
        self._owner_id = uuid.uuid4().hex
        # Tests may explicitly supply a local bare remote. Never expose this in HTTP.
        self._test_remote = Path(test_remote).resolve() if test_remote is not None else None
        if self._test_remote is not None:
            if not (self._test_remote / "HEAD").is_file() or not (self._test_remote / "objects").is_dir():
                raise DeveloperUpdateError("测试远端必须是本机临时 bare 仓库。")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._hooks_path = self.state_dir / "disabled-hooks"
        self._hooks_path.mkdir(exist_ok=True)
        self._settings_path = self.state_dir / "settings.json"
        self._operations_dir = self.state_dir / "operations"
        self._operations_dir.mkdir(exist_ok=True)
        if repo_path is not None and not self._settings_path.exists():
            self.configure(False, str(repo_path))

    @property
    def busy(self):
        # A stale working receipt is also a reason not to silently retire the host.
        operation = self.operation()
        return bool(self._running or operation and operation["status"] == "working")

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _read_json(path, default):
        for attempt in range(8):
            try:
                result = json.loads(path.read_text(encoding="utf-8"))
                return result if isinstance(result, dict) else default
            except PermissionError:
                if attempt != 7:
                    time.sleep(.01)
            except (OSError, ValueError):
                return default
        return default

    @staticmethod
    def _atomic_json(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(value, stream, ensure_ascii=False, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            for attempt in range(8):
                try:
                    os.replace(temporary, path)
                    break
                except PermissionError:
                    if attempt == 7:
                        raise
                    time.sleep(.02)
        finally:
            temporary.unlink(missing_ok=True)

    def _settings(self):
        return self._read_json(self._settings_path, {"enabled": False, "sourceRoot": "", "lastRequestId": ""})

    @contextmanager
    def _file_lock(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            if not stream.tell():
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
                raise DeveloperUpdateError("另一处正在更新源码，请等待完成后再试。") from exc
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _git(self, root, *arguments, data=None, index=None, timeout=25):
        executable = shutil.which("git")
        if not executable:
            raise _GitFailure("missing_git")
        if self._hooks_path.is_symlink() or any(self._hooks_path.iterdir()):
            raise _GitFailure("hook_directory_changed")
        env = os.environ.copy()
        for key in tuple(env):
            if key.startswith("GIT_") or key in {"GCM_INTERACTIVE", "SSH_ASKPASS"}:
                env.pop(key, None)
        env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never", GIT_ASKPASS="", SSH_ASKPASS="",
                   GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1")
        if index is not None:
            env["GIT_INDEX_FILE"] = str(index)
        command = [executable, "-C", str(root), "-c", "core.fsmonitor=false", "-c",
                   "core.untrackedCache=false", "-c", "credential.interactive=false", "-c",
                   "push.followTags=false", "-c", "core.hooksPath=" + str(self._hooks_path), *arguments]
        try:
            process = subprocess.run(command, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     timeout=timeout, env=env,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise _GitFailure("unavailable") from exc
        if process.returncode:
            # Never forward stderr: credential helpers and remotes may print tokens/URLs.
            raise _GitFailure("failed", process.returncode)
        return process.stdout

    def _text(self, root, *arguments, **kwargs):
        return self._git(root, *arguments, **kwargs).decode("utf-8", "strict").strip()

    def _valid_origin(self, value):
        if self._test_remote is not None:
            try:
                return Path(value).resolve() == self._test_remote
            except (OSError, ValueError):
                return False
        return value.casefold() in {
            WEB_URL.casefold(), (WEB_URL + ".git").casefold(),
            ("git@github.com:" + REPOSITORY + ".git").casefold(),
            ("ssh://git@github.com/" + REPOSITORY + ".git").casefold(),
        }

    def _validate_repo(self, source_root):
        if not isinstance(source_root, str) or not source_root.strip():
            raise DeveloperUpdateError("请绑定本机 Console 源码目录。")
        supplied = Path(source_root)
        if not supplied.is_absolute() or not supplied.is_dir():
            raise DeveloperUpdateError("源码目录必须是存在的本机绝对路径。")
        root = supplied.resolve()
        try:
            top = Path(self._text(root, "rev-parse", "--show-toplevel")).resolve()
            if top != root or self._text(root, "symbolic-ref", "--short", "HEAD") != BRANCH:
                raise DeveloperUpdateError("请绑定 Console 的 main 源码根目录，不能使用子目录或其他分支。")
            fetch_urls = self._text(root, "remote", "get-url", "--all", "origin").splitlines()
            push_urls = self._text(root, "remote", "get-url", "--push", "--all", "origin").splitlines()
            if len(fetch_urls) != 1 or len(push_urls) != 1 or not all(self._valid_origin(url) for url in fetch_urls + push_urls):
                raise DeveloperUpdateError("源码 origin 必须是 tx74666/CodexControlConsole 的标准 GitHub 地址。")
            manifest = json.loads((root / "app-manifest.json").read_text(encoding="utf-8"))
            if manifest.get("repository") != REPOSITORY:
                raise DeveloperUpdateError("目录不是 Console 源码仓库。")
            git_dir = Path(self._text(root, "rev-parse", "--absolute-git-dir"))
            common = Path(self._text(root, "rev-parse", "--git-common-dir"))
            if not common.is_absolute():
                common = root / common
            for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
                if (git_dir / name).exists():
                    raise DeveloperUpdateError("仓库正在处理其他 Git 操作，请先完成后再更新。")
            return root, git_dir.resolve(), common.resolve(), str(manifest.get("version", ""))
        except DeveloperUpdateError:
            raise
        except (OSError, ValueError, _GitFailure) as exc:
            raise DeveloperUpdateError("无法确认 Console 源码目录、main 分支和 origin，请检查本机 Git。") from exc

    def configure(self, enabled, source_root=None):
        if not self.allowed:
            raise DeveloperUpdateError("当前版本不允许开发者源码更新。")
        if not isinstance(enabled, bool):
            raise DeveloperUpdateError("开发者开关无效。")
        with self._lock, self._file_lock(self.state_dir / "settings.lock"):
            settings = self._settings()
            current = self.operation()
            if self.busy or current and current.get("committed") and (not current.get("pushed") or current.get("indexPending")):
                raise DeveloperUpdateError("先核对或完成上一次源码推送，再改变开发者设置。")
            target = source_root if source_root is not None else settings.get("sourceRoot", "")
            if target:
                root, _, _, _ = self._validate_repo(target)
                settings["sourceRoot"] = str(root)
            elif enabled:
                raise DeveloperUpdateError("请先绑定本机 Console 源码目录。")
            settings["enabled"] = enabled
            self._atomic_json(self._settings_path, settings)
        return self.status()

    @staticmethod
    def _publishable(path, new=False):
        parts = Path(path).parts
        lowered = tuple(part.casefold() for part in parts)
        name = lowered[-1] if lowered else ""
        if not parts or any(ord(char) < 32 or ord(char) == 127 for char in path) or any(part in {"..", "."} for part in parts) or any(part in _EXCLUDED_PARTS for part in lowered):
            return False
        if lowered[:2] == ("docs", "mobile-refresh") or name in _EXCLUDED_NAMES or name.startswith(".env"):
            return False
        if any(word in name for word in ("credential", "secret", "token", ".pem", ".key", ".pfx", ".p12")):
            return False
        if name.endswith((".log", ".sqlite", ".sqlite3", ".db", ".bak", ".tmp")):
            return False
        if new:
            # Only normal repository source locations, never arbitrary new local data.
            if Path(name).suffix not in _SOURCE_SUFFIXES and name not in {".gitignore", ".gitattributes", "license"}:
                return False
            if len(parts) > 1 and lowered[0] not in {"tools", "tests", ".github", "phone", "assets", "docs", "companion", "web"}:
                return False
        return True

    def _snapshot(self, root, git_dir):
        head = self._text(root, "rev-parse", "HEAD")
        branch = self._text(root, "symbolic-ref", "--short", "HEAD")
        index_path = git_dir / "index"
        index_bytes = index_path.read_bytes() if index_path.exists() else b""
        staged = set(filter(None, self._git(root, "diff-index", "--cached", "--name-only", "-z", "--no-renames", head, "--").decode("utf-8").split("\0")))
        unstaged = set(filter(None, self._git(root, "diff-files", "--name-only", "-z", "--no-renames", "--").decode("utf-8").split("\0")))
        new = set(filter(None, self._git(root, "ls-files", "--others", "--exclude-standard", "-z").decode("utf-8").split("\0")))
        entries = {}
        for record in self._git(root, "ls-files", "--stage", "-z").split(b"\0"):
            if not record:
                continue
            metadata, path = record.split(b"\t", 1)
            mode, sha, stage = metadata.decode("ascii").split()
            if stage != "0":
                raise DeveloperUpdateError("仓库包含未解决冲突，请先处理。")
            entries[path.decode("utf-8")] = (mode, sha)
        head_paths = set(filter(None, self._git(root, "ls-tree", "-r", "--name-only", "-z", head).decode("utf-8").split("\0")))
        candidates = [path for path in sorted(staged | unstaged | new) if self._publishable(path, path not in head_paths)]
        if candidates:
            attributes = self._git(root, "check-attr", "-z", "filter", "--", *candidates).split(b"\0")
            if any(attributes[index] not in {b"unspecified", b"unset"} for index in range(2, len(attributes) - 1, 3)):
                raise DeveloperUpdateError("待提交文件使用资源过滤器，请先通过现有资源发布流程处理。")
        changes, payloads = [], {}
        partial = False
        for path in candidates:
            file = root / path
            linked = False
            current = root
            for part in Path(path).parts:
                current = current / part
                try:
                    info = current.lstat()
                    linked = linked or current.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)
                except FileNotFoundError:
                    continue
            if linked or not file.resolve().is_relative_to(root):
                raise DeveloperUpdateError("待提交源码包含文件链接，请先检查。")
            if file.exists() and not file.is_file():
                raise DeveloperUpdateError("待提交内容包含子模块或非普通文件，请先检查。")
            content = file.read_bytes() if file.exists() else None
            if content is not None and path in unstaged and path in entries:
                # diff-files can report only stale stat information. Check canonical bytes.
                if self._text(root, "hash-object", "--path=" + path, "--stdin", data=content) == entries[path][1]:
                    unstaged.discard(path)
                    if path not in staged:
                        continue
            if path in staged and path in unstaged:
                partial = True
            mode = entries.get(path, ("100644", ""))[0]
            if mode not in {"100644", "100755"}:
                raise DeveloperUpdateError("待提交内容包含子模块或文件链接，请先检查。")
            if content is not None and len(content) > 16 * 1024 * 1024:
                raise DeveloperUpdateError("源码文件过大，请使用现有资源发布流程。")
            payloads[path] = {"content": content, "mode": mode}
            changes.append({"path": path, "status": "deleted" if content is None else "new" if path not in head_paths else "modified",
                            "kind": "new" if path not in head_paths else "tracked", "bytes": len(content or b"")})
        canonical = {"sourceRoot": str(root), "head": head, "branch": branch, "index": hashlib.sha256(index_bytes).hexdigest(),
                     "files": [{"path": path, "mode": payload["mode"],
                                "hash": hashlib.sha256(payload["content"]).hexdigest() if payload["content"] is not None else None}
                               for path, payload in payloads.items()]}
        fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        # Commands above must describe the same HEAD and index, rather than a mixed read.
        if head != self._text(root, "rev-parse", "HEAD") or index_bytes != (index_path.read_bytes() if index_path.exists() else b""):
            raise DeveloperUpdateError("源码或暂存区正在变化，请稍后刷新预览。")
        return {"head": head, "branch": branch, "indexBytes": index_bytes, "payloads": payloads,
                "changes": changes, "fingerprint": fingerprint, "partial": partial}

    def _outgoing(self, root, base, head):
        paths = sorted(set(filter(None, (item.strip("\n") for item in self._git(root, "log", "-m", "--format=", "--name-only", "--no-renames", "-z", base + ".." + head).decode("utf-8").split("\0")))))
        return paths, int(self._text(root, "rev-list", "--count", base + ".." + head))

    def _validate_outgoing(self, root, base, head):
        paths, _ = self._outgoing(root, base, head)
        if any(not self._publishable(path) for path in paths):
            raise DeveloperUpdateError("本机待上传提交含本地交接、私有资料或资源规则，已停止上传；请先核对提交范围。")

    def status(self):
        settings = self._settings()
        operation = self.operation()
        result = {"allowed": self.allowed, "enabled": bool(settings.get("enabled")),
                  "sourceRoot": settings.get("sourceRoot", ""), "sourceVersion": "",
                  "runtimeVersion": self.runtime_version, "repoName": REPOSITORY, "repositoryWebUrl": WEB_URL,
                  "branch": "", "changedCount": 0, "changes": [], "head": "", "fingerprint": "",
                  "outgoingCommitCount": 0, "outgoingChanges": [],
                  "canUpdate": False, "blockingReason": "", "operation": operation}
        if not self.allowed:
            result["blockingReason"] = "当前版本不允许开发者源码更新。"
            return result
        try:
            root, git_dir, _, version = self._validate_repo(settings.get("sourceRoot", ""))
            snapshot = self._snapshot(root, git_dir)
            result.update(sourceVersion=version, branch=snapshot["branch"], changedCount=len(snapshot["changes"]),
                          changes=snapshot["changes"], head=snapshot["head"], fingerprint=snapshot["fingerprint"])
            cached_base = self._text(root, "for-each-ref", "--format=%(objectname)", "refs/remotes/origin/main")
            if cached_base and self._contains(root, snapshot["head"], cached_base):
                paths, count = self._outgoing(root, cached_base, snapshot["head"])
                result.update(outgoingCommitCount=count, outgoingChanges=[{"path": path, "status": "committed", "kind": "committed", "bytes": 0} for path in paths])
            if not result["enabled"]:
                result["blockingReason"] = "开启开发者模式后可更新源码。"
            elif self.busy:
                result["blockingReason"] = "正在提交或推送，请等待完成。"
            elif snapshot["partial"] and not (operation and operation.get("committed") and operation["status"] in {"unknown", "push_failed", "conflict", "commit_failed"}):
                result["blockingReason"] = "存在部分暂存的源码，请先完成或取消该文件的部分暂存，再刷新预览。"
            elif any(not self._publishable(change["path"]) for change in result["outgoingChanges"]) and not (operation and operation.get("committed")):
                result["blockingReason"] = "本机待上传提交含本地交接、私有资料或资源规则，请先核对提交范围。"
            else:
                result["canUpdate"] = True
        except (DeveloperUpdateError, OSError, ValueError, _GitFailure) as exc:
            result["blockingReason"] = str(exc) if isinstance(exc, DeveloperUpdateError) else "无法读取源码状态，请检查本机 Git。"
        return result

    def operation(self, request_id=None):
        if request_id is None:
            request_id = self._settings().get("lastRequestId", "")
            if not request_id:
                return None
        if not isinstance(request_id, str) or not _REQUEST.fullmatch(request_id):
            raise DeveloperUpdateError("更新请求身份无效。")
        result = dict(self._volatile.get(request_id) or self._read_json(self._operations_dir / (request_id + ".json"), {}) or self._receipts.get(request_id, {}))
        if result:
            if result.get("status") == "working":
                pid = result.get("ownerPid")
                live = (result.get("ownerId") in _LIVE_OWNERS if pid == os.getpid()
                        else bool(result.get("ownerProcessStarted")) and
                        self._process_identity(pid) == result["ownerProcessStarted"])
                if not live:
                    result.update(status="unknown", phase="interrupted", canRetryPush=False,
                                  error="上一次更新中断，原状态已保留；请显式核对上传结果，不会自动重放。")
            if result.get("preparedSha") and not result.get("commitSha"):
                try:
                    root, _, _, _ = self._validate_repo(result["sourceRoot"])
                    if self._contains(root, self._text(root, "rev-parse", "HEAD"), result["preparedSha"]):
                        result.update(commitSha=result["preparedSha"], committed=True, indexPending=True)
                except (DeveloperUpdateError, _GitFailure, OSError):
                    pass
            return result
        return {"requestId": request_id, "status": "not_found", "phase": "", "summary": "", "commitSha": "",
                "committed": False, "pushed": False, "error": "未找到该请求的回执，请先核对，不要自动重新提交。",
                "canRetryPush": False, "updatedAt": ""}

    @staticmethod
    def _process_identity(pid):
        if not isinstance(pid, int) or pid <= 0:
            return None
        try:
            if os.name == "nt":
                # Windows os.kill(pid, 0) can terminate a process. Query only.
                import ctypes
                from ctypes import wintypes
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                kernel.OpenProcess.restype = wintypes.HANDLE
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
                kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
                handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                if not handle:
                    return None
                try:
                    times = [wintypes.FILETIME() for _ in range(4)]
                    code = wintypes.DWORD()
                    if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)) or not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
                        return None
                    return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
                finally:
                    kernel.CloseHandle(handle)
            # Linux process start time protects against PID reuse as well.
            fields = Path("/proc" + "/" + str(pid) + "/stat").read_text().rsplit(")", 1)[1].split()
            return fields[19]
        except (OSError, ValueError, IndexError):
            return None

    def _save_operation(self, operation, **values):
        operation.update(values, updatedAt=self._now())
        operation["canRetryPush"] = operation["status"] == "push_failed" and bool(operation.get("commitSha"))
        try:
            self._atomic_json(self._operations_dir / (operation["requestId"] + ".json"), operation)
            self._receipts[operation["requestId"]] = dict(operation)
            self._volatile.pop(operation["requestId"], None)
        except OSError:
            self._volatile[operation["requestId"]] = dict(operation)
            raise

    def _stop_operation(self, operation, **values):
        try:
            self._save_operation(operation, **values)
        except OSError:
            # A disk problem stops execution; never continue Git with an unrecorded receipt.
            self._volatile[operation["requestId"]] = dict(operation)

    def update(self, request_id, state_fingerprint, action="update", action_id=None):
        if not isinstance(request_id, str) or not _REQUEST.fullmatch(request_id):
            raise DeveloperUpdateError("更新请求身份无效。")
        if not isinstance(state_fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", state_fingerprint):
            raise DeveloperUpdateError("请刷新源码预览后再更新。")
        if action not in {"update", "verify", "retry"}:
            raise DeveloperUpdateError("更新动作无效。")
        if action != "update" and (not isinstance(action_id, str) or not _REQUEST.fullmatch(action_id)):
            raise DeveloperUpdateError("恢复动作身份无效。")
        with self._lock, self._file_lock(self.state_dir / "settings.lock"):
            existing = self.operation(request_id)
            if action == "update" and existing["status"] != "not_found":
                return existing
            if action != "update":
                if action_id in existing.get("actions", {}):
                    return existing
                if (action == "verify" and existing["status"] not in {"unknown", "conflict", "commit_failed"}
                        or action == "retry" and existing["status"] != "push_failed"):
                    raise DeveloperUpdateError("该请求不能执行此恢复动作，请先刷新回执。")
            status = self.status()
            if not status["canUpdate"]:
                raise DeveloperUpdateError(status["blockingReason"])
            if status["fingerprint"] != state_fingerprint:
                raise DeveloperUpdateError("预览之后源码或暂存区已变化，请刷新后重新确认。")
            previous = status.get("operation")
            if previous and previous.get("committed") and (not previous.get("pushed") or previous.get("indexPending")) and previous["requestId"] != request_id:
                raise DeveloperUpdateError("请先使用原请求核对或重试上一次提交，不会创建重复提交。")
            settings = self._settings()
            root, git_dir, common, version = self._validate_repo(settings["sourceRoot"])
            snapshot = self._snapshot(root, git_dir)
            if snapshot["fingerprint"] != state_fingerprint:
                raise DeveloperUpdateError("预览之后源码已变化，请刷新后重新确认。")
            operation = existing if existing["status"] != "not_found" else {
                "requestId": request_id, "status": "working", "phase": "checking", "summary": "", "commitSha": "",
                "committed": False, "pushed": False, "error": "", "canRetryPush": False,
                "sourceRoot": str(root), "initialHead": snapshot["head"], "initialFingerprint": state_fingerprint,
                "remoteHead": "", "expectedTree": "", "actions": {}, "updatedAt": self._now()}
            # Repo lock lives in Git common dir so different installations serialize too.
            lock_context = self._file_lock(common / "console-developer-update.lock")
            lock_context.__enter__()
            try:
                if action != "update":
                    operation.setdefault("actions", {})[action_id] = action
                _LIVE_OWNERS.add(self._owner_id)
                self._save_operation(operation, status="working", phase="checking", error="", action=action,
                                     actionId=action_id or "", ownerPid=os.getpid(), ownerId=self._owner_id,
                                     ownerProcessStarted=self._process_identity(os.getpid()))
                settings["lastRequestId"] = request_id
                self._atomic_json(self._settings_path, settings)
                self._running.add(request_id)
                thread = threading.Thread(target=self._run, args=(root, git_dir, version, snapshot, operation,
                                                                 action, lock_context), daemon=True)
                thread.start()
            except Exception:
                self._running.discard(request_id)
                _LIVE_OWNERS.discard(self._owner_id)
                lock_context.__exit__(None, None, None)
                raise
            return dict(operation)

    def _remote_head(self, root):
        output = self._text(root, "ls-remote", "--refs", "origin", "refs/heads/" + BRANCH, timeout=35)
        if not output:
            raise _GitFailure("missing_branch")
        lines = output.splitlines()
        fields = lines[0].split()
        if len(lines) != 1 or len(fields) != 2 or not re.fullmatch(r"[0-9a-f]{40,64}", fields[0]) or fields[1] != "refs/heads/main":
            raise _GitFailure("bad_remote")
        return fields[0]

    def _contains(self, root, descendant, ancestor):
        if descendant == ancestor:
            return True
        for sha in (descendant, ancestor):
            try:
                self._git(root, "cat-file", "-e", sha + "^{commit}")
            except _GitFailure:
                return None
        try:
            self._git(root, "merge-base", "--is-ancestor", ancestor, descendant)
            return True
        except _GitFailure as exc:
            return False if exc.returncode == 1 else None

    def _summary(self, version, changes):
        day = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        title = "Update v" + version + " · " + day
        counts = {kind: sum(change["status"] == kind for change in changes) for kind in ("new", "modified", "deleted")}
        body = "本机源码：{} 个文件（新增 {}，修改 {}，删除 {}）。".format(len(changes), counts["new"], counts["modified"], counts["deleted"])
        return title + "\n\n" + body + "\n" + "\n".join("- " + change["path"] for change in changes)

    def _commit(self, root, git_dir, snapshot, operation):
        index_path = git_dir / "index"
        lock_path = git_dir / "index.lock"
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise DeveloperUpdateError("Git 暂存区正在使用，请稍后刷新预览。") from exc
        os.close(descriptor)
        moved = False
        try:
            if self._snapshot(root, git_dir)["fingerprint"] != snapshot["fingerprint"]:
                raise DeveloperUpdateError("源码或暂存区在提交前变化，本次未提交。")
            with tempfile.TemporaryDirectory(prefix="console-update-", dir=git_dir) as temporary:
                frozen_index = Path(temporary) / "frozen-index"
                reconciled_index = Path(temporary) / "reconciled-index"
                self._git(root, "read-tree", snapshot["head"], index=frozen_index)
                if snapshot["indexBytes"]:
                    reconciled_index.write_bytes(snapshot["indexBytes"])
                else:
                    self._git(root, "read-tree", snapshot["head"], index=reconciled_index)
                records = []
                for path, payload in snapshot["payloads"].items():
                    content = payload["content"]
                    sha = self._text(root, "hash-object", "-w", "--path=" + path, "--stdin", data=content) if content is not None else "0" * 40
                    mode = payload["mode"] if content is not None else "0"
                    records.append((mode + " " + sha + "\t" + path).encode("utf-8") + b"\0")
                for index in (frozen_index, reconciled_index):
                    self._git(root, "update-index", "-z", "--index-info", data=b"".join(records), index=index)
                try:
                    self._git(root, "update-index", "--refresh", index=reconciled_index)
                except _GitFailure:
                    # Excluded unstaged files may need update; their index entries stay intact.
                    pass
                tree = self._text(root, "write-tree", index=frozen_index)
                sha = self._text(root, "commit-tree", tree, "-p", snapshot["head"], data=(operation["summary"] + "\n").encode("utf-8"))
                new_index = reconciled_index.read_bytes()
                journal = self.state_dir / ("index-" + operation["requestId"] + ".bin")
                with journal.open("wb") as stream:
                    stream.write(new_index)
                    stream.flush()
                    os.fsync(stream.fileno())
                self._save_operation(operation, phase="committing", preparedSha=sha, expectedTree=tree,
                                     expectedIndex=hashlib.sha256(new_index).hexdigest(),
                                     originalIndex=hashlib.sha256(snapshot["indexBytes"]).hexdigest(),
                                     indexPending=True)
                if self._snapshot(root, git_dir)["fingerprint"] != snapshot["fingerprint"]:
                    raise DeveloperUpdateError("源码在提交前变化，本次未更新 main。")
                # This lock is the standard Git index.lock. Keep unrelated staging intact.
                with lock_path.open("wb") as stream:
                    stream.write(new_index)
                    stream.flush()
                    os.fsync(stream.fileno())
                self._git(root, "update-ref", "refs/heads/main", sha, snapshot["head"])
                moved = True
                operation.update(commitSha=sha, committed=True)
                os.replace(lock_path, index_path)
                self._save_operation(operation, indexPending=False)
                journal.unlink(missing_ok=True)
                return sha
        finally:
            if not moved:
                lock_path.unlink(missing_ok=True)
                operation.update(preparedSha="", commitSha="", committed=False, indexPending=False)
                (self.state_dir / ("index-" + operation["requestId"] + ".bin")).unlink(missing_ok=True)

    def _reconcile_index(self, root, git_dir, operation):
        if not operation.get("indexPending"):
            return
        index_path, lock_path = git_dir / "index", git_dir / "index.lock"
        current = index_path.read_bytes() if index_path.exists() else b""
        current_hash = hashlib.sha256(current).hexdigest()
        expected = operation["expectedIndex"]
        if current_hash != expected:
            journal = self.state_dir / ("index-" + operation["requestId"] + ".bin")
            if current_hash != operation.get("originalIndex") or not journal.exists():
                raise DeveloperUpdateError("本机暂存区已由其他操作修改，原提交和收尾记录保留，请人工核对。")
            content = journal.read_bytes()
            if hashlib.sha256(content).hexdigest() != expected:
                raise DeveloperUpdateError("暂存区收尾记录无法核实，请人工核对原提交。")
            if lock_path.exists():
                if hashlib.sha256(lock_path.read_bytes()).hexdigest() != expected:
                    raise DeveloperUpdateError("Git 暂存区正被其他操作使用，请稍后核对原提交。")
            else:
                with lock_path.open("xb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
            if (index_path.read_bytes() if index_path.exists() else b"") != current:
                raise DeveloperUpdateError("暂存区在收尾前变化，已保留原状态。")
            os.replace(lock_path, index_path)
        self._save_operation(operation, indexPending=False)
        (self.state_dir / ("index-" + operation["requestId"] + ".bin")).unlink(missing_ok=True)

    def _verify_commit(self, root, git_dir, operation, check_head=True):
        sha = operation["commitSha"]
        if check_head and not self._contains(root, self._text(root, "rev-parse", "HEAD"), sha):
            raise DeveloperUpdateError("本机 main 已变化，原提交已保留，请人工核对后再推送。")
        if operation.get("expectedTree"):
            if self._text(root, "rev-parse", sha + "^{tree}") != operation["expectedTree"] or self._text(root, "rev-parse", sha + "^1") != operation["initialHead"]:
                raise DeveloperUpdateError("原提交的父版本或文件树不一致，已停止推送。")

    def _run(self, root, git_dir, version, snapshot, operation, action, lock_context):
        try:
            self._validate_repo(str(root))
            if self._snapshot(root, git_dir)["fingerprint"] != snapshot["fingerprint"]:
                raise DeveloperUpdateError("源码或暂存区已变化，请刷新预览后再确认。")
            remote = self._remote_head(root)
            if operation.get("commitSha"):
                sha = operation["commitSha"]
                self._verify_commit(root, git_dir, operation, check_head=action != "verify")
                if action == "retry":
                    self._reconcile_index(root, git_dir, operation)
                contained = self._contains(root, remote, sha)
                if contained:
                    if operation.get("indexPending"):
                        self._save_operation(operation, status="push_failed", phase="index_pending", pushed=True,
                                             error="GitHub 已收到原提交，本机暂存区收尾待完成；可显式继续完成收尾。")
                        return
                    self._save_operation(operation, status="success", phase="complete", committed=True, pushed=True, error="")
                    return
                if contained is None:
                    self._save_operation(operation, status="unknown", phase="checking_result",
                                         error="GitHub main 已变化，本机缺少核对历史；原提交保留，不会自动重传。")
                    return
                if not self._contains(root, sha, remote):
                    raise DeveloperUpdateError("GitHub 的 main 已领先或分叉，原提交已保留；不会自动合并或覆盖。")
                if action == "verify":
                    self._save_operation(operation, status="push_failed", phase="checked", error="已确认 GitHub 尚未收到原提交；可显式重试同一次推送。")
                    return
            else:
                if action == "verify":
                    # Interrupted before commit: inspect only; do not create or resend work.
                    self._save_operation(operation, status="conflict", phase="checked",
                                         error="中断请求没有已确认提交，请核对本机状态后创建新的更新请求。")
                    return
                if not self._contains(root, snapshot["head"], remote):
                    raise DeveloperUpdateError("GitHub 的 main 已领先或分叉；本机文件保留，不会自动合并或覆盖。")
                self._validate_outgoing(root, remote, snapshot["head"])
                operation["remoteHead"] = remote
                if snapshot["changes"]:
                    operation["summary"] = self._summary(version, snapshot["changes"])
                    self._save_operation(operation, phase="preparing")
                    sha = self._commit(root, git_dir, snapshot, operation)
                    self._verify_commit(root, git_dir, operation)
                    current = self._snapshot(root, git_dir)
                    if current["head"] != sha or hashlib.sha256(current["indexBytes"]).hexdigest() != operation["expectedIndex"] or current["changes"] != []:
                        raise DeveloperUpdateError("提交后检测到其他源码写入，原提交已保留；请人工核对后再推送。")
                else:
                    sha = snapshot["head"]
                    if remote == sha:
                        self._save_operation(operation, status="noop", phase="complete", error="本机源码与 GitHub 已一致。")
                        return
                    self._save_operation(operation, commitSha=sha, committed=True,
                                         summary="推送本机已有提交 " + sha[:12])
            # Freeze the one permitted refspec. No tag, force, fetch, pull, or LFS configuration.
            self._validate_repo(str(root))
            self._validate_outgoing(root, remote, sha)
            self._save_operation(operation, phase="pushing")
            try:
                self._git(root, "push", "--no-follow-tags", "origin", sha + ":refs/heads/main", timeout=120)
            except _GitFailure:
                try:
                    checked = self._remote_head(root)
                except _GitFailure:
                    self._save_operation(operation, status="unknown", phase="checking_result",
                                         error="推送结果尚未确认，原提交已保留；请核对结果，不要重复创建提交。")
                    return
                relation = self._contains(root, checked, sha)
                if relation:
                    self._save_operation(operation, status="success", phase="complete", committed=True, pushed=True, error="")
                elif relation is None:
                    self._save_operation(operation, status="unknown", phase="checking_result",
                                         error="GitHub main 已变化，本机缺少核对历史；原提交保留，不会自动重传。")
                elif not self._contains(root, sha, checked):
                    self._save_operation(operation, status="conflict", phase="stopped", error="GitHub main 已变化，原提交已保留；不会覆盖远端。")
                else:
                    self._save_operation(operation, status="push_failed", phase="stopped", error="推送未完成，原提交已保留；可重试同一次推送。")
                return
            try:
                checked = self._remote_head(root)
            except _GitFailure:
                self._save_operation(operation, status="unknown", phase="checking_result", error="推送已返回，但 GitHub 结果未核实；请核对原提交。")
                return
            if self._contains(root, checked, sha):
                self._save_operation(operation, status="success", phase="complete", committed=True, pushed=True, error="")
            else:
                self._save_operation(operation, status="unknown", phase="checking_result", error="GitHub 尚未核实原提交，请核对结果。")
        except DeveloperUpdateError as exc:
            self._stop_operation(operation, status="conflict", phase="stopped", error=str(exc))
        except _GitFailure:
            if operation.get("committed"):
                status, message = "unknown", "原提交已保留，无法核实 GitHub 状态；请核对原提交。"
            else:
                status, message = "commit_failed", "本机 Git 操作未完成，请检查 Git 身份、权限和网络后刷新预览。"
            self._stop_operation(operation, status=status, phase="stopped", error=message)
        except Exception:
            self._stop_operation(operation, status="unknown" if operation.get("commitSha") else "commit_failed",
                                 phase="stopped", error="更新未完成，已保留本机状态；请核对原请求。")
        finally:
            with self._lock:
                self._running.discard(operation["requestId"])
                _LIVE_OWNERS.discard(self._owner_id)
            lock_context.__exit__(None, None, None)
