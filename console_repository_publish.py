"""Explicit multi-repository commits and exact-commit pushes.

GET/preview never sync or contact remotes. The HTTP caller must enforce a trusted
local developer request. Journals intentionally survive failures: a new request
first resumes the original commit, with its original destination and message.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import ast
import base64
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import signal
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import uuid
import weakref
import xml.etree.ElementTree as ET
from console_repository_versions import (VersionPlanError, catalog as version_catalog_items,
                                        prepare_updates as prepare_version_updates, source_id as version_source_id,
                                        read_current_version, parse_commit_history,
                                        MAX_BYTES as VERSION_MAX_BYTES)


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
_REQUEST = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,99}\Z")
_SHA = re.compile(r"[0-9a-f]{40,64}\Z")
_PRIVATE_PARTS = {".git", ".venv", "venv", "node_modules", "__pycache__", "cache",
                  "private", "workflow-private", "browserprofiles", "logs", "tmp", "temp"}
_PRIVATE_NAMES = {".env", ".npmrc", ".pypirc", "credentials.json", "secrets.json",
                  "installation.json", "local-store-identity.json", "publisher-state.json"}
_DEFAULT_NAMING = {"preset": "version", "fallbackTitle": "更新进度 {datetime}",
                   "subtitle": "", "notes": "", "includeSummary": True, "autoBump": True,
                   "allowActiveWork": True}
_LIVE = {}


# Diagnostics are presentation metadata, never a recovery instruction or a
# configuration mutation. Codes come from explicit guards / sanitized Git codes;
# message text (including changesReason and syncReason) is not a classifier.
_DIAGNOSTICS = {
    "repo_missing": ("connection", "error", "在配置中核对本地仓库根目录，然后重新核对。", ("connection", "path")),
    "repo_root": ("connection", "warning", "选择真实仓库根目录，然后重新核对。", ("connection", "path")),
    "branch_mismatch": ("connection", "warning", "核对当前分支与目标分支；保留工作后自行处理，再重新核对。", ("connection", "branch")),
    "remote_config": ("connection", "warning", "核对远端名称及其读取和推送地址，然后重新核对。", ("connection", "remote")),
    "remote_ownership": ("connection", "error", "核对本地读取、推送和配置地址的仓库归属，然后重新核对。", ("connection", "repositoryUrl")),
    "duplicate_repository": ("connection", "warning", "在配置中保留该 Git 仓库的一个启用入口，再重新核对。", ("connection", "path")),
    "sync_config": ("sync", "warning", "核对已明确配置的工作文件同步映射与清单，再重新核对。", ("sync", "sync")),
    "sync_missing": ("sync", "warning", "保存并确认配置的来源文件存在，再重新核对。", ("sync", "sync")),
    "sync_writing": ("sync", "warning", "等待工作文件保存完成，确认来源与目标后重新核对。", ("sync", "sync")),
    "sync_changed": ("sync", "warning", "核对来源和目标的最新已保存内容，再重新核对；保留现有修改。", ("sync", "sync")),
    "activity_unconfirmed": ("activity", "warning", "先查看具体聊天与原因；确认或完成该仓库相关的 Codex 工作后重新核对。", None),
    "activity_active": ("activity", "warning", "等待列出的聊天完成或交还本仓库的编辑范围，再重新核对并重试。", None),
    "activity_scope_unknown": ("activity", "warning", "列出的聊天尚未声明本轮编辑范围；由该聊天登记实际仓库或完成本轮工作后重新核对。", None),
    "git_history_operation": ("repository", "warning", "在该仓库完成或按原意取消现有 Git 历史操作，再重新核对。", None),
    "git_lock": ("repository", "warning", "确认原 Git 操作已完成后重新核对；保留原锁和工作。", None),
    "staged_selection": ("repository", "warning", "先按原意处理已有暂存选择，再重新核对；当前选择会保留。", None),
    "merge_conflict": ("repository", "warning", "在仓库中处理现有冲突并完成相关 Git 操作，再重新核对。", None),
    "worktree_changed": ("repository", "warning", "确认相关工作与保存已完成，重新预览并核对原提交。", None),
    "version_authority": ("versions", "warning", "核对该组件的权威版本来源和关联声明，再重新核对。", ("versions", "versionPath")),
    "version_plan_stale": ("versions", "warning", "重新读取当前版本，在配置中核对过期的版本计划。", ("versions", "versionPath")),
    "version_plan_blocked": ("versions", "warning", "重新读取版本，核对提示涉及的实际组件和版本来源；不会猜测或再次升版。", ("versions", "versionPath")),
    "version_fallback": ("naming", "info", "可继续使用已记住的备用标题；需要时在配置中补充权威版本来源。", ("naming", "fallbackTitle")),
    "destination_changed": ("verification", "warning", "核对保留记录中的原目标与当前配置；确认原目标后再重试原提交。", None),
    "receipt_unverified": ("verification", "warning", "核对保留的上传或提交记录及远端；重试会先核验原提交。", None),
    "operation_interrupted": ("verification", "warning", "确认相关工作已完成后重试；先核对保留的原提交与操作记录。", None),
    "background_unavailable": ("activity", "warning", "稍后重新核对并重试；此请求尚未开始提交或推送。", None),
    "git_authentication": ("authentication", "error", "核对现有 Git 凭证的登录状态和仓库访问权限，再重试原提交。", None),
    "git_permissions": ("permissions", "error", "核对当前账号的仓库权限，再重试原提交。", None),
    "git_rules": ("rules", "warning", "核对 Git hook 或远端分支规则的拒绝原因，处理后重试原提交。", None),
    "git_lfs": ("lfs", "error", "核对 Git LFS 安装、相关对象及认证，处理后重试原提交。", None),
    "git_timeout": ("network", "warning", "确认网络及原 Git 操作状态；重试先核对远端是否收到原提交。", None),
    "git_missing": ("repository", "error", "确认本机 Git 可用，再重新核对。", None),
    "git_unavailable": ("repository", "warning", "确认本机 Git 能正常运行，再重新核对。", None),
    "git_failed": ("repository", "warning", "查看本次 Git 步骤和退出码；原文件、暂存选择及已有提交保留。", None),
    "git_remote_failed": ("remote", "warning", "远端检查未完成；查看 Git 步骤和退出码后重试，继续保留原提交。", None),
    "git_network": ("network", "warning", "核对网络连接后重试；先核验远端，不会重复提交。", None),
    "git_unsupported": ("repository", "warning", "本机 Git 拒绝此命令选项；核对实际 Git 版本与本次步骤。", None),
    "remote_changed": ("remote", "warning", "重新核对远端和本地历史；需要整合时自行处理后重试原提交。", None),
    "remote_ahead": ("remote", "warning", "在仓库中核对并自行整合远端领先或分叉的历史，再重试原提交。", None),
    "manual_check": ("unknown", "warning", "先核对原安全提示、仓库与保留记录；确认相关工作完成后重新核对。", None),
}
_GIT_DIAGNOSTIC_CODES = {"authentication": "git_authentication", "permissions": "git_permissions",
                         "rules": "git_rules", "lfs": "git_lfs", "timeout": "git_timeout",
                         "missing_git": "git_missing", "git_unavailable": "git_unavailable",
                         "remote_changed": "remote_changed", "remote_config": "remote_config",
                         "git_failed": "git_failed", "network": "git_network", "unsupported": "git_unsupported"}

_GIT_OPERATIONS = {"ls-remote", "fetch", "push", "commit", "status", "config", "rev-parse", "symbolic-ref",
                   "add", "read-tree", "update-index", "write-tree", "diff", "diff-tree", "diff-index",
                   "merge-base", "rev-list", "log", "ls-files", "ls-tree", "cat-file", "show", "show-ref", "update-ref",
                   "check-ref-format", "stripspace"}


def _git_operation(arguments):
    # Recognize only the fixed global flags our caller uses; never persist an
    # unknown argument, pathspec, configuration value or message as a command.
    offset = 0
    while offset < len(arguments) and arguments[offset] in {"--literal-pathspecs", "--no-optional-locks", "--no-pager", "--no-replace-objects"}:
        offset += 1
    return arguments[offset] if offset < len(arguments) and arguments[offset] in _GIT_OPERATIONS else None


_NETWORK_ERRORS = (
    ("resolve_host", r"^fatal:\s*unable to access ['\"][^'\"\r\n]+['\"]:\s*could not resolve (?:host|proxy):"),
    ("connect_failed", r"^fatal:\s*unable to access ['\"][^'\"\r\n]+['\"]:\s*(?:failed to connect|couldn't connect|could not connect)\b"),
    ("connection_reset", r"^(?:fatal:\s*unable to access ['\"][^'\"\r\n]+['\"]:\s*|error:\s*rpc failed;\s*curl\s+\d+\s+)(?:recv failure:|send failure:|connection (?:was )?reset|failure when receiving data from the peer)"),
    ("tls_failed", r"^fatal:\s*unable to access ['\"][^'\"\r\n]+['\"]:\s*(?:ssl certificate problem:|server certificate verification failed|openssl ssl_connect:|gnutls_handshake\(\) failed|schannel:)"),
    ("server_unavailable", r"^fatal:\s*unable to access ['\"][^'\"\r\n]+['\"]:\s*the requested url returned error:\s*5\d\d\s*$"),
    ("transport_failed", r"^error:\s*rpc failed;\s*curl\s+(?:16|18|28|35|52|55|56|92)\s+"),
)


def _git_error_kind(stderr):
    # Only fixed error types survive. URLs, filenames, hook output and tokens do
    # not enter a receipt; an unknown line remains unknown.
    for kind, pattern in _NETWORK_ERRORS:
        if re.search(pattern, stderr, re.MULTILINE | re.IGNORECASE):
            return kind
    if re.search(r"^error:\s*(?:unknown|unrecognized) (?:option|switch)\b", stderr, re.MULTILINE | re.IGNORECASE):
        return "unsupported_option"
    return "unknown"


def _make_diagnostic(code, summary, *, source_id=None):
    code = code if code in _DIAGNOSTICS else "manual_check"
    category, severity, next_step, location = _DIAGNOSTICS[code]
    target = {"section": location[0], "field": location[1]} if location else None
    if target and target["section"] == "versions":
        # A version control is addressable only with a known actual authority.
        target = {**target, "sourceId": source_id} if isinstance(source_id, str) and source_id else None
    return {"code": code, "category": category, "severity": severity,
            "summary": str(summary), "nextStep": next_step, "target": target}


def _activity_blockers(value):
    """Retain bounded actor metadata for display, never as execution permission."""
    if not isinstance(value, list):
        return []
    result = []
    limits = {"threadId": 100, "title": 200, "agentPath": 200, "cwd": 4096, "reason": 300}
    for item in value[:20]:
        if not isinstance(item, dict):
            continue
        scope = item.get("scope")
        if isinstance(scope, dict) and scope.get("status") == "verified":
            item = {**item, "mode": scope.get("mode"), "roots": scope.get("editRoots", [])}
        actor = {key: text[:limit] for key, limit in limits.items()
                 if isinstance((text := item.get(key)), str) and not any(ord(c) < 32 for c in text)}
        for key, allowed in (("state", {"active", "unknown"}), ("mode", {"edit", "read_only", "unknown"})):
            if item.get(key) in allowed:
                actor[key] = item[key]
        actor["roots"] = [path[:4096] for path in item.get("roots", [])[:8]
                          if isinstance(path, str) and path and not any(ord(c) < 32 for c in path)] if isinstance(item.get("roots"), list) else []
        if actor.get("threadId") or actor.get("title") or actor.get("cwd"):
            result.append(actor)
    return result


class RepositoryPublishError(ValueError):
    """A sanitized, user-facing validation error."""

    def __init__(self, message, *, code="", source_id=None):
        super().__init__(message)
        self.code = code
        self.diagnostic = _make_diagnostic(code, message, source_id=source_id)


class _GitFailure(Exception):
    def __init__(self, code, detail="", returncode=None, *, operation=None, error_kind="unknown"):
        super().__init__(code)
        self.code, self.detail, self.returncode = code, detail, returncode
        self.operation = operation if operation in _GIT_OPERATIONS else None
        self.error_kind = error_kind if error_kind in {"unknown", "unsupported_option", "timeout", *(k for k, _ in _NETWORK_ERRORS)} else "unknown"


def _git_error_category(stderr):
    """Recognize error receipts, never words inside a path, URL or progress text.

    Unknown output stays generic. The raw stderr is not included in diagnostics,
    operation messages or durable receipts, and Git behavior is unchanged.
    """
    patterns = (
        ("lfs", (r"^(?:error:\s*)?(?:git lfs upload failed|lfs upload failed|batch (?:request|response):)",
                 r"^(?:fatal|error):\s*(?:external filter ['\"]git-lfs[^\n]*['\"] failed|smudge filter lfs failed)",
                 r"^git-lfs(?: filter-process)?:[^\n]*(?:not found|not recognized|failed|error)",
                 r"^git:\s*['\"]lfs['\"] is not a git command\b",
                 r"^fatal:[^\n]*:\s*smudge filter lfs failed\b",
                 r"^remote:\s*(?:error:\s*)?gh008:")),
        ("authentication", (r"^(?:fatal|error):\s*authentication (?:failed|is required|required)\b",
                            r"^fatal:\s*unable to access ['\"][^'\"\r\n]+['\"]:\s*the requested url returned error:\s*401\s*$",
                            r"^fatal:\s*could not read (?:username|password) for ",
                            r"^[^\n]*:\s*permission denied \(publickey(?:,[^)]+)?\)\.?$",
                            r"^(?:fatal:\s*)?no supported authentication methods available\b")),
        ("permissions", (r"^fatal:[^\n]*requested url returned error:\s*403\b",
                         r"^remote:\s*(?:error:\s*)?(?:write access to repository not granted|permission to .+ denied to .+|access denied)\b")),
        ("rules", (r"^remote:\s*(?:error:\s*)?(?:gh013:|gh006:|protected branch update failed\b|repository rule violations found\b)",
                   r"^\s*!\s*\[remote rejected\][^\n]*\((?:pre-receive hook declined|hook declined|protected branch hook declined|repository rule[^)]*)\)")),
        ("remote_changed", (r"^\s*!\s*\[rejected\][^\n]*\((?:non-fast-forward|fetch first|stale info)\)",)),
        ("remote_config", (r"^error:\s*no such remote ['\"][^'\"\r\n]+['\"]\.?\s*$",)),
    )
    for category, receipts in patterns:
        if any(re.search(pattern, stderr, re.MULTILINE | re.IGNORECASE) for pattern in receipts):
            return category
    kind = _git_error_kind(stderr)
    return "unsupported" if kind == "unsupported_option" else "network" if kind != "unknown" else "git_failed"


def _parse_transfer_progress(record, *, lfs_file=False):
    """Only numeric Git/LFS receipts become progress; never retain file names.

    A transfer substep reaching 100% is not a verified repository delivery.
    LFS's file count is estimated, and its byte percentage covers one file.
    """
    text = record.decode("utf-8", "replace") if isinstance(record, bytes) else str(record)
    if len(text) > 8192:
        return None
    if lfs_file:
        match = re.fullmatch(r"upload (\d{1,16})/(\d{1,16}) (\d{1,16})/(\d{1,16})(?:\s+.*)?", text.strip())
        if not match:
            return None
        number, files, current, total = map(int, match.groups())
        if not 0 < number <= files < 2 ** 53 or not 0 <= current <= total < 2 ** 53 or not total:
            return None
        return {"state": "measured", "scope": "file", "unit": "bytes", "current": current, "total": total,
                "percent": min(99.9, round(current * 100 / total, 1)) if current < total else 100,
                "source": "git-lfs", "step": "lfs_upload",
                "fileIndex": number, "fileTotal": files, "estimatedFileTotal": True}
    match = re.fullmatch(r"(Counting objects|Compressing objects|Writing objects|Uploading LFS objects):\s*(\d{1,3})%\s*\((\d{1,16})/(\d{1,16})\)(?:[,\s].*)?", text.strip())
    if not match:
        return None
    label, percent, current, total = match.groups()
    percent, current, total = int(percent), int(current), int(total)
    if not 0 <= current <= total < 2 ** 53 or not total or not 0 <= percent <= 100:
        return None
    if abs(percent - current * 100 / total) > 1:
        return None
    return {"state": "measured", "scope": "phase", "unit": "objects", "current": current, "total": total,
            "percent": percent, "source": "git-lfs" if label == "Uploading LFS objects" else "git",
            "step": {"Counting objects": "counting_objects", "Compressing objects": "compressing_objects",
                     "Writing objects": "writing_objects", "Uploading LFS objects": "lfs_upload"}[label]}


def _windows_git_job(process):
    """Own this Git child's descendants, without touching shared processes.

    Closing the job normally does not terminate children. Timeout explicitly
    terminates only processes in this newly created, unnamed job.
    """
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise OSError(ctypes.get_last_error(), "Cannot own Git process job")
    if not kernel.AssignProcessToJobObject(handle, wintypes.HANDLE(int(process._handle))):
        code = ctypes.get_last_error()
        kernel.CloseHandle(handle)
        raise OSError(code, "Cannot assign owned Git process job")
    return lambda: kernel.TerminateJobObject(handle, 1), lambda: kernel.CloseHandle(handle)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json_sha(value):
    return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def catalog_source_identity(repository, naming):
    """Bind display results to the exact configuration used during this read."""
    value = {"repository": repository, "naming": naming}
    return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                           allow_nan=False).encode("utf-8"))


def _repo_settings_sha(repo):
    # Plans have their own frozen journal. Clearing a consumed plan cannot break
    # the original commit's destination/configuration identity on push retry.
    return _json_sha({key: value for key, value in repo.items() if key != "versionPlans"})


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
        raise RepositoryPublishError("发布记录损坏或不可读，请保留记录后核对；不会重新提交。", code="receipt_unverified") from exc
    if not isinstance(value, dict):
        raise RepositoryPublishError("发布记录格式错误，请先核对；不会重新提交。", code="receipt_unverified")
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


def _stable(path, *, check=None):
    if check:
        check()
    path = _safe_path(path)
    before = path.stat()
    if not path.is_file():
        raise RepositoryPublishError("文件不是普通已保存文件。")
    digest = hashlib.sha256()
    with _read_lease(path), path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            if check:
                check()
            digest.update(block)
    after = path.stat()
    key = lambda s: (s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_ino)
    if key(before) != key(after):
        raise RepositoryPublishError("文件正在写入，请保存完成后重试。", code="worktree_changed")
    if check:
        check()
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
            raise RepositoryPublishError("文件仍有写入句柄，请等待保存完成；不会关闭应用。", code="worktree_changed")
        raise OSError(code, "Unable to hold read lease")
    try:
        yield
    finally:
        kernel.CloseHandle(handle)


@contextmanager
def _version_write_lease(path):
    """Write through our Windows handle, denying external writers and renames.

    A crash mid-file is retained for manual verification if bytes match neither
    durable image. It is never repaired by overwriting unknown user content.
    """
    if os.name != "nt":
        with path.open("r+b") as stream:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                if os.fstat(stream.fileno()).st_nlink != 1:
                    raise RepositoryPublishError("版本文件存在硬链接来源重叠，请手动准备版本；不会改写其他文件。")
                yield stream
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        return
    import ctypes
    import msvcrt
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x80000000 | 0x40000000, 1, None, 3, 0x08000000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise RepositoryPublishError("版本文件仍在保存或无法锁定，请等待保存完成。")
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    with os.fdopen(descriptor, "r+b") as stream:
        if os.fstat(stream.fileno()).st_nlink != 1:
            raise RepositoryPublishError("版本文件存在硬链接来源重叠，请手动准备版本；不会改写其他文件。")
        yield stream


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
            raise RepositoryPublishError("另一处正在操作该仓库，请等待完成。", code="git_lock") from exc
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
        self._uploads = self.state_dir / "confirmed-uploads"
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

    def _git(self, root, *arguments, data=None, index=None, timeout=35, config=None, progress=None):
        operation = _git_operation(arguments)
        remaining = self._catalog_remaining()
        if remaining is not None:
            timeout = min(timeout, remaining)
        executable = shutil.which("git")
        if not executable:
            raise _GitFailure("missing_git", operation=operation)
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
            command = [executable, "-C", str(root), *arguments]
            process = (self._stream_git(command, env, data, timeout, progress) if progress is not None else
                       subprocess.run(command, input=data, capture_output=True, env=env, timeout=timeout,
                                      creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
        except subprocess.TimeoutExpired as exc:
            raise _GitFailure("timeout", operation=operation, error_kind="timeout") from exc
        except OSError as exc:
            raise _GitFailure("git_unavailable", operation=operation) from exc
        if process.returncode:
            text = process.stderr.decode("utf-8", "replace").replace("\r", "\n").lower()
            category = _git_error_category(text)
            raise _GitFailure(category, returncode=process.returncode, operation=operation, error_kind=_git_error_kind(text))
        return process.stdout

    def _catalog_remaining(self):
        deadline = getattr(getattr(self, "_lease", None), "catalog_deadline", None)
        if deadline is None:
            return None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _GitFailure("timeout")
        return remaining

    def _catalog_stable(self, path):
        if self._catalog_remaining() is None:
            return _stable(path)
        return _stable(path, check=self._catalog_remaining)

    def _stream_git(self, command, env, data, timeout, progress):
        """Drain both byte pipes while the worker can publish live snapshots.

        Hooks, filters, credentials and exact push arguments remain unchanged.
        Transfer telemetry is optional and cannot turn a push into a success.
        """
        events, stop = queue.Queue(maxsize=128), threading.Event()
        chunks = {"stdout": [], "stderr": []}
        readers, child, lfs_path, lfs_stream = [], None, None, None
        terminate_job, close_job = None, None
        trace_buffer = b""
        env = dict(env)
        env.setdefault("GIT_LFS_FORCE_PROGRESS", "1")
        # Preserve any user-supplied telemetry destination, never read it.
        if not env.get("GIT_LFS_PROGRESS"):
            descriptor, name = tempfile.mkstemp(prefix="lfs-progress-", suffix=".tmp", dir=self.state_dir)
            os.close(descriptor)
            lfs_path = Path(name)
            env["GIT_LFS_PROGRESS"] = str(lfs_path)
            lfs_stream = lfs_path.open("rb")

        def emit(record):
            while not stop.is_set():
                try:
                    events.put(record, timeout=.05)
                    return
                except queue.Full:
                    pass

        def read_pipe(name, stream):
            pending = b""
            try:
                while not stop.is_set():
                    block = os.read(stream.fileno(), 65536)
                    if not block:
                        break
                    chunks[name].append(block)
                    records = re.split(br"[\r\n]", pending + block)
                    pending = records.pop()
                    for record in records:
                        if record:
                            value = _parse_transfer_progress(record)
                            if value:
                                emit(value)
                    # A malformed huge output line never becomes telemetry.
                    if len(pending) > 8192:
                        pending = b""
                if pending:
                    value = _parse_transfer_progress(pending)
                    if value:
                        emit(value)
            except OSError:
                emit({"pipeError": True})
            finally:
                stream.close()
                emit({"pipeDone": name})

        def write_input():
            try:
                if data:
                    remaining = memoryview(data)
                    while remaining and not stop.is_set():
                        written = child.stdin.write(remaining)
                        if not written:
                            break
                        remaining = remaining[written:]
            except (BrokenPipeError, OSError):
                pass  # The actual process receipt remains authoritative.
            finally:
                child.stdin.close()

        def read_lfs():
            nonlocal trace_buffer
            if lfs_stream is None:
                return
            block = lfs_stream.read(65536)
            if block:
                records = (trace_buffer + block).split(b"\n")
                trace_buffer = records.pop()
                for record in records:
                    value = _parse_transfer_progress(record.rstrip(b"\r"), lfs_file=True)
                    if value:
                        progress(value)
                if len(trace_buffer) > 8192:
                    trace_buffer = b""

        def stop_owned():
            if terminate_job is not None:
                terminate_job()
            elif child is not None and os.name != "nt":
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if child is not None and child.poll() is None:
                child.kill()
            if child is not None:
                child.wait(timeout=5)

        try:
            child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env=env, bufsize=0, start_new_session=os.name != "nt",
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            if os.name == "nt":
                terminate_job, close_job = _windows_git_job(child)
            for name in ("stdout", "stderr"):
                reader = threading.Thread(target=read_pipe, args=(name, getattr(child, name)), daemon=True,
                                          name="repository-git-" + name)
                readers.append(reader)
                reader.start()
            writer = threading.Thread(target=write_input, daemon=True, name="repository-git-stdin")
            readers.append(writer)
            writer.start()
            deadline = time.monotonic() + timeout
            done, pipe_error = set(), False
            while len(done) < 2 or child.poll() is None:
                if time.monotonic() >= deadline:
                    stop_owned()
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    value = events.get(timeout=min(.05, max(.001, deadline - time.monotonic())))
                    if "pipeDone" in value:
                        done.add(value["pipeDone"])
                    elif "pipeError" in value:
                        pipe_error = True
                    else:
                        progress(value)
                except queue.Empty:
                    pass
                read_lfs()
            while not events.empty():
                value = events.get_nowait()
                if "state" in value:
                    progress(value)
            read_lfs()
            if pipe_error:
                raise OSError("Git output pipe became unreadable")
            return subprocess.CompletedProcess(command, child.returncode, b"".join(chunks["stdout"]), b"".join(chunks["stderr"]))
        except BaseException:
            if child is not None:
                stop_owned()
            raise
        finally:
            stop.set()
            for reader in readers:
                reader.join(timeout=1)
            if close_job is not None:
                close_job()
            if lfs_stream is not None:
                lfs_stream.close()
            if lfs_path is not None:
                try:
                    lfs_path.unlink(missing_ok=True)
                except OSError:
                    pass  # An owned trace is not a repository upload file.

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
                if versions[-1]["kind"] == "git_commit" and (versions[-1]["path"] != "HEAD" or versions[-1]["key"] != "subject"):
                    raise RepositoryPublishError("提交版本仅允许固定 HEAD / subject 来源，不能指定命令或模式。")
            plans = raw.get("versionPlans", [])
            fields = {"sourceId", "currentVersion", "targetVersion", "expectedSha256", "expectedBytes", "planProof"}
            if not isinstance(plans, list) or len(plans) > 100 or any(not isinstance(item, dict) or set(item) != fields for item in plans):
                raise RepositoryPublishError("一次性版本计划格式无效，请重新配置。")
            seen_plans = set()
            for item in plans:
                if (not _ID.fullmatch(str(item["sourceId"])) or item["sourceId"] in seen_plans
                        or any(not isinstance(item[key], str) or len(item[key]) > 80 for key in ("currentVersion", "targetVersion"))
                        or any(not re.fullmatch(r"[0-9a-f]{64}", str(item[key])) for key in ("expectedSha256", "planProof"))
                        or type(item["expectedBytes"]) is not int or not 0 < item["expectedBytes"] <= VERSION_MAX_BYTES):
                    raise RepositoryPublishError("一次性版本计划身份或文件证明无效，请重新配置。")
                seen_plans.add(item["sourceId"])
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
                                 "syncError": str(raw.get("syncError", ""))[:1000], "syncManifest": manifest,
                                 "versionPlans": json.loads(json.dumps(plans))})
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
        if not isinstance(naming["autoBump"], bool):
            raise RepositoryPublishError("自动升版设置必须为开关。")
        if not isinstance(naming["allowActiveWork"], bool):
            raise RepositoryPublishError("工作中上传设置必须为开关。")
        return {"repositories": repositories, "naming": naming}

    def _settings(self):
        return _read(self._settings_path)

    def configure(self, payload, *, expected_settings_sha=None):
        if not self.allowed:
            raise RepositoryPublishError("当前入口不允许提交推送。")
        with self._mutex, _file_lock(self.state_dir / "settings.lock"):
            previous = self._settings()
            current_normalized = self._normalize(previous)
            settings = self._normalize(payload)
            if expected_settings_sha is not None:
                if not isinstance(expected_settings_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_settings_sha):
                    raise RepositoryPublishError("配置比较证明无效，请重新读取配置。")
                if _json_sha(current_normalized) != expected_settings_sha:
                    raise RepositoryPublishError("仓库配置已被另一处修改，请重新读取；保留现有选择，不覆盖。", code="settings_changed")
            elif previous.get("casRequired") is True:
                if settings != current_normalized:
                    raise RepositoryPublishError("此仓库配置已启用比较保护；旧草稿没有当前证明，保留现有选择，不覆盖。", code="settings_changed")
                return self.status()  # Exact legacy no-op leaves server metadata and bytes intact.
            previous_repos = {r["id"]: r for r in previous["repositories"]}
            rediscovered = None
            for repo in settings["repositories"]:
                old = previous_repos.get(repo["id"], {})
                if repo.get("versionPlans", []) and repo.get("versionPlans", []) != old.get("versionPlans", []):
                    context = self._repo(repo)
                    self._version_updates(repo, context)
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
            if previous.get("casRequired") is True or expected_settings_sha is not None:
                settings["casRequired"] = True  # Server-owned seal, never taken from the payload.
            _atomic(self._settings_path, settings)
        return self.status()

    def _version_sources(self, repo, root):
        sources = repo["versionSources"]
        if not sources:
            path = next((name for name in ("app-manifest.json", "package.json") if (root / name).is_file()), None)
            return [{"path": path, "kind": "json", "key": "version", "name": root.name, "scope": ""}] if path else []
        # The application manifest supersedes package.json, as in commit naming.
        return [source for source in sources if source["path"] != "package.json"] if any(source["path"] == "app-manifest.json" for source in sources) else sources

    def _version_reader(self, root):
        def read(relative):
            path = _safe_path(root / _relative(relative))
            if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size > VERSION_MAX_BYTES:
                raise RepositoryPublishError("版本文件缺失、超出仓库或过大，请手动准备版本。")
            with _read_lease(path):
                before = self._catalog_stable(path)
                raw = path.read_bytes()
                if self._catalog_stable(path) != before or _sha(raw) != before["sha256"]:
                    raise RepositoryPublishError("版本文件正在变化，请保存完成后重试。")
            return raw
        return read

    def _git_version_reader(self, root):
        def read(source):
            if source.get("kind") != "git_commit" or source.get("path") != "HEAD" or source.get("key") != "subject":
                raise VersionPlanError("提交版本仅允许固定 HEAD / subject 来源。")
            head = self._text(root, "rev-parse", "HEAD")
            raw = self._git(root, "log", "--first-parent", "--max-count=64", "--format=%H%x00%s", "HEAD")
            result = parse_commit_history(head, raw)
            if self._text(root, "rev-parse", "HEAD") != head:
                raise VersionPlanError("读取提交版本时 HEAD 已变化，请重新读取。")
            return result
        return read

    def _console_resource_reader(self, root):
        def read(name):
            if name not in {"console-repository-publish.js", "console-repository-publish.css"}:
                raise VersionPlanError("Console 资源证明只允许固定仓库模块文件。")
            head = self._text(root, "rev-parse", "HEAD")
            names = self._git(root, "--literal-pathspecs", "ls-tree", "--name-only", "-z", head, "--", name).split(b"\0")
            blob = self._git(root, "show", head + ":" + name) if name.encode("utf-8") in names else None
            status = self._git(root, "--literal-pathspecs", "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames", "--", name)
            if blob is not None and len(blob) > VERSION_MAX_BYTES:
                raise VersionPlanError("Console 独立资源的 HEAD 文件超出读取范围。")
            if self._text(root, "rev-parse", "HEAD") != head:
                raise VersionPlanError("读取 Console 独立资源期间 HEAD 已变化。")
            return head, blob, bool(status)
        return read

    def _application_reader(self, repo, root, identity):
        """Fixed, read-only proof for explicitly configured root application files."""
        def read(source):
            if (source.get("path") != "app-manifest.json"
                    or source.get("kind") not in {"json", "app-manifest", "package"}
                    or (source.get("key") or "version") != "version"):
                return None
            configured = repo.get("versionSources", [])
            authorities = [item for item in configured if version_source_id(item) == version_source_id(source)]
            packages = [item for item in configured if item.get("path") == "package.json"
                        and item.get("kind") in {"json", "app-manifest", "package"}
                        and (item.get("key") or "version") == "version"]
            if not authorities or not packages:
                return None  # No inferred package/lock model from matching version numbers.
            if len(authorities) != 1 or len(packages) != 1:
                return {"ambiguous": True}
            paths = ("app-manifest.json", "package.json", "package-lock.json")
            head = self._text(root, "rev-parse", "HEAD")
            if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", head):
                raise VersionPlanError("同一应用的固定 HEAD 身份无法确认。")
            tree = self._git(root, "--literal-pathspecs", "ls-tree", "--name-only", "-z", head, "--", *paths)
            names = tree.split(b"\0")
            if tree and (not tree.endswith(b"\0") or any(name not in {path.encode("utf-8") for path in paths} for name in names[:-1])):
                raise VersionPlanError("同一应用的固定 HEAD 文件清单不完整。")
            head_files = {}
            for path in paths:
                blob = self._git(root, "show", head + ":" + path) if path.encode("utf-8") in names else None
                if blob is not None and len(blob) > VERSION_MAX_BYTES:
                    raise VersionPlanError("同一应用的固定 HEAD 版本文件超出读取范围。")
                head_files[path] = blob
            status = self._git(root, "--literal-pathspecs", "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames", "--", *paths)
            changed = set()
            if status and not status.endswith(b"\0"):
                raise VersionPlanError("同一应用的 Git 变化清单不完整。")
            for record in status.split(b"\0"):
                if not record:
                    continue
                if len(record) < 4 or record[2:3] != b" ":
                    raise VersionPlanError("同一应用的 Git 变化记录不能唯一读取。")
                path = record[3:].decode("utf-8", "surrogateescape")
                if path not in paths:
                    raise VersionPlanError("同一应用的 Git 变化范围不是固定根文件。")
                changed.add(path)
            if self._text(root, "rev-parse", "HEAD") != head:
                raise VersionPlanError("同一应用的关联版本读取期间 HEAD 已变化。")
            return {"sourceId": version_source_id(source), "packageSource": dict(packages[0]),
                    "repository": identity["repository"], "testMode": self._test_mode, "headSha": head,
                    "headFiles": head_files, "gitChanged": {path:path in changed for path in paths},
                    "participates": {path:not _excluded(path, repo["exclude"]) for path in paths}}
        return read

    def _saved_sync_changes(self, repo, root):
        result = {"syncChanged": False, "syncState": "none", "syncReason": "", "syncDifferences": []}
        try:
            self._sync_contract(repo)
            if not repo["syncFiles"]:
                return result
            records = self._sync_preflight(repo, root)
            for mapping, source, target, proof in records:
                self._catalog_remaining()
                target_proof = self._catalog_stable(target) if target.exists() else None
                if self._catalog_stable(source) != proof:
                    raise RepositoryPublishError("同步来源正在写入，请保存后重试。", code="sync_writing")
                if target_proof != proof:
                    result["syncDifferences"].append(mapping["target"])
            result.update(syncChanged=bool(result["syncDifferences"]),
                          syncState="changed" if result["syncDifferences"] else "unchanged",
                          syncReason="已保存工作文件与仓库快照不同；执行时先同步再确定本次版本。" if result["syncDifferences"] else "已保存工作文件与仓库快照相同。")
        except (RepositoryPublishError, OSError) as exc:
            if isinstance(exc, RepositoryPublishError) and exc.code == "worktree_changed":
                exc = RepositoryPublishError(str(exc), code="sync_writing")
            result.update(syncChanged=None, syncState="unknown", syncReason=self._error(exc), syncDifferences=[], diagnostic=self._diagnostic(exc))
        return result

    def _head_commit(self, root, head):
        """Read this exact commit's committer time, never a refresh timestamp."""
        if not _SHA.fullmatch(str(head)):
            return None
        try:
            raw = self._git(root, "show", "-s", "--no-show-signature", "--format=%H%x00%ct", head).strip()
            fields = raw.split(b"\0")
            if (len(fields) != 2 or fields[0].decode("ascii") != head
                    or not re.fullmatch(br"-?\d{1,16}", fields[1])):
                return None
            committed_at = datetime.fromtimestamp(int(fields[1]), timezone.utc).isoformat()
            return {"sha": head, "committedAt": committed_at}
        except (_GitFailure, UnicodeError, ValueError, OverflowError, OSError):
            return None

    def _local_changes(self, repo, context):
        """Display-only Git state; no fetch, synchronization, staging or locks."""
        root = context[0]
        result = {"hasChanges": None, "changeState": "unknown", "worktreeChanged": None,
                  "outgoingCommits": None, "remoteReference": "", "changesReason": "", "changedFiles": [], "headSha": "",
                  "outgoingBaselineSha": "", "outgoingBaselineSource": "", "deliveryVerifiedAt": "", "lastCommit": None,
                  "syncChanged": None, "syncState": "unknown", "syncReason": "", "syncDifferences": []}
        try:
            head = self._text(root, "rev-parse", "HEAD")
            result["headSha"] = head
            last_commit = self._head_commit(root, head)
            status = self._git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames")
            records = [record for record in status.split(b"\0") if record]
            if any(len(record) < 4 or record[2:3] != b" " for record in records):
                raise RepositoryPublishError("工作树状态回执不完整。")
            result["changedFiles"] = [{"path": record[3:].decode("utf-8", "surrogateescape"), "status": record[:2].decode("ascii")}
                                      for record in records if not _excluded(record[3:].decode("utf-8", "surrogateescape"), repo["exclude"])]
            result["worktreeChanged"] = bool(result["changedFiles"])
            reference = "refs/remotes/" + repo["remote"] + "/" + repo["branch"]
            result["remoteReference"] = reference
            baseline, baseline_source = "", ""
            try:
                baseline = self._text(root, "show-ref", "--verify", "--hash", reference)
                if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", baseline):
                    raise RepositoryPublishError("本地远端引用身份无法确认。")
                baseline_source = "tracking_ref"
            except _GitFailure:
                result["changesReason"] = "尚无可确认的本地远端引用；这里不会自动 fetch。"
            # Private transport preserves the user's tracking refs. A verified
            # delivery journal can establish a newer local acknowledgement,
            # without writing those refs or pretending to query today's remote.
            pending = _read(self._pending_path(repo["id"]))
            if (pending and pending.get("state") == "delivered" and pending.get("identity") == context[3]
                    and pending.get("repositorySettingsSha") == _repo_settings_sha(repo)
                    and pending.get("transportOptionsSha") == _json_sha(self._remote_options(repo, root))
                    and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", str(pending.get("commitSha", "")))
                    and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", str(pending.get("verifiedRemote", "")))
                    and pending.get("verifiedAt") and self._ancestor(root, pending["commitSha"], head)
                    and self._ancestor(root, pending["commitSha"], pending["verifiedRemote"])):
                acknowledged = pending["commitSha"]
                if not baseline or not self._ancestor(root, acknowledged, baseline):
                    baseline, baseline_source = acknowledged, "verified_delivery"
                    result.update(deliveryVerifiedAt=pending["verifiedAt"], changesReason="待推数量依据本仓库最近核验成功的回执；执行时会重新核验实际远端。")
            if baseline:
                outgoing = self._text(root, "rev-list", "--count", baseline + "..HEAD")
                if not re.fullmatch(r"\d+", outgoing):
                    raise RepositoryPublishError("待推提交数量无法确认。")
                result.update(outgoingCommits=int(outgoing), outgoingBaselineSha=baseline, outgoingBaselineSource=baseline_source)
            result.update(self._saved_sync_changes(repo, root))
            if self._text(root, "rev-parse", "HEAD") != head or self._git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames") != status:
                raise RepositoryPublishError("读取差异期间工作树或 HEAD 已变化。", code="worktree_changed")
            result["lastCommit"] = last_commit
            if result["worktreeChanged"] or result["syncChanged"] is True or result["outgoingCommits"] is not None and result["outgoingCommits"] > 0:
                result.update(hasChanges=True, changeState="changed")
            elif result["outgoingCommits"] == 0 and result["syncChanged"] is False:
                result.update(hasChanges=False, changeState="unchanged")
            if not result["changesReason"]:
                result["changesReason"] = "待推数量依据已保存的本地远端引用；执行时会重新核验实际远端。"
            if result["syncState"] in {"changed", "unknown"}:
                result["changesReason"] += " " + result["syncReason"]
        except (RepositoryPublishError, _GitFailure, OSError) as exc:
            result.update(hasChanges=None, changeState="unknown", worktreeChanged=None, changedFiles=[], changesReason=self._error(exc), diagnostic=self._diagnostic(exc))
        return result

    def _version_details(self, repo, context):
        root = context[0]
        sources = self._version_sources(repo, root)
        head = self._text(root, "rev-parse", "HEAD")
        components = version_catalog_items(root, sources, self._version_reader(root), self._git_version_reader(root),
                                           self._console_resource_reader(root), self._application_reader(repo, root, context[3]))
        by_id = {version_source_id(source): source for source in sources}
        plans = {plan["sourceId"]: plan for plan in repo.get("versionPlans", [])}
        for component in components:
            source = by_id[component["sourceId"]]
            component.update(repositoryHeadSha=head, headVersion="", headSourceMissing=None, versionChanged=None,
                             planState="none", plannedVersion="", transition=None)
            primary = Path(source["path"])
            companion_name = ("blender_manifest.toml" if primary.name == "__init__.py" and source["kind"] in {"python_ast", "bl_info"}
                              else "__init__.py" if primary.name == "blender_manifest.toml" else None)
            if companion_name and not (root / primary.parent / companion_name).exists():
                companion_path = (primary.parent / companion_name).as_posix()
                names = self._git(root, "--literal-pathspecs", "ls-tree", "--name-only", "-z", head, "--", companion_path).split(b"\0")
                if companion_path.encode("utf-8") in names:
                    component.update(canBump=False, companionState="blocked", reason="原 Blender 插件的另一版本声明已缺失，请协调一致；不会只升剩下的一份。")
            if any(entry["headSha"] != head for entry in component.get("consoleResourceEvidence", [])):
                raise RepositoryPublishError("读取 Console 资源和版本期间 HEAD 已变化。", code="worktree_changed")
            if any(entry["headSha"] != head for entry in component.get("applicationCompanionEvidence", {}).get("files", [])):
                raise RepositoryPublishError("读取同一应用关联版本期间 HEAD 已变化。", code="worktree_changed")
            if not component.get("currentVersion") and source["kind"] != "git_commit":
                try:
                    component["currentVersion"] = read_current_version(self._version_reader(root)(source["path"]), source)
                except (VersionPlanError, OSError, ValueError, UnicodeError, SyntaxError, KeyError, TypeError):
                    pass  # Missing or ambiguous authorities remain unknown.
            if source["kind"] == "git_commit" and component.get("sourceHeadSha") not in (None, head):
                raise RepositoryPublishError("提交版本读取期间 HEAD 已变化，请重新读取。", code="worktree_changed")
            if component.get("canBump") and component.get("expectedFiles"):
                try:
                    self._version_write_scope(repo, root, component["expectedFiles"])
                except (RepositoryPublishError, _GitFailure, OSError) as exc:
                    component.update(canBump=False, reason=self._error(exc))
            if component.get("currentVersion"):
                try:
                    if source["kind"] == "git_commit":
                        previous = component["currentVersion"]
                    else:
                        paths = self._git(root, "--literal-pathspecs", "ls-tree", "--name-only", "-z", head, "--", source["path"]).split(b"\0")
                        component["headSourceMissing"] = source["path"].encode("utf-8") not in paths
                        previous = None if component["headSourceMissing"] else read_current_version(
                            self._git(root, "show", head + ":" + source["path"]), source)
                    if previous is None:
                        component["versionChanged"] = None
                    else:
                        component.update(headVersion=previous, versionChanged=previous != component["currentVersion"])
                    if component["versionChanged"]:
                        component["transition"] = {"kind": "working", "fromVersion": previous, "toVersion": component["currentVersion"]}
                except (VersionPlanError, _GitFailure, ValueError, UnicodeError):
                    pass  # Unknown history is never claimed unchanged.
            if component.get("pairedCompanion"):
                companion = component["pairedCompanion"]
                component.update(companionHeadVersion="", companionVersionChanged=None, headCompanionMissing=None)
                try:
                    names = self._git(root, "--literal-pathspecs", "ls-tree", "--name-only", "-z", head, "--", companion["path"]).split(b"\0")
                    missing = companion["path"].encode("utf-8") not in names
                    component["headCompanionMissing"] = missing
                    if missing:
                        component["companionVersionChanged"] = True
                    else:
                        previous = read_current_version(self._git(root, "show", head + ":" + companion["path"]), companion)
                        component.update(companionHeadVersion=previous, companionVersionChanged=previous != component["currentVersion"])
                except (VersionPlanError, _GitFailure, ValueError, UnicodeError):
                    pass
            plan = plans.get(component["sourceId"])
            if plan:
                expected = {key: component.get(key) for key in ("sourceId", "currentVersion", "expectedSha256", "expectedBytes", "planProof")}
                expected["targetVersion"] = component.get("nextVersion")
                component["planState"] = "valid" if component.get("canBump") and plan == expected else "stale"
                if component["planState"] == "valid":
                    component["plannedVersion"] = plan["targetVersion"]
                    component["transition"] = {"kind": "planned", "fromVersion": plan["currentVersion"], "toVersion": plan["targetVersion"]}
        overlaps = self._version_overlaps(root, [entry for component in components if component.get("canBump") for entry in component.get("expectedFiles", [])])
        for component in components:
            if any(entry["path"] in overlaps for entry in component.get("expectedFiles", [])):
                component.update(canBump=False, reason="版本文件的实际来源重叠，请手动协调；不会分别改写。")
                if component["planState"] == "valid":
                    component.update(planState="stale", plannedVersion="", transition=None)
        if self._text(root, "rev-parse", "HEAD") != head:
            raise RepositoryPublishError("版本读取期间 HEAD 已变化，请重新读取。", code="worktree_changed")
        for component in components:
            if component["sourceId"] in by_id and not component.get("canBump"):
                component["diagnostic"] = _make_diagnostic("version_authority", component.get("reason") or "权威版本无法安全读取。",
                                                           source_id=component["sourceId"])
        return components

    @staticmethod
    def _catalog_diagnostic(item):
        if (item.get("diagnostic") or {}).get("severity") not in {None, "info"}:
            return
        failed = next((component["diagnostic"] for component in item.get("components", [])
                       if (component.get("diagnostic") or {}).get("severity") in {"warning", "error"}), None)
        summary = item.get("uploadSummary") or {}
        if failed:
            item["diagnostic"] = failed
        elif summary.get("state") in {"unknown", "pending"}:
            item["diagnostic"] = _make_diagnostic("receipt_unverified", summary.get("reason") or "上传记录待核对。")

    def version_catalog(self, repo_id=None, *, deadline_seconds=None):
        """A bounded optional display read never limits a later real upload."""
        if deadline_seconds is None:
            return self._version_catalog_read(repo_id)
        if type(deadline_seconds) not in {int, float} or not 0 < deadline_seconds <= 120:
            raise RepositoryPublishError("版本读取时限无效。")
        sentinel = object()
        previous = getattr(self._lease, "catalog_deadline", sentinel)
        deadline = time.monotonic() + deadline_seconds
        self._lease.catalog_deadline = min(previous, deadline) if previous is not sentinel else deadline
        try:
            return self._version_catalog_read(repo_id)
        finally:
            if previous is sentinel:
                del self._lease.catalog_deadline
            else:
                self._lease.catalog_deadline = previous

    def _version_catalog_read(self, repo_id=None):
        """Read exact current versions; never sync, stage, fetch or change files."""
        if not self.allowed:
            raise RepositoryPublishError("当前入口不允许读取版本配置。")
        settings = self._settings()
        with self._activity_policy(settings["naming"]):
            return self._version_catalog_frozen(repo_id, settings)

    def _version_catalog_frozen(self, repo_id, settings):
        rows = settings["repositories"]
        if repo_id is not None and (not isinstance(repo_id, str) or repo_id not in {row["id"] for row in rows}):
            raise RepositoryPublishError("仓库编号不存在。")
        result = []
        for repo in rows:
            if repo_id is not None and repo["id"] != repo_id:
                continue
            item = {"repoId": repo["id"], "name": Path(repo["path"]).name or repo["id"], "components": [], "message": "",
                    "readState": "ready",
                    "sourceIdentity": catalog_source_identity(repo, settings.get("naming", {})),
                    "lastCommit": None,
                    "uploadSummary": self._upload_summary(repo),
                    "hasChanges": None, "changeState": "unknown", "worktreeChanged": None, "outgoingCommits": None,
                    "diagnostic": None, "planState": "none", "versionChanged": None, "versionState": "unknown",
                    "syncChanged": None, "syncState": "unknown", "syncReason": "", "syncDifferences": []}
            item["activityPolicy"] = "allow_saved_snapshot" if self._lease.allow_active_work else "strict"
            try:
                self._catalog_remaining()
                context = self._repo(repo)
                root = context[0]
                sources = self._version_sources(repo, root)
                item["components"] = self._version_details(repo, context)
                item.update(self._local_changes(repo, context))
                if any(component["repositoryHeadSha"] != item["headSha"] for component in item["components"]):
                    raise RepositoryPublishError("读取仓库差异和版本期间 HEAD 已变化，请重新读取。", code="worktree_changed")
                self._planned_versions(repo, context, item["components"], item["changedFiles"], settings["naming"],
                                       sync_pending=bool(repo["syncFiles"]), changes_known=item["worktreeChanged"] is not None)
                states = {component["planState"] for component in item["components"]}
                if any(plan["sourceId"] not in {component["sourceId"] for component in item["components"]} for plan in repo.get("versionPlans", [])):
                    states.add("stale")
                item["planState"] = "stale" if "stale" in states else "valid" if "valid" in states else "none"
                differences = [component["versionChanged"] for component in item["components"]]
                item["versionChanged"] = True if True in differences else None if not differences or None in differences else False
                known = [bool(component.get("currentVersion")) for component in item["components"]]
                item["versionState"] = "missing" if not known else "known" if all(known) else "partial" if any(known) else "unknown"
                if not sources:
                    item["message"] = "此仓库没有独立版本来源，使用已配置的进度标题；不会创建版本文件。"
                    if not item.get("diagnostic"):
                        item["diagnostic"] = _make_diagnostic("version_fallback", item["message"])
                if item.get("syncState") == "unknown":
                    item["message"] = item["syncReason"]
                self._catalog_remaining()
            except (RepositoryPublishError, _GitFailure, OSError) as exc:
                item["readState"] = "error"
                item["message"] = self._error(exc)
                item["diagnostic"] = self._diagnostic(exc)
                item.update(hasChanges=None, changeState="unknown", worktreeChanged=None)
                for component in item["components"]:
                    component.update(canBump=False, reason=item["message"])
                    if (component.get("transition") or {}).get("kind") == "auto":
                        component["transition"] = None
                    component["autoPlan"] = {"state":"unknown", "fromVersion":component.get("currentVersion", ""),
                                             "targetVersion":"", "reason":item["message"]}
            self._catalog_diagnostic(item)
            result.append(item)
        return {"repositories": result}

    def _version_overlaps(self, root, files):
        identities = {}
        for entry in files:
            info = _safe_path(root / entry["path"]).stat()
            identities.setdefault((info.st_dev, info.st_ino), set()).add(entry["path"])
        return {path for paths in identities.values() if len(paths) > 1 for path in paths}

    def _version_write_scope(self, repo, root, files):
        if not files:
            return  # Git-subject plans have no writable authority files.
        paths = [item["path"] for item in files]
        sync_paths, sync_identities = set(), set()
        for mapping in repo["syncFiles"]:
            self._catalog_remaining()
            for location in (mapping["source"], root / mapping["target"]):
                location = _safe_path(location)
                sync_paths.add(os.path.normcase(str(location)))
                if location.exists():
                    info = location.stat()
                    sync_identities.add((info.st_dev, info.st_ino))
        for name in paths:
            path = _safe_path(root / name)
            info = path.stat()
            if info.st_nlink != 1:
                raise RepositoryPublishError("版本文件存在硬链接来源重叠，请手动准备版本；不会改写其他文件。")
            if (_excluded(name, repo["exclude"]) or os.path.normcase(str(path)) in sync_paths
                    or (info.st_dev, info.st_ino) in sync_identities):
                raise RepositoryPublishError("版本文件属于排除范围或同步来源/目标，请在原来源手动准备版本。")
        if self._version_overlaps(root, files):
            raise RepositoryPublishError("版本文件的实际来源重叠，请手动协调；不会分别改写。")
        tracked = set(self._git(root, "--literal-pathspecs", "ls-files", "-z", "--", *paths).decode("utf-8").split("\0"))
        if not set(paths) <= tracked:
            raise RepositoryPublishError("版本文件尚未由 Git 跟踪，请先手动保存并提交该文件。")
        flags = self._git(root, "--literal-pathspecs", "ls-files", "-v", "-z", "--", *paths).split(b"\0")
        if any(record and record[:1] != b"H" for record in flags):
            raise RepositoryPublishError("版本文件设有特殊索引标记，请先处理 skip-worktree 或 assume-unchanged；不会改写。")
        for name in paths:
            path = _safe_path(root / name)
            if not path.stat().st_mode & stat.S_IWRITE:
                raise RepositoryPublishError("版本文件为只读，请先恢复可写状态或手动准备版本。")
            with _version_write_lease(path):
                pass  # Capability preflight, no write; includes all companions.

    def _version_updates(self, repo, context, plans=None):
        try:
            updates, plans = prepare_version_updates(context[0], self._version_sources(repo, context[0]),
                                                     repo.get("versionPlans", []) if plans is None else plans,
                                                     self._version_reader(context[0]), self._git_version_reader(context[0]),
                                                     self._console_resource_reader(context[0]), self._application_reader(repo, context[0], context[3]))
        except VersionPlanError as exc:
            raise RepositoryPublishError(str(exc), code="version_plan_blocked") from exc
        self._version_write_scope(repo, context[0], updates)
        return updates, plans

    @staticmethod
    def _affected_sources(sources, files):
        selected = set()
        for file in files:
            matching = [source for source in sources if file["path"] == source["path"] or _matches(file["path"], source["scope"])]
            def specificity(source):
                if file["path"] == source["path"]:
                    return len(file["path"]) + 10000
                scopes = source["scope"] if isinstance(source["scope"], list) else [source["scope"]]
                return max((len(re.split(r"[*?\[]", value)[0].strip("/")) for value in scopes if _matches(file["path"], value)), default=0)
            best = max((specificity(source) for source in matching), default=-1)
            selected.update(version_source_id(source) for source in matching if specificity(source) == best)
        return selected

    def _planned_versions(self, repo, context, components, files, naming, *, sync_pending=False, changes_known=True, strict=False):
        """Read-only candidates. Only the locked, synchronized worker freezes them."""
        sources = self._version_sources(repo, context[0])
        affected = self._affected_sources(sources, files)
        shared_paths = {source["path"] for source in sources if sum(other["path"] == source["path"] for other in sources) > 1}
        by_id = {version_source_id(source): source for source in sources}
        explicit = {plan["sourceId"]: plan for plan in repo.get("versionPlans", [])}
        effective, automatic, blocked = [], [], []
        for component in components:
            ident = component["sourceId"]
            state, reason, target = "none", "", ""
            component["worktreeChanged"] = ident in affected if changes_known else None
            hidden_resources = [entry["path"] for entry in component.get("consoleResourceEvidence", [])
                                if entry["changed"] and entry["path"] not in {file["path"] for file in files}]
            if hidden_resources and not sync_pending:
                component.update(canBump=False, reason="Console 改动资源未进入实际 Git 变化范围，请处理忽略或特殊索引标记：" + ", ".join(hidden_resources))
                if component["planState"] == "valid":
                    component.update(planState="stale", plannedVersion="", transition=None)
            file_paths = {file["path"] for file in files}
            hidden_versions = [component["path"]] if (component["versionChanged"] is True or component.get("headSourceMissing") is True) and component["path"] not in file_paths else []
            if (component.get("pairedCompanion") and component.get("companionVersionChanged") is not False
                    and component["pairedCompanion"]["path"] not in file_paths):
                hidden_versions.append(component["pairedCompanion"]["path"])
            if component.get("companionState") == "blocked" and ident in affected:
                state, reason = "blocked", component.get("reason") or "同一插件的双版本声明无法一致确认。"
            elif hidden_versions and ident in affected:
                state, reason = "blocked", "手动或新增版本声明未进入实际 Git 变化范围，请处理排除或特殊索引标记；不会冒称提交了目标版本：" + ", ".join(hidden_versions)
            elif ident in explicit:
                if component["planState"] == "valid":
                    effective.append(explicit[ident])
                elif files:
                    blocked.append("一次性版本计划已过期，请重新配置。" + component.get("reason", ""))
                reason = "已配置的一次性计划优先。"
            elif not naming.get("autoBump", True):
                reason = "自动升版已关闭。"
            elif sync_pending:
                state, reason = "sync_pending", "先同步已保存工作文件，再核对改动组件和版本。"
                if (component.get("transition") or {}).get("kind") == "auto":
                    component["transition"] = None
            elif not changes_known:
                state, reason = "unknown", "真实工作树变化尚未确认。"
            elif ident not in affected:
                reason = "此组件没有待提交文件变化；已有提交保留原版本。"
            elif component["versionChanged"] is True:
                state, reason = "manual_version", "版本已手动改变，保留当前版本，不再次递增。"
            elif component["path"] in shared_paths and not any(file["path"] != component["path"] and
                                                               _matches(file["path"], by_id[ident]["scope"]) for file in files):
                reason = "共享版本文件的载体变化不代表此组件有改动；版本未变的字段保留。"
                component["worktreeChanged"] = False if component["versionChanged"] is False else None
            elif component.get("headSourceMissing") is True and component.get("currentVersion"):
                state, reason = "initial_version", "新版本来源保留声明的初始版本。"
            elif component["versionChanged"] is None:
                state, reason = "blocked", "无法确认 HEAD 权威版本，不自动猜测下一版。"
            elif not component.get("canBump") or not component.get("currentVersion"):
                state, reason = "blocked", component.get("reason") or "权威版本无法安全准备。"
            else:
                state, target = "eligible", component["nextVersion"]
                candidate = {key: component[key] for key in ("sourceId", "currentVersion", "expectedSha256", "expectedBytes", "planProof")}
                candidate["targetVersion"] = target
                effective.append(candidate)
                automatic.append(ident)
                component["transition"] = {"kind": "auto", "fromVersion": component["currentVersion"], "toVersion": target}
                reason = "根据当前已保存变化预览；同步和提交前会重新核对。"
            if state == "blocked":
                component["diagnostic"] = _make_diagnostic("version_plan_blocked", reason, source_id=ident)
            elif component["planState"] == "stale":
                component["diagnostic"] = _make_diagnostic("version_plan_stale", "一次性版本计划已过期，请重新配置。", source_id=ident)
            component["autoPlan"] = {"state": state, "fromVersion": component.get("currentVersion", ""), "targetVersion": target, "reason": reason}
            if state == "blocked":
                blocked.append((component.get("name") or component["path"]) + ": " + reason)
        if explicit.keys() - {component["sourceId"] for component in components} and files:
            blocked.append("一次性版本来源已改变，请重新配置。")
        if strict and blocked:
            raise RepositoryPublishError("自动升版暂缓本仓库：" + "；".join(dict.fromkeys(blocked)), code="version_plan_blocked")
        return effective, automatic, blocked

    def _consume_version_plans(self, repo, pending):
        used = pending.get("versionPlans", [])
        if not used or not pending.get("commitSha"):
            return
        if pending["commitSha"] == pending["parentSha"]:
            raise RepositoryPublishError("版本文件未形成实际提交，请检查 Git 过滤器；保留版本计划。")
        with self._mutex, _file_lock(self.state_dir / "settings.lock"):
            settings = self._settings()
            current = next((row for row in settings["repositories"] if row["id"] == repo["id"]), None)
            if current is not None and _repo_settings_sha(current) == pending["repositorySettingsSha"]:
                # Full-plan CAS: never remove a newer explicit user selection.
                remaining = [plan for plan in current.get("versionPlans", []) if plan not in used]
                if remaining != current.get("versionPlans", []):
                    current["versionPlans"] = remaining
                    _atomic(self._settings_path, settings)

    def _version_intent_snapshot(self, repo, context, pending):
        current = self._snapshot(repo, context)
        original = pending["versionBaseSnapshot"]
        if any(current[key] != original[key] for key in ("head", "indexSha", "configSha", "identity")):
            raise RepositoryPublishError("版本计划开始后仓库、分支或暂存区变化，保留已保存文件。")
        paths = {update["path"] for update in pending["versionUpdates"]}
        if [item for item in current["files"] if item["path"] not in paths] != [item for item in original["files"] if item["path"] not in paths]:
            raise RepositoryPublishError("版本准备期间其他工作文件发生变化，保留一次性计划待核对。")
        for update in pending["versionUpdates"]:
            proof = _stable(context[0] / update["path"])
            if proof["sha256"] not in {update["beforeSha256"], update["afterSha256"]}:
                raise RepositoryPublishError("版本文件出现其他修改，保留原文和一次性计划待核对。")
        latest = next((row for row in self._settings()["repositories"] if row["id"] == repo["id"]), None)
        if (latest is None or _repo_settings_sha(latest) != pending["repositorySettingsSha"]
                or _json_sha(latest.get("versionPlans", [])) != pending["versionPlansSha"]):
            raise RepositoryPublishError("版本准备期间配置或版本选择变化，请先核对原计划。")
        self._verify_version_evidence(context[0], pending)
        return current

    def _verify_version_evidence(self, root, pending):
        for entry in pending.get("versionReadEvidence", []):
            if (entry.get("path") not in {"console-repository-publish.js", "console-repository-publish.css"}
                    or entry.get("headSha") != pending["parentSha"]
                    or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("expectedSha256", "")))
                    or type(entry.get("expectedBytes")) is not int or not 0 <= entry["expectedBytes"] <= VERSION_MAX_BYTES):
                raise RepositoryPublishError("Console 资源版本证明损坏，请保留原文件和记录。")
            if _stable(root / entry["path"]) != {"sha256":entry["expectedSha256"], "bytes":entry["expectedBytes"]}:
                raise RepositoryPublishError("Console 资源在版本准备期间变化，保留原计划和文件；不会生成错误缓存版本。")

    def _apply_version_intent(self, repo, context, pending, pending_path):
        root = context[0]
        self._busy_reason(root)
        self._version_intent_snapshot(repo, context, pending)
        self._verify_sync(repo, context, pending.get("syncProofs", []))
        # Recheck remote before any resumed or first version write.
        remote = self._remote(repo, root)
        self._fetch(repo, context, remote)
        if remote and not self._ancestor(root, remote, pending["parentSha"]):
            raise RepositoryPublishError("远端领先或分叉，尚未继续版本准备；请先自行整合。")
        self._version_write_scope(repo, root, pending["versionUpdates"])
        pending["state"] = "version_applying"
        _atomic(pending_path, pending)
        for update in pending["versionUpdates"]:
            self._busy_reason(root)
            self._version_intent_snapshot(repo, context, pending)
            path = _safe_path(root / update["path"])
            proof = _stable(path)
            if proof["sha256"] == update["afterSha256"]:
                continue  # Exact durable target already written; never bump again.
            raw = base64.b64decode(update["afterBase64"], validate=True)
            if len(raw) != update["afterBytes"] or _sha(raw) != update["afterSha256"]:
                raise RepositoryPublishError("版本准备记录损坏，请保留原文件和记录。")
            self._busy_reason(root)
            self._version_intent_snapshot(repo, context, pending)
            with _version_write_lease(path) as stream:
                before = stream.read(VERSION_MAX_BYTES + 1)
                if len(before) != update["beforeBytes"] or _sha(before) != update["beforeSha256"]:
                    raise RepositoryPublishError("版本文件在写入前变化，请保存完成后重试原计划。")
                baseline = pending["versionBaseSnapshot"]
                index = context[1] / "index"
                if (self._repo(repo)[3] != baseline["identity"]
                        or self._text(root, "rev-parse", "HEAD") != baseline["head"]
                        or (_sha(index.read_bytes()) if index.exists() else None) != baseline["indexSha"]
                        or _sha(self._git(root, "config", "--null", "--list")) != baseline["configSha"]):
                    raise RepositoryPublishError("版本写入前仓库、分支、配置或暂存选择变化，保留原计划。")
                self._busy_reason(root)
                if os.fstat(stream.fileno()).st_nlink != 1:
                    raise RepositoryPublishError("版本文件存在硬链接来源重叠，请手动准备版本；不会改写其他文件。")
                stream.seek(0)
                stream.write(raw)
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
            self._version_intent_snapshot(repo, context, pending)
        snapshot = self._version_intent_snapshot(repo, context, pending)
        paths = {update["path"] for update in pending["versionUpdates"]}
        if not paths <= {item["path"] for item in snapshot["files"]}:
            raise RepositoryPublishError("版本修改未进入可提交范围，请检查忽略规则并保留计划。")
        pending["title"], pending["body"], pending["versions"] = self._message(
            repo, snapshot, pending["naming"], version_plans=pending["versionPlans"],
            automatic_source_ids=pending.get("automaticSourceIds", []))
        pending.update(state="prepared", snapshot=snapshot, indexReconciled=False)
        _atomic(pending_path, pending)
        return snapshot

    @property
    def busy(self):
        with self._mutex:
            local = bool(self._queue or self._worker and self._worker.is_alive())
        latest = self.operation()
        return local or bool(latest and latest.get("status") in {"working", "queued"})

    def status(self):
        settings = self._settings()
        normalized = self._normalize(settings)
        return {"settings": settings, "warnings": settings.get("warnings", []), "operation": self.operation(),
                "uploadSummaries": [{"repoId": repo["id"], **self._upload_summary(repo)} for repo in settings["repositories"]],
                "normalizedSettings": normalized, "settingsSha": _json_sha(normalized),
                "casRequired": settings.get("casRequired") is True,
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
                receipt["diagnostic"] = _make_diagnostic("operation_interrupted", receipt["message"])
                for row in receipt.get("repositories", []):
                    if isinstance(row, dict) and row.get("status") in {"queued", "working"}:
                        row["diagnostic"] = dict(receipt["diagnostic"])
        if receipt:
            rows = receipt.get("repositories", [])
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue
                if "uploadSummary" not in row:
                    row["uploadSummary"] = self._upload_value(
                        {"repoId": row.get("repoId", ""), "path": "", "repositoryUrl": "", "remote": "", "branch": ""},
                        state="unknown", count=None, reason="旧操作未保留固定上传目标；请以当前仓库的确认记录为准。")
                if row.get("status") in {"deferred", "push_failed", "verification_required"} and not row.get("diagnostic"):
                    row["diagnostic"] = _make_diagnostic("manual_check", row.get("message", "请核对保留记录。"))
                row["progress"] = self._item_progress(row, interrupted=receipt.get("status") == "verification_required")
            receipt["progress"] = self._operation_progress(receipt)
        return receipt

    @staticmethod
    def _operation_progress(receipt):
        rows = receipt.get("repositories", [])
        rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        terminal = [row for row in rows if row.get("status") not in {"queued", "working"}]
        current = next((row for row in rows if row.get("status") == "working"), {}) if receipt.get("status") in {"queued", "working"} else {}
        return {"total": len(rows), "completed": len(terminal),
                "succeeded": sum(row.get("status") == "success" for row in terminal),
                "skipped": sum(row.get("status") == "noop" for row in terminal),
                "needsAttention": sum(row.get("status") not in {"success", "noop"} for row in terminal),
                "currentRepoId": current.get("repoId", ""), "currentPhase": current.get("phase", "")}

    @staticmethod
    def _item_progress(item, *, interrupted=False):
        status, phase = item.get("status"), item.get("phase", "queued")
        summary = item.get("uploadSummary") if isinstance(item.get("uploadSummary"), dict) else {}
        verified = (bool(_SHA.fullmatch(str(item.get("commitSha", "")))) and
                    (bool(_SHA.fullmatch(str(item.get("verifiedRemote", "")))) and
                     RepositoryPublishService._upload_time(item.get("deliveryVerifiedAt")) or
                     summary.get("state") == "recorded" and summary.get("commitSha") == item.get("commitSha") and
                     RepositoryPublishService._upload_time(summary.get("verifiedAt"))))
        previous = item.get("progress") if isinstance(item.get("progress"), dict) else {}
        state = ("blocked" if interrupted and status in {"queued", "working"} else
                 "complete" if status == "success" else "skipped" if status == "noop" else
                 "queued" if status == "queued" else "indeterminate" if status == "working" else "blocked")
        if state == "indeterminate" and previous.get("state") == "measured" and previous.get("phase") == phase:
            value = dict(previous)
        elif (previous.get("state") == state and previous.get("phase") == phase and
              (state != "complete" or previous.get("percent") == (100 if verified else None) and
               previous.get("source") == ("receipt" if verified else "historical_receipt"))):
            value = dict(previous)
        else:
            value = {"state": state, "phase": phase, "scope": "repository" if state == "complete" else "phase",
                     "unit": None, "current": None, "total": None, "percent": 100 if state == "complete" and verified else None,
                     "source": "historical_receipt" if state == "complete" and not verified else "receipt",
                     "step": None, "startedAt": item.get("startedAt"),
                     "phaseStartedAt": previous.get("phaseStartedAt") if previous.get("phase") == phase else _now(),
                     "updatedAt": _now()}
            if previous.get("state") == "measured" and state == "blocked":
                value["lastTransfer"] = {key: previous.get(key) for key in
                                         ("scope", "unit", "current", "total", "percent", "source", "step", "updatedAt")}
        # GET computes elapsed time without pretending there is a new event.
        try:
            started = datetime.fromisoformat(str(value.get("startedAt")))
            end = datetime.now(timezone.utc) if status in {"queued", "working"} and not interrupted else datetime.fromisoformat(value["updatedAt"])
            value["elapsedSeconds"] = max(0, int((end - started).total_seconds()))
        except (ValueError, TypeError):
            value["elapsedSeconds"] = 0
        return value

    @staticmethod
    def _upload_binding(repo):
        return {"repoId": repo["id"], **{key: repo[key] for key in ("path", "repositoryUrl", "remote", "branch")}}

    def _upload_destination(self, value):
        if not isinstance(value, dict):
            raise RepositoryPublishError("上传序号的目标记录不完整。")
        identity = value.get("identity", value)
        if not isinstance(identity, dict):
            raise RepositoryPublishError("上传序号的目标记录不完整。")
        if "repository" in identity:
            repository, branch = identity.get("repository"), identity.get("branch")
        else:
            repository = (os.path.normcase(str(Path(value["repositoryUrl"]).resolve())) if self._test_mode
                          else self._github(value.get("repositoryUrl", "")))
            branch = value.get("branch")
        if not isinstance(repository, str) or not repository or not isinstance(branch, str) or not branch or "\0" in branch:
            raise RepositoryPublishError("上传序号的仓库或目标分支尚未核定。")
        return {"repository": repository, "branch": branch}

    def _upload_ledger(self, destination):
        path = self._uploads / (_json_sha(destination) + ".json")
        ledger = _read(path)
        if ledger is None:
            return path, None
        events = ledger.get("events")
        if (ledger.get("schema") != "console-confirmed-uploads-v1" or ledger.get("destination") != destination
                or not isinstance(events, list) or not self._upload_time(ledger.get("startedAt"))):
            raise RepositoryPublishError("上传序号记录格式错误，原上传回执保留；请核对记录。")
        seen = set()
        for number, event in enumerate(events, 1):
            if (not isinstance(event, dict) or type(event.get("sequence")) is not int or event["sequence"] != number
                    or not _SHA.fullmatch(str(event.get("commitSha", "")))
                    or not _SHA.fullmatch(str(event.get("verifiedRemote", "")))
                    or not self._upload_time(event.get("verifiedAt"))
                    or not _REQUEST.fullmatch(str(event.get("requestId", "")))
                    or event["commitSha"] in seen):
                raise RepositoryPublishError("上传序号记录不一致，原上传回执保留；不会重置或猜测次数。")
            seen.add(event["commitSha"])
        return path, ledger

    @staticmethod
    def _upload_time(value):
        if not isinstance(value, str):
            return False
        try:
            return datetime.fromisoformat(value).tzinfo is not None
        except ValueError:
            return False

    def _delivery_evidence(self, pending, destination):
        return (isinstance(pending, dict) and pending.get("state") == "delivered"
                and self._upload_destination(pending) == destination
                and bool(_SHA.fullmatch(str(pending.get("commitSha", ""))))
                and bool(_SHA.fullmatch(str(pending.get("verifiedRemote", ""))))
                and self._upload_time(pending.get("verifiedAt"))
                and bool(_REQUEST.fullmatch(str(pending.get("requestId", "")))))

    def _upload_floor(self, pending, destination):
        """A missing/truncated established ledger must never silently reset."""
        if not pending or self._upload_destination(pending) != destination:
            return 0, False
        floor, required = 0, False
        base = pending.get("uploadCounterBase")
        if base is not None:
            if (not isinstance(base, dict) or base.get("destination") != destination
                    or type(base.get("count")) is not int or base["count"] < 0
                    or type(base.get("ledgerExisted")) is not bool):
                raise RepositoryPublishError("上传序号的起始记录不一致，请保留回执核对。")
            floor, required = base["count"], base["ledgerExisted"]
        summary = pending.get("uploadSummary")
        if isinstance(summary, dict) and summary.get("source") == "console_confirmed_deliveries" and summary.get("state") == "recorded":
            if type(summary.get("count")) is not int or summary["count"] < 0:
                raise RepositoryPublishError("已确认上传序号不一致，请保留回执核对。")
            if self._upload_destination(summary.get("binding")) == destination:
                floor = max(floor, summary["count"])
                required = required or summary["count"] > 1 or (summary["count"] > 0 and summary.get("commitSha") != pending.get("commitSha"))
        return floor, required

    def _delivery_acknowledged(self, pending):
        request_id = pending.get("deliveryRecoveryRequestId") or pending.get("requestId")
        if not _REQUEST.fullmatch(str(request_id)):
            return False
        original = _read(self._ops / (request_id + ".json"), {})
        rows = original.get("repositories", [])
        return isinstance(rows, list) and any(isinstance(row, dict) and row.get("repoId") == pending.get("repoId")
                                             and row.get("status") == "success" and row.get("commitSha") == pending.get("commitSha")
                                             for row in rows)

    def _upload_anchors(self, pending, destination):
        anchors = []
        if not pending or self._upload_destination(pending) != destination:
            return anchors
        base = pending.get("uploadCounterBase")
        if isinstance(base, dict) and "commitSha" in base and base.get("count", 0):
            anchors.append({"count": base["count"], "commitSha": base["commitSha"]})
        summary = pending.get("uploadSummary")
        if (isinstance(summary, dict) and summary.get("source") == "console_confirmed_deliveries"
                and summary.get("state") == "recorded" and summary.get("count", 0)
                and self._upload_destination(summary.get("binding")) == destination):
            anchors.append({"count": summary["count"], "commitSha": summary.get("commitSha")})
        if any(type(anchor["count"]) is not int or anchor["count"] < 1
               or not _SHA.fullmatch(str(anchor["commitSha"])) for anchor in anchors):
            raise RepositoryPublishError("上传序号与原确认提交的关联不一致，请保留回执核对。")
        return anchors

    def _upload_check_anchors(self, pending, destination, ledger):
        for anchor in self._upload_anchors(pending, destination):
            if anchor["count"] > len(ledger["events"]) or ledger["events"][anchor["count"] - 1]["commitSha"] != anchor["commitSha"]:
                raise RepositoryPublishError("上传序号对应的原提交不一致，不会把同一确认追加为另一次上传。")

    @staticmethod
    def _upload_value(binding, *, state="recorded", count=0, event=None, started_at="", reason=""):
        return {"state": state, "count": count, "commitSha": (event or {}).get("commitSha", ""),
                "verifiedAt": (event or {}).get("verifiedAt", ""), "startedAt": started_at,
                "source": "console_confirmed_deliveries", "binding": binding,
                "reason": reason or "仅计本机 Console 保留并确认的上传记录，不代表完整 Git 历史或插件软件版本。"}

    def _upload_summary(self, repo):
        """Read-only local receipts; never infer upload counts from Git history."""
        binding = self._upload_binding(repo)
        try:
            destination = self._upload_destination(repo)
            _, ledger = self._upload_ledger(destination)
            pending = _read(self._pending_path(repo["id"]))
            floor, ledger_required = self._upload_floor(pending, destination)
            evidence = self._delivery_evidence(pending, destination) if pending else False
            events = ledger["events"] if ledger else []
            if (ledger is None and ledger_required) or (ledger is not None and len(events) < floor):
                raise RepositoryPublishError("已确认上传序号的历史记录缺失，不会重新从 1 计数。")
            if ledger is not None:
                self._upload_check_anchors(pending, destination, ledger)
            if pending and pending.get("uploadCounterPending") is True and evidence:
                return self._upload_value(binding, state="pending", count=None, reason="上传已确认，序号记录待核对；重试只恢复原记录，不重复上传。")
            if evidence and pending["commitSha"] not in {event["commitSha"] for event in events}:
                # A legacy receipt is already durable confirmation. Expose it
                # without writing on GET; the next explicit run persists it
                # before this per-repository pending journal can be replaced.
                event = {key: pending[key] for key in ("commitSha", "verifiedAt")}
                return self._upload_value(binding, count=len(events) + 1, event=event,
                                          started_at=ledger["startedAt"] if ledger else pending["verifiedAt"])
            if events:
                return self._upload_value(binding, count=len(events), event=events[-1], started_at=ledger["startedAt"])
            # Old operation rows did not freeze destination identity. A success
            # row for this id cannot seed a new binding's numerical history.
            if ledger is None:
                for operation_path in self._ops.glob("*.json"):
                    operation = _read(operation_path, {})
                    if any(row.get("repoId") == repo["id"] and row.get("status") == "success"
                           for row in operation.get("repositories", []) if isinstance(row, dict)):
                        return self._upload_value(binding, state="unknown", count=None, reason="旧成功记录缺少固定上传目标，历史起点待核对；不会用 Git 提交数猜测。")
            return self._upload_value(binding, started_at=ledger["startedAt"] if ledger else "")
        except (RepositoryPublishError, OSError, ValueError, KeyError, TypeError):
            return self._upload_value(binding, state="unknown", count=None, reason="上传序号记录不可读取或不一致；原工作与回执保留，次数待核对。")

    def _record_delivery(self, repo, pending, pending_path, item):
        """Idempotent ledger append after the delivered journal is durable.

        If the ledger cannot be saved, retain the confirmed pending journal and
        stop its replacement on the next run. A successful push stays success.
        """
        binding = pending.get("uploadBinding") or self._upload_binding(repo)
        destination, floor, ledger_required, anchors = None, 0, False, []
        try:
            destination = self._upload_destination(pending)
            if not self._delivery_evidence(pending, destination):
                raise RepositoryPublishError("原上传确认记录不完整，请保留回执后核对。")
            if "uploadBinding" not in pending:
                identity = pending["identity"]
                same = (os.path.normcase(str(Path(repo["path"]).resolve())) == os.path.normcase(str(Path(identity.get("root", "")).resolve()))
                        and repo["remote"] == identity.get("remote") and repo["branch"] == identity.get("branch")
                        and self._upload_destination(repo) == destination)
                if not same:
                    binding = {"repoId": pending.get("repoId", ""), "path": identity.get("root", ""),
                               "repositoryUrl": identity.get("fetchUrl", ""), "remote": identity.get("remote", ""), "branch": identity.get("branch", "")}
            floor, ledger_required = self._upload_floor(pending, destination)
            anchors = self._upload_anchors(pending, destination)
            path = self._uploads / (_json_sha(destination) + ".json")
            with _file_lock(path.with_suffix(".lock")):
                _, ledger = self._upload_ledger(destination)
                if (ledger is None and ledger_required) or (ledger is not None and len(ledger["events"]) < floor):
                    raise RepositoryPublishError("已确认上传序号的历史记录缺失，不会重新从 1 计数。")
                if ledger is not None:
                    self._upload_check_anchors(pending, destination, ledger)
                if ledger is None:
                    ledger = {"schema": "console-confirmed-uploads-v1", "destination": destination,
                              "startedAt": pending["verifiedAt"], "events": []}
                events = ledger["events"]
                event = next((event for event in events if event["commitSha"] == pending["commitSha"]), None)
                if event is None:
                    event = {"sequence": len(events) + 1, **{key: pending[key] for key in
                             ("commitSha", "verifiedRemote", "verifiedAt", "requestId")}}
                    events.append(event)
                    _atomic(path, ledger)
                summary = self._upload_value(binding, count=len(events), event=events[-1], started_at=ledger["startedAt"])
                pending.update(uploadSummary=summary, uploadCounterPending=False)
                _atomic(pending_path, pending)
                item["uploadSummary"] = summary
                return True
        except (RepositoryPublishError, OSError, ValueError, KeyError, TypeError):
            summary = self._upload_value(binding, state="pending", count=None,
                                         reason="上传已确认，序号记录待核对；重试只恢复原记录，不重复上传。")
            pending.update(uploadSummary=summary, uploadCounterPending=True)
            if destination is not None and (floor or ledger_required):
                pending["uploadCounterBase"] = {"destination": destination, "count": floor, "ledgerExisted": ledger_required or floor > 1}
                anchor = next((anchor for anchor in anchors if anchor["count"] == floor), None)
                if anchor:
                    pending["uploadCounterBase"]["commitSha"] = anchor["commitSha"]
            try:
                _atomic(pending_path, pending)
            except (OSError, RepositoryPublishError):
                pass  # The earlier durable delivered receipt is still kept.
            item["uploadSummary"] = summary
            item["message"] += " 上传序号记录待核对。"
            item["diagnostic"] = _make_diagnostic("receipt_unverified", summary["reason"])
            return False

    def _repo(self, repo):
        if not repo["path"] or not Path(repo["path"]).exists():
            raise RepositoryPublishError("仓库目录不存在，请检查设置。", code="repo_missing")
        root = _safe_path(repo["path"])
        top = _safe_path(self._text(root, "rev-parse", "--show-toplevel"))
        if os.path.normcase(str(root)) != os.path.normcase(str(top)):
            raise RepositoryPublishError("请选择仓库根目录，不能使用其子目录。", code="repo_root")
        gitdir = _safe_path(self._text(root, "rev-parse", "--absolute-git-dir"))
        common_text = self._text(root, "rev-parse", "--git-common-dir")
        common = _safe_path(Path(common_text) if Path(common_text).is_absolute() else root / common_text)
        branch = self._text(root, "symbolic-ref", "--short", "HEAD")
        if not repo["branch"] or branch != repo["branch"]:
            raise RepositoryPublishError("当前分支与设置不符，请自行切换或修正设置。", code="branch_mismatch")
        self._git(root, "check-ref-format", "refs/heads/" + branch)
        fetch = self._text(root, "remote", "get-url", "--all", repo["remote"]).splitlines()
        push = self._text(root, "remote", "get-url", "--push", "--all", repo["remote"]).splitlines()
        if len(fetch) != 1 or len(push) != 1:
            raise RepositoryPublishError("远端必须只有一个读取地址和一个推送地址。", code="remote_config")
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
            raise RepositoryPublishError("读取、推送和配置地址必须指向同一个 GitHub 仓库。", code="remote_ownership")
        identity = {"root": str(root), "gitdir": str(gitdir), "common": str(common), "branch": branch,
                    "remote": repo["remote"], "fetchUrl": fetch[0], "pushUrl": push[0], "repository": slugs[0]}
        return root, gitdir, common, identity

    @staticmethod
    def _github(url):
        match = re.fullmatch(r"(?:https://github\.com/|ssh://git@github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?", url)
        return match.group(1).lower() if match else ""

    def activity_status(self, repo_id):
        """Explicit scoped inspection only; no sync, stage, commit or remote I/O."""
        settings = self._settings()
        repo = next((item for item in settings["repositories"] if item["id"] == repo_id), None)
        if repo is None:
            raise RepositoryPublishError("此仓库配置已改变，请重新读取列表。", code="destination_changed")
        root = _safe_path(repo["path"])
        diagnostic = None
        notice = None
        policy = "allow_saved_snapshot" if settings["naming"].get("allowActiveWork", True) is True else "strict"
        try:
            if not root.is_dir():
                raise RepositoryPublishError("本地仓库目录不存在，请核对路径。", code="repo_missing")
            error = self._activity_error(root)
            if error:
                diagnostic = error.diagnostic
                if diagnostic.get("kind") == "codex_activity":
                    notice = dict(diagnostic)
        except RepositoryPublishError as error:
            diagnostic = error.diagnostic
        clear = diagnostic is None
        permitted = clear or policy == "allow_saved_snapshot" and notice is not None
        return {"repoId": repo_id, "sourceIdentity": catalog_source_identity(repo, settings["naming"]),
                "activityClear": clear, "publicationAllowed": permitted, "activityPolicy": policy,
                "activityNotice": notice, "diagnostic": None if permitted else diagnostic, "checkedAt": _now()}

    def _activity_error(self, root):
        """Separate trusted Codex notices from Git/shared-operation blockers."""
        reason = self._busy_check(root) if self._busy_check else None
        if reason:
            if isinstance(reason, dict):
                code = reason.get("code")
                code = code if code in {"activity_active", "activity_scope_unknown", "activity_unconfirmed", "git_lock"} else "activity_unconfirmed"
                summary = reason.get("summary")
                summary = summary[:1000] if isinstance(summary, str) and summary else "无法确认本仓库的编辑活动，请查看具体原因后重试。"
                error = RepositoryPublishError(summary, code=code)
                if reason.get("kind") == "codex_activity" and reason.get("code") in {"activity_active", "activity_scope_unknown", "activity_unconfirmed"}:
                    error.diagnostic["kind"] = "codex_activity"
                elif reason.get("kind") == "git_operation" or code == "git_lock":
                    error.diagnostic["kind"] = "git_operation"
                blockers = _activity_blockers(reason.get("blockers"))
                if blockers:
                    error.diagnostic["blockers"] = blockers
                return error
            return RepositoryPublishError(str(reason)[:1000], code="activity_unconfirmed")
        return None

    @contextmanager
    def _activity_policy(self, naming, item=None):
        """Freeze this invocation's policy and release its thread lease on all exits."""
        if not hasattr(self, "_lease"):
            self._lease = threading.local()
        missing = object()
        previous = {key: getattr(self._lease, key, missing) for key in ("allow_active_work", "activity_item")}
        self._lease.allow_active_work = naming.get("allowActiveWork", True) is True
        self._lease.activity_item = item
        if item is not None:
            item.update(activityPolicy="allow_saved_snapshot" if self._lease.allow_active_work else "strict", activityNotice=None)
        try:
            yield
        finally:
            for key, value in previous.items():
                if value is missing:
                    delattr(self._lease, key)
                else:
                    setattr(self._lease, key, value)

    def _busy_reason(self, root):
        error = self._activity_error(root)
        if error is None:
            return None
        lease = getattr(self, "_lease", None)
        if error.diagnostic.get("kind") == "codex_activity":
            item = getattr(lease, "activity_item", None)
            if item is not None:
                item["activityNotice"] = dict(error.diagnostic)
            if getattr(lease, "allow_active_work", False) is True:
                return dict(error.diagnostic)
        raise error

    def _sync_contract(self, repo):
        if repo.get("syncError"):
            raise RepositoryPublishError("已保存同步清单无效，请修正并验证同步映射：" + repo["syncError"], code="sync_config")
        manifest = repo.get("syncManifest")
        if manifest:
            root = _safe_path(repo["path"])
            source = _safe_path(root / manifest["path"])
            if not source.is_relative_to(root):
                raise RepositoryPublishError("同步清单来源超出仓库。", code="sync_config")
            try:
                actual = _stable(source)
            except OSError as exc:
                raise RepositoryPublishError("导入的同步清单已缺失，请重新核对配置。", code="sync_missing") from exc
            if actual != {"bytes": manifest["bytes"], "sha256": manifest["sha256"]}:
                raise RepositoryPublishError("导入的同步清单已变化，请重新保存并核对同步配置。", code="sync_config")

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
                    raise RepositoryPublishError("仓库正在合并、变基或处理历史，请先完成该操作。", code="git_history_operation")
            locks = [base / "HEAD.lock", base / "config.lock", base / "packed-refs.lock"]
            locks.extend((base / "refs").rglob("*.lock") if (base / "refs").exists() else [])
            if any(p.exists() for p in locks) or not own_index_lock and (gitdir / "index.lock").exists():
                raise RepositoryPublishError("Git 正在使用锁，请等待；不会移除其他操作的锁。", code="git_lock")
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
                raise RepositoryPublishError("保留已有暂存选择，请先提交或取消该选择。", code="merge_conflict" if xy in {"DD", "AU", "UD", "UA", "DU", "AA", "UU"} else "staged_selection")
            path = record[3:].decode("utf-8", "surrogateescape")
            if _excluded(path, repo["exclude"]):
                continue
            location = _safe_path(root / _relative(path))
            proof = _stable(location) if location.exists() else {"deleted": True}
            changed.append({"path": path, "status": xy, **proof})
        if self._git(root, "ls-files", "--unmerged", "-z"):
            raise RepositoryPublishError("仓库存在未解决冲突，请先处理。", code="merge_conflict")
        if self._text(root, "rev-parse", "HEAD") != head or (_sha(index_path.read_bytes()) if index_path.exists() else None) != index_sha:
            raise RepositoryPublishError("仓库在检查期间发生变化，请稍后重试。", code="worktree_changed")
        result = {"head": head, "indexSha": index_sha, "configSha": config_sha, "identity": identity,
                  "files": sorted(changed, key=lambda item: item["path"])}
        result["fingerprint"] = _json_sha(result)
        return result

    def _versions(self, root, sources, files, *, required_ids=(), head="HEAD"):
        result = []
        # Two root manifests describe one application. The application manifest
        # is authoritative; package.json is only its fallback.
        if any(s["path"] == "app-manifest.json" for s in sources):
            sources = [s for s in sources if s["path"] != "package.json"]
        shared_paths = {source["path"] for source in sources if sum(other["path"] == source["path"] for other in sources) > 1}
        if files:
            selected = self._affected_sources(sources, files) | set(required_ids)
            sources = [source for source in sources if version_source_id(source) in selected]
        for source in sources:
            item = {"sourceId": version_source_id(source), "name": source["name"] or Path(source["path"]).stem,
                    "path": source["path"], "version": "", "scope": source["scope"], "kind": source["kind"]}
            try:
                if source["kind"] == "git_commit":
                    item.update(self._git_version_reader(root)(source))
                    result.append(item)
                    continue
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
                if (source["path"] in shared_paths and files and item["sourceId"] not in required_ids
                        and not any(file["path"] != source["path"] and _matches(file["path"], source["scope"]) for file in files)):
                    try:
                        previous = read_current_version(self._git(root, "show", head + ":" + source["path"]), source)
                        if previous == item["version"]:
                            continue  # An unchanged key is not an independently changed component.
                    except (VersionPlanError, _GitFailure, ValueError, UnicodeError):
                        pass
            except (OSError, ValueError, KeyError, TypeError, SyntaxError, RepositoryPublishError, _GitFailure, ET.ParseError):
                item["message"] = "版本来源缺失、变化或无法唯一读取，使用进度标题。"
            result.append(item)
        return result

    def _message(self, repo, snapshot, naming, *, version_plans=None, automatic_source_ids=()):
        root = Path(snapshot["identity"]["root"])
        sources = repo["versionSources"]
        if not sources:
            first = next((p for p in ("app-manifest.json", "package.json") if (root / p).is_file()), None)
            sources = [{"path": first, "kind": "json", "key": "version", "name": root.name, "scope": ""}] if first else []
        if version_plans is None:
            version_plans = []
            if repo.get("versionPlans"):
                try:
                    _, version_plans = prepare_version_updates(root, self._version_sources(repo, root), repo["versionPlans"],
                                                              self._version_reader(root), self._git_version_reader(root),
                                                              self._console_resource_reader(root), self._application_reader(repo, root, snapshot["identity"]))
                except VersionPlanError as exc:
                    raise RepositoryPublishError(str(exc)) from exc
        planned = {plan["sourceId"]: plan for plan in version_plans}
        versions = self._versions(root, sources, snapshot["files"], required_ids=planned, head=snapshot["head"])
        valid = [v for v in versions if v["version"]]
        for item in versions:
            if item["version"] and snapshot["files"] and item["kind"] != "git_commit":
                source = next(source for source in sources if version_source_id(source) == item["sourceId"])
                try:
                    previous = read_current_version(self._git(root, "show", snapshot["head"] + ":" + source["path"]), source)
                    if previous != item["version"]:
                        item["transition"] = {"kind": "working", "fromVersion": previous, "toVersion": item["version"]}
                except (VersionPlanError, _GitFailure, ValueError, UnicodeError):
                    pass
            plan = planned.get(item["sourceId"])
            if plan:
                item["transition"] = {"kind": "auto" if item["sourceId"] in automatic_source_ids else "planned",
                                      "fromVersion": plan["currentVersion"], "toVersion": plan["targetVersion"]}
                item["plannedVersion"] = plan["targetVersion"]
        def label(item, include_name=False):
            transition = item.get("transition")
            value = transition["fromVersion"] + " → " + transition["toVersion"] if transition else item["version"]
            return (item["name"] + " " if include_name else "") + value
        title = naming["fallbackTitle"].replace("{datetime}", datetime.now().strftime("%Y-%m-%d %H:%M"))
        if naming["preset"] == "version" and len(versions) == 1 and len(valid) == 1:
            title = label(valid[0])
        elif naming["preset"] == "module_version" and valid and len(valid) == len(versions):
            title = " / ".join(label(item, True) for item in valid)
        if planned and len(versions) == 1 and valid and valid[0]["kind"] == "git_commit":
            # A Git-only authority must produce the same strict subject shape
            # it can subsequently read, irrespective of a global module preset.
            title = label(valid[0])
        title = " ".join(title.replace("\0", "").splitlines()).strip()[:240] or "更新进度"
        paragraphs = [naming[k].strip() for k in ("subtitle", "notes") if naming[k].strip()]
        if versions:
            paragraphs.append("版本来源：\n" + "\n".join("- " + v["name"] + ": " + (v["version"] or "未确认") + " (" + v["path"] + ")" for v in versions))
        if any(item.get("transition") for item in versions):
            paragraphs.append("版本核对与本次计划：\n" + "\n".join("- " + label(item, True) +
                              ("（已手动改变，保留当前版本）" if item["transition"]["kind"] == "working" else
                               "（有改动自动升版）" if item["transition"]["kind"] == "auto" else "（显式计划）")
                              for item in versions if item.get("transition")))
        elif valid and snapshot["files"]:
            changes = []
            for item in valid:
                source = next(source for source in sources if version_source_id(source) == item["sourceId"])
                try:
                    previous = item["version"] if source["kind"] == "git_commit" else read_current_version(
                        self._git(root, "show", snapshot["head"] + ":" + source["path"]), source)
                    changes.append("- " + item["name"] + ": " + (previous + " → " + item["version"] if previous != item["version"] else "版本未变 " + item["version"]))
                except (VersionPlanError, _GitFailure, ValueError, UnicodeError):
                    pass
            if changes:
                paragraphs.append("版本核对：\n" + "\n".join(changes))
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
        with self._activity_policy(settings["naming"]):
            return self._preview(repo_id, settings)

    def _preview(self, repo_id, settings):
        selected = [r for r in settings["repositories"] if repo_id is None or r["id"] == repo_id]
        if repo_id is not None and not selected:
            raise RepositoryPublishError("仓库编号不存在。")
        results = []
        commons = {}
        for repo in selected:
            item = {"repoId": repo["id"], "name": Path(repo["path"]).name or repo["id"], "title": "", "body": "", "versions": [], "files": [],
                    "uploadSummary": self._upload_summary(repo),
                    "components": [], "versionTransitions": [], "hasChanges": None, "changeState": "unknown", "planWillApply": None, "action": "unknown",
                    "diagnostic": None, "versionState": "unknown", "worktreeChanged": None, "outgoingCommits": None,
                    "syncChanged": None, "syncState": "unknown", "syncReason": "", "syncDifferences": []}
            self._lease.activity_item = item
            item.update(activityPolicy="allow_saved_snapshot" if self._lease.allow_active_work else "strict", activityNotice=None)
            try:
                self._sync_contract(repo)
                context = self._repo(repo)
                key = os.path.normcase(str(context[2]))
                if key in commons:
                    raise RepositoryPublishError("重复仓库或共享 Git 目录，请只配置一个入口。", code="duplicate_repository")
                commons[key] = repo["id"]
                snapshot = self._snapshot(repo, context)
                components = self._version_details(repo, context)
                item["components"] = components
                known = [bool(component.get("currentVersion")) for component in components]
                item["versionState"] = "missing" if not known else "known" if all(known) else "partial" if any(known) else "unknown"
                item.update(self._local_changes(repo, context))
                if item["headSha"] != snapshot["head"] or any(component["repositoryHeadSha"] != snapshot["head"] for component in components):
                    raise RepositoryPublishError("预览期间 HEAD 已变化，请重新读取。", code="worktree_changed")
                effective, automatic, blocked = self._planned_versions(repo, context, components, snapshot["files"], settings["naming"],
                                                                      sync_pending=bool(repo["syncFiles"]))
                item["planWillApply"] = bool(effective) and bool(snapshot["files"])
                item["action"] = "sync_pending" if repo["syncFiles"] else "commit" if snapshot["files"] else "push_only" if item["outgoingCommits"] else "noop" if item["outgoingCommits"] == 0 else "unknown"
                if item["action"] == "sync_pending":
                    item["planWillApply"] = None
                if blocked:
                    item["planWillApply"] = False
                selected_plans = effective if item["planWillApply"] else []
                item["title"], item["body"], item["versions"] = self._message(
                    repo, snapshot, settings["naming"], version_plans=selected_plans, automatic_source_ids=automatic)
                if item["action"] == "push_only":
                    item["title"] = self._text(context[0], "show", "-s", "--format=%s", snapshot["head"])
                    item["body"] = self._text(context[0], "show", "-s", "--format=%b", snapshot["head"])
                item["versionTransitions"] = [{"sourceId": component["sourceId"], "name": component["name"], "path": component["path"], **component["transition"]}
                                             for component in components if component.get("transition") and
                                             (component["transition"]["kind"] not in {"planned", "auto"} or item["planWillApply"] is True)]
                item.update(files=snapshot["files"], fingerprint=snapshot["fingerprint"], status="ready", message="预览已保存文件；提交时会重新核对。")
                if blocked:
                    item.update(status="deferred", message="自动升版暂缓本仓库：" + "；".join(blocked),
                                diagnostic=_make_diagnostic("version_plan_blocked", "自动升版暂缓本仓库：" + "；".join(blocked)))
                elif item["action"] == "sync_pending":
                    item["message"] = "先同步已保存工作文件，再确定实际改动及本次版本。"
                elif item["action"] == "push_only" and repo.get("versionPlans"):
                    item["message"] = "计划保留，仅推已有提交；保留原说明和版本。"
                if not repo["enabled"]:
                    item.update(status="disabled", message="该仓库未启用，请先启用再提交。")
            except (RepositoryPublishError, _GitFailure, OSError) as exc:
                item.update(status="deferred", message=self._error(exc), diagnostic=self._diagnostic(exc))
            self._catalog_diagnostic(item)
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
                                         "message": "等待处理", "commitSha": "", "title": "", "body": "", "logs": [],
                                         "uploadSummary": self._upload_summary(r)} for r in selected]}
            for item in receipt["repositories"]:
                item.update(activityPolicy="allow_saved_snapshot" if settings["naming"].get("allowActiveWork", True) is True else "strict",
                            activityNotice=None)
                item["progress"] = self._item_progress(item)
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
                    receipt.update(status="attention", phase="dispatch_failed", message="后台暂时无法启动，请稍后重试；尚未提交或推送。",
                                   diagnostic=_make_diagnostic("background_unavailable", "后台暂时无法启动，请稍后重试；尚未提交或推送。"))
                    for item in receipt["repositories"]:
                        item.update(status="deferred", phase="dispatch_failed", message=receipt["message"], diagnostic=receipt["diagnostic"])
                    self._save(receipt)
            finally:
                self._starting = False
            return json.loads(json.dumps(receipt))

    def _save(self, receipt):
        receipt["updatedAt"] = _now()
        for item in receipt.get("repositories", []):
            item["progress"] = self._item_progress(item)
        receipt["progress"] = self._operation_progress(receipt)
        _atomic(self._ops / (receipt["requestId"] + ".json"), receipt)

    def _phase(self, receipt, item, phase, message):
        item.update(status="working", phase=phase, message=message, diagnostic=None)
        item.setdefault("startedAt", _now())
        item["progress"] = {"state": "indeterminate", "phase": phase, "scope": "phase", "unit": None,
                            "current": None, "total": None, "percent": None, "source": "receipt", "step": None,
                            "startedAt": item["startedAt"], "phaseStartedAt": _now(), "updatedAt": _now()}
        item["logs"].append({"at": _now(), "phase": phase, "message": message})
        self._save(receipt)

    def _transfer_progress(self, receipt, item):
        """One worker owns mutation; pipe readers only enqueue numeric events."""
        last_saved = 0.
        pending = None

        def update(value):
            nonlocal last_saved, pending
            if item.get("status") != "working" or item.get("phase") != "push":
                return
            # Byte telemetry is finer than the LFS console object summary.
            previous = item.get("progress", {})
            if (previous.get("scope") == "file" and value.get("source") == "git-lfs"
                    and value.get("scope") != "file"):
                return
            pending = {**value, "phase": "push", "startedAt": item.get("startedAt"),
                       "phaseStartedAt": previous.get("phaseStartedAt", _now()), "updatedAt": _now()}
            item["progress"] = pending
            now = time.monotonic()
            # The newest event stays in memory; durable transfer snapshots are
            # throttled to four per second. Phase/terminal writes are separate.
            if now - last_saved >= .25:
                last_saved = now
                try:
                    self._save(receipt)
                except (OSError, RepositoryPublishError):
                    pass  # Telemetry failure never retries or alters a push.

        return update

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
                                raise RepositoryPublishError("重复仓库或共享 Git 目录，请只启用一个入口。", code="duplicate_repository")
                            self._run_repo(repo, settings["naming"], receipt, item)
                        except (RepositoryPublishError, _GitFailure, OSError) as exc:
                            item.update(status="deferred", message=self._error(exc), diagnostic=self._diagnostic(exc))
                        except Exception:
                            item.update(status="verification_required", message="操作中断，保留核对记录；重试会先检查原提交。", diagnostic=_make_diagnostic("operation_interrupted", "操作中断，保留核对记录；重试会先检查原提交。"))
                        try:
                            pending = _read(self._pending_path(repo["id"]))
                            if pending and pending.get("state") != "delivered":
                                item.update(commitSha=pending.get("commitSha", item["commitSha"]), title=pending["title"], body=pending["body"])
                        except RepositoryPublishError as exc:
                            item.update(status="verification_required", message=str(exc), diagnostic=self._diagnostic(exc))
                        item["logs"].append({"at": _now(), "phase": item["phase"], "message": item["message"]})
                        self._save(receipt)
                    states = {i["status"] for i in receipt["repositories"]}
                    receipt.update(status="success" if states <= {"success", "noop"} else "attention", phase="complete",
                                   message="所有仓库已完成。" if states <= {"success", "noop"} else "部分仓库需要处理，其他仓库已继续完成。")
                    self._save(receipt)
            except (RepositoryPublishError, OSError) as exc:
                receipt.update(status="attention", phase="deferred", message=self._error(exc), diagnostic=self._diagnostic(exc))
                for item in receipt["repositories"]:
                    if item["status"] in {"queued", "working"}:
                        item.update(status="deferred", message=receipt["message"], diagnostic=receipt["diagnostic"])
                self._save(receipt)

    @staticmethod
    def _diagnostic(exc):
        if isinstance(exc, RepositoryPublishError):
            return dict(exc.diagnostic)
        code = _GIT_DIAGNOSTIC_CODES.get(exc.code, "manual_check") if isinstance(exc, _GitFailure) else "manual_check"
        if isinstance(exc, _GitFailure) and exc.code == "git_failed":
            code = "git_remote_failed" if exc.operation in {"ls-remote", "fetch"} else "manual_check"
        result = _make_diagnostic(code, RepositoryPublishService._error(exc))
        if isinstance(exc, _GitFailure):
            if exc.operation:
                result["operationKind"] = exc.operation
            if isinstance(exc.returncode, int) and not isinstance(exc.returncode, bool):
                result["exitCode"] = exc.returncode
            result["errorKind"] = exc.error_kind
        return result

    @staticmethod
    def _error(exc):
        if isinstance(exc, RepositoryPublishError):
            return str(exc)
        if isinstance(exc, _GitFailure):
            message = {"authentication": "认证失败，请检查已配置的 Git 凭证后重试原提交。", "permissions": "没有推送权限，请检查仓库权限。",
                    "rules": "远端规则或 Git hook 拒绝操作，请处理规则后重试。", "lfs": "Git LFS 处理失败，请检查 LFS 安装、对象或认证。",
                    "remote_config": "配置的远端名称不存在，请核对该仓库的远端名称后重新核对。",
                    "remote_changed": "远端发生变化，请自行整合；不会强制推送。", "timeout": "Git 操作超时，保留原提交核对状态。",
                    "missing_git": "未找到 Git。", "git_unavailable": "Git 进程无法启动，请核对本机 Git。",
                    "unsupported": "Git 拒绝了本次命令选项，请核对实际 Git 版本。",
                    "network": {"resolve_host": "Git 无法解析远端或代理域名。", "connect_failed": "Git 无法连接远端或代理。",
                                "connection_reset": "Git 连接在传输期间被重置。", "tls_failed": "Git 的 TLS 或证书核验失败。",
                                "server_unavailable": "Git 远端服务返回服务器错误。"}.get(exc.error_kind, "Git 网络传输失败。")}.get(exc.code)
            if message is None:
                message = ({"ls-remote": "读取 Git 远端分支失败。", "fetch": "获取 Git 远端历史失败。",
                            "push": "Git 推送失败，保留原提交以核验或重试。", "commit": "Git 本地提交失败。"}
                           .get(exc.operation, "Git 操作失败。"))
                message += "文件、暂存选择和已有提交保留。"
            metadata = []
            if exc.operation:
                metadata.append("git " + exc.operation)
            if isinstance(exc.returncode, int) and not isinstance(exc.returncode, bool):
                metadata.append("退出码 " + str(exc.returncode))
            return message + ("（" + " · ".join(metadata) + "）" if metadata else "")
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
                    raise RepositoryPublishError("同步来源正在写入，请保存后重试。", code="sync_writing")
                target_before = _stable(target) if target.exists() else None
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name("." + target.name + ".console-sync-" + uuid.uuid4().hex)
                try:
                    with _read_lease(source), source.open("rb") as src, temporary.open("xb") as dst:
                        shutil.copyfileobj(src, dst, 1024 * 1024)
                        dst.flush()
                        os.fsync(dst.fileno())
                    if _stable(source) != proof or _stable(temporary) != proof:
                        raise RepositoryPublishError("同步来源在复制期间发生变化。", code="sync_changed")
                    if (_stable(target) if target.exists() else None) != target_before:
                        raise RepositoryPublishError("同步目标被另一处修改，保留该修改。", code="sync_changed")
                    self._busy_reason(root)
                    if source != target and target_before != proof:
                        os.replace(temporary, target)
                    records.append({"source": str(source), "target": mapping["target"], **proof, "changed": target_before != proof})
                finally:
                    temporary.unlink(missing_ok=True)
            except FileNotFoundError as exc:
                raise RepositoryPublishError("同步来源缺失，请先保存来源文件；本仓库延期。", code="sync_missing") from exc
        self._verify_sync(repo, context, records)
        return records

    def _sync_preflight(self, repo, root):
        records, targets = [], set()
        for mapping in repo["syncFiles"]:
            self._catalog_remaining()
            source = _safe_path(mapping["source"])
            target = _safe_path(root / mapping["target"])
            if self._test_mode and not source.is_relative_to(self._sandbox):
                raise RepositoryPublishError("测试同步来源超出隔离目录。")
            key = os.path.normcase(str(target))
            if source == target or key in targets or not target.is_relative_to(root):
                raise RepositoryPublishError("同步目标重复、与来源相同或超出仓库。", code="sync_config")
            if _excluded(mapping["target"], repo["exclude"]):
                raise RepositoryPublishError("同步目标属于排除或私人范围。", code="sync_config")
            targets.add(key)
            try:
                records.append((mapping, source, target, self._catalog_stable(source)))
            except RepositoryPublishError as exc:
                if exc.code == "worktree_changed":
                    raise RepositoryPublishError(str(exc), code="sync_writing") from exc
                raise
            except FileNotFoundError as exc:
                raise RepositoryPublishError("同步来源缺失，请先保存来源文件；本仓库延期。", code="sync_missing") from exc
        time.sleep(.02 if records else 0)
        if any(self._catalog_stable(source) != proof for _, source, _, proof in records):
            raise RepositoryPublishError("同步来源正在写入，请保存后重试。", code="sync_writing")
        return records

    def _verify_sync(self, repo, context, records):
        self._sync_contract(repo)
        for record in records:
            expected = {"bytes": record["bytes"], "sha256": record["sha256"]}
            try:
                if _stable(Path(record["source"])) != expected or _stable(context[0] / record["target"]) != expected:
                    raise RepositoryPublishError("同步来源或目标在处理期间变化，请保存后重试；不会发布混合快照。", code="sync_changed")
            except FileNotFoundError as exc:
                raise RepositoryPublishError("同步来源或目标在处理期间缺失，本仓库延期。", code="sync_missing") from exc

    def _remote(self, repo, root):
        alias, config = self._transport(repo, root)
        output = self._text(root, "ls-remote", "--heads", alias, "refs/heads/" + repo["branch"], timeout=35, config=config)
        self._transport_identity(repo, root)
        if not output:
            return None
        rows = output.splitlines()
        if len(rows) != 1 or len(rows[0].split()) != 2 or rows[0].split()[1] != "refs/heads/" + repo["branch"] or not _SHA.fullmatch(rows[0].split()[0]):
            raise RepositoryPublishError("远端分支回执无效。", code="receipt_unverified")
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
            raise RepositoryPublishError("远端在核对期间发生变化，请稍后重试。", code="remote_changed")
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
                raise RepositoryPublishError("远端启用了镜像推送，不适用于单分支提交。", code="remote_config")
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

    def _continue_version_intent(self, repo, context, pending, pending_path, receipt, item):
        self._phase(receipt, item, "version", "核对并继续原一次性版本计划；不会重复递增。")
        snapshot = self._apply_version_intent(repo, context, pending, pending_path)
        if not snapshot["files"]:
            raise RepositoryPublishError("原版本标题计划尚无实际可提交变化；保留计划，不创建空提交。")
        self._commit(repo, context, snapshot, pending, pending_path)
        self._consume_version_plans(repo, pending)
        item.update(commitSha=pending["commitSha"], title=pending["title"], body=pending["body"], versions=pending["versions"])
        self._push(repo, context, pending, pending_path, receipt, item)

    def _run_repo(self, repo, naming, receipt, item):
        with self._activity_policy(naming, item):
            return self._run_repo_frozen(repo, naming, receipt, item)

    def _run_repo_frozen(self, repo, naming, receipt, item):
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
            if pending and pending.get("state") == "delivered":
                # Repair a previous ledger-only failure before replacing its
                # sole durable delivery receipt with another submission.
                item.update(commitSha=pending.get("commitSha", ""), title=pending.get("title", ""), body=pending.get("body", ""),
                            status="success", phase="complete", message="原提交已确认送达，正在保存上传序号。")
                if not self._delivery_evidence(pending, self._upload_destination(pending)):
                    item.update(status="verification_required", phase="verify", message="原上传确认记录不完整，保留原提交和回执，请先核对。", diagnostic=_make_diagnostic("receipt_unverified", "原上传确认记录不完整，保留原提交和回执，请先核对。"))
                    return
                item.update(deliveryVerifiedAt=pending["verifiedAt"], verifiedRemote=pending["verifiedRemote"])
                recovering_counter = pending.get("uploadCounterPending") is True or not self._delivery_acknowledged(pending)
                if not self._record_delivery(repo, pending, pending_path, item):
                    return
                if recovering_counter:
                    pending["deliveryRecoveryRequestId"] = receipt["requestId"]
                    _atomic(pending_path, pending)
                    item["message"] = "原提交已确认送达，上传序号已恢复；新修改保留，未再次提交或推送。"
                    return
                item.update(status="working", phase="check", message="核对仓库、分支和活动任务。")
            if (pending and (pending.get("versionUpdates") or pending.get("versionPlans")) and not pending.get("commitSha")
                    and pending.get("state") in {"version_prepared", "version_applying", "prepared", "cancelled_before_commit"}):
                if pending["identity"] != identity or pending["repositorySettingsSha"] != _repo_settings_sha(repo):
                    raise RepositoryPublishError("原版本计划的仓库或配置变化，请恢复后重试；不会重新升版。", code="destination_changed")
                if pending.get("transportOptionsSha", transport["optionsSha"]) != transport["optionsSha"]:
                    raise RepositoryPublishError("原版本计划的 LFS 或传输配置已变化，请恢复后重试。", code="destination_changed")
                self._continue_version_intent(repo, context, pending, pending_path, receipt, item)
                return
            if pending and pending.get("state") not in {"delivered", "cancelled_before_commit"}:
                if pending["identity"] != identity or pending["repositorySettingsSha"] != _repo_settings_sha(repo):
                    raise RepositoryPublishError("原提交的仓库或配置已变化，请恢复原配置后重试；不会推送到新目标。", code="destination_changed")
                if pending.get("transportOptionsSha", transport["optionsSha"]) != transport["optionsSha"]:
                    raise RepositoryPublishError("原提交的 LFS 或传输配置已变化，请恢复后重试。", code="destination_changed")
                self._phase(receipt, item, "verify", "先核对并继续上次原提交。")
                pending = self._recover_commit(repo, context, pending, pending_path)
                if pending.get("state") == "cancelled_before_commit" and (pending.get("versionUpdates") or pending.get("versionPlans")):
                    self._continue_version_intent(repo, context, pending, pending_path, receipt, item)
                    return
                if pending.get("state") != "cancelled_before_commit":
                    item.update(commitSha=pending.get("commitSha", ""), title=pending["title"], body=pending["body"])
                    if not pending.get("commitSha"):
                        raise RepositoryPublishError("上次提交结果尚未确认，请核对保留的记录和 Git 锁。", code="receipt_unverified")
                    self._consume_version_plans(repo, pending)
                    self._push(repo, context, pending, pending_path, receipt, item)
                    return
            self._blockers(root, gitdir, common)
            # Staged work is checked before any explicit source synchronization.
            self._snapshot(repo, context)
            self._phase(receipt, item, "sync", "核对并同步明确指定的已保存文件。")
            item["syncFiles"] = self._sync(repo, context)
            self._save(receipt)
            snapshot = self._snapshot(repo, context)
            components = self._version_details(repo, context)
            if any(component["repositoryHeadSha"] != snapshot["head"] for component in components):
                raise RepositoryPublishError("同步后读取版本期间 HEAD 已变化，请重新核对。", code="worktree_changed")
            effective, automatic, _ = self._planned_versions(repo, context, components, snapshot["files"], naming, strict=True)
            apply_plans = bool(effective) and bool(snapshot["files"])
            title, body, versions = self._message(repo, snapshot, naming, version_plans=effective if apply_plans else [],
                                                  automatic_source_ids=automatic)
            item.update(title=title, body=body, versions=versions)
            self._phase(receipt, item, "remote", "核对远端分支及待推送历史。")
            remote = self._remote(repo, root)
            self._fetch(repo, context, remote)
            self._verify_sync(repo, context, item["syncFiles"])
            if remote and not self._ancestor(root, remote, snapshot["head"]):
                raise RepositoryPublishError("远端领先或分叉，请先自行整合；本仓库延期。", code="remote_ahead")
            self._outgoing_safe(root, remote, snapshot["head"], repo)
            if not snapshot["files"] and remote == snapshot["head"] and not apply_plans:
                item.update(status="noop", phase="complete", message="没有需要提交或推送的文件；一次性标题计划保留。" if repo.get("versionPlans") else "没有需要提交或推送的文件。")
                return
            pending = {"state": "prepared", "requestId": receipt["requestId"], "repoId": repo["id"], "identity": identity,
                       "uploadBinding": self._upload_binding(repo),
                       "repositorySettingsSha": _repo_settings_sha(repo), "parentSha": snapshot["head"], "snapshot": snapshot,
                       "title": title, "body": body, "createdAt": _now(), "commitSha": "", "indexReconciled": not snapshot["files"]}
            _, previous_uploads = self._upload_ledger(self._upload_destination(repo))
            pending["uploadCounterBase"] = {"destination": self._upload_destination(repo),
                                            "count": len(previous_uploads["events"]) if previous_uploads else 0,
                                            "ledgerExisted": previous_uploads is not None,
                                            "commitSha": previous_uploads["events"][-1]["commitSha"] if previous_uploads and previous_uploads["events"] else ""}
            pending["transportOptionsSha"] = transport["optionsSha"]
            pending["syncProofs"] = item["syncFiles"]
            if apply_plans:
                updates, plans = self._version_updates(repo, context, effective)
                pending.update(state="version_prepared", versionUpdates=updates, versionPlans=plans,
                               versionPlansSha=_json_sha(repo.get("versionPlans", [])), versionBaseSnapshot=snapshot, naming=dict(naming),
                               automaticSourceIds=automatic,
                               versionReadEvidence=[entry for component in components if component["sourceId"] in {plan["sourceId"] for plan in plans}
                                                    for entry in component.get("consoleResourceEvidence", [])])
                _atomic(pending_path, pending)
                self._phase(receipt, item, "version", "实际准备已确认的一次性版本文件，再生成真实版本说明。")
                snapshot = self._apply_version_intent(repo, context, pending, pending_path)
                title, body, versions = pending["title"], pending["body"], pending["versions"]
                item.update(title=title, body=body, versions=versions)
            if snapshot["files"]:
                self._phase(receipt, item, "commit", "暂存已核对文件并执行正常 Git 提交及 hooks。")
                self._commit(repo, context, snapshot, pending, pending_path)
            else:
                pending.update(commitSha=snapshot["head"], state="committed")
                pending["title"] = self._text(root, "show", "-s", "--format=%s", snapshot["head"])
                pending["body"] = self._text(root, "show", "-s", "--format=%b", snapshot["head"])
                _atomic(pending_path, pending)
            self._consume_version_plans(repo, pending)
            item.update(commitSha=pending["commitSha"], title=pending["title"], body=pending["body"])
            self._push(repo, context, pending, pending_path, receipt, item)

    def _commit(self, repo, context, snapshot, pending, pending_path):
        root, gitdir, common, identity = context
        self._busy_reason(root)
        self._verify_sync(repo, context, pending.get("syncProofs", []))
        self._verify_version_evidence(root, pending)
        if self._repo(repo)[3] != identity or self._snapshot(repo, context)["fingerprint"] != snapshot["fingerprint"]:
            raise RepositoryPublishError("文件或仓库在提交前变化，请重新预览后重试。", code="worktree_changed")
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
                raise RepositoryPublishError("文件在暂存期间变化，保留工作文件；本仓库延期。", code="worktree_changed")
            self._busy_reason(root)
            self._verify_sync(repo, context, pending.get("syncProofs", []))
            self._verify_version_evidence(root, pending)
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
                        raise RepositoryPublishError("提交超时，保留提交记录和自有锁，需先核对后重试。", code="receipt_unverified")
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
            self._verify_version_evidence(root, pending)
            after = self._snapshot(repo, context)
            # Normalization by filters is permitted; a hook changing source bytes
            # is retained but postpones pushing the created commit.
            before_files = {f["path"]: {k: v for k, v in f.items() if k != "status"} for f in snapshot["files"]}
            unexpected = {f["path"] for f in after["files"]} - set(before_files)
            if unexpected:
                pending["heldReason"] = "Git hook 或另一处新增了工作变更，原提交已保留；请核对后重试原提交。"
                _atomic(pending_path, pending)
                raise RepositoryPublishError(pending["heldReason"], code="worktree_changed")
            for path, old in before_files.items():
                actual = {"path": path, **(_stable(root / path) if (root / path).exists() else {"deleted": True})}
                if actual != old:
                    pending["heldReason"] = "Git hook 或另一处改变了工作文件，原提交已保留；请核对后重试原提交。"
                    _atomic(pending_path, pending)
                    raise RepositoryPublishError(pending["heldReason"], code="worktree_changed")
            if after["configSha"] != snapshot["configSha"] or after["head"] != head:
                raise RepositoryPublishError("提交期间仓库配置或 HEAD 变化，已保留原提交。", code="worktree_changed")
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
            raise RepositoryPublishError("提交结果与记录不符，请核对 HEAD；不会重新提交或推送。", code="receipt_unverified")
        if pending.get("messageSha") and _sha(self._git(root, "stripspace", data=self._git(root, "show", "-s", "--format=%B", head)).strip()) != pending["messageSha"]:
            raise RepositoryPublishError("提交消息与记录不符，请核对 hook 或并发提交；不会重新提交或推送。", code="receipt_unverified")

    def _recover_commit(self, repo, context, pending, pending_path, allow_no_commit=False):
        root = context[0]
        if pending.get("commitSha"):
            if not self._ancestor(root, pending["commitSha"], self._text(root, "rev-parse", "HEAD")):
                raise RepositoryPublishError("原提交已不在当前历史中，请人工核对；不会重新提交。", code="receipt_unverified")
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
                    raise RepositoryPublishError("上次暂存仍有索引写入，请先核对；不会移除锁。", code="git_lock")
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
                raise RepositoryPublishError("上次提交未确认，保留自有记录和锁；请先核对 Git 操作是否结束。", code="receipt_unverified")
        if not pending.get("indexReconciled"):
            self._reconcile(context, pending, pending_path)
        return pending

    def _reconcile(self, context, pending, pending_path):
        root, gitdir = context[:2]
        index = gitdir / "index"
        current = _sha(index.read_bytes()) if index.exists() else None
        temporary = _safe_path(pending["temporaryIndex"])
        if not temporary.is_relative_to(self.state_dir) or not temporary.is_file():
            raise RepositoryPublishError("原提交的索引恢复文件缺失，请先核对。", code="receipt_unverified")
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
            raise RepositoryPublishError("已有新的暂存选择，原提交保留；不会覆盖索引。", code="staged_selection")
        if not lock.exists() or _sha(lock.read_bytes()) not in {pending.get("lockMarkerSha"), pending.get("reconciledIndexSha")}:
            raise RepositoryPublishError("Git 索引锁不属于此任务，原提交保留；不会移除该锁。", code="git_lock")
        pending["reconciledIndexSha"] = expected
        _atomic(pending_path, pending)
        with lock.open("wb") as stream:
            stream.write(temporary.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        if (_sha(index.read_bytes()) if index.exists() else None) != current:
            raise RepositoryPublishError("暂存选择在恢复期间变化，保留原提交与锁。", code="staged_selection")
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
            raise RepositoryPublishError("原提交目标已变化，请恢复配置后重试。", code="destination_changed")
        sha = pending["commitSha"]
        item["commitSha"] = sha
        self._phase(receipt, item, "verify", "核对原提交是否已送达。")
        try:
            remote = self._remote(repo, root)
            self._fetch(repo, context, remote)
        except _GitFailure as exc:
            pending.update(state="verification_required", pushError=exc.code)
            _atomic(pending_path, pending)
            item.update(status="verification_required", message=self._error(exc), diagnostic=self._diagnostic(exc))
            return
        if remote and self._ancestor(root, sha, remote):
            pending.update(state="delivered", verifiedAt=_now(), verifiedRemote=remote)
            _atomic(pending_path, pending)
            item.update(status="success", phase="complete", message="已核对原提交在远端，无需重复推送。",
                        deliveryVerifiedAt=pending["verifiedAt"], verifiedRemote=remote)
            self._record_delivery(repo, pending, pending_path, item)
            return
        if remote and not self._ancestor(root, remote, sha):
            raise RepositoryPublishError("远端领先或分叉，请自行整合；保留原提交。", code="remote_ahead")
        self._outgoing_safe(root, remote, sha, repo)
        self._busy_reason(root)
        if self._repo(repo)[3] != identity or self._text(root, "rev-parse", "HEAD") != pending["snapshot"]["head"] and not self._ancestor(root, sha, self._text(root, "rev-parse", "HEAD")):
            raise RepositoryPublishError("仓库历史或目标变化，请先核对原提交。", code="destination_changed")
        self._phase(receipt, item, "push", "推送原提交并核对远端回执。")
        pending.update(state="push_attempt", pushAttemptAt=_now(), remoteBeforePush=remote)
        _atomic(pending_path, pending)
        error = None
        try:
            alias, config = self._transport(repo, root)
            self._git(root, "push", "--progress", "--no-follow-tags", alias, sha + ":refs/heads/" + repo["branch"],
                      timeout=1800, config=config, progress=self._transfer_progress(receipt, item))
            self._transport_identity(repo, root)
        except _GitFailure as exc:
            error = exc
        except RepositoryPublishError:
            pending.update(state="verification_required", pushError="destination_changed")
            _atomic(pending_path, pending)
            item.update(status="verification_required", phase="verify", message="传输配置在处理期间变化，原提交和固定目标已保留；请恢复配置后核对。", diagnostic=_make_diagnostic("destination_changed", "传输配置在处理期间变化，原提交和固定目标已保留；请恢复配置后核对。"))
            return
        self._phase(receipt, item, "verify", "传输步骤结束，正在核对远端是否收到原提交。")
        try:
            after = self._remote(repo, root)
            self._fetch(repo, context, after)
            delivered = bool(after and self._ancestor(root, sha, after))
        except (_GitFailure, RepositoryPublishError):
            after, delivered = None, False
        if delivered:
            pending.update(state="delivered", verifiedAt=_now(), verifiedRemote=after)
            item.update(status="success", phase="complete", message="原提交已推送并核对成功。",
                        deliveryVerifiedAt=pending["verifiedAt"], verifiedRemote=after)
        elif error and error.code != "timeout" and after == remote:
            pending.update(state="push_failed", pushError=error.code)
            item.update(status="push_failed", phase="push", message=self._error(error), diagnostic=self._diagnostic(error))
        else:
            pending.update(state="verification_required", pushError=error.code if error else "verification")
            item.update(status="verification_required", phase="verify", message="推送结果尚未确认；重试会先核对远端并继续原提交。", diagnostic=_make_diagnostic("receipt_unverified", "推送结果尚未确认；重试会先核对远端并继续原提交。"))
        _atomic(pending_path, pending)
        if delivered:
            self._record_delivery(repo, pending, pending_path, item)
