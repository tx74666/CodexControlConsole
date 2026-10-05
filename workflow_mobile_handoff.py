"""Import one explicitly saved phone idea; never dispatch or execute its content."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from transfer_store import IncomingFile, TransferError, _filename, _image, _safe_child


MAX_MANIFEST_BYTES = 80_000
MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


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
