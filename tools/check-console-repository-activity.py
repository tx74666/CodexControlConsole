"""Isolated ownership/metadata tests: no real Codex history or repository changes."""
from __future__ import annotations
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from console_repository_activity import ScopeError, ScopeStore, scan_rollout
import console_repository_activity as activity_module
from console_repository_bindings import RepositoryBindingDiscovery, desktop_codex_activity

OWNER = "01a13bbb-18e7-73b2-97d5-1bdee9d436d0"
OTHER = "01a12665-80d6-7de3-90c4-4d1b92bcaa9f"
TURN = "01a13bc4-f7f6-7d23-b706-77a31440e4d2"


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="console-edit-scope-")
        self.base = Path(self.temp.name).resolve()
        self.repo, self.other_repo = self.base / "repo", self.base / "other"
        for root in (self.repo, self.other_repo):
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
        self.rollout = self.base / "rollout.jsonl"
        self.database = self.base / "state.sqlite"
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("CREATE TABLE threads(id TEXT,cwd TEXT,rollout_path TEXT,archived INT,name TEXT,title TEXT,agent_path TEXT)")
            db.execute("INSERT INTO threads VALUES(?,?,?,?,?,?,?)", (OWNER, str(self.base), str(self.rollout), 0, "Audit", "long old prompt", "/root/audit"))
            db.commit()
        self.write({"type": "event_msg", "payload": {"type": "task_started", "turn_id": TURN}})
        self.store = ScopeStore(self.base / "claims", state_paths=[self.database])

    def tearDown(self):
        self.temp.cleanup()

    def write(self, event, append=False):
        with self.rollout.open("a" if append else "w", encoding="utf-8") as f:
            if not append:
                f.write(json.dumps({"type": "session_meta", "payload": {"id": OWNER}}) + "\n")
            f.write(json.dumps(event) + "\n")

    def resolve(self):
        return self.store.resolve(OWNER, self.rollout)

    def native(self, root=None):
        return desktop_codex_activity(root or self.repo, [self.database], scope_store=self.store)

    def guard(self, native=None):
        def git(root, *args):
            if args == ("rev-parse", "--git-common-dir"):
                return ".git"
            raise AssertionError(args)
        return RepositoryBindingDiscovery(git_reader=git, desktop_activity=native or self.native())

    def test_read_only_active_turn_and_wait_events_do_not_block(self):
        before = hashlib.sha256(self.database.read_bytes()).hexdigest(), self.rollout.read_bytes()
        self.store.declare(OWNER, "read_only")
        self.write({"type": "response_item", "payload": {"type": "function_call", "name": "wait_agent", "arguments": "SECRET"}}, True)
        self.assertEqual(self.resolve()["status"], "verified")
        self.assertIsNone(self.guard().busy_diagnostic(self.repo))
        self.assertNotIn("SECRET", json.dumps(self.native()))
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(), before[0])
        self.assertTrue(self.rollout.read_bytes().startswith(before[1]))

    def test_scoped_editor_blocks_only_exact_affected_repository(self):
        self.store.declare(OWNER, "edit", [self.repo])
        blocked = self.guard().busy_diagnostic(self.repo)
        self.assertEqual(blocked["code"], "activity_active")
        self.assertEqual(blocked["blockers"][0]["threadId"], OWNER)
        self.assertEqual(blocked["blockers"][0]["title"], "Audit")
        self.assertEqual(blocked["blockers"][0]["agentPath"], "/root/audit")
        self.assertIsNone(self.guard(self.native(self.other_repo)).busy_diagnostic(self.other_repo))
        self.assertIn("Desktop Codex", self.guard().busy_reason(self.repo))

    def test_unknown_editor_never_gets_exemption(self):
        blocked = self.guard().busy_diagnostic(self.repo)
        self.assertEqual(blocked["blockers"][0]["scope"]["status"], "undeclared")
        self.rollout.write_text('{"type":"event_msg","payload":', encoding="utf-8")
        self.assertIsNotNone(self.guard().busy_diagnostic(self.repo))

    def test_new_turn_and_repeated_start_invalidate_claim(self):
        for turn in ("new-turn", TURN):
            self.setUp_turn()
            self.store.declare(OWNER, "read_only")
            self.write({"type": "event_msg", "payload": {"type": "task_started", "turn_id": turn}}, True)
            self.assertEqual(self.resolve()["status"], "unverified")
            self.assertIsNotNone(self.guard().busy_diagnostic(self.repo))

    def setUp_turn(self):
        self.write({"type": "event_msg", "payload": {"type": "task_started", "turn_id": TURN}})

    def test_same_turn_context_after_compaction_preserves_claim(self):
        self.store.declare(OWNER, "read_only")
        self.write({"type": "turn_context", "payload": {"turn_id": TURN}}, True)
        self.assertEqual(self.resolve()["status"], "verified")

    def test_user_message_before_typed_start_invalidates_claim(self):
        self.store.declare(OWNER, "read_only")
        self.write({"type": "response_item", "payload": {"type": "message", "role": "user", "content": "SECRET"}}, True)
        self.assertEqual(self.resolve()["status"], "unverified")

    def test_initial_user_after_typed_turn_allows_declaration(self):
        self.write({"type": "turn_context", "payload": {"turn_id": TURN}}, True)
        self.write({"type": "response_item", "payload": {"type": "message", "role": "user", "content": "SECRET"}}, True)
        self.store.declare(OWNER, "read_only")
        self.assertEqual(self.resolve()["status"], "verified")
        self.write({"type": "response_item", "payload": {"type": "message", "role": "user", "content": "steering"}}, True)
        self.assertEqual(self.resolve()["status"], "unverified")
        self.store.declare(OWNER, "read_only")
        self.assertEqual(self.resolve()["status"], "verified")

    def test_replaced_rollout_same_bytes_invalidates_claim(self):
        self.store.declare(OWNER, "read_only")
        replacement = self.base / "replacement"
        replacement.write_bytes(self.rollout.read_bytes())
        os.replace(replacement, self.rollout)
        self.assertEqual(self.resolve()["status"], "unverified")

    def test_truncated_or_changed_anchor_invalidates_claim(self):
        self.store.declare(OWNER, "read_only")
        self.rollout.write_bytes(self.rollout.read_bytes()[:-2])
        self.assertEqual(self.resolve()["status"], "unverified")
        self.setUp_turn()
        self.store.declare(OWNER, "read_only")
        raw = self.rollout.read_text(encoding="utf-8").replace("task_started", "turn_started")
        self.rollout.write_text(raw, encoding="utf-8")
        self.assertEqual(self.resolve()["status"], "unverified")

    def test_partial_malformed_unknown_and_missing_turn_refuse_declaration(self):
        for raw in ('{"type":"event_msg"}', 'broken\n', '{}\n', '{"type":"event_msg","payload":{"type":"task_started"}}\n'):
            self.rollout.write_text(raw, encoding="utf-8")
            with self.assertRaises(ScopeError):
                self.store.declare(OWNER, "read_only")

    def test_malformed_claim_keeps_guard(self):
        self.store.declare(OWNER, "read_only")
        claim = self.store._file(OWNER)
        for value in ({}, {"schemaVersion": 1, "threadId": OTHER}, {"schemaVersion": 1, "threadId": OWNER, "kind": "scope", "mode": "edit", "editRoots": ["relative"]}):
            claim.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(self.resolve()["status"], "unverified")
            self.assertIsNotNone(self.guard().busy_diagnostic(self.repo))

    def test_exact_git_root_and_redirect_are_required(self):
        nested = self.repo / "nested"
        nested.mkdir()
        with self.assertRaises(ScopeError):
            self.store.declare(OWNER, "edit", [nested])
        with self.assertRaises(ScopeError):
            self.store.declare(OWNER, "edit", [self.base])
        with self.assertRaises(ScopeError):
            self.store.declare(OWNER, "read_only", [self.repo])

    def test_final_answer_is_typed_terminal_without_task_complete(self):
        self.write({"type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": "final_answer", "content": "SECRET"}}, True)
        self.assertEqual(scan_rollout(self.rollout)["state"], "idle")
        self.assertIsNone(self.guard().busy_diagnostic(self.repo))

    def receipt(self, status="interrupted"):
        p = self.base / "native-receipt.json"
        native = self.base / "native-read-thread.json"
        native.write_text(json.dumps({"schemaVersion": 1, "thread": {"id": OWNER, "status": "notLoaded"},
                                      "turns": [{"id": TURN, "status": status, "items": []}]}), encoding="utf-8")
        p.write_text(json.dumps({"source": "codex_app.read_thread", "threadId": OWNER, "turnId": TURN,
                                 "status": status, "rolloutFingerprint": scan_rollout(self.rollout)["fingerprint"],
                                 "nativeReceiptPath": str(native), "nativeReceiptSha256": hashlib.sha256(native.read_bytes()).hexdigest()}), encoding="utf-8")
        return p

    def test_pinned_terminal_attestation_and_any_append_invalidates(self):
        self.store.attest_terminal(OWNER, verified_turn_id=TURN, verified_status="interrupted", evidence_path=self.receipt())
        self.assertEqual(self.resolve()["status"], "terminal")
        self.assertIsNone(self.guard().busy_diagnostic(self.repo))
        self.write({"type": "event_msg", "payload": {"type": "token_count"}}, True)
        self.assertEqual(self.resolve()["status"], "unverified")
        self.assertIsNotNone(self.guard().busy_diagnostic(self.repo))

    def test_notloaded_or_receipt_change_cannot_attest(self):
        with self.assertRaises(ScopeError):
            self.store.attest_terminal(OWNER, verified_turn_id=TURN, verified_status="notLoaded", evidence_path=self.receipt("notLoaded"))
        receipt = self.receipt()
        self.write({"type": "event_msg", "payload": {"type": "token_count"}}, True)
        with self.assertRaises(ScopeError):
            self.store.attest_terminal(OWNER, verified_turn_id=TURN, verified_status="interrupted", evidence_path=receipt)

    def test_partial_or_wrong_turn_terminal_receipt_cannot_attest(self):
        receipt = self.receipt()
        with self.assertRaises(ScopeError):
            self.store.attest_terminal(OWNER, verified_turn_id="wrong", verified_status="interrupted", evidence_path=receipt)
        with self.rollout.open("ab") as f:
            f.write(b'{"type":')
        with self.assertRaises(ScopeError):
            self.store.attest_terminal(OWNER, verified_turn_id=TURN, verified_status="interrupted", evidence_path=receipt)

    def test_all_blockers_collected_not_first_active_only(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("INSERT INTO threads VALUES(?,?,?,?,?,?,?)", (OTHER, str(self.base), str(self.rollout), 0, "Other", "old", None))
            db.commit()
        self.assertEqual(len(self.native()["records"]), 2)
        self.assertEqual(len(self.guard().busy_diagnostic(self.repo)["blockers"]), 2)

    def test_owner_identity_changes_during_declare_fail(self):
        original = self.store.git_root_reader
        def raced(root):
            answer = original(root)
            self.write({"type": "event_msg", "payload": {"type": "task_started", "turn_id": "next"}}, True)
            return answer
        self.store.git_root_reader = raced
        with self.assertRaises(ScopeError):
            self.store.declare(OWNER, "edit", [self.repo])

    def test_bounded_scan_keeps_unknown_when_no_current_turn_available(self):
        self.rollout.write_bytes(b'{}\n' * (4 * 1024 * 1024 // 3 + 100))
        scan = scan_rollout(self.rollout)
        self.assertLessEqual(scan["bytesRead"], 4 * 1024 * 1024)
        self.assertEqual(scan["state"], "unknown")
        with self.assertRaises(ScopeError):
            self.store.declare(OWNER, "read_only")

    def test_cli_rejects_other_actor_even_with_valid_record(self):
        env = dict(os.environ, CODEX_THREAD_ID=OTHER)
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(Path(__file__).with_name("console-repository-edit-scope.py")),
                                 "declare", "--thread-id", OWNER, "--mode", "read-only", "--scope-dir", str(self.store.directory),
                                 "--state-path", str(self.database)], capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("only_owner_thread", result.stdout)
        self.assertFalse(self.store.directory.exists())

    def test_archived_owner_cannot_claim(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("UPDATE threads SET archived=1 WHERE id=?", (OWNER,))
            db.commit()
        with self.assertRaises(ScopeError):
            self.store.declare(OWNER, "read_only")

    def test_declared_editor_outside_cwd_is_guarded_even_after_new_turn(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("UPDATE threads SET cwd=? WHERE id=?", (str(self.repo), OWNER))
            db.commit()
        self.store.declare(OWNER, "edit", [self.other_repo])
        native = self.native(self.other_repo)
        self.assertEqual(len(native["records"]), 1)
        self.assertEqual(self.guard(native).busy_diagnostic(self.other_repo)["code"], "activity_active")
        self.write({"type": "event_msg", "payload": {"type": "task_started", "turn_id": "next"}}, True)
        native = self.native(self.other_repo)
        self.assertEqual(self.guard(native).busy_diagnostic(self.other_repo)["code"], "activity_scope_unknown")

    def test_terminal_receipt_tamper_or_missing_keeps_guard(self):
        receipt = self.receipt()
        self.store.attest_terminal(OWNER, verified_turn_id=TURN, verified_status="interrupted", evidence_path=receipt)
        receipt.write_text('{}', encoding="utf-8")
        self.assertEqual(self.resolve()["status"], "unverified")
        self.assertIsNotNone(self.guard().busy_diagnostic(self.repo))
        receipt.unlink()
        self.assertEqual(self.resolve()["status"], "unverified")

    def test_native_receipt_bytes_identity_status_and_running_command_verified(self):
        for change in ("missing", "tampered", "wrong-thread", "wrong-turn", "nonterminal", "running-command"):
            receipt = self.receipt()
            evidence = json.loads(receipt.read_text(encoding="utf-8"))
            native = Path(evidence["nativeReceiptPath"])
            if change == "missing":
                native.unlink()
            elif change == "tampered":
                native.write_text('{}', encoding="utf-8")
            else:
                raw = json.loads(native.read_text(encoding="utf-8"))
                if change == "wrong-thread":raw["thread"]["id"] = OTHER
                elif change == "wrong-turn":raw["turns"][0]["id"] = "next-turn"
                elif change == "nonterminal":raw["turns"][0]["status"] = "in_progress"
                else:raw["turns"][0]["items"] = [{"type": "commandExecution", "status": "in_progress"}]
                native.write_text(json.dumps(raw), encoding="utf-8")
                evidence["nativeReceiptSha256"] = hashlib.sha256(native.read_bytes()).hexdigest()
                receipt.write_text(json.dumps(evidence), encoding="utf-8")
            with self.assertRaises(ScopeError, msg=change):
                self.store.attest_terminal(OWNER, verified_turn_id=TURN, verified_status="interrupted", evidence_path=receipt)

    def test_native_receipt_changed_after_attestation_revokes_exemption(self):
        receipt = self.receipt()
        self.store.attest_terminal(OWNER, verified_turn_id=TURN, verified_status="interrupted", evidence_path=receipt)
        Path(json.loads(receipt.read_text(encoding="utf-8"))["nativeReceiptPath"]).write_text('{}', encoding="utf-8")
        self.assertEqual(self.resolve()["status"], "unverified")

    def test_sqlite_owner_and_rollout_session_owner_must_match(self):
        self.rollout.write_text(self.rollout.read_text(encoding="utf-8").replace(OWNER, OTHER), encoding="utf-8")
        with self.assertRaises(ScopeError):
            self.store.declare(OWNER, "read_only")
        native = self.native()
        self.assertEqual(native["records"][0]["reason"], "rollout_owner_mismatch")
        self.assertIsNotNone(self.guard(native).busy_diagnostic(self.repo))

    def test_malformed_state_shapes_remain_guarded(self):
        for snapshot in ([], {"jobs": None}, {"jobs": ["unknown"]}, {"native_app": {"threads": "unknown"}}):
            d = self.guard({"records": [], "warnings": []})
            d.workflow_snapshot = snapshot
            self.assertIsNotNone(d.busy_diagnostic(self.repo))
        for native in ([], {"records": None}, {"records": [None]}, {"records": [{"declaredRoots": None}]}):
            d = self.guard()
            d.desktop_activity = native
            self.assertIsNotNone(d.busy_diagnostic(self.repo))

    def test_scope_snapshot_inventory_skips_missing_files_and_refreshes(self):
        self.assertTrue(self.store.begin_snapshot())
        with patch.object(activity_module, "_read_json", wraps=activity_module._read_json) as read:
            for _ in range(100):
                self.assertEqual(self.store.candidate_roots(OWNER), [])
                self.assertEqual(self.resolve()["status"], "undeclared")
            self.assertEqual(read.call_count, 0)
        self.store.declare(OWNER, "edit", [self.repo])
        self.store.begin_snapshot()
        self.assertEqual(self.store.candidate_roots(OWNER), [str(self.repo)])
        self.assertEqual(self.resolve()["status"], "verified")


if __name__ == "__main__":
    unittest.main()
