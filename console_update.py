from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile


CHECK_INTERVAL_SECONDS = 6 * 60 * 60
MAX_RELEASE_BYTES = 1_500 * 1024 * 1024
MAX_CHECKSUM_BYTES = 1024 * 1024
MAX_ARCHIVE_FILES = 50_000
MAX_EXTRACTED_BYTES = 4 * 1024 * 1024 * 1024
VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")
SHA256_PATTERN = re.compile(r"\b([0-9a-fA-F]{64})\b")


def _hidden_subprocess_kwargs():
    if sys.platform != "win32":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _powershell_literal(value):
    return "'" + str(value or "").replace("'", "''") + "'"


def _version_tuple(value):
    match = VERSION_PATTERN.fullmatch(str(value or "").strip())
    return tuple(int(match.group(index)) for index in range(1, 4)) if match else None


def _is_newer(candidate, current):
    candidate_tuple = _version_tuple(candidate)
    current_tuple = _version_tuple(current)
    return bool(candidate_tuple and current_tuple and candidate_tuple > current_tuple)


def _safe_release_url(value):
    raw = str(value or "").strip()
    parsed = urllib.parse.urlparse(raw)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "github.com" or host.endswith(".github.com")):
        return ""
    return raw


class ConsoleUpdateService:
    def __init__(self, app_dir, data_dir, manifest, edition_provider, shutdown_callback=None):
        self.app_dir = Path(app_dir).resolve()
        self.data_dir = Path(data_dir).resolve()
        self.manifest = dict(manifest or {})
        self.edition_provider = edition_provider
        self.shutdown_callback = shutdown_callback
        self.state_file = self.data_dir / "cache" / "update_state.json"
        self.result_file = self.data_dir / "cache" / "update_result.json"
        self.update_dir = self.data_dir / "updates"
        self._lock = threading.RLock()

    @property
    def current_version(self):
        return str(self.manifest.get("version") or "0.0.0-dev").strip()

    @property
    def repository(self):
        return str(self.manifest.get("repository") or "tx74666/CodexControlConsole").strip()

    @property
    def portable(self):
        return str(self.manifest.get("installMode") or "source").lower() in {"portable", "installed"}

    def _default_state(self):
        return {
            "autoCheck": True,
            "checkedAt": "",
            "latest": {},
            "pending": {},
            "error": "",
        }

    def _read_state(self):
        with self._lock:
            try:
                payload = json.loads(self.state_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            state = self._default_state()
            if isinstance(payload, dict):
                state.update(payload)
            state["autoCheck"] = bool(state.get("autoCheck", True))
            state["latest"] = state.get("latest") if isinstance(state.get("latest"), dict) else {}
            state["pending"] = state.get("pending") if isinstance(state.get("pending"), dict) else {}
            return state

    def _write_state(self, state):
        with self._lock:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.state_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, self.state_file)

    def _request(self, url, accept="application/vnd.github+json", timeout=20):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": accept,
                "User-Agent": f"CodexControlConsole/{self.current_version}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        return urllib.request.urlopen(request, timeout=timeout)

    def _edition(self):
        value = self.edition_provider() if callable(self.edition_provider) else self.edition_provider
        return "lite" if str(value or "").lower() == "lite" else "developer"

    def _asset_name(self):
        return "CodexControlConsole-Setup-x64.exe"

    def _check_is_stale(self, state):
        try:
            checked = datetime.fromisoformat(str(state.get("checkedAt") or "").replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - checked).total_seconds() >= CHECK_INTERVAL_SECONDS
        except ValueError:
            return True

    def _last_install_error(self):
        try:
            payload = json.loads(self.result_file.read_text(encoding="utf-8"))
            updated = datetime.fromisoformat(str(payload.get("updatedAt") or "").replace("Z", "+00:00"))
        except (OSError, ValueError, json.JSONDecodeError, AttributeError):
            return ""
        if payload.get("ok") or (datetime.now(timezone.utc) - updated).days >= 7:
            return ""
        return str(payload.get("message") or "The previous update could not be installed")[:500]

    def check(self):
        state = self._read_state()
        try:
            state["latest"] = self._fetch_latest_manifest()
            state["checkedAt"] = datetime.now(timezone.utc).isoformat()
            state["error"] = ""
        except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError):
            try:
                state["latest"] = self._fetch_latest_api()
                state["checkedAt"] = datetime.now(timezone.utc).isoformat()
                state["error"] = ""
            except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as error:
                state["checkedAt"] = datetime.now(timezone.utc).isoformat()
                state["error"] = str(error)[:500]
        self._write_state(state)
        return self.status()

    def _normalize_latest(self, payload, api=False):
        if not isinstance(payload, dict):
            raise ValueError("The update manifest is invalid")
        tag = str(payload.get("tag_name") if api else payload.get("tag") or "")
        version = str(payload.get("tag_name") if api else payload.get("version") or "").lstrip("v")
        if not _version_tuple(version):
            raise ValueError("The update manifest has no valid version")
        assets = []
        for item in payload.get("assets") or []:
            if not isinstance(item, dict):
                continue
            url = _safe_release_url(item.get("browser_download_url") if api else item.get("url"))
            name = str(item.get("name") or "")[:240]
            if not url or not name:
                continue
            checksum = str(item.get("sha256") or "").strip().lower()
            if api and not checksum:
                digest = str(item.get("digest") or "").strip().lower()
                if digest.startswith("sha256:"):
                    checksum = digest.removeprefix("sha256:")
            assets.append({
                "name": name,
                "url": url,
                "size": int(item.get("size") or 0),
                "sha256": checksum if SHA256_PATTERN.fullmatch(checksum) else "",
            })
        return {
            "version": version,
            "tag": tag or f"v{version}",
            "url": _safe_release_url(payload.get("html_url") if api else payload.get("releaseUrl"))
                or f"https://github.com/{self.repository}/releases/tag/v{version}",
            "publishedAt": str(payload.get("published_at") if api else payload.get("publishedAt") or ""),
            "assets": assets,
        }

    def _fetch_latest_manifest(self):
        url = f"https://github.com/{self.repository}/releases/latest/download/update-manifest.json"
        with self._request(url, accept="application/json", timeout=20) as response:
            payload = json.loads(response.read(4 * 1024 * 1024).decode("utf-8-sig"))
        return self._normalize_latest(payload)

    def _fetch_latest_api(self):
        endpoint = f"https://api.github.com/repos/{self.repository}/releases/latest"
        with self._request(endpoint) as response:
            payload = json.loads(response.read(4 * 1024 * 1024).decode("utf-8"))
        return self._normalize_latest(payload, api=True)

    def status(self, check=False, force=False):
        state = self._read_state()
        if force or (check and state["autoCheck"] and self._check_is_stale(state)):
            return self.check()
        latest = state.get("latest") or {}
        latest_version = str(latest.get("version") or "")
        asset_name = self._asset_name()
        asset = next((item for item in latest.get("assets") or [] if item.get("name") == asset_name), {})
        pending = state.get("pending") or {}
        pending_archive = Path(str(pending.get("archive") or ""))
        return {
            "ok": True,
            "currentVersion": self.current_version,
            "latestVersion": latest_version,
            "available": _is_newer(latest_version, self.current_version),
            "autoCheck": state["autoCheck"],
            "checkedAt": state.get("checkedAt") or "",
            "releaseUrl": latest.get("url") or f"https://github.com/{self.repository}/releases/latest",
            "publishedAt": latest.get("publishedAt") or "",
            "assetName": asset_name,
            "assetAvailable": bool(asset),
            "portable": self.portable,
            "canInstall": bool(self.portable and sys.platform == "win32" and asset),
            "staged": bool(pending_archive.is_file()),
            "stagedVersion": str(pending.get("version") or ""),
            "error": str(state.get("error") or ""),
            "updateError": self._last_install_error(),
            "edition": self._edition(),
            "installationMode": str(self.manifest.get("installMode") or "source").lower(),
        }

    def configure(self, payload):
        state = self._read_state()
        if "autoCheck" in payload:
            state["autoCheck"] = bool(payload.get("autoCheck"))
        self._write_state(state)
        return self.status()

    def _release_asset(self, state, name):
        latest = state.get("latest") or {}
        return next((item for item in latest.get("assets") or [] if item.get("name") == name), None)

    def _download_bytes(self, url, maximum):
        with self._request(url, accept="application/octet-stream", timeout=60) as response:
            declared = int(response.headers.get("Content-Length") or 0)
            if declared and declared > maximum:
                raise ValueError("Release asset is larger than the allowed limit")
            content = response.read(maximum + 1)
        if len(content) > maximum:
            raise ValueError("Release asset is larger than the allowed limit")
        return content

    def _expected_checksum(self, state, asset_name):
        release_asset = self._release_asset(state, asset_name)
        inline = str((release_asset or {}).get("sha256") or "").strip().lower()
        if SHA256_PATTERN.fullmatch(inline):
            return inline
        checksum_asset = self._release_asset(state, asset_name + ".sha256")
        if not checksum_asset:
            raise ValueError("This release has no SHA-256 checksum")
        content = self._download_bytes(checksum_asset["url"], MAX_CHECKSUM_BYTES).decode("utf-8", errors="replace")
        match = SHA256_PATTERN.search(content)
        if not match:
            raise ValueError("The release checksum is invalid")
        return match.group(1).lower()

    def _validate_archive(self, archive, expected_version=""):
        try:
            with zipfile.ZipFile(archive) as package:
                file_count = 0
                extracted_bytes = 0
                normalized_paths = set()
                for item in package.infolist():
                    path = PurePosixPath(item.filename.replace("\\", "/"))
                    if (
                        path.is_absolute()
                        or ".." in path.parts
                        or not path.parts
                        or any(":" in part or "\x00" in part for part in path.parts)
                    ):
                        raise ValueError("The update archive contains an unsafe path")
                    mode = (item.external_attr >> 16) & 0o170000
                    if mode == 0o120000:
                        raise ValueError("The update archive contains a symbolic link")
                    if item.is_dir():
                        continue
                    normalized = "/".join(path.parts).casefold()
                    if normalized in normalized_paths:
                        raise ValueError("The update archive contains duplicate paths")
                    normalized_paths.add(normalized)
                    file_count += 1
                    extracted_bytes += max(0, int(item.file_size))
                    if file_count > MAX_ARCHIVE_FILES or extracted_bytes > MAX_EXTRACTED_BYTES:
                        raise ValueError("The update archive expands beyond the allowed limit")

                try:
                    package_manifest = json.loads(package.read("app-manifest.json").decode("utf-8-sig"))
                except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise ValueError("The update archive has no valid app manifest") from error
                if not isinstance(package_manifest, dict):
                    raise ValueError("The update archive has no valid app manifest")
                archive_version = str(package_manifest.get("version") or "").lstrip("v")
                archive_repository = str(package_manifest.get("repository") or "")
                archive_mode = str(package_manifest.get("installMode") or "").lower()
                archive_edition = str(package_manifest.get("edition") or "").lower()
                if not _version_tuple(archive_version) or (expected_version and archive_version != expected_version):
                    raise ValueError("The update archive version does not match the release")
                if archive_repository != self.repository or archive_mode != "portable":
                    raise ValueError("The update archive is not a Codex Console portable release")
                if archive_edition != self._edition():
                    raise ValueError("The update archive edition does not match this installation")
                broken = package.testzip()
                if broken:
                    raise ValueError(f"The update archive is damaged: {broken}")
        except zipfile.BadZipFile as error:
            raise ValueError("The downloaded update is not a valid ZIP") from error

    def download(self):
        self.check()
        state = self._read_state()
        latest = state.get("latest") or {}
        version = str(latest.get("version") or "")
        if not _is_newer(version, self.current_version):
            raise ValueError("Codex Console is already up to date")
        asset_name = self._asset_name()
        asset = self._release_asset(state, asset_name)
        if not asset:
            raise ValueError("The release does not include this Windows edition")
        if int(asset.get("size") or 0) > MAX_RELEASE_BYTES:
            raise ValueError("Release asset is larger than the allowed limit")
        expected = self._expected_checksum(state, asset_name)

        self.update_dir.mkdir(parents=True, exist_ok=True)
        installer = self.update_dir / f"{Path(asset_name).stem}-{version}.exe"
        temporary = installer.with_suffix(".part")
        digest = hashlib.sha256()
        total = 0
        try:
            with self._request(asset["url"], accept="application/octet-stream", timeout=120) as response:
                with temporary.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_RELEASE_BYTES:
                            raise ValueError("Release asset is larger than the allowed limit")
                        output.write(chunk)
                        digest.update(chunk)
            if digest.hexdigest().lower() != expected:
                raise ValueError("The downloaded update failed SHA-256 verification")
            with temporary.open("rb") as executable:
                if executable.read(2) != b"MZ":
                    raise ValueError("The downloaded update is not a Windows installer")
            os.replace(temporary, installer)
        finally:
            temporary.unlink(missing_ok=True)

        state["pending"] = {
            "version": version,
            "archive": str(installer),
            "sha256": expected,
            "verifiedAt": datetime.now(timezone.utc).isoformat(),
        }
        state["error"] = ""
        self._write_state(state)
        return self.status()

    def _setup_helper_script(
        self,
        archive,
        version,
        *,
        wait_pid=0,
        stop_executable=None,
        relaunch_executable=None,
        restart_stopped=False,
    ):
        lines = [
            "$ErrorActionPreference = 'Stop'",
            f"$installer = {_powershell_literal(Path(archive).resolve())}",
            f"$stateFile = {_powershell_literal(self.state_file.resolve())}",
            f"$resultFile = {_powershell_literal(self.result_file.resolve())}",
            f"$version = {_powershell_literal(version)}",
            f"$waitPid = {max(0, int(wait_pid or 0))}",
            f"$stopExecutable = {_powershell_literal(Path(stop_executable).resolve() if stop_executable else '')}",
            f"$relaunchExecutable = {_powershell_literal(Path(relaunch_executable).resolve() if relaunch_executable else '')}",
            f"$restartStopped = {'$true' if restart_stopped else '$false'}",
            "$stoppedTarget = $false",
            "$ok = $false",
            "$message = ''",
            "",
            "function Write-AtomicJson {",
            "  param([string]$Path, $Value)",
            "  $parent = Split-Path -Parent $Path",
            "  if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }",
            "  $temporary = \"$Path.tmp\"",
            "  $json = $Value | ConvertTo-Json -Depth 12",
            "  [IO.File]::WriteAllText($temporary, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))",
            "  Move-Item -LiteralPath $temporary -Destination $Path -Force",
            "}",
            "",
            "function Find-TargetProcesses {",
            "  if (-not $stopExecutable) { return @() }",
            "  return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {",
            "    $_.ExecutablePath -and [string]::Equals($_.ExecutablePath, $stopExecutable, [StringComparison]::OrdinalIgnoreCase)",
            "  })",
            "}",
            "",
            "try {",
            "  if ($waitPid -gt 0) {",
            "    Wait-Process -Id $waitPid -Timeout 90 -ErrorAction SilentlyContinue",
            "    if (Get-Process -Id $waitPid -ErrorAction SilentlyContinue) {",
            "      throw 'Codex Console did not close before the update timeout.'",
            "    }",
            "  }",
            "",
            "  $targets = @(Find-TargetProcesses)",
            "  if ($targets.Count -gt 0) {",
            "    $stoppedTarget = $true",
            "    foreach ($target in $targets) {",
            "      Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue",
            "    }",
            "    $deadline = [DateTime]::UtcNow.AddSeconds(20)",
            "    while (@(Find-TargetProcesses).Count -gt 0 -and [DateTime]::UtcNow -lt $deadline) {",
            "      Start-Sleep -Milliseconds 200",
            "    }",
            "    if (@(Find-TargetProcesses).Count -gt 0) {",
            "      throw 'The running application could not be closed for the update.'",
            "    }",
            "  }",
            "",
            "  $setupArguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/CLOSEAPPLICATIONS')",
            "  $setup = Start-Process -FilePath $installer -ArgumentList $setupArguments -Wait -PassThru",
            "  if ($setup.ExitCode -ne 0) {",
            "    throw \"Setup exited with code $($setup.ExitCode).\"",
            "  }",
            "",
            "  if (Test-Path -LiteralPath $stateFile) {",
            "    try {",
            "      $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json",
            "      if ($null -eq $state.pending) {",
            "        $state | Add-Member -NotePropertyName pending -NotePropertyValue ([pscustomobject]@{}) -Force",
            "      } else {",
            "        $state.pending = [pscustomobject]@{}",
            "      }",
            "      $state.error = ''",
            "      Write-AtomicJson $stateFile $state",
            "    } catch {",
            "      # The installed version remains authoritative if stale cache cleanup fails.",
            "    }",
            "  }",
            "  $ok = $true",
            "  $message = 'The update was installed successfully.'",
            "} catch {",
            "  $message = $_.Exception.Message",
            "}",
            "",
            "$result = [ordered]@{",
            "  ok = $ok",
            "  message = $message",
            "  version = $version",
            "  updatedAt = [DateTime]::UtcNow.ToString('o')",
            "}",
            "Write-AtomicJson $resultFile $result",
            "",
            "if ($ok) {",
            "  if ($relaunchExecutable -and (Test-Path -LiteralPath $relaunchExecutable)) {",
            "    Start-Process -FilePath $relaunchExecutable -ArgumentList @('--no-browser')",
            "  } elseif ($restartStopped -and $stoppedTarget -and (Test-Path -LiteralPath $stopExecutable)) {",
            "    Start-Process -FilePath $stopExecutable -ArgumentList @('--no-browser')",
            "  }",
            "  exit 0",
            "}",
            "exit 1",
        ]
        return "\r\n".join(lines) + "\r\n"

    def _launch_setup_helper(self, archive, version, **options):
        script = self._setup_helper_script(archive, version, **options)
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-EncodedCommand",
            encoded,
        ]
        subprocess.Popen(
            command,
            cwd=str(Path(archive).resolve().parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **_hidden_subprocess_kwargs(),
        )
        return command

    def _shutdown_later(self):
        time.sleep(0.75)
        if callable(self.shutdown_callback):
            self.shutdown_callback()

    def install(self, *, stop_executable=None, restart_stopped=False):
        if not self.portable or sys.platform != "win32":
            raise ValueError("The Windows installer is available from an installed Codex Console")
        state = self._read_state()
        pending = state.get("pending") or {}
        archive = Path(str(pending.get("archive") or ""))
        pending_checksum = str(pending.get("sha256") or "").strip().lower()
        if not archive.is_file() or not SHA256_PATTERN.fullmatch(pending_checksum):
            self.download()
            state = self._read_state()
            pending = state.get("pending") or {}
            archive = Path(str(pending.get("archive") or ""))
        version = str(pending.get("version") or "")
        self.result_file.unlink(missing_ok=True)
        restarting = callable(self.shutdown_callback)
        self_executable = Path(sys.executable).resolve() if restarting else None
        self._launch_setup_helper(
            archive,
            version,
            wait_pid=os.getpid() if restarting else 0,
            stop_executable=self_executable or stop_executable,
            relaunch_executable=self_executable,
            restart_stopped=bool(restart_stopped),
        )
        if restarting:
            threading.Thread(target=self._shutdown_later, daemon=True).start()
        result = self.status()
        result["setupStarted"] = True
        result["restarting"] = restarting
        result["installing"] = True
        result["targetVersion"] = version
        return result

    def open_release(self):
        url = self.status().get("releaseUrl") or f"https://github.com/{self.repository}/releases/latest"
        webbrowser.open(url)
        return {"ok": True, "url": url}
