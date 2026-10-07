"""Recoverable phone discussions and explicit idea saves in the existing store.

This module never sends an App message. A confirmed send freezes one discussion
into the existing outbox; delivery/profile capabilities remain unverified.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import threading
import time
from contextlib import closing
from urllib.parse import parse_qs
import uuid


PROFILES = {"fast", "high", "pro"}
CHAT_TRANSPORTS = {"browser_chat", "chatgpt_subscription"}
MOBILE_IMAGE_BYTES = 8 * 1024 * 1024
_EVENT_HUB_LOCK = threading.Lock()
_EVENT_STREAM_LIMIT = 16


class _DialogueEventHub:
    """Bounded in-memory wakeups; persisted job state supplies reconnection evidence."""
    def __init__(self):
        self.condition = threading.Condition()
        self.subscriptions = {}
        self.versions = {}

    def subscribe(self, key):
        with self.condition:
            if len(self.subscriptions) >= _EVENT_STREAM_LIMIT:
                raise _api().WorkflowError("讨论连接已达到上限，请关闭重复页面后再试。", 429, "dialogue_connections_full")
            token = uuid.uuid4().hex
            self.subscriptions[token] = key
            self.versions.setdefault(key, 0)
            return token, self.versions[key]

    def keys(self):
        with self.condition:
            return tuple(self.versions)

    def notify(self, keys):
        with self.condition:
            changed = False
            for key in keys:
                if key in self.versions:
                    self.versions[key] += 1
                    changed = True
            if changed:
                self.condition.notify_all()

    def wait(self, token, version, timeout):
        with self.condition:
            key = self.subscriptions.get(token)
            if key is None:
                return None
            self.condition.wait_for(lambda: token not in self.subscriptions or self.versions[key] != version, timeout)
            return self.versions.get(key) if token in self.subscriptions else None

    def close(self, token):
        with self.condition:
            key = self.subscriptions.pop(token, None)
            if key is not None and key not in self.subscriptions.values():
                self.versions.pop(key, None)
            self.condition.notify_all()


class _DialogueEventStream:
    def __init__(self, service, hub, key, token, version, state, cursor, authorize):
        self.service, self.hub, self.key = service, hub, key
        self.token, self.version, self.authorize = token, version, authorize
        self.cursor, self.closed = state["cursor"], False
        self.initial = {"event": "dialogue.result" if cursor and cursor != self.cursor else "dialogue.ready", "data": state}

    def _authorized(self):
        if self.authorize:
            self.authorize()
        if getattr(self.service, "_stop", None) is not None and self.service._stop.is_set():
            raise _api().WorkflowError("电脑连接已关闭。", 503, "dialogue_connection_closed")

    def next_event(self, timeout=25):
        if self.closed:
            raise _api().WorkflowError("讨论连接已关闭。", 409, "dialogue_connection_closed")
        self._authorized()
        if self.initial is not None:
            event, self.initial = self.initial, None
            version = self.hub.wait(self.token, self.version, 0)
            if version is None:
                raise _api().WorkflowError("讨论连接已关闭。", 409, "dialogue_connection_closed")
            if version != self.version:
                self.version = version
                state = self.service._mobile_event_read(self.key)
                if state["cursor"] != self.cursor:
                    self.cursor = state["cursor"]
                    event = {"event": "dialogue.result", "data": state}
            self._authorized()
            return event
        deadline = time.monotonic() + min(max(float(timeout), 0), 25)
        while True:
            version = self.hub.wait(self.token, self.version, max(0, deadline - time.monotonic()))
            self._authorized()
            if version is None:
                raise _api().WorkflowError("讨论连接已关闭。", 409, "dialogue_connection_closed")
            if version != self.version:
                self.version = version
                state = self.service._mobile_event_read(self.key)
                self._authorized()
                if state["cursor"] != self.cursor:
                    self.cursor = state["cursor"]
                    return {"event": "dialogue.result", "data": state}
            if time.monotonic() >= deadline:
                # Transport keepalive only: no queue/session reads on idle timeouts.
                return None

    def close(self):
        if not self.closed:
            self.closed = True
            self.hub.close(self.token)


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
    def _mobile_event_hub(self):
        with _EVENT_HUB_LOCK:
            hub = getattr(self, "_mobile_result_hub", None)
            if hub is None:
                hub = self._mobile_result_hub = _DialogueEventHub()
            return hub

    def _mobile_result_job(self, db, session):
        # The frozen session, not the record's newest arbitrary message, owns a result.
        job = db.execute("SELECT * FROM jobs WHERE record_id=? AND kind='discuss' "
            "AND json_extract(payload,'$.mobileDialogue.id')=? "
            "AND json_extract(payload,'$.mobileDialogue.clientId')=? ORDER BY created_at DESC,id DESC LIMIT 1",
            (session["recordId"], session["id"], session["clientId"])).fetchone()
        if job is None:
            return None, None
        payload = json.loads(job["payload"])
        dialogue = payload.get("mobileDialogue")
        identifier = payload.get("appDispatchId")
        dispatch = db.execute("SELECT * FROM idea_dispatches WHERE id=?", (identifier,)).fetchone()
        snapshot = json.loads(dispatch["snapshot"]) if dispatch else {}
        if (not isinstance(dialogue, dict) or dialogue.get("recordId") != session["recordId"]
                or dialogue != payload.get("appFrozen", {}).get("mobileDialogue")
                or dialogue != snapshot.get("mobileDialogue") or snapshot.get("recordId") != job["record_id"]
                or snapshot.get("jobId") != job["id"]):
            raise _api().WorkflowError("本轮回答来源无法核对。", 409, "result_not_matching")
        return job, dispatch

    def _mobile_event_state(self, db, key, require_current=True):
        client_id, session_id = key
        session = self._mobile_session(db, client_id, session_id)
        current = self._mobile_client_state(db, client_id)["currentSessionId"]
        if require_current and current != session_id:
            raise _api().WorkflowError("当前讨论已切换，请读取新的讨论。", 409, "dialogue_changed")
        job, dispatch = self._mobile_result_job(db, session)
        status = "idle" if job is None else "needs_review" if dispatch["status"] == "needs_review" else job["status"]
        proof = {"clientId": client_id, "sessionId": session_id, "recordId": session["recordId"], "currentSessionId": current,
            "job": {name: job[name] for name in ("id", "status", "updated_at", "error", "result")} if job else None,
            "dispatch": {name: dispatch[name] for name in ("id", "status", "updated_at", "error", "result", "target_thread_id")} if dispatch else None}
        # Work remains separate from Chat profile evidence. Its scoped commits
        # still wake this original discussion when progress or Output changes.
        own_work = []
        for row in db.execute("SELECT * FROM jobs WHERE record_id=? AND kind='work' AND json_extract(payload,'$.executionEngine')='codex_agent' ORDER BY created_at DESC,id DESC LIMIT 64", (session["recordId"],)):
            payload = json.loads(row["payload"])
            source = payload.get("codexWork", {}).get("source", {})
            dialogue = payload.get("mobileDialogue")
            phone_owned = (isinstance(dialogue, dict) and dialogue == source.get("mobileDialogue")
                    and dialogue.get("id") == session_id and dialogue.get("clientId") == client_id
                    and dialogue.get("recordId") == session["recordId"] and source.get("recordId") == session["recordId"])
            desktop_owned = False
            if dialogue is None and source.get("mobileDialogue") is None:
                try:
                    _, _, meta, _ = self._codex_work_job_row(db, row["id"])
                    desktop_owned = self._codex_work_phone_run_scope(db, session, meta["source"])
                except _api().WorkflowError:
                    pass
            if phone_owned or desktop_owned:
                own_work.append({**{name: row[name] for name in ("id", "status", "updated_at", "error", "result", "log")},
                    "workProgressSha256": hashlib.sha256(_api()._json(payload["codexWork"]).encode("utf-8")).hexdigest()})
        if own_work:
            proof["work"] = own_work
        guide = self._guide_event_proof(db, session)
        if guide:
            proof["guide"] = guide
        guide_inputs = self._guide_input_event_proof(db, session)
        if guide_inputs:
            proof["guideInputs"] = guide_inputs
        cursor = hashlib.sha256(_api()._json(proof).encode("utf-8")).hexdigest()
        return {"clientId": client_id, "sessionId": session_id, "recordId": session["recordId"], "cursor": cursor,
            "jobId": job["id"] if job else None, "status": status}

    def _mobile_event_read(self, key):
        # This GET never creates tables/settings, recovers jobs, or changes revision.
        with self._lock, closing(sqlite3.connect((self.data_dir / "workflow.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            return self._mobile_event_state(db, key)

    def _mobile_events_snapshot(self, db):
        """Called before/after a transaction; only existing bounded subscriptions."""
        hub = getattr(self, "_mobile_result_hub", None)
        if hub is None:
            return {}
        snapshots = {}
        for key in hub.keys():
            try:
                snapshots[key] = self._mobile_event_state(db, key, require_current=False)["cursor"]
            except _api().WorkflowError as error:
                snapshots[key] = (error.status, error.code)
        return snapshots

    def _mobile_events_committed(self, before, after):
        """Invoke only after db.commit succeeds, never for rolled-back changes."""
        hub = getattr(self, "_mobile_result_hub", None)
        if hub is not None:
            hub.notify(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))

    def mobile_dialogue_subscribe(self, query="", authorize=None):
        params = _query(query, {"clientId", "sessionId", "cursor"})
        client_id = _client(params.get("clientId"))
        session_id = params.get("sessionId")
        cursor = params.get("cursor", "")
        if (params.get("clientId") != client_id or not isinstance(session_id, str) or not re.fullmatch(r"[a-f0-9]{32}", session_id)
                or not isinstance(cursor, str) or cursor and not re.fullmatch(r"[a-f0-9]{64}", cursor)):
            raise _api().WorkflowError("讨论事件请求身份无效。")
        if authorize:
            authorize()
        key = client_id, session_id
        self._mobile_event_read(key)
        hub = self._mobile_event_hub()
        token, version = hub.subscribe(key)
        try:
            # Subscribe before the second read so a concurrent commit cannot be missed.
            state = self._mobile_event_read(key)
            if authorize:
                authorize()
            return _DialogueEventStream(self, hub, key, token, version, state, cursor, authorize)
        except BaseException:
            hub.close(token)
            raise

    def _mobile_profile_observation(self, db, session):
        job, dispatch = self._mobile_result_job(db, session)
        if not job or job["status"] != "succeeded" or dispatch["status"] != "completed":
            return None
        result = json.loads(job["result"] or "{}")
        if result.get("source") == "chatgpt_subscription":
            try:
                row, snapshot, original_job, payload = self._subscription_source(db, dispatch["id"])
            except _api().WorkflowError:
                return None
            selection = payload["subscription"]
            message = db.execute("SELECT role,record_id FROM messages WHERE id=?", (result.get("messageId"),)).fetchone()
            if ("requestedProfile" not in selection or original_job["id"] != job["id"]
                    or result.get("dispatchId") != dispatch["id"] or result.get("subscription") != selection
                    or result.get("actualProfileVerified") is not True
                    or result.get("requestedProfile") != selection["requestedProfile"]
                    or result.get("actualProfile") != selection["requestedProfile"]
                    or result.get("requestedReasoning") != selection["reasoning"]
                    or result.get("actualReasoning") != selection["reasoning"]
                    or result.get("actualModel") != selection["modelSlug"]
                    or result.get("terminalEventObserved") is not True or result.get("terminalStatus") != "completed"
                    or result.get("completionEvidence") != "response.completed" or result.get("providerErrorObserved") is not False
                    or not message or message["record_id"] != session["recordId"] or message["role"] != "assistant"):
                return None
            return {"requestedProfile": selection["requestedProfile"], "actualProfile": selection["requestedProfile"],
                "actualReasoning": dict(selection["reasoning"]), "actualModel": selection["modelSlug"],
                "subscription": selection, "source": "chatgpt_subscription",
                "dispatchId": dispatch["id"], "jobId": job["id"], "messageId": result["messageId"],
                "observedAt": result["completedAt"], "actualProfileVerified": True}
        evidence = result.get("browserEvidence", {})
        profile = evidence.get("profile", {})
        message = db.execute("SELECT role,record_id FROM messages WHERE id=?", (result.get("messageId"),)).fetchone()
        if (result.get("sourceKind") != "browser_dom" or evidence.get("source") != "browser_dom"
                or result.get("dispatchId") != dispatch["id"] or result.get("actualProfileObserved") != "Instant"
                or evidence.get("promptText") != dispatch["prompt"]
                or profile != {"requestedProfile": "fast", "observedBefore": "Instant", "observedAfter": "Instant"}
                or result.get("executionCapabilities") != {"verified": False, "source": "browser_dom_ui_label"}
                or not message or message["record_id"] != session["recordId"] or message["role"] != "assistant"):
            return None
        observation = {"requestedProfile": "fast", "actualProfileObserved": "Instant", "source": "browser_dom_ui_label",
            "dispatchId": dispatch["id"], "jobId": job["id"], "messageId": result["messageId"],
            "observedAt": evidence["observedAt"], "capabilitiesVerified": False}
        if result.get("profileObservation") not in (None, observation):
            return None
        return observation

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

    def _mobile_source_guard(self, db, session):
        if session.get("ideaId"):
            source = self._source_task(db, session["recordId"],
                {"ideaId": session["ideaId"], "revision": session["ideaRevision"]})
            if not source:
                raise _api().WorkflowError("讨论来源已改变，请重新打开此想法。", 409, "task_source_mismatch")

    def _mobile_original_ids(self, db, idea_id):
        """Only explicitly saved originals, never all files on a shared record."""
        api = _api()
        meta = self._mobile_metadata(db, idea_id)
        ids = meta.get("attachmentIds")
        if ids is None:
            ids = []
            for item in meta.get("provenance", []):
                if item.get("kind") == "user_saved":
                    ids.extend(item.get("attachmentIds", []))
        if not isinstance(ids, list):
            raise api.WorkflowError("原图来源无法核对，请保留想法后核对。", 409, "image_source_mismatch")
        record_id = self._setting(db, "task-record:" + idea_id)
        clean = list(dict.fromkeys(api._id(identifier) for identifier in ids))
        for identifier in clean:
            self._mobile_image_row(db, record_id, identifier)
        return clean

    def _mobile_image_row(self, db, record_id, identifier):
        row = db.execute("SELECT * FROM attachments WHERE id=? AND record_id=? AND mime_type LIKE 'image/%'",
            (_api()._id(identifier), record_id)).fetchone()
        if row is None:
            raise _api().WorkflowError("所选原图不属于本次想法或讨论。", 403, "image_source_mismatch")
        return row

    def _mobile_image_proof(self, row):
        api = _api()
        try:
            path = api._safe_child(self.attachments_dir, row["filename"])
            if not path.is_file() or not 0 < path.stat().st_size == row["size"] <= api.MAX_FILE_BYTES:
                raise api.WorkflowError("原图已改变或无法读取，请保留想法后核对。", 409, "image_source_mismatch")
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(65536), b""):
                    size += len(block)
                    if size > api.MAX_FILE_BYTES:
                        raise api.WorkflowError("原图读取期间发生改变，请重新核对。", 409, "image_source_mismatch")
                    digest.update(block)
            if size != row["size"]:
                raise api.WorkflowError("原图读取期间发生改变，请重新核对。", 409, "image_source_mismatch")
            return {"sha256": digest.hexdigest(), "size": row["size"], "mimeType": row["mime_type"]}
        except (OSError, api.TransferError) as error:
            raise api.WorkflowError("原图无法读取，请保留想法后核对。", 409, "image_source_mismatch") from error

    def _mobile_freeze_originals(self, db, idea_id):
        identifiers = self._mobile_original_ids(db, idea_id)
        record_id = self._setting(db, "task-record:" + idea_id)
        return identifiers, {identifier: self._mobile_image_proof(self._mobile_image_row(db, record_id, identifier))
            for identifier in identifiers}

    def _mobile_selected_images(self, db, session, identifiers):
        api = _api()
        if (not isinstance(identifiers, list) or len(identifiers) > api.MAX_ATTACHMENTS
                or any(not isinstance(identifier, str) for identifier in identifiers) or len(set(identifiers)) != len(identifiers)):
            raise api.WorkflowError("请明确选择最多四张不同原图。")
        proofs = {**session.get("eligibleAttachmentProofs", {}), **session.get("uploadedAttachmentProofs", {})}
        allowed = set(session.get("eligibleAttachmentIds", [])) | set(session.get("uploadedAttachmentIds", []))
        total = 0
        for identifier in identifiers:
            row = self._mobile_image_row(db, session["recordId"], identifier)
            if identifier not in allowed or proofs.get(identifier) != self._mobile_image_proof(row):
                raise api.WorkflowError("所选原图不属于本次冻结想法或讨论，请重新选择。", 403, "image_source_mismatch")
            total += row["size"]
        if total > api.MAX_UPLOAD:
            raise api.WorkflowError("所选图片总大小不能超过 24 MB。", 413)
        return identifiers

    def _mobile_project(self, db):
        """A journal's classification is metadata, never an execution grant."""
        projects = self._setting(db, "projects") or []
        return projects[0] if projects else None

    def _mobile_classification_id(self, db, identifier):
        """Saving a category uses its actual identity, not execution/root access."""
        if identifier is None:
            return None
        identifier = _api()._key(identifier)
        if not any(project.get("id") == identifier for project in self._setting(db, "projects") or []):
            raise _api().WorkflowError("项目分类不存在，请重新选择。", 403, "project_not_authorized")
        return identifier

    def _mobile_new_record(self, db, title="当前讨论", text=""):
        api = _api()
        project = self._mobile_project(db)
        identifier, now = uuid.uuid4().hex, api._now()
        db.execute("INSERT INTO records VALUES (?,?,?,?,?,?,?)", (identifier, title, project["id"] if project else "", now, now, None,
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
            "requestedProfile": client["requestedProfile"], "createdAt": now, "updatedAt": now,
            "chatTransport": client.get("chatTransport", "browser_chat"), "subscription": client.get("subscription")}
        ids, proofs = self._mobile_freeze_originals(db, idea["id"]) if idea else ([], {})
        session.update(eligibleAttachmentIds=ids, eligibleAttachmentProofs=proofs,
            uploadedAttachmentIds=[], uploadedAttachmentProofs={})
        self._set_setting(db, "mobile-dialogue:session:" + identifier, session)
        self._set_setting(db, "mobile-dialogue:client:" + client_id, {**client, "currentSessionId": identifier})
        return session

    def _mobile_save_session(self, db, session):
        session["revision"] += 1
        session["updatedAt"] = _api()._now()
        self._set_setting(db, "mobile-dialogue:session:" + session["id"], session)
        client = self._mobile_client_state(db, session["clientId"])
        self._set_setting(db, "mobile-dialogue:client:" + session["clientId"], {**client,
            "requestedProfile": session["requestedProfile"], "chatTransport": session.get("chatTransport", "browser_chat"),
            "subscription": session.get("subscription")})

    @staticmethod
    def _mobile_subscription_choice(value):
        # Saving a choice is not authentication, catalog refresh or inference.
        if value is None:
            return None
        if (not isinstance(value, dict) or set(value) not in (
                {"provider", "connectionId", "catalogRevision", "modelSlug"},
                {"provider", "connectionId", "catalogRevision", "modelSlug", "requestedProfile", "reasoning"})
                or value.get("provider") != "chatgpt_subscription"
                or any(not isinstance(value.get(key), str) or len(value[key]) > 200
                    or any(ord(character) < 32 for character in value[key])
                    for key in ("connectionId", "catalogRevision", "modelSlug"))):
            raise _api().WorkflowError("订阅模型选择格式无效，原草稿保留。", 400, "subscription_selection_invalid")
        from workflow_subscription import subscription_binding
        return subscription_binding(value)

    def _mobile_draft(self, db, body, session):
        api = _api()
        self._mobile_source_guard(db, session)
        text = api._text(body.get("text", ""))
        profile = body.get("requestedProfile", session["requestedProfile"])
        if not isinstance(profile, str) or profile not in PROFILES:
            raise api.WorkflowError("请选择极速、高或 Pro 档位。")
        identifiers = self._mobile_selected_images(db, session, body.get("attachmentIds", []))
        context = self._context(db, session["recordId"], {"attachmentIds": identifiers})
        transport = body.get("chatTransport", "browser_chat")
        if not isinstance(transport, str) or transport not in CHAT_TRANSPORTS:
            raise api.WorkflowError("请选择明确的讨论通道。", 400, "chat_transport_invalid")
        choice = self._mobile_subscription_choice(body.get("subscription"))
        if choice is not None and "requestedProfile" in choice and choice["requestedProfile"] != profile:
            raise api.WorkflowError("订阅选择与当前档位不一致，原草稿保留。", 400, "subscription_profile_mismatch")
        if transport == "browser_chat" and choice is not None:
            raise api.WorkflowError("浏览器通道不能同时提交订阅模型。", 400, "chat_transport_invalid")
        session["draft"] = {"text": text, "attachmentIds": context["attachmentIds"]}
        session["requestedProfile"] = profile
        session["chatTransport"] = transport
        if transport == "chatgpt_subscription":
            session["subscription"] = choice
        return text, context

    def _mobile_execution(self, profile, observation=None, transport="browser_chat", subscription=None):
        execution = {"requestedProfile": profile, "actualReceipt": {"verified": False, "actualProfile": None,
            "status": "unverified", "source": None}, "supportedProfiles": [], "capability": "unverified",
            "relayStatus": "not_connected", "profileObservation": observation,
            "message": "已保留所选档位；当前普通 Chat 通道尚未验证档位切换，事件转发器尚未接通。"}
        if transport == "chatgpt_subscription":
            adapter = getattr(self, "subscription", None)
            status = adapter.get_status() if adapter is not None else {}
            mapping = status.get("profileMappings", {}).get(profile, {})
            execution.update(relayStatus="connected" if status.get("connected") is True else "not_connected",
                supportedProfiles=[key for key, value in status.get("profileMappings", {}).items() if value.get("available") is True],
                message="订阅档位请求映射已准备；实际档位以本轮完成回执核实。" if mapping.get("available") is True
                    else "订阅连接或所选档位尚未准备好，原内容与档位保留。")
            if (isinstance(observation, dict) and observation.get("source") == "chatgpt_subscription"
                    and observation.get("requestedProfile") == profile and observation.get("actualProfileVerified") is True
                    and observation.get("subscription") == subscription):
                execution.update(actualReceipt={"verified": True, "actualProfile": profile, "status": "completed",
                    "source": "chatgpt_subscription", "actualModel": observation["actualModel"],
                    "actualReasoning": dict(observation["actualReasoning"])},
                    capability="verified", message="最近已完成请求的回执已核实这个模型与档位组合。")
            return execution
        broker = getattr(self, "_chat_relay_broker", None)
        if broker is not None:
            status = broker.public_status()
            if status.get("clientReady") is True:
                execution.update(relayStatus="connected", message="普通 Chat 转发已连接；实际模型与推理档位仍待回执核实。")
                if profile != "fast":
                    execution["message"] = "转发器已连接；所选高／Pro档位尚未核实，本次不会降档发送。"
                if status.get("message") in {"older_queue_head_requires_user_review", "unsupported_queue_head_requires_user_review",
                                              "frozen_target_requires_user_review", "prior_send_evidence_requires_user_review"}:
                    execution["message"] = "前一条请求需要核对，当前消息尚未发送；内容与所选档位保留。"
        return execution

    def _mobile_state(self, client_id, prefix, session_id=None, **extra):
        with self._db() as db:
            client = self._mobile_client_state(db, client_id)
            identifier = session_id or client["currentSessionId"]
            session = self._mobile_session(db, client_id, identifier) if identifier else None
            if session:
                session = {**session, "isCurrent": identifier == client["currentSessionId"]}
            result_state = self._mobile_event_state(db, (client_id, identifier), require_current=False) if session else None
            observation = self._mobile_profile_observation(db, session) if session else None
            clear_receipts = self._mobile_clear_receipts(db, session)
            guide = self._guide_input_state(db, session)
            revision = self._revision(db)
        profile = session["requestedProfile"] if session else client["requestedProfile"]
        detail = self.detail(session["recordId"], prefix) if session else None
        if detail:
            detail["messages"] = [message for message in detail["messages"] if all(
                metadata not in message or all(message[metadata].get(key) == value for key, value in
                    (("clientId", client_id), ("sessionId", session["id"]), ("recordId", session["recordId"])))
                for metadata in ("guideSource", "guideInput"))]
        cancellation_receipts = []
        if detail:
            with self._db() as db:
                db.execute("BEGIN")
                for job in detail["jobs"]:
                    if isinstance(job.get("appDispatch"), dict):
                        job["appDispatch"]["canCancelPending"] = self._mobile_can_cancel_pending(db, session, job)
                cancellation_receipts = self._mobile_pending_cancellation_receipts(db, session)
        eligible_ids = set(session.get("eligibleAttachmentIds", [])) | set(session.get("uploadedAttachmentIds", [])) if session else set()
        return {"session": session, "detail": detail,
            "eligibleAttachments": [item for item in detail["attachments"] if item["id"] in eligible_ids] if detail else [],
            "preferences": {"requestedProfile": client["requestedProfile"],
                "chatTransport": client.get("chatTransport", "browser_chat"), "subscription": client.get("subscription")},
            "execution": self._mobile_execution(profile, observation,
                session.get("chatTransport", "browser_chat") if session else client.get("chatTransport", "browser_chat"),
                session.get("subscription") if session else client.get("subscription")),
            "resultCursor": result_state["cursor"] if result_state else None,
            "resultStatus": result_state["status"] if result_state else "idle",
            "cancellationReceipts": cancellation_receipts,
            "clearReceipts": clear_receipts,
            "guide": guide,
            "revision": revision, **extra}

    def _mobile_clear_receipts(self, db, session):
        """Recover only an exact successful clear into this current discussion."""
        if not session or session.get("isCurrent") is not True:
            return []
        fields = {"requestId", "clientId", "sessionId", "expectedRevision", "newSessionId", "newRecordId"}
        entries = db.execute("SELECT id,fingerprint,response FROM requests WHERE kind='mobile_dialogue_clear' "
            "AND json_extract(CASE WHEN json_valid(response) THEN response ELSE '{}' END,'$.clearReceipt.clientId')=? "
            "AND json_extract(CASE WHEN json_valid(response) THEN response ELSE '{}' END,'$.clearReceipt.newSessionId')=? "
            "ORDER BY rowid DESC LIMIT 20", (session["clientId"], session["id"]))
        receipts = []
        for entry in entries:
            try:
                saved = json.loads(entry["response"])
                proof = saved.get("clearReceipt") if isinstance(saved, dict) else None
                if (set(saved) != {"sessionId", "clearReceipt"} or not isinstance(proof, dict) or set(proof) != fields
                        or proof["requestId"] != entry["id"] or str(uuid.UUID(entry["id"])) != entry["id"]
                        or proof["clientId"] != session["clientId"] or proof["newSessionId"] != session["id"]
                        or saved["sessionId"] != session["id"] or proof["newRecordId"] != session["recordId"]
                        or proof["sessionId"] == session["id"] or type(proof["expectedRevision"]) is not int
                        or proof["expectedRevision"] < 1):
                    continue
                original = {key: proof[key] for key in ("requestId", "clientId", "sessionId", "expectedRevision")}
                if hashlib.sha256(_api()._json(original).encode("utf-8")).hexdigest() != entry["fingerprint"]:
                    continue
                old = self._mobile_session(db, session["clientId"], proof["sessionId"])
                if old["recordId"] == session["recordId"] or old["revision"] < proof["expectedRevision"]:
                    continue
                receipts.append(proof)
            except (ValueError, TypeError, KeyError, AttributeError, sqlite3.Error):
                continue
        return receipts

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
                session = self._mobile_new_session(db, client_id)
                session_id = session["id"]
                proof = {key: body[key] for key in ("requestId", "clientId", "sessionId", "expectedRevision")}
                proof.update(newSessionId=session_id, newRecordId=session["recordId"])
                self._receipt(db, "mobile_dialogue_clear", body, {"sessionId": session_id, "clearReceipt": proof})
                self._revision(db, True)
            if authorize:
                authorize()
        return self._mobile_state(client_id, prefix, session_id, duplicate=old is not None)

    def mobile_dialogue_draft(self, body, prefix="/api/workflow", authorize=None):
        return self._mobile_dialogue_write("draft", body, prefix, authorize)

    def mobile_dialogue_send(self, body, prefix="/api/workflow", authorize=None):
        return self._mobile_dialogue_write("send", body, prefix, authorize)

    def mobile_dialogue_send_receipt(self, query="", *, prefix="/api/workflow", authorize=None):
        """Look up an accepted original send without dispatching or changing state."""
        api = _api()
        if prefix not in {"/api/workflow", "/api/phone/workflow"}:
            raise api.WorkflowError("发送回执入口无效。", 403)
        from workflow_guide_reply import _request, _digest, _object
        params = parse_qs(query, keep_blank_values=True)
        keys = {"requestId", "clientId", "sessionId"}
        if len(query) > 400 or set(params) != keys or any(len(values) != 1 for values in params.values()):
            raise api.WorkflowError("发送回执地址无效。")
        identifier = _request(params["requestId"][0])
        client_id, session_id = _client(params["clientId"][0]), api._id(params["sessionId"][0])
        if params["requestId"][0] != identifier or params["clientId"][0] != client_id or params["sessionId"][0] != session_id:
            raise api.WorkflowError("发送回执身份无效。")

        def read(db):
            db.execute("BEGIN")
            entry = db.execute("SELECT * FROM requests WHERE id=?", (identifier,)).fetchone()
            if entry is None:
                raise api.WorkflowError("原发送回执不存在。", 404, "send_receipt_not_found")
            if entry["kind"] != "mobile_dialogue_send":
                raise api.WorkflowError("原请求不是讨论发送。", 409, "send_source_not_matching")
            session = self._mobile_session(db, client_id, session_id)
            record_id = session["recordId"]
            saved = _object(entry["response"])
            if (set(saved) not in ({"sessionId", "jobId"}, {"sessionId", "jobId", "sourceMessageId"})
                    or saved.get("sessionId") != session_id):
                raise api.WorkflowError("原发送回执不属于指定讨论。", 409, "send_source_not_matching")
            job = db.execute("SELECT * FROM jobs WHERE id=? AND record_id=? AND request_id=?", (saved.get("jobId"), record_id, identifier)).fetchone()
            if job is None:
                raise api.WorkflowError("原发送来源无法核对。", 409, "send_source_not_matching")
            if saved.get("sourceMessageId"):
                candidates = db.execute("SELECT * FROM messages WHERE id=? AND role='user' AND record_id=?", (saved["sourceMessageId"], record_id)).fetchall()
            else:
                payload = _object(job["payload"])
                candidates = db.execute("SELECT * FROM messages WHERE role='user' AND record_id=? AND created_at=? AND text=?",
                    (record_id, job["created_at"], payload.get("text"))).fetchall()
                context = payload.get("context")
                if not isinstance(context, dict):
                    raise api.WorkflowError("原发送冻结来源无法核对。", 409, "send_source_not_matching")
                attachments = context.get("attachmentIds")
                candidates = [row for row in candidates if json.loads(row["attachment_ids"]) == attachments]
            if len(candidates) != 1 or self._guide_original_send(db, candidates[0], session) != (job["id"], identifier):
                raise api.WorkflowError("原发送来源无法核对。", 409, "send_source_not_matching")
            user = candidates[0]
            if not re.fullmatch(r"[a-f0-9]{64}", entry["fingerprint"]):
                raise api.WorkflowError("原发送凭据无法核对。", 409, "send_source_not_matching")
            receipt = {"requestId": identifier, "clientId": client_id, "sessionId": session_id, "recordId": record_id,
                "jobId": job["id"], "sourceUserMessageId": user["id"], "requestSha256": entry["fingerprint"],
                "textSha256": _digest(user["text"]), "attachmentIds": json.loads(user["attachment_ids"]), "acceptedAt": user["created_at"]}
            return {"sendReceipt": receipt, "isCurrent": self._mobile_client_state(db, client_id)["currentSessionId"] == session_id}

        return self._guide_read(read, authorize)

    def mobile_dialogue_save(self, body, prefix="/api/workflow", authorize=None):
        return self._mobile_dialogue_write("save", body, prefix, authorize)

    def _mobile_prepare_images(self, files, staging):
        api = _api()
        if (not isinstance(files, (list, tuple)) or not 1 <= len(files) <= api.MAX_ATTACHMENTS
                or any(not isinstance(file, api.IncomingFile) or type(file.size) is not int
                    or not 0 < file.size <= api.MAX_FILE_BYTES for file in files)):
            raise api.WorkflowError("请明确选择一至四张有效图片。")
        if any(file.size > MOBILE_IMAGE_BYTES for file in files):
            raise api.WorkflowError("手机想法每张原图最多 8 MB；原文件与草稿已保留，请缩小图片后再保存。", 413, "idea_image_size_limit")
        if sum(file.size for file in files) > api.MAX_UPLOAD:
            raise api.WorkflowError("上传总大小不能超过 24 MB。", 413)
        prepared = []
        try:
            for index, file in enumerate(files):
                name = api._filename(file.name)
                if Path(name).suffix.lower() not in api.IMAGE_TYPES:
                    raise api.WorkflowError("本次讨论上传只接受图片。", 415)
                path, preview = staging / (str(index) + ".image"), staging / (str(index) + ".preview.jpg")
                digest = file.copy_to(path)
                if path.stat().st_size != file.size:
                    raise api.WorkflowError("图片实际大小不符，内容未保存。", 415)
                extension, detected, has_preview = api._image(path, name, preview)
                allowed = {detected, "application/octet-stream"}
                if detected == "image/jpeg":
                    allowed.add("image/jpg")
                if detected == "image/heic":
                    allowed.add("image/heif")
                if file.mime_type not in allowed:
                    raise api.WorkflowError("图片类型与实际内容不符。", 415)
                prepared.append({"name": name, "declaredType": file.mime_type, "mimeType": detected,
                    "size": file.size, "sha256": digest, "extension": extension,
                    "path": path, "preview": preview, "hasPreview": has_preview})
        except (api.TransferError, OSError) as error:
            raise api.WorkflowError(str(error), getattr(error, "status", 415)) from error
        return prepared

    def _mobile_install_image(self, db, record_id, image, created):
        """Exclusive persistence and cleanup of this invocation's actual files only."""
        api = _api()
        identifier = uuid.uuid4().hex
        if db.execute("SELECT 1 FROM attachments WHERE id=?", (identifier,)).fetchone():
            raise api.WorkflowError("图片标识冲突，原文件已保留，请重新选择。", 409, "image_source_mismatch")
        filename = identifier + image["extension"]
        pairs = [(image["path"], api._safe_child(self.attachments_dir, filename))]
        if image["hasPreview"]:
            pairs.append((image["preview"], api._safe_child(self.attachments_dir, identifier + ".preview.jpg")))
        try:
            for source, target in pairs:
                with source.open("rb") as incoming, target.open("xb") as output:
                    created.append(target)
                    shutil.copyfileobj(incoming, output, 65536)
                    output.flush()
                    os.fsync(output.fileno())
        except (OSError, api.TransferError) as error:
            raise api.WorkflowError("图片保存失败，原文件已保留。", 409, "image_source_mismatch") from error
        db.execute("INSERT INTO attachments VALUES (?,?,?,?,?,?,?,?)", (identifier, record_id, image["name"], filename,
            image["mimeType"], image["size"], int(image["hasPreview"]), None))
        return identifier

    def mobile_dialogue_upload(self, fields, files, prefix="/api/workflow", authorize=None):
        api = _api()
        if authorize:
            authorize()
        _body(fields, {"requestId", "recordId", "text"})
        if set(fields) != {"requestId", "recordId", "text"}:
            raise api.WorkflowError("讨论图片上传缺少确切来源。")
        text = api._text(fields["text"], 4096)
        def exact_object(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise api.WorkflowError("讨论图片来源字段重复。")
                value[key] = item
            return value
        try:
            body = json.loads(text, object_pairs_hook=exact_object)
        except (ValueError, TypeError) as error:
            if isinstance(error, api.WorkflowError):
                raise
            raise api.WorkflowError("讨论图片来源无效。") from error
        _body(body, {"clientId", "sessionId", "expectedRevision"})
        if set(body) != {"clientId", "sessionId", "expectedRevision"}:
            raise api.WorkflowError("讨论图片来源不完整。")
        client_id, record_id = _client(body["clientId"]), api._id(fields["recordId"])
        created, committed = [], False
        try:
            with tempfile.TemporaryDirectory(prefix="mobile-dialogue-", dir=self.jobs_dir) as folder:
                prepared = self._mobile_prepare_images(files, Path(folder))
                nonce = {**fields, "files": [{key: image[key] for key in ("name", "declaredType", "mimeType", "size", "sha256")}
                    for image in prepared]}
                with self._db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    old = self._receipt(db, "mobile_dialogue_upload", nonce)
                    if old:
                        session = self._mobile_session(db, client_id, old["sessionId"])
                        if session["id"] != body["sessionId"] or session["recordId"] != record_id:
                            raise api.WorkflowError("原图片回执来源不匹配。", 409, "image_source_mismatch")
                        identifiers = old["attachmentIds"]
                    else:
                        session = self._mobile_guard(db, body, client_id)
                        self._mobile_source_guard(db, session)
                        if session["recordId"] != record_id:
                            raise api.WorkflowError("图片记录不属于此讨论。", 403, "image_source_mismatch")
                        identifiers = [self._mobile_install_image(db, record_id, image, created) for image in prepared]
                        session["uploadedAttachmentIds"] = session.get("uploadedAttachmentIds", []) + identifiers
                        session["uploadedAttachmentProofs"] = {**session.get("uploadedAttachmentProofs", {}),
                            **{identifier: {key: image[key] for key in ("sha256", "size", "mimeType")}
                                for identifier, image in zip(identifiers, prepared)}}
                        self._mobile_save_session(db, session)
                        self._receipt(db, "mobile_dialogue_upload", nonce, {"sessionId": session["id"], "attachmentIds": identifiers})
                        self._revision(db, True)
                    if authorize:
                        authorize()
                committed = True
            return self._mobile_state(client_id, prefix, session["id"], uploadedAttachmentIds=identifiers, duplicate=old is not None)
        finally:
            if not committed:
                for path in reversed(created):
                    path.unlink(missing_ok=True)

    def _mobile_dialogue_write(self, action, body, prefix, authorize):
        api = _api()
        _body(body, {"requestId", "clientId", "sessionId", "expectedRevision", "text", "attachmentIds", "requestedProfile", "chatTransport", "subscription"})
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
                    if db.execute("SELECT 1 FROM idea_dispatches WHERE json_extract(snapshot,'$.recordId')=? AND status IN ('pending','claimed','waiting','needs_review')", (session["recordId"],)).fetchone():
                        raise api.WorkflowError("当前讨论已有请求在途，请等待回答或核对送达。", 409, "dispatch_in_progress")
                    record = self._record(db, session["recordId"])
                    source = self._source_task(db, record["id"], {"ideaId": session["ideaId"], "revision": session["ideaRevision"]} if session["ideaId"] else None)
                    if source and not session["ideaId"]:
                        raise api.WorkflowError("讨论来源已改变，请重新打开此想法。", 409, "task_source_mismatch")
                    subscription = None
                    if session["chatTransport"] == "chatgpt_subscription":
                        adapter = getattr(self, "subscription", None)
                        selection = session.get("subscription")
                        if adapter is None or selection is None:
                            raise api.WorkflowError("请先在电脑连接 ChatGPT 订阅，并明确选择实际模型。", 409, "subscription_not_connected")
                        subscription = (adapter.validate_selection(selection["modelSlug"], selection["catalogRevision"], selection["connectionId"],
                            requestedProfile=selection["requestedProfile"]) if "requestedProfile" in selection else
                            adapter.validate_selection(selection["modelSlug"], selection["catalogRevision"], selection["connectionId"]))
                        if subscription != selection:
                            raise api.WorkflowError("订阅模型目录已改变，请重新选择；原草稿保留。", 409, "subscription_selection_stale")
                    target = self._app_target(db, {"kind": "chatgpt", "mode": "new", "threadId": "", "name": "Console 手机讨论"}, bool(context["attachmentIds"]))
                    dialogue = {key: session[key] for key in ("id", "clientId", "recordId", "ideaId", "ideaRevision", "revision")}
                    payload = {"computerId": self._setting(db, "computer")["id"], "projectId": record["project_id"],
                        "text": text, "context": context, "purpose": "discussion", "sourceTask": source,
                        "appTarget": target, "requestedProfile": session["requestedProfile"], "mobileDialogue": dialogue}
                    payload["chatTransport"] = session["chatTransport"]
                    if subscription is not None:
                        payload["subscription"] = subscription
                    payload["appFrozen"] = self._freeze_app_discussion(db, record, payload, None)
                    payload["appFrozen"].pop("actionPlanning", None)
                    payload["appFrozen"].update(requestedProfile=session["requestedProfile"], mobileDialogue=dialogue)
                    payload["appFrozen"]["chatTransport"] = session["chatTransport"]
                    if subscription is not None:
                        payload["appFrozen"]["subscription"] = subscription
                    if source:
                        meta = self._mobile_metadata(db, source["ideaId"])
                        payload["appFrozen"]["mobileIdeaContext"] = self._mobile_current_idea_context(db, source)
                        if sum(len(point["text"]) for point in meta["keyPoints"]) + sum(len(item["content"]) for item in payload["appFrozen"]["history"]) > 65000:
                            raise api.WorkflowError("当前长期要点与讨论历史过长，请缩小本轮上下文。")
                    job_id, now = uuid.uuid4().hex, api._now()
                    self._insert_app_dispatch(db, job_id, record, payload, now, body["requestId"])
                    db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (job_id, record["id"], "discuss", body["requestId"],
                        api._json(payload), "waiting", 1, None, now, now,
                        "已确认此消息；等待 ChatGPT 订阅连接发送，尚未发送。" if subscription is not None else
                        "已确认此消息；等待普通 Chat 转发器核对所选档位，尚未发送。", "", "{}"))
                    source_message_id = self._message(db, record["id"], "user", text, attachment_ids=context["attachmentIds"], created_at=now)
                    self._guide_bind_user_message(db, source_message_id, session, job_id, body["requestId"])
                    session["draft"] = {"text": "", "attachmentIds": []}
                    saved["jobId"] = job_id
                    saved["sourceMessageId"] = source_message_id
                elif action == "save":
                    idea = self._idea(db, session["ideaId"]) if session["ideaId"] else None
                    if idea and idea["revision"] != session["ideaRevision"]:
                        raise api.WorkflowError("想法已更新，请重新读取后补充。", 409, "revision_conflict")
                    original_ids = self._mobile_original_ids(db, idea["id"]) if idea else []
                    if any(self._mobile_image_row(db, session["recordId"], identifier)["size"] > MOBILE_IMAGE_BYTES
                            for identifier in context["attachmentIds"]):
                        raise api.WorkflowError("手机想法每张原图最多 8 MB；已选原文件与草稿已保留，请缩小图片后再保存。", 413, "idea_image_size_limit")
                    saved_ids = list(dict.fromkeys(original_ids + context["attachmentIds"]))
                    if len(saved_ids) > api.MAX_ATTACHMENTS:
                        raise api.WorkflowError("同一想法最多保存四张原图；原想法与本轮草稿已保留，请另存或缩小范围。", 413, "idea_images_limit")
                    total = sum(self._mobile_image_proof(self._mobile_image_row(db, session["recordId"], identifier))["size"]
                        for identifier in saved_ids)
                    if total > api.MAX_UPLOAD:
                        raise api.WorkflowError("同一想法原图总大小不能超过 24 MB；原想法与本轮草稿已保留。", 413, "idea_images_limit")
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
                    meta = self._mobile_metadata(db, idea["id"])
                    meta["attachmentIds"] = saved_ids
                    self._set_setting(db, "mobile-idea:" + idea["id"], meta)
                    session.update(ideaId=idea["id"], ideaRevision=idea["revision"])
                    identifiers, proofs = self._mobile_freeze_originals(db, idea["id"])
                    session.update(eligibleAttachmentIds=identifiers, eligibleAttachmentProofs=proofs)
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

    def _mobile_current_idea_context(self, db, source):
        """Read current reviewed source only; callers must freeze final scope explicitly."""
        row = self._idea(db, source["ideaId"])
        if row["revision"] != source["revision"]:
            raise _api().WorkflowError("想法已更新，请重新核对本轮要点。", 409, "revision_conflict")
        meta = self._mobile_metadata(db, row["id"])
        return {"id": row["id"], "revision": row["revision"],
            "keyPoints": [{key: point[key] for key in ("id", "text", "kind")} for point in meta["keyPoints"]],
            "provenance": [{key: item[key] for key in ("id", "kind", "destinationRevision")} for item in meta["provenance"]]}

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
        point_added = bool(point) and len(meta["keyPoints"]) < 100
        if point_added:
            meta["keyPoints"].append({"id": uuid.uuid4().hex, "text": point, "kind": "suggestion", "source": value})
        self._set_setting(db, "mobile-idea:" + idea_id, meta)
        return point_added

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
                guide = db.execute("SELECT * FROM guide_replies WHERE message_id=?", (body["sourceMessageId"],)).fetchone()
                guide_valid = (guide is not None and message is not None and guide["client_id"] == client_id
                    and guide["session_id"] == session["id"] and guide["record_id"] == session["recordId"]
                    and guide["text_sha256"] == hashlib.sha256(message["text"].encode("utf-8")).hexdigest())
                if message is None or (not guide_valid and (guide is not None or len(jobs) != 1
                        or json.loads(jobs[0]["result"]).get("text") != message["text"])):
                    raise api.WorkflowError("请只保存此讨论已完成的实际回答。", 409, "answer_source_mismatch")
                if guide_valid:
                    self._guide_user_source(db, guide["source_user_message_id"], session)
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
                if guide_valid:
                    provenance = {"kind": "assistant_suggestion", "sourceSessionId": session["id"],
                        "sourceSessionRevision": session["revision"], "sourceRecordId": session["recordId"],
                        "sourceMessageId": message["id"], "guideSource": self._guide_public_source(guide)}
                else:
                    payload = json.loads(jobs[0]["payload"])
                    source = payload.get("sourceTask") or {}
                    dialogue = payload.get("mobileDialogue") or {}
                    provenance = {"kind": "assistant_suggestion", "sourceSessionId": dialogue.get("id", session["id"]),
                        "sourceSessionRevision": dialogue.get("revision", session["revision"]), "sourceRecordId": session["recordId"],
                        "sourceMessageId": message["id"], "sourceJobId": jobs[0]["id"], "sourceIdeaId": source.get("ideaId"), "sourceIdeaRevision": source.get("revision")}
                point_added = self._mobile_add_provenance(db, idea["id"], provenance, message["text"])
                if session["ideaId"] == idea["id"]:
                    session["ideaRevision"] = idea["revision"]
                self._mobile_save_session(db, session)
                saved = {"sessionId": session["id"], "ideaId": idea["id"], "keyPointAdded": point_added}
                if not point_added:
                    saved["keyPointOmittedReason"] = "point_limit"
                self._receipt(db, "mobile_dialogue_remember", body, saved)
                self._revision(db, True)
            if authorize:
                authorize()
            idea = self._mobile_idea(db, self._idea(db, saved["ideaId"]))
        return self._mobile_state(client_id, prefix, saved["sessionId"], idea=idea, duplicate=old is not None,
            **{key: saved[key] for key in ("keyPointAdded", "keyPointOmittedReason") if key in saved})

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

    def mobile_idea_split(self, body, prefix="/api/workflow", authorize=None):
        return self._mobile_idea_manage("split", body, prefix, authorize)

    def mobile_idea_merge(self, body, prefix="/api/workflow", authorize=None):
        return self._mobile_idea_manage("merge", body, prefix, authorize)

    def _mobile_management_points(self, sources):
        api = _api()
        points, seen = [], {}
        for source in sources:
            for point in source["metadata"].get("keyPoints", []):
                text = api._text(point.get("text"))
                kind = point.get("kind")
                if not text.strip() or kind not in {"decision", "suggestion"}:
                    raise api.WorkflowError("原要点无法核对，请先编辑原想法。")
                key = (text, kind)
                origin = {"sourceIdeaId": source["id"], "sourceIdeaRevision": source["revision"],
                    "sourcePointId": api._id(point.get("id"))}
                if key in seen:
                    points[seen[key]]["sources"].append(origin)
                else:
                    seen[key] = len(points)
                    points.append({"id": uuid.uuid4().hex, "text": text, "kind": kind,
                        "source": origin, "sources": [origin]})
        if len(points) > 100:
            raise api.WorkflowError("合并后的长期要点超过 100 条，请先缩小范围。")
        return points

    def _mobile_idea_manage(self, action, body, prefix, authorize):
        api = _api()
        fields = {"id", "expectedRevision", "start", "end"} if action == "split" else {"firstId", "firstRevision", "secondId", "secondRevision"}
        _body(body, {"requestId", "title", "attachmentIds"} | fields)
        title = api._text(body.get("title"), 80).strip()
        if not title:
            raise api.WorkflowError("请为新想法填写标题。")
        selected = body.get("attachmentIds", [])
        if (not isinstance(selected, list) or len(selected) > api.MAX_ATTACHMENTS
                or any(not isinstance(item, str) for item in selected) or len(set(selected)) != len(selected)):
            raise api.WorkflowError("请明确选择最多四张不同原图。")
        selected = [api._id(item) for item in selected]
        if authorize:
            authorize()
        created, committed = [], False
        try:
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                kind = "mobile_idea_" + action
                old = self._receipt(db, kind, body)
                if old:
                    identifier = old["ideaId"]
                else:
                    wanted = [(body.get("id"), body.get("expectedRevision"))] if action == "split" else [
                        (body.get("firstId"), body.get("firstRevision")), (body.get("secondId"), body.get("secondRevision"))]
                    if action == "merge" and wanted[0][0] == wanted[1][0]:
                        raise api.WorkflowError("请选择两条不同的原想法。")
                    sources = []
                    for source_id, expected in wanted:
                        row = self._idea(db, source_id)
                        if _revision(expected) != row["revision"]:
                            raise api.WorkflowError("原想法已更新，请保留预览后重新核对。", 409, "revision_conflict")
                        meta = self._mobile_metadata(db, row["id"])
                        sources.append({"id": row["id"], "revision": row["revision"], "title": row["title"], "body": row["body"],
                            "sourceBodySha256": hashlib.sha256(row["body"].encode("utf-8")).hexdigest(),
                            "workflowRecordId": self._setting(db, "task-record:" + row["id"]), "metadata": meta})
                    if action == "split":
                        start, end = body.get("start"), body.get("end")
                        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(sources[0]["body"]):
                            raise api.WorkflowError("请明确选择原正文内的 Unicode 字符范围。")
                        text = sources[0]["body"][start:end]
                        if any(0xD800 <= ord(character) <= 0xDFFF for character in text):
                            raise api.WorkflowError("所选文字包含不完整 Unicode 字符。")
                        execution, points = "", []
                    else:
                        text = "\n\n".join(source["body"] for source in sources if source["body"])
                        execution = "\n\n".join(source["metadata"].get("executionDraft", "") for source in sources
                            if source["metadata"].get("executionDraft", ""))
                        points = self._mobile_management_points(sources)
                    text, execution = api._text(text), api._text(execution)
                    candidates = {}
                    if selected:
                        for source in sources:
                            for attachment_id in self._mobile_original_ids(db, source["id"]):
                                candidates[attachment_id] = source
                        if any(attachment_id not in candidates for attachment_id in selected):
                            raise api.WorkflowError("所选图片不属于这些原想法。", 403, "image_source_mismatch")
                    idea = self._mobile_create_idea(db, text)
                    identifier = idea["id"]
                    db.execute("UPDATE ideas SET title=? WHERE id=?", (title, identifier))
                    record_id = self._mobile_new_record(db, title)
                    self._set_setting(db, "task-record:" + identifier, record_id)
                    attachments, image_sources = [], []
                    if selected:
                        with tempfile.TemporaryDirectory(prefix="mobile-management-", dir=self.jobs_dir) as folder:
                            files = []
                            for attachment_id in selected:
                                source = candidates[attachment_id]
                                row = self._mobile_image_row(db, source["workflowRecordId"], attachment_id)
                                proof = self._mobile_image_proof(row)
                                files.append(api.IncomingFile(api._safe_child(self.attachments_dir, row["filename"]), 0,
                                    row["size"], row["name"], row["mime_type"]))
                                image_sources.append({"sourceAttachmentId": attachment_id, "sourceIdeaId": source["id"],
                                    "sourceIdeaRevision": source["revision"], **proof})
                            prepared = self._mobile_prepare_images(files, Path(folder))
                            for image, origin in zip(prepared, image_sources):
                                if any(image[key] != origin[key] for key in ("sha256", "size", "mimeType")):
                                    raise api.WorkflowError("复制期间原图发生改变，未保存新想法。", 409, "image_source_mismatch")
                                attachments.append(self._mobile_install_image(db, record_id, image, created))
                                origin["destinationAttachmentId"] = attachments[-1]
                        db.execute("UPDATE records SET primary_attachment_id=? WHERE id=?", (attachments[0], record_id))
                    projects = [source["metadata"].get("projectId") for source in sources]
                    project_id = projects[0] if all(project == projects[0] for project in projects) else None
                    project_id = self._mobile_classification_id(db, project_id)
                    meta = {"projectId": project_id, "archived": False, "keyPoints": points,
                        "executionDraft": execution, "provenance": [], "attachmentIds": attachments}
                    self._set_setting(db, "mobile-idea:" + identifier, meta)
                    provenance = {"kind": "user_" + action, "sourceClaim": True, "authorityVerified": False,
                        "sources": [{"ideaId": source["id"], "revision": source["revision"],
                            "sourceRecordId": source["workflowRecordId"], "sourceBodySha256": source["sourceBodySha256"]} for source in sources],
                        "images": image_sources}
                    if action == "split":
                        provenance["selection"] = {"start": body["start"], "end": body["end"], "unit": "unicode_codepoints"}
                    self._mobile_add_provenance(db, identifier, provenance)
                    self._set_setting(db, "mobile-idea-op-source:" + identifier, {"action": action, "sources": sources,
                        "selection": provenance.get("selection"), "images": image_sources})
                    self._receipt(db, kind, body, {"ideaId": identifier})
                    self._revision(db, True)
                if authorize:
                    authorize()
                idea, revision = self._mobile_idea(db, self._idea(db, identifier)), self._revision(db)
            committed = True
            return {"idea": idea, "detail": self.detail(idea["workflowRecordId"], prefix),
                "duplicate": old is not None, "revision": revision}
        finally:
            if not committed:
                for path in reversed(created):
                    path.unlink(missing_ok=True)

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
                        meta["projectId"] = self._mobile_classification_id(db, body["projectId"])
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
