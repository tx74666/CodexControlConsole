"""Activity failures retain actionable actors without changing Git or any real data."""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from console_repository_publish import RepositoryPublishService, RepositoryPublishError


def require(value, message):
    if not value:
        raise AssertionError(message)


with tempfile.TemporaryDirectory(prefix="console-activity-diagnostics-") as temporary:
    root = Path(temporary)
    actor = {"threadId": "actor-fixture", "title": "Character", "agentPath": "/root/review",
             "cwd": str(root), "state": "active", "mode": "edit", "roots": [str(root)], "reason": "declared_current_turn_scope"}
    service = RepositoryPublishService(root / "state", test_mode=True)
    for code in ("activity_active", "activity_scope_unknown", "activity_unconfirmed"):
        service._busy_check = lambda path, code=code: {"code": code, "summary": "等待 Character 完成本仓库工作。", "blockers": [actor]}
        try:
            service._busy_reason(root)
            require(False, "Actual blocked actor must not be bypassed")
        except RepositoryPublishError as error:
            require(error.code == code and error.diagnostic["blockers"] == [actor], "Typed actor and diagnostic must survive")
            require(error.diagnostic["target"] is None, "Activity must not point at an unrelated configuration control")
            item = {"repoId": "fixture", "status": "deferred", "phase": "check", "logs": [],
                    "message": str(error), "diagnostic": error.diagnostic}
            receipt = {"requestId": "activity_fixture_0001", "status": "attention", "repositories": [item]}
            service._save(receipt)
            returned = service.operation(receipt["requestId"])
            require(returned["repositories"][0]["diagnostic"]["blockers"][0]["threadId"] == "actor-fixture",
                    "Durable receipt must retain the actual actor")
    service._busy_check = lambda path: "Existing legacy Work guard"
    try:
        service._busy_reason(root)
        require(False, "Legacy guards must still block")
    except RepositoryPublishError as error:
        require(error.code == "activity_unconfirmed" and str(error) == "Existing legacy Work guard", "Legacy reason compatibility")
    service._busy_check = lambda path: None
    require(service._busy_reason(root) is None, "Verified safe activity permits normal checks")
    native_actor = {key: value for key, value in actor.items() if key not in {"mode", "roots"}}
    native_actor["scope"] = {"status": "verified", "mode": "edit", "editRoots": [str(root)]}
    service._busy_check = lambda path: {"code": "activity_active", "summary": "Native declared actor", "blockers": [native_actor]}
    try:
        service._busy_reason(root)
        require(False, "Native declared actor must remain blocked")
    except RepositoryPublishError as error:
        require(error.diagnostic["blockers"] == [actor], "Native nested declaration must preserve exact mode and roots")
    service._busy_check = lambda path: {"code": "ignore_safety", "summary": None,
                                     "blockers": [None, {"threadId": "kept", "title": "x" * 1000, "cwd": "bad\ncontrol", "roots": ["bad\x00path", str(root)]}]}
    try:
        service._busy_reason(root)
        require(False, "Malformed reason must fail safely")
    except RepositoryPublishError as error:
        require(error.code == "activity_unconfirmed", "Unknown code cannot grant upload")
        actual = error.diagnostic["blockers"][0]
        require(len(actual["title"]) == 200 and "cwd" not in actual and actual["roots"] == [str(root)], "Bound actor display metadata")
    settings = {"repositories": [{"id": "fixture", "path": str(root)}], "naming": {"autoBump": True}}
    service._settings = lambda: settings
    service._busy_check = lambda path: {"code": "activity_active", "summary": "Actual fixture actor is editing", "blockers": [actor]}
    current = service.activity_status("fixture")
    require(current["activityClear"] is False and current["diagnostic"]["blockers"][0]["threadId"] == "actor-fixture",
            "Explicit scoped inspection must report the actual actor")
    require(len(current["sourceIdentity"]) == 64, "Fresh response binds exact configuration")
    service._busy_check = lambda path: None
    clear = service.activity_status("fixture")
    require(clear["activityClear"] is True and clear["diagnostic"] is None and "status" not in clear,
            "No chat activity is not a verified upload or repository readiness")
    settings["naming"]["autoBump"] = False
    require(service.activity_status("fixture")["sourceIdentity"] != clear["sourceIdentity"], "Configuration changes invalidate old actor response")
    try:
        service.activity_status("old-target")
        require(False, "Missing target must not inspect another repository")
    except RepositoryPublishError as error:
        require(error.code == "destination_changed", "Missing activity target is explicitly rejected")

print("PASS activity code, exact actors, durable receipt, safe target, legacy compatibility and malformed metadata guards")
