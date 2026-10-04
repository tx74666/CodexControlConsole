"""Disposable checks for completed ChatGPT capture import; never opens or sends a chat."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_service import WorkflowError, WorkflowService


def request(**fields):
    return {"requestId": str(uuid.uuid4()), **fields}


class NoModels:
    def config(self):
        return {"ready": False, "selected": "", "providers": []}

    def discuss(self, *_):
        raise AssertionError("Capture import must never send to a model")


class ChatCaptureChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="console-chat-capture-check-")
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.private = self.root / "private"
        self.service = WorkflowService(self.private, models=NoModels(), projects=[
            {"id": "console", "name": "Isolated project", "root": str(self.project),
             "capabilities": ["result_import"], "allowGeneratedScripts": False}])
        self.idea = self.service.incubator_create(request(title="Original task", body="Preserve original draft"))["idea"]
        self.record = self.service.task_record(request(ideaId=self.idea["id"], expectedRevision=self.idea["revision"]))["record"]["id"]
        old = self.service.discuss(request(recordId=self.record, text="Earlier authorized Codex discussion",
            sourceTask=self.task(), context={"attachmentIds": []}, appTarget={"kind": "codex", "mode": "new"}))
        claimed = self.service.incubator_claim(request(id=old["job"]["appDispatch"]["id"]))["dispatch"]
        self.service.incubator_attach_result(request(id=claimed["id"], claimToken=claimed["claimToken"],
            targetThreadId=str(uuid.uuid4()), status="completed",
            result={"text": "Earlier Codex answer", "turnId": "old-turn", "sourceMessageId": "old-user"}))
        self.source_thread, self.source_user, self.source_agent = (str(uuid.uuid4()) for _ in range(3))
        self.source_data = {"schemaVersion": 1, "untrustedDataNotice": "Fixture data only.",
            "thread": {"id": self.source_thread, "kind": "chatgpt", "title": "Greeting", "preview": "你好，世界！",
                "status": {"type": "idle"}, "cwd": None, "createdAt": time.time() - 40, "updatedAt": time.time() - 10},
            "page": {"order": "newest_first", "limit": 1, "nextCursor": None, "hasMore": False},
            "turns": [{"id": self.source_user, "status": "completed", "error": None,
                "startedAt": time.time() - 30, "completedAt": time.time() - 20, "durationMs": None,
                "items": [{"type": "userMessage", "id": self.source_user, "content": [{"type": "text", "text": "你好"}]},
                    {"type": "agentMessage", "id": self.source_agent, "text": "你好，世界！"}]}], "attachments": []}

    def tearDown(self):
        self.service.shutdown()
        self.temporary.cleanup()

    def task(self):
        return {"ideaId": self.idea["id"], "revision": self.idea["revision"]}

    def body(self, data=None):
        return request(recordId=self.record, text="你好", sourceTask=self.task(), observedAt=datetime.now(timezone.utc).isoformat(),
            authorization={"origin": "current_human_chat", "description": "Human explicitly authorized this greeting and its return."},
            source={"content": [{"type": "text", "text": json.dumps(data or self.source_data, ensure_ascii=False)}], "isError": False})

    def rows(self, table):
        with self.service._db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM " + table + " ORDER BY rowid")]

    def assert_rejected(self, body, code=None):
        before = {table: self.rows(table) for table in ("ideas", "records", "jobs", "messages", "idea_dispatches", "requests")}
        with self.assertRaises(WorkflowError) as caught:
            self.service.import_chat_capture(body)
        if code:
            self.assertEqual(caught.exception.code, code)
        for table, rows in before.items():
            self.assertEqual(self.rows(table), rows, table)

    def test_import_returns_to_original_output_without_dispatch_or_draft_change(self):
        before = {table: self.rows(table) for table in ("ideas", "jobs", "idea_dispatches")}
        body = self.body()
        imported = self.service.import_chat_capture(body)
        job, capture = imported["job"], imported["job"]["chatCapture"]
        self.assertFalse(imported["duplicate"])
        self.assertEqual((job["kind"], job["status"], job["attempt"]), ("discuss", "succeeded", 0))
        self.assertNotIn("appDispatch", job)
        self.assertNotIn("dispatchId", job["result"])
        self.assertEqual(capture["sourceType"], "chatgpt_browser_capture")
        self.assertEqual(capture["evidenceSource"], "read_thread")
        self.assertEqual(capture["sourceUrl"], "https://chatgpt.com/c/" + self.source_thread)
        self.assertEqual(capture["turnId"], self.source_user)
        self.assertEqual(capture["sourceMessageId"], self.source_user)
        self.assertEqual(capture["agentMessageId"], self.source_agent)
        self.assertEqual(job["sourceTask"]["body"], "Preserve original draft")
        detail = self.service.detail(self.record)
        message = next(item for item in detail["messages"] if item["id"] == job["resultMessageId"])
        self.assertEqual((message["role"], message["text"]), ("assistant", "你好，世界！"))
        self.assertEqual(message["text"], job["result"]["text"])
        for key in ("sourceType", "evidenceSource", "targetThreadId", "sourceUrl", "turnId", "sourceMessageId", "agentMessageId", "sourceSha256"):
            self.assertEqual(capture[key], job["result"][key])
        self.assertEqual(self.rows("ideas"), before["ideas"])
        self.assertEqual(self.rows("idea_dispatches"), before["idea_dispatches"])
        self.assertEqual(self.rows("jobs")[:-1], before["jobs"])
        saved = json.loads(self.rows("jobs")[-1]["payload"])
        self.assertEqual(saved["readThreadSource"], body["source"])
        self.assertEqual(saved["authorization"], body["authorization"])
        self.assertNotIn("userConfirmedAt", saved)
        self.assertFalse(self.service._wake.is_set())
        self.assertIsNone(self.service._thread)
        self.assertFalse(self.service.has_pending_jobs())

    def test_repeat_request_and_same_actual_message_are_idempotent(self):
        body = self.body()
        first = self.service.import_chat_capture(body)
        second = self.service.import_chat_capture(body)
        third = self.service.import_chat_capture({**body, "requestId": str(uuid.uuid4())})
        self.assertTrue(second["duplicate"])
        self.assertTrue(third["duplicate"])
        self.assertEqual(first["job"]["id"], third["job"]["id"])
        self.assertEqual(len(self.rows("jobs")), 2)
        changed = copy.deepcopy(self.source_data)
        changed["turns"][0]["items"][1]["text"] = "Changed same-source answer"
        self.assert_rejected(self.body(changed), "chat_capture_conflict")
        self.assert_rejected({**body, "observedAt": datetime.now(timezone.utc).isoformat()})

    def test_same_source_cannot_be_moved_to_another_task(self):
        self.service.import_chat_capture(self.body())
        other = self.service.incubator_create(request(title="Other task", body="Other draft"))["idea"]
        record = self.service.task_record(request(ideaId=other["id"], expectedRevision=other["revision"]))["record"]["id"]
        body = self.body()
        body.update(recordId=record, sourceTask={"ideaId": other["id"], "revision": other["revision"]})
        self.assert_rejected(body, "chat_capture_conflict")

    def test_other_authorized_plain_text_with_independent_turn_id_imports(self):
        data = copy.deepcopy(self.source_data)
        data["page"]["limit"] = 3
        data["turns"][0]["id"] = str(uuid.uuid4())
        data["turns"][0]["items"][0]["content"][0]["text"] = "请问今天怎么样？"
        body = self.body(data)
        body["text"] = "请问今天怎么样？"
        job = self.service.import_chat_capture(body)["job"]
        self.assertEqual(job["instruction"], body["text"])
        self.assertNotEqual(job["result"]["turnId"], job["result"]["sourceMessageId"])
        self.assert_rejected({**body, "requestId": str(uuid.uuid4()), "text": "未经本轮发送的另一句话"}, "chat_capture_invalid")

    def test_invalid_incomplete_truncated_or_wrong_greeting_receipts_roll_back(self):
        changes = [lambda d: d["thread"].update(kind="codex"), lambda d: d["page"].update(hasMore=True),
            lambda d: d["page"].update(nextCursor="older"), lambda d: d["turns"][0].update(status="inProgress"),
            lambda d: d["turns"][0].update(truncated=True),
            lambda d: d["turns"][0]["items"][0].update(content=[{"type": "text", "text": "Other question"}]),
            lambda d: d["turns"][0]["items"].append(copy.deepcopy(d["turns"][0]["items"][1])),
            lambda d: d["turns"][0]["items"][1].update(id="fake-agent"),
            lambda d: d["turns"][0]["items"][1].update(text=""), lambda d: d.update(attachments=[{"id": "unselected"}])]
        for change in changes:
            with self.subTest(change=change):
                data = copy.deepcopy(self.source_data)
                change(data)
                self.assert_rejected(self.body(data))
        body = self.body()
        body["source"]["isError"] = True
        self.assert_rejected(body)
        body = self.body()
        body["sourceTask"]["revision"] += 1
        self.assert_rejected(body, "revision_conflict")
        body = self.body()
        body["authorization"]["origin"] = "old_dispatch"
        self.assert_rejected(body)

    def test_import_cannot_be_retried_even_if_its_status_is_altered(self):
        job = self.service.import_chat_capture(self.body())["job"]
        for status in ("succeeded", "failed", "waiting", "interrupted"):
            with self.service._db() as db:
                db.execute("UPDATE jobs SET status=? WHERE id=?", (status, job["id"]))
            with self.assertRaises(WorkflowError) as caught:
                self.service.retry(request(jobId=job["id"]))
            self.assertEqual(caught.exception.code, "chat_capture_not_retryable")
        self.assertEqual(len(self.rows("jobs")), 2)
        self.assertFalse(self.service._wake.is_set())

    def test_private_cli_import_preserves_existing_dispatches(self):
        before = self.rows("idea_dispatches")
        operation = [sys.executable, str(Path(__file__).with_name("incubator-dispatch.py")),
            "--data-dir", str(self.private), "import-chat-capture"]
        completed = subprocess.run(operation, input=json.dumps(self.body(), ensure_ascii=False),
            encoding="utf-8", capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["job"]["chatCapture"]["targetThreadId"], self.source_thread)
        self.assertEqual(self.rows("idea_dispatches"), before)


if __name__ == "__main__":
    unittest.main()
