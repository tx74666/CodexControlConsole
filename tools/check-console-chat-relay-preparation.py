"""Isolated tests: review preparation never installs, executes or grants approval."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("console_chat_relay_preparation", ROOT / "tools/prepare-console-chat-relay.py")
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)


def console_pe():
    """Structurally valid isolated PE headers; never executed or a trusted release."""
    data = bytearray(1024)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 128)
    data[128:132] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 132, 0x8664, 1, 0, 0, 0, 240, 0x22)
    struct.pack_into("<H", data, 152, 0x20B)
    struct.pack_into("<I", data, 152 + 60, 512)
    struct.pack_into("<H", data, 152 + 68, 3)
    data[392:400] = b".text\0\0\0"
    struct.pack_into("<II", data, 392 + 16, 512, 512)
    struct.pack_into("<I", data, 392 + 36, 0x60000020)
    data[512:] = bytes([0xC3]) + bytes(511)
    return bytes(data)


def snapshots(root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


class PreparationChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="console-relay-prep-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.app = self.root / "应用 bundle with spaces"
        self.extension = self.app / "_internal/extensions"
        shutil.copytree(ROOT / "extensions/console-chat-relay", self.extension)
        self.host = self.app / prep.HOST_RELATIVE
        self.host.parent.mkdir(parents=True)
        self.host.write_bytes(console_pe())
        (self.app / "_internal/app-manifest.json").write_text(json.dumps({
            "name": "Codex Control Console", "version": "0.0.0", "installMode": "installed",
        }), encoding="utf-8")
        self.output = self.root / "待审核 materials"

    def inspect(self, **extra):
        return prep.inspect_bundle(self.app, fixture=True, **extra)

    def prepare(self, **extra):
        return prep.prepare_bundle(self.app, self.output, fixture=True, **extra)

    def manifest(self, change):
        path = self.extension / "manifest.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        change(value)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def corrupt_pe(self, offset, fmt, value):
        data = bytearray(self.host.read_bytes())
        struct.pack_into(fmt, data, offset, value)
        self.host.write_bytes(data)

    def test_readonly_exact_actual_bundle_layout_and_pe(self):
        before = snapshots(self.root)
        result = self.inspect()
        self.assertEqual(result["hostPath"], str(self.host))
        self.assertEqual(result["extensionDir"], str(self.extension))
        self.assertEqual(result["host"]["subsystemCode"], 3)
        self.assertEqual(result["host"]["machineCode"], 0x8664)
        self.assertFalse(any(result["operations"].values()))
        self.assertTrue(result["fixture"])
        self.assertEqual(before, snapshots(self.root))

    def test_missing_host_has_no_output(self):
        self.host.unlink()
        with self.assertRaises(prep.PreparationError):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_source_script_is_not_host_substitute(self):
        self.host.unlink()
        (self.host.parent / "console-chat-relay-host.py").write_text("raise SystemExit(0)")
        with self.assertRaises(prep.PreparationError):
            self.inspect()

    def test_nested_extension_layout_is_not_guessed(self):
        nested = self.app / "nested-temporary"
        self.extension.rename(nested)
        self.extension.mkdir()
        nested.rename(self.extension / "console-chat-relay")
        with self.assertRaises(prep.PreparationError):
            self.inspect()

    def test_manifest_key_derived_fixed_id(self):
        self.assertEqual(self.inspect()["extension"]["id"], prep.EXTENSION_ID)
        self.manifest(lambda value: value.update(key="ZmFrZSBrZXk="))
        with self.assertRaisesRegex(prep.PreparationError, "fixed extension ID"):
            self.inspect()

    def test_permission_expansion_rejected(self):
        self.manifest(lambda value: value["permissions"].append("cookies"))
        with self.assertRaises(prep.PreparationError):
            self.inspect()

    def test_optional_permissions_rejected(self):
        self.manifest(lambda value: value.update(optional_permissions=["debugger"]))
        with self.assertRaises(prep.PreparationError):
            self.inspect()

    def test_duplicate_manifest_permission_field_refused(self):
        path = self.extension / "manifest.json"
        original = path.read_text(encoding="utf-8")
        path.write_text(original.replace('"permissions":', '"permissions": ["cookies"], "permissions":', 1), encoding="utf-8")
        with self.assertRaises(prep.PreparationError):
            self.inspect()

    def test_extra_host_origin_rejected(self):
        self.manifest(lambda value: value["host_permissions"].append("https://example.com/*"))
        with self.assertRaises(prep.PreparationError):
            self.inspect()

    def test_external_connections_rejected(self):
        self.manifest(lambda value: value.update(externally_connectable={"matches": ["https://chatgpt.com/*"]}))
        with self.assertRaises(prep.PreparationError):
            self.inspect()

    def test_all_frames_rejected(self):
        self.manifest(lambda value: value["content_scripts"][0].update(all_frames=True))
        with self.assertRaises(prep.PreparationError):
            self.inspect()

    def test_missing_runtime_resource_rejected(self):
        (self.extension / "popup.css").unlink()
        with self.assertRaises(prep.PreparationError):
            self.inspect()

    def test_linked_resource_cannot_read_outside_bundle(self):
        outside = self.root / "private-outside.txt"
        outside.write_text("DO_NOT_READ_OUTSIDE")
        linked = self.extension / "linked-resource.txt"
        try:
            linked.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"Fixture symlink not available: {exc}")
        old_open = Path.open
        def guarded_open(path, *args, **kwargs):
            if path == outside or path == linked:
                raise AssertionError("Linked private content was read")
            return old_open(path, *args, **kwargs)
        with patch.object(Path, "open", guarded_open), self.assertRaises(prep.PreparationError):
            self.inspect()

    def test_linked_extension_root_refused(self):
        outside = self.root / "external-extension"
        self.extension.rename(outside)
        try:
            self.extension.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            if os.name == "nt":
                import _winapi
                _winapi.CreateJunction(str(outside), str(self.extension))
            else:
                self.skipTest(f"Fixture symlink not available: {exc}")
        with self.assertRaises(prep.PreparationError):
            self.inspect()

    def test_linked_nested_directory_cannot_read_private_contents(self):
        outside = self.root / "private-external-directory"
        outside.mkdir()
        sentinel = outside / "approval-secret.txt"
        sentinel.write_text("PRIVATE_CONTENT_NOT_READ")
        linked = self.extension / "nested-linked"
        try:
            linked.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            if os.name == "nt":
                import _winapi
                _winapi.CreateJunction(str(outside), str(linked))
            else:
                self.skipTest(f"Fixture symlink not available: {exc}")
        old_open = Path.open
        def guarded_open(path, *args, **kwargs):
            if path == sentinel or path == linked / sentinel.name:
                raise AssertionError("Private content behind a directory link was read")
            return old_open(path, *args, **kwargs)
        with patch.object(Path, "open", guarded_open), self.assertRaises(prep.PreparationError):
            self.inspect()

    def test_protocol_host_name_mismatch_rejected(self):
        path = self.extension / "lib/protocol.js"
        path.write_text(path.read_text(encoding="utf-8").replace(prep.HOST_NAME, "com.example.other"), encoding="utf-8")
        with self.assertRaisesRegex(prep.PreparationError, "HOST_NAME"):
            self.inspect()

    def test_popup_remote_resource_rejected(self):
        path = self.extension / "popup.html"
        path.write_text(path.read_text(encoding="utf-8").replace('src="popup.js"', 'src="https://example.com/js"'), encoding="utf-8")
        with self.assertRaises(prep.PreparationError):
            self.inspect()

    def test_fake_mz_is_not_valid_pe(self):
        self.host.write_bytes(b"MZ" + bytes(1022))
        with self.assertRaises(prep.PreparationError):
            self.inspect()

    def test_gui_host_rejected(self):
        self.corrupt_pe(152 + 68, "<H", 2)
        with self.assertRaisesRegex(prep.PreparationError, "console subsystem"):
            self.inspect()

    def test_x86_host_rejected(self):
        self.corrupt_pe(132, "<H", 0x14C)
        with self.assertRaisesRegex(prep.PreparationError, "AMD64"):
            self.inspect()

    def test_dll_rejected(self):
        self.corrupt_pe(150, "<H", 0x2022)
        with self.assertRaises(prep.PreparationError):
            self.inspect()

    def test_incomplete_optional_header_rejected(self):
        self.host.write_bytes(self.host.read_bytes()[:250])
        with self.assertRaises(prep.PreparationError):
            self.inspect()

    def test_section_outside_file_rejected(self):
        self.corrupt_pe(392 + 20, "<I", 4096)
        with self.assertRaisesRegex(prep.PreparationError, "section data"):
            self.inspect()

    def test_host_trusted_hash_match_and_mismatch(self):
        digest = hashlib.sha256(self.host.read_bytes()).hexdigest()
        result = self.inspect(expected_host_sha256=digest.upper())
        self.assertTrue(result["trustedFingerprintChecked"]["host"])
        with self.assertRaises(prep.PreparationError):
            self.inspect(expected_host_sha256="0" * 64)

    def test_all_relay_resources_have_actual_hash(self):
        result = self.inspect()
        actual = {path.relative_to(self.app).as_posix() for path in self.extension.rglob("*") if path.is_file()}
        expected = actual | {"_internal/app-manifest.json", prep.HOST_RELATIVE.as_posix()}
        self.assertEqual({item["path"] for item in result["resources"]}, expected)
        for item in result["resources"]:
            path = self.app / item["path"]
            self.assertEqual(item["size"], path.stat().st_size)
            self.assertEqual(item["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_changed_asset_fingerprint_rejects_old_expectation(self):
        old = self.inspect()["extension"]["sha256"]
        with (self.extension / "service-worker.js").open("a", encoding="utf-8") as stream:
            stream.write("\n// isolated fixture change\n")
        self.assertNotEqual(old, self.inspect()["extension"]["sha256"])
        with self.assertRaises(prep.PreparationError):
            self.inspect(expected_extension_sha256=old)

    def test_prepare_space_paths_exact_manifest_no_source_mutation(self):
        before = snapshots(self.app)
        result = self.prepare()
        self.assertEqual(before, snapshots(self.app))
        manifest = json.loads(Path(result["reviewManifest"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest, {"name": prep.HOST_NAME, "description": "Codex Console Chat relay (review preparation only)",
                                   "path": str(self.host), "type": "stdio", "allowed_origins": [prep.ALLOWED_ORIGIN]})
        plan = json.loads((self.output / "registration-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["hive"], "HKEY_CURRENT_USER")
        self.assertEqual(plan["key"], prep.REGISTRY_KEY)
        self.assertEqual(plan["valueData"], result["reviewManifest"])
        self.assertEqual(plan["priorRegistryState"], "not_read")
        self.assertFalse(plan["performed"])
        self.assertFalse(any(result["operations"].values()))
        self.assertEqual({path.name for path in self.output.iterdir()}, {
            f"{prep.HOST_NAME}.review-only.json", "registration-plan.json", "inspection.json", "PREPARATION.md"})

    def test_existing_output_never_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_text("keep original")
        with self.assertRaises(prep.PreparationError):
            self.prepare()
        self.assertEqual(sentinel.read_text(), "keep original")
        self.assertEqual(list(self.output.iterdir()), [sentinel])

    def test_output_inside_source_refused(self):
        with self.assertRaisesRegex(prep.PreparationError, "inside"):
            prep.prepare_bundle(self.app, self.app / "review", fixture=True)
        self.assertFalse((self.app / "review").exists())

    def test_private_data_output_refused_without_reading(self):
        private = self.root / "user-data/CodexControlConsole/workflow-private"
        private.mkdir(parents=True)
        sentinel = private / "console-chat-relay-approved.json"
        sentinel.write_text('{"secret":"NEVER_READ_PRIVATE_APPROVAL"}')
        old_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if path == sentinel:
                raise AssertionError("Private approval was read")
            return old_open(path, *args, **kwargs)

        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "user-data")}), patch.object(Path, "open", guarded_open):
            with self.assertRaisesRegex(prep.PreparationError, "user-data"):
                prep.prepare_bundle(self.app, private / "new-review", fixture=True)
            result = self.prepare()
        self.assertNotIn("NEVER_READ_PRIVATE_APPROVAL", json.dumps(result))
        self.assertFalse((private / "new-review").exists())

    def test_store_is_not_substituted(self):
        path = self.app / "_internal/app-manifest.json"
        value = json.loads(path.read_text())
        value["installMode"] = "store"
        path.write_text(json.dumps(value))
        with self.assertRaises(prep.PreparationError):
            self.inspect()

    def test_unreviewed_build_layout_refused(self):
        script = self.root / "changed-build.ps1"
        script.write_text(prep.DEFAULT_BUILD_SCRIPT.read_text(encoding="utf-8-sig").replace(
            '@{ Source = $ChatRelayHostExe; Destination = "tools" }',
            '@{ Source = $ChatRelayHostExe; Destination = "different" }'), encoding="utf-8")
        with self.assertRaises(prep.PreparationError):
            self.inspect(build_script=script)

    def test_inspect_cli_is_readonly_json_and_disabled(self):
        before = snapshots(self.root)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = prep.main(["inspect", "--app-dir", str(self.app), "--fixture", "--json"])
        self.assertEqual(status, 0)
        report = json.loads(output.getvalue())
        self.assertFalse(any(report["operations"].values()))
        self.assertEqual(before, snapshots(self.root))

    def test_prepare_does_not_import_registry_or_process_modules(self):
        import builtins
        actual_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name in {"winreg", "subprocess", "socket", "sqlite3", "webbrowser"}:
                raise AssertionError(f"Forbidden operational import: {name}")
            return actual_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", guarded_import):
            self.prepare()
        self.assertFalse(any("approved" in path.name for path in self.root.rglob("*")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
