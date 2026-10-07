"""Real Git regression checks with temporary worktrees and local bare remotes only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from console_developer_update import ConsoleDeveloperUpdateService, DeveloperUpdateError, _GitFailure


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def git(root, *args, data=None):
    result = subprocess.run(["git", "-C", str(root), *args], input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    require(result.returncode == 0, "fixture git command failed: " + " ".join(args))
    return result.stdout.decode().strip()


class Fixture:
    def __init__(self, base):
        # Windows runners may give TEMP an 8.3 alias; match the service's
        # canonical paths so index-failure injection reaches the real rename.
        base = base.resolve()
        self.root = base / "source"
        self.root.mkdir()
        self.remote = base / "remote.git"
        self.remote.mkdir()
        git(self.remote, "init", "--bare", "--initial-branch=main")
        git(self.root, "init", "--initial-branch=main")
        git(self.root, "config", "user.name", "Local Test")
        git(self.root, "config", "user.email", "test@example.invalid")
        git(self.root, "config", "core.autocrlf", "false")
        self.write("app-manifest.json", json.dumps({"version": "1.0.78", "repository": "tx74666/CodexControlConsole"}))
        self.write("app.js", "const answer = 1;\n")
        self.write("other.py", "first\nsecond\n")
        self.write("docs/mobile-refresh/local.md", "original private handoff\n")
        git(self.root, "add", "app-manifest.json", "app.js", "other.py", "docs/mobile-refresh/local.md")
        git(self.root, "commit", "-m", "Initial fixture")
        git(self.root, "remote", "add", "origin", str(self.remote))
        git(self.root, "push", "--no-follow-tags", "origin", "main")
        self.initial = git(self.root, "rev-parse", "HEAD")
        self.service = ConsoleDeveloperUpdateService(base / "private-state", repo_path=self.root,
                                                     runtime_version="1.0.77", test_remote=self.remote)
        self.service.configure(True)

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode())

    def run(self, request="request-0001", action="update", action_id=None):
        return self.service.update(request, self.service.status()["fingerprint"], action, action_id)

    def wait(self, request="request-0001"):
        until = time.monotonic() + 30
        while time.monotonic() < until:
            operation = self.service.operation(request)
            if operation["status"] not in {"working", "not_found"} and not self.service._running:
                return operation
            time.sleep(.01)
        raise AssertionError("operation did not finish")

    def count(self):
        return int(git(self.root, "rev-list", "--count", "HEAD"))


def case(name, callback):
    with tempfile.TemporaryDirectory(prefix="console-developer-test-") as temporary:
        callback(Fixture(Path(temporary)))
    print("PASS " + name)


def success(f):
    f.write("app.js", "const answer = 2;\n")
    f.write("tools/中文 source.py", "print('源代码')\n")
    f.write("docs/mobile-refresh/local.md", "private new handoff\n")
    f.write(".env", "TEST_SECRET=never-publish\n")
    f.write("work/private.py", "private\n")
    f.write("tokens.json", "private\n")
    f.write(".gitattributes", "*.bin filter=lfs\n")
    git(f.root, "add", "docs/mobile-refresh/local.md")
    preserved = git(f.root, "rev-parse", ":docs/mobile-refresh/local.md")
    before = f.service.status()
    require(before["sourceVersion"] == "1.0.78" and before["runtimeVersion"] == "1.0.77", "versions conflated")
    require([c["path"] for c in before["changes"]] == ["app.js", "tools/中文 source.py"], "private/new paths leaked into preview")
    f.run()
    receipt = f.wait()
    require(receipt["status"] == "success" and receipt["committed"] and receipt["pushed"], "source update failed: " + str(receipt))
    require(f.count() == 2, "wrong commit count")
    require(git(f.remote, "rev-parse", "main") == receipt["commitSha"], "remote differs")
    require(git(f.root, "show", "HEAD:app.js") == "const answer = 2;", "wrong frozen bytes")
    require(git(f.root, "show", "HEAD:docs/mobile-refresh/local.md") == "original private handoff", "excluded staged handoff committed")
    require(git(f.root, "rev-parse", ":docs/mobile-refresh/local.md") == preserved, "unrelated staging changed")
    require("Update v1.0.78" in receipt["summary"] and "2 个文件" in receipt["summary"], "summary does not describe source")
    require("source.js" not in receipt["summary"], "fabricated summary")
    require(not git(f.remote, "tag"), "tags pushed")
    same = f.run()
    require(same["commitSha"] == receipt["commitSha"] and f.count() == 2, "repeated request duplicated commit")


def no_op_and_ahead(f):
    f.run()
    require(f.wait()["status"] == "noop" and f.count() == 1, "clean synchronized no-op failed")
    f.write("app.js", "const answer = 3;\n")
    git(f.root, "add", "app.js")
    git(f.root, "commit", "-m", "Already local")
    sha = git(f.root, "rev-parse", "HEAD")
    f.run("request-0002")
    result = f.wait("request-0002")
    require(result["status"] == "success" and result["commitSha"] == sha and f.count() == 2, "clean ahead created new commit")


def partial(f):
    f.write("other.py", "first staged\nsecond\n")
    git(f.root, "add", "other.py")
    f.write("other.py", "first staged\nsecond unstaged\n")
    index = (f.root / ".git/index").read_bytes()
    status = f.service.status()
    require(not status["canUpdate"] and "部分暂存" in status["blockingReason"], "partial index not blocked")
    try:
        f.run()
        raise AssertionError("partial update accepted")
    except DeveloperUpdateError:
        pass
    require(index == (f.root / ".git/index").read_bytes() and f.count() == 1, "partial staging changed")


def stale_preview(f):
    f.write("app.js", b"const answer = 2;\n")
    fingerprint = f.service.status()["fingerprint"]
    old_stat = (f.root / "app.js").stat()
    f.write("app.js", b"const answer = 3;\n")
    os.utime(f.root / "app.js", ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
    try:
        f.service.update("request-0001", fingerprint)
        raise AssertionError("same size/date byte change accepted")
    except DeveloperUpdateError:
        pass
    require(f.count() == 1, "stale preview committed")


def remote_ahead(f):
    # Build an unseen remote commit in a second local source; do not fetch it into f.
    second = f.root.parent / "second"
    git(f.root.parent, "clone", str(f.remote), str(second))
    git(second, "config", "user.name", "Other Test")
    git(second, "config", "user.email", "other@example.invalid")
    (second / "app.js").write_text("remote change\n")
    git(second, "add", "app.js")
    git(second, "commit", "-m", "Remote ahead")
    git(second, "push", "origin", "main")
    remote = git(f.remote, "rev-parse", "main")
    f.write("app.js", "local change\n")
    index = (f.root / ".git/index").read_bytes()
    f.run()
    require(f.wait()["status"] == "conflict", "remote ahead not blocked")
    require(f.count() == 1 and git(f.remote, "rev-parse", "main") == remote, "remote conflict mutated commits")
    require(index == (f.root / ".git/index").read_bytes(), "remote conflict mutated index")


def push_failure_resume(f):
    f.write("app.js", "local failure\n")
    original = f.service._git
    pushes = []
    def fail(root, *arguments, **kwargs):
        if arguments[0] == "push":
            pushes.append(arguments)
            raise _GitFailure("secret https://token@github.com/never-expose")
        return original(root, *arguments, **kwargs)
    with patch.object(f.service, "_git", fail):
        f.run()
        result = f.wait()
    require(result["status"] == "push_failed" and result["committed"] and result["canRetryPush"], "failure receipt lost commit")
    sha, summary = result["commitSha"], result["summary"]
    require("token" not in result["error"] and "https:" not in result["error"], "stderr leaked")
    f.run()  # Delayed original POST must never retry.
    require(len(pushes) == 1 and f.service.operation()["status"] == "push_failed", "duplicate update restarted failed push")
    reopened = ConsoleDeveloperUpdateService(f.service.state_dir, runtime_version="1.0.77", test_remote=f.remote)
    f.service = reopened
    f.run(action="retry", action_id="action-retry-0001")
    resumed = f.wait()
    require(resumed["status"] == "success" and resumed["commitSha"] == sha and resumed["summary"] == summary and f.count() == 2, "resume recreated commit")
    f.run(action="retry", action_id="action-retry-0001")
    require(f.count() == 2, "repeated recovery action changed commit")
    require(pushes[0] == ("push", "--no-follow-tags", "origin", sha + ":refs/heads/main"), "push refspec or tags unsafe")


def unknown_verify(f):
    f.write("app.js", "unknown upload\n")
    original = f.service._git
    ls_count, push_count = 0, 0
    def unknown(root, *arguments, **kwargs):
        nonlocal ls_count, push_count
        if arguments[0] == "ls-remote":
            ls_count += 1
            if ls_count > 1:
                raise _GitFailure("unavailable")
        if arguments[0] == "push":
            push_count += 1
            raise _GitFailure("timeout")
        return original(root, *arguments, **kwargs)
    with patch.object(f.service, "_git", unknown):
        f.run()
        require(f.wait()["status"] == "unknown", "uncertain push not unknown")
        old_count = ls_count
        f.service.operation(); f.service.status(); f.run()
        require(ls_count == old_count and push_count == 1, "read/duplicate did network")
    sha = f.service.operation()["commitSha"]
    f.run(action="verify", action_id="action-verify-001")
    verified = f.wait()
    require(verified["status"] == "push_failed" and push_count == 1 and git(f.remote, "rev-parse", "main") != sha,
            "verify resent original push")
    f.run(action="verify", action_id="action-verify-001")
    require(f.service.operation()["status"] == "push_failed", "replayed verify created new action")
    f.run(action="retry", action_id="action-retry-001")
    require(f.wait()["status"] == "success" and f.count() == 2, "verified retry failed")


def response_lost_after_push(f):
    f.write("app.js", "delivered but response lost\n")
    original = f.service._git
    pushes = []
    def lost(root, *arguments, **kwargs):
        if arguments[0] == "push":
            pushes.append(arguments)
            original(root, *arguments, **kwargs)
            raise _GitFailure("timeout")
        return original(root, *arguments, **kwargs)
    with patch.object(f.service, "_git", lost):
        f.run()
        require(f.wait()["status"] == "success", "delivered push not verified")
    require(len(pushes) == 1 and f.count() == 2, "lost response duplicated push/commit")


def concurrent_and_lock(f):
    f.write("app.js", "concurrent bytes\n")
    original = f.service._remote_head
    second = ConsoleDeveloperUpdateService(f.root.parent / "other-state", repo_path=f.root, test_remote=f.remote)
    second.configure(True)
    second_fingerprint = second.status()["fingerprint"]
    entered, release = threading.Event(), threading.Event()
    def slow(root):
        entered.set()
        require(release.wait(30), "test lock wait expired")
        return original(root)
    with patch.object(f.service, "_remote_head", slow):
        f.run()
        require(entered.wait(10), "operation did not enter")
        require(f.service.busy, "busy not true")
        try:
            second.update("request-other-01", second_fingerprint)
            raise AssertionError("cross-instance repo lock bypassed")
        except DeveloperUpdateError:
            pass
        require(f.run()["status"] == "working", "same request not idempotent in flight")
        try:
            f.service.configure(False)
            raise AssertionError("in-flight configure accepted")
        except DeveloperUpdateError:
            pass
        release.set()
        require(f.wait()["status"] == "success", "locked operation failed")
    require(not f.service.busy and f.count() == 2, "busy/duplicate state wrong")


def change_during_remote_check(f):
    f.write("app.js", "first frozen bytes\n")
    original = f.service._remote_head
    def changed(root):
        result = original(root)
        f.write("app.js", "later concurrent writer\n")
        return result
    with patch.object(f.service, "_remote_head", changed):
        f.run()
        require(f.wait()["status"] == "conflict", "writer during remote check mixed commit")
    require(f.count() == 1 and (f.root / "app.js").read_text() == "later concurrent writer\n", "writer content reset")


def delete_and_crlf(f):
    git(f.root, "config", "core.autocrlf", "true")
    f.write("app.js", b"const answer = 9;\r\n")
    (f.root / "other.py").unlink()
    f.run()
    result = f.wait()
    require(result["status"] == "success", "CRLF or deletion failed: " + str(result))
    require(git(f.root, "show", "HEAD:app.js") == "const answer = 9;", "canonical Git line ending failed")
    require("other.py" not in git(f.root, "ls-tree", "--name-only", "HEAD").splitlines(), "deleted source kept")


def configuration_boundaries(f):
    before = f.service._settings_path.read_bytes()
    for path in (str(f.root / "docs"), str(f.root.parent)):
        try:
            f.service.configure(True, path)
            raise AssertionError("invalid source accepted")
        except DeveloperUpdateError:
            pass
    require(before == f.service._settings_path.read_bytes(), "failed configure changed settings")
    git(f.root, "remote", "set-url", "origin", "https://secret-token@github.com/tx74666/CodexControlConsole.git")
    status = f.service.status()
    require(not status["canUpdate"] and "secret-token" not in json.dumps(status), "credential URL accepted/exposed")
    denied = ConsoleDeveloperUpdateService(f.root.parent / "denied-state", allowed=False)
    require(not denied.status()["allowed"], "backend allowed gate missing")
    try:
        denied.configure(True, str(f.root))
        raise AssertionError("denied configure accepted")
    except DeveloperUpdateError:
        pass


def read_only(f):
    f.write("app.js", "read only modified\n")
    index = (f.root / ".git/index").read_bytes()
    state = f.service._settings_path.read_bytes()
    original = f.service._git
    calls = []
    def record(root, *arguments, **kwargs):
        calls.append(arguments[0])
        return original(root, *arguments, **kwargs)
    with patch.object(f.service, "_git", record):
        f.service.status(); f.service.operation("unknown-request-01")
    require(not set(calls) & {"fetch", "ls-remote", "push", "commit", "update-ref", "update-index", "config"}, "GET mutated/networked")
    require(index == (f.root / ".git/index").read_bytes() and state == f.service._settings_path.read_bytes(), "read-only changed index/settings")


def interrupted(f):
    f.write("app.js", "interrupted bytes\n")
    settings = f.service._settings()
    settings["lastRequestId"] = "request-stale-01"
    f.service._atomic_json(f.service._settings_path, settings)
    operation = {"requestId": "request-stale-01", "status": "working", "phase": "preparing", "summary": "",
                 "commitSha": "", "committed": False, "pushed": False, "error": "", "ownerPid": os.getpid(),
                 "ownerId": "dead-owner", "actions": {}, "canRetryPush": False}
    f.service._atomic_json(f.service._operations_dir / "request-stale-01.json", operation)
    require(f.service.operation()["status"] == "unknown" and not f.service.busy, "interrupted receipt not isolated")
    f.run("request-stale-01", "verify", "action-stale-01")
    require(f.wait("request-stale-01")["status"] == "conflict" and f.count() == 1, "startup/verify created commit")


def prepared_cas_failure(f):
    f.write("app.js", "prepared snapshot\n")
    original = f.service._save_operation
    def moved(operation, **values):
        result = original(operation, **values)
        if values.get("phase") == "committing":
            f.write("app.js", "writer after object creation\n")
        return result
    with patch.object(f.service, "_save_operation", moved):
        f.run()
        result = f.wait()
    require(result["status"] == "conflict" and not result["committed"] and not result["commitSha"] and f.count() == 1,
            "prepared object became a locked pending commit")
    require(f.service.status()["canUpdate"], "prepared object blocked fresh preview")
    f.run("request-0002")
    require(f.wait("request-0002")["status"] == "success", "fresh request could not recover pre-CAS failure")


def index_reconcile_failure(f):
    f.write("app.js", "committed before index failure\n")
    original = os.replace
    def fail_index(source, destination):
        if Path(source) == f.root / ".git/index.lock" and Path(destination) == f.root / ".git/index":
            raise PermissionError("fixture index rename failed")
        return original(source, destination)
    with patch("console_developer_update.os.replace", fail_index):
        f.run()
        result = f.wait()
    sha = result["commitSha"]
    require(result["status"] == "unknown" and result["committed"] and result["indexPending"] and f.count() == 2,
            "post-ref failure lost confirmed commit")
    require((f.root / ".git/index.lock").exists() and f.service.status()["canUpdate"], "pending index had no recovery entry")
    restarted = ConsoleDeveloperUpdateService(f.service.state_dir, test_remote=f.remote)
    f.service = restarted
    f.run(action="verify", action_id="action-index-verify")
    verified = f.wait()
    require(verified["status"] == "push_failed" and verified["indexPending"], "verify mutated index or lost original SHA")
    require(git(f.remote, "rev-parse", "main") == f.initial, "verify resent commit")
    f.run(action="retry", action_id="action-index-retry")
    require(f.wait()["status"] == "success" and f.count() == 2 and git(f.remote, "rev-parse", "main") == sha,
            "index journal retry failed or recreated commit")
    require(not (f.root / ".git/index.lock").exists(), "own Git lock leaked")
    require(not git(f.root, "diff-index", "--cached", "--name-only", "HEAD"), "index not reconciled")


def existing_private_history(f):
    f.write("localdocs/note.md", "private committed by another workflow\n")
    git(f.root, "add", "localdocs/note.md")
    git(f.root, "commit", "-m", "Private fixture")
    (f.root / "localdocs/note.md").unlink()
    git(f.root, "add", "localdocs/note.md")
    git(f.root, "commit", "-m", "Removed fixture")
    status = f.service.status()
    require(status["outgoingCommitCount"] == 2 and not status["canUpdate"] and "私有资料" in status["blockingReason"],
            "outgoing private history vanished behind clean final tree")
    require(git(f.remote, "rev-parse", "main") == f.initial, "private history pushed")


def verify_with_new_partial_staging(f):
    f.write("app.js", "original committed content\n")
    original = f.service._git
    def fail(root, *arguments, **kwargs):
        if arguments[0] == "push":
            raise _GitFailure("failed")
        return original(root, *arguments, **kwargs)
    with patch.object(f.service, "_git", fail):
        f.run()
        require(f.wait()["status"] == "push_failed", "fixture push unexpectedly succeeded")
    sha = f.service.operation()["commitSha"]
    f.write("other.py", "new staged part\nsecond\n")
    git(f.root, "add", "other.py")
    f.write("other.py", "new staged part\nnew unstaged part\n")
    index = (f.root / ".git/index").read_bytes()
    require(f.service.status()["canUpdate"], "partial unrelated edits blocked original SHA recovery")
    f.run(action="retry", action_id="action-new-partial")
    require(f.wait()["status"] == "success" and f.count() == 2 and git(f.remote, "rev-parse", "main") == sha,
            "original SHA retry included later partial edits")
    require(index == (f.root / ".git/index").read_bytes(), "recovery changed later partial staging")


def conflict_verify_after_manual_push(f):
    f.write("app.js", "original content\n")
    original = f.service._git
    def fail(root, *arguments, **kwargs):
        if arguments[0] == "push":
            raise _GitFailure("failed")
        return original(root, *arguments, **kwargs)
    with patch.object(f.service, "_git", fail):
        f.run()
        result = f.wait()
    f.service._save_operation(result, status="conflict", error="fixture user-resolved conflict")
    git(f.root, "push", "--no-follow-tags", "origin", result["commitSha"] + ":refs/heads/main")
    f.run(action="verify", action_id="action-manual-verify")
    require(f.wait()["status"] == "success" and f.count() == 2, "manual resolution had no readonly verification exit")


def unknown_remote_history(f):
    f.write("app.js", "original upload\n")
    original = f.service._git
    def fail(root, *arguments, **kwargs):
        if arguments[0] == "push":
            raise _GitFailure("failed")
        return original(root, *arguments, **kwargs)
    with patch.object(f.service, "_git", fail):
        f.run()
        result = f.wait()
    sha = result["commitSha"]
    git(f.root, "push", "--no-follow-tags", "origin", sha + ":refs/heads/main")
    second = f.root.parent / "remote-writer"
    git(f.root.parent, "clone", str(f.remote), str(second))
    git(second, "config", "user.name", "Other")
    git(second, "config", "user.email", "other@example.invalid")
    (second / "other.py").write_text("new remote descendant\n")
    git(second, "add", "other.py")
    git(second, "commit", "-m", "Later remote")
    git(second, "push", "origin", "main")
    f.service._save_operation(result, status="unknown")
    f.run(action="verify", action_id="action-unknown-history")
    require(f.wait()["status"] == "unknown" and f.count() == 2, "missing remote object falsely proved non-delivery")


def live_process_read_only(f):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        identity = f.service._process_identity(child.pid)
        require(identity is not None and child.poll() is None, "read-only process check interrupted owned child")
        require(f.service._process_identity(child.pid) == identity and child.poll() is None, "process identity unstable")
    finally:
        child.wait(timeout=5)


def hooks_disabled(f):
    marker = f.root / "hook-ran.txt"
    for name in ("pre-push", "reference-transaction"):
        hook = f.root / ".git/hooks" / name
        hook.write_text('#!/bin/sh\nprintf touched > "' + marker.as_posix() + '"\nexit 1\n', encoding="utf-8")
        hook.chmod(0o755)
    f.write("app.js", "only summary and Git upload\n")
    f.run()
    require(f.wait()["status"] == "success" and not marker.exists(), "repository hook ran during constrained update")


def merge_only_private_history(f):
    git(f.root, "checkout", "-b", "fixture-side")
    f.write("other.py", "side change\n")
    git(f.root, "add", "other.py")
    git(f.root, "commit", "-m", "Public side change")
    git(f.root, "checkout", "main")
    f.write("app.js", "main change\n")
    git(f.root, "add", "app.js")
    git(f.root, "commit", "-m", "Public main change")
    git(f.root, "merge", "--no-commit", "--no-ff", "fixture-side")
    f.write(".env", "FIXTURE_ONLY_SECRET=not-for-GitHub\n")
    git(f.root, "add", ".env")
    git(f.root, "commit", "-m", "Fixture merge with extra private file")
    status = f.service.status()
    require(not status["canUpdate"] and any(change["path"] == ".env" for change in status["outgoingChanges"]),
            "merge-only private change bypassed outgoing guard")
    require(git(f.remote, "rev-parse", "main") == f.initial, "merge-only secret uploaded")


def fingerprint_binds_source_root(f):
    import shutil
    f.write("app.js", "identical local snapshot\n")
    copy = f.root.parent / "identical-copy"
    shutil.copytree(f.root, copy)
    original = f.service.status()["fingerprint"]
    f.service.configure(True, str(copy))
    require(f.service.status()["fingerprint"] != original, "identical index/bytes allowed source target swap")
    try:
        f.service.update("request-0001", original)
        raise AssertionError("old source preview authorized different source root")
    except DeveloperUpdateError:
        pass


def main():
    for name, callback in (
        ("exact source snapshot, excludes, unrelated staging and summary", success),
        ("no-op and existing local ahead commit", no_op_and_ahead),
        ("partial staging protected", partial),
        ("same-size same-date byte CAS", stale_preview),
        ("fresh unseen remote ahead stops", remote_ahead),
        ("push failure persisted original-SHA resume", push_failure_resume),
        ("unknown verify never resends and action idempotency", unknown_verify),
        ("successful upload with lost response verified", response_lost_after_push),
        ("in-flight duplicate and cross-instance repo lock", concurrent_and_lock),
        ("concurrent file writer after preview stops", change_during_remote_check),
        ("deleted source and Git CRLF normalization", delete_and_crlf),
        ("local source, canonical origin and backend permission", configuration_boundaries),
        ("GET paths do not write or access remote", read_only),
        ("interrupted operation never auto resumes", interrupted),
        ("prepared object CAS failure permits fresh request", prepared_cas_failure),
        ("confirmed ref with failed index rename recovers original SHA", index_reconcile_failure),
        ("private outgoing history blocked even after deletion", existing_private_history),
        ("original SHA recovery preserves later partial edits", verify_with_new_partial_staging),
        ("manual resolution can verify pending conflict", conflict_verify_after_manual_push),
        ("missing remote history remains unknown", unknown_remote_history),
        ("process identity query never interrupts owned process", live_process_read_only),
        ("repository hooks disabled without changing config", hooks_disabled),
        ("merge-only private history blocked", merge_only_private_history),
        ("fingerprint pins exact source root", fingerprint_binds_source_root),
    ):
        case(name, callback)
    print("24 developer update regression checks passed")


if __name__ == "__main__":
    main()
