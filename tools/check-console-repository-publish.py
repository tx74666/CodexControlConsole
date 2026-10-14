"""Serial, offline Git integration checks. No real repository is operated on."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


SOURCE = Path(__file__).resolve().parents[1] / "console_repository_publish.py"
sys.path.insert(0, str(SOURCE.parent))
spec = importlib.util.spec_from_file_location("repository_publish_under_test", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Service, Error = module.RepositoryPublishService, module.RepositoryPublishError


class Fixture:
    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="console-repository-publish-")
        self.base = Path(self.temporary.name).resolve()
        self.empty = self.base / "empty-config"
        self.empty.write_text("")
        self.home = self.base / "home"
        self.home.mkdir()
        self.env = os.environ.copy()
        for key in tuple(self.env):
            if key.startswith("GIT_"):
                self.env.pop(key)
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home), XDG_CONFIG_HOME=str(self.home),
                        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_SYSTEM=str(self.empty), GIT_CONFIG_GLOBAL=str(self.empty),
                        GIT_ALLOW_PROTOCOL="file", GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
        self.repositories = []
        self.old_env = os.environ.copy()
        os.environ.clear()
        os.environ.update(self.env)

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        os.environ.clear()
        os.environ.update(self.old_env)
        self.temporary.cleanup()

    def git(self, root, *arguments, okay=True):
        if not Path(root).resolve().is_relative_to(self.base):
            raise AssertionError("Git fixture escaped temporary directory")
        result = subprocess.run([shutil.which("git"), "-C", str(root), *arguments], capture_output=True, env=self.env, timeout=25)
        if okay and result.returncode:
            raise AssertionError(result.stderr.decode("utf-8", "replace"))
        return result.stdout.decode("utf-8", "replace").strip()

    def repo(self, name="one", branch="main"):
        remote, root = self.base / (name + ".git"), self.base / name
        remote.mkdir()
        root.mkdir()
        self.git(remote, "init", "--bare", "--initial-branch=" + branch)
        self.git(root, "init", "--initial-branch=" + branch, "--template=")
        self.git(root, "config", "user.name", "Offline fixture")
        self.git(root, "config", "user.email", "fixture@invalid.local")
        self.git(root, "config", "core.autocrlf", "false")
        self.git(root, "config", "commit.gpgsign", "false")
        (root / "tracked.txt").write_text("base\n")
        self.git(root, "add", "tracked.txt")
        self.git(root, "commit", "-m", "base")
        self.git(root, "remote", "add", "origin", str(remote))
        self.git(root, "push", "origin", "HEAD:refs/heads/" + branch)
        repo = {"id": name, "path": str(root), "repositoryUrl": str(remote), "remote": "origin", "branch": branch,
                "enabled": True, "syncFiles": [], "versionSources": [], "exclude": []}
        self.repositories.append(repo)
        return root, remote, repo

    def service(self, cls=Service, **kwargs):
        return cls(self.base / "state", test_mode=True, discovery=lambda: {"repositories": self.repositories, "warnings": ["fixture"]}, **kwargs)

    def run(self, service, identifier="request_00000001", ids=None):
        service.run(identifier, ids)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            receipt = service.operation(identifier)
            if receipt["status"] not in {"queued", "working"}:
                if service._worker and service._worker.ident is not None:
                    service._worker.join(timeout=5)
                return receipt
            time.sleep(.02)
        raise AssertionError("Fixture worker did not finish")


def require(value, message="assertion failed"):
    if not value:
        raise AssertionError(message)


def child(receipt, number=0):
    return receipt["repositories"][number]


def hooks(root, name, script):
    path = root / ".git" / "hooks" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text("#!/bin/sh\n" + script + "\n", encoding="utf-8", newline="\n")
    path.chmod(0o755)


def test_basic_binary_delete_and_preview():
    with Fixture() as f:
        root, remote, _ = f.repo()
        original = f.git(root, "rev-parse", "HEAD")
        index = (root / ".git" / "index").read_bytes()
        (root / "scene.blend").write_bytes(b"BLENDER" + bytes(range(255)))
        (root / "tracked.txt").unlink()
        (root / ".gitignore").write_text("ignored.*\n")
        (root / "ignored.bin").write_bytes(b"ignored")
        (root / ".env").write_text("SECRET=fixture")
        service = f.service()
        preview = service.preview()["previews"][0]
        require(preview["status"] == "ready", preview)
        require(f.git(root, "rev-parse", "HEAD") == original)
        require((root / ".git" / "index").read_bytes() == index)
        require(not (root / ".git" / "FETCH_HEAD").exists())
        receipt = f.run(service)
        require(child(receipt)["status"] == "success", receipt)
        require(child(receipt)["uploadSummary"]["count"] == 1, receipt)
        sha = child(receipt)["commitSha"]
        require(f.git(remote, "rev-parse", "main") == sha)
        require(f.git(root, "ls-tree", "--name-only", sha) == ".gitignore\nscene.blend")
        require((root / ".env").exists() and (root / "ignored.bin").exists())
        require(not (root / ".git" / "FETCH_HEAD").exists())
        require(f.git(root, "rev-parse", "origin/main") == original, "private transport doesn't overwrite user tracking refs")
        require(not f.git(root, "diff", "--cached", "--name-only"))


def test_any_staging_and_mixed_batch():
    with Fixture() as f:
        root, _, _ = f.repo("staged")
        other, other_remote, _ = f.repo("clean")
        (root / "tracked.txt").write_text("staged\n")
        f.git(root, "add", "tracked.txt")
        index = (root / ".git" / "index").read_bytes()
        (root / "tracked.txt").write_text("partial second edit\n")
        (other / "new.fbx").write_bytes(b"FBX fixture")
        receipt = f.run(f.service())
        require(child(receipt)["status"] == "deferred" and "暂存" in child(receipt)["message"], receipt)
        require(child(receipt)["diagnostic"]["code"] == "staged_selection" and child(receipt)["diagnostic"]["target"] is None, receipt)
        require((root / ".git" / "index").read_bytes() == index)
        require(child(receipt, 1)["status"] == "success", receipt)
        require(receipt["progress"] == {"total": 2, "completed": 2, "succeeded": 1, "skipped": 0,
                                        "needsAttention": 1, "currentRepoId": "", "currentPhase": ""}, receipt)
        require(child(receipt)["uploadSummary"]["count"] == 0 and child(receipt, 1)["uploadSummary"]["count"] == 1)
        require(f.git(other_remote, "rev-parse", "main") == child(receipt, 1)["commitSha"])


def test_sync_missing_and_preview_no_sync():
    with Fixture() as f:
        root, _, repo = f.repo()
        source = f.base / "saved.py"
        source.write_text("print('saved')\n")
        repo["syncFiles"] = [{"source": str(source), "target": "plugin/main.py"}]
        service = f.service()
        service.preview()
        require(not (root / "plugin" / "main.py").exists())
        result = f.run(service)
        require(child(result)["status"] == "success", result)
        require((root / "plugin" / "main.py").read_bytes() == source.read_bytes())
        source.unlink()
        result = f.run(service, "request_00000002")
        require(child(result)["status"] == "deferred" and "来源缺失" in child(result)["message"], result)
        require(child(result)["diagnostic"]["code"] == "sync_missing", result)


def test_duplicate_and_restart_failed_push():
    class FailPush(Service):
        def _git(self, root, *arguments, **kwargs):
            if arguments and arguments[0] == "push":
                raise module._GitFailure("authentication")
            return super()._git(root, *arguments, **kwargs)
    with Fixture() as f:
        root, remote, _ = f.repo()
        (root / "tracked.txt").write_text("first frozen edit\n")
        service = f.service(FailPush)
        first = f.run(service)
        sha = child(first)["commitSha"]
        require(child(first)["status"] == "push_failed" and sha, first)
        require(child(first)["diagnostic"]["code"] == "git_authentication" and child(first)["diagnostic"]["target"] is None, first)
        require(child(first)["uploadSummary"]["count"] == 0, first)
        require(service.run("request_00000001") == first)
        (root / "tracked.txt").write_text("later edit must remain\n")
        restarted = f.service()
        second = f.run(restarted, "request_00000002")
        require(child(second)["commitSha"] == sha and child(second)["status"] == "success", second)
        require(child(second)["uploadSummary"]["count"] == 1, second)
        require(f.git(root, "rev-parse", "HEAD") == sha and f.git(remote, "rev-parse", "main") == sha)
        require((root / "tracked.txt").read_text() == "later edit must remain\n")
        require(f.git(root, "rev-list", "--count", "HEAD") == "2")


def test_delivered_response_lost_no_resend():
    class Lost(Service):
        pushes = 0
        def _git(self, root, *arguments, **kwargs):
            if arguments and arguments[0] == "push":
                self.pushes += 1
                super()._git(root, *arguments, **kwargs)
                raise module._GitFailure("timeout")
            return super()._git(root, *arguments, **kwargs)
    with Fixture() as f:
        root, _, _ = f.repo()
        (root / "new.txt").write_text("one\n")
        service = f.service(Lost)
        result = f.run(service)
        require(child(result)["status"] == "success" and service.pushes == 1, result)
        require(child(result)["uploadSummary"]["count"] == 1, result)
        f.run(service, "request_00000002")
        require(service.pushes == 1)
        require(service.version_catalog()["repositories"][0]["uploadSummary"]["count"] == 1)


def test_unknown_push_then_verified_original():
    class Unknown(Service):
        did_push = False
        def _git(self, root, *arguments, **kwargs):
            if arguments and arguments[0] == "push":
                super()._git(root, *arguments, **kwargs)
                self.did_push = True
                raise module._GitFailure("timeout")
            if self.did_push and arguments and arguments[0] == "ls-remote":
                raise module._GitFailure("timeout")
            return super()._git(root, *arguments, **kwargs)
    with Fixture() as f:
        root, _, _ = f.repo()
        (root / "new.txt").write_text("one\n")
        first = f.run(f.service(Unknown))
        require(child(first)["status"] == "verification_required", first)
        require(child(first)["diagnostic"]["code"] == "receipt_unverified" and child(first)["diagnostic"]["target"] is None, first)
        require(child(first)["uploadSummary"]["count"] == 0, first)
        sha = child(first)["commitSha"]
        (root / "new.txt").write_text("later\n")
        second = f.run(f.service(), "request_00000002")
        require(child(second)["status"] == "success" and child(second)["commitSha"] == sha, second)
        require(child(second)["uploadSummary"]["count"] == 1, second)
        require(f.git(root, "rev-list", "--count", "HEAD") == "2")


def test_remote_ahead_and_during_fetch():
    with Fixture() as f:
        root, remote, _ = f.repo()
        second = f.base / "second"
        second.mkdir()
        f.git(second, "clone", str(remote), ".")
        f.git(second, "config", "user.name", "fixture")
        f.git(second, "config", "user.email", "fixture@invalid.local")
        (second / "remote.txt").write_text("remote\n")
        f.git(second, "add", "remote.txt")
        f.git(second, "commit", "-m", "remote")
        f.git(second, "push", "origin", "main")
        original = f.git(root, "rev-parse", "HEAD")
        (root / "new.txt").write_text("local\n")
        result = f.run(f.service())
        require(child(result)["status"] == "deferred" and "领先" in child(result)["message"], result)
        require(child(result)["diagnostic"]["code"] == "remote_ahead" and child(result)["diagnostic"]["target"] is None, result)
        require(f.git(root, "rev-parse", "HEAD") == original)
        require(not (root / ".git" / "FETCH_HEAD").exists())
    class Race(Service):
        calls = 0
        def _remote(self, repo, root):
            result = super()._remote(repo, root)
            self.calls += 1
            return "f" * 40 if self.calls == 2 else result
    with Fixture() as f:
        root, _, _ = f.repo()
        (root / "new.txt").write_text("local\n")
        result = f.run(f.service(Race))
        require(child(result)["status"] == "deferred" and "远端" in child(result)["message"], result)
        require(f.git(root, "rev-list", "--count", "HEAD") == "1")


def test_normal_hooks_and_clean_filter():
    with Fixture() as f:
        root, _, _ = f.repo()
        precommit = str(f.base / "precommit-proof.txt").replace("\\", "/")
        prepush = str(f.base / "prepush-proof.txt").replace("\\", "/")
        hooks(root, "pre-commit", "printf called > '" + precommit + "'")
        hooks(root, "pre-push", "printf called > '" + prepush + "'")
        (root / "new.txt").write_text("edit\n")
        service = f.service()
        result = f.run(service)
        require(child(result)["status"] == "success", result)
        require((f.base / "precommit-proof.txt").read_text() == "called")
        require((f.base / "prepush-proof.txt").read_text() == "called")
        require("precommit-proof.txt" not in f.git(root, "ls-tree", "--name-only", "HEAD"))
    with Fixture() as f:
        root, _, _ = f.repo()
        (root / ".gitattributes").write_text("*.filtered filter=fixture\n")
        cleaner = f.base / "cleaner.py"
        cleaner.write_text("import sys\nsys.stdout.buffer.write(sys.stdin.buffer.read().upper())\n")
        f.git(root, "config", "filter.fixture.clean", '"' + sys.executable.replace("\\", "/") + '" "' + str(cleaner).replace("\\", "/") + '"')
        f.git(root, "config", "filter.fixture.required", "true")
        (root / "test.filtered").write_text("lowercase\n")
        result = f.run(f.service())
        require(child(result)["status"] == "success", result)
        require(f.git(root, "show", "HEAD:test.filtered") == "LOWERCASE")
        require((root / "test.filtered").read_text() == "lowercase\n")


def test_hook_changes_file_held_and_rejection():
    with Fixture() as f:
        root, remote, _ = f.repo()
        original = f.git(remote, "rev-parse", "main")
        hooks(root, "pre-commit", "printf hookchanged > tracked.txt")
        (root / "tracked.txt").write_text("previewed\n")
        result = f.run(f.service())
        require(child(result)["status"] == "deferred" and child(result)["commitSha"], result)
        require(f.git(remote, "rev-parse", "main") == original)
        require((root / "tracked.txt").read_text() == "hookchanged")
        require(not (root / ".git" / "index.lock").exists())
        require(not f.git(root, "diff", "--cached", "--name-only"))
    with Fixture() as f:
        root, _, _ = f.repo()
        hooks(root, "pre-commit", "exit 1")
        (root / "tracked.txt").write_text("edit\n")
        result = f.run(f.service())
        require(child(result)["status"] == "deferred", result)
        require(f.git(root, "rev-list", "--count", "HEAD") == "1")
        require(not (root / ".git" / "index.lock").exists())
        require(not f.git(root, "diff", "--cached", "--name-only"))


def test_writer_after_staging_and_busy():
    class Writer(Service):
        def _git(self, root, *arguments, **kwargs):
            result = super()._git(root, *arguments, **kwargs)
            if "add" in arguments:
                (Path(root) / "tracked.txt").write_text("concurrent preserved\n")
            return result
    with Fixture() as f:
        root, _, _ = f.repo()
        (root / "tracked.txt").write_text("first\n")
        result = f.run(f.service(Writer))
        require(child(result)["status"] == "deferred", result)
        require(f.git(root, "rev-list", "--count", "HEAD") == "1")
        require(not (root / ".git" / "index.lock").exists())
        require((root / "tracked.txt").read_text() == "concurrent preserved\n")
    with Fixture() as f:
        root, _, repo = f.repo()
        source = f.base / "saved.txt"
        source.write_text("sync\n")
        repo["syncFiles"] = [{"source": str(source), "target": "saved.txt"}]
        result = f.run(f.service(busy_check=lambda root: "Work 正在修改，请等待"))
        require(child(result)["status"] == "deferred" and not (root / "saved.txt").exists(), result)


def test_duplicate_common_and_disabled():
    with Fixture() as f:
        root, _, repo = f.repo()
        duplicate = dict(repo, id="duplicate")
        f.repositories.append(duplicate)
        (root / "new.txt").write_text("edit\n")
        result = f.run(f.service())
        require(all(i["status"] == "deferred" for i in result["repositories"]), result)
        require(f.git(root, "rev-list", "--count", "HEAD") == "1")
    with Fixture() as f:
        root, _, repo = f.repo()
        repo["enabled"] = False
        result = f.run(f.service(), ids=[repo["id"]])
        require(child(result)["status"] == "deferred" and "启用" in child(result)["message"], result)


def test_pending_config_pin_and_corrupt_receipt():
    class Fail(Service):
        def _git(self, root, *arguments, **kwargs):
            if arguments and arguments[0] == "push":
                raise module._GitFailure("permissions")
            return super()._git(root, *arguments, **kwargs)
    with Fixture() as f:
        root, _, _ = f.repo()
        (root / "new.txt").write_text("edit\n")
        service = f.service(Fail)
        result = f.run(service)
        sha = child(result)["commitSha"]
        settings = service.status()["settings"]
        settings["repositories"][0]["exclude"] = ["new.txt"]
        service.configure(settings)
        result = f.run(f.service(), "request_00000002")
        require(child(result)["status"] == "deferred" and "配置" in child(result)["message"], result)
        require(f.git(root, "rev-parse", "HEAD") == sha)
        path = f.base / "state" / "operations" / "request_00000001.json"
        path.write_text("corrupt")
        try:
            service.run("request_00000001")
        except Error:
            pass
        else:
            raise AssertionError("Corrupt receipt must not reexecute")


def test_versions_scopes_and_nonimport():
    with Fixture() as f:
        root, _, repo = f.repo()
        (root / "a").mkdir()
        (root / "b").mkdir()
        (root / "a" / "__init__.py").write_text("raise RuntimeError('never import')\nbl_info = {'version': (2, 4, 1)}\n")
        (root / "b" / "package.json").write_text('{"version":"7.2.0"}')
        (root / "ProjectSettings").mkdir()
        (root / "ProjectSettings" / "ProjectSettings.asset").write_text("  bundleVersion: 1.8.0\n")
        (root / "app.csproj").write_text("<Project><PropertyGroup><Version>3.2.1</Version></PropertyGroup></Project>")
        repo["versionSources"] = [
            {"path": "a/__init__.py", "kind": "python_ast", "name": "Alpha", "key": "bl_info", "scope": "a"},
            {"path": "b/package.json", "kind": "json", "name": "Beta", "key": "version", "scope": "b/*"},
            {"path": "ProjectSettings/ProjectSettings.asset", "kind": "unity", "name": "Unity", "key": "", "scope": "ProjectSettings"},
            {"path": "app.csproj", "kind": "xml", "name": "CSharp", "key": "", "scope": "app.csproj"}]
        service = f.service()
        preview = service.preview()["previews"][0]
        require([v["version"] for v in preview["versions"]] == ["2.4.1", "7.2.0", "1.8.0", "3.2.1"], preview)
        require(preview["title"].startswith("更新进度"))
        settings = service.status()["settings"]
        settings["naming"]["preset"] = "module_version"
        settings["naming"]["autoBump"] = False  # This fixture isolates naming/scope behavior.
        service.configure(settings)
        require("Alpha 2.4.1" in service.preview()["previews"][0]["title"])
        result = f.run(service)
        require(child(result)["status"] == "success", result)
        (root / "a" / "module.py").write_text("one\n")
        preview = service.preview()["previews"][0]
        require(len(preview["versions"]) == 1 and preview["title"] == "Alpha 2.4.1", preview)


def test_branch_locks_and_no_global_config():
    with Fixture() as f:
        root, _, repo = f.repo(branch="develop")
        repo["branch"] = ""
        service = f.service()
        require(service.status()["settings"]["repositories"][0]["branch"] == "develop")
        (root / "new.txt").write_text("edit\n")
        lock = root / ".git" / "index.lock"
        lock.write_bytes(b"foreign lock")
        result = f.run(service)
        require(child(result)["status"] == "deferred" and lock.read_bytes() == b"foreign lock", result)
        require(f.empty.read_bytes() == b"")
        settings = service.status()["settings"]
        settings["repositories"][0]["branch"] = "main"
        service.configure(settings)
        require(service.preview()["previews"][0]["status"] == "deferred")


def test_real_local_lfs_if_available():
    with Fixture() as f:
        root, remote, _ = f.repo()
        process = subprocess.run([shutil.which("git"), "lfs", "version"], cwd=root, capture_output=True, env=f.env, timeout=60)
        if process.returncode:
            print("SKIP real LFS: executable unavailable (normal filters still tested)")
            return
        f.git(root, "lfs", "install", "--local")
        # Remote-specific endpoint must survive the temporary transport alias.
        f.git(root, "config", "remote.origin.lfsurl", str(remote))
        f.git(root, "config", "remote.origin.lfspushurl", str(remote))
        (root / ".gitattributes").write_text("*.blend filter=lfs diff=lfs merge=lfs -text\n")
        (root / "tiny.blend").write_bytes(b"BLENDER fixture" * 100)
        result = f.run(f.service())
        require(child(result)["status"] == "success", result)
        pointer = f.git(root, "show", "HEAD:tiny.blend")
        require(pointer.startswith("version https://git-lfs.github.com/spec/v1\noid sha256:"), pointer)
        require(any((remote / "lfs" / "objects").rglob("*")), "Local LFS objects not transferred")


def test_transport_pin_against_origin_race():
    with Fixture() as f:
        root, original_remote, _ = f.repo()
        _, redirected, _ = f.repo("redirected")
        original_before = f.git(original_remote, "rev-parse", "main")
        redirect_before = f.git(redirected, "rev-parse", "main")
        f.repositories.pop()
        class Race(Service):
            def _git(self, work, *arguments, **kwargs):
                if arguments and arguments[0] == "push":
                    f.git(root, "config", "remote.origin.url", str(redirected))
                    f.git(root, "config", "remote.origin.pushurl", str(redirected))
                return super()._git(work, *arguments, **kwargs)
        (root / "frozen.txt").write_text("fixed original destination\n")
        result = f.run(f.service(Race))
        sha = child(result)["commitSha"]
        require(child(result)["status"] == "verification_required", result)
        require(sha and sha != original_before and f.git(original_remote, "rev-parse", "main") == sha)
        require(f.git(redirected, "rev-parse", "main") == redirect_before, "redirected transport must remain untouched")
        require(f.git(root, "remote") == "origin", "ephemeral alias must not persist")
        f.git(root, "config", "remote.origin.url", str(original_remote))
        f.git(root, "config", "--unset", "remote.origin.pushurl")
        resumed = f.run(f.service(), "request_00000002")
        require(child(resumed)["status"] == "success" and child(resumed)["commitSha"] == sha, resumed)


def test_busy_real_helper_and_new_id_during_work():
    spec = importlib.util.spec_from_file_location("bindings_under_test", SOURCE.with_name("console_repository_bindings.py"))
    binding_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(binding_module)
    with Fixture() as f:
        root, _, _ = f.repo()
        discovery = binding_module.RepositoryBindingDiscovery(workflow_snapshot=lambda: {}, desktop_activity=lambda root: {"records": [], "warnings": []})
        holder = {}
        def callback(path):
            return discovery.busy_reason(path, owned_developer_lock=holder["service"].owns_developer_lock(path))
        service = f.service(busy_check=callback)
        holder["service"] = service
        (root / "new.txt").write_text("normal\n")
        result = f.run(service)
        require(child(result)["status"] == "success", result)
    with Fixture() as f:
        root, _, _ = f.repo()
        import threading
        entered, release = threading.Event(), threading.Event()
        class Wait(Service):
            def _run_repo(self, *args, **kwargs):
                entered.set()
                require(release.wait(10), "release stalled")
                return super()._run_repo(*args, **kwargs)
        (root / "new.txt").write_text("one\n")
        service = f.service(Wait)
        service.run("request_00000001")
        require(entered.wait(10))
        try:
            service.run("request_00000002")
        except Error as exc:
            require("正在处理" in str(exc))
        else:
            raise AssertionError("Different request must not queue while working")
        require(not (f.base / "state/operations/request_00000002.json").exists())
        require(service.run("request_00000001")["requestId"] == "request_00000001")
        release.set()
        result = f.run(service)
        require(child(result)["status"] == "success", result)
        require(f.git(root, "rev-list", "--count", "HEAD") == "2")


def test_sync_whole_set_and_paused_writer():
    with Fixture() as f:
        root, _, repo = f.repo()
        one, missing = f.base / "source-one.txt", f.base / "missing.txt"
        one.write_text("new saved data\n")
        (root / "copy-one.txt").write_text("old target\n")
        repo["syncFiles"] = [{"source": str(one), "target": "copy-one.txt"}, {"source": str(missing), "target": "copy-two.txt"}]
        result = f.run(f.service())
        require(child(result)["status"] == "deferred", result)
        require((root / "copy-one.txt").read_text() == "old target\n", "preflight must not partially copy predictable failures")
    with Fixture() as f:
        root, _, repo = f.repo()
        source = f.base / "saved.txt"
        source.write_text("saved\n")
        repo["syncFiles"] = [{"source": str(source), "target": "copy.txt"}]
        class Changed(Service):
            def _fetch(self, *args, **kwargs):
                result = super()._fetch(*args, **kwargs)
                source.write_text("new saved version\n")
                return result
        result = f.run(f.service(Changed))
        require(child(result)["status"] == "deferred" and "混合快照" in child(result)["message"], result)
        require(f.git(root, "rev-list", "--count", "HEAD") == "1")
    if os.name == "nt":
        with Fixture() as f:
            root, _, repo = f.repo()
            source = f.base / "paused.txt"
            source.write_text("saved\n")
            repo["syncFiles"] = [{"source": str(source), "target": "copy.txt"}]
            with source.open("r+b"):
                result = f.run(f.service())
            require(child(result)["status"] == "deferred" and "写入句柄" in child(result)["message"], result)
            require(not (root / "copy.txt").exists())


def test_sync_manifest_hold_and_source_change():
    with Fixture() as f:
        root, _, repo = f.repo()
        repo["syncError"] = "saved_sync_manifest_invalid"
        service = f.service()
        require(service.preview()["previews"][0]["status"] == "deferred")
        settings = service.status()["settings"]
        settings["repositories"][0].pop("syncError")
        service.configure(settings)
        require(service.status()["settings"]["repositories"][0]["syncError"])
        result = f.run(service)
        require(child(result)["status"] == "deferred", result)
    with Fixture() as f:
        root, _, repo = f.repo()
        manifest = root / "sync.json"
        manifest.write_text("saved manifest snapshot\n")
        repo["syncManifest"] = {"path": str(manifest), **module._stable(manifest)}
        service = f.service()
        manifest.write_text("later manifest changes\n")
        result = f.run(service)
        require(child(result)["status"] == "deferred" and "同步清单已变化" in child(result)["message"], result)


def test_pre_attempt_restart_and_uncertain_commit_hold():
    class Interrupted(Service):
        def _commit(self, repo, context, snapshot, pending, path):
            marker = b"owned preattempt fixture"
            temporary = self.state_dir / "interrupted-index"
            self._git(context[0], "read-tree", snapshot["head"], index=temporary)
            (context[1] / "index.lock").write_bytes(marker)
            pending.update(state="staging", temporaryIndex=str(temporary), lockMarkerSha=module._sha(marker))
            module._atomic(path, pending)
            raise Error("fixture interrupted before commit dispatch")
    with Fixture() as f:
        root, _, _ = f.repo()
        (root / "new.txt").write_text("saved\n")
        first = f.run(f.service(Interrupted))
        require(child(first)["status"] == "deferred" and (root / ".git/index.lock").exists())
        require(f.git(root, "rev-list", "--count", "HEAD") == "1")
        second = f.run(f.service(), "request_00000002")
        require(child(second)["status"] == "success", second)
        require(f.git(root, "rev-list", "--count", "HEAD") == "2")
        require(any((f.base / "state").glob("precommit-recovery-*.json")))
    class Uncertain(Interrupted):
        def _commit(self, *arguments, **kwargs):
            try:
                super()._commit(*arguments, **kwargs)
            except Error:
                path = arguments[4]
                pending = module._read(path)
                pending["state"] = "commit_attempt"
                module._atomic(path, pending)
                raise
    with Fixture() as f:
        root, _, _ = f.repo()
        (root / "new.txt").write_text("saved\n")
        f.run(f.service(Uncertain))
        result = f.run(f.service(), "request_00000002")
        require(child(result)["status"] == "deferred" and (root / ".git/index.lock").exists(), result)
        require(f.git(root, "rev-list", "--count", "HEAD") == "1")


def test_authoritative_format_and_unity_alias():
    with Fixture() as f:
        root, _, repo = f.repo()
        (root / "app-manifest.json").write_text('{"version":"1.6.41"}')
        (root / "package.json").write_text('{"version":"1.6.41"}')
        repo["versionSources"] = [{"path": p, "kind": "json", "key": "version", "name": p, "scope": "**"} for p in ("app-manifest.json", "package.json")]
        service = f.service()
        preview = service.preview()["previews"][0]
        require(preview["title"] == "1.6.41" and len(preview["versions"]) == 1, preview)
        require("app-manifest.json" in preview["body"] and "1.6.41" in preview["body"])
        (root / "app-manifest.json").write_text('{"version":"v1.6.41"}')
        require(service.preview()["previews"][0]["title"] == "v1.6.41")
        settings = service.status()["settings"]
        (root / "ProjectSettings.asset").write_text("bundleVersion: 7.1.0\n")
        settings["repositories"][0]["versionSources"] = [{"path": "ProjectSettings.asset", "kind": "unity_yaml", "key": "", "name": "Unity", "scope": "**"}]
        service.configure(settings)
        require(service.preview()["previews"][0]["title"] == "7.1.0")


def test_alias_rejecting_hook_is_preserved():
    with Fixture() as f:
        root, remote, _ = f.repo()
        original = f.git(remote, "rev-parse", "main")
        hooks(root, "pre-push", 'test "$1" = origin || exit 1')
        hook_bytes = (root / ".git/hooks/pre-push").read_bytes()
        (root / "new.txt").write_text("one\n")
        result = f.run(f.service())
        require(child(result)["status"] == "push_failed" and child(result)["commitSha"], result)
        require((root / ".git/hooks/pre-push").read_bytes() == hook_bytes)
        require(f.git(remote, "rev-parse", "main") == original)
        require(f.git(root, "rev-list", "--count", "HEAD") == "2")


def test_recovery_cleanup_and_index_rename_crashes():
    class Interrupted(Service):
        def _commit(self, repo, context, snapshot, pending, path):
            marker = b"cleanup interruption owned marker"
            temporary = self.state_dir / "interrupted-index"
            self._git(context[0], "read-tree", snapshot["head"], index=temporary)
            (context[1] / "index.lock").write_bytes(marker)
            pending.update(state="staging", temporaryIndex=str(temporary), lockMarkerSha=module._sha(marker))
            module._atomic(path, pending)
            raise Error("pre-attempt fixture")
    with Fixture() as f:
        root, _, _ = f.repo()
        (root / "new.txt").write_text("one\n")
        f.run(f.service(Interrupted))
        original_atomic = module._atomic
        def stop_after_cleanup(path, value):
            if path.parent.name == "pending" and value.get("state") == "cancelled_before_commit":
                raise OSError("fixture process interruption after owned marker unlink")
            return original_atomic(path, value)
        module._atomic = stop_after_cleanup
        try:
            f.run(f.service(), "request_00000002")
        finally:
            module._atomic = original_atomic
        require(not (root / ".git/index.lock").exists())
        pending = module._read(f.base / "state/pending/one.json")
        require(pending["state"] == "releasing_before_commit")
        third = f.run(f.service(), "request_00000003")
        require(child(third)["status"] == "success", third)
        require(f.git(root, "rev-list", "--count", "HEAD") == "2")
    with Fixture() as f:
        root, remote, _ = f.repo()
        (root / "new.txt").write_text("one\n")
        original_replace = module.os.replace
        def interrupt_index_replace(source, destination):
            original_replace(source, destination)
            if Path(destination) == root / ".git/index":
                raise OSError("fixture interruption after actual index rename")
        module.os.replace = interrupt_index_replace
        try:
            first = f.run(f.service())
        finally:
            module.os.replace = original_replace
        sha = child(first)["commitSha"]
        require(child(first)["status"] == "deferred" and sha, first)
        second = f.run(f.service(), "request_00000002")
        require(child(second)["status"] == "success" and child(second)["commitSha"] == sha, second)
        require(f.git(root, "rev-list", "--count", "HEAD") == "2" and f.git(remote, "rev-parse", "main") == sha)


def test_foreign_index_preserved_after_commit():
    with Fixture() as f:
        root, remote, _ = f.repo()
        (root / "new.txt").write_text("one\n")
        original = f.git(remote, "rev-parse", "main")
        class ForeignIndex(Service):
            foreign = None
            def _reconcile(self, context, pending, path):
                other = self.state_dir / "foreign-index"
                self._git(context[0], "read-tree", pending["parentSha"], index=other)
                self.foreign = other.read_bytes()
                # Model a writer bypassing the standard lock. It isn't undone.
                (context[1] / "index").write_bytes(self.foreign)
                return super()._reconcile(context, pending, path)
        service = f.service(ForeignIndex)
        result = f.run(service)
        require(child(result)["status"] == "deferred" and "暂存" in child(result)["message"], result)
        require((root / ".git/index").read_bytes() == service.foreign)
        require((root / ".git/index.lock").exists())
        require(f.git(remote, "rev-parse", "main") == original)


def test_windows_exit_handle_and_stale_thread_owner():
    if os.name == "nt":
        import ctypes
        from types import SimpleNamespace
        class Function:
            def __init__(self, call):
                self.call = call
            def __call__(self, *args):
                return self.call(*args)
        closed, timed = [], []
        code = {"exit": 0, "success": True}
        def exit_code(handle, pointer):
            pointer._obj.value = code["exit"]
            return int(code["success"])
        def process_times(handle, *pointers):
            timed.append(handle)
            pointers[0]._obj.dwLowDateTime = 17
            return 1
        fake = SimpleNamespace(OpenProcess=Function(lambda *args: 123), CloseHandle=Function(lambda handle: closed.append(handle)),
                               GetExitCodeProcess=Function(exit_code), GetProcessTimes=Function(process_times))
        original = ctypes.WinDLL
        ctypes.WinDLL = lambda *args, **kwargs: fake
        try:
            require(module._process_key(111) is None and not timed)
            code["success"] = False
            require(module._process_key(111) == "unknown" and not timed)
            code.update(success=True, exit=259)
            require(module._process_key(111) == "17" and len(timed) == 1)
            require(len(closed) == 3)
        finally:
            ctypes.WinDLL = original
    class Failed(Service):
        def _git(self, root, *arguments, **kwargs):
            if arguments and arguments[0] == "push":
                raise module._GitFailure("authentication")
            return super()._git(root, *arguments, **kwargs)
    with Fixture() as f:
        root, remote, _ = f.repo()
        (root / "new.txt").write_text("one\n")
        service = f.service(Failed)
        result = f.run(service)
        sha = child(result)["commitSha"]
        result["status"] = "working"
        # Simulate an old owner registry entry with a finished worker, keeping
        # the same live process. Its nonce alone must not claim activity.
        import weakref
        module._LIVE[service._owner] = weakref.ref(service)
        module._atomic(service._ops / "request_00000001.json", result)
        require(not service._worker.is_alive())
        require(service.operation()["status"] == "verification_required" and not service.busy)
        resumed = f.run(f.service(), "request_00000002")
        require(child(resumed)["status"] == "success" and child(resumed)["commitSha"] == sha, resumed)
        require(f.git(root, "rev-list", "--count", "HEAD") == "2" and f.git(remote, "rev-parse", "main") == sha)


def test_worker_start_failure_does_not_stick_busy():
    with Fixture() as f:
        root, _, _ = f.repo()
        (root / "new.txt").write_text("one\n")
        service = f.service()
        original = module.threading.Thread.start
        module.threading.Thread.start = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("fixture cannot start new thread"))
        try:
            failed = f.run(service)
        finally:
            module.threading.Thread.start = original
        require(child(failed)["status"] == "deferred" and failed["phase"] == "dispatch_failed", failed)
        require(not service.busy and f.git(root, "rev-list", "--count", "HEAD") == "1")
        require(service.run("request_00000001") == failed)
        resumed = f.run(service, "request_00000002")
        require(child(resumed)["status"] == "success", resumed)
        require(f.git(root, "rev-list", "--count", "HEAD") == "2")


def retained_delivery(f, *, name="one", branch="main", sha="a" * 40):
    """Synthetic retained receipt, with no subprocess or real remote access."""
    root, remote = f.base / name, f.base / (name + ".git")
    repo = {"id": name, "path": str(root), "repositoryUrl": str(remote), "remote": "origin", "branch": branch,
            "enabled": True, "syncFiles": [], "versionSources": [], "exclude": []}
    f.repositories.append(repo)
    pending = {"state": "delivered", "requestId": "request_00000001", "repoId": name, "commitSha": sha,
               "verifiedRemote": sha, "verifiedAt": module._now(), "title": "original title", "body": "original body",
               "identity": {"root": str(root), "gitdir": str(root / ".git"), "common": str(root / ".git"),
                            "branch": branch, "remote": "origin", "fetchUrl": str(remote), "pushUrl": str(remote),
                            "repository": os.path.normcase(str(remote.resolve()))}}
    return repo, pending


def test_upload_counter_retained_seed_read_only_and_scopes():
    with Fixture() as f:
        repo, pending = retained_delivery(f)
        service = f.service()
        path = service._pending_path(repo["id"])
        module._atomic(path, pending)
        original = path.read_bytes()
        summary = service.status()["uploadSummaries"][0]
        require(summary["state"] == "recorded" and summary["count"] == 1, summary)
        require(summary["binding"] == service._upload_binding(repo) and not service._uploads.exists())
        require(path.read_bytes() == original, "GET migration must be read-only")
        item = {"message": "confirmed"}
        require(service._record_delivery(repo, pending, path, item))
        require(item["uploadSummary"]["count"] == 1 and service._uploads.exists())
        pending["requestId"] = "request_00000002"
        require(f.service()._record_delivery(repo, pending, path, item))
        require(item["uploadSummary"]["count"] == 1, "same destination and commit must be idempotent")
        pending.update(commitSha="b" * 40, verifiedRemote="b" * 40)
        require(service._record_delivery(repo, pending, path, item))
        require(item["uploadSummary"]["count"] == 2)
        renamed = dict(repo, id="new-name", path=str(f.base / "another-checkout"), remote="upstream")
        require(service._upload_summary(renamed)["count"] == 2, "display binding does not reset destination ledger")
        require(service._upload_summary(dict(renamed, branch="feature"))["count"] == 0, "branches must remain independent")
        require(service._upload_summary(dict(repo, repositoryUrl=str(f.base / "different.git")))["count"] == 0)


def test_upload_counter_unbound_old_history_stays_unknown():
    with Fixture() as f:
        repo, pending = retained_delivery(f)
        service = f.service()
        module._atomic(service._ops / "request_00000001.json", {"status": "success", "repositories": [
            {"repoId": repo["id"], "status": "success", "commitSha": pending["commitSha"]}]})
        summary = service._upload_summary(repo)
        require(summary["state"] == "unknown" and summary["count"] is None, summary)
        incomplete = dict(pending)
        incomplete.pop("verifiedRemote")
        module._atomic(service._pending_path(repo["id"]), incomplete)
        require(service._upload_summary(repo)["count"] is None, "incomplete delivery cannot seed a number")
        require(service._record_delivery(repo, pending, service._pending_path(repo["id"]), {"message": "confirmed"}))
        summary = service._upload_summary(repo)
        require(summary["count"] == 1 and summary["source"] == "console_confirmed_deliveries", summary)


def test_upload_counter_corrupt_scope_does_not_reset_or_affect_other():
    with Fixture() as f:
        one, first = retained_delivery(f, name="one")
        two, second = retained_delivery(f, name="two")
        service = f.service()
        for repo, pending in ((one, first), (two, second)):
            require(service._record_delivery(repo, pending, service._pending_path(repo["id"]), {"message": "confirmed"}))
        ledger, _ = service._upload_ledger(service._upload_destination(one))
        ledger.write_bytes(b'{"corrupt":true}')
        preserved = ledger.read_bytes()
        require(service._upload_summary(one)["state"] == "unknown" and service._upload_summary(one)["count"] is None)
        require(not service._record_delivery(one, first, service._pending_path(one["id"]), {"message": "confirmed"}))
        require(ledger.read_bytes() == preserved and module._read(service._pending_path(one["id"]))["state"] == "delivered")
        second.update(commitSha="c" * 40, verifiedRemote="c" * 40)
        require(service._record_delivery(two, second, service._pending_path(two["id"]), {"message": "confirmed"}))
        require(service._upload_summary(two)["count"] == 2, "one corrupted ledger must not stop other counters")


def test_upload_counter_crash_after_ledger_is_idempotent():
    with Fixture() as f:
        repo, pending = retained_delivery(f)
        service = f.service()
        path = service._pending_path(repo["id"])
        module._atomic(path, pending)
        original_atomic = module._atomic
        def crash(path_to_write, value):
            if path_to_write == path:
                raise KeyboardInterrupt("fixture crash after durable ledger")
            return original_atomic(path_to_write, value)
        module._atomic = crash
        try:
            try:
                service._record_delivery(repo, pending, path, {"message": "confirmed"})
                raise AssertionError("crash fixture did not interrupt")
            except KeyboardInterrupt:
                pass
        finally:
            module._atomic = original_atomic
        restarted = f.service()
        stored = module._read(path)
        require(restarted._upload_summary(repo)["count"] == 1)
        require(restarted._record_delivery(repo, stored, path, {"message": "recovered"}))
        require(restarted._upload_summary(repo)["count"] == 1)


def test_upload_counter_cas_lock_failure_retains_confirmation():
    with Fixture() as f:
        repo, pending = retained_delivery(f)
        service = f.service()
        path = service._pending_path(repo["id"])
        module._atomic(path, pending)
        ledger = service._uploads / (module._json_sha(service._upload_destination(repo)) + ".json")
        with module._file_lock(ledger.with_suffix(".lock")):
            item = {"message": "confirmed"}
            require(not service._record_delivery(repo, pending, path, item))
            require(item["uploadSummary"]["state"] == "pending" and item["uploadSummary"]["count"] is None)
            require(module._read(path)["state"] == "delivered" and not ledger.exists())
        require(service._record_delivery(repo, module._read(path), path, {"message": "confirmed"}))
        require(service._upload_summary(repo)["count"] == 1)


def test_upload_counter_save_failure_retry_preserves_later_work():
    class Observed(Service):
        pushes = 0
        def _git(self, root, *arguments, **kwargs):
            if arguments and arguments[0] == "push":
                self.pushes += 1
            return super()._git(root, *arguments, **kwargs)
    with Fixture() as f:
        root, remote, _ = f.repo()
        (root / "new.txt").write_text("original saved change\n")
        service = f.service(Observed)
        original_atomic = module._atomic
        def failed_counter(path, value):
            if path.parent == service._uploads and path.suffix == ".json":
                raise PermissionError("fixture counter cannot save")
            return original_atomic(path, value)
        module._atomic = failed_counter
        try:
            first = f.run(service)
        finally:
            module._atomic = original_atomic
        sha = child(first)["commitSha"]
        require(child(first)["status"] == "success" and child(first)["uploadSummary"]["state"] == "pending", first)
        require(f.git(remote, "rev-parse", "main") == sha and service.pushes == 1)
        require(service.status()["uploadSummaries"][0]["state"] == "pending")
        require(service.run("request_00000001") == first, "duplicate click must not count or upload again")
        (root / "new.txt").write_text("later edit must stay separate\n")
        second = f.run(service, "request_00000002")
        require(child(second)["status"] == "success" and child(second)["uploadSummary"]["count"] == 1, second)
        require(child(second)["commitSha"] == sha and service.pushes == 1)
        require(f.git(root, "rev-list", "--count", "HEAD") == "2")
        require((root / "new.txt").read_text() == "later edit must stay separate\n")
        third = f.run(service, "request_00000003")
        require(child(third)["uploadSummary"]["count"] == 2 and service.pushes == 2, third)
        require(f.git(root, "rev-list", "--count", "HEAD") == "3")


def test_upload_counter_lfs_failure_does_not_advance():
    class FailedLfs(Service):
        def _git(self, root, *arguments, **kwargs):
            if arguments and arguments[0] == "push":
                raise module._GitFailure("lfs")
            return super()._git(root, *arguments, **kwargs)
    with Fixture() as f:
        root, remote, _ = f.repo()
        original = f.git(remote, "rev-parse", "main")
        (root / "asset.blend").write_bytes(b"saved LFS fixture asset")
        failed = f.run(f.service(FailedLfs))
        require(child(failed)["status"] == "push_failed" and child(failed)["uploadSummary"]["count"] == 0, failed)
        require(child(failed)["diagnostic"]["code"] == "git_lfs" and child(failed)["diagnostic"]["target"] is None, failed)
        require(f.git(remote, "rev-parse", "main") == original)
        resumed = f.run(f.service(), "request_00000002")
        require(child(resumed)["commitSha"] == child(failed)["commitSha"] and child(resumed)["uploadSummary"]["count"] == 1, resumed)


def test_upload_counter_missing_and_truncated_ledger_preserved():
    with Fixture() as f:
        repo, pending = retained_delivery(f)
        service = f.service()
        path = service._pending_path(repo["id"])
        require(service._record_delivery(repo, pending, path, {"message": "confirmed"}))
        pending.update(commitSha="b" * 40, verifiedRemote="b" * 40)
        require(service._record_delivery(repo, pending, path, {"message": "confirmed"}))
        ledger, value = service._upload_ledger(service._upload_destination(repo))
        complete = ledger.read_bytes()
        ledger.unlink()
        require(service._upload_summary(repo)["state"] == "unknown" and service._upload_summary(repo)["count"] is None)
        require(not service._record_delivery(repo, pending, path, {"message": "confirmed"}))
        require(not ledger.exists(), "missing established ledger must not silently restart at one")
        truncated = dict(value, events=value["events"][:1])
        module._atomic(ledger, truncated)
        original = ledger.read_bytes()
        require(service._upload_summary(repo)["count"] is None)
        require(not service._record_delivery(repo, module._read(path), path, {"message": "confirmed"}))
        require(ledger.read_bytes() == original, "truncated ledger must stay preserved")
        ledger.write_bytes(complete)
        require(service._record_delivery(repo, module._read(path), path, {"message": "confirmed"}))
        require(service._upload_summary(repo)["count"] == 2)
        # A new delivery also freezes whether an older ledger existed. Even
        # one prior entry cannot be replaced by the new commit as upload #1.
        next_pending = dict(pending, commitSha="c" * 40, verifiedRemote="c" * 40)
        next_pending.pop("uploadSummary", None)
        next_pending["uploadCounterBase"] = {"destination": service._upload_destination(repo), "count": 2, "ledgerExisted": True}
        ledger.unlink()
        require(not service._record_delivery(repo, next_pending, path, {"message": "confirmed"}) and not ledger.exists())


def test_upload_counter_malformed_binding_isolated():
    with Fixture() as f:
        one, first = retained_delivery(f, name="one")
        two, second = retained_delivery(f, name="two")
        service = f.service()
        for repo, pending in ((one, first), (two, second)):
            require(service._record_delivery(repo, pending, service._pending_path(repo["id"]), {"message": "confirmed"}))
        path = service._pending_path(one["id"])
        original = module._read(path)
        for binding in (None, [], {}, "invalid"):
            malformed = dict(original, uploadSummary=dict(original["uploadSummary"], binding=binding))
            module._atomic(path, malformed)
            preserved = path.read_bytes()
            summaries = service.status()["uploadSummaries"]
            require(summaries[0]["state"] == "unknown" and summaries[0]["count"] is None)
            require(summaries[1]["state"] == "recorded" and summaries[1]["count"] == 1)
            versions = service.version_catalog()["repositories"]
            require(versions[0]["uploadSummary"]["state"] == "unknown" and versions[1]["uploadSummary"]["count"] == 1)
            require(path.read_bytes() == preserved, "bad bindings must not be rewritten by GET")
        malformed = dict(original, identity=[])
        module._atomic(path, malformed)
        require(service.status()["uploadSummaries"][0]["state"] == "unknown")
        require(service.status()["uploadSummaries"][1]["count"] == 1)


def test_upload_counter_same_length_wrong_anchor_preserved():
    with Fixture() as f:
        repo, pending = retained_delivery(f)
        service = f.service()
        path = service._pending_path(repo["id"])
        require(service._record_delivery(repo, pending, path, {"message": "confirmed"}))
        pending.update(commitSha="b" * 40, verifiedRemote="b" * 40)
        require(service._record_delivery(repo, pending, path, {"message": "confirmed"}))
        ledger, value = service._upload_ledger(service._upload_destination(repo))
        complete = ledger.read_bytes()
        value["events"][-1].update(commitSha="c" * 40, verifiedRemote="c" * 40)
        module._atomic(ledger, value)
        preserved = ledger.read_bytes()
        require(service._upload_summary(repo)["state"] == "unknown" and service._upload_summary(repo)["count"] is None)
        require(not service._record_delivery(repo, pending, path, {"message": "confirmed"}))
        require(ledger.read_bytes() == preserved, "same-length wrong ledger must not append original confirmation again")
        require(module._read(path)["uploadCounterBase"]["commitSha"] == "b" * 40)
        ledger.write_bytes(complete)
        require(service._record_delivery(repo, module._read(path), path, {"message": "confirmed"}))
        require(service._upload_summary(repo)["count"] == 2)


def test_upload_counter_operation_ack_crash_keeps_later_edits():
    with Fixture() as f:
        root, remote, _ = f.repo()
        (root / "new.txt").write_text("original edit\n")
        service = f.service()
        first = f.run(service)
        sha = child(first)["commitSha"]
        # Model the precise crash boundary after delivered journal + ledger,
        # before the operation's successful row was durably acknowledged.
        interrupted = module._read(service._ops / "request_00000001.json")
        interrupted.update(status="working", owner={"pid": 0, "processKey": "", "nonce": "stale"})
        interrupted["repositories"][0].update(status="working", phase="push", message="waiting for receipt")
        module._atomic(service._ops / "request_00000001.json", interrupted)
        (root / "new.txt").write_text("later edit\n")
        second = f.run(f.service(), "request_00000002")
        require(child(second)["status"] == "success" and child(second)["commitSha"] == sha, second)
        require(child(second)["uploadSummary"]["count"] == 1)
        require(f.git(root, "rev-list", "--count", "HEAD") == "2" and f.git(remote, "rev-parse", "main") == sha)
        require((root / "new.txt").read_text() == "later edit\n")
        third = f.run(f.service(), "request_00000003")
        require(child(third)["uploadSummary"]["count"] == 2 and child(third)["commitSha"] != sha, third)
        require(f.git(root, "rev-list", "--count", "HEAD") == "3")


def test_upload_counter_deleted_ledger_retry_preserves_later_work():
    class Observed(Service):
        pushes = 0
        def _git(self, root, *arguments, **kwargs):
            if arguments and arguments[0] == "push":
                self.pushes += 1
            return super()._git(root, *arguments, **kwargs)
    with Fixture() as f:
        root, remote, repo = f.repo()
        service = f.service(Observed)
        for number in (1, 2):
            (root / "new.txt").write_text(str(number) + "\n")
            uploaded = f.run(service, "request_0000000" + str(number))
            require(child(uploaded)["uploadSummary"]["count"] == number)
        sha = child(uploaded)["commitSha"]
        ledger, _ = service._upload_ledger(service._upload_destination(repo))
        complete = ledger.read_bytes()
        ledger.unlink()
        (root / "new.txt").write_text("later edit must remain\n")
        third = f.run(service, "request_00000003")
        require(child(third)["status"] == "success" and child(third)["commitSha"] == sha, third)
        require(child(third)["uploadSummary"]["state"] == "pending" and child(third)["uploadSummary"]["count"] is None)
        require(service.pushes == 2 and f.git(root, "rev-list", "--count", "HEAD") == "3" and not ledger.exists())
        require(f.git(remote, "rev-parse", "main") == sha)
        ledger.write_bytes(complete)
        fourth = f.run(service, "request_00000004")
        require(child(fourth)["status"] == "success" and child(fourth)["uploadSummary"]["count"] == 2, fourth)
        require(service.pushes == 2 and child(fourth)["commitSha"] == sha)
        require((root / "new.txt").read_text() == "later edit must remain\n" and f.git(root, "rev-list", "--count", "HEAD") == "3")


def test_diagnostic_known_targets_and_unknown_safety():
    cases = [("repo_missing", "connection", "error", {"section":"connection", "field":"path"}),
             ("branch_mismatch", "connection", "warning", {"section":"connection", "field":"branch"}),
             ("remote_config", "connection", "warning", {"section":"connection", "field":"remote"}),
             ("remote_ownership", "connection", "error", {"section":"connection", "field":"repositoryUrl"}),
             ("sync_missing", "sync", "warning", {"section":"sync", "field":"sync"}),
             ("staged_selection", "repository", "warning", None),
             ("remote_ahead", "remote", "warning", None),
             ("receipt_unverified", "verification", "warning", None)]
    for code, category, severity, target in cases:
        error = Error("actual safe guard", code=code)
        value = Service._diagnostic(error)
        require(value["code"] == code and value["category"] == category and value["severity"] == severity, value)
        require(value["target"] == target and value["summary"] == str(error) and bool(value["nextStep"]), value)
    # Text is not evidence for auth/LFS/remote ownership, even if it names them.
    error = Error("authentication / LFS / wrong remote: still an untyped safe error")
    value = Service._diagnostic(error)
    require(value["code"] == "manual_check" and value["category"] == "unknown" and value["target"] is None)
    require(value["summary"] == str(error))
    require(module._make_diagnostic("new_unrecognized_code", "safe", source_id="made_up")["target"] is None)
    require(module._make_diagnostic("version_authority", "missing authority")["target"] is None)
    authority = module._make_diagnostic("version_authority", "missing authority", source_id="actual_source")
    require(authority["target"] == {"section":"versions", "field":"versionPath", "sourceId":"actual_source"})


def test_diagnostic_git_categories_do_not_expose_details():
    expected = {"authentication":("git_authentication", "authentication"), "permissions":("git_permissions", "permissions"),
                "rules":("git_rules", "rules"), "lfs":("git_lfs", "lfs"), "timeout":("git_timeout", "network"),
                "remote_changed":("remote_changed", "remote"), "missing_git":("git_missing", "repository")}
    private_detail = "https://credential@private.invalid/repo authentication lfs"
    for code, (expected_code, category) in expected.items():
        value = Service._diagnostic(module._GitFailure(code, detail=private_detail))
        require(value["code"] == expected_code and value["category"] == category and value["target"] is None, value)
        require("credential" not in json.dumps(value) and "private.invalid" not in json.dumps(value), value)
    value = Service._diagnostic(module._GitFailure("git_failed", detail=private_detail))
    require(value["code"] == "manual_check" and value["target"] is None and value["category"] == "unknown", value)
    require("credential" not in json.dumps(value))
    require(Service._diagnostic(OSError("private filesystem path"))["target"] is None)


def test_diagnostic_git_receipts_ignore_keyword_paths():
    # Exercise the actual _git boundary with fake subprocess output. No process,
    # network, Git repository, API, user data or service is touched.
    cases = [
        ("fatal: repository 'https://github.com/owner/lfs-publickey-403-authentication' not found", "git_failed"),
        ("fatal: cannot open D:/lfs/publickey/403/repository rule: unknown failure", "git_failed"),
        ("Uploading LFS objects: 100% (1/1)\nfatal: repository not found", "git_failed"),
        ("fatal: Authentication failed for 'https://github.com/owner/repo'", "authentication"),
        ("git@github.com: Permission denied (publickey).", "authentication"),
        ("fatal: could not read Username for 'https://github.com': terminal prompts disabled", "authentication"),
        ("fatal: unable to access 'https://github.com/owner/repo/': The requested URL returned error: 401", "authentication"),
        ("fatal: unable to access 'https://github.com/owner/repo/': The requested URL returned error: 403", "permissions"),
        ("error: No such remote 'origin'", "remote_config"),
        ("remote: Write access to repository not granted.", "permissions"),
        ("Git LFS upload failed: missing local object", "lfs"),
        ("error: external filter 'git-lfs filter-process' failed", "lfs"),
        ("remote: error: GH008: Your push referenced unknown Git LFS objects", "lfs"),
        ("remote: error: GH013: Repository rule violations found for refs/heads/main.", "rules"),
        (" ! [remote rejected] main -> main (pre-receive hook declined)", "rules"),
        (" ! [rejected] main -> main (fetch first)", "remote_changed"),
        ("hint: unrelated text mentions non-fast-forward / publickey / lfs / 403", "git_failed"),
        ("fatal: unable to access 'https://github.com/owner/401/': The requested URL returned error: 404", "git_failed"),
        ("fatal: cannot open 'D:/401/error: No such remote origin': unknown failure", "git_failed"),
        ("hint: error: No such remote 'origin'", "git_failed"),
        ("Uploading error: No such remote 'origin'", "git_failed"),
    ]
    actual_which, actual_run = module.shutil.which, module.subprocess.run
    service = object.__new__(Service)
    service._test_mode = False
    calls = []
    try:
        module.shutil.which = lambda name: "fixture-git"
        for stderr, expected in cases:
            def fake_run(arguments, **kwargs):
                calls.append(arguments)
                require(arguments[:3] == ["fixture-git", "-C", "fixture"] and arguments[3] == "status")
                return type("Receipt", (), {"returncode":1, "stderr":stderr.encode(), "stdout":b""})()
            module.subprocess.run = fake_run
            try:
                service._git(Path("fixture"), "status")
                require(False, "Nonzero Git receipt must remain a failure")
            except module._GitFailure as exc:
                require(exc.code == expected and exc.returncode == 1, (stderr, exc.code, expected))
                value = Service._diagnostic(exc)
                expected_target = {"section":"connection", "field":"remote"} if expected == "remote_config" else None
                require(value["target"] == expected_target and stderr not in json.dumps(value), value)
                if expected == "remote_config":
                    require(value["code"] == "remote_config" and value["category"] == "connection", value)
                    require("不存在" in value["summary"] and "origin" not in json.dumps(value), value)
                if expected == "git_failed":
                    require(value["category"] == "unknown" and value["code"] == "manual_check", value)
        require(len(calls) == len(cases))
    finally:
        module.shutil.which, module.subprocess.run = actual_which, actual_run


def test_diagnostic_activity_is_an_unconfirmed_boundary():
    service = object.__new__(Service)
    service._busy_check = lambda root: "Desktop Codex lifecycle boundary is unverified; publication deferred."
    try:
        service._busy_reason(Path("fixture"))
        require(False, "Unverified activity must still defer")
    except Error as exc:
        value = Service._diagnostic(exc)
        require(value["code"] == "activity_unconfirmed" and value["target"] is None, value)
        require(value["summary"] == str(exc) and "确认或完成" in value["nextStep"] and "Codex" in value["nextStep"], value)
        require(not any(word in value["nextStep"] for word in ("关闭", "强制", "绕过", "移除锁")), value)


class DiagnosticReadFixture(Service):
    # Pure read contract fixture: any unexpected Git/write/busy call is a failure.
    def __init__(self, *, error=None, sources=None, components=None, sync_state="changed"):
        self.allowed = True
        self.error = error
        self.sources = sources or []
        self.components = components or []
        self.sync_state = sync_state
        self.repo = {"id":"fixture", "path":"fixture", "enabled":True, "versionPlans":[], "syncFiles":[]}

    def _settings(self):
        return {"repositories":[self.repo], "naming":dict(module._DEFAULT_NAMING)}

    def _upload_summary(self, repo):
        return {"state":"recorded", "count":0}

    def _repo(self, repo):
        if self.error:
            raise self.error
        return Path("fixture"), Path("fixture/git"), Path("fixture/common"), {}

    def _sync_contract(self, repo):
        if self.error:
            raise self.error

    def _version_sources(self, repo, root):
        return self.sources

    def _version_details(self, repo, context):
        return [dict(component) for component in self.components]

    def _local_changes(self, repo, context):
        return {"hasChanges":True, "changeState":"changed", "worktreeChanged":True, "outgoingCommits":0,
                "changedFiles":[], "headSha":"fixture_head", "syncState":self.sync_state, "syncChanged":True,
                "changesReason":"Normal informational difference; mentions authentication without any failed receipt.",
                "syncReason":"Saved source differs; will synchronize before determining version."}

    def _planned_versions(self, *args, **kwargs):
        return [], [], []

    def _git(self, *args, **kwargs):
        raise AssertionError("Diagnostic read fixture must not invoke Git")

    def _save(self, *args):
        raise AssertionError("Diagnostic read fixture must not write")


def test_diagnostic_catalog_and_preview_guard_contract():
    missing = DiagnosticReadFixture(error=Error("仓库目录不存在，请检查设置。", code="repo_missing"))
    catalog = missing.version_catalog("fixture")["repositories"][0]
    preview = missing.preview("fixture")["previews"][0]
    require(catalog["diagnostic"]["code"] == "repo_missing" and catalog["message"] == str(missing.error), catalog)
    require(preview["status"] == "deferred" and preview["diagnostic"]["target"] == {"section":"connection", "field":"path"}, preview)
    sync = DiagnosticReadFixture(error=Error("同步来源缺失，请先保存来源文件；本仓库延期。", code="sync_missing"))
    require(sync.preview()["previews"][0]["diagnostic"]["category"] == "sync")
    unknown = DiagnosticReadFixture(error=module._GitFailure("git_failed", detail="authentication"))
    require(unknown.version_catalog()["repositories"][0]["diagnostic"]["code"] == "manual_check")


def test_diagnostic_normal_reasons_and_fallback_are_not_failures():
    fallback = DiagnosticReadFixture().version_catalog()["repositories"][0]
    require(fallback["diagnostic"]["code"] == "version_fallback" and fallback["diagnostic"]["severity"] == "info", fallback)
    require(fallback["changeState"] == "changed" and fallback["syncState"] == "changed", fallback)
    component = {"sourceId":"actual", "currentVersion":"1.2.3", "planState":"none", "versionChanged":False,
                 "repositoryHeadSha":"fixture_head"}
    normal = DiagnosticReadFixture(sources=[{"path":"manifest.json"}], components=[component]).version_catalog()["repositories"][0]
    require(normal["diagnostic"] is None, "Nonempty normal reasons must not become an error: " + str(normal))
    failure = {**component, "diagnostic":module._make_diagnostic("version_authority", "Cannot uniquely read actual authority", source_id="actual")}
    identified = DiagnosticReadFixture(sources=[{"path":"manifest.json"}], components=[failure]).version_catalog()["repositories"][0]
    require(identified["diagnostic"]["target"]["sourceId"] == "actual" and identified["diagnostic"]["severity"] == "warning", identified)
    item = {"diagnostic":module._make_diagnostic("repo_missing", "missing root"), "components":[failure]}
    Service._catalog_diagnostic(item)
    require(item["diagnostic"]["code"] == "repo_missing", "Original repository failure has priority")


TESTS = [v for k, v in tuple(globals().items()) if k.startswith("test_") and callable(v)]
if __name__ == "__main__":
    source_sha = module._sha(SOURCE.read_bytes())
    test_sha = module._sha(Path(__file__).read_bytes())
    print("Source SHA256 " + source_sha + "; test SHA256 " + test_sha)
    selected = [test for test in TESTS if not sys.argv[1:] or test.__name__ in sys.argv[1:]]
    require(len(selected) == len(sys.argv[1:]) if sys.argv[1:] else True, "Unknown test name")
    for test in selected:
        test()
        print("PASS " + test.__name__)
    require(module._sha(SOURCE.read_bytes()) == source_sha and module._sha(Path(__file__).read_bytes()) == test_sha,
            "Source or tests changed during this run; results do not certify the final files")
    print(f"{len(selected)} isolated serial Git checks PASS; real repositories untouched")
