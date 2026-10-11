"""Exercise actual local HTTP guards with a spy; never opens a real Git repository."""
import ast
from contextlib import contextmanager
import http.client
import importlib.util
import ipaddress
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("developer_http_fixture", ROOT / "tools/check-console-developer-update-http.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class RepositoryPublishError(ValueError):
    pass


class Spy:
    def __init__(self, directory):
        self.state_dir, self.calls, self.busy = directory, [], False

    def status(self):
        self.calls.append(("status",))
        return {"allowed": True, "busy": self.busy, "settings": {"repositories": []}}

    def operation(self, request_id=None):
        self.calls.append(("operation", request_id))
        return {"requestId": request_id, "status": "working"}

    def configure(self, settings):
        self.calls.append(("configure", settings))
        return self.status()

    def preview(self, repo_id=None):
        self.calls.append(("preview", repo_id))
        return {"previews": []}

    def run(self, request_id, repo_ids=None):
        self.calls.append(("run", request_id, repo_ids))
        return {"requestId": request_id, "status": "working"}


def main():
    count = 0
    def check(value, message):
        nonlocal count
        count += 1
        if not value:
            raise AssertionError(message)
    # Exercise the actual integration function against the actual jobs schema:
    # jobs owns record_id; project_id belongs to records, not jobs.
    tree = ast.parse((ROOT / "world_console.py").read_text(encoding="utf-8-sig"))
    snapshot_function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                             and node.name == "repository_publish_work_snapshot")
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE records(id TEXT PRIMARY KEY, project_id TEXT);
        CREATE TABLE jobs(record_id TEXT, kind TEXT, status TEXT, payload TEXT);
        CREATE TABLE idea_dispatches(status TEXT, snapshot TEXT);
    """)
    settings = {"projects": [{"id": "p", "root": "/saved-project"}],
                "app_work_bindings": [{"workspaceRoot": "/native-project"}],
                "app_work_catalog": {"workspaces": [{"root": "/catalog-project"}]}}
    @contextmanager
    def read_database():
        yield db
    service = SimpleNamespace(_db=read_database, _setting=lambda _db, key: settings.get(key))
    snapshot_namespace = {"WORKFLOW_SERVICE": service, "json": json}
    exec(compile(ast.Module(body=[snapshot_function], type_ignores=[]), "world_console.py", "exec"),
         snapshot_namespace)
    db.execute("INSERT INTO records VALUES (?,?)", ("r", "p"))
    for kind, status in (("execute", "running"), ("work", "waiting"), ("work", "starting"),
                         ("work", "cancelling"), ("work", "needs_review"), ("discuss", "running"),
                         ("execute", "completed")):
        db.execute("INSERT INTO jobs VALUES (?,?,?,?)", ("r", kind, status,
                   json.dumps({"nativeWork": {"binding": {"workspaceRoot": "/native-project"}}})))
    db.execute("INSERT INTO idea_dispatches VALUES (?,?)", ("claimed", json.dumps(
               {"origin": "workflow_work", "workspace": {"root": "/dispatch-project"}})))
    db.execute("INSERT INTO idea_dispatches VALUES (?,?)", ("pending", '{"origin":"workflow_discussion"}'))
    snapshot = snapshot_namespace["repository_publish_work_snapshot"]()
    check(len(snapshot["jobs"]) == 5, "All unfinished Work states must block repository publishing")
    check(all(row["root"] == "/saved-project" for row in snapshot["jobs"]), "Resolve Work project ownership")
    check(isinstance(snapshot["jobs"][0]["payload"], dict), "Decode frozen Work payload paths")
    check(len(snapshot["nativeDispatches"]) == 1, "Only unfinished native Work dispatches may block")
    check(snapshot["nativeDispatches"][0]["workspace"]["root"] == "/dispatch-project", "Decode native scope")
    check(snapshot["workspaces"] == settings["app_work_catalog"]["workspaces"], "Reuse existing App catalog")
    check(snapshot["bindings"] == settings["app_work_bindings"], "Reuse existing Work bindings")
    db.close()
    with tempfile.TemporaryDirectory(prefix="console-repositories-http-") as temp:
        root = Path(temp).resolve()
        private = root / "cache/repository-publish-private"
        private.mkdir(parents=True)
        (private / "operation.json").write_text('{"private":true}', encoding="utf-8")
        service, shutdowns = Spy(private), []
        ns = {
            "SimpleHTTPRequestHandler": SimpleHTTPRequestHandler, "Path": Path,
            "urllib": urllib, "ipaddress": ipaddress, "re": re, "json": json,
            "threading": threading, "APP_DIR": root, "MAX_JSON_REQUEST_BYTES": 1024 * 1024,
            "RepositoryPublishError": RepositoryPublishError,
            "DeveloperUpdateError": fixture.DeveloperUpdateError,
            "CONSOLE_REPOSITORY_PUBLISH": service,
            "CONSOLE_DEVELOPER_UPDATE": SimpleNamespace(busy=False, state_dir=root / "cache/developer-update-private"),
            "BLENDER_MUTATION_API_PATHS": frozenset(),
            "PHONE_DEVICE_STORE": SimpleNamespace(directory=root / "phone-private"),
            "WORKFLOW_DATA_DIR": root / "workflow-private",
            "TRUSTED_LOCAL_REQUEST_HOSTNAMES": {"localhost"},
            "_PRIVATE_REQUEST_NETWORKS": tuple(ipaddress.ip_network(v) for v in
                ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")),
            "current_console_edition": lambda: ns["edition"], "edition": "public",
            "APP_INSTALL_MODE": "desktop", "APP_VERSION": "1.0.101", "RUNTIME_INSTANCE_ID": "fixture",
            "PHONE_COMPANION": SimpleNamespace(enabled=False),
            "WORKFLOW_SERVICE": SimpleNamespace(background_enabled=False, has_pending_jobs=lambda: False),
            "shutdown_active_server": lambda: shutdowns.append(True),
        }
        server = ThreadingHTTPServer(("127.0.0.1", 0), fixture.actual_handler(ns))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        port, base = server.server_address[1], "/api/console/repository-publish"
        def request(method, path, value=None, headers=None, raw=None):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                body = raw if raw is not None else json.dumps(value) if value is not None else None
                conn.request(method, path, body=body, headers=headers or {})
                response = conn.getresponse()
                return response.status, response.read()
            finally:
                conn.close()
        def reject(method, path, value=None, headers=None, code=400, raw=None):
            before = len(service.calls)
            status, _ = request(method, path, value, headers, raw)
            check(status == code, f"{method} {path}: {status} != {code}")
            check(len(service.calls) == before, "Rejected request reached the repository service")
        try:
            check(request("GET", base)[0] == 200 and service.calls == [("status",)], "GET must only read")
            check(request("GET", base + "/operation?requestId=one")[0] == 200, "Receipt read failed")
            check(service.calls[-1] == ("operation", "one"), "Receipt identity changed")
            for headers in ({"X-Test-LAN": "1"}, {"Host": "evil.invalid"},
                            {"Origin": "https://evil.invalid"}, {"Sec-Fetch-Site": "cross-site"}):
                reject("GET", base, headers=headers, code=403)
                reject("POST", base + "/run", {"requestId": "one"}, headers, 403)
            for path in ("?command=push", "/operation?requestId=a&requestId=b", "/operation?remote=evil", "/unknown"):
                reject("GET", base + path)
            config = {"repositories": [], "naming": {"preset": "version"}}
            check(request("POST", base + "/config", {"settings": config})[0] == 200, "Config failed")
            check(("configure", config) in service.calls, "Settings changed en route")
            check(request("POST", base + "/preview", {"repoId": "one"})[0] == 200, "Preview failed")
            check(service.calls[-1] == ("preview", "one"), "Preview invoked run")
            check(request("POST", base + "/run", {"requestId": "one", "repoIds": ["one"]})[0] == 200, "Run failed")
            check(service.calls[-1] == ("run", "one", ["one"]), "Selected scope changed")
            for path, value in (("/run", {}), ("/run", {"requestId": 1}),
                    ("/run", {"requestId": "one", "command": "push"}),
                    ("/config", config), ("/config", {"settings": []}),
                    ("/preview", {"remote": "evil"}), ("/run?edition=developer", {"requestId": "one"})):
                reject("POST", base + path, value)
            reject("POST", base + "/run", raw="{")
            reject("POST", base + "/config", raw="x" * (128 * 1024 + 1), code=413)
            for edition, mode in (("lite", "desktop"), ("developer", "store")):
                ns["edition"], ns["APP_INSTALL_MODE"] = edition, mode
                before = len(service.calls)
                code, body = request("GET", base)
                check(code == 200 and json.loads(body)["allowed"] is False and len(service.calls) == before,
                      "Unsupported edition exposed repositories")
                reject("POST", base + "/run", {"requestId": "one"}, code=403)
            ns["edition"], ns["APP_INSTALL_MODE"] = "public", "desktop"
            for method in ("GET", "HEAD"):
                check(request(method, "/cache/repository-publish-private/operation.json")[0] == 404,
                      "Private Git state was served")
            service.busy = True
            reject("POST", "/api/console/update/install", {}, code=409)
            try:
                ns["retire_console_instance"]({})
            except ValueError:
                pass
            else:
                raise AssertionError("Retirement interrupted batch Git work")
            ns["shutdown_if_no_background_work"]()
            check(not shutdowns, "Closing the window interrupted batch Git work")
            service.busy = False
            ns["shutdown_if_no_background_work"]()
            check(shutdowns == [True], "Idle shutdown no longer works")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
    print(f"Repository publish HTTP: {count} actual guard assertions passed; no real Git operations.")


if __name__ == "__main__":
    main()
