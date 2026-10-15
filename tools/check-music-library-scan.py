"""Exercise live music catalog scans with isolated files, without importing services."""
import ast
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import tempfile
import threading
import unicodedata
import unittest
from unittest.mock import patch
import urllib.parse


ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = {
    "is_path_inside", "ensure_music_dir", "ensure_youtube_cookie_dir",
    "ensure_music_library_dir", "music_relative_path", "normalize_lyrics_language",
    "lyrics_file_language", "lyrics_language_options_from_music_path",
    "lyrics_path_from_music_path", "clean_music_stem", "display_music_name",
    "music_name_key", "music_path_name_key", "local_music_name_keys",
    "read_music_library_records", "music_track_from_path", "library_tracks_for_record",
    "public_music_library_record", "list_music_libraries",
}


def load_functions(music, source=None):
    source = source or ROOT / "world_console.py"
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS]
    if {node.name for node in nodes} != FUNCTIONS:
        raise AssertionError("production music functions are missing")
    namespace = {
        "Path": Path, "json": json, "re": re, "datetime": datetime,
        "unicodedata": unicodedata, "urllib": urllib,
        "MUSIC_DIR": music, "MUSIC_LIBRARY_DIR": music / "libraries",
        "MUSIC_LIBRARY_FILE": music.parent / "libraries.json",
        "YOUTUBE_COOKIE_DIR": music.parent / "cookies",
        "MUSIC_EXTENSIONS": {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"},
        "LYRICS_LANGUAGE_ORDER": ("fr", "en", "zh"),
        "LYRICS_LANGUAGE_LABELS": {"fr": "Français", "en": "English", "zh": "中文"},
        "MUSIC_LIBRARY_LOCK": threading.RLock(),
        "music_loudness_calibration": lambda _name: {},
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)
    return namespace


class MusicLibraryScanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="console-library-scan-")
        self.addCleanup(self.temporary.cleanup)
        self.music = (Path(self.temporary.name) / "music").resolve()
        self.music.mkdir()
        self.api = load_functions(self.music)
        self.records = []
        self.scans = 0
        original = self.api["local_music_name_keys"]

        def counted_scan():
            self.scans += 1
            return original()

        self.api["local_music_name_keys"] = counted_scan

    def write(self, relative, data=b"synthetic media, never decoded"):
        path = self.music / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def save_records(self):
        self.api["MUSIC_LIBRARY_FILE"].write_text(json.dumps(self.records), encoding="utf-8")

    def add_library(self, identifier, updated):
        relative = "libraries/" + identifier
        (self.music / relative).mkdir(parents=True)
        record = {"id": identifier, "path": relative, "updatedAt": updated, "custom": {"keep": True}}
        self.records.append(record)
        self.save_records()
        return record

    def fingerprints(self):
        return {path.relative_to(self.music.parent).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.music.parent.rglob("*") if path.is_file()}

    def test_many_libraries_share_one_live_scan_and_preserve_catalog(self):
        self.write("local/A8 - Airborne.mp3")
        for number in range(8):
            record = self.add_library(f"set-{number}", f"2026-10-{number + 1:02d}")
            base = record["path"]
            self.write(base + "/Airborne.mp3")
            self.write(base + "/z-last.ogg")
            self.write(base + "/nested/a-first.mp3")
            self.write(base + "/nested/a-first.lrc", b"[lang:fr]\n[00:01]Example\n")
            self.write(base + "/nested/a-first.en.lrc", b"[00:01]Translation\n")
        before = self.fingerprints()
        libraries = self.api["list_music_libraries"]()
        self.assertEqual(self.scans, 1)
        self.assertEqual([item["id"] for item in libraries], [f"set-{i}" for i in reversed(range(8))])
        for item in libraries:
            self.assertEqual(item["custom"], {"keep": True})
            self.assertEqual(item["count"], 2)
            self.assertEqual([track["path"] for track in item["tracks"]],
                [item["path"] + "/nested/a-first.mp3", item["path"] + "/z-last.ogg"])
            track = item["tracks"][0]
            self.assertEqual(track["lyricsLanguage"], "fr")
            self.assertEqual([option["code"] for option in track["lyricsLanguages"]], ["fr", "en"])
        self.assertEqual(self.fingerprints(), before, "a listing changed persistent media or settings")

    def test_external_changes_are_visible_on_the_next_call(self):
        self.write("Airborne.mp3")
        record = self.add_library("one", "2026-10-15")
        self.write(record["path"] + "/Airborne.mp3")
        retained = self.write(record["path"] + "/Keep.mp3")
        self.assertEqual(self.api["list_music_libraries"]()[0]["count"], 1)
        (self.music / "Airborne.mp3").unlink()
        self.write("Keep.mp3")
        self.write(record["path"] + "/New.ogg")
        retained.write_bytes(b"changed externally")
        paths = [track["path"] for track in self.api["list_music_libraries"]()[0]["tracks"]]
        self.assertEqual(paths, [record["path"] + "/Airborne.mp3", record["path"] + "/New.ogg"])
        self.assertEqual(self.scans, 2)
        (self.music / "Keep.mp3").unlink()
        retained.unlink()
        (self.music / (record["path"] + "/New.ogg")).unlink()
        self.assertEqual(self.api["list_music_libraries"]()[0]["count"], 1)
        self.assertEqual(self.scans, 3)

    def test_empty_or_invalid_libraries_do_not_scan_local_music(self):
        self.save_records()
        self.assertEqual(self.api["list_music_libraries"](), [])
        self.records = [{"id": "empty", "path": ""}, {"id": "missing", "path": "libraries/missing"},
                        {"id": "outside", "path": "../outside"}]
        self.save_records()
        libraries = self.api["list_music_libraries"]()
        self.assertEqual([item["count"] for item in libraries], [0, 0, 0])
        self.assertEqual(self.scans, 0)

    def test_an_empty_local_name_set_is_reused(self):
        for number in range(5):
            record = self.add_library(str(number), "2026-10-15")
            self.write(record["path"] + "/Only.mp3")
        self.assertTrue(all(item["count"] == 1 for item in self.api["list_music_libraries"]()))
        self.assertEqual(self.scans, 1)

    def test_standalone_read_and_duplicate_opt_out_keep_their_behavior(self):
        self.write("Airborne.mp3")
        record = self.add_library("one", "2026-10-15")
        self.write(record["path"] + "/Airborne.mp3")
        self.assertEqual(self.api["public_music_library_record"](record)["count"], 0)
        (self.music / "Airborne.mp3").unlink()
        self.assertEqual(self.api["public_music_library_record"](record)["count"], 1)
        self.write("Airborne.mp3")
        self.assertEqual(len(self.api["library_tracks_for_record"](record, hide_local_duplicates=False)), 1)
        self.assertEqual(self.scans, 2)

    def test_one_unreadable_track_does_not_erase_other_library_tracks(self):
        for identifier in ("first", "second"):
            record = self.add_library(identifier, "2026-10-15")
            self.write(record["path"] + "/Good.mp3")
            self.write(record["path"] + "/Bad.mp3")
        original = self.api["music_track_from_path"]

        def read_track(path):
            if path.name == "Bad.mp3":
                raise OSError("synthetic concurrent removal")
            return original(path)

        with patch.dict(self.api, music_track_from_path=read_track):
            libraries = self.api["list_music_libraries"]()
        self.assertEqual([item["id"] for item in libraries], ["first", "second"])
        self.assertTrue(all(item["count"] == 1 and item["tracks"][0]["name"] == "Good" for item in libraries))
        self.assertEqual(self.scans, 1)


if __name__ == "__main__":
    unittest.main()
