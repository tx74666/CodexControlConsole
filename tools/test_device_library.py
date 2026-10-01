"""Deterministic lifecycle/privacy/attribution tests; never run the real sampler."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import device_library as library


def process(pid, parent, name, birth, category=None, resident=100):
    return {"pid": pid, "parentPid": parent, "name": name, "startedAt": birth, "identityCategory": category, "identityReason": "verified fixture", "privateResidentBytes": resident, "workingSetBytes": resident, "privateCommitBytes": resident}


def payload():
    return {"complete": True, "sampledAt": "2026-09-27T00:00:00+08:00", "processInventoryComplete": True, "hardwareComplete": True, "errors": [], "system": {"visiblePhysicalBytes": 1000, "availablePhysicalBytes": 600, "installedPhysicalBytes": 1024, "committedBytes": 800, "commitLimitBytes": 2000, "uptimeSeconds": 100}, "hardware": {"model": "test computer"}, "processes": [process(10, 1, "Codex.exe", "2026-09-27T00:00:00+08:00", "codex")]}


class FakeProcess:
    def __init__(self, args, mode="success", **kwargs):
        self.mode, self.returncode = mode, None
        self._handle = 1
        checkpoint = Path(args[args.index("-OutputPath") + 1])
        if mode != "empty":
            data = payload()
            if mode == "partial":
                data["errors"].append({"metric": "gpu.memory", "reason": "fixture unsupported GPU"})
            library._atomic(checkpoint, data)

    def poll(self):
        if self.mode in {"success", "partial"}:
            self.returncode = 0
        return self.returncode

    def terminate(self):
        self.returncode = 1

    def kill(self):
        self.returncode = 1

    def wait(self, timeout=None):
        return self.returncode


class DeviceLibraryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="device library 中文 ")
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def fake_collect(self, mode="success", **kwargs):
        with patch.object(library.subprocess, "Popen", side_effect=lambda args, **opts: FakeProcess(args, mode, **opts)), patch.object(library, "_measure_process_peak", return_value=4096), patch.object(library, "_child_job", return_value=None):
            return library.collect(self.root, **kwargs)

    def test_verified_codex_ancestry_through_windows_shell(self):
        data = [process(10, 1, "Codex.exe", "2026-09-27T00:00:00Z", "codex"), process(11, 10, "powershell.exe", "2026-09-27T00:01:00Z", "system"), process(12, 11, "unity_mcp.exe", "2026-09-27T00:02:00Z")]
        library.classify_processes(data)
        self.assertEqual([p["category"] for p in data], ["codex"] * 3)

    def test_pid_reuse_does_not_assign_new_parent(self):
        data = [process(10, 1, "Codex.exe", "2026-09-27T00:03:00Z", "codex"), process(12, 10, "python.exe", "2026-09-27T00:02:00Z")]
        library.classify_processes(data)
        self.assertEqual(data[1]["category"], "other")
        self.assertIn("PID", data[1]["classificationReason"])

    def test_missing_birth_time_does_not_assign_parent(self):
        data = [process(10, 1, "Codex.exe", None, "codex"), process(12, 10, "python.exe", "2026-09-27T00:02:00Z")]
        library.classify_processes(data)
        self.assertEqual(data[1]["category"], "other")

    def test_exact_unverified_app_is_unknown_not_zero(self):
        data = payload()
        data["processes"].append(process(20, 1, "devenv.exe", None))
        library._aggregate(data)
        visual = next(g for g in data["groups"] if g["category"] == "visual-studio")
        self.assertIsNone(visual["privateResidentBytes"])
        self.assertTrue(visual["presenceUnconfirmed"])
        blender = next(g for g in data["groups"] if g["category"] == "blender")
        self.assertEqual(blender["privateResidentBytes"], 0)

    def test_private_working_sets_not_total_working_sets_used_for_remainder(self):
        data = payload()
        data["processes"][0]["workingSetBytes"] = 9999
        library._aggregate(data)
        self.assertEqual(data["system"]["systemSharedUnattributedBytes"], 300)

    def test_success_appends_and_updates_indexes_with_unicode_path(self):
        first = self.fake_collect()
        second = self.fake_collect()
        self.assertEqual(first["status"], "completed")
        self.assertNotEqual(first["id"], second["id"])
        self.assertTrue((self.root / first["snapshot"]).exists())
        self.assertEqual(len(library.list_snapshots(self.root)), 2)
        self.assertIn(second["id"], (self.root / "最新檢查.md").read_text(encoding="utf-8"))
        self.assertIn(first["id"], (self.root / "歷史檢查.md").read_text(encoding="utf-8"))
        self.assertFalse((self.root / ".device-library" / "collect.lock").exists())

    def test_gpu_unavailable_partial_report(self):
        result = self.fake_collect("partial")
        self.assertEqual(result["status"], "partial")
        report = (self.root / result["report"]).read_text(encoding="utf-8")
        self.assertIn("fixture unsupported GPU", report)
        self.assertIn("未知／不可用", report)

    def test_timeout_preserves_previous_latest(self):
        good = self.fake_collect()
        old = (self.root / "最新檢查.md").read_bytes()
        timed = self.fake_collect("hung", timeout=1)
        self.assertEqual(timed["status"], "timeout")
        self.assertEqual((self.root / "最新檢查.md").read_bytes(), old)
        self.assertTrue((self.root / good["snapshot"]).exists())

    def test_cancel_before_start_does_not_launch_collector(self):
        event = threading.Event()
        event.set()
        with patch.object(library.subprocess, "Popen") as spawn:
            result = library.collect(self.root, cancel_event=event)
        spawn.assert_not_called()
        self.assertEqual(result["status"], "cancelled")
        self.assertFalse((self.root / "最新檢查.md").exists())

    def test_duplicate_lock_does_not_start_second_job(self):
        lock = self.root / ".device-library" / "collect.lock"
        lock.mkdir(parents=True)
        library._atomic(lock / "owner.json", {"pid": os.getpid(), "processIdentity": library._identity(os.getpid()), "id": "active"})
        with patch.object(library.subprocess, "Popen") as spawn:
            result = library.collect(self.root)
        spawn.assert_not_called()
        self.assertTrue(result["alreadyRunning"])
        self.assertEqual(result["status"], "running")

    def test_failed_start_preserves_prior_evidence(self):
        good = self.fake_collect()
        old = (self.root / "最新檢查.md").read_bytes()
        with patch.object(library.subprocess, "Popen", side_effect=OSError("fixture failure")):
            result = library.collect(self.root)
        self.assertEqual(result["status"], "failed")
        self.assertEqual((self.root / "最新檢查.md").read_bytes(), old)
        self.assertTrue((self.root / good["snapshot"]).exists())

    def test_compare_marks_conditions_and_rejects_path_escape(self):
        a = self.fake_collect(scenario="idle")
        b = self.fake_collect(scenario="development")
        result = library.compare(self.root, "snapshots/" + a["id"] + ".json", b["id"])
        self.assertTrue(any("場景" in item for item in result["comparability"]))
        self.assertTrue((self.root / result["report"]).exists())
        with self.assertRaises(ValueError):
            library.compare(self.root, "../outside", b["id"])
        with self.assertRaises(ValueError):
            library.compare(self.root, a["id"], a["id"])

    def test_stale_status_is_not_permanently_running(self):
        library._atomic(self.root / ".device-library" / "status.json", {"status": "running"})
        self.assertEqual(library.status(self.root)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
