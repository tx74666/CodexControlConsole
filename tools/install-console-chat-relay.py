"""Register only the reviewed ordinary Chat native host in HKCU.

No approval, credentials, database, relay enablement, process or browser actions.
Both registry views and the manifest are backed up before any registration write.
Tests inject an isolated registry backend; running the test suite never uses HKCU.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

_spec = importlib.util.spec_from_file_location(
    "console_chat_relay_preparation", Path(__file__).with_name("prepare-console-chat-relay.py"))
prep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prep)
HOST_NAME = prep.HOST_NAME
EXTENSION_ID = prep.EXTENSION_ID
REGISTRY_KEY = prep.REGISTRY_KEY
BROWSER_KEYS = {
    "chrome": REGISTRY_KEY,
    "edge": rf"Software\Microsoft\Edge\NativeMessagingHosts\{HOST_NAME}",
}
VIEWS = ("32-bit", "64-bit")
REG_SZ = 1
MAX_MANIFEST_BYTES = 65536


class InstallationError(ValueError):
    def __init__(self, message, *, backup_dir=None, recovery=None):
        super().__init__(message)
        self.backup_dir = str(backup_dir) if backup_dir else None
        self.recovery = recovery


def _require(condition, message):
    if not condition:
        raise InstallationError(message)


def registry_key(browser):
    _require(browser in BROWSER_KEYS, "Browser must be chrome or edge.")
    return BROWSER_KEYS[browser]


def _registry(browser, injected):
    registry_key(browser)
    if injected is None:
        return WindowsRegistry(browser)
    _require(getattr(injected, "browser", browser) == browser,
             "Injected registry backend does not match the selected browser.")
    return injected


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _encode_data(data):
    if isinstance(data, bytes):
        return {"encoding": "base64", "data": base64.b64encode(data).decode("ascii")}
    _require(data is None or isinstance(data, (str, int)) or
             (isinstance(data, list) and all(isinstance(item, str) for item in data)),
             "Unsupported registry value representation; no writes permitted.")
    return {"encoding": "json", "data": data}


def _decode_data(value):
    if value["encoding"] == "base64":
        return base64.b64decode(value["data"], validate=True)
    _require(value["encoding"] == "json", "Unknown backup value encoding.")
    return value["data"]


class WindowsRegistry:
    """Only the fixed HKCU host key, never parent keys or other hosts."""
    isolated = False

    def __init__(self, browser="chrome"):
        self.browser = browser
        self.key = registry_key(browser)
        _require(os.name == "nt", "Native host registration is supported only on Windows.")
        import winreg
        self.api = winreg

    def _flag(self, view):
        _require(view in VIEWS, "Unknown registry view.")
        return self.api.KEY_WOW64_32KEY if view == "32-bit" else self.api.KEY_WOW64_64KEY

    def snapshot(self, view):
        api, flag = self.api, self._flag(view)

        def read(path):
            try:
                key = api.OpenKey(api.HKEY_CURRENT_USER, path, 0, api.KEY_READ | flag)
            except FileNotFoundError:
                return {"exists": False, "values": [], "subkeys": {}}
            with key:
                subkey_count, value_count, modified = api.QueryInfoKey(key)
                values = []
                for index in range(value_count):
                    name, data, kind = api.EnumValue(key, index)
                    values.append({"name": name, "type": kind, "value": _encode_data(data)})
                children = [api.EnumKey(key, index) for index in range(subkey_count)]
                subkeys = {name: read(path + "\\" + name) for name in sorted(children, key=str.casefold)}
                _require(api.QueryInfoKey(key) == (subkey_count, value_count, modified),
                         f"Host key changed while reading its {view} backup; retry inspection.")
                return {"exists": True, "values": sorted(values, key=lambda item: item["name"].casefold()),
                        "subkeys": subkeys, "lastWriteTime": modified}

        return read(self.key)

    def set_default(self, view, data):
        api = self.api
        with api.CreateKeyEx(api.HKEY_CURRENT_USER, self.key, 0,
                             api.KEY_SET_VALUE | self._flag(view)) as key:
            api.SetValueEx(key, "", 0, REG_SZ, data)

    def delete_default(self, view):
        api = self.api
        with api.OpenKey(api.HKEY_CURRENT_USER, self.key, 0,
                         api.KEY_SET_VALUE | self._flag(view)) as key:
            api.DeleteValue(key, "")

    def delete_empty_host(self, view):
        api, flag = self.api, self._flag(view)
        with api.OpenKey(api.HKEY_CURRENT_USER, self.key, 0, api.KEY_READ | flag) as key:
            children, values, _ = api.QueryInfoKey(key)
            _require(children == 0 and values == 0, "Host key acquired other contents; retain it.")
        # DeleteKeyEx targets this exact host key and view. It never deletes parents.
        api.DeleteKeyEx(api.HKEY_CURRENT_USER, self.key, flag, 0)


def _check_no_links(path):
    path = Path(path).absolute()
    for component in reversed((path, *path.parents)):
        _require(not component.is_symlink() and not (
            hasattr(component, "is_junction") and component.is_junction()),
            f"Linked installation paths are not accepted: {component}")
        if component.exists() and component != path:
            _require(component.is_dir(), f"Installation parent is not a directory: {component}")
    return path


def fixed_paths(environ=None, *, browser="chrome"):
    registry_key(browser)
    environment = os.environ if environ is None else environ
    base = environment.get("LOCALAPPDATA")
    _require(isinstance(base, str) and bool(base.strip()), "LOCALAPPDATA is required.")
    raw_base = Path(base)
    _require(raw_base.is_absolute(), "LOCALAPPDATA must be an absolute user-local directory.")
    _check_no_links(raw_base)
    base = raw_base.resolve(strict=True)
    _require(base.is_dir(), "LOCALAPPDATA must be an existing directory.")
    private = base / "CodexControlConsole" / "workflow-private" / "native-messaging"
    # Keep the deployed Chrome location. Edge gets its own manifest/backups so
    # installation or recovery never depends on the other browser's host key.
    if browser == "edge":
        private = private / "edge"
    manifest = private / f"{HOST_NAME}.json"
    backups = private / "installation-backups"
    for path in (private, manifest, backups):
        _check_no_links(path)
    return {"appDir": base / "Programs" / "Codex Console", "directory": private,
            "manifest": manifest, "backups": backups, "lock": private / ".installation.lock"}


def native_manifest(bundle):
    return {"name": HOST_NAME, "description": "Codex Console ordinary Chat relay",
            "path": bundle["hostPath"], "type": "stdio", "allowed_origins": [prep.ALLOWED_ORIGIN]}


def _manifest_bytes(path):
    _check_no_links(path)
    if not path.exists():
        return None
    _require(path.is_file(), "Existing native manifest is not a regular file.")
    _require(path.stat().st_size <= MAX_MANIFEST_BYTES, "Existing native manifest is too large.")
    return path.read_bytes()


def _manifest_matches(data, expected):
    if data is None:
        return False

    def distinct(pairs):
        value = {}
        for name, item in pairs:
            _require(name not in value, "Duplicate native manifest field.")
            value[name] = item
        return value

    try:
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=distinct) == expected
    except (ValueError, UnicodeError):
        return False


def _default(snapshot):
    values = [item for item in snapshot["values"] if item["name"] == ""]
    _require(len(values) <= 1, "Multiple registry default values in snapshot.")
    return values[0] if values else None


def _points_to(snapshot, manifest_path):
    value = _default(snapshot)
    return bool(value and value["type"] == REG_SZ and _decode_data(value["value"]) == str(manifest_path))


def _references_manifest(snapshot, manifest_path):
    value = _default(snapshot)
    # During recovery a later writer may have changed the registry type while
    # retaining the same path. Do not remove a manifest it can still reference.
    return bool(value and _decode_data(value["value"]) == str(manifest_path))


def _preflight(bundle, paths, registry):
    expected = native_manifest(bundle)
    original_manifest = _manifest_bytes(paths["manifest"])
    _require(original_manifest is None or _manifest_matches(original_manifest, expected),
             "Existing native manifest conflicts with the reviewed installation; nothing overwritten.")
    snapshots = {view: registry.snapshot(view) for view in VIEWS}
    for view, state in snapshots.items():
        _require(_default(state) is None or _points_to(state, paths["manifest"]),
                 f"Existing {view} host registration conflicts with the fixed manifest; nothing overwritten.")
    return expected, original_manifest, snapshots


def _bundle(app_dir, paths, registry, options):
    return prep.inspect_bundle(app_dir or paths["appDir"],
                               fixture=bool(getattr(registry, "isolated", False)), **options)


def _registration_summary(snapshots, manifest_path):
    return {view: {"keyExists": state["exists"], "defaultExists": _default(state) is not None,
                   "registeredToFixedManifest": _points_to(state, manifest_path),
                   "otherValueCount": sum(item["name"] != "" for item in state["values"]),
                   "subkeyCount": len(state["subkeys"])} for view, state in snapshots.items()}


def inspect_installation(app_dir=None, *, browser="chrome", environ=None, registry=None, **options):
    """Read only, including the exact fixed host registration in both views."""
    paths = fixed_paths(environ, browser=browser)
    registry = _registry(browser, registry)
    bundle = _bundle(app_dir, paths, registry, options)
    expected, original, snapshots = _preflight(bundle, paths, registry)
    return {"format": "codex-console-chat-relay-installation", "version": 1, "mode": "inspect",
            "fixture": bundle["fixture"], "appDir": bundle["appDir"], "appVersion": bundle["appVersion"],
            "browser": browser, "registryKey": registry_key(browser),
            "hostName": HOST_NAME, "extensionId": EXTENSION_ID, "hostSha256": bundle["host"]["sha256"],
            "extensionSha256": bundle["extension"]["sha256"], "manifestPath": str(paths["manifest"]),
            "manifestExists": original is not None, "nativeManifest": expected,
            "registration": _registration_summary(snapshots, paths["manifest"]),
            "registered": original is not None and all(_points_to(state, paths["manifest"]) for state in snapshots.values()),
            "operations": {"registryRead": True, "registryWritten": False, "manifestWritten": False,
                           "backupWritten": False, "approvalCreated": False, "credentialsCreated": False,
                           "privateDatabaseRead": False, "relayEnabled": False, "hostExecuted": False,
                           "browserOpened": False},
            "limitations": ["Registration does not verify browser extension runtime, approval, profile selection or a Chat round trip."]}


def _write_durable(path, data):
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _sync_directory(directory):
    if os.name != "nt":
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _atomic_new(path, data, published):
    """Publish a complete file atomically and refuse to replace any existing file."""
    temporary = path.with_name(path.name + ".pending-" + uuid.uuid4().hex)
    try:
        _write_durable(temporary, data)
        # An exclusive hard-link publication works on NTFS and never replaces a
        # manifest created concurrently. The temporary name is then discarded.
        os.link(temporary, path)
        published.append(str(path))
        _sync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _backup(paths, bundle, snapshots, original, expected, *, browser="chrome"):
    paths["backups"].mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = paths["backups"] / (stamp + "-" + uuid.uuid4().hex[:12])
    directory.mkdir(exist_ok=False)
    value = {"format": "codex-console-chat-relay-registration-backup", "version": 1,
             "createdAt": _now(), "hive": "HKEY_CURRENT_USER", "key": registry_key(browser),
             "browser": browser,
             "hostName": HOST_NAME, "extensionId": EXTENSION_ID,
             "registryViews": snapshots, "manifestPath": str(paths["manifest"]),
             "manifestBefore": {"exists": original is not None,
                                "bytesBase64": base64.b64encode(original).decode("ascii") if original is not None else None,
                                "sha256": hashlib.sha256(original).hexdigest() if original is not None else None},
             "manifestPlanned": expected, "appDir": bundle["appDir"], "appVersion": bundle["appVersion"],
             "hostSha256": bundle["host"]["sha256"], "extensionSha256": bundle["extension"]["sha256"],
             "bundleSha256": bundle["bundleSha256"],
             "recoveryRules": ["Restore only this fixed host default value if still owned by this installation.",
                               "Retain other values, subkeys, parent keys and other hosts.",
                               "Remove a newly created host key only when empty; never delete parent keys.",
                               "Retain later changes and report a conflict rather than overwrite them."]}
    data = _json_bytes(value)
    _write_durable(directory / "backup.json", data)
    _write_durable(directory / "backup.sha256", (hashlib.sha256(data).hexdigest() + "\n").encode("ascii"))
    _sync_directory(directory)
    _require((directory / "backup.json").read_bytes() == data,
             "Persistent backup verification failed; registration was not modified.")
    return directory


def _ancillary(snapshot):
    return {"values": [value for value in snapshot["values"] if value["name"] != ""],
            "subkeys": snapshot["subkeys"]}


def _recover(registry, paths, snapshots, attempted, manifest_created, written_bytes):
    steps, complete = [], True
    for view in reversed(attempted):
        try:
            current = registry.snapshot(view)
            prior = snapshots[view]
            if _points_to(current, paths["manifest"]):
                # The only allowed original defaults already pointed to this
                # manifest and were never written; changed views had no default.
                _require(_default(prior) is None, "Unexpected changed original default; retain for recovery.")
                registry.delete_default(view)
            else:
                _require(_default(current) is None,
                         f"{view} default changed after installation; preserve its later value.")
            current = registry.snapshot(view)
            if not prior["exists"] and current["exists"] and not current["values"] and not current["subkeys"]:
                registry.delete_empty_host(view)
            steps.append({"view": view, "restoredOwnDefault": True})
        except (OSError, ValueError) as exc:
            complete = False
            steps.append({"view": view, "restoredOwnDefault": False, "reason": str(exc)})
    if manifest_created:
        try:
            states = {view: registry.snapshot(view) for view in VIEWS}
            _require(not any(_references_manifest(state, paths["manifest"]) for state in states.values()),
                     "Registration still references the new manifest; retain manifest for recovery.")
            current = _manifest_bytes(paths["manifest"])
            _require(current is None or current == written_bytes,
                     "Manifest changed after installation; preserve its later contents.")
            if current is not None:
                paths["manifest"].unlink()
                _sync_directory(paths["directory"])
            steps.append({"manifest": "removedOwnNewManifest"})
        except (OSError, ValueError) as exc:
            complete = False
            steps.append({"manifest": "retained", "reason": str(exc)})
    return {"ownChangesRestored": complete, "steps": steps,
            "laterOrUnrelatedChangesPreserved": True}


def install(app_dir=None, *, expected_host_sha256, expected_extension_sha256,
            browser="chrome", environ=None, registry=None, build_script=None):
    """Connection-layer registration only; both trusted fingerprints are mandatory."""
    _require(expected_host_sha256 is not None and expected_extension_sha256 is not None,
             "install requires trusted host and extension SHA256 fingerprints.")
    paths = fixed_paths(environ, browser=browser)
    registry = _registry(browser, registry)
    options = {"build_script": build_script, "expected_host_sha256": expected_host_sha256,
               "expected_extension_sha256": expected_extension_sha256}
    bundle = _bundle(app_dir, paths, registry, options)
    _require(bundle["installMode"] == "installed", "Install requires a formal installed Console bundle.")
    expected, original, snapshots = _preflight(bundle, paths, registry)
    if original is not None and all(_points_to(state, paths["manifest"]) for state in snapshots.values()):
        report = inspect_installation(app_dir, browser=browser, environ=environ, registry=registry, **options)
        return {**report, "mode": "install", "idempotent": True, "backupDir": None}

    paths["directory"].mkdir(parents=True, exist_ok=True)
    _check_no_links(paths["directory"])
    # This lock serializes this installer only; all states are also rechecked
    # before mutation to reject changes made by any other program.
    lock_data = _json_bytes({"pid": os.getpid(), "startedAt": _now()})
    try:
        _write_durable(paths["lock"], lock_data)
    except FileExistsError as exc:
        raise InstallationError(f"Another or interrupted installation holds {paths['lock']}; inspect before recovery.") from exc
    backup_dir, attempted, published = None, [], []
    written_bytes = _json_bytes(expected)
    try:
        fresh = _bundle(app_dir, paths, registry, options)
        _require(fresh["bundleSha256"] == bundle["bundleSha256"] and
                 fresh["buildContract"]["sha256"] == bundle["buildContract"]["sha256"],
                 "Bundle changed before backup; no registration modified.")
        _, current_manifest, current_snapshots = _preflight(fresh, paths, registry)
        _require(current_manifest == original and current_snapshots == snapshots,
                 "Manifest or registry changed before backup; no registration modified.")
        backup_dir = _backup(paths, bundle, snapshots, original, expected, browser=browser)
        _require(_manifest_bytes(paths["manifest"]) == original and
                 all(registry.snapshot(view) == snapshots[view] for view in VIEWS),
                 "Manifest or registry changed after backup; no registration modified.")
        if original is None:
            _atomic_new(paths["manifest"], written_bytes, published)
        for view in VIEWS:
            current = registry.snapshot(view)
            # HKCU keys may be shared between WOW64 views on this Windows
            # version. An earlier owned write can already satisfy this view.
            shared_owned_write = bool(attempted) and _default(snapshots[view]) is None and \
                _points_to(current, paths["manifest"]) and _ancillary(current) == _ancillary(snapshots[view])
            _require(current == snapshots[view] or shared_owned_write,
                     f"{view} registration changed before its write.")
            if not _points_to(current, paths["manifest"]):
                # Record intent before the write, because a failing registry API
                # may have created a key or written its value before reporting.
                attempted.append(view)
                registry.set_default(view, str(paths["manifest"]))
        after = {view: registry.snapshot(view) for view in VIEWS}
        _require(all(_points_to(state, paths["manifest"]) and
                     _ancillary(state) == _ancillary(snapshots[view]) for view, state in after.items()),
                 "Registration verification failed or ancillary key contents changed.")
        manifest_created = bool(published)
        _require(_manifest_bytes(paths["manifest"]) == (written_bytes if manifest_created else original),
                 "Native manifest changed after registration.")
        final_bundle = _bundle(app_dir, paths, registry, options)
        _require(final_bundle["bundleSha256"] == bundle["bundleSha256"] and
                 final_bundle["buildContract"]["sha256"] == bundle["buildContract"]["sha256"],
                 "Bundle changed after registration; restore this installation.")
        report = inspect_installation(app_dir, browser=browser, environ=environ, registry=registry, **options)
        _require(report["registered"], "Final read-back did not confirm both registrations.")
        report["operations"].update(registryWritten=bool(attempted), manifestWritten=manifest_created,
                                     backupWritten=True)
        receipt = {"completedAt": _now(), "registered": True, "changedViews": attempted,
                   "browser": browser, "registryKey": registry_key(browser),
                   "manifestCreated": manifest_created, "backupDir": str(backup_dir)}
        _write_durable(backup_dir / "result.json", _json_bytes(receipt))
        _sync_directory(backup_dir)
        return {**report, "mode": "install", "idempotent": False, "backupDir": str(backup_dir)}
    except (OSError, ValueError) as exc:
        recovery = _recover(registry, paths, snapshots, attempted, bool(published), written_bytes)
        if backup_dir:
            try:
                _write_durable(backup_dir / "recovery.json", _json_bytes({"failedAt": _now(),
                               "browser": browser, "registryKey": registry_key(browser),
                               "error": str(exc), "recovery": recovery}))
                _sync_directory(backup_dir)
            except OSError as report_error:
                recovery["recoveryReportWriteError"] = str(report_error)
        message = f"Registration failed: {exc}. "
        message += "This attempt's changes were restored." if recovery["ownChangesRestored"] else "Recovery needs review; later changes were retained."
        if backup_dir:
            message += f" Persistent backup: {backup_dir}"
        raise InstallationError(message, backup_dir=backup_dir, recovery=recovery) from exc
    finally:
        # A replaced lock belongs to a later attempt and must be retained.
        _check_no_links(paths["lock"])
        if paths["lock"].exists() and paths["lock"].read_bytes() == lock_data:
            paths["lock"].unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect or register the fixed Console Chat native host; does not approve, enable or start forwarding.")
    parser.add_argument("mode", choices=("inspect", "install"))
    parser.add_argument("--browser", choices=("chrome", "edge"), default="chrome")
    parser.add_argument("--app-dir", help="Defaults to the formal per-user Codex Console installation")
    parser.add_argument("--build-script", default=str(prep.DEFAULT_BUILD_SCRIPT))
    parser.add_argument("--expected-host-sha256")
    parser.add_argument("--expected-extension-sha256")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "install" and (not args.expected_host_sha256 or not args.expected_extension_sha256):
        parser.error("install requires --expected-host-sha256 and --expected-extension-sha256")
    options = {"browser": args.browser, "build_script": args.build_script, "expected_host_sha256": args.expected_host_sha256,
               "expected_extension_sha256": args.expected_extension_sha256}
    try:
        operation = install if args.mode == "install" else inspect_installation
        result = operation(args.app_dir, **options)
    except (InstallationError, prep.PreparationError, OSError) as exc:
        error = {"error": str(exc), "registered": False,
                 "backupDir": getattr(exc, "backup_dir", None), "recovery": getattr(exc, "recovery", None)}
        if args.json:
            print(json.dumps(error, ensure_ascii=False, indent=2))
        else:
            print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Registration checked: {result['browser']}; Console {result['appVersion']}; host {HOST_NAME}.")
        print(f"Host SHA256: {result['hostSha256']}")
        print(f"Extension SHA256: {result['extensionSha256']}")
        print(f"Registered in both HKCU views: {result['registered']}; manifest: {result['manifestPath']}")
        if result.get("backupDir"):
            print(f"Persistent backup: {result['backupDir']}")
        print("No approval, credentials, database, relay enablement, process or browser action was performed.")
        print("No actual browser/Chat round trip was verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
