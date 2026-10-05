"""Isolated Native Messaging installer fixtures; no actual registry operations."""
from __future__ import annotations

import builtins
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("console_chat_relay_installer", ROOT / "tools/install-console-chat-relay.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
REGISTRY_BACKEND_CLASS = installer.WindowsRegistry


def fixture_pe():
    data = bytearray(1024)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 128)
    data[128:132] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 132, 0x8664, 1, 0, 0, 0, 240, 0x22)
    struct.pack_into("<H", data, 152, 0x20B)
    struct.pack_into("<I", data, 212, 512)
    struct.pack_into("<H", data, 220, 3)
    data[392:400] = b".text\0\0\0"
    struct.pack_into("<II", data, 408, 512, 512)
    struct.pack_into("<I", data, 428, 0x60000020)
    data[512] = 0xC3
    return bytes(data)


def absent():
    return {"exists": False, "values": [], "subkeys": {}}


def value(name, kind, data):
    return {"name": name, "type": kind, "value": installer._encode_data(data)}


def existing(*values, subkeys=None):
    return {"exists": True, "values": sorted(list(values), key=lambda item: item["name"].casefold()),
            "subkeys": subkeys or {}, "lastWriteTime": 123456}


class FixtureRegistry:
    isolated = True

    def __init__(self, *, shared=False, browser="chrome"):
        self.browser = browser
        self.key = installer.registry_key(browser)
        self.shared = shared
        self.states = {view: absent() for view in installer.VIEWS}
        self.actions = []
        self.fail_view = None
        self.after_write = None

    def _view(self, view):
        return "32-bit" if self.shared else view

    def snapshot(self, view):
        return copy.deepcopy(self.states[self._view(view)])

    def set_default(self, view, data):
        self.actions.append(("set_default", view, data))
        target = self._view(view)
        state = self.states[target]
        if not state["exists"]:
            state = self.states[target] = existing()
        state["values"] = [item for item in state["values"] if item["name"]] + [value("", installer.REG_SZ, data)]
        state["values"].sort(key=lambda item: item["name"].casefold())
        state["lastWriteTime"] += 1
        if self.after_write:
            self.after_write(view, self)
        if view == self.fail_view:
            raise OSError("isolated API failure after its default write")

    def delete_default(self, view):
        self.actions.append(("delete_default", view))
        self.states[self._view(view)]["values"] = [item for item in self.states[self._view(view)]["values"] if item["name"]]

    def delete_empty_host(self, view):
        state = self.states[self._view(view)]
        if state["values"] or state["subkeys"]:
            raise AssertionError("Attempt to delete a nonempty fixture host")
        self.actions.append(("delete_empty_host", view))
        self.states[self._view(view)] = absent()


class InstallationChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="console-relay-install-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve(strict=True)
        self.base = self.root / "user-local"
        self.base.mkdir()
        self.environment = {"LOCALAPPDATA": str(self.base)}
        self.paths = installer.fixed_paths(self.environment)
        self.app = self.paths["appDir"]
        self.extension = self.app / installer.prep.EXTENSION_RELATIVE
        shutil.copytree(ROOT / "extensions/console-chat-relay", self.extension)
        self.host = self.app / installer.prep.HOST_RELATIVE
        self.host.parent.mkdir(parents=True)
        self.host.write_bytes(fixture_pe())
        (self.app / "_internal/app-manifest.json").write_text(json.dumps({
            "version": "0.0.0", "installMode": "installed"}), encoding="utf-8")
        self.bundle = installer.prep.inspect_bundle(self.app, fixture=True)
        self.options = {"expected_host_sha256": self.bundle["host"]["sha256"],
                        "expected_extension_sha256": self.bundle["extension"]["sha256"]}
        self.registry = FixtureRegistry()
        self.addCleanup(patch.stopall)
        # A regression that forgets the injected backend must fail before any
        # registry reads or writes. Process/network/database imports are banned.
        patch.object(installer, "WindowsRegistry", side_effect=AssertionError("Real registry is forbidden in fixture tests")).start()
        real_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name in {"winreg", "subprocess", "socket", "sqlite3", "webbrowser"}:
                raise AssertionError(f"Forbidden operational import: {name}")
            return real_import(name, *args, **kwargs)

        patch.object(builtins, "__import__", guarded_import).start()

    def inspect(self):
        return installer.inspect_installation(environ=self.environment, registry=self.registry, **self.options)

    def install(self, **extra):
        return installer.install(environ=self.environment, registry=self.registry, **(self.options | extra))

    def manifest(self, data=None):
        self.paths["directory"].mkdir(parents=True)
        path = self.paths["manifest"]
        path.write_bytes(data if data is not None else installer._json_bytes(installer.native_manifest(self.bundle)))
        return path

    def assert_no_install_writes(self):
        self.assertEqual(self.registry.actions, [])
        self.assertFalse(self.paths["manifest"].exists())
        self.assertFalse(self.paths["backups"].exists())

    def test_inspect_is_readonly_uses_default_formal_path(self):
        report = self.inspect()
        self.assertEqual(report["appDir"], str(self.app))
        self.assertFalse(report["registered"])
        self.assertTrue(report["fixture"])
        self.assertTrue(report["operations"]["registryRead"])
        self.assertFalse(any(item for name, item in report["operations"].items() if name != "registryRead"))
        self.assert_no_install_writes()
        self.assertFalse(self.paths["directory"].exists())

    def test_install_both_views_manifest_and_verified_persistent_backup(self):
        report = self.install()
        self.assertTrue(report["registered"])
        self.assertEqual([action[1] for action in self.registry.actions], list(installer.VIEWS))
        self.assertEqual(json.loads(self.paths["manifest"].read_text(encoding="utf-8")),
                         installer.native_manifest(self.bundle))
        backup_dir = Path(report["backupDir"])
        backup_bytes = (backup_dir / "backup.json").read_bytes()
        self.assertEqual((backup_dir / "backup.sha256").read_text().strip(), hashlib.sha256(backup_bytes).hexdigest())
        backup = json.loads(backup_bytes)
        self.assertEqual(backup["registryViews"], {view: absent() for view in installer.VIEWS})
        self.assertEqual(backup["manifestBefore"], {"exists": False, "bytesBase64": None, "sha256": None})
        self.assertTrue((backup_dir / "result.json").exists())
        self.assertFalse(self.paths["lock"].exists())
        for operation in ("approvalCreated", "credentialsCreated", "privateDatabaseRead", "relayEnabled", "hostExecuted", "browserOpened"):
            self.assertFalse(report["operations"][operation])

    def test_backup_precedes_every_registration_and_manifest_write(self):
        def before_write(view, registry):
            backups = list(self.paths["backups"].glob("*/backup.json"))
            self.assertEqual(len(backups), 1)
            self.assertTrue(self.paths["manifest"].is_file())
            self.assertEqual(json.loads(backups[0].read_text())["registryViews"][view], absent())
        self.registry.after_write = before_write
        original_publish = installer._atomic_new

        def guarded_publish(path, data, published):
            self.assertEqual(len(list(self.paths["backups"].glob("*/backup.json"))), 1)
            return original_publish(path, data, published)

        with patch.object(installer, "_atomic_new", guarded_publish):
            self.install()

    def test_ancillary_values_binary_and_subkeys_preserved_and_backed_up(self):
        initial = existing(value("Binary", 3, bytes(range(256))), value("Count", 4, 7),
                           value("Items", 7, ["中文", "keep"]),
                           subkeys={"KeptChild": existing(value("child", 1, "preserve"))})
        self.registry.states["32-bit"] = copy.deepcopy(initial)
        report = self.install()
        final = self.registry.snapshot("32-bit")
        self.assertEqual(installer._ancillary(final), installer._ancillary(initial))
        backup = json.loads((Path(report["backupDir"]) / "backup.json").read_text(encoding="utf-8"))
        self.assertEqual(backup["registryViews"]["32-bit"], initial)
        binary = next(item for item in initial["values"] if item["name"] == "Binary")
        self.assertEqual(installer._decode_data(binary["value"]), bytes(range(256)))

    def test_same_manifest_is_idempotent_and_never_rewritten(self):
        first = self.install()
        manifest_bytes = self.paths["manifest"].read_bytes()
        actions = copy.deepcopy(self.registry.actions)
        report = self.install()
        self.assertTrue(report["idempotent"])
        self.assertIsNone(report["backupDir"])
        self.assertEqual(self.registry.actions, actions)
        self.assertEqual(self.paths["manifest"].read_bytes(), manifest_bytes)
        self.assertEqual(len(list(self.paths["backups"].iterdir())), 1)
        self.assertTrue(Path(first["backupDir"]).exists())

    def test_existing_equivalent_manifest_bytes_are_retained(self):
        original = json.dumps(installer.native_manifest(self.bundle), ensure_ascii=False).encode("utf-8")
        self.manifest(original)
        report = self.install()
        self.assertFalse(report["operations"]["manifestWritten"])
        self.assertEqual(self.paths["manifest"].read_bytes(), original)
        backup = json.loads((Path(report["backupDir"]) / "backup.json").read_text())
        self.assertEqual(installer._decode_data({"encoding": "base64", "data": backup["manifestBefore"]["bytesBase64"]}), original)

    def test_conflicting_default_in_either_view_is_refused_before_writes(self):
        for view in installer.VIEWS:
            with self.subTest(view=view):
                self.registry.states = {item: absent() for item in installer.VIEWS}
                self.registry.states[view] = existing(value("", 1, "C:\\other\\manifest.json"), value("Keep", 1, "original"))
                before = copy.deepcopy(self.registry.states)
                with self.assertRaisesRegex(installer.InstallationError, "conflicts"):
                    self.install()
                self.assertEqual(self.registry.states, before)
                self.assert_no_install_writes()

    def test_wrong_default_type_is_refused_even_for_matching_path(self):
        self.registry.states["32-bit"] = existing(value("", 2, str(self.paths["manifest"])))
        with self.assertRaisesRegex(installer.InstallationError, "conflicts"):
            self.install()
        self.assert_no_install_writes()

    def test_conflicting_manifest_is_never_overwritten(self):
        data = b'{"name":"com.example.other"}'
        self.manifest(data)
        with self.assertRaisesRegex(installer.InstallationError, "manifest conflicts"):
            self.install()
        self.assertEqual(self.paths["manifest"].read_bytes(), data)
        self.assertEqual(self.registry.actions, [])
        self.assertFalse(self.paths["backups"].exists())

    def test_missing_or_wrong_hashes_refuse_without_registry_writes(self):
        for extra in ({"expected_host_sha256": None}, {"expected_extension_sha256": None},
                      {"expected_host_sha256": "0" * 64}, {"expected_extension_sha256": "0" * 64}):
            with self.subTest(extra=extra):
                with self.assertRaises((installer.InstallationError, installer.prep.PreparationError)):
                    self.install(**extra)
                self.assert_no_install_writes()

    def test_invalid_pe_is_refused_before_any_install_writes(self):
        self.host.write_bytes(b"MZ" + bytes(1022))
        with self.assertRaises(installer.prep.PreparationError):
            self.install()
        self.assert_no_install_writes()

    def test_failure_after_second_write_restores_defaults_and_only_empty_host_keys(self):
        initial = existing(value("Keep", 1, "original"))
        self.registry.states["32-bit"] = copy.deepcopy(initial)
        self.registry.fail_view = "64-bit"
        with self.assertRaises(installer.InstallationError) as caught:
            self.install()
        error = caught.exception
        self.assertTrue(error.recovery["ownChangesRestored"])
        self.assertEqual(installer._ancillary(self.registry.states["32-bit"]), installer._ancillary(initial))
        self.assertIsNone(installer._default(self.registry.states["32-bit"]))
        self.assertFalse(self.registry.states["64-bit"]["exists"])
        self.assertFalse(self.paths["manifest"].exists())
        self.assertTrue((Path(error.backup_dir) / "backup.json").exists())
        self.assertTrue((Path(error.backup_dir) / "recovery.json").exists())
        self.assertNotIn(("delete_empty_host", "32-bit"), self.registry.actions)

    def test_later_default_changes_are_retained_and_recovery_backup_reported(self):
        def concurrent_change(view, registry):
            if view == "64-bit":
                registry.states[view]["values"] = [value("", 1, "C:\\later\\manifest.json")]
                raise OSError("isolated later default change")
        self.registry.after_write = concurrent_change
        with self.assertRaises(installer.InstallationError) as caught:
            self.install()
        self.assertFalse(caught.exception.recovery["ownChangesRestored"])
        self.assertEqual(installer._decode_data(installer._default(self.registry.snapshot("64-bit"))["value"]),
                         "C:\\later\\manifest.json")
        self.assertTrue((Path(caught.exception.backup_dir) / "backup.json").exists())

    def test_later_ancillary_values_kept_while_own_default_is_removed(self):
        def concurrent_value(view, registry):
            if view == "64-bit":
                registry.states[view]["values"].append(value("Later", 1, "retained"))
                raise OSError("isolated new ancillary value")
        self.registry.after_write = concurrent_value
        with self.assertRaises(installer.InstallationError) as caught:
            self.install()
        self.assertTrue(caught.exception.recovery["ownChangesRestored"])
        self.assertEqual(self.registry.snapshot("64-bit")["values"], [value("Later", 1, "retained")])
        self.assertNotIn(("delete_empty_host", "64-bit"), self.registry.actions)

    def test_later_type_change_retains_its_manifest_and_reports_recovery(self):
        def concurrent_type(view, registry):
            if view == "64-bit":
                registry.states[view]["values"] = [value("", 2, str(self.paths["manifest"]))]
                raise OSError("isolated later type change")
        self.registry.after_write = concurrent_type
        with self.assertRaises(installer.InstallationError) as caught:
            self.install()
        self.assertFalse(caught.exception.recovery["ownChangesRestored"])
        self.assertEqual(installer._default(self.registry.snapshot("64-bit"))["type"], 2)
        self.assertTrue(self.paths["manifest"].exists())

    def test_backup_failure_cannot_create_manifest_or_change_registry(self):
        with patch.object(installer, "_backup", side_effect=OSError("isolated storage failure")):
            with self.assertRaises(installer.InstallationError):
                self.install()
        self.assert_no_install_writes()
        self.assertFalse(self.paths["lock"].exists())

    def test_partial_atomic_publish_failure_removes_only_own_manifest(self):
        original_publish = installer._atomic_new
        def fail_after_publish(path, data, published):
            original_publish(path, data, published)
            raise OSError("isolated failure after atomic publication")
        with patch.object(installer, "_atomic_new", fail_after_publish):
            with self.assertRaises(installer.InstallationError) as caught:
                self.install()
        self.assertTrue(caught.exception.recovery["ownChangesRestored"])
        self.assertFalse(self.paths["manifest"].exists())
        self.assertEqual(self.registry.actions, [])

    def test_shared_registry_views_are_supported(self):
        self.registry = FixtureRegistry(shared=True)
        report = self.install()
        self.assertTrue(report["registered"])
        self.assertEqual([action[0] for action in self.registry.actions], ["set_default"])
        self.assertTrue(all(item["registeredToFixedManifest"] for item in report["registration"].values()))

    def test_cli_install_requires_both_hashes_before_any_registry_access(self):
        for args in (["install"], ["install", "--expected-host-sha256", "0" * 64]):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    installer.main(args)
                self.assertEqual(caught.exception.code, 2)
        self.assert_no_install_writes()

    def test_browser_keys_and_native_backend_operations_are_fixed(self):
        for browser, expected in (("chrome", installer.prep.REGISTRY_KEY),
                                  ("edge", rf"Software\Microsoft\Edge\NativeMessagingHosts\{installer.HOST_NAME}")):
            with self.subTest(browser=browser):
                self.assertEqual(installer.registry_key(browser), expected)
                # Exercise the real backend methods with an injected API only;
                # do not construct it or import the real Windows registry API.
                backend = object.__new__(REGISTRY_BACKEND_CLASS)
                backend.browser, backend.key = browser, expected
                api = backend.api = MagicMock()
                api.KEY_READ, api.KEY_SET_VALUE = 1, 2
                api.KEY_WOW64_32KEY, api.KEY_WOW64_64KEY = 512, 256
                api.OpenKey.side_effect = FileNotFoundError
                self.assertFalse(backend.snapshot("32-bit")["exists"])
                self.assertEqual(api.OpenKey.call_args.args[1], expected)
                api.OpenKey.side_effect = None
                api.QueryInfoKey.return_value = (0, 0, 1234)
                backend.set_default("64-bit", "fixture manifest")
                self.assertEqual(api.CreateKeyEx.call_args.args[1], expected)
                backend.delete_default("64-bit")
                self.assertEqual(api.OpenKey.call_args.args[1], expected)
                backend.delete_empty_host("64-bit")
                self.assertEqual(api.DeleteKeyEx.call_args.args[1], expected)

    def test_edge_install_has_own_manifest_and_preserves_chrome_registration(self):
        chrome = self.install()
        chrome_state = copy.deepcopy(self.registry.states)
        chrome_manifest = self.paths["manifest"].read_bytes()
        edge_registry = FixtureRegistry(browser="edge")
        edge_paths = installer.fixed_paths(self.environment, browser="edge")
        report = installer.install(browser="edge", environ=self.environment,
                                   registry=edge_registry, **self.options)
        self.assertTrue(report["registered"])
        self.assertEqual(report["browser"], "edge")
        self.assertEqual(report["registryKey"], installer.BROWSER_KEYS["edge"])
        self.assertNotEqual(edge_paths["manifest"], self.paths["manifest"])
        self.assertEqual(Path(report["manifestPath"]), edge_paths["manifest"])
        self.assertEqual(self.registry.states, chrome_state)
        self.assertEqual(self.paths["manifest"].read_bytes(), chrome_manifest)
        backup = json.loads((Path(report["backupDir"]) / "backup.json").read_text(encoding="utf-8"))
        self.assertEqual((backup["browser"], backup["key"]), ("edge", installer.BROWSER_KEYS["edge"]))
        self.assertTrue(Path(chrome["backupDir"]).exists())
        repeated = installer.install(browser="edge", environ=self.environment,
                                     registry=edge_registry, **self.options)
        self.assertTrue(repeated["idempotent"])

    def test_edge_failure_restores_only_edge_and_keeps_chrome(self):
        self.install()
        chrome_state = copy.deepcopy(self.registry.states)
        chrome_manifest = self.paths["manifest"].read_bytes()
        edge_registry = FixtureRegistry(browser="edge")
        edge_registry.fail_view = "64-bit"
        edge_paths = installer.fixed_paths(self.environment, browser="edge")
        with self.assertRaises(installer.InstallationError) as caught:
            installer.install(browser="edge", environ=self.environment,
                              registry=edge_registry, **self.options)
        self.assertTrue(caught.exception.recovery["ownChangesRestored"])
        self.assertFalse(edge_paths["manifest"].exists())
        self.assertEqual(self.registry.states, chrome_state)
        self.assertEqual(self.paths["manifest"].read_bytes(), chrome_manifest)
        self.assertEqual(edge_registry.states, {view: absent() for view in installer.VIEWS})

    def test_invalid_browser_or_mismatched_backend_refuses_without_writes(self):
        for browser in ("firefox", "edge"):
            with self.subTest(browser=browser):
                with self.assertRaises(installer.InstallationError):
                    self.install(browser=browser)
                self.assert_no_install_writes()

    def test_cli_browser_defaults_to_chrome_and_forwards_explicit_edge(self):
        for arguments, browser in ((["inspect", "--json"], "chrome"),
                                   (["inspect", "--browser", "edge", "--json"], "edge")):
            with self.subTest(browser=browser):
                with patch.object(installer, "inspect_installation", return_value={"fixture": True}) as operation:
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(installer.main(arguments), 0)
                self.assertEqual(operation.call_args.kwargs["browser"], browser)
        self.assert_no_install_writes()


if __name__ == "__main__":
    unittest.main(verbosity=2)
