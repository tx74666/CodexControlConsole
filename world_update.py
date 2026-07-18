from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile

from console_update import (
    MAX_ARCHIVE_FILES,
    MAX_EXTRACTED_BYTES,
    ConsoleUpdateService,
    _hidden_subprocess_kwargs,
    _is_newer,
    _version_tuple,
)


WORLD_REPOSITORY = "tx74666/CodexWorldConsole"
WORLD_EXECUTABLE = "Codex World.exe"
WORLD_README = "README-FIRST.txt"
WORLD_VERSION_PATTERN = re.compile(r"(?im)^Version:\s*v?(\d+\.\d+\.\d+)\s*$")


class WorldUpdateService(ConsoleUpdateService):
    def __init__(self, app_dir, data_dir, source_dir):
        super().__init__(
            app_dir,
            data_dir,
            {
                "name": "Codex World",
                "version": "0.0.0",
                "repository": WORLD_REPOSITORY,
                "installMode": "portable",
                "edition": "windows",
            },
            "windows",
        )
        self.source_dir = Path(source_dir).expanduser().resolve()
        self.managed_root = (self.data_dir / "apps" / "CodexWorld").resolve()
        self.active_file = self.managed_root / "current.json"
        self.state_file = self.data_dir / "cache" / "world_update_state.json"
        self.result_file = self.data_dir / "cache" / "world_update_result.json"
        self.update_dir = self.data_dir / "updates" / "world"

    def _active_install(self):
        try:
            record = json.loads(self.active_file.read_text(encoding="utf-8"))
            relative = Path(str(record.get("path") or ""))
            directory = (self.managed_root / relative).resolve()
            directory.relative_to(self.managed_root)
            version = str(record.get("version") or "").lstrip("v")
        except (OSError, ValueError, json.JSONDecodeError, AttributeError):
            return None
        executable = directory / WORLD_EXECUTABLE
        if not executable.is_file() or not _version_tuple(version):
            return None
        return {
            "directory": directory,
            "executable": executable,
            "version": version,
        }

    @staticmethod
    def _manifest_version(directory):
        path = Path(directory) / "app-manifest.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return ""
        version = str(payload.get("version") or "").lstrip("v") if isinstance(payload, dict) else ""
        return version if _version_tuple(version) else ""

    @staticmethod
    def _readme_version(directory):
        path = Path(directory) / WORLD_README
        try:
            content = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return ""
        match = WORLD_VERSION_PATTERN.search(content)
        return match.group(1) if match else ""

    def _source_version(self):
        if not self.source_dir.is_dir():
            return ""
        version = self._manifest_version(self.source_dir) or self._readme_version(self.source_dir)
        if version:
            return version
        if not (self.source_dir / ".git").exists():
            return ""
        try:
            completed = subprocess.run(
                [
                    "git",
                    "-c",
                    f"safe.directory={self.source_dir.as_posix()}",
                    "describe",
                    "--tags",
                    "--abbrev=0",
                ],
                cwd=str(self.source_dir),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
                **_hidden_subprocess_kwargs(),
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        version = completed.stdout.strip().lstrip("v") if completed.returncode == 0 else ""
        return version if _version_tuple(version) else ""

    def _source_launch_target(self):
        launcher = self.source_dir / "Start-WorldConsole.vbs"
        if launcher.is_file():
            return launcher
        server = self.source_dir / "world_console.py"
        return server if server.is_file() else None

    @staticmethod
    def _registered_install():
        if sys.platform != "win32":
            return None
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Codex\Codex World") as key:
                directory = Path(str(winreg.QueryValueEx(key, "InstallPath")[0])).expanduser().resolve()
                version = str(winreg.QueryValueEx(key, "Version")[0]).lstrip("v")
        except (OSError, ValueError):
            return None
        executable = directory / WORLD_EXECUTABLE
        if not executable.is_file() or not _version_tuple(version):
            return None
        return {
            "mode": "installed",
            "directory": directory,
            "executable": executable,
            "version": version,
        }

    def _installation(self):
        active = self._active_install()
        if active:
            return {"mode": "managed", **active}
        source_version = self._source_version()
        source_target = self._source_launch_target()
        if source_target:
            return {
                "mode": "source",
                "directory": self.source_dir,
                "executable": source_target,
                "version": source_version or "0.0.0",
            }
        registered = self._registered_install()
        if registered:
            return registered
        return {
            "mode": "missing",
            "directory": self.managed_root,
            "executable": None,
            "version": "0.0.0",
        }

    @property
    def current_version(self):
        return self._installation()["version"]

    @property
    def portable(self):
        return self._installation()["mode"] != "source"

    def _edition(self):
        return "windows"

    def _asset_name(self):
        return "Codex-World-Setup-x64.exe"

    def _fetch_latest_manifest(self):
        return super()._fetch_latest_api()

    def status(self, check=False, force=False):
        state = self._read_state()
        if force or (check and state["autoCheck"] and self._check_is_stale(state)):
            return self.check()
        latest = state.get("latest") or {}
        latest_version = str(latest.get("version") or "")
        installation = self._installation()
        current_version = str(installation.get("version") or "0.0.0")
        installed = installation["mode"] != "missing"
        asset_name = self._asset_name()
        asset = next((item for item in latest.get("assets") or [] if item.get("name") == asset_name), {})
        pending = state.get("pending") or {}
        pending_archive = Path(str(pending.get("archive") or ""))
        available = bool(latest_version and (not installed or _is_newer(latest_version, current_version)))
        can_install = bool(
            available
            and installation["mode"] != "source"
            and sys.platform == "win32"
            and asset
        )
        return {
            "ok": True,
            "product": "world",
            "currentVersion": current_version if installed else "",
            "latestVersion": latest_version,
            "available": available,
            "installed": installed,
            "installationMode": installation["mode"],
            "installationPath": str(installation["directory"]),
            "autoCheck": state["autoCheck"],
            "checkedAt": state.get("checkedAt") or "",
            "releaseUrl": latest.get("url") or f"https://github.com/{self.repository}/releases/latest",
            "publishedAt": latest.get("publishedAt") or "",
            "assetName": asset_name,
            "assetAvailable": bool(asset),
            "portable": installation["mode"] != "source",
            "canInstall": can_install,
            "canOpen": bool(installation.get("executable")),
            "staged": bool(pending_archive.is_file()),
            "stagedVersion": str(pending.get("version") or ""),
            "error": str(state.get("error") or ""),
            "updateError": "",
            "edition": "windows",
        }

    @staticmethod
    def _archive_members(package, expected_version=""):
        members = []
        normalized_paths = set()
        file_count = 0
        extracted_bytes = 0
        readme_content = ""
        executable_found = False
        for item in package.infolist():
            path = PurePosixPath(item.filename.replace("\\", "/"))
            if (
                path.is_absolute()
                or ".." in path.parts
                or not path.parts
                or any(":" in part or "\x00" in part for part in path.parts)
            ):
                raise ValueError("The Codex World archive contains an unsafe path")
            mode = (item.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError("The Codex World archive contains a symbolic link")
            normalized = "/".join(path.parts).casefold()
            if normalized in normalized_paths:
                raise ValueError("The Codex World archive contains duplicate paths")
            normalized_paths.add(normalized)
            if item.is_dir():
                members.append((item, path))
                continue
            file_count += 1
            extracted_bytes += max(0, int(item.file_size))
            if file_count > MAX_ARCHIVE_FILES or extracted_bytes > MAX_EXTRACTED_BYTES:
                raise ValueError("The Codex World archive expands beyond the allowed limit")
            if path.name.casefold() == WORLD_EXECUTABLE.casefold():
                executable_found = True
            if path.name.casefold() == WORLD_README.casefold():
                readme_content = package.read(item).decode("utf-8-sig", errors="replace")
            members.append((item, path))
        if not executable_found:
            raise ValueError("The Codex World archive has no application executable")
        match = WORLD_VERSION_PATTERN.search(readme_content)
        archive_version = match.group(1) if match else ""
        if not _version_tuple(archive_version) or (expected_version and archive_version != expected_version):
            raise ValueError("The Codex World archive version does not match the release")
        broken = package.testzip()
        if broken:
            raise ValueError(f"The Codex World archive is damaged: {broken}")
        return archive_version, members

    def _validate_archive(self, archive, expected_version=""):
        try:
            with zipfile.ZipFile(archive) as package:
                self._archive_members(package, expected_version)
        except zipfile.BadZipFile as error:
            raise ValueError("The downloaded Codex World update is not a valid ZIP") from error

    def _extract_archive(self, archive, destination, expected_version):
        with zipfile.ZipFile(archive) as package:
            archive_version, members = self._archive_members(package, expected_version)
            for item, path in members:
                target = (destination / Path(*path.parts)).resolve()
                try:
                    target.relative_to(destination.resolve())
                except ValueError as error:
                    raise ValueError("The Codex World archive escaped the install directory") from error
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(item) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
        return archive_version

    def _write_active_install(self, version, directory):
        relative = directory.resolve().relative_to(self.managed_root)
        payload = {
            "version": version,
            "path": relative.as_posix(),
            "installedAt": datetime.now(timezone.utc).isoformat(),
        }
        self.active_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.active_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.active_file)

    def install(self):
        installation = self._installation()
        if installation["mode"] == "source":
            raise ValueError("Codex World is a source checkout on this device; update it through GitHub Desktop")
        return super().install()

    def open(self):
        installation = self._installation()
        target = installation.get("executable")
        if not target:
            return self.open_release()
        target = Path(target)
        if target.suffix.casefold() == ".vbs":
            command = ["wscript.exe", str(target)]
        elif target.suffix.casefold() == ".py":
            command = [sys.executable, str(target)]
        else:
            command = [str(target)]
        subprocess.Popen(
            command,
            cwd=str(target.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **_hidden_subprocess_kwargs(),
        )
        return {"ok": True, "path": str(target), "version": installation.get("version") or ""}

    def open_release(self):
        url = self.status().get("releaseUrl") or f"https://github.com/{self.repository}/releases/latest"
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "github.com":
            raise ValueError("The Codex World release URL is invalid")
        webbrowser.open(url)
        return {"ok": True, "url": url}
