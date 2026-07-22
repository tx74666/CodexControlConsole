#!/usr/bin/env python3

import os
from pathlib import Path
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    with tempfile.TemporaryDirectory(prefix="codex-media-sync-") as temp:
        root = Path(temp)
        os.environ["CODEX_CONTROL_DATA_DIR"] = str(root / "data")
        os.environ["CODEX_CONTROL_MUSIC_DIR"] = str(root / "active-music")
        os.environ["CODEX_CONTROL_WALLPAPERS_DIR"] = str(root / "active-wallpapers")
        sys.path.insert(0, str(PROJECT_ROOT))

        import world_console as console

        require(console.display_music_name("Airborne") == "Airborne", "clean Airborne title changed")
        require(console.display_music_name("A8 - Airborne") == "Airborne", "legacy A8 prefix remains")
        require(
            console.display_music_name("Asphalt 8 Airborne - Airborne - Official Soundtrack") == "Airborne",
            "legacy Asphalt title was not cleaned",
        )

        music_source = root / "package-music"
        music_target = root / "music"
        music_source.mkdir()
        music_target.mkdir()
        (music_source / "Get Lucky.mp3").write_bytes(b"bundled-get-lucky")
        (music_source / "Get Lucky.lrc").write_text("[00:00.00]Get Lucky\n", encoding="utf-8")
        (music_source / "Airborne.mp3").write_bytes(b"bundled-airborne")
        legacy_track = music_target / "Daft Punk - Get Lucky (Official Audio).mp3"
        legacy_track.write_bytes(b"existing-get-lucky")
        custom_track = music_target / "My Custom Track.mp3"
        custom_track.write_bytes(b"custom")

        first_music = console.sync_builtin_media(
            "music",
            music_source=music_source,
            wallpaper_source=root / "missing-wallpapers",
            music_target=music_target,
            wallpaper_target=root / "wallpapers",
        )
        require(first_music["added"] == 1, "only the missing bundled song should be copied")
        require(first_music["lyricsAdded"] == 1, "lyrics should be added beside the existing legacy song")
        require(first_music["music"]["present"] == 2, "both bundled song identities should be present")
        require(legacy_track.read_bytes() == b"existing-get-lucky", "existing audio was overwritten")
        require(not (music_target / "Get Lucky.mp3").exists(), "legacy song identity was duplicated")
        require(custom_track.exists(), "custom music was removed")
        require((music_target / "Daft Punk - Get Lucky (Official Audio).lrc").exists(), "legacy song did not receive lyrics")

        second_music = console.sync_builtin_media(
            "music",
            music_source=music_source,
            wallpaper_source=root / "missing-wallpapers",
            music_target=music_target,
            wallpaper_target=root / "wallpapers",
        )
        require(second_music["added"] == 0, "second music sync should be idempotent")
        require(second_music["lyricsAdded"] == 0, "second music sync should not rewrite lyrics")

        wallpaper_source = root / "package-wallpapers"
        wallpaper_target = root / "wallpapers"
        wallpaper_source.mkdir()
        wallpaper_target.mkdir(exist_ok=True)
        (wallpaper_source / "blue-lake-boats.jpg").write_bytes(b"bundled-blue")
        (wallpaper_source / "calm-mountain-lake.jpg").write_bytes(b"bundled-calm")
        existing_wallpaper = wallpaper_target / "blue-lake-boats.jpg"
        existing_wallpaper.write_bytes(b"existing-blue")
        custom_wallpaper = wallpaper_target / "my-wallpaper.jpg"
        custom_wallpaper.write_bytes(b"custom")

        first_wallpapers = console.sync_builtin_media(
            "wallpapers",
            music_source=root / "missing-music",
            wallpaper_source=wallpaper_source,
            music_target=root / "unused-music",
            wallpaper_target=wallpaper_target,
        )
        require(first_wallpapers["added"] == 1, "only the missing bundled wallpaper should be copied")
        require(first_wallpapers["wallpapers"]["present"] == 2, "both bundled wallpapers should be present")
        require(existing_wallpaper.read_bytes() == b"existing-blue", "existing wallpaper was overwritten")
        require(custom_wallpaper.exists(), "custom wallpaper was removed")

        second_wallpapers = console.sync_builtin_media(
            "wallpapers",
            music_source=root / "missing-music",
            wallpaper_source=wallpaper_source,
            music_target=root / "unused-music",
            wallpaper_target=wallpaper_target,
        )
        require(second_wallpapers["added"] == 0, "second wallpaper sync should be idempotent")

    print("PASS built-in media sync is additive, identity-aware, and idempotent")


if __name__ == "__main__":
    main()
