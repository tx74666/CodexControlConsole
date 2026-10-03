"""Isolated discovery lifecycle checks; never advertise on a real network."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import phone_discovery as discovery


def interface(**changes):
    return {"address": "192.168.10.15", "name": "Wi-Fi", "hardwareInterface": True,
            "adapterGuid": "{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}",
            "networkProfile": "Home Wi-Fi", "gateway": "192.168.10.1", **changes}


class FakeInfo:
    def __init__(self, type_, name, **kwargs):
        self.type, self.name = type_, name
        self.__dict__.update(kwargs)


class FakeZeroconf:
    instances = []
    failure = None

    def __init__(self, **kwargs):
        self.options, self.registered, self.withdrawn = kwargs, [], []
        self.closed = False
        type(self).instances.append(self)

    def register_service(self, info, **kwargs):
        self.registered.append((info, kwargs))
        if type(self).failure:
            raise type(self).failure

    def unregister_service(self, info):
        self.withdrawn.append(info)

    def close(self):
        self.closed = True


class DiscoveryChecks(unittest.TestCase):
    def setUp(self):
        FakeZeroconf.instances, FakeZeroconf.failure = [], None
        self.patches = [patch.object(discovery, "Zeroconf", FakeZeroconf),
                        patch.object(discovery, "ServiceInfo", FakeInfo),
                        patch.object(discovery, "IPVersion", SimpleNamespace(V4Only="ipv4"))]
        for item in self.patches:
            item.start()
        self.announcer = discovery.DiscoveryAnnouncer()
        self.hostname = discovery.local_hostname("fixture-installation-id")

    def tearDown(self):
        self.announcer.stop()
        for item in reversed(self.patches):
            item.stop()

    def test_hostname_is_stable_unique_and_contains_no_identifier(self):
        self.assertEqual(self.hostname, discovery.local_hostname("fixture-installation-id"))
        self.assertNotEqual(self.hostname, discovery.local_hostname("second-installation-id"))
        self.assertRegex(self.hostname, r"^codex-[a-f0-9]{12}\.local$")
        self.assertNotIn("fixture", self.hostname)
        for invalid in (None, "", "private id", "token/secret", "x" * 161):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                discovery.local_hostname(invalid)

    def test_network_identity_survives_dhcp_and_rejects_network_changes(self):
        expected = discovery.network_fingerprint(interface())
        self.assertRegex(expected, r"^[a-f0-9]{64}$")
        self.assertEqual(expected, discovery.network_fingerprint(interface(address="192.168.10.99", name="renamed adapter")))
        self.assertEqual(expected, discovery.network_fingerprint(interface(adapterGuid="AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE", networkProfile=" home wi-fi ")))
        for changed in ({"gateway": "192.168.10.2"}, {"networkProfile": "Other Wi-Fi"},
                        {"adapterGuid": "bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee"}):
            self.assertNotEqual(expected, discovery.network_fingerprint(interface(**changed)))
        for cache in ("", "aa-bb-cc-dd-ee-ff", "AA:BB:CC:DD:EE:FF", "aa-bb-cc-dd-ee-fe", "00-00-00-00-00-00"):
            self.assertEqual(expected, discovery.network_fingerprint(interface(gatewayMac=cache)))
        for changed in ({"gateway": ""}, {"gateway": "8.8.8.8"}, {"networkProfile": ""},
                        {"adapterGuid": ""}, {"hardwareInterface": False}):
            self.assertEqual(discovery.network_fingerprint(interface(**changed)), "")

    def test_discovery_filters_virtual_public_duplicates_and_keeps_explicit_only_networks(self):
        import json
        rows = [interface(), interface(address="192.168.10.16", hardwareInterface=False),
                interface(address="192.168.10.17", gateway=""), interface(address="8.8.8.8"), interface()]
        result = SimpleNamespace(returncode=0, stdout="\ufeff" + json.dumps(rows))
        with patch.object(discovery.os, "name", "nt"), patch.object(discovery.subprocess, "run", return_value=result) as run:
            found = discovery.discover_lan_interfaces()
        self.assertEqual(len(found), 2)
        self.assertEqual(found[0]["address"], "192.168.10.15")
        self.assertEqual(found[0]["fingerprint"], discovery.network_fingerprint(interface()))
        self.assertEqual(found[1]["address"], "192.168.10.17")
        self.assertEqual(found[1]["fingerprint"], "")
        self.assertEqual(run.call_args.kwargs["timeout"], 12)
        self.assertIn("HardwareInterface", run.call_args.args[0][-1])
        self.assertNotIn("Test-Connection", run.call_args.args[0][-1])

    def test_announcement_uses_exact_interface_and_no_pairing_properties(self):
        state = self.announcer.start(self.hostname, "192.168.10.15", 8899, "1.0.25")
        self.assertTrue(state["available"])
        instance = FakeZeroconf.instances[0]
        self.assertEqual(instance.options, {"interfaces": ["192.168.10.15"], "ip_version": "ipv4"})
        info, options = instance.registered[0]
        self.assertEqual(info.properties, {"version": "1.0.25", "path": "/"})
        self.assertEqual(info.server, self.hostname + ".")
        self.assertEqual(options, {"allow_name_change": False})
        self.assertEqual(info.addresses, [b"\xc0\xa8\x0a\x0f"])
        snapshot = self.announcer.state()
        snapshot["available"] = False
        self.assertTrue(self.announcer.state()["available"])

    def test_rebind_withdraws_only_our_old_service_and_stop_is_idempotent(self):
        self.announcer.start(self.hostname, "192.168.10.15", 8899, "1.0.25")
        old = FakeZeroconf.instances[0]
        self.announcer.start(self.hostname, "192.168.10.99", 8899, "1.0.25")
        self.assertTrue(old.closed)
        self.assertEqual(len(old.withdrawn), 1)
        newest = FakeZeroconf.instances[-1]
        self.announcer.stop()
        self.announcer.stop()
        self.assertTrue(newest.closed)
        self.assertEqual(len(newest.withdrawn), 1)
        self.assertEqual(self.announcer.state()["status"], "stopped")

    def test_name_conflict_and_socket_failure_never_rename_or_leak_an_instance(self):
        for failure, status in ((discovery.NonUniqueNameException(), "conflict"), (OSError("blocked socket"), "unavailable")):
            FakeZeroconf.failure = failure
            result = self.announcer.start(self.hostname, "192.168.10.15", 8899, "1.0.25")
            self.assertFalse(result["available"])
            self.assertEqual(result["status"], status)
            self.assertTrue(FakeZeroconf.instances[-1].closed)
            self.assertFalse(self.announcer._zeroconf)
            self.assertEqual(FakeZeroconf.instances[-1].registered[0][1], {"allow_name_change": False})

    def test_missing_dependency_and_invalid_destinations_do_not_open_sockets(self):
        with patch.object(discovery, "Zeroconf", None):
            self.assertFalse(self.announcer.start(self.hostname, "192.168.10.15", 8899, "1.0.25")["available"])
        for hostname, host, port in (("other.local", "192.168.10.15", 8899), (self.hostname, "8.8.8.8", 8899),
                                     (self.hostname, "127.0.0.1", 8899), (self.hostname, "192.168.10.15", 0),
                                     (self.hostname, "192.168.10.15", True)):
            self.assertFalse(self.announcer.start(hostname, host, port, "1.0.25")["available"])
        self.assertEqual(FakeZeroconf.instances, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
