import argparse
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_WALLPAPERS = {
    "blue-lake-boats.jpg",
    "calm-mountain-lake.jpg",
    "palm-sky-reflection.jpg",
    "quiet-forest-aerial.jpg",
    "snow-water-mountains.jpg",
    "soft-mountain-sun.jpg",
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check_ico(path):
    payload = path.read_bytes()
    require(len(payload) >= 6, f"icon is truncated: {path}")
    reserved, icon_type, count = struct.unpack_from("<HHH", payload, 0)
    require(reserved == 0 and icon_type == 1 and count >= 6, f"icon directory is invalid: {path}")
    require(len(payload) >= 6 + count * 16, f"icon directory is incomplete: {path}")
    for index in range(count):
        size, offset = struct.unpack_from("<II", payload, 6 + index * 16 + 8)
        require(size > 0 and offset >= 6 + count * 16, f"icon entry {index} is invalid")
        require(offset + size <= len(payload), f"icon entry {index} points beyond the file")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--app-dir",
        type=Path,
        default=ROOT / "build" / "console-installer" / "dist" / "Codex Console",
    )
    args = parser.parse_args()

    check_ico(ROOT / "pc-console-icon.ico")
    require(
        (ROOT / "pc-console-icon.ico").read_bytes() == (ROOT / "codex-resource-icon.ico").read_bytes(),
        "desktop executable is not using the classic Codex icon",
    )

    installer = (ROOT / "installer" / "CodexControlConsole.iss").read_text(encoding="utf-8")
    desktop_line = next(
        (line for line in installer.splitlines() if 'Name: "{autodesktop}\\Codex Console"' in line),
        "",
    )
    require(desktop_line, "desktop shortcut is missing from Setup")
    require("Tasks:" not in desktop_line, "desktop shortcut is optional instead of guaranteed")
    require(
        'IconFilename: "{app}\\_internal\\codex-resource-icon.ico"' in desktop_line,
        "shortcut icon is not pinned to the classic Codex icon",
    )
    require('Name: "{group}\\Uninstall Codex Console"; Filename: "{uninstallexe}"' in installer, "Start menu uninstaller is missing")
    require('#define UserDataDir "{localappdata}\\CodexControlConsole"' in installer, "default Console data directory is not device-local")
    require('Type: filesandordirs; Name: "{#UserDataDir}"' in installer, "local Console data is not removed on uninstall")
    require('Type: files; Name: "{userstartup}\\Codex-Control-Hotkey.vbs"' in installer, "Console startup helper is not removed on uninstall")
    require('Type: filesandordirs; Name: "{app}"' not in installer, "uninstaller contains an unsafe recursive app-directory delete")

    app_dir = args.app_dir.resolve()
    require((app_dir / "Codex Console.exe").is_file(), f"packaged EXE is missing: {app_dir}")
    manifests = list(app_dir.rglob("app-manifest.json"))
    require(len(manifests) == 1, "packaged manifest is missing or duplicated")
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    require(manifest.get("edition") == "public", "release package is not the public edition")

    image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    wallpapers = [
        path
        for path in app_dir.rglob("*")
        if path.is_file() and "wallpapers" in path.parts and path.suffix.lower() in image_extensions
    ]
    wallpaper_names = {path.name for path in wallpapers}
    require(
        wallpaper_names == PUBLIC_WALLPAPERS,
        f"public wallpapers do not match the release allowlist: {sorted(wallpaper_names)}",
    )

    personal_extensions = {".mp3", ".wav", ".flac", ".m4a", ".blend"}
    personal_files = [path for path in app_dir.rglob("*") if path.is_file() and path.suffix.lower() in personal_extensions]
    require(not personal_files, f"personal media entered the public package: {personal_files[:3]}")
    require(not list(app_dir.rglob("feedback-admin.json")), "feedback administrator credentials entered the package")
    require(not list(app_dir.rglob("desktop-layout-*.json")), "a device desktop layout entered the package")

    print(f"PASS Console package resources ({len(wallpapers)} wallpapers)")


if __name__ == "__main__":
    main()
