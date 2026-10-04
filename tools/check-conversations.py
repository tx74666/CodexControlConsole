"""Isolated conversation catalog, read queue, page cache and paired-phone checks.

Uses disposable existing workflow databases and simulated App Tools pages only.
Never reads the user's catalog or chats, invokes a model, or delivers a message.
"""
import http.client
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from document_library import DocumentLibraryService
import phone_companion as phone
from workflow_http import workflow_get, workflow_post
from workflow_service import WorkflowError, WorkflowService


def request(**fields):
    return {"requestId": str(uuid.uuid4()), **fields}


class ConversationChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="console-conversations-check-")
        self.root = Path(self.temp.name)
        self.data = self.root / "private"
        self.service = WorkflowService(self.data, recover_jobs=False)
        # A second service uses this already existing database, matching CLI writes.
        self.other = WorkflowService(self.data, recover_jobs=False)
        self.project = self.root / "project"
        self.project.mkdir()
        self.nested = self.project / "subfolder"
        self.nested.mkdir()
        self.thread_id = str(uuid.uuid4())
        self.other_thread_id = str(uuid.uuid4())
        self.observed_at = "2026-10-04T05:00:00+00:00"

    def tearDown(self):
        self.temp.cleanup()

    def error(self, action, status=400, code=None):
        with self.assertRaises(WorkflowError) as caught:
            action()
        self.assertEqual(caught.exception.status, status)
        if code is not None:
            self.assertEqual(caught.exception.code, code)
        return caught.exception

    def unrelated_data(self):
        with self.service._db() as db:
            return {table: [tuple(row) for row in db.execute("SELECT * FROM " + table + " ORDER BY id")]
                    for table in ("records", "messages", "jobs", "ideas", "idea_dispatches")}

    def catalog(self, threads=None, projects=None, **fields):
        return self.service.conversations_catalog(request(
            fetchedAt=self.observed_at,
            projects=projects if projects is not None else [{"id": "fixture-project", "label": " 原始项目名 ", "path": str(self.project)}],
            threads=threads if threads is not None else [
                {"id": self.thread_id, "title": " 原始 Codex 标题 中文 ", "kind": "codex", "hostId": "local",
                 "cwd": str(self.nested), "status": {"type": "active", "activeFlags": ["inProgress"]}, "unread": True},
                {"id": self.other_thread_id, "title": "原始 ChatGPT 标题", "kind": "chatgpt", "status": "idle"}],
            partial=fields.pop("partial", False), **fields))

    def fetch(self, thread_id=None, mode="refresh", **fields):
        return self.service.conversations_request(request(threadId=thread_id or self.thread_id, mode=mode, **fields))["fetchRequest"]

    @staticmethod
    def message(identifier="m-1", text="真实逐条用户内容", **fields):
        return {"id": identifier, "role": "user", "text": text, "truncated": False, **fields}

    def page(self, fetch, messages=None, **fields):
        payload = request(threadId=fetch["threadId"], generation=fetch["generation"], mode=fetch["mode"],
                          olderCursor=None, fetchedAt=datetime.now(timezone.utc).isoformat(), partial=False,
                          coverage={"description": "App Tools 原文，本页已获取"},
                          messages=messages if messages is not None else [self.message()])
        if fetch["mode"] == "older":
            payload["cursor"] = fetch["cursor"]
        payload.update(fields)
        self.service.conversations_thread_snapshot(payload)
        return self.service.conversations_thread(fetch["threadId"])

    def complete(self, fetch, **fields):
        return self.service.conversations_fetch_result(request(id=fetch["id"], status="completed", **fields))

    def test_catalog_preserves_titles_projects_recents_status_and_observation(self):
        self.catalog()
        result = self.service.conversations_list()
        self.assertEqual([item["id"] for item in result["threads"]], [self.thread_id, self.other_thread_id])
        self.assertEqual(result["threads"][0]["title"], " 原始 Codex 标题 中文 ")
        self.assertEqual(result["projects"][0]["label"], " 原始项目名 ")
        self.assertEqual(result["threads"][0]["projectId"], "fixture-project")
        self.assertEqual(result["threads"][0]["status"], {"type": "active", "activeFlags": ["inProgress"]})
        self.assertTrue(result["threads"][0]["unread"])
        self.assertEqual(result["fetchedAt"], self.observed_at)
        self.assertFalse(result["partial"])
        self.assertEqual(result["requests"], [])
        self.assertFalse(self.service.has_pending_jobs())

    def test_cwd_uses_longest_normalized_boundary_and_explicit_project_is_retained(self):
        first, sibling, explicit = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        self.catalog(projects=[{"id": "outer", "label": "Outer", "path": str(self.project)},
                               {"id": "nested", "label": "Nested", "path": str(self.nested)}], threads=[
            {"id": first, "title": "Nested path", "kind": "codex", "cwd": str(self.nested / "child").upper().replace("\\", "/")},
            {"id": sibling, "title": "Similar prefix", "kind": "codex", "cwd": str(self.project) + "-other"},
            {"id": explicit, "title": "Explicit metadata", "kind": "codex", "projectId": "upstream-project", "cwd": str(self.nested)}])
        rows = {item["id"]: item for item in self.service.conversations_list()["threads"]}
        self.assertEqual(rows[first]["projectId"], "nested")
        self.assertFalse(rows[sibling].get("projectId"))
        self.assertEqual(rows[explicit]["projectId"], "upstream-project")

    def test_old_catalog_cannot_replace_current_status_or_project_membership(self):
        self.catalog()
        before = self.service.conversations_list()
        self.service.conversations_catalog(request(fetchedAt="2026-10-03T05:00:00+00:00", projects=[], threads=[]))
        after = self.service.conversations_list()
        self.assertEqual((after["projects"], after["threads"], after["fetchedAt"]),
                         (before["projects"], before["threads"], before["fetchedAt"]))

    def test_catalog_is_idempotent_and_reusing_nonce_with_changed_payload_is_rejected(self):
        payload = request(fetchedAt=self.observed_at, projects=[], threads=[])
        self.service.conversations_catalog(payload)
        before = self.service.conversations_list()
        self.service.conversations_catalog(payload)
        self.assertEqual(self.service.conversations_list(), before)
        self.error(lambda: self.service.conversations_catalog({**payload, "partial": True}), 409)

    def test_click_read_queue_is_independent_of_chat_publication_and_workflow_jobs(self):
        self.service.configure_projects([{"id": "fixture", "root": str(self.project), "capabilities": ["capture_screen"]}])
        record = self.service.create(request(projectId="fixture", title="Legacy record", text="Keep legacy messages"))["record"]
        job = self.service.submit(request(recordId=record["id"], text="Legacy queued job", action="capture_screen"))["job"]
        saved = self.service.incubator_create(request(title="Unpublished local idea"))["idea"]
        before = self.unrelated_data()
        with patch.object(self.service, "_enqueue", side_effect=AssertionError("Read requests must not execute")):
            self.catalog()
            queued = self.fetch()
            self.page(queued)
        self.assertEqual(self.unrelated_data(), before)
        self.assertEqual(self.service.detail(record["id"])["jobs"][0]["id"], job["id"])
        self.assertEqual(self.service.incubator_list()["ideas"][0]["id"], saved["id"])
        self.assertEqual(self.service.incubator_dispatches()["dispatches"], [])

    def test_click_nonce_retry_and_pending_merge_do_not_duplicate_fetches(self):
        self.catalog()
        payload = request(threadId=self.thread_id, mode="refresh")
        first = self.service.conversations_request(payload)
        duplicate = self.other.conversations_request(payload)
        merged = self.fetch()
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(first["fetchRequest"]["id"], duplicate["fetchRequest"]["id"])
        self.assertEqual(merged["id"], first["fetchRequest"]["id"])
        self.assertEqual(len(self.service.conversations_fetch_requests()["requests"]), 1)
        self.error(lambda: self.service.conversations_request({**payload, "threadId": self.other_thread_id}), 409)
        self.error(lambda: self.service.conversations_request({**payload, "mode": "older"}), 409)

    def test_concurrent_clicks_merge_to_one_pending_read_request(self):
        self.catalog()
        barrier, outcomes = threading.Barrier(2), []
        def click(service):
            barrier.wait(timeout=3)
            try:
                outcomes.append(service.conversations_request(request(threadId=self.thread_id, mode="refresh")))
            except Exception as error:
                outcomes.append(error)
        readers = [threading.Thread(target=click, args=(service,)) for service in (self.service, self.other)]
        for reader in readers:
            reader.start()
        for reader in readers:
            reader.join(5)
            self.assertFalse(reader.is_alive())
        self.assertEqual(len(outcomes), 2)
        self.assertTrue(all(isinstance(item, dict) for item in outcomes), outcomes)
        self.assertEqual(len({item["fetchRequest"]["id"] for item in outcomes}), 1)
        self.assertEqual(len(self.service.conversations_fetch_requests()["requests"]), 1)

    def test_each_message_and_summary_truncation_metadata_survive_roundtrip(self):
        self.catalog()
        queued = self.fetch()
        text = "  保留原文与换行\n第二行 <script>只是文字</script>  "
        messages = [self.message("u-1", text, turnId="turn-1", sourceMessageId="source-1", createdAt=self.observed_at),
                    self.message("a-1", "实际抓到的回合摘要", role="assistant", phase="final", status="completed", truncated=True)]
        detail = self.page(queued, messages, partial=True, coverage={"description": "回合摘要；单项因字符上限截断", "oldestAt": self.observed_at, "newestAt": self.observed_at})
        self.assertEqual(detail["messages"], messages)
        self.assertTrue(detail["partial"])
        self.assertTrue(detail["messages"][1]["truncated"])
        self.assertEqual(detail["coverage"]["messageCount"], 2)
        self.assertEqual(detail["coverage"]["pageCount"], 1)
        self.assertIn("摘要", detail["coverage"]["description"])
        self.assertGreaterEqual(datetime.fromisoformat(detail["fetchedAt"]), datetime.fromisoformat(queued["createdAt"]))

    def test_older_pages_deduplicate_keep_order_and_advance_actual_cursor(self):
        self.catalog()
        first = self.fetch()
        head = [self.message("m-2", "中间消息"), self.message("m-3", "最新消息", role="assistant")]
        self.page(first, head, olderCursor="opaque-page-two")
        self.complete(first)
        older = self.fetch(mode="older")
        detail = self.page(older, [self.message("m-1", "最早消息"), head[0]], olderCursor=None)
        self.assertEqual([item["id"] for item in detail["messages"]], ["m-1", "m-2", "m-3"])
        self.assertEqual(detail["coverage"]["messageCount"], 3)
        self.assertEqual(detail["coverage"]["pageCount"], 2)
        self.assertIsNone(detail["olderCursor"])
        self.assertFalse(detail["hasMore"])
        self.complete(older)
        self.error(lambda: self.fetch(mode="older"), 409)

    def test_snapshot_idempotency_and_repeated_cursor_do_not_inflate_pages(self):
        self.catalog()
        first = self.fetch()
        payload = request(threadId=self.thread_id, generation=first["generation"], mode="refresh", olderCursor="page-2",
                          fetchedAt=self.observed_at, partial=False, messages=[self.message("head")])
        self.service.conversations_thread_snapshot(payload)
        before = self.service.conversations_thread(self.thread_id)
        self.other.conversations_thread_snapshot(payload)
        after = self.service.conversations_thread(self.thread_id)
        self.assertEqual((after["messages"], after["coverage"]), (before["messages"], before["coverage"]))
        self.error(lambda: self.service.conversations_thread_snapshot({**payload, "messages": [self.message("changed")]}), 409)

    def test_cross_thread_cursor_is_rejected_without_altering_either_cache(self):
        self.catalog()
        first, second = self.fetch(), self.fetch(self.other_thread_id)
        self.page(first, [self.message("a")], olderCursor="cursor-for-a")
        self.page(second, [self.message("b")], olderCursor="cursor-for-b")
        before = self.service.conversations_thread(self.other_thread_id)
        self.error(lambda: self.service.conversations_thread_snapshot(request(threadId=self.other_thread_id,
            generation=second["generation"], mode="older", cursor="cursor-for-a", olderCursor=None,
            fetchedAt=self.observed_at, partial=False, messages=[self.message("intruder")])), 409)
        after = self.service.conversations_thread(self.other_thread_id)
        self.assertEqual((after["messages"], after["coverage"], after["olderCursor"]),
                         (before["messages"], before["coverage"], before["olderCursor"]))

    def test_refresh_generation_supersedes_older_request_and_ignores_late_pages(self):
        self.catalog()
        original = self.fetch()
        self.page(original, [self.message("old-head")], olderCursor="old-tail")
        self.complete(original)
        stale_older = self.fetch(mode="older")
        fresh = self.fetch()
        self.assertGreater(fresh["generation"], stale_older["generation"])
        self.page(fresh, [self.message("fresh-head")], olderCursor="fresh-tail")
        before = self.service.conversations_thread(self.thread_id)
        self.page(stale_older, [self.message("late-old-data")], olderCursor=None)
        after = self.service.conversations_thread(self.thread_id)
        self.assertEqual((after["messages"], after["coverage"], after["olderCursor"], after["snapshotGeneration"]),
                         (before["messages"], before["coverage"], before["olderCursor"], before["snapshotGeneration"]))
        self.assertFalse(any(item["id"] == stale_older["id"] for item in self.service.conversations_fetch_requests()["requests"]))

    def test_failed_refresh_keeps_existing_cache_and_cannot_claim_false_completion(self):
        self.catalog()
        original = self.fetch()
        self.error(lambda: self.complete(original), 409)
        self.page(original, [self.message("keep-cached-message")])
        self.complete(original)
        fresh = self.fetch()
        self.error(lambda: self.complete(fresh), 409)
        self.service.conversations_fetch_result(request(id=fresh["id"], status="failed", error="实际 App Tools 读取失败"))
        detail = self.service.conversations_thread(self.thread_id)
        self.assertEqual([item["id"] for item in detail["messages"]], ["keep-cached-message"])
        self.assertEqual(detail["snapshotGeneration"], original["generation"])
        failed = next(item for item in detail["requests"] if item["id"] == fresh["id"])
        self.assertEqual((failed["status"], failed["error"]), ("failed", "实际 App Tools 读取失败"))

    def test_unknown_threads_bad_shapes_roles_and_query_fields_are_rejected(self):
        self.catalog()
        unknown = self.service.conversations_thread(str(uuid.uuid4()))
        self.assertNotIn("title", unknown["thread"])
        self.assertEqual(unknown["messages"], [])
        self.assertEqual(unknown["coverage"]["pageCount"], 0)
        self.error(lambda: self.fetch(str(uuid.uuid4())), 404)
        self.error(lambda: self.fetch(mode="all"))
        self.error(lambda: self.service.conversations_request(request(threadId=self.thread_id, mode="refresh", execute=True)))
        self.error(lambda: self.service.conversations_list("password=bad"))
        queued = self.fetch()
        for fields in ({"generation": 0}, {"generation": True}, {"partial": "true"}, {"messages": [{"id": "bad", "role": "tool", "text": "not a user/assistant message"}]}, {"messages": [self.message("bad", truncated="true")]}):
            self.error(lambda values=fields: self.page(queued, **values))
        self.assertEqual(self.service.conversations_thread(self.thread_id)["messages"], [])

    def test_revoked_authorization_rolls_back_click_and_receipt(self):
        self.catalog()
        calls = []
        def revoked():
            calls.append(True)
            if len(calls) == 2:
                raise WorkflowError("Pairing revoked", 401)
        payload = request(threadId=self.thread_id, mode="refresh")
        self.error(lambda: self.service.conversations_request(payload, authorize=revoked), 401)
        self.assertEqual(self.service.conversations_fetch_requests()["requests"], [])
        accepted = self.service.conversations_request(payload)
        self.assertFalse(accepted["duplicate"])

    def test_shared_routes_expose_only_read_request_not_private_snapshot_writes(self):
        self.catalog()
        self.assertEqual(workflow_get(self.service, "conversations", "")["threads"][0]["id"], self.thread_id)
        self.assertEqual(workflow_get(self.service, "conversations/thread", "id=" + self.thread_id)["thread"]["id"], self.thread_id)
        result = workflow_post(self.service, "conversations/request", request(threadId=self.thread_id, mode="refresh"), prefix="/api/phone/workflow")
        self.assertEqual(result["fetchRequest"]["threadId"], self.thread_id)
        for action in ("conversations/catalog", "conversations/thread-snapshot", "conversations/fetch-result"):
            for desktop in (False, True):
                self.error(lambda name=action, local=desktop: workflow_post(self.service, name, request(), desktop=local), 404)
        self.error(lambda: workflow_get(self.service, "conversations/thread", "id=" + self.thread_id + "&cursor=untrusted"))

    def test_cli_existing_database_reads_pending_without_recovering_live_jobs(self):
        self.service.configure_projects([{"id": "fixture", "root": str(self.project), "capabilities": ["capture_screen"]}])
        record = self.service.create(request(projectId="fixture", title="Running workflow"))["record"]
        job = self.service.submit(request(recordId=record["id"], text="Existing live job", action="capture_screen"))["job"]
        with self.service._db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job["id"],))
        self.catalog()
        queued = self.fetch()
        cli = Path(__file__).with_name("incubator-dispatch.py")
        completed = subprocess.run([sys.executable, "-B", str(cli), "--data-dir", str(self.data), "read-fetch-requests"],
                                   shell=False, capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["requests"][0]["id"], queued["id"])
        self.assertEqual(self.service.detail(record["id"])["jobs"][0]["status"], "running")

    def test_cli_accepts_large_snapshot_but_rejects_nonexistent_database(self):
        self.catalog()
        queued = self.fetch()
        payload = request(threadId=self.thread_id, generation=queued["generation"], mode="refresh", olderCursor=None,
                          fetchedAt=self.observed_at, partial=True, coverage={"description": "五条真实原文，仍受抓取范围限制"},
                          messages=[self.message(f"long-{index}", "中" * 12000) for index in range(5)])
        fixture = self.root / "large-page.json"
        fixture.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.assertGreater(fixture.stat().st_size, 128 * 1024)
        cli = Path(__file__).with_name("incubator-dispatch.py")
        completed = subprocess.run([sys.executable, "-B", str(cli), "--data-dir", str(self.data), "thread-snapshot", "--json-file", str(fixture)],
                                   shell=False, capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(self.service.conversations_thread(self.thread_id)["coverage"]["messageCount"], 5)
        rejected = subprocess.run([sys.executable, "-B", str(cli), "--data-dir", str(self.root / "missing"), "read-fetch-requests"],
                                  shell=False, capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertFalse((self.root / "missing").exists())

    def test_older_summary_partial_flags_are_visible_in_combined_cache(self):
        self.catalog()
        first = self.fetch()
        self.page(first, [self.message("latest", "最近一条原文")], olderCursor="summary-page",
                  coverage={"description": "最近一页为消息原文"})
        self.complete(first)
        older = self.fetch(mode="older")
        detail = self.page(older, [self.message("summary", "实际抓到的较早回合摘要", role="assistant", truncated=True)],
                           partial=True, coverage={"description": "更早一页为回合摘要，字符上限截断"})
        self.assertTrue(detail["partial"])
        self.assertIn("摘要", detail["coverage"]["description"])
        self.assertEqual(detail["coverage"]["pageCount"], 2)
        self.assertEqual(detail["coverage"]["messageCount"], 2)

    def test_older_cursor_loops_and_thirty_page_limit_are_explicit_not_silently_complete(self):
        self.catalog()
        first = self.fetch()
        self.page(first, [self.message("page-1")], olderCursor="page-2")
        self.complete(first)
        for number in range(2, 31):
            older = self.fetch(mode="older")
            detail = self.page(older, [self.message(f"page-{number}")], olderCursor=f"page-{number + 1}")
            self.complete(older)
        self.assertEqual(detail["coverage"]["pageCount"], 30)
        self.assertTrue(detail["hasMore"])
        blocked = self.fetch(mode="older")
        self.error(lambda: self.page(blocked, [self.message("page-31")], olderCursor="page-32"), 409, "cache_page_limit")
        self.assertEqual(self.service.conversations_thread(self.thread_id)["coverage"]["pageCount"], 30)
        self.assertEqual(self.service.conversations_thread(self.thread_id)["olderCursor"], "page-31")
        self.error(lambda: self.page(blocked, [self.message("loop")], olderCursor="page-2"), 409, "cursor_mismatch")

    def test_same_generation_stale_source_page_does_not_replace_newer_observation(self):
        self.catalog()
        queued = self.fetch()
        self.page(queued, [self.message("new-observation")], olderCursor="newer-cursor")
        before = self.service.conversations_thread(self.thread_id)
        stale_time = (datetime.fromisoformat(before["fetchedAt"]) - timedelta(days=1)).isoformat()
        self.page(queued, [self.message("older-observation")], fetchedAt=stale_time, olderCursor=None)
        after = self.service.conversations_thread(self.thread_id)
        self.assertEqual((after["messages"], after["fetchedAt"], after["olderCursor"]),
                         (before["messages"], before["fetchedAt"], before["olderCursor"]))

    def test_catalog_and_pages_reject_naive_times_duplicate_ids_and_invented_percentages(self):
        self.catalog()
        before = self.service.conversations_list()
        for payload in (request(fetchedAt="2026-10-04T05:00:00", projects=[], threads=[]),
                        request(fetchedAt=self.observed_at, projects=[], threads=[
                            {"id": self.thread_id, "title": "Duplicate 1", "kind": "codex"},
                            {"id": self.thread_id, "title": "Duplicate 2", "kind": "codex"}])):
            self.error(lambda body=payload: self.service.conversations_catalog(body))
        self.assertEqual(self.service.conversations_list(), before)
        queued = self.fetch()
        self.error(lambda: self.page(queued, [self.message("duplicate"), self.message("duplicate")]))
        self.error(lambda: self.page(queued, coverage={"description": "No source percentage", "percent": 100}))
        self.error(lambda: self.page(queued, [self.message(f"over-limit-{number}") for number in range(257)]))
        self.assertEqual(self.service.conversations_thread(self.thread_id)["coverage"]["pageCount"], 0)

    def test_malformed_enum_containers_return_validation_errors_not_type_errors(self):
        self.catalog()
        queued = self.fetch()
        for value in ([], {}, True, 1, None):
            self.error(lambda item=value: self.service.conversations_catalog(request(fetchedAt=self.observed_at,
                projects=[], threads=[{"id": self.thread_id, "title": "Invalid kind", "kind": item}])))
            self.error(lambda item=value: self.service.conversations_request(request(threadId=self.thread_id, mode=item)))
            self.error(lambda item=value: self.page(queued, mode=item))
            self.error(lambda item=value: self.page(queued, [self.message("invalid-role", role=item)]))
            self.error(lambda item=value: self.service.conversations_fetch_result(request(id=queued["id"], status=item)))
        self.assertEqual(self.service.conversations_thread(self.thread_id)["coverage"]["pageCount"], 0)


class ConversationPhoneChecks(unittest.TestCase):
    # Reuse disposable fixture helpers, without repeating the pure-service cases.
    setUp = ConversationChecks.setUp
    tearDown = ConversationChecks.tearDown
    catalog = ConversationChecks.catalog
    page = ConversationChecks.page
    message = staticmethod(ConversationChecks.message)

    def test_paired_http_read_click_origin_gate_private_writes_and_revocation(self):
        self.catalog()
        documents = DocumentLibraryService(self.root / "document-settings.json")
        library = self.root / "library"
        library.mkdir()
        documents.select(str(library))
        assets = self.root / "assets"
        assets.mkdir()
        companion = phone.PhoneCompanionService(documents, lambda: {"plan": {"groups": []}}, assets, "fixture",
            interface_getter=lambda: [{"address": "127.0.0.1", "name": "Disposable loopback"}], workflow_service=self.service)
        with socket.socket() as holder:
            holder.bind(("127.0.0.1", 0))
            port = holder.getsockname()[1]
        origin, cookie = f"http://127.0.0.1:{port}", ""
        def phone_request(path, method="GET", body=None, extra=None):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            headers = {"Origin": origin, "Cookie": cookie, "X-Codex-Phone": "1", "Content-Type": "application/json"}
            headers.update(extra or {})
            try:
                connection.request(method, path, json.dumps(body).encode("utf-8") if body is not None else None, headers)
                result = connection.getresponse()
                return result.status, json.loads(result.read()), dict(result.getheaders())
            finally:
                connection.close()
        original = phone.is_lan_address
        with patch.object(phone, "is_lan_address", lambda address: address == "127.0.0.1" or original(address)):
            try:
                companion.start("127.0.0.1", port)
                path = "/api/phone/workflow/conversations"
                self.assertEqual(phone_request(path)[0], 401)
                status, _, headers = phone_request("/api/phone/pair", "POST", {"code": companion.state(False)["pairingCode"]})
                self.assertEqual(status, 200)
                cookie = headers["Set-Cookie"].split(";", 1)[0]
                status, listed, _ = phone_request(path)
                self.assertEqual(status, 200, listed)
                self.assertEqual(listed["threads"][0]["id"], self.thread_id)
                click = request(threadId=self.thread_id, mode="refresh")
                self.assertEqual(phone_request(path + "/request", "POST", click, {"X-Codex-Phone": ""})[0], 403)
                self.assertEqual(phone_request(path + "/request", "POST", click, {"Origin": "http://attacker.example"})[0], 403)
                self.assertEqual(phone_request(path + "/request", "POST", request(threadId=self.thread_id, mode=[]))[0], 400)
                status, accepted, _ = phone_request(path + "/request", "POST", click)
                self.assertEqual(status, 200, accepted)
                queued = accepted["fetchRequest"]
                self.assertEqual(len(self.service.conversations_fetch_requests()["requests"]), 1)
                self.page(queued, [self.message("phone-cache", "手机仅显示本次已抓到的消息")], partial=True)
                status, detail, _ = phone_request(path + "/thread?id=" + self.thread_id)
                self.assertEqual(status, 200, detail)
                self.assertEqual(detail["messages"][0]["id"], "phone-cache")
                self.assertTrue(detail["partial"])
                for action in ("catalog", "thread-snapshot", "fetch-result"):
                    self.assertEqual(phone_request(path + "/" + action, "POST", request())[0], 404)
                self.assertEqual(self.service.incubator_dispatches()["dispatches"], [])
                # Same disposable phone fixture exercises the refinement whitelist.
                saved = self.service.incubator_create(request(title="Phone refinement gate", body="只完善稿，不执行"))["idea"]
                publish_body = request(id=saved["id"], expectedRevision=saved["revision"], targetKind="codex",
                                       targetMode="new", purpose="refine", roundLimit=3)
                publish_path = "/api/phone/workflow/incubator/publish"
                self.assertEqual(phone_request(publish_path, "POST", publish_body, {"X-Codex-Phone": ""})[0], 403)
                status, refining, _ = phone_request(publish_path, "POST", publish_body)
                self.assertEqual(status, 200, refining)
                self.assertEqual(refining["refinement"]["roundLimit"], 3)
                pause_body = request(id=refining["refinement"]["id"])
                pause_path = "/api/phone/workflow/incubator/refinement/pause"
                self.assertEqual(phone_request(pause_path, "POST", pause_body, {"Origin": "http://attacker.example"})[0], 403)
                status, paused, _ = phone_request(pause_path, "POST", pause_body)
                self.assertEqual(status, 200, paused)
                self.assertEqual(paused["refinement"]["state"], "paused")
                self.assertEqual(self.service.incubator_dispatches()["dispatches"][0]["status"], "failed")
                self.assertFalse(self.service.has_pending_jobs())
                self.assertEqual(phone_request("/api/phone/logout", "POST", {})[0], 200)
                self.assertEqual(phone_request(path)[0], 401)
                self.assertEqual(phone_request(path + "/thread?id=" + self.thread_id)[0], 401)
                self.assertEqual(phone_request(path + "/request", "POST", request(threadId=self.other_thread_id, mode="refresh"))[0], 401)
            finally:
                companion.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
