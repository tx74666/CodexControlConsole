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
EXPECTED_MUSIC = {
    "Airborne", "Around the World", "Dancin", "Final Step", "Fire Inside",
    "Get Lucky", "House of Memories", "Liquid Roller", "Luminescence",
    "Never Be Alone", "Never Slow Me Down", "Outrun", "Redline", "Stasis", "Toxic",
}
RETIRED_MUSIC = {
    "Codex - Glass Horizon.wav",
    "Codex - Night Workspace.wav",
    "Codex - Quiet Circuit.wav",
}
RETIRED_WALLPAPERS = {
    "elaina-wandering-witch-online.jpg",
    "kobayashi-dragon-maid-online.jpg",
}


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


def verify_packaged_app(executable, app_dir, data_dir):
    port = available_port()
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
        tracks = music.get("tracks") or []
        require(len(tracks) == 15, "installation did not seed all 15 tracks")
        require({item.get("name") for item in tracks} == EXPECTED_MUSIC, "installed track names are incorrect")
        require(len(wallpapers.get("wallpapers") or []) == 8, "installation did not seed all eight wallpapers")
        require(len(list((data_dir / "music").glob("*.mp3"))) == 15, "tracks were not copied to device data")
        require(len(list((data_dir / "wallpapers").glob("*.jpg"))) == 8, "wallpapers were not copied to device data")
        require(not any((data_dir / "music" / name).exists() for name in RETIRED_MUSIC), "retired starter music remains")
        require(
            not any((data_dir / "wallpapers" / name).exists() for name in RETIRED_WALLPAPERS),
            "retired wallpaper names remain",
        )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=4)


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

    with tempfile.TemporaryDirectory(prefix="codex-console-clean-") as temporary:
        root = Path(temporary)
        verify_packaged_app(executable, app_dir, root / "clean-data")

        upgrade_data = root / "upgrade-data"
        upgrade_music = upgrade_data / "music"
        upgrade_music.mkdir(parents=True)
        for name in RETIRED_MUSIC:
            (upgrade_music / name).write_bytes(b"retired starter track")
        (upgrade_music / ".codex-media-migrated").write_text("0.5.8\n", encoding="utf-8")
        upgrade_wallpapers = upgrade_data / "wallpapers"
        upgrade_wallpapers.mkdir(parents=True)
        for name in RETIRED_WALLPAPERS:
            (upgrade_wallpapers / name).write_bytes(b"retired wallpaper")
        (upgrade_wallpapers / ".codex-media-migrated").write_text("0.5.8\n", encoding="utf-8")
        verify_packaged_app(executable, app_dir, upgrade_data)

    print("PASS clean install and v0.5.8 upgrade (15 tracks, 8 wallpapers)")


if __name__ == "__main__":
    main()
