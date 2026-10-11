"""Explicit one-time version plans: pure text and serial isolated Git fixtures."""
import base64
from contextlib import contextmanager
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import console_repository_versions as versions
spec = importlib.util.spec_from_file_location("publish_fixtures", ROOT / "tools/check-console-repository-publish.py")
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
Fixture, Service, Error = fixtures.Fixture, fixtures.Service, fixtures.Error
module, require, child, hooks = fixtures.module, fixtures.require, fixtures.child, fixtures.hooks


def source(path="app.json", kind="json", key="version", name="fixture", scope=""):
    return dict(path=path, kind=kind, key=key, name=name, scope=scope)


def plan(component):
    require(component["canBump"], component)
    return {key: component[key] for key in ("sourceId", "currentVersion", "expectedSha256", "expectedBytes", "planProof")} | {"targetVersion": component["nextVersion"]}


def pure(raw, item=None):
    item = item or source()
    reader = lambda path: raw
    component = versions.catalog(Path("."), [item], reader)[0]
    updates, _ = versions.prepare_updates(Path("."), [item], [plan(component)], reader)
    return component, base64.b64decode(updates[0]["afterBase64"])


def seed(f, root, repo, console=False):
    if console:
        files = console_images()
        repo["versionSources"] = [source("app-manifest.json")]
    else:
        files = {"app.json": b'\xef\xbb\xbf{\r\n  "version": "1.2.3", "label": "\xe4\xb8\xad\xe6\x96\x87"\r\n}\r\n'}
        repo["versionSources"] = [source()]
    for name, raw in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    f.git(root, "add", ".")
    f.git(root, "commit", "-m", "version fixture")
    f.git(root, "push", "origin", "HEAD:refs/heads/" + repo["branch"])
    return files


def configure_plan(service):
    component = service.version_catalog()["repositories"][0]["components"][0]
    settings = service.status()["settings"]
    settings["repositories"][0]["versionPlans"] = [plan(component)]
    service.configure(settings)
    return component


def console_images():
    result = {
        "app-manifest.json": b'{"repository":"tx74666/CodexControlConsole","version":"1.0.105","untouched":"1.0.105"}\r\n',
        "app.js": b'const consoleUiVersion = "1.0.105";\r\nconst unrelated = "1.0.105";\r\n',
        "phone/version.json": b'\xef\xbb\xbf{ "version" : "1.0.105", "label": "keep" }\r\n',
    }
    for name in ("index.html", "music.html", "workspace.html"):
        refs = ('<link href="styles.css?v=console-resume-1.0.105-20261011">\r\n'
                '<script src="app.js?v=console-resume-1.0.105-20261011"></script>\r\n')
        if name == "index.html":
            refs += '<link href="console-repository-publish.css?v=console-repository-publish-1.0.105">\r\n<script src="console-repository-publish.js?v=console-repository-publish-1.0.105"></script>\r\n'
        result[name] = (refs + '<p>1.0.105 untouched</p>\r\n').encode()
    return result


def test_json_bom_crlf_preserved():
    raw = b'\xef\xbb\xbf{\r\n  "version" : "v1.02.003", "other": 5\r\n}\r\n'
    component, after = pure(raw)
    require(component["nextVersion"] == "v1.02.004")
    require(after == raw.replace(b"v1.02.003", b"v1.02.004"))


def test_same_json_two_independent_versions_single_patch():
    raw = b'{"plugins":{"A":{"version":"2.4.5"},"B":{"version":"8.1.0"}}}\n'
    sources = [source(key="plugins.A.version", name="A"), source(key="plugins.B.version", name="B")]
    items = versions.catalog(Path("."), sources, lambda path: raw)
    updates, plans = versions.prepare_updates(Path("."), sources, list(map(plan, items)), lambda path: raw)
    require(len(updates) == 1 and len(plans) == 2)
    require(base64.b64decode(updates[0]["afterBase64"]) == raw.replace(b"2.4.5", b"2.4.6").replace(b"8.1.0", b"8.1.1"))


def test_python_utf8_tuple_comments():
    raw = '\ufeffbl_info = {"中文": "例子", "version": (1, 2, 3), # keep\r\n "name": "Plugin"}\r\n'.encode()
    _, after = pure(raw, source("plugin.py", "python_ast", "bl_info.version"))
    require(after == raw.replace(b"(1, 2, 3)", b"(1, 2, 4)"))


def test_python_dynamic_dictionary_is_manual():
    for raw in (b'bl_info={"version":(1,2,3),**other}', b'bl_info={"version":(1,2,3),key:"unknown"}'):
        component = versions.catalog(Path("."), [source("plugin.py", "python_ast", "bl_info.version")], lambda path: raw)[0]
        require(not component["canBump"], component)


def test_json_invalid_or_duplicate_is_per_source_manual():
    for raw in (b"", b"{", b'{"version":', b'{"version":"1.2.3","version":"4.5.6"}', b'{"version":"1.2.3-beta"}'):
        component = versions.catalog(Path("."), [source()], lambda path: raw)[0]
        require(not component["canBump"], component)


def test_unity_xml_and_toml_scalar_preserved():
    for raw, item, old, new in (
        (b'  bundleVersion: 0.1.9\r\n  other: keep\r\n', source("ProjectSettings/ProjectSettings.asset", "unity", "bundleVersion"), b"0.1.9", b"0.1.10"),
        (b'<Project><Version> 1.2.3 </Version><Other>keep</Other></Project>\r\n', source("app.csproj", "xml", "Version"), b"1.2.3", b"1.2.4"),
        (b'name="plugin"\nversion = "1.2.3" # keep\n', source("blender_manifest.toml", "text", "version"), b"1.2.3", b"1.2.4"),
    ):
        _, after = pure(raw, item)
        require(after == raw.replace(old, new))


def test_toml_other_section_is_manual():
    raw = b'name="Example"\n[project]\nversion="1.2.3"\n'
    item = versions.catalog(Path("."), [source("version.toml", "text")], lambda path: raw)[0]
    require(not item["canBump"], item)


def test_console_six_files_and_precise_cache_tokens():
    images = console_images()
    component = versions.catalog(Path("."), [source("app-manifest.json", key="")], images.__getitem__)[0]
    require(len(component["expectedFiles"]) == 6)
    updates, _ = versions.prepare_updates(Path("."), [source("app-manifest.json", key="")], [plan(component)], images.__getitem__)
    for update in updates:
        result = base64.b64decode(update["afterBase64"])
        original = images[update["path"]]
        require(b"1.0.106" in result and result.count(b"\r\n") == original.count(b"\r\n"))
        if b"untouched" in original or b"unrelated" in original:
            require(b"1.0.105" in result)
        if original.startswith(b"\xef\xbb\xbf"):
            require(result.startswith(b"\xef\xbb\xbf"))


def test_console_companion_proof_stale_or_mismatch():
    images = console_images()
    authority = source("app-manifest.json")
    component = versions.catalog(Path("."), [authority], images.__getitem__)[0]
    images["app.js"] += b"// other modification\r\n"
    try:
        versions.prepare_updates(Path("."), [authority], [plan(component)], images.__getitem__)
    except versions.VersionPlanError:
        pass
    else:
        raise AssertionError("Changed companion accepted stale plan")
    images["app.js"] = images["app.js"].replace(b"1.0.105", b"1.0.104")
    require(not versions.catalog(Path("."), [authority], images.__getitem__)[0]["canBump"])


def test_blender_companion_requires_manual_coordination():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "blender_manifest.toml").write_text('version="1.2.3"')
        (root / "__init__.py").write_text('bl_info={"version":(1,2,3)}')
        items = versions.catalog(root, [source("__init__.py", "python_ast", "bl_info.version")], lambda path: (root / path).read_bytes())
        require(not items[0]["canBump"] and "blender_manifest" in items[0]["reason"])


def test_catalog_and_config_are_readonly_then_once_only_push():
    with Fixture() as f:
        root, remote, repo = f.repo()
        images = seed(f, root, repo)
        service = f.service()
        head = f.git(root, "rev-parse", "HEAD")
        index = (root / ".git/index").read_bytes()
        configure_plan(service)
        require((root / "app.json").read_bytes() == images["app.json"])
        require(f.git(root, "rev-parse", "HEAD") == head and (root / ".git/index").read_bytes() == index)
        require(not (root / ".git/FETCH_HEAD").exists())
        result = f.run(service)
        require(child(result)["status"] == "success" and child(result)["title"] == "1.2.4", result)
        require((root / "app.json").read_bytes() == images["app.json"].replace(b"1.2.3", b"1.2.4"))
        require(not service.status()["settings"]["repositories"][0]["versionPlans"])
        sha = f.git(root, "rev-parse", "HEAD")
        require(f.git(remote, "rev-parse", "main") == sha)
        require(service.run("request_00000001") == result)
        require(child(f.run(service, "request_00000002"))["status"] == "noop")
        require(f.git(root, "rev-parse", "HEAD") == sha)


def test_normal_push_does_not_increment():
    with Fixture() as f:
        root, _, repo = f.repo()
        images = seed(f, root, repo)
        (root / "tracked.txt").write_text("saved edit\n")
        result = f.run(f.service())
        require(child(result)["status"] == "success" and child(result)["title"] == "1.2.3", result)
        require((root / "app.json").read_bytes() == images["app.json"])


def test_planned_push_failure_retries_original_sha():
    class Fail(Service):
        def _git(self, root, *arguments, **kwargs):
            if arguments and arguments[0] == "push":
                raise module._GitFailure("permissions")
            return super()._git(root, *arguments, **kwargs)
    with Fixture() as f:
        root, remote, repo = f.repo()
        seed(f, root, repo)
        service = f.service(Fail)
        configure_plan(service)
        failed = f.run(service)
        sha = child(failed)["commitSha"]
        require(child(failed)["status"] == "push_failed" and sha, failed)
        require(not service.status()["settings"]["repositories"][0]["versionPlans"])
        result = f.run(f.service(), "request_00000002")
        require(child(result)["status"] == "success" and child(result)["commitSha"] == sha, result)
        require(f.git(root, "rev-list", "--count", "HEAD") == "3" and f.git(remote, "rev-parse", "main") == sha)
        require(b"1.2.4" in (root / "app.json").read_bytes())


def test_hook_rejection_resumes_same_version():
    with Fixture() as f:
        root, _, repo = f.repo()
        seed(f, root, repo)
        service = f.service()
        configure_plan(service)
        hooks(root, "pre-commit", "exit 1")
        failed = f.run(service)
        require(child(failed)["status"] == "deferred", failed)
        require(b"1.2.4" in (root / "app.json").read_bytes() and f.git(root, "rev-list", "--count", "HEAD") == "2")
        (root / ".git/hooks/pre-commit").unlink()
        resumed = f.run(f.service(), "request_00000002")
        require(child(resumed)["status"] == "success" and child(resumed)["title"] == "1.2.4", resumed)
        require(f.git(root, "rev-list", "--count", "HEAD") == "3")


def test_partial_staging_and_busy_preserve_version():
    for mode in ("staged", "busy"):
        with Fixture() as f:
            root, _, repo = f.repo()
            images = seed(f, root, repo)
            service = f.service(busy_check=(lambda root: "Codex 正在修改") if mode == "busy" else None)
            configure_plan(service)
            if mode == "staged":
                (root / "tracked.txt").write_text("partially selected\n")
                f.git(root, "add", "tracked.txt")
            index = (root / ".git/index").read_bytes()
            result = f.run(service)
            require(child(result)["status"] == "deferred", result)
            require((root / "app.json").read_bytes() == images["app.json"] and (root / ".git/index").read_bytes() == index)


def test_plan_excludes_sync_targets_and_private_paths():
    for mode in ("sync", "exclude", "readonly"):
        with Fixture() as f:
            root, _, repo = f.repo()
            seed(f, root, repo)
            if mode == "sync":
                external = f.base / "authority.json"
                external.write_bytes((root / "app.json").read_bytes())
                repo["syncFiles"] = [{"source": str(external), "target": "app.json"}]
            elif mode == "exclude":
                repo["exclude"] = ["app.json"]
            else:
                (root / "app.json").chmod(0o444)
            try:
                item = f.service().version_catalog()["repositories"][0]["components"][0]
                require(not item["canBump"], item)
            finally:
                (root / "app.json").chmod(0o666)


def test_console_partial_write_restart_continues_frozen_plan():
    class Interrupt(Service):
        def _version_intent_snapshot(self, repo, context, pending):
            current = super()._version_intent_snapshot(repo, context, pending)
            if any(module._stable(context[0] / entry["path"])["sha256"] == entry["afterSha256"] for entry in pending["versionUpdates"]):
                raise Error("fixture interruption after first file")
            return current
    with Fixture() as f:
        root, remote, repo = f.repo()
        images = seed(f, root, repo, console=True)
        service = f.service(Interrupt)
        configure_plan(service)
        failed = f.run(service)
        require(child(failed)["status"] == "deferred", failed)
        require(f.git(root, "rev-list", "--count", "HEAD") == "2")
        changed = [name for name in images if (root / name).read_bytes() != images[name]]
        require(len(changed) == 1, changed)
        result = f.run(f.service(), "request_00000002")
        require(child(result)["status"] == "success" and child(result)["title"] == "1.0.106", result)
        require(f.git(root, "rev-list", "--count", "HEAD") == "3" and f.git(remote, "rev-parse", "main") == child(result)["commitSha"])
        require(all(b"1.0.106" in (root / name).read_bytes() for name in images))


def test_staging_crash_resumes_version_intent():
    class Interrupt(Service):
        def _commit(self, repo, context, snapshot, pending, pending_path):
            marker = b"owned fixture marker"
            temporary = self.state_dir / "interrupted-index"
            temporary.write_bytes((context[1] / "index").read_bytes())
            (context[1] / "index.lock").write_bytes(marker)
            pending.update(state="staging", lockMarkerSha=module._sha(marker), temporaryIndex=str(temporary))
            module._atomic(pending_path, pending)
            raise Error("fixture stopped before commit dispatch")
    with Fixture() as f:
        root, _, repo = f.repo()
        seed(f, root, repo)
        service = f.service(Interrupt)
        configure_plan(service)
        failed = f.run(service)
        require(child(failed)["status"] == "deferred" and (root / ".git/index.lock").exists(), failed)
        resumed = f.run(f.service(), "request_00000002")
        require(child(resumed)["status"] == "success" and child(resumed)["title"] == "1.2.4", resumed)
        require(f.git(root, "rev-list", "--count", "HEAD") == "3")


def test_unknown_version_bytes_are_preserved_for_verification():
    class Interrupt(Service):
        def _apply_version_intent(self, repo, context, pending, pending_path):
            (context[0] / "app.json").write_bytes(b"user concurrent partial or edited bytes")
            return super()._apply_version_intent(repo, context, pending, pending_path)
    with Fixture() as f:
        root, _, repo = f.repo()
        seed(f, root, repo)
        service = f.service(Interrupt)
        configure_plan(service)
        failed = f.run(service)
        require(child(failed)["status"] == "deferred", failed)
        resumed = f.run(f.service(), "request_00000002")
        require(child(resumed)["status"] == "deferred", resumed)
        require((root / "app.json").read_bytes() == b"user concurrent partial or edited bytes")
        require(f.git(root, "rev-list", "--count", "HEAD") == "2")


def test_legacy104_pending_retry_survives_empty_plan_normalization():
    class Fail(Service):
        def _git(self, root, *arguments, **kwargs):
            if arguments and arguments[0] == "push":
                raise module._GitFailure("permissions")
            return super()._git(root, *arguments, **kwargs)
    with Fixture() as f:
        root, remote, _ = f.repo()
        (root / "tracked.txt").write_text("saved work\n")
        service = f.service(Fail)
        settings = service.status()["settings"]
        for row in settings["repositories"]:
            row.pop("versionPlans", None)
        module._atomic(service._settings_path, settings)
        failed = f.run(service)
        sha = child(failed)["commitSha"]
        pending = module._read(service._pending_path("one"))
        require(pending["repositorySettingsSha"] == module._json_sha(settings["repositories"][0]))
        service.configure(settings)
        result = f.run(f.service(), "request_00000002")
        require(child(result)["status"] == "success" and child(result)["commitSha"] == sha, result)
        require(f.git(remote, "rev-parse", "main") == sha)


def test_new_plan_survives_original_commit_retry():
    class Fail(Service):
        def _git(self, root, *arguments, **kwargs):
            if arguments and arguments[0] == "push":
                raise module._GitFailure("permissions")
            return super()._git(root, *arguments, **kwargs)
    with Fixture() as f:
        root, _, repo = f.repo()
        seed(f, root, repo)
        service = f.service(Fail)
        configure_plan(service)
        failed = f.run(service)
        sha = child(failed)["commitSha"]
        following = configure_plan(service)
        require(following["nextVersion"] == "1.2.5")
        restarted = f.service()
        result = f.run(restarted, "request_00000002")
        require(child(result)["status"] == "success" and child(result)["commitSha"] == sha, result)
        require(restarted.status()["settings"]["repositories"][0]["versionPlans"][0]["targetVersion"] == "1.2.5")
        require(b"1.2.4" in (root / "app.json").read_bytes())


def test_windows_version_write_lease_denies_writer_and_rename():
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    with tempfile.TemporaryDirectory() as directory:
        path, replacement = Path(directory) / "version.json", Path(directory) / "author-save.json"
        path.write_bytes(b'{"version":"1.2.3"}')
        replacement.write_bytes(b"external save")
        with module._version_write_lease(path) as stream:
            handle = kernel.CreateFileW(str(path), 0x40000000, 1 | 2 | 4, None, 3, 0, None)
            if handle != ctypes.c_void_p(-1).value:
                kernel.CloseHandle(handle)
                raise AssertionError("External write handle accepted while our exclusive writer is held")
            require(ctypes.get_last_error() in {32, 33})
            try:
                os.replace(replacement, path)
            except OSError:
                pass
            else:
                raise AssertionError("External atomic rename replaced held version file")
            require(stream.read() == b'{"version":"1.2.3"}')
            stream.seek(0)
            stream.write(b'{"version":"1.2.4"}')
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
        require(path.read_bytes() == b'{"version":"1.2.4"}' and replacement.read_bytes() == b"external save")


def test_plan_remote_ahead_defers_before_version_write():
    with Fixture() as f:
        root, remote, repo = f.repo()
        images = seed(f, root, repo)
        service = f.service()
        configure_plan(service)
        author = f.base / "remote-author"
        f.git(f.base, "clone", str(remote), str(author))
        f.git(author, "config", "user.name", "Remote fixture")
        f.git(author, "config", "user.email", "remote@invalid.local")
        (author / "tracked.txt").write_text("new remote work\n")
        f.git(author, "add", "tracked.txt")
        f.git(author, "commit", "-m", "remote ahead")
        f.git(author, "push", "origin", "main")
        result = f.run(service)
        require(child(result)["status"] == "deferred" and "远端" in child(result)["message"], result)
        require((root / "app.json").read_bytes() == images["app.json"] and f.git(root, "rev-list", "--count", "HEAD") == "2")


def test_special_index_version_flags_are_manual_before_write():
    for flag in ("--skip-worktree", "--assume-unchanged"):
        with Fixture() as f:
            root, _, repo = f.repo()
            images = seed(f, root, repo)
            f.git(root, "update-index", flag, "app.json")
            service = f.service()
            component = service.version_catalog()["repositories"][0]["components"][0]
            require(not component["canBump"] and "索引" in component["reason"], component)
            require((root / "app.json").read_bytes() == images["app.json"])


def test_version_plan_consume_cas_checks_binding_and_exact_plan():
    import threading
    with tempfile.TemporaryDirectory() as directory:
        dummy = Service.__new__(Service)
        dummy._mutex = threading.RLock()
        dummy.state_dir = Path(directory)
        dummy._settings_path = dummy.state_dir / "settings.json"
        used = {"sourceId":"same-source", "planProof":"before-proof"}
        base = {"id":"one", "path":"first-repository", "versionPlans":[used]}
        pending = {"versionPlans":[used], "commitSha":"created", "parentSha":"parent", "repositorySettingsSha":module._repo_settings_sha(base)}
        settings = {"repositories":[dict(base, path="different-repository")]}
        dummy._settings = lambda: settings
        dummy._consume_version_plans(base, pending)
        require(settings["repositories"][0]["versionPlans"] == [used] and not dummy._settings_path.exists())
        newer = dict(used, planProof="new-proof")
        settings["repositories"] = [dict(base, versionPlans=[newer])]
        dummy._consume_version_plans(base, pending)
        require(settings["repositories"][0]["versionPlans"] == [newer] and not dummy._settings_path.exists())
        settings["repositories"] = [copy.deepcopy(base)]
        dummy._consume_version_plans(base, pending)
        require(settings["repositories"][0]["versionPlans"] == [] and dummy._settings_path.exists())


def test_sync_source_authority_is_manual_and_never_rewritten():
    with Fixture() as f:
        root, _, repo = f.repo()
        images = seed(f, root, repo)
        repo["syncFiles"] = [{"source":str(root / "app.json"), "target":"saved-copy.json"}]
        service = f.service()
        item = service.version_catalog()["repositories"][0]["components"][0]
        require(not item["canBump"] and "同步来源" in item["reason"], item)
        require((root / "app.json").read_bytes() == images["app.json"] and not (root / "saved-copy.json").exists())


def test_single_authority_external_hardlink_defers_without_writes():
    with Fixture() as f:
        root, _, repo = f.repo()
        images = seed(f, root, repo)
        service = f.service()
        configure_plan(service)  # The authority was a normal single-link file.
        outside = f.base / "unconfigured-external-version.json"
        os.link(root / "app.json", outside)
        require((root / "app.json").stat().st_nlink == 2)
        component = service.version_catalog()["repositories"][0]["components"][0]
        require(not component["canBump"] and "重叠" in component["reason"], component)
        try:
            with module._version_write_lease(root / "app.json"):
                raise AssertionError("Write lease yielded for an unconfigured outside hardlink peer")
        except Error as exc:
            require("重叠" in str(exc), exc)
        result = f.run(service)
        require(child(result)["status"] == "deferred" and "重叠" in child(result)["message"], result)
        require((root / "app.json").read_bytes() == outside.read_bytes() == images["app.json"])
        require(f.git(root, "rev-list", "--count", "HEAD") == "2")
        require(service.status()["settings"]["repositories"][0]["versionPlans"][0]["targetVersion"] == "1.2.4")


def test_hardlinked_authorities_are_manual_but_same_file_keys_merge():
    with Fixture() as f:
        root, _, repo = f.repo()
        seed(f, root, repo)
        os.link(root / "app.json", root / "alias.json")
        f.git(root, "add", "alias.json")
        f.git(root, "commit", "-m", "hardlink authority fixture")
        repo["versionSources"].append(source("alias.json"))
        service = f.service()
        components = service.version_catalog()["repositories"][0]["components"]
        require(len(components) == 2 and all(not item["canBump"] and "重叠" in item["reason"] for item in components), components)
        require((root / "app.json").read_bytes() == (root / "alias.json").read_bytes())


TESTS = [item for name, item in tuple(globals().items()) if name.startswith("test_") and callable(item)]
if __name__ == "__main__":
    files = [ROOT / "console_repository_versions.py", ROOT / "console_repository_publish.py", Path(__file__)]
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    selected = [test for test in TESTS if not sys.argv[1:] or test.__name__ in sys.argv[1:]]
    require(not sys.argv[1:] or len(selected) == len(sys.argv[1:]), "Unknown test name")
    for test in selected:
        test()
        print("PASS " + test.__name__, flush=True)
    require(hashes == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}, "Source changed during tests")
    print(f"{len(selected)} explicit version checks PASS; real repositories untouched", flush=True)
    print(json.dumps(hashes, ensure_ascii=False), flush=True)
