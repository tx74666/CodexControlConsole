"""Isolated committed-result streams; fixtures never send a real App/Chat message."""
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_service import WorkflowError

spec = importlib.util.spec_from_file_location("relay_event_fixtures", Path(__file__).with_name("check-console-chat-relay.py"))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
work_spec = importlib.util.spec_from_file_location("desktop_work_event_fixtures", Path(__file__).with_name("check-workflow-codex-work-service.py"))
work_fixtures = importlib.util.module_from_spec(work_spec)
work_spec.loader.exec_module(work_fixtures)


class DialogueEvents(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RelayChecks(methodName="runTest")
        self.fixture.setUp()
        self.service = self.fixture.service
        self.streams = []

    def tearDown(self):
        for stream in self.streams:
            stream.close()
        self.fixture.tearDown()

    def subscribe(self, state=None, client=None, **options):
        state = state or self.fixture.state
        query = urlencode({"clientId": client or self.fixture.client, "sessionId": state["session"]["id"],
            "cursor": options.pop("cursor", state["resultCursor"])})
        stream = self.service.mobile_dialogue_subscribe(query, **options)
        self.streams.append(stream)
        return stream

    def begin_capture(self):
        sent, prepare = self.fixture.begin()
        self.fixture.controller.handle(self.fixture.prepared(prepare))
        return sent, prepare, self.fixture.evidence(prepare)

    def capture(self, prepare, evidence):
        self.fixture.controller.handle(self.fixture.envelope(prepare, "capture", evidence=evidence))

    def test_initial_snapshot_is_readonly_scoped_and_has_no_answer_text(self):
        before = self.service.data_dir.joinpath("workflow.sqlite3").read_bytes()
        original = sqlite3.connect
        calls = []
        def connect(path, *args, **kwargs):
            calls.append((path, kwargs))
            return original(path, *args, **kwargs)
        with patch.object(self.service, "_db", side_effect=AssertionError("stream GET cannot open write transaction")), patch("workflow_mobile_dialogue.sqlite3.connect", side_effect=connect):
            stream = self.subscribe()
            frame = stream.next_event(0)
            self.assertIsNone(stream.next_event(0))
        self.assertEqual(frame["event"], "dialogue.ready")
        self.assertEqual(set(frame["data"]), {"clientId", "sessionId", "recordId", "cursor", "jobId", "status"})
        self.assertIsNone(frame["data"]["jobId"])
        self.assertEqual(frame["data"]["status"], "idle")
        self.assertEqual(frame["data"]["cursor"], self.fixture.state["resultCursor"])
        self.assertTrue(all("mode=ro" in path and kwargs.get("uri") is True for path, kwargs in calls))
        self.assertEqual(before, self.service.data_dir.joinpath("workflow.sqlite3").read_bytes())

    def test_complete_capture_commits_then_wakes_exact_session_and_replay_is_quiet(self):
        sent, prepare, evidence = self.begin_capture()
        current = self.service.mobile_dialogue_get(urlencode({"clientId": self.fixture.client}))
        stream = self.subscribe(current)
        self.assertEqual(stream.next_event(0)["event"], "dialogue.ready")
        self.capture(prepare, evidence)
        frame = stream.next_event(0)
        self.assertEqual(frame["event"], "dialogue.result")
        self.assertEqual(frame["data"]["status"], "succeeded")
        self.assertEqual(frame["data"]["jobId"], sent["job"]["id"])
        with closing(sqlite3.connect(self.service.data_dir / "workflow.sqlite3")) as db:
            result = json.loads(db.execute("SELECT result FROM jobs WHERE id=?", (sent["job"]["id"],)).fetchone()[0])
            self.assertEqual(result["text"], evidence["answerText"])
        refreshed = self.service.mobile_dialogue_get(urlencode({"clientId": self.fixture.client}))
        observation = refreshed["execution"]["profileObservation"]
        self.assertEqual(observation, result["profileObservation"])
        self.assertEqual(observation["actualProfileObserved"], "Instant")
        self.assertFalse(observation["capabilitiesVerified"])
        self.assertFalse(refreshed["execution"]["actualReceipt"]["verified"])
        self.assertIsNone(refreshed["execution"]["actualReceipt"]["actualProfile"])
        self.capture(prepare, evidence)
        self.assertIsNone(stream.next_event(0))

    def test_committed_output_event_survives_stored_transport_failure(self):
        _, prepare, evidence = self.begin_capture()
        stream = self.subscribe(self.service.mobile_dialogue_get(urlencode({"clientId": self.fixture.client})))
        stream.next_event(0)
        def broken_transport(message):
            if message["type"] == "stored":
                raise OSError("isolated transport ended after database commit")
        self.fixture.controller.emit = broken_transport
        with self.assertRaises(OSError):
            self.capture(prepare, evidence)
        self.assertEqual(stream.next_event(0)["data"]["status"], "succeeded")

    def test_rollback_and_draft_edits_do_not_emit_result_event(self):
        sent, _, _ = self.begin_capture()
        stream = self.subscribe(self.service.mobile_dialogue_get(urlencode({"clientId": self.fixture.client})))
        stream.next_event(0)
        with self.assertRaises(ValueError):
            with self.service._db() as db:
                db.execute("UPDATE jobs SET status='failed',error='rollback fixture' WHERE id=?", (sent["job"]["id"],))
                raise ValueError("rollback")
        self.assertIsNone(stream.next_event(0))
        state = self.service.mobile_dialogue_get(urlencode({"clientId": self.fixture.client}))
        session = state["session"]
        self.service.mobile_dialogue_draft(fixtures.request(clientId=self.fixture.client, sessionId=session["id"],
            expectedRevision=session["revision"], text="未发草稿", attachmentIds=[], requestedProfile="fast"))
        self.assertIsNone(stream.next_event(0))

    def test_clear_closes_old_stream_and_late_a_never_notifies_b(self):
        _, prepare, evidence = self.begin_capture()
        state = self.service.mobile_dialogue_get(urlencode({"clientId": self.fixture.client}))
        old = self.subscribe(state)
        old.next_event(0)
        session = state["session"]
        new = self.service.mobile_dialogue_clear(fixtures.request(clientId=self.fixture.client,
            sessionId=session["id"], expectedRevision=session["revision"]))
        with self.assertRaises(WorkflowError) as failure:
            old.next_event(0)
        self.assertEqual(failure.exception.code, "dialogue_changed")
        old.close()
        stream = self.subscribe(new)
        stream.next_event(0)
        self.capture(prepare, evidence)
        self.assertIsNone(stream.next_event(0))
        self.assertIsNone(self.service.mobile_dialogue_get(urlencode({"clientId": self.fixture.client}))["execution"]["profileObservation"])

    def test_reconnection_uses_durable_cursor_without_creating_another_dispatch(self):
        _, prepare, evidence = self.begin_capture()
        state = self.service.mobile_dialogue_get(urlencode({"clientId": self.fixture.client}))
        cursor = state["resultCursor"]
        self.capture(prepare, evidence)
        recovered = self.subscribe(state, cursor=cursor).next_event(0)
        self.assertEqual(recovered["event"], "dialogue.result")
        self.assertEqual(recovered["data"]["status"], "succeeded")
        fresh = self.service.mobile_dialogue_get(urlencode({"clientId": self.fixture.client}))
        self.assertEqual(self.subscribe(fresh).next_event(0)["event"], "dialogue.ready")
        with self.service._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM idea_dispatches").fetchone()[0], 1)

    def test_capture_between_first_read_and_registration_is_not_lost(self):
        _, prepare, evidence = self.begin_capture()
        state = self.service.mobile_dialogue_get(urlencode({"clientId": self.fixture.client}))
        original, count = self.service._mobile_event_read, 0
        def racing_read(key):
            nonlocal count
            result = original(key)
            count += 1
            if count == 1:
                self.capture(prepare, evidence)
            return result
        with patch.object(self.service, "_mobile_event_read", side_effect=racing_read):
            stream = self.subscribe(state)
        self.assertEqual(stream.next_event(0)["data"]["status"], "succeeded")

    def test_two_changes_around_read_do_not_clear_a_new_notification(self):
        sent, _, _ = self.begin_capture()
        stream = self.subscribe(self.service.mobile_dialogue_get(urlencode({"clientId": self.fixture.client})))
        stream.next_event(0)
        with self.service._db() as db:
            db.execute("UPDATE jobs SET error='first' WHERE id=?", (sent["job"]["id"],))
        original = self.service._mobile_event_read
        def another_commit(key):
            result = original(key)
            with self.service._db() as db:
                db.execute("UPDATE jobs SET error='second' WHERE id=?", (sent["job"]["id"],))
            return result
        with patch.object(self.service, "_mobile_event_read", side_effect=another_commit):
            first = stream.next_event(0)
        second = stream.next_event(0)
        self.assertNotEqual(first["data"]["cursor"], second["data"]["cursor"])
        self.assertIsNone(stream.next_event(0))

    def test_waiting_reader_wakes_from_actual_commit_without_timer_read(self):
        sent, _, _ = self.begin_capture()
        stream = self.subscribe(self.service.mobile_dialogue_get(urlencode({"clientId": self.fixture.client})))
        stream.next_event(0)
        waiting, done, frames, failures = threading.Event(), threading.Event(), [], []
        original = stream.hub.wait
        def wait(token, version, timeout):
            waiting.set()
            return original(token, version, timeout)
        def reader():
            try:
                frames.append(stream.next_event(1))
            except BaseException as error:
                failures.append(error)
            finally:
                done.set()
        with patch.object(stream.hub, "wait", side_effect=wait):
            thread = threading.Thread(target=reader)
            thread.start()
            self.assertTrue(waiting.wait(1))
            with self.service._db() as db:
                db.execute("UPDATE jobs SET status='failed',error='known unsent fixture' WHERE id=?", (sent["job"]["id"],))
            self.assertTrue(done.wait(1))
            thread.join(1)
        self.assertFalse(failures)
        self.assertEqual(frames[0]["data"]["status"], "failed")

    def test_close_wakes_blocking_reader_and_releases_subscription(self):
        stream = self.subscribe()
        stream.next_event(0)
        waiting, done, failures = threading.Event(), threading.Event(), []
        original = stream.hub.wait
        def wait(token, version, timeout):
            waiting.set()
            return original(token, version, timeout)
        def reader():
            try:
                stream.next_event(1)
            except WorkflowError as error:
                failures.append(error.code)
            finally:
                done.set()
        with patch.object(stream.hub, "wait", side_effect=wait):
            thread = threading.Thread(target=reader)
            thread.start()
            self.assertTrue(waiting.wait(1))
            stream.close()
            self.assertTrue(done.wait(1))
            thread.join(1)
        self.assertEqual(failures, ["dialogue_connection_closed"])
        self.assertEqual(stream.hub.keys(), ())

    def test_idle_wait_never_reads_database_and_rechecks_pair_authorization(self):
        checks = []
        allowed = True
        def authorize():
            checks.append(True)
            if not allowed:
                raise WorkflowError("配对已撤销。", 403, "phone_not_paired")
        stream = self.subscribe(authorize=authorize)
        stream.next_event(0)
        with patch.object(self.service, "_mobile_event_read", side_effect=AssertionError("idle is not polling")), patch.object(self.service, "_db", side_effect=AssertionError("idle cannot recover jobs")):
            self.assertIsNone(stream.next_event(.001))
            allowed = False
            with self.assertRaises(WorkflowError):
                stream.next_event(0)
        self.assertGreaterEqual(len(checks), 6)

    def test_query_identity_and_connection_limit_do_not_expand_permissions(self):
        session = self.fixture.state["session"]
        base = urlencode({"clientId": self.fixture.client, "sessionId": session["id"]})
        for query in (base + "&clientId=" + self.fixture.client, base + "&recordId=" + session["recordId"],
                      base + "&cursor=bad", urlencode({"clientId": self.fixture.client.upper(), "sessionId": session["id"]}),
                      urlencode({"clientId": str(uuid.uuid4()), "sessionId": session["id"]}),
                      urlencode({"clientId": self.fixture.client, "sessionId": uuid.uuid4().hex})):
            with self.subTest(query=query), self.assertRaises(WorkflowError):
                self.service.mobile_dialogue_subscribe(query)
        for _ in range(16):
            self.subscribe()
        with self.assertRaises(WorkflowError) as failure:
            self.subscribe()
        self.assertEqual(failure.exception.status, 429)
        self.streams[0].close()
        self.subscribe()
        for stream in self.streams:
            stream.close()
        self.assertEqual(self.service._mobile_result_hub.keys(), ())

    def test_known_unsent_unsupported_profile_notifies_failure_without_send(self):
        self.fixture.approve()
        sent, _ = self.fixture.send("high")
        stream = self.subscribe(self.fixture.state)
        stream.next_event(0)
        self.fixture.controller.committed([sent["job"]["appDispatch"]["id"]])
        self.assertEqual(stream.next_event(0)["data"]["status"], "failed")
        self.assertFalse(any(item["type"] in {"prepare", "commitSend"} for item in self.fixture.messages))


class DesktopWorkDialogueEvents(unittest.TestCase):
    """Actual durable service actions with only an inert controller and temp data."""
    def setUp(self):
        self.fixture = work_fixtures.ServiceChecks(methodName="runTest")
        self.fixture.setUp()
        self.service = self.fixture.service
        self.client = str(uuid.uuid4())
        self.state = self.service.mobile_dialogue_open(work_fixtures.body(clientId=self.client))
        self.streams = []

    def tearDown(self):
        for stream in self.streams:
            stream.close()
        self.fixture.tearDown()

    def subscribe(self, state=None):
        state = state or self.state
        session = state["session"]
        stream = self.service.mobile_dialogue_subscribe(urlencode({"clientId": session["clientId"], "sessionId": session["id"]}))
        self.streams.append(stream)
        stream.next_event(0)
        return stream

    def test_desktop_same_current_record_progress_and_output_wake_only_after_commit(self):
        self.fixture.record_id = self.state["session"]["recordId"]
        stream = self.subscribe()
        job, _ = self.fixture.running()
        stream.next_event(0)  # Durable submit/start changed the same source.
        with self.assertRaises(ValueError):
            with self.service._db() as db:
                db.execute("UPDATE jobs SET log='rolled back local Work progress' WHERE id=?", (job["id"],))
                raise ValueError("rollback fixture")
        self.assertIsNone(stream.next_event(0))
        self.assertTrue(self.fixture.emit(self.fixture.event(job, "progress", turnId="turn_fixture",
            kind="item/agentMessage/delta", itemId="agent", text="来自桌面同一Agent的真实fixture进度")))
        progress = stream.next_event(0)
        self.assertEqual(progress["event"], "dialogue.result")
        self.assertEqual(progress["data"]["recordId"], job["recordId"])
        self.assertEqual(progress["data"]["status"], "idle", "Work cannot masquerade as a completed Chat")
        self.assertIsNone(progress["data"]["jobId"])
        self.assertTrue(self.fixture.emit(self.fixture.terminal(job)))
        completed = stream.next_event(0)
        self.assertNotEqual(completed["data"]["cursor"], progress["data"]["cursor"])
        result = self.service.mobile_dialogue_get("clientId=" + self.client)
        self.assertEqual(result["session"], self.state["session"])
        self.assertEqual(result["detail"]["messages"][-1]["text"], "Actual complete report 中文")
        self.assertFalse(result["execution"]["actualReceipt"]["verified"])

    def test_foreign_record_desktop_progress_cannot_wake_current_phone(self):
        stream = self.subscribe()
        job, _ = self.fixture.running()  # The fixture's separate original record.
        self.assertNotEqual(job["recordId"], self.state["session"]["recordId"])
        self.assertTrue(self.fixture.emit(self.fixture.event(job, "progress", turnId="turn_fixture",
            kind="item/agentMessage/delta", itemId="foreign", text="different record")))
        self.assertIsNone(stream.next_event(0))

    def test_desktop_stale_task_and_cleared_discussion_exclude_later_progress(self):
        idea = self.service.incubator_create(work_fixtures.body(title="明确原任务", body="原版"))["idea"]
        opened = self.service.mobile_dialogue_open(work_fixtures.body(clientId=self.client, ideaId=idea["id"], expectedIdeaRevision=idea["revision"]))
        self.fixture.record_id = opened["session"]["recordId"]
        job, _ = self.fixture.running()
        stream = self.subscribe(opened)
        self.service.incubator_update(work_fixtures.body(id=idea["id"], expectedRevision=idea["revision"], body="新的已保存来源"))
        stream.next_event(0)  # Scope removal itself may notify; later Work may not.
        self.assertTrue(self.fixture.emit(self.fixture.event(job, "progress", turnId="turn_fixture",
            kind="item/agentMessage/delta", itemId="stale", text="old original task version")))
        self.assertIsNone(stream.next_event(0))
        session = opened["session"]
        new = self.service.mobile_dialogue_clear(work_fixtures.body(clientId=self.client, sessionId=session["id"], expectedRevision=session["revision"]))
        fresh = self.subscribe(new)
        self.assertTrue(self.fixture.emit(self.fixture.event(job, "progress", turnId="turn_fixture",
            kind="item/agentMessage/delta", itemId="cleared", text="old discussion")))
        self.assertIsNone(fresh.next_event(0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
