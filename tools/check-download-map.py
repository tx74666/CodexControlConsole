from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from download_map import DownloadMapService  # noqa: E402


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def write_addon(path, name, version):
    path.mkdir(parents=True)
    (path / "__init__.py").write_text(
        "bl_info = {\n"
        f"    'name': {name!r},\n"
        f"    'version': {version!r},\n"
        "}\n",
        encoding="utf-8",
    )


def main():
    with tempfile.TemporaryDirectory(prefix="codex-download-map-") as temporary:
        root = Path(temporary)
        project_root = root / "Blender Projects"
        character_source = project_root / "Character" / "X" / "addons" / "character_designer"
        write_addon(character_source, "Character Designer", (0, 6, 1))
        character_package = character_source.parent.parent / "dist" / "character_designer-0.6.1.zip"
        character_package.parent.mkdir()
        character_package.write_bytes(b"zip")

        randomrealm = root / "RandomRealm2"
        rr_tools = randomrealm / "Tools" / "AssetPipeline" / "Blender"
        rr_source = rr_tools / "addons" / "random_realm_builder_exporter"
        write_addon(rr_source, "RR Helper", (0, 2, 2))
        rr_package = root / "packages" / "random_realm_builder_exporter.zip"
        rr_package.parent.mkdir()
        rr_package.write_bytes(b"zip")
        (rr_tools / "Package-RRHelperAddon.ps1").write_text(
            f"param([string]$OutputPath = '{rr_package}')\n",
            encoding="utf-8",
        )

        appdata = root / "AppData" / "Roaming"
        character_installed = (
            appdata
            / "Blender Foundation"
            / "Blender"
            / "5.1"
            / "scripts"
            / "addons"
            / "character_designer"
        )
        write_addon(character_installed, "Character Designer", (0, 6, 1))

        blender_executable = root / "Blender" / "blender.exe"
        blender_executable.parent.mkdir()
        blender_executable.write_bytes(b"exe")
        rr_installed = (
            blender_executable.parent
            / "5.1"
            / "scripts"
            / "addons"
            / "random_realm_builder_exporter"
        )
        write_addon(rr_installed, "RR Helper", (0, 2, 2))

        service = DownloadMapService(
            project_roots=[project_root],
            randomrealm_project_dir=randomrealm,
            environment={"APPDATA": str(appdata)},
        )
        state = service.state(blender_executable=blender_executable)
        require([item["id"] for item in state["plugins"]] == ["character-designer", "rr-helper"], "plugin order changed")
        require(all(item["complete"] for item in state["plugins"]), "complete plugin paths were not detected")
        require(state["plugins"][0]["version"] == "0.6.1", "Character Designer version was not read")
        require(state["plugins"][1]["version"] == "0.2.2", "RR Helper version was not read")
        require(
            service.target("rr-helper", "package", blender_executable)["entry"]["value"] == str(rr_package.resolve()),
            "RR Helper package output was not resolved from the packaging script",
        )

        missing = DownloadMapService(environment={}).state()
        require(
            all(plugin["available"] == 1 for plugin in missing["plugins"]),
            "a clean device should expose only repository links",
        )
        require(
            all(
                not entry["value"]
                for plugin in missing["plugins"]
                for entry in plugin["entries"]
                if entry["id"] != "repository"
            ),
            "device-specific paths leaked into the clean-device map",
        )
        try:
            DownloadMapService(environment={}).target("rr-helper", "installed")
        except ValueError:
            pass
        else:
            raise AssertionError("an unavailable install directory could be opened")

    print("Download Map checks passed.")


if __name__ == "__main__":
    main()
