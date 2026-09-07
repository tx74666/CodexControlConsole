import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
import hashlib
import uuid


ICON_COORDINATE_MIN = -(2 ** 15)
ICON_COORDINATE_MAX = (2 ** 15) - 1


def _default_startup_file():
    app_data = os.environ.get("APPDATA", "").strip()
    root = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
    return root / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "RestoreDesktopLayout.vbs"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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


def _atomic_write_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(bytes(data))
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


def _atomic_write_json(path, payload):
    _atomic_write_bytes(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
    )


class DesktopLayoutService:
    def __init__(
        self,
        app_dir,
        data_dir=None,
        default_plan_path=None,
        external_script=None,
        bundled_script=None,
        startup_file=None,
        snapshot_interval_days=3,
        history_target_days=7,
        clock=None,
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
        self.history_dir = self.data_dir / "history"
        self.verification_dir = self.data_dir / "verification"
        self.config_file = self.data_dir / "plans.json"
        self.history_file = self.data_dir / "history.json"
        self.seven_day_path = self.plan_dir / "desktop-layout-seven-days-ago.json"
        configured_plan_path = default_plan_path or os.environ.get("CODEX_CONTROL_DESKTOP_LAYOUT_CURRENT")
        self.default_plan_path = (
            Path(configured_plan_path)
            if configured_plan_path
            else self.plan_dir / "desktop-layout-current.json"
        )
        configured_external_script = external_script or os.environ.get("CODEX_CONTROL_DESKTOP_LAYOUT_SCRIPT")
        self.external_script = Path(configured_external_script) if configured_external_script else None
        self.bundled_script = Path(bundled_script or self.app_dir / "tools" / "DesktopLayout.ps1")
        configured_startup_file = startup_file or os.environ.get("CODEX_CONTROL_DESKTOP_LAYOUT_STARTUP_FILE")
        self.startup_file = Path(configured_startup_file or _default_startup_file())
        self.snapshot_interval_days = max(1, int(snapshot_interval_days))
        self.history_target_days = max(1, int(history_target_days))
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()

    def _now(self):
        value = self._clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

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
                    "source": raw.get("source") if raw.get("source") in {"remembered", "device", "history", "imported"} else "imported",
                    "createdAt": str(raw.get("createdAt") or ""),
                })

            changed = False
            default_key = _path_key(self.default_plan_path)
            current_plan = next((plan for plan in plans if plan["source"] in {"remembered", "device"}), None)
            if not current_plan and self.default_plan_path.is_file() and default_key not in seen_paths:
                current_plan = {
                    "id": "remembered-current",
                    "name": "Remembered current",
                    "path": str(self.default_plan_path),
                    "source": "remembered",
                    "createdAt": _now_iso(),
                }
                plans.insert(0, current_plan)
                changed = True

            if not current_plan:
                current_plan = {
                    "id": "device-current",
                    "name": "Current desktop",
                    "path": str(self.plan_dir / "desktop-layout-current.json"),
                    "source": "device",
                    "createdAt": _now_iso(),
                }
                plans.insert(0, current_plan)
                changed = True

            history_plan = {
                "id": "seven-days-ago",
                "name": "About 7 days ago",
                "path": str(self.seven_day_path),
                "source": "history",
                "createdAt": _now_iso(),
            }
            existing_history_index = next(
                (index for index, plan in enumerate(plans) if plan["id"] == history_plan["id"]),
                None,
            )
            if existing_history_index is None:
                current_index = plans.index(current_plan)
                plans.insert(current_index + 1, history_plan)
                changed = True
            else:
                existing = plans[existing_history_index]
                history_plan["createdAt"] = existing.get("createdAt") or history_plan["createdAt"]
                if existing != history_plan:
                    plans[existing_history_index] = history_plan
                    changed = True

            selected = str(payload.get("selectedPlan") or "") if isinstance(payload, dict) else ""
            available_ids = {plan["id"] for plan in plans}
            if selected not in available_ids:
                selected = plans[0]["id"] if plans else ""
                changed = True

            config = {
                "version": 2,
                "selectedPlan": selected,
                "plans": plans,
            }
            if changed:
                self._write_config(config)
            return config

    def _write_config(self, config):
        with self._lock:
            _atomic_write_json(self.config_file, config)

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
        seen_names = set()
        for index, raw in enumerate(raw_icons, start=1):
            if not isinstance(raw, dict):
                raise ValueError(f"Desktop icon entry {index} must contain an object.")
            name = str(raw.get("Name") or "").strip()
            if not name:
                raise ValueError(f"Desktop icon entry {index} does not contain a name.")
            raw_x = raw.get("X")
            raw_y = raw.get("Y")
            if isinstance(raw_x, bool) or isinstance(raw_y, bool):
                raise ValueError(f'Desktop icon "{name}" does not contain a valid position.')
            try:
                x = int(raw_x)
                y = int(raw_y)
            except (TypeError, ValueError, OverflowError):
                raise ValueError(f'Desktop icon "{name}" does not contain a valid position.') from None
            if (
                isinstance(raw_x, float) and not raw_x.is_integer()
                or isinstance(raw_y, float) and not raw_y.is_integer()
            ):
                raise ValueError(f'Desktop icon "{name}" does not contain a valid position.')
            if not (
                ICON_COORDINATE_MIN <= x <= ICON_COORDINATE_MAX
                and ICON_COORDINATE_MIN <= y <= ICON_COORDINATE_MAX
            ):
                raise ValueError(
                    f'Desktop icon "{name}" has a position outside the Windows-supported range.'
                )
            name_key = name.casefold()
            if name_key in seen_names:
                raise ValueError(f'Desktop layout JSON contains the duplicate icon name "{name}".')
            seen_names.add(name_key)
            icons.append({"name": name, "x": x, "y": y})
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

    def _startup_state(self, current_path=None):
        exists = self.startup_file.is_file()
        points_to_current = False
        restores_layout = False
        if exists:
            try:
                body = self.startup_file.read_text(encoding="utf-8-sig", errors="replace")
                if current_path:
                    points_to_current = str(current_path).casefold() in body.casefold()
                restores_layout = bool(re.search(
                    r"(?:-Action\s+(?:restore|ensure|persist|apply)\b|Restore-DesktopLayout\.cmd)",
                    body,
                    flags=re.IGNORECASE,
                ))
            except OSError:
                pass
        return {
            "path": str(self.startup_file),
            "exists": exists,
            "pointsToCurrent": points_to_current,
            "restoresLayout": restores_layout,
            "nativeWindowsLayout": not restores_layout,
        }

    def _current_plan(self, config):
        for plan in config.get("plans", []):
            if plan.get("source") in {"remembered", "device"}:
                return plan
        raise ValueError("Current desktop layout plan was not found.")

    def _read_history(self):
        try:
            payload = json.loads(self.history_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        snapshots = []
        for raw in payload.get("snapshots", []) if isinstance(payload, dict) else []:
            if not isinstance(raw, dict):
                continue
            path = str(raw.get("path") or "").strip()
            captured_at = str(raw.get("capturedAt") or "").strip()
            if path and _parse_datetime(captured_at):
                snapshots.append({
                    "path": path,
                    "capturedAt": captured_at,
                    "digest": str(raw.get("digest") or ""),
                    "kind": str(raw.get("kind") or "automatic"),
                })
        return {
            "version": 1,
            "lastCapturedAt": str(payload.get("lastCapturedAt") or "") if isinstance(payload, dict) else "",
            "sevenDayCapturedAt": str(payload.get("sevenDayCapturedAt") or "") if isinstance(payload, dict) else "",
            "sevenDaySource": str(payload.get("sevenDaySource") or "") if isinstance(payload, dict) else "",
            "snapshots": snapshots,
        }

    def _write_history(self, state):
        _atomic_write_json(self.history_file, state)

    def _history_status(self, state=None):
        state = state or self._read_history()
        now = self._now()
        last_captured = _parse_datetime(state.get("lastCapturedAt"))
        next_capture = last_captured + timedelta(days=self.snapshot_interval_days) if last_captured else None
        seven_day_captured = _parse_datetime(state.get("sevenDayCapturedAt"))
        seven_day_age = (now - seven_day_captured).total_seconds() / 86400 if seven_day_captured else None
        seven_day_available = False
        if seven_day_captured and self.seven_day_path.is_file() and 0 <= seven_day_age <= 12:
            try:
                self._layout_payload(self.seven_day_path)
                seven_day_available = True
            except ValueError:
                pass
        return {
            "enabled": True,
            "automaticRestore": False,
            "intervalDays": self.snapshot_interval_days,
            "targetDays": self.history_target_days,
            "due": not next_capture or now >= next_capture,
            "lastCapturedAt": last_captured.isoformat() if last_captured else "",
            "nextCaptureAt": next_capture.isoformat() if next_capture else "",
            "sevenDayAvailable": seven_day_available,
            "sevenDayCapturedAt": seven_day_captured.isoformat() if seven_day_captured else "",
            "sevenDayAgeDays": round(seven_day_age, 1) if seven_day_age is not None else None,
            "snapshotCount": len(state.get("snapshots", [])),
        }

    def _layout_digest(self, path):
        layout = self._layout_payload(path)
        semantic_layout = {
            "iconSize": layout["iconSize"],
            "screens": layout["screens"],
            "icons": layout["icons"],
        }
        encoded = json.dumps(
            semantic_layout,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _layout_capture_time(self, path, fallback=None):
        layout = self._layout_payload(path)
        captured_at = _parse_datetime(layout.get("savedAt"))
        if captured_at:
            return captured_at
        try:
            return datetime.fromtimestamp(Path(path).stat().st_mtime, timezone.utc)
        except OSError:
            return fallback or self._now()

    def _archive_snapshot(self, state, source_path, captured_at, kind):
        source_path = Path(source_path)
        digest = self._layout_digest(source_path)
        for snapshot in state["snapshots"]:
            if snapshot.get("digest") == digest and Path(snapshot.get("path", "")).is_file():
                if kind in {"automatic", "manual"}:
                    logical_snapshot = {
                        "path": snapshot["path"],
                        "capturedAt": captured_at.isoformat(),
                        "digest": digest,
                        "kind": kind,
                    }
                    state["snapshots"].append(logical_snapshot)
                    return logical_snapshot
                return snapshot
        self.history_dir.mkdir(parents=True, exist_ok=True)
        stamp = captured_at.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = self.history_dir / f"desktop-layout-{stamp}-{kind}.json"
        counter = 2
        while target.exists():
            target = self.history_dir / f"desktop-layout-{stamp}-{kind}-{counter}.json"
            counter += 1
        shutil.copy2(source_path, target)
        snapshot = {
            "path": str(target),
            "capturedAt": captured_at.isoformat(),
            "digest": digest,
            "kind": kind,
        }
        state["snapshots"].append(snapshot)
        return snapshot

    def _update_seven_day_snapshot(self, state, now):
        candidates = []
        for snapshot in state.get("snapshots", []):
            captured_at = _parse_datetime(snapshot.get("capturedAt"))
            path = Path(snapshot.get("path", ""))
            if not captured_at or not path.is_file():
                continue
            age_days = (now - captured_at).total_seconds() / 86400
            if 5 <= age_days <= 10:
                candidates.append((abs(age_days - self.history_target_days), captured_at, path))
        if not candidates:
            return
        _, captured_at, source = min(candidates, key=lambda item: item[0])
        self.plan_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.seven_day_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, self.seven_day_path)
        finally:
            try:
                temporary.unlink()
            except OSError:
                pass
        state["sevenDayCapturedAt"] = captured_at.isoformat()
        state["sevenDaySource"] = str(source)

    def status(self):
        config = self._read_config()
        script = self._script_path()
        history = self._history_status()
        plan_records = [self._plan_record(plan, config["selectedPlan"]) for plan in config["plans"]]
        if not history["sevenDayAvailable"]:
            for plan in plan_records:
                if plan.get("source") == "history":
                    plan.update({"exists": False, "valid": False, "iconCount": 0, "savedAt": "", "error": ""})
        else:
            for plan in plan_records:
                if plan.get("source") == "history":
                    plan["savedAt"] = history["sevenDayCapturedAt"]
        current_plan = self._current_plan(config)
        return {
            "ok": True,
            "localOnly": True,
            "dataDirectory": str(self.data_dir),
            "selectedPlan": config["selectedPlan"],
            "plans": plan_records,
            "history": history,
            "tool": {
                "path": str(script),
                "available": script.is_file(),
                "external": script == self.external_script,
            },
            "startup": self._startup_state(current_plan.get("path")),
        }

    def _selected(self, config, plan_id=""):
        requested = str(plan_id or config.get("selectedPlan") or "").strip()
        for plan in config.get("plans", []):
            if plan["id"] == requested:
                return plan
        raise ValueError("Select a desktop layout plan first.")

    def select(self, payload):
        with self._lock:
            config = self._read_config()
            plan = self._selected(config, payload.get("planId") if isinstance(payload, dict) else "")
            config["selectedPlan"] = plan["id"]
            self._write_config(config)
            return self.status()

    def import_layouts(self, files):
        with self._lock:
            config = self._read_config()
            prepared = []
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
                plan = {
                    "id": plan_id,
                    "name": _safe_label(Path(filename).stem.replace("desktop-layout-", ""), "Imported layout"),
                    "path": str(target),
                    "source": "imported",
                    "createdAt": _now_iso(),
                }
                prepared.append((target, bytes(data), plan, len(layout["icons"])))
            if not prepared:
                raise ValueError("Choose at least one valid desktop layout JSON file.")

            written = []
            try:
                for target, data, plan, icon_count in prepared:
                    _atomic_write_bytes(target, data)
                    written.append(target)
                    config["plans"].append(plan)
                    config["selectedPlan"] = plan["id"]
                    imported.append({"id": plan["id"], "name": plan["name"], "iconCount": icon_count})
                self._write_config(config)
            except Exception:
                for target in written:
                    try:
                        target.unlink()
                    except OSError:
                        pass
                raise
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
        candidate = path.with_name(
            f"{path.stem}-backup-{stamp}-{uuid.uuid4().hex[:8]}{path.suffix}"
        )
        while candidate.exists():
            candidate = path.with_name(
                f"{path.stem}-backup-{stamp}-{uuid.uuid4().hex[:8]}{path.suffix}"
            )
        return candidate

    def save(self, payload):
        with self._lock:
            return self._save(payload)

    def _save(self, payload):
        config = self._read_config()
        plan = self._selected(config, payload.get("planId") if isinstance(payload, dict) else "")
        if plan.get("source") == "history":
            raise ValueError("The seven-day history snapshot is read-only.")
        path = Path(plan["path"])
        backup = None
        if path.is_file():
            backup = self._backup_path(path)
            shutil.copy2(path, backup)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.stem}.save-{uuid.uuid4().hex}.tmp.json")
        try:
            output = self._run_script("save", temporary)
            self._layout_payload(temporary)
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink()
            except OSError:
                pass
        history_warning = ""
        if plan.get("source") in {"remembered", "device"}:
            try:
                now = self._now()
                state = self._read_history()
                self._archive_snapshot(state, path, now, "manual")
                state["lastCapturedAt"] = now.isoformat()
                self._update_seven_day_snapshot(state, now)
                self._write_history(state)
            except (OSError, ValueError) as error:
                history_warning = str(error)
        result = self.status()
        result.update({
            "saved": str(path),
            "backup": str(backup) if backup else "",
            "output": output,
            "historyUpdated": not bool(history_warning),
            "historyWarning": history_warning,
        })
        return result

    def refresh_history(self, payload=None):
        raw_force = payload.get("force", False) if isinstance(payload, dict) else False
        if not isinstance(raw_force, bool):
            raise ValueError("Desktop layout history force must be a JSON boolean.")
        force = raw_force
        with self._lock:
            state = self._read_history()
            if not force and not self._history_status(state)["due"]:
                result = self.status()
                result["captured"] = False
                return result

            config = self._read_config()
            current_plan = self._current_plan(config)
            current_path = Path(current_plan["path"])
            now = self._now()
            if current_path.is_file():
                existing_time = self._layout_capture_time(current_path, now)
                self._archive_snapshot(state, current_path, existing_time, "previous")

            self.history_dir.mkdir(parents=True, exist_ok=True)
            capture_path = self.history_dir / f".desktop-layout-capture-{uuid.uuid4().hex}.json"
            temporary = None
            try:
                output = self._run_script("save", capture_path)
                self._layout_payload(capture_path)
                snapshot = self._archive_snapshot(state, capture_path, now, "automatic")
                current_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = current_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
                shutil.copy2(capture_path, temporary)
                os.replace(temporary, current_path)
            finally:
                if temporary is not None:
                    try:
                        temporary.unlink()
                    except OSError:
                        pass
                try:
                    capture_path.unlink()
                except OSError:
                    pass

            state["lastCapturedAt"] = now.isoformat()
            self._update_seven_day_snapshot(state, now)
            self._write_history(state)
            result = self.status()
            result.update({
                "captured": True,
                "snapshot": snapshot["path"],
                "saved": str(current_path),
                "output": output,
            })
            return result

    def _verify_restore(self, target_path, snapshot_name="last-restored.json"):
        self.verification_dir.mkdir(parents=True, exist_ok=True)
        actual_path = self.verification_dir / snapshot_name
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

    def _rollback_restore(self, rollback_path):
        rollback = {
            "attempted": True,
            "healthy": False,
            "path": str(rollback_path),
            "output": "",
            "verification": None,
            "error": "",
        }
        try:
            rollback["output"] = self._run_script("restore", rollback_path)
            rollback["verification"] = self._verify_restore(
                rollback_path,
                snapshot_name="last-rollback.json",
            )
            rollback["healthy"] = bool(rollback["verification"].get("healthy"))
        except Exception as error:
            rollback["error"] = str(error)
        return rollback

    def restore(self, payload):
        with self._lock:
            return self._restore(payload)

    def _restore(self, payload):
        config = self._read_config()
        plan = self._selected(config, payload.get("planId") if isinstance(payload, dict) else "")
        path = Path(plan["path"])
        self._layout_payload(path)
        self.verification_dir.mkdir(parents=True, exist_ok=True)
        rollback_path = self.verification_dir / "before-last-restore.json"
        self._run_script("save", rollback_path)
        self._layout_payload(rollback_path)
        try:
            output = self._run_script("restore", path)
            verification = self._verify_restore(path)
        except Exception as error:
            rollback = self._rollback_restore(rollback_path)
            result = self.status()
            result.update({
                "ok": False,
                "finalState": "rolled-back" if rollback["healthy"] else "rollback-failed",
                "restoreError": str(error),
                "restored": str(path),
                "output": "",
                "verification": None,
                "rolledBack": True,
                "rollback": rollback,
            })
            return result
        rollback = None
        if not verification["healthy"]:
            rollback = self._rollback_restore(rollback_path)
        final_state = (
            "restored"
            if rollback is None
            else "rolled-back"
            if rollback["healthy"]
            else "rollback-failed"
        )
        result = self.status()
        result.update({
            "ok": final_state == "restored",
            "finalState": final_state,
            "restoreError": "",
            "restored": str(path),
            "output": output,
            "verification": verification,
            "rolledBack": rollback is not None,
            "rollback": rollback,
        })
        return result
