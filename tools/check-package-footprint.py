import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def available_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def read_json(url, timeout=1):
    request = urllib.request.Request(url, headers={"User-Agent": "CodexPackageCheck/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(1024 * 1024).decode("utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--app-dir",
        default=str(ROOT / "build" / "console-installer" / "dist" / "Codex Console"),
    )
    parser.add_argument("--startup-limit", type=float, default=20.0)
    args = parser.parse_args()

    app_dir = Path(args.app_dir).resolve()
    internal = app_dir / "_internal"
    executable = app_dir / "Codex Console.exe"
    require(executable.is_file(), "packaged Codex Console.exe is missing")
    require(not (internal / "_tcl_data").exists(), "the unused Tcl runtime is still packaged")
    require(not (internal / "_tk_data").exists(), "the unused Tk runtime is still packaged")
    unpacked_yt_dlp = list((internal / "yt_dlp").rglob("*.py")) if (internal / "yt_dlp").exists() else []
    require(len(unpacked_yt_dlp) <= 10, "yt-dlp source files are duplicated outside the PyInstaller archive")

    port = available_port()
    environment = os.environ.copy()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    with tempfile.TemporaryDirectory(prefix="codex-package-check-") as temp_dir:
        environment["CODEX_CONTROL_DATA_DIR"] = temp_dir
        environment["CODEX_CONTROL_MUSIC_DIR"] = str(internal / "music")
        environment["CODEX_CONTROL_WALLPAPERS_DIR"] = str(internal / "wallpapers")
        started = time.perf_counter()
        process = subprocess.Popen(
            [str(executable), "--host", "127.0.0.1", "--port", str(port), "--no-browser"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
            creationflags=creationflags,
        )
        try:
            config = None
            deadline = started + max(30.0, args.startup_limit)
            while time.perf_counter() < deadline and process.poll() is None:
                try:
                    config = read_json(f"http://127.0.0.1:{port}/api/console/config")
                    break
                except (OSError, ValueError, json.JSONDecodeError):
                    time.sleep(0.1)
            startup_seconds = time.perf_counter() - started
            require(config is not None, "the packaged local service did not start")
            require(startup_seconds <= args.startup_limit, f"packaged startup took {startup_seconds:.2f}s")
            package = read_json(f"http://127.0.0.1:{port}/api/console/package-check", timeout=30)
            require(package.get("ytDlp"), "the packaged YouTube importer cannot load yt-dlp")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

    file_count = sum(1 for item in internal.rglob("*") if item.is_file())
    print(
        "PASS lean package "
        f"({file_count} files, {len(unpacked_yt_dlp)} unpacked yt-dlp sources, "
        f"startup {startup_seconds:.2f}s)"
    )


if __name__ == "__main__":
    main()
