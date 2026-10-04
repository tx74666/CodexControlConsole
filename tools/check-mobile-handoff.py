#!/usr/bin/env python3
"""Exercise atomic saved-idea imports using only isolated databases and files."""
import copy
from email.message import Message
import hashlib
import importlib.util
import io
import json
from pathlib import Path
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
        manifest["idea"]["keyPoints"][0]["text"] = "x" * 2001
        cases.append(manifest)
        for manifest in cases:
            with self.subTest(manifest=manifest):
                self.reject(lambda: self.import_idea(self.fields(manifest)))
                self.assertEqual(previous, self.state())
        fields = self.fields()
        fields["text"] = '{"format":"one","format":"two"}'
        self.reject(lambda: self.import_idea(fields))
        self.assertEqual(previous, self.state())

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
