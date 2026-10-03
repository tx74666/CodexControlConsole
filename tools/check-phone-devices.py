"""Isolated remembered-device authentication and same-network lifecycle checks."""
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from document_library import DocumentLibraryService
from phone_device_store import PhoneDeviceStore, DeviceStoreError, REMEMBER_TTL
import phone_companion as phone


class FakeAnnouncer:
    def __init__(self):
        self.available = False
        self.calls = []
    def start(self, hostname, host, port, version):
        self.available = True
        self.calls.append((hostname, host, port, version))
    def stop(self):
        self.available = False
    def state(self):
        return {"available": self.available, "status": "active" if self.available else "stopped", "error": ""}


class PhoneDeviceChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-phone-devices-")
        self.base = Path(self.temp.name)
        self.library = self.base / "library"
        self.library.mkdir()
        self.assets = self.base / "assets"
        self.assets.mkdir()
        (self.assets / "mobile.html").write_text("<!doctype html><title>Phone</title>", encoding="utf-8")
        self.documents = DocumentLibraryService(self.base / "documents.json")
        self.documents.select(str(self.library))
        self.now = [1_800_000_000.0]
        self.store = PhoneDeviceStore(self.assets / "cache" / "phone-private", clock=lambda: self.now[0])
        self.interfaces = [{"address": "127.0.0.1", "name": "Test physical network", "fingerprint": "a" * 64}]
        self.service = self.make_service()
        original = phone.is_lan_address
        self.policy = patch.object(phone, "is_lan_address", lambda value: value == "127.0.0.1" or original(value))
        self.policy.start()
        with socket.socket() as holder:
            holder.bind(("127.0.0.1", 0))
            self.port = holder.getsockname()[1]
        self.service.start("127.0.0.1", self.port)
        self.cookies = {}

    def make_service(self):
        return phone.PhoneCompanionService(self.documents, lambda: {}, self.assets, "1.0.test",
            computer_id="1234567890abcdef1234567890abcdef", device_store=self.store,
            interface_getter=lambda: [dict(item) for item in self.interfaces], announcer=FakeAnnouncer())

    def tearDown(self):
        self.service.shutdown()
        self.policy.stop()
        self.temp.cleanup()

    def request(self, path, method="GET", body=None, headers=None, *, jar=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        authority = f"{self.service.hostname}:{self.port}"
        merged = {"Host": authority}
        jar = self.cookies if jar is None else jar
        if jar:
            merged["Cookie"] = "; ".join(key + "=" + value for key, value in jar.items())
        if method == "POST":
            merged.update({"Origin": "http://" + authority, "X-Codex-Phone": "1", "Content-Type": "application/json"})
        merged.update(headers or {})
        try:
            connection.request(method, path, json.dumps(body or {}) if method == "POST" else None, merged)
            response = connection.getresponse()
            raw = response.read()
            result_headers = response.getheaders()
            for key, value in result_headers:
                if key.lower() == "set-cookie":
                    name, value = value.split(";", 1)[0].split("=", 1)
                    if value:
                        jar[name] = value
                    else:
                        jar.pop(name, None)
            try:
                result = json.loads(raw)
            except (ValueError, UnicodeError):
                result = raw
            return response.status, result, result_headers
        finally:
            connection.close()

    def remember(self):
        token = self.service.state(False)["qrToken"]
        status, result, headers = self.request("/api/phone/pair", "POST", {"qrToken": token, "remember": True, "deviceName": "床上 iPhone"})
        self.assertEqual(status, 200, result)
        self.assertTrue(result["remembered"])
        self.assertEqual(result["expiresIn"], REMEMBER_TTL)
        return token, result, headers

    def test_qr_once_no_secret_in_json_hash_only_and_persistent_cookie(self):
        qr, result, headers = self.remember()
        credential = self.cookies[phone.REMEMBER_COOKIE_NAME]
        self.assertNotIn(credential, json.dumps(result))
        persistent = [value for key, value in headers if key.lower() == "set-cookie" and value.startswith(phone.REMEMBER_COOKIE_NAME + "=")][0]
        for flag in ("HttpOnly", "SameSite=Strict", "Max-Age=" + str(REMEMBER_TTL)):
            self.assertIn(flag, persistent)
        self.assertEqual(self.request("/api/phone/pair", "POST", {"qrToken": qr, "remember": True})[0], 401)
        state = self.service.state(False)
        self.assertEqual(len(state["rememberedDevices"]), 1)
        self.assertEqual(state["rememberedDevices"][0]["name"], "床上 iPhone")
        for key in ("secret", "secret_hash", "root_hash", "network_hash", "token"):
            self.assertNotIn(key, state["rememberedDevices"][0])
        raw = (self.store.directory / "phone-devices.sqlite3").read_bytes()
        self.assertNotIn(credential.encode("ascii"), raw)
        self.assertNotIn(credential.split(".")[1].encode("ascii"), raw)
        self.assertTrue(self.request("/api/phone/status")[1]["remembered"])

    def test_restart_restore_same_host_cookie_and_phone_dhcp_change(self):
        self.remember()
        credential = self.cookies[phone.REMEMBER_COOKIE_NAME]
        stable = self.service.connection_url
        self.service.shutdown()
        self.assertTrue(self.store.settings()["enabled"])
        self.store = PhoneDeviceStore(self.store.directory, clock=lambda: self.now[0])
        self.service = self.make_service()
        state = self.service.restore()
        self.assertTrue(state["enabled"])
        self.assertEqual(self.service.connection_url, stable)
        self.assertTrue(self.request("/api/phone/status")[1]["remembered"])
        session = self.service.session("device:" + credential, "192.168.1.201")
        self.assertTrue(session["remembered"])
        self.assertEqual(session["root"], self.documents.state()["root"])

    def test_manual_stop_keeps_trust_but_disables_restart_then_reenable(self):
        self.remember()
        self.service.stop()
        self.assertFalse(self.store.settings()["enabled"])
        self.assertEqual(len(self.store.list()), 1)
        self.service = self.make_service()
        self.assertFalse(self.service.restore()["enabled"])
        self.service.start("127.0.0.1", self.port)
        self.assertTrue(self.request("/api/phone/status")[1]["paired"])

    def test_bad_cookie_root_change_expiry_and_logout_revoke_all_session_forms(self):
        self.remember()
        credential = self.cookies[phone.REMEMBER_COOKIE_NAME]
        session_token = self.cookies[phone.COOKIE_NAME]
        bad = credential[:-1] + ("a" if credential[-1] != "a" else "b")
        self.assertEqual(self.request("/api/phone/status", jar={phone.REMEMBER_COOKIE_NAME: bad})[1], {"paired": False})
        self.assertEqual(len(self.store.list()), 1)
        self.assertEqual(self.request("/api/phone/logout", "POST")[1], {"paired": False})
        self.assertFalse(self.store.list())
        for token in ("device:" + credential, session_token):
            with self.assertRaises(phone.PhoneRequestError):
                self.service.session(token, "127.0.0.1")
        self.service.renew_pairing()
        self.remember()
        other = self.base / "other"
        other.mkdir()
        self.documents.select(str(other))
        self.assertEqual(self.request("/api/phone/status")[1], {"paired": False})
        self.assertEqual(self.store.list(), [])
        self.documents.select(str(self.library))
        self.service.renew_pairing()
        self.remember()
        self.now[0] += REMEMBER_TTL + 1
        self.assertEqual(self.request("/api/phone/status")[1], {"paired": False})

    def test_scopes_csrf_authority_and_refresh_generation_are_narrow(self):
        state = self.service.state(False)
        qr = state["qrToken"]
        self.assertGreaterEqual(len(qr), 43)
        self.assertIn("#qrToken=" + qr, state["qrUrl"])
        self.assertNotIn(qr, state["connectionUrl"])
        new_state = self.service.renew_pairing()
        self.assertNotEqual(state["qrGeneration"], new_state["qrGeneration"])
        self.assertNotEqual(qr, new_state["qrToken"])
        self.assertEqual(self.request("/api/phone/pair", "POST", {"qrToken": qr})[0], 401)
        for headers in ({"Host": "attacker.local:" + str(self.port)}, {"Origin": "http://127.0.0.1:" + str(self.port)}, {"X-Codex-Phone": ""}):
            self.assertEqual(self.request("/api/phone/pair", "POST", {"qrToken": new_state["qrToken"]}, headers=headers)[0], 403)
        self.remember()
        token = self.cookies[phone.REMEMBER_COOKIE_NAME]
        with self.assertRaises(phone.PhoneRequestError):
            self.service.session("device:" + token, "127.0.0.1", scope="plan-sync")
        code = self.service.renew_pairing()["pairingCode"]
        plan_token = self.service.pair(code, "127.0.0.1", scope="plan-sync")
        self.assertFalse(self.service.is_paired(plan_token, "127.0.0.1"))

    def test_network_change_stops_listener_same_network_ip_rebind_preserves_trust(self):
        self.remember()
        credential = self.cookies[phone.REMEMBER_COOKIE_NAME]
        self.interfaces[0]["fingerprint"] = "b" * 64
        self.service.check_network()
        self.assertFalse(self.service.enabled)
        self.assertTrue(self.service.state(False)["autoRestore"]["enabled"])
        self.assertEqual(self.service.state(False)["autoRestore"]["status"], "waiting-for-approved-network")
        self.assertEqual(len(self.store.list()), 1)
        self.interfaces[0]["fingerprint"] = "a" * 64
        self.service.check_network()
        self.assertTrue(self.service.enabled)
        self.assertTrue(self.request("/api/phone/status")[1]["paired"])
        # Rebind logic is checked without opening another real LAN socket.
        self.interfaces[0]["address"] = "192.168.1.88"
        with patch.object(self.service, "_start") as start:
            self.service.check_network()
            start.assert_called_once_with("192.168.1.88", self.port, persist=False)
        self.assertFalse(self.service.enabled)
        self.assertEqual(len(self.store.list()), 1)
        self.interfaces[0]["address"] = "127.0.0.1"
        self.service.check_network()
        self.assertTrue(self.service.session("device:" + credential, "192.168.1.202")["remembered"])

    def test_max_eight_devices_forget_specific_all_and_failed_settings(self):
        names = []
        for index in range(8):
            _, device = self.store.register(self.documents.state()["root"], "a" * 64, "Phone " + str(index))
            names.append(device["id"])
        self.service.renew_pairing()
        self.assertEqual(self.request("/api/phone/pair", "POST", {"qrToken": self.service.state(False)["qrToken"], "remember": True})[0], 429)
        self.service.forget_devices({"id": names[0]})
        self.assertEqual(len(self.store.list()), 7)
        self.service.forget_devices({"all": True})
        self.assertEqual(self.store.list(), [])
        self.service.stop()
        with patch.object(self.store, "save_settings", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.service.start("127.0.0.1", self.port)
        self.assertFalse(self.service.enabled)

    def test_private_device_store_static_read_and_head_denied(self):
        self.remember()
        with patch.dict(os.environ, {"CODEX_CONTROL_DATA_DIR": str(self.base / "desktop-runtime"),
                "CODEX_CONTROL_PUBLISHER_STATE_FILE": str(self.base / "publisher.json")}):
            import world_console as desktop
        server = desktop.ConsoleHTTPServer(("127.0.0.1", 0), desktop.ConsoleHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        with patch.object(desktop, "APP_DIR", self.assets), patch.object(desktop, "PHONE_DEVICE_STORE", self.store):
            worker.start()
            try:
                for method in ("GET", "HEAD"):
                    for path in ("/cache/phone-private/phone-devices.sqlite3", "/%63ache/phone-private/phone-devices.sqlite3", "/cache/phone-private/", "/cache/phone-private/phone-devices.sqlite3-journal",
                                 "/CACHE/PHONE-PRIVATE/phone-devices.sqlite3", "/%43ACHE/PHONE-PRIVATE/phone-devices.sqlite3"):
                        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
                        try:
                            connection.request(method, path)
                            response = connection.getresponse()
                            self.assertEqual(response.status, 404, (method, path))
                            response.read()
                        finally:
                            connection.close()
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)

    def test_missing_network_identity_keeps_manual_pairing_and_fails_remember_closed(self):
        self.service.stop()
        self.interfaces[0]["fingerprint"] = ""
        state = self.service.start("127.0.0.1", self.port)
        self.assertTrue(state["enabled"])
        self.assertFalse(state["autoRestore"]["enabled"])
        self.assertFalse(state["autoRestore"]["networkAvailable"])
        self.assertTrue(state["autoRestore"]["error"])
        self.assertEqual(self.request("/api/phone/pair", "POST", {"code": state["pairingCode"], "remember": True})[0], 503)
        self.assertEqual(self.request("/api/phone/pair", "POST", {"code": state["pairingCode"], "remember": False})[0], 200)
        self.assertEqual(self.request("/api/phone/status")[1], {"paired": True})

    def test_top_level_pwa_navigation_can_load_shell_without_opening_cross_site_api(self):
        navigation = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
        for path in ("/", "/mobile.html?tab=transfer"):
            self.assertEqual(self.request(path, headers=navigation)[0], 200)
        self.assertEqual(self.request("/", "HEAD", headers=navigation)[0], 200)
        self.assertEqual(self.request("/", headers={**navigation, "Sec-Fetch-Dest": "iframe"})[0], 403)
        self.assertEqual(self.request("/api/phone/status", headers=navigation)[0], 403)
        self.assertEqual(self.request("/api/phone/pair", "POST", {"code": self.service.state(False)["pairingCode"]}, headers=navigation)[0], 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
