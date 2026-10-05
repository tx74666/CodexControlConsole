"""Offline production subscription-stream fixtures. Every HTTPS connection is fake.

No real token, network, user image, production store, OAuth, or inference request.
Run only when the parent schedules these checks; importing performs no request.
"""
import base64
import importlib.util
import hashlib
import io
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
import zlib

from PIL import Image

spec = importlib.util.spec_from_file_location("isolated_subscription_stream", Path(__file__).resolve().parents[1] / "workflow_subscription_stream.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
TOKEN = "fixture-access-token-never-real"
MODEL = "fixture-selected-model"
TEXT = "任意完整回答：符号 ∑，emoji 🧭，中文与 Markdown。\n第二行保持原样。"
INPUT_ITEMS = [{"role": "user", "content": [{"type": "input_text", "text": "保留我的原问题与标点！"}]}]


def fixture_png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0\x12\x34\x56\xff")) + chunk(b"IEND", b""))


def image_part(png=None):
    data = fixture_png() if png is None else png
    return {"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(data).decode("ascii")}


def fixture_image(media):
    if media == "png":
        return fixture_png()
    buffer = io.BytesIO()
    with Image.new("RGB", (1, 1), (18, 52, 86)) as image:
        image.save(buffer, format={"jpeg": "JPEG", "webp": "WEBP", "gif": "GIF"}[media])
    return buffer.getvalue()


def event(kind, **fields):
    return {"type": kind, **fields}


def wire(*events, newline=b"\n", multiline=False):
    parts = []
    for value in events:
        data = json.dumps(value, ensure_ascii=False, indent=2 if multiline else None).encode("utf-8")
        parts.append(b"event: " + value["type"].encode("ascii") + newline)
        parts.extend(b"data: " + line + newline for line in data.split(b"\n"))
        parts.append(newline)
    return b"".join(parts)


def created(identifier="resp_fixture", sequence=0):
    return event("response.created", sequence_number=sequence,
                 response={"id": identifier, "model": "fixture-actual-model", "status": "in_progress"})


def delta(text=TEXT, sequence=1):
    return event("response.output_text.delta", sequence_number=sequence, delta=text,
                 item_id="msg_fixture", output_index=0, content_index=0)


def completed(text=TEXT, identifier="resp_fixture", sequence=2):
    return event("response.completed", sequence_number=sequence, response={
        "id": identifier, "model": "fixture-actual-model", "status": "completed", "error": None,
        "incomplete_details": None, "output": [{"id": "msg_fixture", "type": "message", "role": "assistant",
        "status": "completed", "content": [{"type": "output_text", "text": text}]}]})


class FakeSocket:
    def __init__(self):
        self.timeouts = []

    def settimeout(self, value):
        assert 0 < value <= probe.MAX_IDLE_SECONDS
        self.timeouts.append(value)


class FakeResponse:
    def __init__(self, body, status=200, headers=None, block_size=7):
        self.body, self.status, self.block_size, self.offset, self.closed = body, status, block_size, 0, False
        self.headers = {"content-type": "text/event-stream; charset=utf-8", "x-request-id": "req_fixture",
                        **{key.lower(): value for key, value in (headers or {}).items()}}

    def getheader(self, name, default=None):
        return self.headers.get(name.lower(), default)

    def read1(self, size):
        count = min(size, self.block_size)
        value = self.body[self.offset:self.offset + count]
        self.offset += len(value)
        return value

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, response, send_error=False, close_on_headers=False):
        self.response, self.send_error, self.close_on_headers = response, send_error, close_on_headers
        self.sock, self.original_socket, self.requests = FakeSocket(), None, []
        self.original_socket = self.sock
        self.auto_open, self.connect_count, self.closed, self.debug = 1, 0, False, None

    def set_debuglevel(self, value):
        self.debug = value

    def connect(self):
        self.connect_count += 1
        assert self.connect_count == 1, "The probe may connect only once."

    def request(self, method, path, body, headers):
        assert self.auto_open == 0
        self.requests.append((method, path, body, headers))
        if self.send_error:
            raise TimeoutError("fixture socket outcome is unknown")

    def getresponse(self):
        if self.close_on_headers:
            # Real HTTPConnection relinquishes its socket when will_close=true.
            self.sock = None
        return self.response

    def close(self):
        self.closed = True


class ResponseChecks(unittest.TestCase):
    def check(self, body, *, status=200, headers=None, send_error=False, close_on_headers=False, block_size=7,
              diagnostic=False, verification=False, input_items=None):
        response = FakeResponse(body, status, headers, block_size)
        connection = FakeConnection(response, send_error, close_on_headers)

        def factory(host, port, *, timeout, context):
            self.assertEqual((host, port), ("api.openai.com", 443))
            self.assertGreater(timeout, 0)
            self.assertTrue(context.check_hostname)
            self.assertIsNone(context.keylog_filename)
            return connection

        with patch.object(probe.http.client, "HTTPSConnection", side_effect=factory) as calls:
            result = probe.run_response(TOKEN, MODEL, INPUT_ITEMS if input_items is None else input_items)
        self.assertEqual(calls.call_count, 1)
        self.assertEqual(connection.connect_count, 1)
        self.assertEqual(len(connection.requests), 1, "Unknown or failed POST outcomes must never be repeated.")
        self.assertTrue(connection.closed)
        self.assertEqual(connection.debug, 0)
        self.assertFalse(result["retryAllowed"])
        self.assertFalse(result["visionVerified"], "Completion does not automatically attest image understanding.")
        self.assertNotIn(TOKEN, json.dumps(result))
        self.assertNotIn("Authorization", result)
        self.assertNotIn("usage", result)
        return result, connection


    def test_complete_multiline_sse_and_utf8_split_boundaries_preserve_full_text(self):
        for newline in (b"\n", b"\r", b"\r\n"):
            with self.subTest(newline=newline):
                result, _ = self.check(b"\xef\xbb\xbf" + wire(created(), delta(TEXT[:5]), delta(TEXT[5:], 2),
                    completed(sequence=3), newline=newline, multiline=True), block_size=1)
                self.assertTrue(result["ok"])
                self.assertTrue(result["responseCompleted"])
                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["output"], TEXT)
                self.assertEqual(result["requestId"], "req_fixture")
                self.assertEqual(result["actualModel"], "fixture-actual-model")
                self.assertTrue(result["requestStartedAt"])
                self.assertTrue(result["sentAt"])
                self.assertTrue(result["completedAt"])

    def test_failed_after_delta_preserves_subscription_machine_code_without_message(self):
        failed = event("response.failed", sequence_number=2, response={"id": "resp_fixture", "status": "failed",
            "error": {"code": "subscription_sharing_no_active_subscription", "message": TOKEN + " private details"}})
        result, _ = self.check(wire(created(), delta(), failed))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["code"], "subscription_sharing_no_active_subscription")
        self.assertEqual(result["output"], TEXT)
        self.assertFalse(result["responseCompleted"])

    def test_incomplete_and_error_keep_safe_event_or_response_code(self):
        for terminal in (
            event("response.incomplete", response={"id": "resp_fixture", "status": "incomplete",
                "error": {"code": "subscription_sharing_budget_exhausted", "message": TOKEN}}),
            event("error", error={"code": "subscription_sharing_budget_exhausted", "message": TOKEN}),
            event("error", code="subscription_sharing_budget_exhausted", message=TOKEN)):
            with self.subTest(kind=terminal["type"]):
                result, _ = self.check(wire(created(), delta(), terminal))
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["code"], "subscription_sharing_budget_exhausted")
                self.assertFalse(result["ok"])

    def test_unsafe_or_echoed_error_code_is_never_returned(self):
        for code in (TOKEN, "line\r\nAuthorization", "x" * 100, {"unexpected": TOKEN}):
            with self.subTest(code_type=type(code).__name__):
                result, _ = self.check(wire(event("error", error={"code": code, "message": TOKEN})))
                self.assertEqual(result["code"], "error")

    def test_delta_only_done_sentinel_and_uncommitted_terminal_are_unknown(self):
        for body in (wire(created(), delta()), wire(created(), delta()) + b"data: [DONE]\n\n",
                     wire(created(), delta(), completed()).removesuffix(b"\n")):
            result, _ = self.check(body)
            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(result["code"], "stream_ended_without_completed")
            self.assertFalse(result["responseCompleted"])

    def test_empty_completed_or_changed_delta_cannot_pass(self):
        for body, code in ((wire(created(), completed("")), "completed_output_empty"),
                           (wire(created(), delta("截断片段"), completed()), "completed_text_mismatch")):
            result, _ = self.check(body)
            self.assertFalse(result["ok"])
            self.assertEqual(result["code"], code)

    def test_duplicate_sequence_and_different_response_id_cannot_bind_a_completion(self):
        for body, code in ((wire(created(), delta(), completed(sequence=1)), "event_sequence_invalid"),
                           (wire(created(), delta(), completed(identifier="resp_other")), "response_identity_changed")):
            result, _ = self.check(body)
            self.assertFalse(result["ok"])
            self.assertEqual(result["code"], code)

    def test_http_redirect_does_not_follow_or_make_a_second_request(self):
        result, connection = self.check(b"", status=302, headers={"location": "https://unrelated.example/collect"})
        self.assertEqual(result["code"], "redirect_rejected")
        self.assertEqual(result["httpStatus"], 302)
        self.assertEqual(connection.requests[0][1], "/v1/responses")

    def test_http_subscription_error_keeps_only_safe_code_and_request_id(self):
        body = json.dumps({"error": {"code": "subscription_sharing_not_enabled", "message": TOKEN}}).encode()
        result, _ = self.check(body, status=403)
        self.assertEqual(result["code"], "subscription_sharing_not_enabled")
        self.assertEqual(result["requestId"], "req_fixture")
        self.assertEqual(result["httpStatus"], 403)

    def test_unknown_request_write_performs_exactly_one_post_and_no_retry(self):
        result, _ = self.check(b"", send_error=True)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["code"], "network_timeout")
        self.assertIsNotNone(result["requestStartedAt"])
        self.assertIsNone(result["sentAt"])

    def test_non_json_http_rejection_is_not_mislabeled_as_invalid_user_arguments(self):
        result, _ = self.check(b"upstream unavailable", status=503)
        self.assertEqual(result["code"], "http_rejected")
        self.assertEqual(result["httpStatus"], 503)
        self.assertEqual(result["status"], "failed")

    def test_connection_close_response_uses_original_transport_for_bounded_stream_reads(self):
        result, _ = self.check(wire(created(), delta(), completed()), close_on_headers=True)
        self.assertTrue(result["ok"])

    def test_output_bound_rejects_instead_of_truncating_and_claiming_completion(self):
        result, _ = self.check(wire(created(), delta("x" * (probe.MAX_OUTPUT_CHARS + 1)), completed()), block_size=4096)
        self.assertEqual(result["code"], "output_too_large")
        self.assertFalse(result["ok"])
        self.assertFalse(result["responseCompleted"])

    def test_invalid_arguments_never_open_a_socket(self):
        with patch.object(probe.http.client, "HTTPSConnection", side_effect=AssertionError("No socket allowed")):
            for token, model in (("", MODEL), (TOKEN + "\r\n", MODEL), (TOKEN, "bad slug")):
                result = probe.run_response(token, model, INPUT_ITEMS)
                self.assertEqual(result["status"], "not_sent")
                self.assertEqual(result["code"], "invalid_arguments")


    def test_wrong_or_absent_mime_actual_sse_still_requires_real_complete_event(self):
        body = b"\xef\xbb\xbf: actual comment\r\n\r\n" + wire(created(), delta(), completed(), newline=b"\r\n")
        for content_type in ("application/json; charset=utf-8", "text/plain", None):
            with self.subTest(content_type=content_type):
                result, _ = self.check(body, headers={"content-type": content_type}, diagnostic=True)
                self.assertTrue(result["ok"])
                self.assertTrue(result["responseCompleted"])
                self.assertTrue(result["mimeMismatch"])
                self.assertEqual(result["bodyClass"], "sse_candidate")
                self.assertEqual(result["bodyBytes"], len(body))
                self.assertEqual(result["bodySha256"], hashlib.sha256(body).hexdigest())
                self.assertFalse(result["bodyTruncated"])
                self.assertEqual(result["output"], TEXT)

    def test_wrong_mime_sse_does_not_bypass_identity_sequence_text_or_terminal_guards(self):
        cases = (
            (wire(created(), delta(), completed(identifier="resp_other")), "response_identity_changed"),
            (wire(created(), delta(), completed(sequence=1)), "event_sequence_invalid"),
            (wire(created(), delta("different"), completed()), "completed_text_mismatch"),
            (wire(created(), completed("")), "completed_output_empty"),
            (wire(created(), delta()), "stream_ended_without_completed"),
            (wire(created(), delta(), completed()).removesuffix(b"\n"), "stream_ended_without_completed"))
        for body, code in cases:
            with self.subTest(code=code):
                result, _ = self.check(body, headers={"content-type": "text/plain"}, diagnostic=True)
                self.assertFalse(result["ok"])
                self.assertFalse(result["responseCompleted"])
                self.assertEqual(result["code"], code)

    def test_json_completed_is_diagnostic_only_and_never_validates_stream(self):
        value = dict(completed()["response"], object="response", usage={"secret": TOKEN})
        body = json.dumps(value, ensure_ascii=False).encode()
        result, _ = self.check(body, headers={"content-type": "application/json"}, diagnostic=True)
        self.assertFalse(result["ok"])
        self.assertFalse(result["responseCompleted"])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["code"], "unexpected_content_type")
        self.assertEqual(result["output"], "")
        self.assertEqual(result["bodyClass"], "json_response")
        self.assertEqual(result["diagnosticResponseStatus"], "completed")
        self.assertEqual(result["diagnosticResponseId"], "resp_fixture")
        self.assertEqual(result["diagnosticModel"], "fixture-actual-model")
        self.assertEqual(result["diagnosticOutput"], TEXT)
        self.assertIsNone(result["responseId"])
        self.assertIsNone(result["actualModel"])

    def test_json_error_keeps_safe_code_and_param_without_raw_message_or_detail(self):
        body = json.dumps({"error": {"code": "subscription_sharing_unsupported_capability",
            "param": "input[0].content", "message": TOKEN}, "detail": TOKEN}).encode()
        for status in (200, 400):
            with self.subTest(status=status):
                result, _ = self.check(body, status=status, headers={"content-type": "application/json"}, diagnostic=True)
                self.assertEqual(result["bodyClass"], "json_error")
                self.assertEqual(result["code"], "subscription_sharing_unsupported_capability")
                self.assertEqual(result["errorParam"], "input[0].content")
                self.assertEqual(result["status"], "failed")
                self.assertFalse(result["responseCompleted"])
                self.assertNotIn("message", result)
                self.assertNotIn("detail", result)

    def test_html_and_detail_only_json_keep_shape_hash_but_no_raw_body(self):
        for body, kind in ((b"<!DOCTYPE html><html><body>" + TOKEN.encode() + b"</body></html>", "html"),
                           (json.dumps({"detail": TOKEN}).encode(), "json_other"),
                           (b"", "empty"), (b"\xff\xfe", "binary")):
            with self.subTest(kind=kind):
                result, _ = self.check(body, headers={"content-type": "text/html"}, diagnostic=True)
                self.assertEqual(result["bodyClass"], kind)
                self.assertEqual(result["bodyBytes"], len(body))
                self.assertEqual(result["bodySha256"], hashlib.sha256(body).hexdigest())
                self.assertEqual(result["code"], "unexpected_content_type")
                self.assertEqual(result["diagnosticOutput"], "")
                self.assertFalse(result["ok"])

    def test_diagnostic_reads_at_most_cap_and_prefix_cannot_prove_completion(self):
        body = b"<!doctype html>" + b"x" * probe.MAX_DIAGNOSTIC_BYTES
        result, connection = self.check(body, headers={"content-type": "text/plain"}, block_size=4096,
                                        diagnostic=True)
        self.assertEqual(connection.response.offset, probe.MAX_DIAGNOSTIC_BYTES)
        self.assertEqual(result["bodyBytes"], probe.MAX_DIAGNOSTIC_BYTES)
        self.assertEqual(result["bodySha256"], hashlib.sha256(body[:probe.MAX_DIAGNOSTIC_BYTES]).hexdigest())
        self.assertTrue(result["bodyTruncated"])
        self.assertEqual(result["bodyClass"], "truncated")
        self.assertEqual(result["code"], "diagnostic_body_too_large")
        self.assertFalse(result["responseCompleted"])

    def test_generic_text_history_and_selected_image_are_serialized_exactly_without_mutation(self):
        part = dict(image_part(), detail="high")
        items = [{"type": "message", "role": "system", "content": "已确认的固定规则。"},
                 {"role": "assistant", "content": [{"type": "output_text", "text": "保留既有回答与换行。\n"}]},
                 {"role": "user", "content": [{"type": "input_text", "text": "时间：原确认时间\n原问题 ‘你好’！ 🧭"}, part]}]
        before = json.dumps(items, ensure_ascii=False)
        result, connection = self.check(wire(created(), delta(), completed()), input_items=items)
        method, path, body, _ = connection.requests[0]
        payload = json.loads(body)
        self.assertEqual((method, path), ("POST", "/v1/responses"))
        self.assertEqual(set(payload), {"model", "input", "store", "stream"})
        self.assertIs(payload["store"], False)
        self.assertIs(payload["stream"], True)
        self.assertEqual(payload["input"], items)
        self.assertEqual(json.dumps(items, ensure_ascii=False), before)
        self.assertEqual(base64.b64decode(payload["input"][-1]["content"][-1]["image_url"].split(",", 1)[1]), fixture_png())
        self.assertEqual(result["requestSha256"], hashlib.sha256(body).hexdigest())
        frozen_input = json.dumps(items, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        self.assertEqual(result["inputSha256"], hashlib.sha256(frozen_input).hexdigest())
        self.assertEqual(result["output"], TEXT)
        self.assertTrue(result["ok"])

    def test_image_only_and_four_supported_data_urls_preserve_complete_input(self):
        for media in ("png", "jpeg", "webp", "gif"):
            original_image = fixture_image(media)
            part = image_part(original_image)
            part["image_url"] = part["image_url"].replace("image/png", "image/" + media)
            items = [{"role": "user", "content": [part]}]
            result, connection = self.check(wire(created(), delta(), completed()), input_items=items)
            self.assertEqual(json.loads(connection.requests[0][2])["input"], items)
            self.assertEqual(base64.b64decode(json.loads(connection.requests[0][2])["input"][0]["content"][0]["image_url"].split(",", 1)[1]), original_image)
            self.assertTrue(result["ok"])
        items = [{"role": "user", "content": [image_part() for _ in range(4)]}]
        result, connection = self.check(wire(created(), delta(), completed()), input_items=items)
        self.assertEqual(json.loads(connection.requests[0][2])["input"], items)
        self.assertTrue(result["ok"])

    def test_invalid_or_oversized_frozen_input_is_unsent_without_a_socket_or_truncation(self):
        invalid = ([], "not-an-array", [{"role": "tool", "content": "unsupported"}],
                   [{"role": "user", "content": "   "}], [{"role": "user", "content": [], "createdAt": "not-API-input"}],
                   [{"role": "user", "content": [{"type": "input_file", "file_id": "file_unused"}]}],
                   [{"role": "user", "content": [{"type": "input_image", "image_url": "https://example.invalid/private.png"}]}],
                   [{"role": "user", "content": [{"type": "input_image", "image_url": "data:image/png;base64,%%"}]}],
                   [{"role": "user", "content": [image_part() for _ in range(5)]}])
        with patch.object(probe.http.client, "HTTPSConnection", side_effect=AssertionError("No socket allowed")):
            for items in invalid:
                with self.subTest(items=repr(items)[:100]):
                    result = probe.run_response(TOKEN, MODEL, items)
                    self.assertEqual(result["status"], "not_sent")
                    self.assertFalse(result["ok"])
                    self.assertIsNone(result["requestSha256"])
            with patch.object(probe, "MAX_REQUEST_BYTES", 50):
                result = probe.run_response(TOKEN, MODEL, INPUT_ITEMS)
                self.assertEqual(result["code"], "request_too_large")
            with patch.object(probe, "MAX_IMAGE_BYTES", 8):
                result = probe.run_response(TOKEN, MODEL, [{"role": "user", "content": [image_part(b"123456789")]}])
                self.assertEqual(result["code"], "input_image_too_large")
            with patch.object(probe, "MAX_TOTAL_IMAGE_BYTES", len(fixture_png()) * 3):
                result = probe.run_response(TOKEN, MODEL, [{"role": "user", "content": [image_part() for _ in range(4)]}])
                self.assertEqual(result["code"], "input_image_too_large")

    def test_long_unicode_output_over_legacy_limits_is_complete_even_without_mime(self):
        text = "长回复 🧭\n" * 12000
        self.assertGreater(len(text.encode()), probe.MAX_DIAGNOSTIC_BYTES)
        self.assertLess(len(text), probe.MAX_OUTPUT_CHARS)
        terminal = completed(sequence=2)
        terminal["response"]["output"] = []
        for mime in ("text/event-stream", "", "text/plain"):
            result, connection = self.check(wire(created(), delta(text), terminal),
                headers={"content-type": mime}, block_size=4096)
            self.assertTrue(result["ok"])
            self.assertEqual(result["output"], text)
            self.assertTrue(result["terminalEventObserved"])
            self.assertEqual(result["completionSource"], "completed_stream_deltas")
            self.assertGreater(connection.response.offset, probe.MAX_DIAGNOSTIC_BYTES)

    def test_total_deadline_allows_a_completed_request_after_legacy_120_seconds_without_sleep(self):
        calls = 0
        def clock():
            nonlocal calls
            calls += 1
            return 0 if calls == 1 else 150
        with patch.object(probe.time, "monotonic", side_effect=clock):
            result, connection = self.check(wire(created(), delta(), completed()))
        self.assertTrue(result["ok"])
        self.assertGreater(max(connection.original_socket.timeouts), 30)
        self.assertLessEqual(max(connection.original_socket.timeouts), 120)

    def test_missing_mime_bom_comments_and_partial_sse_field_use_only_same_response(self):
        body = b"\xef\xbb\xbf:heartbeat\r\n\r\n" + wire(created(), delta(), completed(), newline=b"\r\n")
        result, connection = self.check(body, headers={"content-type": ""}, block_size=1)
        self.assertTrue(result["ok"])
        self.assertEqual(result["output"], TEXT)
        self.assertEqual(result["bodySha256"], hashlib.sha256(body).hexdigest())
        self.assertEqual(connection.connect_count, 1)

    def test_missing_mime_long_delta_only_and_comment_prefix_cap_cannot_complete(self):
        text = "尚无终态" * 20000
        result, _ = self.check(wire(created(), delta(text)), headers={"content-type": ""}, block_size=4096)
        self.assertFalse(result["ok"])
        self.assertFalse(result["terminalEventObserved"])
        self.assertEqual(result["code"], "stream_ended_without_completed")
        result, connection = self.check(b":" + b"x" * probe.MAX_DIAGNOSTIC_BYTES,
            headers={"content-type": ""}, block_size=4096)
        self.assertEqual(connection.response.offset, probe.MAX_DIAGNOSTIC_BYTES)
        self.assertEqual(result["code"], "diagnostic_body_too_large")
        self.assertFalse(result["responseCompleted"])

    def test_stream_and_event_caps_keep_received_prefix_unsuccessful(self):
        body = wire(created(), delta(), completed())
        for name, maximum, code in (("MAX_STREAM_BYTES", 100, "stream_too_large"),
                                    ("MAX_EVENT_BYTES", 100, "event_too_large")):
            with patch.object(probe, name, maximum):
                result, _ = self.check(body, headers={"content-type": ""}, block_size=7)
                self.assertFalse(result["ok"])
                self.assertFalse(result["responseCompleted"])
                self.assertEqual(result["code"], code)

    def test_header_and_json_fields_cannot_echo_token_and_diagnostic_text_is_redacted(self):
        value = dict(completed(TEXT + TOKEN)["response"], object="response")
        body = json.dumps(value).encode()
        result, _ = self.check(body, headers={"content-type": "application/json; note=" + TOKEN,
            "x-request-id": TOKEN}, diagnostic=True)
        self.assertIsNone(result["mediaType"])
        self.assertIsNone(result["requestId"])
        self.assertIn("[credential redacted]", result["diagnosticOutput"])
        for fields in ({"id": TOKEN}, {"model": TOKEN}, {"status": {"private": TOKEN}}):
            value = dict(completed()["response"], object="response", **fields)
            result, _ = self.check(json.dumps(value).encode(), headers={"content-type": "application/json"}, diagnostic=True)
            self.assertEqual(result["diagnosticOutput"], "")
            self.assertFalse(result["ok"])
        result, _ = self.check(json.dumps({"error": {"code": TOKEN, "param": TOKEN}}).encode(),
            headers={"content-type": "application/json"}, diagnostic=True)
        self.assertIsNone(result["errorParam"])
        self.assertEqual(result["code"], "unexpected_content_type")

    def test_non_identity_or_invalid_encoding_never_parses_sse_or_json_completion(self):
        for encoding in ("gzip", TOKEN, "identity, gzip"):
            result, _ = self.check(wire(created(), delta(), completed()), headers={
                "content-type": "text/plain", "content-encoding": encoding}, diagnostic=True)
            self.assertEqual(result["bodyClass"], "encoded")
            self.assertFalse(result["ok"])
            self.assertFalse(result["responseCompleted"])

    def test_diagnostic_reader_obeys_deadline_and_keeps_only_read_prefix_facts(self):
        result = {}
        response, transport = FakeResponse(b"x" * 100), FakeSocket()
        with patch.object(probe.time, "monotonic", side_effect=[0, 2]):
            with self.assertRaises(probe._Stop) as failure:
                probe._diagnostic_body(response, transport, 1, result)
        self.assertEqual(failure.exception.code, "deadline_exceeded")
        self.assertEqual(response.offset, 7)
        self.assertEqual(result["bodyBytes"], 7)
        self.assertEqual(result["bodySha256"], hashlib.sha256(b"x" * 7).hexdigest())

    def test_diagnostic_unknown_and_redirect_each_make_only_original_post(self):
        result, _ = self.check(b"", send_error=True, diagnostic=True)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["code"], "network_timeout")
        result, _ = self.check(b"not followed", status=302,
            headers={"location": "https://unrelated.example/collect"}, diagnostic=True)
        self.assertEqual(result["code"], "redirect_rejected")


    def test_real_completed_with_absent_empty_or_reasoning_snapshot_accepts_bound_deltas_without_done_chain(self):
        for kind in ("absent", "empty", "reasoning_only"):
            terminal = completed()
            if kind == "absent":
                terminal["response"].pop("output")
            elif kind == "empty":
                terminal["response"]["output"] = []
            else:
                terminal["response"]["output"] = [{"type": "reasoning", "id": "rs_fixture", "summary": []}]
            for content_type in ("text/event-stream", None):
                with self.subTest(kind=kind, mime=content_type):
                    output_index = 1 if kind == "reasoning_only" else 0
                    result, _ = self.check(wire(created(), dict(delta(TEXT[:5]), output_index=output_index),
                        dict(delta(TEXT[5:], 2), output_index=output_index),
                        dict(terminal, sequence_number=3)), headers={"content-type": content_type}, verification=True)
                    self.assertTrue(result["ok"])
                    self.assertTrue(result["responseCompleted"])
                    self.assertTrue(result["terminalEventObserved"])
                    self.assertEqual(result["terminalStatus"], "completed")
                    self.assertEqual(result["terminalOutputKind"], kind)
                    self.assertEqual(result["terminalTextValidation"], "stream_deltas")
                    self.assertEqual(result["completionEvidence"], "response.completed")
                    self.assertEqual(result["completionSource"], "completed_stream_deltas")
                    self.assertEqual(result["output"], TEXT)

    def test_terminal_fact_is_independent_of_empty_text_or_snapshot_mismatch_validation(self):
        for body, kind, validation, code in (
            (wire(created(), completed("")), "assistant_empty", "empty", "completed_output_empty"),
            (wire(created(), delta(), completed("")), "assistant_empty", "mismatch", "completed_text_mismatch"),
            (wire(created(), delta("different"), completed()), "text", "mismatch", "completed_text_mismatch"),
            (wire(created(), dict(completed(), response=dict(completed()["response"], output=[]))),
                "empty", "empty", "completed_output_empty"),
            (wire(created(), delta(), dict(completed(), response=dict(completed()["response"], output=None))),
                "invalid", "invalid", "completed_output_invalid")):
            with self.subTest(kind=kind, validation=validation):
                result, _ = self.check(body, verification=True)
                self.assertFalse(result["ok"])
                self.assertFalse(result["responseCompleted"])
                self.assertTrue(result["terminalEventObserved"])
                self.assertEqual(result["terminalOutputKind"], kind)
                self.assertEqual(result["terminalTextValidation"], validation)
                self.assertEqual(result["code"], code)
                self.assertEqual(result["completionEvidence"], "response.completed")
                self.assertIsNone(result["completionSource"])
                self.assertFalse(result["providerErrorObserved"])
                self.assertEqual(result["failureOrigin"], "parser")

    def test_partial_stream_or_error_code_resembling_local_completion_failure_does_not_prove_terminal(self):
        for body in (wire(created(), delta()), wire(created(), delta(), event("error", code="completed_output_empty")),
                     wire(created(), delta(), event("response.failed", response={"id": "resp_fixture", "status": "failed",
                         "error": {"code": "completed_output_empty", "message": TOKEN}}))):
            result, _ = self.check(body, verification=True)
            self.assertFalse(result["ok"])
            self.assertFalse(result["terminalEventObserved"])
            self.assertFalse(result["responseCompleted"])
            self.assertIsNone(result["completionEvidence"])
            self.assertIsNone(result["completionSource"])
            self.assertEqual(result["output"], TEXT)
            if result["code"] == "completed_output_empty":
                self.assertTrue(result["providerErrorObserved"])
                self.assertEqual(result["failureOrigin"], "provider")

    def test_invalid_completed_status_or_error_never_sets_validated_terminal_fact(self):
        for fields in ({"status": "failed"}, {"status": "incomplete"}, {"error": {"code": "server_error"}},
                       {"incomplete_details": {"reason": "limit"}}):
            terminal = completed()
            terminal["response"].update(fields)
            result, _ = self.check(wire(created(), delta(), terminal), verification=True)
            self.assertEqual(result["code"], "completed_status_invalid")
            self.assertFalse(result["terminalEventObserved"])
            self.assertIsNone(result["completionEvidence"])

    def test_optional_done_events_validate_text_but_are_not_required_to_complete(self):
        text_done = event("response.output_text.done", sequence_number=2, item_id="msg_fixture", output_index=0,
                          content_index=0, text=TEXT)
        item_done = event("response.output_item.done", sequence_number=3, output_index=0,
                          item=completed()["response"]["output"][0])
        terminal = completed(sequence=4)
        terminal["response"]["output"] = []
        result, _ = self.check(wire(created(), delta(), text_done, item_done, terminal), verification=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["output"], TEXT)
        self.assertEqual(result["completionSource"], "completed_stream_deltas")
        for bad_event in (dict(text_done, text="different"),
                          dict(item_done, item=completed("different")["response"]["output"][0])):
            result, _ = self.check(wire(created(), delta(), bad_event, terminal), verification=True)
            self.assertFalse(result["ok"])
            self.assertEqual(result["code"], "completed_text_mismatch")

    def test_optional_done_without_terminal_or_later_failure_cannot_complete(self):
        text_done = event("response.output_text.done", sequence_number=2, item_id="msg_fixture", output_index=0,
                          content_index=0, text=TEXT)
        for tail in ([], [event("response.failed", sequence_number=3, response={"id": "resp_fixture", "status": "failed",
                "error": {"code": "subscription_sharing_usage_limit_exceeded"}})]):
            result, _ = self.check(wire(created(), delta(), text_done, *tail), verification=True)
            self.assertFalse(result["ok"])
            self.assertFalse(result["terminalEventObserved"])
            self.assertFalse(result["responseCompleted"])

    def test_delta_is_bound_to_prior_response_and_unique_item_index_before_fallback(self):
        terminal = completed(sequence=3)
        terminal["response"]["output"] = []
        cases = ((wire(delta(), terminal), "stream_response_unbound"),
                 (wire(created(), delta(), dict(delta(sequence=2), item_id="msg_other"), terminal),
                     "stream_item_identity_changed"),
                 (wire(created(), delta(), dict(delta(sequence=2), output_index=1), terminal),
                     "stream_item_identity_changed"))
        for body, code in cases:
            result, _ = self.check(body, verification=True)
            self.assertFalse(result["ok"])
            self.assertEqual(result["code"], code)

    def test_delta_after_done_and_duplicate_done_never_silently_changes_fallback_text(self):
        text_done = event("response.output_text.done", sequence_number=2, item_id="msg_fixture", output_index=0,
                          content_index=0, text=TEXT)
        terminal = completed(sequence=4)
        terminal["response"]["output"] = []
        for middle, code in ((delta("extra", 3), "text_after_done"),
                             (dict(text_done, sequence_number=3), "text_done_invalid")):
            result, _ = self.check(wire(created(), delta(), text_done, middle, terminal), verification=True)
            self.assertFalse(result["ok"])
            self.assertEqual(result["code"], code)

    def test_full_snapshot_authority_preserves_mismatch_gate_and_reports_source(self):
        for events, validation in (([created(), delta(), completed()], "snapshot_matches"),
                                   ([created(), completed()], "snapshot_only")):
            result, _ = self.check(wire(*events), verification=True)
            self.assertTrue(result["ok"])
            self.assertEqual(result["terminalOutputKind"], "text")
            self.assertEqual(result["terminalTextValidation"], validation)
            self.assertEqual(result["completionSource"], "terminal_snapshot")
        terminal = completed()
        terminal["response"]["model"] = "other-model"
        result, _ = self.check(wire(created(), delta(), terminal), verification=True)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "response_model_changed")

    def test_json_completed_never_sets_new_terminal_event_facts(self):
        body = json.dumps(dict(completed()["response"], object="response")).encode()
        result, _ = self.check(body, headers={"content-type": "application/json"}, verification=True)
        self.assertEqual(result["diagnosticOutput"], TEXT)
        self.assertFalse(result["terminalEventObserved"])
        self.assertFalse(result["ok"])
        self.assertIsNone(result["completionEvidence"])

    def test_text_delta_cannot_change_same_item_to_reasoning_in_added_or_terminal_snapshot(self):
        reasoning = {"id": "msg_fixture", "type": "reasoning", "summary": []}
        terminal = completed(sequence=3)
        terminal["response"]["output"] = [reasoning]
        for body in (wire(created(), delta(), event("response.output_item.added", sequence_number=2,
                           output_index=0, item=reasoning), terminal),
                     wire(created(), delta(), terminal)):
            result, _ = self.check(body, verification=True)
            self.assertFalse(result["ok"])
            self.assertFalse(result["responseCompleted"])
            self.assertEqual(result["code"], "unexpected_output_kind")
            self.assertIsNone(result["completionSource"])

    def test_terminal_snapshot_cannot_replace_added_only_item_identity_or_kind(self):
        message = {"id": "msg_original", "type": "message", "role": "assistant", "status": "in_progress", "content": []}
        reasoning = {"id": "rs_original", "type": "reasoning", "summary": []}
        cases = (
            (message, completed()["response"]["output"][0], "stream_item_identity_changed"),
            (reasoning, {"id": "rs_replacement", "type": "reasoning", "summary": []}, "stream_item_identity_changed"),
            (reasoning, dict(completed()["response"]["output"][0], id="rs_original"), "unexpected_output_kind"))
        for added_item, final_item, code in cases:
            terminal = completed()
            terminal["response"]["output"] = [final_item]
            result, _ = self.check(wire(created(), event("response.output_item.added", sequence_number=1,
                output_index=0, item=added_item), terminal), verification=True)
            self.assertFalse(result["ok"])
            self.assertFalse(result["responseCompleted"])
            self.assertTrue(result["terminalEventObserved"])
            self.assertEqual(result["terminalTextValidation"], "mismatch")
            self.assertEqual(result["code"], code)
            self.assertIsNone(result["completionSource"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
