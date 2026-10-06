"""Owned child-stdio fixtures; no account, provider, desktop or production IO."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import workflow_codex_work as api
from workflow_service import WorkflowError


TOKEN = "fixture-ACCESS-secret-0123456789"
BINDING = {"provider": "chatgpt_subscription", "connectionId": "1" * 32,
           "catalogRevision": "2" * 64, "modelSlug": "gpt-6-astra"}
# A real child process speaks the documented RPC protocol, including a terminal
# notification before its turn/start reply and an interrupt acknowledgement that
# is deliberately separate from the later interrupted notification.
CHILD = r'''
import json, os, pathlib, queue, sys, threading, time, tomllib
mode = sys.argv[1]
runtime_home = pathlib.Path(os.environ["CODEX_HOME"])
home = pathlib.Path(sys.argv[2])
command = json.loads(sys.argv[3])
log = home / "fixture-rpcs.jsonl"
inbox = queue.Queue()
def reader():
    for line in sys.stdin.buffer:
        inbox.put(json.loads(line))
    inbox.put(None)
threading.Thread(target=reader, daemon=True).start()
def emit(value):
    # ASCII JSON is valid UTF-8 on Windows regardless of this mock Python's
    # console code page; the native CLI's wire itself is always UTF-8.
    sys.stdout.write(json.dumps(value, ensure_ascii=True) + "\n")
    sys.stdout.flush()
thread_id, turn_id, running, release, setup_running = "thread_fixture", "turn_fixture", False, False, False
def event(method, **values):
    emit({"method": method, "params": {"threadId": thread_id, "turnId": turn_id, **values}})
def terminal(status="completed", text="修改说明完整。", mismatch=False):
    global running
    item = {"id": "answer_fixture", "type": "agentMessage", "text": "矛盾快照" if mismatch else text}
    event("turn/completed", turn={"id": turn_id, "status": status,
                                  "items": [item] if status == "completed" else [], "error": None})
    running = False
while True:
    if running and (home / "fixture-release").exists():
        terminal("interrupted")
    if setup_running and (home / "fixture-setup-release").exists():
        # Match actual 0.160.1 run_windows_sandbox_setup_and_persist(): official
        # config mutation precedes the successful completion notification.
        (runtime_home / "config.toml").write_text('[windows]\nsandbox = "elevated"\n', encoding="utf-8")
        emit({"method": "windowsSandbox/setupCompleted", "params": {"mode": "elevated", "success": True, "error": None}})
        setup_running = False
    try:
        value = inbox.get(timeout=.02)
    except queue.Empty:
        continue
    if value is None:
        break
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")
    method, params = value.get("method"), value.get("params", {})
    if method == "initialize":
        emit({"id": value["id"], "result": {"userAgent": "isolated fake"}})
    elif method == "initialized":
        pass
    elif method == "config/read":
        overrides = [command[index + 1] for index, value in enumerate(command[:-1]) if value == "-c"]
        config = tomllib.loads("\n".join(overrides))
        filesystem = config["permissions"]["console-work-scope"]["filesystem"]
        if mode == "legacy_read_scope":
            filesystem.pop(":root")
        if mode == "changed_write_scope":
            filesystem[str(home.parent)] = "write"
        if mode == "external_tools":
            config["mcp_servers"] = {"unowned": {"command": "other-tool"}}
        hook_events = ("Interrupt", "PermissionRequest", "PostCompact", "PostToolUse",
                       "PreCompact", "PreToolUse", "SessionEnd", "SessionStart", "Stop",
                       "SubagentStart", "SubagentStop", "UserPromptSubmit")
        if mode == "hooks_defaults":
            # Actual token-free CLI 0.160.1 config/read returned these twelve
            # arrays, all empty, despite the explicit hooks={} override.
            config["hooks"] = {name: [] for name in hook_events}
        elif mode == "hooks_subset":
            config["hooks"] = {"SessionStart": [], "Stop": []}
        invalid_tools = {
            "hooks_command": ("hooks", {"PreToolUse": [{"hooks": [{"type": "command", "command": "other-tool"}]}]}),
            "hooks_mcp": ("hooks", {"PreToolUse": [{"hooks": [{"type": "mcp_tool", "server": "other", "tool": "run"}]}]}),
            "hooks_prompt": ("hooks", {"Stop": [{"hooks": [{"type": "prompt"}]}]}),
            "hooks_agent": ("hooks", {"Stop": [{"hooks": [{"type": "agent"}]}]}),
            "hooks_unknown": ("hooks", {"UnknownEvent": []}),
            "hooks_state": ("hooks", {"state": {}}),
            "hooks_false": ("hooks", False),
            "hooks_event_false": ("hooks", {"Stop": False}),
            "hooks_event_null": ("hooks", {"Stop": None}),
            "hooks_event_object": ("hooks", {"Stop": {}}),
            "hooks_empty_matcher": ("hooks", {"Stop": [{"hooks": []}]}),
            "plugins_named": ("plugins", {"other-plugin": {"enabled": False}}),
            "plugins_array": ("plugins", []),
            "mcp_false": ("mcp_servers", False),
            "mcp_array": ("mcp_servers", []),
        }
        if mode in invalid_tools:
            key, setting = invalid_tools[mode]
            config[key] = setting
        if mode == "receipt_extra":
            config["fixture_private"] = {"accessToken": os.environ["ACCESS_TOKEN"]}
            config["permissions"]["console-work-scope"]["description"] = os.environ["ACCESS_TOKEN"]
            config["permissions"]["console-work-scope"]["network"]["unused"] = None
            filesystem["unused"] = None
        emit({"id": value["id"], "result": {"config": config}})
    elif method == "windowsSandbox/setupStart":
        setup_running = True
        emit({"id": value["id"], "result": {"started": True}})
        if mode == "setup_complete":
            (runtime_home / "config.toml").write_text('[windows]\nsandbox = "elevated"\n', encoding="utf-8")
            emit({"method": "windowsSandbox/setupCompleted", "params": {"mode": "elevated", "success": True, "error": None}})
            setup_running = False
        elif mode == "setup_failed":
            emit({"method": "windowsSandbox/setupCompleted", "params": {"mode": "elevated", "success": False, "error": "fixture private error"}})
            setup_running = False
        elif mode == "setup_unknown":
            # A mock abrupt process exit supplies no setupCompleted. Avoid
            # Python finalization waiting for this fixture's daemon stdin reader.
            os._exit(0)
    elif method == "thread/start":
        if mode == "windows_scope_required":
            emit({"id": value["id"], "error": {"code": -32603, "message":
                "windows unelevated restricted-token sandbox cannot enforce split filesystem read restrictions directly; refusing to run unsandboxed"}})
            continue
        profile = {"id": params["permissions"], "extends": ":workspace"}
        if mode == "wrong_profile":
            profile["id"] = ":danger-full-access"
        emit({"id": value["id"], "result": {"thread": {"id": thread_id},
              "model": params["model"], "modelProvider": params["modelProvider"],
              "reasoningEffort": params["config"]["model_reasoning_effort"],
              "cwd": params["cwd"], "approvalPolicy": params["approvalPolicy"], "activePermissionProfile": profile}})
    elif method == "turn/start":
        running = True
        event("turn/started", turn={"id": turn_id, "status": "inProgress", "items": [], "error": None})
        if mode == "foreign_turn":
            event("item/agentMessage/delta", itemId="answer_fixture", delta="部分说明。")
            emit({"method": "turn/completed", "params": {"threadId": "other_thread",
                 "turn": {"id": turn_id, "status": "completed", "items": [], "error": None}}})
        if mode == "secret":
            token = os.environ["ACCESS_TOKEN"]
            for text in ["说明：", token[:11], token[11:22], token[22:], "。"]:
                event("item/agentMessage/delta", itemId="answer_fixture", delta=text)
            sys.stderr.write(token + "\n")
            sys.stderr.flush()
            terminal(text="说明：" + token + "。")
        elif mode in {"complete", "mismatch", "receipt_extra", "hooks_defaults", "hooks_subset"}:
            event("item/agentMessage/delta", itemId="answer_fixture", delta="修改说明完整。")
            terminal(mismatch=mode == "mismatch")
        elif mode == "approval":
            emit({"id": "approval_fixture", "method": "item/commandExecution/requestApproval",
                  "params": {"threadId": thread_id, "turnId": turn_id, "itemId": "command_fixture"}})
        emit({"id": value["id"], "result": {"turn": {"id": turn_id, "status": "inProgress", "items": [], "error": None}}})
    elif method == "turn/interrupt":
        emit({"id": value["id"], "result": {}})
        if mode not in {"ack_only", "foreign_turn"}:
            terminal("interrupted")
'''


class Subscription:
    def __init__(self):
        self.calls = []

    def prepare_work_connection(self, binding):
        self.calls.append(copy.deepcopy(binding))
        if binding != BINDING:
            raise WorkflowError("stale", 409, "subscription_selection_stale")
        return {"accessToken": TOKEN, "subscription": dict(binding)}


class Fixture:
    def __init__(self, root, mode="complete", reject_intent=False):
        # Windows CI TEMP may be an 8.3 alias. Match the controller's canonical
        # owned path without weakening any exact RPC/source comparisons.
        self.root, self.mode, self.reject_intent = Path(root).resolve(), mode, reject_intent
        self.events, self.children, self.invocations = [], [], []
        self.workspace = self.root / "workspace"
        self.allowed = self.workspace / "allowed"
        self.allowed.mkdir(parents=True)
        self.script = self.root / "child.py"
        self.script.write_text(CHILD, encoding="utf-8")
        self.subscription = Subscription()
        self.controller = api.CodexWorkController(self.subscription, self.root / "state",
            executable=sys.executable, popen_factory=self.spawn, rpc_timeout=2, turn_timeout=4)
        self.run_id = uuid.uuid4().hex

    def spawn(self, command, **kwargs):
        self.invocations.append({"command": list(command), "env": dict(kwargs["env"]), "cwd": kwargs["cwd"]})
        setup = not any(value.startswith("permissions." + api.PERMISSION_PROFILE + "=") for value in command)
        log_home = Path(kwargs["env"]["CODEX_HOME"]).parent if setup else self.home()
        child = subprocess.Popen([sys.executable, "-I", "-B", str(self.script), self.mode,
                                  str(log_home), json.dumps(command)], **kwargs)
        self.children.append(child)
        return child

    def spec(self, **changes):
        value = {"subscription": dict(BINDING), "requestedProfile": "high",
                 "workspaceRoot": str(self.workspace), "allowedRoot": str(self.allowed),
                 "text": "本轮明确确认：只修改允许目录。", "images": [], "sourceSha256": "3" * 64}
        value.update(changes)
        return value

    def event(self, value):
        self.events.append(value)
        return False if self.reject_intent and value["type"] == "send_intent" else True

    def submit(self, **changes):
        return self.controller.submit(self.run_id, self.spec(**changes), self.event)

    def home(self):
        return self.root / "state" / "codex-work" / self.run_id

    def messages(self):
        path = self.home() / "fixture-rpcs.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def wait(self, predicate, seconds=5):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            if predicate():
                return
            time.sleep(.02)
        raise AssertionError("owned fixture did not reach expected state")

    def done(self):
        self.wait(lambda: not self.controller.snapshot(self.run_id)["active"])

    def cleanup(self):
        setup_run = self.controller._setup_run
        if setup_run is not None and not setup_run.complete.is_set():
            (setup_run.home / "fixture-setup-release").write_text("owned fake completion", encoding="utf-8")
            self.wait(lambda: setup_run.complete.is_set())
        if self.run_id in self.controller._runs:
            state = self.controller.snapshot(self.run_id)
            if state["active"] and state["turnId"] and not state["terminalEventObserved"]:
                if not state["cancelRequested"]:
                    self.controller.interrupt(self.run_id, state["threadId"], state["turnId"])
                self.home().joinpath("fixture-release").write_text("owned fake terminal", encoding="utf-8")
                self.done()
        self.controller.close()
        for child in self.children:
            child.wait(timeout=4)
            for pipe in (child.stdout, child.stderr):
                pipe.close()


class Checks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="console-work-fixture-")
        self.fixtures = []

    def tearDown(self):
        for fixture in reversed(self.fixtures):
            fixture.cleanup()
        self.temp.cleanup()

    def fixture(self, mode="complete", reject_intent=False):
        value = Fixture(Path(self.temp.name) / str(len(self.fixtures)), mode, reject_intent)
        self.fixtures.append(value)
        return value

    def test_complete_before_start_reply_keeps_exact_source_and_single_intent(self):
        f = self.fixture()
        self.assertFalse(f.submit()["executionVerified"])
        f.done()
        state = f.controller.snapshot(f.run_id)
        self.assertEqual((state["state"], state["terminalStatus"], state["report"]),
                         ("completed", "completed", "修改说明完整。"))
        self.assertTrue(state["terminalEventObserved"])
        self.assertFalse(state["retryAllowed"])
        self.assertEqual([event["type"] for event in f.events].count("send_intent"), 1)
        self.assertTrue(all(event["sourceSha256"] == "3" * 64 and event["runId"] == f.run_id for event in f.events))
        self.assertTrue(all(event.get("executionVerified") is not True for event in f.events))
        frames = f.messages()
        self.assertEqual([row.get("method") for row in frames], ["initialize", "initialized", "config/read", "thread/start", "turn/start"])
        self.assertEqual(frames[0]["params"]["clientInfo"]["name"], "Codex Console")
        self.assertEqual(frames[-1]["params"]["input"], [{"type": "text", "text": f.spec()["text"]}])
        self.assertEqual(frames[-1]["params"]["model"], BINDING["modelSlug"])
        self.assertEqual(frames[-1]["params"]["effort"], "high")

    def test_frozen_image_exact_owned_copy_and_no_user_config_environment(self):
        f = self.fixture()
        image = b"fixture-specific-image-bytes"
        f.submit(images=[{"bytes": image, "mimeType": "image/png", "sha256": hashlib.sha256(image).hexdigest()}],
                 requestedProfile="fast")
        f.done()
        image_path = f.home() / "images" / "0.png"
        self.assertEqual(image_path.read_bytes(), image)
        start = next(row for row in f.messages() if row.get("method") == "turn/start")
        self.assertEqual(start["params"]["input"][1], {"type": "localImage", "path": str(image_path)})
        self.assertEqual(start["params"]["effort"], "low")
        invocation = f.invocations[0]
        self.assertEqual(invocation["env"]["CODEX_HOME"], str(f.root / "state" / "codex-work" / "runtime-home"))
        self.assertEqual(invocation["env"]["ACCESS_TOKEN"], TOKEN)
        self.assertTrue(set(invocation["env"]).issubset(api.SAFE_ENV | {"CODEX_HOME", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TMP", "TEMP", "TMPDIR", "ACCESS_TOKEN"}))
        args = "\n".join(invocation["command"])
        self.assertNotIn(TOKEN, args)
        self.assertIn("https://api.openai.com/v1", args)
        self.assertIn('supports_websockets=false', args)
        self.assertIn('request_max_retries=0', args)
        self.assertIn('agents.enabled=false', args)
        self.assertIn('trust_level="untrusted"', args)

    def test_actual_selected_prepare_echo_is_bound_and_does_not_forward_private_config(self):
        f = self.fixture("receipt_extra")
        f.submit()
        f.done()
        prepared = next(event for event in f.events if event["type"] == "prepared")
        receipt = prepared["preparationReceipt"]
        self.assertTrue(api.valid_preparation_receipt(receipt, allowed_root=f.allowed,
            image_root=f.home() / "images", model=BINDING["modelSlug"], effort="high", thread_id="thread_fixture"))
        self.assertEqual(receipt["threadStart"]["activePermissionProfile"], {"id": api.PERMISSION_PROFILE, "extends": ":workspace"})
        self.assertEqual(receipt["evidenceType"], "configuration_and_thread_profile_echo")
        self.assertNotIn(TOKEN, json.dumps(f.events))
        self.assertNotIn("description", receipt["configuration"]["permissionProfile"])
        self.assertNotIn("unused", receipt["configuration"]["permissionProfile"]["filesystem"])
        changed = copy.deepcopy(receipt)
        changed["configuration"]["permissionProfile"]["filesystem"]["glob_scan_max_depth"] = 3.0
        self.assertFalse(api.valid_preparation_receipt(changed, allowed_root=f.allowed,
            image_root=f.home() / "images", model=BINDING["modelSlug"], effort="high", thread_id="thread_fixture"))

    def test_uncommitted_prepare_receipt_stops_before_intent_and_turn(self):
        f = self.fixture()
        original = f.event
        def reject_preparation(event):
            original(event)
            return event["type"] != "prepared"
        f.event = reject_preparation
        f.submit()
        f.done()
        self.assertEqual(f.controller.snapshot(f.run_id)["error"], "codex_work_preparation_not_durable")
        self.assertFalse(any(event["type"] == "send_intent" for event in f.events))
        self.assertFalse(any(frame.get("method") == "turn/start" for frame in f.messages()))

    def test_legacy_or_changed_scope_never_starts_turn(self):
        for mode in ("legacy_read_scope", "changed_write_scope", "wrong_profile"):
            with self.subTest(mode=mode):
                f = self.fixture(mode)
                f.submit()
                f.done()
                self.assertEqual(f.controller.snapshot(f.run_id)["error"], "codex_work_read_scope_unsupported")
                self.assertFalse(any(row.get("method") == "turn/start" for row in f.messages()))
                self.assertFalse(any(row["type"] == "send_intent" for row in f.events))

    def test_actual_windows_rejection_and_external_tools_fail_without_inference(self):
        for mode, code in (("windows_scope_required", "codex_work_windows_sandbox_required"),
                           ("external_tools", "codex_work_external_tools_present")):
            with self.subTest(mode=mode):
                f = self.fixture(mode)
                f.submit()
                f.done()
                self.assertEqual(f.controller.snapshot(f.run_id)["error"], code)
                self.assertFalse(any(row.get("method") == "turn/start" for row in f.messages()))
                self.assertFalse(any(row["type"] == "send_intent" for row in f.events))

    def test_actual_typed_empty_hook_defaults_prepare_and_send_exactly_once(self):
        for mode in ("hooks_defaults", "hooks_subset"):
            with self.subTest(mode=mode):
                f = self.fixture(mode)
                f.submit()
                f.done()
                self.assertEqual(f.controller.snapshot(f.run_id)["state"], "completed")
                self.assertEqual(sum(event["type"] == "prepared" for event in f.events), 1)
                self.assertEqual(sum(event["type"] == "send_intent" for event in f.events), 1)
                self.assertEqual(sum(frame.get("method") == "thread/start" for frame in f.messages()), 1)
                self.assertEqual(sum(frame.get("method") == "turn/start" for frame in f.messages()), 1)
                self.assertEqual(len(f.subscription.calls), 1)

    def test_configured_or_unrecognized_hooks_fail_before_thread_and_send_intent(self):
        for mode in ("hooks_command", "hooks_mcp", "hooks_prompt", "hooks_agent",
                     "hooks_unknown", "hooks_state", "hooks_false", "hooks_event_false",
                     "hooks_event_null", "hooks_event_object", "hooks_empty_matcher"):
            with self.subTest(mode=mode):
                f = self.fixture(mode)
                f.submit()
                f.done()
                self.assertEqual(f.controller.snapshot(f.run_id)["error"], "codex_work_external_tools_present")
                self.assertFalse(any(event["type"] in {"prepared", "send_intent"} for event in f.events))
                self.assertFalse(any(frame.get("method") in {"thread/start", "turn/start"} for frame in f.messages()))

    def test_mcp_and_plugins_still_require_exact_empty_mapping(self):
        for mode in ("plugins_named", "plugins_array", "mcp_false", "mcp_array"):
            with self.subTest(mode=mode):
                f = self.fixture(mode)
                f.submit()
                f.done()
                self.assertEqual(f.controller.snapshot(f.run_id)["error"], "codex_work_external_tools_present")
                self.assertFalse(any(event["type"] in {"prepared", "send_intent"} for event in f.events))
                self.assertFalse(any(frame.get("method") in {"thread/start", "turn/start"} for frame in f.messages()))

    def test_intent_must_commit_before_sole_turn_start(self):
        f = self.fixture(reject_intent=True)
        f.submit()
        f.done()
        self.assertEqual(f.controller.snapshot(f.run_id)["error"], "codex_work_intent_not_durable")
        self.assertFalse(any(row.get("method") == "turn/start" for row in f.messages()))

    def test_pro_extra_binding_scope_and_image_fail_before_child(self):
        cases = [{"requestedProfile": "pro"}, {"subscription": {**BINDING, "reasoningMode": "pro"}},
                 {"allowedRoot": str(Path(self.temp.name))},
                 {"images": [{"bytes": b"wrong", "mimeType": "image/png", "sha256": "0" * 64}]}]
        for changes in cases:
            with self.subTest(changes=list(changes)):
                f = self.fixture()
                with self.assertRaises(WorkflowError):
                    f.submit(**changes)
                self.assertEqual(f.subscription.calls, [])
                self.assertEqual(f.children, [])

    def test_duplicate_run_and_restart_do_not_replay(self):
        f = self.fixture()
        f.submit()
        f.done()
        with self.assertRaises(WorkflowError):
            f.submit()
        fresh = api.CodexWorkController(f.subscription, f.root / "state", executable=sys.executable)
        with self.assertRaises(WorkflowError):
            fresh.submit(f.run_id, f.spec(), f.event)
        self.assertEqual(len(f.children), 1)
        self.assertEqual(len(f.subscription.calls), 1)
        fresh.close()

    def test_ack_is_not_cancel_completion_and_duplicate_interrupt_is_single_rpc(self):
        f = self.fixture("ack_only")
        f.submit()
        f.wait(lambda: f.controller.snapshot(f.run_id)["turnId"] is not None)
        state = f.controller.snapshot(f.run_id)
        first = f.controller.interrupt(f.run_id, state["threadId"], state["turnId"])
        second = f.controller.interrupt(f.run_id, state["threadId"], state["turnId"])
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        f.wait(lambda: any(row.get("method") == "turn/interrupt" for row in f.messages()))
        state = f.controller.snapshot(f.run_id)
        self.assertTrue(state["active"])
        self.assertFalse(state["cancelVerified"])
        self.assertFalse(state["terminalEventObserved"])
        self.assertFalse(f.controller.close()["closed"])
        f.home().joinpath("fixture-release").write_text("complete own fake interruption", encoding="utf-8")
        f.done()
        self.assertTrue(f.controller.snapshot(f.run_id)["cancelVerified"])
        self.assertEqual(sum(row.get("method") == "turn/interrupt" for row in f.messages()), 1)

    def test_two_processes_cancel_one_without_changing_other(self):
        a, b = self.fixture("running"), self.fixture("running")
        a.submit()
        b.submit()
        for f in (a, b):
            f.wait(lambda f=f: f.controller.snapshot(f.run_id)["state"] == "running")
        self.assertNotEqual(a.children[0].pid, b.children[0].pid)
        state = a.controller.snapshot(a.run_id)
        a.controller.interrupt(a.run_id, state["threadId"], state["turnId"])
        a.done()
        self.assertTrue(a.controller.snapshot(a.run_id)["cancelVerified"])
        self.assertEqual(b.controller.snapshot(b.run_id)["state"], "running")
        self.assertFalse(any(row.get("method") == "turn/interrupt" for row in b.messages()))
        with self.assertRaises(WorkflowError):
            b.controller.interrupt(b.run_id, "other_thread", state["turnId"])

    def test_foreign_terminal_is_unknown_active_partial_and_can_be_precisely_interrupted(self):
        f = self.fixture("foreign_turn")
        f.submit()
        f.wait(lambda: f.controller.snapshot(f.run_id)["state"] == "unknown")
        state = f.controller.snapshot(f.run_id)
        self.assertEqual(state["error"], "codex_work_foreign_thread_event")
        self.assertEqual(state["report"], "部分说明。")
        self.assertTrue(state["active"])
        self.assertFalse(state["terminalEventObserved"])
        f.controller.interrupt(f.run_id, state["threadId"], state["turnId"])
        f.wait(lambda: any(row.get("method") == "turn/interrupt" for row in f.messages()))
        self.assertFalse(f.controller.snapshot(f.run_id)["cancelVerified"])
        f.home().joinpath("fixture-release").write_text("own true terminal", encoding="utf-8")
        f.done()
        self.assertTrue(f.controller.snapshot(f.run_id)["cancelVerified"])

    def test_matching_terminal_fact_survives_contradictory_answer(self):
        f = self.fixture("mismatch")
        f.submit()
        f.done()
        state = f.controller.snapshot(f.run_id)
        self.assertEqual(state["state"], "unknown")
        self.assertTrue(state["terminalEventObserved"])
        self.assertEqual(state["terminalStatus"], "completed")
        self.assertEqual(state["error"], "codex_work_terminal_text_mismatch")
        self.assertEqual(state["report"], "修改说明完整。")
        self.assertEqual(f.children[0].poll(), 0)

    def test_credential_split_across_progress_frames_and_stderr_is_never_public(self):
        f = self.fixture("secret")
        f.submit()
        f.done()
        public = json.dumps(f.events, ensure_ascii=False) + json.dumps(f.controller.snapshot(f.run_id), ensure_ascii=False)
        self.assertNotIn(TOKEN, public)
        chunks = "".join(event.get("text", "") for event in f.events if event["type"] == "progress")
        self.assertEqual(chunks, "说明：［凭据已隐藏］。")
        self.assertEqual(f.controller.snapshot(f.run_id)["report"], "说明：［凭据已隐藏］。")

    def test_additional_approval_is_denied_and_waits_real_interrupt(self):
        f = self.fixture("approval")
        f.submit()
        f.done()
        reply = next(row for row in f.messages() if row.get("id") == "approval_fixture")
        self.assertEqual(reply["result"], {"decision": "cancel"})
        self.assertTrue(f.controller.snapshot(f.run_id)["cancelVerified"])
        self.assertEqual(sum(row.get("method") == "turn/interrupt" for row in f.messages()), 1)
        self.assertTrue(any(row["type"] == "approval_blocked" for row in f.events))

    def test_setup_ack_is_not_ready_and_same_owned_runtime_is_reused_after_real_notification(self):
        f = self.fixture("setup_ack")
        result = f.controller.begin_setup(str(f.allowed))
        self.assertTrue(result["accepted"])
        self.assertFalse(result["ready"])
        root = f.root / "state" / "codex-work"
        log = root / "fixture-rpcs.jsonl"
        f.wait(lambda: log.exists() and "windowsSandbox/setupStart" in log.read_text(encoding="utf-8"))
        self.assertTrue(f.controller.setup_status()["busy"])
        self.assertFalse(f.controller.setup_status()["terminalEventObserved"])
        self.assertFalse(f.controller.begin_setup(str(f.allowed))["accepted"])
        self.assertNotIn("ACCESS_TOKEN", f.invocations[0]["env"])
        self.assertEqual(f.subscription.calls, [])
        frames = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row.get("method") for row in frames], ["initialize", "initialized", "windowsSandbox/setupStart"])
        self.assertEqual(frames[-1]["params"], {"mode": "elevated", "cwd": str(f.allowed)})
        original_config = (root / "runtime-home" / "config.toml").read_bytes()
        self.assertEqual(original_config, api.RUNTIME_CONFIG)
        (root / "fixture-setup-release").write_text("actual own fake completion", encoding="utf-8")
        f.wait(lambda: f.controller._setup_run.complete.is_set())
        self.assertTrue(f.controller.setup_status()["ready"])
        self.assertTrue(f.controller.setup_status()["terminalEventObserved"])
        self.assertFalse(f.controller.setup_status()["busy"])
        official_config = (root / "runtime-home" / "config.toml").read_bytes()
        self.assertNotEqual(official_config, original_config)
        self.assertEqual(official_config.replace(b"\r\n", b"\n"), b'[windows]\nsandbox = "elevated"\n')
        f.mode = "complete"
        f.submit()
        f.done()
        self.assertEqual(f.invocations[0]["env"]["CODEX_HOME"], f.invocations[1]["env"]["CODEX_HOME"])
        self.assertEqual((root / "runtime-home" / "config.toml").read_bytes(), official_config)
        self.assertIn('windows.sandbox="elevated"', f.invocations[1]["command"])
        self.assertEqual(f.controller.snapshot(f.run_id)["state"], "completed")
        restarted = api.CodexWorkController(f.subscription, f.root / "state", executable=sys.executable,
                                           popen_factory=f.spawn, rpc_timeout=2, turn_timeout=4)
        restarted.start()
        self.assertTrue(restarted.setup_status()["ready"])
        self.assertFalse(restarted.begin_setup(str(f.allowed))["accepted"])
        f.controller.close()
        f.controller = restarted
        f.run_id = uuid.uuid4().hex
        f.submit()
        f.done()
        self.assertEqual(restarted.snapshot(f.run_id)["state"], "completed")
        self.assertEqual(f.invocations[-1]["env"]["CODEX_HOME"], f.invocations[0]["env"]["CODEX_HOME"])
        self.assertIn('windows.sandbox="elevated"', f.invocations[-1]["command"])

    def test_official_persisted_mode_requires_own_success_receipt(self):
        for mode in ("no_setup", "setup_unknown", "setup_failed"):
            with self.subTest(mode=mode):
                f = self.fixture(mode)
                if mode == "no_setup":
                    f.controller.start()
                else:
                    f.controller.begin_setup(str(f.allowed))
                    f.wait(lambda: f.controller._setup_run.complete.is_set())
                runtime = f.root / "state" / "codex-work" / "runtime-home"
                (runtime / "config.toml").write_text('[windows]\nsandbox = "elevated"\n', encoding="utf-8")
                before_children = len(f.children)
                f.mode = "complete"
                f.submit()
                f.done()
                self.assertEqual(f.controller.snapshot(f.run_id)["error"], "codex_work_runtime_changed")
                self.assertEqual(len(f.children), before_children)
                restarted = api.CodexWorkController(f.subscription, f.root / "state", executable=sys.executable)
                self.assertFalse(restarted.start()["ready"])
                restarted.close()

    def test_success_receipt_never_admits_extra_settings_or_unbound_receipt(self):
        f = self.fixture("setup_complete")
        f.controller.begin_setup(str(f.allowed))
        f.wait(lambda: f.controller._setup_run.complete.is_set())
        root = f.root / "state" / "codex-work"
        runtime = root / "runtime-home"
        config = runtime / "config.toml"
        official = config.read_bytes()
        for suffix in (b'[mcp_servers.other]\ncommand="other"\n', b'model_provider="other"\n',
                       b'[permissions.other]\nextends=":danger-full-access"\n', b'#' * (api.MAX_RUNTIME_CONFIG + 1)):
            with self.subTest(extra=suffix[:40]):
                config.write_bytes(official + suffix)
                with self.assertRaises(WorkflowError) as blocked:
                    f.controller._runtime()
                self.assertEqual(blocked.exception.code, "codex_work_runtime_changed")
        config.write_bytes(official)
        receipt_path = next(root.glob("setup-completion-*.json"))
        receipt = json.loads(receipt_path.read_bytes())
        original_receipt = receipt_path.read_bytes()
        for changes in ({"attemptId": "f" * 32}, {"runtimeHome": str(f.workspace)},
                        {"terminalEventObserved": False}, {"success": False}, {"mode": "unelevated"}):
            with self.subTest(receipt=changes):
                receipt_path.write_text(json.dumps({**receipt, **changes}), encoding="utf-8")
                with self.assertRaises(WorkflowError) as blocked:
                    f.controller._runtime()
                self.assertEqual(blocked.exception.code, "codex_work_runtime_changed")
        receipt_path.write_bytes(original_receipt)
        self.assertEqual(f.controller._runtime()[1], runtime.resolve())
        self.assertEqual(len(f.children), 1)

    def test_setup_unknown_persists_once_and_restart_cannot_retry(self):
        f = self.fixture("setup_unknown")
        f.controller.begin_setup(str(f.allowed))
        f.wait(lambda: f.controller._setup_run.complete.is_set())
        status = f.controller.setup_status()
        self.assertEqual(status["status"], "unknown")
        self.assertFalse(status["ready"])
        self.assertFalse(status["terminalEventObserved"])
        self.assertTrue(f.children[0].stdin.closed)
        restarted = api.CodexWorkController(f.subscription, f.root / "state", executable=sys.executable,
                                           popen_factory=f.spawn)
        restarted.start()
        self.assertEqual(restarted.setup_status()["status"], "unknown")
        self.assertFalse(restarted.begin_setup(str(f.allowed))["accepted"])
        self.assertEqual(len(f.children), 1)
        self.assertEqual(f.subscription.calls, [])
        restarted.close()

    def test_setup_failure_error_is_fixed_and_does_not_grant_ready(self):
        f = self.fixture("setup_failed")
        events = []
        f.controller.begin_setup(str(f.allowed), events.append)
        f.wait(lambda: f.controller._setup_run.complete.is_set())
        status = f.controller.setup_status()
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["error"], "codex_work_setup_failed")
        self.assertFalse(status["ready"])
        self.assertNotIn("fixture private error", json.dumps(events) + json.dumps(status))
        self.assertFalse(f.controller.begin_setup(str(f.allowed))["accepted"])

    def test_get_status_does_not_initialize_or_adopt_modified_runtime_config(self):
        f = self.fixture()
        self.assertFalse((f.root / "state").exists())
        f.controller.setup_status()
        self.assertFalse((f.root / "state").exists())
        f.controller.start()
        runtime = f.root / "state" / "codex-work" / "runtime-home"
        (runtime / "config.toml").write_text('mcp_servers.other.command="unsafe"\n', encoding="utf-8")
        f.submit()
        f.done()
        self.assertEqual(f.controller.snapshot(f.run_id)["state"], "failed")
        self.assertEqual(f.controller.snapshot(f.run_id)["error"], "codex_work_runtime_changed")
        self.assertEqual(f.children, [])


if __name__ == "__main__":
    unittest.main()
