#!/usr/bin/env python3
"""Guide phone inputs in disposable databases and paired localhost only."""
import copy
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


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), Path(__file__).with_name(name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


reply = load("check-guide-reply")
mobile = reply.mobile


class GuideInputs(unittest.TestCase):
    def setUp(self):
        self.fixture = reply.GuideReplyChecks(methodName="runTest")
        self.fixture.setUp()
        self.service = self.fixture.service
        self.mobile = self.fixture.fixture
        self.client = self.fixture.client
        self.chat = self.fixture.chat_id
        self.state = self.mobile.open()

    def tearDown(self):
        self.fixture.tearDown()

    def body(self, state=None, **changes):
        session = (state or self.state)["session"]
        fields = {"clientId": self.client, "sessionId": session["id"], "recordId": session["recordId"],
            "expectedRevision": session["revision"], "text": " 用户原文\r\n 第二行\n  ", "attachmentIds": []}
        fields.update(changes)
        return mobile.request(**fields)

    def send(self, body, **options):
        return workflow_post(self.service, "mobile/dialogue/guide-send", body, prefix="/api/phone/workflow", **options)

    def receipt(self, body, **options):
        return workflow_get(self.service, "mobile/dialogue/guide-send-receipt", urlencode({key: body[key] for key in
            ("requestId", "clientId", "sessionId", "recordId")}), prefix="/api/phone/workflow", **options)

    def inbox(self, cursor="0", limit="20", **changes):
        query = {"sourceGuideChatId": self.chat, "clientId": self.client, "cursor": cursor, "limit": limit}
        query.update(changes)
        return workflow_get(self.service, "mobile/dialogue/guide-inbox", urlencode(query), desktop=True)

    def snapshot(self):
        with self.service._db() as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            return {name: [tuple(row) for row in db.execute('SELECT * FROM "' + name + '" ORDER BY rowid')] for name in tables}

    def error(self, operation, status=None, code=None):
        return self.fixture.error(operation, status, code)

    def answer(self, sent, text="Guide 实际回答\r\n  原字符\n"):
        source = sent["guideSendReceipt"]
        body = mobile.request(clientId=source["clientId"], sessionId=source["sessionId"], recordId=source["recordId"],
            sourceUserMessageId=source["sourceUserMessageId"], sourceGuideChatId=source["sourceGuideChatId"], text=text)
        return self.fixture.post("guide-reply", body), body

    def test_explicit_send_exact_contract_preserves_chat_profile_transport_and_models(self):
        self.service.subscription = mobile.CachedSubscription()
        self.state = self.mobile.mutate("draft", self.state, text="API草稿", requestedProfile="pro",
            chatTransport="chatgpt_subscription", subscription=self.service.subscription.choice())
        body = self.body()
        before = self.snapshot()
        sent = self.send(body)
        source = sent["guideSendReceipt"]
        self.assertEqual(set(source), {"requestId", "target", "clientId", "sessionId", "recordId", "sourceUserMessageId",
            "sourceGuideChatId", "textSha256", "sourceSha256", "attachmentIds", "expectedRevision", "acceptedSessionRevision", "acceptedAt"})
        self.assertEqual(source["target"], "codex_guide")
        self.assertEqual(source["textSha256"], hashlib.sha256(body["text"].encode("utf-8")).hexdigest())
        self.assertEqual(source["acceptedSessionRevision"], body["expectedRevision"] + 1)
        self.assertEqual(source["sourceGuideChatId"], self.chat)
        self.assertEqual(sent["session"]["draft"], {"text": "", "attachmentIds": []})
        for key in ("requestedProfile", "chatTransport", "subscription"):
            self.assertEqual(sent["session"][key], self.state["session"][key])
        self.assertEqual(sent["preferences"], self.state["preferences"])
        self.assertEqual(sent["execution"], self.state["execution"])
        message = sent["detail"]["messages"][-1]
        self.assertEqual(message["role"], "user")
        self.assertEqual(message["text"], body["text"])
        self.assertEqual(message["guideInput"], sent["guide"]["requests"][-1])
        self.assertEqual(message["guideInput"]["sourceUserMessageId"], message["id"])
        self.assertEqual(message["guideInput"]["status"], "waiting")
        self.assertIsNone(message["guideInput"]["replyMessageId"])
        self.assertEqual(sent["guide"]["author"], "Codex Guide")
        self.assertEqual(sent["guide"]["coordinationIntervalSeconds"], 60)
        self.assertIs(sent["guide"]["available"], True)
        after = self.snapshot()
        for table in ("jobs", "idea_dispatches", "mobile_message_sources", "ideas"):
            self.assertEqual(after[table], before[table])

    def test_exact_fields_invalid_content_and_unbound_target_leave_draft_unchanged(self):
        body = self.body()
        before = self.snapshot()
        for extra in ("target", "sourceGuideChatId", "role", "author", "requestedProfile", "subscription"):
            self.error(lambda: self.send({**body, extra: "fake"}), 400)
        for text in (" \r\n", "x\0y", "x\ud800", "x" * 20001):
            self.error(lambda: self.send({**body, "text": text}), 400)
        self.error(lambda: self.send({key: value for key, value in body.items() if key != "recordId"}), 400)
        self.assertEqual(self.snapshot(), before)
        with self.service._db() as db:
            db.execute("DELETE FROM guide_sources")
        before = self.snapshot()
        self.error(lambda: self.send(body), 409, "guide_not_connected")
        self.assertEqual(self.snapshot(), before)
        self.assertIs(self.mobile.current()["guide"]["available"], False)

    def test_current_scope_revision_and_source_version_are_required(self):
        body = self.body()
        before = self.snapshot()
        for changed in ({**body, "expectedRevision": body["expectedRevision"] + 1}, {**body, "recordId": uuid.uuid4().hex},
                {**body, "clientId": str(uuid.uuid4())}, {**body, "sessionId": uuid.uuid4().hex}):
            self.error(lambda: self.send(changed))
        self.assertEqual(self.snapshot(), before)
        self.mobile.mutate("clear", self.state)
        self.error(lambda: self.send(body), 409, "dialogue_changed")
        saved = self.mobile.mutate("save", self.mobile.current(), text="原想法")
        self.state = self.mobile.open(ideaId=saved["idea"]["id"], expectedIdeaRevision=saved["idea"]["revision"])
        old = self.body()
        self.service.mobile_idea_update(mobile.request(id=saved["idea"]["id"], expectedRevision=saved["idea"]["revision"], body="新版本"))
        self.error(lambda: self.send(old), 409)

    def test_replay_and_unknown_result_lookup_are_readonly_and_cannot_clear_new_draft(self):
        body = self.body()
        sent = self.send(body)
        receipt = sent["guideSendReceipt"]
        self.state = self.mobile.mutate("draft", sent, text="下一条未发草稿")
        before = self.snapshot()
        self.assertEqual(self.send(body)["guideSendReceipt"], receipt)
        self.assertEqual(self.mobile.current()["session"], self.state["session"])
        self.assertEqual(self.snapshot(), before)
        db_before = self.service.data_dir.joinpath("workflow.sqlite3").read_bytes()
        with patch.object(self.service, "_db", side_effect=AssertionError("receipt GET cannot write")):
            self.assertEqual(self.receipt(body), {"guideSendReceipt": receipt, "isCurrent": True})
            self.error(lambda: self.receipt({**body, "requestId": str(uuid.uuid4())}), 404, "guide_send_receipt_not_found")
        self.assertEqual(self.service.data_dir.joinpath("workflow.sqlite3").read_bytes(), db_before)
        for changed in ({**body, "text": body["text"] + " "}, {**body, "attachmentIds": [uuid.uuid4().hex]},
                {**body, "recordId": uuid.uuid4().hex}, {**body, "expectedRevision": body["expectedRevision"] + 1}):
            self.error(lambda: self.send(changed), 409)

    def test_clear_then_accepted_replay_and_late_reply_stay_original_scope(self):
        body = self.body()
        sent = self.send(body)
        current = self.mobile.mutate("clear", sent)
        current = self.mobile.mutate("draft", current, text="新讨论草稿")
        before = self.snapshot()
        replay = self.send(body)
        self.assertIs(replay["session"]["isCurrent"], False)
        self.assertEqual(self.snapshot(), before)
        self.assertIs(self.receipt(body)["isCurrent"], False)
        self.assertEqual(self.mobile.current()["session"], current["session"])
        stream = self.fixture.subscribe(current)
        late, _ = self.answer(sent)
        self.assertIs(late["isCurrent"], False)
        self.assertIsNone(stream.next_event(0))
        self.assertEqual(self.mobile.current()["session"], current["session"])
        self.assertEqual(self.mobile.current()["guide"]["requests"], [])
        self.assertEqual(self.inbox()["items"], [])

    def test_direct_reply_and_remember_are_real_without_model_job(self):
        body = self.body()
        sent = self.send(body)
        before = self.snapshot()
        receipt, reply_body = self.answer(sent)
        current = self.mobile.current()
        self.assertEqual(current["guide"]["requests"][-1]["status"], "replied")
        self.assertEqual(current["guide"]["requests"][-1]["replyMessageId"], receipt["guideSource"]["messageId"])
        self.assertEqual(current["detail"]["messages"][0]["guideInput"], current["guide"]["requests"][-1])
        self.assertEqual(current["detail"]["messages"][-1]["text"], reply_body["text"])
        self.assertEqual(self.fixture.post("guide-reply", reply_body), receipt)
        remembered = self.mobile.mutate("remember", current, sourceMessageId=receipt["guideSource"]["messageId"])
        self.assertEqual(remembered["idea"]["body"], reply_body["text"])
        self.assertEqual(remembered["idea"]["provenance"][-1]["guideSource"], receipt["guideSource"])
        after = self.snapshot()
        for table in ("jobs", "idea_dispatches", "mobile_message_sources"):
            self.assertEqual(after[table], before[table])

    def test_send_and_reply_commit_scoped_six_field_events_and_replay_is_quiet(self):
        stream = self.fixture.subscribe(self.state)
        body = self.body()
        sent = self.send(body)
        frame = stream.next_event(0)
        self.assertEqual(frame["event"], "dialogue.result")
        self.assertEqual(set(frame["data"]), {"clientId", "sessionId", "recordId", "cursor", "jobId", "status"})
        self.assertIsNone(frame["data"]["jobId"])
        self.assertEqual(frame["data"]["status"], "idle")
        self.send(body)
        self.assertIsNone(stream.next_event(0))
        receipt, reply_body = self.answer(sent)
        answered = stream.next_event(0)
        self.assertEqual(answered["event"], "dialogue.result")
        self.assertNotEqual(answered["data"]["cursor"], frame["data"]["cursor"])
        self.fixture.post("guide-reply", reply_body)
        self.assertIsNone(stream.next_event(0))

    def test_authorization_revocation_rolls_back_message_source_nonce_draft_and_event(self):
        stream = self.fixture.subscribe(self.state)
        before = self.snapshot()
        calls = []
        def authorize():
            calls.append(True)
            if len(calls) == 2:
                raise WorkflowError("revoked", 403)
        self.error(lambda: self.send(self.body(), authorize=authorize), 403)
        self.assertEqual(self.snapshot(), before)
        self.assertIsNone(stream.next_event(0))

    def test_concurrent_same_request_from_separate_services_saves_once(self):
        body = self.body()
        other = WorkflowService(self.service.data_dir, models=mobile.ForbiddenModels(), projects=self.mobile.projects, recover_jobs=False)
        self.fixture.other_services.append(other)
        barrier = threading.Barrier(2)
        outputs, errors = [], []
        def operation(service):
            try:
                barrier.wait(3)
                outputs.append(service.mobile_dialogue_guide_send(body))
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=operation, args=(service,)) for service in (self.service, other)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(6)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(len(outputs), 2)
        self.assertEqual(outputs[0]["guideSendReceipt"], outputs[1]["guideSendReceipt"])
        snapshot = self.snapshot()
        self.assertEqual(len(snapshot["guide_inputs"]), 1)
        self.assertEqual(len(snapshot["messages"]), 1)
        self.assertEqual(snapshot["jobs"], [])

    def test_image_snapshot_inbox_link_and_file_hash_are_exact(self):
        image = self.mobile.image(self.state)
        body = {**self.body(), "attachmentIds": [image], "text": ""}
        sent = self.send(body)
        inbox = self.inbox()
        item = inbox["items"][0]
        self.assertEqual(item["text"], "")
        self.assertEqual(item["guideSendReceipt"]["attachmentIds"], [image])
        self.assertEqual(item["images"][0]["id"], image)
        self.assertTrue(item["images"][0]["url"].startswith("/api/workflow/attachment?id="))
        path = self.service.attachment("id=" + image)["path"]
        self.assertEqual(item["images"][0]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        path.write_bytes(b"changed-original")
        before = self.snapshot()
        self.error(lambda: self.inbox(), 409, "guide_source_not_matching")
        self.error(lambda: self.answer(sent), 409, "guide_source_not_matching")
        self.assertEqual(self.snapshot(), before)

    def test_bad_direct_source_never_downgrades_to_old_job_recovery(self):
        sent = self.send(self.body())
        with self.service._db() as db:
            row = dict(db.execute("SELECT * FROM guide_inputs").fetchone())
        for field, value in (("client_id", str(uuid.uuid4())), ("text_sha256", "f" * 64),
                ("source_guide_chat_id", str(uuid.uuid4())), ("request_body", "{}"),
                ("attachment_ids", json.dumps([uuid.uuid4().hex])), ("source_snapshot", "[]")):
            with self.subTest(field=field):
                with self.service._db() as db:
                    db.execute("UPDATE guide_inputs SET " + field + "=? WHERE seq=?", (value, row["seq"]))
                before = self.snapshot()
                with patch.object(self.service, "_guide_original_send", side_effect=AssertionError("direct source cannot fall back")):
                    self.error(lambda: self.answer(sent), 409, "guide_source_not_matching")
                self.assertEqual(self.snapshot(), before)
                with self.service._db() as db:
                    db.execute("UPDATE guide_inputs SET " + field + "=? WHERE seq=?", (row[field], row["seq"]))

    def test_frozen_context_and_image_proofs_are_anchored_by_persistent_receipt(self):
        saved = self.mobile.mutate("save", self.state, text="发送当时的长期来源")
        self.state = self.mobile.open(ideaId=saved["idea"]["id"], expectedIdeaRevision=saved["idea"]["revision"])
        image = self.mobile.image(self.state)
        body = self.body(attachmentIds=[image])
        sent = self.send(body)
        with self.service._db() as db:
            row = dict(db.execute("SELECT * FROM guide_inputs").fetchone())
        snapshot = json.loads(row["source_snapshot"])
        proofs = json.loads(row["attachment_proofs"])
        self.assertEqual(sent["guideSendReceipt"]["sourceSha256"], hashlib.sha256(_json({
            "sourceSnapshot": snapshot, "attachmentProofs": proofs}).encode("utf-8")).hexdigest())
        changed_task = copy.deepcopy(snapshot)
        changed_task["sourceTask"]["body"] = "改写冻结来源"
        changed_points = copy.deepcopy(snapshot)
        changed_points["ideaContext"]["keyPoints"] = [{"text": "后来未经发送确认的要点"}]
        changed_proofs = copy.deepcopy(proofs)
        changed_proofs[0]["name"] = "假图片.png"
        for field, value in (("source_snapshot", _json(changed_task)), ("source_snapshot", _json(changed_points)),
                ("attachment_proofs", _json(changed_proofs))):
            with self.subTest(field=field):
                with self.service._db() as db:
                    db.execute("UPDATE guide_inputs SET " + field + "=? WHERE seq=?", (value, row["seq"]))
                self.error(lambda: self.inbox(), 409, "guide_source_not_matching")
                self.error(lambda: self.receipt(body), 409, "guide_source_not_matching")
                self.error(lambda: self.answer(sent), 409, "guide_source_not_matching")
                with self.service._db() as db:
                    db.execute("UPDATE guide_inputs SET " + field + "=? WHERE seq=?", (row[field], row["seq"]))
        # Later legitimate editing preserves the accepted historical snapshot.
        self.service.mobile_idea_update(mobile.request(id=saved["idea"]["id"], expectedRevision=saved["idea"]["revision"], body="后来合法保存的新来源"))
        self.assertEqual(self.inbox()["items"][0]["sourceSnapshot"]["sourceTask"]["body"], "发送当时的长期来源")
        self.answer(sent)

    def test_inbox_readonly_scoped_pending_pagination_and_cursor_reset(self):
        bodies, sent = [], []
        for index in range(3):
            body = self.body(text="问题" + str(index))
            result = self.send(body)
            bodies.append(body)
            sent.append(result)
            self.state = result
        before = self.snapshot()
        original = self.service.data_dir.joinpath("workflow.sqlite3").read_bytes()
        with patch.object(self.service, "_db", side_effect=AssertionError("inbox GET cannot write")):
            first = self.inbox(limit="2")
            self.assertEqual(len(first["items"]), 2)
            self.assertIs(first["hasMore"], True)
            self.assertEqual(first["nextCursor"], first["items"][-1]["sequence"])
            second = self.inbox(first["nextCursor"], "2")
            self.assertEqual([item["text"] for item in second["items"]], ["问题2"])
            self.assertIs(second["hasMore"], False)
            self.assertEqual(len(self.inbox()["items"]), 3)
        self.assertEqual(self.service.data_dir.joinpath("workflow.sqlite3").read_bytes(), original)
        self.assertEqual(self.snapshot(), before)
        self.answer(sent[0])
        self.assertEqual([item["text"] for item in self.inbox()["items"]], ["问题1", "问题2"])
        for changes in ({"cursor": "99999999"}, {"cursor": "01"}, {"limit": "21"},
                {"sourceGuideChatId": str(uuid.uuid4())}, {"clientId": str(uuid.uuid4()), "cursor": first["nextCursor"]}):
            self.error(lambda: self.inbox(**changes))

    def test_same_record_other_session_filters_user_reply_and_history_before_limit(self):
        saved = self.mobile.mutate("save", self.state, text="共享任务底稿")
        self.state = self.mobile.open(ideaId=saved["idea"]["id"], expectedIdeaRevision=saved["idea"]["revision"])
        self.service.add_message(mobile.request(recordId=self.state["session"]["recordId"], text="普通历史应保留"))
        sent = []
        for index in range(13):
            item = self.send({**self.body(), "text": "旧Guide输入" + str(index)})
            sent.append(item)
            self.state = item
        current = self.mobile.open(ideaId=saved["idea"]["id"], expectedIdeaRevision=saved["idea"]["revision"])
        self.assertEqual(current["session"]["recordId"], self.state["session"]["recordId"])
        self.assertEqual(current["guide"]["requests"], [])
        self.assertFalse(any(message.get("guideInput") for message in current["detail"]["messages"]))
        stream = self.fixture.subscribe(current)
        self.answer(sent[-1])
        self.assertIsNone(stream.next_event(0))
        with self.service._db() as db:
            dialogue = {"clientId": self.client, "id": current["session"]["id"]}
            history = self.service._guide_history(db, current["session"]["recordId"], dialogue)
            self.assertTrue(any(row["text"] == "普通历史应保留" for row in history))
            self.assertFalse(any(row["text"].startswith("旧Guide输入") for row in history))
            work = self.service._codex_work_context(db, current["session"]["recordId"], dialogue)
            self.assertFalse(any(row["text"].startswith("旧Guide输入") for row in work["history"]))
        self.assertFalse(any(message.get("guideSource") for message in self.mobile.current()["detail"]["messages"]))

    def test_restart_retains_source_receipt_pending_and_reply_proof(self):
        body = self.body()
        sent = self.send(body)
        expected = sent["guideSendReceipt"]
        cursor = sent["resultCursor"]
        self.service.shutdown()
        self.service = self.fixture.service = self.mobile.service = WorkflowService(self.service.data_dir,
            models=mobile.ForbiddenModels(), projects=self.mobile.projects, recover_jobs=False)
        self.assertEqual(self.receipt(body)["guideSendReceipt"], expected)
        self.assertEqual(self.mobile.current()["resultCursor"], cursor)
        self.assertEqual(self.inbox()["items"][0]["guideSendReceipt"], expected)
        self.answer(sent)
        self.assertEqual(self.inbox()["items"], [])


class GuideInputHttp(unittest.TestCase):
    def test_actual_paired_phone_send_lookup_and_desktop_only_inbox(self):
        http = load("check-mobile-dialogue-http")
        instance = http.MobileDialogueHttpChecks(methodName="runTest")
        instance.setUp()
        try:
            chat = str(uuid.uuid4())
            workflow_post(instance.service, "mobile/dialogue/guide-source", mobile.request(sourceGuideChatId=chat), desktop=True)
            instance.pair()
            session = instance.open()
            client = str(uuid.UUID(instance.client_id))
            body = mobile.request(clientId=client, sessionId=session["id"], recordId=session["recordId"],
                expectedRevision=session["revision"], text="手机明确Guide消息", attachmentIds=[])
            path = http.PREFIX + "mobile/dialogue/guide-send"
            before = instance.counts()
            self.assertEqual(instance.call(path, body, cookie="")[0], 401)
            self.assertEqual(instance.call(path, body, headers={"Origin": "http://evil.invalid"})[0], 403)
            status, sent, _ = instance.call(path, body)
            self.assertEqual(status, 200, sent)
            self.assertEqual(instance.counts()["jobs"], before["jobs"])
            self.assertEqual(instance.counts()["idea_dispatches"], before["idea_dispatches"])
            query = urlencode({key: body[key] for key in ("requestId", "clientId", "sessionId", "recordId")})
            status, found, _ = instance.get(http.PREFIX + "mobile/dialogue/guide-send-receipt?" + query)
            self.assertEqual(status, 200, found)
            self.assertEqual(found["guideSendReceipt"], sent["guideSendReceipt"])
            status, unknown, _ = instance.get(http.PREFIX + "mobile/dialogue/guide-send-receipt?" + query.replace(body["requestId"], str(uuid.uuid4())))
            self.assertEqual(status, 404, unknown)
            self.assertEqual(instance.get(http.PREFIX + "mobile/dialogue/guide-inbox")[0], 403)
            self.assertEqual(instance.call(http.PREFIX + "mobile/dialogue/guide-reply", {})[0], 404)
        finally:
            instance.tearDown()


if __name__ == "__main__":
    unittest.main(verbosity=2)
