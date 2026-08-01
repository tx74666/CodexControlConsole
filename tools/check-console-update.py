import base64
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from console_update import ConsoleUpdateService  # noqa: E402


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def helper_script(launch):
    command = launch.call_args.args[0]
    require(command[0].casefold() == "powershell.exe", "Setup helper is not PowerShell")
    try:
        encoded = command[command.index("-EncodedCommand") + 1]
    except (ValueError, IndexError) as error:
        raise AssertionError("Setup helper command is not encoded") from error
    return base64.b64decode(encoded).decode("utf-16-le")


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
        script = helper_script(launch)
        require(str(installer.resolve()) in script, "the wrong installer was handed to the helper")
        require("/VERYSILENT" in script and "/CLOSEAPPLICATIONS" in script, "Setup is not unattended")
        require("_internal\\app-manifest.json" in script, "installed version is not verified")
        require("Ensure-Shortcut" in script, "shortcuts are not repaired after update")
        require(
            "[string]::Equals($existing.TargetPath, $installedExecutable" in script,
            "valid shortcuts are rewritten instead of preserved",
        )
        require("Setup finished but Codex Console.exe is missing." in script, "missing EXE is not detected")
        require(
            "if ($stoppedTarget -or $restartStopped -or $relaunchExecutable)" in script,
            "the previous app is not restarted when Setup fails",
        )

        stopped = threading.Event()
        service.shutdown_callback = stopped.set
        with (
            patch("console_update.sys.platform", "win32"),
            patch("console_update.subprocess.Popen") as launch,
            patch("console_update.time.sleep", return_value=None),
        ):
            restarting = service.install()
            require(stopped.wait(1), "Console shutdown was not scheduled")
        restart_script = helper_script(launch)
        require(restarting["restarting"], "self-update did not enter restart mode")
        require(f"$waitPid = {os.getpid()}" in restart_script, "helper does not wait for Console")
        require("--no-browser" in restart_script, "Console is not relaunched without duplicating its window")

        installer.write_bytes(b"MZtampered")
        with (
            patch("console_update.sys.platform", "win32"),
            patch.object(service, "download", side_effect=ValueError("redownload required")),
        ):
            try:
                service.install()
            except ValueError as error:
                require("redownload required" in str(error), "tampered Setup returned the wrong error")
            else:
                raise AssertionError("tampered Setup was launched")

        source_service = ConsoleUpdateService(
            app_dir,
            root / "source-data",
            {**manifest, "installMode": "source"},
            lambda: "developer",
        )
        source_service._write_state(state)
        with patch("console_update.sys.platform", "win32"):
            require(not source_service.status()["canInstall"], "source checkout should not overwrite itself")

        store_service = ConsoleUpdateService(
            app_dir,
            root / "store-data",
            {**manifest, "installMode": "store", "storeProductId": "9TESTSTORE"},
            lambda: "developer",
        )
        store_service._write_state(state)
        with patch.object(store_service, "_request", side_effect=AssertionError("Store build contacted GitHub")):
            store_status = store_service.status(check=True, force=True)
        require(store_status["managedByStore"], "Store update ownership was not exposed")
        require(store_status["installationMode"] == "store", "Store installation mode was not exposed")
        require(not store_status["available"], "Store build advertised a GitHub update")
        require(not store_status["canInstall"], "Store build can launch the GitHub Setup")
        require(store_status["latestVersion"] == manifest["version"], "Store status did not stay on its package version")
        require(
            store_status["releaseUrl"] == "ms-windows-store://pdp/?ProductId=9TESTSTORE",
            "Store product link is wrong",
        )
        store_without_product = ConsoleUpdateService(
            app_dir,
            root / "store-data-no-product",
            {**manifest, "installMode": "store"},
            lambda: "developer",
        )
        require(
            store_without_product.status()["releaseUrl"] == "",
            "Store build fell back to an external GitHub download",
        )
        require(store_service.configure({"autoCheck": False})["autoCheck"], "Store update checks were disabled locally")
        for operation in (store_service.download, store_service.install):
            try:
                operation()
            except ValueError as error:
                require("Microsoft Store" in str(error), "Store update guard returned the wrong error")
            else:
                raise AssertionError("Store build launched the GitHub updater")

    print("PASS Codex Console Setup updater")


if __name__ == "__main__":
    main()
