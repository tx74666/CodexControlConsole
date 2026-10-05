"""Inspect a packaged relay and prepare review materials. Never install or enable it.

This module has no registry, process, network, browser or private-database access.
The public inspect_bundle/inspect_pe/validate_extension functions are read-only.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys

HOST_NAME = "com.tx74666.codex_console_chat_relay"
EXTENSION_ID = "ggjlmdfnbknlicnibfngaenlakeabkfk"
ALLOWED_ORIGIN = f"chrome-extension://{EXTENSION_ID}/"
HOST_RELATIVE = Path("_internal/tools/Codex Chat Relay.exe")
EXTENSION_RELATIVE = Path("_internal/extensions")
DEFAULT_BUILD_SCRIPT = Path(__file__).resolve().parent / "build-windows.ps1"
RUNTIME_FILES = (
    "manifest.json", "service-worker.js", "content-script.js", "lib/protocol.js",
    "popup.html", "popup.css", "popup.js",
)
REGISTRY_KEY = rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}"
OFFICIAL_DOC = "https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging"


class PreparationError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise PreparationError(message)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(path, root):
    return path == root or path.is_relative_to(root)


def _safe_file(path, root):
    path, root = Path(path), Path(root).resolve(strict=True)
    _require(path.is_file(), f"Required file is missing: {path}")
    _require(_inside(path.resolve(strict=True), root), f"Resource escapes its bundle: {path}")
    current = path
    while current != root:
        _require(not current.is_symlink() and not (
            hasattr(current, "is_junction") and current.is_junction()
        ), f"Linked bundle resources are not accepted: {path}")
        current = current.parent
    return path


def _read_json(path, root):
    path = _safe_file(path, root)
    def distinct_keys(pairs):
        value = {}
        for key, item in pairs:
            _require(key not in value, f"Duplicate JSON field in {path}: {key}")
            value[key] = item
        return value
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=distinct_keys)
    except (ValueError, UnicodeError) as exc:
        raise PreparationError(f"Invalid JSON: {path}") from exc
    _require(type(value) is dict, f"Expected a JSON object: {path}")
    return value


def _fingerprint(path, relative):
    return {"path": Path(relative).as_posix(), "size": path.stat().st_size,
            "sha256": _sha256(path)}


def inspect_pe(path):
    """Validate a real AMD64 PE32+ console executable's headers and sections."""
    path = Path(path)
    _require(path.is_file(), f"Native host executable is missing: {path}")
    size = path.stat().st_size
    with path.open("rb") as stream:
        dos = stream.read(64)
        _require(len(dos) == 64 and dos[:2] == b"MZ", "Host has no complete DOS/PE header.")
        pe_offset = struct.unpack_from("<I", dos, 60)[0]
        _require(64 <= pe_offset <= size - 24, "Invalid PE header offset.")
        stream.seek(pe_offset)
        header = stream.read(24)
        _require(header[:4] == b"PE\0\0", "Host has no PE signature.")
        machine, sections, _, _, _, optional_size, characteristics = struct.unpack("<HHIIIHH", header[4:])
        _require(machine == 0x8664, "Native host must be AMD64 (x64).")
        _require(1 <= sections <= 96, "Invalid PE section count.")
        _require(characteristics & 0x0002 and not characteristics & 0x2000,
                 "Native host must be an executable, not a DLL.")
        _require(optional_size >= 112 and pe_offset + 24 + optional_size + sections * 40 <= size,
                 "Incomplete PE optional header or section table.")
        optional = stream.read(optional_size)
        _require(struct.unpack_from("<H", optional)[0] == 0x20B, "Native host must use PE32+.")
        subsystem = struct.unpack_from("<H", optional, 68)[0]
        _require(subsystem == 3, "Native host must use console subsystem 3 for stdin/stdout.")
        header_size = struct.unpack_from("<I", optional, 60)[0]
        _require(pe_offset + 24 + optional_size + sections * 40 <= header_size <= size,
                 "Invalid PE SizeOfHeaders.")
        executable_section = False
        ranges = []
        for _ in range(sections):
            section = stream.read(40)
            raw_size, raw_offset = struct.unpack_from("<II", section, 16)
            flags = struct.unpack_from("<I", section, 36)[0]
            if raw_size:
                _require(header_size <= raw_offset and raw_offset + raw_size <= size,
                         "PE section data is outside the file.")
                _require(all(raw_offset >= end or raw_offset + raw_size <= start for start, end in ranges),
                         "Overlapping PE section data.")
                ranges.append((raw_offset, raw_offset + raw_size))
            executable_section |= bool(raw_size and flags & 0x20000000)
        _require(executable_section, "PE has no executable section data.")
    return {"machine": "amd64", "machineCode": machine, "optionalHeader": "PE32+",
            "subsystem": "console", "subsystemCode": subsystem, "sections": sections,
            "size": size, "sha256": _sha256(path), "executed": False}


def validate_extension(extension_dir):
    """Check the fixed extension identity, narrow manifest and all packaged assets."""
    original_root = Path(extension_dir)
    _require(not original_root.is_symlink() and not (
        hasattr(original_root, "is_junction") and original_root.is_junction()
    ), "Linked extension directories are not accepted.")
    root = original_root.resolve(strict=True)
    manifest = _read_json(root / "manifest.json", root)
    _require(set(manifest) == {
        "manifest_version", "name", "version", "key", "description", "permissions",
        "host_permissions", "background", "action", "options_ui", "content_scripts", "content_security_policy",
    }, "Extension manifest has unexpected or missing fields; permission changes require review.")
    _require(manifest.get("manifest_version") == 3, "Extension must use manifest version 3.")
    _require(manifest.get("permissions") == ["nativeMessaging", "storage"],
             "Extension permissions must be exactly nativeMessaging and storage.")
    _require(manifest.get("host_permissions") == ["https://chatgpt.com/*"],
             "Extension host permissions must be exactly https://chatgpt.com/*.")
    _require(manifest.get("background") == {"service_worker": "service-worker.js"},
             "Unexpected extension background worker.")
    _require(manifest.get("action") == {"default_title": "Console Chat 转发", "default_popup": "popup.html"},
             "Unexpected extension popup contract.")
    _require(manifest.get("options_ui") == {"page": "popup.html", "open_in_tab": True},
             "Extension options must open only the existing local setup page in a tab.")
    _require(manifest.get("content_scripts") == [{
        "matches": ["https://chatgpt.com/*"], "js": ["lib/protocol.js", "content-script.js"],
        "run_at": "document_idle", "all_frames": False,
    }], "Unexpected content script scope, resources or frame access.")
    _require(manifest.get("content_security_policy") == {
        "extension_pages": "script-src 'self'; object-src 'none'"
    }, "Unexpected extension content security policy.")
    _require(isinstance(manifest.get("key"), str), "Extension public key is missing.")
    try:
        public_der = base64.b64decode(manifest["key"], validate=True)
    except (ValueError, TypeError) as exc:
        raise PreparationError("Extension public key is not valid base64.") from exc
    extension_id = "".join(chr(ord("a") + int(nibble, 16))
                           for nibble in hashlib.sha256(public_der).hexdigest()[:32])
    _require(extension_id == EXTENSION_ID, "Extension public key does not match the fixed extension ID.")
    for relative in RUNTIME_FILES:
        _safe_file(root / relative, root)
    protocol = (root / "lib/protocol.js").read_text(encoding="utf-8")
    for symbol, expected in (("HOST_NAME", HOST_NAME), ("EXTENSION_ID", EXTENSION_ID)):
        values = re.findall(rf'\b{symbol}\s*=\s*"([^"\r\n]+)"', protocol)
        _require(values == [expected], f"Protocol {symbol} does not match the fixed contract.")
    popup = (root / "popup.html").read_text(encoding="utf-8")
    references = re.findall(r'(?:src|href)\s*=\s*[\"\']([^\"\']+)[\"\']', popup)
    _require(sorted(references) == ["popup.css", "popup.js"], "Unexpected popup resource references.")
    resources = []
    directories = [root]
    while directories:
        directory = directories.pop()
        # Check directory links before descending, including Windows junctions.
        for path in sorted(directory.iterdir()):
            _require(not path.is_symlink() and not (hasattr(path, "is_junction") and path.is_junction()),
                     f"Linked extension resource is not accepted: {path}")
            if path.is_dir():
                _require(_inside(path.resolve(strict=True), root), f"Directory escapes its bundle: {path}")
                directories.append(path)
            elif path.is_file():
                _safe_file(path, root)
                resources.append(_fingerprint(path, path.relative_to(root)))
    resources.sort(key=lambda item: item["path"])
    fingerprint = hashlib.sha256(_json(resources).encode("utf-8")).hexdigest()
    return {"id": extension_id, "version": manifest["version"], "hostName": HOST_NAME,
            "permissions": manifest["permissions"], "hostPermissions": manifest["host_permissions"],
            "manifestSha256": _sha256(root / "manifest.json"), "sha256": fingerprint,
            "resources": resources, "installed": False, "enabled": None,
            "runtimeStateObserved": False}


def _build_contract(build_script):
    path = Path(build_script).resolve(strict=True)
    script = path.read_text(encoding="utf-8-sig")
    fragments = (
        '$ChatRelayHostExe = Join-Path $GeneratedToolsDir "Codex Chat Relay.exe"',
        '--onefile --console', 'tools\\console-chat-relay-host.py',
        '@{ Source = $ChatRelayHostExe; Destination = "tools" }',
        '@{ Source = "extensions\\console-chat-relay"; Destination = "extensions" }',
        '"--onedir"', '"--windowed"', '"_internal\\app-manifest.json"',
    )
    _require(all(fragment in script for fragment in fragments) and "--contents-directory" not in script,
             "Build script no longer matches the reviewed PyInstaller bundle layout.")
    return {"path": str(path), "sha256": _sha256(path),
            "hostBuild": "PyInstaller --onefile --console", "appBuild": "PyInstaller --onedir --windowed",
            "hostRelativePath": HOST_RELATIVE.as_posix(),
            "extensionRelativePath": EXTENSION_RELATIVE.as_posix(),
            "layoutEvidence": "Data destination extensions contains the source directory's contents; PyInstaller onedir uses _internal."}


def _expected(actual, expected, label):
    if expected is not None:
        _require(isinstance(expected, str) and re.fullmatch(r"[0-9a-fA-F]{64}", expected),
                 f"Expected {label} SHA256 must contain 64 hex digits.")
        _require(actual == expected.lower(), f"{label} SHA256 differs from the supplied trusted fingerprint.")


def inspect_bundle(app_dir, *, build_script=None, expected_host_sha256=None,
                   expected_extension_sha256=None, fixture=False):
    """Read only. Fingerprints identify bytes; they are not a code-signing assertion."""
    app = Path(app_dir).resolve(strict=True)
    _require(app.is_dir(), "Application bundle must be an existing directory.")
    contract = _build_contract(build_script or DEFAULT_BUILD_SCRIPT)
    app_manifest_path = app / "_internal/app-manifest.json"
    app_manifest = _read_json(app_manifest_path, app)
    _require(app_manifest.get("installMode") in {"installed", "portable"},
             "Only installed/portable bundles contain this optional native host; source/store is not a substitute.")
    _require(isinstance(app_manifest.get("version"), str) and
             re.fullmatch(r"\d+\.\d+\.\d+", app_manifest["version"]), "Invalid bundled application version.")
    host_path = _safe_file(app / HOST_RELATIVE, app)
    host = inspect_pe(host_path)
    _safe_file(app / EXTENSION_RELATIVE / "manifest.json", app)
    extension = validate_extension(app / EXTENSION_RELATIVE)
    _expected(host["sha256"], expected_host_sha256, "host")
    _expected(extension["sha256"], expected_extension_sha256, "extension bundle")
    resources = [_fingerprint(app_manifest_path, app_manifest_path.relative_to(app)),
                 _fingerprint(host_path, HOST_RELATIVE)]
    resources.extend({**item, "path": (EXTENSION_RELATIVE / item["path"]).as_posix()}
                     for item in extension["resources"])
    return {"format": "codex-console-chat-relay-preparation", "version": 1,
            "inspectionOnly": True, "fixture": bool(fixture), "appDir": str(app),
            "appVersion": app_manifest["version"], "installMode": app_manifest["installMode"],
            "hostPath": str(host_path), "extensionDir": str(app / EXTENSION_RELATIVE),
            "host": host, "extension": extension, "buildContract": contract,
            "resources": resources,
            "bundleSha256": hashlib.sha256(_json(resources).encode("utf-8")).hexdigest(),
            "trustedFingerprintChecked": {"host": expected_host_sha256 is not None,
                                          "extension": expected_extension_sha256 is not None},
            "operations": {"registryRead": False, "registryWritten": False, "installed": False,
                           "hostExecuted": False, "browserOpened": False, "approvalCreated": False,
                           "privateDataRead": False, "relayEnabled": False},
            "limitations": ["No Chrome, installation, runtime approval or actual Chat round trip has been verified.",
                            "SHA256 records the inspected bytes; without a supplied trusted fingerprint it does not prove release provenance."]}


def _output_target(output_dir, app):
    output = Path(output_dir).absolute()
    parent = output.parent.resolve(strict=True)
    output = parent / output.name
    _require(not output.exists() and not output.is_symlink(), "Output directory must not already exist; nothing will be overwritten.")
    _require(not _inside(output, Path(app).resolve(strict=True)), "Review output cannot be written inside the inspected application bundle.")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        protected = (Path(local_app_data) / "CodexControlConsole").resolve()
        _require(not _inside(output.resolve(), protected), "Review output cannot be written to Console user-data directories.")
    return output


def prepare_bundle(app_dir, output_dir, **options):
    """Create a new review folder only. No registration/approval/install action exists."""
    report = inspect_bundle(app_dir, **options)
    output = _output_target(output_dir, report["appDir"])
    manifest_path = output / f"{HOST_NAME}.review-only.json"
    native_manifest = {"name": HOST_NAME, "description": "Codex Console Chat relay (review preparation only)",
                       "path": report["hostPath"], "type": "stdio", "allowed_origins": [ALLOWED_ORIGIN]}
    plan = {"reviewOnly": True, "requiresExplicitApproval": True, "performed": False,
            "hive": "HKEY_CURRENT_USER", "key": REGISTRY_KEY,
            "valueName": "", "valueType": "REG_SZ", "valueData": str(manifest_path),
            "priorRegistryState": "not_read", "registryViews": ["32-bit", "64-bit"],
            "recovery": {"beforeAnyApprovedWrite": "Capture the prior key/value/type in both registry views. No backup has been captured by this tool.",
                         "ifOriginallyAbsent": "Remove only this host key, and only if its current default value still equals this manifest path.",
                         "ifOriginallyPresent": "Restore exactly the recorded prior value/type in the changed view; retain unrelated or later changes.",
                         "preserve": "Never remove the Chrome or NativeMessagingHosts parent keys or other hosts."}}
    readme = f"""# Console Chat 转发器：待审核安装材料

这只是准备材料。没有注册、安装、启用、批准或实际发送。
{'本次检查使用隔离 fixture，不能作为正式 exe 验收。' if report['fixture'] else '本次只读检查指定应用目录；没有运行其中的 exe。'}

- 应用：{report['appVersion']}（{report['installMode']}）
- Native host：`{report['hostPath']}`
- PE：AMD64 / PE32+ / console subsystem 3
- Host SHA256：`{report['host']['sha256']}`
- 扩展目录：`{report['extensionDir']}`
- 扩展 ID：`{EXTENSION_ID}`
- 扩展资源 SHA256：`{report['extension']['sha256']}`
- Host 名称：`{HOST_NAME}`
- 权限仅 `nativeMessaging`、`storage`；页面范围仅 `https://chatgpt.com/*`。

`inspection.json` 保存逐文件大小、SHA256 和实际构建脚本证据。未提供可信发布指纹时，计算指纹不能证明这些文件来自可信发布；审核前须核对来源。文件更新后需重新检查，不能沿用旧计划。

## 待审核注册计划

`{manifest_path.name}` 是 Native Messaging manifest 的审核稿。
`registration-plan.json` 仅描述 HKCU 默认 REG_SZ 值到该稿的路径；没有执行注册命令。Chrome 会先查 32 位注册表视图，再查 64 位视图，后续审批必须核对两者，避免旧值遮挡。
注册本身不代表扩展已安装、转发已获批准或真实 Chat 已验证。扩展默认为停用，本工具没有读取运行时启用状态或生成批准文件。批准、扩展安装和真实 Chrome 验收需在后续明确授权后另行完成。

## 恢复规则

任何未来获准的注册写入前，先保存两种注册表视图中该 host 的原键、默认值及类型；本工具没有读取它们，也没有产生可用注册表备份。
若原键不存在，仅当该 host 当前值仍指向本稿时才删除这一个 host 键。若原键存在，恢复记录的原值与类型；发现后来改动就停止核对，不能覆盖。保留 Chrome、NativeMessagingHosts 父键及其他 host。

官方协议：[Chrome Native Messaging]({OFFICIAL_DOC})。
"""
    # Re-read before creating any output: a changed executable/resource needs fresh review.
    refreshed = inspect_bundle(app_dir, **options)
    _require(refreshed["bundleSha256"] == report["bundleSha256"] and
             refreshed["buildContract"]["sha256"] == report["buildContract"]["sha256"],
             "Bundle changed during preparation; no output was written.")
    output.mkdir(exist_ok=False)
    for filename, value in ((manifest_path.name, native_manifest), ("registration-plan.json", plan),
                            ("inspection.json", report), ("PREPARATION.md", readme)):
        with (output / filename).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    return {**report, "reviewOutputDir": str(output), "registrationPlan": plan,
            "reviewManifest": str(manifest_path)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only inspection or preparation of review-only Chat relay materials. Never installs/enables/registers.")
    parser.add_argument("mode", choices=("inspect", "prepare"))
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--output-dir", help="New review folder only, required for prepare")
    parser.add_argument("--build-script", default=str(DEFAULT_BUILD_SCRIPT))
    parser.add_argument("--expected-host-sha256")
    parser.add_argument("--expected-extension-sha256")
    parser.add_argument("--fixture", action="store_true", help="Label isolated test material; does not relax validation")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if (args.mode == "prepare") != bool(args.output_dir):
        parser.error("prepare requires --output-dir; inspect must not have --output-dir")
    options = {"build_script": args.build_script, "expected_host_sha256": args.expected_host_sha256,
               "expected_extension_sha256": args.expected_extension_sha256, "fixture": args.fixture}
    try:
        result = prepare_bundle(args.app_dir, args.output_dir, **options) if args.mode == "prepare" else inspect_bundle(args.app_dir, **options)
    except (PreparationError, OSError) as exc:
        print(f"Preparation refused: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Inspection passed: Console {result['appVersion']}; AMD64 console host; extension {EXTENSION_ID}.")
        print(f"Host SHA256: {result['host']['sha256']}")
        print(f"Extension assets SHA256: {result['extension']['sha256']}")
        if args.fixture:
            print("Isolated fixture only; not production binary acceptance.")
        if args.mode == "prepare":
            print(f"Review materials: {result['reviewOutputDir']}")
        print("No installation, registry access, approval, browser or relay enablement was performed.")
        print("No actual Chrome/Chat round trip was verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
