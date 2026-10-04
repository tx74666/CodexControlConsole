"""Disposable App-plan/confirmed fixed-action checks; no App or model requests."""
from copy import deepcopy
import hashlib
import io
import json
import os
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
from workflow_models import WorkflowModels
from workflow_script_proposals import action_blocks
from workflow_service import WorkflowError, WorkflowService


def request(**fields):
    return {"requestId": str(uuid.uuid4()), **fields}


def proposal(action="command", **fields):
    value = {"version": 1, "label": "One selected option", "instruction": "Run this reviewed task", "action": action}
    if action == "command":
        value["commandId"] = "preview"
    if action == "result_import":
        value["args"] = {"paths": ["existing.png"]}
    return {**value, **fields}


def fence(value):
    return "```console-action\n" + json.dumps(value, ensure_ascii=False) + "\n```\n"


COMMAND = """import json, os
from pathlib import Path
from PIL import Image
inputs = json.loads(Path(os.environ['CONSOLE_WORKFLOW_INPUT_FILE']).read_text(encoding='utf-8'))
assert len(inputs['images']) == 1
assert Image.open(inputs['images'][0]['path']).getpixel((0, 0)) == (0, 0, 255)
output = Path(os.environ['CONSOLE_WORKFLOW_OUTPUT_DIR'])
Image.new('RGB', (32, 20), 'green').save(output / 'actual.png')
marker = Path('command-execution-count.txt')
marker.write_text(str(int(marker.read_text()) + 1) if marker.exists() else '1')
Path(os.environ['CONSOLE_WORKFLOW_RESULT_MANIFEST']).write_text(json.dumps({'text':'Actually executed the selected fixed command','files':['actual.png']}), encoding='utf-8')
print('actual fixed command')
"""


class NoRemoteModels(WorkflowModels):
    def _post(self, *_args, **_kwargs):
        raise AssertionError("App proposals must not call model services")

    def plan(self, *_args, **_kwargs):
        raise AssertionError("App proposals must not ask a model to plan")

    def discuss(self, *_args, **_kwargs):
        raise AssertionError("App proposals must not ask a model to discuss")

    def transcribe(self, *_args, **_kwargs):
        raise AssertionError("App proposals must not ask a model to transcribe")


class ActionFenceChecks(unittest.TestCase):
    def test_only_complete_exact_protocol_creates_one_independent_option(self):
        first = proposal()
        second = proposal("capture_screen", label="Second")
        blocks = action_blocks("Prose\n```json\n" + json.dumps(first) + "\n```\n" + fence(first) + fence(second))
        self.assertEqual([item["blockIndex"] for item in blocks], [0, 1])
        self.assertEqual([item["action"] for item in blocks], ["command", "capture_screen"])
        digest = hashlib.sha256(json.dumps(first, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(blocks[0]["actionSha256"], digest)
        self.assertEqual(action_blocks("```console-action\n" + json.dumps(first)), [])
        self.assertEqual(action_blocks("````text\n" + fence(first) + "````\n"), [])

    def test_arbitrary_code_argv_parameters_duplicates_and_invalid_types_are_rejected(self):
        valid = proposal()
        cases = [{**valid, "version": True}, {**valid, "action": []}, {**valid, "action": "generated_script"},
                 {**valid, "argv": ["anything"]}, {**valid, "root": "D:/"}, {**valid, "timeout": 1},
                 {**valid, "label": ""}, {**valid, "instruction": ""}, {**valid, "commandId": "wrong id"},
                 proposal("capture_screen", args={}), proposal("command", args={}),
                 proposal("result_import", args={"paths": []}), proposal("result_import", args={"paths": [1]}),
                 proposal("result_import", args={"paths": ["../escape.png"]}),
                 proposal("result_import", args={"paths": ["C:\\private.png"]}),
                 proposal("result_import", args={"paths": ["/private.png"]}),
                 proposal("result_import", args={"paths": ["image.py"]}),
                 proposal("result_import", args={"paths": ["nested\\..\\escape.png"]})]
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(action_blocks(fence(value)), [])
        duplicate = json.dumps(valid)[:-1] + ',"commandId":"other"}'
        self.assertEqual(action_blocks("```console-action\n" + duplicate + "\n```"), [])
        self.assertEqual(action_blocks("```console-action\n{bad}\n```"), [])

    def test_invalid_fence_keeps_later_block_identity_and_relative_paths(self):
        blocks = action_blocks(fence({"invalid": True}) + fence(proposal("result_import", args={"paths": ["nested\\image.PNG"]})))
        self.assertEqual(blocks[0]["blockIndex"], 1)
        self.assertEqual(blocks[0]["args"]["paths"], ["nested\\image.PNG"])


class ConfirmedAppActionChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="console-app-action-check-")
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.script = self.project / "fixed-preview.py"
        self.script.write_text(COMMAND, encoding="utf-8")
        self.other_script = self.project / "unselected.py"
        self.other_script.write_text("from pathlib import Path\nPath('WRONG-OPTION-RAN').write_text('wrong')\n", encoding="utf-8")
        Image.new("RGB", (24, 18), "yellow").save(self.project / "existing.png")
        self.models = NoRemoteModels(self.root / "private")
        self.projects = [{"id": "fixture", "name": "Isolated authorized fixed commands", "root": str(self.project),
            "capabilities": ["capture_screen", "command", "result_import"], "allowGeneratedScripts": False,
            "commands": [{"id": "preview", "name": "Configured preview", "argv": [sys.executable, str(self.script)], "timeout": 5},
                         {"id": "other", "name": "Unselected", "argv": [sys.executable, str(self.other_script)], "timeout": 5}],
            "scriptRunners": {}, "timeout": 5}]
        self.capture_count = 0
        def capture(path):
            self.capture_count += 1
            Image.new("RGB", (28, 16), "red").save(path)
            return path
        self.service = WorkflowService(self.root / "private", models=self.models, projects=self.projects, callbacks={"capture_screen": capture})
        self.record = self.service.create(request(projectId="fixture", text="Original opinion"))["record"]["id"]
        self.image = self.upload()
        self.thread_id = str(uuid.uuid4())

    def tearDown(self):
        self.service.shutdown()
        self.temporary.cleanup()

    def upload(self, color="blue"):
        stream = io.BytesIO()
        Image.new("RGB", (24, 18), color).save(stream, "PNG")
        data = stream.getvalue()
        spool = self.root / (uuid.uuid4().hex + ".spool")
        spool.write_bytes(data)
        return self.service.upload(request(recordId=self.record), [IncomingFile(spool, 0, len(data), "original.png", "image/png")])["uploadedAttachmentIds"][0]

    def complete(self, text=None, **fields):
        body = request(recordId=self.record, text="Prepare options; do not run",
            context={"attachmentIds": [self.image]}, appTarget={"kind": "codex", "mode": "new", "name": "Fixture App planning"}, **fields)
        job = self.service.discuss(body)["job"]
        dispatch = self.service.incubator_claim(request())["dispatch"]
        self.service.incubator_attach_result(request(id=dispatch["id"], claimToken=dispatch["claimToken"], status="completed",
            targetThreadId=self.thread_id, result={"text": text or fence(proposal()), "turnId": "exact-turn-" + job["id"],
                                                 "sourceMessageId": "exact-user-" + job["id"]}))
        message = next(item for item in reversed(self.service.detail(self.record)["messages"]) if item["role"] == "assistant")
        return message, job, dispatch

    def body(self, value, **fields):
        return request(recordId=self.record, projectId=value["projectId"], text=value["instruction"],
            context={"sourceMessageId": value["sourceMessageId"], "attachmentIds": value["attachmentIds"]},
            actionProposal={key: value[key] for key in ("sourceMessageId", "blockIndex", "actionSha256", "executionAuthorizationSha256")}, **fields)

    def error(self, operation, code=None):
        with self.assertRaises(WorkflowError) as caught:
            operation()
        if code:
            self.assertEqual(caught.exception.code, code)

    def wait(self, job):
        until = time.monotonic() + 12
        while time.monotonic() < until:
            current = next(item for item in self.service.detail(job["recordId"])["jobs"] if item["id"] == job["id"])
            if current["status"] not in {"queued", "running"}:
                return current
            time.sleep(.025)
        self.fail("isolated action worker did not finish")

    def execute(self, value):
        job = self.service.submit(self.body(value))["job"]
        with patch.object(self.service, "_require_model", side_effect=AssertionError("No model needed")):
            self.service.start()
            return self.wait(job)

    def test_new_discussion_and_execution_plan_freeze_catalog_without_executing(self):
        for purpose in ("discussion", "execution_plan"):
            message, job, dispatch = self.complete(purpose=purpose)
            self.assertEqual(job["kind"], "discuss")
            self.assertEqual(job["purpose"], purpose)
            self.assertEqual(job["status"], "waiting")
            value = message["actionProposals"][0]
            self.assertTrue(value["executable"], value)
            self.assertFalse(self.service.has_pending_jobs())
            private = next(item for item in self.service.incubator_dispatches(private=True)["dispatches"] if item["id"] == dispatch["id"])
            self.assertIn("console-action", private["prompt"])
            self.assertIn("allowedActions", private["prompt"])
            self.assertIn('"id":"preview","name":"Configured preview"', private["prompt"])
            self.assertNotIn(str(self.script), private["prompt"])
            self.assertNotIn(str(self.project), private["prompt"])
            self.assertIn("禁止执行修改", private["prompt"])
            self.assertIn("另行", private["prompt"])
            self.assertFalse((self.project / "command-execution-count.txt").exists())
            self.assertEqual(value["executionAuthorization"], {"projectId": "fixture", "projectName": self.projects[0]["name"],
                "root": str(self.project.resolve()), "action": "command", "capabilityGranted": True,
                "commandId": "preview", "argv": [str(Path(sys.executable).resolve()), str(self.script)], "timeout": 5})

    def test_executable_is_canonical_but_fixed_argument_alias_is_preserved_and_runs_once(self):
        alias_directory = self.project / "aliasdir"
        alias_directory.mkdir()
        original_argument = str(alias_directory / ".." / self.script.name)
        self.assertNotEqual(original_argument, str(Path(original_argument).resolve()))
        command = {**self.projects[0]["commands"][0], "argv": [sys.executable, original_argument]}
        self.service.configure_projects({"project": {**self.projects[0], "commands": [command]}})
        message, _, _ = self.complete()
        value = message["actionProposals"][0]
        # Only argv[0] is an executable path. Fixed arguments are exact reviewed
        # strings, including valid directory aliases; canonicalizing them would
        # change the command authorization and can change non-path arguments.
        self.assertEqual(value["executionAuthorization"], {"projectId": "fixture", "projectName": self.projects[0]["name"],
            "root": str(self.project.resolve()), "action": "command", "capabilityGranted": True,
            "commandId": "preview", "argv": [str(Path(sys.executable).resolve()), original_argument], "timeout": 5})
        done = self.execute(value)
        self.assertEqual(done["status"], "succeeded", done)
        self.assertEqual((self.project / "command-execution-count.txt").read_text(), "1")
        actual = self.service.attachment("id=" + done["resultAttachmentIds"][0])
        self.assertEqual(Image.open(actual["path"]).getpixel((0, 0)), (0, 128, 0))

    def test_app_multioption_only_confirmed_command_runs_actual_png_same_record(self):
        message, _, _ = self.complete(fence(proposal(commandId="other")) + fence(proposal()) + fence(proposal("capture_screen")))
        self.assertEqual(len(message["actionProposals"]), 3)
        self.assertFalse(self.models.config()["ready"])
        done = self.execute(message["actionProposals"][1])
        self.assertEqual(done["status"], "succeeded", done)
        self.assertEqual(done["action"], "command")
        self.assertIn("actual fixed command", done["log"])
        self.assertEqual((self.project / "command-execution-count.txt").read_text(), "1")
        self.assertFalse((self.project / "WRONG-OPTION-RAN").exists())
        self.assertEqual(self.capture_count, 0)
        result = self.service.attachment("id=" + done["resultAttachmentIds"][0])
        self.assertEqual(Image.open(result["path"]).getpixel((0, 0)), (0, 128, 0))
        self.assertEqual(self.service.detail(self.record)["record"]["primaryAttachmentId"], done["result"]["primaryAttachmentId"])
        self.assertEqual(done["actionProposal"]["sourceMessageId"], message["id"])
        for private in ("appAction", "commandAuthorization", str(self.project), str(self.script)):
            self.assertNotIn(private, json.dumps(done))

    def test_capture_and_project_import_use_bound_selection_and_return_actual_images(self):
        for action, pixel in (("capture_screen", (255, 0, 0)), ("result_import", (255, 255, 0))):
            message, _, _ = self.complete(fence(proposal(action)))
            done = self.execute(message["actionProposals"][0])
            self.assertEqual(done["status"], "succeeded", done)
            self.assertEqual(done["action"], action)
            actual = self.service.attachment("id=" + done["resultAttachmentIds"][0])
            self.assertEqual(Image.open(actual["path"]).getpixel((0, 0)), pixel)
        self.assertEqual(self.capture_count, 1)

    def test_new_images_and_edited_instruction_do_not_retarget_original_app_context(self):
        message, _, _ = self.complete()
        value = message["actionProposals"][0]
        newer = self.upload("red")
        body = self.body(value)
        body["text"] = "Explicitly edited review instruction"
        done = self.service.submit(body)["job"]
        self.service.start()
        done = self.wait(done)
        self.assertEqual(done["status"], "succeeded", done)
        inputs = json.loads((self.service.jobs_dir / done["id"] / "input.json").read_text(encoding="utf-8"))
        self.assertIn(self.image, inputs["images"][0]["path"])
        self.assertNotIn(newer, json.dumps(inputs))
        self.assertEqual(inputs["context"][0]["content"], message["text"])
        self.assertEqual(inputs["text"], body["text"])

    def test_no_arbitrary_args_or_unbound_context_can_override_reviewed_reference(self):
        message, _, _ = self.complete()
        value = message["actionProposals"][0]
        for key, supplied in (("action", "command"), ("args", {}), ("commandId", "other"),
                              ("scriptProposal", {}), ("attachmentId", self.image), ("script", "print(1)")):
            body = self.body(value)
            body[key] = supplied
            self.error(lambda: self.service.submit(body))
        for context in ({"sourceMessageId": message["id"], "attachmentIds": []},
                        {"sourceMessageId": message["id"], "attachmentIds": [self.image], "selectedText": "Extra"},
                        {"sourceMessageId": message["id"], "attachmentIds": [self.image], "referenceIds": ["private"]}):
            body = self.body(value)
            body["context"] = context
            self.error(lambda: self.service.submit(body), "action_context_mismatch")
        body = self.body(value)
        body["actionProposal"]["blockIndex"] = True
        self.error(lambda: self.service.submit(body), "action_reference_invalid")
        body = self.body(value)
        body["actionProposal"]["actionSha256"] = "0" * 64
        self.error(lambda: self.service.submit(body), "action_source_changed")
        body = self.body(value)
        body["actionProposal"]["executionAuthorizationSha256"] = "0" * 64
        self.error(lambda: self.service.submit(body), "permission_changed")

    def test_old_plain_api_and_incomplete_sources_do_not_gain_execution_authority(self):
        with self.service._db() as db:
            unrelated = self.service._message(db, self.record, "assistant", fence(proposal()))
        self.assertEqual(next(item for item in self.service.detail(self.record)["messages"] if item["id"] == unrelated)["actionProposals"], [])
        message, job, dispatch = self.complete()
        value = message["actionProposals"][0]
        with self.service._db() as db:
            payload = json.loads(db.execute("SELECT payload FROM jobs WHERE id=?", (job["id"],)).fetchone()["payload"])
            payload["appFrozen"].pop("actionPlanning")
            db.execute("UPDATE jobs SET payload=? WHERE id=?", (json.dumps(payload), job["id"]))
        self.assertEqual(next(item for item in self.service.detail(self.record)["messages"] if item["id"] == message["id"])["actionProposals"], [])
        self.error(lambda: self.service.submit(self.body(value)), "action_source_invalid")
        with self.service._db() as db:
            db.execute("UPDATE jobs SET status='waiting' WHERE id=?", (job["id"],))
        self.error(lambda: self.service.submit(self.body(value)), "action_source_invalid")

    def test_wrong_record_project_or_ambiguous_result_never_dispatches(self):
        message, job, dispatch = self.complete()
        value = message["actionProposals"][0]
        another = self.service.create(request(projectId="fixture", text="Other record"))["record"]["id"]
        body = self.body(value)
        body["recordId"] = another
        self.error(lambda: self.service.submit(body))
        other_root = self.root / "other-project"
        other_root.mkdir()
        self.service.configure_projects({"project": {**self.projects[0], "id": "other", "root": str(other_root)}})
        body = self.body(value)
        body["projectId"] = "other"
        self.error(lambda: self.service.submit(body), "action_project_mismatch")
        with self.service._db() as db:
            row = dict(db.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone())
            row.update(id=uuid.uuid4().hex, request_id=str(uuid.uuid4()))
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", tuple(row.values()))
        self.assertEqual(next(item for item in self.service.detail(self.record)["messages"] if item["id"] == message["id"])["actionProposals"], [])
        self.error(lambda: self.service.submit(self.body(value)), "action_source_invalid")

    def test_original_catalog_not_live_new_command_or_capability_defines_scope(self):
        self.service.configure_projects({"project": {**self.projects[0], "capabilities": ["capture_screen"], "commands": []}})
        message, _, _ = self.complete(fence(proposal()) + fence(proposal("result_import")))
        self.assertTrue(all(not item["executable"] for item in message["actionProposals"]))
        self.service.configure_projects({"project": self.projects[0]})
        for item in next(item for item in self.service.detail(self.record)["messages"] if item["id"] == message["id"])["actionProposals"]:
            self.assertFalse(item["executable"])
            self.error(lambda: self.service.submit(self.body(item)), "permission_changed")
        self.assertFalse((self.project / "command-execution-count.txt").exists())

    def test_catalog_provenance_and_actual_app_turn_text_mismatches_are_rejected(self):
        message, job, dispatch = self.complete()
        value = message["actionProposals"][0]
        with self.service._db() as db:
            old = dict(db.execute("SELECT * FROM idea_dispatches WHERE id=?", (dispatch["id"],)).fetchone())
        for column, new in (("result", json.dumps({**json.loads(old["result"]), "turnId": "wrong"})),
                            ("snapshot", json.dumps({**json.loads(old["snapshot"]), "actionPlanningSha256": "0" * 64})),
                            ("status", "waiting")):
            with self.subTest(column=column):
                with self.service._db() as db:
                    db.execute(f"UPDATE idea_dispatches SET {column}=? WHERE id=?", (new, dispatch["id"]))
                self.error(lambda: self.service.submit(self.body(value)), "action_source_invalid")
                with self.service._db() as db:
                    db.execute(f"UPDATE idea_dispatches SET {column}=? WHERE id=?", (old[column], dispatch["id"]))

    def test_command_root_argv_timeout_and_permission_changes_block_old_review(self):
        message, _, _ = self.complete()
        value = message["actionProposals"][0]
        other_root = self.root / "moved-project"
        other_root.mkdir()
        changes = [{"root": str(other_root)}, {"capabilities": ["capture_screen", "result_import"]},
            {"commands": [{**self.projects[0]["commands"][0], "timeout": 6}]},
            {"commands": [{**self.projects[0]["commands"][0], "argv": [sys.executable, str(self.other_script)]}]}]
        for change in changes:
            with self.subTest(change=change):
                self.service.configure_projects({"project": {**self.projects[0], **change}})
                unavailable = next(item for item in self.service.detail(self.record)["messages"] if item["id"] == message["id"])["actionProposals"][0]
                self.assertFalse(unavailable["executable"])
                self.error(lambda: self.service.submit(self.body(value)), "permission_changed")
                self.service.configure_projects({"project": self.projects[0]})

    def test_worker_start_and_immediately_before_spawn_recheck_frozen_grant(self):
        message, _, _ = self.complete()
        job = self.service.submit(self.body(message["actionProposals"][0]))["job"]
        changed = {**self.projects[0], "commands": [{**self.projects[0]["commands"][0], "timeout": 6}]}
        self.service.configure_projects({"project": changed})
        self.service.start()
        done = self.wait(job)
        self.assertEqual(done["status"], "failed", done)
        self.assertFalse((self.project / "command-execution-count.txt").exists())
        self.error(lambda: self.service.retry(request(jobId=job["id"])), "permission_changed")
        self.service.configure_projects({"project": self.projects[0]})
        def revoke(_action, _project):
            self.service.configure_projects({"project": changed})
            return True
        self.service.callbacks["before_execute"] = revoke
        done = self.wait(self.service.retry(request(jobId=job["id"]))["job"])
        self.assertEqual(done["status"], "failed", done)
        self.assertFalse((self.project / "command-execution-count.txt").exists())

    def test_original_image_changed_blocks_acceptance_and_worker_and_retry(self):
        message, _, _ = self.complete()
        value = message["actionProposals"][0]
        path = self.service.attachment("id=" + self.image)["path"]
        original = path.read_bytes()
        modified = original[:-1] + bytes([original[-1] ^ 1])
        path.write_bytes(modified)
        self.error(lambda: self.service.submit(self.body(value)), "context_changed")
        path.write_bytes(original)
        job = self.service.submit(self.body(value))["job"]
        path.write_bytes(modified)
        self.service.start()
        done = self.wait(job)
        self.assertEqual(done["status"], "failed", done)
        self.error(lambda: self.service.retry(request(jobId=job["id"])), "context_changed")
        self.assertFalse((self.project / "command-execution-count.txt").exists())

    def test_lost_response_uuid_dedup_executes_once_and_changed_body_conflicts(self):
        message, _, _ = self.complete()
        body = self.body(message["actionProposals"][0])
        first = self.service.submit(body)["job"]
        self.assertEqual(self.service.submit(deepcopy(body))["job"]["id"], first["id"])
        self.error(lambda: self.service.submit({**body, "text": "different under same UUID"}))
        self.service.start()
        self.assertEqual(self.wait(first)["status"], "succeeded")
        self.assertEqual(self.service.submit(body)["job"]["id"], first["id"])
        self.assertEqual((self.project / "command-execution-count.txt").read_text(), "1")

    def test_explicit_retry_keeps_one_selection_without_new_app_or_new_image(self):
        message, _, _ = self.complete()
        self.service.callbacks["before_execute"] = lambda *_: False
        done = self.execute(message["actionProposals"][0])
        self.assertEqual(done["status"], "waiting", done)
        self.upload("red")
        self.service.callbacks.pop("before_execute")
        body = request(jobId=done["id"])
        retried = self.service.retry(body)["job"]
        self.assertEqual(self.service.retry(body)["job"]["id"], retried["id"])
        result = self.wait(retried)
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(result["attempt"], 2)
        self.assertEqual(result["parentJobId"], done["id"])
        self.assertEqual(len(self.service.incubator_dispatches()["dispatches"]), 1)

    def test_restart_no_replay_and_explicit_retry_uses_frozen_action(self):
        message, _, _ = self.complete()
        job = self.service.submit(self.body(message["actionProposals"][0]))["job"]
        with self.service._db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job["id"],))
        self.service = WorkflowService(self.root / "private", models=self.models)
        self.service.start()
        self.assertEqual(self.wait(job)["status"], "interrupted")
        self.assertFalse((self.project / "command-execution-count.txt").exists())
        retry = self.service.retry(request(jobId=job["id"]))["job"]
        self.assertEqual(self.wait(retry)["status"], "succeeded")
        self.service.shutdown()
        self.service = WorkflowService(self.root / "private", models=self.models)
        self.service.start()
        self.assertEqual(self.wait(retry)["status"], "succeeded")
        self.assertEqual((self.project / "command-execution-count.txt").read_text(), "1")

    def test_missing_empty_invalid_or_escaping_manifest_never_claims_success(self):
        for contents in (None, "{}", '{"files":[]}', '{"text":"","files":[]}', "{bad", '{"text":"bad","files":["../escape.png"]}'):
            with self.subTest(contents=contents):
                script = "print('no usable result')\n" if contents is None else (
                    "import os\nfrom pathlib import Path\nPath(os.environ['CONSOLE_WORKFLOW_RESULT_MANIFEST']).write_text(" + repr(contents) + ")\n")
                self.script.write_text(script, encoding="utf-8")
                message, _, _ = self.complete()
                done = self.execute(message["actionProposals"][0])
                self.assertEqual(done["status"], "failed", done)
                self.assertEqual(done["resultAttachmentIds"], [])

    def test_no_models_adapter_and_local_custom_key_filter_remain_supported(self):
        key_name, secret = "CONSOLE_CUSTOM_ACTION_CREDENTIAL", "private-synthetic-action-value"
        self.script.write_text("import os\nassert '" + key_name + "' not in os.environ\nprint('" + secret + "')\n" + COMMAND, encoding="utf-8")
        message, _, _ = self.complete()
        with patch.dict(os.environ, {key_name: secret}):
            self.models.configure({"id": "unused", "endpoint": "http://127.0.0.1:9/v1", "model": "unused", "keyEnv": key_name})
            done = self.execute(message["actionProposals"][0])
        self.assertEqual(done["status"], "succeeded", done)
        self.assertNotIn(secret, done["log"])
        self.assertIn("[model-key-redacted]", done["log"])
        self.service.models = None
        self.script.write_text(COMMAND, encoding="utf-8")
        message, _, _ = self.complete()
        self.assertEqual(self.execute(message["actionProposals"][0])["status"], "succeeded")

    def test_ordinary_command_freezes_acceptance_start_spawn_and_retry(self):
        job = self.service.submit(request(recordId=self.record, text="Ordinary command", action="command", commandId="preview", context={"attachmentIds": [self.image]}))["job"]
        changed = {**self.projects[0], "commands": [{**self.projects[0]["commands"][0], "argv": [sys.executable, str(self.other_script)]}]}
        self.service.configure_projects({"project": changed})
        self.service.start()
        done = self.wait(job)
        self.assertEqual(done["status"], "failed", done)
        self.error(lambda: self.service.retry(request(jobId=job["id"])), "permission_changed")
        self.assertFalse((self.project / "WRONG-OPTION-RAN").exists())
        self.service.configure_projects({"project": self.projects[0]})
        self.service.callbacks["before_execute"] = lambda *_: (self.service.configure_projects({"project": changed}) and True)
        done = self.wait(self.service.retry(request(jobId=job["id"]))["job"])
        self.assertEqual(done["status"], "failed", done)
        self.assertFalse((self.project / "WRONG-OPTION-RAN").exists())

    def test_legacy_unfrozen_command_refuses_replay_but_can_be_newly_reviewed(self):
        body = request(recordId=self.record, text="Original command", action="command", commandId="preview", context={"attachmentIds": [self.image]})
        job = self.service.submit(body)["job"]
        with self.service._db() as db:
            payload = json.loads(db.execute("SELECT payload FROM jobs WHERE id=?", (job["id"],)).fetchone()["payload"])
            payload.pop("commandAuthorization")
            payload.pop("commandAuthorizationSha256")
            db.execute("UPDATE jobs SET payload=? WHERE id=?", (json.dumps(payload), job["id"]))
        self.service.start()
        done = self.wait(job)
        self.assertEqual(done["status"], "failed", done)
        self.assertIn("重新审核并提交", done["error"])
        self.error(lambda: self.service.retry(request(jobId=job["id"])), "permission_changed")
        fresh = self.service.submit({**body, "requestId": str(uuid.uuid4()), "text": "Explicit freshly reviewed task"})["job"]
        self.assertEqual(self.wait(fresh)["status"], "succeeded")
        self.assertEqual((self.project / "command-execution-count.txt").read_text(), "1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
