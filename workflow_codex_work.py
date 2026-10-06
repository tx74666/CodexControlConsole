"""Console-owned Codex stdio turns; never adopts desktop threads or old jobs.

The caller durably reserves a new run and freezes its source before submit().
Its synchronous on_event must return True for send_intent and interrupt_intent.
No database, account file, periodic scanner or automatic retry lives here.
Only a real matching turn/completed notification supplies a terminal outcome;
the caller separately verifies workspace file evidence before claiming work.

Protocol: https://learn.chatgpt.com/docs/app-server
Provider: https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import stat
import subprocess
import threading
import time
import uuid

from workflow_service import WorkflowError


PROVIDER = "openai_chatgpt_plan"
PROVIDER_URL = "https://api.openai.com/v1"
PERMISSION_PROFILE = "console-work-scope"
MAX_TEXT = 128 * 1024
MAX_IMAGE = 8 * 1024 * 1024
MAX_IMAGES_TOTAL = 24 * 1024 * 1024
MAX_LINE = 2 * 1024 * 1024
MAX_STREAM = 32 * 1024 * 1024
MAX_INPUT = 48 * 1024 * 1024
MAX_ITEMS = 512
MAX_PROGRESS = 256 * 1024
ID = re.compile(r"[A-Za-z0-9_-]{1,190}\Z")
RUN_ID = re.compile(r"[a-f0-9]{32}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
PROFILE_EFFORT = {"fast": "low", "high": "high"}
IMAGE_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}
SAFE_ENV = {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "SYSTEMDRIVE"}
SPEC_KEYS = {"subscription", "requestedProfile", "workspaceRoot", "allowedRoot", "text", "images", "sourceSha256"}
BINDING_KEYS = {"provider", "connectionId", "catalogRevision", "modelSlug"}
PROTECTED_DIRECTORIES = (".codex", ".ssh", ".aws", ".azure", "work", "workflow-private",
                         "chatgpt-subscription", "attachments", "jobs", "siwc-probe")
PROTECTED_PATTERNS = ("**/auth.json", "**/.env", "**/.env.*", "**/*.pem", "**/*.key",
                      "**/*.pfx", "**/*.p12", "**/*.dpapi")


def _error(code, message="Work 尚未完成；底稿与已发生的修改保留，不会自动重跑。", status=409):
    return WorkflowError(message, status, code)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _plain(path, must_exist=True):
    path = Path(path)
    if not path.is_absolute():
        raise _error("codex_work_scope_invalid")
    for entry in (path, *path.parents):
        try:
            value = entry.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(value.st_mode) or getattr(value, "st_file_attributes", 0) & 0x400:
            raise _error("codex_work_reparse_scope")
    canonical = path.resolve()
    if must_exist and not canonical.is_dir():
        raise _error("codex_work_scope_missing")
    if canonical == Path(canonical.anchor):
        raise _error("codex_work_scope_too_broad")
    return canonical


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _spec(value):
    if type(value) is not dict or set(value) != SPEC_KEYS:
        raise _error("codex_work_spec_invalid", status=400)
    profile = value["requestedProfile"]
    if profile == "pro":
        raise _error("codex_work_pro_unsupported", "本机 Codex 稳定接口没有 Pro mode；未降档、未执行。")
    if type(profile) is not str or profile not in PROFILE_EFFORT:
        raise _error("codex_work_profile_invalid", status=400)
    binding = value["subscription"]
    if (type(binding) is not dict or set(binding) != BINDING_KEYS or binding.get("provider") != "chatgpt_subscription"
            or type(binding.get("connectionId")) is not str or not RUN_ID.fullmatch(binding["connectionId"])
            or type(binding.get("catalogRevision")) is not str or not SHA.fullmatch(binding["catalogRevision"])
            or type(binding.get("modelSlug")) is not str or not MODEL.fullmatch(binding["modelSlug"])):
        raise _error("codex_work_subscription_invalid", status=400)
    workspace, allowed = _plain(value["workspaceRoot"]), _plain(value["allowedRoot"])
    if not allowed.is_relative_to(workspace):
        raise _error("codex_work_scope_outside_workspace")
    text, images, source = value["text"], value["images"], value["sourceSha256"]
    if type(text) is not str or len(text) > MAX_TEXT or "\0" in text:
        raise _error("codex_work_text_invalid", status=400)
    if type(source) is not str or not SHA.fullmatch(source):
        raise _error("codex_work_source_invalid", status=400)
    if type(images) is not list or len(images) > 4:
        raise _error("codex_work_images_invalid", status=400)
    total, frozen_images = 0, []
    for image in images:
        if (type(image) is not dict or set(image) != {"bytes", "mimeType", "sha256"}
                or type(image["bytes"]) is not bytes or not 0 < len(image["bytes"]) <= MAX_IMAGE
                or type(image["mimeType"]) is not str or image["mimeType"] not in IMAGE_EXTENSIONS
                or type(image["sha256"]) is not str or not SHA.fullmatch(image["sha256"])
                or hashlib.sha256(image["bytes"]).hexdigest() != image["sha256"]):
            raise _error("codex_work_image_source_mismatch", status=400)
        total += len(image["bytes"])
        frozen_images.append(dict(image))
    if total > MAX_IMAGES_TOTAL or not text.strip() and not images:
        raise _error("codex_work_input_invalid", status=400)
    return {**value, "subscription": dict(binding), "workspaceRoot": str(workspace),
            "allowedRoot": str(allowed), "images": frozen_images}


def scope_policy(allowed_root, image_root):
    """Actual named-profile contract; never inject unknown legacy read fields.

The :workspace parent preserves Codex's protected .git/.codex paths. Explicit
root/tmp denials remove its broad reads and temporary writes; only the chosen
directory and the exact owned image copies are granted additional access.
"""
    filesystem = {":root": "deny", ":minimal": "read", ":tmpdir": "deny", ":slash_tmp": "deny",
                  str(allowed_root): "write", str(image_root): "read", "glob_scan_max_depth": 3,
                  ":workspace_roots": {pattern: "deny" for pattern in PROTECTED_PATTERNS}}
    filesystem.update({str(Path(allowed_root) / name): "deny" for name in PROTECTED_DIRECTORIES})
    return {"extends": ":workspace", "filesystem": filesystem,
            "network": {"enabled": False}}


def _same_scope(actual, expected):
    if type(actual) is not dict or actual.get("extends") != expected["extends"]:
        return False
    filesystem, network = actual.get("filesystem"), actual.get("network")
    if type(filesystem) is not dict or type(network) is not dict or network.get("enabled") is not False:
        return False
    normalized_fs = {key: value for key, value in filesystem.items() if value is not None}
    normalized_net = {key: value for key, value in network.items() if value is not None}
    return (normalized_fs == expected["filesystem"] and normalized_net == expected["network"]
            and actual.get("workspace_roots") is None
            and all(key in {"extends", "filesystem", "network", "description", "workspace_roots"} for key in actual))


@dataclass(repr=False)
class _Run:
    identifier: str
    spec: dict
    callback: object
    lock: object = field(default_factory=threading.RLock)
    incoming: object = field(default_factory=lambda: queue.Queue(maxsize=32))
    replies: dict = field(default_factory=dict)
    items: dict = field(default_factory=dict)
    state: str = "preparing"
    thread_id: str | None = None
    turn_id: str | None = None
    send_started: bool = False
    interrupted_requested: bool = False
    interrupt_sent: bool = False
    terminal_observed: bool = False
    terminal_status: str | None = None
    process: object = None
    worker: object = None
    read_error: str | None = None
    error: str | None = None
    report: str = ""
    progress_chars: int = 0
    lifecycle_unknown: bool = False
    next_id: int = 1
    secret: str = ""
    home: Path | None = None
    runtime_home: Path | None = None
    is_setup: bool = False
    actual_model: str | None = None
    actual_effort: str | None = None
    deadline: float = 0
    complete: object = field(default_factory=threading.Event)
    write_lock: object = field(default_factory=threading.Lock)


class CodexWorkController:
    """Lazy, event-driven manager for new Console-owned turns only.

Each accepted run owns fresh markers/images and one child process. The dedicated
Console runtime home reuses only its own explicit Windows setup. No start-time
queue scan, shared App daemon, thread listing/resume, or provider retry occurs.
"""
    def __init__(self, subscription, data_dir, *, executable=None, version="1.0.0",
                 popen_factory=None, rpc_timeout=20, turn_timeout=1800, windows_sandbox=None):
        self.subscription = subscription
        self.data_dir = Path(data_dir).absolute()
        self.executable = str(executable) if executable else None
        self.version = version if isinstance(version, str) and re.fullmatch(r"[A-Za-z0-9._+-]{1,64}", version) else "1.0.0"
        self._popen = popen_factory or subprocess.Popen
        self._rpc_timeout = max(1, min(float(rpc_timeout), 60))
        self._turn_timeout = max(1, min(float(turn_timeout), 7200))
        self._lock = threading.RLock()
        self._runs = {}
        self._closed = False
        # This flag only selects an already explicitly configured sandbox. It
        # never performs UAC/setup or changes system users/permissions itself.
        if windows_sandbox not in (None, "elevated"):
            raise _error("codex_work_sandbox_configuration_invalid", status=400)
        self.windows_sandbox = windows_sandbox
        self._initialized = False
        self._setup_run = None
        self._setup = {"status": "not_configured", "busy": False, "ready": False, "error": None,
                       "mode": "elevated", "terminalEventObserved": False, "attempted": False,
                       "requiresAdministratorApproval": True}

    def setup_status(self):
        with self._lock:
            message = {"not_configured": "请在电脑上明确启动 Windows 沙箱设置。",
                       "configuring": "正在设置；如出现 Windows 权限窗口，请亲自处理。",
                       "ready": "已收到沙箱设置完成回执；每次执行仍会核对实际范围。",
                       "failed": "沙箱设置未完成；本次结果已保留。",
                       "unknown": "沙箱设置结果待核对；不会自动重复设置。"}[self._setup["status"]]
            return {**self._setup, "message": message}

    def _runtime(self):
        root = _plain(self.data_dir / "codex-work", must_exist=False)
        root.mkdir(parents=True, exist_ok=True)
        runtime = _plain(root / "runtime-home", must_exist=False)
        runtime.mkdir(exist_ok=True)
        for name in ("appdata", "localappdata", "tmp"):
            _plain(runtime / name, must_exist=False).mkdir(exist_ok=True)
        config = runtime / "config.toml"
        if config.exists():
            if config.is_symlink() or getattr(config.lstat(), "st_file_attributes", 0) & 0x400:
                raise _error("codex_work_runtime_changed")
            if config.read_bytes() != b"# Console-owned runtime; per-process scope is supplied through -c.\n":
                raise _error("codex_work_runtime_changed")
        else:
            with config.open("xb") as stream:
                stream.write(b"# Console-owned runtime; per-process scope is supplied through -c.\n")
                stream.flush()
                os.fsync(stream.fileno())
        return root, runtime

    def start(self):
        """Read only our safe setup receipts once; never setup, login or infer."""
        with self._lock:
            if self._initialized:
                return self.setup_status()
            self._initialized = True
            try:
                root, runtime = self._runtime()
                intent = root / "setup-intent.json"
                if not intent.exists():
                    return self.setup_status()
                document = self._read_setup_receipt(intent)
                if (document.get("format") != 1 or document.get("runtimeHome") != str(runtime)
                        or document.get("mode") != "elevated" or not RUN_ID.fullmatch(document.get("attemptId", ""))):
                    raise _error("codex_work_setup_receipt_invalid")
                self._setup.update(status="unknown", attempted=True, error="codex_work_setup_unknown")
                completed = root / ("setup-completion-" + document["attemptId"] + ".json")
                if completed.exists():
                    receipt = self._read_setup_receipt(completed)
                    if (receipt.get("attemptId") != document["attemptId"] or receipt.get("runtimeHome") != str(runtime)
                            or receipt.get("mode") != "elevated" or receipt.get("terminalEventObserved") is not True
                            or type(receipt.get("success")) is not bool):
                        raise _error("codex_work_setup_receipt_invalid")
                    success = receipt["success"]
                    self._setup.update(status="ready" if success else "failed", ready=success,
                        terminalEventObserved=True, error=None if success else "codex_work_setup_failed")
            except Exception:
                self._setup.update(status="unknown", error="codex_work_setup_receipt_invalid", ready=False)
            return self.setup_status()

    @staticmethod
    def _read_setup_receipt(path):
        if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400 or path.stat().st_size > 8192:
            raise _error("codex_work_setup_receipt_invalid")
        value = json.loads(path.read_bytes())
        if type(value) is not dict:
            raise _error("codex_work_setup_receipt_invalid")
        return value

    @staticmethod
    def _save_setup_receipt(path, document):
        with path.open("xb") as stream:
            stream.write(_canonical(document) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def begin_setup(self, workspace_root, on_event=None):
        """One explicit desktop-confirmed setup, not an inference or UAC click."""
        allowed = _plain(workspace_root)
        self.start()
        with self._lock:
            if self._closed:
                raise _error("codex_work_controller_closed")
            if self._setup["attempted"]:
                return {**self.setup_status(), "accepted": False}
            if any(not run.complete.is_set() for run in self._runs.values()):
                raise _error("codex_work_controller_busy")
            root, runtime = self._runtime()
            identifier = uuid.uuid4().hex
            self._save_setup_receipt(root / "setup-intent.json", {"format": 1, "attemptId": identifier,
                "runtimeHome": str(runtime), "workspaceRoot": str(allowed), "mode": "elevated", "observedAt": _now()})
            run = _Run(identifier, {"sourceSha256": "0" * 64, "allowedRoot": str(allowed)},
                       on_event or (lambda event: True))
            run.home, run.runtime_home, run.is_setup = root, runtime, True
            self._setup_run = run
            self._setup.update(status="configuring", busy=True, ready=False, error=None, attempted=True)
            run.worker = threading.Thread(target=self._execute_setup, args=(run,), daemon=True, name="console-work-setup")
            run.worker.start()
            return {**self.setup_status(), "accepted": True}

    def _setup_changed(self, run):
        try:
            run.callback({"type": "setup_changed", "setup": self.setup_status()})
        except Exception:
            pass

    def _finish_setup(self, run, params):
        if (run.terminal_observed or not {"mode", "success"} <= set(params)
                or set(params) - {"mode", "success", "error"} or params.get("mode") != "elevated"
                or type(params.get("success")) is not bool
                or params.get("error") is not None and type(params["error"]) is not str):
            raise _error("codex_work_setup_notification_invalid")
        success = params["success"] and params.get("error") is None
        self._save_setup_receipt(run.home / ("setup-completion-" + run.identifier + ".json"),
            {"format": 1, "attemptId": run.identifier, "runtimeHome": str(run.runtime_home), "mode": "elevated",
             "terminalEventObserved": True, "success": success, "observedAt": _now()})
        run.terminal_observed = True
        with self._lock:
            self._setup.update(status="ready" if success else "failed", ready=success, busy=False,
                terminalEventObserved=True, error=None if success else "codex_work_setup_failed")
        self._setup_changed(run)

    def _execute_setup(self, run):
        try:
            executable = self.executable or shutil.which("codex")
            if not executable or not Path(executable).is_absolute() or not Path(executable).is_file():
                raise _error("codex_work_cli_unavailable")
            flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            # Setup does not receive ACCESS_TOKEN or invoke a provider.
            run.process = self._popen(self._command(str(Path(executable).resolve()), run.spec["allowedRoot"]),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=run.spec["allowedRoot"],
                env=self._environment(run, None), **flags)
            threading.Thread(target=self._read_stdout, args=(run,), daemon=True).start()
            threading.Thread(target=self._drain_stderr, args=(run,), daemon=True).start()
            self._rpc(run, "initialize", {"clientInfo": {"name": "Codex Console", "version": self.version},
                                          "capabilities": {"experimentalApi": True}})
            self._notify_initialized(run)
            run.send_started = True  # consume the sole ambiguous setup write
            result = self._rpc(run, "windowsSandbox/setupStart", {"mode": "elevated", "cwd": run.spec["allowedRoot"]})
            if result.get("started") is not True:
                run.send_started = False  # exact reply proves setup did not start
                raise _error("codex_work_setup_not_started")
            deadline = time.monotonic() + 600
            while not run.terminal_observed:
                if time.monotonic() >= deadline:
                    raise _error("codex_work_setup_timeout")
                self._pump(run)
        except Exception:
            if not run.terminal_observed:
                live = run.send_started and run.process is not None and run.process.poll() is None
                with self._lock:
                    self._setup.update(status="unknown", ready=False, busy=live, error="codex_work_setup_unknown")
                self._setup_changed(run)
                if live:
                    self._retain_unknown(run)
        finally:
            self._close_idle(run)
            run.complete.set()
            with self._lock:
                self._setup["busy"] = False

    def submit(self, run_id, spec, on_event):
        if type(run_id) is not str or not RUN_ID.fullmatch(run_id) or not callable(on_event):
            raise _error("codex_work_run_invalid", status=400)
        frozen = _spec(spec)
        self.start()
        with self._lock:
            if self._closed:
                raise _error("codex_work_controller_closed")
            if self._setup["busy"]:
                raise _error("codex_work_setup_busy")
            if run_id in self._runs or (self.data_dir / "codex-work" / run_id).exists():
                raise _error("codex_work_run_already_reserved", "此 Work 已接收或结果待核对；不会自动重跑。")
            if len(self._runs) >= 1024 or sum(not run.complete.is_set() for run in self._runs.values()) >= 4:
                raise _error("codex_work_controller_busy")
            run = _Run(run_id, frozen, on_event)
            self._runs[run_id] = run
            run.worker = threading.Thread(target=self._execute, args=(run,), name="console-work-" + run_id[:8], daemon=True)
            run.worker.start()
        return {"runId": run_id, "accepted": True, "executionVerified": False}

    def snapshot(self, run_id):
        with self._lock:
            run = self._runs.get(run_id)
        if run is None:
            raise _error("codex_work_run_not_owned", status=404)
        with run.lock:
            return {"runId": run.identifier, "state": run.state, "threadId": run.thread_id, "turnId": run.turn_id,
                    "sourceSha256": run.spec["sourceSha256"], "requestedModel": run.spec["subscription"]["modelSlug"],
                    "actualModel": run.actual_model, "requestedProfile": run.spec["requestedProfile"],
                    "requestedEffort": PROFILE_EFFORT[run.spec["requestedProfile"]], "actualEffort": run.actual_effort,
                    "terminalEventObserved": run.terminal_observed, "terminalStatus": run.terminal_status,
                    "cancelRequested": run.interrupted_requested, "cancelVerified": run.terminal_status == "interrupted",
                    "error": run.error, "report": run.report, "retryAllowed": False,
                    "active": not run.complete.is_set()}

    def interrupt(self, run_id, thread_id, turn_id):
        with self._lock:
            run = self._runs.get(run_id)
        if run is None:
            raise _error("codex_work_run_not_owned", status=404)
        with run.lock:
            if (type(thread_id) is not str or type(turn_id) is not str
                    or thread_id != run.thread_id or turn_id != run.turn_id or run.complete.is_set()
                    or run.terminal_observed):
                raise _error("codex_work_cancel_target_changed")
            duplicate = run.interrupted_requested
            run.interrupted_requested = True
        return {"runId": run_id, "threadId": thread_id, "turnId": turn_id, "requestAccepted": True,
                "duplicate": duplicate, "cancelVerified": False}

    def close(self):
        # Active turns are retained. Closing a shared/user process or pretending
        # that EOF proves an interrupt would lose the durable lifecycle contract.
        with self._lock:
            self._closed = True
            runs = tuple(self._runs.values())
        active = []
        if self._setup_run is not None and not self._setup_run.complete.is_set():
            active.append(self._setup_run.identifier)
        for run in runs:
            if run.complete.is_set():
                self._close_idle(run)
            else:
                active.append(run.identifier)
        return {"closed": not active, "activeRunCount": len(active), "activeRunIds": active}

    def _clean(self, run, value, maximum=MAX_TEXT):
        if not isinstance(value, str):
            return ""
        return value.replace(run.secret, "［凭据已隐藏］")[:maximum] if run.secret else value[:maximum]

    def _emit(self, run, event_type, **values):
        event = {"type": event_type, "runId": run.identifier, "threadId": run.thread_id, "turnId": run.turn_id,
                 "sourceSha256": run.spec["sourceSha256"], "observedAt": _now(), **values}
        # No raw protocol, environment, RPC error message or stderr is forwarded.
        result = run.callback(event)
        if event_type in {"send_intent", "interrupt_intent"} and result is not True:
            raise _error("codex_work_intent_not_durable")
        return result

    def _command(self, executable, allowed, policy=None):
        settings = {
            "model_provider": json.dumps(PROVIDER),
            "model_providers." + PROVIDER + ".name": '"ChatGPT plan"',
            "model_providers." + PROVIDER + ".base_url": json.dumps(PROVIDER_URL),
            "model_providers." + PROVIDER + ".env_key": '"ACCESS_TOKEN"',
            "model_providers." + PROVIDER + ".wire_api": '"responses"',
            "model_providers." + PROVIDER + ".requires_openai_auth": "false",
            "model_providers." + PROVIDER + ".supports_websockets": "false",
            "model_providers." + PROVIDER + ".request_max_retries": "0",
            "model_providers." + PROVIDER + ".stream_max_retries": "0",
            "agents.enabled": "false", "features.apps": "false", "features.browser_use": "false",
            "features.computer_use": "false", "web_search": '"disabled"',
            "check_for_update_on_startup": "false", "project_doc_max_bytes": "0",
            "mcp_servers": "{}", "plugins": "{}", "hooks": "{}",
            "allow_login_shell": "false", "shell_environment_policy.experimental_use_profile": "false",
            "shell_environment_policy.ignore_default_excludes": "false",
            "shell_environment_policy.exclude": '["ACCESS_TOKEN", "*TOKEN*", "*SECRET*", "*KEY*"]',
            "projects." + json.dumps(str(allowed)) + ".trust_level": '"untrusted"',
        }
        command = [executable, "app-server", "--listen", "stdio://"]
        if self.windows_sandbox is not None or self._setup["ready"]:
            settings["windows.sandbox"] = '"elevated"'
        if policy is not None:
            def toml(value):
                if type(value) is dict:
                    return "{" + ",".join(json.dumps(key) + "=" + toml(row) for key, row in value.items()) + "}"
                return json.dumps(value)
            filesystem = toml(policy["filesystem"])
            settings["default_permissions"] = json.dumps(PERMISSION_PROFILE)
            settings["permissions." + PERMISSION_PROFILE] = ('{extends=":workspace",filesystem=' + filesystem
                                                               + ',network={enabled=false}}')
        for key, value in settings.items():
            command.extend(["-c", key + "=" + value])
        return command

    def _verify_configuration(self, result, policy):
        config = result.get("config")
        if (type(config) is not dict or config.get("default_permissions") != PERMISSION_PROFILE
                or type(config.get("permissions")) is not dict
                or not _same_scope(config["permissions"].get(PERMISSION_PROFILE), policy)):
            raise _error("codex_work_read_scope_unsupported", "本机 Codex 未准确确认限定读写范围；未发送执行请求。")
        # Empty own CODEX_HOME cannot silently adopt globally configured tools.
        if any(config.get(key) not in (None, {}) for key in ("mcp_servers", "plugins", "hooks")):
            raise _error("codex_work_external_tools_present", "检测到额外工具配置；未发送执行请求。")

    def _environment(self, run, token):
        environment = {key: value for key, value in os.environ.items() if key.upper() in SAFE_ENV}
        home = run.runtime_home or run.home
        environment.update(CODEX_HOME=str(home), HOME=str(home), USERPROFILE=str(home),
                           APPDATA=str(home / "appdata"), LOCALAPPDATA=str(home / "localappdata"),
                           TMP=str(home / "tmp"), TEMP=str(home / "tmp"), TMPDIR=str(home / "tmp"))
        if token is not None:
            environment["ACCESS_TOKEN"] = token
        return environment

    def _send(self, run, method, params):
        with run.write_lock:
            identifier = run.next_id
            run.next_id += 1
            frame = _canonical({"id": identifier, "method": method, "params": params}) + b"\n"
            if len(frame) > MAX_INPUT:
                raise _error("codex_work_input_too_large")
            run.process.stdin.write(frame)
            run.process.stdin.flush()
        return identifier

    def _notify_initialized(self, run):
        with run.write_lock:
            run.process.stdin.write(b'{"method":"initialized","params":{}}\n')
            run.process.stdin.flush()

    def _read_stdout(self, run):
        total = 0
        try:
            while True:
                line = run.process.stdout.readline(MAX_LINE + 1)
                if not line:
                    run.read_error = "codex_work_process_ended"
                    return
                total += len(line)
                if len(line) > MAX_LINE or total > MAX_STREAM:
                    run.read_error = "codex_work_stream_too_large"
                    # Keep consuming only this owned pipe; do not block a child
                    # while the lifecycle thread tries its exact interrupt.
                    while run.process.stdout.read(65536):
                        pass
                    return
                value = json.loads(line)
                if type(value) is not dict:
                    raise ValueError()
                run.incoming.put(value, timeout=2)
        except Exception:
            run.read_error = "codex_work_protocol_invalid"

    def _drain_stderr(self, run):
        try:
            while run.process.stderr.read(65536):
                pass
        except Exception:
            pass

    def _reply_server_request(self, run, value):
        method, params = value.get("method"), value.get("params")
        if not isinstance(params, dict) or params.get("threadId") != run.thread_id or params.get("turnId") != run.turn_id:
            raise _error("codex_work_foreign_server_request")
        if method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
            response = {"id": value["id"], "result": {"decision": "cancel"}}
        elif method == "item/permissions/requestApproval":
            response = {"id": value["id"], "result": {"permissions": {}, "scope": "turn"}}
        else:
            response = {"id": value["id"], "error": {"code": -32601, "message": "Additional authority is not granted."}}
        with run.write_lock:
            run.process.stdin.write(_canonical(response) + b"\n")
            run.process.stdin.flush()
        self._emit(run, "approval_blocked", code="codex_work_additional_approval_required")
        run.interrupted_requested = True

    def _maybe_interrupt(self, run):
        with run.lock:
            ready = run.interrupted_requested and not run.interrupt_sent and not run.terminal_observed and run.turn_id is not None
            if ready:
                # Ambiguous writes also consume the sole cancel attempt.
                run.interrupt_sent = True
        if ready:
            self._emit(run, "interrupt_intent")
            self._send(run, "turn/interrupt", {"threadId": run.thread_id, "turnId": run.turn_id})
            run.state = "cancelling"
            self._emit(run, "cancel_requested", cancellationVerified=False)

    def _pump(self, run, timeout=.1):
        self._maybe_interrupt(run)
        try:
            value = run.incoming.get(timeout=timeout)
        except queue.Empty:
            if run.read_error:
                raise _error(run.read_error)
            return
        if "method" in value and "id" in value:
            self._reply_server_request(run, value)
        elif "id" in value:
            if type(value["id"]) is not int or value["id"] in run.replies or len(run.replies) > 16:
                raise _error("codex_work_reply_invalid")
            run.replies[value["id"]] = value
        elif type(value.get("method")) is str:
            self._notification(run, value["method"], value.get("params"))

    def _rpc(self, run, method, params):
        identifier = self._send(run, method, params)
        deadline = time.monotonic() + self._rpc_timeout
        while identifier not in run.replies:
            if time.monotonic() >= deadline:
                raise _error("codex_work_rpc_timeout")
            self._pump(run)
        reply = run.replies.pop(identifier)
        if "error" in reply or type(reply.get("result")) is not dict:
            message = reply.get("error", {}).get("message") if type(reply.get("error")) is dict else None
            if method == "thread/start" and isinstance(message, str) and (
                    "cannot enforce split filesystem read restrictions" in message
                    or "failed to prepare windows sandbox" in message):
                raise _error("codex_work_windows_sandbox_required", "需要先配置支持限定范围的 Windows 沙箱；本次未发送执行请求。")
            raise _error("codex_work_rpc_rejected")
        return reply["result"]

    def _bind_turn(self, run, turn):
        identifier = turn.get("id") if type(turn) is dict else None
        if type(identifier) is not str or not ID.fullmatch(identifier) or not run.send_started:
            raise _error("codex_work_turn_unbound")
        if run.turn_id is not None and run.turn_id != identifier:
            raise _error("codex_work_turn_changed")
        if run.turn_id is None:
            run.turn_id, run.state = identifier, "running"
            self._emit(run, "turn_started", actualModel=run.actual_model, actualEffort=run.actual_effort)

    def _notification(self, run, method, params):
        if type(params) is not dict:
            raise _error("codex_work_notification_invalid")
        if run.is_setup:
            if method == "windowsSandbox/setupCompleted":
                self._finish_setup(run, params)
            return
        if method in {"thread/started", "thread/status/changed", "serverRequest/resolved"}:
            return
        # Irrelevant server/system notifications never become record progress.
        if not method.startswith(("turn/", "item/", "error", "model/rerouted")):
            return
        if params.get("threadId") != run.thread_id:
            raise _error("codex_work_foreign_thread_event")
        if method == "turn/started":
            self._bind_turn(run, params.get("turn"))
            return
        if method == "turn/completed":
            turn = params.get("turn")
            if type(turn) is not dict or turn.get("id") != run.turn_id or turn.get("status") not in {"completed", "interrupted", "failed"}:
                raise _error("codex_work_terminal_unbound")
            self._finish(run, turn)
            return
        if params.get("turnId") != run.turn_id or run.turn_id is None or run.terminal_observed:
            raise _error("codex_work_foreign_turn_event")
        if method == "model/rerouted":
            raise _error("codex_work_model_changed")
        if method == "error":
            self._emit(run, "provider_error", code="codex_work_provider_error", retryAllowed=False)
            return
        if method in {"item/agentMessage/delta", "item/commandExecution/outputDelta", "item/fileChange/outputDelta"}:
            identifier, delta = params.get("itemId"), params.get("delta")
            if type(identifier) is not str or not ID.fullmatch(identifier) or type(delta) is not str or "\0" in delta:
                raise _error("codex_work_progress_invalid")
            item = run.items.setdefault(identifier, {"kind": method, "text": "", "pending": ""})
            if item["kind"] != method or len(run.items) > MAX_ITEMS or len(item["text"]) + len(delta) > MAX_TEXT:
                raise _error("codex_work_progress_too_large")
            item["text"] += delta
            # Scrub complete credentials before releasing any suffix. A prefix
            # split across frames remains buffered until it is disambiguated.
            pending = item["pending"] + delta
            if run.secret:
                pending = pending.replace(run.secret, "［凭据已隐藏］")
                hold = max((size for size in range(1, min(len(run.secret), len(pending) + 1))
                            if pending.endswith(run.secret[:size])), default=0)
            else:
                hold = 0
            chunk = pending[:-hold] if hold else pending
            item["pending"] = pending[-hold:] if hold else ""
            if chunk:
                run.progress_chars += len(chunk)
                if run.progress_chars > MAX_PROGRESS:
                    raise _error("codex_work_progress_too_large")
                self._emit(run, "progress", kind=method, itemId=identifier, text=chunk)
        elif method == "turn/plan/updated":
            plan = params.get("plan")
            if type(plan) is not list or len(plan) > 100 or any(type(row) is not dict
                    or row.get("status") not in {"pending", "inProgress", "completed"}
                    or type(row.get("step")) is not str or len(row["step"]) > 2000 for row in plan):
                raise _error("codex_work_plan_invalid")
            self._emit(run, "plan", plan=[{"step": self._clean(run, row["step"], 2000), "status": row["status"]} for row in plan])
        elif method in {"item/started", "item/completed"}:
            item = params.get("item")
            if type(item) is not dict or type(item.get("id")) is not str or not ID.fullmatch(item["id"]):
                raise _error("codex_work_item_invalid")
            self._emit(run, "item_status", itemId=item["id"], itemType=item.get("type") if item.get("type") in
                {"agentMessage", "commandExecution", "fileChange", "reasoning", "userMessage"} else "other", completed=method == "item/completed")

    def _finish(self, run, turn):
        if run.terminal_observed:
            raise _error("codex_work_duplicate_terminal")
        # Persist the actual terminal fact independently of report validation.
        # A malformed answer cannot turn an idle owned child into an active one.
        run.terminal_observed, run.terminal_status = True, turn["status"]
        items = turn.get("items", [])
        if type(items) is not list or len(items) > MAX_ITEMS:
            raise _error("codex_work_terminal_invalid")
        messages = []
        for item in items:
            if type(item) is not dict:
                raise _error("codex_work_terminal_invalid")
            if item.get("type") == "agentMessage":
                text, identifier = item.get("text"), item.get("id")
                if type(text) is not str or type(identifier) is not str or not ID.fullmatch(identifier) or len(text) > MAX_TEXT:
                    raise _error("codex_work_terminal_invalid")
                delta = run.items.get(identifier)
                if delta is not None and (delta["kind"] != "item/agentMessage/delta" or delta["text"] != text):
                    raise _error("codex_work_terminal_text_mismatch")
                messages.append(text)
        if not messages:
            messages = [row["text"] for row in run.items.values() if row["kind"] == "item/agentMessage/delta"]
        report = "\n\n".join(messages)
        if len(report) > MAX_TEXT:
            raise _error("codex_work_report_too_large")
        run.report = self._clean(run, report)
        run.state = turn["status"]
        if turn["status"] == "completed" and (turn.get("error") is not None or not report.strip()):
            run.state, run.error = "unknown", "codex_work_completed_report_unverified"
        self._emit(run, "terminal", status=run.state, terminalStatus=run.terminal_status,
                   terminalEventObserved=True, report=run.report, actualModel=run.actual_model,
                   actualEffort=run.actual_effort, error=run.error, cancellationVerified=run.terminal_status == "interrupted",
                   executionVerified=False, retryAllowed=False)

    def _close_idle(self, run):
        process = run.process
        if process is None or run.send_started and not run.terminal_observed and process.poll() is None:
            return
        try:
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
            process.wait(timeout=3)
        except Exception:
            # No force kill or service-wide cleanup. Only this owned process can
            # be reviewed if its normal EOF does not finish within the bound.
            pass

    def _retain_unknown(self, run):
        """Keep only this owned live child observable; never replay its turn.

The updater remains blocked while its real state is unknown. An explicit
matching interrupt can still reach it, and a later actual terminal is retained.
No provider call, process kill, thread adoption or queue scan is performed.
"""
        while not run.terminal_observed and run.process.poll() is None:
            try:
                self._maybe_interrupt(run)
                value = run.incoming.get(timeout=.25)
                if "method" in value and "id" in value:
                    self._reply_server_request(run, value)
                elif "id" in value:
                    # Sole interrupt acknowledgement is not completion.
                    continue
                elif type(value.get("method")) is str:
                    self._notification(run, value["method"], value.get("params"))
            except queue.Empty:
                continue
            except Exception:
                # Retain the first safe failure and keep consuming the bounded
                # owned pipe. Malformed/foreign events cannot supply completion.
                continue

    def _execute(self, run):
        try:
            prepared = self.subscription.prepare_work_connection(run.spec["subscription"])
            if (type(prepared) is not dict or set(prepared) != {"accessToken", "subscription"}
                    or prepared["subscription"] != run.spec["subscription"]
                    or type(prepared["accessToken"]) is not str or not 1 <= len(prepared["accessToken"]) <= 16384
                    or any(ord(character) <= 32 or ord(character) >= 127 for character in prepared["accessToken"])):
                raise _error("codex_work_connection_invalid")
            run.secret = prepared["accessToken"]
            executable = self.executable or shutil.which("codex")
            if not executable or not Path(executable).is_absolute() or not Path(executable).is_file():
                raise _error("codex_work_cli_unavailable")
            executable = str(Path(executable).resolve())
            root, run.runtime_home = self._runtime()
            run.home = root / run.identifier
            run.home.mkdir(exist_ok=False)
            (run.home / "images").mkdir()
            image_root = run.home / "images"
            policy = scope_policy(run.spec["allowedRoot"], image_root)
            inputs = [{"type": "text", "text": run.spec["text"]}] if run.spec["text"] else []
            for index, image in enumerate(run.spec["images"]):
                path = image_root / (str(index) + "." + IMAGE_EXTENSIONS[image["mimeType"]])
                with path.open("xb") as stream:
                    stream.write(image["bytes"])
                inputs.append({"type": "localImage", "path": str(path)})
            run.spec["images"] = []  # release bounded bytes after their exact owned copies
            flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            run.process = self._popen(self._command(executable, run.spec["allowedRoot"], policy), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=run.spec["allowedRoot"],
                env=self._environment(run, run.secret), **flags)
            threading.Thread(target=self._read_stdout, args=(run,), daemon=True).start()
            threading.Thread(target=self._drain_stderr, args=(run,), daemon=True).start()
            self._rpc(run, "initialize", {"clientInfo": {"name": "Codex Console", "title": "Codex Console", "version": self.version},
                                          "capabilities": {"experimentalApi": True}})
            self._notify_initialized(run)
            configuration = self._rpc(run, "config/read", {"includeLayers": False, "cwd": run.spec["allowedRoot"]})
            self._verify_configuration(configuration, policy)
            effort = PROFILE_EFFORT[run.spec["requestedProfile"]]
            result = self._rpc(run, "thread/start", {"model": run.spec["subscription"]["modelSlug"],
                "modelProvider": PROVIDER, "cwd": run.spec["allowedRoot"], "approvalPolicy": "never",
                "permissions": PERMISSION_PROFILE, "runtimeWorkspaceRoots": [run.spec["allowedRoot"]],
                "ephemeral": False, "config": {"model_reasoning_effort": effort}})
            thread_id = result.get("thread", {}).get("id")
            if type(thread_id) is not str or not ID.fullmatch(thread_id):
                raise _error("codex_work_thread_invalid")
            run.thread_id = thread_id
            if (result.get("model") != run.spec["subscription"]["modelSlug"] or result.get("modelProvider") != PROVIDER
                    or result.get("reasoningEffort") != effort or result.get("approvalPolicy") != "never"
                    or result.get("cwd") != run.spec["allowedRoot"]):
                raise _error("codex_work_thread_settings_changed")
            profile = result.get("activePermissionProfile")
            if (type(profile) is not dict or profile != {"id": PERMISSION_PROFILE, "extends": policy["extends"]}):
                raise _error("codex_work_read_scope_unsupported", "本机 Codex 未准确确认限定读写范围；未发送执行请求。")
            run.actual_model, run.actual_effort = result["model"], effort
            self._emit(run, "prepared", requestedProfile=run.spec["requestedProfile"],
                       actualModel=run.actual_model, actualEffort=effort, sandboxVerified=True)
            # This callback is the durable fence immediately before the sole
            # inference-starting RPC. Ambiguous acknowledgement never retries.
            self._emit(run, "send_intent", model=run.actual_model, effort=effort)
            run.send_started = True
            started = self._rpc(run, "turn/start", {"threadId": thread_id, "input": inputs,
                "cwd": run.spec["allowedRoot"], "approvalPolicy": "never", "permissions": PERMISSION_PROFILE,
                "model": run.actual_model, "effort": effort})
            self._bind_turn(run, started.get("turn"))
            run.deadline = time.monotonic() + self._turn_timeout
            while not run.terminal_observed:
                if time.monotonic() >= run.deadline:
                    raise _error("codex_work_turn_timeout")
                self._pump(run)
        except Exception as error:
            code = getattr(error, "code", None)
            code = code if type(code) is str and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", code) else "codex_work_controller_error"
            run.error, run.state = code, "unknown" if run.send_started else "failed"
            partial = "\n\n".join(row["text"] for row in run.items.values()
                                  if row["kind"] == "item/agentMessage/delta")
            run.report = self._clean(run, run.report or partial)
            try:
                self._emit(run, "terminal", status=run.state, terminalStatus=run.terminal_status,
                    terminalEventObserved=run.terminal_observed, report=self._clean(run, run.report), error=code,
                    cancellationVerified=False, executionVerified=False, retryAllowed=False)
            except Exception:
                pass
        finally:
            if run.send_started and not run.terminal_observed and run.process is not None and run.process.poll() is None:
                run.lifecycle_unknown = True
                self._retain_unknown(run)
            self._close_idle(run)
            run.secret = ""
            # Unknown active children are retained; root must not call their
            # disappearance successful cancellation or update over active work.
            if not run.send_started or run.terminal_observed or run.process is None or run.process.poll() is not None:
                run.complete.set()
