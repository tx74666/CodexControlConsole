"""Durable, explicitly confirmed local Work; never adopts a historical queue.

The injected controller owns a fresh child process. This module owns source
freezing, one-shot submission, exact cancellation and independently observed
file changes. Neither reviews nor status reads call a provider.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import parse_qs
import uuid


CATALOG = "codex-work:workspaces"
REVIEW_PREFIX = "codex-work:review:"
ACTIVE = frozenset({"starting", "running", "cancelling", "needs_review"})
EFFORT = {"fast": "low", "high": "high"}
MAX_TEXT = 128 * 1024
MAX_PROGRESS = 256 * 1024
BINDING_KEYS = {"provider", "connectionId", "catalogRevision", "modelSlug"}
REVIEW_KEYS = {"requestId", "recordId", "expectedRevision", "text", "attachmentIds", "workspaceId",
              "workspaceAuthorizationSha256", "requestedProfile", "subscription"}
PRIVATE_DIRS = {".codex", ".ssh", ".aws", ".azure", "chatgpt-subscription", "siwc-probe", "attachments", "jobs"}


def _api():
    import workflow_service
    return workflow_service


def _fail(code, message="Work 来源或状态无法核对；保留本轮内容，请重新核对。", status=409):
    raise _api().WorkflowError(message, status, code)


def _sha(value):
    return hashlib.sha256(_api()._json(value).encode("utf-8")).hexdigest()


def _exact(body, keys):
    if not isinstance(body, dict) or set(body) != keys:
        _fail("codex_work_request_invalid", "请完整确认这次 Work 的内容与目标。", 400)


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        _fail("codex_work_source_invalid", status=400)
    return value


def _remote_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,190}", value):
        _fail("codex_work_identity_invalid", status=400)
    return value


def _root(value):
    # Check the spelling and every ancestor before resolving; no junction aliases.
    if not isinstance(value, str) or len(value) > 2048 or "\0" in value:
        _fail("codex_work_workspace_invalid", status=403)
    path = Path(value)
    if not path.is_absolute() or path == Path(path.anchor) or not path.is_dir():
        _fail("codex_work_workspace_invalid", "请选择实际存在的具体工作目录。", 403)
    for item in (path, *path.parents):
        try:
            if (item.is_symlink() or getattr(item, "is_junction", lambda: False)()
                    or getattr(item.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400):
                _fail("codex_work_workspace_redirected", status=403)
        except OSError:
            _fail("codex_work_workspace_invalid", status=403)
    if path.resolve() != path.absolute() or any(part.casefold() in PRIVATE_DIRS for part in path.parts):
        _fail("codex_work_workspace_redirected", status=403)
    return path.resolve()


def _overlap(first, second):
    a, b = os.path.normcase(str(first)), os.path.normcase(str(second))
    try:
        return os.path.commonpath((a, b)) in (a, b)
    except ValueError:
        return False


def _phone(prefix):
    return prefix.startswith("/api/phone/")


def _public_preparation(meta):
    """Only the selected persisted echo is public; no private image-root path.

The operating system's out-of-scope denial needs a separate actual experiment.
Neither a profile echo nor Windows setup completion supplies that evidence.
"""
    empty = {"sandboxVerified": False, "configurationEchoVerified": False,
             "fileToolsScopeVerified": False, "nativeEnvironmentAccess": None,
             "actualActivePermissionProfile": None, "preparationReceipt": None,
             "preparationReceiptSha256": None, "scopeEvidenceType": None,
             "outsideScopeReadDeniedVerified": False}
    event, digest = meta.get("preparationReceipt"), meta.get("preparationReceiptSha256")
    if event is None:
        return empty
    try:
        source = meta["source"]
        actual = event["preparationReceipt"]["threadStart"]
        if (not CodexWorkMixin._codex_work_event_shape(event) or event["type"] != "prepared"
                or digest != _sha(event) or event["runId"] != meta["runId"]
                or event["sourceSha256"] != meta["sourceSha256"] or event["threadId"] != meta["threadId"]
                or event["turnId"] is not None
                or type(event["preparationReceipt"]) is not dict
                or type(event["sandboxVerified"]) is not bool
                or event["sandboxVerified"] != (event["preparationReceipt"].get("schemaVersion") == 1)
                or event["requestedProfile"] != source["requestedProfile"]
                or event["actualModel"] != source["subscription"]["modelSlug"]
                or event["actualEffort"] != EFFORT[source["requestedProfile"]]):
            return empty
        selected = event["preparationReceipt"]
        from workflow_codex_work import valid_preparation_receipt
        reads = [key for key, value in selected["configuration"]["permissionProfile"]["filesystem"].items()
                 if value == "read" and key != ":minimal"]
        if len(reads) != 1:
            return empty
        image_root = Path(reads[0])
        if (not image_root.is_absolute() or image_root.name != "images" or image_root.parent.name != meta["runId"]
                or image_root.parent.parent.name != "codex-work"
                or not valid_preparation_receipt(selected, allowed_root=source["workspace"]["allowedRoot"],
                    image_root=image_root, model=event["actualModel"], effort=event["actualEffort"], thread_id=event["threadId"])):
            return empty
        # The full selected configuration stays in the private job. A stable
        # hash binds this public summary without disclosing its staging path.
        file_tools = selected["schemaVersion"] == 2
        return {**empty, "sandboxVerified": event["sandboxVerified"], "configurationEchoVerified": True,
                "fileToolsScopeVerified": file_tools, "nativeEnvironmentAccess": False if file_tools else None,
                "scopeEvidenceType": selected["evidenceType"],
                "actualActivePermissionProfile": dict(actual["activePermissionProfile"]),
                "preparationReceiptSha256": digest,
                "preparationReceipt": {"schemaVersion": selected["schemaVersion"], "evidenceType": selected["evidenceType"],
                    "runId": event["runId"], "sourceSha256": event["sourceSha256"], "observedAt": event["observedAt"],
                    **{key: actual[key] for key in ("threadId", "model", "modelProvider", "reasoningEffort", "cwd", "approvalPolicy")},
                    "activePermissionProfile": dict(actual["activePermissionProfile"]),
                    "scopePolicySha256": _sha(selected["configuration"]["permissionProfile"]),
                    "configurationEchoVerified": True, "outsideScopeReadDeniedVerified": False,
                    **({"capabilities": json.loads(_api()._json(selected["capabilities"]))} if file_tools else {})}}
    except (KeyError, TypeError, ValueError, RecursionError):
        return empty


class CodexWorkMixin:
    def codex_work_setup(self, body, authorize=None):
        _exact(body, {"workspaceId", "workspaceAuthorizationSha256", "confirmed"})
        if body["confirmed"] is not True:
            _fail("codex_work_setup_not_confirmed", status=403)
        if authorize:
            authorize()
        with self._db() as db:
            workspace = self._codex_work_workspace(db, body["workspaceId"], _digest(body["workspaceAuthorizationSha256"]))
        if self.codex_work_active():
            _fail("codex_work_workspace_busy", "先等待本机 Work 结束，再配置沙箱。")
        controller = getattr(self, "codex_work", None)
        if controller is None:
            _fail("codex_work_controller_unavailable", status=503)
        if authorize:
            authorize()
        return controller.begin_setup(workspace["allowedRoot"])

    def codex_work_config(self):
        with self._db() as db:
            catalog = self._setting(db, CATALOG) or {"workspaces": [], "revision": None}
            controller = getattr(self, "codex_work", None)
            setup_status = getattr(controller, "setup_status", None)
            return {"workspaces": catalog["workspaces"], "revision": catalog["revision"],
                    "controllerAttached": controller is not None,
                    "setup": setup_status() if callable(setup_status) else {"status": "unavailable", "busy": False, "ready": False},
                    "subscription": self.subscription.get_status() if getattr(self, "subscription", None) is not None else
                        {"connected": False, "connectionId": None, "catalogRevision": None, "models": [], "status": "disconnected", "busy": False, "error": None},
                    "executionVerified": False, "profiles": [
                        {"id": "fast", "effort": "low", "supported": True, "verified": False},
                        {"id": "high", "effort": "high", "supported": True, "verified": False},
                        {"id": "pro", "effort": None, "supported": False, "verified": False}]}

    def _codex_work_workspace(self, db, identifier, authorization=None):
        item = next((entry for entry in (self._setting(db, CATALOG) or {}).get("workspaces", [])
                     if entry["id"] == identifier), None)
        if item is None or authorization is not None and authorization != item["authorizationSha256"]:
            _fail("codex_work_permission_changed", "本次 Workspace 授权已改变，请重新审核。", 403)
        workspace, allowed = _root(item["workspaceRoot"]), _root(item["allowedRoot"])
        if not allowed.is_relative_to(workspace) or _overlap(allowed, self.data_dir):
            _fail("codex_work_workspace_invalid", status=403)
        if item["authorizationSha256"] != _sha({key: item[key] for key in ("id", "name", "workspaceRoot", "allowedRoot")}):
            _fail("codex_work_permission_changed", status=403)
        return dict(item)

    def configure_codex_work(self, body, authorize=None):
        _exact(body, {"requestId", "workspaces"})
        if authorize:
            authorize()
        if not isinstance(body["workspaces"], list) or len(body["workspaces"]) > 32:
            _fail("codex_work_workspace_invalid", status=400)
        clean, seen = [], set()
        for entry in body["workspaces"]:
            _exact(entry, {"id", "name", "workspaceRoot", "allowedRoot"})
            identifier = _api()._key(entry["id"])
            name = _api()._text(entry["name"], 120)
            workspace, allowed = _root(entry["workspaceRoot"]), _root(entry["allowedRoot"])
            if not name.strip() or identifier in seen or not allowed.is_relative_to(workspace) or _overlap(allowed, self.data_dir):
                _fail("codex_work_workspace_invalid", status=403)
            item = {"id": identifier, "name": name, "workspaceRoot": str(workspace), "allowedRoot": str(allowed)}
            item["authorizationSha256"] = _sha(item)
            clean.append(item)
            seen.add(identifier)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "codex_work_config", body)
            if old is None:
                previous = (self._setting(db, CATALOG) or {}).get("workspaces", [])
                if clean != previous and db.execute("SELECT 1 FROM jobs WHERE json_extract(payload,'$.executionEngine')='codex_agent' AND status IN ('starting','running','cancelling','needs_review')").fetchone():
                    _fail("codex_work_workspace_busy", "Work 尚在执行或待核对，不能改动其授权范围。")
                self._set_setting(db, CATALOG, {"workspaces": clean, "revision": _sha(clean)})
                self._receipt(db, "codex_work_config", body, {"revision": _sha(clean)})
                self._revision(db, True)
            if authorize:
                authorize()
        return self.codex_work_config()

    def _codex_work_binding(self, value):
        _exact(value, BINDING_KEYS)
        if (value["provider"] != "chatgpt_subscription" or not isinstance(value["connectionId"], str)
                or not re.fullmatch(r"[a-f0-9]{32}", value["connectionId"])):
            _fail("subscription_binding_invalid")
        _digest(value["catalogRevision"])
        adapter = getattr(self, "subscription", None)
        if adapter is None:
            _fail("subscription_not_connected")
        # This is the broker's cache-only selector; not token preparation or GET models.
        actual = adapter.validate_selection(value["modelSlug"], value["catalogRevision"], value["connectionId"])
        if actual != value:
            _fail("subscription_selection_stale")
        return dict(actual)

    def _codex_work_scope(self, db, body, prefix, *, revision=True):
        record = self._record(db, body["recordId"])
        if _phone(prefix):
            from workflow_mobile_dialogue import _client
            client = _client(body["clientId"])
            if client != body["clientId"]:
                _fail("codex_work_source_invalid")
            session = self._mobile_guard(db, body, client) if revision else self._mobile_session(db, client, body["sessionId"])
            if session["recordId"] != record["id"]:
                _fail("codex_work_source_invalid", status=403)
            self._mobile_source_guard(db, session)
            return {key: session[key] for key in ("id", "clientId", "recordId", "ideaId", "ideaRevision", "revision")}
        if revision and (type(body["expectedRevision"]) is not int or body["expectedRevision"] != int(self._revision(db))):
            _fail("revision_conflict", "工作记录已更新，请保留输入后重新审核。")
        return None

    def _codex_work_phone_session(self, db, client_id, session_id, record_id):
        """Read the explicit current phone identity without touching its draft."""
        from workflow_mobile_dialogue import _client
        client = _client(client_id)
        if client != client_id:
            _fail("codex_work_source_invalid", status=403)
        session = self._mobile_session(db, client, session_id)
        if self._mobile_client_state(db, client)["currentSessionId"] != session["id"]:
            _fail("dialogue_changed", "当前讨论已切换；不会取消其它讨论的 Agent。", 409)
        if session["recordId"] != record_id:
            _fail("codex_work_source_invalid", status=403)
        self._mobile_source_guard(db, session)
        return session

    def _codex_work_phone_run_scope(self, db, session, source):
        """Only the current same-task phone discussion may view/control a run.

        Desktop-created runs keep mobileDialogue=None. Their task binding is
        verified against the explicit current phone scope rather than invented
        from the job. Draft text/revision and global progress revisions are not
        cancellation authority and may change while this Agent runs.
        """
        current = self._codex_work_phone_session(db, session["clientId"], session["id"], session["recordId"])
        if not isinstance(source, dict) or source.get("recordId") != current["recordId"]:
            _fail("codex_work_source_invalid", status=403)
        origin = source.get("mobileDialogue")
        if origin is not None and (not isinstance(origin, dict)
                or any(origin.get(key) != current[key] for key in ("id", "clientId", "recordId", "ideaId", "ideaRevision"))):
            _fail("codex_work_source_invalid", status=403)
        context = source.get("context")
        actual = self._source_task(db, current["recordId"])
        if not isinstance(context, dict) or context.get("sourceTask") != actual:
            _fail("codex_work_source_changed", status=403)
        if (actual is None and current.get("ideaId") is not None
                or actual is not None and (current.get("ideaId") != actual["ideaId"]
                                          or current.get("ideaRevision") != actual["revision"])):
            _fail("codex_work_source_changed", status=403)
        idea_context = self._native_idea_context(db, actual) if actual else None
        if context.get("ideaContext") != idea_context:
            _fail("codex_work_source_changed", status=403)
        return True

    @staticmethod
    def _codex_work_phone_public_scope(session):
        return {"recordId": session["recordId"], "clientId": session["clientId"], "sessionId": session["id"]}

    def _codex_work_images(self, db, record_id, identifiers, frozen=None, materialize=False):
        if (not isinstance(identifiers, list) or len(identifiers) > 4
                or any(not isinstance(identifier, str) for identifier in identifiers)
                or len(set(identifiers)) != len(identifiers)):
            _fail("codex_work_images_invalid", status=400)
        images, total = [], 0
        for index, identifier in enumerate(identifiers):
            row = self._mobile_image_row(db, record_id, identifier)
            proof = self._mobile_image_proof(row)
            if row["mime_type"] not in {"image/png", "image/jpeg", "image/webp", "image/gif"} or row["size"] > 8 * 1024 * 1024:
                _fail("codex_work_images_invalid", "请选择每张不超过 8 MB 的 PNG、JPEG、WebP 或 GIF。", 413)
            total += row["size"]
            if total > 24 * 1024 * 1024:
                _fail("codex_work_images_invalid", status=413)
            image = {"id": identifier, "filename": row["filename"], "name": row["name"], **proof}
            if frozen is not None and (index >= len(frozen) or frozen[index] != image):
                _fail("image_source_mismatch")
            if materialize:
                path = _api()._safe_child(self.attachments_dir, row["filename"])
                data = path.read_bytes()
                if len(data) != image["size"] or hashlib.sha256(data).hexdigest() != image["sha256"]:
                    _fail("image_source_mismatch")
                images.append({"bytes": data, "mimeType": image["mimeType"], "sha256": image["sha256"]})
            else:
                images.append(image)
        if frozen is not None and len(frozen) != len(identifiers):
            _fail("image_source_mismatch")
        return images

    def _codex_work_inventory(self, root):
        from workflow_native_work import _internal_directory, _file, _file_key
        files, remaining = {}, 128 * 1024 * 1024
        for directory, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(name for name in dirs if not _internal_directory(name)
                             and name.casefold() not in PRIVATE_DIRS
                             and not (Path(directory) / name).is_symlink()
                             and not getattr(Path(directory) / name, "is_junction", lambda: False)())
            for name in sorted(names):
                lower = name.casefold()
                if lower in {"auth.json", "registration.json", "identity-hint.json"} or lower.endswith(".dpapi"):
                    continue
                path = Path(directory) / name
                try:
                    path = _file(root, path.relative_to(root).as_posix())
                except (ValueError, OSError):
                    continue
                key, size = _file_key(path.relative_to(root).as_posix()), path.stat().st_size
                if key in files or len(files) >= 10000 or size > min(remaining, 32 * 1024 * 1024):
                    _fail("codex_work_inventory_too_large", "文件核对范围过大，请缩小允许修改的目录。")
                files[key] = self._file_digest(path)
                remaining -= size
        return files

    def _codex_work_context(self, db, record_id):
        record = self._record(db, record_id)
        history = [{"id": row["id"], "role": row["role"], "text": row["text"], "createdAt": row["created_at"]}
                   for row in db.execute("SELECT * FROM (SELECT rowid,* FROM messages WHERE record_id=? ORDER BY rowid DESC LIMIT 12) ORDER BY rowid", (record_id,))]
        source = self._source_task(db, record_id)
        idea = self._native_idea_context(db, source) if source else None
        value = {"record": {key: record[key] for key in ("id", "title", "project_id", "context", "updated_at")},
                 "history": history, "sourceTask": source, "ideaContext": idea}
        if len(_api()._json(value)) > 96000:
            _fail("codex_work_context_too_long", "本记录的上下文过长，请缩小本轮内容；原文保留。", 413)
        return value

    def _codex_work_review_row(self, db, identifier):
        value = self._setting(db, REVIEW_PREFIX + _api()._id(identifier))
        if (not isinstance(value, dict) or value.get("reviewId") != identifier
                or value.get("sourceSha256") != _sha(value.get("source"))
                or value.get("reviewSha256") != _sha({key: val for key, val in value.items() if key != "reviewSha256"})):
            _fail("codex_work_review_invalid")
        return value

    @staticmethod
    def _codex_work_review_public(review):
        source = json.loads(_api()._json(review["source"]))
        for image in source["images"]:
            image.pop("filename", None)
        return {"reviewId": review["reviewId"], "recordId": source["recordId"],
                "sourceSha256": review["sourceSha256"], "reviewSha256": review["reviewSha256"],
                "source": source, "beforeFileCount": len(review["beforeFiles"])}

    def codex_work_review(self, body, prefix="/api/workflow", authorize=None):
        _exact(body, REVIEW_KEYS | ({"clientId", "sessionId"} if _phone(prefix) else set()))
        if authorize:
            authorize()
        text = _api()._text(body["text"], MAX_TEXT)
        if not isinstance(body["requestedProfile"], str) or body["requestedProfile"] not in EFFORT:
            _fail("codex_work_pro_unsupported", "Console Work 的 Pro 档位尚未接通；请明确选择已核实的档位。")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "codex_work_review", body)
            if old is not None:
                review = self._codex_work_review_row(db, old["reviewId"])
                self._codex_work_scope(db, body, prefix, revision=False)
            else:
                dialogue = self._codex_work_scope(db, body, prefix)
                binding = self._codex_work_binding(body["subscription"])
                workspace = self._codex_work_workspace(db, body["workspaceId"], _digest(body["workspaceAuthorizationSha256"]))
                if dialogue:
                    session = self._mobile_session(db, dialogue["clientId"], dialogue["id"])
                    self._mobile_selected_images(db, session, body["attachmentIds"])
                images = self._codex_work_images(db, body["recordId"], body["attachmentIds"])
                if not text.strip() and not images:
                    _fail("codex_work_request_invalid", "请输入本轮内容或明确选择图片。", 400)
                context = self._codex_work_context(db, body["recordId"])
                source = {"recordId": body["recordId"], "text": text, "attachmentIds": list(body["attachmentIds"]),
                          "images": images, "workspace": workspace, "subscription": binding,
                          "requestedProfile": body["requestedProfile"], "context": context,
                          "mobileDialogue": dialogue, "expectedRevision": body["expectedRevision"]}
                instruction = ("本轮仅在下列已确认范围工作，历史内容是上下文，不扩大允许范围。\n"
                               + _api()._json({"workspace": workspace, "history": context["history"],
                                               "sourceTask": context["sourceTask"], "ideaContext": context["ideaContext"]})
                               + "\n本轮用户原文：\n" + text)
                _api()._text(instruction, MAX_TEXT)
                source["executionText"] = instruction
                review = {"reviewId": uuid.uuid4().hex, "source": source, "sourceSha256": _sha(source),
                          "reviewedAt": _api()._now(), "requestBody": dict(body),
                          "beforeFiles": self._codex_work_inventory(Path(workspace["allowedRoot"]))}
                review["reviewSha256"] = _sha(review)
                self._set_setting(db, REVIEW_PREFIX + review["reviewId"], review)
                self._receipt(db, "codex_work_review", body, {"reviewId": review["reviewId"]})
                # A review is durable but does not alter the record/session draft.
                self._revision(db, True)
            if authorize:
                authorize()
            return {**self._codex_work_review_public(review), "duplicate": old is not None, "revision": self._revision(db)}

    def _codex_work_check_review(self, db, review, prefix):
        source = review["source"]
        if bool(source["mobileDialogue"]) != _phone(prefix):
            _fail("codex_work_source_invalid", status=403)
        # Desktop global revision changed by the review itself. Compare the
        # actual record/context and authority; mobile retains its exact revision.
        self._codex_work_scope(db, review["requestBody"], prefix, revision=_phone(prefix))
        if self._codex_work_context(db, source["recordId"]) != source["context"]:
            _fail("codex_work_source_changed")
        if self._codex_work_workspace(db, source["workspace"]["id"], source["workspace"]["authorizationSha256"]) != source["workspace"]:
            _fail("codex_work_permission_changed", status=403)
        self._codex_work_binding(source["subscription"])
        self._codex_work_images(db, source["recordId"], source["attachmentIds"], source["images"])
        if self._codex_work_inventory(Path(source["workspace"]["allowedRoot"])) != review["beforeFiles"]:
            _fail("codex_work_files_changed", "允许修改范围在审核后已改变，请重新审核。")

    def _codex_work_job_row(self, db, job_id):
        row = db.execute("SELECT * FROM jobs WHERE id=?", (_api()._id(job_id),)).fetchone()
        if row is None or row["kind"] != "work":
            _fail("codex_work_job_invalid", status=404)
        payload = json.loads(row["payload"])
        meta = payload.get("codexWork", {})
        review = self._codex_work_review_row(db, meta.get("reviewId"))
        acceptance = self._setting(db, REVIEW_PREFIX + review["reviewId"] + ":accepted")
        receipt = db.execute("SELECT * FROM requests WHERE id=?", (row["request_id"],)).fetchone()
        if (payload.get("executionEngine") != "codex_agent" or meta.get("runId") != row["id"]
                or meta.get("sourceSha256") != review["sourceSha256"] or meta.get("reviewSha256") != review["reviewSha256"]
                or meta.get("source") != review["source"] or row["record_id"] != review["source"]["recordId"]
                or payload.get("mobileDialogue") != review["source"]["mobileDialogue"]
                or acceptance != {"jobId": row["id"]} or receipt is None or receipt["kind"] != "codex_work_submit"
                or json.loads(receipt["response"]) != {"jobId": row["id"]}):
            _fail("codex_work_source_invalid")
        message = db.execute("SELECT * FROM messages WHERE id=? AND record_id=?", (meta.get("inputMessageId"), row["record_id"])).fetchone()
        if (message is None or message["role"] != "user" or message["text"] != review["source"]["text"]
                or json.loads(message["attachment_ids"]) != review["source"]["attachmentIds"]
                or message["created_at"] != payload["submissionTime"]["confirmedAt"]):
            _fail("codex_work_source_invalid")
        if meta.get("preparationReceipt") is not None:
            event = meta["preparationReceipt"]
            if (not self._codex_work_event_shape(event) or event["type"] != "prepared"
                    or meta.get("preparationReceiptSha256") != _sha(event)
                    or event["runId"] != row["id"] or event["sourceSha256"] != meta["sourceSha256"]
                    or event["threadId"] != meta["threadId"] or event["turnId"] is not None
                    or not self._codex_work_preparation_valid(event, meta["source"])):
                _fail("codex_work_preparation_receipt_invalid")
        return row, payload, meta, review

    @staticmethod
    def _public_codex_work_job(row, prefix="/api/workflow"):
        payload, result = json.loads(row["payload"]), json.loads(row["result"])
        meta, source = payload["codexWork"], payload["codexWork"]["source"]
        fields = ("runId", "reviewId", "sourceSha256", "inputMessageId", "name", "threadId", "turnId", "phase", "actualModel", "actualEffort",
                  "cancellationVerified", "executionVerified", "reportOnly")
        public = {key: meta.get(key) for key in fields}
        public.update(_public_preparation(meta))
        public.update(workspaceId=source["workspace"]["id"], requestedProfile=source["requestedProfile"],
                      workspaceName=source["workspace"]["name"], workspaceRoot=source["workspace"]["workspaceRoot"],
                      allowedRoot=source["workspace"]["allowedRoot"],
                      requestedModel=source["subscription"]["modelSlug"], requestedEffort=EFFORT[source["requestedProfile"]],
                      terminalEventObserved=(meta.get("terminal") or {}).get("terminalEventObserved", False),
                      terminalStatus=(meta.get("terminal") or {}).get("terminalStatus"),
                      sendIntentRecorded=meta.get("sendIntent") is not None, cancelRequested=meta.get("cancelRequest") is not None,
                      retryAllowed=False, progress=meta.get("progress", []), plan=meta.get("plan", []),
                      fileToolsBlocked=meta.get("fileToolsBlocked") is True)
        return {"id": row["id"], "recordId": row["record_id"], "kind": "work", "executionEngine": "codex_agent",
                "requestId": row["request_id"], "status": row["status"], "attempt": row["attempt"],
                "createdAt": row["created_at"], "updatedAt": row["updated_at"], "error": row["error"],
                "instruction": source["text"], "subscription": source["subscription"], "requestedProfile": source["requestedProfile"],
                "workspace": source["workspace"], "mobileDialogue": source["mobileDialogue"], "codexWork": public,
                "result": result, "resultMessageId": result.get("messageId"), "resultAttachmentIds": []}

    def _codex_work_response(self, job_id, prefix, duplicate=False):
        with self._db() as db:
            row, _, _, _ = self._codex_work_job_row(db, job_id)
            return {"recordId": row["record_id"], "job": self._public_codex_work_job(row, prefix),
                    "duplicate": duplicate, "revision": self._revision(db)}

    def codex_work_submit(self, body, prefix="/api/workflow", authorize=None):
        _exact(body, {"requestId", "reviewId", "sourceSha256", "confirmed"})
        if body["confirmed"] is not True:
            _fail("codex_work_confirmation_required", status=400)
        _digest(body["sourceSha256"])
        if authorize:
            authorize()
        controller = getattr(self, "codex_work", None)
        spec = None
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "codex_work_submit", body)
            review = self._codex_work_review_row(db, body["reviewId"])
            source = review["source"]
            if body["sourceSha256"] != review["sourceSha256"] or bool(source["mobileDialogue"]) != _phone(prefix):
                _fail("codex_work_source_invalid", status=403)
            if old is not None:
                job_id = old["jobId"]
            else:
                if controller is None:
                    _fail("codex_work_not_connected", "Work 控制器尚未接通。", 503)
                if self._setting(db, REVIEW_PREFIX + review["reviewId"] + ":accepted"):
                    _fail("codex_work_review_already_submitted", "这次审核已提交；不能换请求标识重发。")
                self._codex_work_check_review(db, review, prefix)
                for active in db.execute("SELECT payload FROM jobs WHERE json_extract(payload,'$.executionEngine')='codex_agent' AND status IN ('starting','running','cancelling','needs_review')"):
                    previous = json.loads(active["payload"])["codexWork"]["source"]["workspace"]
                    if _overlap(source["workspace"]["allowedRoot"], previous["allowedRoot"]):
                        _fail("codex_work_workspace_busy", "同一或重叠范围已有 Work 在执行或待核对。")
                if db.execute("SELECT 1 FROM idea_dispatches WHERE json_extract(snapshot,'$.recordId')=? AND status IN ('pending','claimed','waiting','needs_review')", (source["recordId"],)).fetchone():
                    _fail("dispatch_in_progress", "本记录还有 Chat 请求在途，请先核对结果。")
                images = self._codex_work_images(db, source["recordId"], source["attachmentIds"], source["images"], materialize=True)
                spec = {"subscription": source["subscription"], "requestedProfile": source["requestedProfile"],
                        "workspaceRoot": source["workspace"]["workspaceRoot"], "allowedRoot": source["workspace"]["allowedRoot"],
                        "text": source["executionText"], "images": images, "sourceSha256": review["sourceSha256"]}
                job_id, now = uuid.uuid4().hex, _api()._now()
                ordinal = db.execute("SELECT COUNT(*) FROM jobs WHERE record_id=? AND json_extract(payload,'$.executionEngine')='codex_agent'", (source["recordId"],)).fetchone()[0] + 1
                meta = {"runId": job_id, "reviewId": review["reviewId"], "sourceSha256": review["sourceSha256"],
                        "name": "Agent " + str(ordinal),
                        "reviewSha256": review["reviewSha256"], "source": source, "threadId": None, "turnId": None,
                        "phase": "starting", "prepared": False, "preparationReceipt": None,
                        "preparationReceiptSha256": None, "sendIntent": None, "interruptIntent": None,
                        "cancelRequest": None, "progress": [], "plan": [], "actualModel": None, "actualEffort": None,
                        "cancellationVerified": False, "executionVerified": False, "reportOnly": False}
                payload = {"executionEngine": "codex_agent", "codexWork": meta, "text": source["text"],
                           "mobileDialogue": source["mobileDialogue"], "requestedProfile": source["requestedProfile"],
                           "subscription": source["subscription"], "submissionTime": self._submission_time(now)}
                meta["inputMessageId"] = self._message(db, source["recordId"], "user", source["text"], source["attachmentIds"],
                                                       created_at=now, text_limit=MAX_TEXT)
                db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (job_id, source["recordId"], "work", str(uuid.UUID(body["requestId"])),
                           _api()._json(payload), "starting", 1, None, now, now, "", "", "{}"))
                # The review hash is immutable; acceptance is a separate durable key.
                self._set_setting(db, REVIEW_PREFIX + review["reviewId"] + ":accepted", {"jobId": job_id})
                self._receipt(db, "codex_work_submit", body, {"jobId": job_id})
                self._revision(db, True)
            if authorize:
                authorize()
        if spec is not None:
            # The callback can safely inspect committed intent/job/source rows.
            try:
                controller.submit(job_id, spec, self._codex_work_event)
            except Exception:
                # A transport exception cannot prove a child did not start.
                self._codex_work_submission_unknown(job_id)
        return self._codex_work_response(job_id, prefix, old is not None)

    def _codex_work_submission_unknown(self, job_id):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row, payload, meta, _ = self._codex_work_job_row(db, job_id)
            if row["status"] not in {"completed", "interrupted", "failed"}:
                meta["phase"] = "needs_review"
                db.execute("UPDATE jobs SET status='needs_review',payload=?,error=?,updated_at=? WHERE id=?",
                           (_api()._json(payload), "codex_work_submission_unknown", _api()._now(), job_id))
                self._revision(db, True)

    def codex_work_cancel(self, body, prefix="/api/workflow", authorize=None):
        _exact(body, {"requestId", "jobId", "threadId", "turnId", "sourceSha256"}
               | ({"clientId", "sessionId"} if _phone(prefix) else set()))
        _remote_id(body["threadId"])
        _remote_id(body["turnId"])
        _digest(body["sourceSha256"])
        if authorize:
            authorize()
        controller, interrupt, phone_scope = getattr(self, "codex_work", None), False, None
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "codex_work_cancel", body)
            row, payload, meta, _ = self._codex_work_job_row(db, body["jobId"])
            if (body["sourceSha256"] != meta["sourceSha256"] or body["threadId"] != meta["threadId"]
                    or body["turnId"] != meta["turnId"]):
                _fail("codex_work_cancel_mismatch", status=403)
            if _phone(prefix):
                session = self._codex_work_phone_session(db, body["clientId"], body["sessionId"], row["record_id"])
                self._codex_work_phone_run_scope(db, session, meta["source"])
                phone_scope = self._codex_work_phone_public_scope(session)
            if old is None:
                if controller is None or row["status"] not in ACTIVE:
                    _fail("codex_work_cancel_unavailable")
                if meta["cancelRequest"] is not None:
                    _fail("codex_work_cancel_already_requested", "本轮已保存取消请求，等待实际中断回执；不能换标识重复取消。")
                current = controller.snapshot(row["id"])
                if (not current or current.get("active") is not True or current.get("threadId") != meta["threadId"]
                        or current.get("turnId") != meta["turnId"] or current.get("sourceSha256") != meta["sourceSha256"]):
                    _fail("codex_work_cancel_unavailable", "没有可核对的本轮活动 Agent，不能对其它进程发取消。")
                meta["cancelRequest"] = {"requestId": body["requestId"], "requestedAt": _api()._now(),
                                         "threadId": body["threadId"], "turnId": body["turnId"]}
                meta["phase"] = "cancelling"
                db.execute("UPDATE jobs SET status='cancelling',payload=?,updated_at=? WHERE id=?",
                           (_api()._json(payload), _api()._now(), row["id"]))
                self._receipt(db, "codex_work_cancel", body, {"jobId": row["id"]})
                self._revision(db, True)
                interrupt = True
            if authorize:
                authorize()
        if interrupt:
            try:
                controller.interrupt(body["jobId"], body["threadId"], body["turnId"])
            except Exception:
                self._codex_work_submission_unknown(body["jobId"])
        result = self._codex_work_response(body["jobId"], prefix, old is not None)
        if phone_scope is not None:
            result["scope"] = phone_scope
        return result

    def codex_work_runs(self, query="", prefix="/api/workflow", authorize=None):
        values = parse_qs(query, keep_blank_values=True)
        keys = {"recordId", "clientId", "sessionId"} if _phone(prefix) else {"recordId"}
        if len(query) > 512 or set(values) != keys or any(len(values[key]) != 1 for key in keys):
            _fail("codex_work_request_invalid", status=400)
        if authorize:
            authorize()
        with self._db() as db:
            record = self._record(db, values["recordId"][0])
            session = (self._codex_work_phone_session(db, values["clientId"][0], values["sessionId"][0], record["id"])
                       if _phone(prefix) else None)
            rows = db.execute("SELECT * FROM jobs WHERE record_id=? AND kind='work' AND json_extract(payload,'$.executionEngine')='codex_agent' ORDER BY rowid", (record["id"],)).fetchall()
            visible = []
            for row in rows:
                if session:
                    _, _, meta, _ = self._codex_work_job_row(db, row["id"])
                    try:
                        self._codex_work_phone_run_scope(db, session, meta["source"])
                    except _api().WorkflowError:
                        continue
                visible.append(self._public_codex_work_job(row, prefix))
            result = {"recordId": record["id"], "runs": visible, "revision": self._revision(db)}
            if session:
                result["scope"] = self._codex_work_phone_public_scope(session)
            if authorize:
                authorize()
            return result

    def _recover_codex_work(self, db):
        recovered = 0
        for row in db.execute("SELECT * FROM jobs WHERE json_extract(payload,'$.executionEngine')='codex_agent' AND status IN ('starting','running','cancelling')").fetchall():
            payload = json.loads(row["payload"])
            payload["codexWork"]["phase"] = "needs_review"
            payload["codexWork"]["recoveredAt"] = _api()._now()
            db.execute("UPDATE jobs SET status='needs_review',payload=?,error=?,updated_at=? WHERE id=?",
                       (_api()._json(payload), "codex_work_restart_needs_review", _api()._now(), row["id"]))
            recovered += 1
        return recovered

    def codex_work_active(self):
        # Unknown is not proof of termination; do not update over an unknown child.
        controller = getattr(self, "codex_work", None)
        setup_status = getattr(controller, "setup_status", None)
        if callable(setup_status) and setup_status().get("busy") is True:
            return True
        with self._db() as db:
            rows = db.execute("SELECT * FROM jobs WHERE json_extract(payload,'$.executionEngine')='codex_agent' AND status IN ('starting','running','cancelling','needs_review')").fetchall()
            controller = getattr(self, "codex_work", None)
            for row in rows:
                meta = json.loads(row["payload"]).get("codexWork", {})
                terminal = meta.get("terminal") or {}
                try:
                    snapshot = controller.snapshot(row["id"]) if controller is not None else None
                except _api().WorkflowError:
                    # A fresh controller correctly refuses to adopt historical runs.
                    snapshot = None
                if (row["status"] == "needs_review" and terminal.get("terminalEventObserved") is True
                        and isinstance(snapshot, dict) and snapshot.get("runId") == row["id"]
                        and snapshot.get("sourceSha256") == meta.get("sourceSha256")
                        and snapshot.get("threadId") == meta.get("threadId") and snapshot.get("turnId") == meta.get("turnId")
                        and snapshot.get("active") is False):
                    continue
                return True
            return False

    @staticmethod
    def _codex_work_event_shape(event):
        base = {"type", "runId", "threadId", "turnId", "sourceSha256", "observedAt"}
        extras = {"prepared": {"requestedProfile", "actualModel", "actualEffort", "sandboxVerified", "preparationReceipt"},
                  "send_intent": {"model", "effort"}, "turn_started": {"actualModel", "actualEffort"},
                  "progress": {"kind", "itemId", "text"}, "plan": {"plan"},
                  "item_status": {"itemId", "itemType", "completed"}, "approval_blocked": {"code"},
                  "file_tools_blocked": {"code"},
                  "provider_error": {"code", "retryAllowed"}, "interrupt_intent": set(),
                  "cancel_requested": {"cancellationVerified"}}
        kind = event.get("type") if isinstance(event, dict) else None
        if kind == "terminal":
            required = base | {"status", "terminalStatus", "terminalEventObserved", "report", "error",
                               "cancellationVerified", "executionVerified", "retryAllowed"}
            if not required <= set(event) or set(event) - required - {"actualModel", "actualEffort"}:
                return False
        elif kind not in extras or set(event) != base | extras[kind]:
            return False
        try:
            _api()._id(event["runId"])
            _digest(event["sourceSha256"])
            _api().WorkflowService._source_time(event["observedAt"])
            for key in ("threadId", "turnId"):
                if event[key] is not None:
                    _remote_id(event[key])
        except (ValueError, TypeError):
            return False
        return True

    def _codex_work_preparation_valid(self, event, source):
        from workflow_codex_work import valid_preparation_receipt
        receipt = event.get("preparationReceipt")
        return (type(receipt) is dict and type(event["sandboxVerified"]) is bool
                and event["sandboxVerified"] == (receipt.get("schemaVersion") == 1)
                and event["requestedProfile"] == source["requestedProfile"]
                and event["actualModel"] == source["subscription"]["modelSlug"]
                and event["actualEffort"] == EFFORT[source["requestedProfile"]]
                and valid_preparation_receipt(receipt,
                    allowed_root=source["workspace"]["allowedRoot"],
                    image_root=self.data_dir / "codex-work" / event["runId"] / "images",
                    model=source["subscription"]["modelSlug"], effort=EFFORT[source["requestedProfile"]],
                    thread_id=event["threadId"]))

    def _codex_work_event(self, event):
        if not self._codex_work_event_shape(event):
            return False
        try:
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                row, payload, meta, review = self._codex_work_job_row(db, event["runId"])
                source, kind = meta["source"], event["type"]
                if event["sourceSha256"] != meta["sourceSha256"]:
                    return False
                thread, turn = event["threadId"], event["turnId"]
                if meta["threadId"] is not None and thread != meta["threadId"] or meta["turnId"] is not None and turn != meta["turnId"]:
                    return False
                if row["status"] in {"completed", "interrupted", "failed"}:
                    return kind == "terminal" and meta.get("terminal") == event
                if row["status"] == "needs_review" and kind in {"prepared", "send_intent", "turn_started"}:
                    return False
                if row["status"] == "needs_review" and kind == "interrupt_intent" and not meta.get("fileToolsBlocked"):
                    return False
                model, effort = source["subscription"]["modelSlug"], EFFORT[source["requestedProfile"]]
                status = row["status"]
                if kind == "prepared":
                    if (status != "starting" or meta["prepared"] or not thread or turn is not None
                            or event["requestedProfile"] != source["requestedProfile"] or event["actualModel"] != model
                            or event["actualEffort"] != effort or not self._codex_work_preparation_valid(event, source)):
                        return False
                    self._codex_work_workspace(db, source["workspace"]["id"], source["workspace"]["authorizationSha256"])
                    self._codex_work_binding(source["subscription"])
                    self._codex_work_images(db, source["recordId"], source["attachmentIds"], source["images"])
                    receipt = json.loads(_api()._json(event))
                    meta.update(threadId=thread, prepared=True, actualModel=model, actualEffort=effort,
                                preparationReceipt=receipt, preparationReceiptSha256=_sha(receipt))
                elif kind == "send_intent":
                    if (not meta["prepared"] or meta.get("preparationReceipt") is None
                            or meta["sendIntent"] is not None or not thread or turn is not None
                            or event["model"] != model or event["effort"] != effort or meta["cancelRequest"]):
                        return False
                    self._codex_work_workspace(db, source["workspace"]["id"], source["workspace"]["authorizationSha256"])
                    self._codex_work_binding(source["subscription"])
                    self._codex_work_images(db, source["recordId"], source["attachmentIds"], source["images"])
                    if self._codex_work_inventory(Path(source["workspace"]["allowedRoot"])) != review["beforeFiles"]:
                        return False
                    meta["sendIntent"] = dict(event)
                elif kind == "turn_started":
                    if not meta["sendIntent"] or not thread or not turn or event["actualModel"] != model or event["actualEffort"] != effort:
                        return False
                    meta.update(threadId=thread, turnId=turn)
                    status = "cancelling" if meta["cancelRequest"] else "running"
                elif kind in {"progress", "plan", "item_status", "approval_blocked", "file_tools_blocked", "provider_error", "interrupt_intent", "cancel_requested"}:
                    if not meta["sendIntent"] or not thread or not turn or meta["turnId"] != turn:
                        return False
                    if kind == "progress":
                        if (event["kind"] not in {"item/agentMessage/delta", "item/commandExecution/outputDelta", "item/fileChange/outputDelta", "console_file_write"}
                                or not isinstance(event["itemId"], str) or len(event["itemId"]) > 512
                                or not isinstance(event["text"], str) or len(event["text"]) > MAX_TEXT or "\0" in event["text"]):
                            return False
                        progress = meta["progress"]
                        if progress and all(progress[-1].get(key) == event[key] for key in ("kind", "itemId")):
                            if len(progress[-1]["text"]) + len(event["text"]) <= MAX_TEXT:
                                progress[-1]["text"] += event["text"]
                            else:
                                progress.append({key: event[key] for key in ("kind", "itemId", "text")})
                        else:
                            progress.append({key: event[key] for key in ("kind", "itemId", "text")})
                        while len(progress) > 100 or sum(len(item["text"]) for item in progress) > MAX_PROGRESS:
                            progress.pop(0)
                        meta["progressTruncated"] = meta.get("progressTruncated", False) or len(progress) == 100
                    elif kind == "plan":
                        if (not isinstance(event["plan"], list) or len(event["plan"]) > 100
                                or any(not isinstance(item, dict) or set(item) != {"step", "status"}
                                       or not isinstance(item["step"], str) or len(item["step"]) > 2000
                                       or item["status"] not in {"pending", "inProgress", "completed"} for item in event["plan"])):
                            return False
                        meta["plan"] = event["plan"]
                    elif kind == "item_status":
                        if (not isinstance(event["itemId"], str) or len(event["itemId"]) > 512
                                or event["itemType"] not in {"agentMessage", "commandExecution", "fileChange", "reasoning", "userMessage", "other"}
                                or type(event["completed"]) is not bool):
                            return False
                        meta["lastItem"] = {key: event[key] for key in ("itemId", "itemType", "completed")}
                    elif kind == "approval_blocked":
                        if event["code"] != "codex_work_additional_approval_required":
                            return False
                        meta["approvalBlocked"] = True
                    elif kind == "file_tools_blocked":
                        if (event["code"] != "codex_work_file_write_unverified" or meta.get("fileToolsBlocked")
                                or not self._codex_work_preparation_valid(meta.get("preparationReceipt", {}), source)
                                or meta["preparationReceipt"]["preparationReceipt"].get("schemaVersion") != 2):
                            return False
                        meta["fileToolsBlocked"] = True
                        meta["fileToolsBlockReceipt"] = dict(event)
                        status = "needs_review"
                    elif kind == "provider_error":
                        if event["code"] != "codex_work_provider_error" or event["retryAllowed"] is not False:
                            return False
                        meta["providerErrorObserved"] = True
                    elif kind == "interrupt_intent":
                        if meta["interruptIntent"] is not None or not (meta["cancelRequest"] or meta.get("approvalBlocked") or meta.get("fileToolsBlocked")):
                            return False
                        meta["interruptIntent"] = dict(event)
                        status = "needs_review" if meta.get("fileToolsBlocked") else "cancelling"
                    elif event["cancellationVerified"] is not False or meta["interruptIntent"] is None:
                        return False
                elif kind == "terminal":
                    status = self._codex_work_terminal(db, row, payload, meta, review, event)
                    if status is None:
                        return False
                meta["phase"], meta["lastObservedAt"] = status, event["observedAt"]
                db.execute("UPDATE jobs SET payload=?,status=?,updated_at=? WHERE id=?", (_api()._json(payload), status, _api()._now(), row["id"]))
                self._revision(db, True)
            return True
        except (ValueError, TypeError, OSError, KeyError):
            return False

    def _codex_work_terminal(self, db, row, payload, meta, review, event):
        if (event["status"] not in {"completed", "interrupted", "failed", "unknown"}
                or event["terminalStatus"] not in {None, "completed", "interrupted", "failed"}
                or type(event["terminalEventObserved"]) is not bool or event["executionVerified"] is not False
                or event["retryAllowed"] is not False or type(event["cancellationVerified"]) is not bool
                or not isinstance(event["report"], str) or len(event["report"]) > MAX_TEXT or "\0" in event["report"]
                or event["error"] is not None and (not isinstance(event["error"], str) or not re.fullmatch(r"[a-z0-9_]{1,160}", event["error"]))):
            return None
        observed = event["terminalEventObserved"]
        real = (observed and meta["sendIntent"] is not None and bool(event["threadId"]) and bool(event["turnId"]))
        status, files, message_id, verified, report_only = "needs_review", [], None, False, False
        source = meta["source"]
        actual = event.get("actualModel") == source["subscription"]["modelSlug"] and event.get("actualEffort") == EFFORT[source["requestedProfile"]]
        if not observed and event["terminalStatus"] is not None or event["cancellationVerified"] and (not real or event["terminalStatus"] != "interrupted"):
            return None
        if not meta["sendIntent"] and event["status"] == "failed" and not observed:
            status = "failed"
        elif real:
            meta.update(threadId=event["threadId"], turnId=event["turnId"])
            if (event["status"] == event["terminalStatus"] == "interrupted" and event["cancellationVerified"] is True
                    and not meta.get("fileToolsBlocked")):
                status = "interrupted"
            elif event["status"] == event["terminalStatus"] == "failed" and not meta.get("fileToolsBlocked"):
                status = "failed"
            elif (event["status"] == event["terminalStatus"] == "completed" and actual
                  and event["error"] is None and event["report"].strip() and not meta.get("providerErrorObserved")
                  and not meta.get("fileToolsBlocked")):
                try:
                    workspace = self._codex_work_workspace(db, source["workspace"]["id"], source["workspace"]["authorizationSha256"])
                    after = self._codex_work_inventory(Path(workspace["allowedRoot"]))
                    before = review["beforeFiles"]
                    for path in sorted(before.keys() | after.keys()):
                        if before.get(path) != after.get(path):
                            files.append({"path": path, "change": "added" if path not in before else "removed" if path not in after else "modified",
                                          "beforeSha256": before.get(path), "afterSha256": after.get(path)})
                    if len(files) > 256:
                        _fail("codex_work_diff_too_large")
                except (ValueError, OSError):
                    files = []
                else:
                    status, verified, report_only = "completed", bool(files), not files
                    message_id = self._message(db, row["record_id"], "assistant", event["report"], text_limit=MAX_TEXT)
        cancellation_verified = (status == "interrupted" and meta["interruptIntent"] is not None
                                 and (meta["cancelRequest"] is not None or meta.get("approvalBlocked") is True))
        meta.update(terminal=dict(event), actualModel=event.get("actualModel", meta["actualModel"]),
                    actualEffort=event.get("actualEffort", meta["actualEffort"]),
                    cancellationVerified=cancellation_verified, executionVerified=verified, reportOnly=report_only)
        result = {"source": "codex_agent", "sourceSha256": meta["sourceSha256"], "runId": row["id"],
                  "threadId": meta["threadId"], "turnId": meta["turnId"], "status": status,
                  "terminalEventObserved": observed, "terminalStatus": event["terminalStatus"],
                  "requestedModel": source["subscription"]["modelSlug"], "actualModel": meta["actualModel"],
                  "requestedProfile": source["requestedProfile"], "requestedEffort": EFFORT[source["requestedProfile"]],
                  "actualEffort": meta["actualEffort"], "text": event["report"], "messageId": message_id,
                  "changedFiles": files, "executionVerified": verified, "reportOnly": report_only,
                  "cancellationVerified": cancellation_verified, "retryAllowed": False,
                  "error": event["error"], "completedAt": event["observedAt"]}
        db.execute("UPDATE jobs SET result=?,error=? WHERE id=?", (_api()._json(result), event["error"] or ("codex_work_outcome_needs_review" if status == "needs_review" else ""), row["id"]))
        return status
