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
        require((root / ".git" / "index").read_bytes() == index)
        require(child(receipt, 1)["status"] == "success", receipt)
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
        require(service.run("request_00000001") == first)
        (root / "tracked.txt").write_text("later edit must remain\n")
        restarted = f.service()
        second = f.run(restarted, "request_00000002")
        require(child(second)["commitSha"] == sha and child(second)["status"] == "success", second)
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
        f.run(service, "request_00000002")
        require(service.pushes == 1)


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
        sha = child(first)["commitSha"]
        (root / "new.txt").write_text("later\n")
        second = f.run(f.service(), "request_00000002")
        require(child(second)["status"] == "success" and child(second)["commitSha"] == sha, second)
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
