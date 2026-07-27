import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request


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


def post_json(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=4) as response:
        return json.loads(response.read().decode("utf-8"))


def check_session_service():
    shutdown = threading.Event()
    service = ConsoleWindowSessionService(
        shutdown.set,
        close_delay_seconds=0.12,
        stale_after_seconds=1.0,
        sweep_interval_seconds=0.05,
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

    stale_shutdown = threading.Event()
    stale_service = ConsoleWindowSessionService(
        stale_shutdown.set,
        close_delay_seconds=0.05,
        stale_after_seconds=0.12,
        sweep_interval_seconds=0.03,
    )
    try:
        stale_service.update({"action": "open", "sessionId": "stale-window"})
        require(stale_shutdown.wait(1.0), "an abandoned window session was not cleaned up")
    finally:
        stale_service.stop()

    try:
        service.update({"action": "invalid", "sessionId": "window-one"})
    except ValueError:
        pass
    else:
        raise AssertionError("invalid window actions were accepted")


def check_live_server():
    port = available_port()
    environment = os.environ.copy()
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with tempfile.TemporaryDirectory(prefix="codex-console-lifecycle-") as temporary:
        environment["CODEX_CONTROL_DATA_DIR"] = temporary
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

            opened = post_json(
                endpoint + "/api/console/window-session",
                {"action": "open", "sessionId": "integration-window"},
            )
            require(opened["activeSessions"] == 1, "live server did not register the window")
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


def main():
    check_session_service()
    check_live_server()
    print("PASS Codex Console window lifecycle")


if __name__ == "__main__":
    main()
