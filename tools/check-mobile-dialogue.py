#!/usr/bin/env python3
"""Phone dialogue behavior in temporary databases; never sends to an App."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transfer_store import IncomingFile
from PIL import Image
from workflow_http import workflow_get, workflow_post
from workflow_service import WorkflowError, WorkflowService


def request(**fields):
    return {"requestId": str(uuid.uuid4()), **fields}


class ForbiddenModels:
    def config(self):
        return {"ready": False, "selected": "", "providers": []}

    def discuss(self, *_args, **_kwargs):
        raise AssertionError("Phone dialogue must never call a model API")


class MobileDialogueChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="console-mobile-dialogue-")
        self.root = Path(self.temporary.name)
        self.projects = [{"id": "console", "name": "Isolated Console", "root": str(self.root), "capabilities": ["result_import"]}]
        self.service = WorkflowService(self.root / "private", models=ForbiddenModels(), projects=self.projects)
        self.client = str(uuid.uuid4())

    def tearDown(self):
        self.service.shutdown()
        self.temporary.cleanup()

    def post(self, action, body):
        return workflow_post(self.service, "mobile/" + action, body)

    def current(self, client=None):
        return workflow_get(self.service, "mobile/dialogue", "clientId=" + (client or self.client))

    def open(self, **fields):
        return self.post("dialogue/open", request(clientId=self.client, **fields))

    def mutate(self, action, state, **fields):
        session = state["session"]
        body = request(clientId=self.client, sessionId=session["id"], expectedRevision=session["revision"])
        if action in {"draft", "send", "save"}:
            body.update(text="本轮问题", attachmentIds=[], requestedProfile=session["requestedProfile"])
        body.update(fields)
        return self.post("dialogue/" + action, body)

    def counts(self):
        with self.service._db() as db:
            return {table: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] for table in ("records", "messages", "ideas", "jobs", "idea_dispatches")}

    def error(self, operation, code=None):
        with self.assertRaises(WorkflowError) as caught:
            operation()
        if code:
            self.assertEqual(caught.exception.code, code)
        return caught.exception

    def answer(self, sent, text="这是隔离测试回答"):
        dispatch_id = sent["job"]["appDispatch"]["id"]
        claimed = self.service.incubator_claim(request(id=dispatch_id))
        self.assertIs(claimed["shouldDispatch"], True)
        dispatch = claimed["dispatch"]
        self.service.incubator_attach_result(request(id=dispatch_id, claimToken=dispatch["claimToken"],
            status="completed", targetThreadId=str(uuid.uuid4()),
            result={"text": text, "sourceMessageId": str(uuid.uuid4()), "turnId": str(uuid.uuid4())}))
        detail = self.service.detail(sent["session"]["recordId"])
        return next(message for message in detail["messages"] if message["role"] == "assistant")

    def image(self, state):
        spool = self.root / (uuid.uuid4().hex + ".png")
        Image.new("RGB", (2, 2), "blue").save(spool, "PNG")
        result = self.service.upload(request(recordId=state["session"]["recordId"]),
            [IncomingFile(spool, 0, spool.stat().st_size, "selected.png", "image/png")])
        return result["attachments"][-1]["id"]

    def test_get_is_readonly_and_open_does_not_create_a_long_term_idea(self):
        before = self.counts()
        state = self.current()
        self.assertIsNone(state["session"])
        self.assertIsNone(state["detail"])
        self.assertEqual(before, self.counts())
        state = self.open()
        self.assertEqual(state["session"]["requestedProfile"], "high")
        self.assertEqual(state["detail"]["messages"], [])
        self.assertEqual(self.counts()["ideas"], 0)
        self.assertEqual(self.counts()["idea_dispatches"], 0)

    def test_open_nonce_is_idempotent_and_open_without_idea_recovers_current(self):
        body = request(clientId=self.client)
        first = self.post("dialogue/open", body)
        second = self.post("dialogue/open", body)
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["session"]["id"], second["session"]["id"])
        self.assertEqual(self.open()["session"]["id"], first["session"]["id"])
        self.assertEqual(self.counts()["records"], 1)

    def test_draft_and_selected_profile_survive_service_reopen_without_dispatch(self):
        state = self.mutate("draft", self.open(), text="未发送草稿", requestedProfile="pro")
        self.service = WorkflowService(self.root / "private", models=ForbiddenModels(), recover_jobs=False)
        restored = self.current()
        self.assertEqual(restored["session"], state["session"])
        self.assertEqual(restored["session"]["draft"]["text"], "未发送草稿")
        self.assertEqual(restored["preferences"]["requestedProfile"], "pro")
        self.assertEqual(self.counts()["messages"], 0)
        self.assertEqual(self.counts()["idea_dispatches"], 0)

    def test_clear_creates_new_identity_and_keeps_old_draft_record_and_profile(self):
        first = self.mutate("draft", self.open(), text="问题A草稿", requestedProfile="fast")
        second = self.mutate("clear", first)
        self.assertNotEqual(first["session"]["id"], second["session"]["id"])
        self.assertNotEqual(first["session"]["recordId"], second["session"]["recordId"])
        self.assertEqual(second["session"]["draft"], {"text": "", "attachmentIds": []})
        self.assertEqual(second["session"]["requestedProfile"], "fast")
        with self.service._db() as db:
            old = self.service._mobile_session(db, self.client, first["session"]["id"])
        self.assertEqual(old["draft"]["text"], "问题A草稿")
        self.assertEqual(self.counts()["records"], 2)

    def test_send_freezes_one_record_profile_and_session_without_claiming_delivery(self):
        sent = self.mutate("send", self.open(), text="准确本轮问题", requestedProfile="pro")
        job = sent["job"]
        dispatch = self.service.incubator_dispatches()["dispatches"][0]
        self.assertEqual(job["status"], "waiting")
        self.assertEqual(dispatch["status"], "pending")
        self.assertEqual(dispatch["targetKind"], "chatgpt")
        self.assertEqual(dispatch["targetMode"], "new")
        self.assertTrue(dispatch["userConfirmedAt"])
        self.assertEqual(dispatch["snapshot"]["requestedProfile"], "pro")
        self.assertEqual(dispatch["snapshot"]["mobileDialogue"]["id"], sent["session"]["id"])
        with self.service._db() as db:
            payload = json.loads(db.execute("SELECT payload FROM jobs WHERE id=?", (job["id"],)).fetchone()[0])
            priority = db.execute("SELECT priority FROM idea_dispatches").fetchone()[0]
        self.assertEqual(priority, "normal", "requested profile is not queue priority")
        for value in (payload, payload["appFrozen"]):
            self.assertEqual(value["requestedProfile"], "pro")
        self.assertNotIn("requestedProfile", payload["appTarget"])
        self.assertEqual(payload["appFrozen"]["history"], [])
        self.assertEqual(job["actualReceipt"]["actualProfile"], None)
        self.assertFalse(job["actualReceipt"]["verified"])
        self.assertEqual(sent["execution"]["relayStatus"], "not_connected")
        self.assertEqual(sent["session"]["draft"]["text"], "")

    def test_late_answer_returns_only_to_original_record_after_clear_and_question_b(self):
        first = self.mutate("send", self.open(), text="问题A")
        second = self.mutate("clear", first)
        sent_b = self.mutate("send", second, text="问题B")
        answer = self.answer(first, "回答A，不能进入B")
        current = self.current()
        self.assertEqual(current["session"]["id"], sent_b["session"]["id"])
        self.assertEqual([message["text"] for message in current["detail"]["messages"]], ["问题B"])
        self.assertEqual(self.service.detail(first["session"]["recordId"])["messages"][-1]["id"], answer["id"])
        with self.service._db() as db:
            payload_b = json.loads(db.execute("SELECT payload FROM jobs WHERE id=?", (sent_b["job"]["id"],)).fetchone()[0])
        self.assertEqual(payload_b["appFrozen"]["history"], [])
        self.error(lambda: self.mutate("remember", current, sourceMessageId=answer["id"]), "answer_source_mismatch")

    def test_send_nonce_replay_after_clear_never_republishes_or_changes_current(self):
        state = self.open(); session = state["session"]
        body = request(clientId=self.client, sessionId=session["id"], expectedRevision=1,
            text="发一次", attachmentIds=[], requestedProfile="high")
        first = self.post("dialogue/send", body)
        second = self.mutate("clear", first)
        replay = self.post("dialogue/send", body)
        self.assertTrue(replay["duplicate"])
        self.assertFalse(replay["session"]["isCurrent"])
        self.assertEqual(replay["job"]["id"], first["job"]["id"])
        self.assertEqual(self.current()["session"]["id"], second["session"]["id"])
        self.assertEqual(self.counts()["idea_dispatches"], 1)
        self.error(lambda: self.post("dialogue/send", {**body, "text": "另一个问题"}))

    def test_old_session_new_nonce_and_other_phone_cannot_modify_current(self):
        first = self.open()
        second = self.mutate("clear", first)
        self.error(lambda: self.mutate("send", first), "dialogue_changed")
        session = second["session"]
        self.error(lambda: self.post("dialogue/draft", request(clientId=str(uuid.uuid4()), sessionId=session["id"],
            expectedRevision=session["revision"], text="错误手机")), "dialogue_not_matching")
        self.assertEqual(self.current()["session"]["draft"]["text"], "")

    def test_stale_draft_revision_preserves_the_other_editor_and_nonce_retries(self):
        first = self.open(); session = first["session"]
        body = request(clientId=self.client, sessionId=session["id"], expectedRevision=1, text="已保存")
        accepted = self.post("dialogue/draft", body)
        self.error(lambda: self.mutate("draft", first, text="过期编辑"), "revision_conflict")
        duplicate = self.post("dialogue/draft", body)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["session"]["revision"], accepted["session"]["revision"])
        self.assertEqual(self.current()["session"]["draft"]["text"], "已保存")

    def test_save_needs_no_task_form_and_reuses_the_existing_task_record(self):
        state = self.mutate("save", self.open(), text="未成熟想法\n不需要项目或优先级表单")
        idea = state["idea"]
        self.assertEqual(idea["title"], "未成熟想法")
        self.assertEqual(idea["priority"], "normal")
        self.assertEqual(idea["projectId"], None)
        self.assertEqual(idea["workflowRecordId"], state["session"]["recordId"])
        self.assertEqual(self.counts()["jobs"], 0)
        self.assertEqual(self.counts()["idea_dispatches"], 0)
        self.assertEqual(self.current()["session"]["draft"], {"text": "", "attachmentIds": []})
        self.mutate("clear", state)
        restored = self.open(ideaId=idea["id"], expectedIdeaRevision=idea["revision"])
        self.assertEqual(restored["session"]["recordId"], idea["workflowRecordId"])
        self.assertEqual(restored["detail"]["sourceTask"]["body"], idea["body"])

    def test_save_appends_to_linked_idea_and_preserves_source_revisions(self):
        first = self.mutate("save", self.open(), text="原想法")
        second = self.mutate("save", first, text="用户补充")
        self.assertEqual(second["idea"]["id"], first["idea"]["id"])
        self.assertEqual(second["idea"]["body"], "原想法\n\n用户补充")
        self.assertEqual(second["idea"]["revision"], 2)
        provenance = second["idea"]["provenance"][-1]
        self.assertEqual(provenance["kind"], "user_saved")
        self.assertEqual(provenance["sourceIdeaRevision"], 1)
        self.assertEqual(provenance["destinationRevision"], 2)
        self.assertEqual(self.counts()["idea_dispatches"], 0)

    def test_saved_attachments_remain_and_chat_image_rejection_keeps_draft(self):
        state = self.open(); image = self.image(state)
        draft = self.mutate("draft", state, text="有原图的草稿", attachmentIds=[image])
        self.error(lambda: self.mutate("send", draft, text="有原图的草稿", attachmentIds=[image]), "app_images_unavailable")
        self.assertEqual(self.current()["session"]["draft"], draft["session"]["draft"])
        saved = self.mutate("save", draft, text="", attachmentIds=[image])
        self.assertEqual(saved["idea"]["imageCount"], 1)
        self.assertEqual(saved["idea"]["provenance"][-1]["attachmentIds"], [image])
        self.mutate("clear", saved)
        self.assertEqual(len(self.service.detail(saved["session"]["recordId"])["attachments"]), 1)
        self.assertEqual(self.counts()["idea_dispatches"], 0)

    def test_other_record_attachment_cannot_enter_current_draft(self):
        first = self.open(); image = self.image(first)
        second = self.mutate("clear", first)
        self.error(lambda: self.mutate("draft", second, attachmentIds=[image]))
        self.assertEqual(self.current()["session"]["draft"]["attachmentIds"], [])

    def test_remember_actual_answer_creates_suggestion_with_frozen_origin_only(self):
        saved = self.mutate("save", self.open(), text="原任务")
        sent = self.mutate("send", saved, text="请讨论这一点")
        answer = self.answer(sent, "助手建议，不是用户决定")
        remembered = self.mutate("remember", self.current(), sourceMessageId=answer["id"])
        idea = remembered["idea"]
        self.assertNotEqual(idea["id"], saved["idea"]["id"])
        self.assertEqual(idea["body"], answer["text"])
        self.assertEqual(idea["keyPoints"][0]["kind"], "suggestion")
        provenance = idea["provenance"][-1]
        self.assertEqual(provenance["sourceMessageId"], answer["id"])
        self.assertEqual(provenance["sourceIdeaId"], saved["idea"]["id"])
        self.assertEqual(provenance["sourceIdeaRevision"], 1)
        self.assertEqual(remembered["session"]["ideaId"], saved["idea"]["id"])
        with self.service._db() as db:
            self.assertEqual(self.service._source_task(db, sent["session"]["recordId"])["ideaId"], saved["idea"]["id"])

    def test_append_answer_checks_destination_revision_and_does_not_duplicate(self):
        saved = self.mutate("save", self.open(), text="原想法")
        sent = self.mutate("send", saved)
        answer = self.answer(sent, "新增结论")
        state = self.current()
        self.error(lambda: self.mutate("remember", state, sourceMessageId=answer["id"],
            ideaId=saved["idea"]["id"], expectedIdeaRevision=2), "revision_conflict")
        session = state["session"]
        body = request(clientId=self.client, sessionId=session["id"], expectedRevision=session["revision"],
            sourceMessageId=answer["id"], ideaId=saved["idea"]["id"], expectedIdeaRevision=1)
        first = self.post("dialogue/remember", body)
        second = self.post("dialogue/remember", body)
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["idea"]["body"], "原想法\n\n新增结论")
        self.assertEqual(len(second["idea"]["keyPoints"]), 1)

    def test_user_message_is_not_a_completed_answer(self):
        sent = self.mutate("send", self.open())
        message = sent["detail"]["messages"][0]
        self.error(lambda: self.mutate("remember", sent, sourceMessageId=message["id"]), "answer_source_mismatch")
        self.assertEqual(self.counts()["ideas"], 0)

    def test_user_can_edit_delete_points_and_save_execution_draft_without_changing_body(self):
        sent = self.mutate("send", self.open()); answer = self.answer(sent)
        idea = self.mutate("remember", self.current(), sourceMessageId=answer["id"])["idea"]
        point = idea["keyPoints"][0]
        changed = self.post("idea/update", request(id=idea["id"], expectedRevision=idea["revision"],
            keyPoints=[{"id": point["id"], "text": "用户确认采用此决定", "kind": "decision"}], executionDraft="集中确认前的执行稿"))["idea"]
        self.assertEqual(changed["body"], idea["body"])
        self.assertEqual(changed["keyPoints"][0]["source"], point["source"])
        self.assertEqual(changed["keyPoints"][0]["kind"], "decision")
        deleted = self.post("idea/update", request(id=idea["id"], expectedRevision=changed["revision"], keyPoints=[]))["idea"]
        self.assertEqual(deleted["keyPoints"], [])
        self.assertEqual(deleted["executionDraft"], "集中确认前的执行稿")
        self.assertEqual(self.counts()["idea_dispatches"], 1, "editing execution draft never executes it")

    def test_current_idea_points_are_frozen_into_next_mobile_prompt_without_rewriting_previous_round(self):
        initial = self.mutate("send", self.open())
        answer = self.answer(initial, "旧助手建议，尚未决定")
        idea = self.mutate("remember", self.current(), sourceMessageId=answer["id"])["idea"]
        linked = self.open(ideaId=idea["id"], expectedIdeaRevision=idea["revision"])
        first = self.mutate("send", linked, text="讨论已保存想法")
        first_id = first["job"]["appDispatch"]["id"]
        with self.service._db() as db:
            first_snapshot = db.execute("SELECT snapshot FROM idea_dispatches WHERE id=?", (first_id,)).fetchone()[0]
            first_payload = db.execute("SELECT payload FROM jobs WHERE id=?", (first["job"]["id"],)).fetchone()[0]
        old_context = json.loads(first_payload)["appFrozen"]["mobileIdeaContext"]
        self.assertEqual(old_context["keyPoints"], [{key: idea["keyPoints"][0][key] for key in ("id", "text", "kind")}])
        self.assertEqual(old_context["provenance"][0]["id"], idea["provenance"][0]["id"])
        self.answer(first, "历史回答不等于当前决定")
        points = [{"id": idea["keyPoints"][0]["id"], "text": "用户最新确认的决定", "kind": "decision"},
            {"id": uuid.uuid4().hex, "text": "另一待确认建议", "kind": "suggestion"}]
        edited = self.post("idea/update", request(id=idea["id"], expectedRevision=idea["revision"], keyPoints=points))["idea"]
        self.error(lambda: self.mutate("send", self.current()), "revision_conflict")
        second = self.mutate("send", self.open(ideaId=idea["id"], expectedIdeaRevision=edited["revision"]))
        dispatch = next(item for item in self.service.incubator_dispatches()["dispatches"] if item["id"] == second["job"]["appDispatch"]["id"])
        context = dispatch["snapshot"]["mobileIdeaContext"]
        self.assertEqual((context["id"], context["revision"], context["keyPoints"]), (idea["id"], edited["revision"], points))
        with self.service._db() as db:
            prompt = db.execute("SELECT prompt FROM idea_dispatches WHERE id=?", (dispatch["id"],)).fetchone()[0]
        self.assertIn(json.dumps(context, ensure_ascii=False, separators=(",", ":")), prompt)
        self.assertIn("kind=suggestion 是仍待用户确认的建议", prompt)
        self.answer(second)
        deleted = self.post("idea/update", request(id=idea["id"], expectedRevision=edited["revision"], keyPoints=[]))["idea"]
        third = self.mutate("send", self.open(ideaId=idea["id"], expectedIdeaRevision=deleted["revision"]))
        with self.service._db() as db:
            third_payload = json.loads(db.execute("SELECT payload FROM jobs WHERE id=?", (third["job"]["id"],)).fetchone()[0])
            self.assertEqual(db.execute("SELECT snapshot FROM idea_dispatches WHERE id=?", (first_id,)).fetchone()[0], first_snapshot)
            self.assertEqual(db.execute("SELECT payload FROM jobs WHERE id=?", (first["job"]["id"],)).fetchone()[0], first_payload)
        self.assertEqual(third_payload["appFrozen"]["mobileIdeaContext"]["keyPoints"], [])
        self.assertEqual(deleted["body"], idea["body"], "Deleting active points retains the original answer body and provenance")

    def test_clear_discussion_does_not_carry_saved_idea_points_into_new_temporary_session(self):
        saved = self.mutate("save", self.open(), text="长期底稿")
        point = {"id": uuid.uuid4().hex, "text": "长期决定", "kind": "decision"}
        idea = self.post("idea/update", request(id=saved["idea"]["id"], expectedRevision=1, keyPoints=[point]))["idea"]
        linked = self.open(ideaId=idea["id"], expectedIdeaRevision=idea["revision"])
        cleared = self.mutate("clear", linked)
        sent = self.mutate("send", cleared)
        with self.service._db() as db:
            frozen = json.loads(db.execute("SELECT payload FROM jobs WHERE id=?", (sent["job"]["id"],)).fetchone()[0])["appFrozen"]
        self.assertNotIn("mobileIdeaContext", frozen)
        self.assertEqual(frozen["history"], [])
        self.assertEqual(workflow_get(self.service, "mobile/idea", "id=" + idea["id"])["idea"]["keyPoints"][0]["text"], point["text"])

    def test_archive_search_classification_preserve_legacy_ideas_and_original_stage(self):
        legacy = self.service.incubator_create(request(title="应用定制员", body="Existing record", stage="ready"))["idea"]
        saved = self.mutate("save", self.open(), text="音乐分类方案")["idea"]
        classified = self.post("idea/update", request(id=saved["id"], expectedRevision=1, projectId="console"))["idea"]
        self.assertEqual([idea["id"] for idea in workflow_get(self.service, "mobile/ideas", "search=音乐&projectId=console")["ideas"]], [saved["id"]])
        self.assertIn(legacy["id"], [idea["id"] for idea in workflow_get(self.service, "mobile/ideas", "projectId=unclassified")["ideas"]])
        archived = self.post("idea/archive", request(id=saved["id"], expectedRevision=classified["revision"], archived=True))["idea"]
        self.assertEqual(archived["body"], saved["body"])
        self.assertNotIn(saved["id"], [idea["id"] for idea in workflow_get(self.service, "mobile/ideas", "")["ideas"]])
        self.assertEqual(workflow_get(self.service, "mobile/ideas", "archived=1")["ideas"][0]["id"], saved["id"])
        self.assertEqual(workflow_get(self.service, "mobile/idea", "id=" + legacy["id"])["idea"]["stage"], "ready")

    def test_definitely_unsent_failed_dispatch_can_be_explicitly_retried_with_profile(self):
        sent = self.mutate("send", self.open(), requestedProfile="pro")
        dispatch_id = sent["job"]["appDispatch"]["id"]
        claimed = self.service.incubator_claim(request(id=dispatch_id))["dispatch"]
        self.service.incubator_fail(request(id=dispatch_id, claimToken=claimed["claimToken"], status="failed", error="Isolated fixture: definitely not sent"))
        retried = self.service.retry(request(jobId=sent["job"]["id"]))
        self.assertEqual(retried["job"]["requestedProfile"], "pro")
        self.assertEqual(retried["job"]["status"], "waiting")
        self.assertNotEqual(retried["job"]["appDispatch"]["id"], dispatch_id)
        with self.service._db() as db:
            payload = json.loads(db.execute("SELECT payload FROM jobs WHERE id=?", (retried["job"]["id"],)).fetchone()[0])
        self.assertEqual(payload["appFrozen"]["requestedProfile"], "pro")
        self.assertEqual(payload["mobileDialogue"]["id"], sent["session"]["id"])
        self.assertEqual(self.service.incubator_dispatches()["dispatches"][-1]["snapshot"]["requestedProfile"], "pro")

    def test_save_refresh_and_reopen_have_empty_draft_without_duplicate_append(self):
        drafted = self.mutate("draft", self.open(), text="保存这条草稿")
        saved = self.mutate("save", drafted, text="保存这条草稿")
        self.assertEqual(saved["session"]["draft"], {"text": "", "attachmentIds": []})
        self.assertEqual(self.current()["session"]["draft"], {"text": "", "attachmentIds": []})
        self.assertEqual(self.open()["session"]["draft"], {"text": "", "attachmentIds": []})
        self.assertEqual(workflow_get(self.service, "mobile/idea", "id=" + saved["idea"]["id"])["idea"]["body"], "保存这条草稿")

    def test_all_new_post_routes_recheck_authorization_and_reject_extra_execution_fields(self):
        state = self.open(); session = state["session"]
        identity = {"clientId": self.client, "sessionId": session["id"], "expectedRevision": 1}
        idea = self.service.incubator_create(request(title="Existing idea"))["idea"]
        actions = {"dialogue/open": {"clientId": self.client}, "dialogue/clear": identity, "dialogue/draft": identity,
            "dialogue/send": {**identity, "text": "Current question"}, "dialogue/save": {**identity, "text": "Only save"},
            "dialogue/remember": {**identity, "sourceMessageId": uuid.uuid4().hex},
            "idea/update": {"id": idea["id"], "expectedRevision": 1, "title": "Changed"},
            "idea/archive": {"id": idea["id"], "expectedRevision": 1, "archived": True}}
        for action, fields in actions.items():
            calls = []
            def reject():
                calls.append(1)
                raise WorkflowError("Revoked phone", 403)
            body = request(**fields)
            self.error(lambda: workflow_post(self.service, "mobile/" + action, body, authorize=reject))
            self.assertEqual(calls, [1], action)
        self.error(lambda: self.mutate("draft", state, dispatch=True))
        self.assertEqual(self.counts()["idea_dispatches"], 0)

    def test_edit_in_another_view_invalidates_old_source_revision_without_dispatch(self):
        state = self.mutate("save", self.open(), text="原底稿")
        idea = state["idea"]
        self.post("idea/update", request(id=idea["id"], expectedRevision=1, body="另一端新底稿"))
        self.error(lambda: self.mutate("send", state), "revision_conflict")
        self.assertEqual(self.counts()["idea_dispatches"], 0)
        reopened = self.open(ideaId=idea["id"], expectedIdeaRevision=2)
        sent = self.mutate("send", reopened)
        self.assertEqual(self.service.incubator_dispatches()["dispatches"][0]["snapshot"]["sourceTask"]["body"], "另一端新底稿")

    def test_profile_values_and_revision_types_are_strict_and_real_receipt_stays_unverified(self):
        state = self.open()
        for invalid in ("speed", "instant", [], True):
            self.error(lambda: self.mutate("draft", state, requestedProfile=invalid))
        for invalid in (True, "1", 0):
            self.error(lambda: self.mutate("draft", state, expectedRevision=invalid))
        sent = self.mutate("send", state, requestedProfile="fast")
        self.answer(sent, "仅实际测试回答，不含档位宣称")
        completed = self.current()["detail"]["jobs"][0]
        self.assertEqual(completed["result"]["text"], "仅实际测试回答，不含档位宣称")
        self.assertFalse(completed["actualReceipt"]["verified"])

    def test_phone_authorization_is_rechecked_and_denial_rolls_back_every_write(self):
        state = self.open(); session = state["session"]
        calls = []
        def authorize():
            calls.append(1)
            if len(calls) == 2:
                raise WorkflowError("Phone was revoked", 403)
        before = self.counts()
        body = request(clientId=self.client, sessionId=session["id"], expectedRevision=1, text="不能发送")
        self.error(lambda: workflow_post(self.service, "mobile/dialogue/send", body, authorize=authorize))
        self.assertEqual(before, self.counts())
        self.assertEqual(self.current()["session"]["revision"], 1)

    def test_existing_tables_and_records_are_not_rebuilt_or_dropped(self):
        legacy = self.service.create(request(projectId="console", title="原工作记录", text="原记录正文"))["record"]["id"]
        before_detail = self.service.detail(legacy)
        with self.service._db() as db:
            before_tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        state = self.mutate("save", self.open(), text="新增想法")
        self.mutate("clear", state)
        after_detail = self.service.detail(legacy)
        before_detail.pop("revision"); after_detail.pop("revision")
        self.assertEqual(before_detail, after_detail)
        with self.service._db() as db:
            self.assertEqual(before_tables, [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
