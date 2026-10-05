"""Disposable relay checks. Synthetic DOM contracts are not real Chat evidence."""
import copy
from contextlib import closing
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_chat_relay import (APPROVAL_KEY, ATTEMPT_PREFIX, EXTENSION_ID, HOST_NAME, MAX_FRAME, PROTOCOL,
                                 ChatRelayBroker, ChatRelayController, approval, decode, encode, fixed_approval, now, read_approval)
from workflow_service import WorkflowService

spec = importlib.util.spec_from_file_location("isolated_native_host", Path(__file__).with_name("console-chat-relay-host.py"))
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


def request(**fields):
    return {"requestId": str(uuid.uuid4()), **fields}


class RelayChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="console-chat-relay-isolated-")
        self.root = Path(self.temp.name)
        self.environment = patch.dict("os.environ", {"LOCALAPPDATA": str(self.root)})
        self.environment.start()
        project = self.root / "project"
        project.mkdir()
        self.service = WorkflowService(self.root / "CodexControlConsole" / "workflow-private", projects=[{"id": "isolated", "name": "Fixture", "root": str(project), "capabilities": ["result_import"]}])
        self.client = str(uuid.uuid4())
        self.state = self.service.mobile_dialogue_open(request(clientId=self.client))
        self.messages, self.commits = [], []
        self.controller = ChatRelayController(self.service, self.messages.append)
        self.config = {"version": 1, "enabled": True, "hostName": HOST_NAME, "extensionId": EXTENSION_ID,
                       "pipeName": "\\\\.\\pipe\\codex-console-chat-relay-" + uuid.uuid4().hex, "authKeyHex": "f" * 64,
                       "dataDir": str(self.service.data_dir), "approvalConfirmedAt": now(), "approvalVersion": 1,
                       "domContract": {"version": 1, "verified": True, "surface": "chrome", "capturedAt": now(),
                                       "source": "cua", "observationSha256": "a" * 64,
                                       "selectors": {key: "#isolated-" + key for key in ("composer", "profile", "messages", "userText", "assistantText", "completion", "send", "stop", "login", "chatMode")},
                                       "profiles": {"fast": {"label": "Instant"}}}}

    def tearDown(self):
        self.service._dispatch_commit_notifier = None
        self.service.shutdown()
        self.temp.cleanup()
        self.environment.stop()

    def approve(self):
        with self.service._db() as db:
            self.service._set_setting(db, APPROVAL_KEY, self.config)
        self.service.data_dir.joinpath("console-chat-relay-approved.json").write_text(json.dumps(self.config), encoding="utf-8")
        self.controller.handle({"protocol": PROTOCOL, "type": "ready", "hostName": HOST_NAME, "clientReady": True})

    def send(self, profile="fast", text="你好 · isolated"):
        session = self.state["session"]
        body = request(clientId=self.client, sessionId=session["id"], expectedRevision=session["revision"], text=text, attachmentIds=[], requestedProfile=profile)
        sent = self.service.mobile_dialogue_send(body)
        self.state = sent
        return sent, body

    def new_session(self):
        self.client = str(uuid.uuid4())
        self.state = self.service.mobile_dialogue_open(request(clientId=self.client))

    def begin(self):
        self.approve()
        sent, _ = self.send()
        identifier = sent["job"]["appDispatch"]["id"]
        self.controller.committed([identifier])
        return sent, next(message for message in self.messages if message["type"] == "prepare")

    def envelope(self, prepare, kind, **fields):
        return {"protocol": PROTOCOL, "type": kind, "dispatchId": prepare["dispatchId"], "attemptId": prepare["attemptId"], **fields}

    def prepared(self, prepare):
        return self.envelope(prepare, "prepared", observation={"url": "https://chatgpt.com/", "chatMode": True, "loginVerified": True,
                            "emptyComposer": True, "observedProfile": "Instant", "completionInitiallyPresent": False,
                            "surface": prepare["domContract"]["surface"], "observationSha256": "a" * 64, "profileDom": {"text": "Thinking effortInstant", "reasoningEffort": "none"}})

    def evidence(self, prepare):
        return {"source": "browser_dom", "conversationUrl": "https://chatgpt.com/c/" + str(uuid.uuid4()),
                "sourceUserMessageId": str(uuid.uuid4()), "assistantMessageId": str(uuid.uuid4()),
                "sourceUnitKey": "fallback-turn-0:0:user", "assistantUnitKey": "fallback-turn-0:1:assistant",
                "promptText": prepare["prompt"], "answerText": "你好！这是隔离回执。",
                "completion": {"text": "Response complete", "observedAfterCommit": True, "stopPresent": False},
                "profile": {"requestedProfile": "fast", "observedBefore": "Instant", "observedAfter": "Instant"}, "observedAt": now()}

    def attempt(self, identifier):
        with self.service._db() as db:
            return self.service._setting(db, ATTEMPT_PREFIX + identifier)

    def row(self, identifier):
        with self.service._db() as db:
            return dict(self.service._dispatch(db, identifier))

    def test_default_disabled_does_not_provision_or_start(self):
        before = self.service.data_dir.joinpath("workflow.sqlite3").read_bytes()
        broker = ChatRelayBroker(self.service)
        self.assertFalse(broker.public_status()["enabled"])
        with patch.dict("os.environ", {"LOCALAPPDATA": str(self.root)}):
            self.assertFalse(broker.start())
        self.assertIsNone(self.service._dispatch_commit_notifier)
        self.assertEqual(before, self.service.data_dir.joinpath("workflow.sqlite3").read_bytes())
        absent = self.root / "absent"
        self.assertIsNone(read_approval(absent))
        self.assertFalse(absent.exists())

    def test_commit_notification_observes_committed_database_and_rollback_has_no_event(self):
        test = self
        class Notify:
            def notify_committed(self, identifiers):
                with closing(sqlite3.connect(test.service.data_dir / "workflow.sqlite3")) as db:
                    for identifier in identifiers:
                        row = db.execute("SELECT status,user_confirmed_at FROM idea_dispatches WHERE id=?", (identifier,)).fetchone()
                        test.assertEqual(row[0], "pending")
                        test.assertTrue(row[1])
                test.commits.append(identifiers)
        self.service._dispatch_commit_notifier = Notify()
        sent, body = self.send()
        self.assertEqual(self.commits, [[sent["job"]["appDispatch"]["id"]]])
        self.service.mobile_dialogue_send(body)
        self.assertEqual(len(self.commits), 1)
        with self.assertRaises(ValueError):
            with self.service._db() as db:
                old = db.execute("SELECT * FROM idea_dispatches LIMIT 1").fetchone()
                values = list(old)
                values[0], values[2] = uuid.uuid4().hex, str(uuid.uuid4())
                db.execute("INSERT INTO idea_dispatches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
                raise ValueError("rollback fixture")
        self.assertEqual(len(self.commits), 1)

    def test_read_transaction_with_no_open_dispatch_never_scans_completed_history(self):
        self.approve()
        sent, _ = self.send("high")
        self.controller.committed([sent["job"]["appDispatch"]["id"]])
        self.assertEqual(self.row(sent["job"]["appDispatch"]["id"])["status"], "failed")
        class Notify:
            def notify_released(self, identifiers):
                raise AssertionError("an unchanged old failure is not a release event")
        self.service._dispatch_commit_notifier = Notify()
        statements = []
        with self.service._db() as db:
            db.set_trace_callback(statements.append)
            db.execute("SELECT value FROM settings WHERE key=?", (APPROVAL_KEY,)).fetchone()
        self.assertFalse(any("SELECT" in sql.upper() and "idea_dispatches" in sql and "completed" in sql for sql in statements))

    def test_save_and_draft_do_not_dispatch(self):
        class Notify:
            def notify_committed(self, identifiers):
                raise AssertionError("saving must not produce dispatch events")
        self.service._dispatch_commit_notifier = Notify()
        session = self.state["session"]
        body = request(clientId=self.client, sessionId=session["id"], expectedRevision=session["revision"], text="只保存", attachmentIds=[], requestedProfile="fast")
        state = self.service.mobile_dialogue_save(body)
        with self.service._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM idea_dispatches").fetchone()[0], 0)
        self.assertTrue(state["session"]["ideaId"])

    def test_hello_and_status_never_claim(self):
        self.approve()
        self.controller.client_ready = False
        sent, _ = self.send()
        identifier = sent["job"]["appDispatch"]["id"]
        self.controller.committed([identifier])
        for kind in ("hello", "status"):
            self.controller.handle({"protocol": PROTOCOL, "type": kind, "hostName": HOST_NAME})
        self.assertEqual(self.row(identifier)["status"], "pending")
        self.assertFalse(any(message["type"] == "prepare" for message in self.messages))

    def test_unverified_iab_contract_never_claims(self):
        self.config["domContract"].update(verified=False, surface="iab")
        self.config["domContract"]["selectors"]["stop"] = None
        self.approve()
        sent, _ = self.send()
        identifier = sent["job"]["appDispatch"]["id"]
        self.controller.committed([identifier])
        self.assertEqual(self.row(identifier)["status"], "pending")
        self.assertIsNone(self.attempt(identifier))

    def test_edge_round_trip_preserves_cua_surface_and_exact_attribution(self):
        self.config["domContract"]["surface"] = "edge"
        sent, prepare = self.begin()
        self.assertEqual(prepare["domContract"]["surface"], "edge")
        self.assertEqual(prepare["domContract"]["source"], "cua")
        self.assertTrue(self.controller.status()["clientReady"])
        prepared = self.prepared(prepare)
        self.assertEqual(prepared["observation"]["surface"], "edge")
        prepared["observation"]["profileDom"]["text"] = "思考强度Instant"
        self.controller.handle(prepared)
        evidence = self.evidence(prepare)
        evidence["completion"]["text"] = "回答已完成"
        self.controller.handle(self.envelope(prepare, "capture", evidence=evidence))
        identifier = sent["job"]["appDispatch"]["id"]
        row = self.row(identifier)
        self.assertEqual(row["status"], "completed")
        self.assertEqual(json.loads(row["result"])["browserEvidence"], evidence)
        self.assertEqual(json.loads(row["result"])["browserEvidence"]["completion"]["text"], "回答已完成")
        self.assertEqual(self.attempt(identifier)["preparedObservation"]["surface"], "edge")

    def test_edge_chinese_instant_label_still_requires_none_effort(self):
        self.config["domContract"]["surface"] = "edge"
        sent, prepare = self.begin()
        prepared = self.prepared(prepare)
        prepared["observation"]["profileDom"] = {"text": "思考强度Instant", "reasoningEffort": "high"}
        with self.assertRaisesRegex(ValueError, "relay_prepared_dom_invalid"):
            self.controller.handle(prepared)
        self.assertEqual(self.row(sent["job"]["appDispatch"]["id"])["status"], "needs_review")
        self.assertFalse(any(message["type"] == "commitSend" for message in self.messages))

    def test_edge_contract_cannot_accept_chrome_prepare_observation(self):
        self.config["domContract"]["surface"] = "edge"
        sent, prepare = self.begin()
        prepared = self.prepared(prepare)
        prepared["observation"]["surface"] = "chrome"
        with self.assertRaisesRegex(ValueError, "relay_prepared_dom_invalid"):
            self.controller.handle(prepared)
        self.assertEqual(self.row(sent["job"]["appDispatch"]["id"])["status"], "needs_review")
        self.assertFalse(any(message["type"] == "commitSend" for message in self.messages))

    def test_chrome_contract_cannot_accept_edge_prepare_observation(self):
        sent, prepare = self.begin()
        prepared = self.prepared(prepare)
        prepared["observation"]["surface"] = "edge"
        with self.assertRaisesRegex(ValueError, "relay_prepared_dom_invalid"):
            self.controller.handle(prepared)
        self.assertEqual(self.row(sent["job"]["appDispatch"]["id"])["status"], "needs_review")
        self.assertFalse(any(message["type"] == "commitSend" for message in self.messages))

    def test_edge_contract_does_not_widen_source_or_extension_allowlist(self):
        self.config["domContract"]["surface"] = "edge"
        self.assertEqual(approval(self.config, self.service.data_dir), self.config)
        for kind in ("source", "extensionId"):
            other = copy.deepcopy(self.config)
            if kind == "source":
                other["domContract"]["source"] = "chrome_extension_dom"
            else:
                other["extensionId"] = "a" * 32
            with self.assertRaises(ValueError):
                approval(other, self.service.data_dir)

    def test_unsupported_profile_fails_without_downgrade_and_new_confirmation_can_use_fast(self):
        self.approve()
        sent, _ = self.send("high")
        identifier = sent["job"]["appDispatch"]["id"]
        self.controller.committed([identifier])
        self.assertEqual(self.row(identifier)["status"], "failed")
        self.assertIn("unsupported_profile", self.row(identifier)["error"])
        self.assertIsNone(self.attempt(identifier))
        self.assertFalse(any(message["type"] == "prepare" for message in self.messages))
        sent, _ = self.send("fast")
        self.controller.committed([sent["job"]["appDispatch"]["id"]])
        self.assertEqual(sum(message["type"] == "prepare" for message in self.messages), 1)

    def test_queued_independent_high_and_fast_events_before_ready_do_not_strand_fast(self):
        self.approve()
        self.controller.client_ready = False
        first, _ = self.send("high")
        self.new_session()
        second, _ = self.send("fast")
        identifiers = [item["job"]["appDispatch"]["id"] for item in (first, second)]
        self.controller.committed(identifiers)
        self.assertFalse(any(message["type"] == "prepare" for message in self.messages))
        self.controller.handle({"protocol": PROTOCOL, "type": "ready", "hostName": HOST_NAME, "clientReady": True})
        self.assertEqual(self.row(identifiers[0])["status"], "failed")
        self.assertEqual(self.row(identifiers[1])["status"], "claimed")
        self.assertEqual(sum(message["type"] == "prepare" for message in self.messages), 1)

    def test_known_unsent_blocked_fails_preserves_tombstone_and_releases_independent_event(self):
        first, prepare = self.begin()
        first_id = first["job"]["appDispatch"]["id"]
        before = self.row(first_id)
        self.new_session()
        second, _ = self.send()
        second_id = second["job"]["appDispatch"]["id"]
        self.controller.committed([second_id])
        self.assertEqual(self.row(second_id)["status"], "pending")
        releases = []
        test = self
        class Notify:
            def notify_released(self, identifiers):
                with closing(sqlite3.connect(test.service.data_dir / "workflow.sqlite3")) as db:
                    for identifier in identifiers:
                        test.assertEqual(db.execute("SELECT status FROM idea_dispatches WHERE id=?", (identifier,)).fetchone()[0], "failed")
                releases.extend(identifiers)
        self.service._dispatch_commit_notifier = Notify()
        blocked = self.envelope(prepare, "blocked", code="login_required", message="登录状态未确认，本次未发送。")
        self.controller.handle(blocked)
        self.assertEqual(releases, [first_id])
        first_attempt = self.attempt(first_id)
        self.assertEqual(first_attempt["phase"], "failed")
        self.assertIsNone(first_attempt["sendIntentAt"])
        self.assertEqual(first_attempt["attemptId"], prepare["attemptId"])
        self.assertEqual(first_attempt["blockedReport"], {"code": blocked["code"], "message": blocked["message"]})
        self.assertEqual(self.row(first_id)["status"], "failed")
        for field in ("prompt", "snapshot", "claim_token"):
            self.assertEqual(self.row(first_id)[field], before[field])
        with self.service._db() as db:
            job = db.execute("SELECT status,error FROM jobs WHERE id=?", (first["job"]["id"],)).fetchone()
            self.assertEqual(job["status"], "failed")
            self.assertIn("login_required", job["error"])
        self.assertEqual(self.row(second_id)["status"], "claimed")
        self.assertEqual(self.controller.active, second_id)
        self.assertEqual([message["dispatchId"] for message in self.messages if message["type"] == "prepare"], [first_id, second_id])
        self.assertFalse(any(message["type"] == "commitSend" for message in self.messages))
        # Exact late failure replay is inert, including while a later request prepares.
        self.controller.handle(blocked)
        self.assertEqual(self.controller.active, second_id)
        self.assertEqual(self.attempt(first_id), first_attempt)
        self.controller.disconnect()
        self.assertEqual(self.attempt(first_id), first_attempt)
        restarted = ChatRelayController(self.service, self.messages.append)
        restarted.committed([first_id])
        self.assertEqual(self.row(first_id)["status"], "failed")
        self.assertEqual(sum(message["type"] == "prepare" and message["dispatchId"] == first_id for message in self.messages), 1)

    def test_uncertain_preparation_does_not_become_known_unsent(self):
        sent, prepare = self.begin()
        self.controller.handle(self.envelope(prepare, "uncertain", code="prepare_unknown", message="准备结果不明。"))
        identifier = sent["job"]["appDispatch"]["id"]
        self.assertEqual(self.row(identifier)["status"], "needs_review")
        self.assertEqual(self.attempt(identifier)["phase"], "needs_review")
        self.assertIsNone(self.attempt(identifier)["sendIntentAt"])
        self.assertEqual(self.controller.active, identifier)

    def test_blocked_after_persisted_send_intent_keeps_review_and_blocks_next_event(self):
        first, prepare = self.begin()
        self.controller.handle(self.prepared(prepare))
        first_id = first["job"]["appDispatch"]["id"]
        intent = self.attempt(first_id)["sendIntentAt"]
        self.new_session()
        second, _ = self.send()
        second_id = second["job"]["appDispatch"]["id"]
        self.controller.committed([second_id])
        self.controller.handle(self.envelope(prepare, "blocked", code="composer_changed", message="Send 前后状态不能确定。"))
        self.assertEqual(self.row(first_id)["status"], "needs_review")
        self.assertEqual(self.attempt(first_id)["phase"], "needs_review")
        self.assertEqual(self.attempt(first_id)["sendIntentAt"], intent)
        self.assertEqual(self.row(second_id)["status"], "pending")
        self.assertEqual(sum(message["type"] == "commitSend" for message in self.messages), 1)
        self.controller.released()
        self.assertEqual(sum(message["type"] == "prepare" for message in self.messages), 1)

    def test_blocked_without_intent_but_not_exact_preparation_phase_keeps_review(self):
        sent, prepare = self.begin()
        identifier = sent["job"]["appDispatch"]["id"]
        with self.service._db() as db:
            attempt = self.service._setting(db, ATTEMPT_PREFIX + identifier)
            attempt["phase"] = "waiting"
            self.service._set_setting(db, ATTEMPT_PREFIX + identifier, attempt)
        self.controller.handle(self.envelope(prepare, "blocked", code="unexpected_phase", message="阶段不明。"))
        self.assertEqual(self.row(identifier)["status"], "needs_review")
        self.assertEqual(self.attempt(identifier)["phase"], "needs_review")

    def test_startup_adopts_only_post_approval_production_pending_and_never_old_head(self):
        first, _ = self.send()
        old_id = first["job"]["appDispatch"]["id"]
        self.config["approvalConfirmedAt"] = now()
        self.approve()
        self.new_session()
        second, _ = self.send()
        new_id = second["job"]["appDispatch"]["id"]
        broker = ChatRelayBroker(self.service)
        self.assertEqual(broker._startup_pending(self.config), [new_id])
        restarted = ChatRelayController(self.service, self.messages.append)
        restarted.handle({"protocol": PROTOCOL, "type": "ready", "hostName": HOST_NAME, "clientReady": True})
        restarted.committed(broker._startup_pending(self.config))
        self.assertEqual(self.row(old_id)["status"], "pending")
        self.assertEqual(self.row(new_id)["status"], "pending")
        self.assertEqual(restarted.status()["message"], "older_queue_head_requires_user_review")

    def test_startup_recovers_post_approval_pending_without_any_send_or_claim_evidence(self):
        self.approve()
        sent, _ = self.send()
        identifier = sent["job"]["appDispatch"]["id"]
        broker = ChatRelayBroker(self.service)
        self.assertEqual(broker._startup_pending(self.config), [identifier])
        restarted = ChatRelayController(self.service, self.messages.append)
        restarted.committed(broker._startup_pending(self.config))
        restarted.handle({"protocol": PROTOCOL, "type": "ready", "hostName": HOST_NAME, "clientReady": True})
        self.assertEqual(self.row(identifier)["status"], "claimed")
        self.assertEqual(broker._startup_pending(self.config), [])

    def test_external_completed_release_commit_wakes_only_retained_submission(self):
        self.approve()
        record = self.service.create(request(projectId="isolated", text="other"))["record"]["id"]
        original = self.service.discuss(request(recordId=record, text="Codex only", appTarget={"kind": "codex", "mode": "new", "name": "fixture"}))
        claimed = self.service.incubator_claim(request(id=original["job"]["appDispatch"]["id"]))["dispatch"]
        sent, _ = self.send()
        identifier = sent["job"]["appDispatch"]["id"]
        self.controller.committed([identifier])
        self.assertEqual(self.row(identifier)["status"], "pending")
        released = []
        test = self
        class Notify:
            def notify_committed(self, identifiers):
                raise AssertionError("completion must not fabricate a submission")
            def notify_released(self, identifiers):
                with closing(sqlite3.connect(test.service.data_dir / "workflow.sqlite3")) as db:
                    test.assertEqual(db.execute("SELECT status FROM idea_dispatches WHERE id=?", (claimed["id"],)).fetchone()[0], "completed")
                released.extend(identifiers)
        self.service._dispatch_commit_notifier = Notify()
        self.service.incubator_attach_result(request(id=claimed["id"], claimToken=claimed["claimToken"], status="completed",
                                                     targetThreadId=str(uuid.uuid4()), result={"text": "isolated external result", "sourceMessageId": "actual-fixture-source", "turnId": "actual-fixture-turn"}))
        self.assertEqual(released, [claimed["id"]])
        self.controller.released()
        self.assertEqual(self.row(identifier)["status"], "claimed")

    def test_send_intent_is_durable_before_commit_send_and_duplicate_is_never_sent(self):
        _, prepare = self.begin()
        test = self
        def emit(message):
            if message["type"] == "commitSend":
                with closing(sqlite3.connect(test.service.data_dir / "workflow.sqlite3")) as db:
                    attempt = json.loads(db.execute("SELECT value FROM settings WHERE key=?", (ATTEMPT_PREFIX + prepare["dispatchId"],)).fetchone()[0])
                    test.assertTrue(attempt["sendIntentAt"])
                    test.assertEqual(attempt["phase"], "send_intent")
            test.messages.append(message)
        self.controller.emit = emit
        self.controller.handle(self.prepared(prepare))
        with self.assertRaises(ValueError):
            self.controller.handle(self.prepared(prepare))
        self.assertEqual(sum(message["type"] == "commitSend" for message in self.messages), 1)
        self.assertEqual(self.row(prepare["dispatchId"])["status"], "needs_review")

    def test_disconnect_restart_never_reclaims_or_resends(self):
        _, prepare = self.begin()
        self.controller.handle(self.prepared(prepare))
        self.controller.disconnect()
        restarted = ChatRelayController(self.service, self.messages.append)
        restarted.disconnect("fixture_restart")
        restarted.handle({"protocol": PROTOCOL, "type": "ready", "hostName": HOST_NAME, "clientReady": True})
        restarted.committed([prepare["dispatchId"]])
        self.assertEqual(sum(message["type"] == "prepare" for message in self.messages), 1)
        self.assertEqual(sum(message["type"] == "commitSend" for message in self.messages), 1)
        self.assertEqual(self.row(prepare["dispatchId"])["status"], "needs_review")

    def test_accepted_real_conversation_and_capture_uuid_unit_bind_without_server_turn(self):
        _, prepare = self.begin()
        self.controller.handle(self.prepared(prepare))
        evidence = self.evidence(prepare)
        source = {key: evidence[key] for key in ("source", "conversationUrl", "sourceUserMessageId", "sourceUnitKey", "promptText", "observedAt", "profile")}
        self.controller.handle(self.envelope(prepare, "accepted", evidence=source))
        self.assertEqual(self.row(prepare["dispatchId"])["status"], "waiting")
        self.controller.handle(self.envelope(prepare, "capture", evidence=evidence))
        result = json.loads(self.row(prepare["dispatchId"])["result"])
        self.assertEqual(result["sourceKind"], "browser_dom")
        self.assertNotIn("turnId", result)
        self.assertNotIn("sourceMessageId", result)
        self.assertFalse(result["executionCapabilities"]["verified"])
        mobile = self.service.mobile_dialogue_get("clientId=" + self.client)
        self.assertEqual(mobile["execution"]["profileObservation"], result["profileObservation"])
        self.assertEqual(result["profileObservation"]["source"], "browser_dom_ui_label")
        self.assertFalse(result["profileObservation"]["capabilitiesVerified"])
        self.assertEqual(result["profileObservation"]["messageId"], result["messageId"])
        self.assertFalse(mobile["execution"]["actualReceipt"]["verified"])
        self.assertIsNone(mobile["execution"]["actualReceipt"]["actualProfile"])
        self.assertEqual(self.messages[-1]["type"], "stored")
        before = self.service.detail(self.state["session"]["recordId"])
        self.controller.handle(self.envelope(prepare, "capture", evidence=evidence))
        self.assertEqual(before, self.service.detail(self.state["session"]["recordId"]))

    def test_late_a_answer_stays_on_a_after_clear_to_b(self):
        sent, prepare = self.begin()
        self.controller.handle(self.prepared(prepare))
        source_record = sent["session"]["recordId"]
        session = self.state["session"]
        self.state = self.service.mobile_dialogue_clear(request(clientId=self.client, sessionId=session["id"], expectedRevision=session["revision"]))
        new_record = self.state["session"]["recordId"]
        self.assertNotEqual(source_record, new_record)
        self.controller.handle(self.envelope(prepare, "capture", evidence=self.evidence(prepare)))
        self.assertTrue(any(item["role"] == "assistant" for item in self.service.detail(source_record)["messages"]))
        self.assertFalse(any(item["role"] == "assistant" for item in self.service.detail(new_record)["messages"]))

    def rejected_capture(self, mutate):
        sent, prepare = self.begin()
        self.controller.handle(self.prepared(prepare))
        evidence = self.evidence(prepare)
        mutate(evidence)
        with self.assertRaises(ValueError):
            self.controller.handle(self.envelope(prepare, "capture", evidence=evidence))
        self.assertEqual(self.row(prepare["dispatchId"])["status"], "needs_review")
        self.assertFalse(any(item["role"] == "assistant" for item in self.service.detail(sent["session"]["recordId"])["messages"]))

    def test_wrong_prompt_not_saved(self):
        self.rejected_capture(lambda item: item.update(promptText="unknown source"))

    def test_wrong_profile_not_saved(self):
        self.rejected_capture(lambda item: item["profile"].update(observedAfter="Pro"))

    def test_cross_dom_unit_not_saved(self):
        self.rejected_capture(lambda item: item.update(assistantUnitKey="fallback-turn-1:1:assistant"))

    def test_incomplete_dom_not_saved(self):
        self.rejected_capture(lambda item: item["completion"].update(stopPresent=True))

    def test_edge_chinese_completion_typo_not_saved(self):
        self.config["domContract"]["surface"] = "edge"
        self.rejected_capture(lambda item: item["completion"].update(text="回答已完城"))

    def test_edge_chinese_completion_before_commit_not_saved(self):
        self.config["domContract"]["surface"] = "edge"
        self.rejected_capture(lambda item: item["completion"].update(text="回答已完成", observedAfterCommit=False))

    def test_edge_chinese_completion_with_stop_present_not_saved(self):
        self.config["domContract"]["surface"] = "edge"
        self.rejected_capture(lambda item: item["completion"].update(text="回答已完成", stopPresent=True))

    def test_precommit_dom_not_saved(self):
        self.rejected_capture(lambda item: item.update(observedAt="2000-01-01T00:00:00Z"))

    def test_oversized_dom_answer_not_saved_or_previewed(self):
        self.rejected_capture(lambda item: item.update(answerText="x" * 20001))

    def test_accepted_source_cannot_change_in_final_capture(self):
        _, prepare = self.begin()
        self.controller.handle(self.prepared(prepare))
        evidence = self.evidence(prepare)
        source = {key: evidence[key] for key in ("source", "conversationUrl", "sourceUserMessageId", "sourceUnitKey", "promptText", "observedAt", "profile")}
        self.controller.handle(self.envelope(prepare, "accepted", evidence=source))
        evidence["sourceUserMessageId"] = str(uuid.uuid4())
        with self.assertRaises(ValueError):
            self.controller.handle(self.envelope(prepare, "capture", evidence=evidence))
        self.assertEqual(self.row(prepare["dispatchId"])["status"], "needs_review")

    def test_other_head_or_global_inflight_cannot_be_skipped(self):
        self.approve()
        record = self.service.create(request(projectId="isolated", text="other"))["record"]["id"]
        original = self.service.discuss(request(recordId=record, text="Codex only", appTarget={"kind": "codex", "mode": "new", "name": "fixture"}))
        sent, _ = self.send()
        identifier = sent["job"]["appDispatch"]["id"]
        self.controller.committed([identifier])
        self.assertEqual(self.row(identifier)["status"], "pending")
        self.service.incubator_claim(request(id=original["job"]["appDispatch"]["id"]))
        self.controller.committed([identifier])
        self.assertEqual(self.row(identifier)["status"], "pending")

    def test_revoked_approval_after_prepare_never_commits_send(self):
        _, prepare = self.begin()
        with self.service._db() as db:
            self.service._set_setting(db, APPROVAL_KEY, {"version": 1, "enabled": False})
        with self.assertRaises(ValueError):
            self.controller.handle(self.prepared(prepare))
        self.assertFalse(any(item["type"] == "commitSend" for item in self.messages))
        self.assertEqual(self.row(prepare["dispatchId"])["status"], "needs_review")

    def test_native_frame_and_origin_limits_and_no_config_no_database_creation(self):
        message = {"protocol": PROTOCOL, "type": "hello", "hostName": HOST_NAME}
        output = io.BytesIO()
        host.write_frame(output, message)
        self.assertEqual(host.read_frame(io.BytesIO(output.getvalue())), message)
        for raw in (b"x", struct.pack("<I", MAX_FRAME + 1), struct.pack("<I", 5) + b"x"):
            with self.assertRaises(ValueError):
                host.read_frame(io.BytesIO(raw))
        output = io.BytesIO()
        self.assertEqual(host.main(["chrome-extension://wrong/"], io.BytesIO(), output), 2)
        with patch.dict(host.os.environ, {"LOCALAPPDATA": str(self.root / "no-config")}, clear=True):
            output = io.BytesIO()
            self.assertEqual(host.main(["chrome-extension://" + EXTENSION_ID + "/"], io.BytesIO(), output), 3)
        self.assertFalse(self.root.joinpath("no-config").exists())

    def test_native_partial_reads_and_product_eof_exits_only_own_host(self):
        class SplitStream(io.BytesIO):
            def read(self, size=-1):
                return super().read(min(size, 2))
        output = io.BytesIO()
        expected = {"protocol": PROTOCOL, "type": "status", "hostName": HOST_NAME}
        host.write_frame(output, expected)
        self.assertEqual(host.read_frame(SplitStream(output.getvalue())), expected)
        class DroppedProduct:
            closed = False
            def recv_bytes(self, limit):
                raise EOFError("fixture product disconnected")
            def close(self):
                self.closed = True
        product, exited, stopped = DroppedProduct(), [], threading.Event()
        host.forward_product(product, io.BytesIO(), threading.Lock(), stopped, exited.append)
        self.assertEqual(exited, [0])
        self.assertTrue(stopped.is_set())
        self.assertTrue(product.closed)

    def test_fixed_approval_file_and_existing_store_must_match(self):
        self.approve()
        environment = {"LOCALAPPDATA": str(self.root)}
        path = self.service.data_dir / "console-chat-relay-approved.json"
        path.unlink()
        self.assertIsNone(fixed_approval(environment))
        path.write_text(json.dumps(self.config), encoding="utf-8")
        self.assertEqual(fixed_approval(environment), self.config)
        self.assertEqual(host.approved_config(environment), self.config)
        modified = copy.deepcopy(self.config)
        modified["authKeyHex"] = "b" * 64
        path.write_text(json.dumps(modified), encoding="utf-8")
        with self.assertRaises(ValueError):
            fixed_approval(environment)

    @unittest.skipUnless(os.name == "nt", "Windows authenticated pipe contract")
    def test_isolated_pipe_start_close_restart_is_bounded_and_idle_has_no_claim(self):
        self.approve()
        path = self.service.data_dir / "console-chat-relay-approved.json"
        path.write_text(json.dumps(self.config), encoding="utf-8")
        broker = ChatRelayBroker(self.service)
        with patch.dict("os.environ", {"LOCALAPPDATA": str(self.root)}):
            try:
                self.assertTrue(broker.start())
                self.assertTrue(broker.start())
                self.assertFalse(broker.public_status()["clientReady"])
                broker.close()
                self.assertFalse(broker.thread.is_alive())
                self.assertFalse(broker.event_thread.is_alive())
                self.assertTrue(broker.start())
                self.assertFalse(broker.public_status()["clientReady"])
            finally:
                broker.close()
        self.assertIsNone(self.service._dispatch_commit_notifier)

    @unittest.skipUnless(os.name == "nt", "Windows authenticated Edge pipe contract")
    def test_edge_pipe_start_close_restart_is_bounded_and_idle_has_no_claim(self):
        self.config["domContract"]["surface"] = "edge"
        self.test_isolated_pipe_start_close_restart_is_bounded_and_idle_has_no_claim()

    def test_approval_identity_exact_and_close_only_owns_notifier(self):
        self.assertEqual(approval(self.config, self.service.data_dir), self.config)
        other = copy.deepcopy(self.config)
        other["extensionId"] = "a" * 32
        with self.assertRaises(ValueError):
            approval(other, self.service.data_dir)
        other = copy.deepcopy(self.config)
        other["dataDir"] = str(self.root / "unrelated")
        with self.assertRaises(ValueError):
            approval(other, self.service.data_dir)
        broker = ChatRelayBroker(self.service)
        sentinel = object()
        self.service._dispatch_commit_notifier = sentinel
        broker.close()
        self.assertIs(self.service._dispatch_commit_notifier, sentinel)
        self.assertFalse(broker.public_status()["clientReady"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
