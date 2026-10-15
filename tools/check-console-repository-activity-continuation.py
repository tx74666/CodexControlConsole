"""Bounded long-turn proof tests; only temporary fixture Git/SQLite/rollout data."""
from __future__ import annotations
import importlib.util
from contextlib import closing
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import console_repository_activity as activity
from console_repository_activity import ScopeError, MAX_SCAN_BYTES, MAX_APPEND_BYTES, scan_rollout

spec = importlib.util.spec_from_file_location("scope_base_fixtures", Path(__file__).with_name("check-console-repository-activity.py"))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
OWNER, OTHER, TURN = fixtures.OWNER, fixtures.OTHER, fixtures.TURN


class ContinuationTests(unittest.TestCase):
    setUp = fixtures.ActivityTests.setUp
    tearDown = fixtures.ActivityTests.tearDown
    write = fixtures.ActivityTests.write
    resolve = fixtures.ActivityTests.resolve
    native = fixtures.ActivityTests.native
    guard = fixtures.ActivityTests.guard

    def pad(self, length):
        empty = json.dumps({"type": "response_item", "payload": {"type": "reasoning", "padding": ""}}, separators=(",", ":")).encode() + b"\n"
        assert length >= len(empty)
        line = json.dumps({"type": "response_item", "payload": {"type": "reasoning", "padding": "x" * (length - len(empty))}}, separators=(",", ":")).encode() + b"\n"
        self.assertEqual(len(line), length)
        with self.rollout.open("ab") as stream:
            stream.write(line)

    def prepare(self, mode="read_only"):
        # The initial declaration can still independently find its typed turn.
        self.pad(MAX_SCAN_BYTES - 32768 - self.rollout.stat().st_size)
        self.claim = self.store.declare(OWNER, mode, [] if mode == "read_only" else [self.repo])
        self.original_anchor = dict(self.claim["anchor"])

    def forgotten_tail(self, append=65536):
        self.prepare()
        self.pad(append)
        scan = scan_rollout(self.rollout)
        self.assertEqual((scan["state"], scan["reason"]), ("unknown", "no_boundary_in_bounded_tail"))
        return scan

    def test_small_append_recovers_verified_typed_turn_beyond_scan_window(self):
        self.forgotten_tail()
        result = self.resolve()
        self.assertEqual((result["status"], result["mode"], result["turnId"]), ("verified", "read_only", TURN))
        self.assertEqual(result["lifecycleProof"]["appendBytes"], 65536)
        self.assertEqual(result["lifecycleProof"]["source"], "verified_anchor_continuation")
        record = self.native()["records"][0]
        self.assertEqual(record["state"], "active")
        self.assertEqual(record["rawReason"], "no_boundary_in_bounded_tail")
        self.assertIsNone(self.guard().busy_diagnostic(self.repo))

    def test_actual_six_mib_append_streamed_without_advancing_anchor(self):
        self.forgotten_tail(6 * 1024 * 1024)
        result = self.resolve()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["lifecycleProof"]["appendBytes"], 6 * 1024 * 1024)
        changed = self.store.declare(OWNER, "edit", [self.repo])
        self.assertEqual(changed["anchor"], self.original_anchor)
        self.assertEqual(changed["turnId"], TURN)
        self.assertEqual(changed["editRoots"], [str(self.repo)])
        self.assertEqual(self.guard().busy_diagnostic(self.repo)["code"], "activity_active")
        saved = self.store.declare(OWNER, "read_only")
        self.assertEqual(saved["anchor"], self.original_anchor)
        self.assertIsNone(self.guard().busy_diagnostic(self.repo))

    def test_exact_edit_scope_preserved_and_other_repository_not_blocked(self):
        self.prepare("edit")
        self.pad(65536)
        result = self.resolve()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["editRoots"], [str(self.repo)])
        self.assertEqual(self.guard().busy_diagnostic(self.repo)["code"], "activity_active")
        self.assertIsNone(self.guard(self.native(self.other_repo)).busy_diagnostic(self.other_repo))

    def test_no_prior_verified_claim_cannot_seed_unknown_tail(self):
        self.forgotten_tail()
        self.store._file(OWNER).unlink()
        self.assertEqual(self.resolve()["status"], "undeclared")
        with self.assertRaises(ScopeError):
            self.store.declare(OWNER, "read_only")

    def test_hidden_user_before_latest_four_mib_invalidates_old_claim(self):
        self.prepare()
        self.write({"type": "response_item", "payload": {"type": "message", "role": "user", "content": "new task"}}, True)
        self.pad(6 * 1024 * 1024)
        self.assertEqual(scan_rollout(self.rollout)["reason"], "no_boundary_in_bounded_tail")
        self.assertEqual(self.resolve()["status"], "unverified")
        self.assertIsNotNone(self.guard().busy_diagnostic(self.repo))
        with self.assertRaises(ScopeError):
            self.store.declare(OWNER, "read_only")

    def test_hidden_user_also_invalidates_when_latest_context_has_same_turn(self):
        self.prepare()
        self.write({"type": "response_item", "payload": {"type": "message", "role": "user"}}, True)
        self.pad(6 * 1024 * 1024)
        self.write({"type": "turn_context", "payload": {"turn_id": TURN}}, True)
        self.assertEqual(scan_rollout(self.rollout)["state"], "active")
        self.assertEqual(self.resolve()["status"], "unverified")
        # A new explicit owner declaration may use this genuinely fresh boundary.
        renewed = self.store.declare(OWNER, "edit", [self.repo])
        self.assertNotEqual(renewed["anchor"], self.original_anchor)
        self.assertEqual(self.resolve()["status"], "verified")

    def test_any_hidden_start_context_terminal_or_session_refuses_continuation(self):
        events = [
            {"type": "event_msg", "payload": {"type": "task_started", "turn_id": TURN}},
            {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "new"}},
            {"type": "event_msg", "payload": {"type": "task_started"}},
            {"type": "turn_context", "payload": {"turn_id": TURN}},
            {"type": "event_msg", "payload": {"type": "task_complete"}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": "final_answer"}},
            {"type": "session_meta", "payload": {"id": OWNER}},
        ]
        for event in events:
            self.write({"type": "event_msg", "payload": {"type": "task_started", "turn_id": TURN}})
            self.prepare()
            self.write(event, True)
            self.pad(6 * 1024 * 1024)
            self.assertEqual(self.resolve()["status"], "unverified", event)
            with self.assertRaises(ScopeError, msg=str(event)):
                self.store.declare(OWNER, "read_only")

    def test_malformed_or_partial_append_never_grants(self):
        self.prepare()
        with self.rollout.open("ab") as stream:stream.write(b'broken\n')
        self.pad(6 * 1024 * 1024)
        self.assertEqual(self.resolve()["status"], "unverified")

    def test_native_user_event_and_null_typed_payloads_never_clear(self):
        for event in ({"type": "event_msg", "payload": {"type": "user_message", "message": "new"}},
                      {"type": "response_item", "payload": None},
                      {"type": "session_meta", "payload": None},
                      {"type": "", "payload": {}},
                      {"type": "event_msg", "payload": {"type": ""}},
                      {"type": "\t", "payload": {}}):
            self.write({"type": "event_msg", "payload": {"type": "task_started", "turn_id": TURN}})
            self.prepare()
            self.write(event, True)
            self.pad(6 * 1024 * 1024)
            self.assertEqual(self.resolve()["status"], "unverified", event)
            self.assertIsNotNone(self.guard().busy_diagnostic(self.repo), event)
            with self.assertRaises(ScopeError):
                self.store.declare(OWNER, "read_only")
        self.write({"type": "event_msg", "payload": {"type": "task_started", "turn_id": TURN}})
        self.prepare()
        self.pad(65536)
        with self.rollout.open("ab") as stream:stream.write(b'{"type":')
        self.assertEqual(self.resolve()["status"], "unverified")

    def test_append_budget_overflow_refuses_before_streaming(self):
        self.prepare()
        for size in (6 * 1024 * 1024, 6 * 1024 * 1024, 4 * 1024 * 1024 + 1):self.pad(size)
        self.assertEqual(self.rollout.stat().st_size - self.claim["anchor"]["size"], MAX_APPEND_BYTES + 1)
        with patch.object(activity, "_stream_range", wraps=activity._stream_range) as stream:
            self.assertEqual(self.resolve()["status"], "unverified")
            self.assertEqual(stream.call_count, 0)

    def test_tampered_anchor_turn_cwd_or_mode_refuses(self):
        self.forgotten_tail()
        original = json.loads(self.store._file(OWNER).read_text(encoding="utf-8"))
        for field in ("turn", "mode", "cwd", "hash", "size", "null-anchor"):
            value = json.loads(json.dumps(original))
            if field == "turn":value["turnId"] = "wrong"
            elif field == "mode":value["mode"] = "invalid"
            elif field == "cwd":value["cwd"] = str(self.other_repo)
            elif field == "hash":value["anchor"]["tailSha256"] = "0" * 64
            elif field == "size":value["anchor"]["size"] -= 1
            else:value["anchor"] = None
            self.store._file(OWNER).write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(self.resolve()["status"], "unverified", field)

    def test_cwd_change_rejects_current_scope(self):
        self.forgotten_tail()
        import sqlite3
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("UPDATE threads SET cwd=? WHERE id=?", (str(self.other_repo), OWNER))
            db.commit()
        self.assertEqual(self.resolve()["status"], "unverified")

    def test_resize_during_streaming_invalidates_proof(self):
        self.forgotten_tail(6 * 1024 * 1024)
        original = activity._stream_range
        changed = []
        def raced(stream, start, end, consume=None, **kwargs):
            if consume is not None and start == self.original_anchor["size"]:
                original_read = stream.read
                def resize(n=-1):
                    data = original_read(n)
                    if not changed:
                        changed.append(True)
                        self.write({"type": "event_msg", "payload": {"type": "token_count"}}, True)
                    return data
                # Actual open buffered readers permit a local read hook; this is
                # only a temporary fixture, never a native rollout.
                stream.read = resize
            return original(stream, start, end, consume, **kwargs)
        with patch.object(activity, "_stream_range", side_effect=raced):
            self.assertEqual(self.resolve()["status"], "unverified")
        self.assertTrue(changed)

    def test_replacement_shrink_and_changed_prefix_reject(self):
        self.forgotten_tail()
        replacement = self.base / "replacement.jsonl"
        replacement.write_bytes(self.rollout.read_bytes())
        replacement.replace(self.rollout)
        self.assertEqual(self.resolve()["status"], "unverified")
        self.rollout.write_bytes(self.rollout.read_bytes()[:self.claim["anchor"]["size"] - 1])
        self.assertEqual(self.resolve()["status"], "unverified")
        self.write({"type": "event_msg", "payload": {"type": "task_started", "turn_id": TURN}})
        self.prepare()
        self.pad(65536)
        with self.rollout.open("r+b") as stream:
            first = stream.read(512).replace(OWNER.encode(), OTHER.encode())
            stream.seek(0);stream.write(first)
        self.assertEqual(self.resolve()["status"], "unverified")

    def test_natural_final_stays_idle_and_no_claim_is_used_to_fake_terminal(self):
        self.forgotten_tail()
        self.write({"type": "event_msg", "payload": {"type": "task_complete", "turn_id": TURN}}, True)
        self.assertEqual(scan_rollout(self.rollout)["state"], "idle")
        self.assertIsNone(self.guard().busy_diagnostic(self.repo))
        self.assertNotEqual(self.resolve()["status"], "terminal")

    def test_opened_descriptor_substitution_cannot_grant_or_fake_idle(self):
        self.prepare()
        user_start = self.rollout.stat().st_size
        self.write({"type": "response_item", "payload": {"type": "message", "role": "user", "content": "new task"}}, True)
        user_end = self.rollout.stat().st_size
        self.pad(6 * 1024 * 1024)
        actual_scan = scan_rollout(self.rollout)
        source = bytearray(self.rollout.read_bytes())
        template = {"type": "event_msg", "payload": {"type": "token_count", "padding": ""}}
        empty = json.dumps(template, separators=(",", ":")).encode() + b"\n"
        template["payload"]["padding"] = "x" * (user_end - user_start - len(empty))
        replacement = json.dumps(template, separators=(",", ":")).encode() + b"\n"
        self.assertEqual(len(replacement), user_end - user_start)
        source[user_start:user_end] = replacement
        alternate = self.base / "substituted-reader.jsonl"
        alternate.write_bytes(source)
        old_open = Path.open
        def substituted(path, *args, **kwargs):
            return old_open(alternate if path == self.rollout else path, *args, **kwargs)
        with patch.object(Path, "open", substituted), patch.object(activity, "_stream_range", wraps=activity._stream_range) as stream:
            self.assertEqual(self.store.resolve(OWNER, self.rollout, scan=actual_scan)["status"], "unverified")
            self.assertEqual(stream.call_count, 0)  # Reject before reading spoofed proof bytes.
            self.assertEqual(scan_rollout(self.rollout)["reason"], "rollout_changed_during_read")
            self.assertIsNotNone(self.guard().busy_diagnostic(self.repo))

    def test_claim_mode_flip_during_proof_cannot_grant_stale_readonly(self):
        self.forgotten_tail()
        original = activity.ScopeStore._scope_proof
        changed = []
        def mode_flip(value, scan, **kwargs):
            result = original(value, scan, **kwargs)
            if result is not None and not changed:
                changed.append(True)
                fresh = json.loads(self.store._file(OWNER).read_text(encoding="utf-8"))
                fresh.update(mode="edit", editRoots=[str(self.repo)])
                self.store._file(OWNER).write_text(json.dumps(fresh), encoding="utf-8")
            return result
        with patch.object(activity.ScopeStore, "_scope_proof", side_effect=mode_flip):
            self.assertEqual(self.resolve()["status"], "unverified")
        self.assertTrue(changed)


if __name__ == "__main__":
    unittest.main()
