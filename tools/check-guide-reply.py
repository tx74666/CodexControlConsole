#!/usr/bin/env python3
"""Disposable desktop Guide provenance and scoped commit tests; no real App/model."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow_http import workflow_get, workflow_post
from workflow_service import WorkflowError, WorkflowService, _json


def fixture(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), Path(__file__).with_name(name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


mobile = fixture("check-mobile-dialogue")


class GuideReplyChecks(unittest.TestCase):
    def setUp(self):
        self.fixture = mobile.MobileDialogueChecks(methodName="runTest")
        self.fixture.setUp()
        self.service = self.fixture.service
        self.client = self.fixture.client
        self.chat_id = str(uuid.uuid4())
        self.streams = []
        self.other_services = []
        self.bind_body = mobile.request(sourceGuideChatId=self.chat_id)
        self.post("guide-source", self.bind_body)

    def tearDown(self):
        for stream in self.streams:
            stream.close()
        for service in self.other_services:
            service.shutdown()
        self.fixture.tearDown()

    def post(self, action, body, **options):
        return workflow_post(self.service, "mobile/dialogue/" + action, body, desktop=True, **options)

    def get(self, action, query="", **options):
        return workflow_get(self.service, "mobile/dialogue/" + action, query, desktop=True, **options)

    def send(self, state=None, **options):
        return self.fixture.mutate("send", state or self.fixture.open(), **options)

    def reply_body(self, sent, text=" Guide 第一行\r\n第二行\n  "):
        user = next(message for message in reversed(sent["detail"]["messages"]) if message["role"] == "user")
        return mobile.request(clientId=self.client, sessionId=sent["session"]["id"], recordId=sent["session"]["recordId"],
            sourceUserMessageId=user["id"], sourceGuideChatId=self.chat_id, text=text)

    def snapshot(self):
        with self.service._db() as db:
            return {table: [tuple(row) for row in db.execute("SELECT * FROM " + table + " ORDER BY rowid")]
                for table in ("settings", "messages", "jobs", "idea_dispatches", "requests", "mobile_message_sources", "guide_sources", "guide_replies", "records", "ideas")}

    def error(self, operation, status=None, code=None):
        with self.assertRaises(WorkflowError) as caught:
            operation()
        if status:
            self.assertEqual(caught.exception.status, status)
        if code:
            self.assertEqual(caught.exception.code, code)
        return caught.exception

    def subscribe(self, state):
        stream = self.service.mobile_dialogue_subscribe(urlencode({"clientId": self.client,
            "sessionId": state["session"]["id"], "cursor": state["resultCursor"]}))
        self.streams.append(stream)
        self.assertEqual(stream.next_event(0)["event"], "dialogue.ready")
        return stream

    def make_historical(self, sent):
        """Simulate pre-82 rows only inside this disposable database."""
        with self.service._db() as db:
            db.execute("DELETE FROM mobile_message_sources")
            receipt = db.execute("SELECT id,response FROM requests WHERE kind='mobile_dialogue_send'").fetchone()
            saved = json.loads(receipt["response"])
            saved.pop("sourceMessageId")
            db.execute("UPDATE requests SET response=? WHERE id=?", (_json(saved), receipt["id"]))
        return self.reply_body(sent)

    def test_binding_same_chat_is_idempotent_and_different_chat_conflicts(self):
        first = self.get("guide-source")
        self.assertEqual(first, {"bound": True, "kind": "codex_guide", "author": "Codex Guide", "sourceGuideChatId": self.chat_id})
        before = self.snapshot()
        self.assertEqual(self.post("guide-source", self.bind_body), first)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.post("guide-source", mobile.request(sourceGuideChatId=self.chat_id)), first)
        self.error(lambda: self.post("guide-source", mobile.request(sourceGuideChatId=str(uuid.uuid4()))), 409, "guide_source_conflict")
        self.error(lambda: self.post("guide-source", {**self.bind_body, "sourceGuideChatId": str(uuid.uuid4())}), 409)

    def test_only_exact_desktop_prefix_can_read_or_write(self):
        sent = self.send()
        reply = self.reply_body(sent)
        before = self.snapshot()
        for action, body in (("guide-source", self.bind_body), ("guide-reply", reply)):
            for desktop, prefix in ((False, "/api/workflow"), (True, "/api/phone/workflow"), (True, "/api/workflow/")):
                self.error(lambda: workflow_post(self.service, "mobile/dialogue/" + action, body,
                    desktop=desktop, prefix=prefix), 403, "guide_desktop_required")
                self.error(lambda: workflow_get(self.service, "mobile/dialogue/" + action,
                    "requestId=" + reply["requestId"] if action == "guide-reply" else "", desktop=desktop, prefix=prefix), 403)
        self.assertEqual(self.snapshot(), before)

    def test_exact_body_and_raw_text_preserved_without_job_draft_profile_change(self):
        sent = self.send(text=" 原问题\n不裁切 ")
        draft = self.fixture.mutate("draft", sent, text="未发新草稿\n第二行", requestedProfile="pro")
        body = self.reply_body(sent)
        before = self.snapshot()
        for changed in ({**body, "role": "assistant"}, {**body, "author": "Codex Guide"}, {**body, "expectedRevision": 2},
                {key: value for key, value in body.items() if key != "sourceUserMessageId"}):
            self.error(lambda: self.post("guide-reply", changed), 400)
        for text in (" \r\n\t", "a\0b", "x" * 20001, 123, "bad\ud800"):
            self.error(lambda: self.post("guide-reply", {**body, "text": text}), 400)
        receipt = self.post("guide-reply", body)
        self.assertEqual(set(receipt), {"guideSource", "isCurrent"})
        source = receipt["guideSource"]
        self.assertEqual(set(source), {"kind", "author", "messageId", "clientId", "sessionId", "recordId",
            "sourceUserMessageId", "sourceGuideChatId", "requestId", "textSha256"})
        self.assertEqual(source["kind"], "codex_guide")
        self.assertEqual(source["author"], "Codex Guide")
        self.assertEqual(source["textSha256"], hashlib.sha256(body["text"].encode("utf-8")).hexdigest())
        detail = self.service.detail(body["recordId"])
        message = detail["messages"][-1]
        self.assertEqual(message["role"], "assistant")
        self.assertEqual(message["text"], body["text"])
        self.assertEqual(message["guideSource"], source)
        after = self.snapshot()
        for table in ("jobs", "idea_dispatches", "mobile_message_sources", "ideas"):
            self.assertEqual(after[table], before[table])
        old_settings = {key: value for key, value in before["settings"] if key != "revision"}
        new_settings = {key: value for key, value in after["settings"] if key != "revision"}
        self.assertEqual(new_settings, old_settings)
        refreshed = self.fixture.current()
        self.assertEqual(refreshed["session"], draft["session"])
        self.assertEqual(refreshed["execution"], draft["execution"])

    def test_future_send_receipt_captures_source_message(self):
        sent = self.send()
        body = self.reply_body(sent)
        with self.service._db() as db:
            source = db.execute("SELECT * FROM mobile_message_sources WHERE message_id=?", (body["sourceUserMessageId"],)).fetchone()
            saved = json.loads(db.execute("SELECT response FROM requests WHERE id=?", (source["request_id"],)).fetchone()[0])
            self.assertEqual(saved["sourceMessageId"], body["sourceUserMessageId"])
            self.assertEqual(saved["jobId"], source["job_id"])
            self.assertEqual(source["session_id"], body["sessionId"])

    def test_replay_get_and_full_body_conflict_do_not_append(self):
        body = self.reply_body(self.send())
        first = self.post("guide-reply", body)
        before = self.snapshot()
        self.assertEqual(self.post("guide-reply", dict(body)), first)
        self.assertEqual(self.get("guide-reply", "requestId=" + body["requestId"]), first)
        self.assertEqual(self.snapshot(), before)
        for key, value in (("text", body["text"] + "\n"), ("recordId", uuid.uuid4().hex),
                           ("sourceUserMessageId", uuid.uuid4().hex), ("sourceGuideChatId", str(uuid.uuid4()))):
            self.error(lambda: self.post("guide-reply", {**body, key: value}), 409)
        self.error(lambda: self.post("guide-source", {"requestId": body["requestId"], "sourceGuideChatId": self.chat_id}), 409)
        self.assertEqual(self.snapshot(), before)

    def test_gets_are_readonly_and_unknown_receipt_is_404(self):
        body = self.reply_body(self.send())
        result = self.post("guide-reply", body)
        before = self.service.data_dir.joinpath("workflow.sqlite3").read_bytes()
        with patch.object(self.service, "_db", side_effect=AssertionError("GET must be read-only")):
            self.assertTrue(self.get("guide-source")["bound"])
            self.assertEqual(self.get("guide-reply", "requestId=" + body["requestId"]), result)
            self.error(lambda: self.get("guide-reply", "requestId=" + str(uuid.uuid4())), 404, "guide_receipt_not_found")
        self.assertEqual(self.service.data_dir.joinpath("workflow.sqlite3").read_bytes(), before)

    def test_wrong_client_record_user_or_chat_fails_without_mutation(self):
        sent = self.send()
        body = self.reply_body(sent)
        other = self.service.mobile_dialogue_open(mobile.request(clientId=str(uuid.uuid4())))
        before = self.snapshot()
        for changed in ({**body, "clientId": str(uuid.uuid4())}, {**body, "recordId": other["session"]["recordId"]},
                {**body, "sourceUserMessageId": uuid.uuid4().hex}, {**body, "sourceGuideChatId": str(uuid.uuid4())}):
            self.error(lambda: self.post("guide-reply", changed))
        self.assertEqual(self.snapshot(), before)

    def test_authorization_revocation_rolls_back_append_receipt_and_recovery(self):
        body = self.make_historical(self.send())
        before = self.snapshot()
        calls = []
        def authorize():
            calls.append(True)
            if len(calls) == 2:
                raise WorkflowError("revoked", 403)
        self.error(lambda: self.post("guide-reply", body, authorize=authorize), 403)
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.snapshot(), before)
        self.error(lambda: self.get("guide-reply", "requestId=" + body["requestId"]), 404)

    def test_concurrent_same_request_commits_once(self):
        body = self.reply_body(self.send())
        other_service = WorkflowService(self.service.data_dir, models=mobile.ForbiddenModels(), projects=self.fixture.projects, recover_jobs=False)
        self.other_services.append(other_service)
        barrier = threading.Barrier(2)
        results, failures = [], []
        def append(service):
            try:
                barrier.wait(3)
                results.append(workflow_post(service, "mobile/dialogue/guide-reply", body, desktop=True))
            except Exception as error:
                failures.append(error)
        threads = [threading.Thread(target=append, args=(service,)) for service in (self.service, other_service)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(5)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1])
        with self.service._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM guide_replies").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM messages WHERE role='assistant'").fetchone()[0], 1)

    def test_committed_guide_wakes_scope_with_six_fields_replay_and_rollback_quiet(self):
        sent = self.send()
        stream = self.subscribe(sent)
        body = self.reply_body(sent)
        before = self.snapshot()
        calls = []
        def revoked():
            calls.append(True)
            if len(calls) == 2: raise WorkflowError("revoked", 403)
        self.error(lambda: self.post("guide-reply", body, authorize=revoked), 403)
        self.assertEqual(self.snapshot(), before)
        self.assertIsNone(stream.next_event(0))
        self.post("guide-reply", body)
        frame = stream.next_event(0)
        self.assertEqual(frame["event"], "dialogue.result")
        self.assertEqual(set(frame["data"]), {"clientId", "sessionId", "recordId", "cursor", "jobId", "status"})
        self.assertEqual(frame["data"]["jobId"], sent["job"]["id"])
        self.assertEqual(frame["data"]["status"], "waiting")
        self.assertNotEqual(frame["data"]["cursor"], sent["resultCursor"])
        self.post("guide-reply", body)
        self.assertIsNone(stream.next_event(0))

    def test_late_clear_reply_stays_original_and_does_not_wake_new_session(self):
        sent = self.send()
        body = self.reply_body(sent)
        current = self.fixture.mutate("clear", sent)
        stream = self.subscribe(current)
        receipt = self.post("guide-reply", body)
        self.assertIs(receipt["isCurrent"], False)
        self.assertIsNone(stream.next_event(0))
        self.assertEqual(self.fixture.current()["resultCursor"], current["resultCursor"])
        self.assertFalse(any(message.get("guideSource") for message in self.fixture.current()["detail"]["messages"]))
        old = self.service._mobile_state(self.client, "/api/workflow", body["sessionId"])
        self.assertEqual(old["detail"]["messages"][-1]["guideSource"], receipt["guideSource"])

    def test_same_record_new_session_filters_old_guide_and_rejects_old_user_binding(self):
        idea_state = self.fixture.mutate("save", self.fixture.open(), text="同 record 想法")
        sent = self.send(idea_state)
        body = self.reply_body(sent)
        current = self.fixture.open(ideaId=idea_state["idea"]["id"], expectedIdeaRevision=idea_state["idea"]["revision"])
        self.assertEqual(current["session"]["recordId"], sent["session"]["recordId"])
        stream = self.subscribe(current)
        receipt = self.post("guide-reply", body)
        self.assertIs(receipt["isCurrent"], False)
        self.assertIsNone(stream.next_event(0))
        refreshed = self.fixture.current()
        self.assertEqual(refreshed["resultCursor"], current["resultCursor"])
        self.assertTrue(any(message["id"] == body["sourceUserMessageId"] for message in refreshed["detail"]["messages"]))
        self.assertFalse(any(message.get("guideSource") for message in refreshed["detail"]["messages"]))
        before = self.snapshot()
        self.error(lambda: self.post("guide-reply", {**body, "requestId": str(uuid.uuid4()), "sessionId": current["session"]["id"]}), 409)
        self.assertEqual(self.snapshot(), before)

    def test_receipt_projection_and_cursor_survive_restart(self):
        body = self.reply_body(self.send())
        first = self.post("guide-reply", body)
        cursor = self.fixture.current()["resultCursor"]
        before = self.snapshot()
        self.service.shutdown()
        self.service = self.fixture.service = WorkflowService(self.service.data_dir, models=mobile.ForbiddenModels(),
            projects=self.fixture.projects, recover_jobs=False)
        self.assertEqual(self.get("guide-reply", "requestId=" + body["requestId"]), first)
        self.assertEqual(self.fixture.current()["resultCursor"], cursor)
        self.assertEqual(self.post("guide-reply", body), first)
        after = self.snapshot()
        for table in ("messages", "requests", "jobs", "idea_dispatches", "guide_replies", "mobile_message_sources"):
            self.assertEqual(after[table], before[table])

    def test_historical_browser_send_recovers_only_new_provenance(self):
        body = self.make_historical(self.send(text="81 已发送原问题\r\n 保留 "))
        before = self.snapshot()
        self.post("guide-reply", body)
        after = self.snapshot()
        self.assertEqual(len(after["mobile_message_sources"]), 1)
        self.assertEqual(after["jobs"], before["jobs"])
        self.assertEqual(after["idea_dispatches"], before["idea_dispatches"])
        self.assertEqual(after["requests"][:-1], before["requests"])

    def test_historical_subscription_source_and_loaded_image_scope_recover(self):
        self.service.subscription = mobile.CachedSubscription()
        state = self.fixture.open()
        image_id = self.fixture.image(state)
        sent = self.send(state, text="81 订阅问题与原图\r\n 不裁切 ", attachmentIds=[image_id],
            chatTransport="chatgpt_subscription", subscription=self.service.subscription.choice())
        # Match a completed original subscription send, without generating a
        # model/API job or touching a production database.
        with self.service._db() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=?", (sent["job"]["id"],)).fetchone()
            payload = json.loads(job["payload"])
            self.assertEqual(payload["appFrozen"]["text"], payload["text"])
            self.assertEqual([item["id"] for item in payload["appFrozen"]["images"]], [image_id])
            db.execute("UPDATE jobs SET status='succeeded' WHERE id=?", (job["id"],))
            db.execute("UPDATE idea_dispatches SET status='completed' WHERE id=?", (payload["appDispatchId"],))
        body = self.make_historical(sent)
        before = self.snapshot()
        receipt = self.post("guide-reply", body)
        self.assertEqual(receipt["guideSource"]["sourceUserMessageId"], body["sourceUserMessageId"])
        after = self.snapshot()
        self.assertEqual(after["jobs"], before["jobs"])
        self.assertEqual(after["idea_dispatches"], before["idea_dispatches"])
        self.assertEqual(after["requests"][:-1], before["requests"])
        # A source image/signature mismatch cannot be rebound to another session.
        with self.service._db() as db:
            db.execute("DELETE FROM mobile_message_sources")
            db.execute("UPDATE messages SET attachment_ids='[]' WHERE id=?", (body["sourceUserMessageId"],))
        invalid = {**body, "requestId": str(uuid.uuid4())}
        self.error(lambda: self.post("guide-reply", invalid), 409, "guide_source_not_matching")

    def test_foreign_guide_is_filtered_before_chat_and_work_history_limit(self):
        saved = self.fixture.mutate("save", self.fixture.open(), text="原始长期想法")
        sent = self.send(saved)
        body = self.reply_body(sent)
        current = self.fixture.open(ideaId=saved["idea"]["id"], expectedIdeaRevision=saved["idea"]["revision"])
        for index in range(13):
            self.post("guide-reply", {**body, "requestId": str(uuid.uuid4()), "text": "旧 Guide " + str(index)})
        with self.service._db() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=?", (sent["job"]["id"],)).fetchone()
            payload = json.loads(job["payload"])
            payload["mobileDialogue"] = {key: current["session"][key] for key in
                ("id", "clientId", "recordId", "ideaId", "ideaRevision", "revision")}
            record = self.service._record(db, body["recordId"])
            frozen = self.service._freeze_app_discussion(db, record, payload, None)
            work = self.service._codex_work_context(db, body["recordId"], payload["mobileDialogue"])
            self.assertTrue(any(item["content"] == payload["text"] for item in frozen["history"]))
            self.assertTrue(any(item["id"] == body["sourceUserMessageId"] for item in work["history"]))
            self.assertFalse(any(item["content"].startswith("旧 Guide") for item in frozen["history"]))
            self.assertFalse(any(item["text"].startswith("旧 Guide") for item in work["history"]))
            original_scope = {"clientId": body["clientId"], "id": body["sessionId"]}
            own = self.service._guide_history(db, body["recordId"], original_scope)
            self.assertEqual(len(own), 12)
            self.assertTrue(all(item["text"].startswith("旧 Guide") for item in own))

    def test_late_foreign_guide_does_not_invalidate_phone_work_review(self):
        work = fixture("check-workflow-codex-work-service")
        saved = self.fixture.mutate("save", self.fixture.open(), text="新讨论 Work 的底稿")
        sent = self.send(saved)
        guide_body = self.reply_body(sent)
        with self.service._db() as db:
            db.execute("UPDATE jobs SET status='succeeded' WHERE id=?", (sent["job"]["id"],))
            db.execute("UPDATE idea_dispatches SET status='completed' WHERE id=?", (sent["job"]["appDispatch"]["id"],))
        current = self.fixture.open(ideaId=saved["idea"]["id"], expectedIdeaRevision=saved["idea"]["revision"])
        workspace = (self.fixture.root / "workspace").resolve()
        allowed = workspace / "owned"
        allowed.mkdir(parents=True)
        (allowed / "fixture.txt").write_text("unchanged", encoding="utf-8")
        self.service.subscription = work.Subscription()
        controller = work.Controller(self.service)
        self.service.codex_work = controller
        config = self.service.configure_codex_work(mobile.request(workspaces=[{"id": "fixture", "name": "Fixture Work",
            "workspaceRoot": str(workspace), "allowedRoot": str(allowed)}]))
        session = current["session"]
        review = self.service.codex_work_review(mobile.request(clientId=self.client, sessionId=session["id"],
            recordId=session["recordId"], expectedRevision=session["revision"], text="实际本轮 Work 输入", attachmentIds=[],
            requestedProfile="high", workspaceId="fixture", workspaceAuthorizationSha256=config["workspaces"][0]["authorizationSha256"],
            subscription=dict(work.Subscription.binding)), prefix="/api/phone/workflow")
        submit = mobile.request(reviewId=review["reviewId"], sourceSha256=review["sourceSha256"], confirmed=True)
        original_title = current["detail"]["record"]["title"]
        with self.service._db() as db:
            db.execute("UPDATE records SET title='changed title' WHERE id=?", (session["recordId"],))
        self.error(lambda: self.service.codex_work_submit(submit, prefix="/api/phone/workflow"), 409, "codex_work_source_changed")
        with self.service._db() as db:
            db.execute("UPDATE records SET title=? WHERE id=?", (original_title, session["recordId"]))
        self.assertIs(self.post("guide-reply", guide_body)["isCurrent"], False)
        with self.service._db() as db:
            record = self.service._record(db, session["recordId"])
            self.assertNotEqual(record["updated_at"], review["source"]["context"]["record"]["updated_at"])
        accepted = self.service.codex_work_submit(submit, prefix="/api/phone/workflow")
        self.assertEqual(accepted["job"]["status"], "starting")
        self.assertEqual(accepted["job"]["codexWork"]["sourceSha256"], review["sourceSha256"])
        self.assertEqual(len(controller.calls), 1)
        self.assertNotIn(guide_body["text"], controller.calls[0][1]["text"])

    def test_historical_duplicate_user_signature_or_original_job_is_ambiguous(self):
        body = self.make_historical(self.send())
        with self.service._db() as db:
            user = list(db.execute("SELECT * FROM messages WHERE id=?", (body["sourceUserMessageId"],)).fetchone())
            user[0] = uuid.uuid4().hex
            db.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?)", user)
        before = self.snapshot()
        self.error(lambda: self.post("guide-reply", body), 409, "guide_source_not_matching")
        self.assertEqual(self.snapshot(), before)
        with self.service._db() as db:
            db.execute("DELETE FROM messages WHERE id=?", (user[0],))
            job = list(db.execute("SELECT * FROM jobs").fetchone())
            job[0], job[3] = uuid.uuid4().hex, str(uuid.uuid4())
            payload = json.loads(job[4])
            payload["mobileDialogue"]["id"] = uuid.uuid4().hex
            job[4] = _json(payload)
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", job)
        before = self.snapshot()
        self.error(lambda: self.post("guide-reply", body), 409, "guide_source_not_matching")
        self.assertEqual(self.snapshot(), before)

    def test_historical_bad_frozen_scope_prompt_receipt_time_and_attachment_fail_closed(self):
        body = self.make_historical(self.send())
        with self.service._db() as db:
            job = dict(db.execute("SELECT * FROM jobs").fetchone())
            payload = json.loads(job["payload"])
            dispatch = dict(db.execute("SELECT * FROM idea_dispatches").fetchone())
            receipt = dict(db.execute("SELECT * FROM requests WHERE kind='mobile_dialogue_send'").fetchone())
        corruptions = [
            ("jobs", "payload", _json({**payload, "appFrozen": {**payload["appFrozen"], "mobileDialogue": {**payload["mobileDialogue"], "clientId": str(uuid.uuid4())}}}), job),
            ("idea_dispatches", "prompt", dispatch["prompt"] + "changed", dispatch),
            ("idea_dispatches", "created_at", "2026-01-01T00:00:00+00:00", dispatch),
            ("idea_dispatches", "snapshot", _json({**json.loads(dispatch["snapshot"]), "attachmentIds": [uuid.uuid4().hex]}), dispatch),
            ("idea_dispatches", "user_confirmed_at", "2026-01-01T00:00:00+00:00", dispatch),
            ("idea_dispatches", "snapshot", _json({**json.loads(dispatch["snapshot"]), "sourceTask": {"body": "foreign"}}), dispatch),
            ("requests", "kind", "retry", receipt),
            ("requests", "response", _json({"sessionId": uuid.uuid4().hex, "jobId": job["id"]}), receipt)]
        for table, field, value, row in corruptions:
            with self.subTest(table=table, field=field):
                with self.service._db() as db:
                    db.execute("UPDATE " + table + " SET " + field + "=? WHERE id=?", (value, row["id"]))
                before = self.snapshot()
                self.error(lambda: self.post("guide-reply", body), 409, "guide_source_not_matching")
                self.assertEqual(self.snapshot(), before)
                with self.service._db() as db:
                    db.execute("UPDATE " + table + " SET " + field + "=? WHERE id=?", (row[field], row["id"]))

    def test_historical_missing_confirmation_and_malformed_structures_are_controlled(self):
        body = self.make_historical(self.send())
        with self.service._db() as db:
            job = dict(db.execute("SELECT * FROM jobs").fetchone())
            dispatch = dict(db.execute("SELECT * FROM idea_dispatches").fetchone())
            receipt = dict(db.execute("SELECT * FROM requests WHERE kind='mobile_dialogue_send'").fetchone())
        payload = json.loads(job["payload"])
        malformed = [
            ("jobs", "payload", "[]", job),
            ("jobs", "payload", _json({**payload, "context": None}), job),
            ("jobs", "payload", _json({**payload, "appFrozen": []}), job),
            ("jobs", "payload", _json({**payload, "appFrozen": {**payload["appFrozen"], "images": [None]}}), job),
            ("idea_dispatches", "snapshot", "null", dispatch),
            ("requests", "response", "[]", receipt)]
        for table, field, value, row in malformed:
            with self.subTest(table=table, value=value):
                with self.service._db() as db:
                    db.execute("UPDATE " + table + " SET " + field + "=? WHERE id=?", (value, row["id"]))
                before = self.snapshot()
                self.error(lambda: self.post("guide-reply", body), 409, "guide_source_not_matching")
                self.assertEqual(self.snapshot(), before)
                with self.service._db() as db:
                    db.execute("UPDATE " + table + " SET " + field + "=? WHERE id=?", (row[field], row["id"]))
        no_time = dict(payload)
        no_time.pop("submissionTime")
        no_time["appFrozen"] = dict(no_time["appFrozen"])
        no_time["appFrozen"].pop("submissionTime")
        snapshot = json.loads(dispatch["snapshot"])
        snapshot.pop("submissionTime")
        with self.service._db() as db:
            db.execute("UPDATE jobs SET payload=? WHERE id=?", (_json(no_time), job["id"]))
            db.execute("UPDATE idea_dispatches SET snapshot=? WHERE id=?", (_json(snapshot), dispatch["id"]))
        self.error(lambda: self.post("guide-reply", body), 409, "guide_source_not_matching")

    def test_guide_remember_uses_exact_scope_and_guide_provenance_without_job(self):
        sent = self.send()
        body = self.reply_body(sent)
        receipt = self.post("guide-reply", body)
        current = self.fixture.current()
        jobs = self.snapshot()["jobs"]
        remembered = self.fixture.mutate("remember", current, sourceMessageId=receipt["guideSource"]["messageId"])
        self.assertEqual(remembered["idea"]["body"], body["text"])
        provenance = remembered["idea"]["provenance"][-1]
        self.assertEqual(provenance["kind"], "assistant_suggestion")
        self.assertEqual(provenance["guideSource"], receipt["guideSource"])
        self.assertNotIn("sourceJobId", provenance)
        self.assertEqual(self.snapshot()["jobs"], jobs)
        other = self.fixture.open(ideaId=remembered["idea"]["id"], expectedIdeaRevision=remembered["idea"]["revision"])
        # Linking this idea creates an independent record; foreign ID is rejected.
        self.error(lambda: self.fixture.mutate("remember", other, sourceMessageId=receipt["guideSource"]["messageId"]), 409, "answer_source_mismatch")

    def test_guide_remember_rejects_modified_body_and_same_record_other_session(self):
        saved = self.fixture.mutate("save", self.fixture.open(), text="同 idea")
        sent = self.send(saved)
        receipt = self.post("guide-reply", self.reply_body(sent))
        message_id = receipt["guideSource"]["messageId"]
        with self.service._db() as db:
            db.execute("UPDATE messages SET text=text||' changed' WHERE id=?", (message_id,))
        before = self.snapshot()
        self.error(lambda: self.fixture.mutate("remember", self.fixture.current(), sourceMessageId=message_id), 409, "answer_source_mismatch")
        self.assertEqual(self.snapshot(), before)
        other = self.fixture.open(ideaId=saved["idea"]["id"], expectedIdeaRevision=saved["idea"]["revision"])
        self.assertEqual(other["session"]["recordId"], sent["session"]["recordId"])
        before = self.snapshot()
        self.error(lambda: self.fixture.mutate("remember", other, sourceMessageId=message_id), 409, "answer_source_mismatch")
        self.assertEqual(self.snapshot(), before)


class GuidePhoneRoutes(unittest.TestCase):
    def test_paired_phone_cannot_read_or_write_guide_routes(self):
        http = fixture("check-mobile-dialogue-http")
        instance = http.MobileDialogueHttpChecks(methodName="runTest")
        instance.setUp()
        try:
            instance.pair()
            for action in ("guide-source", "guide-reply"):
                path = http.PREFIX + "mobile/dialogue/" + action
                self.assertEqual(instance.call(path, {})[0], 404)
                self.assertIn(instance.get(path)[0], (403, 404))
                self.assertEqual(instance.call("/api/workflow/mobile/dialogue/" + action, {})[0], 404)
        finally:
            instance.tearDown()


if __name__ == "__main__":
    unittest.main(verbosity=2)
