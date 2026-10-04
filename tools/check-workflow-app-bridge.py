"""Private, disposable App discussion outbox checks; never sends an App message."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from transfer_store import IncomingFile
from workflow_service import WorkflowError, WorkflowService


def request(**fields):
    return {"requestId": str(uuid.uuid4()), **fields}


class ForbiddenModels:
    def config(self):
        return {"ready": False, "selected": "", "providers": []}

    def discuss(self, *_):
        raise AssertionError("App discussion must never call a model API")

    def transcribe(self, *_args, **_kwargs):
        raise AssertionError("Local transcription must never call a model API")


class AppBridgeChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="console-app-bridge-check-")
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.service = WorkflowService(self.root / "private", models=ForbiddenModels(), projects=[
            {"id": "console", "name": "Isolated project", "root": str(self.project),
             "capabilities": ["result_import"], "allowGeneratedScripts": False}])
        self.record = self.service.create(request(projectId="console", title="Selected record", text="Original context"))["record"]["id"]
        self.codex, self.chatgpt = str(uuid.uuid4()), str(uuid.uuid4())
        self.targets = [{"id": self.codex, "kind": "codex", "title": "Local Codex", "hostId": "local"},
                        {"id": self.chatgpt, "kind": "chatgpt", "title": "Existing ChatGPT"}]
        self.service.incubator_set_targets(request(targets=self.targets))

    def tearDown(self):
        self.service.shutdown()
        self.temporary.cleanup()

    def target(self, kind="codex", mode="new"):
        return {"kind": kind, "mode": mode, "threadId": "" if mode == "new" else self.codex if kind == "codex" else self.chatgpt,
                "name": "Image discussion" if mode == "new" else "Local Codex" if kind == "codex" else "Existing ChatGPT"}

    def discuss(self, record=None, **fields):
        return self.service.discuss(request(recordId=record or self.record, text="Please analyse this image only",
            appTarget=self.target(), **fields))

    def upload(self, record=None, color="blue"):
        stream = io.BytesIO()
        Image.new("RGB", (21, 17), color).save(stream, "PNG")
        data = stream.getvalue()
        spool = self.root / (uuid.uuid4().hex + ".spool")
        spool.write_bytes(data)
        result = self.service.upload(request(recordId=record or self.record), [IncomingFile(spool, 0, len(data), "selected.png", "image/png")])
        return result["attachments"][-1]["id"]

    def upload_audio(self):
        import wave
        spool = self.root / (uuid.uuid4().hex + ".wav")
        with wave.open(str(spool), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(b"\0\0" * 16000)
        uploaded = self.service.upload(request(recordId=self.record), [IncomingFile(spool, 0, spool.stat().st_size, "review.wav", "audio/wav")])
        return next(item["id"] for item in uploaded["attachments"] if item["mimeType"].startswith("audio/"))

    def error(self, action, code=None):
        with self.assertRaises(WorkflowError) as caught:
            action()
        if code:
            self.assertEqual(caught.exception.code, code)

    def claim(self):
        return self.service.incubator_claim(request())

    def attach(self, dispatch, status="waiting", result=None, **fields):
        return self.service.incubator_attach_result(request(id=dispatch["id"], claimToken=dispatch["claimToken"],
            status=status, targetThreadId=dispatch["targetThreadId"] or self.codex, result=result or {}, **fields))

    def complete(self, dispatch):
        return self.attach(dispatch, "completed", {"text": "Actual selected-image analysis", "turnId": "actual-turn", "sourceMessageId": "actual-user-message"})

    def test_config_no_api_default_and_saving_does_not_dispatch(self):
        config = self.service.config()
        self.assertTrue(config["appDiscussion"]["enabled"])
        self.assertEqual(config["appDiscussion"]["defaultTarget"]["kind"], "codex")
        self.assertFalse(config["models"]["ready"])
        self.assertIn("available", config["localTranscription"])
        self.upload()
        self.service.add_message(request(recordId=self.record, text="Saved review, not authorised to send"))
        self.assertEqual(self.service.incubator_dispatches()["dispatches"], [])
        self.assertEqual(self.service.incubator_list()["ideas"], [])

    def test_selected_images_and_history_are_frozen_and_private(self):
        first = self.upload()
        other = self.service.create(request(projectId="console", text="Other record private comment"))["record"]["id"]
        other_image = self.upload(other, "red")
        self.service.add_message(request(recordId=self.record, text="Before acceptance"))
        reply = self.discuss(context={"attachmentIds": [first], "selectedText": "Only chosen sentence"})
        self.service.add_message(request(recordId=self.record, text="After acceptance must not retarget"))
        later_image = self.upload(color="green")
        public = self.service.detail(self.record)
        self.assertEqual(reply["job"]["status"], "waiting")
        self.assertEqual(reply["job"]["appDispatch"]["status"], "pending")
        self.assertNotIn(str(self.root), json.dumps(public))
        self.assertEqual(self.service.incubator_list()["dispatches"], [])
        self.assertEqual(self.service.incubator_list()["ideas"], [])
        exposed = self.service.incubator_dispatches()["dispatches"][0]
        self.assertNotIn("prompt", exposed)
        private = self.claim()["dispatch"]
        self.assertEqual(private["sourceType"], "workflow_discussion")
        self.assertEqual(private["recordId"], self.record)
        self.assertEqual(private["jobId"], reply["job"]["id"])
        self.assertEqual(private["ideaId"], "")
        self.assertIn(first, private["prompt"])
        self.assertNotIn(other_image, private["prompt"])
        self.assertNotIn(later_image, private["prompt"])
        self.assertNotIn("Other record private comment", private["prompt"])
        self.assertNotIn("After acceptance must not retarget", private["prompt"])
        self.assertIn("Before acceptance", private["prompt"])
        self.assertIn("Only chosen sentence", private["prompt"])
        self.assertIn("sha256", private["prompt"])
        self.assertIn("禁止执行修改", private["prompt"])
        with self.service._db() as db:
            frozen = json.loads(db.execute("SELECT payload FROM jobs WHERE id=?", (reply["job"]["id"],)).fetchone()[0])["appFrozen"]
        item = frozen["images"][0]
        self.assertTrue(Path(item["path"]).is_absolute())
        self.assertEqual(item["sha256"], hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest())

    def test_duplicate_discover_and_claim_are_idempotent_and_serial(self):
        payload = request(recordId=self.record, text="Confirmed once", appTarget=self.target())
        first = self.service.discuss(payload)
        again = self.service.discuss(payload)
        self.assertTrue(again["duplicate"])
        self.assertEqual(first["job"]["id"], again["job"]["id"])
        self.error(lambda: self.discuss(), "dispatch_in_progress")
        claim_payload = request()
        claimed = self.service.incubator_claim(claim_payload)
        self.assertTrue(claimed["shouldDispatch"])
        self.assertFalse(self.service.incubator_claim(claim_payload)["shouldDispatch"])
        self.error(lambda: self.claim(), "dispatch_busy")
        self.error(lambda: self.service.retry(request(jobId=first["job"]["id"])), "verification_required")

    def test_concurrent_app_requests_create_once_and_block_idea_claim(self):
        second = WorkflowService(self.root / "private", recover_jobs=False)
        payload = request(recordId=self.record, text="One accepted question", appTarget=self.target())
        barrier, results = threading.Barrier(2), []
        def accept(service):
            barrier.wait(timeout=5)
            results.append(service.discuss(payload))
        threads = [threading.Thread(target=accept, args=(service,)) for service in (self.service, second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["job"]["id"], results[1]["job"]["id"])
        self.assertEqual(len(self.service.detail(self.record)["jobs"]), 1)
        idea = self.service.incubator_create(request(title="Separate idea"))["idea"]
        idea_dispatch = self.service.incubator_publish(request(id=idea["id"], expectedRevision=idea["revision"],
            targetKind="codex", targetMode="new", targetName="Separate idea chat"))["dispatch"]
        app_dispatch = self.service.incubator_claim(request(id=results[0]["job"]["appDispatch"]["id"]))["dispatch"]
        self.error(lambda: second.incubator_claim(request(id=idea_dispatch["id"])), "dispatch_busy")
        self.complete(app_dispatch)
        claimed_idea = second.incubator_claim(request(id=idea_dispatch["id"]))["dispatch"]
        self.assertEqual(claimed_idea["sourceType"], "idea")

    def test_restarted_claim_is_needs_review_and_never_automatically_sent(self):
        job = self.discuss()["job"]
        dispatch = self.claim()["dispatch"]
        restarted = WorkflowService(self.root / "private")
        self.assertEqual(restarted.incubator_dispatches(waiting=True)["dispatches"][0]["status"], "needs_review")
        self.assertEqual(restarted.detail(self.record)["jobs"][0]["status"], "waiting")
        self.error(lambda: restarted.retry(request(jobId=job["id"])), "verification_required")
        self.error(lambda: restarted.incubator_claim(request()), "dispatch_busy")
        self.error(lambda: restarted.incubator_attach_result(request(id=dispatch["id"], claimToken=dispatch["claimToken"],
            status="waiting", targetThreadId=self.codex)), "verification_required")
        accepted = restarted.incubator_attach_result(request(id=dispatch["id"], claimToken=dispatch["claimToken"],
            status="waiting", targetThreadId=self.codex, verified=True))
        self.assertEqual(accepted["job"]["appDispatch"]["status"], "waiting")

    def test_complete_returns_one_assistant_to_same_record_and_no_execution(self):
        image_id = self.upload()
        job = self.discuss()["job"]
        dispatch = self.claim()["dispatch"]
        self.attach(dispatch, result={"turnId": "actual-turn", "sourceMessageId": "actual-user-message"})
        payload = request(id=dispatch["id"], claimToken=dispatch["claimToken"], status="completed", targetThreadId=self.codex,
            result={"text": "Actual selected-image analysis", "turnId": "actual-turn", "sourceMessageId": "actual-user-message"})
        completed = self.service.incubator_attach_result(payload)
        self.assertTrue(self.service.incubator_attach_result(payload)["duplicate"])
        self.error(lambda: self.service.incubator_attach_result({**payload, "requestId": str(uuid.uuid4())}))
        detail = self.service.detail(self.record)
        self.assertEqual(detail["jobs"][0]["status"], "succeeded")
        self.assertEqual(detail["jobs"][0]["resultMessageId"], completed["job"]["resultMessageId"])
        self.assertEqual([message["text"] for message in detail["messages"] if message["role"] == "assistant"], ["Actual selected-image analysis"])
        self.assertEqual(detail["record"]["primaryAttachmentId"], image_id)
        self.assertEqual(detail["record"]["discussionTarget"], {"kind": "codex", "mode": "existing", "threadId": self.codex, "name": "Local Codex"})
        self.assertEqual(len(detail["jobs"]), 1)
        self.assertFalse(self.service.has_pending_jobs())
        next_round = self.service.discuss(request(recordId=self.record, text="Second question", appTarget=detail["record"]["discussionTarget"]))
        self.assertEqual(next_round["job"]["appDispatch"]["targetThreadId"], self.codex)
        self.assertEqual(next_round["job"]["appDispatch"]["targetMode"], "existing")
        self.assertEqual(next_round["job"]["parentJobId"], None)
        self.assertEqual(job["recordId"], next_round["job"]["recordId"])

    def test_completion_requires_text_turn_user_and_exact_binding(self):
        self.discuss()
        dispatch = self.claim()["dispatch"]
        self.error(lambda: self.attach(dispatch, "completed", {"text": "Answer"}))
        self.error(lambda: self.attach(dispatch, "completed", {"text": "Answer", "turnId": "turn"}), "result_not_matching")
        self.attach(dispatch, result={"turnId": "bound-turn", "sourceMessageId": "bound-user"})
        self.error(lambda: self.attach(dispatch, "completed", {"text": "Answer", "turnId": "wrong-turn", "sourceMessageId": "bound-user"}), "result_not_matching")
        self.error(lambda: self.attach(dispatch, "completed", {"text": "Answer", "turnId": "bound-turn", "sourceMessageId": "wrong-user"}), "result_not_matching")
        self.error(lambda: self.service.incubator_attach_result(request(id=dispatch["id"], claimToken=dispatch["claimToken"],
            status="completed", targetThreadId=self.chatgpt,
            result={"text": "Answer", "turnId": "bound-turn", "sourceMessageId": "bound-user"})))
        self.assertFalse(any(item["role"] == "assistant" for item in self.service.detail(self.record)["messages"]))

    def test_chatgpt_image_rejected_but_explicit_empty_selection_allows_text(self):
        self.upload()
        target = self.target("chatgpt", "existing")
        self.error(lambda: self.service.discuss(request(recordId=self.record, text="Image please", appTarget=target)), "app_images_unavailable")
        self.assertEqual(self.service.incubator_dispatches()["dispatches"], [])
        reply = self.service.discuss(request(recordId=self.record, text="Only text please", context={"attachmentIds": []}, appTarget=target))
        self.assertEqual(reply["job"]["appDispatch"]["targetKind"], "chatgpt")
        self.assertNotIn(str(self.service.attachments_dir), self.claim()["dispatch"]["prompt"])

    def test_target_mismatch_cloud_unknown_host_and_chatgpt_new_rejected(self):
        self.error(lambda: self.service.discuss(request(recordId=self.record, text="Question", appTarget=self.target("chatgpt", "new"))), "app_target_unavailable")
        self.error(lambda: self.service.discuss(request(recordId=self.record, text="Question", appTarget={**self.target("codex", "existing"), "name": "Wrong title"})), "app_target_changed")
        self.error(lambda: self.service.discuss(request(recordId=self.record, text="Question", appTarget={**self.target("chatgpt", "existing"), "threadId": self.codex})), "app_target_changed")
        self.upload()
        for host in ("remote", None):
            targets = [dict(item) for item in self.targets]
            if host is None:
                targets[0].pop("hostId")
            else:
                targets[0]["hostId"] = host
            self.service.incubator_set_targets(request(targets=targets))
            self.error(lambda: self.service.discuss(request(recordId=self.record, text="Image", appTarget=self.target("codex", "existing"))), "app_images_unavailable")

    def test_foreign_attachment_message_and_mutated_image_never_dispatch(self):
        first = self.upload()
        other = self.service.create(request(projectId="console", text="Other"))["record"]["id"]
        other_image = self.upload(other, "red")
        other_message = self.service.detail(other)["messages"][0]["id"]
        self.error(lambda: self.discuss(context={"attachmentIds": [other_image]}))
        self.error(lambda: self.discuss(context={"attachmentIds": [first], "sourceMessageId": other_message}))
        job = self.discuss()["job"]
        with self.service._db() as db:
            payload = json.loads(db.execute("SELECT payload FROM jobs WHERE id=?", (job["id"],)).fetchone()[0])
        Path(payload["appFrozen"]["images"][0]["path"]).write_bytes(b"changed")
        claimed = self.claim()
        self.assertFalse(claimed["shouldDispatch"])
        self.assertEqual(claimed["dispatch"]["status"], "failed")
        self.assertEqual(self.service.detail(self.record)["jobs"][0]["status"], "failed")

    def test_needs_review_fail_and_known_failure_retry_preserve_context(self):
        image_id = self.upload()
        job = self.discuss()["job"]
        dispatch = self.claim()["dispatch"]
        self.service.incubator_fail(request(id=dispatch["id"], claimToken=dispatch["claimToken"], status="needs_review", error="Tool timeout, delivery unknown"))
        self.error(lambda: self.service.retry(request(jobId=job["id"])), "verification_required")
        self.service.incubator_fail(request(id=dispatch["id"], claimToken=dispatch["claimToken"], status="failed", error="Verified no message was delivered"))
        later = self.upload(color="green")
        again = self.service.retry(request(jobId=job["id"]))["job"]
        self.assertEqual(again["attempt"], 2)
        self.assertEqual(again["parentJobId"], job["id"])
        self.assertEqual(again["status"], "waiting")
        next_dispatch = self.claim()["dispatch"]
        self.assertIn(image_id, next_dispatch["prompt"])
        self.assertNotIn(later, next_dispatch["prompt"])
        self.assertNotEqual(next_dispatch["id"], dispatch["id"])

    def test_permission_change_during_acceptance_rolls_back_without_send(self):
        count = 0
        def authorize():
            nonlocal count
            count += 1
            if count == 2:
                raise WorkflowError("Phone permission revoked", 403)
        self.error(lambda: self.service.discuss(request(recordId=self.record, text="Question", appTarget=self.target()), authorize=authorize))
        self.assertEqual(self.service.incubator_dispatches()["dispatches"], [])
        self.assertEqual(self.service.detail(self.record)["jobs"], [])
        self.assertEqual(len(self.service.detail(self.record)["messages"]), 1)

    def test_worker_executes_only_later_explicit_task_and_returns_image(self):
        self.upload()
        job = self.discuss()["job"]
        self.service.start()
        time.sleep(0.08)
        self.assertEqual(self.service.detail(self.record)["jobs"][0]["status"], "waiting")
        self.complete(self.claim()["dispatch"])
        result_path = self.project / "real-result.png"
        Image.new("RGB", (31, 19), "green").save(result_path)
        executed = self.service.submit(request(recordId=self.record, text="Import only selected result", action="result_import", args={"paths": [result_path.name]}))["job"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            done = next(item for item in self.service.detail(self.record)["jobs"] if item["id"] == executed["id"])
            if done["status"] == "succeeded":
                break
            time.sleep(0.02)
        self.assertEqual(done["status"], "succeeded", done)
        detail = self.service.detail(self.record)
        self.assertEqual(detail["jobs"][0]["id"], job["id"])
        self.assertEqual(detail["messages"][-1]["role"], "result")
        self.assertEqual(detail["record"]["primaryAttachmentId"], done["result"]["primaryAttachmentId"])

    def test_local_transcription_routes_without_api_and_keeps_editable_transcript(self):
        attachment = self.upload_audio()
        discovered = str(self.root / "trusted-existing-ffmpeg.exe")
        self.service.callbacks["ffmpeg_executable"] = lambda: discovered
        queued = self.service.transcribe(request(recordId=self.record, attachmentId=attachment, transcriptionSource="windows_local"))["job"]
        with patch("workflow_service.local_transcribe", return_value={"text": "Editable local transcript", "durationValidated": True,
                "durationSeconds": 1.0, "provider": "windows_local", "language": "zh-CN"}) as local:
            self.service.start()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                done = next(item for item in self.service.detail(self.record)["jobs"] if item["id"] == queued["id"])
                if done["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.02)
            self.assertEqual(done["status"], "succeeded", done)
            self.assertEqual(local.call_count, 1)
            self.assertEqual(local.call_args.kwargs["ffmpeg_path"], discovered)
            self.assertIs(local.call_args.kwargs["stop_event"], self.service._stop)
            self.assertEqual(local.call_args.args[1], self.service.jobs_dir / queued["id"])
        self.assertEqual(self.service.detail(self.record)["messages"][-1]["role"], "transcript")
        self.assertEqual(done["result"]["provider"], "windows_local")
        self.assertEqual(self.service.incubator_dispatches()["dispatches"], [])

    def test_local_transcription_config_uses_trusted_discovery_without_exposing_path(self):
        discovered = str(self.root / "trusted-existing-ffmpeg.exe")
        self.service.callbacks["ffmpeg_executable"] = lambda: discovered
        public = {"available": True, "status": "ready", "languages": ["zh-CN"], "compressedAudioAvailable": True}
        with patch("workflow_service.local_transcription_config", return_value=public) as capability:
            config = self.service.config()
            capability.assert_called_once_with(ffmpeg_path=discovered)
            self.assertEqual(config["localTranscription"], public)
            self.assertNotIn(discovered, json.dumps(config))

    def test_local_transcription_resource_gate_waits_and_preserves_original_audio(self):
        attachment = self.upload_audio()
        self.service.callbacks["before_execute"] = lambda action, project: action != "transcribe"
        queued = self.service.transcribe(request(recordId=self.record, attachmentId=attachment, transcriptionSource="windows_local"))["job"]
        with patch("workflow_service.local_transcribe", side_effect=AssertionError("Resource gate must prevent a recognizer process")) as local:
            self.service.start()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                done = next(item for item in self.service.detail(self.record)["jobs"] if item["id"] == queued["id"])
                if done["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.02)
            self.assertEqual(done["status"], "waiting", done)
            self.assertIn("资源不足", done["error"])
            local.assert_not_called()
        with self.service.read_attachment("id=" + attachment) as audio:
            self.assertGreater(len(audio["source"].read()), 0)
        self.assertFalse(any(item["role"] == "transcript" for item in self.service.detail(self.record)["messages"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
