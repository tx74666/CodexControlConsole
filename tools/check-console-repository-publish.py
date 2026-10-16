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

    def run(self, service, identifier="request_00000001", ids=None, *, intent=None):
        service.run(identifier, ids, **({"intent": intent} if intent is not None else {}))
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


def test_long_push_deadline_preserves_short_metadata_bounds():
    class SlowTransfer(Service):
        def _git(self, root, *arguments, **kwargs):
            operation = module._git_operation(arguments)
            self.observed.append((operation, kwargs.get("timeout", 35)))
            return super()._git(root, *arguments, **kwargs)

        def _stream_git(self, command, env, data, timeout, progress):
            if command[3] == "push":
                # Model an ordinary/LFS transfer taking longer than the old
                # 100-second cap, without sleeping or transferring large files.
                if timeout < 125:
                    raise subprocess.TimeoutExpired(command, timeout)
                require(callable(progress), "Long push must retain measured Git/LFS progress")
                require("--progress" in command and "--no-follow-tags" in command)
                require(not any(flag.startswith("--force") or flag == "--no-verify" for flag in command),
                        "A longer deadline must not bypass hooks or remote history")
            return super()._stream_git(command, env, data, timeout, progress)

    with Fixture() as f:
        root, remote, _ = f.repo()
        (root / "tracked.txt").write_text("saved long-transfer fixture\n")
        service = f.service(SlowTransfer)
        service.observed = []
        result = f.run(service)
        require(child(result)["status"] == "success", result)
        require(f.git(remote, "rev-parse", "main") == child(result)["commitSha"], result)
        pushes = [timeout for operation, timeout in service.observed if operation == "push"]
        require(pushes == [1800], service.observed)
        for operation, expected in (("ls-remote", 35), ("fetch", 65), ("add", 90), ("commit", 90)):
            actual = [timeout for name, timeout in service.observed if name == operation]
            require(actual and all(timeout == expected for timeout in actual), (operation, actual))
        require(all(0 < timeout <= 90 for operation, timeout in service.observed if operation != "push"),
                "Metadata and preparation deadlines must remain bounded")


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
        require([v["version"] for v in preview["versions"] if not v.get("repositoryVersion")] == ["2.4.1", "7.2.0", "1.8.0", "3.2.1"], preview)
        require(preview["title"] == "1.0.0" and preview["repositoryVersion"]["state"] == "initial", preview)
        settings = service.status()["settings"]
        settings["naming"]["preset"] = "module_version"
        settings["naming"]["autoBump"] = False  # This fixture isolates naming/scope behavior.
        service.configure(settings)
        require(service.preview()["previews"][0]["title"] == "1.0.0")
        result = f.run(service)
        require(child(result)["status"] == "success", result)
        (root / "a" / "module.py").write_text("one\n")
        preview = service.preview()["previews"][0]
        require(len(preview["versions"]) == 2 and preview["title"] == "1.0.0", preview)
        require(any(item["name"] == "Alpha" and item["version"] == "2.4.1" for item in preview["versions"]), preview)


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


def synthetic_delivery_service(f, *, already_remote=True):
    """Exercise real delivery journals/ledgers/acks without launching Git."""
    repo, pending = retained_delivery(f)
    service = f.service()
    path = service._pending_path(repo["id"])
    identity = pending["identity"]
    context = tuple(Path(identity[key]) for key in ("root", "gitdir", "common")) + (identity,)
    pending.update(state="committed", snapshot={"head": pending["commitSha"]},
                   repositorySettingsSha=module._repo_settings_sha(repo), transportOptionsSha="fixture-transport")
    module._atomic(path, pending)
    request_id = "request_recovered_0002"
    item = {"repoId": repo["id"], "status": "working", "phase": "verify", "message": "", "logs": [],
            "commitSha": pending["commitSha"], "title": pending["title"], "body": pending["body"]}
    receipt = {"requestId": request_id, "status": "working", "repositories": [item]}
    module._atomic(service._ops / (pending["requestId"] + ".json"),
                   {"requestId": pending["requestId"], "status": "attention", "repositories": [dict(item, status="push_failed")]})
    remotes = iter([pending["commitSha"]] if already_remote else ["b" * 40, pending["commitSha"]])
    launches = []
    service._blockers = lambda *args: None
    service._snapshot = lambda *args: {}
    service._repo = lambda *args: context
    service._remote = lambda *args: next(remotes)
    service._fetch = lambda *args: None
    service._ancestor = lambda root, first, second: first == second or first == "b" * 40
    service._outgoing_safe = lambda *args: None
    service._busy_reason = lambda *args: None
    service._text = lambda *args, **kwargs: pending["commitSha"]
    service._transport = lambda *args: ("fixture-alias", [])
    service._transport_identity = lambda *args: {"optionsSha": "fixture-transport"}
    service._git = lambda *args, **kwargs: launches.append(args[1:]) or b""
    return service, repo, context, pending, path, receipt, item, launches


def test_resumed_delivery_ack_tracks_successful_request_without_git():
    for already_remote in (True, False):
        with Fixture() as f:
            service, repo, context, pending, path, receipt, item, launches = synthetic_delivery_service(f, already_remote=already_remote)
            service._push(repo, context, pending, path, receipt, item)
            require(item["status"] == "success" and pending["uploadCounterPending"] is False)
            require(pending["requestId"] == "request_00000001" and pending["deliveryRecoveryRequestId"] == receipt["requestId"])
            require(module._read(path)["deliveryRecoveryRequestId"] == receipt["requestId"])
            require(not service._delivery_acknowledged(pending), "Journal alone cannot fabricate a durable successful row")
            service._save(receipt)
            require(service._delivery_acknowledged(pending), "The new successful verification must acknowledge the original commit")
            require(len(launches) == (0 if already_remote else 1))


def test_commit_and_push_continuation_preserves_old_ack_on_new_failure_without_git():
    with Fixture() as f:
        service, repo, context, pending, path, receipt, item, launches = synthetic_delivery_service(f)
        service._push(repo, context, pending, path, receipt, item)
        item["versions"] = [{"version": "old"}]
        require(not service._continue_current_after_delivery(repo, context, {"optionsSha": "fixture-transport"}, path, receipt, item),
                "An omitted legacy intent must remain recovery-only")
        receipt["intent"] = "commit_and_push"
        recovery_request = receipt["requestId"]
        receipt["requestId"] = pending["requestId"]
        require(not service._continue_current_after_delivery(repo, context, {"optionsSha": "fixture-transport"}, path, receipt, item),
                "Even with a missing operation file, the same pending request cannot consume another fresh submission")
        receipt["requestId"] = recovery_request
        wrong_context = context[:3] + ({**context[3], "branch": "different"},)
        try:
            service._continue_current_after_delivery(repo, wrong_context, {"optionsSha": "fixture-transport"}, path, receipt, item)
            raise AssertionError("Changed fixed context cannot authorize fresh work")
        except Error as exc:
            require(exc.code == "destination_changed")
        require(service._continue_current_after_delivery(repo, context, {"optionsSha": "fixture-transport"}, path, receipt, item))
        saved = module._read(service._ops / (receipt["requestId"] + ".json"))
        row = saved["repositories"][0]
        require(row["status"] == "working" and row["commitSha"] == "" and row["title"] == row["body"] == "")
        require("versions" not in row and "verifiedRemote" not in row and "deliveryVerifiedAt" not in row)
        require(row["recoveredDelivery"]["status"] == "success" and row["recoveredDelivery"]["phase"] == "complete")
        require(row["recoveredDelivery"]["commitSha"] == pending["commitSha"])
        item.update(status="deferred", message="new saved work changed while being checked")
        service._save(receipt)
        require(service._delivery_acknowledged(pending), "Later WIP deferral must not lose the durable old success")
        item["recoveredDelivery"]["destination"] = {"repository": "wrong", "branch": "main"}
        service._save(receipt)
        require(not service._delivery_acknowledged(pending), "A different destination cannot acknowledge the original commit")
        require(not launches)


def test_commit_and_push_waits_for_delivery_and_ledger_without_git():
    with Fixture() as f:
        service, repo, context, pending, path, receipt, item, launches = synthetic_delivery_service(f)
        receipt["intent"] = "commit_and_push"
        require(not service._continue_current_after_delivery(repo, context, {"optionsSha": "fixture-transport"}, path, receipt, item))
        original_atomic = module._atomic
        def fail_ledger(target, value):
            if target.parent == service._uploads and target.suffix == ".json":
                raise PermissionError("synthetic ledger failure")
            return original_atomic(target, value)
        module._atomic = fail_ledger
        try:
            service._push(repo, context, pending, path, receipt, item)
        finally:
            module._atomic = original_atomic
        require(item["status"] == "success" and pending["uploadCounterPending"] is True)
        require(not service._continue_current_after_delivery(repo, context, {"optionsSha": "fixture-transport"}, path, receipt, item),
                "A successful remote check with a failed ledger cannot replace the original receipt")
        require("recoveredDelivery" not in item and not launches)


def test_request_intent_is_durable_and_cannot_upgrade_replay_without_git():
    with Fixture() as f:
        repo, pending = retained_delivery(f)
        service = f.service()
        original = {"requestId": "request_legacy_0001", "status": "success", "repositories": []}
        module._atomic(service._ops / (original["requestId"] + ".json"), original)
        restored = service.run(original["requestId"])
        require(restored["requestId"] == original["requestId"] and restored.get("intent") is None)
        try:
            service.run(original["requestId"], intent="commit_and_push")
            raise AssertionError("A legacy request ID must not gain a new submission intent")
        except Error:
            pass
        explicit = dict(original, requestId="request_explicit_0002", intent="commit_and_push")
        module._atomic(service._ops / (explicit["requestId"] + ".json"), explicit)
        restored = service.run(explicit["requestId"], intent="commit_and_push")
        require(restored["requestId"] == explicit["requestId"] and restored["intent"] == "commit_and_push")
        for intent in (None, "push_only", True):
            try:
                service.run(explicit["requestId"], intent=intent)
                raise AssertionError("A replayed or unknown intent cannot change the request")
            except Error:
                pass
        require(not service.busy and not service._queue)


def test_explicit_intent_enters_fresh_work_once_after_recovery_without_git():
    from contextlib import nullcontext
    for retained_state in ("committed", "delivered", "version_prepared", "staging"):
        for intent in (None, "commit_and_push"):
            with Fixture() as f:
                service, repo, context, pending, path, receipt, item, launches = synthetic_delivery_service(f)
                # Seed a durable successful old delivery, but leave its operation
                # unacknowledged to model the historical separate verify request.
                service._push(repo, context, pending, path, receipt, item)
                delivered = module._read(path)
                retained = dict(delivered, state=retained_state)
                if retained_state in {"version_prepared", "staging"}:
                    retained.update(commitSha="", versionPlans=[{"sourceId": "old-consumed-plan"}])
                module._atomic(path, retained)
                receipt["requestId"] = "request_fresh_submission_0003"
                if intent:
                    receipt["intent"] = intent
                fresh, continued_versions = [], []
                saved_work = f.base / "later-saved-work.txt"
                saved_work.write_text("version45 and current saved work remain until fresh CAS")
                service._sync_contract = lambda *args: None
                service._repo_locks = lambda *args: nullcontext()
                service._recover_commit = lambda *args, **kwargs: (
                    dict(retained, state="cancelled_before_commit") if retained_state == "staging" else retained)
                def resume_version(*args):
                    continued_versions.append(True)
                    # Deliberately persist a NEW dictionary, without mutating the
                    # caller's no-SHA/cancelled object or returning this journal.
                    replacement = dict(delivered, deliveryRecoveryRequestId=receipt["requestId"])
                    module._atomic(path, replacement)
                    item.update(status="success", phase="complete", commitSha=replacement["commitSha"],
                                deliveryVerifiedAt=replacement["verifiedAt"], verifiedRemote=replacement["verifiedRemote"])
                service._continue_version_intent = resume_version
                def verify_old(*args):
                    replacement = dict(delivered, deliveryRecoveryRequestId=receipt["requestId"])
                    module._atomic(path, replacement)
                    item.update(status="success", phase="complete", commitSha=replacement["commitSha"],
                                deliveryVerifiedAt=replacement["verifiedAt"], verifiedRemote=replacement["verifiedRemote"])
                service._push = verify_old
                def fresh_sync(*args):
                    fresh.append(True)
                    raise Error("Synthetic fresh-WIP CAS boundary", code="worktree_changed")
                service._sync = fresh_sync
                try:
                    service._run_repo_frozen(repo, {}, receipt, item)
                except Error as exc:
                    require(intent == "commit_and_push" and exc.code == "worktree_changed")
                else:
                    require(intent is None, "Explicit intent must enter the fresh work path")
                require(len(fresh) == (1 if intent else 0), (retained_state, intent, fresh))
                require(len(continued_versions) == (1 if retained_state in {"version_prepared", "staging"} else 0))
                require(saved_work.read_text() == "version45 and current saved work remain until fresh CAS")
                if intent:
                    require(item["commitSha"] == "" and item["recoveredDelivery"]["commitSha"] == delivered["commitSha"])
                    item.update(status="deferred")
                    service._save(receipt)
                    require(service._delivery_acknowledged(module._read(path)))
                require(not launches)


def test_legacy_verify_then_explicit_current_submission_bumps_once():
    class FailedOriginal(Service):
        def _git(self, root, *arguments, **kwargs):
            if arguments and arguments[0] == "push":
                raise module._GitFailure("timeout")
            return super()._git(root, *arguments, **kwargs)
    with Fixture() as f:
        root, remote, repo = f.repo()
        manifest = root / "app-manifest.json"
        manifest.write_text('{"version":"1.6.44"}\n')
        f.git(root, "add", "app-manifest.json")
        f.git(root, "commit", "-m", "Initial version")
        f.git(root, "push", "origin", "main")
        repo["versionSources"] = [{"path": "app-manifest.json", "kind": "json", "key": "version", "name": "App", "scope": "**"}]
        (root / "tracked.txt").write_text("original saved batch\n")
        first = f.run(f.service(FailedOriginal))
        original_sha = child(first)["commitSha"]
        require(child(first)["status"] == "verification_required" and original_sha)
        require(json.loads(manifest.read_text())["version"] == "1.6.45")
        f.git(root, "push", "origin", original_sha + ":refs/heads/main")
        (root / "tracked.txt").write_text("current saved batch\n")
        service = f.service()
        verified = f.run(service, "request_verify_original_0002")
        require(child(verified)["status"] == "success" and child(verified)["commitSha"] == original_sha)
        require(json.loads(manifest.read_text())["version"] == "1.6.45")
        require(f.git(root, "show", "HEAD:tracked.txt") == "original saved batch")
        current = f.run(service, "request_current_saved_0003", intent="commit_and_push")
        new_sha = child(current)["commitSha"]
        require(child(current)["status"] == "success" and new_sha != original_sha)
        require(child(current)["recoveredDelivery"]["commitSha"] == original_sha)
        require(json.loads(manifest.read_text())["version"] == "1.6.46")
        require(json.loads(f.git(remote, "show", "main:app-manifest.json"))["version"] == "1.6.46")
        require(f.git(remote, "show", "main:tracked.txt") == "current saved batch")
        count = f.git(root, "rev-list", "--count", "HEAD")
        replay = f.run(service, "request_current_saved_0003", intent="commit_and_push")
        require(child(replay)["commitSha"] == new_sha and f.git(root, "rev-list", "--count", "HEAD") == count)


def test_commit_timeout_after_success_reconciles_once_preserves_later_work():
    class LostCommitExit(Service):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.commit_calls = self.reconcile_calls = self.push_calls = 0
            self.actual_commit = ""
            self.push_targets = []

        def _git(self, root, *arguments, **kwargs):
            result = super()._git(root, *arguments, **kwargs)
            if arguments and arguments[0] == "commit":
                self.commit_calls += 1
                self.actual_commit = self._text(root, "rev-parse", "HEAD")
                # The commit really exists before its caller loses confirmation.
                raise module._GitFailure("timeout", operation="commit", error_kind="timeout")
            if arguments and arguments[0] == "push":
                self.push_calls += 1
            return result

        def _reconcile(self, *args, **kwargs):
            self.reconcile_calls += 1
            return super()._reconcile(*args, **kwargs)

        def _push(self, repo, context, pending, *args):
            self.push_targets.append(pending["commitSha"])
            # Work saved after the frozen commit must remain outside that push.
            (context[0] / "later-saved.txt").write_text("later saved work\n")
            return super()._push(repo, context, pending, *args)

    with Fixture() as f:
        root, remote, repo = f.repo()
        f.git(root, "commit", "--allow-empty", "-m", "1.6.44 → 1.6.45")
        f.git(root, "push", "origin", "main")
        repo["versionSources"] = [{"path": "HEAD", "kind": "git_commit", "key": "subject", "name": "App", "scope": "**"}]
        before_count = int(f.git(root, "rev-list", "--count", "HEAD"))
        (root / "tracked.txt").write_text("original saved work\n")
        service = f.service(LostCommitExit)
        identifier = "request_commit_timeout_0001"
        result = f.run(service, identifier, intent="commit_and_push")
        item = child(result)
        require(item["status"] == "success", result)
        sha = item["commitSha"]
        require(sha == service.actual_commit and service.commit_calls == service.reconcile_calls == service.push_calls == 1)
        require(service.push_targets == [sha] and item["verifiedRemote"] == sha)
        require(item["title"] == "1.6.45 → 1.6.46" and f.git(root, "show", "-s", "--format=%s", sha) == item["title"])
        require(f.git(root, "rev-parse", "HEAD") == f.git(remote, "rev-parse", "main") == sha)
        require(int(f.git(root, "rev-list", "--count", "HEAD")) == before_count + 1)
        require(f.git(remote, "show", "main:tracked.txt") == "original saved work")
        require(f.git(remote, "ls-tree", "--name-only", "main", "--", "later-saved.txt") == "")
        require((root / "later-saved.txt").read_text() == "later saved work\n")
        pending = module._read(service._pending_path(repo["id"]))
        require(pending["state"] == "delivered" and pending["commitError"] == "timeout" and pending["indexReconciled"] is True)
        require(pending["versionUpdates"] == [] and not Path(pending["temporaryIndex"]).exists())
        index = (root / ".git/index").read_bytes()
        require(module._sha(index) == pending["reconciledIndexSha"] and not (root / ".git/index.lock").exists())
        replay = f.run(service, identifier, intent="commit_and_push")
        require(child(replay)["commitSha"] == sha and service.commit_calls == service.reconcile_calls == service.push_calls == 1)
        require(int(f.git(root, "rev-list", "--count", "HEAD")) == before_count + 1 and (root / ".git/index").read_bytes() == index)
        require((root / "later-saved.txt").read_text() == "later saved work\n")

    # An unreconciled journal still needs its actual original temporary index.
    with Fixture() as f:
        repo, pending = retained_delivery(f)
        service = f.service()
        identity = pending["identity"]
        context = tuple(Path(identity[key]) for key in ("root", "gitdir", "common")) + (identity,)
        pending.update(indexReconciled=False, temporaryIndex=str(service.state_dir / "missing-index"))
        try:
            service._reconcile(context, pending, service._pending_path(repo["id"]))
            raise AssertionError("A genuinely missing recovery index must still refuse")
        except Error as exc:
            require(exc.code == "receipt_unverified" and pending["indexReconciled"] is False)


def test_missing_operation_replay_never_consumes_fresh_work_without_git():
    from contextlib import nullcontext
    for replay_id_kind in ("original", "recovery"):
        for intent in (None, "commit_and_push"):
            with Fixture() as f:
                service, repo, context, pending, path, receipt, item, launches = synthetic_delivery_service(f)
                service._push(repo, context, pending, path, receipt, item)
                original_id, recovery_id = pending["requestId"], "request_prior_recovery_0002"
                pending["deliveryRecoveryRequestId"] = recovery_id
                module._atomic(path, pending)
                module._atomic(service._ops / (recovery_id + ".json"),
                               {"requestId": recovery_id, "status": "success", "repositories": [dict(item)]})
                request_id = original_id if replay_id_kind == "original" else recovery_id
                (service._ops / (request_id + ".json")).unlink(missing_ok=True)
                receipt["requestId"] = request_id
                if intent:
                    receipt["intent"] = intent
                service._sync_contract = lambda *args: None
                service._repo_locks = lambda *args: nullcontext()
                fresh_reads = []
                def forbidden_fresh_snapshot(*args):
                    fresh_reads.append(True)
                    raise AssertionError("A used request cannot freeze later saved work again")
                service._snapshot = forbidden_fresh_snapshot
                saved = f.base / "later-saved-work.txt"
                saved.write_bytes(b"saved version45 plus new work must remain untouched")
                service._run_repo_frozen(repo, {}, receipt, item)
                service._save(receipt)
                require(item["status"] == "success" and item["commitSha"] == pending["commitSha"])
                require(not fresh_reads and not launches and "recoveredDelivery" not in item,
                        (replay_id_kind, intent, fresh_reads))
                require(saved.read_bytes() == b"saved version45 plus new work must remain untouched")
                retained = module._read(path)
                require(service._delivery_acknowledged(retained) and retained["uploadSummary"]["count"] == 1)


def test_unknown_old_delivery_never_enters_fresh_work_without_git():
    from contextlib import nullcontext
    with Fixture() as f:
        service, repo, context, pending, path, receipt, item, launches = synthetic_delivery_service(f)
        receipt.update(requestId="request_new_explicit_0003", intent="commit_and_push")
        service._sync_contract = lambda *args: None
        service._repo_locks = lambda *args: nullcontext()
        service._recover_commit = lambda *args, **kwargs: pending
        def still_unknown(*args):
            pending["state"] = "verification_required"
            module._atomic(path, pending)
            item.update(status="verification_required", phase="verify")
        service._push = still_unknown
        fresh_reads = []
        def forbidden_snapshot(*args):
            fresh_reads.append(True)
            raise AssertionError("Unknown original delivery cannot authorize a fresh snapshot")
        service._snapshot = forbidden_snapshot
        service._run_repo_frozen(repo, {}, receipt, item)
        require(item["status"] == "verification_required" and not fresh_reads and not launches)


def test_submission_probe_local_clean_outgoing_sync_and_staging_without_git():
    with Fixture() as f:
        root, gitdir = f.base / "repo", f.base / "repo" / ".git"
        gitdir.mkdir(parents=True)
        (gitdir / "index").write_bytes(b"original index")
        repo = {"id":"probe", "path":str(root), "repositoryUrl":str(f.base / "remote.git"),
                "remote":"origin", "branch":"main", "exclude":[], "syncFiles":[], "versionSources":[]}
        context = (root, gitdir, gitdir, {})
        service = f.service()
        service._repo = lambda _repo: context
        head, other = "a" * 40, "b" * 40
        observed = []
        status, baseline, outgoing, sync = b"", head, "0", False
        def git(_root, *args, **kwargs):
            observed.append(args[0])
            require(args[0] in {"config", "status"}, "Local probe must not fetch, filter, sync or push")
            return b"fixed config" if args[0] == "config" else status
        def text(_root, *args):
            observed.append(args[0])
            if args[0] == "show-ref":
                if baseline is None:
                    raise module._GitFailure("git_failed", returncode=1)
                return baseline
            return outgoing if args[0] == "rev-list" else head
        service._git, service._text = git, text
        service._saved_sync_changes = lambda *args: {"syncChanged":sync}
        require(service._submission_probe(repo, context)["state"] == "clean")
        status = b"?? .env\0"
        require(service._submission_probe(repo, context)["state"] == "clean", "Private work remains excluded")
        status = b" M tracked.txt\0"
        require(service._submission_probe(repo, context)["state"] == "actionable")
        for staged in (b"M  .env\0", b"UU conflict.txt\0"):
            status = staged
            try:
                service._submission_probe(repo, context)
                raise AssertionError("Existing staging/conflicts must not become clean")
            except Error as exc:
                require(exc.code in {"staged_selection", "merge_conflict"})
        status = b""
        sync = True
        require(service._submission_probe(repo, context)["state"] == "actionable")
        sync = None
        require(service._submission_probe(repo, context)["state"] == "unknown")
        sync = False
        baseline = None
        require(service._submission_probe(repo, context)["state"] == "unknown")
        baseline = other
        require(service._submission_probe(repo, context)["state"] == "unknown", "Behind is not confirmed clean")
        service._head_commit = lambda *args: None
        catalog = service._local_changes(repo, context)
        require(catalog["outgoingCommits"] == 0 and catalog["headSha"] != catalog["outgoingBaselineSha"]
                and catalog["hasChanges"] is None and catalog["changeState"] == "unknown", catalog)
        outgoing = "1"
        require(service._submission_probe(repo, context)["state"] == "actionable")
        service._version_sources = lambda *args: [{"path":"version.json", "kind":"json", "key":"version", "repositoryVersion":True, "minimumVersion":"1.0.0"}]
        service._version_reader = lambda *args: lambda path: b'{"version":"unknown"}'
        require(service._submission_probe(repo, context)["state"] == "unknown", "Invalid authority cannot escape the batch preflight")
        require(not any(name in observed for name in ("fetch", "push", "add", "commit", "ls-remote")))


def test_clean_submission_returns_before_sync_version_remote_without_git():
    from contextlib import nullcontext
    with Fixture() as f:
        service = f.service()
        root = f.base / "repo"
        repo = {"id":"clean", "path":str(root), "repositoryUrl":str(f.base / "remote.git"), "remote":"origin", "branch":"main", "syncFiles":[], "exclude":[]}
        context = (root, root / ".git", root / ".git", {})
        history = {"binding":dict(repoId="clean", path=str(root)), "count":7, "state":"recorded"}
        item = {"repoId":"clean", "status":"queued", "phase":"queued", "commitSha":"", "title":"", "body":"", "logs":[], "uploadSummary":history}
        receipt = {"requestId":"request_clean_now_0001", "status":"working", "repositories":[item]}
        saved = []
        service._save = lambda current: saved.append(json.loads(json.dumps(current)))
        service._repo = lambda *args: context
        service._repo_locks = lambda *args: nullcontext()
        service._transport_identity = lambda *args: {"optionsSha":module._json_sha([])}
        service._busy_reason = service._blockers = lambda *args: None
        service._submission_probe = lambda *args: {"state":"clean", "headSha":"a" * 40, "baselineSha":"a" * 40, "remoteChecked":False}
        def forbidden(*args, **kwargs):
            raise AssertionError("Clean submission must finish before snapshot/sync/version/remote phases")
        for name in ("_git", "_snapshot", "_sync", "_version_details", "_remote", "_fetch", "_push"):
            setattr(service, name, forbidden)
        service._run_repo_frozen(repo, {}, receipt, item)
        require(item["status"] == "noop" and item["phase"] == "complete" and item["commitSha"] == "")
        require(item["uploadSummary"] is history and history["count"] == 7 and item["preflight"]["remoteChecked"] is False)
        require(all(row["repositories"][0]["phase"] not in {"sync", "version", "remote"} for row in saved))


def test_batch_skips_clean_before_green_work_preserving_display_order_without_git():
    from contextlib import nullcontext
    with Fixture() as f:
        service = f.service()
        states = [("white-one", "clean"), ("unknown", "unknown"), ("green-one", "actionable"), ("green-two", "actionable"), ("white-two", "clean")]
        repos = [{"id":name, "path":str(f.base / name), "enabled":True} for name, _ in states]
        items = [{"repoId":repo["id"], "status":"queued", "phase":"queued", "message":"", "logs":[], "commitSha":"", "title":"", "body":"", "uploadSummary":{"count":3}} for repo in repos]
        receipt = {"requestId":"request_sorted_batch_0001", "status":"queued", "repositories":items}
        service._repo = lambda repo: (f.base / repo["id"], f.base / repo["id"] / ".git", f.base / repo["id"] / ".git", {})
        service._repo_locks = lambda *args: nullcontext()
        by_state, persisted, actual = dict(states), [], []
        def probe(repo, context, current, item):
            state = by_state[repo["id"]]
            if state == "unknown":
                raise ValueError("Classification is unknown; normal row handling still follows")
            if state == "clean":
                item.update(status="noop", phase="complete", message="clean")
            return {"state":state}
        service._skip_clean_submission = probe
        service._save = lambda current: persisted.append(json.loads(json.dumps(current)))
        def work(repo, naming, current, item):
            require(all(row["status"] == "noop" for row in items if by_state[row["repoId"]] == "clean"), "Clean rows must not wait behind a long green push")
            require(any(all(row["status"] == "noop" for row in snapshot["repositories"] if by_state[row["repoId"]] == "clean") for snapshot in persisted))
            actual.append(repo["id"])
            item.update(status="success", phase="complete")
        service._run_repo = work
        service._queue.append((receipt, repos, {"naming":dict(module._DEFAULT_NAMING)}))
        service._drain_batches()
        require(actual == ["green-one", "green-two", "unknown"] == receipt["executionOrder"])
        require([row["repoId"] for row in receipt["repositories"]] == [name for name, _ in states])
        require(all(row["uploadSummary"]["count"] == 3 for row in items))


def test_clean_skip_preserves_unsettled_delivery_and_used_requests_without_git():
    with Fixture() as f:
        service, repo, context, pending, path, receipt, item, launches = synthetic_delivery_service(f)
        service._push(repo, context, pending, path, receipt, item)
        service._save(receipt)
        pending = module._read(path)
        pending.update(indexReconciled=True, transportOptionsSha=module._json_sha([]))
        service._remote_options = lambda *args: []
        module._atomic(path, pending)
        require(service._settled_submission(repo, context, pending))
        for key, value in (("state", "verification_required"), ("uploadCounterPending", True), ("indexReconciled", False)):
            require(not service._settled_submission(repo, context, dict(pending, **{key:value})))
        ledger_path, ledger = service._upload_ledger(service._upload_destination(repo))
        ledger_path.unlink()
        require(not service._settled_submission(repo, context, pending), "A missing ledger still needs recovery")
        module._atomic(ledger_path, ledger)
        def forbidden(*args):
            raise AssertionError("A previously used request must retain original recovery scope")
        service._submission_probe = forbidden
        for request_id in (pending["requestId"], pending["deliveryRecoveryRequestId"]):
            receipt["requestId"] = request_id
            require(service._skip_clean_submission(repo, context, receipt, item) is None)
        require(not launches)


def test_clean_bare_submission_skips_sync_and_remote_but_keeps_changed_sources_and_staging():
    class Observed(Service):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.git_operations, self.phases, self.sync_calls = [], [], 0
        def _git(self, root, *args, **kwargs):
            self.git_operations.append(module._git_operation(args))
            require(module._git_operation(args) not in {"ls-remote", "fetch", "push", "add", "commit"}, "Confirmed clean must use only local Git reads")
            return super()._git(root, *args, **kwargs)
        def _phase(self, receipt, item, phase, message):
            self.phases.append(phase)
            return super()._phase(receipt, item, phase, message)
        def _sync(self, *args):
            self.sync_calls += 1
            raise Error("Changed saved source reached its normal sync boundary", code="worktree_changed")
        def _version_details(self, *args):
            raise AssertionError("A clean row must not enter version planning")
    with Fixture() as f:
        root, _remote, repo = f.repo()
        source = f.base / "saved.txt"
        source.write_bytes((root / "tracked.txt").read_bytes())
        repo["syncFiles"] = [{"source":str(source), "target":"tracked.txt"}]
        (root / ".env").write_text("private work remains private\n")
        head, index = f.git(root, "rev-parse", "HEAD"), (root / ".git/index").read_bytes()
        service = f.service(Observed)
        result = f.run(service, "request_clean_bare_0001", intent="commit_and_push")
        item = child(result)
        require(item["status"] == "noop" and item["phase"] == "complete" and item["commitSha"] == "", result)
        require(item["preflight"]["remoteChecked"] is False and item["uploadSummary"]["count"] == 0)
        require(service.sync_calls == 0 and not any(phase in service.phases for phase in ("sync", "version", "remote")))
        require(not service._pending_path(repo["id"]).exists() and (root / ".git/index").read_bytes() == index)
        count = len(service.git_operations)
        replay = f.run(service, "request_clean_bare_0001", intent="commit_and_push")
        require(child(replay)["status"] == "noop" and len(service.git_operations) == count)
        source.write_text("new saved external source\n")
        result = f.run(service, "request_changed_source_0002", intent="commit_and_push")
        require(child(result)["status"] == "deferred" and service.sync_calls == 1, result)
        require((root / "tracked.txt").read_text() == "base\n", "Probe did not copy an external file")
        f.git(root, "add", ".env")
        staged = (root / ".git/index").read_bytes()
        result = f.run(service, "request_staged_private_0003", intent="commit_and_push")
        require(child(result)["diagnostic"]["code"] == "staged_selection" and service.sync_calls == 1, result)
        require((root / ".git/index").read_bytes() == staged and f.git(root, "rev-parse", "HEAD") == head)
        require((root / ".env").read_text() == "private work remains private\n")


def test_repository_main_authority_and_initial_public_contract_without_git():
    with Fixture() as f:
        root = f.base / "project"
        service = f.service()
        plugins = [{"path":"one/__init__.py", "kind":"python_ast", "key":"bl_info.version", "name":"One", "scope":"one/**"},
                   {"path":"two/__init__.py", "kind":"python_ast", "key":"bl_info.version", "name":"Two", "scope":"two/**"}]
        repo = {"versionSources":plugins}
        sources = service._version_sources(repo, root)
        require(sources[:2] == plugins and not any("minimumVersion" in item for item in plugins))
        main = sources[-1]
        require(main["repositoryVersion"] and main["allowInitial"] and main["path"] == "HEAD" and main["minimumVersion"] == "1.0.0")
        affected = service._affected_sources(sources, [{"path":"one/module.py"}])
        require(module.version_source_id(main) in affected and module.version_source_id(plugins[0]) in affected)
        file_main = {"repositoryVersion":True, "kind":"json", "currentVersion":"0.4.0", "nextVersion":"1.0.0", "requiresVersionFloor":True}
        public = service._repository_version([file_main])
        require(public == {"state":"initial", "currentVersion":"1.0.0", "sourceVersion":"0.4.0", "nextVersion":"1.0.0",
                           "transition":{"kind":"initial", "fromVersion":"0.4.0", "toVersion":"1.0.0"}})
        initial = service._repository_version([{**file_main, "kind":"git_commit", "currentVersion":"1.0.0", "initialVersion":True}])
        require(initial["sourceVersion"] == "" and initial["transition"] is None)
        known = service._repository_version([{**file_main, "requiresVersionFloor":False, "currentVersion":"1.6.47", "nextVersion":"1.6.48"}])
        require(known["state"] == "current" and known["currentVersion"] == "1.6.47")
        raw = {**file_main, "requiresVersionFloor":False, "currentVersion":"v1.02.003", "nextVersion":"v1.02.004",
               "transition":{"kind":"working", "fromVersion":"V1.02.002", "toVersion":"v1.02.003"}}
        public = service._repository_version([raw])
        require(public["currentVersion"] == "1.2.3" and public["nextVersion"] == "1.2.4"
                and public["transition"] == {"kind":"working", "fromVersion":"1.2.2", "toVersion":"1.2.3"})
        require(raw["currentVersion"] == "v1.02.003", "Public formatting must not rewrite the real authority")


def test_root_repository_version_discovery_keeps_independent_plugin_versions_without_git():
    with Fixture() as f:
        root = f.base / "plugins"
        root.mkdir()
        (root / "repository-version.json").write_text('{"version":"1.0.0"}\n')
        plugins = [{"path":"one/__init__.py", "kind":"python_ast", "key":"bl_info.version", "name":"One", "scope":"one/**"},
                   {"path":"two/__init__.py", "kind":"python_ast", "key":"bl_info.version", "name":"Two", "scope":"two/**"}]
        service = f.service()
        sources = service._version_sources({"versionSources":plugins}, root)
        require(sources[:2] == plugins and len(sources) == 3)
        require(sources[-1]["path"] == "repository-version.json" and sources[-1]["repositoryVersion"] is True)
        require(not any(source["kind"] == "git_commit" for source in sources))
        require(not any("minimumVersion" in source for source in plugins))


def test_main_initialization_ignores_old_auto_optout_but_never_creates_empty_git_plan_without_git():
    with Fixture() as f:
        root = f.base / "project"
        service = f.service()
        repo = {"versionSources":[], "versionPlans":[]}
        source = service._version_sources(repo, root)[0]
        component = {"sourceId":module.version_source_id(source), "path":"HEAD", "kind":"git_commit", "name":"Main", "repositoryVersion":True,
                     "initialVersion":True, "currentVersion":"1.0.0", "nextVersion":"1.0.0", "versionChanged":False,
                     "canBump":True, "planState":"none", "expectedSha256":"a" * 64, "expectedBytes":1, "planProof":"b" * 64}
        context = (root, root / ".git", root / ".git", {})
        effective, _automatic, _blocked = service._planned_versions(repo, context, [dict(component)], [{"path":"saved.txt"}], {"autoBump":False})
        require(len(effective) == 1 and effective[0]["targetVersion"] == "1.0.0")
        require(not service._planned_versions(repo, context, [dict(component)], [], {"autoBump":False})[0])
        known = dict(component, initialVersion=False, currentVersion="1.6.47", nextVersion="1.6.48")
        require(not service._planned_versions(repo, context, [known], [{"path":"saved.txt"}], {"autoBump":False})[0])
        root.mkdir()
        (root / "repository-version.json").write_text('{"version":"0.4.0"}\n')
        source = service._version_sources(repo, root)[0]
        floor = dict(component, sourceId=module.version_source_id(source), path=source["path"], kind="json",
                     initialVersion=False, requiresVersionFloor=True, currentVersion="0.4.0")
        require(len(service._planned_versions(repo, context, [floor], [], {"autoBump":False})[0]) == 1)


def test_git_environment_uses_actual_transport_and_skips_test_mode_without_git():
    with Fixture() as f:
        service = f.service()
        original_environment, original_run = module.environment_for_remote, module.subprocess.run
        seen, environments = [], []
        def proxy(environment, url):
            seen.append(url)
            return dict(environment, FIXTURE_PROXY_ONLY="1")
        def run(command, **kwargs):
            environments.append(kwargs["env"])
            return subprocess.CompletedProcess(command, 0, b"", b"")
        module.environment_for_remote, module.subprocess.run = proxy, run
        try:
            service._test_mode = False
            service._lease.transport = {"identity":{"fetchUrl":"https://example.invalid/read", "pushUrl":"https://example.invalid/write"}}
            service._git(f.base, "ls-remote", "origin")
            service._git(f.base, "push", "origin", config=[("remote.fixed.url", "https://example.invalid/pinned-read"), ("remote.fixed.pushurl", "https://example.invalid/pinned-write")])
            require(seen == ["https://example.invalid/read", "https://example.invalid/pinned-write"])
            service._test_mode = True
            service._git(f.base, "ls-remote", "origin")
            require(len(seen) == 2 and "FIXTURE_PROXY_ONLY" not in environments[-1])
        finally:
            module.environment_for_remote, module.subprocess.run = original_environment, original_run


def test_missing_repository_version_initializes_once_and_recovery_keeps_new_work():
    class FailFirstPush(Service):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.pushes = 0
        def _git(self, root, *args, **kwargs):
            if args and args[0] == "push":
                self.pushes += 1
                if self.pushes == 1:
                    raise module._GitFailure("timeout", operation="push", error_kind="timeout")
            return super()._git(root, *args, **kwargs)
    with Fixture() as f:
        root, remote, repo = f.repo()
        service = f.service(FailFirstPush)
        clean = f.run(service, "request_missing_clean_0001", intent="commit_and_push")
        require(child(clean)["status"] == "noop" and f.git(root, "rev-list", "--count", "HEAD") == "1")
        (root / "tracked.txt").write_text("first saved batch\n")
        first = f.run(service, "request_initial_version_0002", intent="commit_and_push")
        sha = child(first)["commitSha"]
        require(child(first)["status"] == "verification_required" and child(first)["title"] == "1.0.0", first)
        require(f.git(root, "show", "-s", "--format=%s", sha) == "1.0.0")
        (root / "later.txt").write_text("new work remains outside the original scope\n")
        require(f.run(service, "request_initial_version_0002", intent="commit_and_push") == first)
        recovered = f.run(service, "request_verify_initial_0003")
        require(child(recovered)["status"] == "success" and child(recovered)["commitSha"] == sha and service.pushes == 2, recovered)
        require(f.git(root, "rev-list", "--count", "HEAD") == "2" and f.git(remote, "rev-parse", "main") == sha)
        require(f.git(remote, "ls-tree", "--name-only", "main", "--", "later.txt") == "" and (root / "later.txt").exists())


def test_used_cancelled_request_has_terminal_receipt_without_git():
    from contextlib import nullcontext
    for intent in (None, "commit_and_push"):
        with Fixture() as f:
            service, repo, context, pending, path, receipt, item, launches = synthetic_delivery_service(f)
            pending.update(state="cancelled_before_commit", commitSha="")
            module._atomic(path, pending)
            receipt["requestId"] = pending["requestId"]
            if intent:
                receipt["intent"] = intent
            service._sync_contract = lambda *args: None
            service._repo_locks = lambda *args: nullcontext()
            def forbidden_snapshot(*args):
                raise AssertionError("A used cancelled request cannot resnapshot fresh work")
            service._snapshot = forbidden_snapshot
            service._run_repo_frozen(repo, {}, receipt, item)
            require(item["status"] == "verification_required" and item["phase"] == "verify" and not launches)


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
    service._lease = module.threading.local()
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
    environment_sha = module._sha(SOURCE.with_name("console_git_environment.py").read_bytes())
    print("Source SHA256 " + source_sha + "; test SHA256 " + test_sha)
    print("Git environment SHA256 " + environment_sha)
    selected = [test for test in TESTS if not sys.argv[1:] or test.__name__ in sys.argv[1:]]
    require(len(selected) == len(sys.argv[1:]) if sys.argv[1:] else True, "Unknown test name")
    for test in selected:
        test()
        print("PASS " + test.__name__)
    require(module._sha(SOURCE.read_bytes()) == source_sha and module._sha(Path(__file__).read_bytes()) == test_sha
            and module._sha(SOURCE.with_name("console_git_environment.py").read_bytes()) == environment_sha,
            "Source or tests changed during this run; results do not certify the final files")
    print(f"{len(selected)} isolated serial Git checks PASS; real repositories untouched")
