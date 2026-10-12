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
    if console:
        (root / "console-repository-publish.js").write_bytes(b"// independent module\n")
        (root / "console-repository-publish.css").write_bytes(b".independent { color: white; }\n")
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


def save_edit(root):
    (root / "tracked.txt").write_text("saved implementation change\n")


def opt_out(service):
    settings = service.status()["settings"]
    settings["naming"]["autoBump"] = False
    service.configure(settings)


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
        require(b"1.1.0" in result and result.count(b"\r\n") == original.count(b"\r\n"))
        if update["path"] == "index.html":
            require(b"console-repository-publish-1.0.105" in result, "Independent module cache changed")
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
        (root / "blender_manifest.toml").write_text('version="1.2.4"')
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
        save_edit(root)
        result = f.run(service)
        require(child(result)["status"] == "success" and child(result)["title"] == "1.2.3 → 1.2.4", result)
        require((root / "app.json").read_bytes() == images["app.json"].replace(b"1.2.3", b"1.2.4"))
        require(not service.status()["settings"]["repositories"][0]["versionPlans"])
        sha = f.git(root, "rev-parse", "HEAD")
        require(f.git(remote, "rev-parse", "main") == sha)
        require(service.run("request_00000001") == result)
        require(child(f.run(service, "request_00000002"))["status"] == "noop")
        require(f.git(root, "rev-parse", "HEAD") == sha)


def test_opt_out_push_does_not_increment():
    with Fixture() as f:
        root, _, repo = f.repo()
        images = seed(f, root, repo)
        (root / "tracked.txt").write_text("saved edit\n")
        service = f.service()
        opt_out(service)
        result = f.run(service)
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
        save_edit(root)
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
        save_edit(root)
        hooks(root, "pre-commit", "exit 1")
        failed = f.run(service)
        require(child(failed)["status"] == "deferred", failed)
        require(b"1.2.4" in (root / "app.json").read_bytes() and f.git(root, "rev-list", "--count", "HEAD") == "2")
        (root / ".git/hooks/pre-commit").unlink()
        resumed = f.run(f.service(), "request_00000002")
        require(child(resumed)["status"] == "success" and child(resumed)["title"] == "1.2.3 → 1.2.4", resumed)
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
        save_edit(root)
        failed = f.run(service)
        require(child(failed)["status"] == "deferred", failed)
        require(f.git(root, "rev-list", "--count", "HEAD") == "2")
        changed = [name for name in images if (root / name).read_bytes() != images[name]]
        require(len(changed) == 1, changed)
        result = f.run(f.service(), "request_00000002")
        require(child(result)["status"] == "success" and child(result)["title"] == "1.0.105 → 1.1.0", result)
        require(f.git(root, "rev-list", "--count", "HEAD") == "3" and f.git(remote, "rev-parse", "main") == child(result)["commitSha"])
        require(all(b"1.1.0" in (root / name).read_bytes() for name in images))


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
        save_edit(root)
        failed = f.run(service)
        require(child(failed)["status"] == "deferred" and (root / ".git/index.lock").exists(), failed)
        resumed = f.run(f.service(), "request_00000002")
        require(child(resumed)["status"] == "success" and child(resumed)["title"] == "1.2.3 → 1.2.4", resumed)
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
        save_edit(root)
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
        save_edit(root)
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
        save_edit(root)
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
        save_edit(root)
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


def test_base100_carry_all_authority_formats_and_tuple_spans():
    for before, after in (("1.6.98", "1.6.99"), ("1.6.99", "1.7.0"), ("1.99.99", "2.0.0"),
                          ("v01.099.099", "v02.000.000")):
        require(versions.next_patch(before) == after)
    for raw, item, expected in (
        (b'{"version":"1.6.99","other":"1.6.99"}\r\n', source(), b'{"version":"1.7.0","other":"1.6.99"}\r\n'),
        (b'bundleVersion: 1.99.99 # keep\r\n', source("ProjectSettings.asset", "unity", "bundleVersion"),
         b'bundleVersion: 2.0.0 # keep\r\n'),
        (b'\xef\xbb\xbfbl_info = {"version": (1, # major\r\n 99, # minor\r\n 99), "name":"keep"}\r\n',
         source("plugin.py", "python_ast", "bl_info.version"),
         b'\xef\xbb\xbfbl_info = {"version": (2, # major\r\n 0, # minor\r\n 0), "name":"keep"}\r\n'),
        (b'bl_info = {"version": [1, 6, 99]}\n', source("plugin.py", "python_ast", "bl_info.version"),
         b'bl_info = {"version": [1, 7, 0]}\n')):
        _, actual = pure(raw, item)
        require(actual == expected, actual)


def test_console_independent_repository_cache_preserved():
    images = console_images()
    images["index.html"] = images["index.html"].replace(
        b"console-repository-publish-1.0.105", b"console-repository-publish-0.4.0")
    authority = source("app-manifest.json")
    component = versions.catalog(Path("."), [authority], images.__getitem__)[0]
    updates, _ = versions.prepare_updates(Path("."), [authority], [plan(component)], images.__getitem__)
    index = next(base64.b64decode(item["afterBase64"]) for item in updates if item["path"] == "index.html")
    require(b"console-repository-publish-0.4.0" in index and b"console-resume-1.1.0" in index)


def test_console_actual_resource_query_and_exact_evidence_cas():
    images = console_images()
    js, css = "console-repository-publish.js", "console-repository-publish.css"
    original = {js:b"// stable javascript\n", css:b".stable { color:white; }\n"}
    images.update(original)
    images[js] += b"// saved real change\n"
    authority = source("app-manifest.json")
    evidence = lambda name: ("a" * 40, original[name], name == js)
    component = versions.catalog(Path("."), [authority], images.__getitem__, console_reader=evidence)[0]
    require(len(component["expectedFiles"]) == 6 and len(component["consoleResourceEvidence"]) == 2)
    frozen = plan(component)
    updates, _ = versions.prepare_updates(Path("."), [authority], [frozen], images.__getitem__, console_reader=evidence)
    index = next(base64.b64decode(entry["afterBase64"]) for entry in updates if entry["path"] == "index.html")
    require(b'console-repository-publish.js?v=console-repository-publish-1.1.0' in index)
    require(b'console-repository-publish.css?v=console-repository-publish-1.0.105' in index)
    require(not {js, css} & {entry["path"] for entry in updates}, "Read evidence incorrectly wrote resources")
    images[js] += b"// later edit\n"
    try:
        versions.prepare_updates(Path("."), [authority], [frozen], images.__getitem__, console_reader=evidence)
    except versions.VersionPlanError:
        pass
    else:
        raise AssertionError("Changed resource bytes accepted frozen cache plan")
    images[js] = original[js] + b"// saved real change\n"
    try:
        versions.prepare_updates(Path("."), [authority], [frozen], images.__getitem__,
                                 console_reader=lambda name: ("b" * 40, original[name], name == js))
    except versions.VersionPlanError:
        pass
    else:
        raise AssertionError("Changed HEAD accepted resource cache proof")


def test_console_clean_windows_eol_preserves_query_and_exact_raw_proof():
    for git_changed in (False, True):
        images = console_images()
        js, css = "console-repository-publish.js", "console-repository-publish.css"
        original = {js:b"// stable\n", css:b".stable { color:white; }\n"}
        images.update({name:raw.replace(b"\n", b"\r\n") for name, raw in original.items()})
        authority = source("app-manifest.json")
        evidence = lambda name: ("a" * 40, original[name], git_changed)
        component = versions.catalog(Path("."), [authority], images.__getitem__, console_reader=evidence)[0]
        require(all(entry["changed"] is False for entry in component["consoleResourceEvidence"]), component)
        require(component["consoleResourceEvidence"][0]["expectedSha256"] == hashlib.sha256(images[js]).hexdigest())
        updates, _ = versions.prepare_updates(Path("."), [authority], [plan(component)], images.__getitem__, console_reader=evidence)
        index = next(base64.b64decode(entry["afterBase64"]) for entry in updates if entry["path"] == "index.html")
        require(index.count(b"console-repository-publish-1.0.105") == 2 and b"console-resume-1.1.0" in index)


def test_console_auto_changed_module_refreshes_only_its_query():
    with Fixture() as f:
        root, _, repo = f.repo()
        seed(f, root, repo, console=True)
        js = root / "console-repository-publish.js"
        js.write_bytes(js.read_bytes() + b"// saved real feature\n")
        service = f.service()
        preview = service.preview()["previews"][0]
        require(preview["title"] == "1.0.105 → 1.1.0" and preview["status"] == "ready", preview)
        result = f.run(service)
        require(child(result)["status"] == "success" and child(result)["title"] == preview["title"], result)
        index = (root / "index.html").read_bytes()
        require(b'console-repository-publish.js?v=console-repository-publish-1.1.0' in index)
        require(b'console-repository-publish.css?v=console-repository-publish-1.0.105' in index)
        require(js.read_bytes().endswith(b"// saved real feature\n"))
    with Fixture() as f:
        root, _, repo = f.repo()
        seed(f, root, repo, console=True)
        f.git(root, "config", "core.autocrlf", "true")
        for name in ("console-repository-publish.js", "console-repository-publish.css"):
            path = root / name
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        save_edit(root)
        result = f.run(f.service())
        require(child(result)["status"] == "success", result)
        require((root / "index.html").read_bytes().count(b"console-repository-publish-1.0.105") == 2)


def test_console_resource_changed_after_cache_intent_is_held():
    class Concurrent(Service):
        def _apply_version_intent(self, repo, context, pending, path):
            resource = context[0] / "console-repository-publish.css"
            resource.write_bytes(resource.read_bytes() + b"/* later user change */\n")
            return super()._apply_version_intent(repo, context, pending, path)
    with Fixture() as f:
        root, remote, repo = f.repo()
        images = seed(f, root, repo, console=True)
        save_edit(root)
        original_head = f.git(root, "rev-parse", "HEAD")
        failed = f.run(f.service(Concurrent))
        require(child(failed)["status"] == "deferred", failed)
        require((root / "app-manifest.json").read_bytes() == images["app-manifest.json"])
        require((root / "console-repository-publish.css").read_bytes().endswith(b"/* later user change */\n"))
        require(f.git(root, "rev-parse", "HEAD") == f.git(remote, "rev-parse", "main") == original_head)


def test_git_subject_history_strict_bounded_terminal_version():
    head, version_commit = "a" * 40, "b" * 40
    raw = head + "\0saved model\n" + version_commit + "\0 1.6.43 → 1.6.44 \n"
    evidence = versions.parse_commit_history(head, raw)
    require(evidence["currentVersion"] == "1.6.44" and evidence["historyDepth"] == 2)
    require(evidence["sourceHeadSha"] == head and evidence["versionCommitSha"] == version_commit)
    require(versions.parse_commit_history(head, head + "\0v1.6.99 -> v1.7.0\n")["version"] == "v1.7.0")
    for invalid in (head + "\0fix version 1.6.43\n", "b" * 40 + "\0" + "1.6.43\n",
                    head + "\0\0bad\n", "invalid\0" + "1.6.43\n",
                    "\n".join((head if i == 0 else "b" * 40) + "\0no version" for i in range(65))):
        try:
            versions.parse_commit_history(head, invalid)
        except versions.VersionPlanError:
            pass
        else:
            raise AssertionError("Ambiguous/unbounded Git version accepted")


def test_git_plan_binds_head_without_any_authority_file_update():
    authority = source("HEAD", "git_commit", "subject", "Git version", "**")
    evidence = versions.parse_commit_history("a" * 40, "a" * 40 + "\0" + "1.6.43\n")
    reader = lambda path: (_ for _ in ()).throw(AssertionError("Git plan read a fake version file"))
    component = versions.catalog(Path("."), [authority], reader, lambda source: evidence)[0]
    updates, proofs = versions.prepare_updates(Path("."), [authority], [plan(component)], reader, lambda source: evidence)
    require(updates == [] and proofs == [plan(component)] and component["expectedFiles"] == [])
    changed = dict(evidence, sourceHeadSha="b" * 40)
    try:
        versions.prepare_updates(Path("."), [authority], [plan(component)], reader, lambda source: changed)
    except versions.VersionPlanError:
        pass
    else:
        raise AssertionError("Changed Git HEAD accepted old version plan")


def git_seed(f, root, repo, version="1.6.43"):
    unity = root / "ProjectSettings/ProjectSettings.asset"
    unity.parent.mkdir()
    unity.write_bytes(b"bundleVersion: 0.1.0\r\n")
    f.git(root, "add", "ProjectSettings/ProjectSettings.asset")
    f.git(root, "commit", "-m", version)
    f.git(root, "push", "origin", "HEAD:refs/heads/" + repo["branch"])
    repo["versionSources"] = [source("HEAD", "git_commit", "subject", "Random Realm", "**")]
    return unity


def test_git_plan_summary_real_commit_and_once_only_retry():
    class Fail(Service):
        def _git(self, root, *arguments, **kwargs):
            if arguments and arguments[0] == "push":
                raise module._GitFailure("permissions")
            return super()._git(root, *arguments, **kwargs)
    with Fixture() as f:
        root, remote, repo = f.repo()
        unity = git_seed(f, root, repo)
        service = f.service(Fail)
        configure_plan(service)
        (root / "tracked.txt").write_text("saved work\n")
        preview = service.preview()["previews"][0]
        require(preview["title"] == "1.6.43 → 1.6.44" and preview["planWillApply"] is True, preview)
        failed = f.run(service)
        sha = child(failed)["commitSha"]
        require(child(failed)["status"] == "push_failed" and sha, failed)
        require(f.git(root, "show", "-s", "--format=%s", "HEAD") == "1.6.43 → 1.6.44")
        require(unity.read_bytes() == b"bundleVersion: 0.1.0\r\n")
        resumed = f.run(f.service(), "request_00000002")
        require(child(resumed)["status"] == "success" and child(resumed)["commitSha"] == sha, resumed)
        require(f.git(remote, "rev-parse", "main") == sha and f.git(root, "rev-list", "--count", "HEAD") == "3")
        require(f.service().version_catalog()["repositories"][0]["components"][0]["currentVersion"] == "1.6.44")


def test_git_plan_no_changes_no_empty_commit_and_push_only_retains_plan():
    with Fixture() as f:
        root, remote, repo = f.repo()
        git_seed(f, root, repo)
        service = f.service()
        configure_plan(service)
        old = f.git(root, "rev-parse", "HEAD")
        result = f.run(service)
        require(child(result)["status"] == "noop" and f.git(root, "rev-parse", "HEAD") == old, result)
        require(service.status()["settings"]["repositories"][0]["versionPlans"])
        (root / "tracked.txt").write_text("already committed work\n")
        f.git(root, "commit", "-am", "existing exact original title")
        sha = f.git(root, "rev-parse", "HEAD")
        preview = service.preview()["previews"][0]
        require(preview["action"] == "push_only" and preview["planWillApply"] is False, preview)
        require(preview["title"] == "existing exact original title" and not preview["versionTransitions"], preview)
        pushed = f.run(service, "request_00000002")
        require(child(pushed)["status"] == "success" and child(pushed)["commitSha"] == sha, pushed)
        require(child(pushed)["title"] == "existing exact original title" and f.git(remote, "rev-parse", "main") == sha)
        require(service.status()["settings"]["repositories"][0]["versionPlans"])


def test_catalog_real_dirty_ahead_and_version_delta_are_distinct_readonly():
    with Fixture() as f:
        root, _, repo = f.repo()
        images = seed(f, root, repo)
        service = f.service()
        opt_out(service)
        clean = service.version_catalog()["repositories"][0]
        require(clean["hasChanges"] is False and clean["versionChanged"] is False, clean)
        (root / "tracked.txt").write_text("saved implementation only\n")
        index = (root / ".git/index").read_bytes()
        files = (root / "app.json").read_bytes()
        dirty = service.version_catalog()["repositories"][0]
        require(dirty["hasChanges"] is True and dirty["versionChanged"] is False, dirty)
        preview = service.preview()["previews"][0]
        require(preview["title"] == "1.2.3" and "版本未变" in preview["body"], preview)
        require((root / ".git/index").read_bytes() == index and (root / "app.json").read_bytes() == files)
        (root / "app.json").write_bytes(images["app.json"].replace(b"1.2.3", b"1.2.4"))
        changed = service.version_catalog()["repositories"][0]
        component = changed["components"][0]
        require(changed["hasChanges"] is True and component["versionChanged"] is True, changed)
        require(component["headVersion"] == "1.2.3" and component["currentVersion"] == "1.2.4")
        require(component["transition"] == {"kind":"working", "fromVersion":"1.2.3", "toVersion":"1.2.4"})
        f.git(root, "add", ".")
        f.git(root, "commit", "-m", "saved local commit")
        ahead = service.version_catalog()["repositories"][0]
        require(ahead["worktreeChanged"] is False and ahead["outgoingCommits"] == 1 and ahead["hasChanges"] is True, ahead)


def test_git_source_without_clear_subject_is_unknown_not_unity_fallback():
    with Fixture() as f:
        root, _, repo = f.repo()
        repo["versionSources"] = [source("HEAD", "git_commit", "subject", "Random Realm", "**")]
        (root / "package.json").write_text('{"version":"0.1.0"}')
        catalog = f.service().version_catalog()["repositories"][0]
        component = catalog["components"][0]
        require(component["currentVersion"] == "" and component["canBump"] is False, catalog)
        require(component["versionChanged"] is None and component["planState"] == "none")


def test_default_auto_saved_change_preview_readonly_then_once():
    with Fixture() as f:
        root, remote, repo = f.repo()
        images = seed(f, root, repo)
        service = f.service()
        require(service.status()["settings"]["naming"]["autoBump"] is True)
        save_edit(root)
        head, index = f.git(root, "rev-parse", "HEAD"), (root / ".git/index").read_bytes()
        row = service.version_catalog()["repositories"][0]
        component = row["components"][0]
        require(row["hasChanges"] is True and component["versionChanged"] is False)
        require(component["autoPlan"]["state"] == "eligible" and component["autoPlan"]["targetVersion"] == "1.2.4", row)
        require(component["transition"] == {"kind":"auto", "fromVersion":"1.2.3", "toVersion":"1.2.4"})
        preview = service.preview()["previews"][0]
        require(preview["title"] == "1.2.3 → 1.2.4" and preview["planWillApply"] is True, preview)
        require(preview["versionTransitions"][0]["kind"] == "auto" and "有改动自动升版" in preview["body"])
        require((root / "app.json").read_bytes() == images["app.json"] and (root / ".git/index").read_bytes() == index)
        require(f.git(root, "rev-parse", "HEAD") == head and not service.status()["settings"]["repositories"][0]["versionPlans"])
        result = f.run(service)
        sha = child(result)["commitSha"]
        require(child(result)["status"] == "success" and child(result)["title"] == preview["title"], result)
        require(f.git(remote, "rev-parse", "main") == sha and f.git(root, "rev-list", "--count", "HEAD") == "3")
        require((root / "app.json").read_bytes() == images["app.json"].replace(b"1.2.3", b"1.2.4"))
        confirmed = service.version_catalog()["repositories"][0]
        require(confirmed["hasChanges"] is False and confirmed["outgoingCommits"] == 0, confirmed)
        require(confirmed["outgoingBaselineSource"] == "verified_delivery" and confirmed["outgoingBaselineSha"] == sha)
        require(f.git(root, "rev-parse", "origin/main") == head, "Delivery status changed user tracking ref")
        require(service.run("request_00000001") == result)
        require(child(f.run(service, "request_00000002"))["status"] == "noop")
        require(f.git(root, "rev-parse", "HEAD") == sha and b"1.2.5" not in (root / "app.json").read_bytes())


def test_auto_carry_double_rollover_and_manual_version_preserved():
    for current, target in (("1.6.99", "1.7.0"), ("1.99.99", "2.0.0")):
        with Fixture() as f:
            root, _, repo = f.repo()
            seed(f, root, repo)
            (root / "app.json").write_text(json.dumps({"version":current}))
            f.git(root, "commit", "-am", "source version fixture")
            f.git(root, "push", "origin", "main")
            save_edit(root)
            result = f.run(f.service())
            require(child(result)["status"] == "success" and child(result)["title"] == current + " → " + target, result)
            require(json.loads((root / "app.json").read_text())["version"] == target)
    with Fixture() as f:
        root, _, repo = f.repo()
        images = seed(f, root, repo)
        manually_saved = images["app.json"].replace(b"1.2.3", b"1.2.4")
        (root / "app.json").write_bytes(manually_saved)
        save_edit(root)
        service = f.service()
        component = service.version_catalog()["repositories"][0]["components"][0]
        require(component["versionChanged"] is True and component["autoPlan"]["state"] == "manual_version")
        result = f.run(service)
        require(child(result)["status"] == "success" and child(result)["title"] == "1.2.3 → 1.2.4", result)
        require((root / "app.json").read_bytes() == manually_saved and "已手动改变" in child(result)["body"])


def test_auto_new_authority_retains_initial_and_known_unknown_defers():
    with Fixture() as f:
        root, _, repo = f.repo()
        raw = b'\xef\xbb\xbf{"version":"0.4.0","keep":true}\r\n'
        (root / "app.json").write_bytes(raw)
        repo["versionSources"] = [source()]
        service = f.service()
        component = service.version_catalog()["repositories"][0]["components"][0]
        require(component["headSourceMissing"] is True and component["autoPlan"]["state"] == "initial_version", component)
        result = f.run(service)
        require(child(result)["status"] == "success" and child(result)["title"] == "0.4.0", result)
        require((root / "app.json").read_bytes() == raw)
    with Fixture() as f:
        root, remote, repo = f.repo()
        images = seed(f, root, repo)
        original = f.git(remote, "rev-parse", "main")
        (root / "app.json").write_bytes(b'{"version":"unconfirmed"}')
        save_edit(root)
        result = f.run(f.service())
        require(child(result)["status"] == "deferred" and "自动升版" in child(result)["message"], result)
        require(f.git(remote, "rev-parse", "main") == original and f.git(root, "rev-list", "--count", "HEAD") == "2")
        require((root / "app.json").read_bytes() == b'{"version":"unconfirmed"}')


def test_auto_independent_component_scopes_and_fallback_title():
    for preset in ("version", "module_version"):
        with Fixture() as f:
            root, _, repo = f.repo()
            for name, version in (("a", "1.6.99"), ("b", "2.4.8")):
                (root / name).mkdir()
                (root / name / "package.json").write_text(json.dumps({"version":version}))
                (root / name / "module.txt").write_text("base\n")
            f.git(root, "add", ".")
            f.git(root, "commit", "-m", "modules fixture")
            f.git(root, "push", "origin", "main")
            repo["versionSources"] = [source(name + "/package.json", name=name.upper(), scope=name) for name in ("a", "b")]
            service = f.service()
            settings = service.status()["settings"]
            settings["naming"].update(preset=preset, fallbackTitle="Exact fallback")
            service.configure(settings)
            (root / "a/module.txt").write_text("saved A\n")
            rows = service.version_catalog()["repositories"][0]["components"]
            require(rows[0]["autoPlan"]["state"] == "eligible" and rows[1]["autoPlan"]["state"] == "none", rows)
            (root / "b/module.txt").write_text("saved B\n")
            preview = service.preview()["previews"][0]
            require(preview["title"] == ("Exact fallback" if preset == "version" else "A 1.6.99 → 1.7.0 / B 2.4.8 → 2.4.9"), preview)
            require("A 1.6.99 → 1.7.0" in preview["body"] and "B 2.4.8 → 2.4.9" in preview["body"])
            result = f.run(service)
            require(child(result)["status"] == "success" and child(result)["title"] == preview["title"], result)
            require(json.loads((root / "a/package.json").read_text())["version"] == "1.7.0")
            require(json.loads((root / "b/package.json").read_text())["version"] == "2.4.9")


def test_auto_shared_json_carrier_does_not_bump_unchanged_component():
    with Fixture() as f:
        root, _, repo = f.repo()
        raw = b'{"plugins":{"A":{"version":"1.2.3"},"B":{"version":"8.1.0"}}}\r\n'
        (root / "versions.json").write_bytes(raw)
        for name in ("a", "b"):
            (root / name).mkdir()
            (root / name / "module.txt").write_text("base\n")
        f.git(root, "add", ".")
        f.git(root, "commit", "-m", "shared authority fixture")
        f.git(root, "push", "origin", "main")
        repo["versionSources"] = [source("versions.json", key="plugins.A.version", name="A", scope="a"),
                                  source("versions.json", key="plugins.B.version", name="B", scope="b")]
        (root / "versions.json").write_bytes(raw.replace(b"1.2.3", b"1.2.4"))
        service = f.service()
        components = service.version_catalog()["repositories"][0]["components"]
        require(components[0]["autoPlan"]["state"] == "manual_version", components)
        require(components[1]["autoPlan"]["state"] == "none" and components[1]["currentVersion"] == "8.1.0")
        preview = service.preview()["previews"][0]
        require(preview["title"] == "1.2.3 → 1.2.4" and "A 1.2.3 → 1.2.4" in preview["body"], preview)
        require("B 8.1.0 →" not in preview["body"])
        result = f.run(service)
        require(child(result)["status"] == "success", result)
        require((root / "versions.json").read_bytes() == raw.replace(b"1.2.3", b"1.2.4"))
        (root / "b/module.txt").write_text("saved B implementation\n")
        next_preview = service.preview()["previews"][0]
        require(next_preview["title"] == "8.1.0 → 8.1.1", next_preview)
        following = f.run(service, "request_00000002")
        require(child(following)["status"] == "success" and child(following)["title"] == next_preview["title"], following)
        values = json.loads((root / "versions.json").read_text())
        require(values["plugins"]["A"]["version"] == "1.2.4" and values["plugins"]["B"]["version"] == "8.1.1")


def test_auto_git_subject_and_push_only_file_plan_retained():
    with Fixture() as f:
        root, _, repo = f.repo()
        unity = git_seed(f, root, repo, "1.6.99")
        save_edit(root)
        service = f.service()
        require(service.version_catalog()["repositories"][0]["components"][0]["autoPlan"]["targetVersion"] == "1.7.0")
        result = f.run(service)
        require(child(result)["status"] == "success" and child(result)["title"] == "1.6.99 → 1.7.0", result)
        require(unity.read_bytes() == b"bundleVersion: 0.1.0\r\n")
        require(service.version_catalog()["repositories"][0]["components"][0]["currentVersion"] == "1.7.0")
    with Fixture() as f:
        root, remote, repo = f.repo()
        images = seed(f, root, repo)
        service = f.service()
        configure_plan(service)
        save_edit(root)
        f.git(root, "commit", "-am", "Original existing title")
        sha = f.git(root, "rev-parse", "HEAD")
        preview = service.preview()["previews"][0]
        require(preview["action"] == "push_only" and preview["planWillApply"] is False, preview)
        require(preview["title"] == "Original existing title" and preview["versionTransitions"] == [])
        result = f.run(service)
        require(child(result)["status"] == "success" and child(result)["commitSha"] == sha, result)
        require(f.git(remote, "rev-parse", "main") == sha and (root / "app.json").read_bytes() == images["app.json"])
        require(service.status()["settings"]["repositories"][0]["versionPlans"][0]["targetVersion"] == "1.2.4")


def test_auto_saved_sync_first_and_failure_preserves_authority():
    for missing in (False, True):
        with Fixture() as f:
            root, _, repo = f.repo()
            images = seed(f, root, repo)
            outside = f.base / "Builder6.blend"
            if not missing:
                outside.write_bytes(b"BLENDER saved fixture")
            repo["syncFiles"] = [{"source":str(outside), "target":"Build.blend"}]
            service = f.service()
            preview = service.preview()["previews"][0]
            require(preview["action"] == "sync_pending" and preview["planWillApply"] is None, preview)
            require(preview["components"][0]["autoPlan"]["state"] == "sync_pending")
            require(preview["versionTransitions"] == [] and (root / "app.json").read_bytes() == images["app.json"])
            catalog = service.version_catalog()["repositories"][0]
            if missing:
                require(catalog["syncChanged"] is None and catalog["hasChanges"] is None and catalog["changeState"] == "unknown", catalog)
            else:
                require(catalog["syncChanged"] is True and catalog["hasChanges"] is True and catalog["worktreeChanged"] is False, catalog)
                require(catalog["syncDifferences"] == ["Build.blend"] and not (root / "Build.blend").exists())
            result = f.run(service)
            if missing:
                require(child(result)["status"] == "deferred" and not (root / "Build.blend").exists(), result)
                require((root / "app.json").read_bytes() == images["app.json"] and f.git(root, "rev-list", "--count", "HEAD") == "2")
            else:
                require(child(result)["status"] == "success" and child(result)["title"] == "1.2.3 → 1.2.4", result)
                require((root / "Build.blend").read_bytes() == outside.read_bytes() and b"1.2.4" in (root / "app.json").read_bytes())
                unchanged = service.version_catalog()["repositories"][0]
                require(unchanged["syncChanged"] is False and unchanged["hasChanges"] is False, unchanged)


def test_missing_version_model_is_normal_fallback_not_read_failure():
    with Fixture() as f:
        root, _, _ = f.repo()
        save_edit(root)
        service = f.service()
        catalog = service.version_catalog()["repositories"][0]
        require(catalog["versionState"] == "missing" and catalog["components"] == [] and catalog["hasChanges"] is True, catalog)
        result = f.run(service)
        require(child(result)["status"] == "success" and child(result)["title"].startswith("更新进度"), result)
        require(not (root / "app-manifest.json").exists() and not (root / "package.json").exists())


def test_auto_unknown_push_restart_preserves_exact_commit_and_target():
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
        root, remote, repo = f.repo()
        seed(f, root, repo)
        save_edit(root)
        first = f.run(f.service(Unknown))
        sha = child(first)["commitSha"]
        require(child(first)["status"] == "verification_required" and sha, first)
        pending = module._read(f.base / "state/pending/one.json")
        require(pending["automaticSourceIds"] and pending["versionPlans"][0]["targetVersion"] == "1.2.4", pending)
        (root / "tracked.txt").write_text("later unrelated work\n")
        result = f.run(f.service(), "request_00000002")
        require(child(result)["status"] == "success" and child(result)["commitSha"] == sha, result)
        require(f.git(remote, "rev-parse", "main") == sha and f.git(root, "rev-list", "--count", "HEAD") == "3")
        require(b"1.2.4" in (root / "app.json").read_bytes() and b"1.2.5" not in (root / "app.json").read_bytes())
        require((root / "tracked.txt").read_text() == "later unrelated work\n")


def test_auto_lfs_failure_retries_frozen_version_commit():
    class LfsFail(Service):
        def _git(self, root, *arguments, **kwargs):
            if arguments and arguments[0] == "push":
                raise module._GitFailure("lfs")
            return super()._git(root, *arguments, **kwargs)
    with Fixture() as f:
        root, remote, repo = f.repo()
        seed(f, root, repo)
        (root / "saved.fbx").write_bytes(b"FBX saved fixture")
        failed = f.run(f.service(LfsFail))
        sha = child(failed)["commitSha"]
        require(child(failed)["status"] == "push_failed" and "LFS" in child(failed)["message"] and sha, failed)
        require(b"1.2.4" in (root / "app.json").read_bytes())
        result = f.run(f.service(), "request_00000002")
        require(child(result)["status"] == "success" and child(result)["commitSha"] == sha, result)
        require(f.git(remote, "rev-parse", "main") == sha and f.git(root, "rev-list", "--count", "HEAD") == "3")
        require(b"1.2.5" not in (root / "app.json").read_bytes())


def test_auto_precommit_resume_partial_staging_merge_and_unknown_head_guard():
    with Fixture() as f:
        root, _, repo = f.repo()
        seed(f, root, repo)
        save_edit(root)
        hooks(root, "pre-commit", "exit 1")
        failed = f.run(f.service())
        require(child(failed)["status"] == "deferred" and b"1.2.4" in (root / "app.json").read_bytes(), failed)
        (root / ".git/hooks/pre-commit").unlink()
        result = f.run(f.service(), "request_00000002")
        require(child(result)["status"] == "success" and child(result)["title"] == "1.2.3 → 1.2.4", result)
        require(b"1.2.5" not in (root / "app.json").read_bytes() and f.git(root, "rev-list", "--count", "HEAD") == "3")
    for guard in ("staged", "merge", "unknown_head"):
        with Fixture() as f:
            root, remote, repo = f.repo()
            images = seed(f, root, repo)
            saved = images["app.json"]
            if guard == "unknown_head":
                (root / "app.json").write_bytes(b'{"version":"unknown"}')
                f.git(root, "commit", "-am", "unreadable authority history")
                saved = images["app.json"]
                (root / "app.json").write_bytes(saved)
            save_edit(root)
            if guard == "staged":
                f.git(root, "add", "tracked.txt")
                (root / "tracked.txt").write_text("partial unstaged remainder\n")
            elif guard == "merge":
                (root / ".git/MERGE_HEAD").write_text(f.git(root, "rev-parse", "HEAD") + "\n")
            index = (root / ".git/index").read_bytes()
            remote_head = f.git(remote, "rev-parse", "main")
            result = f.run(f.service())
            require(child(result)["status"] == "deferred", result)
            require((root / "app.json").read_bytes() == saved and (root / ".git/index").read_bytes() == index)
            require(f.git(remote, "rev-parse", "main") == remote_head)


def test_settings_cas_preserves_concurrent_choices_and_stale_migration():
    with Fixture() as f:
        root, _, repo = f.repo()
        seed(f, root, repo)
        service = f.service()
        before = service.status()
        migrated = copy.deepcopy(before["settings"])
        migrated["repositories"][0]["versionSources"] = [source("HEAD", "git_commit", "subject", "New authority", "**")]
        concurrent = copy.deepcopy(before["settings"])
        concurrent["naming"].update(autoBump=False, notes="user concurrent saved note")
        concurrent["repositories"][0]["enabled"] = False
        service.configure(concurrent, expected_settings_sha=before["settingsSha"])
        saved = service._settings_path.read_bytes()
        index, head = (root / ".git/index").read_bytes(), f.git(root, "rev-parse", "HEAD")
        try:
            service.configure(migrated, expected_settings_sha=before["settingsSha"])
        except Error as exc:
            require(exc.code == "settings_changed" and "另一处" in str(exc) and "不覆盖" in str(exc), exc)
        else:
            raise AssertionError("Stale migration overwrote concurrently saved choices")
        require(service._settings_path.read_bytes() == saved)
        require((root / ".git/index").read_bytes() == index and f.git(root, "rev-parse", "HEAD") == head)
        require(service.status()["settings"]["naming"]["autoBump"] is False)
        require(service.status()["settingsSha"] != before["settingsSha"])
        for invalid in ("", "not-a-sha", False):
            try:
                service.configure(migrated, expected_settings_sha=invalid)
            except Error:
                pass
            else:
                raise AssertionError("Invalid configuration CAS accepted")
            require(service._settings_path.read_bytes() == saved)


def test_sealed_settings_reject_legacy_overwrite_but_allow_exact_noop():
    with Fixture() as f:
        root, _, repo = f.repo()
        seed(f, root, repo)
        service = f.service()
        before = service.status()
        require(before["casRequired"] is False)
        legacy = copy.deepcopy(before["settings"])
        selected = copy.deepcopy(before["settings"])
        selected["naming"].update(notes="current user choice", autoBump=False)
        selected["repositories"][0]["enabled"] = False
        service.configure(selected, expected_settings_sha=before["settingsSha"])
        sealed = service.status()
        require(sealed["casRequired"] is True and sealed["settings"]["casRequired"] is True)
        raw = service._settings_path.read_bytes()
        legacy["casRequired"] = False  # Untrusted metadata cannot unseal configuration.
        try:
            service.configure(legacy)
        except Error as exc:
            require(exc.code == "settings_changed" and "不覆盖" in str(exc), exc)
        else:
            raise AssertionError("Legacy unsealed draft overwrote sealed settings")
        require(service._settings_path.read_bytes() == raw)
        noop = copy.deepcopy(sealed["settings"])
        noop["casRequired"] = False
        service.configure(noop)
        require(service._settings_path.read_bytes() == raw and service.status()["casRequired"] is True)
        changed = copy.deepcopy(sealed["settings"])
        changed["naming"]["notes"] = "new acknowledged choice"
        changed["casRequired"] = False
        service.configure(changed, expected_settings_sha=sealed["settingsSha"])
        require(service.status()["casRequired"] is True and service.status()["settings"]["naming"]["notes"] == "new acknowledged choice")
        restarted = f.service()
        require(restarted.status()["casRequired"] is True)
        try:
            restarted.configure(legacy)
        except Error as exc:
            require(exc.code == "settings_changed", exc)
        else:
            raise AssertionError("Restart removed server-owned CAS protection")
    with Fixture() as f:
        root, _, repo = f.repo()
        seed(f, root, repo)
        service = f.service()
        settings = service.status()["settings"]
        settings["naming"]["notes"] = "fresh legacy caller remains compatible"
        settings["casRequired"] = True  # A client also cannot manufacture the server seal.
        service.configure(settings)
        require(service.status()["casRequired"] is False)


def test_legacy_status_normalized_sha_and_raw_opaque_bytes_preserved():
    with Fixture() as f:
        root, _, repo = f.repo()
        seed(f, root, repo)
        service = f.service()
        legacy = service.status()["settings"]
        legacy["repositories"][0].pop("versionPlans", None)
        legacy["naming"].pop("autoBump", None)
        legacy["opaqueLocalMarker"] = {"preserve":"legacy server metadata"}
        module._atomic(service._settings_path, legacy)
        raw = service._settings_path.read_bytes()
        restarted = f.service()
        status = restarted.status()
        require(status["settings"] == legacy and status["settings"]["opaqueLocalMarker"] == legacy["opaqueLocalMarker"])
        require(status["normalizedSettings"]["naming"]["autoBump"] is True)
        require(status["normalizedSettings"]["repositories"][0]["versionPlans"] == [])
        require(status["settingsSha"] == module._json_sha(status["normalizedSettings"]))
        require(status["settingsSha"] != module._json_sha(status["settings"]))
        require(service._settings_path.read_bytes() == raw and status["casRequired"] is False)
        save_edit(root)
        result = f.run(restarted)
        require(child(result)["status"] == "success" and child(result)["title"] == "1.2.3 → 1.2.4", result)
        require(service._settings_path.read_bytes() == raw, "Automatic plan normalized away legacy server metadata")


def blender_pair(root, version="1.0.99"):
    directory = root / "plugin"
    directory.mkdir()
    values = ", ".join(version.split("."))
    py = ('\ufeffraise RuntimeError("never import project")\r\nbl_info = {"name":"Keep", "version": (' + values + '), # keep tuple\r\n "other": 17}\r\n').encode()
    toml = ('\ufeffid = "language_switcher"\r\nversion = "' + version + '" # keep scalar\r\nname = "Keep"\r\n').encode()
    (directory / "__init__.py").write_bytes(py)
    (directory / "blender_manifest.toml").write_bytes(toml)
    return {"plugin/__init__.py":py, "plugin/blender_manifest.toml":toml}


def pair_source(manifest=False):
    return source("plugin/blender_manifest.toml", "text", "version", "Language-Switcher", "plugin") if manifest else source(
        "plugin/__init__.py", "python_ast", "bl_info.version", "Language-Switcher", "plugin")


def test_blender_pair_two_authorities_exact_text_and_proofs():
    for manifest in (False, True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images = blender_pair(root)
            authority = pair_source(manifest)
            reader = lambda name: (root / name).read_bytes()
            component = versions.catalog(root, [authority], reader)[0]
            require(component["canBump"] and component["companionState"] == "paired" and len(component["expectedFiles"]) == 2, component)
            updates, _ = versions.prepare_updates(root, [authority], [plan(component)], reader)
            results = {entry["path"]:base64.b64decode(entry["afterBase64"]) for entry in updates}
            require(results["plugin/__init__.py"] == images["plugin/__init__.py"].replace(b"(1, 0, 99)", b"(1, 1, 0)"))
            require(results["plugin/blender_manifest.toml"] == images["plugin/blender_manifest.toml"].replace(b"1.0.99", b"1.1.0"))
            for name, raw in images.items():
                require((root / name).read_bytes() == raw, "Pure paired plan wrote a project file")
            (root / "plugin/blender_manifest.toml").write_bytes(images["plugin/blender_manifest.toml"] + b"# user edited companion\r\n")
            try:
                versions.prepare_updates(root, [authority], [plan(component)], reader)
            except versions.VersionPlanError:
                pass
            else:
                raise AssertionError("Changed companion raw bytes accepted original paired proof")


def test_blender_duplicate_pair_sources_and_ambiguous_declarations_hold():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        images = blender_pair(root)
        sources = [pair_source(), pair_source(True)]
        reader = lambda name: (root / name).read_bytes()
        singles = [versions.catalog(root, [item], reader)[0] for item in sources]
        duplicate = versions.catalog(root, sources, reader)
        require(all(not item["canBump"] and item["companionState"] == "blocked" and "重复" in item["reason"] for item in duplicate), duplicate)
        try:
            versions.prepare_updates(root, sources, list(map(plan, singles)), reader)
        except versions.VersionPlanError as exc:
            require("重叠" in str(exc), exc)
        else:
            raise AssertionError("Duplicate component authority plans merged silently")
        (root / "plugin/blender_manifest.toml").write_bytes(images["plugin/blender_manifest.toml"] + b'version="1.0.99"\r\n')
        component = versions.catalog(root, [pair_source()], reader)[0]
        require(not component["canBump"] and component["companionState"] == "blocked", component)
        malformed = images["plugin/blender_manifest.toml"] + b'malformed_other_field = [\r\n'
        (root / "plugin/blender_manifest.toml").write_bytes(malformed)
        for authority in (pair_source(), pair_source(True)):
            component = versions.catalog(root, [authority], reader)[0]
            require(not component["canBump"] and component["companionState"] == "blocked", component)
            require((root / "plugin/blender_manifest.toml").read_bytes() == malformed)


def test_blender_pair_auto_and_manual_saved_versions_preserved():
    for manifest, manual in ((False, False), (True, False), (False, True), (True, True)):
        with Fixture() as f:
            root, remote, repo = f.repo()
            images = blender_pair(root)
            repo["versionSources"] = [pair_source(manifest)]
            f.git(root, "add", ".")
            f.git(root, "commit", "-m", "dual-version plugin fixture")
            f.git(root, "push", "origin", "main")
            if manual:
                (root / "plugin/__init__.py").write_bytes(images["plugin/__init__.py"].replace(b"(1, 0, 99)", b"(1, 1, 0)"))
                (root / "plugin/blender_manifest.toml").write_bytes(images["plugin/blender_manifest.toml"].replace(b"1.0.99", b"1.1.0"))
            (root / "plugin/behavior.py").write_text("# saved real module change\n")
            service = f.service()
            component = service.version_catalog()["repositories"][0]["components"][0]
            require(component["autoPlan"]["state"] == ("manual_version" if manual else "eligible"), component)
            result = f.run(service)
            require(child(result)["status"] == "success" and child(result)["title"] == "1.0.99 → 1.1.0", result)
            require((root / "plugin/__init__.py").read_bytes() == images["plugin/__init__.py"].replace(b"(1, 0, 99)", b"(1, 1, 0)"))
            require((root / "plugin/blender_manifest.toml").read_bytes() == images["plugin/blender_manifest.toml"].replace(b"1.0.99", b"1.1.0"))
            require(f.git(remote, "rev-parse", "main") == child(result)["commitSha"] and f.git(root, "rev-list", "--count", "HEAD") == "3")


def test_blender_pair_mismatch_or_missing_companion_defers_without_writes():
    for missing in (False, True):
        with Fixture() as f:
            root, remote, repo = f.repo()
            images = blender_pair(root)
            repo["versionSources"] = [pair_source()]
            f.git(root, "add", ".")
            f.git(root, "commit", "-m", "dual-version plugin fixture")
            f.git(root, "push", "origin", "main")
            old_head = f.git(root, "rev-parse", "HEAD")
            # Manual authority change must not bypass an inconsistent companion.
            saved = images["plugin/__init__.py"].replace(b"(1, 0, 99)", b"(1, 1, 0)")
            (root / "plugin/__init__.py").write_bytes(saved)
            if missing:
                (root / "plugin/blender_manifest.toml").unlink()
            (root / "plugin/behavior.py").write_text("# saved real change\n")
            result = f.run(f.service())
            require(child(result)["status"] == "deferred" and "版本" in child(result)["message"], result)
            require((root / "plugin/__init__.py").read_bytes() == saved and f.git(root, "rev-parse", "HEAD") == old_head)
            require(f.git(remote, "rev-parse", "main") == old_head)
            if not missing:
                require((root / "plugin/blender_manifest.toml").read_bytes() == images["plugin/blender_manifest.toml"])


def test_blender_pair_partial_write_restart_and_concurrent_companion_hold():
    class Interrupt(Service):
        def _version_intent_snapshot(self, repo, context, pending):
            result = super()._version_intent_snapshot(repo, context, pending)
            if any(module._stable(context[0] / update["path"])["sha256"] == update["afterSha256"] for update in pending["versionUpdates"]):
                raise Error("fixture interruption after first paired version write")
            return result
    class Concurrent(Service):
        def _apply_version_intent(self, repo, context, pending, path):
            (context[0] / "plugin/blender_manifest.toml").write_bytes(b'user concurrent companion bytes\r\n')
            return super()._apply_version_intent(repo, context, pending, path)
    for race in (False, True):
        with Fixture() as f:
            root, _, repo = f.repo()
            images = blender_pair(root)
            repo["versionSources"] = [pair_source()]
            f.git(root, "add", ".")
            f.git(root, "commit", "-m", "dual-version plugin fixture")
            f.git(root, "push", "origin", "main")
            (root / "plugin/behavior.py").write_text("# saved module change\n")
            failed = f.run(f.service(Concurrent if race else Interrupt))
            require(child(failed)["status"] == "deferred" and f.git(root, "rev-list", "--count", "HEAD") == "2", failed)
            resumed = f.run(f.service(), "request_00000002")
            if race:
                require(child(resumed)["status"] == "deferred", resumed)
                require((root / "plugin/blender_manifest.toml").read_bytes() == b'user concurrent companion bytes\r\n')
                require((root / "plugin/__init__.py").read_bytes() == images["plugin/__init__.py"])
            else:
                require(child(resumed)["status"] == "success" and child(resumed)["title"] == "1.0.99 → 1.1.0", resumed)
                require(f.git(root, "rev-list", "--count", "HEAD") == "3")


def test_manual_hidden_primary_and_paired_companion_versions_hold():
    for guard in ("primary_exclude", "primary_skip", "companion_assume"):
        with Fixture() as f:
            root, remote, repo = f.repo()
            images = blender_pair(root)
            repo["versionSources"] = [pair_source()]
            f.git(root, "add", ".")
            f.git(root, "commit", "-m", "paired version fixture")
            f.git(root, "push", "origin", "main")
            py = images["plugin/__init__.py"].replace(b"(1, 0, 99)", b"(1, 1, 0)")
            toml = images["plugin/blender_manifest.toml"].replace(b"1.0.99", b"1.1.0")
            (root / "plugin/__init__.py").write_bytes(py)
            (root / "plugin/blender_manifest.toml").write_bytes(toml)
            (root / "plugin/behavior.py").write_text("# real changed module\n")
            if guard == "primary_exclude":
                repo["exclude"] = ["plugin/__init__.py"]
            else:
                f.git(root, "update-index", "--skip-worktree" if guard == "primary_skip" else "--assume-unchanged",
                      "plugin/__init__.py" if guard == "primary_skip" else "plugin/blender_manifest.toml")
            index = (root / ".git/index").read_bytes()
            head = f.git(root, "rev-parse", "HEAD")
            result = f.run(f.service())
            require(child(result)["status"] == "deferred" and "未进入实际" in child(result)["message"], result)
            require((root / ".git/index").read_bytes() == index and f.git(root, "rev-parse", "HEAD") == head)
            require(f.git(remote, "rev-parse", "main") == head)
            require((root / "plugin/__init__.py").read_bytes() == py and (root / "plugin/blender_manifest.toml").read_bytes() == toml)


def test_hidden_initial_authority_is_not_claimed_as_committed():
    with Fixture() as f:
        root, remote, repo = f.repo()
        raw = b'\xef\xbb\xbf{"version":"0.4.0","keep":true}\r\n'
        (root / "app.json").write_bytes(raw)
        repo["versionSources"] = [source()]
        repo["exclude"] = ["app.json"]
        save_edit(root)
        index, head = (root / ".git/index").read_bytes(), f.git(root, "rev-parse", "HEAD")
        result = f.run(f.service())
        require(child(result)["status"] == "deferred" and "未进入实际" in child(result)["message"], result)
        require((root / "app.json").read_bytes() == raw and (root / ".git/index").read_bytes() == index)
        require(f.git(root, "rev-parse", "HEAD") == f.git(remote, "rev-parse", "main") == head)


TESTS = [item for name, item in tuple(globals().items()) if name.startswith("test_") and callable(item)]
if __name__ == "__main__":
    files = [ROOT / "console_repository_versions.py", ROOT / "console_repository_publish.py", Path(__file__),
             ROOT / "tools/check-console-repository-publish.py"]
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    selected = [test for test in TESTS if not sys.argv[1:] or test.__name__ in sys.argv[1:]]
    require(not sys.argv[1:] or len(selected) == len(sys.argv[1:]), "Unknown test name")
    for test in selected:
        test()
        print("PASS " + test.__name__, flush=True)
    require(hashes == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}, "Source changed during tests")
    print(f"{len(selected)} repository version checks PASS; real repositories untouched", flush=True)
    print(json.dumps(hashes, ensure_ascii=False), flush=True)
