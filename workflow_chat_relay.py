"""Opt-in, event-driven ordinary Chat relay. No browser/API or registration code.

The product owns claims and durable send intent. A separately approved extension
owns visible DOM operations. Browser evidence is never a fabricated App turn.
"""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import closing
import hashlib
import json
import os
import queue
import re
import sqlite3
import threading
import uuid
from pathlib import Path
from urllib.parse import urlsplit

PROTOCOL = "console_chat_relay/v1"
HOST_NAME = "com.tx74666.codex_console_chat_relay"
EXTENSION_ID = "ggjlmdfnbknlicnibfngaenlakeabkfk"
APPROVAL_KEY = "console_chat_relay_approval"
ATTEMPT_PREFIX = "console-chat-relay:attempt:"
MAX_FRAME = 1024 * 1024
BROWSER_SURFACES = frozenset({"chrome", "edge"})


def encode(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_FRAME:
        raise ValueError("relay_frame_too_large")
    return data


def decode(data):
    if not isinstance(data, bytes) or len(data) > MAX_FRAME:
        raise ValueError("relay_frame_too_large")
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("relay_object_required")
    return value


def timestamp(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("relay_time_invalid")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("relay_time_invalid")
    return parsed


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def uuid_text(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("relay_uuid_invalid")
    return value


def approval(value, directory):
    """Validate product-private approval; absence is disabled, never provisioning."""
    if value is None or value == {"version": 1, "enabled": False}:
        return None
    fields = {"version", "enabled", "hostName", "extensionId", "pipeName", "authKeyHex", "dataDir", "domContract", "approvalConfirmedAt", "approvalVersion"}
    if not isinstance(value, dict) or set(value) != fields or value["version"] != 1 or value["enabled"] is not True or value["approvalVersion"] != 1:
        raise ValueError("relay_approval_invalid")
    if value["hostName"] != HOST_NAME or value["extensionId"] != EXTENSION_ID:
        raise ValueError("relay_identity_invalid")
    if not isinstance(value["pipeName"], str) or not re.fullmatch(r"\\\\\.\\pipe\\codex-console-chat-relay-[a-f0-9]{32}", value["pipeName"]):
        raise ValueError("relay_pipe_invalid")
    if not isinstance(value["authKeyHex"], str) or not re.fullmatch(r"[a-f0-9]{64}", value["authKeyHex"]):
        raise ValueError("relay_auth_invalid")
    if Path(value["dataDir"]).resolve() != Path(directory).resolve():
        raise ValueError("relay_store_identity_invalid")
    timestamp(value["approvalConfirmedAt"])
    contract = value["domContract"]
    if (not isinstance(contract, dict) or set(contract) != {"version", "verified", "surface", "capturedAt", "source", "observationSha256", "selectors", "profiles"}
            or contract["version"] != 1 or type(contract["verified"]) is not bool or contract["surface"] not in BROWSER_SURFACES | {"iab"}
            or contract["source"] != "cua" or not isinstance(contract["observationSha256"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", contract["observationSha256"])
            or not isinstance(contract["selectors"], dict) or not isinstance(contract["profiles"], dict)
            or set(contract["selectors"]) != {"composer", "profile", "messages", "userText", "assistantText", "completion", "send", "stop", "login", "chatMode"}
            or contract["profiles"] != {"fast": {"label": "Instant"}}):
        raise ValueError("relay_dom_contract_invalid")
    if contract["verified"] and any(
            not isinstance(item, str) or not item.strip() or len(item) > 1000
            for key, item in contract["selectors"].items() if key != "stop" or item is not None):
        raise ValueError("relay_dom_selectors_unverified")
    if any(item is not None and (not isinstance(item, str) or len(item) > 1000) for item in contract["selectors"].values()):
        raise ValueError("relay_dom_selectors_invalid")
    timestamp(contract["capturedAt"])
    encode(contract)
    return value


def read_approval(directory):
    path = Path(directory).resolve() / "workflow.sqlite3"
    if not path.is_file():
        return None
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        row = db.execute("SELECT value FROM settings WHERE key=?", (APPROVAL_KEY,)).fetchone()
    return approval(json.loads(row[0]) if row else None, directory)


def fixed_approval(environ=None, directory=None):
    environment = environ if environ is not None else os.environ
    base = environment.get("LOCALAPPDATA")
    if not base:
        return None
    expected = (Path(base) / "CodexControlConsole" / "workflow-private").resolve()
    if directory is not None and Path(directory).resolve() != expected:
        raise ValueError("relay_fixed_store_not_matching")
    path = expected / "console-chat-relay-approved.json"
    if not path.is_file() or path.stat().st_size > MAX_FRAME:
        return None
    config = approval(json.loads(path.read_text(encoding="utf-8")), expected)
    if config != read_approval(expected):
        raise ValueError("relay_approval_file_store_not_matching")
    return config


def _confirmed_pending(db, config):
    """Preserve historical rows; select only this approval's new confirmations.

    Production inserts created_at and user_confirmed_at in the same submission.
    Compare parsed instants so timezone spelling cannot cross the consent fence.
    The original human approval time stays intact. Actual browser observation
    also fences out confirmations accumulated before this connection contract.
    Invalid, split, future or pre-connection times never authorize a relay claim.
    """
    eligible_at = max(timestamp(config["approvalConfirmedAt"]),
                      timestamp(config["domContract"]["capturedAt"]))
    observed_at = datetime.now(timezone.utc)
    rows = db.execute("SELECT * FROM idea_dispatches WHERE status='pending' ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,created_at,id")
    for row in rows:
        try:
            created_at = timestamp(row["created_at"])
            confirmed_at = timestamp(row["user_confirmed_at"])
            if created_at == confirmed_at and eligible_at <= confirmed_at <= observed_at:
                yield row
        except (ValueError, TypeError, OverflowError):
            continue


def _prior_dispatch_evidence(db, row):
    """Presence, including an empty/malformed attempt, must forbid another send."""
    if row["claim_token"] or row["target_thread_id"]:
        return True
    try:
        if json.loads(row["result"]) != {}:
            return True
    except (ValueError, TypeError):
        return True
    if db.execute("SELECT 1 FROM settings WHERE key=? LIMIT 1", (ATTEMPT_PREFIX + row["id"],)).fetchone():
        return True
    return bool(db.execute("SELECT 1 FROM requests WHERE kind IN ('incubator_claim','chat_relay_claim') AND json_extract(response,'$.dispatchId')=? LIMIT 1", (row["id"],)).fetchone())


class ChatRelayController:
    """One approved connection; all task reads are caused by commit/connection events."""

    def __init__(self, service, emit):
        self.service, self.emit = service, emit
        self.client_ready = False
        self.events = set()
        self.retired_receipts = set()
        self.active = None
        self.blocked_reason = None
        self.lock = threading.RLock()

    def config(self):
        return fixed_approval(directory=self.service.data_dir)

    def status(self):
        try:
            config = self.config()
        except (ValueError, OSError):
            config = None
        usable = bool(config and config["domContract"]["verified"] and config["domContract"]["surface"] in BROWSER_SURFACES)
        return {"protocol": PROTOCOL, "type": "status", "hostName": HOST_NAME, "enabled": bool(config),
                "approved": bool(config), "configured": bool(config), "clientReady": bool(self.client_ready and usable),
                "message": self.blocked_reason or ("approved_browser_contract" if usable else "relay_disabled_or_browser_dom_unverified")}

    def committed(self, identifiers):
        with self.lock:
            self.events.update(identifiers)
            self._drain()

    def released(self, identifiers=None):
        with self.lock:
            self._retire_failed(identifiers)
            self._drain()

    def _retire_failed(self, identifiers=None):
        """Release only an explicitly failed original identity, without rewriting it.

        Connection/release events may replay the same receipt on a new connection.
        An attempt tombstone and its unknown send outcome remain durable forever.
        """
        try:
            config = self.config()
        except (ValueError, OSError, sqlite3.Error):
            return
        if not config or config["domContract"]["verified"] is not True or config["domContract"]["surface"] not in BROWSER_SURFACES:
            return
        selected = None if identifiers is None else tuple(dict.fromkeys(identifiers))[:50]
        if selected == ():
            return
        frozen_sha = sha(encode(config).decode())
        outgoing = []
        path = self.service.data_dir / "workflow.sqlite3"
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            current = approval(self.service._setting(db, APPROVAL_KEY), self.service.data_dir)
            if current != config:
                return
            statement = ("SELECT d.id AS dispatch_id,s.value FROM idea_dispatches d JOIN settings s ON s.key=?||d.id "
                         "WHERE d.status='failed'")
            parameters = [ATTEMPT_PREFIX]
            if selected is not None:
                statement += " AND d.id IN (" + ",".join("?" for _ in selected) + ")"
                parameters.extend(selected)
            if self.retired_receipts:
                retired_ids = tuple(identifier for identifier, _ in self.retired_receipts)
                statement += " AND d.id NOT IN (" + ",".join("?" for _ in retired_ids) + ")"
                parameters.extend(retired_ids)
            statement += " ORDER BY d.updated_at DESC,d.id LIMIT 50"
            for entry in db.execute(statement, parameters):
                try:
                    saved = json.loads(entry["value"])
                    if saved["dispatchId"] != entry["dispatch_id"]:
                        continue
                    identity = {"protocol": PROTOCOL, "dispatchId": entry["dispatch_id"], "attemptId": saved["attemptId"]}
                    attempt, row = self._attempt(db, identity)
                    if row["status"] != "failed" or attempt["approvalSha256"] != frozen_sha:
                        continue
                    snapshot = json.loads(row["snapshot"])
                    if (snapshot.get("origin") != "workflow_discussion" or snapshot.get("purpose") != "discuss"
                            or row["target_kind"] != "chatgpt" or row["target_mode"] != "new"):
                        continue
                    job = self.service._app_dispatch_job(db, row, snapshot)
                    if job["status"] != "failed" or job["id"] != attempt["jobId"] or job["record_id"] != attempt["recordId"]:
                        continue
                    # A status-only change is insufficient: normal incubator/fail
                    # stores this exact immutable receipt after its explicit fail.
                    response = encode({"dispatchId": row["id"]}).decode()
                    if not db.execute("SELECT 1 FROM requests WHERE kind='incubator_fail' AND response=? LIMIT 1", (response,)).fetchone():
                        continue
                    outgoing.append({"protocol": PROTOCOL, "type": "retired", "dispatchId": row["id"],
                                     "attemptId": attempt["attemptId"], "reason": "original_dispatch_failed"})
                except (ValueError, TypeError, KeyError):
                    # Corrupt or mismatched history can never release a worker.
                    continue
        for message in outgoing:
            # Keep the fixed file/store approval matched at the emission boundary.
            try:
                if self.config() != config:
                    return
            except (ValueError, OSError, sqlite3.Error):
                return
            identity = (message["dispatchId"], message["attemptId"])
            self.emit(message)
            self.retired_receipts.add(identity)
            self.events.discard(message["dispatchId"])
            if self.active == message["dispatchId"]:
                self.active = None

    def _drain(self):
        # A known-not-sent failure consumes only its original submission event.
        # Another retained submission has its own identity and authorization.
        for _ in range(min(len(self.events), 50)):
            if self.prepare_next() != "failed":
                break

    def prepare_next(self):
        if not self.client_ready or self.active:
            return
        config = self.config()
        if not config or config["domContract"]["surface"] not in BROWSER_SURFACES or config["domContract"]["verified"] is not True:
            return
        service = self.service
        with service._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM idea_dispatches WHERE status IN ('claimed','waiting','needs_review') LIMIT 1").fetchone():
                self.blocked_reason = "dispatch_inflight"
                return
            row = next(_confirmed_pending(db, config), None)
            if row is None:
                self.blocked_reason = None
                return
            if row["id"] not in self.events:
                self.blocked_reason = "older_queue_head_requires_user_review"
                return
            if _prior_dispatch_evidence(db, row):
                self.blocked_reason = "prior_send_evidence_requires_user_review"
                return
            snapshot = json.loads(row["snapshot"])
            if (not row["user_confirmed_at"] or row["target_kind"] != "chatgpt" or row["target_mode"] != "new"
                    or snapshot.get("origin") != "workflow_discussion" or snapshot.get("purpose") != "discuss"
                    or snapshot.get("discussionPurpose", "discussion") != "discussion"):
                self.blocked_reason = "unsupported_queue_head_requires_user_review"
                return
            job = service._app_dispatch_job(db, row, snapshot)
            if job["status"] != "waiting" or json.loads(job["result"]) != {}:
                self.blocked_reason = "prior_job_result_requires_user_review"
                return
            payload = json.loads(job["payload"])
            target = payload.get("appTarget", {})
            if (target.get("kind") != "chatgpt" or target.get("mode") != "new" or target.get("threadId") not in (None, "")
                    or target.get("name") != row["target_name"] or payload.get("purpose") != "discussion"):
                self.blocked_reason = "frozen_target_requires_user_review"
                return
            if snapshot.get("attachmentIds") or payload.get("context", {}).get("attachmentIds") or payload.get("appFrozen", {}).get("images"):
                reason = "unsupported_images: 普通 Chat 转发只接受纯文字；原图与草稿保留，本次未发送。"
                db.execute("UPDATE jobs SET status='failed',error=?,updated_at=? WHERE id=?", (reason, now(), job["id"]))
                db.execute("UPDATE idea_dispatches SET status='failed',error=?,updated_at=? WHERE id=?", (reason, now(), row["id"]))
                service._revision(db, True)
                self.events.discard(row["id"])
                return "failed"
            profile = payload.get("requestedProfile")
            if profile not in {"fast", "high", "pro"} or profile != snapshot.get("requestedProfile"):
                self.blocked_reason = "profile_selection_unverified"
                return
            mapping = config["domContract"]["profiles"].get(profile)
            if profile != "fast" or mapping != {"label": "Instant"}:
                reason = "unsupported_profile: 当前档位未核实，本次未发送，未降档；原选择与内容保留，请选可用档位后明确重新发送。"
                db.execute("UPDATE jobs SET status='failed',error=?,updated_at=? WHERE id=?", (reason, now(), job["id"]))
                db.execute("UPDATE idea_dispatches SET status='failed',error=?,updated_at=? WHERE id=?", (reason, now(), row["id"]))
                service._revision(db, True)
                self.events.discard(row["id"])
                return "failed"
            service._check_app_images(payload)
            marker = "[Codex Console 发布编号：" + row["id"] + "]"
            if row["prompt"].count(marker) != 1:
                return
            attempt = {"dispatchId": row["id"], "attemptId": str(uuid.uuid4()), "claimToken": uuid.uuid4().hex,
                       "jobId": job["id"], "recordId": row["snapshot"] and snapshot["recordId"], "phase": "prepared_requested",
                       "promptSha256": sha(row["prompt"]), "requestedProfile": profile, "profileLabel": mapping["label"],
                       "observationSha256": config["domContract"]["observationSha256"],
                       "approvalSha256": sha(encode(config).decode()),
                       "createdAt": now(), "sendIntentAt": None, "conversationUrl": None}
            service._set_setting(db, ATTEMPT_PREFIX + row["id"], attempt)
            db.execute("UPDATE idea_dispatches SET status='claimed',claim_token=?,updated_at=? WHERE id=?", (attempt["claimToken"], now(), row["id"]))
            service._revision(db, True)
            outgoing = {"protocol": PROTOCOL, "type": "prepare", "dispatchId": row["id"], "attemptId": attempt["attemptId"],
                        "prompt": row["prompt"], "promptSha256": attempt["promptSha256"], "requestedProfile": profile,
                        "target": {"kind": "chatgpt", "mode": "new"}, "domContract": config["domContract"]}
        self.active = attempt["dispatchId"]
        self.events.discard(attempt["dispatchId"])
        self.blocked_reason = None
        self.emit(outgoing)
        return "prepared"

    def _attempt(self, db, message):
        if (message.get("protocol") != PROTOCOL or not re.fullmatch(r"[a-f0-9]{32}", message.get("dispatchId", ""))):
            raise ValueError("relay_message_identity_invalid")
        uuid_text(message.get("attemptId"))
        saved = self.service._setting(db, ATTEMPT_PREFIX + message["dispatchId"])
        if not saved or saved["attemptId"] != message["attemptId"]:
            raise ValueError("relay_attempt_not_matching")
        row = self.service._dispatch(db, message["dispatchId"])
        if row["claim_token"] != saved["claimToken"] or sha(row["prompt"]) != saved["promptSha256"]:
            raise ValueError("relay_frozen_dispatch_changed")
        return saved, row

    def handle(self, message):
        try:
            return self._handle(message)
        except (ValueError, TypeError, KeyError) as failure:
            self.disconnect(str(failure))
            raise ValueError(str(failure)) from failure

    def _handle(self, message):
        with self.lock:
            if message.get("type") in {"hello", "status", "ready"}:
                fields = {"protocol", "type", "hostName"} | ({"clientReady"} if message["type"] == "ready" else set())
                if set(message) != fields or message["protocol"] != PROTOCOL or message["hostName"] != HOST_NAME:
                    raise ValueError("relay_handshake_invalid")
                if message["type"] == "ready":
                    config = self.config()
                    self.client_ready = bool(message["clientReady"] is True and config and config["domContract"]["verified"] is True and config["domContract"]["surface"] in BROWSER_SURFACES)
                self.emit(self.status())
                if message["type"] in {"hello", "ready"}:
                    self._retire_failed()
                if self.client_ready:
                    self._drain()
                return
            base = {"protocol", "type", "dispatchId", "attemptId"}
            extra = {"prepared": {"observation"}, "sending": set(), "accepted": {"evidence"},
                     "capture": {"evidence"}, "blocked": {"code", "message"}, "uncertain": {"code", "message"}}.get(message.get("type"))
            if extra is None or set(message) != base | extra:
                raise ValueError("relay_message_fields_invalid")
            config = self.config()
            if not config or config["domContract"]["surface"] not in BROWSER_SURFACES or config["domContract"]["verified"] is not True:
                self.disconnect("relay_approval_revoked")
                raise ValueError("relay_approval_unavailable")
            outgoing = None
            with self.service._db() as db:
                db.execute("BEGIN IMMEDIATE")
                attempt, row = self._attempt(db, message)
                current_approval = approval(self.service._setting(db, APPROVAL_KEY), self.service.data_dir)
                if not current_approval or sha(encode(current_approval).decode()) != attempt["approvalSha256"]:
                    raise ValueError("relay_frozen_approval_changed")
                if row["status"] == "failed":
                    # Normal explicit retirement is terminal for this identity.
                    # A late DOM report must not revive it or rewrite its attempt.
                    return
                if attempt["phase"] == "completed":
                    if message["type"] == "capture" and sha(json.dumps(message["evidence"], ensure_ascii=False, sort_keys=True)) == attempt.get("captureSha256"):
                        self.emit({"protocol": PROTOCOL, "type": "stored", "dispatchId": attempt["dispatchId"], "attemptId": attempt["attemptId"],
                                   "sourceKind": "browser_dom", "actualProfileObserved": attempt["profileLabel"],
                                   "executionCapabilities": {"verified": False, "source": "browser_dom_ui_label"}})
                        return
                    raise ValueError("relay_attempt_ended")
                if attempt["phase"] == "needs_review":
                    raise ValueError("relay_attempt_needs_review")
                if attempt["phase"] == "failed":
                    # Preserve the attempt tombstone; an old failure is not new authority.
                    if message["type"] == "blocked" and attempt.get("blockedReport") == {key: message[key] for key in ("code", "message")}:
                        return
                    raise ValueError("relay_attempt_ended")
                if message["type"] == "prepared":
                    if attempt["sendIntentAt"] or attempt["phase"] != "prepared_requested":
                        raise ValueError("relay_send_already_committed")
                    observation = message["observation"]
                    if (not isinstance(observation, dict) or set(observation) != {"url", "chatMode", "loginVerified", "emptyComposer", "observedProfile", "completionInitiallyPresent", "surface", "observationSha256", "profileDom"}
                            or observation["url"] != "https://chatgpt.com/" or any(observation[key] is not True for key in ("chatMode", "loginVerified", "emptyComposer"))
                            or observation["completionInitiallyPresent"] is not False or observation["observedProfile"] != attempt["profileLabel"]
                            or observation["surface"] != config["domContract"]["surface"] or observation["observationSha256"] != attempt["observationSha256"]
                            or not isinstance(observation["profileDom"], dict) or set(observation["profileDom"]) != {"text", "reasoningEffort"}
                            or observation["profileDom"]["text"] not in {"Instant", "Thinking effortInstant", "思考强度Instant", "思考强度即时"}
                            or observation["profileDom"]["reasoningEffort"] != "none"):
                        raise ValueError("relay_prepared_dom_invalid")
                    attempt.update(phase="send_intent", sendIntentAt=now(), preparedObservation=observation)
                    outgoing = {"protocol": PROTOCOL, "type": "commitSend", "dispatchId": attempt["dispatchId"], "attemptId": attempt["attemptId"]}
                elif message["type"] in {"sending", "accepted"}:
                    if not attempt["sendIntentAt"]:
                        raise ValueError("relay_no_send_intent")
                    attempt["phase"] = "waiting"
                    if message["type"] == "accepted":
                        evidence = message["evidence"]
                        if not isinstance(evidence, dict) or set(evidence) != {"source", "conversationUrl", "sourceUserMessageId", "sourceUnitKey", "promptText", "observedAt", "profile"}:
                            raise ValueError("relay_accepted_fields_invalid")
                        conversation = self._source_evidence(row, attempt, evidence)
                        if attempt["conversationUrl"] and attempt["conversationUrl"] != evidence["conversationUrl"]:
                            raise ValueError("relay_conversation_changed")
                        if attempt.get("acceptedEvidence") and attempt["acceptedEvidence"] != evidence:
                            raise ValueError("relay_accepted_source_changed")
                        attempt.update(conversationUrl=evidence["conversationUrl"], acceptedEvidence=evidence)
                        db.execute("UPDATE idea_dispatches SET target_thread_id=?,status='waiting',updated_at=? WHERE id=?", (conversation, now(), row["id"]))
                elif message["type"] == "capture":
                    if not attempt["sendIntentAt"]:
                        raise ValueError("relay_no_send_intent")
                    self._capture(db, row, attempt, message["evidence"], current_approval["domContract"])
                    outgoing = {"protocol": PROTOCOL, "type": "stored", "dispatchId": attempt["dispatchId"], "attemptId": attempt["attemptId"],
                                "sourceKind": "browser_dom", "actualProfileObserved": attempt["profileLabel"],
                                "executionCapabilities": {"verified": False, "source": "browser_dom_ui_label"}}
                else:
                    reason = str(message["code"])[:120] + ": " + str(message["message"])[:1000]
                    if message["type"] == "blocked" and attempt["phase"] == "prepared_requested" and attempt["sendIntentAt"] is None:
                        attempt.update(phase="failed", error=reason, failedAt=now(),
                                       blockedReport={key: message[key] for key in ("code", "message")})
                        db.execute("UPDATE idea_dispatches SET status='failed',error=?,updated_at=? WHERE id=?", (reason, now(), row["id"]))
                        db.execute("UPDATE jobs SET status='failed',error=?,updated_at=? WHERE id=?", (reason, now(), attempt["jobId"]))
                    else:
                        self._review(db, row, attempt, reason)
                self.service._set_setting(db, ATTEMPT_PREFIX + row["id"], attempt)
                self.service._revision(db, True)
            if outgoing:
                # This write occurs after the transaction containing sendIntent commits.
                current_approval = self.config()
                if not current_approval or sha(encode(current_approval).decode()) != attempt["approvalSha256"]:
                    self.disconnect("relay_approval_changed_after_commit")
                    raise ValueError("relay_approval_changed_after_commit")
                self.emit(outgoing)
            if message["type"] == "capture" or attempt["phase"] == "failed":
                self.active = None
                self._drain()

    def _capture(self, db, row, attempt, evidence, contract):
        fields = {"source", "conversationUrl", "sourceUserMessageId", "assistantMessageId", "sourceUnitKey", "assistantUnitKey", "promptText", "answerText", "completion", "profile", "observedAt"}
        if not isinstance(evidence, dict) or set(evidence) != fields or evidence["source"] != "browser_dom":
            raise ValueError("relay_capture_fields_invalid")
        conversation = self._source_evidence(row, attempt, evidence)
        if attempt["conversationUrl"] and attempt["conversationUrl"] != evidence["conversationUrl"]:
            raise ValueError("relay_capture_conversation_changed")
        uuid_text(evidence["assistantMessageId"])
        if evidence["sourceUserMessageId"] == evidence["assistantMessageId"]:
            raise ValueError("relay_capture_message_alias")
        source_unit = re.fullmatch(r"fallback-turn-(\d+):(\d+):user", evidence["sourceUnitKey"])
        assistant_unit = re.fullmatch(r"fallback-turn-(\d+):(\d+):assistant", evidence["assistantUnitKey"] if isinstance(evidence["assistantUnitKey"], str) and len(evidence["assistantUnitKey"]) <= 160 else "")
        if not assistant_unit or assistant_unit[1] != source_unit[1] or int(assistant_unit[2]) <= int(source_unit[2]):
            raise ValueError("relay_capture_unit_not_same_dom_turn")
        accepted = attempt.get("acceptedEvidence")
        if accepted and any(accepted[key] != evidence[key] for key in ("conversationUrl", "sourceUserMessageId", "sourceUnitKey", "promptText", "profile")):
            raise ValueError("relay_capture_accepted_source_changed")
        answer = evidence["answerText"]
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 20000 or "\0" in answer:
            raise ValueError("relay_capture_answer_empty_or_too_long")
        completion = evidence["completion"]
        # Unknown stop is retained as null, never fabricated as "not present".
        # The caller has matched this current contract to the frozen approval SHA.
        expected_stop = None if contract["selectors"]["stop"] is None else False
        if (not isinstance(completion, dict)
                or set(completion) != {"text", "observedAfterCommit", "stopPresent"}
                or not isinstance(completion["text"], str)
                or completion["text"] not in {"Response complete", "回答已完成"}
                or completion["observedAfterCommit"] is not True
                or completion["stopPresent"] is not expected_stop):
            raise ValueError("relay_capture_not_completed")
        snapshot = json.loads(row["snapshot"])
        job = self.service._app_dispatch_job(db, row, snapshot)
        if job["record_id"] != attempt["recordId"] or job["id"] != attempt["jobId"] or job["status"] != "waiting" or row["status"] not in {"claimed", "waiting"}:
            raise ValueError("relay_capture_origin_changed")
        message_id = self.service._message(db, attempt["recordId"], "assistant", answer)
        result = {"text": answer, "sourceKind": "browser_dom", "browserEvidence": evidence, "targetThreadId": conversation,
                  "dispatchId": row["id"], "messageId": message_id, "attachmentIds": [], "actualProfileObserved": attempt["profileLabel"],
                  "executionCapabilities": {"verified": False, "source": "browser_dom_ui_label"}}
        # A DOM label is observable evidence, never a backend model/reasoning receipt.
        result["profileObservation"] = {"requestedProfile": attempt["requestedProfile"], "actualProfileObserved": attempt["profileLabel"],
            "source": "browser_dom_ui_label", "dispatchId": row["id"], "jobId": job["id"], "messageId": message_id,
            "observedAt": evidence["observedAt"], "capabilitiesVerified": False}
        db.execute("UPDATE jobs SET status='succeeded',result=?,error='',updated_at=? WHERE id=?", (encode(result).decode(), now(), job["id"]))
        db.execute("UPDATE idea_dispatches SET status='completed',target_thread_id=?,result=?,error='',updated_at=? WHERE id=?", (conversation, encode(result).decode(), now(), row["id"]))
        attempt.update(phase="completed", conversationUrl=evidence["conversationUrl"], captureSha256=sha(json.dumps(evidence, ensure_ascii=False, sort_keys=True)), completedAt=now())
        # Current mobile session is intentionally untouched; an A reply stays on A's record.

    def _source_evidence(self, row, attempt, evidence):
        if evidence["source"] != "browser_dom":
            raise ValueError("relay_capture_source_invalid")
        conversation = conversation_id(evidence["conversationUrl"])
        uuid_text(evidence["sourceUserMessageId"])
        if not isinstance(evidence["sourceUnitKey"], str) or len(evidence["sourceUnitKey"]) > 160 or not re.fullmatch(r"fallback-turn-\d+:\d+:user", evidence["sourceUnitKey"]):
            raise ValueError("relay_capture_unit_invalid")
        if evidence["promptText"] != row["prompt"] or sha(evidence["promptText"]) != attempt["promptSha256"]:
            raise ValueError("relay_capture_prompt_not_matching")
        if evidence["profile"] != {"requestedProfile": attempt["requestedProfile"], "observedBefore": attempt["profileLabel"], "observedAfter": attempt["profileLabel"]}:
            raise ValueError("relay_capture_profile_not_matching")
        observed = timestamp(evidence["observedAt"])
        if observed < timestamp(attempt["sendIntentAt"]) or (observed - datetime.now(timezone.utc)).total_seconds() > 300:
            raise ValueError("relay_capture_before_commit_or_future")
        return conversation

    def _review(self, db, row, attempt, reason):
        attempt.update(phase="needs_review", error=reason)
        db.execute("UPDATE idea_dispatches SET status='needs_review',error=?,updated_at=? WHERE id=?", (reason, now(), row["id"]))
        db.execute("UPDATE jobs SET status='waiting',error=?,updated_at=? WHERE id=?", (reason, now(), attempt["jobId"]))

    def disconnect(self, reason="relay_connection_lost"):
        with self.lock:
            self.client_ready = False
            with self.service._db() as db:
                db.execute("BEGIN IMMEDIATE")
                rows = db.execute("SELECT key,value FROM settings WHERE key LIKE ?", (ATTEMPT_PREFIX + "%",)).fetchall()
                changed = False
                for entry in rows:
                    attempt = json.loads(entry["value"])
                    if attempt["phase"] in {"completed", "failed", "needs_review"}:
                        continue
                    row = self.service._dispatch(db, attempt["dispatchId"])
                    if row["status"] == "failed":
                        # Preserve a normal explicit fail even when the browser
                        # outcome in the original attempt is still unknown.
                        continue
                    self._review(db, row, attempt, reason)
                    self.service._set_setting(db, entry["key"], attempt)
                    changed = True
                if changed:
                    self.service._revision(db, True)
            self.active = None


def conversation_id(url):
    if not isinstance(url, str):
        raise ValueError("relay_conversation_url_invalid")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "chatgpt.com" or parsed.query or parsed.fragment or not re.fullmatch(r"/c/[a-f0-9-]{36}", parsed.path):
        raise ValueError("relay_conversation_url_invalid")
    return uuid_text(parsed.path[3:])


class ChatRelayBroker:
    """Windows authenticated pipe, started only by explicit product-private approval."""

    def __init__(self, service):
        self.service = service
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.listener = self.connection = self.controller = None
        self.write_lock = threading.Lock()
        self.thread = self.event_thread = None
        self.approved_config = None

    def notify_committed(self, identifiers):
        if identifiers and not self.stop_event.is_set():
            self.events.put(("submitted", tuple(identifiers)))

    def notify_released(self, identifiers):
        if identifiers and not self.stop_event.is_set():
            self.events.put(("released", tuple(identifiers)))

    def _startup_pending(self, config):
        """One bounded adoption of post-approval production confirmations only."""
        eligible = []
        with self.service._db() as db:
            # Apply the consent fence before the adoption limit; historical
            # pending rows must neither be sent nor starve newer confirmations.
            for row in _confirmed_pending(db, config):
                try:
                    snapshot = json.loads(row["snapshot"])
                    if (_prior_dispatch_evidence(db, row)
                            or row["target_kind"] != "chatgpt" or row["target_mode"] != "new"
                            or snapshot.get("origin") != "workflow_discussion" or snapshot.get("purpose") != "discuss"
                            or snapshot.get("discussionPurpose", "discussion") != "discussion"):
                        continue
                    job = self.service._app_dispatch_job(db, row, snapshot)
                    payload = json.loads(job["payload"])
                    target = payload.get("appTarget", {})
                    if (job["status"] != "waiting" or json.loads(job["result"]) != {} or payload.get("appDispatchId") != row["id"]
                            or target.get("kind") != "chatgpt" or target.get("mode") != "new" or target.get("threadId") not in (None, "")
                            or payload.get("purpose") != "discussion" or payload.get("requestedProfile") not in {"fast", "high", "pro"}
                            or payload.get("requestedProfile") != snapshot.get("requestedProfile")
                            or row["prompt"].count("[Codex Console 发布编号：" + row["id"] + "]") != 1):
                        continue
                    self.service._check_app_images(payload)
                    eligible.append(row["id"])
                    if len(eligible) >= 50:
                        break
                except (ValueError, OSError, KeyError, TypeError):
                    continue
        return eligible

    def start(self):
        if os.name != "nt":
            return False
        config = fixed_approval(directory=self.service.data_dir)
        if not config or config["domContract"]["verified"] is not True or config["domContract"]["surface"] not in BROWSER_SURFACES:
            return False
        if self.thread and self.thread.is_alive() and not self.stop_event.is_set():
            return config == self.approved_config
        if (self.thread and self.thread.is_alive()) or (self.event_thread and self.event_thread.is_alive()):
            return False
        self.stop_event = threading.Event()
        self.events = queue.Queue()
        from multiprocessing.connection import Listener
        self.listener = Listener(config["pipeName"], family="AF_PIPE", authkey=bytes.fromhex(config["authKeyHex"]))
        self.approved_config = config
        self.service._dispatch_commit_notifier = self
        self.thread = threading.Thread(target=self._listen, args=(self.listener, self.stop_event), name="console-chat-relay-pipe", daemon=True)
        self.event_thread = threading.Thread(target=self._events, args=(self.events, self.stop_event), name="console-chat-relay-events", daemon=True)
        self.thread.start()
        self.event_thread.start()
        self.events.put(("submitted", tuple(self._startup_pending(config))))
        return True

    def public_status(self):
        enabled = bool(self.approved_config and not self.stop_event.is_set())
        if enabled:
            try:
                enabled = fixed_approval(directory=self.service.data_dir) == self.approved_config
            except (ValueError, OSError, sqlite3.Error):
                enabled = False
        controller = self.controller
        return {"enabled": enabled, "approved": enabled, "configured": enabled,
                "clientReady": bool(enabled and self.connection and controller and controller.client_ready),
                "source": "browser_dom" if enabled else None, "capabilitiesVerified": False,
                "message": controller.blocked_reason if controller and controller.blocked_reason else "approved_browser_relay" if enabled else "relay_disabled_or_browser_dom_unverified"}

    def _emit(self, message):
        with self.write_lock:
            if not self.connection:
                raise OSError("relay_connection_unavailable")
            self.connection.send_bytes(encode(message))

    def _events(self, events, stopped):
        pending = set()
        while not stopped.is_set():
            event = events.get()
            if event is None:
                break
            kind, identifiers = event
            if kind == "submitted":
                pending.update(identifiers)
            controller = self.controller
            if controller:
                try:
                    controller.committed(pending)
                    if kind == "released":
                        controller.released(identifiers)
                    # Retain event identities across extension reconnects; completed /
                    # claimed rows are never eligible for a new send on reconnect.
                    with self.service._db() as db:
                        still_pending = {row[0] for row in db.execute("SELECT id FROM idea_dispatches WHERE status='pending'")}
                    pending.intersection_update(still_pending)
                except (ValueError, OSError, sqlite3.Error):
                    controller.disconnect()

    def _listen(self, listener, stopped):
        from multiprocessing import AuthenticationError
        while not stopped.is_set():
            try:
                self.connection = listener.accept()
                if stopped.is_set():
                    self.connection.close()
                    break
                controller = self.controller = ChatRelayController(self.service, self._emit)
                # A previous process/connection attempt must never send again.
                controller.disconnect("relay_reconnected_requires_review")
                self.events.put(("connected", ()))
                while not stopped.is_set():
                    message = decode(self.connection.recv_bytes(MAX_FRAME))
                    try:
                        controller.handle(message)
                    except (ValueError, sqlite3.Error) as failure:
                        controller.disconnect(str(failure))
                        self._emit({"protocol": PROTOCOL, "type": "status", "hostName": HOST_NAME, "enabled": False,
                                    "approved": False, "configured": False, "clientReady": False, "message": str(failure)})
            except (EOFError, OSError, ValueError, AuthenticationError):
                if self.controller:
                    self.controller.disconnect()
            finally:
                if self.connection:
                    self.connection.close()
                self.connection = self.controller = None

    def close(self):
        self.stop_event.set()
        if self.service._dispatch_commit_notifier is self:
            self.service._dispatch_commit_notifier = None
        self.events.put(None)
        if self.controller:
            self.controller.disconnect("relay_product_closed_requires_review")
        connected = self.connection
        if connected:
            self.connection.close()
        elif self.listener and self.approved_config and self.thread and self.thread.is_alive():
            # Unblock this broker's own accept. Listener.close alone does not
            # cancel a Windows ConnectNamedPipe already waiting on a handle.
            config = self.approved_config
            def release_accept():
                try:
                    from multiprocessing.connection import Client
                    wake = Client(config["pipeName"], family="AF_PIPE", authkey=bytes.fromhex(config["authKeyHex"]))
                    wake.close()
                except (OSError, EOFError):
                    pass
            wake = threading.Thread(target=release_accept, name="console-relay-close-accept", daemon=True)
            wake.start()
            wake.join(timeout=0.5)
        if self.listener:
            self.listener.close()
        self.connection = self.controller = self.listener = None
        self.approved_config = None
        for worker in (self.thread, self.event_thread):
            if worker and worker is not threading.current_thread():
                worker.join(timeout=0.5)
