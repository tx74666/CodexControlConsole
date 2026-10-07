#!/usr/bin/env python3
"""Exercise atomic saved-idea imports using only isolated databases and files."""
import copy
from contextlib import closing
from email.message import Message
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from transfer_store import IncomingFile, TransferError, read_transfer_request
from workflow_http import workflow_get, workflow_import_idea, workflow_post
from workflow_service import WorkflowError, WorkflowService


class ForbiddenModels:
    def config(self):
        return {"ready": False, "selected": "", "providers": []}

    def discuss(self, *_args, **_kwargs):
        raise AssertionError("An idea import must never call a model")


class MobileHandoffChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="console-mobile-handoff-check-")
        self.root = Path(self.temporary.name)
        self.service = WorkflowService(self.root / "private", models=ForbiddenModels(), projects=[
            {"id": "test", "name": "Isolated test", "root": str(self.root), "capabilities": ["result_import"]}])
        self.manifest = {"format": "codex-console-idea", "version": 1,
            "source": {"clientId": str(uuid.uuid4()), "ideaId": uuid.uuid4().hex, "revision": 1},
            "idea": {"title": "手机保存的想法", "body": "原始底稿", "executionDraft": "尚未交付的执行稿",
                "archived": False, "keyPoints": [{"id": uuid.uuid4().hex, "text": "需要确认的建议", "kind": "suggestion"},
                    {"id": uuid.uuid4().hex, "text": "手机已保存的决定", "kind": "decision"}]}, "images": []}

    def tearDown(self):
        self.service.shutdown()
        self.temporary.cleanup()

    def fields(self, manifest=None, request_id=None):
        return {"requestId": request_id or str(uuid.uuid4()), "text": json.dumps(manifest or self.manifest, ensure_ascii=False)}

    def image(self, color="purple", name="图片.png"):
        path = self.root / (uuid.uuid4().hex + ".png")
        Image.new("RGB", (12, 12), color).save(path, "PNG")
        meta = {"id": uuid.uuid4().hex, "name": name, "mimeType": "image/png", "size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        return meta, IncomingFile(path, 0, path.stat().st_size, name, "image/png")

    def import_idea(self, fields=None, files=None, authorize=None):
        return workflow_import_idea(self.service, fields or self.fields(), files or [],
            prefix="/api/phone/workflow", authorize=authorize)

    def lookup(self, fields, authorize=None):
        return workflow_post(self.service, "mobile/idea/import-status", fields,
            prefix="/api/phone/workflow", authorize=authorize)

    def state(self):
        with self.service._db() as db:
            return {table: [tuple(row) for row in db.execute("SELECT * FROM " + table + " ORDER BY rowid")]
                for table in ("settings", "records", "messages", "attachments", "ideas", "jobs", "idea_dispatches", "requests")}

    def reject(self, operation, code=None):
        with self.assertRaises(WorkflowError) as caught:
            operation()
        if code:
            self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_import_preserves_saved_fields_and_source_without_any_delivery(self):
        image, file = self.image()
        self.manifest["images"] = [image]
        fields = self.fields()
        result = self.import_idea(fields, [file])
        self.assertEqual(result["requestId"], fields["requestId"])
        self.assertFalse(result["duplicate"])
        self.assertEqual(result["imported"]["source"], self.manifest["source"])
        self.assertEqual(result["imported"]["destinationRevision"], 1)
        idea, detail = result["idea"], result["detail"]
        self.assertNotEqual(idea["id"], self.manifest["source"]["ideaId"])
        self.assertEqual(idea["id"], result["imported"]["ideaId"])
        self.assertEqual(idea["workflowRecordId"], detail["record"]["id"])
        for field in ("title", "body", "executionDraft", "archived"):
            self.assertEqual(idea[field], self.manifest["idea"][field])
        self.assertEqual([{key: point[key] for key in ("id", "text", "kind")} for point in idea["keyPoints"]], self.manifest["idea"]["keyPoints"])
        self.assertFalse(idea["provenance"][-1]["authorityVerified"])
        self.assertTrue(idea["provenance"][-1]["sourceClaim"])
        self.assertEqual(idea["provenance"][-1]["kind"], "phone_imported")
        self.assertEqual(idea["attachmentIds"], detail["messages"][-1]["attachmentIds"])
        attachment = detail["attachments"][0]
        self.assertEqual(attachment["name"], "图片.png")
        self.assertTrue(attachment["url"].startswith("/api/phone/workflow/attachment?"))
        actual = self.service.attachment("id=" + attachment["id"])["path"]
        self.assertEqual(hashlib.sha256(actual.read_bytes()).hexdigest(), image["sha256"])
        state = self.state()
        self.assertFalse(state["jobs"])
        self.assertFalse(state["idea_dispatches"])
        self.assertFalse(self.service._wake.is_set())

    def test_same_nonce_and_source_revision_replay_do_not_duplicate(self):
        image, file = self.image()
        self.manifest["images"] = [image]
        fields = self.fields()
        first = self.import_idea(fields, [file])
        state = self.state()
        second = self.import_idea(fields, [file])
        self.assertTrue(second["duplicate"])
        self.assertEqual(state, self.state())
        third = self.import_idea(self.fields(), [file])
        self.assertTrue(third["duplicate"])
        self.assertEqual(first["idea"], third["idea"])
        self.assertEqual(len(self.state()["attachments"]), 1)
        self.assertEqual(len(self.state()["ideas"]), 1)
        self.assertEqual(len(self.state()["messages"]), 1)

    def test_nonce_reuse_with_different_body_rejects_without_changes(self):
        fields = self.fields()
        self.import_idea(fields)
        previous = self.state()
        self.manifest["idea"]["body"] = "不同内容"
        self.reject(lambda: self.import_idea(self.fields(request_id=fields["requestId"])))
        self.assertEqual(self.state(), previous)

    def test_same_source_revision_content_collision_rejects(self):
        self.import_idea()
        previous = self.state()
        self.manifest["idea"]["body"] = "同版本冲突"
        self.reject(lambda: self.import_idea(), "import_source_conflict")
        self.assertEqual(previous, self.state())

    def test_new_revision_updates_original_idea_and_reuses_verified_image(self):
        image, file = self.image()
        self.manifest["images"] = [image]
        first = self.import_idea(files=[file])
        self.manifest["source"]["revision"] = 2
        self.manifest["idea"].update(title="修改后的标题", body="第二版底稿", archived=True, executionDraft="第二版执行稿")
        second = self.import_idea(files=[file])
        self.assertEqual(second["idea"]["id"], first["idea"]["id"])
        self.assertEqual(second["idea"]["workflowRecordId"], first["idea"]["workflowRecordId"])
        self.assertEqual(second["idea"]["revision"], 2)
        self.assertEqual(second["idea"]["attachmentIds"], first["idea"]["attachmentIds"])
        self.assertEqual(len(self.state()["attachments"]), 1)
        self.assertEqual(len(self.state()["records"]), 1)
        self.assertEqual(len(self.state()["messages"]), 2)
        self.assertEqual(second["idea"]["body"], "第二版底稿")
        self.assertTrue(second["idea"]["archived"])
        self.assertEqual(len(second["idea"]["provenance"]), 2)

    def test_old_import_snapshot_preserves_execution_draft_points_and_original_bytes(self):
        image, file = self.image()
        self.manifest["images"] = [image]
        original = copy.deepcopy(self.manifest)
        first = self.import_idea(files=[file])
        self.manifest["source"]["revision"] = 2
        self.manifest["idea"].update(body="新底稿", executionDraft="新的执行稿", keyPoints=[])
        self.manifest["images"] = []
        second = self.import_idea()
        key = "mobile-import:" + original["source"]["clientId"] + ":" + original["source"]["ideaId"] + ":revision:1:snapshot"
        with self.service._db() as db:
            saved = self.service._setting(db, key)
        self.assertEqual(saved["manifest"], original)
        self.assertEqual(saved["attachmentIds"], first["idea"]["attachmentIds"])
        self.assertEqual(saved["destinationRevision"], 1)
        self.assertEqual(second["idea"]["attachmentIds"], [])
        path = self.service.attachment("id=" + saved["attachmentIds"][0])["path"]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), image["sha256"])

    def test_late_database_failure_cleans_created_images_and_rolls_back_all_rows(self):
        image, file = self.image()
        self.manifest["images"] = [image]
        previous = self.state()
        original = self.service._set_setting
        def fail_snapshot(db, key, value):
            if key.endswith(":snapshot"):
                raise WorkflowError("隔离测试模拟写入失败", 503)
            return original(db, key, value)
        with patch.object(self.service, "_set_setting", fail_snapshot):
            self.reject(lambda: self.import_idea(files=[file]))
        self.assertEqual(previous, self.state())
        self.assertFalse(list(self.service.attachments_dir.iterdir()))
        self.assertFalse(list(self.service.jobs_dir.iterdir()))

    def test_unexpected_uuid_collision_preserves_existing_image_and_preview_files(self):
        image, file = self.image()
        self.manifest["images"] = [image]
        identifier = "a" * 32
        fake_uuid = SimpleNamespace(UUID=uuid.UUID, uuid4=lambda: uuid.UUID(hex=identifier))
        for suffix in (".png", ".preview.jpg"):
            with self.subTest(suffix=suffix):
                path = self.service.attachments_dir / (identifier + suffix)
                path.write_bytes(b"Unrelated pre-existing content")
                previous = self.state()
                with patch("workflow_mobile_handoff.uuid", fake_uuid):
                    self.reject(lambda: self.import_idea(files=[file]), "import_storage_conflict")
                self.assertEqual(previous, self.state())
                self.assertEqual(path.read_bytes(), b"Unrelated pre-existing content")
                self.assertEqual(list(self.service.attachments_dir.iterdir()), [path])
                path.unlink()

    def test_computer_edit_conflict_keeps_both_and_no_new_files(self):
        first = self.import_idea()
        workflow_post(self.service, "mobile/idea/update", {"requestId": str(uuid.uuid4()),
            "id": first["idea"]["id"], "expectedRevision": 1, "body": "电脑已编辑的内容"})
        previous = self.state()
        self.manifest["source"]["revision"] = 2
        image, file = self.image()
        self.manifest["images"] = [image]
        self.reject(lambda: self.import_idea(files=[file]), "import_conflict")
        self.assertEqual(previous, self.state())
        self.assertEqual(list(self.service.attachments_dir.iterdir()), [])
        self.assertEqual(list(self.service.jobs_dir.iterdir()), [])

    def test_old_import_replay_returns_actual_current_idea_and_original_receipt(self):
        old_manifest = copy.deepcopy(self.manifest)
        fields = self.fields()
        first = self.import_idea(fields)
        self.manifest["source"]["revision"] = 3
        self.manifest["idea"]["body"] = "第三版"
        latest = self.import_idea()
        replay = self.import_idea(fields)
        self.assertEqual(replay["idea"], latest["idea"])
        self.assertEqual(replay["imported"], first["imported"])
        self.assertTrue(replay["duplicate"])
        unknown = copy.deepcopy(old_manifest)
        unknown["source"]["revision"] = 2
        previous = self.state()
        self.reject(lambda: self.import_idea(self.fields(unknown)), "import_revision_conflict")
        self.assertEqual(previous, self.state())

    def test_different_phone_store_identity_does_not_merge_source_idea(self):
        first = self.import_idea()
        self.manifest["source"]["clientId"] = str(uuid.uuid4())
        second = self.import_idea()
        self.assertNotEqual(first["idea"]["id"], second["idea"]["id"])
        self.assertEqual(len(self.state()["ideas"]), 2)

    def test_revoked_authorization_rolls_back_everything_and_only_own_files(self):
        image, file = self.image()
        self.manifest["images"] = [image]
        original = self.service.attachments_dir / (uuid.uuid4().hex + ".keep")
        original.write_bytes(b"Preserve unrelated existing content")
        previous = self.state()
        calls = []
        def authorize():
            calls.append(True)
            if len(calls) == 2:
                raise WorkflowError("配对已撤销", 401, "session_expired")
        self.reject(lambda: self.import_idea(files=[file], authorize=authorize), "session_expired")
        self.assertEqual(previous, self.state())
        self.assertEqual(list(self.service.attachments_dir.iterdir()), [original])
        self.assertEqual(original.read_bytes(), b"Preserve unrelated existing content")
        self.assertFalse(list(self.service.jobs_dir.iterdir()))

    def test_image_content_mismatch_and_corruption_never_persist(self):
        image, file = self.image()
        self.manifest["images"] = [{**image, "sha256": "0" * 64}]
        previous = self.state()
        self.reject(lambda: self.import_idea(files=[file]), "import_image_mismatch")
        self.assertEqual(previous, self.state())
        broken = self.root / "broken.png"
        broken.write_bytes(b"Not an image")
        self.manifest["images"] = [{**image, "size": broken.stat().st_size,
            "sha256": hashlib.sha256(broken.read_bytes()).hexdigest()}]
        self.reject(lambda: self.import_idea(files=[IncomingFile(broken, 0, broken.stat().st_size, image["name"], "image/png")]))
        self.assertEqual(previous, self.state())
        self.assertFalse(list(self.service.attachments_dir.iterdir()))
        self.assertFalse(list(self.service.jobs_dir.iterdir()))

    def test_image_identifier_collision_rolls_back_updated_idea(self):
        image, file = self.image()
        self.manifest["images"] = [image]
        self.import_idea(files=[file])
        second_image, second_file = self.image("blue")
        second_image["id"] = image["id"]
        self.manifest["source"]["revision"] = 2
        self.manifest["images"] = [second_image]
        previous = self.state()
        self.reject(lambda: self.import_idea(files=[second_file]), "import_source_conflict")
        self.assertEqual(previous, self.state())
        self.assertEqual(len(list(self.service.attachments_dir.iterdir())), 2)

    def test_missing_existing_original_image_prevents_silent_reuse(self):
        image, file = self.image()
        self.manifest["images"] = [image]
        first = self.import_idea(files=[file])
        self.service.attachment("id=" + first["idea"]["attachmentIds"][0])["path"].unlink()
        self.manifest["source"]["revision"] = 2
        previous = self.state()
        self.reject(lambda: self.import_idea(files=[file]), "import_image_unavailable")
        self.assertEqual(previous, self.state())

    def test_manifest_rejects_untrusted_authority_fields_and_invalid_limits(self):
        previous = self.state()
        cases = []
        for location, key, value in [("idea", "projectId", "test"), ("idea", "target", {}), ("source", "root", "D:/"), (None, "dispatch", True)]:
            manifest = copy.deepcopy(self.manifest)
            (manifest[location] if location else manifest)[key] = value
            cases.append(manifest)
        for field, value in [("title", "x" * 161), ("body", "x" * 20001), ("executionDraft", "x" * 20001), ("archived", 1)]:
            manifest = copy.deepcopy(self.manifest)
            manifest["idea"][field] = value
            cases.append(manifest)
        manifest = copy.deepcopy(self.manifest)
        manifest["source"]["revision"] = True
        cases.append(manifest)
        manifest = copy.deepcopy(self.manifest)
        manifest["idea"]["keyPoints"][0]["text"] = "x" * 20001
        cases.append(manifest)
        for manifest in cases:
            with self.subTest(manifest=manifest):
                self.reject(lambda: self.import_idea(self.fields(manifest)))
                self.assertEqual(previous, self.state())
        fields = self.fields()
        fields["text"] = '{"format":"one","format":"two"}'
        self.reject(lambda: self.import_idea(fields))
        self.assertEqual(previous, self.state())

    def test_full_legal_long_points_and_unicode_remain_exact_after_import(self):
        for text in ("x" * 20000, "😀" * 19000):
            manifest = json.loads(json.dumps(self.manifest))
            manifest["source"]["ideaId"] = uuid.uuid4().hex
            manifest["idea"]["keyPoints"][0]["text"] = text
            result = self.import_idea(self.fields(manifest))
            self.assertEqual(result["idea"]["keyPoints"][0]["text"], text)
            self.assertEqual(result["idea"]["keyPoints"][0]["kind"], "suggestion")
            self.assertEqual(result["idea"]["keyPoints"][1]["kind"], "decision")
            self.assertEqual(result["idea"]["provenance"][-1]["kind"], "phone_imported")
        previous = self.state()
        manifest["source"]["ideaId"] = uuid.uuid4().hex
        # 20,000 four-byte codepoints fit the individual contract, but JSON
        # framing makes their portable manifest exceed the unchanged byte cap.
        manifest["idea"]["keyPoints"][0]["text"] = "😀" * 20000
        self.assertGreater(len(self.fields(manifest)["text"].encode("utf-8")), 80000)
        self.reject(lambda: self.import_idea(self.fields(manifest)))
        self.assertEqual(previous, self.state())

    def test_mixed_full_points_preserve_exact_eighty_thousand_manifest_byte_boundary(self):
        manifest = json.loads(json.dumps(self.manifest))
        manifest["idea"]["keyPoints"] = [{"id": uuid.uuid4().hex, "text": "x" * 20000,
            "kind": "decision" if index == 0 else "suggestion"} for index in range(3)]
        manifest["idea"]["body"] = ""
        manifest["idea"]["executionDraft"] = "d" * 10000
        remaining = 80000 - len(self.fields(manifest)["text"].encode("utf-8"))
        self.assertTrue(0 < remaining <= 20000)
        manifest["idea"]["body"] = "b" * remaining
        fields = self.fields(manifest)
        self.assertEqual(len(fields["text"].encode("utf-8")), 80000)
        imported = self.import_idea(fields)
        self.assertEqual([{key: point[key] for key in ("id", "text", "kind")} for point in imported["idea"]["keyPoints"]], manifest["idea"]["keyPoints"])
        previous = self.state()
        manifest["source"]["ideaId"] = uuid.uuid4().hex
        manifest["idea"]["body"] += "b"
        fields = self.fields(manifest)
        self.assertEqual(len(fields["text"].encode("utf-8")), 80001)
        self.reject(lambda: self.import_idea(fields))
        self.assertEqual(self.state(), previous)

    def test_manifest_utf8_bytes_bound_and_file_count_or_size_are_checked(self):
        previous = self.state()
        manifest = copy.deepcopy(self.manifest)
        manifest["idea"]["body"] = "字" * 20000
        manifest["idea"]["executionDraft"] = "字" * 20000
        self.assertEqual(self.reject(lambda: self.import_idea(self.fields(manifest))).status, 413)
        image, file = self.image()
        self.reject(lambda: self.import_idea(files=[file]))
        self.manifest["images"] = [{**image, "size": 8 * 1024 * 1024 + 1}]
        self.assertEqual(self.reject(lambda: self.import_idea(files=[file])).status, 413)
        self.assertEqual(previous, self.state())

    def test_import_route_is_not_a_json_post_or_get_and_missing_service_fails(self):
        self.assertEqual(self.reject(lambda: workflow_get(self.service, "mobile/idea/import", "")).status, 404)
        self.assertEqual(self.reject(lambda: workflow_post(self.service, "mobile/idea/import", self.fields())).status, 404)
        self.assertEqual(self.reject(lambda: workflow_import_idea(None, self.fields(), [])).status, 503)
        self.assertFalse(self.service._wake.is_set())

    def test_unknown_import_lookup_is_readonly_and_does_not_save_or_resend(self):
        fields = self.fields()
        previous = self.state()
        with patch.object(self.service, "_receipt", side_effect=AssertionError("Lookup must not use receipt mutation")), \
                patch.object(self.service, "mobile_idea_import", side_effect=AssertionError("Lookup must not import")):
            result = self.lookup(fields)
        self.assertFalse(result["found"])
        self.assertEqual(result["requestId"], fields["requestId"])
        self.assertEqual(result["source"], self.manifest["source"])
        self.assertEqual(previous, self.state())
        self.assertFalse(list(self.service.attachments_dir.iterdir()))
        self.assertFalse(list(self.service.jobs_dir.iterdir()))
        self.assertFalse(self.service._wake.is_set())

    def test_lookup_returns_original_imported_version_and_current_computer_idea_without_changes(self):
        image, file = self.image()
        self.manifest["images"] = [image]
        fields = self.fields()
        original = self.import_idea(fields, [file])
        self.manifest["source"]["revision"] = 2
        self.manifest["idea"].update(body="第二版", executionDraft="第二版执行稿")
        latest = self.import_idea(files=[file])
        workflow_post(self.service, "mobile/idea/update", {"requestId": str(uuid.uuid4()),
            "id": latest["idea"]["id"], "expectedRevision": 2, "body": "电脑后来编辑"})
        previous = self.state()
        files_before = {path.name: path.read_bytes() for path in self.service.attachments_dir.iterdir()}
        with patch.object(self.service, "_receipt", side_effect=AssertionError("Lookup must not write a receipt")):
            result = self.lookup(fields)
        self.assertTrue(result["found"])
        self.assertTrue(result["duplicate"])
        self.assertEqual(result["imported"], original["imported"])
        self.assertEqual(result["idea"]["revision"], 3)
        self.assertEqual(result["idea"]["body"], "电脑后来编辑")
        self.assertEqual(result["detail"]["record"]["id"], original["detail"]["record"]["id"])
        self.assertEqual(previous, self.state())
        self.assertEqual(files_before, {path.name: path.read_bytes() for path in self.service.attachments_dir.iterdir()})
        self.assertFalse(self.service._wake.is_set())

    def test_lookup_rejects_another_source_or_changed_frozen_text_without_changes(self):
        fields = self.fields()
        self.import_idea(fields)
        previous = self.state()
        for section, field, value in [("source", "clientId", str(uuid.uuid4())), ("source", "ideaId", uuid.uuid4().hex),
                ("source", "revision", 2), ("idea", "executionDraft", "另一执行稿")]:
            changed = copy.deepcopy(self.manifest)
            changed[section][field] = value
            self.reject(lambda: self.lookup(self.fields(changed, fields["requestId"])), "import_lookup_mismatch")
        # Same semantic JSON with different frozen bytes is not the original request.
        self.reject(lambda: self.lookup({**fields, "text": fields["text"] + " "}), "import_lookup_mismatch")
        self.assertEqual(previous, self.state())

    def test_lookup_rechecks_authorization_and_rejects_wrong_receipt_kind(self):
        fields = self.fields()
        self.import_idea(fields)
        previous = self.state()
        calls = []
        def revoke():
            calls.append(True)
            if len(calls) == 2:
                raise WorkflowError("配对已撤销", 401, "session_expired")
        self.reject(lambda: self.lookup(fields, revoke), "session_expired")
        self.assertEqual(previous, self.state())
        with self.service._db() as db:
            db.execute("UPDATE requests SET kind='another_operation' WHERE id=?", (fields["requestId"],))
        previous = self.state()
        self.reject(lambda: self.lookup(fields), "import_lookup_mismatch")
        self.assertEqual(previous, self.state())

    def test_lookup_accepts_only_frozen_manifest_fields_and_rejects_invalid_unicode(self):
        previous = self.state()
        fields = self.fields()
        self.reject(lambda: self.lookup({**fields, "files": []}))
        self.reject(lambda: self.lookup({**fields, "requestId": "invalid"}))
        bad = copy.deepcopy(self.manifest)
        bad["idea"]["body"] = "\ud800"
        self.reject(lambda: self.lookup({**fields, "text": json.dumps(bad)}))
        self.reject(lambda: self.import_idea({**fields, "text": json.dumps(bad)}))
        self.assertEqual(previous, self.state())

    def test_real_bounded_multipart_supports_utf8_manifest_and_actual_image(self):
        image, file = self.image()
        self.manifest["images"] = [image]
        fields = self.fields()
        boundary = "ConsoleMobileHandoffTestBoundary"
        chunks = []
        for name, value in fields.items():
            chunks.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), value.encode("utf-8"), b"\r\n"])
        chunks.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="图片.png"\r\nContent-Type: image/png\r\n\r\n'.encode("utf-8"),
            Path(file.spool).read_bytes(), f"\r\n--{boundary}--\r\n".encode()])
        body = b"".join(chunks)
        headers = Message()
        headers["Content-Length"] = str(len(body))
        headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
        with read_transfer_request(headers, io.BytesIO(body), allowed_fields={"requestId", "text"}) as (actual_fields, actual_files):
            result = self.import_idea(actual_fields, actual_files)
        self.assertEqual(result["idea"]["title"], self.manifest["idea"]["title"])
        self.assertEqual(result["detail"]["attachments"][0]["name"], "图片.png")


class MobilePendingCancellationChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="console-mobile-cancel-isolated-")
        self.root = Path(self.temporary.name)
        self.service = WorkflowService(self.root / "private", models=ForbiddenModels(), projects=[
            {"id": "isolated", "name": "Isolated", "root": str(self.root), "capabilities": ["result_import"]}])
        self.client = str(uuid.uuid4())
        self.state = self.post("open", self.request(clientId=self.client))
        self.sent = self.mutate("send", text="原确认问题，不能重送。", requestedProfile="fast")
        self.dispatch_id = self.sent["job"]["appDispatch"]["id"]
        self.job_id = self.sent["job"]["id"]

    def tearDown(self):
        self.service._dispatch_commit_notifier = None
        self.service.shutdown()
        self.temporary.cleanup()

    @staticmethod
    def request(**fields):
        return {"requestId": str(uuid.uuid4()), **fields}

    def post(self, action, body, authorize=None):
        return workflow_post(self.service, "mobile/dialogue/" + action, body,
                             prefix="/api/phone/workflow", authorize=authorize)

    def mutate(self, action, **fields):
        session = self.state["session"]
        body = self.request(clientId=self.client, sessionId=session["id"], expectedRevision=session["revision"])
        if action in {"send", "draft"}:
            body.update(text="尚未发送草稿", attachmentIds=[], requestedProfile="fast")
        body.update(fields)
        self.state = self.post(action, body)
        return self.state

    def cancel_body(self, **fields):
        session = self.state["session"]
        return self.request(clientId=self.client, sessionId=session["id"], recordId=session["recordId"],
                            expectedRevision=session["revision"], dispatchId=self.dispatch_id, **fields)

    def snapshot(self):
        with self.service._db() as db:
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            return {t: [dict(r) for r in db.execute(f'SELECT * FROM "{t}" ORDER BY rowid')] for t in tables}

    def reject(self, body, code=None, authorize=None):
        before = self.snapshot()
        with self.assertRaises(WorkflowError) as caught:
            self.post("cancel-pending", body, authorize)
        if code:
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.snapshot(), before)
        return caught.exception

    def test_cancel_only_original_pending_preserves_all_sources_draft_profile_and_other_queue(self):
        other_client = str(uuid.uuid4())
        other = self.post("open", self.request(clientId=other_client))
        s = other["session"]
        other = self.post("send", self.request(clientId=other_client, sessionId=s["id"], expectedRevision=s["revision"],
                         text="另一讨论仍保留", attachmentIds=[], requestedProfile="fast"))
        spool = self.root / "preserved.png"
        Image.new("RGB", (2, 2), "blue").save(spool, "PNG")
        s = self.state["session"]
        self.state = self.service.mobile_dialogue_upload(self.request(recordId=s["recordId"], text=json.dumps({
            "clientId": self.client, "sessionId": s["id"], "expectedRevision": s["revision"]})),
            [IncomingFile(spool, 0, spool.stat().st_size, "原附件.png", "image/png")])
        attachment = self.state["uploadedAttachmentIds"][0]
        self.mutate("draft", text="下一轮草稿🧩", attachmentIds=[attachment], requestedProfile="pro")
        session_before = copy.deepcopy(self.state["session"])
        files_before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.service.attachments_dir.iterdir()}
        before = self.snapshot()
        test = self
        class NoDispatch:
            def notify_committed(self, identifiers):
                test.fail("cancellation must never submit another request")
            def notify_released(self, identifiers):
                test.fail("an unclaimed pending row must not be reported as an active release")
        self.service._dispatch_commit_notifier = NoDispatch()
        result = self.post("cancel-pending", self.cancel_body())
        after = self.snapshot()
        self.assertFalse(result["duplicate"])
        self.assertEqual(result["cancellation"], {"clientId": self.client, "sessionId": session_before["id"], "recordId": session_before["recordId"],
            "expectedRevision": session_before["revision"],
            "dispatchId": self.dispatch_id, "jobId": self.job_id, "status": "failed", "reason": "cancelled_before_send", "unsent": True})
        self.assertEqual(result["session"], session_before)
        self.assertEqual(result["resultStatus"], "failed")
        self.assertEqual(files_before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.service.attachments_dir.iterdir()})
        for table in set(before) - {"settings", "requests", "jobs", "idea_dispatches"}:
            self.assertEqual(before[table], after[table], table)
        self.assertEqual([r for r in before["settings"] if r["key"] != "revision"],
                         [r for r in after["settings"] if r["key"] != "revision"])
        self.assertEqual(after["requests"][:-1], before["requests"])
        self.assertEqual(after["requests"][-1]["kind"], "mobile_dialogue_cancel_pending")
        for table, identifier in (("jobs", self.job_id), ("idea_dispatches", self.dispatch_id)):
            for old, new in zip(before[table], after[table]):
                if old["id"] == identifier:
                    self.assertEqual(new["status"], "failed")
                    self.assertIn("未发送", new["error"])
                    self.assertEqual({k: v for k, v in old.items() if k not in {"status", "error", "updated_at"}},
                                     {k: v for k, v in new.items() if k not in {"status", "error", "updated_at"}})
                else:
                    self.assertEqual(old, new)
        self.assertEqual(other["job"]["appDispatch"]["status"], "pending")
        self.assertFalse(self.service._wake.is_set())

    def test_can_cancel_projection_is_readonly_and_false_for_old_or_attempted_identity(self):
        before = self.snapshot()
        current = workflow_get(self.service, "mobile/dialogue", "clientId=" + self.client)
        job = next(j for j in current["detail"]["jobs"] if j["id"] == self.job_id)
        self.assertIs(job["appDispatch"]["canCancelPending"], True)
        self.assertEqual(current["cancellationReceipts"], [])
        self.assertEqual(self.snapshot(), before)
        with self.service._db() as db:
            self.service._set_setting(db, "console-chat-relay:attempt:" + self.dispatch_id, {})
        before = self.snapshot()
        current = workflow_get(self.service, "mobile/dialogue", "clientId=" + self.client)
        self.assertIs(current["detail"]["jobs"][-1]["appDispatch"]["canCancelPending"], False)
        self.assertEqual(self.snapshot(), before)
        old_session = self.state["session"]["id"]
        self.mutate("clear")
        old = self.service._mobile_state(self.client, "/api/phone/workflow", old_session)
        self.assertFalse(old["session"]["isCurrent"])
        self.assertIs(old["detail"]["jobs"][-1]["appDispatch"]["canCancelPending"], False)
        self.assertEqual(old["cancellationReceipts"], [])

    def test_cancellation_receipt_readback_binds_nonce_original_revision_and_current_scope(self):
        body = self.cancel_body()
        result = self.post("cancel-pending", body)
        expected = {"requestId": body["requestId"], **result["cancellation"]}
        self.assertEqual(result["cancellationReceipts"], [expected])
        self.assertIs(result["detail"]["jobs"][-1]["appDispatch"]["canCancelPending"], False)
        self.mutate("draft", text="不同版本的新草稿", requestedProfile="pro")
        current = workflow_get(self.service, "mobile/dialogue", "clientId=" + self.client)
        self.assertEqual(current["cancellationReceipts"], [expected])
        self.assertEqual(current["cancellationReceipts"][0]["expectedRevision"], body["expectedRevision"])
        self.assertNotEqual(current["session"]["revision"], expected["expectedRevision"])
        self.assertEqual(current["session"]["draft"], self.state["session"]["draft"])
        self.mutate("clear")
        current = workflow_get(self.service, "mobile/dialogue", "clientId=" + self.client)
        self.assertEqual(current["cancellationReceipts"], [])
        self.reject(body, "dialogue_changed")

    def test_cancellation_readback_rejects_forged_nonce_scope_reason_or_job_identity(self):
        body = self.cancel_body()
        result = self.post("cancel-pending", body)
        correct = result["cancellation"]
        for change in ({"clientId": str(uuid.uuid4())}, {"sessionId": uuid.uuid4().hex}, {"recordId": uuid.uuid4().hex}, {"dispatchId": uuid.uuid4().hex},
                       {"jobId": uuid.uuid4().hex}, {"reason": "some_failure"}, {"unsent": False},
                       {"expectedRevision": body["expectedRevision"] + 1}):
            with self.subTest(change=change):
                saved = {**correct, **change}
                with self.service._db() as db:
                    db.execute("UPDATE requests SET response=? WHERE id=?", (json.dumps(saved), body["requestId"]))
                before = self.snapshot()
                current = workflow_get(self.service, "mobile/dialogue", "clientId=" + self.client)
                self.assertEqual(current["cancellationReceipts"], [])
                self.assertEqual(self.snapshot(), before)
        with self.service._db() as db:
            db.execute("UPDATE requests SET response=?,fingerprint='forged' WHERE id=?", (json.dumps(correct), body["requestId"]))
        current = workflow_get(self.service, "mobile/dialogue", "clientId=" + self.client)
        self.assertEqual(current["cancellationReceipts"], [])

    def test_cancellation_readback_is_bounded_and_requires_original_pair_still_failed(self):
        body = self.cancel_body()
        result = self.post("cancel-pending", body)
        saved = result["cancellation"]
        with self.service._db() as db:
            for _ in range(25):
                candidate = {**body, "requestId": str(uuid.uuid4())}
                db.execute("INSERT INTO requests VALUES (?,?,?,?)", (candidate["requestId"], "mobile_dialogue_cancel_pending",
                    hashlib.sha256(json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                    json.dumps(saved)))
        current = workflow_get(self.service, "mobile/dialogue", "clientId=" + self.client)
        self.assertEqual(len(current["cancellationReceipts"]), 20)
        for table, identifier in (("jobs", self.job_id), ("idea_dispatches", self.dispatch_id)):
            with self.service._db() as db:
                db.execute(f'UPDATE "{table}" SET status=? WHERE id=?', ("waiting", identifier))
            current = workflow_get(self.service, "mobile/dialogue", "clientId=" + self.client)
            self.assertEqual(current["cancellationReceipts"], [])
            with self.service._db() as db:
                db.execute(f'UPDATE "{table}" SET status=? WHERE id=?', ("failed", identifier))

    def test_cancel_notifies_only_original_subscribed_session_after_durable_commit(self):
        session = self.state["session"]
        key = (self.client, session["id"])
        other_client = str(uuid.uuid4())
        other = self.post("open", self.request(clientId=other_client))["session"]
        hub = self.service._mobile_event_hub()
        token, _ = hub.subscribe(key)
        other_token, _ = hub.subscribe((other_client, other["id"]))
        original_notify, notices = hub.notify, []
        body = self.cancel_body()
        def notify(keys):
            keys = tuple(keys)
            if keys:
                # A separate reader sees old rows until the transaction commits.
                with closing(sqlite3.connect((self.service.data_dir / "workflow.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)) as db:
                    self.assertEqual(db.execute("SELECT status FROM jobs WHERE id=?", (self.job_id,)).fetchone()[0], "failed")
                    self.assertEqual(db.execute("SELECT status FROM idea_dispatches WHERE id=?", (self.dispatch_id,)).fetchone()[0], "failed")
                    self.assertIsNotNone(db.execute("SELECT id FROM requests WHERE id=?", (body["requestId"],)).fetchone())
                notices.extend(keys)
            return original_notify(keys)
        with patch.object(hub, "notify", notify):
            self.post("cancel-pending", body)
        self.assertEqual(notices, [key])
        event = self.service._mobile_event_read(key)
        self.assertEqual(event["jobId"], self.job_id)
        self.assertEqual(event["status"], "failed")
        hub.close(token)
        hub.close(other_token)

    def test_cancel_rollback_has_no_subscriber_result_notification(self):
        key = (self.client, self.state["session"]["id"])
        hub = self.service._mobile_event_hub()
        token, _ = hub.subscribe(key)
        notices = []
        original_receipt = self.service._receipt
        def fail(db, kind, body, response=None):
            if kind == "mobile_dialogue_cancel_pending" and response is not None:
                raise WorkflowError("Isolated cancellation rollback", 503)
            return original_receipt(db, kind, body, response)
        def notify(keys):
            notices.extend(keys)
        with patch.object(self.service, "_receipt", fail), patch.object(hub, "notify", notify):
            self.reject(self.cancel_body())
        self.assertEqual(notices, [])
        event = self.service._mobile_event_read(key)
        self.assertEqual(event["jobId"], self.job_id)
        self.assertEqual(event["status"], "waiting")
        hub.close(token)

    def test_cancel_same_nonce_is_idempotent_and_returns_newer_current_draft(self):
        body = self.cancel_body()
        first = self.post("cancel-pending", body)
        before = self.snapshot()
        duplicate = self.post("cancel-pending", body)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["cancellation"], first["cancellation"])
        self.assertEqual(self.snapshot(), before)
        self.mutate("draft", text="取消之后另存的草稿", requestedProfile="high")
        before = self.snapshot()
        duplicate = self.post("cancel-pending", body)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["session"], self.state["session"])
        self.assertEqual(self.snapshot(), before)
        self.reject({**body, "dispatchId": uuid.uuid4().hex})

    def test_cancel_checks_exact_current_client_session_record_and_revision(self):
        body = self.cancel_body()
        for fields in ({"clientId": str(uuid.uuid4())}, {"sessionId": uuid.uuid4().hex},
                       {"recordId": uuid.uuid4().hex}, {"expectedRevision": body["expectedRevision"] - 1},
                       {"expectedRevision": True}):
            with self.subTest(fields=fields):
                self.reject({**body, **fields})
        self.mutate("clear")
        self.reject(body, "dialogue_changed")

    def test_cancel_schema_is_exact_and_other_request_kinds_cannot_be_reused(self):
        body = self.cancel_body()
        for key in body:
            self.reject({k: v for k, v in body.items() if k != key})
        for extra in ("claimToken", "force", "send", "requestedProfile", "text"):
            self.reject({**body, extra: True})
        with self.service._db() as db:
            old_id = db.execute("SELECT id FROM requests WHERE kind='mobile_dialogue_send'").fetchone()[0]
        self.reject({**body, "requestId": old_id})

    def test_cancel_refuses_claimed_waiting_review_completed_and_failed_states(self):
        body = self.cancel_body()
        for status in ("claimed", "waiting", "needs_review", "completed", "failed", "unknown"):
            with self.subTest(status=status):
                with self.service._db() as db:
                    db.execute("UPDATE idea_dispatches SET status=? WHERE id=?", (status, self.dispatch_id))
                self.reject(body, "cancel_requires_unclaimed_pending")

    def test_cancel_refuses_actual_claim_and_keeps_claim_evidence(self):
        body = self.cancel_body()
        self.service.incubator_claim(self.request(id=self.dispatch_id))
        self.reject(body, "cancel_requires_unclaimed_pending")

    def test_cancel_refuses_any_attempt_tombstone_even_without_send_intent(self):
        body = self.cancel_body()
        for value in (None, {}, {"phase": "prepared_requested", "sendIntentAt": None},
                      {"phase": "needs_review", "sendIntentAt": "2026-10-05T14:00:00Z"}):
            with self.subTest(value=value):
                with self.service._db() as db:
                    self.service._set_setting(db, "console-chat-relay:attempt:" + self.dispatch_id, value)
                self.reject(body, "cancel_requires_unclaimed_pending")

    def test_cancel_refuses_claim_source_result_and_prior_claim_receipt(self):
        body = self.cancel_body()
        variants = {"claim_token": uuid.uuid4().hex, "target_thread_id": str(uuid.uuid4()), "result": json.dumps({"unknown": True})}
        with self.service._db() as db:
            original = dict(self.service._dispatch(db, self.dispatch_id))
        for key, value in variants.items():
            with self.subTest(key=key):
                with self.service._db() as db:
                    db.execute(f'UPDATE idea_dispatches SET "{key}"=? WHERE id=?', (value, self.dispatch_id))
                self.reject(body, "cancel_requires_unclaimed_pending")
                with self.service._db() as db:
                    db.execute(f'UPDATE idea_dispatches SET "{key}"=? WHERE id=?', (original[key], self.dispatch_id))
        with self.service._db() as db:
            db.execute("INSERT INTO requests VALUES (?,?,?,?)", (str(uuid.uuid4()), "incubator_claim", "fixture",
                       json.dumps({"dispatchId": self.dispatch_id})))
        self.reject(body, "cancel_requires_unclaimed_pending")

    def test_cancel_refuses_queued_running_nonempty_job_result_or_unmatched_mobile_binding(self):
        body = self.cancel_body()
        for status in ("queued", "running", "succeeded", "failed"):
            with self.subTest(status=status):
                with self.service._db() as db:
                    db.execute("UPDATE jobs SET status=? WHERE id=?", (status, self.job_id))
                self.reject(body, "cancel_requires_unclaimed_pending")
        with self.service._db() as db:
            db.execute("UPDATE jobs SET status='waiting',result=? WHERE id=?", (json.dumps({"sent": True}), self.job_id))
        self.reject(body, "cancel_requires_unclaimed_pending")
        with self.service._db() as db:
            payload = json.loads(db.execute("SELECT payload FROM jobs WHERE id=?", (self.job_id,)).fetchone()[0])
            payload["mobileDialogue"]["clientId"] = str(uuid.uuid4())
            db.execute("UPDATE jobs SET result='{}',payload=? WHERE id=?", (json.dumps(payload), self.job_id))
        self.reject(body, "cancel_context_mismatch")

    def test_cancel_refuses_other_active_work_on_original_record(self):
        body = self.cancel_body()
        with self.service._db() as db:
            job = dict(db.execute("SELECT * FROM jobs WHERE id=?", (self.job_id,)).fetchone())
            job.update(id=uuid.uuid4().hex, request_id=str(uuid.uuid4()), kind="execute", payload="{}", status="queued")
            columns = list(job)
            db.execute('INSERT INTO jobs (' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')', tuple(job.values()))
        for status in ("queued", "running"):
            with self.subTest(status=status):
                with self.service._db() as db:
                    db.execute("UPDATE jobs SET status=? WHERE id=?", (status, job["id"]))
                self.reject(body, "cancel_requires_unclaimed_pending")
        with self.service._db() as db:
            db.execute("UPDATE jobs SET status='failed' WHERE id=?", (job["id"],))
            row = dict(self.service._dispatch(db, self.dispatch_id))
            row.update(id=uuid.uuid4().hex, request_id=str(uuid.uuid4()), status="claimed", claim_token=uuid.uuid4().hex)
            columns = list(row)
            db.execute('INSERT INTO idea_dispatches (' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')', tuple(row.values()))
        self.reject(body, "cancel_requires_unclaimed_pending")

    def test_cancel_requires_original_mobile_send_receipt(self):
        body = self.cancel_body()
        with self.service._db() as db:
            request_id = db.execute("SELECT request_id FROM idea_dispatches WHERE id=?", (self.dispatch_id,)).fetchone()[0]
            db.execute("UPDATE requests SET response=? WHERE id=?", (json.dumps({"jobId": self.job_id, "sessionId": uuid.uuid4().hex}), request_id))
        self.reject(body, "cancel_context_mismatch")

    def test_cancel_accepts_exact_legacy_two_field_send_receipt_without_restoring_source(self):
        with self.service._db() as db:
            request_id = db.execute("SELECT request_id FROM jobs WHERE id=?", (self.job_id,)).fetchone()[0]
            db.execute("UPDATE requests SET response=? WHERE id=?", (json.dumps({"sessionId": self.state["session"]["id"],
                "jobId": self.job_id}), request_id))
            db.execute("DELETE FROM mobile_message_sources WHERE job_id=?", (self.job_id,))
        before = self.snapshot()
        current = workflow_get(self.service, "mobile/dialogue", "clientId=" + self.client)
        self.assertIs(current["detail"]["jobs"][-1]["appDispatch"]["canCancelPending"], True)
        self.assertEqual(self.snapshot(), before)
        result = self.post("cancel-pending", self.cancel_body())
        self.assertIs(result["cancellation"]["unsent"], True)
        self.assertEqual(self.snapshot()["mobile_message_sources"], [])

    def test_cancel_rejects_changed_new_source_message_id_and_readonly_hint_cannot_repair(self):
        with self.service._db() as db:
            request_id = db.execute("SELECT request_id FROM jobs WHERE id=?", (self.job_id,)).fetchone()[0]
            original = json.loads(db.execute("SELECT response FROM requests WHERE id=?", (request_id,)).fetchone()[0])
            source = dict(db.execute("SELECT * FROM mobile_message_sources WHERE job_id=?", (self.job_id,)).fetchone())
        for wrong in (uuid.uuid4().hex, None, [source["message_id"]]):
            with self.subTest(wrong=wrong):
                with self.service._db() as db:
                    db.execute("UPDATE requests SET response=? WHERE id=?", (json.dumps({**original, "sourceMessageId": wrong}), request_id))
                before = self.snapshot()
                current = workflow_get(self.service, "mobile/dialogue", "clientId=" + self.client)
                self.assertIs(current["detail"]["jobs"][-1]["appDispatch"]["canCancelPending"], False)
                self.assertEqual(self.snapshot(), before)
                self.reject(self.cancel_body(), "cancel_context_mismatch")
        with self.service._db() as db:
            db.execute("UPDATE requests SET response=? WHERE id=?", (json.dumps(original), request_id))
            db.execute("DELETE FROM mobile_message_sources WHERE job_id=?", (self.job_id,))
        before = self.snapshot()
        with patch.object(self.service, "_guide_user_source", side_effect=AssertionError("cancel hint cannot restore provenance")):
            current = workflow_get(self.service, "mobile/dialogue", "clientId=" + self.client)
            self.assertIs(current["detail"]["jobs"][-1]["appDispatch"]["canCancelPending"], False)
            self.reject(self.cancel_body(), "cancel_context_mismatch")
        self.assertEqual(self.snapshot(), before)

    def test_cancel_new_source_checks_immutable_scope_request_job_text_and_attachments(self):
        with self.service._db() as db:
            source = dict(db.execute("SELECT * FROM mobile_message_sources WHERE job_id=?", (self.job_id,)).fetchone())
            message = dict(db.execute("SELECT * FROM messages WHERE id=?", (source["message_id"],)).fetchone())
            job = dict(db.execute("SELECT * FROM jobs WHERE id=?", (self.job_id,)).fetchone())
            dispatch = dict(db.execute("SELECT * FROM idea_dispatches WHERE id=?", (self.dispatch_id,)).fetchone())
        changes = [("mobile_message_sources", "message_id", source, key, value) for key, value in (
            ("client_id", str(uuid.uuid4())), ("session_id", uuid.uuid4().hex), ("record_id", uuid.uuid4().hex),
            ("request_id", str(uuid.uuid4())), ("job_id", uuid.uuid4().hex), ("text_sha256", "f" * 64),
            ("attachment_ids", json.dumps([uuid.uuid4().hex])), ("created_at", "2026-01-01T00:00:00+00:00"))]
        changes += [("messages", "id", message, key, value) for key, value in (
            ("text", "篡改正文"), ("attachment_ids", json.dumps([uuid.uuid4().hex])), ("role", "assistant"))]
        changes += [("jobs", "id", job, "attempt", 2), ("jobs", "id", job, "parent_id", uuid.uuid4().hex),
            ("idea_dispatches", "id", dispatch, "snapshot", json.dumps({**json.loads(dispatch["snapshot"]), "attachmentIds": [uuid.uuid4().hex]})),
            ("jobs", "id", job, "payload", json.dumps({**json.loads(job["payload"]),
                "appFrozen": {**json.loads(job["payload"])["appFrozen"], "images": [{"id": uuid.uuid4().hex}]}}))]
        for table, identity, original, field, value in changes:
            with self.subTest(table=table, field=field):
                with self.service._db() as db:
                    db.execute("UPDATE " + table + " SET " + field + "=? WHERE " + identity + "=?", (value, original[identity]))
                before = self.snapshot()
                current = workflow_get(self.service, "mobile/dialogue", "clientId=" + self.client)
                self.assertIs(current["detail"]["jobs"][-1]["appDispatch"]["canCancelPending"], False)
                self.assertEqual(self.snapshot(), before)
                self.reject(self.cancel_body(), "cancel_context_mismatch")
                with self.service._db() as db:
                    db.execute("UPDATE " + table + " SET " + field + "=? WHERE " + identity + "=?", (original[field], original[identity]))

    def test_cancel_authorization_recheck_rolls_back_both_failures_and_receipt(self):
        calls = []
        def revoke():
            calls.append(True)
            if len(calls) == 2:
                raise WorkflowError("Isolated authorization revoked", 403)
        self.reject(self.cancel_body(), authorize=revoke)
        self.assertEqual(len(calls), 2)

    def test_cancel_late_receipt_failure_rolls_back_all_state(self):
        original = self.service._receipt
        def fail(db, kind, body, response=None):
            if kind == "mobile_dialogue_cancel_pending" and response is not None:
                raise WorkflowError("Isolated receipt storage failure", 503)
            return original(db, kind, body, response)
        with patch.object(self.service, "_receipt", fail):
            self.reject(self.cancel_body())


class MobileHandoffGatewayChecks(unittest.TestCase):
    def setUp(self):
        # Reuse the existing disposable gateway fixture, not a production server.
        path = Path(__file__).with_name("check-workflow-http.py")
        spec = importlib.util.spec_from_file_location("mobile_handoff_http_fixture", path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.fixture = self.module.WorkflowHttpChecks()
        self.fixture.setUp()
        self.manifest = {"format": "codex-console-idea", "version": 1,
            "source": {"clientId": str(uuid.uuid4()), "ideaId": uuid.uuid4().hex, "revision": 1},
            "idea": {"title": "真实配对导入测试", "body": "仅保存", "executionDraft": "未确认执行稿",
                "archived": False, "keyPoints": []}, "images": [{"id": uuid.uuid4().hex, "name": "配对图片.png",
                    "mimeType": "image/png", "size": len(self.fixture.png), "sha256": hashlib.sha256(self.fixture.png).hexdigest()}]}
        self.request_id = str(uuid.uuid4())
        self.raw, self.content_type = self.module.multipart({"requestId": self.request_id,
            "text": json.dumps(self.manifest, ensure_ascii=False)}, [("配对图片.png", "image/png", self.fixture.png)])

    def tearDown(self):
        self.fixture.tearDown()

    def send(self, **headers):
        return self.fixture.request("/api/phone/workflow/mobile/idea/import", "POST", raw=self.raw,
            headers={"Content-Type": self.content_type, **headers})

    def test_import_uses_existing_pairing_and_exact_own_origin_without_cors_extension(self):
        self.assertEqual(self.send()[0], 401)
        self.fixture.pair()
        denied, _, headers = self.send(Origin="https://tx74666.github.io", **{"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(denied, 403)
        self.assertFalse(any(name.lower() == "access-control-allow-origin" for name, _ in headers))
        status, result, _ = self.send()
        self.assertEqual(status, 200, result)
        self.assertEqual(result["requestId"], self.request_id)
        self.assertEqual(result["imported"]["source"], self.manifest["source"])
        self.assertEqual(len(result["detail"]["attachments"]), 1)
        self.assertEqual(result["detail"]["jobs"], [])
        self.assertEqual(self.fixture.workflow.incubator_dispatches()["dispatches"], [])
        self.assertEqual(self.fixture.request("/api/phone/workflow/mobile/idea/import")[0], 404)
        denied, _, _ = self.fixture.request("/api/phone/workflow/mobile/idea/import", "POST", {"requestId": self.request_id})
        self.assertEqual(denied, 415)
        self.assertFalse(self.fixture.marker.exists())

    def test_readonly_plan_sync_session_cannot_import_saved_ideas(self):
        code = self.fixture.companion.state(False)["pairingCode"]
        token = self.fixture.companion.pair(code, "127.0.0.1", scope="plan-sync")
        self.assertEqual(self.fixture.companion.session(token, "127.0.0.1", scope="plan-sync")["scope"], "plan-sync")
        status, result, _ = self.fixture.request("/api/phone/workflow/mobile/idea/import", "POST", raw=self.raw,
            cookie=self.module.phone.COOKIE_NAME + "=" + token, headers={"Content-Type": self.content_type})
        self.assertEqual(status, 401, result)
        with self.fixture.workflow._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM ideas").fetchone()[0], 0)

    def test_cancel_pending_requires_existing_pairing_and_own_origin(self):
        endpoint = "/api/phone/workflow/mobile/dialogue/cancel-pending"
        self.assertEqual(self.fixture.request(endpoint, "POST", {})[0], 401)
        self.fixture.pair()
        client = str(uuid.uuid4())
        s = self.fixture.workflow.mobile_dialogue_open({"requestId": str(uuid.uuid4()), "clientId": client})["session"]
        sent = self.fixture.workflow.mobile_dialogue_send({"requestId": str(uuid.uuid4()), "clientId": client,
            "sessionId": s["id"], "expectedRevision": s["revision"], "text": "Isolated unsent request", "attachmentIds": [], "requestedProfile": "fast"})
        s = sent["session"]
        body = {"requestId": str(uuid.uuid4()), "clientId": client, "sessionId": s["id"], "recordId": s["recordId"],
                "expectedRevision": s["revision"], "dispatchId": sent["job"]["appDispatch"]["id"]}
        status, _, headers = self.fixture.request(endpoint, "POST", body,
            headers={"Origin": "https://tx74666.github.io", "Sec-Fetch-Site": "cross-site"})
        self.assertEqual(status, 403)
        self.assertFalse(any(k.lower() == "access-control-allow-origin" for k, _ in headers))
        code = self.fixture.companion.renew_pairing()["pairingCode"]
        token = self.fixture.companion.pair(code, "127.0.0.1", scope="plan-sync")
        status, denied, _ = self.fixture.request(endpoint, "POST", body,
            cookie=self.module.phone.COOKIE_NAME + "=" + token)
        self.assertEqual(status, 401, denied)
        status, cancelled, _ = self.fixture.request(endpoint, "POST", body)
        self.assertEqual(status, 200, cancelled)
        self.assertEqual(cancelled["session"], s)
        self.assertTrue(cancelled["cancellation"]["unsent"])
        self.assertEqual(cancelled["resultStatus"], "failed")
        status, duplicate, _ = self.fixture.request(endpoint, "POST", body)
        self.assertEqual(status, 200, duplicate)
        self.assertTrue(duplicate["duplicate"])
        self.assertFalse(self.fixture.marker.exists())

    def test_status_is_paired_same_origin_and_readonly_for_missing_or_found_imports(self):
        fields = {"requestId": self.request_id, "text": json.dumps(self.manifest, ensure_ascii=False)}
        endpoint = "/api/phone/workflow/mobile/idea/import-status"
        self.assertEqual(self.fixture.request(endpoint, "POST", fields)[0], 401)
        self.fixture.pair()
        status, _, headers = self.fixture.request(endpoint, "POST", fields,
            {"Origin": "https://tx74666.github.io", "Sec-Fetch-Site": "cross-site"})
        self.assertEqual(status, 403)
        self.assertFalse(any(name.lower() == "access-control-allow-origin" for name, _ in headers))
        def snapshot():
            with self.fixture.workflow._db() as db:
                tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
                return {table: [tuple(row) for row in db.execute("SELECT * FROM " + table + " ORDER BY rowid")] for table in tables}
        before = snapshot()
        status, missing, _ = self.fixture.request(endpoint, "POST", fields)
        self.assertEqual(status, 200, missing)
        self.assertIs(missing["found"], False)
        self.assertEqual(snapshot(), before)
        status, imported, _ = self.send()
        self.assertEqual(status, 200, imported)
        before = snapshot()
        status, found, _ = self.fixture.request(endpoint, "POST", fields)
        self.assertEqual(status, 200, found)
        self.assertIs(found["found"], True)
        self.assertEqual(found["imported"], imported["imported"])
        self.assertEqual(found["idea"], imported["idea"])
        self.assertEqual(snapshot(), before)
        self.assertFalse(self.fixture.marker.exists())

    def test_status_bounded_wrapper_can_read_a_legal_highly_escaped_manifest(self):
        self.fixture.pair()
        self.manifest["idea"].update(body="\\" * 19000, executionDraft="\\" * 19000)
        manifest_text = json.dumps(self.manifest, ensure_ascii=False)
        self.assertLessEqual(len(manifest_text.encode("utf-8")), 80000)
        fields = {"requestId": self.request_id, "text": manifest_text}
        wrapped = json.dumps(fields).encode("utf-8")
        self.assertGreater(len(wrapped), 128 * 1024)
        self.assertLessEqual(len(wrapped), 192 * 1024)
        self.raw, self.content_type = self.module.multipart(fields, [("配对图片.png", "image/png", self.fixture.png)])
        status, imported, _ = self.send()
        self.assertEqual(status, 200, imported)
        with self.fixture.workflow._db() as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            before = {table: [tuple(row) for row in db.execute("SELECT * FROM " + table + " ORDER BY rowid")] for table in tables}
        status, found, _ = self.fixture.request("/api/phone/workflow/mobile/idea/import-status", "POST", fields)
        self.assertEqual(status, 200, found)
        self.assertIs(found["found"], True)
        self.assertEqual(found["imported"], imported["imported"])
        self.assertEqual(found["idea"]["body"], self.manifest["idea"]["body"])
        with self.fixture.workflow._db() as db:
            after = {table: [tuple(row) for row in db.execute("SELECT * FROM " + table + " ORDER BY rowid")] for table in tables}
        self.assertEqual(after, before)
        # Other routes keep their original request limit; the inner manifest
        # remains bounded even on the read-only route with a larger wrapper.
        self.assertEqual(self.fixture.request("/api/phone/workflow/mobile/dialogue/open", "POST", fields)[0], 413)
        oversized = {**fields, "text": manifest_text + " " * (80001 - len(manifest_text.encode("utf-8")))}
        self.assertLessEqual(len(json.dumps(oversized).encode("utf-8")), 192 * 1024)
        self.assertEqual(self.fixture.request("/api/phone/workflow/mobile/idea/import-status", "POST", oversized)[0], 413)


if __name__ == "__main__":
    unittest.main()
