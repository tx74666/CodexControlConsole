import json
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop_layout import DesktopLayoutService  # noqa: E402


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def layout_payload(offset=0):
    return {
        "SavedAt": "2026-07-15T12:00:00+08:00",
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

        service = DesktopLayoutService(
            app_dir,
            data_dir=data_dir,
            default_plan_path=default_layout,
            external_script=root / "missing-external.ps1",
            bundled_script=bundled_script,
            startup_file=startup_file,
        )
        status = service.status()
        require(status["localOnly"], "desktop layouts are not marked as device-local")
        require(len(status["plans"]) == 1, "history or preferred JSON was auto-imported")
        require(status["plans"][0]["path"] == str(default_layout), "the canonical current JSON was not selected")
        require(status["startup"]["pointsToCurrent"], "startup script was not checked against the canonical JSON")
        require(status["tool"]["path"] == str(bundled_script), "bundled helper fallback was not selected")

        imported_payload = json.dumps(layout_payload(40)).encode("utf-8")
        imported = service.import_layouts([{
            "filename": "Studio plan.json",
            "data": imported_payload,
        }])
        require(len(imported["plans"]) == 2, "imported plan was not added")
        imported_plan = next(plan for plan in imported["plans"] if plan["source"] == "imported")
        require(Path(imported_plan["path"]).parent == data_dir / "plans", "imported JSON was not copied into device-local data")
        require(Path(imported_plan["path"]).read_bytes() == imported_payload, "imported JSON changed unexpectedly")

        service.select({"planId": "remembered-current"})
        original = default_layout.read_bytes()
        runner_state = {"restored": None, "saveOffset": 100}

        def fake_run(action, path):
            target = Path(path)
            if action == "restore":
                runner_state["restored"] = target
                return "restored"
            if action == "save" and target.name == "last-restored.json":
                shutil.copy2(runner_state["restored"], target)
                return "captured verification"
            if action == "save":
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

        second_save = service.save({"planId": "remembered-current"})
        second_backup = Path(second_save["backup"])
        require(second_backup.is_file() and second_backup != first_backup, "a later backup overwrote an earlier backup")
        require(first_backup.is_file(), "an earlier backup was deleted")

        restored = service.restore({"planId": "remembered-current"})
        require(restored["verification"]["healthy"], "matching restored positions failed verification")
        require(Path(restored["verification"]["snapshot"]).parent == data_dir / "verification", "verification snapshot escaped local data")

        fresh_service = DesktopLayoutService(
            app_dir,
            data_dir=root / "fresh-local-data",
            default_plan_path=root / "missing-current.json",
            external_script=root / "missing-external.ps1",
            bundled_script=bundled_script,
            startup_file=root / "missing-startup.vbs",
        )
        fresh = fresh_service.status()
        require(len(fresh["plans"]) == 1, "a new device did not receive a local current plan")
        require(fresh["plans"][0]["source"] == "device", "new-device plan has the wrong source")
        require(not fresh["plans"][0]["exists"], "new-device plan should start unsaved")
        require(Path(fresh["plans"][0]["path"]).parent == fresh_service.plan_dir, "new-device plan is not device-local")

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
