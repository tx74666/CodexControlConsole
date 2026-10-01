"""Local document browsing, a persistent report inbox and a fixed device sampler."""
from contextlib import contextmanager
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import uuid

import device_library


TEXT_EXTENSIONS = {'.md', '.txt', '.json', '.csv', '.log', '.ps1', '.py', '.cmd'}
MAX_TEXT_BYTES = 2 * 1024 * 1024
INBOX_FILE = '.document-inbox.json'
INBOX_LOCK_FILE = '.document-inbox.lock'
MAX_INBOX_ENTRIES = 5000
GUIDE_FILE = '.document-guide.json'
MAX_GUIDE_BYTES = 64 * 1024
MAX_GUIDE_ITEMS = 50
REFERENCES_FILE = '.document-references.json'
MAX_REFERENCE_BYTES = 128 * 1024
MAX_REFERENCE_ITEMS = 100


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
              'availableBytes': None, 'totalBytes': None, 'usedPercent': None, 'reason': ''}
    try:
        result.update(_windows_memory_values())
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

    def overview(self):
        root = self._root()
        memory = current_memory()
        snapshots = device_library.list_snapshots(root)
        for item in snapshots:
            try:
                _, path = self._path(item.get('path') or f"snapshots/{item['id']}.json")
                with path.open('rb') as source:
                    raw = source.read(MAX_TEXT_BYTES + 1)
                if len(raw) > MAX_TEXT_BYTES:
                    continue
                snapshot = json.loads(raw.decode('utf-8-sig'))
                system, hardware = snapshot.get('system') or {}, snapshot.get('hardware') or {}
                if snapshot.get('status') not in {'completed', 'partial'} or system.get('visiblePhysicalBytes') is None:
                    continue
                return {'root': str(root), 'currentMemory': memory, 'sampledAt': snapshot.get('sampledAt'),
                        'scenario': snapshot.get('scenario'), 'status': snapshot.get('status'),
                        'physicalTotalBytes': system.get('visiblePhysicalBytes'),
                        'availableBytes': system.get('availablePhysicalBytes'), 'commitBytes': system.get('committedBytes'),
                        'model': hardware.get('model'), 'cpuModel': ', '.join(cpu.get('name', '') for cpu in hardware.get('cpus') or []),
                        'gpuModels': [gpu.get('name') for gpu in hardware.get('gpus') or [] if gpu.get('name')],
                        'installedMemoryBytes': system.get('installedPhysicalBytes'),
                        'report': item.get('report') or f"reports/{snapshot['id']}.md",
                        'applications': snapshot.get('groups') or []}
            except (ValueError, KeyError, OSError, UnicodeError):
                continue
        return {'root': str(root), 'currentMemory': memory, 'sampledAt': None, 'status': 'idle', 'applications': [], 'gpuModels': []}

    def compare(self, before, after):
        with self._lock:
            if self._busy():
                raise ValueError('請在採樣完成後比較。')
            return device_library.compare(self._root(), before, after)
