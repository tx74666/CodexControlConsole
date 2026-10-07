"""Read-only adapters for fixed public asset catalogues.

The injected fetchers own transport limits, TLS and redirect policy. Adapters
construct their own official endpoints and never follow a result, thumbnail or
download URL. Metadata remains a candidate for the resource library to validate.
"""
from html.parser import HTMLParser
import re
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit


CATALOG_PROVIDERS = [
    {'id': 'ambientcg', 'name': 'ambientCG', 'kinds': ['texture', 'model', 'hdri'],
     'mode': 'api', 'defaultKind': 'texture',
     'note': '官方 v3 目錄與縮圖，材質／模型／HDRI 均為 CC0。'},
    {'id': 'kenney', 'name': 'Kenney', 'kinds': ['model', 'vfx', 'texture', 'other'],
     'mode': 'api', 'defaultKind': 'model',
     'note': '官方免費 CC0 素材包；包含模型、2D 特效與其他遊戲素材。'},
    {'id': 'opengameart', 'name': 'OpenGameArt', 'kinds': ['model', 'texture', 'other'],
     'mode': 'api', 'defaultKind': 'model',
     'note': '官方模型／材質／2D 目錄（2D 含特效）；許可需逐項核對。'},
]

OFFICIAL_SOURCES = {
    'ambientcg': ['https://docs.ambientcg.com/api/v3/assets', 'https://docs.ambientcg.com/license/'],
    'kenney': ['https://kenney.nl/support', 'https://kenney.nl/assets/particle-pack'],
    'opengameart': ['https://opengameart.org/art-search-advanced', 'https://opengameart.org/content/car-0'],
}

_AMBIENT_TYPES = {'model': '3d-model', 'texture': 'material', 'hdri': 'hdri'}
_KENNEY_PATHS = {'model': '/assets/category:3D', 'vfx': '/assets/series:VFX',
                 'texture': '/assets/category:Textures', 'other': '/assets'}
_OGA_TYPES = {'model': '10', 'texture': '14', 'other': '9'}
_VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
              'link', 'meta', 'param', 'source', 'track', 'wbr'}


class _Element:
    __slots__ = ('tag', 'attrs', 'children')

    def __init__(self, tag, attrs=()):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []

    def has_class(self, value):
        return value in (self.attrs.get('class') or '').split()

    def walk(self):
        # An iterative walk keeps malformed, deeply nested pages bounded.
        pending = [self]
        while pending:
            element = pending.pop()
            yield element
            pending.extend(c for c in reversed(element.children) if isinstance(c, _Element))

    def text(self):
        values = []
        pending = [self]
        while pending:
            current = pending.pop()
            if isinstance(current, str):
                values.append(current)
            elif current.tag not in {'script', 'style'}:
                pending.extend(reversed(current.children))
        return re.sub(r'\s+', ' ', ''.join(values)).strip()


class _Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = _Element('document')
        self.stack = [self.root]
        self.node_count = 0
        if not isinstance(html, str):
            raise ValueError('資源目錄回應不是 HTML 文字。')
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.node_count += 1
        if self.node_count > 100000 or len(self.stack) > 256:
            raise ValueError('資源目錄 HTML 結構超過解析上限。')
        element = _Element(tag, attrs)
        self.stack[-1].children.append(element)
        if tag not in _VOID_TAGS:
            self.stack.append(element)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _official_url(value, origin, path_pattern):
    """Return only the expected source's display URL; make no network request."""
    if not isinstance(value, str) or not value or len(value) > 4096:
        return ''
    if '\\' in value or any(ord(c) < 33 for c in value) or re.search(r'%(?:00|0a|0d)', value, re.I):
        return ''
    try:
        parts = urlsplit(urljoin(origin, value))
        expected = urlsplit(origin)
        if (parts.scheme != 'https' or parts.hostname != expected.hostname or
                parts.username is not None or parts.password is not None or
                parts.port not in (None, 443) or not re.fullmatch(path_pattern, parts.path)):
            return ''
        return urlunsplit(('https', expected.netloc, parts.path, parts.query, ''))
    except ValueError:
        return ''


def _first(elements, test):
    return next((e for e in elements if test(e)), None)


def _provenance(provider, query, endpoint, note):
    return [{'source': provider, 'query': query, 'url': endpoint, 'note': note}]


def _invalid_item():
    # The caller's shared validator counts this row and reports a public warning.
    return {'name': '', 'url': '', 'kind': 'other', 'previewUrl': '',
            'description': '', 'license': '', 'price': '', 'provenance': []}


def _ambientcg(kind, query, count, fetch_json):
    asset_type = _AMBIENT_TYPES[kind]
    endpoint = 'https://ambientcg.com/api/v3/assets?' + urlencode({
        'q': query, 'type': asset_type, 'limit': count,
        'include': 'type,title,url,shortDescription,thumbnails'})
    data = fetch_json(endpoint)
    if not isinstance(data, dict) or not isinstance(data.get('assets'), list):
        raise ValueError('ambientCG v3 目錄格式無效。')
    results = []
    for row in data['assets'][:count]:
        if not isinstance(row, dict) or row.get('type') != asset_type:
            results.append(_invalid_item())
            continue
        asset_id = row.get('id')
        if not isinstance(asset_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', asset_id):
            results.append(_invalid_item())
            continue
        expected_url = 'https://ambientcg.com/a/' + asset_id
        source_url = _official_url(row.get('url'), 'https://ambientcg.com', r'/a/' + re.escape(asset_id))
        thumbnails = row.get('thumbnails')
        preview = ''
        if isinstance(thumbnails, dict):
            for key in ('512-PNG', '512-WEBP', '256-PNG', '256-WEBP', '128-PNG'):
                preview = _official_url(thumbnails.get(key), 'https://acg-media.struffelproductions.com',
                                        r'/file/ambientCG-Web/media/thumbnail/[^/]+/[^/]+\.(?i:png|jpg|webp)')
                if preview:
                    break
        results.append({'name': row.get('title', asset_id), 'url': source_url if source_url == expected_url else '',
                        'kind': kind, 'previewUrl': preview,
                        'description': row.get('shortDescription') or 'ambientCG 官方資源；使用前核對資源頁。',
                        'license': 'CC0', 'price': '免費',
                        'provenance': _provenance('ambientCG', query, endpoint,
                                                  '官方 v3 API；資源與預覽圖採 CC0。')})
    return results


def _kenney(kind, query, count, fetch_text):
    endpoint = 'https://kenney.nl' + _KENNEY_PATHS[kind] + '?' + urlencode({'search': query})
    document = _Document(fetch_text(endpoint))
    if not _first(document.root.walk(), lambda e: e.tag == 'input' and e.attrs.get('name') == 'search'):
        raise ValueError('Kenney 目錄格式無效。')
    results = []
    for card in (e for e in document.root.walk() if e.has_class('asset')):
        if len(results) >= count:
            break
        heading = _first(card.walk(), lambda e: e.tag == 'h2')
        link = _first(heading.walk(), lambda e: e.tag == 'a') if heading else None
        if link is None:
            results.append(_invalid_item())
            continue
        categories = [e.attrs.get('href', '') for e in card.walk() if e.tag == 'a']
        if any('/assets/category:3D' in href for href in categories):
            actual_kind = 'model'
        elif any('/assets/series:VFX' in href for href in categories):
            actual_kind = 'vfx'
        elif any('/assets/category:Textures' in href for href in categories):
            actual_kind = 'texture'
        else:
            actual_kind = 'other'
        if kind != 'other' and actual_kind != kind:
            results.append(_invalid_item())
            continue
        cover = _first(card.walk(), lambda e: e.has_class('cover'))
        image_match = re.search(r'background-image\s*:\s*url\((?:[\"\']?)([^\"\')]+)(?:[\"\']?)\)',
                                (cover.attrs.get('style') or '') if cover else '', re.I)
        preview = _official_url(image_match.group(1), 'https://kenney.nl',
                                r'/media/pages/assets/[^/]+/[^/]+/[^/]+\.(?i:png|jpg|jpeg|webp)') if image_match else ''
        results.append({'name': link.text(),
                        'url': _official_url(link.attrs.get('href'), 'https://kenney.nl', r'/assets/[a-zA-Z0-9_-]+'),
                        'kind': actual_kind, 'previewUrl': preview,
                        'description': 'Kenney 官方素材包（整包預覽）；下載後再選取包內素材。',
                        'license': 'CC0', 'price': '免費／自願贊助',
                        'provenance': _provenance('Kenney', query, endpoint,
                                                  '官方素材目錄；資產頁素材採 CC0。')})
    return results


def _opengameart(kind, query, count, fetch_text):
    endpoint = 'https://opengameart.org/art-search-advanced?' + urlencode({
        'keys': query, 'field_art_type_tid[]': _OGA_TYPES[kind], 'items_per_page': 24})
    document = _Document(fetch_text(endpoint))
    main = _first(document.root.walk(), lambda e: e.attrs.get('id') == 'right')
    # The live site's advanced form is outside #right. Validate its actual
    # selected filter across the document, then limit result cards to #right.
    type_filter = _first(document.root.walk(), lambda e: e.tag == 'select' and e.attrs.get('name') == 'field_art_type_tid[]')
    if (main is None or not _first(document.root.walk(), lambda e: e.tag == 'input' and e.attrs.get('name') == 'keys') or
            type_filter is None or
            _first(document.root.walk(), lambda e: e.has_class('messages') and e.has_class('error'))):
        raise ValueError('OpenGameArt 進階目錄格式無效。')
    selected_types = [e.attrs.get('value') for e in type_filter.walk()
                      if e.tag == 'option' and 'selected' in e.attrs]
    if selected_types != [_OGA_TYPES[kind]]:
        raise ValueError('OpenGameArt 未確認套用要求的資源類型。')
    results = []
    for card in (e for e in main.walk() if e.has_class('art-previews-inline')):
        if len(results) >= count:
            break
        title = _first(card.walk(), lambda e: e.has_class('art-preview-title'))
        link = _first(title.walk(), lambda e: e.tag == 'a') if title else None
        image_field = _first(card.walk(), lambda e: e.has_class('field-name-field-art-preview'))
        image = _first(image_field.walk(), lambda e: e.tag == 'img') if image_field else None
        if link is None:
            results.append(_invalid_item())
            continue
        results.append({'name': link.text(),
                        'url': _official_url(link.attrs.get('href'), 'https://opengameart.org', r'/content/[a-zA-Z0-9_%.-]+'),
                        'kind': kind,
                        'previewUrl': _official_url(image.attrs.get('src'), 'https://opengameart.org',
                                                   r'/sites/default/files/[^?]+\.(?i:png|jpg|jpeg|gif|webp)') if image else '',
                        'description': 'OpenGameArt 官方 2D 目錄（含特效）；許可與作者需到原頁核對。' if kind == 'other'
                                       else 'OpenGameArt 官方資源；許可與作者需到原頁核對。',
                        'license': '待核對（見來源頁）', 'price': '免費；許可待核對',
                        'provenance': _provenance('OpenGameArt', query, endpoint,
                                                  '官方進階搜尋；列表不提供完整許可，未抓取詳情或素材。')})
    return results


def search_catalog(provider, kind, query, count, *, fetch_json, fetch_text):
    """Return bounded candidate metadata using one fixed official endpoint."""
    descriptor = next((p for p in CATALOG_PROVIDERS if p['id'] == provider), None)
    if descriptor is None or kind not in descriptor['kinds']:
        raise ValueError('資源來源或類型無效。')
    if (not isinstance(query, str) or not query.strip() or len(query) > 240 or
            any(ord(c) < 32 for c in query) or type(count) is not int or not 1 <= count <= 24):
        raise ValueError('資源搜尋詞或數量無效。')
    query = query.strip()
    if provider == 'ambientcg':
        return _ambientcg(kind, query, count, fetch_json)
    if provider == 'kenney':
        return _kenney(kind, query, count, fetch_text)
    return _opengameart(kind, query, count, fetch_text)
