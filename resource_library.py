"""A small, local resource catalogue with explicit, bounded public-API searches.

Browsing never contacts a provider. Searches keep candidates; only a user's save
changes a selection. No resource downloads, background polling, or API keys.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import threading
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request
import uuid

from resource_catalogs import CATALOG_PROVIDERS, search_catalog


STORE_RELATIVE = '游戏资源/.console-resources/library.json'
LOCK_RELATIVE = '游戏资源/.console-resources/library.lock'
MAX_STORE_BYTES = 4 * 1024 * 1024
MAX_API_BYTES = 12 * 1024 * 1024
MAX_HTML_BYTES = 3 * 1024 * 1024
MAX_ITEMS = 5000
MAX_SEARCHES = 1000
MAX_PROVENANCE = 2000
SEARCH_TIMEOUT = 12
KINDS = {'model', 'texture', 'hdri', 'vfx', 'other'}
STATUSES = {'candidate', 'saved', 'planned'}
PROVIDERS = [
    {'id': 'sketchfab', 'name': 'Sketchfab', 'kinds': ['model'], 'mode': 'api', 'defaultKind': 'model',
     'note': '公開可下載模型；逐項核對許可，下載仍需帳戶。'},
    {'id': 'polyhaven', 'name': 'Poly Haven', 'kinds': ['model', 'texture', 'hdri'], 'mode': 'api', 'defaultKind': 'model',
     'note': '官方資源列表與縮圖，CC0。'},
] + CATALOG_PROVIDERS + [
    {'id': 'itchio', 'name': 'itch.io', 'kinds': ['model', 'texture', 'vfx', 'other'],
     'mode': 'external', 'defaultKind': 'other', 'searchUrlTemplate': 'https://itch.io/search?q={query}&facets=c.2',
     'note': '開啟來源搜尋頁；選中公開資源網址後可預覽並保存。'},
    {'id': 'unity', 'name': 'Unity Asset Store', 'kinds': ['model', 'texture', 'vfx', 'other'],
     'mode': 'external', 'defaultKind': 'vfx', 'searchUrlTemplate': 'https://marketplace.unity.com/search?q={query}',
     'note': '開啟來源搜尋頁；選中公開資源網址後可預覽並保存。'},
    {'id': 'fab', 'name': 'Fab', 'kinds': ['model', 'texture', 'hdri', 'vfx', 'other'],
     'mode': 'external', 'defaultKind': 'model', 'searchUrlTemplate': 'https://www.fab.com/search?q={query}',
     'note': '開啟來源搜尋頁；選中公開資源網址後可預覽並保存。'},
    {'id': 'cgtrader', 'name': 'CGTrader', 'kinds': ['model'],
     'mode': 'external', 'defaultKind': 'model', 'searchUrlTemplate': 'https://www.cgtrader.com/search?keywords={query}',
     'note': '開啟來源搜尋頁；選中公開資源網址後可預覽並保存。'},
]
QUERY_WORDS = {'地球': 'earth', '角色': 'character', '人物': 'character',
               '房屋': 'house', '房子': 'house', '椅子': 'chair',
               '石头': 'rock', '石頭': 'rock', '木头': 'wood', '木頭': 'wood',
               '树木': 'tree', '樹木': 'tree', '植物': 'plant', '金属': 'metal',
               '金屬': 'metal', '天空': 'sky'}


class ResourceLibraryError(ValueError):
    status = 400

    def __init__(self, message, *, status=None):
        super().__init__(message)
        if status is not None:
            self.status = status


class ResourceLibraryConflict(ResourceLibraryError):
    status = 409


def _now():
    return datetime.now(timezone.utc).isoformat()


def _text(value, label, limit=1000, required=False):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ResourceLibraryError(f'{label}格式無效或超過 {limit} 字。')
    value = value.strip()
    if required and not value:
        raise ResourceLibraryError(f'請填寫{label}。')
    return value


def public_https_url(value, *, required=True):
    """Validate a display URL; this function performs no DNS or HTTP requests."""
    value = _text(value, '來源網址', 4096, required=required)
    if not value and not required:
        return ''
    if '\\' in value or any(ord(c) < 33 for c in value) or re.search(r'%(?:00|0a|0d)', value, re.I):
        raise ResourceLibraryError('來源與預覽只接受公開 HTTPS 網址。')
    try:
        parts = urlsplit(value)
        host = (parts.hostname or '').rstrip('.').encode('idna').decode('ascii').lower()
        port = parts.port
    except (ValueError, UnicodeError) as exc:
        raise ResourceLibraryError('來源網址無效。') from exc
    if parts.scheme.lower() != 'https' or not host or parts.username is not None or parts.password is not None or port not in (None, 443):
        raise ResourceLibraryError('來源與預覽只接受無帳密的公開 HTTPS 網址。')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')) or '%' in host:
        raise ResourceLibraryError('來源網址不能指向本機或內網。')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # Reject alternate integer/octal/hex IP forms as well as bare hostnames.
        if '.' not in host or re.fullmatch(r'[\d.]+', host) or host.startswith('0x'):
            raise ResourceLibraryError('來源網址必須使用公開網域。')
        if not re.fullmatch(r'[a-z0-9.-]+', host) or any(not label or label.startswith('-') or label.endswith('-') for label in host.split('.')):
            raise ResourceLibraryError('來源網域格式無效。')
        netloc = host
    else:
        if not address.is_global:
            raise ResourceLibraryError('來源網址不能指向本機或內網。')
        netloc = '[' + host + ']' if address.version == 6 else host
    query = [(key, item) for key, item in parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith('utm_') and key.lower() not in {'fbclid', 'gclid', 'msclkid', 'mc_cid', 'mc_eid'}]
    return urlunsplit(('https', netloc, parts.path or '/', urlencode(sorted(query)), ''))


def _sketchfab_uid(value):
    # The official API returns both 32-hex UIDs and case-sensitive, alphanumeric
    # legacy UIDs (e.g. Future Car has a 27-character UID). UIDs are opaque tokens.
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9]{1,64}', value):
        return None
    return value.lower() if re.fullmatch(r'[a-fA-F0-9]{32}', value) else value


def _sketchfab_path_uid(path):
    if path.startswith('/models/') and '/' not in path[len('/models/'):]:
        return _sketchfab_uid(path[len('/models/'):])
    if path.startswith('/3d-models/') and '/' not in path[len('/3d-models/'):]:
        slug = path[len('/3d-models/'):]
        return _sketchfab_uid(slug.rsplit('-', 1)[-1]) if '-' in slug else None
    return None


def _api_provider_ids():
    return {p['id'] for p in PROVIDERS if p.get('mode', 'api') == 'api'}


def canonical_resource(value):
    """Return stable source identity and its canonical, human-openable URL."""
    url = public_https_url(value)
    parts = urlsplit(url)
    host, path = parts.hostname, parts.path.rstrip('/')
    if host in {'assetstore.unity.com', 'marketplace.unity.com'}:
        match = re.search(r'/packages/(?:.*-)?(\d+)$', path)
        if match:
            return 'unity:' + match.group(1), urlunsplit(('https', 'marketplace.unity.com', path, '', ''))
    if host in {'sketchfab.com', 'www.sketchfab.com'}:
        uid = _sketchfab_path_uid(path)
        if uid:
            return 'sketchfab:' + uid, 'https://sketchfab.com/models/' + uid
    if host in {'polyhaven.com', 'www.polyhaven.com'}:
        match = re.fullmatch(r'/a/([a-zA-Z0-9_-]+)', path)
        if match:
            slug = match.group(1).lower()
            return 'polyhaven:' + slug, 'https://polyhaven.com/a/' + slug
    url = urlunsplit((parts.scheme, parts.netloc, path or '/', parts.query, ''))
    return 'url:' + url, url


def _legacy_sketchfab_identity(value):
    """Read an old manually saved legacy-UID URL without changing its stored ID."""
    url = public_https_url(value)
    parts = urlsplit(url)
    if parts.hostname not in {'sketchfab.com', 'www.sketchfab.com'}:
        return None
    uid = _sketchfab_path_uid(parts.path.rstrip('/'))
    if uid and not re.fullmatch(r'[a-fA-F0-9]{32}', uid):
        return 'url:' + urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip('/') or '/', parts.query, ''))
    return None


def _identifier(identity):
    return hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]


def _known_metadata(key, value):
    """Distinguish a real selection from the manual form's unknown defaults."""
    if key == 'kind':
        return value != 'other'
    normalized = value.strip().casefold()
    if not normalized or normalized in {'unknown', 'unverified', 'not specified',
            'to verify', 'n/a', '未知', '未標明', '未标明', '待確認', '待确认',
            '待核對', '待核对', '尚未核實', '尚未核实', '未核實', '未核实'}:
        return False
    if key in {'license', 'price'} and any(marker in normalized for marker in
            ('待核對', '待核对', '未標明', '未标明', '未核實', '未核实')):
        return False
    return True


def _query(value):
    value = _text(value, '搜尋詞', 120, required=True)
    value = re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value)).strip()
    value = _text(value, '搜尋詞', 120, required=True)
    return value, value.casefold()


def _search_query(value):
    # A visible literal dictionary, not an AI or semantic search claim.
    result = value
    for word, replacement in QUERY_WORDS.items():
        result = result.replace(word, ' ' + replacement + ' ')
    return _text(re.sub(r'\s+', ' ', result).strip(), '實際搜尋詞', 240, required=True)


def _provenance(value):
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    if len(values) > MAX_PROVENANCE:
        raise ResourceLibraryError(f'來源記錄最多 {MAX_PROVENANCE} 項。')
    result = []
    for entry in values:
        if isinstance(entry, str):
            entry = _text(entry, '來源記錄', 2000, required=True)
        elif isinstance(entry, dict):
            if len(entry) > 20 or any(not isinstance(k, str) or not isinstance(v, (str, int, float, bool, type(None))) for k, v in entry.items()):
                raise ResourceLibraryError('來源記錄格式無效。')
            try:
                encoded = json.dumps(entry, ensure_ascii=False, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise ResourceLibraryError('來源記錄格式無效。') from exc
            if len(encoded) > 4000:
                raise ResourceLibraryError('來源記錄過長。')
        else:
            raise ResourceLibraryError('來源記錄格式無效。')
        if entry not in result:
            result.append(entry)
    return result


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ResourceLibraryError('資源服務返回轉址，本次搜尋未保存；請稍後重試。', status=502)


def _fetch_json(url):
    # Only callers below construct URLs, always at these fixed official APIs.
    parts = urlsplit(url)
    allowed = {('api.sketchfab.com', '/v3/search'), ('api.polyhaven.com', '/assets'),
               ('ambientcg.com', '/api/v3/assets')}
    if parts.scheme != 'https' or (parts.netloc, parts.path) not in allowed or parts.fragment:
        raise ResourceLibraryError('不支援的資源服務。')
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'CodexConsole/ResourceLibrary'})
    try:
        with build_opener(_NoRedirect()).open(request, timeout=SEARCH_TIMEOUT) as response:
            raw = response.read(MAX_API_BYTES + 1)
        if len(raw) > MAX_API_BYTES:
            raise ResourceLibraryError('資源服務回應超過讀取上限，本次搜尋未保存。', status=502)
        return json.loads(raw.decode('utf-8'))
    except HTTPError as exc:
        reason = '請求過於頻繁，請稍後重試' if exc.code == 429 else f'HTTP {exc.code}'
        raise ResourceLibraryError(f'資源服務搜尋失敗（{reason}），本次結果未保存。', status=502) from exc
    except (URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResourceLibraryError('資源服務連線或回應失敗，本次搜尋未保存；請稍後重試。', status=502) from exc


def _fetch_text(url):
    """Fetch fixed catalogue listing routes; never a supplied resource URL."""
    parts = urlsplit(url)
    allowed = {('kenney.nl', '/assets'), ('kenney.nl', '/assets/category:3D'),
               ('kenney.nl', '/assets/category:2D'), ('kenney.nl', '/assets/category:Textures'),
               ('kenney.nl', '/assets/series:VFX'), ('opengameart.org', '/art-search-advanced')}
    if parts.scheme != 'https' or (parts.netloc, parts.path) not in allowed or parts.fragment:
        raise ResourceLibraryError('不支援的資源目錄。')
    request = Request(url, headers={'Accept': 'text/html,application/xhtml+xml;q=0.9',
                                   'User-Agent': 'CodexConsole/ResourceLibrary'})
    try:
        with build_opener(_NoRedirect()).open(request, timeout=SEARCH_TIMEOUT) as response:
            raw = response.read(MAX_HTML_BYTES + 1)
        if len(raw) > MAX_HTML_BYTES:
            raise ResourceLibraryError('資源目錄回應超過讀取上限，本次搜尋未保存。', status=502)
        return raw.decode('utf-8-sig')
    except HTTPError as exc:
        reason = '請求過於頻繁，請稍後重試' if exc.code == 429 else f'HTTP {exc.code}'
        raise ResourceLibraryError(f'資源目錄搜尋失敗（{reason}），本次結果未保存。', status=502) from exc
    except (URLError, TimeoutError, OSError, UnicodeError) as exc:
        raise ResourceLibraryError('資源目錄連線或回應失敗，本次搜尋未保存；請稍後重試。', status=502) from exc


class ResourceLibraryService:
    def __init__(self, document_library):
        self.documents = document_library
        self._lock = threading.RLock()

    @contextmanager
    def _scope(self, expectedRoot='', *, write=False):
        if write and (not isinstance(expectedRoot, str) or not expectedRoot.strip()):
            raise ResourceLibraryConflict('資料庫身份缺失，請重新開啟資源頁。')
        try:
            with self._lock, self.documents._document_scope(expectedRoot or None) as root:
                yield root
        except (ResourceLibraryError, PermissionError):
            raise
        except (ValueError, OSError, RuntimeError) as exc:
            # Keep the companion's authorization status and response headers.
            if hasattr(exc, 'status'):
                raise
            if '切換' in str(exc) or '路徑無效' in str(exc):
                raise ResourceLibraryConflict(str(exc)) from exc
            raise ResourceLibraryError(str(exc)) from exc

    def _path(self, relative=STORE_RELATIVE):
        root, path = self.documents._path(relative)
        direct = root / relative
        if path != direct:
            raise ResourceLibraryError('資源索引與目錄不能是檔案連結。')
        current = direct
        while current != root:
            if current.is_symlink() or getattr(current, 'is_junction', lambda: False)():
                raise ResourceLibraryError('資源索引與目錄不能是檔案連結。')
            current = current.parent
        return path

    def _load(self):
        path = self._path()
        if not path.exists():
            return {'version': 1, 'revision': 0, 'items': [], 'searches': []}
        try:
            with path.open('rb') as source:
                raw = source.read(MAX_STORE_BYTES + 1)
            if len(raw) > MAX_STORE_BYTES:
                raise ResourceLibraryError('資源索引超過 4 MiB。')
            data = json.loads(raw.decode('utf-8-sig'))
            self._validate(data)
            return data
        except (ValueError, OSError, UnicodeError) as exc:
            raise ResourceLibraryError(f'資源索引無法讀取，原檔案已保留：{exc}') from exc

    @staticmethod
    def _validate(data):
        if not isinstance(data, dict) or data.get('version') != 1 or type(data.get('revision')) is not int or not 0 <= data['revision'] <= 2 ** 53 - 2:
            raise ResourceLibraryError('資源索引格式無效。')
        if not isinstance(data.get('items'), list) or len(data['items']) > MAX_ITEMS or not isinstance(data.get('searches'), list) or len(data['searches']) > MAX_SEARCHES:
            raise ResourceLibraryError('資源索引項目格式或數量無效。')
        seen = set()
        api_providers = _api_provider_ids()
        for item in data['items']:
            if not isinstance(item, dict):
                raise ResourceLibraryError('資源項目格式無效。')
            identity, url = canonical_resource(item.get('url', ''))
            stored_identity = item.get('identity')
            if stored_identity not in (identity, _legacy_sketchfab_identity(item.get('url', ''))) or not isinstance(stored_identity, str) or item.get('id') != _identifier(stored_identity) or stored_identity in seen:
                raise ResourceLibraryError('資源身份重複或無效。')
            seen.add(stored_identity)
            if not all(isinstance(item.get(key), str) for key in ('status', 'kind', 'provider')) or item['status'] not in STATUSES or item['kind'] not in KINDS or item['provider'] not in api_providers | {'manual'}:
                raise ResourceLibraryError('資源分類或狀態無效。')
            _text(item.get('name'), '資源名稱', 240, required=True)
            for key, limit in [('description', 4000), ('license', 1000), ('price', 1000), ('notes', 4000)]:
                _text(item.get(key), key, limit)
            public_https_url(item.get('previewUrl'), required=False)
            for key in ('createdAt', 'updatedAt'):
                _text(item.get(key), key, 100, required=True)
            if not isinstance(item.get('provenance'), list):
                raise ResourceLibraryError('來源記錄格式無效。')
            _provenance(item['provenance'])
            if not isinstance(item.get('queries'), list) or len(item['queries']) > 1000:
                raise ResourceLibraryError('搜尋來源記錄無效。')
            for query in item['queries']:
                if not isinstance(query, dict) or not isinstance(query.get('provider'), str) or not isinstance(query.get('kind'), str) or query['provider'] not in api_providers or query['kind'] not in KINDS:
                    raise ResourceLibraryError('搜尋來源記錄無效。')
                _query(query.get('query'))
                _text(query.get('searchQuery'), '實際搜尋詞', 240, required=True)
        ids = {_identifier(identity) for identity in seen}
        search_keys = set()
        for search in data['searches']:
            if not isinstance(search, dict) or not isinstance(search.get('provider'), str) or not isinstance(search.get('kind'), str) or search['provider'] not in api_providers or search['kind'] not in KINDS:
                raise ResourceLibraryError('搜尋快取格式無效。')
            query, normalized = _query(search.get('query'))
            key = (search['provider'], search['kind'], normalized)
            if key in search_keys:
                raise ResourceLibraryError('搜尋快取包含重複身份。')
            search_keys.add(key)
            _text(search.get('searchQuery'), '實際搜尋詞', 240, required=True)
            _text(search.get('searchTime'), '搜尋時間', 100, required=True)
            if not isinstance(search.get('itemIds'), list) or len(search['itemIds']) > 24 or any(not isinstance(i, str) or i not in ids for i in search['itemIds']):
                raise ResourceLibraryError('搜尋快取引用無效。')
            if type(search.get('skippedCount', 0)) is not int or not 0 <= search.get('skippedCount', 0) <= 24:
                raise ResourceLibraryError('搜尋略過數量無效。')
            warnings = search.get('warnings', [])
            if not isinstance(warnings, list) or len(warnings) > 24:
                raise ResourceLibraryError('搜尋警告格式無效。')
            for warning in warnings:
                _text(warning, '搜尋警告', 400, required=True)

    @contextmanager
    def _write_lock(self):
        path = self._path(LOCK_RELATIVE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path = self._path(LOCK_RELATIVE)
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
                raise ResourceLibraryConflict('另一個 Console 正在保存資源，請稍後重試。') from exc
            try:
                yield
            finally:
                lock_file.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _write(self, data):
        self._validate(data)
        content = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
        if len(content) > MAX_STORE_BYTES:
            raise ResourceLibraryError('資源索引已達 4 MiB 上限，原資料已保留。')
        path = self._path()
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            with temporary.open('xb') as destination:
                destination.write(content)
                destination.flush()
                os.fsync(destination.fileno())
            path = self._path()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _commit(self, data, expectedRoot, base_revision, authorize):
        # Companion sessions take their own lock before the document lock. Run
        # authorization outside both locks, then pin the root again and compare
        # the revision under the cross-process file lock before the atomic write.
        if authorize is not None:
            authorize()
        with self._scope(expectedRoot, write=True) as root:
            with self._write_lock():
                self._revision(self._load(), base_revision)
                self._write(data)
                return root

    @staticmethod
    def _revision(data, value):
        if type(value) is not int or value != data['revision']:
            raise ResourceLibraryConflict('資源清單已更新，請重新載入後再確認。')

    @staticmethod
    def _result(root, data, items=None):
        return {'root': str(root), 'revision': data['revision'],
                'items': data['items'] if items is None else items, 'providers': PROVIDERS}

    def state(self, expectedRoot='', q='', kind='', status=''):
        q = _text(q, '篩選詞', 120).casefold()
        if not isinstance(kind, str) or not isinstance(status, str) or kind and kind not in KINDS or status and status not in STATUSES:
            raise ResourceLibraryError('資源篩選條件無效。')
        with self._scope(expectedRoot) as root:
            data = self._load()
            items = [i for i in data['items'] if (not kind or i['kind'] == kind) and (not status or i['status'] == status)
                     and (not q or q in ' '.join([i['name'], i['description'], i['url'], i['notes'], *[r['query'] for r in i['queries']]]).casefold())]
            return self._result(root, data, sorted(items, key=lambda i: (i['updatedAt'], i['id']), reverse=True))

    @staticmethod
    def _candidate(payload, provider='manual'):
        identity, url = canonical_resource(payload.get('url', ''))
        kind = payload.get('kind', 'other')
        if not isinstance(kind, str) or kind not in KINDS:
            raise ResourceLibraryError('資源類型無效。')
        now = _now()
        return {'id': _identifier(identity), 'identity': identity,
                'name': _text(payload.get('name', ''), '資源名稱', 240, required=True), 'url': url,
                'kind': kind, 'previewUrl': public_https_url(payload.get('previewUrl', ''), required=False),
                'description': _text(payload.get('description', ''), '資源說明', 4000),
                'license': _text(payload.get('license', ''), '許可', 1000),
                'price': _text(payload.get('price', ''), '價格', 1000),
                'provider': provider, 'status': 'candidate', 'notes': '', 'queries': [],
                'provenance': _provenance(payload.get('provenance')), 'createdAt': now, 'updatedAt': now}

    @staticmethod
    def _merge(data, incoming, *, manual=False):
        existing = next((i for i in data['items'] if i['identity'] == incoming['identity'] or
                         canonical_resource(i['url'])[0] == incoming['identity']), None)
        if existing is None:
            if len(data['items']) >= MAX_ITEMS:
                raise ResourceLibraryError('資源清單已達數量上限，原資料已保留。')
            data['items'].append(incoming)
            return incoming
        # Re-adding a source is a reuse operation, not an edit of a confirmed
        # resource. Manual imports may fill blanks or clarify unknown values.
        # Candidate metadata can still be checked before a user chooses it.
        for key in ('name', 'kind', 'previewUrl', 'description', 'license', 'price'):
            value = incoming[key]
            if not value:
                continue
            old_known, new_known = _known_metadata(key, existing[key]), _known_metadata(key, value)
            if existing['status'] == 'candidate':
                if new_known or not old_known:
                    existing[key] = value
            elif manual and (not existing[key] or not old_known and new_known):
                existing[key] = value
        for key in ('queries', 'provenance'):
            for entry in incoming[key]:
                if entry not in existing[key]:
                    existing[key].append(entry)
        existing['updatedAt'] = incoming['updatedAt']
        return existing

    def save(self, payload, authorize=None):
        if authorize is not None:
            authorize()
        if not isinstance(payload, dict):
            raise ResourceLibraryError('資源保存內容無效。')
        status = payload.get('status')
        if status is not None and (not isinstance(status, str) or status not in STATUSES):
            raise ResourceLibraryError('資源狀態無效。')
        with self._scope(payload.get('expectedRoot'), write=True) as root:
            data = self._load()
            self._revision(data, payload.get('expectedRevision'))
            base_revision = data['revision']
            if payload.get('id'):
                item = next((i for i in data['items'] if i['id'] == payload['id']), None)
                if item is None:
                    raise ResourceLibraryError('資源不存在，請重新載入。')
                if status is None and 'notes' not in payload:
                    raise ResourceLibraryError('請指定資源狀態或筆記。')
            else:
                item = self._merge(data, self._candidate(payload), manual=True)
            if status is not None:
                # Explicit id actions can change a user's selection in either
                # direction; source imports cannot downgrade an existing one.
                ranks = {'candidate': 0, 'saved': 1, 'planned': 2}
                if payload.get('id') or ranks[status] >= ranks[item['status']]:
                    item['status'] = status
            if 'notes' in payload:
                notes = _text(payload['notes'], '資源筆記', 4000)
                if payload.get('id') or not item['notes']:
                    item['notes'] = notes
                elif notes and notes != item['notes'] and notes not in item['notes'].split('\n\n'):
                    item['notes'] = _text(item['notes'] + '\n\n' + notes, '資源筆記', 4000)
            item['updatedAt'] = _now()
            data['revision'] += 1
        root = self._commit(data, payload.get('expectedRoot'), base_revision, authorize)
        return {**self._result(root, data), 'item': item}

    @staticmethod
    def _cached(data, provider, kind, normalized):
        return next((s for s in data['searches'] if s['provider'] == provider and s['kind'] == kind
                     and _query(s['query'])[1] == normalized), None)

    def _search_result(self, root, data, search, cached):
        by_id = {i['id']: i for i in data['items']}
        return {**self._result(root, data, [by_id[i] for i in search['itemIds']]),
                **{key: search[key] for key in ('query', 'searchQuery', 'provider', 'kind', 'searchTime')},
                'cached': cached, 'skippedCount': search.get('skippedCount', 0), 'warnings': search.get('warnings', [])}

    def search(self, payload, authorize=None):
        if authorize is not None:
            authorize()
        if not isinstance(payload, dict):
            raise ResourceLibraryError('搜尋內容無效。')
        query, normalized = _query(payload.get('q', ''))
        provider, kind = payload.get('provider', 'sketchfab'), payload.get('kind', 'model')
        if not any(p['id'] == provider and p.get('mode', 'api') == 'api' and kind in p['kinds'] for p in PROVIDERS):
            raise ResourceLibraryError('此來源不支援所選資源類型。')
        refresh = payload.get('refresh', False)
        count = payload.get('count', 12)
        if type(refresh) is not bool or type(count) is not int or not 1 <= count <= 24:
            raise ResourceLibraryError('搜尋數量或更新選項無效。')
        expected = payload.get('expectedRoot')
        with self._scope(expected, write=True) as root:
            data = self._load()
            cached = self._cached(data, provider, kind, normalized)
            if cached is not None and not refresh:
                return self._search_result(root, data, cached, True)
        actual_query = _search_query(query)
        provider_result = self._provider_search(provider, kind, actual_query, count)
        if isinstance(provider_result, list):
            candidates, skipped_count, warnings = provider_result, 0, []
        else:
            candidates = provider_result['items']
            skipped_count, warnings = provider_result['skippedCount'], provider_result['warnings']
        search_time = _now()
        if authorize is not None:
            authorize()
        with self._scope(expected, write=True) as root:
            data = self._load()
            if 'expectedRevision' in payload:
                self._revision(data, payload['expectedRevision'])
            base_revision = data['revision']
            # Another server may have completed the same explicit request.
            cached = self._cached(data, provider, kind, normalized)
            if cached is not None and not refresh:
                return self._search_result(root, data, cached, True)
            item_ids = []
            for candidate in candidates:
                candidate['queries'] = [{'provider': provider, 'query': query, 'kind': kind, 'searchQuery': actual_query}]
                candidate['provenance'].append({'provider': provider, 'query': query, 'searchQuery': actual_query, 'searchTime': search_time})
                item = self._merge(data, candidate)
                if item['id'] not in item_ids:
                    item_ids.append(item['id'])
            search = {'query': query, 'searchQuery': actual_query, 'provider': provider,
                      'kind': kind, 'searchTime': search_time, 'itemIds': item_ids,
                      'skippedCount': skipped_count, 'warnings': warnings}
            if cached:
                data['searches'].remove(cached)
            elif len(data['searches']) >= MAX_SEARCHES:
                # Eviction affects repeat-search cache only, never resources.
                data['searches'].pop(0)
            data['searches'].append(search)
            data['revision'] += 1
        root = self._commit(data, expected, base_revision, authorize)
        return self._search_result(root, data, search, False)

    def _provider_search(self, provider, kind, query, count):
        if provider in {p['id'] for p in CATALOG_PROVIDERS}:
            try:
                rows = search_catalog(provider, kind, query, count, fetch_json=_fetch_json, fetch_text=_fetch_text)
            except ResourceLibraryError:
                raise
            except ValueError as exc:
                raise ResourceLibraryError(f'資源目錄格式無效，本次結果未保存：{exc}', status=502) from exc
            if not isinstance(rows, list):
                raise ResourceLibraryError('資源目錄格式無效，本次結果未保存。', status=502)
            candidates, warnings = [], []
            for index, row in enumerate(rows[:count], 1):
                try:
                    if not isinstance(row, dict):
                        raise ResourceLibraryError('資源資料格式無效。')
                    candidates.append(self._candidate(row, provider))
                except ResourceLibraryError as exc:
                    warnings.append(f'第 {index} 個結果略過：{exc}')
            if warnings and not candidates:
                raise ResourceLibraryError(f'資源目錄返回的 {len(warnings)} 項資源均無法安全讀取，本次結果未保存。', status=502)
            return {'items': candidates, 'skippedCount': len(warnings), 'warnings': warnings}
        if provider == 'sketchfab':
            url = 'https://api.sketchfab.com/v3/search?' + urlencode({'type': 'models', 'q': query, 'downloadable': 'true', 'count': count})
            response = _fetch_json(url)
            if not isinstance(response, dict) or not isinstance(response.get('results'), list):
                raise ResourceLibraryError('Sketchfab 搜尋回應格式無效，本次結果未保存。')
            candidates, warnings = [], []
            for index, raw in enumerate(response['results'][:count], 1):
                try:
                    if not isinstance(raw, dict):
                        raise ResourceLibraryError('資源資料格式無效。')
                    uid = _sketchfab_uid(raw.get('uid'))
                    if uid is None:
                        raise ResourceLibraryError('來源 UID 格式無效。')
                    images = raw.get('thumbnails', {}).get('images', []) if isinstance(raw.get('thumbnails'), dict) else []
                    images = images if isinstance(images, list) else []
                    images = [i for i in images if isinstance(i, dict) and isinstance(i.get('url'), str) and type(i.get('width')) is int]
                    preview = min(images, key=lambda i: abs(i['width'] - 720))['url'] if images else ''
                    license_info = raw.get('license') if isinstance(raw.get('license'), dict) else {}
                    owner = raw.get('user') if isinstance(raw.get('user'), dict) else {}
                    candidates.append(self._candidate({'name': raw.get('name', ''), 'url': 'https://sketchfab.com/models/' + uid,
                        'kind': kind, 'previewUrl': preview, 'description': '公開可下載模型；使用前核對作者與許可。',
                        'license': license_info.get('label') or '未標明，使用前需核對',
                        'price': '免費可下載；下載需登入來源帳戶',
                        'provenance': [{'source': 'Sketchfab official public API', 'author': str(owner.get('displayName') or owner.get('username') or '')[:240]}]}, provider))
                except ResourceLibraryError as exc:
                    warnings.append(f'第 {index} 個結果略過：{exc}')
            if warnings and not candidates:
                raise ResourceLibraryError(f'Sketchfab 返回的 {len(warnings)} 項資源均無法安全讀取，本次結果未保存。', status=502)
            return {'items': candidates, 'skippedCount': len(warnings), 'warnings': warnings}
        response = _fetch_json('https://api.polyhaven.com/assets?' + urlencode({'type': {'model': 'models', 'texture': 'textures', 'hdri': 'hdris'}[kind]}))
        if not isinstance(response, dict):
            raise ResourceLibraryError('Poly Haven 搜尋回應格式無效，本次結果未保存。')
        tokens = query.casefold().split()
        matches = []
        for slug, raw in response.items():
            if not isinstance(raw, dict) or not re.fullmatch(r'[a-zA-Z0-9_-]+', slug):
                raise ResourceLibraryError('Poly Haven 資源身份無效，本次結果未保存。')
            tags = raw.get('tags') if isinstance(raw.get('tags'), list) else []
            categories = raw.get('categories') if isinstance(raw.get('categories'), list) else []
            name = raw.get('name', '')
            haystack = ' '.join([slug, str(name), *map(str, tags), *map(str, categories)]).casefold()
            if not all(token in haystack for token in tokens):
                continue
            matches.append((slug, raw))
        candidates = []
        for slug, raw in sorted(matches, key=lambda pair: (str(pair[1].get('name', '')).casefold(), pair[0]))[:count]:
            description = raw.get('description') if isinstance(raw.get('description'), str) else ''
            authors = raw.get('authors') if isinstance(raw.get('authors'), dict) else {}
            candidates.append(self._candidate({'name': raw.get('name', slug), 'url': 'https://polyhaven.com/a/' + quote(slug),
                'kind': kind, 'previewUrl': raw.get('thumbnail_url') or '', 'description': description[:4000],
                'license': 'CC0', 'price': '免費',
                'provenance': [{'source': 'Poly Haven official public API', 'authors': ', '.join(authors)[:1000]}]}, provider))
        return candidates
