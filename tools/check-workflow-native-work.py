"""Disposable Native Codex Work contract checks. No App sends or model calls."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from transfer_store import IncomingFile
from workflow_service import WorkflowService, WorkflowError
import workflow_native_work as native_work


def request(**fields):
    return {"requestId": str(uuid.uuid4()), **fields}


def now():
    return datetime.now(timezone.utc).isoformat()


def answer(**fields):
    manifest = {"version": 1, "text": "Actual selected Work result", "files": [], "changedFiles": [], "validation": "Verified actual output", **fields}
    return "```console-work-result\n" + json.dumps(manifest, ensure_ascii=False) + "\n```"


class NoModels:
    def config(self):
        return {"ready": False}

    def __getattr__(self, name):
        raise AssertionError("Native Work must not call model method " + name)


class NativeWorkChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="console-native-work-check-")
        self.root = Path(self.temporary.name).resolve()
        self.workspace = self.root / "workspace"
        self.project = self.workspace / "console"
        self.project.mkdir(parents=True)
        (self.project / "source.txt").write_text("Original source", encoding="utf-8")
        self.service = WorkflowService(self.root / "private", models=NoModels(), projects=[{"id": "console", "name": "Fixture project", "root": str(self.project),
            "capabilities": ["capture_screen"], "allowGeneratedScripts": False}])
        self.thread_id = str(uuid.uuid4())
        self.catalog = request(source="codex_app_tools", capturedAt=now(), workspaces=[{"projectId": "saved-console", "hostId": "local", "root": str(self.workspace), "name": "Saved local Workspace"}],
            threads=[{"id": self.thread_id, "kind": "codex", "hostId": "local", "projectId": "saved-console", "cwd": str(self.workspace), "title": "Existing matching Work"}])
        self.service.native_work_catalog(self.catalog)
        self.binding = {"id": "console-source", "name": "Explicit source scope", "workspaceProjectId": "saved-console", "hostId": "local",
            "workspaceRoot": str(self.workspace), "allowedRoot": str(self.project), "allowAppWork": True}
        self.service.configure_app_work(request(bindings=[self.binding]))
        self.idea = self.service.incubator_create(request(title="Original task", body="Original task body"))["idea"]
        self.record = self.service.task_record(request(ideaId=self.idea["id"], expectedRevision=self.idea["revision"]))["record"]["id"]

    def tearDown(self):
        self.service.shutdown()
        self.temporary.cleanup()

    def body(self, **fields):
        binding = self.service.config()["appWork"]["bindings"][0]
        return request(recordId=self.record, text="Actually modify only the chosen source", sourceTask={"ideaId": self.idea["id"], "revision": self.idea["revision"]},
            context={"attachmentIds": []}, bindingId=binding["id"], workspaceAuthorizationSha256=binding["executionAuthorizationSha256"], workTarget={"mode": "new", "name": "Precise Work target"}, **fields)

    def error(self, operation, code=None):
        with self.assertRaises(WorkflowError) as caught:
            operation()
        if code:
            self.assertEqual(caught.exception.code, code)

    def claim(self, body=None):
        accepted = self.service.app_work(body or self.body())
        claim = self.service.incubator_claim(request())
        self.assertTrue(claim["shouldDispatch"])
        return accepted, claim["dispatch"]

    def attach(self, dispatch, text, **fields):
        return self.service.incubator_attach_result(request(id=dispatch["id"], claimToken=dispatch["claimToken"], targetThreadId=self.thread_id,
            status="completed", result={"text": text, "turnId": "actual-work-turn", "sourceMessageId": "actual-user-with-dispatch-marker"}, **fields))

    def test_task_mapping_browsing_is_one_record_and_never_a_publish(self):
        body = request(ideaId=self.idea["id"], expectedRevision=self.idea["revision"])
        first = self.service.task_record(body)
        self.assertEqual(first["record"]["id"], self.record)
        self.assertEqual(self.service.task_record(deepcopy(body))["record"]["id"], self.record)
        self.assertEqual(first["record"]["sourceIdeaId"], self.idea["id"])
        self.assertEqual(first["sourceTask"]["body"], "Original task body")
        self.assertEqual(self.service.incubator_list()["ideas"][0]["workflowRecordId"], self.record)
        self.assertEqual(len(self.service.list()["records"]), 1)
        self.assertEqual(self.service.incubator_dispatches()["dispatches"], [])

    def test_inventory_prunes_nested_dist_directories_without_hashing_or_counting(self):
        (self.project / "nested").mkdir()
        (self.project / "nested" / "source.txt").write_text("Nested real source", encoding="utf-8")
        artifacts = ["dist-candidate/old.txt", "nested/DIST-local/security-venv/old.txt", "nested/dist-phone/site/old.txt"]
        for relative in artifacts:
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Ignored build artifact", encoding="utf-8")
        hashed = []
        original_digest = self.service._file_digest
        def digest(path):
            relative = path.relative_to(self.project).as_posix()
            self.assertNotIn(relative, artifacts, "Excluded build output must never be read")
            hashed.append(relative)
            return original_digest(path)
        self.service._file_digest = digest
        inventory = self.service._native_inventory(self.project)
        self.assertEqual(set(inventory), {"source.txt", "nested/source.txt"})
        self.assertEqual(set(hashed), {"source.txt", "nested/source.txt"})

    def test_build_artifact_changes_do_not_invalidate_reviewed_source_before_claim(self):
        artifact = self.project / "nested" / "dist-local" / "security-venv" / "runtime.txt"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("Original generated artifact", encoding="utf-8")
        accepted = self.service.app_work(self.body())
        artifact.write_text("Rebuilt generated artifact", encoding="utf-8")
        claimed = self.service.incubator_claim(request())
        self.assertTrue(claimed["shouldDispatch"])
        self.assertEqual(claimed["dispatch"]["id"], accepted["job"]["appDispatch"]["id"])

    def test_old_excluded_artifact_cannot_be_reported_as_new_work_result(self):
        for relative in ("nested/DIST-candidate/old.txt", "dist-local/security-venv/file.txt", "nested/dist-phone/site/new.png"):
            for field in ("files", "changedFiles"):
                self.error(lambda path=relative, key=field: native_work.result_block(answer(**{key: [path]})))
        artifact = self.project / "nested" / "DIST-candidate" / "old.txt"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("An unchanged old build artifact", encoding="utf-8")
        accepted, dispatch = self.claim()
        result = self.attach(dispatch, answer(changedFiles=["nested/DIST-candidate/old.txt"]))
        self.assertEqual(result["dispatch"]["status"], "needs_review")
        self.assertFalse(result["job"]["result"]["executionVerified"])
        self.assertNotEqual(result["job"]["status"], "succeeded")
        self.assertIn("构建缓存", result["job"]["result"]["verificationError"])
        self.assertEqual(artifact.read_text(encoding="utf-8"), "An unchanged old build artifact")

    def test_dist_prefixed_source_filename_is_preserved_and_its_change_verified(self):
        path = self.project / "dist-notes.txt"
        path.write_text("Real source before Work", encoding="utf-8")
        self.assertIn("dist-notes.txt", self.service._native_inventory(self.project))
        accepted, dispatch = self.claim()
        path.write_text("Real source after Work", encoding="utf-8")
        result = self.attach(dispatch, answer(changedFiles=["dist-notes.txt"]))
        self.assertEqual(result["job"]["status"], "succeeded", result["job"])
        self.assertTrue(result["job"]["result"]["executionVerified"])
        self.assertEqual(result["job"]["result"]["fileProof"][0]["path"], "dist-notes.txt")

    def test_default_binding_disabled_and_existing_project_grants_unchanged(self):
        original = self.service.config()["projects"]
        self.service.configure_app_work(request(bindings=[{**self.binding, "allowAppWork": False}]))
        self.assertFalse(self.service.config()["appWork"]["bindings"][0]["available"])
        self.error(lambda: self.service.app_work(self.body()), "work_not_authorized")
        self.assertEqual(self.service.config()["projects"], original)
        self.assertFalse(original[0]["allowGeneratedScripts"])

    def test_actual_work_prompt_native_project_target_and_precise_source_frozen(self):
        accepted, dispatch = self.claim()
        self.assertEqual(accepted["job"]["kind"], "execute")
        self.assertEqual(accepted["job"]["executionEngine"], "codex_app")
        self.assertEqual(dispatch["sourceType"], "workflow_work")
        self.assertEqual(dispatch["snapshot"]["workspace"]["projectId"], "saved-console")
        self.assertIn(str(self.project), dispatch["prompt"])
        self.assertIn("实际完成", dispatch["prompt"])
        self.assertIn("console-work-result", dispatch["prompt"])
        self.assertEqual(dispatch["snapshot"]["sourceTask"]["body"], "Original task body")
        public = self.service.incubator_dispatches()["dispatches"][0]
        self.assertNotIn("prompt", public)
        self.assertTrue(self.service.has_pending_jobs())
        self.assertEqual(self.service.incubator_list()["dispatches"], [])

    def test_actual_file_change_and_png_are_verified_to_same_record(self):
        accepted, dispatch = self.claim()
        (self.project / "source.txt").write_text("Actual changed source", encoding="utf-8")
        Image.new("RGB", (32, 20), "green").save(self.project / "new-result.png")
        result = self.attach(dispatch, answer(changedFiles=["source.txt"], files=["new-result.png"]))
        job = result["job"]
        self.assertEqual(job["status"], "succeeded", job)
        self.assertTrue(job["result"]["executionVerified"])
        self.assertEqual(job["recordId"], self.record)
        self.assertEqual(len(job["result"]["fileProof"]), 2)
        path = self.service.attachment("id=" + job["resultAttachmentIds"][0])["path"]
        self.assertEqual(Image.open(path).getpixel((0, 0)), (0, 128, 0))
        self.assertEqual(self.service.detail(self.record)["record"]["primaryAttachmentId"], job["resultAttachmentIds"][0])

    def test_report_empty_stale_files_unfinished_or_escape_never_claim_success(self):
        for text in ("Plain App advice", answer(), answer(changedFiles=["source.txt"]), answer(files=["missing.png"]), answer(changedFiles=["../escape.txt"]),
                     "```console-work-result\n{}", answer() + "\n" + answer()):
            with self.subTest(text=text):
                accepted, dispatch = self.claim()
                result = self.attach(dispatch, text)
                self.assertEqual(result["dispatch"]["status"], "needs_review")
                self.assertFalse(result["job"]["result"]["executionVerified"])
                self.assertNotEqual(result["job"]["status"], "succeeded")
                self.error(lambda: self.service.retry(request(jobId=result["job"]["id"])), "verification_required")
                self.service.incubator_fail(request(id=dispatch["id"], claimToken=dispatch["claimToken"], status="failed", error="Known no valid output; explicit next review"))

    def test_uuid_lost_response_dedup_and_body_change_rejected(self):
        body = self.body()
        first = self.service.app_work(body)
        self.assertEqual(self.service.app_work(deepcopy(body))["job"]["id"], first["job"]["id"])
        self.error(lambda: self.service.app_work({**body, "text": "different"}))
        claimed = self.service.incubator_claim(request())
        self.assertTrue(claimed["shouldDispatch"])
        self.assertEqual(len(self.service.incubator_dispatches()["dispatches"]), 1)

    def test_existing_actual_workspace_required_not_just_title(self):
        body = self.body()
        body["workTarget"] = {"mode": "existing", "threadId": str(uuid.uuid4()), "name": "Existing matching Work"}
        self.error(lambda: self.service.app_work(body))
        body["workTarget"]["threadId"] = self.thread_id
        self.assertEqual(self.service.app_work(body)["job"]["appDispatch"]["targetThreadId"], self.thread_id)

    def test_revocation_or_file_edit_before_claim_blocks_dispatch(self):
        for change in ("grant", "source"):
            with self.subTest(change=change):
                accepted = self.service.app_work(self.body())
                if change == "grant":
                    self.service.configure_app_work(request(bindings=[{**self.binding, "allowAppWork": False}]))
                else:
                    (self.project / "source.txt").write_text("Edited after review", encoding="utf-8")
                claim = self.service.incubator_claim(request())
                self.assertFalse(claim["shouldDispatch"])
                self.assertEqual(claim["dispatch"]["status"], "failed")
                self.service.configure_app_work(request(bindings=[self.binding]))

    def test_source_idea_revision_and_record_mismatch_are_rejected(self):
        body = self.body()
        body["sourceTask"]["revision"] += 1
        self.error(lambda: self.service.app_work(body), "revision_conflict")
        body = self.body()
        body["sourceTask"]["ideaId"] = uuid.uuid4().hex
        self.error(lambda: self.service.app_work(body), "task_source_mismatch")

    def test_explicit_body_update_is_real_revision_change_without_files(self):
        accepted, dispatch = self.claim(self.body(updateTaskBody=True))
        result = self.attach(dispatch, answer(updatedTaskBody="Completed original task rewrite"))
        self.assertEqual(result["job"]["status"], "succeeded", result)
        idea = self.service.incubator_list()["ideas"][0]
        self.assertEqual(idea["body"], "Completed original task rewrite")
        self.assertEqual(idea["revision"], self.idea["revision"] + 1)
        self.assertEqual(self.service.detail(self.record)["messages"][-1]["role"], "result")

    def test_unauthorized_update_or_new_user_draft_never_overwritten(self):
        for explicit in (False, True):
            with self.subTest(explicit=explicit):
                accepted, dispatch = self.claim(self.body(updateTaskBody=explicit))
                if explicit:
                    with self.service._db() as db:
                        db.execute("UPDATE ideas SET body='User newer draft',revision=revision+1 WHERE id=?", (self.idea["id"],))
                result = self.attach(dispatch, answer(updatedTaskBody="App rewrite"))
                self.assertEqual(result["dispatch"]["status"], "needs_review")
                idea = self.service.incubator_list()["ideas"][0]
                self.assertEqual(idea["body"], "User newer draft" if explicit else "Original task body")
                self.service.incubator_fail(request(id=dispatch["id"], claimToken=dispatch["claimToken"], status="failed", error="Review required"))

    def test_restart_claim_is_needs_review_and_never_resends_or_local_executes(self):
        accepted, dispatch = self.claim()
        self.service = WorkflowService(self.root / "private", models=NoModels())
        self.assertEqual(self.service.incubator_dispatches()["dispatches"][0]["status"], "needs_review")
        self.error(lambda: self.service.incubator_claim(request()), "dispatch_busy")
        with self.service._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (accepted["job"]["id"],)).fetchone()
        self.error(lambda: self.service._run(row))

    def test_body_write_rolls_back_if_later_image_validation_fails(self):
        accepted, dispatch = self.claim(self.body(updateTaskBody=True))
        (self.project / "bad.png").write_bytes(b"Not an actual image")
        result = self.attach(dispatch, answer(updatedTaskBody="Must not be committed", files=["bad.png"]))
        self.assertEqual(result["dispatch"]["status"], "needs_review")
        current = self.service.incubator_list()["ideas"][0]
        self.assertEqual(current["body"], "Original task body")
        self.assertEqual(current["revision"], self.idea["revision"])
        self.assertEqual(self.service.detail(self.record)["attachments"], [])

    def test_precise_original_image_and_source_message_rechecked_before_claim(self):
        stream = io.BytesIO()
        Image.new("RGB", (18, 12), "blue").save(stream, "PNG")
        data = stream.getvalue()
        spool = self.root / "original.spool"
        spool.write_bytes(data)
        uploaded = self.service.upload(request(recordId=self.record), [IncomingFile(spool, 0, len(data), "original.png", "image/png")])
        image_id = uploaded["uploadedAttachmentIds"][0]
        source_id = self.service.detail(self.record)["messages"][0]["id"]
        body = self.body()
        body["context"] = {"sourceMessageId": source_id, "attachmentIds": [image_id], "selectedText": "Original"}
        accepted = self.service.app_work(body)
        path = self.service.attachment("id=" + image_id)["path"]
        path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        claim = self.service.incubator_claim(request())
        self.assertFalse(claim["shouldDispatch"])
        self.assertEqual(claim["dispatch"]["status"], "failed")

    def test_completed_retry_same_uuid_does_not_repeat_body_revision_or_result(self):
        accepted, dispatch = self.claim(self.body(updateTaskBody=True))
        body = request(id=dispatch["id"], claimToken=dispatch["claimToken"], targetThreadId=self.thread_id, status="completed",
            result={"text": answer(updatedTaskBody="Actual once-only rewrite"), "turnId": "exact-turn", "sourceMessageId": "exact-user"})
        first = self.service.incubator_attach_result(body)
        again = self.service.incubator_attach_result(deepcopy(body))
        self.assertEqual(first["job"]["resultMessageId"], again["job"]["resultMessageId"])
        self.assertTrue(again["duplicate"])
        self.assertEqual(self.service.incubator_list()["ideas"][0]["revision"], self.idea["revision"] + 1)
        self.assertEqual(len([m for m in self.service.detail(self.record)["messages"] if m["role"] == "result"]), 1)

    def test_cross_workspace_catalog_stale_and_authorization_recheck_rollback(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.error(lambda: self.service.configure_app_work(request(bindings=[{**self.binding, "allowedRoot": str(outside)}])))
        old = deepcopy(self.catalog)
        old["requestId"] = str(uuid.uuid4())
        old["capturedAt"] = "2020-01-01T00:00:00+00:00"
        self.error(lambda: self.service.native_work_catalog(old))
        calls = []
        def authorize():
            calls.append(1)
            if len(calls) == 2:
                raise WorkflowError("Desktop authorization expired", 403)
        self.error(lambda: self.service.configure_app_work(request(bindings=[]), authorize=authorize))
        self.assertEqual(len(self.service.config()["appWork"]["bindings"]), 1)

    def test_chat_freezes_same_task_revision_without_modifying_or_work_dispatch(self):
        result = self.service.discuss(request(recordId=self.record, text="Discuss original draft only", sourceTask={"ideaId": self.idea["id"], "revision": self.idea["revision"]},
            context={"attachmentIds": []}, appTarget={"kind": "codex", "mode": "new"}))
        dispatch = self.service.incubator_claim(request())["dispatch"]
        self.assertEqual(dispatch["sourceType"], "workflow_discussion")
        self.assertEqual(dispatch["snapshot"]["sourceTask"]["body"], "Original task body")
        self.assertIn('"sourceTask"', dispatch["prompt"])
        self.assertEqual(self.service.incubator_list()["ideas"][0]["revision"], self.idea["revision"])

    def test_unknown_preimage_and_private_output_not_claimed_as_code_change(self):
        accepted, dispatch = self.claim()
        (self.project / "work").mkdir()
        (self.project / "work" / "private.txt").write_text("Unverifiable private file")
        result = self.attach(dispatch, answer(changedFiles=["work/private.txt"]))
        self.assertEqual(result["dispatch"]["status"], "needs_review")
        self.assertFalse(result["job"]["result"]["executionVerified"])

    def test_only_nonce_bound_new_output_folder_can_return_images(self):
        accepted, dispatch = self.claim()
        relative = "work/console-work-results/" + dispatch["id"] + "/actual.png"
        path = self.project / relative
        path.parent.mkdir(parents=True)
        Image.new("RGB", (16, 12), "blue").save(path)
        result = self.attach(dispatch, answer(files=[relative]))
        self.assertEqual(result["job"]["status"], "succeeded", result)
        self.assertIsNone(result["job"]["result"]["fileProof"][0]["beforeSha256"])
        self.assertEqual(result["job"]["result"]["imageProof"][0]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_new_work_actual_target_workspace_must_be_verified_before_success(self):
        accepted, dispatch = self.claim(self.body(updateTaskBody=True))
        new_thread = str(uuid.uuid4())
        text = answer(updatedTaskBody="Verified target rewrite")
        body = request(id=dispatch["id"], claimToken=dispatch["claimToken"], targetThreadId=new_thread, status="completed",
            result={"text": text, "turnId": "actual-new-work-turn", "sourceMessageId": "actual-new-user"})
        result = self.service.incubator_attach_result(body)
        self.assertEqual(result["dispatch"]["status"], "needs_review")
        self.assertEqual(result["job"]["result"]["appReport"], text)
        self.assertEqual(self.service.incubator_list()["ideas"][0]["body"], "Original task body")
        catalog = deepcopy(self.catalog)
        catalog["requestId"] = str(uuid.uuid4())
        catalog["threads"].append({**catalog["threads"][0], "id": new_thread, "title": "Actually created native Work"})
        self.service.native_work_catalog(catalog)
        result = self.service.incubator_attach_result({**body, "requestId": str(uuid.uuid4()), "verified": True})
        self.assertEqual(result["job"]["status"], "succeeded", result)
        self.assertEqual(result["job"]["result"]["targetThreadId"], new_thread)
        self.assertEqual(len(self.service.incubator_dispatches()["dispatches"]), 1)

    def test_changed_task_revision_retains_verified_image_without_body_apply_or_duplicate(self):
        accepted, dispatch = self.claim(self.body(updateTaskBody=True))
        Image.new("RGB", (16, 12), "blue").save(self.project / "actual.png")
        with self.service._db() as db:
            db.execute("UPDATE ideas SET body='New user draft',revision=revision+1 WHERE id=?", (self.idea["id"],))
        text = answer(updatedTaskBody="Work candidate rewrite", files=["actual.png"])
        first = self.attach(dispatch, text)
        self.assertEqual(first["dispatch"]["status"], "needs_review")
        self.assertFalse(first["job"]["result"]["executionVerified"])
        self.assertEqual(len(first["job"]["resultAttachmentIds"]), 1)
        second = self.attach(dispatch, text, verified=True)
        self.assertEqual(first["job"]["resultMessageId"], second["job"]["resultMessageId"])
        self.assertEqual(first["job"]["resultAttachmentIds"], second["job"]["resultAttachmentIds"])
        self.assertEqual(len(self.service.detail(self.record)["attachments"]), 1)
        self.assertEqual(self.service.incubator_list()["ideas"][0]["body"], "New user draft")

    def test_revoked_authorization_keeps_actual_report_without_read_or_body_apply(self):
        accepted, dispatch = self.claim(self.body(updateTaskBody=True))
        self.service.configure_app_work(request(bindings=[{**self.binding, "allowAppWork": False}]))
        text = answer(updatedTaskBody="Must not auto apply", files=["never-read.png"])
        result = self.attach(dispatch, text)
        self.assertEqual(result["dispatch"]["status"], "needs_review")
        self.assertEqual(result["job"]["result"]["appReport"], text)
        self.assertEqual(result["job"]["resultAttachmentIds"], [])
        self.assertEqual(self.service.incubator_list()["ideas"][0]["body"], "Original task body")

    def test_unknown_baseline_is_not_misreported_as_new_file(self):
        path = self.project / "too-large-before.bin"
        with path.open("wb") as output:
            output.truncate(32 * 1024 * 1024 + 1)
        accepted, dispatch = self.claim()
        path.write_bytes(b"Actual modified but original not captured")
        result = self.attach(dispatch, answer(changedFiles=[path.name]))
        self.assertEqual(result["dispatch"]["status"], "needs_review")
        self.assertIn("快照", result["job"]["result"]["verificationError"])

    def test_image_changes_while_copied_roll_back_body_and_all_attachments(self):
        accepted, dispatch = self.claim(self.body(updateTaskBody=True))
        path = self.project / "changing.png"
        Image.new("RGB", (16, 12), "blue").save(path)
        original = self.service._store_file
        def changed(db, record_id, source, name, mime):
            Image.new("RGB", (16, 12), "green").save(source)
            return original(db, record_id, source, name, mime)
        self.service._store_file = changed
        result = self.attach(dispatch, answer(updatedTaskBody="Should roll back", files=[path.name]))
        self.assertEqual(result["dispatch"]["status"], "needs_review")
        self.assertEqual(self.service.detail(self.record)["attachments"], [])
        self.assertEqual(self.service.incubator_list()["ideas"][0]["body"], "Original task body")

    @unittest.skipUnless(os.name == "nt", "Requires the real Windows case-insensitive filesystem")
    def test_windows_case_alias_of_unchanged_file_never_claims_real_work(self):
        original_sha = hashlib.sha256((self.project / "source.txt").read_bytes()).hexdigest()
        accepted, dispatch = self.claim()
        result = self.attach(dispatch, answer(changedFiles=["SOURCE.TXT"]))
        self.assertEqual(result["dispatch"]["status"], "needs_review")
        self.assertFalse(result["job"]["result"]["executionVerified"])
        self.assertEqual(hashlib.sha256((self.project / "source.txt").read_bytes()).hexdigest(), original_sha)

    @unittest.skipUnless(os.name == "nt", "Requires the real Windows case-insensitive filesystem")
    def test_windows_cross_list_alias_is_one_modified_image_identity(self):
        path = self.project / "before.png"
        Image.new("RGB", (16, 12), "blue").save(path)
        original_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        accepted, dispatch = self.claim()
        Image.new("RGB", (16, 12), "green").save(path)
        result = self.attach(dispatch, answer(changedFiles=["before.png"], files=["BEFORE.PNG"]))
        self.assertEqual(result["job"]["status"], "succeeded", result)
        self.assertEqual(len(result["job"]["result"]["fileProof"]), 1)
        self.assertEqual(result["job"]["result"]["fileProof"][0]["beforeSha256"], original_sha)
        self.assertEqual(len(result["job"]["resultAttachmentIds"]), 1)

    @unittest.skipUnless(os.name == "nt", "Requires the real Windows case-insensitive filesystem")
    def test_windows_list_alias_duplicate_and_unknown_preimage_cannot_bypass(self):
        path = self.project / "unknown.bin"
        with path.open("wb") as output:
            output.truncate(32 * 1024 * 1024 + 1)
        accepted, dispatch = self.claim()
        path.write_bytes(b"New value, but unknown original hash")
        result = self.attach(dispatch, answer(changedFiles=["UNKNOWN.BIN"]))
        self.assertEqual(result["dispatch"]["status"], "needs_review")
        self.assertIn("快照", result["job"]["result"]["verificationError"])
        result = self.attach(dispatch, answer(changedFiles=["source.txt", "SOURCE.TXT"]), verified=True)
        self.assertEqual(result["dispatch"]["status"], "needs_review")
        self.assertIn("重复", result["job"]["result"]["verificationError"])

    def end_body(self, result):
        return request(jobId=result["job"]["id"], dispatchId=result["dispatch"]["id"],
            sourceMessageId=result["job"]["result"]["sourceMessageId"], turnId=result["job"]["result"]["turnId"])

    def test_user_can_end_returned_failed_work_keep_outputs_and_continue_same_task(self):
        accepted, dispatch = self.claim(self.body(updateTaskBody=True))
        Image.new("RGB", (16, 12), "blue").save(self.project / "returned.png")
        with self.service._db() as db:
            db.execute("UPDATE ideas SET body='Preserved newer draft',revision=revision+1 WHERE id=?", (self.idea["id"],))
        result = self.attach(dispatch, answer(updatedTaskBody="Unapplied candidate", files=["returned.png"]))
        end_body = self.end_body(result)
        ended = self.service.end_app_work(end_body)
        self.assertEqual(ended["dispatch"]["status"], "completed")
        self.assertEqual(ended["job"]["status"], "failed")
        self.assertFalse(ended["job"]["result"]["executionVerified"])
        self.assertTrue(ended["job"]["result"]["resolvedByUser"])
        self.assertEqual(ended["job"]["result"]["resolution"], "keep_current_task")
        self.assertEqual(ended["job"]["result"]["appReport"], result["job"]["result"]["appReport"])
        self.assertEqual(ended["job"]["error"], result["job"]["error"])
        self.assertEqual(ended["job"]["resultAttachmentIds"], result["job"]["resultAttachmentIds"])
        self.assertTrue(self.service.end_app_work(deepcopy(end_body))["duplicate"])
        self.assertEqual(len(self.service.detail(self.record)["attachments"]), 1)
        self.idea = self.service.incubator_list()["ideas"][0]
        self.assertEqual(self.idea["body"], "Preserved newer draft")
        accepted_next, dispatch_next = self.claim()
        self.assertNotEqual(dispatch["id"], dispatch_next["id"])
        self.assertEqual(accepted_next["job"]["recordId"], self.record)

    def test_end_returned_work_after_revocation_does_not_read_workspace(self):
        accepted, dispatch = self.claim()
        result = self.attach(dispatch, "Actual complete App report, but no execution proof")
        self.service.configure_app_work(request(bindings=[{**self.binding, "allowAppWork": False}]))
        def forbidden(*args, **kwargs):
            raise AssertionError("Ending a returned Work must not read Workspace or execute")
        self.service._native_binding = forbidden
        self.service._native_inventory = forbidden
        self.service._file_digest = forbidden
        self.service._script_images = forbidden
        result = self.service.end_app_work(self.end_body(result))
        self.assertEqual(result["job"]["status"], "failed")
        self.assertEqual(self.service.incubator_list()["ideas"][0]["body"], "Original task body")

    def test_unknown_delivery_and_incomplete_return_cannot_be_ended(self):
        accepted, dispatch = self.claim()
        body = request(jobId=accepted["job"]["id"], dispatchId=dispatch["id"], sourceMessageId="unverified-source", turnId="unverified-turn")
        self.error(lambda: self.service.end_app_work(body), "verification_required")
        self.service.incubator_attach_result(request(id=dispatch["id"], claimToken=dispatch["claimToken"], targetThreadId=self.thread_id,
            status="waiting", result={"text": "An incomplete preview", "turnId": "unverified-turn", "sourceMessageId": "unverified-source"}))
        self.service.incubator_fail(request(id=dispatch["id"], claimToken=dispatch["claimToken"], status="needs_review", error="Unknown actual acceptance"))
        self.error(lambda: self.service.end_app_work(body), "verification_required")
        self.assertEqual(self.service.incubator_dispatches()["dispatches"][0]["status"], "needs_review")

    def test_end_exact_source_cross_record_uuid_and_authorization_rollback(self):
        accepted, dispatch = self.claim()
        result = self.attach(dispatch, "Actual completed report without verifiable changes")
        body = self.end_body(result)
        for changed in ({"jobId": uuid.uuid4().hex}, {"sourceMessageId": "wrong-user"}, {"turnId": "wrong-turn"}, {"extra": "unapproved"}):
            with self.subTest(changed=changed):
                self.error(lambda: self.service.end_app_work({**body, **changed}))
        calls = []
        def authorize():
            calls.append(1)
            if len(calls) == 2:
                raise WorkflowError("Phone authorization expired", 401)
        self.error(lambda: self.service.end_app_work(body, authorize=authorize))
        detail = self.service.detail(self.record)
        self.assertEqual(detail["jobs"][-1]["status"], "waiting")
        self.assertEqual(detail["jobs"][-1]["appDispatch"]["status"], "needs_review")
        ended = self.service.end_app_work(body)
        self.assertFalse(ended["duplicate"])
        self.error(lambda: self.service.end_app_work({**body, "turnId": "changed-body-with-same-uuid"}))

    def test_known_rolled_back_rejection_has_no_accepted_queue_but_same_uuid_never_cancels(self):
        rejected = self.body()
        rejected["sourceTask"]["revision"] += 1
        with self.assertRaises(WorkflowError) as caught:
            self.service.app_work(rejected)
        self.assertIs(caught.exception.queueAccepted, False)
        self.assertEqual(self.service.incubator_dispatches()["dispatches"], [])
        body = self.body()
        accepted = self.service.app_work(body)
        changed = deepcopy(body)
        changed["text"] = "Different payload with already accepted UUID"
        with self.assertRaises(WorkflowError) as caught:
            self.service.app_work(changed)
        self.assertFalse(hasattr(caught.exception, "queueAccepted"))
        replay = self.service.app_work(deepcopy(body))
        self.assertEqual(replay["job"]["id"], accepted["job"]["id"])
        self.assertTrue(replay["duplicate"])

    def test_authorization_or_unknown_error_never_releases_pending_outbox(self):
        body = self.body()
        def forbidden():
            raise WorkflowError("Authentication failed", 401, "permission_changed")
        with self.assertRaises(WorkflowError) as caught:
            self.service.app_work(body, authorize=forbidden)
        self.assertFalse(hasattr(caught.exception, "queueAccepted"))
        calls = []
        def expire():
            calls.append(1)
            if len(calls) == 2:
                raise WorkflowError("Authorization changed during acceptance", 403, "permission_changed")
        with self.assertRaises(WorkflowError) as caught:
            self.service.app_work(body, authorize=expire)
        self.assertFalse(hasattr(caught.exception, "queueAccepted"))
        self.assertEqual(self.service.incubator_dispatches()["dispatches"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
