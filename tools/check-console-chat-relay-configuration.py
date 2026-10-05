"""Disposable configuration tests; synthetic contracts are not live CUA proof.

Only temporary SQLite stores and JSON files are used. No Chrome/Edge, native host,
production store, registry, model, broker or service is opened or started.
"""
from __future__ import annotations

from contextlib import closing, redirect_stderr, redirect_stdout
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "isolated_console_chat_relay_configuration", ROOT / "tools/configure-console-chat-relay.py")
configuration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configuration)


class ConfigurationChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="console-relay-configuration-isolated-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.directory = self.root / "CodexControlConsole" / "workflow-private"
        self.directory.mkdir(parents=True)
        self.database = self.directory / "workflow.sqlite3"
        self.approved = self.directory / configuration.APPROVAL_FILENAME
        self.environment = {"LOCALAPPDATA": str(self.root)}
        self.current = datetime.now(timezone.utc)
        self.confirmed_at = self.current.isoformat()
        with closing(sqlite3.connect(self.database)) as db:
            db.executescript("""
                CREATE TABLE settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE jobs (id TEXT PRIMARY KEY,status TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE TABLE idea_dispatches (id TEXT PRIMARY KEY,status TEXT NOT NULL,prompt TEXT NOT NULL);
                CREATE TABLE records (id TEXT PRIMARY KEY,body TEXT NOT NULL);
                INSERT INTO settings VALUES ('revision','77');
                INSERT INTO settings VALUES ('computer','{"id":"fixture-computer"}');
                INSERT INTO jobs VALUES ('old-pending-job','waiting','{"frozen":"原内容"}');
                INSERT INTO idea_dispatches VALUES ('old-pending','pending','旧问题，不能发送');
                INSERT INTO records VALUES ('saved-draft','未发送草稿');
            """)
            db.execute("INSERT INTO settings VALUES (?,?)", (
                configuration.ATTEMPT_PREFIX + "old-completed", json.dumps({"phase": "completed", "evidence": "fixture-tombstone"})))
            db.commit()
        # Deliberately synthetic and confined to these disposable tests. The
        # production CLI explicitly warns against calling such JSON live proof.
        self.contract = {
            "version": 1, "verified": True, "surface": "chrome", "source": "cua",
            "capturedAt": self.confirmed_at,
            "observationSha256": hashlib.sha256(b"synthetic fixture, not browser evidence").hexdigest(),
            "selectors": {key: "#synthetic-fixture-" + key for key in (
                "composer", "profile", "messages", "userText", "assistantText",
                "completion", "send", "stop", "login", "chatMode")},
            "profiles": {"fast": {"label": "Instant"}},
        }

    def configure(self, contract=None, **kwargs):
        options = {"user_authorized": True, "approval_confirmed_at": self.confirmed_at,
                   "environ": self.environment, "directory": self.directory,
                   "current_time": self.current}
        options.update(kwargs)
        return configuration.configure_configuration(self.contract if contract is None else contract, **options)

    def inspect(self):
        return configuration.inspect_configuration(environ=self.environment, directory=self.directory)

    def raw_setting(self):
        with closing(sqlite3.connect(self.database)) as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (configuration.APPROVAL_KEY,)).fetchone()
        return row[0] if row else None

    def snapshot(self, path=None, *, exclude_approval=False):
        with closing(sqlite3.connect(path or self.database)) as db:
            names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            result = {name: list(db.execute('SELECT * FROM "' + name.replace('"', '""') + '" ORDER BY rowid')) for name in names}
        if exclude_approval:
            result["settings"] = [row for row in result["settings"] if row[0] != configuration.APPROVAL_KEY]
        return result

    def filenames(self):
        return sorted(path.relative_to(self.directory).as_posix() for path in self.directory.rglob("*") if path.is_file())

    def sql(self, sql, args=()):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute(sql, args)
            db.commit()

    def assert_refused_unchanged(self, code, operation):
        before = self.snapshot()
        file_before = self.approved.read_bytes() if self.approved.exists() else None
        names_before = self.filenames()
        with self.assertRaises(configuration.ConfigurationError) as raised:
            operation()
        self.assertEqual(str(raised.exception), code)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.approved.read_bytes() if self.approved.exists() else None, file_before)
        self.assertEqual(self.filenames(), names_before)

    def assert_restored(self, before):
        self.assertEqual(self.snapshot(), before)
        self.assertIsNone(self.raw_setting())
        self.assertFalse(self.approved.exists())
        operations = list((self.directory / configuration.BACKUP_DIRECTORY).glob("*/operation.json"))
        self.assertEqual(len(operations), 1)
        self.assertEqual(json.loads(operations[0].read_text())["phase"], "restored_after_failure")

    def test_inspect_does_not_create_missing_store(self):
        other_root = self.root / "missing-local-app-data"
        before = sorted(self.root.rglob("*"))
        result = configuration.inspect_configuration(environ={"LOCALAPPDATA": str(other_root)})
        self.assertEqual(result["code"], "existing_workflow_store_required")
        self.assertFalse(result["configured"])
        self.assertEqual(sorted(self.root.rglob("*")), before)

    def test_inspect_is_readonly_and_reports_unconfigured(self):
        before, names = self.snapshot(), self.filenames()
        result = self.inspect()
        self.assertEqual(result["state"], "unconfigured")
        self.assertFalse(any(result["operations"].values()))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.filenames(), names)

    def test_configures_exact_pair_with_independent_backup_and_no_other_changes(self):
        before = self.snapshot()
        result = self.configure()
        config = configuration.fixed_approval(environ=self.environment, directory=self.directory)
        self.assertEqual(config["domContract"], self.contract)
        self.assertEqual(config["hostName"], configuration.HOST_NAME)
        self.assertEqual(config["extensionId"], configuration.EXTENSION_ID)
        self.assertEqual(config["dataDir"], str(self.directory))
        self.assertEqual(json.loads(self.raw_setting()), json.loads(self.approved.read_bytes()))
        self.assertEqual(self.snapshot(exclude_approval=True), before)
        self.assertTrue(result["changed"])
        self.assertTrue(result["operations"]["configurationWritten"])
        self.assertFalse(any(value for key, value in result["operations"].items() if key != "configurationWritten"))
        backup = Path(result["backupDir"])
        self.assertEqual(self.snapshot(backup / "original-workflow.sqlite3"), before)
        self.assertEqual(json.loads((backup / "original-approval-setting.json").read_bytes()), {"present": False, "rawValue": None})
        self.assertFalse((backup / "original-approved.json").exists())
        self.assertEqual(json.loads((backup / "operation.json").read_bytes())["phase"], "configured")
        public = json.dumps(result) + json.dumps(self.inspect())
        self.assertNotIn(config["authKeyHex"], public)
        self.assertNotIn(config["pipeName"], public)
        self.assertNotIn("authKeyHex", public)

    def test_identical_contract_is_idempotent_and_keeps_original_identity_and_time(self):
        first = self.configure()
        raw, contents, before, names = self.raw_setting(), self.approved.read_bytes(), self.snapshot(), self.filenames()
        result = self.configure(approval_confirmed_at=(self.current + timedelta(seconds=1)).isoformat(),
                                current_time=self.current + timedelta(seconds=1))
        self.assertFalse(result["changed"])
        self.assertNotIn("backupDir", result)
        self.assertEqual(result["approvalConfirmedAt"], first["approvalConfirmedAt"])
        self.assertEqual(self.raw_setting(), raw)
        self.assertEqual(self.approved.read_bytes(), contents)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.filenames(), names)

    def test_edge_configuration_preserves_surface_cua_source_and_safe_status(self):
        contract = copy.deepcopy(self.contract)
        contract["surface"] = "edge"
        result = self.configure(contract)
        config = configuration.fixed_approval(environ=self.environment, directory=self.directory)
        self.assertEqual(config["domContract"]["surface"], "edge")
        self.assertEqual(config["domContract"]["source"], "cua")
        self.assertEqual(result["contractDeclaredSurface"], "edge")
        self.assertTrue(result["runtimeContractEligible"])
        self.assertEqual(self.inspect()["contractDeclaredSurface"], "edge")
        self.assertFalse(self.configure(contract)["changed"])

    def test_changing_chrome_to_edge_contract_requires_separate_review(self):
        self.configure()
        contract = copy.deepcopy(self.contract)
        contract["surface"] = "edge"
        self.assert_refused_unchanged("existing_configuration_change_requires_review", lambda: self.configure(contract))

    def test_changed_valid_contract_requires_separate_review(self):
        self.configure()
        changed = copy.deepcopy(self.contract)
        changed["observationSha256"] = "b" * 64
        self.assert_refused_unchanged("existing_configuration_change_requires_review", lambda: self.configure(changed))

    def test_user_authorization_must_be_explicit_boolean(self):
        for value in (False, None, 1, "yes"):
            with self.subTest(value=value):
                self.assert_refused_unchanged("explicit_user_authorization_required", lambda: self.configure(user_authorized=value))

    def test_approval_time_cannot_be_future_or_timezone_naive(self):
        self.assert_refused_unchanged("user_approval_time_invalid_or_future", lambda: self.configure(
            approval_confirmed_at=(self.current + timedelta(seconds=1)).isoformat()))
        for value in ("not-a-time", self.current.replace(tzinfo=None).isoformat(), None):
            self.assert_refused_unchanged("reviewed_browser_cua_contract_invalid", lambda: self.configure(approval_confirmed_at=value))

    def test_original_user_consent_does_not_expire_or_get_retimestamped(self):
        original = (self.current - timedelta(days=3)).isoformat()
        result = self.configure(approval_confirmed_at=original)
        self.assertEqual(result["approvalConfirmedAt"], original)
        self.assertEqual(json.loads(self.raw_setting())["approvalConfirmedAt"], original)

    def test_new_configuration_requires_recent_dom_observation(self):
        contract = copy.deepcopy(self.contract)
        contract["capturedAt"] = (self.current - timedelta(seconds=configuration.MAX_CONTRACT_AGE_SECONDS + 1)).isoformat()
        self.assert_refused_unchanged("recent_browser_cua_observation_required", lambda: self.configure(contract))

    def test_idempotent_existing_contract_does_not_require_reobservation(self):
        self.configure()
        before = self.snapshot()
        result = self.configure(current_time=self.current + timedelta(days=1))
        self.assertFalse(result["changed"])
        self.assertEqual(self.snapshot(), before)

    def test_contract_capture_cannot_be_in_the_future(self):
        contract = copy.deepcopy(self.contract)
        contract["capturedAt"] = (self.current + timedelta(seconds=61)).isoformat()
        self.assert_refused_unchanged("contract_capture_time_invalid", lambda: self.configure(contract))

    def test_iab_unverified_and_relabelled_diagnostics_rejected(self):
        for key, value in (("surface", "iab"), ("surface", "firefox"), ("verified", False), ("source", "chrome_extension_dom"), ("version", True)):
            contract = copy.deepcopy(self.contract)
            contract[key] = value
            with self.subTest(key=key):
                self.assert_refused_unchanged("reviewed_browser_cua_contract_required", lambda: self.configure(contract))

    def test_incomplete_or_expanded_runtime_contract_rejected(self):
        changes = [lambda contract: contract["selectors"].pop("stop"),
                   lambda contract: contract["selectors"].update(send=None),
                   lambda contract: contract["profiles"].update(high={"label": "Thinking"}),
                   lambda contract: contract.update(extensionId="other-extension"),
                   lambda contract: contract.update(dataDir="other-store")]
        for change in changes:
            contract = copy.deepcopy(self.contract)
            change(contract)
            self.assert_refused_unchanged("reviewed_browser_cua_contract_invalid", lambda: self.configure(contract))

    def test_malformed_existing_pair_rejected_without_credential_disclosure(self):
        self.configure()
        secret = json.loads(self.raw_setting())["authKeyHex"]
        self.approved.write_text('{"private":"' + secret + '", "bad":}', encoding="utf-8")
        self.assert_refused_unchanged("configuration_json_invalid", self.configure)
        status = self.inspect()
        self.assertEqual(status["state"], "requires_review")
        self.assertNotIn(secret, json.dumps(status))

    def test_mismatched_file_and_setting_or_missing_active_file_rejected(self):
        self.configure()
        self.approved.unlink()
        self.assert_refused_unchanged("existing_approval_pair_mismatch", self.configure)
        config = json.loads(self.raw_setting())
        config["authKeyHex"] = "e" * 64
        self.approved.write_text(json.dumps(config), encoding="utf-8")
        self.assert_refused_unchanged("existing_approval_pair_mismatch", self.configure)

    def test_orphan_approval_file_rejected(self):
        self.approved.write_text('{"version":1,"enabled":false}', encoding="utf-8")
        self.assert_refused_unchanged("existing_approval_pair_mismatch", self.configure)

    def test_existing_disabled_setting_and_file_are_backed_up_exactly(self):
        raw = ' {"enabled": false, "version": 1} '
        contents = b'{"version":1,"enabled":false}\n'
        self.sql("INSERT INTO settings VALUES (?,?)", (configuration.APPROVAL_KEY, raw))
        self.approved.write_bytes(contents)
        result = self.configure()
        backup = Path(result["backupDir"])
        self.assertEqual(json.loads((backup / "original-approval-setting.json").read_bytes())["rawValue"], raw)
        self.assertEqual((backup / "original-approved.json").read_bytes(), contents)

    def test_disabled_setting_without_file_is_an_inactive_store(self):
        self.sql("INSERT INTO settings VALUES (?,?)", (configuration.APPROVAL_KEY, '{"version":1,"enabled":false}'))
        self.assertEqual(self.inspect()["state"], "unconfigured")
        self.assertTrue(self.configure()["changed"])

    def test_dispatch_inflight_and_review_states_rejected(self):
        for status in ("claimed", "waiting", "needs_review"):
            self.sql("UPDATE idea_dispatches SET status=?", (status,))
            self.assert_refused_unchanged("dispatch_inflight_or_review_required", self.configure)

    def test_queued_and_running_work_rejected(self):
        for status in ("queued", "running"):
            self.sql("UPDATE jobs SET status=?", (status,))
            self.assert_refused_unchanged("work_inflight", self.configure)

    def test_unfinished_relay_ledger_rejected_without_reset(self):
        self.sql("INSERT INTO settings VALUES (?,?)", (configuration.ATTEMPT_PREFIX + "unfinished", '{"phase":"send_intent"}'))
        self.assert_refused_unchanged("relay_attempt_inflight_or_review_required", self.configure)

    def test_settings_trigger_cannot_mutate_queue_as_side_effect(self):
        self.sql("CREATE TRIGGER bad_fixture_trigger AFTER INSERT ON settings BEGIN DELETE FROM idea_dispatches; END")
        self.assert_refused_unchanged("settings_triggers_require_review", self.configure)

    def test_alternate_private_directory_and_relative_environment_rejected(self):
        self.assert_refused_unchanged("fixed_store_identity_required", lambda: self.configure(directory=self.root / "other"))
        self.assert_refused_unchanged("local_app_data_must_be_absolute", lambda: self.configure(environ={"LOCALAPPDATA": "relative"}))

    def test_file_swap_failure_restores_only_approval_and_retains_backup(self):
        before = self.snapshot()
        original = configuration._atomic_replace
        def failed(path, data, *, expected):
            if path.name == configuration.APPROVAL_FILENAME:
                raise OSError("synthetic private authentication material must not escape")
            return original(path, data, expected=expected)
        with patch.object(configuration, "_atomic_replace", side_effect=failed):
            with self.assertRaisesRegex(configuration.ConfigurationError, "^configuration_failed_prior_values_restored$"):
                self.configure()
        self.assert_restored(before)

    def test_failure_after_file_swap_restores_original_disabled_bytes(self):
        previous_raw = ' {"version":1,"enabled":false} '
        previous_bytes = b' {"enabled":false,"version":1}\n'
        self.sql("INSERT INTO settings VALUES (?,?)", (configuration.APPROVAL_KEY, previous_raw))
        self.approved.write_bytes(previous_bytes)
        before = self.snapshot()
        original, fired = configuration._atomic_replace, False
        def failed_once(path, data, *, expected):
            nonlocal fired
            original(path, data, expected=expected)
            if path.name == configuration.APPROVAL_FILENAME and not fired:
                fired = True
                raise OSError("synthetic swap completed then failed")
        with patch.object(configuration, "_atomic_replace", side_effect=failed_once):
            with self.assertRaisesRegex(configuration.ConfigurationError, "^configuration_failed_prior_values_restored$"):
                self.configure()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.raw_setting(), previous_raw)
        self.assertEqual(self.approved.read_bytes(), previous_bytes)

    def test_commit_failure_before_or_after_actual_commit_restores_prior_values(self):
        for committed in (False, True):
            with self.subTest(committed=committed):
                # A new temporary fixture avoids reusing the previous backup.
                test = ConfigurationChecks("runTest")
                test.setUp()
                try:
                    before = test.snapshot()
                    def fail(db):
                        if committed:
                            db.commit()
                        raise sqlite3.OperationalError("synthetic failure contains private input")
                    with patch.object(configuration, "_commit", side_effect=fail):
                        with self.assertRaisesRegex(configuration.ConfigurationError, "^configuration_failed_prior_values_restored$"):
                            test.configure()
                    test.assert_restored(before)
                finally:
                    test.doCleanups()

    def test_postcommit_runtime_validation_failure_restores_both_stores(self):
        before = self.snapshot()
        original, calls = configuration.fixed_approval, 0
        def inconsistent(**kwargs):
            nonlocal calls
            calls += 1
            return original(**kwargs) if calls == 1 else None
        with patch.object(configuration, "fixed_approval", side_effect=inconsistent):
            with self.assertRaisesRegex(configuration.ConfigurationError, "^configuration_failed_prior_values_restored$"):
                self.configure()
        self.assert_restored(before)

    def test_recovery_preserves_subsequent_external_file_changes_and_stays_disabled(self):
        before = self.snapshot()
        external = b'{"version":1,"enabled":false}\n'
        def changed(db):
            self.approved.write_bytes(external)
            raise sqlite3.OperationalError("synthetic external edit")
        with patch.object(configuration, "_commit", side_effect=changed):
            with self.assertRaisesRegex(configuration.ConfigurationError, "^configuration_failed_recovery_requires_review$"):
                self.configure()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.approved.read_bytes(), external)
        self.assertFalse(self.inspect()["runtimeContractEligible"])
        self.assertFalse(self.inspect()["configured"])

    def test_duplicate_contract_fields_rejected(self):
        path = self.root / "duplicate-contract.json"
        path.write_text('{"source":"cua","source":"imported"}', encoding="utf-8")
        with self.assertRaisesRegex(configuration.ConfigurationError, "^duplicate_json_field_rejected$"):
            configuration.load_contract(path)

    def test_cli_is_fixed_store_only_and_requires_all_configuration_inputs(self):
        cases = [["configure"], ["configure", "--contract-file", "unused", "--user-authorized"],
                 ["inspect", "--contract-file", "unused"],
                 ["inspect", "--data-dir", str(self.directory)]]
        before = self.snapshot()
        for args in cases:
            with self.subTest(args=args), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    configuration.main(args)
                self.assertEqual(raised.exception.code, 2)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.approved.exists())

    def test_cli_help_explains_trusted_operator_and_provenance_limit(self):
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit):
            configuration.main(["--help"])
        rendered = " ".join(output.getvalue().split())
        self.assertIn("not provenance proof", rendered)
        self.assertIn("never registers, starts or sends", rendered)

    def test_cli_inspect_and_configure_only_use_disposable_fixed_environment(self):
        path = self.root / "SYNTHETIC-TEST-contract.json"
        path.write_text(json.dumps(self.contract), encoding="utf-8")
        output = io.StringIO()
        with patch.dict(os.environ, self.environment), redirect_stdout(output):
            status = configuration.main(["configure", "--contract-file", str(path),
                                         "--user-authorized", "--approval-confirmed-at", self.confirmed_at, "--json"])
        self.assertEqual(status, 0)
        result = json.loads(output.getvalue())
        self.assertTrue(result["changed"])
        secret = json.loads(self.raw_setting())["authKeyHex"]
        self.assertNotIn(secret, output.getvalue())
        output = io.StringIO()
        with patch.dict(os.environ, self.environment), redirect_stdout(output):
            self.assertEqual(configuration.main(["inspect", "--json"]), 0)
        self.assertNotIn(secret, output.getvalue())
        self.assertFalse(json.loads(output.getvalue())["operations"]["relayStarted"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
