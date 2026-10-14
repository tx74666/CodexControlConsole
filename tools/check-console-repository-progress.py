"""Offline progress, timeout and read-deadline checks; no real repository writes."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time


SOURCE = Path(__file__).resolve().parents[1] / "console_repository_publish.py"
sys.path.insert(0, str(SOURCE.parent))
spec = importlib.util.spec_from_file_location("publish_progress_under_test", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Service = module.RepositoryPublishService


def require(value, message="assertion failed"):
    if not value:
        raise AssertionError(message)


def fixture():
    temporary = tempfile.TemporaryDirectory(prefix="console-publish-progress-")
    base = Path(temporary.name).resolve()
    return temporary, base, Service(base / "state", test_mode=True)


def receipt(service, identifier="progress_00000001"):
    item = {"repoId": "fixture", "status": "queued", "phase": "queued", "logs": [], "message": "queued"}
    value = {"requestId": identifier, "status": "working", "repositories": [item],
             "owner": {"pid": os.getpid(), "processKey": service._pid_key, "nonce": service._owner}}
    service._save(value)
    return value, item


def test_numeric_progress_and_private_paths():
    parse = module._parse_transfer_progress
    value = parse(b"Writing objects:  80% (16/20), 1.25 MiB | 100.00 KiB/s")
    require(value["percent"] == 80 and value["unit"] == "objects" and value["step"] == "writing_objects")
    private = "upload 2/3 3200/12800 D:/private/secret-token.blend"
    value = parse(private, lfs_file=True)
    require(value["percent"] == 25 and value["scope"] == "file" and value["fileIndex"] == 2)
    require(value["estimatedFileTotal"] is True and "private" not in json.dumps(value) and "secret" not in json.dumps(value))
    require(parse("upload 1/1 99999/100000 x", lfs_file=True)["percent"] == 99.9)
    for record in ("remote: Writing objects: 100% (1/1)", "hint: 100%", "Writing objects: 100% (1/2)",
                   "Writing objects: 10% (0/0)", "Writing objects: 101% (2/1)", "error: Git LFS upload failed"):
        require(parse(record) is None, record)
    for record in ("download 1/1 12/24 secret", "upload 2/1 5/10 secret", "upload 1/1 11/10 secret",
                   "upload 1/1 0/0 secret", "upload 1/1 9007199254740993/9007199254740993 secret"):
        require(parse(record, lfs_file=True) is None, record)


def test_stream_pipes_lfs_and_existing_environment():
    temporary, base, service = fixture()
    try:
        events = []
        code = """import os,time,sys
time.sleep(.1)
os.write(1,b'\\0binary-output\\xff')
os.write(2,b'Writing objects: 50% (1/2)\\r')
with open(os.environ['GIT_LFS_PROGRESS'],'a') as f:
 f.write('upload 1/1 500/1000 secret.blend\\n'); f.flush()
time.sleep(.35)
with open(os.environ['GIT_LFS_PROGRESS'],'a') as f:
 f.write('upload 1/1 1000/1000 secret.blend\\n'); f.flush()
os.write(2,b'Writing objects: 100% (2/2), done.\\n')
"""
        env = os.environ.copy()
        env.pop("GIT_LFS_PROGRESS", None)
        result = service._stream_git([sys.executable, "-u", "-c", code], env, None, 5, events.append)
        require(result.returncode == 0 and result.stdout == b"\0binary-output\xff")
        require(b"Writing objects: 50% (1/2)\r" in result.stderr)
        require(any(event.get("scope") == "file" and event["percent"] == 50 for event in events), events)
        require(any(event.get("scope") == "file" and event["percent"] == 100 for event in events), events)
        require(not list(service.state_dir.glob("lfs-progress-*")), "Owned telemetry trace must be removed")
        external = base / "existing-user-progress.txt"
        external.write_text("original\n")
        env["GIT_LFS_PROGRESS"] = str(external)
        env["GIT_LFS_FORCE_PROGRESS"] = "0"
        code = "import os,time; time.sleep(.1); print(os.environ['GIT_LFS_PROGRESS']); print(os.environ['GIT_LFS_FORCE_PROGRESS'])"
        result = service._stream_git([sys.executable, "-u", "-c", code], env, None, 5, events.append)
        require(result.stdout.decode().splitlines() == [str(external), "0"])
        require(external.read_text() == "original\n", "Do not read, overwrite or remove user's telemetry file")
        code = "import sys,time; time.sleep(.1); sys.stdout.buffer.write(sys.stdin.buffer.read())"
        data = bytes(range(256)) * 1000
        result = service._stream_git([sys.executable, "-u", "-c", code], env, data, 5, events.append)
        require(result.stdout == data, "Raw-pipe writes must preserve all supplied bytes")
    finally:
        temporary.cleanup()


def test_elapsed_phase_percent_and_verified_completion():
    temporary, base, service = fixture()
    try:
        value, item = receipt(service)
        require(service.operation(value["requestId"])["repositories"][0]["progress"]["percent"] is None)
        service._phase(value, item, "check", "checking")
        require(item["progress"]["state"] == "indeterminate" and item["progress"]["percent"] is None)
        service._phase(value, item, "push", "pushing")
        service._transfer_progress(value, item)(module._parse_transfer_progress("Writing objects: 100% (2/2)"))
        require(item["progress"]["state"] == "measured" and item["progress"]["scope"] == "phase")
        service._phase(value, item, "verify", "checking actual remote")
        require(item["progress"]["percent"] is None, "Transfer100 never completes the repository")
        item.update(status="success", phase="complete", commitSha="a" * 40)
        service._save(value)
        require(item["progress"]["percent"] is None and item["progress"]["source"] == "historical_receipt")
        item.update(deliveryVerifiedAt=module._now(), verifiedRemote="a" * 40)
        service._save(value)
        require(item["progress"]["percent"] == 100 and item["progress"]["scope"] == "repository")
        first = item["progress"]["updatedAt"]
        service._save(value)
        require(item["progress"]["updatedAt"] == first, "Terminal elapsed time must stay frozen")
        for state in ("noop", "deferred", "push_failed", "verification_required"):
            item["status"] = state
            service._save(value)
            require(item["progress"]["percent"] is None, state)
    finally:
        temporary.cleanup()


def test_durable_progress_read_during_live_process_and_throttle():
    temporary, base, service = fixture()
    try:
        value, item = receipt(service)
        service._starting = True
        module._LIVE[service._owner] = module.weakref.ref(service)
        service._phase(value, item, "push", "pushing")
        code = "import os,time; time.sleep(.1); os.write(2,b'Writing objects: 25% (1/4)\\r'); time.sleep(.7)"
        result = []
        worker = threading.Thread(target=lambda: result.append(service._stream_git(
            [sys.executable, "-u", "-c", code], os.environ.copy(), None, 5, service._transfer_progress(value, item))))
        worker.start()
        deadline = time.monotonic() + 3
        observed = None
        while time.monotonic() < deadline:
            current = service.operation(value["requestId"])["repositories"][0]["progress"]
            if current.get("percent") == 25:
                observed = current
                break
            time.sleep(.02)
        require(observed and worker.is_alive(), "GET must return measured progress before push exits")
        worker.join(timeout=5)
        require(result and result[0].returncode == 0)
        writes = []
        original_save = service._save
        service._save = lambda current: writes.append(current["repositories"][0]["progress"]["percent"])
        callback = service._transfer_progress(value, item)
        for number in range(101):
            callback(module._parse_transfer_progress(f"Writing objects: {number}% ({number}/100)"))
        require(len(writes) == 1 and item["progress"]["percent"] == 100, writes)
        service._save = original_save
    finally:
        service._starting = False
        module._LIVE.pop(service._owner, None)
        temporary.cleanup()


def test_timeout_only_owns_git_child_tree():
    temporary, base, service = fixture()
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"],
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        marker = base / "owned-child-pid.txt"
        code = """import subprocess,sys,time,pathlib
time.sleep(.1)
child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'])
pathlib.Path(sys.argv[1]).write_text(str(child.pid))
print('Writing objects: 10% (1/10)',file=sys.stderr,flush=True)
time.sleep(20)
"""
        started = time.monotonic()
        try:
            service._stream_git([sys.executable, "-u", "-c", code, str(marker)], os.environ.copy(), None, .7, lambda value: None)
            require(False, "Must time out")
        except subprocess.TimeoutExpired:
            pass
        require(time.monotonic() - started < 4, "Timeout cannot hang on descendant pipe handles")
        require(marker.exists(), "Owned child fixture must actually start")
        pid = int(marker.read_text())
        deadline = time.monotonic() + 2
        while module._process_key(pid) is not None and time.monotonic() < deadline:
            time.sleep(.02)
        require(module._process_key(pid) is None, "Owned hook/LFS child must stop on timeout")
        require(unrelated.poll() is None, "An unrelated process must remain running")
        require(not list(service.state_dir.glob("lfs-progress-*")))
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)
        temporary.cleanup()


def test_stream_error_classification_and_timeout_are_unchanged():
    temporary, base, service = fixture()
    try:
        stream = service._stream_git
        for stderr, expected in ((b"Git LFS upload failed: private data", "lfs"),
                                 (b"fatal: Authentication failed for 'private'", "authentication"),
                                 (b"Writing objects: 50% (1/2)\rfatal: Authentication failed for 'private'", "authentication"),
                                 (b"remote: error: GH013: Repository rule violations found", "rules")):
            service._stream_git = lambda *args, text=stderr: subprocess.CompletedProcess([], 1, b"", text)
            try:
                service._git(base, "push", progress=lambda value: None)
                require(False)
            except module._GitFailure as exc:
                require(exc.code == expected and exc.detail == "", exc.code)
        def timeout(*args):
            raise subprocess.TimeoutExpired("fixture", .1)
        service._stream_git = timeout
        try:
            service._git(base, "push", progress=lambda value: None)
            require(False)
        except module._GitFailure as exc:
            require(exc.code == "timeout")
        service._stream_git = stream
    finally:
        temporary.cleanup()


def test_catalog_deadline_bounds_read_and_never_leaks():
    temporary, base, service = fixture()
    original_run = module.subprocess.run
    try:
        timeouts = []
        def fake_run(command, **kwargs):
            timeouts.append(kwargs["timeout"])
            return subprocess.CompletedProcess(command, 0, b"fixture", b"")
        module.subprocess.run = fake_run
        def read(repo_id):
            service._git(base, "status", timeout=35)
            return {"repositories": []}
        service._version_catalog_read = read
        service.version_catalog(deadline_seconds=.5)
        require(0 < timeouts[-1] <= .5)
        require(not hasattr(service._lease, "catalog_deadline"))
        service._git(base, "status", timeout=35)
        require(timeouts[-1] == 35, "Catalog timeout must not limit later commits or pushes")
        def expired(repo_id):
            time.sleep(.04)
            service._catalog_remaining()
        service._version_catalog_read = expired
        try:
            service.version_catalog(deadline_seconds=.02)
            require(False)
        except module._GitFailure as exc:
            require(exc.code == "timeout")
        require(not hasattr(service._lease, "catalog_deadline"), "Failure must restore deadline too")
        service._lease.catalog_deadline = time.monotonic() + 2
        previous = service._lease.catalog_deadline
        service._version_catalog_read = read
        service.version_catalog(deadline_seconds=.5)
        require(service._lease.catalog_deadline == previous, "Nested read must restore outer scope")
        del service._lease.catalog_deadline
        blocked = base / "saved.blend"
        blocked.write_bytes(b"saved")
        service._lease.catalog_deadline = time.monotonic() - 1
        try:
            service._catalog_stable(blocked)
            require(False)
        except module._GitFailure as exc:
            require(exc.code == "timeout")
        del service._lease.catalog_deadline
        require(blocked.read_bytes() == b"saved")
        large = base / "large-saved.blend"
        large.write_bytes(b"x" * (3 * 1024 * 1024))
        visits = []
        def during_hash():
            visits.append(True)
            if len(visits) == 3:
                raise module._GitFailure("timeout")
        try:
            module._stable(large, check=during_hash)
            require(False)
        except module._GitFailure as exc:
            require(exc.code == "timeout" and len(visits) == 3, "Hashing must check deadline between blocks")
        require(large.stat().st_size == 3 * 1024 * 1024, "Deadline never modifies saved source")
    finally:
        module.subprocess.run = original_run
        temporary.cleanup()


def test_catalog_deadline_is_thread_local():
    temporary, base, service = fixture()
    entered, finish = threading.Event(), threading.Event()
    errors = []
    try:
        def read(repo_id):
            require(service._catalog_remaining() is not None)
            entered.set()
            finish.wait(timeout=2)
            return {"repositories": []}
        service._version_catalog_read = read
        def bounded():
            try:
                service.version_catalog(deadline_seconds=2)
                require(not hasattr(service._lease, "catalog_deadline"))
            except BaseException as exc:
                errors.append(exc)
        worker = threading.Thread(target=bounded)
        worker.start()
        require(entered.wait(timeout=2))
        require(service._catalog_remaining() is None, "A read worker cannot put a deadline on the real upload worker")
        finish.set()
        worker.join(timeout=3)
        require(not worker.is_alive() and not errors, errors)
    finally:
        finish.set()
        temporary.cleanup()


def test_catalog_read_state_and_actual_source_identity():
    diagnostic_spec = importlib.util.spec_from_file_location(
        "publish_diagnostic_read_fixtures", SOURCE.parent / "tools" / "check-console-repository-publish.py")
    fixtures = importlib.util.module_from_spec(diagnostic_spec)
    diagnostic_spec.loader.exec_module(fixtures)
    cases = [(fixtures.DiagnosticReadFixture(), "ready"),
             (fixtures.DiagnosticReadFixture(error=fixtures.Error("Missing root", code="repo_missing")), "error"),
             (fixtures.DiagnosticReadFixture(error=fixtures.module._GitFailure("timeout")), "error")]
    for service, expected in cases:
        row = service.version_catalog()["repositories"][0]
        require(row["readState"] == expected, row)
        settings = service._settings()
        require(row["sourceIdentity"] == module.catalog_source_identity(service.repo, settings["naming"]), row)
    fallback = cases[0][0].version_catalog()["repositories"][0]
    require(fallback["message"] and fallback["diagnostic"]["severity"] == "info" and fallback["readState"] == "ready",
            "An informational fallback message must not imply failed reading")
    repository = {"id": "fixture", "path": "source-a", "branch": "main", "name": "模組"}
    naming = {"preset": "version", "fallbackTitle": "更新進度"}
    identity = module.catalog_source_identity(repository, naming)
    require(identity == module.catalog_source_identity(dict(reversed(list(repository.items()))),
                                                      dict(reversed(list(naming.items())))))
    require(identity != module.catalog_source_identity({**repository, "path": "source-b"}, naming))
    require(identity != module.catalog_source_identity(repository, {**naming, "preset": "module_version"}))
    try:
        module.catalog_source_identity(repository, {"nonfinite": float("nan")})
        require(False, "Nonfinite configuration cannot have a canonical source identity")
    except ValueError:
        pass


def test_last_commit_uses_actual_branch_committer_time_and_rejects_changed_head():
    git_spec = importlib.util.spec_from_file_location(
        "publish_commit_time_git_fixtures", SOURCE.parent / "tools" / "check-console-repository-publish.py")
    fixtures = importlib.util.module_from_spec(git_spec)
    git_spec.loader.exec_module(fixtures)
    with fixtures.Fixture() as files:
        root, remote, repo = files.repo("commit-time")
        files.env.update(GIT_AUTHOR_DATE="2001-01-02T03:04:05+0200", GIT_COMMITTER_DATE="2024-04-05T06:07:08-0300")
        files.git(root, "commit", "--allow-empty", "-m", "committer date fixture")
        service = files.service(cls=Service)
        head = files.git(root, "rev-parse", "HEAD")
        index = (root / ".git" / "index").read_bytes()
        catalog = service.version_catalog(repo["id"], deadline_seconds=10)["repositories"][0]
        require(catalog["lastCommit"] == {"sha": head, "committedAt": "2024-04-05T09:07:08+00:00"}, catalog)
        require((root / ".git" / "index").read_bytes() == index and files.git(root, "rev-parse", "HEAD") == head,
                "Catalog timestamp reads cannot stage or change history")
        files.git(root, "checkout", "-b", "work")
        files.env["GIT_COMMITTER_DATE"] = "2025-02-03T04:05:06+0800"
        files.git(root, "commit", "--allow-empty", "-m", "work branch date fixture")
        work = files.git(root, "rev-parse", "HEAD")
        work_repo = {**repo, "branch": "work"}
        result = service._local_changes(work_repo, service._repo(work_repo))
        require(result["lastCommit"] == {"sha": work, "committedAt": "2025-02-02T20:05:06+00:00"}, result)
        context = service._repo(work_repo)
        original_text = service._text
        reads = []
        def changed_head(location, *arguments, **kwargs):
            value = original_text(location, *arguments, **kwargs)
            if arguments == ("rev-parse", "HEAD"):
                reads.append(True)
                if len(reads) == 2:
                    return "b" * 40
            return value
        service._text = changed_head
        changed = service._local_changes(work_repo, context)
        require(changed["lastCommit"] is None and changed["diagnostic"]["code"] == "worktree_changed", changed)
        service._text = original_text
        unborn = files.base / "unborn"
        unborn.mkdir()
        files.git(unborn, "init", "--initial-branch=main", "--template=")
        empty_repo = {**repo, "id": "unborn", "path": str(unborn)}
        empty = service._local_changes(empty_repo, (unborn, unborn / ".git", unborn / ".git", {}))
        require(empty["lastCommit"] is None and empty["headSha"] == "", empty)


def test_unknown_commit_metadata_never_uses_current_time():
    service = object.__new__(Service)
    head = "a" * 40
    for raw in ((head + "\0invalid\n").encode(), ("b" * 40 + "\0" + "1700000000\n").encode(),
                (head + "\09999999999999999\n").encode(), b"malformed"):
        service._git = lambda *args, value=raw, **kwargs: value
        require(service._head_commit(Path("fixture"), head) is None, raw)
    require(service._head_commit(Path("fixture"), "unknown") is None)


TESTS = [value for name, value in tuple(globals().items()) if name.startswith("test_") and callable(value)]
if __name__ == "__main__":
    source_sha = module._sha(SOURCE.read_bytes())
    test_sha = module._sha(Path(__file__).read_bytes())
    print("Source SHA256 " + source_sha + "; test SHA256 " + test_sha, flush=True)
    for test in TESTS:
        test()
        print("PASS " + test.__name__, flush=True)
    require(module._sha(SOURCE.read_bytes()) == source_sha and module._sha(Path(__file__).read_bytes()) == test_sha,
            "Source/test changed during checks")
    print(f"{len(TESTS)} isolated progress checks PASS; real repositories untouched", flush=True)
