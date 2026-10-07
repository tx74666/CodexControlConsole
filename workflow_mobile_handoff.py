"""Preserve phone sources through explicit imports and cancellation before send."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import uuid

from transfer_store import IncomingFile, TransferError, _filename, _image, _safe_child


MAX_MANIFEST_BYTES = 80_000
MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
CANCEL_RECEIPT_FIELDS = {"clientId", "sessionId", "recordId", "expectedRevision", "dispatchId", "jobId", "status", "reason", "unsent"}


def _api():
    import workflow_service
    return workflow_service


def _object(value, fields):
    if not isinstance(value, dict) or set(value) != fields:
        raise _api().WorkflowError("手机想法导入内容无效。")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _api().WorkflowError("手机想法导入包含重复字段。")
        result[key] = value
    return result


def _manifest(text):
    api = _api()
    if not isinstance(text, str):
        raise api.WorkflowError("请提供手机想法导入内容。")
    try:
        if len(text.encode("utf-8")) > MAX_MANIFEST_BYTES:
            raise api.WorkflowError("手机想法导入文字超过 80 KB。", 413)
        value = json.loads(text, object_pairs_hook=_unique_object)
    except api.WorkflowError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise api.WorkflowError("手机想法导入格式无效。") from None
    _object(value, {"format", "version", "source", "idea", "images"})
    if value["format"] != "codex-console-idea" or type(value["version"]) is not int or value["version"] != 1:
        raise api.WorkflowError("手机想法导入版本不支持。")
    source = value["source"]
    _object(source, {"clientId", "ideaId", "revision"})
    try:
        client_id = str(uuid.UUID(source["clientId"]))
    except (ValueError, TypeError, AttributeError):
        raise api.WorkflowError("手机想法来源无效。") from None
    api._id(source["ideaId"])
    if type(source["revision"]) is not int or not 1 <= source["revision"] <= 9007199254740991:
        raise api.WorkflowError("手机想法来源版本无效。")
    source = {**source, "clientId": client_id}
    idea = value["idea"]
    _object(idea, {"title", "body", "executionDraft", "archived", "keyPoints"})
    if not api._text(idea["title"], 160).strip():
        raise api.WorkflowError("手机想法标题不能为空。")
    api._text(idea["body"])
    api._text(idea["executionDraft"])
    if type(idea["archived"]) is not bool:
        raise api.WorkflowError("手机想法归档状态无效。")
    points = idea["keyPoints"]
    if not isinstance(points, list) or len(points) > 100:
        raise api.WorkflowError("长期要点最多 100 条。")
    seen = set()
    for point in points:
        _object(point, {"id", "text", "kind"})
        identifier = api._id(point["id"])
        if identifier in seen or not api._text(point["text"]).strip():
            raise api.WorkflowError("手机想法要点为空或重复。")
        if not isinstance(point["kind"], str) or point["kind"] not in {"suggestion", "decision"}:
            raise api.WorkflowError("请区分建议和已保存决定。")
        seen.add(identifier)
    images = value["images"]
    if not isinstance(images, list) or len(images) > 4:
        raise api.WorkflowError("手机想法最多导入 4 张图片。", 413)
    seen = set()
    for image in images:
        _object(image, {"id", "name", "mimeType", "size", "sha256"})
        identifier = api._id(image["id"])
        try:
            name = _filename(image["name"])
        except TransferError as error:
            raise api.WorkflowError(str(error), error.status) from error
        if identifier in seen or name != image["name"]:
            raise api.WorkflowError("手机想法图片名称或标识无效。")
        if not isinstance(image["mimeType"], str) or image["mimeType"] not in IMAGE_MIMES:
            raise api.WorkflowError("仅支持 JPEG、PNG、GIF 或 WebP 图片。", 415)
        if type(image["size"]) is not int or not 0 < image["size"] <= MAX_IMAGE_BYTES:
            raise api.WorkflowError("每张导入图片不能超过 8 MB。", 413)
        if not isinstance(image["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", image["sha256"]):
            raise api.WorkflowError("手机想法图片校验值无效。")
        seen.add(identifier)
    return {**value, "source": source}


def _digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(64 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _source_hash(manifest):
    try:
        return hashlib.sha256(_api()._json(manifest).encode("utf-8")).hexdigest()
    except UnicodeError:
        raise _api().WorkflowError("手机想法文字包含无效编码，原内容未改动。") from None


def _nonce_body(fields, manifest):
    return {**fields, "files": [{key: image[key] for key in ("name", "mimeType", "size", "sha256")} for image in manifest["images"]]}


class MobileHandoffMixin:
    def _mobile_cancel_pending_candidate(self, db, session, dispatch_id, *, cancelled=False):
        """One shared read predicate for hints and the locked cancellation."""
        api = _api()
        from workflow_chat_relay import _prior_dispatch_evidence

        client_id, record_id = session["clientId"], session["recordId"]
        row = self._dispatch(db, dispatch_id)
        snapshot = json.loads(row["snapshot"])
        dialogue = snapshot.get("mobileDialogue")
        if (not isinstance(dialogue, dict) or dialogue.get("id") != session["id"]
                or dialogue.get("clientId") != client_id or dialogue.get("recordId") != record_id
                or snapshot.get("recordId") != record_id or snapshot.get("origin") != "workflow_discussion"
                or snapshot.get("purpose") != "discuss" or row["target_kind"] != "chatgpt" or row["target_mode"] != "new"):
            raise api.WorkflowError("原请求与当前讨论来源不匹配。", 409, "cancel_context_mismatch")
        job = self._app_dispatch_job(db, row, snapshot)
        payload = json.loads(job["payload"])
        if (job["record_id"] != record_id or payload.get("mobileDialogue") != dialogue
                or payload.get("appFrozen", {}).get("mobileDialogue") != dialogue
                or job["request_id"] != row["request_id"]):
            raise api.WorkflowError("原工作与冻结讨论身份不匹配。", 409, "cancel_context_mismatch")
        try:
            original_id = str(uuid.UUID(row["request_id"]))
        except (ValueError, TypeError, AttributeError):
            raise api.WorkflowError("原发送凭据无法核对。", 409, "cancel_context_mismatch") from None
        original = db.execute("SELECT kind,response FROM requests WHERE id=?", (original_id,)).fetchone()
        try:
            saved_send = json.loads(original["response"]) if original else None
        except (ValueError, TypeError):
            saved_send = None
        expected_send = {"sessionId": session["id"], "jobId": job["id"]}
        original_matches = original is not None and original["kind"] == "mobile_dialogue_send"
        if isinstance(saved_send, dict) and set(saved_send) == {"sessionId", "jobId", "sourceMessageId"}:
            message_id = saved_send["sourceMessageId"]
            original_matches = original_matches and {key: saved_send[key] for key in expected_send} == expected_send
            # This predicate also powers readonly hints. New sends create this
            # immutable binding atomically; never recover or write one here.
            source = message = None
            if isinstance(message_id, str) and re.fullmatch(r"[a-f0-9]{32}", message_id):
                source = db.execute("SELECT * FROM mobile_message_sources WHERE message_id=?", (message_id,)).fetchone()
                message = db.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
            try:
                original_matches = (original_matches and source is not None and message is not None
                    and source["client_id"] == client_id and source["session_id"] == session["id"]
                    and source["record_id"] == record_id and source["job_id"] == job["id"]
                    and source["request_id"] == original_id and message["role"] == "user"
                    and job["attempt"] == 1 and job["parent_id"] is None
                    and message["record_id"] == record_id and message["text"] == payload["text"]
                    and source["text_sha256"] == hashlib.sha256(message["text"].encode("utf-8")).hexdigest()
                    and json.loads(source["attachment_ids"]) == json.loads(message["attachment_ids"]) == payload["context"]["attachmentIds"]
                        == snapshot["attachmentIds"] == [image["id"] for image in payload["appFrozen"]["images"]]
                    and source["created_at"] == message["created_at"] == job["created_at"] == row["created_at"])
            except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
                original_matches = False
        else:
            # Preserve the exact pre-provenance two-field receipt boundary.
            original_matches = original_matches and saved_send == expected_send
        if not original_matches:
            raise api.WorkflowError("原发送凭据与本条请求不匹配。", 409, "cancel_context_mismatch")
        if (row["status"] != ("failed" if cancelled else "pending") or job["status"] != ("failed" if cancelled else "waiting")
                or _prior_dispatch_evidence(db, row) or json.loads(job["result"]) != {}):
            raise api.WorkflowError("原请求已有认领或送达证据，不能按未发送取消。", 409, "cancel_requires_unclaimed_pending")
        if not cancelled and (db.execute("SELECT 1 FROM jobs WHERE record_id=? AND status IN ('queued','running') LIMIT 1", (record_id,)).fetchone()
                or db.execute("SELECT 1 FROM idea_dispatches WHERE json_extract(snapshot,'$.recordId')=? "
                              "AND status IN ('claimed','waiting','needs_review') LIMIT 1", (record_id,)).fetchone()):
            raise api.WorkflowError("当前记录还有工作在途，请先核对原工作。", 409, "cancel_requires_unclaimed_pending")
        return row, job

    def _mobile_can_cancel_pending(self, db, session, public_job):
        """A boolean hint for this current session; no private receipt is exposed."""
        try:
            if not session or session.get("isCurrent") is not True:
                return False
            current = self._mobile_session(db, session["clientId"], session["id"])
            if (self._mobile_client_state(db, session["clientId"])["currentSessionId"] != session["id"]
                    or current["recordId"] != session["recordId"] or current["revision"] != session["revision"]
                    or public_job.get("recordId") != session["recordId"]):
                return False
            _, job = self._mobile_cancel_pending_candidate(db, current, public_job["appDispatch"]["id"])
            return job["id"] == public_job["id"]
        except (ValueError, TypeError, KeyError, AttributeError, sqlite3.Error):
            return False

    def _mobile_pending_cancellation_receipts(self, db, session):
        """Read at most twenty exact successful nonces in the current scope."""
        if not session or session.get("isCurrent") is not True:
            return []
        current = self._mobile_session(db, session["clientId"], session["id"])
        if (self._mobile_client_state(db, session["clientId"])["currentSessionId"] != session["id"]
                or current["recordId"] != session["recordId"] or current["revision"] != session["revision"]):
            return []
        result = []
        entries = db.execute("SELECT id,fingerprint,response FROM requests WHERE kind='mobile_dialogue_cancel_pending' "
            "AND json_extract(CASE WHEN json_valid(response) THEN response ELSE '{}' END,'$.sessionId')=? "
            "AND json_extract(CASE WHEN json_valid(response) THEN response ELSE '{}' END,'$.recordId')=? "
            "ORDER BY rowid DESC LIMIT 20", (session["id"], session["recordId"]))
        for entry in entries:
            try:
                saved = json.loads(entry["response"])
                if (not isinstance(saved, dict) or set(saved) != CANCEL_RECEIPT_FIELDS or saved["clientId"] != session["clientId"]
                        or saved["sessionId"] != session["id"] or saved["recordId"] != session["recordId"]
                        or type(saved["expectedRevision"]) is not int or not 1 <= saved["expectedRevision"] <= current["revision"]
                        or saved["status"] != "failed" or saved["reason"] != "cancelled_before_send" or saved["unsent"] is not True
                        or str(uuid.UUID(entry["id"])) != entry["id"]):
                    continue
                original = {key: saved[key] for key in ("clientId", "sessionId", "recordId", "expectedRevision", "dispatchId")}
                original["requestId"] = entry["id"]
                if hashlib.sha256(_api()._json(original).encode("utf-8")).hexdigest() != entry["fingerprint"]:
                    continue
                _, job = self._mobile_cancel_pending_candidate(db, current, saved["dispatchId"], cancelled=True)
                if job["id"] == saved["jobId"]:
                    result.append({"requestId": entry["id"], **saved})
            except (ValueError, TypeError, KeyError, AttributeError, sqlite3.Error):
                continue
        return result

    def mobile_dialogue_cancel_pending(self, body, prefix="/api/workflow", authorize=None):
        """End one original unclaimed request; never claim, clear or resend it."""
        api = _api()
        from workflow_mobile_dialogue import _client
        fields = {"requestId", "clientId", "sessionId", "recordId", "expectedRevision", "dispatchId"}
        if not isinstance(body, dict) or set(body) != fields:
            raise api.WorkflowError("取消未发送请求的内容无效。")
        client_id = _client(body["clientId"])
        try:
            request_id = str(uuid.UUID(body["requestId"]))
        except (ValueError, TypeError, AttributeError):
            raise api.WorkflowError("取消请求标识无效。") from None
        if request_id != body["requestId"] or client_id != body["clientId"]:
            raise api.WorkflowError("取消请求身份格式无效。")
        record_id, dispatch_id = api._id(body["recordId"]), api._id(body["dispatchId"])
        if authorize:
            authorize()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "mobile_dialogue_cancel_pending", body)
            session = self._mobile_session(db, client_id, body["sessionId"])
            if self._mobile_client_state(db, client_id)["currentSessionId"] != session["id"]:
                raise api.WorkflowError("当前讨论已切换；原请求保留，未取消其它讨论。", 409, "dialogue_changed")
            if session["recordId"] != record_id:
                raise api.WorkflowError("取消请求不属于当前讨论记录。", 409, "cancel_context_mismatch")
            if old:
                # A matching receipt authorizes only the previous cancellation,
                # even if its original revision has since gained another draft.
                if (not isinstance(old, dict) or set(old) != CANCEL_RECEIPT_FIELDS
                        or old.get("sessionId") != session["id"] or old.get("recordId") != record_id
                        or old.get("dispatchId") != dispatch_id or old.get("status") != "failed"
                        or old.get("reason") != "cancelled_before_send" or old.get("unsent") is not True
                        or old.get("clientId") != client_id or old.get("expectedRevision") != body["expectedRevision"]):
                    raise api.WorkflowError("原取消回执身份无法核对。", 409, "cancel_context_mismatch")
                _, job = self._mobile_cancel_pending_candidate(db, session, dispatch_id, cancelled=True)
                if job["id"] != old["jobId"]:
                    raise api.WorkflowError("原取消回执工作无法核对。", 409, "cancel_context_mismatch")
                saved = old
            else:
                self._mobile_guard(db, body, client_id)
                row, job = self._mobile_cancel_pending_candidate(db, session, dispatch_id)
                error = "已取消未发送请求；原请求未认领，原文、附件、草稿与档位保留。"
                now = api._now()
                if db.execute("UPDATE jobs SET status='failed',error=?,updated_at=? WHERE id=? AND record_id=? AND status='waiting'",
                              (error, now, job["id"], record_id)).rowcount != 1:
                    raise api.WorkflowError("原工作状态已改变，取消未执行。", 409, "cancel_requires_unclaimed_pending")
                if db.execute("UPDATE idea_dispatches SET status='failed',error=?,updated_at=? WHERE id=? AND status='pending' "
                              "AND (claim_token IS NULL OR claim_token='')", (error, now, dispatch_id)).rowcount != 1:
                    raise api.WorkflowError("原请求已被认领，取消未执行。", 409, "cancel_requires_unclaimed_pending")
                saved = {"clientId": client_id, "sessionId": session["id"], "recordId": record_id,
                         "expectedRevision": body["expectedRevision"], "dispatchId": dispatch_id,
                         "jobId": job["id"], "status": "failed", "reason": "cancelled_before_send", "unsent": True}
                self._receipt(db, "mobile_dialogue_cancel_pending", body, saved)
                self._revision(db, True)
            if authorize:
                authorize()
        # Return the current session after commit. Cancellation leaves its own
        # revision, draft, selected profile and all original source bytes intact.
        return self._mobile_state(client_id, prefix, duplicate=old is not None, cancellation=saved)

    def mobile_idea_import_status(self, body, prefix="/api/workflow", authorize=None):
        """Read the exact original import receipt without retrying any import."""
        api = _api()
        if authorize:
            authorize()
        _object(body, {"requestId", "text"})
        try:
            request_id = str(uuid.UUID(body["requestId"]))
        except (ValueError, TypeError, AttributeError):
            raise api.WorkflowError("请求标识无效。") from None
        manifest = _manifest(body["text"])
        source, source_hash = manifest["source"], _source_hash(manifest)
        fingerprint = hashlib.sha256(api._json(_nonce_body(body, manifest)).encode("utf-8")).hexdigest()
        with self._db() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if row is None:
                result = {"requestId": request_id, "found": False, "source": source,
                    "sourceHash": source_hash, "revision": self._revision(db)}
            else:
                if row["kind"] != "mobile_idea_import" or row["fingerprint"] != fingerprint:
                    raise api.WorkflowError("原交接编号与完整冻结内容不匹配；保留原凭据后核对。", 409, "import_lookup_mismatch")
                saved = json.loads(row["response"])
                imported = saved.get("imported")
                if (not isinstance(imported, dict) or imported.get("source") != source
                        or imported.get("sourceHash") != source_hash or imported.get("ideaId") != saved.get("ideaId")
                        or self._setting(db, "task-record:" + api._id(saved.get("ideaId"))) != saved.get("recordId")):
                    raise api.WorkflowError("电脑原导入凭据的来源无法完整核对；没有再次导入。", 409, "import_lookup_mismatch")
                record_id = api._id(saved.get("recordId"))
                self._record(db, record_id)
                idea = self._mobile_idea(db, self._idea(db, saved["ideaId"]))
                result = {"requestId": request_id, "found": True, "idea": idea,
                    "duplicate": True,
                    "imported": imported, "revision": self._revision(db)}
        if result["found"]:
            result["detail"] = self.detail(record_id, prefix)
        if authorize:
            authorize()
        return result

    def mobile_idea_import(self, fields, files, prefix="/api/workflow", authorize=None):
        """Commit validated bytes and a source/revision binding in one transaction."""
        api = _api()
        if authorize:
            authorize()
        _object(fields, {"requestId", "text"})
        try:
            request_id = str(uuid.UUID(fields["requestId"]))
        except (ValueError, TypeError, AttributeError):
            raise api.WorkflowError("请求标识无效。") from None
        manifest = _manifest(fields["text"])
        if (not isinstance(files, (list, tuple)) or len(files) != len(manifest["images"])
                or any(not isinstance(file, IncomingFile) for file in files)):
            raise api.WorkflowError("导入图片与想法清单不一致。")
        if sum(image["size"] for image in manifest["images"]) > api.MAX_UPLOAD:
            raise api.WorkflowError("导入总大小不能超过 24 MB。", 413)
        source = manifest["source"]
        source_hash = _source_hash(manifest)
        binding_key = "mobile-import:" + source["clientId"] + ":" + source["ideaId"]
        version_key = binding_key + ":revision:" + str(source["revision"])
        created, committed = [], False
        try:
            # Private staging never creates durable records or trusts supplied hashes.
            with tempfile.TemporaryDirectory(prefix="mobile-handoff-", dir=self.jobs_dir) as folder:
                staging, prepared = Path(folder), []
                for index, (image, file) in enumerate(zip(manifest["images"], files)):
                    if file.name != image["name"] or file.mime_type != image["mimeType"] or file.size != image["size"]:
                        raise api.WorkflowError("导入图片属性与实际文件不一致。", 415)
                    path, preview = staging / (str(index) + ".image"), staging / (str(index) + ".preview.jpg")
                    digest = file.copy_to(path)
                    if path.stat().st_size != image["size"] or digest != image["sha256"]:
                        raise api.WorkflowError("导入图片实际校验失败。", 409, "import_image_mismatch")
                    extension, mime_type, has_preview = _image(path, image["name"], preview)
                    if mime_type != image["mimeType"]:
                        raise api.WorkflowError("导入图片类型与实际内容不一致。", 415)
                    prepared.append((image, path, preview, extension, has_preview))
                with self._db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    nonce_body = _nonce_body(fields, manifest)
                    receipt = self._receipt(db, "mobile_idea_import", nonce_body)
                    binding = self._setting(db, binding_key)
                    imported = self._setting(db, version_key)
                    duplicate = receipt is not None or imported is not None
                    if receipt:
                        imported = receipt["imported"]
                        identifier, record_id = receipt["ideaId"], receipt["recordId"]
                    elif imported:
                        if imported["sourceHash"] != source_hash:
                            raise api.WorkflowError("此手机想法的同一版本已有不同内容，请保留两边后核对。", 409, "import_source_conflict")
                        identifier, record_id = binding["ideaId"], binding["recordId"]
                    else:
                        if binding:
                            if source["revision"] <= binding["latestSourceRevision"]:
                                raise api.WorkflowError("此手机想法版本已落后，请保留手机内容后合并。", 409, "import_revision_conflict")
                            row = self._idea(db, binding["ideaId"])
                            if row["revision"] != binding["destinationRevision"]:
                                raise api.WorkflowError("电脑上的想法已修改；未覆盖电脑或手机内容，请先合并。", 409, "import_conflict")
                            identifier, record_id = row["id"], binding["recordId"]
                            self._record(db, record_id)
                            self._mobile_bump_idea(db, row, manifest["idea"]["title"], manifest["idea"]["body"])
                        else:
                            row = self._mobile_create_idea(db, manifest["idea"]["body"])
                            identifier = row["id"]
                            db.execute("UPDATE ideas SET title=? WHERE id=?", (manifest["idea"]["title"], identifier))
                            record_id = self._mobile_new_record(db, manifest["idea"]["title"])
                            self._set_setting(db, "task-record:" + identifier, record_id)
                        attachment_ids = []
                        for image, path, preview, extension, has_preview in prepared:
                            image_key = binding_key + ":image:" + image["id"]
                            previous = self._setting(db, image_key)
                            if previous:
                                if previous["image"] != image:
                                    raise api.WorkflowError("手机图片标识已对应另一份内容，请保留两边后核对。", 409, "import_source_conflict")
                                saved = db.execute("SELECT * FROM attachments WHERE id=? AND record_id=?", (previous["attachmentId"], record_id)).fetchone()
                                actual = _safe_child(self.attachments_dir, saved["filename"]) if saved else None
                                if not actual or not actual.is_file() or _digest(actual) != image["sha256"]:
                                    raise api.WorkflowError("电脑保存的原图片无法核验，请保留手机图片后核对。", 409, "import_image_unavailable")
                                attachment_id = saved["id"]
                            else:
                                attachment_id = uuid.uuid4().hex
                                filename = attachment_id + extension
                                target = _safe_child(self.attachments_dir, filename)
                                thumbnail = _safe_child(self.attachments_dir, attachment_id + ".preview.jpg")
                                # Exclusive creation protects even an unexpected
                                # UUID collision; cleanup tracks only our files.
                                file_pairs = [(path, target)]
                                if has_preview:
                                    file_pairs.append((preview, thumbnail))
                                for incoming, output in file_pairs:
                                    try:
                                        with incoming.open("rb") as stream, output.open("xb") as destination:
                                            created.append(output)
                                            shutil.copyfileobj(stream, destination, 64 * 1024)
                                            destination.flush()
                                            os.fsync(destination.fileno())
                                    except FileExistsError:
                                        raise api.WorkflowError("导入图片保存标识冲突；原内容未被覆盖，请保留手机内容。", 409, "import_storage_conflict") from None
                                db.execute("INSERT INTO attachments VALUES (?,?,?,?,?,?,?,?)", (attachment_id, record_id, image["name"], filename,
                                    image["mimeType"], image["size"], int(has_preview), None))
                                self._set_setting(db, image_key, {"image": image, "attachmentId": attachment_id})
                            attachment_ids.append(attachment_id)
                        self._message(db, record_id, "user", manifest["idea"]["body"], attachment_ids)
                        db.execute("UPDATE records SET title=?,primary_attachment_id=?,context=? WHERE id=?", (manifest["idea"]["title"],
                            attachment_ids[0] if attachment_ids else None, api._json({"selectedText": "", "referenceIds": [], "attachmentIds": attachment_ids}), record_id))
                        destination_revision = self._idea(db, identifier)["revision"]
                        provenance = {"id": uuid.uuid4().hex, "kind": "phone_imported", "source": source,
                            "sourceHash": source_hash, "sourceClaim": True, "authorityVerified": False,
                            "attachmentIds": attachment_ids, "destinationRevision": destination_revision, "createdAt": api._now()}
                        meta = self._mobile_metadata(db, identifier)
                        meta.update(archived=manifest["idea"]["archived"], executionDraft=manifest["idea"]["executionDraft"],
                            attachmentIds=attachment_ids, keyPoints=[{**point, "source": provenance} for point in manifest["idea"]["keyPoints"]])
                        meta["provenance"].append(provenance)
                        self._set_setting(db, "mobile-idea:" + identifier, meta)
                        imported = {"source": source, "sourceHash": source_hash, "ideaId": identifier, "destinationRevision": destination_revision}
                        self._set_setting(db, version_key, imported)
                        self._set_setting(db, version_key + ":snapshot", {"manifest": manifest, "attachmentIds": attachment_ids,
                            "ideaId": identifier, "recordId": record_id, "sourceHash": source_hash, "destinationRevision": destination_revision})
                        self._set_setting(db, binding_key, {"ideaId": identifier, "recordId": record_id,
                            "latestSourceRevision": source["revision"], "destinationRevision": destination_revision})
                        self._revision(db, True)
                    if not receipt:
                        self._receipt(db, "mobile_idea_import", nonce_body, {"ideaId": identifier, "recordId": record_id, "imported": imported})
                    self._record(db, record_id)
                    idea = self._mobile_idea(db, self._idea(db, identifier))
                    revision = self._revision(db)
                    if authorize:
                        authorize()
                committed = True
            return {"requestId": request_id, "idea": idea, "detail": self.detail(record_id, prefix),
                "duplicate": duplicate, "imported": imported, "revision": revision}
        except TransferError as error:
            raise api.WorkflowError(str(error), error.status) from error
        finally:
            # Once committed these UUID files belong to the store. Failed imports
            # only remove files created here, never historical or shared files.
            if not committed:
                for path in created:
                    path.unlink(missing_ok=True)
