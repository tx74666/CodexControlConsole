"""Disposable incubator persistence, concurrency and authenticated phone checks.

Uses one temporary workflow SQLite database; no model, chat or installed server.
"""
import http.client
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from document_library import DocumentLibraryService
import phone_companion as phone
from workflow_http import workflow_get, workflow_post
from workflow_service import WorkflowError, WorkflowService


def request(**fields):
    return {"requestId": str(uuid.uuid4()), **fields}


class IncubatorChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="console-incubator-check-")
        self.root = Path(self.temp.name)
        self.data = self.root / "private"
        self.service = WorkflowService(self.data)

    def tearDown(self):
        self.temp.cleanup()

    def create(self, **fields):
        return self.service.incubator_create(request(**fields))["idea"]

    def update(self, idea, **fields):
        return self.service.incubator_update(request(id=idea["id"], expectedRevision=idea["revision"], **fields))["idea"]

    def error(self, action, status=400, code=None):
        with self.assertRaises(WorkflowError) as caught:
            action()
        self.assertEqual(caught.exception.status, status)
        if code:
            self.assertEqual(caught.exception.code, code)

    def snapshot(self):
        with self.service._db() as db:
            return {table: [tuple(row) for row in db.execute("SELECT * FROM " + table + " ORDER BY id")]
                    for table in ("records", "messages", "attachments", "jobs")}

    def test_defaults_restart_shared_database_and_no_dispatch(self):
        with patch.object(self.service, "_enqueue", side_effect=AssertionError("Saving is not execution")):
            idea = self.create(title=" 一个模糊想法 ", body="先保存\n再深化")
            for stage in ("thinking", "ready", "queued", "published"):
                idea = self.update(idea, stage=stage)
        self.assertEqual(idea["title"], "一个模糊想法")
        self.assertEqual((idea["priority"], idea["parentId"], idea["targetKind"]), ("normal", None, "none"))
        self.assertEqual(idea["revision"], 5)
        self.assertFalse(self.service.has_pending_jobs())
        self.assertEqual(self.snapshot(), {name: [] for name in ("records", "messages", "attachments", "jobs")})
        restarted = WorkflowService(self.data)
        self.assertEqual(restarted.incubator_list()["ideas"], [idea])
        self.assertEqual([item.name for item in self.data.glob("*.sqlite*")], ["workflow.sqlite3"])

    def test_legacy_records_messages_and_jobs_are_preserved(self):
        self.service.configure_projects([{ "id": "console", "name": "Fixture", "root": str(self.root),
            "capabilities": ["capture_screen"], "allowGeneratedScripts": False}])
        record = self.service.create(request(projectId="console", title="Existing", text="Existing message"))["record"]
        self.service.submit(request(recordId=record["id"], text="Existing queued job", action="capture_screen"))
        before = self.snapshot()
        idea = self.create(title="Independent idea")
        self.update(idea, priority="high", stage="ready")
        self.assertEqual(self.snapshot(), before)

    def test_update_conflict_does_not_overwrite_other_endpoint(self):
        idea = self.create(title="Original")
        edited = self.update(idea, body="Computer edit", priority="high")
        before = self.service.incubator_list()
        self.error(lambda: self.update(idea, body="Stale phone edit"), 409, "revision_conflict")
        self.assertEqual(self.service.incubator_list(), before)
        merged = self.update(edited, body="Manually merged")
        self.assertEqual((merged["body"], merged["priority"], merged["revision"]), ("Manually merged", "high", 3))

    def test_idempotency_returns_current_idea_and_survives_restart(self):
        payload = request(title="Create once")
        first = self.service.incubator_create(payload)
        changed = self.update(first["idea"], body="Later edit")
        duplicate = WorkflowService(self.data).incubator_create(payload)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["idea"], changed)
        update_payload = request(id=changed["id"], expectedRevision=changed["revision"], stage="ready")
        applied = self.service.incubator_update(update_payload)
        self.assertTrue(self.service.incubator_update(update_payload)["duplicate"])
        self.assertEqual(len(self.service.incubator_list()["ideas"]), 1)
        self.error(lambda: self.service.incubator_create({**payload, "title": "Different"}), 409)
        self.error(lambda: self.service.incubator_update({**update_payload, "stage": "thinking"}), 409)
        self.error(lambda: self.service.incubator_update({**update_payload, "requestId": payload["requestId"]}), 409)
        self.assertEqual(self.service.incubator_list()["ideas"], [applied["idea"]])

    def test_parent_tree_rejects_self_ancestor_missing_and_invalid_ids(self):
        parent = self.create(title="Parent")
        child = self.create(title="Child", parentId=parent["id"])
        grandchild = self.create(title="Grandchild", parentId=child["id"])
        self.error(lambda: self.update(parent, parentId=parent["id"]), 409, "idea_cycle")
        self.error(lambda: self.update(parent, parentId=grandchild["id"]), 409, "idea_cycle")
        self.error(lambda: self.update(child, parentId=uuid.uuid4().hex), 404, "idea_not_found")
        for invalid in ([], {}, False, "../record"):
            self.error(lambda value=invalid: self.update(child, parentId=value), 404)
        detached = self.update(child, parentId=None)
        self.assertIsNone(detached["parentId"])

    def test_concurrent_writers_allow_only_one_matching_revision(self):
        idea = self.create(title="Simultaneous")
        other = WorkflowService(self.data)
        barrier, outcomes = threading.Barrier(2), []
        def save(service, body):
            barrier.wait(timeout=3)
            try:
                outcomes.append(service.incubator_update(request(id=idea["id"], expectedRevision=1, body=body)))
            except WorkflowError as error:
                outcomes.append(error)
        threads = [threading.Thread(target=save, args=(service, body))
                   for service, body in ((self.service, "Computer"), (other, "Phone"))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(sum(isinstance(item, dict) for item in outcomes), 1)
        self.assertEqual([item.code for item in outcomes if isinstance(item, WorkflowError)], ["revision_conflict"])
        self.assertEqual(self.service.incubator_list()["ideas"][0]["revision"], 2)

    def test_concurrent_reparenting_never_creates_cycle(self):
        left, right = self.create(title="Left"), self.create(title="Right")
        other = WorkflowService(self.data)
        barrier, outcomes = threading.Barrier(2), []
        def move(service, idea, parent):
            barrier.wait(timeout=3)
            try:
                outcomes.append(service.incubator_update(request(id=idea["id"], expectedRevision=1, parentId=parent["id"])))
            except WorkflowError as error:
                outcomes.append(error)
        threads = [threading.Thread(target=move, args=(self.service, left, right)),
                   threading.Thread(target=move, args=(other, right, left))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sum(isinstance(item, dict) for item in outcomes), 1)
        self.assertEqual([item.code for item in outcomes if isinstance(item, WorkflowError)], ["idea_cycle"])

    def test_target_metadata_is_validated_but_never_sent(self):
        target = "01a10257-e1b3-7ce2-a0af-cf9df4ec2c09"
        idea = self.create(title="Publish later", targetKind="codex", targetThreadId=target, targetName="Codex Console")
        self.assertEqual(idea["targetThreadId"], target)
        self.error(lambda: self.update(idea, targetThreadId="not-a-uuid"))
        idea = self.update(idea, targetKind="chatgpt", targetThreadId="conversation_abc", targetName="整理任务")
        idea = self.update(idea, targetKind="none")
        self.assertEqual((idea["targetThreadId"], idea["targetName"]), ("", ""))
        self.assertFalse(self.service.has_pending_jobs())

    def test_limits_enums_expected_revision_and_request_ids(self):
        self.create(title="a" * 160, body="b" * 20000)
        for fields in ({"title": " "}, {"title": "a" * 161}, {"body": "a" * 20001}, {"body": "\0"},
                       {"stage": "fuzzy"}, {"priority": "urgent"}, {"targetKind": []}, {"targetName": "a" * 121},
                       {"targetThreadId": "a" * 129}, {"title": 1}, {"execute": True}):
            self.error(lambda values=fields: self.service.incubator_create(request(**values)))
        self.error(lambda: self.service.incubator_create({"requestId": "invalid", "title": "No receipt"}))
        idea = self.create(title="Revision validation")
        for revision in (None, "1", True, 0, -1, 9007199254740992):
            self.error(lambda value=revision: self.service.incubator_update(request(id=idea["id"], expectedRevision=value, body="bad")))
        self.error(lambda: self.service.incubator_update(request(id=idea["id"], expectedRevision=1)))

    def test_authorization_revocation_rolls_back_idea_receipt_and_revision(self):
        calls = []
        def revoked():
            calls.append(True)
            if len(calls) == 2:
                raise WorkflowError("Pairing revoked", 401)
        payload = request(title="Never accepted")
        before = self.service.incubator_list()
        self.error(lambda: self.service.incubator_create(payload, authorize=revoked), 401)
        self.assertEqual(self.service.incubator_list(), before)
        applied = self.service.incubator_create(payload)
        self.assertFalse(applied["duplicate"])
        calls.clear()
        edit = request(id=applied["idea"]["id"], expectedRevision=1, body="Unauthorized edit")
        before = self.service.incubator_list()
        self.error(lambda: self.service.incubator_update(edit, authorize=revoked), 401)
        self.assertEqual(self.service.incubator_list(), before)
        self.assertFalse(self.service.incubator_update(edit)["duplicate"])

    def test_shared_routes_priority_and_conditional_cursor(self):
        low = workflow_post(self.service, "incubator/create", request(title="Low", priority="low"), desktop=True)["idea"]
        high = workflow_post(self.service, "incubator/create", request(title="High", priority="high"), prefix="/api/phone/workflow")["idea"]
        listing = workflow_get(self.service, "incubator", "", prefix="/api/phone/workflow")
        self.assertEqual([idea["id"] for idea in listing["ideas"]], [high["id"], low["id"]])
        self.assertEqual(workflow_get(self.service, "incubator", "revision=" + listing["revision"]),
                         {"unchanged": True, "revision": listing["revision"]})
        for query in ("id=x", "revision=", "revision=1&revision=2", "revision=invalid"):
            self.error(lambda value=query: workflow_get(self.service, "incubator", value))

    def publish(self, idea, **fields):
        return self.service.incubator_publish(request(id=idea["id"], expectedRevision=idea["revision"],
            targetKind="codex", targetMode="new", targetThreadId=None, **fields))

    def test_publish_requires_explicit_action_and_freezes_current_content(self):
        idea = self.create(title="Reviewed title", body="Reviewed body", stage="ready", priority="high")
        self.assertEqual(self.service.incubator_list()["dispatches"], [])
        payload = request(id=idea["id"], expectedRevision=1, targetKind="codex", targetMode="new", targetName="New local task")
        self.error(lambda: self.service.incubator_publish({**payload, "prompt": "Unreviewed replacement"}))
        accepted = self.service.incubator_publish(payload)
        duplicate = self.service.incubator_publish(payload)
        dispatch = accepted["dispatch"]
        self.assertEqual(dispatch["prompt"], f"[Codex Console 发布编号：{dispatch['id']}]\n\n" + idea["publishPrompt"])
        self.assertEqual(dispatch["snapshot"], {key: idea[key] for key in ("title", "body", "stage", "priority", "revision")})
        self.assertEqual((dispatch["status"], accepted["idea"]["stage"]), ("pending", "queued"))
        self.assertTrue(dispatch["userConfirmedAt"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["dispatch"]["id"], dispatch["id"])
        self.error(lambda: self.publish(accepted["idea"]), 409, "dispatch_in_progress")
        self.assertEqual(len(self.service.incubator_dispatches()["dispatches"]), 1)
        self.assertFalse(self.service.has_pending_jobs())

    def test_publish_targets_and_stale_review_are_rejected(self):
        idea = self.create(title="Target validation")
        base = request(id=idea["id"], expectedRevision=1, targetKind="codex", targetMode="new")
        for invalid in ({"targetKind": "none"}, {"targetKind": "chatgpt"}, {"targetMode": []},
                        {"targetMode": "existing", "targetThreadId": None},
                        {"targetMode": "existing", "targetThreadId": "invalid"},
                        {"targetThreadId": str(uuid.uuid4())}):
            self.error(lambda values=invalid: self.service.incubator_publish({**base, **values}))
        edited = self.update(idea, body="Changed after review")
        self.error(lambda: self.service.incubator_publish(base), 409, "revision_conflict")
        existing = self.service.incubator_publish(request(id=edited["id"], expectedRevision=2, targetKind="chatgpt",
            targetMode="existing", targetThreadId=str(uuid.uuid4()), targetName="Existing chat"))
        self.assertEqual(existing["dispatch"]["targetKind"], "chatgpt")

    def test_claim_priority_idempotency_and_private_token(self):
        low = self.publish(self.create(title="Low", priority="low"))["dispatch"]
        normal = self.publish(self.create(title="Normal"))["dispatch"]
        high = self.publish(self.create(title="High", priority="high"))["dispatch"]
        payload = request()
        claimed = self.service.incubator_claim(payload)["dispatch"]
        self.assertEqual(claimed["id"], high["id"])
        self.assertTrue(claimed["claimToken"])
        self.assertEqual(self.service.incubator_claim(payload)["dispatch"]["claimToken"], claimed["claimToken"])
        self.error(lambda: self.service.incubator_claim(request(id=high["id"])), 409, "dispatch_busy")
        self.assertNotIn("claimToken", json.dumps(self.service.incubator_list()))
        self.assertEqual(self.service.incubator_dispatches(waiting=True, private=True)["dispatches"], [claimed])
        self.service.incubator_fail(request(id=claimed["id"], claimToken=claimed["claimToken"], error="Known fixture rejection"))
        claimed = self.service.incubator_claim(request())["dispatch"]
        self.assertEqual(claimed["id"], normal["id"])
        self.service.incubator_fail(request(id=claimed["id"], claimToken=claimed["claimToken"], error="Known fixture rejection"))
        self.assertEqual(self.service.incubator_claim(request())["dispatch"]["id"], low["id"])

    def test_two_consumers_cannot_claim_two_live_dispatches(self):
        for title in ("First", "Second"):
            self.publish(self.create(title=title))
        other = WorkflowService(self.data, recover_jobs=False)
        barrier, outcomes = threading.Barrier(2), []
        def claim(service):
            barrier.wait(timeout=3)
            try:
                outcomes.append(service.incubator_claim(request()))
            except WorkflowError as error:
                outcomes.append(error)
        threads = [threading.Thread(target=claim, args=(service,)) for service in (self.service, other)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sum(isinstance(item, dict) for item in outcomes), 1)
        self.assertEqual([item.code for item in outcomes if isinstance(item, WorkflowError)], ["dispatch_busy"])

    def test_empty_claim_nonce_cannot_claim_future_publication(self):
        payload = request()
        self.assertIsNone(self.service.incubator_claim(payload)["dispatch"])
        pending = self.publish(self.create(title="Later"))["dispatch"]
        self.assertIsNone(self.service.incubator_claim(payload)["dispatch"])
        self.assertEqual(self.service.incubator_claim(request())["dispatch"]["id"], pending["id"])

    def test_claimed_result_waits_then_completed_is_persisted(self):
        accepted = self.publish(self.create(title="Actual result later"))
        claimed = self.service.incubator_claim(request(id=accepted["dispatch"]["id"]))["dispatch"]
        thread_id = str(uuid.uuid4())
        payload = request(id=claimed["id"], claimToken=claimed["claimToken"], status="waiting", targetThreadId=thread_id,
                          result={"turnId": "verified-turn", "sourceMessageId": "published-user-message"})
        waiting = self.service.incubator_attach_result(payload)
        self.assertEqual(waiting["dispatch"]["status"], "waiting")
        self.assertEqual(waiting["idea"]["stage"], "queued")
        self.error(lambda: self.service.incubator_attach_result({**request(), "id": claimed["id"], "claimToken": uuid.uuid4().hex,
            "status": "completed", "result": {"text": "Wrong claimant"}}), 403)
        self.error(lambda: self.service.incubator_attach_result(request(id=claimed["id"], claimToken=claimed["claimToken"],
            status="completed", targetThreadId=str(uuid.uuid4()), result={"text": "Wrong thread"})), 409)
        self.error(lambda: self.service.incubator_attach_result(request(id=claimed["id"], claimToken=claimed["claimToken"], status="completed")))
        self.error(lambda: self.service.incubator_attach_result(request(id=claimed["id"], claimToken=claimed["claimToken"],
            status="completed", result={"text": "Other turn", "turnId": "unrelated-turn"})), 409, "result_not_matching")
        self.error(lambda: self.service.incubator_attach_result(request(id=claimed["id"], claimToken=claimed["claimToken"],
            status="completed", result={"text": "Other input", "sourceMessageId": "unrelated-message"})), 409, "result_not_matching")
        done_payload = request(id=claimed["id"], claimToken=claimed["claimToken"], status="completed",
            targetThreadId=thread_id, result={"text": "Actual final reply", "turnId": "verified-turn"})
        done = self.service.incubator_attach_result(done_payload)
        self.assertEqual(done["idea"]["stage"], "published")
        self.assertEqual(done["dispatch"]["result"]["text"], "Actual final reply")
        self.assertTrue(self.service.incubator_attach_result(done_payload)["duplicate"])
        self.assertEqual(WorkflowService(self.data).incubator_list()["dispatches"][0]["status"], "completed")

    def test_later_idea_edits_are_not_marked_published_by_old_result(self):
        accepted = self.publish(self.create(title="Original"))
        claimed = self.service.incubator_claim(request())["dispatch"]
        newer = self.update(accepted["idea"], title="New unpublished version", stage="thinking")
        result = self.service.incubator_attach_result(request(id=claimed["id"], claimToken=claimed["claimToken"],
            status="completed", targetThreadId=str(uuid.uuid4()), result={"text": "Old version finished", "turnId": "old-turn"}))
        self.assertEqual(result["idea"], newer)
        self.assertEqual(result["dispatch"]["snapshot"]["title"], "Original")

    def test_restart_uncertain_claim_cannot_resend_without_verification(self):
        accepted = self.publish(self.create(title="Uncertain"))
        claimed = self.service.incubator_claim(request())["dispatch"]
        restarted = WorkflowService(self.data)
        self.assertEqual(restarted.incubator_dispatches()["dispatches"][0]["status"], "needs_review")
        self.error(lambda: restarted.incubator_claim(request(id=claimed["id"])), 409)
        self.error(lambda: self.publish(accepted["idea"]), 409, "dispatch_in_progress")
        receipt = request(id=claimed["id"], claimToken=claimed["claimToken"], status="waiting", targetThreadId=str(uuid.uuid4()))
        self.error(lambda: restarted.incubator_attach_result(receipt), 409, "verification_required")
        self.assertEqual(restarted.incubator_attach_result({**receipt, "verified": True})["dispatch"]["status"], "waiting")

    def test_known_failure_allows_only_explicit_new_publish(self):
        accepted = self.publish(self.create(title="Known rejected delivery", stage="ready"))
        claimed = self.service.incubator_claim(request())["dispatch"]
        failed = self.service.incubator_fail(request(id=claimed["id"], claimToken=claimed["claimToken"],
            status="failed", error="Tool explicitly rejected before delivery"))
        self.assertEqual(failed["idea"]["stage"], "ready")
        self.assertIsNone(self.service.incubator_claim(request())["dispatch"])
        retried = self.publish(failed["idea"])
        self.assertNotEqual(retried["dispatch"]["id"], accepted["dispatch"]["id"])

    def test_cli_uses_existing_database_without_recovering_live_work(self):
        self.service.configure_projects([{ "id": "console", "root": str(self.root), "capabilities": ["capture_screen"]}])
        record = self.service.create(request(projectId="console", title="Live workflow"))["record"]
        job = self.service.submit(request(recordId=record["id"], text="Live job", action="capture_screen"))["job"]
        with self.service._db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job["id"],))
        pending = self.publish(self.create(title="CLI fixture"))["dispatch"]
        cli = Path(__file__).with_name("incubator-dispatch.py")
        def invoke(*arguments):
            completed = subprocess.run([sys.executable, "-B", str(cli), "--data-dir", str(self.data), *arguments],
                shell=False, capture_output=True, text=True, encoding="utf-8", timeout=10)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            return json.loads(completed.stdout)
        self.assertEqual(invoke("list")["dispatches"][0]["id"], pending["id"])
        claimed = invoke("claim", "--request-id", str(uuid.uuid4()), "--id", pending["id"])["dispatch"]
        self.assertEqual(invoke("read-waiting")["dispatches"][0]["claimToken"], claimed["claimToken"])
        self.assertEqual(self.service.detail(record["id"])["jobs"][0]["status"], "running")
        self.assertEqual(self.service.incubator_dispatches()["dispatches"][0]["status"], "claimed")

    def test_targets_preserve_real_titles_and_phone_cannot_write_worker_settings(self):
        title = " 原始聊天标题 中文 "
        body = request(targets=[{"id": str(uuid.uuid4()), "kind": "codex", "title": title, "hostId": "local",
                                 "status": {"type": "active", "activeFlags": []}}], updatedAt="2026-10-04T05:00:00+08:00")
        saved = workflow_post(self.service, "incubator/targets", body, desktop=True)
        self.assertEqual(saved["targets"][0]["title"], title)
        self.assertEqual(self.service.incubator_list()["targets"], saved["targets"])
        self.assertEqual(workflow_post(self.service, "incubator/targets", body, desktop=True), saved)
        self.error(lambda: workflow_post(self.service, "incubator/targets", body, prefix="/api/phone/workflow"), 404)
        for action in ("incubator/claim", "incubator/attach-result", "incubator/fail"):
            self.error(lambda name=action: workflow_post(self.service, name, request(), prefix="/api/phone/workflow"), 404)


class IncubatorPhoneChecks(unittest.TestCase):
    """One real disposable paired-phone round across the existing HTTP gate."""
    setUp = IncubatorChecks.setUp
    tearDown = IncubatorChecks.tearDown

    def test_paired_phone_reads_and_edits_desktop_idea(self):
        library = self.root / "library"
        library.mkdir()
        documents = DocumentLibraryService(self.root / "document-settings.json")
        documents.select(str(library))
        assets = self.root / "assets"
        assets.mkdir()
        companion = phone.PhoneCompanionService(documents, lambda: {"plan": {"groups": []}}, assets, "fixture",
            interface_getter=lambda: [{"address": "127.0.0.1", "name": "Disposable loopback"}], workflow_service=self.service)
        original = phone.is_lan_address
        with socket.socket() as holder:
            holder.bind(("127.0.0.1", 0))
            port = holder.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        cookie = ""
        def phone_request(path, method="GET", body=None, extra=None):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            headers = {"Cookie": cookie, "Origin": origin, "X-Codex-Phone": "1", "Content-Type": "application/json"}
            headers.update(extra or {})
            try:
                connection.request(method, path, json.dumps(body).encode() if body is not None else None, headers)
                response = connection.getresponse()
                return response.status, json.loads(response.read()), dict(response.getheaders())
            finally:
                connection.close()
        with patch.object(phone, "is_lan_address", lambda value: value == "127.0.0.1" or original(value)):
            try:
                companion.start("127.0.0.1", port)
                self.assertEqual(phone_request("/api/phone/workflow/incubator")[0], 401)
                status, _, headers = phone_request("/api/phone/pair", "POST", {"code": companion.state(False)["pairingCode"]})
                self.assertEqual(status, 200)
                cookie = headers["Set-Cookie"].split(";", 1)[0]
                idea = workflow_post(self.service, "incubator/create", request(title="Computer saved"), desktop=True)["idea"]
                status, listed, _ = phone_request("/api/phone/workflow/incubator")
                self.assertEqual(status, 200)
                self.assertEqual(listed["ideas"], [idea])
                payload = request(id=idea["id"], expectedRevision=1, body="Phone refined", stage="thinking")
                status, edited, _ = phone_request("/api/phone/workflow/incubator/update", "POST", payload)
                self.assertEqual(status, 200, edited)
                self.assertEqual(workflow_get(self.service, "incubator", "")["ideas"], [edited["idea"]])
                self.assertEqual(phone_request("/api/phone/workflow/incubator/update", "POST", request(id=idea["id"], expectedRevision=1, title="Stale"))[0], 409)
                self.assertEqual(phone_request("/api/phone/workflow/incubator/create", "POST", request(title="Cross-site"), {"Origin": "http://attacker.example"})[0], 403)
                self.assertEqual(phone_request("/api/phone/workflow/incubator/create", "POST", request(title="Phone saved"))[0], 200)
                status, accepted, _ = phone_request("/api/phone/workflow/incubator/publish", "POST",
                    request(id=idea["id"], expectedRevision=edited["idea"]["revision"], targetKind="codex", targetMode="new"))
                self.assertEqual(status, 200, accepted)
                self.assertEqual(accepted["dispatch"]["status"], "pending")
                claimed = self.service.incubator_claim(request())["dispatch"]
                self.assertEqual(claimed["id"], accepted["dispatch"]["id"])
                self.assertNotIn("claimToken", json.dumps(phone_request("/api/phone/workflow/incubator")[1]))
                self.assertEqual(phone_request("/api/phone/workflow/incubator/claim", "POST", request())[0], 404)
                self.assertEqual(len(self.service.incubator_list()["ideas"]), 2)
                self.assertFalse(self.service.has_pending_jobs())
            finally:
                companion.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
