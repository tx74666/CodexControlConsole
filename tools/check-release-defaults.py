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
                "layoutVersion": DEFAULTS["music"]["layoutVersion"],
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

        broken_data_dir = Path(temporary) / "broken-device"
        broken_cache = broken_data_dir / "cache"
        broken_cache.mkdir(parents=True)
        broken_state = {
            "tiers": {},
            "order": [
                "Liquid Roller.mp3",
                "Airborne.mp3",
                "Never Be Alone.mp3",
                "Stasis.mp3",
                "Final Step.mp3",
                "Luminescence.mp3",
                "Dancin.mp3",
                "House of Memories.mp3",
                "Toxic.mp3",
                "Get Lucky.mp3",
                "Outrun.mp3",
                "Fire Inside.mp3",
                "Never Slow Me Down.mp3",
                "Around the World.mp3",
                "Redline.mp3",
                "Ma rose éternelle.mp3",
            ],
            "promotedLibraryTracks": {},
            "selectedTrackPath": "Redline.mp3",
        }
        (broken_cache / "music_state.json").write_text(
            json.dumps(broken_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        port = available_port()
        base_url = f"http://127.0.0.1:{port}"
        process = start_server(broken_data_dir, port)
        try:
            migrated = request_json(f"{base_url}/api/music").get("state") or {}
            require(migrated.get("tiers") == DEFAULTS["music"]["tiers"], "broken public tiers were not repaired")
            require(migrated.get("order") == DEFAULTS["music"]["order"], "broken public order was not repaired")
            require(migrated.get("selectedTrackPath") == "Redline.mp3", "selected track was lost during repair")
            require(
                (broken_cache / "music_state.previous.json").is_file(),
                "broken public state was not backed up before repair",
            )
        finally:
            stop_server(process)

        legacy_custom_data = Path(temporary) / "legacy-custom-device"
        legacy_custom_cache = legacy_custom_data / "cache"
        legacy_custom_cache.mkdir(parents=True)
        legacy_custom = {
            "tiers": {"Toxic.mp3": "first"},
            "order": ["Toxic.mp3", "Outrun.mp3"],
            "promotedLibraryTracks": {},
            "selectedTrackPath": "Toxic.mp3",
        }
        (legacy_custom_cache / "music_state.json").write_text(
            json.dumps(legacy_custom, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        port = available_port()
        base_url = f"http://127.0.0.1:{port}"
        process = start_server(legacy_custom_data, port)
        try:
            preserved = request_json(f"{base_url}/api/music").get("state") or {}
            require(preserved.get("tiers") == legacy_custom["tiers"], "custom tiers were overwritten")
            require(preserved.get("order") == legacy_custom["order"], "custom order was overwritten")
            require(
                preserved.get("layoutVersion") == DEFAULTS["music"]["layoutVersion"],
                "custom layout was not marked as migrated",
            )
        finally:
            stop_server(process)

    print("PASS release defaults and per-device layout preservation")


if __name__ == "__main__":
    main()
