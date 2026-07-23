#!/usr/bin/env python3
"""Verify clean-install defaults and per-device layout preservation."""

import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = json.loads((ROOT / "release-defaults.json").read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def available_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def request_json(url, payload=None):
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST" if body else "GET")
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def request_text(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.read().decode("utf-8")


def start_server(data_dir, port):
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / ".cache-migrated-v0.3").write_text("test\n", encoding="utf-8")
    environment = os.environ.copy()
    environment["CODEX_CONTROL_DATA_DIR"] = str(data_dir)
    environment["CODEX_CONTROL_MUSIC_DIR"] = str(ROOT / "public-music")
    environment["CODEX_CONTROL_WALLPAPERS_DIR"] = str(ROOT / "wallpapers")
    process = subprocess.Popen(
        [
            os.environ.get("PYTHON", "python"),
            str(ROOT / "world_console.py"),
            "--host", "127.0.0.1",
            "--port", str(port),
            "--edition", "public",
            "--no-browser",
        ],
        cwd=str(ROOT),
        env=environment,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"server exited early: {process.returncode}")
        try:
            request_json(f"http://127.0.0.1:{port}/api/release-defaults")
            return process
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            time.sleep(0.15)
    process.terminate()
    raise AssertionError("server did not become ready")


def stop_server(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def main():
    with tempfile.TemporaryDirectory(prefix="codex-release-defaults-") as temporary:
        data_dir = Path(temporary) / "device"
        port = available_port()
        base_url = f"http://127.0.0.1:{port}"
        process = start_server(data_dir, port)
        try:
            served_defaults = request_json(f"{base_url}/api/release-defaults")
            require(served_defaults == DEFAULTS, "release defaults endpoint changed the snapshot")
            music_state = request_json(f"{base_url}/api/music").get("state") or {}
            require(music_state == DEFAULTS["music"], "clean device did not receive publisher music layout")
            console_state = request_json(f"{base_url}/api/console/state").get("state") or {}
            for key, expected in DEFAULTS["modules"].items():
                require(console_state.get(key) == expected, f"clean device module {key} is incorrect")
            require(console_state.get("href") == "music.html", "clean device does not launch Music")

            custom_music = {
                "tiers": {"Toxic.mp3": "first"},
                "order": ["Toxic.mp3", "Outrun.mp3"],
                "promotedLibraryTracks": {},
                "selectedTrackPath": "Toxic.mp3",
            }
            custom_modules = {
                "order": ["music", "wallpaper", "workspace", "blender", "randomrealm", "steamwork", "unity", "manager"],
                "archive": ["blender"],
                "deepArchive": ["manager"],
                "deleted": [],
                "lastModule": "music",
            }
            request_json(f"{base_url}/api/music/state", custom_music)
            request_json(f"{base_url}/api/console/state", custom_modules)
        finally:
            stop_server(process)

        process = start_server(data_dir, port)
        try:
            music_state = request_json(f"{base_url}/api/music").get("state") or {}
            require(music_state == custom_music, "existing device music layout was overwritten")
            console_state = request_json(f"{base_url}/api/console/state").get("state") or {}
            for key, expected in custom_modules.items():
                require(console_state.get(key) == expected, f"existing device module {key} was overwritten")
            bootstrap = request_text(f"{base_url}/api/release-defaults.js")
            require("window.CODEX_RELEASE_DEFAULTS=" in bootstrap, "release defaults bootstrap is missing")
            require("window.CODEX_DEVICE_LAYOUT=" in bootstrap, "device layout bootstrap is missing")
            require(
                json.dumps(custom_modules["order"], ensure_ascii=False, separators=(",", ":")) in bootstrap,
                "device layout bootstrap did not preserve the custom order",
            )
        finally:
            stop_server(process)

    print("PASS release defaults and per-device layout preservation")


if __name__ == "__main__":
    main()
