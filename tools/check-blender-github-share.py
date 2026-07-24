import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from blender_github_share import (  # noqa: E402
    BlenderGithubShareService,
    filter_blender_discovery_directories,
    is_blender_discovery_file,
)


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
        generated_backup = project / "Scene.codex-pre-test.blend"
        generated_backup.write_bytes(b"backup blend")
        asset_blend = project / "assets" / "models" / "Asset.blend"
        asset_blend.parent.mkdir(parents=True)
        asset_blend.write_bytes(b"asset blend")
        roundtrip_blend = project / "RoundTrip" / "RoundTrip.blend"
        roundtrip_blend.parent.mkdir()
        roundtrip_blend.write_bytes(b"roundtrip blend")
        (project / "Scene.blend1").write_bytes(b"backup")
        (project / "textures").mkdir()
        (project / "textures" / "base.png").write_bytes(b"texture-one")
        (project / "renders").mkdir()
        (project / "renders" / "frame.png").write_bytes(b"render")

        catalog_file = temp_root / "github-coop.json"
        catalog_file.write_text(json.dumps({
            "version": 1,
            "repositories": [{
                "name": "Cloud Project",
                "repositoryUrl": "https://github.com/example/cloud-project.git",
                "blendFile": "Cloud.blend",
                "defaultBranch": "main",
                "version": "v1.2.3",
                "visibility": "private",
            }],
        }), encoding="utf-8")
        cloud_service = BlenderGithubShareService(
            temp_root / "cloud-share-config.json",
            [temp_root],
            catalog_file=catalog_file,
        )
        cloud_status = cloud_service.status()
        require(cloud_status["project"]["name"] == "Cloud Project", "catalog repository was not selected")
        require(not cloud_status["project"]["downloaded"], "cloud repository was marked as downloaded")
        require(cloud_status["git"]["state"] == "cloud", "cloud repository has the wrong state")

        cloud_local_app_data = temp_root / "CloudLocalAppData"
        cloud_desktop_cli = cloud_local_app_data / "GitHubDesktop" / "bin" / "github.bat"
        cloud_desktop_cli.parent.mkdir(parents=True)
        cloud_desktop_cli.write_text("@echo off\n", encoding="ascii")
        with patch.dict("os.environ", {"LOCALAPPDATA": str(cloud_local_app_data), "PATH": ""}, clear=False):
            with patch.object(cloud_service, "_launch_desktop_command") as launch:
                opened_cloud = cloud_service.open_desktop({
                    "project": "https://github.com/example/cloud-project",
                })
                require(opened_cloud["action"] == "clone", "cloud repository did not enter the clone flow")
                require("clone" in launch.call_args.args[0], "GitHub Desktop clone command was not used")
                require(
                    "https://github.com/example/cloud-project" in launch.call_args.args[0],
                    "clone flow did not receive the repository URL",
                )
        try:
            cloud_service.open_folder({"project": "https://github.com/example/cloud-project"})
        except ValueError as error:
            require("Clone" in str(error), "cloud folder error did not explain the clone requirement")
        else:
            raise AssertionError("cloud repository opened a nonexistent local folder")

        service = BlenderGithubShareService(temp_root / "share-config.json", [temp_root])
        require(is_blender_discovery_file(blend, temp_root), "main blend file was hidden from discovery")
        require(not is_blender_discovery_file(generated_backup, temp_root), "Codex backup entered project discovery")
        require(not is_blender_discovery_file(asset_blend, temp_root), "asset blend entered project discovery")
        require(not is_blender_discovery_file(roundtrip_blend, temp_root), "round-trip blend entered project discovery")
        require(filter_blender_discovery_directories(["Project", "assets", "UnityExports"]) == ["Project"], "generated directories were not pruned")
        require(Path(service._discover_latest_project()) == blend, "generated blend replaced the latest real project")
        require(service._blend_files(project) == [blend.resolve()], "generated blends appeared as project cards")
        status = service.status(str(blend))
        require(status["git"]["state"] == "uninitialized", "new project should be uninitialized")
        require(not status["collection"]["projects"], "an unpublished local project entered GitHub Coop")

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

        collaborator = temp_root / "Collaborator"
        run([
            "git",
            "-c",
            "filter.lfs.smudge=",
            "-c",
            "filter.lfs.required=false",
            "clone",
            "--branch",
            "main",
            str(remote),
            str(collaborator),
        ])
        run(["git", "config", "user.name", "Codex Collaborator"], collaborator)
        run(["git", "config", "user.email", "collaborator@example.invalid"], collaborator)
        (collaborator / "README.md").write_text("Remote Blender update\n", encoding="utf-8")
        run(["git", "add", "README.md"], collaborator)
        run(["git", "commit", "-m", "Add collaborator note"], collaborator)
        run(["git", "push", "origin", "main"], collaborator)
        refreshed = service.status(str(blend), refresh_remote=True)
        require(refreshed["git"]["remoteCheck"]["ok"], "remote refresh did not complete")
        require(refreshed["git"]["behind"] == 1, "remote collaborator update was not detected")

        try:
            service.add_project({"project": str(blend)})
        except ValueError as error:
            require("Publish" in str(error), "unpublished repository returned the wrong error")
        else:
            raise AssertionError("an unpublished repository was added to GitHub Coop")
        run(["git", "remote", "set-url", "origin", "https://github.com/example/project-one.git"], project)

        sibling_blend = project / "Scene Alt.blend"
        sibling_blend.write_bytes(b"BLENDER-sibling")
        same_group = service.add_project({"project": str(sibling_blend)})
        require(len(same_group["collection"]["projects"]) == 1, "files from one directory created duplicate project groups")
        require(
            same_group["collection"]["projects"][0]["repositoryUrl"] == "https://github.com/example/project-one",
            "GitHub repository URL was not exposed to the project card",
        )

        unadded_project = temp_root / "Not Added"
        unadded_project.mkdir()
        unadded_blend = unadded_project / "Hidden.blend"
        unadded_blend.write_bytes(b"BLENDER-unadded")
        require(
            all(item["path"] != str(unadded_blend.resolve()) for item in same_group["collection"]["projects"]),
            "an unadded Blender project entered GitHub Coop",
        )

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

        with patch("blender_github_share.webbrowser.open") as open_web:
            opened = service.open_repository({"project": str(second_blend)})
            require(opened["url"] == "https://github.com/new", "missing remote did not open GitHub's new repository page")
            open_web.assert_called_once_with("https://github.com/new")

        initialized_second = service.initialize({
            "project": str(second_blend),
            "visibility": "public",
            "scope": "project",
            "confirmPublic": True,
        })
        require(initialized_second["git"]["initialized"], "second repository was not initialized")
        run(["git", "config", "user.name", "Codex Console Test"], second_project)
        run(["git", "config", "user.email", "codex-console@example.invalid"], second_project)
        service.commit({
            "project": str(second_blend),
            "visibility": "public",
            "scope": "project",
            "version": "v0.2.0",
            "message": "Second Blender project",
            "confirmPublic": True,
        })
        run(["git", "remote", "add", "origin", "https://github.com/example/project-two.git"], second_project)
        added_second = service.add_project({"project": str(second_blend)})
        require(len(added_second["collection"]["projects"]) == 2, "published repositories were not kept in GitHub Coop")
        reordered = service.reorder_projects({
            "project": str(second_blend),
            "order": [str(second_blend), str(sibling_blend)],
        })
        require(
            [item["name"] for item in reordered["collection"]["projects"]] == ["project-two", "project-one"],
            "GitHub repository card order was not persisted",
        )

        first_config = service.status(str(blend))["config"]
        second_config = service.status(str(second_blend))["config"]
        require(first_config["visibility"] == "private", "second project overwrote first project visibility")
        require(second_config["visibility"] == "public", "second project configuration was not saved")
        collection = service.status(str(second_blend))["collection"]["projects"]
        require(len(collection) == 2, "GitHub Coop did not keep the two published repositories")
        require(all(item["path"] != str(unadded_blend.resolve()) for item in collection), "unadded project appeared in the picker collection")

        config_payload = json.loads((temp_root / "share-config.json").read_text(encoding="utf-8"))
        require(len(config_payload.get("projects", {})) == 2, "configurations were not stored per project")

        local_app_data = temp_root / "LocalAppData"
        desktop_cli = local_app_data / "GitHubDesktop" / "bin" / "github.bat"
        desktop_cli.parent.mkdir(parents=True)
        desktop_cli.write_text("@echo off\n", encoding="ascii")
        with patch.dict("os.environ", {"LOCALAPPDATA": str(local_app_data)}, clear=False):
            with patch.object(service, "_launch_desktop_command") as launch:
                opened = service.open_desktop({"project": str(blend)})
                require(opened["fallback"] is False, "GitHub Desktop launcher used the web fallback")
                require(launch.called, "GitHub Desktop was not launched")
                require("open" in launch.call_args.args[0], "local repository did not use GitHub Desktop open")
                require(str(project) in launch.call_args.args[0], "GitHub Desktop did not receive the project directory")

        if sys.platform == "win32":
            with patch("blender_github_share.os.startfile") as open_folder:
                opened = service.open_folder({"project": str(sibling_blend)})
                require(opened["path"] == str(project.resolve()), "project folder response used the wrong repository root")
                open_folder.assert_called_once_with(str(project.resolve()))

    print("PASS Blender GitHub Share backend")


if __name__ == "__main__":
    main()
