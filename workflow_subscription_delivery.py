"""Durable, scoped subscription delivery. No credentials or network operations."""
from __future__ import annotations

import json
import re
import uuid

PROVIDER = "chatgpt_subscription"
MAX_ANSWER = 128 * 1024


def _api():
    import workflow_service
    return workflow_service


class DispatchFanout:
    def __init__(self, listeners=()):
        self.listeners = tuple(listeners)

    def notify_committed(self, identifiers):
        for listener in self.listeners:
            try:
                listener.notify_committed(identifiers)
            except Exception:
                # Durable acceptance must never become a retry instruction.
                pass

    def notify_released(self, identifiers):
        for listener in self.listeners:
            try:
                listener.notify_released(identifiers)
            except Exception:
                pass


class SubscriptionDeliveryMixin:
    def register_dispatch_notifier(self, listener):
        with self._lock:
            current = self._dispatch_commit_notifier
            listeners = current.listeners if isinstance(current, DispatchFanout) else (current,) if current else ()
            if listener not in listeners:
                self._dispatch_commit_notifier = DispatchFanout((*listeners, listener))

    def unregister_dispatch_notifier(self, listener):
        with self._lock:
            current = self._dispatch_commit_notifier
            listeners = current.listeners if isinstance(current, DispatchFanout) else (current,) if current else ()
            if listener not in listeners:
                return
            remaining = tuple(item for item in listeners if item is not listener)
            self._dispatch_commit_notifier = DispatchFanout(remaining) if remaining else None

    def _subscription_source(self, db, dispatch_id, binding=None, token=None):
        api = _api()
        row = self._dispatch(db, api._id(dispatch_id))
        snapshot = json.loads(row["snapshot"])
        subscription = snapshot.get("subscription")
        if (not isinstance(subscription, dict)
                or set(subscription) != {"provider", "connectionId", "catalogRevision", "modelSlug"}
                or subscription.get("provider") != PROVIDER
                or snapshot.get("chatTransport") != PROVIDER
                or snapshot.get("origin") != "workflow_discussion"
                or row["target_kind"] != "chatgpt" or row["target_mode"] != "new"
                or row["target_thread_id"] not in (None, "")):
            raise api.WorkflowError("这条记录不属于正式订阅连接；未发送。", 409, "subscription_source_mismatch")
        if binding is not None and subscription != binding:
            raise api.WorkflowError("订阅连接与确认来源不匹配；未发送。", 409, "subscription_source_mismatch")
        if token is not None and (not token or row["claim_token"] != token):
            raise api.WorkflowError("订阅请求认领标识不匹配。", 403, "subscription_claim_mismatch")
        job = self._app_dispatch_job(db, row, snapshot)
        payload = json.loads(job["payload"])
        frozen = payload.get("appFrozen")
        if (not isinstance(frozen, dict) or payload.get("chatTransport") != PROVIDER
                or frozen.get("chatTransport") != PROVIDER
                or subscription != payload.get("subscription") or subscription != frozen.get("subscription")
                or payload.get("mobileDialogue") != snapshot.get("mobileDialogue")
                or payload.get("mobileDialogue") != frozen.get("mobileDialogue")
                or payload.get("text") != frozen.get("text")
                or not isinstance(payload.get("submissionTime"), dict)
                or payload["submissionTime"] != frozen.get("submissionTime")
                or payload["submissionTime"] != snapshot.get("submissionTime")
                or payload.get("purpose") != "discussion"
                or not row["user_confirmed_at"] or row["created_at"] != row["user_confirmed_at"]
                or job["created_at"] != row["user_confirmed_at"]):
            raise api.WorkflowError("订阅消息与原讨论冻结版本不匹配。", 409, "subscription_source_mismatch")
        return row, snapshot, job, payload

    def _recover_subscription_pending(self, db):
        """A lost process event never becomes permission to adopt an old send."""
        api = _api()
        now, count = api._now(), 0
        rows = db.execute("SELECT * FROM idea_dispatches WHERE status='pending' "
            "AND json_extract(snapshot,'$.subscription.provider')=?", (PROVIDER,)).fetchall()
        for row in rows:
            snapshot = json.loads(row["snapshot"])
            note = "电脑服务重启，本轮尚未发送；原消息保留，不会自动重发。"
            db.execute("UPDATE idea_dispatches SET status='failed',error=?,updated_at=? WHERE id=?", (note, now, row["id"]))
            db.execute("UPDATE jobs SET status='failed',error=?,updated_at=? WHERE id=? AND status='waiting'", (note, now, snapshot.get("jobId")))
            count += 1
        return count

    def subscription_claim(self, dispatch_id, binding=None):
        api = _api()
        from workflow_chat_relay_images import frozen_images
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row, snapshot, job, payload = self._subscription_source(db, dispatch_id, binding)
            provider = getattr(self, "subscription", None)
            if provider is None:
                raise api.WorkflowError("请先在电脑连接 ChatGPT 订阅。", 409, "subscription_not_connected")
            selected = snapshot["subscription"]
            verified = provider.validate_selection(selected["modelSlug"], selected["catalogRevision"], selected["connectionId"])
            if verified != selected:
                raise api.WorkflowError("订阅模型或连接已改变；未发送。", 409, "subscription_selection_changed")
            binding = verified
            if (row["status"] != "pending" or row["claim_token"] or json.loads(row["result"]) != {}
                    or job["status"] != "waiting" or json.loads(job["result"]) != {}
                    or self._setting(db, "subscription-intent:" + dispatch_id)):
                raise api.WorkflowError("本轮已认领或结束；不会重复发送。", 409, "subscription_not_pending")
            image_bytes = frozen_images(self, db, payload, snapshot, job["record_id"])
            self._check_app_images(payload)
            token, now = uuid.uuid4().hex, api._now()
            db.execute("UPDATE idea_dispatches SET status='claimed',claim_token=?,updated_at=? WHERE id=?", (token, now, dispatch_id))
            db.execute("UPDATE jobs SET error=?,updated_at=? WHERE id=?", ("已接收，正在准备这条订阅消息；尚未发送。", now, job["id"]))
            self._revision(db, True)
            return {"dispatch": self._public_dispatch(self._dispatch(db, dispatch_id), True),
                "frozen": payload["appFrozen"], "text": payload["text"], "claimToken": token,
                "subscription": binding, "imageBytes": image_bytes}

    def subscription_send_intent(self, dispatch_id, claim_token, binding):
        api = _api()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row, snapshot, job, payload = self._subscription_source(db, dispatch_id, binding, claim_token)
            key = "subscription-intent:" + dispatch_id
            if row["status"] != "claimed" or job["status"] != "waiting" or self._setting(db, key):
                raise api.WorkflowError("本轮已开始发送或结束；不会重复发送。", 409, "subscription_send_reserved")
            # This marker commits before the sole network POST.
            now = api._now()
            self._set_setting(db, key, {"dispatchId": dispatch_id, "claimToken": claim_token,
                "subscription": binding, "recordedAt": now})
            db.execute("UPDATE jobs SET error=?,updated_at=? WHERE id=?", ("请求已开始，等待真实完成回答。", now, job["id"]))
            self._revision(db, True)
            return {"sendIntentRecorded": True, "confirmedAt": now}

    def subscription_complete(self, dispatch_id, claim_token, receipt):
        api = _api()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row, snapshot, job, payload = self._subscription_source(db, dispatch_id, token=claim_token)
            if row["status"] == "completed":
                return {"duplicate": True, "job": self._job_public(db, job)}
            intent = self._setting(db, "subscription-intent:" + dispatch_id)
            model, text = payload["subscription"]["modelSlug"], receipt.get("output") if isinstance(receipt, dict) else None
            if (row["status"] != "claimed" or job["status"] != "waiting"
                    or not intent or intent.get("claimToken") != claim_token
                    or intent.get("subscription") != payload["subscription"]
                    or not isinstance(text, str) or not text.strip() or len(text) > MAX_ANSWER or "\0" in text
                    or receipt.get("ok") is not True or receipt.get("status") != "completed"
                    or receipt.get("terminalEventObserved") is not True or receipt.get("terminalStatus") != "completed"
                    or receipt.get("completionEvidence") != "response.completed"
                    or receipt.get("responseCompleted") is not True
                    or receipt.get("providerErrorObserved") is not False
                    or receipt.get("requestedModel") != model or receipt.get("actualModel") != model
                    or not isinstance(receipt.get("responseId"), str)
                    or not re.fullmatch(r"resp_[A-Za-z0-9_-]{1,190}", receipt["responseId"])):
                raise api.WorkflowError("订阅回答缺少准确完成回执；未标记成功。", 409, "subscription_completion_unverified")
            now = api._now()
            message = self._message(db, job["record_id"], "assistant", text, text_limit=MAX_ANSWER)
            saved = {"text": text, "messageId": message, "attachmentIds": [], "dispatchId": dispatch_id,
                "source": PROVIDER, "responseId": receipt["responseId"], "requestedModel": model,
                "actualModel": receipt["actualModel"], "terminalEventObserved": True, "terminalStatus": "completed",
                "completionEvidence": "response.completed", "completionSource": receipt.get("completionSource"),
                "providerErrorObserved": False, "subscription": payload["subscription"], "completedAt": now}
            db.execute("UPDATE jobs SET status='succeeded',result=?,error='',updated_at=? WHERE id=?", (api._json(saved), now, job["id"]))
            db.execute("UPDATE idea_dispatches SET status='completed',result=?,error='',updated_at=? WHERE id=?", (api._json(saved), now, dispatch_id))
            self._revision(db, True)
            return {"duplicate": False, "job": self._job_public(db, db.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone())}

    def subscription_fail(self, dispatch_id, claim_token, receipt):
        api = _api()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row, snapshot, job, payload = self._subscription_source(db, dispatch_id, token=claim_token)
            if row["status"] == "claimed" and not claim_token:
                raise api.WorkflowError("订阅请求认领标识缺失。", 403, "subscription_claim_mismatch")
            if row["status"] not in {"claimed", "pending"} or job["status"] != "waiting":
                return {"duplicate": True}
            sent = bool(self._setting(db, "subscription-intent:" + dispatch_id))
            code = receipt.get("code", "subscription_unfinished") if isinstance(receipt, dict) else "subscription_unfinished"
            if not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", code):
                code = "subscription_unfinished"
            unknown = sent and (not isinstance(receipt, dict) or receipt.get("status") != "failed")
            note = ("本轮发送或完成状态未能核实；原消息保留，不会自动重发。" if unknown else
                    "本轮未完成；原消息保留，不会自动重发。") + "（" + code + "）"
            result = {"source": PROVIDER, "code": code, "status": "unknown" if unknown else "failed", "retryAllowed": False}
            if isinstance(receipt, dict) and isinstance(receipt.get("output"), str) and receipt["output"]:
                result["partialText"] = receipt["output"][:MAX_ANSWER]
                result["partialTextComplete"] = False
            now = api._now()
            db.execute("UPDATE idea_dispatches SET status=?,result=?,error=?,updated_at=? WHERE id=?",
                ("needs_review" if unknown else "failed", api._json(result), note, now, dispatch_id))
            db.execute("UPDATE jobs SET status=?,result=?,error=?,updated_at=? WHERE id=?",
                ("waiting" if unknown else "failed", api._json(result), note, now, job["id"]))
            self._revision(db, True)
            return {"duplicate": False}
