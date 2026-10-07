"""Trusted desktop Guide replies, separate from model/relay job receipts."""
from contextlib import closing
import hashlib
import json
import sqlite3
from urllib.parse import parse_qs
import uuid


def _api():
    import workflow_service
    return workflow_service


def _request(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise _api().WorkflowError("Guide 请求身份无效。") from None


def _digest(text):
    try:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    except UnicodeError:
        raise _api().WorkflowError("Guide 正文必须是有效 UTF-8 文字。") from None


def _object(value):
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    except (ValueError, TypeError):
        pass
    raise _api().WorkflowError("Guide 冻结来源结构无法核对。", 409, "guide_source_not_matching")


class GuideReplyMixin:
    @staticmethod
    def _guide_desktop(prefix, desktop):
        if desktop is not True or prefix != "/api/workflow":
            raise _api().WorkflowError("Guide 回答只允许受信任电脑端写入和读取。", 403, "guide_desktop_required")

    @staticmethod
    def _guide_body(body, fields):
        if not isinstance(body, dict) or set(body) != fields:
            raise _api().WorkflowError("Guide 请求字段无效。")
        return _request(body["requestId"])

    @staticmethod
    def _guide_chat(value):
        identifier = _request(value)
        if identifier != value:
            raise _api().WorkflowError("Guide 会话身份无效。")
        return identifier

    @staticmethod
    def _guide_binding(db):
        row = db.execute("SELECT chat_id FROM guide_sources WHERE id=1").fetchone()
        return {"bound": row is not None, "kind": "codex_guide", "author": "Codex Guide",
                "sourceGuideChatId": row[0] if row else None}

    def _guide_read(self, operation, authorize):
        if authorize:
            authorize()
        with self._lock, closing(sqlite3.connect((self.data_dir / "workflow.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            result = operation(db)
            if authorize:
                authorize()
            return result

    def mobile_dialogue_guide_source_get(self, query="", *, prefix="/api/workflow", desktop=False, authorize=None):
        self._guide_desktop(prefix, desktop)
        if query:
            raise _api().WorkflowError("Guide 绑定读取地址无效。")
        return self._guide_read(self._guide_binding, authorize)

    def mobile_dialogue_guide_source(self, body, *, prefix="/api/workflow", desktop=False, authorize=None):
        self._guide_desktop(prefix, desktop)
        request_id = self._guide_body(body, {"requestId", "sourceGuideChatId"})
        chat_id = self._guide_chat(body["sourceGuideChatId"])
        if authorize:
            authorize()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            result = self._receipt(db, "mobile_dialogue_guide_source", body)
            if result is None:
                binding = self._guide_binding(db)
                if binding["bound"] and binding["sourceGuideChatId"] != chat_id:
                    raise _api().WorkflowError("已绑定另一 Guide 会话。", 409, "guide_source_conflict")
                if not binding["bound"]:
                    db.execute("INSERT INTO guide_sources VALUES (1,?,?,?)", (chat_id, request_id, _api()._now()))
                    self._revision(db, True)
                result = self._guide_binding(db)
                self._receipt(db, "mobile_dialogue_guide_source", body, result)
            if authorize:
                authorize()
        return result

    @staticmethod
    def _guide_public_source(row):
        return {"kind": "codex_guide", "author": "Codex Guide", "messageId": row["message_id"],
            "clientId": row["client_id"], "sessionId": row["session_id"], "recordId": row["record_id"],
            "sourceUserMessageId": row["source_user_message_id"], "sourceGuideChatId": row["source_guide_chat_id"],
            "requestId": row["request_id"], "textSha256": row["text_sha256"]}

    def _guide_message_sources(self, db, record_id):
        return {row["message_id"]: self._guide_public_source(row) for row in db.execute(
            "SELECT * FROM guide_replies WHERE record_id=?", (record_id,))}

    def _guide_event_proof(self, db, session):
        return [self._guide_public_source(row) for row in db.execute(
            "SELECT * FROM guide_replies WHERE client_id=? AND session_id=? AND record_id=? ORDER BY rowid DESC LIMIT 64",
            (session["clientId"], session["id"], session["recordId"]))]

    def _guide_history(self, db, record_id, dialogue=None):
        """Filter scoped Guide rows before the history limit; plain history is unchanged."""
        if dialogue is None:
            return db.execute("SELECT rowid,* FROM messages WHERE record_id=? ORDER BY rowid DESC LIMIT 12", (record_id,)).fetchall()
        return db.execute("SELECT m.rowid,m.* FROM messages m WHERE m.record_id=? AND (NOT EXISTS "
            "(SELECT 1 FROM guide_replies g WHERE g.message_id=m.id) OR EXISTS "
            "(SELECT 1 FROM guide_replies g WHERE g.message_id=m.id AND g.client_id=? AND g.session_id=? AND g.record_id=?)) "
            "ORDER BY m.rowid DESC LIMIT 12", (record_id, dialogue["clientId"], dialogue["id"], record_id)).fetchall()

    def _guide_bind_user_message(self, db, message_id, session, job_id, request_id):
        row = db.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        if row is None or row["role"] != "user" or row["record_id"] != session["recordId"]:
            raise _api().WorkflowError("Guide 原问题来源无法核对。", 409, "guide_source_not_matching")
        values = (message_id, session["clientId"], session["id"], session["recordId"], _request(request_id),
                  job_id, _digest(row["text"]), _api()._json(json.loads(row["attachment_ids"])), row["created_at"])
        prior = db.execute("SELECT * FROM mobile_message_sources WHERE message_id=?", (message_id,)).fetchone()
        if prior:
            if tuple(prior) != values:
                raise _api().WorkflowError("Guide 原问题绑定发生冲突。", 409, "guide_source_not_matching")
        else:
            db.execute("INSERT INTO mobile_message_sources VALUES (?,?,?,?,?,?,?,?,?)", values)

    def _guide_original_send(self, db, user, session):
        """Recover only one unambiguous original send, never infer from latest history."""
        api = _api()
        attachments = json.loads(user["attachment_ids"])
        matching_users = [row for row in db.execute("SELECT * FROM messages WHERE role='user' AND record_id=? AND created_at=? AND text=?",
            (user["record_id"], user["created_at"], user["text"])) if json.loads(row["attachment_ids"]) == attachments]
        if len(matching_users) != 1:
            raise api.WorkflowError("历史原问题存在歧义，未写入 Guide 回答。", 409, "guide_source_not_matching")
        candidates = []
        for job in db.execute("SELECT * FROM jobs WHERE record_id=? AND kind='discuss' AND created_at=? AND attempt=1 AND parent_id IS NULL",
                (user["record_id"], user["created_at"])):
            payload = _object(job["payload"])
            context = payload.get("context")
            if not isinstance(context, dict):
                raise api.WorkflowError("历史发送结构无法核对。", 409, "guide_source_not_matching")
            if payload.get("text") == user["text"] and context.get("attachmentIds") == attachments:
                candidates.append((job, payload))
        if len(candidates) != 1:
            raise api.WorkflowError("历史发送来源存在歧义，未写入 Guide 回答。", 409, "guide_source_not_matching")
        job, payload = candidates[0]
        frozen = payload.get("appFrozen", {})
        if not isinstance(frozen, dict) or not isinstance(payload.get("appTarget"), dict):
            raise api.WorkflowError("历史冻结结构无法核对。", 409, "guide_source_not_matching")
        dispatch = db.execute("SELECT * FROM idea_dispatches WHERE id=?", (payload.get("appDispatchId"),)).fetchone()
        snapshot = _object(dispatch["snapshot"]) if dispatch else {}
        dialogue = payload.get("mobileDialogue")
        request_id = _request(job["request_id"])
        receipt = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        saved = _object(receipt["response"]) if receipt else {}
        # Browser Chat freezes its question in the canonical prompt, while the
        # subscription path additionally has appFrozen.text. Verify both forms.
        expected_prompt = {"recordTitle": frozen.get("recordTitle"), "projectName": frozen.get("projectName"),
            "question": payload.get("text"), "submissionTime": payload.get("submissionTime"),
            "history": frozen.get("history"), "selectedImages": frozen.get("images")}
        if payload.get("sourceTask"):
            expected_prompt["sourceTask"] = payload["sourceTask"]
        if frozen.get("mobileIdeaContext") is not None:
            expected_prompt["mobileIdeaContext"] = frozen["mobileIdeaContext"]
        images = frozen.get("images")
        if not isinstance(images, list) or any(not isinstance(image, dict) for image in images):
            raise api.WorkflowError("历史原图冻结结构无法核对。", 409, "guide_source_not_matching")
        try:
            if dispatch is None or not isinstance(payload.get("submissionTime"), dict):
                raise api.WorkflowError("历史提交确认时间无法核对。")
            proven_job = self._app_dispatch_job(db, dispatch, snapshot)
        except (api.WorkflowError, ValueError, KeyError, TypeError, AttributeError):
            raise api.WorkflowError("历史提交冻结来源无法核对。", 409, "guide_source_not_matching") from None
        matches = (isinstance(dialogue, dict) and dialogue == frozen.get("mobileDialogue") == snapshot.get("mobileDialogue")
            and dialogue.get("clientId") == session["clientId"] and dialogue.get("id") == session["id"]
            and dialogue.get("recordId") == session["recordId"] == user["record_id"] == job["record_id"]
            and payload.get("purpose") == "discussion" and payload.get("appTarget", {}).get("kind") == "chatgpt"
            and payload.get("appTarget", {}).get("mode") == "new"
            and proven_job["id"] == job["id"]
            and payload.get("sourceTask") == frozen.get("sourceTask") == snapshot.get("sourceTask")
            and snapshot.get("origin") == "workflow_discussion" and snapshot.get("purpose") == "discuss"
            and snapshot.get("recordId") == user["record_id"] and snapshot.get("jobId") == job["id"]
            and snapshot.get("attachmentIds") == attachments and isinstance(images, list)
            and [image.get("id") for image in images] == attachments
            and ("text" not in frozen or frozen["text"] == user["text"])
            and payload.get("submissionTime") == frozen.get("submissionTime") == snapshot.get("submissionTime")
            and dispatch is not None and dispatch["created_at"] == job["created_at"] == user["created_at"]
            and dispatch["request_id"] == request_id
            and dispatch["prompt"].endswith(api._json(expected_prompt))
            and receipt is not None and receipt["kind"] == "mobile_dialogue_send"
            and set(saved) in ({"sessionId", "jobId"}, {"sessionId", "jobId", "sourceMessageId"})
            and saved.get("sessionId") == session["id"] and saved.get("jobId") == job["id"]
            and ("sourceMessageId" not in saved or saved["sourceMessageId"] == user["id"]))
        if not matches:
            raise api.WorkflowError("历史原问题与冻结发送来源不一致。", 409, "guide_source_not_matching")
        return job["id"], request_id

    def _guide_user_source(self, db, message_id, session):
        user = db.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        if user is None or user["role"] != "user" or user["record_id"] != session["recordId"]:
            raise _api().WorkflowError("Guide 原问题不属于指定讨论。", 409, "guide_source_not_matching")
        source = db.execute("SELECT * FROM mobile_message_sources WHERE message_id=?", (message_id,)).fetchone()
        if source is None:
            job_id, request_id = self._guide_original_send(db, user, session)
            self._guide_bind_user_message(db, message_id, session, job_id, request_id)
            source = db.execute("SELECT * FROM mobile_message_sources WHERE message_id=?", (message_id,)).fetchone()
        if (source["client_id"] != session["clientId"] or source["session_id"] != session["id"]
                or source["record_id"] != session["recordId"] or source["text_sha256"] != _digest(user["text"])
                or json.loads(source["attachment_ids"]) != json.loads(user["attachment_ids"])
                or source["created_at"] != user["created_at"]):
            raise _api().WorkflowError("Guide 原问题不属于指定讨论。", 409, "guide_source_not_matching")

    def mobile_dialogue_guide_reply_get(self, query="", *, prefix="/api/workflow", desktop=False, authorize=None):
        self._guide_desktop(prefix, desktop)
        params = parse_qs(query, keep_blank_values=True)
        if len(query) > 100 or set(params) != {"requestId"} or len(params["requestId"]) != 1:
            raise _api().WorkflowError("Guide 回执地址无效。")
        identifier = _request(params["requestId"][0])
        def read(db):
            row = db.execute("SELECT * FROM requests WHERE id=? AND kind='mobile_dialogue_guide_reply'", (identifier,)).fetchone()
            if row is None:
                raise _api().WorkflowError("Guide 回执不存在。", 404, "guide_receipt_not_found")
            return json.loads(row["response"])
        return self._guide_read(read, authorize)

    def mobile_dialogue_guide_reply(self, body, *, prefix="/api/workflow", desktop=False, authorize=None):
        self._guide_desktop(prefix, desktop)
        identifier = self._guide_body(body, {"requestId", "clientId", "sessionId", "recordId", "sourceUserMessageId", "sourceGuideChatId", "text"})
        api = _api()
        from workflow_mobile_dialogue import _client
        client_id = _client(body["clientId"])
        session_id, record_id, user_id = (api._id(body[key]) for key in ("sessionId", "recordId", "sourceUserMessageId"))
        chat_id = self._guide_chat(body["sourceGuideChatId"])
        # Keep the exact original characters, including surrounding whitespace.
        text = api._text(body["text"])
        if not text.strip():
            raise api.WorkflowError("Guide 回答正文不能为空。")
        text_sha256 = _digest(text)
        if authorize:
            authorize()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            result = self._receipt(db, "mobile_dialogue_guide_reply", body)
            if result is None:
                binding = self._guide_binding(db)
                if not binding["bound"] or binding["sourceGuideChatId"] != chat_id:
                    raise api.WorkflowError("Guide 会话未绑定或来源不一致。", 409, "guide_source_not_matching")
                session = self._mobile_session(db, client_id, session_id)
                if session["recordId"] != record_id:
                    raise api.WorkflowError("Guide 回答记录不属于指定讨论。", 409, "guide_source_not_matching")
                self._guide_user_source(db, user_id, session)
                now = api._now()
                # The role and author are server constants; no model job is made.
                message_id = self._message(db, record_id, "assistant", text, created_at=now)
                db.execute("INSERT INTO guide_replies VALUES (?,?,?,?,?,?,?,?,?)", (identifier, message_id, client_id,
                    session_id, record_id, user_id, chat_id, text_sha256, now))
                row = db.execute("SELECT * FROM guide_replies WHERE request_id=?", (identifier,)).fetchone()
                result = {"guideSource": self._guide_public_source(row),
                    "isCurrent": self._mobile_client_state(db, client_id)["currentSessionId"] == session_id}
                self._receipt(db, "mobile_dialogue_guide_reply", body, result)
                self._revision(db, True)
            if authorize:
                authorize()
        return result
