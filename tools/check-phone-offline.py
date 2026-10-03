"""Check private export boundaries and the whitelist-only static phone bundle."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from document_library import DocumentLibraryService
import phone_offline

spec = importlib.util.spec_from_file_location("phone_static_builder", PROJECT / "tools" / "build-phone-static.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def valid_plan():
    return {"version": 1, "revision": "private-20261001", "groups": [
        {"id": f"group-{index}", "title": f"Private Task {index}", "summary": "Private summary",
         "items": [{"id": f"item-{index}", "text": "Private item", "done": False}]} for index in range(4)]}


class ExportChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-phone-export-check-")
        self.base = Path(self.temp.name)
        self.root = self.base / "library"
        self.root.mkdir()
        (self.root / "reports").mkdir()
        (self.root / "guide.md").write_text("# Important\nOne point.\n", encoding="utf-8")
        (self.root / "reports/one.md").write_text("# Report\nOne result.\n", encoding="utf-8")
        (self.root / "reference.md").write_text("# Reference\nUse safely.\n", encoding="utf-8")
        (self.root / "private-ai-record.txt").write_text("DO NOT EXPORT RAW TREE", encoding="utf-8")
        (self.root / ".document-guide.json").write_text(json.dumps({"version": 1, "items": [
            {"path": "guide.md", "title": "Important", "summary": "One point", "highlights": ["Point"]},
            {"path": "reports/one.md", "title": "Result", "summary": "", "highlights": []}]}), encoding="utf-8")
        (self.root / ".document-references.json").write_text(json.dumps({"version": 1, "items": [
            {"id": "paired", "module": "blender", "defaultLanguage": "en", "variants": [
             {"language": "en", "label": "English", "title": "Reference", "summary": "", "path": "reference.md"},
             {"language": "zh-CN", "label": "中文", "title": "Missing reference", "summary": "", "path": "missing.md"}]}]}), encoding="utf-8")
        self.documents = DocumentLibraryService(self.base / "documents.json")
        self.documents.select(str(self.root))
        self.documents.register_report("one", "reports/one.md", "One", "Result", "Fixture")
        self.plan_getter = lambda: {"plan": valid_plan(), "error": ""}
        self.device_getter = lambda: {"root": str(self.documents._root()), "model": "PC", "cpuModel": "CPU",
            "currentMemory": {"status": "available", "readAt": "today", "totalBytes": 16000,
                              "availableBytes": 3000, "usedPercent": 81},
            "applications": ["PRIVATE PROCESSES"], "sampledAt": "yesterday"}

    def tearDown(self):
        self.temp.cleanup()

    def export(self):
        return phone_offline.build_phone_export(self.documents, self.plan_getter, self.device_getter, "1.0.16")

    def test_registered_only_deduplicated_plan_curated_device_no_root(self):
        payload = self.export()
        self.assertEqual(payload["format"], "codex-console-phone-data")
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["dashboard"]["version"], "1.0.16")
        self.assertEqual(len(payload["dashboard"]["plan"]["plan"]["groups"]), 4)
        self.assertEqual([item["path"] for item in payload["files"]], ["guide.md", "reports/one.md", "reference.md"])
        serialized = json.dumps(payload)
        for value in (str(self.root), "PRIVATE PROCESSES", "DO NOT EXPORT RAW TREE"):
            self.assertNotIn(value, serialized)
        self.assertNotIn("root", payload["dashboard"]["documents"]["inbox"])
        self.assertLessEqual(len(phone_offline._json_bytes(payload)), phone_offline.MAX_EXPORT_BYTES)

    def test_export_never_writes_library_settings_or_progress(self):
        paths = [self.documents.settings_file] + [item for item in self.root.rglob("*") if item.is_file()]
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        self.export()
        self.export()
        self.assertEqual(before, {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})
        self.assertEqual(len(paths), len([self.documents.settings_file] + [item for item in self.root.rglob("*") if item.is_file()]))

    def test_other_process_selection_change_keeps_entire_export_pinned(self):
        alternate = self.base / "alternate"
        alternate.mkdir()
        (alternate / "guide.md").write_text("NEW ROOT SECRET", encoding="utf-8")
        original = self.documents.read
        calls = []
        def changed_settings_read(path, expectedRoot=None):
            if not calls:
                self.documents.settings_file.write_text(json.dumps({"root": str(alternate)}), encoding="utf-8")
            calls.append(path)
            return original(path, expectedRoot=expectedRoot)
        with patch.object(self.documents, "read", side_effect=changed_settings_read):
            payload = self.export()
        self.assertNotIn("NEW ROOT SECRET", json.dumps(payload))
        self.assertIn("One point", payload["files"][0]["content"])
        self.assertEqual(len(payload["files"]), 3)
        self.assertEqual(self.documents.state()["root"], str(alternate))

    def test_invalid_registration_outside_library_rejected(self):
        original = (self.root / ".document-guide.json").read_bytes()
        (self.base / "outside.md").write_text("OUTSIDE SECRET", encoding="utf-8")
        (self.root / ".document-guide.json").write_text(json.dumps({"version": 1, "items": [
            {"path": "../outside.md", "title": "Bad", "summary": "", "highlights": []}]}), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.export()
        self.assertEqual((self.base / "outside.md").read_text(encoding="utf-8"), "OUTSIDE SECRET")
        self.assertNotEqual((self.root / ".document-guide.json").read_bytes(), original)

    def test_file_limit_and_total_packet_limit_do_not_mutate_sources(self):
        guide = self.root / "guide.md"
        guide.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
        with self.assertRaises(ValueError):
            self.export()
        self.assertEqual(guide.stat().st_size, 2 * 1024 * 1024 + 1)
        guide.write_text("Small", encoding="utf-8")
        with patch.object(phone_offline, "MAX_EXPORT_BYTES", 100):
            with self.assertRaisesRegex(ValueError, "8 MiB"):
                self.export()
        self.assertEqual(guide.read_text(encoding="utf-8"), "Small")
        items = []
        for index in range(5):
            name = f"large-{index}.md"
            (self.root / name).write_bytes(b"a" * (2 * 1024 * 1024 - 1))
            items.append({"path": name, "title": f"Large {index}", "summary": "", "highlights": []})
        (self.root / ".document-guide.json").write_text(json.dumps({"version": 1, "items": items}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "8 MiB"):
            self.export()
        self.assertEqual((self.root / "large-4.md").stat().st_size, 2 * 1024 * 1024 - 1)

    def test_invalid_plan_no_library_or_version_are_rejected(self):
        self.plan_getter = lambda: {"plan": {"version": 1, "revision": "x", "groups": []}, "error": ""}
        with self.assertRaises(ValueError):
            self.export()
        with self.assertRaises(ValueError):
            phone_offline.build_phone_export(self.documents, lambda: {}, self.device_getter, "bad")
        (self.base / "documents.json").unlink()
        with self.assertRaises(ValueError):
            self.export()


class StaticBuildChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-phone-static-check-")
        self.base = Path(self.temp.name)
        self.project = self.base / "project"
        self.project.mkdir()
        self.output = self.base / "dist-phone"
        (self.project / "app-manifest.json").write_text(json.dumps({"version": "1.0.16", "private": "PRIVATE CONFIG"}), encoding="utf-8")
        phone = self.project / "phone"
        phone.mkdir()
        for name in builder.PHONE_ASSETS:
            source = phone / name
            source.parent.mkdir(parents=True, exist_ok=True)
            if name.startswith("vendor/"):
                source.write_bytes((PROJECT / "phone" / name).read_bytes())
            else:
                source.write_text("// __CONSOLE_PHONE_VERSION__ / __CONSOLE_PHONE_BUILD__\n", encoding="utf-8")
        (phone / "index.html").write_text('<!doctype html><title>__CONSOLE_PHONE_VERSION__</title><link href="./styles.css"><script src="./app.js"></script>', encoding="utf-8")
        (phone / "manifest.webmanifest").write_text(json.dumps({"name": "Codex Console", "start_url": "./index.html", "scope": "./", "icons": [{"src": "./phone-icon-192.png"}]}), encoding="utf-8")
        (phone / "private-plan.json").write_text("PRIVATE PLAN", encoding="utf-8")
        (self.project / "workspace-plan.json").write_text("PRIVATE PLAN", encoding="utf-8")
        for icon in builder.ICONS:
            (phone / icon).write_bytes(b"\x89PNG\r\n\x1a\nFIXTURE")
        music = self.project / "public-music"
        music.mkdir()
        for name in builder.PUBLIC_TRACKS:
            (music / name).write_bytes(b"PUBLIC MUSIC " + name.encode("utf-8"))
        (music / "Around the World.lrc").write_text("[00:01.00]Public lyric", encoding="utf-8")
        (music / "Ma rose éternelle.lrc").write_text("[lang:fr]\n[00:01.00]French lyric", encoding="utf-8")
        (music / "Ma rose éternelle.en.lrc").write_text("[lang:en]\n[00:01.00]English lyric", encoding="utf-8")
        (music / "Ma rose éternelle.zh.lrc").write_text("[lang:zh]\n[00:01.00]中文", encoding="utf-8")
        (music / "libraries").mkdir()
        (music / "libraries/private-song.mp3").write_bytes(b"PRIVATE MUSIC")
        (music / "extra-private.mp3").write_bytes(b"PRIVATE MUSIC")
        (music / "private.json").write_text("PRIVATE METADATA", encoding="utf-8")
        (music / "Outrun.en.lrc").write_text("PRIVATE LOCAL LYRICS", encoding="utf-8")
        (music / "Airborne.fr.lrc").write_text("PRIVATE LOCAL LYRICS", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_whitelist_only_no_private_content_version_and_relative_catalog(self):
        result = builder.build_static(self.project, self.output, make_zip=True)
        self.assertEqual(result["version"], "1.0.16")
        self.assertEqual(result["musicTracks"], 16)
        files = {item.relative_to(self.output).as_posix() for item in self.output.rglob("*") if item.is_file()}
        self.assertEqual(len(files), len(builder.PHONE_ASSETS) + len(builder.ICONS) + 16 + 4 + 2)
        self.assertFalse(any("private" in item for item in files))
        self.assertFalse((self.output / "music/libraries").exists())
        for file in files:
            data = (self.output / file).read_bytes()
            self.assertNotIn(b"PRIVATE ", data)
            self.assertNotIn(b"__CONSOLE_PHONE_VERSION__", data)
            self.assertNotIn(b"__CONSOLE_PHONE_BUILD__", data)
        version = json.loads((self.output / "version.json").read_text(encoding="utf-8"))
        self.assertEqual(version["version"], "1.0.16")
        self.assertEqual(version["buildId"], result["buildId"])
        catalog = json.loads((self.output / "music-catalog.json").read_text(encoding="utf-8"))
        self.assertEqual([item["source"].removeprefix("music/") for item in catalog["tracks"]], list(builder.PUBLIC_TRACKS))
        french = next(item for item in catalog["tracks"] if item["name"] == "Ma rose éternelle")
        self.assertEqual(french["lyricsLanguage"], "fr")
        self.assertEqual({item["code"] for item in french["lyricsLanguages"]}, {"fr", "en", "zh"})
        for item in catalog["tracks"]:
            self.assertFalse(item["source"].startswith("/"))
            self.assertTrue((self.output / item["source"]).is_file())
        with zipfile.ZipFile(result["archive"]) as archive:
            self.assertEqual(set(archive.namelist()), files)

    def test_unknown_output_file_rejected_without_delete_or_overwrite(self):
        self.output.mkdir()
        (self.output / "important.txt").write_text("Keep me", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unknown files"):
            builder.build_static(self.project, self.output)
        self.assertEqual((self.output / "important.txt").read_text(encoding="utf-8"), "Keep me")
        self.assertFalse((self.output / "index.html").exists())

    def test_vendor_assets_and_actual_license_are_preserved_in_directory_and_archive(self):
        vendor = self.project / "phone/vendor"
        (vendor / "private-config.js").write_text("PRIVATE VENDOR CONFIG", encoding="utf-8")
        result = builder.build_static(self.project, self.output, make_zip=True)
        license_data = (PROJECT / "phone/vendor/jsQR.LICENSE").read_bytes()
        self.assertIn(b"Apache License", license_data)
        self.assertIn(b"Version 2.0", license_data)
        self.assertEqual((self.output / "vendor/jsQR.LICENSE").read_bytes(), license_data)
        self.assertEqual((self.output / "vendor/jsQR.js").read_bytes(), (PROJECT / "phone/vendor/jsQR.js").read_bytes())
        self.assertTrue((self.output / "connection-qr.js").is_file())
        self.assertFalse((self.output / "vendor/private-config.js").exists())
        with zipfile.ZipFile(result["archive"]) as archive:
            self.assertEqual(archive.read("vendor/jsQR.LICENSE"), license_data)
            self.assertIn("vendor/jsQR.js", archive.namelist())
            self.assertIn("connection-qr.js", archive.namelist())
            self.assertNotIn("vendor/private-config.js", archive.namelist())

    def test_unknown_vendor_output_file_rejected_without_modifying_existing_bundle(self):
        builder.build_static(self.project, self.output)
        sentinel = self.output / "vendor/unlisted.js"
        sentinel.write_text("Keep my unknown vendor file", encoding="utf-8")
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in self.output.rglob("*") if path.is_file()}
        with self.assertRaisesRegex(ValueError, "unknown files"):
            builder.build_static(self.project, self.output)
        self.assertEqual(before, {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before})
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "Keep my unknown vendor file")

    def test_linked_vendor_source_directory_or_asset_is_rejected_before_output_creation(self):
        vendor = self.project / "phone/vendor"
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in vendor.iterdir() if path.is_file()}
        for classification in ("is_symlink", "is_junction"):
            original = getattr(Path, classification, lambda path: False)
            for linked in (vendor, vendor / "jsQR.js", vendor / "jsQR.LICENSE"):
                with self.subTest(classification=classification, linked=str(linked)):
                    with patch.object(Path, classification,
                                      lambda path: path == linked or original(path), create=True):
                        with self.assertRaisesRegex(ValueError, "linked"):
                            builder.build_static(self.project, self.output)
                    self.assertFalse(self.output.exists())
        self.assertEqual(before, {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before})

    def test_existing_output_with_parent_components_rebuilds_after_normalization(self):
        first = builder.build_static(self.project, self.output)
        spelling = self.output / ".." / self.output.name
        rebuilt = builder.build_static(self.project, spelling)
        self.assertEqual(rebuilt["buildId"], first["buildId"])
        self.assertEqual(Path(rebuilt["outputDirectory"]), self.output.resolve())

    @unittest.skipUnless(sys.platform == "win32", "Windows short path regression")
    def test_windows_short_name_output_rebuilds_without_bypassing_safety_checks(self):
        import ctypes
        from ctypes import wintypes

        get_short_path = ctypes.WinDLL("kernel32", use_last_error=True).GetShortPathNameW
        get_short_path.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
        get_short_path.restype = wintypes.DWORD
        required = get_short_path(str(self.base), None, 0)
        if not required:
            self.fail(f"GetShortPathNameW failed: {ctypes.get_last_error()}")
        buffer = ctypes.create_unicode_buffer(required)
        self.assertGreater(get_short_path(str(self.base), buffer, required), 0)
        short_base = Path(buffer.value)
        if short_base == self.base:
            self.skipTest("The temporary volume does not generate short names")
        short_output = short_base / self.output.name
        first = builder.build_static(self.project, self.output)
        rebuilt = builder.build_static(self.project, short_output, make_zip=True)
        self.assertEqual(rebuilt["buildId"], first["buildId"])
        self.assertEqual(Path(rebuilt["outputDirectory"]), self.output.resolve())
        self.assertTrue(Path(rebuilt["archive"]).is_file())
        sentinel = self.output / "important.txt"
        sentinel.write_text("Keep me", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unknown files"):
            builder.build_static(self.project, short_output)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "Keep me")
        source = self.project / "phone/index.html"
        before = source.read_bytes()
        with self.assertRaises(ValueError):
            builder.build_static(self.project, short_base / "project/phone")
        self.assertEqual(source.read_bytes(), before)

    def test_linked_output_or_ancestor_rejected_before_normalizing_or_writing(self):
        ancestor = self.base / "alias"
        ancestor.mkdir()
        if sys.platform == "win32":
            with self.assertRaisesRegex(ValueError, "absolute output path"):
                builder.build_static(self.project, self.base.drive + "new-output")
        for classification in ("is_symlink", "is_junction"):
            original = getattr(Path, classification, lambda path: False)
            for output, linked in ((self.output, self.output),
                                   (ancestor / "new-output", ancestor),
                                   (ancestor / ".." / "new-output", ancestor)):
                with self.subTest(classification=classification, output=str(output)):
                    with patch.object(Path, classification,
                                      lambda path: path == linked or original(path), create=True):
                        with self.assertRaisesRegex(ValueError, "linked path"):
                            builder.build_static(self.project, output)
                    self.assertFalse(output.exists())
        self.assertEqual(list(ancestor.iterdir()), [])

    def test_relative_html_and_manifest_required_for_project_subdirectory(self):
        (self.project / "phone/index.html").write_text('<script src="/app.js"></script>', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "relative URLs"):
            builder.build_static(self.project, self.output)
        self.assertFalse(self.output.exists())
        (self.project / "phone/index.html").write_text('<script src="./app.js"></script>', encoding="utf-8")
        (self.project / "phone/manifest.webmanifest").write_text(json.dumps({"start_url": "/index.html", "scope": "/"}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "relative URLs"):
            builder.build_static(self.project, self.output)

    def test_missing_track_or_source_output_collision_cannot_modify_sources(self):
        track = self.project / "public-music" / builder.PUBLIC_TRACKS[0]
        saved = track.read_bytes()
        track.unlink()
        with self.assertRaises(ValueError):
            builder.build_static(self.project, self.output)
        self.assertFalse(self.output.exists())
        track.write_bytes(saved)
        before = (self.project / "phone/index.html").read_bytes()
        with self.assertRaises(ValueError):
            builder.build_static(self.project, self.project / "phone")
        self.assertEqual((self.project / "phone/index.html").read_bytes(), before)

    def test_build_identifier_deterministic_and_changes_for_same_version_asset_edit(self):
        first = builder.build_static(self.project, self.output)
        second = builder.build_static(self.project, self.output)
        self.assertEqual(first["buildId"], second["buildId"])
        script = self.project / "phone/app.js"
        script.write_text(script.read_text(encoding="utf-8") + "// maintenance fix\n", encoding="utf-8")
        changed = builder.build_static(self.project, self.output)
        self.assertEqual(first["version"], changed["version"])
        self.assertNotEqual(first["buildId"], changed["buildId"])
        self.assertRegex(changed["buildId"], r"^[a-f0-9]{16}$")
        self.assertIn(changed["buildId"], (self.output / "sw.js").read_text(encoding="utf-8"))

    def test_same_version_icon_change_refreshes_shell_without_including_unlisted_assets(self):
        first = builder.build_static(self.project, self.output)
        icon = self.project / "phone" / builder.ICONS[0]
        icon.write_bytes(icon.read_bytes() + b"NEW PHONE ICON")
        (self.project / "phone/private-photo.png").write_bytes(b"PRIVATE PHOTO")
        changed = builder.build_static(self.project, self.output)
        self.assertEqual(first["version"], changed["version"])
        self.assertNotEqual(first["buildId"], changed["buildId"])
        self.assertEqual((self.output / builder.ICONS[0]).read_bytes(), icon.read_bytes())
        self.assertFalse((self.output / "private-photo.png").exists())

    def test_independent_phone_version_precedes_desktop_and_missing_phone_falls_back(self):
        desktop = self.project / "app-manifest.json"
        desktop.write_text(json.dumps({"version": "1.0.6"}), encoding="utf-8")
        self.assertEqual(builder.build_static(self.project, self.output)["version"], "1.0.6")
        phone_version = self.project / "phone/version.json"
        phone_version.write_text(json.dumps({"version": "1.0.16"}), encoding="utf-8")
        first = builder.build_static(self.project, self.output)
        self.assertEqual(first["version"], "1.0.16")
        self.assertEqual(json.loads((self.output / "version.json").read_text(encoding="utf-8"))["version"], "1.0.16")
        desktop.unlink()
        phone_version.write_text(json.dumps({"version": "1.0.16", "irrelevant": "Not published"}), encoding="utf-8")
        self.assertEqual(builder.build_static(self.project, self.output)["buildId"], first["buildId"])
        self.assertNotIn("irrelevant", (self.output / "version.json").read_text(encoding="utf-8"))

    def test_invalid_phone_version_does_not_silently_use_desktop_version(self):
        version_file = self.project / "phone/version.json"
        for invalid in (None, 16, "bad", "1.0", "01.0.16", "1.0.16-01", "1.0.16+", "1.0.1\u0666"):
            with self.subTest(version=invalid):
                version_file.write_text(json.dumps({"version": invalid}), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "phone/version.json"):
                    builder.build_static(self.project, self.output)
                self.assertFalse(self.output.exists())
        for invalid_json in ("[]", "not-json"):
            version_file.write_text(invalid_json, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "phone/version.json"):
                builder.build_static(self.project, self.output)
        self.assertFalse(self.output.exists())

    def test_linked_phone_version_is_rejected_even_when_pointing_to_valid_file(self):
        target = self.base / "version.json"
        target.write_text(json.dumps({"version": "1.0.16"}), encoding="utf-8")
        link = self.project / "phone/version.json"
        try:
            link.symlink_to(target)
        except OSError:
            # Standard Windows accounts may not create links. Exercise the
            # same path classification policy without requesting privileges.
            link.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
            original_is_symlink = Path.is_symlink
            with patch.object(Path, "is_symlink", lambda path: path == link or original_is_symlink(path)):
                with self.assertRaisesRegex(ValueError, "linked file"):
                    builder.build_static(self.project, self.output)
        else:
            with self.assertRaisesRegex(ValueError, "linked file"):
                builder.build_static(self.project, self.output)
        self.assertFalse(self.output.exists())

    def test_explicit_version_override_is_validated_and_included_in_build_identifier(self):
        first = builder.build_static(self.project, self.output)
        changed = builder.build_static(self.project, self.output, version="1.0.17-rc.1+phone")
        self.assertEqual(changed["version"], "1.0.17-rc.1+phone")
        self.assertNotEqual(first["buildId"], changed["buildId"])
        with self.assertRaisesRegex(ValueError, "--version"):
            builder.build_static(self.project, self.output, version="not-a-version")

    def test_public_original_music_order_and_tiers_preserved_without_private_paths(self):
        preferred = ["Outrun.mp3", "Redline.mp3", "Liquid Roller.mp3", "Get Lucky.mp3"]
        defaults = {"schemaVersion": 1, "capturedAt": "Old timestamp", "music": {
            "order": preferred + ["Outrun.mp3", "D:\\Private\\secret.mp3", "extra-private.mp3"],
            "tiers": {"Outrun.mp3": "first", "Redline.mp3": "first", "Get Lucky.mp3": "second",
                      "D:\\Private\\secret.mp3": "first", "Airborne.mp3": "invalid"}},
            "modules": {"PRIVATE CONFIG": "DO NOT PUBLISH"}}
        source = self.project / "release-defaults.json"
        source.write_text(json.dumps(defaults), encoding="utf-8")
        first = builder.build_static(self.project, self.output)
        catalog = json.loads((self.output / "music-catalog.json").read_text(encoding="utf-8"))
        names = [item["source"].removeprefix("music/") for item in catalog["tracks"]]
        self.assertEqual(names, preferred + [name for name in builder.PUBLIC_TRACKS if name not in preferred])
        self.assertEqual(len(names), 16)
        self.assertEqual(len(set(names)), 16)
        self.assertEqual({item["source"].removeprefix("music/"): item["tier"] for item in catalog["tracks"] if "tier" in item},
                         {"Outrun.mp3": "first", "Redline.mp3": "first", "Get Lucky.mp3": "second"})
        serialized = json.dumps(catalog)
        for excluded in ("Private", "secret.mp3", "extra-private", "modules", "capturedAt"):
            self.assertNotIn(excluded, serialized)
        defaults["capturedAt"] = "New timestamp"
        source.write_text(json.dumps(defaults, indent=4), encoding="utf-8")
        self.assertEqual(builder.build_static(self.project, self.output)["buildId"], first["buildId"])
        defaults["music"]["order"][:2] = ["Redline.mp3", "Outrun.mp3"]
        source.write_text(json.dumps(defaults), encoding="utf-8")
        reordered = builder.build_static(self.project, self.output)
        self.assertNotEqual(reordered["buildId"], first["buildId"])
        defaults["music"]["tiers"]["Get Lucky.mp3"] = "third"
        source.write_text(json.dumps(defaults), encoding="utf-8")
        self.assertNotEqual(builder.build_static(self.project, self.output)["buildId"], reordered["buildId"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
