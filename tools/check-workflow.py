"""Disposable durable workflow tests: real child scripts, local HTTP model fixture."""
import io
import json
import os
import sqlite3
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from transfer_store import IncomingFile
from workflow_service import WorkflowService, WorkflowError
from workflow_models import WorkflowModels, WorkflowModelError


def request(**values):
    return {"requestId": str(uuid.uuid4()), **values}


def image():
    stream = io.BytesIO()
    Image.new("RGB", (24, 18), "blue").save(stream, "PNG")
    return stream.getvalue()


SCRIPT = """import json, os
from pathlib import Path
from PIL import Image
output = Path(os.environ['CONSOLE_WORKFLOW_OUTPUT_DIR'])
inputs = json.loads(Path(os.environ['CONSOLE_WORKFLOW_INPUT_FILE']).read_text(encoding='utf-8'))
Image.new('RGB', (32, 20), 'green').save(output / 'result.png')
Path(os.environ['CONSOLE_WORKFLOW_RESULT_MANIFEST']).write_text(json.dumps({'text': 'Real script result', 'files': ['result.png']}), encoding='utf-8')
print('script actually executed')
"""


class Models:
    def __init__(self):
        self.inputs = []
        self.ready = True
        self.script = SCRIPT

    def config(self):
        return {"ready": self.ready, "selected": "fake", "providers": [{"id": "fake", "transcriptionReady": True}]}

    def execution_environment(self, environment):
        return dict(environment)

    def redact_execution_log(self, text):
        return text

    def discuss(self, payload):
        self.inputs.append(payload)
        return {"text": "Analyse only; no execution.", "options": [{"id": "one", "title": "One change", "instruction": "Make selected change"},
                                                                 {"id": "two", "title": "Unselected", "instruction": "Never select this other option"}]}

    def plan(self, payload):
        self.inputs.append(payload)
        return {"action": "generated_script", "args": {}, "language": "python", "text": "Proposal", "script": self.script}

    def transcribe(self, path, **kwargs):
        self.inputs.append({"path": path, **kwargs})
        return {"text": "Recorded review, not a dispatch", "durationValidated": True}


class Provider(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *_):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append(body)
        result = {"text": "Local HTTP AI analysis", "options": [{"id": "one", "title": "Inspect", "instruction": "Inspect image"}]}
        reply = {"status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(result)}]}]}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(reply).encode())


class WorkflowChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="console-workflow-check-")
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.command = self.project / "preview.py"
        self.command.write_text(SCRIPT, encoding="utf-8")
        self.models = Models()
        self.projects = [{"id": "console", "name": "Console isolated fixture", "root": str(self.project),
                          "capabilities": ["command", "capture_screen", "generated_script", "result_import"], "allowGeneratedScripts": True,
                          "commands": [{"id": "preview", "name": "Preview", "argv": [sys.executable, str(self.command)]}],
                          "scriptRunners": {"python": [sys.executable]}, "timeout": 5}]
        self.service = WorkflowService(self.root / "data", self.models, projects=self.projects)
        self.record = self.service.create(request(projectId="console", title="Test review", text="Original image comment"))["record"]["id"]

    def tearDown(self):
        self.service.shutdown()
        self.temp.cleanup()

    def wait(self, job, service=None):
        service = service or self.service
        until = time.monotonic() + 12
        while time.monotonic() < until:
            current = next(item for item in service.detail(job["recordId"])["jobs"] if item["id"] == job["id"])
            if current["status"] not in {"queued", "running"}:
                return current
            time.sleep(0.03)
        self.fail("worker did not finish")

    def upload(self, contents=None, name="input.png", mime="image/png", fields=None, authorize=None):
        contents = image() if contents is None else contents
        source = self.root / (uuid.uuid4().hex + ".spool")
        source.write_bytes(contents)
        incoming = IncomingFile(source, 0, len(contents), name, mime)
        return self.service.upload(fields or request(recordId=self.record), [incoming], authorize=authorize)

    def test_real_command_executes_without_ai_returns_image_to_original_record(self):
        self.service.models = None
        original = self.upload()
        payload = request(recordId=self.record, text="Generate a real preview", action="command", commandId="preview")
        dispatched = self.service.submit(payload)
        duplicate = self.service.submit(payload)
        self.assertEqual(dispatched["job"]["id"], duplicate["job"]["id"])
        self.assertTrue(self.service.has_pending_jobs())
        self.service.start()
        done = self.wait(dispatched["job"])
        self.assertEqual(done["status"], "succeeded", done)
        self.assertIn("script actually executed", done["log"])
        detail = self.service.detail(self.record, prefix="/api/phone/workflow")
        self.assertEqual(detail["record"]["primaryAttachmentId"], done["result"]["primaryAttachmentId"])
        self.assertNotEqual(detail["record"]["primaryAttachmentId"], original["record"]["primaryAttachmentId"])
        self.assertEqual(detail["messages"][-1]["role"], "result")
        self.assertNotIn(str(self.root), json.dumps(detail))
        with self.service.read_attachment("id=" + done["resultAttachmentIds"][0]) as item:
            with Image.open(item["source"]) as output:
                self.assertEqual(output.size, (32, 20))
        restarted = WorkflowService(self.root / "data", projects=[])
        self.assertEqual(restarted.detail(self.record)["jobs"][0]["status"], "succeeded")
        self.assertTrue(restarted.detail(self.record)["attachments"])

    def test_generated_script_is_real_and_only_selected_option_reaches_planner(self):
        self.upload()
        self.service.start()
        discussion = self.service.discuss(request(recordId=self.record, text="Review screenshot"))
        analysed = self.wait(discussion["job"])
        message = next(item for item in self.service.detail(self.record)["messages"] if item["id"] == analysed["resultMessageId"])
        job = self.service.submit(request(recordId=self.record, text="Make selected change", action="generated_script",
                                          context={"sourceMessageId": message["id"], "optionId": "one", "selectedText": "Make selected change"}))["job"]
        done = self.wait(job)
        self.assertEqual(done["status"], "succeeded", done)
        plan_input = self.models.inputs[-1]
        self.assertTrue(plan_input["images"])
        self.assertNotIn("Never select", json.dumps(plan_input, default=str))
        self.assertIn("CONSOLE_WORKFLOW_RESULT_MANIFEST", plan_input["text"])

    def test_discussion_keeps_bounded_history_and_never_executes(self):
        self.service.start()
        first = self.wait(self.service.discuss(request(recordId=self.record, text="First discussion"))["job"])
        second = self.wait(self.service.discuss(request(recordId=self.record, text="Second discussion"))["job"])
        self.assertEqual((first["status"], second["status"]), ("succeeded", "succeeded"))
        history = self.models.inputs[-1]["context"]
        self.assertTrue(any(item["content"] == "First discussion" for item in history))
        self.assertTrue(any(item["role"] == "assistant" for item in history))
        self.assertFalse(list(self.service.jobs_dir.iterdir()))
        self.assertIsNone(self.service.detail(self.record)["record"]["primaryAttachmentId"])

    def test_jobs_survive_disconnected_client_and_interrupted_jobs_never_replay(self):
        queued = self.service.submit(request(recordId=self.record, text="Offline accepted command", action="command", commandId="preview"))["job"]
        self.service.shutdown()
        restored = WorkflowService(self.root / "data", models=None)
        self.service = restored
        restored.start()
        self.assertEqual(self.wait(queued)["status"], "succeeded")
        other = restored.submit(request(recordId=self.record, text="Interrupted", action="command", commandId="preview"))["job"]
        # Stop first, then emulate the on-disk state of a process lost mid-operation.
        restored.shutdown()
        with restored._db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (other["id"],))
        replacement = WorkflowService(self.root / "data", models=None)
        self.service = replacement
        self.assertEqual(replacement.detail(self.record)["jobs"][-1]["status"], "interrupted")
        replacement.start()
        time.sleep(0.1)
        self.assertEqual(replacement.detail(self.record)["jobs"][-1]["status"], "interrupted")
        retry = replacement.retry(request(jobId=other["id"]))["job"]
        self.assertEqual(retry["attempt"], 2)
        self.assertEqual(self.wait(retry)["status"], "succeeded")

    def test_failure_and_timeout_keep_logs_require_new_explicit_attempt(self):
        self.command.write_text("print('failure evidence', flush=True)\nraise SystemExit(7)\n", encoding="utf-8")
        self.service.models = None
        self.service.start()
        job = self.service.submit(request(recordId=self.record, text="Fail honestly", action="command", commandId="preview"))["job"]
        failed = self.wait(job)
        self.assertEqual(failed["status"], "failed")
        self.assertIn("failure evidence", failed["log"])
        self.assertFalse(failed["resultAttachmentIds"])
        self.command.write_text(SCRIPT, encoding="utf-8")
        retried = self.service.retry(request(jobId=job["id"]))["job"]
        self.assertEqual(self.wait(retried)["status"], "succeeded")
        self.assertEqual(self.service.detail(self.record)["jobs"][0]["status"], "failed")
        self.command.write_text("import time\nprint('timeout evidence', flush=True)\ntime.sleep(5)\n", encoding="utf-8")
        project = {**self.projects[0], "commands": [{"id": "preview", "argv": [sys.executable, str(self.command)], "timeout": 1}]}
        self.service.configure_projects([project])
        timed = self.wait(self.service.submit(request(recordId=self.record, text="Timeout", action="command", commandId="preview"))["job"])
        self.assertEqual(timed["status"], "failed")
        self.assertIn("timeout evidence", timed["log"])

    def test_no_model_and_resource_limits_wait_without_execution(self):
        self.models.ready = False
        self.service.start()
        waiting = self.wait(self.service.discuss(request(recordId=self.record, text="Missing AI"))["job"])
        self.assertEqual(waiting["status"], "waiting")
        self.assertFalse(list(self.service.jobs_dir.iterdir()))
        self.service.callbacks["before_execute"] = lambda action, project: False
        resource = self.wait(self.service.submit(request(recordId=self.record, text="Low memory", action="command", commandId="preview"))["job"])
        self.assertEqual(resource["status"], "waiting")
        self.assertFalse(resource["resultAttachmentIds"])

    def test_command_authorization_revoked_or_changed_during_resource_gate_never_starts(self):
        marker = self.project / "executed-marker.txt"
        self.command.write_text("from pathlib import Path\nPath('executed-marker.txt').write_text('executed')\n" + SCRIPT, encoding="utf-8")
        changes = ({"capabilities": ["capture_screen", "result_import"], "commands": []},
                   {"commands": [{"id": "preview", "argv": [sys.executable, str(self.command), "changed"]}]},
                   {"root": str(self.root)})
        self.service.start()
        for change in changes:
            with self.subTest(change=change):
                self.service.configure_projects(self.projects)
                def revoke(action, project):
                    self.service.configure_projects({"project": {"id": "console", **change}})
                    return True
                self.service.callbacks["before_execute"] = revoke
                done = self.wait(self.service.submit(request(recordId=self.record, text="Revoke before spawn", action="command", commandId="preview"))["job"])
                self.assertEqual(done["status"], "failed", done)
                self.assertFalse(marker.exists())
                self.assertFalse(list(self.service.jobs_dir.rglob("result.png")))
                self.assertFalse(done["resultAttachmentIds"])

    def test_ai_plan_cannot_capture_or_import_after_capability_revocation(self):
        (self.project / "already-created.png").write_bytes(image())
        captured = []
        self.service.callbacks["capture_screen"] = lambda path: captured.append(path)
        self.service.start()
        for action, args in (("capture_screen", {}), ("result_import", {"paths": ["already-created.png"]})):
            self.service.configure_projects(self.projects)
            def revoke_plan(payload):
                self.service.configure_projects({"project": {"id": "console", "capabilities": []}})
                return {"action": action, "args": args, "text": "", "script": "", "language": "none"}
            self.models.plan = revoke_plan
            done = self.wait(self.service.submit(request(recordId=self.record, text="Revoke before result action", action="auto"))["job"])
            self.assertEqual(done["status"], "failed", done)
            self.assertFalse(done["resultAttachmentIds"])
        self.assertFalse(captured)

    def test_configured_key_environment_and_split_log_secret_never_persist(self):
        key_name, secret = "CONSOLE_WORKFLOW_FIXTURE_KEY", "synthetic-only-execution-secret"
        # The literal is synthetic so log redaction is exercised even though the
        # real configured environment value must never reach the child process.
        self.command.write_text("import os,sys\nprint('env-visible=' + str('" + key_name + "' in os.environ))\n"
                                "sys.stdout.write('synthetic-only-');sys.stdout.flush()\n"
                                "sys.stdout.write('execution-secret\\n');sys.stdout.flush()\n" + SCRIPT, encoding="utf-8")
        with patch.dict(os.environ, {key_name: secret}):
            adapter = WorkflowModels(self.root / "data" / "models", image_root=self.service.attachments_dir)
            adapter.configure({"id": "fixture", "endpoint": "http://127.0.0.1:9/v1", "model": "synthetic", "keyEnv": key_name})
            self.service.models = adapter
            self.service.start()
            done = self.wait(self.service.submit(request(recordId=self.record, text="Private output fixture", action="command", commandId="preview"))["job"])
            self.assertEqual(done["status"], "succeeded", done)
            self.assertIn("env-visible=False", done["log"])
            self.assertIn("[model-key-redacted]", done["log"])
            self.assertNotIn(secret, json.dumps(self.service.detail(self.record)))
            saved = (self.service.jobs_dir / done["id"] / "execution.log").read_text(encoding="utf-8")
            self.assertNotIn(secret, saved)
            self.assertIn("[model-key-redacted]", saved)

    def test_upload_idempotency_and_revoke_rollback_keep_existing_files(self):
        payload = request(recordId=self.record)
        uploaded = self.upload(fields=payload)
        repeated = self.upload(fields=payload)
        self.assertEqual(uploaded["uploadedAttachmentIds"], repeated["uploadedAttachmentIds"])
        self.assertEqual(len(repeated["attachments"]), 1)
        calls = []
        def revoked():
            calls.append(True)
            if len(calls) == 2:
                raise WorkflowError("revoked", 401)
        with self.assertRaises(WorkflowError):
            self.upload(authorize=revoked)
        self.assertEqual(len(self.service.detail(self.record)["attachments"]), 1)
        self.assertEqual(len(list(self.service.attachments_dir.glob("*.png"))), 1)
        calls.clear()
        with self.assertRaises(WorkflowError):
            self.service.submit(request(recordId=self.record, text="Rejected auth", action="command", commandId="preview"), authorize=revoked)

    def test_permissions_paths_manifest_boundaries_and_project_upsert(self):
        before = self.service.config()
        self.assertFalse(self.service.background_enabled)
        self.assertNotIn("root", before["projects"][0])
        self.service.configure_projects({"project": {"id": "console", "name": "Renamed"}})
        with self.service._db() as db:
            project = self.service._project(db, "console")
        configured_command = self.projects[0]["commands"][0]
        self.assertEqual(project["commands"], [{**configured_command,
            "argv": [str(Path(configured_command["argv"][0]).resolve()), *configured_command["argv"][1:]], "timeout": 5}])
        self.assertTrue(project["scriptRunners"])
        for payload in (request(recordId=self.record, text="bad", projectId="unity", action="command", commandId="preview"),
                        request(recordId=self.record, text="bad", action="command", commandId="unapproved"),
                        request(recordId=self.record, text="bad", computerId="wrong", action="command", commandId="preview")):
            with self.assertRaises(WorkflowError):
                self.service.submit(payload)
        self.command.write_text("import os,json\nfrom pathlib import Path\nPath(os.environ['CONSOLE_WORKFLOW_RESULT_MANIFEST']).write_text(json.dumps({'text':'bad','files':['../outside.png']}))\n", encoding="utf-8")
        self.service.models = None
        self.service.start()
        escaped = self.wait(self.service.submit(request(recordId=self.record, text="No escape", action="command", commandId="preview"))["job"])
        self.assertEqual(escaped["status"], "failed")
        self.assertFalse(escaped["resultAttachmentIds"])
        self.service.configure_background(True)
        self.assertTrue(self.service.background_enabled)

    def test_transcription_is_durable_text_only_and_independent_of_discussion_ready(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(8000)
            output.writeframes(b"\0\0" * 100)
        uploaded = self.upload(audio.getvalue(), "voice.wav", "audio/wav")
        self.models.ready = False
        self.service.start()
        job = self.service.transcribe(request(recordId=self.record, attachmentId=uploaded["uploadedAttachmentIds"][0]))["job"]
        done = self.wait(job)
        self.assertEqual(done["status"], "succeeded", done)
        self.assertIn("Recorded review", done["result"]["text"])
        self.assertEqual(self.service.detail(self.record)["messages"][-1]["role"], "transcript")
        self.assertFalse(list(self.service.jobs_dir.iterdir()))

    def test_capture_and_result_import_work_without_model_configuration(self):
        self.service.models = None
        def capture(path):
            path.write_bytes(image())
            return path
        self.service.callbacks["capture_screen"] = capture
        self.service.start()
        captured = self.wait(self.service.submit(request(recordId=self.record, text="Capture fixture", action="capture_screen"))["job"])
        self.assertEqual(captured["status"], "succeeded", captured)
        self.assertTrue(captured["resultAttachmentIds"])
        (self.project / "already-created.png").write_bytes(image())
        imported = self.wait(self.service.submit(request(recordId=self.record, text="Import real existing result", action="result_import", args={"paths": ["already-created.png"]}))["job"])
        self.assertEqual(imported["status"], "succeeded", imported)
        self.assertTrue(imported["resultAttachmentIds"])

    def test_model_request_is_real_local_http_with_image_and_private_key_redaction(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(os.environ, {"CONSOLE_WORKFLOW_FIXTURE_KEY": "synthetic-only-key"}):
                adapter = WorkflowModels(self.root / "data" / "models", image_root=self.service.attachments_dir, timeout=3)
                adapter.configure({"id": "fixture", "endpoint": "http://127.0.0.1:" + str(server.server_port) + "/v1", "model": "synthetic", "keyEnv": "CONSOLE_WORKFLOW_FIXTURE_KEY"})
                self.service.models = adapter
                self.upload()
                self.service.start()
                done = self.wait(self.service.discuss(request(recordId=self.record, text="Inspect saved image"))["job"])
                self.assertEqual(done["status"], "succeeded", done)
                self.assertIn("Local HTTP", done["result"]["text"])
                self.assertTrue(any(item.get("type") == "input_image" for message in Provider.requests[-1]["input"] for item in message.get("content", []) if isinstance(item, dict)))
                self.assertNotIn("synthetic-only-key", json.dumps(self.service.detail(self.record)))
                self.assertNotIn(str(self.root), json.dumps(Provider.requests[-1]))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_work_finished_runs_once_after_commit_and_callback_failure_preserves_results(self):
        committed_states = []
        def finished():
            with sqlite3.connect(self.service.data_dir / "workflow.sqlite3") as database:
                committed_states.append([row[0] for row in database.execute("SELECT status FROM jobs ORDER BY rowid")])
            database.close()
            raise RuntimeError("lifecycle callback failure")
        self.service.callbacks["work_finished"] = finished
        first = self.service.discuss(request(recordId=self.record, text="Successful callback fixture"))["job"]
        self.command.write_text("raise SystemExit(4)\n", encoding="utf-8")
        second = self.service.submit(request(recordId=self.record, text="Failure callback fixture", action="command", commandId="preview"))["job"]
        self.service.start()
        self.assertEqual(self.wait(first)["status"], "succeeded")
        self.assertEqual(self.wait(second)["status"], "failed")
        until = time.monotonic() + 2
        while len(committed_states) < 2 and time.monotonic() < until:
            time.sleep(0.01)
        self.assertEqual(committed_states, [["succeeded", "queued"], ["succeeded", "failed"]])
        time.sleep(1.05)
        self.assertEqual(len(committed_states), 2, "idle worker must not repeat lifecycle callbacks")


if __name__ == "__main__":
    unittest.main(verbosity=2)
