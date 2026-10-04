"""Disposable reviewed App script checks; no App sends or model network calls."""
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
from workflow_script_proposals import script_blocks
from workflow_service import WorkflowError, WorkflowService


def request(**fields):
    return {"requestId": str(uuid.uuid4()), **fields}


SCRIPT = """import json, os
from pathlib import Path
from PIL import Image
inputs = json.loads(Path(os.environ['CONSOLE_WORKFLOW_INPUT_FILE']).read_text(encoding='utf-8'))
output = Path(os.environ['CONSOLE_WORKFLOW_OUTPUT_DIR'])
assert len(inputs['images']) == 1
assert Image.open(inputs['images'][0]['path']).getpixel((0, 0)) == (0, 0, 255)
Image.new('RGB', (32, 20), 'green').save(output / 'result.png')
Path('selected-script-ran.txt').write_text(inputs['text'], encoding='utf-8')
Path(os.environ['CONSOLE_WORKFLOW_RESULT_MANIFEST']).write_text(json.dumps({'text': 'Actual reviewed script result', 'files': ['result.png']}), encoding='utf-8')
print('selected script actually executed')
"""


class NoRemoteModels(WorkflowModels):
    def _post(self, *_args, **_kwargs):
        raise AssertionError("Reviewed App scripts must never request a model service")

    def plan(self, *_args, **_kwargs):
        raise AssertionError("Reviewed App scripts must never ask a model to plan")

    def discuss(self, *_args, **_kwargs):
        raise AssertionError("Reviewed App scripts must never ask a model to discuss")

    def transcribe(self, *_args, **_kwargs):
        raise AssertionError("Reviewed App scripts must never ask a model to transcribe")


class ScriptFenceChecks(unittest.TestCase):
    def test_only_balanced_named_fences_are_proposals(self):
        text = "Prose\n```js\nprint('ignored')\n```\n```python\nprint('chosen')\n```\n```powershell\nWrite-Output 'second'\n```\n"
        self.assertEqual([(item['blockIndex'], item['language']) for item in script_blocks(text)],
                         [(0, 'python'), (1, 'powershell')])

    def test_truncated_fence_and_empty_code_are_not_executable(self):
        self.assertEqual(script_blocks("```python\nprint('unfinished')"), [])
        self.assertEqual(script_blocks("```python\n  \n```"), [])

    def test_fence_inside_other_language_does_not_escape_outer_block(self):
        self.assertEqual(script_blocks("````text\n```python\nprint('nested')\n```\n````"), [])

    def test_long_fence_closer_rules_preserve_embedded_backticks(self):
        code = "s = '''\n```\n'''\n"
        self.assertEqual(script_blocks("````python\n" + code + "````\n")[0]['code'], code)
        self.assertEqual(script_blocks("````python\nprint(1)\n```\n"), [])

    def test_exact_utf8_crlf_bytes_and_sha_are_preserved(self):
        code = "print('中文')\r\n"
        block = script_blocks("~~~python\r\n" + code + "~~~\r\n")[0]
        self.assertEqual(block['code'], code)
        self.assertEqual(block['codeSha256'], hashlib.sha256(code.encode('utf-8')).hexdigest())

    def test_inline_and_indented_code_do_not_create_proposals(self):
        self.assertEqual(script_blocks("Here is `python print(1)`\n    ```python\n    print(1)\n    ```\n"), [])


class ReviewedAppScriptChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="console-app-script-check-")
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.models = NoRemoteModels(self.root / "private")
        self.projects = [{"id": "fixture", "name": "Isolated script project", "root": str(self.project),
            "capabilities": ["generated_script", "result_import"], "allowGeneratedScripts": True,
            "scriptRunners": {"python": [sys.executable]}, "timeout": 5}]
        self.service = WorkflowService(self.root / "private", models=self.models, projects=self.projects)
        self.record = self.service.create(request(projectId="fixture", text="Original review"))["record"]["id"]
        self.image = self.upload()
        self.thread_id = str(uuid.uuid4())

    def tearDown(self):
        self.service.shutdown()
        self.temporary.cleanup()

    def upload(self, color="blue", record=None):
        stream = io.BytesIO()
        Image.new("RGB", (24, 18), color).save(stream, "PNG")
        data = stream.getvalue()
        spool = self.root / (uuid.uuid4().hex + ".spool")
        spool.write_bytes(data)
        uploaded = self.service.upload(request(recordId=record or self.record),
            [IncomingFile(spool, 0, len(data), "selected.png", "image/png")])
        return uploaded["uploadedAttachmentIds"][0]

    def complete(self, text=None, record=None, images=None):
        record = record or self.record
        text = text or "Review this chosen script:\n```python\n" + SCRIPT + "```\n"
        job = self.service.discuss(request(recordId=record, text="Suggest only; do not run",
            context={"attachmentIds": [self.image] if images is None else images},
            appTarget={"kind": "codex", "mode": "new", "name": "Fixture discussion"}))["job"]
        dispatch = self.service.incubator_claim(request())["dispatch"]
        self.service.incubator_attach_result(request(id=dispatch["id"], claimToken=dispatch["claimToken"],
            status="completed", targetThreadId=self.thread_id,
            result={"text": text, "turnId": "fixture-turn-" + job["id"], "sourceMessageId": "fixture-user-" + job["id"]}))
        detail = self.service.detail(record)
        message = next(item for item in detail["messages"] if item["role"] == "assistant")
        return message, job, dispatch

    def body(self, proposal, **fields):
        return request(recordId=self.record, projectId=proposal["projectId"], text="Run only this reviewed choice",
            action="generated_script", scriptProposal={key: proposal[key] for key in
                ("sourceMessageId", "blockIndex", "codeSha256", "executionAuthorizationSha256")}, **fields)

    def wait(self, job):
        until = time.monotonic() + 12
        while time.monotonic() < until:
            current = next(item for item in self.service.detail(job["recordId"])["jobs"] if item["id"] == job["id"])
            if current["status"] not in {"queued", "running"}:
                return current
            time.sleep(.03)
        self.fail("isolated reviewed script did not finish")

    def execute(self, proposal, **fields):
        job = self.service.submit(self.body(proposal, **fields))["job"]
        with patch.object(self.service, "_require_model", side_effect=AssertionError("No model required")):
            self.service.start()
            return self.wait(job)

    def error(self, operation, code=None):
        with self.assertRaises(WorkflowError) as caught:
            operation()
        if code:
            self.assertEqual(caught.exception.code, code)

    def test_reading_proposal_does_not_execute_and_grant_is_precise(self):
        message, _, _ = self.complete()
        proposal = message["scriptProposals"][0]
        self.assertFalse((self.project / "selected-script-ran.txt").exists())
        self.assertEqual(proposal["code"], SCRIPT)
        self.assertEqual(proposal["attachmentIds"], [self.image])
        self.assertEqual(proposal["executionAuthorization"], {"projectId": "fixture", "projectName": "Isolated script project",
            "root": str(self.project.resolve()), "language": "python", "runner": [str(Path(sys.executable).resolve())],
            "timeout": 5, "allowGeneratedScripts": True, "capabilityGranted": True})
        self.assertTrue(proposal["executable"])
        self.assertFalse(self.service.has_pending_jobs())
        self.assertEqual(len(self.service.detail(self.record)["jobs"]), 1)

    def test_new_discussion_prompt_describes_script_contract_without_execution_authority(self):
        _, _, dispatch = self.complete()
        prompt = next(item for item in self.service.incubator_dispatches(private=True)["dispatches"]
                      if item["id"] == dispatch["id"])["prompt"]
        self.assertIn("仅当用户本轮明确请求可执行脚本提案时", prompt)
        self.assertIn("CONSOLE_WORKFLOW_INPUT_FILE", prompt)
        self.assertIn("CONSOLE_WORKFLOW_OUTPUT_DIR", prompt)
        self.assertIn("CONSOLE_WORKFLOW_RESULT_MANIFEST", prompt)
        self.assertIn("禁止执行修改", prompt)
        self.assertIn("另行确认", prompt)
        self.assertFalse((self.project / "selected-script-ran.txt").exists())

    def test_real_script_without_model_config_returns_png_to_same_record(self):
        message, _, _ = self.complete()
        self.assertFalse(self.models.config()["ready"])
        done = self.execute(message["scriptProposals"][0])
        self.assertEqual(done["status"], "succeeded", done)
        self.assertIn("selected script actually executed", done["log"])
        self.assertEqual((self.project / "selected-script-ran.txt").read_text(encoding="utf-8"), "Run only this reviewed choice")
        detail = self.service.detail(self.record)
        self.assertEqual(detail["record"]["primaryAttachmentId"], done["result"]["primaryAttachmentId"])
        result = self.service.attachment("id=" + done["resultAttachmentIds"][0])
        self.assertEqual(Image.open(result["path"]).getpixel((0, 0)), (0, 128, 0))
        self.assertEqual(done["scriptProposal"]["sourceMessageId"], message["id"])
        self.assertNotIn("appScript", done)
        self.assertNotIn(str(self.project), json.dumps(done))
        self.assertNotIn(SCRIPT, json.dumps(done))

    def test_only_selected_block_runs_other_python_and_powershell_stay_unexecuted(self):
        text = ("```powershell\nWrite-Output 'unselected'\n```\n```python\n" + SCRIPT +
                "```\n```python\nraise Exception('NEVER RUN OTHER BLOCK')\n```\n")
        message, _, _ = self.complete(text)
        proposals = message["scriptProposals"]
        self.assertEqual([item["blockIndex"] for item in proposals], [0, 1, 2])
        self.assertFalse(proposals[0]["executable"])
        done = self.execute(proposals[1])
        self.assertEqual(done["status"], "succeeded", done)
        self.assertNotIn("NEVER RUN OTHER BLOCK", done["log"])
        self.assertEqual((self.service.jobs_dir / done["id"] / "task.py").read_bytes(), SCRIPT.encode("utf-8"))

    def test_edited_instruction_retains_original_images_despite_later_upload(self):
        message, _, _ = self.complete()
        proposal = message["scriptProposals"][0]
        second_image = self.upload("red")
        body = self.body(proposal)
        body["text"] = "Edited request, same reviewed code"
        job = self.service.submit(body)["job"]
        self.service.start()
        done = self.wait(job)
        self.assertEqual(done["status"], "succeeded", done)
        inputs = json.loads((self.service.jobs_dir / job["id"] / "input.json").read_text(encoding="utf-8"))
        self.assertIn(self.image, inputs["images"][0]["path"])
        self.assertNotIn(second_image, json.dumps(inputs))
        self.assertEqual(inputs["text"], body["text"])

    def test_ordinary_or_api_assistant_and_unfinished_discussion_have_no_proposals(self):
        with self.service._db() as db:
            message_id = self.service._message(db, self.record, "assistant", "```python\nprint(1)\n```")
        self.assertEqual(next(item for item in self.service.detail(self.record)["messages"] if item["id"] == message_id)["scriptProposals"], [])
        job = self.service.discuss(request(recordId=self.record, text="Still waiting", appTarget={"kind": "codex", "mode": "new"}))["job"]
        self.assertEqual(job["status"], "waiting")
        self.error(lambda: self.service.submit(request(recordId=self.record, text="Unbound", action="generated_script",
            scriptProposal={"sourceMessageId": message_id, "blockIndex": 0, "codeSha256": "0" * 64,
                            "executionAuthorizationSha256": "0" * 64})), "script_source_invalid")

    def test_cross_record_and_cross_project_references_are_rejected(self):
        message, _, _ = self.complete()
        proposal = message["scriptProposals"][0]
        other = self.service.create(request(projectId="fixture", text="Another record"))["record"]["id"]
        body = self.body(proposal)
        body["recordId"] = other
        self.error(lambda: self.service.submit(body), "script_source_invalid")
        other_project = self.root / "other-project"
        other_project.mkdir()
        self.service.configure_projects({"project": {**self.projects[0], "id": "other", "root": str(other_project)}})
        body = self.body(proposal)
        body["projectId"] = "other"
        self.error(lambda: self.service.submit(body), "script_project_mismatch")

    def test_caller_cannot_supply_code_or_extra_execution_parameters(self):
        message, _, _ = self.complete()
        proposal = message["scriptProposals"][0]
        for key, value in (("script", "print(1)"), ("args", {"paths": ["other.png"]}), ("commandId", "other")):
            body = self.body(proposal)
            body[key] = value
            self.error(lambda: self.service.submit(body))
        body = self.body(proposal)
        body["scriptProposal"]["code"] = "print(1)"
        self.error(lambda: self.service.submit(body), "script_reference_invalid")
        body = self.body(proposal)
        body["scriptProposal"]["blockIndex"] = True
        self.error(lambda: self.service.submit(body), "script_reference_invalid")

    def test_code_and_execution_authorization_sha_must_match_current_review(self):
        message, _, _ = self.complete()
        proposal = message["scriptProposals"][0]
        body = self.body(proposal)
        body["scriptProposal"]["codeSha256"] = "0" * 64
        self.error(lambda: self.service.submit(body), "script_source_changed")
        body = self.body(proposal)
        body["scriptProposal"]["executionAuthorizationSha256"] = "0" * 64
        self.error(lambda: self.service.submit(body), "permission_changed")

    def test_original_context_rejects_new_image_and_extra_selected_option(self):
        message, _, _ = self.complete()
        proposal = message["scriptProposals"][0]
        second = self.upload("red")
        for context in ({"sourceMessageId": message["id"], "attachmentIds": [second]},
                        {"sourceMessageId": message["id"], "attachmentIds": [self.image], "selectedText": "Extra text"},
                        {"sourceMessageId": message["id"], "attachmentIds": [self.image], "referenceIds": ["other"]}):
            self.error(lambda: self.service.submit(self.body(proposal, context=context)), "script_context_mismatch")

    def test_provenance_mismatch_or_ambiguous_job_never_offers_or_accepts_script(self):
        message, job, dispatch = self.complete()
        proposal = message["scriptProposals"][0]
        with self.service._db() as db:
            original_job = dict(db.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone())
            original_dispatch = dict(db.execute("SELECT * FROM idea_dispatches WHERE id=?", (dispatch["id"],)).fetchone())
        cases = [("jobs", "status", "waiting"), ("idea_dispatches", "status", "failed"),
            ("jobs", "result", json.dumps({**json.loads(original_job["result"]), "text": "Different answer"})),
            ("idea_dispatches", "result", json.dumps({**json.loads(original_dispatch["result"]), "turnId": "other-turn"})),
            ("idea_dispatches", "snapshot", json.dumps({**json.loads(original_dispatch["snapshot"]), "recordId": uuid.uuid4().hex}))]
        for table, column, value in cases:
            identifier = job["id"] if table == "jobs" else dispatch["id"]
            with self.subTest(table=table, column=column):
                with self.service._db() as db:
                    db.execute(f"UPDATE {table} SET {column}=? WHERE id=?", (value, identifier))
                self.assertEqual(next(item for item in self.service.detail(self.record)["messages"] if item["id"] == message["id"])["scriptProposals"], [])
                self.error(lambda: self.service.submit(self.body(proposal)), "script_source_invalid")
                with self.service._db() as db:
                    original = original_job if table == "jobs" else original_dispatch
                    db.execute(f"UPDATE {table} SET {column}=? WHERE id=?", (original[column], identifier))
        with self.service._db() as db:
            clone = {**original_job, "id": uuid.uuid4().hex, "request_id": str(uuid.uuid4())}
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", tuple(clone.values()))
        self.assertEqual(next(item for item in self.service.detail(self.record)["messages"] if item["id"] == message["id"])["scriptProposals"], [])
        self.error(lambda: self.service.submit(self.body(proposal)), "script_source_invalid")

    def test_root_runner_timeout_and_revocation_changes_block_old_review(self):
        message, _, _ = self.complete()
        proposal = message["scriptProposals"][0]
        other = self.root / "new-project"
        other.mkdir()
        changes = [{"root": str(other)}, {"scriptRunners": {"python": [sys.executable, "-B"]}},
                   {"timeout": 6}, {"allowGeneratedScripts": False}, {"capabilities": ["result_import"]}]
        for change in changes:
            with self.subTest(change=change):
                self.service.configure_projects({"project": {**self.projects[0], **change}})
                self.error(lambda: self.service.submit(self.body(proposal)))
                self.service.configure_projects({"project": self.projects[0]})
        self.assertFalse((self.project / "selected-script-ran.txt").exists())

    def test_queued_task_rechecks_grant_before_start_and_inside_preexecute_hook(self):
        message, _, _ = self.complete()
        job = self.service.submit(self.body(message["scriptProposals"][0]))["job"]
        self.service.configure_projects({"project": {**self.projects[0], "timeout": 6}})
        self.service.start()
        done = self.wait(job)
        self.assertEqual(done["status"], "failed", done)
        self.assertIn("授权已变更", done["error"])
        self.assertFalse((self.project / "selected-script-ran.txt").exists())
        self.service.configure_projects({"project": self.projects[0]})
        def revoke(_action, _project):
            self.service.configure_projects({"project": {**self.projects[0], "allowGeneratedScripts": False}})
            return True
        self.service.callbacks["before_execute"] = revoke
        retry = self.service.retry(request(jobId=job["id"]))["job"]
        done = self.wait(retry)
        self.assertEqual(done["status"], "failed", done)
        self.assertFalse((self.project / "selected-script-ran.txt").exists())

    def test_original_image_mutation_blocks_acceptance_and_execution(self):
        message, _, _ = self.complete()
        proposal = message["scriptProposals"][0]
        image_path = self.service.attachment("id=" + self.image)["path"]
        original = image_path.read_bytes()
        image_path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        self.error(lambda: self.service.submit(self.body(proposal)), "context_changed")
        unavailable = next(item for item in self.service.detail(self.record)["messages"] if item["id"] == message["id"])["scriptProposals"][0]
        self.assertFalse(unavailable["executable"])
        image_path.write_bytes(original)
        job = self.service.submit(self.body(proposal))["job"]
        image_path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        self.service.start()
        done = self.wait(job)
        self.assertEqual(done["status"], "failed", done)
        self.assertFalse((self.project / "selected-script-ran.txt").exists())

    def test_duplicate_request_after_lost_response_is_one_job_and_one_execution(self):
        message, _, _ = self.complete()
        body = self.body(message["scriptProposals"][0])
        first = self.service.submit(body)["job"]
        again = self.service.submit(deepcopy(body))["job"]
        self.assertEqual(first["id"], again["id"])
        self.error(lambda: self.service.submit({**body, "text": "Different request under same UUID"}))
        self.service.start()
        done = self.wait(first)
        self.assertEqual(done["status"], "succeeded", done)
        self.assertEqual(self.service.submit(body)["job"]["id"], first["id"])
        self.assertEqual(len([job for job in self.service.detail(self.record)["jobs"] if job["kind"] == "execute"]), 1)
        self.assertEqual(len([item for item in self.service.detail(self.record)["messages"] if item["role"] == "result"]), 2)

    def test_concurrent_receipt_creates_one_job_across_service_instances(self):
        message, _, _ = self.complete()
        body = self.body(message["scriptProposals"][0])
        second = WorkflowService(self.root / "private", models=self.models, recover_jobs=False)
        barrier, results, errors = threading.Barrier(2), [], []
        def submit(service):
            try:
                barrier.wait(timeout=5)
                results.append(service.submit(deepcopy(body))["job"]["id"])
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=submit, args=(service,)) for service in (self.service, second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1])

    def test_explicit_retry_reuses_frozen_code_and_images_and_rechecks_permissions(self):
        message, _, _ = self.complete()
        proposal = message["scriptProposals"][0]
        self.service.callbacks["before_execute"] = lambda *_: False
        done = self.execute(proposal)
        self.assertEqual(done["status"], "waiting", done)
        self.upload("red")
        self.service.configure_projects({"project": {**self.projects[0], "timeout": 6}})
        self.error(lambda: self.service.retry(request(jobId=done["id"])), "permission_changed")
        self.service.configure_projects({"project": self.projects[0]})
        self.service.callbacks.pop("before_execute")
        retry_body = request(jobId=done["id"])
        retried = self.service.retry(retry_body)["job"]
        self.assertEqual(self.service.retry(retry_body)["job"]["id"], retried["id"])
        result = self.wait(retried)
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(result["attempt"], 2)
        self.assertEqual(result["parentJobId"], done["id"])
        self.assertEqual(len(self.service.incubator_dispatches()["dispatches"]), 1)

    def test_restart_does_not_replay_running_or_finished_script(self):
        message, _, _ = self.complete()
        job = self.service.submit(self.body(message["scriptProposals"][0]))["job"]
        with self.service._db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job["id"],))
        restarted = WorkflowService(self.root / "private", models=self.models)
        self.service = restarted
        self.service.start()
        done = self.wait(job)
        self.assertEqual(done["status"], "interrupted", done)
        self.assertFalse((self.project / "selected-script-ran.txt").exists())
        retry = self.service.retry(request(jobId=job["id"]))["job"]
        result = self.wait(retry)
        self.assertEqual(result["status"], "succeeded", result)
        self.service.shutdown()
        restarted = WorkflowService(self.root / "private", models=self.models)
        self.service = restarted
        self.service.start()
        self.assertEqual(self.wait(retry)["status"], "succeeded")
        self.assertFalse(self.service.has_pending_jobs())
        self.assertEqual(len(list(self.service.jobs_dir.glob("*/task.py"))), 1)

    def test_missing_or_invalid_result_is_failed_never_assumed_done(self):
        for script in ("print('No manifest')\n", "import os\nfrom pathlib import Path\nPath(os.environ['CONSOLE_WORKFLOW_RESULT_MANIFEST']).write_text('{}')\n",
                       "import os\nfrom pathlib import Path\nPath(os.environ['CONSOLE_WORKFLOW_RESULT_MANIFEST']).write_text('{\"files\":[]}')\n",
                       "import os\nfrom pathlib import Path\nPath(os.environ['CONSOLE_WORKFLOW_RESULT_MANIFEST']).write_text('{\"text\":\"\",\"files\":[]}')\n",
                       "import os\nfrom pathlib import Path\nPath(os.environ['CONSOLE_WORKFLOW_RESULT_MANIFEST']).write_text('{bad')\n"):
            with self.subTest(script=script):
                record = self.service.create(request(projectId="fixture", text="Invalid result fixture"))["record"]["id"]
                message, _, _ = self.complete("```python\n" + script + "```", record=record, images=[])
                body = self.body(message["scriptProposals"][0])
                body["recordId"] = record
                job = self.service.submit(body)["job"]
                self.service.start()
                done = self.wait(job)
                self.assertEqual(done["status"], "failed", done)
                self.assertEqual(done["resultAttachmentIds"], [])

    def test_local_environment_and_log_redaction_still_protect_custom_api_key(self):
        key_name, secret = "CONSOLE_SYNTHETIC_CUSTOM_CREDENTIAL", "synthetic-private-value-36"
        script = ("import json, os\nfrom pathlib import Path\nassert '" + key_name + "' not in os.environ\n" +
                  "print('" + secret + "')\n" +
                  "Path(os.environ['CONSOLE_WORKFLOW_RESULT_MANIFEST']).write_text(json.dumps({'text':'Environment filtered','files':[]}))\n")
        message, _, _ = self.complete("```python\n" + script + "```", images=[])
        with patch.dict(os.environ, {key_name: secret}):
            self.models.configure({"id": "unused", "endpoint": "http://127.0.0.1:9/v1", "model": "unused", "keyEnv": key_name})
            done = self.execute(message["scriptProposals"][0])
        self.assertEqual(done["status"], "succeeded", done)
        self.assertNotIn(secret, done["log"])
        self.assertIn("[model-key-redacted]", done["log"])
        self.assertNotIn(secret, (self.service.jobs_dir / done["id"] / "execution.log").read_text(encoding="utf-8"))

    def test_no_models_adapter_can_execute_reviewed_python_script(self):
        message, _, _ = self.complete()
        self.service.models = None
        done = self.execute(message["scriptProposals"][0])
        self.assertEqual(done["status"], "succeeded", done)

    def test_unavailable_capability_and_missing_runner_remain_visible_but_disabled(self):
        message, _, _ = self.complete()
        for change in ({"allowGeneratedScripts": False}, {"capabilities": ["result_import"]}, {"scriptRunners": {}}):
            self.service.configure_projects({"project": {**self.projects[0], **change}})
            proposal = next(item for item in self.service.detail(self.record)["messages"] if item["id"] == message["id"])["scriptProposals"][0]
            self.assertFalse(proposal["executable"])
            self.assertTrue(proposal["unavailableReason"])
            self.error(lambda: self.service.submit(self.body(proposal)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
