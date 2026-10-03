"""Local document browsing, a persistent report inbox and a fixed device sampler."""
from contextlib import contextmanager
import csv
import ctypes
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import uuid
from urllib.parse import unquote

import device_library


TEXT_EXTENSIONS = {'.md', '.txt', '.json', '.csv', '.log', '.ps1', '.py', '.cmd'}
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 1024 * 1024
IMAGE_MIME_TYPES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                    '.webp': 'image/webp', '.gif': 'image/gif'}
INBOX_FILE = '.document-inbox.json'
INBOX_LOCK_FILE = '.document-inbox.lock'
MAX_INBOX_ENTRIES = 5000
GUIDE_FILE = '.document-guide.json'
MAX_GUIDE_BYTES = 64 * 1024
MAX_GUIDE_ITEMS = 50
REFERENCES_FILE = '.document-references.json'
MAX_REFERENCE_BYTES = 128 * 1024
MAX_REFERENCE_ITEMS = 100
DEVICE_DETAILS_FILE = '.device-details.json'
MAX_DEVICE_DETAILS_BYTES = 16 * 1024
MAX_GPU_QUERY_BYTES = 64 * 1024
GPU_QUERY_TIMEOUT = 2.0


def document_image_path(target, document_path=''):
    """Resolve one Markdown image reference, without allowing URLs or root escape."""
    if not isinstance(target, str) or re.search(r'%(?![0-9a-fA-F]{2})', target):
        raise ValueError('圖片相對路徑無效。')
    try:
        value = unquote(target, errors='strict').replace('\\', '/')
    except (UnicodeError, ValueError) as exc:
        raise ValueError('圖片相對路徑無效。') from exc
    if not value or value.startswith('/') or re.search(r'[\x00-\x1f\x7f:?#]', value):
        raise ValueError('圖片只可使用資料庫內的相對路徑。')
    parts = document_path.replace('\\', '/').split('/')[:-1] if document_path else []
    for part in value.split('/'):
        if not part or part == '.':
            continue
        if part == '..':
            if not parts:
                raise ValueError('圖片路徑不可離開所選資料庫。')
            parts.pop()
        else:
            parts.append(part)
    if not parts or Path(parts[-1]).suffix.lower() not in IMAGE_MIME_TYPES:
        raise ValueError('圖片只支援 PNG、JPEG、WebP 或 GIF。')
    return '/'.join(parts)


def markdown_image_paths(source, document_path):
    """Collect the inline images displayed by our reader; code and URLs stay text."""
    fence = None
    for line in str(source).replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if fence:
            if re.fullmatch(r'\s{0,3}' + re.escape(fence[0]) + '{' + str(len(fence)) + r',}\s*', line):
                fence = None
            continue
        if marker:
            fence = marker.group(1)
            continue
        for match in re.finditer(r'`[^`\n]+`|!\[[^\]\n]*\]\((?:<[^>\n]+>|[^)\n]+)\)', line):
            token = match.group(0)
            if not token.startswith('!['):
                continue
            target = token[token.index('](') + 2:-1].strip()
            target = target[1:-1] if target.startswith('<') and target.endswith('>') else re.sub(r'\s+["\'][^"\']*["\']$', '', target)
            if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target) or target.startswith('//'):
                continue
            yield document_image_path(target, document_path)


def _text_value(value, limit=256):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        return None
    if any(ord(char) < 32 for char in value):
        return None
    return value.strip()


def _integer_value(value, *, positive=False):
    if type(value) is not int or value < (1 if positive else 0) or value > 2 ** 53 - 1:
        return None
    return value


def _nvidia_smi_path():
    """Only existing driver installation locations; never PATH or library files."""
    if os.name != 'nt':
        return None
    candidates = (Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'nvidia-smi.exe',
                  Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'NVIDIA Corporation' / 'NVSMI' / 'nvidia-smi.exe')
    for path in candidates:
        try:
            if not path.is_absolute() or not path.is_file():
                continue
            if any(part.is_symlink() or getattr(part, 'is_junction', lambda: False)() for part in (path, *path.parents)):
                continue
            return path
        except (OSError, RuntimeError):
            continue
    return None


def _gpu_query_output(driver):
    # Spool a fixed, two-second query to a temporary file rather than retaining
    # unbounded child output in memory. Read only the bounded result, then remove it.
    query = '--query-gpu=index,name,pci.bus_id,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu'
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen([str(driver), query, '--format=csv,noheader,nounits'],
                                   stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.DEVNULL,
                                   shell=False, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            try:
                process.wait(timeout=GPU_QUERY_TIMEOUT)
            except subprocess.TimeoutExpired:
                raise OSError('驅動顯存查詢超過 2 秒，已停止本次查詢。')
            if process.returncode:
                raise OSError('驅動顯存查詢失敗。')
            output.seek(0)
            raw = output.read(MAX_GPU_QUERY_BYTES + 1)
            if len(raw) > MAX_GPU_QUERY_BYTES:
                raise ValueError('驅動顯存查詢結果超過讀取限制。')
            return raw.decode('utf-8-sig')
        finally:
            if process.poll() is None:
                try:
                    process.kill()
                    process.wait(timeout=1)
                except (OSError, subprocess.SubprocessError):
                    pass


def _gpu_number(value, *, memory=False, low=0, high=100):
    if not re.fullmatch(r'-?\d+(?:\.\d+)?', value.strip()):
        return None
    number = float(value)
    if not math.isfinite(number) or number < low or number > high:
        return None
    if memory:
        converted = int(number * 1048576)
        return converted if converted <= 2 ** 53 - 1 else None
    return number


def _windows_storage_volumes():
    """Native fixed-volume enumeration, no filesystem walk and no drive details output."""
    if os.name != 'nt':
        raise OSError('此系統尚未提供本機存儲讀取。')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetLogicalDrives.argtypes, kernel.GetLogicalDrives.restype = [], ctypes.c_uint32
    kernel.GetDriveTypeW.argtypes, kernel.GetDriveTypeW.restype = [ctypes.c_wchar_p], ctypes.c_uint32
    kernel.GetVolumeNameForVolumeMountPointW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    kernel.GetVolumeNameForVolumeMountPointW.restype = ctypes.c_int
    kernel.GetDiskFreeSpaceExW.argtypes = [ctypes.c_wchar_p, *([ctypes.POINTER(ctypes.c_uint64)] * 3)]
    kernel.GetDiskFreeSpaceExW.restype = ctypes.c_int
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                  ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.DeviceIoControl.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32,
                                      ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
    kernel.DeviceIoControl.restype = ctypes.c_int
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [ctypes.c_void_p], ctypes.c_int

    class StoragePropertyQuery(ctypes.Structure):
        _fields_ = [('propertyId', ctypes.c_uint32), ('queryType', ctypes.c_uint32), ('additional', ctypes.c_ubyte)]

    class StorageDeviceDescriptor(ctypes.Structure):
        _fields_ = [('version', ctypes.c_uint32), ('size', ctypes.c_uint32),
                    ('deviceType', ctypes.c_ubyte), ('deviceTypeModifier', ctypes.c_ubyte),
                    ('removable', ctypes.c_ubyte), ('queueing', ctypes.c_ubyte),
                    ('vendorOffset', ctypes.c_uint32), ('productOffset', ctypes.c_uint32),
                    ('revisionOffset', ctypes.c_uint32), ('serialOffset', ctypes.c_uint32),
                    ('busType', ctypes.c_uint32), ('rawLength', ctypes.c_uint32), ('raw', ctypes.c_ubyte)]

    mask = kernel.GetLogicalDrives()
    if not mask:
        raise OSError('無法列出本機固定卷。')
    records, seen = [], set()
    for index in range(26):
        if not mask & (1 << index):
            continue
        mount = chr(65 + index) + ':\\'
        drive_type = kernel.GetDriveTypeW(mount)
        if drive_type != 3:
            if drive_type in (0, 1):
                records.append({'error': True})
            continue
        identity = ctypes.create_unicode_buffer(64)
        if not kernel.GetVolumeNameForVolumeMountPointW(mount, identity, len(identity)) or not identity.value:
            records.append({'error': True})
            continue
        volume_id = identity.value.casefold()
        if volume_id in seen:
            continue
        seen.add(volume_id)
        handle = kernel.CreateFileW(identity.value.rstrip('\\'), 0, 3, None, 3, 0, None)
        if handle in (None, ctypes.c_void_p(-1).value):
            records.append({'error': True})
            continue
        try:
            query = StoragePropertyQuery()
            buffer = ctypes.create_string_buffer(4096)
            returned = ctypes.c_uint32()
            ok = kernel.DeviceIoControl(handle, 0x2D1400, ctypes.byref(query), ctypes.sizeof(query),
                                        buffer, len(buffer), ctypes.byref(returned), None)
            if not ok or returned.value < StorageDeviceDescriptor.busType.offset + 4:
                records.append({'error': True})
                continue
            descriptor = ctypes.cast(buffer, ctypes.POINTER(StorageDeviceDescriptor)).contents
            if descriptor.version < 32 or descriptor.size < 32:
                records.append({'error': True})
                continue
            bus_type = descriptor.busType
        finally:
            kernel.CloseHandle(handle)
        # Positive local-bus allowlist. Unknown/virtual/RAID/network backing is
        # not assumed internal; USB (7) and other known external buses are omitted.
        if bus_type in {4, 6, 7, 9, 12, 20}:
            continue
        if bus_type not in {1, 2, 3, 10, 11, 13, 17, 19}:
            records.append({'error': True})
            continue
        available, total, free = ctypes.c_uint64(), ctypes.c_uint64(), ctypes.c_uint64()
        if not kernel.GetDiskFreeSpaceExW(mount, ctypes.byref(available), ctypes.byref(total), ctypes.byref(free)):
            records.append({'error': True})
            continue
        # Match caller-visible total with caller-available bytes (quotas may apply).
        records.append({'identity': volume_id, 'totalBytes': total.value, 'freeBytes': available.value})
    return records


def current_storage():
    result = {'readAt': datetime.now().astimezone().isoformat(), 'status': 'unavailable',
              'totalBytes': None, 'usedBytes': None, 'freeBytes': None,
              'source': 'GetDiskFreeSpaceExW (current-user fixed volumes)', 'reason': ''}
    try:
        records = _windows_storage_volumes()
        total, free, read_count, incomplete, seen = 0, 0, 0, len(records) > 26, set()
        for record in records[:26]:
            if record.get('error'):
                incomplete = True
                continue
            identity = record.get('identity')
            size, available = _integer_value(record.get('totalBytes'), positive=True), _integer_value(record.get('freeBytes'))
            if not isinstance(identity, str) or not identity or size is None or available is None or available > size:
                incomplete = True
                continue
            if identity.casefold() in seen:
                continue
            seen.add(identity.casefold())
            total, free, read_count = total + size, free + available, read_count + 1
        if read_count:
            if _integer_value(total, positive=True) is None or _integer_value(free) is None:
                raise ValueError('匯總存儲容量超出有效數值範圍。')
            result.update({'status': 'partial' if incomplete else 'available', 'totalBytes': total,
                           'freeBytes': free, 'usedBytes': total - free,
                           'reason': '部分固定卷無法讀取；僅彙總已確認的內置卷。' if incomplete else ''})
        else:
            result['reason'] = '未取得可用的內置固定卷資料。'
    except (OSError, AttributeError, ValueError, TypeError, RuntimeError):
        result['reason'] = '本機存儲暫時無法讀取；未知容量不以 0 代替。'
    return result


def current_gpu():
    """One bounded, read-only driver query per overview; no saved usage fallback."""
    result = {'readAt': datetime.now().astimezone().isoformat(), 'status': 'unavailable',
              'source': 'nvidia-smi', 'reason': '', 'adapters': []}
    try:
        driver = _nvidia_smi_path()
        if driver is None:
            result['reason'] = '未找到受支援的 NVIDIA 驅動接口；目前顯存用量不可用。'
            return result
        rows = list(csv.reader(_gpu_query_output(driver).splitlines(), skipinitialspace=True))
        rows = [row for row in rows if any(value.strip() for value in row)]
        if not rows or len(rows) > 32:
            raise ValueError('未取得有效的驅動顯卡清單。')
        adapters, seen = [], set()
        for row in rows:
            if len(row) != 8:
                raise ValueError('驅動顯卡欄位格式無效。')
            index, name, pci, total, used, free, utilization, temperature = (value.strip() for value in row)
            name = _text_value(name)
            if name is None or not re.fullmatch(r'\d{1,4}', index):
                raise ValueError('驅動顯卡識別資料無效。')
            adapter_id = ('pci:' + pci.casefold() if re.fullmatch(r'(?:[\da-fA-F]{4}|[\da-fA-F]{8}):[\da-fA-F]{2}:[\da-fA-F]{2}\.[0-7]', pci)
                          else 'nvidia:' + index)
            if adapter_id in seen:
                raise ValueError('驅動顯卡識別資料重複。')
            seen.add(adapter_id)
            total_bytes = _gpu_number(total, memory=True, low=1 / 1048576, high=(2 ** 53 - 1) / 1048576)
            used_bytes = _gpu_number(used, memory=True, high=(2 ** 53 - 1) / 1048576)
            free_bytes = _gpu_number(free, memory=True, high=(2 ** 53 - 1) / 1048576)
            if total_bytes is not None:
                if used_bytes is not None and used_bytes > total_bytes:
                    used_bytes = None
                if free_bytes is not None and free_bytes > total_bytes:
                    free_bytes = None
            available = all(value is not None for value in (total_bytes, used_bytes, free_bytes))
            adapters.append({'adapterId': adapter_id, 'name': name, 'readAt': result['readAt'],
                             'status': 'available' if available else 'partial', 'totalBytes': total_bytes,
                             'usedBytes': used_bytes, 'freeBytes': free_bytes, 'source': 'nvidia-smi',
                             'utilizationPercent': _gpu_number(utilization),
                             'temperatureC': _gpu_number(temperature, low=-100, high=200),
                             'reason': '' if available else '部分顯存指標無法讀取；未知數值不以 0 代替。'})
        result['adapters'] = adapters
        result['status'] = 'available' if all(item['status'] == 'available' for item in adapters) else 'partial'
        result['reason'] = '' if result['status'] == 'available' else '部分顯卡顯存指標不可用。'
    except (OSError, ValueError, UnicodeError, csv.Error, subprocess.SubprocessError) as exc:
        result['reason'] = str(exc)
    return result


def _hardware_rows(value, kind):
    if not isinstance(value, list):
        return []
    rows = []
    for item in value[:32]:
        if not isinstance(item, dict):
            continue
        if kind == 'cpus':
            rows.append({'name': _text_value(item.get('name')), 'cores': _integer_value(item.get('cores'), positive=True),
                         'logicalProcessors': _integer_value(item.get('logicalProcessors'), positive=True)})
        elif kind == 'memoryModules':
            rows.append({'capacityBytes': _integer_value(item.get('capacityBytes'), positive=True),
                         'speedMHz': _integer_value(item.get('speedMHz'), positive=True),
                         'configuredSpeedMHz': _integer_value(item.get('configuredSpeedMHz'), positive=True)})
        elif kind == 'gpus':
            rows.append({'name': _text_value(item.get('name')), 'driverVersion': _text_value(item.get('driverVersion'), 128),
                         'dedicatedCapacityBytes': _integer_value(item.get('dedicatedCapacityBytes'), positive=True),
                         'capacityReason': _text_value(item.get('capacityReason'), 512)})
    return rows


def _windows_memory_values():
    """Read physical memory once, without a process scan or sampler subprocess."""
    if os.name != 'nt':
        raise OSError('此系統尚未提供即時記憶體讀取。')

    class MemoryStatus(ctypes.Structure):
        _fields_ = [('length', ctypes.c_uint32), ('load', ctypes.c_uint32),
                    ('totalPhysical', ctypes.c_uint64), ('availablePhysical', ctypes.c_uint64),
                    ('totalPageFile', ctypes.c_uint64), ('availablePageFile', ctypes.c_uint64),
                    ('totalVirtual', ctypes.c_uint64), ('availableVirtual', ctypes.c_uint64),
                    ('availableExtendedVirtual', ctypes.c_uint64)]

    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    query = kernel.GlobalMemoryStatusEx
    query.argtypes = [ctypes.POINTER(MemoryStatus)]
    query.restype = ctypes.c_int
    if not query(ctypes.byref(status)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not status.totalPhysical or status.availablePhysical > status.totalPhysical:
        raise OSError('系統返回的記憶體數值無效。')
    return {'availableBytes': status.availablePhysical, 'totalBytes': status.totalPhysical,
            'usedPercent': status.load}


def current_memory():
    result = {'readAt': datetime.now().astimezone().isoformat(), 'status': 'unavailable',
              'availableBytes': None, 'totalBytes': None, 'usedBytes': None,
              'usedPercent': None, 'source': 'GlobalMemoryStatusEx', 'reason': ''}
    try:
        values = _windows_memory_values()
        total, available = _integer_value(values.get('totalBytes'), positive=True), _integer_value(values.get('availableBytes'))
        if total is None or available is None or available > total:
            raise ValueError('系統記憶體數值無效。')
        result.update(values)
        result['usedBytes'] = total - available
        result['status'] = 'available'
    except (OSError, AttributeError, ValueError) as exc:
        result['reason'] = f'即時記憶體暫時無法讀取：{exc}'
    return result


class DocumentLibraryService:
    def __init__(self, settings_file):
        self.settings_file = Path(settings_file)
        self._lock = threading.RLock()
        self._root_context = threading.local()
        self._worker = None
        self._job = None
        self._cancel_event = None

    def _settings(self):
        try:
            value = json.loads(self.settings_file.read_text(encoding='utf-8'))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def state(self):
        with self._lock:
            root = str(self._settings().get('root') or '')
            exists = bool(root and Path(root).is_dir())
            return {'root': root, 'exists': exists,
                    'error': '資料夾已移動、無法存取或不存在，請重新選擇。' if root and not exists else ''}

    def _root(self):
        pinned = getattr(self._root_context, 'root', None)
        if pinned is not None:
            return pinned
        state = self.state()
        if not state['exists']:
            raise ValueError(state['error'] or '請先開啟一個資料夾。')
        return Path(state['root']).resolve()

    @contextmanager
    def _document_scope(self, expectedRoot=None):
        """Validate the selected root and pin every nested path lookup to that root.

        The local lock serializes same-process selection changes. The thread-local
        pin also prevents another process changing settings midway through a read
        or inbox write from redirecting the rest of this operation to another root.
        expectedRoot is a comparison only; it never selects or grants a new root.
        """
        with self._lock:
            previous = getattr(self._root_context, 'root', None)
            root = self._root()
            if expectedRoot is not None:
                if not isinstance(expectedRoot, (str, os.PathLike)) or not str(expectedRoot).strip():
                    raise ValueError('閱讀器資料庫路徑無效，請從主視窗重新開啟文件。')
                expected = Path(expectedRoot)
                if not expected.is_absolute():
                    raise ValueError('閱讀器資料庫路徑無效，請從主視窗重新開啟文件。')
                try:
                    matches = expected.resolve() == root
                except (OSError, ValueError, RuntimeError) as exc:
                    raise ValueError('閱讀器資料庫路徑無效，請從主視窗重新開啟文件。') from exc
                if not matches:
                    raise ValueError('資料庫已切換，請從主視窗重新開啟文件。')
            self._root_context.root = root
            try:
                yield root
            finally:
                self._root_context.root = previous

    def _path(self, relative=''):
        root = self._root()
        path = Path(str(relative or ''))
        if path.is_absolute() or path.drive or '..' in path.parts or any(':' in part for part in path.parts):
            raise ValueError('只可讀取所選資料夾內的相對路徑。')
        resolved = (root / path).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError('檔案連結指向所選資料夾之外。')
        return root, resolved

    def _busy(self):
        if self._worker and self._worker.is_alive():
            return True
        state = self.state()
        return bool(state['exists'] and device_library.status(state['root']).get('status') == 'running')

    def select(self, path=None):
        with self._lock:
            if self._busy():
                raise ValueError('請先等採樣完成或取消，再切換資料夾。')
            if path is None or not str(path).strip():
                path = self._choose_folder()
                if not path:
                    return {**self.state(), 'cancelled': True}
            candidate = Path(str(path).strip()).expanduser()
            if not candidate.is_absolute() or str(candidate).startswith('\\\\'):
                raise ValueError('請選擇本機的完整資料夾路徑。')
            candidate = candidate.resolve()
            if not candidate.is_dir():
                raise ValueError('資料夾不存在或無法讀取，原選擇已保留。')
            # Check permissions before replacing the last usable choice.
            next(candidate.iterdir(), None)
            config = self._settings()
            config['root'] = str(candidate)
            config['updatedAt'] = datetime.now(timezone.utc).isoformat()
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.settings_file.with_name(self.settings_file.name + '.' + uuid.uuid4().hex + '.tmp')
            try:
                temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
                os.replace(temporary, self.settings_file)
            finally:
                temporary.unlink(missing_ok=True)
            self._job = None
            return self.state()

    @staticmethod
    def _choose_folder():
        if os.name != 'nt':
            raise ValueError('此系統請在路徑欄貼上本機資料夾路徑。')
        command = """[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Windows.Forms
$picker = New-Object System.Windows.Forms.FolderBrowserDialog
$picker.Description = 'Document - Open local folder'
$picker.ShowNewFolderButton = $false
try { if ($picker.ShowDialog() -eq 'OK') { $picker.SelectedPath | ConvertTo-Json -Compress } }
finally { $picker.Dispose() }
"""
        try:
            result = subprocess.run(['powershell.exe', '-NoProfile', '-STA', '-Command', command],
                                    capture_output=True, encoding='utf-8', timeout=120,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired as exc:
            raise ValueError('選擇資料夾已逾時，請重試或貼上路徑。') from exc
        if result.returncode:
            raise ValueError('無法開啟系統資料夾選擇器，請貼上路徑。')
        return json.loads(result.stdout.lstrip('\ufeff')) if result.stdout.strip() else None

    def list(self, relative=''):
        root, directory = self._path(relative)
        if not directory.is_dir():
            raise ValueError('資料夾已不存在，請刷新。')
        entries = []
        truncated = False
        for item in directory.iterdir():
            if item.name.startswith('.'):
                continue
            try:
                if not item.resolve().is_relative_to(root):
                    continue
                is_directory = item.is_dir()
                if not is_directory and item.suffix.lower() not in TEXT_EXTENSIONS:
                    continue
                if len(entries) >= 2000:
                    truncated = True
                    break
                entries.append({'name': item.name, 'path': item.relative_to(root).as_posix(),
                                'isDirectory': is_directory})
            except OSError:
                continue
        entries.sort(key=lambda item: (not item['isDirectory'], item['name'].casefold() != 'readme.md', item['name'].casefold()))
        return {'root': str(root), 'path': '' if directory == root else directory.relative_to(root).as_posix(),
                'entries': entries, 'truncated': truncated,
                'error': '資料夾項目超過 2,000，僅顯示前 2,000 項。' if truncated else ''}

    def read(self, relative, expectedRoot=None):
        with self._document_scope(expectedRoot):
            return self._read_document(relative)

    def image(self, relative, expectedRoot=None):
        """Read a bounded library image, with the same selected-root pin as text."""
        if expectedRoot is None:
            raise ValueError('讀取圖片需要目前資料庫位置，請從主視窗重新開啟。')
        if not isinstance(relative, str) or re.search(r'[\x00-\x1f\x7f:?#]', relative):
            raise ValueError('圖片相對路徑無效。')
        with self._document_scope(expectedRoot) as root:
            _, path = self._path(relative)
            mime = IMAGE_MIME_TYPES.get(path.suffix.lower())
            if not path.is_file() or not mime:
                raise ValueError('圖片只支援資料庫內的 PNG、JPEG、WebP 或 GIF。')
            with path.open('rb') as source:
                content = source.read(MAX_IMAGE_BYTES + 1)
            if len(content) > MAX_IMAGE_BYTES:
                raise ValueError('單張圖片超過 1 MiB，請先保存較小的閱讀副本。')
            valid = ((mime == 'image/png' and content.startswith(b'\x89PNG\r\n\x1a\n'))
                     or (mime == 'image/jpeg' and content.startswith(b'\xff\xd8\xff'))
                     or (mime == 'image/gif' and content[:6] in (b'GIF87a', b'GIF89a'))
                     or (mime == 'image/webp' and len(content) >= 12
                         and content[:4] == b'RIFF' and content[8:12] == b'WEBP'))
            if not valid:
                raise ValueError('圖片內容與副檔名不符，請重新保存 PNG、JPEG、WebP 或 GIF。')
            return {'root': str(root), 'path': Path(relative).as_posix(),
                    'mimeType': mime, 'content': content}

    def _read_document(self, relative):
        root, path = self._path(relative)
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            raise ValueError('只支援 Markdown、JSON 及文字資料；不會執行文件或腳本。')
        with path.open('rb') as source:
            content = source.read(MAX_TEXT_BYTES + 1)
        if len(content) > MAX_TEXT_BYTES:
            raise ValueError('文件超過 2 MiB，請用本機文字編輯器查看。')
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError('此文件不是 UTF-8 文字，請用本機文字編輯器查看。') from exc
        return {'root': str(root), 'path': path.relative_to(root).as_posix(), 'name': path.name,
                'content': text, 'format': 'markdown' if path.suffix.lower() == '.md' else 'text',
                'modifiedAt': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()}

    def guide(self, expectedRoot=None):
        """Read an optional human guide manifest without inferring items from README."""
        with self._document_scope(expectedRoot) as root:
            try:
                _, manifest = self._path(GUIDE_FILE)
                if not manifest.exists():
                    return {'root': str(root), 'items': []}
                with manifest.open('rb') as source:
                    raw = source.read(MAX_GUIDE_BYTES + 1)
                if len(raw) > MAX_GUIDE_BYTES:
                    raise ValueError('導覽設定超過 64 KiB。')
                data = json.loads(raw.decode('utf-8-sig'))
                if (not isinstance(data, dict) or type(data.get('version')) is not int
                        or data['version'] != 1 or not isinstance(data.get('items'), list)):
                    raise ValueError('請使用 version: 1 與 items 清單。')
                if len(data['items']) > MAX_GUIDE_ITEMS:
                    raise ValueError('導覽項目請保持在 50 項以內。')
                items, readable_paths = [], {}
                for index, item in enumerate(data['items'], 1):
                    if not isinstance(item, dict):
                        raise ValueError(f'第 {index} 個導覽項目必須是物件。')
                    relative = self._inbox_text(item.get('path'), f'第 {index} 項路徑', 1024)
                    title = self._inbox_text(item.get('title'), f'第 {index} 項標題', 160)
                    summary = self._inbox_text(item.get('summary'), f'第 {index} 項摘要', 600, required=False)
                    highlights = item.get('highlights')
                    if not isinstance(highlights, list) or len(highlights) > 8:
                        raise ValueError(f'第 {index} 項 highlights 請使用最多 8 個重點的清單。')
                    highlights = [self._inbox_text(value, f'第 {index} 項重點', 240) for value in highlights]
                    if relative not in readable_paths:
                        # Reuse the bounded UTF-8 reader and its path/link boundary;
                        # never return the full document body with the guide list.
                        readable_paths[relative] = self._read_document(relative)['path']
                    items.append({'path': readable_paths[relative], 'title': title,
                                  'summary': summary, 'highlights': highlights})
                return {'root': str(root), 'items': items}
            except (ValueError, OSError, UnicodeError, RuntimeError) as exc:
                raise ValueError(f'無法讀取重點導覽設定，原檔案未更動：{exc}') from exc

    def references(self, module=None, expectedRoot=None):
        """A read-only catalog of documents with paired language variants.

        Catalog entries are durable references, not inbox reports. Missing or
        unreadable document variants remain visible with availability metadata;
        an invalid manifest or escaping path is rejected without rewriting it.
        """
        if module is not None and (not isinstance(module, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', module)):
            raise ValueError('文件模組名稱無效。')
        with self._document_scope(expectedRoot) as root:
            try:
                _, manifest = self._path(REFERENCES_FILE)
                if not manifest.exists():
                    return {'root': str(root), 'items': []}
                with manifest.open('rb') as source:
                    raw = source.read(MAX_REFERENCE_BYTES + 1)
                if len(raw) > MAX_REFERENCE_BYTES:
                    raise ValueError('參考文件索引超過 128 KiB。')
                data = json.loads(raw.decode('utf-8-sig'))
                if (not isinstance(data, dict) or type(data.get('version')) is not int
                        or data['version'] != 1 or not isinstance(data.get('items'), list)
                        or len(data['items']) > MAX_REFERENCE_ITEMS):
                    raise ValueError('請使用 version: 1 與最多 100 項的 items 清單。')
                items, identifiers = [], set()
                for item in data['items']:
                    if not isinstance(item, dict):
                        raise ValueError('參考文件項目必須是物件。')
                    identifier = self._inbox_id(item.get('id'))
                    category = item.get('module')
                    if identifier in identifiers or not isinstance(category, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', category):
                        raise ValueError('參考文件 id 重複或模組名稱無效。')
                    identifiers.add(identifier)
                    variants = item.get('variants')
                    if not isinstance(variants, list) or not 1 <= len(variants) <= 2:
                        raise ValueError('每份參考文件支援中文與 English 兩種語言。')
                    normalized, languages, paths = [], set(), set()
                    for variant in variants:
                        if not isinstance(variant, dict):
                            raise ValueError('語言版本必須是物件。')
                        language = variant.get('language')
                        if (language not in ('zh-CN', 'en')
                                or language.casefold() in languages):
                            raise ValueError('文件語言無效或重複。')
                        languages.add(language.casefold())
                        relative = self._inbox_text(variant.get('path'), '文件路徑', 1024)
                        _, path = self._path(relative)
                        if path.suffix.lower() != '.md' or str(path).casefold() in paths:
                            raise ValueError('每種語言需要不同的 Markdown 文件路徑。')
                        paths.add(str(path).casefold())
                        record = {'language': language,
                                  'label': self._inbox_text(variant.get('label'), '語言標籤', 40),
                                  'title': self._inbox_text(variant.get('title'), '文件標題', 160),
                                  'summary': self._inbox_text(variant.get('summary', ''), '文件摘要', 600, required=False),
                                  'path': path.relative_to(root).as_posix(), 'available': False, 'error': ''}
                        try:
                            self._read_document(relative)
                            record['available'] = True
                        except (ValueError, OSError, UnicodeError, RuntimeError) as exc:
                            record['error'] = str(exc)
                        normalized.append(record)
                    default = item.get('defaultLanguage')
                    if default not in [variant['language'] for variant in normalized]:
                        raise ValueError('預設語言必須對應一個文件版本。')
                    if module is None or category == module:
                        items.append({'id': identifier, 'module': category, 'defaultLanguage': default, 'variants': normalized})
                return {'root': str(root), 'items': items}
            except (ValueError, OSError, UnicodeError, RuntimeError) as exc:
                raise ValueError(f'無法讀取參考文件索引，原檔案未更動：{exc}') from exc

    @staticmethod
    def _inbox_text(value, label, maximum, required=True):
        if not isinstance(value, str):
            raise ValueError(f'{label}必須是文字。')
        value = value.strip()
        if (required and not value) or len(value) > maximum or any(ord(char) < 32 for char in value):
            raise ValueError(f'{label}請使用 {maximum} 字以內的單行文字。')
        return value

    @staticmethod
    def _inbox_id(value):
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,159}', value):
            raise ValueError('報告 id 請使用 1–160 位英數字、點、底線、冒號或連字號。')
        return value

    @staticmethod
    def _inbox_date(value):
        if not isinstance(value, str) or len(value) > 40:
            raise ValueError('報告日期請使用 ISO 8601 日期或含時區的時間。')
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if len(value) != 10 and parsed.tzinfo is None:
                raise ValueError()
        except ValueError as exc:
            raise ValueError('報告日期請使用 ISO 8601 日期或含時區的時間。') from exc
        return value

    @staticmethod
    def _undo_token(value):
        if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value):
            raise ValueError('復原代碼無效，請使用清單操作提供的復原按鈕。')
        return value

    def _inbox_report_path(self, relative):
        if not isinstance(relative, str):
            raise ValueError('報告路徑必須是資料庫內的相對路徑。')
        root, path = self._path(relative)
        normalized = path.relative_to(root)
        if len(normalized.parts) < 2 or normalized.parts[0] != 'reports' or path.suffix.lower() != '.md':
            raise ValueError('收件箱只登記目前資料庫 reports 資料夾內的 Markdown 報告。')
        return normalized.as_posix()

    def _inbox_storage_path(self, name):
        root, path = self._path(name)
        if path != root / name:
            raise ValueError('收件箱索引與鎖定檔案不能是指向其他檔案的連結。')
        return path

    def _inbox_entries(self):
        path = self._inbox_storage_path(INBOX_FILE)
        if not path.exists():
            return []
        try:
            with path.open('rb') as source:
                raw = source.read(MAX_TEXT_BYTES + 1)
            if len(raw) > MAX_TEXT_BYTES:
                raise ValueError('收件箱索引超過 2 MiB。')
            data = json.loads(raw.decode('utf-8-sig'))
            if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('entries'), list):
                raise ValueError('收件箱索引格式不支援。')
            entries = data['entries']
            if len(entries) > MAX_INBOX_ENTRIES:
                raise ValueError('收件箱索引項目過多。')
            ids = set()
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError('收件箱項目格式有誤。')
                identifier = self._inbox_id(entry.get('id'))
                if identifier in ids:
                    raise ValueError('收件箱索引包含重複 id。')
                ids.add(identifier)
                self._inbox_text(entry.get('title'), '報告標題', 240)
                self._inbox_text(entry.get('summary'), '報告摘要', 2000, required=False)
                self._inbox_text(entry.get('source'), '報告來源', 240)
                self._inbox_report_path(entry.get('path'))
                self._inbox_date(entry.get('createdAt'))
                self._inbox_date(entry.get('registeredAt'))
                if type(entry.get('read')) is not bool:
                    raise ValueError('收件箱已讀狀態格式有誤。')
                if entry['read']:
                    self._inbox_date(entry.get('readAt'))
                elif entry.get('readAt') is not None:
                    raise ValueError('未讀項目不能含已讀時間。')
                # Version 1 before Archive had only read/readAt. Normalize in
                # memory; a GET must not rewrite the user's existing registry.
                status = entry.get('status', 'archive' if entry['read'] else 'inbox')
                if not isinstance(status, str) or status not in {'inbox', 'later', 'archive', 'cleared'}:
                    raise ValueError('收件箱項目狀態格式有誤。')
                if entry['read'] != (status in {'archive', 'cleared'}):
                    raise ValueError('收件箱項目狀態與已讀標記不一致。')
                entry['status'] = status
                if status == 'cleared':
                    self._undo_token(entry.get('clearBatch'))
                    self._inbox_date(entry.get('clearedAt'))
                elif entry.get('clearBatch') is not None or entry.get('clearedAt') is not None:
                    raise ValueError('未清除的項目不能含清除批次資料。')
            return entries
        except (ValueError, UnicodeError, OSError) as exc:
            raise ValueError(f'無法讀取收件箱索引，原檔案已保留：{exc}') from exc

    @contextmanager
    def _inbox_write_lock(self):
        # An advisory lock also protects concurrent source and installed servers.
        # It releases automatically on process exit, so there is no stale lock owner.
        path = self._inbox_storage_path(INBOX_LOCK_FILE)
        with path.open('a+b') as lock_file:
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b'\0')
                lock_file.flush()
            lock_file.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ValueError('另一個 Console 正在更新收件箱，請稍後重試。') from exc
            try:
                yield
            finally:
                lock_file.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _save_inbox(self, entries):
        path = self._inbox_storage_path(INBOX_FILE)
        content = json.dumps({'version': 1, 'entries': entries}, ensure_ascii=False, indent=2).encode('utf-8')
        if len(content) > MAX_TEXT_BYTES:
            raise ValueError('收件箱索引已達 2 MiB 上限，未更改原始索引。')
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            with temporary.open('xb') as destination:
                destination.write(content)
                destination.flush()
                os.fsync(destination.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _inbox_result(self, entries):
        visible = [entry for entry in entries if entry['status'] != 'cleared']
        return {'root': str(self._root()),
                'entries': sorted(visible, key=lambda item: (item['createdAt'], item['registeredAt'], item['id']), reverse=True),
                'unreadCount': sum(not item['read'] for item in visible), 'totalCount': len(visible),
                'inboxCount': sum(item['status'] == 'inbox' for item in visible),
                'laterCount': sum(item['status'] == 'later' for item in visible),
                'archiveCount': sum(item['status'] == 'archive' for item in visible)}

    def inbox(self, expectedRoot=None):
        """List To read, Later and Archive reports; browsing never changes status."""
        with self._document_scope(expectedRoot):
            return self._inbox_result(self._inbox_entries())

    def register_report(self, id, path, title, summary, source, createdAt=None):
        """Register an existing report by stable id without changing earlier delivery."""
        identifier = self._inbox_id(id)
        with self._document_scope(), self._inbox_write_lock():
            entries = self._inbox_entries()
            existing = next((entry for entry in entries if entry['id'] == identifier), None)
            if existing is not None:
                return {**self._inbox_result(entries), 'created': False, 'item': existing}
            if len(entries) >= MAX_INBOX_ENTRIES:
                raise ValueError('收件箱已達 5,000 項上限，未更改原始索引。')
            report_path = self._inbox_report_path(path)
            # Validate bounded UTF-8 Markdown through the same reader used by Document.
            document = self.read(report_path)
            if not document['content'].strip():
                raise ValueError('報告正文不能是空白。')
            now = datetime.now(timezone.utc).isoformat()
            entry = {'id': identifier, 'path': report_path,
                     'title': self._inbox_text(title, '報告標題', 240),
                     'summary': self._inbox_text(summary, '報告摘要', 2000, required=False),
                     'source': self._inbox_text(source, '報告來源', 240),
                     'createdAt': self._inbox_date(createdAt) if createdAt is not None else now,
                     'registeredAt': now, 'read': False, 'readAt': None, 'status': 'inbox'}
            entries.append(entry)
            self._save_inbox(entries)
            return {**self._inbox_result(entries), 'created': True, 'item': entry}

    def mark_report_read(self, id, read, expectedRoot=None):
        """Retain the reader checkbox API: Read archives; unchecking returns To read."""
        if type(read) is not bool:
            raise ValueError('已讀狀態必須明確指定為 true 或 false。')
        return self.move_report(id, 'archive' if read else 'inbox', expectedRoot=expectedRoot)

    def move_report(self, id, status, expectedRoot=None):
        """Move a visible report between To read, Later and Archive."""
        identifier = self._inbox_id(id)
        if not isinstance(status, str) or status not in {'inbox', 'later', 'archive'}:
            raise ValueError('報告狀態只能是 inbox、later 或 archive。')
        with self._document_scope(expectedRoot), self._inbox_write_lock():
            entries = self._inbox_entries()
            entry = next((item for item in entries if item['id'] == identifier), None)
            if entry is None:
                raise ValueError('找不到此報告，請刷新收件箱。')
            if entry['status'] == 'cleared':
                raise ValueError('此報告已從歸檔清單移除；請使用清除操作的復原按鈕。')
            if entry['status'] != status:
                entry['status'] = status
                entry['read'] = status == 'archive'
                entry['readAt'] = datetime.now(timezone.utc).isoformat() if entry['read'] else None
                self._save_inbox(entries)
            return {**self._inbox_result(entries), 'item': entry}

    def clear_archive(self, expectedRoot=None):
        """Hide only archived entries as one undoable batch; never delete files."""
        with self._document_scope(expectedRoot), self._inbox_write_lock():
            entries = self._inbox_entries()
            token = uuid.uuid4().hex
            now = datetime.now(timezone.utc).isoformat()
            archived = [entry for entry in entries if entry['status'] == 'archive']
            for entry in archived:
                entry.update({'status': 'cleared', 'clearBatch': token, 'clearedAt': now})
            if archived:
                self._save_inbox(entries)
            return {**self._inbox_result(entries), 'clearedCount': len(archived), 'undoToken': token}

    def restore_archive(self, undoToken, expectedRoot=None):
        """Undo only the requested batch's entries that are still cleared."""
        token = self._undo_token(undoToken)
        with self._document_scope(expectedRoot), self._inbox_write_lock():
            entries = self._inbox_entries()
            restored = [entry for entry in entries if entry['status'] == 'cleared' and entry['clearBatch'] == token]
            for entry in restored:
                entry['status'] = 'archive'
                entry.pop('clearBatch', None)
                entry.pop('clearedAt', None)
            if restored:
                self._save_inbox(entries)
            return {**self._inbox_result(entries), 'restoredCount': len(restored), 'undoToken': token}

    def sample_status(self):
        with self._lock:
            root = self._root()
            current = device_library.status(root)
            if self._worker and self._worker.is_alive():
                return {**current, 'root': str(root), 'status': 'running'}
            result = current if current.get('status') == 'running' else (self._job or current)
            self._job = None
            return {**result, 'root': str(root)}

    def collect(self, scenario):
        with self._lock:
            root = self._root()
            if self._busy():
                raise ValueError('已有一次採樣正在進行。')
            scenario = str(scenario or '未標記工作狀態').strip()
            if len(scenario) > 100 or any(ord(char) < 32 for char in scenario):
                raise ValueError('工作狀態標籤請保持在 100 字以內，且使用單行。')
            self._job = {'status': 'running', 'phase': '準備輕量採樣', 'root': str(root)}
            self._cancel_event = threading.Event()

            def run():
                try:
                    result = device_library.collect(root, scenario=scenario, timeout=45, window=1.0,
                                                    cancel_event=self._cancel_event)
                except Exception as exc:
                    result = {'status': 'failed', 'error': str(exc), 'phase': '採樣失敗；已保存的歷史記錄不受影響'}
                with self._lock:
                    self._job = {**result, 'root': str(root)}

            self._worker = threading.Thread(target=run, name='device-library-sample', daemon=True)
            self._worker.start()
            return dict(self._job)

    def cancel(self):
        with self._lock:
            active = bool(self._worker and self._worker.is_alive())
            if active and self._cancel_event is not None:
                self._cancel_event.set()
            result = device_library.cancel(self._root())
            if active:
                result.update({'status': 'running', 'cancelRequested': True, 'phase': '已要求取消，正在保存已取得的資料'})
            return {**result, 'root': str(self._root())}

    def snapshots(self):
        root = self._root()
        return {'root': str(root), 'snapshots': device_library.list_snapshots(root)}

    def _device_details(self, model):
        """Read a small, model-bound private note; never infer price or color."""
        result = {'status': 'unavailable', 'model': None, 'purchase': None, 'color': None, 'reason': ''}
        if not model:
            result['reason'] = '尚無已保存型號可核對設備補充資料。'
            return result
        try:
            candidate = self._root() / DEVICE_DETAILS_FILE
            if not candidate.exists():
                result['reason'] = '尚未記錄購買資訊或機身顏色。'
                return result
            if candidate.is_symlink() or getattr(candidate, 'is_junction', lambda: False)() or not candidate.is_file():
                raise ValueError('設備補充資料必須是所選資料庫內的普通檔案。')
            _, path = self._path(DEVICE_DETAILS_FILE)
            with path.open('rb') as source:
                raw = source.read(MAX_DEVICE_DETAILS_BYTES + 1)
            if len(raw) > MAX_DEVICE_DETAILS_BYTES:
                raise ValueError('設備補充資料超過 16 KiB。')
            data = json.loads(raw.decode('utf-8-sig'))
            if (not isinstance(data, dict) or type(data.get('schemaVersion')) is not int
                    or data['schemaVersion'] != 1 or not _text_value(data.get('model'))):
                raise ValueError('設備補充資料格式無效。')
            if data['model'].strip().casefold() != model.strip().casefold():
                result['reason'] = '補充資料型號與目前保存的設備不同，未套用。'
                return result
            purchase = data.get('purchase')
            if purchase is not None:
                if not isinstance(purchase, dict):
                    raise ValueError('購買資訊格式無效。')
                amount, currency, provenance = purchase.get('amount'), purchase.get('currency'), purchase.get('source')
                year = purchase.get('year')
                approximate, year_approximate = purchase.get('approximate'), purchase.get('yearApproximate', False)
                if (type(amount) not in (int, float) or not math.isfinite(amount) or not 0 < amount <= 1000000000
                        or not isinstance(currency, str) or not re.fullmatch(r'[A-Z]{3}', currency)
                        or not isinstance(provenance, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', provenance)
                        or type(approximate) is not bool or type(year_approximate) is not bool
                        or year is not None and (type(year) is not int or not 1900 <= year <= 2100)):
                    raise ValueError('購買資訊數值或來源無效。')
                purchase = {'amount': amount, 'currency': currency, 'approximate': approximate,
                            'source': provenance, 'year': year, 'yearApproximate': year_approximate}
            color = data.get('color')
            if color is not None:
                color = _text_value(color, 64)
                if color is None:
                    raise ValueError('機身顏色記錄無效。')
            result.update({'status': 'available', 'model': model, 'purchase': purchase, 'color': color})
        except (OSError, ValueError, UnicodeError, RuntimeError, RecursionError, OverflowError) as exc:
            result['reason'] = '設備補充資料暫時不可用。' if not isinstance(exc, ValueError) else '設備補充資料格式或讀取範圍無效。'
        return result

    def overview(self):
        with self._document_scope() as root:
            memory, gpu, storage = current_memory(), current_gpu(), current_storage()
            result = {'root': str(root), 'currentMemory': memory, 'currentGpu': gpu['adapters'],
                      'currentStorage': storage,
                      'currentGpuRead': {key: value for key, value in gpu.items() if key != 'adapters'},
                      'sampledAt': None, 'hardwareSampledAt': None, 'status': 'idle', 'applications': [],
                      'gpuModels': [], 'cpus': [], 'memoryModules': [], 'gpus': []}
            try:
                snapshots = device_library.list_snapshots(root)
            except (OSError, ValueError, TypeError, RuntimeError, RecursionError):
                snapshots = []
            for item in snapshots:
                try:
                    _, path = self._path(item.get('path') or f"snapshots/{item['id']}.json")
                    with path.open('rb') as source:
                        raw = source.read(MAX_TEXT_BYTES + 1)
                    if len(raw) > MAX_TEXT_BYTES:
                        continue
                    snapshot = json.loads(raw.decode('utf-8-sig'))
                    if not isinstance(snapshot, dict):
                        continue
                    system = snapshot.get('system') if isinstance(snapshot.get('system'), dict) else {}
                    hardware = snapshot.get('hardware') if isinstance(snapshot.get('hardware'), dict) else {}
                    if snapshot.get('status') not in {'completed', 'partial'} or _integer_value(system.get('visiblePhysicalBytes'), positive=True) is None:
                        continue
                    cpus, modules, gpus = (_hardware_rows(hardware.get(key), key) for key in ('cpus', 'memoryModules', 'gpus'))
                    result.update({'sampledAt': snapshot.get('sampledAt'),
                                   'hardwareSampledAt': hardware.get('sampledAt') or snapshot.get('sampledAt'),
                                   'scenario': snapshot.get('scenario'), 'status': snapshot.get('status'),
                                   'physicalTotalBytes': system.get('visiblePhysicalBytes'),
                                   'availableBytes': system.get('availablePhysicalBytes'), 'commitBytes': system.get('committedBytes'),
                                   'model': _text_value(hardware.get('model')),
                                   'cpuModel': ', '.join(cpu['name'] for cpu in cpus if cpu['name']),
                                   'gpuModels': [adapter['name'] for adapter in gpus if adapter['name']],
                                   'installedMemoryBytes': system.get('installedPhysicalBytes'),
                                   'cpus': cpus, 'memoryModules': modules, 'gpus': gpus,
                                   'report': item.get('report') or f"reports/{snapshot['id']}.md",
                                   'applications': snapshot.get('groups') or []})
                    break
                except (ValueError, TypeError, AttributeError, KeyError, OSError, UnicodeError, RuntimeError, RecursionError):
                    continue
            result['deviceDetails'] = self._device_details(result.get('model'))
            return result

    def compare(self, before, after):
        with self._lock:
            if self._busy():
                raise ValueError('請在採樣完成後比較。')
            return device_library.compare(self._root(), before, after)
