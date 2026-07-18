import hashlib
import io
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from world_update import WorldUpdateService  # noqa: E402


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    with tempfile.TemporaryDirectory(prefix="codex-world-update-") as temporary:
        root = Path(temporary)
        app_dir = root / "console"
        data_dir = root / "user-data"
        source_dir = root / "world-source-missing"
        app_dir.mkdir()
        data_dir.mkdir()
        service = WorldUpdateService(app_dir, data_dir, source_dir)

        version = "0.2.0"
        setup_name = "Codex-World-Setup-x64.exe"
        setup_bytes = b"MZ" + b"world-setup" * 40
        state = service._default_state()
        state["latest"] = {
            "version": version,
            "tag": f"v{version}",
            "url": f"https://github.com/tx74666/CodexWorldConsole/releases/tag/v{version}",
            "assets": [{
                "name": setup_name,
                "url": f"https://github.com/tx74666/CodexWorldConsole/releases/download/v{version}/{setup_name}",
                "size": len(setup_bytes),
                "sha256": hashlib.sha256(setup_bytes).hexdigest(),
            }],
        }
        service._write_state(state)

        with (
            patch("world_update.sys.platform", "win32"),
            patch("console_update.sys.platform", "win32"),
            patch.object(service, "check", side_effect=lambda: service.status()),
            patch.object(service, "_request", side_effect=lambda *args, **kwargs: io.BytesIO(setup_bytes)),
            patch("console_update.subprocess.Popen") as launch,
        ):
            before = service.status()
            require(before["available"] and not before["installed"], "missing Codex World was not detected")
            require(before["assetName"] == setup_name and before["canInstall"], "World x64 Setup was not selected")
            result = service.install()

        installer = Path(service._read_state()["pending"]["archive"])
        require(installer.is_file() and installer.read_bytes() == setup_bytes, "World Setup was not downloaded")
        require(result["setupStarted"], "World Setup was not started")
        require(launch.call_args.args[0] == [str(installer)], "the wrong World installer was launched")

        source_data = root / "source-user-data"
        source_data.mkdir()
        source_dir.mkdir()
        (source_dir / "Start-WorldConsole.vbs").write_text("' launcher\n", encoding="ascii")
        (source_dir / "README-FIRST.txt").write_text("Version: v0.1.7\n", encoding="ascii")
        source_service = WorldUpdateService(app_dir, source_data, source_dir)
        source_service._write_state(state)
        with patch("world_update.sys.platform", "win32"):
            source_status = source_service.status()
        require(source_status["installationMode"] == "source", "source checkout was not detected")
        require(source_status["available"] and not source_status["canInstall"], "source update policy is wrong")
        try:
            source_service.install()
        except ValueError as error:
            require("GitHub Desktop" in str(error), "source checkout error has no guidance")
        else:
            raise AssertionError("source checkout was overwritten by Setup")

    print("PASS Codex World Setup updater")


if __name__ == "__main__":
    main()
