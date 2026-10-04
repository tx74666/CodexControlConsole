"""Extract complete reviewable script blocks; this module never runs code."""
from __future__ import annotations

import hashlib
import re


def script_blocks(text):
    """Return only balanced Python/PowerShell fences, preserving exact code bytes.

    A fence opened for another language still owns its contents. An unfinished
    fence is never a proposal, including when an App answer was truncated.
    Indented code, inline backticks and prose are not executable selections.
    """
    if not isinstance(text, str):
        return []
    result, opened, contents = [], None, []
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
            if language in {"python", "powershell"} and code.strip() and "\0" not in code:
                result.append({"blockIndex": len(result), "language": language, "code": code,
                               "codeSha256": hashlib.sha256(code.encode("utf-8")).hexdigest()})
            opened, contents = None, []
        else:
            contents.append(line)
    return result
