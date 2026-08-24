from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import external_app_launcher as launcher  # noqa: E402
import world_console  # noqa: E402


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    with TemporaryDirectory(prefix="codex-app-launcher-") as temporary:
        executable = Path(temporary) / "Example.exe"
        executable.write_bytes(b"MZ")

        starter = Mock()
        launcher._RECENT_LAUNCHES.clear()
        with patch.object(
            launcher,
            "focus_existing_executable",
            return_value={"existing": True, "activated": True, "pending": False},
        ):
            result = launcher.launch_or_focus_executable(executable, starter=starter, startup_wait=0)
        require(result["existing"] and result["activated"], "an existing app was not activated")
        require(not result["launched"] and not starter.called, "an existing app was launched again")

        launcher._RECENT_LAUNCHES.clear()
        starter.reset_mock()
        missing = {"existing": False, "activated": False, "pending": False}
        with patch.object(launcher, "focus_existing_executable", return_value=missing):
            first = launcher.launch_or_focus_executable(executable, starter=starter, startup_wait=0)
            second = launcher.launch_or_focus_executable(executable, starter=starter, startup_wait=0)
        require(first["launched"], "a missing app was not launched")
        require(not second["existing"] and second["pending"], "a rapid second launch reported a phantom process")
        require(starter.call_count == 1, "rapid clicks launched more than one process")

        target_window = 101
        other_window = 202
        kernel32 = Mock()
        kernel32.GetCurrentThreadId.return_value = 1
        user32 = Mock()
        user32.IsIconic.return_value = False
        user32.GetForegroundWindow.return_value = other_window
        user32.AttachThreadInput.return_value = False

        def window_thread_process(window, process_pointer):
            if process_pointer is not None:
                process_pointer._obj.value = 41 if int(window) == target_window else 99
            return 2

        user32.GetWindowThreadProcessId.side_effect = window_thread_process
        with patch.object(launcher, "_windows_apis", return_value=(kernel32, Mock(), user32)):
            require(not launcher._activate_window(target_window), "a rejected foreground activation was reported as successful")
            user32.GetForegroundWindow.return_value = target_window
            require(launcher._activate_window(target_window), "a confirmed foreground activation was not reported")

        focused = {"launched": False, "existing": True, "activated": True, "pending": False}
        with patch.object(world_console, "launch_or_focus_executable", return_value=focused) as focus, patch.object(
            world_console.os,
            "startfile",
        ) as startfile:
            opened = world_console.open_file_resource(executable)
        require(focus.call_args.args[0] == executable.resolve(), "the executable path was not passed to the launcher")
        require(opened["existing"] and opened["activated"], "the API did not return the activation state")
        require(not startfile.called, "the executable bypassed the single-instance launcher")

    print("PASS external application launch-or-focus behavior")


if __name__ == "__main__":
    main()
