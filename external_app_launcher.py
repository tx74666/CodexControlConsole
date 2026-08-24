import ctypes
from ctypes import wintypes
from functools import lru_cache
import os
from pathlib import Path
import subprocess
import sys
import threading
import time


_LAUNCH_GUARD = threading.Lock()
_RECENT_LAUNCHES = {}
_RECENT_LAUNCH_SECONDS = 5.0


def _normalized_path(value):
    return os.path.normcase(os.path.abspath(str(Path(value).expanduser().resolve())))


@lru_cache(maxsize=1)
def _windows_apis():
    if sys.platform != "win32":
        return None

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    psapi.EnumProcesses.argtypes = [
        ctypes.POINTER(wintypes.DWORD),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    psapi.EnumProcesses.restype = wintypes.BOOL

    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.SetFocus.argtypes = [wintypes.HWND]
    user32.SetFocus.restype = wintypes.HWND
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL
    return kernel32, psapi, user32


def _process_image_path(process_id):
    apis = _windows_apis()
    if not apis:
        return ""
    kernel32, _, _ = apis
    process = kernel32.OpenProcess(0x1000, False, int(process_id))
    if not process:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
            return ""
        return buffer.value
    finally:
        kernel32.CloseHandle(process)


def _all_process_ids():
    apis = _windows_apis()
    if not apis:
        return []
    _, psapi, _ = apis
    capacity = 2048
    while capacity <= 32768:
        process_ids = (wintypes.DWORD * capacity)()
        needed = wintypes.DWORD()
        if not psapi.EnumProcesses(process_ids, ctypes.sizeof(process_ids), ctypes.byref(needed)):
            return []
        count = needed.value // ctypes.sizeof(wintypes.DWORD)
        if count < capacity:
            return [int(process_ids[index]) for index in range(count) if process_ids[index]]
        capacity *= 2
    return []


def _matching_process_ids(executable):
    if sys.platform != "win32":
        return set()
    target = _normalized_path(executable)
    matches = set()
    for process_id in _all_process_ids():
        image_path = _process_image_path(process_id)
        if image_path and _normalized_path(image_path) == target:
            matches.add(process_id)
    return matches


def _window_handles_for_processes(process_ids):
    apis = _windows_apis()
    if not apis or not process_ids:
        return []
    _, _, user32 = apis
    handles = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(window, _):
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
        if process_id.value not in process_ids:
            return True
        if not (user32.IsWindowVisible(window) or user32.IsIconic(window)):
            return True
        if user32.GetWindowTextLengthW(window) <= 0:
            return True
        handles.append(window)
        return True

    callback = callback_type(visit)
    user32.EnumWindows(callback, 0)
    return handles


def _activate_window(window):
    apis = _windows_apis()
    if not apis:
        return False
    kernel32, _, user32 = apis
    current_thread = kernel32.GetCurrentThreadId()
    target_thread = user32.GetWindowThreadProcessId(window, None)
    foreground = user32.GetForegroundWindow()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    attached = []

    for thread_id in {int(target_thread or 0), int(foreground_thread or 0)}:
        if thread_id and thread_id != current_thread and user32.AttachThreadInput(current_thread, thread_id, True):
            attached.append(thread_id)
    try:
        user32.ShowWindow(window, 9 if user32.IsIconic(window) else 5)
        user32.SetWindowPos(window, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
        user32.BringWindowToTop(window)
        user32.SetForegroundWindow(window)
        user32.SetFocus(window)
    finally:
        for thread_id in reversed(attached):
            user32.AttachThreadInput(current_thread, thread_id, False)

    foreground = user32.GetForegroundWindow()
    if not foreground:
        return False
    if int(foreground) == int(window):
        return True

    target_process = wintypes.DWORD()
    foreground_process = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(target_process))
    user32.GetWindowThreadProcessId(foreground, ctypes.byref(foreground_process))
    return bool(target_process.value and target_process.value == foreground_process.value)


def focus_existing_executable(executable, wait_seconds=0.0):
    if sys.platform != "win32":
        return {"existing": False, "activated": False, "pending": False}
    deadline = time.monotonic() + max(0.0, float(wait_seconds))
    process_ids = set()
    while True:
        if not process_ids:
            process_ids = _matching_process_ids(executable)
        if process_ids:
            windows = _window_handles_for_processes(process_ids)
            if windows:
                return {
                    "existing": True,
                    "activated": bool(_activate_window(windows[0])),
                    "pending": False,
                }
        if time.monotonic() >= deadline:
            return {
                "existing": bool(process_ids),
                "activated": False,
                "pending": bool(process_ids),
            }
        time.sleep(0.05)


def launch_or_focus_executable(executable, starter=None, startup_wait=1.0):
    target = Path(executable).expanduser().resolve()
    if not target.is_file():
        raise ValueError(f"executable was not found: {target}")
    if sys.platform != "win32":
        subprocess.Popen([str(target)], cwd=str(target.parent))
        return {"launched": True, "existing": False, "activated": False, "pending": False}

    start = starter or os.startfile
    key = _normalized_path(target)
    with _LAUNCH_GUARD:
        existing = focus_existing_executable(target, wait_seconds=0.15)
        if existing["existing"]:
            if not existing["activated"]:
                existing = focus_existing_executable(target, wait_seconds=0.75)
            return {"launched": False, **existing}

        now = time.monotonic()
        recent = _RECENT_LAUNCHES.get(key, 0.0)
        if recent and now - recent < _RECENT_LAUNCH_SECONDS:
            focused = focus_existing_executable(target, wait_seconds=min(1.0, startup_wait))
            return {
                "launched": False,
                "existing": focused["existing"],
                "activated": focused["activated"],
                "pending": not focused["activated"],
            }

        start(str(target))
        _RECENT_LAUNCHES[key] = now
        focused = focus_existing_executable(target, wait_seconds=startup_wait)
        return {
            "launched": True,
            "existing": False,
            "activated": focused["activated"],
            "pending": not focused["activated"],
        }
