"""Disposable standard-Git/LFS checks; no user repository or remote is changed."""
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import console_repository_lfs as lfs
import console_repository_publish as publisher

spec = importlib.util.spec_from_file_location("publish_lfs_fixture", ROOT / "tools/check-console-repository-publish.py")
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
publisher = fixtures.module
Fixture, Service, child, require = fixtures.Fixture, fixtures.Service, fixtures.child, fixtures.require


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


class Recorded(Service):
    def __init__(self, *args, **kwargs):
        self.calls = []
        super().__init__(*args, **kwargs)

    def _git(self, root, *args, **kwargs):
        self.calls.append((args, kwargs.get("config")))
        return super()._git(root, *args, **kwargs)


def endpoint(fixture, root, remote):
    fixture.git(root, "config", "remote.origin.lfsurl", str(remote))
    fixture.git(root, "config", "remote.origin.lfspushurl", str(remote))


def test_decimal_boundary_and_literal_patterns():
    records = [{"path": "equal.bin", "bytes": 100_000_000}, {"path": "larger.bin", "bytes": 100_000_001},
               {"path": "deleted.bin", "bytes": 100_000_001, "deleted": True}]
    require([item["path"] for item in lfs.candidates(records)] == ["larger.bin"])
    with Fixture() as f:
        root, _, _ = f.repo()
        names = ["space [1] #.bin", "dir/a*.bin", "q?.bin", 'quote".bin']
        (root / ".gitattributes").write_text("".join(lfs.attribute_line(name) for name in names), encoding="utf-8")
        git = lambda *args, **kwargs: subprocess.run(["git", "-C", str(root), *args], input=kwargs.get("data"),
                                                     capture_output=True, check=True, env=f.env).stdout
        result = lfs.filters(git, names + ["space 1 #.bin", "dir/abc.bin", "qa.bin", "nested/space [1] #.bin"])
        require(all(result[name] == "lfs" for name in names), result)
        require(all(result[name] == "unspecified" for name in result if name not in names), result)


def test_saved_files_use_pointers_preserve_hooks_and_transfer():
    with Fixture() as f, patch.object(lfs, "LARGE_FILE_BYTES", 4096):
        root, remote, _ = f.repo()
        endpoint(f, root, remote)
        hook = root / ".git/hooks/pre-push"
        hook.parent.mkdir(exist_ok=True)
        hook.write_text("#!/bin/sh\nprintf checked >>\"$(git rev-parse --git-dir)/hook-proof\"\n", encoding="utf-8", newline="\n")
        hook.chmod(0o755); original_hook = hook.read_bytes()
        attributes = b"# Existing user rules stay intact\n*.unrelated -text\n"
        (root / ".gitattributes").write_bytes(attributes)
        asset = root / "saved [1] file.bin"; asset.write_bytes(b"binary fixture\0" * 1024)
        original = digest(asset)
        service = f.service(Recorded)
        result = f.run(service, intent="commit_and_push")
        require(child(result)["status"] == "success", result)
        pointer = lfs.pointer(f.git(root, "show", "HEAD:saved [1] file.bin").encode())
        require(pointer == {"bytes": asset.stat().st_size, "sha256": original}, pointer)
        require(digest(asset) == original and hook.read_bytes() == original_hook)
        require((root / ".gitattributes").read_bytes().startswith(attributes))
        require((root / ".git/hook-proof").read_text() == "checked")
        require(any(path.is_file() for path in (remote / "lfs/objects").rglob("*")))
        transfers = [args for args, config in service.calls if args[:2] == ("lfs", "push")]
        require(len(transfers) == 1 and transfers[0][3] == child(result)["commitSha"], transfers)
        require(all("--force" not in args and "--force-with-lease" not in args for args, _ in service.calls))
        require(f.git(root, "status", "--porcelain") == "")
        calls = len(transfers)
        replay = f.run(service, "request_00000001", intent="commit_and_push")
        require(child(replay)["commitSha"] == child(result)["commitSha"])
        require(len([args for args, _ in service.calls if args[:2] == ("lfs", "push")]) == calls)


def test_conflicting_nested_filters_and_staging_are_preserved():
    for mode in ("filter", "nested", "staged"):
        with Fixture() as f, patch.object(lfs, "LARGE_FILE_BYTES", 4096):
            root, remote, _ = f.repo()
            folder = root / "assets"; folder.mkdir()
            asset = folder / "data.big"; asset.write_bytes(b"saved asset\0" * 1024)
            attributes = folder / ".gitattributes" if mode == "nested" else root / ".gitattributes"
            attributes.write_text("*.big -filter\n" if mode == "nested" else "*.big filter=other\n")
            if mode == "staged":
                f.git(root, "add", "tracked.txt")
                (root / "tracked.txt").write_text("user selected\n")
                f.git(root, "add", "tracked.txt")
                (root / "tracked.txt").write_text("later unstaged bytes\n")
            before_index = (root / ".git/index").read_bytes()
            before_attrs = attributes.read_bytes(); before_head = f.git(root, "rev-parse", "HEAD")
            result = f.run(f.service(), intent="commit_and_push")
            expected = "staged_selection" if mode == "staged" else "git_lfs"
            require(child(result)["diagnostic"]["code"] == expected, result)
            require(attributes.read_bytes() == before_attrs and (root / ".git/index").read_bytes() == before_index)
            require(f.git(root, "rev-parse", "HEAD") == before_head and f.git(remote, "rev-parse", "main") == before_head)


def test_excluded_big_file_is_never_tracked():
    with Fixture() as f, patch.object(lfs, "LARGE_FILE_BYTES", 4096):
        root, _, repo = f.repo()
        repo["exclude"] = ["keep.big"]
        (root / "keep.big").write_bytes(b"private saved bytes" * 1024)
        (root / "tracked.txt").write_text("real saved work\n")
        result = f.run(f.service(), intent="commit_and_push")
        require(child(result)["status"] == "success", result)
        require(not (root / ".gitattributes").exists())
        require(f.git(root, "ls-tree", "--name-only", "HEAD", "keep.big") == "")


def test_existing_large_history_is_diagnosed_without_rewrite():
    with Fixture() as f, patch.object(lfs, "LARGE_FILE_BYTES", 4096):
        root, remote, _ = f.repo()
        published = f.git(root, "rev-parse", "HEAD")
        (root / "old.big").write_bytes(b"old Git blob\0" * 1024)
        f.git(root, "add", "old.big"); f.git(root, "commit", "-m", "unpublished large blob")
        head = f.git(root, "rev-parse", "HEAD"); index = (root / ".git/index").read_bytes()
        service = f.service(Recorded); result = f.run(service, intent="commit_and_push")
        require(child(result)["diagnostic"]["code"] == "git_large_history", result)
        require(f.git(root, "rev-parse", "HEAD") == head and (root / ".git/index").read_bytes() == index)
        require(f.git(remote, "rev-parse", "main") == published)
        require(not any(args[0] == "push" or args[:2] == ("lfs", "push") for args, _ in service.calls))


def test_staged_raw_content_cannot_masquerade_as_lfs():
    with Fixture() as f, patch.object(lfs, "LARGE_FILE_BYTES", 4096):
        root, _, _ = f.repo()
        asset = root / "broken.big"; asset.write_bytes(b"still normal Git\0" * 1024)
        (root / ".gitattributes").write_text("*.big filter=lfs\n")
        f.git(root, "config", "filter.lfs.clean", "cat")
        f.git(root, "config", "filter.lfs.process", "")
        f.git(root, "config", "filter.lfs.required", "false")
        index = f.base / "test-index"
        service = f.service()
        service._git(root, "read-tree", "HEAD", index=index)
        service._git(root, "add", ".gitattributes", "broken.big", index=index)
        try:
            lfs.verify_index(lambda *args, **kwargs: service._git(root, *args, **kwargs),
                             [{"path": "broken.big", "bytes": asset.stat().st_size, "sha256": digest(asset)}], index)
            raise AssertionError("Raw blob must not pass LFS pointer verification")
        except lfs.LargeFileError:
            pass


def test_inherited_custom_filter_and_atomic_attribute_failure_preserve_files():
    for mode in ("inherited", "replace", "created"):
        with Fixture() as f, patch.object(lfs, "LARGE_FILE_BYTES", 4096):
            root, _, _ = f.repo()
            asset = root / "saved.big"; asset.write_bytes(b"unchanged file\0" * 1024)
            attributes = root / ".gitattributes"
            if mode != "created":
                attributes.write_bytes(b"# Keep these exact user bytes\n")
            service = f.service()
            config_path = root / ".git/config"
            config_before = config_path.read_bytes()
            if mode == "inherited":
                (service.state_dir / "empty-config").write_text('[filter "lfs"]\n\tclean = custom-user-clean %f\n')
                result = f.run(service, intent="commit_and_push")
                require(child(result)["diagnostic"]["code"] == "git_lfs", result)
                require(config_path.read_bytes() == config_before, "Must not hide an inherited filter with local settings")
            else:
                real_replace, real_link = publisher.os.replace, publisher.os.link
                def replace(source, target):
                    if Path(target) == attributes:
                        raise OSError("isolated atomic attribute replacement failure")
                    return real_replace(source, target)
                def link(source, target):
                    if Path(target) == attributes:
                        attributes.write_bytes(b"# Concurrently created by another editor\n")
                        raise FileExistsError("isolated concurrent create")
                    return real_link(source, target)
                with patch.object(publisher.os, "replace", side_effect=replace), patch.object(publisher.os, "link", side_effect=link):
                    result = f.run(service, intent="commit_and_push")
                require(child(result)["status"] != "success", result)
                require(list(service.state_dir.glob("lfs-attributes-*.json")), "Original attributes need a recoverable backup")
            expected = b"# Concurrently created by another editor\n" if mode == "created" else b"# Keep these exact user bytes\n"
            require(attributes.read_bytes() == expected)
            require(not list(root.glob(".console-lfs-*.tmp")))


def test_explicit_lfs_transport_uses_the_pinned_push_url():
    with Fixture() as f:
        root, _, _ = f.repo()
        service = f.service(); service._test_mode = False
        service._lease.transport = {"identity": {"fetchUrl": "https://read.invalid/repo", "pushUrl": "https://write.invalid/repo"}}
        observed = []
        def environment(original, remote):
            observed.append(remote); return original
        with patch.object(publisher, "environment_for_remote", side_effect=environment), patch.object(publisher.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=b"", stderr=b"")):
            service._git(root, "lfs", "push", "fixed-alias", "a" * 40,
                         config=[("remote.fixed-alias.url", "https://read.invalid/repo"),
                                 ("remote.fixed-alias.pushurl", "https://write.invalid/repo")])
        require(observed == ["https://write.invalid/repo"], observed)
        require(publisher._git_operation(("lfs", "push", "fixed-alias", "a" * 40)) == "lfs")


def test_failed_lfs_upload_retries_the_same_commit_and_preserves_later_work():
    class FailedOnce(Recorded):
        fail = True

        def _git(self, root, *args, **kwargs):
            if args[:2] == ("lfs", "push") and self.fail:
                raise publisher._GitFailure("lfs", returncode=1, operation="lfs")
            return super()._git(root, *args, **kwargs)
    with Fixture() as f, patch.object(lfs, "LARGE_FILE_BYTES", 4096):
        root, remote, _ = f.repo(); endpoint(f, root, remote)
        (root / "saved.big").write_bytes(b"saved local LFS asset\0" * 1024)
        service = f.service(FailedOnce)
        failed = f.run(service, "request_lfs_failure_001", intent="commit_and_push")
        sha = child(failed)["commitSha"]
        require(sha and child(failed)["status"] == "push_failed", failed)
        require(child(failed)["diagnostic"]["code"] == "git_lfs", failed)
        (root / "tracked.txt").write_text("later work must stay uncommitted\n")
        service.fail = False
        recovered = f.run(service, "request_lfs_retry_0001")
        require(child(recovered)["status"] == "success" and child(recovered)["commitSha"] == sha, recovered)
        require(f.git(root, "rev-parse", "HEAD") == sha and f.git(remote, "rev-parse", "main") == sha)
        require((root / "tracked.txt").read_text() == "later work must stay uncommitted\n")
        require(f.git(root, "show", "HEAD:tracked.txt") == "base")


def test_real_decimal_limit_sparse_file_once():
    with Fixture() as f:
        root, remote, _ = f.repo()
        endpoint(f, root, remote)
        asset = root / "large-sparse.bin"
        with asset.open("wb") as stream:
            stream.seek(100_000_000); stream.write(b"X")
        original = digest(asset)
        service = f.service()
        service.run("request_real_limit_0001", intent="commit_and_push")
        deadline = time.monotonic() + 300
        while True:
            result = service.operation("request_real_limit_0001")
            if result["status"] not in {"queued", "working"}:
                if service._worker:
                    service._worker.join(timeout=5)
                break
            require(time.monotonic() < deadline, "Real LFS fixture did not finish")
            time.sleep(.05)
        require(child(result)["status"] == "success", result)
        pointer = lfs.pointer(f.git(root, "show", "HEAD:large-sparse.bin").encode())
        require(pointer == {"bytes": 100_000_001, "sha256": original}, pointer)
        require(asset.stat().st_size == 100_000_001 and digest(asset) == original)


TESTS = [value for key, value in tuple(globals().items()) if key.startswith("test_")]
if __name__ == "__main__":
    selected = [test for test in TESTS if test.__name__ in sys.argv[1:] or not sys.argv[1:] and test.__name__ != "test_real_decimal_limit_sparse_file_once"]
    require(not sys.argv[1:] or len(selected) == len(sys.argv[1:]), "Unknown LFS test name")
    for test in selected:
        test(); print("PASS " + test.__name__, flush=True)
    if not sys.argv[1:]:
        print("Real 100,000,001-byte fixture is opt-in: test_real_decimal_limit_sparse_file_once")
