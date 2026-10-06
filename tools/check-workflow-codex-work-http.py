#!/usr/bin/env python3
"""Real paired-phone HTTP with temporary data and inert Work/identity fixtures.

No real controller, provider, OAuth, permission setup or model request is made.
The legacy fixture contributes only its local HTTP server and pairing helpers;
none of its script-execution tests are inherited or run.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_http import workflow_get, workflow_post
from workflow_service import WorkflowError, _now


spec = importlib.util.spec_from_file_location("codex_work_isolated_http_fixture", Path(__file__).with_name("check-workflow-http.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
PREFIX = fixture.PREFIX


def request_body(**values):
    return {"requestId": str(uuid.uuid4()), **values}


class CachedSubscription:
    binding = {"provider": "chatgpt_subscription", "connectionId": "b" * 32,
               "catalogRevision": "a" * 64, "modelSlug": "gpt-6-astra"}

    def get_status(self):
        return {"connected": True, "connectionId": self.binding["connectionId"], "catalogRevision": self.binding["catalogRevision"],
                "models": [{"slug": "gpt-6-astra", "displayName": "Isolated model"}], "status": "connected", "busy": False, "error": None}

    def validate_selection(self, model, revision, connection):
        if (model, revision, connection) != tuple(self.binding[key] for key in ("modelSlug", "catalogRevision", "connectionId")):
            raise WorkflowError("fixture selection mismatch", 409, "subscription_selection_stale")
        return dict(self.binding)

    def prepare_work_connection(self, *_args):
        raise AssertionError("A fake HTTP controller must never prepare real tokens")

    def refresh_catalog(self):
        raise AssertionError("Status/config cannot query a provider")


class InertController:
    def __init__(self, service):
        self.service = service
        self.submissions, self.interrupts, self.setups, self.runs = [], [], [], {}
        self.setup = {"status": "not_configured", "ready": False, "busy": False, "mode": "elevated",
                      "terminalEventObserved": False, "error": None, "attempted": False, "requiresAdministratorApproval": True}

    def setup_status(self):
        return dict(self.setup)

    def begin_setup(self, workspace_root):
        self.setups.append(workspace_root)
        self.setup.update(status="configuring", busy=True, attempted=True)
        return dict(self.setup)

    def submit(self, run_id, spec, callback):
        with self.service._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (run_id,)).fetchone()
            assert row is not None and row["status"] == "starting"
            assert db.execute("SELECT 1 FROM requests WHERE id=?", (row["request_id"],)).fetchone()
        self.submissions.append((run_id, copy.deepcopy(spec)))
        self.runs[run_id] = {"runId": run_id, "sourceSha256": spec["sourceSha256"],
                            "threadId": None, "turnId": None, "active": True, "callback": callback}
        return {"runId": run_id, "accepted": True, "executionVerified": False}

    def snapshot(self, run_id):
        row = self.runs.get(run_id)
        return {key: val for key, val in row.items() if key != "callback"} if row else None

    def interrupt(self, run_id, thread_id, turn_id):
        with self.service._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (run_id,)).fetchone()
            assert row["status"] == "cancelling"
            assert json.loads(row["payload"])["codexWork"]["cancelRequest"] is not None
        self.interrupts.append((run_id, thread_id, turn_id))
        return {"requestAccepted": True, "cancelVerified": False}

    def event(self, run_id, event_type, **values):
        run = self.runs[run_id]
        event = {"type": event_type, "runId": run_id, "sourceSha256": run["sourceSha256"], "threadId": run["threadId"],
                 "turnId": run["turnId"], "observedAt": _now(), **values}
        accepted = run["callback"](event)
        if accepted:
            run.update(threadId=event["threadId"], turnId=event["turnId"])
            if event_type == "terminal" and event["terminalEventObserved"] is True:
                run["active"] = False
        return accepted

    def close(self):
        pass


class CodexWorkHttpChecks(unittest.TestCase):
    request = fixture.WorkflowHttpChecks.request
    pair = fixture.WorkflowHttpChecks.pair
    detail = fixture.WorkflowHttpChecks.detail

    def setUp(self):
        fixture.WorkflowHttpChecks.setUp(self)
        self.workflow.subscription = CachedSubscription()
        self.controller = InertController(self.workflow)
        self.workflow.codex_work = self.controller
        self.allowed = self.project / "owned-work"
        self.allowed.mkdir()
        (self.allowed / "before.txt").write_text("source before", encoding="utf-8")
        self.desktop_authorizations = []
        config = workflow_post(self.workflow, "codex-work/workspaces", request_body(workspaces=[
            {"id": "fixture", "name": "Only fixture", "workspaceRoot": str(self.project), "allowedRoot": str(self.allowed)}]),
            desktop=True, authorize=lambda: self.desktop_authorizations.append("authorized"))
        self.workspace = config["workspaces"][0]

    def tearDown(self):
        fixture.WorkflowHttpChecks.tearDown(self)

    def count_jobs(self):
        with self.workflow._db() as db:
            return db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    def open_phone(self):
        self.pair()
        client = str(uuid.uuid4())
        status, state, _ = self.request(PREFIX + "mobile/dialogue/open", "POST", request_body(clientId=client))
        self.assertEqual(status, 200, state)
        return client, state

    def review_phone(self, client, state):
        session = state["session"]
        payload = request_body(recordId=session["recordId"], clientId=client, sessionId=session["id"], expectedRevision=session["revision"],
            text="手机确认本轮 Work，保留同一来源", attachmentIds=[], workspaceId=self.workspace["id"],
            workspaceAuthorizationSha256=self.workspace["authorizationSha256"], requestedProfile="high", subscription=dict(CachedSubscription.binding))
        status, review, _ = self.request(PREFIX + "codex-work/review", "POST", payload)
        self.assertEqual(status, 200, review)
        return review, payload

    def submit_phone(self, review):
        payload = request_body(reviewId=review["reviewId"], sourceSha256=review["sourceSha256"], confirmed=True)
        status, result, _ = self.request(PREFIX + "codex-work/submit", "POST", payload)
        self.assertEqual(status, 200, result)
        return result["job"], payload

    def start_phone(self):
        client, state = self.open_phone()
        review, source = self.review_phone(client, state)
        job, payload = self.submit_phone(review)
        self.assertTrue(self.controller.event(job["id"], "prepared", threadId="owned_thread", requestedProfile="high",
                                               actualModel="gpt-6-astra", actualEffort="high", sandboxVerified=True))
        self.assertTrue(self.controller.event(job["id"], "send_intent", model="gpt-6-astra", effort="high"))
        self.assertTrue(self.controller.event(job["id"], "turn_started", turnId="owned_turn", actualModel="gpt-6-astra", actualEffort="high"))
        return client, state, source, job, payload

    def terminal(self, job, **values):
        fields = {"status": "completed", "terminalStatus": "completed", "terminalEventObserved": True,
                  "report": "完整真实终态报告（隔离fixture）", "actualModel": "gpt-6-astra", "actualEffort": "high",
                  "error": None, "cancellationVerified": False, "executionVerified": False, "retryAllowed": False}
        fields.update(values)
        return self.controller.event(job["id"], "terminal", **fields)

    def test_real_phone_cookie_origin_header_gates_cover_new_get_and_post(self):
        for action in ("codex-work/config", "codex-work/runs?recordId=" + "e" * 32):
            self.assertEqual(self.request(PREFIX + action)[0], 401)
        for action in ("codex-work/review", "codex-work/submit", "codex-work/cancel", "codex-work/setup", "codex-work/workspaces"):
            self.assertEqual(self.request(PREFIX + action, "POST", {})[0], 401)
        client, state = self.open_phone()
        for headers in ({"Origin": "http://foreign.invalid"}, {"X-Codex-Phone": ""}, {"Sec-Fetch-Site": "cross-site"}):
            status, _, _ = self.request(PREFIX + "codex-work/review", "POST", {}, headers)
            self.assertEqual(status, 403)
        self.assertEqual(self.request(PREFIX + "codex-work/config", cookie="")[0], 401)
        self.assertEqual(self.request(PREFIX + "codex-work/config", cookie="codex_phone=invalid")[0], 401)
        status, config, headers = self.request(PREFIX + "codex-work/config")
        self.assertEqual(status, 200, config)
        self.assertEqual(config["workspaces"][0]["authorizationSha256"], self.workspace["authorizationSha256"])
        self.assertTrue(config["subscription"]["connected"])
        self.assertIn("no-store", dict(headers)["Cache-Control"])
        self.assertEqual(self.count_jobs(), 0)
        self.assertFalse(self.controller.submissions)

    def test_phone_review_submit_idempotent_progress_and_output_keep_exact_session(self):
        client, state = self.open_phone()
        review, source = self.review_phone(client, state)
        self.assertEqual(self.count_jobs(), 0)
        status, duplicate, _ = self.request(PREFIX + "codex-work/review", "POST", source)
        self.assertEqual(status, 200, duplicate)
        self.assertEqual(duplicate["reviewId"], review["reviewId"])
        job, payload = self.submit_phone(review)
        status, duplicate, _ = self.request(PREFIX + "codex-work/submit", "POST", payload)
        self.assertEqual(status, 200, duplicate)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["job"]["id"], job["id"])
        self.assertEqual(len(self.controller.submissions), 1)
        self.assertEqual(self.count_jobs(), 1)
        dialogue = job["mobileDialogue"]
        self.assertEqual((dialogue["id"], dialogue["clientId"], dialogue["recordId"]), (state["session"]["id"], client, state["session"]["recordId"]))
        self.assertTrue(self.controller.event(job["id"], "prepared", threadId="owned_thread", requestedProfile="high", actualModel="gpt-6-astra", actualEffort="high", sandboxVerified=True))
        self.assertTrue(self.controller.event(job["id"], "send_intent", model="gpt-6-astra", effort="high"))
        self.assertTrue(self.controller.event(job["id"], "turn_started", turnId="owned_turn", actualModel="gpt-6-astra", actualEffort="high"))
        self.assertTrue(self.controller.event(job["id"], "progress", kind="item/agentMessage/delta", itemId="owned_item", text="实际可见进度"))
        status, runs, _ = self.request(PREFIX + "codex-work/runs?recordId=" + job["recordId"])
        self.assertEqual(status, 200, runs)
        self.assertEqual(runs["runs"][0]["codexWork"]["progress"][0]["text"], "实际可见进度")
        self.assertTrue(self.terminal(job))
        detail = self.detail(job["recordId"])
        self.assertEqual(detail["jobs"][-1]["status"], "completed")
        self.assertTrue(detail["jobs"][-1]["codexWork"]["reportOnly"])
        self.assertFalse(detail["jobs"][-1]["codexWork"]["executionVerified"])
        self.assertEqual(detail["messages"][-1]["text"], "完整真实终态报告（隔离fixture）")
        status, after, _ = self.request(PREFIX + "mobile/dialogue?clientId=" + client)
        self.assertEqual(status, 200, after)
        self.assertEqual(after["session"], state["session"])
        self.assertEqual(after["detail"]["messages"][-1]["id"], detail["messages"][-1]["id"])
        self.assertEqual(len(self.controller.submissions), 1)

    def test_exact_phone_cancel_is_durable_ack_not_completion_then_matching_terminal(self):
        _, state, _, job, _ = self.start_phone()
        payload = request_body(jobId=job["id"], threadId="owned_thread", turnId="owned_turn", sourceSha256=job["codexWork"]["sourceSha256"])
        status, wrong, _ = self.request(PREFIX + "codex-work/cancel", "POST", {**payload, "turnId": "other_turn"})
        self.assertEqual(status, 403, wrong)
        self.assertFalse(self.controller.interrupts)
        status, result, _ = self.request(PREFIX + "codex-work/cancel", "POST", payload)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["job"]["status"], "cancelling")
        self.assertFalse(result["job"]["codexWork"]["cancellationVerified"])
        self.assertFalse(result["job"]["codexWork"]["terminalEventObserved"])
        self.assertEqual(self.request(PREFIX + "codex-work/cancel", "POST", payload)[0], 200)
        self.assertEqual(len(self.controller.interrupts), 1)
        self.assertTrue(self.controller.event(job["id"], "interrupt_intent"))
        self.assertTrue(self.controller.event(job["id"], "cancel_requested", cancellationVerified=False))
        self.assertFalse(self.controller.event(job["id"], "terminal", turnId="wrong_turn", status="interrupted", terminalStatus="interrupted",
            terminalEventObserved=True, report="", error=None, cancellationVerified=True, executionVerified=False, retryAllowed=False))
        self.assertTrue(self.terminal(job, status="interrupted", terminalStatus="interrupted", report="", cancellationVerified=True))
        status, actual, _ = self.request(PREFIX + "codex-work/runs?recordId=" + state["session"]["recordId"])
        self.assertEqual(status, 200, actual)
        run = actual["runs"][0]
        self.assertEqual(run["status"], "interrupted")
        self.assertTrue(run["codexWork"]["cancellationVerified"])
        self.assertTrue(run["codexWork"]["terminalEventObserved"])
        self.assertEqual(len(self.controller.submissions), 1)

    def test_failed_own_work_cannot_enter_generic_retry_or_legacy_queued_worker(self):
        client, state = self.open_phone()
        review, _ = self.review_phone(client, state)
        job, payload = self.submit_phone(review)
        self.assertTrue(self.terminal(job, status="failed", terminalStatus=None, terminalEventObserved=False,
                                      report="", actualModel=None, actualEffort=None, error="codex_work_windows_sandbox_required"))
        status, error, _ = self.request(PREFIX + "retry", "POST", request_body(jobId=job["id"]))
        self.assertEqual(status, 409, error)
        self.assertEqual(error["code"], "verification_required")
        self.assertEqual(self.count_jobs(), 1)
        self.assertEqual(len(self.controller.submissions), 1)
        with self.workflow._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM jobs WHERE status='queued'").fetchone()[0], 0)
        status, duplicate, _ = self.request(PREFIX + "codex-work/submit", "POST", payload)
        self.assertEqual(status, 200, duplicate)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["job"]["status"], "failed")
        self.assertEqual(len(self.controller.submissions), 1)

    def test_desktop_dispatcher_setup_requires_confirmed_grant_phone_settings_forbidden(self):
        self.pair()
        for action in ("codex-work/setup", "codex-work/workspaces"):
            status, error, _ = self.request(PREFIX + action, "POST", {})
            self.assertEqual(status, 403, error)
        payload = {"workspaceId": self.workspace["id"], "workspaceAuthorizationSha256": self.workspace["authorizationSha256"], "confirmed": False}
        with self.assertRaises(WorkflowError) as error:
            workflow_post(self.workflow, "codex-work/setup", payload, desktop=True)
        self.assertEqual((error.exception.status, error.exception.code), (403, "codex_work_setup_not_confirmed"))
        with self.assertRaises(WorkflowError) as error:
            workflow_post(self.workflow, "codex-work/setup", {**payload, "confirmed": True, "workspaceAuthorizationSha256": "0" * 64}, desktop=True)
        self.assertEqual((error.exception.status, error.exception.code), (403, "codex_work_permission_changed"))
        self.assertFalse(self.controller.setups)
        result = workflow_post(self.workflow, "codex-work/setup", {**payload, "confirmed": True}, desktop=True,
                               authorize=lambda: self.desktop_authorizations.append("authorized"))
        self.assertEqual(self.controller.setups, [str(self.allowed)])
        self.assertFalse(result["ready"])
        self.assertFalse(result["terminalEventObserved"])
        config = workflow_get(self.workflow, "codex-work/config", "")
        self.assertEqual(config["setup"]["status"], "configuring")
        self.assertFalse(config["setup"]["ready"])
        self.assertFalse(self.controller.submissions)
        self.assertGreaterEqual(len(self.desktop_authorizations), 4)

    def test_same_session_work_progress_wakes_result_cursor_only_after_durable_commit(self):
        client, state, _, job, _ = self.start_phone()
        session = state["session"]
        stream = self.workflow.mobile_dialogue_subscribe("clientId=" + client + "&sessionId=" + session["id"])
        other = self.workflow.mobile_dialogue_open(request_body(clientId=str(uuid.uuid4())))
        other_client, other_session = other["session"]["clientId"], other["session"]["id"]
        other_stream = self.workflow.mobile_dialogue_subscribe("clientId=" + other_client + "&sessionId=" + other_session)
        try:
            original = stream.next_event(timeout=0)["data"]
            other_initial = other_stream.next_event(timeout=0)["data"]
            self.assertTrue(self.controller.event(job["id"], "progress", kind="item/agentMessage/delta", itemId="item", text="post-commit progress"))
            changed = stream.next_event(timeout=.1)
            self.assertEqual(changed["event"], "dialogue.result")
            self.assertNotEqual(changed["data"]["cursor"], original["cursor"])
            self.assertEqual(changed["data"]["recordId"], session["recordId"])
            self.assertIsNone(other_stream.next_event(timeout=.01))
            self.assertTrue(self.terminal(job))
            completed = stream.next_event(timeout=.1)
            self.assertNotEqual(completed["data"]["cursor"], changed["data"]["cursor"])
            status, detail, _ = self.request(PREFIX + "record?id=" + session["recordId"])
            self.assertEqual(status, 200, detail)
            self.assertEqual(detail["jobs"][-1]["status"], "completed")
            self.assertEqual(detail["messages"][-1]["text"], "完整真实终态报告（隔离fixture）")
            self.assertEqual(self.workflow._mobile_event_read((other_client, other_session))["cursor"], other_initial["cursor"])
        finally:
            stream.close()
            other_stream.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
