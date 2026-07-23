import argparse
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_WALLPAPERS = {
    "blue-lake-boats.jpg",
    "calm-mountain-lake.jpg",
    "dragon-maid.jpg",
    "quiet-forest-aerial.jpg",
    "snow-water-mountains.jpg",
    "soft-mountain-sun.jpg",
    "wandering-witch.jpg",
}
PUBLIC_MUSIC = {
    "Airborne.mp3",
    "Around the World.mp3",
    "Dancin.mp3",
    "Final Step.mp3",
    "Fire Inside.mp3",
    "Get Lucky.mp3",
    "House of Memories.mp3",
    "Liquid Roller.mp3",
    "Luminescence.mp3",
    "Ma rose éternelle.mp3",
    "Never Be Alone.mp3",
    "Never Slow Me Down.mp3",
    "Outrun.mp3",
    "Redline.mp3",
    "Stasis.mp3",
    "Toxic.mp3",
}
PUBLIC_LYRICS = {
    "Around the World.lrc",
    "Dancin.lrc",
    "Get Lucky.lrc",
    "House of Memories.lrc",
    "Ma rose éternelle.lrc",
    "Ma rose éternelle.en.lrc",
    "Ma rose éternelle.zh.lrc",
    "Never Be Alone.lrc",
    "Toxic.lrc",
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
        'IconFilename: "{app}\\Codex Console.exe"' in desktop_line,
        "shortcut icon is not pinned to the installed executable",
    )
    require("Check: ShouldCreateDesktopShortcut" in desktop_line, "desktop shortcut is overwritten during upgrades")
    require(
        'Type: files; Name: "{autodesktop}\\Codex Console.lnk"' not in installer,
        "desktop shortcut is deleted during upgrades",
    )
    require(
        "not FileExists(ExpandConstant('{autodesktop}\\Codex Console.lnk'))" in installer,
        "desktop shortcut preservation check is missing",
    )
    require(
        "'/F /IM \"Codex Console.exe\"'" in installer,
        "Console Setup does not close the previous installed process automatically",
    )
    require('Filename: "{sys}\\ie4uinit.exe"; Parameters: "-show"' in installer, "Windows icon cache is not refreshed")
    require(
        'Type: filesandordirs; Name: "{app}\\_internal\\music"' in installer,
        "obsolete packaged music is not cleared during upgrade",
    )
    require(
        'Type: filesandordirs; Name: "{app}\\_internal\\wallpapers"' in installer,
        "obsolete packaged wallpapers are not cleared during upgrade",
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
    defaults_files = list(app_dir.rglob("release-defaults.json"))
    require(len(defaults_files) == 1, "release defaults are missing or duplicated")
    release_defaults = json.loads(defaults_files[0].read_text(encoding="utf-8"))
    default_music = release_defaults.get("music") or {}
    require(set(default_music.get("order") or []) == PUBLIC_MUSIC, "release music order is incomplete")
    require(len(default_music.get("order") or []) == len(PUBLIC_MUSIC), "release music order contains duplicates")
    require(
        set((default_music.get("tiers") or {}).values()) <= {"first", "second", "third"},
        "release music tiers contain an invalid group",
    )
    default_modules = release_defaults.get("modules") or {}
    expected_module_ids = {"manager", "workspace", "blender", "unity", "steamwork", "randomrealm", "music", "wallpaper"}
    module_order = default_modules.get("order") or []
    archive = default_modules.get("archive") or []
    deep_archive = default_modules.get("deepArchive") or []
    deleted = default_modules.get("deleted") or []
    require(set(module_order) == expected_module_ids, "release module order is incomplete")
    require(len(module_order) == len(expected_module_ids), "release module order contains duplicates")
    require(not (set(archive) & set(deep_archive)), "release Archive levels overlap")
    require(not ((set(archive) | set(deep_archive)) & set(deleted)), "deleted modules remain archived")
    visible_modules = [
        module_id for module_id in module_order
        if module_id not in set(archive) | set(deep_archive) | set(deleted)
    ]
    require(visible_modules, "release layout has no visible module")
    require(default_modules.get("lastModule") in visible_modules, "release default page is hidden")

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

    audio_extensions = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}
    music = [
        path
        for path in app_dir.rglob("*")
        if path.is_file() and "music" in path.parts and path.suffix.lower() in audio_extensions
    ]
    music_names = {path.name for path in music}
    require(music_names == PUBLIC_MUSIC, f"public music does not match the release allowlist: {sorted(music_names)}")
    for path in music:
        require(path.suffix.lower() == ".mp3", f"public track is not MP3: {path.name}")
        require(path.stat().st_size > 1_000_000, f"public track is unexpectedly small: {path.name}")
        require(" - " not in path.stem, f"public track still exposes an artist prefix: {path.name}")
        metadata = path.read_bytes()[:1_048_576]
        require(b"TPE1" not in metadata and b"TPE2" not in metadata, f"artist metadata remains in {path.name}")
        require(b"APIC" not in metadata, f"embedded artwork remains in {path.name}")

    lyrics = [
        path
        for path in app_dir.rglob("*.lrc")
        if path.is_file() and "music" in path.parts
    ]
    require({path.name for path in lyrics} == PUBLIC_LYRICS, "packaged lyrics do not match the music set")

    packaged_audio = [path for path in app_dir.rglob("*") if path.is_file() and path.suffix.lower() in audio_extensions]
    require(set(packaged_audio) == set(music), "an audio file was packaged outside the public music directory")
    personal_extensions = {".blend"}
    personal_files = [path for path in app_dir.rglob("*") if path.is_file() and path.suffix.lower() in personal_extensions]
    require(not personal_files, f"personal media entered the public package: {personal_files[:3]}")
    require(not list(app_dir.rglob("feedback-admin.json")), "feedback administrator credentials entered the package")
    require(not list(app_dir.rglob("desktop-layout-*.json")), "a device desktop layout entered the package")

    print(f"PASS Console package resources ({len(wallpapers)} wallpapers, {len(music)} tracks)")


if __name__ == "__main__":
    main()
