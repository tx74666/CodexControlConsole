import json
import hashlib
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from console_update import ConsoleUpdateService  # noqa: E402
from tools.apply_update import apply_archive  # noqa: E402


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
        (app_dir / "tools").mkdir()
        (app_dir / "tools" / "apply_update.py").write_text("# helper\n", encoding="ascii")
        (app_dir / "Start-ControlConsole.vbs").write_text("' launcher\n", encoding="ascii")

        manifest = {
            "name": "Codex Control Console",
            "version": "0.3.0",
            "repository": "example/repository",
            "installMode": "portable",
            "edition": "developer",
        }
        service = ConsoleUpdateService(app_dir, data_dir, manifest, lambda: "developer")
        normalized = service._normalize_latest({
            "version": "0.3.1",
            "tag": "v0.3.1",
            "releaseUrl": "https://github.com/example/repository/releases/tag/v0.3.1",
            "assets": [{
                "name": "CodexControlConsole-developer-windows.zip",
                "url": "https://github.com/example/repository/releases/download/v0.3.1/developer.zip",
                "size": 100,
                "sha256": "a" * 64,
            }],
        })
        require(normalized["version"] == "0.3.1", "direct release manifest was not normalized")
        require(normalized["assets"][0]["sha256"] == "a" * 64, "inline release checksum was discarded")
        api_normalized = service._normalize_latest({
            "tag_name": "v0.3.1",
            "html_url": "https://github.com/example/repository/releases/tag/v0.3.1",
            "assets": [{
                "name": "CodexControlConsole-developer-windows.zip",
                "browser_download_url": "https://github.com/example/repository/releases/download/v0.3.1/developer.zip",
                "size": 100,
                "digest": "sha256:" + "b" * 64,
            }],
        }, api=True)
        require(api_normalized["assets"][0]["sha256"] == "b" * 64, "GitHub asset digest was discarded")
        state = service._default_state()
        state["latest"] = {
            "version": "0.3.1",
            "tag": "v0.3.1",
            "url": "https://github.com/example/repository/releases/tag/v0.3.1",
            "assets": [
                {
                    "name": "CodexControlConsole-developer-windows.zip",
                    "url": "https://github.com/example/repository/releases/download/v0.3.1/developer.zip",
                    "size": 100,
                }
            ],
        }
        service._write_state(state)
        with patch("console_update.sys.platform", "win32"):
            status = service.status()
        require(status["available"], "newer semantic version was not detected")
        require(status["assetAvailable"], "developer update asset was not selected")
        require(status["canInstall"], "portable Windows update should be installable")

        configured = service.configure({"autoCheck": False})
        require(configured["autoCheck"] is False, "per-user automatic update preference was not saved")
        require((data_dir / "cache" / "update_state.json").is_file(), "update state was not stored in user data")

        archive = data_dir / "updates" / "verified.zip"
        archive.parent.mkdir(parents=True)
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("app-manifest.json", json.dumps({**manifest, "version": "0.3.1"}))
            package.writestr("app.js", "const updated = true;\n")
            package.writestr("tools/apply_update.py", "# updated helper\n")
        service._validate_archive(archive)

        malicious = data_dir / "updates" / "unsafe.zip"
        with zipfile.ZipFile(malicious, "w") as package:
            package.writestr("../outside.txt", "unsafe")
        try:
            service._validate_archive(malicious)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe ZIP path was accepted")

        user_file = data_dir / "cache" / "personal.json"
        user_file.write_text('{"keep": true}\n', encoding="utf-8")
        (app_dir / "app.js").write_text("const updated = false;\n", encoding="utf-8")
        apply_archive(archive, app_dir, data_dir)
        require("true" in (app_dir / "app.js").read_text(encoding="utf-8"), "app file was not updated")
        require(user_file.is_file(), "per-user data was touched by the updater")
        require(not (root / "outside.txt").exists(), "updater wrote outside the application directory")

        rollback_archive = data_dir / "updates" / "rollback.zip"
        old_manifest = json.dumps(manifest, sort_keys=True)
        (app_dir / "app-manifest.json").write_text(old_manifest, encoding="utf-8")
        (app_dir / "a-ok.txt").write_text("old\n", encoding="utf-8")
        (app_dir / "z-block").write_text("block\n", encoding="utf-8")
        with zipfile.ZipFile(rollback_archive, "w") as package:
            package.writestr("app-manifest.json", json.dumps({**manifest, "version": "0.3.1"}))
            package.writestr("a-ok.txt", "new\n")
            package.writestr("z-block/child.txt", "fail after replacement\n")
        try:
            apply_archive(rollback_archive, app_dir, data_dir, expected_version="0.3.1")
        except OSError:
            pass
        else:
            raise AssertionError("forced update failure did not occur")
        require((app_dir / "a-ok.txt").read_text(encoding="utf-8") == "old\n", "failed update was not rolled back")
        require((app_dir / "app-manifest.json").read_text(encoding="utf-8") == old_manifest, "manifest rollback failed")

        state = service._read_state()
        state["pending"] = {
            "version": "0.3.1",
            "archive": str(archive),
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        }
        service._write_state(state)
        with patch("console_update.sys.platform", "win32"), patch("console_update.subprocess.Popen") as launch:
            result = service.install()
            require(result["restarting"], "install did not enter restarting state")
            require(launch.called, "update helper was not launched")
            command = launch.call_args.args[0]
            require(str(archive) in command and str(app_dir) in command, "update helper received the wrong paths")

    print("PASS Codex Console updater")


if __name__ == "__main__":
    main()
