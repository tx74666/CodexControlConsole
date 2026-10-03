import json
import io
import os
from contextlib import ExitStack
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from console_window_session import ConsoleWindowSessionService  # noqa: E402


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def available_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def post_json(url, payload, headers=None):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=4) as response:
        return json.loads(response.read().decode("utf-8"))


def require_rejected_post(url, payload, status, headers=None):
    try:
        post_json(url, payload, headers)
    except urllib.error.HTTPError as error:
        require(error.code == status, f"POST returned {error.code}, expected {status}")
        require(json.loads(error.read().decode("utf-8")).get("error"), "rejected POST lacked an error")
    else:
        raise AssertionError("invalid retirement request was accepted")


def check_session_service():
    shutdown = threading.Event()
    service = ConsoleWindowSessionService(
        shutdown.set,
        close_delay_seconds=0.12,
    )
    try:
        first = service.update({"action": "open", "sessionId": "window-one"})
        repeated = service.update({"action": "heartbeat", "sessionId": "window-one"})
        second = service.update({"action": "open", "sessionId": "window-two"})
        require(first["activeSessions"] == 1, "first window was not registered")
        require(repeated["activeSessions"] == 1, "heartbeat duplicated a window session")
        require(second["activeSessions"] == 2, "second window was not registered")

        service.update({"action": "close", "sessionId": "window-one"})
        time.sleep(0.18)
        require(not shutdown.is_set(), "closing one of two windows stopped the backend")

        service.update({"action": "close", "sessionId": "window-two"})
        time.sleep(0.04)
        service.update({"action": "open", "sessionId": "window-two"})
        time.sleep(0.16)
        require(not shutdown.is_set(), "a page reload was mistaken for the final window closing")

        service.update({"action": "close", "sessionId": "window-two"})
        require(shutdown.wait(1.0), "the backend stayed alive after the final window closed")
    finally:
        service.stop()

    background_shutdown = threading.Event()
    background_service = ConsoleWindowSessionService(
        background_shutdown.set,
        close_delay_seconds=0.05,
    )
    try:
        background_service.update({"action": "open", "sessionId": "background-window"})
        time.sleep(0.3)
        require(
            not background_shutdown.is_set(),
            "a background or throttled window was mistaken for a closed window",
        )
        heartbeat = background_service.update({
            "action": "heartbeat",
            "sessionId": "background-window",
        })
        require(heartbeat["activeSessions"] == 1, "background heartbeat duplicated the session")
        background_service.update({"action": "close", "sessionId": "background-window"})
        require(background_shutdown.wait(1.0), "an explicitly closed window left the backend running")
    finally:
        background_service.stop()

    try:
        service.update({"action": "invalid", "sessionId": "window-one"})
    except ValueError:
        pass
    else:
        raise AssertionError("invalid window actions were accepted")


def check_live_server(*, retire=False):
    port = available_port()
    environment = os.environ.copy()
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with tempfile.TemporaryDirectory(prefix="codex-console-lifecycle-") as temporary:
        temporary_path = Path(temporary)
        Path(temporary_path, ".cache-migrated-v0.3").write_text("test\n", encoding="utf-8")
        desktop_layout_data = temporary_path / "CodexControlConsole" / "desktop-layout"
        desktop_layout_helper = temporary_path / "DesktopLayout-Test.ps1"
        desktop_layout_helper.write_text(
            'param([string]$Action = "list", [string]$Path = "")\n'
            'throw "Desktop operations are disabled in the lifecycle check."\n',
            encoding="utf-8",
        )
        environment["CODEX_CONTROL_DATA_DIR"] = temporary
        environment["CODEX_CONTROL_DESKTOP_LAYOUT_DATA_DIR"] = str(desktop_layout_data)
        environment["CODEX_CONTROL_DESKTOP_LAYOUT_CURRENT"] = str(
            desktop_layout_data / "plans" / "desktop-layout-current.json"
        )
        environment["CODEX_CONTROL_DESKTOP_LAYOUT_SCRIPT"] = str(desktop_layout_helper)
        environment["CODEX_CONTROL_DESKTOP_LAYOUT_STARTUP_FILE"] = str(
            temporary_path / "Startup" / "RestoreDesktopLayout.vbs"
        )
        process = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "world_console.py"),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-browser",
            ],
            cwd=str(ROOT),
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        endpoint = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise AssertionError(f"test server exited early with code {process.returncode}")
                try:
                    with urllib.request.urlopen(endpoint + "/api/console/config", timeout=1) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.1)
            else:
                raise AssertionError("test server did not become ready")

            with urllib.request.urlopen(endpoint + "/api/console/desktop-layout", timeout=4) as response:
                desktop_layout_status = json.loads(response.read().decode("utf-8"))
            require(
                Path(desktop_layout_status["dataDirectory"]).resolve() == desktop_layout_data.resolve(),
                "lifecycle server reached the real desktop-layout data directory",
            )
            require(
                Path(desktop_layout_status["tool"]["path"]).resolve() == desktop_layout_helper.resolve(),
                "lifecycle server reached the real desktop-layout helper",
            )

            if retire:
                with urllib.request.urlopen(endpoint + "/api/console/config", timeout=4) as response:
                    runtime = json.loads(response.read().decode("utf-8"))["runtime"]
                require(Path(runtime["dataDirectory"]).resolve() == temporary_path.resolve(),
                        "retirement server reached the real user data directory")
                require(runtime.get("instanceId") and runtime.get("handoffProtocol") == 1,
                        "server did not advertise its retirement identity and protocol")
                version = runtime["version"]
                major = int(version.split(".", 1)[0])
                newer_version = f"{major + 1}.0.0"
                valid = {"expectedInstanceId": runtime["instanceId"], "version": newer_version}
                for invalid in (
                    {**valid, "expectedInstanceId": "different-runtime-instance"},
                    {**valid, "version": version},
                    {**valid, "version": "0.0.0"},
                ):
                    require_rejected_post(endpoint + "/api/console/retire", invalid, 400)
                for hostile_headers in (
                    {"Origin": "https://untrusted.example"},
                    {"Sec-Fetch-Site": "cross-site"},
                    {"Host": "untrusted.example"},
                ):
                    require_rejected_post(endpoint + "/api/console/retire", valid, 403, hostile_headers)
                # A rejected request must not have scheduled a delayed shutdown.
                time.sleep(0.35)
                require(process.poll() is None, "a rejected retirement stopped the server")
                with urllib.request.urlopen(endpoint + "/api/console/config", timeout=4) as response:
                    unchanged = json.loads(response.read().decode("utf-8"))["runtime"]
                require(unchanged["instanceId"] == runtime["instanceId"],
                        "the original isolated runtime changed after rejected requests")
                accepted = post_json(endpoint + "/api/console/retire", valid)
                require(accepted.get("accepted") is True, "higher version retirement was not accepted")
                process.wait(timeout=10)
                require(process.returncode == 0, f"retired server exited with code {process.returncode}")
                return

            opened = post_json(
                endpoint + "/api/console/window-session",
                {"action": "open", "sessionId": "integration-window"},
            )
            require(opened["activeSessions"] == 1, "live server did not register the window")
            require("version" not in opened, "legacy window would reload and discard an unsent transfer draft")
            current = post_json(endpoint + "/api/console/window-session",
                                {"action": "heartbeat", "sessionId": "integration-window", "uiVersion": "1.0.28"})
            require(current.get("version") == json.loads((ROOT / "app-manifest.json").read_text(encoding="utf-8"))["version"],
                    "draft-aware window did not receive the real update version")
            malformed = post_json(endpoint + "/api/console/window-session",
                                  {"action": "heartbeat", "sessionId": "integration-window", "uiVersion": {"invalid": True}})
            require("version" not in malformed, "malformed UI identity enabled an automatic reload")
            post_json(
                endpoint + "/api/console/window-session",
                {"action": "close", "sessionId": "integration-window"},
            )
            process.wait(timeout=10)
            require(process.returncode == 0, f"live server exited with code {process.returncode}")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)


def check_device_overview_startup():
    import world_console

    saved_state = {"href": "music.html", "lastModule": "music", "order": ["music", "workspace"]}
    with mock.patch.object(world_console, "read_console_state", return_value=saved_state), \
            mock.patch.object(world_console, "write_console_state") as write_state:
        for edition in ("developer", "public"):
            with mock.patch.dict(world_console.CONSOLE_CONFIG, {"edition": edition}):
                url = world_console.console_start_url(8898)
                require("/workspace.html?" in url and "consoleView=work" in url,
                        f"{edition} daily entry did not open task incubator")
        with mock.patch.dict(world_console.CONSOLE_CONFIG, {"edition": "lite"}):
            require("/music.html?edition=lite" in world_console.console_start_url(8898),
                    "lite edition lost its supported saved module")
        write_state.assert_not_called()
        require(saved_state["lastModule"] == "music", "startup overwrote the user's module settings")


def check_main_instance_reuse():
    import world_console

    for running_version in ("1.0.8", "1.0.9"):
        for no_browser in (False, True):
            instance = {"port": 19899, "runtime": {"version": running_version}}
            arguments = ["world_console.py", "--port", "19898", "--edition", "developer", "--replace-window"]
            if no_browser:
                arguments.append("--no-browser")
            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(sys, "argv", arguments))
                stack.enter_context(mock.patch.object(world_console, "APP_VERSION", "1.0.8"))
                stack.enter_context(mock.patch.dict(world_console.CONSOLE_CONFIG, {}, clear=False))
                gate = stack.enter_context(mock.patch.object(world_console, "StartupLock"))
                find = stack.enter_context(mock.patch.object(world_console, "find_running_console", return_value=instance))
                retire = stack.enter_context(mock.patch.object(world_console, "retire_older_instance"))
                choose_port = stack.enter_context(mock.patch.object(world_console, "pick_port"))
                server = stack.enter_context(mock.patch.object(world_console, "ConsoleHTTPServer"))
                window = stack.enter_context(mock.patch.object(world_console, "open_console_window"))
                world_console.main()
                gate.assert_called_once_with(world_console.USER_DATA_DIR, 19898)
                find.assert_called_once_with(19898, world_console.USER_DATA_DIR,
                                             world_console.INSTALLATION_STATE.get("installationId", ""))
                retire.assert_not_called()
                choose_port.assert_not_called()
                server.assert_not_called()
                if no_browser:
                    window.assert_not_called()
                else:
                    window.assert_called_once_with(world_console.console_start_url(19899), replace=False)


def check_main_older_handoff():
    import world_console

    instance = {"port": 19899, "runtime": {"version": "1.0.7"}}
    for supported in (True, False):
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, "argv", ["world_console.py", "--port", "19898"]))
            stack.enter_context(mock.patch.object(sys, "stdout", io.StringIO()))
            stack.enter_context(mock.patch.object(world_console, "APP_VERSION", "1.0.8"))
            stack.enter_context(mock.patch.object(world_console, "ACTIVE_SERVER", None))
            stack.enter_context(mock.patch.dict(world_console.CONSOLE_CONFIG, {}, clear=False))
            stack.enter_context(mock.patch.object(world_console, "StartupLock"))
            stack.enter_context(mock.patch.object(world_console, "find_running_console", return_value=instance))
            retire = stack.enter_context(mock.patch.object(world_console, "retire_older_instance"))
            if not supported:
                retire.side_effect = world_console.ConsoleInstanceError("legacy handoff unavailable")
            choose_port = stack.enter_context(mock.patch.object(world_console, "pick_port"))
            server = stack.enter_context(mock.patch.object(world_console, "ConsoleHTTPServer"))
            thread = stack.enter_context(mock.patch.object(world_console.threading, "Thread"))
            companion = stack.enter_context(mock.patch.object(world_console, "PHONE_COMPANION"))
            workflow = stack.enter_context(mock.patch.object(world_console, "WORKFLOW_SERVICE"))
            backend_thread = mock.Mock()
            backend_thread.is_alive.return_value = False
            restore_thread = mock.Mock()
            def make_thread(*args, **kwargs):
                if kwargs.get("target") == server.return_value.serve_forever:
                    return backend_thread
                if kwargs.get("target") == companion.restore:
                    return restore_thread
                raise AssertionError("handoff started an unexpected background thread")
            thread.side_effect = make_thread
            window = stack.enter_context(mock.patch.object(world_console, "open_console_window"))
            sessions = stack.enter_context(mock.patch.object(world_console, "CONSOLE_WINDOW_SESSIONS"))
            events = []
            retire.side_effect = (lambda *_: events.append("retired")) if supported else retire.side_effect
            backend_thread.start.side_effect = lambda: events.append("serving")
            window.side_effect = lambda *_args, **_kwargs: events.append("window")
            try:
                world_console.main()
            except world_console.ConsoleInstanceError:
                require(not supported, "supported retirement unexpectedly failed")
            else:
                require(supported, "unsupported retirement was silently ignored")
            retire.assert_called_once_with(instance, "1.0.8")
            choose_port.assert_not_called()
            if supported:
                server.assert_called_once_with(("127.0.0.1", 19899), world_console.ConsoleHandler)
                window.assert_called_once_with(world_console.console_start_url(19899), replace=True)
                require(events == ["retired", "serving", "window"],
                        "handoff opened a window before the old server retired and the new server started")
                server.return_value.server_close.assert_called_once_with()
                sessions.stop.assert_called_once_with()
                backend_thread.start.assert_called_once_with()
                restore_thread.start.assert_called_once_with()
                companion.restore.assert_not_called()
                companion.shutdown.assert_called_once_with()
                workflow.start.assert_called_once_with()
                workflow.shutdown.assert_called_once_with()
                require(world_console.ACTIVE_SERVER is None, "finished backend left ACTIVE_SERVER registered")
            else:
                server.assert_not_called()
                thread.assert_not_called()
                window.assert_not_called()


def check_retirement_guards():
    import world_console

    with (
        mock.patch.object(world_console, "APP_VERSION", "1.0.8"),
        mock.patch.object(world_console, "RUNTIME_INSTANCE_ID", "current-runtime-instance"),
        mock.patch.object(world_console.threading, "Timer") as timer,
        mock.patch.object(world_console, "shutdown_active_server") as shutdown,
    ):
        for payload in (
            {"expectedInstanceId": "other-runtime-instance", "version": "1.0.9"},
            {"expectedInstanceId": "current-runtime-instance", "version": "1.0.8"},
            {"expectedInstanceId": "current-runtime-instance", "version": "1.0.7"},
            {"expectedInstanceId": "current-runtime-instance", "version": "not-a-version"},
        ):
            try:
                world_console.retire_console_instance(payload)
            except (ValueError, world_console.ConsoleInstanceError):
                pass
            else:
                raise AssertionError("wrong runtime or non-newer version scheduled retirement")
        timer.assert_not_called()
        shutdown.assert_not_called()
        accepted = world_console.retire_console_instance(
            {"expectedInstanceId": "current-runtime-instance", "version": "1.0.9"},
        )
        require(accepted.get("accepted") is True, "newer matching instance was not accepted")
        timer.assert_called_once_with(0.2, shutdown)
        require(timer.return_value.daemon is True, "retirement timer could keep the old process alive")
        timer.return_value.start.assert_called_once_with()
        shutdown.assert_not_called()

    # Exercise the local-only guard without binding a LAN socket or contacting a real device.
    handler = object.__new__(world_console.ConsoleHandler)
    handler.client_address = ("203.0.113.8", 49152)
    handler.send_json = mock.Mock()
    require(handler.require_local_request() is False, "non-loopback caller passed the retirement boundary")
    require(handler.send_json.call_args.kwargs.get("status") == 403, "non-loopback caller was not denied")


def check_portable_and_lan_launch():
    import world_console
    for platform, url in (("linux", "http://127.0.0.1:8898/workspace.html"),
                          ("win32", "http://192.168.1.20:8898/workspace.html")):
        with mock.patch.object(world_console.sys, "platform", platform), \
                mock.patch.object(world_console, "start_console_browser") as start, \
                mock.patch.object(world_console, "launch_or_focus_console_window") as native:
            require(world_console.open_console_window(url)["launched"], "portable/LAN browser did not open")
            start.assert_called_once_with(url)
            native.assert_not_called()

    stopped = threading.Event()
    service = ConsoleWindowSessionService(stopped.set, close_delay_seconds=0.04)
    try:
        service.update({"action": "open", "sessionId": "old-owned-window"})
        with service.launching():
            service.update({"action": "close", "sessionId": "old-owned-window"})
            time.sleep(0.12)
            require(not stopped.is_set(), "replacement closed the backend before the new page opened")
            service.update({"action": "open", "sessionId": "new-owned-window"})
        require(not stopped.is_set(), "the replacement window did not retain its backend")
        service.update({"action": "close", "sessionId": "new-owned-window"})
        require(stopped.wait(1), "final replacement window close did not stop the backend")
    finally:
        service.stop()


def main():
    # Importing the application initializes its data paths; never let unit checks
    # initialize the user's real source/installed cache or desktop-layout data.
    with tempfile.TemporaryDirectory(prefix="codex-lifecycle-unit-") as temporary:
        isolated = Path(temporary)
        (isolated / ".cache-migrated-v0.3").write_text("test\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {
            "CODEX_CONTROL_DATA_DIR": temporary,
            "CODEX_CONTROL_DESKTOP_LAYOUT_DATA_DIR": str(isolated / "desktop-layout"),
            "CODEX_CONTROL_DESKTOP_LAYOUT_CURRENT": str(isolated / "desktop-layout" / "current.json"),
            "CODEX_CONTROL_DESKTOP_LAYOUT_SCRIPT": str(isolated / "disabled.ps1"),
            "CODEX_CONTROL_DESKTOP_LAYOUT_STARTUP_FILE": str(isolated / "Startup" / "disabled.vbs"),
        }):
            check_device_overview_startup()
            check_main_instance_reuse()
            check_main_older_handoff()
            check_retirement_guards()
            check_portable_and_lan_launch()
            check_session_service()
            check_live_server()
            check_live_server(retire=True)
    print("PASS Codex Console window lifecycle")


if __name__ == "__main__":
    main()
