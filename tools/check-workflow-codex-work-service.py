#!/usr/bin/env python3
"""Exercise durable Work only with isolated files/SQLite and an inert controller."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_service import WorkflowError, WorkflowService, _json, _now
from workflow_codex_work_service import CATALOG, REVIEW_PREFIX, CodexWorkMixin
from workflow_codex_work import PERMISSION_PROFILE, PROVIDER, preparation_receipt, scope_policy


def body(**items):
    return {"requestId": str(uuid.uuid4()), **items}


class Subscription:
    binding = {"provider": "chatgpt_subscription", "connectionId": "c" * 32,
               "catalogRevision": "d" * 64, "modelSlug": "gpt-6-astra"}

    def __init__(self):
        self.calls = []
        self.connected = True

    def validate_selection(self, model, revision, connection):
        self.calls.append((model, revision, connection))
        if not self.connected or (model, revision, connection) != tuple(self.binding[key] for key in ("modelSlug", "catalogRevision", "connectionId")):
            raise WorkflowError("fixture selection stale", 409, "subscription_selection_stale")
        return dict(self.binding)

    def get_status(self):
        return {"connected": self.connected, "connectionId": self.binding["connectionId"],
                "catalogRevision": self.binding["catalogRevision"], "models": [{"slug": self.binding["modelSlug"], "displayName": "Fixture"}],
                "status": "connected", "busy": False, "error": None}


class Controller:
    def __init__(self, service):
        self.service = service
        self.calls, self.interrupts, self.active = [], [], {}
        self.throw_after_start = False

    def submit(self, run_id, spec, callback):
        # Inspect through another connection: acceptance must already be committed.
        with self.service._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (run_id,)).fetchone()
            if row is None or row["status"] != "starting":
                raise AssertionError("submit happened before durable acceptance")
            meta = json.loads(row["payload"])["codexWork"]
            assert meta["sourceSha256"] == spec["sourceSha256"]
            assert db.execute("SELECT 1 FROM requests WHERE id=?", (row["request_id"],)).fetchone()
        self.calls.append((run_id, copy.deepcopy(spec), callback))
        self.active[run_id] = {"runId": run_id, "threadId": None, "turnId": None,
                               "sourceSha256": spec["sourceSha256"], "active": True}
        if self.throw_after_start:
            raise RuntimeError("unknown acceptance")
        return {"runId": run_id, "accepted": True, "executionVerified": False}

    def snapshot(self, run_id):
        return copy.deepcopy(self.active.get(run_id))

    def interrupt(self, run_id, thread_id, turn_id):
        with self.service._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (run_id,)).fetchone()
            meta = json.loads(row["payload"])["codexWork"]
            assert row["status"] == "cancelling" and meta["cancelRequest"] is not None
        self.interrupts.append((run_id, thread_id, turn_id))
        return {"requestAccepted": True, "cancelVerified": False}

    def close(self):
        pass


class ServiceChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-work-service-fixture-")
        self.root = Path(self.temp.name).resolve()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.allowed = self.workspace / "owned"
        self.allowed.mkdir()
        (self.allowed / "source.txt").write_text("before", encoding="utf-8")
        self.service = WorkflowService(self.root / "private", projects=[
            {"id": "fixture", "name": "Fixture", "root": str(self.workspace), "capabilities": []}])
        self.service.subscription = Subscription()
        self.controller = Controller(self.service)
        self.service.codex_work = self.controller
        self.config_body = body(workspaces=[{"id": "fixture", "name": "Explicit Work", "workspaceRoot": str(self.workspace),
                                            "allowedRoot": str(self.allowed)}])
        self.config = self.service.configure_codex_work(self.config_body)
        self.workspace_binding = self.config["workspaces"][0]
        self.record_id = self.service.create(body(projectId="fixture", title="Same record", text="Original context"))["record"]["id"]

    def tearDown(self):
        self.service.shutdown()
        self.temp.cleanup()

    def revision(self):
        with self.service._db() as db:
            return int(self.service._revision(db))

    def counts(self):
        with self.service._db() as db:
            return {table: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                    for table in ("messages", "jobs", "idea_dispatches", "requests")}

    def review(self, **changes):
        request = body(recordId=self.record_id, expectedRevision=self.revision(), text="Exact current Work request 中文",
                       attachmentIds=[], workspaceId="fixture", workspaceAuthorizationSha256=self.workspace_binding["authorizationSha256"],
                       requestedProfile="high", subscription=dict(Subscription.binding))
        request.update(changes)
        return self.service.codex_work_review(request), request

    def submit(self, review=None, **changes):
        review = review or self.review()[0]
        request = body(reviewId=review["reviewId"], sourceSha256=review["sourceSha256"], confirmed=True)
        request.update(changes)
        return self.service.codex_work_submit(request), request

    def reject(self, operation, code=None):
        with self.assertRaises(WorkflowError) as error:
            operation()
        if code:
            self.assertEqual(error.exception.code, code)
        return error.exception

    def event(self, job, event_type, **changes):
        meta = job["codexWork"]
        event = {"type": event_type, "runId": job["id"], "sourceSha256": meta["sourceSha256"],
                 "threadId": "thread_fixture", "turnId": None, "observedAt": _now()}
        event.update(changes)
        if event_type == "prepared":
            # Synthetic RPC echoes for this isolated inert controller only.
            policy = scope_policy(job["workspace"]["allowedRoot"], self.service.data_dir / "codex-work" / job["id"] / "images")
            event.setdefault("preparationReceipt", preparation_receipt(
                {"config": {"default_permissions": PERMISSION_PROFILE, "permissions": {PERMISSION_PROFILE: policy}}},
                {"thread": {"id": event["threadId"]}, "model": event["actualModel"], "modelProvider": PROVIDER,
                 "reasoningEffort": event["actualEffort"], "cwd": job["workspace"]["allowedRoot"], "approvalPolicy": "never",
                 "activePermissionProfile": {"id": PERMISSION_PROFILE, "extends": ":workspace"}}))
        return event

    def emit(self, event):
        return self.service._codex_work_event(event)

    def job(self, job_id):
        return self.service.codex_work_runs("recordId=" + self.record_id)["runs"][-1]

    def running(self):
        accepted, request = self.submit()
        job = accepted["job"]
        self.assertTrue(self.emit(self.event(job, "prepared", requestedProfile="high", actualModel="gpt-6-astra", actualEffort="high", sandboxVerified=True)))
        intent = self.event(job, "send_intent", model="gpt-6-astra", effort="high")
        self.assertTrue(self.emit(intent))
        self.assertFalse(self.emit(intent), "durable intent cannot authorize a second turn/start")
        self.assertTrue(self.emit(self.event(job, "turn_started", turnId="turn_fixture", actualModel="gpt-6-astra", actualEffort="high")))
        self.controller.active[job["id"]].update(threadId="thread_fixture", turnId="turn_fixture")
        return self.job(job["id"]), request

    def terminal(self, job, **changes):
        return self.event(job, "terminal", turnId="turn_fixture", status="completed", terminalStatus="completed",
                          terminalEventObserved=True, report="Actual complete report 中文", actualModel="gpt-6-astra",
                          actualEffort="high", error=None, cancellationVerified=False, executionVerified=False, retryAllowed=False, **changes)

    def test_prepare_receipt_commits_selected_rpc_echo_and_survives_terminal_and_restart(self):
        accepted, _ = self.submit()
        job = accepted["job"]
        event = self.event(job, "prepared", requestedProfile="high", actualModel="gpt-6-astra", actualEffort="high", sandboxVerified=True)
        self.assertTrue(self.emit(event))
        with self.service._db() as independent:
            payload = json.loads(independent.execute("SELECT payload FROM jobs WHERE id=?", (job["id"],)).fetchone()[0])
            receipt = payload["codexWork"]["preparationReceipt"]
            digest = payload["codexWork"]["preparationReceiptSha256"]
        self.assertEqual(receipt, event)
        self.assertEqual(digest, hashlib.sha256(_json(event).encode()).hexdigest())
        public = self.job(job["id"])["codexWork"]
        self.assertTrue(public["configurationEchoVerified"])
        self.assertTrue(public["sandboxVerified"])
        self.assertFalse(public["outsideScopeReadDeniedVerified"])
        self.assertEqual(public["scopeEvidenceType"], "configuration_and_thread_profile_echo")
        self.assertEqual(public["actualActivePermissionProfile"], {"id": PERMISSION_PROFILE, "extends": ":workspace"})
        self.assertEqual(public["preparationReceiptSha256"], digest)
        self.assertEqual(public["preparationReceipt"]["modelProvider"], PROVIDER)
        self.assertNotIn(str(self.service.data_dir), _json(public))
        event["preparationReceipt"]["threadStart"]["model"] = "caller-mutated-after-commit"
        self.assertEqual(self.job(job["id"])["codexWork"], public)
        self.assertTrue(self.emit(self.event(job, "send_intent", model="gpt-6-astra", effort="high")))
        self.assertTrue(self.emit(self.event(job, "turn_started", turnId="turn_fixture", actualModel="gpt-6-astra", actualEffort="high")))
        self.assertTrue(self.emit(self.terminal(job)))
        recovered = WorkflowService(self.service.data_dir)
        try:
            result = recovered.codex_work_runs("recordId=" + self.record_id)["runs"][-1]
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["codexWork"]["preparationReceipt"], public["preparationReceipt"])
            self.assertEqual(result["codexWork"]["preparationReceiptSha256"], digest)
            self.assertFalse(result["codexWork"]["outsideScopeReadDeniedVerified"])
        finally:
            recovered.shutdown()
        self.assertEqual(len(self.controller.calls), 1)

    def test_prepare_missing_or_wrong_actual_scope_and_thread_cannot_authorize_send(self):
        accepted, _ = self.submit()
        job = accepted["job"]
        original = self.event(job, "prepared", requestedProfile="high", actualModel="gpt-6-astra", actualEffort="high", sandboxVerified=True)
        candidates = []
        missing = copy.deepcopy(original)
        missing.pop("preparationReceipt")
        candidates.append(missing)
        mutations = [
            (["schemaVersion"], True), (["evidenceType"], "os_scope_enforced"),
            (["configuration", "defaultPermissions"], ":danger-full-access"),
            (["configuration", "permissionProfile", "filesystem", ":root"], "read"),
            (["configuration", "permissionProfile", "filesystem", str(self.root)], "write"),
            (["configuration", "permissionProfile", "filesystem", str(self.service.data_dir / "codex-work" / job["id"] / "images")], "write"),
            (["configuration", "permissionProfile", "filesystem", "glob_scan_max_depth"], 3.0),
            (["configuration", "permissionProfile", "network", "enabled"], True),
            (["configuration", "permissionProfile", "network", "extra"], None),
            (["threadStart", "activePermissionProfile", "id"], "foreign-profile"),
            (["threadStart", "threadId"], "other-thread"), (["threadStart", "model"], "other-model"),
            (["threadStart", "modelProvider"], "other-provider"), (["threadStart", "reasoningEffort"], "low"),
            (["threadStart", "cwd"], str(self.workspace)), (["threadStart", "approvalPolicy"], "on-request")]
        for keys, value in mutations:
            event = copy.deepcopy(original)
            target = event["preparationReceipt"]
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = value
            candidates.append(event)
        for changes in ({"sourceSha256": "f" * 64}, {"sandboxVerified": 1}, {"turnId": "premature-turn"}):
            candidates.append({**copy.deepcopy(original), **changes})
        before = self.counts()
        for index, event in enumerate(candidates):
            with self.subTest(index=index):
                self.assertFalse(self.emit(event))
                self.assertFalse(self.emit(self.event(job, "send_intent", model="gpt-6-astra", effort="high")))
                state = self.job(job["id"])
                self.assertEqual(state["status"], "starting")
                self.assertFalse(state["codexWork"]["configurationEchoVerified"])
                self.assertIsNone(state["codexWork"]["preparationReceipt"])
                self.assertFalse(state["codexWork"]["sendIntentRecorded"])
                self.assertEqual(self.counts(), before)
        self.assertTrue(self.emit(original))

    def test_prepare_rechecks_current_binding_and_workspace_before_saving_echo(self):
        accepted, _ = self.submit()
        job = accepted["job"]
        event = self.event(job, "prepared", requestedProfile="high", actualModel="gpt-6-astra", actualEffort="high", sandboxVerified=True)
        self.service.subscription.connected = False
        self.assertFalse(self.emit(event))
        self.service.subscription.connected = True
        with self.service._db() as db:
            catalog = self.service._setting(db, CATALOG)
            changed = copy.deepcopy(catalog)
            changed["workspaces"][0]["authorizationSha256"] = "e" * 64
            self.service._set_setting(db, CATALOG, changed)
        self.assertFalse(self.emit(event))
        with self.service._db() as db:
            self.service._set_setting(db, CATALOG, catalog)
        self.assertTrue(self.emit(event))

    def test_historical_job_without_receipt_never_gains_echo_proof_or_new_send(self):
        job, _ = self.running()
        with self.service._db() as db:
            payload = json.loads(db.execute("SELECT payload FROM jobs WHERE id=?", (job["id"],)).fetchone()[0])
            payload["codexWork"].pop("preparationReceipt")
            payload["codexWork"].pop("preparationReceiptSha256")
            db.execute("UPDATE jobs SET payload=? WHERE id=?", (_json(payload), job["id"]))
        before = self.job(job["id"])["codexWork"]
        self.assertFalse(before["configurationEchoVerified"])
        self.assertFalse(before["sandboxVerified"])
        self.assertIsNone(before["actualActivePermissionProfile"])
        self.assertIsNone(before["preparationReceiptSha256"])
        self.assertFalse(self.emit(self.event(job, "prepared", requestedProfile="high", actualModel="gpt-6-astra", actualEffort="high", sandboxVerified=True)))
        self.assertFalse(self.emit(self.event(job, "send_intent", model="gpt-6-astra", effort="high")))
        self.assertEqual(self.job(job["id"])["codexWork"], before)
        with self.service._db() as db:
            kept = json.loads(db.execute("SELECT payload FROM jobs WHERE id=?", (job["id"],)).fetchone()[0])["codexWork"]
        self.assertNotIn("preparationReceipt", kept)

    def test_config_exact_explicit_authority_persists_and_reads_only_cache(self):
        self.assertRegex(self.workspace_binding["authorizationSha256"], r"^[a-f0-9]{64}$")
        before = len(self.service.subscription.calls)
        self.assertEqual(self.service.configure_codex_work(self.config_body), self.config)
        self.assertEqual(self.service.codex_work_config(), self.config)
        self.assertEqual(len(self.service.subscription.calls), before)
        with self.service._db() as db:
            self.assertIsNone(self.service._setting(db, "app-work_catalog"))
            self.assertEqual(self.service._setting(db, CATALOG)["workspaces"], self.config["workspaces"])

    def test_configuration_rejects_extra_fields_outside_missing_relative_and_private_roots(self):
        candidates = [str(self.root / "missing"), "relative", str(self.root), str(self.service.data_dir)]
        for path in candidates:
            entry = {**self.config_body["workspaces"][0], "allowedRoot": path}
            self.reject(lambda: self.service.configure_codex_work(body(workspaces=[entry])))
        self.reject(lambda: self.service.configure_codex_work({**body(workspaces=[]), "enabled": True}))
        self.reject(lambda: self.service.configure_codex_work(body(workspaces=[self.config_body["workspaces"][0]] * 2)))

    def test_configuration_rejects_symlink_ancestor_even_when_target_is_inside(self):
        alias = self.workspace / "alias"
        try:
            alias.symlink_to(self.allowed, target_is_directory=True)
        except OSError:
            # Exercise the actual reparse attribute check without OS link privileges.
            original = Path.stat
            class Stat:
                st_file_attributes = 0x400
                def __init__(self, actual):
                    self.actual = actual
                def __getattr__(self, name):
                    return getattr(self.actual, name)
            def redirect(path, *args, **kwargs):
                if path == self.allowed and kwargs.get("follow_symlinks") is False:
                    return Stat(original(path, *args, **kwargs))
                return original(path, *args, **kwargs)
            with patch.object(Path, "stat", redirect):
                self.reject(lambda: self.service.configure_codex_work(body(workspaces=self.config_body["workspaces"])), "codex_work_workspace_redirected")
        else:
            entry = {**self.config_body["workspaces"][0], "allowedRoot": str(alias)}
            self.reject(lambda: self.service.configure_codex_work(body(workspaces=[entry])), "codex_work_workspace_redirected")
            alias.unlink()

    def test_review_freezes_original_context_images_scope_without_enqueuing(self):
        before = self.counts()
        review, request = self.review()
        self.assertEqual(review["source"]["text"], request["text"])
        self.assertEqual(review["source"]["context"]["history"][0]["text"], "Original context")
        self.assertEqual(review["source"]["workspace"], self.workspace_binding)
        self.assertEqual(review["beforeFileCount"], 1)
        after = self.counts()
        for key in ("messages", "jobs", "idea_dispatches"):
            self.assertEqual(before[key], after[key])
        self.assertFalse(self.controller.calls)
        self.assertTrue(self.service.codex_work_review(request)["duplicate"])

    def test_review_rejects_stale_revision_authorization_pro_and_six_field_binding(self):
        self.reject(lambda: self.review(expectedRevision=self.revision() - 1), "revision_conflict")
        self.reject(lambda: self.review(workspaceAuthorizationSha256="0" * 64), "codex_work_permission_changed")
        self.reject(lambda: self.review(requestedProfile="pro"), "codex_work_pro_unsupported")
        self.reject(lambda: self.review(subscription={**Subscription.binding, "requestedProfile": "high", "reasoning": {"mode": "standard", "effort": "high"}}), "codex_work_request_invalid")
        self.assertFalse(self.controller.calls)
        self.assertEqual(self.counts()["jobs"], 0)

    def test_submit_durable_one_call_same_record_no_dispatch_and_frozen_nonce(self):
        review, _ = self.review()
        accepted, request = self.submit(review)
        job = accepted["job"]
        self.assertEqual(job["status"], "starting")
        self.assertEqual(job["kind"], "work")
        self.assertEqual(job["executionEngine"], "codex_agent")
        self.assertEqual(job["recordId"], self.record_id)
        self.assertEqual(len(self.controller.calls), 1)
        self.assertTrue(self.service.codex_work_submit(request)["duplicate"])
        self.assertEqual(len(self.controller.calls), 1)
        self.assertEqual(self.counts()["idea_dispatches"], 0)
        self.reject(lambda: self.service.codex_work_submit({**request, "sourceSha256": "1" * 64}))
        self.reject(lambda: self.service.codex_work_submit({**request, "confirmed": False}), "codex_work_confirmation_required")

    def test_consumed_review_cannot_send_again_even_after_real_completed(self):
        job, request = self.running()
        self.assertTrue(self.emit(self.terminal(job)))
        duplicate = {**request, "requestId": str(uuid.uuid4())}
        self.reject(lambda: self.service.codex_work_submit(duplicate), "codex_work_review_already_submitted")
        self.assertEqual(len(self.controller.calls), 1)

    def test_submit_changed_record_or_files_cannot_call_controller(self):
        review, _ = self.review()
        self.service.add_message(body(recordId=self.record_id, text="Changed context"))
        self.reject(lambda: self.submit(review), "codex_work_source_changed")
        review, _ = self.review()
        (self.allowed / "source.txt").write_text("changed after review", encoding="utf-8")
        self.reject(lambda: self.submit(review), "codex_work_files_changed")
        self.assertFalse(self.controller.calls)

    def test_overlap_is_rejected_distinct_allowed_roots_can_start(self):
        first, _ = self.submit()
        second_root = self.workspace / "second"
        second_root.mkdir()
        # Settings fixture config prepared before first acceptance is immutable in product.
        with self.service._db() as db:
            catalog = self.service._setting(db, CATALOG)
            sibling = {"id": "sibling", "name": "Sibling", "workspaceRoot": str(self.workspace), "allowedRoot": str(second_root)}
            sibling["authorizationSha256"] = hashlib.sha256(_json(sibling).encode()).hexdigest()
            catalog["workspaces"].append(sibling)
            self.service._set_setting(db, CATALOG, catalog)
        self.reject(lambda: self.submit(), "codex_work_workspace_busy")
        review, _ = self.review(workspaceId="sibling", workspaceAuthorizationSha256=sibling["authorizationSha256"])
        second, _ = self.submit(review)
        self.assertNotEqual(first["job"]["id"], second["job"]["id"])
        self.assertEqual(len(self.controller.calls), 2)

    def test_active_config_change_rejected_and_inventory_never_reads_credentials(self):
        (self.allowed / ".env").write_text("unread credential fixture")
        (self.allowed / "auth.json").write_text("unread credential fixture")
        private = self.allowed / ".codex"
        private.mkdir()
        (private / "credentials.json").write_text("unread credential fixture")
        original = self.service._file_digest
        def digest(path):
            self.assertNotIn(path.name, {".env", "auth.json", "credentials.json"})
            return original(path)
        with patch.object(self.service, "_file_digest", digest):
            review, _ = self.review()
        self.assertEqual(review["beforeFileCount"], 1)
        self.submit(review)
        self.reject(lambda: self.service.configure_codex_work(body(workspaces=[])), "codex_work_workspace_busy")

    def test_unknown_submission_is_retained_and_never_restarted_by_duplicate(self):
        self.controller.throw_after_start = True
        accepted, request = self.submit()
        self.assertEqual(accepted["job"]["status"], "needs_review")
        self.assertTrue(self.service.codex_work_submit(request)["duplicate"])
        self.assertEqual(len(self.controller.calls), 1)
        self.assertTrue(self.service.codex_work_active())

    def test_authorization_failure_rolls_back_and_never_calls_controller(self):
        review, _ = self.review()
        request = body(reviewId=review["reviewId"], sourceSha256=review["sourceSha256"], confirmed=True)
        before = self.counts()
        calls = []
        def authorize():
            calls.append(True)
            if len(calls) == 2:
                raise WorkflowError("expired fixture", 401)
        self.reject(lambda: self.service.codex_work_submit(request, authorize=authorize))
        self.assertEqual(self.counts(), before)
        self.assertFalse(self.controller.calls)

    def test_send_intent_rejects_changed_model_image_or_files(self):
        accepted, _ = self.submit()
        job = accepted["job"]
        self.assertTrue(self.emit(self.event(job, "prepared", requestedProfile="high", actualModel="gpt-6-astra", actualEffort="high", sandboxVerified=True)))
        self.service.subscription.connected = False
        self.assertFalse(self.emit(self.event(job, "send_intent", model="gpt-6-astra", effort="high")))
        self.service.subscription.connected = True
        (self.allowed / "source.txt").write_text("changed")
        self.assertFalse(self.emit(self.event(job, "send_intent", model="gpt-6-astra", effort="high")))
        self.assertFalse(self.job(job["id"])["codexWork"]["sendIntentRecorded"])

    def test_progress_foreign_source_thread_turn_cannot_touch_original(self):
        job, _ = self.running()
        event = self.event(job, "progress", turnId="turn_fixture", kind="item/agentMessage/delta", itemId="agent_item", text="真实进度")
        before = self.job(job["id"])
        for changes in ({"sourceSha256": "0" * 64}, {"threadId": "foreign_thread"}, {"turnId": "foreign_turn"}, {"unexpected": True}):
            self.assertFalse(self.emit({**event, **changes}))
            self.assertEqual(self.job(job["id"]), before)
        self.assertTrue(self.emit(event))
        self.assertEqual(self.job(job["id"])["codexWork"]["progress"][0]["text"], "真实进度")

    def test_cancel_persists_before_interrupt_ack_is_not_verified(self):
        job, _ = self.running()
        request = body(jobId=job["id"], threadId="thread_fixture", turnId="turn_fixture", sourceSha256=job["codexWork"]["sourceSha256"])
        cancelled = self.service.codex_work_cancel(request)
        self.assertEqual(cancelled["job"]["status"], "cancelling")
        self.assertFalse(cancelled["job"]["codexWork"]["cancellationVerified"])
        self.assertTrue(self.service.codex_work_cancel(request)["duplicate"])
        self.assertEqual(len(self.controller.interrupts), 1)
        intent = self.event(job, "interrupt_intent", turnId="turn_fixture")
        self.assertTrue(self.emit(intent))
        self.assertFalse(self.emit(intent))
        self.assertTrue(self.emit(self.event(job, "cancel_requested", turnId="turn_fixture", cancellationVerified=False)))
        terminal = self.terminal(job)
        terminal.update(status="interrupted", terminalStatus="interrupted", cancellationVerified=True)
        self.assertTrue(self.emit(terminal))
        actual = self.job(job["id"])
        self.assertEqual(actual["status"], "interrupted")
        self.assertTrue(actual["codexWork"]["cancellationVerified"])

    def test_cancel_requires_exact_owned_live_snapshot_and_wrong_turn_is_rejected(self):
        job, _ = self.running()
        request = body(jobId=job["id"], threadId="thread_fixture", turnId="foreign", sourceSha256=job["codexWork"]["sourceSha256"])
        self.reject(lambda: self.service.codex_work_cancel(request), "codex_work_cancel_mismatch")
        request["turnId"] = "turn_fixture"
        self.controller.active[job["id"]]["active"] = False
        self.reject(lambda: self.service.codex_work_cancel(request), "codex_work_cancel_unavailable")
        self.assertFalse(self.controller.interrupts)

    def test_phone_views_and_cancels_current_desktop_agent_without_changing_draft(self):
        client = str(uuid.uuid4())
        initial = self.service.mobile_dialogue_open(body(clientId=client))
        session = initial["session"]
        self.record_id = session["recordId"]
        job, _ = self.running()
        draft = self.service.mobile_dialogue_draft(body(clientId=client, sessionId=session["id"],
            expectedRevision=session["revision"], text="正在输入的新草稿，不是取消底稿", attachmentIds=[], requestedProfile="high"))
        scope = {"recordId": self.record_id, "clientId": client, "sessionId": session["id"]}
        runs = self.service.codex_work_runs(urlencode(scope), prefix="/api/phone/workflow")
        self.assertEqual(runs["scope"], scope)
        self.assertEqual([row["id"] for row in runs["runs"]], [job["id"]])
        self.assertIsNone(runs["runs"][0]["mobileDialogue"])
        request = body(jobId=job["id"], threadId="thread_fixture", turnId="turn_fixture",
                       sourceSha256=job["codexWork"]["sourceSha256"], clientId=client, sessionId=session["id"])
        wrong = {**request, "turnId": "other_turn"}
        self.reject(lambda: self.service.codex_work_cancel(wrong, prefix="/api/phone/workflow"), "codex_work_cancel_mismatch")
        result = self.service.codex_work_cancel(request, prefix="/api/phone/workflow")
        self.assertEqual(result["scope"], scope)
        self.assertIsNone(result["job"]["mobileDialogue"])
        self.assertFalse(result["job"]["codexWork"]["cancellationVerified"])
        self.assertTrue(self.service.codex_work_cancel(request, prefix="/api/phone/workflow")["duplicate"])
        self.assertEqual(len(self.controller.interrupts), 1)
        self.assertTrue(self.emit(self.event(job, "interrupt_intent", turnId="turn_fixture")))
        terminal = self.terminal(job)
        terminal.update(status="interrupted", terminalStatus="interrupted", cancellationVerified=True)
        self.assertTrue(self.emit(terminal))
        self.assertTrue(self.job(job["id"])["codexWork"]["cancellationVerified"])
        self.assertEqual(self.service.mobile_dialogue_get("clientId=" + client)["session"], draft["session"])
        self.assertEqual(len(self.controller.calls), 1)

    def test_phone_control_rejects_foreign_record_client_and_cleared_session(self):
        client = str(uuid.uuid4())
        initial = self.service.mobile_dialogue_open(body(clientId=client))
        session = initial["session"]
        self.record_id = session["recordId"]
        job, _ = self.running()
        request = body(jobId=job["id"], threadId="thread_fixture", turnId="turn_fixture",
                       sourceSha256=job["codexWork"]["sourceSha256"], clientId=client, sessionId=session["id"])
        other_client = str(uuid.uuid4())
        other = self.service.mobile_dialogue_open(body(clientId=other_client))["session"]
        for values in ({"clientId": other_client, "sessionId": session["id"]},
                       {"clientId": client, "sessionId": other["id"]},
                       {"clientId": other_client, "sessionId": other["id"]}):
            self.reject(lambda values=values: self.service.codex_work_cancel({**request, **values}, prefix="/api/phone/workflow"))
            self.reject(lambda values=values: self.service.codex_work_runs(urlencode({"recordId": self.record_id, **values}), prefix="/api/phone/workflow"))
        self.reject(lambda: self.service.codex_work_cancel({key: value for key, value in request.items() if key not in {"clientId", "sessionId"}}, prefix="/api/phone/workflow"), "codex_work_request_invalid")
        self.service.mobile_dialogue_clear(body(clientId=client, sessionId=session["id"], expectedRevision=session["revision"]))
        self.reject(lambda: self.service.codex_work_cancel(request, prefix="/api/phone/workflow"), "dialogue_changed")
        self.reject(lambda: self.service.codex_work_runs(urlencode({"recordId": self.record_id, "clientId": client, "sessionId": session["id"]}), prefix="/api/phone/workflow"), "dialogue_changed")
        self.assertFalse(self.controller.interrupts)
        self.assertEqual(self.job(job["id"])["status"], "running")

    def test_phone_cannot_cancel_a_desktop_agent_after_original_task_changes(self):
        client = str(uuid.uuid4())
        idea = self.service.incubator_create(body(title="原工作来源", body="明确旧底稿"))["idea"]
        initial = self.service.mobile_dialogue_open(body(clientId=client, ideaId=idea["id"], expectedIdeaRevision=idea["revision"]))
        session = initial["session"]
        self.record_id = session["recordId"]
        job, _ = self.running()
        self.service.incubator_update(body(id=idea["id"], expectedRevision=idea["revision"], body="另一个已保存版本"))
        request = body(jobId=job["id"], threadId="thread_fixture", turnId="turn_fixture",
                       sourceSha256=job["codexWork"]["sourceSha256"], clientId=client, sessionId=session["id"])
        self.reject(lambda: self.service.codex_work_cancel(request, prefix="/api/phone/workflow"))
        self.assertFalse(self.controller.interrupts)

    def test_desktop_local_authorization_can_cancel_phone_created_agent(self):
        client = str(uuid.uuid4())
        initial = self.service.mobile_dialogue_open(body(clientId=client))
        session = initial["session"]
        self.record_id = session["recordId"]
        request = body(recordId=self.record_id, clientId=client, sessionId=session["id"], expectedRevision=session["revision"],
            text="手机创建的确切Agent", attachmentIds=[], workspaceId="fixture",
            workspaceAuthorizationSha256=self.workspace_binding["authorizationSha256"], requestedProfile="high", subscription=dict(Subscription.binding))
        review = self.service.codex_work_review(request, prefix="/api/phone/workflow")
        submitted = self.service.codex_work_submit(body(reviewId=review["reviewId"], sourceSha256=review["sourceSha256"], confirmed=True), prefix="/api/phone/workflow")
        job = submitted["job"]
        self.assertTrue(self.emit(self.event(job, "prepared", requestedProfile="high", actualModel="gpt-6-astra", actualEffort="high", sandboxVerified=True)))
        self.assertTrue(self.emit(self.event(job, "send_intent", model="gpt-6-astra", effort="high")))
        self.assertTrue(self.emit(self.event(job, "turn_started", turnId="turn_fixture", actualModel="gpt-6-astra", actualEffort="high")))
        self.controller.active[job["id"]].update(threadId="thread_fixture", turnId="turn_fixture")
        cancel = body(jobId=job["id"], threadId="thread_fixture", turnId="turn_fixture", sourceSha256=job["codexWork"]["sourceSha256"])
        before = self.counts()
        self.reject(lambda: self.service.codex_work_cancel(cancel, authorize=lambda: (_ for _ in ()).throw(WorkflowError("local authorization revoked", 403))))
        self.assertEqual(self.counts(), before)
        self.assertFalse(self.controller.interrupts)
        authorizations = []
        result = self.service.codex_work_cancel(cancel, authorize=lambda: authorizations.append(True))
        self.assertEqual(result["job"]["mobileDialogue"]["id"], session["id"])
        self.assertEqual(result["job"]["status"], "cancelling")
        self.assertGreaterEqual(len(authorizations), 2)
        self.assertEqual(self.controller.interrupts, [(job["id"], "thread_fixture", "turn_fixture")])

    def test_completion_with_no_changes_is_report_only_same_record(self):
        job, _ = self.running()
        event = self.terminal(job)
        self.assertTrue(self.emit(event))
        done = self.job(job["id"])
        self.assertEqual(done["status"], "completed")
        self.assertTrue(done["codexWork"]["reportOnly"])
        self.assertFalse(done["codexWork"]["executionVerified"])
        self.assertTrue(self.emit(event))
        messages = self.service.detail(self.record_id)["messages"]
        self.assertEqual(len([row for row in messages if row["role"] == "assistant"]), 1)
        self.assertEqual(messages[-1]["text"], event["report"])
        self.assertFalse(self.service.codex_work_active())

    def test_complete_inventory_proves_added_modified_removed_bytes(self):
        job, _ = self.running()
        (self.allowed / "source.txt").write_text("actual changed")
        (self.allowed / "new.txt").write_text("actual added")
        self.assertTrue(self.emit(self.terminal(job)))
        done = self.job(job["id"])
        self.assertTrue(done["codexWork"]["executionVerified"])
        self.assertFalse(done["codexWork"]["reportOnly"])
        self.assertEqual({row["path"]: row["change"] for row in done["result"]["changedFiles"]}, {"source.txt": "modified", "new.txt": "added"})
        self.assertEqual(done["result"]["changedFiles"][0]["afterSha256"], hashlib.sha256(b"actual added").hexdigest())

    def test_missing_terminal_empty_report_or_wrong_actual_profile_never_claims_success(self):
        job, _ = self.running()
        for changes in ({"terminalEventObserved": False, "terminalStatus": None}, {"report": ""}, {"actualEffort": "low"}, {"actualModel": "foreign_model"}):
            event = self.terminal(job)
            event.update(changes)
            self.assertTrue(self.emit(event))
            done = self.job(job["id"])
            self.assertEqual(done["status"], "needs_review")
            self.assertFalse(done["codexWork"]["executionVerified"])
            self.assertIsNone(done["resultMessageId"])
        self.assertFalse(any(row["role"] == "assistant" for row in self.service.detail(self.record_id)["messages"]))

    def test_unknown_then_actual_matching_terminal_can_reconcile_but_cannot_resend(self):
        job, _ = self.running()
        unknown = self.terminal(job)
        unknown.update(status="unknown", terminalStatus=None, terminalEventObserved=False, error="codex_work_turn_timeout")
        self.assertTrue(self.emit(unknown))
        self.assertEqual(self.job(job["id"])["status"], "needs_review")
        self.assertFalse(self.emit(self.event(job, "send_intent", model="gpt-6-astra", effort="high")))
        self.assertTrue(self.emit(self.terminal(job)))
        self.assertEqual(self.job(job["id"])["status"], "completed")
        self.assertEqual(len(self.controller.calls), 1)

    def test_observed_terminal_needs_review_is_idle_only_with_exact_inactive_snapshot(self):
        job, _ = self.running()
        terminal = self.terminal(job)
        terminal.update(status="unknown", report="", error="codex_work_completed_report_unverified")
        self.assertTrue(self.emit(terminal))
        self.assertTrue(self.service.codex_work_active())
        self.controller.active[job["id"]]["active"] = False
        self.assertFalse(self.service.codex_work_active())
        self.controller.active[job["id"]]["sourceSha256"] = "0" * 64
        self.assertTrue(self.service.codex_work_active())
        self.controller.active.pop(job["id"])
        self.assertTrue(self.service.codex_work_active())
        with patch.object(self.controller, "snapshot", side_effect=WorkflowError("not owned after restart", 404, "codex_work_run_not_owned")):
            self.assertTrue(self.service.codex_work_active())

    def test_pre_send_failure_is_terminal_but_has_no_send_or_fake_output(self):
        accepted, _ = self.submit()
        event = self.terminal(accepted["job"])
        event.update(threadId=None, turnId=None, status="failed", terminalStatus=None, terminalEventObserved=False,
                     report="", error="codex_work_read_scope_unverified")
        self.assertTrue(self.emit(event))
        done = self.job(accepted["job"]["id"])
        self.assertEqual(done["status"], "failed")
        self.assertFalse(done["codexWork"]["sendIntentRecorded"])
        self.assertIsNone(done["resultMessageId"])

    def test_startup_recovery_does_not_call_controller_or_adopt_other_jobs(self):
        accepted, request = self.submit()
        prior = self.controller.calls[:]
        recovered = WorkflowService(self.service.data_dir)
        try:
            runs = recovered.codex_work_runs("recordId=" + self.record_id)["runs"]
            self.assertEqual(runs[-1]["status"], "needs_review")
            self.assertFalse(runs[-1]["codexWork"]["cancellationVerified"])
            self.assertIsNone(recovered.codex_work)
            recovered.codex_work = self.controller
            self.assertTrue(recovered.codex_work_submit(request)["duplicate"])
            self.assertEqual(self.controller.calls, prior)
        finally:
            recovered.codex_work = None
            recovered.shutdown()

    def test_bounded_inventory_cannot_save_truncated_success_and_changed_files_removal(self):
        job, _ = self.running()
        (self.allowed / "source.txt").unlink()
        self.assertTrue(self.emit(self.terminal(job)))
        self.assertEqual(self.job(job["id"])["result"]["changedFiles"][0]["change"], "removed")
        new_job, _ = self.running()
        with patch.object(self.service, "_codex_work_inventory", side_effect=WorkflowError("too large", 409, "codex_work_inventory_too_large")):
            self.assertTrue(self.emit(self.terminal(new_job)))
        self.assertEqual(self.job(new_job["id"])["status"], "needs_review")
        self.assertIsNone(self.job(new_job["id"])["resultMessageId"])

    def test_review_image_bytes_are_full_and_changed_original_rejected(self):
        identifier, data = uuid.uuid4().hex, b"fixture PNG bytes with unchanged SHA"
        filename = identifier + ".png"
        path = self.service.attachments_dir / filename
        path.write_bytes(data)
        with self.service._db() as db:
            db.execute("INSERT INTO attachments VALUES (?,?,?,?,?,?,?,?)", (identifier, self.record_id, "原图.png", filename,
                        "image/png", len(data), 0, None))
        review, _ = self.review(attachmentIds=[identifier])
        result, _ = self.submit(review)
        spec = self.controller.calls[-1][1]
        self.assertEqual(spec["images"][0]["bytes"], data)
        self.assertEqual(spec["images"][0]["sha256"], hashlib.sha256(data).hexdigest())
        self.assertNotIn("bytes", _json(result["job"]))
        path.write_bytes(b"mutated after acceptance")
        prepared = self.event(result["job"], "prepared", requestedProfile="high", actualModel="gpt-6-astra", actualEffort="high", sandboxVerified=True)
        self.assertFalse(self.emit(prepared))
        self.assertIsNone(self.job(result["job"]["id"])["codexWork"]["preparationReceipt"])
        path.write_bytes(data)
        self.assertTrue(self.emit(prepared))
        path.write_bytes(b"mutated after preparation")
        self.assertFalse(self.emit(self.event(result["job"], "send_intent", model="gpt-6-astra", effort="high")))

    def test_mobile_review_scope_revision_and_draft_remain_same_then_output_same_origin(self):
        client = str(uuid.uuid4())
        initial = self.service.mobile_dialogue_open(body(clientId=client))
        session = initial["session"]
        request = body(recordId=session["recordId"], clientId=client, sessionId=session["id"], expectedRevision=session["revision"],
                       text="手机明确 Work", attachmentIds=[], workspaceId="fixture",
                       workspaceAuthorizationSha256=self.workspace_binding["authorizationSha256"], requestedProfile="high", subscription=dict(Subscription.binding))
        review = self.service.codex_work_review(request, prefix="/api/phone/workflow")
        self.assertEqual(self.service.mobile_dialogue_get("clientId=" + client)["session"], initial["session"])
        self.reject(lambda: self.service.codex_work_submit(body(reviewId=review["reviewId"], sourceSha256=review["sourceSha256"], confirmed=True)), "codex_work_source_invalid")
        submitted = self.service.codex_work_submit(body(reviewId=review["reviewId"], sourceSha256=review["sourceSha256"], confirmed=True), prefix="/api/phone/workflow")
        self.assertEqual(submitted["job"]["mobileDialogue"]["id"], session["id"])
        self.assertEqual(submitted["job"]["mobileDialogue"]["clientId"], client)
        self.assertEqual(submitted["job"]["recordId"], session["recordId"])
        self.assertEqual(self.service.mobile_dialogue_get("clientId=" + client)["session"], initial["session"])

    def test_stale_mobile_session_or_different_record_cannot_review(self):
        client = str(uuid.uuid4())
        initial = self.service.mobile_dialogue_open(body(clientId=client))
        session = initial["session"]
        request = body(recordId=self.record_id, clientId=client, sessionId=session["id"], expectedRevision=session["revision"],
                       text="work", attachmentIds=[], workspaceId="fixture", workspaceAuthorizationSha256=self.workspace_binding["authorizationSha256"],
                       requestedProfile="high", subscription=dict(Subscription.binding))
        self.reject(lambda: self.service.codex_work_review(request, prefix="/api/phone/workflow"), "codex_work_source_invalid")
        request["recordId"] = session["recordId"]
        self.service.mobile_dialogue_clear(body(clientId=client, sessionId=session["id"], expectedRevision=session["revision"]))
        self.reject(lambda: self.service.codex_work_review(request, prefix="/api/phone/workflow"), "dialogue_changed")

    def test_source_sha_internal_mutation_cannot_accept_callback_or_reveal_unsafe_projection(self):
        accepted, _ = self.submit()
        job = accepted["job"]
        with self.service._db() as db:
            row = db.execute("SELECT payload FROM jobs WHERE id=?", (job["id"],)).fetchone()
            payload = json.loads(row[0])
            payload["codexWork"]["source"]["text"] = "changed frozen payload"
            db.execute("UPDATE jobs SET payload=? WHERE id=?", (_json(payload), job["id"]))
        self.assertFalse(self.emit(self.event(job, "prepared", requestedProfile="high", actualModel="gpt-6-astra", actualEffort="high", sandboxVerified=True)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
