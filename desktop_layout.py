import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
import uuid


def _default_startup_file():
    app_data = os.environ.get("APPDATA", "").strip()
    root = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
    return root / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "RestoreDesktopLayout.vbs"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _safe_label(value, fallback="Desktop layout"):
    text = str(value or "").strip()
    return text[:120] or fallback


def _safe_filename(value):
    stem = Path(str(value or "layout.json").replace("\\", "/")).stem
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")
    return clean[:80] or "desktop-layout"


def _path_key(value):
    try:
        return os.path.normcase(str(Path(value).resolve())).casefold()
    except (OSError, TypeError, ValueError):
        return os.path.normcase(str(value or "")).casefold()


class DesktopLayoutService:
    def __init__(
        self,
        app_dir,
        data_dir=None,
        default_plan_path=None,
        external_script=None,
        bundled_script=None,
        startup_file=None,
    ):
        self.app_dir = Path(app_dir)
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        default_data_dir = (
            Path(local_app_data) / "CodexControlConsole" / "desktop-layout"
            if local_app_data
            else Path.home() / "AppData" / "Local" / "CodexControlConsole" / "desktop-layout"
        )
        self.data_dir = Path(data_dir or os.environ.get("CODEX_CONTROL_DESKTOP_LAYOUT_DATA_DIR", default_data_dir))
        self.plan_dir = self.data_dir / "plans"
        self.verification_dir = self.data_dir / "verification"
        self.config_file = self.data_dir / "plans.json"
        configured_plan_path = default_plan_path or os.environ.get("CODEX_CONTROL_DESKTOP_LAYOUT_CURRENT")
        self.default_plan_path = (
            Path(configured_plan_path)
            if configured_plan_path
            else self.plan_dir / "desktop-layout-current.json"
        )
        configured_external_script = external_script or os.environ.get("CODEX_CONTROL_DESKTOP_LAYOUT_SCRIPT")
        self.external_script = Path(configured_external_script) if configured_external_script else None
        self.bundled_script = Path(bundled_script or self.app_dir / "tools" / "DesktopLayout.ps1")
        self.startup_file = Path(startup_file or _default_startup_file())
        self._lock = threading.RLock()

    def _read_config(self):
        with self._lock:
            try:
                payload = json.loads(self.config_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            plans = []
            seen_ids = set()
            seen_paths = set()
            for raw in payload.get("plans", []) if isinstance(payload, dict) else []:
                if not isinstance(raw, dict):
                    continue
                raw_path = str(raw.get("path") or "").strip()
                if not raw_path:
                    continue
                path = Path(raw_path).expanduser()
                plan_id = str(raw.get("id") or "").strip()
                path_key = _path_key(path)
                if not plan_id or plan_id in seen_ids or path_key in seen_paths:
                    continue
                seen_ids.add(plan_id)
                seen_paths.add(path_key)
                plans.append({
                    "id": plan_id,
                    "name": _safe_label(raw.get("name"), path.stem),
                    "path": str(path),
                    "source": raw.get("source") if raw.get("source") in {"remembered", "device", "imported"} else "imported",
                    "createdAt": str(raw.get("createdAt") or ""),
                })

            changed = False
            default_key = _path_key(self.default_plan_path)
            if self.default_plan_path.is_file() and default_key not in seen_paths:
                plans.insert(0, {
                    "id": "remembered-current",
                    "name": "Remembered current",
                    "path": str(self.default_plan_path),
                    "source": "remembered",
                    "createdAt": _now_iso(),
                })
                changed = True

            if not plans:
                plans.append({
                    "id": "device-current",
                    "name": "Current desktop",
                    "path": str(self.plan_dir / "desktop-layout-current.json"),
                    "source": "device",
                    "createdAt": _now_iso(),
                })
                changed = True

            selected = str(payload.get("selectedPlan") or "") if isinstance(payload, dict) else ""
            available_ids = {plan["id"] for plan in plans}
            if selected not in available_ids:
                selected = plans[0]["id"] if plans else ""
                changed = True

            config = {
                "version": 1,
                "selectedPlan": selected,
                "plans": plans,
            }
            if changed:
                self._write_config(config)
            return config

    def _write_config(self, config):
        with self._lock:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            temporary = self.config_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, self.config_file)

    def _script_path(self):
        if self.external_script and self.external_script.is_file():
            return self.external_script
        return self.bundled_script

    def _layout_payload(self, source):
        try:
            if isinstance(source, (bytes, bytearray)):
                payload = json.loads(bytes(source).decode("utf-8-sig"))
            else:
                payload = json.loads(Path(source).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("The selected file is not a valid desktop layout JSON.") from error
        if not isinstance(payload, dict):
            raise ValueError("Desktop layout JSON must contain an object.")
        raw_icons = payload.get("Icons")
        if not isinstance(raw_icons, list) or not raw_icons:
            raise ValueError("Desktop layout JSON does not contain any Icons.")
        if len(raw_icons) > 5000:
            raise ValueError("Desktop layout JSON contains too many icons.")
        icons = []
        for raw in raw_icons:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("Name") or "").strip()
            try:
                x = int(raw.get("X"))
                y = int(raw.get("Y"))
            except (TypeError, ValueError):
                continue
            if name:
                icons.append({"name": name, "x": x, "y": y})
        if not icons:
            raise ValueError("Desktop layout JSON has no usable icon positions.")
        return {
            "savedAt": str(payload.get("SavedAt") or ""),
            "computerName": str(payload.get("ComputerName") or ""),
            "userName": str(payload.get("UserName") or ""),
            "iconSize": payload.get("IconSize"),
            "screens": payload.get("Screens") if isinstance(payload.get("Screens"), list) else [],
            "icons": icons,
        }

    def _plan_record(self, plan, selected):
        path = Path(plan["path"])
        exists = path.is_file()
        layout = None
        error = ""
        if exists:
            try:
                layout = self._layout_payload(path)
            except ValueError as layout_error:
                error = str(layout_error)
        try:
            stat = path.stat() if exists else None
        except OSError:
            stat = None
        return {
            **plan,
            "selected": plan["id"] == selected,
            "exists": exists,
            "valid": bool(layout),
            "iconCount": len(layout["icons"]) if layout else 0,
            "savedAt": layout["savedAt"] if layout else "",
            "computerName": layout["computerName"] if layout else "",
            "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat() if stat else "",
            "size": stat.st_size if stat else 0,
            "error": error,
        }

    def _startup_state(self):
        exists = self.startup_file.is_file()
        points_to_current = False
        if exists:
            try:
                body = self.startup_file.read_text(encoding="utf-8-sig", errors="replace")
                points_to_current = str(self.default_plan_path).casefold() in body.casefold()
            except OSError:
                pass
        return {
            "path": str(self.startup_file),
            "exists": exists,
            "pointsToCurrent": points_to_current,
        }

    def status(self):
        config = self._read_config()
        script = self._script_path()
        return {
            "ok": True,
            "localOnly": True,
            "dataDirectory": str(self.data_dir),
            "selectedPlan": config["selectedPlan"],
            "plans": [self._plan_record(plan, config["selectedPlan"]) for plan in config["plans"]],
            "tool": {
                "path": str(script),
                "available": script.is_file(),
                "external": script == self.external_script,
            },
            "startup": self._startup_state(),
        }

    def _selected(self, config, plan_id=""):
        requested = str(plan_id or config.get("selectedPlan") or "").strip()
        for plan in config.get("plans", []):
            if plan["id"] == requested:
                return plan
        raise ValueError("Select a desktop layout plan first.")

    def select(self, payload):
        config = self._read_config()
        plan = self._selected(config, payload.get("planId") if isinstance(payload, dict) else "")
        config["selectedPlan"] = plan["id"]
        self._write_config(config)
        return self.status()

    def import_layouts(self, files):
        config = self._read_config()
        self.plan_dir.mkdir(parents=True, exist_ok=True)
        imported = []
        for item in files:
            filename = str(item.get("filename") or "")
            data = item.get("data") or b""
            if Path(filename).suffix.lower() != ".json" or not data:
                continue
            layout = self._layout_payload(data)
            plan_id = uuid.uuid4().hex
            safe_name = _safe_filename(filename)
            target = self.plan_dir / f"{safe_name}-{plan_id[:8]}.json"
            target.write_bytes(data)
            plan = {
                "id": plan_id,
                "name": _safe_label(Path(filename).stem.replace("desktop-layout-", ""), "Imported layout"),
                "path": str(target),
                "source": "imported",
                "createdAt": _now_iso(),
            }
            config["plans"].append(plan)
            config["selectedPlan"] = plan_id
            imported.append({"id": plan_id, "name": plan["name"], "iconCount": len(layout["icons"])})
        if not imported:
            raise ValueError("Choose at least one valid desktop layout JSON file.")
        self._write_config(config)
        result = self.status()
        result["imported"] = imported
        return result

    def _run_script(self, action, path):
        script = self._script_path()
        if sys.platform != "win32":
            raise RuntimeError("Desktop layout restore is available on Windows only.")
        if not script.is_file():
            raise RuntimeError("DesktopLayout.ps1 was not found.")
        command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Action",
            action,
            "-Path",
            str(path),
        ]
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=120,
                **kwargs,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Desktop layout operation timed out.") from error
        output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
        if completed.returncode != 0:
            raise RuntimeError(output or f"Desktop layout operation failed ({completed.returncode}).")
        return output

    def _backup_path(self, path):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        candidate = path.with_name(f"{path.stem}-backup-{stamp}{path.suffix}")
        counter = 2
        while candidate.exists():
            candidate = path.with_name(f"{path.stem}-backup-{stamp}-{counter}{path.suffix}")
            counter += 1
        return candidate

    def save(self, payload):
        config = self._read_config()
        plan = self._selected(config, payload.get("planId") if isinstance(payload, dict) else "")
        path = Path(plan["path"])
        backup = None
        if path.is_file():
            backup = self._backup_path(path)
            shutil.copy2(path, backup)
        path.parent.mkdir(parents=True, exist_ok=True)
        output = self._run_script("save", path)
        self._layout_payload(path)
        result = self.status()
        result.update({
            "saved": str(path),
            "backup": str(backup) if backup else "",
            "output": output,
        })
        return result

    def _verify_restore(self, target_path):
        self.verification_dir.mkdir(parents=True, exist_ok=True)
        actual_path = self.verification_dir / "last-restored.json"
        self._run_script("save", actual_path)
        target = self._layout_payload(target_path)
        actual = self._layout_payload(actual_path)
        target_by_name = {icon["name"]: icon for icon in target["icons"]}
        actual_by_name = {icon["name"]: icon for icon in actual["icons"]}
        missing = sorted(name for name in target_by_name if name not in actual_by_name)
        mismatches = []
        for name, expected in target_by_name.items():
            current = actual_by_name.get(name)
            if not current:
                continue
            if abs(expected["x"] - current["x"]) > 4 or abs(expected["y"] - current["y"]) > 4:
                mismatches.append(name)
        positions = {}
        for icon in actual["icons"]:
            positions.setdefault((icon["x"], icon["y"]), []).append(icon["name"])
        overlaps = [names for names in positions.values() if len(names) > 1]
        return {
            "healthy": not missing and not mismatches and not overlaps,
            "checkedIcons": len(target_by_name),
            "missing": missing[:20],
            "mismatches": mismatches[:20],
            "overlaps": overlaps[:20],
            "snapshot": str(actual_path),
        }

    def restore(self, payload):
        config = self._read_config()
        plan = self._selected(config, payload.get("planId") if isinstance(payload, dict) else "")
        path = Path(plan["path"])
        self._layout_payload(path)
        output = self._run_script("restore", path)
        verification = self._verify_restore(path)
        result = self.status()
        result.update({
            "restored": str(path),
            "output": output,
            "verification": verification,
        })
        return result
