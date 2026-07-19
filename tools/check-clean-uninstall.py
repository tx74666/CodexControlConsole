from pathlib import Path
import os
import sys
import tempfile
import threading
import time
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_uninstall  # noqa: E402
from app_uninstall import AppUninstallService  # noqa: E402


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    with tempfile.TemporaryDirectory(prefix="codex-clean-uninstall-") as temporary:
        root = Path(temporary)
        local_app_data = root / "LocalAppData"
        console_dir = local_app_data / "Programs" / "Codex Console"
        world_dir = local_app_data / "Programs" / "Codex World"
        console_dir.mkdir(parents=True)
        world_dir.mkdir(parents=True)
        (console_dir / "unins000.exe").write_bytes(b"test")
        (world_dir / "unins000.exe").write_bytes(b"test")

        service = AppUninstallService(root / "source", {"installMode": "source"})
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}, clear=False), \
             patch.object(app_uninstall.sys, "platform", "win32"), \
             patch.object(AppUninstallService, "_registered_directory", return_value=None), \
             patch.object(app_uninstall.subprocess, "Popen") as launch:
            require(service.status("console")["canUninstall"], "installed Console uninstaller was not found")
            require(service.status("world")["canUninstall"], "installed World uninstaller was not found")
            result = service.launch("world")
            require(result["cleanLocalData"], "World uninstall did not declare local-data cleanup")
            require(launch.call_args.args[0][0] == str(world_dir / "unins000.exe"), "wrong World uninstaller launched")

        installed_dir = root / "Installed Console"
        installed_dir.mkdir()
        (installed_dir / "unins000.exe").write_bytes(b"test")
        stopped = threading.Event()
        installed = AppUninstallService(
            installed_dir,
            {"installMode": "installed"},
            shutdown_callback=stopped.set,
        )
        with patch.object(app_uninstall.sys, "platform", "win32"), \
             patch.object(app_uninstall.subprocess, "Popen") as launch:
            installed.launch("console")
            require(launch.call_args.args[0][0] == str(installed_dir / "unins000.exe"), "wrong Console uninstaller launched")
            require(stopped.wait(1.5), "Console did not schedule shutdown before self-uninstall")

        internal_dir = installed_dir / "_internal"
        internal_dir.mkdir()
        frozen = AppUninstallService(internal_dir, {"installMode": "installed"})
        with patch.object(app_uninstall.sys, "platform", "win32"):
            require(frozen.status("console")["canUninstall"], "frozen Console did not find its parent uninstaller")
            require(
                frozen.status("console")["uninstallPath"] == str(installed_dir / "unins000.exe"),
                "frozen Console selected the wrong parent uninstaller",
            )

    print("PASS clean uninstall launcher")


if __name__ == "__main__":
    main()
