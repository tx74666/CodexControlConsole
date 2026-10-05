"""Confirmed local Codex Work bridge. Never sends messages or invokes a model."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs
import uuid

from workflow_script_proposals import _fenced_blocks, _unique_object


def _api():
    # Imported lazily because WorkflowService mixes this class into its API.
    import workflow_service
    return workflow_service


def _digest(value):
    return hashlib.sha256(_api()._json(value).encode("utf-8")).hexdigest()


def _text_sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_key(value):
    # Filesystem identity, rather than the spelling used in an App manifest.
    return os.path.normcase(value.replace("\\", "/")).replace("\\", "/")


def _root(value):
    api = _api()
    path = Path(api._text(value, 2048)).expanduser()
    if not path.is_absolute() or not path.is_dir() or path.resolve() != path.absolute():
        raise api.WorkflowError("Workspace 目录不存在或被重定向。", 403)
    if any(item.is_symlink() or getattr(item, "is_junction", lambda: False)() for item in (path, *path.parents)):
        raise api.WorkflowError("Workspace 不能经过符号链接或重解析目录。", 403)
    return path.resolve()


_INTERNAL_DIRECTORIES = frozenset({
    ".git", "workflow-private", "work", "node_modules", "__pycache__", ".venv", "venv", "cache", "build", "dist"
})
_IDEA_CONTEXT_TEXT_LIMIT = 65000


def _internal_directory(name):
    name = name.casefold()
    return name in _INTERNAL_DIRECTORIES or name.startswith("dist-")


def _relative(value, output_directory=None):
    if not isinstance(value, str) or not value or len(value) > 1024 or "\0" in value or ":" in value or value.startswith(("/", "\\")):
        raise _api().WorkflowError("Work 成果必须使用范围内相对路径。", 403)
    parts = value.replace("\\", "/").split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise _api().WorkflowError("Work 成果路径越过授权目录。", 403)
    output = bool(output_directory and "/".join(parts).startswith(output_directory + "/"))
    checked_parts = parts[3:] if output else parts
    if (any(_internal_directory(part) for part in checked_parts[:-1])
            or checked_parts[-1].casefold() in _INTERNAL_DIRECTORIES):
        raise _api().WorkflowError("Work 不访问凭据、内部资料或构建缓存。", 403)
    if any(part.casefold().startswith(".env") or part.casefold().endswith((".pem", ".key", ".pfx")) or
           "credential" in part.casefold() or part.casefold().startswith("secrets.") for part in parts):
        raise _api().WorkflowError("Work 不读取凭据文件。", 403)
    return "/".join(parts)


def _file(root, relative, exists=True, output_directory=None):
    relative = _relative(relative, output_directory)
    path = root / relative
    if path.resolve() != path.absolute() or any(item.is_symlink() or getattr(item, "is_junction", lambda: False)() for item in (path, *path.parents)):
        raise _api().WorkflowError("Work 成果文件被重定向。", 403)
    if exists and not path.is_file():
        raise _api().WorkflowError("Work 成果文件不存在。", 409)
    return path


def result_block(text, output_directory=None):
    blocks = [code for lang, code in _fenced_blocks(text) if lang == "console-work-result"]
    if len(blocks) != 1:
        raise _api().WorkflowError("App 未返回唯一完整的 Work 成果清单。", 409)
    try:
        value = json.loads(blocks[0], object_pairs_hook=_unique_object)
    except (ValueError, TypeError, RecursionError) as error:
        raise _api().WorkflowError("Work 成果清单无效。", 409) from error
    if (not isinstance(value, dict) or set(value) - {"version", "text", "files", "changedFiles", "validation", "updatedTaskBody"}
            or not {"version", "text", "files", "changedFiles", "validation"} <= set(value)
            or type(value["version"]) is not int or value["version"] != 1
            or any(not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 20000 for key in ("text", "validation"))
            or any(not isinstance(value[key], list) or len(value[key]) > limit for key, limit in (("files", 4), ("changedFiles", 64)))):
        raise _api().WorkflowError("Work 成果清单字段无效。", 409)
    if "updatedTaskBody" in value and (not isinstance(value["updatedTaskBody"], str) or not value["updatedTaskBody"].strip() or len(value["updatedTaskBody"]) > 20000):
        raise _api().WorkflowError("Work 新任务正文无效。", 409)
    for key in ("files", "changedFiles"):
        value[key] = [_relative(path, output_directory if key == "files" else None) for path in value[key]]
        if len({_file_key(path) for path in value[key]}) != len(value[key]):
            raise _api().WorkflowError("Work 成果清单有重复路径。", 409)
    return value


class NativeWorkMixin:
    def native_work_catalog(self, body):
        api = _api()
        if (not isinstance(body, dict) or set(body) != {"requestId", "source", "capturedAt", "workspaces", "threads"}
                or body["source"] != "codex_app_tools" or not isinstance(body["workspaces"], list)
                or len(body["workspaces"]) > 100 or not isinstance(body["threads"], list) or len(body["threads"]) > 100):
            raise api.WorkflowError("请使用电脑 App Tools 的真实 Workspace 快照。")
        captured = self._source_time(body["capturedAt"])
        if abs((self._source_time(api._now()) - captured).total_seconds()) > 3600:
            raise api.WorkflowError("App Workspace 快照已过期。", 409)
        workspaces, threads = [], []
        for item in body["workspaces"]:
            if not isinstance(item, dict) or set(item) != {"projectId", "hostId", "root", "name"} or item["hostId"] != "local":
                raise api.WorkflowError("只接受真实本机 Workspace。")
            workspaces.append({"projectId": api._text(item["projectId"], 160), "hostId": "local", "root": str(_root(item["root"])), "name": api._text(item["name"], 160)})
        if len({item["projectId"] for item in workspaces}) != len(workspaces):
            raise api.WorkflowError("Workspace 快照有重复 ID。")
        for item in body["threads"]:
            if (not isinstance(item, dict) or set(item) != {"id", "kind", "hostId", "projectId", "cwd", "title"}
                    or item["kind"] != "codex" or item["hostId"] != "local"):
                raise api.WorkflowError("Work 聊天须有准确本机 cwd。")
            workspace = next((row for row in workspaces if row["projectId"] == item["projectId"]), None)
            if workspace is None or _root(item["cwd"]) != Path(workspace["root"]):
                raise api.WorkflowError("Work 聊天实际目录与 Workspace 不匹配。", 403)
            threads.append({**item, "id": self._thread_id(item["id"]), "cwd": workspace["root"], "title": api._text(item["title"], 160)})
        if len({item["id"] for item in threads}) != len(threads):
            raise api.WorkflowError("Work 聊天快照有重复 ID。")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "native_work_catalog", body)
            if not old:
                self._set_setting(db, "app_work_catalog", {"source": body["source"], "capturedAt": body["capturedAt"], "workspaces": workspaces, "threads": threads})
                self._receipt(db, "native_work_catalog", body, {"saved": True})
                self._revision(db, True)
        return {"saved": True, "duplicate": old is not None}

    def configure_app_work(self, body, authorize=None):
        api = _api()
        if authorize:
            authorize()
        if not isinstance(body, dict) or set(body) != {"requestId", "bindings"} or not isinstance(body["bindings"], list) or len(body["bindings"]) > 16:
            raise api.WorkflowError("Work 授权配置无效。")
        bindings = []
        for item in body["bindings"]:
            fields = {"id", "name", "workspaceProjectId", "hostId", "workspaceRoot", "allowedRoot", "allowAppWork"}
            if not isinstance(item, dict) or set(item) != fields or item["hostId"] != "local" or type(item["allowAppWork"]) is not bool:
                raise api.WorkflowError("请明确本机 Workspace 与 Work 授权。")
            workspace, allowed = _root(item["workspaceRoot"]), _root(item["allowedRoot"])
            try:
                allowed.relative_to(workspace)
            except ValueError as error:
                raise api.WorkflowError("Work 子目录不在所选 Workspace 内。", 403) from error
            bindings.append({**item, "id": api._key(item["id"]), "name": api._text(item["name"], 160),
                             "workspaceProjectId": api._text(item["workspaceProjectId"], 160), "workspaceRoot": str(workspace), "allowedRoot": str(allowed)})
        if len({item["id"] for item in bindings}) != len(bindings):
            raise api.WorkflowError("Work 授权 ID 重复。")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "app_work_bindings", body)
            if not old:
                self._set_setting(db, "app_work_bindings", bindings)
                self._receipt(db, "app_work_bindings", body, {"saved": True})
                self._revision(db, True)
            if authorize:
                authorize()
        return {"appWork": self.app_work_config(), "duplicate": old is not None}

    def _native_binding(self, db, identifier, enabled=True):
        api = _api()
        binding = next((item for item in self._setting(db, "app_work_bindings") or [] if item["id"] == identifier), None)
        if binding is None or (enabled and not binding.get("allowAppWork", False)):
            raise api.WorkflowError("此 Workspace 尚未明确授权 App Work。", 403, "work_not_authorized")
        catalog = self._setting(db, "app_work_catalog") or {}
        if catalog.get("source") != "codex_app_tools" or (self._source_time(api._now()) - self._source_time(catalog.get("capturedAt", ""))).total_seconds() > 3600:
            raise api.WorkflowError("请由电脑重新核对真实 App Workspace。", 409, "work_catalog_stale")
        workspace = next((item for item in catalog.get("workspaces", []) if item["projectId"] == binding["workspaceProjectId"] and item["hostId"] == "local"), None)
        if workspace is None or workspace["root"] != binding["workspaceRoot"]:
            raise api.WorkflowError("实际 App Workspace 与已审核目录不同。", 403, "permission_changed")
        _root(binding["workspaceRoot"])
        _root(binding["allowedRoot"]).relative_to(Path(binding["workspaceRoot"]))
        return binding, catalog

    def app_work_config(self):
        result = []
        with self._db() as db:
            for binding in self._setting(db, "app_work_bindings") or []:
                try:
                    _, catalog = self._native_binding(db, binding["id"])
                    reason = ""
                except (ValueError, OSError) as error:
                    reason, catalog = str(error), {}
                result.append({**binding, "executionAuthorizationSha256": _digest(binding), "available": not bool(reason),
                    "unavailableReason": reason, "matchingThreads": [{"id": row["id"], "title": row["title"]} for row in catalog.get("threads", [])
                        if row["projectId"] == binding["workspaceProjectId"] and row["cwd"] == binding["workspaceRoot"]]})
        return {"bindings": result}

    def _source_task(self, db, record_id, value=None):
        api = _api()
        keys = db.execute("SELECT key FROM settings WHERE value=? AND key LIKE 'task-record:%'", (api._json(record_id),)).fetchall()
        if len(keys) > 1:
            raise api.WorkflowError("原任务关联不唯一。", 409)
        idea_id = keys[0]["key"][len("task-record:"):] if keys else None
        if value is not None:
            if (not isinstance(value, dict) or set(value) != {"ideaId", "revision"} or type(value["revision"]) is not int
                    or value["ideaId"] != idea_id):
                raise api.WorkflowError("原任务关联与当前记录不匹配。", 409, "task_source_mismatch")
        if idea_id is None:
            return None
        idea = self._idea(db, idea_id)
        if value is not None and idea["revision"] != value["revision"]:
            raise api.WorkflowError("原任务草稿已变化，请保留输入并重新审核。", 409, "revision_conflict")
        return {"ideaId": idea_id, "revision": idea["revision"], "title": idea["title"], "body": idea["body"]}

    def _native_idea_context(self, db, source):
        """Freeze current saved idea data without treating it as Work authority."""
        api = _api()
        idea = self._idea(db, source["ideaId"])
        if idea["revision"] != source["revision"]:
            raise api.WorkflowError("想法来源已变化，请保留执行稿并重新审核。", 409, "revision_conflict")
        meta = self._mobile_metadata(db, idea["id"])
        points = meta.get("keyPoints", [])
        if not isinstance(points, list) or len(points) > 100:
            raise api.WorkflowError("当前长期要点无法核对，请保留执行稿后核对。", 409, "idea_context_changed")
        clean, seen = [], set()
        for point in points:
            if (not isinstance(point, dict) or not {"id", "text", "kind"} <= set(point)
                    or not isinstance(point["kind"], str) or point["kind"] not in {"suggestion", "decision"}):
                raise api.WorkflowError("当前长期要点无法核对，请保留执行稿后核对。", 409, "idea_context_changed")
            identifier, text = api._id(point["id"]), api._text(point["text"])
            if identifier in seen or not text.strip():
                raise api.WorkflowError("当前长期要点无法核对，请保留执行稿后核对。", 409, "idea_context_changed")
            seen.add(identifier)
            clean.append({"id": identifier, "text": text, "kind": point["kind"]})
        draft = api._text(meta.get("executionDraft", ""))
        if sum(len(point["text"]) for point in clean) + len(draft) > _IDEA_CONTEXT_TEXT_LIMIT:
            raise api.WorkflowError("当前长期要点与已保存执行稿过长，请保留原内容并缩小本轮来源。", 413, "idea_context_too_long")
        return {"ideaId": idea["id"], "revision": idea["revision"], "bodySha256": _text_sha(idea["body"]),
            "keyPoints": clean, "savedExecutionDraft": {"text": draft, "sha256": _text_sha(draft)}}

    def app_work_review(self, query, prefix="/api/workflow", authorize=None):
        """Read only one linked idea's current review data in a consistent snapshot."""
        api = _api()
        if authorize:
            authorize()
        if not isinstance(query, str) or len(query) > 256:
            raise api.WorkflowError("Work 审核来源请求地址无效。")
        values = parse_qs(query, keep_blank_values=True)
        if (set(values) != {"recordId", "ideaId", "revision"}
                or any(len(items) != 1 for items in values.values())):
            raise api.WorkflowError("Work 审核来源请求地址无效。")
        revision = values["revision"][0]
        if (not revision or len(revision) > 10 or not revision.isascii()
                or not revision.isdecimal() or int(revision) < 1):
            raise api.WorkflowError("Work 审核来源版本无效。")
        record_id, idea_id = api._id(values["recordId"][0]), api._id(values["ideaId"][0])
        path = api._safe_child(self.data_dir, "workflow.sqlite3")
        with self._lock:
            # _db initializes schema. This endpoint must never create or repair a database.
            db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=15)
            db.row_factory = sqlite3.Row
            try:
                db.execute("BEGIN")
                self._record(db, record_id)
                source = self._source_task(db, record_id, {"ideaId": idea_id, "revision": int(revision)})
                if source is None:
                    raise api.WorkflowError("Work 审核未关联当前想法。", 409, "task_source_mismatch")
                context = self._native_idea_context(db, source)
                result = {"recordId": record_id, "sourceTask": source, "ideaContext": context,
                    "ideaContextSha256": _digest(context)}
                if authorize:
                    authorize()
                return result
            finally:
                db.close()

    def task_record(self, body, prefix="/api/workflow", authorize=None):
        api = _api()
        if authorize:
            authorize()
        if not isinstance(body, dict) or set(body) - {"requestId", "ideaId", "expectedRevision", "projectId"}:
            raise api.WorkflowError("任务关联请求无效。")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "task_record", body)
            if old:
                identifier = old["recordId"]
            else:
                idea = self._idea(db, body.get("ideaId"))
                if "expectedRevision" in body and (type(body["expectedRevision"]) is not int or body["expectedRevision"] != idea["revision"]):
                    raise api.WorkflowError("任务已改变，请保留输入并重新读取。", 409, "revision_conflict")
                key = "task-record:" + idea["id"]
                identifier = self._setting(db, key)
                if identifier:
                    self._record(db, identifier)
                else:
                    projects = self._setting(db, "projects") or []
                    project = self._project(db, body.get("projectId", projects[0]["id"] if projects else ""))
                    identifier, now = uuid.uuid4().hex, api._now()
                    db.execute("INSERT INTO records VALUES (?,?,?,?,?,?,?)", (identifier, idea["title"], project["id"], now, now, None,
                        api._json({"selectedText": "", "referenceIds": [], "attachmentIds": []})))
                    if idea["body"]:
                        self._message(db, identifier, "user", idea["body"])
                    self._set_setting(db, key, identifier)
                    self._revision(db, True)
                self._receipt(db, "task_record", body, {"recordId": identifier})
            if authorize:
                authorize()
        return self.detail(identifier, prefix)

    def _native_inventory(self, root):
        # Bound reads, never follow links, and do not inspect internal/private trees.
        files, remaining = {}, 128 * 1024 * 1024
        for directory, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = [name for name in dirs if not _internal_directory(name)
                and not (Path(directory) / name).is_symlink() and not getattr(Path(directory) / name, "is_junction", lambda: False)()]
            for name in sorted(names):
                path = Path(directory) / name
                relative = path.relative_to(root).as_posix()
                try:
                    path = _file(root, relative)
                except (ValueError, OSError):
                    continue
                if len(files) >= 10000:
                    raise _api().WorkflowError("Workspace 文件过多，请缩小 Work 范围。", 409)
                key = _file_key(relative)
                if key in files:
                    raise _api().WorkflowError("Workspace 文件身份存在大小写别名冲突。", 409)
                size = path.stat().st_size
                files[key] = self._file_digest(path) if size <= min(remaining, 32 * 1024 * 1024) else None
                remaining -= size if files[key] is not None else 0
        return files

    def _check_native_work(self, db, job, payload, before_send=False, result_thread_id=None):
        api = _api()
        frozen = payload["nativeWork"]
        snapshot = json.loads(self._dispatch(db, payload["appDispatchId"])["snapshot"])
        if (payload.get("executionEngine") != "codex_app" or snapshot.get("origin") != "workflow_work"
                or snapshot.get("frozenPayloadSha256") != _digest(payload)):
            raise api.WorkflowError("Native Work 冻结任务不匹配。", 409, "context_changed")
        binding, catalog = self._native_binding(db, frozen["binding"]["id"])
        if binding != frozen["binding"] or _digest(binding) != frozen["authorizationSha256"]:
            raise api.WorkflowError("Work 授权已改变，未继续执行。", 403, "permission_changed")
        self._script_images(db, job["record_id"], {"payload": payload})
        context = payload["context"]
        if context.get("sourceMessageId"):
            row = db.execute("SELECT text FROM messages WHERE id=? AND record_id=?", (context["sourceMessageId"], job["record_id"])).fetchone()
            if row is None or _text_sha(row["text"]) != frozen["sourceTextSha256"]:
                raise api.WorkflowError("原消息已变化，Work 未继续执行。", 409, "context_changed")
        target = payload["appTarget"]
        actual_thread = result_thread_id or (target["threadId"] if target["mode"] == "existing" else None)
        if actual_thread:
            match = next((row for row in catalog["threads"] if row["id"] == actual_thread and row["kind"] == "codex"
                and row["hostId"] == "local" and row["projectId"] == binding["workspaceProjectId"] and row["cwd"] == binding["workspaceRoot"]), None)
            if match is None:
                raise api.WorkflowError("Work 目标聊天的实际 Workspace 未能核对。", 403)
        if before_send and self._native_inventory(Path(binding["allowedRoot"])) != frozen["beforeFiles"]:
            raise api.WorkflowError("Work 底稿在确认后改变，请重新审核。", 409, "context_changed")
        if before_send and _file(Path(binding["allowedRoot"]), frozen["outputDirectory"] + "/.reserved", False, frozen["outputDirectory"]).parent.exists():
            raise api.WorkflowError("本轮 Work 输出目录已存在，请重新审核新任务。", 409, "context_changed")

    def app_work(self, body, prefix="/api/workflow", authorize=None):
        api = _api()
        if authorize:
            authorize()
        authority_failed = False
        def reauthorize():
            nonlocal authority_failed
            try:
                if authorize:
                    authorize()
            except BaseException:
                authority_failed = True
                raise
        try:
            return self._accept_app_work(body, prefix, reauthorize)
        except api.WorkflowError as error:
            # Only a known, rolled-back rejection can release the browser's pending outbox.
            rejected = {"revision_conflict", "permission_changed", "work_not_authorized", "work_catalog_stale", "task_source_mismatch", "dispatch_in_progress", "idea_context_changed", "idea_context_too_long", "work_images_too_large"}
            if not authority_failed and error.status != 401 and error.code in rejected and isinstance(body, dict):
                try:
                    request_id = str(uuid.UUID(body.get("requestId", "")))
                    with self._db() as db:
                        accepted = db.execute("SELECT 1 FROM requests WHERE id=?", (request_id,)).fetchone()
                        accepted_job = db.execute("SELECT 1 FROM jobs WHERE request_id IN (?,?)", (request_id, body["requestId"])).fetchone()
                    if not accepted and not accepted_job:
                        error.queueAccepted = False
                except (ValueError, TypeError, AttributeError):
                    pass
            raise

    def _accept_app_work(self, body, prefix="/api/workflow", authorize=None):
        api = _api()
        allowed = {"requestId", "recordId", "text", "computerId", "projectId", "context", "sourceTask", "bindingId", "workspaceAuthorizationSha256", "workTarget", "updateTaskBody", "ideaContextSha256"}
        if not isinstance(body, dict) or set(body) - allowed:
            raise api.WorkflowError("请明确审核这次 Work 任务与 Workspace。")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "app_work", body)
            record = self._record(db, body.get("recordId"))
            if old:
                job_id = old["jobId"]
            else:
                if db.execute("SELECT 1 FROM idea_dispatches WHERE json_extract(snapshot,'$.recordId')=? AND status IN ('pending','claimed','waiting','needs_review')", (record["id"],)).fetchone():
                    raise api.WorkflowError("当前任务已有 App 请求在途，请先核对结果。", 409, "dispatch_in_progress")
                binding, catalog = self._native_binding(db, api._key(body.get("bindingId")))
                if body.get("workspaceAuthorizationSha256") != _digest(binding):
                    raise api.WorkflowError("Workspace 授权与审核内容不同。", 403, "permission_changed")
                computer = self._setting(db, "computer")
                if body.get("computerId", computer["id"]) != computer["id"]:
                    raise api.WorkflowError("Work 目标不是这台电脑。", 403)
                project = self._project(db, body.get("projectId", record["project_id"]))
                context = self._context(db, record["id"], body.get("context", json.loads(record["context"])))
                context.setdefault("attachmentIds", [record["primary_attachment_id"]] if record["primary_attachment_id"] else [])
                context["attachmentIds"] = list(dict.fromkeys(context["attachmentIds"]))
                if context.get("referenceIds"):
                    raise api.WorkflowError("Native Work 请使用明确选定的原消息与图片。")
                source_text = ""
                if context.get("sourceMessageId"):
                    source_text = db.execute("SELECT text FROM messages WHERE id=? AND record_id=?", (context["sourceMessageId"], record["id"])).fetchone()["text"]
                    if context.get("selectedText") and context["selectedText"] not in source_text:
                        raise api.WorkflowError("选中文字不属于原消息。", 409)
                target = body.get("workTarget")
                if not isinstance(target, dict) or set(target) - {"mode", "threadId", "name"} or target.get("mode") not in {"new", "existing"}:
                    raise api.WorkflowError("请选择准确的本机 Codex Work 聊天。")
                thread_id, name = "", api._text(target.get("name", record["title"]), 160)
                if target["mode"] == "new":
                    if target.get("threadId"):
                        raise api.WorkflowError("新 Work 聊天不能指定其他会话 ID。")
                else:
                    thread_id = self._thread_id(target.get("threadId"))
                    matched = next((row for row in catalog["threads"] if row["id"] == thread_id and row["projectId"] == binding["workspaceProjectId"] and row["cwd"] == binding["workspaceRoot"]), None)
                    if matched is None:
                        raise api.WorkflowError("目标 Work 聊天实际 Workspace 不匹配。", 403)
                    name = matched["title"]
                text = api._text(body.get("text", ""))
                if not text.strip():
                    raise api.WorkflowError("请填写这次需要实际完成的 Work 任务。")
                source_task = self._source_task(db, record["id"], body.get("sourceTask"))
                if source_task and body.get("sourceTask") is None:
                    raise api.WorkflowError("请核对原任务当前草稿后确认 Work。", 409, "revision_conflict")
                idea_context = self._native_idea_context(db, source_task) if source_task else None
                if idea_context is not None and body.get("ideaContextSha256") != _digest(idea_context):
                    raise api.WorkflowError("本轮执行稿或长期要点尚未准确审核，请保留草稿并重新审核。", 409, "idea_context_changed")
                update_body = body.get("updateTaskBody", False)
                if type(update_body) is not bool or (update_body and source_task is None):
                    raise api.WorkflowError("更新原任务正文需要明确审核且已关联原任务。")
                job_id, dispatch_id, now = uuid.uuid4().hex, uuid.uuid4().hex, api._now()
                output_directory = "work/console-work-results/" + dispatch_id
                if _file(Path(binding["allowedRoot"]), output_directory + "/.reserved", False, output_directory).parent.exists():
                    raise api.WorkflowError("本轮 Work 输出目录已存在，请重新审核。", 409)
                payload = {"computerId": computer["id"], "projectId": project["id"], "text": text, "context": context,
                    "executionEngine": "codex_app", "action": "native_work", "sourceTask": source_task, "updateTaskBody": update_body,
                    "appTarget": {"kind": "codex", "mode": target["mode"], "threadId": thread_id, "name": name}}
                payload["appFrozen"] = self._freeze_app_discussion(db, record, payload, project)
                if sum(image["originalSize"] for image in payload["appFrozen"]["images"]) > api.MAX_UPLOAD:
                    raise api.WorkflowError("本轮所选原图总大小超过 24 MB；图片与执行稿保留，Work 未入队。", 413, "work_images_too_large")
                if idea_context is not None:
                    if (sum(len(point["text"]) for point in idea_context["keyPoints"])
                            + len(idea_context["savedExecutionDraft"]["text"])
                            + sum(len(item["content"]) for item in payload["appFrozen"]["history"]) > _IDEA_CONTEXT_TEXT_LIMIT):
                        raise api.WorkflowError("本轮长期要点、已保存执行稿与讨论历史过长，请保留原内容并缩小本轮上下文。", 413, "idea_context_too_long")
                    payload["ideaContext"] = idea_context
                    payload["ideaContextSha256"] = _digest(idea_context)
                    payload["appFrozen"].update(ideaContext=idea_context, ideaContextSha256=payload["ideaContextSha256"])
                payload["nativeWork"] = {"binding": binding, "authorizationSha256": _digest(binding),
                    "sourceTextSha256": _text_sha(source_text), "beforeFiles": self._native_inventory(Path(binding["allowedRoot"])), "outputDirectory": output_directory}
                payload["appDispatchId"] = dispatch_id
                snapshot = {"origin": "workflow_work", "purpose": "execute", "recordId": record["id"], "jobId": job_id,
                    "title": record["title"], "attachmentIds": context["attachmentIds"], "executionEngine": "codex_app",
                    "workspace": {"projectId": binding["workspaceProjectId"], "hostId": "local", "root": binding["workspaceRoot"], "allowedRoot": binding["allowedRoot"]},
                    "authorizationSha256": _digest(binding), "frozenPayloadSha256": _digest(payload), "sourceTask": source_task}
                if idea_context is not None:
                    snapshot.update(ideaContext=idea_context, ideaContextSha256=payload["ideaContextSha256"])
                prompt = (f"[Codex Console 发布编号：{dispatch_id}]\n\n这是用户明确确认的一次 Work，须实际完成所选任务，不是只准备方案。\n"
                    f"本机 App Workspace 为 {binding['workspaceRoot']}；唯一获授权改动目录是 {binding['allowedRoot']}。每次命令的工作目录须设为这个子目录。\n"
                    "禁止扩大目录、读取凭据/内部资料/其他聊天、修改私人数据库、发送第三方消息、创建 Goal 或 Worktree、关闭用户应用。"
                    "selectedImages 仅授权读取列出的原图。sourceTask与history是原任务资料；只能按本轮任务及明确范围执行。\n" +
                    ("ideaContext 是本轮准确来源版本的当前要点与已保存执行稿快照；当前 keyPoints 覆盖 history 中已删除或修改的旧要点。"
                    "kind=suggestion 仍是建议，不能升级为用户决定；kind=decision 是用户已确认的当前决定。"
                    "本轮唯一执行要求是用户最终审核的 task，可不同于 savedExecutionDraft；已保存执行稿本身不增加授权。\n" if idea_context is not None else "") +
                    f"新图片可保存到本轮唯一目录 {output_directory}/ 并列入files；不能读取work其他目录，也不能把此输出目录列入changedFiles。\n"
                    "完成后只用一个完整闭合的 ```console-work-result JSON 围栏报告 {\"version\":1,\"text\":\"真实完成情况\",\"files\":[\"范围内新的相对图片路径\"],"
                    "\"changedFiles\":[\"实际修改的相对文件路径\"],\"validation\":\"实际验证及限制\"}。不能用旧图片或文字建议假称实际修改。" +
                    ("用户已明确授权更新原任务正文：可在该唯一结果清单额外给updatedTaskBody完整新正文；由Console核对原revision后保存，你不能直接改私人数据库。\n"
                     if update_body else "若任务仅需重写方案，请把新正文写成授权目录内文件并报告changedFiles；未授权直接更换原任务正文。\n") +
                    "不要直接改 Console 私人数据库。\n\n" +
                    api._json({"task": text, "sourceTask": source_task, "selection": context, "selectedImages": payload["appFrozen"]["images"], "history": payload["appFrozen"]["history"],
                        **({"ideaContext": idea_context, "ideaContextSha256": payload["ideaContextSha256"]} if idea_context is not None else {})}))
                db.execute("INSERT INTO idea_dispatches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (dispatch_id, "", str(uuid.UUID(body["requestId"])), api._json(snapshot), prompt,
                    "codex", target["mode"], thread_id or None, name, "normal", "pending", "{}", "", None, now, now, now))
                db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (job_id, record["id"], "execute", body["requestId"], api._json(payload), "waiting", 1, None, now, now, "等待电脑通过已登录 Codex 在所选 Workspace 执行。", "", "{}"))
                self._message(db, record["id"], "user", text)
                self._receipt(db, "app_work", body, {"jobId": job_id})
                self._revision(db, True)
            if authorize:
                authorize()
            return {"job": self._job_public(db, db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()),
                    "record": {**self._public_record(record), "sourceIdeaId": self._source_task(db, record["id"])["ideaId"] if self._source_task(db, record["id"]) else None},
                    "revision": self._revision(db), "duplicate": old is not None}

    def _attach_native_work(self, db, dispatch, snapshot, status, result, thread_id, error, now):
        api = _api()
        job = self._app_dispatch_job(db, dispatch, snapshot)
        payload = json.loads(job["payload"])
        if job["status"] != "waiting":
            raise api.WorkflowError("Work 已结束，不能重复附加成果。", 409)
        if status != "completed":
            db.execute("UPDATE jobs SET status=?,error=?,updated_at=? WHERE id=?", ("failed" if status == "failed" else "waiting", error or "等待准确 Work 结果。", now, job["id"]))
            return status, error
        ids, created_ids, proof, image_proof, body_update, review_error = [], [], [], [], None, ""
        previous = json.loads(job["result"])
        db.execute("SAVEPOINT native_work_result")
        try:
            self._check_native_work(db, job, payload, result_thread_id=thread_id)
            output_directory = payload["nativeWork"]["outputDirectory"]
            manifest = result_block(result["text"], output_directory)
            root, baseline = Path(payload["nativeWork"]["binding"]["allowedRoot"]), payload["nativeWork"]["beforeFiles"]
            remaining = 128 * 1024 * 1024
            image_keys = {_file_key(path) for path in manifest["files"]}
            claimed_files = {}
            for relative in manifest["changedFiles"] + manifest["files"]:
                claimed_files.setdefault(_file_key(relative), relative)
            for key, relative in claimed_files.items():
                path = _file(root, relative, exists=False, output_directory=output_directory if key in image_keys else None)
                old = baseline.get(key)
                if path.is_file():
                    size = path.stat().st_size
                    if size > min(remaining, api.MAX_FILE_BYTES if key in image_keys else 32 * 1024 * 1024):
                        raise api.WorkflowError("Work 成果超过有界回收限制，请缩小成果。", 413)
                    remaining -= size
                new = self._file_digest(path) if path.is_file() else None
                if key in baseline and old is None:
                    raise api.WorkflowError("此文件没有可核验的工作前快照，不能确认已修改。", 409)
                if old == new or (old is None and new is None):
                    raise api.WorkflowError("所报告文件未产生可验证的实际改动。", 409)
                proof.append({"path": relative, "beforeSha256": old, "afterSha256": new, "deleted": new is None})
            if "updatedTaskBody" in manifest:
                source_task = payload.get("sourceTask")
                if not payload.get("updateTaskBody") or not source_task:
                    raise api.WorkflowError("用户没有确认更换原任务正文。", 409)
                idea = self._idea(db, source_task["ideaId"])
                if idea["revision"] != source_task["revision"] or idea["body"] != source_task["body"]:
                    review_error = "用户已编辑新草稿，Work 结果未覆盖它；请核对 App 返回的新正文。"
                elif manifest["updatedTaskBody"] == idea["body"]:
                    raise api.WorkflowError("Work 新正文与原稿相同，未实际更新。", 409)
                else:
                    body_update = (manifest["updatedTaskBody"], now, idea["id"], idea["revision"])
            if not proof and not body_update and not review_error:
                raise api.WorkflowError("App 只返回报告，没有可验证的实际 Work 成果。", 409)
            for relative in manifest["files"]:
                path = _file(root, relative, output_directory=output_directory)
                mime = api.IMAGE_TYPES.get(path.suffix.lower())
                if not mime:
                    raise api.WorkflowError("Work 图片成果类型无效。", 409)
                expected_sha = next(item["afterSha256"] for item in proof if _file_key(item["path"]) == _file_key(relative))
                identifier = None
                if previous.get("appReport") == result["text"]:
                    prior = next((item for item in previous.get("imageProof", [])
                        if _file_key(item["path"]) == _file_key(relative) and item.get("sha256") == expected_sha), None)
                    if prior:
                        stored = db.execute("SELECT filename FROM attachments WHERE id=? AND record_id=?", (prior["attachmentId"], job["record_id"])).fetchone()
                        if stored and self._file_digest(api._safe_child(self.attachments_dir, stored["filename"])) == expected_sha:
                            identifier, copied_sha = prior["attachmentId"], expected_sha
                if identifier is None:
                    identifier, copied_sha = self._store_file(db, job["record_id"], path, path.name, mime)
                    created_ids.append(identifier)
                ids.append(identifier)
                image_proof.append({"path": relative, "attachmentId": identifier, "sha256": copied_sha})
                if copied_sha != expected_sha:
                    raise api.WorkflowError("Work 图片在回收期间变化，未确认执行完成。", 409)
            # Validate every claimed file again after copying, before any task-body write.
            for item in proof:
                path = _file(root, item["path"], False, output_directory if _file_key(item["path"]) in image_keys else None)
                if (self._file_digest(path) if path.is_file() else None) != item["afterSha256"]:
                    raise api.WorkflowError("Work 文件在回收期间变化，未确认执行完成。", 409)
            if body_update:
                proof.append({"kind": "task_body", "ideaId": body_update[2], "beforeRevision": body_update[3], "afterRevision": body_update[3] + 1,
                              "beforeSha256": _text_sha(payload["sourceTask"]["body"]), "afterSha256": _text_sha(body_update[0])})
                db.execute("UPDATE ideas SET body=?,revision=revision+1,updated_at=? WHERE id=? AND revision=?", body_update)
            if review_error:
                message = previous.get("messageId") if previous.get("appReport") == result["text"] and previous.get("attachmentIds") == ids else None
                message = message or self._message(db, job["record_id"], "assistant", result["text"], ids)
                saved = {**result, "appReport": result["text"], "targetThreadId": thread_id, "dispatchId": dispatch["id"], "messageId": message,
                    "attachmentIds": ids, "executionVerified": False, "fileProof": proof, "imageProof": image_proof, "verificationError": review_error}
                db.execute("UPDATE jobs SET status='waiting',result=?,error=?,updated_at=? WHERE id=?", (api._json(saved), review_error, now, job["id"]))
                db.execute("RELEASE native_work_result")
                return "needs_review", review_error
        except (ValueError, OSError) as failure:
            db.execute("ROLLBACK TO native_work_result")
            db.execute("RELEASE native_work_result")
            for identifier in created_ids:
                for path in self.attachments_dir.glob(identifier + ".*"):
                    path.unlink(missing_ok=True)
            message = previous.get("messageId") if previous.get("appReport", previous.get("text")) == result["text"] else None
            message = message or self._message(db, job["record_id"], "assistant", result["text"])
            retained = {key: previous[key] for key in ("attachmentIds", "fileProof", "imageProof") if key in previous} if previous.get("appReport") == result["text"] else {}
            saved = {**result, "targetThreadId": thread_id, "dispatchId": dispatch["id"], "messageId": message,
                     "appReport": result["text"], "attachmentIds": [], **retained, "executionVerified": False, "verificationError": str(failure)}
            db.execute("UPDATE jobs SET status='waiting',result=?,error=?,updated_at=? WHERE id=?", (api._json(saved), str(failure), now, job["id"]))
            return "needs_review", str(failure)
        message = self._message(db, job["record_id"], "result", manifest["text"], ids)
        saved = {**result, "text": manifest["text"], "appReport": result["text"], "targetThreadId": thread_id, "dispatchId": dispatch["id"],
            "messageId": message, "attachmentIds": ids, "executionVerified": True, "fileProof": proof, "imageProof": image_proof, "validation": manifest["validation"]}
        if ids:
            saved["primaryAttachmentId"] = ids[-1]
            db.execute("UPDATE records SET primary_attachment_id=? WHERE id=?", (ids[-1], job["record_id"]))
        db.execute("UPDATE jobs SET status='succeeded',result=?,error='',updated_at=? WHERE id=?", (api._json(saved), now, job["id"]))
        db.execute("RELEASE native_work_result")
        return status, ""

    def end_app_work(self, body, prefix="/api/workflow", authorize=None):
        """Keep a verified returned report, without accepting its failed execution claim."""
        api = _api()
        if authorize:
            authorize()
        fields = {"requestId", "jobId", "dispatchId", "sourceMessageId", "turnId"}
        if not isinstance(body, dict) or set(body) != fields:
            raise api.WorkflowError("请明确核对这轮已返回的 Work，再保留当前底稿并结束。")
        job_id, dispatch_id = api._id(body["jobId"]), api._id(body["dispatchId"])
        source_id, turn_id = api._text(body["sourceMessageId"], 160), api._text(body["turnId"], 160)
        if not source_id.strip() or not turn_id.strip():
            raise api.WorkflowError("未知送达的 Work 不能结束，须先核对实际返回。", 409, "verification_required")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "end_app_work", body)
            dispatch = self._dispatch(db, dispatch_id)
            snapshot = json.loads(dispatch["snapshot"])
            if snapshot.get("origin") != "workflow_work":
                raise api.WorkflowError("此操作仅适用于已回收的 Native Work。", 409, "result_not_matching")
            job = self._app_dispatch_job(db, dispatch, snapshot)
            payload, result = json.loads(job["payload"]), json.loads(job["result"])
            returned = json.loads(dispatch["result"])
            if (job["id"] != job_id or payload.get("executionEngine") != "codex_app"
                    or snapshot.get("frozenPayloadSha256") != _digest(payload)):
                raise api.WorkflowError("Work 与原记录冻结内容不匹配。", 409, "result_not_matching")
            if not old:
                report = result.get("appReport")
                message = db.execute("SELECT role,text FROM messages WHERE id=? AND record_id=?",
                    (result.get("messageId"), job["record_id"])).fetchone()
                if (job["status"] != "waiting" or dispatch["status"] != "needs_review"
                        or result.get("executionVerified") is not False or not result.get("verificationError")
                        or not isinstance(report, str) or not report.strip() or result.get("text") != report
                        or returned.get("text") != report or not dispatch["target_thread_id"]
                        or result.get("targetThreadId") != dispatch["target_thread_id"]
                        or result.get("dispatchId") != dispatch_id or message is None
                        or message["role"] != "assistant" or message["text"] != report
                        or any(data.get("sourceMessageId") != source_id or data.get("turnId") != turn_id for data in (result, returned))):
                    raise api.WorkflowError("只有准确回收完成、但成果核验未通过的 Work 可以由用户结束。", 409, "verification_required")
                now = api._now()
                result.update(resolvedByUser=True, resolution="keep_current_task", resolvedAt=now)
                db.execute("UPDATE jobs SET status='failed',result=?,updated_at=? WHERE id=?", (api._json(result), now, job_id))
                # completed is the delivery/collection state; the actual execution remains failed.
                db.execute("UPDATE idea_dispatches SET status='completed',updated_at=? WHERE id=?", (now, dispatch_id))
                self._receipt(db, "end_app_work", body, {"jobId": job_id, "dispatchId": dispatch_id})
                self._revision(db, True)
            if authorize:
                authorize()
            return {"job": self._job_public(db, db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()),
                    "dispatch": self._public_dispatch(self._dispatch(db, dispatch_id)), "revision": self._revision(db), "duplicate": old is not None}
