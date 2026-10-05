#!/usr/bin/env python3
"""Phone dialogue behavior in temporary databases; never sends to an App."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transfer_store import IncomingFile
from PIL import Image
from workflow_http import workflow_get, workflow_post
from workflow_service import WorkflowError, WorkflowService
from workflow_mobile_dialogue import MOBILE_IMAGE_BYTES


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
        fields, files = self.upload_request(state)
        result = self.service.mobile_dialogue_upload(fields, files)
        state.update(result)
        return result["uploadedAttachmentIds"][0]

    def upload_request(self, state, color="blue"):
        spool = self.root / (uuid.uuid4().hex + ".png")
        Image.new("RGB", (2, 2), color).save(spool, "PNG")
        session = state["session"]
        return request(recordId=session["recordId"], text=json.dumps({"clientId": self.client,
            "sessionId": session["id"], "expectedRevision": session["revision"]})), [
                IncomingFile(spool, 0, spool.stat().st_size, "selected.png", "image/png")]

    def save_idea(self, text):
        state = self.mutate("save", self.open(), text=text)
        self.mutate("clear", state)
        return state["idea"]

    def db_snapshot(self):
        with self.service._db() as db:
            return {table: [tuple(row) for row in db.execute("SELECT * FROM " + table + " ORDER BY rowid")]
                for table in ("settings", "requests", "attachments", "records", "messages", "ideas", "jobs", "idea_dispatches")}

    def files_snapshot(self):
        return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.service.attachments_dir.iterdir() if path.is_file()}

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

    def test_first_unclassified_phone_saves_recovers_clears_and_reopens_real_images_without_a_project(self):
        self.service = WorkflowService(self.root / "first-install-private", models=ForbiddenModels(), projects=[], recover_jobs=False)
        self.assertEqual(self.service.config()["projects"], [])
        self.assertIsNone(self.current()["session"])
        self.assertEqual(self.counts()["records"], 0)
        opened = self.open()
        self.assertEqual(opened["detail"]["record"]["projectId"], "")
        drafted = self.mutate("draft", opened, text="还没想成熟的无项目想法", requestedProfile="pro")
        original = self.image(drafted)
        selected = self.mutate("draft", drafted, text="还没想成熟的无项目想法", attachmentIds=[original], requestedProfile="pro")
        files = self.files_snapshot()
        self.service = WorkflowService(self.root / "first-install-private", models=ForbiddenModels(), recover_jobs=False)
        recovered = self.current()
        self.assertEqual(recovered["session"], selected["session"])
        saved = self.mutate("save", recovered, text=recovered["session"]["draft"]["text"], attachmentIds=[original])
        idea = saved["idea"]
        self.assertIsNone(idea["projectId"])
        self.assertEqual(idea["body"], "还没想成熟的无项目想法")
        self.assertEqual(idea["attachmentIds"], [original])
        self.assertEqual(idea["workflowRecordId"], opened["session"]["recordId"])
        cleared = self.mutate("clear", saved)
        self.assertNotEqual(cleared["session"]["id"], saved["session"]["id"])
        self.assertEqual(cleared["detail"]["record"]["projectId"], "")
        self.assertEqual(cleared["session"]["draft"], {"text": "", "attachmentIds": []})
        before_late = self.db_snapshot()
        self.error(lambda: self.mutate("draft", saved, text="旧页迟到草稿"), "dialogue_changed")
        self.assertEqual(self.db_snapshot(), before_late)
        found = workflow_get(self.service, "mobile/ideas", "projectId=unclassified&search=无项目")
        self.assertEqual(found["projects"], [])
        self.assertEqual([item["id"] for item in found["ideas"]], [idea["id"]])
        reopened = self.open(ideaId=idea["id"], expectedIdeaRevision=idea["revision"])
        self.assertEqual(reopened["session"]["recordId"], opened["session"]["recordId"])
        self.assertEqual([item["id"] for item in reopened["eligibleAttachments"]], [original])
        self.assertEqual(reopened["session"]["draft"], {"text": "", "attachmentIds": []})
        self.assertEqual(workflow_get(self.service, "mobile/idea", "id=" + idea["id"])["idea"], idea)
        before_work = self.db_snapshot()
        reviewed = self.service.app_work_review("recordId=" + reopened["session"]["recordId"] + "&ideaId=" + idea["id"] + "&revision=" + str(idea["revision"]))
        self.assertEqual(reviewed["ideaContext"]["ideaId"], idea["id"])
        self.assertEqual(self.service.config()["appWork"]["bindings"], [])
        self.assertEqual(self.db_snapshot(), before_work)
        self.error(lambda: self.service.app_work(request(recordId=reopened["session"]["recordId"],
            bindingId="no-grant", text="没有授权不能执行", sourceTask={"ideaId": idea["id"], "revision": idea["revision"]})))
        self.assertEqual(self.db_snapshot(), before_work)
        self.assertEqual(self.files_snapshot(), files)
        self.assertEqual(self.counts()["jobs"], 0)
        self.assertEqual(self.counts()["idea_dispatches"], 0)
        self.assertFalse(self.service._wake.is_set())
        with self.service._db() as db:
            self.assertEqual(self.service._setting(db, "projects"), [])
            self.assertIsNone(self.service._setting(db, "app_work_bindings"))
            self.assertIsNone(self.service._setting(db, "app_work_catalog"))

    def test_classification_split_and_merge_do_not_require_an_execution_directory(self):
        workspace = self.root / "management-project"
        workspace.mkdir()
        self.service = WorkflowService(self.root / "management-private", models=ForbiddenModels(), recover_jobs=False,
            projects=[{"id": "stale-project", "name": "Configured classification", "root": str(workspace), "capabilities": []}])
        saved = self.mutate("save", self.open(), text="原想法：物理方案与手动方案")
        idea = saved["idea"]
        with self.service._db() as db:
            projects_before = self.service._setting(db, "projects")
            record_before = dict(self.service._record(db, saved["session"]["recordId"]))
        workspace.rmdir()
        classified = self.post("idea/update", request(id=idea["id"], expectedRevision=idea["revision"], projectId="stale-project"))["idea"]
        self.assertEqual(classified["projectId"], "stale-project")
        split_body = request(id=classified["id"], expectedRevision=classified["revision"], start=0, end=3, title="分出的文字")
        split = self.post("idea/split", split_body)["idea"]
        self.assertEqual(split["body"], classified["body"][:3])
        self.assertEqual(split["projectId"], "stale-project")
        self.assertEqual(self.post("idea/split", split_body)["idea"]["id"], split["id"])
        combined = self.post("idea/merge", request(firstId=classified["id"], firstRevision=classified["revision"],
            secondId=split["id"], secondRevision=split["revision"], title="同分类合并"))["idea"]
        self.assertEqual(combined["body"], classified["body"] + "\n\n" + split["body"])
        self.assertEqual(combined["projectId"], "stale-project")
        before = self.db_snapshot()
        self.error(lambda: self.post("idea/update", request(id=classified["id"], expectedRevision=classified["revision"], projectId="unknown")))
        self.error(lambda: self.post("idea/update", request(id=classified["id"], expectedRevision=classified["revision"] + 1, projectId="stale-project")))
        self.assertEqual(self.db_snapshot(), before)
        with self.service._db() as db:
            self.assertEqual(self.service._setting(db, "projects"), projects_before)
            self.assertEqual(dict(self.service._record(db, saved["session"]["recordId"])), record_before)
            self.assertEqual(self.service._idea(db, classified["id"])["body"], classified["body"])
            self.assertEqual(self.error(lambda: self.service._project(db, "stale-project")).status, 503)
            self.assertIsNone(self.service._setting(db, "app_work_bindings"))
        self.assertFalse(workspace.exists())
        self.assertEqual(self.counts()["jobs"], 0)
        self.assertEqual(self.counts()["idea_dispatches"], 0)

    def test_notebook_save_and_clear_do_not_open_or_require_an_existing_project_directory(self):
        workspace = self.root / "previously-authorized-project"
        workspace.mkdir()
        self.service = WorkflowService(self.root / "missing-workspace-private", models=ForbiddenModels(), recover_jobs=False,
            projects=[{"id": "stale-project", "name": "Actual configured project", "root": str(workspace), "capabilities": []}])
        with self.service._db() as db:
            projects_before = self.service._setting(db, "projects")
        workspace.rmdir()
        saved = self.mutate("save", self.open(), text="目录失效仍须记住的念头")
        self.assertEqual(saved["detail"]["record"]["projectId"], "stale-project")
        self.assertIsNone(saved["idea"]["projectId"])
        self.mutate("clear", saved)
        self.assertEqual(workflow_get(self.service, "mobile/idea", "id=" + saved["idea"]["id"])["idea"]["body"], "目录失效仍须记住的念头")
        with self.service._db() as db:
            self.assertEqual(self.service._setting(db, "projects"), projects_before)
            self.error(lambda: self.service._project(db, "stale-project"))
        self.assertFalse(workspace.exists())
        self.assertEqual(self.counts()["jobs"], 0)
        self.assertEqual(self.counts()["idea_dispatches"], 0)
        sent = self.mutate("send", self.current(), text="目录失效不阻止普通文字讨论")
        with self.service._db() as db:
            payload = json.loads(db.execute("SELECT payload FROM jobs WHERE id=?", (sent["job"]["id"],)).fetchone()[0])
            self.assertEqual(self.service._setting(db, "projects"), projects_before)
        self.assertEqual(payload["projectId"], "stale-project")
        self.assertNotIn("actionPlanning", payload["appFrozen"])
        self.assertFalse(workspace.exists())

    def test_unclassified_text_chat_freezes_once_and_recovers_a_late_answer_only_to_its_original_source(self):
        self.service = WorkflowService(self.root / "unclassified-chat-private", models=ForbiddenModels(), projects=[], recover_jobs=False)
        saved = self.mutate("save", self.open(), text="没有项目的长期想法")
        state = saved["session"]
        body = request(clientId=self.client, sessionId=state["id"], expectedRevision=state["revision"],
            text="问题A：继续分析这个想法", attachmentIds=[], requestedProfile="fast")
        first = self.post("dialogue/send", body)
        duplicate = self.post("dialogue/send", body)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["job"]["id"], first["job"]["id"])
        with self.service._db() as db:
            payload = json.loads(db.execute("SELECT payload FROM jobs WHERE id=?", (first["job"]["id"],)).fetchone()[0])
        self.assertEqual(payload["projectId"], "")
        self.assertEqual(payload["appFrozen"]["projectName"], "未归类")
        self.assertNotIn("actionPlanning", payload["appFrozen"])
        self.assertEqual(payload["sourceTask"], {key: saved["idea"][key] for key in ("title", "body")} |
            {"ideaId": saved["idea"]["id"], "revision": saved["idea"]["revision"]})
        self.assertEqual(self.counts()["jobs"], 1)
        self.assertEqual(self.counts()["idea_dispatches"], 1)
        cleared = self.mutate("clear", first)
        second = self.mutate("send", cleared, text="问题B：新的临时讨论", requestedProfile="fast")
        response = self.answer(first, "回答A完整回到原无项目想法讨论")
        current = self.current()
        self.assertEqual(current["session"]["id"], second["session"]["id"])
        self.assertEqual([message["text"] for message in current["detail"]["messages"]], ["问题B：新的临时讨论"])
        original = self.service.detail(first["session"]["recordId"])
        self.assertEqual(original["messages"][-1]["id"], response["id"])
        self.assertEqual(original["sourceTask"]["ideaId"], saved["idea"]["id"])
        replay = self.post("dialogue/send", body)
        self.assertTrue(replay["duplicate"])
        self.assertFalse(replay["session"]["isCurrent"])
        self.assertEqual(replay["job"]["id"], first["job"]["id"])
        self.assertEqual(self.counts()["idea_dispatches"], 2)
        self.assertEqual(self.current()["session"]["id"], second["session"]["id"])
        self.error(lambda: self.mutate("remember", current, sourceMessageId=response["id"]), "answer_source_mismatch")
        self.assertFalse(self.service._wake.is_set())
        with self.service._db() as db:
            self.assertEqual(self.service._setting(db, "projects"), [])

    def test_no_project_freeze_rejects_project_references_and_non_mobile_or_work_callers(self):
        self.service = WorkflowService(self.root / "unclassified-scope-private", models=ForbiddenModels(), projects=[], recover_jobs=False)
        state = self.open()
        original = self.image(state)
        drafted = self.mutate("draft", state, text="有图不假称传给普通 Chat", attachmentIds=[original])
        before = self.db_snapshot()
        self.error(lambda: self.mutate("send", drafted, text="图像问题", attachmentIds=[original]), "app_images_unavailable")
        self.assertEqual(self.db_snapshot(), before)
        self.assertEqual(self.current()["session"]["draft"], drafted["session"]["draft"])
        with self.service._db() as db:
            record = self.service._record(db, state["session"]["recordId"])
            payload = {"context": {"attachmentIds": [], "selectedText": "", "referenceIds": ["private-ref"]},
                "purpose": "discussion", "appTarget": {"kind": "chatgpt", "mode": "new"},
                "mobileDialogue": {"recordId": record["id"]}}
            self.error(lambda: self.service._freeze_app_discussion(db, record, payload, None), "project_not_authorized")
            payload["context"]["referenceIds"] = []
            for mobile, purpose, target in [(None, "discussion", {"kind": "chatgpt", "mode": "new"}),
                    ({"recordId": "other-record"}, "discussion", {"kind": "chatgpt", "mode": "new"}),
                    ({"recordId": record["id"]}, "native_work", {"kind": "codex", "mode": "new"})]:
                self.error(lambda: self.service._freeze_app_discussion(db, record,
                    {**payload, "mobileDialogue": mobile, "purpose": purpose, "appTarget": target}, None), "project_not_authorized")
        self.assertEqual(self.db_snapshot(), before)
        self.assertEqual(self.counts()["jobs"], 0)
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

    def test_saved_originals_are_frozen_candidates_and_selection_survives_restart(self):
        state = self.open(); original = self.image(state)
        saved = self.mutate("save", state, text="有原图的想法", attachmentIds=[original])
        idea = saved["idea"]
        fields, files = self.upload_request(saved, "red")
        incidental = self.service.upload(request(recordId=idea["workflowRecordId"]), files)["uploadedAttachmentIds"][0]
        self.mutate("clear", saved)
        reopened = self.open(ideaId=idea["id"], expectedIdeaRevision=idea["revision"])
        self.assertEqual(reopened["session"]["eligibleAttachmentIds"], [original])
        self.assertEqual([image["id"] for image in reopened["eligibleAttachments"]], [original])
        self.assertEqual(reopened["session"]["draft"]["attachmentIds"], [])
        self.error(lambda: self.mutate("draft", reopened, attachmentIds=[incidental]), "image_source_mismatch")
        draft = self.mutate("draft", reopened, text="明确复用原图", attachmentIds=[original])
        self.service = WorkflowService(self.root / "private", models=ForbiddenModels(), recover_jobs=False)
        self.assertEqual(self.current()["session"]["draft"], draft["session"]["draft"])
        self.error(lambda: self.mutate("send", self.current(), text="明确复用原图", attachmentIds=[original]), "app_images_unavailable")
        self.assertEqual(self.counts()["idea_dispatches"], 0)

    def test_another_session_same_record_upload_is_not_eligible(self):
        saved = self.mutate("save", self.open(), text="相同想法独立讨论")
        original_session = saved["session"]["id"]
        other = self.open(ideaId=saved["idea"]["id"], expectedIdeaRevision=1)
        uploaded = self.image(other)
        reopened = self.open(ideaId=saved["idea"]["id"], expectedIdeaRevision=1)
        self.assertNotEqual(reopened["session"]["id"], original_session)
        self.assertEqual(reopened["session"]["recordId"], other["session"]["recordId"])
        self.assertEqual(reopened["eligibleAttachments"], [])
        self.error(lambda: self.mutate("draft", reopened, attachmentIds=[uploaded]), "image_source_mismatch")

    def test_source_revision_and_actual_original_bytes_are_checked_before_selection(self):
        state = self.open(); original = self.image(state)
        saved = self.mutate("save", state, text="原图底稿", attachmentIds=[original])
        linked = self.open(ideaId=saved["idea"]["id"], expectedIdeaRevision=1)
        self.post("idea/update", request(id=saved["idea"]["id"], expectedRevision=1, body="新版本"))
        self.error(lambda: self.mutate("draft", linked, attachmentIds=[original]), "revision_conflict")
        cleared = self.mutate("clear", linked)
        self.assertEqual(cleared["session"]["eligibleAttachmentIds"], [])
        reopened = self.open(ideaId=saved["idea"]["id"], expectedIdeaRevision=2)
        with self.service._db() as db:
            filename = db.execute("SELECT filename FROM attachments WHERE id=?", (original,)).fetchone()[0]
        path = self.service.attachments_dir / filename
        data = bytearray(path.read_bytes()); data[-1] ^= 1; path.write_bytes(data)
        self.error(lambda: self.mutate("draft", reopened, attachmentIds=[original]), "image_source_mismatch")
        self.assertEqual(self.current()["session"]["draft"]["attachmentIds"], [])

    def test_upload_nonce_and_old_session_replay_never_retargets_or_changes_draft(self):
        first = self.mutate("draft", self.open(), text="保留的输入")
        fields, files = self.upload_request(first)
        uploaded = self.service.mobile_dialogue_upload(fields, files)
        self.assertEqual(uploaded["session"]["draft"], first["session"]["draft"])
        self.assertEqual(uploaded["session"]["revision"], first["session"]["revision"] + 1)
        second = self.mutate("clear", uploaded)
        before = self.db_snapshot(), self.files_snapshot()
        replay = self.service.mobile_dialogue_upload(fields, files)
        self.assertTrue(replay["duplicate"])
        self.assertFalse(replay["session"]["isCurrent"])
        self.assertEqual(replay["uploadedAttachmentIds"], uploaded["uploadedAttachmentIds"])
        self.assertEqual(self.current()["session"]["id"], second["session"]["id"])
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)
        _changed_fields, changed_files = self.upload_request(second, "red")
        self.error(lambda: self.service.mobile_dialogue_upload(fields, changed_files))
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)

    def test_upload_revocation_and_partial_failure_leave_no_orphan_files_or_rows(self):
        state = self.open(); fields, files = self.upload_request(state)
        before = self.db_snapshot(), self.files_snapshot()
        calls = []
        def revoked():
            calls.append(1)
            if len(calls) == 2:
                raise WorkflowError("Revoked", 403)
        self.error(lambda: self.service.mobile_dialogue_upload(fields, files, authorize=revoked))
        self.assertEqual(len(calls), 2)
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)
        with patch.object(self.service, "_mobile_install_image", wraps=self.service._mobile_install_image) as install:
            def fail_after_install(*args):
                install._mock_wraps(*args)
                raise WorkflowError("Isolated failure after actual file creation")
            install.side_effect = fail_after_install
            self.error(lambda: self.service.mobile_dialogue_upload(fields, files))
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)

    def test_upload_invalid_content_and_preview_collision_preserve_all_prior_files(self):
        state = self.open(); fields, files = self.upload_request(state)
        invalid = self.root / "invalid.png"
        invalid.write_bytes(b"not an image")
        before = self.db_snapshot(), self.files_snapshot()
        self.error(lambda: self.service.mobile_dialogue_upload(fields, [
            IncomingFile(invalid, 0, invalid.stat().st_size, "invalid.png", "image/png")]))
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)
        ghost = uuid.uuid4().hex
        preview = self.service.attachments_dir / (ghost + ".preview.jpg")
        preview.write_bytes(b"prior unregistered preview")
        before = self.db_snapshot(), self.files_snapshot()
        with patch("workflow_mobile_dialogue.uuid.uuid4", return_value=uuid.UUID(ghost)):
            self.error(lambda: self.service.mobile_dialogue_upload(fields, files), "image_source_mismatch")
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)

    def test_selected_actual_image_total_limit_is_atomic_for_saved_originals(self):
        state = self.open(); first = self.image(state); second = self.image(state)
        with self.service._db() as db:
            limit = self.service._mobile_image_row(db, state["session"]["recordId"], first)["size"]
        saved = self.mutate("save", state, text="明确保存两张", attachmentIds=[first, second])
        linked = self.open(ideaId=saved["idea"]["id"], expectedIdeaRevision=1)
        before = self.db_snapshot(), self.files_snapshot()
        with patch("workflow_service.MAX_UPLOAD", limit):
            error = self.error(lambda: self.mutate("draft", linked, attachmentIds=[first, second]))
        self.assertEqual(error.status, 413)
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)

    def test_saving_originals_across_rounds_stops_at_four_and_preserves_fifth_draft(self):
        state, saved_ids = self.open(), []
        for index in range(4):
            identifier = self.image(state)
            saved_ids.append(identifier)
            state = self.mutate("save", state, text="第" + str(index + 1) + "轮原图", attachmentIds=[identifier])
        self.assertEqual(state["idea"]["attachmentIds"], saved_ids)
        fifth = self.image(state)
        drafted = self.mutate("draft", state, text="第五张需要保留的草稿", attachmentIds=[fifth])
        before = self.db_snapshot(), self.files_snapshot()
        error = self.error(lambda: self.mutate("save", drafted, text="第五张需要保留的草稿", attachmentIds=[fifth]), "idea_images_limit")
        self.assertEqual(error.status, 413)
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)
        self.assertEqual(self.current()["session"]["draft"], drafted["session"]["draft"])
        idea = workflow_get(self.service, "mobile/idea", "id=" + state["idea"]["id"])["idea"]
        self.assertEqual((idea["body"], idea["revision"], idea["attachmentIds"]),
            (state["idea"]["body"], state["idea"]["revision"], saved_ids))

    def test_saving_cumulative_original_bytes_checks_more_than_this_round_selection(self):
        state = self.open(); first = self.image(state)
        saved = self.mutate("save", state, text="已经保存第一张", attachmentIds=[first])
        second = self.image(saved)
        drafted = self.mutate("draft", saved, text="第二张草稿", attachmentIds=[second])
        with self.service._db() as db:
            limit = max(self.service._mobile_image_row(db, drafted["session"]["recordId"], identifier)["size"] for identifier in (first, second))
        before = self.db_snapshot(), self.files_snapshot()
        with patch("workflow_service.MAX_UPLOAD", limit):
            error = self.error(lambda: self.mutate("save", drafted, text="第二张草稿", attachmentIds=[second]), "idea_images_limit")
        self.assertEqual(error.status, 413)
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)
        self.assertEqual(self.current()["session"]["draft"]["attachmentIds"], [second])

    def test_mobile_image_portable_limit_is_actual_eight_mib_but_legacy_upload_stays_twelve(self):
        state = self.open(); fields, files = self.upload_request(state)
        spool = files[0].spool
        with spool.open("r+b") as stream:
            stream.truncate(MOBILE_IMAGE_BYTES)
        exact = IncomingFile(spool, 0, MOBILE_IMAGE_BYTES, "exact.png", "image/png")
        accepted = self.service.mobile_dialogue_upload(fields, [exact])
        self.assertEqual(accepted["detail"]["attachments"][0]["size"], MOBILE_IMAGE_BYTES)
        saved = self.mutate("save", accepted, text="边界原图", attachmentIds=accepted["uploadedAttachmentIds"])
        with spool.open("r+b") as stream:
            stream.truncate(MOBILE_IMAGE_BYTES + 1)
        over = IncomingFile(spool, 0, MOBILE_IMAGE_BYTES + 1, "legacy.png", "image/png")
        next_fields, _files = self.upload_request(saved)
        before = self.db_snapshot(), self.files_snapshot()
        error = self.error(lambda: self.service.mobile_dialogue_upload(next_fields, [over]), "idea_image_size_limit")
        self.assertEqual(error.status, 413)
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)
        legacy = self.service.upload(request(recordId=saved["session"]["recordId"]), [over])
        identifier = legacy["uploadedAttachmentIds"][0]
        self.assertEqual(next(image["size"] for image in legacy["attachments"] if image["id"] == identifier), MOBILE_IMAGE_BYTES + 1)
        # Existing oversized metadata remains intact and readable; selecting it
        # for a new mobile save is rejected, never resized or silently dropped.
        with self.service._db() as db:
            meta = self.service._mobile_metadata(db, saved["idea"]["id"])
            meta["attachmentIds"].append(identifier)
            self.service._set_setting(db, "mobile-idea:" + saved["idea"]["id"], meta)
        linked = self.open(ideaId=saved["idea"]["id"], expectedIdeaRevision=1)
        draft = self.mutate("draft", linked, text="旧大图要保留", attachmentIds=[identifier])
        before = self.db_snapshot(), self.files_snapshot()
        self.error(lambda: self.mutate("save", draft, text="旧大图要保留", attachmentIds=[identifier]), "idea_image_size_limit")
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)
        self.assertEqual(self.current()["session"]["draft"], draft["session"]["draft"])
        self.assertEqual(workflow_get(self.service, "mobile/idea", "id=" + saved["idea"]["id"])["idea"]["attachmentIds"], meta["attachmentIds"])

    def test_upload_and_management_uuid_collision_preserve_existing_bytes(self):
        state = self.open(); existing = self.image(state)
        before = self.db_snapshot(), self.files_snapshot()
        fields, files = self.upload_request(state, "red")
        with patch("workflow_mobile_dialogue.uuid.uuid4", return_value=uuid.UUID(existing)):
            self.error(lambda: self.service.mobile_dialogue_upload(fields, files), "image_source_mismatch")
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)
        ghost = uuid.uuid4().hex
        path = self.service.attachments_dir / (ghost + ".png")
        path.write_bytes(b"existing unregistered file")
        before = self.db_snapshot(), self.files_snapshot()
        with patch("workflow_mobile_dialogue.uuid.uuid4", return_value=uuid.UUID(ghost)):
            self.error(lambda: self.service.mobile_dialogue_upload(fields, files), "image_source_mismatch")
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)

    def test_upload_strict_source_and_file_fields_never_become_execution(self):
        state = self.open(); fields, files = self.upload_request(state)
        before = self.db_snapshot(), self.files_snapshot()
        for extra in ("dispatch", "appTarget", "role"):
            self.error(lambda: self.service.mobile_dialogue_upload({**fields, extra: True}, files))
        self.error(lambda: self.service.mobile_dialogue_upload({**fields,
            "text": fields["text"][:-1] + ',"dispatch":true}'}, files))
        self.error(lambda: self.service.mobile_dialogue_upload({**fields,
            "text": fields["text"][:-1] + ',"clientId":"' + self.client + '"}'}, files))
        for identifiers in ([{}], [files[0].name], [True]):
            self.error(lambda: self.mutate("draft", state, attachmentIds=identifiers))
        audio = IncomingFile(files[0].spool, 0, files[0].size, "test.mp3", "audio/mpeg")
        self.error(lambda: self.service.mobile_dialogue_upload(fields, [audio]))
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)

    def test_split_unicode_exact_subset_preserves_source_and_full_snapshot(self):
        source = self.save_idea("A😀B\n第二段")
        point = {"id": uuid.uuid4().hex, "text": "原要点", "kind": "decision"}
        source = self.post("idea/update", request(id=source["id"], expectedRevision=1, keyPoints=[point],
            executionDraft="原执行稿", projectId="console"))["idea"]
        body = request(id=source["id"], expectedRevision=source["revision"], start=1, end=2, title="提取原表情")
        split = self.post("idea/split", body)
        idea = split["idea"]
        self.assertEqual(idea["body"], "😀")
        self.assertEqual((idea["keyPoints"], idea["executionDraft"], idea["attachmentIds"]), ([], "", []))
        self.assertEqual(idea["projectId"], "console")
        self.assertNotEqual(idea["workflowRecordId"], source["workflowRecordId"])
        self.assertEqual(workflow_get(self.service, "mobile/idea", "id=" + source["id"])["idea"], source)
        provenance = idea["provenance"][0]
        self.assertEqual(provenance["selection"], {"start": 1, "end": 2, "unit": "unicode_codepoints"})
        self.assertFalse(provenance["authorityVerified"])
        with self.service._db() as db:
            frozen = self.service._setting(db, "mobile-idea-op-source:" + idea["id"])["sources"][0]
        self.assertEqual((frozen["body"], frozen["metadata"]["executionDraft"], frozen["metadata"]["keyPoints"]),
            (source["body"], source["executionDraft"], source["keyPoints"]))
        self.assertEqual(frozen["sourceBodySha256"], hashlib.sha256(source["body"].encode()).hexdigest())
        self.assertEqual(self.counts()["idea_dispatches"], 0)

    def test_management_nonce_precedes_source_version_but_returns_current_destination(self):
        source = self.save_idea("原正文")
        body = request(id=source["id"], expectedRevision=1, start=0, end=1, title="新条")
        first = self.post("idea/split", body)
        self.post("idea/update", request(id=source["id"], expectedRevision=1, body="来源后来修改"))
        edited = self.post("idea/update", request(id=first["idea"]["id"], expectedRevision=1, body="新条后来修改"))["idea"]
        before = self.db_snapshot(), self.files_snapshot()
        replay = self.post("idea/split", body)
        self.assertTrue(replay["duplicate"])
        self.assertEqual(replay["idea"], edited)
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)
        self.error(lambda: self.post("idea/split", {**body, "title": "另一个标题"}))
        self.error(lambda: self.post("idea/split", {**body, "requestId": str(uuid.uuid4())}), "revision_conflict")
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)

    def test_merge_third_idea_deterministic_fields_points_and_sources(self):
        first, second = self.save_idea("第一份"), self.save_idea("第二份")
        identical = "同文字不同决定程度"
        first = self.post("idea/update", request(id=first["id"], expectedRevision=1, executionDraft=" 第一稿 ", projectId="console",
            keyPoints=[{"id": uuid.uuid4().hex, "text": identical, "kind": "suggestion"},
                {"id": uuid.uuid4().hex, "text": identical, "kind": "decision"}]))["idea"]
        second = self.post("idea/update", request(id=second["id"], expectedRevision=1, executionDraft="第二稿",
            keyPoints=[{"id": uuid.uuid4().hex, "text": identical, "kind": "suggestion"}]))["idea"]
        body = request(firstId=first["id"], firstRevision=2, secondId=second["id"], secondRevision=2, title="合并第三份")
        merged = self.post("idea/merge", body)["idea"]
        self.assertNotIn(merged["id"], [first["id"], second["id"]])
        self.assertEqual(merged["body"], "第一份\n\n第二份")
        self.assertEqual(merged["executionDraft"], " 第一稿 \n\n第二稿")
        self.assertIsNone(merged["projectId"])
        self.assertEqual([(point["text"], point["kind"]) for point in merged["keyPoints"]],
            [(identical, "suggestion"), (identical, "decision")])
        self.assertEqual(len(merged["keyPoints"][0]["sources"]), 2)
        self.assertEqual(merged["keyPoints"][0]["source"]["sourceIdeaId"], first["id"])
        self.assertEqual(merged["attachmentIds"], [])
        for source in (first, second):
            self.assertEqual(workflow_get(self.service, "mobile/idea", "id=" + source["id"])["idea"], source)
        self.assertEqual((self.counts()["jobs"], self.counts()["idea_dispatches"]), (0, 0))
        self.post("idea/update", request(id=second["id"], expectedRevision=2, body="来源后来变化"))
        before = self.db_snapshot(), self.files_snapshot()
        replay = self.post("idea/merge", body)
        self.assertTrue(replay["duplicate"])
        self.assertEqual(replay["idea"], merged)
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)

    def test_management_explicit_original_images_copy_exact_bytes_and_ownership(self):
        state = self.open(); original = self.image(state)
        saved = self.mutate("save", state, text="原图正文", attachmentIds=[original])
        source = saved["idea"]
        no_images = self.post("idea/split", request(id=source["id"], expectedRevision=1, start=0, end=2, title="不带图"))
        self.assertEqual(no_images["idea"]["imageCount"], 0)
        split = self.post("idea/split", request(id=source["id"], expectedRevision=1, start=0, end=2, title="明确复制图", attachmentIds=[original]))
        copy = split["idea"]["attachmentIds"][0]
        self.assertNotEqual(copy, original)
        with self.service._db() as db:
            original_row = self.service._mobile_image_row(db, source["workflowRecordId"], original)
            copy_row = self.service._mobile_image_row(db, split["idea"]["workflowRecordId"], copy)
            self.assertEqual(self.service._mobile_image_proof(original_row), self.service._mobile_image_proof(copy_row))
        before = self.db_snapshot(), self.files_snapshot()
        self.error(lambda: self.post("idea/split", request(id=source["id"], expectedRevision=1, start=0, end=1,
            title="不能串原图", attachmentIds=[copy])), "image_source_mismatch")
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)
        self.mutate("clear", saved)
        reopened = self.open(ideaId=split["idea"]["id"], expectedIdeaRevision=1)
        self.assertEqual(reopened["session"]["eligibleAttachmentIds"], [copy])
        self.assertEqual(reopened["session"]["draft"]["attachmentIds"], [])

    def test_management_selected_images_revocation_cleans_only_new_copies(self):
        state = self.open(); original = self.image(state)
        source = self.mutate("save", state, text="原图和正文", attachmentIds=[original])["idea"]
        before = self.db_snapshot(), self.files_snapshot()
        calls = []
        def revoked():
            calls.append(1)
            if len(calls) == 2:
                raise WorkflowError("Revoked", 403)
        self.error(lambda: self.service.mobile_idea_split(request(id=source["id"], expectedRevision=1,
            start=0, end=2, title="保留原图", attachmentIds=[original]), authorize=revoked))
        self.assertEqual(len(calls), 2)
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)

    def test_management_limits_auth_revocation_and_source_conflicts_are_atomic(self):
        first, second = self.save_idea("a" * 11000), self.save_idea("b" * 10000)
        before = self.db_snapshot(), self.files_snapshot()
        self.error(lambda: self.post("idea/merge", request(firstId=first["id"], firstRevision=1,
            secondId=second["id"], secondRevision=1, title="不截断")))
        for fields in ({"title": "x" * 81}, {"start": True}, {"end": 12000}, {"dispatch": True}, {"attachmentIds": [{}]}):
            invalid = {**request(id=first["id"], expectedRevision=1, start=0, end=1, title="严格范围"), **fields}
            self.error(lambda: self.post("idea/split", invalid))
        self.error(lambda: self.post("idea/merge", request(firstId=first["id"], firstRevision=1,
            secondId=first["id"], secondRevision=1, title="不能同源两遍")))
        calls = []
        def revoked():
            calls.append(1)
            if len(calls) == 2:
                raise WorkflowError("Revoked", 403)
        self.error(lambda: self.service.mobile_idea_split(request(id=first["id"], expectedRevision=1,
            start=0, end=1, title="撤销前确认"), authorize=revoked))
        self.assertEqual(len(calls), 2)
        self.assertEqual((self.db_snapshot(), self.files_snapshot()), before)

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

    def test_saved_long_answer_and_maximum_unicode_point_can_merge_and_review_work_in_full(self):
        text = "已完成回答" * 501
        sent = self.mutate("send", self.open())
        answer = self.answer(sent, text)
        remembered = self.mutate("remember", self.current(), sourceMessageId=answer["id"])
        self.assertTrue(remembered["keyPointAdded"])
        idea = remembered["idea"]
        other = self.save_idea("另一份保持不变的正文")
        merged = self.post("idea/merge", request(firstId=idea["id"], firstRevision=idea["revision"],
            secondId=other["id"], secondRevision=other["revision"], title="完整长回答合并"))["idea"]
        self.assertEqual(merged["keyPoints"][0]["text"], text)
        self.assertEqual(merged["body"], text + "\n\n" + other["body"])
        self.assertEqual(merged["keyPoints"][0]["kind"], "suggestion")
        long_point = "😀" * 20000
        changed = self.post("idea/update", request(id=merged["id"], expectedRevision=merged["revision"],
            executionDraft="真正交付前的保存稿", keyPoints=[{"id": merged["keyPoints"][0]["id"],
                "text": long_point, "kind": "suggestion"}]))["idea"]
        reviewed = workflow_get(self.service, "app-work-review", "recordId=" + changed["workflowRecordId"]
            + "&ideaId=" + changed["id"] + "&revision=" + str(changed["revision"]))
        self.assertEqual(reviewed["ideaContext"]["keyPoints"][0]["text"], long_point)
        self.assertEqual(reviewed["ideaContext"]["savedExecutionDraft"]["text"], changed["executionDraft"])
        second_merge = self.post("idea/merge", request(firstId=changed["id"], firstRevision=changed["revision"],
            secondId=other["id"], secondRevision=other["revision"], title="Unicode要点完整保留"))["idea"]
        self.assertEqual(second_merge["keyPoints"][0]["text"], long_point)
        before = self.db_snapshot()
        self.error(lambda: self.post("idea/update", request(id=changed["id"], expectedRevision=changed["revision"],
            keyPoints=[{"id": changed["keyPoints"][0]["id"], "text": long_point + "😀", "kind": "suggestion"}])))
        self.assertEqual(self.db_snapshot(), before)
        self.assertEqual(self.counts()["idea_dispatches"], 1, "saving, merging and reviewing never dispatches another request")

    def test_remember_at_one_hundred_points_keeps_full_answer_origin_and_persistent_omission_receipt(self):
        saved = self.mutate("save", self.open(), text="原想法")
        points = [{"id": uuid.uuid4().hex, "text": "完整要点" + str(index),
            "kind": "decision" if index == 0 else "suggestion"} for index in range(100)]
        idea = self.post("idea/update", request(id=saved["idea"]["id"], expectedRevision=saved["idea"]["revision"],
            keyPoints=points))["idea"]
        state = self.open(ideaId=idea["id"], expectedIdeaRevision=idea["revision"])
        sent = self.mutate("send", state, text="这一条明确确认的讨论")
        text = "新的完整回答与来源仍需保存" * 180
        answer = self.answer(sent, text)
        session = self.current()["session"]
        body = request(clientId=self.client, sessionId=session["id"], expectedRevision=session["revision"],
            sourceMessageId=answer["id"], ideaId=idea["id"], expectedIdeaRevision=idea["revision"])
        first = self.post("dialogue/remember", body)
        duplicate = self.post("dialogue/remember", body)
        for result in (first, duplicate):
            self.assertFalse(result["keyPointAdded"])
            self.assertEqual(result["keyPointOmittedReason"], "point_limit")
            self.assertEqual(result["idea"]["body"], idea["body"] + "\n\n" + text)
            self.assertEqual([{key: point[key] for key in ("id", "text", "kind")} for point in result["idea"]["keyPoints"]], points)
            self.assertEqual(result["idea"]["provenance"][-1]["sourceMessageId"], answer["id"])
            self.assertEqual(result["idea"]["provenance"][-1]["sourceJobId"], sent["job"]["id"])
        self.assertTrue(duplicate["duplicate"])
        review = workflow_get(self.service, "app-work-review", "recordId=" + idea["workflowRecordId"]
            + "&ideaId=" + idea["id"] + "&revision=" + str(first["idea"]["revision"]))
        self.assertEqual(review["ideaContext"]["keyPoints"], points)
        with self.service._db() as db:
            receipt = json.loads(db.execute("SELECT response FROM requests WHERE id=?", (body["requestId"],)).fetchone()[0])
        self.assertFalse(receipt["keyPointAdded"])
        self.assertEqual(receipt["keyPointOmittedReason"], "point_limit")

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
