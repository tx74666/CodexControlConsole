"""Identify and hand off this local Console installation without killing processes."""
from __future__ import annotations

import errno
import http.client
import json
import math
import os
from pathlib import Path
import re
import socket
import time
import urllib.error
import urllib.request


SCAN_PORT_COUNT = 30
REQUEST_TIMEOUT = 0.35
MAX_RESPONSE_BYTES = 64 * 1024
STARTUP_LOCK_NAME = '.console-startup.lock'
ACTIVE_INSTANCE_HINT = Path('cache') / 'console-active-instance.json'
MAX_HINT_BYTES = 4096
_VERSION_PATTERN = re.compile(
    r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
    r'(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?'
    r'(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?'
)


class ConsoleInstanceError(RuntimeError):
    """A local instance cannot be identified or handed off safely."""


class StartupLockTimeout(ConsoleInstanceError):
    pass


class HandoffError(ConsoleInstanceError):
    pass


class InvalidVersionError(ConsoleInstanceError):
    pass


def version_tuple(version):
    """Return strict SemVer precedence; build metadata never changes precedence.

    Stable x.y.z and existing prereleases such as 0.0.0-dev are supported.
    Unknown formats, optional 'v' prefixes and leading-zero versions are rejected.
    """
    match = _VERSION_PATTERN.fullmatch(version) if isinstance(version, str) and len(version) <= 160 else None
    if match is None:
        raise InvalidVersionError(f'無法辨識 Console 版本：{version!r}')
    major, minor, patch, prerelease, _build = match.groups()
    identifiers = []
    for identifier in prerelease.split('.') if prerelease else []:
        if identifier.isdigit():
            if len(identifier) > 1 and identifier.startswith('0'):
                raise InvalidVersionError(f'無法辨識 Console 版本：{version!r}')
            identifiers.append((0, int(identifier)))
        else:
            identifiers.append((1, identifier))
    return int(major), int(minor), int(patch), int(prerelease is None), tuple(identifiers)


version_key = version_tuple


def compare_versions(left, right):
    before, after = version_tuple(left), version_tuple(right)
    return (before > after) - (before < after)


def _directory_key(value):
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise ConsoleInstanceError('Console 資料目錄必須是完整路徑。')
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ConsoleInstanceError('Console 資料目錄必須是完整路徑。')
    try:
        return os.path.normcase(str(path.resolve()))
    except (OSError, ValueError, RuntimeError) as exc:
        raise ConsoleInstanceError('無法確認 Console 資料目錄。') from exc


def _port(value):
    if type(value) is not int or not 1 <= value <= 65535:
        raise ConsoleInstanceError('Console 埠號必須在 1–65535 之間。')
    return value


def _timeout(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ConsoleInstanceError('等待時間必須是大於零的有限秒數。')
    return float(value)


class StartupLock:
    """Cross-process startup mutex keyed only by the canonical data directory.

    The port argument is retained for caller compatibility, but does not create a
    separate lock. The lock file stays in place after release to avoid unlink races.
    """
    def __init__(self, data_dir, port, timeout=30):
        self.data_dir = Path(_directory_key(data_dir))
        self.port = _port(port)
        self.timeout = _timeout(timeout)
        self.path = self.data_dir / STARTUP_LOCK_NAME
        self._file = None

    def __enter__(self):
        if self._file is not None:
            raise ConsoleInstanceError('同一個啟動鎖不能重複取得。')
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise ConsoleInstanceError('Console 啟動鎖不能是符號連結。')
        lock_file = self.path.open('a+b')
        try:
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b'\0')
                lock_file.flush()
            deadline = time.monotonic() + self.timeout
            while True:
                lock_file.seek(0)
                try:
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._file = lock_file
                    return self
                except OSError as exc:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise StartupLockTimeout(f'等待 Console 啟動鎖逾時（{self.timeout:g} 秒），未啟動另一個實例。') from exc
                    time.sleep(min(0.05, remaining))
        except BaseException:
            lock_file.close()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        lock_file, self._file = self._file, None
        if lock_file is not None:
            try:
                lock_file.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            finally:
                lock_file.close()
        return False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        # A loopback probe must never follow redirects to another port or network.
        return None


def _local_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _windows_listener_ports():
    """Read the local IPv4/IPv6 listener tables, or return None if unavailable.

    Some Windows network setups time out even for closed loopback ports. Kernel
    listener state both avoids slow empty-port probes and confirms port release.
    It is never used to infer a listener's Console identity.
    """
    if os.name != 'nt':
        return None
    try:
        import ctypes
        query = ctypes.WinDLL('iphlpapi').GetExtendedTcpTable
        query.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.c_int,
                          ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        query.restype = ctypes.c_uint32
        ports = set()
        # OWNER_PID_LISTENER rows: IPv4 has six DWORDs; IPv6 has two 16-byte
        # addresses plus six DWORDs. Local port is a network-order 16-bit value.
        for family, stride, port_offset in ((2, 24, 8), (23, 56, 20)):
            size = ctypes.c_uint32()
            result = query(None, ctypes.byref(size), False, family, 3, 0)
            if result not in (0, 122):
                return None
            for _attempt in range(3):
                if size.value < 4 or size.value > 16 * 1024 * 1024:
                    return None
                buffer = ctypes.create_string_buffer(size.value)
                result = query(buffer, ctypes.byref(size), False, family, 3, 0)
                if result != 122:
                    break
            if result != 0:
                return None
            raw = buffer.raw
            count = int.from_bytes(raw[:4], 'little')
            if 4 + count * stride > len(raw):
                return None
            for index in range(count):
                offset = 4 + index * stride + port_offset
                ports.add(socket.ntohs(int.from_bytes(raw[offset:offset + 4], 'little') & 0xffff))
        return ports
    except (OSError, AttributeError, ValueError):
        return None


def _request_json(opener, port, route, *, payload=None, timeout=REQUEST_TIMEOUT):
    url = f'http://127.0.0.1:{_port(port)}{route}'
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    headers = {'Accept': 'application/json', 'User-Agent': 'CodexConsole/InstanceHandoff'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, data=data, headers=headers, method='GET' if data is None else 'POST')
    with opener.open(request, timeout=timeout) as response:
        if not 200 <= response.status < 300 or response.headers.get_content_type() != 'application/json':
            raise ConsoleInstanceError('本機服務未返回 Console JSON 回應。')
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ConsoleInstanceError('本機 Console 回應超過大小上限。')
    result = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(result, dict):
        raise ConsoleInstanceError('本機服務未返回 Console 設定物件。')
    return result


def _active_instance_port(data_dir):
    """Read a bounded local hint; its port must still pass normal API identity checks."""
    try:
        root = Path(data_dir)
        path = (root / ACTIVE_INSTANCE_HINT).resolve()
        if not path.is_relative_to(root):
            return None
        with path.open('rb') as source:
            raw = source.read(MAX_HINT_BYTES + 1)
        if len(raw) > MAX_HINT_BYTES:
            return None
        payload = json.loads(raw.decode('utf-8-sig'))
        if not isinstance(payload, dict):
            return None
        return _port(payload.get('port'))
    except (ConsoleInstanceError, OSError, ValueError, UnicodeError, RecursionError, RuntimeError):
        return None


def find_running_console(start, data_dir, installation_id):
    """Probe only loopback config APIs and select this installation's newest version."""
    start = _port(start)
    directory = _directory_key(data_dir)
    if not isinstance(installation_id, str) or not installation_id.strip():
        raise ConsoleInstanceError('Console installationId 不能為空白。')
    opener = _local_opener()
    listening = _windows_listener_ports()
    found = None
    found_version = None
    hinted_port = _active_instance_port(directory)
    candidates = list(range(start, min(start + SCAN_PORT_COUNT, 65536)))
    if hinted_port is not None:
        # A valid hint wins version ties, preserving the existing browser origin.
        candidates = [hinted_port, *(port for port in candidates if port != hinted_port)]
    for port in candidates:
        if listening is not None and port not in listening:
            continue
        try:
            payload = _request_json(opener, port, '/api/console/config')
            runtime = payload.get('runtime')
            if not isinstance(runtime, dict) or runtime.get('installationId') != installation_id:
                continue
            if _directory_key(runtime.get('dataDirectory')) != directory:
                continue
            version = version_tuple(runtime.get('version'))
            if found is None or version > found_version:
                found, found_version = {'port': port, 'runtime': dict(runtime)}, version
        except (ConsoleInstanceError, OSError, ValueError, UnicodeError, RecursionError, urllib.error.URLError, http.client.HTTPException):
            continue
    return found


def _port_is_closed(port, timeout):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=timeout):
            return False
    except ConnectionRefusedError:
        return True
    except OSError as exc:
        # Timeouts and ambiguous networking errors do not prove the server stopped.
        if exc.errno in {errno.ECONNREFUSED, 10061}:
            return True
        listening = _windows_listener_ports()
        return listening is not None and port not in listening


def retire_older_instance(instance, new_version, timeout=10):
    """Request a supported older server to retire, then confirm its original port closed.

    No files are changed, no processes are killed and no alternate port is chosen.
    Returns True only after an accepted handoff and connection refusal on that port.
    """
    timeout = _timeout(timeout)
    if not isinstance(instance, dict) or not isinstance(instance.get('runtime'), dict):
        raise HandoffError('無法確認要交接的 Console 實例。')
    port = _port(instance.get('port'))
    runtime = instance['runtime']
    try:
        if compare_versions(new_version, runtime.get('version')) <= 0:
            raise HandoffError('只有較新的 Console 版本可以要求舊實例交接。')
    except InvalidVersionError as exc:
        raise HandoffError('Console 版本無法辨識，未要求舊實例退出。') from exc
    protocol, instance_id = runtime.get('handoffProtocol'), runtime.get('instanceId')
    if (type(protocol) is not int or protocol < 1 or not isinstance(instance_id, str)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{15,127}', instance_id)):
        raise HandoffError('舊版 Console 不支援安全交接，請先正常退出該版本；未強制結束程序。')
    deadline = time.monotonic() + timeout
    try:
        response = _request_json(_local_opener(), port, '/api/console/retire',
                                 payload={'expectedInstanceId': instance_id, 'version': new_version},
                                 timeout=min(REQUEST_TIMEOUT, timeout))
    except (ConsoleInstanceError, OSError, ValueError, UnicodeError, RecursionError, urllib.error.URLError, http.client.HTTPException) as exc:
        raise HandoffError(f'舊版 Console 未接受交接（埠 {port}）；未強制結束程序。') from exc
    if response.get('accepted') is not True:
        raise HandoffError(f'舊版 Console 拒絕交接（埠 {port}）；未啟動另一個實例。')
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HandoffError(f'等待舊版 Console 釋放埠 {port} 逾時；未強制結束程序或改用其他埠。')
        if _port_is_closed(port, min(REQUEST_TIMEOUT, remaining)):
            return True
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
