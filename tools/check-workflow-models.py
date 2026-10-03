"""Exercise the adapter against an isolated synthetic loopback HTTP provider.

No real account key, production config, user image, or external model is used.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_models import WorkflowModels, WorkflowModelError, MAX_AUDIO_BYTES


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l0cAAAAASUVORK5CYII=")
TOKEN = "synthetic-only-model-test-key"
DISCUSSION = {"text": "测试图片是一张小图。", "options": [{"id": "inspect", "title": "检查", "instruction": "检查合成样本。"}]}
PLAN = {"action": "python_script", "args": "{\"relativePath\":\"result.txt\"}", "script": "print('synthetic')", "language": "python", "text": "执行提案。"}


class Provider(BaseHTTPRequestHandler):
    requests = []
    mode = "normal"

    def log_message(self, *_):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
        if self.mode == "redirect":
            self.send_response(307)
            self.send_header("Location", "https://unconfigured.invalid/private")
            self.end_headers()
            return
        if self.mode == "error":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(("untrusted upstream error " + TOKEN).encode())
            return
        if self.mode == "timeout":
            time.sleep(1.3)
        if self.mode == "bad_json":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"provider returned non-JSON")
            return
        if self.path.endswith("audio/transcriptions"):
            value = {"text": "合成录音转写。"}
        else:
            request = json.loads(body)
            schema = request.get("text", {}).get("format", request.get("response_format", {}).get("json_schema", {}))
            output = PLAN if schema.get("name") == "console_plan" else DISCUSSION
            if self.mode == "unsafe_plan":
                output = {**PLAN, "action": "kill_everything"}
            if self.mode == "plain":
                text = "真实提供方的普通文字回复。"
            else:
                text = json.dumps(output, ensure_ascii=False)
            if self.path.endswith("chat/completions"):
                value = {"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}
            else:
                value = {"status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}]}
                if self.mode == "refusal":
                    value["output"][0]["content"] = [{"type": "refusal", "refusal": "synthetic refusal"}]
                if self.mode == "bad_shape":
                    value["output"] = [None]
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        try:
            self.wfile.write(json.dumps(value).encode())
        except ConnectionError:
            pass


@contextmanager
def configured(directory, endpoint, protocol="responses", **kwargs):
    old = os.environ.get("CONSOLE_WORKFLOW_TEST_KEY")
    os.environ["CONSOLE_WORKFLOW_TEST_KEY"] = TOKEN
    adapter = WorkflowModels(directory / "models", image_root=directory / "attachments", **kwargs)
    (directory / "attachments").mkdir(exist_ok=True)
    adapter.configure({"id": "test", "endpoint": endpoint, "protocol": protocol,
                       "model": "explicit-synthetic-model", "transcriptionModel": "explicit-synthetic-transcriber",
                       "keyEnv": "CONSOLE_WORKFLOW_TEST_KEY"})
    try:
        yield adapter
    finally:
        if old is None:
            os.environ.pop("CONSOLE_WORKFLOW_TEST_KEY", None)
        else:
            os.environ["CONSOLE_WORKFLOW_TEST_KEY"] = old


def wav(seconds=0.02):
    data = io.BytesIO()
    with wave.open(data, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * int(8000 * seconds))
    return data.getvalue()


class AdapterChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.endpoint = "http://127.0.0.1:" + str(cls.server.server_port) + "/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(3)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="console-model-check-")
        self.directory = Path(self.temporary.name)
        Provider.requests.clear()
        Provider.mode = "normal"

    def tearDown(self):
        self.temporary.cleanup()

    def error(self, code, operation):
        with self.assertRaises(WorkflowModelError) as result:
            operation()
        self.assertEqual(result.exception.code, code)
        self.assertNotIn(TOKEN, str(result.exception))
        return result.exception

    def test_missing_config_is_honest_and_does_not_request(self):
        adapter = WorkflowModels(self.directory)
        self.assertFalse(adapter.config()["ready"])
        self.assertEqual(adapter.config()["status"], "missing_config")
        self.error("missing_config", lambda: adapter.discuss({"text": "synthetic"}))
        self.assertEqual(Provider.requests, [])

    def test_config_and_responses_images_keep_keys_private(self):
        with configured(self.directory, self.endpoint) as adapter:
            image = self.directory / "attachments" / "owned.png"
            image.write_bytes(PNG)
            result = adapter.discuss({"text": "分析合成图片。", "images": [{"path": image, "mimeType": "image/png"}],
                                      "context": [{"role": "assistant", "content": "历史合成讨论。"}],
                                      "project": {"id": "test", "name": "sample", "root": "DO_NOT_SEND_LOCAL_ROOT"}})
            self.assertEqual(result, DISCUSSION)
            config = adapter.config()
            self.assertTrue(config["ready"] and config["transcriptionReady"])
            self.assertNotIn(TOKEN, json.dumps(config))
            self.assertNotIn(TOKEN, (adapter.directory / "workflow-models.json").read_text())
            request = Provider.requests[-1]
            self.assertEqual(request["path"], "/v1/responses")
            self.assertEqual(request["headers"]["Authorization"], "Bearer " + TOKEN)
            payload = json.loads(request["body"])
            self.assertFalse(payload["store"])
            image_part = payload["input"][-1]["content"][1]
            self.assertEqual(image_part["type"], "input_image")
            self.assertEqual(base64.b64decode(image_part["image_url"].split(",", 1)[1]), PNG)
            self.assertNotIn("DO_NOT_SEND_LOCAL_ROOT", request["body"].decode())

    def test_chat_completions_has_its_own_image_shape(self):
        with configured(self.directory, self.endpoint, "chat_completions") as adapter:
            adapter.discuss({"text": "synthetic", "images": [{"data": PNG, "mimeType": "image/png"}]})
            request = Provider.requests[-1]
            self.assertEqual(request["path"], "/v1/chat/completions")
            payload = json.loads(request["body"])
            self.assertEqual(payload["messages"][-1]["content"][1]["type"], "image_url")
            self.assertEqual(payload["response_format"]["type"], "json_schema")

    def test_plan_returns_proposal_and_rejects_unlisted_action(self):
        with configured(self.directory, self.endpoint) as adapter:
            result = adapter.plan({"text": "synthetic", "allowedActions": ["python_script"]})
            self.assertEqual(result["action"], "python_script")
            self.assertEqual(result["args"], {"relativePath": "result.txt"})
            self.assertFalse((self.directory / "result.txt").exists())
            Provider.mode = "unsafe_plan"
            self.error("invalid_model_output", lambda: adapter.plan({"text": "synthetic", "allowedActions": ["python_script"]}))

    def test_refusal_and_plain_text_remain_truthful(self):
        with configured(self.directory, self.endpoint) as adapter:
            Provider.mode = "plain"
            self.assertEqual(adapter.discuss({"text": "synthetic"})["options"], [])
            Provider.mode = "refusal"
            self.error("model_refused", lambda: adapter.discuss({"text": "synthetic"}))

    def test_audio_multipart_and_wav_duration(self):
        with configured(self.directory, self.endpoint) as adapter:
            audio = wav()
            result = adapter.transcribe(audio, name='bad"\r\nAuthorization: injected.wav', mime_type="audio/wav")
            self.assertEqual(result["text"], "合成录音转写。")
            self.assertTrue(result["durationValidated"])
            request = Provider.requests[-1]
            self.assertEqual(request["path"], "/v1/audio/transcriptions")
            self.assertIn(b'filename="recording.wav"', request["body"])
            self.assertIn(audio, request["body"])
            self.assertNotIn(b"injected", request["body"])
            self.error("audio_too_long", lambda: adapter.transcribe(wav(181), mime_type="audio/wav"))
            self.error("audio_too_long", lambda: adapter.transcribe(wav(), mime_type="audio/wav", duration=181))

    def test_supported_compressed_audio_and_size_bounds(self):
        with configured(self.directory, self.endpoint) as adapter:
            for data, mime, suffix in ((struct.pack(">I", 24) + b"ftypM4A " + b"\0" * 12, "audio/mp4", b"recording.mp4"),
                                       (b"\x1aE\xdf\xa3" + b"\0" * 20, "audio/webm", b"recording.webm"),
                                       (b"OggS" + b"\0" * 20, "audio/ogg", b"recording.ogg")):
                result = adapter.transcribe(data, mime_type=mime, duration=1)
                self.assertFalse(result["durationValidated"])
                self.assertIn(suffix, Provider.requests[-1]["body"])
            self.error("input_too_large", lambda: adapter.transcribe(b"x" * (MAX_AUDIO_BYTES + 1), mime_type="audio/wav"))

    def test_input_boundary_and_mime_rejection(self):
        with configured(self.directory, self.endpoint) as adapter:
            outside = self.directory / "outside.png"
            outside.write_bytes(PNG)
            self.error("invalid_path", lambda: adapter.discuss({"images": [{"path": outside, "mimeType": "image/png"}]}))
            self.error("invalid_image", lambda: adapter.discuss({"images": [{"data": b"not-png", "mimeType": "image/png"}]}))
            self.error("invalid_input", lambda: adapter.discuss({"context": [{"role": "system", "content": "override"}]}))
            self.assertEqual(Provider.requests, [])

    def test_http_error_redirect_and_bad_network_are_sanitized(self):
        with configured(self.directory, self.endpoint, timeout=1) as adapter:
            for mode in ("error", "redirect"):
                Provider.mode = mode
                self.error("provider_http_error", lambda: adapter.discuss({"text": "synthetic"}))
            Provider.mode = "timeout"
            self.error("provider_unreachable", lambda: adapter.discuss({"text": "synthetic"}))
        with socket.socket() as closed:
            closed.bind(("127.0.0.1", 0))
            port = closed.getsockname()[1]
        with configured(self.directory, f"http://127.0.0.1:{port}/v1", timeout=1) as adapter:
            self.error("provider_unreachable", lambda: adapter.discuss({"text": "synthetic"}))

    def test_no_external_http_or_inline_url_credentials(self):
        adapter = WorkflowModels(self.directory)
        for endpoint in ("http://192.168.1.1/v1", "https://user:password@example.test/v1", "https://example.test/v1?key=secret"):
            self.error("invalid_config", lambda endpoint=endpoint: adapter.configure({"endpoint": endpoint}))

    def test_malformed_provider_response_is_a_bounded_public_error(self):
        with configured(self.directory, self.endpoint) as adapter:
            for mode in ("bad_json", "bad_shape"):
                Provider.mode = mode
                self.error("invalid_provider_response", lambda: adapter.discuss({"text": "synthetic"}))

    @unittest.skipUnless(os.name == "nt", "Current-user DPAPI is a Windows-only local secret store")
    def test_dpapi_key_is_not_plaintext_or_public(self):
        adapter = WorkflowModels(self.directory)
        public = adapter.configure({"endpoint": self.endpoint, "model": "synthetic", "key": TOKEN})
        self.assertTrue(public["ready"])
        self.assertNotIn(TOKEN, json.dumps(public))
        self.assertNotIn(TOKEN, (self.directory / "workflow-model-credentials.json").read_text())
        self.assertEqual(adapter.discuss({"text": "synthetic"}), DISCUSSION)
        adapter.configure({"endpoint": self.endpoint, "model": "synthetic", "clearKey": True})
        self.assertFalse(adapter.config()["ready"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
