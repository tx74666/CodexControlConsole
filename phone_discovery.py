"""Selected physical-network identity and a bounded, local-only mDNS entrance.

The caller owns network selection and HTTP listener rebinding. This module
never scans addresses, changes routing, edits the firewall, or advertises
pairing credentials. A remembered network fingerprint excludes its DHCP IP.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import subprocess
import threading
import unicodedata
import uuid

try:
    from zeroconf import IPVersion, NonUniqueNameException, ServiceInfo, Zeroconf
except ImportError:
    IPVersion = ServiceInfo = Zeroconf = None

    class NonUniqueNameException(Exception):
        pass


SERVICE_TYPE = "_codex-console._tcp.local."
HOST_PATTERN = re.compile(r"codex-[a-f0-9]{12}\.local\Z")
_LAN_NETWORKS = tuple(ipaddress.IPv4Network(value) for value in
                      ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def _lan_address(value):
    try:
        address = ipaddress.IPv4Address(value)
        return str(address) if any(address in network for network in _LAN_NETWORKS) else ""
    except (ValueError, TypeError, ipaddress.AddressValueError):
        return ""


def local_hostname(computer_id):
    """Stable, pseudonymous hostname; never publish the installation identifier."""
    if (not isinstance(computer_id, str) or not computer_id or len(computer_id) > 160
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", computer_id)):
        raise ValueError("电脑标识无效。")
    return "codex-" + hashlib.sha256(computer_id.encode("ascii")).hexdigest()[:12] + ".local"


def network_fingerprint(interface):
    """Match the adapter and Windows network profile, independent of DHCP IP.

Windows' NetConnectionProfile.InstanceID is an adapter identifier, not a
separate network UUID. Consequently profile name and gateway are mandatory.
The neighbor cache is diagnostic metadata and never affects this identifier.
Missing identity fails closed; callers must not persist an empty fingerprint.
"""
    if not isinstance(interface, dict) or interface.get("hardwareInterface") is False:
        return ""
    try:
        adapter = str(uuid.UUID(str(interface.get("adapterGuid", ""))))
    except (ValueError, TypeError, AttributeError):
        return ""
    profile = interface.get("networkProfile")
    if not isinstance(profile, str):
        return ""
    profile = unicodedata.normalize("NFKC", profile).strip().casefold()
    if not profile or len(profile) > 256 or any(ord(char) < 32 for char in profile):
        return ""
    gateway = _lan_address(interface.get("gateway"))
    if not gateway:
        return ""
    identity = ["codex-console-network-v1", adapter, profile, gateway]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


_INTERFACE_SCRIPT = r"""$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$rows = @()
foreach ($adapter in (Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.HardwareInterface })) {
  $config = Get-NetIPConfiguration -InterfaceIndex $adapter.ifIndex
  $gateways = @($config.IPv4DefaultGateway | Where-Object { $_.NextHop -and $_.NextHop -ne '0.0.0.0' })
  $profiles = @(Get-NetConnectionProfile -InterfaceIndex $adapter.ifIndex -ErrorAction SilentlyContinue)
  $gateway = ''
  $profile = ''
  if ($gateways.Count -eq 1) { $gateway = [string]$gateways[0].NextHop }
  if ($profiles.Count -eq 1) { $profile = [string]$profiles[0].Name }
  $gatewayMac = ''
  if ($gateway) {
    $neighbor = @(Get-NetNeighbor -InterfaceIndex $adapter.ifIndex -IPAddress $gateway -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.State -in @('Reachable','Stale','Delay','Probe','Permanent') })
    if ($neighbor.Count -eq 1) { $gatewayMac = [string]$neighbor[0].LinkLayerAddress }
  }
  foreach ($address in $config.IPv4Address) {
    $rows += [PSCustomObject]@{
      address = [string]$address.IPAddress; name = [string]$adapter.Name
      adapterGuid = [string]$adapter.InterfaceGuid
      networkProfile = $profile; gateway = $gateway
      gatewayMac = $gatewayMac; hardwareInterface = $true
    }
  }
}
ConvertTo-Json -InputObject @($rows) -Compress
"""


def discover_lan_interfaces():
    """Read active physical IPv4 adapters and existing neighbor cache once."""
    if os.name != "nt":
        return []
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                                 _INTERFACE_SCRIPT], capture_output=True, encoding="utf-8",
                                timeout=12, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            return []
        rows = json.loads(result.stdout.lstrip("\ufeff"))
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            return []
        interfaces, seen = [], set()
        for row in rows:
            if not isinstance(row, dict) or row.get("hardwareInterface") is not True:
                continue
            address = _lan_address(row.get("address"))
            fingerprint = network_fingerprint(row)
            if not address or address in seen:
                continue
            seen.add(address)
            interfaces.append({"address": address, "name": str(row.get("name") or "Wi-Fi / Ethernet")[:80],
                               "fingerprint": fingerprint, "adapterGuid": row.get("adapterGuid", ""),
                               "networkProfile": row.get("networkProfile", ""), "gateway": row.get("gateway", ""),
                               "gatewayMac": row.get("gatewayMac", ""), "hardwareInterface": True})
        return interfaces
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        return []


class DiscoveryAnnouncer:
    """Own exactly one zeroconf instance, bound to the selected IPv4 interface."""
    def __init__(self):
        self._lock = threading.RLock()
        self._zeroconf = self._info = None
        self._state = {"available": False, "hostname": "", "status": "stopped", "error": ""}

    def state(self):
        with self._lock:
            return dict(self._state)

    def _stop_locked(self):
        instance, info = self._zeroconf, self._info
        self._zeroconf = self._info = None
        if instance is not None:
            try:
                if info is not None:
                    instance.unregister_service(info)
            except Exception:
                pass
            finally:
                try:
                    instance.close()
                except Exception:
                    pass

    def stop(self):
        with self._lock:
            self._stop_locked()
            self._state = {"available": False, "hostname": "", "status": "stopped", "error": ""}

    def start(self, hostname, host, port, version):
        with self._lock:
            self._stop_locked()
            self._state = {"available": False, "hostname": "", "status": "unavailable", "error": ""}
            address = _lan_address(host)
            if (not isinstance(hostname, str) or not HOST_PATTERN.fullmatch(hostname) or not address
                    or isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535
                    or not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version)):
                self._state["error"] = "自动发现地址无效，请使用电脑显示的手机地址。"
                return self.state()
            self._state["hostname"] = hostname
            if Zeroconf is None or ServiceInfo is None or IPVersion is None:
                self._state["error"] = "自动发现组件不可用，可重新扫码连接。"
                return self.state()
            instance = None
            try:
                instance = Zeroconf(interfaces=[address], ip_version=IPVersion.V4Only)
                name = "Codex Console " + hostname[6:18] + "." + SERVICE_TYPE
                info = ServiceInfo(SERVICE_TYPE, name, addresses=[socket.inet_aton(address)], port=port,
                                   properties={"version": version, "path": "/"}, server=hostname + ".",
                                   host_ttl=30, other_ttl=120)
                instance.register_service(info, allow_name_change=False)
                if info.name != name or info.server != hostname + ".":
                    instance.unregister_service(info)
                    raise NonUniqueNameException()
                self._zeroconf, self._info = instance, info
                instance = None
                self._state.update(available=True, status="announced", error="")
            except NonUniqueNameException:
                self._state.update(status="conflict", error="局域网名称冲突，请重新扫码连接。")
            except Exception:
                self._state["error"] = "当前网络的自动发现不可用，可重新扫码连接。"
            finally:
                if instance is not None:
                    try:
                        instance.close()
                    except Exception:
                        pass
            return self.state()
