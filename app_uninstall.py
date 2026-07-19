from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import threading
import time


PRODUCTS = {
    "console": {
        "name": "Codex Console",
        "registry": r"Software\Codex\Codex Console",
        "directory": "Codex Console",
    },
    "world": {
        "name": "Codex World",
        "registry": r"Software\Codex\Codex World",
        "directory": "Codex World",
    },
}


def _hidden_subprocess_kwargs():
    if sys.platform != "win32":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


class AppUninstallService:
    def __init__(self, app_dir, manifest, shutdown_callback=None):
        self.app_dir = Path(app_dir).resolve()
        self.manifest = dict(manifest or {})
        self.shutdown_callback = shutdown_callback

    @staticmethod
    def _registered_directory(product):
        if sys.platform != "win32":
            return None
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PRODUCTS[product]["registry"]) as key:
                value = str(winreg.QueryValueEx(key, "InstallPath")[0]).strip()
        except (OSError, ValueError):
            return None
        try:
            return Path(value).expanduser().resolve() if value else None
        except OSError:
            return None

    @staticmethod
    def _default_directory(product):
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return (base / "Programs" / PRODUCTS[product]["directory"]).resolve()

    def _install_directory(self, product):
        if product == "console" and str(self.manifest.get("installMode") or "source").lower() == "installed":
            candidates = [self.app_dir]
            if self.app_dir.name.casefold() == "_internal":
                candidates.insert(0, self.app_dir.parent)
            for candidate in candidates:
                if any((candidate / name).is_file() for name in ("unins000.exe", "uninstall.exe")):
                    return candidate
            return candidates[0]
        return self._registered_directory(product) or self._default_directory(product)

    def _uninstaller(self, product):
        if product not in PRODUCTS:
            raise ValueError("Unknown Codex product")
        directory = self._install_directory(product)
        for name in ("unins000.exe", "uninstall.exe"):
            candidate = directory / name
            if candidate.is_file():
                return candidate
        return None

    def status(self, product):
        uninstaller = self._uninstaller(product)
        directory = self._install_directory(product)
        return {
            "canUninstall": bool(uninstaller and sys.platform == "win32"),
            "uninstallPath": str(uninstaller or ""),
            "uninstallInstallationPath": str(directory),
        }

    def _shutdown_later(self):
        time.sleep(0.45)
        if callable(self.shutdown_callback):
            self.shutdown_callback()

    def launch(self, product):
        if sys.platform != "win32":
            raise ValueError("Uninstall is available on Windows only")
        uninstaller = self._uninstaller(product)
        if not uninstaller:
            raise ValueError(f"{PRODUCTS[product]['name']} does not have an installed uninstaller")
        subprocess.Popen(
            [str(uninstaller), "/NORESTART"],
            cwd=str(uninstaller.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **_hidden_subprocess_kwargs(),
        )
        if product == "console" and uninstaller.parent.resolve() == self.app_dir:
            threading.Thread(target=self._shutdown_later, daemon=True).start()
        return {
            "ok": True,
            "product": product,
            "uninstaller": str(uninstaller),
            "cleanLocalData": True,
        }
