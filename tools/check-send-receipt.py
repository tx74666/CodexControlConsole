#!/usr/bin/env python3
"""Accepted mobile sends are recovered by read-only receipts in disposable fixtures.

No real App, model, account, production data, install or user-message resend.
The three query identities prove the original persisted session and its record.
"""
from contextlib import ExitStack, closing, contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
import uuid


ROOT = mobile = workflow_get = workflow_post = WorkflowError = canonical_json = None
ENABLE_HTTP = False
RECEIPT_KEYS = {"requestId", "clientId", "sessionId", "recordId", "jobId",
    "sourceUserMessageId", "requestSha256", "textSha256", "attachmentIds", "acceptedAt"}


def load_fixture(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure(repo, with_http=False):
    global ROOT, mobile, workflow_get, workflow_post, WorkflowError, canonical_json, ENABLE_HTTP
    ROOT = Path(repo).resolve(strict=True)
    for relative in ("workflow_mobile_dialogue.py", "workflow_http.py", "tools/check-mobile-dialogue.py"):
        if not ROOT.joinpath(relative).is_file():
            raise ValueError("Explicit --repo must name the reviewed Console source checkout")
    sys.path.insert(0, str(ROOT))
    http = importlib.import_module("workflow_http")
    service = importlib.import_module("workflow_service")
    for module in (http, service):
        if not Path(module.__file__).resolve().is_relative_to(ROOT):
            raise ValueError("Run in a fresh Python process; another checkout is already imported")
    workflow_get, workflow_post = http.workflow_get, http.workflow_post
    WorkflowError, canonical_json = service.WorkflowError, service._json
    mobile = load_fixture(ROOT / "tools/check-mobile-dialogue.py", "receipt84_mobile_fixture")
    ENABLE_HTTP = bool(with_http)


class SendReceiptChecks(unittest.TestCase):
    def setUp(self):
        if mobile is None:
            raise RuntimeError("configure(explicit_repo) is required before running this private draft")
        self.fixture = mobile.MobileDialogueChecks(methodName="runTest")
        self.fixture.setUp()
        self.service, self.client = self.fixture.service, self.fixture.client

    def tearDown(self):
        self.fixture.tearDown()

    def send(self, state=None, **changes):
        session = (state or self.fixture.open())["session"]
        body = mobile.request(clientId=self.client, sessionId=session["id"], expectedRevision=session["revision"],
            text=" 原问题中文😀\r\n第二行\n  ", attachmentIds=[], requestedProfile=session["requestedProfile"])
        body.update(changes)
        sent = workflow_post(self.service, "mobile/dialogue/send", body)
        user = next(message for message in sent["detail"]["messages"] if message["role"] == "user"
            and message["createdAt"] == sent["job"]["createdAt"] and message["text"] == body["text"]
            and message["attachmentIds"] == body["attachmentIds"])
        return body, sent, user

    def query(self, body):
        return {key: body[key] for key in ("requestId", "clientId", "sessionId")}

    def get(self, body, **options):
        return workflow_get(self.service, "mobile/dialogue/send-receipt", urlencode(self.query(body)), **options)

    def expect_error(self, operation, status=None, code=None):
        with self.assertRaises(WorkflowError) as caught:
            operation()
        if status is not None:
            self.assertEqual(caught.exception.status, status)
        if code is not None:
            self.assertEqual(caught.exception.code, code)
        return caught.exception

    def snapshot(self):
        """Read all fixture tables including schema/sequence; never production."""
        database = self.service.data_dir / "workflow.sqlite3"
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            result = {name: db.execute('SELECT * FROM "' + name.replace('"', '""') + '" ORDER BY rowid').fetchall()
                for name in tables}
            result["__schema__"] = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
            return result

    @contextmanager
    def guarded_read(self):
        before = self.snapshot()
        database = self.service.data_dir / "workflow.sqlite3"
        before_bytes = database.read_bytes()
        traces = []
        original_read = self.service._guide_read
        original_proof = self.service._guide_original_send
        def checked_read(operation, authorize):
            def inspect(db):
                self.assertEqual(db.execute("PRAGMA query_only").fetchone()[0], 1)
                db.set_trace_callback(traces.append)
                return operation(db)
            return original_read(inspect, authorize)
        def checked_proof(db, user, session):
            self.assertTrue(db.in_transaction, "All proof SELECTs must share an explicit read transaction")
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("UPDATE settings SET value=value WHERE 0")
            return original_proof(db, user, session)
        with ExitStack() as stack:
            for name in ("_db", "_guide_user_source", "_guide_bind_user_message", "_receipt", "_mobile_save_session", "_revision"):
                stack.enter_context(patch.object(self.service, name,
                    side_effect=AssertionError("Receipt GET may not call a writing helper: " + name)))
            stack.enter_context(patch.object(self.service, "_guide_read", side_effect=checked_read))
            stack.enter_context(patch.object(self.service, "_guide_original_send", side_effect=checked_proof))
            yield traces
        self.assertEqual(database.read_bytes(), before_bytes)
        self.assertEqual(self.snapshot(), before)

    def assert_receipt(self, found, body, sent, user, is_current=True):
        self.assertEqual(set(found), {"sendReceipt", "isCurrent"})
        receipt = found["sendReceipt"]
        self.assertEqual(set(receipt), RECEIPT_KEYS)
        for key in ("requestId", "clientId", "sessionId"):
            self.assertEqual(receipt[key], body[key])
        self.assertEqual(receipt["recordId"], sent["session"]["recordId"])
        self.assertEqual(receipt["jobId"], sent["job"]["id"])
        self.assertEqual(receipt["sourceUserMessageId"], user["id"])
        self.assertEqual(receipt["requestSha256"], hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest())
        self.assertEqual(receipt["textSha256"], hashlib.sha256(body["text"].encode("utf-8")).hexdigest())
        self.assertEqual(receipt["attachmentIds"], body["attachmentIds"])
        self.assertEqual(receipt["acceptedAt"], user["createdAt"])
        self.assertIs(found["isCurrent"], is_current)

    def make_legacy(self, body, user):
        with self.service._db() as db:
            entry = db.execute("SELECT response FROM requests WHERE id=?", (body["requestId"],)).fetchone()
            saved = json.loads(entry[0])
            self.assertEqual(set(saved), {"sessionId", "jobId", "sourceMessageId"})
            saved.pop("sourceMessageId")
            db.execute("UPDATE requests SET response=? WHERE id=?", (canonical_json(saved), body["requestId"]))
            db.execute("DELETE FROM mobile_message_sources WHERE message_id=?", (user["id"],))

    def delete_fixture_images(self, sent, image_id):
        with self.service._db() as db:
            attachment = db.execute("SELECT filename FROM attachments WHERE id=?", (image_id,)).fetchone()
            payload = json.loads(db.execute("SELECT payload FROM jobs WHERE id=?", (sent["job"]["id"],)).fetchone()[0])
            paths = [self.service.attachments_dir / attachment["filename"]]
            paths += [Path(image["path"]) for image in payload["appFrozen"]["images"]]
            db.execute("DELETE FROM attachments WHERE id=?", (image_id,))
        for path in set(paths):
            self.assertTrue(path.resolve().is_relative_to(self.fixture.root.resolve()), "Only disposable fixture files may be removed")
            if path.is_file():
                path.unlink()

    def test_modern_three_key_receipt_phone_desktop_exact_fields_and_read_transaction(self):
        body, sent, user = self.send()
        with self.guarded_read() as traces:
            for prefix, desktop in (("/api/workflow", True), ("/api/phone/workflow", False)):
                self.assert_receipt(self.get(body, prefix=prefix, desktop=desktop), body, sent, user)
        begin = next(i for i, sql in enumerate(traces) if sql.strip().upper() == "BEGIN")
        request_select = next(i for i, sql in enumerate(traces) if "SELECT * FROM requests WHERE id=" in sql)
        self.assertLess(begin, request_select)

    def test_nested_subscription_original_request_fingerprint_and_no_model_claim(self):
        adapter = self.service.subscription = mobile.CachedSubscription()
        body, sent, user = self.send(chatTransport="chatgpt_subscription", subscription=adapter.choice())
        adapter.connected = False
        with self.guarded_read():
            self.assert_receipt(self.get(body), body, sent, user)
        self.assertEqual(len(adapter.calls), 1, "Read must not validate current subscription selection")

    def deleted_image_case(self, legacy):
        state = self.fixture.open()
        image_id = self.fixture.image(state)
        body, sent, user = self.send(state, attachmentIds=[image_id])
        if legacy:
            self.make_legacy(body, user)
        self.delete_fixture_images(sent, image_id)
        with self.guarded_read():
            self.assert_receipt(self.get(body), body, sent, user)

    def test_81_two_key_receipt_survives_deleted_attachment_row_and_files_without_backfill(self):
        self.deleted_image_case(legacy=True)

    def test_83_three_key_receipt_survives_deleted_attachment_row_and_files(self):
        self.deleted_image_case(legacy=False)

    def test_legacy_same_time_text_different_attachments_filters_before_uniqueness(self):
        state = self.fixture.open()
        image_id = self.fixture.image(state)
        body, sent, user = self.send(state, attachmentIds=[image_id])
        self.make_legacy(body, user)
        with self.service._db() as db:
            self.service._message(db, sent["session"]["recordId"], "user", body["text"],
                attachment_ids=[], created_at=user["createdAt"])
        with self.guarded_read():
            self.assert_receipt(self.get(body), body, sent, user)

    def test_truly_duplicate_user_source_is_409_not_unknown(self):
        body, sent, user = self.send()
        self.make_legacy(body, user)
        with self.service._db() as db:
            self.service._message(db, sent["session"]["recordId"], "user", body["text"],
                attachment_ids=body["attachmentIds"], created_at=user["createdAt"])
        with self.guarded_read():
            error = self.expect_error(lambda: self.get(body), 409)
            self.assertNotEqual(error.code, "send_receipt_not_found")

    def test_unknown_request_only_is_dedicated_404_and_wrong_kind_is_409(self):
        body, sent, user = self.send()
        unknown = {**body, "requestId": str(uuid.uuid4())}
        with self.guarded_read():
            self.expect_error(lambda: self.get(unknown), 404, "send_receipt_not_found")
        with self.service._db() as db:
            db.execute("UPDATE requests SET kind='mobile_dialogue_draft' WHERE id=?", (body["requestId"],))
        with self.guarded_read():
            self.expect_error(lambda: self.get(body), 409, "send_source_not_matching")

    def test_exact_three_field_query_rejects_extra_missing_duplicate_blank_and_noncanonical(self):
        body, sent, user = self.send(requestId="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        fields = self.query(body)
        invalid = [urlencode({**fields, "recordId": sent["session"]["recordId"]}),
            urlencode({key: value for key, value in fields.items() if key != "sessionId"}),
            urlencode(fields) + "&requestId=" + body["requestId"],
            urlencode({**fields, "sessionId": ""}),
            urlencode({**fields, "requestId": body["requestId"].upper()}),
            urlencode({**fields, "requestId": "{" + body["requestId"] + "}"}),
            urlencode({**fields, "clientId": "{" + self.client + "}"}),
            urlencode({**fields, "sessionId": "{" + body["sessionId"] + "}"})]
        with self.guarded_read():
            for query in invalid:
                error = self.expect_error(lambda: workflow_get(self.service, "mobile/dialogue/send-receipt", query))
                self.assertIn(error.status, (400, 404))
                self.assertNotEqual(error.code, "send_receipt_not_found")

    def test_get_route_prefix_and_post_method_do_not_broaden_authority(self):
        body, sent, user = self.send()
        with self.guarded_read():
            for prefix in ("/api/workflow/", "/api/phone/workflow/", "/api/other/workflow"):
                self.expect_error(lambda: self.get(body, prefix=prefix), 403)
            self.expect_error(lambda: workflow_post(self.service, "mobile/dialogue/send-receipt", body), 404)

    def test_authorization_before_and_after_read_no_result_on_revocation(self):
        body, sent, user = self.send()
        successful = []
        with self.guarded_read():
            self.assert_receipt(self.get(body, authorize=lambda: successful.append(True)), body, sent, user)
        self.assertEqual(len(successful), 2)
        for revoke_at in (1, 2):
            calls = []
            def authorize():
                calls.append(True)
                if len(calls) == revoke_at:
                    raise WorkflowError("fixture authorization revoked", 403)
            with self.guarded_read():
                self.expect_error(lambda: self.get(body, authorize=authorize), 403)
            self.assertEqual(len(calls), revoke_at)

    def test_noncurrent_original_session_returns_receipt_without_restoring_old_scope(self):
        body, sent, user = self.send()
        current = self.fixture.mutate("clear", sent)
        self.assertNotEqual(current["session"]["id"], body["sessionId"])
        with self.guarded_read():
            self.assert_receipt(self.get(body), body, sent, user, is_current=False)
        self.assertEqual(self.fixture.current()["session"]["id"], current["session"]["id"])

    def test_wrong_client_or_different_session_does_not_return_acceptance(self):
        body, sent, user = self.send()
        current = self.fixture.mutate("clear", sent)
        with self.guarded_read():
            self.expect_error(lambda: self.get({**body, "clientId": str(uuid.uuid4())}), 403)
            self.expect_error(lambda: self.get({**body, "sessionId": current["session"]["id"]}), 409, "send_source_not_matching")

    def test_frozen_prompt_tampering_fails_closed(self):
        body, sent, user = self.send()
        with self.service._db() as db:
            db.execute("UPDATE idea_dispatches SET prompt=prompt || ? WHERE id=?", ("\nfixture tamper", sent["job"]["appDispatch"]["id"]))
        with self.guarded_read():
            error = self.expect_error(lambda: self.get(body), 409)
            self.assertNotEqual(error.code, "send_receipt_not_found")


class SendReceiptPairedHttpChecks(unittest.TestCase):
    def test_existing_paired_phone_get_checks_cookie_origin_fetch_site_and_no_mutation(self):
        if not ENABLE_HTTP:
            self.skipTest("Private draft: explicit --with-http required for disposable loopback fixture")
        http = load_fixture(ROOT / "tools/check-mobile-dialogue-http.py", "receipt84_phone_http_fixture")
        fixture = http.MobileDialogueHttpChecks(methodName="runTest")
        fixture.setUp()
        try:
            fixture.pair()
            session = fixture.open()
            body = mobile.request(clientId=str(uuid.UUID(fixture.client_id)), sessionId=session["id"],
                expectedRevision=session["revision"], text="isolated phone original send", attachmentIds=[], requestedProfile="high")
            status, sent, _ = fixture.call(http.PREFIX + "mobile/dialogue/send", body)
            self.assertEqual(status, 200, sent)
            path = http.PREFIX + "mobile/dialogue/send-receipt?" + urlencode({key: body[key]
                for key in ("requestId", "clientId", "sessionId")})
            before = fixture.counts()
            self.assertEqual(fixture.get(path, cookie="")[0], 401)
            for headers in ({"Origin": "https://other.invalid"}, {"Sec-Fetch-Site": "cross-site"}):
                status, error, response_headers = fixture.get(path, headers=headers)
                self.assertEqual(status, 403, error)
                self.assertNotIn("Access-Control-Allow-Origin", response_headers)
            status, found, _ = fixture.get(path)
            self.assertEqual(status, 200, found)
            self.assertEqual(found["sendReceipt"]["recordId"], session["recordId"])
            self.assertEqual(found["sendReceipt"]["jobId"], sent["job"]["id"])
            self.assertEqual(fixture.counts(), before)
        finally:
            fixture.tearDown()


if __name__ == "__main__":
    configure(Path(__file__).resolve().parents[1], with_http=True)
    unittest.main(verbosity=2)
