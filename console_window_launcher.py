"""Conservative reuse of Console browser app windows.

This module never terminates a browser process. A legacy title match permits
focus only; WM_CLOSE requires a scope property placed on a uniquely observed
new window by this launcher. The caller supplies cross-process serialization.
"""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import hashlib
import json
import ntpath
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
import uuid

from external_app_launcher import _activate_window, _normalized_path, _process_image_path, _windows_apis


_OWNER_PROPERTY = "CodexConsole.WindowOwner.v1"
_SCOPE_PREFIX = "CodexConsole.WindowScope.v1."
_START_WAIT = 9.0
_CLOSE_WAIT = 4.0
_POLL_SECONDS = 0.05
_PENDING_SECONDS = 60.0
_MODULE_TITLES = frozenset({
    "Console", "Manager", "管理", "Blender", "Unity", "Steamwork",
    "RandomRealm", "随机领域", "隨機領域", "Music", "音乐", "音樂", "Wallpaper", "桌布",
})


@dataclass(frozen=True)
class Window:
    handle: int
    pid: int
    title: str
    class_name: str
    image: str
    owned: bool = False
    scope_pid: int = 0


def _browser_window(window):
    if window.class_name != "Chrome_WidgetWin_1" or not window.pid:
        return False
    return ntpath.basename(window.image).lower() in {"msedge.exe", "chrome.exe"}


def _console_window(window):
    if not _browser_window(window):
        return False
    return window.title == "Codex Console" or (
        window.title.startswith("Codex Console - ")
        and window.title[len("Codex Console - "):] in _MODULE_TITLES
    )


def _scope_property(url, data_dir):
    address = urlsplit(str(url))
    if address.scheme not in {"http", "https"} or address.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Console window URL must use a loopback HTTP(S) address")
    if address.username or address.password or not str(data_dir).strip():
        raise ValueError("Console window scope requires a local data directory and no URL credentials")
    port = address.port or (443 if address.scheme == "https" else 80)
    value = f"{_normalized_path(data_dir)}\n{port}".encode("utf-8")
    return _SCOPE_PREFIX + hashlib.sha256(value).hexdigest()


class _NativeWindows:
    def __init__(self, apis):
        self.user32 = apis[2]
        user32 = self.user32
        self.callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows.argtypes = [self.callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
        user32.GetPropW.restype = wintypes.HANDLE
        user32.SetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE]
        user32.SetPropW.restype = wintypes.BOOL
        user32.RemovePropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
        user32.RemovePropW.restype = wintypes.HANDLE
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostMessageW.restype = wintypes.BOOL

    def inspect(self, handle, scope):
        user32 = self.user32
        if not user32.IsWindow(handle):
            return None
        class_name = ctypes.create_unicode_buffer(256)
        if not user32.GetClassNameW(handle, class_name, len(class_name)) or class_name.value != "Chrome_WidgetWin_1":
            return None
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        image = _process_image_path(pid.value)
        if ntpath.basename(image).lower() not in {"msedge.exe", "chrome.exe"}:
            return None
        owned = bool(user32.GetPropW(handle, _OWNER_PROPERTY))
        scope_pid = int(user32.GetPropW(handle, scope) or 0)
        size = user32.GetWindowTextLengthW(handle)
        title = ""
        if 0 < size <= 512:
            buffer = ctypes.create_unicode_buffer(size + 1)
            user32.GetWindowTextW(handle, buffer, len(buffer))
            title = buffer.value
        window = Window(int(handle), pid.value, title, class_name.value, image, owned, scope_pid)
        # Navigation can clear/change a document title. Existing ownership must
        # remain visible to duplicate suppression and foreign-scope isolation.
        # Untagged/new windows still need the strict Console title whitelist.
        return window if owned or scope_pid or _console_window(window) else None

    def scan(self, scope):
        handles, matches, failures = set(), [], []

        def visit(handle, _):
            handles.add(int(handle))
            try:
                window = self.inspect(handle, scope)
                if window:
                    matches.append(window)
            except Exception as error:
                failures.append(error)
            return True

        callback = self.callback_type(visit)
        if not self.user32.EnumWindows(callback, 0) or failures:
            raise OSError("Console window enumeration was incomplete")
        return handles, matches

    def tag(self, window, scope):
        current = self.inspect(window.handle, scope)
        if not _same_window(current, window) or current.owned or current.scope_pid:
            return False
        # The PID in the scope property also makes every later close revalidate
        # the original window process. Never tag a pre-existing legacy window.
        if not self.user32.SetPropW(window.handle, scope, window.pid):
            return False
        if not self.user32.SetPropW(window.handle, _OWNER_PROPERTY, 1):
            self.user32.RemovePropW(window.handle, scope)
            return False
        return True

    def activate(self, window):
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(window.handle, ctypes.byref(pid))
        if pid.value != window.pid:
            return False
        return bool(_activate_window(window.handle))

    def close(self, window, scope):
        current = self.inspect(window.handle, scope)
        if not _same_window(current, window) or not _belongs(current):
            return False
        return bool(self.user32.PostMessageW(window.handle, 0x0010, 0, 0))  # WM_CLOSE

    def alive(self, window):
        if not self.user32.IsWindow(window.handle):
            return False
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(window.handle, ctypes.byref(pid))
        return pid.value == window.pid


def _same_window(current, original):
    return bool(current and _console_window(current)
                and (current.handle, current.pid, current.class_name, current.image)
                == (original.handle, original.pid, original.class_name, original.image))


def _belongs(window):
    return bool(window.owned and window.scope_pid == window.pid and window.pid)


def _native_windows():
    apis = _windows_apis()
    return _NativeWindows(apis) if apis else None


def _result(status, **values):
    return {"status": status, "launched": False, "existing": False, "activated": False,
            "pending": False, "replaced": False, "blocked": False, "legacyNeedsRefresh": False, **values}


def _activate(native, window):
    try:
        return bool(native.activate(window))
    except OSError:
        return False


class _PendingStart:
    def __init__(self, data_dir, scope):
        self.scope = scope
        self.path = Path(data_dir).expanduser().resolve() / "cache" / f"console-window-start-{scope.rsplit('.', 1)[-1]}.json"

    def active(self):
        try:
            with self.path.open("rb") as source:
                raw = source.read(4097)
        except FileNotFoundError:
            return False
        try:
            value = json.loads(raw) if len(raw) <= 4096 else None
            if not isinstance(value, dict) or value.get("scope") != self.scope:
                raise ValueError("unexpected pending launch scope")
            started = float(value["startedAt"])
            if not (started > 0):
                raise ValueError("invalid pending launch time")
        except (ValueError, TypeError, KeyError) as error:
            raise OSError("Pending Console launch record could not be verified") from error
        return 0 <= time.time() - started < _PENDING_SECONDS

    def set(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps({"scope": self.scope, "startedAt": time.time()}), encoding="utf-8")
            os.replace(temporary, self.path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def clear(self):
        try:
            self.path.unlink()
        except OSError:
            # A stale marker only delays future attempts; never use marker
            # cleanup failure as a reason to duplicate an existing window.
            pass


def launch_or_focus(url, starter, data_dir, replace=False):
    """Focus an existing app, or call starter(url) once after safe checks.

    ``replace`` closes only windows with this data-directory/port scope tag.
    Legacy or ambiguous windows block replacement. Foreground refusal never
    falls back to starting another window. Call under a cross-process mutex.
    """
    scope = _scope_property(url, data_dir)
    pending_start = _PendingStart(data_dir, scope)
    native = _native_windows()
    if native is None:
        return _result("unsupported", blocked=True)
    try:
        baseline, candidates = native.scan(scope)
    except OSError as error:
        return _result("scan-failed", blocked=True, error=str(error))
    owned = [window for window in candidates if _belongs(window)]
    legacy = [window for window in candidates if not window.owned and not window.scope_pid]
    if owned or legacy:
        pending_start.clear()
    if any(window.scope_pid and not _belongs(window) for window in candidates):
        return _result("identity-mismatch", existing=True, blocked=True)
    if replace and legacy:
        return _result("legacy-needs-refresh", existing=True, blocked=True, legacyNeedsRefresh=True)
    replaced = False
    if owned:
        if not replace:
            return _result("focused" if (activated := _activate(native, owned[0])) else "existing-not-foreground",
                           existing=True, activated=activated)
        if any(not _console_window(window) for window in owned):
            return _result("owned-title-unconfirmed", existing=True, blocked=True)
        for window in owned:
            if not native.close(window, scope):
                return _result("close-rejected", existing=True, blocked=True)
        deadline = time.monotonic() + _CLOSE_WAIT
        while any(native.alive(window) for window in owned):
            if time.monotonic() >= deadline:
                return _result("close-pending", existing=True, pending=True, blocked=True)
            time.sleep(_POLL_SECONDS)
        replaced = True
    elif legacy:
        if len(legacy) != 1:
            return _result("ambiguous-legacy", existing=True, blocked=True)
        activated = _activate(native, legacy[0])
        return _result("legacy-focused" if activated else "legacy-not-foreground", existing=True, activated=activated)

    if not replaced:
        try:
            pending = pending_start.active()
        except OSError as error:
            return _result("pending-state-unavailable", blocked=True, error=str(error))
        if pending:
            deadline = time.monotonic() + _START_WAIT
            while True:
                try:
                    _, observed = native.scan(scope)
                except OSError as error:
                    return _result("scan-failed", pending=True, blocked=True, error=str(error))
                if any(_belongs(window) or not window.owned or window.scope_pid for window in observed):
                    pending_start.clear()
                    # Re-evaluate identity using the normal focus/close rules.
                    # A late legacy window is still focus-only, never adopted.
                    return launch_or_focus(url, starter, data_dir, replace=replace)
                if time.monotonic() >= deadline:
                    return _result("startup-pending", pending=True)
                time.sleep(_POLL_SECONDS)

    # Re-snapshot immediately before launch; old handles can survive closure
    # briefly, and other browser windows must never become ownership evidence.
    try:
        baseline, remaining = native.scan(scope)
    except OSError as error:
        return _result("scan-failed", blocked=True, replaced=replaced, error=str(error))
    if any(window.scope_pid for window in remaining):
        return _result("existing-after-close", existing=True, blocked=True, replaced=replaced)
    remaining_legacy = [window for window in remaining if not window.owned]
    if remaining_legacy:
        pending_start.clear()
        if replace or len(remaining_legacy) != 1:
            return _result("legacy-needs-refresh" if replace else "ambiguous-legacy", existing=True,
                           blocked=True, legacyNeedsRefresh=bool(replace), replaced=replaced)
        activated = _activate(native, remaining_legacy[0])
        return _result("legacy-focused" if activated else "legacy-not-foreground", existing=True, activated=activated)
    try:
        pending_start.set()
    except OSError as error:
        return _result("pending-state-unavailable", blocked=True, replaced=replaced, error=str(error))
    try:
        starter(url)
    except Exception as error:
        pending_start.clear()
        return _result("launch-failed", replaced=replaced, error=str(error))
    deadline = time.monotonic() + _START_WAIT
    while True:
        try:
            _, windows = native.scan(scope)
        except OSError as error:
            return _result("launched-unconfirmed", launched=True, pending=True, replaced=replaced, error=str(error))
        fresh = [window for window in windows if window.handle not in baseline
                 and not window.owned and not window.scope_pid]
        if fresh:
            pending_start.clear()
        if len(fresh) > 1:
            return _result("launched-ambiguous", launched=True, pending=True, replaced=replaced)
        if len(fresh) == 1:
            candidate = fresh[0]
            time.sleep(_POLL_SECONDS)
            current = native.inspect(candidate.handle, scope)
            if _same_window(current, candidate) and not current.owned and not current.scope_pid:
                tagged = native.tag(current, scope)
                return _result("launched" if tagged else "launched-untagged", launched=True,
                               activated=_activate(native, current) if tagged else False,
                               pending=not tagged, replaced=replaced)
        if time.monotonic() >= deadline:
            return _result("launched-pending", launched=True, pending=True, replaced=replaced)
        time.sleep(_POLL_SECONDS)
