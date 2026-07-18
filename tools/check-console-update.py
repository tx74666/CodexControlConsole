import hashlib
import io
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from console_update import ConsoleUpdateService  # noqa: E402


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    with tempfile.TemporaryDirectory(prefix="codex-console-update-") as temporary:
        root = Path(temporary)
        app_dir = root / "app"
        data_dir = root / "user-data"
        app_dir.mkdir()
        data_dir.mkdir()

        manifest = {
            "name": "Codex Control Console",
            "version": "0.4.0",
            "repository": "example/repository",
            "installMode": "installed",
            "edition": "developer",
        }
        service = ConsoleUpdateService(app_dir, data_dir, manifest, lambda: "developer")
        setup_bytes = b"MZ" + b"setup" * 40
        setup_hash = hashlib.sha256(setup_bytes).hexdigest()
        setup_name = "CodexControlConsole-Setup-x64.exe"
        state = service._default_state()
        state["latest"] = {
            "version": "0.4.1",
            "tag": "v0.4.1",
            "url": "https://github.com/example/repository/releases/tag/v0.4.1",
            "assets": [{
                "name": setup_name,
                "url": f"https://github.com/example/repository/releases/download/v0.4.1/{setup_name}",
                "size": len(setup_bytes),
                "sha256": setup_hash,
            }],
        }
        service._write_state(state)

        with patch("console_update.sys.platform", "win32"):
            status = service.status()
        require(status["available"], "newer semantic version was not detected")
        require(status["assetName"] == setup_name and status["assetAvailable"], "x64 Setup was not selected")
        require(status["canInstall"], "installed Windows build should open Setup updates")
        require(status["installationMode"] == "installed", "installation mode was not exposed")

        configured = service.configure({"autoCheck": False})
        require(configured["autoCheck"] is False, "per-user update preference was not saved")

        with (
            patch.object(service, "check", side_effect=lambda: service.status()),
            patch.object(service, "_request", side_effect=lambda *args, **kwargs: io.BytesIO(setup_bytes)),
        ):
            downloaded = service.download()
        pending = service._read_state()["pending"]
        installer = Path(pending["archive"])
        require(installer.is_file() and installer.read_bytes() == setup_bytes, "verified Setup was not downloaded")
        require(downloaded["staged"], "downloaded Setup was not staged")

        with patch("console_update.sys.platform", "win32"), patch("console_update.subprocess.Popen") as launch:
            result = service.install()
        require(result["setupStarted"] and not result["restarting"], "Setup launch state is wrong")
        require(launch.call_args.args[0] == [str(installer)], "the wrong installer was launched")

        source_service = ConsoleUpdateService(
            app_dir,
            root / "source-data",
            {**manifest, "installMode": "source"},
            lambda: "developer",
        )
        source_service._write_state(state)
        with patch("console_update.sys.platform", "win32"):
            require(not source_service.status()["canInstall"], "source checkout should not overwrite itself")

    print("PASS Codex Console Setup updater")


if __name__ == "__main__":
    main()
