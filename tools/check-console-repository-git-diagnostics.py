"""Exercise Git failure receipts without contacting or modifying real repositories."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
spec = importlib.util.spec_from_file_location("git_diagnostic_fixture", Path(__file__).with_name("check-console-repository-publish.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
module = fixture.module


class GitDiagnostics(unittest.TestCase):
    def diagnostic(self, stderr, operation="fetch", code=128):
        return module.RepositoryPublishService._diagnostic(module._GitFailure(
            module._git_error_category(stderr), returncode=code,
            operation=operation, error_kind=module._git_error_kind(stderr)))

    def test_remote_unknown_identifies_step_without_claiming_hook_failure(self):
        result = self.diagnostic("fatal: unknown failure with PRIVATE_VALUE\n")
        self.assertEqual((result["code"], result["operationKind"], result["exitCode"]), ("git_remote_failed", "fetch", 128))
        self.assertIn("远端历史", result["summary"])
        self.assertNotIn("hook", result["summary"].lower())
        self.assertNotIn("PRIVATE_VALUE", json.dumps(result))

    def test_known_network_receipts_are_safe_and_actionable(self):
        cases = (
            ("Could not resolve host: PRIVATE_HOST", "resolve_host"),
            ("Failed to connect to PRIVATE_HOST port 443", "connect_failed"),
            ("Recv failure: Connection was reset", "connection_reset"),
            ("SSL certificate problem: PRIVATE_CERT", "tls_failed"),
            ("The requested URL returned error: 503", "server_unavailable"),
        )
        for suffix, kind in cases:
            with self.subTest(kind=kind):
                result = self.diagnostic("fatal: unable to access 'https://secret:PRIVATE_TOKEN@example.invalid/private': " + suffix)
                self.assertEqual((result["code"], result["errorKind"]), ("git_network", kind))
                self.assertNotIn("PRIVATE_", json.dumps(result))
                self.assertNotIn("example.invalid", json.dumps(result))
        result = self.diagnostic("error: RPC failed; curl 92 HTTP/2 stream was not closed cleanly", "push")
        self.assertEqual(result["errorKind"], "transport_failed")

    def test_path_words_progress_and_unknown_hook_text_are_not_error_types(self):
        for stderr in ("M notes/SSL certificate problem.txt", "Uploading PRIVATE_TOKEN connection reset: 15%",
                       "my hook says network authentication permission error", "remote: arbitrary customer message"):
            with self.subTest(stderr=stderr):
                result = self.diagnostic(stderr)
                self.assertEqual((result["code"], result["errorKind"]), ("git_remote_failed", "unknown"))

    def test_existing_auth_permissions_lfs_and_rules_remain_distinct(self):
        cases = (("fatal: Authentication failed for 'https://PRIVATE_TOKEN@example.invalid'", "git_authentication"),
                 ("remote: Permission to owner/repo denied to PRIVATE_USER", "git_permissions"),
                 ("batch response: PRIVATE_LFS_ERROR", "git_lfs"),
                 ("remote: error: GH013: PRIVATE_RULE", "git_rules"))
        for stderr, code in cases:
            result = self.diagnostic(stderr, "push")
            self.assertEqual(result["code"], code)
            self.assertNotIn("PRIVATE_", json.dumps(result))

    def test_untrusted_operation_and_boolean_exit_code_are_not_rendered(self):
        result = module.RepositoryPublishService._diagnostic(module._GitFailure(
            "git_failed", detail="PRIVATE_DETAIL", returncode=True, operation="PRIVATE_OPERATION"))
        self.assertNotIn("operationKind", result)
        self.assertNotIn("exitCode", result)
        self.assertNotIn("PRIVATE_", json.dumps(result))
        result = self.diagnostic("", "fetch", -1073741515)
        self.assertEqual(result["exitCode"], -1073741515)

    def test_global_flags_do_not_hide_staging_and_version_read_commands(self):
        self.assertEqual(module._git_operation(("--literal-pathspecs", "add", "-A")), "add")
        self.assertEqual(module._git_operation(("--literal-pathspecs", "ls-tree", "HEAD")), "ls-tree")
        self.assertEqual(module._git_operation(("stripspace",)), "stripspace")
        for arguments in (("--unknown-global", "add"), ("-c", "PRIVATE_CONFIG", "add"), ("PRIVATE_OPERATION",)):
            self.assertIsNone(module._git_operation(arguments))

    def test_literal_add_failure_keeps_safe_operation(self):
        with fixture.Fixture() as state:
            root, _, _ = state.repo()
            service = state.service()
            completed = subprocess.CompletedProcess([], 128, b"", b"fatal: PRIVATE_FAILURE")
            with mock.patch.object(module.subprocess, "run", return_value=completed):
                with self.assertRaises(module._GitFailure) as raised:
                    service._git(root, "--literal-pathspecs", "add", "--", "PRIVATE_PATH")
            result = service._diagnostic(raised.exception)
            self.assertEqual((result["operationKind"], result["exitCode"]), ("add", 128))
            self.assertNotIn("PRIVATE_", json.dumps(result))

    def test_real_local_git_unknown_option_retains_operation_and_exit_code(self):
        with fixture.Fixture() as state:
            root, _, _ = state.repo()
            service = state.service()
            with self.assertRaises(module._GitFailure) as raised:
                service._git(root, "status", "--console-invalid-option")
            result = service._diagnostic(raised.exception)
            self.assertEqual((result["code"], result["operationKind"]), ("git_unsupported", "status"))
            self.assertIsInstance(result["exitCode"], int)
            self.assertNotEqual(result["exitCode"], 0)

    def test_timeout_and_streaming_share_the_safe_receipt_contract(self):
        with fixture.Fixture() as state:
            root, _, _ = state.repo()
            service = state.service()
            with mock.patch.object(module.subprocess, "run", side_effect=subprocess.TimeoutExpired("PRIVATE_COMMAND", 1)):
                with self.assertRaises(module._GitFailure) as raised:
                    service._git(root, "ls-remote")
            result = service._diagnostic(raised.exception)
            self.assertEqual((result["code"], result["operationKind"], result["errorKind"]), ("git_timeout", "ls-remote", "timeout"))
            self.assertNotIn("exitCode", result)
            self.assertNotIn("PRIVATE_COMMAND", json.dumps(result))
            completed = subprocess.CompletedProcess([], 128, b"", b"error: RPC failed; curl 56 Recv failure: Connection was reset")
            with mock.patch.object(service, "_stream_git", return_value=completed):
                with self.assertRaises(module._GitFailure) as raised:
                    service._git(root, "push", progress=lambda value: None)
            result = service._diagnostic(raised.exception)
            self.assertEqual((result["operationKind"], result["exitCode"], result["errorKind"]), ("push", 128, "connection_reset"))


if __name__ == "__main__":
    unittest.main()
