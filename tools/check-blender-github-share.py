import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from blender_github_share import BlenderGithubShareService  # noqa: E402


def run(command, cwd=None):
    completed = subprocess.run(
        [str(item) for item in command],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise AssertionError((completed.stderr or completed.stdout or "command failed").strip())
    return completed.stdout.strip()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    if not shutil.which("git"):
        raise AssertionError("Git is required")
    if subprocess.run(["git", "lfs", "version"], capture_output=True).returncode != 0:
        raise AssertionError("Git LFS is required")

    with tempfile.TemporaryDirectory(prefix="codex-blender-share-") as temporary:
        temp_root = Path(temporary)
        project = temp_root / "Project One"
        project.mkdir()
        blend = project / "Scene.blend"
        blend.write_bytes(b"BLENDER-test-version-one")
        (project / "Scene.blend1").write_bytes(b"backup")
        (project / "textures").mkdir()
        (project / "textures" / "base.png").write_bytes(b"texture-one")
        (project / "renders").mkdir()
        (project / "renders" / "frame.png").write_bytes(b"render")

        service = BlenderGithubShareService(temp_root / "share-config.json", [temp_root])
        status = service.status(str(blend))
        require(status["git"]["state"] == "uninitialized", "new project should be uninitialized")

        initialized = service.initialize({
            "project": str(blend),
            "scope": "current",
            "visibility": "private",
            "version": "v0.1.0",
            "message": "Initial Blender scene",
        })
        require(initialized["git"]["initialized"], "repository was not initialized")
        require(initialized["git"]["lfsTracked"], "blend file is not tracked by Git LFS")
        run(["git", "config", "user.name", "Codex Console Test"], project)
        run(["git", "config", "user.email", "codex-console@example.invalid"], project)

        committed = service.commit({
            "project": str(blend),
            "scope": "current",
            "visibility": "private",
            "version": "v0.1.0",
            "message": "Initial Blender scene",
        })
        require(committed["action"]["tag"] == "v0.1.0", "version tag was not created")
        tracked = set(run(["git", "ls-tree", "-r", "--name-only", "HEAD"], project).splitlines())
        require("Scene.blend" in tracked, "current blend file was not committed")
        require("textures/base.png" not in tracked, "current-file scope committed an unrelated texture")
        require(run(["git", "check-ignore", "Scene.blend1"], project) == "Scene.blend1", "blend backup is not ignored")
        require(run(["git", "check-ignore", "renders/frame.png"], project) == "renders/frame.png", "render output is not ignored")

        (project / "textures" / "base.png").write_bytes(b"texture-two")
        (project / "textures" / "private.png").write_bytes(b"private")
        custom = service.commit({
            "project": str(blend),
            "scope": "custom",
            "includePatterns": ["textures/**"],
            "excludePatterns": ["textures/private*"],
            "visibility": "private",
            "version": "v0.1.1",
            "message": "Share selected textures",
        })
        require(custom["action"]["tag"] == "v0.1.1", "custom version tag was not created")
        tracked = set(run(["git", "ls-tree", "-r", "--name-only", "HEAD"], project).splitlines())
        require("textures/base.png" in tracked, "custom include did not commit the texture")
        require("textures/private.png" not in tracked, "custom exclude did not protect the private texture")

        remote = temp_root / "remote.git"
        run(["git", "init", "--bare", str(remote)])
        run(["git", "remote", "add", "origin", str(remote)], project)
        pushed = service.push({
            "project": str(blend),
            "scope": "custom",
            "includePatterns": ["textures/**"],
            "excludePatterns": ["textures/private*"],
            "visibility": "private",
            "version": "v0.1.1",
            "message": "Share selected textures",
        })
        require(pushed["git"]["state"] == "dirty", "excluded local change should remain visible after push")
        require(run(["git", "rev-parse", "refs/tags/v0.1.1"], remote), "tag was not pushed")

        second_project = temp_root / "Project Two"
        second_project.mkdir()
        second_blend = second_project / "Other.blend"
        second_blend.write_bytes(b"BLENDER-second")
        try:
            service.save({
                "project": str(second_blend),
                "visibility": "public",
                "scope": "project",
            })
        except ValueError as error:
            require("explicit confirmation" in str(error), "public confirmation returned the wrong error")
        else:
            raise AssertionError("public visibility did not require confirmation")

        service.save({
            "project": str(second_blend),
            "visibility": "public",
            "scope": "project",
            "confirmPublic": True,
        })
        first_config = service.status(str(blend))["config"]
        second_config = service.status(str(second_blend))["config"]
        require(first_config["visibility"] == "private", "second project overwrote first project visibility")
        require(second_config["visibility"] == "public", "second project configuration was not saved")

        config_payload = json.loads((temp_root / "share-config.json").read_text(encoding="utf-8"))
        require(len(config_payload.get("projects", {})) == 2, "configurations were not stored per project")

        local_app_data = temp_root / "LocalAppData"
        desktop_cli = local_app_data / "GitHubDesktop" / "bin" / "github.bat"
        desktop_cli.parent.mkdir(parents=True)
        desktop_cli.write_text("@echo off\n", encoding="ascii")
        with patch.dict("os.environ", {"LOCALAPPDATA": str(local_app_data)}, clear=False):
            with patch("blender_github_share.subprocess.Popen") as launch:
                opened = service.open_desktop({"project": str(blend)})
                require(opened["fallback"] is False, "GitHub Desktop launcher used the web fallback")
                require(launch.called, "GitHub Desktop was not launched")
                require(str(project) in launch.call_args.args[0], "GitHub Desktop did not receive the project directory")

        with patch("blender_github_share.webbrowser.open") as open_web:
            opened = service.open_repository({"project": str(second_blend)})
            require(opened["url"] == "https://github.com/new", "missing remote did not open GitHub's new repository page")
            open_web.assert_called_once_with("https://github.com/new")

    print("PASS Blender GitHub Share backend")


if __name__ == "__main__":
    main()
