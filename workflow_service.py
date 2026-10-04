"""Private durable phone review/AI/work queue, independent of Codex chat."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlencode
import uuid

from transfer_store import IncomingFile, TransferError, _image, _filename, _safe_child, MAX_FILE_BYTES

MAX_TEXT = 20000
MAX_UPLOAD = 24 * 1024 * 1024
MAX_ATTACHMENTS = 4
MAX_LOG = 48000
ACTIONS = {"auto", "capture_screen", "command", "generated_script", "result_import"}
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
               ".gif": "image/gif", ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif"}
AUDIO_TYPES = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
               ".mp4": "audio/mp4", ".webm": "audio/webm", ".ogg": "audio/ogg"}
IDEA_STAGES = {"vague", "thinking", "ready", "queued", "published"}
IDEA_PRIORITIES = {"high", "normal", "low"}
IDEA_TARGETS = {"none", "codex", "chatgpt"}
IDEA_FIELDS = {"title", "body", "stage", "priority", "parentId", "targetKind", "targetThreadId", "targetName"}
DISPATCH_OPEN = {"pending", "claimed", "waiting", "needs_review"}


class WorkflowError(ValueError):
    def __init__(self, message, status=400, code="invalid_request"):
        super().__init__(message)
        self.status, self.code = status, code


def _now():
    return datetime.now(timezone.utc).isoformat()


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise WorkflowError("记录或附件标识无效。", 404)
    return value


def _key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value):
        raise WorkflowError("项目或选项标识无效。")
    return value


def _text(value, limit=MAX_TEXT):
    if not isinstance(value, str) or len(value) > limit or "\0" in value:
        raise WorkflowError("文字内容无效或过长。")
    return value


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class WorkflowService:
    def __init__(self, data_dir, models=None, callbacks=None, projects=None, *, computer_id=None, computer_name=None, recover_jobs=True):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.attachments_dir = _safe_child(self.data_dir, "attachments")
        self.jobs_dir = _safe_child(self.data_dir, "jobs")
        self.attachments_dir.mkdir(exist_ok=True)
        self.jobs_dir.mkdir(exist_ok=True)
        self.models, self.callbacks = models, callbacks or {}
        self._lock, self._wake, self._stop = threading.RLock(), threading.Event(), threading.Event()
        self._thread, self._process = None, None
        with self._db() as db:
            if self._setting(db, "computer") is None:
                self._set_setting(db, "computer", {"id": computer_id or uuid.uuid4().hex, "name": computer_name or socket.gethostname()})
            if projects is not None and self._setting(db, "projects") is None:
                self._set_setting(db, "projects", self._validate_projects(projects))
            recovered = 0
            if recover_jobs:
                recovered = db.execute("UPDATE jobs SET status='interrupted',error='电脑进程已中断；请明确重试，新尝试不会自动重复执行。',updated_at=? WHERE status='running'", (_now(),)).rowcount
                recovered += db.execute("UPDATE idea_dispatches SET status='needs_review',error='发布过程中电脑服务重启；请核对目标聊天，不能自动重发。',updated_at=? WHERE status='claimed'", (_now(),)).rowcount
            if recovered:
                self._revision(db, True)
            db.commit()

    @contextmanager
    def _db(self):
        with self._lock:
            path = _safe_child(self.data_dir, "workflow.sqlite3")
            db = sqlite3.connect(path, timeout=15)
            db.row_factory = sqlite3.Row
            try:
                db.executescript("""
                    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
                    INSERT OR IGNORE INTO settings VALUES ('revision','0');
                    CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY,title TEXT NOT NULL,project_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,updated_at TEXT NOT NULL,primary_attachment_id TEXT,context TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY,record_id TEXT NOT NULL,role TEXT NOT NULL,
                        text TEXT NOT NULL,created_at TEXT NOT NULL,attachment_ids TEXT NOT NULL,options TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS attachments (id TEXT PRIMARY KEY,record_id TEXT NOT NULL,name TEXT NOT NULL,
                        filename TEXT NOT NULL,mime_type TEXT NOT NULL,size INTEGER NOT NULL,preview INTEGER NOT NULL,duration REAL);
                    CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY,record_id TEXT NOT NULL,kind TEXT NOT NULL,
                        request_id TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,attempt INTEGER NOT NULL,
                        parent_id TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,error TEXT NOT NULL,log TEXT NOT NULL,result TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY,kind TEXT NOT NULL,fingerprint TEXT NOT NULL,response TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS ideas (id TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,
                        stage TEXT NOT NULL,priority TEXT NOT NULL,parent_id TEXT,target_kind TEXT NOT NULL,
                        target_thread_id TEXT NOT NULL,target_name TEXT NOT NULL,revision INTEGER NOT NULL,
                        created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
                    CREATE INDEX IF NOT EXISTS message_records ON messages(record_id);
                    CREATE INDEX IF NOT EXISTS job_status ON jobs(status);
                    CREATE INDEX IF NOT EXISTS idea_parents ON ideas(parent_id);
                    CREATE TABLE IF NOT EXISTS idea_dispatches (id TEXT PRIMARY KEY,idea_id TEXT NOT NULL,
                        request_id TEXT NOT NULL UNIQUE,snapshot TEXT NOT NULL,prompt TEXT NOT NULL,
                        target_kind TEXT NOT NULL,target_mode TEXT NOT NULL,target_thread_id TEXT,target_name TEXT NOT NULL,
                        priority TEXT NOT NULL,status TEXT NOT NULL,result TEXT NOT NULL,error TEXT NOT NULL,
                        claim_token TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,user_confirmed_at TEXT NOT NULL);
                    CREATE INDEX IF NOT EXISTS idea_dispatch_status ON idea_dispatches(status,priority,created_at);
                    CREATE TABLE IF NOT EXISTS idea_refinements (id TEXT PRIMARY KEY,idea_id TEXT NOT NULL,
                        state TEXT NOT NULL,round INTEGER NOT NULL,round_limit INTEGER NOT NULL,
                        target_kind TEXT NOT NULL,target_thread_id TEXT,target_name TEXT NOT NULL,
                        user_confirmed_at TEXT NOT NULL,error TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS conversation_threads (id TEXT PRIMARY KEY,generation INTEGER NOT NULL,
                        cached_generation INTEGER NOT NULL,fetched_at TEXT,payload TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS conversation_pages (thread_id TEXT NOT NULL,generation INTEGER NOT NULL,
                        cursor TEXT NOT NULL,fetched_at TEXT NOT NULL,payload TEXT NOT NULL,
                        PRIMARY KEY(thread_id,generation,cursor));
                    CREATE TABLE IF NOT EXISTS conversation_requests (id TEXT PRIMARY KEY,thread_id TEXT NOT NULL,
                        mode TEXT NOT NULL,generation INTEGER NOT NULL,cursor TEXT NOT NULL,status TEXT NOT NULL,
                        error TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
                    CREATE INDEX IF NOT EXISTS conversation_request_status ON conversation_requests(status,created_at);
                """)
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    @staticmethod
    def _setting(db, key):
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def _set_setting(db, key, value):
        db.execute("INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, _json(value)))

    def _revision(self, db, change=False):
        value = int(self._setting(db, "revision") or 0) + int(change)
        if change:
            self._set_setting(db, "revision", value)
        return str(value)

    def _validate_projects(self, projects):
        if not isinstance(projects, list) or len(projects) > 16:
            raise WorkflowError("项目授权列表无效。")
        clean, seen = [], set()
        for item in projects:
            if not isinstance(item, dict) or set(item) - {"id", "name", "root", "capabilities", "commands", "allowGeneratedScripts", "scriptRunners", "timeout"}:
                raise WorkflowError("项目授权内容无效。")
            identifier = _key(item.get("id"))
            root = Path(_text(item.get("root"), 2048)).expanduser().resolve()
            if identifier in seen or not root.is_dir():
                raise WorkflowError("项目目录不存在或项目重复。")
            capabilities = item.get("capabilities", [])
            if not isinstance(capabilities, list) or any(action not in ACTIONS - {"auto"} for action in capabilities):
                raise WorkflowError("项目能力授权无效。")
            commands, command_ids = [], set()
            for command in item.get("commands", []):
                if not isinstance(command, dict) or set(command) - {"id", "name", "argv", "timeout"}:
                    raise WorkflowError("指定脚本授权无效。")
                cid = _key(command.get("id"))
                argv = self._argv(command.get("argv"))
                if cid in command_ids:
                    raise WorkflowError("指定脚本重复。")
                command_ids.add(cid)
                commands.append({"id": cid, "name": _text(command.get("name", cid), 120), "argv": argv,
                                 "timeout": self._timeout(command.get("timeout", item.get("timeout", 120)))})
            runners = item.get("scriptRunners", {})
            if not isinstance(runners, dict) or set(runners) - {"python", "powershell"}:
                raise WorkflowError("脚本运行程序无效。")
            allow = item.get("allowGeneratedScripts", False)
            if type(allow) is not bool:
                raise WorkflowError("脚本授权须明确开启或关闭。")
            clean.append({"id": identifier, "name": _text(item.get("name", identifier), 120), "root": str(root),
                          "capabilities": list(dict.fromkeys(capabilities)), "commands": commands,
                          "allowGeneratedScripts": allow, "scriptRunners": {language: self._argv(argv) for language, argv in runners.items()},
                          "timeout": self._timeout(item.get("timeout", 120))})
            seen.add(identifier)
        return clean

    @staticmethod
    def _timeout(value):
        if type(value) is not int or not 1 <= value <= 600:
            raise WorkflowError("脚本超时须为 1 至 600 秒。")
        return value

    @staticmethod
    def _argv(argv):
        if not isinstance(argv, list) or not 1 <= len(argv) <= 32 or any(not isinstance(arg, str) or not arg or len(arg) > 4096 or "\0" in arg for arg in argv):
            raise WorkflowError("指定脚本参数无效。")
        executable = Path(argv[0])
        if not executable.is_absolute() or not executable.is_file():
            raise WorkflowError("请指定实际存在的脚本运行程序完整路径。")
        return [str(executable.resolve()), *argv[1:]]

    def configure_projects(self, projects):
        # Keep an upsert's read/merge/write atomic with execution authorization.
        with self._lock:
            return self._configure_projects(projects)

    def _configure_projects(self, projects):
        if isinstance(projects, dict):
            if set(projects) == {"project"}:
                update = projects["project"]
                if not isinstance(update, dict) or set(update) - {"id", "name", "root", "capabilities", "allowGeneratedScripts", "commands", "scriptRunners", "timeout"}:
                    raise WorkflowError("项目授权修改无效。")
                identifier = _key(update.get("id"))
                with self._db() as db:
                    existing = self._setting(db, "projects") or []
                    previous = next((item for item in existing if item["id"] == identifier),
                                    {"id": identifier, "capabilities": ["capture_screen", "result_import"], "allowGeneratedScripts": False})
                    merged = self._validate_projects([{**previous, **update}])[0]
                    projects = [item for item in existing if item["id"] != identifier] + [merged]
            elif set(projects) == {"projects"}:
                projects = projects["projects"]
            else:
                raise WorkflowError("项目配置无效。")
        with self._db() as db:
            self._set_setting(db, "projects", self._validate_projects(projects))
            self._revision(db, True)
        return self.config()

    @property
    def background_enabled(self):
        with self._db() as db:
            return self._setting(db, "background") is True

    def configure_background(self, enabled):
        if type(enabled) is not bool:
            raise WorkflowError("后台接收设置无效。")
        with self._db() as db:
            self._set_setting(db, "background", enabled)
            self._revision(db, True)
        return self.config()

    def config(self):
        with self._db() as db:
            projects = self._setting(db, "projects") or []
            computer = self._setting(db, "computer")
        return {"computer": computer, "projects": [{"id": p["id"], "name": p["name"], "capabilities": p["capabilities"],
                "allowGeneratedScripts": p["allowGeneratedScripts"], "commands": [{"id": c["id"], "name": c["name"]} for c in p["commands"]]} for p in projects],
                "actions": [{"id": action, "name": {"auto": "AI 规划并执行", "capture_screen": "截图", "command": "指定脚本", "generated_script": "生成并运行项目脚本", "result_import": "导入项目结果"}[action]} for action in sorted(ACTIONS)],
                "models": self.models.config() if self.models is not None else {"ready": False, "selected": "", "providers": [], "status": "未配置 AI"},
                "backgroundEnabled": self.background_enabled, "limits": {"maxTextChars": MAX_TEXT, "maxFiles": MAX_ATTACHMENTS, "maxFileBytes": MAX_FILE_BYTES}}

    def _project(self, db, identifier):
        for project in self._setting(db, "projects") or []:
            if project["id"] == identifier:
                root = Path(project["root"])
                if not root.is_dir() or root.resolve() != root or root.is_symlink() or getattr(root, "is_junction", lambda: False)():
                    raise WorkflowError("已授权项目目录无法访问。", 503)
                return project
        raise WorkflowError("项目尚未在电脑授权。", 403)

    def _execution_project(self, db, expected, action, command_id=None, language=None):
        """Recheck the exact execution grant while holding the configuration lock."""
        current = self._project(db, expected["id"])
        unchanged = current["root"] == expected["root"] and action in current["capabilities"]
        if action == "command":
            old = next((item for item in expected["commands"] if item["id"] == command_id), None)
            new = next((item for item in current["commands"] if item["id"] == command_id), None)
            unchanged = unchanged and old is not None and new is not None and old["argv"] == new["argv"] and old["timeout"] == new["timeout"]
        elif action == "generated_script":
            unchanged = unchanged and current["allowGeneratedScripts"] and current["timeout"] == expected["timeout"]
            unchanged = unchanged and bool(current["scriptRunners"].get(language)) and current["scriptRunners"].get(language) == expected["scriptRunners"].get(language)
        if not unchanged:
            raise WorkflowError("项目执行授权已变更；任务未继续执行，请重新确认后派工。", 403, "permission_changed")
        return current

    @staticmethod
    def _record(db, identifier):
        row = db.execute("SELECT * FROM records WHERE id=?", (_id(identifier),)).fetchone()
        if row is None:
            raise WorkflowError("记录不存在。", 404)
        return row

    @staticmethod
    def _public_record(row):
        return {"id": row["id"], "title": row["title"], "projectId": row["project_id"], "createdAt": row["created_at"],
                "updatedAt": row["updated_at"], "primaryAttachmentId": row["primary_attachment_id"], "context": json.loads(row["context"])}

    @staticmethod
    def _public_job(row):
        payload, result = json.loads(row["payload"]), json.loads(row["result"])
        return {"id": row["id"], "recordId": row["record_id"], "kind": row["kind"], "requestId": row["request_id"],
                "instruction": payload.get("text", ""), "projectId": payload.get("projectId", ""), "action": payload.get("action", ""),
                "computerId": payload.get("computerId", ""),
                "status": row["status"], "attempt": row["attempt"], "parentJobId": row["parent_id"], "createdAt": row["created_at"],
                "updatedAt": row["updated_at"], "error": row["error"], "log": row["log"], "result": result,
                "resultMessageId": result.get("messageId"), "resultAttachmentIds": result.get("attachmentIds", [])}

    def detail(self, identifier, prefix="/api/workflow"):
        with self._db() as db:
            row = self._record(db, identifier)
            attachments = []
            for item in db.execute("SELECT * FROM attachments WHERE record_id=? ORDER BY rowid", (identifier,)):
                url = prefix + "/attachment?" + urlencode({"id": item["id"]})
                attachments.append({"id": item["id"], "name": item["name"], "mimeType": item["mime_type"], "size": item["size"],
                                    "url": url, "previewUrl": url + "&preview=1" if item["preview"] else None, "duration": item["duration"]})
            messages = [{"id": item["id"], "role": item["role"], "text": item["text"], "createdAt": item["created_at"],
                         "attachmentIds": json.loads(item["attachment_ids"]), "options": json.loads(item["options"])}
                        for item in db.execute("SELECT * FROM messages WHERE record_id=? ORDER BY rowid", (identifier,))]
            jobs = [self._public_job(item) for item in db.execute("SELECT * FROM jobs WHERE record_id=? ORDER BY rowid", (identifier,))]
            return {"record": self._public_record(row), "messages": messages, "attachments": attachments, "jobs": jobs, "revision": self._revision(db)}

    def list(self, query="", prefix="/api/workflow"):
        params = parse_qs(query, keep_blank_values=True)
        if len(query) > 256 or set(params) - {"limit", "before", "revision"} or any(len(values) != 1 for values in params.values()):
            raise WorkflowError("记录列表请求无效。")
        limit = params.get("limit", ["30"])[0]
        if not re.fullmatch(r"[0-9]{1,2}", limit) or not 1 <= int(limit) <= 50:
            raise WorkflowError("记录数量无效。")
        with self._db() as db:
            revision = self._revision(db)
            if params.get("revision", [None])[0] == revision and "before" not in params:
                return {"unchanged": True, "revision": revision}
            before = params.get("before", [""])[0]
            position = self._record(db, before)["created_at"] if before else None
            rows = db.execute("SELECT * FROM records WHERE (? IS NULL OR created_at<?) ORDER BY created_at DESC LIMIT ?", (position, position, int(limit) + 1)).fetchall()
            records = []
            for row in rows[:int(limit)]:
                item = self._public_record(row)
                primary = db.execute("SELECT preview FROM attachments WHERE id=?", (row["primary_attachment_id"],)).fetchone()
                item["thumbnailUrl"] = prefix + "/attachment?" + urlencode({"id": row["primary_attachment_id"], **({"preview": "1"} if primary and primary["preview"] else {})}) if row["primary_attachment_id"] else None
                records.append(item)
            return {"records": records, "hasMore": len(rows) > int(limit), "revision": revision}

    @staticmethod
    def _idea_prompt(value):
        priority = {"high": "高", "normal": "普通", "low": "低"}[value["priority"]]
        stage = {"vague": "模糊", "thinking": "思考中", "ready": "已成熟", "queued": "已排队", "published": "已发布"}[value["stage"]]
        return ("以下是我从任务孵化器主动发布的想法，请根据内容继续讨论或推进。\n\n"
                f"标题：{value['title']}\n优先级：{priority}\n成熟度：{stage}\n\n"
                + (value["body"] or "（尚无正文，请先协助明确这个想法。）"))

    @staticmethod
    def _public_idea(row):
        value = {"id": row["id"], "title": row["title"], "body": row["body"], "stage": row["stage"],
                "priority": row["priority"], "parentId": row["parent_id"], "targetKind": row["target_kind"],
                "targetThreadId": row["target_thread_id"], "targetName": row["target_name"],
                "revision": row["revision"], "createdAt": row["created_at"], "updatedAt": row["updated_at"]}
        value["publishPrompt"] = WorkflowService._idea_prompt(value)
        return value

    @staticmethod
    def _public_dispatch(row, private=False):
        snapshot = json.loads(row["snapshot"])
        value = {"id": row["id"], "ideaId": row["idea_id"], "snapshot": snapshot,
                 "prompt": row["prompt"], "targetKind": row["target_kind"], "targetMode": row["target_mode"],
                 "targetThreadId": row["target_thread_id"], "targetName": row["target_name"], "status": row["status"],
                 "result": json.loads(row["result"]), "error": row["error"], "createdAt": row["created_at"],
                 "updatedAt": row["updated_at"], "userConfirmedAt": row["user_confirmed_at"],
                 "purpose": snapshot.get("purpose", "execute"), "refinementId": snapshot.get("refinementId"),
                 "round": snapshot.get("round"), "roundLimit": snapshot.get("roundLimit")}
        if private:
            value["claimToken"] = row["claim_token"]
        return value

    @staticmethod
    def _dispatch(db, identifier):
        row = db.execute("SELECT * FROM idea_dispatches WHERE id=?", (_id(identifier),)).fetchone()
        if row is None:
            raise WorkflowError("发布记录不存在。", 404)
        return row

    @staticmethod
    def _idea(db, identifier):
        row = db.execute("SELECT * FROM ideas WHERE id=?", (_id(identifier),)).fetchone()
        if row is None:
            raise WorkflowError("想法不存在。", 404, "idea_not_found")
        return row

    def incubator_list(self, query="", prefix="/api/workflow"):
        params = parse_qs(query, keep_blank_values=True)
        if (len(query) > 64 or set(params) - {"revision"} or any(len(values) != 1 for values in params.values())
                or ("revision" in params and not re.fullmatch(r"[0-9]{1,20}", params["revision"][0]))):
            raise WorkflowError("想法列表请求无效。")
        with self._db() as db:
            db.execute("BEGIN")
            revision = self._revision(db)
            if params.get("revision", [None])[0] == revision:
                return {"unchanged": True, "revision": revision}
            rows = db.execute("""SELECT * FROM ideas ORDER BY
                CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,updated_at DESC,id""").fetchall()
            dispatches = db.execute("SELECT * FROM idea_dispatches ORDER BY created_at DESC,id").fetchall()
            return {"ideas": [self._public_idea(row) for row in rows], "revision": revision,
                    "dispatches": [self._public_dispatch(row) for row in dispatches],
                    "refinements": [self._public_refinement(row) for row in db.execute("SELECT * FROM idea_refinements ORDER BY created_at DESC,id")],
                    "targets": self._setting(db, "incubator_targets") or []}

    def _clean_idea(self, db, value, identifier):
        clean = {"title": _text(value.get("title", "新想法"), 160).strip(),
                 "body": _text(value.get("body", "")), "stage": value.get("stage", "vague"),
                 "priority": value.get("priority", "normal"), "parentId": value.get("parentId"),
                 "targetKind": value.get("targetKind", "none"),
                 "targetThreadId": _text(value.get("targetThreadId", ""), 128).strip(),
                 "targetName": _text(value.get("targetName", ""), 120).strip()}
        if not clean["title"]:
            raise WorkflowError("请填写想法标题。")
        for field, allowed in (("stage", IDEA_STAGES), ("priority", IDEA_PRIORITIES), ("targetKind", IDEA_TARGETS)):
            if not isinstance(clean[field], str) or clean[field] not in allowed:
                raise WorkflowError("想法阶段、优先级或目标类型无效。")
        if clean["parentId"] == "":
            clean["parentId"] = None
        parent, ancestors = clean["parentId"], set()
        while parent is not None:
            parent = _id(parent)
            if parent == identifier or parent in ancestors:
                raise WorkflowError("父想法不能形成循环。", 409, "idea_cycle")
            ancestors.add(parent)
            parent = self._idea(db, parent)["parent_id"]
        if clean["targetKind"] == "none":
            clean["targetThreadId"] = clean["targetName"] = ""
        elif clean["targetThreadId"]:
            if clean["targetKind"] == "codex":
                try:
                    clean["targetThreadId"] = str(uuid.UUID(clean["targetThreadId"]))
                except ValueError:
                    raise WorkflowError("Codex 目标聊天标识须为 UUID。") from None
            elif not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", clean["targetThreadId"]):
                raise WorkflowError("ChatGPT 目标聊天标识无效。")
        return clean

    def _incubator_mutation(self, action, body, authorize):
        if authorize:
            authorize()
        allowed = IDEA_FIELDS | {"requestId"} | ({"id", "expectedRevision"} if action == "update" else set())
        if not isinstance(body, dict) or set(body) - allowed:
            raise WorkflowError("想法保存内容无效。")
        if action == "update":
            _id(body.get("id"))
            if type(body.get("expectedRevision")) is not int or not 1 <= body["expectedRevision"] <= 9007199254740991:
                raise WorkflowError("修改想法须提供当前 revision。")
            if not (set(body) & IDEA_FIELDS):
                raise WorkflowError("请选择要修改的想法内容。")
        with self._db() as db:
            # One write lock covers idempotency, revisions and tree checks across processes.
            db.execute("BEGIN IMMEDIATE")
            kind = "incubator_" + action
            old = self._receipt(db, kind, body)
            if old:
                identifier = old["ideaId"]
            else:
                if action == "update":
                    previous = self._idea(db, body["id"])
                    if previous["revision"] != body["expectedRevision"]:
                        raise WorkflowError("想法已在另一端修改；请保留草稿，刷新后再合并。", 409, "revision_conflict")
                    identifier = previous["id"]
                    clean = self._clean_idea(db, {**self._public_idea(previous), **body}, identifier)
                    now, revision = _now(), previous["revision"] + 1
                    db.execute("""UPDATE ideas SET title=?,body=?,stage=?,priority=?,parent_id=?,target_kind=?,
                        target_thread_id=?,target_name=?,revision=?,updated_at=? WHERE id=?""",
                        (clean["title"], clean["body"], clean["stage"], clean["priority"], clean["parentId"],
                         clean["targetKind"], clean["targetThreadId"], clean["targetName"], revision, now, identifier))
                    for session in db.execute("SELECT * FROM idea_refinements WHERE idea_id=? AND state='active'", (identifier,)).fetchall():
                        db.execute("UPDATE idea_refinements SET state='needs_review',error='想法已编辑；保留新正文，后续完善已停止。',updated_at=? WHERE id=?", (now, session["id"]))
                        self._cancel_refinement_pending(db, session["id"], now, "想法已编辑；未发送的完善轮次已取消。")
                else:
                    identifier, now = uuid.uuid4().hex, _now()
                    clean = self._clean_idea(db, body, identifier)
                    db.execute("INSERT INTO ideas VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (identifier, clean["title"], clean["body"], clean["stage"], clean["priority"], clean["parentId"],
                         clean["targetKind"], clean["targetThreadId"], clean["targetName"], 1, now, now))
                self._receipt(db, kind, body, {"ideaId": identifier})
                self._revision(db, True)
            result = {"idea": self._public_idea(self._idea(db, identifier)), "revision": self._revision(db), "duplicate": old is not None}
            if authorize:
                authorize()
            return result

    def incubator_create(self, body, prefix="/api/workflow", authorize=None):
        return self._incubator_mutation("create", body, authorize)

    def incubator_update(self, body, prefix="/api/workflow", authorize=None):
        return self._incubator_mutation("update", body, authorize)

    @staticmethod
    def _thread_id(value):
        if not isinstance(value, str):
            raise WorkflowError("目标聊天标识须为 UUID。")
        try:
            return str(uuid.UUID(value))
        except ValueError:
            raise WorkflowError("目标聊天标识须为 UUID。") from None

    @staticmethod
    def _source_time(value):
        try:
            parsed = datetime.fromisoformat(_text(value, 64).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError()
            return parsed.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            raise WorkflowError("快照时间须为包含时区的 ISO 时间。") from None

    @staticmethod
    def _conversation_status(value):
        if isinstance(value, str):
            return _text(value, 80)
        if isinstance(value, dict) and not set(value) - {"type", "activeFlags"}:
            flags = value.get("activeFlags", [])
            if isinstance(flags, list) and len(flags) <= 16:
                return {"type": _text(value.get("type", ""), 80), "activeFlags": [_text(flag, 80) for flag in flags]}
        raise WorkflowError("会话状态快照无效。")

    @staticmethod
    def _conversation_path(value):
        # Match source paths without touching files or probing other projects.
        return value.replace("\\", "/").rstrip("/").casefold()

    def conversations_catalog(self, body):
        if (not isinstance(body, dict) or set(body) - {"requestId", "fetchedAt", "projects", "threads", "partial"}
                or not isinstance(body.get("projects"), list) or len(body["projects"]) > 256
                or not isinstance(body.get("threads"), list) or len(body["threads"]) > 2000):
            raise WorkflowError("会话目录快照无效。")
        source_time = self._source_time(body.get("fetchedAt"))
        partial = body.get("partial", True)
        if type(partial) is not bool:
            raise WorkflowError("快照范围标记无效。")
        projects, threads, seen = [], [], set()
        for source in body["projects"]:
            if not isinstance(source, dict) or set(source) - {"id", "label", "path"}:
                raise WorkflowError("项目快照无效。")
            item = {"id": _text(source.get("id"), 256), "label": _text(source.get("label"), 256),
                    "path": _text(source.get("path", ""), 4096)}
            if not item["id"].strip() or not item["label"].strip() or item["id"] in seen:
                raise WorkflowError("项目标识或名称无效。")
            seen.add(item["id"])
            projects.append(item)
        seen.clear()
        for source in body["threads"]:
            if not isinstance(source, dict) or set(source) - {"id", "title", "kind", "hostId", "projectId", "cwd", "status", "unread", "updatedAt"}:
                raise WorkflowError("会话快照无效。")
            item = {"id": self._thread_id(source.get("id")), "title": _text(source.get("title"), 256), "kind": source.get("kind")}
            if not item["title"].strip() or not isinstance(item["kind"], str) or item["kind"] not in {"codex", "chatgpt"} or item["id"] in seen:
                raise WorkflowError("会话类型、标题或标识无效。")
            seen.add(item["id"])
            for key, limit in (("hostId", 120), ("projectId", 256), ("cwd", 4096)):
                if source.get(key) is not None:
                    item[key] = _text(source[key], limit)
            if "status" in source:
                item["status"] = self._conversation_status(source["status"])
            if "unread" in source:
                if type(source["unread"]) is not bool:
                    raise WorkflowError("会话未读标记无效。")
                item["unread"] = source["unread"]
            if source.get("updatedAt") is not None:
                self._source_time(source["updatedAt"])
                item["updatedAt"] = source["updatedAt"]
            if not item.get("projectId") and item.get("cwd"):
                cwd = self._conversation_path(item["cwd"])
                candidates = [p for p in projects if p["path"] and (cwd == self._conversation_path(p["path"])
                    or cwd.startswith(self._conversation_path(p["path"]) + "/"))]
                if candidates:
                    item["projectId"] = max(candidates, key=lambda p: len(self._conversation_path(p["path"])))["id"]
            threads.append(item)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "conversation_catalog", body)
            previous = self._setting(db, "conversations_catalog")
            ignored = previous is not None and source_time < self._source_time(previous["fetchedAt"])
            if not old:
                if not ignored:
                    self._set_setting(db, "conversations_catalog", {"projects": projects, "threads": threads,
                        "fetchedAt": body["fetchedAt"], "partial": partial})
                    self._revision(db, True)
                self._receipt(db, "conversation_catalog", body, {"saved": not ignored})
        result = self.conversations_list()
        return {**result, "duplicate": old is not None, "ignored": ignored}

    @staticmethod
    def _public_fetch(row):
        return {"id": row["id"], "threadId": row["thread_id"], "mode": row["mode"],
                "generation": row["generation"], "cursor": row["cursor"], "status": row["status"],
                "error": row["error"], "createdAt": row["created_at"], "updatedAt": row["updated_at"]}

    def conversations_list(self, query=""):
        params = parse_qs(query, keep_blank_values=True)
        if (len(query) > 64 or set(params) - {"revision"} or any(len(v) != 1 for v in params.values())
                or ("revision" in params and not re.fullmatch(r"[0-9]{1,20}", params["revision"][0]))):
            raise WorkflowError("会话目录请求无效。")
        with self._db() as db:
            db.execute("BEGIN")
            revision = self._revision(db)
            if params.get("revision", [None])[0] == revision:
                return {"unchanged": True, "revision": revision}
            catalog = self._setting(db, "conversations_catalog") or {"projects": [], "threads": [], "fetchedAt": None, "partial": True}
            rows = db.execute("SELECT * FROM conversation_requests ORDER BY created_at DESC,id LIMIT 100").fetchall()
            return {**catalog, "requests": [self._public_fetch(row) for row in rows], "revision": revision}

    @staticmethod
    def _conversation_state(db, identifier):
        return db.execute("SELECT * FROM conversation_threads WHERE id=?", (identifier,)).fetchone()

    def _conversation_detail(self, db, identifier):
        catalog = self._setting(db, "conversations_catalog") or {"threads": []}
        thread = next((item for item in catalog["threads"] if item["id"] == identifier), {"id": identifier})
        state = self._conversation_state(db, identifier)
        pages, seen, cursor, partial, coverage, fetched = [], set(), "", True, {}, None
        if state:
            generation = state["cached_generation"]
            while cursor not in seen:
                row = db.execute("SELECT * FROM conversation_pages WHERE thread_id=? AND generation=? AND cursor=?",
                    (identifier, generation, cursor)).fetchone()
                if row is None:
                    break
                seen.add(cursor)
                payload = json.loads(row["payload"])
                pages.append(payload)
                if len(pages) == 1:
                    partial, coverage, fetched = payload["partial"], payload["coverage"], row["fetched_at"]
                else:
                    partial = partial or payload["partial"]
                if payload["olderCursor"] is None:
                    cursor = None
                    break
                cursor = payload["olderCursor"]
            ordered = {}
            for page in reversed(pages):
                for message in page["messages"]:
                    ordered[message["id"]] = message
            messages = list(ordered.values())
            if not pages:
                cursor = None
            descriptions = list(dict.fromkeys(page["coverage"]["description"] for page in pages))
            coverage = {**coverage, "description": "；".join(descriptions)[:4096]} if descriptions else coverage
            partial = partial or bool(cursor) or any(message["truncated"] for message in messages)
        else:
            messages, cursor = [], None
        requests = db.execute("SELECT * FROM conversation_requests WHERE thread_id=? ORDER BY created_at DESC,id LIMIT 30", (identifier,)).fetchall()
        return {"thread": thread, "messages": messages, "generation": state["generation"] if state else 0,
                "snapshotGeneration": state["cached_generation"] if state else 0, "fetchedAt": fetched,
                "partial": partial, "olderCursor": cursor, "hasMore": bool(cursor),
                "coverage": {**coverage, "description": coverage.get("description", "尚未抓取；显示的是已保存缓存。"),
                             "messageCount": len(messages), "pageCount": len(pages)},
                "requests": [self._public_fetch(row) for row in requests], "revision": self._revision(db)}

    def conversations_thread(self, identifier):
        identifier = self._thread_id(identifier)
        with self._db() as db:
            db.execute("BEGIN")
            return self._conversation_detail(db, identifier)

    def conversations_request(self, body, prefix="/api/workflow", authorize=None):
        if authorize:
            authorize()
        if (not isinstance(body, dict) or set(body) - {"requestId", "threadId", "mode"}
                or not isinstance(body.get("mode"), str) or body["mode"] not in {"refresh", "older"}):
            raise WorkflowError("会话抓取请求无效。")
        identifier, mode = self._thread_id(body.get("threadId")), body["mode"]
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "conversation_request", body)
            if old:
                row = db.execute("SELECT * FROM conversation_requests WHERE id=?", (old["fetchId"],)).fetchone()
            else:
                detail = self._conversation_detail(db, identifier)
                if "kind" not in detail["thread"] and not detail["snapshotGeneration"]:
                    raise WorkflowError("请先同步真实会话目录。", 404, "conversation_not_found")
                row = db.execute("SELECT * FROM conversation_requests WHERE thread_id=? AND mode=? AND status='pending'",
                    (identifier, mode)).fetchone()
                if row is None:
                    generation = detail["generation"]
                    cursor = ""
                    if mode == "refresh":
                        generation += 1
                        db.execute("UPDATE conversation_requests SET status='failed',error='新刷新已取代旧页请求。',updated_at=? WHERE thread_id=? AND status='pending'", (_now(), identifier))
                    elif not detail["olderCursor"] or detail["snapshotGeneration"] != generation:
                        raise WorkflowError("没有可读取的更早页，或新刷新尚未完成。", 409, "no_older_page")
                    else:
                        cursor = detail["olderCursor"]
                    state = self._conversation_state(db, identifier)
                    if state:
                        db.execute("UPDATE conversation_threads SET generation=? WHERE id=?", (generation, identifier))
                    else:
                        db.execute("INSERT INTO conversation_threads VALUES (?,?,0,NULL,'{}')", (identifier, generation))
                    now, fetch_id = _now(), uuid.uuid4().hex
                    db.execute("INSERT INTO conversation_requests VALUES (?,?,?,?,?,'pending','',?,?)", (fetch_id, identifier, mode, generation, cursor, now, now))
                    row = db.execute("SELECT * FROM conversation_requests WHERE id=?", (fetch_id,)).fetchone()
                    self._revision(db, True)
                self._receipt(db, "conversation_request", body, {"fetchId": row["id"]})
            if authorize:
                authorize()
            return {"fetchRequest": self._public_fetch(row), "revision": self._revision(db), "duplicate": old is not None}

    def conversations_thread_snapshot(self, body):
        allowed = {"requestId", "threadId", "generation", "mode", "cursor", "olderCursor", "fetchedAt", "partial", "coverage", "messages"}
        if (not isinstance(body, dict) or set(body) - allowed or not isinstance(body.get("mode"), str) or body["mode"] not in {"refresh", "older"}
                or type(body.get("generation")) is not int or not 1 <= body["generation"] <= 2147483647
                or not isinstance(body.get("messages"), list) or len(body["messages"]) > 256):
            raise WorkflowError("会话页面快照无效。")
        identifier, generation, mode = self._thread_id(body.get("threadId")), body["generation"], body["mode"]
        source_time = self._source_time(body.get("fetchedAt"))
        cursor = _text(body.get("cursor", ""), 2048)
        older = None if body.get("olderCursor") is None else _text(body["olderCursor"], 2048)
        partial = body.get("partial", True)
        if type(partial) is not bool or (mode == "refresh" and cursor) or (mode == "older" and not cursor) or older == cursor:
            raise WorkflowError("会话页游标或范围标记无效。")
        coverage = body.get("coverage", {})
        if not isinstance(coverage, dict) or set(coverage) - {"description", "oldestAt", "newestAt"}:
            raise WorkflowError("会话缓存范围无效。")
        clean_coverage = {"description": _text(coverage.get("description", "App Tools 实际可读消息缓存；可能含截断或缺页。"), 1024)}
        for key in ("oldestAt", "newestAt"):
            if coverage.get(key) is not None:
                self._source_time(coverage[key])
                clean_coverage[key] = coverage[key]
        messages, seen, size = [], set(), 0
        for source in body["messages"]:
            if (not isinstance(source, dict) or set(source) - {"id", "role", "text", "turnId", "sourceMessageId", "phase", "status", "createdAt", "truncated"}
                    or not isinstance(source.get("role"), str) or source["role"] not in {"user", "assistant"}):
                raise WorkflowError("会话消息快照无效。")
            message = {"id": _text(source.get("id"), 256), "role": source["role"], "text": _text(source.get("text")), "truncated": source.get("truncated", False)}
            if not message["id"] or type(message["truncated"]) is not bool:
                raise WorkflowError("会话消息标识或截断标记无效。")
            for key, limit in (("turnId", 160), ("sourceMessageId", 160), ("phase", 80)):
                if source.get(key) is not None:
                    message[key] = _text(source[key], limit)
            if "status" in source:
                message["status"] = self._conversation_status(source["status"])
            if source.get("createdAt") is not None:
                self._source_time(source["createdAt"])
                message["createdAt"] = source["createdAt"]
            if message["id"] in seen:
                raise WorkflowError("同一页面消息标识重复。")
            seen.add(message["id"])
            size += len(_json(message).encode("utf-8"))
            if size > 1024 * 1024:
                raise WorkflowError("会话缓存页面过大。", 413)
            messages.append(message)
        payload = {"messages": messages, "olderCursor": older, "partial": partial, "coverage": clean_coverage}
        ignored = False
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "conversation_snapshot", body)
            state = self._conversation_state(db, identifier)
            if not old:
                if state and (generation < state["generation"] or (mode == "refresh" and state["fetched_at"] and source_time < self._source_time(state["fetched_at"]))):
                    ignored = True
                elif mode == "older":
                    detail = self._conversation_detail(db, identifier)
                    if not state or generation != state["generation"] or generation != state["cached_generation"] or cursor != detail["olderCursor"]:
                        existing = db.execute("SELECT * FROM conversation_pages WHERE thread_id=? AND generation=? AND cursor=?", (identifier, generation, cursor)).fetchone()
                        if not existing:
                            raise WorkflowError("更早页不属于这个会话当前缓存游标。", 409, "cursor_mismatch")
                        if source_time < self._source_time(existing["fetched_at"]):
                            ignored = True
                    if older is not None and db.execute("SELECT 1 FROM conversation_pages WHERE thread_id=? AND generation=? AND cursor=?", (identifier, generation, older)).fetchone():
                        raise WorkflowError("会话分页游标形成循环。", 409, "cursor_mismatch")
                    count = db.execute("SELECT COUNT(*) FROM conversation_pages WHERE thread_id=? AND generation=?", (identifier, generation)).fetchone()[0]
                    if count >= 30 and not db.execute("SELECT 1 FROM conversation_pages WHERE thread_id=? AND generation=? AND cursor=?", (identifier, generation, cursor)).fetchone():
                        raise WorkflowError("已保存 30 页缓存；请刷新最新消息。", 409, "cache_page_limit")
                if not ignored:
                    if mode == "refresh":
                        db.execute("DELETE FROM conversation_pages WHERE thread_id=?", (identifier,))
                        db.execute("INSERT INTO conversation_threads VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET generation=excluded.generation,cached_generation=excluded.cached_generation,fetched_at=excluded.fetched_at,payload=excluded.payload",
                            (identifier, generation, generation, body["fetchedAt"], "{}"))
                        db.execute("UPDATE conversation_requests SET status='failed',error='新刷新已取代旧页请求。',updated_at=? WHERE thread_id=? AND generation<? AND status='pending'", (_now(), identifier, generation))
                    db.execute("INSERT INTO conversation_pages VALUES (?,?,?,?,?) ON CONFLICT(thread_id,generation,cursor) DO UPDATE SET fetched_at=excluded.fetched_at,payload=excluded.payload",
                        (identifier, generation, cursor, body["fetchedAt"], _json(payload)))
                    self._revision(db, True)
                self._receipt(db, "conversation_snapshot", body, {"saved": not ignored})
            result = self._conversation_detail(db, identifier)
            return {**result, "duplicate": old is not None, "ignored": ignored}

    def conversations_fetch_requests(self):
        with self._db() as db:
            db.execute("BEGIN")
            return {"requests": [self._public_fetch(row) for row in db.execute("SELECT * FROM conversation_requests WHERE status='pending' ORDER BY created_at,id")], "revision": self._revision(db)}

    def conversations_fetch_result(self, body):
        if (not isinstance(body, dict) or set(body) - {"requestId", "id", "status", "error"}
                or not isinstance(body.get("status"), str) or body["status"] not in {"completed", "failed"}):
            raise WorkflowError("会话抓取结果无效。")
        identifier, status = _id(body.get("id")), body["status"]
        error = _text(body.get("error", ""), 2000)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM conversation_requests WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise WorkflowError("会话抓取请求不存在。", 404)
            old = self._receipt(db, "conversation_fetch_result", body)
            if not old:
                if row["status"] != "pending":
                    raise WorkflowError("抓取请求已经结束或被新代际取代。", 409)
                if status == "completed":
                    page = db.execute("SELECT fetched_at FROM conversation_pages WHERE thread_id=? AND generation=? AND cursor=?", (row["thread_id"], row["generation"], row["cursor"])).fetchone()
                    if page is None or self._source_time(page["fetched_at"]) < self._source_time(row["created_at"]):
                        raise WorkflowError("请先保存这次实际抓取的新页面，不能假报完成。", 409, "snapshot_missing")
                db.execute("UPDATE conversation_requests SET status=?,error=?,updated_at=? WHERE id=?", (status, error, _now(), identifier))
                self._receipt(db, "conversation_fetch_result", body, {"fetchId": identifier})
                self._revision(db, True)
            return {"fetchRequest": self._public_fetch(db.execute("SELECT * FROM conversation_requests WHERE id=?", (identifier,)).fetchone()),
                    "revision": self._revision(db), "duplicate": old is not None}

    def incubator_publish(self, body, prefix="/api/workflow", authorize=None):
        if authorize:
            authorize()
        if (not isinstance(body, dict) or set(body) - {"requestId", "id", "expectedRevision", "targetKind", "targetMode", "targetThreadId", "targetName", "purpose", "roundLimit"}
                or type(body.get("expectedRevision")) is not int or not 1 <= body["expectedRevision"] <= 9007199254740991):
            raise WorkflowError("请确认当前想法和发布目标后再发布。")
        purpose, round_limit = body.get("purpose", "execute"), body.get("roundLimit", 3)
        if (not isinstance(purpose, str) or purpose not in {"execute", "refine"}
                or (purpose == "execute" and "roundLimit" in body)
                or (purpose == "refine" and (type(round_limit) is not int or not 1 <= round_limit <= 10))):
            raise WorkflowError("请明确完善用途及 1 至 10 次授权轮数。")
        identifier = _id(body.get("id"))
        kind, thread_id = body.get("targetKind"), body.get("targetThreadId")
        mode = body.get("targetMode", "existing" if thread_id else "new")
        if not isinstance(kind, str) or kind not in {"codex", "chatgpt"} or not isinstance(mode, str) or mode not in {"new", "existing"}:
            raise WorkflowError("请选择 Codex 或 ChatGPT 发布目标。")
        if mode == "new":
            if kind != "codex" or thread_id not in (None, ""):
                raise WorkflowError("只有 Codex 支持明确创建本机新聊天。")
            thread_id = None
        else:
            thread_id = self._thread_id(thread_id)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "incubator_publish", body)
            if old:
                dispatch_id = old["dispatchId"]
            else:
                idea = self._public_idea(self._idea(db, identifier))
                if idea["revision"] != body["expectedRevision"]:
                    raise WorkflowError("想法已变更；请保留草稿，重新核对发布内容。", 409, "revision_conflict")
                if db.execute("SELECT 1 FROM idea_dispatches WHERE idea_id=? AND status IN ('pending','claimed','waiting','needs_review')", (identifier,)).fetchone():
                    raise WorkflowError("这条想法已有未结束的发布，请先查看或核对结果。", 409, "dispatch_in_progress")
                name = _text(body.get("targetName", idea["targetName"] or idea["title"][:120]), 120).strip()
                dispatch_id, now = uuid.uuid4().hex, _now()
                snapshot = {key: idea[key] for key in ("title", "body", "stage", "priority", "revision")}
                if purpose == "refine":
                    session_id = uuid.uuid4().hex
                    db.execute("INSERT INTO idea_refinements VALUES (?,?,'active',1,?,?,?,?,?,'',?,?)",
                        (session_id, identifier, round_limit, kind, thread_id, name, now, now, now))
                    snapshot.update(purpose="refine", refinementId=session_id, round=1, roundLimit=round_limit)
                prompt = self._dispatch_prompt(dispatch_id, idea, snapshot)
                db.execute("INSERT INTO idea_dispatches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (dispatch_id, identifier, str(uuid.UUID(body["requestId"])), _json(snapshot), prompt, kind,
                     mode, thread_id, name, idea["priority"], "pending", "{}", "", None, now, now, now))
                db.execute("UPDATE ideas SET stage='queued',target_kind=?,target_thread_id=?,target_name=?,revision=revision+1,updated_at=? WHERE id=?",
                    (kind, thread_id or "", name, now, identifier))
                self._receipt(db, "incubator_publish", body, {"dispatchId": dispatch_id})
                self._revision(db, True)
            result = {"dispatch": self._public_dispatch(self._dispatch(db, dispatch_id)),
                      "idea": self._public_idea(self._idea(db, identifier)), "revision": self._revision(db), "duplicate": old is not None}
            session_id = result["dispatch"]["refinementId"]
            if session_id:
                result["refinement"] = self._public_refinement(db.execute("SELECT * FROM idea_refinements WHERE id=?", (session_id,)).fetchone())
            if authorize:
                authorize()
            return result

    @staticmethod
    def _dispatch_prompt(dispatch_id, idea, snapshot):
        marker = f"[Codex Console 发布编号：{dispatch_id}]\n\n"
        if snapshot.get("purpose") != "refine":
            return marker + idea["publishPrompt"]
        return (marker + f"这是任务孵化器的第 {snapshot['round']}/{snapshot['roundLimit']} 轮提示词完善。\n"
                "本次只授权分析、澄清、检查遗漏并重写下面的完整任务稿；禁止执行任务、运行命令、修改项目、发送消息或建立其他聊天。\n"
                "保留用户意图与限制，避免加入未经授权的操作。请指出关键缺口，再给出可直接保存的完整新版正文。\n"
                "完整稿须且仅须放在一个 <refined_prompt>完整新版正文</refined_prompt> 块中，不在块内使用该标签；不要只给差异或声称已经执行。\n\n"
                + f"标题：{idea['title']}\n\n原稿：\n" + (idea["body"] or "（请先帮助明确此想法，不能自行执行。）"))

    @staticmethod
    def _public_refinement(row):
        return {"id": row["id"], "ideaId": row["idea_id"], "state": row["state"], "round": row["round"],
                "roundLimit": row["round_limit"], "targetKind": row["target_kind"], "targetThreadId": row["target_thread_id"],
                "targetName": row["target_name"], "userConfirmedAt": row["user_confirmed_at"], "error": row["error"],
                "createdAt": row["created_at"], "updatedAt": row["updated_at"]}

    @staticmethod
    def _cancel_refinement_pending(db, session_id, now, error):
        db.execute("UPDATE idea_dispatches SET status='failed',error=?,updated_at=? WHERE status='pending' AND json_extract(snapshot,'$.refinementId')=?",
            (error, now, session_id))

    def incubator_refinement_pause(self, body, prefix="/api/workflow", authorize=None):
        if authorize:
            authorize()
        if not isinstance(body, dict) or set(body) - {"requestId", "id"}:
            raise WorkflowError("暂停完善请求无效。")
        identifier = _id(body.get("id"))
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM idea_refinements WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise WorkflowError("完善会话不存在。", 404)
            old = self._receipt(db, "refinement_pause", body)
            if not old:
                if row["state"] == "completed":
                    raise WorkflowError("完善已完成，无需暂停。", 409)
                now = _now()
                db.execute("UPDATE idea_refinements SET state='paused',error='后续完善已暂停；已送达的聊天不会被终止。',updated_at=? WHERE id=?", (now, identifier))
                self._cancel_refinement_pending(db, identifier, now, "用户暂停，未发送的完善轮次已取消。")
                latest = db.execute("SELECT snapshot FROM idea_dispatches WHERE idea_id=? ORDER BY rowid DESC LIMIT 1", (row["idea_id"],)).fetchone()
                latest_snapshot = json.loads(latest["snapshot"]) if latest else {}
                if latest_snapshot.get("refinementId") == identifier:
                    db.execute("UPDATE ideas SET stage='thinking',revision=revision+1,updated_at=? WHERE id=? AND stage='queued' AND revision=?",
                        (now, row["idea_id"], latest_snapshot["revision"] + 1))
                self._receipt(db, "refinement_pause", body, {"refinementId": identifier})
                self._revision(db, True)
            if authorize:
                authorize()
            return {"refinement": self._public_refinement(db.execute("SELECT * FROM idea_refinements WHERE id=?", (identifier,)).fetchone()),
                    "revision": self._revision(db), "duplicate": old is not None}

    def _complete_refinement(self, db, row, result, thread_id, now):
        snapshot = json.loads(row["snapshot"])
        session = db.execute("SELECT * FROM idea_refinements WHERE id=?", (snapshot["refinementId"],)).fetchone()
        if session is None:
            return "needs_review", "完善授权记录缺失；未改写正文。"
        if session["state"] == "paused":
            return "completed", ""
        idea = self._idea(db, row["idea_id"])
        error = ""
        if session["state"] != "active" or idea["revision"] != snapshot["revision"] + 1 or idea["stage"] != "queued":
            error = "正文或完善状态已变更；保留用户草稿，请手动核对返回稿。"
        text = result.get("text", "")
        blocks = re.findall(r"<refined_prompt>(.*?)</refined_prompt>", text, re.DOTALL)
        if len(blocks) != 1 or text.count("<refined_prompt>") != 1 or text.count("</refined_prompt>") != 1 or not blocks[0].strip():
            error = error or "返回内容没有唯一完整的 refined_prompt 稿块；原稿未改变。"
        elif len(blocks[0].strip()) > MAX_TEXT or "\0" in blocks[0]:
            error = error or "返回稿无效或过长；原稿未改变。"
        if error:
            db.execute("UPDATE idea_refinements SET state='needs_review',error=?,updated_at=? WHERE id=?", (error, now, session["id"]))
            return "needs_review", error
        final = snapshot["round"] >= session["round_limit"]
        db.execute("UPDATE ideas SET body=?,stage=?,revision=revision+1,updated_at=? WHERE id=?",
            (blocks[0].strip(), "ready" if final else "queued", now, idea["id"]))
        db.execute("UPDATE idea_refinements SET target_thread_id=?,state=?,error='',updated_at=? WHERE id=?",
            (thread_id, "completed" if final else "active", now, session["id"]))
        if not final:
            next_round, next_id = snapshot["round"] + 1, uuid.uuid4().hex
            next_idea = self._public_idea(self._idea(db, idea["id"]))
            next_snapshot = {key: next_idea[key] for key in ("title", "body", "stage", "priority", "revision")}
            next_snapshot.update(purpose="refine", refinementId=session["id"], round=next_round, roundLimit=session["round_limit"])
            nonce = str(uuid.uuid5(uuid.NAMESPACE_URL, f"console-refinement:{session['id']}:{next_round}"))
            db.execute("INSERT INTO idea_dispatches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (next_id, idea["id"], nonce, _json(next_snapshot), self._dispatch_prompt(next_id, next_idea, next_snapshot),
                 session["target_kind"], "existing", thread_id, session["target_name"], next_idea["priority"], "pending", "{}", "", None, now, now, session["user_confirmed_at"]))
            db.execute("UPDATE ideas SET revision=revision+1 WHERE id=?", (idea["id"],))
            db.execute("UPDATE idea_refinements SET round=? WHERE id=?", (next_round, session["id"]))
        return "completed", ""

    def incubator_targets(self, query=""):
        if query:
            raise WorkflowError("发布目标请求地址无效。")
        with self._db() as db:
            db.execute("BEGIN")
            return {"targets": self._setting(db, "incubator_targets") or [],
                    "updatedAt": self._setting(db, "incubator_targets_updated_at"), "revision": self._revision(db)}

    def incubator_set_targets(self, body, authorize=None):
        if authorize:
            authorize()
        if not isinstance(body, dict) or set(body) - {"requestId", "targets", "updatedAt"} or not isinstance(body.get("targets"), list) or len(body["targets"]) > 256:
            raise WorkflowError("发布目标快照无效。")
        clean, seen = [], set()
        for target in body["targets"]:
            if not isinstance(target, dict) or set(target) - {"id", "kind", "title", "name", "hostId", "status"}:
                raise WorkflowError("发布目标内容无效。")
            kind = target.get("kind")
            if not isinstance(kind, str) or kind not in {"codex", "chatgpt"}:
                raise WorkflowError("发布目标类型无效。")
            identifier = self._thread_id(target.get("id"))
            if (kind, identifier) in seen:
                raise WorkflowError("发布目标重复。")
            title = _text(target.get("title", target.get("name", "")), 160)
            if not title.strip():
                raise WorkflowError("发布目标标题不可为空。")
            item = {"id": identifier, "kind": kind, "title": title, "name": title}
            if "hostId" in target:
                item["hostId"] = _text(target["hostId"], 120)
            if "status" in target:
                status = target["status"]
                if isinstance(status, dict) and not set(status) - {"type", "activeFlags"}:
                    flags = status.get("activeFlags", [])
                    if not isinstance(flags, list) or len(flags) > 16:
                        raise WorkflowError("目标聊天状态无效。")
                    item["status"] = {"type": _text(status.get("type", ""), 40), "activeFlags": [_text(flag, 40) for flag in flags]}
                elif isinstance(status, str):
                    item["status"] = _text(status, 40)
                else:
                    raise WorkflowError("目标聊天状态无效。")
            clean.append(item)
            seen.add((kind, identifier))
        updated = body.get("updatedAt", _now())
        try:
            datetime.fromisoformat(_text(updated, 64).replace("Z", "+00:00"))
        except ValueError:
            raise WorkflowError("发布目标快照时间无效。") from None
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if not self._receipt(db, "incubator_targets", body):
                self._set_setting(db, "incubator_targets", clean)
                self._set_setting(db, "incubator_targets_updated_at", updated)
                self._receipt(db, "incubator_targets", body, {"saved": True})
                self._revision(db, True)
            if authorize:
                authorize()
        return self.incubator_targets()

    def incubator_dispatches(self, *, waiting=False, private=False):
        with self._db() as db:
            db.execute("BEGIN")
            rows = db.execute("SELECT * FROM idea_dispatches " + ("WHERE status IN ('claimed','waiting','needs_review') " if waiting else "")
                + "ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,created_at,id").fetchall()
            return {"dispatches": [self._public_dispatch(row, private) for row in rows], "revision": self._revision(db)}

    def incubator_claim(self, body):
        if not isinstance(body, dict) or set(body) - {"requestId", "id"}:
            raise WorkflowError("发布认领请求无效。")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._receipt(db, "incubator_claim", body)
            if old:
                dispatch_id = old["dispatchId"]
                if dispatch_id is None:
                    return {"dispatch": None, "revision": self._revision(db), "duplicate": True, "shouldDispatch": False}
            else:
                if db.execute("SELECT 1 FROM idea_dispatches WHERE status IN ('claimed','waiting','needs_review') LIMIT 1").fetchone():
                    raise WorkflowError("已有发布正在等待结果或需要核查，请先处理该记录。", 409, "dispatch_busy")
                if "id" in body:
                    row = self._dispatch(db, body["id"])
                    if row["status"] != "pending":
                        raise WorkflowError("这次发布已认领或已结束，不能重复发送。", 409, "dispatch_not_pending")
                else:
                    row = db.execute("SELECT * FROM idea_dispatches WHERE status='pending' ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,created_at,id LIMIT 1").fetchone()
                    if row is None:
                        self._receipt(db, "incubator_claim", body, {"dispatchId": None})
                        return {"dispatch": None, "revision": self._revision(db), "duplicate": False, "shouldDispatch": False}
                dispatch_id = row["id"]
                db.execute("UPDATE idea_dispatches SET status='claimed',claim_token=?,updated_at=? WHERE id=?",
                    (uuid.uuid4().hex, _now(), dispatch_id))
                self._receipt(db, "incubator_claim", body, {"dispatchId": dispatch_id})
                self._revision(db, True)
            return {"dispatch": self._public_dispatch(self._dispatch(db, dispatch_id), True),
                    "revision": self._revision(db), "duplicate": old is not None, "shouldDispatch": old is None}

    def incubator_attach_result(self, body):
        return self._incubator_dispatch_result(body, fail=False)

    def incubator_fail(self, body):
        return self._incubator_dispatch_result(body, fail=True)

    def _incubator_dispatch_result(self, body, fail):
        allowed = {"requestId", "id", "claimToken", "status", "error"} if fail else {"requestId", "id", "claimToken", "status", "targetThreadId", "result", "verified"}
        if not isinstance(body, dict) or set(body) - allowed:
            raise WorkflowError("发布结果内容无效。")
        dispatch_id = _id(body.get("id"))
        token = _id(body.get("claimToken"))
        status = body.get("status", "failed" if fail else "waiting")
        if not isinstance(status, str) or status not in ({"failed", "needs_review"} if fail else {"waiting", "completed"}):
            raise WorkflowError("发布结果状态无效。")
        result, error = {}, ""
        if fail:
            error = _text(body.get("error", "发布未完成，请在目标聊天核对。"), 2000)
        else:
            result = body.get("result", {})
            if not isinstance(result, dict) or set(result) - {"text", "sourceMessageId", "turnId"}:
                raise WorkflowError("发布成果内容无效。")
            result = {key: _text(value, MAX_TEXT if key == "text" else 160) for key, value in result.items()}
            if status == "completed" and not result.get("text", "").strip():
                raise WorkflowError("请保存实际返回的结果，再标记发布完成。")
        kind = "incubator_fail" if fail else "incubator_result"
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._dispatch(db, dispatch_id)
            if token != row["claim_token"]:
                raise WorkflowError("发布认领标识不匹配。", 403)
            old = self._receipt(db, kind, body)
            if not old:
                if row["status"] not in {"claimed", "waiting", "needs_review"}:
                    raise WorkflowError("这次发布已结束，不能覆盖已有结果。", 409)
                if not fail and row["status"] == "needs_review" and body.get("verified") is not True:
                    raise WorkflowError("发送结果不明，必须先核对已有目标聊天，不能自动重发。", 409, "verification_required")
                thread_id = row["target_thread_id"]
                previous_result = json.loads(row["result"])
                if fail:
                    result = previous_result
                if not fail:
                    for marker in ("turnId", "sourceMessageId"):
                        if previous_result.get(marker) and marker in result and previous_result[marker] != result[marker]:
                            raise WorkflowError("返回结果不属于这次发布对应的消息或执行轮次。", 409, "result_not_matching")
                    result = {**previous_result, **result}
                    if status == "completed" and not result.get("turnId", "").strip():
                        raise WorkflowError("请核对这次发布对应的实际执行轮次，再保存完成结果。")
                    confirmed_id = self._thread_id(body.get("targetThreadId", thread_id))
                    if thread_id and thread_id != confirmed_id:
                        raise WorkflowError("发布结果不属于已选目标聊天。", 409)
                    thread_id = confirmed_id
                now = _now()
                refinement_id = json.loads(row["snapshot"]).get("refinementId")
                if refinement_id:
                    if not fail and status == "completed":
                        status, error = self._complete_refinement(db, row, result, thread_id, now)
                    elif fail:
                        db.execute("UPDATE idea_refinements SET state=?,error=?,updated_at=? WHERE id=?",
                            ("needs_review" if status == "needs_review" else "paused", error, now, refinement_id))
                        if status == "failed":
                            snapshot = json.loads(row["snapshot"])
                            db.execute("UPDATE ideas SET stage='thinking',revision=revision+1,updated_at=? WHERE id=? AND revision=? AND stage='queued'",
                                (now, row["idea_id"], snapshot["revision"] + 1))
                db.execute("UPDATE idea_dispatches SET status=?,target_thread_id=?,result=?,error=?,updated_at=? WHERE id=?",
                    (status, thread_id, _json(result), error, now, dispatch_id))
                idea = self._idea(db, row["idea_id"])
                snapshot = json.loads(row["snapshot"])
                # Later edits remain drafts; completing an older snapshot cannot publish them.
                if not refinement_id and idea["revision"] == snapshot["revision"] + 1 and idea["stage"] == "queued":
                    stage = "published" if status == "completed" else snapshot["stage"] if status == "failed" else None
                    if stage is not None:
                        db.execute("UPDATE ideas SET stage=?,target_thread_id=?,revision=revision+1,updated_at=? WHERE id=?",
                            (stage, thread_id or "", now, idea["id"]))
                self._receipt(db, kind, body, {"dispatchId": dispatch_id})
                self._revision(db, True)
            response = {"dispatch": self._public_dispatch(self._dispatch(db, dispatch_id), True),
                        "idea": self._public_idea(self._idea(db, row["idea_id"])), "revision": self._revision(db), "duplicate": old is not None}
            refinement_id = response["dispatch"]["refinementId"]
            if refinement_id:
                response["refinement"] = self._public_refinement(db.execute("SELECT * FROM idea_refinements WHERE id=?", (refinement_id,)).fetchone())
            return response

    def _receipt(self, db, kind, body, response=None):
        try:
            request_id = str(uuid.UUID(body.get("requestId", "")))
        except (ValueError, TypeError, AttributeError):
            raise WorkflowError("请求标识无效。")
        fingerprint = hashlib.sha256(_json(body).encode("utf-8")).hexdigest()
        row = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        if row:
            if row["kind"] != kind or row["fingerprint"] != fingerprint:
                raise WorkflowError("该请求标识已用于其他内容。", 409)
            return json.loads(row["response"])
        if response is not None:
            db.execute("INSERT INTO requests VALUES (?,?,?,?)", (request_id, kind, fingerprint, _json(response)))
        return None

    def _message(self, db, record_id, role, text, attachment_ids=None, options=None):
        identifier = uuid.uuid4().hex
        db.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?)", (identifier, record_id, role, _text(text), _now(), _json(attachment_ids or []), _json(options or [])))
        db.execute("UPDATE records SET updated_at=? WHERE id=?", (_now(), record_id))
        return identifier

    def _context(self, db, record_id, value):
        if value is None:
            value = {}
        if not isinstance(value, dict) or set(value) - {"sourceMessageId", "selectedText", "optionId", "attachmentIds", "referenceIds"}:
            raise WorkflowError("所选上下文无效。")
        clean = dict(value)
        clean["selectedText"] = _text(value.get("selectedText", ""))
        ids = value.get("attachmentIds", [])
        refs = value.get("referenceIds", [])
        if not isinstance(ids, list) or len(ids) > MAX_ATTACHMENTS or not isinstance(refs, list) or len(refs) > 8:
            raise WorkflowError("所选上下文过多。")
        for identifier in ids:
            if db.execute("SELECT 1 FROM attachments WHERE id=? AND record_id=?", (_id(identifier), record_id)).fetchone() is None:
                raise WorkflowError("所选图片不属于当前记录。", 403)
        clean["referenceIds"] = [_key(identifier) for identifier in refs]
        source = value.get("sourceMessageId")
        if source:
            row = db.execute("SELECT * FROM messages WHERE id=? AND record_id=?", (_id(source), record_id)).fetchone()
            if row is None:
                raise WorkflowError("所选消息不属于当前记录。", 403)
            if value.get("optionId") and not any(item["id"] == value["optionId"] for item in json.loads(row["options"])):
                raise WorkflowError("所选 AI 方案不存在。")
        elif value.get("optionId"):
            raise WorkflowError("请选择 AI 方案所属消息。")
        return clean

    def create(self, body, prefix="/api/workflow", authorize=None):
        if authorize:
            authorize()
        if not isinstance(body, dict) or set(body) - {"requestId", "projectId", "title", "text", "context"}:
            raise WorkflowError("新记录内容无效。")
        with self._db() as db:
            old = self._receipt(db, "create", body)
            if old:
                identifier = old["recordId"]
            else:
                project = self._project(db, _key(body.get("projectId")))
                identifier, now = uuid.uuid4().hex, _now()
                text = _text(body.get("text", ""))
                context = self._context(db, identifier, body.get("context"))
                db.execute("INSERT INTO records VALUES (?,?,?,?,?,?,?)", (identifier, _text(body.get("title", text[:60] or "新评价与任务"), 160), project["id"], now, now, None, _json(context)))
                if text:
                    self._message(db, identifier, "user", text)
                self._receipt(db, "create", body, {"recordId": identifier})
                self._revision(db, True)
            if authorize:
                authorize()
        return self.detail(identifier, prefix)

    def add_message(self, body, prefix="/api/workflow", authorize=None):
        if authorize:
            authorize()
        if not isinstance(body, dict) or set(body) - {"requestId", "recordId", "text"}:
            raise WorkflowError("消息内容无效。")
        with self._db() as db:
            identifier = self._record(db, body.get("recordId"))["id"]
            if not self._receipt(db, "message", body):
                text = _text(body.get("text", ""))
                if not text.strip():
                    raise WorkflowError("请输入消息内容。")
                self._message(db, identifier, "user", text)
                self._receipt(db, "message", body, {"recordId": identifier})
                self._revision(db, True)
            if authorize:
                authorize()
        return self.detail(identifier, prefix)

    def _enqueue(self, kind, body, authorize=None):
        if authorize:
            authorize()
        allowed = {"requestId", "recordId", "text", "computerId", "projectId", "action", "commandId", "context", "attachmentId", "args"}
        if not isinstance(body, dict) or set(body) - allowed:
            raise WorkflowError("任务内容无效。")
        with self._db() as db:
            record = self._record(db, body.get("recordId"))
            old = self._receipt(db, kind, body)
            if old:
                job_id = old["jobId"]
            else:
                computer = self._setting(db, "computer")
                if body.get("computerId") and body["computerId"] != computer["id"]:
                    raise WorkflowError("任务目标不是这台电脑。", 403)
                project = self._project(db, _key(body.get("projectId", record["project_id"])))
                payload = dict(body)
                payload["computerId"] = computer["id"]
                payload["projectId"] = project["id"]
                payload["text"] = _text(body.get("text", ""))
                payload["context"] = self._context(db, record["id"], body.get("context", json.loads(record["context"])))
                if kind == "execute":
                    action = body.get("action", "auto")
                    if not isinstance(action, str) or action not in ACTIONS:
                        raise WorkflowError("执行能力无效。")
                    payload["action"] = action
                    if action != "auto" and action not in project["capabilities"]:
                        raise WorkflowError("此项目未授权该能力。", 403)
                    if action == "generated_script" and not project["allowGeneratedScripts"]:
                        raise WorkflowError("此项目未授权生成脚本。", 403)
                    if action == "command" and not any(c["id"] == body.get("commandId") for c in project["commands"]):
                        raise WorkflowError("指定脚本未授权。", 403)
                    args = body.get("args", {})
                    if not isinstance(args, dict) or len(_json(args)) > 4096:
                        raise WorkflowError("任务参数无效。")
                if kind in {"execute", "discuss"} and not payload["text"].strip():
                    raise WorkflowError("请填写明确评价或任务要求。")
                if kind == "transcribe":
                    attachment = db.execute("SELECT * FROM attachments WHERE id=? AND record_id=?", (_id(body.get("attachmentId")), record["id"])).fetchone()
                    if attachment is None or not attachment["mime_type"].startswith("audio/"):
                        raise WorkflowError("请先上传当前记录的录音。")
                job_id, now = uuid.uuid4().hex, _now()
                db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (job_id, record["id"], kind, body["requestId"], _json(payload), "queued", 1, None, now, now, "", "", "{}"))
                if payload["text"]:
                    self._message(db, record["id"], "user", payload["text"])
                self._receipt(db, kind, body, {"jobId": job_id})
                self._revision(db, True)
            job = self._public_job(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
            result = {"job": job, "record": self._public_record(record), "revision": self._revision(db)}
            if authorize:
                authorize()
        self._wake.set()
        return result

    def discuss(self, body, prefix="/api/workflow", authorize=None):
        return self._enqueue("discuss", body, authorize)

    def submit(self, body, prefix="/api/workflow", authorize=None):
        return self._enqueue("execute", body, authorize)

    def transcribe(self, body, prefix="/api/workflow", authorize=None):
        return self._enqueue("transcribe", body, authorize)

    def retry(self, body, prefix="/api/workflow", authorize=None):
        if authorize:
            authorize()
        if not isinstance(body, dict) or set(body) != {"requestId", "jobId"}:
            raise WorkflowError("请明确选择重试任务。")
        with self._db() as db:
            old = self._receipt(db, "retry", body)
            if old:
                job_id = old["jobId"]
            else:
                parent = db.execute("SELECT * FROM jobs WHERE id=?", (_id(body["jobId"]),)).fetchone()
                if parent is None or parent["status"] not in {"failed", "waiting", "interrupted"}:
                    raise WorkflowError("仅失败、等待配置或中断的任务可以重试。", 409)
                job_id, now = uuid.uuid4().hex, _now()
                db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (job_id, parent["record_id"], parent["kind"], body["requestId"], parent["payload"], "queued", parent["attempt"] + 1, parent["id"], now, now, "", "", "{}"))
                self._receipt(db, "retry", body, {"jobId": job_id})
                self._revision(db, True)
            job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            result = {"job": self._public_job(job), "record": self._public_record(self._record(db, job["record_id"])), "revision": self._revision(db)}
            if authorize:
                authorize()
        self._wake.set()
        return result

    def _store_file(self, db, record_id, source, name, mime_type, duration=None):
        identifier = uuid.uuid4().hex
        suffix = Path(name).suffix.lower()
        temporary = _safe_child(self.attachments_dir, identifier + ".pending")
        preview = _safe_child(self.attachments_dir, identifier + ".preview.jpg")
        target = None
        try:
            if isinstance(source, IncomingFile) or hasattr(source, "copy_to"):
                digest = source.copy_to(temporary)
            else:
                with Path(source).open("rb") as incoming, temporary.open("xb") as output:
                    digest = hashlib.sha256()
                    size = 0
                    while True:
                        block = incoming.read(65536)
                        if not block:
                            break
                        size += len(block)
                        if size > MAX_FILE_BYTES:
                            raise WorkflowError("结果文件超过 12 MB。", 413)
                        output.write(block)
                        digest.update(block)
                digest = digest.hexdigest()
            size = temporary.stat().st_size
            if not 0 < size <= MAX_FILE_BYTES:
                raise WorkflowError("文件为空或超过限制。", 413)
            has_preview = False
            if suffix in IMAGE_TYPES:
                extension, detected, has_preview = _image(temporary, name, preview)
                allowed_types = {detected, "application/octet-stream"}
                if detected == "image/jpeg":
                    allowed_types.add("image/jpg")
                if detected == "image/heic":
                    allowed_types.add("image/heif")
                if mime_type not in allowed_types:
                    raise WorkflowError("图片类型与内容不符。", 415)
                mime_type, suffix = detected, extension
            elif suffix in AUDIO_TYPES:
                if mime_type not in {AUDIO_TYPES[suffix], "application/octet-stream", "audio/x-wav", "audio/x-m4a", "video/webm", "video/mp4"}:
                    raise WorkflowError("录音类型无效。", 415)
                mime_type = AUDIO_TYPES[suffix]
            else:
                raise WorkflowError("仅支持图片与录音。", 415)
            filename = identifier + suffix
            target = _safe_child(self.attachments_dir, filename)
            os.replace(temporary, target)
            db.execute("INSERT INTO attachments VALUES (?,?,?,?,?,?,?,?)", (identifier, record_id, _filename(name), filename, mime_type, size, int(has_preview), duration))
            return identifier, digest
        except BaseException:
            temporary.unlink(missing_ok=True)
            preview.unlink(missing_ok=True)
            if target is not None:
                target.unlink(missing_ok=True)
            raise

    def upload(self, fields, files, prefix="/api/workflow", authorize=None):
        if authorize:
            authorize()
        if not isinstance(fields, dict) or set(fields) - {"requestId", "recordId", "role", "duration"} or not 1 <= len(files) <= MAX_ATTACHMENTS:
            raise WorkflowError("文件上传内容无效。")
        if sum(item.size for item in files) > MAX_UPLOAD:
            raise WorkflowError("上传总大小不能超过 24 MB。", 413)
        role = fields.get("role", "result")
        if role not in {"user", "result"}:
            raise WorkflowError("附件消息类型无效。")
        duration = fields.get("duration")
        if duration not in (None, ""):
            try:
                duration = float(duration)
            except (ValueError, TypeError):
                raise WorkflowError("录音时长无效。")
            if not 0 < duration <= 180:
                raise WorkflowError("录音不能超过三分钟。", 413)
        else:
            duration = None
        created = []
        try:
            with self._db() as db:
                record = self._record(db, fields.get("recordId"))
                digests = []
                for file in files:
                    identifier, digest = self._store_file(db, record["id"], file, file.name, file.mime_type, duration)
                    created.append(identifier)
                    digests.append([file.name, digest])
                body = {**fields, "files": digests}
                old = self._receipt(db, "upload", body)
                if old:
                    for identifier in created:
                        row = db.execute("SELECT filename FROM attachments WHERE id=?", (identifier,)).fetchone()
                        _safe_child(self.attachments_dir, row["filename"]).unlink(missing_ok=True)
                        _safe_child(self.attachments_dir, identifier + ".preview.jpg").unlink(missing_ok=True)
                        db.execute("DELETE FROM attachments WHERE id=?", (identifier,))
                    created = []
                else:
                    self._message(db, record["id"], role, "已添加图片或录音。", created)
                    image = db.execute("SELECT id FROM attachments WHERE id IN (" + ",".join("?" for _ in created) + ") AND mime_type LIKE 'image/%' ORDER BY rowid DESC LIMIT 1", created).fetchone()
                    if image:
                        db.execute("UPDATE records SET primary_attachment_id=? WHERE id=?", (image["id"], record["id"]))
                    self._receipt(db, "upload", body, {"recordId": record["id"], "attachmentIds": created})
                    self._revision(db, True)
                if authorize:
                    authorize()
            result = self.detail(record["id"], prefix)
            result["uploadedAttachmentIds"] = old.get("attachmentIds", []) if old else created
            return result
        except BaseException:
            # Rollback paths are identified solely by UUIDs created in this call.
            for identifier in created:
                for suffix in (".jpg", ".png", ".gif", ".webp", ".heic", ".wav", ".mp3", ".m4a", ".mp4", ".webm", ".ogg", ".preview.jpg", ".pending"):
                    _safe_child(self.attachments_dir, identifier + suffix).unlink(missing_ok=True)
            raise

    def attachment(self, query):
        params = parse_qs(query, keep_blank_values=True)
        if set(params) - {"id", "preview", "download"} or any(len(value) != 1 for value in params.values()) or any(params.get(key, ["0"])[0] not in {"0", "1"} for key in ("preview", "download")):
            raise WorkflowError("附件请求无效。")
        with self._db() as db:
            row = db.execute("SELECT * FROM attachments WHERE id=?", (_id(params.get("id", [None])[0]),)).fetchone()
            if row is None:
                raise WorkflowError("附件不存在。", 404)
            preview = params.get("preview", ["0"])[0] == "1"
            if preview and not row["preview"]:
                raise WorkflowError("该附件没有预览图。", 415)
            path = _safe_child(self.attachments_dir, row["id"] + ".preview.jpg" if preview else row["filename"])
            if not path.is_file():
                raise WorkflowError("附件文件无法读取。", 404)
            return {"path": path, "mimeType": "image/jpeg" if preview else row["mime_type"], "name": row["name"], "download": params.get("download", ["0"])[0] == "1"}

    @contextmanager
    def read_attachment(self, query, authorize=None):
        with self._lock:
            if authorize:
                authorize()
            item = self.attachment(query)
            source = item["path"].open("rb")
        try:
            yield {**item, "source": source}
        finally:
            source.close()

    def status(self):
        with self._db() as db:
            counts = {row["status"]: row["count"] for row in db.execute("SELECT status,COUNT(*) AS count FROM jobs GROUP BY status")}
        return {"running": counts.get("running", 0), "queued": counts.get("queued", 0), "waiting": counts.get("waiting", 0), "workerAlive": bool(self._thread and self._thread.is_alive()), "backgroundEnabled": self.background_enabled}

    def has_pending_jobs(self):
        status = self.status()
        return bool(status["running"] or status["queued"])

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._worker, name="console-workflow-worker", daemon=True)
            self._thread.start()
            self._wake.set()

    def shutdown(self, wait=5):
        self._stop.set()
        self._wake.set()
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()  # Only the subprocess owned by this worker.
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=max(0, min(float(wait), 30)))
        with self._db() as db:
            db.execute("UPDATE jobs SET status='interrupted',error='电脑任务服务已停止；请明确重试。',updated_at=? WHERE status='running'", (_now(),))
            self._revision(db, True)

    def _worker(self):
        while not self._stop.is_set():
            with self._db() as db:
                row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
                if row:
                    db.execute("UPDATE jobs SET status='running',updated_at=? WHERE id=?", (_now(), row["id"]))
                    self._revision(db, True)
            if row is None:
                self._wake.wait(1)
                self._wake.clear()
                continue
            terminal_committed = False
            try:
                result, log, options = self._run(row)
                if self._stop.is_set():
                    raise WorkflowError("任务服务已停止。", 503, "interrupted")
                with self._db() as db:
                    current = db.execute("SELECT status FROM jobs WHERE id=?", (row["id"],)).fetchone()
                    if current["status"] != "running":
                        continue
                    role = "assistant" if row["kind"] == "discuss" else "transcript" if row["kind"] == "transcribe" else "result"
                    message = self._message(db, row["record_id"], role, result.get("text", ""), result.get("attachmentIds", []), options)
                    result["messageId"] = message
                    if result.get("primaryAttachmentId"):
                        db.execute("UPDATE records SET primary_attachment_id=? WHERE id=?", (result["primaryAttachmentId"], row["record_id"]))
                    db.execute("UPDATE jobs SET status='succeeded',result=?,log=?,updated_at=? WHERE id=?", (_json(result), log, _now(), row["id"]))
                    self._revision(db, True)
                terminal_committed = True
            except Exception as error:
                code = getattr(error, "code", "failed")
                status = "interrupted" if self._stop.is_set() or code == "interrupted" else "waiting" if code in {"missing_config", "resource_wait"} else "failed"
                message = str(error) if isinstance(error, (WorkflowError, TransferError)) or error.__class__.__name__ == "WorkflowModelError" else "任务未完成，请查看日志并明确重试。"
                with self._db() as db:
                    db.execute("UPDATE jobs SET status=?,error=?,updated_at=? WHERE id=? AND status='running'", (status, message[:1000], _now(), row["id"]))
                    self._revision(db, True)
                terminal_committed = True
            finally:
                if terminal_committed:
                    callback = self.callbacks.get("work_finished")
                    if callback is not None:
                        try:
                            callback()
                        except Exception:
                            pass  # Lifecycle callbacks cannot alter a committed result.

    def _model_input(self, row, payload, project, for_model=True):
        with self._db() as db:
            record = self._record(db, row["record_id"])
            context = payload.get("context", {})
            ids = context.get("attachmentIds") or ([record["primary_attachment_id"]] if record["primary_attachment_id"] else [])
            images = []
            for identifier in ids:
                attachment = db.execute("SELECT * FROM attachments WHERE id=? AND record_id=?", (identifier, record["id"])).fetchone()
                if attachment and attachment["mime_type"].startswith("image/"):
                    if for_model and attachment["mime_type"] not in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
                        raise WorkflowError("所选图片格式暂不支持 AI 阅读，请上传 PNG 或 JPEG。", 415)
                    use_preview = for_model and (attachment["mime_type"] == "image/gif" or attachment["size"] > 3 * 1024 * 1024)
                    filename = attachment["id"] + ".preview.jpg" if use_preview else attachment["filename"]
                    images.append({"path": _safe_child(self.attachments_dir, filename), "mimeType": "image/jpeg" if use_preview else attachment["mime_type"]})
            selected = []
            if row["kind"] == "discuss":
                recent = db.execute("SELECT * FROM messages WHERE record_id=? AND role IN ('user','assistant') ORDER BY rowid DESC LIMIT 12", (record["id"],)).fetchall()
                remaining = 40000
                for previous in recent:
                    if previous["role"] == "user" and previous["text"] == payload["text"] and not selected:
                        continue
                    content = previous["text"][-min(remaining, 10000):]
                    if content:
                        selected.append({"role": previous["role"], "content": content})
                        remaining -= len(content)
                    if not remaining:
                        break
                selected.reverse()
            if context.get("sourceMessageId"):
                message = db.execute("SELECT * FROM messages WHERE id=? AND record_id=?", (context["sourceMessageId"], record["id"])).fetchone()
                if message:
                    option = next((item for item in json.loads(message["options"]) if item["id"] == context.get("optionId")), None)
                    content = context.get("selectedText") or (option["instruction"] if option else message["text"] if row["kind"] == "discuss" or message["role"] == "user" else "")
                    if content:
                        selected.append({"role": "assistant" if message["role"] == "assistant" else "user", "content": content})
            elif context.get("selectedText"):
                selected.append({"role": "user", "content": context["selectedText"]})
        resolver = self.callbacks.get("resolve_context")
        if context.get("referenceIds"):
            if resolver is None:
                raise WorkflowError("所选项目上下文读取能力尚未配置。", 503)
            for item in resolver(context["referenceIds"], project):
                selected.append({"role": "user", "content": _text(item.get("text", ""))})
        if sum(len(item["content"]) for item in selected) > 65000:
            raise WorkflowError("所选上下文过长，请缩小引用范围。")
        return {"text": payload["text"], "images": images, "context": selected,
                "project": {"id": project["id"], "name": project["name"], "capabilities": project["capabilities"], "commands": [{"id": item["id"], "name": item["name"]} for item in project["commands"]]}}

    def _require_model(self, transcription=False):
        if self.models is None:
            raise WorkflowError("请先在电脑配置并选择 AI 方案。", 503, "missing_config")
        config = self.models.config()
        ready = config.get("ready")
        if transcription:
            ready = any(item.get("id") == config.get("selected") and item.get("transcriptionReady") for item in config.get("providers", []))
        if not ready:
            raise WorkflowError("请先在电脑配置并选择可用 AI 或语音方案。", 503, "missing_config")

    def _run(self, row):
        payload = json.loads(row["payload"])
        with self._db() as db:
            project = self._project(db, payload["projectId"])
        if row["kind"] == "transcribe":
            self._require_model(True)
            with self._db() as db:
                item = db.execute("SELECT * FROM attachments WHERE id=? AND record_id=?", (payload["attachmentId"], row["record_id"])).fetchone()
                if item is None:
                    raise WorkflowError("录音不存在。", 404)
            result = self.models.transcribe(_safe_child(self.attachments_dir, item["filename"]), name=item["name"], mime_type=item["mime_type"], duration=item["duration"])
            return {"text": _text(result.get("text", "")), "attachmentIds": []}, "", []
        action = payload.get("action", "auto")
        needs_model = row["kind"] == "discuss" or action in {"auto", "generated_script"}
        if needs_model:
            self._require_model()
        model_input = self._model_input(row, payload, project, for_model=needs_model)
        if row["kind"] == "discuss":
            result = self.models.discuss(model_input)
            options = []
            for item in result.get("options", [])[:6]:
                if not isinstance(item, dict):
                    continue
                options.append({"id": _key(item.get("id", uuid.uuid4().hex)), "label": _text(item.get("label", item.get("title", "方案")), 160), "instruction": _text(item.get("instruction", ""))})
            return {"text": _text(result.get("text", "")), "attachmentIds": []}, "", options
        allowed = [item for item in project["capabilities"] if item != "generated_script" or project["allowGeneratedScripts"]]
        plan = {"action": action, "args": payload.get("args", {}), "text": "", "script": "", "language": "none"}
        if action in {"auto", "generated_script"}:
            if not allowed:
                raise WorkflowError("此项目没有已授权执行能力。", 403)
            contract = ("\n电脑执行约束：cwd 已是获授权项目。只执行这一个已选任务。截图参数为空；command.args仅commandId。"
                        "result_import.args.paths为现有项目内相对图片路径。生成脚本须从环境变量CONSOLE_WORKFLOW_OUTPUT_DIR取输出目录，"
                        "从CONSOLE_WORKFLOW_INPUT_FILE读所选图片与上下文，勿读凭据或关闭其他应用。将图片写入该输出目录后，"
                        "必须向CONSOLE_WORKFLOW_RESULT_MANIFEST指定文件写JSON {text:真实结果说明,files:[输出目录内相对图片路径]}。"
                        "不可以无结果清单声称完成。指定脚本列表：" + _json(model_input["project"]["commands"]))
            plan = self.models.plan({**model_input, "text": model_input["text"] + contract, "allowedActions": allowed if action == "auto" else ["generated_script"]})
            action = plan.get("action")
        if action not in allowed:
            raise WorkflowError("AI 计划请求了未授权能力，未执行。", 403)
        if self._stop.is_set():
            raise WorkflowError("任务已中断。", 503, "interrupted")
        job_dir = _safe_child(self.jobs_dir, row["id"])
        job_dir.mkdir(exist_ok=True)
        output = _safe_child(job_dir, "output")
        output.mkdir(exist_ok=True)
        manifest = _safe_child(output, "result-manifest.json")
        input_file = _safe_child(job_dir, "input.json")
        input_file.write_text(_json({"text": payload["text"], "context": model_input["context"],
                                     "images": [{"path": str(item["path"]), "mimeType": item["mimeType"]} for item in model_input["images"]]}), encoding="utf-8")
        args, log = plan.get("args", {}), ""
        if not isinstance(args, dict):
            raise WorkflowError("执行参数无效。")
        if action == "capture_screen":
            if args:
                raise WorkflowError("截图不接受额外执行参数。")
            callback = self.callbacks.get("capture_screen")
            if callback is None:
                raise WorkflowError("电脑截图能力尚未配置。", 503)
            with self._db() as db:
                self._execution_project(db, project, action)
                captured = callback(output / "screen.png")
            path = Path(captured) if captured else output / "screen.png"
            try:
                paths = [self._contained(output, str(path.relative_to(output)))]
            except ValueError:
                raise WorkflowError("截图结果越过任务输出目录。", 403)
            result = {"text": "已截取电脑画面。", "files": [path.name for path in paths]}
        elif action == "result_import":
            if set(args) - {"paths"} or not isinstance(args.get("paths"), list) or not 1 <= len(args["paths"]) <= 4:
                raise WorkflowError("请提供已授权项目内的结果图片。")
            with self._db() as db:
                current = self._execution_project(db, project, action)
                paths = [self._contained(Path(current["root"]), name) for name in args["paths"]]
            result = {"text": "已导入项目结果。", "files": []}
        else:
            command_id, language = None, None
            before_execute = self.callbacks.get("before_execute")
            if before_execute is not None and before_execute(action, project) is False:
                raise WorkflowError("电脑资源不足，任务等待明确重试。", 503, "resource_wait")
            if action == "command":
                command_id = payload.get("commandId") or args.get("commandId")
                if set(args) - {"commandId"}:
                    raise WorkflowError("指定脚本不接受未经授权的命令参数。", 403)
                command = next((item for item in project["commands"] if item["id"] == command_id), None)
                if command is None:
                    raise WorkflowError("指定脚本未授权。", 403)
                argv, timeout = command["argv"], command["timeout"]
            elif action == "generated_script":
                if args:
                    raise WorkflowError("生成脚本不接受额外执行参数。")
                if not project["allowGeneratedScripts"]:
                    raise WorkflowError("此项目未授权生成脚本。", 403)
                language = plan.get("language")
                runner = project["scriptRunners"].get(language)
                if not runner:
                    raise WorkflowError("此脚本语言尚未配置运行程序。", 503)
                script = _text(plan.get("script", ""), 60000)
                if not script.strip():
                    raise WorkflowError("AI 没有返回可执行脚本。")
                path = _safe_child(job_dir, "task.py" if language == "python" else "task.ps1")
                path.write_text(script, encoding="utf-8")
                argv, timeout = [*runner, str(path)], project["timeout"]
            else:
                raise WorkflowError("执行能力无效。")
            replacements = {"{jobDir}": str(job_dir), "{outputDir}": str(output), "{resultManifest}": str(manifest), "{instruction}": payload["text"]}
            argv = [self._replace(arg, replacements) for arg in argv]
            log = self._execute(row, argv, project, job_dir, output, manifest, timeout, payload["text"],
                                action=action, command_id=command_id, language=language)
            if not manifest.is_file() or manifest.stat().st_size > 65536:
                raise WorkflowError("脚本没有生成有效结果清单；不能确认任务完成。")
            self._contained(output, "result-manifest.json")
            try:
                result = json.loads(manifest.read_text(encoding="utf-8"))
            except (ValueError, UnicodeError):
                raise WorkflowError("脚本结果清单无效。")
            if not isinstance(result, dict) or set(result) - {"text", "files"} or not isinstance(result.get("files", []), list) or len(result.get("files", [])) > 4:
                raise WorkflowError("脚本结果清单无效。")
            paths = [self._contained(output, name) for name in result.get("files", [])]
        result_text = _text(result.get("text", "任务已完成。"))
        if not result_text.strip() and not paths:
            raise WorkflowError("没有可验证的任务结果。")
        ids = []
        try:
            with self._db() as db:
                if action == "result_import":
                    current = self._execution_project(db, project, action)
                    paths = [self._contained(Path(current["root"]), name) for name in args["paths"]]
                for path in paths:
                    if path.suffix.lower() not in IMAGE_TYPES:
                        raise WorkflowError("结果仅接受图片；其他文件保留在本机任务目录。")
                    identifier, _ = self._store_file(db, row["record_id"], path, path.name, IMAGE_TYPES[path.suffix.lower()])
                    ids.append(identifier)
        except BaseException:
            for identifier in ids:
                for suffix in (".jpg", ".png", ".gif", ".webp", ".heic", ".preview.jpg"):
                    _safe_child(self.attachments_dir, identifier + suffix).unlink(missing_ok=True)
            raise
        return {"text": result_text, "attachmentIds": ids, "primaryAttachmentId": ids[-1] if ids else None}, log, []

    @staticmethod
    def _replace(value, replacements):
        for key, replacement in replacements.items():
            value = value.replace(key, replacement)
        return value

    @staticmethod
    def _contained(root, value):
        if not isinstance(value, str) or not value or Path(value).is_absolute() or "\0" in value:
            raise WorkflowError("结果文件必须位于授权输出目录。", 403)
        path = root / value
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            raise WorkflowError("结果文件越过授权目录。", 403)
        if path.is_symlink() or path.resolve() != path.absolute() or not path.is_file():
            raise WorkflowError("结果文件不存在或被重定向。", 403)
        return path

    def _execute(self, row, argv, project, job_dir, output, manifest, timeout, instruction, *, action, command_id=None, language=None):
        env = self.models.execution_environment(os.environ) if self.models is not None else os.environ.copy()
        env.update({"CONSOLE_WORKFLOW_JOB_DIR": str(job_dir), "CONSOLE_WORKFLOW_OUTPUT_DIR": str(output),
                    "CONSOLE_WORKFLOW_RESULT_MANIFEST": str(manifest), "CONSOLE_WORKFLOW_INSTRUCTION": instruction,
                    "CONSOLE_WORKFLOW_INPUT_FILE": str(job_dir / "input.json")})
        # Public script contract; keep the initial internal prefix compatible.
        for name in ("JOB_DIR", "OUTPUT_DIR", "RESULT_MANIFEST", "INSTRUCTION", "INPUT_FILE"):
            env["CODEX_WORKFLOW_" + name] = env["CONSOLE_WORKFLOW_" + name]
        log_file = _safe_child(job_dir, "execution.log")
        try:
            failure = None
            # Raw output is bounded in RAM and never persisted before redaction.
            captured, output_lock, truncated = bytearray(), threading.Lock(), False
            with self._db() as db:
                current = self._execution_project(db, project, action, command_id, language)
                process = subprocess.Popen(argv, cwd=current["root"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           stdin=subprocess.DEVNULL, shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self._process = process
            def drain():
                nonlocal truncated
                try:
                    while True:
                        block = process.stdout.read(65536)
                        if not block:
                            break
                        with output_lock:
                            if len(captured) + len(block) > MAX_LOG:
                                truncated = True
                            if len(captured) < MAX_LOG:
                                captured.extend(block[:MAX_LOG - len(captured)])
                except (OSError, ValueError):
                    pass
            reader = threading.Thread(target=drain, name="workflow-output-reader", daemon=True)
            reader.start()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
                failure = WorkflowError("脚本执行超时；没有自动重试。", 503)
            finally:
                self._process = None
                reader.join(timeout=2)
                if not reader.is_alive():
                    process.stdout.close()
            with output_lock:
                # A truncated last line could contain only a prefix of a secret.
                complete = captured.rsplit(b"\n", 1)[0] + b"\n" if truncated and b"\n" in captured else (b"" if truncated else captured)
                log = complete.decode("utf-8", errors="replace")
            if self.models is not None:
                log = self.models.redact_execution_log(log)
            log = log.replace(str(self.data_dir), "[workflow]").replace(project["root"], "[project]")
            log_file.write_text(log, encoding="utf-8")
            with self._db() as db:
                db.execute("UPDATE jobs SET log=? WHERE id=?", (log, row["id"]))
            if failure is not None:
                raise failure
            if process.returncode:
                raise WorkflowError("脚本执行失败（退出码 " + str(process.returncode) + "）；日志已保留。", 503)
            return log
        except OSError:
            raise WorkflowError("已授权脚本无法启动，请检查电脑上的运行程序。", 503)
