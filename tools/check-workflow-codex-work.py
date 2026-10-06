"""Owned child-stdio fixtures; no account, provider, desktop or production IO."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
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
import hashlib, json, os, pathlib, queue, sys, threading, time, tomllib
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
def file_tool(identifier=800, call_id="file_call_1", tool="console_write_text", arguments=None):
    params = {"threadId": thread_id, "turnId": turn_id, "callId": call_id,
              "namespace": "console_workspace", "tool": tool,
              "arguments": arguments or {"path": "probe.txt", "content": "真实的隔离修改。", "expectedSha256": None}}
    if mode == "dynamic_foreign_turn":
        params["turnId"] = "unowned_turn"
    elif mode == "dynamic_foreign_namespace":
        params["namespace"] = "unowned_namespace"
    elif mode == "dynamic_invalid_call":
        params["callId"] = "not/an/id"
    elif mode == "dynamic_wrong_tool":
        params["tool"] = "shell_command"
    elif mode == "dynamic_scope_error":
        params["arguments"]["path"] = "../outside.txt"
    emit({"id": identifier, "method": "item/tool/call", "params": params})
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
    if method is None and "result" in value and mode.startswith("dynamic_"):
        if mode.startswith("dynamic_unknown_"):
            # The second request was already buffered before the first reply.
            # Only the owned interrupt may terminate this unknown-write fixture.
            pass
        elif value["id"] == 800 and mode == "dynamic_prewrite_then_write":
            file_tool(identifier=801, call_id="file_call_2", arguments={"path": "probe.txt",
                "content": "真实的隔离修改。",
                "expectedSha256": hashlib.sha256("原先的内容。".encode("utf-8")).hexdigest()})
        elif value["id"] == 800 and mode == "dynamic_duplicate":
            file_tool(identifier=801, call_id="file_call_1", arguments={"path": "probe.txt", "content": "不应重复写入。",
                "expectedSha256": None})
        elif value["id"] == 800 and mode == "dynamic_write":
            file_tool(identifier=801, call_id="file_call_2", tool="console_read_text", arguments={"path": "probe.txt"})
        elif mode not in {"dynamic_cancel", "dynamic_duplicate", "dynamic_foreign_turn",
                          "dynamic_foreign_namespace", "dynamic_invalid_call", "dynamic_wrong_tool"}:
            event("item/agentMessage/delta", itemId="answer_fixture", delta="修改说明完整。")
            terminal()
        continue
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
        elif mode.startswith("dynamic_"):
            file_tool()
            if mode.startswith("dynamic_unknown_"):
                file_tool(identifier=801, call_id="file_call_2", arguments={"path": "probe.txt",
                    "content": "不应再次写入。",
                    "expectedSha256": hashlib.sha256("真实的隔离修改。".encode("utf-8")).hexdigest()})
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
        self.version_reads = []
        self.cli_version = "codex-cli " + api.SUPPORTED_CLI_VERSION
        self.workspace = self.root / "workspace"
        self.allowed = self.workspace / "allowed"
        self.allowed.mkdir(parents=True)
        self.script = self.root / "child.py"
        self.script.write_text(CHILD, encoding="utf-8")
        self.subscription = Subscription()
        self.controller = api.CodexWorkController(self.subscription, self.root / "state",
            executable=sys.executable, popen_factory=self.spawn, rpc_timeout=2, turn_timeout=4,
            cli_version_reader=self.read_version)
        self.run_id = uuid.uuid4().hex

    def read_version(self, executable, environment, cwd):
        self.version_reads.append({"executable": executable, "environment": dict(environment), "cwd": str(cwd)})
        return self.cli_version

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
        self.assertEqual(receipt["evidenceType"], api.FILE_TOOLS_EVIDENCE)
        self.assertEqual(receipt["schemaVersion"], 2)
        self.assertFalse(prepared["sandboxVerified"])
        self.assertEqual(receipt["capabilities"], api.file_tools_capabilities())
        self.assertNotIn(TOKEN, json.dumps(f.events))
        self.assertNotIn("description", receipt["configuration"]["permissionProfile"])
        self.assertNotIn("unused", receipt["configuration"]["permissionProfile"]["filesystem"])
        changed = copy.deepcopy(receipt)
        changed["configuration"]["permissionProfile"]["filesystem"]["glob_scan_max_depth"] = 3.0
        self.assertFalse(api.valid_preparation_receipt(changed, allowed_root=f.allowed,
            image_root=f.home() / "images", model=BINDING["modelSlug"], effort="high", thread_id="thread_fixture"))

    def test_file_tools_write_and_read_real_temp_file_with_exact_environment_contract(self):
        f = self.fixture("dynamic_write")
        f.submit()
        f.done()
        self.assertEqual((f.allowed / "probe.txt").read_text(encoding="utf-8"), "真实的隔离修改。")
        self.assertEqual(f.controller.snapshot(f.run_id)["state"], "completed")
        frames = f.messages()
        start = next(frame for frame in frames if frame.get("method") == "thread/start")
        self.assertEqual(start["params"]["environments"], [])
        self.assertEqual(start["params"]["dynamicTools"], api.file_tools_specs())
        self.assertEqual(start["params"]["developerInstructions"], api.FILE_TOOLS_INSTRUCTIONS)
        self.assertEqual([tool["name"] for tool in start["params"]["dynamicTools"][0]["tools"]],
                         ["console_list_files", "console_read_text", "console_write_text"])
        write = next(frame["result"] for frame in frames if frame.get("id") == 800)
        read = next(frame["result"] for frame in frames if frame.get("id") == 801)
        self.assertTrue(write["success"])
        self.assertTrue(read["success"])
        actual_write = json.loads(write["contentItems"][0]["text"])
        actual_read = json.loads(read["contentItems"][0]["text"])
        self.assertEqual(actual_write["afterSha256"], hashlib.sha256((f.allowed / "probe.txt").read_bytes()).hexdigest())
        self.assertEqual(actual_read["text"], "真实的隔离修改。")
        self.assertFalse(actual_write["optimisticRaceEliminated"])
        self.assertEqual(sum(event.get("kind") == "console_file_write" for event in f.events), 1)
        self.assertEqual(sum(frame.get("method") == "turn/start" for frame in frames), 1)
        self.assertEqual(len(list((f.home() / "file-tools").glob("*intent*"))), 2)

    def test_file_tools_duplicate_call_cannot_repeat_a_real_write(self):
        f = self.fixture("dynamic_duplicate")
        f.submit()
        f.wait(lambda: f.controller.snapshot(f.run_id)["state"] == "unknown")
        self.assertEqual(f.controller.snapshot(f.run_id)["error"], "codex_work_file_tool_replayed")
        self.assertEqual((f.allowed / "probe.txt").read_text(encoding="utf-8"), "真实的隔离修改。")
        self.assertEqual(sum(event.get("kind") == "console_file_write" for event in f.events), 1)
        self.assertEqual(len(list((f.home() / "file-tools").glob("*intent*"))), 1)

    def test_foreign_or_malformed_file_tool_requests_do_not_touch_files(self):
        for mode, code in (("dynamic_foreign_turn", "codex_work_foreign_server_request"),
                           ("dynamic_foreign_namespace", "codex_work_file_tool_request_invalid"),
                           ("dynamic_invalid_call", "codex_work_file_tool_request_invalid"),
                           ("dynamic_wrong_tool", "codex_work_file_tool_request_invalid")):
            with self.subTest(mode=mode):
                f = self.fixture(mode)
                f.submit()
                f.wait(lambda: f.controller.snapshot(f.run_id)["state"] == "unknown")
                self.assertEqual(f.controller.snapshot(f.run_id)["error"], code)
                self.assertFalse((f.allowed / "probe.txt").exists())
                self.assertEqual(list((f.home() / "file-tools").iterdir()), [])
                self.assertFalse(any(event.get("kind") == "console_file_write" for event in f.events))

    def test_file_tool_cancel_accepted_before_call_prevents_write(self):
        f = self.fixture("dynamic_cancel")
        original = f.event
        def cancel_when_started(event):
            result = original(event)
            if event["type"] == "turn_started":
                f.controller.interrupt(f.run_id, event["threadId"], event["turnId"])
            return result
        f.event = cancel_when_started
        f.submit()
        f.done()
        self.assertTrue(f.controller.snapshot(f.run_id)["cancelVerified"])
        self.assertFalse((f.allowed / "probe.txt").exists())
        self.assertEqual(list((f.home() / "file-tools").iterdir()), [])
        reply = next(frame["result"] for frame in f.messages() if frame.get("id") == 800)
        self.assertFalse(reply["success"])
        self.assertEqual(json.loads(reply["contentItems"][0]["text"]), {"code": "codex_work_file_tool_cancelled"})

    def test_file_tool_scope_failure_is_fixed_safe_reply_not_success_or_write(self):
        f = self.fixture("dynamic_scope_error")
        f.submit()
        f.done()
        reply = next(frame["result"] for frame in f.messages() if frame.get("id") == 800)
        self.assertFalse(reply["success"])
        result = json.loads(reply["contentItems"][0]["text"])
        self.assertRegex(result["code"], r"^codex_files_[a-z0-9_]+$")
        self.assertNotIn(str(f.allowed), reply["contentItems"][0]["text"])
        self.assertFalse((f.workspace / "outside.txt").exists())
        self.assertFalse(any(event.get("kind") == "console_file_write" for event in f.events))

    def assert_unknown_write_fenced(self, f, *, receipt_count):
        f.done()
        state, frames = f.controller.snapshot(f.run_id), f.messages()
        self.assertEqual((state["state"], state["error"], state["terminalStatus"]),
                         ("unknown", "codex_work_file_write_unverified", "interrupted"))
        self.assertTrue(state["terminalEventObserved"])
        self.assertFalse(state["cancelVerified"])
        self.assertFalse(state["active"])
        self.assertFalse(state["retryAllowed"])
        self.assertEqual((f.allowed / "probe.txt").read_text(encoding="utf-8"), "真实的隔离修改。")
        self.assertEqual(sum(frame.get("method") == "turn/start" for frame in frames), 1)
        self.assertEqual(sum(frame.get("method") == "turn/interrupt" for frame in frames), 1)
        blocked = [event for event in f.events if event["type"] == "file_tools_blocked"]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["code"], "codex_work_file_write_unverified")
        second = next(frame["result"] for frame in frames if frame.get("id") == 801)
        self.assertFalse(second["success"])
        self.assertEqual(json.loads(second["contentItems"][0]["text"]),
                         {"code": "codex_work_file_tool_cancelled"})
        markers = f.home() / "file-tools"
        self.assertEqual(len(list(markers.glob("*.intent.json"))), 1)
        self.assertEqual(len(list(markers.glob("*.receipt.json"))), receipt_count)
        last_terminal = [event for event in f.events if event["type"] == "terminal"][-1]
        self.assertEqual((last_terminal["status"], last_terminal["terminalStatus"]), ("unknown", "interrupted"))
        self.assertFalse(last_terminal["cancellationVerified"])

    def test_write_receipt_save_failure_keeps_actual_write_and_blocks_new_call_id(self):
        f = self.fixture("dynamic_unknown_receipt")
        original = api.CodexFiles.save
        def fail_receipt(instance, path, value):
            if path.name.endswith(".receipt.json"):
                raise OSError("fixture failure after destination mutation")
            return original(instance, path, value)
        with mock.patch.object(api.CodexFiles, "save", new=fail_receipt):
            f.submit()
            self.assert_unknown_write_fenced(f, receipt_count=0)

    def test_write_post_mutation_verification_failure_blocks_new_call_id(self):
        f = self.fixture("dynamic_unknown_verification")
        original = api.CodexFiles._write_text
        def fail_verification(instance, *args):
            original(instance, *args)
            raise RuntimeError("codex_files_write_unverified")
        with mock.patch.object(api.CodexFiles, "_write_text", new=fail_verification):
            f.submit()
            self.assert_unknown_write_fenced(f, receipt_count=0)

    def test_successful_write_frame_and_progress_failures_fence_subsequent_calls(self):
        for failure in ("frame", "progress_false", "progress_exception", "progress_limit"):
            with self.subTest(failure=failure):
                f = self.fixture("dynamic_unknown_" + failure)
                original_call, original_event = api.CodexFiles.call, f.event
                def checked_call(instance, *args, **kwargs):
                    result = original_call(instance, *args, **kwargs)
                    if failure == "frame":
                        result["fixtureOversized"] = "x" * api.MAX_LINE
                    return result
                def fail_progress(event):
                    value = original_event(event)
                    if event["type"] == "turn_started" and failure == "progress_limit":
                        f.controller._runs[f.run_id].progress_chars = api.MAX_PROGRESS
                    if event.get("kind") == "console_file_write":
                        if failure == "progress_false":
                            return False
                        if failure == "progress_exception":
                            raise OSError("fixture callback failure")
                    return value
                f.event = fail_progress
                with mock.patch.object(api.CodexFiles, "call", new=checked_call):
                    f.submit()
                    self.assert_unknown_write_fenced(f, receipt_count=1)

    def test_definite_prewrite_sha_rejection_allows_new_valid_call(self):
        f = self.fixture("dynamic_prewrite_then_write")
        (f.allowed / "probe.txt").write_text("原先的内容。", encoding="utf-8")
        f.submit()
        f.done()
        first = next(frame["result"] for frame in f.messages() if frame.get("id") == 800)
        self.assertFalse(first["success"])
        self.assertEqual(json.loads(first["contentItems"][0]["text"]), {"code": "codex_files_sha_conflict"})
        second = next(frame["result"] for frame in f.messages() if frame.get("id") == 801)
        self.assertTrue(second["success"])
        self.assertEqual((f.allowed / "probe.txt").read_text(encoding="utf-8"), "真实的隔离修改。")
        self.assertEqual(f.controller.snapshot(f.run_id)["state"], "completed")
        self.assertFalse(any(event["type"] == "file_tools_blocked" for event in f.events))

    def test_progress_and_unknown_fence_callbacks_do_not_deadlock_a_cancel_snapshot(self):
        for callback_kind in ("progress", "file_tools_blocked"):
            with self.subTest(callback_kind=callback_kind):
                f = self.fixture("dynamic_unknown_lock")
                service_lock = threading.Lock()
                db_owned, callback_entered, snapshot_done = (threading.Event() for _ in range(3))
                observed, callback_timeouts, original_event = [], [], f.event
                def service_cancel_scope():
                    # Mirrors the service's DB-lock -> controller.snapshot order.
                    with service_lock:
                        db_owned.set()
                        if callback_entered.wait(3):
                            state = f.controller.snapshot(f.run_id)
                            observed.append(state)
                            f.controller.interrupt(f.run_id, state["threadId"], state["turnId"])
                            snapshot_done.set()
                def service_callback(event):
                    selected = (event.get("kind") == "console_file_write" if callback_kind == "progress"
                                else event["type"] == "file_tools_blocked")
                    if selected:
                        callback_entered.set()
                        # With the old run-lock -> callback order, this times out:
                        # cancellation owns DB and waits for the same run lock.
                        if not snapshot_done.wait(2):
                            callback_timeouts.append(callback_kind)
                            raise RuntimeError("fixture detected run/DB lock inversion")
                        with service_lock:
                            pass
                    value = original_event(event)
                    if callback_kind == "progress" and selected:
                        return False  # preserve a hard unknown fence afterward
                    return value
                f.event = service_callback
                cancel_thread = threading.Thread(target=service_cancel_scope)
                cancel_thread.start()
                self.assertTrue(db_owned.wait(2))
                original_save = api.CodexFiles.save
                def fail_receipt(instance, path, value):
                    if callback_kind == "file_tools_blocked" and path.name.endswith(".receipt.json"):
                        raise OSError("fixture post-write receipt failure")
                    return original_save(instance, path, value)
                try:
                    with mock.patch.object(api.CodexFiles, "save", new=fail_receipt):
                        f.submit()
                        self.assert_unknown_write_fenced(f, receipt_count=1 if callback_kind == "progress" else 0)
                    self.assertTrue(snapshot_done.is_set())
                    self.assertEqual(len(observed), 1)
                    self.assertEqual(callback_timeouts, [])
                finally:
                    callback_entered.set()
                    cancel_thread.join(timeout=4)
                self.assertFalse(cancel_thread.is_alive())

    def test_file_tools_preparation_caps_are_strict_and_legacy_receipt_stays_compatible(self):
        f = self.fixture()
        f.submit()
        f.done()
        receipt = next(event["preparationReceipt"] for event in f.events if event["type"] == "prepared")
        for changes in ({"fileToolsOnly": False}, {"nativeEnvironmentAccess": True},
                        {"threadStartEnvironments": ["local"]}, {"dynamicToolsSha256": "0" * 64},
                        {"enforcement": "windows_os_sandbox"}, {"fileToolsOnly": 1}, {"cliVersion": "0.160.0"}):
            with self.subTest(changes=changes):
                changed = copy.deepcopy(receipt)
                changed["capabilities"].update(changes)
                self.assertFalse(api.valid_preparation_receipt(changed, allowed_root=f.allowed,
                    image_root=f.home() / "images", model=BINDING["modelSlug"], effort="high", thread_id="thread_fixture"))
        legacy = copy.deepcopy(receipt)
        legacy.update(schemaVersion=1, evidenceType=api.PREPARATION_EVIDENCE)
        legacy.pop("capabilities")
        self.assertTrue(api.valid_preparation_receipt(legacy, allowed_root=f.allowed,
            image_root=f.home() / "images", model=BINDING["modelSlug"], effort="high", thread_id="thread_fixture"))

    def test_unknown_cli_contract_fails_before_connection_and_native_thread(self):
        for version in ("codex-cli 0.160.0", "codex-cli 0.160.2", "not a version", None):
            with self.subTest(version=version):
                f = self.fixture()
                f.cli_version = version
                f.submit()
                f.done()
                self.assertEqual(f.controller.snapshot(f.run_id)["error"], "codex_work_cli_version_unsupported")
                self.assertEqual(f.subscription.calls, [])
                self.assertEqual(f.children, [])
                self.assertNotIn("ACCESS_TOKEN", f.version_reads[0]["environment"])
                self.assertEqual(f.version_reads[0]["environment"]["CODEX_HOME"],
                                 str(f.root / "state" / "codex-work" / "runtime-home"))

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
                                           popen_factory=f.spawn, rpc_timeout=2, turn_timeout=4,
                                           cli_version_reader=f.read_version)
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
                before_children = len(f.children)
                f.mode = "complete"
                for project_config in ("", '\n[projects.' + json.dumps(str(f.allowed))
                                       + ']\ntrust_level = "trusted"\n'):
                    with self.subTest(projects=bool(project_config)):
                        (runtime / "config.toml").write_text('[windows]\nsandbox = "elevated"\n'
                                                            + project_config, encoding="utf-8")
                        f.run_id = uuid.uuid4().hex
                        f.submit()
                        f.done()
                        self.assertEqual(f.controller.snapshot(f.run_id)["error"], "codex_work_runtime_changed")
                        self.assertEqual(len(f.children), before_children)
                        restarted = api.CodexWorkController(f.subscription, f.root / "state", executable=sys.executable)
                        self.assertFalse(restarted.start()["ready"])
                        restarted.close()

    def test_setup_workspace_trust_survives_restart_without_new_authorization(self):
        f = self.fixture("setup_complete")
        f.controller.begin_setup(str(f.workspace))
        f.wait(lambda: f.controller._setup_run.complete.is_set())
        root = f.root / "state" / "codex-work"
        runtime = root / "runtime-home"
        config = runtime / "config.toml"
        # Real Windows setup saved a lower-case key for a mixed-case path.
        key = str(f.workspace).lower() if os.name == "nt" else str(f.workspace)
        config.write_text('[windows]\nsandbox = "elevated"\n\n[projects.'
                          + json.dumps(key) + ']\ntrust_level = "trusted"\n', encoding="utf-8")
        protected = [config, root / "setup-intent.json", next(root.glob("setup-completion-*.json"))]
        original = {str(path): path.read_bytes() for path in protected}
        f.controller.close()
        f.controller = api.CodexWorkController(f.subscription, f.root / "state", executable=sys.executable,
            popen_factory=f.spawn, rpc_timeout=2, turn_timeout=4, cli_version_reader=f.read_version)
        status = f.controller.start()
        self.assertEqual(status["status"], "ready")
        self.assertTrue(status["ready"])
        self.assertTrue(status["terminalEventObserved"])
        self.assertFalse(f.controller.begin_setup(str(f.workspace))["accepted"])
        self.assertEqual(len(f.children), 1)
        self.assertEqual(f.subscription.calls, [])
        f.mode = "complete"
        f.submit()
        f.done()
        self.assertEqual(f.controller.snapshot(f.run_id)["state"], "completed")
        self.assertEqual(sum(row.get("method") == "turn/start" for row in f.messages()), 1)
        self.assertEqual(len(f.children), 2)
        self.assertEqual(f.invocations[-1]["env"]["CODEX_HOME"], str(runtime))
        self.assertIn('projects.' + json.dumps(str(f.allowed)) + '.trust_level="untrusted"',
                      f.invocations[-1]["command"])
        self.assertEqual({str(path): path.read_bytes() for path in protected}, original)

    def test_success_receipt_only_admits_one_plain_same_setup_workspace_trust_entry(self):
        f = self.fixture("setup_complete")
        f.controller.begin_setup(str(f.workspace))
        f.wait(lambda: f.controller._setup_run.complete.is_set())
        root = f.root / "state" / "codex-work"
        config = root / "runtime-home" / "config.toml"
        other = f.root / "unrelated"
        other.mkdir()
        trusted = {"trust_level": "trusted"}
        valid = {str(f.workspace): trusted}

        def write_projects(projects, extra=""):
            content = '[windows]\nsandbox="elevated"\n' + extra
            if not projects:
                content += '\n[projects]\n'
            for path, settings in projects.items():
                content += '\n[projects.' + json.dumps(path) + ']\n'
                for name, value in settings.items():
                    content += name + '=' + json.dumps(value) + '\n'
            config.write_text(content, encoding="utf-8")

        for projects, extra in (({}, ""), ({str(other): trusted}, ""),
                ({str(f.root): trusted}, ""), ({str(f.allowed): trusted}, ""),
                ({str(Path(f.workspace.anchor)): trusted}, ""), ({"relative": trusted}, ""),
                ({**valid, str(other): trusted}, ""),
                ({str(f.workspace): {"trust_level": "untrusted"}}, ""),
                ({str(f.workspace): {**trusted, "unknown_setting": "value"}}, ""),
                (valid, '\n[hooks]\ncommand="outside"\n'),
                (valid, '\n[mcp_servers.other]\ncommand="outside"\n')):
            with self.subTest(projects=projects, extra=extra):
                write_projects(projects, extra)
                with self.assertRaises(WorkflowError) as blocked:
                    f.controller._runtime()
                self.assertEqual(blocked.exception.code, "codex_work_runtime_changed")
                restarted = api.CodexWorkController(f.subscription, f.root / "state", executable=sys.executable)
                self.assertFalse(restarted.start()["ready"])
                restarted.close()
        write_projects(valid)
        intent_path = root / "setup-intent.json"
        original = intent_path.read_bytes()
        intent = json.loads(original)
        for workspace in (None, "relative", str(other), str(f.root)):
            with self.subTest(intent_workspace=workspace):
                intent_path.write_text(json.dumps({**intent, "workspaceRoot": workspace}), encoding="utf-8")
                with self.assertRaises(WorkflowError) as blocked:
                    f.controller._runtime()
                self.assertEqual(blocked.exception.code, "codex_work_runtime_changed")
        intent_path.write_bytes(original)
        self.assertEqual(f.controller._runtime()[1], config.parent.resolve())
        self.assertEqual(len(f.children), 1)
        self.assertEqual(f.subscription.calls, [])

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
