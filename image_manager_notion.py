"""On-demand original-file synchronization through the signed-in Codex app server.

No model turn, credential extraction, browser automation, scheduler, or watcher is
used. The generated public app-server protocol is used only for fixed Notion
tools. Downloaded files always enter the core import review workflow.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone, timedelta
import hashlib
import html
import io
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time
import tomllib
from urllib.parse import parse_qs, urlsplit
import uuid

from PIL import Image

from image_manager import ImageManagerError, _atomic_json, _json, _link, _title, _filename_annotation, EXTENSIONS


MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_BATCH = 50
MAX_CATALOG_BYTES = 256 * 1024
MAX_CATALOG_ENTRIES = 1000
CATALOG_PREFIX = 'Image manager catalog - '
CATALOG_STORAGE_PREFIX = 'Image_manager_catalog_-_'
CATALOG_RE = re.compile(r'^(?:Image manager catalog - |Image_manager_catalog_-_)(\d{8}T\d{12}Z)-([0-9a-f]{64})\.json$')
SHA_RE = re.compile(r'[0-9a-f]{64}\Z')
OPERATION_FIELDS = ('id', 'requestId', 'source', 'target', 'root', 'pageId', 'status', 'phase',
    'code', 'message', 'startedAt', 'finishedAt', 'resumedAt', 'priorVerificationFailure',
    'items', 'catalog', 'annotations', 'planId', 'completedTargets', 'remainingTargets', 'verifiedOriginals',
    'exportSnapshot', 'exportCatalogSha256')
RPC_TOOLS = {
    'fetch': 'notion.fetch',
    'prepare': 'notion.notion-create-file-upload',
    'attach': 'notion.notion-update-folder',
    'download': 'notion.notion-get-file-download-urls',
    'page': 'notion.notion-update-page',
}
REF_RE = re.compile(r'notion-file-block://[^\s"<>]+')
GALLERY_MARKER = 'image-manager-gallery-v1'
SYNCED_RE = re.compile(r'<synced-block\s+url="([^"<>\r\n]+)"\s*>.*?</synced-block>', re.S)
SOURCE_RE = re.compile(r'<(?:image|file)\b[^>]*\bsource="([^"<>]+)"[^>]*>', re.S)
FILE_SOURCE_RE = re.compile(r'<file\b[^>]*\bsource="([^"<>]+)"[^>]*>', re.S)
PAGE_IMAGE_RE = re.compile(r'<image\b[^>]*\bsource="([^"<>]+)"[^>]*?(?:/\s*>|>(.*?)</image>)', re.S)


def _page_region(page):
    text = page.get('text', '')
    if not isinstance(text, str) or len(text) > 1024 * 1024:
        raise NotionSyncError('notion_page_incomplete', 'Notion 图片页面未能完整读取；没有写入。')
    marker = re.compile(r'(?m)^[ \t]*' + GALLERY_MARKER + r'[ \t]*$')
    regions = [match for match in SYNCED_RE.finditer(text) if marker.search(match[0])]
    if len(regions) != 1 or len(marker.findall(text)) != 1:
        raise NotionSyncError('notion_gallery_unconfigured', '此页面需要唯一的 Image 图片区；未更改页面说明。')
    region = regions[0]
    value = region[0]
    parsed = urlsplit(region[1])
    owner = _identifier(page.get('id'))
    if (parsed.scheme != 'https' or parsed.hostname not in {'notion.so','www.notion.so','notion.com','www.notion.com','app.notion.com'}
            or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.query
            or not _identifier(parsed.fragment) or not _identifier(region[1])
            or owner and _identifier(region[1]) != owner):
        raise NotionSyncError('notion_gallery_foreign', '图片区必须是当前页面所属的原始区块，未更改其他页面。')
    if (value.count('<synced-block') != 1 or '<synced-block-reference' in value
            or re.search(r'<(?:page|database|folder)\b', value)
            or not re.search(r'<toggle(?:\s[^>]*)?>.*?' + GALLERY_MARKER + r'.*?</toggle>', value, re.S)):
        raise NotionSyncError('notion_gallery_invalid', '图片区结构无法安全核对，未更改页面。')
    return {'text':value, 'url':region[1], 'start':region.start(), 'end':region.end()}


def _managed_text(entity):
    return _page_region(entity)['text'] if entity.get('metadata', {}).get('type') == 'page' else entity.get('text', '')


def _stable_refs(entity, *, pending=()):
    text = _managed_text(entity)
    if entity.get('metadata', {}).get('type') == 'page':
        values = [html.unescape(value) for value in SOURCE_RE.findall(text)]
        if any(not REF_RE.fullmatch(value) and value not in pending for value in values):
            raise NotionSyncError('notion_gallery_source_unsupported', '图片区含尚未支持的附件来源，保留原页面，未删除或替换图片。')
        return list(dict.fromkeys(value for value in values if REF_RE.fullmatch(value)))
    return list(dict.fromkeys(html.unescape(value) for value in REF_RE.findall(text)))


def _source_id(source):
    matches = re.findall(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', source.split('?', 1)[0])
    return _identifier(matches[-1]) if matches else ''


def _upload_source(uploaded):
    source = uploaded.get('markdown_source')
    if not isinstance(source, str):
        suggested = uploaded.get('suggested_markdown', '')
        match = re.fullmatch(r'\s*<(?:image|file) source="([^"<>]+)"[^>]*>.*?</(?:image|file)>\s*', suggested, re.S) if isinstance(suggested, str) else None
        if not match and isinstance(suggested, str):
            match = re.fullmatch(r'!?\[[^\]\r\n]*\]\(([^\s()]+)\)\s*', suggested)
        source = html.unescape(match[1]) if match else None
    upload_id = _identifier(uploaded.get('id', uploaded.get('file_upload_id')))
    if (not isinstance(source, str) or not 1 <= len(source) <= 4096
            or any(ord(char) < 32 or char in '<>"' for char in source)
            or not re.match(r'[a-z][a-z0-9+._-]*:', source)
            or source.split(':',1)[0].lower() in {'http', 'https', 'file', 'data', 'javascript'}
            or not upload_id or _source_id(source) != upload_id):
        raise NotionSyncError('upload_markdown_unverified', '上传已保存，但原生附件引用尚未核实；不会猜测地址或重传。', unknown=True)
    return source


def _caption(value):
    return f"{value['groupTitle']} · {value['variantLabel']} · {value['width']}×{value['height']}"


def _render_gallery(region, rows, files):
    blocks = ['<synced-block url="' + html.escape(region['url'], quote=True) + '">', '## Image', '']
    for offset in range(0, len(rows), 3):
        group = rows[offset:offset + 3]
        blocks.append('<columns>')
        for index, row in enumerate(group):
            ratio = (34 if index == 0 else 33) if len(group) == 3 else 50 if len(group) == 2 else 100
            caption = html.escape(row['caption'])
            # A catalogue label is text, never Markdown instructions or links.
            caption = re.sub(r'([\\`*_\[\]{}])', r'\\\1', caption)
            blocks.extend([f'<column ratio="{ratio}">', '<image source="' + html.escape(row['source'], quote=True) + '">',
                           caption, '</image>', '</column>'])
        blocks.extend(['</columns>', ''])
    blocks.extend(['<toggle>', '同步记录', '', GALLERY_MARKER, ''])
    for source, name in files:
        label = '方案目录' if _catalog_identity(name) else name
        blocks.extend(['<file source="' + html.escape(source, quote=True) + '">', html.escape(label), '</file>', ''])
    blocks.extend(['</toggle>', '</synced-block>'])
    return '\n'.join(blocks)


def _now():
    return datetime.now(timezone.utc).isoformat()


class NotionSyncError(ImageManagerError):
    def __init__(self, code, message, *, unknown=False, status=409):
        super().__init__(message, status=status)
        self.code, self.unknown = code, unknown


def _identifier(value):
    if not isinstance(value, str):
        return ''
    if value.startswith('https://'):
        value = urlsplit(value).path.rsplit('/', 1)[-1]
        match = re.search(r'([0-9a-fA-F]{32})$', value)
        value = match[1] if match else value
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        return ''


def _unwrap(value):
    if isinstance(value, dict) and value.get('isError'):
        raise NotionSyncError('notion_tool_error', 'Notion 未完成此次操作；请查看同步记录。')
    if isinstance(value, dict) and isinstance(value.get('structuredContent'), dict):
        return value['structuredContent']
    if isinstance(value, dict):
        for block in value.get('content', []):
            if isinstance(block, dict) and block.get('type') == 'text':
                try:
                    parsed = json.loads(block['text'])
                    if isinstance(parsed, dict):
                        return parsed
                except (ValueError, TypeError):
                    pass
        return value
    raise NotionSyncError('notion_response_invalid', 'Notion 返回了无法核对的资料。')


def _reference_name(reference):
    return parse_qs(urlsplit(reference).query).get('name', [''])[0]


def _catalog_identity(name):
    match = CATALOG_RE.fullmatch(name) if isinstance(name, str) else None
    return (match[1], match[2]) if match else None


def _same_catalog_name(left, right):
    identity = _catalog_identity(left)
    return identity is not None and identity == _catalog_identity(right)


def _image_refs(folder):
    if folder.get('metadata', {}).get('type') == 'page':
        _stable_refs(folder)
        values = [html.unescape(source) for source, _ in PAGE_IMAGE_RE.findall(_managed_text(folder))]
        return list(dict.fromkeys(value for value in values
            if REF_RE.fullmatch(value) and Path(_reference_name(value)).suffix.lower() in EXTENSIONS))
    return [ref for ref in _stable_refs(folder)
        if Path(_reference_name(ref)).suffix.lower() in EXTENSIONS]


def _sync_name(metadata, items):
    """A label on a new upload never changes the identity of its original."""
    suffix = Path(metadata.get('canonicalName', metadata.get('name', ''))).suffix.lower()
    width, height = metadata.get('width'), metadata.get('height')
    if suffix not in EXTENSIONS or type(width) is not int or type(height) is not int or min(width, height) < 1:
        raise NotionSyncError('sync_name_invalid', '图片尺寸或真实格式无法核对。')
    name = metadata.get('syncName')
    if not name:
        title = metadata.get('groupTitle') or metadata.get('title') or Path(metadata['name']).stem
        label = metadata.get('variantLabel') or ''
        group = metadata.get('groupId') or str(title).casefold()
        variants = {item.get('variantId') or item.get('assetId') or item.get('sha256') for item in items
            if (item.get('groupId') or str(item.get('groupTitle') or item.get('title') or '').casefold()) == group}
        explicit = metadata.get('variantExplicit') is True
        marker = ' [方案 ' + label + ']' if label and (explicit or len(variants) > 1) else ''
        name = str(title) + marker + f' - {width}x{height}' + suffix
    if (not isinstance(name, str) or not name or len(name) > 255 or Path(name).name != name
            or re.search(r'[<>:"/\\|?*\x00-\x1f\x7f]', name)
            or not re.search(r'(?<!\d)' + str(width) + r'[xX×]' + str(height) + re.escape(suffix) + r'$', name)
            or Path(name).suffix.lower() != suffix):
        raise NotionSyncError('sync_name_invalid', '同步文件名须保留标题、实际尺寸和图片格式。')
    return name


def _entry(metadata):
    return {'groupTitle': metadata.get('groupTitle') or metadata.get('title') or Path(metadata['name']).stem,
        'variantLabel': metadata.get('variantLabel') or '',
        'derivedFromId': metadata.get('derivedFromId') or metadata.get('pendingDerivedFromId') or ''}


def _export_rows(snapshot):
    """Validate our private, versioned local export evidence, never legacy guesses."""
    if (not isinstance(snapshot, dict) or set(snapshot) != {'version','entries','fingerprint'}
            or type(snapshot['version']) is not int or snapshot['version'] != 1
            or not isinstance(snapshot['entries'], list) or len(snapshot['entries']) > MAX_BATCH):
        return None
    entries = snapshot['entries']
    metadata = {}
    for row in entries:
        if not isinstance(row, dict) or set(row) != {'filename','syncName','sha256','metadata'}:
            return None
        for field in ('filename','syncName'):
            value = row[field]
            if (not isinstance(value, str) or not 1 <= len(value) <= 255 or '/' in value or '\\' in value
                    or any(ord(char) < 32 or ord(char) == 127 for char in value)):
                return None
        digest = row['sha256']
        if not isinstance(digest, str) or not SHA_RE.fullmatch(digest):
            return None
        if digest in metadata and metadata[digest] != row['metadata']:
            return None
        metadata[digest] = row['metadata']
    try:
        _validate_entries(metadata)
    except ImageManagerError:
        return None
    canonical = sorted(entries, key=lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True))
    encoded = json.dumps({'version':1,'entries':canonical}, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':')).encode('utf-8')
    if hashlib.sha256(encoded).hexdigest() != snapshot['fingerprint']:
        return None
    return canonical


def _snapshot_matches_catalog(snapshot, catalog):
    rows = _export_rows(snapshot)
    return rows is not None and all(catalog.get(row['sha256']) == row['metadata'] for row in rows)


def _export_scope(root, page_id):
    return hashlib.sha256((os.path.normcase(root) + ':' + page_id).encode()).hexdigest()


def _validate_entries(entries, *, known=None):
    if not isinstance(entries, dict) or len(entries) > MAX_CATALOG_ENTRIES:
        raise NotionSyncError('catalog_invalid', '方案目录格式无效，未更改图片或注释。')
    for digest, row in entries.items():
        if (not isinstance(digest, str) or not SHA_RE.fullmatch(digest) or not isinstance(row, dict)
                or set(row) != {'groupTitle', 'variantLabel', 'derivedFromId'}):
            raise NotionSyncError('catalog_invalid', '方案目录包含无效的图片身份或字段。')
        for field, maximum, required in [('groupTitle', 140, True), ('variantLabel', 100, False)]:
            value = row[field]
            if (not isinstance(value, str) or len(value) > maximum or (required and not value.strip())
                    or any(ord(char) < 32 or ord(char) == 127 for char in value)):
                raise NotionSyncError('catalog_invalid', '方案目录中的名称超长或包含无效字符。')
        source = row['derivedFromId']
        if not isinstance(source, str) or (source and not SHA_RE.fullmatch(source)) or source == digest:
            raise NotionSyncError('catalog_invalid', '方案目录中的派生来源无效。')
        if known is not None and digest not in known:
            raise NotionSyncError('catalog_original_missing', '方案目录中的原件尚未核实，未修改注释。')
    completed = set()
    for start in entries:
        chain, current = set(), start
        while current in entries and current not in completed:
            if current in chain:
                raise NotionSyncError('catalog_cycle', '方案目录的派生关系存在循环，未修改注释。')
            chain.add(current)
            current = entries[current]['derivedFromId']
        completed.update(chain)
    return entries


def _catalog_bytes(entries):
    _validate_entries(entries)
    data = (json.dumps({'kind': 'image-manager-catalog', 'schemaVersion': 1, 'entries': entries},
        ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    if len(data) > MAX_CATALOG_BYTES:
        raise NotionSyncError('catalog_too_large', '本批方案目录超过 256 KiB。')
    return data


def _parse_catalog(data, digest):
    if not data or len(data) > MAX_CATALOG_BYTES or hashlib.sha256(data).hexdigest() != digest:
        raise NotionSyncError('catalog_hash_mismatch', '方案目录原件校验不匹配，未修改图片或注释。')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate catalog key')
            result[key] = value
        return result
    try:
        value = json.loads(data, object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError):
        raise NotionSyncError('catalog_invalid', '方案目录无法读取，未修改图片或注释。') from None
    if (not isinstance(value, dict) or set(value) != {'kind', 'schemaVersion', 'entries'}
            or value.get('kind') != 'image-manager-catalog' or type(value.get('schemaVersion')) is not int
            or value['schemaVersion'] != 1):
        raise NotionSyncError('catalog_invalid', '方案目录版本或结构不受支持，未修改注释。')
    return _validate_entries(value['entries'])


def _verified_completion(operation):
    """Positive terminal evidence for the one completed Notion destination."""
    if (not isinstance(operation, dict) or operation.get('source') not in {'local','console'}
            or operation.get('target') != 'notion' or operation.get('completedTargets') != ['notion']
            or operation.get('remainingTargets') != []):
        return False
    items, catalog = operation.get('items'), operation.get('catalog')
    if (not isinstance(items, list) or not 1 <= len(items) <= MAX_BATCH
            or any(not isinstance(item, dict) or item.get('status') not in {'verified','unchanged'}
                or not isinstance(item.get('sha256'), str) or not SHA_RE.fullmatch(item['sha256']) for item in items)
            or not isinstance(catalog, dict) or catalog.get('status') != 'verified'
            or not isinstance(catalog.get('sha256'), str) or not SHA_RE.fullmatch(catalog['sha256'])
            or not isinstance(catalog.get('reference'), str) or not REF_RE.fullmatch(catalog['reference'])):
        return False
    identity = _catalog_identity(catalog.get('filename'))
    return bool(identity and identity[1] == catalog['sha256']
        and _same_catalog_name(_reference_name(catalog['reference']), catalog['filename']))


def _recheck_kind(operation):
    if not isinstance(operation, dict):
        return None
    if operation.get('status') == 'unknown' and operation.get('code') == 'catalog_attached_unverified':
        return 'catalog'
    eligible = (operation.get('status'), operation.get('code')) in {
        ('failed','notion_sync_failed'), ('unknown','verified_completion_unrecorded')}
    return 'verified_completion' if eligible and _verified_completion(operation) else None


def _operation_view(operation):
    if not isinstance(operation, dict):
        return operation
    view = json.loads(json.dumps(operation))
    view.pop('exportSnapshot', None)
    view.pop('exportCatalogSha256', None)
    kind = _recheck_kind(operation)
    view.update(recheckable=bool(kind), recheckKind=kind)
    return view


def _executable(value=None):
    if value:
        path = Path(value)
        return str(path) if path.is_file() else None
    found = shutil.which('codex.exe') or shutil.which('codex')
    if found:
        return found
    base = Path(os.environ.get('LOCALAPPDATA', '')) / 'OpenAI' / 'Codex' / 'bin'
    found = list(base.glob('*/codex.exe')) if base.is_dir() else []
    return str(max(found, key=lambda p: p.stat().st_mtime_ns)) if found else None


def _acquire_file_lock(path, *, initialize=True):
    if path.exists() and _link(path):
        raise NotionSyncError('sync_lock_invalid', '同步锁位置无效。')
    handle = path.open('a+b' if initialize else 'r+b')
    try:
        if initialize and path.stat().st_size == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except OSError:
        handle.close()
        raise NotionSyncError('sync_busy', '此 Notion 图库正在由另一个同步请求处理。') from None


def _release_file_lock(handle):
    try:
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


class CodexNotionRPC:
    """One owned stdio process, ephemeral context, and fixed tool allowlist."""
    def __init__(self, executable, cwd, target_id, *, timeout=45):
        self.executable, self.cwd, self.timeout = executable, str(cwd), timeout
        self.target_id = _identifier(target_id)
        if not self.target_id:
            raise NotionSyncError('notion_target_invalid', 'Notion 图库身份无效。')
        self.process = None
        self.incoming, self.sequence = queue.Queue(), 0
        self.thread_id = None
        self.allowed_refs = set()
        self.prepared_ids, self.allowed_upload_sources = set(), set()
        self.latest_region, self.target_type = None, None

    def authorize_upload(self, uploaded):
        source = _upload_source(uploaded)
        if _identifier(uploaded.get('id', uploaded.get('file_upload_id'))) not in self.prepared_ids:
            raise NotionSyncError('notion_scope_invalid', '只能附加本次已核对的上传原件。')
        self.allowed_upload_sources.add(source)
        return source

    def __enter__(self):
        command = [self.executable, 'app-server', '--listen', 'stdio://']
        settings = {'hooks': '{}', 'notify': '[]', 'check_for_update_on_startup': 'false',
            'features.apps': 'true', 'features.browser_use': 'false', 'features.computer_use': 'false',
            'apps._default.enabled': 'false', 'apps._default.destructive_enabled': 'false',
            'apps.asdk_app_69c18c28f1188191bf5b8445c4ab0a2e.enabled': 'true',
            'apps.asdk_app_69c18c28f1188191bf5b8445c4ab0a2e.default_tools_enabled': 'false',
            'project_doc_max_bytes': '0'}
        # Empty tables merge with configuration. Disable configured entries one
        # at a time instead; never read, copy, or log their command/auth values.
        configuration = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'config.toml'
        try:
            config = tomllib.loads(configuration.read_text(encoding='utf-8'))
            for group in ('mcp_servers', 'plugins'):
                for name in config.get(group, {}):
                    if re.fullmatch(r'[A-Za-z0-9_@-]+', name):
                        settings[group + '.' + name + '.enabled'] = 'false'
        except (OSError, ValueError):
            pass
        for tool in RPC_TOOLS.values():
            settings['apps.asdk_app_69c18c28f1188191bf5b8445c4ab0a2e.tools.' + tool.split('.', 1)[1] + '.enabled'] = 'true'
        for key, value in settings.items():
            command += ['-c', key + '=' + value]
        environment = dict(os.environ)
        # Authentication remains inside the installed CLI. Do not forward
        # incidental API keys or inherited approval overrides to this process.
        for name in list(environment):
            if name.upper() in {'OPENAI_API_KEY', 'CODEX_API_KEY', 'ACCESS_TOKEN'}:
                environment.pop(name)
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, cwd=self.cwd, env=environment,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        threading.Thread(target=self._read, daemon=True).start()
        try:
            self._call('initialize', {'clientInfo': {'name': 'console_image_manager', 'version': '1.0.0'},
                'capabilities': {'experimentalApi': True}})
            self._send({'method': 'initialized'})
            result = self._call('thread/start', {'cwd': self.cwd, 'ephemeral': True,
                'sandbox': 'read-only', 'approvalPolicy': 'never', 'config': {'project_doc_max_bytes': 0}})
            self.thread_id = result['thread']['id']
            status = self._call('mcpServerStatus/list', {'threadId': self.thread_id,
                'serverName': 'codex_apps', 'limit': 20, 'detail': 'toolsAndAuthOnly'})
            server = next((row for row in status.get('data', []) if row.get('name') == 'codex_apps'), None)
            if not server or not all(name in server.get('tools', {}) for name in RPC_TOOLS.values()):
                raise NotionSyncError('notion_connection_missing', '当前 Codex 登录尚未提供图片同步所需的 Notion 工具。')
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(4 * 1024 * 1024 + 1)
                if not line or len(line) > 4 * 1024 * 1024:
                    break
                try:
                    value = json.loads(line)
                except ValueError:
                    break
                if isinstance(value, dict) and ('id' in value or value.get('method') == 'error'):
                    self.incoming.put(value)
        finally:
            self.incoming.put(None)

    def _send(self, value):
        try:
            self.process.stdin.write((json.dumps(value, ensure_ascii=False) + '\n').encode('utf-8'))
            self.process.stdin.flush()
        except (OSError, ValueError, AttributeError):
            raise NotionSyncError('codex_connection_closed', 'Codex 同步连接已结束。', unknown=True) from None

    def _call(self, method, params):
        self.sequence += 1
        identifier = self.sequence
        self._send({'id': identifier, 'method': method, 'params': params})
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                value = self.incoming.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                raise NotionSyncError('codex_response_timeout', '同步回执尚未核实；本次请求不会自动重发。', unknown=True) from None
            if value is None:
                raise NotionSyncError('codex_connection_closed', 'Codex 同步连接已结束；请核对同步记录。', unknown=True)
            if value.get('id') == identifier and ('result' in value or 'error' in value):
                if 'error' in value:
                    raise NotionSyncError('codex_rpc_failed', 'Codex 未完成同步工具调用；原图与请求记录已保留。', unknown=True)
                return value.get('result', {})
            if 'id' in value and 'method' in value:
                # This provider never starts inference, accepts approvals, or
                # grants another tool/shell permission.
                self._send({'id': value['id'], 'error': {'code': -32601, 'message': 'Not supported by the image synchronizer.'}})

    def call(self, action, arguments):
        if action not in RPC_TOOLS:
            raise NotionSyncError('notion_scope_invalid', '不支持此同步操作。')
        if action == 'fetch' and (set(arguments) != {'id'} or _identifier(arguments['id']) != self.target_id):
            raise NotionSyncError('notion_scope_invalid', '同步只允许已选择的 Image manager。')
        if action == 'attach' and (set(arguments) != {'folder_id', 'command', 'file_upload_ids'}
                or arguments.get('folder_id') != self.target_id or arguments.get('command') != 'add_files'
                or not isinstance(arguments.get('file_upload_ids'), list)
                or not 1 <= len(arguments['file_upload_ids']) <= MAX_BATCH
                or any(not _identifier(x) for x in arguments['file_upload_ids'])):
            raise NotionSyncError('notion_scope_invalid', '同步不会删除或覆盖 Notion 中的已有图片。')
        if action == 'prepare' and (set(arguments) != {'filename'} or not isinstance(arguments['filename'], str)
                or Path(arguments['filename']).name != arguments['filename']
                or '/' in arguments['filename'] or '\\' in arguments['filename']
                or any(ord(c) < 32 for c in arguments['filename'])):
            raise NotionSyncError('notion_scope_invalid', '上传图片名称无效。')
        if action == 'download' and (set(arguments) != {'references'}
                or not isinstance(arguments.get('references'), list)
                or not 1 <= len(arguments['references']) <= 25
                or not set(arguments['references']) <= self.allowed_refs):
            raise NotionSyncError('notion_scope_invalid', '只能下载所选图库中已回读的原件。')
        if action == 'page':
            updates = arguments.get('content_updates')
            if (set(arguments) != {'page_id', 'command', 'content_updates'}
                    or arguments.get('page_id') != self.target_id or arguments.get('command') != 'update_content'
                    or self.target_type != 'page' or not self.latest_region
                    or not isinstance(updates, list) or len(updates) != 1
                    or not isinstance(updates[0], dict) or set(updates[0]) != {'old_str', 'new_str'}
                    or updates[0].get('old_str') != self.latest_region['text']):
                raise NotionSyncError('notion_scope_invalid', '只可更新已回读的同一页面图片区。')
            new = _page_region({'id':self.target_id, 'text':updates[0]['new_str']})
            old_refs = set(_stable_refs({'id':self.target_id, 'metadata':{'type':'page'}, 'text':self.latest_region['text']}))
            new_refs = set(_stable_refs({'id':self.target_id, 'metadata':{'type':'page'}, 'text':new['text']},
                                       pending=self.allowed_upload_sources))
            sources = set(html.unescape(value) for value in SOURCE_RE.findall(new['text']))
            if (new['text'] != updates[0]['new_str'] or new['url'] != self.latest_region['url']
                    or not old_refs <= new_refs or not new_refs <= self.allowed_refs
                    or not sources <= self.allowed_refs | self.allowed_upload_sources):
                raise NotionSyncError('notion_scope_invalid', '图片区不能删除原件、引入未知附件或改写区外内容。')
        result = _unwrap(self._call('mcpServer/tool/call', {'threadId': self.thread_id,
            'server': 'codex_apps', 'tool': RPC_TOOLS[action], 'arguments': arguments}))
        if action == 'fetch':
            if (result.get('truncated') or result.get('unknown_block_count')
                    or result.get('unknown_block_ids') or _identifier(result.get('id')) != self.target_id
                    or result.get('metadata', {}).get('type') not in {'folder', 'page'}
                    or self.target_type not in {None, result.get('metadata', {}).get('type')}):
                raise NotionSyncError('notion_folder_incomplete', 'Notion 图库未能完整读取；没有写入。')
            self.target_type = result['metadata']['type']
            self.latest_region = _page_region(result) if self.target_type == 'page' else None
            self.allowed_refs.update(_stable_refs(result))
        if action == 'prepare':
            identifier = _identifier(result.get('file_upload_id'))
            if identifier:
                self.prepared_ids.add(identifier)
        if action == 'page' and result.get('warnings'):
            raise NotionSyncError('notion_page_update_warning', 'Notion 页面更新需要核对；没有重复发送。', unknown=True)
        return result

    def __exit__(self, *_):
        if self.process is None:
            return
        try:
            self.process.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Only our own newly started stdio helper; never an existing shared
            # daemon or the desktop application.
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.process.stdout:
            self.process.stdout.close()


def _quote(value):
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise NotionSyncError('transfer_value_invalid', '文件传输参数无效。')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


class CurlTransfer:
    """Bounded single HTTP/1.1 requests; secrets only in curl's stdin."""
    def __init__(self, directory, executable=None):
        self.directory = Path(directory)
        self.executable = executable or shutil.which('curl.exe') or shutil.which('curl')

    def _run(self, options, maximum):
        if not self.executable:
            raise NotionSyncError('curl_missing', '本机缺少原件传输工具。')
        response = self.directory / ('transfer-' + uuid.uuid4().hex + '.response')
        options = ['silent', 'show-error', 'http1.1', 'no-location', 'retry = 0',
            'max-redirs = 0', 'proto = "=https"', 'connect-timeout = 20', 'max-time = 180',
            'max-filesize = ' + str(maximum), 'output = ' + _quote(str(response)),
            'write-out = "%{http_code}"'] + options
        try:
            result = subprocess.run([self.executable, '--config', '-'],
                input=('\n'.join(options) + '\n').encode('utf-8'), stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=195,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode or result.stdout.strip() not in {b'200', b'201'}:
                raise NotionSyncError('file_transfer_unknown', '原件传输未取得成功回执；保留请求记录，不自动重发。', unknown=True)
            if not response.is_file() or response.stat().st_size > maximum:
                raise NotionSyncError('file_transfer_invalid', '原件传输结果超过允许大小。', unknown=True)
            return response.read_bytes()
        except (OSError, subprocess.TimeoutExpired):
            raise NotionSyncError('file_transfer_unknown', '原件传输中断；请求状态需要核对，不会自动重发。', unknown=True) from None
        finally:
            response.unlink(missing_ok=True)

    def upload(self, request, path):
        url = request.get('upload_url', '')
        parsed = urlsplit(url)
        upload_id = _identifier(request.get('file_upload_id'))
        if (parsed.scheme != 'https' or parsed.hostname != 'api.notion.com'
                or parsed.port not in (None, 443) or parsed.username or parsed.password
                or parsed.query or parsed.fragment or not upload_id
                or parsed.path != '/v1/mcp/file_uploads/' + upload_id + '/send'
                or request.get('upload_method') != 'POST' or request.get('upload_form_field') != 'file'
                or not isinstance(request.get('upload_headers'), dict)):
            raise NotionSyncError('upload_scope_invalid', 'Notion 未返回可核对的单次原件上传入口。')
        filename = request.get('filename', '')
        if not filename or Path(filename).name != filename or '/' in filename or '\\' in filename:
            raise NotionSyncError('upload_name_invalid', 'Notion 上传文件名无效。')
        form = 'file=@' + _quote(str(path)) + ';filename=' + _quote(filename)
        options = ['request = "POST"', 'url = ' + _quote(url), 'form = ' + _quote(form)]
        for name, value in request['upload_headers'].items():
            if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) or not isinstance(value, str):
                raise NotionSyncError('upload_header_invalid', '上传授权头无效。')
            options.append('header = ' + _quote(name + ': ' + value))
        if not any(k.lower() == 'expect' for k in request['upload_headers']):
            options.append('header = "Expect:"')
        try:
            return json.loads(self._run(options, 1024 * 1024))
        except (ValueError, UnicodeError):
            raise NotionSyncError('upload_response_invalid', '上传回执无法核对；不会自动重传原件。', unknown=True) from None

    def download(self, url):
        parsed = urlsplit(url)
        host = parsed.hostname or ''
        if (parsed.scheme != 'https' or parsed.port not in (None, 443) or parsed.username or parsed.password
                or not (host.endswith('.amazonaws.com') or host.endswith('.notion.so')
                    or host.endswith('.notion-static.com') or host.endswith('.notion.com')
                    or host in {'notion.so', 'notion.com'})):
            raise NotionSyncError('download_scope_invalid', 'Notion 未返回受支持的原件下载地址。')
        return self._run(['request = "GET"', 'url = ' + _quote(url)], MAX_FILE_BYTES)


class ImageManagerNotion:
    def __init__(self, service, state_dir, executable=None, *, rpc_factory=None, transfer_factory=None):
        self.service, self.directory = service, Path(state_dir).absolute()
        for path in (self.directory, *self.directory.parents):
            if path.exists() and _link(path):
                raise NotionSyncError('state_path_invalid', '同步记录目录不能经过目录链接。')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.executable = _executable(executable)
        self.custom_rpc = rpc_factory is not None
        self.rpc_factory = rpc_factory or (lambda root, page_id: CodexNotionRPC(self.executable, root, page_id))
        self.transfer_factory = transfer_factory or (lambda: CurlTransfer(self.directory))
        self.lock, self.worker = threading.RLock(), None
        self._operation = None

    @staticmethod
    def _remember_operation(record):
        history = record.setdefault('operations', {})
        if not isinstance(history, dict):
            raise NotionSyncError('notion_record_invalid', '同步请求历史无法读取；未发送新请求。')
        operation = record.get('operation')
        if isinstance(operation, dict):
            request_id = operation.get('requestId')
            if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', request_id):
                raise NotionSyncError('notion_record_invalid', '同步请求历史身份无效；未发送新请求。')
            # Only our typed receipt fields are archived, never raw RPC frames,
            # upload preparations, authorization headers, or signed URLs.
            history[request_id] = json.loads(json.dumps({key:operation[key] for key in OPERATION_FIELDS if key in operation}))
        return history

    def _context(self, payload=None, local_state=None):
        current = self.service.state() if local_state is None else local_state
        expected = (payload or {}).get('expectedRoot')
        if not current.get('configured') or not isinstance(expected or current.get('root'), str):
            raise NotionSyncError('library_unconfigured', '请先选择图片文件夹。')
        if payload is not None and (not expected or os.path.normcase(expected) != os.path.normcase(current['root'])):
            raise NotionSyncError('library_changed', '图库已切换，请重新载入后同步。')
        target_id = _identifier(current.get('notionPage'))
        if not target_id:
            raise NotionSyncError('notion_target_unconfigured', '请先连接已选择的 Notion Image manager。')
        if payload and payload.get('_targetId') and payload['_targetId'] != target_id:
            raise NotionSyncError('notion_target_changed', 'Notion 图库已切换；本次同步已停止。')
        root = current['root']
        key = hashlib.sha256((os.path.normcase(root) + ':' + target_id).encode()).hexdigest()
        path = self.directory / ('page-' + target_id + '.json')
        record = _json(path, {'root': root, 'pageId': target_id, 'receipts': [], 'operation': None})
        if record.get('pageId') != target_id or not isinstance(record.get('receipts'), list):
            raise NotionSyncError('notion_record_invalid', 'Notion 同步记录身份不匹配，请先检查原记录。')
        # Receipts are page-scoped: changing the local root never authorizes a
        # second transmission of a file whose first delivery is uncertain.
        # Read older root-scoped receipts without changing or deleting them.
        present = {row.get('uploadId') or row.get('id') or row.get('reference') for row in record['receipts']}
        for legacy in self.directory.glob('*.json'):
            if not re.fullmatch(r'[0-9a-f]{64}\.json', legacy.name):
                continue
            old = _json(legacy, {})
            if old.get('pageId') != target_id:
                continue
            for row in old.get('receipts', []):
                identity = row.get('uploadId') or row.get('id') or row.get('reference')
                if identity not in present:
                    record['receipts'].append(row)
                    present.add(identity)
            if not path.exists() and legacy.stem == key:
                record['operation'] = old.get('operation')
                record['bridgeVerifiedAt'] = old.get('bridgeVerifiedAt')
        self._remember_operation(record)
        return current, path, record

    def _export_items(self, current):
        items = [item for item in current.get('items', []) if item.get('space','root') == 'root'
                 and item.get('path','').split('/')[0].casefold() not in {'inbox','.image-manager'}]
        items = json.loads(json.dumps(items))
        annotations = {item['sha256']:{key:item[key] for key in (
            'groupTitle','groupId','variantId','variantLabel','variantExplicit','derivedFromId','pendingDerivedFromId')
            if key in item} for item in items}
        # Core state also projects pending Inbox variants. Export names must be
        # projected from adopted originals alone, without mutating that state.
        self.service._enrich(items, annotations, standard=bool(current.get('standardNaming')))
        return items

    def _export_snapshot(self, current):
        items = self._export_items(current)
        if len(items) > MAX_BATCH:
            raise NotionSyncError('local_batch_limit', '已入库图片超过本批同步范围。')
        rows = []
        for item in items:
            image = self.service.image(item['path'], current['root'], space='root')
            path = Path(image['path'])
            before = path.stat()
            digest = hashlib.sha256()
            if before.st_nlink != 1:
                raise NotionSyncError('local_original_changed', '原图身份已变化。')
            with path.open('rb') as source:
                for part in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(part)
            after = path.stat()
            token = lambda value:(value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_nlink)
            if (token(before) != token(after) or digest.hexdigest() != item.get('sha256')
                    or before.st_size != item.get('size')):
                raise NotionSyncError('local_original_changed', '图片已改变，请更新本地图库。')
            rows.append({'filename':path.name,'syncName':_sync_name(item, items),
                         'sha256':item['sha256'],'metadata':_entry(item)})
        rows.sort(key=lambda row:json.dumps(row, ensure_ascii=False, sort_keys=True))
        encoded = json.dumps({'version':1,'entries':rows}, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':')).encode('utf-8')
        snapshot = {'version':1,'entries':rows,'fingerprint':hashlib.sha256(encoded).hexdigest()}
        if _export_rows(snapshot) is None:
            raise NotionSyncError('local_export_invalid', '本地导出信息尚未核实。')
        return snapshot

    @staticmethod
    def _mark_verified_export(record):
        operation = record['operation']
        snapshot = operation.get('exportSnapshot')
        rows = _export_rows(snapshot)
        catalog = operation.get('catalog') or {}
        items = operation.get('items')
        if (not rows or operation.get('status') != 'completed'
                or operation.get('source') not in {'local','console'} or operation.get('target') not in {'notion','all'}
                or operation.get('completedTargets') != ['notion'] or operation.get('remainingTargets') != []
                or not isinstance(items, list) or len(items) != len(rows)
                or any(item.get('status') not in {'verified','unchanged'} for item in items)
                or sorted(item.get('sha256','') for item in items) != sorted(row['sha256'] for row in rows)
                or catalog.get('status') not in {'verified','unchanged'}
                or not isinstance(catalog.get('sha256'), str) or not SHA_RE.fullmatch(catalog['sha256'])
                or operation.get('exportCatalogSha256') != catalog['sha256']):
            return
        reference, filename = catalog.get('reference'), catalog.get('filename')
        identity = _catalog_identity(filename)
        if (not isinstance(reference, str) or not REF_RE.fullmatch(reference) or not identity
                or identity[1] != catalog['sha256'] or not _same_catalog_name(_reference_name(reference), filename)):
            return
        key = _export_scope(operation['root'], operation['pageId'])
        # A successful export from another root may change this page's catalog.
        # Keep its last acknowledgement only; older evidence remains in history.
        record['verifiedExports'] = {key:{'root':operation['root'],'pageId':operation['pageId'],
            'requestId':operation['requestId'],'operationId':operation['id'],
            'snapshot':json.loads(json.dumps(snapshot)), 'verifiedAt':operation['finishedAt']}}

    def _sync_status(self, current, record, operation, can_attempt):
        root, page_id = current.get('root',''), _identifier(current.get('notionPage'))
        result = {'root':root,'pageId':page_id,'status':'unavailable','localFingerprint':None,
                  'syncedFingerprint':None,'lastSyncedAt':None,'pendingCount':None,'reason':'not_configured'}
        if not current.get('configured') or not page_id or not can_attempt:
            return result
        markers = record.get('verifiedExports', {})
        marker = markers.get(_export_scope(root, page_id), {}) if isinstance(markers, dict) else {}
        if not isinstance(marker, dict):
            marker = {}
        previous = marker.get('snapshot')
        old_rows = _export_rows(previous)
        if marker.get('root') != root or marker.get('pageId') != page_id:
            old_rows = None
        if old_rows is not None:
            result.update(syncedFingerprint=previous['fingerprint'],lastSyncedAt=marker.get('verifiedAt'))
        try:
            snapshot = self._export_snapshot(current)
        except (ImageManagerError, OSError, ValueError):
            result.update(status='pending',reason='local_changed')
            return result
        result['localFingerprint'] = snapshot['fingerprint']
        if old_rows is not None:
            encode = lambda row:json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',',':'))
            now_count, old_count = Counter(map(encode,snapshot['entries'])), Counter(map(encode,old_rows))
            result['pendingCount'] = max(sum((now_count-old_count).values()),sum((old_count-now_count).values()))
        if not snapshot['entries']:
            result.update(status='unverified',reason='empty_library')
        elif operation and operation.get('status') == 'running':
            result.update(status='syncing',reason='request_running')
        elif old_rows is not None and result['localFingerprint'] != result['syncedFingerprint']:
            result.update(status='pending',reason='local_changes')
        elif operation and operation.get('status') == 'failed':
            result.update(status='failed',reason='last_request_failed')
        elif operation and (operation.get('status') in {'unknown','needs_review'} or operation.get('remainingTargets')):
            result.update(status='unverified',reason='verification_pending')
        elif old_rows is not None:
            result.update(status='synced',reason='verified_snapshot')
        else:
            result.update(status='unverified',reason='no_verified_snapshot')
        return result

    def state(self, local_state=None):
        current = self.service.state() if local_state is None else local_state
        try:
            _, _, record = self._context(local_state=current)
            operation = _operation_view(record.get('operation'))
            if operation and os.path.normcase(operation.get('root', '')) != os.path.normcase(current.get('root', '')):
                operation = None
            if operation and operation.get('status') == 'running' and not self.busy:
                operation = dict(operation, status='unknown', message='上次同步中断；请重新核对同一请求记录。')
            configured = True
        except ImageManagerError:
            record, operation, configured = {}, None, False
        can_attempt = configured and bool(self.executable or self.custom_rpc)
        available = can_attempt and bool(record.get('bridgeVerifiedAt'))
        notion = {'available': available, 'canAttempt': can_attempt, 'configured': configured, 'provider': 'codex-app-server',
            'onDemand': True, 'verified': bool(record.get('bridgeVerifiedAt')),
            'lastVerifiedAt': record.get('bridgeVerifiedAt'), 'pageId': record.get('pageId'),
            'url': 'https://app.notion.com/p/' + record.get('pageId', '').replace('-', ''),
            'operation': operation, 'maxFileBytes': MAX_FILE_BYTES}
        summary = self._sync_status(current, record, operation or _operation_view(record.get('operation')), can_attempt)
        notion['syncStatus'] = summary
        return {'notionAvailable': available, 'notion': notion, 'operation': operation, 'notionSync':summary}

    @property
    def busy(self):
        if self.worker and self.worker.is_alive():
            return True
        try:
            _, _, record = self._context()
            path = self.directory / ('target-' + record['pageId'] + '.lock')
            if not path.exists():
                return False
            handle = _acquire_file_lock(path, initialize=False)
            _release_file_lock(handle)
            return False
        except NotionSyncError as error:
            return error.code in {'sync_busy', 'sync_lock_invalid'}
        except (ImageManagerError, OSError):
            return False

    def operation(self, requestId=None):
        result = self.state()
        if requestId is not None:
            _, _, record = self._context()
            operation = record['operations'].get(requestId)
            if not isinstance(operation, dict) or operation.get('requestId') != requestId:
                raise NotionSyncError('sync_request_not_found', '尚未找到此同步请求的回执。', status=404)
            operation = _operation_view(operation)
            latest = record.get('operation') or {}
            if operation.get('status') == 'running' and (operation.get('id') != latest.get('id') or not self.busy):
                operation.update(status='unknown', message='此请求没有在途回执，保留原编号供核对。')
            result['operation'] = operation
            result['notion']['operation'] = operation
        return result

    def sync(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'source', 'target', 'expectedRoot', 'requestId'}:
            raise NotionSyncError('sync_request_invalid', '图片同步参数无效。')
        source, target = payload.get('source', 'local'), payload.get('target', 'notion')
        if not ((source in {'local', 'console'} and target in {'notion', 'all'})
                or (source == 'notion' and target in {'local', 'console', 'all'})):
            raise NotionSyncError('sync_direction_invalid', 'Notion 图片请先导入图库确认，再同步设备。')
        request_id = payload.get('requestId') or uuid.uuid4().hex
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', request_id):
            raise NotionSyncError('sync_request_invalid', '图片同步请求编号无效。')
        with self.lock:
            current, path, record = self._context(payload)
            previous = record['operations'].get(request_id)
            if previous:
                if (previous.get('root'), previous.get('source'), previous.get('target'), previous.get('pageId')) != (current['root'], source, target, record['pageId']):
                    raise NotionSyncError('sync_request_identity_changed', '同步请求编号已用于另一范围，请重新发起。')
                if not _recheck_kind(previous):
                    return self.operation(request_id)
            if self.worker and self.worker.is_alive():
                raise NotionSyncError('sync_busy', '当前图片同步尚未结束。')
            held = _acquire_file_lock(self.directory / ('target-' + record['pageId'] + '.lock'))
            try:
                # Another app instance may have just completed between our first
                # read and obtaining the lock. Preserve its receipts.
                current, path, record = self._context(payload)
                previous = record['operations'].get(request_id)
                if previous:
                    if (previous.get('root'), previous.get('source'), previous.get('target'), previous.get('pageId')) != (current['root'], source, target, record['pageId']):
                        raise NotionSyncError('sync_request_identity_changed', '同步请求编号已用于另一范围，请重新发起。')
                    if _recheck_kind(previous):
                        recheck_kind = _recheck_kind(previous)
                        operation = json.loads(json.dumps(previous))
                        operation['priorVerificationFailure'] = {'code': operation.get('code'),
                            'finishedAt': operation.get('finishedAt')}
                        operation.update(status='running', phase='connecting', resumedAt=_now(),
                            message='正在只读核对原目录请求，不会重新上传。')
                        record['operation'] = operation
                        reconcile = recheck_kind
                    else:
                        _release_file_lock(held)
                        return self.operation(request_id)
                else:
                    operation = {'id': uuid.uuid4().hex, 'requestId': request_id, 'source': source, 'target': target,
                        'root': current['root'], 'pageId': record['pageId'], 'status': 'running', 'phase': 'connecting',
                        'startedAt': _now(), 'items': [], 'message': '正在连接 Notion。'}
                    record['operation'] = operation
                    reconcile = False
                self._remember_operation(record)
                _atomic_json(path, record)
                frozen = dict(payload, _targetId=record['pageId'])
                if reconcile:
                    frozen['_reconcileCatalog'] = True
                    if reconcile == 'verified_completion':
                        frozen['_verifyOriginals'] = True
                self.worker = threading.Thread(target=self._run, args=(frozen, path, record, held), daemon=True)
                self.worker.start()
            except Exception:
                if not held.closed:
                    _release_file_lock(held)
                raise
            return self.operation(request_id)

    def _save(self, path, record, **changes):
        with self.lock:
            previous = json.loads(json.dumps(record.get('verifiedExports', {})))
            record['operation'].update(changes)
            self._mark_verified_export(record)
            self._remember_operation(record)
            try:
                _atomic_json(path, record)
            except Exception:
                record['verifiedExports'] = previous
                raise

    def _preserve_verified_completion(self, path, record):
        operation = record['operation']
        if not _verified_completion(operation):
            return False
        try:
            durable = _json(path, {})
            candidates = [durable.get('operation'), durable.get('operations', {}).get(operation['requestId'])]
            for saved in candidates:
                if (isinstance(saved, dict) and saved.get('id') == operation.get('id')
                        and saved.get('status') == 'completed' and _verified_completion(saved)):
                    # A later context-manager cleanup error cannot revoke a
                    # completion receipt which is already on disk.
                    record['operation'] = json.loads(json.dumps(saved))
                    return True
        except (OSError, ValueError, TypeError):
            pass
        # _save updates the in-memory fields before its atomic file replace.
        # Preserve the verified effects when that final replace briefly fails;
        # the original id can only enter the read-only verification path.
        self._save(path, record, status='unknown', phase='finished', code='verified_completion_unrecorded',
            message='原件与目录已核实，完成回执仍待核对；不会重新上传。', finishedAt=_now())
        return True

    def _check_root(self, payload):
        current, _, _ = self._context(payload)
        return current

    @staticmethod
    def _refs(folder):
        return _stable_refs(folder)

    def _download(self, rpc, transport, reference, *, maximum=MAX_FILE_BYTES):
        response = rpc.call('download', {'references': [reference]})
        files = response.get('files', [])
        if len(files) != 1 or response.get('unresolved'):
            raise NotionSyncError('notion_original_unavailable', 'Notion 原件下载地址尚未核实。')
        item = files[0]
        url = item.get('download_url') or item.get('url')
        if not isinstance(url, str):
            raise NotionSyncError('notion_original_unavailable', 'Notion 未返回原件下载地址。')
        data = transport.download(url)
        if not data or len(data) > maximum:
            raise NotionSyncError('notion_original_too_large', 'Notion 原件超过单张 20 MiB 同步限制。')
        return data

    def _page_rows(self, rpc, transport, entity, entries):
        rows, total = [], 0
        references = _image_refs(entity)
        if len(references) > MAX_BATCH:
            raise NotionSyncError('notion_batch_limit', '页面原图超过单批限制，未更改图片区。')
        for reference in references:
            data = self._download(rpc, transport, reference)
            total += len(data)
            if total > 96 * 1024 * 1024:
                raise NotionSyncError('notion_batch_too_large', '页面原图超过本批读取限制，未更改图片区。')
            digest = hashlib.sha256(data).hexdigest()
            try:
                with Image.open(io.BytesIO(data)) as image:
                    width, height = image.size
                    if min(width, height) < 1 or width * height > 40_000_000:
                        raise ValueError('image dimensions')
                    image.verify()
            except (OSError, ValueError, Image.DecompressionBombError):
                raise NotionSyncError('notion_image_invalid', '页面原图无法核对实际尺寸，未更改图片区。') from None
            title, label = _filename_annotation(_title(_reference_name(reference)))
            entry = entries.get(digest, {'groupTitle':title, 'variantLabel':label or '方案1'})
            row = dict(entry, source=reference, sha256=digest, width=width, height=height)
            row['caption'] = _caption(row)
            rows.append(row)
        return rows

    def _attach_asset(self, payload, record, rpc, transport, entity, receipt, uploaded, entries):
        if entity.get('metadata', {}).get('type') != 'page':
            self._check_root(payload)
            rpc.call('attach', {'folder_id':record['pageId'], 'command':'add_files', 'file_upload_ids':[receipt['uploadId']]})
            return None
        region = _page_region(entity)
        source = rpc.authorize_upload(uploaded) if hasattr(rpc, 'authorize_upload') else _upload_source(uploaded)
        rows = self._page_rows(rpc, transport, entity, entries)
        files = [(html.unescape(reference), _reference_name(html.unescape(reference)))
                 for reference in FILE_SOURCE_RE.findall(region['text'])]
        if receipt['direction'] == 'catalog':
            files.append((source, receipt['filename']))
        else:
            row = dict(receipt['metadata'], source=source, sha256=receipt['sha256'],
                       width=receipt['width'], height=receipt['height'])
            row['caption'] = _caption(row)
            rows.append(row)
        replacement = _render_gallery(region, rows, files)
        latest = rpc.call('fetch', {'id':record['pageId']})
        if latest.get('metadata', {}).get('type') != 'page' or _page_region(latest)['text'] != region['text']:
            raise NotionSyncError('notion_gallery_changed', 'Notion 图片区刚有更改，未覆盖这些修改。')
        self._check_root(payload)
        rpc.call('page', {'page_id':record['pageId'], 'command':'update_content',
            'content_updates':[{'old_str':region['text'], 'new_str':replacement}]})
        return rows

    def _verify_page_rows(self, rpc, transport, entity, expected, *, uncertain=True):
        if expected is None:
            return
        observed = {}
        for source, caption in PAGE_IMAGE_RE.findall(_page_region(entity)['text']):
            source = html.unescape(source)
            caption = re.sub(r'\\([\\`*_{}\[\]()#+\-.!|>])', r'\1', html.unescape(caption)).strip()
            observed.setdefault(_source_id(source), []).append((source, caption))
        total = 0
        for row in expected:
            match = next((source for source, caption in observed.get(_source_id(row['source']), [])
                          if caption == row['caption']), None)
            if match is None:
                raise NotionSyncError('notion_gallery_unverified', '页面图片与方案显示尚未核实；保留原请求，不重新发送。', unknown=uncertain)
            data = self._download(rpc, transport, match)
            total += len(data)
            if total > 96 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != row['sha256']:
                raise NotionSyncError('notion_gallery_unverified', '页面原图回读未能匹配，保留原请求，不重新发送。', unknown=uncertain)

    def _read_catalog(self, rpc, transport, folder):
        versions = []
        references = self._refs(folder)
        if len(references) > 2048:
            raise NotionSyncError('catalog_history_limit', '图库版本记录过多，请先检查目录。')
        for reference in references:
            name = _reference_name(reference)
            if not name.startswith((CATALOG_PREFIX, CATALOG_STORAGE_PREFIX)) or not name.endswith('.json'):
                continue
            match = CATALOG_RE.fullmatch(name)
            try:
                timestamp = datetime.strptime(match[1], '%Y%m%dT%H%M%S%fZ').replace(tzinfo=timezone.utc) if match else None
            except ValueError:
                timestamp = None
            if timestamp is None or timestamp > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise NotionSyncError('catalog_name_invalid', '方案目录的版本身份无法核对，未更改注释。')
            versions.append({'reference': reference, 'filename': name, 'sha256': match[2], 'timestamp': match[1]})
        if not versions:
            return {'entries': {}, 'sha256': None, 'reference': None, 'versions': []}
        latest = max(versions, key=lambda row: (row['timestamp'], row['sha256']))
        data = self._download(rpc, transport, latest['reference'], maximum=MAX_CATALOG_BYTES)
        entries = _parse_catalog(data, latest['sha256'])
        return dict(latest, entries=entries, versions=versions)

    @staticmethod
    def _local_metadata(current):
        values = list(current.get('items', []))
        for candidate in (current.get('plan') or {}).get('candidates', []):
            for key in ('incoming', 'existing'):
                if isinstance(candidate.get(key), dict):
                    values.append(candidate[key])
            values.extend(item for item in candidate.get('matches', []) if isinstance(item, dict))
        return {item['sha256']: item for item in values
            if item.get('space', 'root') == 'root'
            and isinstance(item.get('sha256'), str) and SHA_RE.fullmatch(item['sha256'])}

    def _check_local_originals(self, current, payload):
        verified = set()
        roots = list(current.get('items', []))
        pending = [item for item in self._local_metadata(current).values()
            if item.get('path', '').startswith('inbox/')]
        for metadata in roots + pending:
            is_pending = metadata.get('path', '').startswith('inbox/')
            try:
                image = self.service.image(metadata['path'], payload['expectedRoot'], space='root')
            except ImageManagerError:
                if is_pending:
                    continue
                raise
            digest, count = hashlib.sha256(), 0
            with Path(image['path']).open('rb') as source:
                while True:
                    block = source.read(64 * 1024)
                    if not block:
                        break
                    count += len(block)
                    if count > 64 * 1024 * 1024:
                        raise NotionSyncError('local_original_changed', '图片已改变，请重新检查图库后同步。')
                    digest.update(block)
            if count != metadata.get('size') or digest.hexdigest() != metadata.get('sha256'):
                if is_pending:
                    continue
                raise NotionSyncError('local_original_changed', '图片已改变，请重新检查图库后同步。')
            verified.add(metadata['sha256'])
        return verified

    def _remote_hashes(self, rpc, transport, folder, record):
        refs = _image_refs(folder)
        if len(refs) > MAX_BATCH:
            raise NotionSyncError('notion_batch_limit', 'Notion 当前图库超过单批 50 张，请分批整理后同步。')
        known = {x.get('reference'): x.get('sha256') for x in record['receipts']
            if x.get('status') == 'verified' and x.get('reference')}
        result = {}
        for reference in refs:
            if reference in known:
                digest = known[reference]
            else:
                data = self._download(rpc, transport, reference)
                digest = hashlib.sha256(data).hexdigest()
            result.setdefault(digest, reference)
        return result

    def _publish_catalog(self, payload, path, record, rpc, transport, local_entries):
        self._check_root(payload)
        latest_folder = rpc.call('fetch', {'id': record['pageId']})
        remote = self._remote_hashes(rpc, transport, latest_folder, record)
        latest = self._read_catalog(rpc, transport, latest_folder)
        merged = dict(latest['entries'])
        merged.update(local_entries)
        _validate_entries(merged, known=set(remote))
        data = _catalog_bytes(merged)
        digest = hashlib.sha256(data).hexdigest()
        previous = [row for row in record['receipts']
            if row.get('direction') == 'catalog' and row.get('sha256') == digest]
        if latest['sha256'] == digest:
            if latest_folder.get('metadata', {}).get('type') == 'page':
                rows = self._page_rows(rpc, transport, latest_folder, merged)
                self._verify_page_rows(rpc, transport, latest_folder, rows, uncertain=False)
            for receipt in previous:
                receipt.update(status='verified', reference=latest['reference'], verifiedAt=_now())
            self._save(path, record, catalog={'status': 'unchanged', 'sha256': digest,
                'reference': latest['reference'], 'filename': latest['filename']})
            return
        unresolved = [row for row in previous if row.get('status') in {
            'upload_preparing', 'upload_unknown', 'uploaded_unattached', 'attach_unknown', 'attached_unverified'}]
        for receipt in unresolved:
            matches = [row for row in latest['versions'] if row['sha256'] == digest
                and _same_catalog_name(row['filename'], receipt.get('filename'))]
            if matches:
                version = matches[0]
                original = self._download(rpc, transport, version['reference'], maximum=MAX_CATALOG_BYTES)
                _parse_catalog(original, digest)
                receipt.update(status='verified', reference=version['reference'], verifiedAt=_now())
        if any(row.get('status') != 'verified' for row in unresolved):
            raise NotionSyncError('catalog_receipt_unresolved', '此方案目录已有未核实的上传请求，不会重复发送。', unknown=True)
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        if latest.get('timestamp') and timestamp <= latest['timestamp']:
            raise NotionSyncError('catalog_clock_ahead', 'Notion 目录版本时间较新，请稍后重新同步。')
        name = CATALOG_PREFIX + timestamp + '-' + digest + '.json'
        receipt = {'id': uuid.uuid4().hex, 'direction': 'catalog', 'sha256': digest, 'size': len(data),
            'requestId': record['operation']['requestId'],
            'filename': name, 'status': 'upload_preparing', 'createdAt': _now()}
        record['receipts'].append(receipt)
        self._save(path, record, phase='uploading', message='正在保存方案目录；原图不会重复上传。')
        snapshot = self.directory / ('catalog-' + receipt['id'] + '.json')
        try:
            with snapshot.open('xb') as output:
                output.write(data)
            self._check_root(payload)
            prepared = rpc.call('prepare', {'filename': name})
            receipt.update(uploadId=prepared.get('file_upload_id'), status='upload_pending')
            self._save(path, record)
            self._check_root(payload)
            receipt['status'] = 'upload_unknown'
            self._save(path, record)
            self._check_root(payload)
            uploaded = transport.upload(prepared, snapshot)
            if uploaded.get('status') != 'uploaded' or _identifier(uploaded.get('id', uploaded.get('file_upload_id'))) != _identifier(receipt['uploadId']):
                raise NotionSyncError('catalog_upload_unverified', '方案目录上传回执无法核对，不会自动重传。', unknown=True)
            receipt['status'] = 'uploaded_unattached'
            self._save(path, record)
            before_folder = rpc.call('fetch', {'id': record['pageId']})
            before = self._refs(before_folder)
            # Reuse an identical catalogue appended by another device while our
            # upload was in flight, without adding a duplicate folder entry.
            concurrent = self._read_catalog(rpc, transport, before_folder)
            if concurrent['sha256'] == digest:
                receipt.update(status='verified', reference=concurrent['reference'], verifiedAt=_now())
                self._save(path, record, catalog={'status': 'verified', 'sha256': digest,
                    'reference': concurrent['reference'], 'filename': concurrent['filename']})
                return
            if concurrent['sha256'] != latest['sha256']:
                # The prepared bytes do not contain this newer remote metadata.
                # Keep their upload receipt instead of overwriting its entries.
                raise NotionSyncError('catalog_changed_during_upload', 'Notion 方案目录刚有更新；原图保留，请核对后重新同步。')
            receipt['status'] = 'attach_unknown'
            self._save(path, record)
            self._check_root(payload)
            page_rows = self._attach_asset(payload, record, rpc, transport, before_folder, receipt, uploaded, merged)
            receipt['status'] = 'attached_unverified'
            self._save(path, record, phase='verifying', message='正在回读核对方案目录。')
            after = rpc.call('fetch', {'id': record['pageId']})
            self._verify_page_rows(rpc, transport, after, page_rows)
            candidates = [ref for ref in self._refs(after) if ref not in before and _same_catalog_name(_reference_name(ref), name)]
            for reference in candidates:
                returned = self._download(rpc, transport, reference, maximum=MAX_CATALOG_BYTES)
                _parse_catalog(returned, digest)
                if returned == data:
                    receipt.update(status='verified', reference=reference, verifiedAt=_now())
                    self._save(path, record, catalog={'status': 'verified', 'sha256': digest,
                        'reference': reference, 'filename': name})
                    return
            raise NotionSyncError('catalog_attached_unverified', '方案目录已附页但原件完整性尚未核实，不会重复上传。', unknown=True)
        finally:
            snapshot.unlink(missing_ok=True)

    def _reconcile_catalog(self, payload, path, record, rpc, transport, folder):
        """Finish one existing delivery receipt with read-only tool calls.

        Do not scan the library, inspect later files, merge current annotations,
        prepare another upload, or append a folder entry in this path.
        """
        operation = record['operation']
        started, finished = operation.get('startedAt'), operation.get('finishedAt')
        pending = []
        for row in record['receipts']:
            if row.get('direction') != 'catalog' or row.get('status') not in {'attached_unverified', 'verified'}:
                continue
            if row.get('requestId') == operation['requestId']:
                pending.append(row)
            elif not row.get('requestId') and isinstance(row.get('createdAt'), str) and started and finished:
                # Version 1.1.34 recorded the original creation boundary but did
                # not yet repeat the request id on the individual receipt.
                try:
                    parse = lambda value: datetime.fromisoformat(value.replace('Z', '+00:00'))
                    if parse(started) <= parse(row['createdAt']) <= parse(finished):
                        pending.append(row)
                except (ValueError, TypeError):
                    pass
        if len(pending) != 1:
            raise NotionSyncError('catalog_receipt_identity_unverified', '无法唯一核对原目录请求；未发送任何新上传。', unknown=True)
        receipt = pending[0]
        identity = _catalog_identity(receipt.get('filename'))
        if (not identity or identity[1] != receipt.get('sha256') or not _identifier(receipt.get('uploadId'))
                or type(receipt.get('size')) is not int or not 0 < receipt['size'] <= MAX_CATALOG_BYTES):
            raise NotionSyncError('catalog_receipt_identity_unverified', '原目录上传回执身份不完整；未发送任何新上传。', unknown=True)
        candidates = [reference for reference in self._refs(folder)
            if _same_catalog_name(_reference_name(reference), receipt['filename'])]
        if not candidates:
            raise NotionSyncError('catalog_attached_unverified', '原目录附件尚未出现在回读中；保留原请求，不重新上传。', unknown=True)
        expected = {item.get('sha256') for item in operation.get('items', [])}
        if any(not isinstance(value, str) or not SHA_RE.fullmatch(value) for value in expected):
            raise NotionSyncError('catalog_receipt_identity_unverified', '原图片请求身份无法核对；未发送任何新上传。', unknown=True)
        self._save(path, record, phase='verifying', message='正在下载核对原目录的字节与哈希。')
        for reference in candidates:
            data = self._download(rpc, transport, reference, maximum=MAX_CATALOG_BYTES)
            entries = _parse_catalog(data, receipt['sha256'])
            if len(data) != receipt['size'] or not expected <= set(entries):
                raise NotionSyncError('catalog_receipt_identity_unverified', '回读目录与原请求不匹配；未发送任何新上传。', unknown=True)
            if folder.get('metadata', {}).get('type') == 'page':
                rows = self._page_rows(rpc, transport, folder, entries)
                self._verify_page_rows(rpc, transport, folder, rows)
            snapshot = operation.get('exportSnapshot')
            latest_catalog = self._read_catalog(rpc, transport, folder) if _export_rows(snapshot) is not None else None
            proven_snapshot = (_snapshot_matches_catalog(snapshot, entries) and latest_catalog is not None
                               and _snapshot_matches_catalog(snapshot, latest_catalog['entries']))
            originals = self._verify_attached_originals(record, rpc, transport, folder) if payload.get('_verifyOriginals') or proven_snapshot else None
            self._check_root(payload)
            receipt.update(status='verified', reference=reference, verifiedAt=_now())
            operation.pop('code', None)
            remaining = ['device'] if payload.get('target') == 'all' and self.service.state().get('deviceRoot') else []
            self._save(path, record, status='completed', phase='finished', completedTargets=['notion'],
                remainingTargets=remaining, catalog={'status':'verified','sha256':receipt['sha256'],
                    'reference':reference,'filename':_reference_name(reference)},
                verifiedOriginals=originals,
                exportCatalogSha256=receipt['sha256'] if proven_snapshot else None,
                message='原件与方案目录已回读核实；沿用原请求，未重传原图或目录。' if originals is not None
                    else '原方案目录已回读核实；沿用原请求，未重传原图或目录。', finishedAt=_now())
            return

    def _verify_attached_originals(self, record, rpc, transport, folder):
        present = set(_image_refs(folder))
        verified = {}
        page_originals = None
        for item in record['operation']['items']:
            digest = item['sha256']
            if digest in verified:
                continue
            candidates = [item.get('reference')] if item.get('reference') in present else []
            candidates.extend(row['reference'] for row in record['receipts']
                if row.get('direction') in {'upload','download'} and row.get('status') == 'verified'
                and row.get('sha256') == digest and row.get('reference') in present)
            if not candidates:
                # Native page edits can copy the same uploaded file into a new
                # block UUID. Reconcile its real bytes, never infer from a label.
                if page_originals is None:
                    page_originals = self._remote_hashes(rpc, transport, folder, record)
                if digest in page_originals:
                    candidates.append(page_originals[digest])
            if not candidates:
                raise NotionSyncError('verified_original_missing', '原请求的原件引用尚未核实；没有发送新上传。', unknown=True)
            reference = candidates[0]
            data = self._download(rpc, transport, reference)
            sizes = [row.get('size') for row in [item, *record['receipts']]
                if row.get('sha256') == digest and type(row.get('size')) is int]
            if hashlib.sha256(data).hexdigest() != digest or (sizes and len(data) not in sizes):
                raise NotionSyncError('verified_original_hash_mismatch', '回读原件与原请求不一致；保留原回执，没有重新上传。')
            verified[digest] = {'sha256':digest, 'size':len(data), 'reference':reference}
        return list(verified.values())

    def _run(self, payload, path, record, held):
        try:
            current = self._check_root(payload)
            with self.rpc_factory(current['root'], record['pageId']) as rpc:
                folder = rpc.call('fetch', {'id': record['pageId']})
                record['bridgeVerifiedAt'] = _now()
                self._save(path, record, phase='reading', message='正在核对原件与已保存版本。')
                transport = self.transfer_factory()
                if payload.get('_reconcileCatalog'):
                    self._reconcile_catalog(payload, path, record, rpc, transport, folder)
                elif payload.get('source') == 'notion':
                    self._pull(payload, path, record, rpc, transport, folder)
                else:
                    self._push(payload, path, record, rpc, transport, folder)
        except NotionSyncError as error:
            self._save(path, record, status='unknown' if error.unknown else 'failed',
                phase='finished', code=error.code, message=str(error), finishedAt=_now())
        except Exception:
            # Arbitrary subprocess/HTTP errors can contain short-lived auth
            # headers or signed URLs. Never put their repr into user records.
            if not self._preserve_verified_completion(path, record):
                self._save(path, record, status='failed', phase='finished', code='notion_sync_failed',
                    message='图片同步未完成；原图与请求记录已保留。', finishedAt=_now())
        finally:
            _release_file_lock(held)

    def _push(self, payload, path, record, rpc, transport, folder):
        current = self._check_root(payload)
        items = self._export_items(current)
        if current.get('standardNaming') and any(
                item.get('namingNeedsReview') or not item.get('standardType')
                for item in items if item.get('space', 'root') == 'root'
                and item.get('path', '').split('/')[0].casefold() not in {'inbox', '.image-manager'}):
            raise NotionSyncError('standard_naming_required',
                '有图片尚未确认标准用途；请先选择用途并完成命名，再同步到 Notion。未上传任何新原图或方案目录。')
        if len(items) > MAX_BATCH:
            raise NotionSyncError('local_batch_limit', '单批最多同步 50 张已入库图片。')
        # Freeze the bytes, actual basename and export semantics before the first
        # upload. A later edit can never be credited to this earlier request.
        self._save(path, record, exportSnapshot=self._export_snapshot(current))
        remote = self._remote_hashes(rpc, transport, folder, record)
        catalog = self._read_catalog(rpc, transport, folder)
        local_entries = {item['sha256']: _entry(item) for item in items
            if item.get('space', 'root') == 'root'
            and item.get('path', '').split('/')[0].casefold() not in {'inbox', '.image-manager'}}
        if len(set(remote) | set(local_entries)) > MAX_BATCH:
            raise NotionSyncError('notion_batch_limit', '本次图库合并后超过单批 50 张原图限制。')
        _validate_entries(catalog['entries'], known=set(remote) | set(local_entries))
        planned_entries = dict(catalog['entries'])
        planned_entries.update(local_entries)
        _validate_entries(planned_entries, known=set(remote) | set(local_entries))
        for metadata in items:
            self._check_root(payload)
            if metadata.get('space', 'root') != 'root' or metadata.get('path', '').split('/')[0].casefold() in {'inbox', '.image-manager'}:
                continue
            digest = metadata.get('sha256')
            image = self.service.image(metadata['path'], payload['expectedRoot'], space='root')
            source = Path(image['path'])
            if source.stat().st_size > MAX_FILE_BYTES:
                raise NotionSyncError('notion_original_too_large', '单张原件超过 Notion 的 20 MiB 同步限制，未缩图。')
            with source.open('rb') as original:
                data = original.read(MAX_FILE_BYTES + 1)
            if len(data) != metadata.get('size') or hashlib.sha256(data).hexdigest() != digest:
                raise NotionSyncError('local_original_changed', '图片已改变，请重新检查图库后同步。')
            if digest in remote:
                for receipt in record['receipts']:
                    if receipt.get('sha256') == digest and receipt.get('status') != 'verified':
                        receipt.update(status='verified', reference=remote[digest], verifiedAt=_now())
                record['operation']['items'].append({'name': metadata['name'], 'status': 'unchanged', 'sha256': digest})
                self._save(path, record)
                continue
            existing = [x for x in record['receipts'] if x.get('sha256') == digest and x.get('direction') == 'upload']
            blocked = next((x for x in existing if x.get('status') in {'upload_preparing', 'upload_unknown', 'uploaded_unattached', 'attach_unknown', 'attached_unverified'}), None)
            if blocked:
                raise NotionSyncError('upload_receipt_unresolved', '此原件已有未核实的上传请求，已保留同一编号；请先核对，不会重复上传。', unknown=True)
            # A different device may have appended this original after our first
            # read. Check again just before preparing its one-time upload.
            latest = rpc.call('fetch', {'id': record['pageId']})
            remote.update(self._remote_hashes(rpc, transport, latest, record))
            if digest in remote:
                for receipt in record['receipts']:
                    if receipt.get('sha256') == digest and receipt.get('status') != 'verified':
                        receipt.update(status='verified', reference=remote[digest], verifiedAt=_now())
                record['operation']['items'].append({'name': metadata['name'], 'status': 'unchanged', 'sha256': digest})
                self._save(path, record)
                continue
            receipt = {'id': uuid.uuid4().hex, 'name': metadata['name'], 'filename': _sync_name(metadata, items),
                'path': metadata['path'], 'sha256': digest, 'size': len(data), 'width': metadata.get('width'),
                'height': metadata.get('height'), 'direction': 'upload', 'status': 'upload_preparing',
                'metadata': _entry(metadata), 'createdAt': _now()}
            record['receipts'].append(receipt)
            self._save(path, record, phase='uploading', message='正在保存原件到 Notion。')
            snapshot = self.directory / ('original-' + receipt['id'] + source.suffix.lower())
            try:
                with snapshot.open('xb') as output:
                    output.write(data)
                self._check_root(payload)
                prepared = rpc.call('prepare', {'filename': receipt['filename']})
                receipt['uploadId'] = prepared.get('file_upload_id')
                receipt['status'] = 'upload_pending'
                self._save(path, record)
                self._check_root(payload)
                receipt['status'] = 'upload_unknown'
                self._save(path, record)
                self._check_root(payload)
                uploaded = transport.upload(prepared, snapshot)
                if uploaded.get('status') != 'uploaded' or _identifier(uploaded.get('id', uploaded.get('file_upload_id'))) != _identifier(receipt['uploadId']):
                    raise NotionSyncError('upload_response_invalid', '原件上传回执不匹配，未重复发送。', unknown=True)
                receipt['status'] = 'uploaded_unattached'
                self._save(path, record)
                self._check_root(payload)
                # Re-read immediately before appending; this never removes or
                # replaces existing files and keeps another writer's additions.
                before_entity = rpc.call('fetch', {'id': record['pageId']})
                before = self._refs(before_entity)
                receipt['status'] = 'attach_unknown'
                self._save(path, record)
                self._check_root(payload)
                page_rows = self._attach_asset(payload, record, rpc, transport, before_entity, receipt, uploaded, planned_entries)
                receipt['status'] = 'attached_unverified'
                self._save(path, record, phase='verifying', message='正在回读核对原图。')
                folder = rpc.call('fetch', {'id': record['pageId']})
                self._verify_page_rows(rpc, transport, folder, page_rows)
                additions = [ref for ref in self._refs(folder) if ref not in before]
                matched = None
                for reference in additions:
                    returned = self._download(rpc, transport, reference)
                    if len(returned) == len(data) and hashlib.sha256(returned).hexdigest() == digest:
                        matched = reference
                        break
                if matched is None:
                    raise NotionSyncError('attached_original_unverified', 'Notion 已接收附页请求，原件完整性尚未核实；不会重传。', unknown=True)
                receipt.update(status='verified', reference=matched, verifiedAt=_now())
                remote[digest] = matched
                record['operation']['items'].append({k: v for k, v in receipt.items() if k not in {'path'}})
                self._save(path, record)
            finally:
                snapshot.unlink(missing_ok=True)
        self._publish_catalog(payload, path, record, rpc, transport, local_entries)
        extra_device = bool(current.get('deviceRoot') and payload.get('target') == 'all')
        self._save(path, record, status='completed', phase='finished', completedTargets=['notion'],
            remainingTargets=['device'] if extra_device else [],
            exportCatalogSha256=(record['operation'].get('catalog') or {}).get('sha256'),
            message='Notion 原件与方案目录已保存并回读核对。' + ('设备文件夹仍需独立同步预览。' if extra_device else ''), finishedAt=_now())

    def _pull(self, payload, path, record, rpc, transport, folder):
        refs = _image_refs(folder)
        if len(refs) > MAX_BATCH:
            raise NotionSyncError('notion_batch_limit', '每批最多导入 50 张 Notion 原图。')
        current = self._check_root(payload)
        local = self._check_local_originals(current, payload)
        catalog = self._read_catalog(rpc, transport, folder)
        cached = {item.get('reference'): item.get('sha256') for item in record['receipts']
            if item.get('status') == 'verified' and item.get('reference')}
        remote = set()
        files, incoming = [], []
        total = 0
        for reference in refs:
            self._check_root(payload)
            name = _reference_name(reference)
            if Path(name).suffix.lower() not in EXTENSIONS or Path(name).name != name or '/' in name or '\\' in name:
                continue
            if cached.get(reference) in local:
                remote.add(cached[reference])
                continue
            data = self._download(rpc, transport, reference)
            digest = hashlib.sha256(data).hexdigest()
            remote.add(digest)
            if digest in local:
                continue
            total += len(data)
            if total > 96 * 1024 * 1024:
                raise NotionSyncError('notion_batch_too_large', '本批原件超过 96 MiB，请分批导入。')
            files.append((name, data))
            incoming.append({'reference': reference, 'sha256': digest, 'name': name, 'size': len(data)})
            local.add(digest)
        _validate_entries(catalog['entries'], known=remote | local)
        combined = {digest: _entry(item) for digest, item in self._local_metadata(current).items() if digest in local}
        combined.update(catalog['entries'])
        _validate_entries(combined, known=remote | local)
        self._check_root(payload)
        plan = None
        if files:
            plan = self.service.import_files(files, {'expectedRoot': payload['expectedRoot']})
            for item in incoming:
                record['receipts'].append(dict(item, direction='download', status='verified', verifiedAt=_now()))
            self._save(path, record, planId=plan.get('planId'), items=incoming)
        annotations = None
        if catalog['sha256'] is not None:
            self._check_root(payload)
            annotations = self.service.import_annotations({'expectedRoot': payload['expectedRoot'],
                'entries': [dict(sha256=digest, **row) for digest, row in catalog['entries'].items()]})
            self._save(path, record, catalog={'status': 'applied', 'sha256': catalog['sha256'],
                'reference': catalog['reference'], 'filename': catalog['filename']},
                annotations={key: annotations.get(key) for key in ('applied', 'skipped', 'unresolved')})
        unresolved = bool(annotations and annotations.get('unresolved'))
        self._save(path, record, status='needs_review' if files else 'completed', phase='finished',
            message=('原图已进入 inbox；确认预览后才会整理或替换。' if files else '原图已在本地图库中，没有重复导入。')
                + ('方案目录已恢复。' if annotations is not None else '')
                + ('部分派生来源尚未在本地，已保留待关联记录。' if unresolved else ''), finishedAt=_now())

    def wait(self, timeout=None):
        worker = self.worker
        if worker:
            worker.join(timeout)
        return self.state()
