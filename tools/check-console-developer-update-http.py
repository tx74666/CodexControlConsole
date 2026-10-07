"""Exercise the real HTTP guards without importing or migrating the application."""
import ast
import http.client
import ipaddress
import json
from pathlib import Path
import re
import socket
import tempfile
import threading
from types import SimpleNamespace
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ast.parse((ROOT / "world_console.py").read_text(encoding="utf-8-sig"))


class DeveloperUpdateError(ValueError):
    pass


class SpyService:
    def __init__(self, directory):
        self.state_dir = directory
        self.calls = []
        self.busy = False

    def status(self):
        self.calls.append(("status",))
        return {"allowed": True, "enabled": False}

    def operation(self, request_id=None):
        self.calls.append(("operation", request_id))
        return {"requestId": request_id, "status": "succeeded"}

    def configure(self, enabled, source_root=None):
        self.calls.append(("configure", enabled, source_root))
        return {"allowed": True, "enabled": enabled}

    def update(self, request_id, fingerprint, **kwargs):
        self.calls.append(("update", request_id, fingerprint, kwargs))
        return {"requestId": request_id, "status": "accepted"}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def actual_handler(namespace):
    functions = {
        "_normalize_http_hostname", "_parse_http_authority", "_is_trusted_request_host",
        "_client_address_is_loopback", "_origin_matches_host", "retire_console_instance",
        "shutdown_if_no_background_work",
    }
    methods = {
        "__init__", "require_local_request", "require_trusted_post_context", "do_GET",
        "do_HEAD", "_private_phone_path", "_dispatch_POST", "read_json_body", "send_json",
    }
    nodes = []
    for node in SOURCE.body:
        if isinstance(node, ast.FunctionDef) and node.name in functions:
            nodes.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == "RequestBodyError":
            nodes.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == "ConsoleHandler":
            nodes.append(ast.ClassDef(name=node.name, bases=node.bases, keywords=[],
                body=[method for method in node.body if isinstance(method, ast.FunctionDef) and method.name in methods],
                decorator_list=[]))
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(module, str(ROOT / "world_console.py"), "exec"), namespace)
    base = namespace["ConsoleHandler"]

    class TestHandler(base):
        # Simulate a LAN connection while keeping the fixture listener on loopback.
        def require_local_request(self):
            if self.headers.get("X-Test-LAN"):
                original = self.client_address
                self.client_address = ("192.168.1.42", original[1])
                try:
                    return super().require_local_request()
                finally:
                    self.client_address = original
            return super().require_local_request()

        def do_POST(self):
            self._dispatch_POST()

        def log_message(self, *_args):
            pass

    return TestHandler


def main():
    with tempfile.TemporaryDirectory(prefix="console-developer-http-") as temporary:
        app_dir = Path(temporary).resolve()
        private = app_dir / "cache" / "developer-update-private"
        private.mkdir(parents=True)
        (private / "receipt.json").write_text('{"private":true}', encoding="utf-8")
        service = SpyService(private)
        shutdowns = []
        namespace = {
            "SimpleHTTPRequestHandler": SimpleHTTPRequestHandler,
            "Path": Path, "urllib": urllib, "ipaddress": ipaddress, "re": re, "json": json,
            "threading": threading, "APP_DIR": app_dir, "MAX_JSON_REQUEST_BYTES": 1024 * 1024,
            "DeveloperUpdateError": DeveloperUpdateError, "CONSOLE_DEVELOPER_UPDATE": service,
            "BLENDER_MUTATION_API_PATHS": frozenset(),
            "PHONE_DEVICE_STORE": SimpleNamespace(directory=app_dir / "phone-private"),
            "WORKFLOW_DATA_DIR": app_dir / "workflow-private",
            "TRUSTED_LOCAL_REQUEST_HOSTNAMES": {"localhost"},
            "_PRIVATE_REQUEST_NETWORKS": tuple(ipaddress.ip_network(value) for value in
                ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")),
            "current_console_edition": lambda: namespace["edition"], "edition": "public",
            "APP_INSTALL_MODE": "desktop", "APP_VERSION": "1.0.78", "RUNTIME_INSTANCE_ID": "fixture",
            "PHONE_COMPANION": SimpleNamespace(enabled=False),
            "WORKFLOW_SERVICE": SimpleNamespace(background_enabled=False, has_pending_jobs=lambda: False),
            "shutdown_active_server": lambda: shutdowns.append(True),
        }
        handler = actual_handler(namespace)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        base = "/api/console/developer-update"

        def request(method, path, payload=None, headers=None, raw=None):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            body = raw if raw is not None else (json.dumps(payload) if payload is not None else None)
            try:
                connection.request(method, path, body=body, headers=headers or {})
                response = connection.getresponse()
                data = response.read()
                return response.status, data
            finally:
                connection.close()

        def rejected(method, path, payload=None, headers=None, raw=None, status=403):
            before = len(service.calls)
            code, _ = request(method, path, payload, headers, raw)
            require(code == status, f"{method} {path}: expected {status}, got {code}")
            require(len(service.calls) == before, "rejected request reached the Git service")

        try:
            require(request("GET", base)[0] == 200, "native loopback status failed")
            require(service.calls == [("status",)], "status invoked an operation")
            require(request("GET", base + "/operation?requestId=original")[0] == 200, "receipt GET failed")
            require(service.calls[-1] == ("operation", "original"), "receipt identity changed")
            require(request("GET", base, headers={"Origin": f"http://127.0.0.1:{port}"})[0] == 200,
                "same-origin browser status failed")
            for method, path, payload in [("GET", base, None), ("POST", base + "/config", {"enabled": True})]:
                rejected(method, path, payload, {"X-Test-LAN": "1"})
                rejected(method, path, payload, {"Host": "evil.example"})
                rejected(method, path, payload, {"Origin": "https://evil.example"})
                rejected(method, path, payload, {"Sec-Fetch-Site": "cross-site"})
            for query in ("?edition=developer", "/status", "/operation?requestId=a&requestId=b",
                    "/operation?command=push", "/operation?requestId=a&remote=evil"):
                rejected("GET", base + query, status=400)
            for edition, mode in (("lite", "desktop"), ("developer", "store")):
                namespace["edition"], namespace["APP_INSTALL_MODE"] = edition, mode
                before = len(service.calls)
                code, body = request("GET", base)
                require(code == 200 and json.loads(body) == {"allowed": False, "enabled": False}, "unsupported status exposed state")
                require(len(service.calls) == before, "unsupported status touched the repository")
                rejected("POST", base + "/config", {"enabled": True})
            namespace["edition"], namespace["APP_INSTALL_MODE"] = "developer", "desktop"
            require(request("POST", base + "/config", {"enabled": True, "sourceRoot": "source-fixture"})[0] == 200,
                "explicit configuration failed")
            require(service.calls[-1] == ("configure", True, "source-fixture"), "source configuration was changed")
            run = {"requestId": "one", "stateFingerprint": "frozen", "action": "verify", "actionId": "explicit"}
            require(request("POST", base + "/run", run)[0] == 200, "explicit recovery failed")
            require(service.calls[-1] == ("update", "one", "frozen", {"action": "verify", "action_id": "explicit"}),
                "recovery action identity was lost")
            for path, payload in [("/config", {"enabled": 1}), ("/config", {"enabled": True, "command": "push"}),
                    ("/run", {"requestId": "one"}), ("/run", {**run, "remote": "evil"}),
                    ("/run", []), ("/run?edition=developer", run), ("/other", {})]:
                rejected("POST", base + path, payload, status=400)
            rejected("POST", base + "/run", raw="{", status=400)
            rejected("POST", base + "/run", raw="x" * 8193, status=413)
            for method in ("GET", "HEAD"):
                require(request(method, "/cache/developer-update-private/receipt.json")[0] == 404,
                    "private receipt was served as a static file")

            # Duplicate Host must not be accepted even when both values are local.
            with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
                connection.sendall((f"GET {base} HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\nHost: localhost:{port}\r\n\r\n").encode())
                response = connection.recv(4096)
            require(response.split(b"\r\n", 1)[0].split()[1] == b"403", "duplicate Host was accepted")

            service.busy = True
            rejected("POST", "/api/console/update/install", {}, status=409)
            try:
                namespace["retire_console_instance"]({})
            except ValueError:
                pass
            else:
                raise AssertionError("retirement interrupted an active source update")
            namespace["shutdown_if_no_background_work"]()
            require(not shutdowns, "last-window close interrupted an active source update")
            service.busy = False
            namespace["shutdown_if_no_background_work"]()
            require(shutdowns == [True], "idle normal shutdown no longer works")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    print("Developer Update HTTP: local origin, edition, payload, private state and shutdown guards passed.")


if __name__ == "__main__":
    main()
