"""Independent, explicitly submitted phone inputs for the bound Codex Guide."""
import hashlib
import json
import re
from urllib.parse import parse_qs, urlencode

from workflow_guide_reply import _api, _digest, _request


def _source_error():
    return _api().WorkflowError("Guide 输入来源无法核对，原内容保留。", 409, "guide_source_not_matching")


def _exact_query(query, fields, limit=1024):
    values = parse_qs(query, keep_blank_values=True)
    if len(query) > limit or set(values) != fields or any(len(value) != 1 for value in values.values()):
        raise _api().WorkflowError("Guide 读取地址无效。")
    return {key: value[0] for key, value in values.items()}


class GuideInputMixin:
    @staticmethod
    def _guide_input_prefix(prefix):
        if prefix not in {"/api/workflow", "/api/phone/workflow"}:
            raise _api().WorkflowError("Guide 输入入口无效。", 403)

    @staticmethod
    def _guide_input_receipt(row):
        return {"requestId": row["request_id"], "target": "codex_guide", "clientId": row["client_id"],
            "sessionId": row["session_id"], "recordId": row["record_id"], "sourceUserMessageId": row["message_id"],
            "sourceGuideChatId": row["source_guide_chat_id"], "textSha256": row["text_sha256"],
            "sourceSha256": _digest(_api()._json({"sourceSnapshot": json.loads(row["source_snapshot"]),
                "attachmentProofs": json.loads(row["attachment_proofs"])})),
            "attachmentIds": json.loads(row["attachment_ids"]), "expectedRevision": row["expected_revision"],
            "acceptedSessionRevision": row["expected_revision"] + 1, "acceptedAt": row["created_at"]}

    def _guide_input_public(self, db, row):
        reply = db.execute("SELECT message_id FROM guide_replies WHERE source_user_message_id=? AND client_id=? "
            "AND session_id=? AND record_id=? AND source_guide_chat_id=? ORDER BY rowid DESC LIMIT 1",
            (row["message_id"], row["client_id"], row["session_id"], row["record_id"], row["source_guide_chat_id"])).fetchone()
        return {"requestId": row["request_id"], "target": "codex_guide", "clientId": row["client_id"],
            "sessionId": row["session_id"], "recordId": row["record_id"], "sourceUserMessageId": row["message_id"],
            "status": "replied" if reply else "waiting", "replyMessageId": reply[0] if reply else None,
            "acceptedAt": row["created_at"]}

    def _guide_input_state(self, db, session):
        binding = self._guide_binding(db)
        rows = db.execute("SELECT * FROM guide_inputs WHERE client_id=? AND session_id=? AND record_id=? "
            "ORDER BY seq DESC LIMIT 64", (session["clientId"], session["id"], session["recordId"])).fetchall() if session else []
        return {"available": binding["bound"], "target": "codex_guide", "author": "Codex Guide",
            "requests": [self._guide_input_public(db, row) for row in reversed(rows)], "coordinationIntervalSeconds": 60}

    def _guide_input_event_proof(self, db, session):
        return [{**self._guide_input_public(db, row), "textSha256": row["text_sha256"],
                 "sourceGuideChatId": row["source_guide_chat_id"]} for row in db.execute(
            "SELECT * FROM guide_inputs WHERE client_id=? AND session_id=? AND record_id=? ORDER BY seq DESC LIMIT 64",
            (session["clientId"], session["id"], session["recordId"]))]

    def _guide_input_message_sources(self, db, record_id):
        return {row["message_id"]: self._guide_input_public(db, row) for row in
            db.execute("SELECT * FROM guide_inputs WHERE record_id=? ORDER BY seq", (record_id,))}

    def _guide_input_validate(self, db, row, session, *, verify_files=False):
        """Readonly proof of one direct input. Never fall back to a model job."""
        try:
            user = db.execute("SELECT * FROM messages WHERE id=?", (row["message_id"],)).fetchone()
            legacy = db.execute("SELECT 1 FROM mobile_message_sources WHERE message_id=?", (row["message_id"],)).fetchone()
            body = json.loads(row["request_body"])
            ids = json.loads(row["attachment_ids"])
            proofs = json.loads(row["attachment_proofs"])
            snapshot = json.loads(row["source_snapshot"])
            receipt = self._guide_input_receipt(row)
            request = db.execute("SELECT * FROM requests WHERE id=?", (row["request_id"],)).fetchone()
            frozen = snapshot.get("mobileDialogue") if isinstance(snapshot, dict) else None
            source_task = snapshot.get("sourceTask") if isinstance(snapshot, dict) else None
            idea_context = snapshot.get("ideaContext") if isinstance(snapshot, dict) else None
            source_shape = (isinstance(snapshot, dict) and set(snapshot) == {"mobileDialogue", "sourceTask", "ideaContext"}
                and isinstance(frozen, dict) and set(frozen) == {"id", "clientId", "recordId", "ideaId", "ideaRevision", "revision"})
            if source_shape:
                if frozen["ideaId"] is None:
                    source_shape = frozen["ideaRevision"] is None and source_task is None and idea_context is None
                else:
                    source_shape = (isinstance(source_task, dict) and isinstance(idea_context, dict)
                        and _api()._id(frozen["ideaId"]) == source_task.get("ideaId") == idea_context.get("id")
                        and type(frozen["ideaRevision"]) is int and frozen["ideaRevision"] > 0
                        and frozen["ideaRevision"] == source_task.get("revision") == idea_context.get("revision"))
            matching = (user is not None and legacy is None and user["role"] == "user"
                and row["client_id"] == session["clientId"] and row["session_id"] == session["id"]
                and row["record_id"] == session["recordId"] == user["record_id"]
                and row["source_guide_chat_id"] == self._guide_binding(db)["sourceGuideChatId"]
                and self._guide_chat(row["source_guide_chat_id"]) == row["source_guide_chat_id"]
                and _request(row["request_id"]) == row["request_id"]
                and type(row["expected_revision"]) is int and row["expected_revision"] > 0
                and row["created_at"] == user["created_at"] and row["text_sha256"] == _digest(user["text"])
                and isinstance(ids, list) and len(ids) <= _api().MAX_ATTACHMENTS and len(set(ids)) == len(ids)
                and ids == json.loads(user["attachment_ids"])
                and isinstance(proofs, list) and all(isinstance(proof, dict)
                    and set(proof) == {"id", "name", "filename", "sha256", "size", "mimeType"} for proof in proofs)
                and [proof["id"] for proof in proofs] == ids
                and source_shape and frozen.get("clientId") == session["clientId"]
                and frozen.get("id") == session["id"] and frozen.get("recordId") == session["recordId"]
                and frozen.get("revision") == row["expected_revision"]
                and body == {"requestId": row["request_id"], "clientId": row["client_id"], "sessionId": row["session_id"],
                    "recordId": row["record_id"], "expectedRevision": row["expected_revision"],
                    "text": user["text"], "attachmentIds": ids}
                and request is not None and request["kind"] == "mobile_dialogue_guide_send"
                and request["fingerprint"] == hashlib.sha256(_api()._json(body).encode("utf-8")).hexdigest()
                and json.loads(request["response"]) == {"sessionId": row["session_id"], "guideSendReceipt": receipt})
            if not matching:
                raise _source_error()
            if verify_files:
                for proof in proofs:
                    image = self._mobile_image_row(db, session["recordId"], proof["id"])
                    actual = self._mobile_image_proof(image)
                    if (set(proof) != {"id", "name", "filename", "sha256", "size", "mimeType"}
                            or proof["name"] != image["name"] or proof["filename"] != image["filename"]
                            or {key: proof[key] for key in actual} != actual):
                        raise _source_error()
            return user, receipt, snapshot, proofs
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            raise _source_error() from None

    def mobile_dialogue_guide_send(self, body, *, prefix="/api/workflow", authorize=None):
        self._guide_input_prefix(prefix)
        fields = {"requestId", "clientId", "sessionId", "recordId", "expectedRevision", "text", "attachmentIds"}
        identifier = self._guide_body(body, fields)
        from workflow_mobile_dialogue import _client
        client_id = _client(body["clientId"])
        if identifier != body["requestId"] or client_id != body["clientId"]:
            raise _api().WorkflowError("Guide 输入身份格式无效。")
        record_id = _api()._id(body["recordId"])
        text = _api()._text(body["text"])
        text_sha256 = _digest(text)
        if authorize:
            authorize()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            saved = self._receipt(db, "mobile_dialogue_guide_send", body)
            duplicate = saved is not None
            if saved is None:
                session = self._mobile_guard(db, body, client_id)
                self._mobile_source_guard(db, session)
                if session["recordId"] != record_id:
                    raise _source_error()
                binding = self._guide_binding(db)
                if not binding["bound"]:
                    raise _api().WorkflowError("电脑尚未连接 Codex Guide，草稿保留。", 409, "guide_not_connected")
                guide_chat_id = self._guide_chat(binding["sourceGuideChatId"])
                ids = self._mobile_selected_images(db, session, body["attachmentIds"])
                self._context(db, record_id, {"attachmentIds": ids})
                if not text.strip() and not ids:
                    raise _api().WorkflowError("请输入内容或选择附件。")
                proofs = []
                for image_id in ids:
                    image = self._mobile_image_row(db, record_id, image_id)
                    proofs.append({"id": image_id, "name": image["name"], "filename": image["filename"], **self._mobile_image_proof(image)})
                source = self._source_task(db, record_id,
                    {"ideaId": session["ideaId"], "revision": session["ideaRevision"]} if session["ideaId"] else None)
                if source and not session["ideaId"]:
                    raise _source_error()
                snapshot = {"mobileDialogue": {key: session[key] for key in
                    ("id", "clientId", "recordId", "ideaId", "ideaRevision", "revision")}, "sourceTask": source,
                    "ideaContext": self._mobile_current_idea_context(db, source) if source else None}
                now = _api()._now()
                message_id = self._message(db, record_id, "user", text, attachment_ids=ids, created_at=now)
                db.execute("INSERT INTO guide_inputs (request_id,message_id,client_id,session_id,record_id,source_guide_chat_id,"
                    "expected_revision,text_sha256,attachment_ids,attachment_proofs,source_snapshot,request_body,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (identifier, message_id, client_id, session["id"], record_id, guide_chat_id, body["expectedRevision"],
                     text_sha256, _api()._json(ids), _api()._json(proofs), _api()._json(snapshot), _api()._json(body), now))
                session["draft"] = {"text": "", "attachmentIds": []}
                self._mobile_save_session(db, session)
                row = db.execute("SELECT * FROM guide_inputs WHERE request_id=?", (identifier,)).fetchone()
                saved = {"sessionId": session["id"], "guideSendReceipt": self._guide_input_receipt(row)}
                self._receipt(db, "mobile_dialogue_guide_send", body, saved)
                self._revision(db, True)
            if authorize:
                authorize()
        return self._mobile_state(client_id, prefix, saved["sessionId"], guideSendReceipt=saved["guideSendReceipt"], duplicate=duplicate)

    def mobile_dialogue_guide_send_receipt(self, query="", *, prefix="/api/workflow", authorize=None):
        self._guide_input_prefix(prefix)
        params = _exact_query(query, {"requestId", "clientId", "sessionId", "recordId"})
        from workflow_mobile_dialogue import _client
        identifier, client_id = _request(params["requestId"]), _client(params["clientId"])
        session_id, record_id = _api()._id(params["sessionId"]), _api()._id(params["recordId"])
        def read(db):
            row = db.execute("SELECT * FROM guide_inputs WHERE request_id=?", (identifier,)).fetchone()
            if row is None:
                raise _api().WorkflowError("Guide 输入回执不存在。", 404, "guide_send_receipt_not_found")
            session = self._mobile_session(db, client_id, session_id)
            if session["recordId"] != record_id:
                raise _source_error()
            _, receipt, _, _ = self._guide_input_validate(db, row, session)
            return {"guideSendReceipt": receipt, "isCurrent": self._mobile_client_state(db, client_id)["currentSessionId"] == session_id}
        return self._guide_read(read, authorize)

    def mobile_dialogue_guide_inbox(self, query="", *, prefix="/api/workflow", desktop=False, authorize=None):
        self._guide_desktop(prefix, desktop)
        params = _exact_query(query, {"sourceGuideChatId", "clientId", "cursor", "limit"})
        from workflow_mobile_dialogue import _client
        guide_chat_id, client_id = self._guide_chat(params["sourceGuideChatId"]), _client(params["clientId"])
        if (client_id != params["clientId"] or not re.fullmatch(r"0|[1-9][0-9]{0,18}", params["cursor"])
                or int(params["cursor"]) > 9223372036854775807 or not re.fullmatch(r"[1-9][0-9]?", params["limit"])
                or int(params["limit"]) > 20):
            raise _api().WorkflowError("Guide 收件箱分页无效。")
        cursor, limit = int(params["cursor"]), int(params["limit"])
        def read(db):
            if self._guide_binding(db)["sourceGuideChatId"] != guide_chat_id:
                raise _source_error()
            if cursor:
                prior = db.execute("SELECT client_id,source_guide_chat_id FROM guide_inputs WHERE seq=?", (cursor,)).fetchone()
                if prior is None or prior["client_id"] != client_id or prior["source_guide_chat_id"] != guide_chat_id:
                    raise _api().WorkflowError("Guide 收件箱游标不属于此范围。", 409, "guide_cursor_not_matching")
            rows = db.execute("SELECT g.* FROM guide_inputs g WHERE g.source_guide_chat_id=? AND g.client_id=? AND g.seq>? "
                "AND NOT EXISTS (SELECT 1 FROM guide_replies r WHERE r.source_user_message_id=g.message_id AND r.client_id=g.client_id "
                "AND r.session_id=g.session_id AND r.record_id=g.record_id AND r.source_guide_chat_id=g.source_guide_chat_id) "
                "ORDER BY g.seq LIMIT ?", (guide_chat_id, client_id, cursor, limit + 1)).fetchall()
            items = []
            for row in rows[:limit]:
                session = self._mobile_session(db, client_id, row["session_id"])
                user, receipt, snapshot, proofs = self._guide_input_validate(db, row, session, verify_files=True)
                items.append({**self._guide_input_public(db, row), "sequence": str(row["seq"]), "guideSendReceipt": receipt,
                    "sourceGuideChatId": guide_chat_id, "text": user["text"], "sourceSnapshot": snapshot,
                    "images": [{key: proof[key] for key in ("id", "name", "mimeType", "size", "sha256")} |
                        {"url": prefix + "/attachment?" + urlencode({"id": proof["id"]})} for proof in proofs],
                    "isCurrent": self._mobile_client_state(db, client_id)["currentSessionId"] == row["session_id"]})
            return {"target": "codex_guide", "author": "Codex Guide", "sourceGuideChatId": guide_chat_id,
                "clientId": client_id, "items": items, "nextCursor": str(rows[min(limit, len(rows)) - 1]["seq"]) if rows else str(cursor),
                "hasMore": len(rows) > limit}
        return self._guide_read(read, authorize)
