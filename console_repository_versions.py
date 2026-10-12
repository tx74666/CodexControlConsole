"""Read and plan exact, explicit one-time version edits. Never imports project code."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

MAX_BYTES = 2 * 1024 * 1024


class VersionPlanError(ValueError):
    pass


class _CompanionVersionError(VersionPlanError):
    pass


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _proof(value):
    return _hash(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def source_id(source):
    return "version-" + _proof({key: source.get(key, "") for key in ("path", "kind", "key")})[:24]


def next_patch(value):
    match = re.fullmatch(r"([vV]?)(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise VersionPlanError("此版本不是明确的三段数字版本，请手动准备版本。")
    prefix, major, minor, patch = match.groups()
    original = (major, minor, patch)
    following = [int(major), int(minor), int(patch) + 1]
    for index in (2, 1):
        if following[index] >= 100:
            following[index] = 0
            following[index - 1] += 1
    parts = [str(number).zfill(len(old)) if len(old) > 1 and old.startswith("0") else str(number)
             for number, old in zip(following, original)]
    return prefix + ".".join(parts)


def parse_commit_history(head, raw):
    """Parse fixed first-parent `%H%x00%s` lines, never run Git or project code."""
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", str(head)):
        raise VersionPlanError("提交版本的 HEAD 身份无法确认。")
    if isinstance(raw, bytes):
        if len(raw) > MAX_BYTES:
            raise VersionPlanError("提交版本历史超出读取范围。")
        try:
            raw = raw.decode("utf-8")
        except UnicodeError as exc:
            raise VersionPlanError("提交版本历史不是完整 UTF-8 回执。") from exc
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_BYTES:
        raise VersionPlanError("提交版本历史无法读取。")
    lines = raw.splitlines()
    if any(line.count("\0") != 1 for line in lines):
        raise VersionPlanError("提交版本历史回执不完整。")
    rows = [tuple(part.strip() for part in line.split("\0")) for line in lines]
    if not 1 <= len(rows) <= 64 or rows[0][0] != head:
        raise VersionPlanError("提交版本历史不属于固定 HEAD 或超过 64 条。")
    if any(not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit) for commit, _ in rows):
        raise VersionPlanError("提交版本历史包含未确认的提交身份。")
    pattern = r"([vV]?\d+\.\d+\.\d+)(?:\s*(?:→|->)\s*([vV]?\d+\.\d+\.\d+))?"
    for depth, (commit, subject) in enumerate(rows, 1):
        match = re.fullmatch(pattern, subject)
        if match:
            version = match.group(2) or match.group(1)
            if len(version) > 80:
                raise VersionPlanError("提交版本号超出显示范围。")
            return {"sourceHeadSha": head, "versionCommitSha": commit, "versionSubject": subject,
                    "version": version, "currentVersion": version, "historyDepth": depth,
                    "versionOrigin": "git_commit_first_parent"}
    raise VersionPlanError("最近 64 条 first-parent 提交中没有明确版本；不会使用其他版本来源代替。")


def _decode(raw):
    if len(raw) > MAX_BYTES:
        raise VersionPlanError("版本文件过大，请手动准备版本。")
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    return bom, raw[len(bom):].decode("utf-8")


def _json_span(text, key):
    # Validate before the span walker so truncated/empty JSON fails per source.
    json.loads(text)
    decoder = json.JSONDecoder()
    wanted, matches = key.split("."), []

    def space(index):
        while index < len(text) and text[index].isspace():
            index += 1
        return index

    def value(index, path):
        index = space(index)
        if text[index] != "{":
            item, end = decoder.raw_decode(text, index)
            if path == wanted:
                matches.append((index, end, item))
            return end
        index, seen = space(index + 1), set()
        if text[index] == "}":
            return index + 1
        while True:
            name, end = decoder.raw_decode(text, index)
            if not isinstance(name, str) or name in seen:
                raise VersionPlanError("JSON 字段重复或不明确，请手动准备版本。")
            seen.add(name)
            end = space(end)
            if text[end] != ":":
                raise ValueError("JSON colon")
            index = space(value(end + 1, path + [name]))
            if text[index] == "}":
                return index + 1
            if text[index] != ",":
                raise ValueError("JSON comma")
            index = space(index + 1)

    end = space(value(0, []))
    if end != len(text) or len(matches) != 1 or not isinstance(matches[0][2], str):
        raise VersionPlanError("版本字段不是唯一字符串，请手动准备版本。")
    start, end, current = matches[0]
    # Replace a JSON string token; indentation, other fields, BOM and EOL remain.
    return current, (start, end, json.dumps(next_patch(current), ensure_ascii=False))


def _ast_offsets(text, node):
    lines = text.encode("utf-8").splitlines(keepends=True)
    start = sum(map(len, lines[:node.lineno - 1])) + node.col_offset
    end = sum(map(len, lines[:node.end_lineno - 1])) + node.end_col_offset
    raw = text.encode("utf-8")
    return len(raw[:start].decode("utf-8")), len(raw[:end].decode("utf-8"))


def _python_span(text, key):
    parts = (key or "bl_info.version").split(".")
    if parts == ["bl_info"]:
        parts.append("version")  # Preserve the existing legacy bl_info source alias.
    assignments = [node.value for node in ast.parse(text).body
                   if isinstance(node, (ast.Assign, ast.AnnAssign)) and
                   any(isinstance(target, ast.Name) and target.id == parts[0]
                       for target in (node.targets if isinstance(node, ast.Assign) else [node.target]))]
    if len(assignments) != 1:
        raise VersionPlanError("Python 版本赋值不唯一，请手动准备版本。")
    node = assignments[0]
    for part in parts[1:]:
        if not isinstance(node, ast.Dict):
            raise VersionPlanError("Python 版本不是静态字典，请手动准备版本。")
        if any(not isinstance(name, ast.Constant) or not isinstance(name.value, str) for name in node.keys):
            raise VersionPlanError("Python 字典包含动态字段或展开，不能确定实际版本，请手动准备版本。")
        matches = [item for name, item in zip(node.keys, node.values)
                   if isinstance(name, ast.Constant) and name.value == part]
        if len(matches) != 1:
            raise VersionPlanError("Python 版本字段不唯一，请手动准备版本。")
        node = matches[0]
    literal = ast.literal_eval(node)
    if isinstance(literal, (list, tuple)) and len(literal) == 3 and all(type(item) is int and item >= 0 for item in literal):
        current = ".".join(map(str, literal))
        following = tuple(map(int, next_patch(current).split(".")))
        spans = [(*_ast_offsets(text, element), str(value))
                 for element, previous, value in zip(node.elts, literal, following) if previous != value]
        return current, spans
    if isinstance(literal, str):
        start, end = _ast_offsets(text, node)
        token = text[start:end]
        if len(token) >= 2 and token[0] in "\"'" and token[-1] == token[0] and token[1:-1] == literal:
            return literal, (start + 1, end - 1, next_patch(literal))
    raise VersionPlanError("Python 版本格式需要人工协调，请手动准备版本。")


def _simple_span(text, kind, key):
    key = key or ("bundleVersion" if kind in {"unity", "unity_yaml"} else "Version" if kind in {"xml", "csproj"} else "version")
    if kind in {"xml", "csproj"}:
        if "<!DOCTYPE" in text.upper():
            raise VersionPlanError("XML 声明不适合自动编辑，请手动准备版本。")
        nodes = [node for node in ET.fromstring(text).iter() if node.tag.split("}")[-1] == key]
        matches = list(re.finditer(r"<(?P<tag>(?:[\w.-]+:)?" + re.escape(key) + r")\b[^>]*>(?P<value>[^<]*)</(?P=tag)\s*>", text))
        if len(nodes) != 1 or len(matches) != 1:
            raise VersionPlanError("XML 版本节点不唯一，请手动准备版本。")
        match = matches[0]
        value = match["value"]
        current = value.strip()
        if current != (nodes[0].text or "").strip():
            raise VersionPlanError("XML 版本包含转义，请手动准备版本。")
        start = match.start("value") + len(value) - len(value.lstrip())
        return current, (start, start + len(current), next_patch(current))
    pattern = r"(?m)^\s*" + re.escape(key) + r"\s*[:=]\s*([\"']?)(?P<value>[vV]?\d+\.\d+\.\d+)\1\s*(?:#.*)?$"
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise VersionPlanError("文本版本字段不唯一或格式不支持，请手动准备版本。")
    match = matches[0]
    if kind in {"text", "yaml"} and text.lstrip().startswith("["):
        raise VersionPlanError("版本字段位于不明确的节，请手动准备版本。")
    if kind == "text":
        # TOML companion uses a root scalar. Do not edit another section's version.
        try:
            import tomllib
            parsed = tomllib.loads(text)
            if key not in parsed or parsed[key] != match["value"]:
                raise VersionPlanError("TOML 版本字段不一致，请手动准备版本。")
        except tomllib.TOMLDecodeError:
            pass  # Plain version.txt/Unity-like scalar remains supported.
    current = match["value"]
    return current, (match.start("value"), match.end("value"), next_patch(current))


def _one(raw, source):
    bom, text = _decode(raw)
    kind, key = source.get("kind", "json"), source.get("key", "")
    if kind in {"json", "app-manifest", "package"}:
        current, edit = _json_span(text, key or "version")
    elif kind in {"python_ast", "bl_info"}:
        current, edit = _python_span(text, key or "bl_info.version")
    elif kind in {"unity", "unity_yaml", "text", "yaml", "xml", "csproj"}:
        current, edit = _simple_span(text, kind, key)
    else:
        raise VersionPlanError("此版本来源格式不支持自动升版，请手动准备版本。")
    return current, (bom, text, edit)


def _console_files(root, source, reader, current, console_reader=None):
    edits = {}
    raw = reader("app-manifest.json")
    _, parsed = _decode(raw)
    if json.loads(parsed).get("repository") != "tx74666/CodexControlConsole":
        return None
    if source.get("path") != "app-manifest.json" or (source.get("key") or "version") != "version":
        raise VersionPlanError("Console 版本须使用 app-manifest.json 的权威版本字段。")
    if not re.fullmatch(r"\d+\.\d+\.\d+", current):
        raise VersionPlanError("Console 发布要求三段数字版本，请先按发布流程协调。")
    evidence = []
    if console_reader is not None:
        for name in ("console-repository-publish.js", "console-repository-publish.css"):
            head, previous, git_changed = console_reader(name)
            if (not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", str(head)) or type(git_changed) is not bool
                    or previous is not None and (not isinstance(previous, bytes) or len(previous) > MAX_BYTES)):
                raise VersionPlanError("Console 独立资源的固定 HEAD 证明无效。")
            current_raw = reader(name)
            if not isinstance(current_raw, bytes) or len(current_raw) > MAX_BYTES:
                raise VersionPlanError("Console 独立资源超出读取范围。")
            evidence.append({"path": name, "headSha": head, "headMissing": previous is None,
                             "headSha256": _hash(previous) if previous is not None else None,
                             "headBytes": len(previous) if previous is not None else None,
                             "expectedSha256": _hash(current_raw), "expectedBytes": len(current_raw),
                             "gitChanged": git_changed, "changed": previous is None or git_changed and
                             previous.replace(b"\r\n", b"\n") != current_raw.replace(b"\r\n", b"\n")})
        if len({entry["headSha"] for entry in evidence}) != 1:
            raise VersionPlanError("Console 独立资源读取期间 HEAD 已变化。")
    changed_resources = {entry["path"] for entry in evidence if entry["changed"]}
    edits["app-manifest.json"] = (raw, _one(raw, source)[1])
    for name in ("app.js", "index.html", "music.html", "workspace.html", "phone/version.json"):
        raw = reader(name)
        bom, text = _decode(raw)
        spans = []
        if name == "phone/version.json":
            found, edit = _json_span(text, "version")
            if found != current:
                raise VersionPlanError("Console 手机与桌面版本不一致，请先按发布流程协调。")
            spans = [edit]
        elif name == "app.js":
            matches = list(re.finditer(r'(?m)^\s*const consoleUiVersion\s*=\s*(["\'])(?P<version>[^"\']+)\1\s*;', text))
            if len(matches) != 1 or matches[0]["version"] != current:
                raise VersionPlanError("Console UI 与权威版本不一致，请先按发布流程协调。")
            match = matches[0]
            spans = [(match.start("version"), match.end("version"), next_patch(current))]
        else:
            expected = ("styles.css", "app.js")
            for asset in expected:
                matches = list(re.finditer(r'\b(?:href|src)\s*=\s*(["\'])(?P<url>' + re.escape(asset) + r'\?v=[^"\'<>]+)\1', text))
                if len(matches) != 1:
                    raise VersionPlanError("Console 缓存引用不唯一，请先按发布流程协调。")
                match = matches[0]
                versions = list(re.finditer(r"(?<![\d.])" + re.escape(current) + r"(?![\d.])", match["url"]))
                if len(versions) != 1:
                    raise VersionPlanError("Console 缓存版本不一致，请先按发布流程协调。")
                offset = match.start("url") + versions[0].start()
                spans.append((offset, offset + len(current), next_patch(current)))
            # Preserve an unchanged independently cached module. A changed
            # resource gets a fresh query only with fixed HEAD byte evidence.
            if name == "index.html":
                for asset in ("console-repository-publish.css", "console-repository-publish.js"):
                    matches = list(re.finditer(r'\b(?:href|src)\s*=\s*(["\'])(?P<url>' + re.escape(asset) + r'\?v=console-repository-publish-(?P<cache>[vV]?\d+\.\d+\.\d+))\1', text))
                    if len(matches) != 1:
                        raise VersionPlanError("Console 独立仓库模块缓存引用不唯一，请按发布流程协调。")
                    if asset in changed_resources:
                        match = matches[0]
                        spans.append((match.start("cache"), match.end("cache"), next_patch(current)))
        edits[name] = (raw, (bom, text, spans))
    return edits, evidence


def read_current_version(raw, source):
    """Read one exact source value without companion writes or imports."""
    return _one(raw, source)[0]


def _strict_blender_manifest(raw, current):
    try:
        import tomllib
        _, text = _decode(raw)
        manifest = tomllib.loads(text)
        if not isinstance(manifest.get("version"), str) or manifest["version"] != current:
            raise ValueError("manifest root version does not match declaration")
    except (UnicodeError, ValueError, KeyError, TypeError) as exc:
        raise _CompanionVersionError("固定 Blender manifest 不是完整、唯一且一致的 TOML 版本声明，请协调后重试。") from exc


def _blender_companion(root, source, reader, current, primary_raw):
    path = Path(source["path"])
    if path.name == "blender_manifest.toml":
        _strict_blender_manifest(primary_raw, current)
    companion = None
    if source.get("kind") in {"python_ast", "bl_info"} and (root / path.parent / "blender_manifest.toml").exists():
        if path.name != "__init__.py" or (source.get("key") or "bl_info.version") not in {"bl_info", "bl_info.version"}:
            raise _CompanionVersionError("同目录 Blender manifest 与此 Python 版本归属不明确，请手动协调。")
        companion = {"path":(path.parent / "blender_manifest.toml").as_posix(), "kind":"text", "key":"version"}
    elif path.name == "blender_manifest.toml" and (root / path.parent / "__init__.py").exists():
        if source.get("kind") != "text" or (source.get("key") or "version") != "version":
            raise _CompanionVersionError("Blender manifest 权威版本字段不明确，请手动协调。")
        companion = {"path":(path.parent / "__init__.py").as_posix(), "kind":"python_ast", "key":"bl_info.version"}
    if companion is None:
        return None
    try:
        raw = reader(companion["path"])
        previous, edit = _one(raw, companion)
        if Path(companion["path"]).name == "blender_manifest.toml":
            _strict_blender_manifest(raw, previous)
        if previous != current:
            raise _CompanionVersionError("同一 Blender 插件的 blender_manifest.toml 与 bl_info 版本不同，请协调一致；不会分别升版。")
        return companion, raw, edit
    except _CompanionVersionError:
        raise
    except (OSError, UnicodeError, ValueError, SyntaxError, KeyError, TypeError, ET.ParseError) as exc:
        raise _CompanionVersionError("同一 Blender 插件的另一版本声明缺失或不唯一，请协调一致；不会导入插件代码。") from exc


def _inspect(root, source, reader, git_reader=None, console_reader=None):
    if source.get("kind") == "git_commit":
        if source.get("path") != "HEAD" or source.get("key") != "subject" or git_reader is None:
            raise VersionPlanError("提交版本仅允许固定 HEAD / subject 来源。")
        evidence = git_reader(source)
        current = evidence["version"]
        raw = json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode("utf-8")
        public = {"sourceId": source_id(source), **{key: source.get(key, "") for key in ("path", "kind", "key", "name", "scope")},
                  "currentVersion": current, "nextVersion": next_patch(current), "canBump": True, "reason": "",
                  "expectedSha256": _hash(raw), "expectedBytes": len(raw), "expectedFiles": [], **evidence}
        public["planProof"] = _proof({"sourceId": public["sourceId"], "currentVersion": current,
                                      "targetVersion": public["nextVersion"], "files": [], "gitEvidence": evidence})
        return public, {}
    path = source["path"]
    raw = reader(path)
    current, edit = _one(raw, source)
    edits = {path: (raw, edit)}
    evidence = []
    if path == "app-manifest.json":
        companion = _console_files(root, source, reader, current, console_reader)
        if companion:
            edits, evidence = companion
    paired = _blender_companion(root, source, reader, current, raw)
    if paired:
        companion, companion_raw, companion_edit = paired
        edits[companion["path"]] = (companion_raw, companion_edit)
    files = [{"path": name, "expectedSha256": _hash(item[0]), "expectedBytes": len(item[0])} for name, item in sorted(edits.items())]
    public = {"sourceId": source_id(source), **{key: source.get(key, "") for key in ("path", "kind", "key", "name", "scope")},
              "currentVersion": current, "nextVersion": next_patch(current), "canBump": True, "reason": "",
              "expectedSha256": _hash(raw), "expectedBytes": len(raw), "expectedFiles": files}
    if paired:
        public.update(pairedCompanion=paired[0], companionState="paired")
    proof = {"sourceId": public["sourceId"], "currentVersion": current, "targetVersion": public["nextVersion"], "files": files}
    if evidence:
        public["consoleResourceEvidence"] = evidence
        proof["consoleResourceEvidence"] = evidence
    public["planProof"] = _proof(proof)
    return public, edits


def catalog(root, sources, reader, git_reader=None, console_reader=None):
    items, seen = [], set()
    for source in sources:
        ident = source_id(source)
        if ident in seen:
            continue
        seen.add(ident)
        try:
            item, _ = _inspect(root, source, reader, git_reader, console_reader)
        except (VersionPlanError, OSError, UnicodeError, ValueError, SyntaxError, KeyError, TypeError, ET.ParseError) as exc:
            item = {"sourceId": ident, **{key: source.get(key, "") for key in ("path", "kind", "key", "name", "scope")},
                    "currentVersion": "", "nextVersion": "", "canBump": False, "reason": str(exc) if isinstance(exc, VersionPlanError) else "版本来源缺失、变化或无法唯一读取，请手动准备版本。"}
            if isinstance(exc, _CompanionVersionError):
                item["companionState"] = "blocked"
        items.append(item)
    for item in items:
        paths = {entry["path"] for entry in item.get("expectedFiles", [])}
        if paths and any(other is not item and (item.get("pairedCompanion") or other.get("pairedCompanion")) and
                         paths & {entry["path"] for entry in other.get("expectedFiles", [])} for other in items):
            item.update(canBump=False, companionState="blocked", reason="同一 Blender 插件的双版本来源被重复配置，修改范围重叠；请保留一个权威来源。")
    return items


def prepare_updates(root, sources, plans, reader, git_reader=None, console_reader=None):
    by_id = {source_id(source): source for source in sources}
    combined, proofs, paired_paths = {}, [], set()
    for plan in plans:
        source = by_id.get(plan["sourceId"])
        if source is None:
            raise VersionPlanError("版本来源已改变，请重新配置一次性版本计划。")
        item, edits = _inspect(root, source, reader, git_reader, console_reader)
        if set(edits) & paired_paths or item.get("pairedCompanion") and set(edits) & combined.keys():
            raise VersionPlanError("同一 Blender 插件的双版本来源被重复配置，修改范围重叠；请保留一个权威来源。")
        if item.get("pairedCompanion"):
            paired_paths.update(edits)
        expected = {"sourceId": item["sourceId"], "currentVersion": item["currentVersion"], "targetVersion": item["nextVersion"],
                    "expectedSha256": item["expectedSha256"], "expectedBytes": item["expectedBytes"], "planProof": item["planProof"]}
        if plan != expected:
            raise VersionPlanError("版本或关联文件已变化，请重新配置一次性版本计划。")
        proofs.append(expected)
        for path, (raw, (bom, text, spans)) in edits.items():
            if isinstance(spans, tuple):
                spans = [spans]
            old = combined.setdefault(path, {"raw": raw, "bom": bom, "text": text, "spans": []})
            if old["raw"] != raw:
                raise VersionPlanError("版本文件在规划期间变化，请稍后重试。")
            old["spans"].extend(spans)
    updates = []
    if sum(len(item["raw"]) for item in combined.values()) > 16 * 1024 * 1024:
        raise VersionPlanError("一次性版本关联文件总量过大，请分次配置或手动准备版本。")
    for path, item in sorted(combined.items()):
        spans = sorted(set(item["spans"]), reverse=True)
        text, boundary = item["text"], len(item["text"])
        for start, end, replacement in spans:
            if not 0 <= start <= end <= boundary:
                raise VersionPlanError("同一文件的版本修改范围重叠，请手动协调。")
            text = text[:start] + replacement + text[end:]
            boundary = start
        before, after = item["raw"], item["bom"] + text.encode("utf-8")
        updates.append({"path": path, "beforeSha256": _hash(before), "afterSha256": _hash(after),
                        "beforeBytes": len(before), "afterBytes": len(after),
                        "beforeBase64": base64.b64encode(before).decode("ascii"), "afterBase64": base64.b64encode(after).decode("ascii")})
    return updates, proofs
