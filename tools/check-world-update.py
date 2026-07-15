import hashlib
import io
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from world_update import WORLD_EXECUTABLE, WorldUpdateService  # noqa: E402


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def world_archive(version):
    buffer = io.BytesIO()
    root = f"Codex-World-Console-Windows-v{version}"
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr(f"{root}/{WORLD_EXECUTABLE}", b"portable executable placeholder")
        package.writestr(f"{root}/README-FIRST.txt", f"Codex World\nVersion: v{version}\n")
        package.writestr(f"{root}/app.js", "const version = true;\n")
    return buffer.getvalue()


def main():
    with tempfile.TemporaryDirectory(prefix="codex-world-update-") as temporary:
        root = Path(temporary)
        app_dir = root / "console"
        data_dir = root / "user-data"
        source_dir = root / "world-source-missing"
        app_dir.mkdir()
        data_dir.mkdir()
        service = WorldUpdateService(app_dir, data_dir, source_dir)

        version = "0.1.7"
        archive_bytes = world_archive(version)
        asset_name = f"Codex-World-Console-Windows-v{version}.zip"
        state = service._default_state()
        state["latest"] = {
            "version": version,
            "tag": f"v{version}",
            "url": f"https://github.com/tx74666/CodexWorldConsole/releases/tag/v{version}",
            "assets": [{
                "name": asset_name,
                "url": f"https://github.com/tx74666/CodexWorldConsole/releases/download/v{version}/{asset_name}",
                "size": len(archive_bytes),
                "sha256": hashlib.sha256(archive_bytes).hexdigest(),
            }],
        }
        service._write_state(state)

        with (
            patch("world_update.sys.platform", "win32"),
            patch.object(service, "check", side_effect=lambda: service.status()),
            patch.object(service, "_request", side_effect=lambda *args, **kwargs: io.BytesIO(archive_bytes)),
        ):
            before = service.status()
            require(before["available"] and not before["installed"], "missing Codex World was not detected")
            require(before["canInstall"], "missing Codex World was not installable")
            installed = service.install()

        require(installed["installedNow"], "Codex World installation did not complete")
        require(installed["currentVersion"] == version, "installed Codex World version was not recorded")
        require(not installed["available"], "installed Codex World still reports an update")
        executable = Path(installed["installationPath"]) / WORLD_EXECUTABLE
        require(executable.is_file(), "managed Codex World executable is missing")
        require(service.active_file.is_file(), "managed Codex World pointer was not saved")

        with patch("world_update.subprocess.Popen") as launch:
            opened = service.open()
        require(launch.called and opened["version"] == version, "managed Codex World did not open")

        unsafe = root / "unsafe-world.zip"
        with zipfile.ZipFile(unsafe, "w") as package:
            package.writestr("../outside.txt", "unsafe")
            package.writestr(WORLD_EXECUTABLE, "placeholder")
            package.writestr("README-FIRST.txt", f"Version: v{version}\n")
        try:
            service._validate_archive(unsafe, expected_version=version)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe Codex World ZIP path was accepted")

        source_data = root / "source-user-data"
        source_data.mkdir()
        source_dir.mkdir()
        (source_dir / "Start-WorldConsole.vbs").write_text("' launcher\n", encoding="ascii")
        (source_dir / "README-FIRST.txt").write_text("Version: v0.1.6\n", encoding="ascii")
        source_service = WorldUpdateService(app_dir, source_data, source_dir)
        source_state = source_service._default_state()
        source_state["latest"] = state["latest"]
        source_service._write_state(source_state)
        with patch("world_update.sys.platform", "win32"):
            source_status = source_service.status()
        require(source_status["installationMode"] == "source", "source checkout was not detected")
        require(source_status["available"] and not source_status["canInstall"], "source checkout update policy is wrong")
        try:
            source_service.install()
        except ValueError as error:
            require("GitHub Desktop" in str(error), "source checkout error has no update guidance")
        else:
            raise AssertionError("source checkout was overwritten by the managed installer")

    print("PASS Codex World updater")


if __name__ == "__main__":
    main()
