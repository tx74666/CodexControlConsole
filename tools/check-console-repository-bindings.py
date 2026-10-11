"""Lightweight metadata/temporary-fixture checks; no actual repository mutation."""
from __future__ import annotations
import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from console_repository_bindings import RepositoryBindingDiscovery, ReadOnlyGit, desktop_codex_activity, probe_existing_lock, rollout_activity


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="console-repo-discovery-")
        self.base = Path(self.temp.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        self.calls = []
        self.workflow_calls = 0

    def tearDown(self):
        self.temp.cleanup()

    def git(self, root, *args):
        self.calls.append(args)
        if args == ("rev-parse", "--show-toplevel"):
            return str(self.root)
        if args == ("rev-parse", "--git-common-dir"):
            return ".git"
        if args == ("symbolic-ref", "--short", "HEAD"):
            return "feature/current-work"
        return "https://github.com/tx74666/Test-project.git"

    def discovery(self, **kwargs):
        return RepositoryBindingDiscovery(git_reader=self.git, known_roots=[self.root], **kwargs)

    def write(self, relative, content):
        p = self.root / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def test_current_branch_and_no_default_version_or_exclude(self):
        result = self.discovery().discover()
        repo = result["repositories"][0]
        self.assertEqual(repo["branch"], "feature/current-work")
        self.assertEqual(repo["versionSources"], [])
        self.assertEqual(repo["exclude"], [])
        self.assertIsNone(repo["syncManifest"])
        self.assertTrue(repo["enabled"])
        self.assertTrue(any(x["code"] == "authoritative_version_source_missing" for x in result["warnings"]))
        self.assertNotIn("v0.1.0", json.dumps(repo))

    def test_catalog_extensible_missing_separate_and_bindings_dedup(self):
        other = self.base / "another"
        other.mkdir()
        def git(root, *args):
            if args == ("rev-parse", "--show-toplevel"): return str(root)
            if args == ("symbolic-ref", "--short", "HEAD"): return "work/branch"
            return "https://github.com/tx74666/" + Path(root).name
        catalog = [{"repositoryUrl": "https://github.com/tx74666/" + self.root.name, "path": str(self.root)},
                   {"repositoryUrl": "https://github.com/tx74666/" + other.name, "path": str(other)},
                   {"repositoryUrl": "https://github.com/tx74666/CloudOnly", "version": "v0.1.0"}]
        d = RepositoryBindingDiscovery(blender_catalog=lambda: catalog, workflow_snapshot=lambda: {"bindings": [{"workspaceRoot": str(other)}]}, git_reader=git)
        result = d.discover()
        self.assertEqual(len(result["repositories"]), 3)
        cloud = next(r for r in result["repositories"] if not r["path"])
        self.assertEqual(cloud["repositoryUrl"], "https://github.com/tx74666/CloudOnly")
        self.assertFalse(cloud["enabled"])
        self.assertEqual(cloud["branch"], "")
        self.assertEqual(cloud["versionSources"], [])
        self.assertTrue(any(x["code"] == "configured_repository_path_missing" for x in result["warnings"]))

    def test_authoritative_json_python_unity_metadata_without_import(self):
        self.write("app-manifest.json", '{"version":"1.2.3"}')
        self.write("node_library/manifest.json", '{"library_version":"0.3.1"}')
        self.write("addons/helper/__init__.py", "bl_info={'name':'Helper','version':(2,4,6)}\nraise RuntimeError('must never import')\n")
        self.write("ProjectSettings/ProjectSettings.asset", "PlayerSettings:\n  bundleVersion: 7.8.9\n")
        versions = self.discovery().discover()["repositories"][0]["versionSources"]
        self.assertEqual({v["kind"] for v in versions}, {"json", "python_ast", "unity"})
        self.assertEqual(len(versions), 4)
        self.assertTrue(all(v["path"] and v["name"] and v["scope"] for v in versions))

    def test_manifest_addon_version_and_bad_configuration_warning(self):
        self.write("Language-Switcher/blender_manifest.toml", 'schema_version="1.0.0"\nversion="3.2.1"\nname="Language Switcher"\n')
        result = self.discovery(blender_store=lambda: ["wrong shape"]).discover()
        versions = result["repositories"][0]["versionSources"]
        self.assertEqual([(v["kind"], v["key"]) for v in versions], [("text", "version")])
        self.assertIn("configuration_unreadable", [w["code"] for w in result["warnings"]])

    def test_reuse_explicit_saved_build_mapping_dependencies_before_scene(self):
        saved = self.base / "Builder6.blend"
        saved.write_bytes(b"saved scene fixture")
        dep = self.base / "texture.png"
        dep.write_bytes(b"texture")
        # Equivalent input spellings must return the canonical saved-file identity.
        # Windows CI may also give the temporary root its short 8.3 spelling.
        saved_alias, dep_alias = self.root / ".." / saved.name, self.root / ".." / dep.name
        self.assertTrue(saved_alias.samefile(saved))
        self.assertTrue(dep_alias.samefile(dep))
        manifest = {"sourceScene": str(saved_alias), "sceneDestination": "Build.blend",
                    "dependencies": [{"source": str(dep_alias), "destination": "textures/texture.png"}]}
        self.write("tools/build_sources.json", json.dumps(manifest))
        before = saved.stat().st_mtime_ns
        sync = self.discovery().discover()["repositories"][0]["syncFiles"]
        self.assertEqual(sync, [{"source": str(dep.resolve()), "target": "textures/texture.png"}, {"source": str(saved.resolve()), "target": "Build.blend"}])
        self.assertFalse((self.root / "Build.blend").exists())
        self.assertEqual(saved.stat().st_mtime_ns, before)
        manifest_proof = self.discovery().discover()["repositories"][0]["syncManifest"]
        self.assertEqual(manifest_proof["path"], str((self.root / "tools/build_sources.json").resolve()))
        import hashlib
        self.assertEqual(manifest_proof["sha256"], hashlib.sha256((self.root / "tools/build_sources.json").read_bytes()).hexdigest())

    def test_sync_source_missing_kept_for_publisher_fail_closed(self):
        self.write("tools/build_sources.json", json.dumps({"sourceScene": str(self.base / "missing.blend"), "sceneDestination": "Build.blend", "dependencies": []}))
        result = self.discovery().discover()
        self.assertEqual(len(result["repositories"][0]["syncFiles"]), 1)
        self.assertIn("configured_sync_source_missing", [w["code"] for w in result["warnings"]])

    def test_outside_sync_target_rejected(self):
        self.write("tools/build_sources.json", '{"sourceScene":"saved.blend","sceneDestination":"../escape.blend","dependencies":[]}')
        result = self.discovery().discover()
        self.assertEqual(result["repositories"][0]["syncFiles"], [])
        self.assertTrue(result["repositories"][0]["syncError"])
        self.assertIn("saved_sync_manifest_invalid", [w["code"] for w in result["warnings"]])

    def test_remote_mismatch_and_credential_url_never_exported(self):
        d = RepositoryBindingDiscovery(blender_catalog=[{"path": str(self.root), "repositoryUrl": "https://github.com/tx74666/Wrong"},
                                                            {"repositoryUrl": "https://SECRET:password@github.com/a/b"}], git_reader=self.git)
        result = d.discover()
        self.assertEqual(result["repositories"], [])
        self.assertNotIn("SECRET", json.dumps(result))

    def test_named_environment_missing_path_editable_placeholder_no_invented_branch(self):
        d = RepositoryBindingDiscovery(known_roots=[{"path": "", "repositoryUrl": "https://github.com/tx74666/MyWeb"}], git_reader=self.git)
        result = d.discover()
        self.assertEqual(self.calls, [])
        repo = result["repositories"][0]
        self.assertEqual((repo["path"], repo["branch"], repo["enabled"]), ("", "", False))
        self.assertEqual(repo["repositoryUrl"], "https://github.com/tx74666/MyWeb")
        self.assertIsNone(repo["syncManifest"])
        self.assertIn("configured_repository_path_missing", [w["code"] for w in result["warnings"]])

    def test_git_metadata_sync_target_cannot_escape_invalid_manifest_blocker(self):
        self.write("tools/build_sources.json", '{"sourceScene":"saved.blend","sceneDestination":".git/config","dependencies":[]}')
        result = self.discovery().discover()
        self.assertEqual(result["repositories"][0]["syncFiles"], [])
        self.assertTrue(result["repositories"][0]["syncError"])

    def test_read_only_git_actual_temp_current_branch(self):
        subprocess.run(["git", "init", "-q", "-b", "feature/fixture", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "remote.origin.url", "https://github.com/tx74666/Fixture"], check=True)
        d = RepositoryBindingDiscovery(known_roots=[self.root], desktop_activity={"records": [], "warnings": []})
        self.assertEqual(d.discover()["repositories"][0]["branch"], "feature/fixture")
        with self.assertRaises(ValueError): ReadOnlyGit()(self.root, "fetch", "origin")
        with self.assertRaises(ValueError): ReadOnlyGit()(self.root, "status")

    def test_stale_existing_lock_not_busy_and_held_lock_busy(self):
        lock = self.root / ".git/console-developer-update.lock"
        lock.parent.mkdir()
        lock.write_bytes(b"\0")
        self.assertEqual(probe_existing_lock(lock), "free")
        d = self.discovery(desktop_activity={"records": [], "warnings": []})
        self.assertIsNone(d.busy_reason(self.root))
        d.lock_probe = lambda path: "held"
        self.assertIn("lock", d.busy_reason(self.root))
        self.assertIsNone(d.busy_reason(self.root, owned_developer_lock=True))
        d.desktop_activity = {"records": [{"cwd": str(self.root), "state": "active"}], "warnings": []}
        self.assertIn("Desktop Codex", d.busy_reason(self.root, owned_developer_lock=True))
        self.assertEqual(lock.read_bytes(), b"\0")

    def test_work_overlap_and_developer_operation_and_one_snapshot_read(self):
        def snapshot():
            self.workflow_calls += 1
            return {"jobs": [{"workspaceRoot": str(self.root / "nested"), "status": "running"}]}
        d = self.discovery(workflow_snapshot=snapshot, desktop_activity={"records": [], "warnings": []})
        self.assertIn("Work", d.busy_reason(self.root))
        self.assertEqual(self.workflow_calls, 1)
        d.workflow_snapshot = lambda: {"jobs": [{"workspaceRoot": str(self.base / "other"), "status": "running"}]}
        self.assertIsNone(d.busy_reason(self.root))
        self.assertIn("Work", d.busy_reason(self.root, developer_operation={"sourceRoot": str(self.root), "status": "working"}))

    def test_desktop_parent_active_unknown_and_archived(self):
        d = self.discovery(desktop_activity={"records": [{"cwd": str(self.base), "state": "active"}], "warnings": []})
        self.assertIn("Desktop Codex", d.busy_reason(self.root))
        d.desktop_activity = {"records": [{"cwd": str(self.base), "state": "unknown"}], "warnings": []}
        self.assertIn("unverified", d.busy_reason(self.root))
        d.desktop_activity = {"records": [{"cwd": str(self.root), "state": "active", "archived": True}], "warnings": []}
        self.assertIsNone(d.busy_reason(self.root))

    def test_actual_nested_codex_work_source_scopes_unrelated_repository(self):
        job = {"status": "needs_review", "payload": {"codexWork": {"source": {"workspace": {
            "workspaceRoot": str(self.base / "other"), "allowedRoot": str(self.base / "other" / "nested")}}}}}
        d = self.discovery(workflow_snapshot={"jobs": [job]}, desktop_activity={"records": [], "warnings": []})
        self.assertIsNone(d.busy_reason(self.root))
        job["payload"]["codexWork"]["source"]["workspace"]["workspaceRoot"] = str(self.root)
        self.assertIn("Work", d.busy_reason(self.root))
        job = {"status": "running", "spec": {"source": {"workspaceRoot": str(self.base / "other")}}}
        d.workflow_snapshot = {"jobs": [job]}
        self.assertIsNone(d.busy_reason(self.root))

    def test_native_app_snapshot_and_edit_ownership_guard(self):
        d = self.discovery(workflow_snapshot={"native_app": {"threads": [{"cwd": str(self.root), "status": "running"}]}},
                           desktop_activity={"records": [], "warnings": []})
        self.assertIn("Work", d.busy_reason(self.root))
        d.workflow_snapshot = {}
        d.edit_ownership = [{"root": str(self.root / "addons"), "active": True}]
        self.assertIn("Work", d.busy_reason(self.root))

    def test_rollout_typed_user_after_final_is_active_no_text_exported(self):
        rollout = self.base / "rollout.jsonl"
        events = [{"type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": "final", "content": "SECRET TEXT"}},
                  {"type": "response_item", "payload": {"type": "message", "role": "user", "content": "SECRET TEXT"}}]
        rollout.write_text("".join(json.dumps(x) + "\n" for x in events), encoding="utf-8")
        result = rollout_activity(rollout)
        self.assertEqual(result["state"], "active")
        self.assertNotIn("SECRET", json.dumps(result))
        with rollout.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "event_msg", "payload": {"type": "task_complete"}}) + "\n")
        self.assertEqual(rollout_activity(rollout)["state"], "idle")

    def test_rollout_bounded_missing_and_partial_are_unverified(self):
        p = self.base / "rollout.jsonl"
        p.write_text(json.dumps({"type": "event_msg", "payload": {"type": "token_count"}}) + "\n", encoding="utf-8")
        self.assertEqual(rollout_activity(p)["state"], "unknown")
        p.write_text('{"type":"event_msg","payload":{"type":"task_complete"}}', encoding="utf-8")
        self.assertEqual(rollout_activity(p)["state"], "unknown")

    def test_actual_sqlite_schema_archived_and_only_matching_root(self):
        dbpath, rollout = self.base / "state.sqlite", self.base / "rollout.jsonl"
        rollout.write_text('{"type":"event_msg","payload":{"type":"task_started"}}\n', encoding="utf-8")
        with closing(sqlite3.connect(dbpath)) as db:
            db.execute("CREATE TABLE threads(id TEXT,cwd TEXT,rollout_path TEXT,archived INT,updated_at INT)")
            db.executemany("INSERT INTO threads VALUES(?,?,?,?,?)", [("archived", str(self.root), str(rollout), 1, 2),
                                                                     ("other", str(self.base / "other"), str(rollout), 0, 2),
                                                                     ("live", str(self.root), str(rollout), 0, 1)])
            db.commit()
        result = desktop_codex_activity(self.root, [dbpath])
        self.assertEqual([r["threadId"] for r in result["records"]], ["live"])
        self.assertEqual(result["records"][0]["state"], "active")
        with closing(sqlite3.connect(dbpath)) as db:
            db.execute("DROP TABLE threads")
            db.commit()
        result = desktop_codex_activity(self.root, [dbpath])
        self.assertEqual(result["records"], [])
        self.assertEqual(result["warnings"][0]["code"], "desktop_codex_schema_unverified")


if __name__ == "__main__":
    unittest.main(verbosity=2)
