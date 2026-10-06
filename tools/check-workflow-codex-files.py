"""Isolated filesystem fixtures; no provider, credentials or production IO."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import workflow_codex_files as api


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class FileToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="console-files-")
        self.home = Path(self.temporary.name).resolve()
        self.root = self.home / "project"; self.root.mkdir()
        self.markers = self.home / "markers"; self.markers.mkdir()
        self.tools = api.CodexFiles(self.root, self.markers)
        self.sequence = 0

    def tearDown(self):
        self.temporary.cleanup()

    def call(self, tool, args, **kwargs):
        self.sequence += 1
        return self.tools.call(tool, args, "call_" + str(self.sequence), **kwargs)

    def rejected(self, code, function, *args, **kwargs):
        with self.assertRaisesRegex(RuntimeError, "^codex_files_" + code + "$"):
            function(*args, **kwargs)

    def test_complete_utf8_create_replace_read_and_durable_receipt(self):
        first = "你好\nline two\n"
        result = self.call("write_text", {"path": "hello.py", "content": first, "expectedSha256": None})
        self.assertEqual(result["afterSha256"], sha(first.encode()))
        self.assertIsNone(result["beforeSha256"])
        second = "替换完整內容🙂\n"
        result = self.call("write_text", {"path": "hello.py", "content": second, "expectedSha256": sha(first.encode())})
        self.assertFalse(result["optimisticRaceEliminated"])
        self.assertEqual((self.root / "hello.py").read_bytes(), second.encode())
        read = self.call("read_text", {"path": "hello.py"})
        self.assertEqual(read, {"path": "hello.py", "text": second, "bytes": len(second.encode()), "sha256": sha(second.encode())})
        receipts = list(self.markers.glob("*.receipt.json"))
        self.assertEqual(len(receipts), 3)
        for path in receipts:
            value = json.loads(path.read_text())
            self.assertEqual(value["status"], "completed")
            self.assertNotIn(str(self.root), path.read_text())
        self.assertEqual(list(self.root.glob(".console-codex-*.tmp")), [])

    def test_metadata_listing_has_bounded_depth_and_skips_secret_names(self):
        (self.root / "a.txt").write_bytes(b"a")
        nested = self.root / "src"; nested.mkdir(); (nested / "b.txt").write_bytes(b"bb")
        deeper = nested / "more"; deeper.mkdir(); (deeper / "c.txt").write_bytes(b"ccc")
        (self.root / ".env").write_bytes(b"fixture-only-secret")
        git = self.root / ".git"; git.mkdir(); (git / "config").write_bytes(b"fixture")
        self.assertEqual(self.call("list_files", {"path": "", "depth": 1}), {"files": [{"path": "a.txt", "bytes": 1}], "truncated": False})
        listed = self.call("list_files", {"path": "", "depth": 3})
        self.assertEqual(listed["files"], [{"path": "a.txt", "bytes": 1}, {"path": "src/b.txt", "bytes": 2}, {"path": "src/more/c.txt", "bytes": 3}])
        self.assertTrue(all(set(item) == {"path", "bytes"} for item in listed["files"]))

    def test_strict_argument_schema_types_and_call_identity(self):
        for tool, args in [(None, {}), ([], {}), ("delete", {}), ("read_text", {"path": "x", "extra": 1}),
                           ("list_files", {"path": "", "depth": True}), ("list_files", {"path": "", "depth": 4}),
                           ("write_text", {"path": "x", "text": "x", "expectedSha256": None}),
                           ("write_text", {"path": "x", "content": "x", "expectedSha256": "A" * 64})]:
            self.rejected("invalid_arguments", self.call, tool, args)
        self.rejected("invalid_call_id", self.tools.call, "read_text", {"path": "x"}, "../call")
        self.rejected("invalid_arguments", self.call, "read_text", {"path": "x"}, cancelled=True)

    def test_relative_paths_refuse_escape_ads_devices_and_aliases(self):
        (self.root / "safe.txt").write_bytes(b"same")
        for path in ["../safe.txt", "/safe.txt", "C:/safe.txt", "//server/share", "src\\safe.txt", "a//b", "./a", "a/../b", "safe.txt:secret", "NUL.txt", "CONIN$", "CONOUT$", "COM1", "LPT¹.txt", "a.", "a ", "x\0y"]:
            self.rejected("invalid_relative_path", self.call, "read_text", {"path": path})
        self.rejected("path_too_deep", self.call, "read_text", {"path": "/".join(["x"] * 9)})
        self.assertEqual((self.root / "safe.txt").read_bytes(), b"same")

    def test_protected_names_patterns_and_subdirectories(self):
        tools = api.CodexFiles(self.root, self.markers, protected_directories=("restricted",), protected_patterns=("**/private*.txt",))
        for path in [".git/config", ".codex/config", "work/x", "workflow-private/x", "chatgpt-subscription/x", ".env", ".env.local", "auth.json", "credentials.json", "file.pem", "file.dpapi", "restricted/x", "private-data.txt", "src/private-data.txt"]:
            self.rejected("protected_path", tools.call, "read_text", {"path": path}, "protected_call")

    def test_stale_hash_and_null_new_only_preserve_existing_file(self):
        path = self.root / "existing.txt"; path.write_bytes(b"original")
        for expected in [None, "0" * 64]:
            self.rejected("sha_conflict", self.call, "write_text", {"path": "existing.txt", "content": "new", "expectedSha256": expected})
        self.rejected("sha_conflict", self.call, "write_text", {"path": "missing.txt", "content": "new", "expectedSha256": sha(b"old")})
        self.assertEqual(path.read_bytes(), b"original")
        self.assertFalse((self.root / "missing.txt").exists())

    def test_duplicate_and_unknown_intent_are_never_replayed(self):
        args = {"path": "new.txt", "content": "one", "expectedSha256": None}
        self.tools.call("write_text", args, "unique")
        fresh = api.CodexFiles(self.root, self.markers)
        self.rejected("duplicate_call", fresh.call, "write_text", {**args, "content": "two", "expectedSha256": sha(b"one")}, "unique")
        marker = self.markers / (sha(b"unknown") + ".intent.json"); marker.write_text("{}")
        self.rejected("duplicate_call", fresh.call, "write_text", {**args, "path": "unknown.txt"}, "unknown")
        self.assertEqual((self.root / "new.txt").read_bytes(), b"one")
        self.assertFalse((self.root / "unknown.txt").exists())

    def test_read_write_and_listing_limits_do_not_truncate_success(self):
        (self.root / "large.txt").write_bytes(b"x" * (api.MAX_TEXT_BYTES + 1))
        self.rejected("text_too_large", self.call, "read_text", {"path": "large.txt"})
        self.rejected("text_too_large", self.call, "write_text", {"path": "new.txt", "content": "x" * (api.MAX_TEXT_BYTES + 1), "expectedSha256": None})
        self.assertFalse((self.root / "new.txt").exists())
        for index in range(api.MAX_LIST_ENTRIES):
            (self.root / (str(index) + ".txt")).touch()
        self.rejected("list_limit", self.call, "list_files", {"path": "", "depth": 1})
        for path in self.root.iterdir():
            path.unlink()
        with (self.root / "sparse.bin").open("wb") as stream:
            stream.truncate(api.MAX_LIST_BYTES + 1)
        self.rejected("list_limit", self.call, "list_files", {"path": "", "depth": 1})

    def test_invalid_utf8_and_nul_are_refused_without_leaking_content(self):
        (self.root / "invalid.txt").write_bytes(b"\xff-private-fixture")
        (self.root / "binary.txt").write_bytes(b"some\0text")
        for name in ["invalid.txt", "binary.txt"]:
            self.rejected("invalid_utf8_text", self.call, "read_text", {"path": name})
        for value in ["\ud800", "hello\0there"]:
            self.rejected("invalid_utf8_text", self.call, "write_text", {"path": "new.txt", "content": value, "expectedSha256": None})

    def test_hardlink_files_refused_on_read_write_and_list(self):
        outside = self.home / "outside.txt"; outside.write_bytes(b"fixture-outside")
        os.link(outside, self.root / "alias.txt")
        self.rejected("unsafe_file", self.call, "read_text", {"path": "alias.txt"})
        self.rejected("unsafe_file", self.call, "write_text", {"path": "alias.txt", "content": "new", "expectedSha256": sha(b"fixture-outside")})
        self.rejected("unsafe_file", self.call, "list_files", {"path": "", "depth": 1})
        self.assertEqual(outside.read_bytes(), b"fixture-outside")

    def test_symlink_files_and_ancestors_refused(self):
        outside = self.home / "outside"; outside.mkdir(); (outside / "note.txt").write_bytes(b"outside")
        try:
            os.symlink(outside, self.root / "alias", target_is_directory=True)
            os.symlink(outside / "note.txt", self.root / "note.txt")
        except OSError as error:
            self.skipTest("symlink creation not permitted: " + type(error).__name__)
        self.rejected("unsafe_path", self.call, "read_text", {"path": "alias/note.txt"})
        self.rejected("unsafe_path", self.call, "read_text", {"path": "note.txt"})
        self.rejected("unsafe_path", self.call, "write_text", {"path": "alias/new.txt", "content": "new", "expectedSha256": None})
        self.assertFalse((outside / "new.txt").exists())

    @unittest.skipUnless(os.name == "nt", "Windows ancestor handle fixture")
    def test_windows_junction_ancestor_refused(self):
        # Own directories only. Native CreateSymbolicLink permissions are not
        # needed for a directory junction; no credentials or global paths.
        import subprocess
        outside = self.home / "outside"; outside.mkdir(); (outside / "note.txt").write_bytes(b"outside")
        link = self.root / "junction"
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
        self.assertEqual(result.returncode, 0)
        try:
            self.rejected("unsafe_path", self.call, "read_text", {"path": "junction/note.txt"})
            self.rejected("unsafe_path", self.call, "write_text", {"path": "junction/new.txt", "content": "new", "expectedSha256": None})
        finally:
            link.rmdir()
        self.assertFalse((outside / "new.txt").exists())

    def test_cancellation_before_intent_and_before_mutation(self):
        args = {"path": "new.txt", "content": "new", "expectedSha256": None}
        self.rejected("cancelled", self.call, "write_text", args, cancelled=lambda: True)
        self.assertEqual(list(self.markers.iterdir()), [])
        answers = iter([False, False, True])
        self.rejected("cancelled", self.call, "write_text", args, cancelled=lambda: next(answers))
        self.assertEqual(len(list(self.markers.glob("*.intent.json"))), 1)
        self.assertEqual(list(self.markers.glob("*.receipt.json")), [])
        self.assertFalse((self.root / "new.txt").exists())
        self.assertEqual(list(self.root.glob(".console-codex-*.tmp")), [])

    def test_unknown_cancellation_and_callback_exception_fail_closed(self):
        self.rejected("cancelled", self.call, "read_text", {"path": "x"}, cancelled=lambda: None)
        def broken():
            raise RuntimeError("private-fixture-message")
        self.rejected("operation_unverified", self.call, "read_text", {"path": "x"}, cancelled=broken)

    def test_final_hash_recheck_preserves_external_edit(self):
        path = self.root / "note.txt"; path.write_bytes(b"old")
        original = api.bounded_text; calls = 0
        def changed(target):
            nonlocal calls
            calls += 1
            if calls == 2:
                target.write_bytes(b"external-new")
            return original(target)
        with patch.object(api, "bounded_text", side_effect=changed):
            self.rejected("sha_conflict", self.call, "write_text", {"path": "note.txt", "content": "replacement", "expectedSha256": sha(b"old")})
        self.assertEqual(path.read_bytes(), b"external-new")
        self.assertEqual(list(self.root.glob(".console-codex-*.tmp")), [])

    def test_atomic_new_file_race_preserves_competing_file(self):
        original = os.link
        def raced(source, destination, **kwargs):
            Path(destination).write_bytes(b"competing-file")
            return original(source, destination, **kwargs)
        with patch.object(api.os, "link", side_effect=raced):
            self.rejected("sha_conflict", self.call, "write_text", {"path": "new.txt", "content": "replacement", "expectedSha256": None})
        self.assertEqual((self.root / "new.txt").read_bytes(), b"competing-file")

    def test_receipt_failure_retains_write_and_blocks_retry(self):
        original = self.tools.save
        def failed_receipt(path, value):
            if path.name.endswith(".receipt.json"):
                raise OSError("private-fixture-error")
            return original(path, value)
        args = {"path": "note.txt", "content": "written", "expectedSha256": None}
        with patch.object(api.CodexFiles, "save", side_effect=failed_receipt):
            self.rejected("operation_unverified", self.tools.call, "write_text", args, "once")
        self.assertEqual((self.root / "note.txt").read_bytes(), b"written")
        self.rejected("duplicate_call", self.tools.call, "write_text", {**args, "expectedSha256": sha(b"written")}, "once")

    @unittest.skipUnless(os.name == "nt", "Windows handle fixture")
    def test_parent_rename_cannot_escape_write_scope(self):
        nested = self.root / "src"; nested.mkdir(); path = nested / "note.txt"; path.write_bytes(b"old")
        original = os.replace; attempted = []
        def rename_parent(source, destination):
            try:
                nested.rename(self.home / "moved")
            except OSError:
                attempted.append("denied")
            else:
                attempted.append("escaped")
            return original(source, destination)
        with patch.object(api.os, "replace", side_effect=rename_parent):
            self.call("write_text", {"path": "src/note.txt", "content": "new", "expectedSha256": sha(b"old")})
        self.assertEqual(attempted, ["denied"])
        self.assertEqual(path.read_bytes(), b"new")

    def test_scope_must_exist_and_markers_stay_outside_scope(self):
        self.rejected("invalid_scope", api.CodexFiles, Path("relative"), self.markers)
        inside = self.root / "markers"; inside.mkdir()
        self.rejected("invalid_scope", api.CodexFiles, self.root, inside)
        self.rejected("not_found", api.CodexFiles, self.home / "missing", self.markers)


if __name__ == "__main__":
    unittest.main()
