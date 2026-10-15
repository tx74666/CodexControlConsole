"""Isolated database read and invalidation checks; never opens user data."""
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_service import WorkflowService


class ReadPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = WorkflowService(self.temp.name, recover_jobs=False)
        self.path = Path(self.temp.name) / "workflow.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    def test_repeated_reads_run_no_schema_or_data_writes_and_preserve_bytes(self):
        statements = []
        connect = sqlite3.connect
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()

        def traced(*args, **kwargs):
            db = connect(*args, **kwargs)
            db.set_trace_callback(statements.append)
            return db

        with patch("workflow_service.sqlite3.connect", side_effect=traced):
            for _ in range(10):
                self.assertFalse(self.service.status()["backgroundEnabled"])
        self.assertFalse(any(sql.lstrip().upper().startswith(("CREATE", "INSERT", "UPDATE", "DELETE")) for sql in statements))
        self.assertEqual(before, hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_external_schema_change_is_rechecked_and_missing_index_repaired(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DROP INDEX message_records")
        with self.service._db() as db:
            self.assertIsNotNone(db.execute("SELECT name FROM sqlite_master WHERE name='message_records'").fetchone())

    def test_replacement_database_with_same_generation_is_initialized(self):
        previous = self.service._schema_key[2]
        replacement = self.path.with_suffix(".replacement")
        with closing(sqlite3.connect(replacement)) as db, db:
            db.execute(f"PRAGMA schema_version={previous}")
        replacement.replace(self.path)
        with self.service._db() as db:
            self.assertEqual(self.service._setting(db, "revision"), 0)
            self.assertIsNotNone(db.execute("SELECT name FROM sqlite_master WHERE name='jobs'").fetchone())

    def test_external_data_update_is_visible_without_schema_change(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO settings VALUES ('background','true')")
        self.assertTrue(self.service.background_enabled)

    def test_reads_skip_second_subscriber_snapshot_and_notification(self):
        with patch.object(self.service, "_mobile_events_snapshot", return_value={}) as snapshot, patch.object(self.service, "_mobile_events_committed") as committed:
            with self.service._db() as db:
                db.execute("SELECT COUNT(*) FROM messages").fetchone()
            self.assertEqual(snapshot.call_count, 1)
            committed.assert_not_called()

    def test_write_notifies_only_after_commit_and_rollback_stays_quiet(self):
        def observe(before, after):
            with closing(sqlite3.connect(self.path)) as db, db:
                self.assertEqual(db.execute("SELECT value FROM settings WHERE key='probe'").fetchone()[0], "true")

        with patch.object(self.service, "_mobile_events_snapshot", return_value={}) as snapshot, patch.object(self.service, "_mobile_events_committed", side_effect=observe) as committed:
            with self.service._db() as db:
                self.service._set_setting(db, "probe", True)
            self.assertEqual(snapshot.call_count, 2)
            committed.assert_called_once()
            committed.reset_mock()
            with self.assertRaises(ValueError):
                with self.service._db() as db:
                    self.service._set_setting(db, "probe", False)
                    raise ValueError("rollback fixture")
            committed.assert_not_called()
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute("SELECT value FROM settings WHERE key='probe'").fetchone()[0], "true")


if __name__ == "__main__":
    unittest.main()
