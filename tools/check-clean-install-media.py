import argparse
import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def available_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def read_json(url):
    with urllib.request.urlopen(url, timeout=4) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--app-dir",
        type=Path,
        default=ROOT / "build" / "console-installer" / "dist" / "Codex Console",
    )
    args = parser.parse_args()
    app_dir = args.app_dir.resolve()
    executable = app_dir / "Codex Console.exe"
    require(executable.is_file(), f"packaged executable is missing: {executable}")

    port = available_port()
    with tempfile.TemporaryDirectory(prefix="codex-console-clean-") as temporary:
        data_dir = Path(temporary) / "data"
        environment = os.environ.copy()
        environment["CODEX_CONTROL_DATA_DIR"] = str(data_dir)
        environment.pop("CODEX_CONTROL_MUSIC_DIR", None)
        environment.pop("CODEX_CONTROL_WALLPAPERS_DIR", None)
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            [str(executable), "--host", "127.0.0.1", "--port", str(port), "--no-browser"],
            cwd=str(app_dir),
            env=environment,
            creationflags=creation_flags,
        )
        try:
            deadline = time.monotonic() + 45
            music = None
            wallpapers = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise AssertionError(f"packaged app exited early: {process.returncode}")
                try:
                    music = read_json(f"http://127.0.0.1:{port}/api/music")
                    wallpapers = read_json(f"http://127.0.0.1:{port}/api/wallpapers")
                    break
                except (OSError, urllib.error.URLError, json.JSONDecodeError):
                    time.sleep(0.25)
            require(music is not None and wallpapers is not None, "packaged app did not become ready")
            require(len(music.get("tracks") or []) == 3, "clean install did not seed three starter tracks")
            require(len(wallpapers.get("wallpapers") or []) == 6, "clean install did not seed six wallpapers")
            require(len(list((data_dir / "music").glob("*.wav"))) == 3, "starter tracks were not copied to device data")
            require(len(list((data_dir / "wallpapers").glob("*.jpg"))) == 6, "wallpapers were not copied to device data")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=4)

    print("PASS clean-install media (3 starter tracks, 6 wallpapers)")


if __name__ == "__main__":
    main()
