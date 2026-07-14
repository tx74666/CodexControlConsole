from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile


MAX_ARCHIVE_FILES = 50_000
MAX_EXTRACTED_BYTES = 4 * 1024 * 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def hidden_subprocess_kwargs():
    if sys.platform != "win32":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def write_result(data_dir, ok, message, version=""):
    target = data_dir / "cache" / "update_result.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ok": bool(ok),
        "message": str(message or "")[:1000],
        "version": str(version or ""),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)


def process_is_running(pid):
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def wait_for_process(pid, timeout=45):
    deadline = time.monotonic() + timeout
    while process_is_running(pid) and time.monotonic() < deadline:
        time.sleep(0.2)
    if process_is_running(pid):
        raise RuntimeError("Codex Console did not close before the update timeout")


def validate_member(item):
    path = PurePosixPath(item.filename.replace("\\", "/"))
    if (
        path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or any(":" in part or "\x00" in part for part in path.parts)
    ):
        raise RuntimeError("Update archive contains an unsafe path")
    mode = (item.external_attr >> 16) & 0o170000
    if mode == 0o120000:
        raise RuntimeError("Update archive contains a symbolic link")


def archive_sha256(archive):
    digest = hashlib.sha256()
    with archive.open("rb") as source:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().lower()


def validate_archive(archive, expected_sha256="", expected_version=""):
    checksum = str(expected_sha256 or "").strip().lower()
    if checksum:
        if not SHA256_PATTERN.fullmatch(checksum) or archive_sha256(archive) != checksum:
            raise RuntimeError("Verified update checksum no longer matches")
    try:
        with zipfile.ZipFile(archive) as package:
            file_count = 0
            extracted_bytes = 0
            normalized_paths = set()
            for item in package.infolist():
                validate_member(item)
                if item.is_dir():
                    continue
                path = PurePosixPath(item.filename.replace("\\", "/"))
                normalized = "/".join(path.parts).casefold()
                if normalized in normalized_paths:
                    raise RuntimeError("Update archive contains duplicate paths")
                normalized_paths.add(normalized)
                file_count += 1
                extracted_bytes += max(0, int(item.file_size))
                if file_count > MAX_ARCHIVE_FILES or extracted_bytes > MAX_EXTRACTED_BYTES:
                    raise RuntimeError("Update archive expands beyond the allowed limit")
            try:
                manifest = json.loads(package.read("app-manifest.json").decode("utf-8-sig"))
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise RuntimeError("Update archive has no valid app manifest") from error
            if not isinstance(manifest, dict):
                raise RuntimeError("Update archive has no valid app manifest")
            version = str(manifest.get("version") or "").lstrip("v")
            if expected_version and version != str(expected_version).lstrip("v"):
                raise RuntimeError("Update archive version does not match the requested release")
            if manifest.get("name") != "Codex Control Console" or str(manifest.get("installMode") or "").lower() != "portable":
                raise RuntimeError("Update archive is not a Codex Console portable release")
            broken = package.testzip()
            if broken:
                raise RuntimeError(f"Update archive is damaged: {broken}")
    except zipfile.BadZipFile as error:
        raise RuntimeError("Verified update is not a valid ZIP") from error


def apply_archive(archive, app_dir, data_dir, expected_sha256="", expected_version=""):
    update_root = data_dir / "updates"
    update_root.mkdir(parents=True, exist_ok=True)
    validate_archive(archive, expected_sha256=expected_sha256, expected_version=expected_version)
    extraction = Path(tempfile.mkdtemp(prefix="codex-update-", dir=str(update_root))).resolve()
    backup = Path(tempfile.mkdtemp(prefix="codex-backup-", dir=str(update_root))).resolve()
    changes = []
    try:
        with zipfile.ZipFile(archive) as package:
            package.extractall(extraction)

        for source in extraction.rglob("*"):
            if source.is_symlink() or not source.is_file():
                continue
            relative = source.relative_to(extraction)
            target = (app_dir / relative).resolve()
            try:
                target.relative_to(app_dir)
            except ValueError as error:
                raise RuntimeError("Update target escaped the application directory") from error
            target.parent.mkdir(parents=True, exist_ok=True)
            backup_target = backup / relative
            existed = target.exists()
            if existed:
                if not target.is_file() or target.is_symlink():
                    raise RuntimeError(f"Update target is not a regular file: {relative}")
                backup_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup_target)
            changes.append((target, backup_target, existed))
            temporary = target.with_name(target.name + ".update-new")
            shutil.copy2(source, temporary)
            os.replace(temporary, target)
    except Exception:
        rollback_errors = []
        for target, backup_target, existed in reversed(changes):
            try:
                target.with_name(target.name + ".update-new").unlink(missing_ok=True)
                if existed:
                    restore = target.with_name(target.name + ".update-restore")
                    shutil.copy2(backup_target, restore)
                    os.replace(restore, target)
                else:
                    target.unlink(missing_ok=True)
            except OSError as error:
                rollback_errors.append(str(error))
        if rollback_errors:
            raise RuntimeError("Update failed and could not fully roll back: " + rollback_errors[0])
        raise
    finally:
        if extraction.is_dir() and extraction.parent == update_root.resolve():
            shutil.rmtree(extraction, ignore_errors=True)
        if backup.is_dir() and backup.parent == update_root.resolve():
            shutil.rmtree(backup, ignore_errors=True)


def launch_console(launcher):
    if sys.platform == "win32" and launcher.suffix.lower() == ".vbs":
        subprocess.Popen(
            ["wscript.exe", str(launcher)],
            cwd=str(launcher.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **hidden_subprocess_kwargs(),
        )
    else:
        subprocess.Popen([str(launcher)], cwd=str(launcher.parent), **hidden_subprocess_kwargs())


def main():
    parser = argparse.ArgumentParser(description="Apply a verified Codex Console update")
    parser.add_argument("--archive", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--launcher", required=True)
    parser.add_argument("--pid", required=True, type=int)
    args = parser.parse_args()

    archive = Path(args.archive).resolve()
    app_dir = Path(args.app_dir).resolve()
    data_dir = Path(args.data_dir).resolve()
    launcher = Path(args.launcher).resolve()
    ok = False
    message = ""
    try:
        if not archive.is_file() or archive.suffix.lower() != ".zip":
            raise RuntimeError("Verified update archive is missing")
        wait_for_process(args.pid)
        apply_archive(
            archive,
            app_dir,
            data_dir,
            expected_sha256=args.sha256,
            expected_version=args.version,
        )
        pending = data_dir / "cache" / "update_state.json"
        if pending.is_file():
            try:
                state = json.loads(pending.read_text(encoding="utf-8"))
                if isinstance(state, dict):
                    state["pending"] = {}
                    temporary = pending.with_suffix(".tmp")
                    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                    os.replace(temporary, pending)
            except (OSError, json.JSONDecodeError):
                pass
        archive.unlink(missing_ok=True)
        ok = True
        message = "Codex Console was updated successfully"
    except Exception as error:
        message = str(error)
    write_result(data_dir, ok, message, args.version)
    launch_console(launcher)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
