"""Isolated durable delivery checks: no account, credentials, or network."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from transfer_store import IncomingFile
from workflow_service import WorkflowError, WorkflowService
from workflow_http import workflow_get, workflow_post
from workflow_subscription_stream import profile_reasoning


def request(**value):
    return {"requestId": str(uuid.uuid4()), **value}


class Subscription:
    binding = {"provider": "chatgpt_subscription", "connectionId": "fixture-connection",
        "catalogRevision": "fixture-catalog", "modelSlug": "fixture-model"}

    def validate_selection(self, model, catalog, connection, requestedProfile=None):
        if (model, catalog, connection) != (self.binding["modelSlug"], self.binding["catalogRevision"], self.binding["connectionId"]):
            raise WorkflowError("选择已改变。", 409, "subscription_selection_changed")
        binding = dict(self.binding)
        if requestedProfile is not None:
            binding.update(requestedProfile=requestedProfile, reasoning=profile_reasoning(requestedProfile, model))
        return binding

    def get_status(self):
        return {"connected": True, **self.binding, "models": [{"slug": "fixture-model", "displayName": "Fixture"}]}


class DeliveryChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="subscription-delivery-")
        self.root = Path(self.temp.name)
        self.service = WorkflowService(self.root / "private")
        self.service.subscription = Subscription()
        self.client = str(uuid.uuid4())
        self.state = self.service.mobile_dialogue_open(request(clientId=self.client))

    def tearDown(self):
        self.service.shutdown()
        self.temp.cleanup()

    def send(self, **extras):
        session = self.state["session"]
        body = request(clientId=self.client, sessionId=session["id"], expectedRevision=session["revision"],
            text="本轮准确问题", attachmentIds=[], requestedProfile="high", chatTransport="chatgpt_subscription",
            subscription=Subscription.binding)
        body.update(extras)
        self.state = self.service.mobile_dialogue_send(body)
        return self.state["job"]["appDispatch"]["id"], body

    def receipt(self, **overrides):
        return {"ok": True, "status": "completed", "output": "完整回答", "responseId": "resp_fixture",
            "responseCompleted": True,
            "actualModel": "fixture-model", "requestedModel": "fixture-model", "terminalEventObserved": True,
            "terminalStatus": "completed", "completionEvidence": "response.completed",
            "completionSource": "completed_stream_deltas", "providerErrorObserved": False, **overrides}

    def ready(self, **extras):
        identifier, body = self.send(**extras)
        claimed = self.service.subscription_claim(identifier)
        self.service.subscription_send_intent(identifier, claimed["claimToken"], claimed["subscription"])
        return identifier, claimed, body

    def profiled(self, profile="pro"):
        self.service.subscription.binding = {**Subscription.binding, "modelSlug": "gpt-6-astra"}
        return self.service.subscription.validate_selection("gpt-6-astra", "fixture-catalog", "fixture-connection", profile)

    def profile_receipt(self, selection, **overrides):
        return self.receipt(actualModel=selection["modelSlug"], requestedModel=selection["modelSlug"],
            requestedReasoning=dict(selection["reasoning"]), actualReasoning=dict(selection["reasoning"]), **overrides)

    def test_three_profile_completions_save_full_answer_and_actual_receipt(self):
        for profile in ("fast", "high", "pro"):
            selection = self.profiled(profile)
            identifier, claimed, _ = self.ready(subscription=selection, requestedProfile=profile)
            text = ("完整长回答：\n" + profile + "\n") * 4000
            result = self.service.subscription_complete(identifier, claimed["claimToken"], self.profile_receipt(selection, output=text))
            saved = result["job"]["result"]
            self.assertEqual(saved["text"], text)
            self.assertTrue(saved["actualProfileVerified"])
            self.assertEqual(saved["actualProfile"], profile)
            self.assertEqual(saved["requestedReasoning"], selection["reasoning"])
            self.assertEqual(saved["actualReasoning"], selection["reasoning"])
            state = self.service.mobile_dialogue_get("clientId=" + self.client)
            self.assertTrue(state["execution"]["actualReceipt"]["verified"])
            self.assertEqual(state["execution"]["actualReceipt"]["actualProfile"], profile)

    def test_profile_completion_missing_or_different_reasoning_cannot_create_answer(self):
        selection = self.profiled()
        identifier, claimed, _ = self.ready(subscription=selection, requestedProfile="pro")
        for actual in (None, {"mode": "standard", "effort": "high"}, {"mode": "pro", "effort": "max"}):
            receipt = self.profile_receipt(selection)
            receipt["actualReasoning"] = actual
            with self.assertRaises(WorkflowError) as error:
                self.service.subscription_complete(identifier, claimed["claimToken"], receipt)
            self.assertEqual(error.exception.code, "subscription_profile_unverified")
        self.assertFalse(any(item["role"] == "assistant" for item in self.service.detail(self.state["session"]["recordId"])["messages"]))
        receipt.update(ok=False, status="unknown", code="completed_reasoning_mismatch")
        self.service.subscription_fail(identifier, claimed["claimToken"], receipt)
        saved = self.service.detail(self.state["session"]["recordId"])["jobs"][-1]["result"]
        self.assertFalse(saved["actualProfileVerified"])
        self.assertEqual(saved["partialText"], "完整回答")
        self.assertFalse(saved["retryAllowed"])

    def test_mobile_profile_mismatch_rejects_without_changing_draft_or_creating_job(self):
        selection = self.profiled("pro")
        before = self.service.mobile_dialogue_get("clientId=" + self.client)
        with self.assertRaises(WorkflowError) as error:
            self.send(subscription=selection, requestedProfile="high")
        self.assertEqual(error.exception.code, "subscription_profile_mismatch")
        after = self.service.mobile_dialogue_get("clientId=" + self.client)
        self.assertEqual(after["session"], before["session"])
        self.assertEqual(after["detail"]["jobs"], before["detail"]["jobs"])

    def test_changing_selected_model_cannot_reuse_previous_profile_verification(self):
        selection = self.profiled("pro")
        identifier, claimed, _ = self.ready(subscription=selection, requestedProfile="pro")
        completed = self.service.subscription_complete(identifier, claimed["claimToken"], self.profile_receipt(selection))
        old_result = completed["job"]["result"]
        before = self.service.mobile_dialogue_get("clientId=" + self.client)
        self.assertTrue(before["execution"]["actualReceipt"]["verified"])
        session = before["session"]
        changed = self.service.mobile_dialogue_draft(request(clientId=self.client, sessionId=session["id"],
            expectedRevision=session["revision"], text="下一轮草稿", attachmentIds=[], requestedProfile="pro",
            chatTransport="chatgpt_subscription", subscription={**selection, "modelSlug": "gpt-5.6-sol"}))
        self.assertFalse(changed["execution"]["actualReceipt"]["verified"])
        self.assertEqual(changed["detail"]["jobs"][-1]["result"], old_result)
        self.assertTrue(old_result["actualProfileVerified"])
        self.assertEqual(old_result["actualModel"], "gpt-6-astra")

    def test_cross_profile_mutation_in_frozen_payload_cannot_claim_or_record_intent(self):
        selection = self.profiled("high")
        identifier, _ = self.send(subscription=selection, requestedProfile="high")
        with self.service._db() as db:
            row = self.service._dispatch(db, identifier)
            snapshot = json.loads(row["snapshot"])
            job = self.service._app_dispatch_job(db, row, snapshot)
            payload = json.loads(job["payload"])
            payload["subscription"]["reasoning"] = {"mode": "pro", "effort": "high"}
            db.execute("UPDATE jobs SET payload=? WHERE id=?", (json.dumps(payload), job["id"]))
        with self.assertRaises(WorkflowError):
            self.service.subscription_claim(identifier)
        with self.service._db() as db:
            self.assertIsNone(self.service._setting(db, "subscription-intent:" + identifier))
            self.assertFalse(self.service._dispatch(db, identifier)["claim_token"])

    def test_frozen_binding_intent_exactly_once_and_completed_original_output(self):
        identifier, claimed, body = self.ready()
        self.assertEqual(claimed["frozen"]["text"], body["text"])
        self.assertEqual(claimed["frozen"]["subscription"], Subscription.binding)
        with self.assertRaises(WorkflowError):
            self.service.subscription_send_intent(identifier, claimed["claimToken"], claimed["subscription"])
        first = self.service.subscription_complete(identifier, claimed["claimToken"], self.receipt())
        replay = self.service.subscription_complete(identifier, claimed["claimToken"], self.receipt())
        self.assertFalse(first["duplicate"])
        self.assertTrue(replay["duplicate"])
        detail = self.service.detail(self.state["session"]["recordId"])
        self.assertEqual([item["text"] for item in detail["messages"] if item["role"] == "assistant"], ["完整回答"])
        self.assertEqual(first["job"]["result"]["responseId"], "resp_fixture")
        self.assertNotIn("targetThreadId", first["job"]["result"])
        self.assertEqual(first["job"]["subscriptionPhase"], "completed")
        self.assertEqual(self.service.mobile_dialogue_send(body)["job"]["id"], first["job"]["id"])

    def test_missing_terminal_wrong_model_or_provider_error_cannot_complete(self):
        identifier, claimed, _ = self.ready()
        for fields in ({"terminalEventObserved": False}, {"actualModel": "other-model"}, {"providerErrorObserved": True}, {"output": ""}):
            with self.assertRaises(WorkflowError):
                self.service.subscription_complete(identifier, claimed["claimToken"], self.receipt(**fields))
        self.assertFalse(any(message["role"] == "assistant" for message in self.service.detail(self.state["session"]["recordId"])["messages"]))

    def test_long_answer_is_saved_whole(self):
        identifier, claimed, _ = self.ready()
        text = "长回复\n" * 9000
        self.service.subscription_complete(identifier, claimed["claimToken"], self.receipt(output=text))
        self.assertEqual(self.service.detail(self.state["session"]["recordId"])["messages"][-1]["text"], text)

    def test_late_answer_after_clear_stays_on_original_record(self):
        identifier, claimed, _ = self.ready()
        original = self.state["session"]["recordId"]
        session = self.state["session"]
        new = self.service.mobile_dialogue_clear(request(clientId=self.client, sessionId=session["id"], expectedRevision=session["revision"]))
        self.service.subscription_complete(identifier, claimed["claimToken"], self.receipt())
        self.assertEqual(self.service.detail(original)["messages"][-1]["text"], "完整回答")
        self.assertFalse(any(item["role"] == "assistant" for item in self.service.detail(new["session"]["recordId"])["messages"]))

    def test_unknown_and_restart_do_not_resend_or_upgrade_partials(self):
        identifier, claimed, _ = self.ready()
        self.service.subscription_fail(identifier, claimed["claimToken"], {"status": "unknown", "code": "stream_interrupted", "output": "尚未完成"})
        with self.assertRaises(WorkflowError):
            self.service.subscription_claim(identifier)
        with self.assertRaises(WorkflowError):
            self.service.subscription_complete(identifier, claimed["claimToken"], self.receipt())
        job = self.service.detail(self.state["session"]["recordId"])["jobs"][-1]
        self.assertEqual(job["subscriptionPhase"], "unknown")
        self.assertEqual(job["result"]["partialText"], "尚未完成")
        recovered = WorkflowService(self.root / "private")
        self.assertEqual(recovered.detail(self.state["session"]["recordId"])["jobs"][-1]["status"], "waiting")
        recovered.shutdown()

    def test_startup_does_not_adopt_unsent_pending(self):
        identifier, _ = self.send()
        with self.service._db() as db:
            original_revision = self.service._revision(db)
        recovered = WorkflowService(self.root / "private")
        job = recovered.detail(self.state["session"]["recordId"])["jobs"][-1]
        self.assertEqual(job["status"], "failed")
        self.assertIn("不会自动重发", job["error"])
        with recovered._db() as db:
            self.assertGreater(recovered._revision(db), original_revision)
        recovered.shutdown()

    def test_new_subscription_cannot_lose_all_submission_timestamps(self):
        identifier, _ = self.send()
        with self.service._db() as db:
            row = self.service._dispatch(db, identifier)
            snapshot = json.loads(row["snapshot"])
            job = self.service._app_dispatch_job(db, row, snapshot)
            payload = json.loads(job["payload"])
            for value in (snapshot, payload, payload["appFrozen"]):
                value.pop("submissionTime")
            db.execute("UPDATE jobs SET payload=? WHERE id=?", (json.dumps(payload), job["id"]))
            db.execute("UPDATE idea_dispatches SET snapshot=? WHERE id=?", (json.dumps(snapshot), identifier))
        with self.assertRaises(WorkflowError):
            self.service.subscription_claim(identifier)

    def test_native_cannot_claim_old_browser_or_use_generic_app_result(self):
        session = self.state["session"]
        browser = self.service.mobile_dialogue_send(request(clientId=self.client, sessionId=session["id"],
            expectedRevision=session["revision"], text="旧浏览器消息", attachmentIds=[], requestedProfile="high"))
        with self.assertRaises(WorkflowError):
            self.service.subscription_claim(browser["job"]["appDispatch"]["id"])
        session = browser["session"]
        self.state = self.service.mobile_dialogue_clear(request(clientId=self.client, sessionId=session["id"], expectedRevision=session["revision"]))
        identifier, _, _ = self.ready()
        with self.assertRaises(WorkflowError):
            self.service.incubator_attach_result(request(id=identifier, claimToken=uuid.uuid4().hex, status="completed",
                targetThreadId=str(uuid.uuid4()), result={"text": "伪造App回答", "turnId": "turn", "sourceMessageId": "user"}))

    def test_selected_image_bytes_bound_to_current_record(self):
        buffer = io.BytesIO()
        Image.new("RGB", (12, 12), "green").save(buffer, "PNG")
        data = buffer.getvalue()
        path = self.root / "selected.png"
        path.write_bytes(data)
        session = self.state["session"]
        uploaded = self.service.mobile_dialogue_upload({"requestId": str(uuid.uuid4()), "recordId": session["recordId"], "text": json.dumps({
            "clientId": self.client, "sessionId": session["id"], "expectedRevision": session["revision"]})},
            [IncomingFile(path, 0, len(data), "selected.png", "image/png")])
        self.state = self.service.mobile_dialogue_get("clientId=" + self.client)
        identifier, _ = self.send(attachmentIds=uploaded["uploadedAttachmentIds"])
        claimed = self.service.subscription_claim(identifier)
        descriptor, image = claimed["imageBytes"][0]
        self.assertEqual(image, data)
        self.assertEqual(descriptor["sha256"], hashlib.sha256(data).hexdigest())

    def test_phone_can_read_safe_cache_but_cannot_change_authorization(self):
        self.assertTrue(workflow_get(self.service, "subscription/status", "")["connected"])
        for action in ("signin", "models", "disconnect"):
            with self.assertRaises(WorkflowError):
                workflow_post(self.service, "subscription/" + action, {})

    def test_notifier_fanout_preserves_other_listener_on_close(self):
        class Listener:
            def __init__(self): self.received = []
            def notify_committed(self, ids): self.received.extend(ids)
            def notify_released(self, ids): pass
        a, b = Listener(), Listener()
        self.service.register_dispatch_notifier(a)
        self.service.register_dispatch_notifier(b)
        identifier, _ = self.send()
        self.assertEqual(a.received, [identifier])
        self.assertEqual(b.received, [identifier])
        self.service.unregister_dispatch_notifier(a)
        self.assertIn(b, self.service._dispatch_commit_notifier.listeners)


if __name__ == "__main__":
    unittest.main()
