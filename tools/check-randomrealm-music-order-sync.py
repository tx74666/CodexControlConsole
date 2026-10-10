"""Exercise production sync functions and HTTP guards using isolated files only."""
import ast
from datetime import datetime, timezone
import hashlib
import http.client
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import urllib.parse
import uuid


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ast.parse((ROOT / "world_console.py").read_text(encoding="utf-8-sig"))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def load_actual(directory):
    names = {
        "atomic_write_json", "read_randomrealm_music_order_json",
        "randomrealm_music_order_request_id", "randomrealm_music_order_sync_status",
        "build_randomrealm_music_order_request", "request_randomrealm_music_order_sync",
        "_normalize_http_hostname", "_parse_http_authority", "_is_trusted_request_host",
        "_client_address_is_loopback", "_origin_matches_host",
    }
    methods = {
        "__init__", "require_local_request", "require_trusted_post_context", "do_GET",
        "_dispatch_POST", "read_json_body", "send_json",
    }
    nodes = []
    for node in SOURCE.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            nodes.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == "RequestBodyError":
            nodes.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == "ConsoleHandler":
            nodes.append(ast.ClassDef(name=node.name, bases=node.bases, keywords=[],
                body=[method for method in node.body if isinstance(method, ast.FunctionDef)
                      and method.name in methods], decorator_list=[]))
    namespace = {
        "Path": Path, "json": json, "os": os, "tempfile": tempfile,
        "threading": threading, "datetime": datetime, "timezone": timezone,
        "hashlib": hashlib, "uuid": uuid, "re": re, "urllib": urllib,
        "ipaddress": ipaddress, "SimpleHTTPRequestHandler": SimpleHTTPRequestHandler,
        "APP_DIR": directory, "MAX_JSON_REQUEST_BYTES": 1024 * 1024,
        "MUSIC_STATE_LOCK": threading.RLock(), "RANDOMREALM_MUSIC_ORDER_LOCK": threading.RLock(),
        "MUSIC_STATE_FILE": directory / "music_state.json",
        "RANDOMREALM_MUSIC_CATALOG_FILE": directory / "catalog.json",
        "RANDOMREALM_MUSIC_ORDER_REQUEST_FILE": directory / "game" / "order-sync-request.json",
        "RANDOMREALM_MUSIC_ORDER_RECEIPT_FILE": directory / "game" / "order-sync-receipt.json",
        "TRUSTED_LOCAL_REQUEST_HOSTNAMES": {"localhost"},
        "_PRIVATE_REQUEST_NETWORKS": tuple(ipaddress.ip_network(value) for value in
            ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")),
    }
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(module, str(ROOT / "world_console.py"), "exec"), namespace)
    base = namespace["ConsoleHandler"]

    class Handler(base):
        def _private_phone_path(self):
            return False

        def do_POST(self):
            self._dispatch_POST()

        def require_local_request(self):
            if self.headers.get("X-Test-LAN"):
                original = self.client_address
                self.client_address = ("192.168.1.42", original[1])
                try:
                    return super().require_local_request()
                finally:
                    self.client_address = original
            return super().require_local_request()

        def log_message(self, *_args):
            pass

    return namespace, Handler


def main():
    with tempfile.TemporaryDirectory(prefix="console-music-order-sync-") as temporary:
        directory = Path(temporary)
        api, handler = load_actual(directory)
        catalog = {"version": 1, "tracks": [
            {"id": f"{number + 1:016x}", "audioFile": f"Song {number}.mp3",
             "audioSha256": hashlib.sha256(str(number).encode()).hexdigest()}
            for number in range(17)
        ]}
        write = api["atomic_write_json"]
        write(api["RANDOMREALM_MUSIC_CATALOG_FILE"], catalog)
        paths = [track["audioFile"] for track in reversed(catalog["tracks"])]
        state = {"order": paths, "tiers": {paths[2]: "first", paths[4]: "second"},
                 "selectedTrackPath": paths[7], "otherData": {"untouched": True}}
        write(api["MUSIC_STATE_FILE"], state)
        state_before = api["MUSIC_STATE_FILE"].read_bytes()
        catalog_before = api["RANDOMREALM_MUSIC_CATALOG_FILE"].read_bytes()
        require(api["randomrealm_music_order_sync_status"]()["status"] == "idle", "fresh state is not idle")
        request_status = api["request_randomrealm_music_order_sync"]()
        request_file = api["RANDOMREALM_MUSIC_ORDER_REQUEST_FILE"]
        request_before = request_file.read_bytes()
        request = json.loads(request_before)
        require(request_status["status"] == "pending", "writing a request claimed game success")
        require(request["catalogSha256"] == hashlib.sha256(catalog_before).hexdigest(), "catalog hash differs")
        require(len(request["entries"]) == 17, "request does not cover all 17 songs")
        require([entry["order"] for entry in request["entries"]] == list(range(17)), "order is not contiguous")
        require(request["entries"][0]["id"] == catalog["tracks"][14]["id"], "first tier does not follow saved state")
        require(request["entries"][1]["id"] == catalog["tracks"][12]["id"], "second tier does not follow saved state")
        require(request["entries"][2]["id"] == catalog["tracks"][16]["id"], "third tier did not preserve current reverse order")
        require(set(request) == {"version", "requestId", "createdUtc", "catalogSha256", "entries"}, "unrequested player state leaked")
        require(all(set(entry) == {"id", "audioSha256", "tier", "order"} for entry in request["entries"]), "non-order data leaked")
        write(api["MUSIC_STATE_FILE"], {**state, "order": list(reversed(paths))})
        repeated = api["request_randomrealm_music_order_sync"]()
        require(repeated["requestId"] == request["requestId"] and request_file.read_bytes() == request_before,
                "repeated click overwrote a pending request")
        receipt_file = api["RANDOMREALM_MUSIC_ORDER_RECEIPT_FILE"]
        write(receipt_file, {"version": 1, "requestId": str(uuid.uuid4()), "status": "applied"})
        require(api["randomrealm_music_order_sync_status"]()["status"] == "pending", "unrelated receipt claimed success")
        write(receipt_file, {"version": 1, "requestId": request["requestId"], "status": "applied", "appliedUtc": "2026-10-10T00:00:00Z"})
        require(api["randomrealm_music_order_sync_status"]()["status"] == "applied", "matching game receipt was not applied")
        next_status = api["request_randomrealm_music_order_sync"]()
        require(next_status["requestId"] != request["requestId"] and next_status["status"] == "pending", "changed order did not create a new request")
        require(api["randomrealm_music_order_sync_status"](request["requestId"])["status"] == "superseded", "stale poll received another request's result")
        next_request = json.loads(request_file.read_bytes())
        write(receipt_file, {"version": 1, "requestId": next_request["requestId"], "status": "applied"})
        manual_again = api["request_randomrealm_music_order_sync"]()
        refreshed_request = json.loads(request_file.read_bytes())
        require(manual_again["requestId"] != next_request["requestId"]
                and refreshed_request["entries"] == next_request["entries"],
                "manual re-sync reused an old receipt after a possible game Undo")
        next_request = refreshed_request
        write(receipt_file, {"version": 1, "requestId": next_request["requestId"], "status": "rejected"})
        require(api["randomrealm_music_order_sync_status"]()["status"] == "rejected", "game rejection not reported")
        write(api["MUSIC_STATE_FILE"], {**state, "order": paths[:-1]})
        protected_pending = request_file.read_bytes()
        try:
            api["request_randomrealm_music_order_sync"]()
            raise AssertionError("missing song was accepted")
        except ValueError:
            pass
        require(request_file.read_bytes() == protected_pending, "invalid request overwrote the prior request")
        write(api["MUSIC_STATE_FILE"], state)
        write(receipt_file, {"version": 1, "requestId": next_request["requestId"], "status": "applied"})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def request_http(method, extra_headers=None, suffix="", body=b"{}"):
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            headers = {"Content-Type": "application/json"}
            headers.update(extra_headers or {})
            connection.request(method, "/api/randomrealm/music-order-sync" + suffix,
                               body=body if method == "POST" else None, headers=headers)
            response = connection.getresponse()
            result = response.status, json.loads(response.read())
            connection.close()
            return result

        try:
            require(request_http("POST", {"Origin": "https://outside.test"})[0] == 403, "foreign Origin allowed")
            require(request_http("POST", {"Sec-Fetch-Site": "cross-site"})[0] == 403, "cross-site request allowed")
            require(request_http("POST", {"X-Test-LAN": "1"})[0] == 403, "LAN mutation allowed")
            require(request_http("GET", {"X-Test-LAN": "1"})[0] == 403, "LAN status allowed")
            require(request_http("POST", suffix="?other=1")[0] == 400, "POST query accepted")
            require(request_http("POST", body=b'{"entries":[]}')[0] == 400, "browser supplied game identities accepted")
            require(request_http("GET", suffix="?requestId=wrong")[0] == 400, "invalid request ID accepted")
            origin = f"http://127.0.0.1:{server.server_port}"
            status, result = request_http("POST", {"Origin": origin})
            require(status == 200 and result["status"] == "pending", "same-origin manual sync failed")
            status, result = request_http("GET")
            require(status == 200 and result["status"] == "pending", "GET falsely claimed offline game applied")
            require(api["MUSIC_STATE_FILE"].read_bytes() == state_before, "sync modified current music state")
            require(api["RANDOMREALM_MUSIC_CATALOG_FILE"].read_bytes() == catalog_before, "sync modified game catalog")
            require(not list((directory / "game").glob("*.tmp")), "temporary writes were left behind")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    print("PASS music order sync: current 17-song order, identities, pending/replay receipts, protected files, local HTTP guards")


if __name__ == "__main__":
    main()
