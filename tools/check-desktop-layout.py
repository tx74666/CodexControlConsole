import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop_layout import DesktopLayoutService  # noqa: E402


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def layout_payload(offset=0, saved_at="2026-07-15T12:00:00+08:00"):
    return {
        "SavedAt": saved_at,
        "ComputerName": "TEST-PC",
        "UserName": "tester",
        "IconSize": 48,
        "Screens": [],
        "Icons": [
            {"Name": "First", "X": 20 + offset, "Y": 30},
            {"Name": "Second", "X": 120 + offset, "Y": 30},
        ],
    }


def write_layout(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    with tempfile.TemporaryDirectory(prefix="codex-desktop-layout-") as temporary:
        root = Path(temporary)
        app_dir = root / "app"
        data_dir = root / "local-data"
        layouts_dir = root / "outside-layouts"
        bundled_script = app_dir / "tools" / "DesktopLayout.ps1"
        default_layout = layouts_dir / "desktop-layout-remembered-current.json"
        startup_file = root / "Startup" / "RestoreDesktopLayout.vbs"
        bundled_script.parent.mkdir(parents=True)
        bundled_script.write_text("# test helper\n", encoding="ascii")
        write_layout(default_layout, layout_payload())
        write_layout(layouts_dir / "desktop-layout-preferred.json", layout_payload(10))
        write_layout(layouts_dir / "desktop-layout-history-20260714.json", layout_payload(20))
        startup_file.parent.mkdir(parents=True)
        startup_file.write_text(f'layout = "{default_layout}"\n', encoding="utf-8")
        clock = {"now": datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)}

        service = DesktopLayoutService(
            app_dir,
            data_dir=data_dir,
            default_plan_path=default_layout,
            external_script=root / "missing-external.ps1",
            bundled_script=bundled_script,
            startup_file=startup_file,
            clock=lambda: clock["now"],
        )
        status = service.status()
        require(status["localOnly"], "desktop layouts are not marked as device-local")
        require(len(status["plans"]) == 2, "current and seven-day plans were not exposed together")
        require(status["plans"][0]["path"] == str(default_layout), "the canonical current JSON was not selected")
        require(status["plans"][1]["source"] == "history", "seven-day history plan is missing")
        require(not status["plans"][1]["exists"], "seven-day history should start empty")
        require(not any("preferred" in plan["path"].casefold() for plan in status["plans"]), "preferred JSON was auto-imported")
        require(not any("20260714" in plan["path"] for plan in status["plans"]), "legacy history JSON was auto-imported")
        require(status["startup"]["pointsToCurrent"], "startup script was not checked against the canonical JSON")
        require(not status["startup"]["restoresLayout"], "a harmless startup note was mistaken for auto-restore")
        require(status["startup"]["nativeWindowsLayout"], "native Windows layout is not authoritative")
        require(status["history"]["automaticRestore"] is False, "history unexpectedly enables automatic restore")
        require(status["tool"]["path"] == str(bundled_script), "bundled helper fallback was not selected")

        imported_payload = json.dumps(layout_payload(40)).encode("utf-8")
        imported = service.import_layouts([{
            "filename": "Studio plan.json",
            "data": imported_payload,
        }])
        require(len(imported["plans"]) == 3, "imported plan was not added")
        imported_plan = next(plan for plan in imported["plans"] if plan["source"] == "imported")
        require(Path(imported_plan["path"]).parent == data_dir / "plans", "imported JSON was not copied into device-local data")
        require(Path(imported_plan["path"]).read_bytes() == imported_payload, "imported JSON changed unexpectedly")
        invalid_position = layout_payload(0)
        invalid_position["Icons"][0]["X"] = 40000
        try:
            service.import_layouts([{
                "filename": "out-of-range.json",
                "data": json.dumps(invalid_position).encode("utf-8"),
            }])
            raise AssertionError("an out-of-range desktop coordinate was imported")
        except ValueError as error:
            require("Windows-supported range" in str(error), "an invalid coordinate failed for the wrong reason")

        service.select({"planId": "remembered-current"})
        original = default_layout.read_bytes()
        save_temporary_pattern = f".{default_layout.stem}.save-*.tmp.json"

        def require_staged_save_target(path):
            target = Path(path)
            require(target != default_layout, "save helper was allowed to overwrite the formal layout directly")
            require(target.parent == default_layout.parent, "save staging file was not created beside the formal layout")
            require(target.suffix.casefold() == ".json", "save staging file is not JSON")

        def require_no_save_temporary_files():
            require(
                not list(default_layout.parent.glob(save_temporary_pattern)),
                "save left a temporary layout file behind",
            )

        def truncated_failure_run(action, path):
            require(action == "save", "failed-save test invoked an unexpected helper action")
            require_staged_save_target(path)
            Path(path).write_text('{"Icons": [', encoding="utf-8")
            raise RuntimeError("simulated interrupted desktop capture")

        service._run_script = truncated_failure_run
        try:
            service.save({"planId": "remembered-current"})
            raise AssertionError("a helper exception during save was ignored")
        except RuntimeError as error:
            require("simulated interrupted" in str(error), "failed save raised the wrong error")
        require(default_layout.read_bytes() == original, "a failed save changed the formal layout")
        require_no_save_temporary_files()

        def invalid_success_run(action, path):
            require(action == "save", "invalid-save test invoked an unexpected helper action")
            require_staged_save_target(path)
            Path(path).write_text('{"Icons": []}', encoding="utf-8")
            return "reported success with an invalid layout"

        service._run_script = invalid_success_run
        try:
            service.save({"planId": "remembered-current"})
            raise AssertionError("an invalid captured layout replaced the formal layout")
        except ValueError as error:
            require("does not contain any Icons" in str(error), "invalid save failed for the wrong reason")
        require(default_layout.read_bytes() == original, "an invalid save changed the formal layout")
        require_no_save_temporary_files()

        runner_state = {"restored": None, "saveOffset": 100, "saveTargets": []}

        def fake_run(action, path):
            target = Path(path)
            if action == "restore":
                runner_state["restored"] = target
                return "restored"
            if action == "save" and target.name == "last-restored.json":
                shutil.copy2(runner_state["restored"], target)
                return "captured verification"
            if action == "save" and target.name == "before-last-restore.json":
                write_layout(target, layout_payload(runner_state["saveOffset"]))
                return "captured rollback"
            if action == "save":
                require_staged_save_target(target)
                runner_state["saveTargets"].append(target)
                write_layout(target, layout_payload(runner_state["saveOffset"]))
                runner_state["saveOffset"] += 10
                return "saved"
            raise AssertionError(f"unexpected action: {action}")

        service._run_script = fake_run
        first_save = service.save({"planId": "remembered-current"})
        first_backup = Path(first_save["backup"])
        require(first_backup.is_file(), "save did not create a backup first")
        require(first_backup.read_bytes() == original, "backup does not contain the pre-save JSON")
        require(default_layout.read_bytes() != original, "save did not update the selected plan")
        require_no_save_temporary_files()

        before_second_save = default_layout.read_bytes()
        second_save = service.save({"planId": "remembered-current"})
        second_backup = Path(second_save["backup"])
        require(second_backup.is_file() and second_backup != first_backup, "a later backup overwrote an earlier backup")
        require(second_backup.read_bytes() == before_second_save, "later backup is not the pre-save formal JSON")
        require(first_backup.is_file(), "an earlier backup was deleted")
        require(runner_state["saveTargets"][0] != runner_state["saveTargets"][1], "save reused a staging filename")
        require_no_save_temporary_files()

        before_history_failure = default_layout.read_bytes()
        original_write_history = service._write_history

        def fail_history_write(_state):
            raise OSError("simulated unavailable history storage")

        service._write_history = fail_history_write
        try:
            degraded_save = service.save({"planId": "remembered-current"})
        finally:
            service._write_history = original_write_history
        degraded_backup = Path(degraded_save["backup"])
        require(degraded_save["historyWarning"], "history failure was not returned as a save warning")
        require(default_layout.read_bytes() != before_history_failure, "history failure rolled back a successful save")
        require(degraded_backup.read_bytes() == before_history_failure, "degraded save backup is not the prior layout")
        require_no_save_temporary_files()

        restored = service.restore({"planId": "remembered-current"})
        require(restored["verification"]["healthy"], "matching restored positions failed verification")
        require(not restored["rolledBack"], "a healthy desktop restore was unexpectedly rolled back")
        require(Path(restored["verification"]["snapshot"]).parent == data_dir / "verification", "verification snapshot escaped local data")

        restore_actions = []

        def failing_restore_run(action, path):
            target = Path(path)
            if action == "save":
                write_layout(target, layout_payload(200))
                return "captured"
            if action == "restore":
                restore_actions.append(target.name)
                return "restored"
            raise AssertionError(f"unexpected action: {action}")

        def verify_failed_then_rollback(target, snapshot_name="last-restored.json"):
            healthy = Path(target).name == "before-last-restore.json"
            return {
                "healthy": healthy,
                "checkedIcons": 2,
                "missing": [] if healthy else ["First"],
                "mismatches": [],
                "overlaps": [],
                "snapshot": str(data_dir / "verification" / snapshot_name),
            }

        service._run_script = failing_restore_run
        service._verify_restore = verify_failed_then_rollback
        rolled_back = service.restore({"planId": "remembered-current"})
        require(rolled_back["rolledBack"], "an unhealthy desktop restore was not rolled back")
        require(rolled_back["rollback"]["healthy"], "the pre-restore desktop layout was not recovered")
        require(
            restore_actions == [default_layout.name, "before-last-restore.json"],
            "desktop rollback did not restore the pre-operation snapshot",
        )

        fresh_service = DesktopLayoutService(
            app_dir,
            data_dir=root / "fresh-local-data",
            default_plan_path=root / "missing-current.json",
            external_script=root / "missing-external.ps1",
            bundled_script=bundled_script,
            startup_file=root / "missing-startup.vbs",
        )
        fresh = fresh_service.status()
        require(len(fresh["plans"]) == 2, "a new device did not receive current and history plans")
        require(fresh["plans"][0]["source"] == "device", "new-device plan has the wrong source")
        require(not fresh["plans"][0]["exists"], "new-device plan should start unsaved")
        require(Path(fresh["plans"][0]["path"]).parent == fresh_service.plan_dir, "new-device plan is not device-local")

        history_data = root / "history-local-data"
        history_current = root / "history-current.json"
        history_start = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
        history_clock = {"now": history_start}
        write_layout(history_current, layout_payload(0, history_start.isoformat()))
        history_service = DesktopLayoutService(
            app_dir,
            data_dir=history_data,
            default_plan_path=history_current,
            bundled_script=bundled_script,
            startup_file=root / "missing-history-startup.vbs",
            clock=lambda: history_clock["now"],
        )
        actions = []

        def history_run(action, path):
            actions.append(action)
            require(action == "save", "automatic history attempted to move desktop icons")
            write_layout(path, layout_payload(len(actions) * 10, history_clock["now"].isoformat()))
            return "captured"

        history_service._run_script = history_run
        first_capture = history_service.refresh_history({})
        require(first_capture["captured"], "initial current-desktop snapshot was not captured")
        require(actions == ["save"], "initial history capture used an unexpected action")
        require(not history_service.refresh_history({})["captured"], "history recaptured before the interval elapsed")
        require(actions == ["save"], "an early refresh still invoked the desktop helper")

        history_clock["now"] += timedelta(days=2)
        require(not history_service.refresh_history({})["captured"], "history recaptured after only two days")
        history_clock["now"] += timedelta(days=1)
        require(history_service.refresh_history({})["captured"], "three-day history refresh did not run")
        history_clock["now"] += timedelta(days=3)
        third_capture = history_service.refresh_history({})
        require(third_capture["captured"], "second three-day history refresh did not run")
        require(actions == ["save", "save", "save"], "automatic history called something other than save")
        require(third_capture["history"]["sevenDayAvailable"], "a six-day snapshot was not offered as about seven days ago")
        seven_day = next(plan for plan in third_capture["plans"] if plan["source"] == "history")
        require(seven_day["valid"] and seven_day["exists"], "seven-day plan is not restorable")
        require(Path(seven_day["path"]).parent == history_service.plan_dir, "seven-day plan escaped device-local data")
        require(third_capture["history"]["snapshotCount"] >= 3, "rolling history did not retain earlier snapshots")
        try:
            history_service.save({"planId": "seven-days-ago"})
            raise AssertionError("seven-day history could be overwritten")
        except ValueError as error:
            require("read-only" in str(error), "history save failed for the wrong reason")

        concurrent_data = root / "concurrent-local-data"
        concurrent_service = DesktopLayoutService(
            app_dir,
            data_dir=concurrent_data,
            bundled_script=bundled_script,
            startup_file=root / "missing-concurrent-startup.vbs",
        )
        concurrent_service.status()
        original_read_config = concurrent_service._read_config

        def delayed_read_config():
            config = original_read_config()
            time.sleep(0.05)
            return config

        concurrent_service._read_config = delayed_read_config
        uploads = [
            [{"filename": f"concurrent-{index}.json", "data": json.dumps(layout_payload(index)).encode("utf-8")}]
            for index in range(2)
        ]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(concurrent_service.import_layouts, uploads))
        imported_ids = {item["id"] for result in results for item in result["imported"]}
        persisted_ids = {
            plan["id"]
            for plan in concurrent_service.status()["plans"]
            if plan["source"] == "imported"
        }
        require(imported_ids <= persisted_ids, "concurrent imports lost a desktop layout plan")

        unchanged_data = root / "unchanged-local-data"
        unchanged_current = root / "unchanged-current.json"
        unchanged_start = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
        unchanged_clock = {"now": unchanged_start}
        unchanged_payload = layout_payload(0, unchanged_start.isoformat())
        write_layout(unchanged_current, unchanged_payload)
        unchanged_service = DesktopLayoutService(
            app_dir,
            data_dir=unchanged_data,
            default_plan_path=unchanged_current,
            bundled_script=bundled_script,
            startup_file=root / "missing-unchanged-startup.vbs",
            clock=lambda: unchanged_clock["now"],
        )

        def unchanged_run(action, path):
            require(action == "save", "unchanged history attempted to restore the desktop")
            write_layout(path, unchanged_payload)
            return "captured unchanged layout"

        unchanged_service._run_script = unchanged_run
        unchanged_status = None
        for day in (0, 3, 6, 9, 12, 15):
            unchanged_clock["now"] = unchanged_start + timedelta(days=day)
            unchanged_status = unchanged_service.refresh_history({})
            require(unchanged_status["captured"], f"unchanged layout was not captured on day {day}")
        require(
            unchanged_status["history"]["sevenDayAvailable"],
            "an unchanged desktop eventually lost its seven-day history",
        )
        require(
            unchanged_status["history"]["snapshotCount"] >= 7,
            "unchanged automatic captures did not retain their logical timeline",
        )
        unchanged_history = next(plan for plan in unchanged_status["plans"] if plan["source"] == "history")
        require(
            unchanged_history["savedAt"] == unchanged_status["history"]["sevenDayCapturedAt"],
            "seven-day history exposed stale file metadata instead of its capture time",
        )

    package_script = (ROOT / "tools" / "build-windows.ps1").read_text(encoding="utf-8")
    runtime_script = (ROOT / "world_console.py").read_text(encoding="utf-8")
    require("from desktop_layout import DesktopLayoutService" in runtime_script, "desktop layout backend is missing from the executable")
    require('"tools\\DesktopLayout.ps1"' in package_script, "generic desktop helper is missing from Setup")
    generic_helper = (ROOT / "tools" / "DesktopLayout.ps1").read_text(encoding="utf-8")
    require("D:\\Q\\DesktopLayout" not in generic_helper, "bundled helper contains a personal layout path")
    require("preferred" not in generic_helper.casefold(), "bundled helper contains legacy preferred-layout behavior")

    print("PASS device-local desktop layouts")


if __name__ == "__main__":
    main()
