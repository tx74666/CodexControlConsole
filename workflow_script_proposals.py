"""Extract complete reviewable script blocks; this module never runs code."""
from __future__ import annotations

import hashlib
import json
import re


def _fenced_blocks(text):
    """Yield complete fences; even an unrecognized language owns its contents.

    A fence opened for another language still owns its contents. An unfinished
    fence is never a proposal, including when an App answer was truncated.
    Indented code, inline backticks and prose are not executable selections.
    """
    if not isinstance(text, str):
        return
    opened, contents = None, []
    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        if opened is None:
            match = re.fullmatch(r" {0,3}(`{3,}|~{3,})([^\r\n]*)", bare)
            if match is None:
                continue
            fence, info = match.groups()
            if fence[0] == "`" and "`" in info:
                continue
            opened = (fence[0], len(fence), info.strip().lower())
            contents = []
            continue
        marker, count, language = opened
        if re.fullmatch(r" {0,3}" + re.escape(marker) + "{" + str(count) + r",}[ \t]*", bare):
            code = "".join(contents)
            if code.strip() and "\0" not in code:
                yield language, code
            opened, contents = None, []
        else:
            contents.append(line)


def script_blocks(text):
    """Return reviewable scripts, preserving the exact UTF-8 code bytes."""
    result = []
    for language, code in _fenced_blocks(text):
        if language in {"python", "powershell"}:
            result.append({"blockIndex": len(result), "language": language, "code": code,
                           "codeSha256": hashlib.sha256(code.encode("utf-8")).hexdigest()})
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate action property")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("Nonfinite value")


def _relative_image(value):
    # Both Windows and POSIX path spellings must stay within the selected project.
    if not isinstance(value, str) or not value or len(value) > 512 or "\0" in value or ":" in value:
        return False
    parts = value.replace("\\", "/").split("/")
    return (not value.startswith(("/", "\\")) and all(part and part not in {".", ".."} for part in parts)
            and parts[-1].lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif")))


def action_blocks(text):
    """Project strict console-action JSON fences; never turn prose into commands.

    Every nonempty console-action fence owns an index, including invalid ones, so deleting
    an invalid candidate cannot silently retarget a later reviewed block.
    """
    result, index = [], -1
    for language, content in _fenced_blocks(text):
        if language != "console-action":
            continue
        index += 1
        try:
            value = json.loads(content, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        except (ValueError, TypeError, RecursionError):
            continue
        if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1:
            continue
        action = value.get("action")
        if not isinstance(action, str):
            continue
        extra = {"commandId"} if action == "command" else {"args"} if action == "result_import" else set()
        if action not in {"capture_screen", "command", "result_import"} or set(value) != {"version", "label", "instruction", "action"} | extra:
            continue
        if any(not isinstance(value.get(key), str) or not value[key].strip() or "\0" in value[key] or len(value[key]) > limit
               for key, limit in (("label", 160), ("instruction", 20000))):
            continue
        if action == "command" and (not isinstance(value["commandId"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value["commandId"])):
            continue
        if action == "result_import":
            args = value["args"]
            if (not isinstance(args, dict) or set(args) != {"paths"} or not isinstance(args["paths"], list)
                    or not 1 <= len(args["paths"]) <= 4 or not all(_relative_image(path) for path in args["paths"])):
                continue
        try:
            encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        except UnicodeError:
            continue
        result.append({**value, "blockIndex": index, "actionSha256": hashlib.sha256(encoded).hexdigest()})
    return result
