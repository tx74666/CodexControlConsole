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
        images = seed(f, root, repo)
        os.link(root / "app.json", root / "alias.json")
        f.git(root, "add", "alias.json")
        f.git(root, "commit", "-m", "hardlink authority fixture")
        repo["versionSources"].append(source("alias.json"))
        service = f.service()
        original_head = f.git(root, "rev-parse", "HEAD")
        original_index = (root / ".git" / "index").read_bytes()
        components = service.version_catalog()["repositories"][0]["components"]
        file_authorities = [item for item in components if item["path"] in {"app.json", "alias.json"}]
        repository_versions = [item for item in components if item.get("repositoryVersion") is True]
        require(len(components) == 3 and len(file_authorities) == 2 and
                {item["path"] for item in file_authorities} == {"app.json", "alias.json"}, components)
        require(all(not item["canBump"] and "重叠" in item["reason"] for item in file_authorities), file_authorities)
        require(len(repository_versions) == 1, components)
        main = repository_versions[0]
        require(main["path"] == "HEAD" and main["kind"] == "git_commit" and main["key"] == "subject" and
                main["initialVersion"] is True and main["versionOrigin"] == "git_commit_initial" and
                main["currentVersion"] == main["nextVersion"] == "1.0.0" and main["canBump"] is True and
                main["versionCommitSha"] == "" and main["versionSubject"] == "" and
                main["sourceHeadSha"] == original_head and main["autoPlan"]["state"] == "none", main)
        require((root / "app.json").stat().st_ino == (root / "alias.json").stat().st_ino and
                (root / "app.json").stat().st_nlink == 2)
        require((root / "app.json").read_bytes() == (root / "alias.json").read_bytes() == images["app.json"])
        require(f.git(root, "rev-parse", "HEAD") == original_head and
                (root / ".git" / "index").read_bytes() == original_index)


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


def test_saved_snapshot_git_only_plan_commits_latest_saved_files():
    class SaveDuringPlan(Service):
        def _apply_version_intent(self, repo, context, pending, pending_path):
            require(pending["versionUpdates"] == [], "Git-subject plan must not write a version file")
            (context[0] / "tracked.txt").write_text("latest saved implementation\n")
            (context[0] / "new.txt").write_text("saved after the version plan\n")
            return super()._apply_version_intent(repo, context, pending, pending_path)
    with Fixture() as f:
        root, remote, repo = f.repo()
        unity = git_seed(f, root, repo)
        service = f.service(SaveDuringPlan)
        configure_plan(service)
        save_edit(root)
        result = f.run(service)
        item = child(result)
        require(item["status"] == "success" and item["title"] == "1.6.43 → 1.6.44", result)
        require(f.git(remote, "show", "main:tracked.txt") == "latest saved implementation")
        require(f.git(remote, "show", "main:new.txt") == "saved after the version plan")
        require(f.git(remote, "rev-parse", "main") == item["commitSha"])
        require(f.git(root, "rev-list", "--count", "HEAD") == "3" and unity.read_bytes() == b"bundleVersion: 0.1.0\r\n")


def test_saved_snapshot_file_plan_refreshes_work_after_version_write():
    class SaveDuringPlan(Service):
        saved_after_version = False
        def _apply_version_intent(self, repo, context, pending, pending_path):
            (context[0] / "tracked.txt").write_text("saved while preparing version\n")
            return super()._apply_version_intent(repo, context, pending, pending_path)
        def _version_intent_snapshot(self, repo, context, pending):
            current = super()._version_intent_snapshot(repo, context, pending)
            if not self.saved_after_version and any(
                    module._stable(context[0] / update["path"])["sha256"] == update["afterSha256"]
                    for update in pending["versionUpdates"]):
                self.saved_after_version = True
                (context[0] / "tracked.txt").write_text("latest saved after version write\n")
                (context[0] / "new.txt").write_text("new saved work\n")
            return current
    with Fixture() as f:
        root, remote, repo = f.repo()
        images = seed(f, root, repo)
        service = f.service(SaveDuringPlan)
        configure_plan(service)
        save_edit(root)
        result = f.run(service)
        item = child(result)
        require(item["status"] == "success" and item["title"] == "1.2.3 → 1.2.4", result)
        require(service.saved_after_version, "Fixture did not save during the real version write")
        require((root / "app.json").read_bytes() == images["app.json"].replace(b"1.2.3", b"1.2.4"))
        require(f.git(remote, "show", "main:tracked.txt") == "latest saved after version write")
        require(f.git(remote, "show", "main:new.txt") == "new saved work")
        require(f.git(root, "rev-list", "--count", "HEAD") == "3" and f.git(remote, "rev-parse", "main") == item["commitSha"])


def test_strict_version_plan_still_holds_changed_other_files():
    class SaveDuringPlan(Service):
        def _apply_version_intent(self, repo, context, pending, pending_path):
            (context[0] / "tracked.txt").write_text("new work outside the strict plan\n")
            return super()._apply_version_intent(repo, context, pending, pending_path)
    for git_only in (False, True):
        with Fixture() as f:
            root, remote, repo = f.repo()
            images = None if git_only else seed(f, root, repo)
            if git_only:
                git_seed(f, root, repo)
            service = f.service(SaveDuringPlan)
            configure_plan(service)
            settings = service.status()["settings"]
            settings["naming"]["allowActiveWork"] = False
            service.configure(settings)
            save_edit(root)
            head, index = f.git(root, "rev-parse", "HEAD"), (root / ".git/index").read_bytes()
            result = f.run(service)
            require(child(result)["status"] == "deferred" and "其他工作文件发生变化" in child(result)["message"], result)
            require(f.git(root, "rev-parse", "HEAD") == f.git(remote, "rev-parse", "main") == head)
            require((root / ".git/index").read_bytes() == index)
            require((root / "tracked.txt").read_text() == "new work outside the strict plan\n")
            if images:
                require((root / "app.json").read_bytes() == images["app.json"])


def test_saved_snapshot_version_path_change_still_preserves_user_bytes():
    class ConcurrentVersion(Service):
        def _apply_version_intent(self, repo, context, pending, pending_path):
            (context[0] / "tracked.txt").write_text("allowed ordinary saved work\n")
            (context[0] / "app.json").write_bytes(b'{"version":"9.9.9","user":"concurrent"}\n')
            return super()._apply_version_intent(repo, context, pending, pending_path)
    with Fixture() as f:
        root, remote, repo = f.repo()
        seed(f, root, repo)
        service = f.service(ConcurrentVersion)
        configure_plan(service)
        save_edit(root)
        head, index = f.git(root, "rev-parse", "HEAD"), (root / ".git/index").read_bytes()
        result = f.run(service)
        require(child(result)["status"] == "deferred" and "版本文件出现其他修改" in child(result)["message"], result)
        require((root / "app.json").read_bytes() == b'{"version":"9.9.9","user":"concurrent"}\n')
        require((root / ".git/index").read_bytes() == index)
        require(f.git(root, "rev-parse", "HEAD") == f.git(remote, "rev-parse", "main") == head)
        resumed = f.run(f.service(), "request_00000002")
        require(child(resumed)["status"] == "deferred" and (root / "app.json").read_bytes() == b'{"version":"9.9.9","user":"concurrent"}\n', resumed)


def test_saved_snapshot_resumed_plan_keeps_one_version_and_request_identity():
    class InterruptAfterVersion(Service):
        def _version_intent_snapshot(self, repo, context, pending):
            current = super()._version_intent_snapshot(repo, context, pending)
            if any(module._stable(context[0] / update["path"])["sha256"] == update["afterSha256"]
                   for update in pending["versionUpdates"]):
                raise Error("fixture interruption after the original version write")
            return current
    with Fixture() as f:
        root, remote, repo = f.repo()
        images = seed(f, root, repo)
        service = f.service(InterruptAfterVersion)
        configure_plan(service)
        save_edit(root)
        first = f.run(service)
        require(child(first)["status"] == "deferred", first)
        pending_path = service._pending_path(repo["id"])
        pending = module._read(pending_path)
        require(pending["state"] == "version_applying" and len(pending["versionPlans"]) == 1, pending)
        version_bytes = images["app.json"].replace(b"1.2.3", b"1.2.4")
        require((root / "app.json").read_bytes() == version_bytes)
        (root / "tracked.txt").write_text("saved after interrupted version preparation\n")
        (root / "new.txt").write_text("retained later work\n")
        resumed_service = f.service()
        resumed = f.run(resumed_service, "request_00000002")
        item = child(resumed)
        require(item["status"] == "success" and item["title"] == "1.2.3 → 1.2.4", resumed)
        require((root / "app.json").read_bytes() == version_bytes and f.git(root, "rev-list", "--count", "HEAD") == "3")
        require(f.git(remote, "show", "main:tracked.txt") == "saved after interrupted version preparation")
        require(f.git(remote, "show", "main:new.txt") == "retained later work")
        require(f.git(remote, "rev-parse", "main") == item["commitSha"])
        require(resumed_service.run("request_00000001") == first and resumed_service.run("request_00000002") == resumed)
        require((root / "app.json").read_bytes() == version_bytes and f.git(root, "rev-parse", "HEAD") == item["commitSha"])
        require(child(f.run(resumed_service, "request_00000003"))["status"] == "noop")
        require(f.git(root, "rev-list", "--count", "HEAD") == "3" and (root / "app.json").read_bytes() == version_bytes)


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
        raw = b'\xef\xbb\xbf{"version":"1.4.0","keep":true}\r\n'
        (root / "app.json").write_bytes(raw)
        repo["versionSources"] = [source()]
        service = f.service()
        component = service.version_catalog()["repositories"][0]["components"][0]
        require(component["headSourceMissing"] is True and component["autoPlan"]["state"] == "initial_version", component)
        result = f.run(service)
        require(child(result)["status"] == "success" and child(result)["title"] == "1.4.0", result)
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
            require(preview["title"] == "1.0.0" and preview["repositoryVersion"]["state"] == "initial", preview)
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
        require(preview["title"] == "1.0.0" and "A 1.2.3 → 1.2.4" in preview["body"], preview)
        require("B 8.1.0 →" not in preview["body"])
        result = f.run(service)
        require(child(result)["status"] == "success", result)
        require((root / "versions.json").read_bytes() == raw.replace(b"1.2.3", b"1.2.4"))
        (root / "b/module.txt").write_text("saved B implementation\n")
        next_preview = service.preview()["previews"][0]
        require(next_preview["title"] == "1.0.0 → 1.0.1" and "B 8.1.0 → 8.1.1" in next_preview["body"], next_preview)
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
        require(catalog["versionState"] == "known" and len(catalog["components"]) == 1 and catalog["hasChanges"] is True, catalog)
        require(catalog["repositoryVersion"]["state"] == "initial" and catalog["repositoryVersion"]["currentVersion"] == "1.0.0", catalog)
        result = f.run(service)
        require(child(result)["status"] == "success" and child(result)["title"] == "1.0.0", result)
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


def application_sources():
    return [source("app-manifest.json", "json", "version", "Application", "**"),
            source("package.json", "json", "version", "Package", "**")]


def application_images(version="0.4.0"):
    manifest = ('\ufeff{\r\n  "repository": "tx74666/CodexWorldConsole",\r\n'
                '  "version" : "' + version + '",\r\n  "description": "保存原文 0.4.0"\r\n}\r\n').encode("utf-8")
    package = ('\ufeff{\r\n  "name": "codex-world-console",\r\n  "version" : "' + version + '",\r\n'
               '  "private": true,\r\n  "dependencies": {"fixture-tool": "0.4.0"},\r\n'
               '  "description": "keep 0.4.0"\r\n}\r\n').encode("utf-8")
    lock = ('\ufeff{\r\n  "name": "codex-world-console",\r\n  "version" : "' + version + '",\r\n'
            '  "lockfileVersion": 3,\r\n  "requires": true,\r\n  "packages": {\r\n'
            '    "": {"name": "codex-world-console", "version": "' + version + '", '
            '"dependencies": {"fixture-tool": "0.4.0"}},\r\n'
            '    "node_modules/fixture-tool": {"version": "0.4.0", "integrity": "sha512-fixture"}\r\n'
            '  }\r\n}\r\n').encode("utf-8")
    return {"app-manifest.json": manifest, "package.json": package, "package-lock.json": lock}


def application_after(images, current, target):
    root_old = ('"version" : "' + current + '"').encode("ascii")
    root_new = ('"version" : "' + target + '"').encode("ascii")
    result = {name: raw.replace(root_old, root_new, 1) for name, raw in images.items()}
    result["package-lock.json"] = result["package-lock.json"].replace(
        ('"version": "' + current + '"').encode("ascii"), ('"version": "' + target + '"').encode("ascii"), 1)
    return result


def application_contract(sources, images, *, head_files=None, head_sha=None, changed=None, participates=None):
    primary, package = sources
    paths = ("app-manifest.json", "package.json", "package-lock.json")
    evidence = {"sourceId": versions.source_id(primary), "packageSource": copy.deepcopy(package),
                "repository": "tx74666/CodexWorldConsole", "testMode": False,
                "headSha": head_sha or "a" * 40,
                "headFiles": copy.deepcopy(images if head_files is None else head_files),
                "gitChanged": {name: False for name in paths} if changed is None else dict(changed),
                "participates": {name: True for name in paths} if participates is None else dict(participates)}
    def read(item):
        return copy.deepcopy(evidence) if item.get("path") == "app-manifest.json" else None
    return read, evidence


def application_component(items, primary=None):
    primary = primary or application_sources()[0]
    rows = [item for item in items if item["sourceId"] == versions.source_id(primary)]
    require(len(rows) == 1, items)
    return rows[0]


def application_seed(f, root, repo, version="0.4.0", commit=True):
    images = application_images(version)
    repo["versionSources"] = application_sources()
    for name, raw in images.items():
        (root / name).write_bytes(raw)
    if commit:
        f.git(root, "add", ".")
        f.git(root, "commit", "-m", "application companion fixture")
        f.git(root, "push", "origin", "HEAD:refs/heads/" + repo["branch"])
    return images


def require_application_images(root, expected):
    require({name: (root / name).read_bytes() for name in expected} == expected,
            "Application root declarations or unrelated dependency bytes changed")


def test_application_root_companions_exact_three_file_plan_and_single_authority():
    for current, target, reverse in (("0.4.0", "0.4.1", False), ("1.6.99", "1.7.0", True), ("1.99.99", "2.0.0", False)):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources, images = application_sources(), application_images(current)
            contract, _ = application_contract(sources, images)
            configured = list(reversed(sources)) if reverse else sources
            items = versions.catalog(root, configured, images.__getitem__, application_reader=contract)
            require(len(items) == 1, "Root package was presented as an independent application version")
            component = application_component(items)
            require(component["canBump"] and component["currentVersion"] == current and component["nextVersion"] == target, component)
            paths = [entry["path"] for entry in component["expectedFiles"]]
            require(len(paths) == len(set(paths)) == 3 and set(paths) == set(images), component)
            original = copy.deepcopy(images)
            updates, proofs = versions.prepare_updates(root, configured, [plan(component)], images.__getitem__, application_reader=contract)
            require(len(updates) == 3 and len(proofs) == 1, updates)
            actual = {entry["path"]: base64.b64decode(entry["afterBase64"]) for entry in updates}
            require(actual == application_after(images, current, target), actual)
            require(images == original, "Pure application plan mutated its reader data")
            lock = json.loads(actual["package-lock.json"].decode("utf-8-sig"))
            package = json.loads(actual["package.json"].decode("utf-8-sig"))
            require(lock["version"] == lock["packages"][""]["version"] == package["version"] == target)
            require(lock["packages"]["node_modules/fixture-tool"]["version"] == "0.4.0")
            require(lock["packages"][""]["dependencies"]["fixture-tool"] == package["dependencies"]["fixture-tool"] == "0.4.0")
            for name, raw in actual.items():
                require(raw.startswith(b"\xef\xbb\xbf") and raw.count(b"\r\n") == images[name].count(b"\r\n"), name)


def test_application_pair_requires_explicit_contract_and_attested_project_identity():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        sources, images = application_sources(), application_images()
        reads = []
        def reader(name):
            reads.append(name)
            return images[name]
        ordinary = versions.catalog(root, sources, reader)
        require(len(ordinary) == 2 and all(len(item["expectedFiles"]) == 1 for item in ordinary), ordinary)
        require("package-lock.json" not in reads, "Unconfigured application contract inferred a lock-file owner")
        updates, _ = versions.prepare_updates(root, sources, [plan(ordinary[0])], reader)
        require([entry["path"] for entry in updates] == ["app-manifest.json"])
        for invalid in ("manifest_repository", "package_name", "lock_name", "lock_package_name", "scope", "source_id", "ambiguous"):
            working = copy.deepcopy(images)
            contract, evidence = application_contract(sources, images)
            if invalid == "manifest_repository":
                working["app-manifest.json"] = working["app-manifest.json"].replace(b"tx74666/CodexWorldConsole", b"other-owner/CodexWorldConsole")
            elif invalid == "package_name":
                working["package.json"] = working["package.json"].replace(b"codex-world-console", b"another-application")
            elif invalid == "lock_name":
                working["package-lock.json"] = working["package-lock.json"].replace(b"codex-world-console", b"another-application", 1)
            elif invalid == "lock_package_name":
                working["package-lock.json"] = working["package-lock.json"].replace(
                    b'"": {"name": "codex-world-console"', b'"": {"name": "another-application"')
            elif invalid == "scope":
                evidence["packageSource"]["scope"] = "unrelated-module"
            elif invalid == "ambiguous":
                evidence["ambiguous"] = True
            else:
                evidence["sourceId"] = "not-the-configured-authority"
            items = versions.catalog(root, sources, working.__getitem__, application_reader=contract)
            component = application_component(items)
            if invalid == "package_name":
                require(len(items) == 2 and all(len(item["expectedFiles"]) == 1 for item in items), items)
                require(component["canBump"], "Different application names were silently coupled")
                updates, _ = versions.prepare_updates(root, sources, [plan(component)], working.__getitem__, application_reader=contract)
                require([entry["path"] for entry in updates] == ["app-manifest.json"])
                continue
            require(not component["canBump"] and component["companionState"] == "blocked", (invalid, component))
            require(working != images if invalid in {"manifest_repository", "package_name", "lock_name", "lock_package_name"} else working == images)


def test_application_companion_source_cannot_be_planned_as_an_independent_component():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        sources, images = application_sources(), application_images()
        contract, _ = application_contract(sources, images)
        primary = application_component(versions.catalog(root, sources, images.__getitem__, application_reader=contract))
        independent_package = versions.catalog(root, [sources[1]], images.__getitem__)[0]
        for invalid in (False, True):
            working = copy.deepcopy(images)
            if invalid:
                working["package-lock.json"] += b" malformed current lock JSON"
            for plans in ([plan(independent_package)], [plan(primary), plan(independent_package)]):
                try:
                    versions.prepare_updates(root, sources, plans, working.__getitem__, application_reader=contract)
                except versions.VersionPlanError:
                    pass
                else:
                    raise AssertionError("Root package companion accepted a separate version plan")


def test_application_missing_malformed_duplicate_and_partial_versions_block_the_whole_pair():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        sources, images = application_sources(), application_images()
        for name in images:
            for invalid in ("missing", "malformed", "duplicate", "manual_partial"):
                working = copy.deepcopy(images)
                if invalid == "missing":
                    working.pop(name)
                elif invalid == "malformed":
                    working[name] += b" incomplete JSON trailing text"
                elif invalid == "duplicate":
                    working[name] = working[name].replace(b"{\r\n", b'{\r\n  "version": "0.4.0",\r\n', 1)
                else:
                    working[name] = working[name].replace(b'"version" : "0.4.0"', b'"version" : "0.4.1"', 1)
                contract, _ = application_contract(sources, images)
                before = copy.deepcopy(working)
                component = application_component(versions.catalog(root, sources, working.__getitem__, application_reader=contract))
                require(not component["canBump"] and component["companionState"] == "blocked", (name, invalid, component))
                require(working == before, "Rejected application inspection changed the supplied file data")
        working = copy.deepcopy(images)
        working["package-lock.json"] = working["package-lock.json"].replace(b'"version": "0.4.0"', b'"version": "0.4.1"', 1)
        contract, _ = application_contract(sources, images)
        component = application_component(versions.catalog(root, sources, working.__getitem__, application_reader=contract))
        require(not component["canBump"] and component["companionState"] == "blocked", component)


def test_application_plan_proof_binds_each_companion_raw_bytes_and_fixed_head():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        sources, images = application_sources(), application_images()
        contract, evidence = application_contract(sources, images)
        component = application_component(versions.catalog(root, sources, images.__getitem__, application_reader=contract))
        original_plan = plan(component)
        for name in images:
            working = copy.deepcopy(images)
            working[name] += b"\r\n"
            try:
                versions.prepare_updates(root, sources, [original_plan], working.__getitem__, application_reader=contract)
            except versions.VersionPlanError:
                pass
            else:
                raise AssertionError("Changed application companion bytes accepted an old plan: " + name)
            require(working[name] == images[name] + b"\r\n", "CAS rejection replaced user bytes")
        evidence["headSha"] = "b" * 40
        try:
            versions.prepare_updates(root, sources, [original_plan], images.__getitem__, application_reader=contract)
        except versions.VersionPlanError:
            pass
        else:
            raise AssertionError("Application plan did not bind its fixed HEAD evidence")


def test_application_changed_or_initial_versions_require_all_three_actual_participants():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        sources, original = application_sources(), application_images()
        working = application_after(original, "0.4.0", "0.4.1")
        for initial in (False, True):
            for hidden in original:
                participation = {name: name != hidden for name in original}
                changed = {name: True for name in original}
                head = {name: None for name in original} if initial else original
                contract, _ = application_contract(sources, working, head_files=head, changed=changed, participates=participation)
                component = application_component(versions.catalog(root, sources, working.__getitem__, application_reader=contract))
                require(not component["canBump"] and component["companionState"] == "blocked", (initial, hidden, component))
                require(working == application_after(original, "0.4.0", "0.4.1"))


def test_application_fixed_head_requires_matching_history_or_attested_new_members():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        sources, images = application_sources(), application_images()
        cases = []
        for name in images:
            missing = copy.deepcopy(images)
            missing[name] = None
            cases.append((name + " new member without actual Git change", missing))
            malformed = copy.deepcopy(images)
            malformed[name] += b" incomplete HEAD JSON"
            cases.append((name + " malformed", malformed))
            mismatched = copy.deepcopy(images)
            mismatched[name] = mismatched[name].replace(b'"version" : "0.4.0"', b'"version" : "0.4.1"', 1)
            cases.append((name + " mismatch", mismatched))
        cases.append(("all initial without actual Git changes", {name: None for name in images}))
        partial_lock = copy.deepcopy(images)
        partial_lock["package-lock.json"] = partial_lock["package-lock.json"].replace(b'"version": "0.4.0"', b'"version": "0.4.1"', 1)
        cases.append(("HEAD lock empty-package partial", partial_lock))
        for label, head in cases:
            contract, _ = application_contract(sources, images, head_files=head)
            component = application_component(versions.catalog(root, sources, images.__getitem__, application_reader=contract))
            require(not component["canBump"] and component["companionState"] == "blocked", (label, component))
            require(images == application_images(), "Rejected historical evidence changed working declaration data")


def test_application_new_members_are_allowed_only_with_actual_git_change_evidence():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        sources, images = application_sources(), application_images()
        for initial in (False, True):
            head = {name: None for name in images} if initial else dict(images)
            if not initial:
                head["package-lock.json"] = None
            changes = {name: head[name] is None for name in images}
            contract, _ = application_contract(sources, images, head_files=head, changed=changes)
            component = application_component(versions.catalog(root, sources, images.__getitem__, application_reader=contract))
            require(component["canBump"] and len(component["expectedFiles"]) == 3, (initial, component))
            updates, _ = versions.prepare_updates(root, sources, [plan(component)], images.__getitem__, application_reader=contract)
            require({entry["path"] for entry in updates} == set(images))
            require(images == application_images(), "Read-only attestation wrote new application declarations")


def test_application_root_pair_keeps_independent_nested_module_versions():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        sources, images = application_sources(), application_images()
        module_source = source("plugins/example/package.json", "json", "version", "Independent plugin", "plugins/example")
        images[module_source["path"]] = b'{"name":"independent-plugin","version":"7.2.9"}\r\n'
        contract, _ = application_contract(sources, {name: raw for name, raw in images.items() if name != module_source["path"]})
        configured = sources + [module_source]
        items = versions.catalog(root, configured, images.__getitem__, application_reader=contract)
        require(len(items) == 2, items)
        independent = [item for item in items if item["sourceId"] == versions.source_id(module_source)][0]
        require(independent["currentVersion"] == "7.2.9" and len(independent["expectedFiles"]) == 1, independent)
        updates, _ = versions.prepare_updates(root, configured, [plan(application_component(items))], images.__getitem__, application_reader=contract)
        require({entry["path"] for entry in updates} == {"app-manifest.json", "package.json", "package-lock.json"}, updates)
        require(images[module_source["path"]] == b'{"name":"independent-plugin","version":"7.2.9"}\r\n')


def test_application_auto_dirty_summary_readonly_then_synchronized_commit_once():
    with Fixture() as f:
        root, remote, repo = f.repo()
        images = application_seed(f, root, repo)
        save_edit(root)
        service = f.service()
        service.status()
        settings_bytes = service._settings_path.read_bytes()
        head, index = f.git(root, "rev-parse", "HEAD"), (root / ".git/index").read_bytes()
        catalog = service.version_catalog()["repositories"][0]
        require(len(catalog["components"]) == 1 and catalog["hasChanges"] is True, catalog)
        component = application_component(catalog["components"])
        require(component["autoPlan"]["state"] == "eligible" and component["autoPlan"]["targetVersion"] == "1.0.0", component)
        preview = service.preview()["previews"][0]
        require(preview["title"] == "0.4.0 → 1.0.0" and len(preview["versionTransitions"]) == 1, preview)
        require(len(preview["components"]) == 1 and "Application 0.4.0 → 1.0.0" in preview["body"], preview)
        require_application_images(root, images)
        require(f.git(root, "rev-parse", "HEAD") == head and (root / ".git/index").read_bytes() == index)
        require(not (root / ".git/FETCH_HEAD").exists())
        first = f.run(service)
        sha = child(first)["commitSha"]
        require(child(first)["status"] == "success" and child(first)["title"] == preview["title"], first)
        expected = application_after(images, "0.4.0", "1.0.0")
        require_application_images(root, expected)
        require(f.git(remote, "rev-parse", "main") == sha and f.git(root, "rev-list", "--count", "HEAD") == "3")
        require(service.run("request_00000001") == first, "Repeated request created another application commit")
        second = f.run(service, "request_00000002")
        require(child(second)["status"] == "noop" and f.git(root, "rev-parse", "HEAD") == sha, second)
        require_application_images(root, expected)
        require(not service.status()["settings"]["repositories"][0]["versionPlans"])
        require(service._settings_path.read_bytes() == settings_bytes, "Automatic application plan changed saved user choices")


def test_application_manual_matching_declarations_are_not_incremented_again():
    with Fixture() as f:
        root, remote, repo = f.repo()
        images = application_seed(f, root, repo, version="1.4.0")
        expected = application_after(images, "1.4.0", "1.4.1")
        for name, raw in expected.items():
            (root / name).write_bytes(raw)
        save_edit(root)
        service = f.service()
        catalog = service.version_catalog()["repositories"][0]
        require(len(catalog["components"]) == 1, catalog)
        component = application_component(catalog["components"])
        require(component["autoPlan"]["state"] == "manual_version", component)
        preview = service.preview()["previews"][0]
        require(preview["title"] == "1.4.0 → 1.4.1", preview)
        result = f.run(service)
        require(child(result)["status"] == "success" and child(result)["title"] == preview["title"], result)
        require_application_images(root, expected)
        require(f.git(remote, "rev-parse", "main") == child(result)["commitSha"])
        require(f.git(root, "rev-list", "--count", "HEAD") == "3")
        for name, raw in expected.items():
            require(f.git(root, "show", "HEAD:" + name) == raw.decode("utf-8").strip(), "Commit omitted an application declaration: " + name)


def test_application_initial_declarations_preserved_and_untracked_companion_write_deferred():
    for initial in (False, True):
        with Fixture() as f:
            root, remote, repo = f.repo()
            images = application_seed(f, root, repo, version="1.4.0", commit=not initial)
            if not initial:
                f.git(root, "rm", "package-lock.json")
                f.git(root, "commit", "-m", "HEAD companion missing fixture")
                f.git(root, "push", "origin", "main")
                (root / "package-lock.json").write_bytes(images["package-lock.json"])
            save_edit(root)
            head, index = f.git(root, "rev-parse", "HEAD"), (root / ".git/index").read_bytes()
            service = f.service()
            component = application_component(service.version_catalog()["repositories"][0]["components"])
            require(component["autoPlan"]["state"] == ("initial_version" if initial else "blocked"), component)
            require_application_images(root, images)
            result = f.run(service)
            require_application_images(root, images)
            if initial:
                require(child(result)["status"] == "success" and child(result)["title"] == "1.4.0", result)
                require(f.git(root, "rev-parse", "HEAD") == f.git(remote, "rev-parse", "main") == child(result)["commitSha"])
                require(f.git(root, "rev-list", "--count", "HEAD") == "2")
                for name, raw in images.items():
                    require(f.git(root, "show", "HEAD:" + name) == raw.decode("utf-8").strip(), "Commit omitted an attested initial declaration: " + name)
            else:
                require(child(result)["status"] == "deferred" and "版本" in child(result)["message"], result)
                require((root / ".git/index").read_bytes() == index and f.git(root, "rev-parse", "HEAD") == head)
                require(f.git(remote, "rev-parse", "main") == head and f.git(root, "rev-list", "--count", "HEAD") == "3")


def test_application_duplicate_configured_root_package_sources_defer_as_ambiguous():
    with Fixture() as f:
        root, remote, repo = f.repo()
        images = application_seed(f, root, repo)
        duplicate = copy.deepcopy(repo["versionSources"][1])
        duplicate["name"] = "Another root package authority"
        repo["versionSources"].append(duplicate)
        save_edit(root)
        head, index = f.git(root, "rev-parse", "HEAD"), (root / ".git/index").read_bytes()
        service = f.service()
        component = application_component(service.version_catalog()["repositories"][0]["components"])
        require(component["companionState"] == "blocked" and component["autoPlan"]["state"] == "blocked", component)
        result = f.run(service)
        require(child(result)["status"] == "deferred" and "版本" in child(result)["message"], result)
        require_application_images(root, images)
        require((root / ".git/index").read_bytes() == index and f.git(root, "rev-parse", "HEAD") == head)
        require(f.git(remote, "rev-parse", "main") == head)


def test_application_partial_malformed_or_missing_companion_defers_without_writes():
    for invalid in ("primary_only", "lock_root_only", "lock_package_only", "malformed_lock", "missing_lock"):
        with Fixture() as f:
            root, remote, repo = f.repo()
            images = application_seed(f, root, repo)
            if invalid == "primary_only":
                (root / "app-manifest.json").write_bytes(images["app-manifest.json"].replace(b'"version" : "0.4.0"', b'"version" : "0.4.1"'))
            elif invalid == "lock_root_only":
                (root / "package-lock.json").write_bytes(images["package-lock.json"].replace(b'"version" : "0.4.0"', b'"version" : "0.4.1"', 1))
            elif invalid == "lock_package_only":
                (root / "package-lock.json").write_bytes(images["package-lock.json"].replace(b'"version": "0.4.0"', b'"version": "0.4.1"', 1))
            elif invalid == "malformed_lock":
                (root / "package-lock.json").write_bytes(images["package-lock.json"] + b" incomplete JSON")
            else:
                (root / "package-lock.json").unlink()
            save_edit(root)
            expected = {name: (root / name).read_bytes() for name in images if (root / name).exists()}
            head, index = f.git(root, "rev-parse", "HEAD"), (root / ".git/index").read_bytes()
            service = f.service()
            component = application_component(service.version_catalog()["repositories"][0]["components"])
            require(component["companionState"] == "blocked" and component["autoPlan"]["state"] == "blocked", (invalid, component))
            result = f.run(service)
            require(child(result)["status"] == "deferred" and "版本" in child(result)["message"], (invalid, result))
            require_application_images(root, expected)
            require((root / ".git/index").read_bytes() == index and f.git(root, "rev-parse", "HEAD") == head)
            require(f.git(remote, "rev-parse", "main") == head and (root / "tracked.txt").read_text() == "saved implementation change\n")
            if invalid == "missing_lock":
                require(not (root / "package-lock.json").exists(), "Rejected upload recreated a missing companion")


def test_application_hidden_primary_package_and_lock_manual_changes_preserve_index():
    for hidden, guard in (("app-manifest.json", "exclude"), ("package.json", "assume"), ("package-lock.json", "skip")):
        with Fixture() as f:
            root, remote, repo = f.repo()
            images = application_seed(f, root, repo)
            expected = application_after(images, "0.4.0", "0.4.1")
            for name, raw in expected.items():
                (root / name).write_bytes(raw)
            save_edit(root)
            if guard == "exclude":
                repo["exclude"] = [hidden]
            else:
                f.git(root, "update-index", "--assume-unchanged" if guard == "assume" else "--skip-worktree", hidden)
            head, index = f.git(root, "rev-parse", "HEAD"), (root / ".git/index").read_bytes()
            service = f.service()
            component = application_component(service.version_catalog()["repositories"][0]["components"])
            require(component["companionState"] == "blocked" and component["autoPlan"]["state"] == "blocked", (hidden, guard, component))
            result = f.run(service)
            require(child(result)["status"] == "deferred" and "版本" in child(result)["message"], result)
            require_application_images(root, expected)
            require((root / ".git/index").read_bytes() == index and f.git(root, "rev-parse", "HEAD") == head)
            require(f.git(remote, "rev-parse", "main") == head)


def test_application_hidden_initial_companion_is_not_claimed_as_uploaded():
    with Fixture() as f:
        root, remote, repo = f.repo()
        images = application_seed(f, root, repo, commit=False)
        repo["exclude"] = ["package-lock.json"]
        save_edit(root)
        head, index = f.git(root, "rev-parse", "HEAD"), (root / ".git/index").read_bytes()
        result = f.run(f.service())
        require(child(result)["status"] == "deferred" and "版本" in child(result)["message"], result)
        require_application_images(root, images)
        require((root / ".git/index").read_bytes() == index and f.git(root, "rev-parse", "HEAD") == head)
        require(f.git(remote, "rev-parse", "main") == head)


def test_application_partial_write_restart_continues_original_three_file_intent():
    class Interrupt(Service):
        def _version_intent_snapshot(self, repo, context, pending):
            current = super()._version_intent_snapshot(repo, context, pending)
            if any(module._stable(context[0] / entry["path"])["sha256"] == entry["afterSha256"] for entry in pending["versionUpdates"]):
                raise Error("fixture interruption after first application version write")
            return current
    with Fixture() as f:
        root, remote, repo = f.repo()
        images = application_seed(f, root, repo)
        save_edit(root)
        failed = f.run(f.service(Interrupt))
        require(child(failed)["status"] == "deferred" and f.git(root, "rev-list", "--count", "HEAD") == "2", failed)
        pending = module._read(f.base / "state/pending/one.json")
        require(len(pending["versionPlans"]) == 1 and len(pending["versionUpdates"]) == 3, pending)
        require(pending["versionPlans"][0]["currentVersion"] == "0.4.0" and pending["versionPlans"][0]["targetVersion"] == "1.0.0")
        require({entry["path"] for entry in pending["versionUpdates"]} == set(images))
        expected = application_after(images, "0.4.0", "1.0.0")
        written = [name for name in images if (root / name).read_bytes() == expected[name]]
        require(len(written) == 1, "Interruption did not preserve the actual partial application write")
        original_remote = f.git(remote, "rev-parse", "main")
        resumed = f.run(f.service(), "request_00000002")
        require(child(resumed)["status"] == "success" and child(resumed)["title"] == "0.4.0 → 1.0.0", resumed)
        require_application_images(root, expected)
        require(f.git(root, "rev-list", "--count", "HEAD") == "3" and child(resumed)["commitSha"] != original_remote)
        require(f.git(remote, "rev-parse", "main") == child(resumed)["commitSha"])


def test_application_concurrent_companion_edit_holds_without_overwriting_user_bytes():
    class Concurrent(Service):
        def _apply_version_intent(self, repo, context, pending, pending_path):
            path = context[0] / "package-lock.json"
            path.write_bytes(path.read_bytes() + b"\r\n")
            return super()._apply_version_intent(repo, context, pending, pending_path)
    with Fixture() as f:
        root, remote, repo = f.repo()
        images = application_seed(f, root, repo)
        save_edit(root)
        head, index = f.git(root, "rev-parse", "HEAD"), (root / ".git/index").read_bytes()
        failed = f.run(f.service(Concurrent))
        require(child(failed)["status"] == "deferred", failed)
        expected = dict(images)
        expected["package-lock.json"] += b"\r\n"
        require_application_images(root, expected)
        resumed = f.run(f.service(), "request_00000002")
        require(child(resumed)["status"] == "deferred", resumed)
        require_application_images(root, expected)
        require((root / ".git/index").read_bytes() == index and f.git(root, "rev-parse", "HEAD") == head)
        require(f.git(remote, "rev-parse", "main") == head and f.git(root, "rev-list", "--count", "HEAD") == "2")


def test_application_failed_or_uncertain_push_retries_exact_synchronized_commit():
    class Fail(Service):
        def _git(self, root, *arguments, **kwargs):
            if arguments and arguments[0] == "push":
                raise module._GitFailure("permissions")
            return super()._git(root, *arguments, **kwargs)
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
    for uncertain in (False, True):
        with Fixture() as f:
            root, remote, repo = f.repo()
            images = application_seed(f, root, repo)
            save_edit(root)
            first = f.run(f.service(Unknown if uncertain else Fail))
            sha = child(first)["commitSha"]
            require(child(first)["status"] == ("verification_required" if uncertain else "push_failed") and sha, first)
            expected = application_after(images, "0.4.0", "1.0.0")
            require_application_images(root, expected)
            pending = module._read(f.base / "state/pending/one.json")
            require(len(pending["versionPlans"]) == 1 and len(pending["versionUpdates"]) == 3, pending)
            (root / "tracked.txt").write_text("later user work remains\n")
            resumed = f.run(f.service(), "request_00000002")
            require(child(resumed)["status"] == "success" and child(resumed)["commitSha"] == sha, resumed)
            require_application_images(root, expected)
            require(f.git(root, "rev-parse", "HEAD") == f.git(remote, "rev-parse", "main") == sha)
            require(f.git(root, "rev-list", "--count", "HEAD") == "3" and (root / "tracked.txt").read_text() == "later user work remains\n")


def test_repository_floor_is_explicit_and_preserves_later_versions():
    for current in ("0.0.0", "0.4.0", "v0.99.99", "0.999.999"):
        require(versions.next_patch(current, "1.0.0") == "1.0.0")
    for current in ("1.0.0", "1.6.46", "v1.02.003", "2.99.99"):
        require(versions.next_patch(current, "1.0.0") == versions.next_patch(current))
    require(versions.next_patch("0.4.0") == "0.4.1", "Independent components acquired a repository floor")
    for current, minimum in (("not-a-version", "1.0.0"), ("0.4.0", "2.0.0")):
        try:
            versions.next_patch(current, minimum)
        except versions.VersionPlanError:
            pass
        else:
            raise AssertionError("An ambiguous or unsupported version policy was accepted")


def test_git_system_proxy_respects_explicit_environment_and_protocol():
    from console_git_environment import environment_for_remote
    calls = []
    def resolve(url):
        calls.append(url)
        return "http://127.0.0.1:43210"
    original = {"PATH": "kept", "NO_PROXY": "localhost"}
    actual = environment_for_remote(original, "https://example.invalid/project.git", resolver=resolve)
    require(actual == {**original, "https_proxy": "http://127.0.0.1:43210"} and original == {"PATH": "kept", "NO_PROXY": "localhost"})
    require(environment_for_remote({}, "http://example.invalid/project.git", resolver=resolve)
            == {"http_proxy": "http://127.0.0.1:43210"})
    for key in ("ALL_PROXY", "all_proxy", "https_proxy", "HTTPS_PROXY"):
        calls.clear()
        explicit = {key: "", "PATH": "kept"}
        require(environment_for_remote(explicit, "https://example.invalid/project.git", resolver=resolve) == explicit and not calls)
    for remote in ("git@example.invalid:project.git", "ssh://example.invalid/project.git", "file:///fixture.git", "not a URL"):
        calls.clear()
        require(environment_for_remote(original, remote, resolver=resolve) == original and not calls)


def test_git_system_proxy_unknown_or_invalid_resolution_keeps_git_defaults():
    from console_git_environment import environment_for_remote
    for address in (None, "", "not-a-proxy", "http://localhost:99999", "http://localhost:12\nSECRET", "javascript:ignored"):
        require(environment_for_remote({"PATH": "kept"}, "https://example.invalid/project.git", resolver=lambda url: address) == {"PATH": "kept"})
    def unavailable(url):
        raise OSError("resolution unavailable")
    require(environment_for_remote({}, "https://example.invalid/project.git", resolver=unavailable) == {})


def test_repository_floor_edits_exact_json_and_python_spans():
    raw = b'\xef\xbb\xbf{\r\n "version": "0.4.0", "dependency": "0.4.0"\r\n}\r\n'
    authority = {**source(), "minimumVersion": "1.0.0", "repositoryVersion": True}
    component, after = pure(raw, authority)
    require(component["currentVersion"] == "0.4.0" and component["nextVersion"] == "1.0.0"
            and component["requiresVersionFloor"] and component["repositoryVersion"], component)
    require(after == raw.replace(b'"version": "0.4.0"', b'"version": "1.0.0"'))
    raw = b'bl_info = {"version": (0, 4, 7), "description": "0.4.7"} # keep\r\n'
    authority = {**source("plugin.py", "python_ast", "bl_info.version"), "minimumVersion": "1.0.0"}
    _, after = pure(raw, authority)
    require(after == raw.replace(b"(0, 4, 7)", b"(1, 0, 0)"))


def test_repository_initial_commit_requires_valid_fixed_history_and_explicit_policy():
    head = "a" * 40
    raw = head + "\0Create repository\n" + "b" * 40 + "\0Feature mentions 9.9.9\n"
    try:
        versions.parse_commit_history(head, raw)
    except versions.VersionPlanError:
        pass
    else:
        raise AssertionError("Existing strict Git authorities silently initialized")
    evidence = versions.parse_commit_history(head, raw, allow_initial=True)
    require(evidence["initialVersion"] and evidence["version"] == "1.0.0"
            and evidence["sourceHeadSha"] == head and not evidence["versionCommitSha"], evidence)
    for malformed in ("b" * 40 + "\0Create repository\n", head + "\0bad\0row\n", ""):
        try:
            versions.parse_commit_history(head, malformed, allow_initial=True)
        except versions.VersionPlanError:
            pass
        else:
            raise AssertionError("Malformed history became a repository initial version")
    existing = versions.parse_commit_history(head, head + "\0" + "1.6.46 -> 1.6.47\n", allow_initial=True)
    require(existing["version"] == "1.6.47" and not existing.get("initialVersion"), existing)


def test_repository_initial_commit_plan_is_bound_without_file_writes():
    authority = {**source("HEAD", "git_commit", "subject"), "repositoryVersion": True,
                 "minimumVersion": "1.0.0", "allowInitial": True}
    evidence = versions.parse_commit_history("a" * 40, "a" * 40 + "\0Create repository\n", allow_initial=True)
    reader = lambda path: (_ for _ in ()).throw(AssertionError("Git initial version read a project file"))
    component = versions.catalog(Path("."), [authority], reader, lambda item: evidence)[0]
    require(component["initialVersion"] and component["currentVersion"] == component["nextVersion"] == "1.0.0", component)
    updates, proofs = versions.prepare_updates(Path("."), [authority], [plan(component)], reader, lambda item: evidence)
    require(not updates and len(proofs) == 1)
    changed = versions.parse_commit_history("b" * 40, "b" * 40 + "\0Create repository\n", allow_initial=True)
    try:
        versions.prepare_updates(Path("."), [authority], [plan(component)], reader, lambda item: changed)
    except versions.VersionPlanError:
        pass
    else:
        raise AssertionError("Repository initialization replayed across a changed HEAD")


def test_application_repository_floor_keeps_companions_and_dependencies_coherent():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        sources = application_sources()
        sources[0].update(repositoryVersion=True, minimumVersion="1.0.0")
        images = application_images()
        contract, _ = application_contract(sources, images)
        component = application_component(versions.catalog(root, sources, images.__getitem__, application_reader=contract))
        require(component["requiresVersionFloor"] and component["nextVersion"] == "1.0.0", component)
        updates, _ = versions.prepare_updates(root, sources, [plan(component)], images.__getitem__, application_reader=contract)
        actual = {entry["path"]: base64.b64decode(entry["afterBase64"]) for entry in updates}
        require(actual == application_after(images, "0.4.0", "1.0.0"), actual)
        require(images == application_images(), "A read-only version plan changed the project")


def test_clean_application_repository_floor_creates_real_exact_companion_commit_once():
    with Fixture() as f:
        root, remote, repo = f.repo()
        images = application_seed(f, root, repo)
        head, index = f.git(root, "rev-parse", "HEAD"), (root / ".git/index").read_bytes()
        service = f.service()
        catalog = service.version_catalog()["repositories"][0]
        require(catalog["hasChanges"] is True and catalog["worktreeChanged"] is False and catalog["pendingRecovery"] is False, catalog)
        require(catalog["repositoryVersion"] == {"state":"initial", "currentVersion":"1.0.0", "sourceVersion":"0.4.0", "nextVersion":"1.0.0",
                                               "transition":{"kind":"initial", "fromVersion":"0.4.0", "toVersion":"1.0.0"}}, catalog)
        preview = service.preview()["previews"][0]
        require(preview["action"] == "commit" and preview["planWillApply"] is True and preview["title"] == "0.4.0 → 1.0.0", preview)
        require_application_images(root, images)
        require(f.git(root, "rev-parse", "HEAD") == head and (root / ".git/index").read_bytes() == index)
        first = f.run(service, "request_clean_floor_0001", intent="commit_and_push")
        item = child(first)
        require(item["status"] == "success" and item["title"] == "0.4.0 → 1.0.0", first)
        require_application_images(root, application_after(images, "0.4.0", "1.0.0"))
        require(f.git(root, "rev-list", "--count", "HEAD") == "3" and f.git(remote, "rev-parse", "main") == item["commitSha"])
        changed = f.git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()
        require(set(changed) == set(images), changed)
        require(f.run(service, "request_clean_floor_0001", intent="commit_and_push") == first)
        again = f.run(service, "request_clean_floor_0002", intent="commit_and_push")
        require(child(again)["status"] == "noop" and f.git(root, "rev-list", "--count", "HEAD") == "3", again)
        require(service.version_catalog()["repositories"][0]["repositoryVersion"]["currentVersion"] == "1.0.0")


TESTS = [item for name, item in tuple(globals().items()) if name.startswith("test_") and callable(item)]
if __name__ == "__main__":
    files = [ROOT / "console_repository_versions.py", ROOT / "console_repository_publish.py", ROOT / "console_git_environment.py", Path(__file__),
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
