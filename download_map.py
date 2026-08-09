import ast
import os
import re
from pathlib import Path


PLUGIN_REPOSITORIES = {
    "character-designer": "https://github.com/tx74666/Blender-projects",
    "rr-helper": "https://github.com/tx74666/Random-Realm",
}


class DownloadMapService:
    def __init__(self, project_roots=(), randomrealm_project_dir=None, environment=None):
        self.project_roots = [Path(path).expanduser() for path in project_roots]
        self.randomrealm_project_dir = (
            Path(randomrealm_project_dir).expanduser() if randomrealm_project_dir else None
        )
        self.environment = environment if environment is not None else os.environ

    @staticmethod
    def _dedupe(paths):
        result = []
        seen = set()
        for path in paths:
            if not path:
                continue
            candidate = Path(path).expanduser()
            key = os.path.normcase(os.path.abspath(str(candidate)))
            if key in seen:
                continue
            seen.add(key)
            result.append(candidate)
        return result

    @staticmethod
    def _first_directory(paths):
        return next((path.resolve() for path in paths if path.is_dir()), None)

    @staticmethod
    def _first_file(paths):
        return next((path.resolve() for path in paths if path.is_file()), None)

    @staticmethod
    def _version_from_addon(addon_dir):
        if not addon_dir:
            return ""
        init_file = Path(addon_dir) / "__init__.py"
        try:
            tree = ast.parse(init_file.read_text(encoding="utf-8"), filename=str(init_file))
            for node in tree.body:
                if not isinstance(node, ast.Assign):
                    continue
                if not any(isinstance(target, ast.Name) and target.id == "bl_info" for target in node.targets):
                    continue
                info = ast.literal_eval(node.value)
                version = info.get("version") if isinstance(info, dict) else None
                if isinstance(version, (tuple, list)) and version:
                    return ".".join(str(int(part)) for part in version)
        except (OSError, SyntaxError, ValueError, TypeError):
            pass
        return ""

    def _environment_path(self, name):
        value = str(self.environment.get(name, "") or "").strip()
        return Path(value).expanduser() if value else None

    def _project_addon_candidates(self, addon_folder):
        candidates = []
        for root in self.project_roots:
            candidates.extend([
                root / "addons" / addon_folder,
                root / "X" / "addons" / addon_folder,
                root / "Character" / "X" / "addons" / addon_folder,
            ])
            if not root.is_dir():
                continue
            candidates.extend(root.glob(f"*/addons/{addon_folder}"))
            candidates.extend(root.glob(f"*/*/addons/{addon_folder}"))
        return candidates

    def _installed_addon_candidates(self, addon_folder, blender_executable=None):
        candidates = []
        appdata = str(self.environment.get("APPDATA", "") or "").strip()
        if appdata:
            blender_root = Path(appdata) / "Blender Foundation" / "Blender"
            if blender_root.is_dir():
                for version_dir in sorted(blender_root.iterdir(), reverse=True):
                    candidates.extend([
                        version_dir / "scripts" / "addons" / addon_folder,
                        version_dir / "scripts" / "addons_core" / addon_folder,
                        version_dir / "extensions" / "user_default" / addon_folder,
                    ])

        executable_value = blender_executable or self._environment_path("CODEX_CONTROL_BLENDER_EXE")
        if executable_value:
            blender_root = Path(executable_value).expanduser().parent
            candidates.extend([
                blender_root / "scripts" / "addons" / addon_folder,
                blender_root / "scripts" / "addons_core" / addon_folder,
            ])
            if blender_root.is_dir():
                candidates.extend(blender_root.glob(f"*/scripts/addons/{addon_folder}"))
                candidates.extend(blender_root.glob(f"*/scripts/addons_core/{addon_folder}"))
        return candidates

    @staticmethod
    def _latest_zip(directory, pattern):
        if not directory or not Path(directory).is_dir():
            return None
        files = [path for path in Path(directory).glob(pattern) if path.is_file()]
        if not files:
            return None
        return max(files, key=lambda path: (path.stat().st_mtime_ns, path.name.casefold())).resolve()

    @staticmethod
    def _powershell_default_output(script_path):
        if not script_path or not Path(script_path).is_file():
            return None
        try:
            source = Path(script_path).read_text(encoding="utf-8")[:4096]
        except OSError:
            return None
        match = re.search(r"\$OutputPath\s*=\s*(['\"])(.+?)\1", source, flags=re.IGNORECASE)
        return Path(match.group(2)).expanduser() if match else None

    @staticmethod
    def _entry(entry_id, kind, value, variant=""):
        path_value = str(value) if value else ""
        return {
            "id": entry_id,
            "kind": kind,
            "value": path_value,
            "available": bool(path_value),
            "variant": variant,
        }

    def _character_designer(self, blender_executable=None):
        source = self._first_directory(self._dedupe([
            self._environment_path("CODEX_CONTROL_CHARACTER_DESIGNER_DIR"),
            *self._project_addon_candidates("character_designer"),
        ]))
        installed = self._first_directory(self._dedupe([
            self._environment_path("CODEX_CONTROL_CHARACTER_DESIGNER_INSTALLED_DIR"),
            *self._installed_addon_candidates("character_designer", blender_executable),
        ]))
        package = self._first_file(self._dedupe([
            self._environment_path("CODEX_CONTROL_CHARACTER_DESIGNER_PACKAGE"),
        ]))
        if not package and source:
            package = self._latest_zip(source.parent.parent / "dist", "character_designer-*.zip")
        version = self._version_from_addon(source) or self._version_from_addon(installed)
        entries = [
            self._entry("repository", "url", PLUGIN_REPOSITORIES["character-designer"]),
            self._entry("source", "folder", source),
            self._entry("installed", "folder", installed),
            self._entry("package", "file", package, "zip" if package else ""),
        ]
        return self._plugin("character-designer", "Character Designer", version, entries)

    def _rr_helper(self, blender_executable=None):
        canonical = None
        if self.randomrealm_project_dir:
            canonical = (
                self.randomrealm_project_dir
                / "Tools"
                / "AssetPipeline"
                / "Blender"
                / "addons"
                / "random_realm_builder_exporter"
            )
        source = self._first_directory(self._dedupe([
            self._environment_path("CODEX_CONTROL_RR_HELPER_DIR"),
            canonical,
            *self._project_addon_candidates("random_realm_builder_exporter"),
        ]))
        installed = self._first_directory(self._dedupe([
            self._environment_path("CODEX_CONTROL_RR_HELPER_INSTALLED_DIR"),
            *self._installed_addon_candidates("random_realm_builder_exporter", blender_executable),
        ]))
        package = self._first_file(self._dedupe([
            self._environment_path("CODEX_CONTROL_RR_HELPER_PACKAGE"),
        ]))
        package_script = source.parent.parent / "Package-RRHelperAddon.ps1" if source else None
        if not package:
            package = self._first_file(self._dedupe([
                self._powershell_default_output(package_script),
                self._latest_zip(source.parent.parent / "dist", "*rr*helper*.zip") if source else None,
            ]))
        package_target = package or self._first_file([package_script] if package_script else [])
        package_variant = "zip" if package else ("builder" if package_target else "")
        version = self._version_from_addon(source) or self._version_from_addon(installed)
        entries = [
            self._entry("repository", "url", PLUGIN_REPOSITORIES["rr-helper"]),
            self._entry("source", "folder", source),
            self._entry("installed", "folder", installed),
            self._entry("package", "file", package_target, package_variant),
        ]
        return self._plugin("rr-helper", "RR Helper", version, entries)

    @staticmethod
    def _plugin(plugin_id, name, version, entries):
        available = sum(1 for entry in entries if entry["available"])
        return {
            "id": plugin_id,
            "name": name,
            "version": version,
            "available": available,
            "total": len(entries),
            "complete": available == len(entries),
            "entries": entries,
        }

    def state(self, blender_executable=None):
        return {
            "ok": True,
            "category": "blender-plugins",
            "plugins": [
                self._character_designer(blender_executable),
                self._rr_helper(blender_executable),
            ],
        }

    def target(self, plugin_id, entry_id, blender_executable=None):
        state = self.state(blender_executable)
        plugin = next((item for item in state["plugins"] if item["id"] == plugin_id), None)
        if not plugin:
            raise ValueError("unknown download map plugin")
        entry = next((item for item in plugin["entries"] if item["id"] == entry_id), None)
        if not entry:
            raise ValueError("unknown download map target")
        if not entry["available"]:
            raise ValueError("download map target was not found on this device")
        return {"plugin": plugin, "entry": entry}
