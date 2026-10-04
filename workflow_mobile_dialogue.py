"""Recoverable phone discussions and explicit idea saves in the existing store.

This module never sends an App message. A confirmed send freezes one discussion
into the existing outbox; delivery/profile capabilities remain unverified.
"""
from __future__ import annotations

import json
from urllib.parse import parse_qs
import uuid


PROFILES = {"fast", "high", "pro"}


def _api():
    import workflow_service
    return workflow_service


def _client(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise _api().WorkflowError("手机讨论身份无效。") from None


def _revision(value):
    if type(value) is not int or not 1 <= value <= 9007199254740991:
        raise _api().WorkflowError("请提供当前版本。")
    return value


def _query(query, allowed):
    values = parse_qs(query, keep_blank_values=True)
    if len(query) > 1024 or set(values) - allowed or any(len(items) != 1 for items in values.values()):
        raise _api().WorkflowError("手机讨论请求地址无效。")
    return {key: items[0] for key, items in values.items()}


def _body(body, allowed):
    if not isinstance(body, dict) or set(body) - allowed:
        raise _api().WorkflowError("手机讨论内容无效。")


class MobileDialogueMixin:
    def _mobile_client_state(self, db, client_id):
        return self._setting(db, "mobile-dialogue:client:" + client_id) or {"currentSessionId": None, "requestedProfile": "high"}

    def _mobile_session(self, db, client_id, session_id):
        session = self._setting(db, "mobile-dialogue:session:" + _api()._id(session_id))
        if not session or session["clientId"] != client_id:
            raise _api().WorkflowError("讨论不属于这台手机。", 403, "dialogue_not_matching")
        self._record(db, session["recordId"])
        return session

    def _mobile_guard(self, db, body, client_id):
        session = self._mobile_session(db, client_id, body.get("sessionId"))
        if self._mobile_client_state(db, client_id)["currentSessionId"] != session["id"]:
            raise _api().WorkflowError("当前讨论已切换；保留输入后重新读取。", 409, "dialogue_changed")
        if _revision(body.get("expectedRevision")) != session["revision"]:
            raise _api().WorkflowError("讨论草稿已在另一端更新；请保留输入后合并。", 409, "revision_conflict")
        return session

    def _mobile_project(self, db):
        projects = self._setting(db, "projects") or []
        return self._project(db, projects[0]["id"] if projects else "")

    def _mobile_new_record(self, db, title="当前讨论", text=""):
        api = _api()
        project = self._mobile_project(db)
        identifier, now = uuid.uuid4().hex, api._now()
        db.execute("INSERT INTO records VALUES (?,?,?,?,?,?,?)", (identifier, title, project["id"], now, now, None,
            api._json({"selectedText": "", "referenceIds": [], "attachmentIds": []})))
        if text:
            self._message(db, identifier, "user", text)
        return identifier

    def _mobile_new_session(self, db, client_id, idea=None):
        api = _api()
        client = self._mobile_client_state(db, client_id)
        record_id = self._setting(db, "task-record:" + idea["id"]) if idea else None
        if record_id:
            self._record(db, record_id)
        else:
            record_id = self._mobile_new_record(db, idea["title"] if idea else "当前讨论", idea["body"] if idea else "")
            if idea:
                self._set_setting(db, "task-record:" + idea["id"], record_id)
        identifier, now = uuid.uuid4().hex, api._now()
        session = {"id": identifier, "clientId": client_id, "recordId": record_id,
            "ideaId": idea["id"] if idea else None, "ideaRevision": idea["revision"] if idea else None,
            "revision": 1, "draft": {"text": "", "attachmentIds": []},
            "requestedProfile": client["requestedProfile"], "createdAt": now, "updatedAt": now}
        self._set_setting(db, "mobile-dialogue:session:" + identifier, session)
        self._set_setting(db, "mobile-dialogue:client:" + client_id, {**client, "currentSessionId": identifier})
        return session

    def _mobile_save_session(self, db, session):
        session["revision"] += 1
        session["updatedAt"] = _api()._now()
        self._set_setting(db, "mobile-dialogue:session:" + session["id"], session)
        client = self._mobile_client_state(db, session["clientId"])
        self._set_setting(db, "mobile-dialogue:client:" + session["clientId"], {**client, "requestedProfile": session["requestedProfile"]})

    def _mobile_draft(self, db, body, session):
        api = _api()
        text = api._text(body.get("text", ""))
        profile = body.get("requestedProfile", session["requestedProfile"])
        if not isinstance(profile, str) or profile not in PROFILES:
            raise api.WorkflowError("请选择极速、高或 Pro 档位。")
        context = self._context(db, session["recordId"], {"attachmentIds": body.get("attachmentIds", [])})
        session["draft"] = {"text": text, "attachmentIds": context["attachmentIds"]}
        session["requestedProfile"] = profile
        return text, context

    @staticmethod
    def _mobile_execution(profile):
        return {"requestedProfile": profile, "actualReceipt": {"verified": False, "actualProfile": None,
            "status": "unverified", "source": None}, "supportedProfiles": [], "capability": "unverified",
            "relayStatus": "not_connected", "message": "已保留所选档位；当前普通 Chat 通道尚未验证档位切换，事件转发器尚未接通。"}

    def _mobile_state(self, client_id, prefix, session_id=None, **extra):
        with self._db() as db:
            client = self._mobile_client_state(db, client_id)
            identifier = session_id or client["currentSessionId"]
            session = self._mobile_session(db, client_id, identifier) if identifier else None
            if session:
                session = {**session, "isCurrent": identifier == client["currentSessionId"]}
            revision = self._revision(db)
        profile = session["requestedProfile"] if session else client["requestedProfile"]
        return {"session": session, "detail": self.detail(session["recordId"], prefix) if session else None,
            "preferences": {"requestedProfile": client["requestedProfile"]}, "execution": self._mobile_execution(profile),
            "revision": revision, **extra}

    def mobile_dialogue_get(self, query="", prefix="/api/workflow"):
        params = _query(query, {"clientId"})
        return self._mobile_state(_client(params.get("clientId")), prefix)

    def mobile_dialogue_open(self, body, prefix="/api/workflow", authorize=None):
        api = _api()
        _body(body, {"requestId", "clientId", "ideaId", "expectedIdeaRevision"})
        client_id = _client(body.get("clientId"))
        if authorize:
            authorize()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "mobile_dialogue_open", body)
            if old:
                session_id = old["sessionId"]
            else:
                idea = None
                if body.get("ideaId") is not None:
                    idea = self._idea(db, body["ideaId"])
                    if _revision(body.get("expectedIdeaRevision")) != idea["revision"]:
                        raise api.WorkflowError("想法已更新，请重新读取。", 409, "revision_conflict")
                elif "expectedIdeaRevision" in body:
                    raise api.WorkflowError("想法版本必须与明确想法一起提供。")
                current = self._mobile_client_state(db, client_id)["currentSessionId"]
                session = self._mobile_session(db, client_id, current) if current and idea is None else self._mobile_new_session(db, client_id, idea)
                session_id = session["id"]
                self._receipt(db, "mobile_dialogue_open", body, {"sessionId": session_id})
                self._revision(db, True)
            if authorize:
                authorize()
        return self._mobile_state(client_id, prefix, session_id, duplicate=old is not None)

    def mobile_dialogue_clear(self, body, prefix="/api/workflow", authorize=None):
        _body(body, {"requestId", "clientId", "sessionId", "expectedRevision"})
        client_id = _client(body.get("clientId"))
        if authorize:
            authorize()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "mobile_dialogue_clear", body)
            if old:
                session_id = old["sessionId"]
            else:
                self._mobile_guard(db, body, client_id)
                session_id = self._mobile_new_session(db, client_id)["id"]
                self._receipt(db, "mobile_dialogue_clear", body, {"sessionId": session_id})
                self._revision(db, True)
            if authorize:
                authorize()
        return self._mobile_state(client_id, prefix, session_id, duplicate=old is not None)

    def mobile_dialogue_draft(self, body, prefix="/api/workflow", authorize=None):
        return self._mobile_dialogue_write("draft", body, prefix, authorize)

    def mobile_dialogue_send(self, body, prefix="/api/workflow", authorize=None):
        return self._mobile_dialogue_write("send", body, prefix, authorize)

    def mobile_dialogue_save(self, body, prefix="/api/workflow", authorize=None):
        return self._mobile_dialogue_write("save", body, prefix, authorize)

    def _mobile_dialogue_write(self, action, body, prefix, authorize):
        api = _api()
        _body(body, {"requestId", "clientId", "sessionId", "expectedRevision", "text", "attachmentIds", "requestedProfile"})
        client_id = _client(body.get("clientId"))
        if authorize:
            authorize()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            kind = "mobile_dialogue_" + action
            old = self._receipt(db, kind, body)
            if old:
                saved = old
            else:
                session = self._mobile_guard(db, body, client_id)
                text, context = self._mobile_draft(db, body, session)
                saved = {"sessionId": session["id"]}
                if action != "draft" and not text.strip() and not context["attachmentIds"]:
                    raise api.WorkflowError("请输入内容或选择附件。")
                if action == "send":
                    if not text.strip():
                        raise api.WorkflowError("普通 Chat 当前仅支持纯文字；附件和草稿已保留，请先保存为想法。", 400, "chatgpt_images_unavailable")
                    if db.execute("SELECT 1 FROM idea_dispatches WHERE json_extract(snapshot,'$.recordId')=? AND status IN ('pending','claimed','waiting','needs_review')", (session["recordId"],)).fetchone():
                        raise api.WorkflowError("当前讨论已有请求在途，请等待回答或核对送达。", 409, "dispatch_in_progress")
                    record = self._record(db, session["recordId"])
                    project = self._project(db, record["project_id"])
                    source = self._source_task(db, record["id"], {"ideaId": session["ideaId"], "revision": session["ideaRevision"]} if session["ideaId"] else None)
                    if source and not session["ideaId"]:
                        raise api.WorkflowError("讨论来源已改变，请重新打开此想法。", 409, "task_source_mismatch")
                    target = self._app_target(db, {"kind": "chatgpt", "mode": "new", "threadId": "", "name": "Console 手机讨论"}, bool(context["attachmentIds"]))
                    dialogue = {key: session[key] for key in ("id", "clientId", "recordId", "ideaId", "ideaRevision", "revision")}
                    payload = {"computerId": self._setting(db, "computer")["id"], "projectId": project["id"],
                        "text": text, "context": context, "purpose": "discussion", "sourceTask": source,
                        "appTarget": target, "requestedProfile": session["requestedProfile"], "mobileDialogue": dialogue}
                    payload["appFrozen"] = self._freeze_app_discussion(db, record, payload, project)
                    payload["appFrozen"].pop("actionPlanning", None)
                    payload["appFrozen"].update(requestedProfile=session["requestedProfile"], mobileDialogue=dialogue)
                    if source:
                        meta = self._mobile_metadata(db, source["ideaId"])
                        payload["appFrozen"]["mobileIdeaContext"] = {"id": source["ideaId"], "revision": source["revision"],
                            "keyPoints": [{key: point[key] for key in ("id", "text", "kind")} for point in meta["keyPoints"]],
                            "provenance": [{key: item[key] for key in ("id", "kind", "destinationRevision")} for item in meta["provenance"]]}
                        if sum(len(point["text"]) for point in meta["keyPoints"]) + sum(len(item["content"]) for item in payload["appFrozen"]["history"]) > 65000:
                            raise api.WorkflowError("当前长期要点与讨论历史过长，请缩小本轮上下文。")
                    job_id, now = uuid.uuid4().hex, api._now()
                    self._insert_app_dispatch(db, job_id, record, payload, now, body["requestId"])
                    db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (job_id, record["id"], "discuss", body["requestId"],
                        api._json(payload), "waiting", 1, None, now, now, "已确认此消息；等待普通 Chat 转发器核对所选档位，尚未发送。", "", "{}"))
                    self._message(db, record["id"], "user", text)
                    session["draft"] = {"text": "", "attachmentIds": []}
                    saved["jobId"] = job_id
                elif action == "save":
                    idea = self._idea(db, session["ideaId"]) if session["ideaId"] else None
                    if idea and idea["revision"] != session["ideaRevision"]:
                        raise api.WorkflowError("想法已更新，请重新读取后补充。", 409, "revision_conflict")
                    if idea:
                        self._mobile_bump_idea(db, idea, body=api._text(idea["body"] + ("\n\n" if idea["body"] and text else "") + text))
                        idea = self._idea(db, idea["id"])
                    else:
                        idea = self._mobile_create_idea(db, text)
                        if self._source_task(db, session["recordId"]):
                            raise api.WorkflowError("此记录已关联另一想法。", 409, "task_source_mismatch")
                        self._set_setting(db, "task-record:" + idea["id"], session["recordId"])
                    self._mobile_add_provenance(db, idea["id"], {"kind": "user_saved", "sourceSessionId": session["id"],
                        "sourceSessionRevision": session["revision"], "sourceRecordId": session["recordId"],
                        "sourceIdeaId": session["ideaId"], "sourceIdeaRevision": session["ideaRevision"], "attachmentIds": context["attachmentIds"]})
                    session.update(ideaId=idea["id"], ideaRevision=idea["revision"])
                    session["draft"] = {"text": "", "attachmentIds": []}
                    saved["ideaId"] = idea["id"]
                self._mobile_save_session(db, session)
                self._receipt(db, kind, body, saved)
                self._revision(db, True)
            if authorize:
                authorize()
        extra = {"duplicate": old is not None}
        if saved.get("jobId"):
            with self._db() as db:
                extra["job"] = self._job_public(db, db.execute("SELECT * FROM jobs WHERE id=?", (saved["jobId"],)).fetchone())
        if saved.get("ideaId"):
            with self._db() as db:
                extra["idea"] = self._mobile_idea(db, self._idea(db, saved["ideaId"]))
        return self._mobile_state(client_id, prefix, saved["sessionId"], **extra)

    def _mobile_metadata(self, db, idea_id):
        return self._setting(db, "mobile-idea:" + idea_id) or {"projectId": None, "archived": False, "keyPoints": [], "executionDraft": "", "provenance": []}

    def _mobile_idea(self, db, row):
        return {**self._public_idea(db, row), **self._mobile_metadata(db, row["id"])}

    def _mobile_create_idea(self, db, text):
        api = _api()
        identifier, now = uuid.uuid4().hex, api._now()
        title = next((line.strip()[:160] for line in text.splitlines() if line.strip()), "图片想法")
        db.execute("INSERT INTO ideas VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (identifier, title, text, "vague", "normal", None, "none", "", "", 1, now, now))
        return self._idea(db, identifier)

    def _mobile_bump_idea(self, db, row, title=None, body=None):
        now = _api()._now()
        db.execute("UPDATE ideas SET title=?,body=?,revision=revision+1,updated_at=? WHERE id=?", (row["title"] if title is None else title,
            row["body"] if body is None else body, now, row["id"]))
        for session in db.execute("SELECT * FROM idea_refinements WHERE idea_id=? AND state='active'", (row["id"],)).fetchall():
            db.execute("UPDATE idea_refinements SET state='needs_review',error='想法已编辑；后续完善已停止。',updated_at=? WHERE id=?", (now, session["id"]))
            self._cancel_refinement_pending(db, session["id"], now, "想法已编辑；未发送的完善轮次已取消。")

    def _mobile_add_provenance(self, db, idea_id, value, point=None):
        meta = self._mobile_metadata(db, idea_id)
        value = {**value, "id": uuid.uuid4().hex, "createdAt": _api()._now(), "destinationRevision": self._idea(db, idea_id)["revision"]}
        meta["provenance"].append(value)
        if point:
            meta["keyPoints"].append({"id": uuid.uuid4().hex, "text": point, "kind": "suggestion", "source": value})
        self._set_setting(db, "mobile-idea:" + idea_id, meta)

    def mobile_dialogue_remember(self, body, prefix="/api/workflow", authorize=None):
        api = _api()
        _body(body, {"requestId", "clientId", "sessionId", "expectedRevision", "sourceMessageId", "ideaId", "expectedIdeaRevision"})
        client_id = _client(body.get("clientId"))
        if authorize:
            authorize()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "mobile_dialogue_remember", body)
            if old:
                saved = old
            else:
                session = self._mobile_guard(db, body, client_id)
                message = db.execute("SELECT * FROM messages WHERE id=? AND record_id=? AND role='assistant'", (api._id(body.get("sourceMessageId")), session["recordId"])).fetchone()
                jobs = db.execute("SELECT * FROM jobs WHERE record_id=? AND kind='discuss' AND status='succeeded' AND json_extract(result,'$.messageId')=?", (session["recordId"], body["sourceMessageId"])).fetchall()
                if message is None or len(jobs) != 1 or json.loads(jobs[0]["result"]).get("text") != message["text"]:
                    raise api.WorkflowError("请只保存此讨论已完成的实际回答。", 409, "answer_source_mismatch")
                idea = self._idea(db, body["ideaId"]) if body.get("ideaId") is not None else None
                if idea:
                    if _revision(body.get("expectedIdeaRevision")) != idea["revision"]:
                        raise api.WorkflowError("想法已更新，请重新读取后补充。", 409, "revision_conflict")
                    self._mobile_bump_idea(db, idea, body=api._text(idea["body"] + ("\n\n" if idea["body"] else "") + message["text"]))
                    idea = self._idea(db, idea["id"])
                elif "expectedIdeaRevision" in body:
                    raise api.WorkflowError("想法版本必须与明确想法一起提供。")
                else:
                    idea = self._mobile_create_idea(db, message["text"])
                payload = json.loads(jobs[0]["payload"])
                source = payload.get("sourceTask") or {}
                dialogue = payload.get("mobileDialogue") or {}
                self._mobile_add_provenance(db, idea["id"], {"kind": "assistant_suggestion", "sourceSessionId": dialogue.get("id", session["id"]),
                    "sourceSessionRevision": dialogue.get("revision", session["revision"]), "sourceRecordId": session["recordId"],
                    "sourceMessageId": message["id"], "sourceJobId": jobs[0]["id"], "sourceIdeaId": source.get("ideaId"), "sourceIdeaRevision": source.get("revision")}, message["text"])
                if session["ideaId"] == idea["id"]:
                    session["ideaRevision"] = idea["revision"]
                self._mobile_save_session(db, session)
                saved = {"sessionId": session["id"], "ideaId": idea["id"]}
                self._receipt(db, "mobile_dialogue_remember", body, saved)
                self._revision(db, True)
            if authorize:
                authorize()
            idea = self._mobile_idea(db, self._idea(db, saved["ideaId"]))
        return self._mobile_state(client_id, prefix, saved["sessionId"], idea=idea, duplicate=old is not None)

    def mobile_ideas(self, query="", prefix="/api/workflow"):
        params = _query(query, {"search", "projectId", "archived"})
        if params.get("archived", "0") not in {"0", "1"}:
            raise _api().WorkflowError("想法归档筛选无效。")
        search = params.get("search", "").casefold()
        with self._db() as db:
            ideas = [self._mobile_idea(db, row) for row in db.execute("SELECT * FROM ideas ORDER BY updated_at DESC,id")]
            ideas = [idea for idea in ideas if idea["archived"] == (params.get("archived", "0") == "1")
                and (not search or search in (idea["title"] + "\n" + idea["body"]).casefold())
                and (not params.get("projectId") or (idea["projectId"] is None if params["projectId"] == "unclassified" else idea["projectId"] == params["projectId"]))]
            projects = [{"id": project["id"], "name": project["name"]} for project in self._setting(db, "projects") or []]
            return {"ideas": ideas, "projects": projects, "revision": self._revision(db)}

    def mobile_idea(self, query="", prefix="/api/workflow"):
        params = _query(query, {"id"})
        with self._db() as db:
            idea = self._mobile_idea(db, self._idea(db, params.get("id")))
            revision = self._revision(db)
        return {"idea": idea, "detail": self.detail(idea["workflowRecordId"], prefix) if idea["workflowRecordId"] else None,
            "provenance": idea["provenance"], "revision": revision}

    def mobile_idea_update(self, body, prefix="/api/workflow", authorize=None):
        return self._mobile_idea_write(False, body, authorize)

    def mobile_idea_archive(self, body, prefix="/api/workflow", authorize=None):
        return self._mobile_idea_write(True, body, authorize)

    def _mobile_idea_write(self, archive, body, authorize):
        api = _api()
        editable = {"archived"} if archive else {"title", "body", "projectId", "keyPoints", "executionDraft"}
        _body(body, {"requestId", "id", "expectedRevision"} | editable)
        if not set(body) & editable:
            raise api.WorkflowError("请选择要保存的内容。")
        if authorize:
            authorize()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            kind = "mobile_idea_archive" if archive else "mobile_idea_update"
            old = self._receipt(db, kind, body)
            if old:
                identifier = old["ideaId"]
            else:
                row = self._idea(db, body.get("id"))
                if _revision(body.get("expectedRevision")) != row["revision"]:
                    raise api.WorkflowError("想法已更新，请保留输入后合并。", 409, "revision_conflict")
                identifier = row["id"]
                meta = self._mobile_metadata(db, identifier)
                if archive:
                    if type(body.get("archived")) is not bool:
                        raise api.WorkflowError("归档状态无效。")
                    meta["archived"] = body["archived"]
                else:
                    if "projectId" in body:
                        if body["projectId"] is not None:
                            self._project(db, body["projectId"])
                        meta["projectId"] = body["projectId"]
                    if "executionDraft" in body:
                        meta["executionDraft"] = api._text(body["executionDraft"])
                    if "keyPoints" in body:
                        points = body["keyPoints"]
                        if not isinstance(points, list) or len(points) > 100:
                            raise api.WorkflowError("长期要点最多 100 条。")
                        previous = {point["id"]: point for point in meta["keyPoints"]}
                        clean, seen = [], set()
                        for point in points:
                            if (not isinstance(point, dict) or set(point) != {"id", "text", "kind"}
                                    or not isinstance(point["kind"], str) or point["kind"] not in {"suggestion", "decision"}):
                                raise api.WorkflowError("请区分助手建议和用户确认决定。")
                            point_id = api._id(point["id"])
                            text = api._text(point["text"]).strip()
                            if not text or point_id in seen:
                                raise api.WorkflowError("长期要点内容为空或重复。")
                            seen.add(point_id)
                            clean.append({**previous.get(point_id, {}), "id": point_id, "text": text, "kind": point["kind"], "userEditedAt": api._now()})
                        meta["keyPoints"] = clean
                title = api._text(body["title"], 160).strip() if "title" in body else row["title"]
                if not title:
                    raise api.WorkflowError("想法标题不能为空。")
                text = api._text(body["body"]) if "body" in body else row["body"]
                self._mobile_bump_idea(db, row, title, text)
                self._set_setting(db, "mobile-idea:" + identifier, meta)
                self._mobile_add_provenance(db, identifier, {"kind": "user_archive" if archive else "user_edit", "sourceIdeaId": identifier, "sourceIdeaRevision": row["revision"]})
                self._receipt(db, kind, body, {"ideaId": identifier})
                self._revision(db, True)
            if authorize:
                authorize()
            return {"idea": self._mobile_idea(db, self._idea(db, identifier)), "revision": self._revision(db), "duplicate": old is not None}
