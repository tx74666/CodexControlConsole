"""Bounded, single-POST Responses transport for an approved subscription request.

Importing performs no I/O. The caller owns credentials, granted scopes, the
account model catalog and a durable one-use reservation for the frozen input.
This module never reads credential files, scans attachments, refreshes tokens,
follows redirects or retries an unknown request. Only a validated actual
response.completed event plus complete nonempty text makes a result successful.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
import hashlib
import http.client
import json
import re
import socket
import ssl
import time

MAX_RETRIES = 0
MAX_SECONDS = 600
MAX_IDLE_SECONDS = 120
MAX_STREAM_BYTES = 8 * 1024 * 1024
MAX_EVENT_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_CHARS = 128 * 1024
MAX_EVENTS = 200000
MAX_DIAGNOSTIC_BYTES = 64 * 1024
MAX_REQUEST_BYTES = 48 * 1024 * 1024
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 24 * 1024 * 1024
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}\Z")
_ID = re.compile(r"[A-Za-z0-9._:-]{1,200}\Z")
_CODE = re.compile(r"[a-z][a-z0-9_]{0,79}\Z")
_PARAM = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\[\]-]{0,119}\Z")
_MEDIA = re.compile(r"[a-z0-9][a-z0-9!#$&^_.+-]{0,63}/[a-z0-9][a-z0-9!#$&^_.+-]{0,63}\Z")
_ENCODING = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}\Z")
_STATUSES = {"completed", "failed", "incomplete", "in_progress", "queued", "cancelled"}


def _payload(model_slug, input_items):
    """Validate bounded message input without changing its text, roles or images."""
    if type(input_items) is not list or not 1 <= len(input_items) <= 512:
        raise _Stop("input_invalid", "not_sent")
    images, image_bytes, has_content = 0, 0, False
    for item in input_items:
        if (type(item) is not dict or set(item) - {"role", "content", "type"}
                or item.get("role") not in {"user", "assistant", "system", "developer"}
                or item.get("type", "message") != "message"):
            raise _Stop("input_invalid", "not_sent")
        content = item.get("content")
        if type(content) is str:
            has_content = has_content or bool(content.strip())
            continue
        if type(content) is not list or not 1 <= len(content) <= 128:
            raise _Stop("input_invalid", "not_sent")
        for part in content:
            if type(part) is not dict:
                raise _Stop("input_invalid", "not_sent")
            kind = part.get("type")
            if kind in {"input_text", "output_text"}:
                if set(part) != {"type", "text"} or type(part.get("text")) is not str:
                    raise _Stop("input_invalid", "not_sent")
                if kind == "output_text" and item["role"] != "assistant":
                    raise _Stop("input_invalid", "not_sent")
                has_content = has_content or bool(part["text"].strip())
            elif kind == "input_image":
                if (set(part) - {"type", "image_url", "detail"} or "image_url" not in part
                        or part.get("detail", "auto") not in {"auto", "low", "high"}
                        or item["role"] != "user" or type(part["image_url"]) is not str):
                    raise _Stop("input_invalid", "not_sent")
                prefix, separator, encoded = part["image_url"].partition(",")
                if (not separator or prefix not in {"data:image/png;base64", "data:image/jpeg;base64",
                        "data:image/webp;base64", "data:image/gif;base64"}
                        or not encoded or len(encoded) > 4 * ((MAX_IMAGE_BYTES + 2) // 3)):
                    raise _Stop("input_image_invalid", "not_sent")
                try:
                    decoded = base64.b64decode(encoded, validate=True)
                except (ValueError, binascii.Error):
                    raise _Stop("input_image_invalid", "not_sent") from None
                count = len(decoded)
                del decoded
                images, image_bytes = images + 1, image_bytes + count
                if not count or count > MAX_IMAGE_BYTES or images > MAX_IMAGES or image_bytes > MAX_TOTAL_IMAGE_BYTES:
                    raise _Stop("input_image_too_large", "not_sent")
                has_content = True
            else:
                raise _Stop("input_invalid", "not_sent")
    if not has_content:
        raise _Stop("input_empty", "not_sent")
    try:
        encoded_input = json.dumps(input_items, ensure_ascii=False, separators=(",", ":"),
                                   sort_keys=True, allow_nan=False).encode("utf-8")
        body = json.dumps({"model": model_slug, "store": False, "stream": True, "input": input_items},
                          ensure_ascii=False, separators=(",", ":"), sort_keys=True,
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise _Stop("input_invalid", "not_sent") from None
    if len(body) > MAX_REQUEST_BYTES:
        raise _Stop("request_too_large", "not_sent")
    return body, hashlib.sha256(encoded_input).hexdigest()


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _safe(value, pattern, secret):
    return value if isinstance(value, str) and secret not in value and pattern.fullmatch(value) else None


class _Stop(Exception):
    def __init__(self, code, status="unknown"):
        self.code, self.status = code, status


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _Stop("deadline_exceeded")
    return min(MAX_IDLE_SECONDS, remaining)


def _header_value(value, pattern, secret, *, media=False):
    # Return only a normalized grammar token, never the raw header or parameters.
    if not isinstance(value, str) or len(value) > 256 or secret.casefold() in value.casefold():
        return None
    normalized = (value.split(";", 1)[0] if media else value).strip().lower()
    return _safe(normalized, pattern, secret)


def _diagnostic_body(response, transport, deadline, result, prefix=b""):
    """Read only this response, at most 64 KiB; hash identifies the read prefix.

    Reaching the cap is conservatively marked truncated, even at exact length:
    no extra byte is read to prove EOF and a truncated prefix never proves success.
    """
    body = bytearray(prefix)
    digest = hashlib.sha256(prefix)
    result.update(bodyBytes=len(prefix), bodySha256=digest.hexdigest(), bodyTruncated=False)
    while len(body) < MAX_DIAGNOSTIC_BYTES:
        transport.settimeout(_remaining(deadline))
        block = response.read1(min(4096, MAX_DIAGNOSTIC_BYTES - len(body)))
        if not block:
            return bytes(body)
        body.extend(block)
        digest.update(block)
        result.update(bodyBytes=len(body), bodySha256=digest.hexdigest())
    result.update(bodyClass="truncated", bodyTruncated=True)
    return bytes(body)


class _PrefixedResponse:
    """Continue the same HTTP response after MIME sniffing; never reconnect."""
    def __init__(self, prefix, response, result):
        self.prefix, self.offset, self.response, self.result = prefix, 0, response, result
        self.digest, self.total = hashlib.sha256(prefix), len(prefix)
        result.update(bodyClass="sse_candidate", bodyBytes=self.total,
                      bodySha256=self.digest.hexdigest(), bodyTruncated=False)

    def read1(self, size):
        if self.offset < len(self.prefix):
            block = self.prefix[self.offset:self.offset + size]
            self.offset += len(block)
            return block
        block = self.response.read1(size)
        self.total += len(block)
        self.digest.update(block)
        self.result.update(bodyBytes=self.total, bodySha256=self.digest.hexdigest())
        return block


def _sse_prefix_kind(prefix):
    if len(prefix) < 3 and b"\xef\xbb\xbf".startswith(prefix):
        return None
    data = prefix.removeprefix(b"\xef\xbb\xbf")
    lines = re.split(br"\r\n|\r|\n", data)
    for index, line in enumerate(lines):
        if not line or line.startswith(b":"):
            continue
        if line.startswith((b"event:", b"data:")):
            return True
        if index == len(lines) - 1 and any(field.startswith(line) for field in (b"event:", b"data:")):
            return None
        return False
    return None


def _mime_response(response, transport, deadline, result):
    """Sniff at most 64 KiB; only actual SSE continues under the 8 MiB cap.

Non-SSE bodies remain diagnostics only. Body hashes describe bytes read, not an
unread remainder. A valid completed event is still required by the same decoder.
"""
    prefix = bytearray()
    while len(prefix) < MAX_DIAGNOSTIC_BYTES:
        transport.settimeout(_remaining(deadline))
        block = response.read1(min(4096, MAX_DIAGNOSTIC_BYTES - len(prefix)))
        prefix.extend(block)
        kind = _sse_prefix_kind(bytes(prefix))
        if kind is True:
            return _PrefixedResponse(bytes(prefix), response, result), None
        if kind is False or not block:
            return None, _diagnostic_body(response, transport, deadline, result, bytes(prefix))
    result.update(bodyClass="truncated", bodyBytes=len(prefix), bodyTruncated=True,
                  bodySha256=hashlib.sha256(prefix).hexdigest())
    return None, bytes(prefix)


def _error_fields(error, result, secret):
    if not isinstance(error, dict):
        return None
    result.update(providerErrorObserved=True, failureOrigin="provider")
    code = _safe(error.get("code"), _CODE, secret)
    result["errorParam"] = _safe(error.get("param"), _PARAM, secret)
    return code


def _classify_body(body, result, secret):
    """Project bounded facts only; a JSON completed object is not an SSE event."""
    if result["bodyTruncated"]:
        return None
    if result["contentEncoding"] != "identity":
        result["bodyClass"] = "encoded"
        return None
    if not body:
        result["bodyClass"] = "empty"
        return None
    try:
        text = body.decode("utf-8-sig", errors="strict")
    except UnicodeError:
        result["bodyClass"] = "binary"
        return None
    try:
        value = json.loads(text)
        json_valid = True
    except ValueError:
        value = None
        json_valid = False
    if isinstance(value, dict):
        if isinstance(value.get("error"), dict):
            result["bodyClass"] = "json_error"
            code = _error_fields(value["error"], result, secret)
            return code
        if value.get("object") == "response" or "status" in value and "output" in value and "id" in value:
            result["bodyClass"] = "json_response"
            status = value.get("status")
            result["diagnosticResponseStatus"] = status if isinstance(status, str) and status in _STATUSES else None
            result["diagnosticResponseId"] = _safe(value.get("id"), _ID, secret)
            result["diagnosticModel"] = _safe(value.get("model"), _MODEL, secret)
            # Diagnostic text is accepted only from the same completed assistant
            # shape used by SSE. It does not set ok/responseCompleted/output.
            if (result["diagnosticResponseStatus"] == "completed" and result["diagnosticResponseId"]
                    and result["diagnosticModel"] and value.get("error") is None
                    and value.get("incomplete_details") is None):
                try:
                    output, _ = _final_output(value, secret)
                    result["diagnosticOutput"] = output.replace(secret, "[credential redacted]")
                except (_Stop, TypeError):
                    pass
            return None
        result["bodyClass"] = "json_other"
        return None
    if json_valid:
        result["bodyClass"] = "json_other"
        return None
    stripped = text.lstrip()
    if stripped.lower().startswith(("<!doctype html", "<html", "<head", "<body")):
        result["bodyClass"] = "html"
        return None
    # Sniff only the first non-comment SSE field; the existing decoder then
    # validates every actual event, identity, sequence and terminal completion.
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line or line.startswith(":"):
            continue
        result["bodyClass"] = "sse_candidate" if line.startswith(("event:", "data:")) else "text"
        return None
    result["bodyClass"] = "text"
    return None


def _events(response, transport, deadline):
    """Bounded SSE frames; CR/LF/CRLF and multiple data lines are supported."""
    buffer, total, event, data, event_size, first_line = b"", 0, "", [], 0, True
    while True:
        transport.settimeout(_remaining(deadline))
        block = response.read1(4096)
        total += len(block)
        if total > MAX_STREAM_BYTES:
            raise _Stop("stream_too_large")
        buffer += block
        while buffer:
            positions = [index for index in (buffer.find(b"\r"), buffer.find(b"\n")) if index >= 0]
            if not positions:
                break
            index = min(positions)
            if buffer[index:index + 1] == b"\r" and index + 1 == len(buffer) and block:
                break
            width = 2 if buffer[index:index + 2] == b"\r\n" else 1
            raw, buffer = buffer[:index], buffer[index + width:]
            if first_line:
                raw, first_line = raw.removeprefix(b"\xef\xbb\xbf"), False
            if len(raw) > MAX_EVENT_BYTES:
                raise _Stop("event_too_large")
            line = raw.decode("utf-8", errors="strict")
            if not line:
                if data:
                    yield event, "\n".join(data)
                event, data, event_size = "", [], 0
                continue
            if line.startswith(":"):
                continue
            field, separator, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if field == "event":
                if len(value) > 100:
                    raise _Stop("event_name_invalid")
                event = value
            elif field == "data":
                event_size += len(raw) + 1
                if event_size > MAX_EVENT_BYTES:
                    raise _Stop("event_too_large")
                data.append(value if separator else "")
        if len(buffer) > MAX_EVENT_BYTES:
            raise _Stop("event_too_large")
        if not block:
            # SSE never commits a partial final event without the blank line.
            return


def _output_snapshot(response, secret):
    if "output" not in response:
        return "", {}, "absent"
    output = response.get("output")
    if not isinstance(output, list) or len(output) > 64:
        raise _Stop("completed_output_invalid")
    parts, item_ids, messages = {}, set(), 0
    for index, item in enumerate(output):
        if not isinstance(item, dict):
            raise _Stop("completed_output_invalid")
        if item.get("type") == "reasoning":
            continue
        if item.get("type") != "message" or item.get("role") != "assistant" or item.get("status") != "completed":
            raise _Stop("unexpected_output_kind")
        item_id = _safe(item.get("id"), _ID, secret)
        if not item_id or item_id in item_ids:
            raise _Stop("completed_output_invalid")
        item_ids.add(item_id)
        messages += 1
        content = item.get("content")
        if not isinstance(content, list) or len(content) > 64:
            raise _Stop("completed_output_invalid")
        for content_index, part in enumerate(content):
            if not isinstance(part, dict):
                raise _Stop("completed_output_invalid")
            if part.get("type") == "refusal":
                continue
            if part.get("type") != "output_text" or not isinstance(part.get("text"), str):
                raise _Stop("completed_output_invalid")
            parts[(index, content_index, item_id)] = part["text"]
    text = "".join(parts.values())
    if len(text) > MAX_OUTPUT_CHARS:
        raise _Stop("output_too_large")
    kind = "text" if text.strip() else "assistant_empty" if messages else "reasoning_only" if output else "empty"
    return text, parts, kind


def _final_output(response, secret):
    text, parts, _ = _output_snapshot(response, secret)
    if not text.strip():
        raise _Stop("completed_output_empty", "failed")
    return text, parts


def _bind_item(index, identifier, secret, slots, identifiers, kinds, kind=None):
    if type(index) is not int or not 0 <= index < 64 or not _safe(identifier, _ID, secret):
        raise _Stop("stream_item_invalid")
    if index in slots and slots[index] != identifier or identifier in identifiers and identifiers[identifier] != index:
        raise _Stop("stream_item_identity_changed")
    if kind is not None:
        if kind not in {"message", "reasoning"} or index in kinds and kinds[index] != kind:
            raise _Stop("unexpected_output_kind")
        kinds[index] = kind
    slots[index], identifiers[identifier] = identifier, index


def _text_key(event, secret, slots, identifiers, kinds):
    index, identifier, content_index = event.get("output_index"), event.get("item_id"), event.get("content_index")
    _bind_item(index, identifier, secret, slots, identifiers, kinds, "message")
    if type(content_index) is not int or not 0 <= content_index < 64 or kinds.get(index, "message") != "message":
        raise _Stop("text_delta_invalid")
    return index, content_index, identifier


def run_response(access_token, model_slug, input_items):
    """Make one explicitly reserved request; return only bounded, token-free facts.

No input is read from disk or replaced with calibration text/images. Successful
output is complete; failed/unknown receipts can retain partial received text but
never mark it completed. The caller must never retry an unknown send.
"""
    result = {"ok": False, "status": "not_sent", "code": "invalid_arguments", "httpStatus": None,
              "requestId": None, "responseId": None, "requestedModel": None, "actualModel": None, "output": "",
              "responseCompleted": False, "visionVerified": False, "requestSha256": None, "inputSha256": None,
              "requestStartedAt": None, "sentAt": None, "completedAt": None, "retryAllowed": False,
              "mediaType": None, "contentEncoding": None, "bodyClass": None, "bodyBytes": None,
              "bodySha256": None, "bodyTruncated": False, "errorParam": None,
              "diagnosticResponseStatus": None, "diagnosticResponseId": None, "diagnosticModel": None,
              "diagnosticOutput": "", "mimeMismatch": False,
              "terminalEventObserved": False, "terminalStatus": None, "terminalOutputKind": None,
              "terminalTextValidation": "not_observed", "completionEvidence": None, "completionSource": None,
              "providerErrorObserved": False, "failureOrigin": "arguments"}
    if (not isinstance(access_token, str) or not 1 <= len(access_token) <= 16384
            or any(ord(character) <= 32 or ord(character) >= 127 for character in access_token)
            or not isinstance(model_slug, str) or not _MODEL.fullmatch(model_slug) or access_token in model_slug):
        return result
    result["requestedModel"] = model_slug
    try:
        body, result["inputSha256"] = _payload(model_slug, input_items)
    except _Stop as error:
        result.update(status="not_sent", code=error.code)
        return result
    except (TypeError, ValueError, UnicodeError):
        result.update(status="not_sent", code="input_invalid")
        return result
    result["failureOrigin"] = None
    result["requestSha256"] = hashlib.sha256(body).hexdigest()
    deadline, connection, response, post_started = time.monotonic() + MAX_SECONDS, None, None, False
    deltas, delta_size, observed_id, sequence, event_count = {}, 0, None, None, 0
    slots, identifiers, kinds, text_done, item_done, added = {}, {}, {}, {}, {}, set()
    try:
        context = ssl.create_default_context()
        context.keylog_filename = None
        connection = http.client.HTTPSConnection("api.openai.com", 443, timeout=_remaining(deadline), context=context)
        connection.set_debuglevel(0)
        # Explicitly connect once and prohibit http.client's implicit reconnect.
        connection.connect()
        connection.auto_open = 0
        connection.sock.settimeout(_remaining(deadline))
        result["requestStartedAt"] = _utc()
        post_started = True
        connection.request("POST", "/v1/responses", body=body, headers={"Authorization": "Bearer " + access_token,
            "Content-Type": "application/json", "Accept": "text/event-stream", "Accept-Encoding": "identity"})
        result["sentAt"] = _utc()
        transport = connection.sock
        transport.settimeout(_remaining(deadline))
        response = connection.getresponse()
        result["httpStatus"] = response.status
        result["requestId"] = _safe(response.getheader("x-request-id"), _ID, access_token)
        result["mediaType"] = _header_value(response.getheader("content-type", ""), _MEDIA, access_token, media=True)
        encoding = response.getheader("content-encoding", "identity")
        result["contentEncoding"] = _header_value(encoding or "identity", _ENCODING, access_token)
        if 300 <= response.status < 400:
            result["failureOrigin"] = "http"
            raise _Stop("redirect_rejected", "failed")
        if response.status != 200:
            # Never return the server's free-form error message or echoed input.
            result["code"] = "http_rejected"
            result["failureOrigin"] = "http"
            error_body = _diagnostic_body(response, transport, deadline, result)
            code = _classify_body(error_body, result, access_token)
            if result["bodyTruncated"]:
                raise _Stop("http_error_body_too_large", "failed")
            raise _Stop(code or "http_rejected", "failed")
        if result["contentEncoding"] != "identity":
            result["bodyClass"] = "encoded"
            raise _Stop("unexpected_content_encoding")
        if result["mediaType"] != "text/event-stream":
            result["mimeMismatch"] = True
            mime_stream, diagnostic = _mime_response(response, transport, deadline, result)
            if mime_stream is None:
                code = _classify_body(diagnostic, result, access_token)
                if result["bodyTruncated"]:
                    raise _Stop("diagnostic_body_too_large")
                if result["contentEncoding"] != "identity":
                    raise _Stop("unexpected_content_encoding")
                if code:
                    raise _Stop(code, "failed")
                raise _Stop("unexpected_content_type")
            response_events = _events(mime_stream, transport, deadline)
        else:
            response_events = _events(response, transport, deadline)
        if result["contentEncoding"] != "identity":
            raise _Stop("unexpected_content_encoding")
        for name, data in response_events:
            event_count += 1
            if event_count > MAX_EVENTS:
                raise _Stop("too_many_events")
            if data == "[DONE]":
                raise _Stop("stream_ended_without_completed")
            event = json.loads(data)
            if not isinstance(event, dict) or not isinstance(event.get("type"), str) or name and name != event["type"]:
                raise _Stop("event_schema_invalid")
            kind = event["type"]
            current_sequence = event.get("sequence_number")
            if current_sequence is not None:
                if type(current_sequence) is not int or current_sequence < 0 or sequence is not None and current_sequence <= sequence:
                    raise _Stop("event_sequence_invalid")
                sequence = current_sequence
            current = event.get("response")
            if isinstance(current, dict):
                identifier = _safe(current.get("id"), _ID, access_token)
                if not identifier or observed_id and identifier != observed_id:
                    raise _Stop("response_identity_changed")
                observed_id = identifier
                result["responseId"] = identifier
                if "model" in current:
                    model = _safe(current["model"], _MODEL, access_token)
                    if not model or result["actualModel"] and model != result["actualModel"]:
                        raise _Stop("response_model_changed")
                    result["actualModel"] = model
            if kind in {"response.failed", "response.incomplete", "error"}:
                result.update(providerErrorObserved=True, failureOrigin="provider")
                # Preserve the provider's machine code, never its free-form
                # message (which could echo credentials or request contents).
                candidates = [event.get("error"), current.get("error") if isinstance(current, dict) else None]
                code = next((_error_fields(error, result, access_token) for error in candidates
                             if isinstance(error, dict) and _safe(error.get("code"), _CODE, access_token)), None)
                code = code or _safe(event.get("code"), _CODE, access_token)
                raise _Stop(code or kind.replace(".", "_"), "failed")
            if kind in {"response.output_text.delta", "response.output_text.done", "response.output_item.added", "response.output_item.done"} and not observed_id:
                raise _Stop("stream_response_unbound")
            if kind == "response.output_text.delta":
                delta = event.get("delta")
                if not isinstance(delta, str):
                    raise _Stop("text_delta_invalid")
                key = _text_key(event, access_token, slots, identifiers, kinds)
                if key in text_done or key[0] in item_done:
                    raise _Stop("text_after_done")
                delta_size += len(delta)
                if delta_size > MAX_OUTPUT_CHARS:
                    raise _Stop("output_too_large")
                deltas[key] = deltas.get(key, "") + delta
                result["output"] = "".join(deltas[key] for key in sorted(deltas)).replace(access_token, "[credential redacted]")
            elif kind == "response.output_text.done":
                key = _text_key(event, access_token, slots, identifiers, kinds)
                text = event.get("text")
                if not isinstance(text, str) or len(text) > MAX_OUTPUT_CHARS or key in text_done:
                    raise _Stop("text_done_invalid")
                if key in deltas and deltas[key] != text or key[0] in item_done and item_done[key[0]].get(key) != text:
                    raise _Stop("completed_text_mismatch")
                text_done[key] = text
            elif kind in {"response.output_item.added", "response.output_item.done"}:
                item, index = event.get("item"), event.get("output_index")
                if not isinstance(item, dict) or item.get("type") not in {"message", "reasoning"}:
                    raise _Stop("stream_item_invalid")
                _bind_item(index, item.get("id"), access_token, slots, identifiers, kinds, item.get("type"))
                if item.get("type") == "message" and item.get("role") != "assistant":
                    raise _Stop("unexpected_output_kind")
                if kind == "response.output_item.added":
                    if index in added or index in item_done:
                        raise _Stop("stream_item_duplicate")
                    added.add(index)
                else:
                    if index in item_done:
                        raise _Stop("stream_item_duplicate")
                    _, parts, _ = _output_snapshot({"output": [item]}, access_token)
                    parts = {(index, key[1], key[2]): value for key, value in parts.items()}
                    if any(parts.get(key) != text for key, text in {**deltas, **text_done}.items() if key[0] == index):
                        raise _Stop("completed_text_mismatch")
                    item_done[index] = parts
            elif kind == "response.completed":
                status = current.get("status") if isinstance(current, dict) else None
                result["terminalStatus"] = status if isinstance(status, str) and status in _STATUSES else None
                if (not isinstance(current, dict) or current.get("status") != "completed"
                        or current.get("error") is not None or current.get("incomplete_details") is not None
                        or not result["actualModel"]):
                    raise _Stop("completed_status_invalid")
                # This fact is set from the actual validated event, never from
                # a provider error.code that happens to resemble a local code.
                result.update(terminalEventObserved=True, completionEvidence="response.completed",
                              terminalOutputKind="invalid", terminalTextValidation="invalid")
                output, parts, snapshot_kind = _output_snapshot(current, access_token)
                result["terminalOutputKind"] = snapshot_kind
                try:
                    for index, item in enumerate(current.get("output", [])):
                        _bind_item(index, item.get("id"), access_token, slots, identifiers, kinds, item.get("type"))
                except _Stop:
                    result["terminalTextValidation"] = "mismatch"
                    raise
                done_parts = {key: value for item in item_done.values() for key, value in item.items()}
                observed_parts = {**deltas, **text_done, **done_parts}
                if snapshot_kind == "text":
                    if any(parts.get(key) != text for key, text in observed_parts.items()):
                        result["terminalTextValidation"] = "mismatch"
                        raise _Stop("completed_text_mismatch")
                    result.update(terminalTextValidation="snapshot_matches" if observed_parts else "snapshot_only",
                                  completionSource="terminal_snapshot")
                elif snapshot_kind in {"absent", "empty", "reasoning_only"}:
                    if any(deltas.get(key) != text for key, text in {**text_done, **done_parts}.items()):
                        result["terminalTextValidation"] = "mismatch"
                        raise _Stop("completed_text_mismatch")
                    output = "".join(deltas[key] for key in sorted(deltas))
                    if not output.strip():
                        result["terminalTextValidation"] = "empty"
                        raise _Stop("completed_output_empty", "failed")
                    result.update(terminalTextValidation="stream_deltas", completionSource="completed_stream_deltas")
                else:
                    # An explicit completed assistant item with empty text is
                    # contradictory to nonempty deltas; it is not an absent snapshot.
                    result["terminalTextValidation"] = "mismatch" if deltas else "empty"
                    if deltas:
                        raise _Stop("completed_text_mismatch")
                    raise _Stop("completed_output_empty", "failed")
                if len(output) > MAX_OUTPUT_CHARS:
                    result["terminalTextValidation"] = "invalid"
                    raise _Stop("output_too_large")
                if not output.strip():
                    raise _Stop("completed_text_mismatch")
                result.update(ok=True, status="completed", code="response_completed", responseCompleted=True,
                              output=output.replace(access_token, "[credential redacted]"), completedAt=_utc())
                return result
        raise _Stop("stream_ended_without_completed")
    except _Stop as error:
        result.update(status=error.status if post_started else "not_sent", code=error.code)
        result["failureOrigin"] = result["failureOrigin"] or "parser"
    except (socket.timeout, TimeoutError):
        result.update(status="unknown" if post_started else "not_sent", code="network_timeout", failureOrigin="transport")
    except (OSError, http.client.HTTPException):
        result.update(status="unknown" if post_started else "not_sent", code="network_or_tls_error", failureOrigin="transport")
    except (ValueError, UnicodeError, TypeError, KeyError):
        result.update(status="unknown" if post_started else "not_sent", code="invalid_stream", failureOrigin="parser")
    finally:
        if response is not None:
            response.close()
        if connection is not None:
            connection.close()
    return result
