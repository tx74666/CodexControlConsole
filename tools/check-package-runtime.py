"""Exercise the actual diagnostic route without loading production services."""
import ast
import builtins
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / "world_console.py").read_text(encoding="utf-8"))
HELPER = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "package_runtime_status")
HANDLER = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "ConsoleHandler")
ROUTE = next(node for node in HANDLER.body if isinstance(node, ast.FunctionDef) and node.name == "do_GET")
SECRET = "fixture-secret-code-and-private-path"


class Digest:
    def update(self, value):
        assert value == b"Codex Console packaged runtime check"

    def finalize(self):
        return b"x" * 32


def load_route(fail_import=None, fail_hash=None, fail_signature=None, frozen=True,
               missing_surface=False, missing_signature=False,
               missing_certifi_surface=False, fail_certificate=None,
               fail_challenge_scripts=None, empty_challenge_script=False):
    imports = []

    def must_not_run(*args, **kwargs):
        raise AssertionError("The diagnostic must not create a broker or send inference")

    def make_hash(*args):
        if fail_hash:
            raise fail_hash(SECRET)
        return Digest()

    def algorithms():
        if fail_signature:
            raise fail_signature(SECRET)
        return {} if missing_signature else {"RS256": object()}

    class CertificateContext:
        def __init__(self, protocol):
            assert protocol == "fixture-TLS-client"

        def load_verify_locations(self, cafile):
            assert cafile == SECRET
            if fail_certificate:
                raise fail_certificate(SECRET)

    def challenge_script():
        if fail_challenge_scripts:
            raise fail_challenge_scripts(SECRET)
        return "" if empty_challenge_script else "fixture-JS-script"

    modules = {
        "certifi": SimpleNamespace() if missing_certifi_surface else SimpleNamespace(where=lambda: SECRET),
        "ssl": SimpleNamespace(SSLContext=CertificateContext, PROTOCOL_TLS_CLIENT="fixture-TLS-client"),
        "yt_dlp": SimpleNamespace(version=SimpleNamespace(__version__="fixture-media"), YoutubeDL=must_not_run),
        "yt_dlp_ejs": SimpleNamespace(version="0.8.0"),
        "yt_dlp_ejs.yt.solver": SimpleNamespace(core=challenge_script, lib=challenge_script),
        "jwt": SimpleNamespace(__version__="fixture-jwt", algorithms=SimpleNamespace(get_default_algorithms=algorithms)),
        "cryptography": SimpleNamespace(__version__="fixture-crypto"),
        "cryptography.hazmat.primitives": SimpleNamespace(hashes=SimpleNamespace(Hash=make_hash, SHA256=object)),
        "workflow_subscription": SimpleNamespace(SubscriptionBroker=None if missing_surface else must_not_run),
        "workflow_subscription_delivery": SimpleNamespace(SubscriptionDeliveryMixin=must_not_run),
        "workflow_subscription_stream": SimpleNamespace(run_response=must_not_run),
    }

    def import_fixture(name, *args, **kwargs):
        imports.append(name)
        if fail_import and name == fail_import[0]:
            raise fail_import[1](SECRET)
        if name not in modules:
            raise AssertionError("Unexpected dependency import: " + name)
        return modules[name]

    namespace = {
        "__builtins__": {**vars(builtins), "__import__": import_fixture},
        "urllib": SimpleNamespace(parse=urllib.parse), "APP_VERSION": "fixture-version",
        "sys": SimpleNamespace(frozen=frozen),
    }
    exec(compile(ast.Module(body=[HELPER, ROUTE], type_ignores=[]), "world_console.py", "exec"), namespace)
    return namespace, imports


def http_result(namespace, remote=False):
    class Handler(BaseHTTPRequestHandler):
        do_GET = namespace["do_GET"]

        def _private_phone_path(self):
            return False

        def require_local_request(self):
            if remote:
                self.send_json({"error": "This action is available on this PC only."}, status=403)
                return False
            return True

        def send_json(self, value, status=200):
            body = json.dumps(value).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            response = opener.open(f"http://127.0.0.1:{server.server_port}/api/console/package-check", timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


class PackageRuntimeTests(unittest.TestCase):
    def test_healthy_frozen_route(self):
        namespace, imports = load_route()
        status, result = http_result(namespace)
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertTrue(result["mediaCertificates"])
        self.assertTrue(result["mediaChallengeScripts"])
        self.assertEqual(result["ejsVersion"], "0.8.0")
        self.assertTrue(result["subscriptionModules"])
        self.assertTrue(result["subscriptionRuntime"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(imports), 11)

    def test_missing_and_empty_challenge_scripts_fail_without_network(self):
        for case, expected_code in (
            ({"fail_challenge_scripts": OSError}, "OSError"),
            ({"empty_challenge_script": True}, "ValueError"),
        ):
            with self.subTest(case=case):
                namespace, _ = load_route(**case)
                _, result = http_result(namespace)
                self.assertFalse(result["ok"])
                self.assertTrue(result["ytDlp"])
                self.assertTrue(result["mediaCertificates"])
                self.assertFalse(result["mediaChallengeScripts"])
                self.assertTrue(result["subscriptionRuntime"])
                self.assertEqual(result["errors"], [
                    {"component": "media", "stage": "challenge_scripts", "code": expected_code},
                ])
                self.assertNotIn(SECRET, json.dumps(result))

    def test_data_only_certifi_namespace_fails_before_downloader_import(self):
        namespace, imports = load_route(missing_certifi_surface=True)
        status, result = http_result(namespace)
        self.assertEqual(status, 200)
        self.assertFalse(result["ok"])
        self.assertFalse(result["mediaCertificates"])
        self.assertFalse(result["ytDlp"])
        self.assertTrue(result["subscriptionRuntime"])
        self.assertEqual(result["errors"], [
            {"component": "media", "stage": "certificate_module", "code": "AttributeError"},
        ])
        self.assertNotIn("yt_dlp", imports)
        self.assertNotIn(SECRET, json.dumps(result))

    def test_missing_or_invalid_ca_bundle_is_a_safe_media_failure(self):
        for error in (OSError, ValueError):
            with self.subTest(error=error.__name__):
                namespace, imports = load_route(fail_certificate=error)
                _, result = http_result(namespace)
                self.assertFalse(result["ok"])
                self.assertFalse(result["mediaCertificates"])
                self.assertTrue(result["subscriptionRuntime"])
                self.assertEqual(result["errors"], [
                    {"component": "media", "stage": "certificate_bundle", "code": error.__name__},
                ])
                self.assertNotIn("yt_dlp", imports)
                self.assertNotIn(SECRET, json.dumps(result))

    def test_media_exception_still_returns_json_and_checks_subscription(self):
        namespace, _ = load_route(fail_import=("yt_dlp", AttributeError))
        status, result = http_result(namespace)
        self.assertEqual(status, 200)
        self.assertFalse(result["ok"])
        self.assertTrue(result["subscriptionRuntime"])
        self.assertEqual(result["errors"], [{"component": "media", "stage": "import", "code": "AttributeError"}])
        self.assertNotIn(SECRET, json.dumps(result))

    def test_native_errors_are_safe_and_do_not_disable_media(self):
        unsupported = type("UnsupportedAlgorithm", (Exception,), {})
        unusual = type("fixture_private_exception_name", (Exception,), {})
        for error in (TypeError, AttributeError, unsupported, unusual):
            with self.subTest(error=error.__name__):
                namespace, _ = load_route(fail_hash=error)
                status, result = http_result(namespace)
                self.assertEqual(status, 200)
                self.assertTrue(result["ytDlp"])
                self.assertFalse(result["ok"])
                self.assertFalse(result["subscriptionRuntime"])
                self.assertNotIn(SECRET, json.dumps(result))
                self.assertNotIn("fixture_private_exception_name", json.dumps(result))

    def test_signature_exception_preserves_source_compatibility(self):
        namespace, _ = load_route(fail_signature=AttributeError, frozen=False)
        status, result = http_result(namespace)
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertFalse(result["subscriptionRuntime"])
        self.assertEqual(result["errors"][0]["stage"], "signature")

    def test_missing_subscription_surface_fails_frozen_check(self):
        namespace, _ = load_route(missing_surface=True)
        _, result = http_result(namespace)
        self.assertFalse(result["ok"])
        self.assertFalse(result["subscriptionModules"])
        self.assertEqual(result["errors"][0]["stage"], "module_surface")

    def test_missing_rs256_is_reported_as_signature_failure(self):
        namespace, _ = load_route(missing_signature=True)
        _, result = http_result(namespace)
        self.assertFalse(result["ok"])
        self.assertTrue(result["subscriptionModules"])
        self.assertEqual(result["errors"][0]["stage"], "signature")

    def test_remote_request_is_denied_before_importing_dependencies(self):
        namespace, imports = load_route()
        status, _ = http_result(namespace, remote=True)
        self.assertEqual(status, 403)
        self.assertEqual(imports, [])


if __name__ == "__main__":
    unittest.main()
