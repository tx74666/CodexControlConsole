"""Saved-snapshot policy checks using isolated local bare Git repositories only."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve()
spec = importlib.util.spec_from_file_location("publish_snapshot_fixtures", HERE.with_name("check-console-repository-publish.py"))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
module, Fixture, Service, Error = fixtures.module, fixtures.Fixture, fixtures.Service, fixtures.Error
require, child = fixtures.require, fixtures.child
from console_repository_bindings import RepositoryBindingDiscovery


def activity(code="activity_active"):
    return {"kind": "codex_activity", "code": code, "summary": "Codex is editing this repository.",
            "blockers": [{"threadId": "actual-fixture-thread", "title": "Fixture work", "state": "active",
                          "cwd": "/fixture", "scope": {"status": "verified", "mode": "edit", "editRoots": ["/fixture"]}}]}


def set_policy(service, enabled):
    settings = service._settings()
    settings["naming"]["allowActiveWork"] = enabled
    service.configure(settings)


def test_old_settings_default_allow_saved_snapshot():
    with Fixture() as f:
        root, remote, repo = f.repo()
        (root / "tracked.txt").write_text("saved edit\n")
        service = f.service(busy_check=lambda root: activity())
        old = service._settings()
        old["naming"].pop("allowActiveWork")
        module._atomic(service._settings_path, old)  # Migration fixture, not application state.
        current = service.activity_status(repo["id"])
        require(current["activityClear"] is False and current["publicationAllowed"] is True, current)
        require(current["activityPolicy"] == "allow_saved_snapshot" and current["diagnostic"] is None, current)
        require(current["activityNotice"]["blockers"][0]["threadId"] == "actual-fixture-thread", current)
        preview = service.preview()["previews"][0]
        require(preview["status"] == "ready" and preview["activityNotice"]["kind"] == "codex_activity", preview)
        result = child(f.run(service))
        require(result["status"] == "success" and result["activityPolicy"] == "allow_saved_snapshot", result)
        require(result["activityNotice"]["code"] == "activity_active", result)
        require(f.git(remote, "rev-parse", "main") == result["commitSha"])
        require(not hasattr(service._lease, "activity_item") and not hasattr(service._lease, "allow_active_work"))


def test_strict_setting_waits_and_can_be_changed():
    with Fixture() as f:
        root, _, repo = f.repo()
        (root / "tracked.txt").write_text("saved edit\n")
        service = f.service(busy_check=lambda root: activity())
        set_policy(service, False)
        current = service.activity_status(repo["id"])
        require(current["activityClear"] is False and current["publicationAllowed"] is False, current)
        require(current["activityPolicy"] == "strict" and current["diagnostic"]["code"] == "activity_active", current)
        require(current["activityNotice"] == current["diagnostic"], current)
        require(service.preview()["previews"][0]["status"] == "deferred")
        result = child(f.run(service))
        require(result["status"] == "deferred" and result["diagnostic"]["code"] == "activity_active", result)
        require(f.git(root, "rev-list", "--count", "HEAD") == "1")
        set_policy(service, True)
        require(child(f.run(service, "request_00000002"))["status"] == "success")


def test_unknown_codex_scope_is_notice_but_legacy_unknown_is_not_permission():
    for code in ("activity_scope_unknown", "activity_unconfirmed"):
        with Fixture() as f:
            root, _, repo = f.repo()
            (root / "tracked.txt").write_text("saved edit\n")
            service = f.service(busy_check=lambda root: activity(code))
            require(service.activity_status(repo["id"])["publicationAllowed"] is True)
            require(child(f.run(service))["status"] == "success")
    for untyped in ("Some unknown operation", {"code": "activity_active", "summary": "Unverified callback"},
                    {"kind": "other_operation", "code": "activity_active", "summary": "Unknown writer"}):
        with Fixture() as f:
            root, _, repo = f.repo()
            (root / "tracked.txt").write_text("saved edit\n")
            service = f.service(busy_check=lambda root: untyped)
            state = service.activity_status(repo["id"])
            require(state["publicationAllowed"] is False and state["activityNotice"] is None, state)
            require(child(f.run(service))["status"] == "deferred")
            require(f.git(root, "rev-list", "--count", "HEAD") == "1")


def test_actual_work_and_shared_git_lock_are_separate_typed_receipts():
    with Fixture() as f:
        root, _, repo = f.repo()
        (root / "tracked.txt").write_text("saved edit\n")
        discovery = RepositoryBindingDiscovery(workflow_snapshot={"jobs": [{"status": "working", "workspaceRoot": str(root)}]},
                                               desktop_activity={"records": [], "warnings": []})
        holder = {}
        def probe(path):
            return discovery.busy_diagnostic(path, owned_developer_lock=holder["service"].owns_developer_lock(path))
        service = f.service(busy_check=probe)
        holder["service"] = service
        require(discovery.busy_diagnostic(root)["kind"] == "codex_activity")
        lock = root / ".git/console-developer-update.lock"
        with module._file_lock(lock):
            reason = discovery.busy_diagnostic(root)
            require(reason["code"] == "git_lock" and reason["kind"] == "git_operation", reason)
            state = service.activity_status(repo["id"])
            require(not state["publicationAllowed"] and state["diagnostic"]["code"] == "git_lock", state)
            require(child(f.run(service))["diagnostic"]["code"] == "git_lock")
        require(child(f.run(service, "request_00000002"))["status"] == "success")


def test_unverifiable_shared_git_lock_remains_hard_blocker():
    with Fixture() as f:
        root, _, repo = f.repo()
        (root / "tracked.txt").write_text("saved edit\n")
        discovery = RepositoryBindingDiscovery(workflow_snapshot={"jobs": [{"status": "working", "workspaceRoot": str(root)}]},
                                               desktop_activity={"records": [], "warnings": []})
        discovery.lock_probe = lambda unused: "unknown"
        service = f.service(busy_check=discovery.busy_diagnostic)
        state = service.activity_status(repo["id"])
        require(not state["publicationAllowed"] and state["diagnostic"]["code"] == "git_lock", state)
        require(child(f.run(service))["diagnostic"]["code"] == "git_lock")


def test_concurrent_writer_staging_and_history_still_pause():
    class Writer(Service):
        def _git(self, root, *arguments, **kwargs):
            result = super()._git(root, *arguments, **kwargs)
            if "add" in arguments:
                (Path(root) / "tracked.txt").write_text("concurrent edit preserved\n")
            return result
    with Fixture() as f:
        root, _, _ = f.repo()
        (root / "tracked.txt").write_text("saved edit\n")
        result = child(f.run(f.service(Writer, busy_check=lambda root: activity())))
        require(result["status"] == "deferred" and result["diagnostic"]["code"] == "worktree_changed", result)
        require(f.git(root, "rev-list", "--count", "HEAD") == "1")
        require((root / "tracked.txt").read_text() == "concurrent edit preserved\n")
        require(not (root / ".git/index.lock").exists())
    for mode, code in (("stage", "staged_selection"), ("merge", "git_history_operation"), ("lock", "git_lock")):
        with Fixture() as f:
            root, _, _ = f.repo()
            (root / "tracked.txt").write_text("saved edit\n")
            if mode == "stage":
                f.git(root, "add", "tracked.txt")
            else:
                (root / ".git" / ("MERGE_HEAD" if mode == "merge" else "index.lock")).write_text("original owner\n")
            index = (root / ".git/index").read_bytes()
            result = child(f.run(f.service(busy_check=lambda root: activity())))
            require(result["status"] == "deferred" and result["diagnostic"]["code"] == code, result)
            require((root / ".git/index").read_bytes() == index)
            require(f.git(root, "rev-list", "--count", "HEAD") == "1")


def test_execution_policy_is_frozen_and_worker_lease_is_cleared():
    class ChangeSettings(Service):
        def _run_repo_frozen(self, repo, naming, receipt, item):
            settings = self._settings()
            settings["naming"]["allowActiveWork"] = not naming.get("allowActiveWork", True)
            module._atomic(self._settings_path, settings)
            return super()._run_repo_frozen(repo, naming, receipt, item)

        def _run_repo(self, *args):
            try:
                return super()._run_repo(*args)
            finally:
                self.worker_lease_clear = not hasattr(self._lease, "allow_active_work") and not hasattr(self._lease, "activity_item")
    for enabled, expected in ((True, "success"), (False, "deferred")):
        with Fixture() as f:
            root, _, _ = f.repo()
            (root / "tracked.txt").write_text("saved edit\n")
            service = f.service(ChangeSettings, busy_check=lambda root: activity())
            set_policy(service, enabled)
            result = child(f.run(service))
            require(result["status"] == expected, result)
            require(result["activityPolicy"] == ("allow_saved_snapshot" if enabled else "strict"), result)
            require(service.worker_lease_clear)
            require(service._settings()["naming"]["allowActiveWork"] is not enabled)


def test_failed_push_retry_reuses_original_commit_during_active_work():
    class FailPush(Service):
        def _git(self, root, *arguments, **kwargs):
            if arguments and arguments[0] == "push":
                raise module._GitFailure("authentication")
            return super()._git(root, *arguments, **kwargs)
    with Fixture() as f:
        root, remote, _ = f.repo()
        (root / "tracked.txt").write_text("saved edit\n")
        first = child(f.run(f.service(FailPush, busy_check=lambda root: activity())))
        require(first["status"] == "push_failed" and first["commitSha"], first)
        (root / "tracked.txt").write_text("later work remains local\n")
        second = child(f.run(f.service(busy_check=lambda root: activity()), "request_00000002"))
        require(second["status"] == "success" and second["commitSha"] == first["commitSha"], second)
        require(f.git(root, "rev-list", "--count", "HEAD") == "2")
        require(f.git(remote, "rev-parse", "main") == first["commitSha"])
        require((root / "tracked.txt").read_text() == "later work remains local\n")


def test_clear_receipt_and_setting_validation():
    with Fixture() as f:
        _, _, repo = f.repo()
        service = f.service()
        value = service.activity_status(repo["id"])
        require(value["activityClear"] is True and value["publicationAllowed"] is True, value)
        require(value["diagnostic"] is None and value["activityNotice"] is None, value)
        catalog = service.version_catalog()["repositories"][0]
        require(catalog["activityPolicy"] == "allow_saved_snapshot")
        for invalid in ("true", 1, None):
            settings = service._settings()
            settings["naming"]["allowActiveWork"] = invalid
            try:
                service.configure(settings)
                require(False, "Policy accepts only a real boolean")
            except Error:
                pass


def test_notice_bounds_unknown_codes_and_nested_lease_restoration():
    service = object.__new__(Service)
    excessive = activity()
    excessive["summary"] = "s" * 1200
    excessive["blockers"] *= 30
    service._busy_check = lambda root: excessive
    outer, inner = {}, {}
    with service._activity_policy({"allowActiveWork": True}, outer):
        value = service._busy_reason(Path("fixture"))
        require(len(value["summary"]) == 1000 and len(value["blockers"]) == 20, value)
        with service._activity_policy({"allowActiveWork": False}, inner):
            try:
                service._busy_reason(Path("fixture"))
                require(False, "Strict nested policy must still wait")
            except Error:
                require(inner["activityNotice"]["code"] == "activity_active")
        require(service._lease.activity_item is outer and service._lease.allow_active_work is True)
        require(service._busy_reason(Path("fixture"))["kind"] == "codex_activity")
        for code in ("unknown_operation", "git_history_operation", "git_lock"):
            service._busy_check = lambda root, code=code: {"kind": "codex_activity", "code": code, "summary": "Hard or unrecognized operation"}
            try:
                service._busy_reason(Path("fixture"))
                require(False, "Only explicit Codex activity codes are advisory")
            except Error as error:
                require(error.diagnostic.get("kind") != "codex_activity", error.diagnostic)
    require(not hasattr(service._lease, "activity_item") and not hasattr(service._lease, "allow_active_work"))


TESTS = [v for k, v in tuple(globals().items()) if k.startswith("test_") and callable(v)]
if __name__ == "__main__":
    source_paths = [fixtures.SOURCE, HERE, HERE.with_name("check-console-repository-publish.py"), HERE.parents[1] / "console_repository_bindings.py"]
    frozen = {p: module._sha(p.read_bytes()) for p in source_paths}
    selected = [test for test in TESTS if not sys.argv[1:] or test.__name__ in sys.argv[1:]]
    require(len(selected) == len(sys.argv[1:]) if sys.argv[1:] else True, "Unknown test name")
    for test in selected:
        test()
        print("PASS " + test.__name__)
    require(all(module._sha(p.read_bytes()) == sha for p, sha in frozen.items()), "Source changed during verification")
    print(f"{len(selected)} active-work snapshot checks PASS; real repositories untouched")
